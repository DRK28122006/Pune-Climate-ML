# Session 14 — Flood evidence: fluvial exposure, slope decision, heat corroboration

**Suggested model:** Beam Free (1M context; this session is source-heavy and decision-heavy)
**Dependencies:** Sessions 9–13 complete. Read `ml_pipeline/research/08_signoff/ML_SIGNOFF.md`.
**Runs in parallel with:** Session 15 (slope derivation). Disjoint files. Do not edit Session 15's files.
**Owns:**
- `ml_pipeline/research/07_decisions/0014-fluvial-flood.md`
- `ml_pipeline/research/07_decisions/0015-slope-derivation.md`
- `ml_pipeline/research/07_decisions/0016-heat-data-sources.md`
- `ml_pipeline/research/05_sources/FLOOD_DATA_STATUS.md`
- `ml_pipeline/research/04_validation/HEAT_CROSSCHECK.md`
- `ml_pipeline/core/floodplain.py` (new, pure, no scoring integration)
- `ml_pipeline/data/floodplain_probe.py` (new, standalone)
- `ml_pipeline/data/flood_layers.sqlite` (new, derived, gitignored)
- `ml_pipeline/research/01_data_inventory.md`
- `ml_pipeline/research/MANIFEST.json`
- `prompts/handoffs/session14.md`

**Do not touch:**
- `ml_pipeline/core/scoring.py`, `ml_pipeline/core/recommendations.py`
- `ml_pipeline/report/render.py`, `ml_pipeline/report/narrative.py`
- `ml_pipeline/cli.py`, `engine/score.py`
- `ml_pipeline/data/validate_wards.py`, `ml_pipeline/data/validate_sites.py`
- `ml_pipeline/config/regions/pune.json` and every measured constant (214 mm, 17.96 °C, 5.0 °C, weights, bands)
- `ml_pipeline/data/ward_validation.json`, `ml_pipeline/data/site_validation.json`, `docs/`, `frontend/`, `backend/`
- Session 15 files: `ml_pipeline/data/derive_slope.py`, `ml_pipeline/data/slope_preview.py`, `ml_pipeline/tests/test_slope.py`, `ml_pipeline/data/slope_band.json`

Read first: `prompts/00_context.md`, `prompts/handoffs/session13.md`,
`ml_pipeline/research/08_signoff/ML_SIGNOFF.md`,
`ml_pipeline/research/07_decisions/0002-flood-scale.md`,
`0003-flood-plain.md`, `0004-heat-elevation.md`, `0012-partial-evidence-contract.md`.

Do not commit. Leave all work uncommitted for review.

---

## Mission

Answer three questions with evidence, and write the decisions that let a later
session integrate the answers safely.

1. **Fluvial/floodplain exposure.** Can we add a defensible floodplain signal
   without inventing one? If yes, acquire the layer and prove it runs on the 41
   wards and the 8 validation sites. If no, write `UNAVAILABLE` with the exact
   blocker, not a placeholder polygon.
2. **Slope.** Is the existing slope modifier ready to enable? Decide the
   derivation method, label the parameters honestly, and define the enable gate.
   Do **not** implement it — Session 15 does that.
3. **Heat data sources.** Does independent air-temperature data corroborate the
   night-LST ranking? Should daytime heat use WAQI / Open-Meteo? Expected answer:
   use them only for corroboration, never as a substitute for land surface
   temperature.

**This session changes no score and no verdict.** Wiring floodplain or slope into
`score_project` is deferred to a review-gated session. Reason: both change scores
or force `REVIEW`, and turning both on at once without a controlled re-baseline
would make every stored artifact incomparable. Evidence and decisions now,
integration later.

---

## Scope discipline

| In scope | Out of scope |
|---|---|
| Source audit, licence, hash, acquisition | Editing the scorer, recommendations, renderer, narrator |
| Standalone pure floodplain function + probe | Adding a floodplain penalty to the composite |
| Decision notes 0014 / 0015 / 0016 | Changing weights, bands, 214 mm, 17.96 °C, 5.0 °C |
| Heat rank cross-check | Adding a daytime heat score |
| Status, inventory, manifest updates | Live API calls in the runtime path |
| Re-baseline and rollback plans | Regenerating validation JSONs, PDF, examples |

