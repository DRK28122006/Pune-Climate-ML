"""Are the 17 census parts disjoint, or do they overlap?

The 17 CSVs total ~6.72 million data rows, but PMC's own census reports
4,090,000 trees citywide. Either the parts share rows (double counting if we
concatenate them blindly) or 4.09M is an undercount.

This answers it by deduplicating on the census's own stable `id` column, which
is present in every part. It streams -- the files are 1.2 GB total, so nothing is
loaded into memory at once.

Run: .venv/bin/python ml_pipeline/data/check_census_parts.py
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, Iterator, List, Tuple

REPO = Path(__file__).resolve().parents[2]
CENSUS = REPO / "ml_pipeline" / "data" / "census"

csv.field_size_limit(10_000_000)


def rows(path: Path) -> Iterator[dict]:
    with path.open(newline="", encoding="utf-8", errors="replace") as fh:
        r = csv.DictReader(fh)
        for row in r:
            yield row


def main() -> int:
    parts = sorted(CENSUS.glob("*.csv"))
    if not parts:
        print(f"no CSVs in {CENSUS}")
        return 1

    print(f"parts: {len(parts)}\n")

    seen: Dict[str, str] = {}          # tree id -> part that first had it
    per_part: List[Tuple[str, int]] = []
    blank_id = 0
    total_rows = 0

    for p in parts:
        n = 0
        for row in rows(p):
            n += 1
            total_rows += 1
            tid = (row.get("id") or "").strip()
            if not tid:
                blank_id += 1
                continue
            if tid not in seen:
                seen[tid] = p.name
        per_part.append((p.name, n))
        print(f"  {p.name[:12]}... {n:>9,} rows   unique so far: {len(seen):>9,}")

    print()
    print(f"total data rows      : {total_rows:,}")
    print(f"rows with blank id   : {blank_id:,}")
    print(f"unique tree ids      : {len(seen):,}")
    print(f"duplicate rows       : {total_rows - blank_id - len(seen):,}")
    pct = (total_rows - blank_id - len(seen)) / max(1, total_rows) * 100
    print(f"duplication          : {pct:.2f}%")

    # Which parts overlap most?
    owner = Counter(seen.values())
    print("\nrows contributed (first-claim owner):")
    for name, cnt in owner.most_common():
        print(f"  {name[:12]}... {cnt:>9,}")

    print()
    print("=" * 60)
    print(f"PMC census states 4,090,000 trees citywide.")
    print(f"Unique ids found  : {len(seen):,}")
    diff = len(seen) - 4_090_000
    print(f"Difference        : {diff:+,} ({diff/4_090_000*100:+.1f}%)")
    if diff > 0:
        print()
        print("The unique count EXCEEDS the official total, so 4.09M is an")
        print("undercount (or counts a different unit). Update")
        print("pune.json trees.census_total_city_trees and the coverage")
        print("denominator, or the '6.11% loaded' figure becomes wrong.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())