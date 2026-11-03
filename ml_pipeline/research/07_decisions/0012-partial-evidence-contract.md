# Decision 0012 — partial-evidence contract and recommendation safety

**Date:** 2026-11-02
**Session:** 9 (partial-data contract and recommendation safety)
**Status:** accepted
**Scope:** evidence tiers, composite issuance, report/narrative enforcement, recommendation input guards

## Context

Sessions 1–8 withheld individual factors from the composite when their inputs
were missing, but the composite itself was still issued for any number of
available factors. A carbon-only input produced a numeric `climate_score`,
`impact_score` and `risk_band` (for example `92.4 / Low`) and only the
recommendation code stayed `REVIEW`. A report reader could therefore see a
decision-grade-looking "Low" score for an assessment that had measured one
factor out of four.

The recommendation engine had a second, independent defect. It defaulted
missing land cover to 60% impervious and 30% vegetation, and it called
`float(None)` when those keys were present but null. Absent data could thus be
invented as a baseline and the invented baseline could be "improved" by
rescoring, or the call could crash.

## Decisions

### 1. Four evidence tiers

The tier is determined only by how many of the four factors could be scored.
It is not a judgement about how good the available numbers look.

| Available factors | `evidence_status` | `decision_grade` | Composite / band | Recommendation |
|---|---|---|---|---|
| 4/4 | `COMPLETE` | `true` | numeric | normal decision |
| 3/4 | `PARTIAL` | `false` | numeric diagnostic, labelled | always `REVIEW` |
| 2/4 | `INSUFFICIENT` | `false` | all composite fields `null` | `REVIEW`, "insufficient evidence" |
| 1/4 or 0/4 | `UNAVAILABLE` | `false` | all composite fields `null` | `REVIEW`, "assessment unavailable" |

`score_project` now emits `evidence_status`, `decision_grade`,
`available_factor_count` and an always-present `partial_notice` (null only at
4/4). `complete` remains true only at 4/4. `weight_contributions` is populated
only when `decision_grade` is true. `missing_factors` still lists every
unavailable factor.

The per-factor veto, the `Very High` carbon-band review rule and blocking
issues are unchanged and still force `REVIEW` at 4/4.

### 2. Why 3/4 may be shown, but only as a diagnostic

Three scored factors still carry real information, and suppressing it entirely
would remove the ability to explain what the site looks like. But a 3/4
composite is a renormalised mean over different weights; it is not comparable
with a 4/4 score, and one missing factor could be the one that would have
vetoed the project. It is therefore allowed as a **DIAGNOSTIC ONLY — NOT
COMPARABLE TO A COMPLETE SCORE**, never as an approval, and the recommendation
is unconditionally `REVIEW`.

### 3. Why 2/4 and below carry no composite or band

With half the evidence absent, renormalisation gives the remaining two factors
double their normal influence. The result is not a weaker version of the same
measurement; it is a different, unvalidated measure. Issuing a number or a band
would give a downstream report something that looks like a decision. The scorer
therefore sets `climate_score`, `impact_score` and `risk_band` to `null` and
says so in the recommendation headline. The per-factor sub-scores remain
visible as evidence.

### 4. Renderer and narrator enforcement

`ml_pipeline/report/render.py` branches on `decision_grade`:

- 4/4 keeps the normal `CLIMATE SCORE` / `IMPACT SCORE` / `RISK BAND` block.
- 3/4 prints `EVIDENCE STATUS: PARTIAL`, the missing factors, and every number
  under a `DIAGNOSTIC ONLY — NOT COMPARABLE TO A COMPLETE SCORE` label.
- 2/4 and below print `CLIMATE SCORE: NOT ISSUED` and `RISK BAND: NOT ISSUED`,
  plus an explicit insufficient/unavailable sentence.
- Missing-factor rows keep their withholding reason visible.

`ml_pipeline/report/narrative.py` adds `EVIDENCE_STATUS`, `DECISION_GRADE`,
`AVAILABLE_FACTORS`, `MISSING_FACTORS` and `partial_notice` to the prompt, plus
an iron rule that a non-decision-grade result must never be narrated as an
approval or as a normal score. For 2/4 and below the prompt supplies
`impact: NOT ISSUED` / `risk band: NOT ISSUED` rather than a number, and an
additional rule requires the narrator to call the assessment
insufficient/unavailable and not low risk.

### 5. Recommendation actions are skipped when their inputs are missing

`recommendations.py` now uses a single `_finite_number` guard. No default land
cover exists anywhere in the recommendation path.

- `_impervious_reduction` runs only when both `impervious_pct` and
  `vegetation_pct` are numeric finite values. Otherwise it is skipped with
  `{"id": "impervious_reduction", "reason": "impervious_pct or
  vegetation_pct unavailable"}`.
- `_preserve_mature_trees` guards canopy (`canopy_cover_pct_proposed` /
  `canopy_cover_pct`), `always_preserve_canopy_m2`, `plotAreaSqm` and
  `builtUpAreaSqm`. A missing value skips the action with a reason rather than
  calling `float(None)` or substituting zero.
- `_material_substitutions` still runs when land cover is missing, because
  carbon is independent of land cover. It is skipped only when the baseline
  carbon factor is unavailable or the bill of quantities is empty.
- `_combined` repeats the numeric guards before applying an impervious shift or
  a footprint rescale, so the aggregate cannot reintroduce the old 60/30
  default.
- `build_recommendations` adds a `skipped_actions` list and a defence-in-depth
  filter: an action targeting a factor that was `UNAVAILABLE` in the baseline
  is moved to `skipped_actions`, not reported as an improvement. Mandatory
  blocking sourcing conditions are exempt because they do not claim an
  improvement.
- The recommendation ranking and the "verified only if the rescore moved the
  targeted factor" rule are unchanged.

## What did not change

- Composite weights remain flood 0.30, heat 0.30, green 0.20, carbon 0.20.
- The 30 / 60 approve / conditions boundaries are unchanged.
- Per-factor review thresholds and the `Very High` carbon review band are
  unchanged.
- The 214 mm design storm, 17.96 °C night reference, 5.0 °C night span, carbon
  bands 400/800/1200 and every other measured constant are unchanged.
- No factor formula was changed. `scoring.py` only propagates the evidence
  tier and withholds the composite below 3/4.

## Consequences

- A carbon-only assessment no longer reports a numeric climate score or a
  `Low` band. It reports `UNAVAILABLE`, `REVIEW`, and the carbon sub-score as
  evidence only.
- A 3/4 assessment remains useful for diagnosis but can never approve.
- Recommendation calls no longer crash on `None` and cannot invent land cover.
- Generated artifacts and validation scripts that consume `climate_score` /
  `risk_band` may now receive `null` for partial assessments. That is the
  intended contract; renderers must handle `null` rather than treat it as a
  numeric score. The validation harness is owned by Session 11 and was not
  edited here.

## Verification

`pytest` is not installed in this checkout, so the runnable test files were
used directly:

```bash
python3 ml_pipeline/tests/test_scoring.py     # 83/83 passed
python3 ml_pipeline/tests/test_narrative.py   # 36/36 passed
python3 engine/tests/test_engine.py           # 25/25 passed
python3 engine/tests/test_strict.py           # passed
```

The new scoring tests were also run against the pre-session `HEAD` tree: all
eleven failed there (9 `KeyError`s — 8 on the new evidence fields and 1 on
`skipped_actions` — 1 `TypeError: float() argument must be a string or a real
number, not 'NoneType'`, and 1 `TypeError` for the new `skipped` argument),
while the pre-existing 72 tests passed. They pass with this change.