**Rule:** every deliverable must either (a) add a real, sourced risk signal,
(b) remove a false claim, or (c) make a number reproducible. If it does none of
those, drop it. Do not build a feature because it is interesting.

**No mocks. No synthetic polygons. No placeholder temperatures.** If a source is
unavailable, record `UNAVAILABLE` with the exact reason and the credential or
command needed. Decision `0003` already says no synthetic floodplain penalty;
keep that rule.

---

## 1. Fluvial / floodplain exposure

### 1.1 What the gap actually is

The engine models **pluvial** flood only: rain falling on the site, SCS curve
number, 214 mm design storm. It does **not** model **fluvial** flood: a river or
nalla overflowing its banks, with water arriving from upstream. The result
currently carries `fluvial_flood: "NOT_MODELLED"` and nothing else.

For Pune this is the larger life-safety gap. A site on the Mula-Mutha floodplain
can be fully permeable, near a storm drain, and still read `Moderate`. That is
actively misleading, not merely incomplete.

### 1.2 Source audit (required)

Search local disk first, then open sources. Record every row in
`FLOOD_DATA_STATUS.md`:

| Column | Meaning |
|---|---|
| `source` | Dataset / agency |
| `measures` | Floodplain extent, observed inundation, or proximity only |
| `resolution` | Native spatial resolution |
| `licence` | Explicit licence or "unknown" |
| `access` | Local file, open download, API, or account/GEE required |
| `status` | `ACQUIRED` / `UNAVAILABLE` / `BLOCKED` |
| `why` | One line, with the exact blocker if not acquired |

Search order:

1. **Local files.** Look in the repo, `ml_pipeline/reference/`,
   `ml_pipeline/research/05_sources/`, `/home/mesh/Pictures`,
   `/home/mesh/Downloads`, `/home/mesh/Documents` for `*.kml`, `*.kmz`,
   `*.geojson`, `*.shp`, `*.gpkg` whose names match
   `flood|nalla|river|drain|blue|red|floodline|watercourse`. Record full paths.
2. **PMC / Maharashtra WRD flood lines.** Check whether the blue-red flood-line
   layer is openly downloadable. If it is not, mark `UNAVAILABLE` and state
   exactly who must provide it.
3. **OSM waterways via Overpass.** No key required, ODbL licence. Use the Pune
   bounding box `18.39,73.73,18.60,74.06`:

   ```text
   [out:json][timeout:60];
   (
     way["waterway"~"river|stream|canal|drain"](18.39,73.73,18.60,74.06);
     relation["waterway"~"river|stream"](18.39,73.73,18.60,74.06);
   );
   out geom;
   ```

   Save the raw response under `/tmp/opencode/floodcheck/` and record its
   sha256. Convert to a `waterways` table in `ml_pipeline/data/flood_layers.sqlite`
   with `id, kind, name, geometry_json, source, retrieved_at, licence`.
   OSM is **proximity only** — it is not an inundation extent. Label it
   `PROXIMITY_ONLY` and say so everywhere.
4. **JRC global flood hazard (100-year), Copernicus EMS, UNOSAT.** Check whether
   a no-key download exists. If access needs GEE, a Copernicus account, or a
   manual request, mark `BLOCKED` with the exact requirement. Do not guess a URL.
5. **Sentinel-1 observed inundation.** Requires GEE (`ee` is not installed) or a
   Copernicus account. Mark `BLOCKED` unless a local archive exists.

### 1.3 Selection rule

Prefer, in order:

1. Official regulatory flood line → confidence `REGULATORY`.
2. Observed inundation (SAR / surveyed) → `OBSERVED`.
3. Global modelled hazard (JRC) → `MODELLED_GLOBAL`, must be sanity-checked.
4. OSM watercourse proximity → `PROXIMITY_ONLY`.
5. Nothing → `UNAVAILABLE`.

**Never** promote proximity to a floodplain claim. A nalla 40 m away is a risk
signal; it is not proof the parcel floods.

