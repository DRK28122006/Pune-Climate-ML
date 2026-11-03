# Session 2 — Core scoring safety

**Suggested model:** DeepSeek  
**Dependencies:** none  
**Owns:** `ml_pipeline/core/scoring.py` safety changes, `ml_pipeline/tests/test_scoring.py`, `ml_pipeline/config/regions/pune.json` census total, `ml_pipeline/core/geometry.py` census total  
**Do not touch:** flood/heat/green/carbon methodology beyond the specific fixes below, validation artifacts, report, web app

Read `prompts/00_context.md` first.

## Mission

Fix the four problems that can make the scorer produce a confidently wrong answer: missing-data zero fill, seasonal-bare double counting, no per-factor veto, and the census off-by-one.

This session is about **safety and data integrity**, not about redesigning the physics. Do not normalize scales, change composite weights, or replace the heat/green/carbon methods. Those belong to Sessions 4 and 5.

## Fix C1 — missing land cover must not become a perfect score

Current behaviour:

```python
imperv = indicators.get("impervious_pct", 0.0)
veg = indicators.get("vegetation_pct", 0.0)
water = indicators.get("water_pct", 0.0)
```

This makes empty indicators produce flood `0.0` and CN `60.0`, which can produce `impact 0`, `climate 100`, `Low`, and `APPROVE`.

Required:

- Flood must require explicit numeric `impervious_pct`, `vegetation_pct`, and `water_pct`. `None` or absent means flood is `UNAVAILABLE`, not zero.
- Do not default missing land cover to zero anywhere in `score_project`.
- Do not let a partial score produce `APPROVE` or `REJECT_OR_REDESIGN`. Partial results must be `REVIEW`.
- Keep `complete: false` and `missing_factors` accurate.
- Remove or clearly relabel the CLI fallbacks that use `70` impervious and `24` vegetation when no cube exists. If they remain for explicit user scenarios, they must be marked as supplied assumptions, not measured data.

Acceptance:

```python
r = score_project(site, {}, region, materials, ledger=None)
assert r["sub_scores"]["flood"] is None
assert r["recommendation"]["recommendation"] == "REVIEW"
```

Also test a cell with `impervious_pct=None`, `vegetation_pct=None`, or `water_pct=None`.

## Fix C2 — seasonal bare soil is double-counted

The annual partition already sums to one. `bare_season_pct` is an additional seasonal estimate, not a residual.

Current problem:

- `area_weighted_cn` adds `bare_season_pct` as a fourth band.
- It clamps only `accounted` to 1.0.
- It does not renormalise the fractions or subtract seasonal bare from vegetation.
- 847/864 cells sum above 1; 166 cells reach CN ≥ 99.99.

Required:

- Use the annual `bare_pct` in the flood calculation, or
- If seasonal bare is genuinely preferred, subtract it from vegetation/crops/shrub or explicitly renormalise all four bands.
- Remove the silent `accounted = 1.0` clamp.
- Add a build-time or scoring-time gate that fails or reports loudly when the land-cover fractions sum above 1.0.
- Report `landcover_sum` and `seasonal_bare_used` in the flood result.
- Update every caller that passes `bare_season_pct`: `engine/score.py`, `ml_pipeline/cli.py`, and any stress/E2E builders.

Acceptance:

- The 864-cell cube no longer produces 166 saturated CN cells from seasonal bare.
- A cell whose fractions sum above 1.0 is reported, not silently absorbed.
- Add a regression test that uses a synthetic cell with an overlapping seasonal bare value.

## Fix C4 — no per-factor veto

Current behaviour:

- `_decision` thresholds only the weighted composite.
- Heat 99 with all others 0 gives impact 29.7 and `APPROVE`.
- Carbon 100 gives impact 20 and `APPROVE`.

Required:

- Add a documented per-factor review policy. Suggested starting point:
  - any factor ≥ 80 → `REVIEW`
  - carbon band `Very High` → `REVIEW`
  - any factor unavailable → `REVIEW` if the result is partial
- Do not silently change the composite weights. Keep the arithmetic mean unless a decision note says otherwise.
- Make the policy configurable in `pune.json` if practical, but do not hide it.
- Add tests for single-factor extremes: heat 99, carbon 100, green 100, flood at its ceiling.
- Make sure a legitimate low-impact complete result can still `APPROVE`.

Acceptance:

- `heat=99, others=0` → `REVIEW`.
- `carbon=100, others=0` → `REVIEW`.
- A complete result with all factors below the review threshold can still `APPROVE`.
- Tests cover partial, complete, and single-factor extremes.

## Fix C13 — census off-by-one

`16 × 250,000 + 9,623 = 4,009,623`, not `4,009,624`.

Fix:

- `ml_pipeline/config/regions/pune.json` `trees.census_total_city_trees`
- `ml_pipeline/core/geometry.py` fallback constant
- any duplicate in `docs/make_report.py` or README
- any test or artifact that asserts the old total

Do not change `loaded_trees`; `4,009,623` loaded is correct. The total is the wrong number.

Acceptance:

- `grep -R "4009624"` finds no live code/config/docs references.
- The coverage line reads `4,009,623 unique`, not `4,009,623 of 4,009,624`.

## Tests to add

Add tests in `ml_pipeline/tests/test_scoring.py` or a new focused test file:

1. Empty indicators → flood `None`, verdict `REVIEW`.
2. Missing cube → no flood score, no approval.
3. Null land-cover field → flood `None`.
4. Seasonal bare overlap → land-cover sum reported; no silent clamp.
5. Heat 99 alone → `REVIEW`.
6. Carbon 100 alone → `REVIEW`.
7. Complete low-impact result → `APPROVE`.
8. Census total is `4,009,623`.

Run:

```bash
.venv/bin/python -m pytest ml_pipeline/tests -q
.venv/bin/python ml_pipeline/tests/test_scoring.py
```

If a test depends on missing data, mark it clearly or skip with a reason. Do not fake the data.

## Do not

- Do not normalize flood or green to 0–100. That is Session 4.
- Do not change the 214 mm storm, 17.96 °C reference, or 5.0 °C span.
- Do not change carbon bands or factors.
- Do not change the 70/30 green weights.
- Do not regenerate validation JSONs.
- Do not edit `frontend/` or `backend/`.
- Do not weaken or delete existing tests.

## Decision note

Write `ml_pipeline/research/07_decisions/0001-core-safety-policy.md` (create directories if needed) explaining:

- why missing land cover is `UNAVAILABLE`
- why partial results are `REVIEW`
- the per-factor threshold chosen
- why the composite weights were not changed

## Handoff

Report:

- Files changed.
- Exact test commands and results.
- Before/after behaviour for empty indicators and single-factor extremes.
- Any caller that still passes `bare_season_pct`.
- What Session 3 and Session 4 need to know.
