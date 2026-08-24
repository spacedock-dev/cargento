# Design: when a prompt outranks a busy session

Owner for the question "the agent is waiting on you, so why does the row say Working?". The module
map, including which file owns the collector and which owns hook classification, belongs to
[design-runtime-architecture.md](design-runtime-architecture.md); this document owns the precedence
call between a standing prompt and a session that looks busy, and it exists mainly to record the
attempts that did not work, because two of them were made and reverted before the third landed.

## N-1: there are three needs-input paths, and only one of them was broken

Worth establishing first, because the defect was originally filed as though there were one path and
it was dead. Three independent mechanisms can put a Claude row into Needs input:

| Path | Source | Covers |
|---|---|---|
| Transcript | a pending question found by reading the session's records | `AskUserQuestion`, `ExitPlanMode`, and only when the record has reached disk. See N-4 |
| Event overlay | the plugin-bundled `PermissionRequest` hook | `ExitPlanMode` observed directly (N-4). `AskUserQuestion` seen once in the wild, on the DRC-4097 incident row, which carried `acquisition: event`. Any other tool gate, and a subagent's, is **inferred** from the hook being tool-scoped and has not been seen |
| Notification | the user-installed `Notification` hook, posted to the loopback API | MCP elicitation dialogs, worker permission and network requests |

Codex has since become the second harness that can report a gate, and it has exactly one path: the
event overlay, from its own bundled `PermissionRequest` hook. It is not a fourth row in that table
because the table sorts Claude's three against each other, and a second harness with one source has
nothing to be sorted against. What the two share is the overlay mechanism, so N-5's ledger and N-9's stop handling apply to a
Codex row unchanged. N-6 is the exception and says so in its own section: its dispute ring only
watches a *collector* wait, so it cannot see a Codex gate in either direction. What they do not share is the other two
paths: Codex has no transcript detection and no Notification hook, which is why a Codex row can say a
gate is open and cannot say which. See N-7 for why that limit is a security decision rather than an
omission, and B2 in the tracker for the other eight harnesses.

The first two rows overlap, which is easy to miss and was missed here. `AskUserQuestion` and
`ExitPlanMode` are gated tools, so `PermissionRequest` fires for them like any other tool call, and
the event overlay carries them independently of whether the transcript ever shows them. An earlier
draft of this table listed those two under the transcript row alone, which read as though the event
path did not cover them. It does, and N-4 is the measurement.

The event overlay is the one that carries ordinary permission prompts, and its patch is written over
whatever the collector decided, so the collector's own ordering cannot suppress it. That is why the
symptom was narrower than it first read: the prompts that went missing were the ones with no
`PermissionRequest` behind them. `PermissionRequest` is tool-scoped, so an MCP elicitation, which is
a server asking the user rather than a tool being gated, raises only a notification. A worker's
request for network access is in the same position: it is a sandbox grant off a queue, not a tool
call.

## N-2: a live subagent used to mean Working, and it could not lapse

The collector resolved state in a fixed order: a pending question in the transcript, then a busy
test, then a standing hook. The busy test was two conditions joined by `or`, and they behave nothing
alike.

Fresh activity in the session's own transcript lapses on its own. An open prompt leaves that
transcript quiet, so a genuinely blocked session falls out of the window within
`working_threshold_sec` and its hook surfaces. Late, but not lost.

An earlier draft of this paragraph gave a mechanism for the quiet: that the `tool_use` record is
written before the prompt is raised and the `tool_result` only after it is answered. N-4 measured
that and it is not reliably true, since the record is sometimes not written at all while the gate
stands. The conclusion survives the correction because it only needs the transcript to be quiet, and
a record that was never written leaves it quieter still. The mechanism was wrong, the window still
lapses.

A live subagent never lapses. One running subagent held the row for as long as the workflow ran, so
a fan-out, the shape most likely to be holding a prompt in the first place, could not show one at
all. The two conditions had been written as if they were the same kind of evidence.

So they are now separated. Fresh own-transcript activity still outranks a hook. A live subagent
outranks only a hook this build does not recognise.

## N-3: recognised, not merely actionable

The ingress already classifies a notification before storing it, and an unknown structured type
fails visible: stored, popped, treated as needing input. That is the right default there, because a
notification type added upstream must not vanish.