### 1.4 Standalone screening function

Create `ml_pipeline/core/floodplain.py`. Pure functions, no file reads at import,
no scoring integration. Suggested interface:

```python
def floodplain_status(
    lon: float,
    lat: float,
    layer_path: str | None = None,
) -> dict:
    """Return a floodplain-exposure record, or an explicit UNAVAILABLE record."""

def watercourse_distance_m(
    lon: float,
    lat: float,
    layer_path: str | None = None,
) -> dict:
    """Nearest natural watercourse distance, or UNAVAILABLE."""
```

Return shape (stable — a later session will rely on it):

```json
{
  "status": "REGULATORY | OBSERVED | MODELLED_GLOBAL | PROXIMITY_ONLY | UNAVAILABLE",
  "in_floodplain": true,
  "nearest_watercourse_m": 41.2,
  "source": "osm-overpass-2026-11-03",
  "licence": "ODbL-1.0",
  "confidence": "high | medium | low | none",
  "note": "One sentence a reviewer can quote."
}
```

Use only `shapely` and `pyproj` (already dependencies). If `shapely` is absent,
fail with a clear message; do not hand-roll point-in-polygon on lat/lon degrees.

### 1.5 Probe

Create `ml_pipeline/data/floodplain_probe.py`. It must:

- Load all 41 ward polygons from `ml_pipeline/data/reference_layers.sqlite`.
- Load the 8 validation sites from the same source used by
  `validate_sites.py`. Import `SITES` from that module; it is `__main__`-guarded
  and safe to import. Read it; do not edit it.
- Print a table: ward/site, status, in_floodplain, nearest watercourse, source.
- Write `/tmp/opencode/floodplain_probe.json`. **No tracked writes.**
- Exit cleanly with `UNAVAILABLE` rows if no layer exists. Do not crash.

### 1.6 Decision note `0014-fluvial-flood.md`

Required sections:

1. **Decision** — which source tier was selected, or `UNAVAILABLE`.
2. **Why this tier** — one paragraph, with the rejected alternatives and why.
3. **What it does and does not measure.** Proximity ≠ inundation. Say it plainly.
4. **Integration contract for the later session.** Propose, do not implement:
   - Add a `floodplain` block to the flood factor output using the shape above.
   - If `in_floodplain is True`, add a `blocking_issues` entry of type
     `floodplain_exposure`. That forces `REVIEW`. **No numeric multiplier.**
   - If `status == "PROXIMITY_ONLY"`, report as context, do **not** force REVIEW.
   - If `UNAVAILABLE`, change nothing.
5. **Re-baseline impact.** Count how many of the 41 wards and 8 sites would flip
   to `REVIEW` under the proposed rule. Put the count in the note.
6. **Rollback.** How to disable the flag without touching the scorer.

If no defensible layer is obtainable, the note should say so and stop. A good
`UNAVAILABLE` is a successful outcome; a fabricated polygon is not.

---

## 2. Slope decision (feeds Session 15)

Do not derive the band and do not edit the cube. Decide and document.

### 2.1 Current state

- `compute_flood` already accepts `mean_slope_deg` and applies
  `1 + min(slope/15, 1) × 0.25`, capped at 1.25×.
- The cube has **no** slope band: 0 of 864 cells carry `mean_slope_deg`.
- The cube **does** carry `elevation_m` in all 864 cells, range
  **535.1–1030.8 m**, on a 32 × 27 grid with 0.009° spacing (~1 km).
- The old code silently substituted `3.0°`. That was removed.
- The 15° and 1.25× parameters have **no source and no status field**. They are
  house judgment, unlike the 214 mm storm.
- Flood's attainable ceiling is ~56.6 before slope/drainage (decision `0002`),
  and saturated cells cluster there, so slope is one of the few remaining
  sources of discrimination.

### 2.2 Options to evaluate

| Option | What it gives | What it costs |
|---|---|---|
| Finite difference from `elevation_m` | Cell-scale slope, no new data, reproducible offline | ~1 km smoothing; lower bound on local steepness |
| 30 m DEM (Copernicus / SRTM) | Parcel-adjacent slope | New download, new dependency, new provenance |
| Leave slope off | No re-baseline | Saturated sites stay indistinguishable |

