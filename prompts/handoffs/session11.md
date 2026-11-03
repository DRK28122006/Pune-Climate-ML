# Handoff — Session 11 (Validation Harness Truth Pass)

**Date:** 2026-11-02  
**Status:** COMPLETED  
**Next session:** Session 12 (artifact and report regeneration)

## Issues fixed

### 1. Night/day heat reporting
- `validate_wards.py`: Row dict now has `lst_night_mean_c`, `lst_night_reference_c`, `night_uhi_delta_c` as primary heat fields. Day values renamed to `legacy_day_lst_c`, `legacy_day_reference_c`, `legacy_day_uhi_c`. Display table uses night fields.
- `validate_sites.py`: Same fix. `lst`/`ref`/`uhi` day fields replaced with night fields as primary, day as legacy.
- Both JSONs now report `heat_mode: NIGHT_MODIS_LST`.

### 2. Area weighting
- `validate_wards.py` `_cells_for_ward`: Replaced centroid-membership + `selected_cells * cell_area / ward_area` with true polygon-cell intersection area in EPSG:32643 using shapely + pyproj. Coverage is now `sum(intersection_area) / ward_area`. Indicators are area-weighted by intersection fraction.

### 3. Unknown canopy and census flags
- `validate_wards.py`: `trees_reliable` defaults to `False` when ward profile unavailable (was `True`). `trees_loaded` and `tree_canopy_pct` set to `None` when profile unavailable.
- `validate_sites.py`: `census_reliable` no longer true just because trees were found in the site. `trees` set to `None` when census unreliable. Zero ledger only created when coverage is complete AND site is genuinely empty.

### 4. Carbon validation
- `validate_sites.py`: Koregaon Park green site now uses PPC cement + recycled-content steel (lower EF) instead of OPC + reinforcement. Carbon now varies: Koregaon Park 26.3 vs 84.5 elsewhere.

### 5. Test story
- `day_signal_test.py`: Wrapped `import ee` in try/except with `pytest.importorskip("ee")` fallback and graceful skip when run as script.
- `test_e2e_ward12.py`: Added SKIP (return 0) when tree index or Ward 12 KML missing. Fixed night LST (passes `lst_night_mean_c`/`lst_night_reference_c`). Removed invented 3.1° slope default (now `None`). Updated expected ranges for full census (69,982 trees / 29,445 mature / 2,220 rare).

### 6. Provenance
- Both `validate_wards.py` and `validate_sites.py` `_provenance()`: Added `reference_layers_sha256`, `reference_layers_status`, `slope_status`.

### 7. Validation README
- `ml_pipeline/research/04_validation/README.md`: Updated with current test status, available/missing data, regeneration commands, stale artifact notes.

## Data available in this session

| Data | Status |
|---|---|
| Tree index (4,009,623 trees) | PRESENT |
| Reference layers (wards + storm drains) | PRESENT |
| Night LST (864 cells) | PRESENT |
| Parks/nallas/rivers KMLs | MISSING (parks=0, nallas=0, rivers=0) |
| Slope band | MISSING (0/864 cells) |

## Green scoring

Green was scored for all 6 wards and 8 sites. Tree index present with complete census.

## New ward/site ranges and completeness

### Ward validation (6 wards, all complete)
- Score range: 30.30 – 55.90 (spread 25.60, PASS)
- All 6 wards scored all 4 factors
- Night UHI range: -0.30 to +0.12

### Site validation (8 sites, all complete)
- Carbon now varies: 26.3 (Koregaon Park, low-carbon BOQ) vs 84.5 (standard RC)
- All 8 sites scored all 4 factors
- Flood, heat, green, carbon all show strong discrimination

## Test results

| Test | Result |
|---|---|
| `pytest -q` (root) | 83 passed, 1 skipped |
| `pytest ml_pipeline/tests -q` | 83 passed |
| `test_data_integrity.py` | 6/6 PASS |
| `test_e2e_ward12.py` | All checks PASS |
| `day_signal_test.py` | SKIP (ee not installed) |
| `check_provenance.py` | PASS (both JSONs) |

## Artifacts current

- `ward_validation.json` — current (regenerated Session 11)
- `site_validation.json` — current (regenerated Session 11)
- `stress/` and `e2e/` — still stale (Session 12)

## What Session 12 needs

1. Regenerate or mark stale `docs/example_assessment.json`, `stress/`, `e2e/`
2. Fix `docs/make_report.py` (remove `/tmp/ward_*.json` dependency)
3. Regenerate PDF or mark stale
4. Update README ranges to match current artifacts
5. Update MANIFEST.json statuses
