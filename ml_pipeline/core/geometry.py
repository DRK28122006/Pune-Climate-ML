"""Geometry normalisation and spatial lookup.

L2 of the pipeline: turn a user polygon into measured facts, and resolve it
against the reference layers.

All area and distance maths happens in EPSG:32643 (WGS 84 / UTM zone 43N).
Degrees are only ever used for storage and point-in-polygon tests.

    .venv/bin/python -c "from ml_pipeline.core.geometry import *"
"""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

REPO = Path(__file__).resolve().parents[2]
REF_DB = REPO / "ml_pipeline" / "data" / "reference_layers.sqlite"
TREE_DB = REPO / "ml_pipeline" / "data" / "tree_index.sqlite"

UTM43N = "EPSG:32643"
EARTH_RADIUS_M = 6_371_008.8

# Citywide census total, used only to state coverage — never to fabricate a count
# for an unloaded ward.
#
# The MEASURED value is 4,009,624: deduplicating the `id` column across all 17
# CSV parts gives 16 x 250,000 + 9,623 with zero duplicate ids. PMC's published
# figure is 4,090,000, which is close but not the same number, and using it here
# silently under-reported coverage as 98.03% instead of ~100% and printed PMC's
# published total next to our own count as if they were the same figure.
#
# The single source of truth is pune.json trees.census_total_city_trees, so this
# value is read from config with the measured figure as the fallback for any
# caller that runs without config available.
_CENSUS_FALLBACK = 4_009_624


def _census_total_city_trees() -> int:
    try:
        cfg_path = REPO / "ml_pipeline" / "config" / "regions" / "pune.json"
        raw = json.loads(cfg_path.read_text())
        return int(raw["trees"]["census_total_city_trees"])
    except Exception:
        return _CENSUS_FALLBACK


CENSUS_TOTAL_CITY_TREES = _census_total_city_trees()

Coord = Tuple[float, float]  # (lon, lat) in WGS84


# ---------------------------------------------------------------------------
# Projection helpers. shapely/pyproj are preferred; a local equirectangular
# fallback keeps the module importable without them, clearly labelled.
# ---------------------------------------------------------------------------

def _have_gdal() -> bool:
    try:
        import pyproj  # type: ignore  # noqa: F401
        import shapely  # type: ignore  # noqa: F401
        return True
    except ImportError:
        return False


def to_utm(coords: Sequence[Coord]) -> List[Tuple[float, float]]:
    """Project lon/lat to EPSG:32643 x/y metres."""
    if not coords:
        return []
    if _have_gdal():
        from pyproj import Transformer  # type: ignore
        tr = Transformer.from_crs("EPSG:4326", UTM43N, always_xy=True)
        return [tr.transform(lon, lat) for lon, lat in coords]
    lat0 = math.radians(sum(c[1] for c in coords) / len(coords))
    # FIX 2026-10-10: the old fallback multiplied by lat0 (radians) an extra
    # time (kx = 111320*cos(lat0)*lat0), shrinking every x/y by ~32x at
    # Pune's latitude. Correct equirectangular approximation. This path runs
    # only when pyproj/shapely are absent; the venv has them, so no live
    # output changes.
    kx = 111_320.0 * math.cos(lat0)
    ky = 110_574.0
    return [(lon * kx, lat * ky) for lon, lat in coords]


HAVE_GDAL: bool = _have_gdal()


def haversine_m(a: Coord, b: Coord) -> float:
    """Great-circle distance in metres. Used for the reported figures."""
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlon, dlat = lon2 - lon1, lat2 - lat1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def polygon_area_m2(ring: Sequence[Coord]) -> float:
    """Area in m2, projected to UTM 43N first."""
    if len(ring) < 3:
        return 0.0
    if _have_gdal():
        from shapely.geometry import Polygon  # type: ignore
        pts = to_utm(ring)
        poly = Polygon(pts)
        if not poly.is_valid:
            poly = poly.buffer(0)
        return float(poly.area) if not poly.is_empty else 0.0
    # Fallback: local planar shoelace on the projected approximation.
    pts = to_utm(ring)
    s = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def polygon_perimeter_m(ring: Sequence[Coord]) -> float:
    if len(ring) < 3:
        return 0.0
    if _have_gdal():
        from shapely.geometry import Polygon  # type: ignore
        pts = to_utm(ring)
        poly = Polygon(pts)
        if not poly.is_valid:
            poly = poly.buffer(0)
        return float(poly.length) if not poly.is_empty else 0.0
    pts = to_utm(ring)
    return sum(
        math.hypot(pts[(i + 1) % len(pts)][0] - pts[i][0],
                   pts[(i + 1) % len(pts)][1] - pts[i][1])
        for i in range(len(pts))
    )


