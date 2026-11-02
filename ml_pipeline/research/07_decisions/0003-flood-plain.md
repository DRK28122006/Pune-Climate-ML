# Decision 0003 — flood-plain exposure (not modelled)

**Date:** 2026-11-02 (Session 4)
**Status:** accepted

## Decision
Fluvial flood-plain exposure is NOT modelled. PMC/WRD blue-red flood lines,
watercourse distance, and elevation layers are not available in this checkout
(parks/nallas KMLs and reference_layers.sqlite are missing). No synthetic
penalty is added.

## Implementation
- `compute_flood` returns `fluvial_flood: "NOT_MODELLED"` in every result.
- `floodplain_penalty_applied` is not added; only the field above.
- Engineered-drain proximity (existing) is unchanged and is NOT a flood-plain
  proxy. Proximity to a natural nala raises risk; only engineered outfalls
  lower it.

## Revisit
When `pune_nallas.kml` and flood-line layers are available, implement a
distance-to-watercourse + elevation penalty and update this note.
EOF