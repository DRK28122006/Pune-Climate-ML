# Session 9 — Partial-data contract and recommendation safety

**Suggested model:** DeepSeek V4.1 Flash (242k context is enough for this focused code session)  
**Dependencies:** None. Run this first.  
**Owns:** the partial-data / decision sections of `ml_pipeline/core/scoring.py`, `ml_pipeline/core/recommendations.py`, `ml_pipeline/report/render.py`, `ml_pipeline/report/narrative.py`, `engine/score.py`, `ml_pipeline/tests/test_scoring.py`, `ml_pipeline/tests/test_narrative.py`, `engine/tests/test_engine.py`, and a new decision note in `ml_pipeline/research/07_decisions/`  
**Do not touch:** validation harness or validation JSONs, `docs/`, PDF, `frontend/`, `backend/`, measured constants, weights, bands, or flood/heat physics.

Read `prompts/00_context.md` and `prompts/00_review_findings.md` first.

## Mission

Make the scorer obey the agreed partial-evidence policy, and stop the recommendation engine from crashing or inventing land cover when inputs are missing.

This is a safety pass. Do not “improve” scores. Do not change the weights, thresholds, measured constants, or factor formulas except where required to propagate the evidence tier.

## P0-1 — Implement evidence tiers

Current behaviour: 1/4 and 2/4 available factors still produce numeric `climate_score`, `impact_score`, and `risk_band`. Example: carbon-only input returns `climate_score=92.4`, `risk_band=Low`, recommendation `REVIEW`.

Required behaviour:

| Available factors | `evidence_status` | `decision_grade` | Composite / band | Recommendation |
|---|---|---|---|---|
| 4/4 | `COMPLETE` | `true` | numeric | normal decision |
| 3/4 | `PARTIAL` | `false` | numeric diagnostic allowed, clearly labelled | always `REVIEW`, never approve |
| 2/4 | `INSUFFICIENT` | `false` | `climate_score`, `impact_score`, `risk_band` = `null` | `REVIEW` with “insufficient evidence” headline |
| 1/4 or 0/4 | `UNAVAILABLE` | `false` | all composite fields = `null` | `REVIEW` with “assessment unavailable” headline |

Add explicit fields to the score result:

```json
{
  "evidence_status": "COMPLETE | PARTIAL | INSUFFICIENT | UNAVAILABLE",
  "decision_grade": true,
  "available_factor_count": 4,
  "partial_notice": null
}
```

Rules:

- `complete` remains `true` only at 4/4.
- `missing_factors` remains the list of unavailable factors.
- `weight_contributions` is populated only when `decision_grade` is true.
- A 2/4 result must not carry a number that a downstream report can mistake for a decision.
- Do not add a new recommendation code unless every downstream renderer and test handles it. `REVIEW` plus `evidence_status` is acceptable.
- Preserve the existing per-factor veto: any factor at or above its threshold still forces `REVIEW`.
- Preserve `Very High` carbon band review behaviour and blocking issues.
- Do not change the composite weights or the 30/60 approve/condition boundaries.

Update `render.py`:

- If `decision_grade` is false, do not print a normal `CLIMATE SCORE ... / RISK BAND ...` block as if it were decision-grade.
- Print `EVIDENCE STATUS: PARTIAL / INSUFFICIENT / UNAVAILABLE`, the missing factors, and a clear sentence that the number is diagnostic or withheld.
- For 3/4, if a diagnostic number is shown, label it `DIAGNOSTIC ONLY — NOT COMPARABLE TO A COMPLETE SCORE`.
- For 2/4 and below, print `CLIMATE SCORE: NOT ISSUED` and `RISK BAND: NOT ISSUED`.
- Keep the factor breakdown and missing reasons visible.

Update `narrative.py`:

- Add `decision_grade` and `evidence_status` to the prompt payload.
- Add an iron rule: a non-decision-grade result must not be narrated as an approval or as a normal score.
- A 2/4 or lower result must say the assessment is insufficient/unavailable.
- Add tests that a carbon-only result is not narrated as a clean/low-risk approval.

Update `engine/score.py` only as needed to propagate the same fields. Do not duplicate scoring logic.

## P0-2 — Fix recommendation safety

