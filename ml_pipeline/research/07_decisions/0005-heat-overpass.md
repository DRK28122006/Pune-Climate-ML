# Decision 0005 — heat overpass (Terra/Aqua averaged night)

**Date:** 2026-11-02 (Session 4)
**Status:** accepted

## Current state
The cube's `lst_night_mean_c` averages Terra 10:30 pm and Aqua 1:30 am MODIS
night LST into one value. No separate overpass field exists in the cube.

## Decision
No change in this session: splitting the overpasses requires a cube rebuild
(build_cube.py / GEE) that is not run here. The averaged value is retained and
labelled as such in the cube source metadata. If a single-overpass (prefer Aqua
1:30 am) product is needed, rebuild the cube with separate bands and update
this note.

## Day fallback
The day fallback is now UNAVAILABLE (LEGACY_DAY), not a scored factor. Daytime
surface contrast has no usable signal (two measured failures on record).
EOF