It is the wrong test for precedence, and there is a measured reason. Claude Code advertises eight
`notification_type` values and its callers pass at least four more. One of the four is
`computer_use_enter`, whose message is "Claude is using your computer, press Esc to stop": a status
line, not a question. Under fail-visible alone an unknown type would have been allowed to override a
working row, which means the next status line Anthropic ships would paint a red band on a session
that is fine.

The predicate that gates precedence therefore asks whether the type is one this build names
actionable, not whether the ingress let it through. An unrecognised type keeps the old behaviour and
waits for the session to go quiet. Storing an unknown prompt costs nothing; letting it win a
precedence fight costs the credibility of the band, and a band that cries wolf is worse than no band,
because it teaches the reader to ignore the one signal the product exists to give.

A hook stored before the type was carried through has no type recorded at all, which reads as
unrecognised. That is the safe direction on an upgrade.

### Rejected

- **Reordering the whole chain so any hook beats the busy test.** Attempted and reverted. It breaks
  the background-task lifecycle test, which posts a permission-shaped message while background
  events flow and asserts the row holds at Working, poll after poll. That test is right: its hook
  carries no type, so it exercises the legacy text-matching path, and fresh own-transcript activity
  should still win there.
- **Gating on the type, but against both halves of the busy test.** Fixed the subagent case and
  still failed the same test, because it also overrode fresh activity. The freshness half was never
  the defect; it self-clears.
- **Clearing a wait whenever the row shows activity.** Rejected earlier for the event path and
  rejected again here. A row's activity is the maximum over its transcript, its task files and every
  child transcript, deliberately, so that a parent parked on a long workflow does not age out. Using
  it to clear a wait would clear a genuine block the moment a subagent wrote. A false clear is worse
  than a false block: it hides the thing the dashboard is for.
- **Treating an unknown type as non-actionable at the ingress instead.** This would fix the false
  band by dropping the notification entirely, and it trades a wrong colour for a missing prompt. The
  ingress and the precedence test want opposite defaults, which is why they are two decisions and not
  one.

## N-4: every path is probabilistic, so the docs rank them instead of trusting one

N-1 sorted the three paths by what they cover. This section sorts them by how often they actually
fire, which is a different question and was answered later, by holding real sessions at real gates
and reading both the transcript and `/api/data` while the question was still on screen.

| Path | Live gates seen on it | Breakdown |
|---|---|---|
| Transcript (`pending_input_tool`) | 3 of 6 | `ExitPlanMode` 2/4, `AskUserQuestion` 1/2 |
| Event overlay (`PermissionRequest`) | 4 of 5 | all `ExitPlanMode`; one miss read `working` with `acquisition: event` |

Both rows are Claude's, and there is no Codex equivalent. Its one path had not shipped when these
were taken, and a hit rate for it would need the same interactive method applied to a Codex session,
which nobody has run. So the ranking below is a Claude ranking; a Codex row's reliability is
unmeasured rather than assumed to match.

**These are observations, not a capture, and they are not auditable.** Claude Code 2.1.226 on macOS,
2026-08-12, driven interactively under `tmux` against a scratch workspace, reading the transcript and
`/api/data` while the pane still showed the gate. Nothing was recorded to `captures/`, so a reader
cannot re-derive these counts from this repository, and the directory's own rule is that a claim
marked measured should be able to show its measurement. This one cannot. Treat the table as a field
note. Turning it into evidence is DRC-4135.

The samples are also far too small to rank anything. Five and six trials, unevenly composed, with
some drawn from the same session, support exactly one conclusion: **both paths missed at least once,
so neither is a guarantee.** That both counts point the same way is a hint about which to prefer, not
a measured ordering, and the ranking `SKILL.md` gives readers is a judgement built on that hint plus
the mechanism, not a statistic.

The transcript case is the strange one. Claude Code does not write the `tool_use` record for an
input tool on a fixed schedule. Two consecutive questions in a single session, same version, same
prompt shape, behaved differently: the first had its record on disk with no matching `tool_result`
while the gate stood, and the second had no record at all after five minutes of waiting. That is not
a slow flush, it is a flush that had not been triggered. So the branch is neither dead nor live, it
is opportunistic, and it is documented that way rather than removed. Removing it would cost the one
population that has nothing else: a user running without the bundled hooks, for whom this is the only
needs-input source there is.

The event path's single miss is recorded as DRC-4134 and its cause is **not established**. All the
observation shows is `state: working` with `acquisition: event`, which proves some overlay patched
the row and nothing more. A `PermissionRequest` that never fired, never forwarded, or never
associated would look identical from outside, and so would a later working overlay retiring a wait
that did arrive.

