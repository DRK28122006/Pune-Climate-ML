# Session 11 — Validation harness truth pass

**Suggested model:** DeepSeek V4.1 Flash (242k context is enough for this focused harness session)  
**Dependencies:** Session 9 merged. Session 10 attempted first.  
**Owns:** `ml_pipeline/data/validate_wards.py`, `ml_pipeline/data/validate_sites.py`, `ml_pipeline/data/factor_breakdown.py`, `ml_pipeline/data/ward_validation.json`, `ml_pipeline/data/site_validation.json`, `ml_pipeline/tests/test_data_integrity.py`, `ml_pipeline/tests/test_e2e_ward12.py`, `ml_pipeline/data/day_signal_test.py` (optional-test guard only), and `ml_pipeline/research/04_validation/README.md`  
**Do not touch:** scoring formulas, `ml_pipeline/core/scoring.py`, `recommendations.py`, `report/`, `docs/`, PDF, `engine/`, `frontend/`, `backend/`

Read `prompts/00_context.md` and `prompts/00_review_findings.md` first.

## Mission

Make the validation artifacts honest and reproducible. They currently mix day and night heat, overstate “area weighting,” report unknown census as zero, and cannot be run as part of a clean test suite.

If Session 10 restored the tree index and reference layers, use them. If not, keep green/canopy and drainage explicitly unavailable. Do not fabricate values to make the table complete.

## 1. Fix the night/day heat reporting

`ward_validation.json` and `site_validation.json` currently print day LST as `lst`/`ref`/`uhi`, while the heat sub-score is night-LST-based.

Required row fields:

```json
{
  "lst_night_mean_c": 21.4,
  "lst_night_reference_c": 17.96,
  "night_uhi_delta_c": 3.44,
  "heat_score": 68.8,
  "legacy_day_lst_c": 36.2,
  "legacy_day_reference_c": 35.1,
  "legacy_day_uhi_c": 1.1
}
```

Rules:

- The primary `uhi` shown in the table must be the night delta used by the scorer.
- Day values may remain only as explicitly labelled `legacy_day_*` diagnostics.
- Do not label a day delta as the heat basis.
- If night data is missing, heat is `UNAVAILABLE`; do not fall back to day.
- Keep `heat_mode: NIGHT_MODIS_LST` in provenance.
- Do not change `17.96 °C` or `5.0 °C`.

## 2. Fix area weighting or stop claiming it

`validate_wards.py` currently selects cells by centroid and then takes a simple mean. `area_coverage` is `selected_cells × cell_area / ward_area`, not a true polygon-cell intersection.

Required, choose one:

- **Option A:** Compute the actual polygon-cell intersection area in EPSG:32643 (shapely/pyproj are already used in the repo), and weight each cell by its clipped area. Report `area_weighted: true` and the true covered fraction.
- **Option B:** If true clipping is not practical, use majority-overlap and rename the claim to `majority_overlap` / `cell_count_coverage`. Do not call it area-weighted.

Do not report `area_coverage: 1.0` just because the selected-cell count times cell area exceeds the ward area.

Add a test or assertion that a ward with edge cells does not silently claim 100% area coverage unless the clipped area really is 100%.

## 3. Fix unknown canopy and census flags

Ward validation:

- If `ward_tree_profile` is unavailable, set `trees_loaded: null`, `tree_canopy_pct: null`, and `trees_reliable: false`.
- Do not default `trees_reliable` to `true`.
- If the census profile is available and reliable, keep the real canopy value.
- If the profile is available but coverage is incomplete, set `trees_reliable: false` and withhold green.
- Do not feed ward-level canopy density into a site canopy field.

Site validation:

- If the tree index is missing or the site is outside loaded coverage, set `trees: null` and `canopy_pct: null`.
- Do not print `trees: 0` / `canopy_pct: 0.0` when the census is unknown.
- A real measured zero is allowed only when the census coverage is complete and the site genuinely contains zero trees.
- Keep `green` as `null` and in `missing` when the ledger is unavailable.

## 4. Make carbon validation meaningful

