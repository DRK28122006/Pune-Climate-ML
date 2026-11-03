# Handoff — Session 10 (Data Restoration and Dependency Gate)

**Date:** 2026-11-02  
**Status:** COMPLETED (partial — see blockers below)  
**Next session:** Session 11 (validation harness truth pass)

## What was restored

| Asset | Path | Status | Size | Trees / rows |
|---|---|---|---|---|
| Raw tree census | `ml_pipeline/data/census/` | PRESENT (17 CSV parts) | ~1.2 GB | 10,147,553 rows read |
| Tree index | `ml_pipeline/data/tree_index.sqlite` | PRESENT | 1,129,594,880 bytes | 4,009,623 unique tree IDs |
| Reference layers | `ml_pipeline/data/reference_layers.sqlite` | PRESENT (partial) | 21,663,744 bytes | wards=41, storm_drains=141,341 |
| Epoch cube | `ml_pipeline/data/epoch_cube.json` | PRESENT (unchanged) | 522,251 bytes | 864 cells, no `mean_slope_deg` |

SHA256 hashes are recorded in `ml_pipeline/research/05_sources/DATA_STATUS.md`.

No large data files were committed. `tree_index.sqlite`, `reference_layers.sqlite`, and `ml_pipeline/data/census/` are all gitignored.

## What was already in place (verified, not rebuilt)

- `ml_pipeline/data/census/` — 17 parts already downloaded from PMC CKAN `f00d83b8-c70f-4fff-9ac7-9a6ab4255edf`
- `ml_pipeline/data/tree_index.sqlite` — already built with spatial R-tree index
- `ml_pipeline/data/reference_layers.sqlite` — already rebuilt (was 0 bytes before this session, now 21 MB)

## What remains missing / blocked

1. **`ml_pipeline/reference/pune_parks.kml`** — NOT FOUND anywhere in the repo. Parks table is empty (0 rows). Park attribution and relocation checks cannot be validated. Do not fabricate geometry.
2. **`ml_pipeline/reference/pune_nallas.kml`** — NOT FOUND. Nallas table is empty (0 rows).
3. **`ml_pipeline/reference/pune_rivers.kml`** — NOT FOUND. Rivers table is empty (0 rows).
4. **Slope band** — `mean_slope_deg` is absent from all 864 cube cells. The `ee` (Google Earth Engine) Python package is NOT installed (`ModuleNotFoundError`). Cube cannot be rebuilt without GEE auth + `ee`. Recorded as `slope_status: MISSING` in DATA_STATUS.md.

## Test results

| Test | Result |
|---|---|
| `ml_pipeline/tests/test_data_integrity.py` | 6/6 PASS |
| `ml_pipeline/tests/test_e2e_ward12.py` | 5 FAILURES (see below) |

### test_e2e_ward12.py failures

These are **not** missing-file skips. They are real mismatches between the test's expected ranges and the current full-census data / night-LST scoring path:

1. Tree count: 69,982 inside Ward 12 ring; test expects 38,000–52,000. `ward-profile --ward 12` independently confirms 69,980.
2. Mature count: 29,445; test expects 14,000–24,000.
3. Rare count: 2,220; test expects 800–2,000.
4. Heat scored: `None` (cube has night LST values but the test passes day LST values to the scorer).
5. All four factors: `complete=False`, `missing=['heat']`.

The test's expected figures (44,468 trees / 18,823 mature / 1,266 rare) appear calibrated against the earlier partial census (ptc_part1.csv only). The full 17-part census yields ~69,980 trees in Ward 12.

## Session 11 readiness

| Factor | Ready? | Notes |
|---|---|---|
| Green | YES | Tree index present (4,009,623 trees) |
| Heat | YES | Cube has night LST for all 864 cells |
| Flood | PARTIAL | Storm drains present; parks/nallas/rivers tables empty (KMLs missing) |
| Slope | NO | `mean_slope_deg` absent; `ee` not installed |

## Files created/modified in this session

- **Created:** `ml_pipeline/research/05_sources/DATA_STATUS.md` (full asset inventory, hashes, blockers)
- **Not committed:** No large data files committed
- **Not modified:** No scoring, report, validation harness, or frontend/backend files touched

## Handoff to Session 11

Session 11 should:

1. Fix `validate_wards.py` / `validate_sites.py` for night LST fields, true area weighting, unknown canopy flags.
2. Fix `test_data_integrity.py` / `test_e2e_ward12.py` as needed (test expectations may need updating for full census; night LST values should be passed to scorer).
3. Regenerate `ward_validation.json` and `site_validation.json` with provenance.
4. Confirm whether green can now be scored (tree index exists).
5. Confirm drainage is limited (parks/nallas KMLs still missing).

## Source / licence notes

- Census: PMC Tree Census 2019 via data.opencity.in CKAN package `f00d83b8-c70f-4fff-9ac7-9a6ab4255edf`. Downloaded 17 parts; no fabrication.
- Ward boundaries: `pmc_wards_2025.kml` (pre-existing in `ml_pipeline/research/05_sources/kml/`).
- Stormwater drains: `pmc_stormwater_drains.kmz` (pre-existing in `ml_pipeline/reference/`).
- Parks/nallas/rivers KMLs: not available in this checkout; no source URL recorded. Must be obtained before those layers can be populated.
