"""Derive a deterministic cell-scale slope band from the epoch cube.

The cube already carries `elevation_m` for all 864 cells but no slope.  This
script turns that elevation field into `mean_slope_deg` with a central (or
one-sided, at the grid edge) finite difference on the WGS84 ellipsoid, and
writes `ml_pipeline/data/slope_band.json`.

Why a derived lower bound, not a measured slope
-----------------------------------------------
Each cube cell is a ~1 km mean elevation.  Local relief inside a cell is
smoothed away, so the resulting slope is a LOWER BOUND on parcel-scale slope.
It is not a substitute for a 30 m DEM on a steep site.  That limitation is
recorded in the band's provenance and must travel with every use of it.

Determinism
-----------
Same cube in, same band out.  The only non-deterministic field is
`provenance.generated_at_utc`; `--generated-at` makes it injectable so a test
can run the derivation twice and compare byte-for-byte.

Run:
    .venv/bin/python ml_pipeline/data/derive_slope.py
    .venv/bin/python ml_pipeline/data/derive_slope.py --generated-at 2026-11-03T00:00:00+00:00
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

SOURCE_CUBE = REPO / "ml_pipeline" / "data" / "epoch_cube.json"
OUT = REPO / "ml_pipeline" / "data" / "slope_band.json"

METHOD = "finite_difference_from_cell_elevation"
METHOD_LABEL = "CELL_SCALE_DERIVED_LOWER_BOUND"
SPACING_LABEL = "geodesic via pyproj.Geod(WGS84)"

CAVEATS = [
    "1 km cell-mean elevation smooths local relief.",
    "The result is a lower bound on parcel-scale slope.",
    "Not a substitute for a 30 m DEM on steep sites.",
]

# A slope above this on a 535-1031 m city cube means the derivation is broken,
# not that Pune has a cliff.  Refuse to write a band that fails this check.
IMPLAUSIBLE_MAX_DEG = 45.0


# -------------------------------------------------------------------------
# Geodesy
# -------------------------------------------------------------------------


def geodesic_distance_m(
    lon1: float,
    lat1: float,
    lon2: float,
    lat2: float,
    geod: Optional[Any] = None,
) -> float:
    """Geodesic distance between two lon/lat points, in metres.

    Uses pyproj's WGS84 ellipsoid rather than a degrees-to-metres constant.
    One degree of longitude at Pune's latitude is about 5% shorter than one
    degree of latitude; hard-coding 111.32 km would bias the east-west slope.
    """
    if geod is None:
        from pyproj import Geod

        geod = Geod(ellps="WGS84")
    _, _, distance = geod.inv(float(lon1), float(lat1), float(lon2), float(lat2))
    return float(distance)


# -------------------------------------------------------------------------
# Grid derivation
# -------------------------------------------------------------------------


def _parse_key(key: str) -> Tuple[float, float]:
    lon_s, lat_s = key.split("_")
    return float(lon_s), float(lat_s)


def _grid_axes(keys: Sequence[str]) -> Tuple[List[float], List[float]]:
    lons = sorted({_parse_key(k)[0] for k in keys})
    lats = sorted({_parse_key(k)[1] for k in keys})
    return lons, lats


def _quantile(values: Sequence[float], q: float) -> Optional[float]:
    """Deterministic linear-interpolation quantile (Hyndman-Fan type 7).

    Implemented locally so the band does not depend on numpy and so the
    definition is explicit in one place.  `q` is clamped to [0, 1].
    """
    if not values:
        return None
    xs = sorted(float(v) for v in values)
    if len(xs) == 1:
        return xs[0]
    q = min(1.0, max(0.0, float(q)))
    pos = (len(xs) - 1) * q
    low = int(math.floor(pos))
    high = int(math.ceil(pos))
    if low == high:
        return xs[low]
    frac = pos - low
    return xs[low] * (1.0 - frac) + xs[high] * frac


def derive_slope_cells(
    elevations: Dict[str, Optional[float]],
    geod: Optional[Any] = None,
) -> Dict[str, Optional[float]]:
    """Derive `mean_slope_deg` for every cell in an in-memory elevation grid.

    `elevations` maps a `"{lon}_{lat}"` cell key to metres.  The axes are
    inferred from the keys, so this works for the real 32x27 cube and for the
    small test grids.  No smoothing, filling, interpolation or extrapolation.

    Rules:
      * central difference when both opposite neighbours exist;
      * the central difference divides by the full neighbour-to-neighbour
        distance, not twice the one-step spacing, so a missing row/column
        cannot inflate the gradient;
      * one-sided difference at a grid edge;
      * use the one available axis when the other has no neighbours;
      * `None` when neither axis has a neighbour (a hole, not flat ground).
    """
    if geod is None:
        geod = _geod()

    keys = [k for k, z in elevations.items() if z is not None]
    if not keys:
        return {k: None for k in elevations}

    # Build the axes from EVERY key, including cells whose elevation is None.
    # Dropping a missing column would collapse the grid and make the remaining
    # neighbours look adjacent when they are two steps apart.
    lons, lats = _grid_axes(list(elevations.keys()))
    lon_index = {lon: i for i, lon in enumerate(lons)}
    lat_index = {lat: i for i, lat in enumerate(lats)}

    # Coordinate -> exact key.  Keeping the original strings avoids assuming
    # a particular float formatting and makes missing cells explicit.
    coord_key: Dict[Tuple[float, float], str] = {}
    for key in elevations:
        try:
            coord_key[_parse_key(key)] = key
        except (ValueError, AttributeError):
            continue

    out: Dict[str, Optional[float]] = {}

    for key, z in elevations.items():
        if z is None:
            out[key] = None
            continue
        try:
            lon, lat = _parse_key(key)
            i = lon_index[lon]
            j = lat_index[lat]
        except (ValueError, KeyError, AttributeError):
            out[key] = None
            continue

        # --- east-west derivative -------------------------------------
        # A neighbour whose elevation is None is not usable, exactly like an
        # absent key.  Treat both as missing rather than averaging in a hole.
        left_key = coord_key.get((lons[i - 1], lat)) if i > 0 else None
        right_key = coord_key.get((lons[i + 1], lat)) if i + 1 < len(lons) else None
        if left_key is not None and elevations[left_key] is None:
            left_key = None
        if right_key is not None and elevations[right_key] is None:
            right_key = None
        dzdx: Optional[float] = None
        if left_key is not None and right_key is not None:
            zl = elevations[left_key]
            zr = elevations[right_key]
            # General central difference: divide by the actual distance
            # between the two neighbours.  On a uniform grid this equals
            # 2 * one step; across a gap it does not.
            dx_left = geodesic_distance_m(lons[i - 1], lat, lon, lat, geod)
            dx_right = geodesic_distance_m(lon, lat, lons[i + 1], lat, geod)
            dzdx = (float(zr) - float(zl)) / (dx_left + dx_right)
        elif right_key is not None:
            zr = elevations[right_key]
            dx = geodesic_distance_m(lon, lat, lons[i + 1], lat, geod)
            dzdx = (float(zr) - float(z)) / dx
        elif left_key is not None:
            zl = elevations[left_key]
            dx = geodesic_distance_m(lons[i - 1], lat, lon, lat, geod)
            dzdx = (float(z) - float(zl)) / dx

        # --- north-south derivative -----------------------------------
        below_key = coord_key.get((lon, lats[j - 1])) if j > 0 else None
        above_key = (
            coord_key.get((lon, lats[j + 1])) if j + 1 < len(lats) else None
        )
        if below_key is not None and elevations[below_key] is None:
            below_key = None
        if above_key is not None and elevations[above_key] is None:
            above_key = None
        dzdy: Optional[float] = None
        if below_key is not None and above_key is not None:
            zb = elevations[below_key]
            za = elevations[above_key]
            dy_below = geodesic_distance_m(lon, lats[j - 1], lon, lat, geod)
            dy_above = geodesic_distance_m(lon, lat, lon, lats[j + 1], geod)
            dzdy = (float(za) - float(zb)) / (dy_below + dy_above)
        elif above_key is not None:
            za = elevations[above_key]
            dy = geodesic_distance_m(lon, lat, lon, lats[j + 1], geod)
            dzdy = (float(za) - float(z)) / dy
        elif below_key is not None:
            zb = elevations[below_key]
            dy = geodesic_distance_m(lon, lats[j - 1], lon, lat, geod)
            dzdy = (float(z) - float(zb)) / dy

        if dzdx is None and dzdy is None:
            out[key] = None
            continue

        gx = dzdx if dzdx is not None else 0.0
        gy = dzdy if dzdy is not None else 0.0
        slope_deg = math.degrees(math.atan(math.hypot(gx, gy)))
        slope_deg = min(90.0, max(0.0, slope_deg))
        out[key] = round(slope_deg, 2)

    return out


def _geod() -> Any:
    from pyproj import Geod

    return Geod(ellps="WGS84")


# -------------------------------------------------------------------------
# Provenance and band assembly
# -------------------------------------------------------------------------


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_band(
    cube: Dict[str, Any],
    source_cube: str,
    source_sha256: str,
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Assemble the slope band document from an already-loaded cube."""
    cells = cube.get("cells") or {}
    elevations = {
        key: (cell or {}).get("elevation_m") for key, cell in cells.items()
    }
    slopes = derive_slope_cells(elevations)
    values = [v for v in slopes.values() if v is not None]

    if not values:
        raise SystemExit("FAIL: no cell produced a slope; check elevation_m")

    observed_max = max(values)
    if observed_max > IMPLAUSIBLE_MAX_DEG:
        raise SystemExit(
            f"FAIL: derived slope {observed_max:.2f} deg exceeds "
            f"{IMPLAUSIBLE_MAX_DEG:.0f} deg on a 535-1031 m city cube. "
            "Debug the elevation field or the spacing; refusing to write."
        )

    cell_deg = cube.get("cell_deg")
    lons, lats = _grid_axes(list(cells.keys()))
    grid_label = f"{len(lons)}x{len(lats)}"

    def above(threshold: float) -> int:
        return sum(1 for v in values if v > threshold)

    provenance = {
        "method": METHOD,
        "method_label": METHOD_LABEL,
        "source_cube": source_cube,
        "source_cube_sha256": source_sha256,
        "cell_count": len(cells),
        "cells_with_slope": len(values),
        "grid": grid_label,
        "spacing": SPACING_LABEL,
        "cell_deg": cell_deg,
        "slope_p05_deg": round(_quantile(values, 0.05) or 0.0, 4),
        "slope_median_deg": round(_quantile(values, 0.50) or 0.0, 4),
        "slope_p95_deg": round(_quantile(values, 0.95) or 0.0, 4),
        "slope_max_deg": round(max(values), 4),
        "slope_min_deg": round(min(values), 4),
        "quantile_method": "linear interpolation between order statistics (Hyndman-Fan type 7)",
        "cells_above_1_deg": above(1.0),
        "cells_above_5_deg": above(5.0),
        "cells_above_15_deg": above(15.0),
        "elevation_min_m": round(min(float(z) for z in elevations.values() if z is not None), 4),
        "elevation_max_m": round(max(float(z) for z in elevations.values() if z is not None), 4),
        "generated_at_utc": generated_at
        or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "caveats": list(CAVEATS),
    }

    return {
        "provenance": provenance,
        "cells": {
            key: {"mean_slope_deg": value} for key, value in slopes.items()
        },
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="derive_slope")
    ap.add_argument("--source", default=str(SOURCE_CUBE))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument(
        "--generated-at",
        default=None,
        help="ISO-8601 timestamp for provenance; default is now (UTC)",
    )
    args = ap.parse_args(argv)

    source = Path(args.source)
    if not source.exists():
        print(f"FAIL: no epoch cube at {source}")
        print("Run: .venv/bin/python -m ml_pipeline.data.build_cube --epoch 2024")
        return 1

    raw = source.read_bytes()
    cube = json.loads(raw.decode("utf-8"))
    band = build_band(
        cube,
        source_cube=str(source.relative_to(REPO)) if source.is_relative_to(REPO) else str(source),
        source_sha256=sha256_bytes(raw),
        generated_at=args.generated_at,
    )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(band, indent=2) + "\n")

    p = band["provenance"]
    print("SLOPE BAND DERIVED")
    print(f"  source cube       : {p['source_cube']}")
    print(f"  source sha256     : {p['source_cube_sha256']}")
    print(f"  grid              : {p['grid']}  ({p['cell_count']} cells)")
    print(f"  cells with slope  : {p['cells_with_slope']}")
    print(
        "  distribution (deg): "
        f"min {p['slope_min_deg']:.4f}  p05 {p['slope_p05_deg']:.4f}  "
        f"median {p['slope_median_deg']:.4f}  p95 {p['slope_p95_deg']:.4f}  "
        f"max {p['slope_max_deg']:.4f}"
    )
    print(
        "  cells above       : "
        f"1 deg {p['cells_above_1_deg']}, 5 deg {p['cells_above_5_deg']}, "
        f"15 deg {p['cells_above_15_deg']}"
    )
    print(f"  wrote             : {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
