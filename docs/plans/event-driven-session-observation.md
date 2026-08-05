# Plan: event-driven session observation

Status: Phase 0 has shipped; Phases 1 through 4 are unshipped and still provisional. The Phase 0
collector fixes, the two quota opt-out repairs and the benchmark have landed with tests, and its four
gates now carry verdicts: one measured and failed, three unreached. Everything below the Phase 0
section remains a problem statement and an option survey. Delete this file once its contents ship or
are dropped, folding the durable rationale (the ACP, filesystem-watcher and OpenTelemetry findings)
into a `docs/design-*.md` owner.

Which runtime file owns what, and the inward-only dependency rule any new module must respect, is
owned by [`design-runtime-architecture.md`](../design-runtime-architecture.md). The per-harness
store formats are owned by the shipped [`SKILL.md`](../../cargento/skills/cargento/SKILL.md). This
file records the August 2026 investigation into replacing request-driven session polling with
lower-latency collection.

## Recommendation

Cargento should keep its Python runtime and existing collectors, but stop making a browser refresh
the scheduler for all collection work.

**Phase 0 has run its measurement, collector and quota-repair tasks, and the recommendation below is
subordinate to the verdicts it produced.** One of the four gates was reached and it failed; the other
three were never reached. All of them are recorded under
[Phase 0](#phase-0-measure-repair-prerequisites-and-fix-the-collector).

The figures below come from **one machine only**: darwin/arm64 (macOS 26.5.2, Apple silicon), CPython
3.12.13, 6 of 10 harnesses discovered, 16 sessions in the default 24-hour window, and 3,632 Claude
transcript files under `~/.claude/projects`. Nothing here has been reproduced on Linux or Windows.
Both columns were measured on the same machine and the same day with `scripts/bench_collect.py`: the
after column at the branch tip, the before column at the pre-fix commit checked out in a detached
worktree of the same repository, against the same store.

| Measurement | Before the Phase 0 collector fixes | After |
|---|---|---|
| Warm `Application.collect`, median of 7 | 283 ms | 118 to 120 ms |
| Of which the Claude collector | 263 ms, 93% | 98 to 101 ms, 83% |
| First collect in a fresh process, caches empty | 392 to 399 ms | 275 to 297 ms |
| The five other discovered harnesses combined | 7.3 ms | 7.5 ms |
| All ten discovery predicates combined | 0.34 ms | 0.33 ms |
| `glob_under` calls in one cold collect | 11,850 | 1,646 |
| Coarse `os.stat` probe over 97 store paths | 0.14 ms | not re-measured |
| Forwarder process cost, server absent, macOS | 56 ms median | not re-measured; p95 and p99 never measured |
| Files or bytes consulted | not measured | not measured, no counter exists |

Run-to-run variance is worth about 15% of the total on this machine: an earlier same-commit baseline
recorded 322 ms warm against the 283 ms above, on the same store hours apart. Read the columns as a
ratio, not as absolute constants.

Two conclusions survive the fixes. First, the cost argument for an event architecture is gone: a 120
ms warm collect at the current five-second cadence is a 2.4% duty cycle, and latency plus
needs-input semantics are the only remaining justification for anything below. Second, per-harness
dirty invalidation still saves little. Claude is 83% of the post-fix collection and is also the
harness that generates the most events, so it will be dirty in nearly every coalescing window; the
[selective-reuse gate](#phase-0-measure-repair-prerequisites-and-fix-the-collector) measures that
saving at 16% and fails it.

The design that survives those numbers is an event-triggered, materialized dashboard snapshot:

1. Harness-native lifecycle hooks, status-line callbacks, native event streams, a coarse store
   probe, and optional Cargento-managed ACP connections report that something changed.
2. An authenticated, bounded loopback ingress normalizes the signal and marks one session or harness
   dirty.
3. The existing defensive collector for that harness reconstructs authoritative state from its
   store when the event does not contain enough trustworthy state on its own.
4. Cargento merges the result into a versioned in-memory snapshot.
5. The server pushes a revision notification to dashboard tabs with Server-Sent Events (SSE).
6. A full reconstruction on first demand and periodic reconciliation retain correctness when an
   event is missed or an integration is unavailable.

In short:

> Events tell Cargento **when** to look. Collectors determine **what** the authoritative state is.

That invariant is the one thing in this document that should survive any cut. Where it and a
latency goal conflict, it wins, with the narrow per-field exceptions written out under
[Event overlays versus store truth](#event-overlays-versus-store-truth).

ACP is useful for sessions Cargento launches, owns, or transparently proxies. It is not a suitable
replacement for passive discovery of arbitrary agent sessions already running under other clients.

## The current collection path

The browser calls `/api/data` every five seconds in `cargento_runtime/web/main.js`. A cold request
enters `Application.collect` in `cargento_runtime/aggregate.py`, iterates the harness registry, runs
discovery for each harness, invokes every discovered collector, and serializes the complete
aggregate response.

`Application.collect_json` memoizes the serialized result for 2.5 seconds and holds its lock through
collection. That prevents concurrent browser tabs from stampeding the stores on the same cold cache
entry, but it does not make collection incremental at the application level. Once the memo expires,
the next request repeats discovery and invokes every discovered harness collector.

Individual collectors use bounded reads, mtime and size checks, metadata caches, incremental turn
scanners and defensive SQLite access, behind a per-harness failure boundary that `Application.collect`
owns rather than the collectors themselves. The costs are architectural rather than a property of the
language:

- Browser demand schedules collection work.
- A change in one harness invalidates nothing specifically, so the next cold request consults all
  discovered harnesses. On the profile above this is worth about 7 ms, so it is the weakest of these
  costs, not the strongest.
- The page learns about a change zero to five seconds after it occurs, and up to about 7.5 seconds in
  the worst case, because the five-second poll composes with up to 2.5 seconds of memo staleness.
- Multiple tabs still generate repeated HTTP requests, even when the memo makes some of them cheap.
- Long-running turns can look idle when a harness only updates its store at message boundaries.
- Exact semantic state such as waiting for approval is often reduced to an mtime freshness guess.

The supported sources remain intentionally heterogeneous. Those stores are valuable because they
provide historical reconstruction and a fallback that does not depend on an agent still running.

### State is partly time-derived

Cargento treats activity within `working_threshold_sec` as Working. A session can therefore become
Idle without another file write or lifecycle event. Moving to events does not remove the need for
clocks: the server must schedule state invalidations for deadlines such as:

- `last_activity + working_threshold_sec`;
- history-window expiry;
- expiry of Working and other transient overlays, so a missed stop cannot pin false activity;
- the vendor quota poll floor and allowance reset times.

Needs-input state is deliberately *not* cleared merely because a wall-clock TTL elapsed. A real
permission or input wait can last for hours, so a time-only deadline would replace a possible stale
positive with a more dangerous false negative. An `input_requested` overlay retires on a positive
`input_resolved`, resumed user/agent activity, `session_ended`, collector evidence allowed by that
harness's precedence rule, or removal of the collector-owned row. A liveness lease may mark its event
source stale, but does not silently clear the alert.

Existing hook state follows the same principle. `notifications.current_hook` clears a standing hook
when the newest user record in the transcript changes, and its docstring calls that clock-independent;
the only fallback compares against a newly parsed transcript timestamp, not a timer, and no hook TTL
field exists in `config`. Scheduling an arbitrary expiry would invent behavior the mechanism does not
have. Working overlays and source-health leases do need deadlines; Needs-input overlays need positive
retirement evidence.

An event-driven system is not timer-free. It avoids asking every source the same question at a fixed
cadence when nothing has changed.

### Existing push paths

Cargento already has two partial push integrations:

- Claude `Notification` and `SessionEnd` hooks can forward JSON to `POST /api/notify` through
  `notify_hook.py`. The resulting hook state augments Claude session state and can drive native
  notifications even when no dashboard tab is open.
- Antigravity invokes its configured `statusLine` command on agent-state changes. That payload reaches
  `POST /api/usage` and Cargento retains the shaped quota receipt in memory.

One script serves both. The shipped skill configures Antigravity's `statusLine` as
`notify_hook.py <url>/api/usage` and states that it is the same forwarder the Claude hooks use with a
different URL. It is payload-agnostic, forwarding raw stdin bytes to whichever URL it is given. That
coupling is easy to miss and constrains anything done to the forwarder later.

Both paths reach Cargento only for a user who has edited the harness's own configuration by hand. They
prove that loopback event ingestion fits the product; they are not evidence that the mechanism is
installed anywhere. Today they update side state; they do not maintain the session-board snapshot or
trigger browser delivery.

## Cheaper options that must be tried first

### Make collection cheaper

The cheapest option is not an acquisition strategy at all: fix the dominant collector and keep
request-driven polling. `claude.collect` issues roughly 11,800 `glob` calls per collection across
about 3,000 historical session prefixes to produce 8 rows, because the freshness filter
(`if not (active or show_all)`) runs *after* the per-prefix subagent scan, and because
`agent_transcripts` is called once directly and once again inside `load_subagents` for every prefix.

**This shipped in Phase 0.** Three behavior-preserving fixes landed: an `os.path.isdir` guard before
globbing, calling `agent_transcripts` once per prefix instead of twice, and a bounded `RuntimeState`
cache of subagent listings. Together they took the warm Claude collector from 263 ms to about 100 ms
and one cold collect from 11,850 `glob` calls to 1,646, with the whole test suite unchanged.

The cache did not land the way the prototype described it, because the prototype was not
behavior-preserving. Keying on the session directory's mtime alone misses two writes: appending to an
existing child transcript changes no directory mtime, and creating a child below
`subagents/workflows/<run>/` need not change the session directory. Either one loses the parked-parent
case the code comments exist to preserve. What shipped caches membership only; fingerprints every
directory a glob pattern can reach, including each existing workflow run directory, so a run watched
before it holds anything still notices its first agent; takes that fingerprint **before** the listing,
so a write racing the scan invalidates the entry instead of pinning a listing that missed it; and
restats every cached child transcript on every call, so a running subagent is never frozen at the
mtime it was first seen at. That conservatism is why the result is near 100 ms rather than the 41 ms
the mtime-only prototype reported. The parked-parent and nested-workflow cases have regression tests.

Doing this first was worth it regardless of what follows. A 120 ms collect at the current five-second
cadence is a 2.4% duty cycle, which removes cost from the argument entirely and leaves latency and
needs-input semantics as the only remaining justification for anything below. An event architecture
layered over an O(all-history) collector inherits the same cost on every dirty refresh.

### A coarse store probe

A prototype `os.stat` sweep over store roots, per-project directories, and known in-window
transcripts cost 0.14 ms for 97 paths on one warm macOS profile. At 1 Hz that would be a 0.014% duty
cycle on that profile, roughly 400 times cheaper than today's poll. It is pure stdlib, needs no user
configuration, no envelope, no versioning and no uninstall path. It is not yet proven to cover every
input read by all ten collectors.

The probe needs a reviewed dependency and fingerprint table per harness before it can become a
correctness-relevant trigger. Its target set includes known JSONL, task and subagent files; every
directory used to discover new or removed targets; and SQLite database, WAL and SHM sidecars. A
fingerprint uses only change-bearing fields such as existence, `mtime_ns`, size and, where portable,
inode or file ID, plus the owning directory; atime is excluded. Reconciliation refreshes the target
set. Mutation fixtures must cover append-in-place, same-size rewrite, atomic replacement, create,
delete, nested-file creation, WAL append and checkpoint, coarse timestamp resolution, suspend/resume,
and target-set changes on all three supported operating systems. Bind mounts, WSL/9p, remote and
network stores remain best-effort unless measured separately.

It cannot distinguish "waiting for approval" from "bytes changed". That distinction is the case for
hooks, and it is a narrower case than "hooks are the primary trigger". Until the probe passes its
independent false-negative and performance gate, the current five-second scan remains the fallback;
the 0.14 ms experiment is a hypothesis, not grounds to reduce polling.

## ACP findings

### What ACP is designed to do

The [ACP introduction](https://agentclientprotocol.com/get-started/introduction) describes a standard
interface between an agent and a client such as an editor or IDE. In the standard local topology,
the client launches the agent as a subprocess and exchanges newline-delimited JSON-RPC over stdin
and stdout. A connection may host several sessions, and the protocol makes extensive use of
notifications for real-time UI updates. See the
[architecture](https://agentclientprotocol.com/get-started/architecture) and
[transport specification](https://agentclientprotocol.com/protocol/v1/transports).

For a session carried on that connection, ACP's live data model covers:

- prompt-turn start and completion;
- streamed agent messages;
- tool calls and status changes;
- agent plans;
- permission requests;
- context usage and optional cost;
- cancellation;
- session metadata updates.

The [prompt-turn specification](https://agentclientprotocol.com/protocol/v1/prompt-turn) states turn
boundaries directly, where a transcript mtime only supports a guess.

### What ACP does not standardize

ACP does not define a machine-wide observer connection for all independently running agents.

Its optional [`session/list`](https://agentclientprotocol.com/protocol/v1/session-list) method is a
history-discovery mechanism. Standard `SessionInfo` contains a session identifier, working
directory, and optional `additionalDirectories`, `title`, `updatedAt` and `_meta`. Only `sessionId` and
`cwd` are required, so a collector cannot rely on a title or an update time being present, and `_meta`
is ACP's generic extension slot rather than a defined agent-metadata field. The method is gated on the
`sessionCapabilities.list` capability. `session_info_update` can keep title, update time and `_meta`
current without polling, and it is delivered over `session/update`, so it inherits exactly the scoping
described next.
The standard does not give listed sessions a normalized Working, Idle, waiting-for-approval, tool
progress, or externally-running status.

No ACP page states in so many words that `session/update` is connection-scoped; that is an inference
from the stdio-subprocess topology, in which the stream belongs to the connection on which the client
set up, loaded, resumed, or prompted the session. The direct evidence for the claim that matters is
negative and stronger: the v1 method index contains no `session/subscribe`, `session/observe` or
`session/watch`. A normal terminal session, a session in an editor, and a Cargento process are
normally different processes and different connections. An implementation may expose a shared daemon
or custom transport, but ACP does not require it. Remote transports are moving: the introduction calls
ACP suitable for remote scenarios over HTTP or WebSocket with full support still in progress, and
Streamable HTTP is a draft proposal, so a future shared-HTTP topology could soften this conclusion.

Consequently, launching an ACP subprocess merely to call `session/list` would not replace the current
passive collectors. It would still query for history, would not guarantee live state, and could be
more expensive than reading the already-local store.

### Nominal coverage is not passive observability

The current [ACP agent directory](https://agentclientprotocol.com/get-started/agents) lists nine of
Cargento's ten harnesses:

- Claude Agent, through an adapter;
- Codex CLI, through an adapter;
- Cursor;
- Factory Droid;
- Gemini CLI;
- GitHub Copilot, currently preview;
- Goose;
- OpenCode;
- Pi, through an adapter.

Antigravity is not listed. More importantly, the implementations do not have one maturity level or
one deployment topology. Being able to launch a harness as an ACP agent does not mean a second ACP
client can subscribe to sessions that another terminal or editor already owns.

### Where ACP does fit Cargento

ACP fits an optional managed-session lane:

- Cargento launches an ACP agent and becomes its client.
- The dashboard gains prompts, permission UI, cancellation, plans, and tool progress for sessions it
  owns.
- An editor is configured to launch a Cargento proxy, which forwards ACP traffic bidirectionally
  while copying lifecycle notifications into the dashboard.
- Cargento connects to a harness daemon that explicitly supports multiple clients and live
  subscription semantics.

Every form changes the product boundary. A direct ACP client must answer or relay permission
requests, survive as part of the session's critical path, and potentially gain write or control
access. A proxy can preserve the existing editor's permission experience but still becomes a point
of failure. These modes should be explicit and optional rather than prerequisites for passive
cartography.

Codex illustrates the distinction. Its official
[app-server protocol](https://learn.chatgpt.com/docs/app-server) exposes authentication,
conversation history, approvals, streamed `turn/*` and `item/*` events, loaded-thread discovery, and
`thread/status/changed`, including `waitingOnApproval`. Those explicit loaded-thread states make it
the provisional first managed Codex topology, subject to an adapter fixture comparison rather than
an assumed superiority over ACP. It only provides exact runtime status for threads loaded in that
app-server; ordinary standalone CLI sessions do not silently join a separate Cargento server.

## Alternative acquisition strategies

| Approach | Sees independently launched sessions? | Semantic precision | Main cost | Feasibility | Recommendation |
|---|---|---|---|---|---|
| Fix the dominant collector | Yes | Whatever stores persist | One collector's algorithm | Done in Phase 0 | **Done first, unconditionally** |
| Coarse periodic `stat` probe | Intended to, pending mutation tests | Low: says bytes changed, not what the agent is doing | 0.14 ms for one warm 97-path Mac profile; cross-platform cost unmeasured | Medium, gate unreached | Primary latency candidate only after its independent gate |
| Harness-native hooks, extensions, and status lines | Yes, when installed at user or plugin scope | High for lifecycle and input waits | Per-harness adapters, user trust, an indefinite support tail | Medium | Semantic supplement, needs-input first |
| ACP | Not guaranteed; normally only sessions on Cargento's connection | Very high for owned sessions | Changes Cargento into a client, launcher, or proxy | Technically feasible | Optional managed mode |
| Native harness server or event API | Only sessions connected to that server | Very high | Agent-specific topology and lifecycle | Medium | Use opportunistically; prefer where already running |
| Native filesystem-event watcher | Yes | Low | Three platform backends or a dependency | Poor fit | For precision the product does not need |
| OpenTelemetry | Yes for opted-in processes | Strong telemetry, uneven interactive state | Configuration, decoding, and partial harness coverage | Low | Optional observability lane |
| Fixed polling | Yes | Whatever stores persist | Repeated work and latency | High | Correctness fallback only |

### Filesystem notifications

Watching session stores reduces blind polling without requiring harness configuration, but it is not
sufficient as the source of truth:

- JSONL is often appended in place, so watching only directory mtimes misses changes.
- SQLite may write a database, WAL, shared-memory file, temporary file, or replacement file.
- Watchers coalesce events, can overflow, and differ in rename and delete semantics.
- A filesystem event has no standard meaning for Working, Idle, permission requested, turn ended, or
  subagent started.
- Linux inotify, macOS FSEvents, and Windows directory-change APIs require separate implementations.

The last two objections are objections to a *native* watcher, not to a cheap one. Cargento's runtime
has a deliberate stdlib-only, no-dependencies contract; the Python floor is owned by
[`COMPATIBILITY.md`](../../COMPATIBILITY.md) and the implementation constraint by
[`CONTRIBUTING.md`](../../CONTRIBUTING.md). A watcher library would overturn that contract and three
native backends would be substantial maintenance. The coarse probe described above needs
neither. It captures most of the latency win at a fraction of the surface area. Every notification,
from a probe or a native watcher, remains a hint followed by reconciliation.

### OpenTelemetry

Claude Code, Codex, and Gemini CLI all document OpenTelemetry export:

- [Claude Code monitoring](https://code.claude.com/docs/en/monitoring-usage)
- [Codex observability](https://learn.chatgpt.com/docs/config-file/config-advanced)
- [Gemini CLI telemetry](https://geminicli.com/docs/cli/telemetry/)

OTel can provide session identifiers, prompts, API lifecycle, token usage, tool decisions and results,
metrics, logs, and traces. Prompt logging is configurable but its default is not uniform, which matters
for a security review: Claude redacts prompts unless `OTEL_LOG_USER_PROMPTS` is set, Codex has
`log_user_prompt`, and Gemini's `logPrompts` defaults to true. It is useful for organizational
observability and could eventually become an optional Cargento source.

It should not be the core transport because it is disabled by default, does not cover the full
harness set, introduces OTLP receiving and decoding concerns, and is aimed more at telemetry than a
portable interactive state machine. Hooks are simpler for local lifecycle events and can report
permission waits directly.

## Harness-by-harness feasibility

No single hook integration covers all ten harnesses. The coarse probe is intended to cover their
known mutation surfaces, but cannot be called universal until its per-harness mutation corpus passes.
What hooks add is semantics, so the route is one small event adapter per harness where the semantics
justify it, each of which feeds one normalized ingress.

Cost of that route, stated plainly: ten adapters, ten forwarder configurations, an ingress, a
coalescing worker, two schedulers, an SSE endpoint, browser reconnect logic and an acquisition-mode
display, in a stdlib-only runtime with a 3:1 test-to-code ratio, `ruff select = ALL`,
`mypy --strict`, a ratcheting coverage floor and a three-OS matrix. Order-of-magnitude estimate:
1,000 to 1,500 runtime lines and 3,000 to 4,500 test lines. The latency it buys over the coarse probe
is about one second down to about 0.3 seconds. Each phase beyond the first two must carry its own
justification against the probe baseline rather than inherit this recommendation.

Distribution asymmetry compounds it. Cargento currently ships artifacts to four harnesses (Claude,
Codex, Antigravity and Gemini) and currently has no distribution artifact for the other six. That is
not the same as those ecosystems lacking manageable lifecycle support: [Pi has packages](https://pi.dev/docs/latest/packages),
[Cursor has plugin-installed hooks](https://cursor.com/docs/hooks.md), and Factory can install hooks
through its plugin surface. Other harnesses vary. Assess
install, trust, update and exact removal per harness. Until Cargento actually ships such an artifact,
any hand-written setup instructions remain a user-owned support tail.

Harness counts stated in prose drift. `docs/design-harness-registry.md` H-4 owns that problem, and
any count next to a harness list here is part of the list.

| Harness | Best passive live source | ACP or managed source | Recommendation |
|---|---|---|---|
| Claude Code | Plugin-bundled HTTP or command hooks | Claude ACP adapter | First and only initial implementation target |
| Codex | Plugin-bundled command hooks | Native app-server first; ACP adapter second | Second target, after Claude proves the ingress |
| Pi | User extension lifecycle events | Community ACP adapter | Deferred; probe baseline |
| Gemini CLI | Extension-bundled command hooks and OTel; consumer-account access transitioned, while enterprise and API-key use remain | Native ACP mode | Shipped-extension candidate after the first adapters |
| Antigravity | Plugin-bundled model/tool/loop hints, plus opt-in `statusLine` snapshots for agent state, confirmation, background tasks and quota | No listed ACP implementation | Phase 2 target alongside Claude |
| Copilot CLI | Personal command hooks | Preview ACP server over stdio or TCP | Deferred; probe baseline |
| OpenCode | Shared server SSE where safely discoverable and authenticated; user plugin otherwise | Native ACP mode | Prefer a proven existing-server topology |
| Cursor CLI | Plugin-installed hooks, with ordinary local-CLI coverage requiring fixtures | Native ACP mode, or opt-in `--output-format stream-json` in print mode | Deferred; probe baseline |
| Goose | No universal passive feed documented | Goose ACP server/API | Deferred; probe baseline |
| Factory Droid | User or plugin command hooks | Native ACP output mode | Deferred; probe baseline |

### Claude Code

[Claude's hook reference](https://code.claude.com/docs/en/hooks) exposes session start/end, prompt
submission, pre- and post-tool events, permission requests, notifications, stops, subagent and task
lifecycle, and several other events. It supports HTTP hooks directly and allows hooks to ship in an
enabled plugin. This fits Cargento's existing loopback server and can lift the current restriction
that Claude's only event-driven path is a notification side channel.

The minimal event set should be `SessionStart`, `UserPromptSubmit`, `PermissionRequest` and/or
actionable `Notification`, `Stop`, `SubagentStart`, `SubagentStop`, `TaskCompleted` if task progress is
needed, and `SessionEnd`. All nine names are present in the Claude Code 2.1.221 binary, alongside
`PreToolUse`, `PostToolUse`, `PreCompact` and `PostCompact`. That last pair is a reminder that this set
has changed across releases, so confirm each name against the installed version at implementation time
rather than against this document. Observing every tool call is not required merely to know that a turn
is active and would add avoidable process or HTTP traffic.

Cost, measured: the current forwarder takes 56 ms per invocation on macOS against a closed port:
about 13.5 ms of interpreter startup plus about 42 ms importing `urllib.request`. Process
creation on Windows is substantially more expensive. Against a 285 ms poll every five seconds,
break-even is roughly 60 hook events per minute; against a fixed 60 ms collector it is roughly 13.
The minimal event set is therefore not a nicety but the thing that decides whether the event path
costs less than the polling it replaces, and a forwarder that imports `urllib.request` on every event
is the wrong shape. Prefer `http.client`, or a persistent local transport.

### Codex

[Codex hooks](https://learn.chatgpt.com/docs/hooks) expose session start/end, prompt submission,
pre- and post-tool events, permission requests, stops, and subagent lifecycle. Enabled Codex plugins
can bundle hooks through `hooks/hooks.json` or a manifest-specific path. Non-managed hooks require
the user to review and trust their current definition, which is an appropriate consent boundary.

Codex command hooks should call a small forwarder that always exits successfully and returns quickly
when Cargento is not running. For a future managed mode, native app-server exposes explicit loaded
thread status and is preferable to scraping rollouts; compare it with the ACP adapter using fixtures
before choosing between those managed transports.

### Antigravity

Antigravity has two push paths, not one, and the second is the better fit for this design.

The [status-line callback](https://antigravity.google/docs/cli/statusline) fires on every state change,
and its payload is much richer than a dirty
signal. It carries about two dozen top-level fields, including `agent_state` (`idle`, `thinking`,
`working`, `tool_use`, `initializing`), `tool_confirmation_pending`, `pending_input_count`,
`task_count`, `session_id`, `conversation_id`, `transcript_path`, `cwd`, and a `quota` block mapping
model and bucket identifiers to `remaining_fraction`, `reset_time` and `reset_in_seconds`.
`agent_state` supplies Working and Idle, and `tool_confirmation_pending` supplies a visible
permission wait. `pending_input_count` is the number of queued user messages and must not map to
`input_requested`. Antigravity is therefore the best-instrumented
harness Cargento supports, not a marginal one, and the `/api/usage` receipt path should feed the
general event coordinator before or alongside quota shaping.

Antigravity also documents [agent hooks](https://antigravity.google/docs/hooks): `PreToolUse`,
`PostToolUse`, `PreInvocation`, `PostInvocation` and `Stop`, configured through a `hooks.json`. They
provide tool, model-invocation and execution-loop hints, not clean user-turn boundaries:
`PreInvocation` may occur before each model call, `PostInvocation` follows tool completion, and one
user turn may contain several invocations. `Stop.fullyIdle` is useful, but no adapter may normalize
these as `turn_started` and `turn_stopped` until real fixtures establish cardinality and ordering.
The decisive detail is trust asymmetry:
[plugins can bundle `hooks.json` at plugin root](https://antigravity.google/docs/cli/plugins), and
Cargento already ships an Antigravity plugin manifest, whereas `statusLine` cannot be plugin-bundled
under the documented plugin schema. Status-line forwarding still requires explicit user opt-in via
`/statusline <command>` or settings, but not necessarily hand-editing a file. So this document's own
rule, to prefer plugin-bundled hooks where Cargento already ships through the harness's plugin system,
applies here and makes Antigravity a Phase 2 target on the same footing as Claude.

Neither path replaces the other. Antigravity's hooks include no session start or end and no
notification event. The status line supplies live state, confirmation, background-task and quota
snapshots while the TUI runs, but does not document a guaranteed start, end or final callback;
collectors and reconciliation remain authoritative for definitive session lifecycle. The hooks are
what can be installed without separate user configuration.

### Gemini CLI, Copilot, and Factory Droid

All three document command-based lifecycle hooks:

- [Gemini CLI hooks](https://geminicli.com/docs/hooks/reference/) include before/after agent and
  model events, tool events, session lifecycle, notifications, and compression.
- [Copilot hooks](https://docs.github.com/en/copilot/concepts/agents/hooks) include session,
  prompt, tool, agent-stop, subagent-stop, and error events, with personal hook configuration for
  ordinary CLI use.
- [Factory hooks](https://docs.factory.ai/reference/hooks-reference) include session lifecycle,
  prompts, notifications, stops, subagent stops, and tool events. Factory documents notification
  cases for permission waits and idle input waits.

The [Gemini extension format](https://geminicli.com/docs/extensions/reference/) can bundle
`hooks/hooks.json`, and this repository already ships an extension manifest. Gemini CLI's
[consumer-account transition](https://github.com/google-gemini/gemini-cli/discussions/28017) did not
remove enterprise Code Assist or API-key use, so call out the affected authentication populations
rather than labeling the whole harness legacy.

These hooks are synchronous in at least some implementations, which puts the forwarder's cost on the
user's own agent latency. The forwarding command must do no collection work itself, must use a short
bounded loopback request, and must not make an unavailable dashboard visible as a harness failure.

### OpenCode

OpenCode has two native options:

- Its [server](https://dev.opencode.ai/docs/server/) exposes `/global/event` and `/event` SSE
  streams, session listing, and session status.
- Its [plugin API](https://dev.opencode.ai/docs/plugins/) exposes `permission.asked`,
  `permission.replied`, session creation/update/status/idle/error, message, todo, and tool events.

Prefer the shared server where the exact TUI server can be discovered and authenticated. That path
is zero-install only under those conditions: the TUI may select a random host and port, and an
operator may configure authentication. It carries `permission.asked` semantics natively for one SSE
client thread when reachable. A user plugin is the fallback for sessions with no safely discoverable
server. Starting a second `opencode serve` process does not reveal the live state of a separate TUI
server.

### Pi, Cursor, and Goose

Pi exposes an extension event model, so a small package suits passive events better than its ACP
adapter. [Cursor documents hooks](https://cursor.com/docs/hooks.md) and plugin installation, but its
official documentation does not establish complete ordinary local-CLI parity; fixture-test each
transition. Its [structured output](https://cursor.com/docs/cli/reference/output-format.md) is opt-in
`--output-format stream-json` in explicit or inferred print mode, while `text` is the default.
Goose's [official documentation](https://block.github.io/goose/) describes CLI, API and managed ACP
server modes, but no documented way exists for a separate Cargento process to attach passively to
every already-running ordinary Goose CLI session. That last conclusion is an inference from the
documented topologies, not a claim that Goose lacks managed transports.

For all three, the current store collectors remain the safe compatibility baseline. Event support
can be added only for the states proven by contract tests and real CLI fixtures.

## Proposed runtime design

```text
Claude/Codex hooks ───────┐
Antigravity statusLine ───┤
Other hooks/extensions ───┼──► Event ingress ──► Dirty queue ──► Per-harness collector
Native server streams ────┤                          ▲                    │
Managed ACP sessions ─────┘                          │                    ▼
                                                     │          Materialized snapshot
Coarse store stat probe ─────────────────────────────┤                    │
Slow reconciliation scan ────────────────────────────┘                    ▼
                                                                 SSE revision stream
                                                                          │
                                                                          ▼
                                                                   Dashboard tabs
```

### Module ownership

Four responsibilities in this design have no owner in the current module map, and the obvious
placement would invert the enforced dependency rule. Putting a publish protocol, revision counter,
dirty queue and deadline scheduler into `state.py` makes `state` import `aggregate`, which imports
`state`: an import cycle, and a failure of R-2, the inward-only dependency rule, which
`test_runtime_import_graph_matches_the_reviewed_allowlist` enforces. `design-runtime-architecture.md`
says that allowlist changes only in a PR that makes a reviewed ownership decision, never to make the
test pass.

Name the owners before implementation:

- `events.py` owns pure envelope validation, identity normalization and transition reducers;
- `snapshot.py` owns immutable published payloads, the revision pair and subscriber notification;
- `observation.py`, above `aggregate`, `events` and `snapshot`, owns the bounded dirty coordinator,
  the single collection lane, collection floors, the probe, deadlines, reconciliation, worker
  lifecycle and deterministic shutdown;
- `http_api.py` owns the stream and ingress routes through an injected observation interface.

The CLI constructs an inert coordinator. `lifecycle.serve` starts it only after the final POSIX fork
or in the Windows child, then stops ingress, wakes conditions, closes stream clients, joins every
worker to a deadline, closes the server and removes state in that order. Constructors must not start
threads before daemonization. A synchronous GET submits work to the same collection lane and waits;
dirty refresh, reconciliation, `?all=1` and GET freshness may not run collectors concurrently or let
an older slow result replace a newer result. Amend `design-runtime-architecture.md` and the reviewed
import allowlist in the same implementation PR.

### Event ingress

Use a source-specific path, for example `POST /api/events/codex`, so the server assigns the harness
from the route rather than trusting a payload field. A route is not authentication: new event ingress
requires the per-run capability described under [Security and privacy requirements](#security-and-privacy-requirements).
Normalize only an allowlisted envelope:

```json
{
  "v": 1,
  "event": "input_requested",
  "session_id": "opaque-harness-id",
  "timestamp": "2026-08-04T12:34:56Z",
  "source_instance_id": null,
  "source_sequence": null,
  "cwd": null,
  "subagent_id": null,
  "transcript_path": null
}
```

The public normalized event vocabulary can remain small:

- `session_started`
- `session_ended`
- `turn_started`
- `turn_stopped`
- `input_requested`
- `input_resolved`
- `subagent_started`
- `subagent_stopped`
- `tasks_changed`
- `store_changed`
- `reconcile_required`, for a source-specific cache invalidation such as completed compaction

Adapters translate native names. Unknown event names are ignored rather than accepted into state.
The forwarder shapes every native payload to its destination's minimum schema, and the server repeats
validation because every hook input is untrusted. `cwd` is an optional matching hint, never a display
field or authority to create a row, and is never echoed. `transcript_path` is allowed only for the
validated Claude clearing rule described under security and is never echoed.

Ordering uses three deliberately separate concepts:

- `arrival_seq` is assigned by the server under the ingress lock after authentication and validation;
  it is monotonic for one Cargento process and defines deterministic reducer order for concurrent
  handler threads.
- `(source_instance_id, source_sequence)` is optional and is used only when the native source supplies
  both trustworthy values. It supports source-local deduplication and ordering.
- `session_generation` is a server lifecycle invalidation generation, like the existing
  `hook_generation`; it is not an external event counter.

A fresh command-hook process cannot mint a shared sequence. Sources without a trustworthy native key
have at-least-once, possibly reordered delivery: reducers must be idempotent, may use a bounded
canonical-payload replay cache where safe, and reconcile ambiguous transitions. A lower source
sequence without a new source-instance identifier cannot distinguish a restart from a delayed packet,
so it triggers conservative reconciliation rather than unconditional rejection. Event timestamps
drive plausibility and displayed timing only; neither wall time nor filesystem time fences concurrency.

Event timestamps are parsed to epoch seconds and passed through the same plausibility filter as every
store timestamp, so an implausible stamp is replaced by server arrival time. A hook inside a
container whose clock runs hours ahead must not be able to pin a row.

### Envelope versioning

Adapters installed in user-owned configuration are not upgraded when Cargento is. The envelope is
therefore a versioned compatibility surface with an indefinite support tail, not an internal wire
format. Every event carries `v`; the server accepts a documented range of versions; and an
out-of-range `v` is reported through `--diagnose` and the acquisition-mode strip as
`event-incompatible` rather than silently ignored, which is what the unknown-name rule above would
otherwise do to it. Removing a field or changing a field's meaning is a breaking change to a public
interface.

### Session identity

The envelope's `session_id` is not the key the collectors use. Claude's `sid` is the eight-character
prefix of the transcript filename and `dedupe_sessions` keys on `(harness, sid)`, which is why the
existing notification path truncates the hook payload's full UUID before looking anything up. An
overlay keyed on the raw native id would never match its row.

The ingress therefore owns a per-harness identity normalizer that maps a native event id onto the
exact `sid` its collector produces and rejects ambiguous mappings. A normalized id that matches no
collected session goes into a small bounded, expiring pending map and triggers collection; it never
renders and never creates a row. It attaches only if a later collection produces the matching
`(harness, sid)`, otherwise it expires after bounded time and attempts with a diagnostic counter.
This preserves first-session and early permission events without letting a wrong or forged id invent
a session. The mapping and pending behavior must be established per harness before its adapter ships.
At capacity, reject new pending entries and count the rejection rather than evicting a live alert.

### Dirty queue and coalescing

An event handler must acknowledge quickly. It should not scan a transcript or query SQLite on the
hook's request thread.

Instead it should:

1. Authenticate, validate and normalize the event.
2. Assign its `arrival_seq` and apply only a transition that is unambiguous and safe, if one exists.
3. Mark the session or harness dirty by advancing its dirty generation.
4. Signal the coordinator condition.
5. Return promptly; the reporting shim exits successfully even if Cargento rejects or drops it.

The coordinator coalesces an event burst for roughly 50 to 150 milliseconds. The window is fixed,
not sliding: a sliding window never closes under a sustained burst and the board would stop updating
entirely. Every overlay in a burst is reduced in `arrival_seq` order. A matched `input_requested` is
exempt from the delay and publishes an overlay revision immediately; an unmatched request remains
non-rendering in the pending map until a collector supplies its row. No event is assumed to arrive
alone.

Coalescing bounds burst latency but sets no floor between collections, and removing the 2.5-second
memo would remove the only rate limiter on store reads. A ten-agent fan-out emitting lifecycle events
continuously would drive roughly 6.7 full collections per second against today's ceiling of 0.4.
Keep an explicit minimum interval per harness, the role `collect_memo_sec` plays today. The first
dirty event schedules collection at the later of the fixed coalescing deadline and the harness's next
allowed collection time; subsequent events merge into the pending state. Semantic overlays may
publish before that collection. The floor is the store-protection guarantee and must not be a derived
side effect of the coalescing window.

The bounded coordinator exists regardless of whether selective collection proves worthwhile: it
serializes events and scans, enforces floors, and keeps collection off request threads. The existing
`HarnessSpec.collect` boundary makes per-harness refresh feasible. The Phase 0 selective-reuse gate
failed at 16%, so what Phase 1 builds is the failed-gate path: the coordinator marks the aggregate
dirty and performs one full `Application.collect` per floor instead of retaining per-harness results.
The paragraph below describes the selective path only for the day a profile clears the gate.

When selective refresh is enabled, the new application state retains one current result per harness,
merges only the refreshed harness, deduplicates and sorts the aggregate, then serializes a new
version. Retained per-harness results are immutable once
published: `assign_display_ids` writes into session dicts and the Claude collector mutates task dicts
during row construction, so merging must build a fresh aggregate list before dedupe, display-id
assignment and sorting run over it. Otherwise a Codex worker re-running display-id assignment over
the retained Claude list while `/api/data` serializes it can emit one session twice at two id widths,
the exact confusion display ids exist to prevent. The single coordinator lane serializes collection
and merge, rather than merely placing a lock around the final merge.

`show_all` is decided here rather than deferred, because it is not a presentation filter: it reaches
into the collectors and changes what they return. The snapshot is built for the default window only.
In the first delivery, `?all=1` keeps its existing five-second polling fallback behind its own memo
instead of reacting to default-view revisions; its collection still runs through the coordinator and
the same overlay/fencing pass. A later on-demand historical snapshot may replace that fallback.
Deriving both centrally from one raw snapshot would mean always collecting the unfiltered set, and on
a machine with 3,600
historical Claude transcripts that is the expensive path taken on every lifecycle event, forever, for
a rarely used historical query.

### Event overlays versus store truth

Some native events are semantically stronger than persisted stores:

- prompt or before-agent event → Working;
- explicit permission request → Needs input;
- permission reply or resumed agent activity → Working;
- stop or after-agent event → Idle, after a short dwell;
- subagent start/stop → update child activity.

Other events only mean that the store probably changed. Provenance matters: an explicit native
permission request can patch `state`, `state_detail`, `active`, `blocked_since` and the event-derived
activity marker. A generic or actionable Claude `Notification` remains standing hook state under
today's precedence; it is not promoted to an authoritative permission overlay.

Precedence is per field and per provenance, not per timestamp. A live Working or explicit-permission
overlay may be authoritative for the fields above when its adapter contract proves the transition.
For every other field the collector is authoritative: titles, projects, historical turns, tasks,
token rates, parent relationships, subagent reconstruction and recovery after missed events. That is
what makes a long generation stay Working without letting a hook rewrite collector-owned metadata.

Wall-clock recency cannot fence a concurrent collection. Under the ingress lock, each collection
captures `collection_start_seq` and the harness dirty generation before reading. Under the merge lock
it then:

1. installs the collector result only through the single collection lane;
2. applies **every live overlay**, including overlays that predate collection start, in `arrival_seq`
   order;
3. refuses to retire an overlay whose `arrival_seq` is newer than `collection_start_seq`; and
4. leaves the harness dirty and queues another pass if its dirty generation changed during the read,
   because a non-semantic `store_changed` event cannot be recovered by overlay replay.

The overlay ledger is immutable apart from explicit retirement records. `arrival_seq`, not an epoch
clock, closes the mid-collection race. A collector can retire an older overlay only through a
documented, source-specific evidence rule.

One such rule already exists and must be preserved: the Claude collector lets fresh transcript or
background activity beat a standing `Notification`, because Claude Code can emit an input-waiting
notification for a session that continues running. An explicit `PermissionRequest` is different and
must be cleared by a reply, resumed activity known to follow it, session end, or equivalent positive
collector evidence. Working overlays get a measured deadline so a missed stop cannot pin Working.
Needs-input overlays do not get an arbitrary time-only expiry; event-source liveness can become stale
without silently clearing a real hours-long permission wait.

`session_ended` is non-destructive. It retires overlays and hook state but never removes a row; only
the collector may do that. Claude fires it on `/clear` as well as on exit, so a user who clears and
immediately prompts again can produce `session_ended` and `turn_started` for the same session inside
one coalescing window. A killed harness may never send it; in that case its source-health lease
expires while the alert remains until positive evidence resolves it or the collector removes the row
from its authoritative window.

Compaction is a conservative invalidation hint, not documented proof that Claude rewrites its JSONL.
If fixtures show a transient mutation window, `PreCompact` marks rewrite-in-progress and suppresses
collection; `PostCompact` emits `reconcile_required`, clears only the scan or metadata caches proven
unsafe, and performs a full session reconciliation. If only one event is supported, use
`PostCompact`. Offset/size discontinuity detection and periodic reconciliation cover compaction with a
missed event. Neither hook counts as activity. Tests must cover both append-only and rewrite fixtures
before the implementation assumes either storage behavior.

Notification ownership has to move with this. Both the native notifier and browser notification text
hardcode Claude today. Before any second harness can report Needs input, titles and bodies must derive
from the matched row's harness label. The server assigns a stable alert generation so overlay- and
collector-derived views of one wait deduplicate against the same identity; native and browser ledgers
consume that identity according to the user's channel policy. Only the elected browser leader may
issue browser notifications; follower tabs render the shared snapshot without each producing another
popup.

### Versioned snapshot

Replace the 2.5-second response memo with a durable in-memory snapshot and monotonically increasing
revision:

- `/api/data` returns the latest already-built bytes, subject to the freshness rule below.
- Collection workers, deadline timers, quota updates, and hook overlays publish revisions.
- A revision increments only after a material state change or a deliberate generated-time update.
- Collection failure for one harness retains the existing per-harness failure boundary.
- The cache remains bounded and process-local; the first demanded snapshot is reconstructed from
  stores before it is served. An idle daemon with no request and no event still does no filesystem
  work.

A revision number alone is not a safe cursor, because it restarts at zero when the process does. Every
revision is the pair `(server_started, revision)`. `server_started` already exists and `/api/health`
already publishes it. The pair distinguishes a restart; it does not "survive" one. Any change in the
first element forces the client to discard its cursor and refetch. `/api/data` returns the revision it
actually served, so the client compares what it got rather than what it was told. Otherwise a tab
frozen at revision 512 across a dashboard restart would treat every subsequent revision as older and
never refetch, showing an hours-old board behind a live indicator.

`/api/data` must also remain self-freshening. Define a direct-GET maximum age no greater than today's
`collect_memo_sec` (2.5 seconds by default), independently of the slower reconciliation interval. A
GET beyond that age submits a collection to the coordinator and waits before answering.
`curl -s http://127.0.0.1:4553/api/data` is documented in the shipped skill, is printed by the
bind-error message, and is the whole headless and SSH story; those callers have no SSE connection and
no tab. A snapshot-only read would hand them arbitrarily stale data. This keeps the current freshness
contract rather than quietly replacing 2.5 seconds with 30 to 60 seconds.

Time-derived fields need their own contract, but the wire snapshot does not currently retain enough
inputs to recompute them cheaply. Before Phase 1, inventory `rate_per_min`, `turn`, Claude task
`elapsed_h` and `updated_ago`, `active`, history-window membership, overlay dwell/expiry and
`generated`. For each, either retain immutable derivation inputs outside the wire snapshot or admit
that the tick recollects and measure that cost. A scalar `rate_per_min` cannot decay itself; its source
timestamped usage events or database projection must remain available.

Use one documented sampling cadence after that design is proven. Add a `rate_sampled_at` value (or an
equivalent fixed time bucket) so the frontend appends at most one sparkline point per cadence. Event,
quota and notification revisions must not create extra samples merely because `generated` advanced;
otherwise an event burst distorts the rate graph. Without an explicit derivation and sampling design,
keep today's five-second collection behavior for these fields.

### SSE browser delivery

Add a `GET /api/stream` endpoint that is strictly same-origin. It must not inherit the `do_GET`
default: `do_GET` passes `allow_cross_site_navigation=True` so a cross-site *document* navigation can
reach the dashboard, while `do_POST` uses the strict check. A long-lived data stream is not a document
navigation and must use the strict form. SSE is preferable to WebSockets for the dashboard
because updates are server-to-browser; existing HTTP POST endpoints already cover shutdown and any
future controls.

A minimal stream can send revision numbers rather than duplicating the full dashboard payload:

```text
id: 1722765296.125/123
event: revision
data: {"server_started":1722765296.125,"revision":123}

```

The page loads `/api/data` once, opens `EventSource`, and fetches the cached payload whenever it sees
a newer revision. This design preserves the current rendering functions and keeps large JSON out of
the long-lived stream. Every connection receives the current pair immediately. `EventSource`
reconnects automatically and sends the last string as `Last-Event-ID`; the server, not the browser,
owns replay policy. When the server identity differs it sends a `reset` event and forces a data
refetch. When it matches, sending the current revision is sufficient, so a replay buffer is not
required. Leader handoff shares the complete pair, not the numeric revision alone.

Three constraints apply, and none of them is optional.

The first is the browser's connection budget. HTTP/1.x browsers commonly cap persistent connections
near six per browser and domain, so one `EventSource` per tab can starve other requests. Exact limits,
pooling and failure behavior are user-agent-dependent; the risk is not a theorem that the seventh tab
always freezes. Elect one leader tab per origin over `BroadcastChannel` or a `localStorage` lease to
hold the single stream and fan revisions out to the others, with a hard staleness deadline and tested
handoff. Unsupported coordination falls back to bounded polling rather than opening unbounded streams.

The second is the response path. The handler's `protocol_version` is HTTP/1.0 and its send helper
always sets `Content-Length`, so the stream needs its own persistent response path and an explicitly
tested HTTP version rather than an extension of the existing helper. Send and flush an SSE comment
heartbeat about every 15 seconds so intermediaries and clients can detect a dead connection.

The third is connection, thread and lock discipline. A stream cap alone is insufficient because
`ThreadingHTTPServer` creates a handler before the route is known, and partial headers or bodies can
occupy threads. Add a server-wide accepted-connection/handler budget, header and body read deadlines,
exact body-length enforcement and a smaller SSE cap. Give every accepted stream a one-slot
latest-revision queue and a socket write timeout; collapse intermediate revisions rather than growing
a FIFO. Never hold snapshot or client-registry locks across a socket write. The snapshot is published
as one immutable `(revision_pair, bytes)` value under a short lock. Today the collect memo lock is held
across collection, so that is exactly the lock the implementation will be tempted to reuse.

While the default-window stream is healthy, the browser's five-second refresh timer disappears. In
Phase 1, before hooks or the probe exist, one demand-scoped server producer runs the current
five-second collection cadence while at least one stream client is connected and stops at zero
clients. Merely opening a passive connection is not a recurring trigger. Later phases may replace
that producer only when their correctness gates pass. A slow adaptive fallback remains for
unsupported browsers and prolonged disconnection, while `?all=1` retains the explicit fallback above.
The client coalesces revisions behind a minimum render interval. The frontend rebuilds `#app` from
scratch on every render and reapplies reader state afterwards, so a burst arriving several times a
second during a fan-out would
destroy and rebuild the DOM under a user mid-keystroke. Skip re-rendering while an interaction is in
progress.

Shutdown closes stream sockets and must prove long-lived handlers and every observation worker exit
within the shutdown deadline.

### Deadline scheduler and reconciliation

The runtime needs two kinds of background scheduling:

1. Exact deadlines. Working-to-Idle transitions, transient-overlay expiry, source-health leases,
   history-window removal, and similar state derived from time. Needs-input retirement requires the
   positive evidence defined above, not a generic TTL. A condition-driven priority queue or
   recalculated nearest deadline avoids a busy loop. Deadlines must tolerate a machine that suspends
   and resumes, where a batch of them comes due at once.
2. Reconciliation. A full or dirty-aware store scan that repairs state after dropped events, unclean
   harness exits, unsupported versions, or files copied into a store.

A reasonable starting policy is:

- full reconstruction on the first `/api/data` or stream demand, or on an event that requires a row
  for an immediate native notification; no eager scan merely because the daemon started;
- direct-GET maximum age at or below today's 2.5-second memo age;
- the current five-second connected-client producer for Phase 1 and for sources without proven
  invalidation coverage;
- immediate selective collection after events;
- 30 to 60 second reconciliation only for sources whose probe or event topology has passed its
  correctness and liveness gate;
- a longer interval when no tab is connected, while hooks continue to maintain native notification
  state. A read still collects on demand, so no timer-driven scan is not the same as no scan;
- immediate reconciliation on tab focus, stream reconnect after a long gap, or manual refresh.

The exact values should follow measurements rather than become undocumented constants.

Three timings are independent configuration values: direct-GET maximum age, connected-client
producer cadence and slow reconciliation cadence. Conflating them silently weakens the headless API.

Two classes of session get *worse* under a slower reconciliation cadence and must be exempt. A
session in a container or remote shell has its own loopback, so its hook POSTs to a `127.0.0.1` that
is not the host's and the event is lost by design; if its store is bind-mounted, polling sees it today
at five seconds and would see it at 30 to 60 instead. The same applies to any harness with no healthy
event source. Either the reconciliation floor stays at the current poll interval for those harnesses,
or the acquisition display shows those rows as `scan-only` with their true latency. The degradation
must be disclosed, not silent. A command-hook receipt is not a harness heartbeat: an idle session,
disabled hook and broken hook are otherwise indistinguishable. Track `installed`, `compatible` and
`live` separately. Only a verified heartbeat or persistent source subscription establishes continuing
liveness; a one-shot hook establishes at most a short per-session lease and never justifies reducing
harness-wide reconciliation on its own.

### Quota consent and refresh

Today a page adds `usage=1` to `/api/data` only after the user has enabled the feature and answered
the disclosure. That request may schedule a vendor quota fetch behind its existing floor and
in-flight gates. [`SECURITY.md`](../../SECURITY.md) publishes the resulting property: with the feature
off, nothing is fetched or retained, and no polling happens while no dashboard page is connected.

Phase 0 repaired the two existing violations of that contract: Windows daemon respawn now carries
`--no-usage`, and `/api/usage` now discards quota fields before storage whenever server-side usage is
disabled, while still answering 200 so a status line never sees an error. Those were security
prerequisites, and Phase 1 may now claim the contract it preserves.

Under SSE, quota consent remains browser-originated but cannot depend on unrelated revisions. The
elected tab is the only quota-triggering client. It broadcasts `localStorage` consent changes to all
tabs, transfers the current value on leader handoff, and sends or renews a short-lived same-origin
server consent lease while enabled. Revocation clears that lease immediately; absence of a page lets
it expire. A consenting leader sends an explicit quota-due request no more often than the existing
vendor/cache floor, so five quiet minutes still refresh without a session revision. A server timer
never initiates an outbound vendor fetch by itself, and background fetch completion publishes a
snapshot revision.

Antigravity status-line forwarding separates always-allowed lifecycle fields from quota fields. The
server drops quota before storage when `--no-usage` is set or no consent lease exists. Quota
acquisition and session acquisition remain separate schedulers even when both publish into the same
dashboard snapshot.

## Installation, upgrade, and removal

Every adapter Cargento does not distribute through a harness plugin is user-owned configuration that
outlives Cargento's own installation. The hazard is already reachable: the shipped skill tells users
to hand-add a `notify_hook.py` command to their Claude settings, and uninstalling the plugin deletes
that path while leaving the hook in place, so every later session runs a command that cannot be found.

The plan must therefore include:

- plugin- or extension-bundled hooks wherever the harness supports them, using its native trust and
  uninstall lifecycle;
- an `--install-hooks <harness>` / `--uninstall-hooks <harness>` pair only for adapters Cargento must
  place in user configuration. It previews a diff and requires explicit confirmation, rejects
  symlinked or wrongly owned targets, uses compare-and-swap plus atomic replacement, preserves a
  recovery backup, marks the exact entry and removes only that entry, and detects concurrent edits;
- a self-contained stable shim outside a versioned plugin/cache path, for example under
  `CARGENTO_HOME/bin`, installed atomically and retained as a silent no-op until its matching config
  entry is removed. A deleted script cannot execute code to exit 0, so manually installed hooks must
  never point only at the removable plugin copy;
- `notify_hook.py` retained at its current plugin-relative path and default URL for legacy settings
  while that plugin is installed. It cannot promise graceful behavior after the plugin itself is
  deleted. New behavior arrives behind arguments rather than breaking the legacy invocation;
- a minimum schema per destination. Antigravity forwarding retains only the quota buckets and
  lifecycle fields actually consumed, and drops account email and unrelated state before transport;
- `--diagnose` listing installed adapters with the Cargento version that wrote them.

Adding a stable shim, secret or edited harness config changes the "exactly two written files" contract
in `SECURITY.md`; amend that owner before implementation rather than hiding the new paths in an
installer.

### Port discovery

The forwarder must discover the port rather than assume it. `notify_hook.py` hardcodes port 4553 and
works on another port only because the skill tells the user to pass a URL by hand. A plugin-bundled
hook bakes a fixed command string into a manifest, so a user on `--port 9999` gets a hook pointed at a
port nothing is listening on, silently and forever.

The state directory can hold the answer, but the current health response is not authentication: a
process that acquires a stale recorded port can imitate its JSON and capture forwarded payloads. The
selected design must authenticate discovery before sending event data. The forwarder reads an
owner-private per-run secret, challenges the candidate with a fresh nonce, and accepts only a response
that authenticates the nonce and expected server identity. The subsequent capability is bound to the
source endpoint. An explicit URL or environment override must supply equivalent authentication; it
does not bypass the requirement.

Create state and secret material atomically. On POSIX, reject symlinked, non-owned or permissive state
homes/files. `0600` is not a Windows ACL design, so Phase 0 must choose and prove a Windows user-scoped
mechanism, such as protected secret storage or an explicitly ACLed named pipe/file. If owner privacy
cannot be established, event overlays stay disabled and the instance remains scan-only.

Discovery and delivery share one end-to-end deadline, targeted at roughly 100 to 250 ms and measured
at p95 and p99 on every supported OS. Do not spend a per-probe timeout or the current two-second HTTP
timeout on each candidate: synchronous SessionEnd hooks have tighter budgets. The shim always exits
successfully and silently when the deadline expires.

### Multiple instances and multiple users

`lifecycle` supports many instances by design, one state file and one `--status` per port, but a
synchronous hook must not probe and post sequentially to all of them. An explicit authenticated URL
targets one instance; otherwise discovery chooses one authenticated live instance deterministically.
Every other instance keeps the current scan cadence and reports `scan-only`, rather than claiming a
stale event integration or silently slowing its polling. A future authenticated local dispatcher can
fan out off the hook's critical path, but is not part of this plan.

Loopback is also not a user boundary. The local-request check reads Host, Origin and `Sec-Fetch-Site`,
none of which carry a uid, and separate ports or store roots are discovery hygiene rather than access
control. New event ingress therefore requires the per-run capability above; without it, overlays are
disabled and current polling continues. This protects event integrity only. Other local accounts can
still read `/api/data` and reach existing control surfaces under the accepted exposure in
`SECURITY.md`. Actual shared-host confidentiality would additionally require protecting `/api/data`,
`/api/stream` and `/api/shutdown`. The optional `cwd` hint never creates or renders a row, so it is not
an event-driven path-disclosure field.

## Security and privacy requirements

The refactor must preserve both invariants in [`SECURITY.md`](../../SECURITY.md). The requirements
below are how this design satisfies them.

- Reuse the current Host, Origin, and fetch-site checks.
- Require an authenticated per-run, per-source capability for every new event overlay; source-specific
  routing chooses a harness but does not prove the caller.
- Reject non-loopback forwarding URLs and redirects.
- Keep strict body caps, exact lengths, read deadlines, a server-wide handler budget, per-source rate
  limits and bounded pending/replay/overlay caches.
- Assign the harness from the endpoint or installed adapter, not from the body.
- Allowlist fields and event names; discard prompts, tool arguments, tool output, credentials, and
  unrelated native payload fields.
- Deduplicate only when an adapter supplies a trustworthy source instance and key. Otherwise document
  at-least-once/out-of-order delivery, use idempotent reducers and reconcile ambiguous events.
- Always return quickly and never make a missing Cargento server disrupt an agent session.
- Keep hook installation visible and consented. Where a harness has plugin hook trust, use it.
- Make ACP control access an explicit separate mode rather than silently weakening the read-only
  product promise.

The trust boundary widens with this work, and that has to be recorded rather than implied. Today a
forged `POST /api/notify` can set one harness's side state, which `SECURITY.md` carries as accepted.
General lifecycle overlays are more powerful: a forged `session_ended` can suppress a permission
alert, and a looped `turn_started` can mask a blocked session. Do not merely generalize the accepted
exposure. Require the new capability, retain the invariant that an overlay may patch only a
collector-produced row and may never create or delete one, and document that same-user malicious
processes remain inside the trust boundary because they can read user-owned secret material.

One allowlist exception is load-bearing. The rule that clears a standing needs-input hook when the
newest user record changes works
only because the payload carried `transcript_path`; without it the code falls back to a timestamp rule
its own docstring describes as compatibility for older versions. Keep `transcript_path` in the
allowlisted envelope for harnesses whose clearing rule depends on it, validated as it is today (inside
the resolved projects root, basename matching the session prefix), since it is a path the server already
resolves rather than new content, and never echo it to `/api/data`. Shape every destination to its
minimum envelope before forwarding. In particular, `/api/usage` does not need account email or the
complete status-line document merely because it needs selected quota and lifecycle fields.

## User experience

The visible benefits:

- Session transitions appear shortly after the native lifecycle event rather than up to five seconds
  later.
- More harnesses can display Needs input, for those whose native hooks expose permission waits and
  whose adapter is authenticated, contract-tested and carrying a live per-session lease.
- Long generations remain Working even when their persistent store updates only at message end, on
  harnesses with a contract-tested turn-start event and live per-session lease.
- Multiple dashboard tabs no longer cause repeated scans, up to the connection budget above.
- Native notifications still work with no browser tab open.
- Store-only and older harness versions retain today's scan cadence until a probe or persistent source
  passes the gate that permits reducing it.

Cargento should disclose the quality of each source rather than make all rows look equally live. Do
not collapse configuration, mode and health into one label. Diagnostics and possibly the harness
strip expose:

- acquisition mode: `managed`, `events-plus-reconcile`, or `scan-only`;
- installation state: `not-installed`, `installed`, or `requires-trust`;
- compatibility: `compatible`, `incompatible`, or `unknown`;
- positive liveness: `connected` for a persistent source, a short `session-lease` after a command
  hook, or `unverified`. Ordinary user inactivity is not evidence that a hook is broken.

`--diagnose` should report which integrations are installed, which endpoint last received an event,
the last event timestamp, the last successful collection per harness, any adapter error without
prompt content, and counters for events accepted, events rejected by reason (unknown source, unknown
name, oversized body, failed authentication or allowlist, deduplicated event, incompatible version),
pending overlays expired, coalescing windows opened, and selective or full collections triggered. An
adapter firing ten times a second and one firing never look identical without those counters.

## Delivery sequence

### Phase 0: measure, repair prerequisites, and fix the collector

The baseline measurements must complete before architectural code lands. What was measured, and what
was not:

| Baseline measurement | Status |
|---|---|
| Cold and memo-hit collection duration | Measured. Cold 275 to 297 ms, warm 118 to 120 ms, one machine. |
| Discovery and collection duration per harness | Measured by `scripts/bench_collect.py`, one machine. |
| `cProfile` of the slowest collector by function | Measured. Claude remains the slowest; its residue is subagent globbing (140 ms cumulative under the profiler), JSONL parsing and turn scanning. |
| Files or bytes consulted | **Not measured.** No counter exists without instrumenting `io.py`, and the design asks for this only where cheaply measurable. Blocks nothing on its own, but leave the row empty rather than guessing. |
| Number of collections with one and several tabs | **Not yet measured, blocks the phase it gates.** Only meaningful once Phase 1 owns the render path. |
| Forwarder p50, p95 and p99 per OS, against a closed port, a stale listener and a live server | **Not yet measured, blocks the phase it gates.** One macOS median (56 ms, server absent) exists and is not a distribution. Depends on the authenticated discovery Phase 2 designs. |
| Native hook event count per turn per harness | **Not yet measured, blocks the phase it gates.** The Antigravity status-line path is in production and remains the free sample to take it from. |
| Probe dependency table, mutation corpus, warm and cold probe cost and false negatives on three OSes | **Not yet measured, blocks the phase it gates.** Phase 0 did not build the probe. |
| Event cardinality and ordering from real harness fixtures | **Not yet measured, blocks the phase it gates.** Prerequisite for assigning semantic transitions. |

Event-to-render latency and reconciliation repair counts are post-change measurements, but
missed-event rate is a rollout gate rather than a dashboard-only metric.

The collector fixes from [Make collection cheaper](#make-collection-cheaper) have landed, with the
parked-parent and nested-workflow equivalence tests, and they changed every number above. The two
quota opt-out defects are fixed as well: `--no-usage` now reaches the respawned Windows daemon, and a
pushed status-line receipt has its quota fields dropped before storage when server-side usage is off.
[`SECURITY.md`](../../SECURITY.md) documents the resulting behavior, so no exposure remains open
against the published contract.

The gates are independent. Verdicts, one per gate:

- **Selective reuse: NOT DECIDABLE from the profile measured. Do not treat it as failed.** The rule
  is that if per-harness reuse saves less than 25% of post-fix collection time, keep the coordinator
  but run one full aggregate collection per floor. The saving available to reuse is the total minus
  the largest single harness, as a fraction of the total, since the dirty harness is the one whose
  cost cannot be skipped. That makes the criterion a single number:

  > Selective reuse clears the 25% bar whenever the largest harness is at most 75% of collection
  > time. It fails only when one harness dominates.

  The one machine measured is an extreme outlier and cannot answer this. Its Claude store holds
  25,483 files against Codex's 349, a 71x skew, so Claude is 92.8% of collection time and the saving
  computes to 7.2%. That is a fact about one store, not about the product.

  Extrapolating from measured cost per store file makes the direction clear, and it points the other
  way. Claude is now the *cheapest* collector per file, at 0.0039 ms, precisely because Phase 0
  optimised it; every other collector currently costs between 1.5x and 11x more per file. So at equal
  history volumes Claude does not dominate at all:

  ```
  measured ms/file:  claude 0.0039  cursor 0.0059  codex 0.0118  antigravity 0.0178
                     copilot 0.0200  pi 0.0427

  this machine, 71x Claude skew      largest 92.8%  saving  7.2%   fails
  10k Claude + 1k each x4            largest 41.6%  saving 58.4%   passes
  two harnesses, 5k files each       largest 74.9%  saving 25.1%   passes
  five harnesses, 3k files each      largest 33.6%  saving 66.4%   passes
  ```

  Every balanced profile clears the bar, and the largest harness in those profiles is Copilot, not
  Claude. Cargento's intended users run several harnesses, so the balanced rows describe them better
  than the machine that produced the measurement does.

  Treat the extrapolation as establishing that the question is open, not as a new verdict. Cost per
  file is crude: collectors read different formats with different fixed overheads, the file counts
  are whole store trees rather than in-window sessions, and the other collectors have not had the
  optimisation pass Claude just had, so their per-file cost may also fall.

  What this gate needs is `scripts/bench_collect.py --repeat 7` output from several genuinely
  multi-harness machines, reported as largest-harness share rather than as absolute milliseconds so
  the figures are comparable across hardware. Until then Phase 1 should keep the publish protocol
  behind an interface that can serve either one full aggregate or per-harness merges, and should not
  hard-code the full-aggregate assumption that a single-machine reading would have justified.
- **Coarse probe: not yet measured, blocks the phase it gates.** Do not use it to reduce scans until
  its mutation corpus has no false negatives on supported local filesystems and its CPU/I/O budget
  passes on all three OSes. WSL, remote, bind and network stores retain the current cadence unless
  separately proven. Phase 0 built no probe, so this gate is unreached, not passed. The 0.14 ms sweep
  remains a hypothesis.
- **Adapter semantics: not yet measured, blocks the phase it gates.** Do not publish an overlay
  transition without contract or real-CLI fixtures proving event meaning, cardinality and order. Each
  synchronous shim must fit the single end-to-end p99 hook budget. Unreachable until Phase 2 collects
  those fixtures.
- **Operational rollout: not yet measured, blocks the phase it gates.** Retain abort thresholds for
  CPU duty, memory, handler/thread ceilings, p95 render latency and missed-event repair rate. A 25%
  collection threshold alone cannot protect the user experience. There is no render path to measure
  against until Phase 1 delivers one.

Phase 1 may proceed: its inputs from Phase 0 are the post-fix collection time and the selective-reuse
verdict, and both now exist. Phase 2 may not begin its probe or its adapters, because all three gates
those steps depend on are unreached.

### Phase 1: materialized snapshot and SSE

- Introduce a versioned snapshot, revision pair, and publish protocol in the modules named above.
- Start its services only after daemonization and implement the shutdown order above.
- Make `/api/data` serve the snapshot with the independent 2.5-second-or-better direct-GET freshness
  rule; initialize lazily on first demand.
- Add the SSE revision stream with restart-qualified IDs, immediate current-state delivery, server-wide
  and stream connection budgets, read/write timeouts, one-slot queues, heartbeats, leader-tab election
  and browser reconnect behavior.
- Keep one demand-scoped server producer at the current five-second cadence while a default-window
  stream is connected. Stop it with zero readers; keep `?all=1` on its explicit polling fallback.
- Move time-derived fields only after the derivation-input inventory proves the tick can recompute
  them; otherwise retain the current cadence. Decouple sparkline sampling from arbitrary revisions.
- Implement elected-tab quota consent synchronization, the explicit quota-due request, completion
  publication, and server-side discard of unconsented pushed quota.

This phase separates browser delivery from collection without changing harness semantics. Its success
criterion is delivery-mechanism correctness, not a user-visible latency improvement, which it does not
produce.

### Phase 2: the gated coarse probe, then Claude and Antigravity events

- Add the coarse store probe only for harnesses and filesystems that pass its independent gate;
  unproven sources keep the current scan cadence.
- Add authenticated normalized ingress, envelope versioning, identity normalization, the pending
  overlay map and the bounded coordinator. These are not subject to the selective-reuse gate; a
  failed reuse gate makes the coordinator run a full collection.
- Ship a minimal plugin-bundled lifecycle hook for Claude first, using its native trust model, and get
  the ingress to one working producer end to end before adding a second.
- Then add Antigravity's plugin-bundled `hooks.json` as model/tool/execution-loop hints, not asserted
  user-turn boundaries. It installs with the plugin Cargento already ships, which makes it the
  cheapest second producer.
- Generalize notification ownership off the Claude-specific path.
- Extend `notify_hook.py` with source-aware minimal schemas behind arguments, keeping its legacy path
  and default URL while installed. Add the stable shim and authenticated one-instance discovery with
  a single end-to-end deadline.
- Route Antigravity's existing status-line receipt into dirty invalidation, and read `agent_state`,
  `tool_confirmation_pending` and `task_count` from its minimal lifecycle envelope.
  `pending_input_count` is queued user input, not Needs input. Keep status-line quota separately;
  collectors own definitive session lifecycle.
- Add deadline-driven Working-to-Idle transitions with dwell. Needs-input retirement requires
  positive evidence, not a generic dead-man timeout.
- Do **not** reduce reconciliation from a one-shot hook receipt or for a harness without positive
  liveness and proven invalidation coverage.

This is the highest-value validation milestone because the repository already distributes Cargento to
Claude and Antigravity and already has push plumbing for both.

### Phase 3: Codex and Gemini, then nothing else by default

Add the Codex adapter once Claude has proven the ingress; its plugin can bundle hooks and its
app-server is a provisional managed target later. Evaluate Gemini next because Cargento already ships
a Gemini extension and that extension can bundle `hooks/hooks.json`; consumer-account transition does
not erase enterprise and API-key CLI use.

Further passive adapters (OpenCode, Copilot, Factory Droid, Pi, Cursor and Goose) are deferred
indefinitely. Each needs its own justification against the proven probe baseline and a harness-specific
distribution/lifecycle assessment. OpenCode is worth revisiting first only where Cargento can safely
discover and authenticate the exact already-running TUI server; otherwise it is not a zero-action
topology.

Each adapter must be independently optional and independently testable. One broken integration must
never take down the aggregate, as the existing collector failure boundary already ensures.

### Phase 4: optional managed sessions

A managed ACP or native-server mode is a different product from passive cartography, and the analysis
above already establishes that. It is recorded here only so it is not mistaken for sequenced work:
prototype it, if ever, after the passive architecture is stable, with one harness, explicit connection
ownership, faithfully proxied permission requests, managed and passively observed sessions displayed
distinctly, and collectors retained for history and crash recovery. Codex app-server or OpenCode's
native server is the provisional first managed integration because each documents explicit native
state; validate that choice against an ACP adapter fixture before committing to it.

## Verification requirements

The implementation plan should include tests for:

- event capability authentication, source binding, body-size limits, exact lengths, read deadlines,
  invalid JSON, unknown sources, unknown events, per-source rate limits and server-wide handler caps;
- authenticated discovery rejecting a stale-port impersonator before sending a payload, owner and
  symlink checks on POSIX, and the selected Windows user-private mechanism;
- an out-of-range envelope `v`;
- field allowlisting and prompt/tool-output redaction, with `transcript_path` retained and never
  echoed, and Antigravity email/unrelated fields removed before forwarding;
- native ids that must be normalized to a collector `sid`, ambiguous ids, a first-session event before
  store flush, an event during the first collection, pending attachment, expiry, and capacity rejection;
- trustworthy source-instance/sequence deduplication, sources with no sequence, reordered and repeated
  events, a source restart, idempotent reduction and conservative reconciliation;
- an implausible or skewed event timestamp;
- event-burst coalescing, arrival-order overlay application, and the per-harness collection floor;
- an overlay and a non-semantic dirty event arriving mid-collection, fenced by `arrival_seq` and dirty
  generation rather than wall time;
- one collection lane across dirty refresh, reconciliation, direct GET and `?all=1`, proving an older
  slow result cannot overwrite a newer one;
- per-harness selective collection and unchanged-harness reuse, with retained results proven
  immutable, plus the failed-reuse-gate full-collection path;
- one collector failing while other cached harnesses remain available;
- the Claude membership cache appending an existing parked-parent child and creating a nested workflow
  child without touching ancestor directory mtimes;
- every coarse-probe mutation and filesystem case in its Phase 0 corpus;
- Working-to-Idle transitions without a new event, dwell, Working-overlay expiry, and a long-lived
  Needs-input overlay that is not cleared by time alone;
- `session_ended` followed immediately by `turn_started` for one session;
- `PreCompact`/`PostCompact`, append-only and rewrite fixtures, and compaction with a missed event, all
  reconciled without counting as activity;
- provenance-specific precedence: a Claude `Notification` stays subordinate to fresh activity while
  an explicit permission request retains its contracted fields;
- Needs input and its notification on a non-Claude harness;
- lazy first-demand reconstruction, no filesystem work for an idle no-event daemon, a critical event
  before first browser demand, and missed-event reconciliation;
- `/api/data` direct-GET freshness at today's age with no tab or stream, the connected five-second
  producer, and independent slow reconciliation;
- every time-derived field's retained inputs or measured recollection, and fixed-bucket sparkline
  sampling during an event burst;
- the complete revision pair on initial SSE connect, reconnect, leader handoff and server restart,
  including reset behavior and `Last-Event-ID` from the previous process;
- SSE keepalive, multiple tabs, leader failure/handoff, exactly one browser notification, common
  HTTP/1.x connection pressure, a stalled reader, queue collapse and stream/global caps;
- SSE clients and all observation workers disconnecting during shutdown;
- manual `/api/data`, `?all=1` polling and overlay compatibility;
- Windows `--no-usage` respawn, unconsented `/api/usage` discard, multi-tab consent broadcast and
  revocation, leader handoff, five quiet minutes reaching quota due, fetch completion publication,
  and consent expiry with no page;
- hook forwarding with no server, a wrong port, an authenticated discovered port, an impersonator,
  an unresponsive listener, deleted plugin runtime files with a surviving stable shim, one selected
  instance plus a scan-only second instance, the total hook deadline, and every supported OS;
- an event posted by a different OS user;
- hooks never returning an error that disturbs the reporting harness;
- bounded state under a long-running event stream;
- no worker starting in either daemon parent, exactly one service set in the foreground/final child,
  and deterministic shutdown order;
- `--no-events` disabling event ingress only, independent probe/stream gates, and
  `--legacy-polling` restoring today's memoized `/api/data` plus browser-poll path;
- direct launch on the documented Python floor with no third-party package.

## Feasibility assessment

| Outcome | Feasibility | Reason |
|---|---|---|
| Cheaper Claude collector at identical output | Done | All three fixes shipped in Phase 0 at 263 ms to about 100 ms warm; the membership cache passes the parked-parent and nested-workflow fixtures |
| Coarse stat-poll invalidation across all ten harnesses | Medium, pending Phase 0 | Stdlib and promising on one Mac, but mutation coverage and cross-platform cost are unproven |
| Materialized snapshot with SSE delivery | Medium to high | Fits the runtime, but needs a real coordinator, demand producer, restart cursor, server-wide resource limits and shutdown lifecycle |
| Event-triggered selective collection | Low value, gate failed | Per-harness invalidation saves 16% of a post-fix collection on the measured machine, under the 25% gate, so the coordinator runs one full aggregate per floor instead |
| Near-real-time Claude and Codex | Medium to high | Both plugin formats can bundle hooks; Cargento still needs authenticated routing, fixtures and its own lifecycle wiring |
| Near-real-time Antigravity | Medium to high | Hooks are bundleable and status line adds agent state and tool confirmation, but hooks are not clean turn boundaries and status line is opt-in |
| Near-real-time Gemini | Medium | The shipped extension can bundle hooks, but supported auth populations and event semantics need fixtures |
| Near-real-time coverage across all ten harnesses | Low to medium | Several adapters and passive topologies remain unproven; Cargento lacks artifacts for six even where upstream lifecycle support exists |
| Zero polling for every arbitrary external session | Not presently feasible | No universal observer protocol; events can be missed and time-derived state still needs deadlines |
| ACP-backed sessions launched by Cargento | Technically feasible | Standard event model, broad nominal harness support |
| ACP as a transparent universal replacement for collectors | Not feasible | Connection-scoped lifecycle and incomplete passive/global semantics |
| Native filesystem-event watcher | Poor fit | Three platform backends or a dependency, for precision the product does not need |

The likely experience is near-real-time rather than literally instantaneous, and the estimate below is
unmeasured. A matched semantic overlay can publish before the collection floor; a store-only event may
wait for that floor and store flush. A native hook, bounded loopback POST, short coalescing window,
collection, snapshot publication and SSE delivery should normally beat the current five-second
interval, but p95/p99 hook cost, store timing and harness behavior must be measured before setting any
public latency promise.

## Decisions to carry forward

- Do not rewrite the runtime merely to remove Python; the cost is one collector's algorithm, not the
  interpreter.
- Do fix that collector before changing any scheduling, since it changes every number in the argument.
  Done: Phase 0 landed the three fixes, and the numbers in the argument are the post-fix ones.
- Do not remove the existing collectors; they are the cross-harness historical and recovery layer.
- Do not adopt ACP as the core passive observation mechanism, and never require ACP for the ordinary
  dashboard.
- Do add a materialized snapshot, a revision pair that distinguishes restart, and SSE delivery. This is the
  highest-value change here and needs no events, no adapters and no envelope.
- Do use the coarse probe for latency only after per-harness mutation and cross-platform gates prove
  its coverage; keep current scans for every unproven source.
- Do add hooks for the needs-input semantics an mtime genuinely cannot express, starting with a
  harness for which Cargento already ships a plugin artifact.
- Do use plugin-bundled hooks where Cargento ships through the harness's plugin system, and treat
  every other adapter according to a harness-specific distribution and removal assessment.
- Do version the event envelope; it is a public compatibility surface the moment a third-party harness
  executes a Cargento hook.
- Do serialize collections through one coordinator, fence them with `arrival_seq` and dirty
  generations, and set overlay precedence per field and provenance rather than timestamp recency.
- Do normalize native session ids onto collector `sid`s, quarantine unmatched overlays without
  rendering them, and never let an overlay create or delete a row.
- Do treat native filesystem watchers and OTel as optional inputs, not foundations.
- Do retain full first-demand reconstruction and periodic reconciliation, and keep the current cadence
  for any harness without positive liveness and proven invalidation coverage.
- Do schedule time-derived state transitions only after retaining the inputs they need, and keep
  sparkline samples on a fixed cadence independent of event revisions.
- Do keep quota consent browser-originated, synchronized across tabs and separate from session
  refresh; no server timer may initiate a vendor fetch without a consenting request.
- Do make event health, acquisition quality, and ingress rejection counters visible in diagnostics.
- Do define `--no-events` accurately as disabling event ingress, keep independent stream/probe gates,
  and ship `--legacy-polling` for a real operational rollback to today's delivery path.
- Do require authenticated discovery and a per-run event capability; record the remaining shared-host
  read exposure and every new written path in `SECURITY.md`.
- Do install user-configured hooks through a stable shim outside removable plugin paths, with exact
  config ownership and uninstall semantics.
- Do start observation workers only after daemonization and join them deterministically.
- Do keep managed ACP and native-server sessions as a distinct future product mode.
