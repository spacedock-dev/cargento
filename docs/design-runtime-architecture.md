# Design: the modular dashboard runtime

Owner for how the dashboard's Python is arranged: which file owns what, which direction dependencies
run, and how one process's configuration, state and services are held. Other design documents own
their own subject and link here rather than repeating the module map.

The dashboard began as a single `server.py` of 7,357 lines. It is now a launcher of seven lines plus
an importable `cargento_runtime` package. This document records the arrangement and the reasoning, so
a later change either follows it or overturns it deliberately.

The materialized snapshot and the SSE stream have since landed as `snapshot.py` and `stream.py`, each
importing no runtime module so that `state` can own them without inverting R-2. `events.py` has landed
as the envelope and reducer layer beneath them, and `observation.py` as the coordinator that drives
it. The loopback ingress route and bundled event hook now feed that coordinator. The remaining
adapter and rollout work lives in
[`plans/event-driven-session-observation.md`](plans/event-driven-session-observation.md).

## The problem these decisions answer

One file that holds configuration, ten harness collectors, notification policy, HTTP handling,
process lifecycle and the frontend loader has no seams. Three specific costs made it worth fixing:

- Any change had to be reasoned about against everything else in the file.
- Tests reached for module globals, so a test's setup was coupled to the launcher rather than to the
  behaviour under test. Patching an alias did not necessarily patch the module that read it.
- Two dashboards could not run in one interpreter, because the caches, the notification state and the
  clock were process-wide.

## R-1: One responsibility per file, and the launcher owns none

`server.py` is the stable entry point every harness manifest names, so its content is a contract:

```python
#!/usr/bin/env python3
"""Launch the Cargento dashboard."""

from cargento_runtime.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
```

One import, one call, no re-exports. `LauncherContractTest` parses this file with `ast` and rejects
any `def`, `class` or assignment, and `runpy` executes it under `__main__` to prove the guard reaches
`cli.main` and exits with what it returned.

Everything else lives in one file per responsibility:

