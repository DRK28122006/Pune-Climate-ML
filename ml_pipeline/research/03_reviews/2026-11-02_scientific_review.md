# Dishadharti / Pune-Climate-ML — Scientific and Engineering Review

**Status:** final research draft for discussion  
**Scope:** repository at `/home/mesh/Pune-Climate-ML`, README, technical report PDF, committed artefacts, and the separate web application  
**Method:** read-only code and artefact review, pure-function re-runs, arithmetic checks, and targeted verification of external legal/carbon claims. No repository files were changed. GEE assets were not rebuilt and the 1.2 GB census was not re-downloaded.

**Confidence labels used below:** `[M]` measured in the repository or reproduced from it; `[D]` derived by calculation; `[A]` assumption/house judgment; `[U]` unverified or needing an external check.

---

## Preamble: there are two scoring systems in this repository

This is the first thing a skeptical reviewer will discover, and it changes how every other claim should be read.

1. **The documented scientific pipeline** — `ml_pipeline/` and `engine/`. It uses `epoch_cube.json`, the tree index, SCS-CN flood, night MODIS LST, the canopy ledger, and the India-specific carbon factors. This is what the README and `Dishadharti_ML_Report.pdf` describe.
2. **The web application** — `frontend/`, `backend/`, `api/`. It uses a **different, legacy JavaScript scorer** and, in the UI path, **synthetic `mlOutput` generated from sliders**, not the Python pipeline.

The web app is not a thin front end over the reviewed scorer. `backend/src/domain/scoring.js` still contains the retired placeholders:

- design storm **150 mm** (the README says this was retired);
- heat baseline **28 °C air temperature** and normalisation **15 °C** (the project says this is physically invalid);
- `greenScore = 100 − vegetation_pct`, with no canopy ledger or 70/30 stratification;
- older carbon factors: concrete 0.15, steel 1.85, brick 0.24, glass 1.2, aluminium 12.5 kgCO₂e/kg;
- a step-function carbon score of 20/50/80/100, so a zero-carbon project still scores 20.

`frontend/src/services/optimization.ts` builds `mlOutput` from user-entered percentages:

- vegetation = 100 − (built-up + paved), water = 0;
- LST = `31 + 0.085·builtUpPct + 0.05·pavedPct − 0.14·canopyPct`;
- fixed coordinates `18.5204, 73.8567` for every plan;
- `slope_deg_mean: 3`, `elevation_m_mean: 560`, `ndvi_mean: 0.3`, `ndbi_mean: 0.5`, `ndwi_mean: 0.1`;
- `isDemo: false` and `modelVersion: "backend-1.0"`.

The backend accepts that payload as `source: "request"` (`backend/src/services/mlService.js`), and `assessDataQuality` treats `"request"` as measured (`backend/src/services/assessmentService.js`). The backend also defaults to `ML_MODE = "fixture"` (`backend/src/config.js`) and can generate seeded pseudo-landcover/LST from a hash (`fixtureOutput`). Its “optimisation” is hardcoded: +12% vegetation, a cooler LST, and materials × 0.85, labelled `source: "verified-scenario"` (`backend/src/services/recommendationService.js`).

The Assessment page does say “Results are illustrative and are not validated predictions,” which is honest. But `isDemo: false`, `modelVersion: "backend-1.0"`, and `source: "verified-scenario"` contradict that caveat. **If the demo is the web app, the scientific claims in the report do not describe what the reviewer sees.** If the Python pipeline is the submission, the legacy web scorer should be removed or clearly quarantined. This is not a cosmetic issue; it is the difference between a measured tool and a slider-driven mock.

The rest of this review focuses on the Python pipeline, because that is the system the scientific claims describe. The web app is flagged again in Sections 2 and 8.

---

## 1. Understanding check

The Python pipeline is a deterministic screening engine, not a predictive model.

- **Phase 1** bakes an 864-cell ~1 km grid (`epoch_cube.json`) and a spatially indexed 2019 tree ledger (`tree_index.sqlite`). The cube carries 2024 Dynamic World land cover, day and night LST, and elevation.
- **Phase 2** takes a site polygon, a built-up area, a plot area, and a bill of quantities. It looks up **the single cube cell containing the polygon centroid**, walks the census trees whose points fall inside the polygon, and computes four sub-scores.
- **Flood** is SCS-CN excess runoff for the cell’s existing land cover against a CN 60 vegetated baseline at a 214 mm, 100-year, one-day storm, optionally adjusted for slope and distance to an engineered drain.
- **Heat** is the cell’s 2024 night MODIS LST minus a rural reference of 17.96 °C, divided by a 5.0 °C p95−p05 span.
- **Green** is 100 minus a blend of site census canopy and cell satellite vegetation, using the proposed canopy after tree decisions.
- **Carbon** is A1–A3 material mass × India-specific factors, divided by built-up area, scored against a 1,200 kgCO₂e/m² ceiling.
- The composite is a weighted mean (0.30 flood, 0.30 heat, 0.20 green, 0.20 carbon). Missing factors are renormalised and labelled partial.
- `impact_score` is high = worse. `climate_score` is `100 − impact`, so high = better. The README’s “score 0–100 (high = worse)” is therefore true of the sub-scores and `impact_score`, not of the primary `climate_score`.

Corrections to the mental model:

1. **Flood and heat score the existing 1 km cell, not the proposed design.** The built-up area and plot area do not enter the flood calculation. A proposal that paves 15% and one that paves 85% of the same plot get the same flood and heat score.
2. **Green is not purely per-site.** It mixes a plot-scale census canopy with a 1 km satellite vegetation fraction. The scales differ by two orders of magnitude.
3. **Carbon is material-only A1–A3**, not whole-life embodied carbon, and it is per built-up m², not per plot.
4. **A partial score can still produce a verdict.** Renormalisation can yield `APPROVE` from two factors, despite the “not comparable” notice.
5. **214 mm is a 100-year, one-day storm**, not PMC’s drainage design standard. The return period is a policy choice.
6. **Night LST is surface temperature**, not air temperature. It is a proxy for stored heat, not a heat-stress measurement.
7. **Tree compensation is an allometric estimate**, not a legal determination. The Tree Officer determines age under the Act.

---

## 2. Critical errors

### C0. The web app uses a different scorer and fabricated inputs

**Severity:** critical if the web app is part of the submission or demo.

**What is wrong.** The UI path does not call the Python scorer. It sends slider-derived `mlOutput` to an Express API that runs the legacy JavaScript scorer. The legacy constants are exactly the ones the Python project retired: 150 mm storm, 28 °C air-temperature heat baseline, 15 °C normalisation, `green = 100 − vegetation`, and old carbon factors. The frontend supplies fixed coordinates, a fake 3° slope, a fixed 560 m elevation, constant NDVI/NDBI/NDWI, and a linear LST formula. `isDemo` is set to `false`.

**Why it matters.** A reviewer who opens the web app sees a different model from the one in the report. The app can label fabricated inputs as `measured-or-supplied` because `source: "request"` is treated as measured. Its recommendations are hardcoded (+12% vegetation, cooler LST, materials ×0.85) and labelled `verified-scenario`. This directly contradicts the project’s “no fake data, mocks, or AI magic” claim.

**Evidence.** `frontend/src/services/optimization.ts` (lines 14–79); `backend/src/domain/scoring.js` (SETTINGS); `backend/src/services/mlService.js` (`fixtureOutput`, `getMlOutput`); `backend/src/services/assessmentService.js` (`measuredMl`); `backend/src/services/recommendationService.js`; `backend/src/config.js` (`mlMode: process.env.ML_MODE || "fixture"`). The UI caveat is in `frontend/src/pages/Assessment.tsx`.

