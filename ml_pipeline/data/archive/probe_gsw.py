"""Ground truth for the water class, from an independent source.

The cube reports water_pct = 0.000000 in all 864 cells. An earlier point probe
of `label.mode()` returned water at a hill pixel, and the built city centre
returned built=1. The cube and that probe disagree, and neither is obviously
wrong, so this settles it against data that shares no classifier with Dynamic
World:

  1. JRC Global Surface Water (GSW) -- an independent 30 m product. `occurrence`
     is the fraction of 1984-1999 valid observations in which the pixel was
     water, so permanent rivers and lakes score high and seasonal spill does not.
  2. PMC's own stormwater / nalla polygon layer, already downloaded as GeoJSON.
     That is the layer the flood factor's drainage proximity uses, so water
     derived from it is consistent with the rest of the model.

Prints the cube's water_pct next to GSW occurrence and to the distance-to-water
the pipeline already computes, for real PMC locations including the Mula-Mutha
confluence and a known lake.
"""
import json
import math

import ee

from ml_pipeline.data import build_cube as bc

ee.Initialize(project="dishadharti")

NEW = json.load(open("ml_pipeline/data/epoch_cube.json"))["cells"]

print("JRC/GSW1_4/GlobalSurfaceWater is an Image (not a collection). Checking bands:")
gsw = ee.Image("JRC/GSW1_4/GlobalSurfaceWater")
print(" ", gsw.bandNames().getInfo())
print()

occ = gsw.select("occurrence")

POINTS = [
    ("Mula-Mutha confluence", 73.8570, 18.4900),
    ("Pune station (Dashashwamedh)", 73.8460, 18.5300),
    ("Pimpri (Mula-Mutha)", 73.7893, 18.6290),
    ("Kothrud lake (Pashan)", 73.4740, 18.5070),
    ("Sinhagad hill", 73.7633, 18.4351),
    ("Vimannagar", 73.8983, 18.5670),
    ("Hinjewadi IT park", 73.6700, 18.5910),
    ("Bhugaon", 73.7400, 18.5300),
]

print("=" * 88)
print("GSW occurrence (0-100, % of 1984-1999 observations that were water)")
print("=" * 88)
print(f"  {'place':<28} {'lon':>9} {'lat':>9} {'GSW occ':>9}")
res = {}
for name, lon, lat in POINTS:
    v = occ.reduceRegion(ee.Reducer.first(), ee.Geometry.Point([lon, lat]),
                         30, maxPixels=1e9).getInfo().get("occurrence")
    res[name] = v
    print(f"  {name:<28} {lon:9.4f} {lat:9.4f} {str(v):>9}")

print()
print("=" * 88)
print("GSW occurrence over the whole cube extent, reduced per cell")
print("=" * 88)
GRID = {f"{round(c['centre'][0], 4)}_{round(c['centre'][1], 4)}": c
        for c in bc.grid_cells()}
fc = ee.FeatureCollection([
    ee.Feature(ee.Geometry.Rectangle([c["lon0"], c["lat0"], c["lon1"], c["lat1"]],
                                     proj="EPSG:4326", geodesic=False),
               {"id": cid})
    for cid, c in GRID.items()
])
rows = occ.rename("gsw_occurrence").reduceRegions(
    collection=fc, reducer=ee.Reducer.max(), scale=30,
    maxPixelsPerRegion=1e9, tileScale=1).getInfo()
vals = {}
for f in rows["features"]:
    v = f["properties"].get("gsw_occurrence")
    if v is not None:
        vals[f["id"]] = v
pos = sorted(vals.values(), reverse=True)
print(f"  cells with GSW occurrence present : {len(vals)}/{len(fc.size().getInfo())}")
if pos:
    print(f"  occurrence max {pos[0]}  p99 {pos[len(pos)//100]}  "
          f"median {pos[len(pos)//2]}  min {pos[-1]}")
    print(f"  cells with occurrence > 25 (real water) : {sum(1 for v in pos if v > 25)}")
    print(f"  cells with occurrence > 50 (permanent)  : {sum(1 for v in pos if v > 50)}")
print()
top = sorted(vals.items(), key=lambda kv: -kv[1])[:10]
print("  top 10 cells by GSW occurrence:")
for cid, v in top:
    print(f"    {cid}  occ {v:5.1f}   cube water_pct {NEW[cid].get('water_pct', 0):.6f}")
print()
print("If GSW finds substantial water in cells where the cube says 0.0%, the")
print("Dynamic World majority vote is losing the class and GSW should supply it.")
print("If GSW also finds nothing, then at 30 m these rivers are genuinely")
print("sub-pixel and the pipeline's drainage-distance layer is the right input.")