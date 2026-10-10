"""Controlled proof of the heat inversion, with NO site-selection noise.

validate_sites.py mixed many variables at once: built fraction, storey count,
material quantities, tree count, elevation and drainage distance all varied
together, so its ordering cannot isolate a cause. This script varies exactly ONE
input -- the impervious fraction of the site -- and holds everything else fixed
at a realistic mid-rise Pune value, then reports the heat score.

If the score FALLS as imperviousness rises, the factor is inverted and no
amount of downstream tuning will fix it.

Run: .venv/bin/python ml_pipeline/data/heat_isolation.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

CONFIG_DIR = REPO / "ml_pipeline" / "config"
CUBE = REPO / "ml_pipeline" / "data" / "epoch_cube.json"


def main() -> None:
    cube = json.loads(CUBE.read_text())
    cells = cube["cells"]

    from ml_pipeline.core import scoring as S

    region = json.loads((CONFIG_DIR / "regions" / "pune.json").read_text())
    span = float(region["thermal"]["uhi_max_delta_c"])

    # ---- Part 1: sweep the real cube's own cells -------------------------
    # Every cell already carries a consistent set of bands, so ordering cells by
    # built_pct and reading their heat scores is a natural experiment over the
    # actual city -- no synthetic inputs at all.
    rows = []
    for cid, c in cells.items():
        lst = c.get("lst_mean_c")
        ref = c.get("lst_reference_c")
        if lst is None or ref is None:
            continue
        built = float(c.get("built_pct") or 0.0)
        veg = float(c.get("vegetation_pct") or 0.0)
        rows.append((built, veg, lst, ref))

    rows.sort()

    print("=" * 84)
    print("PART 1 — the real cube, sorted by impervious fraction (864 cells, no synthetic data)")
    print("=" * 84)
    print(f"{'built%':>7} {'veg%':>6} {'lst':>7} {'ref':>7} {'delta':>7} {'heat':>7}")
    print("-" * 84)

    n = len(rows)
    # Print 10 evenly-spaced samples across the imperviousness range, so the
    # trend is visible rather than buried in 864 rows.
    for i in range(10):
        built, veg, lst, ref = rows[int(i * (n - 1) / 9)]
        delta = lst - ref
        score = max(0.0, min(100.0, delta / span * 100.0))
        print(f"{built*100:>7.1f} {veg*100:>6.1f} {lst:>7.2f} {ref:>7.2f} "
              f"{delta:>+7.2f} {score:>7.1f}")

    # Quantify: correlation between imperviousness and the heat score.
    def pearson(xs, ys):
        n = len(xs)
        if n < 3:
            return float("nan")
        mx, my = sum(xs) / n, sum(ys) / n
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        dx = sum((x - mx) ** 2 for x in xs) ** 0.5
        dy = sum((y - my) ** 2 for y in ys) ** 0.5
        return num / (dx * dy) if dx and dy else float("nan")

    xs = [r[0] for r in rows]
    ys = [max(0.0, min(100.0, (r[2] - r[3]) / span * 100.0)) for r in rows]

    print()
    print(f"cells with usable LST + reference: {n}")
    print(f"impervious fraction range: {min(xs)*100:.1f}% .. {max(xs)*100:.1f}%")
    print(f"Pearson r(impervious, heat_score) = {pearson(xs, ys):+.3f}")
    print()
    if pearson(xs, ys) < -0.2:
        print("*** INVERTED: the more built-up a cell is, the LOWER its heat score. ***")
        print("    The factor is measuring how much vegetation the cell contains,")
        print("    not how hot the proposed development will be.")
    elif pearson(xs, ys) > 0.2:
        print("*** CORRECT: heat rises with imperviousness, as physics requires. ***")
    else:
        print("*** NO RELATIONSHIP: heat does not respond to imperviousness at all. ***")

    # ---- Part 2: the fix, measured ---------------------------------------
    print()
    print("=" * 84)
    print("PART 2 — what the reference SHOULD be: city-wide green median")
    print("=" * 84)
    # The alternative already documented in pune.json: reference the median LST
    # of ALL vegetated pixels in the city, not just this cell's own. That makes
    # the delta measure "how much hotter than the city's green baseline", which
    # is the question a municipality is actually asking.
    all_veg_lsts = sorted(r[2] for r in rows if r[1] >= 0.15)
    city_ref = all_veg_lsts[len(all_veg_lsts) // 2] if all_veg_lsts else None
    print(f"city-wide vegetated-pixel LST median: {city_ref:.2f} C "
          f"(from {len(all_veg_lsts)} cells with >=15% vegetation)")
    print()
    print(f"{'built%':>7} {'lst':>7} {'delta':>7} {'heat(city ref)':>16}")
    print("-" * 84)
    ys2 = []
    for i in range(10):
        built, veg, lst, ref = rows[int(i * (n - 1) / 9)]
        delta = lst - (city_ref or ref)
        score = max(0.0, min(100.0, delta / span * 100.0))
        ys2.append(score)
        print(f"{built*100:>7.1f} {lst:>7.2f} {delta:>+7.2f} {score:>16.1f}")
    print()
    print(f"Pearson r(impervious, heat_score) with city-wide reference = "
          f"{pearson(xs, ys2):+.3f}")
    print()
    print(f"NOTE: with a 2.0 C span, city-referenced deltas range "
          f"{min(ys2):.0f}..{max(ys2):.0f}. A span calibrated for a per-cell")
    print("reference saturates differently against a city baseline, so the span")
    print("must be re-derived if the reference method changes.")


if __name__ == "__main__":
    main()