def polygon_centroid(ring: Sequence[Coord]) -> Coord:
    if not ring:
        return (0.0, 0.0)
    if _have_gdal():
        from shapely.geometry import Polygon  # type: ignore
        poly = Polygon(to_utm(ring))
        if not poly.is_valid:
            poly = poly.buffer(0)
        if not poly.is_empty:
            from pyproj import Transformer  # type: ignore
            back = Transformer.from_crs(UTM43N, "EPSG:4326", always_xy=True)
            lon, lat = back.transform(poly.centroid.x, poly.centroid.y)
            return (float(lon), float(lat))
    return (
        sum(p[0] for p in ring) / len(ring),
        sum(p[1] for p in ring) / len(ring),
    )


def bbox_of(ring: Sequence[Coord]) -> Tuple[float, float, float, float]:
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    return (min(lons), min(lats), max(lons), max(lats))


def point_in_polygon(pt: Coord, ring: Sequence[Coord]) -> bool:
    """Ray casting. Boundary behaviour is unspecified but deterministic."""
    x, y = pt
    inside = False
    n = len(ring)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y):
            denom = yj - yi
            if denom != 0 and x < (xj - xi) * (y - yi) / denom + xi:
                inside = not inside
        j = i
    return inside


def compactness(area_m2: float, perimeter_m: float) -> float:
    """4*pi*A / P^2. 1.0 is a circle; lower is more sprawling."""
    if perimeter_m <= 0:
        return 0.0
    return min(1.0, (4.0 * math.pi * area_m2) / (perimeter_m ** 2))


# ---------------------------------------------------------------------------
# Site facts
# ---------------------------------------------------------------------------

@dataclass
class SiteGeometry:
    ring: List[Coord]
    area_m2: float = 0.0
    perimeter_m: float = 0.0
    centroid: Coord = (0.0, 0.0)
    bbox: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    compactness: float = 0.0
    vertex_count: int = 0
    crs_used: str = UTM43N
    centroid_method: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "area_m2": round(self.area_m2, 1),
            "area_km2": round(self.area_m2 / 1e6, 4),
            "perimeter_m": round(self.perimeter_m, 1),
            "centroid_lon": round(self.centroid[0], 6),
            "centroid_lat": round(self.centroid[1], 6),
            "bbox": [round(v, 6) for v in self.bbox],
            "compactness": round(self.compactness, 4),
            "vertex_count": self.vertex_count,
            "crs_used": self.crs_used,
            "area_method": self.centroid_method,
        }


def normalise_site(ring: Sequence[Coord]) -> SiteGeometry:
    """L2. Measure the polygon. Areas and distances in EPSG:32643."""
    pts = [(float(a), float(b)) for a, b in ring]
    area = polygon_area_m2(pts)
    perim = polygon_perimeter_m(pts)
    return SiteGeometry(
        ring=pts,
        area_m2=area,
        perimeter_m=perim,
        centroid=polygon_centroid(pts),
        bbox=bbox_of(pts),
        compactness=compactness(area, perim),
        vertex_count=len(pts),
        centroid_method="pyproj+shapely in EPSG:32643" if _have_gdal()
        else "equirectangular fallback (pyproj/shapely unavailable)",
    )


# ---------------------------------------------------------------------------
# Reference layer lookups
# ---------------------------------------------------------------------------

def _connect(db: Path) -> Optional[sqlite3.Connection]:
    if not db.exists():
        return None
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    return conn


