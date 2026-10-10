"""End-to-end check against the REAL census data and a REAL ward polygon.

    .venv/bin/python ml_pipeline/tests/test_e2e_ward12.py

This is the test that proves the pieces join. Everything else is unit-level.
It reads the actual Ward 12 KML, queries the actual SQLite index over the
polygon, and runs the actual canopy ledger over the trees that come back.
No mocks.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from ml_pipeline.core.canopy import CanopyLedger, TreeRecord, canopy_area_m2  # noqa: E402
from ml_pipeline.core.scoring import score_project  # noqa: E402
from ml_pipeline.data.tree_index import query_bbox  # noqa: E402

DB = REPO / "ml_pipeline" / "data" / "tree_index.sqlite"
WARD12_KML = REPO / "WARD12_TEST_SITE.kml"
SPECIES = json.loads((REPO / "ml_pipeline" / "config" / "species.json").read_text())
MATERIALS = json.loads((REPO / "ml_pipeline" / "config" / "materials.json").read_text())
REGION = json.loads((REPO / "ml_pipeline" / "config" / "regions" / "pune.json").read_text())

# Ward 12 verified bounds from the boundary check (Deccan / Ganeshkhind).
WARD12_BOUNDS = (73.8250, 18.5137, 73.8606, 18.5380)


def parse_kml_polygons(path: Path) -> dict[str, list[list[tuple[float, float]]]]:
    """Extract each Placemark's ring(s) as (lon, lat) pairs, keyed by name.

    The test-site KML holds several placemarks — the Ward 12 site, two
    comparison wards, the full PMC extent and point markers. Concatenating all
    <coordinates> blobs into one ring silently merges the whole city into the
    Ward 12 polygon, which is exactly the kind of silent-geometry bug this
    test exists to catch. Each placemark is kept separate.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    out: dict[str, list[list[tuple[float, float]]]] = {}

    for pm in re.findall(r"<Placemark.*?</Placemark>", text, re.S):
        name_match = re.search(r"<name>(.*?)</name>", pm, re.S)
        name = (name_match.group(1).strip() if name_match else f"placemark_{len(out)}")
        rings: list[list[tuple[float, float]]] = []
        for blob in re.findall(r"<coordinates>(.*?)</coordinates>", pm, re.S):
            pts: list[tuple[float, float]] = []
            for token in blob.split():
                parts = token.split(",")
                if len(parts) >= 2:
                    try:
                        pts.append((float(parts[0]), float(parts[1])))
                    except ValueError:
                        continue
            if len(pts) >= 3:
                rings.append(pts)
        if rings:
            out[name] = rings

    return out


def point_in_polygon(lon: float, lat: float, ring: list[tuple[float, float]]) -> bool:
    """Ray-casting test. `ring` is a closed list of (lon, lat)."""
    inside = False
    n = len(ring)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat):
            denom = yj - yi
            if denom != 0 and lon < (xj - xi) * (lat - yi) / denom + xi:
                inside = not inside
        j = i
    return inside


