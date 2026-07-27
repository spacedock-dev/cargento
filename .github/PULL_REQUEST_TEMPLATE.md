## Summary

<!-- What does this change and why? -->

## Test plan

- [ ] Ran the pre-PR suite in `AGENTS.md` § Pre-PR Checks (ruff, ruff format, mypy, `lint_embedded.py`, `validate_plugins.py`, `bump_version.py --current`, tests under coverage) and it is clean
- [ ] Ran `/sync-docs` — the doc updates for this change ride in this PR, or there was nothing to reconcile
- [ ] Behavior changes to `server.py` include a regression test
- [ ] No version field was touched (`version-guard` fails any PR that bumps one)
- [ ] Commits are signed off (`git commit -s`, DCO)

<!-- If this closes an issue, one line per issue — a comma-separated list does not autoclose: -->
<!-- Closes #NNN -->
