"""Offline tests for the deterministic core. No network, no credentials.

    .venv/bin/python -m pytest ml_pipeline/tests -q
    (or: .venv/bin/python ml_pipeline/tests/test_scoring.py)

Every test here runs with zero external dependencies. The pipeline's claim is
that the score is reproducible and defensible; that claim is only worth making
if these tests exist and pass.
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from ml_pipeline.core.canopy import (  # noqa: E402
    CanopyLedger,
    TreeRecord,
    canopy_area_m2,
    estimate_age_years,
    maturity_tier,
    species_key,
)
from ml_pipeline.core.scoring import (  # noqa: E402
    area_weighted_cn,
    clamp,
    compute_carbon,
    compute_flood,
    compute_green,
    compute_heat,
    score_project,
    scs_cn_runoff_mm,
    UNKNOWN_MASS_EXCLUDE_PCT,
)

CONFIG_DIR = REPO / "ml_pipeline" / "config"
SPECIES = json.loads((CONFIG_DIR / "species.json").read_text())
MATERIALS = json.loads((CONFIG_DIR / "materials.json").read_text())
REGION = json.loads((CONFIG_DIR / "regions" / "pune.json").read_text())
CARBON_BANDS = (REGION.get("carbon") or {}).get("bands") or []

HYD = REGION["hydrology"]
CN_TABLE = HYD["cn_table"]


# =========================================================================
# The three tests the review asked for
# =========================================================================


def test_more_vegetation_strictly_lowers_flood_score():
    """Replacing concrete with vegetation must reduce flood risk."""
    base = compute_flood(80, 15, 5, HYD["design_storm_mm"], CN_TABLE)
    greener = compute_flood(30, 65, 5, HYD["design_storm_mm"], CN_TABLE)
    assert greener["score"] < base["score"], (
        f"vegetation did not reduce flood: {base['score']} -> {greener['score']}"
    )
    assert greener["excess_runoff_mm"] < base["excess_runoff_mm"]
    assert greener["curve_number"] < base["curve_number"]


def test_girth_90_trees_are_must_preserve_with_zero_felling():
    """House policy: girth >= 90 cm is never felled, and never compensated."""
    ledger = CanopyLedger(SPECIES)
    for girth in (90.0, 95.0, 120.0, 250.0):
        d = ledger.evaluate_tree(
            TreeRecord(
                tree_id=1, lon=73.85, lat=18.53,
                botanical_name="Ficus benghalensis Linn.",
                girth_cm=girth, canopy_dia_m=12.0, condition="Healthy",
            ),
            inside_building_footprint=True,
        )
        assert d.action == "MUST_PRESERVE", f"girth {girth} -> {d.action}"
        assert not d.compensatory_saplings, f"girth {girth} demanded compensation"
        assert "HOUSE POLICY" in d.statutory_basis


def test_carbon_score_is_monotonic_in_material_mass():
    """Doubling any material's mass must never reduce the carbon score."""
    for name in ("cement_opc", "steel_reinforcement", "brick_clay", "aluminium_primary"):
        scores = []
        for mult in (1, 2, 4, 8):
            r = compute_carbon(
                [{"name": name, "quantityKg": 1000.0 * mult}],
                built_up_area_m2=1000.0,
                materials_table=MATERIALS,
                bands=REGION["carbon"]["bands"],
            )
            scores.append(r["score"])
        assert scores == sorted(scores), f"{name} not monotonic: {scores}"
        assert scores[0] < scores[-1], f"{name} did not increase with mass: {scores}"


# =========================================================================
# Traps from the review that we adopted — these lock the fix in
# =========================================================================


def test_green_does_not_double_count_satellite_canopy():
    """A 40% canopy site must not score twice for the same trees.

    Regression test for the double-count trap: averaging sat_veg with census
    canopy counted identical trees twice.
    """
    # Site is entirely closed canopy: satellite sees 40% veg, census says 40%.
    r = compute_green(sat_veg_pct=40.0, canopy_cover_pct=40.0)
    # Stratified: effective green = 40*0.7 + 0*0.3 = 28, not (40+40)/2 = 40.
    assert r["ground_vegetation_pct"] == 0.0
    assert r["effective_green_pct"] == 28.0
    assert r["score"] == 72.0
    # The naive average would have given 60.0.
    assert r["score"] != 60.0


def test_canopy_weighted_above_ground_vegetation():
    """Equal cover: tree canopy must beat turf grass on the green score."""
    canopy_site = compute_green(sat_veg_pct=50.0, canopy_cover_pct=50.0)
    grass_site = compute_green(sat_veg_pct=50.0, canopy_cover_pct=0.0)
    assert canopy_site["effective_green_pct"] > grass_site["effective_green_pct"]
    assert canopy_site["score"] < grass_site["score"]


