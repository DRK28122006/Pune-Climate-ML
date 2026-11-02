# Satellite source — epoch cube

## Source
- Google Earth Engine reduction of Sentinel-2 / Landsat + MODIS LST, reduced server-side.
- Cube: `ml_pipeline/data/epoch_cube.json`, ~512 KB, 864 cells (~1 km) covering PMC bbox.

## Epochs
- Available: 2024, 2010, 2000, 1990, 1980; projected 2080 (scenario delta, not observation).
- Scoring supported for 2024 only. Cross-sensor radiometric calibration deliberately not built.

## Fields and units
- Land cover per cell: built-up, vegetation, water, bare soil (percent); tree canopy (percent).
- Temperatures: day and night LST (°C), annual composite.
- Elevation (m), slope (where present).
- LST reference per cell (vegetated-pixel median) and UHI delta.

## Day/night LST decision
- Night heat is deliberate. Daytime surface heat retired after two measured failures (mid-morning contrast +0.11 °C; ECOSTRESS afternoon 3 clear scenes < 10 bar).
- Night reference = 17.96 °C; night UHI span = 5.0 °C (both measured/derived). Do not switch back to day LST.
- Day branch retained only as fallback when night data absent.

## Stale / pending
- `ward_validation.json` and `site_validation.json` are stale (use day LST and 2.0 °C span; 6 wards only) — see 04_validation.
- `uhi_max_delta_c` (day span 2.0) derivation is stale vs live cube; retained pending heat decision.
- Reference method for heat is per-cell vegetation median; city-wide green median would yield 1–8 °C deltas (not yet adopted).
- LCZ overlay (RUB global LCZ map at 100 m in GEE) not yet sampled.
