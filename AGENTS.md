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
python3 -m unittest cargento/skills/cargento/tests/test_server.py
claude plugin validate . --strict
claude plugin validate ./cargento --strict
```

## Versioning

The plugin version must be identical in four places: the `.claude-plugin/marketplace.json` plugin entry, `cargento/.claude-plugin/plugin.json`, `cargento/.codex-plugin/plugin.json`, and `cargento/gemini-extension.json`. The plugin description must be identical in five (those four plus the Antigravity `cargento/plugin.json`). `scripts/validate_plugins.py` enforces both.

## Portability Rules

Shared skill bodies must work in every harness:

- No `${CLAUDE_PLUGIN_ROOT}` in skill bodies — resolve resources relative to `SKILL.md`.
- No host-specific tool names (`mcp__claude_ai_*`, `ToolSearch(`, `Skill(skill=`, `subagent_type`) — describe capabilities semantically.
- The validator (`scripts/validate_plugins.py`) rejects these markers in any bundled Markdown.