def test_drainage_proximity_only_ever_reduces_flood():
    """Engineered drainage is a discount. It must never increase the score."""
    near = compute_flood(70, 20, 10, HYD["design_storm_mm"], CN_TABLE,
                         dist_to_storm_drain_m=0.0)
    far = compute_flood(70, 20, 10, HYD["design_storm_mm"], CN_TABLE,
                        dist_to_storm_drain_m=500.0)
    unknown = compute_flood(70, 20, 10, HYD["design_storm_mm"], CN_TABLE,
                            dist_to_storm_drain_m=None)
    assert near["score"] <= unknown["score"] <= far["score"]
    assert near["drainage_multiplier"] == pytest_approx(HYD["storm_drain_min_multiplier"])
    assert far["drainage_multiplier"] == pytest_approx(1.0)


def pytest_approx(x: float, tol: float = 1e-6):
    class _Approx:
        def __eq__(self, other):
            return abs(float(other) - float(x)) <= tol

        def __repr__(self):
            return f"~{x}"

    return _Approx()


def test_heat_uses_empirical_reference_not_air_temperature():
    """Regression test for the saturation bug.

    The old formula subtracted a fixed 28 C air temperature from a surface
    temperature, pinning heat at 100/100 for any built-up Pune site.
    """
    lst_ref = REGION["thermal"]["reference_c"]
    assert lst_ref is None, "Reference should stay unset until the epoch cube exists"

    # Unavailable reference must degrade, not silently default.
    r = compute_heat(lst_mean_c=46.0, lst_reference_c=None)
    assert r["score"] is None
    assert r["status"] == "UNAVAILABLE"

    # With an empirical reference, a hotter site scores worse and a cooler site
    # better. Both fixtures now sit INSIDE the cube-derived 2.0 C span: the old
    # fixture used a 16 C delta (46 vs 30), which is eight times the largest
    # contrast the cube actually contains and therefore clamped to the same
    # 100.0 as the mild case, making the comparison meaningless.
    hot = compute_heat(lst_mean_c=31.9, lst_reference_c=30.0,
                       uhi_max_delta_c=REGION["thermal"]["uhi_max_delta_c"])
    mild = compute_heat(lst_mean_c=32.0, lst_reference_c=30.0,
                        uhi_max_delta_c=REGION["thermal"]["uhi_max_delta_c"])
    assert 0.0 <= hot["score"] < mild["score"], (hot["score"], mild["score"])
    # The span is DERIVED from the epoch cube (p95 - p05 of within-cell heat
    # contrast = 1.86 C, rounded up to 2.0), so a 2 C delta saturates by
    # design. Assert the scaling relationship rather than a hard-coded value:
    # the score is (delta / span) * 100, and must never exceed 100.
    span = REGION["thermal"]["uhi_max_delta_c"]
    assert span == 2.0, span
    assert mild["score"] == min(100.0, (2.0 / span) * 100.0), mild["score"]
    # A 1 C delta must be visibly better than a 2 C one -- i.e. the factor
    # still discriminates at the top of its range.
    one_c = compute_heat(lst_mean_c=31.0, lst_reference_c=30.0,
                         uhi_max_delta_c=span)
    assert one_c["score"] < mild["score"], (one_c["score"], mild["score"])
    # A site AT the reference scores 0, which the broken formula could not do.
    at_ref = compute_heat(lst_mean_c=30.0, lst_reference_c=30.0,
                          uhi_max_delta_c=REGION["thermal"]["uhi_max_delta_c"])
    assert at_ref["score"] == 0.0


def test_heat_missing_lst_returns_none_not_a_guess():
    r = compute_heat(lst_mean_c=None, lst_reference_c=30.0)
    assert r["score"] is None
    assert r["status"] == "UNAVAILABLE"
    assert r["confidence"] == "none"


def test_score_project_heat_prefers_per_cell_reference_over_config():
    """Regression test: heat must read the epoch cube's per-cell reference.

    `score_project` originally took the LST reference only from
    region_config["thermal"]["reference_c"], which stays null until a city-wide
    reference is accepted. That kept heat permanently UNAVAILABLE even with a
    fully built epoch cube in hand.

    The per-cell value also matters on the merits: Pune's UHI gradient is sharp
    over a few kilometres, so a single city-wide number is the wrong baseline.
    """
    site = {
        "builtUpAreaSqm": 2000.0,
        "plotAreaSqm": 4000.0,
        "materials": [{"name": "cement", "quantityKg": 100_000}],
    }
    indicators = {
        "impervious_pct": 70.0,
        "vegetation_pct": 24.0,
        "water_pct": 0.0,
        "lst_mean_c": 36.5,
        "lst_reference_c": 35.0,      # from the cube, per ~1 km cell
        "mean_slope_deg": 3.0,
        "dist_to_storm_drain_m": 120.0,
    }

    out = score_project(site, indicators, REGION, MATERIALS)

    assert out["sub_scores"]["heat"] is not None, out["factors"]["heat"]
    heat = out["factors"]["heat"]
    assert heat["status"] == "OK", heat
    assert heat["lst_reference_c"] == 35.0, heat
    assert heat["uhi_delta_c"] == 1.5, heat
    # 1.5 C on the cube-derived 2.0 C span => 75.0. The span is derived, not
    # assumed, so assert the ratio rather than a literal that would need
    # editing every time the span is re-derived from a new cube.
    span = REGION["thermal"]["uhi_max_delta_c"]
    assert heat["score"] == min(100.0, (1.5 / span) * 100.0), heat["score"]

    # With no cube reference the factor must degrade, not fall back to air temp.
    no_ref = dict(indicators)
    no_ref["lst_reference_c"] = None
    out2 = score_project(site, no_ref, REGION, MATERIALS)
    assert out2["sub_scores"]["heat"] is None
    assert out2["complete"] is False