**Fix.** Either (a) wire the web app to the Python pipeline and delete the legacy scorer, or (b) mark the web app as an explicit prototype, set `isDemo: true`, remove `verified-scenario`, and never present its scores as measured. Do not ship both and describe only the better one.

---

### C1. Missing land-cover data is zero-filled; flood becomes 0 and the tool can APPROVE

**Severity:** critical.

**What is wrong.** `score_project` defaults `impervious_pct`, `vegetation_pct`, and `water_pct` to `0.0` when the keys are absent (`ml_pipeline/core/scoring.py:1000–1002`). `area_weighted_cn` then sees an accounted fraction of zero and returns the vegetation CN (60), so flood excess is zero. The composite is computed and `_decision` can return `APPROVE`.

**Why it matters.** It violates the project’s central claim that missing data is never zero-filled and that a missing factor cannot look perfect. A site with no satellite cube, or a cell with missing fields, can receive `climate_score = 100`, `impact_score = 0`, `risk_band = Low`, and `APPROVE`.

**Evidence.** Reproduced directly:

```
score_project(site, {}, region_config, materials, ledger=None)
→ flood 0.0, curve_number 60.0
→ climate_score 100.0, impact_score 0.0, risk_band "Low"
→ complete False, missing_factors ["heat", "green"]
→ recommendation "APPROVE"
```

With a valid low-carbon BOQ, carbon is also scored and the result still approves. The CLI compounds this: when no cube exists, `--impervious` defaults to 70 and `--vegetation` to 24 (`ml_pipeline/cli.py:355–358`), so flood is computed from house defaults rather than withheld. `ml_pipeline/intake/validate.py:229` even says plot area “drives the flood score,” which is false.

**Fix.** Require explicit non-`None` land-cover inputs for flood; return `UNAVAILABLE` if any are missing. Make partial results `REVIEW` only, never `APPROVE` or `REJECT`. Remove the 70/24 fallbacks, or label them as a user-supplied scenario with a visible warning. Add regression tests for empty indicators, a missing cube, and a cell with null land-cover fields.

---

### C2. Seasonal bare soil is double-counted; 166 cells saturate at CN 100

**Severity:** critical.

**What is wrong.** The annual land-cover partition already sums to 1 (`built + vegetation + water + bare + flooded + snow`). `bare_season_pct` is an additional seasonal estimate, not a residual. `area_weighted_cn` adds it as a fourth band and weights by the supplied fractions, then clamps only `accounted` to 1.0 (`scoring.py:116–142`). It does not renormalise the fractions or subtract the seasonal bare from vegetation.

**Why it matters.** The curve number is inflated, and cells with enough built cover saturate at CN 100, where the flood score is pinned at its ceiling. This is not a small bias: 847/864 cells have `built + vegetation + water + bare_season > 1` (maximum 1.198); 166 cells reach CN ≥ 99.99 with seasonal bare, versus 0 with the annual bare fraction. The code comment says the excess is “reported rather than absorbed,” but no field reports it.

**Evidence.** `ml_pipeline/core/scoring.py:116–142`; the cube fields `bare_pct` and `bare_season_pct`; `docs/example_assessment.json` (CN 100 with built 99.56% and bare_season 3.21%). The same double count is used in `engine/score.py:46–47` and `ml_pipeline/cli.py:220–221`.

**Fix.** Use the annual `bare_pct` as the fourth band. If seasonal bare is preferred, subtract it from the vegetation/crops/shrub class or renormalise all four bands explicitly. Remove the silent `accounted = 1.0` clamp and add a build-time gate that fails if the land-cover fractions sum above 1. Report `landcover_sum` and `seasonal_bare_used` in every flood result.

---

### C3. The proposal design is mostly not modelled; built-up area is used only for carbon

**Severity:** critical.

**What is wrong.** Flood uses the cell’s existing land cover, heat uses the cell’s existing night LST, and green uses existing satellite vegetation plus census canopy. The proposed built-up area enters only the carbon denominator (`scoring.py:1082`). The tree ledger treats every census tree inside the **plot** as obstructed, because `process_site` is called without a building footprint (`ml_pipeline/cli.py:198`; `engine/score.py:88–89`). The report and `docs/make_report.py:145` nevertheless say the built-up area “drives flood (impervious fraction).”

**Why it matters.** The tool is a location/baseline screening tool, not a proposal-impact tool. Two radically different designs on the same plot receive the same flood, heat, and green scores. The report’s “what it will do to the city’s climate” is therefore overstated.

There is a second, separate error in the same variable: the code uses one `builtUpAreaSqm` for carbon intensity. A multi-storey building’s total floor area (GFA) can exceed the plot area, but `ml_pipeline/intake/validate.py` rejects `built_up > plot`. If the user enters the plinth to pass validation, carbon is divided by the plinth and overstated by the number of storeys; if the user enters GFA, validation rejects a legitimate building. The report’s Table 1 says built-up must not exceed plot, which conflates 2D footprint with 3D floor area.

**Evidence.** `score_project` flood call (`scoring.py:1004–1023`); carbon area (`1082`); `intake/validate.py:226–235`; `docs/make_report.py:144–145`; PDF Section 2 and Section 12; `process_site(records, plot_area_m2=...)` with no footprint.

**Fix.** Introduce three explicit inputs: `plot_area_m2`, `impervious_footprint_m2` (≤ plot), and `total_gfa_m2` (≥ footprint). Flood should use plot-scale imperviousness plus a catchment term; carbon should divide by GFA; green should use the proposed plot canopy and the unbuilt pervious area. If the proposal design cannot be supplied, relabel the product as “site baseline screening” and remove the proposal-impact claims. Add a test where two designs on the same plot produce different flood and green scores.

---

### C4. There is no per-factor veto; the worst single factor can still be APPROVE

**Severity:** critical.

**What is wrong.** `_decision` applies thresholds only to the weighted composite (`scoring.py:887–906`). A single catastrophic factor is diluted by the other three.

**Why it matters.** A site with heat 99 and all else 0 has impact 29.7 → `APPROVE`. Carbon 100 → impact 20 → `APPROVE`. Flood at its current ceiling (56.6) → impact 17 → `APPROVE`. Green 100 → impact 20 → `APPROVE`. The carbon band can say “Very High” while the overall verdict says “Low/Approve.” For municipal screening, that is unsafe.

**Evidence.** Reproduced with `_decision` and the weights; the report’s own carbon band and risk band use different objects. `scoring.py:887–906`, `1116–1120`.

**Fix.** Add per-factor review thresholds (e.g. any factor ≥ 80 → `REVIEW`; carbon band “Very High” → `REVIEW`), or use a max/power mean instead of an arithmetic mean. Make the policy explicit and test single-factor extremes. Do not let a high carbon band coexist with an unconditional approval.

---

### C5. Validation is circular, point-sampled, stale, and includes fabricated defaults

**Severity:** critical.

**What is wrong.** Four separate problems compound:

