"""Probe which thermal / land-surface-temperature datasets actually have data
over Pune, and over what dates.

This decides the whole heat layer. Landsat's thermal sensors have been winding
down, so the obvious dataset may be empty for recent years. We ask the archive
itself rather than assume.

Run: .venv/bin/python ml_pipeline/data/probe_cube_sources.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import ee  # type: ignore

# CANDIDATES = (asset_id, label, window_start, window_end)
# Built at call time: ee.Geometry must not be constructed before ee.Initialize(),
# which is why PMC is passed in rather than defined at module scope.

CANDIDATES = [
    (
        "LANDSAT/LC08/C02/T1_L2",
        "Landsat 8 C2 L2 (thermal band ST_B10)",
        "2024-01-01",
        "2025-12-31",
    ),
    (
        "LANDSAT/LC09/C02/T1_L2",
        "Landsat 9 C2 L2 (thermal band ST_B10)",
        "2024-01-01",
        "2025-12-31",
    ),
    (
        "COPERNICUS/S2_SR_HARMONIZED",
        "Sentinel-2 SR (vegetation / NDVI only, no thermal)",
        "2024-01-01",
        "2025-12-31",
    ),
    (
        "ECOSIFEL/GOOGLE/DYNAMICWORLD/V1",
        "Dynamic World V1 (10 m land cover, prob. built/veg/tree/water)",
        "2024-01-01",
        "2025-06-30",
    ),
    (
        "MODIS/061/MOD11A2",
        "MODIS Terra land surface temperature (1 km, 8-day)",
        "2024-01-01",
        "2025-12-31",
    ),
    (
        "USGS/SRTMGL1_003",
        "SRTM 30 m elevation (slope)",
        "2000-01-01",
        "2000-12-31",
    ),
]


def probe(
    pmc, asset_id: str, label: str, start: str, end: str
) -> None:
    print(f"\n=== {label}")
    print(f"    {asset_id}")
    try:
        col = ee.ImageCollection(asset_id)
        probe_col = col.filterDate(start, end).filterBounds(pmc)
        n = probe_col.size().getInfo()
        print(f"    images in {start}..{end} over PMC: {n}")
        if n == 0:
            print("    -> NO DATA for this window")
            return

        bands = probe_col.first().bandNames().getInfo()
        print(f"    bands ({len(bands)}): {bands[:14]}")

        # Most recent acquisition actually available.
        latest = col.filterBounds(pmc).sort("system:time_start", False).first()
        t = latest.date().format("YYYY-MM-dd").getInfo()
        print(f"    latest image over PMC: {t}")

        # Cloud cover is the usual blocker for optical; report the mean.
        if "CLOUDY_PIXEL_PERCENTAGE" in bands:
            cc = col.filterBounds(pmc).filterDate(start, end).mean(
                selector="CLOUDY_PIXEL_PERCENTAGE"
            )
            print(f"    mean cloud cover: {cc.getInfo()}")

    except Exception as exc:  # noqa: BLE001
        print(f"    ERROR: {type(exc).__name__}: {str(exc)[:220]}")


def main() -> int:
    ee.Initialize()
    pmc = ee.Geometry.Rectangle([73.7318, 18.3856, 74.0183, 18.6216])
    print("Earth Engine initialised.")
    print("Probing PMC bbox [73.7318, 18.3856, 74.0183, 18.6216]")
    for asset_id, label, start, end in CANDIDATES:
        try:
            probe(pmc, asset_id, label, start, end)
        except Exception as exc:  # noqa: BLE001
            print(f"\n=== {label}\n    FATAL: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())