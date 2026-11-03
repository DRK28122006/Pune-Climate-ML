# Session 5 — Green, carbon, and GFA

**Suggested model:** Mimo V2.6 Flash Free  
**Dependencies:** Session 4 merged  
**Owns:** green and carbon sections of `ml_pipeline/core/scoring.py`, `ml_pipeline/core/canopy.py`, `ml_pipeline/config/materials.json`, `ml_pipeline/intake/validate.py`, `ml_pipeline/data/build_cube.py`  
**Do not touch:** flood/heat sections, validation JSONs, `report/`, `frontend/`, `backend/`

Read `prompts/00_context.md` first.

## Mission

Fix the two factors that respond most directly to the proposal: green cover and embodied carbon. Also fix the plinth/GFA confusion that makes carbon intensity wrong for multi-storey buildings.

Only one session may edit `core/scoring.py`. Confirm Session 4 is merged before editing.

## Green — C8 and C3

### C8 — the 70/30 label is misleading

Current algebra:

```text
ground = max(0, satellite_vegetation - canopy)
effective = 0.70 × canopy + 0.30 × ground
         = 0.30 × satellite_vegetation + 0.40 × canopy
```

The marginal canopy weight is 0.40, not 0.70. When site canopy exceeds the cell’s satellite vegetation, `ground` clips to zero and `effective` can exceed the satellite total. The code reports a mismatch but still uses the number.

Required:

- State the algebra explicitly in the output and docs.
- Prevent `effective_green_pct` from exceeding the satellite vegetation plus a clearly explained canopy correction, or document why it can.
- Do not feed a >100% ward density index into a site fraction.
- Use the proposed canopy (`canopy_cover_pct_proposed`) in every artifact, not the existing canopy.
- Constrain ground vegetation by the unbuilt, non-canopy pervious area where possible.
- If site-scale 10 m vegetation is available, use it. If not, report the 1 km resolution mismatch honestly.
- Consider a two-part score:
  - canopy retained / pre-existing canopy
  - post-development plot green cover
  This is a design decision; write it in a note.

Do not silently replace the 70/30 weights with a new universal number. If you change them, document why and what evidence supports it.

### C3 — green is not a full proposal-impact model

Flood and heat still use the existing cell. Green responds to tree decisions but not to the built footprint. Make that explicit.

Required:

- Report `canopy_basis`: `proposed`, `existing`, or `unavailable`.
- Report the satellite resolution and census resolution.
- If the proposal cannot supply a planting plan, label the result “site baseline with tree-decision overlay,” not “post-development green cover.”

## Carbon — C9

### 1. Unknown threshold is mass-based, not carbon-based

`UNKNOWN_MASS_EXCLUDE_PCT = 10` withholds the score only when >10% of BOQ mass is unrecognised. A small mass of a high-factor material can dominate carbon.

Example: 95% cement (0.91) + 5% aluminium (20.88) by mass. Aluminium is 5% of mass but 54.7% of carbon. The code would score the known cement and understate intensity by about 55%.

Required:

- Threshold by carbon share, or
- Use a conservative upper-bound factor for unknown materials, or
- Withhold the score when unknown carbon share exceeds a documented limit.
- Keep the old mass-share number in the output for transparency, but do not use it as the only gate.
- Add the 5% aluminium test.

### 2. Double counting is warned but not enforced

If both cement and ready-mix concrete are specified, the total includes both. `double_count_warning` is set but no caller drops a line.

Required:

- Enforce the exclusion, or make it a blocking issue that withholds the score.
- Do not silently subtract. Name the line items and the rule.
- Add a test with cement + ready-mix concrete.

### 3. Withheld score still reports intensity and band

The >10% branch returns `score: None` but still sets `intensity_kgco2e_m2` and `band` from the known-only total. The empty-BOQ branch reports intensity 0.0, which reads as zero-carbon.

Required:

- When the score is unavailable, set intensity and band to `null` or explicitly label them `PARTIAL_KNOWN_ONLY`.
- Do not let an empty BOQ read as zero-carbon.
- Add tests for empty BOQ and wholly unknown BOQ.

### 4. Units are ambiguous

The intake requires `quantityKg` and performs no unit conversion. A real BOQ in m³ or m² for concrete/brick is silently treated as kg.

Required:

- Require explicit units and a density conversion table, or
- Accept only mass and reject other units with a clear error.
- Add a m³-concrete test.
- Name the conversion source for every density.

### 5. GFA vs plinth — C3

The code uses one `builtUpAreaSqm` for carbon intensity. A multi-storey building’s GFA can exceed the plot area, but intake rejects `built_up > plot`. If the user enters the plinth to pass validation, carbon is divided by the plinth and overstated by the number of storeys.

Required:

- Introduce three explicit inputs:
  - `plot_area_m2`
  - `impervious_footprint_m2` (≤ plot)
  - `total_gfa_m2` (≥ footprint)
- Flood uses footprint/plot imperviousness.
- Carbon divides by GFA.
- Green uses plot and proposed canopy.
- Update intake validation and error messages.
- Keep backward compatibility only if clearly labelled; do not guess which old input meant GFA.
- Add a 10-storey test: flood uses footprint, carbon uses GFA.

## Carbon bands

400/800/1200 are house bands. Do not silently change them. If you derive new bands:

- Use a documented A1–A3 distribution or typology-specific percentiles.
- Keep IGBC 700 as a marker, not a saturation ceiling.
- Write `0006-carbon-bands.md`.
- Update the report only through Session 6.

## Tests

Add tests for:

- 5% aluminium by mass → carbon-share warning/withhold, not silent understatement.
- Cement + ready-mix concrete → double-count blocked or score withheld.
- Empty BOQ → not zero-carbon.
- Wholly unknown BOQ → score `None`, intensity/band `None`.
- m³ concrete → converted with documented density or rejected.
- 10-storey building → carbon uses GFA, flood uses footprint.
- Proposed canopy → green changes when trees are felled.
- Effective green does not exceed satellite vegetation without an explicit explanation.

Run:

```bash
.venv/bin/python -m pytest ml_pipeline/tests -q
.venv/bin/python ml_pipeline/tests/test_scoring.py
```

## Decision notes

Write in `ml_pipeline/research/07_decisions/`:

- `0006-green-algebra.md`
- `0007-carbon-threshold.md`
- `0008-carbon-bands.md`
- `0009-gfa-inputs.md`

## Do not

- Do not touch flood/heat.
- Do not change 214 mm, 17.96 °C, or 5.0 °C.
- Do not silently change 70/30 or 400/800/1200.
- Do not regenerate validation JSONs.
- Do not edit the report or PDF.
- Do not fabricate a site-scale vegetation layer. If it is unavailable, report the resolution mismatch.

## Acceptance

- Green’s marginal canopy weight is explicit.
- Effective green cannot silently exceed satellite vegetation.
- Carbon withholds on carbon-share uncertainty, not only mass.
- Double counting is blocked or explicitly withheld.
- Units are converted or rejected.
- GFA and footprint are separate inputs.
- Tests cover all of the above.

## Handoff

Report:

- The green algebra and any weight decision.
- The carbon threshold and band decision.
- The new input contract.
- Test results.
- What Session 6 needs for the report.
