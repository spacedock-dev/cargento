---
id: drc-4344
title: 'A team member dispatched into its own pane is a black box: its session is never published, the lead''s row shows a bare name, and its own subagents are unreachable'
status: done
source: https://linear.app/recce/issue/DRC-4344
started: 2026-09-03T09:39:35Z
completed: 2026-09-03T23:37:57Z
verdict: PASSED
score: 0.6
worktree: .worktrees/spacedock-ensign-drc-4344
issue:
pr: pr-merge:261
mod-block:
linear-status: 'Todo'
milestone: ''
release: ''
promise: 'P2'
move: 'sharpen'
estimate: ''
reconciled: 2026-09-03T23:35:39Z
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
        - id: gate:drc-4344:review
          stage: review
          attempts:
            - id: gate-attempt:drc-4344-review-1
              briefing:
                id: briefing:drc-4344:review:attempt-1:revision-1
                digest: sha256:1abb513d37018af8f343f783982e6bd18593aae229c8f7c22371b70977da1a83
                room-ref: ./review/review/briefing-1
              resolution:
                type: Resolution
                id: resolution:spacedock:drc-4344:review:1
                briefing: briefing:drc-4344:review:attempt-1:revision-1
                by: person:captain
                at: "2026-09-03T23:26:50.929059Z"
                decision: approve
                reason: 'Captain approved the review gate on 2026-09-04 ("yes I approve, go with your recommendation"). Accepts the cycle-3 GO on 5314e09 after two correction rounds: AC-1..AC-6 reproduced, AC-4 with 0 state fields moved over 86,816 comparisons, AC-5 driven live both arms, 26 byte pins matched in both pinning files, redaction at the clip boundary proven, 13/13 checks on this head. Deferred items filed as DRC-4346, DRC-4347, DRC-4348; surface overage accepted under the standing ruling.'
              application:
                target-stage: done
                state: consumed
review-round:
    id: round:drc-4344:review:2
    stage: review
    cycle: 2
    briefing:
        id: briefing:drc-4344:review:round-2:revision-1
        digest: sha256:9db5507d5ef3413f03914a70953b74f4803c5148fb44aef3f0d008ec994a87d4
        room-ref: ./review/review/round-2
archived: 2026-09-03T23:37:57Z
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
are never counted as running; and that `state_detail` reads `running 1 subagent`.
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

**Spent at review, 2026-09-03: three lenses plus an arbiter.** The gate's two, plus one the diff
earned after triage was written. The justifying property is in the diff rather than in the plan:
`aggregate.py`'s credential-sweep table is in it (+7), because the implementer's own pre-PR lens
found it had added `subagents[].parent` beside `name` without joining that table, publishing the
same untrusted `agentName` redacted in one key and raw in the other. That module's docstring
records the same omission twice before. A change that touches that table gets a lens whose only
question is what it publishes, so the third lens traced every string this PR adds from its
untrusted source to the wire. The other two were the gate's: the fold and the frozen field, and
the frontend with its byte pins. No completeness critic was added — three questions covered the
diff and a fourth agent had no unread surface left to be given.

**Spent at re-review, 2026-09-03 (cycle 2): self-verify by reproduction, three lenses in parallel.**
The property that chose it is a property of the correction round rather than of the diff: fifteen
authorized items, each with a named red-first mutation already recorded, so the cheap and decisive
pass is to re-apply those mutations rather than to re-ask the three questions the `0d48cfb` lenses
already answered. That pass stands and was not repeated. Three lenses ran anyway, on the surfaces
the round newly touched — the heading, the byte pins in both files that pin the page, and the
redaction boundary with the capture recorder — and they ran in parallel because AC-5's positive arm
needed a live worker beneath a teammate and the reviewer that spawns them is the only fixture on
this board that produces one. I arbitrated their findings by reproducing each myself; the
grading moved on two. What would have made me climb: an item outside its span, a citation that does
not reproduce, a change to a frozen state field, or a redaction regression at the new clip boundary.
The second of those happened — a provenance sentence this PR adds to `docs/captures/README.md` does
not reproduce — and it is the finding the verdict rests on.

**Spent at re-review, 2026-09-03 (cycle 3): self-verify by reproduction, no lenses.** The property
that chose it belongs to the correction round rather than to the diff: eight bounded items, each
already carrying its own named red-first mutation, over a runtime change of one bound and one
comment in one file (`claude.py`, +15/-5) and one web asset (`next-chrome.js`, +2/-1). The decisive
pass is therefore to re-apply the round's own mutations in throwaway checkouts and to recompute the
pins from the assets, not to re-ask the questions the `0d48cfb` three-lens pass and the cycle-2
lenses already answered; that work stands and is not repeated. What would have made me climb to
lenses: a runtime edit outside the `state_detail` bound, a second changed web asset, a moved pin
whose asset did not move, any state-bearing field moving in the two-collector run, or the capture
directory's provenance claim still failing to reproduce. None of the five happened. AC-5 was
re-driven live rather than carried over, because dispatching one worker of my own makes this session
the fixture the criterion needs.

### Feedback Cycles

