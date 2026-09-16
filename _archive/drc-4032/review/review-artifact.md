# DRC-4032 Review Artifact: Quiet hours notification suppression

## Implementation summary
PR #357 implements D9 (DRC-4032), adding quiet hours notification suppression to Cargento:
- Adds `--quiet-hours WINDOW` and `--no-quiet-hours` CLI flags, supporting local time windows (e.g. `22:00-08:00`), environment variable `CARGENTO_QUIET_HOURS`, and file `~/.cargento/quiet_hours`.
- Correctly handles overnight windows spanning midnight.
- When quiet hours are active, suppresses native desktop popups, Claude notify hook popups, unasked departure alerts, tripwire notifications, and off-machine reach nudges.
- Preserves direct operator questions (`ask_operator` / `maybe_ask_popup`), allowing urgent questions requiring operator input to pass through.
- Publishes `in_quiet_hours` flag in `/api/data` payload.

## Verification results
- All 3519 dashboard and script tests pass
- 86.8% coverage across runtime and scripts
- 0 errors across 163 files in mypy
- All checks pass in ruff check and ruff format
- Zero em or en dashes introduced in prose or code
