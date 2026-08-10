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
| Transcript | a pending question found by reading the session's records | `AskUserQuestion`, `ExitPlanMode` |
| Event overlay | the plugin-bundled `PermissionRequest` hook | any tool permission gate, including a subagent's |
| Notification | the user-installed `Notification` hook, posted to the loopback API | MCP elicitation dialogs, worker permission and network requests |

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
transcript quiet, because the `tool_use` record is written before the prompt is raised and the
`tool_result` only after it is answered, so a genuinely blocked session falls out of the window
within `working_threshold_sec` and its hook surfaces. Late, but not lost.

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

## What is still not measured

`notification_type` is present on every Notification payload, and its value list was read from the
emit sites in an installed 2.1.226 bundle rather than observed on the wire. No capture in
`captures/` holds a `Notification` record, because a headless run auto-denies and never raises one,
so getting one needs an interactive session. Two specific values are inferred rather than seen: which
one a plain main-session permission prompt carries, and that a worker's network request has no
`PermissionRequest` behind it.
