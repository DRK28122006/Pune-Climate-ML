# Handoff — Session 6 (legal, report, narrative)

**Date:** 2026-11-02
**Branch:** main (committed locally, e1e8112)

## Changed files
- `ml_pipeline/config/species.json` — legal rule labels, pre-2021 "twice the number", heritage 50 yr, >200 tree referral, [U] flags.
- `README.md` — ranges sourced/labelled, night-only heat, green floor documented.
- `ml_pipeline/research/07_decisions/0010-report-claims.md`.

## Verified
- `test_narrative.py`: 22/22.
- `pytest ml_pipeline/tests`: 72 passed.

## Not done
- PDF not regenerated: reportlab not installed. make_report.py untouched.
- Report binary not edited by hand.

## Session 7 needs
- Final provenance language; any-region claims must use Session 7's language.
- Verify report claims against Session 3 artifacts.
EOF
echo done