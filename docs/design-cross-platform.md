# Design: cross-platform store discovery, diagnostics, and notifications

The durable rationale behind how Cargento finds harness stores, reports what it found, and decides
who delivers a notification. It records the decisions and the alternatives that were tried and
rejected. The rejected ones are the expensive part, because without them they get re-attempted.

Behavioral detail lives in [`COMPATIBILITY.md`](../COMPATIBILITY.md) (the per-OS matrix) and in the
skill body (the user-facing contract). This file explains *why*, not *what*. Remaining unshipped
work is in [`plans/native-notifications.md`](plans/native-notifications.md).

Store resolution and every tunable limit are frozen in `cargento_runtime/config.py`; bounded reads,
safe globbing and read-only SQLite are `cargento_runtime/io.py`; the report is
`cargento_runtime/diagnostics.py`. How those pieces fit together, and why configuration is frozen
while state is separate, is owned by
[`design-runtime-architecture.md`](design-runtime-architecture.md).

Each decision keeps a stable `D-N` anchor, and code comments cite them by name. Grep the identifier
across `*.py`, `*.toml` and `*.md` before renumbering anything. These numbers carry over from the
cross-platform plan this file replaced; D-1 through D-6 mean what they meant there.

---

## The problem these decisions answer

Every collector swallows its own errors by design: a broken or absent harness store is skipped,
never fatal. That is correct robustness, and it means a wrong path, an unreadable database, or an
unescaped glob produces zero sessions and no complaint. The failure mode almost everything below is
shaped around is silent false-negative discovery, where a clean-looking dashboard simply omits the
user's sessions.

## D-1: Scan every viable root, never pick one

Each harness has an ordered *candidate set* of store roots (`resolve_store_roots` in
`cargento_runtime/config.py`), and every candidate that exists is scanned on every collection pass.
Results are de-duplicated by `(harness, session id)`, keeping the freshest copy.

Rejected: selecting the first matching candidate at import. It regresses real users three ways. A
store created after launch stays invisible until restart, an empty native directory shadows
populated legacy data, and a user mid-migration loses whichever copy sorts second. The
de-duplication step is not optional under this decision: without it, a migration that left a session
in two roots emits it twice.

An explicit environment override is *authoritative*. If it is set but missing or unreadable, say so
loudly rather than falling through to a default that happens to work. Some harnesses need more than
one unrelated root (Claude needs `projects/` and `tasks/`; Gemini needs the Gemini CLI tree and the
Antigravity CLI tree), so the unit is a per-harness root set, not a single root. Pi makes the same
case in a different shape: its default store is nested below its configuration root, while a custom
session directory is flat. `PI_CODING_AGENT_SESSION_DIR` therefore wins over the configuration-root
override, global setting, and default. The global `sessionDir` setting is readable, but a separate
process cannot discover a per-invocation CLI directory or project-local settings file. Those users
must expose the effective directory through the session-store override.

## D-2: `--diagnose` is a first-class deliverable, not a debug flag

`--diagnose [--json]` prints the platform, the interpreter, every candidate root considered, which
existed, which were readable, and every collector error the refresh path swallowed. It is the only
realistic way to validate a platform's path table without owning an install of all ten harnesses,
and it is what turns "no sessions" into an answer.

Two standing constraints:

- No outbound telemetry, ever. The command reads local paths and prints them. Users choose to share
  the output. Because it prints absolute paths and the *values* of the store environment variables,
  `SECURITY.md` tells users to redact before pasting it into an issue.
- Diagnostic verbosity stays out of `/api/data`, which is fetched every five seconds.

## D-3: Exactly one owner per notification path

- The browser Notification API owns transcript-detected transitions. That path already requires an
  open dashboard tab, so nothing is lost by putting delivery there.
- Native OS backends own hook POSTs to `/api/notify`, which must work with no tab open.
- A question registered on `/api/ask` follows the same split, and is keyed on the ask id rather than
  on a transition: it has no prior state, and it leaves the payload for good once answered, withdrawn
  or expired. Two differences from the session path are deliberate. No dismissal is consulted, because
  the card is published regardless, and suppressing the alert would leave the reader an alert and a board
  that disagree. And the ask lane reads and writes its own cooldown key, never the gate lane's shared
  `_global` floor, so neither alert can swallow the other. That asymmetry is load-bearing in both
  directions: a gate re-emits for as long as it stands, while nothing ever re-registers a question and
  the sweep deletes it unanswered at `ask_deadline_sec`; and `maybe_popup` records the transition
  *above* its cooldown gates, so a gate suppressed by a shared floor is not delayed by 15s, it is gone
  for the whole block.

`/api/data` publishes `native_notify`, which is the name of the server's OS backend, or empty. The
page raises its own notification only when that field is empty. Double-firing is impossible by
construction rather than by deduplication logic, which matters because `maybe_popup` runs *during*
the very collection the page is about to render from.

