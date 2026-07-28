# Contributing to Cargento

Thanks for your interest in improving Cargento. This document covers everything you need to get a change from idea to merged PR.

## What Cargento is

Cargento is an agnostic agent cartography and visualization tool, distributed as a cross-platform plugin (Claude Code, Codex, Antigravity/AGY, Gemini CLI). The repository is markdown-first: the product is the `cargento/` plugin and its single `cargento` skill, backed by a stdlib-only Python dashboard server.

Read [AGENTS.md](AGENTS.md) for the repository architecture and [COMPATIBILITY.md](COMPATIBILITY.md) for the cross-platform contract before making changes.

## Development setup

Prerequisites: Python 3.11+ (3.12 is what the PR checks run, so it is the safer choice), `git`, Node
(only for `scripts/lint_embedded.py`, which checks the embedded JS; pass `--allow-missing-node` to
skip that half), and optionally the Claude Code / AGY CLIs for native validation. See
[COMPATIBILITY.md](COMPATIBILITY.md) for why 3.11 is the floor.

```bash
git clone https://github.com/spacedock-dev/cargento.git
cd cargento
# PyYAML for the contract validator; ruff, mypy and coverage for the quality gate.
python3 -m pip install -r requirements-validation.txt -r requirements-dev.txt
```

Run the dashboard locally without installing any plugin:

```bash
python3 cargento/skills/cargento/server.py --port 4553
python3 -m webbrowser -t http://127.0.0.1:4553/
```

## Before you open a PR