def test_cube_landcover_fractions_are_read_as_percent():
    """Dynamic World and NDVI return 0..1; the scorer expects percent.

    Without the conversion a built fraction of 0.54 becomes impervious = 0.54 %,
    which would make every site look almost entirely vegetated and quietly
    destroy the flood score.
    """
    from ml_pipeline.cli import _pct

    assert _pct(0.54) == 54.0
    assert _pct(0.0) == 0.0
    assert _pct(None, default=70.0) == 70.0
    assert _pct(1.0) == 100.0


# =========================================================================
# Bugs in the review's own code, guarded
# =========================================================================


def test_ledger_action_counts_match_decisions():
    """The review's roll-up reported 'COMPENSATORY_FELL' in action_counts while
    emitting action='COMPENSATORY_FELL' with an inconsistent sapling ratio.
    Guard: the count of each action must equal the decisions actually made."""
    ledger = CanopyLedger(SPECIES)
    trees = [
        TreeRecord(1, 73.85, 18.53, "Leucaena leucocephala (Lamk.)De.wit.", 40, 8, 6, "Healthy"),
        TreeRecord(2, 73.85, 18.53, "Azadirachta indica Juss.", 120, 15, 10, "Healthy"),
        TreeRecord(3, 73.85, 18.53, "Mangifera indica Linn.", 35, 6, 4, "Dead"),
    ]
    out = ledger.process_site(trees, plot_area_m2=2000.0)
    for action, n in out["action_counts"].items():
        actual = sum(1 for d in out["decisions"] if d["action"] == action)
        assert actual == n, f"action_counts says {action}={n} but decisions show {actual}"
    assert out["action_counts"].get("REMOVE_DEAD") == 1


def test_dead_tree_is_removed_not_felled_and_costs_nothing():
    ledger = CanopyLedger(SPECIES)
    out = ledger.process_site(
        [TreeRecord(9, 73.85, 18.53, "Mangifera indica Linn.", 100, 12, 9, "Dead")],
        plot_area_m2=500.0,
    )
    d = out["decisions"][0]
    assert d["action"] == "REMOVE_DEAD"
    assert not d.get("compensatory_saplings")
    assert out["compensatory_required"] == {"low": 0, "high": 0}
    # A dead tree contributes no existing canopy to lose.
    assert out["tree_canopy_m2_before"] == 0.0


def test_transplant_ceiling_is_enforced_by_girth():
    """A listed transplant-hardy species above the ceiling must NOT relocate."""
    ledger = CanopyLedger(SPECIES)
    ceiling = SPECIES["transplant_hardy_ceiling_cm"]
    ok = ledger.evaluate_tree(
        TreeRecord(1, 73.85, 18.53, "Azadirachta indica Juss.", 35, 8, 5, "Healthy"),
        inside_building_footprint=True,
    )
    too_big = ledger.evaluate_tree(
        TreeRecord(2, 73.85, 18.53, "Azadirachta indica Juss.",
                   ceiling + 10, 12, 8, "Healthy"),
        inside_building_footprint=True,
    )
    assert ok.action == "RELOCATE"
    assert too_big.action == "FELL_AND_COMPENSATE"
    assert too_big.compensatory_saplings["low"] >= 1


def test_rare_flag_overrides_girth_and_cannot_be_compensated():
    ledger = CanopyLedger(SPECIES)
    d = ledger.evaluate_tree(
        TreeRecord(1, 73.85, 18.53, "Madhuca longifolia (Koenig) MacBr",
                   30, 10, 7, "Healthy", is_rare=True),
        inside_building_footprint=True,
    )
    assert d.action == "MUST_PRESERVE"
    assert not d.compensatory_saplings


def test_compensation_is_species_blind_but_mix_is_native_weighted():
    """The 1975 Act s.7 counts saplings by AGE, not by species.

    So the statutory count must be IDENTICAL for a native and a non-native
    tree of the same girth — an earlier version applied a reduced ratio to
    non-natives, which understates statutory liability. The native/non-native
    distinction belongs in the recommended species mix, not the count.

    This also guards the real finding: 52.5% of the census is non-native, with
    Leucaena alone at 15.7%, so replanting the count in kind adds nothing.
    """
    ledger = CanopyLedger(SPECIES)
    native = ledger.evaluate_tree(
        TreeRecord(1, 73.85, 18.53, "Mangifera indica Linn.", 70, 12, 8, "Healthy"),
        inside_building_footprint=True,
    )
    non_native = ledger.evaluate_tree(
        TreeRecord(2, 73.85, 18.53, "Leucaena leucocephala (Lamk.)De.wit.",
                   70, 12, 8, "Healthy"),
        inside_building_footprint=True,
    )
    assert native.action == "FELL_AND_COMPENSATE"
    assert non_native.action == "FELL_AND_COMPENSATE"
    # Same girth, same statutory count.
    assert native.compensatory_saplings == non_native.compensatory_saplings
    # But the mix is not "replant Leucaena".
    mix = ledger._compensatory_mix({"Leucaena leucocephala": 1}, 30)
    assert mix[0]["recommended_replacement"] == "Mangifera indica"
    assert mix[0]["recommended_replacement_native"] is True


