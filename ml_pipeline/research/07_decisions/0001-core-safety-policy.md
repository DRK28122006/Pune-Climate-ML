# Decision 0001 — core scoring safety policy

**Date:** 2026-11-02
**Session:** 2 (core scoring safety)
**Status:** accepted
**Scope:** missing land cover, seasonal bare soil, verdict gating, census total

## Context

The deterministic scorer can only be defensible if it refuses to answer when
the evidence is missing and if one catastrophic factor cannot be diluted by
three clean ones. Four defects made that untrue:

1. `score_project` read missing land cover as `0.0` for impervious, vegetation
   and water. Zero impervious plus zero vegetation is a *perfect* flood score,
   so an empty indicator dict produced `impact_score = 0.0`, `climate_score =
   100`, `Low` and `APPROVE`. Absence of evidence became evidence of safety.
2. The cube's annual land-cover partition already sums to one. The code added
   `bare_season_pct` as a fourth band anyway, and `area_weighted_cn` clamped the
   denominator to `1.0` without renormalising the numerators. The overlap was
   counted twice; 166 of 864 cells reached CN ≥ 99.99.
3. The recommendation used only the weighted composite. `heat = 99` with the
   other three factors at zero gives impact 29.7 and `APPROVE`; `carbon = 100`
   with the other three at zero can do the same. There was no per-factor veto.
4. The census total was `4,009,624`. The measured total is
   `16 × 250,000 + 9,623 = 4,009,623`.

## Decisions

### 1. Missing land cover is UNAVAILABLE, not zero

`impervious_pct`, `vegetation_pct` and `water_pct` are mandatory numeric inputs
to `compute_flood`. `None`, NaN or a non-numeric value withholds the factor:

- `sub_scores["flood"] = None`
- `factors["flood"]["status"] = "UNAVAILABLE"`
- `flood` appears in `missing_factors`
- the factor's weight is redistributed over the available factors

The same rule applies to the CLI. The old implicit fallbacks (70 % impervious,
24 % vegetation) are gone. A caller who wants a scenario can pass
`--impervious`, `--vegetation`, `--water` explicitly, and the result records
`landcover_source = "user_supplied_assumption"` and the assumed field names.

### 2. Seasonal bare is reported, never added to the annual partition

The flood factor now takes:

- `bare_pct` — the annual fourth band from the same partition as built,
  vegetation and water
- `bare_season_pct` — a seasonal overlay, reported as `seasonal_bare_pct`

`seasonal_bare_used` is always `false`. `compute_flood` reports
`landcover_sum`, `landcover_sum_within_bounds` and `landcover_warning`. Above a
0.001 tolerance, the result is flagged rather than silently capped. The curve
number itself renormalises the over-sum explicitly, so the arithmetic remains
an areal mean and cannot saturate. On the live cube, CN ≥ 99.99 now occurs in
0 of 864 cells.

### 3. Per-factor veto and partial-result rule

The composite weights are unchanged: flood 0.30, heat 0.30, green 0.20,
carbon 0.20. They answer “what is the average impact?”, not “is any single
factor disqualifying?”. The verdict therefore adds a second, independent gate:

- any factor at or above its review threshold → `REVIEW`
  - default threshold: 80
  - flood: 50, because the current flood scale tops out near 56.6 (C6). An 80
    threshold would make the flood veto unreachable until Session 4 normalises
    the scale.
- carbon band `Very High` → `REVIEW`
- a partial result (any factor unavailable) → `REVIEW`
- blocking material-sourcing / unknown-material conditions → `REVIEW`

Only a complete result with every factor below its threshold and a composite
below 30 can `APPROVE`. This is deliberately conservative: the policy can cost
a false review, but it cannot approve a single-factor catastrophe.

The thresholds live in `ml_pipeline/config/regions/pune.json`
(`decision_policy`) so a region can change them without editing the scorer.

### 4. Census total is 4,009,623

The loaded index count is unchanged at 4,009,623. The citywide total is the
same measured number: 16 complete 250,000-row parts plus 9,623, with zero
duplicate ids. The earlier 4,009,624 was an off-by-one, not a dropped tree. The
coverage line now reads `4,009,623 unique`, not `4,009,623 of 4,009,624`.

## Why the weights did not change

Changing weights would be a methodological decision that requires its own
validation and would make every prior score incomparable. The defect was not
that flood and heat are weighted 0.30; it was that the verdict ignored the
factor scores entirely. The veto is additive and transparent, and the
composite remains the same arithmetic mean for every caller.

## Consequences

- An empty or cube-less assessment now yields `REVIEW`, not `APPROVE`.
- A partial assessment remains useful as a diagnostic but can never be a
  decision.
- The flood factor is no longer computed from seasonal bare, so flood scores
  drop for cells where the seasonal overlay overlapped the annual partition.
- Existing generated artifacts under `ml_pipeline/data/` still carry the old
  census scalar until Session 3 regenerates them. They are snapshots, not live
  code or config.

## Verification

```bash
python3 ml_pipeline/tests/test_scoring.py     # 65/65 passed
```

`pytest` is not installed in this checkout; the test file is runnable directly
and the command above is the exact run used here.
