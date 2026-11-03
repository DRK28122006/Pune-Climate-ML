# Handoff — Session 15 (slope derivation, distribution audit, score-impact preview)

**Date:** 2026-11-03  
**Verdict:** **DO NOT ENABLE** — the derivation is real and reproducible, but it fails the house gate on ward impact.  
**Status:** Additive at first pass. Post-review fixes on 2026-11-03 corrected the derivation and added a stale-band guard; see §9. Nothing was committed.

---

## 1. What was built

| File | Tracked? | Purpose |
|---|---|---|
| `ml_pipeline/data/derive_slope.py` | new | Deterministic finite-difference slope derivation from `elevation_m` |
| `ml_pipeline/data/slope_band.json` | new (derived) | 864-cell `mean_slope_deg` band + provenance |
| `ml_pipeline/data/slope_preview.py` | new | Flood-only before/after preview; writes only `/tmp/opencode/slope_preview.json` |
| `ml_pipeline/tests/test_slope.py` | new | 11 derivation / multiplier / no-op tests |
| `prompts/handoffs/session15.md` | new | This report |

No other file was modified. `git status --short` shows only these files from this session.

### Method

For each cell \((i,j)\):

\[
\frac{\partial z}{\partial x} \approx \frac{z_{i+1,j}-z_{i-1,j}}{x_{i+1}-x_{i-1}},
\qquad
\frac{\partial z}{\partial y} \approx \frac{z_{i,j+1}-z_{i,j-1}}{y_{j+1}-y_{j-1}}
\]

\[
\text{slope}_{i,j}=\arctan\!\left(\sqrt{(\partial z/\partial x)^2+(\partial z/\partial y)^2}\right)
\]

- The denominator is the full **geodesic** neighbour-to-neighbour distance from `pyproj.Geod(ellps="WGS84").inv()`, not `2 * one step`. The cube grid is not perfectly uniform at its eastern/northern edges (`lon` step 0.0083 vs 0.009, `lat` step 0.0055 vs 0.009), so the general form is required.
- Central difference where both opposite neighbours exist; one-sided at the grid edge.
- One available axis is used; `None` only when neither axis has a neighbour.
- No smoothing, filling, interpolation or extrapolation. Clamped to \([0,90]\), rounded to 2 dp.
- `method_label`: `CELL_SCALE_DERIVED_LOWER_BOUND` (`elevation_m` is a 1 km cell mean, so this is a lower bound on parcel-scale slope).

### Reproduce

```bash
python ml_pipeline/data/derive_slope.py
python ml_pipeline/data/slope_preview.py
python ml_pipeline/tests/test_slope.py
python ml_pipeline/tests/test_scoring.py
```

Deterministic check (timestamp injectable; two runs are byte-identical):

```bash
python ml_pipeline/data/derive_slope.py --generated-at 2026-11-03T00:00:00+00:00 --out /tmp/opencode/band_a.json
python ml_pipeline/data/derive_slope.py --generated-at 2026-11-03T00:00:00+00:00 --out /tmp/opencode/band_b.json
cmp /tmp/opencode/band_a.json /tmp/opencode/band_b.json   # BYTE-IDENTICAL
```

### Provenance recorded in the band

| Field | Value |
|---|---|
| source cube | `ml_pipeline/data/epoch_cube.json` |
| source cube sha256 | `3a88ae667bad0e0ec3c7888a632a2c4cf70fdee148b5288920dce42d3734bad6` |
| cell count / with slope | 864 / 864 |
| grid | 32 × 27 |
| spacing | geodesic via `pyproj.Geod(WGS84)` |
| generated at (UTC) | `2026-11-03T04:35:34+00:00` (regenerated after the §9 fix) |
| quantiles | linear interpolation between order statistics (Hyndman–Fan type 7) |

Caveats embedded in the artifact: 1 km cell-mean elevation smooths local relief; the result is a lower bound; it is not a 30 m DEM.

---

## 2. Distribution (864 cells, degrees)

| Statistic | Value |
|---|---|
| min | 0.0100 |
| p05 | 0.2000 |
| median | 0.8400 |
| p95 | **4.9895** |
| max | 11.5800 |

| Threshold | Cells |
|---|---|
| > 1° | 372 / 864 |
| > 5° | 43 / 864 |
| > 15° | 0 / 864 |

