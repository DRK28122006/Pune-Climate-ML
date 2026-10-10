"""Inspect raw Landsat thermal pixels and QA values to find why the mask empties.

Run: .venv/bin/python -m ml_pipeline.data/qa_check.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import ee  # type: ignore

BBOX = [73.7318, 18.3856, 74.0183, 18.6216]
PT = [73.8475, 18.5209]  # Shivajinagar


def main() -> int:
    ee.Initialize()
    region = ee.Geometry.Rectangle(BBOX, proj="EPSG:4326", geodesic=False)
    pt = ee.Geometry.Point(PT)

    col = (
        ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
        .filterDate("2024-01-01", "2025-01-01")
        .filterBounds(region)
    )
    print(f"L8 images over PMC 2024: {col.size().getInfo()}")
    col9 = (
        ee.ImageCollection("LANDSAT/LC09/C02/T1_L2")
        .filterDate("2024-01-01", "2025-01-01")
        .filterBounds(region)
    )
    print(f"L9 images over PMC 2024: {col9.size().getInfo()}")

    first = col.first()
    print("\nFirst scene raw values at Shivajinagar:")
    for band in ("ST_B10", "ST_TRAD", "ST_URAD", "ST_EMIS", "QA_PIXEL"):
        try:
            v = first.select(band).reduceRegion(
                reducer=ee.Reducer.first(), geometry=pt, scale=30, maxPixels=1e9
            ).getInfo()
            print(f"  {band:>12}: {v}")
        except Exception as exc:  # noqa: BLE001
            print(f"  {band:>12}: ERR {str(exc)[:90]}")

    qa = first.select("QA_PIXEL").reduceRegion(
        reducer=ee.Reducer.first(), geometry=pt, scale=30, maxPixels=1e9
    ).get("QA_PIXEL")
    if qa is not None:
        print(f"\n  QA_PIXEL = {qa}")
        print(f"  & 0b11111110 = {int(qa) & int('11111110', 2)}")
        print(f"  == 0 ? {int(qa) & int('11111110', 2) == 0}")
        for bit, name in enumerate(
            ["fill", "dilate", "cirrus", "cloud", "shadow", "snow", "clear", "water"]
        ):
            print(f"    bit {bit} ({name}): {(int(qa) >> bit) & 1}")

    print("\nMean ST_B10 WITHOUT any mask, over whole PMC:")
    raw_mean = col.select("ST_B10").mean()
    v = raw_mean.reduceRegion(
        reducer=ee.Reducer.mean(), geometry=region, scale=30, maxPixels=1e9
    ).getInfo()
    print(f"  {v}")

    print("\nMean ST_B10 with QA mask, over whole PMC:")
    def masked(im):
        q = im.select("QA_PIXEL")
        return im.updateMask(q.bitwiseAnd(int("11111110", 2)).eq(0))

    m = col.map(masked).select("ST_B10").mean()
    v2 = m.reduceRegion(
        reducer=ee.Reducer.mean(), geometry=region, scale=30, maxPixels=1e9
    ).getInfo()
    print(f"  {v2}")

    print("\nHow many pixels survive the mask citywide?")
    print(f"  {col.map(masked).select('ST_B10').count().reduceRegion(reducer=ee.Reducer.mean(), geometry=region, scale=30, maxPixels=1e9).getInfo()}")
    print(f"  unmasked count: {col.select('ST_B10').count().reduceRegion(reducer=ee.Reducer.mean(), geometry=region, scale=30, maxPixels=1e9).getInfo()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())