Only the last of those resembles DRC-4095, and even there the resemblance is not a defect claim:
DRC-4095's fix makes a later working overlay retire an earlier wait **on purpose**, and its tests
pin that. So this is a miss in need of a mechanism, not a known bug of a known family. Attributing
it to one before tracing the overlay sequence is the same error this section is about.

### The methodology this cost us

A single live read is one coin toss, not a measurement. The first `ExitPlanMode` observation showed
the record present and detected, and stopping there would have produced a confident write-up saying
the transcript branch works. Three more trials made it 2 of 4. The same trap ran the other way on the
event path: one trial showed `working` at a live gate, which looked exactly like a released-version
regression worth an emergency release, and the next two showed `needs_input` and killed that reading.

The original report on this behavior measured it once and concluded the branch was dead. This
investigation measured it once and nearly concluded it was live. Both readings came from honest live
reads. Anything in this area needs n greater than one before it goes in writing, and the desk read
and the timestamp replay that the original report warned about are not the only ways to get it wrong.

## N-5: two different faults produce the same row, so the ledger is now readable

The event path's one miss (N-4, tracked as DRC-4134) could not be diagnosed from outside the
process, and the reason is worth stating in general terms because it will happen again. A row
reading `state: working` with `acquisition: event` at a live gate has at least two causes, and
`/api/data` shows the same three fields for both:

- a needs-input overlay exists but the reducer suppressed it, leaving the turn's working overlay as
  the last applicable writer;
- no needs-input overlay ever existed, because the hook did not fire, did not reach the server, or
  did not match a session key.

The fixes have nothing in common. The first is a reducer change; the second is a delivery problem
where changing the reducer would do nothing at all. Guessing between them was the mistake DRC-4134
was opened to stop, and the issue's own first draft guessed wrong: it proposed a `PostToolUse`
landing after the request and retiring the wait through `ENDS_A_WAIT`. `PostToolUse` maps to
`store_changed`, which produces no overlay, so it can never enter that set. Only `UserPromptSubmit`
and `Stop` end a wait by outranking it, and in an ordinary turn both arrive before the gate.
`SessionEnd` ends one too, by retiring the whole ledger for that session rather than by outranking
anything, and Claude fires it on `/clear`.

`GET /api/overlays` publishes the ledger the reducer reads: one row per live overlay, with its kind,
`arrival_seq`, timestamps, and `time_gate_open`, which is the overlay's own effective and expiry
window and nothing more.

### Reading it

Two causes is the short version, and the short version is the one that sends an investigator to the
wrong file. There are four readings, and the report carries what separates all of them:

| The ledger shows | The reading | Where the fault is |
|---|---|---|
| a needs-input overlay, `arrival_seq` above every working and idle row | the activity grace suppressed it (`events.py:525`) | the reducer's grace |
| a needs-input overlay, `arrival_seq` below a working or idle row | it was outranked and permanently superseded (`events.py:523`) | ordering, the DRC-4095 family |
| no needs-input overlay, and a counter moved | the envelope arrived and was dropped | ingress, not the reducer |
| no needs-input overlay, and no counter moved | nothing was ever posted | the hook, or the wire |

The bottom two rows are not decidable from a single read, because the counters are cumulative since
the process started: a lone `reject.rate: 3` says nothing about whether any of the three belong to
the gate in front of you. Read the report before reproducing and again after, and diff. The top two
are decidable from one read, with one caveat: a row only reflects an overlay once a collection has
run, so compare the report's `now` against `/api/data`'s `generated` before concluding anything
inside the collection floor.

The second row is why `arrival_seq` is published rather than implied by list order. Delivery is
at-least-once and may reorder, so a `turn_started` can land after the `input_requested` it precedes
in real time, and the result is a needs-input overlay that is present, inside its window, and skipped
anyway. Attributing that to the grace and going to change the grace is exactly the wrong-guess
failure DRC-4134 exists to stop.

The third row is why `counters` rides along. An envelope can arrive and still leave no overlay:
rate-limited (`reject.rate`), rejected at validation (`reject.unmappable-id` is the one that means
the id matched no session, and the other `reject.*` reasons cover a malformed, incompatible or
unknown event), refused at the session cap (`overlay.refused`), expired while waiting for a
collection to produce its row (`pending.expired`), or retired by a `session_ended`, which Claude
fires on `/clear` (`retired`). `pending_rows` names the sessions currently in that waiting state.
None of this is visible in `overlays`, because in every case there is nothing there to see.