| Module | Owns |
|---|---|
| `config.py` | Immutable process configuration, store-root resolution, every tunable limit. |
| `state.py` | Mutable caches, locks, bounded-cache helpers, the server start stamp, and the runtime's published snapshot. Cache validity is not one rule. Of the eighteen caches, six turn on a file's `(mtime_ns, size)`: the four Claude and Codex title, user-event and instruction caches carry it in the value, and the Spacedock readme and entity caches carry it in the key. The other twelve do something else. `metadata_cache`, `cwd_cache`, `agent_class_cache` and `spacedock_role_cache` key on a path and never stat it, because each holds a fact that is fixed once the file has it. `spacedock_boot_cache` keys on a path and holds a scan position beside its records, because a first officer does not necessarily boot at session start (S-7). `claude_subagent_cache` keys on a session directory and turns on directory mtimes, since appending to a transcript moves no directory. `cursor_metadata_cache` turns on an `st_mtime` float across four derived keys per store. `pi_scan` and `turn_scan` hold an incremental scan position rather than a validity stamp. `usage_fetch_cache` and `usage_receipts` key on a vendor name and stamp the fetch time. `dispute_episodes` keys on `(harness, sid)`. Most are bounded at `max_cache_entries`; the two quota caches are bounded by the vendor list, and `dispute_episodes` by the sessions the current collection saw. The two instruction caches are honest about what they do not buy: the key moves on every event, so they never hit for a live session, and they exist for the idle and `?all=1` rows re-read on each refresh. |
| `snapshot.py` | The published response bytes per variant, and the restart-qualified revision that versions them. Imports no runtime module, which is what lets `state`, `aggregate` and `http_api` all depend on it without a cycle. |
| `stream.py` | Connected SSE clients and their one-slot revision mailboxes, with the connection budget. Imports no runtime module, for the same reason `snapshot.py` does not. `state` owns the registry because a connected stream belongs to the runtime, not to whichever object serves a request. |
| `asks.py` | Every outstanding `ask_operator` question and its one-slot answer mailbox, with the pending budget, the expiry sweep and the shutdown decline. Imports no runtime module, for the reason `stream.py` does not: `state` owns the registry because an outstanding question belongs to the runtime rather than to whichever request serves it, and a leaf is the only shape that lets `state`, `aggregate` and `http_api` all reach it without a cycle. It therefore cannot call `records.safe_text`, so every text bound is applied at the `http_api` ingress and it stores what it is handed. See [design-ask-lane.md](design-ask-lane.md). |
| `io.py` | Bounded file reads, safe globbing, read-only SQLite, the diagnostic sink. |
| `probe.py` | The coarse store probe: a bounded stat sweep answering whether anything on disk moved. Stat only, no globbing or reads, and a hint rather than authority. |
| `git_status.py` | The end-of-session git probe: one fixed argv, a porcelain entry count, and two scalars or `None`. A leaf: it imports no runtime module and holds no state, so the coordinator can call it off-thread without ordering concerns. Named `git_status.py` rather than `gitprobe.py` because `probe.py` above already owns "the coarse store probe", and two names a letter apart in one package is a reading hazard. Its bounds are a security contract, not a preference: see "Repository git reads (the end-of-session probe)" in [SECURITY.md](../SECURITY.md). |
| `observation.py` | The event coordinator, and the only module that owns a long-lived one. It starts the collection worker and, on a session end, one short-lived git probe thread; `quota.py`, `http_api.py` and `lifecycle.py` each start one of their own for a single task. Owns the bounded overlay ledger and pending map, the per-session completion marks it holds outside that ledger (N-9 in [design-needs-input.md](design-needs-input.md)), the dirty generations, the end-of-session git readings it holds outside that ledger for the same reason and retires on the same edges, one collection lane, the collection floor, the coalescing window, probe-gated periodic ticks, the reconciliation interval and deterministic shutdown. The git probe is dispatched from here and deliberately runs neither on the event-ingress thread nor under the coordinator lock: that edge arrives on an HTTP handler thread behind the hook client's two-second timeout, so an inline probe would stall every other event and time out the harness's own session-end hook. It also holds the one seam an outstanding question uses to demand a collection, because a question that nothing collects is a question that never renders and never expires: see A-3 in [design-ask-lane.md](design-ask-lane.md). Constructed inert so a coordinator built before the daemon fork is never inherited half-running; `lifecycle.serve` starts it after the last fork. |
| `events.py` | The untrusted event envelope: its accepted version range, its vocabulary, per-harness identity normalization onto the collector's key, the mapping from event to overlay, and the reducer that turns live overlays into a field patch. Pure by design, so ordering and precedence are testable without a server: no locks, no counters, no clock and no filesystem. The mutable pending map and overlay ledger belong to the coordinator that bounds them, not here. |
| `records.py` | Parsing and normalizing untrusted records from disk, and the one place the repo-wide ISO-8601 rule lives: `iso_epoch` decides that an **offset-less stamp means UTC**, and the transcript, SQLite, quota and event readers all defer to it. That rule was four separate copies until two of them disagreed, so it is stated once here and imported rather than reimplemented. It also holds the scanner's harness-gated record signals: `model_signal` reads the model a Codex `turn_context` record declares, `usage_signal` reads output tokens from a Claude assistant record, and `tool_outcome` reads the tool a Claude record calls and whether it came back an error. `scan_turns` runs over five harnesses' transcripts, so every signal refuses a record from the wrong harness rather than turning a shared type or shape into a false measurement. The same gating shapes `injected_prompt`, which answers whether a user record is the harness talking (a skill body, hook feedback, a compaction summary) rather than the operator: Codex names its wrappers with underscores and Claude with hyphens, only five names are common to both, so there are two measured lists and an unmeasured harness gets their union. Beside it, `harness_control` answers the narrower question of whether a RENDERED directive drives the harness rather than the work (`/clear`, `/login`), and it lives here rather than in either caller because `observer.py`'s goal slot and the instruction line beneath a session title publish the same reading of the same directive; two lists would be two chances to disagree. `instruction_line` bounds a published line at the cap plus one, because `transcripts.clip` appends its ellipsis after cutting and a scrub at the cap takes the marker back off. `redact_secrets` sits beside them and is the one place credential shapes are named: it is called from `safe_text`, so nearly every published string is covered by passing through the bound it already had; from `redact_clip`, which is redact-then-bound in that order for the collectors that slice `title` and `last_prompt` out of a record by hand; and from `aggregate` over the assembled rows, as a backstop under both. Its shape list carries per-shape corpus counts the way `injected_prompt` above does, and [`design-credential-redaction.md`](design-credential-redaction.md) carries the measurement and the rejected alternatives. `strip_prompt_wrappers` peels the image markers first, because those envelope a real prompt rather than replacing one, and the slash-command wrappers (`<command-message>`, `<command-name>`, `<command-args>`) are absent from both lists for the same reason: a slash command is the operator's intent spelled in harness markup, and `transcripts.prompt_title` already owns reading it back out, so the two primitives agree about one record instead of contradicting each other. |
| `sessions.py` | Session identity and shape, freshness, display ids, deterministic aggregation. The row's declared field set is `base_session`, and three contracts hang off it: `MODEL_CAP_CHARS`, the width every collector bounds a published model to, `TOOL_NAME_CAP_CHARS`, the wider width a published tool name gets, and the `subagents` element shape, `{"name": str, "model": str \| None, "started_at": float \| None}` with both measurement keys always present. `instruction` is declared there too, as a label, a text and a stamp or None, rather than folded into `last_prompt`: that field is read at ten render sites and two of them are not the session card, so a labelled line packed into it would leak onto the projects list and the calm view with no label to explain it. |
| `transcripts.py` | Shared metadata readers, prompt titles, the non-Claude analyzers, and the instruction line beneath a session title. `codex_instruction` walks a rollout backward for its newest genuine prompt, because a bounded tail read misses that prompt on 62% of the rollouts that carry one, and `instruction_from` turns the candidates into the one labelled line both harnesses publish. `states_work` is the pairing rule for `records.bare_continuation`, and it reads two different things off one prompt: the RENDERING decides the shape, since a slash command is sixty characters of markup that reads back as a five-word instruction, and the tag-stripped BODY decides the word count, since `prompt_title` returns line 1 only and counting there called 97 of 2,066 local newest prompts bare over a real instruction. The preamble it pairs with is bounded structurally rather than by the turn floor alone: only a record newer than the newest genuine prompt can supply one, because reaching a `task_started` proves that some turn opened and not that this one did. `codex_plan` is a second backward walk over the same file for a different record, and it has its own cache entry because the two stop in different places: it reads the newest `update_plan` and publishes it as the session's task rows. It reads both live wire shapes, since a Codex build writes one or the other and a single-shape reader reports an empty plan on the other one: across 487 local rollouts the `function_call` shape accounts for 279 plan records and the `exec` shape, which carries the plan as JavaScript source rather than JSON, for 211. All 490 parse, including the 6 that bind the array to a variable before the call, which is why the array is located directly instead of through the `update_plan(` call site. The JS rewrite is a string-aware scan and not a set of substitutions, because a step reading `Recce Task 7: full Recce verification` is ordinary and a naive rewrite corrupts exactly that. Unlike the prompt walk it crosses a compaction boundary: a compaction disowns an older prompt, but the plan is state the CLI keeps rendering, and stopping there would blank the panel for the long sessions the field exists to make legible. |
| `turns.py` | Generic incremental turn scanning and turn display, including the model a Codex rollout declares, the run of failed tool calls inside the current turn (Claude only: `records.tool_outcome` is where that gate lives), output-token totals, and a transcript's first timestamp. The scan state carries `first_ts` and `scanned_from_zero`; crossing the unscanned-delta budget makes the latter false for that entry, so a bounded tail or rebuilt oversized entry can never publish its later first record as the session start or a partial lifetime token total. The current-turn total has a separate completeness guard and stays withheld until the forward scan observes that turn's opening boundary. The model and loop readings still use the backward context pass, while the start and token totals deliberately do not. |
| `claude_data.py` | Claude transcript reads shared by the collector and the hook path, including the model a session ran on and the one each of its sidechain children ran on, kept apart because the `isSidechain` flag inverts between the two. It also reads a child's first bounded JSON record for its start stamp; mtime remains last activity and never substitutes for a start. `session_instruction` is the Claude half of the instruction line, walking backward beside `session_title` because that title is generated once from the opening prompt and never refreshed. |
| `spacedock.py` | Spacedock workflow and entity cartography. `tool_result_text` is the provenance gate the whole read surface rests on: a boot envelope counts only when it arrives as command output, and it does that in three transcript shapes, one per harness. Codex's is a `function_call_output` or `custom_tool_call_output` payload, which is why it was missing for so long; see [`design-spacedock.md`](design-spacedock.md) decision S-6 for the measured payload shapes and what accepting a `function_call`'s arguments instead would have cost. Provenance settles where an envelope may come from, not what it looks like there: S-7 records that no real session pastes the raw JSON, so the envelope is also read as the key/value rendering a session printed, under the same `command: boot` gate and the same downstream guards. |
| `observer.py` | The on-demand observer: goal, current stage and one open block for one named session, written to a sidecar under `~/.cargento/observer/`. A reader above `spacedock` and `transcripts` rather than beside the collectors, because it answers about one session a person asked about and a collector answers about every session there is. It derives, it does not summarize: the stage comes back through `read_entities`, so the freshness window and the declared-stage discriminator the project-read contract rests on both apply, and `--no-spacedock` withdraws that half exactly as it withdraws a strip. The transcript half reads three record shapes, not one: a nested `message.role` under `type: "message"` (Pi and Droid), `type: "user"`/`"assistant"` (Claude), and a `message` payload under `type: "response_item"` (Codex). The union is additive and takes no `harness` argument, because the three are disjoint across the whole local corpus and the caller has already resolved one file for one requested harness. It could not ship without `records.injected_prompt`, which every user record now goes through: the parser alone published a harness-injected shape as the goal on 51.2% of 457 Codex rollouts and 61.8% of a seeded 400-transcript Claude sample, which is a confident wrong answer in place of the silent one the unfixed parser gave. What survives is rendered by `transcripts.prompt_title`, so a slash command, the one shape that predicate deliberately admits, reads as `/name args` rather than as its wrapper. Sidechain records are excluded on the Claude arm, since a subagent's prompt is its parent's dispatch and not the operator's, and the Codex path excludes the same thing one level up: a subagent thread writes its own rollout under its PARENT's session id, so the transcript resolver drops subagent rollouts before it picks the newest file, the order `collectors/codex.py` already does it in. Two directives are refused rather than published: a generic skill-load opener, read on the raw text, and a bare harness-control slash command (`/clear`, `/login`, `/plugin`), read on what `prompt_title` renders, since the raw and rendered spellings of the same record never meet. The control list lives in `records.harness_control`, shared with the instruction line beneath a session title so the two surfaces cannot disagree about whether `/clear` is an objective, and it is measured names and not the structural rule "a bare command has no arguments, so it has no goal": a skill invoked with no arguments is an objective, and 39 local goals are exactly that. Refusing a directive leaves the one beneath it standing, so a `/clear` typed after real work does not erase it. The head and tail windows are cut apart on byte offsets rather than concatenated and deduped, because the two overlap on any file smaller than their sum and the dedup key falls back to the message text on the 76.4% of Codex user records carrying no `payload.id`, which dropped a verbatim-repeated prompt as a duplicate of its own first occurrence. Disjoint windows make that fallback positional, and the key is left to do the one job it is good at: collapsing a resumed transcript's replayed block, which carries its original ids. The block half is a keyword scan over the newest assistant message only, and the table is self-state phrases rather than bare words, with a trailing word-boundary test so `waiting for you` stops matching `waiting for your`: on the whole local Claude corpus the bare forms produced 7 blocks of which 4 sat in a quoted or fenced span, two of them clipped so the card showed no block language at all. A false block is the one field on the panel a reader would act on, so precision wins over recall by construction. |
| `quota.py` | Quota acquisition: the per-vendor credential reads and outbound requests, the receipts a harness pushes in, and the shared cache with its per-vendor floor. The whole outbound network surface (see [design-usage-quota.md](design-usage-quota.md)). |
| `dismissals.py` | The sessions the reader marked handled: the store's path, its bounded read and write, and the rule that decides when a mark lapses. The only module that writes user-authored state, and a leaf beside `records` for that reason: `aggregate` subtracts through it before `summary` is counted, `notifications` gates a popup on it, and `http_api` mutates it, and none of those three could depend on it if it depended on any of them. See [design-dismissals.md](design-dismissals.md). |
| `notifications.py` | Hook state, popup policy for both lanes (needs-input and ask), the native notifier, hook payload handling. |
| `collectors/*.py` | One harness each: a discovery predicate and a collector. Two of them, Cursor and Antigravity, reach a value through a bounded read inside a stored blob rather than off a column, and both bound the read in SQLite (`substr`) so the whole blob is never materialized. |
| `aggregate.py` | `HarnessSpec`, the registry and its label lookup, the per-harness failure boundary, and `Application`, including the one place a needs-input popup is decided: after the overlays have been reduced onto a row and before a dismissed row is subtracted (R-5). |
| `diagnostics.py` | Store-path reporting for `--diagnose`. |
| `http_api.py` | The loopback server, its request handler, and network helpers. |
| `lifecycle.py` | State file, port probes, status, stop, and daemon detach. |
| `cli.py` | Argument parsing, runtime assembly, and the three serve branches. |
| `web/page.py` | Package-relative frontend loading, the ordered `APP_PARTS` and `NEXT_PARTS` script lists, validation and data-URL embedding of the opt-in page's packaged fonts, and byte-preserving assembly of the default and opt-in pages. |

