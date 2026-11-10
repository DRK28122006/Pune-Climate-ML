#!/usr/bin/env python3
"""Extract a 5-ward subset (2, 12, 23, 33, 41) for the hackathon demo.

Source of truth stays the full files. The demo pack is written to
`ml_pipeline/data/demo/` and is small enough to commit.

Two rules decide what the subset may contain:

  * Reference layers are copied verbatim. The `wards` table is only 214 KB and
    scoring resolves a site's centroid against *every* ward ring, so cutting it
    down to five would make scores fail on boundary geometry that legitimately
    falls in a neighbouring ward (ward 2's centroid sits in ward 6).
  * Trees are selected spatially, by point-in-polygon against the five ward
    rings, not by `census_ward`. Census blocks are coarse: ward 12 holds 69,980
    trees by geometry but only 31,480 carry `census_ward = 12`, and the canopy
    ledger queries by geometry. A census-labelled cut under-counts canopy by
    half and silently turns green cover into UNAVAILABLE.
"""
import json
import shutil
import sqlite3
from pathlib import Path

OUT = Path(__file__).resolve().parent / "demo"
DATA = Path(__file__).resolve().parent

FIVE = (2, 12, 23, 33, 41)


def extract_reference():
    src = DATA / "reference_layers.sqlite"
    dst = OUT / "reference_layers.sqlite"
    shutil.copy2(src, dst)
    print(
        f"reference_layers.sqlite: copied verbatim "
        f"({dst.stat().st_size // 1024 // 1024} MB, all 41 ward rings kept)"
    )


def _ward_rings():
    conn = sqlite3.connect(DATA / "reference_layers.sqlite")
    try:
        return {
            int(ward_no): json.loads(ring_json)
            for ward_no, ring_json in conn.execute(
                "SELECT ward_no, ring_json FROM wards WHERE ward_no IN (?, ?, ?, ?, ?)",
                FIVE,
            )
        }
    finally:
        conn.close()


def extract_trees():
    from shapely.geometry import Point, Polygon
    from shapely.prepared import prep

    rings = _ward_rings()
    missing = [w for w in FIVE if w not in rings]
    if missing:
        raise SystemExit(f"wards missing from reference layers: {missing}")

    prepared = {w: prep(Polygon(ring)) for w, ring in rings.items()}
    bounds = {w: Polygon(ring).bounds for w, ring in rings.items()}

    keep = set()
    src_conn = sqlite3.connect(DATA / "tree_index.sqlite")
    try:
        for ward_no, (minx, miny, maxx, maxy) in bounds.items():
            rows = src_conn.execute(
                "SELECT t.tree_id, t.lon, t.lat FROM tree_rtree r "
                "JOIN trees t ON t.tree_id = r.tree_id "
                "WHERE r.max_lon >= ? AND r.min_lon <= ? "
                "AND r.max_lat >= ? AND r.min_lat <= ?",
                (minx, maxx, miny, maxy),
            )
            before = len(keep)
            for tree_id, lon, lat in rows:
                if prepared[ward_no].contains(Point(lon, lat)):
                    keep.add(int(tree_id))
            print(f"  ward {ward_no}: {len(keep) - before:,} trees inside the ring")
    finally:
        src_conn.close()

    dst = OUT / "tree_index.sqlite"
    if dst.exists():
        dst.unlink()
    shutil.copy2(DATA / "tree_index.sqlite", dst)

    conn = sqlite3.connect(dst)
    try:
        conn.execute("CREATE TEMP TABLE keep(tree_id INTEGER PRIMARY KEY)")
        conn.executemany(
            "INSERT OR IGNORE INTO keep(tree_id) VALUES (?)", ((t,) for t in keep)
        )
        conn.execute("DELETE FROM trees WHERE tree_id NOT IN (SELECT tree_id FROM keep)")
        conn.execute("DELETE FROM tree_rtree")
        conn.execute(
            "INSERT INTO tree_rtree(tree_id, min_lon, max_lon, min_lat, max_lat) "
            "SELECT tree_id, lon, lon, lat, lat FROM trees"
        )
        conn.commit()
        conn.execute("DROP TABLE keep")
        conn.commit()
    finally:
        conn.close()

    conn = sqlite3.connect(dst)
    try:
        conn.execute("VACUUM")
    finally:
        conn.close()
    kept = sqlite3.connect(dst).execute("SELECT COUNT(*) FROM trees").fetchone()[0]
    print(
        f"tree_index.sqlite: {kept:,} trees kept, "
        f"size = {dst.stat().st_size // 1024 // 1024} MB"
    )


def extract_cube():
    src = DATA / "epoch_cube.json"
    dst = OUT / "epoch_cube.json"
    if not src.exists():
        print("epoch_cube.json not found, skipping")
        return
    shutil.copy2(src, dst)
    print(f"epoch_cube.json: {dst.stat().st_size // 1024} KB")


def export_wards_geojson():
    src = Path(__file__).resolve().parents[2] / "frontend" / "public" / "wards.geojson"
    dst = OUT / "wards.geojson"
    if not src.exists():
        print("wards.geojson not found, skipping")
        return
    data = json.loads(src.read_text())
    feats = []
    for f in data.get("features", []):
        p = f.get("properties", {})
        wnum = p.get("ward_no") or p.get("ward") or p.get("id")
        try:
            n = int(wnum)
        except Exception:
            n = None
        if n in FIVE:
            feats.append(f)
    data["features"] = feats
    dst.write_text(json.dumps(data))
    print(f"wards.geojson: {len(feats)} features, size = {dst.stat().st_size // 1024} KB")


def export_ward_scores():
    src = Path(__file__).resolve().parents[2] / "frontend" / "public" / "ward_scores.json"
    dst = OUT / "ward_scores.json"
    if not src.exists():
        print("ward_scores.json not found, skipping")
        return
    data = json.loads(src.read_text())
    out = {}
    for k, v in data.items():
        if int(k) in FIVE:
            out[k] = v
    dst.write_text(json.dumps(out))
    print(f"ward_scores.json: {len(out)} wards, size = {dst.stat().st_size} bytes")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    extract_reference()
    extract_trees()
    extract_cube()
    export_wards_geojson()
    export_ward_scores()
