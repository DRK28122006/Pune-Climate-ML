# Census source — PMC Tree Census 2019

## Source
- PMC Tree Census 2019, CKAN package `f00d83b8-c70f-4fff-9ac7-9a6ab4255edf` on data.opencity.in.
- 17 CSV parts, ~1.2 GB total. Never committed (see `.gitignore`).

## Expected size / count
- 4,009,623 unique trees (16 × 250,000 + 9,623, zero duplicate ids).
- `wc -l` OVERSTATES the row count by ~68% because quoted fields contain embedded newlines. Do not count census rows with `wc`.

## Rebuild (requires network + user approval; do NOT run without approval)
```bash
python ml_pipeline/data/fetch_census_parts.py --all
python -m ml_pipeline.cli build-data
```
Expected output: `ml_pipeline/data/tree_index.sqlite` (~52 MB) with 4,009,623 rows.

## Derived artifacts
- `ml_pipeline/data/tree_index.sqlite` — missing, ~52 MB, re-derivable from the census. Do not fake.
- `ml_pipeline/data/census_ward_profile.csv` — present (ward-level aggregate).
- `ml_pipeline/data/reference_layers.sqlite` — missing (parks/nallas/drains). Rebuild from KML/KMZ + `ml_pipeline/data/reference_layers.py`.

## Status
- Raw census: **missing** (not downloaded in this session; user did not approve the 1.2 GB download).
- Tree index: **missing**.
- Reference layers: **missing**.
