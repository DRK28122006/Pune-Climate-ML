# Session 1 — Research vault and data restoration

**Suggested model:** Beam Free  
**Dependencies:** none  
**Owns:** `ml_pipeline/research/**`, `.gitignore` exceptions  
**Do not touch:** scoring code, validation code, `frontend/`, `backend/`, `engine/`

Read `prompts/00_context.md` first.

## Mission

Create `ml_pipeline/research/` as the single onboarding pack for every future session. It must let a fresh agent answer three questions in under five minutes:

1. What research assets exist?
2. Which assets are missing, stale, or external?
3. How do I rebuild or verify each one?

This is an indexing and provenance session, not a modelling session.

## Create this structure

```text
ml_pipeline/research/
├── README.md
├── MANIFEST.json
├── 00_scope.md
├── 01_data_inventory.md
├── 02_methods/
│   ├── flood.md
│   ├── heat.md
│   ├── green.md
│   └── carbon.md
├── 03_reviews/
│   └── 2026-11-02_scientific_review.md
├── 04_validation/
│   ├── README.md
│   └── artifacts/
├── 05_sources/
│   ├── kml/
│   ├── census/README.md
│   ├── satellite/README.md
│   └── carbon/README.md
├── 06_figures/
└── 07_decisions/
```

## Tasks

1. Create the folder structure.
2. Copy the small KMLs into `05_sources/kml/`:
   - `/home/mesh/Pictures/pmc_wards_2025.kml`
   - `/home/mesh/Pictures/WARD12_TEST_SITE.kml`
3. Copy the scientific review draft into `03_reviews/`:
   - `/tmp/opencode/Dishadharti_Scientific_Review_Draft.md`
4. Create `MANIFEST.json` with one entry per asset. Each entry must include:
   - `id`
   - `title`
   - `kind` (`report`, `kml`, `cube`, `validation`, `config`, `figure`, `script`, `external`)
   - `path`
   - `bytes`
   - `sha256`
   - `source`
   - `retrieved_at`
   - `licence`
   - `tracked` (`true`/`false`)
   - `status` (`current`, `stale`, `missing`, `external`, `experimental`)
   - `notes`
5. Index, but do not duplicate, the existing assets:
   - `docs/Dishadharti_ML_Report.pdf`
   - `README.md`
   - `ml_pipeline/data/epoch_cube.json`
   - `ml_pipeline/data/imd_pune_annual_max.csv`
   - `ml_pipeline/data/census_ward_profile.csv`
   - `ml_pipeline/data/gedi_ward_rh95.csv`
   - `ml_pipeline/data/ward_validation.json`
   - `ml_pipeline/data/site_validation.json`
   - `ml_pipeline/data/stress/`
   - `ml_pipeline/data/e2e/`
   - `ml_pipeline/config/regions/pune.json`
   - `ml_pipeline/config/materials.json`
   - `ml_pipeline/config/species.json`
   - `ml_pipeline/reference/pmc_stormwater_drains.kmz`
   - `docs/assets/*.png`
6. Document the missing assets with exact rebuild instructions:
   - raw tree census: `ml_pipeline/data/census/`
   - tree index: `ml_pipeline/data/tree_index.sqlite`
   - reference layers: `ml_pipeline/data/reference_layers.sqlite`
   - parks KML: `ml_pipeline/reference/pune_parks.kml`
   - nallas KML: `ml_pipeline/reference/pune_nallas.kml`
7. Add `.gitignore` exceptions only for the small research KMLs and research documents:
   - allow `ml_pipeline/research/05_sources/kml/*.kml`
   - do not allow census CSV, tree index, or other large binaries
8. Write `05_sources/census/README.md` with:
   - the census source and expected size
   - `fetch_census_parts.py --all`
   - `ml_pipeline/cli.py build-data`
   - expected tree count `4,009,623`
   - a warning that `wc -l` overstates rows because of embedded newlines
9. Write `05_sources/satellite/README.md` with:
   - cube source, 864 cells, 2024 epoch
   - fields and units
   - the day/night LST decision
   - what is stale or pending
10. Write `05_sources/carbon/README.md` with:
    - IFC India 2017 source
    - CEEW aluminium source
    - IGBC 700 anchor
    - a warning that 400/800/1200 are house bands
11. Write `02_methods/*.md` as concise method notes for flood, heat, green, and carbon. Link to code and config; do not invent new methods.
12. Write `07_decisions/README.md` explaining that decision notes are required for changes to weights, spans, bands, thresholds, and legal labels.

## Asset restoration

Do **not** download the 1.2 GB census unless the user explicitly approves it in this session.

If the user approves and network is available:

```bash
python ml_pipeline/data/fetch_census_parts.py --all
python -m ml_pipeline.cli build-data
```

If not approved, leave the exact commands and expected outputs in `05_sources/census/README.md`.

Do not fake `tree_index.sqlite`, `reference_layers.sqlite`, or any KML.

## Do not

- Do not edit `ml_pipeline/core/scoring.py`, `canopy.py`, `geometry.py`, or `engine/`.
- Do not regenerate validation JSONs.
- Do not edit the PDF.
- Do not commit the 1.2 GB census or the 52 MB tree index.
- Do not create a second copy of `ml_pipeline/data` inside `research/`.
- Do not claim a checksum you did not compute.

## Acceptance

- `ml_pipeline/research/README.md` exists and is useful to a new agent.
- `MANIFEST.json` is valid JSON and every entry has a checksum or a `missing` status.
- The two KMLs are present in `05_sources/kml/` and are tracked or explicitly documented as external.
- Missing assets have exact rebuild commands.
- `git status` shows only intended additions and `.gitignore` changes.
- No ML code files changed.

## Handoff

Report:

- The folder tree you created.
- Which assets are present, stale, external, or missing.
- Whether you restored any data, and the exact commands.
- Any `.gitignore` exceptions.
- What Session 3 needs from you.