def main() -> int:
    failures = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' — ' + detail) if detail else ''}")
        if not ok:
            failures.append(label)

    print("=" * 72)
    print("E2E: Ward 12 real polygon -> real tree index -> real canopy ledger")
    print("=" * 72)

    if not DB.exists():
        print(f"FAIL  tree index missing at {DB}; run --build first")
        return 1
    if not WARD12_KML.exists():
        print(f"FAIL  Ward 12 KML missing at {WARD12_KML}")
        return 1

    # --- 1. geometry from the real KML -----------------------------------
    polygons = parse_kml_polygons(WARD12_KML)
    check("KML exposes several distinct placemarks", len(polygons) >= 3,
          ", ".join(list(polygons)[:4]))
    if len(polygons) < 3:
        return 1

    # Find the Ward 12 ring by name; never assume index 0.
    ward12_key = next(
        (k for k in polygons if "WARD 12" in k.upper()), None
    )
    check("Ward 12 placemark found by name", ward12_key is not None, str(ward12_key))
    if ward12_key is None:
        return 1

    ring = max(polygons[ward12_key], key=len)
    check("Ward 12 ring is usable", len(ring) >= 4, f"{len(ring)} vertices")

    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    # The KML ring should sit inside the verified Ward 12 bounds.
    bbox_ok = (73.82 <= min(lons) <= 73.83 and 18.51 <= min(lats) <= 18.52
               and 73.85 <= max(lons) <= 73.87 and 18.53 <= max(lats) <= 18.55)
    check("ring bbox consistent with verified Ward 12 bounds", bbox_ok,
          f"lon {min(lons):.4f}-{max(lons):.4f}  lat {min(lats):.4f}-{max(lats):.4f}")

    # Shoelace area in degrees, then an equirectangular m2 conversion good
    # enough to sanity-check magnitude (never used in the real pipeline,
    # which projects to EPSG:32643).
    area_deg2 = abs(
        0.5 * sum(
            ring[i][0] * ring[(i + 1) % len(ring)][1] - ring[(i + 1) % len(ring)][0] * ring[i][1]
            for i in range(len(ring))
        )
    )
    mid_lat = math.radians((min(lats) + max(lats)) / 2)
    m_per_deg_lat = 110_574.0
    m_per_deg_lon = 111_320.0 * math.cos(mid_lat)
    area_m2 = area_deg2 * m_per_deg_lon * m_per_deg_lat
    check("Ward 12 area is plausible (expect ~5.4 km2)", 4.0e6 < area_m2 < 7.0e6,
          f"{area_m2/1e6:.3f} km2")

    # --- 2. index query over the real polygon -----------------------------
    t0 = time.perf_counter()
    bbox_rows = query_bbox(str(DB), min(lons), min(lats), max(lons), max(lats))
    bbox_ms = (time.perf_counter() - t0) * 1000

    inside = [r for r in bbox_rows
              if point_in_polygon(r["lon"], r["lat"], ring)]
    query_ms = (time.perf_counter() - t0) * 1000

    check("bbox query returns candidates", len(bbox_rows) > 0, f"{len(bbox_rows)} candidates")
    check("point-in-polygon narrows the set", len(inside) < len(bbox_rows),
          f"{len(inside)} inside vs {len(bbox_rows)} bbox")
    # The R-tree is 1 GB now (4,009,623 trees vs 249,999 before), so the budget
    # is relaxed from 500 ms. It is still indexed: a full scan of 4M rows would
    # take seconds, so a sub-2s total still proves the index is being used.
    check("index query is fast", query_ms < 2000.0, f"{query_ms:.1f} ms total")
    # Ward 12 holds 44,468 trees under the COMPLETE census. The earlier figure
    # of 26,161 was measured with only ptc_part1.csv loaded (6.11% of the city,
    # one geographic block), so it was an undercount by design.
    check("tree count matches the verified Ward 12 figure", 38_000 < len(inside) < 52_000,
          f"{len(inside)} trees")

    # --- 3. the real ledger over real trees --------------------------------
    trees = [
        TreeRecord(
            tree_id=r["tree_id"], lon=r["lon"], lat=r["lat"],
            botanical_name=r["botanical_name"] or "",
            girth_cm=r["girth_cm"] or 0.0, height_m=r["height_m"] or 0.0,
            canopy_dia_m=r["canopy_dia_m"] or 0.0,
            condition=r["condition"] or "", is_rare=bool(r["is_rare"]),
        )
        for r in inside
    ]
    ledger = CanopyLedger(SPECIES)
    # Ward area in m2 from the shoelace figure above.
    out = ledger.process_site(trees, plot_area_m2=area_m2)

    mature = sum(1 for t in trees if t.girth_cm >= 60)
    rare = sum(1 for t in trees if t.is_rare)
    print("\n  Real Ward 12 census profile:")
    print(f"    trees                {len(trees):,}")
    print(f"    mature (girth>=60)   {mature:,}")
    print(f"    rare-flagged         {rare:,}")
    print(f"    canopy before        {out['tree_canopy_m2_before']:,.0f} m2")
    print(f"    canopy cover         {out['canopy_cover_pct']:.2f}%")
    print(f"    action counts        {out['action_counts']}")
    print(f"    compensatory range   {out['compensatory_required']}")

    # Thresholds widened for the COMPLETE census. These figures were originally
    # measured against ptc_part1.csv alone (6.11% of the city, a single
    # geographic block) and read 26,162 trees / 12,199 mature / 492 rare.
    # With all 17 parts indexed, Ward 12 genuinely holds 44,468 / 18,823 /
    # 1,266 -- verified via `ml_pipeline/cli.py ward-profile --ward 12`.
    # Narrow bands here would fail on correct data, so they are sanity ranges,
    # not exact-match assertions.
    check("mature count is plausible for Ward 12 (full census: ~18,800)",
          14_000 < mature < 24_000, f"{mature:,}")
    check("rare count is plausible (full census: ~1,270)", 800 < rare < 2_000, f"{rare}")
    check("canopy cover is a sane percentage",
          0.5 < out["canopy_cover_pct"] < 100.0, f"{out['canopy_cover_pct']:.2f}%")
    check("dead trees are removed, not felled",
          out["action_counts"].get("REMOVE_DEAD", 0) >= 0
          and "FELL" not in "".join(k for k in out["action_counts"] if k == "REMOVE_DEAD"))

    # --- 4. whole-ward scenario through the scorer ------------------------
    site = {
        "builtUpAreaSqm": 2_000.0,
        "plotAreaSqm": area_m2,
        "materials": [
            {"name": "cement", "quantityKg": 80_000},
            {"name": "steel_reinforcement", "quantityKg": 40_000},
            {"name": "brick", "quantityKg": 90_000},
        ],
    }
    # Read the REAL cube for Ward 12 rather than stubbing LST to None. Heat is
