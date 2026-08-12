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

## What is still not measured

`notification_type` is present on every Notification payload, and its value list was read from the
emit sites in an installed 2.1.226 bundle rather than observed on the wire. No capture in
`captures/` holds a `Notification` record, because a headless run auto-denies and never raises one,
so getting one needs an interactive session. Two specific values are inferred rather than seen: which
one a plain main-session permission prompt carries, and that a worker's network request has no
`PermissionRequest` behind it.
