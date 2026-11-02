# Decision 0006 — green algebra and weights

**Date:** 2026-11-02 (Session 5)
**Status:** accepted

## Algebra
ground_vegetation = max(0, sat_veg_pct - canopy_cover_pct)
effective_green = 0.70 * canopy + 0.30 * ground
               = 0.30 * sat_veg + 0.40 * canopy  (when canopy <= sat_veg)

The marginal canopy weight is 0.40, not 0.70. The 70/30 split is house
judgment, not a literature coefficient (see config green.stratification_note).

## Exceedance of satellite vegetation
When canopy > sat_veg, ground clips to 0 and effective = 0.70*canopy, which
can exceed sat_veg. This is reported as `effective_green_exceeds_satellite`
and `resolution_mismatch_pts`; it is not silently absorbed. The 1 km satellite
cell vs site/polygon mismatch means a small plot can legitimately have more
canopy than its cell's vegetation fraction.

## Weights
0.70/0.30 unchanged. No new universal number introduced.

## Proposed canopy
`canopy_cover_pct_proposed` (post-decision) is used wherever a ledger exists;
`canopy_basis` reports proposed/existing/unavailable.
EOF