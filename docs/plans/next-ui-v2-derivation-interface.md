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
