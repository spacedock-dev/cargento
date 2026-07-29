# Staged functional split design

Date: 2026-07-29

Status: approved; adversarial review fixes applied

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
│   ├── records.py
│   ├── transcripts.py
│   ├── turns.py
│   ├── sessions.py
│   ├── claude_data.py
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
config, state, io, records
        |
        v
transcripts, turns, sessions, claude_data
        |
        v
spacedock, notifications
        |
        v
collectors
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

`records.py` owns record classification, turn-signal extraction, Gemini event expansion, and event
fingerprinting shared by transcript and turn analysis. This prevents a
`transcripts -> turns -> transcripts` cycle.

`claude_data.py` owns Claude transcript facts used outside collection, including session-prefix
classification. `notifications.py` and `spacedock.py` may import it. The Claude collector may import
all three. The HTTP layer calls notification operations and never imports the Claude collector.

The `"gemini"` registry entry remains one application collector. `collectors/gemini.py` owns both
Gemini CLI and Antigravity source readers and composes their rows behind the existing discovery,
error, and display boundary. They move in one pull request.

`cargento_runtime.__init__` remains empty. Importers name the module they need instead of depending
on a second facade.

## Canonical import identity

Every process imports the runtime as the top-level package `cargento_runtime`. Runtime modules use
package-relative imports. Repository code must not import it through the namespace-qualified name
`cargento.skills.cargento.cargento_runtime`, which would create a second set of classes, locks, and
caches.

Direct `server.py` execution already places the skill directory on `sys.path`. Repository tests,
the asset linter, and other path-based tools prepend the absolute skill directory before importing
`cargento_runtime`. Transitional test support loads `server.py` only after establishing the same
path.

Tests assert that no namespace-qualified runtime module appears in `sys.modules`. Copied-plugin
tests assert that every loaded `cargento_runtime` module resolves beneath the copied skill
directory.

## Runtime ownership

`cli.main()` constructs the runtime from three explicit objects:

### RuntimeConfig

`RuntimeConfig` owns immutable configuration for one process:

- resolved store roots and documented overrides;
- threshold and cache-limit values;
- platform facts;
- whether Spacedock project reads are enabled;
- the state directory resolved from `CARGENTO_HOME`;
- the selected host, port, and display settings; and
- the absolute `server.py` launcher path used for daemon respawning.

Tests create modified configurations instead of patching module constants.
An explicit per-store test or adapter override replaces that store's whole candidate list with the
selected path. Normal configuration retains every resolved candidate. This preserves the current
isolation rule that a fixture root cannot fall through to a real user store.

### RuntimeState

`RuntimeState` owns mutable process state:

- cache dictionaries, whose limits come from `RuntimeConfig`;
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

The registry uses one explicit contract:

```python
@dataclass(frozen=True)
class HarnessSpec:
    key: str
    label: str
    discover: Callable[[RuntimeConfig, RuntimeState], bool]
    collect: Collector


def collect(
    config: RuntimeConfig,
    state: RuntimeState,
    now: float,
    window_hours: float,
    show_all: bool,
) -> list[dict[str, Any]]: ...
```

`aggregate.py` owns `HarnessSpec`, catches discovery and collection errors at the current per-harness
boundaries, and records diagnostics through `RuntimeState`. Collector modules export callables but
do not mutate the registry. Discovery receives state because validating a Pi store reads the same
bounded first-line metadata cache as collection; it must not regain that cache through a hidden
module global.

`CargentoHTTPServer` stores exactly one `Application` and one assembled page. Request handlers read
them from their server instance rather than class or process globals. A contract test starts two
servers with different configurations and states and proves that requests and notification state
do not cross between them.

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
to its own package. Argument parsing and the `--help`, `--diagnose`, `--status`, and `--stop`
early-exit paths run before page construction. Foreground and daemon serving paths load the page
before binding, opening the daemon log, forking, or spawning a child. A missing or unreadable asset
must therefore produce a clear startup error while stderr is still available without disabling
recovery commands.

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

Fresh-interpreter tests are the deliberate exception. Optional-`sqlite3`, import-side-effect, and
copied-plugin checks run in isolated subprocesses so they can control `sys.modules` and imports
without contaminating the shared test process.

`tests/fixtures.py` owns store builders and shared harness contract fixtures.
`tests/page_harness.py` owns the Node DOM harness.

Tests split by behavior, not by the source file they happened to occupy. Each test module imports
the production module that owns the behavior. Aggregate contract tests continue to exercise all
harnesses through the public application boundary.

Replace every hard-coded `test_server` target with canonical dashboard discovery plus the existing
repository script modules. The coverage sequence is:

```bash
coverage erase
coverage run -m unittest discover -s cargento/skills/cargento/tests -t .
coverage run -a -m unittest \
  scripts.tests.test_validate_plugins \
  scripts.tests.test_bump_version \
  scripts.tests.test_lint_embedded
coverage report
```

The non-coverage sequence runs discovery first, then the same three script modules with a second
`python -m unittest` invocation. The first test split must prove both sequences work from the
repository root on Python 3.11 and 3.12, including native Windows.

