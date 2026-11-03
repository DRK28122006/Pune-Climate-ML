# Handoff — Session 4 (flood and heat physics)

**Date:** 2026-11-02
**Branch:** main (committed locally, 78335ef)

## Changed files
- `ml_pipeline/core/scoring.py` — water-invariant baseline CN; `fluvial_flood: NOT_MODELLED`; `attainable_score_max`, `flood_scale_policy`; heat day fallback → UNAVAILABLE (LEGACY_DAY); per-cell night reference fallback; elevation reported, not corrected; `heat_scale` label.
- `engine/score.py` — pass `lst_night_reference_c`.
- `ml_pipeline/tests/test_scoring.py` — water cell test, day-fallback test, heat scale label test; updated per-cell-reference test to new policy.
- Decision notes: `0002-flood-scale.md`, `0003-flood-plain.md`, `0004-heat-elevation.md`, `0005-heat-overpass.md`.

## Verified
- `pytest ml_pipeline/tests`: 68 passed.
- `test_scoring.py`: 68/68.
- `engine/tests/test_engine.py`: 23/23.

## Flood
- Option B chosen: physical excess-runoff fraction retained; attainable max ~56.6 reported.
- Water held invariant in baseline (was vegetated).
- Fluvial flood explicitly NOT_MODELLED (layers missing).

## Heat
- Night-only; day fallback UNAVAILABLE/LEGACY_DAY.
- 17.96 °C and 5.0 °C unchanged; percentile scale labelled, not a physical magnitude.
- Elevation confounding reported, not corrected (no elevation-banded reference).

## Session 5/3 needs
- Green/carbon untouched; green scale floor 30 remains (Session 5).
- Validation artifacts use night mode already; flood scale policy now in output.
- Flood veto threshold stays 50 until flood normalised.
EOF
echo done