A fifth thing the ledger cannot tell you: whether an overlay it shows actually won. `time_gate_open`
is the overlay's own gate only. The reducer's ordering and its activity guards both run afterwards,
and their inputs (`own_activity`, `last_activity`) live on the collected row, which is `/api/data`'s
to publish. Read the two together.

Three notes on its shape, each of which was a choice:

- **It publishes the inputs, not a verdict.** The reducer's activity guards read `own_activity` and
  `last_activity` off the collected row, which `/api/data` already carries. Recomputing the patch
  here would mean sampling a second collection and reporting a decision the server never actually
  made.
- **It is same-origin only**, unlike `/api/data`. `do_GET` relaxes its cross-site check so that a
  link to the dashboard opens. Nothing renders this route, so the relaxation has no reason to reach
  it.
- **No coordinator answers 503, not 404.** Under `--no-events` the route exists and the ledger does
  not. A 404 would read as a build too old to have the route, which is a bad thing to conclude while
  chasing a missing overlay.

### Rejected

- **A `debug=1` parameter on `/api/data`.** That response is a published snapshot, revision-
  qualified and shared between clients, and a per-request variant of it either doubles the snapshot
  keyspace or serves one caller's debug view to another. The ledger is a different object with a
  different lifetime, so it is a different route.
- **Logging the ledger on every collection.** It would answer the question after the fact, and only
  for whoever had the log level raised before the fault. Nothing rotates the log either, so a
  standing gate would write the same rows every few seconds for as long as it stood.

## N-6: the server records its own contradictions, because nobody else will

N-5 gave a person a way to read the ledger. It assumed the person knows to look, and that
assumption does not survive contact with the product: the dashboard exists so that nobody opens
every session, so a row wrongly reading Working is a row nobody visits. The one instance behind
DRC-4134 was found because somebody was deliberately holding a gate open under `tmux` while reading
the API. That is not a detector, it is a person, and it stops the moment they stop.

Nor is it recoverable afterwards. Overlays expire, the ledger is memory, and an hour later there is
nothing to read.

So the server records the disagreement itself. `Application._apply_overlays` already holds both
halves at the moment they conflict: the row a collector produced, and the patch the ledger reduced
to. When the collector says `needs_input` and the patch says `working` or `idle`, that is one source
of truth overruling another about the single fact the product exists to report, and it is written to
a bounded ring on `RuntimeState` with the ledger attached. `/api/overlays` serves it alongside the
live ledger, in the same response, because a dispute is read against the ledger and two requests
would be two instants.

The ring is a ring, unlike the ledger and pending caps, which refuse rather than evict. Those hold
live alerts, where dropping the oldest could drop a standing prompt. A dispute is evidence: losing
the oldest costs a sample, and refusing new ones would stop recording exactly when the fault got
worse. The running total is separate and never resets, so a machine can still report that this
happened sixty times after the ring has turned over four times.

### Reading what it collected

`GET /api/overlays` carries `dispute_total`, a count of episodes since the process started, and
`disputes`, the last `dispute_log_max` of them. For each record:

1. Walk its own `overlays` against the four-reading table above. The record carries `own_activity`,
   `last_activity` and the `activity_grace_sec` it was read against, so the first two readings are
   decidable from the record alone, without the live process and without `/api/data`.
2. For the second two, diff its `drop_counters` against the record before it. The live counters
   cannot do this job hours later, because they are cumulative and a single read cannot be
   bracketed; two consecutive records can, because each carries its own copy. Two things to know
   before reading that diff: the first record in the ring has no neighbour, so its counters are the
   totals since the process started rather than a delta, and the counters are process-wide, so the
   window between two records covers every session rather than the one the records are about.
3. `repeats` and `last_seen_at` say how long the episode stood, and what that means depends on which
   state overruled the wait. On an `idle` record it is the whole answer, since an idle overlay has no
   deadline and a long one is a stale overlay pinning a live wait. On a `working` record it can never
   exceed the working TTL, because a refreshed working overlay carries a new arrival sequence and
   therefore opens a new record. The signature to look for there is not one long record but a chain
   of consecutive records for the same session, each a fresh working overlay over the same standing
   wait.

