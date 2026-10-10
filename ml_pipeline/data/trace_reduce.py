"""Trace reduce_cell band by band to find which reduce returns 0 bands.

Run: .venv/bin/python -m ml_pipeline.data.trace_reduce
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

    region = ee.Geometry.Rectangle(
        [73.835, 18.530, 73.844, 18.539], proj="EPSG:4326", geodesic=False
    )

    def try_reduce(label, img, band):
        try:
            sel = img.select(band)
            v = sel.reduceRegion(
                reducer=ee.Reducer.mean(), geometry=region, scale=30, maxPixels=1e9
            )
            print(f"  {label:<32} {v.getInfo()}")
        except Exception as exc:  # noqa: BLE001
            print(f"  {label:<32} FAIL {str(exc)[:120]}")

    print("component band names:")
    print(f"  lst : {lst.bandNames().getInfo()}")
    print(f"  veg : {veg.bandNames().getInfo()}")
    print(f"  dw  : {dw.bandNames().getInfo()}")
    print(f"  terr: {terr.bandNames().getInfo()}")
    print()

    print("single-band means:")
    try_reduce("lst.lst_c", lst, "lst_c")
    try_reduce("veg.vegetation_pct", veg, "vegetation_pct")
    try_reduce("dw.tree_canopy_pct", dw, "tree_canopy_pct")
    try_reduce("dw.built_pct", dw, "built_pct")
    try_reduce("dw.bare_pct", dw, "bare_pct")
    try_reduce("dw.water_pct", dw, "water_pct")
    try_reduce("dw.grass_pct", dw, "grass_pct")
    try_reduce("terr.elevation_m", terr, "elevation_m")

    print()
    print("LST masked to vegetation (the reference path):")
    try:
        ref = lst.updateMask(veg.gt(0.3)).reduceRegion(
            reducer=ee.Reducer.median(), geometry=region, scale=30, maxPixels=1e9
        ).getInfo()
        print(f"  reference median LST: {ref}")
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL {str(exc)[:160]}")

    print()
    print("LST mean+max combiner:")
    try:
        v = lst.reduceRegion(
            reducer=ee.Reducer.mean().combine(ee.Reducer.max(), sharedInputs=True),
            geometry=region,
            scale=30,
            maxPixels=1e9,
        ).getInfo()
        print(f"  {v}")
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL {str(exc)[:160]}")

    print()
    print("full reduce_cell:")
    try:
        vals = B.reduce_cell(lst, veg, dw, terr, {"lon0": 73.835, "lat0": 18.530, "lon1": 73.844, "lat1": 18.539})
        for k, v in vals.items():
            print(f"  {k:>20}: {v.getInfo() if hasattr(v, 'getInfo') else v}")
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL {type(exc).__name__}: {str(exc)[:200]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())