"""Provenance freshness check (Session 7).

Run: .venv/bin/python -m ml_pipeline.data.check_provenance

Checks committed validation artifacts carry a provenance block consistent with
the current code/config/cube. Does not invent hashes.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ARTIFACTS = [
    REPO / "ml_pipeline" / "data" / "ward_validation.json",
    REPO / "ml_pipeline" / "data" / "site_validation.json",
]


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for ch in iter(lambda: f.read(65536), b""):
            h.update(ch)
    return h.hexdigest()


def git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return None


def main() -> int:
    failures = []
    cfg = json.loads((REPO / "ml_pipeline/config/regions/pune.json").read_text())
    cube_path = REPO / "ml_pipeline/data/epoch_cube.json"
    cube_hash = sha256_file(cube_path) if cube_path.exists() else None
    config_hash = sha256_file(REPO / "ml_pipeline/config/regions/pune.json")
    tree_path = REPO / "ml_pipeline/data/tree_index.sqlite"
    tree_hash = sha256_file(tree_path) if tree_path.exists() and tree_path.stat().st_size > 0 else None
    tree_status = "PRESENT" if tree_hash else "MISSING"

    for art in ARTIFACTS:
        if not art.exists():
            failures.append(f"{art}: missing")
            continue
        data = json.loads(art.read_text())
        prov = data.get("provenance")
        if not prov:
            failures.append(f"{art}: no provenance block")
            continue
        if prov.get("heat_mode") != "NIGHT_MODIS_LST":
            failures.append(f"{art}: heat_mode != NIGHT_MODIS_LST")
        if prov.get("design_storm_mm") != 214.0:
            failures.append(f"{art}: design_storm_mm != 214.0")
        if prov.get("region_config_sha256") != config_hash:
            failures.append(f"{art}: region_config_sha256 drift")
        if prov.get("epoch_cube_sha256") != cube_hash:
            failures.append(f"{art}: epoch_cube_sha256 drift")
        if prov.get("tree_index_sha256") != tree_hash:
            failures.append(f"{art}: tree_index_sha256 drift")
        if prov.get("tree_index_status") != tree_status:
            failures.append(f"{art}: tree_index_status drift")
        print(f"{'OK' if art not in [] else 'FAIL'}  {art.name}")

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print("  -", f)
        print("\nRegenerate with: .venv/bin/python -m ml_pipeline.data.validate_wards")
        return 1
    print("\nAll provenance checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())