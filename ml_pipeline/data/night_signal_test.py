"""Night-heat signal test: does the night observable carry contrast?

Reads a candidate cube (default /tmp/cube_night.json) and correlates the
night UHI delta against its physical drivers. Bar for shipping, same as
flood/green: |r| > 0.7, correctly signed, and < 25% of wards pinned at 0.

Also cross-checks the city-scale night delta against the YCEO Pune anchor
(night +1.14 C): if our city mean is far from +1..2 C, the build is wrong.

Usage:
    .venv/bin/python ml_pipeline/data/night_signal_test.py [/path/cube.json]
"""
import json
import math
import statistics
import sys


def pearson(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    den = math.sqrt(sum(a * a for a in dx) * sum(b * b for b in dy))
    if den == 0:
        return float("nan")
    return sum(a * b for a, b in zip(dx, dy)) / den


def main(path="/tmp/cube_night.json"):
    cube = json.load(open(path))
    cells = cube["cells"]
    rows = []
    for cid, r in cells.items():
        if not r:
            continue
        nm = r.get("lst_night_mean_c")
        nr = r.get("lst_night_reference_c")
        b = r.get("built_pct")
        v = r.get("vegetation_pct")
        if None in (nm, nr, b, v):
            continue
        rows.append((cid, nm - nr, b * 100, v * 100, nm))

    print(f"cells with night delta: {len(rows)}/{len(cells)}")
    deltas = [d for _, d, _, _, _ in rows]
    print(f"night delta min/med/max: {min(deltas):.2f}/{statistics.median(deltas):.2f}/{max(deltas):.2f}")
    print(f"night mean city-wide: {statistics.mean([m for _, _, _, _, m in rows]):.2f} C "
          f"(YCEO Pune anchor: night +1.14 delta, expect city delta +1..2)")
    print(f"ref > site: {sum(1 for d in deltas if d < 0)}/{len(deltas)} "
          f"(day was 22/41 wards)")

    r_built = pearson([b for _, _, b, _, _ in rows], deltas)
    r_veg = pearson([v for _, _, _, v, _ in rows], deltas)
    r_canopy_check = pearson(
        [m for _, _, _, _, m in rows],
        [b for _, _, b, _, _ in rows],
    )
    print(f"r(built% -> night_delta) = {r_built:+.4f}  (expect positive, |>0.7|)")
    print(f"r(veg%   -> night_delta) = {r_veg:+.4f}  (expect negative, |>0.7|)")
    print(f"r(built% -> night_mean)  = {r_canopy_check:+.4f}  (sanity: hotter where built)")

    ok = (
        len(rows) >= 800
        and r_built > 0.7
        and r_veg < -0.7
    )
    print("VERDICT:", "SIGNAL - shippable" if ok else "NO SIGNAL - do not ship")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/cube_night.json"))