The existing dashboard script is the same kind of split, applied to the frontend once it crossed the same
threshold the Python did: over a thousand lines holding more than one responsibility. The parts are
plain concatenated script, not modules: `page.py` joins them in `APP_PARTS` order into the page's
single script slot, so they share one scope and order carries meaning. Shared state and the
component tables come before the listeners and the render loop that read them. The cut points are
the file's own section seams, taken as contiguous byte-exact slices, which made the refactor
self-proving: the assembled page hash in `test_page.py` did not change.

| Frontend file | Owns |
|---|---|
| `web/spark.js` | Shared page state, rate buffers, the sparkline with its hover machinery, and the four rules both views read: the waiting queue (the gate filter, the ask key, and the merge that puts one order over both), how any cursor resolves against what is drawn, the attention ordering (its key, its comparators, and the sort the card view applies), and the shared-project-label collision, with the one wording every surface that marks it prints. |
| `web/regular.js` | Regular-mode components: badges, the harness strip, tiles, Spacedock strips, cards, rows, and the waiting band both views draw, with its cursor and what `⏎` does on each kind of row. |
| `web/mode.js` | Display-mode state and its switch, the session view's target and its `#session=<key>` hash router. LocalStorage holds which mode and the hash holds which session, so the view survives a reload and answers browser back/forward. It also owns the calm ledger's mutable state (sort, filters, open row, cursor, scroll). |
| `web/usage.js` | The usage band, the configure popover, and the quota disclosure banner. |
| `web/controls.js` | The stop control, the stopped panel, and the mode bar. |
| `web/ask.js` | The question card: one per outstanding `ask_operator` question, and the answer POST behind its option buttons. A card in the queue band rather than a synthetic row in `d.sessions`, for the reason [design-ask-lane.md](design-ask-lane.md) records. |
| `web/calm.js` | The calm ledger: tone tables, actions, document listeners, and renderers. The click and keydown listeners are the page's, not calm's: all three modes route their controls through them. |
| `web/session.js` | The session view: one session's Spacedock dispatch tree, its goal line, the picker, and the four empty states. It renders from the same `/api/data` payload as the other two modes and has no endpoint or collector of its own. |
| `web/observer.js` | The observer panel: the fetch behind a row's `observe` control, and the goal / stage / block card it renders from the sidecar that comes back. |
| `web/notify.js` | Desktop notifications. |
| `web/main.js` | `render()` and `refresh()`. |
| `web/live.js` | Leader election across tabs, the SSE stream, and the fallback poll. |
| `web/next/index.html` | The two-slot shell for the opt-in page. It is assembled independently of `web/index.html`. |
| `web/next/styles.css` | The next page's light-root token copy, system dark override, live-dot pulse and reduced-motion override. It never extends the byte-pinned default stylesheet. |
| `web/next/next-boot.js` | Query reads, HTML escaping, shared payload-number and time helpers, harness labels, session attention ordering and metrics, status dots, first-seen project groups and the next page's fragment route. It is first in `NEXT_PARTS`; its grammar is owned by [design-next-ui.md](design-next-ui.md). |
| `web/next/next-chrome.js` | Breadcrumbs, header counts, the overview tab shell, route controls and the one delegated keyboard listener. The selected tab asks the view dispatcher for its body. |
| `web/next/next-sessions.js` | The sessions overview table: the untouched gate queue, the shared working attention ladder, active-row live dots, the nearest-idle tail, measured activity and rate phrases, the all-state shared-label caveat, and each row's project-plus-full-session route. |
| `web/next/next-projects.js` | The projects overview table: first-seen project-label groups, measured task progress and current state, explicit estimate and delegation withholding, and the all-state shared-label caveat. |
| `web/next/next-project.js` | The project detail header, same-workflow plan merge, ordered entity rows, three Spacedock empty states, and the main-column and rail section layout. |
| `web/next/next-activity.js` | The project GOING ON cards and DONE list: current-payload session ordering, observed-live treatment, session routes, Claude completed-task provenance and both explicit empty states. |
| `web/next/next-session.js` | The bounded session detail: exact route and ask attribution, last-instruction header, optional measured metadata, pulsing fresh subagents, token footer, and the existing answer POST. |
| `web/next/next-workstream.js` | The bounded in-tab observation ledger, per-payload session samples, project workstream rail, honest retained-window label and namespaced collapse preference. |
| `web/next/next-delegation.js` | The project rail's windowed delegation percentage, delegated token-rate aggregate, human-turn count, evidence floor and two-window trend gate. |
| `web/next/next-controls.js` | The project rail's local-only steer receipt and namespaced guardrail preferences, including their storage and escaping boundaries. |
| `web/next/next-render.js` | The next page's overview, project and session dispatchers, payload fetch and failure state. Transport startup is kept out so every renderer exists before the final part runs. |
| `web/next/next-live.js` | Namespaced cross-tab leader election, SSE revision delivery and the fallback poll. It is last in `NEXT_PARTS` and starts the next page's refresh loop. |

