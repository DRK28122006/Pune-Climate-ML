# Research vault — onboarding pack

This directory is the single onboarding pack for every future session on Dishadharti / Pune-Climate-ML. It lets a fresh agent answer, in under five minutes:

1. What research assets exist? → `MANIFEST.json`, `01_data_inventory.md`.
2. Which assets are missing, stale, or external? → `MANIFEST.json` (`status`), `01_data_inventory.md`.
3. How do I rebuild or verify each one? → `02_methods/`, `05_sources/`, `04_validation/`.

## Layout
```
ml_pipeline/research/
├── README.md
├── MANIFEST.json
├── 00_scope.md
├── 01_data_inventory.md
├── 02_methods/        # flood.md heat.md green.md carbon.md
├── 03_reviews/        # scientific review draft
├── 04_validation/     # README.md + artifacts/
├── 05_sources/        # kml/, census/, satellite/, carbon/
├── 06_figures/        # (reserved)
└── 07_decisions/      # README.md + decision notes
```

## Quick facts
- Scorer: deterministic Python pipeline (`ml_pipeline/`, `engine/`); four factors 0–100 (higher = worse): flood, heat, green, carbon.
- Design storm 214 mm (measured IMD 1901–2024); night heat primary (reference 17.96 °C, span 5.0 °C).
- Carbon bands 400/800/1200 are house bands, not a named standard.
- Census total 4,009,623 (not 4,009,624). `wc -l` overstates rows.
- Ward ids do not join directly; use point-in-polygon against `05_sources/kml/pmc_wards_2025.kml`.

## Rules
- No fabricated data; missing assets documented with exact rebuild commands.
- Do not edit scoring/validation code, `frontend/`, `backend/`, `engine/` from this pack.
- Large binaries (census 1.2 GB, tree index 52 MB) are never committed.

## Sources of truth
- Shared context: `prompts/00_context.md`.
- Scientific review: `03_reviews/2026-11-02_scientific_review.md`.
- Config: `ml_pipeline/config/regions/pune.json`, `materials.json`, `species.json`.
