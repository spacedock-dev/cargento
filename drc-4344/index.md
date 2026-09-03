---
id: drc-4344
title: 'A team member dispatched into its own pane is a black box: its session is never published, the lead''s row shows a bare name, and its own subagents are unreachable'
status: implementation
source: https://linear.app/recce/issue/DRC-4344
started: 2026-09-03T09:39:35Z
completed:
verdict:
score: 0.6
worktree: .worktrees/spacedock-ensign-drc-4344
issue:
pr:
mod-block:
linear-status: 'Todo'
milestone: ''
release: ''
promise: 'P2'
move: 'sharpen'
estimate: ''
reconciled:
gates:
    version: 1
    records:
        - id: gate:drc-4344:triage
          stage: triage
          attempts:
            - id: gate-attempt:drc-4344-triage-1
              briefing:
                id: briefing:drc-4344:triage:attempt-1:revision-1
                digest: sha256:9d8ed1fc4175fd0dafe571cacaf14bf5d3eae32a62d4acee57e8d04bb3ed9525
                room-ref: ./review/triage/briefing-1
              resolution:
                type: Resolution
                id: resolution:spacedock:drc-4344:triage:1
                briefing: briefing:drc-4344:triage:attempt-1:revision-1
                by: person:captain
                at: "2026-09-03T11:20:38.142656Z"
                decision: approve
                reason: 'Captain approved the triage gate on 2026-09-03 ("1. approve"). Accepts the direction: Drafts A and B authorized as drafted (rewrite longer than the original, declared and accepted); enrich-the-fold approach over peer rows; six ACs with AC-5 the live user-visible drive and AC-6 the shape capture; +230 LOC ±30% across 6 runtime/doc and 11 test files; takes the single web/ slot ahead of H1 PR 2; review at two lenses plus an arbiter.'
              application:
                target-stage: implementation
                state: consumed
---

