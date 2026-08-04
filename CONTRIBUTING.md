# Contributing to Cargento

Thanks for your interest in improving Cargento. This document covers everything you need to get a change from idea to merged PR.

## What Cargento is

Cargento is an agnostic agent cartography and visualization tool, distributed as a cross-platform plugin (Claude Code, Codex, Antigravity/AGY, Gemini CLI). The repository is markdown-first: the product is the `cargento/` plugin and its single `cargento` skill, backed by a stdlib-only Python dashboard server.

Read [AGENTS.md](AGENTS.md) for the repository architecture and [COMPATIBILITY.md](COMPATIBILITY.md) for the cross-platform contract before making changes.

If you are looking for what to work on rather than how, [docs/visibility-2x2](docs/visibility-2x2/README.md) is a local board of candidate signals scored on how much a user could act on them against how hard the information is to get without Cargento. Open it with the `visibility-2x2` skill. It is a working document, so treat it as an argument in progress rather than a committed roadmap.

## Development setup

Prerequisites: Python 3.11+ (`runtime-floor` checks the shipped entry point on 3.11, while the full
gate runs on 3.12), `git`, Node (only for `scripts/lint_embedded.py`, which checks the frontend JS;
pass `--allow-missing-node` to skip that half), and optionally the Claude Code / AGY CLIs for native
validation. See [COMPATIBILITY.md](COMPATIBILITY.md) for why 3.11 is the floor.

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
- `scripts/lint_embedded.py`, which lints the shipped HTML, CSS and JS source files directly.
- `runtime-floor`, which launches the shipped `server.py` entry point directly from outside the
  checkout on Python 3.11 and exercises `--help` and `--diagnose --json`.
- The full unittest suite under `coverage`, against the `fail_under` threshold in `pyproject.toml`.
  That threshold only ratchets up. A PR that must merge below it needs the `coverage-exception`
  label, which is visible in the PR timeline.
- `platform-tests`, the unit suite re-run natively on Ubuntu, macOS and Windows.

### Tests

Every behavior change to `server.py` or `cargento_runtime/` needs a regression test in
`cargento/skills/cargento/tests/`. The suite uses only the standard library, and the fixtures are
temp directories and in-memory SQLite databases. It has three layers, and a change usually touches
more than one:

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
targeted test actually fails. This is the only way to tell a test from a decoration, and skipping it
has shipped hollow tests here more than once. Two failure modes worth knowing:

- An assertion that cannot fail. `assertIn(word, "some string")` matches substrings, so a test
  meant to prove a word survived truncation passed on a fragment of it.
- An assertion that restates the implementation. Comparing a function's output to the very table it
  reads from moves both sides together, so the check holds no matter how wrong the table is. Assert
  literals, or patch the input to values the test chose.

A flipped comparison is the cheapest mutation to try, and the most revealing: change one `<` to
`<=`, or one `and` to `or`, and run the suite. Anything that still passes is a boundary nothing
pins.

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
- Every file the dashboard needs at runtime must be present, and must be a file rather than a
  directory. The list is `CARGENTO_RUNTIME_FILES` in `scripts/validate_plugins.py`: the launcher, the
  hook forwarder, all three package initializers, every runtime module and collector, and the three
  frontend assets. Adding a runtime module means adding it there, and a test compares the list
  against what the checkout actually ships so it cannot fall behind quietly.
  `python3 scripts/validate_plugins.py --runtime-files <plugin root>` checks an installed copy, which
  is what the `Plugin Compatibility` canary runs against the path Codex installed.

### Design constraints for the dashboard implementation

The module map, the inward-only dependency rule, and how one process's configuration, state and
services are held are owned by
[docs/design-runtime-architecture.md](docs/design-runtime-architecture.md). Read it before adding
a runtime file or an import between two of them: the import graph is asserted by a test, and its
allowlist changes only in a PR that makes a reviewed ownership decision.

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
- The frontend rebuilds `#app` from scratch every five seconds. Anything the reader set has to
  live in a module variable and be reapplied after the swap: the expanded row, the keyboard cursor,
  the filters, the scroll offset. Two rules follow. Escape every payload-derived string through
  `esc()`, because the page builds HTML by concatenation and session titles come from files a
  project can write. And never sort rows on a value that ticks: order on the state, then on a fixed
  timestamp, then on the session id, or rows move under the reader between refreshes.
- Size text through the `--fs-*` scale in `styles.css` and nothing else. A test rejects any raw px
  `font-size` and any declared step the file never uses, because the stylesheet previously carried
  twenty ad-hoc values between 8px and 15px, which is drift rather than hierarchy. Adding a rung is
  fine when a real role needs one. Reaching past the scale for a one-off is how the twenty came back.
- Keep the three ink steps far enough apart to mean something. A test computes the contrast of
  `--ink`, `--ink2` and `--ink3` against the worst surface each can land on, in both themes, and
  requires `--ink3` to clear WCAG AA and each step to beat the next by 25 percent. `--ink3` carries
  most of the metadata on the board and once sat at 3.1:1, below AA, on the smallest type in the UI.
- Draw selected state with `--sel-bg` and `--sel-bd`. The display toggle, the order segment, the
  state filter chips and the flag pill all used to paint selection as `--panel` over `--bg`, a 1.2:1
  step, so on and off were indistinguishable in either theme.