Update `AGENTS.md`, both quality-gate invocations, `validate.yml`, `release.yml`, the `sync-docs`
skill, contributor documentation, the root architecture map, and validator comments in the same
pull request.

Add a Python 3.11 direct-launch smoke job if no required job exercises the supported runtime floor.
The existing three-platform suite may remain on Python 3.12.

When the runtime package first appears, add its directory to `[tool.mypy].files`. Transfer only the
Ruff per-file exemptions required by moved code to each new owner. Do not apply one wildcard
exemption to the whole package, broaden an ignore, or refactor branchy code merely to make a move
pass lint.

## Delivery phases and behavioral checkpoints

Each phase may contain several pull requests. A pull request moves one responsibility or establishes
one prerequisite. The implementation plan must name each pull request and its entry and exit
criteria.

### Phase 1: characterize the installed contract

Add tests before moving code:

- launch `server.py` from an unrelated working directory;
- exercise help, diagnose, status, stop, and invalid-argument paths;
- exercise every HTTP route and pin response shapes;
- preserve Host and Origin rejection, DNS-rebinding protection, request-size limits, and loopback
  binding;
- preserve the SessionEnd generation guard and notification ordering;
- prove `/api/health` performs no harness-store reads;
- prove collection memoization holds its lock across the scan and releases it after failure;
- prove daemon respawn uses the stable launcher;
- copy only the plugin directory and run the launcher from that copy;
- test the detached-process argument builder with a Windows launcher path;
- characterize current `main()` and detached-spawn argument forwarding in the parent coverage
  process, then replace that assertion with thin-launcher import/forwarding coverage when the
  launcher is reduced; and
- record the numeric test count, skipped count, test inventory, and measured CI coverage.

At the time of this design, the canonical suite runs 423 tests with one skip. If `main` changes
before the first implementation pull request, record the new baseline and the commit that produced
it. Test splitting must match that recorded count before adding new tests.

The copied-plugin subprocess runs from an unrelated temporary directory. Remove `PYTHONPATH`, set
`PYTHONNOUSERSITE=1`, invoke the absolute copied launcher, and assert that every loaded
`cargento_runtime` module and frontend asset resolves beneath the copied skill directory. This
path assertion catches a same-named runtime package installed elsewhere.

Avoid broad golden files. Assert stable behavior and schemas, not volatile timestamps or generated
prose.

### Phase 2: split tests

Move tests and helpers without changing production code. The new discovery command must collect
every existing test. Cross-test state checks must remain green under the new import order.

### Phase 3: extract frontend assets

Create the `cargento_runtime` package shell and move the page source byte-for-byte into its `web`
subdirectory. Adapt the linter and Node harness, extend the copied-plugin smoke test to require all
assets, and assert that assembly produces the same response bytes as the former embedded `PAGE`.

### Phase 4: introduce the runtime foundation

Use separate pull requests:

1. create `RuntimeConfig`, `RuntimeState`, the canonical import bootstrap, and temporary adapters
   while leaving behavior in `server.py`;
2. move pure I/O and record-classification helpers;
3. move shared session construction and identity helpers;
4. move transcript analysis; and
5. move turn scanning after shared record operations sit below both analyzers.

Preserve algorithms, locks, cache bounds, and error handling. A pull request must not both introduce
state ownership and relocate several functional subsystems.

### Phase 5: establish the application boundary and extract collectors

Move collectors through separate pull requests in dependency order:

1. introduce `HarnessSpec`, the registry, `Application`, and temporary adapters while collectors
   remain in `server.py`;
2. Codex;
3. Pi;
4. Copilot and Droid, separately unless their shared JSONL contract makes one small move clearer;
5. OpenCode, Cursor, and Goose, separately after shared SQLite helpers exist;
6. the composite Gemini and Antigravity collector in one pull request;
7. `claude_data.py`, then Spacedock and notifications through their defined lower-layer APIs; and
8. the Claude collector.

Each move keeps aggregate harness contracts and adds direct tests at the new module boundary.

### Phase 6: extract application services

Move diagnostics, HTTP handling, and lifecycle control in separate pull requests. Reduce
`server.py` to the launcher only after the application already runs through the package.

### Phase 7: harden packaging and reconcile documentation

Teach repository validation to enumerate required runtime files and assets. Run the launcher from a
copied plugin with no repository path on `sys.path`. Update architecture, compatibility,
contributor, test, release, and `sync-docs` references.

Fold the durable module boundaries, dependency rules, and rejected alternatives into the owning
`docs/design-*.md` file. Then delete this design and its implementation plan, because
`docs/plans/` contains only unshipped work. Run `sync-docs` after those deletions.

## Pull request rules

Every pull request is independently mergeable and based on the latest `main`. Every pull request
must:

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

Each pull request preserves behavior and data formats, so it can be reverted without migration.
Later pull requests begin only after the previous one reaches `main`. If a phase reveals a
behavioral defect, record the defect separately and decide whether the present behavior or the
documented contract is authoritative before continuing.