`NEXT_PARTS` is a second concatenated scope, not an extension of `APP_PARTS`. The HTTP server selects
its assembled bytes only when the first `next` query value is exactly `true`. The reason for that
seam, its shared-origin firewall, and the rollback path live in
[design-next-ui.md](design-next-ui.md).

## R-2: Dependencies run inward, and the test enforces it

Lower layers never import higher ones. `config` imports no runtime module at all; `cli` may import
any, because it is the assembly point.

`test_runtime_import_graph_matches_the_reviewed_allowlist` parses every runtime file with `ast`,
normalizes each import to a top-level runtime module, and compares the result to an explicit
allowlist. Two rules matter more than the table:

- A collector may not import another collector, or `aggregate`. Collectors take `Session` from
  `sessions.py`. Ten independent files each testable alone is the property that makes adding a
  harness cheap.
- `TYPE_CHECKING` imports count. A dependency that exists only for annotations is still a dependency
  a reader has to follow, and exempting it would make the allowlist describe less than the truth.

The allowlist changes only in a PR that makes a reviewed ownership decision, never to make the test
pass. Two edges arrived that way with the per-session model. `claude_data` gained `sessions`, and
`collectors/cursor` gained `records`, because each bounds a model string through `records.safe_text`
at the width `sessions.MODEL_CAP_CHARS` declares. Neither is a layering break: `sessions` imports
nothing from inside the package, and every collector already depends on it. The alternative was a
second literal 40 beside the declared one, which is how two caps drift apart.

