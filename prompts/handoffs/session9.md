# Session 9 handoff — partial-evidence contract and recommendation safety

**Date:** 2026-11-02
**Model:** DeepSeek V4.1 Flash
**Status:** complete; all target tests pass. `pytest` is not installed in this
checkout, so the runnable test files were executed directly.

## Evidence-tier contract implemented

`score_project` now returns these additional fields on every result:

```json
{
  "evidence_status": "COMPLETE | PARTIAL | INSUFFICIENT | UNAVAILABLE",
  "decision_grade": true,
  "available_factor_count": 4,
  "partial_notice": null
}
```

| Available factors | `evidence_status` | `decision_grade` | `climate_score` / `impact_score` / `risk_band` | Recommendation |
|---|---|---|---|---|
| 4/4 | `COMPLETE` | `true` | numeric | normal decision |
| 3/4 | `PARTIAL` | `false` | numeric but labelled diagnostic | always `REVIEW` |
| 2/4 | `INSUFFICIENT` | `false` | all `null` | `REVIEW`, "insufficient evidence" headline |
| 1/4 or 0/4 | `UNAVAILABLE` | `false` | all `null` | `REVIEW`, "assessment unavailable" headline |

- `complete` is still `true` only at 4/4.
- `missing_factors` still lists every unavailable factor.
- `weight_contributions` is populated only when `decision_grade` is true.
- `partial_notice` is always present; it is `null` at 4/4.
- The per-factor veto, the `Very High` carbon-band rule and blocking issues
  still force `REVIEW` at 4/4.
- Weights (0.30/0.30/0.20/0.20), the 30/60 approve/condition boundaries,
  measured constants and all factor formulas are unchanged.
- A 4/4 result was diffed against the pre-session `HEAD` tree and is
  byte-identical for `climate_score`, `impact_score`, `risk_band`,
  recommendation, sub-scores and weight contributions.

## Files changed

| File | Change |
|---|---|
| `ml_pipeline/core/scoring.py` | Added evidence-tier helpers/constants, composite withholding below 3/4, explicit result fields, and tier-aware `_decision` headlines. 3/4 is always `REVIEW`; 2/4 and below always `REVIEW` with no composite. |
| `ml_pipeline/core/recommendations.py` | Added `_finite_number`; removed all 60/30 land-cover defaults; guarded impervious, tree-preservation and combined rescoring; added `skipped_actions`; filtered actions targeting an unavailable baseline factor; added `baseline_evidence_status`, `baseline_decision_grade`, `baseline_available_factor_count`. |
| `ml_pipeline/report/render.py` | `score_block` branches on `decision_grade`; 3/4 is labelled `DIAGNOSTIC ONLY — NOT COMPARABLE TO A COMPLETE SCORE`; 2/4 and below print `CLIMATE SCORE: NOT ISSUED` and `RISK BAND: NOT ISSUED`; missing-factor reasons stay visible. `decision_block` states the result is not decision-grade and lists skipped actions with their reasons. |
| `ml_pipeline/report/narrative.py` | Prompt now carries `EVIDENCE_STATUS`, `DECISION_GRADE`, `AVAILABLE_FACTORS`, `MISSING_FACTORS`, `partial_notice`. Added iron rules forbidding narration as approval/normal score, and withholding numbers for 2/4 and below. |
| `ml_pipeline/tests/test_scoring.py` | Added 11 regression tests covering the four tiers, carbon-only behaviour, renderer output, missing land cover, skipped actions, partial verification and material substitutions without land cover. |
| `ml_pipeline/tests/test_narrative.py` | Added 14 checks for partial/insufficient/unavailable prompt payloads, including a real carbon-only score. |
| `engine/tests/test_engine.py` | Added checks that the complete engine fixture propagates `COMPLETE`, `decision_grade=true`, 4 factors and weight contributions. |
| `ml_pipeline/research/07_decisions/0012-partial-evidence-contract.md` | New decision note. |

Not touched: validation harness/JSONs, `docs/`, PDF, `frontend/`, `backend/`,
measured constants, weights, bands, flood/heat physics.

## Recommendation safety

- `_impervious_reduction` runs only when `impervious_pct` and
  `vegetation_pct` are numeric finite values. Otherwise it records
  `{"id": "impervious_reduction", "reason": "impervious_pct or
  vegetation_pct unavailable"}` in `skipped_actions`.
- `_preserve_mature_trees` guards `canopy_cover_pct(_proposed)`,
  `always_preserve_canopy_m2`, `plotAreaSqm` and `builtUpAreaSqm`. No
  `float(None)` and no zero substitution.
- `_combined` repeats the numeric guards before applying shifts or rescaling.
- `_material_substitutions` still models a BOQ substitution when land cover is
  missing, because carbon is independent. It is skipped only when the baseline
  carbon factor is unavailable or the BOQ is empty.
- No recommendation can claim to improve a factor that was `UNAVAILABLE` in
  the baseline. Such actions move to `skipped_actions`.
- Ranking and the "verified only if the rescore moved the targeted factor"
  rule are unchanged.