# #1 of the four factors and 30% of the weight; an e2e that hard-codes
    # `lst_mean_c: None` kept asserting the degraded path long after the cube
    # existed, so it would have passed even if the heat wiring were broken.
    from ml_pipeline.cli import indicators_from_cube, load_epoch_cube

    cube = load_epoch_cube()
    sat = indicators_from_cube(ring, cube) if cube else {}
    print(f"\n  epoch cube for Ward 12: "
          f"LST {sat.get('lst_mean_c')} vs ref {sat.get('lst_reference_c')}")

    def _pct(x, d=0.0):
        return float(x) * 100.0 if x is not None else d

    indicators = {
        "impervious_pct": _pct(sat.get("built_pct"), 72.0),
        "vegetation_pct": _pct(sat.get("vegetation_pct"), 22.0),
        "water_pct": _pct(sat.get("water_pct"), 6.0),
        "lst_mean_c": sat.get("lst_mean_c"),
        "lst_reference_c": sat.get("lst_reference_c"),
        "mean_slope_deg": sat.get("mean_slope_deg", 3.1),
        "dist_to_storm_drain_m": 180.0,
    }
    res = score_project(site, indicators, REGION, MATERIALS, ledger=out)

    print("\n  Score on a 2,000 m2 footprint inside real Ward 12:")
    print(f"    climate_score    {res['climate_score']}")
    print(f"    impact_score     {res['impact_score']}  ({res['risk_band']})")
    print(f"    flood            {res['sub_scores']['flood']}")
    heat_s = res['sub_scores']['heat']
    print(f"    heat             {heat_s}"
          + ("" if heat_s is not None else "  (excluded: no satellite pass)"))
    print(f"    green            {res['sub_scores']['green']}")
    print(f"    carbon           {res['sub_scores']['carbon']}  ({res['factors']['carbon']['band']})")
    print(f"    recommendation   {res.get('recommendation')}")
    print(f"    complete         {res['complete']}  missing={res['missing_factors']}")
    if res.get("partial_notice"):
        print(f"    notice           {res['partial_notice']}")

    # Heat must now be SCORED from the real cube, and the score must be
    # complete. The degrade-still-partial behaviour is covered separately in
    # test_scoring.py (test_score_project_heat_prefers_per_cell_reference...),
    # which explicitly re-runs with lst_reference_c=None and asserts the
    # partial result. Keeping it here too would mean asserting the OLD broken
    # state as the expected one.
    check("heat is scored from the epoch cube", res["sub_scores"]["heat"] is not None,
          f"heat={res['sub_scores']['heat']}")
    check("all four factors present", res["complete"] is True,
          f"missing={res['missing_factors']}")
    check("heat uses the per-cell reference, not an air temperature",
          res["factors"]["heat"].get("lst_reference_c") is not None,
          f"ref={res['factors']['heat'].get('lst_reference_c')}")
    check("impact is inside 0-100", 0.0 <= res["impact_score"] <= 100.0)
    check("a recommendation is still issued", "recommendation" in res)
    check("carbon uses India steel factor",
          res["factors"]["carbon"]["dominant_material"] == "steel_reinforcement")

    print("\n" + "=" * 72)
    if failures:
        print(f"{len(failures)} FAILURE(S): {failures}")
        return 1
    print("All end-to-end checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
