# Multi-session ML work plan

This folder contains one self-contained prompt per workstream. Start each session with exactly:

> Read `prompts/sessionN.md` and do the work.

Sessions 1–8 are the original build pass and are already committed. Their handoffs are in `prompts/handoffs/`. Sessions 9–13 are the repair/sign-off pass created after the independent review.

Read `prompts/00_context.md` first, and for Sessions 9–13 also read `prompts/00_review_findings.md`.

## Current repair pass

| # | Session | Suggested model | Depends on | Main owner files |
|---|---|---|---|---|
| 9 | Partial-data contract and recommendation safety | DeepSeek V4.1 Flash | none | `core/scoring.py` partial/decision, `recommendations.py`, `report/render.py`, `report/narrative.py`, `engine/score.py`, tests |
| 10 | Data restoration and dependency gate | Beam Free | Session 9 | census/, `tree_index.sqlite`, `reference_layers.sqlite`, parks/nallas KMLs, cube slope |
| 11 | Validation harness truth pass | DeepSeek V4.1 Flash | Sessions 9 and 10 | `validate_wards.py`, `validate_sites.py`, validation JSONs, data/e2e tests |
| 12 | Artifact and report regeneration | Beam Free | Session 11 | `docs/example_assessment.json`, `docs/make_report.py`, PDF, `README.md`, `stress/`, `e2e/`, manifest |
| 13 | Final ML audit and engine sign-off | Beam Free (DeepSeek review) | Sessions 9–12 | `ml_pipeline/research/08_signoff/` |

Strict order:

```text
9 → 10 → 11 → 12 → 13
```

Do not run these in parallel. Only Session 9 may edit `ml_pipeline/core/scoring.py`. Sessions 10–13 must not change scoring formulas.

If Session 10 is blocked by missing census or KMLs, stop and report the block. Session 11 can still fix the harness, but green/drainage/slope cannot be signed off. Do not fabricate data to unblock the chain.

## Post-sign-off pass (flood evidence and heat corroboration)

Sessions 14 and 15 run **in parallel**. They own disjoint files, and neither
changes a score. Session 16 is review-gated and must not start until 14 and 15
are reviewed.

| # | Session | Suggested model | Runs with | Changes a score? | Main owner files |
|---|---|---|---|---|---|
| 14 | Fluvial evidence, slope decision, heat corroboration | Beam Free | 15 | No | `research/07_decisions/0014-0016`, `05_sources/FLOOD_DATA_STATUS.md`, `04_validation/HEAT_CROSSCHECK.md`, new `core/floodplain.py`, `data/floodplain_probe.py` |
| 15 | Slope derivation and impact preview | DeepSeek V4.1 Flash | 14 | No | new `data/derive_slope.py`, `data/slope_preview.py`, `tests/test_slope.py`, `data/slope_band.json` |
| 16 | Integration and controlled re-baseline | TBD after review | — | Yes | deferred until 14/15 are reviewed |

Why parallel: Session 14 is source- and decision-heavy; Session 15 is numerical
engineering. They do not share a file. Neither may edit `scoring.py`, the config
constants, the validation JSONs, or the report.

Why integration waits: fluvial and slope both change verdicts or scores. Turning
both on at once without a controlled re-baseline makes every stored artifact
incomparable. Session 16 applies only what the review approves, one change at a
time, each with its own decision note and artifact regeneration.

Starter messages:

```text
Read prompts/session14.md and do the work.
Read prompts/session15.md and do the work.
```

Do not start Session 16 until both handoffs and the diffs are reviewed.

## Original build pass (completed)

| # | Session | Suggested model | Status | Main owner files |
|---|---|---|---|---|
| 1 | Research vault and data restoration | Beam Free | committed | `ml_pipeline/research/**`, `.gitignore` |
| 2 | Core scoring safety | DeepSeek | committed | `ml_pipeline/core/scoring.py` safety, tests, census total |
| 3 | Validation and provenance | GLM 5.3 Flash | committed | `validate_wards.py`, `validate_sites.py`, validation JSONs |
| 4 | Flood and heat physics | Beam Free | committed | flood/heat parts of `scoring.py`, `pune.json`, derive scripts |
| 5 | Green, carbon, and GFA | Mimo V2.6 Flash Free | committed | green/carbon parts of `scoring.py`, `canopy.py`, `materials.json`, intake |
| 6 | Legal, report, and narrative | Mimo V2.6 Flash Free | committed | `report/**`, `docs/**`, README, legal labels |
| 7 | Engine, any-region, and CI | GLM 5.3 Flash | committed | `engine/**`, CI, provenance tests |
| 8 | Web demo honesty (optional) | DeepSeek or any | committed | `frontend/**`, `backend/**` |