A third arrived with the credential filter. `aggregate` gained `records`, because several published
strings do not reach `records.safe_text` on the way out: nine collectors build `title`,
`last_prompt`, `state_detail` and a subagent name out of the transcript by hand and bound them with a
slice. Codex is the exception and was described as though it were not: its title and prompt come
from `transcripts.codex_instruction`, which bounds both through `safe_text` like everything else.
Aggregate is the one place that holds every row from every harness before any of it is published, so
the sweep runs there rather than in ten collectors and whichever one is added next. `records` is a
leaf, so the edge points inward like the other two.

`collectors.claude` and `collectors.droid` gained the same edge later, and for the ordering rather
than the coverage: the sweep above cannot repair a shape the slice has already cut short, so the
redaction has to run before the bound at each of those sites. `records.redact_clip` is the one place
that order is written down. See
[`design-credential-redaction.md`](design-credential-redaction.md).

## R-3: The runtime package is imported by its top-level name

`cargento_runtime.io`, never `cargento.skills.cargento.cargento_runtime.io`. Two spellings would give
every module two identities in `sys.modules`, and therefore two copies of every cache and lock: a
write through one spelling would be invisible through the other. The validator rejects the
namespace-qualified form in any runtime file, and a contract test asserts the qualified package never
appears in `sys.modules`.

