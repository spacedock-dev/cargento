# next-UI v2 — the derivation interface

Transient. Delete this file with
[the shared contract](next-ui-v2-contract.md) when the refactor ships.

Workstream A implements this. Workstreams B–E build against it without waiting for
A to finish. **It is frozen.** If A finds it cannot be implemented against the real
payload, A reports to the coordinator and the coordinator amends this file — A does
not quietly change the shape, because four other sessions are already writing code
against it.

One function, in `web/next-observed.js`, placed in `APP_PARTS` directly after
`next-boot.js` so every consumer sees it:

```js
nextObserved(payload) -> model
```

It is pure: same payload in, same model out, no reads of `nextData`, no DOM, no
storage, no clock beyond `payload.generated`.

## The absence convention

This is the whole point of the module. **A view never sees `null`.**

Every field that can be absent is derived as a pair:

- `<name>Text` — a non-empty string. When the source published a value, it is that
  value. When it did not, it is the reason it is absent, written as a sentence the
  board can say out loud: `"No pending step published"`, `"Title not published"`,
  `"Harness does not report blocks"`, `"Exact location not published"`.
- `<name>Known` — `true` when a source published it, `false` when the text is a
  reason.

A view renders `<name>Text` and picks its ink from `<name>Known`: known text takes
`--ink`/`--ink2`, a reason takes `--ink3`. No view invents a fallback, and no view
tests a raw payload field for emptiness. If a reason string is missing from this
module, that is a bug in the module, not something a view patches locally.

Two derived-number fields carry a third key: `<name>Floor`, true when the figure
rests on partial data and must render prefixed with `≥`. The reason `Floor` is true
belongs in the accompanying text, not in the view.

## The model

```
{
  sessions,          // THE collection. Every derived count resolves from this array
                     // and nothing else. See §2 of the contract.
  projects,          // grouped by the label the harness publishes (F1, already shipped)
  activeProjects,    // projects with at least one working or needs-input session
  restProjects,      // the remainder — "Recently observed"
  active,            // sessions working, waiting on you, or carrying an exact request
  history,           // sessions ended or quiet
  counters,          // the four-counter strip, see below
  coverage,          // the Attention brief
  risks,             // scope: session — counted in the session denominator
  boardRisks,        // scope: board — NOT counted in it
  windows,           // P4 quota windows, one per vendor window
  sublimits,         // sub-limits inside a window, no clock of their own
  open,              // the "Not on this board yet" list
  totals,            // {sessions, running, needs, ended, quiet, subagents,
                     //  reportsBlock, exactRequests} — every one a length or a
                     //  count over `sessions`, never a literal
}
```

### A session

```
{
  sid, harness, project,          // identity, as published
  titleText, titleKnown,
  nowText, nowKnown,              // what it is doing right now
  nextText, nextKnown,            // the pending step
  whereText, whereKnown,          // exact location
  turnText, turnKnown,
  blockText, blockKnown,          // "Waiting on you" / "No reported block" / a reason
  blockNote,                      // the sub-line: how the board knows, or why it does not
  outcomeText, outcomeKnown,      // E2/E3/E4 — see below
  outcomeGlyph,                   // "◦" unread · "×" died · "△" dirty · "" when none
  gitText, gitKnown,
  rateText, rateKnown,
  askText, askKnown,              // the question, when one was asked
  waitedText,                     // how long it has waited
  stuckText, stuckKnown,          // C2
  sharedLabelText, sharedLabelKnown,
  state,                          // the harness's own word, unmapped
  isWorking, isNeeds, isEnded, isQuiet,
  tone,                           // "ok" | "want" | "bad" | "unknown" — see contract §3
  subagents, tasks,               // pass through, shape unchanged
}
```

`outcomeText` uses the shipped E2/E3/E4 wording exactly, and nothing else:
`"finished and was never read"`, `"died rather than finished"`,
`"ended leaving uncommitted work"`. Each carries its git-state line in `gitText`.

### A project

