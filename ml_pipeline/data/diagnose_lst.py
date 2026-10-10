"""Why does built area not show up as hot in the cube's LST?

Measured across all 864 cells: r(built% -> LST) = -0.0765, i.e. more built area
is slightly COOLER. Tree canopy behaves correctly (-0.3161, canopy cools), so
the relationship is not simply inverted across the board -- it is specific to the
built class.

Three candidate causes, and they need different fixes:

  A. The composite destroyed a real signal. If a SINGLE scene separates built
     from vegetated, but our annual mean does not, the bug is in
     `.mean()` over scenes -- e.g. scenes covering different parts of the city
     are being averaged as though they were simultaneous.

  B. The time of day is wrong. Measured overpass 05:26-05:28 UTC =
     10:56-10:58 IST, i.e. mid-morning. At
     mid-morning, dry bare soil and crops can be hotter than shaded rooftops,
     which would genuinely invert built-vs-soil even though built is hotter at
     night. This is a real physical effect, not a bug -- but it makes LST the
     wrong basis for a heat factor at that hour.

  C. Cloud-mask sampling bias. Clouds preferentially obscure certain surfaces.
     The surviving "clear" pixels over a dense city are not a random sample.

This measures A directly (per-scene contrast) and measures the ingredients of B
and C (scene counts per cell, per-cell seasonal spread).
"""
import json
import statistics as st

import ee

from ml_pipeline.data import build_cube as bc

ee.Initialize(project="dishadharti")

EPOCH = 2024
region = ee.Geometry.Rectangle(bc.BBOX, proj="EPSG:4326", geodesic=False)

# Cells: ward 4 (hottest, dense), a known green ward, a known built core.
CELLS = {
    "ward4_hot_dense": "73.8983_18.5431",
    "ward3_green": "73.8443_18.4351",
    "ward2_mixed": "73.8173_18.4891",
    "ward6_high_heat": "73.8083_18.5431",
}
GRID = {f"{round(c['centre'][0], 4)}_{round(c['centre'][1], 4)}": c
        for c in bc.grid_cells()}

cube = json.load(open("ml_pipeline/data/epoch_cube.json"))["cells"]

print("=" * 78)
print("CUBE'S OWN VALUES for these cells")
print("=" * 78)
for name, cid in CELLS.items():
    v = cube.get(cid)
    if not v:
        print(f"  {name:<18} {cid} NOT IN CUBE")
        continue
    print(f"  {name:<18} {cid}  built {v['built_pct']*100:5.1f}%  "
          f"veg {v['vegetation_pct']*100:5.1f}%  trees {v.get('tree_canopy_pct',0)*100:5.1f}%  "
          f"LST {v['lst_mean_c']:.2f}  ref {v['lst_reference_c']:.2f}")

# ---------------------------------------------------------------- per-scene
col = (ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
       .filterDate(f"{EPOCH}-01-01", f"{EPOCH + 1}-01-01")
       .filterBounds(region)
       .map(bc._cloud_mask_l8l9)
       .merge(ee.ImageCollection("LANDSAT/LC09/C02/T1_L2")
              .filterDate(f"{EPOCH}-01-01", f"{EPOCH + 1}-01-01")
              .filterBounds(region)
              .map(bc._cloud_mask_l8l9))
       .select("ST_B10"))

n = col.size().getInfo()
print()
print(f"scenes after cloud masking: {n}")
info = col.aggregate_array("system:time_start").getInfo()
dates = [ee.Date(t).format("YYYY-MM-dd").getInfo() for t in info]
print("dates:", dates)

to_c = lambda im: im.multiply(0.00341802).add(149.0).subtract(273.15)

# Per-scene contrast, computed one scene at a time CLIENT-side. Mapping over the
# collection and calling `im.date()` inside loses `system:time_start`, because
# the arithmetic that converts kelvin to Celsius returns a bare Image with no
# timestamp. Iterating explicitly keeps each scene's date attached.
dw = bc.dynamic_world_tree(EPOCH)
built = dw.select("built_pct")
trees = dw.select("tree_canopy_pct")
veg = dw.select("vegetation_pct")


def cell_geom(cid):
    c = GRID[cid]
    return ee.Geometry.Rectangle([c["lon0"], c["lat0"], c["lon1"], c["lat1"]],
                                 proj="EPSG:4326", geodesic=False)


print()
print("=" * 78)
print("A. IS THERE BUILT-vs-TREE CONTRAST WITHIN A SINGLE SCENE?")
print("=" * 78)
print("For each raw scene, the mean LST over pixels where built>0.5 minus the")
print("mean over pixels where tree_canopy>0.5, inside one cell. A real UHI")
print("signature shows built hotter than canopy.")
print()

