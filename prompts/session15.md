# Session 15 — Slope derivation, distribution audit, and score-impact preview

**Suggested model:** DeepSeek V4.1 Flash Free (numerical engineering)
**Dependencies:** none blocking. Reads Session 14's `0015-slope-derivation.md`
if it exists; otherwise uses the default method and gate in this prompt.
**Runs in parallel with:** Session 14 (flood/heat research). Disjoint files.
**Owns (new files only):**
- `ml_pipeline/data/derive_slope.py`
- `ml_pipeline/data/slope_preview.py`
- `ml_pipeline/data/slope_band.json` (derived)
- `ml_pipeline/tests/test_slope.py`
- `prompts/handoffs/session15.md`

**Do not touch:** any existing file. This session is **additive only**.

Specifically, do not edit:

- `ml_pipeline/core/scoring.py` — the slope multiplier already exists
- `ml_pipeline/core/recommendations.py`, `ml_pipeline/report/*`
- `ml_pipeline/cli.py`, `engine/score.py`
- `ml_pipeline/data/validate_wards.py`, `ml_pipeline/data/validate_sites.py`
- `ml_pipeline/config/regions/pune.json`, `materials.json`, `species.json`
- `ml_pipeline/data/ward_validation.json`, `site_validation.json`
- `ml_pipeline/research/**`, `docs/`, `README.md`, `frontend/`, `backend/`
- Session 14 files: `ml_pipeline/core/floodplain.py`,
  `ml_pipeline/data/floodplain_probe.py`, `ml_pipeline/data/flood_layers.sqlite`,
  and its three decision notes

Do not commit. Leave all work uncommitted for review.

Read first: `prompts/00_context.md`, `prompts/handoffs/session13.md`,
`ml_pipeline/research/08_signoff/ML_SIGNOFF.md`,
`ml_pipeline/research/07_decisions/0002-flood-scale.md`.

---

## Mission

Produce a reproducible, cell-scale slope band from the cube's existing
`elevation_m`, audit whether it actually adds discrimination, and preview its
effect on the current flood scores.

**Do not enable it. Do not re-baseline. Do not edit the scorer.** The plumbing
already exists: `cli.py`, `engine/score.py`, `validate_wards.py`, and
`validate_sites.py` all read `mean_slope_deg` from the cell dictionary. The
missing piece is the data and the evidence, not the wiring. Integration is a
small, review-gated change for a later session.

The honest possible outcomes are:

- **Worth enabling** — the band discriminates and the preview shows a material
  score change. Hand off with numbers.
- **Not worth enabling** — the 1 km grid is too smooth; p95 slope is tiny and
  nothing moves. Say so plainly and recommend against it.

Both are successful. Do not force a win.

---

## 0. Hard constraints

1. **No existing file may be edited.** If you believe one must change, stop and
   write the reason in the handoff.
2. **No measured constant changes.** 214 mm, 17.96 °C, 5.0 °C, weights, bands,
   CN table, 15°, 1.25×, 500 m, 0.80 are all out of scope.
3. **No artifact regeneration.** Do not run `validate_wards.py` or
   `validate_sites.py` in write mode. Do not touch the validation JSONs.
4. **Deterministic output.** Same cube in, same band out. No randomness, no
   interpolation, no smoothing.
5. **Provenance is mandatory.** The band must record the cube hash, method,
   spacing method, distribution, timestamp, and caveats.
6. **No hand-editing** of the generated `slope_band.json`.

---

## 1. Derivation

### 1.1 Input

`ml_pipeline/data/epoch_cube.json`

- 864 cells, 32 × 27 grid, 0.009° spacing (~1 km).
- `elevation_m` is present in all 864 cells, range **535.1–1030.8 m**.
- Cell key format: `"{lon:.4f}_{lat:.4f}"`, e.g. `73.7363_18.3901`.
- The cells are a complete rectangle, but still handle missing neighbours
  defensively.

### 1.2 Mathematics

For cell \((i,j)\) with elevation \(z_{i,j}\):

