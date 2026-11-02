"""Deterministic climate scorer — the credibility core of the pipeline.

Pure functions. No network, no file reads, no randomness. Same inputs always
produce the same scores, which is what makes the output defensible in a
municipal hearing and testable in CI.

Four factors, weighted 0.30 / 0.30 / 0.20 / 0.20 for Pune:

    flood   SCS-CN excess runoff vs a fully vegetated baseline, modified by
            slope and by proximity to ENGINEERED storm drainage.
    heat    Urban heat island as a DELTA from an empirical city-wide
            reference LST, never from a fixed air temperature.
    green   100 - effective green, where effective green stratifies tree
            canopy (0.70) from ground vegetation (0.30).
    carbon  Embodied carbon intensity per m2 of built-up area.

Two structural properties this module is designed around:

  1. No double counting. Sentinel-2 vegetation pixels already contain tree
     canopy, so averaging satellite vegetation with census canopy cover counts
     the same trees twice and inflates a "green" signal. green.py stratifies
     instead.

  2. No saturation. Comparing a surface temperature against a fixed air
     temperature pins the heat factor at 100/100 for any built-up site. The
     reference here is empirical and the delta is normalised.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

# --- materials table is loaded lazily by the caller; this module takes it as
# --- a plain dict so it stays pure and trivially testable.

MIN_SCORE = 0.0
MAX_SCORE = 100.0


def clamp(value: float, low: float = MIN_SCORE, high: float = MAX_SCORE) -> float:
    """Clamp to a closed range, coercing NaN/None to `low`."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return low
    if v != v:  # NaN
        return low
    return max(low, min(high, v))


def _as_number(value: Any) -> Optional[float]:
    """Return a finite float, or None for absent/non-numeric/NaN input.

    This is the missing-data boundary for the flood factor. `_pct()` returns a
    default (usually 0.0), which is useful for optional terms but catastrophic
    for mandatory land cover: zero impervious and zero vegetation is a perfect
    score, not an unknown one. Flood uses this helper so None can never be read
    as "0%".
    """
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    return v


class Recommendation(str):
    """Verdict code that remains JSON-compatible with the legacy string schema.

    `score_project` has always exposed `result["recommendation"]` as a plain
    string. Callers also need the structured form, so this subclass answers
    `result["recommendation"]["recommendation"]` and
    `result["recommendation"]["headline"]` while serialising as the same string
    JSON has always received. That avoids a schema break for the report,
    narrator and existing artifacts.
    """

    def __new__(cls, code: str, headline: str = "") -> "Recommendation":
        obj = super().__new__(cls, code)
        obj.headline = headline
        return obj

    def __getitem__(self, key: Any) -> Any:
        if key == "recommendation":
            return str(self)
        if key == "headline":
            return self.headline
        return super().__getitem__(key)


# Four annual land-cover bands are fractions of the cell and should sum to 1.
# A small tolerance absorbs four-decimal rounding in the cube (the live cube's
# worst over-sum is 0.0001); anything larger is a source inconsistency and is
# reported rather than absorbed.
LANDCOVER_SUM_TOLERANCE = 0.001


# Percentages above this are far more likely to be a units error than a real
# observation. Nothing on Earth is 100%+ vegetated, so a value in this range is
# either a fraction passed where a percent was expected (0.068 read as 6.8 is
# benign, but 6.8 recorded as 680 is not) or a fraction/percent mix-up further
# upstream. Values in this band are reported as a data fault rather than clamped
# to 100, because clamping makes a units bug indistinguishable from genuine
# saturation -- the single most damaging failure mode for a green-loss factor.
IMPLAUSIBLE_PCT_ABOVE = 100.0
IMPLAUSIBLE_PCT_BELOW = 0.0