1. **Centroid-only ward lookup.** `indicators_from_cube` returns the single cell containing the polygon centroid (`ml_pipeline/cli.py:76–78`). `validate_wards.py` passes a whole ward ring but scores one centroid cell. A ward is not one cell.
2. **Ward canopy used as site canopy.** `ward_tree_profile` computes canopy / ward area (`geometry.py:612–622`), and `validate_wards.py:181–185` passes that ward-level density into a 4,000 m² plot ledger. A ward with 103.32% canopy density is clamped to 100 and treated as a site fraction.
3. **Day LST and stale spans.** `ward_validation.json` heat 27.0 is `0.539 / 2.0 × 100` — the day path and the retired 2.0 °C span. The current scorer uses night LST and 5.0 °C. `site_validation.json` heat 53.8 is `1.076 / 2.0 × 100`. The committed validation artefacts are not testing the current scorer.
4. **Fabricated defaults.** `validate_wards.py:174` uses `dist_to_storm_drain_m = 150.0`; `validate_sites.py:214` uses `or 200.0`; `docs/example_assessment.json` and `ml_pipeline/data/stress/*.json` contain `mean_slope_deg: 3.0` and `slope_multiplier: 1.05`, exactly the fake 3° slope the README says was retired.

The correlations are also not independent. Flood is a deterministic function of built/vegetation; green directly includes satellite vegetation. The ward run uses one identical proposal 41 times, not 41 independent designs. The site validation’s expected ordering fails: Hadapsar “hot-fringe” 57.1 (best), Koregaon Park “best” 38.1 (worst), Shivajinagar “worst” 50.0 (middle). Hadapsar has `canopy_pct: null`, zero trees, and still gets green 94.2 with `complete: true` — a direct contradiction of the missing-data policy.

**Why it matters.** The reported `r = +0.92 / −0.95 / −0.81` values are consistency checks, not validation. They cannot support claims about flood, heat, or green accuracy. The stale artefacts make the README’s ranges unreproducible: the README says flood 14.5–53.3, heat 0.8–99.0, green 62–100; the committed `ward_validation.json` gives flood 51.0–57.6, heat 11.0–64.8, green 97.6–99.8; the `stress/` run gives flood 30.6–67.3, heat 0–85.9, green 64.7–99.8. `factor_breakdown.py:103–105` also states the wrong sign convention: it says higher sub-scores should correlate positively with the final score, but the sub-scores are higher = worse and the final `score` is `climate_score` (higher = better).

**Evidence.** `ml_pipeline/data/ward_validation.json`; `site_validation.json`; `ml_pipeline/data/stress/*.json`; `docs/example_assessment.json`; `validate_wards.py`; `validate_sites.py`; `factor_breakdown.py`; `geometry.py:612–622`.

**Fix.** Area-weight or majority-overlap all cells intersecting the ward; use the site polygon for green; pass night LST and no drainage default; regenerate all validation artefacts with the current scorer; embed hashes and versions; add CI freshness checks; assert expected ordering; delete or clearly mark the stale artefacts.

---

### C6. Flood and green do not use the full 0–100 scale, so the weights and bands mislead

**Severity:** high.

**What is wrong.** Flood is `(Q_site − Q_baseline) / P × 100`. At 214 mm, CN 98 gives 53.8 and CN 100 gives 56.6. With the current cube (no slope), the flood sub-score cannot reach the “High” band (≥60). Green has a floor of 30: with 100% canopy and 100% satellite vegetation, `effective = 0.7 × 100 = 70`, so the score is 30. It can never fall below 30.

**Why it matters.** The declared “0–100” scale and the 0.30/0.30/0.20/0.20 weights assume all factors span the same range. They do not. Flood’s maximum contribution is about 17, not 30; green’s contribution ranges from about 6 to 20. Heat and carbon dominate the variance. The report’s “flood 0–100” and “green 0–100” are scale claims that the formulas do not support.

**Evidence.** `compute_flood` (`scoring.py:159–260`); `compute_green` (`327–460`); `_risk_band` (`879–885`); weights in `pune.json`. The max flood score at CN 100 is `(214 − 92.85) / 214 × 100 = 56.6`.

**Fix.** Normalise each factor to its attainable range, or use physically meaningful thresholds and report the attainable range. Recalibrate the weights on the normalised scale. Show the range in the report and test the extremes. Do not call the scale “0–100” without qualification.

---

### C7. Heat is a percentile rescaling, confounded by elevation, and still has a day fallback

**Severity:** high.

**What is wrong.** `compute_heat` is `(LST_night − 17.96) / 5.0 × 100` (`scoring.py:303–306`). The 5.0 °C span is the p95−p05 of the same 864-cell sample. That is a percentile rescaling, not an absolute UHI magnitude: it guarantees roughly 5% of cells at 0 and 5% at 100. 99/864 cells are exactly 0. The “0.8–99.0 spread” is therefore partly by construction.

Night LST is also strongly related to elevation: the cube’s slope is about −7.63 °C/km, and the elevation range (535–1031 m) predicts ~3.78 °C against a ~4.8 °C span. Raw `r(night LST, built) = 0.553`; partial `r` controlling elevation is 0.407. Raw `r(night LST, elevation) = −0.475`; partial controlling built is −0.263. The score is partly a topography map.

Finally, `score_project` still falls back to daytime LST when night data is missing (`scoring.py:1038–1053`), even though the project says daytime LST carries no signal and its own config marks the day span stale (2.0 vs recomputed 4.40). The fallback prioritises backward compatibility over validity.

**Why it matters.** The heat score is not a physical heat-risk metric. It conflates UHI with elevation and guarantees a fixed tail at 0. The day fallback can produce a number for a signal the project has retired. The Terra 10:30 pm and Aqua 1:30 am overpasses are also averaged into one “night” value, although the UHI magnitude and sign differ between evening and pre-dawn.

**Evidence.** `compute_heat`; `pune.json` `thermal` fields (`night_uhi_max_delta_c = 5.0`, `uhi_max_delta_c = 2.0`, `uhi_max_delta_status = DERIVED_FROM_EPOCH_CUBE` with a note saying STALE); cube elevation/night LST; `score_project` day fallback.

**Fix.** Use absolute UHI thresholds with uncertainty, or at least report the percentile rank separately from the physical delta. Match the rural reference by elevation (e.g. ±50 m) or regress out elevation. Use one overpass (Aqua) or model the overpass hour. Make the day fallback `UNAVAILABLE`, or label it legacy and exclude it from the composite. Recompute the validation with night data.

---

### C8. Green’s “70% canopy” label is mathematically misleading; scale mixing can make effective green exceed satellite vegetation

**Severity:** high.

**What is wrong.** The formula is:

```
ground = max(0, satellite_vegetation − canopy)
effective = 0.70 × canopy + 0.30 × ground
         = 0.30 × satellite_vegetation + 0.40 × canopy
```

The marginal weight on canopy is therefore 0.40, not 0.70. The label “canopy counts 70%” describes the component weights, not the effective marginal contribution. More importantly, when site census canopy exceeds the cell’s satellite vegetation, `ground` clips to zero and `effective` can exceed the satellite total. `ml_pipeline/data/stress/w02.json` shows satellite vegetation 7.6%, canopy 50.4%, effective green 35.3%, green score 64.7, and a 42.8-point resolution mismatch. The code reports the mismatch but still uses the number.

The ward harness makes this worse by feeding a ward-level canopy density above 100% into a site-scale fraction; `process_site` clamps it, but the result is not a site canopy.

**Why it matters.** The green score is not a strict measure of on-site green cover. A barren concrete plot inside a leafy 1 km cell can receive credit for the cell’s vegetation; a wooded plot inside a sparse cell can have its understorey erased. Tree loss is diluted: at satellite vegetation 30% and canopy 30%, felling all trees moves the score from about 79 to 91, only 12 points. The 70/30 label overstates the canopy sensitivity.

**Evidence.** `compute_green` (`scoring.py:427–430`); `stress/w02.json`; `geometry.py:612–622`; `process_site` clamp; `validate_wards.py` passes ward canopy.

