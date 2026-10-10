"""Why does the multi-scene LST composite produce None?

Single-scene ST_B10 reads fine (measured 44593 -> 28.4 C), but the collection
mean is None. Test each stage: per-scene validity, the merge, and the QA mask.

Run: .venv/bin/python -m ml_pipeline.data.lst_debug
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import ee  # type: ignore

BBOX = [73.7318, 18.3856, 74.0183, 18.6216]


def main() -> int:
    ee.Initialize()
    region = ee.Geometry.Rectangle(BBOX, proj="EPSG:4326", geodesic=False)

    l8 = (
        ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
        .filterDate("2024-01-01", "2025-01-01")
        .filterBounds(region)
    )
    l9 = (
        ee.ImageCollection("LANDSAT/LC09/C02/T1_L2")
        .filterDate("2024-01-01", "2025-01-01")
        .filterBounds(region)
    )
    print(f"L8={l8.size().getInfo()} L9={l9.size().getInfo()}")

    # Per-scene: does ANY pixel survive unmasked?
    print("\nper-scene ST_B10 unmasked mean over PMC:")
    arr = l8.map(lambda im: im.select("ST_B10")).aggregate_array(
        "system:index"
    ).getInfo()
    for i, idx in enumerate(arr):
        im = ee.Image(f"LANDSAT/LC08/C02/T1_L2/{idx}")
        v = im.select("ST_B10").reduceRegion(
            reducer=ee.Reducer.mean(), geometry=region, scale=30, maxPixels=1e9
        ).getInfo()
        qa = im.select("QA_PIXEL").reduceRegion(
            reducer=ee.Reducer.mean(), geometry=region, scale=30, maxPixels=1e9
        ).getInfo()
        print(f"  {idx}  ST_B10 mean={v}  QA mean={qa}")

    # Now the masked version.
    print("\nper-scene ST_B10 WITH qa mask (mean over PMC):")

    def masked(im):
        q = im.select("QA_PIXEL")
        return im.updateMask(q.bitwiseAnd(int("11111110", 2)).eq(0))

    for i, idx in enumerate(arr):
        im = ee.Image(f"LANDSAT/LC08/C02/T1_L2/{idx}")
        v = masked(im).select("ST_B10").reduceRegion(
            reducer=ee.Reducer.mean(), geometry=region, scale=30, maxPixels=1e9
        ).getInfo()
        print(f"  {idx}  masked mean={v}")

    print("\ncollection mean, masked:")
    m = l8.map(masked).select("ST_B10").mean()
    print(f"  {m.reduceRegion(reducer=ee.Reducer.mean(), geometry=region, scale=30, maxPixels=1e9).getInfo()}")

    print("\ncollection mean, UNMASKED:")
    u = l8.select("ST_B10").mean()
    print(f"  {u.reduceRegion(reducer=ee.Reducer.mean(), geometry=region, scale=30, maxPixels=1e9).getInfo()}")

    print("\nmerged L8+L9 mean, unmasked:")
    merged = l8.merge(l9).select("ST_B10").mean()
    print(f"  {merged.reduceRegion(reducer=ee.Reducer.mean(), geometry=region, scale=30, maxPixels=1e9).getInfo()}")

    print("\ncount of valid pixels (unmasked mean):")
    c = l8.select("ST_B10").count()
    print(f"  {c.reduceRegion(reducer=ee.Reducer.mean(), geometry=region, scale=30, maxPixels=1e9).getInfo()}")

    print("\nST_QA band on first scene:")
    first = l8.first()
    print(f"  ST_QA mean={first.select('ST_QA').reduceRegion(reducer=ee.Reducer.mean(), geometry=region, scale=30, maxPixels=1e9).getInfo()}")

    print("\nQA_PIXEL mask pixel-count over PMC:")
    mm = l8.map(masked).select("ST_B10").count()
    print(f"  {mm.reduceRegion(reducer=ee.Reducer.mean(), geometry=region, scale=30, maxPixels=1e9).getInfo()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())