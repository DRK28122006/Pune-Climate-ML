"""Ward-level census canopy dump (slow: ~10 s/ward, 1 GB index loads).

Writes /tmp/census_ward.csv INCREMENTALLY (flush per ward) so partial
results survive timeouts. Join with /tmp/gedi_ward.csv for the
census-vs-GEDI cross-check. Skips wards already present (resumable).

Usage:
    PYTHONPATH=. .venv/bin/python ml_pipeline/data/census_ward_dump.py
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from ml_pipeline.core.geometry import ward_tree_profile  # noqa: E402

OUT = "/tmp/census_ward.csv"


def main() -> int:
    done = set()
    if os.path.exists(OUT):
        with open(OUT) as f:
            for r in csv.DictReader(f):
                done.add(int(r["ward"]))
    print(f"resuming: {len(done)}/41 already done", flush=True)
    with open(OUT, "a", newline="") as f:
        w = csv.writer(f)
        # Real ward_tree_profile keys (fixed 2026-10-10: the first version
        # read tree_count/mature_count/rare_count, which do not exist --
        # every row came out None,None,None. Verified against geometry.py).
        cols = ["ward", "canopy_cover_pct", "trees", "mature_girth60",
                "heritage_girth90", "rare", "dead", "median_girth_cm",
                "reliable", "notes", "available"]
        if not done:
            w.writerow(cols)
        for ward in range(1, 42):
            if ward in done:
                continue
            try:
                p = ward_tree_profile(ward)
                w.writerow([ward, p.get("canopy_cover_pct"),
                            p.get("trees"), p.get("mature_girth60"),
                            p.get("heritage_girth90"), p.get("rare"),
                            p.get("dead"), p.get("median_girth_cm"),
                            p.get("trees_are_reliable"),
                            "; ".join(p.get("notes") or []),
                            p.get("available")])
            except Exception as e:  # noqa: BLE001 -- per-ward isolation
                w.writerow([ward, "ERROR", type(e).__name__, "", "", "",
                            "", "", "", str(e)[:120], False])
            f.flush()
            print(f"ward {ward} done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