**Fix.** State the algebra explicitly. Use independent ground-cover data at the site scale (10 m Dynamic World/Sentinel-2 COG clipped to the polygon) instead of subtracting a plot canopy from a 1 km vegetation fraction. Constrain plot ground vegetation by the unbuilt, non-canopy pervious area. Never feed a >100% density index into a fraction. Use the proposed canopy in every artefact, not the existing canopy.

---

### C9. Carbon’s unknown-mass threshold is the wrong metric; double counting is not enforced; units are ambiguous

**Severity:** high.

**What is wrong.**

1. **Threshold by mass, not carbon.** `UNKNOWN_MASS_EXCLUDE_PCT = 10` withholds the score only when >10% of BOQ mass is unrecognised. A small mass of a high-factor material can dominate carbon. Example: 95% cement (0.91) + 5% aluminium (20.88) by mass. Aluminium is 5% of mass but 1.044 / 1.9085 = 54.7% of carbon. The code would compute the score on the known cement and understate intensity by ~55%, while the explanatory note says “understated by up to that share” — the mass share.
2. **Double counting is warned, not fixed.** If both cement and ready-mix concrete are specified, the total includes both; `double_count_warning` is set, but no caller drops a line and the decision does not block it.
3. **A withheld score still reports an intensity and band.** The >10% branch returns `score: None` but still sets `intensity_kgco2e_m2` and `band` from the known-only total (`scoring.py:789–802`). The empty-BOQ branch reports intensity 0.0, which can be misread as zero-carbon.
4. **Units.** The intake requires `quantityKg` and performs no unit conversion (`intake/validate.py:250–274`). A real BOQ in m³ or m² for concrete/brick is silently treated as kg, understating carbon by orders of magnitude.

**Why it matters.** Carbon is the one factor that responds to the proposal; if its threshold and units are wrong, the only design-sensitive factor is compromised. The 10% mass test does not detect a missing whole material category (steel, finishes, MEP).

**Evidence.** `scoring.py:465–474`, `573–816`; `intake/validate.py:250–274`; `materials.json`; `docs/example_assessment.json`.

**Fix.** Threshold by carbon share or use a conservative upper-bound factor for unknowns. Enforce the double-count exclusion or make it a blocking issue. Set intensity and band to `None` whenever the score is unavailable. Require explicit units and a density conversion table, or accept only mass. Add the 5% aluminium test and a m³-concrete test.

---

### C10. Legal and policy labels are partly wrong or too strong

**Severity:** high.

**What is wrong.**

- The 90 cm girth `MUST_PRESERVE` rule is correctly labelled house policy in `canopy.py:8–20`, but the report label says “preserve (no felling permitted)” (`render.py:157`), which sounds statutory. It is not. The Act requires permission; it does not prohibit felling at 90 cm.
- The code/species config says the pre-2021 rule was a “flat 1:3 ratio.” The Act text says the old rule was **“twice the number of trees to be felled”**, not 1:3. The 2021 amendment replaced that with a number equal to the estimated age, at least six feet in height.
- The Act’s heritage-tree criterion is age-based (50 years or more), not 90 cm girth. The tool’s 90 cm rule is a proxy, not the statutory definition.
- The 2021 amendment’s referral triggers — heritage trees and large felling applications (>200 trees) to the State Tree Authority — are not modelled. If the tool issues a local verdict without flagging them, it can imply a local approval that is statutorily incomplete.
- The 6-foot minimum sapling height and the 7-year maintenance/geo-tagging requirements are not modelled.
- The claim that removing a dead tree needs no permit is unverified; it should be marked as a legal question, not an assertion.

**Why it matters.** A municipal officer may treat the output as legal clearance. The report’s “no felling permitted” and “1:3” statements are the kind of errors that undermine the whole tool in front of a legal reviewer.

**Evidence.** `ml_pipeline/core/canopy.py:8–20`, `227–366`; `ml_pipeline/config/species.json`; `ml_pipeline/report/render.py:157`; the Act text as published (LawGist/PRS); the 2021 amendment. The exact section numbers in the prior draft (Sections 2(1a), 6A, 8(3), 8(5C)) should be confirmed against the Gazette before publication.

**Fix.** Label every rule in the JSON and narrator as `LAW`, `HOUSE POLICY`, or `DERIVED ESTIMATE`. Correct 1:3 → 2× for the pre-2021 rule. Add heritage (≥50 years) and >200-tree referral flags. Add 6 ft, 7-year survival, and geo-tagging. Use a species-specific age range or the Tree Officer’s method. Remove “no felling permitted” and “no permit required for dead trees” until verified.

---

### C11. “Any region” is not supported by the current engine

**Severity:** high.

**What is wrong.** `engine/region.py` scaffolds a new region with a 150 mm provisional storm, Pune’s CN table, Pune’s 400/800/1200 carbon bands, the 0.7/0.3 green weights, and the 0.30/0.30/0.20/0.20 composite weights. `validate_config` checks structure and weight sums, not provenance or scientific validity (`engine/region.py:135–168`). The 23-test synthetic region is a 2×2 grid with three trees; it proves plumbing, not real-world reuse.

**Why it matters.** A new city can produce scores using Pune/house constants and a provisional storm. The report’s “the engine holds no city knowledge” is false: the defaults are city knowledge, even if they live in a scaffold.

**Evidence.** `engine/region.py`; `engine/tests/test_engine.py`; `score_project` default 150 mm (`scoring.py:1008`).

**Fix.** Require provenance and status for every constant; refuse to score if `design_storm_status`, `night_reference_c`, `cn_table_source`, or `bands` are `PROVISIONAL`, `UNSOURCED`, or `PENDING`. Provide a region contract/schema. Build a second real city end-to-end with an independent team before claiming reuse.

---

### C12. Floodplain exposure is described but not implemented

**Severity:** high.

**What is wrong.** `scoring.py:175–181` says natural watercourse proximity is flood-plain exposure and that callers should “apply the separate flood-plain penalty.” `geometry.py:412–445` returns `nearest_natural_water_m` and a note, but no scoring function uses it. `compute_flood` only uses `dist_to_storm_drain_m`. A riverside site is therefore scored on its cell’s land cover, not on flood-plain exposure.

**Why it matters.** The Mula riverside validation site has flood 50.8, not the highest; the tool does not penalise the actual fluvial risk. The report’s “natural nalas are never treated as drainage” is only half the rule; the other half — a flood-plain penalty — is missing.

**Evidence.** `scoring.py:175–181`; `geometry.py:412–445`; `validate_sites.py`; `site_validation.json` Mula rows.

**Fix.** Add a flood-plain penalty based on the PMC/WRD blue/red flood lines, distance to the watercourse, and elevation. Or explicitly state that fluvial flood is not modelled and remove the expectation. Validate against PMC waterlogging hotspots.

---

### C13. Stale artefacts, provenance gaps, and an off-by-one census total

**Severity:** high for credibility; low for the arithmetic.

**What is wrong.**

- `docs/example_assessment.json` contains `mean_slope_deg: 3.0`, `slope_multiplier: 1.05`, and `canopy_cover_pct_proposed: None`. The first two are the fake slope the README says was retired; the third means the example does not demonstrate proposed-canopy scoring.
- `site_validation.json` gives Hadapsar green 94.2 with zero trees and `canopy_pct: null`, and `complete: true`. That is impossible under the current missing-data policy.
- `pune.json` sets `uhi_max_delta_c: 2.0` with status `DERIVED_FROM_EPOCH_CUBE`, while its own note says the value is stale and the recomputed span is 4.40.
- `geometry.py` uses `CENSUS_TOTAL_CITY_TREES = 4,009,624`, but the published total is 4,009,623 (16 × 250,000 + 9,623). The “4,009,623 of 4,009,624 unique” line is an off-by-one, not a dropped tree. `docs/make_report.py` repeats it.
- The report says `pmc_wards_2025.kml` is a repo file, but no KML is committed. `reference_layers.py` expects `ml_pipeline/reference/pmc_wards_2025.kml`; `gedi_ward_check.py` expects a root-level file. Neither exists in a clean clone.
- The report’s Figure 5/6 carbon denominators may disagree (602 t over 2,000 m² vs over 3,000 m²). The prior draft alleges this; the figures need checking. If true, it is a report-level inconsistency, not just a code issue.

