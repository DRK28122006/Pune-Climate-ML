"""Standalone probe: floodplain / watercourse exposure for 41 wards + 8 sites.

Reads ward polygons from reference_layers.sqlite and sites from validate_sites
(SITES). Prints a table and writes /tmp/opencode/floodplain_probe.json.
No tracked writes. Exits cleanly with UNAVAILABLE rows if no layer exists.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

REF_DB = REPO / "ml_pipeline" / "data" / "reference_layers.sqlite"
OUT = Path("/tmp/opencode/floodplain_probe.json")

from ml_pipeline.core import floodplain as FP


def _ward_centroids() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not REF_DB.exists():
        return out
    try:
        conn = sqlite3.connect(f"file:{REF_DB}?mode=ro", uri=True)
    except sqlite3.Error:
        return out
    try:
        for ward_no, ring_json in conn.execute("SELECT ward_no, ring_json FROM wards"):
            try:
                ring = json.loads(ring_json)
            except (json.JSONDecodeError, TypeError):
                continue
            if not ring:
                continue
            from shapely.geometry import Polygon

            poly = Polygon(ring)
            if poly.is_empty:
                continue
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.is_empty:
                continue
            centroid = poly.centroid
            out.append(
                {
                    "label": f"ward {ward_no}",
                    "lon": float(centroid.x),
                    "lat": float(centroid.y),
                    "kind": "ward",
                }
            )
    finally:
        conn.close()
    return out


def _sites() -> List[Dict[str, Any]]:
    try:
        from ml_pipeline.data import validate_sites as VS
    except Exception as exc:  # noqa: BLE001
        print(f"WARN: could not import validate_sites: {exc}")
        return []
    out: List[Dict[str, Any]] = []
    for s in getattr(VS, "SITES", []):
        out.append({
            "label": s.get("name", "site"),
            "lon": float(s["lon"]),
            "lat": float(s["lat"]),
            "kind": "site",
        })
    return out


def main() -> int:
    targets = _ward_centroids() + _sites()
    rows: List[Dict[str, Any]] = []
    print(f"{'label':<22} {'status':<16} {'in_fp':<6} {'nearest_m':<10} {'source'}")
    print("-" * 80)
    for t in targets:
        fs = FP.floodplain_status(t["lon"], t["lat"])
        wd = FP.watercourse_distance_m(t["lon"], t["lat"])
        row = {
            "label": t["label"],
            "kind": t["kind"],
            "lon": t["lon"],
            "lat": t["lat"],
            "floodplain_status": fs.get("status"),
            "in_floodplain": fs.get("in_floodplain"),
            "nearest_watercourse_m": fs.get("nearest_watercourse_m"),
            "watercourse_distance_m": wd.get("nearest_watercourse_m"),
            "source": fs.get("source"),
            "licence": fs.get("licence"),
            "confidence": fs.get("confidence"),
            "note": fs.get("note"),
        }
        rows.append(row)
        in_fp = row["in_floodplain"]
        in_str = "None" if in_fp is None else str(in_fp)
        nm = row["nearest_watercourse_m"]
        nm_str = "-" if nm is None else f"{nm}"
        print(f"{row['label']:<22} {row['floodplain_status']:<16} {in_str:<6} {nm_str:<10} {row['source'] or '-'}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"rows": rows}, indent=2))
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())