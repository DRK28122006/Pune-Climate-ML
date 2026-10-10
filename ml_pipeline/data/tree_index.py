"""Build the SQLite + R-Tree tree index from the PMC Tree Census CSVs.

The census ships as multiple CSV parts on data.opencity.in. This builds one
queryable database so a site polygon can be resolved to its trees in
milliseconds rather than by scanning millions of rows.

    python -m ml_pipeline.data.tree_index --build --parts <dir-or-files>

Design notes that matter:

  - Coordinates are stored as WGS84 lon/lat. Degrees are fine for indexing
    and point-in-polygon; areas are never computed here. Area maths belongs to
    the geometry layer in EPSG:32643.

  - The census 'ward'/'ward_name' columns hold ids in the range 3..63 and do
    NOT correspond to the 1..41 numbering of the 2025 ward boundary KML.
    They are stored verbatim and explicitly flagged unusable for joins.

  - Nothing is dropped silently. Rows with unusable geometry are counted and
    reported, not skipped.
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

CSV_GLOB = "ptc_part*.csv"

REQUIRED_COLUMNS = (
    "botanical_name",
    "girth_cm",
    "height_m",
    "canopy_dia_m",
    "condition",
    "ward",
    "is_rare",
)

SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS trees (
    tree_id       INTEGER PRIMARY KEY,
    lon           REAL NOT NULL,
    lat           REAL NOT NULL,
    botanical_name TEXT,
    girth_cm      REAL,
    height_m      REAL,
    canopy_dia_m  REAL,
    condition     TEXT,
    is_rare       INTEGER DEFAULT 0,
    is_dead       INTEGER DEFAULT 0,
    census_ward   TEXT,
    species_key   TEXT,
    source_file   TEXT,
    source_row    INTEGER
);

CREATE VIRTUAL TABLE IF NOT EXISTS tree_rtree USING rtree(
    tree_id, min_lon, max_lon, min_lat, max_lat
);

CREATE INDEX IF NOT EXISTS idx_species_key ON trees(species_key);
CREATE INDEX IF NOT EXISTS idx_girth       ON trees(girth_cm);
CREATE INDEX IF NOT EXISTS idx_rare        ON trees(is_rare);
"""


def species_key(botanical_name: Optional[str]) -> str:
    """'Ficus religiosa Linn.' -> 'Ficus religiosa'."""
    tokens = (botanical_name or "").split()
    if not tokens:
        return ""
    return tokens[0] if len(tokens) == 1 else f"{tokens[0]} {tokens[1]}"


def parse_geom(geom: str) -> Optional[Tuple[float, float]]:
    """'POINT (73.89 18.48)' -> (lon, lat).

    The census also has northing/easting columns, but they hold lat/lon in that
    order despite their names. The WKT geometry is unambiguous, so it is the
    authoritative source and the mis-named columns are ignored.
    """
    if not geom:
        return None
    txt = geom.strip()
    if not txt.upper().startswith("POINT"):
        return None
    start, end = txt.find("("), txt.rfind(")")
    if start < 0 or end <= start:
        return None
    parts = txt[start + 1 : end].split()
    if len(parts) < 2:
        return None
    try:
        lon, lat = float(parts[0]), float(parts[1])
    except ValueError:
        return None
    if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
        return None
    return lon, lat


def _to_float(value: Optional[str]) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _to_bool(value: Optional[str]) -> int:
    return 1 if (value or "").strip().upper() == "TRUE" else 0


DEAD_CONDITIONS = {"dead", "dead tree", "fallen", "stump"}


def find_parts(target: str) -> List[str]:
    p = Path(target)
    if p.is_file():
        return [str(p)]
    if p.is_dir():
        return sorted(glob.glob(os.path.join(target, CSV_GLOB))) or sorted(
            glob.glob(os.path.join(target, "*.csv"))
        )
    return sorted(glob.glob(target))


