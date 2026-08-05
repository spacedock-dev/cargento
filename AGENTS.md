# AGENTS.md

## Project Overview

This repository distributes Cargento — an agnostic agent cartography and visualization tool — to Codex, Claude Code, Antigravity/AGY, and Gemini CLI. It contains one markdown-first plugin rather than a code application:

- `cargento/` — the agent cartography dashboard skill, and the plugin root Claude Code, Codex
  and Antigravity all install
- `cargento-gemini/` — a hooks-only Gemini CLI extension root. It exists because Claude Code and
  Gemini CLI both load extension hooks from `<root>/hooks/hooks.json` and neither lets that path
  be moved, so a shared root hands each harness the other's event vocabulary

The user-facing workflow lives in `cargento/skills/cargento/`. Every user-facing workflow must be usable as a skill so Codex can discover it; Claude-only agents and lifecycle hooks may remain in their native directories if ever added.

## Architecture

```
cargento/                           # plugin root: Claude Code, Codex, Antigravity
├── .claude-plugin/plugin.json      # Claude Code manifest
├── .codex-plugin/plugin.json       # Codex manifest
├── plugin.json                     # Antigravity / AGY manifest
├── hooks/hooks.json                # Claude Code lifecycle hooks (its path, by convention)
├── hooks/codex-hooks.json          # Codex lifecycle hooks (declared in its manifest)
├── hooks.json                      # Antigravity lifecycle hooks (its path, at the root)
└── skills/
    └── cargento/                   # the dashboard skill
        ├── SKILL.md                # shared skill body (all harnesses)
        ├── server.py               # the stable launcher: calls cargento_runtime.cli.main
        ├── notify_hook.py          # loopback POST forwarder for the user-installed Claude hooks
        ├── cargento_runtime/       # importable dashboard runtime package
        │   ├── aggregate.py        # harness registry, failure boundary, and the application
        │   ├── claude_data.py      # Claude transcript reads shared by the collector and hooks
        │   ├── cli.py              # argument parsing, runtime assembly, and the serve branches
        │   ├── collectors/         # one harness collector per file, one per supported harness
        │   ├── config.py           # immutable process configuration and store roots
        │   ├── diagnostics.py      # store-path reporting for --diagnose
        │   ├── http_api.py         # the loopback server, its handler, and network helpers
        │   ├── io.py               # bounded file reads, safe globbing, and read-only SQLite
        │   ├── lifecycle.py       # state file, port probes, stop, and daemon detach
        │   ├── notifications.py    # hook state, popup policy, and the native notifier
        │   ├── quota.py            # quota: per-vendor fetches, pushed receipts, and the cache
        │   ├── records.py          # untrusted-record parsing and normalization
        │   ├── sessions.py         # session identity, shape, and deterministic aggregation
        │   ├── spacedock.py        # Spacedock workflow and entity cartography
        │   ├── state.py            # mutable process state, locks, and bounded caches
        │   ├── transcripts.py      # shared metadata, prompt titles, non-Claude analyzers
        │   ├── turns.py            # generic incremental turn scanning and turn display
        │   └── web/                # HTML, CSS, JS, and byte-preserving page loader
        ├── agents/openai.yaml      # Codex presentation metadata
        └── tests/                  # dashboard unit tests and shared support
```