```
{
  key,                            // the published label
  scopeText, scopeKnown,
  countLine,                      // "6 sessions · 3 working · 1 waiting on you · 2 ended"
                                  // built from this project's own session array
  sharedLabelText, sharedLabelKnown,
  goalText, goalKnown, goalSrcText,
  goalGapText, goalGapKnown,      // "3 of 10 sessions publish no goal." — derived
  sessions, needs, working, ended, risky,
  delegation: {pctText, pctKnown, pctFloor, pct, tpsText, humanText, windowText,
               noteText},         // when pctKnown is false, pctText is "no figure yet"
                                  // and noteText is the reason
  changes, changeNoteText,        // the observed state-change timeline and its
                                  // unattended count, both derived
  tone,
}
```

### The counters

Four entries, `{label, value, noteText}`. **Every `value` is a count over
`sessions`.** None is a literal — the fixture hardcodes two of them and that is
ruling R2 in the contract, not a specification.

```
ACTIVE NOW        active.length              "<n> recently observed"
WORKING           count of isWorking         "<n> waiting on you"
EXACT REQUESTS    count carrying an exact request
REPORTED BLOCKS   count with blockKnown      "<n> of <m> sessions report block state"
```

### Coverage

`observed`, `quiet` and `gates` are **composed at derivation time from
`sessions`**, not authored. The fixture writes them as literal strings; that is R2
again. `rows` is one entry per harness the payload knows about, `caveats` is the
list of things no source published.

## Ranking

`projects` is sorted so a project blocked on the reader sorts above one merely
working (DRC-4468): needs-input first, then carrying a risk, then working, then the
rest. Ties break on a stable key so a redraw never reorders rows under the pointer.

## What A must report rather than invent

Where the payload has no field for something above, that is an **absence with a
reason**, and A picks the reason string and reports the choice. Where A believes a
field exists but cannot confirm it against `cargento_runtime/sessions.py` or a real
payload, A reports the gap instead of guessing. A wrong field name that renders a
plausible reason string is the worst outcome available here: it looks like honest
absence and is actually a bug.

---

## Amendment 1 — measured against the runtime, after workstream A reported

### A1.1 · Eight missing `Known` companions, added

The generic absence invariant this file demands contradicted the field list it gave.
These eight `Text` fields had no companion, so the walk that is supposed to catch a
field added without a reason string could not pass:

`waitedKnown`, `goalSrcKnown`, `changeNoteKnown`, `delegation.tpsKnown`,
`delegation.humanKnown`, `delegation.windowKnown`, `delegation.noteKnown`,
`counters[].noteKnown`.

Purely additive: every name already in use stays. A view may ignore a companion whose
field is always published, but the model provides it so the invariant holds without an
exception list.

### A1.2 · The invariant covers `*Text` keys only

`delegation.pct` is a **number for geometry**, not a string for reading. It is `null`
when `pctKnown` is false, and no view reads it unless `pctKnown` — the bar is inside
the present branch, so an absent figure draws no bar rather than a zero-width one.
The generic walk skips keys that do not end in `Text`.

### A1.3 · The end outcomes are the shipped six, not the fixture's three

**This corrects the fixture, this file's first draft, and the brief given to
workstream B.** The design fixture publishes `outcome: "unread" | "died" | "dirty"`
and wording — "finished and was never read", "died rather than finished" — that reads
as though it were the shipped E2/E3/E4 vocabulary. It is not. Measured:

- `next-attention.js:639` `NEXT_ATTENTION_KIND_LABELS` is the shipped vocabulary, and
  it is a 2×3 matrix: `stop`/`end` × `dirty`/`clean`/`unknown`.
- `next-attention.js:268` `nextAttentionStopSignal` derives it from `ended_at`,
  `finished_at`, `state` and `dirty`. It **deliberately does not distinguish a death**:
  an end with no `finished_at` becomes `end-*`, not "died".
- Readership is not on a session and not in the payload. The `/api/data` top-level keys
  are `ask`, `asks`, `discovered`, `generated`, `harnesses`, `history`, `sessions`,
  `usage`. Dismissals — the nearest thing to "you have read this" — live in a
  server-side store behind a separate route and never reach the page.

So "finished and was never read" would assert readership no source published, and
"died rather than finished" would assert a termination cause no source published. Both
are exactly what contract §1 forbids, and §1 governs.

`outcomeText` is one of these six, verbatim:

