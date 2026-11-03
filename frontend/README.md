# DishaDharti (frontend prototype)

Urban climate intelligence and sustainable urban planning, prototype city Pune.
Journey: polluted Pune → evaluate a plan → optimize → explore the greener outcome.

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # typecheck + production build
```

## Routes
| Path | Page |
|---|---|
| `/` | Landing with the bottom-centre **Evaluate** button |
| `/assess` | Assessment form, **Optimize Plan**, results revealed below on success |
| `/dashboard/overview` `heat` `air-quality` `green-cover` `flood-risk` `scenario-planner` | Dashboard pages with a collapsible sidebar |

The assessment and all dashboard pages share one layout (`src/components/AppShell.tsx`), so the single collapsible sidebar is visible from `/assess` onwards and keeps its collapsed state while navigating. The landing page has no sidebar.

`vercel.json` rewrites unknown paths to `index.html`, and the Vite dev server already does, so refreshing any route works.

## What is simulated
**Everything.** There is no backend and no real data.
- `src/lib/optimizer.ts` is a clearly labelled *demonstration* model. Coefficients are illustrative, not calibrated or validated. It is deterministic: same inputs, same output.
- `src/data/sample.ts` holds placeholder figures copied from the supplied layout prototype ("Growing Pune"). They are not Pune statistics.
- Maps are *conceptual tile layouts*, not geography.
- The 33% canopy target (`src/config.ts`) comes from the prototype and is a placeholder.

## Atmosphere rules
The landing page uses a left-to-right version of the same scene (polluted on the left, green on the right), switched on only there via `atmosphere.setSpatial`. It is scenery only; the scene's greenness value stays at 0.

`src/scene/` draws the sky, haze, skyline and growing tree. Greenness is `0` (polluted) to `1` (green).
- Landing, assessment form and every dashboard page stay at `0` until an optimization has succeeded.
- On `/assess`, once a result exists, scrolling through the results moves the scene toward green. Scrolling alone never reveals results.
- After success, each dashboard page uses its own intensity (`PAGE_INTENSITY` in `config.ts`).
- `prefers-reduced-motion`: no easing, no sway, static dust, near-zero CSS transitions.

## Plugging in real things
| To replace | Edit | Keep |
|---|---|---|
| Optimizer | `runDemoOptimization` in `src/lib/optimizer.ts`: call your API | the `OptimizationResult` shape in `src/types.ts` |
| Datasets | functions in `src/data/api.ts` (already async) | the types in `src/data/sample.ts` |
| Maps | swap `ConceptMap` in `src/components/charts/Visuals.tsx` for a real map layer | its tile/selection props as a contract |
| Logo | `src/components/Logo.tsx` (temporary mark, not an official asset) | |
| Heading / tagline | `TAGLINE` in `src/config.ts` (temporary) | |

## Layout
```
src/
  config.ts  types.ts  nav.ts
  lib/        optimizer.ts (demo engine) · math.ts · useAsync.ts
  data/       sample.ts (placeholder data) · api.ts (async access layer)
  state/      PlanContext.tsx (inputs, validation, run status, result)
  scene/      engine.ts (canvas) · atmosphereStore.ts
  components/ Atmosphere · Sidebar · Logo · Field · ui (Button, Panel, MetricCard, states…) · charts/
  pages/      Landing · Assessment · dashboard/*
  styles/     tokens.css · base.css · components.css · pages.css
```

## Unconfirmed against the live dashboard
The live site (pune-climate-hackathon-prototype.vercel.app) renders client-side and could not be inspected, so the form fields, terminology and page contents are **assumptions**. Only the page names given in the brief and the layout prototype were used.
The layout is desktop-first; make it fully responsive in a later pass.
