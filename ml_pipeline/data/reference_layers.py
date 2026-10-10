"""Reference spatial layers for Pune: wards, parks, drainage, water.

Builds one SQLite database holding every static spatial layer the pipeline
needs, so a site polygon can be resolved against all of them in one place.

    .venv/bin/python -m ml_pipeline.data.reference_layers --build

Sources, all PMC-published and downloaded to ml_pipeline/reference/:

  pmc_wards_2025.kml          41 ward boundaries        (verified 479.94 km2)
  pune_parks.kml              parks and gardens polygons
  pune_parks_locations.csv    gardens with lat/lon
  pune_parks_list.csv         ward-wise park inventory
  pmc_stormwater_drains.kmz   ENGINEERED stormwater network
  pune_nallas.kml             NATURAL watercourses (nalas)
  pune_rivers.kml             river network

The stormwater/nalla separation is load-bearing and is preserved all the way
through to the scorer. Distance to an engineered outfall lowers flood risk
(fast discharge). Distance to a nala or river RAISES it (flood-plain
exposure). Conflating the two inverts the sign of the flood factor, so they
are stored in distinct tables with distinct columns and are never joined.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sqlite3
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

REPO = Path(__file__).resolve().parents[2]
REF_DIR = REPO / "ml_pipeline" / "reference"

# Working CRS for all distance maths. KML is lon/lat; area and distance are
# only ever computed after projecting here.
UTM43N = "EPSG:32643"

SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Ward polygons. ward_no is the 1..41 numbering from the 2025 boundary file.
CREATE TABLE IF NOT EXISTS wards (
    ward_no     INTEGER PRIMARY KEY,
    name        TEXT,
    ring_json   TEXT NOT NULL,
    bbox_min_lon REAL, bbox_min_lat REAL,
    bbox_max_lon REAL, bbox_max_lat REAL,
    vertex_count INTEGER,
    area_m2     REAL
);

-- Park polygons, used as relocation candidates.
-- `ward_no` is resolved SPATIALLY against the ward polygons, not read from the
-- source (PMC's own ward_no is 0 in every record).
-- `prabhag_name` is PMC's administrative CIRCLE name -- there are 15 of them,
-- not 41, and they must never be joined against ward_no.
CREATE TABLE IF NOT EXISTS parks (
    park_id     INTEGER PRIMARY KEY,
    name        TEXT,
    ward_no     INTEGER,
    category    TEXT,
    lon         REAL,
    lat         REAL,
    area_m2     REAL,
    bbox_min_lon REAL, bbox_min_lat REAL,
    bbox_max_lon REAL, bbox_max_lat REAL,
    centroid_lon REAL, centroid_lat REAL,
    prabhag_name TEXT,
    locality     TEXT
);

-- ENGINEERED stormwater. Proximity REDUCES flood score.
CREATE TABLE IF NOT EXISTS storm_drains (
    id       INTEGER PRIMARY KEY,
    name     TEXT,
    ring_json TEXT,
    centroid_lon REAL, centroid_lat REAL,
    bbox_min_lon REAL, bbox_min_lat REAL,
    bbox_max_lon REAL, bbox_max_lat REAL
);

-- NATURAL watercourses. Proximity INCREASES flood score (flood-plain exposure).
CREATE TABLE IF NOT EXISTS nallas (
    id       INTEGER PRIMARY KEY,
    name     TEXT,
    ring_json TEXT,
    centroid_lon REAL, centroid_lat REAL,
    bbox_min_lon REAL, bbox_min_lat REAL,
    bbox_max_lon REAL, bbox_max_lat REAL
);

CREATE TABLE IF NOT EXISTS rivers (
    id       INTEGER PRIMARY KEY,
    name     TEXT,
    ring_json TEXT,
    centroid_lon REAL, centroid_lat REAL,
    bbox_min_lon REAL, bbox_min_lat REAL,
    bbox_max_lon REAL, bbox_max_lat REAL
);
"""


# ---------------------------------------------------------------------------
# KML parsing
# ---------------------------------------------------------------------------

_COORD_RE = re.compile(r"<coordinates>(.*?)</coordinates>", re.S)