The original execution order was:

```text
1 → 2 → 3 → 4 → 5 → 7 → 6 → 8 (optional)
```

Do not rerun Sessions 1–8. Use their handoffs for history.

## File ownership

### Repair pass

| File / area | Owner |
|---|---|
| `ml_pipeline/core/scoring.py` | Session 9 only |
| `ml_pipeline/core/recommendations.py` | Session 9 only |
| `ml_pipeline/report/render.py`, `narrative.py` | Session 9 |
| `engine/score.py` partial propagation | Session 9 |
| `ml_pipeline/data/census/`, tree index, reference layers | Session 10 |
| `ml_pipeline/data/validate_*.py`, validation JSONs | Session 11 |
| `ml_pipeline/tests/test_data_integrity.py`, `test_e2e_ward12.py` | Session 11 |
| `docs/example_assessment.json`, `docs/make_report.py`, PDF, README, manifest | Session 12 |
| `ml_pipeline/research/08_signoff/` | Session 13 |
| `research/07_decisions/0014-0016`, flood/heat evidence notes | Session 14 |
| new `core/floodplain.py`, `data/floodplain_probe.py`, `data/flood_layers.sqlite` | Session 14 |
| new `data/derive_slope.py`, `data/slope_preview.py`, `tests/test_slope.py`, `data/slope_band.json` | Session 15 |
| `frontend/`, `backend/` | Not in the repair pass |

### Original build pass

| File / area | Owner order |
|---|---|
| `ml_pipeline/core/scoring.py` | S2 → S4 → S5 → S9 |
| `ml_pipeline/core/canopy.py` | S5 → S6 (coordinate) |
| `ml_pipeline/config/regions/pune.json` | S2 → S4 → S5 |
| `ml_pipeline/tests/test_scoring.py` | S2 → S4 → S5 → S9 |
| `ml_pipeline/data/validate_*.py`, validation JSONs | S3 → S11 |
| `ml_pipeline/research/**` | S1 → S9/S10/S12/S13 (new notes/status only) |
| `engine/**` | S7 → S9 (partial propagation only) |
| `report/**`, `docs/**`, `README.md` | S6 → S9 (partial report) → S12 |
| `frontend/**`, `backend/**` | S8 only; not in the repair pass |

Use separate git worktrees or branches. Do not run `git reset --hard`, `git checkout -- .`, `git clean -fd`, or delete files you did not create.

## Global rules

- Preserve uncommitted ML work. Do not reset or clean the tree.
- Do not weaken tests to make a fix pass. Optional data tests may skip with a clear reason, not pass silently.
- Do not change measured constants — `214 mm`, `17.96 °C`, `5.0 °C`, carbon factors — without evidence and a decision note.
- Do not silently rescale weights, spans, or carbon bands. Write a decision note in `ml_pipeline/research/07_decisions/` first.
- Do not invent legal citations. Mark anything unverified as `[U]` and say what needs checking.
- Do not commit the 1.2 GB census or the tree index.
- Do not hand-edit generated PDFs or validation JSONs. Regenerate them.
- If a task is blocked by missing data, stop and report the exact missing file and rebuild command. Do not fabricate a substitute.
- Missing data is `UNAVAILABLE`, never zero and never a perfect score.
- One session at a time. Commit after each session and write a handoff to `prompts/handoffs/sessionN.md`.

## Model choice

- **DeepSeek V4.1 Flash (242k)** is good for focused code sessions: Sessions 9, 11, and 15. It is enough for the scorer, report modules, harness, tests, and the slope derivation if the agent uses targeted reads instead of dumping large artifacts.
- **Beam Free (1M)** is better for data/log handling and the broad report/audit sessions: Sessions 10, 12, 13, and 14.
- Sessions 14 and 15 are designed to run at the same time: 14 is research and decisions, 15 is numerical engineering, and their file sets do not overlap.
- If only one agent is used, use Beam and make it stop after every session. Do not give it all the prompts at once.
- Use DeepSeek as the independent reviewer after the final diff, even if Beam does the implementation.

## Starter messages

Use exactly one at a time:

```text
Read prompts/session9.md and do the work.
Read prompts/session10.md and do the work.
Read prompts/session11.md and do the work.
Read prompts/session12.md and do the work.
Read prompts/session13.md and do the work.
```

Each session should end with:

```text
Stop after this session. Run the tests, show the diff summary, commit, write prompts/handoffs/sessionN.md, and wait for review.
```

Do not use:

```text
Read all prompts and complete all sessions.
```

That skips the gates this repair pass exists to enforce.
