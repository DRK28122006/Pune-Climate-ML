# Deployment

Two services, because one of them needs Python.

| Piece | Where | Why |
| --- | --- | --- |
| Frontend (Vite) | Vercel | Static build, no server code. |
| Backend (Express + `ml_bridge.py`) | Docker host (Render blueprint included) | `POST /api/v1/score`, the canopy ledger, air quality and the Disha assistant all shell out to `python3`. Vercel's Node runtime has no Python, so those endpoints return 502 there. |

Everything else on Vercel is static JSON that ships with the repo: the Engine
map, Overview, Air Quality, Green Cover, Heat, Flood and the Scenario Planner.

## Backend (Render)

1. Render → **New → Blueprint** → pick this repository. `render.yaml` is
   detected automatically.
2. Apply. The service builds from `Dockerfile` (Node 20 + python3 + shapely +
   pyproj) and ships the 5-ward demo pack only.
3. Fill the three `sync: false` variables:
   - `FRONTEND_ORIGIN` — the Vercel URL, e.g. `https://pune-climate-ml.vercel.app`.
     Comma-separate preview and production URLs; the API accepts a list.
   - `GROQ_API_KEY` — primary model for Disha.
   - `GEMINI_API_KEY` — fallback model.
4. Wait for `GET /api/health` to return `200`:

   ```json
   {"status":"ok","mlMode":"fixture","database":"file","fileStorage":"local","queues":"synchronous"}
   ```

   `mlMode` stays `fixture` and is unused by the scoring path; scoring always
   runs the real bridge.

Any Docker host works the same way (Railway, Fly, a VPS):

```
docker build -t disha-backend .
docker run -p 8080:8080 \
  -e AUTH_REQUIRED=false \
  -e FRONTEND_ORIGIN=https://your-frontend \
  -e JWT_ACCESS_SECRET=<32+ chars> \
  -e JWT_REFRESH_SECRET=<32+ chars> \
  -e GROQ_API_KEY=... -e GEMINI_API_KEY=... \
  disha-backend
```

## Frontend (Vercel)

Set one environment variable on the frontend project and redeploy:

```
VITE_API_URL=https://<backend-host>/api/v1
```

Leave it unset only when the API is served from the same origin.

## Data pack

`ml_pipeline/data/demo/` holds the deployable subset: wards **2, 12, 23, 33 and
41**. It is regenerated from the full local data with:

```
python ml_pipeline/data/extract_demo_wards.py
```

Rules that pack must keep:

- `reference_layers.sqlite` is copied verbatim. The `wards` table is 214 KB and
  scoring resolves every site centroid against **all** 41 rings; cutting it to
  five makes ward 2 fail because its centroid legitimately falls inside ward 6.
- Trees are selected by point-in-polygon against the five ward rings, not by
  `census_ward`. Census blocks are coarse — ward 12 holds 69,980 trees by
  geometry and only 31,480 carry `census_ward = 12`. A census-labelled cut
  halves the canopy and turns green cover into `UNAVAILABLE`.

`PMC_DATA_DIR` selects the data directory, `PMC_CACHE_DIR` the writable cache
directory, and `PMC_DEMO_WARDS` the wards the deployment will score. With
`PMC_DEMO_WARDS` set, any other ward returns a 400 that names the pack, instead
of reporting a partial score for a ward whose trees were never shipped.

## Verified against local

Identical results for all five wards (default proposal, both stacks):

| Ward | Impact | Climate | Evidence |
| --- | --- | --- | --- |
| 2 | 32.6 | 67.4 | PARTIAL |
| 12 | 58.8 | 41.2 | COMPLETE |
| 23 | 78.5 | 21.5 | COMPLETE |
| 33 | 13.7 | 86.3 | PARTIAL |
| 41 | 14.6 | 85.4 | PARTIAL |

First score on a freshly started container is 0.5–0.7 s, not 4–12 s: the canopy
ledger for the five wards is precomputed into
`ml_pipeline/data/demo/canopy_ledger_cache.json` and baked into the image, so a
cold host never rebuilds it. Air quality is 4.7 s cold and cached for an hour.

`PMC_CACHE_DIR` must point at the same directory as the pack
(`/app/ml_pipeline/data/demo`) or the baked ledger is ignored and every first
score pays the census scan again.
