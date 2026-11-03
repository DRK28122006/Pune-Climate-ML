# Heat cross-check — night LST vs independent 2 m air temperature (2024)

**Date:** 2026-11-03  
**Session:** 14  
**Question:** does independent air-temperature data corroborate the night-LST
ranking?

## Source

- **Air temperature:** Open-Meteo Archive API (`archive-api.open-meteo.com/v1/archive`),
  hourly `temperature_2m`, 2024-01-01 to 2024-12-31, `timezone=Asia/Kolkata`,
  no API key (non-commercial use, attribution required).
- **Retrieved at:** 2026-11-03.
- **Licence:** Open-Meteo data, CC BY 4.0.
- **LST (surface):** area-weighted `lst_night_mean_c` from `epoch_cube.json`
  (MODIS night LST, 1 km) for the same 41 ward polygons, using the same true
  area-weighting as `validate_wards.py`. For the 6 validation wards the value
  is read directly from `ward_validation.json` (already area-weighted).
- **Summary CSV:** `ml_pipeline/data/heat_crosscheck_2024.csv`
  (ward, lat, lon, n_hours, night_mean_c, annual_mean_c, source, retrieved_at,
  licence), tracked via a `.gitignore` exception.
- **Full evidence JSON:** `ml_pipeline/data/heat_crosscheck_2024.json`
  (41 rows including `lst_night_mean_c`; sha256
  `32fc6c521cc3d44e774572d7d7be410a31cf4af873fe75893dec17c2fc6f025e`), tracked.
- **Verifier:** `python ml_pipeline/data/heat_crosscheck.py` (offline) recomputes
  rho and the 10,000-shuffle permutation p from the JSON. `--refresh` re-fetches
  Open-Meteo and rewrites both files.

## Method

1. Ward centroids (shapely polygon centroid in lon/lat) for all 41 wards from
   `reference_layers.sqlite`.
2. For each ward, fetch 2024 hourly 2 m air temperature from Open-Meteo (the API
   snaps to its ~0.25° grid; many wards share a grid point — this is an inherent
   property of the source and is reported).
3. Night mean = mean over hours 22, 23, 0, 1, 2, 3, 4, 5 IST (8 hours; covers
   MODIS Terra ~22:30 and Aqua ~01:30 overpasses). Annual mean = mean over all
   8784 hours (for context).
4. Spearman rank correlation between ward night air-temperature mean and ward
   area-weighted night LST mean. n = 41. p-value: scipy asymptotic + 10000-shuffle
   permutation.

## 6 validation wards

| ward | air night mean (°C) | air annual mean (°C) | lst_night_mean (°C) | n hours |
|---:|---:|---:|---:|---:|
| 3  | 21.993 | 25.627 | 19.599 | 2928 |
| 7  | 21.931 | 25.261 | 21.268 | 2928 |
| 12 | 21.931 | 25.261 | 22.286 | 2928 |
| 13 | 21.931 | 25.261 | 22.213 | 2928 |
| 21 | 22.031 | 25.361 | 22.284 | 2928 |
| 25 | 21.931 | 25.261 | 22.866 | 2928 |

## 41-ward rank correlation

- n = 41
- Spearman rho = 0.2328
- p (asymptotic, two-sided) = 0.1430
- p (permutation, 10000 shuffles) = 0.1406

## Reproduce

```
python ml_pipeline/data/heat_crosscheck.py
# rows 41, rho 0.232781, p_perm 0.140586, p_asym 0.143021 -> PASS
```

The verifier is offline and exits non-zero if the recomputed rho or permutation
p differs from the stored values. `--refresh` is the only network path.

## Verdict

**INCONCLUSIVE.** rho = 0.23 is between the house thresholds of 0.2 (NOT_CORROBORATED)
and 0.5 (CORROBORATED), and p = 0.143 > 0.05. The night-LST ranking is neither
independently corroborated nor contradicted by 2 m air temperature at ward scale.

Thresholds (0.5 / 0.2, p < 0.05) are house judgment; stated as such.

## Caveats

- Air vs surface: 2 m air temperature is not land surface temperature; the heat
  factor is built on radiometric LST.
- Grid vs 1 km: Open-Meteo snaps to a ~0.25° grid, so many wards share an
  identical air-temperature series (41 wards map to 10 distinct series); this
  compresses the air-temperature rank space and weakens the test.
- One year: 2024 only.
- ERA5/Open-Meteo assimilates station data: independent of MODIS but not of all
  observations.
- n = 6 validation wards have low power; n = 41 is the stronger test.
- rho is computed on ward centroids' snapped grid values, not on parcel data.