| Kind | `outcomeText` | Glyph | Tone |
| -- | -- | -- | -- |
| `stop-dirty` | Stop observed with uncommitted work | `△` | bad |
| `stop-clean` | Stop observed; git state clean | `✓` | ok |
| `stop-unknown` | Stop observed; git state not measured | `◦` | unknown |
| `end-dirty` | Session ended with uncommitted work | `△` | bad |
| `end-clean` | Session ended; git state clean | `✓` | ok |
| `end-unknown` | Session ended; git state not measured | `◦` | unknown |

Tone follows the **git half**, because that is the half that says whether anything was
left behind. `stop` versus `end` is carried by the sentence, not by colour: a stop
leaves the session open and typeable, which is a different fact, not a worse one.
`gitText` carries the detail line, and `session.changed` gives the entry count where
one was measured ("3 changed entries") — `nextAttentionCloseText` is the shipped
wording for it.

The two capabilities the fixture implied get a row in `open` instead, so the gap reads
as a gap:

```
["E6", "Finished and never read",
 "Nothing on the board publishes whether you have read a finished session. The
  dismissal store is server-side and does not reach the page."]
```

Termination cause is already covered by the existing coverage caveat, "Termination
cause not reported." Keep it.

---

## Amendment 2 — from workstreams B and C

### A2.1 · The session model carries `focusable` and `resume_id`

**A functional regression, caused by this file.** §"A session" listed
`sid, harness, project` as "identity, as published" and named neither of these, so the
model dropped both, and:

- `nextSessionRaiseControl` (`next-boot.js:272`) returns `""` unless
  `session.focusable === true`. The raise-terminal control disappeared from the board.
- `nextResumeCommand` (`next-boot.js:210`) reads `session.resume_id`. The
  copy-resume-command control degraded to copy-id everywhere.

Both are published payload fields — `focusable` defaults at `sessions.py:366` — and both
controls are shipped. The model carries them, so a **model session is directly
acceptable** to those two functions: they read only `sid`, `harness`, `focusable` and
`resume_id`, all of which the model now has. Pass the model session; do not reach for a
raw payload row.

They are **control inputs, not observations.** Never render them, never derive a count
or a tone from them, and never give them a `Text`/`Known` pair — they are not things
the board says. `resume_id` in particular is re-validated against `NEXT_RESUME_TOKEN`
inside `nextResumeCommand` because it is the one string on the board that becomes a
shell command in someone else's terminal; do not bypass that by building the command
yourself.

### A2.2 · `isWorking` and `isLive` are two different claims

The model collapsed them and the shipped code does not. Measured:

- `state` is a **collector inference off file recency**. `nextOperationsIsActive`
  (`next-sessions.js:134`) uses it alone, with a comment explaining that an observed
  end retires the state word and that requiring more would let the weaker reading veto
  the stronger one.
- `active` is an **event-published liveness flag**, set from real harness lifecycle
  events at `events.py:730`, `:749` and `:769`.

Four shipped sites require both — `next-activity.js:10`, `next-projects.js:103`,
`next-sessions.js:254` and `:295` — and all four are the ones that draw a session as
live right now.

So:

| Field | Definition | Used by |
| -- | -- | -- |
| `isWorking` | `state === "working"`, no observed end | lane membership: active vs history, and the `WORKING` counter, which partitions the active lane |
| `isLive` | `active === true && state === "working"`, no observed end | the breathing dot, `totals.running`, and any sentence claiming something is running now |

`totals.running` moves to `isLive`, because "running" is a liveness claim and a
collector's recency inference does not support it. A session with `state: "working"` and
`active: false` sits in the active lane and **does not breathe**. Assert that pair in a
test: it is the whole distinction.

### A2.3 · The Capacity panel needs an empty-state reason

Unspecified, and the rail cannot render nothing. When no window is published:
`"No quota window published"`, with the sub-line `"No vendor window has been read for
this harness."` Same rule as everywhere else — a reason, not an empty panel.

### A2.4 · The delegation trend is a shipped surface and stays

`nextDelegationTrend` and `nextDelegationTrendMarkup` exist and the new rail dropped
them. Ruling R1. The model exposes `delegation.trendText`, `delegation.trendKnown` and
`delegation.trendDelta`, and the rail renders the trend beside the figure.

### A2.5 · The `changes` row shape, declared

