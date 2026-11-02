# Carbon sources

## IFC India 2017
- IFC India Construction Materials Database v1.0 (thinkstep for IFC/EU Eco-cities, Nov 2017, Table 16 GWP).
- Used for: cement_opc 0.91, brick_clay 0.39, concrete_ready_mix 0.11, concrete_low_clinker_30ggbs 0.089, steel_reinforcement 2.6, steel_rebar_eaf 0.83, river_sand/aggregate_rock 0.009 (kgCO₂e/kg, A1–A3).
- Stored in `ml_pipeline/config/materials.json` with per-material `ef_source`.

## CEEW aluminium
- aluminium_primary 20.88 kgCO₂e/kg from CEEW (IFC lists no "primary aluminium" listing; aluminium ingot 31 not adopted).

## IGBC 700 anchor
- IGBC Net Zero Carbon rating: embodied carbon ≤ 700 kgCO₂e/m² for Near Net Zero, offset ≥ 75% of operational carbon. Reported as the named Indian benchmark reference point.

## House bands warning
- Carbon bands 400 / 800 / 1200 are **house bands**, not a named standard. They must not be attributed to GRIHA (`bands_status: UNSOURCED_BANDS` in `ml_pipeline/config/regions/pune.json`).
- 400/800/1200 are intensity thresholds for Low / Moderate / High / Very High, not a regulatory limit.
- Unknown-material threshold 10% (mass) withholds score.

## Observed anchor
- Indian high-rise residential embodied carbon: mean 454, range 373–530, SD 65.3 kgCO₂e/m² (IFC + EPiC).
