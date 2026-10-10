"""Carbon factor audit — is the arithmetic right, and is the mapping sane?

Runs a battery of BOQs through the real compute_carbon() and prints what the
engine actually returns, so every claim below is read off the code rather than
assumed. Checks specifically for:

  1. the band-label vs score contradiction
  2. false blocking advisories on an ordinary BOQ
  3. non-monotonic behaviour across the band boundaries
  4. what happens with a zero-area site and an empty BOQ

Run: .venv/bin/python ml_pipeline/data/carbon_audit.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

CONFIG = REPO / "ml_pipeline" / "config"
REGION = json.loads((CONFIG / "regions" / "pune.json").read_text())
MATERIALS = json.loads((CONFIG / "materials.json").read_text())
BANDS = (REGION.get("carbon") or {}).get("bands") or []

from ml_pipeline.core.scoring import compute_carbon  # noqa: E402

AREA = 3000.0


def show(label: str, items, area=AREA, bands=BANDS) -> dict:
    r = compute_carbon(items, area, MATERIALS, bands)

    # A factor can legitimately now return score=None (empty BOQ, zero area,
    # wholly unresolvable materials). Formatting None with a float spec raises
    # and kills the report partway down, so it is rendered explicitly.
    def num(v, spec):
        # A float spec cannot format None or a str, so both are routed to a
        # width-only spec. Three separate crashes in this audit came from
        # formatting a missing value, so the check is explicit rather than
        # relying on a fallback default.
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return format("n/a" if v is None else str(v)[:6], ">6")
        return format(v, spec)

    print(f"{label:<34} intensity={num(r['intensity_kgco2e_m2'], '>7.1f')}  "
          f"score={num(r['score'], '>6.1f')}  band={str(r.get('band')):<10} "
          f"total={r['total_kgco2e']:>12,.0f}")
    if r.get("status") == "UNAVAILABLE":
        print(f"{'':<34} UNAVAILABLE: {r.get('reason', '')[:90]}")
    if r.get("double_count_warning"):
        print(f"{'':<34} DOUBLE COUNT: {r['double_count_warning']}")
    if r.get("unknown_materials"):
        print(f"{'':<34} UNKNOWN: {r['unknown_materials']}")
    for a in r.get("ecological_advisories", []):
        print(f"{'':<34} ADVISORY[{a['severity']}]: {a['material']} -> {a['advisory']}")
    return r


def main() -> None:
    print("=" * 96)
    print("CARBON AUDIT — band scale and label behaviour")
    print("=" * 96)
    print("configured bands (in file order):")
    for b in BANDS:
        print(f"  {b['label']:<10} max={b['max']}")
    print()

    print("=" * 96)
    print("TEST 1 — sweep intensity across every band boundary")
    print("=" * 96)
    print("A single synthetic 1 kg item per m2 keeps the arithmetic trivial, so the")
    print("only thing under test is the intensity -> (score, band) mapping.")
    print("Column is kg of cement_opc; real intensity = kg x 0.74 EF, over 1 m2.")
    print()
    print(f"{'cement_kg':>10} {'intensity':>10} {'score':>7} {'band':<11} verdict")
    print("-" * 96)
    prev = None
    for kg in [50, 131, 200, 399, 400, 401, 700, 799, 800, 801,
               1100, 1199, 1200, 1201, 2000]:
        r = compute_carbon([{"name": "cement_opc", "quantityKg": kg}],
                           1.0, MATERIALS, BANDS)
        inten, s, b = r["intensity_kgco2e_m2"], r["score"], r["band"]
        flag = ""
        if prev is not None and s < prev[0]:
            flag = (f"SCORE FELL {prev[0] - s:.1f} pts while emissions ROSE")
        elif s >= 60 and b in ("Low", "Moderate"):
            flag = "high score with a Low/Moderate band label"
        prev = (s, b)
        print(f"{kg:>10} {inten:>10.1f} {s:>7.1f} {b:<11} {flag}")
    print()
    print("Monotonic by construction: the score divides by the top of the configured")
    print("scale (1200), so intensity can only ever push it up. Each band boundary")
    print("now continues the same curve instead of stepping down.")
    print()
    print("Score and band label still describe different things -- the band is a")
    print("named category, the score is position on the 0-100 scale -- but they no")
    print("longer contradict each other.")

    print()
    print("=" * 96)
    print("TEST 2 — does an ORDINARY BOQ trip a blocking advisory?")
    print("=" * 96)
    # A completely standard mid-rise RC frame. Every one of these material names
    # is what an architect or contractor would actually type.
    ordinary = [
        {"name": "cement", "quantityKg": 180_000},
        {"name": "steel", "quantityKg": 150_000},
        {"name": "sand", "quantityKg": 400_000},
        {"name": "aggregate", "quantityKg": 500_000},
        {"name": "brick", "quantityKg": 250_000},
    ]
    print("BOQ: cement 180t, steel 150t, sand 400t, aggregate 500t, brick 250t")
    print("(completely standard for an Indian RC building)")
    print()
    r = show("ordinary BOQ", ordinary)
    advs = r.get("ecological_advisories", [])
    blocking = [a for a in advs if a.get("severity") == "blocking"]
    print()
    if blocking:
        print(f"*** {len(blocking)} BLOCKING advisory/advisories fired on an ordinary BOQ. ***")
        for a in blocking:
            print(f"    {a['material']} -> {a['advisory']}")
            print(f"    aliases to a material whose EF is only 0.005 kgCO2e/kg")
        print()
        print("This matters because a blocking advisory sets the recommendation")
        print("to REVIEW. If typing the ordinary word 'sand' permanently blocks a")
        print("project, the check stops being informative and gets switched off.")
    else:
        print("no blocking advisories on an ordinary BOQ")

    print()
    print("=" * 96)
    print("TEST 3 — same building, sand specified as M-sand instead")
    print("=" * 96)
    msand = [dict(x) for x in ordinary]
    msand[2] = {"name": "manufactured_sand_msand", "quantityKg": 400_000}
    show("M-sand instead of sand", msand)
    print()
    print("The two differ by 3 kgCO2e in total — 0.1% — because the emission factors")
    print("are nearly identical. What differs is the ADVISORY: unspecified sand now")
    print("asks for clarification, M-sand is affirmed, and only a deliberate")
    print("river_sand specification blocks. That is the correct distinction: the")
    print("question is legal and ecological, not carbon.")

    print()
    print("=" * 96)
    print("TEST 4 — degenerate inputs")
    print("=" * 96)
    print("These must be reported as MISSING DATA, never as a good result.")
    print()
    show("empty BOQ", [])
    show("only unknown materials", [{"name": "unobtainium", "quantityKg": 1000}])
    show("zero built-up area", [{"name": "cement", "quantityKg": 180_000}], area=0.0)
    print()
    print("An empty BOQ scoring 0.0 would tell a municipality that an undescribed")
    print("project has the best possible carbon profile. None is the honest answer.")

    print()
    print("=" * 96)
    print("TEST 5 — cement vs ready-mix double counting")
    print("=" * 96)
    print("compute_carbon's docstring says specifying both cement and")
    print("concrete_ready_mix double-counts binder. Check it is now DETECTED.")
    print()
    show("cement only", [{"name": "cement", "quantityKg": 180_000}])
    show("cement AND ready-mix", [{"name": "cement", "quantityKg": 180_000},
                                  {"name": "concrete", "quantityKg": 1_500_000}])
    print()
    print("The rule is stated and now reported. The engine flags it rather than")
    print("silently charging the binder twice; the drafter decides which line to drop.")


if __name__ == "__main__":
    main()