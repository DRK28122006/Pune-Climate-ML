"""Pipeline CLI — the single entry point.

    .venv/bin/python -m ml_pipeline.cli assess --ward 12 \
        --built-up 2000 --plot 4000 --demo-materials

    .venv/bin/python -m ml_pipeline.cli ward-profile --ward 12
    .venv/bin/python -m ml_pipeline.cli build-data

Every layer runs offline once the two SQLite indexes exist. Satellite-derived
indicators (LST, impervious, vegetation, slope) are read from the epoch cube if
it has been built, and are otherwise reported as unavailable rather than
estimated.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ml_pipeline.core import geometry as G
from ml_pipeline.core.canopy import CanopyLedger, TreeRecord
from ml_pipeline.core.recommendations import RecommendationEngine
from ml_pipeline.core.relocation import RelocationSitingEngine
from ml_pipeline.core.scoring import score_project
from ml_pipeline.intake.validate import validate_submission
from ml_pipeline.report.render import render_report

REF_DB = REPO / "ml_pipeline" / "data" / "reference_layers.sqlite"

CONFIG = REPO / "ml_pipeline" / "config"
SPECIES = json.loads((CONFIG / "species.json").read_text())
MATERIALS = json.loads((CONFIG / "materials.json").read_text())
REGION = json.loads((CONFIG / "regions" / "pune.json").read_text())

EPOCH_CUBE = REPO / "ml_pipeline" / "data" / "epoch_cube.json"

# A representative mid-rise RC frame, used by --demo-materials so the pipeline
# can be exercised end to end before a real BOQ is available.
DEMO_MATERIALS = [
    {"name": "cement", "quantityKg": 180_000},
    {"name": "steel_reinforcement", "quantityKg": 95_000},
    {"name": "brick", "quantityKg": 210_000},
    {"name": "river_sand", "quantityKg": 140_000},
    {"name": "glass", "quantityKg": 12_000},
    {"name": "aluminium", "quantityKg": 4_500},
]


def load_epoch_cube() -> Optional[Dict[str, Any]]:
    if not EPOCH_CUBE.exists():
        return None
    try:
        return json.loads(EPOCH_CUBE.read_text())
    except json.JSONDecodeError:
        return None


def indicators_from_cube(
    ring: List[Any], cube: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Read satellite indicators for a ring from the precomputed cube.

    Returns an empty dict when no cube exists, so the scorer excludes heat and
    says so, rather than inventing a land-cover percentage.
    """
    if not cube:
        return {}
    centroid = G.polygon_centroid([(float(a), float(b)) for a, b in ring])
    cells = cube.get("cells") or {}
    key = f"{round(centroid[0], 3)}_{round(centroid[1], 3)}"
    cell = cells.get(key)
    if not cell:
        # Nearest cell fallback.
        best, best_d = None, None
        for k, v in cells.items():
            try:
                lon_s, lat_s = k.split("_")
                d = G.haversine_m(centroid, (float(lon_s), float(lat_s)))
            except ValueError:
                continue
            if best_d is None or d < best_d:
                best, best_d = v, d
        cell = best if (best_d is not None and best_d < 2000.0) else None
    return dict(cell) if cell else {}


def _pct(value: Any, default: float = 0.0) -> float:
    """Cube land-cover values are fractions; the scorer expects percent."""
    if value is None:
        return default
    try:
        return float(value) * 100.0
    except (TypeError, ValueError):
        return default


def _pct_cube_or_fallback(cube_value: Any, fallback_percent: float) -> float:
    """Convert a cube fraction to percent, or take a CLI fallback as-is.

    FIX 2026-10-10: the old code ran the already-percent CLI fallbacks
    (--impervious 70, --vegetation 24) through _pct, multiplying them by
    100 (70 -> 7000 -> clamped 100). A missing cube therefore scored flood
    at full impervious and dropped green -- a plausible-looking answer
    built on a default, the exact failure mode this project exists to
    avoid. Cube values are fractions (x100); fallbacks are percent (as-is).
    """
    if cube_value is None:
        return float(fallback_percent)
    try:
        return float(cube_value) * 100.0
    except (TypeError, ValueError):
        return float(fallback_percent)


def cmd_ward_profile(args: argparse.Namespace) -> int:
    p = G.ward_tree_profile(args.ward)
    if not p.get("available"):
        print(f"unavailable: {p.get('reason')}")
        return 1
    print(f"WARD {p['ward_no']}  {p.get('ward_name')}")
    print(f"  area            {p['ward_area_m2']/1e6:.3f} km2")
    if not p.get("trees_are_reliable", True):
        print("  trees           DATA NOT LOADED FOR THIS WARD")
    else:
        print(f"  trees           {p['trees']:,}")
    print(f"  mature >=60cm   {p['mature_girth60']:,}")
    print(f"  heritage >=90cm {p['heritage_girth90']:,}")
    print(f"  rare            {p['rare']:,}")
    print(f"  dead            {p['dead']:,}")
    print(f"  median girth    {p['median_girth_cm']} cm")
    print(f"  canopy          {p['canopy_m2']:,.0f} m2  ({p['canopy_cover_pct']}%)")
    for n in p.get("notes") or []:
        print(f"\n  !! {n}")
    cov = p.get("census_coverage") or {}
    if cov.get("warning"):
        print(f"\n  !! COVERAGE: {cov['warning']}")
    return 0


