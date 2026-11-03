# Session 3 — Validation and provenance

**Suggested model:** GLM 5.3 Flash  
**Dependencies:** Session 1 (KMLs and data) and Session 2 (corrected scorer)  
**Owns:** `ml_pipeline/data/validate_wards.py`, `ml_pipeline/data/validate_sites.py`, `ml_pipeline/data/factor_breakdown.py`, `ml_pipeline/data/ward_validation.json`, `ml_pipeline/data/site_validation.json`, `ml_pipeline/data/stress/`, `ml_pipeline/tests/test_data_integrity.py`  
**Do not touch:** scoring formulas, `core/scoring.py`, `engine/`, `report/`, `frontend/`, `backend/`

Read `prompts/00_context.md` first.

## Mission

Make the validation honest and reproducible. The current artifacts use the old day-LST path, centroid-only ward sampling, ward canopy as site canopy, and placeholder drainage/slope defaults. They cannot support the README or report claims.

This session fixes the harness and regenerates artifacts. If a scoring formula looks wrong, report it to Session 2/4; do not patch the formula here.

## Fix C5 — validation problems

### 1. Centroid-only ward lookup

`indicators_from_cube` returns the single cell containing the polygon centroid. `validate_wards.py` passes a whole ward ring but scores one cell.

Required:

- For each ward, find all cube cells intersecting the ward polygon.
- Area-weight the land-cover, LST, and elevation values by intersection area.
- Or use majority-overlap if area weighting is not practical.
- Report the number of cells used and the covered area fraction.
- Do not call a ward score a “ward aggregate” if it is still a point sample.

### 2. Ward canopy used as site canopy

`ward_tree_profile` computes canopy / ward area and passes ward-level density into a 4,000 m² plot ledger. A ward with >100% canopy density is clamped to 100 and treated as a site fraction.

Required:

- Use the site polygon for green, or use a clearly labelled ward-density index.
- Never feed a >100% density index into a site fraction.
- If the harness is ward-level, label the output `ward_density_index`, not `canopy_cover_pct`.
- If the tree index is unavailable, fail with a clear message. Do not fabricate a canopy.

### 3. Day LST and stale spans

`ward_validation.json` heat `27.0` is `0.539 / 2.0 × 100` — the day path and the retired 2.0 °C span. `site_validation.json` heat `53.8` is `1.076 / 2.0 × 100`. The current scorer uses night LST and 5.0 °C.

Required:

- Use `lst_night_mean_c`, `lst_night_reference_c`, and `night_uhi_max_delta_c`.
- Do not use `lst_mean_c` or `uhi_max_delta_c` except as an explicitly labelled legacy row.
- If night data is missing, the heat factor is unavailable. Do not fall back to day silently.
- Recompute all heat values from the current scorer.

### 4. Fabricated defaults

Current placeholders:

- `validate_wards.py` uses `dist_to_storm_drain_m = 150.0`.
- `validate_sites.py` uses `or 200.0`.
- `docs/example_assessment.json` and `stress/*.json` contain `mean_slope_deg: 3.0` and `slope_multiplier: 1.05`.

Required:

- Remove the `150.0` and `200.0` drainage defaults.
- Remove the `3.0°` slope default from generated artifacts.
- If a value is unknown, pass `None` and let the scorer report the basis.
- If a placeholder is kept for a synthetic fixture, label it `SYNTHETIC_FIXTURE`, not measured.
- Do not regenerate `docs/example_assessment.json` in this session unless it is part of the validation harness. Flag it for Session 6.

### 5. Correlations are not independent validation

Required:

- Keep the correlations, but label them “internal consistency checks,” not validation.
- Report the sample size and the fact that the 41 ward runs use one identical proposal.
- Report that flood and green are deterministic functions of land cover.
- Report spatial autocorrelation as a caveat.
- Fix `factor_breakdown.py` sign convention: sub-scores are higher = worse; `climate_score` is higher = better. A positive correlation with `climate_score` is not “correct” in the same direction.
- Do not report only the strong correlations. Report all factors and variables tested, or state that the table is selective.

## Required outputs

1. Fixed `validate_wards.py`:
   - area-weighted or majority-overlap cells
   - night LST
   - no 150 m drain default
   - no 3° slope default
   - explicit missing-data handling
2. Fixed `validate_sites.py`:
   - night LST
   - no 200 m drain default
   - correct expected ordering
   - no zero-tree green unless a real zero canopy is measured
3. Regenerated `ward_validation.json` and `site_validation.json` using the Session 2 scorer.
4. Regenerated `stress/` only if the harness is deterministic and the inputs are labelled.
5. A provenance block in every generated artifact:

```json
{
  "code_commit": "...",
  "working_tree_dirty": true,
  "scorer_version": "...",
  "region_config_sha256": "...",
  "epoch_cube_sha256": "...",
  "tree_index_sha256": "...",
  "heat_mode": "NIGHT_MODIS_LST",
  "design_storm_mm": 214.0,
  "hsg": "B",
  "weights": {"flood": 0.3, "heat": 0.3, "green": 0.2, "carbon": 0.2},
  "generated_at_utc": "..."
}
```

If the tree index is missing, set `tree_index_sha256` to `null` and set `tree_index_status: "MISSING"`. Do not invent a hash.

6. A short `ml_pipeline/research/04_validation/README.md` explaining:
   - what each artifact tests
   - what it does not test
   - how to regenerate it
   - which artifacts are stale or superseded

## Independent validation plan

Do not claim the correlation table validates accuracy. Add a plan for:

- **Flood:** PMC waterlogging/chronic-flood hotspots and 2019/2024 inundation polygons; AUROC and Mann–Whitney.
- **Heat:** ECOSTRESS 70 m night LST, IMD/ERA5-Land air temperature, Moran’s I.
- **Green:** GEDI RH95 and a stratified field/crown audit; Lin’s concordance and RMSE.
- **Carbon:** 10 real Pune RERA BOQs against `materials.json` and IFC India; MAPE.
- **Decision stability:** storm CI 191–234 mm, HSG C/D, heat span uncertainty, carbon factor CV; flag `BORDERLINE_VERDICT`.

Put the plan in `04_validation/README.md`. Do not fabricate the validation results.

## Do not

- Do not change scoring formulas.
- Do not fabricate `tree_index.sqlite`, KMLs, or hotspots.
- Do not hand-edit the validation JSONs. Regenerate them.
- Do not claim a 41-ward artifact if you only have 6 wards.
- Do not present the old day-LST rows as current.
- Do not edit the PDF or README in this session.

## Acceptance

- No `150.0` or `200.0` drainage defaults remain in the validation harness.
- No `mean_slope_deg: 3.0` is generated as if measured.
- Heat mode is night in every current artifact.
- Ward scores report cell count and area coverage.
- `factor_breakdown.py` sign convention is correct.
- Every artifact has provenance.
- The README ranges can be reproduced from committed artifacts, or the mismatch is explicitly documented.

## Handoff

Report:

- Which validation artifacts were regenerated and which remain stale.
- The exact commands used.
- Whether the tree index/KMLs were available.
- The new ranges and correlations, with caveats.
- What Session 6 needs to update in the report.