Run the canonical pre-PR suite in [AGENTS.md](AGENTS.md#pre-pr-checks) and make sure it is clean.
It is kept in one place deliberately. A second copy here would drift, and a contributor following a
short copy passes locally and then fails the required gate.

Finish with a docs pass. `/sync-docs` (the skill at `.claude/skills/sync-docs/SKILL.md`) reconciles
the documentation against whatever your change did to the code and commits the result onto your
branch, so the doc updates ride in the same PR.

### The quality gate

`quality-gate` is a required check and covers more than the contract validator:

- `ruff check .` with `select = ALL`. The curated ignore list, with a reason for each, is in
  `pyproject.toml`. Do not add an ignore without one.
- `ruff format --check .`
- `mypy` in `--strict` mode with `warn_unreachable`.
- `scripts/lint_embedded.py`, which lints the HTML, CSS and JS embedded in `server.py`.
- The full unittest suite under `coverage`, against the `fail_under` threshold in `pyproject.toml`.
  That threshold only ratchets up. A PR that must merge below it needs the `coverage-exception`
  label, which is visible in the PR timeline.
- `platform-tests`, the unit suite re-run natively on Ubuntu, macOS and Windows.

### Tests

Every behavior change to `server.py` needs a regression test in
`cargento/skills/cargento/tests/test_server.py`. The suite uses only the standard library, and the
fixtures are temp directories and in-memory SQLite databases. It has three layers, and a change
usually touches more than one:

- Pure-function tests. Platform- and clock-dependent decisions take their environment as an explicit
  argument rather than reading global state (design decision D-4), so one runner exercises the
  Linux, macOS and Windows branches. Prefer this shape for anything platform-dependent. It is what
  keeps new branches from being dead code on the gate runner.
- Behavioural contracts. A realistic store fixture per harness, asserted to discover when present,
  stay quietly undiscovered when absent, survive a corrupt store without taking the other harnesses
  down, and collapse to one row when the same session exists in two candidate roots. A new harness
  also needs a hostile-path case with glob metacharacters, `%`, `#`, spaces, and non-ASCII.
- Documentation-matches-code. Store paths, relocation variables, the Python floor and the loopback
  address documented in `SKILL.md` are asserted against the implementation, so doc drift fails the
  build. Documenting a path the code does not support is therefore a test failure.

Before trusting a new contract, mutation-check it: break the behaviour deliberately and confirm the
targeted test actually fails.

Known flake: the page tests shell out to `node` with a 30-second timeout. On the Windows runner that
occasionally expires on process start, surfacing as
`subprocess.TimeoutExpired: … page_test.js`. It is a runner-speed artifact rather than a page bug,
so re-run the job before investigating, and check the traceback is a timeout and not an assertion.

### Rules the validator enforces

- The plugin version must be identical in the Claude, Codex and Gemini manifests, and the
  description in those three plus the Antigravity `plugin.json`. Never bump versions in a PR,
  because the `version-guard` check will fail it. See [Releases](#releases).
- Skill bodies must stay host-neutral: no `${CLAUDE_PLUGIN_ROOT}`, no host-specific tool names.
  Describe capabilities, not tool APIs.
- The skill description is at most 300 characters, and `agents/openai.yaml` keeps its 25 to 64
  character short description.
- Every relative Markdown link, in the skill and in the repository's prose docs, must resolve within
  the repository, and so must every `#heading-anchor`. Anchors are slugged the way GitHub does it,
  so a link to a heading you renamed fails the build.
- No prose doc may spell the dashboard URL with `localhost`. The server binds IPv4 loopback only, so
  it is always `127.0.0.1:4553`.
- Two link forms the checker cannot parse, both avoidable: unbalanced parentheses in a bare
  destination (wrap the target in `<>`), and links inside a four-space-indented code block (use a
  fence instead).

### Design constraints for `server.py`

- Stdlib only, Python 3.11+. No dependencies, ever. The skill must run on a bare `python3`.
- Read-only. The server only reads harness session stores. It must never write to them or block a
  live agent's writes, so use `mode=ro` SQLite connections with short timeouts.
- Defensive parsing. A broken or unexpected harness store is skipped, never fatal. One bad record
  must not take a collector offline.
- Localhost only. The server binds 127.0.0.1. Do not "fix" this; it exposes local session data.
- Never interpolate a literal path into a glob pattern. Go through `glob_under()`, which escapes
  glob metacharacters in the root and sorts the result. A home directory containing `[` otherwise
  breaks discovery completely and silently, and unsorted glob output makes "newest file wins" ties
  nondeterministic across platforms.
- Build every SQLite URI with `sqlite_ro_uri()`, never an f-string. SQLite percent-decodes the path,
  and a Windows path needs separator and drive-letter conversion. Never generalize `immutable=1`
  beyond the one documented Antigravity call site: on a live agent database it can return incorrect
  results or `SQLITE_CORRUPT`.
- Never `mmap` a file a live harness is writing. Truncation mid-read is an uncatchable `SIGBUS` on
  POSIX. Tail transcripts through `reverse_lines()`.
- Compute freshness only through `age()`, `is_fresh()` and `newest_plausible()`, which reject
  implausibly future timestamps rather than clamping them. A clamped zero reads as "just now", which
  is the bug.
- Read nothing inside a project except what `SECURITY.md` § Project reads permits. Today that is
  Spacedock workflow and entity-state frontmatter, from absolute paths the session itself recorded.
  Never derive a project path by guessing, scanning or walking.

The reasoning behind these, and the alternatives that were tried and rejected, is in [docs/design-cross-platform.md](docs/design-cross-platform.md) and, for the Spacedock reader, [docs/design-spacedock.md](docs/design-spacedock.md).

## Commits

We require [DCO](https://developercertificate.org/) sign-off and use conventional commit messages:

```bash
git commit -s -m "feat(skill): add new harness collector"
```

Format: `<type>(<scope>): <description>`, where type is one of `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.

## Pull requests

1. Fork (or branch, for maintainers) and make your change.
2. Run the pre-PR suite in [AGENTS.md](AGENTS.md#pre-pr-checks), then `/sync-docs`.
3. Open a PR against `main`. `main` is protected: PRs are required, the `validate`, `version-guard` and `quality-gate` checks must pass, history is linear (squash/rebase), all conversations must be resolved, and merged branches are deleted automatically.
4. If your PR closes an issue, use an explicit `Closes #NNN` line, one line per issue. A comma-separated list does not autoclose.

## Adding support for a new harness

This is the contribution we most want. Each harness is one entry in the `HARNESSES` registry in `server.py`: a key, a display label, a cheap discovery predicate, and a collector function. Study `collect_droid` (JSONL-based) or `collect_goose` (SQLite-based) as templates. Requirements:

- Discovery must be cheap (an `isdir` or a `glob_under()` call), and the collector must degrade gracefully on schema drift.
- Resolve store roots through the candidate-set resolver rather than a single hardcoded path, and honor the harness's documented relocation variable if it has one.
- Document the data source and its caveats in `SKILL.md`'s data-sources list. The documentation-matches-code test asserts it.
- Add tests with a synthetic store fixture, including a hostile-path case.

## Releases

Releases are tag-driven and fully automated (maintainers only):

```bash
git checkout main && git pull
git tag v0.2.0        # v-prefixed is canonical; bare 0.2.0 also works, but pick ONE form per release
git push origin v0.2.0
```

The [Release workflow](.github/workflows/release.yml) refuses the tag unless it is on main, is
strict semver, and is strictly greater than every existing release tag. Semver only moves forward,
and back-tagging is impossible. It then runs the contract validator plus the validator, bump-version
and server test modules on the main tip, rather than the whole quality gate, which already ran on
every commit that reached main. From there it writes one bump commit updating all owned version
fields, moves the tag onto the released commit, advances the `stable` branch to it, and publishes a
GitHub Release with generated notes. `stable` is what the shared
[spacedock-dev/marketplace](https://github.com/spacedock-dev/marketplace) listing tracks, so a
release that did not move it would leave the marketplace serving an older Cargento.
The bump is skipped when the manifests already carry the tagged version, which is also how you
release the current version as-is. Every step is idempotent, so re-running a partially failed
release finishes it. Release tags are immutable (a tag ruleset blocks deleting or moving them), and
PRs can never change version fields (the `version-guard` check).

## Reporting bugs and requesting features

Use the [issue templates](https://github.com/spacedock-dev/cargento/issues/new/choose). For security concerns, see [SECURITY.md](SECURITY.md), and please don't open public issues for those.

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). Be excellent to each other.

## License

By contributing, you agree that your contributions are licensed under the [Apache License 2.0](LICENSE).
