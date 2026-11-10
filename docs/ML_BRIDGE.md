# ML Bridge — Scoring Mode Contract

The backend's Python adapter (`backend/python/ml_bridge.py`) supports two modes,
selected by the JSON request on stdin.

## Extraction mode (existing)

Request contains `coordinates` (and no `ward` / `mode`). Requires
`GEE_PROJECT_ID` and `MODEL_PATH`. Returns satellite features.

## Scoring mode (new)

Request contains `mode: "score"` or `ward`. Needs **no network and no model
weights** — only the baked artefacts. Returns the full `score_project` result
plus recommendations and the canopy ledger.

### Request

```json
{
  "mode": "score",
  "ward": 12,
  "builtUpAreaSqm": 2000,
  "plotAreaSqm": 4000,
  "materials": [
    {"name": "steel", "quantityKg": 120000},
    {"name": "cement", "quantityKg": 400000}
  ],
  "storeys": 4,
  "projectType": "residential",
  "epoch": 2024,
  "impervious": null,
  "vegetation": null,
  "water": null,
  "slope": null
}
```

- `ward` (int) — ward number; the ring is read from `reference_layers.sqlite`.
  Alternatively pass `geometry: [[lon,lat],...]` for an arbitrary polygon.
- `materials` — bill of quantities. Empty list → carbon is UNAVAILABLE.
- `impervious` / `vegetation` / `water` / `slope` — optional explicit
  assumptions (percent or degrees). When the epoch cube is present these are
  ignored; when absent they become `user_supplied_assumption` (labelled).
- `epoch` — currently only 2024 is scored.

### Response

```json
{
  "source": "ml-pipeline-scorer",
  "mode": "score",
  "ward": 12,
  "validation": { ... },
  "score": {
    "impact_score": 59.8,
    "climate_score": 40.2,
    "risk_band": "Moderate",
    "evidence_status": "COMPLETE",
    "decision_grade": true,
    "factors": {
      "flood":   { "score": 34.4, "status": "OK", ... },
      "heat":    { "score": 90.6, "status": "OK", ... },
      "green":   { "score": 83.2, ... },
      "carbon":  { "score": 28.2, "status": "OK", ... }
    },
    "recommendations": { ... },
    "contributions": { "flood": ..., "heat": ..., "green": ..., "carbon": ... }
  },
  "recommendations": [ { "id": ..., "action": ..., "delta": { "impact_before": ..., "impact_after": ..., "impact_delta": ... } } ],
  "canopy": { "canopy_cover_pct": 24.0, "census_reliable_for_this_site": true, ... } | null,
  "indicators": { "impervious_pct": ..., "lst_night_mean_c": ..., ... },
  "satellite_cube_available": true,
  "epoch": 2024
}
```

### Response size: per-tree decisions are summarized

The canopy ledger's `decisions` array holds one record per census tree in the
ward ring — tens of thousands of entries (ward 12: ~70k, ~105 MB of JSON).
The bridge replaces it in the API response with:

- `decisions_count` — total per-tree decisions computed,
- `decisions_sample` — the first 25, deterministic,
- `decisions_note` — explains the summarization.

Scoring and recommendations are computed on the full list before trimming, so
numbers are unchanged. The full list stays available through the CLI and
report paths. Without this, `/api/v1/score` responses are too large for the
browser.

### Caches (re-computation avoidance, not new data)

Both caches reuse a prior full computation verbatim; numbers are identical
to a cold run. Delete them to force re-computation.

- `ml_pipeline/data/air_quality_cache.json` — 1 h TTL Open-Meteo response
  for the air-quality mode (warm calls ~0.1 s vs ~5 s cold). Stale cache is
  served when Open-Meteo is unreachable.
- `ml_pipeline/data/canopy_ledger_cache.json` — per-ward tree-census
  aggregates (counts, canopy m2). The census scan of ~100k trees per ward
  takes ~13 s of CPU; warm calls ~0.3 s. Only the two canopy cover-% values
  are recomputed per request, from the cached canopy m2 and the plot area.

### Partial-evidence contract (must be surfaced in the UI)

- `evidence_status`: `COMPLETE` (4/4), `PARTIAL` (3/4), `INSUFFICIENT` (2/4),
  `UNAVAILABLE` (1/4 or 0/4).
- `decision_grade`: true only when COMPLETE.
- `impact_score` / `climate_score` / `risk_band` are `null` when fewer than 3
  factors are available. Never display a number in that case.
- Any factor with `status: "UNAVAILABLE"` must be shown as unavailable, never
  as zero or 100.
- `recommendations` for PARTIAL results are diagnostic only — the UI must label
  them "not decision-grade".

### Required artefacts on the backend host

| File | Size | Purpose |
|---|---|---|
| `ml_pipeline/data/epoch_cube.json` | 512 KB | Satellite indicators |
| `ml_pipeline/data/reference_layers.sqlite` | 21 MB | Ward polygons, storm drains |
| `ml_pipeline/data/tree_index.sqlite` | 1.1 GB | Census trees (green factor) |
| `ml_pipeline/data/flood_layers.sqlite` | 241 KB | OSM waterways (proximity only) |
| `ml_pipeline/config/regions/pune.json` | 20 KB | Region config (constants) |
| `ml_pipeline/config/materials.json` | 20 KB | Emission factors |
| `ml_pipeline/config/species.json` | 14 KB | Species table |

If `tree_index.sqlite` is absent, green is `UNAVAILABLE` (not zero). If
`epoch_cube.json` is absent, flood and heat are `UNAVAILABLE`.

A deployment that cannot ship the 1.1 GB index uses the committed 5-ward pack in
`ml_pipeline/data/demo/` (same file names, 311,666 trees). Selection is by
environment, not by code paths:

| Variable | Meaning |
|---|---|
| `PMC_DATA_DIR` | Directory holding `epoch_cube.json`, `reference_layers.sqlite`, `tree_index.sqlite`. Unset: `ml_pipeline/data` when it has a tree index, otherwise `ml_pipeline/data/demo`. |
| `PMC_CACHE_DIR` | Writable cache directory (air quality, canopy aggregates). Falls back to the system temp dir on read-only filesystems. |
| `PMC_DEMO_WARDS` | Comma-separated wards this deployment will score, e.g. `2,12,23,33,41`. Any other ward is rejected with `400` and a message naming the pack, rather than returning a partial score for a ward whose trees were never shipped. |

The demo pack is byte-for-byte equivalent for its five wards: same impact,
climate, evidence status, sub-scores, canopy area and recommendations as the
full index (see `DEPLOY.md`).


### Smoke test

```bash
python backend/python/test_bridge_smoke.py
```

Exits 0 on success. Tests ward 12 end-to-end through the bridge.

### Backend wiring (for the full-stack devs)

The Node side can call the bridge the same way it already does for extraction:

```js
const child = spawn(pythonCommand, [bridge], { cwd: repositoryRoot });
child.stdin.end(JSON.stringify({ mode: "score", ward: 12, ... }));
```

Parse stdout as JSON. The response shape above is what the frontend should
consume. Do NOT route scoring output through `validateMlOutput` (that
validator is for the extraction shape, not the scoring shape).
