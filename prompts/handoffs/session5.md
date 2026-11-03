# Handoff — Session 5 (green, carbon, GFA)

**Date:** 2026-11-02
**Branch:** main (committed locally, 704f930)

## Changed files
- `ml_pipeline/core/scoring.py` — green algebra/exceedance/resolution fields; carbon carbon-share gate, withheld intensity/band null, empty BOQ not zero; GFA/footprint handling.
- `ml_pipeline/core/canopy.py` — proposed canopy value returned.
- `ml_pipeline/intake/validate.py` — plot_area_m2/impervious_footprint_m2/total_gfa_m2, validation; unit conversion (kg or m3 with documented density) or reject.
- `ml_pipeline/tests/test_scoring.py` — added 5% Al test, empty BOQ, GFA, proposed canopy.
- Decision notes 0006-0009.

## Verified
- `pytest ml_pipeline/tests`: 72 passed.
- `test_scoring.py`: 72/72.

## Green
- Marginal canopy weight explicit (0.40); 70/30 unchanged.
- effective_green_exceeds_satellite reported, not silently absorbed.
- Proposed canopy used when ledger present; canopy_basis reported.

## Carbon
- Withholds on mass or carbon-share (upper bound) > 10%.
- Double counting is blocking issue, not silent subtraction.
- Withheld score: intensity and band null; empty BOQ not zero-carbon.
- Units converted (m3 concrete/brick) or rejected.

## GFA
- Flood uses footprint/plot; carbon divides by GFA; backward compat labelled legacy.

## Session 6 needs
- Report must describe green algebra and carbon threshold/bands.
- Report must use GFA-aware carbon intensity.
- Update report only through Session 6.
EOF
echo done