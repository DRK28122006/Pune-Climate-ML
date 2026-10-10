"""Print the actual band names of every dataset the cube depends on.

Guessing band names is how a Landsat reduction silently returns 0 bands. This
prints what is really there.

Run: .venv/bin/python -m ml_pipeline.data.band_check
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import ee  # type: ignore


def main() -> int:
    ee.Initialize()
    pmc = ee.Geometry.Rectangle([73.7318, 18.3856, 74.0183, 18.6216])

    checks = [
        ("LANDSAT/LC08/C02/T1_L2", "2024-01-01", "2025-01-01"),
        ("LANDSAT/LC09/C02/T1_L2", "2024-01-01", "2025-01-01"),
        ("COPERNICUS/S2_SR_HARMONIZED", "2024-01-01", "2025-01-01"),
        ("GOOGLE/DYNAMICWORLD/V1", "2024-01-01", "2025-01-01"),
        ("MODIS/061/MOD11A2", "2024-01-01", "2025-01-01"),
    ]

    for asset, start, end in checks:
        print(f"\n=== {asset}")
        try:
            col = ee.ImageCollection(asset).filterDate(start, end).filterBounds(pmc)
            n = col.size().getInfo()
            print(f"    images: {n}")
            if n == 0:
                print("    (no images)")
                continue
            first = col.first()
            bands = first.bandNames().getInfo()
            print(f"    bands ({len(bands)}):")
            for b in bands:
                print(f"        {b}")
        except Exception as exc:  # noqa: BLE001
            print(f"    ERROR: {type(exc).__name__}: {str(exc)[:200]}")

    # Dynamic World band semantics
    print("\n=== Dynamic World first image, band values at a Pune point")
    try:
        pt = ee.Geometry.Point([73.8475, 18.5209])
        dw = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterDate(
            "2024-01-01", "2025-01-01"
        ).filterBounds(pmc).first()
        for band in ("label_class_mode", "trees", "built", "bare", "water", "labels"):
            try:
                v = dw.select(band).reduceRegion(
                    reducer=ee.Reducer.first(),
                    geometry=pt,
                    scale=10,
                    maxPixels=1e9,
                ).getInfo()
                print(f"    {band:>16}: {v}")
            except Exception as exc:  # noqa: BLE001
                print(f"    {band:>16}: MISSING ({str(exc)[:70]})")
    except Exception as exc:  # noqa: BLE001
        print(f"    ERROR: {exc}")

    # SRTM
    print("\n=== SRTM")
    try:
        srtm = ee.Image("USGS/SRTMGL1_003")
        print(f"    bands: {srtm.bandNames().getInfo()}")
        print(f"    at Shivajinagar: "
              f"{srtm.reduceRegion(reducer=ee.Reducer.first(), geometry=ee.Geometry.Point([73.8475, 18.5209]), scale=30).getInfo()}")
    except Exception as exc:  # noqa: BLE001
        print(f"    ERROR: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())