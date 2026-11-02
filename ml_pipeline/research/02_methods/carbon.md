# Carbon method (Pune)

**Code:** `ml_pipeline/core/scoring.py::compute_carbon`, `_resolve_material`, `_scale_ceiling`
**Config:** `ml_pipeline/config/materials.json`, `ml_pipeline/config/regions/pune.json` → `carbon`
**Inputs:** bill of quantities (materials + quantities in kg), built-up area (m²)

## Method

- Embodied carbon intensity = total kgCO₂e / built-up area m², from a bill of quantities using India-specific emission factors (IFC India 2017 for cement/brick/steel/concrete; CEEW for primary aluminium 20.88 kgCO₂e/kg; remaining ICE-global where no India listing exists).
- Banding by intensity: Low ≤ 400, Moderate ≤ 800, High ≤ 1200, Very High above (from config `carbon.bands`).
- Score = `intensity / scale_ceiling * 100`, where `scale_ceiling` = largest declared band max (1200), capped at 100. Scale denominator is the top of the scale, not the matched band's ceiling (non-monotonic bug fixed).
- Unknown materials (> 10% of BOQ mass by weight) withhold the score entirely. Empty/unresolvable BOQ or zero built-up area → score `None`.
- Double counting (separate cement line + ready-mix) is detected and reported as `double_count_warning`, not silently charged twice.
- IGBC Near Net Zero anchor = 700 kgCO₂e/m² (named Indian benchmark). Observed Indian high-rise mean = 454 (range 373–530).

## House bands caveat

400/800/1200 breakpoints are house bands, not a named standard and must not be attributed to GRIHA (`bands_status: UNSOURCED_BANDS`). See `05_sources/carbon/README.md`.

## Rebuild / verify

- Materials table is committed at `ml_pipeline/config/materials.json`; provenance in its `provenance` field.
- Tests: `ml_pipeline/tests/test_scoring.py` (carbon cases).
