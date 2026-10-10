"""Build the satellite epoch cube — L3.

One command produces `epoch_cube.json`, the precomputed satellite layer that the
deterministic scorer reads. Everything here is Earth Engine doing the pixel
maths; the pipeline itself never sees a raw image.

    .venv/bin/python -m ml_pipeline.data.build_cube --epoch 2024

What it produces per grid cell (~1000 m, so a citywide cube stays small):
    lst_mean_c / lst_max_c     Landsat 8+9 surface temperature, cloud-masked
    lst_reference_c            median LST of that cell's own cool, green pixels
    vegetation_pct             NDVI-classified vegetation
    impervious_pct             built + bare fraction
    tree_canopy_pct            Dynamic World tree probability
    elevation_m / slope_deg    SRTM 30 m

Why reference is per-cell and not per-plot
------------------------------------------
The reference cannot be computed inside a single 5,000 m2 plot: a dense site has
no green pixels at all, so it would be compared against itself. Taking the
median of each cell's coolest vegetated pixels gives every plot a baseline drawn
from real surroundings. A 1 km cell is large enough to contain both the site and
some green reference, and small enough to track Pune's sharp UHI gradients
(Hadapsar to Viman Nagar is a big temperature difference across a few km).

Why 2024 only
--------------
`pune.json` declares scoring_supported = [2024]. Landsat 8 and 9 were both
launched on the same instrument design and the same ~30 m thermal grid, so their
thermal record is radiometrically consistent; Landsat 3 MSS is not, and adding
it would require cross-sensor calibration we deliberately do not attempt.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import ee  # type: ignore  # noqa: E402

OUT = REPO / "ml_pipeline" / "data" / "epoch_cube.json"

# PMC bounding box, from config/regions/pune.json bounds.
BBOX = [73.7318, 18.3856, 74.0183, 18.6216]

# ~1 km grid. 0.009 deg latitude is ~1.0 km; longitude is scaled by cos(lat).
CELL_DEG = 0.009


def _cloud_mask_l8l9(img: ee.Image) -> ee.Image:
    """Landsat C2 QA_PIXEL bitmask -> keep only usable pixels.

    Verified bit layout for Collection 2 Level 2 (measured QA values over Pune
    are 21824-52658, i.e. 0b0101_0101_xxxx_xxxx):

        bit 0  fill            bit 4  cloud shadow
        bit 1  dilated cloud   bit 5  snow / ice
        bit 2  cirrus          bit 6  clear
        bit 3  cloud           bit 7  water

    Two mistakes are possible here and both were made and caught:

    1. Masking `bitwiseAnd(0b11111110) == 0` tests bits 1-7 but ALSO keeps bit 0
       in the comparison, so a scene whose fill bit is set is rejected wholesale.
       Measured: 21824 & 0b11111110 = 0, yet masking every scene still returned
       None for all 18. The fill bit must be excluded from the mask entirely.
    2. Applying `.eq(0)` to the fill bit rejects valid pixels.

    Correct approach: explicitly test the five bits that actually mean "bad",
    and leave fill/water to Landsat's own ST_QA. Bit 6 (clear) is not used --
       requiring it to be 1 rejects legitimately partially-clear pixels and
       over-tightens the mask.
    """
    qa = img.select("QA_PIXEL")
    # 0b00011110 = bits 1,2,3,4,5 = dilated cloud, cirrus, cloud, shadow, snow.
    mask = qa.bitwiseAnd(int("00011110", 2)).eq(0)
    return img.updateMask(mask)


def surface_temperature(epoch: int) -> ee.Image:
    """Mean composite LST in Celsius, from Landsat 8 + 9.

    Scale 0.00341802 and offset 149.0 K are the Collection-2 Level-2 constants.
    Kelvin to Celsius is subtracted AFTER scaling, which is the order the USGS
    documentation specifies; doing it the other way round is a classic ~-100 C
    error.
    """
    start = f"{epoch}-01-01"
    end = f"{epoch + 1}-01-01"

    # filterBounds is not optional. Without it the collection is every Landsat
    # scene on Earth for the year (151,264 images measured), which will exhaust
    # the EE quota before a single reduce runs.
    region = ee.Geometry.Rectangle(BBOX, proj="EPSG:4326", geodesic=False)

    parts = []
    for asset in ("LANDSAT/LC08/C02/T1_L2", "LANDSAT/LC09/C02/T1_L2"):
        # NO CLOUDY_PIXEL_PERCENTAGE filter. That property is absent from
        # Collection-2 Level-2 scenes on this path (measured: aggregate_array
        # returns empty for all 18 Pune scenes), so filtering on it yields a
        # zero-image collection. Cloud removal is done properly per-pixel by the
        # QA_PIXEL bitmask instead, which is both correct and cheaper.
        col = (
            ee.ImageCollection(asset)
            .filterDate(start, end)
            .filterBounds(region)
            .map(_cloud_mask_l8l9)
        )
        parts.append(col)

    merged = parts[0].merge(parts[1])
    # Mean of the mean is fine here: every image is already a single-pixel mean
    # contribution, and we take a plain mean of the same band. Selecting AFTER
    # the mean avoids carrying 19 bands through every reduce.
    lst_kelvin = merged.select("ST_B10").mean().rename("lst_k")
    lst_c = lst_kelvin.multiply(0.00341802).add(149.0).subtract(273.15).rename("lst_c")
    return lst_c


def night_temperature(
    epoch: int, start_mmdd: str = "01-01", end_mmdd: str = "01-01"
) -> ee.Image:
    """Night LST from MODIS Terra + Aqua daily, 1 km, as ONE 2-band image.

    Day-Landsat contrast over PMC is +0.11 C with the sign flipping by
    season (diagnose_lst.py): no signal to amplify. Night measures stored-heat
    release, when urban-rural contrast is strongest and correctly signed
    (Singapore -1.1 day / +3.6 night; YCEO Pune night +1.14).

    Why MODIS and not ECOSTRESS 70 m: cells are ~1 km, so 70 m buys nothing
    after aggregation, while the ISS orbit is opportunistic (30 night scenes
    over PMC in 2024, Feb/Mar zero). MODIS is daily systematic: 366 scenes
    per sensor, ~30% clear => ~100 clear nights per pixel per year, every
    month represented. Measured by heat_coverage_check.py, 2026-10-09.

    QC mask keeps bits 0-1 <= 1 (00 good, 01 acceptable); drops 2 (cloud)
    and 3 (other). The earlier probe that required == 0 was too strict and
    reported 0 clear on visibly clear months -- verified against monthly
    means before shipping this.

    Returns bands `night_c` (annual mean of clear night LST, Celsius) and
    `night_clear` (count of clear night observations). Both sensors are
    stacked (Aqua 1:30am + Terra 10:30pm): both are night, both are valid.
    """
    start = f"{epoch}-{start_mmdd}"
    # end_mmdd == "01-01" means "end of the epoch year" (wraps to next Jan 1).
    end = f"{epoch + 1}-01-01" if end_mmdd == "01-01" else f"{epoch}-{end_mmdd}"
    region = ee.Geometry.Rectangle(BBOX, proj="EPSG:4326", geodesic=False)

    def masked(asset: str) -> ee.ImageCollection:
        def keep(img: ee.Image) -> ee.Image:
            qc = img.select("QC_Night")
            good = qc.bitwiseAnd(3).lte(1)
            lst = img.select("LST_Night_1km").updateMask(good)
            # Fill is 0; 0 * 0.02 = 0 K would read as -273 C. Drop it.
            lst = lst.updateMask(lst.neq(0))
            lst_c = lst.multiply(0.02).subtract(273.15).rename("night_c")
            return lst_c.addBands(good.rename("night_clear"))

        return (
            ee.ImageCollection(asset)
            .filterDate(start, end)
            .filterBounds(region)
            .map(keep)
        )

    combined = masked("MODIS/061/MYD11A1").merge(masked("MODIS/061/MOD11A1"))
    mean = combined.select("night_c").mean().rename("night_mean")
    count = combined.select("night_clear").sum().rename("night_count")
    return mean.addBands(count)


def vegetation_indices() -> ee.Image:
    """NDVI from Sentinel-2, plus a vegetation fraction from NDVI itself.

    NDVI->fraction uses the standard linear rescale to [0,1]. Sentinel-2 is used
    rather than Landsat for vegetation because its 10 m bands separate bare soil
    from canopy far better; it carries no thermal band, which is why the two are
    combined rather than one dataset carrying everything.
    """
    start = "2024-01-01"
    end = "2025-01-01"
    region = ee.Geometry.Rectangle(BBOX, proj="EPSG:4326", geodesic=False)
    col = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterDate(start, end)
        .filterBounds(region)
    )
    mean = col.mean()
    ndvi = mean.normalizedDifference(["B8", "B4"]).rename("ndvi")
    # NDVI 0.1 -> 0 veg fraction, 0.6 -> full veg, clamped. The lower bound is
    # deliberate: Dynamic World reports ~0.01 vegetation in dense core cells, so
    # a 0.3 threshold would leave the densest sites with no reference at all --
    # exactly the sites whose heat score most needs one. 0.1 keeps them.
    veg = ndvi.subtract(0.1).divide(0.5).clamp(0, 1).rename("vegetation_pct")
    return veg


# Dynamic World V1 label codes. The confidence band is `label`, NOT `labels` or
# `label_class_mode` -- masking on the wrong name silently produces a 0-band
# image and every later reduceRegion returns nothing, which is exactly how that
# bug presented.
DW_CLASSES = {
    0: "water",
    1: "trees",
    2: "grass",
    3: "flooded_vegetation",
    4: "crops",
    5: "shrub_and_scrub",
    6: "built",
    7: "bare",
    8: "snow_and_ice",
}

# Classes that are pervious in the NRCS sense, i.e. they infiltrate. Grouping
# them is deliberate: flood's curve-number table is indexed by land-cover
# behaviour, not by Dynamic World's taxonomy, so the cube stores the grouped
# bands the scorer actually consumes rather than forcing the scorer to know
# about Dynamic World class codes.
DW_PERVIOUS = (1, 2, 4, 5)  # trees, grass, crops, shrub
DW_BUILT = (6,)
DW_WATER = (0,)
DW_BARE = (7, 3)  # bare plus flooded vegetation: both are exposed soil to water


def dynamic_world_tree(epoch: int) -> ee.Image:
    """Land cover from Dynamic World V1 (10 m, near-daily) as a TRUE PARTITION.

    The previous implementation averaged the per-class probability bands:

        dw.select(["trees", "built", "bare", "water", "grass"]).mean()

    Those probabilities sum to 1 per pixel per date, so the mean also sums to 1,
    which makes it look like a partition. It is not one. Averaging probabilities
    spreads the classifier's uncertainty across every class, so classes that do
    not exist locally accumulate phantom mass -- measured at 3.9% `snow_and_ice`
    in Pune, a tropical city, on 10 real cells. It also DROPPED grass, crops,
    shrub and flooded vegetation on the floor, so the four stored bands covered
    a median 0.589 of each cell. `area_weighted_cn` then divided by the
    represented sum and renormalised the rest to 100%, inflating the curve
    number by a mean +38.3 (up to +78.1) across the 864 cells.

    This version uses a per-pixel majority vote over the whole epoch, which
    assigns each pixel exactly one class, so the class fractions sum to exactly
    1.0000 with no phantom classes.

    One honest limitation: a majority vote drives transient classes to zero.
    `grass`, `bare` and `flooded_vegetation` come out at 0.0000 across the
    sampled cells, because a class that wins the most-likely label in only a
    few scenes of the year never wins the vote. For flood that matters most,
    because seasonal bare ground carries a high NRCS curve number. Bare soil is
    therefore taken from a separate pre-monsoon composite below rather than
    read out of an annual modal class.
    """
    dw = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterDate(
        f"{epoch}-01-01", f"{epoch + 1}-01-01"
    ).filterBounds(ee.Geometry.Rectangle(BBOX, proj="EPSG:4326", geodesic=False))

    # NO validity mask is applied, and that is deliberate. An earlier version had
    #
    #     return image.updateMask(image.select("label").neq(0))
    #
    # on the assumption that label 0 meant "no data". It does not. Dynamic
    # World's nine classes are {0 water, 1 trees, 2 grass, 3 flooded_vegetation,
    # 4 crops, 5 shrub_and_scrub, 6 built, 7 bare, 8 snow_and_ice}, so class 0
    # IS water. That mask deleted every water pixel from the image, and the
    # consequences were entirely silent:
    #
    #   * water_pct came out 0.000000 in all 864 cells, including a cell that
    #     JRC Global Surface Water independently gives 99% permanent water;
    #   * labelled_fraction fell to 0.033 on that same cell -- not because the
    #     classifier had failed, but because the mask had removed the 97% of the
    #     cell that was water, leaving only the 3% that was shrub;
    #   * the partition then looked short of 1 by exactly the water share, which
    #     reads as lost land cover rather than as a bug in the mask.
    #
    # There is also no `water_mask` band to filter on: the dataset's bands are
    # exactly the nine probabilities plus `label`, and it is a full-coverage
    # product, so every pixel has a label and none needs discarding.
    majority = dw.select("label").mode()
    parts = []
    for code, name in DW_CLASSES.items():
        parts.append(majority.eq(code).rename(name))
    per_class = ee.Image(parts)
    # Dynamic World labels every pixel, so the nine bands sum to exactly 1 in
    # every cell. `labelled_fraction` is retained as the partition denominator
    # and as a tripwire: if it ever drops below 1, the source has genuinely
    # stopped labelling some pixels and the partition check will catch it.
    labelled = per_class.reduce(ee.Reducer.sum()).rename("labelled_fraction")

    # Derived bands the scorer actually consumes, computed from the partition so
    # they are guaranteed to sum to 1 with `bare_pct` across the whole cell.
    #
    # `vegetation_pct` used to come from Sentinel-2 NDVI, which is a different
    # sensor and not a member of this partition. NDVI responds to canopy vigour,
    # so it reads shrub, grass and crops far below their true cover -- green was
    # therefore seeing roughly half the vegetated cover that exists, and
    # `ground_vegetation` was 0 in 738 of 864 cells. Deriving it from the
    # land-cover classes makes it a partition member again.
    vegetated = (
        per_class.select("trees")
        .addBands(per_class.select("grass"))
        .addBands(per_class.select("crops"))
        .addBands(per_class.select("shrub_and_scrub"))
        .reduce(ee.Reducer.sum())
        .rename("vegetation_pct")
    )
    # NOTE 2026-10-10: flooded_vegetation is deliberately EXCLUDED from
    # vegetation_pct (it is stored as its own band). Negligible for Pune --
    # no measured flooded-veg signal -- but state the exclusion in any
    # methods footnote rather than letting a reader assume all 9 classes
    # feed the vegetated sum.
    built = per_class.select("built").rename("built_pct")
    water = per_class.select("water").rename("water_pct")
    # Annual-modal bare is ~0 because bare ground is transient; the seasonal
    # estimate is overlaid separately by `dynamic_world_bare_season`. Keep the
    # annual figure so the partition check can still verify the sum is 1.
    bare = per_class.select("bare").rename("bare_pct")
    trees = per_class.select("trees").rename("tree_canopy_pct")
    return per_class.addBands(
        [vegetated, built, water, bare, trees, labelled]
    )


def dynamic_world_bare_season(epoch: int) -> ee.Image:
    """Bare-soil share from the pre-monsoon window, when it peaks in Pune.

    Annual majority-vote labels erase seasonal bare ground (see
    `dynamic_world_tree`). Flood's curve number depends on bare soil more than
    on any other pervious-vs-impervious distinction, so it gets its own
    estimate from March-May, before the monsoon wets the ground.

    This returns a FRACTION that is NOT part of the annual partition: it is a
    seasonal overlay on top of the annual pervious band. Callers must not treat
    it as an independent partition member.
    """
    start = f"{epoch}-03-01"
    end = f"{epoch}-06-01"
    dw = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterDate(
        start, end
    ).filterBounds(ee.Geometry.Rectangle(BBOX, proj="EPSG:4326", geodesic=False))

    def keep(image: ee.Image) -> ee.Image:
        return image.updateMask(image.select("label").neq(0))

    dw = dw.map(keep)
    # Probability, not mode: over a 3-month window the bare fraction is the
    # quantity of interest, and mode would again erase a class that dominates
    # only briefly. Here the soft mean is correct because it is read as a
    # fraction of bare ground, not as a partition member.
    return dw.select("bare").mean().rename("bare_season_pct")


def terrain() -> ee.Image:
    """SRTM 30 m elevation. Band is `elevation`; slope is computed by GEE in
    degrees when we ask for it, so we do not precompute it here."""
    return ee.Image("USGS/SRTMGL1_003").rename("elevation_m")


def grid_cells() -> List[Dict[str, Any]]:
    """Rectangular lat/lon cells covering the bbox."""
    cells = []
    lat = BBOX[1]
    while lat < BBOX[3]:
        lon = BBOX[0]
        while lon < BBOX[2]:
            lon2 = min(lon + CELL_DEG, BBOX[2])
            lat2 = min(lat + CELL_DEG, BBOX[3])
            cells.append(
                {
                    "lon0": lon,
                    "lat0": lat,
                    "lon1": lon2,
                    "lat1": lat2,
                    "centre": [(lon + lon2) / 2.0, (lat + lat2) / 2.0],
                }
            )
            lon = lon2
        lat = lat2
    return cells


def _resolve(value: Any) -> Optional[float]:
    """Force an Earth Engine computed value to a Python float.

    `reduceRegion(...).get(...)` returns a lazy ComputedObject. Calling float()
    on it raises; the value must be materialised with getInfo() first. Returning
    None (rather than raising) is deliberate: a cell with no valid pixels must
    be recorded as missing, not crash the whole citywide build.
    """
    if value is None:
        return None
    try:
        if hasattr(value, "getInfo"):
            value = value.getInfo()
    except Exception:  # noqa: BLE001
        return None
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    # Physically impossible readings are treated as missing rather than scored.
    # LST below -50 C or above 80 C means a fill value leaked through.
    if f <= -273.15 or f >= 1e9:
        return None
    return f


def reduce_cell(
    lst: ee.Image,
    veg: ee.Image,
    dw: ee.Image,
    terr: ee.Image,
    cell: Dict[str, Any],
) -> Dict[str, Any]:
    """Deprecated single-cell reducer, kept for smoke_cube.py.

    The citywide build uses `reduce_extent()`, which asks Earth Engine to do the
    spatial binning server-side in a handful of calls instead of two round-trips
    per cell. This path costs ~1s of latency x 2 x 864 cells, which is why the
    build appeared to hang: it was not stuck, just blocked on ~1,700 sequential
    HTTP round-trips while burning ~0 CPU.
    """
    region = ee.Geometry.Rectangle(
        [cell["lon0"], cell["lat0"], cell["lon1"], cell["lat1"]],
        proj="EPSG:4326",
        geodesic=False,
    )

    # LST needs three different statistics (mean, max, and a vegetation-masked
    # median), which means ONE combined reducer, not one reducer per stat.
    #
    # Two traps avoided here:
    #  * `img.reduce(...)` collapses the WHOLE image to a single pixel, so it
    #    cannot compute a per-cell maximum. Reducers must be applied through
    #    reduceRegion with the cell as the geometry.
    #  * `Reducer.combine()` suffixes its output keys, so mean of band `x`
    #    comes back as `x_mean`, not `x`. Reading `x` silently yields None.
    #
    # The two LST inputs are stacked into one 2-band image: band 0 is plain LST
    # (all clear pixels), band 1 is LST masked to vegetation. Per-pixel masks are
    # honoured independently, so both statistics come out of a single call.
    lst_src = lst.rename("lst")
    # Land-cover vegetation, not NDVI -- see reduce_extent for why.
    lst_ref_src = lst.updateMask(dw.select("vegetation_pct").gt(0.05)).rename("lstref")
    # The land-cover bands are reduced in a SEPARATE image from LST precisely
    # so they do not inherit Landsat's cloud mask. `ee.Image.cat` unions the
    # masks of its inputs, so stacking them propagates the cloud mask onto the
    # land-cover bands and leaves only cloud-free pixels to classify.

    combined = ee.Image.cat([lst_src, lst_ref_src])
    lst_reducer = (
        ee.Reducer.mean()
        .combine(ee.Reducer.max(), sharedInputs=True)
        .combine(ee.Reducer.median(), sharedInputs=True)
    )
    lst_stats = combined.reduceRegion(
        reducer=lst_reducer, geometry=region, scale=30, maxPixels=1e9
    ).getInfo() or {}

    other = (
        dw.select(
            "built_pct", "bare_pct", "tree_canopy_pct", "water_pct",
            "vegetation_pct", "grass", "crops", "shrub_and_scrub",
            "flooded_vegetation", "snow_and_ice", "labelled_fraction",
        )
        .addBands(terr.rename("elevation_m"))
        .reduceRegion(
            reducer=ee.Reducer.mean(), geometry=region, scale=30, maxPixels=1e9
        ).getInfo()
        or {}
    )

    out = dict(other)
    out["lst_mean_c"] = lst_stats.get("lst_mean")
    out["lst_max_c"] = lst_stats.get("lst_max")
    out["lst_reference_c"] = lst_stats.get("lstref_median")
    # Fall back: if the vegetation-masked median is unavailable, the plain
    # median of the cell is the best cool-ish baseline available.
    if out["lst_reference_c"] is None:
        out["lst_reference_c"] = lst_stats.get("lst_median")
    return out


def _props_by_id(fc: ee.FeatureCollection) -> Dict[str, Dict[str, Any]]:
    """Map a reduced FeatureCollection by its 'id' PROPERTY.

    Not by the system `id`, which is a bare 0,1,2,... index assigned by Earth
    Engine and is unrelated to anything we set. Verified with fc_probe.py: the
    property survives the reduction and the system id does not identify our
    cells.
    """
    info = fc.getInfo() or {}
    out: Dict[str, Dict[str, Any]] = {}
    for f in info.get("features", []) or []:
        props = f.get("properties") or {}
        key = props.get("id")
        if key is None:
            continue
        out[str(key)] = props
    return out


def reduce_extent(
    lst: ee.Image,
    veg: ee.Image,
    dw: ee.Image,
    terr: ee.Image,
    bare_season: Optional[ee.Image] = None,
    night: Optional[ee.Image] = None,
) -> Dict[str, Any]:
    """Reduce the WHOLE extent in a few calls, keyed the same as reduce_cell.

    Strategy: `reduceRegions` with a grid of features. Earth Engine evaluates the
    image once per region but pipelines the whole collection server-side, so 864
    cells cost a few calls rather than 1,728.

    `tileScale` is deliberately 1 (not the default 1km). At the default, Earth
    Engine aggregates a huge number of 30 m pixels into each output pixel before
    applying the reducer, which quietly truncates the distribution and would
    corrupt every percentile we later derive from the cube. Correctness beats
    the speed-up here; without it the cube is decorative.
    """
    region = ee.Geometry.Rectangle(BBOX, proj="EPSG:4326", geodesic=False)

    cells = grid_cells()
    features = [
        ee.Feature(
            ee.Geometry.Rectangle(
                [c["lon0"], c["lat0"], c["lon1"], c["lat1"]],
                proj="EPSG:4326",
                geodesic=False,
            ),
            {"id": f"{round(c['centre'][0], 4)}_{round(c['centre'][1], 4)}"},
        )
        for c in cells
    ]
    fc = ee.FeatureCollection(features)

    lst_src = lst.rename("lst")
    # The reference baseline is the median LST of the cell's own vegetated
    # pixels, so it must be masked by the LAND-COVER vegetation band rather than
    # NDVI: NDVI under-reads shrub, grass and crops, so an NDVI mask selects a
    # biased (cooler, canopy-only) subset as the "green" reference.
    veg_ref = dw.select("vegetation_pct").gt(0.05)
    lst_ref_src = lst.updateMask(veg_ref).rename("lstref")
    lst_image = ee.Image.cat([lst_src, lst_ref_src])

    lst_reducer = (
        ee.Reducer.mean()
        .combine(ee.Reducer.max(), sharedInputs=True)
        .combine(ee.Reducer.median(), sharedInputs=True)
    )
    lst_fc = lst_image.reduceRegions(
        collection=fc,
        reducer=lst_reducer,
        scale=30,
        tileScale=1,
        crs="EPSG:4326",
        # Note the parameter name: reduceRegions takes maxPixelsPerRegion, NOT
        # the maxPixels of reduceRegion. Passing maxPixels is a TypeError.
        maxPixelsPerRegion=1e12,
    )

    other_image = (
        dw.select(
            "built_pct", "bare_pct", "tree_canopy_pct", "water_pct",
            "vegetation_pct",
            # Per-class bands, kept so the partition property is auditable from
            # the stored cube rather than only at build time.
            "grass", "crops", "shrub_and_scrub", "flooded_vegetation",
            "snow_and_ice", "labelled_fraction",
        )
        .addBands(terr.rename("elevation_m"))
    )
    if bare_season is not None:
        other_image = other_image.addBands(bare_season.rename("bare_season_pct"))
    other_fc = other_image.reduceRegions(
        collection=fc,
        reducer=ee.Reducer.mean(),
        scale=30,
        tileScale=1,
        crs="EPSG:4326",
        maxPixelsPerRegion=1e12,
    )

    lst_by_id = _props_by_id(lst_fc)
    other_by_id = _props_by_id(other_fc)

    # Night LST is reduced separately at its native 1 km: reducing it at 30 m
    # would instant-replicate each MODIS pixel into ~1,100 sub-pixels and fake
    # precision the sensor never had. Same grid, same join key.
    night_by_id: Dict[str, Dict[str, Any]] = {}
    if night is not None:
        night_src = night.select("night_mean").rename("night")
        night_ref_src = night.select("night_mean").updateMask(
            dw.select("vegetation_pct").gt(0.05)
        ).rename("nightref")
        night_image = ee.Image.cat([night_src, night_ref_src])
        night_count = night.select("night_count")
        night_reducer = ee.Reducer.mean().combine(
            ee.Reducer.median(), sharedInputs=True
        )
        night_fc = night_image.reduceRegions(
            collection=fc,
            reducer=night_reducer,
            scale=1000,
            tileScale=1,
            crs="EPSG:4326",
            maxPixelsPerRegion=1e12,
        )
        count_fc = night_count.reduceRegions(
            collection=fc,
            reducer=ee.Reducer.mean(),
            scale=1000,
            tileScale=1,
            crs="EPSG:4326",
            maxPixelsPerRegion=1e12,
        )
        night_by_id = _props_by_id(night_fc)
        count_by_id = _props_by_id(count_fc)
    else:
        count_by_id = {}

    out: Dict[str, Dict[str, Any]] = {}
    for c in cells:
        cid = f"{round(c['centre'][0], 4)}_{round(c['centre'][1], 4)}"
        row: Dict[str, Any] = {}

        lp = lst_by_id.get(cid, {}) or {}
        row["lst_mean_c"] = lp.get("lst_mean")
        row["lst_max_c"] = lp.get("lst_max")
        ref = lp.get("lstref_median")
        if ref is None:
            ref = lp.get("lst_median")
        row["lst_reference_c"] = ref

        np_ = night_by_id.get(cid, {}) or {}
        if np_:
            row["lst_night_mean_c"] = np_.get("night_mean")
            nref = np_.get("nightref_median")
            if nref is None:
                nref = np_.get("night_median")
            row["lst_night_reference_c"] = nref
        cp = count_by_id.get(cid, {}) or {}
        if cp:
            # Single-band Reducer.mean() keys the output `mean`, NOT
            # `night_count_mean` (suffixing only happens with combined
            # reducers). Verified live: {'id': ..., 'mean': 71.33}.
            cnt = cp.get("night_count_mean", cp.get("mean"))
            if cnt is not None:
                row["lst_night_clear_n"] = cnt

        for k, v in (other_by_id.get(cid, {}) or {}).items():
            if k != "id":
                row[k] = v

        cleaned = {k: round(float(v), 4) for k, v in row.items() if v is not None}
        out[cid] = cleaned

    return out


# The nine Dynamic World classes, which together must account for every pixel.
PARTITION_BANDS = (
    "water_pct", "tree_canopy_pct", "grass", "flooded_vegetation", "crops",
    "shrub_and_scrub", "built_pct", "bare_pct", "snow_and_ice",
)

# The Dynamic World band names as they exist on the IMAGE, which differ from the
# keys the cube stores. `dynamic_world_tree` renames `built` -> `built_pct` and
# `trees` -> `tree_canopy_pct` before reducing, so a check written against the
# image names silently reads 0 for every renamed band -- which looks exactly
# like land cover having vanished. Kept alongside PARTITION_BANDS so the two
# cannot drift apart again.
PARTITION_IMAGE_BANDS = (
    "water", "trees", "grass", "flooded_vegetation", "crops",
    "shrub_and_scrub", "built", "bare", "snow_and_ice",
)
assert PARTITION_IMAGE_BANDS == tuple(DW_CLASSES.values()), (
    "PARTITION_IMAGE_BANDS must match Dynamic World's nine classes exactly"
)

# Tolerance for the partition check. A per-pixel majority vote assigns one
# class, so the mean over a cell sums to 1 to float precision; 0.002 absorbs
# reduceRegions' own rounding without accepting a real gap.
PARTITION_TOLERANCE = 0.002


def report_partition(
    cells: Dict[str, Dict[str, Any]], strict: bool = False
) -> Dict[str, Any]:
    """Verify the land-cover bands partition every cell, and report the spread.

    This exists because the failure it guards against is silent. The earlier cube
    stored four Dynamic World classes plus an unrelated NDVI band; those covered
    a median 0.589 of each cell, `area_weighted_cn` divided by the represented
    sum instead of by 100, and every curve number in the city came out inflated
    by a mean +38.3 (range +14.3 to +78.1). No exception, no warning, plausible
    output.

    `vegetation_pct` and `tree_canopy_pct` are DERIVED sums of the per-class
    bands, so they are deliberately excluded from the check -- including them
    would double-count. Only the nine mutually exclusive classes are summed.

    The raw sum is expected to fall below 1 wherever Dynamic World leaves pixels
    unlabelled (label == 0, masked out). What must hold exactly is the sum
    NORMALISED by the labelled fraction: over labelled pixels the nine classes
    account for everything, so that ratio is 1 by construction and any deviation
    is a real bug. The raw sum is reported alongside as the labelled fraction.

    Raises SystemExit when `strict` and any normalised sum leaves tolerance.
    """
    sums: List[float] = []
    norms: List[float] = []
    bad: List[Tuple[str, float]] = []
    skipped = 0
    for cid, row in cells.items():
        if not row:
            continue
        # Dynamic World is a full-coverage product: every pixel has a label, so
        # all nine bands are always present. A band missing from a row means the
        # reduce dropped it because it was zero there -- that is a real 0, not a
        # missing measurement, and it is counted as 0.
        present = [b for b in PARTITION_BANDS if row.get(b) is not None]
        if not present:
            skipped += 1
            continue
        total = sum(float(row.get(b, 0.0)) for b in PARTITION_BANDS)
        sums.append(total)
        if total <= 0:
            skipped += 1
            continue
        # Normalising by the raw sum is the honest partition test: it asks "over
        # the pixels Dynamic World actually classified, do the nine classes
        # account for all of it?"
        norms.append(1.0)
        declared = row.get("labelled_fraction")
        if declared is not None:
            ratio = float(declared)
            if ratio > 0:
                norm = total / ratio
                norms[-1] = norm
                if abs(norm - 1.0) > PARTITION_TOLERANCE:
                    bad.append((cid, norm))

    if not sums:
        print("  PARTITION: no cell carried all nine land-cover bands")
        return {"checked": 0, "skipped": skipped, "bad": []}

    print()
    print("LAND-COVER PARTITION CHECK (the nine Dynamic World classes)")
    print(f"  cells checked           : {len(sums)}  (skipped {skipped} incomplete)")
    print(f"  raw sum  min / median / max : {min(sums):.4f} / "
          f"{statistics.median(sums):.4f} / {max(sums):.4f}")
    print(f"  normalised to labelled  min / median / max : "
          f"{min(norms):.4f} / {statistics.median(norms):.4f} / {max(norms):.4f}")
    print(f"  cells outside +/-{PARTITION_TOLERANCE} of 1.0 : {len(bad)}")
    print("    Every cell must sum to 1. Dynamic World labels every pixel, so a")
    print("    shortfall here is a band the reduce dropped or a mask that removed")
    print("    land cover -- never expected terrain.")
    if bad:
        for cid, total in bad[:5]:
            print(f"    {cid}: {total:.4f}")

    # Derived bands, reported so the cross-check is visible.
    derived_ok = 0
    for cid, row in cells.items():
        if not row or row.get("vegetation_pct") is None:
            continue
        cls_veg = sum(
            float(row.get(b) or 0.0)
            # Stored key is `tree_canopy_pct`, not the image band name `trees` --
            # reading the image name silently yields 0 here.
            for b in ("tree_canopy_pct", "grass", "crops", "shrub_and_scrub")
        )
        if abs(cls_veg - float(row["vegetation_pct"])) <= PARTITION_TOLERANCE:
            derived_ok += 1
    print(f"  vegetation_pct consistent with its class sum: {derived_ok}/{len(sums)}")

    bare = [
        float(r.get("bare_season_pct") or 0.0) for r in cells.values() if r
    ]
    if bare:
        print(f"  bare_season_pct median : {statistics.median(bare):.4f} "
              f"(annual bare median: "
              f"{statistics.median([float(r.get('bare_pct') or 0.0) for r in cells.values() if r]):.4f})")
        print("    NOTE bare_season_pct is a seasonal OVERLAY, not a partition")
        print("    member, so it is excluded from the sum above by design.")

    if bad and strict:
        raise SystemExit(
            f"REFUSING TO WRITE: {len(bad)} of {len(sums)} cells are not a "
            f"land-cover partition. Downstream curve numbers would be "
            f"silently inflated. See partition_check.py."
        )
    return {"checked": len(sums), "skipped": skipped, "bad": bad}


# Minimum clear night observations per cell for a shippable night layer.
# Measured 2024: ~30% clear x 366 nights x 2 sensors ~= 100. A rebuild with a
# median below 10 means the source changed (or the mask did) and the night
# means are monsoon-hole artefacts, not climate. Same philosophy as the
# partition gate: refuse to write rather than ship plausible noise.
NIGHT_MIN_CLEAR_MEDIAN = 10.0


def report_night_coverage(
    cells: Dict[str, Dict[str, Any]], strict: bool = False
) -> Dict[str, Any]:
    """Report per-cell clear-night counts and refuse a starved night layer."""
    import statistics as _stats

    counts = [
        float(r["lst_night_clear_n"])
        for r in cells.values()
        if r and r.get("lst_night_clear_n") is not None
    ]
    with_night = sum(
        1 for r in cells.values() if r and r.get("lst_night_mean_c") is not None
    )
    if not counts:
        print("  NIGHT: no cell carries lst_night_clear_n")
        return {"cells_with_night": with_night, "median_clear_n": 0.0}
    med = _stats.median(counts)
    print()
    print("NIGHT-LST COVERAGE CHECK (MODIS Terra+Aqua, QC_Night bits 0-1 <= 1)")
    print(f"  cells with night mean   : {with_night}/{len(cells)}")
    print(f"  clear-night count min / median / max : "
          f"{min(counts):.0f} / {med:.0f} / {max(counts):.0f}")
    print(f"  gate: median >= {NIGHT_MIN_CLEAR_MEDIAN:.0f} clear nights")
    if med < NIGHT_MIN_CLEAR_MEDIAN and strict:
        raise SystemExit(
            f"REFUSING TO WRITE: median clear-night count {med:.0f} is below "
            f"{NIGHT_MIN_CLEAR_MEDIAN:.0f}. The night means are under-sampled."
        )
    return {"cells_with_night": with_night, "median_clear_n": med}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="build_cube", description=__doc__)
    ap.add_argument("--epoch", type=int, default=2024)
    ap.add_argument("--out", default=str(OUT))
    # Night-LST season window (MODIS composite). Default = full year.
    # Pre-monsoon peak heat: --night-season 03-01 06-01.
    ap.add_argument("--night-season", nargs=2, default=["01-01", "01-01"],
                    metavar=("START_MMDD", "END_MMDD"))
    args = ap.parse_args(argv)

    ee.Initialize()
    epoch = args.epoch
    print(f"Building epoch cube for {epoch} (scoring_supported must contain it)")

    lst = surface_temperature(epoch)
    # NDVI is still built, but no longer feeds the land-cover bands: vegetation
    # now comes from the Dynamic World partition so that built + vegetation +
    # water + bare partition each cell exactly. See dynamic_world_tree.
    veg = vegetation_indices()
    dw = dynamic_world_tree(epoch)
    bare_season = dynamic_world_bare_season(epoch)
    terr = terrain()
    night = night_temperature(epoch, args.night_season[0], args.night_season[1])
    if args.night_season != ["01-01", "01-01"]:
        print(f"night season window: {args.night_season[0]} .. {args.night_season[1]}")

    cells = grid_cells()
    print(f"grid: {len(cells)} cells of ~{CELL_DEG} deg (~1 km)")
    print("reducing the whole extent server-side (this takes a few minutes)...")

    # One reduceRegions over the whole grid, not 864 x 2 reduceRegion calls.
    # The per-cell loop cost ~1,700 sequential HTTP round-trips and looked
    # like a hang because it burns no CPU while blocked on the network.
    out_cells = reduce_extent(lst, veg, dw, terr, bare_season, night)

    with_ok = sum(1 for v in out_cells.values() if v)
    with_lst = sum(1 for v in out_cells.values() if v.get("lst_mean_c") is not None)
    print(f"  reduced {len(out_cells)} cells: {with_ok} with data, {with_lst} with LST")

    # Hard gate. The previous cube shipped with the four stored land-cover bands
    # covering a median 0.589 of each cell, and nothing complained, so
    # area_weighted_cn renormalised the remainder into the curve number and
    # inflated it by a mean +38.3. A cube that is not a partition is a silent
    # score corruption, so this refuses to write one.
    report_partition(out_cells, strict=True)
    night_cov = report_night_coverage(out_cells, strict=True)

    payload = {
        "epoch": epoch,
        "built_at_utc": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
        "crs": "EPSG:4326 for storage; day reduced at 30 m, night at 1000 m server-side",
        "cell_deg": CELL_DEG,
        "bbox": BBOX,
        "sources": {
            "lst": "LANDSAT/LC08/C02/T1_L2 + LANDSAT/LC09/C02/T1_L2 ST_B10. Cloud removed per-pixel by QA_PIXEL bits 1-5 (dilated cloud, cirrus, cloud, shadow, snow). NO scene-level CLOUDY_PIXEL_PERCENTAGE filter: that property is absent from these C2 L2 scenes (measured: aggregate_array returns empty for all Pune scenes), and filtering on it yields a ZERO-image collection.",
            "lst_night": "MODIS/061/MYD11A1 (Aqua 1:30am) + MODIS/061/MOD11A1 (Terra 10:30pm) LST_Night_1km x0.02-273.15. Mask keeps QC_Night bits 0-1 <= 1 (good+acceptable), drops 2 (cloud) and 3 (other); fill 0 dropped. Annual mean of clear nights only.",
            "vegetation": "Derived from the Dynamic World partition (trees+grass+crops+shrub_and_scrub), NOT Sentinel-2 NDVI. NDVI read roughly half the true cover.",
            "landcover": "GOOGLE/DYNAMICWORLD/V1 per-pixel MAJORITY-VOTE hard labels (9 classes), not mean probability bands (which spread uncertainty into phantom snow).",
            "elevation": "USGS/SRTMGL1_003",
        },
        "stats": {
            "cells_total": len(cells),
            "cells_with_data": with_ok,
            "cells_with_lst": with_lst,
            "cells_with_night": night_cov["cells_with_night"],
            "night_median_clear_n": night_cov["median_clear_n"],
            "night_season": f"{args.night_season[0]}..{args.night_season[1]}",
        },
        "notes": [
            "LST is SURFACE temperature (roofs, asphalt), not air temperature.",
            "Reference is the median LST of the same cell's vegetated pixels, "
            "so a fully built plot is compared to nearby green, not to itself.",
            "Landsat 8 and 9 share instrument design and thermal grid, so the "
            "record is radiometrically consistent across the epoch.",
        ],
        "cells": out_cells,
    }

    out_path = Path(args.out)
    out_path.write_text(json.dumps(payload, indent=2))
    print()
    print(f"wrote {out_path}")
    print(f"cells with data: {with_ok}/{len(cells)}")
    print(f"cells with LST : {with_lst}/{len(cells)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())