- Cycle 1: NO-GO — review gate, three lenses plus an arbiter (3 of the lens findings refuted), 1 Material + 2 Needs-decision + 4 Deferred risk + 4 Polish fixed in-PR, 2 Needs-decision ruled by the captain (window gate extended to the lead's own agents; AC-2 reworded), 1 Deferred risk filed as DRC-4348; surface 42 files/+2572 LOC vs estimate 17 files/+230 ±30% (runtime +378 vs band 161–299, overage accepted under the captain's standing ruling); AC narrowed: AC-2 wording only
- Cycle 2: NO-GO — review gate, self-verify plus three lenses (1 Material regraded Deferred, 1 Needs-decision regraded up into the verdict), 1 Needs-decision + 3 Deferred risk + 2 Polish fixed in-PR, heading total deferred to DRC-4348; surface 42 files/+2777 LOC vs estimate 17 files/+230 ±30% (round +205; overage accepted under the captain's standing ruling); AC unchanged

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

## Stage Report: review

- DONE: Review depth stated up front as three lenses plus an arbiter — the two the gate set
  (conflict-prone-surface row: `web/` byte pins and `SKILL.md`) plus a dedicated redaction lens over
  the published surface, because the diff touches `aggregate.py`'s credential-sweep table and the
  round's own lens found a bypass there — with the fan-out declared before the first spawn, each lens
  given one question, and the arbiter reproducing every finding against PR #261's head `0d48cfb` in a
  throwaway copy rather than ranking it
  Declared before the first spawn; `## Review depth` carries the tier and the justifying property.
  Each lens ran in its own `git archive` copy of `0d48cfb`; the worktree was never read as a workspace
  and never written. The arbiter reproduced every finding it kept and **refuted three**: F3 does not
  reproduce at the user-visible level, my own 170-vs-178 prose flag dissolved into two different
  fixtures, and the "+188 functional" figure is unreproducible but its conclusion holds under all three
  groupings I could construct (188 / 256 / 290 all inside the declared 161–299 band).
- DONE: AC-1 through AC-6 each reproduced from its own `Verified by:` clause on head `0d48cfb` — the
  falsifiers re-applied where cheap, AC-4 re-run as the two-collector live comparison the
  implementation used, AC-5 read from the capture and re-driven once against this board (this
  session's registered teammates are the fixture; you are one), AC-6's rewritten vocabulary oracle
  attacked with a fresh defeat of your own — plus the redaction property: the documented AWS
  placeholder routed through `subagents[].parent` and through every other new string on the element
  comes back redacted, and no other key added by this PR escapes the sweep
  All six reproduced, none trusted. **AC-1** falsifier (revert `transcript_started_at` to the one-line
  read) → `AssertionError: 1788440966.488734 != None`; the expected value is the fixture's own fourth
  record, so it cannot pass by agreeing with the code. **AC-2** falsifier (drop the
  `working_threshold_sec` gate on the state-feeding list) → `'running 1 subagent' != 'running 2
  subagents'` **and** DRC-4263's pre-existing guard → `'idle' != 'working'`. **AC-3** falsifier (walk
  the lead's transcript instead of the child's) → both grandchildren vanish, two tests fire. **AC-4**
  proved twice: by construction (`roster` referenced at exactly 5 lines, every state consumer still on
  the fresh-gated `subagents`) and by comparison (base vs head in separate processes on a pinned `now`
  across three synthetic stores and the live store — **0 state-bearing fields moved**, head-vs-head
  churn empty); and statically by me — 27 removed test lines total, **zero** mentioning `state`,
  `state_detail`, `last_activity`, `blocked_since` or `spacedock`, and the claimed count of exactly one
  moved `subagents` expectation is exact. **AC-5** re-driven live on this board, same stores, same
  pinned `now`: base `1 published / 0 measured starts / 0 grandchildren`, head `41 published / 41
  measured starts / 20 grandchildren across 6 named parents / keys +active,+parent`. The implementer
  measured 34/34/17/5; the board moved because I am a new teammate with three new lenses. I then took
  the **negative arm** myself once my three lenses had finished: same `41 published / 20 grandchildren`,
  `active` down `4 → 1`, so the stopped workers are **present and inactive rather than absent** — the
  arm the criterion names, observed on my own crew. **AC-6**
  reproduces triage's figures from the capture itself: top-level indices `[3,3,6,3,3,3,3,3]`, all four
  legacy files at 0, five added registry fields with only `isActive` read, `prompt` present only inside
  a list of field *names*. **Redaction property holds**: `AKIAIOSFODNN7EXAMPLE` through `name` and
  `parent` both return `AKIA…REDACTED`; this PR adds exactly two element keys, `parent` (swept) and
  `active` (a boolean), so no added key escapes. `model` is pre-existing and excused *by name* in
  `SAFE_TEXTED_ELEMENT_KEYS`, an excuse verified sound — `safe_text` redacts before bounding, and
  Claude's model goes through `claude_data.py:154`. A new defeat of the AC-6 oracle **did** land
  (duplicate JSON keys, below). Red-first verified independently: `51e448d` gives `failures=4,
  errors=1`, exactly the "five oracles, four failures and one error" claimed.
- DONE: CI read on head `0d48cfb` (every required check, belonging to that head, measurable jobs run
  not skipped since the diff carries code), `mergeStateStatus`, Copilot confirmed absent rather than
  unread, the byte pins re-derived from the assets, the surface re-derived against the merge base, and
  a GO or NO-GO verdict with findings under their disposition labels written as
  `## Stage Report: review` with evidence on its own line, `## Review depth` filled — no edit to the
  branch, no merge, no worktree or branch removed
  13 checks all SUCCESS; all five workflow runs carry `head_sha=0d48cfbe…`; the nine measurable jobs
  each `completed/success`, none skipped. `mergeStateStatus=CLEAN`, `mergeable=MERGEABLE`. Copilot is an
  **absent mechanism**: `gh api /users/copilot` → 404, `requested_reviewers` empty, zero
  `review_requested` timeline events, 0 reviews, 0 inline comments. Byte pins recomputed independently
  **twice** (me and lens 3, neither using the test's own helper): six moved, six match on size and
  digest, and lens 3 additionally checked the eight that did *not* move — all correct. Surface
  re-derived: 41 files, +2052/−100, **net +1952**, matching the implementer's figure exactly. Local
  suite run **once** at load 4.82: **1874 OK, 1 skipped**; no red, so no module needed the solo re-run.
  Worktree left clean at `0d48cfb`, nothing merged, nothing removed.
- FAILED: a GO verdict
  **NO-GO on one reproduced Material finding.** Details under `## Review-finding disposition` below.

### Review-finding disposition

**Material — routes to `implementation`, unchanged, not fixed here.**

- **The `CURRENT ACTIVITY` heading counts two different populations in one sentence, so it prints
  "NONE RUNNING" above a row it draws as running.** `next-session.js:255` scopes `running` to live
  *direct* children (deliberate, so it agrees with the state line — the comment says so); the total in
  the same label is `subagents.length`, which **includes grandchildren**. Reproduced through the real
  node render harness on head, fixture = one idle direct child plus one live grandchild:
  `<span>2 SUBAGENTS · NONE RUNNING</span>` immediately above
  `<div class="next-session-subagent next-live" …><span … aria-label="running">●</span>`. A screen
  reader announces "running" for the row the heading says is not running.
  - *released user and normal workflow*: a lead whose teammate's own worker is running — this
    session's own shape, and the exact case `## Problem` was filed about.
  - *observable harm*: the board's headline answer to "what is it doing" is false at a glance.
  - *affected value AC or boundary*:
    `contract[docs/promise-map.md#p2-what-is-it-doing-and-when-should-i-come-back]` — P2 is backed by
    "named pills for running subagents, **session detail that leads with current activity**", and this
    heading renders inside that section; `promise-map.md` defines move `keep` as "Without this, the
    board says something untrue about the promise." No AC pins the heading, so the claim rests on the
    contract rather than on AC-5 — AC-5's own count (the chrome) and AC-2's `state_detail` are both
    **correct**.
  - *trigger evidence*: deterministic, no timing. Untested at head: the shipped all-idle case asserts
    `NONE RUNNING` on a roster where it is true; zero-direct-live-plus-live-grandchild has no oracle.
  - *provenance worth reading*: review round 1 fixed the **mirror** of this (`running 1 subagent` under
    `3 RUNNING SUBAGENTS`) by narrowing `running` to direct children, and created this one by leaving
    the total wide. The fix introduced its neighbour.
  - *why not file it*: this PR holds the single `web/` slot. A follow-up heading fix needs that slot
    **again**, putting H1's PR 2 behind two `web/` PRs instead of one. Correcting it in this round is
    cheaper for the queue than merge-and-file.

**Needs decision — the task cannot own the scope.**

- **A quiet worker survives under a teammate and still vanishes under the lead.** `own_agents` stays
  fresh-gated at 90 s while children and grandchildren are window-gated at 24 h. Not a regression —
  at base both vanished — but the fix now reaches one of two populations, and a lens dispatched by the
  lead is the commonest case on this board. Extending it changes approved scope (disposition rule 5).
- **One committed capture record has no recorder behind it.** `board_drive_verdict` in
  `teammate-board-drive-…jsonl`: I confirmed **0** occurrences in `scripts/capture_team_registry.py`.
  Its values are booleans and counts, so the privacy rule holds and AC-6 is met; what does not hold is
  provenance, since the README row attributes the file to the recorder and `AGENTS.md` says
  `docs/captures/` carries "never a value a person or a model wrote". Either name the derivation in the
  row or teach the recorder to emit it.
- **The registry demote publishes two authorities on one fact.** Roster `active` is demoted by
  `isActive` while `state_detail` still follows freshness. Reproduced at the collector level by lens 2;
  I could **not** reproduce it at the user-visible level (with `state=needs_input` the lede shows the
  state, not `state_detail`), so I decline to call it user-visible. New in this PR.

**Deferred risk — file in Linear, do not promote.**

- **Duplicate JSON keys walk past the AC-6 vocabulary oracle.** `json.loads` keeps the last duplicate,
  so the discarded value never becomes a node in the walk. I appended a record carrying a synthetic
  marker in a duplicated `record` slot: `test_documentation` → **27 tests OK** while the marker sat in
  the committed bytes. The committed files have no duplicate keys today and every string in both is
  classified, so nothing leaks at head. One-line fix (`object_pairs_hook`). Promote if a hand-edited
  capture ever lands — which finding 6 above shows is a live practice.
- **The oracle's file list is a hardcoded 2-tuple**, so capture number three is walked by nothing; the
  implementer's own defeat #2 was "read one of two files" and the rewrite hardcodes two.
- **The classification generalisation is single-path and Claude-only.** It probes one argument tuple of
  `published_agent`, so a conditionally-string key (`"note": None if active else …`) stays green while
  publishing unclassified operator text on the `active=False` path — which is most roster entries.
- **The 70-char slice runs before the sweep**, so up to 30 characters of secret material survive
  unmarked when the clip lands mid-run. **Pre-existing** — `name` has been `[:70]` — so `parent` adds a
  second instance of an accepted exposure rather than a new class.
- **The published roster is uncapped**: 294 elements / 30 KB on one row in the implementer's own
  measured shape, 38 live today, no cap in the collector and no slice in the detail panel. Already
  reported in the PR body.
- **A pane-dispatched nested teammate is discarded.** The code-path half reproduces in six lines of
  fixture; only the harness premise is unmeasured. Filed correctly, though "not reproduced" understated
  it.

**Polish.**

- **A sentence this PR adds to `docs/design-session-identity.md:504` is false.** "a child whose named
  lead is not a published row is promoted rather than dropped" — my fixture (classified child,
  `teamName` naming a lead with no transcript) publishes **0 sessions**: the child and its worker are
  both invisible, the exact failure the same sentence says cannot happen. The drop is pre-existing; the
  claim is new. Correcting the PR's own new prose is not promotion, so this one is worth carrying in the
  same round it forced.
- **The chrome header's `N subagents` is now a live-only count under an unqualified word**, so it can
  read `0 subagents` while the detail reads `2 SUBAGENTS · NONE RUNNING`. Reproduced; but this is what
  AC-5 *asked for* (`the chrome's running-subagent count equals the number of active entries`), so the
  finding is the wording, not the number.
- AC-2's "pending members contribute neither" is **vacuous as tested** — the pending branch outranks
  Working, so the two halves are mutually exclusive. Behaviour correct; only the AC wording overstates.
  Only the captain may change an AC.
- `agent_start_cache` is path-keyed and never mtime-invalidated (same class as `agent_class_cache`,
  which documents it), its `| None` value is unreachable, and the `read_first_json` fallback is never
  cached — so a stampless transcript pays two reads a pass forever, the case the cache was added for.
- The recorder's `session` field is layout-blind: on a label-named legacy file it would emit two
  characters of operator text, which the oracle's hex pattern then rejects, so it cannot land silently.

### Summary

Three lenses and an arbiter on head `0d48cfb`. The engineering under this PR is strong and the parts
most likely to be wrong are right: the state freeze is genuine, proved both by construction and by a
base-vs-head comparison across four stores with **0 state-bearing fields moved**; the credential sweep
now covers `parent`, proved end to end with the documented placeholder and guarded by a test that fails
loudly when reverted; all six byte pins match the assets under two independent recomputes; and every
acceptance criterion reproduces from its own falsifier, including AC-5 re-driven live on this board,
where this session's own teammates and lenses are the fixture.

**NO-GO on one Material finding**, and it is a heading rather than a mechanism. `next-session.js`
counts live *direct* children for the running clause and *all* elements for the total in the same
sentence, so a teammate parked on a running worker renders `2 SUBAGENTS · NONE RUNNING` directly above
a row carrying `next-live`, a filled dot and `aria-label="running"`. That is the board saying something
untrue on the surface `docs/promise-map.md` names as P2's backing, in the exact shape this issue was
filed about — and it is the mirror of the defect review round 1 fixed, reintroduced by narrowing one
clause and leaving the other wide. No AC pins the heading, and the two counts the ACs do pin are both
correct, so this is a contract claim rather than an AC failure; I am calling it Material because the
statement is false on a released surface and because this PR holds the single `web/` slot, which makes
fixing it here strictly cheaper for the queue than merging and filing a second `web/` PR ahead of H1.

One Polish item is worth carrying in the same round rather than filed: a sentence this PR adds to
`docs/design-session-identity.md` asserts that a child whose lead is unpublished is promoted rather
than dropped, and my fixture shows such a child publishes nothing at all. Everything else — the
retention asymmetry, the demote's two authorities, the uncapped roster, the capture record with no
recorder, and three oracle-completeness holes including a duplicate-key defeat of the AC-6 vocabulary
check — is filed, not promoted. Three findings were refuted rather than passed along. CI is green on
`0d48cfb` with every measurable job run, `mergeStateStatus` is `CLEAN`, and Copilot is an absent
mechanism rather than an unread one. The branch was not edited, nothing was merged, and the worktree
still stands at `0d48cfb`.

## Stage Report: implementation (correction round 1)

- DONE: Material — `next-session.js:255`, the heading's total and its running clause count the same
  population, with the render test the arbiter's fixture describes and the round-1 mixed case kept
  red-able
  `4ce2a3c`. Both clauses count DIRECT children; a live worker beneath a teammate gets a third
  clause. The honest sentence chosen over silence: a live grandchild's row carries
  `aria-label="running"` either way, so a heading saying only `NONE RUNNING` still contradicts what
  a screen reader reads one line down. Two new tests through the real node harness:
  `test_the_heading_never_says_none_running_over_a_running_worker` (one idle direct child + one live
  grandchild) asserts `1 SUBAGENT · NONE RUNNING · 1 WORKER RUNNING BENEATH` and `assertNotIn("2
  SUBAGENTS")` — red at `0d48cfb` with the exact defect (`2 SUBAGENTS · NONE RUNNING` above a
  `next-live` row); `test_the_heading_counts_workers_beneath_a_live_teammate_separately` asserts
  `1 RUNNING SUBAGENT · 2 WORKERS RUNNING BENEATH`, red at `0d48cfb`. Round 1's mixed case is
  unmodified and still red-able: its `assertNotIn("3 RUNNING SUBAGENTS")` fires if `running` is
  widened again. Byte pins recomputed from the assets in BOTH places that pin the page —
  `test_next_page.py` and `test_next_flag.py`, the second found only by running the suite.
- DONE: Needs decision, FIX — `board_drive_verdict` provenance
  `ca4a1c8`. Taught the recorder rather than annotating the row, because the README route would have
  documented a hand-written record in a directory whose contract forbids one. `drive_verdict` derives
  every count from the arm records committed beside it; the five fields no arm can carry are typed
  declared measurements (`--measured KEY=NUMBER`, allowlisted keys, bool or int only).
  `test_the_committed_verdict_is_reproduced_from_the_committed_arms` asserts the recorder reproduces
  the committed record exactly — it would fail if any derived field, including the two `state_detail`
  comparisons, were computed differently. Verified: reproduces byte-identical. Two guards beside it:
  no verdict from a partial drive, and a declared measurement cannot carry text.
- DONE: Needs decision, HELD then FIXED under captain-ruling[2026-09-03] — the 24-hour window gate
  extended to the lead's own `own_agents`
  `ca4a1c8`. `load_subagents` gained `window_sec` and returns every agent inside it with its own
  `active`; the state list filters back to the running ones, so it is one file read rather than two
  calls. `test_a_quiet_agent_the_lead_dispatched_itself_stays_published`: quiet own agent published
  `active: false`, `parent: null`; one aged past the window absent; `state_detail` still
  `running 1 subagent`. Red at `0d48cfb` for the right reason (`quiet-lens` missing from the
  roster). **AC-4 re-proved by the two-collector comparison, as the ruling required** — base and
  head in separate processes on a pinned `now`: live store, 6 sessions, **0 state-bearing fields
  moved**, roster 39→40 and 0→1 on the two sessions holding a quiet own agent; synthetic store,
  **0 moved**, roster 4→5 with `ancient-lens` correctly absent. One pre-existing expectation moved
  and it is the ruling's own effect:
  `test_a_legacy_hex_member_joins_through_its_own_transcript` asserted `subagents == []`; it now
  asserts the shape that proves what the case owns (a STARTED member gone quiet, never a pending
  one), and its `state` assertion is untouched.
- DONE: Needs decision, RECORD — the registry demote is one authority on `active` while
  `state_detail` follows freshness
  `f23ab79`. One paragraph in `docs/design-session-identity.md` beside the demote rule: two answers
  to one question on purpose, disagreeing for up to ninety seconds, with why each side is where it is.
- DONE: Deferred risk, FIX — `object_pairs_hook` so duplicate keys are walked
  `ca4a1c8`. `records()` keeps every pair, parking a displaced duplicate under a slot no vocabulary
  classifies. The arbiter's own defeat replays as caught: appending a record with a duplicated
  `record` key holding a label now fails with
  `['a-label-someone-wrote', 'record <duplicate 6>']`. Last-wins is preserved for every other
  assertion.
- DONE: Deferred risk, FIX — the oracle's file list globs both recorders' names
  `ca4a1c8`. `REGISTRY_GLOB`/`DRIVE_GLOB` replace the hardcoded 2-tuple. Proved by adding a third
  file (`teammate-board-drive-2.1.260-macos.jsonl`) carrying an unclassified string: now red, where
  before it was walked by nothing.
- DONE: Deferred risk, FIX — sweep before slicing, both keys, one test
  `ca4a1c8`. `published_agent` uses `records.redact_clip(…, 70)`, and the three upstream display
  clips are removed so the full string reaches it.
  `test_a_long_subagent_name_is_swept_before_it_is_bounded` is red at `0d48cfb` on both keys with
  `sk-ant-api` published unmarked, and also holds the bound (limit plus a marker's length).
- DONE: Deferred risk, FIX — the classification probe runs the `active=False` path
  `ca4a1c8`. `ELEMENT_ARGUMENTS` covers four shapes the collector actually builds. Proved by
  injecting the finding's own defeat, `"note": None if active else "…"`: the widened probe fails
  with `unaccounted={'note'}`, where the single tuple stayed green.
- DONE: Polish, FIX — the false promotion sentence at `docs/design-session-identity.md:504`
  `f23ab79`. Corrected to what the code does and the drop named. Verified by exercising, not by
  reading: one fresh classified child naming an absent lead, holding one live worker, publishes
  **0 sessions**. The promotion is not implemented here.
- DONE: Polish, FIX — the chrome's `N subagents` under an unqualified word
  `4ce2a3c`. Now `N subagents running`, the wording AC-5's clause implies. Chose it over a bare
  `N running` because the header already reads `N running` for sessions, and two identical
  unqualified words is worse than one. Three chrome assertions moved with it.
- DONE: Polish, FIX — `agent_start_cache`
  `ca4a1c8`. Keyed on `(mtime_ns, size)` like the five caches beside it. The three sub-items
  conflicted, so the resolution is stated: caching the fallback is what makes `| None` REACHABLE, so
  it is cured by being filled rather than deleted — deleting it would have forbidden the fallback
  cache the same item asked for. Three tests in `StartStampCacheTest`: a stampless head is read once
  and not once per pass (red at `0d48cfb` with 3 head reads for 3 calls); a transcript that gains a
  stamp stops reading as unstarted (the guard on caching a null); a rewritten transcript does not
  serve the old start (red at `0d48cfb`, served the previous file's stamp).
- DONE: Polish, FIX — the recorder's `session` field
  `ca4a1c8`. `session_slot` emits the prefix only when it is 8 hex characters and a salted digest
  otherwise, so the guarantee is in the recorder rather than in the oracle downstream. Red at
  `0d48cfb`: a legacy `agent-evidence-skeptic.jsonl` emitted `agent-ev`.
- DONE: Polish, captain's — AC-2's wording, under captain-ruling[2026-09-03]
  Entity line 492: "pending members contribute neither" is now "pending members are never counted as
  running". The test is unchanged; the behaviour was always right.
- SKIPPED: Deferred risk — the uncapped published roster
  Filed by the FO as **DRC-4348**; a cap and a "+N more" convention is a payload-shape decision.
  Measured again this round: 40 elements on this session's own row.
- SKIPPED: Deferred risk — the pane-dispatched nested teammate
  Already filed as DRC-4347.
- DONE: `sync-docs` invoked, its updates on this branch
  `f23ab79`. Found two claims this round's code falsified beyond the two it was sent for.
  `design-runtime-architecture.md`'s cache accounting was stale — nineteen caches with seven
  stat-keyed, against twenty-one and nine — and both omissions are named rather than absorbed
  (`codex_plan_cache`, pre-existing; `agent_start_cache`, this round's), with why it sits apart from
  `agent_class_cache` over the same head bytes. `design-credential-redaction.md`'s swept set gains
  `subagents[].parent` as its third late arrival and its `redact_clip` call-site count moves 14→16.
  `SKILL.md`'s legacy-agent clause states the new retention. Checks a-e run; the marker is
  deliberately not stamped (feature branch). Unresolved and not this branch's prose: `HOW_TO_USE.md`
  and `SECURITY.md` carry pre-existing em dashes from #260's history work.
- DONE: The canonical pre-PR suite run once, and the diff reviewed in the worktree before pushing
  `ruff check` clean, `ruff format --check` clean, `mypy --strict` 112 files clean,
  `lint_embedded.py` clean, `validate_plugins.py` clean, `bump_version.py --current` 0.20.0 with no
  version field moved since the merge base. Suite run **once** at load 6.03: **1881 tests OK, 1
  skipped**, no red, so no module in the four contention-prone ones needed a solo re-run. Script
  tests + `coverage report`: **90.2%** against `fail_under = 73`.
- SKIPPED: AC-5's positive arm re-driven live this round
  Not this round's obligation, so it is skipped rather than failed: the round carried the heading
  fix, the pins and the suite. The arm is already driven twice — by the implementer at `0d48cfb`
  (34 published / 34 measured starts / 17 grandchildren) and independently by the reviewer on its
  own crew (41/41/20) — this round changed no collection path AC-5 exercises beyond the window gate,
  which the two-collector comparison above proves byte for byte, and the re-reviewer spawns lenses
  and is therefore the fixture, so it re-drives on `f23ab79`. Recorded as
  `fo-ruling[2026-09-03]`.
  The measurement behind the attempt stands: the live board had no running worker at any moment I
  could pin (20 direct children, 1 live; 20 grandchildren, 0 live), so the defect arm could not be
  observed on real data here. What I did drive is the negative arm — the shipped
  `nextSessionSubagents` over the live roster under base and head, both reading
  `1 RUNNING SUBAGENT` and agreeing with the live `state_detail`, showing the change is a no-op on
  this shape. The positive arm rests on the two node render tests, the same method the arbiter used
  to reproduce the finding.

### Surface

Round's own surface, `git diff --numstat 0d48cfb..HEAD`: **19 files, +713/-93, net +620** — of which
runtime and web is **+86** across 5 files, the oracles **+403** across 8, the capture recorder
**+109**, and docs **+22**.

Cumulative, `git diff --numstat "$(git merge-base main HEAD)"..HEAD`: **42 files, +2692/-120, net
+2572**; runtime and web **+378** across 20 files.

**Surfaced rather than passed silently.** The declared estimate is +230 net across runtime and docs
with ±30% (band 161–299). The review round accepted the cumulative figure as inside that band under
all three groupings its arbiter could construct; under the grouping I can construct — runtime and
web only, excluding tests, docs, the capture recorder and the capture files — the cumulative sits at
+378, above the band. Every line of this round's own +620 is an item the FO or the captain
authorised, and none of it narrows an AC. I did not treat that as settled, because it is a tolerance
question and disposition rule 5 puts those above an ensign.

**Answered.** `fo-ruling[2026-09-03]`: accepted by the First Officer under the captain's standing
ruling of the same day on this exact shape. No design reset is required and the estimate is not
retro-fitted; the overrun is recorded here rather than absorbed.

### Summary

Fifteen authorized items closed in one pass, including both the captain approved on the day: the
lead's own agents now keep the same 24-hour retention as its children and grandchildren, and AC-2's
vacuous clause is reworded. The Material finding is fixed by making every number in the heading name
its own population rather than by narrowing one clause and leaving another wide, which is how round 1
created it. Every behavioural fix was watched red at `0d48cfb` first, and three of them are proved by
replaying the reviewer's own defeats: the duplicate-key walk-past, the third unwalked capture, and
the conditionally-string key on the inactive path. AC-4 was re-proved as the ruling required, by two
collectors in separate processes over the same stores, with 0 state-bearing fields moved on the live
store and on a synthetic one.

Two things I raised rather than decided, both since ruled on by the FO under
`fo-ruling[2026-09-03]`. AC-5's positive arm was not re-driven live this round, because no worker
was running on this board at any moment I could pin; it is driven twice already, nothing this round
changed the paths it exercises beyond the window gate the two-collector comparison proves, and the
re-reviewer is itself the fixture — so it is skipped here and re-driven on `f23ab79`. And the
cumulative runtime surface is above the declared band under the grouping in the Surface section;
that is accepted, with the figure recorded rather than absorbed.

New head `f23ab79`, pushed to PR #261. Nothing merged, nothing removed.

## Stage Report: review (cycle 2)

- DONE: Review depth chosen from the property of the correction round and stated up front, then each of the fifteen items in `## Stage Report: implementation (correction round 1)` verified against PR #261's head `f23ab79` at the SHA, stated closed or not with the line cited, the round's named red-first mutations re-applied in a throwaway copy where cheap, and the byte pins recomputed independently from the assets in both files that pin the page
  **Fourteen of fifteen closed; one landed partially.** Heading (`4ce2a3c`): both clauses count DIRECT children (`next-session.js:260-262`), a third clause counts live grandchildren; reverting the block to `0d48cfb` in a `/tmp` copy renders `2 SUBAGENTS · NONE RUNNING` directly above a `next-live` row carrying `aria-label="running"` and both new tests go red — the round-1 defect verbatim. Window gate (`ca4a1c8`): `claude.py:555-563` passes `window_sec=window_hours*3600`, `:565` filters the state list back to `active` — see AC-4 below. Sweep-before-slice (`ca4a1c8`): `claude.py:335,339` call `records.redact_clip(…, 70)`; all three upstream `[:70]` clips are gone (`:105`, `:388`, `:492` at `0d48cfb`, absent at head) and `aggregate.py:381` joins `("subagents", ("name", "parent"))`. `object_pairs_hook` at `test_documentation.py:142`; `REGISTRY_GLOB`/`DRIVE_GLOB` at `:202-206` replace the hardcoded 2-tuple; `ELEMENT_ARGUMENTS` at `test_contracts.py:964-969` covers four shapes including the `active=False` and `active=None` paths; `session_slot` at `capture_team_registry.py:96-97` emits 8-hex or a salted digest. Start-stamp cache stat-keyed at `state.py:101`, `claude_data.py:57-70`. Docs: the false promotion sentence is replaced and its replacement **reproduces** — my own fixture (one fresh classified child naming an absent lead, holding one live worker) publishes **0 sessions**, exactly as `design-session-identity.md:509-516` now claims; `SKILL.md`'s pruning claim is corrected to demote-only; the cache accounting reproduces (21 cache fields in `state.py`, 9 stat-keyed) and so does `redact_clip`'s 16 call sites (17 in `cargento_runtime/`, less the intra-module delegation at `records.py:442`). AC-2's rewording is at entity line 499. **Not fully closed: the `board_drive_verdict` provenance item — see the NO-GO finding.** Byte pins recomputed independently from the assets at the SHA in BOTH files: **56 pins, all MATCH** (14 JS parts × size+digest, `styles.css`, the assembled page in `test_next_page.py:584,586` AND `test_next_flag.py:67,69`, 9 font payloads, 2 OFL notices); the moved-pin set exactly equals the changed-asset set in both directions; appending one byte to `next-boot.js` in a `/tmp` copy turns both files red (`11244 != 11245`, `324669 != 324670` twice).
- DONE: AC-1 through AC-6 re-verified on head `f23ab79` from their own clauses — AC-4 re-run as the two-collector live comparison and AC-5's positive arm re-driven live by me — plus the redaction property at the new clip boundary
  **AC-1** on my own preamble fixture: base publishes `started_at: None`, head publishes `1788445734.33786` = the 4th record's stamp **exactly** — the falsifier's stated behaviour observed on the base side. **AC-2** from its own clause on my own fixture (two classified children, one fresh, one aged past `working_threshold_sec` inside `window_hours`, a roster listing both): both published, stale `active: false`, fresh `active: true`, `state_detail` = `running 1 subagent`; its named falsifier applied in a throwaway copy (drop the fresh gate on the children arm) flips it to `running 2 subagents` and reddens the repo's own two guards including DRC-4263's. **AC-3**: grandchildren published with `parent` = the child's agent name, the teammate's own `parent` null; base publishes neither. **AC-4 re-run as two collectors in separate processes on a pinned `now`** — live store: 2713 sessions × 32 fields = **86,816 comparisons, 0 state-bearing fields moved**, and non-vacuous because the roster goes **1 → 48 elements** over the same run (`active`/`parent`/`started_at` present on 100% of them); synthetic store: **0 moved**, `ancient-lens` correctly absent, `quiet-lens` published inactive. **AC-5 both arms driven live by me on `f23ab79`, served from my worktree on port 4599 against the same stores** — positive: 3 lenses under `parent: "spacedock-ensign-drc-4344-review-2"`, all `active: true`, measured starts `1788445857.316 / 1788445868.111 / 1788445880.487`, the real shipped JS rendering `1 RUNNING SUBAGENT · 3 WORKERS RUNNING BENEATH` over 44 rows with 4 `next-live`, chrome live count 4 = the number of active entries; negative: the same three **present and inactive rather than absent**, same start stamps, heading correctly `1 RUNNING SUBAGENT`. **AC-6**: the capture file exists, is in the README Files table with provenance, and carries 0 `prompt`/`message` values across 17 records. **Redaction boundary**: the placeholder shape mid-clip comes back marked on both `name` and `parent` at length 76 ≤ the 79 bound, and at base 52–56 characters of key body published raw on both keys — the fix is stronger than its own commit message claims.
- DONE: CI on head `f23ab79`, `mergeStateStatus`, Copilot confirmed absent, the surface re-derived, and a GO or NO-GO verdict with any new or surviving finding under its disposition label, no edit to the branch, no merge, no worktree or branch removed
  **13/13 checks `success`, every one with `head_sha` = `f23ab79`**, and every measurable job RAN rather than skipped (Lint, mypy --strict, Runtime floor 3.11, Tests+coverage, Tests on ubuntu/macos/windows, latest-client-smoke, actionlint, validate, version-guard, Detect, quality-gate). `mergeStateStatus: CLEAN`, `MERGEABLE`, `OPEN`. **Copilot absent** — 0 reviews, 0 inline review comments, 0 requested reviewers. Suite run **once** at load 1.77→3.06: **1881 tests OK, 1 skipped**, no red, so no solo re-run was owed in the four contention-prone modules; script tests 205 OK; `coverage report` **90.2%** against `fail_under = 73`; ruff, ruff format, mypy (112 files), `lint_embedded`, `validate_plugins`, `bump_version --current` 0.20.0 all clean, no version field moved since the merge base. Surface re-derived: 42 files, +2692/-120, net **+2572**; runtime+web net **+376** — inside the round's own figure and accepted by the FO, not my question. Branch untouched (`git status --porcelain` empty, HEAD still `f23ab79`), nothing merged, worktree and branch intact, my port-4599 server stopped and the captain's 4553 left running.

### Findings under their disposition labels

**Needs decision — the one the verdict rests on. Routes to `implementation`, unchanged, not fixed here.**

- **The `board_drive_verdict` provenance item did not fully land, and the README sentence it added is false.** `drive_verdict` genuinely derives its counts from the arms — I re-derived the committed verdict byte-identically and confirmed both guards refuse a partial drive and refuse text. But one of the three arms it derives from cannot be a recorder output. Running the real `drive_arm` and diffing key sets: `positive` and `negative` match it exactly; **`control_before` lacks five keys `drive_arm` emits unconditionally** (`active_true`, `active_false`, `active_null`, `chrome_published_subagents`, `chrome_running_subagents`) **and carries one it never emits** (`registered_members`, value 3). `docs/captures/README.md` — the row **this PR writes** — states "Every record in the file comes from that recorder" and names `registered_members` among "the five fields no arm can carry". Both are false about `control_before`, and five of the verdict's derived fields rest on it. `test_the_committed_verdict_is_reproduced_from_the_committed_arms` cannot see this: it reads the arms as given data and never checks an arm is itself a `drive_arm` output, and its `assertNotIn` guard checks only `positive`.
  - *released user and normal workflow*: **no** — repository evidence, `scripts/` is not in `CARGENTO_RUNTIME_FILES`. This is why it is Needs decision rather than Material.
  - *observable harm*: `docs/captures/` is the directory whose whole value is that a reader can re-derive a figure; the row asserts machine provenance for a record a person wrote.
  - *affected value AC or boundary*: `contract[AGENTS.md#documentation]` — `docs/captures/` carries "never a value a person or a model wrote". The same contract round 1 cited when it raised this finding's parent.
  - *trigger evidence*: key-set comparison above, deterministic, reproduced by me against the real recorder.
  - *why it blocks*: round 1 authorized a FIX with two routes ("name the derivation in the row, or teach the recorder to emit it"). The recorder was taught for the verdict and not for this arm, while the row's claim was strengthened. Reporting the item closed would be false. It is a small, mechanical fix either way — re-drive `control_before` through the recorder and drop `registered_members` from the arm, or say in the row that `control_before` predates the recorder and name the figures resting on it.

**Deferred risk — file, do not promote into this PR.**

- **The heading's total no longer counts the rows it sits above** (lens A, graded Material; **regraded by me**). `next-session.js:290` prints `direct.length` while `:265` renders every element, so the all-idle branch reads `21 SUBAGENTS · NONE RUNNING` above **44 rows** on this board right now, and `1 SUBAGENT · NONE RUNNING` above 2 at its smallest. Reproduced independently, before the lens reported, through the real shipped JS on the live payload. **Regraded because field 3 does not establish**: round 1's Material rested on `contract[docs/promise-map.md#p2-what-is-it-doing-and-when-should-i-come-back]` and its `keep` test, "the board says something untrue about the promise" — P2's content is *what it is doing*, and every liveness clause is now correct in every shape both the lens and I enumerated. This is a cardinality that no AC and no promise pins, over rows that are individually visible and attributed. Promote-to-material condition: DRC-4348's cap and "+N more" landing, at which point a truncated list under an undercounting total makes the real size unknowable; or an AC pinning the section total to its rows.
- **Removing `label[:70]` un-bounds `state_detail`** (lens C). `claude.py:105` dropped the clip on the grounds that `published_agent` redacts and then bounds — true of the roster path, but the same label is interpolated raw into `state_detail` at `:780`. Reproduced base vs head on one fixture: divergence begins at label length **71** (34 and 70 chars agree; 80 → 99 vs 109; 200,000 → 99 vs **200,029**, payload 989 → 200,952 bytes). Not a credential exposure — `state_detail` is swept. **Trigger unobserved**: every registry member name on this machine is ≤ 42 characters, 0 over 70. Promote when a name over 70 characters appears, at which point AC-4's `state_detail` freeze breaks and an unbounded untrusted string reaches `/api/data`, every SSE snapshot and the browser notification body.
- **`--lead` is unvalidated free text and reaches the arm and verdict records** (lens C). `capture_team_registry.py:409` has no pattern; the file's only `re.fullmatch` is `session_slot`'s. Same reasoning that produced `session_slot` this round, not applied to the one other string on the verdict. Committed value is 8-hex, so nothing is wrong in the file today.
- **`0 SUBAGENTS` over a populated list** (lens A). Unreachable today, verified structurally rather than taken: `claude.py:670` appends the teammate's parentless entry unconditionally before the grandchild loop at `:686`, so a grandchild cannot outlive its parent's row.

**Polish — declined.**

- The chrome's `N subagents running` has no singular arm, so `1 subagents running` is reachable. **Pre-existing, verified at base** (`ff8280a` reads `${counts.subagents} subagents`, also unsingular); this round changed the wording and the counted population, both as AC-5's clause asks. Not promoted.
- The new boundary test uses `lead = "a" * 60`, the offset at which base leaked the prefix only; at `lead = "x"` base leaked 52–56 body characters. Red at base either way, but it understates its own defect.
- Duplicate `--arm` names last-win silently, and `int()` accepts `1_0`, padded, unicode and negative digits. No text channel, so the privacy guarantee holds.

### Summary

Self-verify by reproduction plus three parallel lenses, arbitrated by reproducing every finding
rather than ranking it; the grading moved on two of them, one down from Material and one up into the
verdict. Fourteen of the fifteen authorized items are closed and cited at the SHA, the byte pins are
independently recomputed in both files that pin the page and bite in both, and AC-1 through AC-6 are
reproduced from their own clauses rather than trusted — AC-4 as 86,816 base-versus-head comparisons
with **0 state-bearing fields moved** over a roster that simultaneously grows 1 → 48, and AC-5 driven
live in both arms off my own lenses, the fixture the correction round could not obtain. CI is 13/13
on `f23ab79`, `CLEAN`, Copilot absent.

**NO-GO on one finding.** The `board_drive_verdict` provenance item, authorized as a FIX in round 1,
landed for the verdict's derivation and not for one of the three arms it derives from — and the
README row this PR writes now asserts machine provenance for a record no invocation of the recorder
can produce, naming `registered_members` as a field no arm carries while an arm carries it. The
runtime is not implicated and no released user is harmed, which is why it is Needs decision and not
Material; it blocks because it is the one authorized item that cannot honestly be reported closed,
and because it is a ten-line correction in the directory whose only value is that its figures can be
re-derived. Everything else is GO. Nothing was edited, merged or removed.

## Stage Report: implementation (correction round 2)

- DONE: **the blocker** — `control_before` re-driven through the recorder against the shipped collector, `registered_members` dropped from the arm, the verdict re-derived, and `test_the_committed_verdict_is_reproduced_from_the_committed_arms` still byte-identical
  Preferred route taken, not the annotation route: `ff8280a` extracted with `git archive` to `/tmp/drc4344-control`, served on port 4611 against the same stores, its `/api/data` payload saved and run through the real `drive_arm`. The arm's key set now equals `positive`'s exactly (asserted, not eyeballed); `registered_members` is absent from it and stays a declared measurement on the verdict. Verdict re-derived by `drive_verdict` from the three arms: `before_published` 2 → **1**, `before_with_a_measured_start` and `before_grandchildren_reachable` unchanged at 0, and both `state_detail` comparison booleans unchanged (`1 <= 1` direct children). The control's own `at` is its own re-drive stamp; the other two arms keep theirs. The re-driven control still reproduces every AC-1/AC-2/AC-3 gap it was there to establish — element keys `model, name, started_at` with no `active` and no `parent`, `published_with_a_null_start: 1`, `grandchildren: 0` — because that is a shape claim and does not rest on how many teammates were live. Server on 4611 stopped; the captain's 4553 untouched.
- DONE: that test strengthened so it checks each arm's key set against `drive_arm`'s, not only the verdict
  `test_every_committed_arm_carries_the_key_set_the_recorder_emits` (`scripts/tests/test_capture_team_registry.py:228`) runs `drive_arm` over the class fixture and asserts every committed arm's keys, less the envelope, equal what it emits. Asserts that no record in the file can be a hand-written arm. **Red-first proved on the real bytes**: `git show f23ab79:` the capture back into place turns it red naming `arm='control_before'` only, then restored — the reproduction test stayed green on those same bytes, which is exactly the blind spot.
- DONE: `state_detail` re-bounded where the label is interpolated, with one test at label length 71+
  `records.redact_clip(label, 70)` at `claude.py:789` — `redact_clip` and not a slice, for the ordering that function owns. `test_a_long_member_name_cannot_grow_the_state_line` (`test_claude.py:2762`) collects twice with names of 70 and 200 characters and asserts equal `state_detail` length, pinned at `70 + len(" has not started, waiting 5m")`. Watched fail first at the pre-fix code: **98 != 228**. The `load_team_members` comment that licensed the removal is corrected: `published_agent` bounds the element's copy, not the label.
- DONE: `--lead` validated on `re.fullmatch` of 8 hex, the same rule `session_slot` applies
  One shared `SESSION_PREFIX` constant now serves both, so the recorder has one rule rather than two. `test_a_lead_that_is_not_a_session_prefix_is_refused` covers a free-text note, uppercase, short, long and empty; each must exit and write nothing. Red first — the note reached three records.
- DONE: duplicate `--arm` names refused, and declared counts parsed with a strict non-negative decimal pattern
  `parser.error(f"--arm {name} given twice")` before the arm is built, and `declared_value` raises unless `re.fullmatch(r"[0-9]+")`. `test_a_repeated_arm_name_is_refused_rather_than_silently_replaced` and `test_a_declared_count_must_be_plain_decimal_digits` (`1_0`, ` 7`, `7 `, `+7`, `-3`, `٣`, `0x10`). Both red first: the duplicate wrote three records at exit 0, and every one of those seven values was accepted.
- SKIPPED: "0 SUBAGENTS over a populated list" — no change, as authorized
  Recorded as the round was asked to: unreachable because `claude.py:673` appends the teammate's own parentless entry unconditionally **before** the grandchild loop that appends at `:692`, so the list cannot hold a grandchild without holding the direct child that produced the `1`. A zero heading over a populated list therefore needs a published element with no parent row above it, which no path builds.
- SKIPPED: the heading total counting direct children while rows show every element — not changed again this round
  Regraded Deferred by the reviewer and promotes with DRC-4348's roster cap; the round's constraint says leave it.
- DONE: chrome gains the singular arm so `1 subagents running` cannot render
  `subagentLabel` beside the existing `gateLabel` in `next-chrome.js:258`. `test_a_single_running_subagent_reads_in_the_singular` asserts `1 subagent running` and refuses `1 subagents`; watched fail first on the plural-only string. The only `web/` change in the round.
- DONE: the redaction boundary test states its own defect fully, at `lead = "x"` alongside the 60-offset case
  `test_a_long_subagent_name_is_swept_before_it_is_bounded` (`test_contracts.py:926`) now loops both offsets. Measured why the pair is needed: at lead 60 the pre-round slice published **0** body characters but **no marker**, at lead 1 it published a **56-character run of key body** unmarked. One offset reads as truncation; the two together read as the leak.
- DONE: byte pins recomputed from the assets in both pinning files, never resolved textually
  Recomputed by importing `frontend_page` and hashing: exactly one part moved (`next-chrome.js` 15_883 → 15_973, +90) and the assembled page moved by the same 90 (324_669 → 324_759), consistent in both directions. Updated in `test_next_page.py` (part + assembled) and `test_next_flag.py` (assembled).
- DONE: canonical suite run once, no Linear write, pushed without merging, surfaces declared
  `uptime` load 3.08 at the start, so no contention re-run was owed and none of the four fragile modules went red: **1883 tests OK, 1 skipped** (1881 before, +2 from this round's dashboard tests), script tests **19 OK** in the recorder module and 205 across the seven others, `coverage report` **90.2%** against `fail_under = 73`. `ruff check`, `ruff format --check` (151 files), `mypy` (112 files), `lint_embedded`, `validate_plugins`, `bump_version --current` 0.20.0 all clean; no version field moved since the merge base; `claude plugin validate --strict` and `agy plugin validate` both pass. No Linear call was made. Pushed to `spacedock-ensign/drc-4344`; PR #261's head is now `5314e09` and nothing was merged. CI on that head came back **13/13 pass**, and the run carrying the gate's jobs reports `head_sha` `5314e09` rather than a superseded one; `mergeStateStatus` is `BLOCKED` on review, as it should be.

### Surface

Round: **12 files, +246/-41, net +205** (`git diff --numstat f23ab79..5314e09`). Cumulative against the merge base: **42 files, +2899/-122, net +2777**. Two-thirds of the round is test text — 115 lines of it in `scripts/tests/test_capture_team_registry.py`, which is the price of the arm oracle and three refusal tests each covering their whole input class rather than one example.

### Summary

New head **`5314e09`**. The one NO-GO is closed on the route the gate preferred rather than the
cheaper one: the control arm is now genuinely a `drive_arm` output, driven against `ff8280a` served
from a `git archive` copy on a spare port, and the README row states what changed and when instead of
asserting machine provenance for a record nobody ran. The reproduction test's blind spot is closed by
an oracle that compares each arm to what the recorder emits, proved red on the exact bytes the gate
rejected. Three inputs that reach a captured record now carry the rule `session_slot` already had,
`state_detail` is bounded again where it publishes, and both polish items landed.

Two items are deliberately unchanged and reported as such: the heading total, which the reviewer
regraded and which promotes with DRC-4348, and the `0 SUBAGENTS` case, whose unreachability is now
recorded with the line that makes it so. The one judgement worth the gate's attention is that the
re-driven control counts a different board population than the two patched arms — the same stores at
a later moment — so the verdict's before/after figures are no longer one snapshot. The README row says
so, and what the control is there to establish is the element's shape and its null start, which no
population changes.

## Stage Report: review (cycle 3)

- DONE: Review depth chosen from the property of the correction round and stated up front — the three-lens pass at `0d48cfb` stands and is not repeated; new are the heading fix, the window gate extended to the lead's own agents, sweep-before-slice, the oracle hardenings, the start-stamp cache, the recorder's verdict derivation, and the doc corrections — then each of the eight items in `## Stage Report: implementation (correction round 2)` verified against PR #261's head `5314e09` at the SHA, stated closed or not with the line cited, the round's named red-first mutations re-applied in a throwaway copy where cheap, and the byte pins recomputed independently from the assets in both files that pin the page
  **All eight closed, the two SKIPPED ones as the authorized no-changes.** (1) **The blocker is closed.** All three committed arms now carry the identical 25-key set; `registered_members` is absent from every arm and present only on the verdict, so the README's "five fields no arm can carry" is true of the bytes. I re-derived the control from the payload shape its own record describes and every field matched except the two `state_detail_*` ones I could not reconstruct without the real string — a hand-written record does not survive that. Red-first on the exact rejected bytes: `git show f23ab79:` the capture into a `git archive` copy turns `test_every_committed_arm_carries_the_key_set_the_recorder_emits` red naming `arm='control_before'` **only**, missing the five keys and carrying `registered_members`, while `test_the_committed_verdict_is_reproduced_from_the_committed_arms` stays **green** on those same bytes — the blind spot, demonstrated rather than described. (2) `state_detail` re-bounded at `claude.py:789` via `records.redact_clip(label, 70)`; `test_a_long_member_name_cannot_grow_the_state_line` green at head, and restoring `f23ab79`'s raw interpolation in a throwaway copy gives **98 != 228**. (3) The recorder refuses every input class from the CLI, nothing written in any arm: five bad `--lead` values (free text, uppercase, short, long, empty) exit 2 with no file; a duplicate `--arm` exits 2 with no file; all seven declared-count values (`1_0`, ` 7`, `7 `, `+7`, `-3`, `٣`, `0x10`) exit 2 with no file, against a `--measured registered_members=7` control that writes all four records — the positive control that makes the seven non-vacuous. (4) `next-chrome.js:258-259`'s `subagentLabel` renders `1 subagent running` through the real shipped JS; reverting to the plural-only string renders `1 subagents running` and reddens the test. **All 26 pins recomputed by me from the assets** (14 JS parts, `styles.css`, 9 base64-decoded font payloads, 2 OFL notices) — every one MATCH — and the assembled page recomputes to `324_759` with the pinned digest in **both** `test_next_page.py` and `test_next_flag.py`. The moved-pin set equals the changed-asset set in both directions: `next-chrome.js` is the round's only changed web asset, and appending one byte to it reddens three assertions (`15973 != 15974`, `324759 != 324760` twice). (5) The boundary test loops both offsets: with the pre-fix `[:70]` slices restored, **four** subtest failures — `lead=1` and `lead=60` × `name` and `parent` — at 1 the whole 64-character value published unmarked, at 60 only the key prefix survived the cut, which is the pair the round said it needed. (6/7) The two SKIPPED items are unchanged and their reasons hold at head: no web asset but `next-chrome.js` moved, so `next-session.js`'s heading is untouched; and the parentless entry is still appended unconditionally at `claude.py:674` **before** the grandchild loop at `:689`, so a populated list cannot carry a zero total. (8) `docs/design-credential-redaction.md`'s "seventeen call sites" reproduces: 18 `redact_clip` invocations in `cargento_runtime/`, less the intra-module delegation at `records.py:442`.
- DONE: AC-1 through AC-6 re-verified on head `5314e09` from their own clauses — AC-4 re-run as the two-collector live comparison (base `ff8280a` vs head, pinned `now`, live and synthetic stores) and AC-5's positive arm re-driven live by you, since you spawn lenses and are therefore the fixture: with your lenses running, `/api/data` carries them under your name with `active` true and a measured start, the session detail heading reads the three-population sentence correctly for your shape, and the negative arm after they finish shows them present and inactive — plus the redaction property at the new clip boundary (a long name and parent carrying the documented placeholder mid-clip come back marked)
  **AC-1/AC-2/AC-3**: the seven `DispatchedTeammateTest` cases green at head, each the case its criterion names. **AC-4 re-run as two collectors in separate processes on a pinned `now` against the same live stores**: **2713 sessions × 32 non-roster fields = 86,816 comparisons, 0 state-bearing fields moved**, `state`/`state_detail`/`last_activity` each on 0 sessions, while the roster simultaneously goes **0 → 49 elements** with `active` and `parent` on all of them and 49/49 measured starts; a 24-hour-window pass gives the same 0 over 6 sessions with the roster at 1 → 50. `test_claude.py` is **purely additive this round (0 deleted lines)**, so no frozen expectation was edited. The new bound cannot bite here and I measured why: the largest registry member label on this machine is **42 characters, 0 over 70** — the synthetic arm is the repo's own unmodified `state`/`state_detail`/`last_activity` cases rather than a second live process, which is what AC-4's clause actually asks for. **AC-5 re-driven live by me on head, both arms.** Positive: I dispatched one worker of my own and sampled the collector six times over 40 s — the element appears under `parent` = my own name, `active: true`, with a measured start, `active_total` 2; the real shipped JS on that live payload renders the detail heading **`1 RUNNING SUBAGENT · 1 WORKER RUNNING BENEATH`** over **47 rows with 2 `next-live`**, and the chrome reads `1 running · 2 subagents running` — the chrome count equals the number of active entries, as the clause requires. Negative: the read taken before I dispatched anything shows cycle 2's **three** finished lenses still attributed to my name, **present and inactive**, each keeping its measured start. `state_detail` stayed `running 1 subagent` throughout, counting no grandchild. **AC-6**: the capture file exists with 17 records over four record kinds, is in the README Files table with its provenance, and `test_documentation`'s positive-vocabulary check over it is green. **Redaction boundary**: green at head on both offsets and both keys; red four ways at base, as above.
- DONE: CI on head `5314e09` (all thirteen checks belonging to that head, measurable jobs run), `mergeStateStatus`, Copilot confirmed absent, the surface re-derived, and a GO or NO-GO verdict with any new or surviving finding under its disposition label, written as `## Stage Report: review (cycle 3)` with evidence on its own line and `## Review depth` extended — no edit to the branch, no merge, no worktree or branch removed
  **13/13 `success`, every check-run's `head_sha` = `5314e09`**, and each measurable job RAN rather than skipped (Lint, mypy --strict, Runtime floor 3.11, Tests + coverage, Tests on ubuntu/macos/windows, latest-client-smoke, actionlint, validate, version-guard, Detect, quality-gate). `mergeStateStatus: CLEAN`, `OPEN`. **Copilot absent** — 0 reviews, 0 inline review comments, 0 requested reviewers. Suite run **once** at load 3.34: **1883 tests OK, 1 skipped**, plus **209 OK** across the eight script modules, so no failure appeared in the four contention-prone modules and no solo re-run was owed; `coverage report` **90.2%** against `fail_under = 73`. `ruff check`, `ruff format --check` (151 files), `mypy` (112 files), `lint_embedded`, `validate_plugins`, `bump_version --current` 0.20.0 all clean; **no version field moved since the merge base** (the half nothing local checks, run by hand); `claude plugin validate --strict` and `agy plugin validate` both pass. Surface re-derived: round **12 files, +246/-41**; cumulative **42 files, +2899/-122** — both agree with the round's own figures. Branch untouched (`git status --porcelain` empty, HEAD still `5314e09`), nothing merged, worktree and branch intact; every reproduction ran in `/tmp` `git archive` copies. My one dispatched worker finished and no server was started.

### Findings under their disposition labels

**No new finding, and the cycle-2 blocker is closed.** The `board_drive_verdict` provenance item that
carried the cycle-2 NO-GO reproduces as fixed: the arms' key sets are identical, `registered_members`
lives only on the verdict as a declared measurement, and the README row states the control's own
re-drive, its own `at`, and the population caveat instead of asserting a provenance it did not have.

**Deferred risk — filed, not promoted.** The heading total counting direct children while rows show
every element (promotes with DRC-4348's roster cap). The `0 SUBAGENTS` case, unreachable at
`claude.py:674` before `:689`. Both were left unchanged this round, as authorized.

**Polish — declined, pre-existing.** Three other collectors still bound a subagent label with a bare
`[:70]` (`goose.py:93`, `codex.py:168`, `opencode.py:94`). Present at base, outside this PR's diff,
and covered by the `aggregate._redact_published_text` backstop. Naming it here so a reader of item 5
does not mistake the claim for a codebase-wide one; not promoted.

### Summary

**GO.** Self-verify by reproduction, chosen from the correction round's shape and stated before the
work: eight bounded items with their own red-first mutations, and a runtime diff of one bound. All
eight closed at the SHA, five of them re-falsified in throwaway `git archive` copies — including the
one that matters most, where the exact bytes the cycle-2 gate rejected turn the round's new arm
oracle red while the older reproduction test stays green, which is the blind spot the round claimed
to close, closed. All 26 byte pins recomputed from the assets in both pinning files and biting in
three places. AC-1 through AC-6 reproduced from their own clauses rather than trusted: AC-4 as 86,816
base-versus-head comparisons with **0 state-bearing fields moved** over a roster that simultaneously
goes 0 → 49, with the reason the new bound cannot bite here measured (42 characters, 0 over 70); AC-5
driven live in both arms on this head off a worker I dispatched for the purpose, the shipped JS
rendering the three-population sentence correctly for that shape.

CI is 13/13 on `5314e09` with every measurable job run, `mergeStateStatus` is `CLEAN`, Copilot is
absent, and the surface matches the round's own figures. Nothing was edited, merged or removed.

## Stage Report: review (post-merge closeout)

- DONE: The six `## Post-merge Linear reconcile` steps run in order against the merged state (PR #261, merge commit `0f0d4a7`): step 1 DRC-4344's Linear state verified or moved to `Done`; step 2 the `Steer before waste` milestone description corrected wherever the merge made it false — the DRC-4344 line under "What remains" — built by script from a fresh capture with an exactly-once assertion and a one-hunk diff; step 3 the project overview's "As of" block re-derived from live label-filtered queries and refreshed only where a figure changed; step 4 nothing blocked by DRC-4344 exists, said so; step 5 the relation set left alone unless a `blocks` edge is found; step 6 the move is `sharpen`, so no promise wording changes — said explicitly, and any P2 wording the promise map now understates named for the next sync-docs pass rather than edited
  Merge verified on `main` at the SHA rather than from `gh pr diff`: `git show --stat 0f0d4a7` is 42 files, +2899/-122, committed 2026-09-04T07:27:00+08:00 (2026-09-03T23:27:00Z).
  Step 1 — verified, not set. Already `Done`, `completedAt` 2026-09-03T23:27:03.608Z, 2.6 seconds after the merge, so the GitHub integration moved it and this stage made no state write.
  Step 2 — one edit to `Steer before waste`, built by `/tmp/drc4344/ms.py` from a fresh `get_milestone` capture. The DRC-4344 line asserted present exactly once (the script exits non-zero on any other count), diff printed exactly 1 hunk for 1 authorized edit, and a second assertion proved every other line byte-identical and in order. Deletion, not a shipped section: that milestone carries no shipped section today, and the live capture confirmed the convention before I chose.
  Step 3 — six figures changed, re-derived rather than adjusted, by `/tmp/drc4344/asof.py` from four state-filtered `list_issues` queries (unstarted 8, started 3, backlog 37, triage 0). As-of heading to 2026-09-04; board items 24 open / 24 closed to 23 / 25; sixteen shipped to seventeen (+H1); Release 3 ten to nine (−H1); open issues 43 to 48, of which 24 board items to 23 and 19 defects-or-engineering to 25; by move sharpen 5→7, new 8→7, none 11→15. Board items were identified as issues carrying a `release:*` label — that derivation reproduces the block's own independently-written "48 board items" exactly (23 open + 17 shipped + 8 cancelled), which is what makes it more than a restatement. Re-derived identical and left untouched: 57 candidate signals, 9 pre-project, the eight cancelled, Release 1 complete, Release 2 two, `later` twelve, keep 6, extend 13, unlabelled 0.
  Step 4 — nothing blocked. `blocks` was empty before the merge and after it, so no issue became newly free and nothing was moved to `Todo`. A no-op with a reason, not an omission.
  Step 5 — relation set left alone, correctly. Step 5 fires only on a `blocks` edge whose blocked side is still open; there is no `blocks` edge at all, so there was nothing to convert and nothing was removed.
  Step 6 — labels are `move:sharpen` and `journey:mid-flight`; a `sharpen` merge changes no promise wording, so `docs/promise-map.md`, the README lede and the project's promise table all stand, and nothing is handed to the next `sync-docs` pass as a promise change. Named for that pass and deliberately not edited: P2's backing clause at `docs/promise-map.md:71` reads "named pills for running subagents", which now understates the shipped capability twice — a teammate pill carries a measured elapsed, its own model and its own liveness rather than a bare name (AC-1, AC-2), and a finished or quiet teammate stays published rather than being only one of the running ones.
- DONE: A receipt comment posted on DRC-4344 naming all six edits, PR #261 and merge commit `0f0d4a7`, the three follow-ups it filed (DRC-4346, DRC-4347, DRC-4348), with the relation set read back after every write and every emphasis-boundary move or unrequested edge reported rather than repaired
  Comment `da744a90-2a7d-4ed4-a7f4-0f4299d202ff`, posted 2026-09-03T23:35:39Z; the returned body is byte-identical to what was sent, so the receipt took no emphasis damage.
  Relations read back three times — at entry, after the two writes, and after the comment. Identical every time: `blocks: []`, `blockedBy: []`, `relatedTo: [DRC-4223, DRC-4118, DRC-4263, DRC-4020, DRC-4044, DRC-4348, DRC-4347, DRC-4346]`. No unrequested edge appeared and no `blocks` or `blockedBy` edge anywhere, so nothing is Material.
  Zero emphasis-boundary moves to report, on all three writes, each proven by checksum rather than by eye: milestone sha256 `72d2821c…` sent and returned, project sha256 `a108a29a…` intended and returned, receipt body compared in full.
- DONE: `## Stage Report: review (post-merge closeout)` written on this entity — a new heading — with DONE/SKIPPED/FAILED per item above and every evidence line on its own line; frontmatter untouched (`reconciled` is the FO's stamp) and `merge guard` not run
  This section, appended at the end of the entity after line 1332. Frontmatter not opened; `merge guard` not invoked; no repository file read or written, and the throwaway worktree the dispatch helper recreated was left untouched.

### Three things for the FO

- **A patch write moved no emphasis boundary this time, and that is a new data point rather than a reprieve.** The workflow rule records `save_project`'s `patch` re-serializing outside its patched range. Four anchored replacements here returned a body byte-identical to the intended one. The difference is structural and consistent with the rule as narrowed: this description's two bold runs are each followed by ordinary text, and its code spans sit in plain prose. It does not weaken the guard — it is the second confirmation that authoring around the trigger works.
- **A comment naming four issue identifiers added zero relations.** The mention rule was measured on issue and milestone *body* writes. This receipt named DRC-4346, DRC-4347, DRC-4348 and DRC-4044 in a comment, and the post-write read-back is byte-for-byte the same relation set; the identifiers also came back as plain text rather than as `<issue …>` mention tags, unlike the same identifiers in this issue's description. Worth recording as a narrowing: the receipt comment appears to be a safe place to name an issue. One observation, not a rule.
- **H1's own reconcile has debt this stage was not scoped to pay.** DRC-4044 closed 2026-09-03T12:25:58Z, yet `Move up a level` still lists it under "What remains" and in two "Waits on" lines, and `Don't burn capacity` still names it as gating A6. My step 2 is scoped to this issue's owning milestone, and repairing another issue's milestone would be an unauthorized write, so I left all of it alone. It is one edit away from being right, which is exactly the shape the reconcile exists to catch.

### Summary

All six reconcile steps ran against the merged state, and four of the six were no-ops recorded with why: the issue was already `Done` by GitHub automation two and a half seconds after the merge, nothing was blocked by it, there was no `blocks` edge to convert, and a `sharpen` merge owes no promise wording. The two real writes — one milestone line removed, four As-of figures re-derived — were both scripted from fresh captures with exactly-once assertions and diffed to their authorized hunk counts before sending, and all three writes including the receipt returned byte-identical bodies. The finding worth the FO's attention is that most of the As-of movement belongs to H1's merge rather than to this one, and H1's milestone entries are still stale in two other milestones this stage had no authority to touch.
