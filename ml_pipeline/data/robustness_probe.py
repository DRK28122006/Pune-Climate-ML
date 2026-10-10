"""Robustness harness — how do green and carbon behave on REAL-WORLD input?

The question that matters before a demo is not "does it work on my test data"
but "does it still work when the input comes from someone else's system".

Every BOQ names materials differently. Every land-cover dataset reports
different units and resolutions. A government portal will hand us a CSV we did
not shape. These probes use the messy spellings and unit conventions that
actually appear in Indian construction documents, and report what the pipeline
does with each.

Run: .venv/bin/python ml_pipeline/data/robustness_probe.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

CONFIG = REPO / "ml_pipeline" / "config"
REGION = json.loads((CONFIG / "regions" / "pune.json").read_text())
MATERIALS = json.loads((CONFIG / "materials.json").read_text())
BANDS = (REGION.get("carbon") or {}).get("bands") or []

from ml_pipeline.core.scoring import compute_carbon, compute_green  # noqa: E402

# Material spellings taken from real Indian BOQs, tender documents and
# contractor schedules. Grouped by the canonical material they SHOULD resolve to.
VARIANTS: Dict[str, List[str]] = {
    "cement_opc": [
        "cement", "CEMENT", "Cement ", "opc", "OPC", "ordinary portland cement",
        "OPC cement", "Cement (OPC)", "Portland Cement", "portland cement",
        "cement_opc", "CEMENT OPC",
    ],
    "steel_reinforcement": [
        "steel", "STEEL", "tmt", "TMT", "TMT Fe500D", "TMT-500", "TMT 500",
        "Steel - TMT", "MS rebar", "MS Rebar", "reinforcement steel",
        "steel_reinforcement", "rebar", "TMT bars",
    ],
    "manufactured_sand_msand": [
        "m_sand", "M-sand", "M Sand", "msand", "MSAND", "manufactured sand",
        "M-sand (manufactured)", "M-sand manufactured",
    ],
    "brick_clay": [
        "brick", "bricks", "Brick", "clay brick", "burnt clay brick",
        "red brick", "Brick (Clay)",
    ],
    "fly_ash_brick": [
        "fly ash brick", "Fly Ash Brick", "flyash brick", "FAL brick",
        "fly ash bricks",
    ],
    "aac_block": [
        "aac block", "AAC Block", "AAC", "aac", "autoclaved aerated concrete block",
    ],
    "aggregate_rock": [
        "aggregate", "stone", "Aggregate", "crushed stone", "aggregate_rock",
        "20mm aggregate", "40mm aggregate",
    ],
    "concrete_ready_mix": [
        "concrete", "rcc", "RCC", "ready mix concrete", "RMC", "ready-mix",
        "concrete_ready_mix",
    ],
}

# Names a BOQ uses for real materials that are genuinely NOT in our table.
NOT_IN_TABLE = [
    "ground_granite_aggregate", "GGI", "laterite", "trap rock",
    "cuplicated soil", "murrum", "stabilized earth block",
]

FAILURES: List[str] = []


def fail(msg: str) -> None:
    FAILURES.append(msg)


def resolve(name: str) -> str:
    r = compute_carbon([{"name": name, "quantityKg": 1000.0}],
                       1000.0, MATERIALS, BANDS)
    return r["line_items"][0]["status"]


def main() -> int:
    print("=" * 100)
    print("ROBUSTNESS 1 — material name resolution on real-world BOQ spellings")
    print("=" * 100)
    total = lost = 0
    per_group: Dict[str, List[str]] = {}
    for canonical, variants in VARIANTS.items():
        bad = []
        for v in variants:
            total += 1
            if resolve(v) != "OK":
                bad.append(v)
                lost += 1
        per_group[canonical] = bad
        status = "all resolved" if not bad else f"{len(bad)}/{len(variants)} LOST"
        print(f"  {canonical:<26} {status}")
        for b in bad:
            print(f"      lost: {b!r}")
    print()
    print(f"  RESOLVED {total - lost}/{total}   LOST {lost}/{total}")
    print()

    print("=" * 100)
    print("ROBUSTNESS 2 — real Pune earthworks materials")
    print("=" * 100)
    print("These are the materials any PMC or MIDC site with excavation and")
    print("filling actually uses. Each must resolve, or its mass contributes")
    print("zero carbon while the factor still reports a number.")
    print()
    print(f"{'material':<30} {'500 t contributes':>20}  status")
    print("-" * 100)
    for name in NOT_IN_TABLE:
        r = compute_carbon([{"name": name, "quantityKg": 500_000}],
                           3000.0, MATERIALS, BANDS)
        li = r["line_items"][0]
        print(f"{name:<30} {r['total_kgco2e']:>20,.0f}  {li['status']}")
    print()
    unscored = [n for n in NOT_IN_TABLE
                if compute_carbon([{"name": n, "quantityKg": 500_000}],
                                  3000.0, MATERIALS, BANDS)["line_items"][0]
                ["status"] != "OK"]
    if unscored:
        ref = compute_carbon([{"name": "aggregate_rock", "quantityKg": 500_000}],
                             3000.0, MATERIALS, BANDS)
        print(f"  For comparison, 500 t of a KNOWN aggregate contributes "
              f"{ref['total_kgco2e']:,.0f} kgCO2e.")
        print(f"  {len(unscored)} material(s) still contribute ZERO, which is a")
        print("  false claim of zero emissions rather than a missing one:")
        for n in unscored:
            print(f"    {n}")
        print()
        print("  Those need an emission factor. Their absence is now DETECTED")
        print("  rather than silent, but detection is not the same as a number.")
    else:
        print("  All resolve. Quarrying and hauling only -- no calcination -- so")
        print("  these are transport-dominated and near-negligible against cement")
        print("  and steel. Their factors are flagged ef_status: ESTIMATE_DERIVED")
        print("  in materials.json; a published Indian factor would supersede.")
    print()

    print("=" * 100)
    print("ROBUSTNESS 3 — unit convention: fraction vs percent")
    print("=" * 100)
    print("Our cube stores FRACTIONS (0.068) and the CLI converts to percent.")
    print("A differently-built dataset may store PERCENT (6.8).")
    print()
    for val, label in ((6.8, "6.8  (already percent)"),
                       (0.068, "0.068 (fraction, our convention)"),
                       (680.0, "680  (10x percent, a units bug)")):
        r = compute_green(sat_veg_pct=val, canopy_cover_pct=6.5)
        score = r['score']
        shown = f"{score:>5.1f}" if score is not None else "  n/a"
        status = r.get('status', 'OK')
        print(f"  vegetation {label:<36} -> {status:<12} score {shown}")
    print()
    print("  clamp() used to collapse 6.8, 68 and 680 all to 100.0, so a units")
    print("  mistake was indistinguishable from genuine 100% vegetation and")
    print("  nothing warned. Out-of-range input now returns UNAVAILABLE.")
    print()

    print("=" * 100)
    print("ROBUSTNESS 4 — canopy magnitude is never sanity-checked")
    print("=" * 100)
    for can, label in ((6.5, "6.5  (correct, percent)"),
                       (0.065, "0.065 (fraction instead of percent)"),
                       (65.0, "65   (10x too high)"),
                       (650.0, "650  (100x, a units bug)")):
        r = compute_green(sat_veg_pct=6.8, canopy_cover_pct=can)
        score = r['score']
        shown = f"{score:>5.1f}" if score is not None else "  n/a"
        print(f"  canopy {label:<42} -> {r.get('status', 'OK'):<12} score {shown}")
    print()
    print("  A 10x canopy error moves the green score from 95.4 to 54.5 with no")
    print("  warning at all, because 65 is a legal percentage. Only errors beyond")
    print("  100 are caught, and a plausible-but-wrong magnitude inside the valid")
    print("  range cannot be detected from the value alone -- it needs a")
    print("  cross-check against a second source.")
    print()
    print("  Since this fix, an out-of-range percentage returns UNAVAILABLE rather")
    print("  than a clamped number, so the units fault is visible in the report.")
    print()
    for can, label in ((650.0, "650  (100x, a units bug)"),
                       (-5.0, "-5    (impossible, negative cover)")):
        r = compute_green(sat_veg_pct=6.8, canopy_cover_pct=can)
        print(f"  canopy {label:<42} -> {r.get('status', 'OK')}")
        print(f"      reason: {r.get('reason', '-')}")
    print()

    print("=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"  material spellings resolved : {total - lost}/{total}")
    print(f"  spellings lost              : {lost}")
    still = [n for n in NOT_IN_TABLE
             if compute_carbon([{"name": n, "quantityKg": 500_000}],
                               3000.0, MATERIALS, BANDS)["line_items"][0]
             ["status"] != "OK"]
    print(f"  real Pune materials unscored: {len(still)}/{len(NOT_IN_TABLE)}")
    print()
    if FAILURES:
        print(f"  {len(FAILURES)} hard failure(s)")
        for f in FAILURES:
            print(f"    * {f}")
        return 1
    print("  No crashes. The failures above are silent wrong answers, not errors,")
    print("  which is why they need explicit detection rather than a try/except.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())