The layer split is decided by `application.native_notifier(config.platform_name)`, the same
expression `/api/data` publishes as `native_notify`, so the server's decision and the page's reading of
it are one value by construction (see D-4). `notify_mac`'s own platform guard is defence in depth, not
a second decision point: a stub notifier injected in a test makes the two disagree, which is why the
ask path gates at the call site.

Corollary for future work: a `--notify` switch must state which owner it disables.

## D-4: Platform and clock decisions take their environment as an argument

Every decision that depends on the platform or on the current time is a pure function that receives
that context explicitly rather than reading global state, and the caller passes it in:
`resolve_store_roots(..., platform_name=...)` and `native_notifier(platform_name)` take a
`sys.platform` string, `reuse_address_allowed(os_name)` takes `os.name`, `sqlite_ro_uri(...,
windows=...)` takes an explicit flag, `encoded_home_prefix(home)` takes the home path, and
`age` / `is_fresh` / `newest_plausible` take `now`.

`build_runtime_config` applies the same rule at the process boundary. It receives the environment,
platform, launcher path, and selected store roots, then freezes the derived paths and limits in
`RuntimeConfig`. Mutable caches and locks belong to a separate `RuntimeState`, whose builder
receives the server start time. Importing either runtime module therefore does not sample the
ambient environment, clock, or filesystem.

Helpers that have moved into the runtime package take their context from that frozen configuration
rather than from per-call keywords. `project_from_cwd(config, cwd)` reads `config.os_name` and
`config.home`, and `age`, `is_fresh` and `newest_plausible` read
`config.future_skew_tolerance_sec`, so a cross-platform test builds a config for the target
platform instead of passing hidden `home=` and `windows=` overrides. Either shape satisfies D-4;
prefer the config field once the value is already frozen in `RuntimeConfig`, because an optional
override is a second source of truth for the same fact.

The payoff is testing: the Linux CI runner executes the Windows and macOS branches directly, with no
`sys.platform` mocking and no frozen clock, so a platform branch is never dead code on the runner
that gates the merge. Write new platform-dependent code this way by default.

*Status note:* the `platform = "darwin"` pin in `[tool.mypy]` predates this decision. `notify_mac`'s
guard now goes through `native_notifier(config.platform_name)`, which mypy does not narrow, so the pin's
stated justification no longer holds and `mypy --platform linux` passes clean. It is left in place
pending a deliberate decision; see [`plans/native-notifications.md`](plans/native-notifications.md).

## D-5: `notify_mac` stays a thin, named alias

The macOS notification entry point keeps the name `notify_mac`, even though it is now selected
through `native_notifier`. The test suite patches it by name in about twenty places. Renaming it to
something more general without leaving a compatibility alias churns the suite for no behavioral
gain, and a churned suite is where regressions hide.

## D-6: Never guess an override or a path

A store path or relocation variable is only shipped when it is confirmed from official documentation
or upstream source. Everything else is documented as "override required" rather than guessed at.

The asymmetry is the whole argument. A wrong default silently breaks a setup that works today, while
a missing one costs the user one line of `--diagnose` output and an environment variable. This is
why `GOOSE_PATH_ROOT` is not implemented, since its upstream semantics are undocumented, and why
reshaping state detection on an unverified platform premise is deferred rather than attempted.

## D-7: Pi follows persisted branches, never inferred relationships

Pi records a session as a tree. The current conversation is the ancestor path of its most recently
persisted leaf, not every record in the JSONL file. The scanner keeps only that active persisted
branch for prompts, tools, output usage, and turns. Navigation that has not appended a record is not
observable, so the dashboard deliberately reports the last persisted branch instead of guessing.
The most recent global `session_info` name still wins as the session title, including a later clear.

Pi's `parentSession` identifies a fork or clone, not a core subagent. Each file remains an
independent row. Treating it as a parent-child relationship would hide a valid session and attach
activity to the wrong row.

Rejected: parsing Pi as a linear JSONL transcript. A sibling branch can contain a newer-looking
prompt, tool, or token total that Pi has abandoned. Also rejected: invoking Pi to discover its live
selector. That would add a runtime dependency, execute user-installed extension code, and turn an
absent Pi installation into an error instead of an undiscovered harness.

## Rejected alternatives worth keeping rejected

These have no other home. Each one looks obviously correct until you read the reason.

- Binding both loopback addresses. Accepting `::1` alongside `127.0.0.1` needs two listeners and two
  threads, with ambiguous behavior when one binds and the other does not. Rejected; instead the
  banner and every document say `127.0.0.1`, which removes the `localhost` to `::1` ambiguity
  outright. (`LOCAL_HOSTS` still *accepts* `::1` in the Host header next to an IPv4-only bind, which
  is what makes this look like an oversight. It is not.)
