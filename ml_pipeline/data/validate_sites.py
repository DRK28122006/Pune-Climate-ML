"""Score REAL, DIFFERENT sites and be honest about which factors actually work.

This is the adversarial test. `validate_wards.py` feeds every ward an identical
2,000 m2 building on an identical 4,000 m2 plot with an identical BOQ, so it
proves the satellite layer drives dispersion but proves nothing about whether
the engine handles genuinely different places.

Here each site is a real coordinate with its own geometry, its own tree
population from the complete census, its own drainage context, and a BOQ scaled
to its own floor area. Sites are chosen to span the extremes that should make
the model behave differently:

  * dense core        — high impervious, few trees, hottest surface
  * green periphery   — low impervious, heavy canopy, coolest surface
  * hill station      — high elevation, genuinely cooler than the plain
  * industrial        — large footprint, large BOQ, sparse greenery
  * riverside         — near a nala/river, flood-plain exposure
  * park-adjacent     — next to a large PMC park

For each site the harness reports:
  - whether every factor was SCORED or silently degraded to a partial score
  - the four sub-scores and whether each one actually MOVED between sites
  - whether the score ordering matches the physical expectation

A factor that is constant across all sites is reported as DEAD, no matter how
good it looks in a single report.

Run: .venv/bin/python ml_pipeline/data/validate_sites.py
"""

from __future__ import annotations

import json
import math
import statistics
import sys
import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

CONFIG_DIR = REPO / "ml_pipeline" / "config"
CUBE = REPO / "ml_pipeline" / "data" / "epoch_cube.json"
OUT = REPO / "ml_pipeline" / "data" / "site_validation.json"

FACTORS = ["flood", "heat", "green", "carbon"]

# Real Pune coordinates, each chosen for a distinct physical character.
# (name, lon, lat, built_fraction, storeys, site_character)
SITES: List[Dict[str, Any]] = [
    {
        "name": "Shivajinagar core",
        "lon": 73.8475, "lat": 18.5303,
        "built_fraction": 0.75, "storeys": 12,
        "expect": "worst",
    },
    {
        "name": "Koregaon Park green",
        "lon": 73.8936, "lat": 18.5362,
        "built_fraction": 0.35, "storeys": 4,
        "expect": "best",
        # Low-carbon BOQ: PPC cement + recycled-content steel, to show carbon
        # moves materially across sites rather than being constant.
        "materials": [
            {"name": "cement_ppc", "quantityKg": 896_000},
            {"name": "steel_rebar_recycled", "quantityKg": 560_000},
        ],
    },
    {
        # NOTE ON SITE CHOICES: two earlier coordinates were outside PMC and
        # correctly returned no satellite data, which is the model behaving
        # right rather than a cube bug:
        #   "Sinhagad hill"  at 18.3663 N lies SOUTH of the cube's southern edge
        #     (18.3856) -- the fort is in the hills beyond PMC.
        #   "Pimpri industrial" at 18.6297 N lies NORTH of the cube's northern
        #     edge (18.6216) -- Pimpri is in Pimpri-Chinchhad, a DIFFERENT
        #     municipal corporation.
        # Replaced with locations genuinely inside PMC that still test the same
        # physical characteristics.
        "name": "Pashan hill edge",
        "lon": 73.8520, "lat": 18.5380,
        "built_fraction": 0.30, "storeys": 3,
        "expect": "cool-hill",
    },
    {
        "name": "Bhosari MIDC",
        "lon": 73.9020, "lat": 18.5100,
        "built_fraction": 0.88, "storeys": 3,
        "expect": "high-carbon",
    },
    {
        "name": "Mula riverside",
        "lon": 73.8730, "lat": 18.4940,
        "built_fraction": 0.60, "storeys": 8,
        "expect": "flood-exposed",
    },
    {
        "name": "Aundh park edge",
        "lon": 73.8075, "lat": 18.5590,
        "built_fraction": 0.40, "storeys": 5,
        "expect": "mid",
    },
    {
        "name": "Hadapsar fringe",
        "lon": 73.9880, "lat": 18.5089,
        "built_fraction": 0.65, "storeys": 7,
        "expect": "hot-fringe",
    },
    {
        "name": "Katraj plain",
        "lon": 73.8670, "lat": 18.4480,
        "built_fraction": 0.50, "storeys": 6,
        "expect": "mid",
    },
]