Frontend assets load relative to `web/page.py`, so an installed copy needs no repository and no
working directory. A contract test walks the package with `pkgutil` from an unrelated directory, with
`PYTHONPATH` removed and `PYTHONNOUSERSITE=1`, and proves every module's `__file__` and every declared
asset path, including the opt-in page's font subsets, resolve inside the skill directory. It
inspects every module it finds rather than a maintained list.

## R-4: Configuration is frozen, state is mutable, services are injected

Three objects, with deliberately different lifetimes:

- **`RuntimeConfig`** is a frozen dataclass built once at the process boundary. It carries the
  resolved store roots, the platform and OS names, the state home, and every limit and threshold.
  Nothing downstream reads the environment, `sys.platform`, or `os.name`.
- **`RuntimeState`** holds what genuinely changes: bounded caches, scanner offsets, locks, hook and
  popup state, the collection memo, and the start stamp.
- **`Application`** binds one config and one state to injected services: the native notifier, the
  popup notifier, the diagnostic sink, and the clock. It owns the registry and the per-harness
  failure boundary, so one broken store cannot take the dashboard down.

`CargentoHTTPServer` stores exactly one `Application`, the mandatory assembled default page, and an
optional assembled next page. Its handler reads all three off the server instance. `cli.main` is the
only place that assembles them. A default-page load failure is fatal before bind. A next-page load
failure is reported but leaves the default page serving, with only `?next=true` returning 503.

