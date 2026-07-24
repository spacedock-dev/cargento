# Contributing to Cargento

Thanks for your interest in improving Cargento! This document covers everything you need to get a change from idea to merged PR.

## What Cargento is

Cargento is an agnostic agent cartography and visualization tool, distributed as a cross-platform plugin (Claude Code, Codex, Antigravity/AGY, Gemini CLI). The repository is markdown-first: the product is the `cargento/` plugin and its single `cargento` skill, backed by a stdlib-only Python dashboard server.

Read [AGENTS.md](AGENTS.md) for the repository architecture and [COMPATIBILITY.md](COMPATIBILITY.md) for the cross-platform contract before making changes.

## Development setup

Prerequisites: Python 3.8+ (3.12 recommended — it's what CI runs), `git`, and optionally the Claude Code / AGY CLIs for native validation.

```bash
git clone https://github.com/spacedock-dev/cargento.git
cd cargento
python3 -m pip install -r requirements-validation.txt   # PyYAML, for the contract validator
```

Run the dashboard locally without installing any plugin:

```bash
python3 cargento/skills/cargento/server.py --port 4553
open http://localhost:4553/
```

## Before you open a PR

Run the full validation suite locally — CI runs the same commands, but finding failures locally is faster:

```bash
python3 scripts/validate_plugins.py
python3 -m unittest scripts/tests/test_validate_plugins.py
python3 -m unittest scripts/tests/test_bump_version.py
python3 -m unittest cargento/skills/cargento/tests/test_server.py
# If you have the native CLIs installed:
claude plugin validate . --strict
claude plugin validate ./cargento --strict
agy plugin validate ./cargento
```

Every behavior change to `server.py` needs a regression test in `cargento/skills/cargento/tests/test_server.py`. The test suite uses only the standard library — fixtures are temp directories and in-memory SQLite databases; see the existing tests for patterns.

### Rules the validator enforces

- The plugin **version** must be identical everywhere it appears (marketplace metadata + entry, and the Claude, Codex, and Gemini manifests); the **description** in five places (marketplace entry, those three manifests, plus the Antigravity `plugin.json`). **Never bump versions in a PR** — the `version-guard` check will fail it; see [Releases](#releases).
- Skill bodies must stay **host-neutral**: no `${CLAUDE_PLUGIN_ROOT}`, no host-specific tool names. Describe capabilities, not tool APIs.
- The skill description stays under 300 characters, and `agents/openai.yaml` keeps its 25–64 character short description.
- Every Markdown link inside the skill must resolve within the repository.

### Design constraints for `server.py`

- **Stdlib only, Python 3.8+.** No dependencies, ever — the skill must run on a bare `python3`.
- **Read-only.** The server only reads harness session stores; it must never write to them or block a live agent's writes (use `mode=ro` SQLite connections with short timeouts).
- **Defensive parsing.** A broken or unexpected harness store is skipped, never fatal — one bad record must not take a collector offline.
- **Localhost only.** The server binds 127.0.0.1; do not "fix" this, it exposes local session data.

## Commits

We require [DCO](https://developercertificate.org/) sign-off and use conventional commit messages:

```bash
git commit -s -m "feat(skill): add new harness collector"
```

Format: `<type>(<scope>): <description>` — types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.

## Pull requests

1. Fork (or branch, for maintainers) and make your change.
2. Run the validation suite above.
3. Open a PR against `main`. `main` is protected: PRs are required, the `validate` and `version-guard` checks must pass, history is linear (squash/rebase), all conversations must be resolved, and merged branches are deleted automatically.
4. If your PR closes an issue, use an explicit `Closes #NNN` line.

## Adding support for a new harness

The most valuable contribution! Each harness is one entry in the `HARNESSES` registry in `server.py`: a key, a display label, a cheap discovery predicate, and a collector function. Study `collect_droid` (JSONL-based) or `collect_goose` (SQLite-based) as templates. Requirements:

- Discovery must be cheap (a `glob` or `isdir`), and the collector must degrade gracefully on schema drift.
- Document the data source and its caveats in `SKILL.md`'s data-sources list.
- Add tests with a synthetic store fixture.

## Releases

Releases are tag-driven and fully automated (maintainers only):

```bash
git checkout main && git pull
git tag v0.2.0        # v-prefixed is canonical; bare 0.2.0 also works — pick ONE form per release
git push origin v0.2.0
```

The [Release workflow](.github/workflows/release.yml) refuses the tag unless it is on main, is strict semver, and is strictly greater than every existing release tag — semver only moves forward, and back-tagging is impossible. It then runs the full validation suite on the main tip, writes one bump commit updating all owned version fields (skipped when the manifests already carry the tagged version — which is also how you release the current version as-is), moves the tag onto the released commit, and publishes a GitHub Release with generated notes. Every step is idempotent, so re-running a partially failed release finishes it. Release tags are immutable (a tag ruleset blocks deleting or moving them), and PRs can never change version fields (the `version-guard` check).

## Reporting bugs and requesting features

Use the [issue templates](https://github.com/spacedock-dev/cargento/issues/new/choose). For security concerns, see [SECURITY.md](SECURITY.md) — please don't open public issues for those.

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). Be excellent to each other.

## License

By contributing, you agree that your contributions are licensed under the [Apache License 2.0](LICENSE).
