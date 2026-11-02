# Decision 0007 — carbon unknown-material threshold

**Date:** 2026-11-02 (Session 5)
**Status:** accepted

## Mass and carbon share
Withholding uses both mass share and a conservative carbon-share upper bound.
Unknown mass is assumed to carry the largest known emission factor; if either
share exceeds 10%, the score is withheld. Both shares are reported
(`unknown_mass_pct`, `unknown_carbon_share_pct`,
`unknown_carbon_upper_bound_kgco2e`).

## Double counting
Cement + ready-mix concrete is a blocking issue (`carbon_double_count`),
not a silent subtraction. The score is still computed but the verdict is
REVIEW. Line items and the rule are named in the warning.

## Withheld score
When withheld, `intensity_kgco2e_m2` and `band` are null (no partial-known
reporting). Empty BOQ is not zero-carbon.
EOF