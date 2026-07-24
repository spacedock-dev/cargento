# AGENTS.md

## Project Overview

This repository distributes Cargento — an agnostic agent cartography and visualization tool — to Codex, Claude Code, Antigravity/AGY, and Gemini CLI. It contains one markdown-first plugin rather than a code application:

- `cargento/` — the agent cartography dashboard skill

The user-facing workflow lives in `cargento/skills/cargento/`. Every user-facing workflow must be usable as a skill so Codex can discover it; Claude-only agents and lifecycle hooks may remain in their native directories if ever added.

## Architecture

```
cargento/                           # plugin root
├── .claude-plugin/plugin.json      # Claude Code manifest
├── .codex-plugin/plugin.json       # Codex manifest
├── plugin.json                     # Antigravity / AGY manifest
├── gemini-extension.json           # Gemini CLI extension manifest
└── skills/
    └── cargento/                   # the dashboard skill
        ├── SKILL.md                # shared skill body (all harnesses)
        ├── server.py               # stdlib-only dashboard server
        ├── agents/openai.yaml      # Codex presentation metadata
        └── tests/test_server.py    # server unit tests
```

Repository marketplaces live at `.claude-plugin/marketplace.json` and `.agents/plugins/marketplace.json`.

## Commit Conventions

```bash
git commit -s -m "feat(skill): add new capability to cargento"
```

**Format:** `<type>(<scope>): <description>` with sign-off (DCO required)

- For multi-line commit messages with backticks, apostrophes, or special characters, write to a temp file and use `git commit -F <file>` instead of heredocs to avoid shell escaping issues.

## PR Workflow

- When opening PRs that close issues, always use explicit `Closes #NNNN` lines (one per issue), never comma-separated lists, so GitHub autoclose works.
- After requesting a PR review, always check for Copilot inline review comments in addition to top-level reviews.
- Never commit or push to another author's PR branch without explicit confirmation from the user.

## Pre-PR Checks

Run the full validation suite locally before opening any PR; do not rely on CI to surface failures:

```bash
python3 -m pip install -r requirements-validation.txt
python3 scripts/validate_plugins.py
python3 -m unittest scripts/tests/test_validate_plugins.py
python3 -m unittest scripts/tests/test_bump_version.py
python3 -m unittest cargento/skills/cargento/tests/test_server.py
claude plugin validate . --strict
claude plugin validate ./cargento --strict
```

## Versioning and Releases

The plugin version must be identical in five places: `.claude-plugin/marketplace.json` (`metadata.version` and the plugin entry), `cargento/.claude-plugin/plugin.json`, `cargento/.codex-plugin/plugin.json`, and `cargento/gemini-extension.json`. The plugin description must be identical in five (the marketplace entry, those three manifests, plus the Antigravity `cargento/plugin.json`). `scripts/validate_plugins.py` enforces both.

Version fields are **owned by the tag-driven Release workflow** — never edit them in a PR (the `version-guard` check fails any PR that does). To release:

```bash
git checkout main && git pull
git tag v0.2.0        # v-prefixed is canonical (bare 0.2.0 also works — pick ONE form per release)
git push origin v0.2.0
```

The Release workflow validates the tag (must be on main, strict semver, strictly greater than every existing release tag — back-tagging is impossible), runs the full validation suite on the main tip, writes one `chore(release)` bump commit via `scripts/bump_version.py`, moves the tag onto that commit, and publishes a GitHub Release. Every step is idempotent: a re-run after a partial failure resumes cleanly, and tagging the version the manifests already carry releases it as-is (that is how the initial 0.1.0 ships). If main advances between tag push and the run, the release includes those extra commits. Release tags are immutable — a tag ruleset blocks deleting or moving them.

## Portability Rules

Shared skill bodies must work in every harness:

- No `${CLAUDE_PLUGIN_ROOT}` in skill bodies — resolve resources relative to `SKILL.md`.
- No host-specific tool names (`mcp__claude_ai_*`, `ToolSearch(`, `Skill(skill=`, `subagent_type`) — describe capabilities semantically.
- The validator (`scripts/validate_plugins.py`) rejects these markers in any bundled Markdown.
