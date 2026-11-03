# Session 4 — Flood and heat physics

**Suggested model:** Beam Free  
**Dependencies:** Session 2 merged (and Session 3 for artifact context, but not for code)  
**Owns:** flood and heat sections of `ml_pipeline/core/scoring.py`, hydrology/thermal sections of `ml_pipeline/config/regions/pune.json`, `ml_pipeline/data/derive_design_storm.py`, `ml_pipeline/data/derive_uhi_span.py`, `ml_pipeline/data/build_cube.py`  
**Do not touch:** green/carbon sections, validation JSONs, `report/`, `frontend/`, `backend/`

Read `prompts/00_context.md` first.

## Mission

Fix the physical meaning of flood and heat. Do not silently change measured constants. Every change to a threshold, span, reference, or weight needs a decision note with evidence.

Only one session may edit `core/scoring.py`. Confirm Session 2 is merged before editing.

## Flood — C6 and C12

### C6 — the 0–100 scale is not real

Current flood score:

```text
(Q_site - Q_baseline) / P × 100
```

At 214 mm, CN 100 gives about 56.6. Flood cannot reach the `High` band (≥60). The 0.30 weight therefore does not mean what the report implies.

Required, choose one and document it:

- **Option A:** normalize the flood score to its attainable range, then recalibrate the weights and bands.
- **Option B:** keep the physical excess-runoff fraction but report the attainable range explicitly and stop calling it 0–100.

Do not silently multiply by a constant. Add a decision note explaining the choice and its effect on the composite.

### C12 — flood-plain exposure is not implemented

`scoring.py` mentions a separate flood-plain penalty, `geometry.py` returns `nearest_natural_water_m`, but no scoring function uses it.

Required:

- Add a flood-plain penalty, or
- Explicitly state that fluvial flood is not modelled and remove the expectation from docs/report.

A defensible implementation uses PMC/WRD blue/red flood lines, distance to the watercourse, and elevation. If those layers are unavailable, report the gap; do not invent a penalty.

### Other flood physics checks

- **Water CN baseline:** water CN 100 is used in both current and baseline states. If the baseline “vegetates the water,” that is wrong. Hold water invariant or compute CN over the terrestrial fraction. Add a regression test: water cells should not be penalised by the baseline transformation.
- **HSG B citywide:** currently assumed. Test sensitivity to HSG C/D. Do not claim B is measured. If a soil dataset is available, integrate it; otherwise report the assumption and the sensitivity band.
- **Design storm:** 214 mm is a single IMD node. Test bilinear interpolation of the four bounding nodes if the data are available. Compare Gumbel and GEV/LP3. Report model uncertainty, not only the parametric bootstrap.
- **AMC and λ:** report AMC II / λ = 0.20 as assumptions. Test AMC III for the monsoon scenario.
- **Absolute vs excess runoff:** report absolute runoff and baseline runoff, not only the score. A reviewer needs to see whether the site actually floods.

## Heat — C7

### Current problem

```text
(LST_night - 17.96) / 5.0 × 100
```

- The 5.0 °C span is the p95−p05 of the same 864-cell sample, so the score is a percentile rescaling.
- 99/864 cells score exactly 0. No cell reaches 100; max is about 99.4.
- Night LST is confounded by elevation: raw `r(built) = 0.553`, `r(elevation) = -0.475`; partial `r(built | elevation) = 0.407`.
- Terra 10:30 pm and Aqua 1:30 am are averaged into one “night” value.
- A daytime fallback still exists.

Required:

- Elevation-match the rural reference (for example ±50 m) or regress out elevation before scoring.
- Use one overpass (prefer Aqua 1:30 am) or model the overpass hour separately.
- Use absolute UHI thresholds with uncertainty, or report the percentile rank separately from the physical delta. Do not present a percentile rank as a physical magnitude.
- Make the day fallback `UNAVAILABLE`, or label it `LEGACY_DAY` and exclude it from the composite. The project position is that daytime surface contrast has no usable signal.
- Do not change `17.96 °C` or `5.0 °C` without a decision note and evidence. If you add an elevation-adjusted reference, write down how it was derived.
- Add a separate unscored afternoon shade/albedo/air-temperature note if useful. Do not turn it into a heat score without data.

## Tests

Add tests for:

- Water cells: current and baseline water held invariant; no artificial penalty.
- Flood scale: attainable range is documented and the composite uses the chosen normalization.
- Flood-plain penalty: if implemented, a riverside site scores worse than an identical inland site; if not implemented, the output says `fluvial_flood: NOT_MODELLED`.
- Heat elevation: an elevation-adjusted score reduces the partial correlation with elevation on the cube.
- Heat day fallback: missing night LST → `UNAVAILABLE`, not day.
- Heat percentile vs absolute: the output distinguishes them.

Run:

```bash
.venv/bin/python -m pytest ml_pipeline/tests -q
.venv/bin/python ml_pipeline/tests/test_scoring.py
```

## Decision notes

Write in `ml_pipeline/research/07_decisions/`:

- `0002-flood-scale.md` — normalization vs attainable range, weight implications.
- `0003-flood-plain.md` — implemented or explicitly not modelled.
- `0004-heat-elevation.md` — reference matching method and evidence.
- `0005-heat-overpass.md` — Terra/Aqua choice and why.

## Do not

- Do not touch green or carbon.
- Do not change 214 mm, 17.96 °C, or 5.0 °C without evidence.
- Do not claim a physical UHI magnitude from a percentile span.
- Do not reintroduce daytime heat as a scored factor.
- Do not regenerate validation artifacts; tell Session 3 what changed.
- Do not edit the report or PDF.

## Acceptance

- Flood range is honest and documented.
- Water cells are not penalised by the baseline.
- Flood-plain handling is either implemented or explicitly marked not modelled.
- Heat is night-only; day fallback is unavailable/legacy.
- Elevation confounding is reduced or explicitly reported.
- Tests cover the decisions.
- Decision notes exist.

## Handoff

Report:

- The chosen flood-scale policy and its effect on composite scores.
- The flood-plain decision.
- The heat reference/overpass method and the elevation statistics before/after.
- Any constant changed, with evidence.
- What Session 5 and Session 3 need to know.