### It is one direction, and it only ever watched the collector

Two scope limits, both easy to read past.

Zero disputes is not evidence of zero faults. This catches a contradiction the collector can see,
which means the collector has to have found the wait. Where a fault starves both paths at once, a
hook that never fired leaves the event path empty and the collector's own notification state unset,
so both halves say Working, they agree, and nothing is recorded. That case is real and is the fourth
reading in N-5.

Only the Claude *collector* ever produces a `needs_input` row, so no other harness can raise a
dispute, and a zero on a Codex machine is not a measurement. That sentence used to carry a second
clause saying this was correct rather than a gap because no other harness had a needs-input signal at
all. That is no longer true, and the correction matters more than the wording: Codex reports a gate,
but it reports it as an **overlay**, and this ledger only records a collector wait that an overlay
overruled. So the ledger is structurally blind to a Codex gate, in both directions at once.

Worse, the direction a Codex row can fail in is the one deliberately not recorded here. "It records,
it does not decide" below explains why the reverse case, an overlay wait wrongly standing over a
session that is generating, is left out: on Claude it is the ordinary event-ahead-of-scan path at
every permission prompt, and counting it would bury the case this ledger exists to find. For a
harness whose *only* path is the overlay, that ordinary case and the fault are the same shape, so
nothing separates them. A Codex gate that should have been retired and was not has no detector, and
adding one means the separate detector that paragraph already says this would need.

### Only one direction counts

A collector Idle row that an overlay promotes to Working is the ordinary path, and counting it would
bury the case worth finding under every ordinary one. So would a collector `needs_input` that an
overlay agrees with.

Both `working` and `idle` count as overruling a wait. Idle is as wrong as Working for a session
holding a question, and the idle dwell makes it the likelier of the two to arrive late.

### It records, it does not decide

The patch is applied either way, and the row still reads whatever the reducer said.

The tempting change is to let the collector's `needs_input` win, on the fail-visible principle N-3
applies to unrecognised notification types. It is not made here, and the reason is that DRC-4095 and
DRC-4097 are this same disagreement resolved the other way: a wait that should have been retired and
was not. Their fix is exactly that a later working overlay retires an earlier wait, and their tests
pin it. The two directions cannot both be loosened.

Which way to move is a question about how often each side is right, and nobody has that number. This
produces half of it: how often an overlay overrules a collected wait. The other half, how often an
overlay wait wrongly stands over a session that is generating, is deliberately not recorded here,
because that shape is the ordinary event-ahead-of-scan path at every permission prompt and counting
it would bury this one. It is DRC-4095 and DRC-4097 territory and would need its own detector.

Half a number is still the half that was missing, and it is the half this milestone is about.
Deciding first and measuring afterwards is how DRC-4134 got a mechanism that turned out to be
impossible.

## N-7: saying what it is waiting for, and why that is two changes rather than one

Knowing a session is blocked is worth less than knowing what it is blocked on. "Force push to main?"
is a decision a person can make from the board; "open question (AskUserQuestion)" is a reason to go
and look, which is the trip the row exists to save (DRC-4015).

The board note that opened that issue said this was pure rendering, over data already parsed. Half of
that was right and the half that was wrong is where the work is.

**The parse threw the text away.** A pending input tool was kept as `{name, ts}`, and the question
lives in the `tool_use` block's `input`, which was dropped on the floor. Summarising it at parse time
rather than keeping it raw is deliberate: `ExitPlanMode` carries a whole plan, sometimes thousands of
words, and a plan has no business in a session row or in the caches a row is built from. A plan is
reduced to its first line, which is its own title in practice. A question is the first question, with
a count of the rest.

**An agreeing overlay then blanked it anyway.** No overlay constructor sets `detail`, so every
needs-input patch carried None and `apply_patch` wrote that over whatever the collector had found.
The fix is narrow on purpose: the collector's detail survives only when the row was already Needs
input and stays Needs input, which is the case where the overlay agrees about the state and
contradicts nothing.

How often that erasure fired is **not measured**, and an earlier draft of this paragraph said it
happened on every default install, which the repository cannot support. It needs an `input_requested`
overlay, which only `PermissionRequest` mints. `captures/` now holds one Claude `PermissionRequest`
record, in `claude/notification-2.1.241-macos.jsonl`, and it is a single tool-permission prompt for
`NotebookEdit`. So the hook is observed firing for a tool gate. Whether it also fires for
`AskUserQuestion` and `ExitPlanMode` is still unobserved, and is an adapter claim of exactly the kind
this repository requires a capture for. Until there is one,
the honest statement is that the erasure is reachable and its frequency is unknown. The fix is
correct and costs nothing either way.

