# Flood Data Status — Session 14

**Date:** 2026-11-03  
**Session:** 14  
**Scope:** fluvial floodplain exposure source audit and acquisition.

## Summary

- **Selected tier:** `PROXIMITY_ONLY` (OSM waterways via Overpass). No regulatory
  flood line, no observed inundation, no global modelled hazard was obtainable.
- **Acquired:** `ml_pipeline/data/flood_layers.sqlite` (waterways table, 172
  features: 97 stream, 40 canal, 23 drain, 12 river). Derived, gitignored.
- **Blocked:** PMC/WRD blue-red flood line, JRC global flood hazard, Sentinel-1
  observed inundation, Copernicus EMS, UNOSAT — all require accounts/GEE/manual
  requests not available in this environment.
- **Not claimed:** floodplain exposure (inundation) is NOT measured. Only
  watercourse proximity is available. `floodplain_status()` returns
  `PROXIMITY_ONLY` with `in_floodplain = null`.

## Source audit

| source | measures | resolution | licence | access | status | why |
|---|---|---|---|---|---|---|
| Local disk search (`/home/mesh/Pictures`, `/home/mesh/Downloads`, `/home/mesh/Documents`, repo) for `*.kml/*.kmz/*.geojson/*.shp/*.gpkg` matching flood/nalla/river/drain/blue/red/floodline/watercourse | (none found) | n/a | n/a | local file | UNAVAILABLE | Only `pmc_stormwater_drains.kmz` (engineered drains) matched; no flood-line or nalla layer anywhere on disk. |
| PMC / Maharashtra WRD blue-red flood line | Floodplain extent (regulatory) | 1:4000 (typical) | unknown | manual request / PMC office | UNAVAILABLE | No open download URL found; layer is provided by PMC/WRD on request. Exact blocker: PMC/WRD must supply the blue-red flood-line KML/GPKG. |
| OSM waterways via Overpass (maps.mail.ru mirror) | Proximity only (watercourse lines) | ~1-10 m (OSM) | ODbL-1.0 | open download (no key) | ACQUIRED | Query run 2026-11-03 over bbox 18.39,73.73,18.60,74.06; 172 unique waterways. Raw response tracked at `ml_pipeline/data/flood_layers_raw.json` (sha256 `4ad69abcc2982e1cdc434b96f2960ae0139d6c1d35210a89a3510fcc363b87e6`). |
| JRC global flood hazard (100-year) | Modelled inundation extent | 30 m / 90 m | unknown / Copernicus | account or manual request | BLOCKED | Requires Copernicus account / manual download; no no-key URL confirmed. Credential needed: Copernicus Data Space Ecosystem account. |
| Copernicus EMS (rapid mapping) | Observed inundation | event-based | Copernicus terms | account required | BLOCKED | Requires Copernicus account and a specific EMS activation ID. |
| UNOSAT flood maps | Observed inundation | event-based | UN terms | manual request | BLOCKED | Requires manual request / no stable no-key bulk download. |
| Sentinel-1 observed inundation (GEE) | Observed inundation | 10 m | GEE terms | GEE (`ee`) account | BLOCKED | `ee` (Google Earth Engine) is not installed in this environment; needs GEE project + authentication. |
| NASA POWER / ERA5 (air temperature) | Not flood | n/a | n/a | n/a | not applicable | Used for heat corroboration only (see HEAT_CROSSCHECK.md). |

## Acquired layer

- **Path:** `ml_pipeline/data/flood_layers.sqlite` (gitignored, `*.sqlite`)
- **Bytes:** 241664
- **SHA256:** `5c418349cacd0d008770f266ac581c021c0bdff92427cecd200d3dd30f8bb9e8`
- **Table:** `waterways (id, kind, name, geometry_json, source, retrieved_at, licence)` + `meta`
- **Rows:** 172 (stream 97, canal 40, drain 23, river 12)
- **Source:** `osm-overpass-2026-11-03`
- **Retrieved at:** 2026-11-03
- **Licence:** ODbL-1.0 (OpenStreetMap contributors)
- **Raw snapshot:** `ml_pipeline/data/flood_layers_raw.json` (377,059 bytes,
  sha256 `4ad69abcc2982e1cdc434b96f2960ae0139d6c1d35210a89a3510fcc363b87e6`),
  tracked.
- **Builder:** `ml_pipeline/data/build_flood_layers.py`, tracked.
- **Rebuild command:**
  ```
  python ml_pipeline/data/build_flood_layers.py \
      --expect-sha256 5c418349cacd0d008770f266ac581c021c0bdff92427cecd200d3dd30f8bb9e8
  ```
  The build is deterministic from the tracked raw snapshot. The current DB's
  `meta.raw_path` is `ml_pipeline/data/flood_layers_raw.json`; rebuilding from
  the original scratch path changes only that metadata row, not the 172
  waterway rows.

## What this layer does and does not measure

- **Does:** distance from a point to the nearest OSM watercourse (river/stream/canal/drain).
- **Does not:** inundation extent, flood depth, flood probability, or whether a
  parcel actually floods. OSM waterways are a **proximity** signal only.
- A site 40 m from a nalla is a risk signal; it is not proof the parcel floods.
- Promoting proximity to a floodplain claim is forbidden (decision 0003 rule).

## Probe

Run: `python ml_pipeline/data/floodplain_probe.py`  
Output: `/tmp/opencode/floodplain_probe.json` (no tracked writes).  
Result: all 41 wards and 8 sites return `PROXIMITY_ONLY` with a nearest-watercourse
distance; `in_floodplain` is `null` for every row.
