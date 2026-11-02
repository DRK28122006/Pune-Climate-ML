# Data inventory

## Present (tracked)
- `docs/Dishadharti_ML_Report.pdf` — technical report (do not edit).
- `README.md` — project README.
- `ml_pipeline/data/epoch_cube.json` — 864 cells, 2024 epoch, ~512 KB.
- `ml_pipeline/data/imd_pune_annual_max.csv` — 124 annual 1-day maxima, 1901–2024.
- `ml_pipeline/data/census_ward_profile.csv` — ward-level census aggregate.
- `ml_pipeline/data/gedi_ward_rh95.csv` — GEDI ward RH95 check.
- `ml_pipeline/data/ward_validation.json` — **stale** (6 wards, day LST, 2.0 °C span).
- `ml_pipeline/data/site_validation.json` — **stale**.
- `ml_pipeline/data/stress/` — 29 ward stress outputs.
- `ml_pipeline/data/e2e/` — 16 E2E assessment outputs.
- `ml_pipeline/config/regions/pune.json`, `materials.json`, `species.json`.
- `ml_pipeline/reference/pmc_stormwater_drains.kmz` — 22 MB, tracked.
- `docs/assets/*.png` — 6 figures.
- `ml_pipeline/research/05_sources/kml/pmc_wards_2025.kml`, `WARD12_TEST_SITE.kml` — copied from `/home/mesh/Pictures/`.

## External (outside repo)
- `/home/mesh/Pictures/pmc_wards_2025.kml` — source of copied KML.
- `/home/mesh/Pictures/WARD12_TEST_SITE.kml` — source of copied KML.

## Missing (rebuild commands)
- `ml_pipeline/data/census/` — raw tree census, ~1.2 GB. Rebuild: `python ml_pipeline/data/fetch_census_parts.py --all` (requires approval).
- `ml_pipeline/data/tree_index.sqlite` — ~52 MB. Rebuild: `python ml_pipeline/data/fetch_census_parts.py --all` then `python -m ml_pipeline.cli build-data`.
- `ml_pipeline/data/reference_layers.sqlite` — parks/nallas/drains. Rebuild: `python ml_pipeline/data/reference_layers.py` (after KML/KMZ available).
- `ml_pipeline/reference/pune_parks.kml` — missing.
- `ml_pipeline/reference/pune_nallas.kml` — missing.

## Stale
- `ward_validation.json`, `site_validation.json` (day LST, 2.0 °C span, 6 wards).
- Day UHI span derivation (2.0 °C) vs live cube.

## Tracked status
- See `MANIFEST.json` for per-asset bytes, sha256, source, licence, tracked flag, status, notes.
