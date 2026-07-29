# Staged functional split design

Date: 2026-07-29

Status: approved in conversation; awaiting written-spec review

## Context

The shipped dashboard has outgrown its two main implementation files:

- `cargento/skills/cargento/server.py` contains 7,357 lines.
- `cargento/skills/cargento/tests/test_server.py` contains 9,942 lines.

The production file combines store resolution, file and database readers, transcript scanners,
session assembly, ten harness collectors, Spacedock cartography, notification state, the complete
web page, HTTP handling, daemon lifecycle, diagnostics, and command-line handling. The test file
contains 31 test classes and more than 250 patches or resets of `server.py` attributes.

This concentration slows navigation and review. It also makes a narrow change expensive for an
agent because understanding one collector often requires loading unrelated collectors, the web
page, and process control code into context.

The stdlib-only constraint does not require one Python file. Each plugin harness already ships the
whole skill directory. Cargento can use sibling Python modules and frontend assets while preserving
`server.py` as the command users execute.

## Decision

Split the dashboard through a sequence of behavior-preserving pull requests. Each pull request
must leave the repository releasable and must pass the full local and three-platform gate.

Preserve the documented executable and network contracts. Do not preserve the internal Python
symbols that happen to exist in `server.py` today. They are not a public API, and a permanent
re-export facade would preserve the coupling this work is meant to remove.

## Goals

- Give each runtime and test module one named responsibility.
- Keep runtime and test Python modules generally below 1,000 lines.
- Keep `server.py` as the stable executable path.
- Preserve every command, flag, exit code, route, response schema, security invariant, and browser
  behavior.
- Replace launcher-global patches with explicit runtime configuration and state.
- Prove that all required modules and assets survive plugin installation.
- Keep each extraction pull request small enough to distinguish moved code from changed code.

The 1,000-line target is a review threshold, not an automated limit. A coherent module may exceed
it when another split would create artificial boundaries.

## Non-goals

This work does not add or change:

- harnesses, session states, or collector algorithms;
- the page design or interaction model;
- HTTP routes or JSON schemas;
- command-line behavior;
- collector concurrency;
- cache limits, invalidation rules, or lock granularity;
- the read-only store policy;
- runtime dependencies;
- packaging through PyPI; or
- unrelated cleanup discovered during extraction.

Record unrelated defects or improvements for separate work. Do not hide behavior changes inside a
move.

## Shipped layout

```text
cargento/skills/cargento/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── server.py
├── notify_hook.py
├── cargento_runtime/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   ├── state.py
│   ├── io.py
│   ├── transcripts.py
│   ├── turns.py
│   ├── sessions.py
│   ├── notifications.py
│   ├── spacedock.py
│   ├── aggregate.py
│   ├── diagnostics.py
│   ├── lifecycle.py
│   ├── http_api.py
│   ├── collectors/
│   │   ├── __init__.py
│   │   ├── claude.py
│   │   ├── codex.py
│   │   ├── pi.py
│   │   ├── gemini.py
│   │   ├── antigravity.py
│   │   ├── copilot.py
│   │   ├── opencode.py
│   │   ├── cursor.py
│   │   ├── goose.py
│   │   └── droid.py
│   └── web/
│       ├── __init__.py
│       ├── index.html
│       ├── styles.css
│       ├── app.js
│       └── page.py
└── tests/
    ├── __init__.py
    ├── support.py
    ├── fixtures.py
    ├── page_harness.py
    ├── test_claude.py
    ├── test_codex.py
    ├── test_pi.py
    ├── test_gemini_antigravity.py
    ├── test_copilot.py
    ├── test_sqlite_collectors.py
    ├── test_droid.py
    ├── test_sessions.py
    ├── test_transcripts.py
    ├── test_spacedock.py
    ├── test_notifications.py
    ├── test_http_api.py
    ├── test_lifecycle.py
    ├── test_page.py
    ├── test_page_calm.py
    ├── test_config_diagnostics.py
    ├── test_contracts.py
    └── test_documentation.py
```

The final names may change when a move proves that two proposed modules form one inseparable
responsibility. Any such change must preserve the dependency rules below.

## Dependency direction

Runtime imports flow in one direction:

```text
config, state, io
        |
        v
transcripts, turns, sessions
        |
        v
collectors, spacedock, notifications
        |
        v
aggregate, diagnostics
        |
        v
http_api, lifecycle
        |
        v
cli
        |
        v
server.py
```

Lower layers must not import `server.py`, `cli`, HTTP handling, lifecycle control, or collectors.
Collectors may import shared lower layers but may not import one another. Cross-harness behavior
belongs in `sessions`, `aggregate`, or another shared lower-level module.

`cargento_runtime.__init__` remains empty. Importers name the module they need instead of depending
on a second facade.

## Runtime ownership

`cli.main()` constructs the runtime from three explicit objects:

