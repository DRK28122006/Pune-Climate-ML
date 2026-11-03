# Session 7 — Engine, any-region, and CI

**Suggested model:** GLM 5.3 Flash  
**Dependencies:** Sessions 2 and 3  
**Owns:** `engine/region.py`, `engine/score.py`, `engine/tests/`, `.github/` if you add CI, `ml_pipeline/tests/test_data_integrity.py` provenance checks  
**Do not touch:** scoring formulas, validation artifacts, `report/`, `frontend/`, `backend/`

Read `prompts/00_context.md` first.

## Mission

Make “any region” honest and make provenance enforceable. The current engine scaffold proves plumbing, not scientific reuse. It also accepts provisional constants and has no CI check that committed artifacts match the current code/config/cube.

## Fix C11 — any-region gate

Current problem:

- `engine/region.py` scaffolds a new region with:
  - 150 mm provisional storm
  - Pune CN table
  - Pune carbon bands 400/800/1200
  - Pune 70/30 green weights
  - Pune 0.30/0.30/0.20/0.20 composite weights
- `validate_config` checks structure and weight sums, not provenance or scientific validity.
- The 23-test synthetic region is a 2×2 grid with three trees. It proves plumbing, not real-world reuse.

Required:

- Add a provenance/status field for every scientific constant:
  - `design_storm_status`
  - `cn_table_status`
  - `thermal_reference_status`
  - `carbon_bands_status`
  - `green_weights_status`
  - `composite_weights_status`
- `validate_config` must reject or warn loudly on `PROVISIONAL`, `UNSOURCED`, `PENDING`, or `STALE` where a real assessment is requested.
- Add a strict mode: `score.py` refuses to score a real region unless every required constant has an accepted status.
- Keep the synthetic region for plumbing tests, but label it `SYNTHETIC_FIXTURE` and never present it as evidence of city reuse.
- Write `ml_pipeline/research/07_decisions/0011-any-region-contract.md` describing what a second real city must supply and what would count as proof.

Do not claim “any region” until a real second city has been scored end-to-end with an independent config and data. A 2×2 synthetic grid is not enough.

## Provenance and CI

### Required provenance block

Every assessment, validation row, and report should carry:

```json
{
  "code_commit": "...",
  "working_tree_dirty": true,
  "scorer_version": "...",
  "region_config_sha256": "...",
  "epoch_cube_sha256": "...",
  "tree_index_sha256": "...",
  "tree_index_status": "PRESENT|MISSING",
  "heat_mode": "NIGHT_MODIS_LST",
  "design_storm_mm": 214.0,
  "hsg": "B|C|D",
  "weights": {"flood": 0.3, "heat": 0.3, "green": 0.2, "carbon": 0.2},
  "generated_at_utc": "..."
}
```

If a hash is unavailable, set it to `null` and say why. Do not invent it.

### CI freshness test

Add a CI test that:

- Parses every committed assessment/validation JSON/CSV that claims to be current.
- Recomputes the relevant hashes from the current config/cube.
- Asserts `heat_mode == "NIGHT_MODIS_LST"`.
- Asserts `design_storm_mm == 214.0` for Pune.
- Re-runs the saved inputs through the scorer and compares to the saved scores within `1e-6`.
- Fails on drift, with a message naming the stale artifact and the regeneration command.

If adding GitHub Actions is not appropriate, add a runnable Python script `ml_pipeline/data/check_provenance.py` and document it in the README. A script that is never run is not a CI check.

### Large artifacts

- Add a small `tests/fixtures/ward12_sample_trees.sqlite` (under 400 KB) so tests can run offline without the 52 MB index.
- Document how the full tree index is published or rebuilt.
- Add `ml_pipeline/research/MANIFEST.json` entries or a separate `artifacts.lock.json` with source, size, checksum, retrieval date, and licence.
- Add a data dictionary for `epoch_cube.json`: each field, units, source, reducer, scale, date range, cloud mask, QA bits, and per-cell sample count.

## Tests

Add tests in `engine/tests/test_engine.py` and/or a new test:

- A config with `design_storm_status: PROVISIONAL_UNVERIFIED` is rejected in strict mode.
- A config with `cn_table_status: UNSOURCED` is rejected or warned.
- A valid accepted config scores.
- A synthetic region is labelled synthetic, not “any region.”
- A stale artifact fails the provenance check.
- A current artifact passes.

Run:

```bash
.venv/bin/python engine/tests/test_engine.py
.venv/bin/python -m pytest ml_pipeline/tests -q
```

## Do not

- Do not change scoring formulas or measured constants.
- Do not claim a second city works unless you actually built one.
- Do not fabricate a tree index or hashes.
- Do not edit the report or PDF; give Session 6 the language.
- Do not silently turn warnings into passes.

## Acceptance

- `validate_config` has a strict mode and a clear error for provisional constants.
- A real assessment cannot silently use a provisional storm or unsourced bands.
- Provenance is emitted and checked.
- A stale artifact fails.
- A micro-fixture lets tests run without the full tree index.
- The “any region” claim is qualified.

## Handoff

Report:

- The new region contract and strict-mode behaviour.
- Which constants are now gated.
- The provenance fields and CI command.
- What remains unproven for any-region reuse.
- What Session 6 should say in the report.
