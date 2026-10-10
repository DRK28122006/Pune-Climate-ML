"""Break down the ward dispersion result by factor.

Total scores can spread while hiding the real problem: one factor might be
inverted, or pinned at a constant, or dominating regardless of location. This
prints the four sub-scores side by side with the inputs that drive them, plus
the pairwise correlation between each factor and the final score.

Run: .venv/bin/python ml_pipeline/data/factor_breakdown.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "ml_pipeline" / "data" / "ward_validation.json"

FACTORS = ["flood", "heat", "green", "carbon"]


def corr(xs: List[float], ys: List[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    if dx == 0 or dy == 0:
        return 0.0
    return num / (dx * dy)


def main() -> int:
    if not SRC.exists():
        print(f"no {SRC} -- run validate_wards.py first")
        return 1
    rows = json.loads(SRC.read_text())["rows"]
    rows = [r for r in rows if r.get("score") is not None]
    rows.sort(key=lambda r: r["score"])

    print(f"{'ward':>5} {'score':>7} | " + " ".join(f"{f:>7}" for f in FACTORS)
          + f" | {'built%':>7} {'veg%':>6} {'UHI':>6} {'canopy%':>8} {'trees':>9}")
    print("-" * 118)
    for r in rows:
        s = r["sub_scores"]
        uhi = r["uhi_delta_c"]
        print(
            f"{r['ward']:>5} {r['score']:>7.1f} | "
            + " ".join(f"{s.get(f, float('nan')):>7.1f}" for f in FACTORS)
            + f" | {r['built_pct']:>7.1f} {r['veg_pct']:>6.1f} "
              f"{uhi:>+6.2f} {r['tree_canopy_pct']:>8.1f} {r['trees_loaded']:>9,}"
        )

    print()
    print("=" * 70)
    print("FACTOR SPREAD (is any factor pinned?)")
    print("=" * 70)
    for f in FACTORS:
        vals = [r["sub_scores"].get(f) for r in rows if r["sub_scores"].get(f) is not None]
        if not vals:
            print(f"{f:<10} no values")
            continue
        sp = max(vals) - min(vals)
        flag = "  <-- PINNED, carries no information" if sp < 2.0 else ""
        print(f"{f:<10} n={len(vals)}  min={min(vals):>6.1f}  max={max(vals):>6.1f}  "
              f"spread={sp:>6.1f}{flag}")

    print()
    print("=" * 70)
    print("CORRELATION with final score (n is tiny: read direction, not magnitude)")
    print("=" * 70)
    scores = [r["score"] for r in rows]
    for f in FACTORS:
        pairs = [(r["score"], r["sub_scores"].get(f)) for r in rows
                 if r["sub_scores"].get(f) is not None]
        if len(pairs) < 2:
            continue
        xs = [a for a, _ in pairs]
        ys = [b for _, b in pairs]
        c = corr(xs, ys)
        direction = "drives" if c > 0.4 else ("drives (inverse)" if c < -0.4 else "weak")
        print(f"{f:<10} r = {c:+.3f}   {direction}")

    print()
    for key, label in (("built_pct", "built %"), ("uhi_delta_c", "UHI delta"),
                       ("veg_pct", "sat vegetation %"), ("tree_canopy_pct", "tree canopy %"),
                       ("trees_loaded", "trees in ward")):
        pairs = [(r["score"], r.get(key)) for r in rows if r.get(key) is not None]
        if len(pairs) < 2:
            continue
        c = corr([a for a, _ in pairs], [float(b) for _, b in pairs])
        print(f"{label:<18} r = {c:+.3f} with final score")

    print()
    print("=" * 70)
    print("READING THIS")
    print("=" * 70)
    print("Score = 100 - weighted impact, so a HIGHER sub-score means a BETTER")
    print("outcome for that factor. A factor should correlate POSITIVELY with")
    print("the final score: high green coverage should raise the score.")
    print()
    print("Note the model scores the SUBMITTED PLOT (a fixed 2,000 m2 building"),
    print("on a 4,000 m2 plot), not the ward as a whole. Ward-level satellite"),
    print("context sets the baseline; the tree canopy column is ward-level and is")
    print("NOT an input to the score in this harness. That is deliberate -- it")
    print("isolates whether the satellite layer drives dispersion. Canopy only")
    print("enters when a real site polygon and its trees are processed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())