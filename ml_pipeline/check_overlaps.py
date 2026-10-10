#!/usr/bin/env python
"""Convert the reported deg2 overlaps into real square metres and judge them.

A deg2 number is meaningless to a reader. Project the actual overlap polygons
into UTM 43N and report m2. Anything under ~1 m2 is coordinate rounding;
anything in the hundreds of m2 is a genuine topology defect in the source KML.
"""
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.ops import unary_union

REPO = Path(__file__).resolve().parents[1]
wards = gpd.read_file(REPO / "pmc_wards_2025.kml", layer="final_41wardboundary")

# Project once; do all area maths in metres, never in degrees.
utm = wards.to_crs("EPSG:32643")
geoms = utm.geometry.tolist()
qwr = wards["qwr"].astype(int).tolist()

rows = []
for i in range(len(geoms)):
    for j in range(i + 1, len(geoms)):
        if not geoms[i].intersects(geoms[j]):
            continue
        inter = geoms[i].intersection(geoms[j]).area
        if inter > 0:
            rows.append({"a": qwr[i], "b": qwr[j], "overlap_m2": inter})

df = pd.DataFrame(rows).sort_values("overlap_m2", ascending=False)
total_m2 = df["overlap_m2"].sum()

print(f"{'pair':<14}{'overlap m2':>14}{'verdict':>22}")
print("-" * 52)
for _, r in df.iterrows():
    m2 = r["overlap_m2"]
    if m2 < 1:
        v = "rounding noise"
    elif m2 < 100:
        v = "small sliver"
    else:
        v = "REAL DEFECT"
    print(f"  ward {r['a']:>2} ^ {r['b']:<3}   {m2:>14.6f}   {v:>18}")

print("-" * 52)
print(f"pairs touching      : {len(df)}")
print(f"total overlap area  : {total_m2:.4f} m2  ({total_m2/1e6:.6f} km2)")
print(f"as share of PMC     : {total_m2 / (unary_union(geoms).area) * 100:.9f} %")

union_m2 = unary_union(geoms).area
print(f"\nPMC union area     : {union_m2/1e6:.2f} km2")
print(f"If overlaps removed : {(unary_union(geoms).buffer(0).area)/1e6:.2f} km2")

worst = df["overlap_m2"].max() if len(df) else 0
print(f"\nlargest single pair : {worst:.6f} m2")
print(f"verdict             : "
      + ("benign — sub-square-metre boundary rounding" if worst < 1
         else "genuine overlap present in the source KML" if worst < 100
         else "significant overlap — wards are not a clean partition"))
