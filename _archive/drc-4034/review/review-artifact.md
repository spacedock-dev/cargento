# DRC-4034 Review Artifact: Reach off-machine nudge delivery

## Implementation summary
PR #356 implements H2 (DRC-4034, DEC-4), adding off-machine reach nudge delivery to Cargento.
The implementation adheres to all non-negotiable security boundaries in SECURITY.md:
- Off until configured with a destination URL (via --reach-url, CARGENTO_REACH_URL, or ~/.cargento/reach_url)
- Refuses redirects and ignores proxy environment variables
- Sends strictly bounded scalar count payload `{"needs_input": int, "finished_unread": int}` without any session text or metadata
- Cooldown-throttled delivery triggered by count changes
- Protected credential handling (never logged or served)
- `--no-reach` off switch forwarded across daemon respawns

## Verification results
- All 3504 dashboard tests pass
- All 513 script tests pass
- 0 errors across 163 files in mypy
- All checks pass in ruff check and ruff format
- Zero em or en dashes introduced in prose or code
