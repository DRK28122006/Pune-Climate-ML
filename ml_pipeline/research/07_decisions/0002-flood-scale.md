# Decision 0002 — flood scale (Option B, physical excess-runoff fraction)

**Date:** 2026-11-02 (Session 4)
**Status:** accepted

## Choice
Option B: keep the physical excess-runoff fraction; do not rescale to 0–100.
The flood score remains `(Q_site − Q_baseline) / P × 100` with P = 214 mm,
modified by slope and engineered-drainage multipliers. The attainable maximum
(at CN 100, before slope/drainage) is reported as `attainable_score_max`
(~56.6) in every flood result, and `flood_scale_policy` documents the choice.

## Why not Option A
Rescaling to 0–100 would require recalibrating composite weights and the
risk bands, making every prior score incomparable, and would hide the physical
ceiling. The defect was presentation (calling a fraction “0–100”), not physics.

## Consequences
- Flood cannot reach the 60 “High” band under this storm; the per-factor
  veto threshold stays 50 (Session 2 decision note).
- Composite weights unchanged (0.30/0.30/0.20/0.20).
- `attainable_score_max` and `flood_scale_policy` added to flood output.
EOF