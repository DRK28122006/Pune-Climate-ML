# Handoff — Session 2 (core scoring safety)

**Date:** 2026-11-02
**Branch:** main (committed locally, 81ae2e2)

## Changed files
- `ml_pipeline/core/scoring.py` — `_as_number`, `Recommendation`, `area_weighted_cn` explicit renormalisation, `compute_flood` missing-data gate + landcover reporting, `_decision` per-factor veto + partial rule, `_canopy_for_green`, `score_project` no zero-fill.
- `ml_pipeline/tests/test_scoring.py` — 65 tests, added empty/null/partial/single-factor-extreme/census-total cases.
- `ml_pipeline/config/regions/pune.json` — census total 4009623; `decision_policy` block.
- `ml_pipeline/core/geometry.py` — census fallback 4009623.
- `ml_pipeline/cli.py` — removed 70/24 fallbacks; assumptions marked.
- `engine/score.py` — missing bands stay None; annual bare only.
- `ml_pipeline/research/07_decisions/0001-core-safety-policy.md`.

## Verified
- `.venv`-equivalent python: `ml_pipeline/tests/test_scoring.py` 65/65; `pytest ml_pipeline/tests` 65 passed; `engine/tests/test_engine.py` 23/23.
- Empty indicators → flood None, verdict REVIEW (verified).
- `grep 4009624` in live code/config/docs: none (only data snapshots + this prompt).

## Behaviour
- Empty indicators → REVIEW, not APPROVE.
- Single factor ≥ threshold (flood 50, others 80; carbon Very High) → REVIEW.
- Complete low-impact result still APPROVE.
- Seasonal bare reported (`seasonal_bare_used=false`); no silent clamp.

## Session 3 needs
- Validation regeneration must use new missing-data semantics; stale JSONs still carry old totals.
- Flood scale normalisation (Session 4) should revisit flood veto threshold 50.
- Artifacts under `ml_pipeline/data/` still show old census scalar until regenerated.
EOF
echo done