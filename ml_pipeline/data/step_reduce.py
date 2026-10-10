"""Find where the band count goes to zero, one step at a time.

Run: .venv/bin/python -m ml_pipeline.data.step_reduce
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import ee  # type: ignore

BBOX = [73.7318, 18.3856, 74.0183, 18.6216]


def nb(img):
    try:
        return img.bandNames().getInfo()
    except Exception as exc:  # noqa: BLE001
        return f"ERR {str(exc)[:90]}"


def main() -> int:
    ee.Initialize()
    region = ee.Geometry.Rectangle(BBOX, proj="EPSG:4326", geodesic=False)

    col = (
        ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
        .filterDate("2024-01-01", "2025-01-01")
        .filterBounds(region)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60))
    )
    print(f"collection size          : {col.size().getInfo()}")
    first = col.first()
    print(f"first bands              : {nb(first)}")

    qa = first.select("QA_PIXEL")
    print(f"QA_PIXEL bands           : {nb(qa)}")

    mask = qa.bitwiseAnd(int("11111110", 2)).eq(0)
    print(f"mask bands               : {nb(mask)}")

    masked = first.updateMask(mask)
    print(f"after updateMask bands   : {nb(masked)}")

    # The real question: does the mask survive an image-level op?
    scaled = masked.select("ST_B10").multiply(0.00341802)
    print(f"after multiply bands     : {nb(scaled)}")

    added = scaled.add(149.0)
    print(f"after add bands          : {nb(added)}")

    subbed = added.subtract(273.15)
    print(f"after subtract bands     : {nb(subbed)}")

    # Map over the whole collection with the mask, then mean.
    mapped = col.map(lambda im: im.updateMask(im.select("QA_PIXEL").bitwiseAnd(int("11111110", 2)).eq(0)))
    print(f"mapped collection size   : {mapped.size().getInfo()}")
    m1 = mapped.first()
    print(f"mapped first bands       : {nb(m1)}")

    mmean = mapped.select("ST_B10").mean()
    print(f"mapped mean bands        : {nb(mmean)}")

    # The likely culprit: mask band name collision. Check band count explicitly.
    print()
    print("unmasked mean for comparison:")
    u = col.select("ST_B10").mean()
    print(f"  bands: {nb(u)}")
    print(f"  value at pt: "
          f"{u.reduceRegion(reducer=ee.Reducer.first(), geometry=ee.Geometry.Point([73.8475, 18.5209]), scale=30, maxPixels=1e9).getInfo()}")

    print()
    print("masked mean, sampling at the SAME point:")
    try:
        print(f"  {mmean.reduceRegion(reducer=ee.Reducer.first(), geometry=ee.Geometry.Point([73.8475, 18.5209]), scale=30, maxPixels=1e9).getInfo()}")
    except Exception as exc:  # noqa: BLE001
        print(f"  ERR {str(exc)[:150]}")

    print()
    print("band count of masked image (per-image, not collection):")
    try:
        print(f"  masked.bandNames: {nb(masked)}")
        print(f"  masked size: {masked.get('system:band_names', None)}")
    except Exception as exc:  # noqa: BLE001
        print(f"  ERR {str(exc)[:120]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())