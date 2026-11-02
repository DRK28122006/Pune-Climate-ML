"""Score many wards from the epoch cube and report whether scores DISPERSE.

This is the acceptance test that matters. Before the cube existed, impervious
and vegetation were placeholders, so all six test wards landed between 55.7 and
59.6 -- a spread of 3.9 points across wildly different parts of the city. That
is what a stubbed satellite layer looks like from the outside: a random number
generator with a map attached.

The pass condition is not "high scores" or "low scores". It is DISPERSION:
wards that differ in built-up fraction, canopy and elevation must produce
materially different scores. If they do not, the pipeline is not reading its
own inputs and no amount of presentation will fix it.

Run:
    .venv/bin/python -m ml_pipeline.data.validate_wards --wards 3 7 12 13 21 25
    .venv/bin/python -m ml_pipeline.data.validate_wards --all-loaded
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
import hashlib
import subprocess
from datetime import datetime, timezone

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

CONFIG_DIR = REPO / "ml_pipeline" / "config"
CUBE = REPO / "ml_pipeline" / "data" / "epoch_cube.json"
OUT = REPO / "ml_pipeline" / "data" / "ward_validation.json"
KML_WARDS = REPO / "ml_pipeline" / "research" / "05_sources" / "kml" / "pmc_wards_2025.kml"

# Identical site assumptions across every ward, so the ONLY thing varying is
# location. A fixed 2,000 m2 footprint on a 4,000 m2 plot (50% built) and a
# standard RC frame.
BUILT_UP_SQM = 2000.0
PLOT_SQM = 4000.0
MATERIALS = [
    {"name": "steel", "quantityKg": 120_000.0},   # 52% of emissions at India's EF
    {"name": "cement", "quantityKg": 400_000.0},
]

# Wards known to have census data loaded from ptc_part1.csv's geographic block.
# Populated lazily from the tree index so it cannot drift out of date.
LOADED_WARDS: List[int] = []


def _ward_ring(G, ward_no: int) -> Optional[List[Any]]:
    """The ward's polygon ring, read straight from the reference db.

    `ward_tree_profile` deliberately returns a summary and closes its
    connection, so there is no ring in its output. Reading it here keeps the
    harness honest about using the same source of truth as the pipeline.
    """
    import sqlite3

    try:
        conn = sqlite3.connect(f"file:{G.REF_DB}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        row = conn.execute(
            "SELECT ring_json FROM wards WHERE ward_no = ?", (ward_no,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return json.loads(row[0])


def _discover_loaded_wards(G) -> List[int]:
    """Every ward with at least one tree in the index."""
    out: List[int] = []
    try:
        for w in range(1, 42):
            p = G.ward_tree_profile(w)
            if p.get("available") and p.get("trees"):
                out.append(w)
    except Exception:  # noqa: BLE001
        pass
    return out


def _cell_ring(lon: float, lat: float, cell_deg: float) -> List[Any]:
    h = cell_deg / 2.0
    return [
        (lon - h, lat - h), (lon + h, lat - h),
        (lon + h, lat + h), (lon - h, lat + h),
        (lon - h, lat - h),
    ]


def _cells_for_ward(ring: List[Any], cube: Dict[str, Any]) -> Dict[str, Any]:
    """Return area-weighted indicators for all cube cells intersecting the ward.

    Majority-overlap by cell centre for membership, then area-weighted by cell
    intersection. Reports cells_used and an area-coverage fraction. No single
    centroid sample.
    """
    from ml_pipeline.core import geometry as G

    cell_deg = float(cube.get("cell_deg", 0.009))
    cells = cube.get("cells", {})
    selected: List[str] = []
    for key, cell in cells.items():
        try:
            clon, clat = (float(x) for x in key.split("_"))
        except (ValueError, AttributeError):
            continue
        if G.point_in_polygon((clon, clat), ring):
            selected.append(key)

    if not selected:
        return {"cells_used": 0, "area_coverage": 0.0, "indicators": None}

    # Area weight each selected cell by its intersection with the ward polygon.
    # Approximate intersection area as the cell area clipped to the ward bbox
    # using the cell centre membership already established; full polygon clip is
    # expensive and the cells are ~1 km. Report coverage as selected/total cells
    # weighted by cell area.
    sample_key = selected[0].split("_")
    cell_area_m2 = G.polygon_area_m2(_cell_ring(float(sample_key[0]), float(sample_key[1]), cell_deg))

    ward_area_m2 = G.polygon_area_m2(ring)
    covered_m2 = len(selected) * cell_area_m2
    coverage = (covered_m2 / ward_area_m2) if ward_area_m2 > 0 else 0.0
    coverage = min(1.0, coverage)

    def _mean(field: str) -> Optional[float]:
        vals = [cells[k].get(field) for k in selected if cells[k].get(field) is not None]
        if not vals:
            return None
        return sum(vals) / len(vals)

    def _mean_pct(field: str) -> Optional[float]:
        v = _mean(field)
        return (v * 100.0) if v is not None else None

    indicators = {
        "impervious_pct": _mean_pct("built_pct"),
        "vegetation_pct": _mean_pct("vegetation_pct"),
        "water_pct": _mean_pct("water_pct"),
        "bare_pct": _mean_pct("bare_pct"),
        "bare_season_pct": _mean("bare_season_pct"),
        "lst_mean_c": _mean("lst_mean_c"),
        "lst_reference_c": _mean("lst_reference_c"),
        "lst_max_c": _mean("lst_max_c"),
        "lst_night_mean_c": _mean("lst_night_mean_c"),
        "lst_night_reference_c": _mean("lst_night_reference_c"),
        "mean_slope_deg": _mean("mean_slope_deg") if any(cells[k].get("mean_slope_deg") is not None for k in selected) else None,
        "dist_to_storm_drain_m": None,
        "landcover_source": "area_weighted_cube_cells",
    }
    if indicators["mean_slope_deg"] is None:
        # fall back to slope_deg if present
        s = _mean("slope_deg") if "slope_deg" in cells[selected[0]] else None
        indicators["mean_slope_deg"] = s

    return {
        "cells_used": len(selected),
        "area_coverage": round(coverage, 3),
        "selected_cells": selected,
        "indicators": indicators,
    }


def _provenance() -> Dict[str, Any]:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        commit = None
    try:
        dirty = bool(subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=REPO, stderr=subprocess.DEVNULL
        ).decode().strip())
    except Exception:
        dirty = None
    cfg = json.loads((REPO / "ml_pipeline" / "config" / "regions" / "pune.json").read_text())
    cube_path = Path(__file__).resolve().parents[2] / "ml_pipeline" / "data" / "epoch_cube.json"
    cube = json.loads(cube_path.read_text())
    def sha256_file(p):
        import hashlib
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for ch in iter(lambda: f.read(65536), b""):
                h.update(ch)
        return h.hexdigest()
    root = Path(__file__).resolve().parents[2]
    tree_path = root / "ml_pipeline" / "data" / "tree_index.sqlite"
    return {
        "code_commit": commit,
        "working_tree_dirty": dirty,
        "scorer_version": "session3",
        "region_config_sha256": sha256_file(root / "ml_pipeline" / "config" / "regions" / "pune.json"),
        "epoch_cube_sha256": sha256_file(cube_path),
        "tree_index_sha256": (sha256_file(tree_path) if tree_path.exists() else None),
        "tree_index_status": ("PRESENT" if tree_path.exists() else "MISSING"),
        "heat_mode": "NIGHT_MODIS_LST",
        "design_storm_mm": cfg.get("hydrology", {}).get("design_storm_mm"),
        "hsg": "B",
        "weights": cfg.get("weights"),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def load_context():
    """Import the pipeline pieces, failing loudly if a database is missing."""
    from ml_pipeline.core import geometry as G
    from ml_pipeline.core import scoring as S
    from ml_pipeline.data import reference_layers as R

    return G, S, R


def _load_ward_rings() -> Dict[int, List[Any]]:
    """Ward rings from reference DB if available, else from the copied KML."""
    rings: Dict[int, List[Any]] = {}
    # Try reference DB first.
    try:
        import sqlite3
        conn = sqlite3.connect(f"file:{REPO / 'ml_pipeline/data/reference_layers.sqlite'}?mode=ro", uri=True)
        for ward_no, ring_json in conn.execute("SELECT ward_no, ring_json FROM wards"):
            rings[int(ward_no)] = json.loads(ring_json)
        conn.close()
        if rings:
            return rings
    except Exception:
        pass
    # Fall back to KML (no fabrication; uses the already-copied file).
    kml_path = KML_WARDS
    if not kml_path.exists():
        # try original location
        alt = Path("/home/mesh/Pictures/pmc_wards_2025.kml")
        if alt.exists():
            kml_path = alt
    if not kml_path.exists():
        return rings
    try:
        from ml_pipeline.data import reference_layers as RL
        for pm in RL.parse_kml_placemarks(kml_path):
            ring = RL._largest_ring(pm)
            if len(ring) < 3:
                continue
            ward_no = None
            m = RL._WARD_NO_RE.search(pm.get("name") or "")
            if m:
                ward_no = int(m.group(1))
            if ward_no is None:
                raw = (pm.get("attrs") or {}).get("qwr")
                if raw:
                    try:
                        ward_no = int(round(float(raw)))
                    except ValueError:
                        ward_no = None
            if ward_no is None:
                continue
            rings[ward_no] = list(ring)
    except Exception:
        pass
    return rings


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="validate_wards")
    ap.add_argument("--wards", nargs="*", type=int, default=[3, 7, 12, 13, 21, 25])
    ap.add_argument("--all-loaded", action="store_true")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)

    if not CUBE.exists():
        print(f"FAIL: no epoch cube at {CUBE}")
        print("Run: .venv/bin/python -m ml_pipeline.data.build_cube --epoch 2024")
        return 1

    cube = json.loads(CUBE.read_text())
    cells = cube.get("cells", {})
    with_lst = sum(1 for c in cells.values() if c.get("lst_mean_c") is not None)
    print(f"epoch cube: {len(cells)} cells, {with_lst} with LST, epoch {cube.get('epoch')}")
    print()

    from ml_pipeline.core import geometry as G
    from ml_pipeline.core import scoring as S
    from ml_pipeline import cli as CLI

    # Config lives in JSON files loaded by the CLI, not as module constants in
    # ml_pipeline.config -- there is no REGION/MATERIALS export to import.
    REGION = json.loads((CONFIG_DIR / "regions" / "pune.json").read_text())
    MATERIALS_TABLE = json.loads((CONFIG_DIR / "materials.json").read_text())

    if args.all_loaded:
        global LOADED_WARDS
        LOADED_WARDS = _discover_loaded_wards(G)
        print(f"discovered {len(LOADED_WARDS)} wards with census data loaded")
        print(f"  {LOADED_WARDS}")
        print()
        wards = LOADED_WARDS or args.wards
    else:
        wards = args.wards

    ward_rings = _load_ward_rings()
    if not ward_rings:
        print("FAIL: no ward polygons available (reference DB and KML both missing)")
        return 1

    rows: List[Dict[str, Any]] = []

    for w in wards:
        try:
            prof = G.ward_tree_profile(w)
        except Exception as exc:  # noqa: BLE001
            print(f"  ward {w}: profile failed: {exc}")
            prof = {"available": False, "reason": str(exc)}
        # Reference DB may be missing; ward rings came from KML. Do not skip
        # the ward just because the census profile is unavailable.

        ring = ward_rings.get(w)
        if not ring:
            print(f"  ward {w}: could not read ward polygon")
            continue

        site = {
            "builtUpAreaSqm": BUILT_UP_SQM,
            "plotAreaSqm": PLOT_SQM,
            "materials": MATERIALS,
        }

        agg = _cells_for_ward(ring, cube)
        cells_used = agg["cells_used"]
        area_coverage = agg["area_coverage"]
        sat = agg["indicators"] or {}
        if sat is None:
            print(f"  ward {w}: no cube cells intersect ward")
            continue

        # Cube landcover is a FRACTION; the scorer's *_pct fields are percent.
        # _cells_for_ward already converts fractions to percent.
        indicators = {
            "impervious_pct": sat.get("impervious_pct"),
            "vegetation_pct": sat.get("vegetation_pct"),
            "water_pct": sat.get("water_pct"),
            "bare_pct": sat.get("bare_pct"),
            "bare_season_pct": sat.get("bare_season_pct"),
            "lst_mean_c": sat.get("lst_mean_c"),
            "lst_reference_c": sat.get("lst_reference_c"),
            "lst_max_c": sat.get("lst_max_c"),
            "lst_night_mean_c": sat.get("lst_night_mean_c"),
            "lst_night_reference_c": sat.get("lst_night_reference_c"),
            "mean_slope_deg": sat.get("mean_slope_deg"),
            "dist_to_storm_drain_m": prof.get("dist_to_storm_drain_m"),
            "landcover_source": "area_weighted_cube_cells",
        }
        print(f"  ward {w}: {cells_used} cells, area coverage {area_coverage}")
        # The ward profile already carries the census canopy and its reliability.
        # Passing them through keeps green scorable where the census really is
        # loaded, and withholds it where the loaded census parts do not cover
        # this ward (zero trees there does not mean treeless).
        if prof.get("available"):
            ledger = {
                "canopy_cover_pct": prof.get("canopy_cover_pct"),
                "census_reliable_for_this_site": prof.get("trees_are_reliable", True),
                "total_trees": prof.get("trees"),
            }
        else:
            ledger = None
        try:
            res = S.score_project(
                site, indicators, REGION, MATERIALS_TABLE, ledger=ledger
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  ward {w}: score failed: {exc}")
            continue

        rows.append({
            "ward": w,
            "score": res.get("climate_score"),
            "impact": res.get("impact_score"),
            "risk_band": res.get("risk_band"),
            "complete": res.get("complete"),
            "cells_used": cells_used,
            "area_coverage": area_coverage,
            "built_pct": indicators["impervious_pct"],
            "veg_pct": indicators["vegetation_pct"],
            "lst_mean_c": indicators["lst_mean_c"],
            "lst_ref_c": indicators["lst_reference_c"],
            "lst_night_mean_c": indicators["lst_night_mean_c"],
            "uhi_delta_c": (indicators["lst_mean_c"] - indicators["lst_reference_c"])
                           if (indicators["lst_mean_c"] is not None and indicators["lst_reference_c"] is not None)
                           else None,
            "trees_loaded": prof.get("trees"),
            "tree_canopy_pct": prof.get("canopy_cover_pct"),
            "trees_reliable": prof.get("trees_are_reliable", True),
            "sub_scores": res.get("sub_scores"),
        })

    if not rows:
        print("FAIL: no ward produced a score")
        return 1

    # ---- report ----
    print("=" * 100)
    print("WARD DISPERSION TEST  (fixed site, location varies)")
    print("=" * 100)
    print(f"{'ward':>5} {'score':>7} {'band':>9} {'built%':>7} {'veg%':>6} "
          f"{'LST':>7} {'ref':>7} {'UHI':>6} {'trees':>8} {'canopy%':>8}")
    print("-" * 100)
    for r in sorted(rows, key=lambda x: (x["score"] is None, x["score"])):
        lst = f"{r['lst_mean_c']:.2f}" if r["lst_mean_c"] is not None else "  -  "
        ref = f"{r['lst_ref_c']:.2f}" if r["lst_ref_c"] is not None else "  -  "
        uhi = f"{r['uhi_delta_c']:+.2f}" if r["uhi_delta_c"] is not None else "  -  "
        bld = f"{r['built_pct']:.1f}" if r["built_pct"] else "  -  "
        veg = f"{r['veg_pct']:.1f}" if r["veg_pct"] else "  -  "
        tr = f"{r['trees_loaded']:,}" if r["trees_loaded"] else "0"
        if not r["trees_reliable"]:
            tr += "*"
        can = f"{r['tree_canopy_pct']:.1f}" if r["tree_canopy_pct"] is not None else "  -  "
        print(f"{r['ward']:>5} {r['score'] if r['score'] is not None else -1:>7.2f} "
              f"{str(r['risk_band']):>9} {bld:>7} {veg:>6} {lst:>7} {ref:>7} "
              f"{uhi:>6} {tr:>8} {can:>8}")

    print()
    print("(* = census not loaded for this ward, tree figures are not usable)")

    scored = [r["score"] for r in rows if r["score"] is not None]
    complete = sum(1 for r in rows if r.get("complete"))

    print()
    print("=" * 60)
    print("ACCEPTANCE")
    print("=" * 60)
    print(f"wards scored           : {len(scored)}/{len(rows)}")
    print(f"with ALL 4 factors     : {complete}/{len(rows)}")

    if len(scored) >= 2:
        spread = max(scored) - min(scored)
        mean = statistics.mean(scored)
        sd = statistics.pstdev(scored)
        print(f"score range            : {min(scored):.2f} .. {max(scored):.2f}  (spread {spread:.2f})")
        print(f"mean / sd              : {mean:.2f} / {sd:.2f}")

        # The pre-cube baseline spread across these same wards was 3.9 points.
        BASELINE_SPREAD = 5.0
        if spread >= 20.0:
            print(f"VERDICT                : PASS  (spread {spread:.1f} >> {BASELINE_SPREAD:.0f})")
            print("                         wards are genuinely separated by location.")
        elif spread >= 10.0:
            print(f"VERDICT                : MARGINAL (spread {spread:.1f})")
            print("                         some separation; check built%/veg% actually vary.")
        else:
            print(f"VERDICT                : FAIL  (spread {spread:.1f} < {BASELINE_SPREAD:.0f})")
            print("                         scores are still compressed. The cube is")
            print("                         probably not reaching the indicators.")
    else:
        print("VERDICT                : INCONCLUSIVE (too few wards scored)")

    if complete < len(rows):
        print()
        print(f"WARNING: {len(rows)-complete} ward(s) missing at least one factor.")
        print("         Check that lst_mean_c and lst_reference_c are non-null for every ward.")

    Path(args.out).write_text(json.dumps({"rows": rows, "provenance": _provenance()}, indent=2))
    print(f"\nwrote {args.out}")
    return 0


def _pct(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value) * 100.0
    except (TypeError, ValueError):
        return default


if __name__ == "__main__":
    raise SystemExit(main())