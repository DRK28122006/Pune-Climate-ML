#!/usr/bin/env python
"""Locate and characterise the genuine ward overlaps."""
from pathlib import Path

import geopandas as gpd

REPO = Path(__file__).resolve().parents[1]
wards = gpd.read_file(REPO / "pmc_wards_2025.kml", layer="final_41wardboundary")
utm = wards.to_crs("EPSG:32643")
geoms, qwr = utm.geometry.tolist(), wards["qwr"].astype(int).tolist()

REAL = 1.0  # m2
found = []
for i in range(len(geoms)):
    for j in range(i + 1, len(geoms)):
        if geoms[i].intersects(geoms[j]):
            inter = geoms[i].intersection(geoms[j])
            if inter.area > REAL:
                c = inter.centroid
                found.append({
                    "a": qwr[i], "b": qwr[j], "m2": inter.area,
                    "lon": round(c.x, 5), "lat": round(c.y, 5),
                    "shape": inter.geom_type,
                    "parts": len(inter.geoms) if inter.geom_type.startswith("Multi") else 1,
                    "a_geom": geoms[i].geom_type,
                })

found.sort(key=lambda d: -d["m2"])
print(f"{'wards':<12}{'m2':>12}{'parts':>7}  {'centroid lon,lat':<24}{'shape':<14}{'ward a geom'}")
print("-" * 88)
for f in found:
    print(f"  {f['a']:>2} ^ {f['b']:<3}  {f['m2']:>12.2f}{f['parts']:>7}  "
          f"{f['lon']:>10.5f},{f['lat']:>9.5f}   {f['shape']:<14}{f['a_geom']}")

# Are the overlapping wards MultiPolygon while others are Polygon, or vice versa?
from collections import Counter
types = Counter(wards.geom_type)
print(f"\nward geometry types : {dict(types)}")
mp = wards[wards.geom_type == "MultiPolygon"]["qwr"].astype(int).tolist()
pl = wards[wards.geom_type == "Polygon"]["qwr"].astype(int).tolist()
print(f"MultiPolygon wards  : {sorted(mp)}")
print(f"Polygon wards       : {sorted(pl)}")

involved = {f["a"] for f in found} | {f["b"] for f in found}
print(f"\nwards in real overlaps: {sorted(involved)}")
print(f"  of which MultiPolygon: {sorted(involved & set(mp))}")
print(f"  of which Polygon     : {sorted(involved & set(pl))}")

# Convert the biggest overlap back to lat/lon for a Google Earth check
big = max(found, key=lambda d: d["m2"])
print(f"\nLARGEST OVERLAP: ward {big['a']} ^ ward {big['b']}")
print(f"  area    : {big['m2']:.1f} m2  (~{big['m2']/10000:.2f} hectares)")
print(f"  centroid: {big['lat']}, {big['lon']}")
print(f"  paste into Google Earth search box to inspect visually")
