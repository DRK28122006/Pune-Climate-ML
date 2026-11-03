# Data inventory

## Present (tracked)
- `docs/Dishadharti_ML_Report.pdf` — technical report (regenerated Session 12).
- `README.md` — project README.
- `ml_pipeline/data/epoch_cube.json` — 864 cells, 2024 epoch, ~512 KB. No slope band.
- `ml_pipeline/data/imd_pune_annual_max.csv` — 124 annual 1-day maxima, 1901–2024.
- `ml_pipeline/data/census_ward_profile.csv` — ward-level census aggregate.
- `ml_pipeline/data/gedi_ward_rh95.csv` — GEDI ward RH95 check.
- `ml_pipeline/data/ward_validation.json` — **current** (6 wards, night LST, true area weighting, Session 11).
- `ml_pipeline/data/site_validation.json` — **current** (8 sites, night LST, varied carbon BOQ, Session 11).
- `ml_pipeline/data/flood_layers.sqlite` — **new, derived, gitignored** (172 OSM waterways; Session 14, PROXIMITY_ONLY). Rebuild from the tracked raw snapshot with `ml_pipeline/data/build_flood_layers.py`.
- `ml_pipeline/data/flood_layers_raw.json` — **new, tracked** (377 KB Overpass snapshot, ODbL-1.0).
- `ml_pipeline/data/heat_crosscheck_2024.csv` — **new, tracked** (41 wards, 2024 night air temperature; Session 14, INCONCLUSIVE).
- `ml_pipeline/data/heat_crosscheck_2024.json` — **new, tracked** (full 41-row evidence with `lst_night_mean_c`; verify with `ml_pipeline/data/heat_crosscheck.py`).
- `ml_pipeline/data/slope_band.json` — **new, derived, evidence only** (864 cells; p95 4.9895°; gate FAIL; slope disabled).
- `ml_pipeline/data/stress/` — 29 ward stress outputs (**stale** — see STALE.md).
- `ml_pipeline/data/e2e/` — 16 E2E assessment outputs (**stale** — see STALE.md).
- `ml_pipeline/config/regions/pune.json`, `materials.json`, `species.json`.
- `ml_pipeline/reference/pmc_stormwater_drains.kmz` — 22 MB, tracked.
- `docs/assets/*.png` — 6 figures.
- `ml_pipeline/research/05_sources/kml/pmc_wards_2025.kml`, `WARD12_TEST_SITE.kml` — copied from `/home/mesh/Pictures/`.
- `docs/example_assessment.json` — **current** (regenerated Session 12, real scorer).

## External (outside repo, not committed)
- `/home/mesh/Pictures/pmc_wards_2025.kml` — source of copied KML.
- `/home/mesh/Pictures/WARD12_TEST_SITE.kml` — source of copied KML.
- `ml_pipeline/data/census/` — raw tree census, ~1.2 GB, gitignored.
- `ml_pipeline/data/tree_index.sqlite` — 4,009,623 trees, 1.1 GB, gitignored.
- `ml_pipeline/data/reference_layers.sqlite` — 41 wards + 141,341 storm drains, 21 MB, gitignored.

## Missing (rebuild commands)
- `ml_pipeline/reference/pune_parks.kml` — missing (parks table empty).
- `ml_pipeline/reference/pune_nallas.kml` — missing (nallas table empty).
- `ml_pipeline/reference/pune_rivers.kml` — missing (rivers table empty).
- Regulatory flood line (PMC/WRD blue-red) — missing (UNAVAILABLE; manual request).
- `mean_slope_deg` in `epoch_cube.json` — missing; `slope_band.json` is evidence only, the gate failed (0/6 wards), and slope remains disabled.

## Tracked status
- See `MANIFEST.json` for per-asset bytes, sha256, source, licence, tracked flag, status, notes.