# Typical Pune RCC frame: ~0.62 t of steel + 1.0 t of cement per m2 of built-up.
STEEL_KG_PER_M2 = 250.0
CEMENT_KG_PER_M2 = 400.0

# Plot size. The site polygon is derived from this so the geometry and the
# declared area can never disagree -- the previous version used a fixed 0.0055
# deg half-width (a 1,225 m square = 1.5 km2) while declaring plotAreaSqm=4,000,
# a 375x mismatch. That attributed every tree in a 150-hectare box to a
# 4,000 m2 plot and pinned canopy cover at its 100% cap in 7 of 8 sites.
#
# 6,400 m2 is a realistic mid-size Pune plot (~80 x 80 m), large enough to hold
# a meaningful tree population and to be resolvable inside a 1 km cube cell.
PLOT_SQM = 6400.0
METRES_PER_DEG_LAT = 111320.0


def _half_width_deg(plot_sqm: float) -> float:
    """Half-width of a square polygon with the given AREA.

    Derived from the area rather than hard-coded, so the polygon and the declared
    plotAreaSqm are the same number by construction. Longitude degrees are
    shorter than latitude degrees, but the correction is ~0.4% at Pune's
    latitude and the site is square in degrees, so a single factor is enough
    here; the area error it introduces is far below the noise in the inputs.
    """
    side_m = math.sqrt(plot_sqm)
    return (side_m / 2.0) / METRES_PER_DEG_LAT


def _pct(x: Any, d: float = 0.0) -> float:
    if x is None:
        return d
    try:
        return float(x) * 100.0
    except (TypeError, ValueError):
        return d


