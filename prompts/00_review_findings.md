# Review findings after Sessions 1–8

**Date:** 2026-11-02  
**Reviewer:** DeepSeek V4.1 Flash (independent review)  
**Scope:** ML pipeline only. Frontend/backend integration is out of scope for this repair pass.

Read this file together with `prompts/00_context.md`. Sessions 9–13 are the repair pass that follows the original eight sessions.

## Verdict

Sessions 1–8 were run and committed, but the ML pipeline is **not yet sign-off ready**. The core scoring safety work is real, but four things still block a defensible screening tool:

1. The partial-data contract is not implemented as agreed.
2. Missing land cover can crash the recommendation engine.
3. Green, slope, and drainage validation are still missing because data assets are absent.
4. Generated artifacts, the report, and the test story are stale or incomplete.

Full-stack integration is **not** the only pending item.

## What is already good

- Missing land cover no longer becomes a perfect flood score.
- Seasonal bare soil is reported, not added to the annual partition.
- Per-factor veto thresholds exist.
- Census total is corrected to `4,009,623`.
- Heat is night-LST-only; day LST is excluded.
- Green uses proposed canopy and withholds when the tree ledger is missing.
- Carbon has carbon-share gating, double-count handling, unit handling, and GFA/footprint separation.
- Engine strict mode and provenance checks exist.
- The web demo is labelled as a prototype.
- Research vault, decision notes, KMLs, and manifest exist.

## Verified test state

Run from the repository root. Use the project venv if `.venv` is absent.

| Check | Result |
|---|---|
| `pytest ml_pipeline/tests -q` | 72 passed |
| `python engine/tests/test_engine.py` | 23/23 passed |
| `python engine/tests/test_strict.py` | passed |
| `python ml_pipeline/tests/test_narrative.py` | 22/22 passed |
| `python ml_pipeline/data/check_provenance.py` | passed |
| `python ml_pipeline/tests/test_e2e_ward12.py` | FAIL — `tree_index.sqlite` missing |
| root `pytest` | FAIL — collects `ml_pipeline/data/day_signal_test.py`; `No module named ee` |
| `python ml_pipeline/tests/test_data_integrity.py` | SKIP — `reference_layers.sqlite` missing or empty |
| `validate_sites.py` | 8/8 sites partial; green never scored |
| `validate_wards.py` | 6/6 scored, 0/6 complete |

## P0 findings

### P0-1 — Partial-data contract is not implemented

`score_project` still emits a numeric `climate_score`, `impact_score`, and `risk_band` for 1/4 and 2/4 available factors.

Current example: carbon-only input with a valid BOQ returns:

```text
climate_score = 92.4
impact_score  = 7.6
risk_band     = Low
recommendation = REVIEW
```

The recommendation is safe, but the report still prints a decision-grade “Low” score. The agreed policy was:

- 4/4 factors: complete, decision-grade.
- 3/4 factors: partial diagnostic, `REVIEW`, never approval.
- 2/4 factors: insufficient evidence, **no decision-grade composite**.
- 1/4 or 0/4: `UNAVAILABLE`, no decision-grade composite.

`ml_pipeline/report/render.py` and `ml_pipeline/report/narrative.py` still print the composite and band for partial results.

### P0-2 — Recommendation engine crashes or invents land cover

`RecommendationEngine._impervious_reduction` does:

```python
imperv = float(indicators.get("impervious_pct", 60.0))
veg = float(indicators.get("vegetation_pct", 30.0))
```

If the key exists but is `None`, it raises `TypeError`. If the key is absent, it invents 60/30 land cover and rescores a fake flood scenario.

Reproduction:

```python
indicators = {"impervious_pct": None, "vegetation_pct": None, "water_pct": None}
RecommendationEngine().build_recommendations(...)
# TypeError: float() argument must be a string or a real number, not 'NoneType'
```

### P0-3 — Green, slope, and drainage validation are missing

- `ml_pipeline/data/tree_index.sqlite` is missing, so `green` is never scored in validation.
- `ml_pipeline/data/reference_layers.sqlite` is 0 bytes; drainage lookup fails with `no such table: storm_drains`.
- `ml_pipeline/reference/pune_parks.kml` and `pune_nallas.kml` are missing.
- `epoch_cube.json` has no `mean_slope_deg`; flood uses no slope multiplier. `build_cube.py` has an uncommitted slope fix, but the cube was not rebuilt.
- `test_e2e_ward12.py` fails on the missing tree index.
- `validate_sites.py` shows 8/8 sites missing `green`.
- `validate_wards.py` shows 0/6 wards complete.

Missing data must remain `UNAVAILABLE`. Do not fabricate a tree index, canopy, drainage layer, or slope band.

### P0-4 — Validation output is misleading