def containing_ward(pt: Coord, conn: Optional[sqlite3.Connection] = None) -> Optional[Dict[str, Any]]:
    """Which ward contains this point.

    Resolved by polygon test, NEVER by ward id. The census' own `ward` column
    runs 3..63 and does not correspond to the 1..41 boundary numbering, so any
    join on ward id silently produces the wrong ward.
    """
    own = conn is None
    conn = conn or _connect(REF_DB)
    if conn is None:
        return None
    try:
        for row in conn.execute(
            "SELECT ward_no, name, ring_json, area_m2 FROM wards "
            "WHERE ? BETWEEN bbox_min_lon AND bbox_max_lon "
            "  AND ? BETWEEN bbox_min_lat AND bbox_max_lat",
            (pt[0], pt[1]),
        ):
            ring = json.loads(row["ring_json"])
            if point_in_polygon(pt, ring):
                return {
                    "ward_no": row["ward_no"],
                    "ward_name": row["name"],
                    "ward_area_m2": row["area_m2"],
                }
        return None
    finally:
        if own:
            conn.close()


def _nearest_in(
    conn: sqlite3.Connection,
    table: str,
    pt: Coord,
    limit: int,
    radius_m: float,
) -> List[Dict[str, Any]]:
    """Nearest features in a bbox-filtered table, by true distance."""
    min_lon, min_lat, max_lon, max_lat = bbox_of([pt])
    # Pre-filter generously in degrees, then measure precisely.
    pad = radius_m / 100_000.0 + 0.01
    rows = conn.execute(
        f"SELECT id, name, centroid_lon, centroid_lat FROM {table} "
        f"WHERE centroid_lon BETWEEN ? AND ? AND centroid_lat BETWEEN ? AND ?",
        (min_lon - pad, max_lon + pad, min_lat - pad, max_lat + pad),
    ).fetchall()

    out = []
    for r in rows:
        d = haversine_m(pt, (r["centroid_lon"], r["centroid_lat"]))
        if d <= radius_m:
            out.append({"id": r["id"], "name": r["name"], "distance_m": round(d, 1)})
    out.sort(key=lambda x: x["distance_m"])
    return out[:limit]


def drainage_context(pt: Coord, radius_m: float = 600.0) -> Dict[str, Any]:
    """Engineered drainage AND natural watercourses, kept strictly apart.

    This separation is the whole point. Distance to an engineered stormwater
    outfall lowers flood risk; distance to a nalla or river raises it. A single
    blended "distance to water" feature inverts the sign of the flood factor
    depending on which layer happens to be nearest.
    """
    conn = _connect(REF_DB)
    if conn is None:
        return {
            "available": False,
            "reason": f"Reference layers not built at {REF_DB}",
            "dist_to_storm_drain_m": None,
            "nalla_context": {"available": False},
            "river_context": {"available": False},
        }

    try:
        drains = _nearest_in(conn, "storm_drains", pt, limit=3, radius_m=radius_m)
        nallas = _nearest_in(conn, "nallas", pt, limit=3, radius_m=radius_m)
        rivers = _nearest_in(conn, "rivers", pt, limit=2, radius_m=radius_m)

        nearest_drain = drains[0]["distance_m"] if drains else None
        nearest_nalla = nallas[0]["distance_m"] if nallas else None
        nearest_river = rivers[0]["distance_m"] if rivers else None

        # Flood-plain exposure: how close is the nearest NATURAL watercourse.
        if nearest_nalla is None and nearest_river is None:
            exposure = None
            exposure_note = "No nalla or river within the search radius."
        else:
            nearest_natural = min(
                [d for d in (nearest_nalla, nearest_river) if d is not None]
            )
            exposure = nearest_natural
            exposure_note = (
                f"Nearest natural watercourse {nearest_natural:.0f} m. Proximity to a "
                f"nala or river is flood-plain EXPOSURE and raises risk. It must "
                f"never be used as a drainage benefit."
            )

        return {
            "available": True,
            "search_radius_m": radius_m,
            "dist_to_storm_drain_m": nearest_drain,
            "storm_drains": drains,
            "storm_drain_note": "Engineered outfall. Proximity LOWERS flood score.",
            "nalla_context": {
                "available": bool(nallas),
                "nearest_m": nearest_nalla,
                "features": nallas,
            },
            "river_context": {
                "available": bool(rivers),
                "nearest_m": nearest_river,
                "features": rivers,
            },
            "nearest_natural_water_m": exposure,
            "flood_plain_note": exposure_note,
        }
    finally:
        conn.close()