def _ward_ring(ward_no: int):
    import sqlite3
    conn = sqlite3.connect(str(REF_DB))
    try:
        row = conn.execute(
            "SELECT ring_json FROM wards WHERE ward_no = ?", (ward_no,)
        ).fetchone()
    finally:
        conn.close()
    return json.loads(row[0]) if row else None


def cmd_assess(args: argparse.Namespace) -> int:
    ring = _ward_ring(args.ward)
    if ring is None:
        print(f"no polygon for ward {args.ward}; run build-data first", file=sys.stderr)
        return 1

    # A site footprint is a centred sub-polygon of the ward at the requested
    # built-up area, so the command is runnable without a drawn boundary.
    site_ring = _footprint_in_ward(ring, args.built_up, args.plot)

    payload: Dict[str, Any] = {
        "geometry": [[float(a), float(b)] for a, b in site_ring],
        "builtUpAreaSqm": args.built_up,
        "plotAreaSqm": args.plot,
        "materials": DEMO_MATERIALS if args.demo_materials else json.loads(args.materials),
        "storeys": args.storeys,
        "projectType": args.project_type,
        "epoch": 2024,
    }

    v = validate_submission(payload, REGION)
    if not v.valid:
        print("VALIDATION FAILED")
        for e in v.errors:
            print(f"  [{e['code']}] {e['message']}")
        return 1

    geom = v.geometry
    if geom is None:
        print("VALIDATION FAILED: geometry could not be measured", file=sys.stderr)
        return 1

    # Census coverage is a hard precondition for any tree-derived figure.
    # If the site falls in a block that was never loaded, the honest answer is
    # "no census data here", not "0 trees, therefore nothing to preserve".
    coverage = G.census_coverage()
    site_trees = G.trees_in_ring(site_ring)
    site_in_loaded_block = len(site_trees) > 0
    census_reliable = coverage.get("coverage_complete", False) or site_in_loaded_block

    trees_raw = site_trees
    ledger_engine = CanopyLedger(SPECIES)
    records = [
        TreeRecord(
            tree_id=t["tree_id"], lon=t["lon"], lat=t["lat"],
            botanical_name=t["botanical_name"] or "",
            girth_cm=t["girth_cm"] or 0.0, height_m=t["height_m"] or 0.0,
            canopy_dia_m=t["canopy_dia_m"] or 0.0,
            condition=t["condition"] or "", is_rare=bool(t["is_rare"]),
        )
        for t in trees_raw
    ]
    ledger = ledger_engine.process_site(records, plot_area_m2=geom.area_m2)
    ledger["census_coverage"] = coverage
    ledger["census_reliable_for_this_site"] = census_reliable

    cube = load_epoch_cube()
    sat = indicators_from_cube(site_ring, cube)
    indicators = {
        # Cube values are fractions (0..1) from Dynamic World / NDVI; the
        # scorer's `*_pct` fields are percent. Convert once, here.
        "impervious_pct": _pct_cube_or_fallback(
            sat.get("built_pct", sat.get("impervious_pct")), args.impervious
        ),
        "vegetation_pct": _pct_cube_or_fallback(
            sat.get("vegetation_pct"), args.vegetation
        ),
        "water_pct": _pct(sat.get("water_pct", 0.0)),
        # Bare soil drives flood's curve number and was previously dropped from
        # the composite entirely. The cube carries two figures: `bare_pct` (annual
        # modal label, which a majority vote drives to ~0 because bare ground is
        # transient) and `bare_season_pct` (pre-monsoon, when bare earth actually
        # peaks). The seasonal one is the physically meaningful estimate, so it
        # wins when present.
        "bare_pct": _pct(
            sat.get("bare_season_pct", sat.get("bare_pct", 0.0))
        ),
        "lst_mean_c": sat.get("lst_mean_c"),
        "lst_reference_c": sat.get("lst_reference_c"),
        "lst_max_c": sat.get("lst_max_c"),
        # Night LST (MODIS Terra+Aqua) is passed through unconverted: it is
        # already Celsius in the cube, unlike the fraction bands above.
        # score_project prefers it over the day pair (see scoring.py).
        "lst_night_mean_c": sat.get("lst_night_mean_c"),
        "mean_slope_deg": sat.get("mean_slope_deg", args.slope),
        "dist_to_storm_drain_m": v.indicators.get("dist_to_storm_drain_m"),
    }

    result = score_project(v.site, indicators, REGION, MATERIALS, ledger=ledger)
    recs = RecommendationEngine().build_recommendations(
        v.site, indicators, REGION, MATERIALS, ledger
    )

    relocate_n = sum(
        n for a, n in (ledger.get("action_counts") or {}).items() if a == "RELOCATE"
    )
    relocation = None
    if relocate_n:
        relocation = RelocationSitingEngine().rank_sites(geom.centroid, relocate_n)

    validation_info = {"ward_no": v.site.get("ward_no"),
                       "ward_name": v.site.get("ward_name")}
    # Add the ward's prabhag (administrative circle) so the site line is
    # recognisable to a PMC officer, who thinks in circles, not ward numbers.
    if validation_info["ward_no"] is not None:
        try:
            crow = sqlite3.connect(str(REF_DB))
            prabhag = crow.execute(
                "SELECT prabhag_name FROM parks WHERE ward_no = ? "
                "GROUP BY prabhag_name ORDER BY COUNT(*) DESC LIMIT 1",
                (validation_info["ward_no"],),
            ).fetchone()
            crow.close()
            if prabhag and prabhag[0]:
                validation_info["prabhag_name"] = prabhag[0]
        except Exception:
            pass

    report = render_report(
        result, recs, ledger=ledger, relocation=relocation,
        region_config=REGION,
        validation=validation_info,
        role=args.role,
        indicators=indicators,
    )
    print(report)

    if args.json_out:
        Path(args.json_out).write_text(json.dumps({
            "validation": v.to_dict(),
            "score": result,
            "recommendations": recs,
            "canopy": ledger,
            "relocation": relocation,
            "indicators": indicators,
            "satellite_cube_available": bool(cube),
        }, indent=2, default=str))
        print(f"\nJSON written to {args.json_out}")
    return 0


