# Session 8 — Web demo honesty (optional)

**Suggested model:** DeepSeek or any available agent  
**Dependencies:** Sessions 2 and 5 if wiring the real ML scorer; otherwise can run independently  
**Owns:** `frontend/`, `backend/` only  
**Do not touch:** `ml_pipeline/` scoring, validation, `engine/`, report

Read `prompts/00_context.md` first.

## Mission

Remove the contradiction between the web demo and the scientific pipeline. The app currently runs a legacy JavaScript scorer with slider-derived inputs, fixed coordinates, a fake slope and elevation, and labels the result as measured.

This is **not** an ML session. It is a product-honesty session. If you are not doing it, skip it; the Python ML work can proceed without it.

## Fix C0

Current problems:

- `frontend/src/services/optimization.ts` builds `mlOutput` from user-entered percentages.
- Land cover is `vegetation = 100 - (builtUp + paved)`, `water = 0`.
- LST is a linear formula: `31 + 0.085·builtUp + 0.05·paved - 0.14·canopy`.
- Coordinates are fixed at `18.5204, 73.8567`.
- `slope_deg_mean: 3`, `elevation_m_mean: 560`, `ndvi_mean: 0.3`, `ndbi_mean: 0.5`, `ndwi_mean: 0.1`.
- The backend defaults to `ML_MODE=fixture`.
- `fixtureOutput` generates seeded pseudo-landcover/LST from a hash.
- `source: "request"` is treated as measured in `assessDataQuality`.
- The “optimization” is hardcoded: +12% vegetation, a cooler LST, materials ×0.85, labelled `source: "verified-scenario"`.
- `isDemo: false` and `modelVersion: "backend-1.0"` contradict the UI caveat.

Required: choose one path and do it completely.

### Path A — Wire the real Python scorer

- Replace the synthetic `mlOutput` with a call to the Python pipeline, either through a new backend bridge or a CLI/API wrapper.
- Pass real site geometry, plot area, footprint/GFA, materials, and tree ledger.
- Remove the fixed coordinates, fake slope, fake elevation, and seeded fixture.
- Set `isDemo: false` only when the result actually came from the Python scorer.
- Keep the UI caveat until the bridge is verified end-to-end.

### Path B — Keep it as a prototype, but label it honestly

- Set `isDemo: true` for every slider-derived result.
- Remove `source: "verified-scenario"`.
- Rename `modelVersion` to something like `prototype-demo-1.0`.
- Stop treating `source: "request"` as measured; mark it `user-supplied scenario`.
- Make the UI say the result is a scenario calculator, not a measured assessment.
- Remove or clearly label the hardcoded optimization as illustrative.
- Do not present the demo as the scientific pipeline in the README or report.

Do not do both halfway. Either the app uses the real scorer or it is explicitly a prototype.

## Tests / verification

- If Path A: one end-to-end assessment through the UI/API produces the same sub-scores as the Python CLI for the same inputs.
- If Path B: a test or visible UI check asserts `isDemo: true`, `source` is not “measured,” and no `verified-scenario` label is emitted.
- Add a README section stating which system the web app uses.
- Run the frontend build and backend tests.

```bash
npm run build --workspace frontend
npm test --workspace backend
```

Use the repository’s actual scripts if they differ.

## Do not

- Do not change ML constants or scoring logic.
- Do not claim the app is wired to Python if it still sends synthetic `mlOutput`.
- Do not leave `isDemo: false` on fabricated inputs.
- Do not label a hardcoded recommendation as “verified.”
- Do not touch `ml_pipeline/`, `engine/`, validation artifacts, or the report.

## Acceptance

- No fabricated input is presented as measured.
- `isDemo` and `source` match reality.
- The README says which system the web app uses.
- If wired, the UI and Python CLI agree for the same inputs.
- If prototype, the UI caveat is prominent and consistent.

## Handoff

Report:

- Which path you chose and why.
- Files changed.
- End-to-end verification or prototype labelling.
- Any remaining mismatch between the web app and the Python pipeline.
