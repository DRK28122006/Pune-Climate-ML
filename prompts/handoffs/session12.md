# Handoff — Session 12 (Artifact and Report Regeneration)

**Date:** 2026-11-03  
**Status:** COMPLETED  
**Next session:** Session 13 (final ML audit and engine sign-off)

## Artifacts regenerated

| Artifact | Method | Status |
|---|---|---|
| `docs/example_assessment.json` | `ml_pipeline/cli.py assess --ward 12 --built-up 3000 --plot 8000 --demo-materials` | Current — real scorer output |
| `docs/Dishadharti_ML_Report.pdf` | `python docs/make_report.py` (reportlab 5.1.0) | Current — regenerated from `ward_validation.json` |
| `ml_pipeline/data/ward_validation.json` | Session 11 (regenerated) | Current |
| `ml_pipeline/data/site_validation.json` | Session 11 (regenerated) | Current |

## Artifacts marked stale

| Artifact | Reason |
|---|---|
| `ml_pipeline/data/stress/*.json` (29 files) | Fabricated `mean_slope_deg: 3.0`, fake drainage, old census total. Marked via `STALE.md`. |
| `ml_pipeline/data/e2e/*.json` (16 files) | Same fabricated values plus `complete: true` with green `95.5`. Marked via `STALE.md`. |

## PDF status

- Regenerated: 2026-11-03
- Command: `python docs/make_report.py`
- Size: 851,446 bytes
- Source: `ml_pipeline/data/ward_validation.json` (no longer depends on `/tmp/ward_*.json`)
- reportlab: 5.1.0 (installed system-wide)

## README/manifest changes

### README.md
- Heat range: 0.8–99.0 → 32.8–98.1 (night LST only)
- Green range: 62–100 → 73.2–93.0 (now scored with real census)
- Carbon: "flat by design" → "flat across wards (identical BOQ); varies 26.3–84.5 across sites"

### MANIFEST.json
- `census-raw`: missing → present
- `tree-index`: missing → local-only (4,009,623 trees, 1.1 GB)
- `reference-layers`: missing → present (41 wards, 141,341 drains)
- `ward-validation`: stale → current
- `site-validation`: stale → current
- `report-pdf`: current (regenerated)
- `example-assessment`: added as current
- All `stress-*` and `e2e-*` entries: current → stale
- Added `stress-stale-md` and `e2e-stale-md` entries

### 01_data_inventory.md
- Updated to reflect current/stale/missing status of all assets

## Claims that still cannot be made

- Green validation against GEDI/field data (no independent validation executed)
- Drainage validation against PMC waterlogging hotspots (parks/nallas KMLs missing)
- Slope validation (cube has no slope band; `ee` not installed)
- Fluvial flood modelling (not implemented; `NOT_MODELLED`)
- Any-region portability (scaffolded, not proven)
- Full e2e success (stress/e2e artifacts stale)

## What Session 13 must verify

1. Full test matrix (unit, narrative, data integrity, e2e, engine, provenance)
2. Partial-evidence contract (0/4 through 4/4 tiers)
3. Data and provenance (tree index, reference layers, validation JSONs)
4. Report and README (PDF regenerated, ranges match artifacts)
5. Engine handoff (strict mode, partial propagation)
6. Write `ML_SIGNOFF.md` with verdict
7. Final diff review
