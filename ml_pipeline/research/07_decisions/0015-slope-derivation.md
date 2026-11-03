# Decision 0015 — Slope derivation method and enable gate

**Date:** 2026-11-03 (Session 14)  
**Status:** accepted (method + gate; no derivation, no scorer change — Session 15 implements)

## 1. Method chosen

**Finite difference from `elevation_m`** (central difference on the 32x27 0.009° grid),
labelled `CELL_SCALE_DERIVED_LOWER_BOUND`.

Evidence (authoritative band: `slope_band.json`, 864/864 cells; the
`epoch_cube.json` elevation range is 535.1-1030.8 m):

- p95 slope = 4.9895°, max = 11.58°, mean = 1.4378°, median = 0.8400°.
- 372 of 864 cells (43.1%) have slope > 1.0°; 43 cells > 5.0°.

Earlier preliminary figures (p95 4.91°, max 11.53°, mean 1.42°, median 0.80°,
367 cells >= 1.0°) were computed before Session 15's band existed and are
superseded; they do not change the gate outcome.

- A 1 km average is **not** a parcel slope. Steep micro-slopes (terraces,
  cuttings, embankments) are smoothed away. This is a lower bound on local
  steepness, and a screening-level proxy only.

Why not the alternatives:

- 30 m DEM (Copernicus/SRTM): higher fidelity but adds a new download, a new
  dependency, and new provenance; not available in this checkout. Worth the
  extra work only if the finite-difference layer fails the enable gate below or
  if a parcel-level claim is needed. See Section 5.
- Leave slope off: avoids a re-baseline but leaves saturated cells
  indistinguishable (decision 0002: flood ceiling ~56.6 before slope/drainage).

## 2. Parameters

- Slope modifier: `1 + min(slope/15, 1) x 0.25`, capped at 1.25x.
- 15° and 1.25x are **`UNSOURCED_HOUSE_JUDGMENT`**. No citation exists; they
  are house judgment, unlike the 214 mm design storm. Acceptable for a screening
  tool only if labelled as house judgment in output and docs. Do not invent a
  citation. Session 15 must surface these as unsourced in any new output.

## 3. Enable gate (house judgment, labelled)

Enable slope only if **both** hold:

1. Derived p95 slope >= 1.0°.  -> **PASS** (4.9895°).
2. At least 3 of the 6 validation wards (3, 7, 12, 13, 21, 25) change flood
   score by >= 1.0 point. -> **FAIL** (0 of 6; deltas +0.30 to +0.90).

**Gate outcome: DO NOT ENABLE** under the current finite-difference layer. Ward-level
flood deltas are < 1.0 point, so slope adds no measurable discrimination at the
validation scale with this method.

## 4. Re-baseline plan (if/when enabled)

- Artifacts that change: `epoch_cube.json` (gains `mean_slope_deg` in all 864
  cells), `ward_validation.json`, `site_validation.json`, `docs/example_assessment.json`,
  stress/e2e artifacts.
- Hashes that move: epoch cube sha256, validation JSON sha256s, example sha256.
- Flood scores rise only in sloped cells (multiplier >= 1.0; never below 1.0),
  so every flood score is >= its pre-slope value. Composite impact rises only
  where flood rises.
- Report must state: slope is `CELL_SCALE_DERIVED_LOWER_BOUND`, 15°/1.25x is
  `UNSOURCED_HOUSE_JUDGMENT`, and whether the gate was met.
- Rollback: set `mean_slope_deg` to null in the cube (or skip the multiplier in
  `compute_flood`), no scorer edit needed beyond the existing null handling.

## 5. Alternative

A 30 m DEM (Copernicus GLO-30 / SRTM) would be worth the extra work when:
- parcel-adjacent slope is required for a claim (the finite-difference layer is
  a 1 km lower bound), or
- the finite-difference gate fails (it does, on ward deltas) and the team still
  wants slope active.
Recommend acquiring Copernicus GLO-30 (free, CC BY 4.0) and re-running the gate
before enabling.
