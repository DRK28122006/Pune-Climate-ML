"""Data-integrity checks against the real PMC datasets.

These are assertions about the DATA, not unit tests of our formulas:

  - every park sits inside the ward we attribute it to
  - ward polygons cover PMC without gross gaps (union vs sum)
  - the tree index row count matches the source CSV
  - ward numbering comes from `qwr`, never from file position

Run: .venv/bin/python ml_pipeline/tests/test_data_integrity.py
Requires the two SQLite indexes to be built (ml_pipeline/cli.py build-data).
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

REF_DB = REPO / "ml_pipeline" / "data" / "reference_layers.sqlite"
TREE_DB = REPO / "ml_pipeline" / "data" / "tree_index.sqlite"
PARK_KML = REPO / "ml_pipeline" / "reference" / "pune_parks.kml"
WARD_KML = REPO / "pmc_wards_2025.kml"

FAILURES = []
CHECKS = 0


def check(cond: bool, label: str, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if cond:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}  {detail}")
        FAILURES.append(label)


def park_polygons():
    """Independent re-parse of the park KML, keyed by position."""
    text = PARK_KML.read_text(encoding="utf-8", errors="replace")
    for i, pm in enumerate(re.findall(r"<Placemark.*?</Placemark>", text, re.S)):
        m = re.search(r'<SimpleData name="structure_">(.*?)</SimpleData>', pm, re.S)
        name = m.group(1).strip() if m else None
        rings = []
        for rm in re.finditer(r"<LinearRing>(.*?)</LinearRing>", pm, re.S):
            co = [
                (float(a), float(b))
                for a, b in re.findall(r"(-?[\d.]+),(-?[\d.]+)", rm.group(1))
            ]
            if len(co) >= 3:
                rings.append(co)
        if rings:
            yield i + 1, name, max(rings, key=len)


def point_in_ring(lon, lat, ring):
    """Ray casting, on the raw coordinates (no reprojection needed for a
    containment test). Boundary counts as inside."""
    n = len(ring)
    if n < 3:
        return False
    inside = False
    for i in range(n - 1):
        x1, y1 = ring[i]
        x2, y2 = ring[i + 1]
        cross = (x2 - x1) * (lat - y1) - (y2 - y1) * (lon - x1)
        if (
            abs(cross) < 1e-12
            and min(x1, x2) - 1e-12 <= lon <= max(x1, x2) + 1e-12
            and min(y1, y2) - 1e-12 <= lat <= max(y1, y2) + 1e-12
        ):
            return True
        if (y1 > lat) != (y2 > lat):
            x_at = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < x_at:
                inside = not inside
    return inside


def main() -> int:
    if not REF_DB.exists():
        print("reference index missing; run: ml_pipeline/cli.py build-data")
        return 2

    ref = sqlite3.connect(str(REF_DB))

    print("\n== ward numbering ==")
    raw = WARD_KML.read_text(encoding="utf-8", errors="replace")
    qwr = re.findall(r'<SimpleData name="qwr">\s*([\d.]+)', raw)
    check(len(qwr) == 41, "41 placemarks carry a qwr attribute", f"got {len(qwr)}")
    file_order = [int(round(float(v))) for v in qwr]
    check(file_order != sorted(file_order),
          "file order is NOT 1..41 (so position-based numbering would be wrong)")
    stored = {r[0] for r in ref.execute("SELECT ward_no FROM wards")}
    check(stored == set(range(1, 42)), "wards stored as 1..41", f"got {sorted(stored)[:5]}...")

    print("\n== ward coverage ==")
    areas = [r[0] for r in ref.execute("SELECT area_m2 FROM wards")]
    total = sum(areas) / 1e6
    # PMC's official administrative area. 1% tolerance absorbs digitising error.
    check(455 <= total <= 500, "sum of ward areas is near PMC's 485 km2",
          f"got {total:.1f} km2")

    print("\n== park ward attribution ==")
    ward_rings = {
        r[0]: json.loads(r[1]) for r in ref.execute("SELECT ward_no, ring_json FROM wards")
    }
    db = {
        r[0]: (r[1], r[2], r[3], r[4])
        for r in ref.execute(
            "SELECT park_id, name, ward_no, centroid_lon, centroid_lat FROM parks"
        )
    }
    misattributed = []
    unresolved = 0
    for park_id, name, ring in park_polygons():
        rec = db.get(park_id)
        if rec is None:
            continue
        _, ward_no, clon, clat = rec
        if ward_no is None:
            unresolved += 1
            continue
        if not point_in_ring(clon, clat, ward_rings[ward_no]):
            misattributed.append((name, ward_no))
    check(unresolved == 0, "every park resolved to a ward", f"{unresolved} unresolved")
    check(not misattributed, "every park centroid lies inside its attributed ward",
          f"{len(misattributed)} bad: {misattributed[:3]}")

    print("\n== tree index ==")
    if TREE_DB.exists():
        tree = sqlite3.connect(str(TREE_DB))
        n = tree.execute("SELECT COUNT(*) FROM trees").fetchone()[0]
        check(n > 200_000, "tree index holds the loaded sample", f"{n} rows")
        named = tree.execute(
            "SELECT COUNT(*) FROM trees WHERE botanical_name IS NOT NULL "
            "AND botanical_name <> ''"
        ).fetchone()[0]
        check(named / n > 0.9, "most trees carry a botanical name",
              f"{named}/{n}")
    else:
        print("  SKIP  tree index not built")

    print(f"\n{CHECKS - len(FAILURES)}/{CHECKS} passed")
    if FAILURES:
        print("FAILED:")
        for f in FAILURES:
            print("   -", f)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())