### RuntimeConfig

`RuntimeConfig` owns immutable configuration for one process:

- resolved store roots and documented overrides;
- threshold and cache-limit values;
- platform facts;
- the selected host, port, and display settings; and
- the absolute `server.py` launcher path used for daemon respawning.

Tests create modified configurations instead of patching module constants.

### RuntimeState

`RuntimeState` owns mutable process state:

- cache dictionaries and their bounds;
- scanner offsets and partial-line state;
- cache and scanner locks;
- hook and notification state;
- popup suppression state;
- collection memoization; and
- server start time.

The first move preserves the present lock groupings and cache behavior. Finer locks or separate
state objects require later evidence and a separate design.

### Application

The application layer owns the collector registry and coordinates diagnostics, collection, HTTP
handling, and lifecycle operations. It receives `RuntimeConfig` and `RuntimeState`; it does not
read launcher globals.

Collectors use an explicit contract:

```python
def collect(
    config: RuntimeConfig,
    state: RuntimeState,
    now: float,
    window_hours: float,
    show_all: bool,
) -> list[dict[str, Any]]:
    ...
```

Discovery follows the same model. The exact callable type should live in `aggregate.py` or a small
shared type module if importing it would otherwise create a cycle.

## Data flow

The data request path remains:

```text
GET /api/data
  -> collection memo
  -> harness registry
  -> discovery predicate
  -> collector
  -> shared transcript and session functions
  -> existing response schema
```

Collection remains sequential. Concurrency would change timing, shared-state access, and failure
behavior.

Diagnostics consume the same configuration and registry as normal collection. No second path table
or harness list may exist.

## Error boundaries

The split preserves these failure rules:

- An absent store means that its harness is undiscovered.
- A malformed record removes only that record.
- A broken file removes only that file.
- A collector failure cannot suppress other harnesses.
- Missing `sqlite3` removes only SQLite-backed details.
- Live harness stores remain read-only.
- Future timestamps remain subject to the existing plausibility rules.
- Every cache remains bounded.

Extracted modules must not open stores, sockets, browsers, logs, or subprocesses at import time.
`cli.main()` performs runtime construction.

Frontend assets introduce a new packaging failure mode. The page loader reads UTF-8 assets relative
to its own package and assembles the served page before daemonization. A missing or unreadable asset
must produce a clear startup error while stderr is still available.

## Stable external contracts

The refactor preserves:

- `python3 <skill-dir>/server.py`;
- every current command-line flag, default, output, and exit code;
- daemon start, status, stop, and respawn behavior;
- `notify_hook.py`;
- binding to IPv4 loopback;
- `/`, `/api/data`, `/api/health`, `/api/notify`, and `/api/shutdown`;
- the complete JSON schema and session identity rules;
- frontend behavior and appearance;
- Python 3.11+ and stdlib-only execution; and
- every security constraint in `SECURITY.md` and `CONTRIBUTING.md`.

No compatibility promise applies to importing functions or constants from `server.py`.

## Frontend assets

Move the current HTML, CSS, and JavaScript without changing their contents. `page.py` reads the
three assets and assembles the document. The HTTP layer continues to serve one HTML response, so
the browser gains no new routes or loading order.

The existing Node harness executes the real `app.js`. The embedded asset linter reads the shipped
files directly and retains its JavaScript syntax, CSS structure, and DOM ID checks.

`app.js` may remain near 1,200 lines during this refactor. Splitting browser modules would require
new routes or a build step and falls outside this work.

## Test architecture

The test suite uses standard imports and one runtime identity. It does not dynamically load a new
copy of the application for each test module.

`tests/support.py` owns:

- the one path-based `server.py` loader needed before the runtime package exists;
- temporary environment and runtime builders;
- shared state reset assertions during the transition;
- server-thread helpers; and
- subprocess helpers for direct-launch and copied-plugin tests.

The transitional loader must register its module in `sys.modules`, and every split test must import
that same object from `support.py`. Once the runtime package exists, standard package imports and
fresh `RuntimeConfig` and `RuntimeState` instances replace the loader and global reset logic.

`tests/fixtures.py` owns store builders and shared harness contract fixtures.
`tests/page_harness.py` owns the Node DOM harness.

Tests split by behavior, not by the source file they happened to occupy. Each test module imports
the production module that owns the behavior. Aggregate contract tests continue to exercise all
harnesses through the public application boundary.

Replace every hard-coded `test_server` command with one canonical discovery command. The first test
split must prove the command works from the repository root on Python 3.11 and 3.12, including
native Windows:

```bash
python -m unittest discover -s cargento/skills/cargento/tests -t .
```

Update the command in `AGENTS.md`, CI, release validation, repository development skills, and
contributor documentation in the same pull request.

Add a Python 3.11 direct-launch smoke job if no required job exercises the supported runtime floor.
The existing three-platform suite may remain on Python 3.12.

