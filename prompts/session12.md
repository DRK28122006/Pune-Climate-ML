# Session 12 — Artifact and report regeneration

**Suggested model:** Beam Free (1M context helps with the report, manifest, and many generated artifacts)  
**Dependencies:** Session 11 merged. Session 10 data status known.  
**Owns:** `docs/example_assessment.json`, `docs/make_report.py`, `docs/Dishadharti_ML_Report.pdf` (regenerate only), `README.md`, `ml_pipeline/data/e2e/`, `ml_pipeline/data/stress/`, `ml_pipeline/research/MANIFEST.json`, `ml_pipeline/research/01_data_inventory.md`, and report-related notes under `ml_pipeline/research/07_decisions/`  
**Do not touch:** scoring formulas, validation harness code, `engine/`, `frontend/`, `backend/`, measured constants, weights, bands

Read `prompts/00_context.md` and `prompts/00_review_findings.md` first.

## Mission

Make every generated artifact either current or clearly marked stale. The current repo contains stale examples, old census totals, fake slope/drainage values, and a PDF that predates the safety fixes.

Do not hand-edit generated JSONs or the PDF. Regenerate from scripts, or mark the artifact stale and stop presenting it as evidence.

## 1. Fix `docs/example_assessment.json`

Current problems:

- `mean_slope_deg: 3.0`
- `slope_multiplier: 1.05`
- fake `dist_to_storm_drain_m: 38.2`
- `complete: true` with green `95.5`
- no demonstrated `canopy_cover_pct_proposed`
- old day/night heat fields

Required, choose one:

### Option A — regenerate as a real complete example

Use the current scorer with a real, self-consistent fixture:

- valid geometry
- explicit land-cover indicators
- night heat inputs
- a complete tree ledger with `canopy_cover_pct_proposed`
- a valid BOQ
- no invented slope or drainage
- provenance showing how it was generated

If the data needed for green is unavailable, this option is not available.

### Option B — mark it as a synthetic contract example

If green cannot be scored, regenerate the example with explicit `synthetic_fixture: true` / `SYNTHETIC_FIXTURE` labels, missing factors named, and no fake measured fields. A synthetic example is allowed for the frontend contract, but it must never look like a measured Pune assessment.

Do not keep `complete: true` by fabricating green or slope. Do not hand-edit a few fields to hide the problem.

## 2. Fix `docs/make_report.py`

Current problems:

- `reportlab` is not installed.
- `sweep_stats()` reads `/tmp/ward_*.json`; no such files exist here.
- The report text contains hardcoded ranges and claims that may no longer match the artifacts.
- The PDF is dated 30 Oct and predates the safety fixes.

Required:

- Install `reportlab` in the project venv, or add it to the project’s documented requirements. Do not install into system Python without recording it.
- Replace the `/tmp/ward_*.json` dependency with a reproducible input:
  - read `ml_pipeline/data/ward_validation.json`, or
  - accept a `--sweep-dir` argument and fail with a clear message when no files are found.
- Recompute ranges from the current validation artifact instead of hardcoding old values.
- Remove or update claims that are no longer true:
  - “48/48, 8/8, e2e” test counts
  - old flood/heat/green ranges
  - “any region” claims unless Session 7’s strict-mode wording supports them
  - carbon unknown-mass language
  - “no felling permitted” or other legal claims if still present
- If green is unavailable, say so in the report. Do not print a green range from a partial run as if it were validated.
- Regenerate the PDF only from the updated script.
- If regeneration is impossible, leave the PDF untouched and mark it `STALE — DO NOT QUOTE` in the README and manifest. Do not hand-edit the binary.

Regenerate:

```bash
python docs/make_report.py
```

Verify the PDF timestamp and that the generated file is non-zero.

## 3. Regenerate or mark stale `stress/` and `e2e/`

These artifacts still contain:

- `4,009,624`
- `mean_slope_deg: 3.0`
- `slope_multiplier: 1.05`
- fake drainage `38.2`

Required, choose one for each directory:

- Regenerate from the current harness and current scorer, with provenance; or
- Add a `STALE.md` in the directory and mark every artifact `STALE — DO NOT QUOTE` in `MANIFEST.json`.

Do not leave stale artifacts looking current. Do not hand-edit them to change only the census number.

If regenerating, do not fabricate slope or drainage. Use `null` and let the scorer report the basis.

## 4. Reconcile README claims

Update `README.md` so every measured range points to a current artifact:

- Flood range: use `ward_validation.json` / `site_validation.json` if complete enough; otherwise label it partial.
- Heat range: night-only; do not quote day-LST ranges.
- Green range: only quote if green was actually scored; otherwise say `UNAVAILABLE` in this checkout.
- Carbon: state whether it is flat by design in the validation harness.
- Web demo: keep the prototype language from Session 8.
- Report/PDF: state whether it is current or stale.

Remove or qualify claims that cannot be reproduced from the committed artifacts.

## 5. Update the manifest and inventory

Update `ml_pipeline/research/MANIFEST.json` and `01_data_inventory.md`:

- `docs/Dishadharti_ML_Report.pdf`: current only if regenerated; otherwise `stale`.
- `ward_validation.json` / `site_validation.json`: current only after Session 11.
- `tree_index.sqlite`: `missing` or `external/local-only`; never committed.
- `reference_layers.sqlite`: `missing`, `local-only`, or `current` based on Session 10.
- `pune_parks.kml`, `pune_nallas.kml`: present/missing with source.
- `docs/example_assessment.json`: `current`, `synthetic`, or `stale`.
- `stress/`, `e2e/`: `current` or `stale`.
- Add Session 9–12 decision notes and status files.
- Update sha256/bytes for regenerated artifacts.

Do not mark an artifact `current` because it exists. Mark it current only when it was regenerated from current code/config/cube and the provenance matches.

## 6. Add a report claims note

Write or update `ml_pipeline/research/07_decisions/0013-report-artifact-status.md`:

- Which artifacts were regenerated.
- Which remain stale and why.
- Which README/report numbers changed and the artifact they came from.
- Whether the PDF is current.
- What cannot be claimed yet (green validation, drainage, slope, fluvial flood).

## Tests and checks

```bash
python docs/make_report.py
python -m pytest ml_pipeline/tests -q
python -m pytest -q
python ml_pipeline/data/check_provenance.py
```

Also:

```bash
grep -R "4,009,624\|mean_slope_deg.*3\.0\|\"slope_multiplier\": 1\.05" -n docs ml_pipeline --exclude='*.pdf'
```

The remaining hits must be explicitly labelled `SYNTHETIC_FIXTURE` or `STALE`, or be absent.

## Acceptance

- `docs/example_assessment.json` is regenerated with current fields, or clearly labelled synthetic/stale.
- No current artifact contains fabricated 3° slope, fake drainage, or old census total.
- PDF is regenerated from the script, or clearly marked stale.
- `docs/make_report.py` no longer depends on nonexistent `/tmp/ward_*.json`.
- README ranges match current artifacts or are labelled partial/unavailable.
- `MANIFEST.json` and inventory statuses are accurate.
- `stress/` and `e2e/` are regenerated or marked stale.
- No generated JSON or PDF was hand-edited.
- Decision note `0013-report-artifact-status.md` exists.

## Handoff

Write `prompts/handoffs/session12.md` with:

- Which artifacts were regenerated.
- Which remain stale.
- The PDF status and exact command used.
- The README/manifest changes.
- Any claims that still cannot be made.
- What Session 13 must verify.
