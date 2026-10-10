"""Print the exact reduceRegion output keys for the LST composite.

Run: .venv/bin/python -m ml_pipeline.data.keys_check
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

    print(f"lst bands : {lst.bandNames().getInfo()}")
    print(f"veg bands : {veg.bandNames().getInfo()}")

    region = ee.Geometry.Rectangle(
        [73.835, 18.530, 73.844, 18.539], proj="EPSG:4326", geodesic=False
    )

    print("\nmean only:")
    print(f"  {lst.reduceRegion(reducer=ee.Reducer.mean(), geometry=region, scale=30, maxPixels=1e9).getInfo()}")

    print("\nmean + max combined:")
    print(f"  {lst.reduceRegion(reducer=ee.Reducer.mean().combine(ee.Reducer.max(), sharedInputs=True), geometry=region, scale=30, maxPixels=1e9).getInfo()}")

    print("\nreference (masked to veg, median):")
    print(f"  {lst.updateMask(veg.gt(0.3)).reduceRegion(reducer=ee.Reducer.median(), geometry=region, scale=30, maxPixels=1e9).getInfo()}")

    print("\nreference (masked to veg, median) WITHOUT mask:")
    print(f"  {lst.reduceRegion(reducer=ee.Reducer.median(), geometry=region, scale=30, maxPixels=1e9).getInfo()}")

    print("\nveg mask coverage in this cell:")
    print(f"  {veg.gt(0.3).reduceRegion(reducer=ee.Reducer.mean(), geometry=region, scale=30, maxPixels=1e9).getInfo()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())