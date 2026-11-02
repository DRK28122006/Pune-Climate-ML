# Decision notes

Decision notes are **required** for any change to weights, spans, bands, thresholds, or legal labels.

- Weights: `ml_pipeline/config/regions/pune.json` → `weights` (flood 0.30, heat 0.30, green 0.20, carbon 0.20).
- Spans: day/night UHI spans (2.0 / 5.0 °C), design storm (214 mm).
- Bands: carbon 400/800/1200 (house bands, not a named standard).
- Thresholds: unknown-mass 10%, sat/census tolerance 15 pts, slope full-effect 15°, drain benefit 500 m.
- Legal labels: girth ≥ 90 cm preserve is house policy; compensatory counts age-equivalent; Act section numbers not cited without primary source.

Each change must cite evidence and be recorded as a dated note in this directory (e.g. `2026-11-02_heat_span.md`). No silent rescaling (hard rule 5).
