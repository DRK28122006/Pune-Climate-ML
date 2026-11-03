"""Tests for the derived cell-scale slope band and its flood multiplier.

Plain assertions and a script runner, matching the rest of `ml_pipeline/tests`.
No network, no cube mock, no external data: the derivation tests use small
in-memory grids; the real cube is exercised only by `slope_preview.py`.

Run:
    .venv/bin/python ml_pipeline/tests/test_slope.py
    .venv/bin/python -m pytest ml_pipeline/tests/test_slope.py -q
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from ml_pipeline.core.scoring import compute_flood  # noqa: E402
from ml_pipeline.data import derive_slope as DS  # noqa: E402

CONFIG_DIR = REPO / "ml_pipeline" / "config"
REGION = json.loads((CONFIG_DIR / "regions" / "pune.json").read_text())
HYD = REGION["hydrology"]

BASE_LON = 73.7363
BASE_LAT = 18.3901
STEP = 0.009

EXPECTED_RAMP_DEG = math.degrees(math.atan(100.0 / 1000.0))  # 5.7106 deg


# -------------------------------------------------------------------------
# Grid helpers
# -------------------------------------------------------------------------


def _key(lon: float, lat: float) -> str:
    return f"{lon:.4f}_{lat:.4f}"


def _axes(n: int) -> tuple:
    lons = [BASE_LON + STEP * i for i in range(n)]
    lats = [BASE_LAT + STEP * j for j in range(n)]
    return lons, lats


def _make_grid(n: int, elevation) -> dict:
    lons, lats = _axes(n)
    return {
        _key(lon, lat): elevation(i, j)
        for i, lon in enumerate(lons)
        for j, lat in enumerate(lats)
    }


def _flood(slope):
    return compute_flood(
        impervious_pct=60.0,
        vegetation_pct=30.0,
        water_pct=0.0,
        design_storm_mm=HYD["design_storm_mm"],
        cn_table=HYD["cn_table"],
        bare_pct=10.0,
        mean_slope_deg=slope,
        dist_to_storm_drain_m=None,
        slope_full_effect_deg=HYD.get("slope_full_effect_deg", 15.0),
        slope_max_multiplier=HYD.get("slope_max_multiplier", 1.25),
        drain_full_benefit_m=HYD.get("storm_drain_full_benefit_m", 500.0),
        drain_min_multiplier=HYD.get("storm_drain_min_multiplier", 0.80),
    )


# -------------------------------------------------------------------------
# Derivation
# -------------------------------------------------------------------------


def test_flat_plane_has_zero_slope_everywhere():
    slopes = DS.derive_slope_cells(_make_grid(5, lambda i, j: 600.0))
    assert len(slopes) == 25
    assert all(v == 0.0 for v in slopes.values()), slopes


def test_known_east_west_ramp_matches_analytical_angle():
    lons, lats = _axes(5)
    # 100 m of rise per 1,000 m of ACTUAL geodesic distance along the row.
    dx = DS.geodesic_distance_m(lons[0], lats[2], lons[1], lats[2])
    per_step = 100.0 * dx / 1000.0
    elevations = _make_grid(5, lambda i, j: 500.0 + per_step * i)
    slopes = DS.derive_slope_cells(elevations)
    for key, value in slopes.items():
        assert abs(value - EXPECTED_RAMP_DEG) < 0.05, (key, value)


def test_known_north_ramp_matches_analytical_angle():
    lons, lats = _axes(5)
    dy = DS.geodesic_distance_m(lons[2], lats[0], lons[2], lats[1])
    per_step = 100.0 * dy / 1000.0
    elevations = _make_grid(5, lambda i, j: 500.0 + per_step * j)
    slopes = DS.derive_slope_cells(elevations)
    for key, value in slopes.items():
        assert abs(value - EXPECTED_RAMP_DEG) < 0.05, (key, value)


def test_edge_cells_use_one_sided_difference():
    lons, lats = _axes(5)
    dx = DS.geodesic_distance_m(lons[0], lats[2], lons[1], lats[2])
    per_step = 100.0 * dx / 1000.0
    elevations = _make_grid(5, lambda i, j: 500.0 + per_step * i)
    slopes = DS.derive_slope_cells(elevations)

    interior = slopes[_key(lons[2], lats[2])]
    west_edge = slopes[_key(lons[0], lats[2])]
    east_edge = slopes[_key(lons[-1], lats[2])]
    assert abs(west_edge - EXPECTED_RAMP_DEG) < 0.05, west_edge
    assert abs(east_edge - EXPECTED_RAMP_DEG) < 0.05, east_edge
    assert abs(west_edge - interior) < 0.01, (west_edge, interior)


def test_missing_column_does_not_inflate_slope():
    lons, lats = _axes(5)
    dx = DS.geodesic_distance_m(lons[0], lats[2], lons[1], lats[2])
    per_step = 100.0 * dx / 1000.0
    elevations = _make_grid(5, lambda i, j: 500.0 + per_step * i)

    # Remove the middle column entirely.  The cells either side now have
    # neighbours at 1 and 2 steps, so a `2 * one-step` denominator would
    # overstate the gradient by 1.5x.
    for lat in lats:
        elevations.pop(_key(lons[2], lat))

    slopes = DS.derive_slope_cells(elevations)
    for i in (1, 3):
        for j in range(5):
            key = _key(lons[i], lats[j])
            assert slopes[key] is not None, key
            assert abs(slopes[key] - EXPECTED_RAMP_DEG) < 0.05, (key, slopes[key])


def test_none_column_is_a_hole_not_a_ramp():
    lons, lats = _axes(5)
    dx = DS.geodesic_distance_m(lons[0], lats[2], lons[1], lats[2])
    per_step = 100.0 * dx / 1000.0
    elevations = _make_grid(5, lambda i, j: 500.0 + per_step * i)

    # A present key with a None elevation is a hole, not flat ground.
    for lat in lats:
        elevations[_key(lons[2], lat)] = None

    slopes = DS.derive_slope_cells(elevations)
    for i in (1, 3):
        for j in range(5):
            key = _key(lons[i], lats[j])
            assert slopes[key] is not None, key
            assert abs(slopes[key] - EXPECTED_RAMP_DEG) < 0.05, (key, slopes[key])
    for lat in lats:
        assert slopes[_key(lons[2], lat)] is None


def test_isolated_cell_with_no_neighbours_is_none_not_zero():
    lons, lats = _axes(3)
    # Keep only the centre and the four diagonal corners.  The centre has no
    # orthogonal neighbour in either axis, so its slope is UNKNOWN, not flat.
    elevations = {
        _key(lons[1], lats[1]): 600.0,
        _key(lons[0], lats[0]): 610.0,
        _key(lons[2], lats[0]): 620.0,
        _key(lons[0], lats[2]): 630.0,
        _key(lons[2], lats[2]): 640.0,
    }
    slopes = DS.derive_slope_cells(elevations)
    assert slopes[_key(lons[1], lats[1])] is None, slopes
    assert all(v is None for v in slopes.values()), slopes


def test_geodesic_spacing_is_used_and_is_near_one_km():
    lons, lats = _axes(2)
    dy = DS.geodesic_distance_m(lons[0], lats[0], lons[0], lats[1])
    dx = DS.geodesic_distance_m(lons[0], lats[0], lons[1], lats[0])

    # At Pune's latitude, 0.009 deg of latitude is ~1 km and of longitude is
    # ~5% shorter.  These bounds are sanity checks on the ellipsoid, not the
    # degrees-to-metres constant the derivation avoids.
    assert 990.0 < dy < 1010.0, dy
    assert 940.0 < dx < 970.0, dx

    # The derivation's one-sided north ramp is built from the SAME geodesic
    # distance, so the recovered angle is exactly the 100 m / 1 km angle.
    per_step = 100.0 * dy / 1000.0
    elevations = _make_grid(3, lambda i, j: 500.0 + per_step * j)
    slopes = DS.derive_slope_cells(elevations)
    for key, value in slopes.items():
        assert abs(value - EXPECTED_RAMP_DEG) < 0.05, (key, value)


def test_band_is_deterministic_except_for_injected_timestamp():
    grid = _make_grid(3, lambda i, j: 500.0 + 7.0 * i + 3.0 * j)
    cube = {"cell_deg": STEP, "cells": {k: {"elevation_m": v} for k, v in grid.items()}}

    first = DS.build_band(
        cube,
        source_cube="synthetic",
        source_sha256="0" * 64,
        generated_at="2026-11-03T00:00:00+00:00",
    )
    second = DS.build_band(
        cube,
        source_cube="synthetic",
        source_sha256="0" * 64,
        generated_at="2026-11-03T00:00:00+00:00",
    )
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["provenance"]["generated_at_utc"] == "2026-11-03T00:00:00+00:00"

    later = DS.build_band(
        cube,
        source_cube="synthetic",
        source_sha256="0" * 64,
        generated_at="2026-11-04T00:00:00+00:00",
    )
    # Everything except the timestamp is byte-identical.
    assert later["provenance"]["generated_at_utc"] == "2026-11-04T00:00:00+00:00"
    first["provenance"]["generated_at_utc"] = None
    later["provenance"]["generated_at_utc"] = None
    assert json.dumps(first, sort_keys=True) == json.dumps(later, sort_keys=True)


# -------------------------------------------------------------------------
# Flood multiplier
# -------------------------------------------------------------------------


def test_flood_multiplier_is_monotonic_and_capped():
    slopes = [0.0, 5.0, 15.0, 30.0]
    results = [_flood(s) for s in slopes]
    scores = [r["score"] for r in results]
    multipliers = [r["slope_multiplier"] for r in results]

    assert all(b >= a for a, b in zip(scores, scores[1:])), scores
    assert multipliers[0] == 1.0
    assert 1.0 < multipliers[1] < 1.25, multipliers
    assert multipliers[2] == 1.25, multipliers
    assert multipliers[3] == 1.25, multipliers
    assert scores[2] == scores[3], scores


def test_missing_slope_is_a_no_op_and_reports_unavailable():
    missing = _flood(None)
    flat = _flood(0.0)

    assert missing["slope_available"] is False
    assert missing["slope_basis"].startswith("unavailable")
    assert missing["slope_multiplier"] == 1.0
    assert missing["score"] == flat["score"], (missing["score"], flat["score"])
    # Zero is a real slope, not the same thing as an unknown slope.
    assert flat["slope_available"] is True


# -------------------------------------------------------------------------
# Runner
# -------------------------------------------------------------------------


def _run() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    passed, failed = 0, []
    for name, fn in tests:
        try:
            fn()
            passed += 1
            print(f"  PASS  {name}")
        except AssertionError as exc:
            failed.append((name, str(exc)))
            print(f"  FAIL  {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed.append((name, f"{type(exc).__name__}: {exc}"))
            print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
    print(f"\n{passed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run())
