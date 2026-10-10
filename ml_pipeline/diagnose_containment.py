#!/usr/bin/env python
"""Diagnose why the Ward 12 test polygon fails the 'within PMC union' check."""
from pathlib import Path

import geopandas as gpd
from shapely.ops import unary_union

REPO = Path(__file__).resolve().parents[1]

wards = gpd.read_file(REPO / "pmc_wards_2025.kml", layer="final_41wardboundary")
site = gpd.read_file(REPO / "WARD12_TEST_SITE.kml")
name_col = "Name" if "Name" in site.columns else "name"

union = unary_union(wards.geometry.values)
w12 = site[site[name_col].str.contains("WARD 12", case=False, na=False)].geometry.iloc[0]

print("Ward 12 test polygon")
print(f"  area          : {w12.area:.10f} deg2")
print(f"  bounds        : {[round(v, 6) for v in w12.bounds]}")
print(f"  valid         : {w12.is_valid}")
print(f"  within union  : {w12.within(union)}")
print(f"  intersects    : {w12.intersects(union)}")
print(f"  covered_by    : {union.contains(w12)}")
print()

# How much of it is actually outside?
outside = w12.difference(union)
print(f"  area outside union : {outside.area:.12f} deg2")
if not outside.is_empty:
    print(f"  outside type       : {outside.geom_type}")
    print(f"  outside bounds     : {[round(v, 6) for v in outside.bounds]}")
    ob = outside.bounds
    # which ward does the stray piece belong to?
    for i, g in enumerate(wards.geometry):
        if g.intersects(outside):
            a = g.intersection(outside).area
            print(f"  falls inside ward qwr={wards.qwr.iloc[i]} by {a:.12f} deg2")
print()

# Same test against each individual ward 12 polygon from the wards file
w12_official = wards[wards.qwr == 12].geometry.iloc[0]
print("Official ward 12 polygon (from pmc_wards_2025.kml)")
print(f"  area          : {w12_official.area:.10f} deg2")
print(f"  bounds        : {[round(v, 6) for v in w12_official.bounds]}")
print(f"  within union  : {w12_official.within(union)}")
print()

print("Comparison between the two Ward 12 polygons")
print(f"  symmetric difference area : {w12.symmetric_difference(w12_official).area:.12f} deg2")
print(f"  identical?                : {w12.equals(w12_official)}")
print(f"  Hausdorff distance (deg)  : {w12.hausdorff_distance(w12_official):.10f}")
print(f"  ~metres                   : {w12.hausdorff_distance(w12_official) * 111320 * 102000:.3f}")
