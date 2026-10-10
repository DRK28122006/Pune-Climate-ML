"""Sanity-check the finished epoch cube before trusting it.

A cube can be 864/864 "with data" and still be nonsense: un-scaled brightness
temperatures, a reference that exceeds the site, or a vegetation fraction that
never leaves 0..1. This prints the distribution of every band and flags the
specific conditions that would make a score meaningless.

Run: .venv/bin/python ml_pipeline/data/cube_report.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Optional

REPO = Path(__file__).resolve().parents[2]
CUBE = REPO / "ml_pipeline" / "data" / "epoch_cube.json"


def col(cells: dict, key: str) -> List[float]:
    out = []
    for v in cells.values():
        x = v.get(key)
        if x is not None:
            try:
                out.append(float(x))
            except (TypeError, ValueError):
                pass
    return out


def pc(v: List[float], p: float) -> Optional[float]:
    if not v:
        return None
    s = sorted(v)
    k = (len(s) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    f = k - lo
    return s[lo] * (1 - f) + s[hi] * f


def main() -> int:
    if not CUBE.exists():
        print("no cube")
        return 1
    d = json.loads(CUBE.read_text())
    cells = d["cells"]
    print(f"epoch {d['epoch']}   cells {len(cells)}   stats {d.get('stats')}")
    print()

    bands = [
        ("lst_mean_c", "LST mean"),
        ("lst_max_c", "LST max"),
        ("lst_reference_c", "LST reference"),
        ("built_pct", "built fraction"),
        ("bare_pct", "bare fraction"),
        ("vegetation_pct", "vegetation fraction"),
        ("tree_canopy_pct", "tree canopy prob"),
        ("water_pct", "water fraction"),
        ("elevation_m", "elevation m"),
    ]
    print(f"{'band':<20} {'n':>4} {'min':>9} {'p25':>9} {'med':>9} {'p75':>9} {'max':>9}")
    print("-" * 74)
    for key, label in bands:
        v = col(cells, key)
        if not v:
            print(f"{label:<20} {0:>4}   (missing)")
            continue
        s = sorted(v)
        print(f"{label:<20} {len(v):>4} {s[0]:>9.3f} {pc(v,.25):>9.3f} "
              f"{pc(v,.5):>9.3f} {pc(v,.75):>9.3f} {s[-1]:>9.3f}")

    print()
    print("=" * 74)
    print("CHECKS")
    print("=" * 74)
    ok = True

    lst = col(cells, "lst_mean_c")
    ref = col(cells, "lst_reference_c")

    # 1. Temperatures must be in a physically plausible Pune range. Raw
    #    brightness temperature (unscaled DN) would be in the tens of thousands.
    bad_t = [x for x in lst if not (15.0 <= x <= 60.0)]
    print(f"{'LST in 15..60 C':<40} {'PASS' if not bad_t else 'FAIL ' + str(len(bad_t))}")
    if bad_t:
        ok = False
        print(f"    offenders: {bad_t[:5]}")

    # 2. The vegetated reference must be COOLER than the cell mean almost
    #    everywhere. If it is hotter, the reference logic is inverted.
    deltas = []
    for v in cells.values():
        m = v.get("lst_mean_c")
        r = v.get("lst_reference_c")
        if m is not None and r is not None:
            deltas.append(m - r)
    hotter = [x for x in deltas if x < -2.0]
    print(f"{'reference cooler than site':<40} {'PASS' if not hotter else 'FAIL ' + str(len(hotter))}")
    print(f"    cells where site is 2C+ COOLER than its own green reference: {len(hotter)}")
    if len(hotter) > len(deltas) * 0.15:
        ok = False
        print("    (>15% of cells -- reference logic looks inverted)")

    if deltas:
        ds = sorted(deltas)
        span = (pc(ds, .95) or 0.0) - (pc(ds, .05) or 0.0)
        p05 = pc(ds, .05) or 0.0
        p50 = pc(ds, .5) or 0.0
        p95 = pc(ds, .95) or 0.0
        print(f"{'':<40} p05={p05:.3f}  med={p50:.3f}  p95={p95:.3f}")
        print(f"{'  implied p95-p05 UHI span':<40} {span:.2f} C")
        print(f"{'    configured uhi_max_delta_c':<40} 8.0 C")
        if span > 8.0 * 1.5:
            print(f"    NOTE: cube span is {span/8.0:.1f}x the configured value.")
            print("          Either raise the config or investigate.")

    # 3. Land-cover probabilities must be fractions.
    for key in ("built_pct", "vegetation_pct", "tree_canopy_pct", "water_pct"):
        v = col(cells, key)
        oob = [x for x in v if not (0.0 <= x <= 1.0)]
        status = "PASS" if not oob else f"FAIL {len(oob)}"
        print(f"{key + ' in 0..1':<40} {status}")
        if oob:
            ok = False

    # 4. Built + vegetation should not exceed 1 everywhere (they can overlap at
    #    pixel edges, but a sum above ~1.4 everywhere means a mix-up).
    sums = [
        float(v.get("built_pct", 0)) + float(v.get("vegetation_pct", 0))
        for v in cells.values()
        if v.get("built_pct") is not None and v.get("vegetation_pct") is not None
    ]
    if sums:
        print(f"{'built+veg median':<40} {pc(sums,.5):.3f}  max {max(sums):.3f}")

    # 5. Elevation must match Pune (~500-850 m).
    elev = col(cells, "elevation_m")
    oob = [x for x in elev if not (400.0 <= x <= 900.0)]
    print(f"{'elevation in 400..900 m':<40} {'PASS' if not oob else 'WARN ' + str(len(oob))}")

    print()
    print("VERDICT:", "PASS" if ok else "SUSPECT -- fix before scoring")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())