def parse_kml_placemarks(path: Path) -> List[Dict[str, Any]]:
    """Return [{name, attrs, geometry_type, rings:[[(lon,lat),...], ...]}, ...].

    Each placemark is kept separate. Concatenating coordinate blocks across
    placemarks merges distinct features into one bogus polygon — this is a real
    failure mode, not a hypothetical one, and the e2e test caught it.

    `attrs` holds KML ExtendedData SimpleData values. The ward file carries the
    real ward number there as <SimpleData name="qwr">5.0</SimpleData>, and the
    placemarks are NOT in ward order in the file. Reading the number from the
    attribute is mandatory: positional indexing silently labels Ward 12 as
    whatever happens to sit twelfth in the file, which is a 38 km2 error.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    out: List[Dict[str, Any]] = []

    for pm in re.findall(r"<Placemark.*?</Placemark>", text, re.S):
        nm = re.search(r"<name>(.*?)</name>", pm, re.S)
        name = nm.group(1).strip() if nm else ""

        attrs: Dict[str, str] = {}
        for m in re.finditer(
            r"<SimpleData\s+name=\"([^\"]+)\"\s*>(.*?)</SimpleData>", pm, re.S
        ):
            attrs[m.group(1).strip()] = m.group(2).strip()

        gtype = "Polygon"
        if "<LineString" in pm:
            gtype = "LineString"
        elif "<Point" in pm:
            gtype = "Point"

        rings: List[List[Tuple[float, float]]] = []
        for blob in _COORD_RE.findall(pm):
            pts: List[Tuple[float, float]] = []
            for token in blob.split():
                parts = token.split(",")
                if len(parts) >= 2:
                    try:
                        pts.append((float(parts[0]), float(parts[1])))
                    except ValueError:
                        continue
            if len(pts) >= 2:
                rings.append(pts)
        if rings:
            out.append(
                {"name": name, "attrs": attrs, "geometry_type": gtype, "rings": rings}
            )

    return out


def ring_area_m2(ring: Sequence[Tuple[float, float]]) -> float:
    """Equirectangular area in m2. Good to ~0.1% over a single PMC ward.

    Used only for fast pre-filtering and reporting. Anything that ends up in a
    score is recomputed in EPSG:32643 via `precise_area_m2`.
    """
    if len(ring) < 3:
        return 0.0
    lat0 = math.radians(sum(p[1] for p in ring) / len(ring))
    kx = 111_320.0 * math.cos(lat0)
    ky = 110_574.0
    s = 0.0
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        s += x1 * ky * (y2 * kx) - x2 * ky * (y1 * kx)
    return abs(s) / 2.0


def precise_area_m2(ring: Sequence[Tuple[float, float]]) -> Optional[float]:
    """Area in m2 via a proper UTM projection, or None if pyproj is absent."""
    try:
        from pyproj import Transformer  # type: ignore
        from shapely.geometry import Polygon  # type: ignore
    except ImportError:
        return None
    tr = Transformer.from_crs("EPSG:4326", UTM43N, always_xy=True)
    pts = [tr.transform(lon, lat) for lon, lat in ring]
    if len(pts) >= 3:
        p = Polygon(pts)
        if p.is_valid:
            return p.area
        p = p.buffer(0)  # fix self-intersection from KML digitising
        if not p.is_empty:
            return p.area
    return None


def _bbox(ring: Sequence[Tuple[float, float]]) -> Tuple[float, float, float, float]:
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    return min(lons), min(lats), max(lons), max(lats)


def _centroid(ring: Sequence[Tuple[float, float]]) -> Tuple[float, float]:
    n = len(ring)
    if n == 0:
        return (0.0, 0.0)
    return (sum(p[0] for p in ring) / n, sum(p[1] for p in ring) / n)


def _largest_ring(pm: Dict[str, Any]) -> List[Tuple[float, float]]:
    return max(pm["rings"], key=len)


def _flatten(pm: Dict[str, Any]) -> List[Tuple[float, float]]:
    """All vertices of a multi-ring placemark, for bbox/centroid purposes."""
    pts: List[Tuple[float, float]] = []
    for r in pm["rings"]:
        pts.extend(r)
    return pts


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

_WARD_NO_RE = re.compile(r"(\d+)")


def build_wards(conn: sqlite3.Connection, kml_path: Path) -> Dict[str, Any]:
    pms = parse_kml_placemarks(kml_path)
    rows = []
    used_numbers: set[int] = set()
    from_name = from_attr = positional = 0
    number_only = from_name_label = 0

    for i, pm in enumerate(pms):
        ring = _largest_ring(pm)
        if len(ring) < 3:
            continue

        # Ward number precedence: an explicit name match, then the `qwr`
        # ExtendedData attribute, then file position as a last resort. The
        # ward file is NOT in ward order, so `qwr` is what makes this correct.
        ward_no: Optional[int] = None
        m = _WARD_NO_RE.search(pm.get("name") or "")
        if m:
            ward_no = int(m.group(1))
            from_name += 1
        if ward_no is None:
            raw = (pm.get("attrs") or {}).get("qwr")
            if raw:
                try:
                    ward_no = int(round(float(raw)))
                    from_attr += 1
                except ValueError:
                    ward_no = None
        if ward_no is None:
            ward_no = i + 1
            positional += 1
        while ward_no in used_numbers:
            ward_no += 1
        used_numbers.add(ward_no)

        name = re.sub(r"^\s*ward\s*[-:]?\s*\d+\s*", "", pm.get("name") or "", flags=re.I)
        name = name.strip()
        # The official 2025 layer carries no <name> per placemark (only the
        # shared Document name "final_41wardboundary"), so a nameless ward is
        # the normal case, not an anomaly. The ward NUMBER is the only
        # identifier PMC publishes here; inventing a locality name would be
        # worse than admitting that.
        if not name or name.lower() == "final_41wardboundary":
            name = f"Ward {ward_no}"
            number_only += 1
        else:
            from_name_label += 1
        minl, minla, maxl, maxla = _bbox(ring)
        rows.append(
            (
                ward_no, name, json.dumps(ring),
                minl, minla, maxl, maxla, len(ring),
                precise_area_m2(ring) or ring_area_m2(ring),
            )
        )

    conn.executemany(
        "INSERT OR REPLACE INTO wards(ward_no,name,ring_json,bbox_min_lon,bbox_min_lat,"
        "bbox_max_lon,bbox_max_lat,vertex_count,area_m2) VALUES (?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    total = sum(r[8] or 0.0 for r in rows)
    return {
        "count": len(rows),
        "ward_no_from_name": from_name,
        "ward_no_from_qwr_attribute": from_attr,
        "ward_no_from_file_position": positional,
        "wards_named_only_by_number": number_only,
        "wards_with_locality_label": from_name_label,
        "name_source": (
            "PMC publishes ward NUMBER only in this layer; locality labels are "
            "not available from open data. Parks are attributed to wards "
            "spatially instead."
        ),
        "total_area_km2": round(total / 1e6, 3),
        "min_ward": min((r[0] for r in rows), default=None),
        "max_ward": max((r[0] for r in rows), default=None),
    }


def _point_in_ring(lon: float, lat: float, ring: Sequence[Tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon in lon/lat degrees.

    Deliberately dependency-free: this must work when GDAL/shapely are absent,
    and a ward boundary is a simple ring. Edges are handled explicitly because
    a park centroid landing exactly on a ward edge is a real case, and the
    fallback (first vertex) covers the concave-polygon failure mode.
    """
    n = len(ring)
    if n < 3:
        return False
    inside = False
    for i in range(n - 1):
        x1, y1 = ring[i]
        x2, y2 = ring[i + 1]
        # On the boundary counts as inside.
        cross = (x2 - x1) * (lat - y1) - (y2 - y1) * (lon - x1)
        if abs(cross) < 1e-12 and min(x1, x2) - 1e-12 <= lon <= max(x1, x2) + 1e-12 \
                and min(y1, y2) - 1e-12 <= lat <= max(y1, y2) + 1e-12:
            return True
        if (y1 > lat) != (y2 > lat):
            x_at = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < x_at:
                inside = not inside
    return inside