`{at, filled, label, harness}`, as implemented. `filled` is the unattended marker and
drives the dot's fill; `at` is a wall-clock label, not a timestamp to re-format.

### A2.6 · `harness` is always published on a session

No `harnessText`/`harnessKnown` pair. Harness is part of the session's identity and its
key, so a session that exists has one. The "Harness not published" reason belongs to a
**request**, not a session, which is where it appears in A's reason table.

### A2.7 · `goalText` is authoritative and rendered verbatim

A normalises the published goal; views render what the model gives, including its
whitespace, and do not re-trim. One normaliser, in one place.

### A2.8 · Text selection is NOT preserved — my brief was wrong

The worker brief said a text selection must survive a redraw.
[`docs/design-reader-state.md`](../design-reader-state.md) is canonical and says
selection is one of the two things `renderNext` deliberately does not manage.
**The canonical document wins.** Workstream B followed it over the brief and was right
to. Disclosures, scroll position and in-flight input drafts are preserved; selection is
not, and nothing should be added to preserve it.

### A2.9 · One discrepancy to reconcile, not yet ruled

On one captured payload the shipped timeline reports the window as "last 10m" and the
model reports "last 5m". Both cannot be right. Reconcile against
`nextWorkstreamProjectWindow` and either match it or state in a comment why the model's
basis is the correct one. Do not simply keep the new number because it is new.

---

## Amendment 3 — from workstream D

Three defects in the lane derivation, all confirmed against the shipped code. The
shipped answer to all three is one predicate and its complement over a deliberately
ordered list, and the model should copy that structure rather than invent another.

### A3.1 · `active` and `history` must partition `sessions`

Today they are two independent filters:

```js
const active  = sessions.filter(s => s.isWorking || s.isNeeds || s.askKnown);
const history = sessions.filter(s => s.isEnded || s.isQuiet);
```

An idle session with an outstanding request is `isQuiet` **and** `askKnown`, so it is in
both. An ended session with an outstanding request likewise. The shipped code cannot
have this bug because it filters one predicate and its negation
(`next-sessions.js:333`):

```js
const active  = ordered.filter(s => nextOperationsIsActive(s, asks));
const history = ordered.filter(s => !nextOperationsIsActive(s, asks));
```

Do the same: one `isActive` derived per session, `history` its complement. Assert both
that the two key sets are disjoint **and** that
`active.length + history.length === totals.sessions`. A partition is the only thing
that makes the counters trustworthy, which is the point of §2.

`isActive` follows `nextOperationsIsActive`: no observed end and
`state ∈ {working, needs_input}`, **or** an outstanding exact request regardless of
state. The request holds the row because it is a published fact with its own lifecycle,
answered or withdrawn rather than aged out — that comment is at `next-sessions.js:135`
and it is the reason an ended session with a live request is still active.

### A3.2 · A session with no published state must not vanish

`isWorking`, `isNeeds`, `isQuiet` and `isEnded` each require a specific `state` or an
`ended_at`. A session with an unrecognised or absent `state`, no end and no request is
in **neither** lane — while still counting in `totals.sessions`. The board then says
twelve and shows eleven, which is the DRC-4453 failure with a different mechanism: the
denominator and the rows disagree.

The shipped code has a fourth bucket for exactly this (`next-sessions.js:30`):

```js
const other = rows.filter(s => !["needs_input","working","idle"].includes(String(s.state || "")));
```

Every session reaches a lane. One with no published state is **not known to be
running**, so it belongs in history, and its `nowText` says why rather than leaving a
blank: `"No state published"`.

### A3.3 · Keep the shipped ordering

`nextSessionBlocks` (`next-sessions.js:10`) orders deliberately and the model lost it:

1. `gates` — `needs_input`, **in server order**, which is a deliberate choice, not an
   accident: the comment at line 16 says `aggregate.py` uses sid for a stable idle
   payload and only the idle tail is re-sorted here.
2. `working` — through `nextSessionWorkingOrder`.
3. `idle` — by nearest activity, ties broken on sid so a redraw is stable.
4. `other` — the remainder.

Derive the lanes from a list in that order and both lanes inherit it, as the shipped
filters do. Do not re-sort inside a lane afterwards; that is what loses it.
