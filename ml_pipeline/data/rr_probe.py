"""Does the REAL LST image return data through reduceRegions?

reduceCell (reduceRegion, one cell) worked. reduce_extent (reduceRegions, whole
grid) returned 0/864. Is that a join bug or an empty-image bug?

Run: .venv/bin/python ml_pipeline/data/rr_probe.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import ee  # type: ignore  # noqa: E402

from ml_pipeline.data import build_cube as B  # noqa: E402


def main() -> int:
    ee.Initialize()
    cells = B.grid_cells()

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

    lst = B.surface_temperature(2024)
    veg = B.vegetation_indices()
    print(f"lst bands : {lst.bandNames().getInfo()}")
    print(f"veg bands : {veg.bandNames().getInfo()}")

    # A) plain mean through reduceRegions
    print("\n--- A) lst.reduceRegions(mean)")
    a = lst.rename("lst_c").reduceRegions(
        collection=fc, reducer=ee.Reducer.mean(), scale=30,
        tileScale=1, crs="EPSG:4326", maxPixelsPerRegion=1e12,
    ).getInfo()
    fa = a.get("features", [])
    print(f"   features: {len(fa)}")
    if fa:
        vals = [f["properties"].get("lst_c_mean", f["properties"].get("lst_c")) for f in fa]
        got = [v for v in vals if v is not None]
        print(f"   non-null: {len(got)}  sample: {got[:5]}")

    # B) same but no tileScale
    print("\n--- B) lst.reduceRegions(mean) with DEFAULT tileScale")
    b = lst.rename("lst_c").reduceRegions(
        collection=fc, reducer=ee.Reducer.mean(), scale=30,
        crs="EPSG:4326", maxPixelsPerRegion=1e12,
    ).getInfo()
    fb = b.get("features", [])
    print(f"   features: {len(fb)}")
    if fb:
        print(f"   props keys: {list(fb[0]['properties'].keys())}")
        vals = [f["properties"].get("lst_c_mean") for f in fb]
        print(f"   non-null: {sum(1 for v in vals if v is not None)}")

    # C) the exact combined expression from reduce_extent
    print("\n--- C) exact reduce_extent expression")
    lst_src = lst.rename("lst")
    lst_ref_src = lst.updateMask(veg.gt(0.05)).rename("lstref")
    combined = ee.Image.cat([lst_src, lst_ref_src])
    reducer = (
        ee.Reducer.mean()
        .combine(ee.Reducer.max(), sharedInputs=True)
        .combine(ee.Reducer.median(), sharedInputs=True)
    )
    c = combined.reduceRegions(
        collection=fc, reducer=reducer, scale=30,
        tileScale=1, crs="EPSG:4326", maxPixelsPerRegion=1e12,
    ).getInfo()
    fcst = c.get("features", [])
    print(f"   features: {len(fcst)}")
    if fcst:
        print(f"   props keys: {list(fcst[0]['properties'].keys())}")
        print(f"   feature 0: {json.dumps(fcst[0]['properties'], indent=2)[:400]}")

    # D) how big is one feature geometry really?
    print("\n--- D) feature geometry sanity")
    print("   cell 0 corners:", cells[0])
    area = G = ee.FeatureCollection(feats).geometry()
    print("   fc bounds:", fc.geometry().bounds().getInfo()["coordinates"])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())