def _footprint_in_ward(ring, built_up: float, plot: float):
    """Carve a plot-sized square at the ward centroid, scaled to built-up area.

    Deliberately simple and obviously correct. Real submissions supply their own
    boundary; this exists so the pipeline is runnable from the command line.
    """
    import math
    cx = sum(p[0] for p in ring) / len(ring)
    cy = sum(p[1] for p in ring) / len(ring)
    side_m = max(plot, built_up) ** 0.5
    dlat = (side_m / 2.0) / 110_574.0
    dlon = (side_m / 2.0) / (111_320.0 * math.cos(math.radians(cy)))
    return [
        (cx - dlon, cy - dlat), (cx + dlon, cy - dlat),
        (cx + dlon, cy + dlat), (cx - dlon, cy + dlat),
        (cx - dlon, cy - dlat),
    ]


def cmd_build_data(args: argparse.Namespace) -> int:
    from ml_pipeline.data import reference_layers, tree_index
    print("== tree index ==")
    # find_parts() globs a single directory. The 17 census parts live in
    # ml_pipeline/data/census/, NOT at the repo root, so passing REPO alone
    # finds the original single ptc_part1.csv and silently builds a 6%-complete
    # index. Pass every directory that may hold parts, and log which was used.
    part_sets: List[str] = []
    for d in (REPO / "ml_pipeline" / "data" / "census", REPO):
        found = tree_index.find_parts(str(d))
        if found:
            print(f"   {d}: {len(found)} part(s)")
            part_sets.extend(found)
    if not part_sets:
        print("no census parts found", file=sys.stderr)
        print("run ml_pipeline/data/fetch_census_parts.py --all first", file=sys.stderr)
        return 1
    stats = tree_index.build(part_sets, str(REPO / "ml_pipeline" / "data" / "tree_index.sqlite"))
    print(json.dumps({k: v for k, v in stats.items() if k != "top_species"}, indent=2))
    print("\n== reference layers ==")
    ref = reference_layers.build(REPO / "ml_pipeline" / "data" / "reference_layers.sqlite")
    print(json.dumps(ref, indent=2))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="ml_pipeline", description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build-data", help="build the tree and reference indexes")
    b.set_defaults(func=cmd_build_data)

    w = sub.add_parser("ward-profile", help="census profile for one ward")
    w.add_argument("--ward", type=int, required=True)
    w.set_defaults(func=cmd_ward_profile)

    a = sub.add_parser("assess", help="score a site")
    a.add_argument("--ward", type=int, required=True)
    a.add_argument("--built-up", type=float, required=True, dest="built_up")
    a.add_argument("--plot", type=float, required=True)
    a.add_argument("--storeys", type=int, default=None)
    a.add_argument("--project-type", default=None, dest="project_type")
    a.add_argument("--role", default="urban_planner",
                   choices=["municipal_authority", "urban_planner",
                            "environmental_consultant", "public_viewer"])
    a.add_argument("--impervious", type=float, default=70.0,
                   help="used only when no satellite cube exists")
    a.add_argument("--vegetation", type=float, default=24.0,
                   help="used only when no satellite cube exists")
    a.add_argument("--slope", type=float, default=3.0)
    a.add_argument("--materials", default="[]")
    a.add_argument("--demo-materials", action="store_true")
    a.add_argument("--json-out", default=None, dest="json_out")
    a.set_defaults(func=cmd_assess)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
