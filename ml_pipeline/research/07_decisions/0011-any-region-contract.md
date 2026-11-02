# Decision 0011 — any-region contract

**Date:** 2026-11-02 (Session 7)
**Status:** accepted

## Contract
A second real city must supply, with accepted (non-provisional) status:
- design storm (return period, distribution, node, uncertainty)
- CN table + hydrologic soil group basis
- thermal reference + span + overpass
- carbon bands (sourced or explicitly house bands)
- green weights + tolerance
- composite weights
- census + tree index + ward polygons + KML
- epoch cube (night LST, land cover, elevation)

## Strict mode
`validate_config(cfg, strict=True)` rejects PROVISIONAL/UNSOURCED/PENDING/STALE/UNSOURCED_BANDS.
`score_site(..., strict=True)` refuses to score otherwise.

## Synthetic fixture
The 2x2 engine grid is labelled SYNTHETIC_FIXTURE and is not evidence of
city reuse. "Any region" remains unproven until a real second city is scored.
EOF