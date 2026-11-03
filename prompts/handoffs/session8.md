# Handoff — Session 8 (web demo honesty)

**Date:** 2026-11-02
**Branch:** main (committed locally, 64a8de0)

## Path chosen
Path B — prototype labelling. No backend bridge to Python scorer.

## Changed files
- `frontend/src/services/optimization.ts` — isDemo true, modelVersion prototype-demo-1.0.
- `backend/src/services/assessmentService.js` — "request" no longer measured.
- `backend/src/services/recommendationService.js` — source illustrative-scenario.
- `README.md` — web demo is prototype, not scientific pipeline.

## Verified
- `npm test --workspace backend`: 5 pass.
- `npm run build --workspace frontend`: success.

## Remaining mismatch
- Web app still uses legacy JS scorer; not wired to Python pipeline.
EOF
echo done