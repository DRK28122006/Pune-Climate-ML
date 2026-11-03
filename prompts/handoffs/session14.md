# Handoff — Session 14 (Flood evidence: fluvial exposure, slope decision, heat corroboration)

**Date:** 2026-11-03

## 1. Acquired

- `ml_pipeline/data/flood_layers.sqlite` — 241,664 bytes, sha256
  `5c418349cacd0d008770f266ac581c021c0bdff92427cecd200d3dd30f8bb9e8`,
  licence ODbL-1.0, status ACQUIRED (proximity only). 172 OSM waterways
  (stream 97, canal 40, drain 23, river 12). Gitignored, but reproducible from
  the tracked raw snapshot `ml_pipeline/data/flood_layers_raw.json`
  (sha256 `4ad69abcc2982e1cdc434b96f2960ae0139d6c1d35210a89a3510fcc363b87e6`)
  with `ml_pipeline/data/build_flood_layers.py`.
- `ml_pipeline/core/floodplain.py` — pure helpers `floodplain_status` and
  `watercourse_distance_m`. The extent branch is dormant with the OSM-only
  layer; an empty `floodplain_extents` table returns `in_floodplain=None`.
- `ml_pipeline/data/floodplain_probe.py` — runs on 41 wards + 8 sites;
  writes `/tmp/opencode/floodplain_probe.json`.
- `ml_pipeline/data/heat_crosscheck_2024.csv` — 41 wards, sha256
  `bc5c8aaca1fc97428328553a70448bcf2cfbf52a8aa7f1fbb4e3b625f191d85a`.
  Full ward evidence is `ml_pipeline/data/heat_crosscheck_2024.json`
  (sha256 `32fc6c521cc3d44e774572d7d7be410a31cf4af873fe75893dec17c2fc6f025e`);
  verifier `ml_pipeline/data/heat_crosscheck.py`.
- `ml_pipeline/tests/test_floodplain.py` — 4 tests: missing layer, empty layer,
  current layer is `PROXIMITY_ONLY`, and distance sanity.

## 2. Blocked

- PMC/WRD blue-red flood line: UNAVAILABLE (manual request to PMC/WRD).
- JRC global flood hazard, Copernicus EMS, UNOSAT, Sentinel-1: BLOCKED (account/GEE).
- Unblock: obtain blue-red flood-line KML/GPKG from PMC/WRD; or Copernicus
  account + GEE authentication for modelled/observed tiers.

## 3. Heat cross-check result

- n = 41, rho = 0.2328, p (asymptotic) = 0.1430, p (permutation) = 0.1406.
- Verdict: **INCONCLUSIVE**.
- Reproduction: `python ml_pipeline/data/heat_crosscheck.py` (offline; reads the
  tracked JSON) returns the same rho and permutation p.

## 4. Slope enable gate and recommended decision

- Method: finite difference from `elevation_m` (CELL_SCALE_DERIVED_LOWER_BOUND).
- Gate condition 1 (p95 slope >= 1.0°): PASS (4.9895°, authoritative band).
- Gate condition 2 (>=3 of 6 validation wards change flood score by >=1.0 pt):
  FAIL (0 of 6; deltas +0.30 to +0.90).
- Recommendation: **DO NOT ENABLE** under the proposed gate. 15°/1.25× labelled
  `UNSOURCED_HOUSE_JUDGMENT`. Consider Copernicus GLO-30 30 m DEM if slope
  must be active.

## 5. Integration contract (later session), 5 bullets

- Add a `floodplain` block to flood output using the stable shape.
- If `in_floodplain is True` (extent tier only): add `blocking_issues` entry
  `floodplain_exposure` -> forces REVIEW; no numeric multiplier.
- If `status == "PROXIMITY_ONLY"`: context only, do not force REVIEW.
- If `status == "UNAVAILABLE"`: change nothing.
- Slope: only enable if gate passes; otherwise leave `mean_slope_deg` null.

## 6. Must not be claimed yet

- "Floodplain exposure is measured" (only proximity available).
- "Daytime heat is scored" (deferred; separate index only).
- "Slope is active" (gate failed; not wired).
- "Heat ranking independently corroborated" (INCONCLUSIVE).

## 7. Recommendation

Integrate **slope via a 30 m DEM** first if any of the three is to be wired,
because the finite-difference layer fails the discrimination gate; fluvial
exposure needs a regulatory flood line before it can force REVIEW; heat
corroboration is INCONCLUSIVE and changes no score. Until then, all three
remain evidence/decision only.

## 8. Post-review fixes (2026-11-03)

- Removed stray heredoc terminators (`EOF`/`PYEOF`, `echo written`) from the
  Session 14 docs.
- Reconciled decision 0015's slope figures with the implemented
  `slope_band.json`; the gate outcome is unchanged.
- Rebuilt `flood_layers.sqlite` from the tracked raw snapshot so the provenance
  chain is durable. The only changed metadata row is `meta.raw_path`; all 172
  waterway rows are identical. New DB sha256 `5c418349...`.
- Added `build_flood_layers.py`, `heat_crosscheck.py`, and
  `test_floodplain.py`; tracked the heat CSV via a `.gitignore` exception and
  added the full heat JSON.
- Fixed `floodplain_probe.py` to use a polygon centroid, and the dormant extent
  branch to return `in_floodplain=None` when the extent table is empty.
- Verification: `pytest ml_pipeline/tests -q` 98 passed; root `pytest -q`
  98 passed, 1 skipped; `heat_crosscheck.py` PASS; `floodplain_probe.py`
  49/49 `PROXIMITY_ONLY`, `in_floodplain=None`.