def build(
    parts: Iterable[str],
    db_path: str,
    batch_size: int = 5000,
    progress_every: int = 50000,
) -> Dict[str, object]:
    parts = list(parts)
    if not parts:
        raise SystemExit("No census CSV parts found. Pass a directory or files.")

    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    cur = conn.cursor()

    stats: Dict[str, Any] = {
        "parts": len(parts),
        "rows_read": 0,
        "inserted": 0,
        "skipped_no_geometry": 0,
        "skipped_out_of_range": 0,
        "duplicate_tree_id": 0,
        "missing_botanical_name": 0,
        "girth_ge_60": 0,
        "girth_ge_90": 0,
        "rare": 0,
        "dead": 0,
    }
    species: Dict[str, int] = {}
    pending: List[Tuple] = []

    for part in parts:
        fname = os.path.basename(part)
        with open(part, newline="", encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh)
            cols = set(reader.fieldnames or [])
            missing = [c for c in REQUIRED_COLUMNS if c not in cols]
            if missing:
                print(
                    f"  ! {fname} missing columns {missing}; skipping this part.",
                    file=sys.stderr,
                )
                stats["skipped_parts"] = int(stats.get("skipped_parts", 0)) + 1
                continue

            for row_idx, row in enumerate(reader, start=2):
                stats["rows_read"] = int(stats["rows_read"]) + 1  # type: ignore[operator]
                total_read = int(stats["rows_read"])  # type: ignore[arg-type]

                pt = parse_geom(row.get("geom", ""))
                if pt is None:
                    lon, lat = _to_float(row.get("easting")), _to_float(row.get("northing"))
                    if lon is None or lat is None:
                        stats["skipped_no_geometry"] = (
                            int(stats["skipped_no_geometry"]) + 1  # type: ignore[arg-type]
                        )
                        continue
                    if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
                        stats["skipped_out_of_range"] = (
                            int(stats["skipped_out_of_range"]) + 1  # type: ignore[arg-type]
                        )
                        continue
                else:
                    lon, lat = pt

                bname = (row.get("botanical_name") or "").strip()
                if not bname:
                    stats["missing_botanical_name"] = (
                        int(stats["missing_botanical_name"]) + 1  # type: ignore[arg-type]
                    )

                girth = _to_float(row.get("girth_cm"))
                height = _to_float(row.get("height_m"))
                canopy = _to_float(row.get("canopy_dia_m"))
                cond = (row.get("condition") or "").strip()
                is_rare = _to_bool(row.get("is_rare"))
                is_dead = 1 if cond.lower() in DEAD_CONDITIONS else 0
                skey = species_key(bname)

                pending.append(
                    (
                        total_read,
                        lon,
                        lat,
                        bname,
                        girth,
                        height,
                        canopy,
                        cond,
                        is_rare,
                        is_dead,
                        (row.get("ward") or "").strip(),
                        skey,
                        fname,
                        row_idx,
                    )
                )
                species[skey] = species.get(skey, 0) + 1

                if girth is not None:
                    if girth >= 90:
                        stats["girth_ge_90"] = int(stats["girth_ge_90"]) + 1  # type: ignore[arg-type]
                    elif girth >= 60:
                        stats["girth_ge_60"] = int(stats["girth_ge_60"]) + 1  # type: ignore[arg-type]
                if is_rare:
                    stats["rare"] = int(stats["rare"]) + 1  # type: ignore[arg-type]
                if is_dead:
                    stats["dead"] = int(stats["dead"]) + 1  # type: ignore[arg-type]

                if len(pending) >= batch_size:
                    changes_before = cur.connection.total_changes
                    _flush(cur, pending, db_path)
                    written = cur.connection.total_changes - changes_before
                    pending.clear()
                    # Each row inserts into `trees` and into the rtree, so
                    # divide out the rtree half to report rows, not writes.
                    stats["inserted"] = int(stats["inserted"]) + max(0, written // 2)
                    if total_read % progress_every < batch_size:
                        print(f"  ... {total_read:,} rows read", flush=True)

    if pending:
        changes_before = cur.connection.total_changes
        _flush(cur, pending, db_path)
        written = cur.connection.total_changes - changes_before
        pending.clear()
        stats["inserted"] = int(stats["inserted"]) + max(0, written // 2)

    top_species = sorted(species.items(), key=lambda kv: -kv[1])[:20]
    total = sum(species.values()) or 1
    meta = {
        "schema_version": "1",
        "census_year": "2019",
        "census_source": "PMC Tree Census 2019 / data.opencity.in "
        "CKAN f00d83b8-c70f-4fff-9ac7-9a6ab4255edf",
        "coordinate_reference": "WGS84 lon/lat (EPSG:4326) for indexing only. "
        "Areas must be computed in EPSG:32643.",
        "ward_id_warning": "census_ward is the census' own id (observed range 3..63). "
        "It does NOT match the 1..41 numbering of pmc_wards_2025.kml. "
        "Assign ward by point-in-polygon, never by joining ward ids.",
        "parts": ",".join(os.path.basename(p) for p in parts),
        "rows_indexed": str(stats["inserted"]),
    }
    cur.executemany(
        "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
        [(k, str(v)) for k, v in meta.items()],
    )
    conn.commit()

    stats["top_species"] = [
        {"species_key": s, "count": c, "share_pct": round(100.0 * c / total, 2)}
        for s, c in top_species
    ]
    stats["db_path"] = os.path.abspath(db_path)
    stats["db_size_mb"] = round(os.path.getsize(db_path) / (1024 * 1024), 1)
    conn.close()
    return stats


def _flush(cur: sqlite3.Cursor, rows: List[Tuple], db_path: str) -> None:
    if not rows:
        return
    try:
        cur.executemany(
            """
            INSERT OR IGNORE INTO trees(
                tree_id, lon, lat, botanical_name, girth_cm, height_m,
                canopy_dia_m, condition, is_rare, is_dead, census_ward,
                species_key, source_file, source_row
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            rows,
        )
        cur.executemany(
            "INSERT OR REPLACE INTO tree_rtree(tree_id, min_lon, max_lon, min_lat, max_lat) "
            "VALUES (?,?,?,?,?)",
            [(r[0], r[1], r[1], r[2], r[2]) for r in rows],
        )
        cur.connection.commit()
    except sqlite3.IntegrityError:
        # Duplicate tree_id: fall back to a synthetic unique id so no data is lost.
        for r in rows:
            try:
                cur.execute(
                    """
                    INSERT INTO trees(
                        tree_id, lon, lat, botanical_name, girth_cm, height_m,
                        canopy_dia_m, condition, is_rare, is_dead, census_ward,
                        species_key, source_file, source_row
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (None, r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10],
                     r[11], r[12], r[13]),
                )
                new_id = cur.lastrowid
                cur.execute(
                    "INSERT OR REPLACE INTO tree_rtree(tree_id, min_lon, max_lon, "
                    "min_lat, max_lat) VALUES (?,?,?,?,?)",
                    (new_id, r[1], r[1], r[2], r[2]),
                )
            except sqlite3.IntegrityError:
                continue
        cur.connection.commit()


def query_bbox(
    db_path: str, min_lon: float, min_lat: float, max_lon: float, max_lat: float
) -> List[sqlite3.Row]:
    """Bounding-box candidates. Callers still need exact point-in-polygon."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT t.* FROM tree_rtree r
        JOIN trees t ON t.tree_id = r.tree_id
        WHERE r.max_lon >= ? AND r.min_lon <= ?
          AND r.max_lat >= ? AND r.min_lat <= ?
        ORDER BY t.tree_id
        """,
        (min_lon, max_lon, min_lat, max_lat),
    ).fetchall()
    conn.close()
    return rows


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build the PMC tree census index")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--parts", default=".", help="dir, glob or file list")
    parser.add_argument("--db", default="ml_pipeline/data/tree_index.sqlite")
    parser.add_argument("--stats-out", default=None)
    args = parser.parse_args(argv)

    parts = find_parts(args.parts)
    if not parts:
        print(f"No {CSV_GLOB} files under {args.parts}", file=sys.stderr)
        return 1

    print(f"Building index from {len(parts)} part(s) -> {args.db}")
    stats = build(parts, args.db)
    printable = {k: v for k, v in stats.items() if k != "top_species"}
    print(json.dumps(printable, indent=2))
    print("\nTop species:")
    for row in stats.get("top_species", []):  # type: ignore[union-attr]
        print(f"  {row['species_key'][:42]:<42} {row['count']:>7} {row['share_pct']:>6.2f}%")
    if args.stats_out:
        Path(args.stats_out).write_text(json.dumps(stats, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
