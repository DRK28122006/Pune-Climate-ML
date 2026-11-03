"""Tests for the floodplain / watercourse helpers.

No synthetic floodplain polygons.  The real OSM proximity layer is used when
present; the only fixture is an empty SQLite file, which proves the UNAVAILABLE
path without inventing an inundation extent.

Run:
    python ml_pipeline/tests/test_floodplain.py
    python -m pytest ml_pipeline/tests/test_floodplain.py -q
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from ml_pipeline.core import floodplain as FP  # noqa: E402

FLOOD_DB = REPO / "ml_pipeline" / "data" / "flood_layers.sqlite"


def _river_vertex() -> tuple:
    conn = sqlite3.connect(f"file:{FLOOD_DB}?mode=ro", uri=True)
    try:
        row = conn.execute(
            "SELECT geometry_json FROM waterways WHERE kind='river' ORDER BY id LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    geom = json.loads(row[0])
    # LineString: [[lon,lat], ...]; MultiLineString: [[[lon,lat], ...], ...]
    line = geom
    if geom and isinstance(geom[0], list) and isinstance(geom[0][0], list):
        line = geom[0]
    return float(line[0][0]), float(line[0][1])


def test_missing_layer_is_unavailable():
    path = "/tmp/opencode/no_such_flood_layer.sqlite"
    fs = FP.floodplain_status(73.85, 18.52, layer_path=path)
    wd = FP.watercourse_distance_m(73.85, 18.52, layer_path=path)
    for out in (fs, wd):
        assert out["status"] == "UNAVAILABLE"
        assert out["nearest_watercourse_m"] is None
        assert out["source"] is None
        assert out["confidence"] == "none"
    assert fs["in_floodplain"] is None


def test_empty_layer_is_unavailable():
    handle = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    path = handle.name
    handle.close()
    try:
        conn = sqlite3.connect(path)
        conn.close()
        fs = FP.floodplain_status(73.85, 18.52, layer_path=path)
        wd = FP.watercourse_distance_m(73.85, 18.52, layer_path=path)
        assert fs["status"] == "UNAVAILABLE"
        assert fs["in_floodplain"] is None
        assert wd["status"] == "UNAVAILABLE"
    finally:
        Path(path).unlink(missing_ok=True)


def test_current_layer_is_proximity_only():
    if not FLOOD_DB.exists():
        return
    lon, lat = _river_vertex()
    fs = FP.floodplain_status(lon, lat, layer_path=str(FLOOD_DB))
    wd = FP.watercourse_distance_m(lon, lat, layer_path=str(FLOOD_DB))

    assert fs["status"] == "PROXIMITY_ONLY"
    assert fs["in_floodplain"] is None
    assert fs["confidence"] == "low"
    assert fs["source"] == "osm-overpass-2026-11-03"
    assert fs["licence"] == "ODbL-1.0"
    assert fs["nearest_watercourse_m"] is not None
    assert fs["nearest_watercourse_m"] < 1.0

    assert wd["status"] == "PROXIMITY_ONLY"
    assert wd["nearest_watercourse_m"] is not None
    assert abs(fs["nearest_watercourse_m"] - wd["nearest_watercourse_m"]) < 0.2


def test_far_point_has_positive_distance():
    if not FLOOD_DB.exists():
        return
    lon, lat = _river_vertex()
    out = FP.watercourse_distance_m(lon + 0.05, lat + 0.05, layer_path=str(FLOOD_DB))
    assert out["status"] == "PROXIMITY_ONLY"
    assert out["nearest_watercourse_m"] is not None
    assert out["nearest_watercourse_m"] > 100.0


def _run() -> int:
    tests = [
        (name, fn)
        for name, fn in sorted(globals().items())
        if name.startswith("test_") and callable(fn)
    ]
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
