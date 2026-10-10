"""Why does the cloud filter produce zero Landsat images over Pune?

Landsat 8 revisits every 16 days; Pune is near the edge of the scene swath on
some paths, so a strict CLOUDY_PIXEL_PERCENTAGE cut can remove every candidate.
We measure the actual distribution rather than guess a threshold.

Run: .venv/bin/python -m ml_pipeline.data/cloud_check
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

    for asset in ("LANDSAT/LC08/C02/T1_L2", "LANDSAT/LC09/C02/T1_L2"):
        print(f"\n=== {asset}")
        base = (
            ee.ImageCollection(asset)
            .filterDate("2024-01-01", "2025-01-01")
            .filterBounds(region)
        )
        n = base.size().getInfo()
        print(f"  date+bounds: {n}")

        if n == 0:
            continue

        # Actual cloud values present.
        cc = base.aggregate_array("CLOUDY_PIXEL_PERCENTAGE").getInfo()
        cc_sorted = sorted(x for x in cc if x is not None)
        print(f"  cloud percentiles: min={cc_sorted[0]} "
              f"p25={cc_sorted[len(cc_sorted)//4]} "
              f"median={cc_sorted[len(cc_sorted)//2]} "
              f"p75={cc_sorted[3*len(cc_sorted)//4]} "
              f"max={cc_sorted[-1]}")
        print(f"  under 60: {sum(1 for x in cc if x is not None and x < 60)}")
        print(f"  under 80: {sum(1 for x in cc if x is not None and x < 80)}")
        print(f"  under100: {sum(1 for x in cc if x is not None and x < 100)}")

        dates = base.aggregate_array("system:time_start").getInfo()
        print("  dates:")
        for d in sorted(dates)[:20]:
            import datetime

            print(f"    {datetime.datetime.utcfromtimestamp(d/1000).date()}")

        # Does the thermal band have valid data at a known-clear point?
        pt = ee.Geometry.Point([73.8475, 18.5209])
        first = base.first()
        try:
            v = first.select("ST_B10").reduceRegion(
                reducer=ee.Reducer.first(), geometry=pt, scale=30, maxPixels=1e9
            ).getInfo()
            print(f"  ST_B10 raw at Shivajinagar (first img): {v}")
        except Exception as exc:  # noqa: BLE001
            print(f"  ERR {str(exc)[:120]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())