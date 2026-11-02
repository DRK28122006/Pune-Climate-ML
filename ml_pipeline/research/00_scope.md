# Scope — research vault

This directory is the single onboarding pack for every future session. It indexes research assets, documents missing/stale/external ones, and records rebuild instructions. It is an indexing/provenance pack, not a modelling session.

## Owns
- `ml_pipeline/research/**`
- `.gitignore` exceptions for small research KMLs and research documents.

## Does not touch
- Scoring code (`ml_pipeline/core/scoring.py`, `canopy.py`, `geometry.py`), validation code, `frontend/`, `backend/`, `engine/`.

## Three questions this pack answers
1. What research assets exist? → `MANIFEST.json`, `01_data_inventory.md`.
2. Which assets are missing, stale, or external? → `MANIFEST.json` status fields, `01_data_inventory.md`.
3. How do I rebuild or verify each one? → `05_sources/*/README.md`, `02_methods/*.md`, `04_validation/README.md`.

## Conventions
- No fabricated data. Missing assets are documented with exact rebuild commands, not created.
- No second copy of `ml_pipeline/data` inside research.
- Checksums in `MANIFEST.json` are computed (sha256) for present files; missing assets carry status `missing` and no checksum.
- Large binaries (census 1.2 GB, tree index 52 MB, KMZ 22 MB) are never committed.
