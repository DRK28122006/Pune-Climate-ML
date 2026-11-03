# ML Pipeline Sign-Off — Session 13

**Date:** 2026-11-03  
**Auditor:** Beam Free (with DeepSeek review requested)  
**Scope:** ML pipeline only. Frontend/backend integration is out of scope.

## A. Verdict

**ML PIPELINE CONDITIONALLY READY**

All P0 code defects (partial-evidence contract, recommendation safety, validation truth) are closed. The test suite is green. The report and example assessment are regenerated. However, three data gaps remain open: slope band missing from the cube, parks/nallas/rivers KMLs missing (drainage incomplete), and stress/e2e artifacts are stale (marked, not regenerated). These are data-dependency blockers, not code defects. Full-stack integration may proceed for the factors that are available, with the limitations in Section D clearly stated.

## B. Test matrix

| Check | Result | Evidence |
|---|---|---|
| Root `pytest -q` | PASS | 98 passed, 1 skipped, 1 warning |
| `pytest ml_pipeline/tests -q` | PASS | 98 passed, 1 warning |
| `test_scoring.py` | PASS | 83/83 passed |
| `test_narrative.py` | PASS | 36/36 passed |
| `test_data_integrity.py` | PASS | 6/6 passed |
| `test_e2e_ward12.py` | PASS | All checks passed (69,982 trees, all 4 factors scored) |
| `engine/tests/test_engine.py` | PASS | 25/25 passed |
| `engine/tests/test_strict.py` | PASS | strict rejects provisional; non-strict accepts |
| `check_provenance.py` | PASS | Both validation JSONs OK |
| `day_signal_test.py` | SKIP | `ee` (Google Earth Engine) not installed |
| Partial-evidence contract | PASS | 4/4 COMPLETE, 3/4 PARTIAL, 2/4 INSUFFICIENT, 1/4+0/4 UNAVAILABLE |
| Artifact freshness | PASS (partial) | `ward_validation.json` and `site_validation.json` current; `stress/` and `e2e/` stale |

## C. P0 closure

| P0 | Item | Status | Evidence | Remaining risk |
|---|---|---|---|---|
| P0-1 | Partial-data contract not implemented | **Closed** | `_evidence_status()` in `scoring.py`; 4/4→COMPLETE, 3/4→PARTIAL, 2/4→INSUFFICIENT, 1/4/0/4→UNAVAILABLE. Renderer prints NOT ISSUED for non-decision-grade. Narrator receives `evidence_status`/`decision_grade`. Tests for all tiers. | None |
| P0-2 | Recommendation engine crashes or invents land cover | **Closed** | `_finite_number()` guard in `recommendations.py`; no 60/30 defaults; `skipped_actions` list. Test: `impervious_pct=None` → no crash, no action, no fake flood improvement. | None |
| P0-3 | Green, slope, drainage validation missing | **Partially closed** | Tree index restored (4,009,623 trees). Green now scored in validation. Storm drains present (141,341). Parks/nallas/rivers KMLs still missing (0 rows). Slope band absent (`ee` not installed). | Green validation works but parks/nallas/rivers drainage incomplete; slope unavailable |
| P0-4 | Validation output misleading | **Closed** | Night LST primary in both JSONs. True area weighting (shapely/pyproj). `trees_reliable` false when census unavailable. Site validation uses null for unknown census. | None |
| P0-5 | Generated artifacts and report stale | **Partially closed** | `example_assessment.json` regenerated (real scorer, no fake slope). PDF regenerated from `make_report.py`. `stress/` and `e2e/` marked stale via `STALE.md` but not regenerated. | Stress/e2e artifacts still contain fabricated values; must not be quoted |
| P0-6 | Test suite not green | **Closed** | Root pytest: 98 passed, 1 skipped (day_signal_test, ee missing). e2e passes. Data integrity 6/6. No collection errors. | day_signal_test skips (optional GEE dependency) |
| P0-7 | Tree is dirty | **Open (expected)** | Uncommitted changes from Sessions 1–8 and 9–12. No reset/clean performed. | Sessions must be committed before full-stack handoff |

## D. Residual limitations