Recommend one. State the evidence, not a preference.

### 2.3 Decision note `0015-slope-derivation.md`

Required sections:

1. **Method chosen** and why. If finite difference: label it
   `CELL_SCALE_DERIVED_LOWER_BOUND` and say a 1 km average is not a parcel slope.
2. **Parameters.** Keep 15° / 1.25× for now, but mark them
   `UNSOURCED_HOUSE_JUDGMENT`. State whether that is acceptable for a screening
   tool. Do not invent a citation.
3. **Enable gate.** Define a numeric gate, for example: enable only if the
   derived p95 slope ≥ 1.0° **and** at least 3 of the 6 validation wards change
   flood score by ≥ 1.0 point. Below that, recommend **DO NOT ENABLE**.
   This gate is house judgment; label it.
4. **Re-baseline plan.** Which artifacts change, which hashes move, and what the
   report must say. Note that flood scores rise only in sloped cells.
5. **Alternative.** When a 30 m DEM would be worth the extra work.

---

## 3. Heat corroboration and data-source decision

### 3.1 What the candidate sources actually are

| Source | What it gives | Why it is not a drop-in heat input |
|---|---|---|
| WAQI | Air quality: PM2.5, PM10, O3, NO2, SO2, CO; a few stations also report air temp and RH | Air quality, not temperature; point stations; token required |
| Open-Meteo | 2 m air temperature, humidity, wind, radiation, soil temp | **Air** temperature, not radiometric land surface temperature |
| NASA POWER | MERRA-2 2 m air temperature | Same category as Open-Meteo |
| MODIS (current) | Night land surface temperature, 1 km | The actual physical quantity the heat factor is built on |

The heat factor is:

\[
\text{heat} = \frac{T_{\text{night,cell}} - 17.96}{5.0} \times 100
\]

Substituting 2 m air temperature for \(T_{\text{night,cell}}\) would reintroduce
the original defect: air temperature is spatially smooth and comparing it to a
surface-calibrated scale pins or compresses the factor. Daytime LST was disabled
for a measured reason: within-city daytime Landsat contrast was **+0.11 °C** and
flipped sign by season. Do not silently undo that.

### 3.2 The corroboration test (required)

Goal: test whether the **night-LST ranking** is corroborated by an independent
air-temperature product. This is a rank check, not an accuracy claim.

Method:

1. Take all 41 ward centroids from `reference_layers.sqlite`.
2. Pull 2024 hourly `temperature_2m` from Open-Meteo Archive:

   ```text
   https://archive-api.open-meteo.com/v1/archive
     ?latitude=<comma-separated>
     &longitude=<comma-separated>
     &start_date=2024-01-01
     &end_date=2024-12-31
     &hourly=temperature_2m
     &timezone=Asia%2FKolkata
   ```

   No key for non-commercial use; check the terms and record them. Batch the
   coordinates if the API allows it; otherwise loop with a small delay.
3. Compute the 2024 mean over night hours **22:00–05:00 IST** (covers the MODIS
   Terra ~22:30 and Aqua ~01:30 overpasses). Also compute the annual mean for
   context.
4. Compare with the area-weighted `lst_night_mean_c` for the same wards from the
   cube. Use the same true area-weighting as `validate_wards.py` (import its
   helpers or copy the minimal logic; do not edit it). For the 6 validation
   wards you may read `lst_night_mean_c` directly from `ward_validation.json`
   instead of recomputing. Do not use a centroid sample for the 41-ward test.
   Use **Spearman rank correlation**. Report \(n\), \(\rho\), and a
   permutation or exact p-value.
5. Fallback if Open-Meteo is blocked: NASA POWER hourly `T2M` for the same
   points. Record which source was used.

Report:

- The 6 validation wards as a readable table.
- The 41-ward rank correlation.
- Verdict: `CORROBORATED` if \(\rho \ge 0.5\) and \(p < 0.05\);
  `NOT_CORROBORATED` if \(\rho < 0.2\); otherwise `INCONCLUSIVE`.
  These thresholds are house judgment; say so.