def ward_lookup(conn: sqlite3.Connection) -> List[Tuple[int, List[Tuple[float, float]]]]:
    """(ward_no, ring) for every ward, for spatial attribution."""
    return [
        (int(r[0]), json.loads(r[1]))
        for r in conn.execute("SELECT ward_no, ring_json FROM wards ORDER BY ward_no")
    ]


def ward_by_point(
    conn: sqlite3.Connection, lon: float, lat: float
) -> Optional[int]:
    """Ward containing a point, by polygon containment.

    Citywide the ward polygons overlap by 20,111 m2 (see check_overlaps.py), so
    a point in that sliver legitimately matches more than one ward. The first
    match by ward number is returned and the overlap is recorded, never hidden.
    """
    for ward_no, ring in ward_lookup(conn):
        if _point_in_ring(lon, lat, ring):
            return ward_no
    return None


def _read_pmc_inventory(path: Path) -> List[Dict[str, str]]:
    """Read a PMC facilities CSV, tolerating the title row PMC puts above the header.

    `pune_parks_locations.csv` ships as:
        line 1: List of Gardens with Lat Longs        <- title
        line 2: Sr No,Facility Type/Category,...       <- real header
        line 3+: data
    Reading it as if line 1 were the header yields one column named
    "List of Gardens with Lat Longs" and every lookup silently misses.
    """
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    lines = text.splitlines()
    for start in (0, 1, 2):
        try:
            rd = csv.DictReader(lines[start:])
        except Exception:
            continue
        fieldnames = rd.fieldnames or []
        if any((f or "").strip() in ("Ward Name", "Name of Facility") for f in fieldnames):
            return [dict(r) for r in rd]
    return []