- Residual limitation: at 1/4 or 2/4 the composite is withheld, so
  `material_substitution` (which verifies on `impact_delta`) can be produced
  internally but is then listed under `dropped_unverified`. It is never
  fabricated as verified. Changing that would change the verification rule.

## Test commands and outputs

Run from the repository root. `python3` was used because there is no `.venv`
and `pytest` is not installed.

```bash
python3 ml_pipeline/tests/test_scoring.py
# 83/83 passed

python3 ml_pipeline/tests/test_narrative.py
# 36/36 passed

python3 engine/tests/test_engine.py
# 25/25 passed

python3 engine/tests/test_strict.py
# PASS strict rejects provisional ...
# PASS non-strict accepts
# PASS scaffold provisional
```

Other checks:

```bash
python3 ml_pipeline/tests/test_data_integrity.py
# SKIP: reference index missing/empty; build reference_layers.sqlite

python3 ml_pipeline/tests/test_e2e_ward12.py
# FAIL: tree index missing at ml_pipeline/data/tree_index.sqlite
```

Both are the pre-existing blocked-data conditions (P0-3), not regressions.

Proof the new tests fail on the old behaviour: an archive of `HEAD` was
extracted to `/tmp/opencode/old`, the new test file was copied in, and the
suite was run there:

```text
72/83 passed
11 errors, all in the new tests:
- 9 x KeyError (8 on 'evidence_status'/'baseline_evidence_status',
  1 on 'skipped_actions')
- 1 x TypeError: float() argument must be a string or a real number,
  not 'NoneType'  (the None land-cover crash)
- 1 x TypeError for the new skipped= argument
```

With this change: `83/83 passed`.

## Before/after example — carbon-only input

Fixture: `builtUpAreaSqm=2000`, `plotAreaSqm=4000`, BOQ
`[{"name": "cement", "quantityKg": 100000}]`, indicators `{}`, no ledger.
This is 1/4 available factors.

Before (pre-session `HEAD`):

```text
climate_score = 96.2
impact_score  = 3.8
risk_band     = Low
recommendation = REVIEW
partial_notice = "... NOT comparable to a complete score."
```

After:

```text
climate_score = None
impact_score  = None
risk_band     = None
evidence_status = UNAVAILABLE
decision_grade = false
available_factor_count = 1
recommendation = REVIEW
headline = "Review required: assessment unavailable — only 1 of 4 factors are available."
partial_notice = "Score computed from 1 of 4 factors. Missing: flood, heat, green.
                  Assessment unavailable: the composite climate score, impact score
                  and risk band are NOT ISSUED."
sub_scores.carbon = 3.8   (evidence only, not a verdict)
```

The review's reported `92.4 / Low` example follows the same path: the carbon
sub-score remains visible, but no composite or band is issued.

## Remaining places that could still surface a partial score

These are outside Session 9's ownership and were not edited:

1. `ml_pipeline/data/validate_sites.py` and `validate_wards.py` write
   `score = res.get("climate_score")` and `band = res.get("risk_band")`. For
   partial rows these are now `null`; their tables will print `None`. They
   should also carry `evidence_status`/`decision_grade` when Session 11
   regenerates the validation JSONs.
2. `ml_pipeline/data/e2e_verify.py` prints `impact_score` and `risk_band`
   directly. Partial rows will show `None`.
3. `docs/make_report.py` / the PDF and `docs/example_assessment.json` may still
   read or hardcode numeric composites. Session 12 owns those artifacts.
4. Any external consumer that reads the raw JSON must check `decision_grade`
   before presenting `climate_score` or `risk_band`. The scorer cannot enforce
   that beyond its own renderer and narrator.

The CLI path (`ml_pipeline/cli.py`) uses `render_report`, so it is covered by
the fixed renderer.

## What Session 11 needs to know

- Partial results now expose `climate_score`, `impact_score` and `risk_band`
  as `null` for 2/4 and below. Do not coerce them to `0` or `"N/A"` in a way
  that reads as a score.
- Preserve `evidence_status`, `decision_grade`, `available_factor_count` and
  `missing_factors` in regenerated validation JSONs.
- A 3/4 row has a numeric composite but `decision_grade=false`; label it as a
  diagnostic, never as a decision-grade band.
- Green remains `UNAVAILABLE` while `tree_index.sqlite` is missing; drainage
  and slope data remain missing. Do not fabricate them to reach 4/4.

## What Session 13 needs to know

- The evidence-tier contract is implemented and tested; the acceptance matrix
  is in `0012-partial-evidence-contract.md`.
- 4/4 behaviour is unchanged (verified by diff against `HEAD`).
- The known residual limitation is the material-substitution verification rule
  at 1/4–2/4 described above.
- `pytest` is still not installed, so the sign-off record should show the
  direct test commands and outputs rather than a `pytest` run.
- The two blocked checks (`test_data_integrity.py` skip,
  `test_e2e_ward12.py` missing tree index) are P0-3 data gaps, not scoring
  regressions.
