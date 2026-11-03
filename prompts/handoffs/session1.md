# Handoff — Session 1 (research vault and data restoration)

**Date:** 2026-11-02
**Branch:** main (committed locally)

## Changed files
- `.gitignore` — exceptions for research KMLs and research dir.
- `ml_pipeline/research/` — full onboarding pack (README, MANIFEST.json, scope, inventory, methods, review copy, validation README, source READMEs, 2 KMLs, decisions README).

## Verified
- `MANIFEST.json` valid JSON, 73 entries; each present asset has sha256/bytes, missing assets status `missing`.
- Tests: `ml_pipeline/tests` — 65 passed; `engine/tests/test_engine.py` — 23/23 passed (via /home/mesh/Projects/GEOai/deepesh-repo/.venv/bin/python).
- `git add -n` confirms KMLs are not ignored.

## Assets status
- Present/current: 64+ (epoch cube, IMD, census ward profile, GEDI, configs, KMZ, figures, stress/e2e, copied KMLs, review draft).
- Stale: `ward_validation.json`, `site_validation.json`.
- Missing: `ml_pipeline/data/census/`, `tree_index.sqlite`, `reference_layers.sqlite`, `pune_parks.kml`, `pune_nallas.kml`.
- External originals preserved at `/home/mesh/Pictures/*.kml`.

## Data restored
- None. Census not downloaded (no approval). Rebuild commands documented in `05_sources/census/README.md`.

## .gitignore exceptions
- `!ml_pipeline/research/` and `!ml_pipeline/research/05_sources/kml/*.kml`. Large binaries remain ignored.

## Session 3 needs
- Restore missing assets (census → tree index; reference layers; parks/nallas KMLs) using documented commands.
- Regenerate stale validation JSONs from scripts (do not hand-edit).
- Decision notes required for any weight/span/band/threshold/legal-label change.
- Note: an untracked `07_decisions/0001-core-safety-policy.md` (Session 2) exists in the working tree and was intentionally left uncommitted.
