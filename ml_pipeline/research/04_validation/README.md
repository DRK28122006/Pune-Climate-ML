# Validation artifacts

## Present (stale)
- `ml_pipeline/data/ward_validation.json` — 6 wards only, uses day LST and a 2.0 °C span. Stale (C5).
- `ml_pipeline/data/site_validation.json` — stale.
- `ml_pipeline/data/stress/` — 29 ward-level stress outputs.
- `ml_pipeline/data/e2e/` — 16 E2E assessment outputs including `e2e_summary.json`.

## Rules
- Do not regenerate validation JSONs in this session (Session 1 is indexing/provenance only).
- Do not hand-edit; regeneration must come from scripts (`validate_wards.py`, `validate_sites.py`, `e2e_verify.py`).
- Validation is circular/centroid-sampled per the scientific review (C5); flagged for a later session.

## Artifacts
- `04_validation/artifacts/` reserved for future regenerated validation outputs (none added here).
