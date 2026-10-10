#!/usr/bin/env python
"""Geospatial verification of the PMC ward boundary + Ward 12 test site.

Run with the project virtualenv:
    .venv/bin/python ml_pipeline/verify_boundary.py
"""
import math
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.ops import unary_union

REPO = Path(__file__).resolve().parents[1]
WARDS = REPO / "pmc_wards_2025.kml"
TESTSITE = REPO / "WARD12_TEST_SITE.kml"
CENSUS = REPO / "ptc_part1.csv"

PMC_OFFICIAL_KM2 = 485.0
WARDS_OFFICIAL = 41


def rule(title: str) -> None:
    print()
    print("=" * 74)
    print(title)
    print("=" * 74)


def main() -> int:
    failures: list[str] = []
    warnings: list[str] = []

    # ------------------------------------------------------------------ 1
    rule("[1] WARDS FILE — STRUCTURE")
    wards = gpd.read_file(WARDS, layer="final_41wardboundary")
    print(f"    file             : {WARDS.name}")
    print(f"    features         : {len(wards)}  (expected {WARDS_OFFICIAL})")
    print(f"    columns          : {list(wards.columns)}")
    print(f"    geometry types   : {sorted(wards.geom_type.unique())}")
    print(f"    CRS              : {wards.crs}")
    print(f"    all geometries valid : {wards.geometry.is_valid.all()}")
    print(f"    null geometries      : {int(wards.geometry.isna().sum())}")

    if len(wards) != WARDS_OFFICIAL:
        failures.append(f"expected {WARDS_OFFICIAL} wards, found {len(wards)}")
    if not wards.geometry.is_valid.all():
        failures.append("some ward geometries are invalid (self-intersecting)")
    if not wards.crs.is_geographic:
        failures.append("CRS is not geographic — lat/lon maths would be wrong")
    if wards.geometry.isna().any():
        failures.append("null geometries present")

    # ------------------------------------------------------------------ 2
    rule("[2] BOUNDS")
    b = wards.total_bounds
    print(f"    west  {b[0]:.6f}   east {b[2]:.6f}")
    print(f"    south {b[1]:.6f}   north {b[3]:.6f}")
    km_ns = (b[3] - b[1]) * 110.574
    km_ew = (b[2] - b[0]) * 111.320 * math.cos(math.radians((b[1] + b[3]) / 2))
    print(f"    extent           : {km_ew:.1f} km E-W x {km_ns:.1f} km N-S")
    if not (18.3 < b[1] and b[3] < 18.7 and 73.7 < b[0] and b[2] < 74.1):
        failures.append("bounds fall outside expected Pune box")

    # ------------------------------------------------------------------ 3
    # KML coordinates are rounded when written, so wards that share a boundary
    # overlap by a sub-millimetre sliver rather than exactly 0. Test against a
    # tolerance instead of an exact predicate, or every pair looks broken.
    TOL_DEG2 = 1e-9  # ~1e-9 deg2 ~ 0.1 mm^2 on the ground
    rule("[3] TOPOLOGY — OVERLAPS / GAPS")
    overlaps = []
    geoms = wards.geometry.tolist()
    qwr = wards["qwr"].tolist()
    for i in range(len(geoms)):
        for j in range(i + 1, len(geoms)):
            if geoms[i].intersects(geoms[j]):
                a = geoms[i].intersection(geoms[j]).area
                if a > TOL_DEG2:
                    overlaps.append((qwr[i], qwr[j], a))
    benign = 0
    for i in range(len(geoms)):
        for j in range(i + 1, len(geoms)):
            if geoms[i].intersects(geoms[j]):
                a = geoms[i].intersection(geoms[j]).area
                if 0 < a <= TOL_DEG2:
                    benign += 1
    print(f"    real overlaps (> {TOL_DEG2:g} deg2) : {len(overlaps)}")
    print(f"    boundary-touch slivers ignored      : {benign}")
    for a, b_, ar in sorted(overlaps, key=lambda x: -x[2])[:8]:
        print(f"       ward {a:>3} ^ ward {b_:<3} {ar:.10f} deg2")
    if overlaps:
        failures.append(f"{len(overlaps)} ward pairs overlap beyond rounding tolerance")
    union = unary_union(geoms)
    print(f"    union area          : {union.area:.8f} deg2")

    # ------------------------------------------------------------------ 4
    rule("[4] AREA — PROJECTED TO UTM 43N")
    utm = wards.to_crs("EPSG:32643")
    sum_km2 = utm.geometry.area.sum() / 1e6
    union_km2 = unary_union(utm.geometry.values).area / 1e6
    print(f"    sum of 41 wards : {sum_km2:8.1f} km2")
    print(f"    union (dedup)   : {union_km2:8.1f} km2")
    print(f"    PMC official    : {PMC_OFFICIAL_KM2:8.1f} km2  (2021, post-merger)")
    dev = abs(union_km2 - PMC_OFFICIAL_KM2) / PMC_OFFICIAL_KM2 * 100
    print(f"    deviation       : {dev:8.1f} %")
    if dev > 15:
        warnings.append(f"area deviates {dev:.0f}% from the official 485 km2 — "
                        f"check whether this is the 2025 delimitation extent")
    if sum_km2 - union_km2 > 1:
        warnings.append("sum exceeds union — wards double-count area")

    # ------------------------------------------------------------------ 5
    rule("[5] WARD IDENTIFIERS")
    ids = sorted(int(v) for v in wards["qwr"])
    print(f"    qwr min/max : {ids[0]} .. {ids[-1]}")
    print(f"    count       : {len(ids)}")
    expected = list(range(1, WARDS_OFFICIAL + 1))
    missing = sorted(set(expected) - set(ids))
    dupes = [v for v in set(ids) if ids.count(v) > 1]
    print(f"    missing     : {missing if missing else 'none'}")
    print(f"    duplicates  : {dupes if dupes else 'none'}")
    if missing:
        failures.append(f"missing ward ids {missing}")
    if dupes:
        failures.append(f"duplicate ward ids {dupes}")

    # ------------------------------------------------------------------ 6
    rule("[6] TEST SITE KML")
    site = gpd.read_file(TESTSITE)
    print(f"    features : {len(site)}")
    print(f"    columns  : {list(site.columns)}")
    # OGR normalises the KML <name> element to 'Name'; be tolerant of either.
    name_col = "Name" if "Name" in site.columns else "name"
    for nm in site[name_col].tolist():
        print(f"      - {nm}")
    w12 = site[site[name_col].str.contains("WARD 12", case=False, na=False)]
    if w12.empty:
        failures.append("WARD 12 polygon not found in test-site KML")
    else:
        g = w12.geometry.iloc[0]
        u12 = gpd.GeoSeries([g], crs=wards.crs).to_crs("EPSG:32643").iloc[0]
        print(f"    Ward 12 area     : {u12.area/1e6:.2f} km2   (Earth measured 5.46)")
        print(f"    Ward 12 length   : {u12.length/1000:.2f} km   (Earth measured 12.8)")
        print(f"    Ward 12 bounds   : {[round(v, 5) for v in g.bounds]}")
        # Same rounding-tolerance issue as the topology check: a shared edge
        # with the neighbouring ward leaves slivers that break a strict
        # `within()`. Buffer by a hair before testing containment.
        TOL_M = 1.0  # 1 metre
        tol_poly = union.buffer(TOL_M / 111320 / 102.0)
        inside_pmc = g.within(tol_poly)
        outside = g.difference(union).area
        print(f"    inside PMC union : {inside_pmc}  (tol {TOL_M} m)")
        print(f"    area outside     : {outside:.14f} deg2  "
              f"(~{outside * 111320 * 102.0 * 1e4:.4f} cm2 — rounding noise)")
        if not inside_pmc:
            failures.append("Ward 12 polygon does not fall inside the PMC ward union")

        # Cross-check: the test-site polygon must match the official ward 12
        # polygon. Compare areas rather than exact equality, since the test file
        # was regenerated independently and coordinates are rounded.
        official12 = wards[wards.qwr == 12].geometry.iloc[0]
        a_test = gpd.GeoSeries([g], crs=wards.crs).to_crs("EPSG:32643").iloc[0].area
        a_off = gpd.GeoSeries([official12], crs=wards.crs).to_crs("EPSG:32643").iloc[0].area
        drift = abs(a_test - a_off) / a_off * 100
        print(f"    vs official ward 12: {a_off/1e6:.2f} km2  (drift {drift:.3f}%)")
        if drift > 1.0:
            failures.append(f"test-site Ward 12 differs from official by {drift:.1f}%")

    # ------------------------------------------------------------------ 7
    rule("[7] TREE CENSUS SAMPLE")
    if CENSUS.exists():
        use = ["girth_cm", "height_m", "canopy_dia_m", "northing", "easting",
               "condition", "ward", "is_rare", "botanical_name"]
        df = pd.read_csv(CENSUS, usecols=use, low_memory=False)
        print(f"    rows            : {len(df):,}")
        print(f"    columns         : {list(df.columns)}")
        lat, lon = df["northing"], df["easting"]
        inside_bounds = (lat.between(18.3, 18.7) & lon.between(73.7, 74.1)).sum()
        print(f"    coords in PMC box: {inside_bounds:,} ({100*inside_bounds/len(df):.1f}%)")
        swapped = ((lon.between(18.3, 18.7) & lat.between(73.7, 74.1))).sum()
        print(f"    swapped axis    : {swapped:,}  -> {'northing/easting ARE swapped' if swapped > inside_bounds else 'northing=lat, easting=lon (confirmed)'}")
        if swapped > inside_bounds:
            failures.append("northing/easting columns are lat/lon in unexpected order")
        print(f"    girth  median   : {df['girth_cm'].median():.1f} cm")
        print(f"    canopy median   : {df['canopy_dia_m'].median():.2f} m")
        print(f"    mature (>=60cm) : {(df['girth_cm'] >= 60).sum():,}")
        print(f"    rare trees      : {(df['is_rare'].astype(str).str.upper() == 'TRUE').sum():,}")
        print(f"    healthy share   : {100*(df['condition'] == 'Healthy').mean():.1f}%")
        print(f"    distinct species: {df['botanical_name'].nunique():,}")
    else:
        warnings.append("ptc_part1.csv not present — census checks skipped")

    # ------------------------------------------------------------------ 8
    rule("VERDICT")
    if failures:
        print("    FAILED")
        for f in failures:
            print(f"      X {f}")
    else:
        print("    PASS — no blocking errors")
    if warnings:
        print("\n    warnings:")
        for w in warnings:
            print(f"      ! {w}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
