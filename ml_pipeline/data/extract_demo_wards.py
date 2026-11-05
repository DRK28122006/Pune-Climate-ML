#!/usr/bin/env python3
"""Extract a 5-ward subset (2, 12, 23, 33, 41) for the hackathon demo.

Source of truth stays the full files. The demo pack is written to
`ml_pipeline/data/demo/` and is small enough to commit.
"""
import json
import shutil
import sqlite3
from pathlib import Path

OUT = Path(__file__).resolve().parent / "demo"

FIVE = (2, 12, 23, 33, 41)

def extract_reference():
    src = Path(__file__).resolve().parent / "reference_layers.sqlite"
    dst = OUT / "reference_layers.sqlite"
    if dst.exists():
        dst.unlink()
    shutil.copy2(src, dst)
    conn = sqlite3.connect(dst)
    cur = conn.cursor()
    # keep only the five wards and their related parks/nallas if ward-filtered;
    # simplest safe cut: keep all tables, just delete the other wards.
    cur.execute("DELETE FROM wards WHERE ward_no NOT IN (?, ?, ?, ?, ?)", FIVE)
    conn.commit()
    conn.close()
    conn = sqlite3.connect(dst)
    conn.execute("VACUUM")
    conn.close()
    print(f"reference_layers.sqlite: kept wards {FIVE}, size = {dst.stat().st_size // 1024} KB")

def extract_trees():
    src = Path(__file__).resolve().parent / "tree_index.sqlite"
    dst = OUT / "tree_index.sqlite"
    if dst.exists():
        dst.unlink()
    shutil.copy2(src, dst)
    conn = sqlite3.connect(dst)
    cur = conn.cursor()
    cur.execute("DELETE FROM trees WHERE census_ward NOT IN (?, ?, ?, ?, ?)", FIVE)
    cur.execute("DELETE FROM tree_rtree")
    cur.execute(
        "INSERT INTO tree_rtree(tree_id, min_lon, max_lon, min_lat, max_lat) "
        "SELECT tree_id, MIN(lon), MAX(lon), MIN(lat), MAX(lat) FROM trees GROUP BY tree_id"
    )
    conn.commit()
    conn.close()
    conn = sqlite3.connect(dst)
    conn.execute("VACUUM")
    conn.close()
    print(f"tree_index.sqlite: kept trees for wards {FIVE}, size = {dst.stat().st_size // 1024 // 1024} MB")

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
    export_wards_geojson()
    export_ward_scores()