\[
\frac{\partial z}{\partial x} \approx
\frac{z_{i+1,j} - z_{i-1,j}}{2\,\Delta x},
\qquad
\frac{\partial z}{\partial y} \approx
\frac{z_{i,j+1} - z_{i,j-1}}{2\,\Delta y}
\]

\[
\text{slope}_{i,j} =
\arctan\!\left(
\sqrt{
\left(\frac{\partial z}{\partial x}\right)^2 +
\left(\frac{\partial z}{\partial y}\right)^2
}
\right)
\quad\text{in degrees}
\]

Rules:

- \(\Delta x\) and \(\Delta y\) are **geodesic metres**, not degrees. Use
  `pyproj.Geod(ellps="WGS84").inv()` between cell centres. Do not hardcode
  111 km or `111320 * cos(lat)`.
- **Central difference** where both opposite neighbours exist.
- **One-sided difference** at the grid edge.
- **`None`** if no neighbour exists in that axis and the other axis is also
  unavailable. If one axis is available, use it (do not drop the cell).
- Clamp to \([0, 90]\).
- Round to 2 decimals.
- No smoothing, no filling, no interpolation, no extrapolation.

### 1.3 Output schema

`ml_pipeline/data/slope_band.json`:

```json
{
  "provenance": {
    "method": "finite_difference_from_cell_elevation",
    "method_label": "CELL_SCALE_DERIVED_LOWER_BOUND",
    "source_cube": "ml_pipeline/data/epoch_cube.json",
    "source_cube_sha256": "<sha256>",
    "cell_count": 864,
    "cells_with_slope": 864,
    "grid": "32x27",
    "spacing": "geodesic via pyproj.Geod(WGS84)",
    "slope_p05_deg": 0.0,
    "slope_median_deg": 0.0,
    "slope_p95_deg": 0.0,
    "slope_max_deg": 0.0,
    "generated_at_utc": "2026-11-03T00:00:00+00:00",
    "caveats": [
      "1 km cell-mean elevation smooths local relief.",
      "The result is a lower bound on parcel-scale slope.",
      "Not a substitute for a 30 m DEM on steep sites."
    ]
  },
  "cells": {
    "73.7363_18.3901": {"mean_slope_deg": 1.23}
  }
}
```

Report the distribution in the handoff and in the preview. If the derivation
produces implausible values (negative, > 45° on a city with 535–1031 m relief),
stop and debug before writing the band.

---

## 2. Kill gate (run before building the preview)

Compute the distribution. Then apply the gate from
`0015-slope-derivation.md`, or this default if that note is absent:

> Enable only if **p95 slope ≥ 1.0°** and at least **3 of the 6 validation
> wards** change flood score by **≥ 1.0 point**.

If the gate fails:

- Still write `slope_band.json` (the data is real and reproducible).
- Write the preview anyway, so the reviewer sees the numbers.
- In the handoff, recommend **DO NOT ENABLE** and state the exact p95 and the
  number of wards that moved.
- Do not build any plumbing.

The gate is house judgment; label it as such. It exists to prevent adding
complexity and a re-baseline for a signal too small to matter.

---

## 3. Score-impact preview

Create `ml_pipeline/data/slope_preview.py`.

Scope: **flood only.** Slope does not touch heat, green, or carbon. With fixed
weights, a flood delta \(\Delta F\) implies:

\[
\Delta\text{impact} = 0.30 \times \Delta F,
\qquad
\Delta\text{climate} = -0.30 \times \Delta F
\]

when all four factors are present. State this identity; do not recompute the
composite with a fake ledger.

Requirements:

1. Read the 6 validation wards and 8 validation sites exactly as
   `validate_wards.py` / `validate_sites.py` do. **Importing those modules is
   allowed; editing them is not.** If they are not safely importable (module-level
   side effects), copy the minimal indicator-building code into the preview and
   say so in the handoff.
2. For each row, call `compute_flood` twice with identical inputs:
   - `mean_slope_deg=None` (current behaviour)
   - `mean_slope_deg=<derived value for that cell>`