- Test the page by running it, not by matching strings against its source. `PageJsHarness` in
  `page_harness.py` executes the real dashboard script (the `web/*.js` parts, concatenated in
  `APP_PARTS` order) under node against a stub DOM, so a test can fire a
  click or a keystroke and assert on what the page did. A source-text assertion passes
  forever after the behavior behind it breaks.
- Load the frontend before creating the daemon log, binding the socket, forking, or spawning a
  Windows child. Then acquire the log file and listening socket before forking (or, on Windows,
  before waiting on the re-spawned child). After the fork there is nowhere for a failure to go.
  Reporting one means pointing the user at the very log that could not be opened. Note that
  `os.makedirs(exist_ok=True)` is not this check: it succeeds for a directory that already exists
  whatever its mode, which is the likeliest bad state of all.
- Never use `os.kill`, including `os.kill(pid, 0)` for liveness. CPython implements it on Windows
  through `TerminateProcess`, so a liveness check would kill the process it was asked to inspect.
  Probe `/api/health` instead.
- Stopping goes over HTTP, so the CLI and the page share one code path, and a handler that stops the
  server must do it on its own thread. Not because a `ThreadingHTTPServer` handler would deadlock
  calling `server.shutdown()` inline. It would not, since every request already runs on its own
  thread and the accept loop is never the caller. The reason is that `shutdown()` blocks until the accept
  loop notices, up to one poll interval, and the client should not be held open for that just to hear
  "stopping".
- Because of that delay, nothing may report a stop as *finished* until the port is free. Ask by
  binding the port, not by connecting to it: a connect to a bound socket that nothing is accepting
  from still succeeds, and repeated connects fill the backlog and then report the port gone while it
  is still bound.
- Guard the sink, not the caller. A check against work landing after teardown belongs in the function
  that actually writes the DOM, the file or the socket: `render()`, not `refresh()`. Guarding a
  caller was wrong twice for the same stop button: first it missed the request already in flight,
  then it missed the other fourteen callers, one of which was a keystroke. If you do also guard a
  caller, it must be for something the sink cannot see, and say so.

The reasoning behind these, and the alternatives that were tried and rejected, is in [docs/design-cross-platform.md](docs/design-cross-platform.md); for the Spacedock reader, [docs/design-spacedock.md](docs/design-spacedock.md); for how a row is labelled and identified, [docs/design-session-identity.md](docs/design-session-identity.md); and for `--daemon`/`--status`/`--stop`, [docs/design-daemon.md](docs/design-daemon.md).

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

This is the contribution we most want. Each harness is one registry entry: a key, a display label, a cheap discovery predicate, and a collector function. The runtime contract is `HarnessSpec` in `cargento_runtime/aggregate.py`, whose discovery takes `(config, state)` and whose collector takes `(config, state, now, window_hours, show_all)`. The registry itself is `aggregate.default_harnesses()`, and every row is a module under `cargento_runtime/collectors/`: add yours there, then add a row. Follow `collectors/codex.py` for the shape, and study `collectors/droid.py` (JSONL-based) or `collectors/goose.py` (SQLite-based) as templates. Requirements:

- Discovery must be cheap (an `isdir` or a `glob_under()` call), and the collector must degrade gracefully on schema drift.
- Resolve store roots through the candidate-set resolver rather than a single hardcoded path, and honor the harness's documented relocation variable if it has one.
- Document the data source and its caveats in `SKILL.md`'s data-sources list. The documentation-matches-code test asserts it.
- Add tests with a synthetic store fixture, including a hostile-path case.
- Add the harness to the page's `HARNESS` table in `cargento_runtime/web/spark.js` with a unique two-letter monogram. A contract test compares that table to the registry, so a row added on one side only fails the build.
- Every row's field set is declared once, in `base_session` in `cargento_runtime/sessions.py`, at `None`. Populate the fields your store can answer and leave the rest; do not add a key that only your harness sets, because then every consumer has to test for presence instead of for a value. `provider` and `model` are there for the same reason and only Pi fills them today, since Pi is the one harness that spends another product's allowance rather than its own.

Before writing any of it, settle whether the thing deserves a row of its own: two store formats can be one harness, and one vendor can be two. [`docs/design-harness-registry.md`](docs/design-harness-registry.md) owns that judgement and the one time it had to be revisited.

### Adding a quota source

A harness row can also publish quota, through the optional `usage` provider on `HarnessSpec`. There are three shapes, and which one applies is a question about the vendor rather than a choice: read it from the harness's own store (Codex, Copilot), fetch it with the harness's own credential (Claude, Cursor), or receive it from a harness that pushes its quota to a user-configured command (Antigravity). A fetch also sets `usage_is_fetch`, which is what raises the disclosure modal, and adds a row to `FETCH_VENDORS` in `quota.py`.

Two obligations are not optional. Name the endpoint and the credential location in `SECURITY.md` in the same PR as the code, because that section is the contract the fetch is held to. And capture a real payload from a live install before writing the parser: every quota source added so far had a field name, a unit, or a rendering that the vendor's own documentation got wrong, and the failures were silent ones (a counter reading zero, an amount in cents read as dollars). [`docs/design-usage-quota.md`](docs/design-usage-quota.md) records each of those and the surfaces that were tried and rejected.

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
and behavior-focused dashboard test modules on the main tip, rather than the whole quality gate,
which already ran on every commit that reached main. From there it writes one bump commit updating
all owned version
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