[DRC-4344](https://linear.app/recce/issue/DRC-4344) — Linear priority Urgent, no estimate yet, labels `discovered-by-agent`, `journey:mid-flight`, `move:sharpen`. Filed 2026-09-03 by the first officer from a live defect measured on this very session's board.

**Pick, 2026-09-03.** Captain-directed, out of chain order: "THIS NEEDS TO BE FIXED ASAP". The A6 chain (H1 in review) continues in parallel; this issue goes first on `web/` if it needs it, ahead of H1's PR 2.

The authoritative issue body lives in Linear. `triage` fetches it live, reviews it adversarially against the current codebase, and drafts the sharpened version for the gate.

## User value

A person running a Spacedock workflow, or any lead session that dispatches named teammates, notices
this the moment they open the board to see what the crew is doing. The lead's row carries a bare
name with no start time and no liveness, a teammate quiet for ninety seconds drops off it, and the
workers that teammate spawned are reachable from nowhere.

Promise **P2** — what is it doing, and when should I come back — with the move `sharpen`. The
promise already covers named pills for running subagents and session detail that leads with current
activity; this shape of delegation is the one place it degrades to a name. The labels
`journey:mid-flight` and `move:sharpen` are already correct on the issue, so `implementation` sets
none.

## Problem

Checked against the code at `5a156bc`, not restated from the issue. **The filed diagnosis is wrong
and the first officer's hypothesis is upheld: the join already works.** What is missing is what the
fold publishes, when it publishes it, and how deep it looks.

### The join, verified line by line

`collect` globs every top-level `*.jsonl` under the project dirs (`collectors/claude.py:398-404`)
and calls `claude_data.agent_identity` at `:408`. That classifier reads the head bytes for
`agentName` and `teamName` (`claude_data.py:430-471`) and returns `(True, name, parent_prefix)` when
`teamName` starts with `session-`. A classified child is folded into its parent at `:410-424`
carrying `path`, `mtime`, `label` and `agent_name`, with the comment on `:421` stating outright that
the untruncated name exists for the roster join. `started_agent_ids` (`:100-127`) then takes those
children and adds the full `<name>@session-<prefix>` id **and** the bare name to the started set.

Measured on the live board rather than argued. The lead's row published one entry: name
`spacedock-ensign-drc-4344-triage`, model `claude-opus-5`, `started_at` null. That model can only
have come from the teammate's own top-level transcript, through `analyses` at `:456-463` and
`child_model` at `:260-277`. A `pending_members` entry publishes a null model (`:749`). So the
teammate was classified, folded, joined, and read — and still published as a name.

### Gap 1 — the start stamp is null for every teammate, and the cause is not "it returned null"

`claude_data.transcript_started_at` (`claude_data.py:31-34`) calls `runtime_io.read_first_json`
(`io.py:50-63`), which reads **one line**. On Claude Code 2.1.259 a top-level transcript opens with
untimestamped control records: index 0 `agent-setting`, index 1 `mode`, index 2 `permission-mode`.
The first record carrying a `timestamp` is at index 3.

Measured over the eight most recent top-level transcripts in this project directory: index 3 on
seven of them, index 6 on the lead's own. Over the four most recent legacy
`<session>/subagents/agent-*.jsonl`: index 0 on all four. **That asymmetry is the whole finding.**
The field works for the layout DRC-4223 was written against and is structurally dead for the
teams-era layout, so the elapsed that issue shipped never renders for a teammate.
`next-session.js:252-255` omits the span when `started_at` is null, which is its intended
degradation and is why nothing looked broken.

The fix is a wider bounded head read, not `st_birthtime`: DRC-4223 rejected that explicitly because
it is macOS/BSD only and absent on the Ubuntu leg of `platform-tests`.

### Gap 2 — publication is gated on 90 s of freshness, so a live teammate flickers and a finished one vanishes

One internal list, `subagents`, currently serves five jobs: `latest_agent_mtime` into
`last_activity` (`:477-480`), the Working pin at `:616`, `working_detail` at `:622`, the Spacedock
strip at `:754`, and the published payload at `:740-751`. It is built fresh-gated —
`load_subagents` filters on `working_threshold_sec` at `:301`, and the classified children appended
at `:465-475` are filtered on the same 90 s (`config.py:456`).

Two consequences, both measured on this session:

- The reviewer `b5bdf44a` was on the lead's row at 09:30Z and **absent** from `/api/data` at
  09:41Z, transcript age 196 s, while alive and mid-review — blocked waiting on its own seven
  subagents, having written nothing for over 90 s. The row does not merely under-report; it blinks.
- The implementer `e257ed1f`, finished 58 minutes earlier, was absent throughout.

The roster cannot rescue either, and this is the part the filed body inverted: both members are in
`started_ids`, so `pending_members` (`:498-518`) correctly excludes them. Nothing publishes a member
that has started and stopped.

### Gap 3 — a teammate's own subagents are reachable by no code path

`load_subagents` is called once per session, at `:464`, with the **lead's** transcript path, and
`agent_transcripts` (`:203-241`) derives `sess_dir` from whatever path it is handed. A classified
child hits `continue` at `:414` and never becomes a `transcripts[prefix]` entry, so no call site
ever passes a child's path. Measured: seven `agent-*.jsonl` under the reviewer's own
`<project>/b5bdf44a-.../subagents/`, sizes 337 KB to 901 KB, mtimes inside the minute, each with a
`.meta.json` sibling carrying `agentType`, `description`, `spawnDepth` and `model`. Reachable by
nothing on the board.

### Gap 4 — the registry changed under the code, and it now carries the liveness this fix needs

`SKILL.md:17` and DRC-4263 both rest on "Members are pruned as they finish, so finished work is not
reported as running." **That is no longer true on this build.** The finished implementer is retained
in `members[]` and marked inactive.

Measured across both team registries on this machine. The 2026-08-10 one carries member fields
`agentId`, `agentType`, `backendType`, `cwd`, `joinedAt`, `name`, `subscriptions`, `tmuxPaneId`.
Today's adds five: `color`, `model`, `isActive`, `prompt`, `planModeRequired`. The `isActive` field
is present on three of four members and absent on the `in-process` lead. A grep for it across the
whole shipped skill returns nothing — the runtime reads none of the five.

Two consequences. It is the signal separating a retained-and-finished member from a live one, which
is what requirement 3 needs. And it retires the pruning assumption, which is a second reason the fix
must not simply publish stale children as running: DRC-4229's constraint stands — "Liveness is the
existing test, nothing new is inferred" — so transcript freshness remains authoritative for
"running now", and the registry flag may only ever demote, never promote. Whether a hard-killed pane
clears that flag is **unmeasured**, which is exactly why it cannot be the promoting signal.

Note for `implementation`: `prompt` in that registry is operator text. Its **name** may be recorded;
its value may never be read into a payload, a log or a capture.

### Verified by exercising, not by reading

Every claim above was re-checked by importing the shipped runtime and calling its own functions
against the live stores, rather than by reading the source. Session `b5bdf44a` is the reviewer,
`df15489c` the lead.

| Call | Result |
|---|---|
| `claude_data.transcript_started_at(teammate)` | `None` |
| `claude_data.transcript_started_at(legacy agent-*.jsonl)` | `1788425193.651` |
| `claude_data.agent_identity(teammate)` | `(True, 'spacedock-ensign-drc-4044-review', 'df15489c')` |
| first timestamped record inside the existing head budget | index `3`, `1788425000.613` |
| `agent_transcripts(child path)` | 7 grandchildren |
| `agent_transcripts(lead path)` | 1 child, and none of the child's 7 among them |
| `load_team_members(config)['df15489c']` | 3 members, joined `1788421553` / `1788425000` / `1788428391` |
| `config.store_roots['claude.teams']` | `('/Users/jaredmscott/.claude/teams',)` |

Two of those lines are worth reading together. `agent_identity` returning `True` with the right name
and the right parent prefix is the falsification of the filed diagnosis, taken from the classifier
itself. And the index-3 stamp, `1788425000.613`, agrees with that member's registry `joinedAt` of
`1788424999866` ms to within 0.75 s — two independent stores giving the same start instant, which is
what makes the wider head read a measurement rather than a guess at which record to trust.

### What the filed body got wrong

Four claims in "Where the join breaks", all falsified above at the line:

1. That the join looks for `agent-<name>.jsonl` under the lead's own subagents directory. It looks
   at the classified top-level child (`:100-127` reading `:410-424`).
2. That a teammate writing a top-level file "never matches". It matches on both the full agent id
   and the bare name.
3. That "the member is published as a pending name". A pending member publishes a null model; the
   live payload carried `claude-opus-5`.
4. That "its real session is left out of the published set" by that failure. It is folded
   deliberately (`SKILL.md:15`), which is the direction DRC-4118 chose for Cursor.

This is the **third** time an issue on this surface has asserted the teams-era layout is unread;
DRC-4263's correction 2 is the second. That is why the rewrite demotes it to a dated history section
rather than deleting it.

Two counts in the filed body are also loose: the reviewer had spawned **seven** subagents, not five,
and the unpublished top-level transcripts number **fourteen classified teammates** in the last 24 h
of this project directory, not "seven recent sessions".

And **requirement 4 is already satisfied.** The fold puts the teammate's activity on the lead's row,
and the lead's project label comes from its own cwd (`:520-534`) — measured `recce/cargento`, with
every registry member carrying that same cwd. Nothing to build. It moves to Out of scope with the
measurement rather than staying on the must-cover list, where it would buy a round of work for a
property that already holds.

## Proposed approach

**Enrich the fold. Do not promote the teammate to a row of its own.** Four changes, in
`claude_data.py`, `collectors/claude.py`, and three frontend parts.

1. **`transcript_started_at` takes the first record carrying a usable timestamp** within the head
   bytes `claude_agent_scan_bytes` / `claude_agent_scan_lines` already bound, instead of line 1
   alone. Index 3 is well inside the existing 50-line, 16 KB budget, so this costs no new read.
2. **Split the one list that serves two jobs.** The fresh-gated list keeps driving `last_activity`,
   the Working pin, `working_detail` and the Spacedock strip byte for byte as today. A second,
   published roster carries every classified child inside `window_hours` plus `pending_members`.
   This is the load-bearing separation: DRC-4118 already states the rule — "only the children that
   are moving now are counted into the state detail: a child parked hours ago must not make its
   parent read 'running 1 subagent'" — and DRC-4263's AC-3 requires it.
3. **Each published entry gains `active` and `parent`.** The first is the same
   `is_fresh(..., working_threshold_sec)` test that admits an entry to the fresh list, with the
   registry's inactive flag allowed to demote and never to promote. The second names the member an
   entry belongs to, null for the lead's own children. Per DRC-4223's own rule for widening this
   element — always present, null meaning not measured — both are declared for every harness.
4. **Walk each classified child's own subagent directory** by calling `agent_transcripts` on the
   child's path, and flatten what it holds onto the published roster with the parent field set.
   Flattening rather than nesting is the rule already in this codebase: Antigravity flattens a whole
   subtree onto the root card, and DRC-4118 chose `rootParentAgentId` over `parentAgentId` because
   "flattening the subtree onto the root card is the rule that cannot orphan a grandchild into a
   peer row".

Frontend: `next-session.js:249-264` and `next-activity.js:17-33` read the active flag instead of
stamping `next-live` on every element, and `next-chrome.js:211-218` counts only active entries.
**This also closes a defect DRC-4229 left standing** — pending members are already published into
`subagents[]`, and today every element renders with the live pulse and inside the "N RUNNING
SUBAGENTS" label, so the board currently pulses at members that have demonstrably not started. A
one-clause render fix on the surface already being changed; it rides this PR per the captain's
standing directive rather than being filed.

### Rejected: publish the teammate as a peer session row that names its lead

It is what the filed body's first requirement gestures at, and it would deliver state, turn, tokens
and the teammate's own pills for free, because a teammate transcript **is** a complete session
transcript — the change is deleting a `continue`. Rejected on two measurements.

- **It reverses DRC-4118 on the surface where the parent link is strongest.** That issue demoted
  peers to children precisely when a measured id-to-id edge to an already-published row existed,
  and a teammate's `teamName` is exactly such an edge to the lead's own prefix. Its promotion rule
  is kept, not discarded: a child whose named lead is not a published row is promoted rather than
  dropped, "because a dropped row is an invisible failure — the reader cannot tell 'folded' from
  'lost'."
- **The population settles it.** Of the 20 top-level transcripts fresh within 24 h in this one
  project directory, 14 classify as teammates of one lead. Promotion turns a six-row board into a
  twenty-row one, for a single lead session. The captain's complaint is that he cannot see the crew,
  not that he wants twenty tabs.

The cheaper rejected variant — keep the 90 s publication gate and encode "finished" in the label
string — is refused because `next-chrome.js:211-218` would then count finished members into
"N running", making the chrome lie in order to close a pill-level gap.

## Linear edits made

**Nothing has been written to Linear.** This section is the pre-edit record and the drafts the gate
authorizes; `implementation` performs the write as its first action.

Owning milestone, determined at triage because the issue was filed without one: **Steer before
waste** (`c965439d-7e5b-4fd0-ab73-dca409cce586`). Its user value is "For each live session: what it
is doing now, what it plans next, how far into the current turn it is, and an estimate of when that
turn ends" — the milestone that owns what my delegated work is doing right now. C1 (`DRC-4020`),
which this issue names as out of scope, lives in it, and P2 is the promise it backs.

### Pre-edit record — DRC-4344 body, verbatim as of 2026-09-03 09:38Z

Fetched live with `get_issue`. The inline mention tags are Linear's own serialization and are
reproduced as they came back.

~~~~markdown
## User value

A person running a Spacedock workflow, or any lead session that dispatches named teammates, notices this the moment they open the board to see what the crew is doing and find nothing: one name under the lead, no state, no start time, no tool, no tokens, and no way to reach the workers those teammates spawned. P2, sharpen: the promise already says Cargento shows what each session and subagent is doing right now, and for this shape of delegation it does not.

## What was measured, 2026-09-03 09:30Z, on the live board

Lead session df15489c (the first officer) had two registered teammates in ~/.claude/teams/session-df15489c/config.json, both with backendType tmux and cwd the repository root: spacedock-ensign-<issue id="b119a23f-5d65-4dcd-b471-c116835f06ca" href="https://linear.app/recce/issue/DRC-4044/h1-keep-a-history-of-what-happened">DRC-4044</issue>-implementation (isActive false, idle after finishing) and spacedock-ensign-<issue id="b119a23f-5d65-4dcd-b471-c116835f06ca" href="https://linear.app/recce/issue/DRC-4044/h1-keep-a-history-of-what-happened">DRC-4044</issue>-review (isActive true, mid-review). The reviewer had spawned four lens subagents and a critic, all writing under ~/.claude/projects/<project>/b5bdf44a-…/subagents/agent-*.jsonl within the last eight minutes.

What /api/data carried for the project:

* The lead's row listed one subagent: name spacedock-ensign-<issue id="b119a23f-5d65-4dcd-b471-c116835f06ca" href="https://linear.app/recce/issue/DRC-4044/h1-keep-a-history-of-what-happened">DRC-4044</issue>-review, model claude-opus-5, started_at null. No state, no last tool, no turn, no elapsed. The implementer was not listed at all.
* Seven recent top-level session transcripts in the same project directory were not published as sessions, including the reviewer's (b5bdf44a, 1.1 MB, modified two minutes earlier) and the implementer's (2.6 MB). Only the lead's own session was published.
* Because the reviewer's session is not a published row, its five subagents are unreachable from anywhere on the board.

Meanwhile the transcripts themselves showed exactly what the board could not: four lenses each 600 to 850 KB deep, last tool calls within four minutes, and a load-average burst of 20 from their test runs.

## Where the join breaks

collectors/claude.py joins a registered member to work in progress through started_agent_ids, which looks for a child transcript under the lead session's own subagents directory, agent-<name>.jsonl, and reads the agent id from it. A teammate that runs in its own tmux pane writes a top-level <uuid>.jsonl instead, in the same project directory, so it never matches: the member is published as a pending name and its real session is left out of the published set. The same assumption made spacedock's context-budget probe report "no subagent jsonl found" for every teammate all day, so the join key it wants (agentId, name, tmuxPaneId in the registry; agentName and teamName in the transcript header) is worth settling once for both readers.

## What a fix must cover

* A registered team member whose session exists is published with that session's state, turn, last activity, model and tokens, either as a child of the lead carrying those fields or as a peer row that names its lead and team, and never as a bare name.
* A member's own subagents are reachable from the board, at least as the count and names under the member.
* An idle or finished member is still visible while the team registry lists it, distinguishable from a running one, rather than vanishing.
* The project view for the repository shows the teammates' work under the same project label as the lead when their cwd is the same repository.

## Out of scope

Tripwires and stage alerts on subagents (C1), and grouping unrelated sessions into a workflow (F1). Codex or Antigravity teammates: capture their registry shapes first.

## Scores

Not yet scored by the panel; filed from a live defect by the first officer at the captain's direction ("this needs to be fixed ASAP").
~~~~

### Pre-edit record — "Steer before waste" milestone description, verbatim

~~~~markdown
## The user value

**For each live session: what it is doing now, what it plans next, how far into the current turn it is, and an estimate of when that turn ends. It tells you when that changes instead of making you poll.**

## What remains

[DRC-4020](https://linear.app/recce/issue/DRC-4020/c1-subagent-workflow-stage-and-a-tripwire-on-it): Cargento alerts you the moment a subagent crosses a line you set, instead of you checking in.
[DRC-4021](https://linear.app/recce/issue/DRC-4021/c2-the-stuck-signals-a-run-of-four-failures-misses): The board reports a turn's true failed-tool-call total, instead of only the peak run of consecutive failures.
[DRC-4023](https://linear.app/recce/issue/DRC-4023/c4-my-goals-across-sessions): You can see each session's stated goal in one place, instead of reopening a transcript.
[DRC-4025](https://linear.app/recce/issue/DRC-4025/c6-report-the-irreversible-things-that-happened): Cargento shows which irreversible actions ran while you weren't watching, such as a force push, recognised by the hook and never read by the runtime.
[DRC-4329](https://linear.app/recce/issue/DRC-4329/irreversible-actions-groundwork-securitymd-scope-section-for-hook-side): The SECURITY.md section for hook-side destructive-shape matching, before any code.

## Waits on

[DRC-4329](https://linear.app/recce/issue/DRC-4329/irreversible-actions-groundwork-securitymd-scope-section-for-hook-side) (irreversible-actions groundwork) gates [DRC-4025](https://linear.app/recce/issue/DRC-4025/c6-report-the-irreversible-things-that-happened).
~~~~

### Drafted rewrite — DRC-4344 body

Unwrapped, one line per paragraph, per the workflow rule measured on DRC-4037. Authored under the
emphasis guard: no emphasis run ends immediately before a code span.

~~~~markdown
## User value

A person running a Spacedock workflow, or any lead that dispatches named teammates, notices this on opening the board to see what the crew is doing: the lead's row carries a bare name with no start time and no liveness, a teammate quiet for ninety seconds drops off it, and the workers that teammate spawned are reachable from nowhere. P2, sharpen — the promise says Cargento reports what each session and subagent is doing right now, and for a dispatched teammate it reports a name.

## Problem

The join is not where this breaks. A teammate's top-level transcript is classified as a child of its lead at `collectors/claude.py:408`, folded at `:410-424` with its name, and joined to the registry roster on the agent id at `:100-127`. The live payload proves it: the pill carried `"model": "claude-opus-5"`, readable only from the teammate's own transcript. What is missing is what the fold publishes, when, and how deep it looks. Three gaps, measured on Claude Code 2.1.259.

**The start stamp is always null.** `claude_data.transcript_started_at` reads the first record only, and a top-level transcript here opens with untimestamped control records — `agent-setting`, `mode`, `permission-mode`. The first timestamped record sits at index 3 on seven of eight fresh top-level transcripts; a legacy `agent-*.jsonl` carries its stamp at index 0, which is why the elapsed DRC-4223 shipped works for the old layout and is dead for the new one.

**Publication is gated on ninety seconds of freshness.** A classified child reaches the published list at `:465-475` only while fresher than `working_threshold_sec`, so a teammate waiting on its own subagents flickers off the row: the reviewer was on it at 09:30Z and gone at 09:41Z, alive throughout. The implementer, finished 58 minutes earlier, was absent entirely. The roster rescues neither, because `pending_members` at `:498-518` excludes any member that has written a transcript.

**A teammate's own subagents are never scanned.** `load_subagents` walks a directory derived from the lead's transcript path, and a classified child is skipped at `:414` and never becomes a session, so nothing walks the child's directory. Seven live subagent transcripts sat under the reviewer's own directory, every mtime inside the minute, reachable by no code path.

**The registry has also changed under the code.** Claude Code 2.1.259 retains a finished member and marks it `isActive: false` rather than pruning it, one of five member fields today's registry adds over the older one here and none of which the runtime reads. That field separates a retained-and-finished member from a live one, and it retires the assumption that pruning alone keeps finished work from reading as running.

## What a fix must cover

* A registered member whose session exists is published with a measured start, its own model and its own liveness — never a bare name, and never dropped for ninety seconds of quiet.
* A member's own subagents are reachable from the board, at least as a count and names attributed to the member that spawned them.
* A member that has finished or gone quiet stays visible while the registry lists it and reads as distinct from a running one, in the running count and the state detail as well as the pill.

## Approach

Enrich the fold rather than promote the teammate to a row of its own. Take the first timestamped record inside the head bytes already read. Split the one list that serves two jobs today: the fresh-gated list keeps deriving state, state detail and last activity exactly as now, while the published list carries every classified child inside the display window plus the roster's unstarted members, each stamped with its own liveness and with the member it belongs to. Walk each classified child's own subagent directory and flatten what it holds onto that list with the same attribution, the rule Cursor and Antigravity already follow here because it cannot orphan a grandchild. Then let the frontend read liveness per entry instead of marking every entry live.

Rejected: publishing the teammate as a peer row naming its lead, which would deliver state, turn and tokens free. It reverses DRC-4118 on the surface where the parent link is strongest — a teammate names its lead by id, the exact condition under which that issue folds rather than promotes — and the population settles it: 14 of the 20 fresh top-level transcripts in this project directory are classified teammates, so promotion turns a six-row board into a twenty-row one. DRC-4118's promotion rule stays, because a dropped row is an invisible failure: a child whose named lead is not a published row is promoted rather than dropped.

## Acceptance

1. A teammate pill carries a measured elapsed rather than nothing.
2. A teammate that has stopped writing is still published, and counts as neither running nor unstarted.
3. A teammate's own subagents appear on the board, attributed to that teammate.
4. State, state detail and last activity are unchanged by all of the above: a member parked for an hour must not make its lead read as running one subagent.
5. On a live board, a reviewer's lens subagents are visible while they run.

## Out of scope

Tripwires and stage alerts on subagents (C1), and grouping unrelated sessions into a workflow (F1). Codex or Antigravity teammates: capture their registry shapes first. Detecting a gate that opens mid-run, which DRC-4263 measured as having no file-based signal.

Already true, so not part of this: the project view shows a teammate's work under the lead's project label, because the fold puts its activity on the lead's row and the label comes from the lead's own working directory. Measured `recce/cargento` on both, with every registry member carrying that same directory.

## History: what this issue said when it was filed, 2026-09-03

Kept because the diagnosis it carried was wrong in a way that has now been wrong three times on this surface, and a later reader is owed the correction rather than the chance to repeat it.

The filed "Where the join breaks" section said the roster join looks for a child transcript under the lead's own subagents directory, that a teammate writing a top-level file therefore never matches, that the member is published as a pending name, and that its session is left out of the published set by that failure. All four are false. The join reads the classified top-level transcript and keys on the agent id; a pending member publishes a null model while the live payload carried a real one; and the session is folded deliberately, which is documented product behaviour and the direction DRC-4118 chose. DRC-4263's second correction records the same mistake in another form.

The filed body listed a fourth requirement, that the project view show teammates under the lead's project label, which was already satisfied when it was written. It is recorded under Out of scope with the measurement.

Two counts were loose and are corrected above: the reviewer had spawned seven subagents rather than five, and the unpublished top-level transcripts were fourteen classified teammates rather than seven recent sessions.
~~~~

**Length, declared rather than hidden.** The rewrite proper is 5,770 bytes against the original's
4,041, and the stage's "Good" asks for shorter. It is longer, and the reason is visible in the diff:
the original spent roughly 1,600 bytes on a narrative measurement and 1,000 on a diagnosis wrong at
four claims, and the replacement spends its length on three gaps each cited to a line, plus a
rejected alternative with its own measurement. Trimming to hit the byte count would mean dropping
the citations, which is the opposite of what makes it buildable by a stranger. Flagged for the
captain to judge rather than resolved silently. The dated history section is a further 1,374 bytes.

### Drafted milestone correction — "Steer before waste"

One insertion into "What remains", after the DRC-4329 line, keeping the ascending-ID order the list
already uses. Nothing else changes; the diff was computed and is exactly one hunk of one added line.

~~~~markdown
[DRC-4344](https://linear.app/recce/issue/DRC-4344/a-team-member-dispatched-into-its-own-pane-is-a-black-box-its-session): A teammate you dispatched into its own pane shows what it is doing and what it spawned, instead of a bare name that disappears when it goes quiet.
~~~~

`implementation` must build this write by script from a fresh pre-write capture, assert the DRC-4329
line is present **exactly once** before replacing it, and diff the result to exactly one hunk — the
workflow's standing rule, because `save_milestone` has no patch operation and resends the whole
description. Expect emphasis boundaries to move in pre-existing text nobody is touching; report it
and do not repair it. Read back the relation set afterwards: any issue reference in a body becomes a
mention, and mentions silently add `relatedTo` edges.

### What was demoted to history, and why

The filed "Where the join breaks" section and the fourth must-cover requirement. Both are wrong
rather than merely superseded, and both have been read by others — the same wrong root cause has now
been asserted three times on this surface. Deleting it would let a fourth reader re-derive it; the
dated history section names it as the mistake it is.

## Expected surface and tolerance

Estimate: **+230 net LOC across 6 runtime and doc files, plus 11 test files**, tolerance **±30%**.
Semantics this may change: **runtime behavior and the published payload shape** — the `subagents[]`
element widens by two always-present keys. No command grammar, no stored format, no authority
change.

Costed separately, because DRC-4037's overrun was an estimate that was right about the work and
wrong about what the repository's own contracts would demand of it.

**Runtime and docs (~+130):**

| File | Why |
|---|---|
| `cargento_runtime/claude_data.py` | `transcript_started_at` widens to a bounded head scan (~+12/-4) |
| `cargento_runtime/collectors/claude.py` | split the two lists, add the two keys, walk the child's directory (~+70/-25) |
| `cargento_runtime/web/next-session.js` | read the active flag; drop the unconditional `next-live` (~+10/-6) |
| `cargento_runtime/web/next-activity.js` | same (~+8/-5) |
| `cargento_runtime/web/next-chrome.js` | count only active entries (~+4/-2) |
| `SKILL.md` | correct the pruning claim at `:17`, extend `:15` for grandchildren (~+4/-4) |

`docs/design-session-identity.md` gains a Claude subsection beside "Folding a subagent onto its
parent" (~+20), which `sync-docs` may place instead.

**Oracles (~+100, and this is where the compulsion lives):**

- **Compelled, not chosen: eight test files hold an exact `subagents[]` element dict.** A grep
  counts 11 assertions carrying both `"model"` and `"started_at"` across `test_claude`,
  `test_codex`, `test_contracts`, `test_copilot`, `test_droid`, `test_gemini_antigravity`,
  `test_sqlite_collectors` and `test_transcripts`. DRC-4223's own rule for this element — always
  present for every harness — makes all eight compelled by the contract rather than by the feature.
- **Compelled: four byte pins in `tests/test_next_page.py`** — the three changed JS parts plus the
  assembled page. Recompute from the assets; never resolve textually.
- Chosen: new offline cases in `tests/test_claude.py` for gaps 1, 2 and 3, and in
  `tests/test_next_session.py` and `tests/test_next_activity.py` for the inactive render.

**Checked and *not* compelled, each verified rather than assumed:**

- `DECLARED_SESSION_FIELDS` (`tests/test_sessions.py:303-347`) — no session-level field is added.
- `PATCHABLE` (`events.py:111-122`) — its nine names do not include `subagents`, so no overlay
  reducer changes.
- `config.resolve_store_roots`, `diagnostics.py` and `CARGENTO_RUNTIME_FILES` — `claude.teams` is
  already a store root (`config.py:353`) with a `--diagnose` row (`diagnostics.py:25`), and no new
  module lands.
- `tests/test_documentation.py` — no new `~/...` path enters `SKILL.md`, so its store-root
  resolution is untouched.
- `styles.css` — the change removes a class rather than adding motion, so the pin at
  `test_next_page.py:576-582` and DRC-4229's reduced-motion fallback both stand.

**Sequencing.** This touches `cargento_runtime/web/`, and exactly one in-flight PR may. It takes the
slot and merges **before** H1's PR 2, which then rebases and recomputes its own pins. Confirm no
other branch holds `web/` with `git worktree list` before starting.

## Acceptance criteria

**AC-1 — A folded teammate's pill carries a measured start stamp.** (offline)
Verified by: a new case in `tests/test_claude.py` writing a top-level child transcript whose first
three records are `agent-setting`, `mode` and `permission-mode` with no timestamp and whose fourth
carries one, then asserting the published first subagent's start stamp equals that fourth record's
parsed value. The fixture's untimestamped preamble is the measured 2.1.259 shape, so the expected
value comes from the fixture rather than from a production constant.
Falsified by: reverting `transcript_started_at` to `read_first_json`, which returns the preamble
record and yields null.

**AC-2 — A teammate that has stopped writing is still published, and counts as neither running nor
unstarted.** (offline)
Verified by: a case with two classified children — one with an mtime inside `working_threshold_sec`,
one aged past it but inside `window_hours` — and a roster listing both. Asserts the published list
holds both entries; that the stale one is inactive and the fresh one active; that pending members
contribute neither; and that `state_detail` reads `running 1 subagent`.
Falsified by: appending the stale child to the fresh-gated list instead of the published one, which
flips `state_detail` to `running 2 subagents` and breaks DRC-4263's AC-3.

**AC-3 — A teammate's own subagents are published, attributed to the teammate.** (offline)
Verified by: a case laying down a classified child transcript plus two `agent-*.jsonl` under that
child's own `<child-uuid>/subagents/` directory, asserting both appear in the published list with
the parent field equal to the child's agent name, and that the parent-level entry's own parent field
is null.
Falsified by: calling `agent_transcripts` only on the lead's transcript, which yields zero
grandchildren — the state of the code today.

**AC-4 — The state derivation is byte-for-byte unchanged.** (offline)
Verified by: the pre-existing `test_claude.py` cases for `state`, `state_detail`, `last_activity`
and the Spacedock strip passing unmodified, with no edit to their expected values anywhere in the
diff.
Falsified by: feeding the published roster into `working_detail` or `latest_agent_mtime`, which
changes those expectations and shows up as edits to assertions this PR has no business touching.

**AC-5 — A user opening the board during a live review sees the reviewer's lens subagents.**
(interactive, user-visible)
Verified by: a live drive against a real session with a dispatched teammate that has itself
dispatched subagents. `GET /api/data` carries one entry per lens with the parent field set to the
teammate's name and the entry active, the rendered session detail lists them under the teammate, and
the chrome's running-subagent count equals the number of active entries. Recorded as
`Verified by: live session:<path>` per the workflow's live-scenario rule, with a negative arm — the
same read after the lenses finish — showing them present and inactive rather than absent.
Falsified by: the same read returning the lead's own children only, which is what it returns today.

**AC-6 — The registry and transcript shapes this fix reads are captured as evidence.** (offline)
Verified by: `docs/captures/claude/team-registry-2.1.259-macos.jsonl` existing, listed in the
captures README's Files table with its provenance, and holding field-name-to-type maps for the
member entry and the top-level transcript header plus the verdicts this triage measured — the
preamble record types, the index of the first timestamped record, the inactive flag's presence per
member, and the older registry's field set for comparison. Plus a check asserting the file carries
no value for `prompt` and none for `message`.
Falsified by: any record in that file carrying the value of `prompt`, or any per-member value that
is not a field name, a type name, or a closed-vocabulary token — the same rule under which
`notification_type` and `reply` earned their place and `message` is still refused. The precedent for
a store-shape rather than hook-payload capture is `pi/boot-envelope-fosession-linux.jsonl`.

The interactive/offline split is declared here so the gate can see it: AC-5 is the only interactive
one, and no harness is proposed to automate it. Driving a real lead that dispatches a real teammate
that dispatches its own subagents means starting three live harness processes, and the workflow's
own rule is that a session you spawn leaves daemons behind. AC-1 through AC-4 and AC-6 carry the
regression weight; AC-5 is the one a person sees, and it is verified by hand once.

## Test plan

Offline, in `tests/test_claude.py`: one case per gap, written test-first against the fixtures above.
The 2.1.259 preamble shape and the child's own `subagents/` layout are the two fixtures that did not
exist before; both are cheap files.

Render, in `tests/test_next_session.py` and `tests/test_next_activity.py`: an inactive entry renders
without the live class and outside the running label; an active one is unchanged.

Byte pins, in `tests/test_next_page.py`: recomputed from the assets for the three changed parts and
the assembled page. Not resolved textually under any circumstances.

Mechanical: the eight files holding an exact element dict gain the two keys. No E2E harness. The
whole suite runs **once** — a load average above about 10 manufactures failures in `test_http_api`,
`test_page`, `test_lifecycle` and `test_quota`, and a full adversarial review is in flight on this
machine right now, so confirm any failure in those four modules by running that module alone before
believing it.

Live, once: AC-5's drive, with the daemons it starts killed and the kill scoped to what was started.

## Review depth

**Two lenses plus an arbiter**, from AGENTS.md's Calibrating Effort table. The row that selects it:
"Owns a conflict-prone surface (`web/` byte pins, `SKILL.md`, `config.py`)." This PR owns two of the
three — the frontend byte pins and `SKILL.md` — and it changes the shape of a published payload that
eight test files assert. It is not the security or data-loss row, so full adversarial is not
warranted. The arbiter reproduces findings rather than ranking them.

### Feedback Cycles

## Out of scope

Tripwires and stage alerts on a subagent crossing a line (C1, `DRC-4020`). Grouping unrelated
sessions into a workflow (F1, `DRC-4041`). Codex or Antigravity teammates — capture their registry
shapes first, which is the same discipline this issue applies to Claude's. Detecting a gate that
opens mid-run, which DRC-4263 measured as having no file-based signal and which the new registry
fields do not supply either.

Publishing a teammate's turn progress, ETA or token totals. The must-cover list gestures at them,
and they are the peer-row shape rather than the pill shape; a pill carrying state, elapsed and its
own children answers "what is the crew doing" without becoming a second session card. If the captain
wants the full card, that is the rejected alternative above and a different issue.

Reading the registry's inactive flag as a promoting signal, or reading `prompt`, `color`, `model` or
`planModeRequired` from the registry at all, beyond the model already read from the transcript.

**Already true, so not part of this** — the project view already shows a teammate's work under the
lead's project label. Measured, with the reasoning under "What the filed body got wrong".

Fixing spacedock's own `dispatch context-budget` probe, which reported "no subagent jsonl found" for
every teammate today. That is spacedock's to fix and not Cargento's. The shared join key is worth
recording for whoever does: the registry side is `agentId`, of the form
`<name>@session-<lead prefix>`, with `name` and `tmuxPaneId` beside it; the transcript side is
`agentName` plus `teamName`, of the form `session-<lead prefix>`. `collectors/claude.py:100-127`
keys on both the full id and the bare name, and is the working reference implementation.

## Stage Report: triage

- DONE: Pre-edit record first (the live DRC-4344 body verbatim, and the owning milestone once you
  have determined which milestone this belongs to), then the drafts in this entity only, nothing
  written to Linear
  Both verbatim under `## Linear edits made`; milestone determined as **Steer before waste** from
  the descriptions. `save_issue` / `save_milestone` never called.
- DONE: and the adversarial read of the filed body against the code — every claim in it checked …
  correcting the filed diagnosis where it is wrong
  Four claims in "Where the join breaks" falsified at the line, plus two loose counts and one
  requirement already satisfied. Checked by calling the functions, not reading them.
- DONE: in particular whether the teammate transcript is already classified as a child at :408 (so
  the fix is publishing what is already identified, not a new join)
  It is: `agent_identity(teammate)` returns `(True, 'spacedock-ensign-drc-4044-review',
  'df15489c')`. FO's hypothesis upheld on the join, corrected on gap 3 — the grandchild scan is a
  genuinely missing call (`agent_transcripts(child)`=7, `agent_transcripts(lead)`=1, disjoint).
- DONE: and why `started_at` comes back null for it
  One-line head read against three untimestamped 2.1.259 preamble records; first stamp at index 3
  on 7 of 8 top-level transcripts, index 0 on 4 of 4 legacy ones. Exercised: `None` vs
  `1788425193.651`.
- DONE: The narrowest approach that makes a dispatched teammate visible end to end … whether it
  needs `cargento_runtime/web/` … and its review tier from AGENTS.md's table
  Enrich the fold; peer rows rejected (14 of 20 fresh top-level transcripts here are teammates).
  Needs `web/` — `next-session.js:256` stamps `next-live` unconditionally — so it takes the single
  slot ahead of H1's PR 2. Tier: two lenses plus an arbiter.
- DONE: Acceptance criteria as end-state properties, each offline or interactive with a
  `Verified by:` and a `Falsified by:`, at least one a user can see
  Six ACs; AC-5 is the interactive user-visible one (seven lenses measured, not four). AC-4 is the
  guard that the state derivation must not move, where DRC-4263 AC-3 and DRC-4118 both bind.
- DONE: plus an expected surface with tolerance that costs the oracles separately and names the
  compelled test edits
  +230 LOC / 6 runtime-and-doc files / 11 test files, ±30%. Compelled: 8 files holding an exact
  element dict, 4 byte pins. Verified **not** compelled: `DECLARED_SESSION_FIELDS`, `PATCHABLE`,
  store roots, `test_documentation.py`, `styles.css`.
- DONE: with the live fixture captured as evidence under `docs/captures/` … field names and timings
  only, never prompt text or any operator text
  Specified as AC-6, not written: an unapproved file under `docs/captures/` is a gate bypass. Its
  name, contents, Files-table row, precedent and falsifying condition are fixed there. The new
  registry's `prompt` field is named as recordable by name only.

### Summary

The filed diagnosis was wrong and the FO's hypothesis right: the teams-era join already works,
proven by calling `agent_identity`. The defect is three gaps — a one-line head read that misses the
start stamp because 2.1.259 writes three untimestamped preamble records, a 90-second freshness gate
applied to publication rather than only to the state derivation, and a directory scan never handed a
child's path. A fourth measurement was not in the issue: the harness now retains a finished member
and marks it inactive rather than pruning it, which falsifies `SKILL.md:17` and supplies the
liveness signal requirement 3 needs.

Two things the gate should read rather than skim. The rewrite is **longer** than what it replaced
(5,770 against 4,041 bytes) where the stage asks for shorter; the trade is citations against brevity
and it is declared in the entity rather than hidden. And the estimate names eight test files as
compelled by an existing contract rather than by this feature — the exact shape of the DRC-4037
overrun, declared up front so it is not discovered at review.

## Stage Report: implementation

- DONE: First action, before any file in the tree changes: the authorized Linear writes performed
  and read back — Draft A sent verbatim and unwrapped, Draft B built by script from a fresh capture
  with an exactly-once assertion on the DRC-4329 anchor line and a diff showing exactly one hunk,
  the labels confirmed, the relation set read back after each write, every emphasis-boundary move
  reported rather than repaired
  Both writes landed before any tree change. Draft A read back and diffed against the draft with
  mention tags normalized: **exactly two differences, both the documented shift** where the approved
  prose ends a bold run immediately before a code span (`**…null.** ` → `**…null. **`). Text content
  identical; reported, not repaired. Draft B: the live `get_milestone` read was byte-identical to the
  entity's pre-edit capture (sha256 `a7db04f8…` both sides), so that capture *was* the fresh capture;
  anchor asserted present exactly once; `difflib` gave **1 hunk, 1 added line, 0 removed**. New
  serializer artifact, worth the record: every link href came back wrapped as `(<url>)`, five of the
  six lines pre-existing text nobody touched. Labels `journey:mid-flight` and `move:sharpen`
  confirmed already correct, so no label write. Relations read back after each write: `relatedTo`
  4 → 5, one unrequested edge (DRC-4223, the only new reference not already related), no
  `blocks`/`blockedBy`, so not Material. Milestone set on the issue, the plain consequence of triage
  naming its owner.
- DONE: The four approved changes built test-first in the worktree, each watched to fail first …
  `SKILL.md:15` and `:17` corrected, the capture written per AC-6 with its README row, the canonical
  pre-PR suite run once, `sync-docs` invoked, the surface measured before the PR opens, the diff
  reviewed in the worktree
  Red first in `51e448d`: five oracles, four failures and one error, each for its own reason.
  Implementation `776c11f`. Rebased onto `ff8280a` after H1's PR 1 landed, no conflict, and main's
  advance touched no `web/` file or byte pin. Suite once at load 3.07 on the final tree: **1874
  dashboard tests OK** (1 skipped) plus **200 script tests OK**, ruff / format / mypy(112) /
  lint_embedded / validate_plugins clean, `bump_version --current` 0.20.0, no version field moved,
  coverage **90.2%** against `fail_under = 73`, both native validators pass. Byte pins recomputed
  from the assets twice, after the rebase and after the review round, and re-verified by running the
  oracles rather than reasoning about them. `sync-docs` in `ff2ad74` found real drift, including a
  true claim in `COMPATIBILITY.md` resting on a premise that had stopped being true. Surface put to
  the FO before the PR and accepted as `fo-ruling[2026-09-03]`, citing the captain's ruling that day
  on H1's identically shaped overage.
- DONE: A PR opened whose body starts `Implements [DRC-4344](…) — <title>` with a `## Verification`
  section, its number and head SHA reported; AC-5 driven live against this session's own board with
  the negative arm, recorded under `docs/captures/` without any operator text; and
  `## Stage Report: implementation` giving AC-1 through AC-6 each an evidence citation
  **PR #261, head `0d48cfb`.** Body carries `## Surface, declared against actual`,
  `## Review round 1`, `## Review guidance`, `## Known and not fixed` and `## Verification`. No
  `Closes` line. Two lenses read the diff in the worktree before it opened.

### Acceptance criteria

- **AC-1** (start stamp measured) — `test_a_teammate_start_comes_from_the_first_timestamped_record`
  asserts the published start equals the fixture's own fourth record, the first carrying a stamp.
  Fails if `transcript_started_at` returns to the one-line read: it then reads the untimestamped
  `agent-setting` preamble and yields null, which is what it did at `51e448d`.
- **AC-2** (quiet teammate published, neither running nor unstarted) —
  `test_a_quiet_teammate_stays_published_and_reads_as_not_running` holds both children with the
  stale one inactive while `state_detail` stays `running 1 subagent`. Fails if the stale child is
  appended to the fresh-gated list, which flips it to `running 2 subagents`.
- **AC-3** (a teammate's workers, attributed) —
  `test_a_teammates_own_subagents_are_published_under_it` finds both `agent-*.jsonl` under the
  child's own directory with `parent` set to the child's name and the child's own `parent` null.
  Fails if `agent_transcripts` is called only on the lead's path: zero grandchildren.
- **AC-4** (state derivation unchanged) — proved beyond the unit tests. The pre-change tree extracted
  with `git archive`, both collectors run in separate processes against the **same live stores** on a
  pinned `now`, and `state` / `state_detail` / `active` / `blocked_since` / `spacedock` /
  `last_activity` compared per session: **9 sessions both sides, 0 state-bearing fields moved.** A
  lens independently proved the same thing by construction, tracing that `roster` is referenced only
  at the payload key. No pre-existing state expectation was edited; one pre-existing `subagents`
  expectation moved by design and carries a comment naming DRC-4344.
- **AC-5** (a user sees the workers, live) —
  `Verified by: live session:~/.claude/projects/<project>/df15489c-….jsonl`, recorded as arity in
  `docs/captures/claude/teammate-board-drive-2.1.259-macos.jsonl`. Control on shipped code:
  **2 published, 0 measured starts**, no grandchild reachable. Patched, same stores: **34 published,
  34 measured starts, 17 grandchildren across 5 named parents**, 2 active; the chrome counted 3
  running, not 37. Negative arm once the workers stopped: **present and inactive**, not absent.
  Fails if the read returns the lead's own children only.
- **AC-6** (the shapes captured as evidence) —
  `docs/captures/claude/team-registry-2.1.259-macos.jsonl` (17 records) and its README row. It
  independently reproduces triage's two figures: the first timestamped record at index 3 on seven of
  eight top-level transcripts and 6 on the eighth, index 0 on all four legacy files; and the five
  member fields today's registry adds, of which only `isActive` is read. `prompt` is recorded **by
  name only**. The oracle behind this was defeatable six ways and is rewritten as a positive
  vocabulary over **both** captures, keys included; all six defeats plus a seventh replay as caught,
  and it rejected two keys added later in the same round. The recorder is committed as
  `scripts/capture_team_registry.py` with its own tests, and re-running it reproduces both files'
  records and both verdicts.

### Filed

- **Grandchild liveness does not reach the teammate.** Reproduced: teammate quiet 300 s, its worker
  2 s, and the teammate publishes `active: false` with a live worker under it and the lead reading
  `idle`. Two mechanisms weighed. Making the teammate live when a worker is puts an active pill
  under an idle lead, which is the worse lie. Absorbing a grandchild's mtime into the session's
  activity is the consistent one, is what DRC-4118 does for Cursor and `latest_agent_file_mtime`
  already does for the lead's own agents, and it moves `state` — the field AC-4 froze. Needs its own
  acceptance criterion and the captain's call to reopen that field.
- **A teammate that dispatches its own teammate into a pane is reachable by nothing.** That bucket
  lands in `agent_children[<child prefix>]` and the session loop iterates `set(transcripts) |
  set(tasks_by_session)`, which holds neither, so it is silently discarded. Reasoned through the code
  path, **not reproduced**: whether the harness writes `teamName: session-<child prefix>` for a
  nested dispatch is unmeasured.

### Summary

The filed diagnosis was wrong and triage's correction held: the teams-era join already worked, so
this changed what the fold publishes, when, and how deep it looks. Four changes plus a frontend that
reads liveness per entry, which also closed a defect DRC-4229 left standing where an unstarted
member pulsed like a running one.

Two things the review gate should read rather than skim. **I introduced a credential-redaction
bypass**: `subagents[].parent` was added beside `name` without being added to `aggregate.py`'s sweep
table, so the same untrusted `agentName` came back redacted in one key and raw in the other. That
module's docstring already records the same omission twice; this was the third. Found by my own lens
before the PR opened, fixed test-first, and generalised so the next key added there must be
classified. And the **AC-6 oracle I wrote was defeatable six ways** — it never checked dict keys, read
one of two files, and bounded strings at 64 characters when the labels it guards are shorter than
that by construction. Rewritten as an enumerated vocabulary; every defeat replays as caught.

Surface came in **+1952 net across 41 files** against a declared +230 ±30%, accepted as
`fo-ruling[2026-09-03]`. The functional change is +188 net across 9 files, inside the band; the rest
is oracles the acceptance criteria demanded, an AC-6 oracle that was never costed, a committed
recorder, and `ruff format` turning each two-key assertion into roughly eight lines.
