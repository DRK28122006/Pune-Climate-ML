# Decision 0016 — Heat data sources

**Date:** 2026-11-03 (Session 14)  
**Status:** accepted (corroboration only; no heat input change)

## 1. Decision

Night LST (MODIS, 1 km) remains the **only** heat input. WAQI and Open-Meteo /
NASA POWER are used for **corroboration only**, never as a substitute for land
surface temperature. No daytime heat score is added.

## 2. Why WAQI is rejected

- WAQI measures air quality (PM2.5, PM10, O3, NO2, SO2, CO). A few stations
  also report air temperature and RH, but coverage is sparse and station-based.
- It is not a temperature product; using it as heat input would substitute air
  quality for surface temperature. Token required for API access.
- Rejected as an input. May be used for context only.

## 3. Why 2 m air temperature is rejected as a substitute

- 2 m air temperature (Open-Meteo / NASA POWER) is a different physical
  quantity from radiometric land surface temperature.
- Air temperature is spatially smooth; substituting it for the surface-calibrated
  17.96 °C / 5.0 °C scale would reintroduce the saturation/compression defect.
- Daytime LST was retired for a measured reason (within-city daytime Landsat
  contrast +0.11 °C, sign flip by season). Do not silently undo that.

## 4. Daytime heat

If a daytime comfort product is wanted later, define it as a **separate** index
(UTCI or WBGT) using air temperature + humidity + wind + radiation, with its own
label. It must never be blended into the 0-100 heat score. Defer until a user
need is confirmed.

## 5. What the corroboration test found

See `ml_pipeline/research/04_validation/HEAT_CROSSCHECK.md`.

Result: on 41 Pune wards, Spearman rho (Open-Meteo 2024 night 2 m air temperature
vs area-weighted MODIS night LST) = 0.233, p = 0.143 (permutation p = 0.141),
n = 41. Verdict: **INCONCLUSIVE** (rho between 0.2 and 0.5; p > 0.05). The
night-LST ranking is not independently corroborated by 2 m air temperature at
ward scale, but it is not contradicted either. Caveats: air vs surface; reanalysis
grid (~0.25°) vs 1 km LST; one year; ERA5/Open-Meteo assimilates station data
so it is independent of MODIS but not of all observations; n=6 validation wards
have low power.

Evidence: `ml_pipeline/data/heat_crosscheck_2024.json` (full 41-row data) and
`ml_pipeline/data/heat_crosscheck.py` (offline verifier; `--refresh` to refetch).