"""Why are water and snow zero/tiny under a per-pixel majority vote?

The majority vote takes `dw.select('label').mode()` across the epoch's scenes.
Every image in a collection has a label band covering the whole globe, so at a
given pixel the collection holds N labels -- one per scene. If a pixel is water
in 12 of 39 scenes and 'trees' or 'built' in the rest, mode() picks whichever
class appears most often across scenes, not the one the pixel usually IS.

That biases toward whichever class dominates the annual cycle at that pixel:
crops and built in the dry season, flooded_vegetation during the monsoon. Rare
or brief classes (a river is water year-round but narrow; snow never) lose.

This measures, for real PMC cells, per-class scene-share versus mean
probability, and asks which basis recovers water.

Also tests the fix: a water mask derived from a permanent-water source rather
than from Dynamic World's label vote.
"""
import ee

from ml_pipeline.data import build_cube as bc

ee.Initialize(project="dishadharti")

EPOCH = 2024

CELLS = {
    # Mula-Mutha confluence / central PMC
    "central  ": (73.8443, 18.4351),
    "Pimpri    ": (73.7893, 18.6290),
    "Kothrud   ": (73.5070, 18.5070),  # deliberately outside bbox, control
    "Vimannagar": (73.8983, 18.5670),
    "Hinjewadi ": (73.6700, 18.5910),
    "Sinhagad  ": (73.7633, 18.4351),
}

CLS = {
    0: "water", 1: "trees", 2: "grass", 3: "flooded_vegetation", 4: "crops",
    5: "shrub_and_scrub", 6: "built", 7: "bare", 8: "snow_and_ice",
}
# Dynamic World band names for the probability images
PROB = {
    0: "water", 1: "trees", 2: "grass", 3: "flooded_vegetation", 4: "crops",
    5: "shrub_and_scrub", 6: "built", 7: "bare", 8: "snow_and_ice",
}

base = (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
        .filterDate(f"{EPOCH}-01-01", f"{EPOCH + 1}-01-01")
        .filterBounds(ee.Geometry.Rectangle(bc.BBOX, proj="EPSG:4326",
                                            geodesic=False)))
print(f"Dynamic World images over PMC for {EPOCH}: {base.size().getInfo()}")
print()

print("=" * 88)
print("BASIS COMPARISON at single pixels (mean probability vs mode-of-label)")
print("=" * 88)
print(f"{'cell':<11} {'basis':<6} " + " ".join(f"{v:>6}" for v in CLS.values()))
print("-" * 88)

for label, (lon, lat) in CELLS.items():
    pt = ee.Geometry.Point([lon, lat])

    # mode of label across the epoch's scenes
    lab_img = (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
               .filterDate(f"{EPOCH}-01-01", f"{EPOCH + 1}-01-01")
               .select("label"))
    mode = lab_img.mode()
    mode_vals = mode.reduceRegion(
        ee.Reducer.first(), pt, 30, maxPixels=1e9).getInfo().get("label")

    # mean probability, summed over scenes per class
    prob_means = {}
    for c, name in CLS.items():
        coll = (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
                .filterDate(f"{EPOCH}-01-01", f"{EPOCH + 1}-01-01")
                .filterBounds(pt.buffer(200))
                .select(PROB[c]))
        prob_means[name] = coll.mean().reduceRegion(
            ee.Reducer.first(), pt, 30, maxPixels=1e9).getInfo().get(name)

    inv = {v: k for k, v in CLS.items()}
    mode_cls = CLS.get(int(mode_vals)) if mode_vals is not None else "?"
    print(f"{label:<11} {'prob':<6} " +
          " ".join(f"{prob_means[v]:6.3f}" for v in CLS.values()))
    print(f"{'':<11} {'mode':<6} " + " ".join(
        f"{1.0 if v == mode_cls else 0.0:6.3f}" for v in CLS.values()))
    print()

print("=" * 88)
print("IS THERE A PERMANENT WATER SOURCE IN EARTH ENGINE?")
print("=" * 88)
cands = [
    "JRC/GSW1_4/GlobalSurfaceWater",
    "LANDSAT/LC08/C02/T1_L2",
]
for c in cands:
    try:
        s = ee.ImageCollection(c).filterDate("2024-01-01", "2025-01-01").size().getInfo()
        print(f"  {c}: {s} images in 2024")
    except Exception as e:  # noqa: BLE001
        print(f"  {c}: {str(e)[:120]}")

try:
    gsw = ee.ImageCollection("JRC/GSW1_4/GlobalSurfaceWater").filter(
        ee.Filter.lt("system:time_start", ee.Date("2025-01-01"))).select(
        "occurrence").max().rename("gsw_occurrence")
    print(f"  GSW occurrence bands: {gsw.bandNames().getInfo()}")
    for label, (lon, lat) in CELLS.items():
        pt = ee.Geometry.Point([lon, lat])
        v = gsw.reduceRegion(ee.Reducer.first(), pt, 30, maxPixels=1e9).getInfo()
        print(f"    {label} occurrence = {v.get('gsw_occurrence')}")
except Exception as e:  # noqa: BLE001
    print(f"  GSW failed: {str(e)[:200]}")

print()
print("GSW 'occurrence' is the fraction of 1984-1999 images where the pixel was")
print("water. Persistent rivers and lakes score high; seasonal spill does not.")
print("Using it as the water band would restore the class the majority vote lost,")
print("and it is an independent source rather than the same classifier again.")