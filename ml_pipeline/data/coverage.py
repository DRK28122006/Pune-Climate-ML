"""How much of each ward is actually covered by the loaded census sample.

The tree index holds only the census CSV parts that are present on disk. A ward
whose cells are absent returns zero trees, which is an artefact of the load,
NOT a finding about the ward. Any report must therefore carry a coverage
figure next to every tree count, or a partially loaded city reads as a
treeless one.

Run: .venv/bin/python ml_pipeline/data/coverage.py
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

TREE_DB = REPO / "ml_pipeline" / "data" / "tree_index.sqlite"
REF_DB = REPO / "ml_pipeline" / "data" / "reference_layers.sqlite"


def ward_coverage(
    ward_no: int,
    tree_db: sqlite3.Connection,
    ref_db: sqlite3.Connection,
) -> Dict[str, Any]:
    """Tree density inside one ward, and how the ward compares citywide."""
    row = ref_db.execute(
        "SELECT ring_json, area_m2 FROM wards WHERE ward_no = ?", (ward_no,)
    ).fetchone()
    if not row:
        return {"ward_no": ward_no, "available": False}
    ring = json.loads(row[0])
    area_m2 = row[1] or 0.0

    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)

    n = tree_db.execute(
        "SELECT COUNT(*) FROM trees WHERE lon BETWEEN ? AND ? AND lat BETWEEN ? AND ?",
        (minx, maxx, miny, maxy),
    ).fetchone()[0]

    return {
        "ward_no": ward_no,
        "available": True,
        "ward_area_km2": round(area_m2 / 1e6, 3),
        "trees_in_bbox": n,
        "per_km2": round(n / (area_m2 / 1e6), 1) if area_m2 else 0.0,
    }


def main() -> int:
    if not TREE_DB.exists():
        print("tree index not built")
        return 2
    tree_db = sqlite3.connect(str(TREE_DB))
    ref_db = sqlite3.connect(str(REF_DB))

    total = tree_db.execute("SELECT COUNT(*) FROM trees").fetchone()[0]
    city_area = sum(
        r[0] for r in ref_db.execute("SELECT area_m2 FROM wards")
    ) / 1e6
    print(f"loaded trees           {total:,}")
    print(f"city area (41 wards)   {city_area:.1f} km2")
    print(f"loaded density         {total / city_area:.1f} trees/km2")
    print()

    rows: List[Dict[str, Any]] = []
    for ward_no, in ref_db.execute("SELECT ward_no FROM wards ORDER BY ward_no"):
        cov = ward_coverage(ward_no, tree_db, ref_db)
        if cov.get("available"):
            rows.append(cov)

    rows.sort(key=lambda r: -r["per_km2"])
    print("wards by loaded density (trees/km2):")
    print(f"{'ward':>5} {'area km2':>9} {'trees':>8} {'per km2':>9}")
    for r in rows[:10]:
        print(
            f"{r['ward_no']:>5} {r['ward_area_km2']:>9.2f} "
            f"{r['trees_in_bbox']:>8,} {r['per_km2']:>9.1f}"
        )
    print("  ...")
    for r in rows[-5:]:
        print(
            f"{r['ward_no']:>5} {r['ward_area_km2']:>9.2f} "
            f"{r['trees_in_bbox']:>8,} {r['per_km2']:>9.1f}"
        )

    zero = [r["ward_no"] for r in rows if r["trees_in_bbox"] == 0]
    print()
    print(f"wards with ZERO loaded trees: {len(zero)} of {len(rows)}")
    print(f"  {zero}")

    # A real PMC ward is not empty: the census maps ~8.4 trees/km2 citywide
    # (4.09M / 485 km2). Any ward reporting 0 is a loading artefact.
    census_total = 4_090_000
    print()
    print(f"citywide census density {census_total / city_area:.1f} trees/km2")
    print(
        f"sample covers {100.0 * total / census_total:.2f}% of the census "
        f"({total:,} of {census_total:,})"
    )
    print()
    print("A tree count of zero from this index means 'not loaded', not 'no trees'.")
    print("Load the remaining census parts before quoting any ward-level figure.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())