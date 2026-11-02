# Heat method (Pune)

**Code:** `ml_pipeline/core/scoring.py::compute_heat`
**Config:** `ml_pipeline/config/regions/pune.json` → `thermal`
**Inputs:** `ml_pipeline/data/epoch_cube.json` (LST + land cover per ~1 km cell)

## Method

- Urban heat island as a delta between the site cell's mean LST and an empirical reference LST, normalised by a span.
- **Night branch (primary):** reference `night_reference_c = 17.96 °C` (rural-ring vegetated median, 2024 MODIS), span `night_uhi_max_delta_c = 5.0 °C`. Status `MEASURED_2024` / `DERIVED_FROM_EPOCH_CUBE`.
- Score = `clamp((lst_mean_c - reference) / span * 100)`.
- Day branch exists only as a fallback when night data is absent; mid-morning surface contrast was measured at +0.11 °C (no signal) and retired. Do not switch back to day LST.

## Not implemented / pending

- Daytime surface heat retired after two measured failures (see `day_reference_status`).
- ECOSTRESS afternoon exposure reported as unscored context only.
- LCZ reporting language only, not a scoring input.

## Rebuild / verify

- `ml_pipeline/data/derive_uhi_span.py` reproduces the 5.0 °C span from the epoch cube.
- Tests: `ml_pipeline/tests/test_scoring.py` (heat cases).