The payoff is testability of the awkward cases. Platform decisions take their environment as an
argument (see D-4 in [design-cross-platform.md](design-cross-platform.md)), so one runner exercises
the Linux, macOS and Windows branches. And two servers can run in one interpreter without crossing: a
contract test proves `/`, `/api/data`, `/api/health`, `/api/overlays` and notification POSTs each
answer only for their owner, including that a `SessionEnd` on one leaves the other's standing hook and
generation untouched, and that an event submitted to one server's coordinator stays out of the other's
ledger.

`RuntimeConfig` carries `state_home` as a string alongside `state_dir` as a `Path`, because a native
`Path` rewrites separators on Windows: an override of `C:/plugin/state` would come back as
`C:\plugin\state`, a different string in `--status` output and in the dirname contract lifecycle
relies on.

## R-5: The registry is data, and no collector notifies

`aggregate.default_harnesses()` returns ten `HarnessSpec` rows in display order, which is also
collection order and the order the page renders its harness chips. Each row names a collector
module's `discover` and `collect`, and nothing else.

`Collector` is one contract for all ten: `(config, state, now, window_hours, show_all)`. A collector
reads a store and returns rows. It does not decide whether the human should be interrupted, because
it cannot: by the time a row is final, two more things have happened to it. The live event overlays
have been reduced onto it, and the reader's dismissals have not yet been subtracted. `Application`
is where both of those are known, so `Application.collect` walks the rows once, after
`_apply_overlays` and before the subtraction, and asks `notifications.maybe_popup` about each. `cli`
passes the same notifier to `Application.popup_notifier` that the hook route uses, so the transcript
path and the hook path cannot diverge.

This overturns an earlier decision, and the reason is worth keeping. Claude's collector used to
raise the popup itself, and `default_harnesses` took a notifier to bind that one row. The argument
was that a transcript-detected transition has no HTTP request behind it, and that widening the
contract for all ten to serve one was the worse trade. It was, until DRC-4184 gave a second harness
a gate: `maybe_popup` had exactly one production caller, so on macOS, where `native_notifier` names
a backend and the browser layer therefore stands down, a Codex session at a real permission prompt
alerted nobody at all. The premise the one-layer split rests on, that the server already fired for
whatever the page declined to, was true of Claude and of nothing else. Binding a second collector,
and then a third, would have restated the same defect once per harness. Moving the decision up also
closed a second silence that was true even for Claude: the popup read the collector's state, and
`_apply_overlays` runs afterwards, so a wait that only an event knew about raised nothing.

One property of `maybe_popup` survived the move unchanged and must keep surviving it: its
`expect_generation` is re-checked under `hook_lock`, so `Application` samples every session's
generation before the harness loop and hands that snapshot in: reading the live map at decision time
would compare a value with itself and let a `SessionEnd` that committed mid-collection be undone by
a popup for a session that has exited.

