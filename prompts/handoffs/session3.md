# Handoff — Session 3 (validation and provenance)

**Date:** 2026-11-02
**Branch:** main (committed locally, cfffe11)

## Changed files
- `ml_pipeline/data/validate_wards.py` — area-weighted cells (cell count + coverage), night LST, no 150 m drain default, no 3° slope default, ward rings from copied KML, provenance block, green withheld when census unavailable.
- `ml_pipeline/data/validate_sites.py` — night LST, no 200 m drain default, no 3° slope default, provenance block, drain None handling in output.
- `ml_pipeline/data/factor_breakdown.py` — None-safe formatting, corrected sign-convention reading (sub-scores higher=worse vs climate_score higher=better).
- `ml_pipeline/tests/test_data_integrity.py` — WARD_KML path to research copy; skip gracefully on missing/empty reference DB.
- `ml_pipeline/data/ward_validation.json`, `site_validation.json` — regenerated with provenance.
- `ml_pipeline/research/04_validation/README.md` — independent validation plan, regeneration commands, stale/superseded notes.

## Verified
- `validate_wards` default 6 wards: all scored, spread 30.7, heat mode night, green withheld (tree index missing), provenance present.
- `validate_sites`: 8 sites, flood/heat real discrimination, green withheld, carbon constant (expected given BOQ scaling).
- `factor_breakdown` runs without crash.
- `test_data_integrity`: skip on missing ref DB (exit 0).
- `pytest ml_pipeline/tests`: 65 passed.

## Assets status
- Tree index: MISSING → `tree_index_sha256` null, `tree_index_status: MISSING`. No canopy fabricated.
- Reference layers: empty file (0 bytes) → treated as missing.

## Session 4/6 needs
- Flood/green 0–100 normalisation (Session 4) will change flood veto threshold 50.
- Report ranges (Session 6) must reflect new night-mode, partial (green-withheld) artifacts or document mismatch.
- Regenerate validation after tree index/reference layers are built.
EOF
echo done