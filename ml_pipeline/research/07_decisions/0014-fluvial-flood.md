# Decision 0014 — Fluvial flood: source tier and integration contract

**Date:** 2026-11-03 (Session 14)  
**Status:** accepted (evidence + contract; no scorer change)

## 1. Decision

Selected tier: **PROXIMITY_ONLY** (OSM waterways via Overpass). No regulatory
flood line, observed inundation, or global modelled hazard was obtainable in
this environment, so `floodplain_status()` returns `PROXIMITY_ONLY` with
`in_floodplain = null`. There is no floodplain-exposure (inundation) claim.

## 2. Why this tier

- Official regulatory flood line (PMC/WRD blue-red): **UNAVAILABLE**. No open
  download URL exists; the layer is supplied by PMC/WRD on request. Rejected as
  unavailable, not fabricated.
- Observed inundation (Sentinel-1 SAR, Copernicus EMS, UNOSAT): **BLOCKED**.
  Requires GEE (`ee` not installed), a Copernicus account, or a manual request.
- Global modelled hazard (JRC 100-year): **BLOCKED**. Requires a Copernicus
  account / manual download; no no-key URL confirmed.
- OSM waterways: **ACQUIRED**, no key, ODbL-1.0. Chosen as the only defensible
  source. It is proximity only and is labelled as such everywhere.

## 3. What it does and does not measure

- **Does:** distance from a point to the nearest OSM watercourse.
- **Does not:** inundation extent, depth, probability, or whether a parcel
  actually floods.
- Proximity ≠ inundation. A nalla 40 m away is a risk signal; it is not proof
  the parcel floods. Never promote proximity to a floodplain claim.

## 4. Integration contract for the later session (propose, do not implement)

- Add a `floodplain` block to the flood factor output using the stable shape:
  `{status, in_floodplain, nearest_watercourse_m, source, licence, confidence, note}`.
- If `in_floodplain is True` (requires an extent tier, not the current OSM
  tier): add a `blocking_issues` entry of type `floodplain_exposure`. That
  forces `REVIEW`. **No numeric multiplier.**
- If `status == "PROXIMITY_ONLY"`: report as context only, **do not** force
  REVIEW.
- If `status == "UNAVAILABLE"`: change nothing.
- Wiring into `score_project` is deferred to a review-gated session.

## 5. Re-baseline impact

Under the proposed rule (extent tier only), with the current OSM-only layer no
ward or site flips to `REVIEW`: `in_floodplain` is `null` for all 41 wards and
8 sites. Counts: wards flipping = 0; sites flipping = 0. If a regulatory flood
line is later acquired, recompute and update this note.

## 6. Rollback

Disable by not calling `floodplain.floodplain_status()` in the scorer; the
scorer continues to emit `fluvial_flood: "NOT_MODELLED"` as today. No weight,
band, or constant changes. Remove the `floodplain` block from output.