**Why it matters.** A reviewer cannot tell which numbers are current. The README’s ranges cannot be reproduced from the committed validation JSONs. The “every number was read off a real run” claim is not supported by stale artefacts.

**Evidence.** `docs/example_assessment.json`; `ml_pipeline/data/site_validation.json`; `ml_pipeline/data/ward_validation.json`; `ml_pipeline/data/stress/*.json`; `pune.json`; `geometry.py`; `docs/make_report.py`; PDF Section 9/10.

**Fix.** Embed `code_commit`, `config_sha256`, `cube_sha256`, `scorer_version`, `heat_mode`, and `design_storm_mm` in every artefact. Add a CI freshness test that re-runs the saved inputs and compares to 1e-6. Correct the census constant to 4,009,623. Regenerate or delete stale artefacts. Commit the KML/manifest or provide a checksummed download.

---

## 3. Weak assumptions

| Assumption | Affected factor | What happens | Replacement / test | Confidence |
|---|---|---|---|---|
| Uniform HSG B citywide | Flood | Pune’s black cotton Vertisols and shallow basaltic hills are likely C/D. But because the baseline CN also changes, the **excess-based score can fall** even as absolute runoff rises. The score is not monotonic in soil permeability. | HYSOGs250m (250 m), ICAR-NBSS&LUP, SoilGrids; report absolute runoff separately from excess. | High that B is wrong; medium on exact HSG. |
| Vegetation CN 60 for all vegetation | Flood | Understates runoff from grass/crops/shrub and from C/D soils. Use TR-55 class-specific CNs. | TR-55 Table 2-2; Dynamic World class-specific CNs. | High. |
| Water CN 100 in the current and baseline states | Flood | Treats rivers/lakes as worse than concrete and makes the baseline “vegetate the water.” Hold water invariant or compute CN over the terrestrial fraction. | TR-55 open-water handling; flood-line layer. | High. |
| One 214 mm storm for all PMC | Flood | The 18.50N/73.75E grid cell is western; eastern wards may have a different 100-year depth. The Gumbel CI is parametric and excludes GEV model uncertainty. | Bilinear interpolation of the four bounding IMD nodes; IMD station/IMDAA; GEV/LP3 comparison. | High. |
| AMC II, λ = 0.20 | Flood | Monsoon Vertisols can be AMC III; λ = 0.05–0.10 is used in some Indian SCS work. | Report a sensitivity band; use AMC III for the monsoon scenario. | Medium. |
| 1 km cell represents the plot | Flood, heat, green | Severe for flood and green; moderate for night heat (MODIS footprint is ~1 km). | 10 m Dynamic World/Sentinel-2 COG; ECOSTRESS 70 m for intra-cell heat; plot-scale flood. | High. |
| Night span 5.0 °C = p95−p05 | Heat | A percentile rescaling, not an absolute magnitude; ~5% at 0/100 by construction. | Absolute UHI thresholds or a rank plus a physical delta; elevation-matched reference. | High. |
| 70/30 canopy/ground weights | Green | House judgment; the algebra gives a 0.40 marginal canopy weight; grassland/hill sites are penalised. | Biome-specific weights; independent ground cover; state the algebra. | High. |
| 2019 census represents 2024–2026 | Green, legal | Five to seven years of growth and felling; geolocation errors; missing fringe wards. | Sentinel-2 ΔNDVI, Meta/WRI canopy height, field audit, newer census. | High. |
| Carbon bands 400/800/1200 | Carbon | House bands; 700 (IGBC near-net-zero) lands in “Moderate.” The 1,200 ceiling is not derived from an A1–A3 distribution. | Typology-specific A1–A3 percentiles; IGBC 700 as a marker or good boundary, not saturation. | High. |
| 10% unknown mass | Carbon | Wrong metric; 5% aluminium can be 55% of carbon. | Carbon-share threshold or upper-bound factor. | High. |
| 2 cm/yr girth-to-age | Legal | Species-blind; the 31–83 year range for a 100 cm girth is very wide. | Species-specific growth curves or Tree Officer method. | High. |
| Slope multiplier / drainage discount | Flood | House judgments; no slope in the cube; a 0 m drain gives a 20% discount, which may understate downstream risk. | Keep `None` when unmeasured; test sensitivity; document the policy. | Medium. |
| Composite weights 30/30/20/20 | All | House judgment; not calibrated; no per-factor veto. | Calibrate on decisions; use a max/power mean; add review thresholds. | High. |

---

## 4. Method review by factor

### 4.1 Flood — SCS Curve Number

**Appropriate?** Yes, for screening-level event runoff when a full SWMM/HEC-RAS model is unavailable. TR-55 is standard, and the project’s refusal to invent a slope is correct in principle.

**Constants.** Impervious 98 is standard. Vegetation 60 is the HSG B “woods” value; bare 86 is plausible for HSG B. Water 100 is the TR-55 open-water value but is misused in a baseline comparison. The 214 mm storm is a defensible 100-year, one-day depth, but the single western grid cell and the naive KS p-value weaken it.

**Main errors.** Seasonal-bare double count; missing-data zero fill; no plot imperviousness; water baseline penalty; no flood-plain penalty; single-node rainfall; HSG B; the flood score ceiling; the score’s non-monotonicity under HSG changes.

**Change first.** Missing-data handling, seasonal bare, water baseline, plot footprint, flood-plain layer, HSG. Then the design storm interpolation and the Gumbel/GEV model uncertainty.

**Refuse to change without data.** The CN table values, the AMC/λ choice, the slope multiplier, and the drainage discount should not be replaced by new guesses. Report them as assumptions and test sensitivity.

### 4.2 Heat — night surface temperature

**Appropriate?** Night LST is a reasonable proxy for stored urban heat, and retiring the day LST is scientifically sound: the day contrast is weak and can invert because dry rural soil out-heats shaded urban surfaces. But the current score is not a physical heat-risk metric.

**Main errors.** The p95−p05 denominator is circular; the score guarantees tails at 0/100; elevation confounds the signal; the rural halo may be biased by hills; Terra/Aqua overpasses are mixed; the day fallback still scores a retired signal; the report calls the 5.0 °C span a “measured” citywide magnitude when it is a sample-derived normalisation.

**Change first.** Elevation-match the reference or regress out elevation; use absolute thresholds/uncertainty; use one overpass; make the day fallback unavailable. Then add a separate, unscored afternoon shade/albedo metric using building heights and canopy.

**Refuse to change without data.** Do not switch to air temperature without a station/ERA5 comparison. Do not claim a physical UHI magnitude from a percentile span.

### 4.3 Green — trees kept vs trees lost

**Appropriate?** The ecological stratification idea is right: tree canopy and herbaceous ground cover are not interchangeable. But the current execution mixes spatial supports and does not measure the proposal’s marginal tree loss.

**Main errors.** The 70/30 algebra; effective green can exceed satellite vegetation; ward canopy >100% fed into a site fraction; tree loss is diluted; the 2019 census is old; crown overlap and missing canopy diameters; the score is a static background measure, not a retention ratio.