3. Print a table with: row, cell id, derived slope, flood before, flood after,
   delta, implied impact delta, implied climate delta.
4. Aggregate: min / median / p95 / max slope, number of rows with delta ≥ 1.0,
   number with no change.
5. Write `/tmp/opencode/slope_preview.json`. **No tracked writes.**
6. Exit cleanly if `slope_band.json` is missing.

Also run the same preview over all 41 wards (centroid cell) for a wider
distribution, but label it `centroid_sample` — a ward centroid is not an
area-weighted ward slope. Do not present it as the latter.

---

## 4. Tests

Create `ml_pipeline/tests/test_slope.py`. Use plain assertions and the existing
test style (the repo runs tests as scripts as well as under pytest). Cover:

1. **Flat plane** — constant elevation → slope 0.0° everywhere.
2. **Known ramp** — a synthetic grid with a known east-west rise gives the
   expected angle within 0.05°. For example, 100 m per 1 km → 5.71°.
3. **North ramp** — same check on the other axis.
4. **Edge cell** — one-sided difference matches the analytical ramp.
5. **Missing neighbour** — a hole in the grid yields `None`, not 0.0.
6. **Geodesic spacing sanity** — 0.009° of latitude is ≈ 1 km, but compute the
   exact geodesic distance and assert it is within 1% of the value your
   derivation actually uses. Do not hardcode 111 km/degree.
7. **Multiplier monotonicity** — call `compute_flood` directly with slopes
   0°, 5°, 15°, 30°; the score must be non-decreasing and capped at 1.25×.
8. **Missing slope** — `mean_slope_deg=None` returns `slope_available: false`
   and the same score as the current baseline.
9. **No regression** — `python ml_pipeline/tests/test_scoring.py` still reports
   83/83.

Do not mock the cube for the unit tests; use small in-memory grids for the
derivation tests and the real cube only for the preview.

---

## 5. Commands and acceptance

Run:

```bash
python ml_pipeline/data/derive_slope.py
python ml_pipeline/data/slope_preview.py
python ml_pipeline/tests/test_slope.py
python ml_pipeline/tests/test_scoring.py
```

Acceptance criteria:

- [ ] `derive_slope.py` is deterministic: two runs produce byte-identical
      `slope_band.json` (modulo the timestamp, which must be the only difference;
      ideally make the timestamp injectable for the test).
- [ ] `slope_band.json` contains 864 cells (or a documented subset), provenance
      with the cube sha256, and the full distribution.
- [ ] `slope_preview.py` prints before/after flood deltas for 6 wards and 8
      sites and writes only to `/tmp/opencode/`.
- [ ] `test_slope.py` passes all cases, including the multiplier cap and the
      missing-slope no-op.
- [ ] `test_scoring.py` is still 83/83.
- [ ] `git status --short` shows only the five new files this session owns.
- [ ] No existing file was modified.
- [ ] No commit was made.

If the gate fails, the acceptance is still met as long as the numbers and the
`DO NOT ENABLE` recommendation are in the handoff. Do not game the gate.

---

## 6. Handoff

Write `prompts/handoffs/session15.md` with:

1. The derivation method and the exact command to reproduce the band.
2. The distribution: min / p05 / median / p95 / max slope, and the count of
   cells above 1°, 5°, 15°.
3. The gate result: pass or fail, with the exact numbers against the threshold.
4. The preview table for the 6 wards and 8 sites, plus the maximum flood delta.
5. The implied composite delta using the identity
   \(\Delta\text{impact} = 0.30\,\Delta F\).
6. A clear recommendation: **ENABLE**, **DO NOT ENABLE**, or **ENABLE AFTER A
   30 m DEM**, with one paragraph of reasoning.
7. The exact integration patch a later session should apply, as a short bullet
   list (which files, which lines, behind what flag). Do not apply it.
8. Anything the reviewer must not claim yet (e.g. "slope-adjusted flood is
   live", "parcel-level slope is measured").