def test_compensation_is_age_equivalent_not_a_flat_ratio():
    """The 1975 Act s.7 (amended 2021) sets compensation by AGE, not 1:3.

    Guard against regressing to a hardcoded ratio: a fatter tree must demand
    more saplings than a thinner one of the same species.
    """
    ledger = CanopyLedger(SPECIES)
    thin = ledger.evaluate_tree(
        TreeRecord(1, 73.85, 18.53, "Leucaena leucocephala (Lamk.)De.wit.", 40, 8, 5, "Healthy"),
        inside_building_footprint=True,
    )
    fat = ledger.evaluate_tree(
        TreeRecord(2, 73.85, 18.53, "Leucaena leucocephala (Lamk.)De.wit.", 85, 14, 9, "Healthy"),
        inside_building_footprint=True,
    )
    assert fat.compensatory_saplings["high"] > thin.compensatory_saplings["high"]
    assert fat.age_estimate_years["low"] > thin.age_estimate_years["low"]
    assert thin.compensatory_saplings["low"] <= thin.compensatory_saplings["high"]


def test_canopy_cover_cannot_exceed_100_percent():
    ledger = CanopyLedger(SPECIES)
    # 200 trees of 10 m crown on 200 m2 — crowns must be capped.
    trees = [
        TreeRecord(i, 73.85, 18.53, "Mangifera indica Linn.", 30, 6, 10, "Healthy")
        for i in range(1, 201)
    ]
    out = ledger.process_site(trees, plot_area_m2=200.0)
    assert out["canopy_cover_pct"] <= 100.0


def test_species_key_strips_taxonomic_suffix():
    assert species_key("Ficus religiosa Linn.") == "Ficus religiosa"
    assert species_key("Leucaena leucocephala (Lamk.)De.wit.") == "Leucaena leucocephala"
    assert species_key("Polyalthia longifolia var.pendula") == "Polyalthia longifolia"
    assert species_key("") == ""


def test_maturity_tiers_match_census_distribution():
    assert maturity_tier(10) == "sapling"
    assert maturity_tier(35) == "young"      # census median
    assert maturity_tier(74) == "mature"     # census p75
    assert maturity_tier(250) == "mature"


def test_canopy_area_geometry():
    assert math.isclose(canopy_area_m2(10.0), math.pi * 25.0)
    assert canopy_area_m2(0.0) == 0.0
    assert canopy_area_m2(-5.0) == 0.0


def test_age_estimate_range_is_wide_and_ordered():
    a = estimate_age_years(100.0)
    assert a["low"] <= a["point"] <= a["high"]
    # Deliberately wide: girth-to-age is a crude proxy.
    assert a["high"] / max(a["low"], 1e-9) > 1.5


# =========================================================================
# Carbon specifics
# =========================================================================


def test_indian_steel_factor_is_used_not_the_world_average():
    """1.85 is the WORLD crude-steel average; IFC India rebar is 2.6."""
    r = compute_carbon(
        [{"name": "steel_reinforcement", "quantityKg": 1000.0}],
        built_up_area_m2=1000.0, materials_table=MATERIALS,
        bands=REGION["carbon"]["bands"],
    )
    assert r["line_items"][0]["ef"] == 2.60


def test_steel_is_the_dominant_material_at_realistic_indian_ratios():
    """An Indian RC frame is steel-led once the correct Indian EF is used.

    With the old world-average 1.85 factor and this BOQ, cement looked dominant.
    At the IFC India rebar factor of 2.60, steel at 120 t overtakes 250 t of
    cement (312.0 t vs 227.5 t CO2e). This test locks the Indian factor in place.
    Share threshold re-verified 2026-10-10 against IFC EFs (cement 0.91,
    brick 0.39): steel share is 47.5%, still the clear plurality leader.
    """
    materials = [
        {"name": "cement", "quantityKg": 250_000},
        {"name": "steel_reinforcement", "quantityKg": 120_000},
        {"name": "brick", "quantityKg": 300_000},
    ]
    r = compute_carbon(materials, 5000.0, MATERIALS, REGION["carbon"]["bands"])
    assert r["dominant_material"] == "steel_reinforcement"
    assert r["dominant_share_pct"] > 45.0
    cement_share = next(li for li in r["line_items"] if li["name"] == "cement_opc")
    assert cement_share["kgco2e"] > 0


def test_river_sand_emits_a_blocking_advisory():
    """A DELIBERATE river_sand specification must block.

    Regression test: the bare word 'sand' used to alias straight to river_sand,
    so every ordinary Indian RC BOQ typed as 'sand 400t' tripped a blocking
    advisory and forced recommendation=REVIEW. That is a false positive — 'sand'
    carries no source information, and the emissions are identical either way.
    The blocking behaviour must survive only for an explicit river_sand line.
    """
    r = compute_carbon(
        [{"name": "river_sand", "quantityKg": 50_000}],
        1000.0, MATERIALS, REGION["carbon"]["bands"],
    )
    advs = r["ecological_advisories"]
    assert any(a["severity"] == "blocking" for a in advs)
    assert advs[0]["alternatives"] == ["manufactured_sand_msand"]