A second property had to change with the move. The transition is recorded into `last_session_state`
*above* the cooldown gates, so a popup the machine-wide floor suppressed used to be consumed rather
than deferred: every later collection then failed the edge test, and that gate was silent for as
long as it stood. That was survivable while Claude's collector was the only caller and only Claude
rows wrote the floor. It is not survivable with ten harnesses contending for it: the first gate of
a collection would permanently eat any other opened within 15s, and registry order decides which
harness systematically loses. So a transition held by the floor alone is now left unrecorded and
retried on the next collection. `popup_cooldown_sec`, the per-session re-emission floor, still
consumes: retrying past it would re-pop the same standing gate every minute. The ask lane keeps its
own floor key either way (D-3 in [design-cross-platform.md](design-cross-platform.md)).

Adding a harness is therefore: a module under `collectors/`, and a row. `CONTRIBUTING.md` owns the
walkthrough, and [design-harness-registry.md](design-harness-registry.md) owns the judgement of what
earns a row of its own, including the one time that judgement had to be revisited.

## R-6: The three serve branches stay distinct

There is deliberately no generic "bind before detach" rule, because the three paths differ in what
owns the bind:

1. **Windows daemon parent** validates its state home and log, re-spawns a foreground child, and
   awaits that child's pid. It never constructs a server: the child owns the bind, and therefore owns
   reporting a bind failure. A test substitutes the server constructor with a failure and proves the
   parent never reaches it.
2. **POSIX daemon** binds in the attached process, then forks. Binding first is what lets a busy port
   explain itself on the terminal that asked, rather than in a log file nobody has been told about.
3. **Foreground** binds, records state, and serves in the same process.

`cli.main` returns exit codes rather than raising, except where argparse owns `SystemExit` for
`--help` and its own usage errors. That is why `lifecycle.prepare_daemon_home` reports whether the
home is usable instead of raising.

All three branches assemble the coordinator without starting it, and `serve` starts it. That is the
whole reason `Observation.__init__` spawns nothing: on the POSIX daemon path the process that
assembles is not the process that serves, and a thread created before the fork is either lost with the
parent or inherited into a child that never asked for it. `serve` runs the coordinator or the older
fixed-interval producer, never both, so two things can never collect at once; a server assembled
without a coordinator, which is what `--no-events` and most test doubles are, gets the producer.

## Rejected alternatives worth keeping rejected

### One large package-first change

A single move would have combined module identity changes, hundreds of patch-site updates, asset
loading, CI discovery, packaging validation and daemon imports. A failure would have been hard to
locate, and review would have mixed moved code with changed behaviour. The work went out as
sequential behaviour-preserving PRs instead, each with its own gate.

### Splitting only tests and frontend assets

Quick context-size relief, but it leaves roughly 5,800 lines of unrelated Python in `server.py` and
postpones the dependency problem entirely.

### A permanent `server.py` re-export facade

Re-exporting every constant and function would have kept tests coupled to the launcher, and patching
an alias does not necessarily patch the module that reads the value, which is the exact failure the
split was meant to remove. The facade would have become a second mutable API and an invitation to import
cycles. A transitional facade did exist *during* the split and was deleted with the last extraction;
that was scaffolding, not a design.

### Hard line-count enforcement

A numeric gate rewards artificial fragmentation and wrapper files. Responsibility and dependency
direction are the architectural checks; line count is a review signal. Review a module over about
1,000 lines by hand, and split it only if it holds more than one responsibility.

### Deriving the shipped-file inventory from a glob

`CARGENTO_RUNTIME_FILES` in `scripts/validate_plugins.py` is an explicit tuple. A glob would describe
whatever happens to be present and could never notice an omission, which is the only thing the check
exists to catch. The cost is that the list can fall behind, so a test compares it against what the
checkout actually ships.

## Testing strategy

Three layers, described in `CONTRIBUTING.md`. Two habits specific to this architecture:

- Prefer pure functions that take their environment as an argument. It is what keeps a new platform
  branch from being dead code on the runner that gates the merge.
- Mutation-check a new contract before trusting it. Across this split, mutation testing found real
  gaps in behaviours the plan explicitly required preserved, including both popup cooldown floors,
  the clearing of `store_errors` before a diagnosis, and whether the registry's Claude row notified
  through the notifier it was handed. Each had passed a full green suite.