def _pct(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# =========================================================================
# FLOOD
# =========================================================================


def area_weighted_cn(
    impervious_pct: float,
    vegetation_pct: float,
    water_pct: float,
    cn_table: Dict[str, float],
    bare_pct: Optional[float] = None,
) -> float:
    """Composite curve number from areal cover fractions.

    Standard SCS-CN (NRCS TR-55): the composite CN is the AREAL WEIGHTED MEAN
    of the curve numbers, and the weights are the fractions of the whole area.

    The divisor is therefore 100, always. Dividing by the sum of the supplied
    fractions instead -- renormalising -- is only valid when those fractions
    already account for the entire cell, which is the assumption this function's
    previous implementation made and the cube violated:

        built + vegetation + water   -> divided by their own sum

    With the old cube those three covered a median 0.589 of each cell (grass,
    crops, shrub and flooded vegetation were never stored, and `vegetation_pct`
    was NDVI from a different sensor). Renormalising inflated the curve number by
    a mean +38.3, up to +78.1, across the 864 cells -- worst in the LEAST-built
    cells, because those had the largest unaccounted remainder. Every resulting
    runoff depth was inflated too, by a mean +85 mm at the 150 mm design storm.

    `bare_pct` is optional and defaults to the residual, so a caller that only
    has three bands still gets an honest curve number rather than an inflated
    one: the missing area is treated as bare soil, which is the conservative
    choice and the correct one for the NRCS land-cover classes that Dynamic World
    does not name (crops and shrub in particular infiltrate less than the
    vegetation figure implies).

    With all four bands supplied and the cube as a true partition, the sum is
    100 and no residual is needed.

    An over-sum is renormalised EXPLICITLY. The old code clamped `accounted` to
    1.0 but left the fractions unnormalised, which silently counted the overlap
    twice and drove CN to saturation (166/864 cells reached CN >= 99.99 when
    seasonal bare was added to an already-complete annual partition). A source
    that sums above 1 is still reported by `compute_flood`; this function only
    keeps the arithmetic an honest areal mean.
    """
    imperv = clamp(_pct(impervious_pct)) / 100.0
    veg = clamp(_pct(vegetation_pct)) / 100.0
    water = clamp(_pct(water_pct)) / 100.0
    bare = clamp(_pct(bare_pct)) / 100.0

    accounted = imperv + veg + water + bare
    if accounted > 1.0:
        # Explicit renormalisation: the supplied bands over-describe the cell,
        # so divide every band by the over-sum before weighting. This preserves
        # the areal-mean definition AND avoids the old saturation bug.
        imperv /= accounted
        veg /= accounted
        water /= accounted
        bare /= accounted
        accounted = 1.0

    if accounted <= 0:
        # Nothing classified: fall back to fully vegetated rather than assuming
        # bare/impervious, which would manufacture a flood penalty.
        return float(cn_table.get("vegetation", 60.0))

    cn = (
        veg * float(cn_table.get("vegetation", 60.0))
        + imperv * float(cn_table.get("impervious", 98.0))
        + water * float(cn_table.get("water", 100.0))
        + bare * float(cn_table.get("bare", 90.0))
    )

    # The unaccounted remainder is bare soil by default: it is the highest-CN
    # class that Dynamic World does not resolve separately in this pipeline, and
    # assuming it infiltrates like vegetation would understate runoff.
    residual = 1.0 - accounted
    if residual > 0:
        cn += residual * float(cn_table.get("bare", 90.0))

    return clamp(cn, 1.0, 100.0)


def scs_cn_runoff_mm(cn: float, rainfall_mm: float) -> float:
    """Direct runoff depth in mm from the SCS-CN loss equation."""
    p = _pct(rainfall_mm)
    if p <= 0:
        return 0.0
    s = (25400.0 / clamp(cn, 1.0, 100.0)) - 254.0
    if s <= 0:
        return p
    ia = 0.2 * s
    if p <= ia:
        return 0.0
    return ((p - ia) ** 2) / (p - ia + s)


def compute_flood(
    impervious_pct: Optional[float],
    vegetation_pct: Optional[float],
    water_pct: Optional[float],
    design_storm_mm: float,
    cn_table: Dict[str, float],
    bare_pct: Optional[float] = None,
    mean_slope_deg: Optional[float] = None,
    dist_to_storm_drain_m: Optional[float] = None,
    slope_full_effect_deg: float = 15.0,
    slope_max_multiplier: float = 1.25,
    drain_full_benefit_m: float = 500.0,
    drain_min_multiplier: float = 0.80,
    bare_season_pct: Optional[float] = None,
    landcover_source: Optional[str] = None,
) -> Dict[str, Any]:
    """Flood factor.

    `impervious_pct`, `vegetation_pct` and `water_pct` are MANDATORY measured
    (or explicitly user-supplied) percentages. None, NaN or a non-numeric value
    makes the factor UNAVAILABLE. They must never be defaulted to zero: zero
    impervious and zero vegetation is the best possible flood score, so a
    missing-data zero-fill would report an undescribed site as safe.

    `bare_pct` is the ANNUAL bare fraction from the same partition as the other
    three bands. `bare_season_pct` is a seasonal overlay and is reported only;
    adding it to an annual partition that already sums to one double-counts the
    cell and saturates the curve number.

    `dist_to_storm_drain_m` is distance to an ENGINEERED stormwater line or
    outfall only. Closer to engineered drainage means faster discharge, which
    lowers the score. It must never be populated from distance to a natural
    nala or river: proximity to a natural watercourse is a flood-plain
    exposure, and in Mula-Mutha that raises risk rather than lowering it.
    Callers that only have a waterbody buffer must leave this None and apply
    the separate flood-plain penalty instead.
    """
    required = {
        "impervious_pct": impervious_pct,
        "vegetation_pct": vegetation_pct,
        "water_pct": water_pct,
    }
    missing = [name for name, value in required.items()
               if _as_number(value) is None]
    if missing:
        return {
            "score": None,
            "status": "UNAVAILABLE",
            "confidence": "none",
            "reason": (
                "Flood requires explicit numeric impervious_pct, "
                "vegetation_pct and water_pct. Missing: "
                + ", ".join(missing)
                + ". A missing land-cover band is not zero cover, so the "
                  "factor is withheld rather than scored as a perfect site."
            ),
            "missing_inputs": missing,
            "curve_number": None,
            "baseline_curve_number": None,
            "runoff_mm": None,
            "baseline_runoff_mm": None,
            "excess_runoff_mm": None,
            "design_storm_mm": round(_pct(design_storm_mm), 1),
            "landcover_sum": None,
            "landcover_sum_within_bounds": None,
            "landcover_warning": None,
            "seasonal_bare_pct": _as_number(bare_season_pct),
            "seasonal_bare_used": False,
            "landcover_source": landcover_source or "supplied",
        }

    imperv = float(required["impervious_pct"])
    veg = float(required["vegetation_pct"])
    water = float(required["water_pct"])
    bare = _as_number(bare_pct)

    # Gate: the annual bands describe one cell. If they sum above 1, an
    # upstream caller has overlaid a seasonal value on a complete partition or
    # mixed units. Report it loudly; do not cap it silently.
    landcover_sum = (imperv + veg + water + (bare or 0.0)) / 100.0
    landcover_within_bounds = landcover_sum <= 1.0 + LANDCOVER_SUM_TOLERANCE
    landcover_warning: Optional[str] = None
    if not landcover_within_bounds:
        landcover_warning = (
            f"Land-cover fractions sum to {landcover_sum:.3f}, above 1.0. "
            f"Annual bands should partition the cell. The curve number is "
            f"renormalised explicitly, and the flood result must not be read "
            f"as a clean measurement until the overlap is resolved."
        )

    cn_site = area_weighted_cn(
        imperv, veg, water, cn_table, bare_pct=bare
    )

    # Baseline = the same cell with the terrestrial bands converted to
    # vegetation, but water held invariant. The old code used a single
    # vegetation CN for the whole cell, which silently "vegetated" open water
    # and overstated the excess runoff on water cells. (C12-adjacent; see
    # research/07_decisions/0003-flood-plain.md for fluvial handling.)
    veg_cn = float(cn_table.get("vegetation", 60.0))
    water_cn = float(cn_table.get("water", 100.0))
    try:
        imperv_f = clamp(_pct(imperv)) / 100.0
        veg_f = clamp(_pct(veg)) / 100.0
        water_f = clamp(_pct(water)) / 100.0
        bare_f = (clamp(_pct(bare)) / 100.0) if bare is not None else 0.0
        accounted = imperv_f + veg_f + water_f + bare_f
        if accounted > 1.0:
            imperv_f /= accounted
            veg_f /= accounted
            water_f /= accounted
            bare_f /= accounted
            accounted = 1.0
        terrestrial = imperv_f + veg_f + bare_f
        if accounted > 0:
            cn_baseline = terrestrial * veg_cn + water_f * water_cn
        else:
            cn_baseline = veg_cn
    except Exception:
        cn_baseline = veg_cn

    q_site = scs_cn_runoff_mm(cn_site, design_storm_mm)
    q_baseline = scs_cn_runoff_mm(cn_baseline, design_storm_mm)
    excess = max(0.0, q_site - q_baseline)

    p = max(1e-6, _pct(design_storm_mm))
    raw = (excess / p) * 100.0

    # Slope: steeper terrain sheds water faster, raising peak runoff.
    #
    # Missing slope is not the same as flat terrain. The cube did not carry a
    # slope band, and both the CLI and engine silently substituted 3 degrees,
    # which made a constant look like a measured site input. Use no multiplier
    # when the value is unavailable and say so in the factor output.
    slope_available = mean_slope_deg is not None
    if slope_available:
        slope = max(0.0, _pct(mean_slope_deg))
        slope_ratio = min(slope / max(1e-6, slope_full_effect_deg), 1.0)
        slope_multiplier = 1.0 + slope_ratio * (slope_max_multiplier - 1.0)
        slope_basis = "measured terrain slope"
    else:
        slope = 0.0
        slope_multiplier = 1.0
        slope_basis = "unavailable - no slope band; no slope multiplier applied"

    # Engineered drainage proximity: a discount, never a bonus.
    if dist_to_storm_drain_m is None:
        drain_multiplier = 1.0
        drain_basis = "unknown — no engineered drainage layer available"
    else:
        d = max(0.0, _pct(dist_to_storm_drain_m))
        ratio = min(d / max(1e-6, drain_full_benefit_m), 1.0)
        drain_multiplier = drain_min_multiplier + ratio * (1.0 - drain_min_multiplier)
        drain_basis = "distance to engineered stormwater outfall"

    score = clamp(raw * slope_multiplier * drain_multiplier)

    # SATURATION FLAG, added 2026-10-10 (reporting aid, NOT a scoring change).
    # At CN 100 the whole design storm runs off (runoff == storm) and 17/41
    # wards pin there -- arithmetically true, useless for planning, since it
    # cannot discriminate between saturated sites. The score is unchanged;
    # this flag lets the report face say "at or above the measurable ceiling"
    # instead of printing a false-precision storm depth. The choice of how to
    # PRESENT saturation (cap text, ceiling band, site-maximum rescale) is
    # the human's reporting decision; this only surfaces the condition.
    saturated = bool(q_site >= _pct(design_storm_mm) - 1e-9)

    attainable_max = 0.0
    try:
        attainable_max = max(0.0, (float(design_storm_mm) - q_baseline) / max(1e-6, float(design_storm_mm)) * 100.0)
    except Exception:
        attainable_max = 0.0

    return {
        "score": round(score, 1),
        "status": "OK",
        "reason": None,
        "confidence": "medium",
        "curve_number": round(cn_site, 1),
        "baseline_curve_number": round(cn_baseline, 1),
        "runoff_mm": round(q_site, 1),
        "baseline_runoff_mm": round(q_baseline, 1),
        "excess_runoff_mm": round(excess, 1),
        "design_storm_mm": round(_pct(design_storm_mm), 1),
        "landcover_sum": round(landcover_sum, 4),
        "landcover_sum_within_bounds": landcover_within_bounds,
        "landcover_warning": landcover_warning,
        "seasonal_bare_pct": (
            round(float(bare_season_pct), 3)
            if _as_number(bare_season_pct) is not None else None
        ),
        "seasonal_bare_used": False,
        "landcover_source": landcover_source or "supplied",
        "slope_deg": round(slope, 2) if slope_available else None,
        "slope_available": slope_available,
        "slope_basis": slope_basis,
        "slope_multiplier": round(slope_multiplier, 3),
        "drainage_multiplier": round(drain_multiplier, 3),
        "drainage_basis": drain_basis,
        "saturated_at_design_storm": saturated,
        "saturation_note": (
            "Site runoff equals the full design storm: at or above the "
            f"measurable ceiling, not exactly {_pct(design_storm_mm):.1f} mm."
            if saturated else None
        ),
        "fluvial_flood": "NOT_MODELLED",
        "flood_scale_policy": "physical_excess_runoff_fraction (Option B; see 07_decisions/0002-flood-scale.md)",
        "attainable_score_max": round(attainable_max, 1),
    }


# =========================================================================
# HEAT
# =========================================================================


def compute_heat(
    lst_mean_c: Optional[float],
    lst_reference_c: Optional[float],
    uhi_max_delta_c: float = 10.0,
) -> Dict[str, Any]:
    """Heat factor from urban-heat-island delta above a green reference.

    The reference is an empirical city-wide LST for the same pass and season,
    computed offline. It is NOT an air-temperature climatology mean: Landsat
    and Sentinel-2 thermal bands measure surface temperature, and comparing
    those to air temperature pins the factor at its maximum for any built-up
    site.

    If the reference is unavailable the factor degrades explicitly rather than
    silently assuming a value.
    """
    if lst_mean_c is None:
        return {
            "score": None,
            "status": "UNAVAILABLE",
            "reason": "No LST observation supplied for this polygon.",
            "lst_celsius": None,
            "lst_reference_c": lst_reference_c,
            "uhi_delta_c": None,
            "confidence": "none",
            "heat_scale": "night_percentile_span",
        }

    site = _pct(lst_mean_c)
    if lst_reference_c is None:
        return {
            "score": None,
            "status": "UNAVAILABLE",
            "reason": "City-wide LST reference not yet computed. Needs the epoch "
                      "cube (Earth Engine auth). Do not substitute an air "
                      "temperature here.",
            "lst_celsius": round(site, 2),
            "lst_reference_c": None,
            "uhi_delta_c": None,
            "confidence": "none",
            "heat_scale": "night_percentile_span",
        }

    ref = _pct(lst_reference_c)
    delta = site - ref
    span = max(0.1, _pct(uhi_max_delta_c, 10.0))
    score = clamp((delta / span) * 100.0)

    return {
        "score": round(score, 1),
        "status": "OK",
        "reason": None,
        "lst_celsius": round(site, 2),
        "lst_reference_c": round(ref, 2),
        "uhi_delta_c": round(delta, 2),
        "uhi_max_delta_c": round(span, 2),
        "confidence": "medium",
        "heat_scale": "percentile_of_cohort_span (not a physical magnitude; see 07_decisions/0004-heat-elevation.md)",
        "confidence_note": "Surface temperature, not air temperature. Single-pass "
                          "composite; a seasonal multi-pass mean is stronger.",
    }


# =========================================================================
# GREEN
# =========================================================================


def compute_green(
    sat_veg_pct: Optional[float],
    canopy_cover_pct: Optional[float],
    canopy_weight: float = 0.70,
    ground_vegetation_weight: float = 0.30,
    tolerance_pct: float = 15.0,
) -> Dict[str, Any]:
    """Green factor via ecological stratification rather than averaging.

    A satellite vegetation percentage already contains tree canopy. Averaging
    it with a census-derived canopy cover double-counts the same trees. So:

        ground_vegetation = max(0, sat_veg_pct - canopy_cover_pct)
        effective_green     = canopy * w_canopy + ground * w_ground
        score               = 100 - effective_green

    The two-source disagreement is surfaced as a confidence signal rather than
    hidden, because the census is 2019 and the imagery is later.

    Missing data is excluded, never scored. `_pct()` coerces None to 0.0, which
    would report an unmeasured site as having zero vegetation and therefore a
    PERFECT green score of 100.0 with `confidence: high`. That is the worst
    possible failure for a factor that is supposed to punish green loss, so a
    site with no satellite band or no census canopy returns None.

    Resolution caveat, which is NOT a bug: `sat_veg_pct` is the ~1 km epoch-cube
    cell's vegetation fraction while `canopy_cover_pct` is measured over the site
    polygon, so a small plot inside a sparse cell can legitimately have canopy
    above the cell's vegetation (ward 2: 50.4% canopy on 8,000 m2 inside a cell
    reading 7.6%). The subtraction therefore mixes two spatial scales. It is
    still the right direction of adjustment — ground vegetation cannot be
    negative — but it is not a strict identity, and `resolution_mismatch_pts`
    records how far apart the two scales are.
    """
    sat_raw = _pct(sat_veg_pct, float("nan"))
    canopy_raw = _pct(canopy_cover_pct, float("nan"))

    # Unit and range validation. A percentage cannot exceed 100, and a negative
    # one is meaningless. Both indicate the upstream source used fractions where
    # percent was expected (or the reverse). This is checked BEFORE any clamping
    # so the fault is reported rather than absorbed -- clamping 680 to 100 would
    # report a units bug as total vegetation, which for a green-LOSS factor is
    # the worst possible misreading.
    faults: List[Tuple[str, float]] = []
    for label, value in (("satellite vegetation", sat_raw),
                         ("census canopy cover", canopy_raw)):
        if value != value:
            continue
        if value > IMPLAUSIBLE_PCT_ABOVE or value < IMPLAUSIBLE_PCT_BELOW:
            faults.append((label, value))
    if faults:
        detail = ", ".join(f"{label}={value:g}" for label, value in faults)
        return {
            "score": None,
            "status": "UNAVAILABLE",
            "reason": (
                f"Out-of-range percentage(s): {detail}. A percentage cannot "
                f"exceed {IMPLAUSIBLE_PCT_ABOVE:g}. This almost certainly means "
                f"the source reported a fraction rather than a percent, or the "
                f"reverse. Green cannot be scored on an unreadable unit."
            ),
            "sat_veg_pct": (None if sat_raw != sat_raw else round(sat_raw, 1)),
            "canopy_cover_pct": (None if canopy_raw != canopy_raw
                                 else round(canopy_raw, 1)),
            "out_of_range_inputs": [
                {"input": label, "value": value} for label, value in faults
            ],
            "confidence": "none",
            "confidence_note": "Unit fault in the vegetation or canopy input.",
        }

    if sat_raw != sat_raw or canopy_raw != canopy_raw:
        missing = []
        if sat_raw != sat_raw:
            missing.append("satellite vegetation")
        if canopy_raw != canopy_raw:
            missing.append("census canopy cover")
        return {
            "score": None,
            "status": "UNAVAILABLE",
            "reason": (
                "Missing required input(s) for the green factor: "
                + ", ".join(missing)
                + ". Green cover cannot be scored without inventing a value."
            ),
            "sat_veg_pct": None if sat_raw != sat_raw else round(sat_raw, 1),
            "canopy_cover_pct": (None if canopy_raw != canopy_raw
                                 else round(canopy_raw, 1)),
            "ground_vegetation_pct": None,
            "effective_green_pct": None,
            "canopy_weight": canopy_weight,
            "ground_vegetation_weight": ground_vegetation_weight,
            "source_divergence_pts": None,
            "resolution_mismatch_pts": None,
            "confidence": "none",
            "confidence_note": "Not scored: a required input was unavailable.",
        }

    sat = clamp(sat_raw)
    canopy = clamp(canopy_raw)
    ground = max(0.0, sat - canopy)

    effective = clamp(canopy * canopy_weight + ground * ground_vegetation_weight)
    score = clamp(100.0 - effective)

    divergence = abs(canopy - sat)
    if divergence > tolerance_pct:
        confidence = "low"
        note = (
            f"Census canopy {canopy:.1f}% vs satellite vegetation {sat:.1f}% "
            f"differ by {divergence:.1f} pts (tolerance {tolerance_pct:.0f}). "
            f"Trees are 2019 census and the pass is later; treat green cover "
            f"with wide uncertainty."
        )
    else:
        confidence = "high"
        note = f"Census and satellite agree within {divergence:.1f} pts."

    return {
        "score": round(score, 1),
        "sat_veg_pct": round(sat, 1),
        "canopy_cover_pct": round(canopy, 1),
        "ground_vegetation_pct": round(ground, 1),
        "effective_green_pct": round(effective, 1),
        "canopy_weight": canopy_weight,
        "ground_vegetation_weight": ground_vegetation_weight,
        "source_divergence_pts": round(divergence, 1),
        "resolution_mismatch_pts": round(max(0.0, canopy - sat), 1),
        "confidence": confidence,
        "confidence_note": note,
    }


# =========================================================================
# CARBON
# =========================================================================


# Share of bill-of-quantities mass, by weight, that may carry no emission factor
# before the carbon factor withholds its score entirely.
#
# Below this, the score is reported with `confidence: low` and
# `unknown_mass_pct`, on the basis that a small unquantified share cannot
# overturn the ranking. Above it, the figure is a floor rather than an estimate,
# so it is excluded from the composite rather than presented as a number.
# 10% is chosen because that is roughly where an unquantified material can
# plausibly shift the intensity across a band boundary.
UNKNOWN_MASS_EXCLUDE_PCT = 10.0

_NAME_NOISE = re.compile(r"[^a-z0-9]+")


def _normalise_name(raw: str) -> str:
    """Collapse a material name to a comparable key.

    Lowercases, replaces every run of non-alphanumeric characters with a single
    space, and trims. This is what makes "TMT-500", "TMT 500", "Steel - TMT" and
    "CEMENT OPC" comparable against the alias table and the canonical keys.

    Deliberately conservative: it normalises form, never meaning. Two different
    materials are never merged by this function, because a false merge would
    silently apply the wrong emission factor -- far worse than an unknown
    material that gets reported loudly.
    """
    return _NAME_NOISE.sub(" ", (raw or "").lower()).strip()


def _resolve_material(
    name: str, materials_table: Dict[str, Any]
) -> Tuple[str, Dict[str, Any]]:
    """Resolve a free-text material name to a canonical table entry.

    Resolution runs in three stages, because a bill of quantities from any
    external system will not match a hand-written alias table exactly:

      1. exact match on the lowered, trimmed name;
      2. exact match on the name with all non-alphanumerics collapsed to
         spaces ("Cement (OPC)", "TMT-500", "Steel - TMT");
      3. exact match on the alias table again after that normalisation, which
         covers "OPC cement", "flyash brick", "M sand" and similar word-order
         and spacing variants.

    Only after all three fail is a material reported unknown. Unknown is still
    a loud failure -- see compute_carbon -- never a silent default factor.
    """
    materials = materials_table.get("materials", {}) or {}
    raw = (name or "").strip()
    if not raw:
        return "unknown", {"ef": None, "category": "unknown",
                           "substitutions": [], "_unknown": True}

    aliases = materials_table.get("aliases", {}) or {}
    lowered = raw.lower()

    # Stage 1: direct.
    if lowered in aliases:
        canonical = aliases[lowered]
        entry = materials.get(canonical)
        if entry is not None:
            return canonical, entry

    canonical = raw
    entry = materials.get(canonical)
    if entry is not None:
        return canonical, entry

    # Stage 2: collapse punctuation and whitespace.
    normalised = _normalise_name(raw)
    if normalised in aliases:
        candidate = aliases[normalised]
        entry = materials.get(candidate)
        if entry is not None:
            return candidate, entry

    # Stage 3: try the canonical table keys through the same normalisation, so
    # "CEMENT OPC" and "Portland Cement" still land on cement_opc when an alias
    # happens to exist for them.
    for key, entry in materials.items():
        if _normalise_name(key) == normalised:
            return key, entry

    return canonical or "unknown", {
        "ef": None,
        "category": "unknown",
        "substitutions": [],
        "_unknown": True,
    }


def _scale_ceiling(band_table: List[Dict[str, Any]]) -> Optional[float]:
    """Top of the configured carbon intensity scale, in kgCO2e/m2.

    This is the last band's `max` when every band declares one, which is the
    point beyond which the score saturates at 100. The final band normally
    carries `max: null` to mean "open ended", so the ceiling is the largest
    *declared* maximum, i.e. the top of the last bounded band.

    Returns None only when the table declares no finite ceiling at all, in
    which case the caller treats the scale as unbounded and scores 100.
    """
    ceilings = [b.get("max") for b in (band_table or []) if b.get("max") is not None]
    if not ceilings:
        return None
    return float(max(float(c) for c in ceilings))


def compute_carbon(
    materials: List[Dict[str, Any]],
    built_up_area_m2: float,
    materials_table: Dict[str, Any],
    bands: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Embodied carbon factor from a bill of quantities.

    Cement and steel dominate an Indian RC building; steel is usually the largest
    single contributor. Collect them separately from concrete — the
    `concrete_ready_mix` factor embeds an assumed cement content, so specifying
    both charges that binder twice. That rule is now detected and reported as
    `double_count_warning` rather than only being described here.

    Three inputs are treated as missing data rather than as outcomes:
      * an empty or wholly unresolvable BOQ scores None, not 0.0, because 0.0
        would report the best possible carbon result for an undescribed project;
      * a zero built-up area scores None rather than dividing by a 1e-6 guard and
        saturating at 100;
      * a material with no emission factor is excluded from the total and named in
        `unknown_materials`, never silently defaulted.
    """
    area = _pct(built_up_area_m2, 0.0)
    if area <= 0.0:
        return {
            "score": None,
            "status": "UNAVAILABLE",
            "reason": "Built-up area is zero, so embodied carbon per m2 is undefined.",
            "total_kgco2e": 0.0,
            "intensity_kgco2e_m2": None,
            "band": None,
            "built_up_area_m2": 0.0,
            "line_items": [],
            "dominant_material": None,
            "dominant_share_pct": 0.0,
            "unknown_materials": [],
            "double_count_warning": None,
            "ecological_advisories": [],
            "confidence": "none",
            "confidence_note": "Carbon intensity is per m2 of built-up area.",
        }
    area = max(1e-6, area)
    total = 0.0
    line_items: List[Dict[str, Any]] = []
    unknown: List[str] = []
    advisories: List[Dict[str, Any]] = []

    binder_canonicals = {"cement_opc", "cement_ppc", "cement_psc", "cement_ggbs",
                         "calcined_clay_cement_lc3"}
    ready_mix_canonicals = {"concrete_ready_mix", "concrete_low_clinker_30ggbs",
                            "concrete_low_clinker_50ggbs"}

    seen_binder: Optional[str] = None
    seen_ready_mix: Optional[str] = None
    double_count: Optional[str] = None

    for item in materials or []:
        raw_name = item.get("name") or item.get("material") or ""
        qty = max(0.0, _pct(item.get("quantityKg", item.get("quantity_kg", 0.0))))
        canonical, entry = _resolve_material(str(raw_name), materials_table)

        if canonical in binder_canonicals and seen_binder is None:
            seen_binder = canonical
        if canonical in ready_mix_canonicals and seen_ready_mix is None:
            seen_ready_mix = canonical

        # Ready-mix already embeds an assumed binder content, so counting a
        # separate cement line against it charges that binder twice. The rule was
        # documented but never enforced; raise it rather than silently
        # double-counting, and let the caller decide which line to drop.
        if seen_binder and seen_ready_mix and double_count is None:
            double_count = (
                f"{seen_binder} and {seen_ready_mix} both specified; "
                f"{seen_ready_mix} embeds binder, so the binder is counted twice"
            )

        if entry.get("_unknown"):
            unknown.append(str(raw_name))
            line_items.append(
                {
                    "name": str(raw_name),
                    "quantity_kg": round(qty, 1),
                    "ef": None,
                    "kgco2e": None,
                    "status": "UNKNOWN_MATERIAL",
                }
            )
            continue

        ef = entry.get("ef")
        if ef is None:
            unknown.append(str(raw_name))
            line_items.append(
                {
                    "name": canonical,
                    "quantity_kg": round(qty, 1),
                    "ef": None,
                    "kgco2e": None,
                    "status": "MISSING_EF",
                }
            )
            continue

        contribution = qty * float(ef)
        total += contribution

        advisory = entry.get("ecological_advisory")
        if advisory:
            advisories.append(
                {
                    "material": canonical,
                    "advisory": advisory,
                    "severity": entry.get("advisory_severity", "info"),
                    "text": entry.get("advisory_text", ""),
                    "alternatives": entry.get("substitutions", []),
                }
            )

        line_items.append(
            {
                "name": canonical,
                "quantity_kg": round(qty, 1),
                "ef": float(ef),
                "kgco2e": round(contribution, 1),
                "category": entry.get("category"),
                "status": "OK",
            }
        )

    intensity = total / area

    band_table = bands or []
    band_label = "Unknown"

    # An empty or unresolvable BOQ is missing data, not a clean outcome. Scoring
    # it 0.0 would report the best possible carbon result for a project nobody
    # has described, so it is excluded from the composite instead.
    if not line_items or (not any(li.get("kgco2e") for li in line_items)
                          and unknown):
        return {
            "score": None,
            "status": "UNAVAILABLE",
            "reason": "No resolvable materials in the bill of quantities. Every "
                      "line was unknown, so embodied carbon cannot be computed "
                      "without inventing an emission factor.",
            "total_kgco2e": round(total, 1),
            "intensity_kgco2e_m2": round(intensity, 1),
            "band": band_label if band_table else None,
            "built_up_area_m2": round(area, 1),
            "line_items": line_items,
            "dominant_material": None,
            "dominant_share_pct": 0.0,
            "unknown_materials": unknown,
            "double_count_warning": double_count,
            "ecological_advisories": advisories,
            "confidence": "none",
            "confidence_note": "No emission factor could be applied to any line.",
        }

    # A bill of quantities that names materials but carries no usable quantity
    # is missing data, not a zero-carbon project. `_pct(item.get("quantityKg",
    # ...))` defaults a missing key to 0.0, and the per-line qty clamp floors a
    # negative at 0.0, so a BOQ of nothing-but-zeroes resolves every line,
    # totals 0.0 kgCO2e, and passes the "no material has any emissions" guard --
    # scoring 0.0 / Low, the best possible result, for a project nobody has
    # actually described. It is caught here instead, before any scoring.
    declared_mass = sum(
        max(0.0, _pct(item.get("quantityKg", item.get("quantity_kg", 0.0))))
        for item in (materials or [])
        if item is not None
    )
    if line_items and declared_mass <= 0.0:
        return {
            "score": None,
            "status": "UNAVAILABLE",
            "reason": (
                "The bill of quantities names materials but carries no positive "
                "quantity for any of them. Zero, negative and missing quantities "
                "are not a zero-carbon project; they are an unfinished bill of "
                "quantities. Quantities are required in kg."
            ),
            "total_kgco2e": 0.0,
            "intensity_kgco2e_m2": None,
            "band": None,
            "built_up_area_m2": round(area, 1),
            "line_items": line_items,
            "dominant_material": None,
            "dominant_share_pct": 0.0,
            "unknown_materials": unknown,
            "unknown_mass_pct": 0.0,
            "double_count_warning": double_count,
            "ecological_advisories": advisories,
            "confidence": "none",
            "confidence_note": "No positive material quantity was supplied.",
        }

    # Unknown mass is a hole in the carbon figure, so its share of the BOQ is
    # measured. A large unquantified fraction means the score is a floor, not
    # an estimate, and the factor must not present itself as authoritative.
    known_mass = sum(
        float(li.get("quantity_kg") or 0.0)
        for li in line_items
        if li.get("kgco2e") is not None
    )
    unknown_mass = sum(
        float(li.get("quantity_kg") or 0.0)
        for li in line_items
        if li.get("kgco2e") is None
    )
    total_mass = known_mass + unknown_mass
    unknown_mass_pct = (100.0 * unknown_mass / total_mass) if total_mass > 0 else 0.0

    # A factor computed while ignoring a material share of the BOQ is not a
    # defensible number. Above UNKNOWN_MASS_EXCLUDE_PCT the score is withheld
    # and the factor drops out of the composite with its weight redistributed,
    # because a silently understated carbon figure is worse than no figure.
    if unknown_mass_pct > UNKNOWN_MASS_EXCLUDE_PCT:
        return {
            "score": None,
            "status": "UNAVAILABLE",
            "reason": (
                f"{unknown_mass_pct:.1f}% of the bill of quantities by mass "
                f"({unknown_mass:,.0f} kg) is material with no emission factor, "
                f"above the {UNKNOWN_MASS_EXCLUDE_PCT:.0f}% limit. Carbon cannot "
                f"be scored without either a factor for those materials or a "
                f"confirmed quantity."
            ),
            "total_kgco2e": round(total, 1),
            "intensity_kgco2e_m2": round(intensity, 1),
            "band": band_label if band_table else None,
            "built_up_area_m2": round(area, 1),
            "line_items": line_items,
            "dominant_material": None,
            "dominant_share_pct": 0.0,
            "double_count_warning": double_count,
            "unknown_materials": unknown,
            "unknown_mass_pct": round(unknown_mass_pct, 1),
            "ecological_advisories": advisories,
            "confidence": "none",
            "confidence_note": (
                f"Excluded: {unknown_mass_pct:.1f}% of BOQ mass has no emission "
                f"factor."
            ),
        }

    band_table = bands or []
    band_label = "Unknown"
    band_max: Optional[float] = None
    for band in band_table:
        band_max = band.get("max")
        if band_max is None or intensity <= float(band_max):
            band_label = str(band.get("label", "Unknown"))
            break

    # Map band intensity to a 0-100 subscore, monotonic and capped.
    #
    # The DENOMINATOR must be the top of the configured scale, never the ceiling
    # of whichever band this intensity happens to fall into. Using the matched
    # band's ceiling made the score non-monotonic: at a fixed 1 m2,
    #   intensity 296 -> 74.0   (inside the Low band, ceiling 400)
    #   intensity 518 -> 64.8   (inside the Moderate band, ceiling 800)
    # so roughly doubling the emissions LOWERED the carbon score by 9 points,
    # and every band boundary produced a downward step.
    scale_max = _scale_ceiling(band_table)
    if scale_max is None:
        score = 100.0
    else:
        score = clamp((intensity / scale_max) * 100.0)

    dominant = max(
        (li for li in line_items if li.get("kgco2e")),
        key=lambda li: li["kgco2e"],
        default=None,
    )

    return {
        "score": round(score, 1),
        "total_kgco2e": round(total, 1),
        "intensity_kgco2e_m2": round(intensity, 1),
        "band": band_label,
        "built_up_area_m2": round(area, 1),
        "line_items": line_items,
        "dominant_material": dominant["name"] if dominant else None,
        "dominant_share_pct": (
            round(100.0 * dominant["kgco2e"] / total, 1) if dominant and total > 0 else 0.0
        ),
        "double_count_warning": double_count,
        "unknown_materials": unknown,
        "unknown_mass_pct": round(unknown_mass_pct, 1),
        "ecological_advisories": advisories,
        "confidence": "low" if unknown else "medium",
        "confidence_note": (
            f"{unknown_mass_pct:.1f}% of BOQ mass has no emission factor and is "
            f"excluded from this total, so the intensity is understated by up "
            f"to that share. Resolve these before issuing a report."
            if unknown
            else "A1-A3 cradle-to-gate. Excludes transport and site waste."
        ),
    }


# =========================================================================
# COMPOSITE
# =========================================================================


def _risk_band(impact: float) -> str:
    if impact < 30.0:
        return "Low"
    if impact < 60.0:
        return "Moderate"
    return "High"


def _decision(
    impact: Optional[float],
    blocking: List[Dict[str, Any]],
    *,
    factor_scores: Optional[Dict[str, Optional[float]]] = None,
    carbon_band: Optional[str] = None,
    complete: bool = True,
    policy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Turn a composite and its factor scores into a recommendation.

    The composite is an arithmetic mean. A single catastrophic factor can be
    diluted by three clean ones, so the verdict is also gated per factor:
    any factor at or above its review threshold, a carbon band configured as
    review-only, or a partial result forces REVIEW regardless of the weighted
    number. The weights are deliberately unchanged -- see
    research/07_decisions/0001-core-safety-policy.md.
    """
    policy = policy or {}
    default_threshold = float(policy.get("factor_review_threshold", 80.0))
    thresholds = policy.get("factor_review_thresholds", {}) or {}
    review_bands = set(policy.get("carbon_review_bands", ["Very High"]))
    partial_reviews = bool(policy.get("partial_results_review", True))
    approve_below = float(
        (policy.get("composite") or {}).get("approve_below", 30.0)
    )
    conditions_below = float(
        (policy.get("composite") or {}).get("conditions_below", 60.0)
    )

    triggers: List[str] = []
    if blocking:
        triggers.append("blocking condition must be resolved before approval")
    if not complete and partial_reviews:
        triggers.append(
            "result is partial: at least one factor is unavailable"
        )

    for name, value in (factor_scores or {}).items():
        if value is None:
            continue
        threshold = float(thresholds.get(name, default_threshold))
        if float(value) >= threshold:
            triggers.append(
                f"{name} factor {float(value):.1f} is at or above its "
                f"{threshold:.1f} review threshold"
            )

    if carbon_band in review_bands:
        triggers.append(
            f"carbon band '{carbon_band}' requires review by policy"
        )

    if triggers:
        return {
            "recommendation": Recommendation(
                "REVIEW",
                "Review required before approval.",
            ),
            "headline": (
                "Review required: " + "; ".join(triggers) + "."
            ),
            "decision_triggers": triggers,
        }

    if impact is None or not math.isfinite(float(impact)):
        return {
            "recommendation": Recommendation(
                "REVIEW",
                "Insufficient data for a verdict.",
            ),
            "headline": "Review required: no impact score could be computed.",
            "decision_triggers": ["no computable impact score"],
        }

    impact = float(impact)
    if impact < approve_below:
        return {
            "recommendation": Recommendation(
                "APPROVE",
                "Climate impact low. No material conditions required.",
            ),
            "headline": "Climate impact low. No material conditions required.",
            "decision_triggers": [],
        }
    if impact < conditions_below:
        return {
            "recommendation": Recommendation(
                "APPROVE_WITH_CONDITIONS",
                "Approvable if the listed conditions are incorporated.",
            ),
            "headline": "Approvable if the listed conditions are incorporated.",
            "decision_triggers": [],
        }
    return {
        "recommendation": Recommendation(
            "REJECT_OR_REDESIGN",
            "Redesign required. Impact too high to condition.",
        ),
        "headline": "Redesign required. Impact too high to condition.",
        "decision_triggers": [],
    }


def _canopy_for_green(
    ledger: Optional[Dict[str, Any]],
) -> Tuple[Optional[float], Optional[str], str]:
    """Resolve the canopy value the green factor is allowed to use.

    Returns ``(canopy_pct, unavailable_reason, basis)``.

    The green factor is a loss factor: a proposed project that fells trees must
    score worse than one that keeps them. `CanopyLedger.process_site` therefore
    returns both the existing canopy (`canopy_cover_pct`) and the canopy left
    after its tree decisions (`canopy_cover_pct_proposed`). Prefer the proposed
    value.

    A missing ledger, an explicitly unreliable census, or an explicitly null
    canopy is NOT the same as a measured zero. Those cases return None so the
    factor is withheld rather than reported as a perfect green score. A real
    zero is a numeric 0.0 and is scored.
    """
    if not ledger:
        return (
            None,
            "Tree census ledger unavailable. Green cover cannot be scored "
            "without inventing a canopy value.",
            "unavailable",
        )

    if ledger.get("census_reliable_for_this_site") is False:
        return (
            None,
            "Tree census coverage is incomplete for this site. Zero loaded "
            "trees does not mean treeless, so green cover is withheld.",
            "unavailable",
        )

    for key, basis in (
        ("canopy_cover_pct_proposed", "proposed"),
        ("canopy_cover_pct", "existing"),
    ):
        if key not in ledger:
            continue
        raw = ledger.get(key)
        if raw is None:
            return (
                None,
                f"Tree census ledger has no usable {key}. Green cover is "
                f"withheld rather than treating it as zero.",
                "unavailable",
            )
        try:
            return float(raw), None, basis
        except (TypeError, ValueError):
            return (
                None,
                f"Tree census ledger has a non-numeric {key}={raw!r}. Green "
                f"cover is withheld.",
                "unavailable",
            )

    return (
        None,
        "Tree census ledger has no canopy field. Green cover is withheld "
        "rather than treating the site as treeless.",
        "unavailable",
    )


def score_project(
    site: Dict[str, Any],
    indicators: Dict[str, Any],
    region_config: Dict[str, Any],
    materials_table: Dict[str, Any],
    ledger: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compute the full four-factor score for one project site.

    site:        builtUpAreaSqm, plotAreaSqm, materials[]
    indicators:  impervious_pct, vegetation_pct, water_pct, lst_mean_c,
                 mean_slope_deg, dist_to_storm_drain_m. The three land-cover
                 percentages are mandatory for flood; absent/None is
                 UNAVAILABLE, never zero.
    region_config / materials_table: the JSON config objects
    ledger:       output of CanopyLedger.process_site; its proposed canopy is
                  used so tree removal affects the green factor

    Any factor whose required input is missing returns score=None and is
    EXCLUDED from the composite with its weight redistributed. A score built
    from fewer than four factors is reported as partial, and a partial result
    can never be APPROVE or REJECT_OR_REDESIGN -- it is always REVIEW.
    """
    hyd = region_config.get("hydrology", {}) or {}
    therm = region_config.get("thermal", {}) or {}
    green_cfg = region_config.get("green", {}) or {}
    weights: Dict[str, float] = region_config.get("weights", {}) or {}
    decision_policy: Dict[str, Any] = region_config.get("decision_policy", {}) or {}

    imperv = indicators.get("impervious_pct")
    veg = indicators.get("vegetation_pct")
    water = indicators.get("water_pct")

    flood = compute_flood(
        impervious_pct=imperv,
        vegetation_pct=veg,
        water_pct=water,
        design_storm_mm=hyd.get("design_storm_mm", 150.0),
        cn_table=hyd.get("cn_table", {"vegetation": 60.0, "impervious": 98.0,
                                      "water": 100.0, "bare": 86.0}),
        # ANNUAL bare fraction, the fourth band of the same partition as built/
        # vegetation/water. `bare_season_pct` is a seasonal overlay and is
        # reported separately; it must never be added as a fourth band to a
        # partition that already sums to one.
        bare_pct=indicators.get("bare_pct"),
        bare_season_pct=indicators.get("bare_season_pct"),
        landcover_source=indicators.get("landcover_source"),
        # No invented fallback. If the cube has no slope band, flood still
        # scores without a slope multiplier and reports that basis explicitly.
        mean_slope_deg=indicators.get("mean_slope_deg"),
        dist_to_storm_drain_m=indicators.get("dist_to_storm_drain_m"),
        slope_full_effect_deg=hyd.get("slope_full_effect_deg", 15.0),
        slope_max_multiplier=hyd.get("slope_max_multiplier", 1.25),
        drain_full_benefit_m=hyd.get("storm_drain_full_benefit_m", 500.0),
        drain_min_multiplier=hyd.get("storm_drain_min_multiplier", 0.80),
    )

    # Night LST is preferred when available: day-Landsat within-cell contrast
    # over PMC is +0.11 C with the sign flipping by season (no signal), while
    # night MODIS vs the rural-ring reference is correctly signed at r=+0.55
    # (moderate, medium confidence). Day remains the fallback so cubes built
    # before the night branch still score exactly as before.
    _night_mean = indicators.get("lst_night_mean_c")
    _night_ref = therm.get("night_reference_c")
    if _night_ref is None:
        _night_ref = indicators.get("lst_night_reference_c")
    if _night_mean is not None and _night_ref is not None:
        heat = compute_heat(
            lst_mean_c=_night_mean,
            lst_reference_c=_night_ref,
            uhi_max_delta_c=therm.get("night_uhi_max_delta_c", 5.0),
        )
    else:
        # Day fallback is LEGACY_DAY and is NOT scored. Night LST is the only
        # heat input; a missing night observation makes the factor UNAVAILABLE
        # rather than silently substituting a daytime surface temperature.
        heat = {
            "score": None,
            "status": "UNAVAILABLE",
            "reason": (
                "Night LST unavailable. Daytime surface contrast is LEGACY_DAY "
                "and is excluded from the composite; no day fallback is used."
            ),
            "lst_celsius": (
                round(float(indicators.get("lst_mean_c")), 2)
                if indicators.get("lst_mean_c") is not None else None
            ),
            "lst_reference_c": indicators.get("lst_reference_c"),
            "uhi_delta_c": None,
            "uhi_max_delta_c": therm.get("uhi_max_delta_c"),
            "confidence": "none",
            "heat_scale": "night_percentile_span",
            "legacy_day_lst_c": indicators.get("lst_mean_c"),
        }

    # Elevation is reported on the heat factor, not corrected: no elevation-banded
    # rural reference exists in this checkout, so adjusting the score would be
    # an unsourced constant. (See 07_decisions/0004-heat-elevation.md.)
    if isinstance(heat, dict):
        heat.setdefault("elevation_m", indicators.get("elevation_m"))
        heat.setdefault(
            "elevation_confounding",
            "Night LST is confounded by elevation (partial r(built|elevation) "
            "~0.41 on the 864-cell cube). Reported, not corrected: no "
            "elevation-banded rural reference is available.",
        )

    canopy, canopy_unavailable_reason, canopy_basis = _canopy_for_green(ledger)
    green = compute_green(
        sat_veg_pct=veg,
        canopy_cover_pct=canopy,
        canopy_weight=green_cfg.get("canopy_weight", 0.70),
        ground_vegetation_weight=green_cfg.get("ground_vegetation_weight", 0.30),
        tolerance_pct=green_cfg.get("sat_census_tolerance_pct", 15.0),
    )
    green["canopy_basis"] = canopy_basis
    if ledger is not None:
        green["census_reliable_for_this_site"] = ledger.get(
            "census_reliable_for_this_site"
        )
    if canopy_unavailable_reason:
        # compute_green already returns score=None for a missing canopy; this
        # replaces its generic "missing census canopy" message with the actual
        # reason (no ledger / incomplete census / null field) and keeps the
        # factor out of the composite.
        green["score"] = None
        green["status"] = "UNAVAILABLE"
        green["reason"] = canopy_unavailable_reason
        green["canopy_unavailable_reason"] = canopy_unavailable_reason
        green["confidence"] = "none"
        green["confidence_note"] = "Not scored: canopy data is unavailable."

    carbon = compute_carbon(
        materials=site.get("materials", []) or [],
        built_up_area_m2=site.get("builtUpAreaSqm", 1.0),
        materials_table=materials_table,
        bands=(region_config.get("carbon", {}) or {}).get("bands"),
    )

    factors = {"flood": flood, "heat": heat, "green": green, "carbon": carbon}
    scores = {k: (v.get("score") if v.get("score") is not None else None) for k, v in factors.items()}

    available = {k: v for k, v in scores.items() if v is not None}
    missing = [k for k, v in scores.items() if v is None]

    if available:
        total_weight = sum(float(weights.get(k, 0.0)) for k in available) or 1.0
        impact = sum(
            float(v) * (float(weights.get(k, 0.0)) / total_weight) for k, v in available.items()
        )
    else:
        impact = float("nan")

    complete = not missing

    # Blocking advisories: a material sourcing issue stops approval regardless
    # of how good the numeric score is.
    blocking = [
        adv
        for adv in carbon.get("ecological_advisories", [])
        if adv.get("severity") == "blocking"
    ]

    contributions: Dict[str, float] = {}
    if complete:
        for k, v in available.items():
            contributions[k] = round(float(v) * float(weights.get(k, 0.0)), 1)

    climate_score = (100.0 - impact) if impact == impact else None

    result: Dict[str, Any] = {
        "climate_score": round(climate_score, 1) if climate_score is not None else None,
        "impact_score": round(impact, 1) if impact == impact else None,
        "risk_band": _risk_band(impact) if impact == impact else None,
        "complete": complete,
        "missing_factors": missing,
        "sub_scores": {k: (round(v, 1) if v is not None else None) for k, v in scores.items()},
        "weight_contributions": contributions,
        "factors": factors,
        "canopy": ledger,
    }

    if missing:
        result["partial_notice"] = (
            f"Score computed from {len(available)} of {len(scores)} factors. "
            f"Missing: {', '.join(missing)}. Weights were renormalised over the "
            f"available factors, so this is NOT comparable to a complete score."
        )
    if carbon.get("unknown_materials"):
        result["blocking_issues"] = [
            {
                "type": "unknown_material",
                "detail": f"No emission factor for: "
                          f"{', '.join(carbon['unknown_materials'])}. Carbon "
                          f"intensity is understated until these are resolved.",
            }
        ]
    elif blocking:
        result["blocking_issues"] = [
            {
                "type": "material_sourcing",
                "detail": adv["text"],
                "material": adv["material"],
                "alternatives": adv["alternatives"],
            }
            for adv in blocking
        ]
    else:
        result["blocking_issues"] = []

    # The verdict is always issued, including when no factor could be scored.
    # A partial result is REVIEW by policy; it must never be APPROVE or
    # REJECT_OR_REDESIGN on a renormalised subset of the evidence.
    result.update(
        _decision(
            impact if impact == impact else None,
            result["blocking_issues"],
            factor_scores=scores,
            carbon_band=carbon.get("band"),
            complete=complete,
            policy=decision_policy,
        )
    )

    return result
