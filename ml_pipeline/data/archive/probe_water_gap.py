"""Resolve: EE says water=1.0 at a hill pixel, the cube says water_pct=0.

`isolate_fixes.py` reported water max 0.00% over 864 cells while `probe_water.py`
reported mode-of-label = water at 73.7633_18.4351 (a cell inside the grid). Both
cannot be true. This prints the cube's stored values for specific cells next to
live Earth Engine reductions built by the SAME function the cube build uses, so
the disagreement is localised to a band-name mismatch, a filter difference, or a
genuine zero.
"""
import json

import ee

from ml_pipeline.data import build_cube as bc

ee.Initialize(project="dishadharti")

NEW = json.load(open("ml_pipeline/data/epoch_cube.json"))["cells"]

TARGETS = ["73.7633_18.4351", "73.8443_18.4351", "73.8983_18.5431"]
GRID = {f"{round(c['centre'][0], 4)}_{round(c['centre'][1], 4)}": c
        for c in bc.grid_cells()}

BAND_LIST = [
    "built_pct", "bare_pct", "tree_canopy_pct", "water_pct",
    "vegetation_pct", "grass", "crops", "shrub_and_scrub",
    "flooded_vegetation", "snow_and_ice", "labelled_fraction",
]

dw = bc.dynamic_world_tree(2024)
print("bands on the image returned by dynamic_world_tree():")
print(" ", dw.bandNames().getInfo())
print()

sel = dw.select(BAND_LIST)
print("bands after .select(BAND_LIST)  [an empty list here is the bug]:")
print(" ", sel.bandNames().getInfo())
print()

fc = ee.FeatureCollection([
    ee.Feature(
        ee.Geometry.Rectangle([c["lon0"], c["lat0"], c["lon1"], c["lat1"]],
                              proj="EPSG:4326", geodesic=False),
        {"id": cid},
    )
    for cid, c in GRID.items()
])

rows = sel.addBands(bc.terrain().rename("elevation_m")).reduceRegions(
    collection=fc.filter(ee.Filter.inList("id", TARGETS)),
    reducer=ee.Reducer.mean(), scale=30, maxPixelsPerRegion=1e9,
    tileScale=1,
).getInfo()

print("=" * 92)
print("CUBE vs LIVE EARTH ENGINE, same cells, same bands")
print("=" * 92)
for feat in rows["features"]:
    cid = feat["id"]
    live = feat["properties"]
    stored = NEW.get(cid, {})
    print(f"\n  {cid}")
    print(f"    {'band':<22} {'cube':>12} {'live EE':>12}   match")
    for b in BAND_LIST:
        s = stored.get(b)
        l = live.get(b)
        sm = f"{s:12.6f}" if isinstance(s, (int, float)) else f"{'ABSENT':>12}"
        lm = f"{l:12.6f}" if isinstance(l, (int, float)) else f"{'ABSENT':>12}"
        ok = ""
        if isinstance(s, (int, float)) and isinstance(l, (int, float)):
            ok = "ok" if abs(s - l) < 1e-6 else f"DIFF {s - l:+.6f}"
        print(f"    {b:<22} {sm} {lm}   {ok}")

print()
print("If a band is ABSENT from `cube` but present live, the store step drops it.")
print("If live is ABSENT too, the select() is failing and the band is 0 by default.")