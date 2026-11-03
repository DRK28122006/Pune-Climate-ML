# Session 6 — Legal, report, and narrative

**Suggested model:** Mimo V2.6 Flash Free  
**Dependencies:** Session 5 + Session 7 for final report; legal/label work can start earlier  
**Owns:** `ml_pipeline/report/render.py`, `ml_pipeline/report/narrative.py`, `docs/make_report.py`, `README.md`, `docs/Dishadharti_ML_Report.pdf` regeneration; coordinate with Session 5 for `core/canopy.py` and `config/species.json` labels  
**Do not touch:** scoring formulas, validation harness, `frontend/`, `backend/`, `engine/`

Read `prompts/00_context.md` first.

## Mission

Make the legal language and the public report match the code. The current report and species config contain claims that are too strong, unsourced, or inconsistent with the Act and with the scorer.

Do not invent legal citations. If you cannot verify the Gazette or a primary source, mark the claim `[U]` and say exactly what needs checking.

## Fix C10 — legal and policy labels

### 1. The 90 cm rule is house policy

The code correctly labels the 90 cm girth rule as house policy, but the report label says “preserve (no felling permitted),” which sounds statutory.

Required:

- Replace “no felling permitted” with a label such as:
  - `HOUSE POLICY: Dishadharti silvicultural preservation threshold; not a statutory prohibition.`
- The Act requires permission before felling; it does not create a 90 cm prohibition.
- The statutory heritage criterion is age-based (50 years or more), not girth.

### 2. The pre-2021 compensation rule

The code/species config says “flat 1:3.” The amendment text says the earlier rule was “twice the number of trees to be felled,” and the 2021 amendment replaced it with a number equal to the estimated age, with saplings at least six feet high.

Required:

- Correct “1:3” to “twice the number” for the pre-2021 rule.
- Keep the current age-equivalent rule as the operative rule.
- Do not state exact section numbers unless you have a primary source. Mark unverified sections `[U]`.
- The prior draft’s section numbers, the 2023 amendment, and case citations are not verified. Do not repeat them as fact.

### 3. Missing legal flags

Add flags or narrative lines for:

- heritage tree: 50 years or more, State Tree Authority referral
- large felling: more than 200 trees, State referral and anti-subdivision
- six-foot minimum sapling height
- seven-year maintenance/survival
- geo-tagging
- dead-tree removal: currently asserted as “no permit required”; mark it `[U]` until verified

### 4. Labels

Every rule in JSON and narrative must be one of:

- `LAW`
- `HOUSE POLICY`
- `DERIVED ESTIMATE`
- `UNVERIFIED`

Do not use “must,” “shall,” or “no felling permitted” for house policy.

### 5. Age estimate

The 2 cm/yr girth-to-age proxy is species-blind. Keep it labelled as a derived range. The Tree Officer determines age. Do not present the tool’s range as a legal determination.

## Report and README consistency

### Claims to reconcile

- The report says the built-up area drives flood. In the current code, flood uses the cell’s existing land cover. Fix the claim or fix the code in Session 4; do not leave the contradiction.
- The report says the KML is a repo file. It is not. Point to `ml_pipeline/research/05_sources/kml/` or document it as external.
- The README says flood `14.5–53.3`, heat `0.8–99.0`, green `62–100`. The committed validation JSONs give different ranges. Use the Session 3 regenerated artifacts or label the ranges as from a specific run with provenance.
- The report’s Figure 5/6 carbon denominators may disagree (602 t over 2,000 m² vs 3,000 m²). Check the source and fix or document.
- The report’s “0–100” claim is not true for flood or green. Use the honest attainable ranges from Session 4.
- The report’s “any region” claim is not supported. Use Session 7’s language.
- The report’s carbon “10% unknown mass” language must match Session 5’s new threshold.
- The report’s “no felling permitted” and “1:3” lines must change.

### Regeneration

- Do not edit the PDF binary by hand.
- Update `docs/make_report.py` and regenerate the PDF only after Sessions 2–5 are merged.
- Do not regenerate figures with stale data. If a figure depends on changed numbers, regenerate it from the current artifact.
- Keep a note in `ml_pipeline/research/07_decisions/0010-report-claims.md` listing every claim changed and why.

## Narrative rules

- The narrator may format and explain computed JSON. It must not compute or adjust numbers.
- It must not soften a `REVIEW` or `REJECT_OR_REDESIGN` recommendation.
- It must not turn a partial result into an approval.
- It must not say “no felling permitted” for a house-policy threshold.
- It must not cite an Act section that is not in the input or verified.
- Add tests that a partial result and a high single factor are narrated as review, not approval.

## Tests

Add or update tests in `ml_pipeline/tests/test_narrative.py` and any report tests:

- `REVIEW` is not narrated as approval.
- `HOUSE POLICY` is not narrated as law.
- `[U]` claims are not presented as fact.
- A partial result says “partial” and names the missing factors.
- A `Very High` carbon band does not produce an unconditional approval.

Run:

```bash
.venv/bin/python ml_pipeline/tests/test_narrative.py
.venv/bin/python -m pytest ml_pipeline/tests -q
```

## Do not

- Do not change scoring formulas.
- Do not invent Act sections or Gazette numbers.
- Do not edit the PDF by hand.
- Do not claim the report is reproducible until Session 3 artifacts are current.
- Do not change carbon factors, weights, or bands.
- Do not touch `frontend/` or `backend/`.

## Acceptance

- No “no felling permitted” for the 90 cm rule.
- No “flat 1:3” claim.
- Heritage and >200-tree referral flags exist or are explicitly marked not modelled.
- Dead-tree permit claim is marked `[U]` or verified.
- Every legal/policy line has a label.
- README/report ranges are sourced or labelled.
- The PDF is regenerated from code after dependencies are merged.
- Narrative tests pass.

## Handoff

Report:

- Every legal claim changed, with source or `[U]`.
- Every report/README number changed and its artifact.
- Which figures were regenerated.
- What remains unverified.
- What Session 7 needs for the final provenance language.