**Change first.** Use site-scale 10 m vegetation, proposed canopy in every artefact, and a two-part score: (a) canopy retained / pre-existing canopy, (b) post-development plot green cover. Constrain ground vegetation by the unbuilt pervious area.

**Refuse to change without data.** Do not replace 70/30 with a new universal weight. Do not treat census canopy as ground truth without a field/GEDI check.

### 4.4 Carbon — A1–A3 embodied carbon

**Appropriate?** Yes, for a material BOQ with cradle-to-gate factors. The project is honest that 400/800/1200 are house bands and that the score is withheld above the unknown threshold. That honesty should be preserved.

**Main errors.** Mass-based unknown threshold; double counting not enforced; intensity/band still reported when unavailable; no unit conversion; GFA/plinth confusion; missing material categories; the 1,200 ceiling and the IGBC 700 anchor are not on the same conceptual scale; the 2017 IFC factors are aging.

**Change first.** Carbon-share threshold, GFA denominator, unit conversion, double-count enforcement, and a band table derived from A1–A3 distributions. Add PPC/PSC factors.

**Refuse to change without data.** Do not replace the IFC/Karadumpa factors with unsourced values. Do not claim whole-life carbon from an A1–A3 BOQ.

### What is genuinely honest and should survive

- Retiring the 150 mm placeholder and deriving 214 mm from 124 years of IMD data, with a bootstrap interval and a GEV cross-check.
- Measuring the day/night LST problem and choosing night LST rather than forcing a signal.
- Refusing to zero-fill a missing tree census in the Python green path (the ward harness is the exception).
- Withholding carbon for an empty/wholly unknown BOQ and naming unknown materials.
- Labelling the 400/800/1200 bands as house bands, and the 90 cm rule as house policy in the code.
- Keeping the scorer deterministic and the LLM as narrator only.
- The cube’s provenance notes and the tests that enforce monotonicity and missing-factor exclusion (even though the flood path has a gap).

---

## 5. Validation and statistics

### What the reported correlations actually test

| Reported result | What it actually tests | Verdict |
|---|---|---|
| Flood vs built `r = +0.92`; vs vegetation `r = −0.95` | A deterministic monotonic transform of the same land-cover fractions. | Internal consistency, not validation. |
| Green vs vegetation `r = −0.81` | The green formula directly includes satellite vegetation. | Partially circular; not independent. |
| Night heat vs built `r = +0.55`; vs vegetation `r = −0.54` | An association between night LST and land cover. Less circular than flood/green, but still not a validation against air temperature or heat-stress observations; elevation and spatial autocorrelation confound it. | Suggestive, not proof. |
| Yale YCEO `+1.139` | A single city-mean sample from a different product/compositing. | A cross-check, not validation. |

### Statistical caveats

- **n = 41 wards, one proposal.** The 41 runs are not 41 independent designs. For the proposal-design question, the effective sample size is one.
- **Spatial autocorrelation.** The wards are contiguous; standard t-tests assume i.i.d. A Dutilleul/Clifford correction would reduce the effective n; the prior draft’s n_eff ≈ 15–22 is plausible but should be computed, not asserted.
- **Centroid cells.** Ward scores are point samples of one 1 km cell, not ward aggregates.
- **Compositional data.** Built, vegetation, and water sum to 1; built and vegetation are collinear. Testing both is not two independent hypotheses.
- **Multiple comparisons.** Four factors × several variables; report all correlations and a Holm/BH correction, not only the strong ones.
- **Range restriction.** Flood’s 53–57 range and green’s 97–99 range in the committed ward table restrict correlation and make r unstable.
- **Stale artefacts.** The committed `ward_validation.json` is six wards and uses day LST/2.0; the report’s 41-ward ranges come from a different run; `stress/` is another. They cannot be pooled.
- **Sign convention.** `factor_breakdown.py:103–105` says a factor should correlate positively with `score`, but `score` is `climate_score` (higher = better) while sub-scores are higher = worse. The interpretation is backwards.

### Independent tests worth running

1. **Flood:** overlay PMC waterlogging/chronic-flood hotspots and the 2019 Ambil Odha / 2024 inundation polygons on the 864 cell scores; report AUROC and a Mann–Whitney test. Target AUROC > 0.70.
2. **Heat:** compare the 2024 MODIS night LST grid with ECOSTRESS 70 m night LST and IMD/ERA5-Land air temperature at station locations. Report Spearman ρ, bias, and Moran’s I. Do not use one city-mean YCEO point as validation.
3. **Green:** compare census canopy with GEDI RH95 and a stratified field/crown audit. Report Lin’s concordance and plot-level RMSE. The current `gedi_ward_rh95.csv` has only means and footprint counts; it does not contain the census comparison, so “no ward-level contradiction” is not demonstrated.
4. **Carbon:** evaluate 10 real Pune RERA BOQs against `materials.json`, the IFC India DB, and the Akshatha et al. range. Report MAPE and a database sensitivity band. The current evidence is a hand-multiplied demo BOQ, not an external validation.
5. **Decision stability:** propagate the storm CI (191–234 mm), HSG C/D, the span uncertainty, and the carbon factor CV; flag `BORDERLINE_VERDICT` when the interval crosses a decision threshold.

### Reporting uncertainty

A municipal officer needs a range and a flip risk, not a decimal score. Report, for example:

> Flood 42 (storm CI 38–45; HSG C/D sensitivity 24–43; absolute runoff 171 mm vs baseline 93 mm).  
> Heat 61 (night LST 21.4 °C; reference 17.96; span 5.0; percentile rank 88; elevation-adjusted rank 72).  
> Green 78 (canopy retained 64%; plot ground cover 18%; 2019 census ±7 years).  
> Carbon 58 (871 kgCO₂e/m²; factor CV ±14%; two unknown lines, 4% mass, 12% carbon).

Do not report one decimal when the input uncertainty is tens of percent.

---

## 6. Data-source review