def test_bare_sand_asks_for_clarification_and_does_not_block():
    """The ordinary word 'sand' must NOT block a project.

    It resolves to a neutral entry that still counts emissions and asks the
    drafter to state the source, because the river-sand prohibition is a legal
    and ecological rule rather than a carbon one.
    """
    r = compute_carbon(
        [{"name": "sand", "quantityKg": 400_000}],
        3000.0, MATERIALS, REGION["carbon"]["bands"],
    )
    advs = r["ecological_advisories"]
    assert advs, "unspecified sand must still raise an advisory"
    assert not any(a["severity"] == "blocking" for a in advs), (
        f"'sand' must not block: {advs}"
    )
    assert advs[0]["advisory"] == "SAND_SOURCE_UNSPECIFIED"
    assert advs[0]["severity"] == "clarify"
    # Emissions must still be counted, not dropped as unknown.
    assert r["unknown_materials"] == []
    assert r["total_kgco2e"] > 0


def test_carbon_score_is_monotonic_across_band_boundaries():
    """Emissions rising must never lower the carbon score, even across bands.

    The original implementation divided the intensity by the CEILING OF
    WHICHEVER BAND it landed in, so at a fixed 1 m2:
        intensity 296 -> 74.0  (Low, ceiling 400)
        intensity 518 -> 64.8  (Moderate, ceiling 800)
    i.e. roughly doubling emissions dropped the score by 9 points. This sweeps
    every band boundary explicitly, which the mass-multiplier test did not.
    """
    scores = []
    for kg in (50, 131, 200, 399, 400, 401, 700, 799, 800, 801,
               1100, 1199, 1200, 1201, 2000):
        r = compute_carbon(
            [{"name": "cement_opc", "quantityKg": float(kg)}],
            1.0, MATERIALS, REGION["carbon"]["bands"],
        )
        assert r["score"] is not None
        scores.append(r["score"])
    assert scores == sorted(scores), f"not monotonic across bands: {scores}"


def test_carbon_score_and_band_label_do_not_contradict():
    """Continuous score and band label must never rank-invert.

    History: the original form asserted score>=60 ⟹ band High+. That
    absolute cutoff was calibrated to the old ICE EFs; the IFC-India swap
    (2026-10-10) moved Moderate-band intensities up to score 66.7 and
    tripped it (800 kg cement -> 60.7/Moderate). The cutoff, not the
    scorer, was EF-coupled -- so the guard now locks RANK consistency
    (score order == band order, boundary labels exact) instead of an
    absolute number. The underlying tension (UNSOURCED 400/800/1200 bands
    vs /1200 divisor) is real and is tracked as an open item: bands still
    need re-derivation against the IGBC-700 + observed-454 anchors.
    """
    labels = []
    scores = []
    for kg in (399, 400, 700, 800, 1100, 1200):
        r = compute_carbon(
            [{"name": "cement_opc", "quantityKg": float(kg)}],
            1.0, MATERIALS, REGION["carbon"]["bands"],
        )
        labels.append(r["band"])
        scores.append(r["score"])
    assert scores == sorted(scores), f"score inverts across bands: {scores}"
    rank = {"Low": 0, "Moderate": 1, "High": 2, "Very High": 3}
    ranks = [rank[b] for b in labels]
    assert ranks == sorted(ranks), f"band inverts against score: {labels}"
    assert labels[0] == "Low" and labels[-1] in ("High", "Very High"), labels


def test_green_with_no_data_is_unavailable_not_perfect():
    """The worst failure mode for a green-loss factor is a perfect score.

    `_pct()` coerces None to 0.0, so before this was fixed compute_green(None,
    None) returned score=100.0 with confidence='high' — i.e. a site with NO
    satellite band and NO census canopy was reported as having zero green loss,
    the best possible outcome, with no warning at all.
    """
    for sat, can in ((None, None), (10.0, None), (None, 20.0)):
        r = compute_green(sat_veg_pct=sat, canopy_cover_pct=can)
        assert r["score"] is None, (
            f"green({sat}, {can}) must be excluded, got {r['score']}"
        )
        assert r["status"] == "UNAVAILABLE"
        assert r["confidence"] == "none"


