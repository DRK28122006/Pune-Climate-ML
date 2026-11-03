# 0013 — Report and artifact status (Session 12)

**Date:** 2026-11-03  
**Session:** 12  
**Status:** Accepted

## What was regenerated

| Artifact | Method | Status |
|---|---|---|
| `docs/example_assessment.json` | `ml_pipeline/cli.py assess --ward 12 --built-up 3000 --plot 8000 --demo-materials` | Current — real scorer output |
| `docs/Dishadharti_ML_Report.pdf` | `python docs/make_report.py` (reportlab 5.1.0) | Current — regenerated from `ward_validation.json` |
| `ml_pipeline/data/ward_validation.json` | Session 11 (regenerated) | Current |
| `ml_pipeline/data/site_validation.json` | Session 11 (regenerated) | Current |

## What remains stale and why

| Artifact | Reason |
|---|---|
| `ml_pipeline/data/stress/*.json` (29 files) | Contain fabricated `mean_slope_deg: 3.0`, fake drainage (`150`/`200`), old census total (`4,009,624`). Marked stale via `STALE.md`. |
| `ml_pipeline/data/e2e/*.json` (16 files) | Same fabricated values plus `complete: true` with green `95.5` (never validated). Marked stale via `STALE.md`. |

## What changed in the report

| Claim | Old value | New value | Source |
|---|---|---|---|
| Flood range | 14.5–53.3 | 33.9–53.3 | `ward_validation.json` sub_scores |
| Heat spread | 0.8–99.0 | 32.8–98.1 | `ward_validation.json` sub_scores |
| Green range | 62–100 | 73.2–93.0 | `ward_validation.json` sub_scores (now scored) |
| Carbon | Flat across wards | Flat at 28.2 (wards); varies 26.3–84.5 (sites) | `ward_validation.json` + `site_validation.json` |
| Test counts | "48/48, 8/8, e2e" | "83 passed, 1 skipped (root pytest)" | `pytest -q` run 2026-11-03 |
| Slope | 3° (fabricated) | Unavailable (cube has no `mean_slope_deg`) | `epoch_cube.json` |
| Drainage | Fake 38.2 m | Real 38.2 m (storm drain layer, 141,341 drains) | `reference_layers.sqlite` |

## What cannot be claimed yet

- Green validation against GEDI/field data (no independent validation executed)
- Drainage validation against PMC waterlogging hotspots (parks/nallas KMLs missing)
- Slope validation (cube has no slope band; `ee` not installed)
- Fluvial flood modelling (not implemented; `NOT_MODELLED`)
- Any-region portability (scaffolded, not proven)
- Full e2e success (stress/e2e artifacts stale)

## Report generator

`docs/make_report.py` no longer depends on `/tmp/ward_*.json`. It reads `ml_pipeline/data/ward_validation.json` directly and fails with a clear message if the file is missing.

## PDF status

Regenerated 2026-11-03 from `docs/make_report.py` using reportlab 5.1.0. Size: 851,446 bytes. Every number is sourced from `ward_validation.json` or the repo's measured constants.

## MANIFEST.json

Updated: census-raw (present), tree-index (local-only), reference-layers (present), ward-validation (current), site-validation (current), report-pdf (current), example-assessment (current). All stress/e2e entries marked stale.