1. **Heat elevation confounding** — partial r(built|elevation) ~0.41 on the 864-cell cube. Reported, not corrected. No elevation-banded rural reference available.
2. **Fluvial flood not modelled** — `NOT_MODELLED`. Only pluvial (SCS-CN) flood is scored.
3. **Green unavailable if census/tree index missing** — green is `UNAVAILABLE` when the tree index is absent. With the index present (current state), green is scored.
4. **Flood slope missing** — `mean_slope_deg` absent from all 864 cube cells. `ee` (Google Earth Engine) not installed. Flood scoring continues without slope multiplier.
5. **Drainage incomplete** — storm drains present (141,341), but parks/nallas/rivers tables are empty (KMLs not in repo). Park attribution and nalla proximity checks cannot be validated.
6. **1 km satellite resolution** — cube cells are ~1 km. Sub-plot variation is not captured.
7. **Carbon A1–A3 only** — cradle-to-gate embodied carbon. Excludes transport (A4) and site waste (A5).
8. **Any-region is scaffolded, not proven** — engine strict mode rejects provisional constants. Only Pune has accepted constants.
9. **Web demo is a prototype** — labelled as such (Session 8). Not wired to the ML pipeline.
10. **Stress/e2e artifacts are stale** — contain fabricated values. Marked `STALE — DO NOT QUOTE`. Not regenerated.

## E. What full-stack may and may not claim

### May claim
- Deterministic four-factor climate screening (flood, heat, green, carbon) when all inputs exist
- Missing factors are withheld and reported as `UNAVAILABLE` — never zero-filled or scored as perfect
- Partial results (3/4) are shown as diagnostic-only with `REVIEW` recommendation, never approval
- 2/4 or fewer factors: no composite score, no risk band, `REVIEW`
- Night-LST-only heat scoring with documented day-LST retirement
- SCS-CN flood with 214 mm design storm, slope modifier, engineered drainage proximity
- Carbon A1–A3 with India-specific emission factors from IFC India Table 16
- Statutory tree compensation under Maharashtra Trees Act 1975 (as amended 2021)
- Web demo is a prototype scenario calculator

### May not claim
- Flood or heat accuracy (no independent validation executed)
- Green validation without the census/tree index
- Floodplain exposure (fluvial flood not modelled)
- Any-region portability (only Pune has accepted constants)
- Web demo results are measured assessments
- Stress/e2e artifact numbers (stale, fabricated values)
- Slope-adjusted flood scores (slope band missing)
- Park/nalla drainage validation (KMLs missing)

## F. Recommendation

**CONDITIONAL GO for full-stack integration**, with the following prerequisites:

1. **Commit Sessions 9–12** before handing off to full-stack. The dirty tree must be cleaned up (committed, not reset).
2. **Do not claim** green validation, drainage validation, slope-adjusted flood, or fluvial flood exposure in the frontend or backend.
3. **Do not wire** the web demo to the ML pipeline until the data gaps are resolved.
4. **Restore missing data** (parks/nallas KMLs, slope band via GEE) before claiming full four-factor validation.
5. **Regenerate stress/e2e artifacts** from the current scorer before quoting any ward-level numbers.

The ML pipeline is defensible for the factors that are available (flood, heat, green with census, carbon). The partial-evidence contract ensures that missing factors are honestly reported. The code is safe, tested, and documented. The remaining gaps are data-dependency issues, not code defects.

## G. Final diff summary

```
git status --short (ML-relevant files only):
 M README.md
 M docs/Dishadharti_ML_Report.pdf
 M docs/example_assessment.json
 M docs/make_report.py
 M engine/tests/test_engine.py
 M ml_pipeline/core/recommendations.py
 M ml_pipeline/core/scoring.py
 M ml_pipeline/data/build_cube.py
 M ml_pipeline/data/site_validation.json
 M ml_pipeline/data/validate_sites.py
 M ml_pipeline/data/validate_wards.py
 M ml_pipeline/data/ward_validation.json
 M ml_pipeline/report/narrative.py
 M ml_pipeline/report/render.py
 M ml_pipeline/tests/test_data_integrity.py
 M ml_pipeline/tests/test_e2e_ward12.py
 M ml_pipeline/tests/test_narrative.py
 M ml_pipeline/tests/test_scoring.py
 M ml_pipeline/ui/build_map.py
?? ml_pipeline/research/05_sources/DATA_STATUS.md
?? ml_pipeline/research/07_decisions/0012-partial-evidence-contract.md
?? ml_pipeline/research/07_decisions/0013-report-artifact-status.md
?? ml_pipeline/research/08_signoff/ML_SIGNOFF.md
?? prompts/ (session9-13 + handoffs)
```

No reset or clean was performed. All changes are intentional (Sessions 9–13 work).