- Caveats: air vs surface; model/reanalysis grid vs 1 km; one year; ERA5
  assimilates station data, so it is independent of MODIS but not of all
  observations; \(n=6\) has low power, \(n=41\) is the stronger test.

Write `ml_pipeline/research/04_validation/HEAT_CROSSCHECK.md`. Commit only a
small summary CSV if useful (`ml_pipeline/data/heat_crosscheck_2024.csv`) with
columns: `ward, lat, lon, n_hours, night_mean_c, annual_mean_c, source,
retrieved_at, licence`. Never commit the raw API dumps.

### 3.3 Decision note `0016-heat-data-sources.md`

Required sections:

1. **Decision** — night LST remains the only heat input. WAQI and Open-Meteo /
   NASA POWER are corroboration, not inputs.
2. **Why WAQI is rejected** — air quality, not temperature; token; stations.
3. **Why 2 m air temperature is rejected as a substitute** — different physical
   quantity; reintroduces the saturation bug.
4. **Daytime heat.** If a daytime comfort product is wanted later, define it as a
   **separate** index (UTCI or WBGT) using air temperature + humidity + wind +
   radiation, with its own label. It must never be blended into the 0–100 heat
   score. Defer until a user need is confirmed.
5. **What the corroboration test found** — link `HEAT_CROSSCHECK.md` and state
   the verdict in one sentence.

---

## 4. Status updates

- `ml_pipeline/research/05_sources/FLOOD_DATA_STATUS.md`: the source audit table,
  hashes, retrieval dates, licences, and the exact rebuild command for anything
  derived.
- `ml_pipeline/research/01_data_inventory.md`: add the new flood layer and the
  heat cross-check CSV, with status.
- `ml_pipeline/research/MANIFEST.json`: add entries for every new tracked
  artifact with path, bytes, sha256, source, licence, tracked flag, status,
  notes. Mark anything unverified as `UNAVAILABLE`, never `current`.
- Do **not** edit `MANIFEST.json` entries owned by Session 15 (slope). If
  Session 15 adds `slope_band.json`, leave it for the review session.

---

## 5. Acceptance criteria

- [ ] `FLOOD_DATA_STATUS.md` lists every source tried, with licence and status.
- [ ] If a layer was acquired: `flood_layers.sqlite` exists, its sha256 is
      recorded, and `floodplain_probe.py` runs on 41 wards + 8 sites without
      editing any tracked artifact.
- [ ] If no layer was acquired: the three decision notes still exist, and the
      blocker is exact (who provides it, or which credential is missing).
- [ ] `HEAT_CROSSCHECK.md` reports \(n\), \(\rho\), p, verdict, and caveats, and
      names the exact source and retrieval date.
- [ ] `0015` defines a numeric enable gate for slope and labels 15° / 1.25× as
      unsourced house judgment.
- [ ] No score, verdict, weight, band, constant, validation JSON, PDF, or
      example was changed.
- [ ] `git status --short` shows only the files this session owns (new files
      appear as untracked; `flood_layers.sqlite` is gitignored).
- [ ] No commit was made.

Allowed commands (run only your own probe, not the full suite):

```bash
python ml_pipeline/data/floodplain_probe.py
python ml_pipeline/data/check_provenance.py
```

Do not run `pytest` mid-session while Session 15 is editing; the final audit runs
the full matrix after both sessions merge.

---

## 6. Handoff

Write `prompts/handoffs/session14.md` with:

1. What was acquired, and the exact path, bytes, sha256, licence, and status.
2. What was blocked, and the exact unblock action.
3. The heat cross-check result: \(n\), \(\rho\), p, verdict.
4. The slope enable gate and the recommended decision.
5. The integration contract for the later session, in 5 bullet points.
6. What must **not** be claimed yet (e.g. "floodplain exposure is measured",
   "daytime heat is scored", "slope is active").
7. A one-line recommendation: which of fluvial / slope / heat corroboration is
   worth integrating first, and why.
