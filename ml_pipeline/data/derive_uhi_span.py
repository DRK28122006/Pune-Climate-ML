"""Derive the UHI span empirically from the epoch cube.

`pune.json` asks for `uhi_max_delta_c` to come from the city-wide LST
distribution rather than a typed-in guess. This computes it, so the number the
scorer divides by is derived from the same pixels the site is scored against.

Definition used
---------------
    span = p95(delta_max) - p05(delta_mean)

where delta_* is the site's LST minus its own ~1 km cell's vegetated reference.
Using per-cell references (not one city-wide number) keeps this consistent with
how `compute_heat` actually scores a site.

Why p95 - p05 and not p95 - p05 of raw LST
------------------------------------------
Raw LST includes Pune's elevation gradient (Sinhagad runs ~850 m, the core sits
at ~550 m, and LST falls with altitude). That would inflate the span with
topography rather than urban heat. Differencing against a nearby vegetated
reference cancels most of it.

Run: .venv/bin/python -m ml_pipeline.data.derive_uhi_span
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

CUBE = REPO / "ml_pipeline" / "data" / "epoch_cube.json"
REGION = REPO / "ml_pipeline" / "config" / "regions" / "pune.json"


def percentile(values: List[float], pct: float) -> Optional[float]:
    """Linear-interpolated percentile. `statistics` quantiles differ in method;
    this matches numpy's default so the number is reproducible for anyone who
    re-derives it in pandas."""
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * pct
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    frac = k - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def main() -> int:
    if not CUBE.exists():
        print(f"no cube at {CUBE} -- run build_cube first")
        return 1

    cube = json.loads(CUBE.read_text())
    cells: Dict[str, Any] = cube.get("cells", {})

    deltas_mean: List[float] = []
    deltas_max: List[float] = []
    no_ref = 0

    for key, c in cells.items():
        ref = c.get("lst_reference_c")
        if ref is None:
            no_ref += 1
            continue
        m = c.get("lst_mean_c")
        x = c.get("lst_max_c")
        if m is not None:
            deltas_mean.append(m - ref)
        if x is not None:
            deltas_max.append(x - ref)

    print(f"epoch          : {cube.get('epoch')}")
    print(f"cells total    : {len(cells)}")
    print(f"cells with ref : {len(deltas_mean) + (len(deltas_max) - len(deltas_mean)) if deltas_max else len(deltas_mean)}")
    print(f"cells w/o ref  : {no_ref}")
    print()

    if not deltas_mean:
        print("NO usable deltas -- every cell lacks a vegetated reference")
        return 1

    def stats(name: str, vals: List[float]) -> None:
        print(f"{name} (n={len(vals)})")
        for p in (5, 25, 50, 75, 95):
            v = percentile(vals, p / 100.0)
            print(f"   p{p:<3} {v:7.3f} C" if v is not None else f"   p{p:<3}     n/a")
        print(f"   min  {min(vals):7.3f} C")
        print(f"   max  {max(vals):7.3f} C")
        print()

    stats("delta_mean (cell mean LST - vegetated ref)", deltas_mean)
    if deltas_max:
        stats("delta_max  (cell max  LST - vegetated ref)", deltas_max)

    p95_mean = percentile(deltas_mean, 0.95)
    p05_mean = percentile(deltas_mean, 0.05)
    p95_max = percentile(deltas_max, 0.95) if deltas_max else None
    p05_max = percentile(deltas_max, 0.05) if deltas_max else None

    span_from_mean = (p95_mean - p05_mean) if (p95_mean is not None and p05_mean is not None) else None
    span_from_max = (p95_max - p05_max) if (p95_max is not None and p05_max is not None) else None

    print("=" * 62)
    print(f"CANDIDATE uhi_max_delta_c")
    print(f"  from delta_mean : {span_from_mean:.2f} C" if span_from_mean else "  from delta_mean : n/a")
    print(f"  from delta_max  : {span_from_max:.2f} C" if span_from_max else "  from delta_max  : n/a")
    print()
    print("  The scorer's heat factor compares lst_MEAN against the reference,")
    print("  so the delta_mean span is the consistent choice.")

    if span_from_mean:
        # Round UP to the next 0.5 C. We want the span to cover the observed
        # range with a little headroom, not to truncate the hottest sites at
        # exactly 100. Rounding down would silently cap real extremes.
        rounded = (span_from_mean + 0.5) // 0.5 * 0.5
        print(f"  RECOMMENDED: {rounded:.1f} C  (span_from_mean rounded up to 0.5 C)")
        print()
        print("  To apply: set thermal.uhi_max_delta_c in pune.json and change")
        print("  uhi_max_delta_status to 'DERIVED_FROM_EPOCH_CUBE'.")
        print()
        print(f"  current configured value: ", end="")
        cfg = json.loads(REGION.read_text())
        cur = cfg["thermal"]["uhi_max_delta_c"]
        print(f"{cur} C")
        if abs(cur - rounded) > 0.01:
            print(f"  -> differs by {rounded - cur:+.1f} C from the configured value")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())