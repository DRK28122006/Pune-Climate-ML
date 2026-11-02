# Decision 0009 — GFA vs footprint inputs

**Date:** 2026-11-02 (Session 5)
**Status:** accepted

## New contract
- plot_area_m2 (total site area)
- impervious_footprint_m2 (<= plot)
- total_gfa_m2 (>= footprint)

Flood uses footprint/plot for imperviousness. Carbon divides by GFA. Green
uses plot and proposed canopy.

## Backward compatibility
Legacy `builtUpAreaSqm`/`plotAreaSqm` fall back to footprint/GFA/plot when
the new keys are absent, labelled as legacy. No guessing beyond that.
EOF