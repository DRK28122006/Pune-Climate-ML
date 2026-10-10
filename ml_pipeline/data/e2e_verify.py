"""END-TO-END VERIFICATION — every number comes from the real ML pipeline CLI.

Rules this harness follows, deliberately:
  * Every score is produced by `python -m ml_pipeline.cli assess --json-out`,
    NOT by calling scoring functions directly. Nothing is reimplemented here.
  * Locations are real PMC wards, so each one resolves to its own satellite
    cell, its own real tree population from the complete census, and its own
    real distance to PMC stormwater outfalls.
  * No invented inputs. The BOQ is the pipeline's own --demo-materials.

It also checks the composite curve number against the published NRCS TR-55
urban formula, because that is the one piece of flood physics that has an
external standard to be wrong against.

Run: .venv/bin/python ml_pipeline/data/e2e_verify.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[2]
OUTDIR = REPO / "ml_pipeline" / "data" / "e2e"
OUTDIR.mkdir(parents=True, exist_ok=True)

# Real PMC wards chosen to span the physical range: dense core, mid-city,
# green periphery, hill-adjacent, riverside, new-development fringe.
WARDS = [3, 7, 12, 13, 21, 25, 30, 37, 39, 44, 33, 41]

# Identical proposal at every location, so the ONLY thing varying is place.
BUILT_UP = 3000
PLOT = 8000
STOREYS = 8

FACTORS = ["flood", "heat", "green", "carbon"]


def run_cli(ward: int) -> Dict[str, Any]:
    """Run the real pipeline CLI for one ward and return its parsed JSON."""
    out = OUTDIR / f"ward_{ward:02d}.json"
    cmd = [
        sys.executable, "-m", "ml_pipeline.cli", "assess",
        "--ward", str(ward),
        "--built-up", str(BUILT_UP),
        "--plot", str(PLOT),
        "--storeys", str(STOREYS),
        "--demo-materials",
        "--role", "municipal_authority",
        "--json-out", str(out),
    ]
    proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
    if proc.returncode != 0:
        return {"ward": ward, "error": (proc.stderr or proc.stdout)[-600:]}
    if not out.exists():
        return {"ward": ward, "error": "no json written"}
    data = json.loads(out.read_text())
    data["_ward"] = ward
    return data


FLOOD = "flood.json"
CARBON_A = OUTDIR / "carbon_low_carbon.json"
CARBON_B = OUTDIR / "carbon_high_carbon.json"

# Two materially different BOQs for the SAME site, to prove the carbon factor
# responds to a real quantity change rather than to place. Carbon has no spatial
# component by design, so place cannot move it -- only the BOQ can.
CARBON_BOQS = {
    "low_carbon": [{"name": "cement", "quantityKg": 150_000},
                   {"name": "steel_reinforcement", "quantityKg": 120_000},
                   {"name": "fly_ash_brick", "quantityKg": 80_000}],
    "high_carbon": [{"name": "cement", "quantityKg": 260_000},
                    {"name": "steel_reinforcement", "quantityKg": 420_000},
                    {"name": "river_sand", "quantityKg": 200_000}],
}


def run_boq(name: str, items) -> Dict[str, Any]:
    """Run the CLI on ward 12 with an explicit BOQ.

    `--materials` takes INLINE json, not a file path: the CLI calls
    json.loads() on the argument string itself, so handing it a path raises
    JSONDecodeError and produces no output file at all.
    """
    out = OUTDIR / f"carbon_{name}.json"
    cmd = [sys.executable, "-m", "ml_pipeline.cli", "assess",
           "--ward", "12", "--built-up", str(BUILT_UP), "--plot", str(PLOT),
           "--storeys", str(STOREYS),
           "--materials", json.dumps(items),
           "--role", "municipal_authority", "--json-out", str(out)]
    proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
    if proc.returncode != 0:
        return {"error": (proc.stderr or proc.stdout)[-300:]}
    if not out.exists():
        return {"error": "no json written"}
    return json.loads(out.read_text())


def main() -> None:
    print("=" * 108)
    print("END-TO-END TEST — 12 real PMC wards, identical 3,000 m2 proposal, real pipeline CLI")
    print("=" * 108)
    print()

    rows: List[Dict[str, Any]] = []
    for w in WARDS:
        d = run_cli(w)
        if "error" in d:
            print(f"  ward {w:>2}: FAILED  {d['error'][:160]}")
            continue
        rows.append(d)
        print(f"  ward {w:>2}: scored, {len(d.get('sub_scores') or {})} factors")

    if not rows:
        print("no ward produced a score")
        return

    print()
    print("=" * 108)
    print("RESULTS")
    print("=" * 108)
    hdr = (f"{'ward':>4} {'impact':>7} {'band':>9} | "
           + " ".join(f"{f:>7}" for f in FACTORS)
           + f" | {'built%':>7} {'veg%':>6} {'LST':>7} {'ref':>7} "
             f"{'trees':>7} {'canopy':>7} {'drain':>6} {'cn':>6}")
    print(hdr)
    print("-" * 108)

    for d in rows:
        # The CLI nests the scorer output under /score/; /indicators and
        # /canopy are siblings of it, not children.
        sc = d.get("score") or {}
        subs = sc.get("sub_scores") or {}

        def f(v, spec=">7.1f"):
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                return format("-" if v is None else str(v)[:7], ">7")
            return format(v, spec)

        fl = (sc.get("factors") or {}).get("flood") or {}
        heat = (sc.get("factors") or {}).get("heat") or {}
        can = d.get("canopy") or {}
        ind = d.get("indicators") or {}
        print(f"{d['_ward']:>4} {f(sc.get('impact_score'))} {str(sc.get('risk_band')):>9} | "
              + " ".join(f(subs.get(k)) for k in FACTORS)
              + f" | {f(ind.get('impervious_pct'), '>7.1f')} {f(ind.get('vegetation_pct'), '>6.1f')} "
                f"{f(heat.get('lst_celsius'), '>7.2f')} {f(heat.get('lst_reference_c'), '>7.2f')} "
                f"{f(can.get('total_trees'), '>7')} {f(can.get('canopy_cover_pct'), '>7.1f')} "
                f"{f(fl.get('drainage_multiplier'), '>6.3f')} {f(fl.get('curve_number'), '>6.1f')}")

    # ---- factor discrimination -----------------------------------------
    print()
    print("=" * 108)
    print("FACTOR DISCRIMINATION ACROSS 12 REAL LOCATIONS")
    print("=" * 108)
    print(f"{'factor':<9} {'n':>3} {'min':>8} {'max':>8} {'spread':>8} {'sd':>7}  verdict")
    print("-" * 108)
    for fac in FACTORS:
        vals = [((d.get("score") or {}).get("sub_scores") or {}).get(fac) for d in rows]
        vals = [v for v in vals if isinstance(v, (int, float))]
        if not vals:
            print(f"{fac:<9} {0:>3}  never scored")
            continue
        sp = max(vals) - min(vals)
        n = len(vals)
        mean = sum(vals) / n
        sd = (sum((v - mean) ** 2 for v in vals) / n) ** 0.5
        verdict = ("STRONG" if sp >= 15 else "moderate" if sp >= 6
                   else "weak" if sp >= 2 else "CONSTANT")
        print(f"{fac:<9} {n:>3} {min(vals):>8.1f} {max(vals):>8.1f} {sp:>8.1f} {sd:>7.1f}  {verdict}")

    # ---- correlation of each factor with the physical input it claims to use
    print()
    print("=" * 108)
    print("DOES EACH FACTOR TRACK THE INPUT IT CLAIMS TO USE?")
    print("=" * 108)

    def pearson(xs, ys):
        n = len(xs)
        if n < 3:
            return float("nan")
        mx, my = sum(xs) / n, sum(ys) / n
        num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
        dx = sum((a - mx) ** 2 for a in xs) ** 0.5
        dy = sum((b - my) ** 2 for b in ys) ** 0.5
        return num / (dx * dy) if dx and dy else float("nan")

    def vals_of(key):
        out = []
        for d in rows:
            v = ((d.get("score") or {}).get("sub_scores") or {}).get(key)
            ind = d.get("indicators") or {}
            sc = d.get("score") or {}
            heat = (sc.get("factors") or {}).get("heat") or {}
            fl = (sc.get("factors") or {}).get("flood") or {}
            if key == "flood":
                src = fl.get("curve_number")
            elif key == "heat":
                src = heat.get("uhi_delta_c")
            elif key == "green":
                src = (d.get("canopy") or {}).get("canopy_cover_pct")
            else:
                src = None
            if isinstance(v, (int, float)) and isinstance(src, (int, float)):
                out.append((v, src))
        return out

    checks = [
        ("flood", "curve_number", "more impervious -> more runoff"),
        ("heat", "uhi_delta_c", "hotter than its green reference -> hotter"),
        ("green", "canopy_cover_pct", "more tree canopy -> less green lost"),
    ]
    for fac, src, why in checks:
        pairs = vals_of(fac)
        if len(pairs) < 3:
            print(f"{fac:<8} insufficient data ({len(pairs)} paired rows)")
            continue
        r = pearson([p[0] for p in pairs], [p[1] for p in pairs])
        print(f"{fac:<8} r(score, {src}) = {r:+.3f}   expected direction: {why}")

    # ---- CN formula check against the published standard -----------------
    print()
    print("=" * 108)
    print("FLOOD PHYSICS — composite curve number vs the NRCS TR-55 published formula")
    print("=" * 108)
    # TR-55 urban composite: CNc = (Pimp*98 + (100-Pimp)*CNperv) / 100,
    # i.e. a percentage-weighted average with a denominator of 100.
    # area_weighted_cn() instead divides by the sum of the three measured
    # fractions, so any unclassified remainder (bare soil) is dropped from the
    # denominator rather than carried at its own curve number.
    sys.path.insert(0, str(REPO))
    from ml_pipeline.core.scoring import area_weighted_cn

    print(f"{'built%':>7} {'veg%':>6} {'water%':>7} {'bare%':>6} "
          f"{'pipeline CN':>12} {'TR-55 CN':>9} {'diff':>7}")
    print("-" * 108)
    for built, veg, water in [(53.7, 9.2, 0.0), (66.8, 7.4, 0.0),
                              (20.5, 19.2, 0.0), (69.4, 3.4, 0.0),
                              (45.6, 9.3, 0.0), (30.0, 20.0, 5.0)]:
        got = area_weighted_cn(built, veg, water,
                               {"vegetation": 60.0, "impervious": 98.0, "water": 100.0})
        bare = max(0.0, 100.0 - built - veg - water)
        # TR-55 with the measured impervious fraction and the remainder pervious.
        ref = (built * 98.0 + (100.0 - built) * 60.0) / 100.0
        print(f"{built:>7.1f} {veg:>6.1f} {water:>7.1f} {bare:>6.1f} "
              f"{got:>12.1f} {ref:>9.1f} {got-ref:>+7.1f}")

    print()
    print("Interpretation: the pipeline's CN exceeds TR-55 wherever bare soil is")
    print("present, because dividing by the measured sum drops the bare fraction")
    print("from the denominator. Larger CN means MORE runoff, so this is")
    print("conservative rather than permissive — but it is not the TR-55 formula")
    print("and the gap is not reported anywhere in the output.")

    print()
    print("=" * 108)
    print("CARBON — same site (ward 12), two materially different bills of quantities")
    print("=" * 108)
    print("Carbon is embodied emissions from the BOQ and has no spatial component, so")
    print("place cannot move it. This is the only legitimate way to test it.")
    print("-" * 108)
    print(f"{'BOQ':<14} {'cement':>9} {'steel':>9} {'total kgCO2e':>14} "
          f"{'per m2':>8} {'carbon score':>13} {'band':>7} {'impact':>8}")
    for name, items in CARBON_BOQS.items():
        d = run_boq(name, items)
        if "error" in d:
            print(f"{name:<14} FAILED: {d['error'][:80]}")
            continue
        sc = d.get("score") or {}
        cb = (sc.get("factors") or {}).get("carbon") or {}
        print(f"{name:<14} {items[0]['quantityKg']:>9,} {items[1]['quantityKg']:>9,} "
              f"{cb.get('total_kgco2e', 0):>14,.0f} "
              f"{cb.get('intensity_kgco2e_m2', 0):>8.1f} "
              f"{cb.get('score', 0):>13.1f} {str(cb.get('band')):>7} "
              f"{sc.get('impact_score', 0):>8.1f}")

    (OUTDIR / "e2e_summary.json").write_text(json.dumps(
        {"wards": [d["_ward"] for d in rows],
         "built_up_sqm": BUILT_UP, "plot_sqm": PLOT, "storeys": STOREYS},
        indent=2))
    print()
    print(f"per-ward JSON written to {OUTDIR}")


if __name__ == "__main__":
    main()