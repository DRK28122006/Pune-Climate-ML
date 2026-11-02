# Green method (Pune)

**Code:** `ml_pipeline/core/scoring.py::compute_green`, `ml_pipeline/core/canopy.py` (CanopyLedger), `ml_pipeline/core/geometry.py`
**Config:** `ml_pipeline/config/regions/pune.json` → `green`; `ml_pipeline/config/species.json`
**Inputs:** `ml_pipeline/data/epoch_cube.json` (satellite vegetation), `ml_pipeline/data/tree_index.sqlite` (census canopy, missing), ward KML for point-in-polygon

## Method

- Satellite vegetation already contains tree canopy, so averaging would double-count. Stratify instead:
  - `ground_vegetation = max(0, sat_veg_pct - canopy_cover_pct)`
  - `effective_green = 0.70 * canopy_cover_pct + 0.30 * ground_vegetation`
  - `score = 100 - effective_green`
- The 0.70/0.30 split is house judgment, not a literature coefficient (see config `stratification_note`).
- Census canopy comes from the 2019 PMC tree census via point-in-polygon against the 2025 ward KML (ward ids do not join directly).
- `sat_census_tolerance_pct = 15`: divergence above this lowers confidence.
- Missing satellite or canopy input → score `None` (never zero-filled).

## Canopy ledger (per proposal)

- `CanopyLedger` in `canopy.py` applies tree-by-tree rules: preserve girth >= 90 cm (house policy, not statute), dead/poor condition handling, age-equivalent compensatory counts from girth (2 cm/yr proxy, reported as range).
- Species data from `species.json` (census-derived, audited against full index).

## Rebuild / verify

- Tree index: `python ml_pipeline/data/fetch_census_parts.py --all` then `python -m ml_pipeline.cli build-data` (see `05_sources/census/README.md`).
- Tests: `ml_pipeline/tests/test_scoring.py`, `ml_pipeline/tests/test_data_integrity.py`.
