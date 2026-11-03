# Data Status — Session 10 (Data Restoration and Dependency Gate)

**Date:** 2026-11-02  
**Session:** 10  
**Status:** PARTIAL — census + tree index restored; reference layers partially built; slope and parks/nallas blocked.

## Asset inventory

| Asset | Path | Status | Size | SHA256 | Source | Committed? |
|---|---|---|---|---|---|---|
| Raw tree census (17 parts) | `ml_pipeline/data/census/` | PRESENT | ~1.2 GB | — | PMC Tree Census 2019 / data.opencity.in CKAN `f00d83b8-c70f-4fff-9ac7-9a6ab4255edf` | NO (gitignored) |
| Tree index | `ml_pipeline/data/tree_index.sqlite` | PRESENT | 1,129,594,880 bytes | `2a1bc91875dbfc5a0825cd1a9e3df841a72b56a4981dbdf47e32113bd6ea93e4` | Built from 17 census parts via `ml_pipeline/cli.py build-data` | NO (gitignored `*.sqlite`) |
| Reference layers | `ml_pipeline/data/reference_layers.sqlite` | PRESENT (partial) | 21,663,744 bytes | `708afa33746552c5e9e06b33b5000ed4d57c25a4dd903eda1ad2ee65cdc945a7` | Built via `ml_pipeline/cli.py build-data` | NO (gitignored `*.sqlite`) |
| Epoch cube | `ml_pipeline/data/epoch_cube.json` | PRESENT | 522,251 bytes | `3a88ae667bad0e0ec3c7888a632a2c4cf70fdee148b5288920dce42d3734bad6` | Pre-existing | N/A |
| Stormwater KMZ | `ml_pipeline/reference/pmc_stormwater_drains.kmz` | PRESENT | 22,184,109 bytes | `46dc617d4aa9c703f093ca555c7897389a9131f213eca80e4c29dbff4db4f9d4` | Pre-existing | N/A |
| Ward KML | `ml_pipeline/research/05_sources/kml/pmc_wards_2025.kml` | PRESENT | 191,370 bytes | — | Pre-existing | N/A |
| Ward 12 test KML | `ml_pipeline/research/05_sources/kml/WARD12_TEST_SITE.kml` | PRESENT | 8,887 bytes | — | Pre-existing | N/A |
| Parks KML | `ml_pipeline/reference/pune_parks.kml` | MISSING | — | — | Not found in repo; no URL recorded | N/A |
| Nallas KML | `ml_pipeline/reference/pune_nallas.kml` | MISSING | — | — | Not found in repo; no URL recorded | N/A |
| Rivers KML | `ml_pipeline/reference/pune_rivers.kml` | MISSING | — | — | Not found in repo; no URL recorded | N/A |

## Reference layer contents

| Table | Count | Notes |
|---|---:|---|
| wards | 41 | ward_no 1..41 from `qwr` attribute; total area ~485 km² |
| parks | 0 | `pune_parks.kml` missing — table empty |
| storm_drains | 141,341 | From `pmc_stormwater_drains.kmz` |
| nallas | 0 | `pune_nallas.kml` missing — table empty |
| rivers | 0 | `pune_rivers.kml` missing — table empty |

A 0-byte `reference_layers.sqlite` is no longer present — the file was rebuilt. However, parks/nallas/rivers are empty because their source KMLs are not in the repository.

## Tree index contents

| Check | Value |
|---|---|
| Unique tree IDs | 4,009,623 |
| Total rows read from census | 10,147,553 |
| Spatial index (R-tree) | Present (`tree_rtree`) |
| Census year | 2019 |
| Ward coverage | Ward assigned by point-in-polygon (`census_ward` is the census' own 3..63 id, NOT 1..41) |
| Ward 12 tree count | 69,980 (via `ward-profile --ward 12` / point-in-polygon against Ward 12 ring) |

## Slope band

| Check | Value |
|---|---|
| `mean_slope_deg` in cube | 0 / 864 cells (missing) |
| `ee` (Google Earth Engine) module | NOT installed — `ModuleNotFoundError: No module named 'ee'` |
| Cube rebuild possible | NO — GEE authentication + `ee` package required |
| Action | Do **not** rebuild cube. Record `slope_status: MISSING`. |

## Commands used

```bash
# Census already downloaded (17 parts) into ml_pipeline/data/census/
# Source: https://data.opencity.in/api/3/action/package_show?id=f00d83b8-c70f-4fff-9ac7-9a6ab4255edf

# Tree index + reference layers built
python -m ml_pipeline.cli build-data

# Or individually:
# python -m ml_pipeline.data.reference_layers --build
```

## Test results

| Test | Result | Details |
|---|---|---|
| `test_data_integrity.py` | 6/6 PASS | Ward numbering, ward coverage, tree index row count, botanical name coverage |
| `test_e2e_ward12.py` | 5 FAILURES | See below |

### test_e2e_ward12.py failures

1. **Tree count**: 69,982 trees inside Ward 12 ring; test expects 38,000–52,000. `ward-profile --ward 12` independently confirms 69,980 / 29,445 mature / 2,220 rare. The test's expected ranges appear to be calibrated against the earlier partial census (ptc_part1.csv only, ~6% of the city), not the full 17-part census now loaded.
2. **Mature count**: 29,445; test expects 14,000–24,000.
3. **Rare count**: 2,220; test expects 800–2,000.
4. **Heat scored**: `heat=None`; test expects a numeric heat score. The cube contains `lst_night_mean_c` (22.49 °C) and `lst_night_reference_c` (22.48 °C) for Ward 12, but the e2e test passes day `lst_mean_c`/`lst_reference_c` to the scorer, not the night pair the scorer requires.
5. **All four factors**: `complete=False`, `missing=['heat']` — consequential to failure #4.

None of these are missing-file skips; they are real code/data mismatches between the test's expectations and the current full-census data / night-LST scoring path.

## Remaining blockers

1. **`pune_parks.kml` missing** — parks table empty (0). Park attribution and relocation checks cannot be validated until this KML is obtained. Do not fabricate geometry.
2. **`pune_nallas.kml` missing** — nallas table empty (0). Nalla proximity checks cannot be validated until this KML is obtained.
3. **`pune_rivers.kml` missing** — rivers table empty (0).
4. **Slope band missing** — `ee` package not installed; cube cannot be rebuilt. Flood scoring continues without slope multiplier.

## Session 11 readiness

| Factor | Can Session 11 validate? | Notes |
|---|---|---|
| Green | YES | Tree index present with 4,009,623 trees |
| Heat | YES | Cube has night LST for all 864 cells |
| Flood | PARTIAL | Storm drains present (141,341); parks/nallas/rivers missing (0 each) |
| Slope | NO | `mean_slope_deg` absent from cube; `ee` not installed |

## Next command

Session 11: fix validation harness (night fields, area weighting, unknown canopy flags), regenerate validation JSONs, then re-run `test_e2e_ward12.py` to confirm whether its expectations need updating for the full census.
