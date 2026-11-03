# Shared context — read this before your session file

This file is the common briefing for every session. Read it fully, then read your `sessionN.md`.

> **Repair pass:** Sessions 9–13 were created after an independent review of Sessions 1–8. Those sessions must also read `prompts/00_review_findings.md`. Sessions 1–8 are already committed; do not rerun them.

## Project

Dishadharti / Pune-Climate-ML is a deterministic climate screening tool for building proposals in Pune, India.

- The scientific system is the Python pipeline in `ml_pipeline/` and `engine/`.
- It scores four factors from 0 to 100, where higher means worse: flood, heat, green cover, carbon.
- It produces a composite `impact_score`, a `climate_score` (`100 - impact`), a risk band, and a recommendation.
- A language model may narrate the computed JSON. It must never compute, adjust, or soften numbers.
- The project deliberately avoids mocks, fabricated satellite data, and trained neural scorers.

## Current repository state

Verify this before editing. Do not assume every file exists.

| Asset | Location | State |
|---|---|---|
| Epoch cube, 864 cells | `ml_pipeline/data/epoch_cube.json` | Present, about 512 KB |
| IMD annual maxima, 1901–2024 | `ml_pipeline/data/imd_pune_annual_max.csv` | Present |
| Census ward profile | `ml_pipeline/data/census_ward_profile.csv` | Present |
| GEDI ward check | `ml_pipeline/data/gedi_ward_rh95.csv` | Present |
| Ward validation | `ml_pipeline/data/ward_validation.json` | Present but stale |
| Site validation | `ml_pipeline/data/site_validation.json` | Present but stale |
| Stress and E2E outputs | `ml_pipeline/data/stress/`, `ml_pipeline/data/e2e/` | Present |
| Region, materials, species configs | `ml_pipeline/config/` | Present |
| Stormwater KMZ | `ml_pipeline/reference/pmc_stormwater_drains.kmz` | Present, about 22 MB |
| Ward KML | `/home/mesh/Pictures/pmc_wards_2025.kml` | Outside repo |
| Ward 12 KML | `/home/mesh/Pictures/WARD12_TEST_SITE.kml` | Outside repo |
| Raw tree census | `ml_pipeline/data/census/` | Missing, about 1.2 GB |
| Tree index | `ml_pipeline/data/tree_index.sqlite` | Missing, about 52 MB |
| Reference layers | `ml_pipeline/data/reference_layers.sqlite` | Missing |
| Parks KML | `ml_pipeline/reference/pune_parks.kml` | Missing |
| Nallas KML | `ml_pipeline/reference/pune_nallas.kml` | Missing |
| Web app | `frontend/`, `backend/`, `api/` | Separate from the Python scorer |

There are uncommitted changes in the repository. Preserve them.

## Scientific decisions that must not be reverted

- Night heat is deliberate. Daytime surface heat was retired after two measured failures. Do not switch back to day LST.
- The design storm is 214 mm, a measured 100-year 1-day Gumbel quantile from 124 years of IMD data. The old 150 mm value is retired.
- Night reference is 17.96 °C; the night UHI span is 5.0 °C. Both are measured or derived. Do not silently replace them with literature ranges.
- Carbon bands 400/800/1200 are house bands, not a named standard. Keep them labelled as such.
- The 90 cm girth preservation rule is house policy, not statute.
- The project refuses to score a factor from missing data. If this is not true in code, that is a bug to fix, not a policy to weaken.

## Known findings from the scientific review

These IDs are used by the session files.

- **C0** — The web app uses a legacy JavaScript scorer and slider-derived `mlOutput`; it is not wired to the Python scorer. It sets `isDemo: false` and labels inputs as measured.
- **C1** — `score_project` zero-fills missing land-cover percentages. Empty indicators can produce flood 0, impact 0, climate 100, `Low`, and `APPROVE`.
- **C2** — Seasonal bare soil is double-counted. 847/864 cells have land-cover sums above 1; 166 cells reach CN ≥ 99.99 with `bare_season_pct`, versus 0 with annual `bare_pct`.
- **C3** — The proposal design is mostly not modelled. Flood and heat use the existing 1 km cell; built-up area only enters carbon. `builtUpAreaSqm` conflates plinth and GFA.
- **C4** — No per-factor veto. A single catastrophic factor can still produce `APPROVE` after weighting.
- **C5** — Validation is circular, centroid-sampled, stale, and contains placeholder defaults. Ward validation has only 6 wards and uses day LST and a 2.0 °C span.
- **C6** — Flood and green do not span 0–100. Flood max is about 56.6; green has a floor of 30.
- **C7** — Heat is a percentile rescaling of night LST, confounded by elevation. 99/864 cells score exactly 0. A daytime fallback still exists.
- **C8** — Green's 70/30 label is algebraically misleading: the marginal canopy weight is 0.40. Effective green can exceed satellite vegetation.
- **C9** — Carbon's unknown threshold is mass-based, not carbon-based. Double counting is warned but not enforced. Units are not converted. Intensity and band are still reported when the score is withheld.
- **C10** — Legal and policy labels are partly wrong or too strong. The code/species config says “flat 1:3”; the pre-2021 rule was “twice the number.” The 90 cm rule is not a statutory prohibition.
- **C11** — “Any region” is not supported by the current engine. The scaffold uses Pune/house constants and a provisional 150 mm storm.
- **C12** — Floodplain exposure is described but not implemented. Only engineered drain proximity is scored.
- **C13** — Stale artifacts, missing provenance, and an off-by-one census total: `4,009,624` should be `4,009,623` (`16 × 250,000 + 9,623`).

## Hard rules for every session

1. **Preserve the working tree.** Do not run `git reset --hard`, `git checkout -- .`, `git clean -fd`, or delete files you did not create.
2. **Do not weaken tests.** Add tests for every fix. If a test is wrong, explain why and change it deliberately.
3. **No fabricated data.** If a required file is missing, stop and report the exact path and rebuild command.
4. **No unsourced constants.** If you change a measured constant, cite the evidence and write a decision note.
5. **No silent rescaling.** Changing weights, spans, bands, or thresholds is a policy decision. Write it down.
6. **No legal hallucination.** Exact Act sections and Gazette notifications need a primary source. Otherwise mark `[U]`.
7. **One writer per file.** `ml_pipeline/core/scoring.py` is serialized: S2 → S4 → S5.
8. **Keep the narrator dumb.** It may format and explain computed JSON; it may not compute or change numbers.
9. **Regenerate, don't hand-edit.** Validation JSONs, figures, and the PDF must come from scripts.
10. **Use `/tmp/opencode` for scratch files.** Do not leave temporary junk in the repo.

## Test commands

Use `.venv/bin/python` if it exists, otherwise `python3`.

```bash
.venv/bin/python -m pytest ml_pipeline/tests -q
.venv/bin/python ml_pipeline/tests/test_scoring.py
.venv/bin/python ml_pipeline/tests/test_data_integrity.py
.venv/bin/python engine/tests/test_engine.py
```

Some tests require `tree_index.sqlite` or KMLs that are currently missing. A missing-data failure is not permission to fake the data. Report it.

## Required handoff at the end of every session

Write a short report containing:

- What changed, file by file.
- What was verified, with exact commands and outputs.
- What is still blocked, with exact missing paths.
- Any decision made, and where the decision note is stored.
- What the next session needs to know.

Do not claim a test passed unless you ran it. Do not claim a number is measured unless you can point to the artifact.
