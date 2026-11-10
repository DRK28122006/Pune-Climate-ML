"""Resolve where the baked ML artefacts live.

The full pipeline writes to ``ml_pipeline/data`` (the census tree index alone is
1.1 GB). Deployments that only ship the 5-ward demo pack point ``PMC_DATA_DIR``
at it; when that variable is unset the full data directory is used if it holds a
tree index, otherwise the committed demo pack is used.

Caches (air quality, canopy aggregates) are written to ``PMC_CACHE_DIR`` when
set, otherwise beside the data. Read-only filesystems fall back to the system
temp directory.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FULL_DATA = REPO / "ml_pipeline" / "data"
DEMO_DATA = FULL_DATA / "demo"


def data_dir() -> Path:
    override = os.environ.get("PMC_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if (FULL_DATA / "tree_index.sqlite").exists():
        return FULL_DATA
    if (DEMO_DATA / "tree_index.sqlite").exists():
        return DEMO_DATA
    return FULL_DATA


def demo_wards() -> tuple[int, ...]:
    """Wards this deployment can actually score.

    A pack cut down to a handful of wards must say so instead of scoring the
    other wards with no trees and reporting a partial result that looks like a
    data problem. Set ``PMC_DEMO_WARDS=2,12,23,33,41`` on the deployment;
    unset means every ward the reference layers know about.
    """
    raw = os.environ.get("PMC_DEMO_WARDS", "").strip()
    if not raw:
        return ()
    wards: list[int] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            wards.append(int(chunk))
        except ValueError:
            continue
    return tuple(wards)


def cache_dir() -> Path:
    override = os.environ.get("PMC_CACHE_DIR")
    base = Path(override).expanduser().resolve() if override else data_dir()
    try:
        base.mkdir(parents=True, exist_ok=True)
        probe = base / ".write-probe"
        probe.touch()
        probe.unlink()
        return base
    except OSError:
        return Path(tempfile.gettempdir())