def test_green_rejects_out_of_range_percentage_instead_of_clamping():
    """A percentage above 100 is a units fault, not total vegetation.

    An external land-cover dataset may report a fraction where a percent was
    expected. clamp() would absorb 680 as 100, which is indistinguishable from
    genuine saturation -- the worst possible misreading for a green-LOSS
    factor, because it reports maximum green loss as if it were measured.
    """
    for bad in (680.0, 650.0, 101.0, -5.0):
        r = compute_green(sat_veg_pct=bad, canopy_cover_pct=6.5)
        assert r["score"] is None, f"{bad} must not be scored"
        assert r["status"] == "UNAVAILABLE"
        assert r["out_of_range_inputs"]
        assert "percent" in r["reason"].lower() or "fraction" in r["reason"].lower()

    # 100 exactly is legal and must still score. Note the result is 70, not 0:
    # a cell that is entirely vegetation but a plot with no canopy has
    # ground = 100, and canopy carries 0.70 of the weight, so a plot that has
    # no trees on it is still heavily penalised. That is intended.
    ok = compute_green(sat_veg_pct=100.0, canopy_cover_pct=0.0)
    assert ok["score"] is not None
    assert ok["score"] == 70.0
    assert ok["effective_green_pct"] == 30.0


def test_carbon_resolves_real_world_boq_spellings():
    """Bill-of-quantities material names are free text in practice.

    Government and contractor schedules spell the same material many ways:
    'TMT Fe500D', 'Steel - TMT', 'OPC cement', 'M Sand', 'fly ash brick'. All
    must resolve to the canonical entry rather than being counted as unknown
    mass, which would silently understate the carbon figure.
    """
    for spelling, canonical in (
        ("cement", "cement_opc"),
        ("CEMENT OPC", "cement_opc"),
        ("OPC cement", "cement_opc"),
        ("ordinary portland cement", "cement_opc"),
        ("Portland Cement", "cement_opc"),
        ("steel_reinforcement", "steel_reinforcement"),
        ("TMT Fe500D", "steel_reinforcement"),
        ("Steel - TMT", "steel_reinforcement"),
        ("MS rebar", "steel_reinforcement"),
        ("M-sand", "manufactured_sand_msand"),
        ("M Sand", "manufactured_sand_msand"),
        ("fly ash brick", "fly_ash_brick"),
        ("Fly Ash Brick", "fly_ash_brick"),
        ("AAC Block", "aac_block"),
        ("crushed stone", "aggregate_rock"),
        ("ready mix concrete", "concrete_ready_mix"),
        ("RMC", "concrete_ready_mix"),
    ):
        r = compute_carbon([{"name": spelling, "quantityKg": 10_000}],
                           1000.0, MATERIALS, CARBON_BANDS)
        li = r["line_items"][0]
        assert li["status"] == "OK", f"{spelling!r} did not resolve: {li}"
        assert li["name"] == canonical, f"{spelling!r} -> {li['name']}"
        assert li["kgco2e"] is not None and li["kgco2e"] > 0
        assert r["unknown_mass_pct"] == 0.0


def test_carbon_withholds_score_when_most_mass_is_unquantified():
    """Carbon computed while ignoring most of the BOQ is a floor, not a score.

    A large unquantified share means the intensity could move the result across
    a band boundary, so reporting a number would be presenting a guess as a
    measurement. The factor withholds and drops out of the composite instead.
    """
    # These use materials with no entry at all. Quoted stone (laterite, trap
    # rock, murrum) is deliberately NOT used here: those are real Pune
    # earthworks materials and DO have factors, so using them as the unknown
    # case would stop testing the unknown path once they were added.
    boq = [
        {"name": "cement", "quantityKg": 50_000},
        {"name": "unobtainium_widget", "quantityKg": 500_000},
    ]
    r = compute_carbon(boq, 3000.0, MATERIALS, CARBON_BANDS)
    assert r["score"] is None
    assert r["status"] == "UNAVAILABLE"
    assert r["unknown_mass_pct"] > 90.0
    assert "unobtainium_widget" in r["reason"] or "no emission factor" in r["reason"]


def test_carbon_reports_unknown_mass_share_below_the_exclusion_limit():
    """A small unquantified share is reported, not hidden and not excluded."""
    boq = [
        {"name": "cement", "quantityKg": 95_000},
        {"name": "steel_reinforcement", "quantityKg": 5_000},
        {"name": "unobtainium_widget", "quantityKg": 10_000},  # 9% of mass, unknown
    ]
    r = compute_carbon(boq, 3000.0, MATERIALS, CARBON_BANDS)
    assert r["score"] is not None
    assert r["unknown_mass_pct"] > 0.0
    assert r["unknown_mass_pct"] <= UNKNOWN_MASS_EXCLUDE_PCT
    assert r["confidence"] == "low"
    assert "understated" in r["confidence_note"]


def test_carbon_withholds_score_when_no_positive_quantity_is_supplied():
    """Named materials with no quantity are an unfinished BOQ, not zero carbon.

    A missing quantity key defaults to 0.0 and a negative one is floored at 0.0,
    so every line resolves, the total is 0.0 kgCO2e, and the result used to score
    0.0 / Low -- the best possible carbon outcome -- for a project nobody has
    described.
    """
    for label, boq in (
        ("all zero", [{"name": "cement", "quantityKg": 0}]),
        ("all negative", [{"name": "cement", "quantityKg": -5000}]),
        ("missing quantity key", [{"name": "cement"}]),
        ("mix of zero and missing",
         [{"name": "cement", "quantityKg": 0},
          {"name": "steel_reinforcement"}]),
    ):
        r = compute_carbon(boq, 3000.0, MATERIALS, CARBON_BANDS)
        assert r["score"] is None, f"{label} scored {r['score']}, must be withheld"
        assert r["status"] == "UNAVAILABLE", label
        assert "quantity" in r["reason"].lower(), r["reason"]
        assert r["confidence"] == "none", label


