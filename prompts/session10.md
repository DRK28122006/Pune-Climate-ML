# Session 10 — Data restoration and dependency gate

**Suggested model:** Beam Free (1M context helps with large build logs and multi-step data checks)  
**Dependencies:** Session 9 merged. Run before Session 11.  
**Owns:** `ml_pipeline/data/census/`, `ml_pipeline/data/tree_index.sqlite` (build locally, do not commit), `ml_pipeline/data/reference_layers.sqlite` (build locally, do not commit), acquisition of `ml_pipeline/reference/pune_parks.kml` and `pune_nallas.kml`, and `ml_pipeline/data/epoch_cube.json` only if a real GEE rebuild is possible.  
**Do not touch:** scoring code, report code, validation harness, validation JSONs, `frontend/`, `backend/`, measured constants.

Read `prompts/00_context.md` and `prompts/00_review_findings.md` first.

## Mission

Restore the real data needed to validate green cover, drainage, and slope. If a dataset cannot be restored, stop and report the exact missing path and rebuild command. Do not fabricate a substitute.

This session is a **data gate**, not a scoring session. Do not “fix” validation results by changing the scorer.

## Current missing state

| Asset | Path | Current state |
|---|---|---|
| Raw tree census | `ml_pipeline/data/census/` | Missing, about 1.2 GB |
| Tree index | `ml_pipeline/data/tree_index.sqlite` | Missing |
| Reference layers | `ml_pipeline/data/reference_layers.sqlite` | Present but 0 bytes; not a database |
| Parks KML | `ml_pipeline/reference/pune_parks.kml` | Missing |
| Nallas KML | `ml_pipeline/reference/pune_nallas.kml` | Missing |
| Slope band | `ml_pipeline/data/epoch_cube.json` | No `mean_slope_deg` |
| Stormwater KMZ | `ml_pipeline/reference/pmc_stormwater_drains.kmz` | Present, about 22 MB |

The copied ward KMLs exist at:

```text
ml_pipeline/research/05_sources/kml/pmc_wards_2025.kml
ml_pipeline/research/05_sources/kml/WARD12_TEST_SITE.kml
```

## 1. Restore the census and tree index

The census download is large and may need explicit approval. Check whether `ml_pipeline/data/fetch_census_parts.py` supports `--all` and whether network access is available.

Commands to try, adjusting for the actual script interface:

```bash
python ml_pipeline/data/fetch_census_parts.py --all
python -m ml_pipeline.cli build-data
```

If `build-data` also rebuilds reference layers and fails because the parks/nallas KMLs are missing, build the tree index directly with the tree-index builder rather than skipping the tree index.

Required checks:

- `ml_pipeline/data/tree_index.sqlite` exists and is a valid SQLite database.
- The `trees` table exists.
- The number of unique tree ids is `4,009,623`.
- The index covers all 41 wards.
- A Ward 12 query returns a plausible count; the e2e test expects roughly `38,000–52,000` trees.
- The index is spatially indexed; a bbox query is fast enough for the e2e test.
- Record the actual file size and sha256.

Do **not** commit `ml_pipeline/data/census/` or `tree_index.sqlite`.

## 2. Restore reference layers

The pipeline needs:

- `ml_pipeline/reference/pune_parks.kml`
- `ml_pipeline/reference/pune_nallas.kml`
- `ml_pipeline/reference/pmc_stormwater_drains.kmz`

If the parks/nallas KMLs are not in the repo, search the existing repo and known external locations first. If they must be downloaded, document the source, date, licence, and checksum. Do not invent geometry and do not copy an unrelated KML just to make the build pass.

Then build:

```bash
python -m ml_pipeline.cli build-data
```

or call the reference-layer builder directly if `build-data` is partially blocked.

Required checks:

- `reference_layers.sqlite` is non-zero and a valid SQLite database.
- The expected tables exist, including `wards`, `parks`, and `storm_drains`.
- `drainage_context()` returns a real distance or a documented `None`; it must not fail with `no such table`.
- Ward polygons are loaded for all 41 wards.
- Park attribution and ward coverage checks pass.

A 0-byte `reference_layers.sqlite` is not a restored database. If it cannot be rebuilt, leave a clear status file and report the block; do not treat it as present.

## 3. Slope band

The current cube has no `mean_slope_deg`. `ml_pipeline/data/build_cube.py` contains an uncommitted slope fix that adds `terrain_slope()` and `mean_slope_deg`.

Only rebuild the cube if Google Earth Engine authentication and quota are available. A rebuild changes `epoch_cube.json`, which invalidates all validation provenance hashes; that is acceptable only before Session 11.

```bash
python -m ml_pipeline.data.build_cube --epoch 2024
```

Required checks:

- Every cell that has land cover also has a finite `mean_slope_deg`, or the output explicitly records why slope is missing.
- The cube still has 864 cells and a valid land-cover partition.
- Do not invent a 3° slope.
- Do not change the 2024 epoch or measured land-cover values.

If GEE is unavailable:

- Do **not** rebuild the cube.
- Record `slope_status: MISSING` in the data status file.
- Tell Session 11 that flood must continue to report `slope_available: false` and use no slope multiplier.

## 4. Re-run data checks

Run the checks that require the restored data:

```bash
python ml_pipeline/tests/test_data_integrity.py
python ml_pipeline/tests/test_e2e_ward12.py
python ml_pipeline/data/check_provenance.py
```

Expected:

- `test_data_integrity.py` no longer skips; it should pass its ward, park, and tree-index checks.
- `test_e2e_ward12.py` no longer fails on a missing index; it should pass the real Ward 12 tree query and canopy ledger checks.
- `check_provenance.py` may fail until Session 11 regenerates the validation artifacts. Record that expected failure; do not hand-edit the provenance.

## 5. Write the data status record

Create `ml_pipeline/research/05_sources/DATA_STATUS.md` with:

- Each asset: present/missing/stale.
- Exact path, size, sha256, and source.
- Exact commands used.
- Whether the file is committed or local-only.
- The tree count and Ward 12 sanity count.
- The reference-layer table list.
- Whether slope is present, missing, or rebuilt.
- Remaining blockers and the next command to run.

Update `ml_pipeline/research/01_data_inventory.md` only if the status changed in a way that is already verified. Do not mark an asset present until the file exists and the check passes.

## Do not

- Do not fabricate census rows, tree coordinates, canopy, ward polygons, parks, nallas, drains, or slope.
- Do not copy the 1.2 GB census or the tree index into git.
- Do not edit scoring, report, validation JSONs, or the PDF.
- Do not run `git clean` or delete files you did not create.
- Do not claim a download succeeded unless the checksum and row count prove it.

## Acceptance

- `tree_index.sqlite` exists, is valid, and contains `4,009,623` unique trees.
- `reference_layers.sqlite` is valid and contains the expected tables, or the exact missing KMLs and rebuild command are reported.
- `test_data_integrity.py` passes, or every skipped check has a documented missing dependency.
- `test_e2e_ward12.py` passes when the tree index exists; if it still fails, the failure is a real code/data defect, not a missing-file skip.
- Slope is either present in the cube or explicitly recorded as missing.
- `DATA_STATUS.md` lists every asset and blocker.
- No large data file is committed.

## Handoff

Write `prompts/handoffs/session10.md` with:

- What was restored, with sizes and hashes.
- What remains missing.
- Whether the cube was rebuilt.
- Exact test commands and outputs.
- Whether Session 11 can validate green, drainage, and slope.
- Any source/licence notes for newly acquired KMLs.
