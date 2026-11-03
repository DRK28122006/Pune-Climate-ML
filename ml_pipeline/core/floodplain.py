"""Standalone floodplain / watercourse-exposure helpers.

Pure functions. No scoring integration. No file reads at import time. No
synthetic polygons: if no layer is available the helpers return an explicit
UNAVAILABLE record.

Dependencies: shapely and pyproj (already project dependencies). If shapely
is missing the module fails loudly rather than hand-rolling point-in-polygon
on lat/lon degrees.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from shapely.geometry import LineString, Point, shape
    _SHAPELY_OK = True
except Exception:  # pragma: no cover - import-time guard
    _SHAPELY_OK = False
    LineString = None  # type: ignore
    Point = None  # type: ignore
    shape = None  # type: ignore

try:
    from pyproj import Transformer
    _PYPROJ_OK = True
except Exception:  # pragma: no cover
    _PYPROJ_OK = False
    Transformer = None  # type: ignore

UTM_CRS = "EPSG:32643"
WGS_CRS = "EPSG:4326"
DEFAULT_SOURCE = "osm-overpass-2026-11-03"
DEFAULT_LICENCE = "ODbL-1.0"


def _ensure_deps() -> None:
    if not _SHAPELY_OK:
        raise RuntimeError(
            "shapely is required for floodplain helpers but is not installed. "
            "Install shapely (already a project dependency) before calling."
        )
    if not _PYPROJ_OK:
        raise RuntimeError(
            "pyproj is required for floodplain helpers but is not installed."
        )


def _candidate_db_paths(layer_path: Optional[str]) -> List[Path]:
    if layer_path:
        return [Path(layer_path)]
    out: List[Path] = []
    # cwd-relative
    out.append(Path("ml_pipeline") / "data" / "flood_layers.sqlite")
    # relative to this file (ml_pipeline/core -> repo root)
    here = Path(__file__).resolve()
    out.append(here.parents[2] / "ml_pipeline" / "data" / "flood_layers.sqlite")
    out.append(here.parents[1] / "data" / "flood_layers.sqlite")
    return out


def _resolve_db(layer_path: Optional[str]) -> Optional[Path]:
    for p in _candidate_db_paths(layer_path):
        if p.exists():
            return p
    return None


def _transformer() -> Any:
    _ensure_deps()
    return Transformer.from_crs(WGS_CRS, UTM_CRS, always_xy=True)


def _project_point(lon: float, lat: float, tr: Any) -> Tuple[float, float]:
    x, y = tr.transform(lon, lat)
    return float(x), float(y)


def _normalize_geometry(geometry_json: Any) -> List[List[Tuple[float, float]]]:
    """Return a list of linestrings, each a list of (lon,lat) tuples."""
    if not geometry_json:
        return []
    # Point geometry (single pair) -> no line
    if isinstance(geometry_json, list) and len(geometry_json) == 2 and all(
        isinstance(v, (int, float)) for v in geometry_json
    ):
        return []
    # LineString: [[lon,lat], ...]
    if isinstance(geometry_json, list) and geometry_json and isinstance(
        geometry_json[0], (list, tuple)
    ) and len(geometry_json[0]) == 2 and isinstance(geometry_json[0][0], (int, float)):
        return [[(float(p[0]), float(p[1])) for p in geometry_json]]
    # MultiLineString: [[[lon,lat],...], ...]
    if isinstance(geometry_json, list) and geometry_json and isinstance(
        geometry_json[0], (list, tuple)
    ) and geometry_json[0] and isinstance(geometry_json[0][0], (list, tuple)):
        out = []
        for seg in geometry_json:
            if seg and isinstance(seg[0], (list, tuple)):
                out.append([(float(p[0]), float(p[1])) for p in seg])
        return out
    return []


def _nearest_watercourse(
    lon: float, lat: float, db_path: Path
) -> Tuple[Optional[float], Optional[str], Optional[str], Optional[int]]:
    """Return (distance_m, kind, name, osm_id) for the nearest waterway, or None."""
    _ensure_deps()
    tr = _transformer()
    px, py = _project_point(lon, lat, tr)
    point = Point(px, py)
    best: Optional[Tuple[float, str, Optional[str], int]] = None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return None, None, None, None
    try:
        for osm_id, kind, name, geom_json in conn.execute(
            "SELECT id, kind, name, geometry_json FROM waterways"
        ):
            try:
                geom = json.loads(geom_json)
            except (json.JSONDecodeError, TypeError):
                continue
            for seg in _normalize_geometry(geom):
                if len(seg) < 2:
                    continue
                try:
                    xs, ys = zip(*[tr.transform(lo, la) for lo, la in seg])
                    line = LineString(list(zip(xs, ys)))
                except Exception:
                    continue
                if line.is_empty:
                    continue
                d = float(line.distance(point))
                if best is None or d < best[0]:
                    best = (d, kind, name, int(osm_id))
    finally:
        conn.close()
    if best is None:
        return None, None, None, None
    return best


def _table_exists(db_path: Path, table: str) -> bool:
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return False
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _waterways_count(db_path: Path) -> int:
    if not _table_exists(db_path, "waterways"):
        return 0
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return 0
    try:
        return int(conn.execute("SELECT COUNT(*) FROM waterways").fetchone()[0])
    except sqlite3.Error:
        return 0
    finally:
        conn.close()


def _read_meta(db_path: Path, key: str) -> Optional[str]:
    if not _table_exists(db_path, "meta"):
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def watercourse_distance_m(
    lon: float, lat: float, layer_path: Optional[str] = None
) -> Dict[str, Any]:
    """Nearest watercourse distance from (lon,lat), or an explicit UNAVAILABLE record."""
    db_path = _resolve_db(layer_path)
    if db_path is None:
        return {
            "status": "UNAVAILABLE",
            "nearest_watercourse_m": None,
            "watercourse_kind": None,
            "watercourse_name": None,
            "source": None,
            "licence": None,
            "confidence": "none",
            "note": "flood_layers.sqlite not found; no watercourse layer available.",
        }
    count = _waterways_count(db_path)
    if count == 0:
        return {
            "status": "UNAVAILABLE",
            "nearest_watercourse_m": None,
            "watercourse_kind": None,
            "watercourse_name": None,
            "source": None,
            "licence": None,
            "confidence": "none",
            "note": "waterways table empty or missing in flood layer.",
        }
    dist, kind, name, osm_id = _nearest_watercourse(lon, lat, db_path)
    source = _read_meta(db_path, "source") or DEFAULT_SOURCE
    licence = _read_meta(db_path, "licence") or DEFAULT_LICENCE
    if dist is None:
        return {
            "status": "UNAVAILABLE",
            "nearest_watercourse_m": None,
            "watercourse_kind": None,
            "watercourse_name": None,
            "source": source,
            "licence": licence,
            "confidence": "none",
            "note": "No computable watercourse geometry in layer.",
        }
    return {
        "status": "PROXIMITY_ONLY",
        "nearest_watercourse_m": round(float(dist), 1),
        "watercourse_kind": kind,
        "watercourse_name": name,
        "source": source,
        "licence": licence,
        "confidence": "low",
        "note": (
            "Nearest OSM watercourse distance (proximity only); "
            "not proof of inundation."
        ),
    }


def floodplain_status(
    lon: float, lat: float, layer_path: Optional[str] = None
) -> Dict[str, Any]:
    """Floodplain-exposure record, or an explicit UNAVAILABLE record.

    With only OSM watercourse proximity available this returns status
    PROXIMITY_ONLY and in_floodplain=None: proximity is not inundation.
    """
    db_path = _resolve_db(layer_path)
    if db_path is None:
        return {
            "status": "UNAVAILABLE",
            "in_floodplain": None,
            "nearest_watercourse_m": None,
            "source": None,
            "licence": None,
            "confidence": "none",
            "note": "flood_layers.sqlite not found; no floodplain layer available.",
        }
    count = _waterways_count(db_path)
    source = _read_meta(db_path, "source") or DEFAULT_SOURCE
    licence = _read_meta(db_path, "licence") or DEFAULT_LICENCE
    # nearest watercourse (proximity) if available
    nearest = None
    if count > 0:
        d, kind, name, osm_id = _nearest_watercourse(lon, lat, db_path)
        nearest = None if d is None else round(float(d), 1)

    # Extent-based determination is not available in this layer (OSM is
    # proximity only). If a future floodplain_extents table exists, use it.
    if _table_exists(db_path, "floodplain_extents"):
        # Optional support for a future regulatory extent layer.  The current
        # OSM-only layer has no such table, so this path is dormant.
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        except sqlite3.Error:
            conn = None
        in_fp = False
        extent_rows = 0
        status = "UNAVAILABLE"
        conf = "none"
        if conn is not None:
            try:
                extent_rows = int(
                    conn.execute("SELECT COUNT(*) FROM floodplain_extents").fetchone()[0]
                )
                if extent_rows > 0:
                    for row in conn.execute(
                        "SELECT status, geometry_json, source, licence, confidence "
                        "FROM floodplain_extents"
                    ):
                        st, gj, src, lic, cf = row
                        try:
                            geom = json.loads(gj)
                        except (json.JSONDecodeError, TypeError):
                            continue
                        try:
                            shp = shape(geom) if isinstance(geom, dict) else None
                        except Exception:
                            shp = None
                        if shp is None:
                            continue
                        # The extent geometry is stored in lon/lat, so the
                        # containment test uses the lon/lat point directly.
                        if shp.contains(Point(lon, lat)) or shp.covers(Point(lon, lat)):
                            in_fp = True
                            status = str(st)
                            source = src or source
                            licence = lic or licence
                            conf = cf or "medium"
                            break
                if not in_fp:
                    status = "PROXIMITY_ONLY" if count > 0 else "UNAVAILABLE"
            finally:
                conn.close()
        return {
            "status": status,
            "in_floodplain": bool(in_fp) if extent_rows > 0 else None,
            "nearest_watercourse_m": nearest,
            "source": source,
            "licence": licence,
            "confidence": conf if in_fp else ("low" if count > 0 else "none"),
            "note": (
                "Extent layer check performed."
                if in_fp
                else (
                    "No floodplain extent contains this point."
                    if extent_rows > 0
                    else "Floodplain extent table is empty; proximity only."
                )
            ),
        }

    # Default: proximity only, no inundation determination.
    if count > 0:
        return {
            "status": "PROXIMITY_ONLY",
            "in_floodplain": None,
            "nearest_watercourse_m": nearest,
            "source": source,
            "licence": licence,
            "confidence": "low",
            "note": (
                "OSM watercourse proximity only; not an inundation extent. "
                "Proximity is a risk signal, not proof the parcel floods."
            ),
        }
    return {
        "status": "UNAVAILABLE",
        "in_floodplain": None,
        "nearest_watercourse_m": None,
        "source": None,
        "licence": None,
        "confidence": "none",
        "note": "No watercourse layer available.",
    }