"""Smoke-test the cube builder on three cells before the full citywide run.

Landsat reductions are the kind of thing that fails on the second cell after
working perfectly on the first (scale limits, mask emptiness, band name typos),
so the reduce logic is exercised on three very different cells: dense core,
green periphery, and a hill slope.

Run: .venv/bin/python -m ml_pipeline.data.smoke_cube
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import ee  # type: ignore

from ml_pipeline.data import build_cube as B


def main() -> int:
    ee.Initialize()
    lst = B.surface_temperature(2024)
    veg = B.vegetation_indices()
    dw = B.dynamic_world_tree(2024)
    terr = B.terrain()

    probes = [
        ("Shivajinagar (dense core)", {"lon0": 73.835, "lat0": 18.530, "lon1": 73.844, "lat1": 18.539}),
        ("Panchvati / Aundh (green)", {"lon0": 73.845, "lat0": 18.545, "lon1": 73.854, "lat1": 18.554}),
        ("Sinhagad / hill slope", {"lon0": 73.855, "lat0": 18.360, "lon1": 73.870, "lat1": 18.400}),
    ]

    for label, cell in probes:
        print(f"\n=== {label}")
        try:
            vals = B.reduce_cell(lst, veg, dw, terr, cell)
            for k, v in vals.items():
                print(f"    {k:>20} : {v.getInfo() if hasattr(v, 'getInfo') else v}")
        except Exception as exc:  # noqa: BLE001
            print(f"    ERROR {type(exc).__name__}: {str(exc)[:300]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())