`validate_sites.py` currently uses an identical per-m² BOQ for every site, so carbon is exactly `84.5` everywhere. That does not test carbon.

Required, choose one:

- Vary at least one site's BOQ so carbon moves materially (for example one low-carbon and one high-carbon material mix), and report the spread; or
- Keep the identical BOQ but label carbon as `NOT_DISCRIMINATED_BY_THIS_HARNESS` and do not present it as a factor validation.

If you vary the BOQ, do not change the carbon factors or bands. Change only the material quantities/names in the validation fixture.

## 5. Fix the test story

The full suite is not green because optional GEE code is collected by root `pytest`.

Required:

- `ml_pipeline/data/day_signal_test.py` must not fail collection when `ee` is absent. Use `pytest.importorskip("ee")` at module import, or otherwise mark it as an optional GEE script. Do not delete the test.
- `test_e2e_ward12.py` must skip with a clear message when `tree_index.sqlite` or the Ward 12 KML is missing, instead of returning a hard failure. When the data exists, it must still run and pass; do not turn it into a no-op.
- `test_data_integrity.py` must keep its skip when the reference DB is missing, but must actually pass when Session 10 restores it.
- Do not weaken assertions. A skip is only for an absent optional dataset; a real assertion failure must remain a failure.

Root `pytest` should then collect cleanly:

```bash
python -m pytest -q
```

## 6. Regenerate artifacts

After fixing the harness, regenerate:

```bash
python -m ml_pipeline.data.validate_wards --wards 3 7 12 13 21 25
python ml_pipeline/data/validate_sites.py
```

Required provenance in both JSONs:

- `code_commit`
- `working_tree_dirty`
- `scorer_version`
- `region_config_sha256`
- `epoch_cube_sha256`
- `tree_index_sha256` (null when missing)
- `tree_index_status` (`PRESENT` / `MISSING`)
- `reference_layers_sha256` / `reference_layers_status` if the harness uses it
- `heat_mode: NIGHT_MODIS_LST`
- `design_storm_mm: 214.0`
- `hsg: B`
- `weights`
- `generated_at_utc`
- `slope_status`

Do not hand-edit the JSONs.

## 7. Update the validation README

Update `ml_pipeline/research/04_validation/README.md`:

- What each artifact tests.
- What it does **not** test.
- Whether green is scored or unavailable.
- Whether drainage/slope are present.
- Whether carbon is discriminated.
- The exact regeneration commands.
- The current test status: unit, integration, e2e, data integrity.
- Which artifacts are stale and must not be quoted.
- The independent validation plan remains a plan; do not present it as completed.

## Tests and checks

```bash
python -m pytest -q
python -m pytest ml_pipeline/tests -q
python ml_pipeline/tests/test_data_integrity.py
python ml_pipeline/tests/test_e2e_ward12.py
python ml_pipeline/data/validate_wards.py --wards 3 7 12 13 21 25
python ml_pipeline/data/validate_sites.py
python ml_pipeline/data/check_provenance.py
```

Also grep the harness and generated artifacts for fabricated defaults:

```bash
grep -R "dist_to_storm_drain_m = 150\|or 200\.0\|mean_slope_deg.*3\.0" -n ml_pipeline/data ml_pipeline/tests
```

## Acceptance

- No day LST is presented as the heat basis.
- Every UHI shown as primary is night-based.
- Area weighting is real or explicitly renamed.
- `trees_reliable` is false when the ward profile is unavailable.
- Site validation does not report unknown census as zero trees/canopy.
- Carbon is either varied or explicitly labelled not discriminated.
- Root `pytest` has no collection error.
- e2e skips clearly when data is missing and passes when data exists.
- Both validation JSONs are regenerated with provenance.
- Validation README matches the artifacts.

## Handoff

Write `prompts/handoffs/session11.md` with:

- Which issues were fixed.
- Which data was available.
- Whether green was scored or withheld.
- The new ward/site ranges and completeness counts.
- Exact test commands and outputs.
- Which artifacts are current and which remain stale.
- What Session 12 needs for the report and manifest.