The Codex/AGY marketplace lives at `.agents/plugins/marketplace.json`. There is no Claude
marketplace in this repository: cargento is listed in the shared
[spacedock-dev/marketplace](https://github.com/spacedock-dev/marketplace), which tracks the
`stable` branch that the Release workflow advances on every release.

## Documentation

Docs are owned, not shared. Each file below owns a subject; every other file links to the owner
rather than restating it. The full map, including the constraints the validator places on the
shipped skill body, lives in the `sync-docs` skill at `.claude/skills/sync-docs/SKILL.md`.

| File | Owns |
|---|---|
| `README.md` | The front door: what Cargento is, install per harness, skill inventory, links out. |
| `AGENTS.md` | **This file.** The repository contract for agents, and the canonical pre-PR command list. |
| `CLAUDE.md` | Claude-Code-only addenda; imports this file. |
| `CONTRIBUTING.md` | The human contributor journey, and the dashboard implementation constraints. |
| `COMPATIBILITY.md` | The cross-harness and cross-platform contract, and the Python floor. |
| `SECURITY.md` | Security invariants, accepted exposures, and private reporting. |
| `cargento/skills/cargento/SKILL.md` | The shipped product surface. A validated artifact — see the portability rules below. |
| `docs/design-runtime-architecture.md` | **Canonical** module map: what each runtime file owns, which way dependencies run, and how config/state/application are held. |
| `docs/design-*.md` | Durable design rationale, including alternatives that were tried and rejected. Each links to the architecture owner rather than repeating its module map. |
| `docs/plans/*.md` | Transient plans for unshipped work. Delete a plan once its work ships. |
| `docs/captures/` | Recorded hook payload shapes from real harness sessions: the evidence behind any adapter gate marked measured. Field names and timings only, never values. |
| `.claude/skills/*/SKILL.md` | Repository development skills (`sync-docs`, `visibility-2x2`). Not shipped with the plugin, so the portability rules below do not apply to them. |
| `docs/visibility-2x2/` | The Visibility 2x2 prioritisation board and the blind-panel evidence behind its scores. A local working tool, opened by the `visibility-2x2` skill. |

`scripts/validate_plugins.py` gates the docs as well as the plugin: across the files above it
resolves every relative Markdown link **and heading anchor**, and rejects the `localhost` spelling of
the dashboard URL (the server is IPv4-only). Deleting or renaming any of them fails the build. It also
owns `CARGENTO_RUNTIME_FILES`, the inventory of every file the shipped dashboard needs at runtime;
`--runtime-files <plugin root>` checks an installed copy without the repository around it.

Run `/sync-docs` before opening a PR (see Pre-PR Checks) so doc updates ride in the PR that changes
the code. Claude Code discovers it as a skill; on other harnesses, read
`.claude/skills/sync-docs/SKILL.md` and follow it directly.

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

**This block is the canonical pre-PR suite.** Every other document points here rather than keeping
its own copy — divergent copies are how the gate drifts. Run it locally before opening any PR; do
not rely on CI to surface failures:

```bash
python3 -m pip install -r requirements-validation.txt -r requirements-dev.txt
ruff check .
ruff format --check .
mypy
python3 scripts/lint_embedded.py   # needs node; add --allow-missing-node to degrade
python3 scripts/validate_plugins.py
python3 scripts/bump_version.py --current   # version-field parity across all owned locations
# `--current` proves the five fields AGREE; `version-guard` additionally proves they have not
# MOVED since the merge base. Check that half yourself — nothing local does:
git diff "$(git merge-base origin/main HEAD)"..HEAD \
  -- '*plugin.json' '*marketplace.json' '*gemini-extension.json' | grep -E '^[+-].*"version"'
coverage erase
coverage run -m unittest discover -s cargento/skills/cargento/tests -t .
coverage run -a -m unittest \
  scripts.tests.test_validate_plugins scripts.tests.test_bump_version \
  scripts.tests.test_lint_embedded scripts.tests.test_bench_collect \
  scripts.tests.test_capture_hook scripts.tests.test_bench_event_latency
coverage report   # enforces the fail_under threshold from pyproject.toml
# Native validators, if the CLIs are installed (they are not available on stock runners):
claude plugin validate ./cargento --strict
agy plugin validate ./cargento
```

Then reconcile the docs before you push. Run `/sync-docs` in your agent — it is a skill, not a
shell command — and let it commit any doc updates onto this same branch. Then:

```bash
git push -u origin HEAD && gh pr create
```

`/sync-docs` is a docs-only pass that diffs the docs against the code and fixes the drift the change
introduced. It also holds the human-facing prose docs it touched to the voice standard written out
in its own "Voice and tone" section — those docs are written for people, and an agent topping them
up in model-default voice is how that erodes — and greps them for the tone tells, since nothing in
CI checks that. The optional third-party `humanizer` skill automates that pass but is not required
and is not vendored here. `/sync-docs` lives at `.claude/skills/sync-docs/SKILL.md`; harnesses
without skill discovery should read that file and follow it.

## Quality Gate

Every PR must pass the `quality-gate` required check (`.github/workflows/quality-gate.yml`): ruff with `select = ALL` (curated ignores documented in `pyproject.toml`), `ruff format --check`, `mypy --strict`, the HTML/CSS/JS frontend source linter (`scripts/lint_embedded.py`), a direct-launch smoke test on the Python 3.11 runtime floor, the full unittest suite under `coverage` with the `fail_under` threshold from `pyproject.toml`, and `platform-tests` — the same unit suite re-run natively on Ubuntu, macOS and Windows. The threshold only ratchets up — never lower it in a PR. A PR that must merge below threshold needs the `coverage-exception` label, which is visible in the PR timeline.

## Versioning and Releases

The plugin version must be identical in three places: `cargento/.claude-plugin/plugin.json` (the
source of truth `bump_version.py` reads and writes from), `cargento/.codex-plugin/plugin.json`,
and `cargento-gemini/gemini-extension.json`. The plugin description must be identical in four:
those three manifests plus the Antigravity `cargento/plugin.json`. `scripts/validate_plugins.py`
enforces both.

Version fields are **owned by the tag-driven Release workflow** — never edit them in a PR (the `version-guard` check fails any PR that does). To release:

```bash
git checkout main && git pull
git tag v0.2.0        # v-prefixed is canonical (bare 0.2.0 also works — pick ONE form per release)
git push origin v0.2.0
```

The Release workflow validates the tag (must be on main, strict semver, strictly greater than every existing release tag — back-tagging is impossible), runs the contract validator plus the validator, bump-version and behavior-focused dashboard test modules on the main tip — not the whole quality gate, which already ran on every commit that reached main — writes one `chore(release)` bump commit via `scripts/bump_version.py`, moves the tag onto that commit, and publishes a GitHub Release. Every step is idempotent: a re-run after a partial failure resumes cleanly, and tagging the version the manifests already carry releases it as-is (that is how the initial 0.1.0 ships). If main advances between tag push and the run, the release includes those extra commits. Release tags are immutable — a tag ruleset blocks deleting or moving them.

## Portability Rules

Shared skill bodies must work in every harness:

- No `${CLAUDE_PLUGIN_ROOT}` in skill bodies — resolve resources relative to `SKILL.md`.
- No `.claude/skills/` paths in skill bodies — reference the bundled skill path, not a user cache.
- No host-specific tool names (`mcp__claude_ai_*`, `ToolSearch(`, `Skill(skill=`, `subagent_type`) — describe capabilities semantically.
- The validator (`scripts/validate_plugins.py`) rejects all six of these markers in any bundled Markdown.

These rules apply to Markdown **under `cargento/skills/`**. In `AGENTS.md` and `CLAUDE.md` the same
strings are the documentation of the rule and must stay.