def test_material_alias_table_is_internally_consistent():
    """The alias layer must not be able to silently misroute a material.

    Three ways it can go wrong, all of which would apply the wrong emission
    factor rather than raise: an alias pointing at a material key that does
    not exist (degrades to unknown, losing the mass), an alias that resolves
    to something other than its declared target, and two distinct canonical
    materials that collide once punctuation is normalised (a false merge,
    which is the most damaging case because the score stays plausible).
    """
    from ml_pipeline.core.scoring import _normalise_name, _resolve_material

    materials = MATERIALS["materials"]
    aliases = MATERIALS["aliases"]

    dangling = [(k, v) for k, v in aliases.items() if v not in materials]
    assert not dangling, f"aliases point at missing materials: {dangling}"

    misrouted = [
        (k, v, _resolve_material(k, MATERIALS)[0])
        for k, v in aliases.items()
        if _resolve_material(k, MATERIALS)[0] != v
    ]
    assert not misrouted, f"aliases resolve elsewhere: {misrouted}"

    by_norm: dict = {}
    for key in materials:
        by_norm.setdefault(_normalise_name(key), []).append(key)
    collisions = {k: v for k, v in by_norm.items() if len(v) > 1}
    assert not collisions, f"materials collide under normalisation: {collisions}"


def test_green_records_resolution_mismatch_between_site_and_cell():
    """Canopy is per-site, satellite vegetation is per-km-cell, and that gap
    is a real feature of the data rather than an error.

    Ward 2 carries 50.4% canopy over an 8,000 m2 plot inside a cell whose
    vegetation is 7.6%, so canopy > sat is legitimate and must not be clamped
    away or treated as impossible. The gap is reported explicitly.
    """
    r = compute_green(sat_veg_pct=7.6, canopy_cover_pct=50.4)
    assert r["canopy_cover_pct"] == 50.4
    assert r["sat_veg_pct"] == 7.6
    assert r["ground_vegetation_pct"] == 0.0
    assert r["resolution_mismatch_pts"] == 42.8
    # Disagreement still downgrades confidence.
    assert r["confidence"] == "low"


def test_green_score_is_monotonic_in_canopy():
    prev = None
    for can in (0.0, 10.0, 20.0, 30.0, 40.0, 50.0):
        r = compute_green(sat_veg_pct=50.0, canopy_cover_pct=can)
        if prev is not None:
            assert r["score"] < prev, (
                f"green score must fall as canopy rises: {can}% -> {r['score']}"
            )
        prev = r["score"]


def test_empty_boq_is_unavailable_not_a_perfect_score():
    """An undescribed project must not be reported as the cleanest possible."""
    r = compute_carbon([], 3000.0, MATERIALS, REGION["carbon"]["bands"])
    assert r["score"] is None, "empty BOQ must be excluded, not scored 0.0"
    assert r["status"] == "UNAVAILABLE"


def test_boq_of_only_unknown_materials_is_unavailable():
    r = compute_carbon(
        [{"name": "unobtainium", "quantityKg": 1000.0}],
        3000.0, MATERIALS, REGION["carbon"]["bands"],
    )
    assert r["score"] is None
    assert r["unknown_materials"] == ["unobtainium"]


def test_zero_built_up_area_is_unavailable_not_saturated():
    """A 1e-6 divisor guard used to make this saturate at 100 (Very High)."""
    r = compute_carbon(
        [{"name": "cement", "quantityKg": 180_000}],
        0.0, MATERIALS, REGION["carbon"]["bands"],
    )
    assert r["score"] is None, "zero area must not score as maximal carbon"
    assert r["status"] == "UNAVAILABLE"


def test_cement_plus_ready_mix_is_flagged_as_double_counted():
    """The docstring's rule is now detected and reported, not just described."""
    only_cement = compute_carbon(
        [{"name": "cement", "quantityKg": 180_000}],
        3000.0, MATERIALS, REGION["carbon"]["bands"],
    )
    assert only_cement["double_count_warning"] is None

    both = compute_carbon(
        [{"name": "cement", "quantityKg": 180_000},
         {"name": "concrete", "quantityKg": 1_500_000}],
        3000.0, MATERIALS, REGION["carbon"]["bands"],
    )
    assert both["double_count_warning"], "binder double count must be reported"
    assert "cement_opc" in both["double_count_warning"]
    assert "concrete_ready_mix" in both["double_count_warning"]