def parks_near(pt: Coord, radius_m: float = 1500.0, limit: int = 50) -> List[Dict[str, Any]]:
    """Parks within a radius, with area and ward. Input to the siting engine."""
    conn = _connect(REF_DB)
    if conn is None:
        return []
    try:
        min_lon, min_lat, max_lon, max_lat = bbox_of([pt])
        pad = radius_m / 100_000.0 + 0.01
        rows = conn.execute(
            "SELECT park_id, name, area_m2, centroid_lon, centroid_lat "
            "FROM parks WHERE centroid_lon BETWEEN ? AND ? AND centroid_lat BETWEEN ? AND ?",
            (min_lon - pad, max_lon + pad, min_lat - pad, max_lat + pad),
        ).fetchall()
        out = []
        for r in rows:
            d = haversine_m(pt, (r["centroid_lon"], r["centroid_lat"]))
            if d <= radius_m:
                ward = containing_ward((r["centroid_lon"], r["centroid_lat"]), conn)
                out.append(
                    {
                        "park_id": r["park_id"],
                        "name": r["name"],
                        "area_m2": r["area_m2"] or 0.0,
                        "distance_m": round(d, 1),
                        "lon": r["centroid_lon"],
                        "lat": r["centroid_lat"],
                        "ward_no": (ward or {}).get("ward_no"),
                    }
                )
        out.sort(key=lambda x: x["distance_m"])
        return out[:limit]
    finally:
        conn.close()


def census_coverage() -> Dict[str, Any]:
    """How much of the PMC census is actually loaded into the tree index.

    The census ships as 17 CSV parts. Only the parts present on disk are loaded,
    and they are geographic blocks, not a random sample: with one part loaded,
    15 of 41 wards report ZERO trees while holding thousands.

    Consequence for correctness: a tree count of zero from this index means
    "not loaded", never "no trees here". Every tree-derived figure must carry
    this context, and callers must not treat a low count as a low tree density.
    """
    if not TREE_DB.exists():
        return {
            "index_built": False,
            "loaded_trees": 0,
            "census_total_city_trees": CENSUS_TOTAL_CITY_TREES,
            "loaded_fraction_pct": 0.0,
            "wards_covered": 0,
            "wards_total": 41,
            "wards_empty": 41,
            "coverage_complete": False,
        }

    conn = sqlite3.connect(str(TREE_DB))
    try:
        loaded = conn.execute("SELECT COUNT(*) FROM trees").fetchone()[0]
    finally:
        conn.close()

    ref = _connect(REF_DB)
    covered = 0
    empty: List[int] = []
    if ref is not None:
        tree_conn = sqlite3.connect(str(TREE_DB))
        try:
            for ward_no, ring_json in ref.execute(
                "SELECT ward_no, ring_json FROM wards"
            ):
                ring = json.loads(ring_json)
                xs = [p[0] for p in ring]
                ys = [p[1] for p in ring]
                n = tree_conn.execute(
                    "SELECT COUNT(*) FROM trees WHERE lon BETWEEN ? AND ? "
                    "AND lat BETWEEN ? AND ?",
                    (min(xs), max(xs), min(ys), max(ys)),
                ).fetchone()[0]
                if n > 0:
                    covered += 1
                else:
                    empty.append(ward_no)
        finally:
            tree_conn.close()
            ref.close()

    total = CENSUS_TOTAL_CITY_TREES
    return {
        "index_built": True,
        "loaded_trees": loaded,
        "census_total_city_trees": total,
        "loaded_fraction_pct": round(100.0 * loaded / total, 2) if total else 0.0,
        "wards_covered": covered,
        "wards_total": 41,
        "wards_empty": len(empty),
        "wards_empty_list": empty,
        "coverage_complete": covered == 41,
        "warning": (
            None if covered == 41 else
            f"Tree census only {100.0 * loaded / total:.1f}% loaded "
            f"({loaded:,} of {total:,}). {len(empty)} of 41 wards have no loaded "
            f"trees. A zero count in those wards means 'not loaded', not 'no trees'."
        ),
    }