## Behavioral checkpoints

### Checkpoint 1: characterize the installed contract

Add tests before moving code:

- launch `server.py` from an unrelated working directory;
- exercise help, diagnose, status, stop, and invalid-argument paths;
- exercise every HTTP route and pin response shapes;
- prove daemon respawn uses the stable launcher;
- copy only the plugin directory and run the launcher from that copy; and
- record the baseline test inventory and measured coverage.

Avoid broad golden files. Assert stable behavior and schemas, not volatile timestamps or generated
prose.

### Checkpoint 2: split tests

Move tests and helpers without changing production code. The new discovery command must collect
every existing test. Cross-test state checks must remain green under the new import order.

### Checkpoint 3: extract frontend assets

Create the `cargento_runtime` package shell and move the page source byte-for-byte into its `web`
subdirectory. Adapt the linter and Node harness, extend the copied-plugin smoke test to require all
assets, and assert that assembly produces the same response bytes as the former embedded `PAGE`.

### Checkpoint 4: introduce the runtime foundation

Create config and state ownership. Move pure I/O and session helpers first, then transcript and turn
scanners. Preserve algorithms, locks, cache bounds, and error handling.

### Checkpoint 5: extract collectors

Move collectors in dependency order:

1. Codex, Pi, Gemini, Copilot, and Droid;
2. OpenCode, Cursor, and Goose;
3. Antigravity;
4. Spacedock and Claude.

Each move keeps aggregate harness contracts and adds direct tests at the new module boundary.

### Checkpoint 6: extract application services

Move aggregation, notifications, diagnostics, HTTP handling, and lifecycle control. Reduce
`server.py` to the launcher only after the application already runs through the package.

### Checkpoint 7: harden packaging and reconcile documentation

Teach repository validation to enumerate required runtime files and assets. Run the launcher from a
copied plugin with no repository path on `sys.path`. Update architecture, compatibility,
contributor, test, release, and `sync-docs` references.

## Pull request rules

Each checkpoint is an independently mergeable pull request based on the latest `main`. Every pull
request must:

- move one responsibility or establish one prerequisite;
- include no feature work;
- preserve or increase meaningful test coverage;
- leave the coverage threshold unchanged;
- run the canonical local gate;
- pass Ubuntu, macOS, and Windows tests;
- pass the copied-plugin smoke test after that test exists; and
- run `sync-docs` when paths, commands, or shipped structure change.

Reviewers should treat a mixed relocation and behavior change as a blocking finding.

## Packaging validation

Current validation proves that the plugin and skill exist but does not enumerate Python modules or
frontend assets. Add a runtime manifest or validator-owned required-file list only after the final
layout is stable. The validator should reject:

- a missing launcher or hook;
- a missing runtime package initializer;
- a missing module named by the architecture;
- a missing frontend asset; and
- an import or startup that succeeds only because the repository root is on `sys.path`.

Native Claude and AGY validators remain useful but do not replace the copied-plugin smoke test.

## Completion criteria

The refactor is complete when:

- `server.py` contains only the stable launcher;
- production and test responsibilities match this design;
- runtime and test modules generally stay below 1,000 lines;
- frontend source lives in separate HTML, CSS, and JavaScript files;
- tests use explicit configuration and state rather than launcher-global patches;
- importing runtime modules has no operational side effects;
- direct launch works from an arbitrary directory and copied plugin;
- documented CLI, HTTP, security, and frontend behavior remains unchanged;
- the full test inventory runs through discovery on all supported platforms;
- measured coverage has no unexplained regression and the threshold remains unchanged;
- Ruff, formatting, strict mypy, embedded asset checks, repository validation, native plugin
  validation, and platform tests pass; and
- `sync-docs` reports no unresolved drift.

## Rejected alternatives

### One large package-first change

A single move would combine module identity changes, hundreds of patch updates, asset loading, CI
discovery, packaging validation, and daemon imports. A failure would be hard to locate, and review
would mix moved code with changed behavior.

### Split only tests and frontend assets

This would improve context size quickly but leave roughly 5,800 lines of unrelated Python behavior
in `server.py`. It postpones the main dependency problem.

### Permanent `server.py` re-export facade

Re-exporting every constant and function would keep tests coupled to the launcher. Patching an alias
would not necessarily patch the module that reads the value. The facade would become a second
mutable API and invite import cycles.

### Hard line-count enforcement

A numeric gate would reward artificial fragmentation and wrapper files. Responsibility and
dependency direction are the architectural checks; line count is a review signal.

## Rollback

Each checkpoint preserves behavior and data formats, so it can be reverted without migration.
Later checkpoints begin only after the previous pull request reaches `main`. If a checkpoint
reveals a behavioral defect, record the defect separately and decide whether the present behavior
or the documented contract is authoritative before continuing.
