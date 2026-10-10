"""STRESS TEST — green and carbon factors, from the real pipeline CLI.

Two independent tracks, because they fail in different ways:

  TRACK 1 (place): the same proposal at many real PMC wards. Uses the CLI, so
  every number is the pipeline's own. Checks whether each factor still
  discriminates between locations and still tracks the input it claims to use.

  TRACK 2 (adversarial): hand-built inputs that probe the boundaries — impossible
  canopy values, satellite/census disagreement, missing data, degenerate areas.
  A factor that survives these is not merely well-behaved on average.

Every claim in the report below is read off this output.

Run: .venv/bin/python ml_pipeline/data/stress_green_carbon.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

CONFIG = REPO / "ml_pipeline" / "config"
OUTDIR = REPO / "ml_pipeline" / "data" / "stress"
OUTDIR.mkdir(parents=True, exist_ok=True)

REGION = json.loads((CONFIG / "regions" / "pune.json").read_text())
MATERIALS = json.loads((CONFIG / "materials.json").read_text())
BANDS = (REGION.get("carbon") or {}).get("bands") or []

from ml_pipeline.core.scoring import compute_carbon, compute_green  # noqa: E402

# A wide spread of real PMC wards: core, mid-city, fringe, and the wards the
# previous tests never touched.
WARDS = [1, 2, 3, 4, 5, 7, 9, 11, 12, 13, 14, 16, 18, 21, 22, 23, 25,
         26, 27, 30, 31, 33, 34, 36, 37, 38, 39, 40, 41]

BUILT_UP = 3000
PLOT = 8000
STOREYS = 8

FAILURES: List[str] = []


def cell(value: Any, spec: str = ">8.1f") -> str:
    """Format a value that may legitimately be absent.

    A factor that withholds its score returns None plus a `reason`, and the
    reason is the whole point -- so the table shows n/a and the reason is
    printed underneath rather than the row being dropped or crashing the run.
    """
    if value is None:
        return f"{'n/a':>8}"
    try:
        return format(value, spec)
    except (TypeError, ValueError):
        return format(str(value), ">8")


def fail(msg: str) -> None:
    FAILURES.append(msg)
    print(f"  FAIL  {msg}")


def run_cli(ward: int) -> Optional[Dict[str, Any]]:
    out = OUTDIR / f"w{ward:02d}.json"
    cmd = [sys.executable, "-m", "ml_pipeline.cli", "assess",
           "--ward", str(ward), "--built-up", str(BUILT_UP), "--plot", str(PLOT),
           "--storeys", str(STOREYS), "--demo-materials",
           "--role", "municipal_authority", "--json-out", str(out)]
    p = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
    if p.returncode != 0 or not out.exists():
        return None
    d = json.loads(out.read_text())
    d["_ward"] = ward
    return d


def pearson(xs: List[float], ys: List[float]) -> float:
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    dx = sum((a - mx) ** 2 for a in xs) ** 0.5
    dy = sum((b - my) ** 2 for b in ys) ** 0.5
    return num / (dx * dy) if dx and dy else float("nan")


# =====================================================================
# TRACK 1 — place
# =====================================================================


def track_place() -> List[Dict[str, Any]]:
    print("=" * 104)
    print(f"TRACK 1 — same {BUILT_UP} m2 proposal at {len(WARDS)} real PMC wards, via the CLI")
    print("=" * 104)
    rows = []
    for w in WARDS:
        d = run_cli(w)
        if d is None:
            print(f"  ward {w:>2}: no output (skipped)")
            continue
        sc = d.get("score") or {}
        g = (sc.get("factors") or {}).get("green") or {}
        c = (sc.get("factors") or {}).get("carbon") or {}
        can = d.get("canopy") or {}
        ind = d.get("indicators") or {}
        rows.append({
            "ward": w,
            "sat_veg": ind.get("vegetation_pct"),
            "canopy": can.get("canopy_cover_pct"),
            "ground": g.get("ground_vegetation_pct"),
            "effective": g.get("effective_green_pct"),
            "green": (sc.get("sub_scores") or {}).get("green"),
            "divergence": g.get("source_divergence_pts"),
            "conf": g.get("confidence"),
            "trees": can.get("total_trees"),
            "carbon": (sc.get("sub_scores") or {}).get("carbon"),
            "carbon_band": c.get("band"),
            "carbon_conf": c.get("confidence"),
            "impact": sc.get("impact_score"),
        })

    print()
    print(f"{'ward':>4} {'satveg%':>8} {'canopy%':>8} {'ground%':>8} {'green':>7} "
          f"{'div':>5} {'conf':>6} {'trees':>6} | {'carbon':>7} {'band':<10} {'impact':>7}")
    print("-" * 104)
    for r in rows:
        def f(v, s=">7.1f"):
            return format(v, s) if isinstance(v, (int, float)) else format("-", ">7")
        print(f"{r['ward']:>4} {f(r['sat_veg'], '>8.1f')} {f(r['canopy'], '>8.1f')} "
              f"{f(r['ground'], '>8.1f')} {f(r['green'])} {f(r['divergence'], '>5.1f')} "
              f"{str(r['conf']):>6} {r['trees'] if r['trees'] is not None else '-':>6} | "
              f"{f(r['carbon'])} {str(r['carbon_band']):<10} {f(r['impact'])}")
    return rows


# =====================================================================
# TRACK 2 — adversarial
# =====================================================================


def track_green_adversarial() -> None:
    print()
    print("=" * 104)
    print("TRACK 2a — GREEN: adversarial inputs")
    print("=" * 104)

    cases = [
        ("no green at all", 0.0, 0.0),
        ("canopy only", 40.0, 40.0),
        ("ground veg only", 40.0, 0.0),
        ("sat < canopy (impossible)", 5.0, 30.0),
        ("canopy 100%", 100.0, 100.0),
        ("sat 100 canopy 0", 100.0, 0.0),
        ("canopy > sat by 40pts", 10.0, 50.0),
        ("negative inputs", -20.0, -10.0),
        ("absurd 500/500", 500.0, 500.0),
        ("NaN-ish huge", 1e9, 1e9),
    ]
    print(f"{'case':<26} {'sat':>8} {'canopy':>8} {'ground':>8} {'effective':>10} "
          f"{'score':>8} {'div':>8} {'conf':>8}  status")
    print("-" * 116)
    for label, sat, can in cases:
        try:
            r = compute_green(sat_veg_pct=sat, canopy_cover_pct=can)
        except Exception as exc:  # noqa: BLE001
            fail(f"green crashed on {label}: {type(exc).__name__}: {exc}")
            continue
        print(f"{label:<26} {cell(r.get('sat_veg_pct'))} "
              f"{cell(r.get('canopy_cover_pct'))} "
              f"{cell(r.get('ground_vegetation_pct'))} "
              f"{cell(r.get('effective_green_pct'), '>10.1f')} "
              f"{cell(r.get('score'), '>8.1f')} "
              f"{cell(r.get('source_divergence_pts'), '>8.1f')} "
              f"{cell(r.get('confidence'), '>8')} "
              f"  {r.get('status', 'OK')}")
        # A withheld score must always explain itself.
        if r.get("score") is None and not r.get("reason"):
            fail(f"green withheld its score for {label} without a reason")

        # NOTE: canopy CAN legitimately exceed satellite vegetation. canopy is
        # measured over the site polygon (8,000 m2), vegetation over the whole
        # ~1 km cube cell (~1,000,000 m2). Ward 2 has 50.4% canopy on its plot
        # inside a cell reading 7.6%, backed by 252 real census trees. An
        # earlier version of this harness asserted canopy <= sat and reported
        # two false failures.
        #
        # What IS a real defect is a site with NO inputs scoring perfectly, and
        # that is checked separately below.

    # Missing data must not read as a perfect green site.
    print()
    r = compute_green(sat_veg_pct=None, canopy_cover_pct=None)
    print(f"{'both None':<26} sat={r['sat_veg_pct']} canopy={r['canopy_cover_pct']} "
          f"score={r['score']} conf={r['confidence']}")
    if r["score"] == 100.0:
        fail("green with NO data scores 100.0 (perfect) — must be excluded instead")
    if r["score"] is not None:
        fail(f"green with no data must return None, got {r['score']}")

    r2 = compute_green(sat_veg_pct=10.0, canopy_cover_pct=None)
    print(f"{'canopy missing only':<26} sat={r2['sat_veg_pct']} "
          f"canopy={r2['canopy_cover_pct']} score={r2['score']} conf={r2['confidence']}")
    if r2["score"] is not None:
        fail(f"green missing canopy must return None, got {r2['score']}")

    r3 = compute_green(sat_veg_pct=None, canopy_cover_pct=20.0)
    print(f"{'satellite missing only':<26} sat={r3['sat_veg_pct']} "
          f"canopy={r3['canopy_cover_pct']} score={r3['score']} conf={r3['confidence']}")
    if r3["score"] is not None:
        fail(f"green missing satellite must return None, got {r3['score']}")

    # Monotonicity: more canopy must never raise the green score.
    print()
    print("monotonicity in canopy (satellite held at 50%):")
    prev = None
    for can in (0, 10, 20, 30, 40, 50):
        r = compute_green(sat_veg_pct=50.0, canopy_cover_pct=float(can))
        s = r.get("score")
        s_txt = f"{s:>5.1f}" if isinstance(s, (int, float)) else f"{'n/a':>5}"
        eff = r.get("effective_green_pct")
        e_txt = f"{eff:>5.1f}" if isinstance(eff, (int, float)) else f"{'n/a':>5}"
        line = f"  canopy {can:>3}% -> score {s_txt} (effective {e_txt})"
        if prev is not None and isinstance(s, (int, float)) and s > prev:
            line += f"  <== ROSE by {s - prev:.1f}"
            fail(f"green score rose when canopy increased: {can}%")
        prev = r.get("score")
        print(line)


def track_carbon_adversarial() -> None:
    print()
    print("=" * 104)
    print("TRACK 2b — CARBON: adversarial inputs")
    print("=" * 104)

    def show(label, items, area=3000.0):
        try:
            r = compute_carbon(items, area, MATERIALS, BANDS)
        except Exception as exc:  # noqa: BLE001
            fail(f"carbon crashed on {label}: {type(exc).__name__}: {exc}")
            return None
        s = r.get("score")
        s_txt = f"{s:>5.1f}" if isinstance(s, (int, float)) else f"{'n/a':>6}"
        inten = r.get("intensity_kgco2e_m2")
        i_txt = f"{inten:>9.1f}" if isinstance(inten, (int, float)) else f"{'n/a':>9}"
        print(f"{label:<34} intensity={i_txt} "
              f"score={s_txt} band={str(r.get('band')):<10} conf={r.get('confidence')}")
        return r

    # Monotonicity across a wide sweep, not just band boundaries.
    print("monotonicity sweep (single material, cement_opc, 1 m2):")
    prev = None
    for kg in (1, 10, 100, 250, 400, 600, 900, 1200, 1600, 3000, 10000):
        r = compute_carbon([{"name": "cement_opc", "quantityKg": float(kg)}],
                           1.0, MATERIALS, BANDS)
        s = r.get("score")
        mark = ""
        if prev is not None and isinstance(s, (int, float)) and s < prev:
            mark = f"  <== FELL {prev - s:.1f}"
            fail(f"carbon not monotonic at {kg} kg")
        prev = s
        s_txt = f"{s:>5.1f}" if isinstance(s, (int, float)) else f"{'n/a':>5}"
        print(f"  {kg:>6} kg -> intensity {r['intensity_kgco2e_m2']:>8.1f}  "
              f"score {s_txt}  band {str(r.get('band')):<10}{mark}")

    print()
    print("missing / degenerate data:")
    show("empty BOQ", [])
    show("only unknown material", [{"name": "zzz", "quantityKg": 100}])
    show("zero area", [{"name": "cement", "quantityKg": 1000}], area=0.0)
    show("negative area", [{"name": "cement", "quantityKg": 1000}], area=-500.0)
    show("zero quantities", [{"name": "cement", "quantityKg": 0}])
    show("negative quantity", [{"name": "cement", "quantityKg": -5000}])
    show("missing quantity key", [{"name": "cement"}])
    show("missing name key", [{"quantityKg": 1000}])
    show("null material entry", [{"name": None, "quantityKg": 1000}])

    print()
    print("mixed resolvable / unresolvable:")
    show("1 good + 1 unknown", [{"name": "cement", "quantityKg": 180_000},
                                 {"name": "qqq", "quantityKg": 5_000}])
    show("1 good + double count", [{"name": "cement", "quantityKg": 180_000},
                                    {"name": "concrete", "quantityKg": 900_000}])

    print()
    print("real-world free-text BOQ spellings (robustness, not arithmetic):")
    for label, items in (
        ("messy spellings, all known",
         [{"name": "OPC cement", "quantityKg": 150_000},
          {"name": "TMT Fe500D", "quantityKg": 95_000},
          {"name": "M Sand", "quantityKg": 60_000},
          {"name": "Fly Ash Brick", "quantityKg": 40_000}]),
        ("Pune earthworks, spelled freely",
         [{"name": "trap rock", "quantityKg": 400_000},
          {"name": "murrum", "quantityKg": 300_000},
          {"name": "C&D waste", "quantityKg": 200_000}]),
        ("one unknown line, small mass",
         [{"name": "cement", "quantityKg": 180_000},
          {"name": "something_we_never_heard_of", "quantityKg": 5_000}]),
        ("one unknown line, most of the mass",
         [{"name": "cement", "quantityKg": 50_000},
          {"name": "something_we_never_heard_of", "quantityKg": 500_000}]),
    ):
        r = show(label, items)
        if r is not None and r.get("unknown_mass_pct") is not None:
            print(f"{'':<34}   unquantified mass: {r['unknown_mass_pct']}%")

    # A factor that withholds a score must always say why, whatever the cause.
    for label, items, area in (
        ("empty BOQ", [], 3000.0),
        ("zero area", [{"name": "cement", "quantityKg": 1000}], 0.0),
        ("all unknown", [{"name": "qqq", "quantityKg": 100}], 3000.0),
        ("mostly unknown", [{"name": "cement", "quantityKg": 50_000},
                            {"name": "qqq", "quantityKg": 500_000}], 3000.0),
    ):
        r = compute_carbon(items, area, MATERIALS, BANDS)
        if r.get("score") is None and not r.get("reason"):
            fail(f"carbon withheld its score for {label} without a reason")

    print()
    print("substitution ordering (same mass, different material):")
    for name in ("cement_opc", "cement_ppc", "cement_ggbs",
                 "steel_reinforcement", "steel_rebar_eaf",
                 "brick_clay", "fly_ash_brick"):
        r = compute_carbon([{"name": name, "quantityKg": 10_000}],
                           1000.0, MATERIALS, BANDS)
        s = r.get("score")
        s_txt = f"{s:>5.1f}" if isinstance(s, (int, float)) else f"{'n/a':>5}"
        print(f"  {name:<22} {r['total_kgco2e']:>10,.0f} kgCO2e  score {s_txt}")


def main() -> int:
    rows = track_place()

    if rows:
        print()
        print("=" * 104)
        print("DISCRIMINATION — does each factor still separate locations?")
        print("=" * 104)
        for key, label in (("green", "green"), ("carbon", "carbon")):
            vals = [r[key] for r in rows if isinstance(r.get(key), (int, float))]
            if len(vals) < 2:
                print(f"{label:<8} not enough data ({len(vals)})")
                continue
            n = len(vals)
            mean = sum(vals) / n
            sd = (sum((v - mean) ** 2 for v in vals) / n) ** 0.5
            sp = max(vals) - min(vals)
            verdict = ("STRONG" if sp >= 15 else "moderate" if sp >= 6
                       else "WEAK" if sp >= 2 else "CONSTANT")
            print(f"{label:<8} n={n:>3} min={min(vals):>6.1f} max={max(vals):>6.1f} "
                  f"spread={sp:>6.1f} sd={sd:>5.1f}  {verdict}")

        # Green must track canopy; carbon must be flat across place.
        pairs = [(r["green"], r["canopy"]) for r in rows
                 if isinstance(r.get("green"), (int, float))
                 and isinstance(r.get("canopy"), (int, float))]
        if len(pairs) >= 3:
            r_pc = pearson([p[0] for p in pairs], [p[1] for p in pairs])
            print(f"\ngreen  r(score, canopy) = {r_pc:+.3f}  expect NEGATIVE "
                  f"(more canopy -> less green lost)")

        pairs2 = [(r["green"], r["sat_veg"]) for r in rows
                  if isinstance(r.get("green"), (int, float))
                  and isinstance(r.get("sat_veg"), (int, float))]
        if len(pairs2) >= 3:
            print(f"green  r(score, satellite veg) = "
                  f"{pearson([p[0] for p in pairs2], [p[1] for p in pairs2]):+.3f}  "
                  f"expect NEGATIVE")

    track_green_adversarial()
    track_carbon_adversarial()

    print()
    print("=" * 104)
    if FAILURES:
        print(f"RESULT — {len(FAILURES)} FAILURE(S)")
        print("=" * 104)
        for f in FAILURES:
            print(f"  * {f}")
        return 1
    print("RESULT — no failures detected")
    print("=" * 104)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())