"""Build the flood-layer SQLite from the tracked Overpass snapshot.

The raw snapshot (`flood_layers_raw.json`) is the durable input; the SQLite is
derived and therefore gitignored.  This script reproduces the Session 14 layer
deterministically for a fixed raw file: element order is preserved and the
schema/meta match the original build.

Run:
    python ml_pipeline/data/build_flood_layers.py
    python ml_pipeline/data/build_flood_layers.py --out /tmp/opencode/flood_test.sqlite

The raw file is the 2026-11-03 Overpass response for the Pune bbox
(18.39,73.73,18.60,74.06), ODbL-1.0.  Rebuilding from the tracked snapshot is
byte-identical except for `meta.raw_path`, which records the input path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[2]
DEFAULT_RAW = REPO / "ml_pipeline" / "data" / "flood_layers_raw.json"
DEFAULT_OUT = REPO / "ml_pipeline" / "data" / "flood_layers.sqlite"
WATERWAY_KINDS = {"river", "stream", "canal", "drain"}


def _resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else REPO / p


def _meta_path(raw: Path) -> str:
    try:
        return str(raw.relative_to(REPO))
    except ValueError:
        return str(raw)


def _geometry(el: Dict[str, Any]) -> Optional[Any]:
    """Return a LineString or MultiLineString coordinate list, or None."""
    if el.get("type") == "way":
        geom = el.get("geometry")
        if not geom:
            return None
        return [[g["lon"], g["lat"]] for g in geom]

    if el.get("type") == "relation":
        segs: List[Any] = []
        for member in el.get("members", []) or []:
            geom = member.get("geometry")
            if geom:
                segs.append([[p["lon"], p["lat"]] for p in geom])
        if not segs:
            geom = el.get("geometry")
            if geom:
                segs = [[[p["lon"], p["lat"]] for p in geom]]
        if not segs:
            return None
        return segs if len(segs) > 1 else segs[0]

    return None


def build(
    raw_path: Path,
    out_path: Path,
    source: str,
    retrieved_at: str,
    licence: str,
) -> Dict[str, Any]:
    raw_bytes = raw_path.read_bytes()
    raw = json.loads(raw_bytes)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    conn = sqlite3.connect(out_path)
    try:
        conn.execute(
            """CREATE TABLE waterways (
                id INTEGER PRIMARY KEY,
                kind TEXT NOT NULL,
                name TEXT,
                geometry_json TEXT NOT NULL,
                source TEXT NOT NULL,
                retrieved_at TEXT NOT NULL,
                licence TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )"""
        )

        inserted = 0
        for el in raw.get("elements", []):
            if el.get("type") not in ("way", "relation"):
                continue
            tags = el.get("tags") or {}
            kind = tags.get("waterway")
            if kind not in WATERWAY_KINDS:
                continue
            geometry = _geometry(el)
            if geometry is None:
                continue

            name = tags.get("name")
            osm_id = int(el["id"])
            payload = (
                osm_id,
                kind,
                name,
                json.dumps(geometry),
                source,
                retrieved_at,
                licence,
            )
            try:
                conn.execute(
                    "INSERT INTO waterways "
                    "(id, kind, name, geometry_json, source, retrieved_at, licence) "
                    "VALUES (?,?,?,?,?,?,?)",
                    payload,
                )
            except sqlite3.IntegrityError:
                conn.execute(
                    "INSERT INTO waterways "
                    "(id, kind, name, geometry_json, source, retrieved_at, licence) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (osm_id + 10_000_000,) + payload[1:],
                )
            inserted += 1

        meta = {
            "source": source,
            "retrieved_at": retrieved_at,
            "licence": licence,
            "raw_sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "raw_path": _meta_path(raw_path),
        }
        for key, value in meta.items():
            conn.execute("INSERT INTO meta (key, value) VALUES (?,?)", (key, value))
        conn.commit()

        kinds = dict(
            conn.execute(
                "SELECT kind, COUNT(*) FROM waterways GROUP BY kind ORDER BY kind"
            ).fetchall()
        )
    finally:
        conn.close()

    return {
        "bytes": out_path.stat().st_size,
        "sha256": hashlib.sha256(out_path.read_bytes()).hexdigest(),
        "rows": inserted,
        "kinds": kinds,
        "meta": meta,
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="build_flood_layers")
    ap.add_argument("--raw", default=str(DEFAULT_RAW))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--source", default="osm-overpass-2026-11-03")
    ap.add_argument("--retrieved-at", default="2026-11-03")
    ap.add_argument("--licence", default="ODbL-1.0")
    ap.add_argument(
        "--expect-sha256",
        default=None,
        help="fail if the built DB hash differs from this value",
    )
    args = ap.parse_args(argv)

    raw = _resolve(args.raw)
    out = _resolve(args.out)
    if not raw.exists():
        print(f"FAIL: raw snapshot not found at {raw}")
        return 1

    result = build(raw, out, args.source, args.retrieved_at, args.licence)
    print("FLOOD LAYER BUILT")
    print(f"  raw      : {raw}")
    print(f"  out      : {out}")
    print(f"  rows     : {result['rows']}  {result['kinds']}")
    print(f"  bytes    : {result['bytes']}")
    print(f"  sha256   : {result['sha256']}")
    print(f"  raw hash : {result['meta']['raw_sha256']}")

    if args.expect_sha256 and result["sha256"] != args.expect_sha256:
        print(
            f"FAIL: built hash {result['sha256']} != expected {args.expect_sha256}"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
