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

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

CONFIG_DIR = REPO / "ml_pipeline" / "config"
CUBE = REPO / "ml_pipeline" / "data" / "epoch_cube.json"
OUT = REPO / "ml_pipeline" / "data" / "ward_validation.json"

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


def load_context():
    """Import the pipeline pieces, failing loudly if a database is missing."""
    from ml_pipeline.core import geometry as G
    from ml_pipeline.core import scoring as S
    from ml_pipeline.data import reference_layers as R

    return G, S, R


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

    rows: List[Dict[str, Any]] = []

    for w in wards:
        try:
            prof = G.ward_tree_profile(w)
        except Exception as exc:  # noqa: BLE001
            print(f"  ward {w}: profile failed: {exc}")
            continue
        if not prof.get("available"):
            print(f"  ward {w}: no ward geometry -- {prof.get('reason')}")
            continue

        # ward_tree_profile returns a SUMMARY, not the polygon. Pull the ring
        # from the reference db the same way it does. (It has no 'ring' key --
        # assuming one silently scored nothing.)
        ring = _ward_ring(G, w)
        if ring is None:
            print(f"  ward {w}: could not read ward polygon")
            continue

        site = {
            "builtUpAreaSqm": BUILT_UP_SQM,
            "plotAreaSqm": PLOT_SQM,
            "materials": MATERIALS,
        }

        try:
            sat = CLI.indicators_from_cube(ring, cube)
        except Exception as exc:  # noqa: BLE001
            print(f"  ward {w}: cube lookup failed: {exc}")
            sat = {}

        # Cube landcover is a FRACTION; the scorer's *_pct fields are percent.
        indicators = {
            "impervious_pct": _pct(sat.get("built_pct")),
            "vegetation_pct": _pct(sat.get("vegetation_pct")),
            "water_pct": _pct(sat.get("water_pct")),
            "lst_mean_c": sat.get("lst_mean_c"),
            "lst_reference_c": sat.get("lst_reference_c"),
            "lst_max_c": sat.get("lst_max_c"),
            "mean_slope_deg": sat.get("mean_slope_deg", 3.0),
            "dist_to_storm_drain_m": prof.get("dist_to_storm_drain_m", 150.0),
        }

        try:
            res = S.score_project(site, indicators, REGION, MATERIALS_TABLE)
        except Exception as exc:  # noqa: BLE001
            print(f"  ward {w}: score failed: {exc}")
            continue

        rows.append({
            "ward": w,
            # score_project returns climate_score / impact_score. There is no
            # 'score' key -- reading it yielded None for every ward while the
            # factors were all present, which looked like a scoring failure.
            "score": res.get("climate_score"),
            "impact": res.get("impact_score"),
            "risk_band": res.get("risk_band"),
            "complete": res.get("complete"),
            "built_pct": indicators["impervious_pct"],
            "veg_pct": indicators["vegetation_pct"],
            "lst_mean_c": indicators["lst_mean_c"],
            "lst_ref_c": indicators["lst_reference_c"],
            "uhi_delta_c": (indicators["lst_mean_c"] - indicators["lst_reference_c"])
                           if (indicators["lst_mean_c"] is not None and indicators["lst_reference_c"] is not None)
                           else None,
            # ward_tree_profile names these 'trees' and 'canopy_cover_pct'.
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

    Path(args.out).write_text(json.dumps({"rows": rows}, indent=2))
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