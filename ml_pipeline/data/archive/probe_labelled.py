"""Diagnose why adding `labelled_fraction` changed the stored class bands.

Build 1 (no labelled_fraction): raw 9-class sum median 1.0000, 738/864 pass.
Build 2 (labelled_fraction added via per_class.reduce(sum)): median 0.2155.

The partition bands themselves were not touched, so the change must come from
how `labelled` was constructed. This probes the image server directly and prints
the raw reduceRegions output for a few cells.
"""
import json

import ee

from ml_pipeline.data import build_cube as bc

ee.Initialize(project="dishadharti")

EPOCH = 2024

cells = bc.grid_cells()
print(f"probe grid: {len(cells)} cells")
# Built exactly the way reduce_extent() builds it -- same rectangles, same id
# format, so the probe measures the same regions the cube does.
fc = ee.FeatureCollection([
    ee.Feature(
        ee.Geometry.Rectangle(
            [c["lon0"], c["lat0"], c["lon1"], c["lat1"]],
            proj="EPSG:4326", geodesic=False,
        ),
        {"id": f"{round(c['centre'][0], 4)}_{round(c['centre'][1], 4)}"},
    )
    for c in cells
])

dw = bc.dynamic_world_tree(EPOCH)
terr = bc.terrain()

BAND_LIST = [
    "built_pct", "bare_pct", "tree_canopy_pct", "water_pct",
    "vegetation_pct", "grass", "crops", "shrub_and_scrub",
    "flooded_vegetation", "labelled_fraction",
]

print()
print("bandNames of the image actually being reduced:")
print(" ", dw.select(BAND_LIST).bandNames().getInfo())

sample = fc.filter(ee.Filter.inList(
    "id", ["73.7363_18.3901", "73.8443_18.4351", "73.7633_18.4351"]))

sel = dw.select(BAND_LIST).addBands(terr.rename("elevation_m"))
red = sel.reduceRegions(
    collection=sample, reducer=ee.Reducer.mean(), scale=30, maxPixelsPerRegion=1e9
).getInfo()

CLS = ["water", "trees", "grass", "flooded_vegetation", "crops",
       "shrub_and_scrub", "built", "bare", "snow_and_ice"]

print()
print("raw reduceRegions rows (this is what lands in the cube):")
for feat in red["features"]:
    p = feat["properties"]
    row = {k: p.get(k) for k in BAND_LIST}
    total = sum(v for k, v in row.items()
               if k != "labelled_fraction" and v is not None)
    print(f"  {feat['id']}")
    print(f"    stored bands: {json.dumps(row)}")
    print(f"    9-class total(excl derived+labelled) = {total:.4f}"
          f"   labelled_fraction = {row.get('labelled_fraction')}")

print()
print("--- isolate: is labelled_fraction really the per-pixel class sum? ---")
names = list(bc.DW_CLASSES.values())
print("DW_CLASSES:", bc.DW_CLASSES)
one = sample.first().geometry()

percls = dw.select(names)
print("per_class bandNames:", percls.bandNames().getInfo())
s = percls.reduceRegion(
    reducer=ee.Reducer.sum(), geometry=one, scale=30, maxPixels=1e9).getInfo()
print("per_class.reduce(sum) at that cell:", s)

m = dw.select("labelled_fraction").reduceRegion(
    reducer=ee.Reducer.mean(), geometry=one, scale=30, maxPixels=1e9).getInfo()
print("labelled_fraction mean there      :", m)

onepx = ee.Geometry.Point([73.8443, 18.4351])
s1 = percls.reduceRegion(
    reducer=ee.Reducer.sum(), geometry=onepx, scale=30, maxPixels=1e9).getInfo()
m1 = dw.select("labelled_fraction").reduceRegion(
    reducer=ee.Reducer.mean(), geometry=onepx, scale=30, maxPixels=1e9).getInfo()
print()
print("single pixel:")
print("  per_class sum :", s1)
print("  labelled_frac :", m1)