| Dataset in the pipeline | Verdict | Main limitation | Better/newer source | Access / link | Confidence |
|---|---|---|---|---|---|
| PMC Tree Census 2019 | Right primary source for stem locations, species, girth, canopy. | 2019 vintage; geolocation errors reported in 2026; pre-expansion coverage; missing canopy diameters. | Sentinel-2 ΔNDVI 2019→2024, Meta/WRI 1 m canopy height, field audit, newer PMC census. | https://data.opencity.in/dataset/pune-tree-census-2019 | High. |
| PMC ward boundaries 2025 | Geometrically complete if the KML is valid. | KML is not committed; attribute schema may lack names/notification; holes/slivers need validation. | PMC/State Election Commission notified boundary + metadata. | PMC GIS / Election Department (catalog-level) | Medium. |
| IMD 0.25° daily rainfall 1901–2024 | Right authoritative centennial series. | Single western node; 24-hr grid smooths cloudbursts; Gumbel fit p-value naive. | Four-node interpolation; IMD Shivajinagar/Lohegaon station IDF; IMDAA/CHIRPS. | https://www.imdpune.gov.in/ | High. |
| Dynamic World V1 (10 m) | Excellent annual land-cover probabilities. | Aggregated to 1 km; loses plot detail; annual modal class hides transient bare. | Keep the 1 km summary and export a 10 m COG for plot clipping; ESA WorldCover. | https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1 | High. |
| MODIS MOD11A1/MYD11A1 (1 km night LST) | Right sensor scale for citywide night heat. | 1 km footprint; mixed Terra/Aqua overpasses; clear-sky annual mean; elevation confound. | Aqua-only or overpass-separated; ECOSTRESS 70 m for intra-cell; VIIRS night. | https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD11A1 | High. |
| ECOSTRESS L2T LSTE V2 (70 m) | Useful validation/downscaling, not an annual wall-to-wall product. | Sparse clear-night sampling (the repo notes ~21 nights); not a complete annual cube. | Use as an intra-cell IQR/validation layer, not the primary score. | https://developers.google.com/earth-engine/datasets/catalog/NASA_ECOSTRESS_L2_LSTE_060 | High. |
| Landsat 8/9 C2 L2 | Good 30 m optical / 100 m thermal day data. | Day LST retired; cloud gaps; not night. | Keep for land-cover validation; do not use for the heat score. | https://developers.google.com/earth-engine/datasets/catalog/LANDSAT_LC09_C02_T1_L2 | High. |
| GEDI L2A RH95 | Useful sparse canopy-height check. | Sparse footprints; not wall-to-wall; not a census replacement. | Meta/WRI 1 m canopy height for wall-to-wall; GEDI for validation. | https://developers.google.com/earth-engine/datasets/catalog/LARSE_GEDI_L4A_AGB_002 (catalog-level) | High. |
| Yale YCEO UHI | Useful independent city-mean cross-check. | Different product/compositing; one point is not validation. | Pixel-level comparison and station air temperature. | https://yceo.yale.edu/ | Medium. |
| IFC India Construction Materials DB (2017) | Right A1–A3 starting point. | 2017 vintage; coarse cement/steel categories. | Karadumpa & Pancharathi 2024 PPC/PSC; CEEW; EPiC; IGBC. | https://edgebuildings.com/wp-content/uploads/2022/04/IFC-India-Construction-Materials-Database-Methodology-Report.pdf | High. |
| IGBC Net Zero Carbon 700 kgCO₂e/m² | Useful anchor. | The public page does not state the module boundary; one threshold is not a band table. | IGBC technical manual; typology-specific A1–A3 distribution. | https://igbc.in/igbc-net-zero-carbon-rating | High for the number; medium for the boundary. |
| Soil / HSG (currently none) | Missing. Uniform B is unscientific for Pune. | Distorts CN and the baseline. | HYSOGs250m, ICAR-NBSS&LUP, SoilGrids. | https://soilgrids.org/ ; https://www.nbsslup.in/ | High. |
| DEM / slope / TWI (currently none) | Missing. The cube has 1 km elevation only. | No plot slope, no flow accumulation, no depression storage. | Copernicus GLO-30/FABDEM; 30 m slope/TWI. | https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_DEM_GLO30 | High. |
| PMC/WRD flood lines (currently none) | Missing. | No fluvial flood-plain penalty. | PMC DP blue/red flood lines; WRD. | PMC DP Cell / wrd.maharashtra.gov.in | High. |
| Building footprints / GFA (currently none) | Missing. | Cannot separate plinth from GFA or model the proposal. | Google Open Buildings, PMC building permissions, RERA drawings. | https://sites.research.google/open-buildings/ | High. |
| Air temperature / heat stress (currently none) | Missing. | Night LST is not air temperature or heat stress. | IMD stations, ERA5-Land, LCZ classification. | https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_HOURLY | High. |

---

## 7. Policy and legal review

### The Act and the 2021 amendment

The Maharashtra (Urban Areas) Protection and Preservation of Trees Act, 1975, as amended in 2021, supports the core age-equivalent compensation rule. The published amendment text says the applicant must plant a number of trees equal to the **estimated age of the tree being felled**, and the saplings must be at least **six feet** high. For transplantation, the equivalent rule uses the age of the tree being transplanted. The earlier rule was **twice the number of trees to be felled**, not a “flat 1:3” ratio. The code/species config’s “1:3” is therefore wrong.

The Act also provides for a **seven-year** maintenance/survival period, geo-tagging, and a heritage-tree category based on age (**50 years or more**), not girth. Applications involving heritage trees or large felling numbers are subject to State Tree Authority referral. The exact section numbers and the effect of later amendments (including the 2023 amendment) should be confirmed against the Gazette before they are printed in a report.

### The 90 cm rule

The 90 cm girth `MUST_PRESERVE` rule is **house policy**, not statutory law. The code says so in `canopy.py:8–20`, which is good. The report label “preserve (no felling permitted)” is misleading: the Act requires permission; it does not create a 90 cm prohibition. The statutory heritage criterion is age-based, so a 65 cm slow-growing native tree can be legally older than a 90 cm fast-growing exotic. The 90 cm threshold is a silvicultural proxy, not a legal definition.

### What the output should say

| Rule in the tool | True classification | Required label |
|---|---|---|
| Permission before felling any tree | Law (subject to the Act’s definitions) | `LAW: Section 8(1)` — verify the 10 cm/3 m threshold, which may be census practice rather than the Act. |
| Compensation equal to estimated age; 6 ft; 7-year care; geo-tag | Law | `LAW: Section 8(5)/8(5C)` — verify the exact sub-sections. |
| Heritage tree ≥ 50 years; State referral | Law | `LAW: heritage-tree referral` — verify sections 2(1a), 6A, 8(3). |
| >200 trees felled; State referral; anti-subdivision | Law | `LAW: large-felling referral` — verify the 2023 amendment. |
| 90 cm / 60 cm preservation | House policy / heuristic | `HOUSE POLICY: Dishadharti silvicultural proxy; not a statutory prohibition.` |
| Girth-to-age range | Derived estimate | `DERIVED ESTIMATE: allometric range; final age determined by the Tree Officer.` |
| 70/30 green weights; 30/30/20/20 composite | House judgment | `HOUSE JUDGMENT: screening weights.` |

### Legal caveats

- Do not say “no felling permitted” for a house-policy threshold.
- Do not say “no permit required for a dead tree” without a verified legal basis.
- Do not present the compensation range as a legal determination; the Tree Officer determines age.
- Add the heritage and >200-tree referral flags even if the tool’s local verdict is only advisory.
- The prior draft’s case citations (PIL/NGT numbers) were not verified here; do not repeat them without checking.

---

## 8. Reproducibility and engineering

### What cannot be reproduced from a clean clone

- `tree_index.sqlite` (about 52 MB) and `reference_layers.sqlite` are ignored/absent.
- The 2019 census CSVs (about 1.2 GB) and the KMLs (`pmc_wards_2025.kml`, `WARD12_TEST_SITE.kml`) are not committed.
- `epoch_cube.json` is committed (good), as is the IMD annual-max CSV, but the GEE build is not reproducible without credentials/asset IDs.
- The validation JSONs contain no `code_commit`, `config_sha256`, `cube_sha256`, `scorer_version`, or `heat_mode`.
- The README’s ranges and the committed `ward_validation.json`/`site_validation.json` do not match; `stress/` is a third vintage.
- The report says the KML is a repo file; it is not.

### Minimum provenance block

Every assessment, validation row, and report should carry:

```
{
  "code_commit": "...",
  "working_tree_dirty": false,
  "scorer_version": "2.x.y",
  "region_config_sha256": "...",
  "epoch_cube_sha256": "...",
  "tree_index_sha256": "...",
  "heat_mode": "NIGHT_MODIS_LST",
  "design_storm_mm": 214.0,
  "hsg": "B|C|D",
  "weights": {"flood":0.3,"heat":0.3,"green":0.2,"carbon":0.2},
  "generated_at_utc": "..."
}
```

A CI test should parse every committed JSON/CSV, compare the provenance hashes to the current config/cube, assert `heat_mode == "NIGHT_MODIS_LST"`, and re-run the saved inputs to 1e-6. Any drift fails the build.