Sanity: no negative values, no value above 45°, max 11.58° on a 535.1–1030.8 m city cube. The derivation was not stopped by the plausibility guard.

Interpretation: the cell-scale tail is real — the western/hill cells reach 5–11° — but most of the city is under 1°. The high p95 is driven by a small steep subset, not by the wards used for validation.

---

## 3. Kill gate

Default gate used because Session 14's `0015-slope-derivation.md` did not exist when this session ran.

> Enable only if p95 slope ≥ 1.0° **and** at least 3 of the 6 validation wards change flood score by ≥ 1.0 point.

| Criterion | Actual | Threshold | Result |
|---|---|---|---|
| p95 slope | 4.9895° | ≥ 1.0° | **PASS** |
| Validation wards moved ≥ 1.0 | **0 of 6** | ≥ 3 of 6 | **FAIL** |
| Overall | — | both | **FAIL — DO NOT ENABLE** |

The closest ward was ward 21 at +0.9 (46.9 → 47.8). No validation ward reached +1.0. This is a house judgment, not a measured constant.

---

## 4. Score-impact preview (flood only)

Identity used: \(\Delta\text{impact}=+0.30\,\Delta F\), \(\Delta\text{climate}=-0.30\,\Delta F\) when all four factors are present. The composite was **not** recomputed with a fake ledger.

### 6 validation wards — area-weighted cube cells

Indicators are built by importing `validate_wards._cells_for_ward()` against a cube copy enriched with `mean_slope_deg`; the code is not copied or edited. Flood-before matches `ward_validation.json` sub-scores exactly (35.5, 33.9, 48.1, 46.2, 46.9, 53.3).

| Row | Cell id (ward centroid) | Derived slope ° | Flood before | Flood after | Δ flood | Δ impact | Δ climate |
|---|---|---:|---:|---:|---:|---:|---:|
| ward 3 | 73.9523_18.5881 | 0.54 | 35.5 | 35.8 | +0.3 | +0.09 | −0.09 |
| ward 7 | 73.8353_18.5341 | 1.17 | 33.9 | 34.5 | +0.6 | +0.18 | −0.18 |
| ward 12 | 73.8443_18.5251 | 0.99 | 48.1 | 48.9 | +0.8 | +0.24 | −0.24 |
| ward 13 | 73.8713_18.5341 | 0.32 | 46.2 | 46.5 | +0.3 | +0.09 | −0.09 |
| ward 21 | 73.8713_18.4891 | 1.16 | 46.9 | 47.8 | +0.9 | +0.27 | −0.27 |
| ward 25 | 73.8533_18.5161 | 0.47 | 53.3 | 53.7 | +0.4 | +0.12 | −0.12 |

Ward slope is area-weighted over all intersecting cells; the cell id is the centroid cell for identification only. **Maximum ward flood delta: +0.9.**

### 8 validation sites — single cube cell

Indicators are built exactly as `validate_sites.py` (centroid cube cell, site square, `drainage_context`); only the slope value is added.

| Row | Cell id | Derived slope ° | Flood before | Flood after | Δ flood | Δ impact | Δ climate |
|---|---|---:|---:|---:|---:|---:|---:|
| Shivajinagar core | 73.8443_18.5341 | 0.73 | 38.2 | 38.7 | +0.5 | +0.15 | −0.15 |
| Koregaon Park green | 73.8893_18.5341 | 0.40 | 38.9 | 39.1 | +0.2 | +0.06 | −0.06 |
| Pashan hill edge | 73.8533_18.5341 | 0.42 | 32.2 | 32.4 | +0.2 | +0.06 | −0.06 |
| Bhosari MIDC | 73.8983_18.5071 | 0.52 | 32.5 | 32.7 | +0.2 | +0.06 | −0.06 |
| Mula riverside | 73.8713_18.4981 | 0.76 | 42.7 | 43.2 | +0.5 | +0.15 | −0.15 |
| Aundh park edge | 73.8083_18.5611 | 0.48 | 44.0 | 44.4 | +0.4 | +0.12 | −0.12 |
| Hadapsar fringe | 73.9883_18.5071 | 0.44 | 14.6 | 14.7 | +0.1 | +0.03 | −0.03 |
| Katraj plain | 73.8713_18.4441 | 1.33 | 43.0 | 44.0 | +1.0 | +0.30 | −0.30 |

