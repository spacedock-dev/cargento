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

Repository development skills use Git symlinks so Claude Code and Codex load one canonical body.
On Windows, enable Developer Mode and run `git config --global core.symlinks true` before cloning.
If an existing checkout shows `.agents/skills/*` as plain files, configure symlink support and clone
again; changing the setting does not repair files already checked out. See the
[Git for Windows symlink guidance](https://gitforwindows.org/symbolic-links.html).

Run the dashboard locally without installing any plugin:

```bash
python3 cargento/skills/cargento/server.py --port 4553
python3 -m webbrowser -t http://127.0.0.1:4553/
```

## Before you open a PR

Run the canonical pre-PR suite in [AGENTS.md](AGENTS.md#pre-pr-checks) and make sure it is clean.
It is kept in one place deliberately. A second copy here would drift, and a contributor following a
short copy passes locally and then fails the required gate.

Finish with a docs pass. Invoke the `sync-docs` skill to reconcile the documentation against
whatever your change did to the code and commit the result onto your branch, so the doc updates
ride in the same PR. `.claude/skills/` is the canonical repository-skill tree; Codex discovers the
same directories through the relative symlinks under `.agents/skills/`.

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

Those seven jobs run when the diff contains something they can measure. A change to prose
documentation alone skips them, because none of them reads it. The `quality-gate` check itself
always runs and always reports, so a prose-only PR is never left waiting on a check that never
arrives. `SKILL.md` and any file under `docs/` that a test opens by name count as code here,
not as prose, and `validate` runs on every PR regardless: it is the check that resolves the
Markdown links and heading anchors. Among the workflow files only `quality-gate.yml` itself
counts as code, since the others cannot change what those jobs measure and each already
reports its own status.

`scripts/bench_collect.py` is not part of the gate. It measures what a collection costs, in total and
per harness, against your own stores: `python3 scripts/bench_collect.py --repeat 7` prints a median,
and `--profile` gives a `cProfile` of one collect by function. Reach for it before optimising a
collector, since the cost is dominated by whichever harness has the most history on the machine and
that is not the same harness for everyone. It runs with usage fetching off, so a benchmark never makes
an outbound request.

`--simulate` asks the same question of a machine you do not have. It writes a synthetic store with a
named number of in-window sessions per harness, redirects every store root at it, and runs the same
collect, so a laptop with one busy harness can still measure what a balanced five-harness machine
would cost. `--list-simulations` names the built-in mixes, or pass your own as `claude=12,codex=12`.
The report prints the sessions each collector actually returned next to the number asked for: a
generator that drifts from a store shape collects nothing and would otherwise report a confident
share of an empty store.

`scripts/capture_hook.py` is also outside the gate. It answers the adapter-semantics question for the
event-driven work: what a harness lifecycle event means, how many arrive per turn, and in what order.
None of that is documented anywhere, so it has to be observed. `--report` summarises what has
accumulated, and captures land in `~/.cargento/captures`.

`--install` does not print a block to paste. It reads your existing `settings.json`, appends the
capture hook as an extra matcher group on each event, and writes the result to
`settings_with_hooks.json` beside it. Nothing is written over: read the merged file, then swap it in
yourself. Appending a group rather than editing one in place is what makes an existing hook on the same
event safe, since Claude Code runs every group whose matcher matches. Running it twice adds nothing.

It records shape and refuses content. A capture line carries the event name, the session prefix, a
salted digest of the working directory, the sorted top-level keys the payload carried, the tool name,
and how long the hook itself took. It never records a prompt, a tool argument, a tool result, or a
path. A research tool that captured those would be a worse leak than the thing it is researching,
because it writes to disk and accumulates.

`scripts/derive_prompt_shapes.py` re-derives the counts written into the harness-injected-prompt
comment block in `cargento_runtime/records.py`: which markup tag leads a harness's own machinery,
how often, and which of those a turn scanner already refuses. Point it at your own store with
`--claude-root` and `--codex-root`, or run it bare for the defaults. Every count in that comment
block is one of its outputs, so a reviewer can check the numbers instead of trusting them, and a new
harness build that changes a tag shows up as a name the vocabulary does not list.

It obeys the same rule `capture_hook.py` does, and for a sharper reason: a derivation script reads
every prompt anyone ever typed, credentials included. It prints counts and shape names only, and the
guard is a whitelist rather than a filter, so a label that is not a short markup name, a literal
already in the source, or one of a fixed set of column headings raises instead of printing. Its test
seeds a distinctive prompt into a fixture store and asserts the whole output carries none of it.
Discovering a new prose prefix is out of scope for the same reason: it cannot be done without
printing prose.

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

The page tests share one long-lived `node` process rather than starting one per check. It is
started on the first check that needs it and replaced every 150, so a full suite spawns about three
instead of 425. If it dies, every page test after it fails with `page-JS worker died:` followed by
whatever node wrote to stderr. A check that never settles is reported by the worker itself after 30
seconds as `page check did not settle within 30000ms`, which is a hung check rather than a slow
runner: read it as a page bug, not as something to re-run.

### Rules the validator enforces

- The plugin version must be identical in the Claude, Codex and Gemini manifests, and the
  description in those three plus the Antigravity `plugin.json`. Never bump versions in a PR,
  because the `version-guard` check will fail it. See [Releases](#releases).
- Skill bodies must stay host-neutral: no `${CLAUDE_PLUGIN_ROOT}`, no host-specific tool names.
  Describe capabilities, not tool APIs.
- Repository development skills live canonically under `.claude/skills/`. Every one needs an
  `agents/openai.yaml` file and a matching relative symlink under `.agents/skills/`; the validator
  rejects a copied, missing, orphaned or misdirected Codex alias.
- The skill description is at most 300 characters, and `agents/openai.yaml` keeps its 25 to 64
  character short description.
- Every relative Markdown link, in the skill and in the repository's prose docs, must resolve within
  the repository, and so must every `#heading-anchor`. Anchors are slugged the way GitHub does it,
  so a link to a heading you renamed fails the build.
- No prose doc may spell the dashboard URL with `localhost`. The server is IPv4-only, so
  it is always `127.0.0.1:4553`.
- Two link forms the checker cannot parse, both avoidable: unbalanced parentheses in a bare
  destination (wrap the target in `<>`), and links inside a four-space-indented code block (use a
  fence instead).
- Every file the dashboard needs at runtime must be present, and must be a file rather than a
  directory. The list is `CARGENTO_RUNTIME_FILES` in `scripts/validate_plugins.py`: the launcher, the
  hook forwarder, all three package initializers, every runtime module and collector, and every
  frontend source asset. Adding a runtime module or asset means adding it there, and a test compares
  the list against what the checkout actually ships so it cannot fall behind quietly.
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
- Loopback by default. The server binds `127.0.0.1` unless the operator passes `--host 0.0.0.0`, which is theirs to pass and not yours to default. Do not widen the default in code, and never admit a Host the bind itself did not ask for. See `SECURITY.md`.
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
- The frontend rebuilds `#app` from scratch on every refresh. What triggers one moved in
  Phase 1c:
  the leader tab holds an `EventSource` on `/api/stream` and refetches when the server announces a
  new revision, with a 20-second safety net behind it, and only a browser without `EventSource`
  falls back to a five-second poll. The rebuild itself is unchanged, so anything the reader
  set has to live in a module variable and be reapplied after the swap: the expanded row, the
  keyboard cursor, the filters, the scroll offset. Two rules follow. Escape every payload-derived string through
  `esc()`, because the page builds HTML by concatenation and session titles come from files a
  project can write. And never sort rows on a value that ticks: order on the state, then on a fixed
  timestamp, then on the session id, or rows move under the reader between refreshes.
- The frontend is one assembled scope under `web/`. The retired `next` query is rejected at the
  page boundary, not routed to another assembly path. The promoted files retain their `next-*` names and
  `cargento.next.*` browser keys so old bookmarks and stored leases stay harmless; do not infer a
  second frontend from those internal names. [docs/design-next-ui.md](docs/design-next-ui.md) owns
  the promotion decision and route grammar.
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
- Test the page by running it, not by matching strings against its source. `NextPageJsHarness` in
  `next_harness.py` executes the real dashboard script (the `web/next-*.js` parts, concatenated in
  `APP_PARTS` order) under node against a stub DOM. A test can fire a click or a keystroke and assert
  on what the page did. A source-text assertion passes forever after the behavior behind it breaks.
  Each check runs in a fresh `vm` context inside the shared worker described above, so it still gets
  a clean set of globals, but it is no longer a clean process: anything a check leaves on a timer
  outlives it. Isolate through the stubs rather than by assuming the interpreter restarts.
- Load the required default frontend before creating the daemon log, binding the socket, forking, or
  spawning a Windows child. Then acquire the log file and listening socket before forking (or, on Windows,
  before waiting on the re-spawned child). After the fork there is nowhere for a failure to go.
  Reporting one means pointing the user at the very log that could not be opened. Note that
  `os.makedirs(exist_ok=True)` is not this check: it succeeds for a directory that already exists
  whatever its mode, which is the likeliest bad state of all.
  There is no optional preview boundary: every canonical asset is required before bind.
- Never use `os.kill`, including `os.kill(pid, 0)` for liveness. CPython implements it on Windows
  through `TerminateProcess`, so a liveness check would kill the process it was asked to inspect.
  Probe `/api/health` instead.
- Stopping goes over HTTP, and a handler that stops the
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
2. Run the pre-PR suite in [AGENTS.md](AGENTS.md#pre-pr-checks), then invoke the `sync-docs` skill.
3. Open a PR against `main`. `main` is protected: PRs are required, the `validate`, `version-guard` and `quality-gate` checks must pass, history is linear (squash/rebase), all conversations must be resolved, and merged branches are deleted automatically.
4. If your PR closes an issue, use an explicit `Closes #NNN` line, one line per issue. A comma-separated list does not autoclose.

## Adding support for a new harness

This is the contribution we most want. Each harness is one registry entry: a key, a display label, a cheap discovery predicate, and a collector function. The runtime contract is `HarnessSpec` in `cargento_runtime/aggregate.py`, whose discovery takes `(config, state)` and whose collector takes `(config, state, now, window_hours, show_all)`. The registry itself is `aggregate.default_harnesses()`, and every row is a module under `cargento_runtime/collectors/`: add yours there, then add a row. Follow `collectors/codex.py` for the shape, and study `collectors/droid.py` (JSONL-based) or `collectors/goose.py` (SQLite-based) as templates. Requirements:

- Discovery must be cheap (an `isdir`, or one of the existence probes: `any_store_dir()`, `any_glob_under()`, `any_glob_stores()`). It answers one bit, so it must not build a match list it will not read, and `collect()` walks the same tree moments later anyway. The collector must degrade gracefully on schema drift.
- Resolve store roots through the candidate-set resolver rather than a single hardcoded path, and honor the harness's documented relocation variable if it has one.
- Document the data source and its caveats in `SKILL.md`'s data-sources list. The documentation-matches-code test asserts it.
- Add tests with a synthetic store fixture, including a hostile-path case.
- No frontend registry entry is needed. The page reads harness keys and labels from the payload's
  `harnesses` list, which is derived from `default_harnesses()`.
- Every row's field set is declared once, in `base_session` in `cargento_runtime/sessions.py`, at `None`. Populate the fields your store can answer and leave the rest; do not add a key that only your harness sets, because then every consumer has to test for presence instead of for a value. `provider` and `model` are there for the same reason and only Pi fills them today, since Pi is the one harness that spends another product's allowance rather than its own.

Before writing any of it, settle whether the thing deserves a row of its own: two store formats can be one harness, and one vendor can be two. [`docs/design-harness-registry.md`](docs/design-harness-registry.md) owns that judgement and the one time it had to be revisited.

### Adding a quota source

A harness row can also publish quota, through the optional `usage` provider on `HarnessSpec`. There are three shapes, and which one applies is a question about the vendor rather than a choice: read it from the harness's own store (Codex, Copilot), fetch it with the harness's own credential (Claude, Cursor), or receive it from a harness that pushes its quota to a user-configured command (Antigravity). A fetch also sets `usage_is_fetch`, which is what raises the disclosure banner, and adds a row to `FETCH_VENDORS` in `quota.py`.

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
