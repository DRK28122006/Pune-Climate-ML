"""Generic census intake: any CSV -> canonical index.

Maps arbitrary headers onto the canonical columns the index builder
requires (botanical_name, girth_cm, height_m, canopy_dia_m, condition,
ward, is_rare + WKT geom or easting/northing lon/lat), then delegates to
ml_pipeline.data.tree_index.build -- the same builder Pune uses, so the
same dedupe/stats/gates apply. PMC-specific meta rows are overwritten
with the caller's source (documented, not silent).
"""
import csv
import os
import sqlite3
from typing import Dict, List, Optional

CANONICAL = ("botanical_name", "girth_cm", "height_m", "canopy_dia_m",
             "condition", "ward", "is_rare", "geom", "easting", "northing")


def normalize_csv(src_path: str, dst_path: str,
                  column_map: Dict[str, str]) -> str:
    """Rewrite src with mapped headers. column_map: canonical -> src header.

    Unmapped canonical columns are emitted empty (geometry may come from
    easting/northing instead of geom -- one of the two forms is required
    per row or the row is skipped by the builder, counted, never scored).
    """
    with open(src_path, newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"{src_path}: no header row")
        rows = list(reader)
    os.makedirs(os.path.dirname(os.path.abspath(dst_path)), exist_ok=True)
    with open(dst_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(CANONICAL))
        w.writeheader()
        # Every row is passed through; the index builder counts geometry-
        # less rows as skips itself. This function never drops data.
        for r in rows:
            out = {}
            for canon in CANONICAL:
                if canon in r:
                    out[canon] = r[canon]
                elif canon in column_map:
                    out[canon] = r.get(column_map[canon], "")
                else:
                    out[canon] = ""
            w.writerow(out)
    return dst_path


def build_index(parts: List[str], db_path: str,
                source_label: str = "UNSOURCED",
                census_year: Optional[int] = None) -> Dict[str, object]:
    """Build the sqlite index, then stamp caller meta over PMC defaults."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from ml_pipeline.data import tree_index
    parent = os.path.dirname(os.path.abspath(db_path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    stats = tree_index.build(parts, db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.executemany(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
            [("census_source", str(source_label)),
             ("census_year", str(census_year or "UNSOURCED")),
             ("ward_id_warning", "census_ward is the census' own id. "
              "Assign ward by point-in-polygon against YOUR boundary file, "
              "never by joining ward ids until proven identical.")])
        conn.commit()
    finally:
        conn.close()
    return stats
