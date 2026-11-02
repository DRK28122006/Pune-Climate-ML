# Decision 0004 — heat elevation confounding

**Date:** 2026-11-02 (Session 4)
**Status:** accepted

## Evidence
On the 864-cell 2024 cube, night LST correlates with built-up (r=+0.553) and
with elevation (r=-0.475); partial r(built | elevation) = 0.407. The 5.0 °C
span is p95−p05 of the same cohort, so the score is a percentile rescaling,
not a physical magnitude.

## Decision
No elevation correction is applied. An elevation-banded rural reference does
not exist in this checkout, and inventing a lapse rate would be an unsourced
constant. Instead:
- `uhi_delta_c` (physical delta) and `uhi_max_delta_c` (span) are both
  reported.
- `heat_scale` states that the score is a percentile-of-cohort-span rescaling.
- `elevation_m` and `elevation_confounding` are reported on every heat result.
- 17.96 °C and 5.0 °C are unchanged (measured/derived; see config).

## Revisit
When an elevation-banded rural reference or a measured lapse rate is
available, add an elevation-adjusted score and update this note with evidence.
EOF