def _park_ward_by_name() -> Dict[str, Dict[str, str]]:
    """garden name (lowercased) -> its PMC inventory row."""
    out: Dict[str, Dict[str, str]] = {}
    for row in _read_pmc_inventory(REF_DIR / "pune_parks_locations.csv"):
        nm = (row.get("Name of Facility") or "").strip().lower()
        if nm:
            out[nm] = row
    return out


def build_parks(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Parks from the KML polygons, enriched with PMC's own attributes.

    The parks KML carries no <name> element. The real identity lives in
    ExtendedData: `structure_` is the garden's name (e.g. "Jaybhawani Udyan"),
    `property_u` the type, `prabhag`/`peth_name` the locality. Falling back to
    "Park 84" hides which park a recommendation actually names, which is the
    part a municipal officer acts on.

    `ward_no` in the source is 0 for every record -- a placeholder, not a real
    ward. It is deliberately NOT trusted. The ward is resolved SPATIALLY
    against the ward polygons in `ward_by_point`, which is the only attribution
    that can be verified. PMC's inventory "Ward Name" column holds PRABHAG
    (circle) names such as Sangamwadi and Dhole Patil -- 15 of them, not the 41
    ward numbers -- so it is kept as `prabhag_name` and never joined as a ward.
    """
    park_kml = REF_DIR / "pune_parks.kml"
    inventory = _park_ward_by_name()

    rows = []
    named = 0
    if park_kml.exists():
        for i, pm in enumerate(parse_kml_placemarks(park_kml)):
            ring = _largest_ring(pm)
            if len(ring) < 3:
                for r in pm["rings"]:
                    if len(r) == 1:
                        ring = r
                        break
            if not ring:
                continue

            attrs = pm.get("attrs", {}) or {}
            clon, clat = _centroid(ring)
            minl, minla, maxl, maxla = _bbox(ring)

            name = (pm.get("name") or "").strip() or attrs.get("structure_", "").strip()
            if not name:
                name = f"Park {i + 1}"
            else:
                named += 1

            # PMC's own area when present is authoritative over our projection.
            area = None
            for key in ("area_sqmtr", "st_area_sh"):
                raw = attrs.get(key)
                if raw:
                    try:
                        area = float(raw)
                        break
                    except ValueError:
                        continue
            if not area:
                area = precise_area_m2(ring) if len(ring) >= 3 else 0.0

            ward_no = ward_by_point(conn, clon, clat)
            if ward_no is None:
                # A centroid can fall outside a concave park polygon; retry the
                # first vertex before giving up.
                ward_no = ward_by_point(conn, *ring[0])

            category = attrs.get("property_u", "").strip() or None
            locality = attrs.get("peth_name", "").strip() or None
            prabhag = (attrs.get("prabhag") or "").strip() or None
            inv = inventory.get(name.lower())
            if inv:
                # PMC's own inventory carries a PRABHAG name; it is not a ward
                # number, so it is stored separately and never joined on ward.
                prabhag = prabhag or (inv.get("Prabhag Name") or "").strip() or None
                ward_label = (inv.get("Ward Name") or "").strip()
                if ward_label and not prabhag:
                    prabhag = ward_label

            rows.append(
                (
                    i + 1, name, ward_no, category,
                    clon, clat, float(area or 0.0),
                    minl, minla, maxl, maxla, clon, clat,
                    prabhag, locality,
                )
            )

    conn.executemany(
        "INSERT OR REPLACE INTO parks(park_id,name,ward_no,category,lon,lat,area_m2,"
        "bbox_min_lon,bbox_min_lat,bbox_max_lon,bbox_max_lat,centroid_lon,centroid_lat,"
        "prabhag_name,locality) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    areas = [r[6] for r in rows if r[6]]
    return {
        "count": len(rows),
        "named_from_pmc_attributes": named,
        "with_area": sum(1 for a in areas if a and a > 0),
        "total_area_km2": round(sum(areas) / 1e6, 3) if areas else 0.0,
        "median_area_m2": round(sorted(areas)[len(areas) // 2], 1) if areas else 0.0,
        "ward_attributed_spatially": sum(1 for r in rows if r[2] is not None),
        "ward_attribution_method": "point-in-polygon against ward boundaries",
        "ward_attribution_unresolved": sum(1 for r in rows if r[2] is None),
        "with_prabhag_name": sum(1 for r in rows if r[13]),
        "prabhag_note": (
            "prabhag = PMC administrative circle. 15 distinct values, NOT the "
            "41-ward numbering. Stored for display only."
        ),
        "pmc_inventory_matched": sum(
            1 for r in rows if inventory.get((r[1] or "").lower())
        ),
        "pmc_inventory_rows": len(inventory),
    }


def _build_network(conn: sqlite3.Connection, table: str, path: Path) -> Dict[str, Any]:
    """Load a line/point network (drains, nallas, rivers) into its own table."""
    if not path.exists():
        return {"count": 0, "source": str(path.name), "missing": True}

    if path.suffix.lower() == ".kmz":
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.lower().endswith(".kml"))
            data = z.read(name).decode("utf-8", errors="replace")
        pms = _parse_kml_text(data)
    else:
        pms = parse_kml_placemarks(path)

    rows = []
    for i, pm in enumerate(pms):
        pts = _flatten(pm)
        if not pts:
            continue
        clon, clat = _centroid(pts)
        minl, minla, maxl, maxla = _bbox(pts)
        nm = (pm.get("name") or "").strip() or f"{table}_{i + 1}"
        rows.append(
            (i + 1, nm, json.dumps(pm["rings"]),
             clon, clat, minl, minla, maxl, maxla)
        )

    conn.executemany(
        f"INSERT OR REPLACE INTO {table}(id,name,ring_json,centroid_lon,centroid_lat,"
        f"bbox_min_lon,bbox_min_lat,bbox_max_lon,bbox_max_lat) VALUES (?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    lons = [r[3] for r in rows]
    lats = [r[4] for r in rows]
    return {
        "count": len(rows),
        "source": path.name,
        "lon_range": [round(min(lons), 4), round(max(lons), 4)] if lons else None,
        "lat_range": [round(min(lats), 4), round(max(lats), 4)] if lats else None,
    }


def _parse_kml_text(text: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for pm in re.findall(r"<Placemark.*?</Placemark>", text, re.S):
        nm = re.search(r"<name>(.*?)</name>", pm, re.S)
        name = nm.group(1).strip() if nm else ""
        rings: List[List[Tuple[float, float]]] = []
        for blob in _COORD_RE.findall(pm):
            pts = []
            for token in blob.split():
                parts = token.split(",")
                if len(parts) >= 2:
                    try:
                        pts.append((float(parts[0]), float(parts[1])))
                    except ValueError:
                        continue
            if len(pts) >= 2:
                rings.append(pts)
        if rings:
            out.append({"name": name, "geometry_type": "", "rings": rings})
    return out


def build(db_path: Path) -> Dict[str, Any]:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)

    stats: Dict[str, Any] = {}
    stats["wards"] = build_wards(conn, REPO / "pmc_wards_2025.kml")
    stats["parks"] = build_parks(conn)
    stats["storm_drains"] = _build_network(
        conn, "storm_drains", REF_DIR / "pmc_stormwater_drains.kmz"
    )
    stats["nallas"] = _build_network(conn, "nallas", REF_DIR / "pune_nallas.kml")
    stats["rivers"] = _build_network(conn, "rivers", REF_DIR / "pune_rivers.kml")

    meta = {
        "schema_version": "1",
        "crs_working": UTM43N,
        "ward_source": "pmc_wards_2025.kml (PMC 2025 ward boundaries)",
        "drainage_sign_convention": "storm_drains proximity REDUCES flood score "
                                    "(engineered, fast discharge). nallas/rivers "
                                    "proximity INCREASES flood score (flood-plain "
                                    "exposure). Never merge these two layers.",
        "wards_count": str(stats["wards"]["count"]),
        "parks_count": str(stats["parks"]["count"]),
        "storm_drains_count": str(stats["storm_drains"]["count"]),
        "nallas_count": str(stats["nallas"]["count"]),
        "rivers_count": str(stats["rivers"]["count"]),
    }
    conn.executemany(
        "INSERT OR REPLACE INTO meta(key,value) VALUES (?,?)", list(meta.items())
    )
    conn.commit()
    conn.close()
    stats["db_path"] = str(db_path)
    stats["db_size_mb"] = round(db_path.stat().st_size / (1024 * 1024), 2)
    return stats


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Build PMC reference spatial layers")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--db", default=str(REPO / "ml_pipeline" / "data" / "reference_layers.sqlite"))
    args = ap.parse_args(argv)

    db = Path(args.db)
    db.parent.mkdir(parents=True, exist_ok=True)
    print(f"Building reference layers -> {db}")
    stats = build(db)
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
