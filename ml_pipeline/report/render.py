"""Report generation — L7.

The score is the input. The report is the product: an approver cannot act on
"the climate score is 49", they can act on "approve if they cut impervious
cover by 18 points, retain 1 heritage tree, and switch to GGBS".

Every number in the output traces to a computation in this pipeline. The
narrative layer, when an LLM is attached, writes prose around these values and
is never permitted to introduce or alter one.

Role shapes the presentation:
    municipal_authority      -> the decision card first
    urban_planner            -> full factor breakdown
    environmental_consultant -> formulas, epoch, citations, confidence
    public_viewer            -> plain language, no jargon
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

ROLE_ORDER = ("municipal_authority", "urban_planner",
              "environmental_consultant", "public_viewer")

FACTOR_LABELS = {
    "flood": "Flood",
    "heat": "Heat",
    "green": "Green cover",
    "carbon": "Carbon",
}

LEGAL_CITATIONS = [
    {
        "id": "mh-trees-act-1975",
        "text": "The Maharashtra (Urban Areas) Preservation of Trees Act, 1975 "
                "(Mah. XLIV of 1975), as amended July 2021 — felling requires Tree Officer "
                "permission; compensatory plantation in number equal to the age of "
                "the tree felled (section number not cited: primary Act text "
                "unverified).",
        "note": "The 90 cm girth threshold used in this tool is HOUSE POLICY, not a "
                "provision of this Act. The Act sets no girth-based automatic "
                "felling prohibition.",
    },
]


def format_site_line(validation: Dict[str, Any]) -> str:
    """One-line site identity, without repeating the ward number.

    PMC's 2025 boundary layer publishes ward NUMBER only, so ward_name is
    "Ward 12" for every ward. Printing "ward 12 Ward 12" looked like a bug and
    would read as one to a reviewer.
    """
    ward_no = validation.get("ward_no")
    ward_name = (validation.get("ward_name") or "").strip()
    prabhag = (validation.get("prabhag_name") or "").strip()
    locality = (validation.get("locality") or "").strip()

    bits = []
    if ward_name and re.sub(r"(?i)^ward\s*[-:]?\s*\d+\s*$", "", ward_name).strip():
        # A real locality label (not just "Ward N").
        bits.append(ward_name)
    elif ward_no is not None:
        bits.append(f"Ward {ward_no}")
    if locality and locality.lower() not in (ward_name or "").lower():
        bits.append(locality)
    if prabhag and prabhag not in bits:
        bits.append(f"prabhag {prabhag}")
    return "SITE: " + ", ".join(bits) if bits else "SITE: unspecified"


def _bar(value: Optional[float], width: int = 20) -> str:
    if value is None:
        return "?" * width
    filled = int(round((max(0.0, min(100.0, value)) / 100.0) * width))
    return "#" * filled + "." * (width - filled)


def score_block(result: Dict[str, Any],
                region_config: Optional[Dict[str, Any]] = None) -> str:
    subs = result.get("sub_scores", {}) or {}
    # Weights read from the region config (fixed 2026-10-10: hardcoded
    # 30/30/20/20 labels lied next to true scores for any region with
    # different weights). Fallback only when config is absent.
    weights = {"flood": 0.30, "heat": 0.30, "green": 0.20, "carbon": 0.20}
    try:
        cfg_w = (region_config or {}).get("weights") or {}
        weights = {k: float(cfg_w.get(k, weights[k])) for k in weights}
    except (TypeError, ValueError):
        pass
    lines = [
        f"CLIMATE SCORE   {result.get('climate_score')} / 100   (higher = better)",
        f"IMPACT SCORE    {result.get('impact_score')} / 100   (higher = worse)",
        f"RISK BAND       {result.get('risk_band')}",
        "",
    ]
    if not result.get("complete", True):
        lines.append(f"PARTIAL SCORE — missing factors: {', '.join(result.get('missing_factors') or [])}")
        if result.get("partial_notice"):
            lines.append(f"  {result['partial_notice']}")
        lines.append("")
    for key in ("flood", "heat", "green", "carbon"):
        v = subs.get(key)
        lines.append(
            f"  {FACTOR_LABELS[key]:<12} {str(v):>5}  {_bar(v)}  weight {weights[key]:.2f}"
        )
    return "\n".join(lines)


def canopy_block(ledger: Optional[Dict[str, Any]]) -> str:
    lines: List[str] = []
    cov = (ledger or {}).get("census_coverage") or {}
    reliable = (ledger or {}).get("census_reliable_for_this_site", True)

    # A ward/cell with no loaded census block returns zero trees. Reporting
    # "0 trees, 0 saplings due" there would read as "this site has no trees,
    # nothing to protect" -- a loading artefact presented as a finding. Say so
    # before any number, so the numbers below are never mistaken for real.
    if not reliable:
        lines += [
            "!! CENSUS DATA NOT LOADED FOR THIS SITE",
            "   Every tree figure below is UNRELIABLE: the PMC census CSV parts",
            "   are geographic blocks and this site's block is not loaded. Zero",
            "   does NOT mean treeless. Load the remaining parts before quoting.",
        ]
        if cov.get("warning"):
            lines.append(f"   {cov['warning']}")
        lines.append("")

    if not ledger:
        lines.append("CANOPY LEDGER")
        lines.append("  no tree data available for this boundary.")
        return "\n".join(lines)

    counts = ledger.get("action_counts", {}) or {}
    comp = ledger.get("compensatory_required", {}) or {}
    mix = ledger.get("compensatory_species_mix", []) or []
    lines += [
        "CANOPY LEDGER",
        f"  trees on site                {ledger.get('total_trees')}",
        f"  canopy before                {ledger.get('tree_canopy_m2_before')} m2",
        f"  canopy after                 {ledger.get('tree_canopy_m2_after')} m2",
        f"  canopy lost                  {ledger.get('tree_canopy_m2_lost')} m2",
        f"  canopy cover                 {ledger.get('canopy_cover_pct')}%",
        "",
        "  DECISIONS",
    ]
    label = {
        "MUST_PRESERVE": "preserve (no felling permitted)",
        "PRESERVE": "preserve in place",
        "RELOCATE": "relocate",
        "FELL_AND_COMPENSATE": "fell with compensation",
        "REMOVE_DEAD": "remove dead tree",
    }
    for k, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"    {label.get(k, k):<38} {n}")
    lines += [
        "",
        f"  heritage-class trees        {ledger.get('always_preserve_count')}"
        f"   ({ledger.get('always_preserve_canopy_m2')} m2 canopy)",
        f"  rare species on site        {ledger.get('rare_trees_in_site')}",
        f"  dead trees removed          {ledger.get('dead_trees_removed')}",
        "",
        f"  COMPENSATORY REQUIRED       {comp.get('low')} – {comp.get('high')} saplings",
        f"  basis                       {ledger.get('compensatory_basis')}",
    ]
    if mix:
        lines += ["", "  RECOMMENDED SPECIES MIX (native-weighted)"]
        for m in mix[:8]:
            if m.get("strategy") == "REPLANT_IN_KIND":
                lines.append(
                    f"    {m['felled_species'][:32]:<32} ({m['felled_share_pct']:>5.1f}%) "
                    f"replant in kind, paired with {m['mix_companion']}"
                )
            else:
                lines.append(
                    f"    replace {m['felled_species'][:28]:<28} "
                    f"({m['felled_share_pct']:>5.1f}%) with "
                    f"{m['recommended_replacement']}"
                )
    return "\n".join(lines)


def decision_block(result: Dict[str, Any], recs: Dict[str, Any]) -> str:
    rec = result.get("recommendation")
    lines = [f"RECOMMENDATION: {rec or 'NOT ISSUED'}"]
    if result.get("headline"):
        lines.append(f"  {result['headline']}")

    blockers = result.get("blocking_issues") or []
    if blockers:
        lines += ["", "  BLOCKING ISSUES (must be resolved before approval)"]
        for b in blockers:
            lines.append(f"    - {b.get('detail')}")

    items = recs.get("recommendations") or []
    if items:
        lines += ["", "  CONDITIONS, ranked by measured impact"]
        for i, r in enumerate(items, start=1):
            d = r.get("delta") or {}
            tgt = r.get("affected")
            fd = ((d.get("factors") or {}).get(tgt) or {}).get("delta")
            lines.append(f"    {i}. {r.get('action')}")
            if fd is not None:
                lines.append(f"       verified: {tgt} changes by {fd:+.1f} on rescore")
            if r.get("blocking"):
                alts = ", ".join(r.get("alternatives") or [])
                if alts:
                    lines.append(f"       substitute with: {alts}")
            if r.get("composite_tradeoff"):
                lines.append(f"       note: {r['composite_tradeoff']}")

    combined = recs.get("combined_effect") or {}
    if combined.get("available"):
        d = combined["delta"]
        lines += [
            "",
            f"  If all conditions are met: impact {d['impact_before']} -> "
            f"{d['impact_after']} (change {d['impact_delta']:+})",
        ]
    dropped = recs.get("dropped_unverified") or []
    if dropped:
        lines += ["", "  DROPPED (rescoring showed no measurable benefit)"]
        for d in dropped:
            lines.append(f"    - {d['id']}: {d['reason']}")
    return "\n".join(lines)


def afternoon_context(indicators: Dict[str, Any]) -> str:
    """Qualitative afternoon-exposure readout. UNSCORED by design.

    The heat factor scores night-time stored heat only (day branch retired
    for no signal). An officer opening this report at 2pm still needs to
    know what the site's mass and shade imply for peak-heat hours. This
    maps the site's own built/vegetation fractions to plain words --
    direction backed by the diurnal-SUHI literature (daytime contrasts
    exceed night-time and peak near midday), magnitude deliberately absent.
    It must never become a number without a measured daytime observable.
    """
    try:
        built = float(indicators.get("impervious_pct", 50.0))
    except (TypeError, ValueError):
        built = 50.0
    try:
        veg = float(indicators.get("vegetation_pct", 20.0))
    except (TypeError, ValueError):
        veg = 20.0
    # Missing drivers must read as unknown, never as a measured 50/20
    # (fixed 2026-10-10: defaults previously printed as fact).
    if (indicators.get("impervious_pct") is None
            or indicators.get("vegetation_pct") is None):
        return ("Afternoon exposure unknown: no land-cover indicators were "
                "supplied with this assessment. Descriptive only.")
    if built >= 80.0 and veg < 10.0:
        return (f"High afternoon exposure expected: {built:.0f}% built mass "
                f"with {veg:.0f}% vegetation offers little shade or "
                f"evaporative cooling at peak-heat hours. Descriptive only -- "
                f"the scored heat factor covers night-time release.")
    if built >= 50.0:
        return (f"Moderate afternoon exposure: {built:.0f}% built, "
                f"{veg:.0f}% vegetation. Street-level shade and cool-roof "
                f"treatment would reduce peak-hour load. Descriptive only.")
    return (f"Lower afternoon exposure: {built:.0f}% built, {veg:.0f}% "
            f"vegetation retains shade and cooling. Descriptive only.")


def assumptions_block(
    region_config: Dict[str, Any],
    ledger: Optional[Dict[str, Any]],
    result: Dict[str, Any],
    indicators: Optional[Dict[str, Any]] = None,
) -> str:
    hyd = region_config.get("hydrology", {}) or {}
    therm = region_config.get("thermal", {}) or {}
    trees = region_config.get("trees", {}) or {}
    carbon = region_config.get("carbon", {}) or {}

    lines = ["ASSUMPTIONS AND DATA PROVENANCE", ""]
    lines.append(f"  region                {region_config.get('display_name')}")
    lines.append(f"  working CRS          {region_config.get('crs', {}).get('working_crs_name')}")
    lines.append(f"  design storm         {hyd.get('design_storm_mm')} mm "
                 f"at {hyd.get('return_period_years')}-year return")
    lines.append(f"    status             {hyd.get('design_storm_status')}")
    lines.append(f"    note               {hyd.get('design_storm_note')}")
    lines.append("")
    lines.append(f"  thermal reference    {therm.get('reference_c')} "
                 f"({therm.get('reference_c_status')})")
    lines.append(f"    method             {therm.get('reference_method')}")
    lines.append(f"    uhi span           {therm.get('uhi_max_delta_c')} C "
                 f"({therm.get('uhi_max_delta_status')})")
    # The officer must never mistake the heat score for afternoon heat.
    # Night-only label + retired-day evidence, both sourced from config.
    lines.append(f"  heat score measures  NIGHT-TIME stored heat (annual), "
                 f"site night LST vs rural {therm.get('night_reference_c')} C "
                 f"over a {therm.get('night_uhi_max_delta_c')} C span")
    lines.append(f"    day branch         {therm.get('day_reference_status')}")
    if therm.get("day_reference_note"):
        lines.append(f"    day note           {therm.get('day_reference_note')}")
    if indicators is not None:
        lines.append("")
        lines.append("  AFTERNOON EXPOSURE (unscored context, not a factor)")
        lines.append(f"    {afternoon_context(indicators)}")
    lines.append("")
    tree_total = trees.get("census_total_city_trees")
    lines.append(
        f"  tree baseline        PMC Tree Census {trees.get('census_year')} "
        + (f"({tree_total:,} trees citywide)" if tree_total else "(city total unknown)")
    )
    lines.append(f"    data age           {trees.get('census_data_age_years_at_2026')} years")
    lines.append(f"    age basis          {trees.get('age_estimate_method')}")
    lines.append(f"    age uncertainty    {trees.get('age_estimate_uncertainty')}")
    lines.append("")
    lines.append(f"  carbon bands         {carbon.get('bands_status')}")
    for a in carbon.get("source_anchors", []) or []:
        lines.append(f"    anchor             {a['id']}: {a['value_kgco2e_m2']} kgCO2e/m2")
    lines.append("")
    conf = []
    for k, fac in (result.get("factors") or {}).items():
        c = fac.get("confidence")
        if c and c != "medium":
            conf.append(f"    {FACTOR_LABELS.get(k, k):<14} confidence {c}")
    if conf:
        lines.append("  FACTOR CONFIDENCE")
        lines += conf
    lines += [
        "",
        "  SCOPE LIMIT",
        "  This is decision support, not statutory clearance. Tree felling requires",
        "  Tree Officer permission under the 1975 Act regardless of any score here.",
    ]
    return "\n".join(x for x in lines if x is not None)


def render_report(
    result: Dict[str, Any],
    recs: Dict[str, Any],
    ledger: Optional[Dict[str, Any]] = None,
    relocation: Optional[Dict[str, Any]] = None,
    region_config: Optional[Dict[str, Any]] = None,
    validation: Optional[Dict[str, Any]] = None,
    role: str = "urban_planner",
    indicators: Optional[Dict[str, Any]] = None,
) -> str:
    """Human-readable report. `role` reorders emphasis, never the numbers."""
    region_config = region_config or {}
    role = role if role in ROLE_ORDER else "urban_planner"

    parts: List[str] = []
    parts.append("=" * 72)
    parts.append("CLIMATE IMPACT ASSESSMENT")
    parts.append(f"generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    parts.append("=" * 72)
    parts.append("")

    if validation:
        parts.append(format_site_line(validation))
        parts.append("")

    # Section ORDER is identical for every role: score, then the decision, then
    # the evidence. Role changes how much detail each section carries and where
    # the emphasis lands WITHIN it. An earlier version moved the decision block
    # to the top for municipal_authority only, which made two reports of the
    # same assessment look like two different assessments.
    parts.append(score_block(result, region_config))
    parts.append("")
    parts.append(decision_block(result, recs))
    parts.append("")

    if role != "public_viewer":
        parts.append(canopy_block(ledger))
    # Fixed 2026-10-10: the old public line printed "0 trees recorded"
    # when the ledger was missing -- a loading artefact stated as a finding
    # (the exact failure mode canopy_block's banner guards against).
    elif ledger is None:
        parts.append(
            "On this site: tree data unavailable for this assessment -- "
            "no tree finding is stated."
        )
    else:
        parts.append(
            f"On this site: {ledger.get('total_trees')} trees "
            f"recorded, {result.get('sub_scores', {}).get('green')} green-cover score."
        )

    if relocation and relocation.get("candidates"):
        parts.append("")
        parts.append("RELOCATION SITES (ranked)")
        for c in relocation["candidates"][:5]:
            flag = "" if c["viable"] else "  [NOT VIABLE: " + "; ".join(c["disqualifiers"]) + "]"
            parts.append(
                f"  {c['rank']}. {c['name']}  ward {c['ward_no']}  "
                f"{c['distance_m']:.0f} m  {c['area_hectares']:.2f} ha  "
                f"score {c['composite_score']}{flag}"
            )
        if relocation.get("method_note"):
            parts.append("")
            parts.append(f"  method: {relocation['method_note']}")

    # 2026-10-10: the officer who APPROVES sees provenance too. Before this
    # change only urban_planner/environmental_consultant saw assumptions --
    # municipal_authority got scores with no PROVISIONAL labels, which is
    # exactly how a provisional storm or a night-only heat score gets
    # misread at decision time.
    if role in ("urban_planner", "environmental_consultant",
                "municipal_authority"):
        parts.append("")
        parts.append(assumptions_block(region_config, ledger, result,
                                       indicators))

    if role == "environmental_consultant":
        parts.append("")
        parts.append("CITATIONS")
        for c in LEGAL_CITATIONS:
            parts.append(f"  [{c['id']}]")
            parts.append(f"    {c['text']}")
            parts.append(f"    caveat: {c['note']}")
        cb = (region_config.get("carbon", {}) or {})
        for a in cb.get("source_anchors", []) or []:
            parts.append(f"  [{a['id']}] {a['value_kgco2e_m2']} kgCO2e/m2 — {a['meaning']}")

    parts.append("")
    parts.append("-" * 72)
    parts.append("Scores are deterministic and reproducible. The narrative layer, if")
    parts.append("attached, writes prose only and cannot alter any computed value.")
    return "\n".join(parts)