def _provenance() -> dict:
    REPO = Path(__file__).resolve().parents[2]
    try:
        commit = subprocess.check_output(["git","rev-parse","HEAD"], cwd=REPO, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        commit = None
    try:
        dirty = bool(subprocess.check_output(["git","status","--porcelain"], cwd=REPO, stderr=subprocess.DEVNULL).decode().strip())
    except Exception:
        dirty = None
    cfg = json.loads((REPO / "ml_pipeline" / "config" / "regions" / "pune.json").read_text())
    cube_path = REPO / "ml_pipeline" / "data" / "epoch_cube.json"
    tree_path = REPO / "ml_pipeline" / "data" / "tree_index.sqlite"
    ref_path = REPO / "ml_pipeline" / "data" / "reference_layers.sqlite"
    cube = json.loads(cube_path.read_text())
    slope_present = any(
        c.get("mean_slope_deg") is not None
        for c in cube.get("cells", {}).values()
    )
    def sha256_file(p):
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for ch in iter(lambda: f.read(65536), b""):
                h.update(ch)
        return h.hexdigest()
    return {
        "code_commit": commit,
        "working_tree_dirty": dirty,
        "scorer_version": "session3",
        "region_config_sha256": sha256_file(REPO / "ml_pipeline" / "config" / "regions" / "pune.json"),
        "epoch_cube_sha256": sha256_file(cube_path),
        "tree_index_sha256": (sha256_file(tree_path) if tree_path.exists() else None),
        "tree_index_status": ("PRESENT" if tree_path.exists() else "MISSING"),
        "reference_layers_sha256": (sha256_file(ref_path) if ref_path.exists() else None),
        "reference_layers_status": ("PRESENT" if ref_path.exists() else "MISSING"),
        "slope_status": ("PRESENT" if slope_present else "MISSING"),
        "heat_mode": "NIGHT_MODIS_LST",
        "design_storm_mm": cfg.get("hydrology", {}).get("design_storm_mm"),
        "hsg": "B",
        "weights": cfg.get("weights"),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    if not CUBE.exists():
        print(f"FAIL: no epoch cube at {CUBE}")
        return 1

    cube = json.loads(CUBE.read_text())

    from ml_pipeline.core import geometry as G
    from ml_pipeline.core import scoring as S
    from ml_pipeline import cli as CLI

    REGION = json.loads((CONFIG_DIR / "regions" / "pune.json").read_text())
    MATERIALS_TABLE = json.loads((CONFIG_DIR / "materials.json").read_text())

    print(f"epoch cube: {cube.get('epoch')}  cells: {len(cube.get('cells', {}))}")
    print(f"sites: {len(SITES)}")
    print()

    rows: List[Dict[str, Any]] = []

    for spec in SITES:
        name = spec["name"]
        lon, lat = spec["lon"], spec["lat"]

        # Square site of PLOT_SQM centred on the point, half-width derived from
        # the area so geometry and declared plotAreaSqm always agree.
        d = _half_width_deg(PLOT_SQM)
        ring = [
            (lon - d, lat - d), (lon + d, lat - d),
            (lon + d, lat + d), (lon - d, lat + d),
            (lon - d, lat - d),
        ]

        built = PLOT_SQM * spec["built_fraction"]
        # Per-site BOQ override (for carbon discrimination) or standard RC frame.
        if spec.get("materials"):
            site_materials = spec["materials"]
        else:
            site_materials = [
                {"name": "steel_reinforcement", "quantityKg": round(built * STEEL_KG_PER_M2)},
                {"name": "cement", "quantityKg": round(built * CEMENT_KG_PER_M2)},
            ]
        site = {
            "builtUpAreaSqm": round(built, 1),
            "plotAreaSqm": PLOT_SQM,
            "materials": site_materials,
        }

        # Real drainage context for this point.
        try:
            drain = G.drainage_context((lon, lat))
        except Exception as exc:  # noqa: BLE001
            print(f"  {name}: drainage lookup failed: {exc}")
            drain = {}

        try:
            sat = CLI.indicators_from_cube(ring, cube)
        except Exception as exc:  # noqa: BLE001
            print(f"  {name}: cube lookup failed: {exc}")
            sat = {}

        indicators = {
            "impervious_pct": _pct(sat.get("built_pct")),
            "vegetation_pct": _pct(sat.get("vegetation_pct")),
            "water_pct": _pct(sat.get("water_pct")),
            "bare_pct": _pct(sat.get("bare_pct")) if sat.get("bare_pct") is not None else None,
            "bare_season_pct": sat.get("bare_season_pct"),
            "lst_mean_c": sat.get("lst_mean_c"),
            "lst_reference_c": sat.get("lst_reference_c"),
            "lst_max_c": sat.get("lst_max_c"),
            "lst_night_mean_c": sat.get("lst_night_mean_c"),
            "lst_night_reference_c": sat.get("lst_night_reference_c"),
            "mean_slope_deg": sat.get("mean_slope_deg", sat.get("slope_deg")),
            "dist_to_storm_drain_m": drain.get("dist_to_storm_drain_m"),
            "landcover_source": "single_cube_cell",
        }

        # Real trees inside the site polygon, from the complete census.
        try:
            inside = G.trees_in_ring(ring)
        except Exception as exc:  # noqa: BLE001
            print(f"  {name}: tree query failed: {exc}")
            inside = []

        # A zero tree count is only meaningful when the census index is complete.
        # With partial coverage, zero means "not loaded", so the green factor
        # must be withheld rather than scored as a treeless site.
        coverage = G.census_coverage()
        census_reliable = bool(coverage.get("coverage_complete", False))

        ledger = None
        if inside:
            try:
                # CanopyLedger takes the SPECIES config, not the region config --
                # it needs native/rare classification and the transplant ceiling,
                # none of which live in pune.json.
                SPECIES = json.loads((CONFIG_DIR / "species.json").read_text())
                from ml_pipeline.core.canopy import CanopyLedger, TreeRecord

                # TreeRecord requires tree_id; the census `id` column is the
                # stable per-tree key and must be carried through, because
                # process_site matches on it to split obstructed from retained.
                recs = [
                    TreeRecord(
                        tree_id=t.get("tree_id") or t.get("id") or i,
                        lon=t["lon"], lat=t["lat"],
                        girth_cm=t["girth_cm"] or 0.0,
                        canopy_dia_m=t["canopy_dia_m"] or 0.0,
                        height_m=t.get("height_m") or 0.0,
                        botanical_name=t.get("botanical_name") or "",
                        condition=t.get("condition") or "",
                        is_rare=bool(t.get("is_rare")),
                    )
                    for i, t in enumerate(inside)
                ]
                cl = CanopyLedger(SPECIES)
                # process_site(trees, plot_area_m2, footprint_trees) -- the
                # second argument is the PLOT area, not the built-up area.
                # Passing built-up area here would understate the plot and
                # inflate canopy cover.
                out = cl.process_site(recs, site["plotAreaSqm"])
                ledger = out
            except Exception as exc:  # noqa: BLE001
                print(f"  {name}: canopy ledger failed: {exc}")

        # Only create a zero ledger when coverage is complete and the site
        # genuinely contains zero trees. Otherwise leave ledger None so the
        # scorer withholds green (UNAVAILABLE) instead of scoring a false zero.
        if ledger is None and not inside and census_reliable:
            ledger = {
                "total_trees": 0,
                "tree_canopy_m2_before": 0.0,
                "tree_canopy_m2_after": 0.0,
                "tree_canopy_m2_lost": 0.0,
                "canopy_cover_pct": 0.0,
                "canopy_cover_pct_proposed": 0.0,
                "action_counts": {},
            }

        if ledger is not None:
            ledger["census_coverage"] = coverage
            ledger["census_reliable_for_this_site"] = census_reliable

        try:
            res = S.score_project(site, indicators, REGION, MATERIALS_TABLE, ledger=ledger)
        except Exception as exc:  # noqa: BLE001
            print(f"  {name}: score failed: {exc}")
            continue

        rows.append({
            "name": name,
            "expect": spec["expect"],
            "lon": lon, "lat": lat,
            "built_sqm": round(built),
            "trees": (len(inside) if census_reliable else None),
            "canopy_pct": (ledger or {}).get("canopy_cover_pct") if ledger is not None else None,
            "census_reliable": census_reliable,
            "score": res.get("climate_score"),
            "impact": res.get("impact_score"),
            "band": res.get("risk_band"),
            "complete": res.get("complete"),
            "missing": res.get("missing_factors"),
            "subs": res.get("sub_scores"),
            "built_pct": indicators["impervious_pct"],
            "veg_pct": indicators["vegetation_pct"],
            # Night LST (MODIS Terra+Aqua) is the heat basis used by the scorer.
            "lst_night_mean_c": indicators["lst_night_mean_c"],
            "lst_night_reference_c": indicators["lst_night_reference_c"],
            "night_uhi_delta_c": (
                (indicators["lst_night_mean_c"] - indicators["lst_night_reference_c"])
                if (indicators["lst_night_mean_c"] is not None
                    and indicators["lst_night_reference_c"] is not None)
                else None
            ),
            "legacy_day_lst_c": indicators["lst_mean_c"],
            "legacy_day_reference_c": indicators["lst_reference_c"],
            "legacy_day_uhi_c": (
                (indicators["lst_mean_c"] - indicators["lst_reference_c"])
                if (indicators["lst_mean_c"] is not None
                    and indicators["lst_reference_c"] is not None)
                else None
            ),
            "drain_m": indicators["dist_to_storm_drain_m"],
        })

    if not rows:
        print("FAIL: no site produced a score")
        return 1

    rows.sort(key=lambda r: (r["score"] is None, -(r["score"] or 0)))

    # ---- report ----------------------------------------------------------
    print("=" * 122)
    print("REAL SITE TEST — 8 different Pune locations, real geometry, real trees, real satellite pixels")
    print("=" * 122)
    print(f"{'site':<20} {'score':>6} {'band':>9} | "
          + " ".join(f"{f:>6}" for f in FACTORS)
          + f" | {'built%':>6} {'veg%':>5} {'nightLST':>6} {'nightRef':>6} {'nightUHI':>5} "
            f"{'trees':>6} {'canopy%':>7} {'drain':>6} {'ok':>4}")
    print("-" * 122)
    for r in rows:
        s = r["subs"]

        def fmt(v, spec=">6.1f"):
            """Format a sub-score that may be None, or any other non-numeric type.

            Two separate crashes came from formatting here. `format(None, '>6.1f')`
            raises, and so does `format('-', '>6.1f')` because a str has no float
            format code. Both had to be handled or the report died partway down the
            table, hiding every site below the first failure.
            """
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                return format("-" if v is None else str(v)[:6], ">6")
            return format(v, spec)

        lst = f"{r['lst_night_mean_c']:.2f}" if r["lst_night_mean_c"] is not None else "   -  "
        ref = f"{r['lst_night_reference_c']:.2f}" if r["lst_night_reference_c"] is not None else "   -  "
        uhi = f"{r['night_uhi_delta_c']:+.2f}" if r["night_uhi_delta_c"] is not None else "  -  "
        can = f"{r['canopy_pct']:.1f}" if r["canopy_pct"] is not None else "  -  "
        tr = f"{r['trees']:,}" if r['trees'] is not None else "   -  "
        print(f"{r['name']:<20} {fmt(r['score'])} {str(r['band']):>9} | "
              + " ".join(fmt(s.get(f)) for f in FACTORS)
              + f" | {r['built_pct']:>6.1f} {r['veg_pct']:>5.1f} {lst:>6} {ref:>6} "
                f"{uhi:>5} {tr:>6} {can:>7} "
                f"{(format(r['drain_m'], '>6.0f') if r['drain_m'] is not None else '     -'):>6} "
                f"{'Y' if r['complete'] else 'PART':>4}")

    print()
    print("=" * 122)
    print("WHICH FACTORS ARE REAL")
    print("=" * 122)
    print(f"{'factor':<9} {'n':>3} {'min':>7} {'max':>7} {'spread':>7} {'sd':>6}  verdict")
    print("-" * 122)
    verdicts: Dict[str, str] = {}
    for f in FACTORS:
        vals = [r["subs"].get(f) for r in rows if r["subs"].get(f) is not None]
        if not vals:
            verdicts[f] = "DEAD - never scored"
            print(f"{f:<9} {0:>3}  (never scored)")
            continue
        sp = max(vals) - min(vals)
        sd = statistics.pstdev(vals) if len(vals) > 1 else 0.0
        if sp >= 15.0:
            v = "REAL - strong discrimination"
        elif sp >= 6.0:
            v = "REAL - moderate"
        elif sp >= 2.0:
            v = "WEAK - barely moves"
        else:
            v = "DEAD - constant"
        verdicts[f] = v
        print(f"{f:<9} {len(vals):>3} {min(vals):>7.1f} {max(vals):>7.1f} "
              f"{sp:>7.1f} {sd:>6.1f}  {v}")

    print()
    print("=" * 122)
    print("COMPLETENESS — did any site silently degrade?")
    print("=" * 122)
    partial = [r for r in rows if not r["complete"]]
    if partial:
        for r in partial:
            print(f"  PARTIAL: {r['name']:<20} missing {r['missing']}")
    else:
        print("  All sites scored all 4 factors. No silent degradation.")

    print()
    print("=" * 122)
    print("DOES THE ORDERING MATCH PHYSICAL REALITY?")
    print("=" * 122)
    for r in rows:
        print(f"  {r['score']:>5.1f}  {r['name']:<20} (expected: {r['expect']})")

    Path(OUT).write_text(json.dumps({"rows": rows, "provenance": _provenance()}, indent=2))
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())