Working and Idle still clear the field, and that is not an oversight. A working detail such as
`running Bash` is true of a session that is running and false of one stopped at a gate, so it must
not follow the row into a wait. And a question that has been answered must not outlive the overlay
that retired the wait, which is exactly DRC-4095 and DRC-4097.

### What it deliberately does not do

The text still comes from the transcript alone, so it appears when the record has reached disk and
does not when it has not (N-4). The row says a question is open either way; it can only sometimes say
which. That is stated in `SKILL.md` rather than smoothed over, because a field that is usually there
teaches a reader to trust it and then fails silently on the sessions that matter.

There is a second window, and it is the ordinary one rather than the exotic one. For up to
`overlay_working_ttl_sec` after a turn starts, a live working overlay overrules the collector
outright: the row reads Working, the detail is cleared, and the question is invisible even when the
record is on disk and the parse has it. `_keep_wait_detail` cannot help there, because it only holds
when the patch agrees the row is waiting, and this patch says Working. That window is bounded, it is
the disagreement N-6's recorder exists to count, and it is the reason the sentence above applies to a
default install and not only to an unlucky flush.

Sourcing the text from the event path instead would make it reliable and is not a rendering change:
the envelope drops the tool name and the tool input at the hook, deliberately, and `SECURITY.md`
states that as a property. Reopening it is a security decision, not this one.

`notification_type` is present on every Notification payload. Its value list was read from the emit
sites in an installed 2.1.226 bundle, and three of the values the classification branches on are now
observed on the wire instead: `captures/claude/notification-2.1.241-macos.jsonl` holds
`permission_prompt`, `elicitation_dialog` and `idle_prompt`, each classified the way this build
already assumed. A plain main-session permission prompt carries **`permission_prompt`**, raised twice
from different tools, which closes the first of the two inferences below.

One inference is still open, and it is the one that matters to `worker_permission_prompt`: that a
worker's **network** request has no `PermissionRequest` behind it. The capture run could not produce a
`worker_permission_prompt` at all. A subagent driven to a tool outside the allow list surfaced a plain
`permission_prompt` on the leader's own session prefix, alongside a `PermissionRequest` carrying the
tool name, so the tool half demonstrably has both signals. That is consistent with the reasoning (the
emit site is tool-scoped) without testing the network half, which needs a worker network request that
is not allow-listed.

Two method notes, because both of them silently produced a run that looked like it worked and measured
nothing. A headless run auto-denies and never raises a prompt, so this needs an interactive session.
And a session that loads a user's own settings may be unable to raise a prompt either: a bare `allow`
list grants the common tools outright, and `--permission-mode default` overrides the *mode* and not
the *list*. Drive a tool the list does not name.

## N-8: the queue clears itself out of measurements, and holds no state of its own

The gates were on screen before they were a queue (DRC-4018). What B7 added was an order that means
something, a position, a handle, and a cursor. What it deliberately did not add is any record of
which gates you have dealt with.

That is the obvious feature and it was rejected. A "handled" mark would be the page asserting
something no collector measured: Cargento never writes to a session and cannot observe an answer, so
the mark could only record that a person clicked something. Two failure modes follow, and the second
is the serious one. A mark that is right is redundant: the session leaves `needs_input` within a
poll and the row goes on its own. A mark that is wrong **hides a gate that is still open**, which is
the exact failure the needs-input band exists to prevent, now caused by the surface built to prevent
it. The asymmetry decides it: the redundant case costs nothing and the wrong case costs everything.
One case escapes that argument rather than weakening it, and it is carved out at the end of this
section.

So the pass is driven entirely by the payload. You answer in the session's own terminal; the
collector stops calling that session blocked; the row leaves the queue on the next refresh. The
cursor is held as a session key rather than an index precisely so this works. `gateFocusKey()`
resolves a key that has left the queue to the current head instead of writing the fallback back, so
answering the row you are standing on advances the pass, and answering a row above the one you are
standing on does not slide the cursor onto a different session. A cursor held as an index would do
the second thing silently.

