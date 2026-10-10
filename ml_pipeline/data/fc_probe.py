"""What does reduceRegions actually return? Verify the join key.

Run: .venv/bin/python ml_pipeline/data/fc_probe.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import ee  # type: ignore  # noqa: E402

from ml_pipeline.data.build_cube import BBOX, CELL_DEG, grid_cells  # noqa: E402


def main() -> int:
    ee.Initialize()
    cells = grid_cells()
    print(f"cells: {len(cells)}")

    feats = [
        ee.Feature(
            ee.Geometry.Rectangle(
                [c["lon0"], c["lat0"], c["lon1"], c["lat1"]],
                proj="EPSG:4326",
                geodesic=False,
            ),
            {"id": f"{round(c['centre'][0], 4)}_{round(c['centre'][1], 4)}"},
        )
        for c in cells
    ]
    fc = ee.FeatureCollection(feats)
    print(f"fc size: {fc.size().getInfo()}")

    first = fc.first().getInfo()
    print("\nfeature 'id' (system):", first.get("id"))
    print("feature properties:", json.dumps(first.get("properties"), indent=2))

    # Now a trivial reduce over a constant image: every cell must come back.
    const = ee.Image.constant(7).rename("seven")
    out = const.reduceRegions(
        collection=fc,
        reducer=ee.Reducer.mean(),
        scale=30,
        tileScale=1,
        crs="EPSG:4326",
        maxPixelsPerRegion=1e12,
    )
    info = out.getInfo()
    print(f"\nreduced features: {len(info.get('features', []))}")
    if info.get("features"):
        f0 = info["features"][0]
        print("feature 0 id      :", f0.get("id"))
        print("feature 0 props   :", json.dumps(f0.get("properties"), indent=2))

    # Check the properties survive the reduce (reduceRegions may DROP properties
    # that are not involved in the reduction).
    props = (info["features"][0].get("properties") or {}) if info.get("features") else {}
    print("\n>>> does 'id' survive reduceRegions?", "id" in props)
    print(">>> all keys after reduce:", list(props.keys()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())