### Large artefacts

- Commit a small `tests/fixtures/ward12_sample_trees.sqlite` (<400 KB) so tests run offline.
- Publish the full tree index as a compressed Parquet or zstd SQLite release asset with a SHA-256 and row count; provide `python -m ml_pipeline.cli bootstrap --verify-checksums`.
- Add an `artifacts.lock.json` with source URLs, file sizes, checksums, retrieval dates, and licences.
- Add a data dictionary for `epoch_cube.json`: each field, units, source, reducer, scale, date range, cloud mask, QA bits, and per-cell sample count.

### The off-by-one

The correct census total is **4,009,623** (16 × 250,000 + 9,623). `geometry.py`, `species.json`, and `docs/make_report.py` use 4,009,624. The “4,009,623 of 4,009,624 unique” line should become “4,009,623 unique,” not “one tree dropped.”

### The web app

If the web app remains, it needs its own provenance and a clear `isDemo` flag. The current `isDemo: false` and `source: "verified-scenario"` are not acceptable for fabricated inputs. The cleanest path is to delete the legacy scorer and call the Python CLI/API, or to label the web app as a non-scientific prototype and keep it out of the submission.

---

## 9. Prioritized fix list

| Priority | Fix | Effort | Impact | Proof it worked |
|---|---|---|---|---|
| Critical | Fix missing land-cover zero-fill; make partial results `REVIEW` only | 1–2 days | Prevents false APPROVE/100 | Empty indicators → flood `None`, verdict `REVIEW`; tests. |
| Critical | Fix seasonal-bare double count; gate land-cover sums | 1 day | 166 saturated cells become meaningful | Cube sum ≤ 1; flood distribution shifts; regression test. |
| Critical | Split `impervious_footprint_m2`, `total_gfa_m2`, `plot_area_m2` | 2–3 days | Correct flood/plot and carbon/GFA | 10-storey test: flood uses footprint, carbon uses GFA. |
| Critical | Implement or relabel proposal design; stop claiming flood/heat respond to design | 1–2 weeks | Restores the core claim or makes the product honest | Two designs on one plot score differently, or docs say baseline. |
| Critical | Add per-factor review thresholds/veto | 1 day | A worst single factor cannot APPROVE | Heat 99/carbon 100 tests → `REVIEW`. |
| Critical | Regenerate validation with night LST, area-weighted cells, site canopy, no fake defaults | 2–3 days | Credible validation | Committed artefacts with provenance; expected ordering; no 150/200/3.0. |
| Critical | Fix legal labels: 1:3→2×, 90 cm house policy, heritage/referral, 6 ft/7 yr | 1 day | Legal defensibility | JSON/narrator label tests; Gazette citations. |
| Critical | Fix carbon threshold/double count/units/GFA | 2–3 days | Carbon defensibility | 5% aluminium → withheld/flagged; m³ conversion; double-count blocked. |
| Critical | Quarantine or rewire the legacy web app | 2–5 days | Removes the fake-data contradiction | Web app calls the Python scorer or is marked demo. |
| High | Replace HSG B with soil map; report absolute and excess runoff | 1 week | Better flood physics | HYSOGs250m field in cube; sensitivity table. |
| High | Fix water CN baseline | 1 day | No river/lake penalty | Water cells ΔQ_water = 0; regression test. |
| High | Elevation-match heat reference; absolute thresholds; remove day fallback | 1 week | Heat validity | Partial correlation with elevation reduced; night-only artefacts. |
| High | Green: site-scale vegetation, proposed canopy, algebra, >100 handling | 1 week | Green validity | No effective > satellite; tree-loss sensitivity. |
| High | Add flood-plain penalty / blue-red lines | 3–5 days | Fluvial risk | Riverside sites score higher; hotspot validation. |
| High | Provenance + CI freshness | 2 days | Reproducibility | CI re-runs artefacts to 1e-6. |
| High | Any-region gate: refuse PROVISIONAL/UNSOURCED constants | 3–5 days | Honest reuse | New-region config rejected; second city. |
| Medium | Gumbel/GEV model uncertainty; Lilliefors/bootstrap AD | 1 day | Correct storm statistics | AIC/AD table; CI includes model uncertainty. |
| Medium | Carbon bands from A1–A3 distribution; 700 as marker | 1 week | Meaningful carbon scale | Typology percentiles; score monotonic. |
| Medium | Census growth/attrition and geolocation audit | 1 week | Green/legal accuracy | ΔNDVI/field audit; uncertainty range. |
| Medium | Data manifest, micro-fixture, zstd/Parquet, KML checksums | 2 days | Clean-clone reproducibility | Offline tests; checksummed download. |
| Low | Fix `factor_breakdown.py` sign convention | 1 hour | Correct interpretation | Correlation table signs. |
| Low | Correct 4,009,624 → 4,009,623 | 1 hour | Data integrity | Row count matches 16×250,000+9,623. |
| Low | UI polarity labels, decimals, `isDemo` | 1 day | Communication | Labels and tests. |

---

## 10. Questions for methodological sign-off

1. **Which system is the submission?** The Python `ml_pipeline`/`engine`, or the React/Express web app? They use different scorers and data.
2. **What is the decision the score is allowed to drive?** Pre-approval screening, prioritisation, or a formal condition/rejection? The answer determines the required accuracy and the per-factor veto policy.
3. **Is this a proposal-impact tool or a site-baseline tool?** If proposal-impact, where are the post-development land cover, footprint, and planting plan?
4. **What is `builtUpAreaSqm`?** Ground plinth or total GFA? What happens to a 30-storey building whose GFA exceeds the plot?
5. **What is the site/plot geometry?** Is `WARD12_TEST_SITE.kml` a plot or the whole ward? What is the polygon-area validation rule?
6. **What is the exact legal status of the 90 cm rule, the 60 cm test threshold, and the age-equivalent compensation in current PMC practice?** Which Act sections and Gazette notifications apply?
7. **What is the tree census geolocation accuracy and coverage?** How many records have usable coordinates and canopy diameters? How are post-2019 growth and felling handled?
8. **What are the BOQ units?** Are all quantities kg? How are m³/m² converted? Are missing material categories flagged?
9. **What is the intended carbon band semantics?** Is 700 a pass/fail threshold, a marker, or the saturation point? Is the boundary A1–A3 or whole-life?
10. **What independent validation data exist?** PMC flood hotspots, IMD/ECOSTRESS/ERA5 heat, permit records, RERA BOQs, field tree audits.
11. **What update cadence is promised?** 2019 census, 2024 cube, 2025 wards; when will 2026 data arrive?
12. **What false-positive/false-negative rate is acceptable for a screening tool?** Who reviews a `BORDERLINE_VERDICT`?
13. **What can the tool legally decide?** If the answer is “nothing; it is advisory,” the report and UI must say so everywhere.

---

## Bottom line

The Python pipeline has real scientific strengths: a measured night-LST decision, a defensible 100-year storm derivation, a deterministic scorer, honest house-band labels, and a serious attempt to separate flood, heat, green, and carbon. But it currently overclaims what it measures. Flood and heat score the existing cell, not the proposal; green mixes scales; the validation is circular and stale; and the composite can approve a site with a worst-case single factor.

The highest-value fixes are not cosmetic. They are: stop zero-filling missing data, stop double-counting seasonal bare, decide whether this is a baseline or a proposal-impact tool, add per-factor review thresholds, regenerate validation with the current night path and no fake defaults, correct the legal labels, and remove or rewire the legacy web scorer. Until those are done, the tool is a promising prototype with a well-written methods narrative, not a defensible pre-approval instrument.