The same reasoning is why the queue's order is published by the server rather than derived in the
page. `row_order()` in `aggregate.py` ranks blocked rows by `blocked_since`; both views render that
order rather than each re-deriving it, so the band and the ledger cannot name a different gate at the
head. Calm's `attention` ordering ranks on the raw timestamp for the same reason, not on the elapsed
`waitSec` it displays: that value floors at zero, so two implausibly future stamps would tie in the
ledger while the server still separated them.

### What it deliberately does not do

It does not tell you how long answering will take, which gate is cheapest to clear, or which is most
urgent beyond how long it has waited. Waiting time is the only ranking signal the payload actually
carries; anything richer would be a guess dressed as an ordering.

### The carve-out: a question the session asked is answerable, because it is measured

The rejection above rests on one fact and not on a preference. A native gate is unanswerable here
because Cargento cannot observe the answer: it never writes to a session, so a mark could only record
that a person clicked something, which is the page asserting a state no collector measured. Every word
of that still holds for every gate on the needs-input band, and nothing about it is softened by what
follows.

The `ask_operator` lane (see [design-ask-lane.md](design-ask-lane.md)) is a different situation on
exactly the fact the argument turns on. There, the answer *is* measured. The session called the tool
and is holding the call open until an answer arrives, so the runtime is the thing the session is
waiting on rather than a bystander guessing at a terminal it cannot see. A click is not an assertion
about someone else's state; it is the state. The wrong-mark failure mode cannot occur either, because
there is no gate left open behind the click: the option the reader chose is what the tool returns.

The two therefore stay two surfaces, and the distinction is the load-bearing part. Asks render in
their own band from `d.asks`, and the needs-input band keeps no handled state of its own. A future
change that wants to mark a native gate has to overturn the paragraph above on its own merits, and
cannot borrow this carve-out to do it: an answer the runtime delivered and a click about a terminal
nobody read are not the same evidence.

## N-9: Idle was two situations, and only an event can separate them

Idle covered a turn that ended and nobody read the result, and a session still waiting on a reply
that never came. Nothing on a collected row separates them, because both are a transcript that
stopped changing. Only an observed `turn_stopped` does, so a row now carries `finished_at`, the stamp
of the last stop seen for it, and both views read the two apart instead of printing the one word.

The stamp is held outside the overlay ledger, and that is the one place this design departs from
N-5's rule that `session_ended` retires everything a session's events wrote. The coordinator keeps it
in a map of its own: `session_ended` pops the ledger whole, and for `claude -p` the stop and the exit
arrive back to back, so a mark kept in the ledger would be destroyed for exactly the sessions the
mark answers for. It is still reduced through `events.reduce_overlays` rather than written straight
onto the row, so it passes the same `session_activity` guard the idle overlay does and a session
resumed by a background task loses it. A working or waiting overlay clears it, and a collection that
stops producing the row is its only other bound, since no event ends it.

**The display threshold is measured, not inherited.** Across 10,119 returns to a stopped turn in
1,355 local Claude transcripts, half were answered inside 106 seconds and nine in ten inside 966, so
past 1,200 the odds are better than ten to one that nobody is coming back to that one soon. That is
the gate both views apply. `SKILL.md` states it in minutes, and a documentation test reads the
constant and requires the prose to agree, because otherwise the two can only match by accident.

### Rejected

- **Marking on the stop itself.** It puts the word on nearly every idle row within seconds, which is
  Idle restated in a second vocabulary: the fault the retired `stale` chip was dropped for. That
  chip's 7,200 seconds is twice the 97th percentile of these returns and was never re-argued, so it
  stayed silent through the whole window in which collecting the finished work is still worth
  something.
- **Narrowing what `session_ended` retires**, which would have let the mark live in the ledger after
  all. Claude fires that event on `/clear` as well as on exit (N-5), so a cleared session would read
  finished forever, which is DRC-4101's failure class by another door.
- **A third flag.** The two-flag cap is a shipped decision, and finished work is worth collecting
  rather than worth alarming about, so the word sits in the `idle / wait` cell and in the regular
  view's idle row. A chip would also pull the count into the flagged total, the `f` filter and the
  attention ordering, none of which should move because a turn ended tidily.
- **Letting a collector infer completion** for the six harnesses with no event adapter. A guessed
  completion renders identically to a measured one, so those rows disclose `scan-only` through
  `acquisition`, which was defined for this and rendered nowhere until now. A test holds the
  collectors to it.