scenes = col.toList(col.size()).getInfo()  # already a list, not a dict
pairs = [(nm, cell_geom(cid)) for nm, cid in CELLS.items()]
per_scene = []
for s in scenes:
    im = ee.Image(s["id"]).select("ST_B10")
    date = ee.Date(s["properties"]["system:time_start"]).format("YYYY-MM-dd").getInfo()
    row = {"date": date}
    for nm, g in pairs:
        vb = to_c(im.updateMask(built.gt(0.5))).reduceRegion(
            ee.Reducer.mean(), g, 30, maxPixels=1e9).getInfo().get("ST_B10")
        vt = to_c(im.updateMask(trees.gt(0.5))).reduceRegion(
            ee.Reducer.mean(), g, 30, maxPixels=1e9).getInfo().get("ST_B10")
        row[nm] = (vb, vt, None if vb is None or vt is None else vb - vt)
    per_scene.append(row)
    print(f"  {date}  " + "  ".join(
        (f"{nm[:8]}:{row[nm][2]:+5.2f}" if row[nm][2] is not None
         else f"{nm[:8]}:  n/a") for nm, _ in pairs))

print()
for nm, _ in pairs:
    vals = [r[nm][2] for r in per_scene if r[nm][2] is not None]
    if vals:
        pos = sum(1 for v in vals if v > 0)
        print(f"  {nm:<18} n={len(vals):>2}  mean {st.mean(vals):+5.2f}  "
              f"median {st.median(vals):+5.2f}  "
              f"range {min(vals):+5.2f}..{max(vals):+5.2f}  "
              f"positive {pos}/{len(vals)}")
    else:
        print(f"  {nm:<18} no usable scenes")
print()
print("  WARNING: read the FULL 35-scene mean, not the first few rows. The")
print("  first eight scenes are all winter and all negative; the year as a")
print("  whole is near zero with the sign flipping by season. Reporting the")
print("  first eight as the verdict overstates the negative case.")
print()
print("  POSITIVE mean => built really is hotter than canopy in raw scenes,")
print("  and the annual composite is destroying it.")
print("  ZERO or NEGATIVE => mid-morning LST does not separate the classes and")
print("  no change to the scorer can fix that.")

print()
print("=" * 78)
print("B. TIME OF DAY -- overpass times, and the seasonal spread per cell")
print("=" * 78)
times = sorted({ee.Date(t).format("HH:mm").getInfo() for t in info})
print(f"  overpass times in collection (UTC): {times}")
# 05:26-05:28 UTC is 10:56-10:58 IST. That IS mid-morning locally, but the
# value must be converted rather than assumed -- an earlier version of this
# script asserted "~10:30" in a comment while the collection said otherwise.
ist = sorted({ee.Date(t).advance(ee.Reducer.minutes(330), "minute")
              .format("HH:mm").getInfo() for t in info})
print(f"  overpass times converted to IST (UTC+5:30): {ist}")
print()

print("  per-cell LST spread across the year (from the cube):")
for name, cid in CELLS.items():
    v = cube.get(cid)
    if v:
        print(f"    {name:<18} LST mean {v['lst_mean_c']:.2f}  max {v['lst_max_c']:.2f}  "
              f"range {v['lst_max_c'] - v['lst_mean_c']:+.2f} C")

print()
print("=" * 78)
print("C. CLOUD-MASK SAMPLING BIAS -- clear-pixel count per cell")
print("=" * 78)
const1 = ee.Image.constant(1)
for name, cid in CELLS.items():
    g = cell_geom(cid)
    # PIXEL COUNT, not area. An earlier version summed `constant 1 * 900 m2`
    # and divided a pixel count by it, printing a meaningless "2.4%".
    total_px = const1.reduceRegion(
        ee.Reducer.sum(), g, 30, maxPixels=1e9).getInfo().get("constant", 0)
    clear_px = col.count().reduceRegion(
        ee.Reducer.sum(), g, 30, maxPixels=1e9).getInfo().get("ST_B10", 0)
    n_scenes = n
    print(f"  {name:<18} px/cell {total_px:7.0f}   clear px/scene {clear_px / n_scenes:7.0f}"
          f"   clear fraction {clear_px / n_scenes / total_px if total_px else 0:6.1%}")

print()
print("=" * 78)
print("READING THE RESULT")
print("=" * 78)
print("  If per-scene built-minus-trees contrast is POSITIVE but the cube's")
print("  r(built -> LST) is negative, the composite is averaging the signal")
print("  away (cause A) -- fix by contrasting like against like, or by using")
print("  a night pass / a thermal-anomaly product instead.")
print()
print("  If per-scene contrast is already weak or negative, mid-morning LST is")
print("  simply the wrong observable for this factor (cause B) -- the fix is a")
print("  different dataset, not a different formula.")