- A generic "split on both path separators" helper. On native Windows `os.path` *is* `ntpath` and
  already understands both separators; on POSIX, `\` is a legal filename character, so such a helper
  would actively corrupt valid POSIX paths. Rejected as a regression, not deferred.
- Generalizing SQLite `immutable=1`. It makes an unreadable store readable, and on a database that
  is in fact changing, which every live agent store is, it can return incorrect results or
  `SQLITE_CORRUPT`. The Antigravity metadata reader makes one narrow exception for the cleanly
  closed WAL-mode stores AGY leaves behind: it tries `mode=ro` first and falls back only while the
  WAL is absent or empty, then rejects the fallback result if WAL data appears. A zero-byte WAL is
  not activity. Everywhere else, diagnose why `mode=ro` failed and report it; do not silently
  downgrade.
- `mmap` for reverse transcript scans. Truncation by the writing harness while a region is mapped is
  an uncatchable `SIGBUS` on POSIX, so this was a latent macOS and Linux bug rather than Windows
  hardening. Replaced everywhere by bounded chunked reverse reads. Chunk size is irrelevant anywhere
  between 64 KiB and 4 MiB; the per-line scan dominates, not the I/O.
- Clamping future timestamps to zero. Zero age reads as "just now", which is still fresh, so the
  clamp would have been a no-op against the bug it was meant to fix. An implausibly future timestamp
  must be *rejected* so no activity is invented from it, with only a small tolerance band clamped
  (sampling noise between `stat()` and the collection clock, and coarse filesystem write times).
- An in-request retry ladder for transient store-read failures. The dashboard already re-reads every
  store every five seconds, so a retry loop would duplicate the refresh cycle while blocking the
  response thread. A transient antivirus or file-sync lock self-heals on the next poll, and
  `--diagnose` explains it if it does not. The *reporting* half did ship, and is the valuable half:
  distinguishing "no store here" from "store present but unreadable".
- `normcase` on the `commonpath` containment check. It looks missing next to the deliberate
  `ntpath.normcase` in the root resolver, and it is not: `ntpath.commonpath` already case-folds for
  comparison and returns the prefix in the first argument's casing, so
  `commonpath((root, path)) == root` holds under case differences. Verified locally and confirmed
  independently. Adding `normcase` would change what the comparison returns, not what it decides.
- `urllib.request.pathname2url` in the SQLite URI builder. It is the obvious stdlib primitive and it
  is wrong here: on POSIX a path with a leading `//` becomes a URI *authority*, and on Windows a UNC
  path becomes `file://server/share/...`, which SQLite rejects outright, because the authority must
  be empty or `localhost`. The hand-rolled quoting is deliberate.
- `sys.stdout.reconfigure()` in the diagnostic writer. Tempting as a one-line replacement for the
  guarded retry, and unsafe: it fails when stdout has been replaced, which is exactly the
  redirected-output case the writer exists for, and it changes macOS and Linux behavior too.
- Reading `os.environ["HOME"]` instead of `os.path.expanduser("~")`. Native CPython's
  `ntpath.expanduser` deliberately ignores `HOME` and uses `USERPROFILE`; only an MSYS-built
  interpreter behaves POSIX-ly. Since Git Bash is a documented invocation shell, "fix" this and
  every native-Windows Git Bash user's store root moves, which is the silent-false-negative failure
  this whole design is shaped around.
- Adding `GEMINI_DATA_DIR` to the resolver. It is a third-party tool's variable, not Gemini CLI's,
  and it is documented well enough elsewhere to look legitimate. The real one is `GEMINI_CLI_HOME`,
  which names a *parent*, so `.gemini` is appended rather than substituted.

## Testing strategy

Three layers, in increasing cost:

1. Pure-function tests, run everywhere. Because of D-4 every platform decision is callable with an
   arbitrary platform string, so one runner covers all three.
2. Behavioural contracts, run natively on each runner. A realistic fixture per store, asserted to:
   discover when present; read working when fresh and idle when stale; stay undiscovered *without an
   error* when absent; refuse to read working from a future-dated store; survive a corrupt store
   without taking the other harnesses down; and collapse to one row when the same session exists in
   two candidate roots. Every store is additionally built under hostile path components legal on all
   three platforms: glob metacharacters, `%`, non-ASCII, spaces, `#`, quotes.
3. Documentation-matches-code. The documented store paths, relocation variables, Python floor and
   loopback address are asserted against the implementation, so doc drift is a test failure rather
   than a review catch. It found real drift twice before it existed.

Mutation-check a new contract before trusting it. Break the behaviour deliberately and confirm the
targeted test fails. Doing this the first time exposed two assertions that could not fail:
de-duplication was tested as a function but never as wired into `collect()`, and one discovery
assertion was vacuous.

Honest gap: nothing validates the *Windows store locations* against a real Windows install. That
needs the ten harnesses actually installed there. The resolver's Windows output is asserted as
strings; whether those strings are where the tools really write is what a user's `--diagnose` output
settles.