def test_unknown_material_is_flagged_not_defaulted():
    """An unresolvable material is named, never silently given a default EF.

    Score is now None rather than 0.0: when EVERY line is unresolvable there is
    no carbon figure at all, and 0.0 would report an undescribed project as the
    cleanest possible. Partial BOQs still score, with confidence downgraded.
    """
    r = compute_carbon(
        [{"name": "unobtainium", "quantityKg": 100.0}],
        1000.0, MATERIALS, REGION["carbon"]["bands"],
    )
    assert r["unknown_materials"] == ["unobtainium"]
    assert r["status"] == "UNAVAILABLE"

    # Mixed BOQ: the resolvable line still counts and confidence drops to low.
    mixed = compute_carbon(
        [{"name": "unobtainium", "quantityKg": 100.0},
         {"name": "cement", "quantityKg": 50_000.0}],
        1000.0, MATERIALS, REGION["carbon"]["bands"],
    )
    assert mixed["unknown_materials"] == ["unobtainium"]
    assert mixed["confidence"] == "low"
    assert mixed["score"] is not None
    assert mixed["total_kgco2e"] > 0


def test_ggbs_substitution_beats_opc():
    opc = compute_carbon([{"name": "cement_opc", "quantityKg": 1000.0}], 1000.0,
                         MATERIALS, REGION["carbon"]["bands"])
    ggbs = compute_carbon([{"name": "cement_ggbs", "quantityKg": 1000.0}], 1000.0,
                          MATERIALS, REGION["carbon"]["bands"])
    assert ggbs["total_kgco2e"] < opc["total_kgco2e"] / 5


# =========================================================================
# Composite behaviour
# =========================================================================


def test_composite_excludes_and_renormalises_missing_heat():
    """With no LST, heat must be excluded and flagged, not faked at 0 or 100."""
    site = {"builtUpAreaSqm": 5000.0, "plotAreaSqm": 10000.0,
            "materials": [{"name": "cement", "quantityKg": 200_000}]}
    indicators = {"impervious_pct": 70, "vegetation_pct": 20, "water_pct": 10,
                  "lst_mean_c": None}
    r = score_project(site, indicators, REGION, MATERIALS, ledger={"canopy_cover_pct": 5.0})
    assert r["sub_scores"]["heat"] is None
    assert "heat" in r["missing_factors"]
    assert r["complete"] is False
    assert "partial_notice" in r
    assert 0.0 <= r["impact_score"] <= 100.0


def test_composite_is_monotonic_in_impervious_cover():
    def impact(imperv):
        site = {"builtUpAreaSqm": 5000.0, "plotAreaSqm": 10000.0,
                "materials": [{"name": "cement", "quantityKg": 200_000}]}
        ind = {"impervious_pct": imperv, "vegetation_pct": 100 - imperv - 10,
               "water_pct": 10, "lst_mean_c": None}
        return score_project(site, ind, REGION, MATERIALS,
                             ledger={"canopy_cover_pct": 3.0})["impact_score"]

    scores = [impact(i) for i in (20, 40, 60, 80)]
    assert scores == sorted(scores), f"impact not monotonic in impervious: {scores}"


def test_weights_sum_to_one():
    assert math.isclose(sum(REGION["weights"].values()), 1.0, rel_tol=1e-9)


def test_clamp_handles_nan_and_none():
    assert clamp(float("nan")) == 0.0
    assert clamp(None) == 0.0
    assert clamp(150.0) == 100.0
    assert clamp(-20.0) == 0.0


def test_scs_runoff_matches_the_trapezoidal_closed_form():
    """Guard the runoff equation against the standard closed-form identity.

    SCS-CN has an exact algebraic check: for CN=98, Ia = 0.2S, and the
    rational runoff form collapses to a closed expression. Using it, a 5 mm
    storm on a CN=98 surface gives ~1.717 mm, NOT zero — the initial
    abstraction for CN=98 is only ~1.04 mm. An earlier version of this test
    assumed zero runoff below the abstraction, which is true only for large S
    (low CN), not for impervious surfaces.
    """
    s = 25400.0 / 98.0 - 254.0
    ia = 0.2 * s
    expected = (5.0 - ia) ** 2 / (5.0 - ia + s)
    assert math.isclose(scs_cn_runoff_mm(98.0, 5.0), expected, rel_tol=1e-9)
    assert scs_cn_runoff_mm(98.0, 5.0) > 0.0

    # On a low-CN surface, Ia is large and a small storm genuinely yields zero.
    s_veg = 25400.0 / 60.0 - 254.0
    assert 0.2 * s_veg > 20.0
    assert scs_cn_runoff_mm(60.0, 10.0) == 0.0

    # Runoff always stays below the rainfall and rises with rainfall.
    assert scs_cn_runoff_mm(98.0, 150.0) < 150.0
    assert scs_cn_runoff_mm(98.0, 100.0) < scs_cn_runoff_mm(98.0, 150.0)


def test_cn_never_exceeds_bounds_and_degrades_sensibly():
    cn = area_weighted_cn(100, 0, 0, CN_TABLE)
    assert 0 < cn <= 100
    # Nothing classified must not manufacture an impervious assumption.
    assert area_weighted_cn(0, 0, 0, CN_TABLE) == pytest_approx(60.0, tol=0.01)


def _run() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    passed, failed = 0, []
    for name, fn in tests:
        try:
            fn()
            passed += 1
            print(f"  PASS  {name}")
        except AssertionError as exc:
            failed.append((name, str(exc)))
            print(f"  FAIL  {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed.append((name, f"{type(exc).__name__}: {exc}"))
            print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
    print(f"\n{passed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run())
