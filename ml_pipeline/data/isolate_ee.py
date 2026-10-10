"""Isolate exactly which cube component collapses to 0 bands.

Run: .venv/bin/python -m ml_pipeline.data.isolate_ee
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import ee  # type: ignore

from ml_pipeline.data import build_cube as B


def show(label, img):
    try:
        bands = img.bandNames().getInfo()
        print(f"    {label:<28} bands={bands}")
    except Exception as exc:  # noqa: BLE001
        print(f"    {label:<28} ERROR {str(exc)[:150]}")


def main() -> int:
    ee.Initialize()

    print("=== raw collections over PMC 2024")
    l8 = ee.ImageCollection("LANDSAT/LC08/C02/T1_L2").filterDate(
        "2024-01-01", "2025-01-01"
    )
    print(f"    L8 images: {l8.size().getInfo()}")
    show("L8 first, raw", l8.first())
    show("L8 after cloud filter", l8.filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60)).first())
    show("L8 after QA mask map", l8.filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60)).map(B._cloud_mask_l8l9).first())
    show("L8 ST_B10 mean", l8.map(B._cloud_mask_l8l9).select("ST_B10").mean())

    print("\n=== LST pipeline pieces")
    merged = l8.map(B._cloud_mask_l8l9).merge(
        ee.ImageCollection("LANDSAT/LC09/C02/T1_L2")
        .filterDate("2024-01-01", "2025-01-01")
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60))
        .map(B._cloud_mask_l8l9)
    )
    show("merged size", merged)
    print(f"    merged images: {merged.size().getInfo()}")
    show("merged ST_B10 mean", merged.select("ST_B10").mean())

    k = merged.select("ST_B10").mean()
    show("after scale", k.multiply(0.00341802))
    show("after +149", k.multiply(0.00341802).add(149.0))
    show("after -273.15 (C)", k.multiply(0.00341802).add(149.0).subtract(273.15))

    print("\n=== LST value at Shivajinagar")
    pt = ee.Geometry.Point([73.8475, 18.5209])
    try:
        v = (
            merged.select("ST_B10")
            .mean()
            .multiply(0.00341802)
            .add(149.0)
            .subtract(273.15)
            .reduceRegion(reducer=ee.Reducer.first(), geometry=pt, scale=30, maxPixels=1e9)
            .getInfo()
        )
        print(f"    LST C = {v}")
    except Exception as exc:  # noqa: BLE001
        print(f"    ERROR {str(exc)[:200]}")

    print("\n=== vegetation")
    try:
        veg = B.vegetation_indices()
        show("veg", veg)
        v = veg.reduceRegion(reducer=ee.Reducer.first(), geometry=pt, scale=30).getInfo()
        print(f"    veg at pt = {v}")
    except Exception as exc:  # noqa: BLE001
        print(f"    ERROR {str(exc)[:200]}")

    print("\n=== dynamic world")
    try:
        dw = B.dynamic_world_tree(2024)
        show("dw", dw)
        v = dw.reduceRegion(reducer=ee.Reducer.mean(), geometry=pt, scale=30, maxPixels=1e9).getInfo()
        print(f"    dw at pt = {v}")
    except Exception as exc:  # noqa: BLE001
        print(f"    ERROR {str(exc)[:200]}")

    print("\n=== terrain")
    try:
        t = B.terrain()
        show("terr", t)
        v = t.reduceRegion(reducer=ee.Reducer.first(), geometry=pt, scale=30).getInfo()
        print(f"    terr at pt = {v}")
    except Exception as exc:  # noqa: BLE001
        print(f"    ERROR {str(exc)[:200]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())