**Maximum site flood delta: +1.0 (Katraj plain only).** All other sites are ≤ +0.5.

### 41-ward centroid sample — label is `centroid_sample`

A ward centroid is **one cube cell**, not an area-weighted ward slope. It is reported only for a wider distribution.

- Derived slope: min 0.41°, median 0.86°, p95 2.11°, max 2.24°.
- 14 of 41 centroids move flood by ≥ 1.0.
- Maximum centroid flood delta: **+1.8** (ward 9, 51.3 → 53.1).
- 0 centroids are unchanged at 1 dp.

This wider sample is where the signal looks largest; it does **not** rescue the gate, which is defined on the 6 validation wards and their area-weighted indicators.

### Aggregates

| Group | Slope min / median / p95 / max | Δ ≥ 1.0 | Unchanged | Max flood Δ |
|---|---|---|---|---:|---:|
| 6 validation wards | 0.32 / 0.77 / 1.17 / 1.17 | 0 / 6 | 0 | +0.9 |
| 8 validation sites | 0.40 / 0.50 / 1.13 / 1.33 | 1 / 8 | 0 | +1.0 |
| 41-ward centroid sample | 0.41 / 0.86 / 2.11 / 2.24 | 14 / 41 | 0 | +1.8 |
| All 55 preview rows | 0.32 / 0.76 / 2.08 / 2.24 | 15 / 55 | 0 | +1.8 |

The maximum implied composite change anywhere is \(0.30 \times 1.8 = 0.54\) points impact, and −0.54 climate.

---

## 5. Verification run

| Command | Result |
|---|---|
| `python ml_pipeline/data/derive_slope.py` | Pass — wrote 864-cell band, p95 4.9895° |
| `python ml_pipeline/data/slope_preview.py` | Pass — 6 wards, 8 sites, 41 centroid rows; gate FAIL; wrote `/tmp/opencode/slope_preview.json` |
| `python ml_pipeline/tests/test_slope.py` | **11/11 passed** |
| `python ml_pipeline/tests/test_scoring.py` | **83/83 passed** |
| `python -m pytest ml_pipeline/tests/test_slope.py -q` | 9 passed |
| `python -m pytest ml_pipeline/tests -q` | **92 passed** (83 existing + 9 new) |
| Two `derive_slope.py` runs with fixed `--generated-at` | Byte-identical |
| `git status --short` for session files | Only four new untracked files (handoff makes five) |

The preview imports `validate_wards` and `validate_sites` rather than copying their indicator code: both modules are import-safe (no module-level side effects, `main()` guarded). No validator was run in write mode.

---

## 6. Recommendation

**DO NOT ENABLE.**

The derivation is scientifically clean and reproducible, and the 1 km band does contain a real hill signal: 43 cells exceed 5°, p95 is 4.99°, and some individual centroids would move flood by 1–2 points. But the gate is deliberately about whether enabling the band changes the published validation set enough to justify a re-baseline. It does not: none of the 6 validation wards reaches a 1.0-point flood change (max +0.9), so the composite impact moves at most 0.27 points and no risk band changes. Adding a re-baseline, provenance plumbing and a new cube field for that is complexity without a decision-grade signal at 1 km.

Keep the band as evidence, not as an enabled input. If steep-site discrimination matters later, the right trigger is not a 1 km derived band but a 30 m DEM; that would also let the product stop calling the result a “lower bound” and start measuring parcel relief. Re-run this same gate after such a band exists.

---

## 7. Integration patch for a later session (NOT APPLIED)

If a future decision changes the gate or a 30 m DEM replaces this band, the minimal review-gated patch is:

1. **Add the band to the cube at build time** in `ml_pipeline/data/build_cube.py`: read `ml_pipeline/data/slope_band.json`, verify its `source_cube_sha256` against the cube being built, and copy `cells[key]["mean_slope_deg"]` into each cube cell. Put it behind an explicit flag (e.g. `--with-slope-band PATH`) or an opt-in config key, default off.
2. **Alternatively**, inject it at read time in `ml_pipeline/cli.py::indicators_from_cube` (around the `return dict(cell)` line) behind the same flag; this avoids changing the cube artifact but must still verify the band's cube hash.
3. **Do not change** `ml_pipeline/core/scoring.py`, `engine/score.py`, `validate_wards.py` or `validate_sites.py`: all already read `mean_slope_deg` and already report `slope_available` / `slope_basis`.
4. **After enabling**, regenerate `ward_validation.json` and `site_validation.json` with the validators (write mode), record the new score baseline and the band provenance, and flip `slope_status` from `MISSING` to `PRESENT`.
5. **Add a provenance link** from the validation JSONs to the band sha256; do not hand-edit either JSON.
6. Keep the current no-slope behaviour as the default until the regenerated artifacts are reviewed.

---

## 8. What the reviewer must NOT claim yet

- “Slope-adjusted flood is live.” It is not; `compute_flood` still receives `mean_slope_deg=None` everywhere in production.
- “Parcel-level slope is measured.” The band is a 1 km cell-mean finite difference; it is a lower bound.
- “Ward slope is measured.” `slope_preview.py` reports a 41-ward **centroid sample**; it is not an area-weighted ward slope. The 6 validation wards are area-weighted, but only as a preview.
- “Pune has 5° slopes everywhere.” Median cell slope is 0.840°; the p95 is a steep-cell tail, not a city-wide typical value.
- “Slope changes risk bands.” In this preview no ward band changes and the maximum implied impact delta is 0.54 points.
- “The 30 m DEM question is answered.” It is not; this is a 1 km derived band.
- “Validation artifacts were regenerated.” They were not touched.
- “The gate passed.” It failed on ward impact (0/6 vs required 3/6), despite p95 passing.

No commit was made. All work is left uncommitted for review.

---

## 9. Post-review fix (2026-11-03)

The first-pass derivation divided the central difference by `2 * one-step`, which is only valid on a uniform grid. The cube grid is not uniform at its eastern and northern edges (`lon` 0.0083 vs 0.009, `lat` 0.0055 vs 0.009), so **38/864 cells were wrong by up to 0.40°**. The corrected code divides by the actual geodesic neighbour-to-neighbour distance and builds the axes from every key (including `None`), so a missing row/column stays a gap instead of collapsing the grid.

Changes:

- `derive_slope.py`: general central difference; axes from all keys; docstring updated.
- `slope_preview.py`: refuses to run when the band's `source_cube_sha256` does not match the current cube, or when any cube cell lacks a slope; prints `coverage: 864/864`.
- `test_slope.py`: +2 tests (`test_missing_column_does_not_inflate_slope`, `test_none_column_is_a_hole_not_a_ramp`); 11/11 pass.
- `slope_band.json`: regenerated from the fixed code.

Corrected figures:

| Quantity | First pass | After fix |
|---|---|---|
| cells changed | — | 38/864, max 0.40° |
| median slope | 0.8350° | 0.8400° |
| p95 / max | 4.9895° / 11.58° | unchanged |
| cells >1° / >5° / >15° | 372 / 43 / 0 | unchanged |
| 6 wards moving ≥1.0 | 0/6 (max +0.9) | 0/6 (max +0.9) |
| 8 sites moving ≥1.0 | 1/8 (Katraj +1.0) | 1/8 (Katraj +1.0) |
| 41 centroids moving ≥1.0 | 14/41 (max +1.8) | 14/41 (max +1.8) |
| gate | FAIL | FAIL — `DO NOT ENABLE` |

Example correction: `74.0063_18.4261` was 8.60°, is 8.83°; an independent `(z_{i+1}-z_{i-1})/(x_{i+1}-x_{i-1})` recomputation gives 8.8318°.

Determinism still holds: two fixed-timestamp runs are byte-identical. Test matrix: 94 passed in `ml_pipeline/tests`, 94 passed + 1 skipped at root. The stale-band guard was exercised by corrupting `source_cube_sha256` in a copy and restoring the band; it exited 2 with a clear message. No flood score, validation artifact, constant, weight or band was changed, and slope remains disabled.

The §8 claim “no ward band changes” is verified for the 6 validation wards only; the 41-ward sample is a flood-only centroid preview and its band status is inferred, not computed. The sample also has 40 unique cells for 41 wards (23 and 24 share `73.8623_18.5161`), so it is not 41 independent observations.
