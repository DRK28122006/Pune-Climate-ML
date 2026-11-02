# Flood method (Pune)

**Code:** `ml_pipeline/core/scoring.py::compute_flood`, `area_weighted_cn`, `scs_cn_runoff_mm`
**Config:** `ml_pipeline/config/regions/pune.json` → `hydrology` (design storm, CN table, slope/drain constants)
**Inputs:** `ml_pipeline/data/epoch_cube.json` (land cover per ~1 km cell), site polygon via `ml_pipeline/core/geometry.py`

## Method

- SCS-CN excess runoff of the site vs a fully vegetated baseline (CN = `cn_table.vegetation`, default 60), under the 100-year 1-day design storm (`design_storm_mm = 214.0` mm, measured IMD 1901–2024).
- Land-cover CNs: vegetation 60, impervious 98, water 100, bare 86 (TR-55, HSG B assumed for all PMC — see config note; not SSURGO-derived).
- Score = `(excess_runoff_mm / design_storm_mm) * 100`, then multiplied by slope multiplier (1.0–1.25 above 15°) and engineered-drainage multiplier (0.8–1.0 by distance to outfall).
- `saturated_at_design_storm` flag is set when site runoff equals the full storm (CN ~100); score is unchanged, reported as a ceiling.

## Not implemented (do not claim)

- Flood-plain / natural watercourse exposure (C12). Only engineered drain proximity is scored; proximity to a nala raises, not lowers, risk. See `compute_flood` docstring.
- HSG not derived from SSURGO; single assumed class B.

## Rebuild / verify

- `python ml_pipeline/data/derive_design_storm.py` reproduces 214 mm from `ml_pipeline/data/imd_pune_annual_max.csv`.
- Tests: `ml_pipeline/tests/test_scoring.py` (flood cases).