- `ward_validation.json` and `site_validation.json` print day LST as `lst`/`ref`/`uhi`, while the heat sub-score is night-LST-based. The table says `heat_mode: NIGHT_MODIS_LST` but shows day UHI.
- `validate_wards.py` claims area weighting, but `_mean()` is a simple average; `area_coverage` is `selected_cells × cell_area / ward_area`, not a true polygon-cell intersection.
- `ward_validation.json` reports `trees_reliable: true` with `trees_loaded: null`.
- `site_validation.json` reports `trees: 0` and `canopy_pct: 0.0` when the census index is missing. Zero is not the same as unknown.

### P0-5 — Generated artifacts and report are stale

- `docs/example_assessment.json` still has `mean_slope_deg: 3.0`, `slope_multiplier: 1.05`, and `complete: true` with green `95.5`.
- `ml_pipeline/data/e2e/*.json` and `stress/*.json` still contain `4,009,624`, fake 3° slope, and fake drainage.
- `docs/Dishadharti_ML_Report.pdf` is dated 30 Oct and was not regenerated. `reportlab` is not installed.
- `docs/make_report.py` reads `/tmp/ward_*.json`; no such files exist in this checkout.
- `ml_pipeline/research/MANIFEST.json` marks the PDF `current` while marking the regenerated validation files `stale`.
- `ml_pipeline/research/01_data_inventory.md` still says the validation files are stale.

### P0-6 — Test suite is not green

Only `ml_pipeline/tests` passes. Root `pytest` fails on the optional GEE script, e2e fails, and data-integrity skips. A claim that “all tests pass” is not true.

### P0-7 — The tree is dirty

There are uncommitted ML changes in `recommendations.py`, `build_cube.py`, `report/render.py`, `ui/build_map.py`, validation JSONs, `docs/example_assessment.json`, `docs/make_report.py`, and `engine/tests/test_engine.py`, plus the frontend rewrite.

Do not run `git reset --hard`, `git checkout -- .`, `git clean -fd`, or delete files you did not create.

## P1 findings

- Heat elevation confounding is reported, not corrected. That is an accepted decision note, but it remains a scientific limitation.
- Fluvial flood is still `NOT_MODELLED`. That is documented, but it is not implemented.
- `site_validation.py` uses an identical per-m² BOQ, so carbon is constant at `84.5` across all sites. That does not test carbon discrimination.
- README/report ranges (`flood 14.5–53.3`, `heat 0.8–99.0`, `green 62–100`) do not match the current partial validation artifacts.
- The report PDF has hardcoded claims that need to be recomputed or labelled.

## Rules for the repair pass

1. Preserve the working tree. Do not reset or clean.
2. Missing data is `UNAVAILABLE`, never zero and never a fabricated substitute.
3. Do not weaken tests. Add tests for each fix.
4. Do not change `214 mm`, `17.96 °C`, `5.0 °C`, carbon factors, weights, or bands without evidence and a decision note.
5. Do not hand-edit generated JSONs, figures, or the PDF. Regenerate them.
6. Do not commit the census or tree index.
7. Only Session 9 may edit `ml_pipeline/core/scoring.py`.
8. Sessions 9–13 run sequentially, one at a time. Commit after each session and write a handoff to `prompts/handoffs/sessionN.md`.

## File ownership for the repair pass

| Area | Owner |
|---|---|
| `ml_pipeline/core/scoring.py` | Session 9 only |
| `ml_pipeline/core/recommendations.py` | Session 9 only |
| `ml_pipeline/report/render.py`, `narrative.py` | Session 9 |
| `engine/score.py`, engine tests | Session 9 for partial propagation |
| `ml_pipeline/data/` census/index/reference build | Session 10 |
| `ml_pipeline/data/validate_*.py`, validation JSONs | Session 11 |
| `ml_pipeline/tests/test_data_integrity.py`, `test_e2e_ward12.py` | Session 11 |
| `docs/example_assessment.json`, `docs/make_report.py`, PDF, `README.md`, manifest | Session 12 |
| `ml_pipeline/research/08_signoff/` | Session 13 |
| `frontend/`, `backend/` | Not in this repair pass |

## Definition of ML sign-off

The ML pipeline is ready to hand to full-stack integration only when:

- Partial evidence tiers are enforced in code and reports.
- Missing land cover cannot crash recommendations or produce a decision-grade score.
- Green, slope, and drainage are either validated with real data or explicitly `UNAVAILABLE`/`NOT_MODELLED` everywhere.
- Validation JSONs and the report are current, or clearly marked stale and not presented as evidence.
- Root `pytest` has no collection error; optional GEE/data tests skip with a clear message; e2e passes when its data exists.
- `check_provenance.py` passes.
- No generated artifact contains fabricated slope, drainage, canopy, or census values.
- A final sign-off note lists passed checks, blocked checks, and residual limitations.