`RecommendationEngine._impervious_reduction` currently does:

```python
imperv = float(indicators.get("impervious_pct", 60.0))
veg = float(indicators.get("vegetation_pct", 30.0))
```

This raises `TypeError` when the key exists with `None`, and it invents 60/30 land cover when the key is absent.

Required:

- Run the impervious-reduction action only when both `impervious_pct` and `vegetation_pct` are numeric finite values.
- Do not use 60/30 defaults anywhere in the recommendation path.
- If the inputs are missing, skip the action and record why in a `skipped_actions` list, for example:

```json
{"id": "impervious_reduction", "reason": "impervious_pct or vegetation_pct unavailable"}
```

- Apply the same numeric guard in `_combined` before using impervious/vegetation values.
- `_preserve_mature_trees` should not use `float(None)`; guard canopy and plot values.
- `_material_substitutions` should still work when land cover is missing; carbon can be available independently.
- A recommendation must never claim to improve a factor that was `UNAVAILABLE` in the baseline.
- Do not rescore with invented land cover.
- Do not change the recommendation ranking or the rescore verification rule.

## Tests to add or update

Add regression tests in `ml_pipeline/tests/test_scoring.py`:

1. 4/4 → `COMPLETE`, `decision_grade=True`, numeric composite.
2. 3/4 → `PARTIAL`, `decision_grade=False`, `REVIEW`, labelled diagnostic.
3. 2/4 → `INSUFFICIENT`, `climate_score is None`, `impact_score is None`, `risk_band is None`, `REVIEW`.
4. 1/4 → `UNAVAILABLE`, all composite fields `None`.
5. 0/4 → `UNAVAILABLE`, all composite fields `None`.
6. Carbon-only with a valid BOQ → not `Low`/`APPROVE`; no decision-grade band.
7. Recommendations with `impervious_pct=None` → no crash, no impervious action, no fake flood improvement.
8. Recommendations with missing land-cover keys entirely → no 60/30 invention.
9. Recommendations with 3/4 factors still verify carbon/green actions against the actual baseline.
10. A recommendation that targets an unavailable factor is dropped or skipped with a reason.

Add or update narrative tests:

- Partial result is narrated as partial.
- 2/4 or lower is narrated as insufficient/unavailable, not low risk.
- `REVIEW` is not softened into approval language.
- Non-decision-grade results cannot be narrated as a normal score.

Add an engine test if the engine test suite already covers composite propagation.

## Decision note

Write `ml_pipeline/research/07_decisions/0012-partial-evidence-contract.md`:

- The four evidence tiers.
- Why 3/4 may be shown as a diagnostic but not decision-grade.
- Why 2/4 and below must not carry a composite or band.
- How the renderer and narrator enforce it.
- How recommendation actions are skipped when their inputs are missing.
- Confirmation that weights, thresholds, and measured constants were not changed.

## Commands

Use `.venv/bin/python` if it exists; otherwise use the project’s working Python environment.

```bash
python -m pytest ml_pipeline/tests -q
python ml_pipeline/tests/test_scoring.py
python ml_pipeline/tests/test_narrative.py
python engine/tests/test_engine.py
python engine/tests/test_strict.py
```

## Acceptance

- 0/4 and 1/4 return `evidence_status: UNAVAILABLE`, no composite, no band.
- 2/4 returns `INSUFFICIENT`, no composite, no band, `REVIEW`.
- 3/4 returns `PARTIAL`, `decision_grade: false`, `REVIEW`; any number shown is labelled diagnostic.
- 4/4 behaviour is unchanged.
- Recommendations never crash on `None` and never invent land cover.
- Renderer and narrator cannot present a partial result as decision-grade.
- All existing tests still pass, plus the new ones.
- Decision note `0012-partial-evidence-contract.md` exists.

## Handoff

Write `prompts/handoffs/session9.md` with:

- The exact evidence-tier contract implemented.
- Files changed.
- Test commands and outputs.
- The before/after example for carbon-only input.
- Any remaining place that could still print a partial score as decision-grade.
- What Session 11 and Session 13 need to know.

Do not claim completion until the new tests fail on the old behaviour and pass on the new behaviour. Do not reset or clean the working tree.