def trees_in_ring(
    ring: Sequence[Coord], db_path: Optional[Path] = None
) -> List[Dict[str, Any]]:
    """Every census tree inside the polygon, via the R-tree then exact test."""
    path = db_path or TREE_DB
    if not path.exists():
        return []
    min_lon, min_lat, max_lon, max_lat = bbox_of(ring)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT t.tree_id, t.lon, t.lat, t.botanical_name, t.girth_cm, t.height_m, "
            "t.canopy_dia_m, t.condition, t.is_rare, t.is_dead "
            "FROM tree_rtree r JOIN trees t ON t.tree_id = r.tree_id "
            "WHERE r.max_lon >= ? AND r.min_lon <= ? AND r.max_lat >= ? AND r.min_lat <= ?",
            (min_lon, max_lon, min_lat, max_lat),
        ).fetchall()
        return [
            dict(r) for r in rows
            if point_in_polygon((r["lon"], r["lat"]), ring)
        ]
    finally:
        conn.close()


def ward_tree_profile(ward_no: int, db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Aggregate census profile for a whole ward, via its polygon."""
    path = db_path or TREE_DB
    ref = _connect(REF_DB)
    if ref is None:
        return {"ward_no": ward_no, "available": False,
                "reason": f"Reference layers not built at {REF_DB}"}
    try:
        # The ward polygon lives in the REFERENCE db, not the tree db.
        row = ref.execute(
            "SELECT ring_json, name, area_m2 FROM wards WHERE ward_no = ?",
            (ward_no,),
        ).fetchone()
        if row is None:
            return {"ward_no": ward_no, "available": False,
                    "reason": f"ward {ward_no} not present in reference layers"}
        ring = json.loads(row[0])
    finally:
        ref.close()

    if not path.exists():
        return {"ward_no": ward_no, "ward_name": row[1], "available": False,
                "reason": f"tree index not built at {path}"}

    trees = trees_in_ring(ring, path)
    total = len(trees)
    girths = sorted(t["girth_cm"] or 0.0 for t in trees)
    canopy = sum(
        math.pi * ((t["canopy_dia_m"] or 0.0) / 2.0) ** 2 for t in trees
    )

    # Summed crowns can exceed the ward area where canopies overlap (dense
    # stands layer crowns over each other), so >100% is a DENSITY index, not
    # a ground fraction. Found live 2026-10-10: ward 35 sums to 103.32%
    # against GEDI mean height 9.96 m (dense low cover, not an error per se).
    # Never feed this uncapped figure to anything expecting a fraction --
    # site scoring caps separately in process_site. Say what it is here.
    cover = round(100.0 * canopy / row[2], 2) if row[2] else 0.0
    # A ward with no loaded trees is a LOADING ARTEFACT, not a finding. The
    # census parts are geographic blocks, so several wards are empty while
    # holding thousands of trees. Say so, rather than reporting "0 trees".
    ward_in_loaded_block = total > 0
    notes: List[str] = []
    if cover > 100.0:
        notes.append(
            f"Summed crown cover is {cover}% -- above the ward area. This "
            f"counts overlapping canopy layers (a density index), not ground "
            f"fraction. Do not read it as 'more than fully covered'."
        )
    if not ward_in_loaded_block:
        notes.append(
            "NO CENSUS DATA LOADED for this ward. This is not a tree-free ward; "
            "the loaded census parts are geographic blocks that do not cover it. "
            "Load the remaining parts (ml_pipeline/cli.py build-data) before "
            "quoting any figure for this ward."
        )

    return {
        "ward_no": ward_no,
        "ward_name": row[1],
        "available": True,
        "ward_area_m2": row[2],
        "trees": total,
        "trees_are_reliable": ward_in_loaded_block,
        "notes": notes,
        "mature_girth60": sum(1 for g in girths if g >= 60),
        "heritage_girth90": sum(1 for g in girths if g >= 90),
        "rare": sum(1 for t in trees if t["is_rare"]),
        "dead": sum(1 for t in trees if t["is_dead"]),
        "median_girth_cm": girths[total // 2] if total else 0.0,
        "canopy_m2": round(canopy, 1),
        "canopy_cover_pct": cover,
        "census_coverage": census_coverage(),
    }
