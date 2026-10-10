"""Does the epoch cube's land-cover partition actually sum to 100%?

Motivation: `area_weighted_cn()` divides by (impervious + vegetation + water),
so it implicitly assumes those three are the whole cell. The cube also carries
a `bare_pct` band that is never passed to the scorer. If the bands do not
partition the cell, the renormalisation is not a small approximation -- it can
inflate the curve number several-fold.

`build_cube.py` computes five Dynamic World classes (trees, built, bare, water,
grass) but stores only four, and `vegetation_pct` comes from NDVI, which is a
different sensor and not a member of that partition. So the suspicion is that
the stored bands are NOT a partition at all.

This asks Earth Engine directly: for a sample of real PMC cells, what are the
five Dynamic World fractions, and do they sum to 1?

Run: .venv/bin/python ml_pipeline/data/partition_check.py
"""

from __future__ import annotations

import json
import os
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

try:
    import ee  # type: ignore
except ImportError:
    print("earthengine-api is not installed in this interpreter.")
    print("Run with: .venv/bin/python ml_pipeline/data/partition_check.py")
    raise SystemExit(2)

BBOX = [73.7318, 18.3856, 74.0183, 18.6216]
CUBE = REPO / "ml_pipeline" / "data" / "epoch_cube.json"


def main() -> int:
    ee.Initialize()
    print("=" * 96)
    print("PARTITION CHECK — do the cube's land-cover bands cover the whole cell?")
    print("=" * 96)

    cells: Dict[str, Any] = json.loads(CUBE.read_text())["cells"]

    # Dynamic World at 10 m. Classes: 0 water, 1 trees, 2 grass, 3 flooded
    # vegetation, 4 crops, 5 shrub/scrub, 6 built, 7 bare, 8 snow.
    dw = (
        ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
        .filterDate("2024-01-01", "2024-12-31")
        .filterBounds(ee.Geometry.Rectangle(BBOX, proj="EPSG:4326", geodesic=False))
    )

    def keep(image: ee.Image) -> ee.Image:
        return image.updateMask(image.select("label").neq(0))

    dw = dw.map(keep)
    # Every Dynamic World class, so the question is answerable rather than
    # assumed. mode selects the most likely class per pixel.
    mode = dw.select("label").mode()
    counts = ee.Image.constant(1).addBands(
        mode.eq(ee.Image.constant(c)).rename(f"is_{c}") for c in range(9)
    ) if False else None  # placeholder, replaced below

    # Build the class indicators as a server-side image.
    indicators = [mode.eq(c).rename(f"is_{c}") for c in range(9)]
    img = ee.Image(indicators).addBands(ee.Image.constant(1).rename("pixels"))
    means = img.reduceRegion(
        reducer=ee.Reducer.mean(), geometry=ee.Geometry.Rectangle(
            BBOX, proj="EPSG:4326", geodesic=False
        ), scale=30, maxPixels=1e9,
    )
    print("  Earth Engine reachable. Querying per-cell is expensive; instead")
    print("  checking a coarse grid over the bbox for the partition property.")
    print()

    # Sample the actual cube cells: build one region per cell and ask for the
    # fraction of each Dynamic World class. A dozen cells is enough to settle
    # whether the bands partition.
    sample_keys = list(cells.keys())
    step = max(1, len(sample_keys) // 12)
    sample_keys = sample_keys[::step][:12]

    labels = {
        0: "water", 1: "trees", 2: "grass", 3: "flooded_veg", 4: "crops",
        5: "shrub", 6: "built", 7: "bare", 8: "snow",
    }

    print(f"  {'cell':<20} {'sum5':>7} {'stored4':>8} {'grass':>7} "
          f"{'cube_built':>10} {'cube_bare':>10}")
    print("  " + "-" * 76)
    stored_sums: List[float] = []
    dw_sums: List[float] = []
    rows = []
    for key in sample_keys:
        lon_s, lat_s = key.split("_")
        lon, lat = float(lon_s), float(lat_s)
        region = ee.Geometry.Point([lon, lat]).buffer(500)
        reducer = ee.Reducer.mean()
        local = img.reduceRegion(
            reducer=reducer, geometry=region, scale=30, maxPixels=1e9
        ).getInfo() or {}
        cls_sum = sum(float(local.get(f"is_{c}", 0.0) or 0.0) for c in range(9))
        grass = float(local.get("is_2", 0.0) or 0.0)
        cell = cells[key]
        stored4 = (
            float(cell.get("built_pct", 0.0))
            + float(cell.get("bare_pct", 0.0))
            + float(cell.get("water_pct", 0.0))
            + float(cell.get("tree_canopy_pct", 0.0))
        )
        dw_sums.append(cls_sum)
        stored_sums.append(stored4)
        rows.append((key, cls_sum, stored4, grass,
                     float(cell.get("built_pct", 0.0)),
                     float(cell.get("bare_pct", 0.0))))
        print(f"  {key:<20} {cls_sum:>7.3f} {stored4:>8.3f} {grass:>7.3f} "
              f"{cell.get('built_pct', 0):>10.3f} {cell.get('bare_pct', 0):>10.3f}")

    print()
    print(f"  Dynamic World 9-class sum : median {statistics.median(dw_sums):.3f} "
          f"(should be 1.000 if the classification is exhaustive)")
    print(f"  cube stored 4-band sum    : median {statistics.median(stored_sums):.3f}")
    print()
    print("  If the 9-class sum is 1.000 but the stored 4-band sum is well below,")
    print("  the cube is dropping real classes -- grass, crops and shrub at")
    print("  minimum -- and the land-cover bands cannot be used as a partition.")
    print("  That makes area_weighted_cn's renormalisation a structural error,")
    print("  not a rounding difference.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())