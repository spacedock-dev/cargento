---
id: drc-4025
title: 'C6 · Report the irreversible things that happened'
status: review
source: https://linear.app/recce/issue/DRC-4025
started: 2026-09-14T10:07:20Z
completed:
verdict:
score: 0.5
worktree: .worktrees/spacedock-ensign-drc-4025
issue:
pr: pr-merge:335
mod-block:
linear-status: Done
milestone: 'Steer before waste'
release: 'r3'
estimate: 'M'
reconciled: 2026-09-14T23:57:54Z
promise: P2
move: extend
gates:
    version: 1
    records:
        - id: gate:drc-4025:triage
          stage: triage
          attempts:
            - id: gate-attempt:drc-4025-triage-1
              briefing:
                id: briefing:drc-4025:triage:attempt-1:revision-1
                digest: sha256:feda0d8bf8bf63cf97033bb371c9dd754b59c02a4daeae670447a68f026819d6
                room-ref: ./review/triage/briefing-1
              resolution:
                type: Resolution
                id: resolution:spacedock:drc-4025:triage:1
                briefing: briefing:drc-4025:triage:attempt-1:revision-1
                by: person:captain
                at: "2026-09-14T12:10:49.102567Z"
                decision: approve
                reason: Captain approved the presented C6 scope and recommended approach, including current-run retention and qualified timing guarantees.
              application:
                target-stage: implementation
                state: consumed
        - id: gate:drc-4025:review
          stage: review
          attempts:
            - id: gate-attempt:drc-4025-review-1
              briefing:
                id: briefing:drc-4025:review:attempt-1:revision-1
                digest: sha256:58c464db4423e5fc9ee93b9547c5b1c19a699cf92f766fdd4e5c124f1b36a6f9
                room-ref: ./review/review/briefing-1
              resolution:
                type: Resolution
                id: resolution:spacedock:drc-4025:review:1
                briefing: briefing:drc-4025:review:attempt-1:revision-1
                by: agent:first-officer
                at: "2026-09-14T23:55:15.157602Z"
                decision: approve
                reason: Independent GO accounts for all six ACs; corrected Windows proof and 12 checks pass on a6c3fcb with CLEAN mergeability, within approved tolerance. Approve delivery and required reconciliation.
                conn:
                    quote: yes I approve the scope. go ahead and take your recommended approach for the following tickets needed to close out this milestone, I trust you
                    source: Captain message in this session, 2026-09-14, approving the presented milestone ticket scopes and recommended approach; subsequent continue directives
              application:
                target-stage: done
                state: pending
review-round:
    id: round:drc-4025:review:1
    stage: review
    cycle: 1
    briefing:
        id: briefing:drc-4025:review:round-1
        digest: sha256:78076a8da2fcd1eb0b8f2e6ab181376ace18da8e318b4c65cbf214aaf47d5f19
        room-ref: ./review/review/round-1
---

[DRC-4025](https://linear.app/recce/issue/DRC-4025) — Linear priority High, estimate M.

Linear owns the live issue. The originals below are dated triage evidence, and the proposed replacements remain local for captain review; the first officer owns gate advancement and subsequent approved tracker writes.

## User value

A person returning to an auto-approved session can see which destructive command shapes its after-tool hook reported while they were away, without reopening the transcript. P2, extend: fixed-label reports on each session and across sessions add a new clause to the mid-flight promise.

## Problem

C6 remains unshipped: current hooks discard command input before forwarding ordinary lifecycle hints, and Attention explicitly lists destructive-shape reports as absent. The live issue overstates what an after-tool event proves: a real Codex command exiting 1 still emitted PostToolUse. The rewrite therefore promises observed command shapes and keeps successful effects unknown. The original hard latency claim also exceeds the measured daemon-thread behavior.

## Proposed approach

After the gate, specify the fixed lexical form table and shape captures, implement hook reduction and the off-state handshake, then validated ingress and a separate bounded report ledger. Add per-session rendering and an Attention list, update owned docs and required oracles together, and perform the Mode 2 walk before full security review. No product implementation was made at triage.

## Linear edits made

Originals captured verbatim from the first officer's live Linear snapshot at 2026-09-14T11:36:50.397Z. Triage drafts remain local until the gate approves them.

### Original issue body

````markdown
## User value

A person who left a session on auto-approve notices this once Cargento surfaces that a force push or a dropped table ran while they weren't watching, instead of staying silent about it. P2, extend: logging irreversible actions across sessions is a new clause the promise does not make today. DEC-5 ruled on 2026-09-02 that Cargento may read what a tool call did, in the bounded shape below.

## What needs to be done

Show, per session and across sessions, which irreversible actions ran, in the shape DEC-5 (<issue id="cfeb6bfa-b079-47b0-8767-226e302def45" href="https://linear.app/recce/issue/DRC-4182/dec-5-decision-may-cargento-read-what-a-tool-call-actually-did">DRC-4182</issue>) allowed on 2026-09-02, and no other.

The PostToolUse hook Cargento installs on Claude Code and Codex matches the tool input it already receives against a fixed list of destructive command shapes that ships with Cargento, such as a force push, a hard reset, a `DROP TABLE`, a recursive delete outside a temp directory. It posts a pattern identifier, the tool name and a timestamp to the loopback event endpoint, and nothing else: never the input, never a substring, never a path. The runtime stores the identifier and renders its display name on the session row and in a small cross-session list, ordered newest first. The match is fail-open and bounded to a few milliseconds so it never delays or blocks the user's tool call. `--no-irreversible` turns the report off. The list is documented as incomplete by design: a shell one-liner can be arbitrarily destructive, and the honest core is literal shapes, not inferred destructiveness.

Coverage: Claude Code and Codex, with the hooks installed. Sessions on other harnesses show nothing here rather than a false all-clear.

Acceptance criteria: with the hooks installed, a Bash call whose input matches a listed shape produces one event carrying a pattern identifier, tool name and timestamp and no other field, and the row shows the display name (offline, against a recorded hook payload). A call whose input does not match produces no event (offline). No stored or served field ever contains the tool input or any substring of it (offline, by test over every listed shape). With `--no-irreversible`, no event is posted (offline). A hook whose match is forced to hang returns within its bound and the tool call proceeds (offline).

## Waits on

Nothing. The groundwork gate, [DRC-4329](<https://linear.app/recce/issue/DRC-4329/irreversible-actions-groundwork-securitymd-scope-section-for-hook-side>), shipped on 2026-09-07 in #295, so this is free to start. Read that SECURITY.md section first: it is the boundary the hook-side matching has to stay inside.

One correction to carry, because it changes what that section is. DEC-5's own ruling assumed the runtime never parses a tool call's input. It does, in three places, so the section shipped as an allowlist rather than a prohibition, and the false premise was filed and closed as [DRC-4432](<https://linear.app/recce/issue/DRC-4432/dec-5s-ruling-rests-on-a-premise-about-the-code-that-does-not-hold>). Build against the section, not against the sentence in DEC-5.

## Scores (blind-panel medians)

| Impact | Risk-adjusted impact | Access | Build | Detector risk |
| -- | -- | -- | -- | -- |
| 72 | 56 | 70 | 40 | 16 |

Score legend: see the Visibility 2x2 board README.
````

### Original milestone description

````markdown
## The user value

**For each live session: what it is doing now, what it plans next, how far into the current turn it is, and an estimate of when that turn ends. It tells you when that changes instead of making you poll.**

## What is left

[C1](<https://linear.app/recce/issue/DRC-4020/c1-subagent-workflow-stage-and-a-tripwire-on-it>): Cargento alerts you the moment a subagent crosses a line you set, instead of you checking in.

[C4](<https://linear.app/recce/issue/DRC-4023/c4-my-goals-across-sessions>): every session on the board says what it is for, from whichever source knows, not only the ones you typed against.

[C6](<https://linear.app/recce/issue/DRC-4025/c6-report-the-irreversible-things-that-happened>): Cargento shows which irreversible actions ran while you were not watching, such as a force push.

## Waits on

Nothing. Every gate this milestone had is clear, so all three are free to start.

## Read before building

* [DRC-4023](<https://linear.app/recce/issue/DRC-4023/c4-my-goals-across-sessions>): the one-place read-only view shipped on 2026-09-11 as the Intent log, and C4 narrowed to what it does not do. Read the issue before building: the view, the read-only constraint and the no-judgment disclaimer are out of scope now, and the remaining work is the population and the two goal sources it does not read.
* [DRC-4025](<https://linear.app/recce/issue/DRC-4025>): read SECURITY.md, "Irreversible actions (hook-side destructive-shape matching)", before building. It permits hook-side pattern identifiers, tool names and timestamps only; the runtime input-reading rule is an allowlist, and the report and its off switch remain unshipped.
````

### Proposed issue body — pending triage gate

````markdown
## User value

A person returning to an auto-approved session can see which destructive command shapes its after-tool hook reported while they were away, without reopening the transcript. P2, extend: fixed-label reports on each session and across sessions add a new clause to the mid-flight promise.

## What needs to be done

Match a fixed, documented set of literal command forms in Claude Code and Codex PostToolUse hooks. A report means the hook observed a matching command after the tool call; it does not prove the destructive effect succeeded. Never register matching at a permission or pre-tool gate, or infer a match from tool output.

Use the current SECURITY.md section, "Irreversible actions (hook-side destructive-shape matching)", and the corrected DEC-5 ruling. Runtime input reads remain its named allowlist; matching stays in the existing hook process. The initial named forms are git force push, git hard reset, DROP TABLE in a supported SQL-client command, and recursive delete outside a literal temporary-directory prefix. Document exact supported forms, wrappers and exclusions before shipping; ambiguous shell syntax abstains. No user patterns, shell evaluation, filesystem resolution or regex matcher.

Keep the new report to version, event name and session identity for routing, plus one fixed pattern identifier, an allowlisted tool name and a timestamp. It carries no cwd, transcript path, input, output, copied argument or free-text explanation. Existing ordinary lifecycle envelopes retain their own contract. Validate the new vocabulary again at ingress; preserve compatibility with old ordinary envelopes.

Keep reports in a bounded in-memory ledger for this dashboard run: newest 1,000 globally, newest 20 per session, at most 24 hours, oldest evicted first. Keep each accepted report through collection coalescing and session end. Publish per-session reports and a small newest-first list on Attention, outside its session-risk denominator. Say "reports", not an exact count of irreversible actions; delivery can repeat or reorder. No disk history, restart persistence, new notifications or dismissal controls.

Read an explicit enablement bit from the existing atomic state file before matching. Missing state, an old server, --no-events and --no-irreversible disable matching. The new flag also disables ingress/publication and survives daemon respawn. A hook already in flight can race a restart and attempt a post; an off server rejects it. The six-field envelope cannot identify an old run, so an enabled replacement server may receive an in-flight report. Ordinary PostToolUse lifecycle hints remain available when only this feature is off.

The matcher has a nominal 5 ms wait budget in a daemon thread, bounded input and no worker I/O. Late results are discarded. This is a bounded best-effort report, not a universal real-time deadline: Python startup, scheduling and the existing transport take separate time. The gate must accept that precise latency contract before implementation; a GIL-held native operation defeats the tested thread deadline and is forbidden in the matcher.

## Acceptance criteria

1. Offline and interactive: each admitted harness/tool/command field has a real shape-only after-tool capture, plus a harmless live call; success and failure-hook behavior are distinguished. Verified by replay and live recorder output; falsified by reading an assumed nested field or treating an undiscovered recorder as negative payload evidence.
2. Offline: every documented positive produces a fixed-label report; unmatched, ambiguous, malformed, oversized, wrong-tool and wrong-event inputs do not. Verified by socket-level positive/negative cases with distinct private sentinels and ingress forgery cases; falsified by a copied sentinel or unknown identifier reaching accepted, stored or served reports.
3. Offline and interactive: session detail and Attention say "Command shape reported: force push" and disclose "A shape match does not prove the action succeeded." Empty coverage says "No matching reports received; missing hooks and unmatched commands can look the same." Unsupported and disabled states say so. Verified by the assembled bundle and browser walk; falsified by any all-clear or successful-effect claim.
4. Offline: two reports within one collection interval both survive, remain after session end within the stated caps, and list counts derive from displayed reports. Verified by coordinator-to-snapshot tests including duplicate/reordered delivery, eviction and restart; falsified by hint coalescing losing reports or absent measurements reading as zero actions.
5. Offline: fresh hooks under an off or missing enablement state neither call the matcher nor post this report; daemon respawn preserves off, and an off replacement server rejects in-flight reports. Verified by real hook subprocesses and restart integration; falsified by matcher entry in a fresh off hook, accepted report at an off server or re-enabled child under off.
6. Offline: forced sleep and pure-Python spin return no report and the actual hook process exits within a 250 ms test containment window on supported CI platforms; normal matching is measured separately. Verified by subprocess timings and exit/stdout, with GIL-held regex retained as a rejected negative control; falsified by late publication, nonempty stdout, worker join at shutdown or a universal 5 ms claim.

## Waits on

No open Linear blocker. Groundwork DRC-4329 shipped in PR 295; DRC-4432 corrected DEC-5's false absolute runtime-input premise. Before implementation, the triage gate must accept the measured latency wording and current-run retention. Before admitting a tool shape, its live payload capture must exist.

## Historical scope, 2026-09-14

The earlier body said "which irreversible actions ran", "no other field", and no input "or any substring" anywhere; those overstate effect evidence, omit required routing fields, and confuse copied input with fixed labels that can coincidentally share characters. It also promised a few milliseconds with no delay: the probe measured scheduling overshoot and a GIL-held timeout failure. The earlier runtime-input count of three is dated; SECURITY.md now names seven expressions. The original issue and milestone were preserved verbatim in the triage entity before drafting.

## Scores (blind-panel medians)

| Impact | Risk-adjusted impact | Access | Build | Detector risk |
| -- | -- | -- | -- | -- |
| 72 | 56 | 70 | 40 | 16 |

Score legend: see the Visibility 2x2 board README. These historical panel scores are unchanged; implementation and oracle estimates are costed separately at the triage gate.
````

### Proposed milestone description — pending triage gate

Only the C6 user-value clause changes; the C4 note, C6 SECURITY pointer and other milestone wording are preserved. Labels remain journey:mid-flight and move:extend.

````markdown
## The user value

**For each live session: what it is doing now, what it plans next, how far into the current turn it is, and an estimate of when that turn ends. It tells you when that changes instead of making you poll.**

## What is left

[C1](<https://linear.app/recce/issue/DRC-4020/c1-subagent-workflow-stage-and-a-tripwire-on-it>): Cargento alerts you the moment a subagent crosses a line you set, instead of you checking in.

[C4](<https://linear.app/recce/issue/DRC-4023/c4-my-goals-across-sessions>): every session on the board says what it is for, from whichever source knows, not only the ones you typed against.

[C6](<https://linear.app/recce/issue/DRC-4025/c6-report-the-irreversible-things-that-happened>): Cargento reports destructive command shapes observed after a tool call while you were not watching, such as a force push; a report does not prove the effect succeeded.

## Waits on

Nothing. Every gate this milestone had is clear, so all three are free to start.

## Read before building

* [DRC-4023](<https://linear.app/recce/issue/DRC-4023/c4-my-goals-across-sessions>): the one-place read-only view shipped on 2026-09-11 as the Intent log, and C4 narrowed to what it does not do. Read the issue before building: the view, the read-only constraint and the no-judgment disclaimer are out of scope now, and the remaining work is the population and the two goal sources it does not read.
* [DRC-4025](<https://linear.app/recce/issue/DRC-4025>): read SECURITY.md, "Irreversible actions (hook-side destructive-shape matching)", before building. It permits hook-side pattern identifiers, tool names and timestamps only; the runtime input-reading rule is an allowlist, and the report and its off switch remain unshipped.
````

## Expected surface and tolerance

Runtime: 11–14 files and 450–850 changed/added lines. Tests/oracles/support: 12–15 files and 500–950 lines, costed independently. Docs: 4–6 files and 100–200 lines. Tolerance: at most 25 percent beyond each approved range, then return to the first officer to recost before broadening. The inventory below names declaration, ingress, import, mirror, byte-pin and documentation obligations. Full delivery estimate: 6–10 hours; calibrated 4–7 hours trims unrelated exploration, retaining full security review and required checks.

## Acceptance criteria

**AC-1** (offline and interactive): each admitted harness/tool/command field has a real shape-only after-tool capture, plus a harmless live call; success and failure-hook behavior are distinguished.

Verified by: replay and live recorder output. Falsified by: reading an assumed nested field or treating an undiscovered recorder as negative payload evidence.

**AC-2** (offline): every documented positive produces a fixed-label report; unmatched, ambiguous, malformed, oversized, wrong-tool and wrong-event inputs do not.

Verified by: socket-level positive/negative cases with distinct private sentinels and ingress forgery cases. Falsified by: a copied sentinel or unknown identifier reaching accepted, stored or served reports.

**AC-3** (offline and interactive): session detail and Attention say "Command shape reported: force push" and disclose "A shape match does not prove the action succeeded." Empty coverage says "No matching reports received; missing hooks and unmatched commands can look the same." Unsupported and disabled states say so.

Verified by: the assembled bundle and browser walk. Falsified by: any all-clear or successful-effect claim.

**AC-4** (offline): two reports within one collection interval both survive, remain after session end within the stated caps, and list counts derive from displayed reports.

Verified by: coordinator-to-snapshot tests including duplicate/reordered delivery, eviction and restart. Falsified by: hint coalescing losing reports or absent measurements reading as zero actions.

**AC-5** (offline): fresh hooks under an off or missing enablement state neither call the matcher nor post this report; daemon respawn preserves off, and an off replacement server rejects in-flight reports.

Verified by: real hook subprocesses and restart integration. Falsified by: matcher entry in a fresh off hook, accepted report at an off server or re-enabled child under off.

**AC-6** (offline): forced sleep and pure-Python spin return no report and the actual hook process exits within a 250 ms test containment window on supported CI platforms; normal matching is measured separately.

Verified by: subprocess timings and exit/stdout, with GIL-held regex retained as a rejected negative control. Falsified by: late publication, nonempty stdout, worker join at shutdown or a universal 5 ms claim.

Implementation proofs remain owed. The 250 ms planned containment assertion must be evaluated under supported CI loads; it is not a universal scheduling guarantee.

## Test plan

Begin with meaningful failing tests at each boundary: recorded input to socket envelope, ingress to retained reports, coordinator to published snapshot, and real hook subprocess to shutdown. Include malformed/oversized/wrong-tool cases and private sentinels; concurrent reports, ordering, repeat delivery and eviction; absent/off state and respawn; exact UI claims and empty/unsupported/off states. Recompute all three frontend pin owners. Run the canonical AGENTS.md pre-PR suite once, isolate known contention failures if any, run sync-docs then sync-project at their authorized stages, and repeat the browser walk on the implemented bundle. Triage ran disposable mechanism probes and a current-surface walk, not this future implementation suite.

## Review depth

Full adversarial security/data-handling review: several lenses, a completeness critic and an arbiter that reproduces findings, as required by AGENTS.md. The independent oracle-inventory reader provided discovery only; no completed implementation review is claimed.

### Feedback Cycles

- Cycle 1: FIXED — retained reviewer/review-1; surface 37/1558 (runtime 13/514, support 17/858, docs 7/186) vs estimate runtime 11–14/450–850, support 12–15/500–950, docs 4–6/100–200; maximum category overrun (+16.7%); AC unchanged

## Out of scope

C1, C4 and canceled C7; successful-effect inference; tool-output inspection; arbitrary shell interpretation or filesystem resolution; configurable patterns; new subprocesses in the matcher; new notifications or controls; durable report storage; version/release changes. No new standing checks were added during triage. Additional tool or platform command forms require measured admission before inclusion.

## Stage Report: selection

- DONE: Reconcile live milestone membership and closed-issue receipts, preserving unrelated workflow work.
  Live membership and merge evidence verified on 2026-09-14; the first officer brokered four missing receipts and both scoped description corrections, then independently read every write back.
- DONE: Select the highest-ranked open issue within Steer before waste from live Linear relations and labels.
  Pick DRC-4025: rule 5 gives its risk-adjusted 56 precedence over DRC-4020's 44 in release r3; rule 2 puts DRC-4023's later row behind both. Reconciliation is complete.
- DONE: Record a concrete remaining-work inventory and the selection evidence, then hand the selected issue to triage.
  Inventory and evidence are below; DRC-4025 is handed to the first officer for triage. The first officer owns advancement and cached frontmatter refresh.

### Remaining work and selection evidence

The complete live project fetch returned 250 issues and then 69, with `hasNextPage=false` on page two. Exactly ten belong to milestone `c965439d-7e5b-4fd0-ab73-dca409cce586`: three open, five completed and two canceled. State was read from Linear, not the panel export or local frontmatter.

| Open issue | Live state and rank | Work still owed |
| -- | -- | -- |
| DRC-4025 | Todo; r3; move:extend; 56; M | Bounded hook-side destructive-shape matching for Claude Code and Codex, identifier-only reporting with tool name and timestamp, per-session/cross-session display, off switch and honest coverage limits. Read the shipped SECURITY.md section first. |
| DRC-4020 | Backlog; r3; move:extend; 44; XL | A persisted user-declared workflow-stage condition and an alert when a subagent crosses it. Existing stage strips are already shipped. |
| DRC-4023 | Backlog; later; move:extend; 47; L | Populate the existing Intent log from every board session and add deterministic-observer and Spacedock goal sources, labelled by source; correct the board gap line. |

All three live `blockedBy` and `blocks` arrays are empty; none is dropped for a blocker and rule 4 does not distinguish them. Every open item has journey:mid-flight and move:extend. All three already have entity files. DRC-4025's cached Backlog frontmatter is stale relative to live Todo; the worker did not change frontmatter.

### Closed delivery receipts

| Issue | Verified evidence | Receipt state |
| -- | -- | -- |
| DRC-4344 | Live completed member; existing six-step receipt `da744a90-2a7d-4ed4-a7f4-0f4299d202ff` cites PR 261 and commit 0f0d4a7 | Present; read in full. |
| DRC-4329 | GitHub PR 295 MERGED 2026-09-07T11:01:38Z, commit `6de8f0a3ed8de45a4bbc1f402e84f5326a335418` | Repaired; `4b034819-3a6b-4a4a-8682-23f107b4a0a1`, exact read-back by first officer. |
| DRC-4021 | GitHub PR 277 MERGED 2026-09-06T08:23:34Z, commit `50bc4b4098c3079508d10cec28807390d63778fc` | Repaired; `8ddfc667-2cd8-4acf-9d28-ac966bfd8d30`, exact read-back by first officer. |
| DRC-4024 | GitHub PR 137 MERGED 2026-08-21T11:09:38Z, commit `ffd2fe448a0e48f555f6d2ccaededc5190fa41bd` | Repaired; `503e2351-d25d-4672-a7aa-b1986820fc88`, exact read-back by first officer. |
| DRC-4027 | GitHub PR 134 MERGED 2026-08-21T08:29:41Z, commit `43bff8d26fc8c444edc84481da118fa95d86be6a` | Repaired; `00c157d8-b241-4cc0-be58-8dadf6d16f46`, exact read-back by first officer. |

All initial comment queries ended with `hasNextPage=false`. Before posting the four receipts, the first officer rechecked Done status and empty blocks/blockedBy; no relation or issue-state mutation was needed. The receipts are dated 2026-09-14 and distinguish current verification from historical reconciliation. DRC-4022 and DRC-4026 are live Canceled and stay outside implementation scope. The first officer checked C7: DEC-14 removed the model restriction, but no ruling permits the repository diff/file-content reads its reopening condition requires.

### Interrupted writes, resolved 2026-09-14

The worker's first mutation batch called `linear_save_milestone` for the C6 SECURITY.md contract pointer, followed sequentially in its source by `linear_save_project` for the C7 correction. The entire call returned no output before being aborted after 756.7 seconds; whether the second call was reached was unknown. Neither write had a confirmed success response.

The next call was read-only `linear_get_project({query: "48468ef3-9b00-4a85-8d3f-3d90f8df8c8d", includeMilestones: true})`; it also returned no result and was aborted after 344.1 seconds. The worker attempted no receipt writes and made no further Linear calls. No implementation, PR, gate or unrelated entity was changed.

The first officer subsequently read the project successfully in about two seconds and confirmed neither description correction had landed. The worker handed exact mutation arguments, original-description preconditions and four drafted receipts to the first officer at `/tmp/spacedock-dispatch/drc-4025-selection-repairs.json`; the first officer executed those writes and reported independent read-backs. All four receipt bodies matched exactly. The project description matched the requested text exactly. The milestone retained the C4 note and added the C6 pointer; its serializer removed the blank line between bullets and wrapped the new link URL in angle brackets, with text unchanged. These are confirmed brokered mutations, and no repair remains outstanding.

### Summary

DRC-4025 wins the live pick rules and is ready for triage. The first officer recovered the stalled reconciliation through confirmed writes and independent read-backs: four missing receipts, the C6 contract pointer and the C7 overview correction. The interruption is resolved; implementation scope remains the three open milestone issues, with canceled C7 left closed.

## Triage evidence, 2026-09-14

Feature, P2 / journey:mid-flight / move:extend. Live snapshot: 2026-09-14T11:36:50.397Z, brokered by the first officer; C6 comments empty and blockedBy empty. Related groundwork and corrected ruling are closed. Main was `4b2120d`; no local or remote-tracking DRC-4025 branch was present. No issue or milestone draft was written to Linear during triage.

### What the current code establishes

- `event_hook.py:100,179` already maps both PostToolUse events to `store_changed`. `envelope:351` drops tool name/input/output and permits routing cwd/transcript hints; `main:427` parses before the capability read. Merely adding a server flag does not stop hook-side matching, and saying the whole existing envelope has no paths would be false.
- `events.py:56,81,195,404` owns version 1, the twelve-field envelope, the Event value and parsing. The new report must validate fixed values at both ends and deliberately omit cwd/transcript hints. No new event should change permission or lifecycle overlays.
- `observation.py:425` retains overlays and coalesced dirty hints, so piggybacking an action solely on `store_changed` loses multiple reports. Keep report retention separate and expose it through aggregate's protocol boundary; importing observation into aggregate would invert the dependency.
- `history.py:532,540` deduplicates on state and annotation changes. Adding a shape field alone would lose repeated actions. Current-run memory is the proposed narrow scope; durable history would need its own schema, read compatibility, transition comparisons and security kept-list work.
- `lifecycle.write_state:84` atomically publishes only pid/port/start/log/python and capabilities; the live 4775 state had no feature-enable bit. `spawn_argv:554` explicitly forwards opt-outs. The real parser rejected `--no-irreversible` with SystemExit 2. A proposed explicit bit must be read before matching; an absent bit means off, so an old server is safe by construction.
- SECURITY.md's current irreversible-actions section is the authority. It now records seven runtime expressions reaching input payloads, including prototype dispatch reads; the issue's three-expression count is historical. It requires matching in the existing hook process, no input-derived free text on the wire, after-tool placement, fail-open behavior and a preserved off switch.

### Live payload admission evidence

One-off shape-only recorder, stored under `/tmp/spacedock-dispatch/drc-4025-probe/shape.py`: it reads the actual hook stdin and records event/tool names, sorted top-level keys, nested field names and Python type names. It never records command, result, cwd, transcript or prompt values. All probe commands were harmless; no destructive command was executed.

| Harness and arm | Measured hook | Measured input and response shape |
| -- | -- | -- |
| Claude Code 2.1.270, successful printf | PostToolUse, tool Bash | tool_input dict: command:str, description:str. tool_response dict: stdout:str, stderr:str, interrupted:bool, isImage:bool, noOutputExpected:bool. |
| Claude Code 2.1.270, false exits nonzero | PostToolUseFailure, tool Bash | tool_input dict: command:str, description:str. No tool_response; top-level error and is_interrupt fields present. |
| Codex 0.154.0, successful printf | PostToolUse, tool Bash | tool_input dict: command:str. tool_response:str. |
| Codex 0.154.0, false exits 1 | PostToolUse, tool Bash | Same input/response types as success. Driver independently reports exit 1; event name alone therefore cannot establish success. |

Claude records: `claude-shapes.jsonl`; Codex records: `codex-shapes.jsonl`, under that scratch directory. Codex's historical 0.146.0 capture established the top-level fields and Bash name, but not the nested command field; these fresh records close that gap. Neither capture admits other tools or other platform-specific argument shapes. Input `description`, tool_response and Claude's error field must not be used by the matcher.

The first two Codex probes were registration negatives, not payload negatives: project `.codex/hooks.json` was not discovered, even after adding a scratch git root. Read-only app-server `hooks/list`, with schema-correct `cwds`, returned no project recorder. The first officer supplied the supported inline TOML override; `hooks/list` then showed the exact recorder enabled under `/<session-flags>/config.toml`. A per-invocation vetted trust flag enabled it without changing CODEX_HOME or installing a plugin. Successful and failing calls both then produced records. Global hooks also ran; every probe process group was terminated after its bounded run, and the six recorded driver pids were absent afterwards.

Reproduction uses an isolated scratch recorder and settings, never edits the operator's hooks: Claude `--settings <scratch-settings> --setting-sources '' --strict-mcp-config --mcp-config '{"mcpServers":{}}' --tools Bash --allowedTools <one harmless command> --no-session-persistence`; Codex `exec --ignore-user-config --ignore-rules --sandbox read-only --ephemeral -c <inline override>`, with its vetted-hook trust flag. The tested inline override shape is `hooks.PostToolUse=[{matcher="^Bash$",hooks=[{type="command",command="python3 <absolute recorder> codex <absolute shape output>",timeout=3}]}]`. Read discovery before driving a model. The recorder's only output file fields are the shapes listed above.

### Mode 1 rendered surface walk

The P2 promise, copied from docs/promise-map.md: "for each live session, what it is doing now, what it plans next, how far into the current turn it is, and an estimate of when that turn ends. It tells you when that changes instead of making you poll." Existing backing includes current-turn timing, source-labelled goal/plan summaries, subagent state and failure readings. The current input limit is the SECURITY.md allowlist, not the stale blanket prohibition in the walk reference.

Started the current dashboard on spare port 4775 with quota/model calls, git/focus operations, persistent history/annotations/dismissals and the ask lane disabled. `/api/data` was read before the screen: seven sessions, Claude and Codex, idle/working states, no irreversible field. One independent oracle reader and harmless capture sessions were spawned during review; their activity is not an unrelated product finding.

Browser navigation used the visible Projects, Sessions, Attention and Intent log links. Session operations rendered "Active evidence leads. Every recently observed session remains reachable." A working session rendered "No pending step published", "No reported block", "No stop or end observed", and "Git state was not measured". Its expanded source coverage said "Codex transcript did not publish a next action." These are the absence standard the new report must follow.

Attention exposed the exact scope gap under "Not on this board yet": "C6", "Irreversible actions", "Force pushes and destructive shapes are not reported on this board yet." The feature should replace this C6 entry with its report list; C1, C4 and unrelated entries remain outside its work. Current notification wording already models the needed restraint: "Whether it was displayed, and whether anyone saw it, is not something that call reports."

Intent log under the disabled feature said "Annotations are off for this run. Start without --no-annotations to type a goal and an expected output, and they will be listed here." A separate short-lived 4776 server served the same assembled page against an empty payload; Projects said "No project has active session evidence right now" and Sessions said "No exact session has active evidence right now" and "No recent-history rows in this payload." This fixture drive was explicitly empty, not a second live-session measurement.

C6-specific unsupported-harness, stale-report and off-state rendering cannot yet be forced: neither producer nor surface exists. Those absences are explicit after-development acceptance arms. The live board contained only Claude/Codex; no claim is made of a live unsupported-harness walk. No independent pre-existing defect was filed from this walk; the observed C6 gap is the issue itself, and unrelated gaps were left alone. The row and new list need assembled-bundle text assertions plus a repeat browser walk after implementation.

### Riskiest mechanism exercised

An ephemeral daemon-thread candidate used a 5 ms join wait. The positive input carried a distinct private sentinel after the force-push shape; only fixed `git_force_push` reached its diagnostic result, with no sentinel. This establishes the small candidate's reduction behavior, not a security proof for an unwritten production matcher.

| Candidate arm | Matcher/wait ms | Actual Python process ms | Result |
| -- | -- | -- | -- |
| Fixed positive token match | 0.108 | 21.754 | Fixed identifier, process exit 0. |
| Forced ten-second sleep | 6.319 | 27.140 | No match; daemon thread still alive, process exit 0. |
| Forced pure-Python infinite loop | 18.920 | 47.745 | No match; daemon thread still alive, process exit 0. |
| Catastrophic native regex | No timely return | 303.575 | External scratch containment killed it at 300 ms. Rejected architecture. |

The experiment proves the join wait is not a universal hard deadline, and interpreter startup is a separate cost. A daemon thread does avoid join-at-exit for sleep and Python spin; ThreadPoolExecutor would not preserve that property. No regex, arbitrary native callback, worker I/O or configurable pattern belongs in the proposed matcher. Production must discard late results, keep the fixed parser's operation count bounded and remeasure on supported platforms. A pure Python sleep/spin test cannot prove that arbitrary GIL-held work is interruptible.

The small standard-library reproducer in scratch `timeout_candidate.py` runs fixed token matching, `time.sleep(10)`, `while True: pass`, or `re.fullmatch('(a+)+$', 'a'*30+'!')` in a daemon Thread; the main thread joins 0.005 seconds and emits a result only when the worker has ended. The external parent runs each arm through `subprocess.run(..., timeout=.3)` and records monotonic elapsed time and process exit. Those distinct arms and the separate process timer are required to reproduce the table; replacing them with a function-return test misses shutdown and the GIL failure.

An independent one-shot control/transport candidate used atomic file replacement and the shipped `notify_hook.forward` to a scratch loopback receiver. Old-server state (no bit), then on, then restart-off, then restart-on produced matcher/post counts `(0,0), (1,1), (0,0), (1,1)`. The two received envelopes had exactly `v,event,session_id,timestamp,pattern_id,tool_name`. This validates the proposed control-file transport and the existing guarded forwarder, not a completed flag implementation; the report label in this transport arm was a stand-in. Product subprocess, stale-capability and daemon-respawn tests remain owed.

Probe results are also in scratch `timeout-results.json` and `control-results.json`. Their measured tables and limitations are preserved here so losing scratch does not turn a hand-authored claim into the only evidence.

### Runtime and oracle inventory

Independent read-only inventory by the delegated oracle reader was checked against the current producer and history paths. Runtime estimate: 11–14 files, 450–850 changed/added lines, plus no more than 25 percent tolerance after the gate. The high end includes a separate in-memory ledger leaf module; that module is optional, not a reason to create a new abstraction by default. Documentation: 4–6 files, 100–200 lines. Test/oracle/support estimate: 12–15 files, 500–950 lines, separately costed with the same 25 percent tolerance; new behavior assertions and byte updates are both included.

- Runtime: both byte-identical `event_hook.py` copies; events, observation, aggregate, sessions, config, cli and lifecycle; web/next-session.js, next-attention.js and next-observed.js, plus at most one shared rendering/style site and optional ledger leaf. The Gemini copy still rejects matching through the harness gate. PostToolUse manifests already exist and need no new hook position.
- Session oracles: `tests/test_sessions.py` independent DECLARED_SESSION_FIELDS plus constructor and ten-harness producer equality; owning producer published mapping; aggregate protocol/fakes. `events.PATCHABLE` need not grow: action reports are not lifecycle patches. If that choice changes, its declaration and history semantics must be recosted rather than silently added.
- Ingress/coordinator: `test_events.py:102`, `test_events_ingress.py:352–824`, `test_observation.py` must exercise unknown IDs/tool names, old envelopes, no free-text wire fields, multiple events before one collect, late/out-of-order arrivals and end-before-collection.
- Lifecycle: `test_lifecycle.py:1272–1300,1519–1585` and its seven hand-built namespaces, plus `test_focus.py:1067`, need the direct off-switch attribute and the enablement handshake. The default state-file schema and old-server absence must have behavioral arms, not a parser-only flag test.
- UI: assembled-bundle tests in `test_next_session.py`, `test_next_attention.py` and `test_next_observed.py`; counts must derive from displayed report collections. Preserve disclosure/keyboard state on redraw. Recompute pins from assets in all three owners: test_next_page.py, test_next_flag.py and test_focus.py (two assembled lengths, three assembled digests).
- Admission/packaging: `test_contracts.RuntimeImportGraphTest:1322` requires every new module and import edge; `scripts/validate_plugins.py` runtime-file inventory requires any new leaf. Its mirrored-hook check and `test_focus.py:542` require the Gemini script to stay byte-identical. Existing suites suffice; no check compels a new test file. A dedicated matcher test file is optional organization, not a standing check.
- Documentation: `test_documentation.py:1530` deliberately asserts the feature and flag are absent; replace with positive implementation contracts. EventEnvelopeEnumerationTest binds both width words to ALLOWED_FIELDS (12 becomes 14 if adding pattern_id/tool_name and reusing timestamp). Update SECURITY's future tense, exact shape set, latency bounds and envelope clauses; shipped SKILL, compatibility and architecture; P2 promise-map backing/limit and the matching board copy through sync-docs. Do not change version fields or the parallel-branch sync marker.

Durable history is not included in these totals. If the captain requires restart persistence, add 100–220 runtime lines and 120–250 oracle lines, including history schema/read versions, observation fields, transition dedupe, expiry/off-state and SECURITY kept-list changes. That is a gate scope change, not something implementation may quietly absorb.

### Gate choices and implementation boundaries

Recommend the bounded current-run list and precise best-effort latency contract above. The original effect-success promise is contradicted by a real Codex failure event and must be corrected before code. The captain must explicitly accept the remaining latency qualification and current-run retention; neither is a settled ruling in this report. If an absolute forced-hang guarantee for arbitrary native work remains required, the no-new-subprocess boundary and that guarantee cannot both be satisfied by the tested candidate; return the decision to the first officer rather than ship a thread test as proof.

The initial form table must be concrete before matcher code: direct git force flags/hard reset, named SQL-client statement arguments, and recursive-rm flags with literal temp-prefix exclusions. Only documented lexical wrappers (including any explicitly admitted rtk form) may be normalized. Reject shell composition, expansions and ambiguous quoting rather than evaluate them. A temp-prefix exclusion is lexical and establishes nothing about symlinks or where a path resolves. No command is executed to classify it. Each shape gets an identifier, display label, positive form, negative control and admitted harness payload mapping in SECURITY.md.

No universal coverage claim follows from these four forms. A failed Codex command can still produce a report; Claude failure hooks remain outside registration. Do not inspect result text to make the two harnesses look equivalent. No new notifications, irreversible-effect counters, persistent history or sibling feature work belong here.

Full adversarial review is required for security and data handling: several lenses, a completeness critic and an arbiter that reproduces findings. The oracle-inventory reader was discovery, not that review. Expected full delivery cost is roughly 6–10 hours including implementation, canonical checks, live Mode 2 and full review; trimming unrelated exploration can bring this toward 4–7 hours, but security review and required oracles are not optional. The first officer presents the estimate and choices at the gate.

### Artifact consistency review

An enablement bit is not a run identity. The six-field envelope has no run token, so an already-running hook can post across a restart; an off replacement server must refuse it, while an enabled replacement may accept it. The draft promises that enforceable off boundary and does not claim stale-run rejection. No additional envelope field or capability mechanism was silently added.

Both C6 review browser tabs were closed. Owned dashboard/fixture listeners on ports 4775 and 4776 were stopped by their verified PIDs (86639 and 4241); a subsequent process read found both absent. Harness driver process groups had already been cleaned and verified absent. No unrelated server or session was stopped. Artifact checks passed: both original descriptions equal the live snapshot, frontmatter equals HEAD, selection history is unchanged, one report exists for each completed stage, and git diff --check is clean.

## Stage Report: triage

- DONE: Verify C6 against current hook captures, runtime, SECURITY.md, and a before-development surface walk; preserve the original Linear issue and milestone verbatim.
  The dated broker snapshot is preserved exactly in the two original-description blocks.
  Read current producer, coordinator, lifecycle, publication and retention boundaries.
  Real Claude 2.1.270 and Codex 0.154.0 shape captures admit Bash.command.
  Claude's nonzero command uses PostToolUseFailure; Codex's uses PostToolUse.
  The before-development browser walk covered live and explicit empty fixtures.
  Feature-specific unsupported/off/stale states remain future implementation proofs.
- DONE: Draft the narrow issue and milestone corrections with user value, source-honest observable acceptance criteria, offline/interactive proofs, and the riskiest mechanism exercised.
  Both proposed bodies above remain local; no triage Linear mutation occurred.
  The C6 milestone clause now promises an observed shape, never a successful effect.
  Six AC carry proof methods and falsifiers at the relevant observable boundaries.
  Disposable matcher probes measured normal, sleep, spin and GIL-held failure arms.
  Nominal 5 ms waiting overshot; sleep/spin process exits were 27.140/47.745 ms.
  GIL-held regex exceeded 300 ms and was externally killed; this failure is retained.
  Control/transport proof exercised missing/on/off/restart states with a fixed-label stand-in.
  Production matching, stale/off ingress and respawn integration are explicitly not proved.
- DONE: Declare runtime and oracle surface estimates separately, tolerance, review depth, and implementation approach; commit the triage report without writing its drafts to Linear.
  Runtime 11–14 files / 450–850 lines; oracles 12–15 / 500–950; docs 4–6 / 100–200.
  Each range has a 25 percent tolerance; overruns return to the first officer.
  Published fields, ingress, mirrors, imports, packaging, all three pins and doc assertions are costed.
  Full security review remains required; delegated inventory did not substitute for review.
  Full delivery estimate is 6–10 hours, or 4–7 with unrelated exploration removed.
  The issue and milestone drafts are reviewable now; implementation remains behind the gate.

### Gate handoff

The gate must accept the precise best-effort latency contract and bounded current-run retention.
An absolute arbitrary-hang guarantee is incompatible with the tested no-new-subprocess candidate.
Restart persistence would expand runtime and oracle scope by the separately stated amounts.
The original successful-effect wording must be replaced, given the measured Codex counterexample.
No universal harness coverage or complete destructive-command detector is proposed.
The first officer owns the decision, advancement, cached frontmatter and approved tracker writes.

### Summary

C6 is a real unshipped gap, and the proposed rewrite now fits observed hook evidence.
The report preserves the originals, actual mechanism failures, full oracle costs and gate choices.
Triage is complete as a reviewable artifact; no product code or tracker draft was published.


## Implementation entry, 2026-09-14

Approved issue and milestone drafts above were written to Linear at 12:17 UTC and freshly read back. Issue text is exact after Linear automatic issue-link markup normalization; milestone text is byte-exact. Additive journey:mid-flight and move:extend label write preserved origin:proposed, cutoff:unsettled and release:r3. A narrow follow-up lifecycle write set In Progress at 12:18 UTC and a fresh read verified it. No product work preceded these writes. The captain-approved nominal timing and current-run retention contract governs this implementation.


### Implementation context and red-first evidence

The required linear-deep-dive was applied through step 6 only. This is a High-priority feature, P2/extend; the approved issue and milestone were read live at entry. Triage supplied the empty comments/blocker result, closed groundwork, measured tool payloads, existing module ownership and Mode 1 walk. The assigned branch began at 4b2120d with no code changes. Targeted reads confirmed the hook, ingress, coordinator, aggregate protocol, lifecycle flag forwarding and reader sites before implementation. The captain already owns this subsystem and approved its framing, so no repeat familiarity interview or scope gate was introduced.

The implementation follows the approved order: literal form table in SECURITY first, then hook reduction and off handshake, ingress and separate current-run ledger, snapshot and reader surfaces, privacy/timing/restart proofs, oracle and documentation reconciliation, Mode 2 and full security review. Implicit risks carried from triage are the coalesced hint lane losing reports, old state implicitly enabling matching, fixed labels being mistaken for successful actions, durable history accidentally acquiring input-derived data, three byte-pin owners, and daemon threads being a qualified rather than universal latency bound.

The first two implementation tests were observed red: missing irreversible_report raised AttributeError; the coordinator returned unknown-event for the six-field report. They became green after implementation. Two assembled-bundle reader tests were separately observed red on missing report and empty-state wording, then green after the reader integration. Removing the session-detail integration call later made the reader test fail; the file was restored byte-for-byte. Early runtime surface measured 13 files / 512 changed lines, within the approved 11–14 / 450–850 range.

### Candidate verification checkpoint

Candidate 735785dd3699df01d2ec1b7dbd7de1fa9bbaa66e contains code commit fe028f6 and sync-docs commit 735785d; the worktree is clean. Runtime is 13 files / 514 changed lines, tests/oracles/support 17 / 688, and docs 7 / 186. Each stays within its approved 25 percent tolerance. Versions and the COMPATIBILITY sync marker are unchanged.

The canonical dashboard discovery ran once: 3,384 tests in 97.693 seconds, with two failures, one error and two skips. Three integration oracles needed updates: the notification overlay stub lacked command_reports, the lexical git-program inventory omitted the hook matcher, and the Attention section count still expected six. The existing subprocess-spawn restriction stayed intact. The worker edited these three before the distinct FO disposition arrived, disclosed that ordering, and the FO subsequently authorized continuing from the matching scoped fixes. That later disposition is not retroactive authorization. The 164-test affected-module recovery passed with one skip. Logs retain both results under /tmp/spacedock-dispatch/drc-4025-{dashboard-suite,affected-suite}.log.

The canonical script suite passed 505 tests with one skip in 19.967 seconds. Combined coverage is 86.7 percent. Ruff, format, mypy, embedded lint, plugin validator, version parity, and both installed native plugin validators passed. Heavy-suite ownership was released to FO; no second full discovery ran. The original two dashboard skips and the script live-automation skip remain disclosed in their logs.

Mode 2 exercised actual loopback hook delivery on isolated port 4778: Attention report, correct session link, second report after redraw, source disclosure and focus preservation, empty Attention, and an actual --no-irreversible replacement. Explicit browser fixtures covered unsupported Gemini and empty supported-session detail. Command strings were synthetic native-hook inputs; no destructive command ran. A screenshot exposed a default-blue unreadable report link. The worker reported it before editing, FO authorized reuse of existing Attention styles, all three byte-pin owners were recomputed, and 218 focused tests plus embedded lint passed. Before/after and empty/off/unsupported screenshots are in the code worktree's ignored docs/screenshots/drc-4025-*.png. Both owned live-server processes and the fixture server were stopped.

Normal irreversible_report measurement, separate from containment, produced 100 reports in 100 runs: median 0.035 ms, maximum 0.292 ms, including thread start/join but excluding transport. Actual hook subprocess sleep/spin containment and the rejected GIL-regex negative control are covered by test_irreversible; no universal 5 ms claim is made.

The approved five-worker review budget was declared before fan-out: three independent hook, ledger and reader lenses plus one completeness critic, followed by one reproducing arbiter. Independent artifacts retain candidate SHA and AC evidence at /tmp/spacedock-dispatch/drc-4025-review-{lens1,lens2,lens3,critic,arbiter}.md. Review is in progress; no PR or completed security-review claim is made at this checkpoint.

### Final pre-PR evidence

All five required reviewers completed on unchanged candidate 735785dd3699df01d2ec1b7dbd7de1fa9bbaa66e with zero confirmed findings. Lens 1 reproduced 41 fresh-hook socket cases, 20 parser cases and delayed-success suppression; lens 2 reproduced 24 malformed/auth refusals, 16 concurrent reports, actual history-file exclusion, 1,530-delivery cap ordering and replacement/off boundaries. Lens 3 drove 27 retained versus 20 displayed reports through the actual assembled bundle with correct routes, escaping and unchanged risk collection. The critic served and rendered orphan reports then exact 24-hour expiry. The arbiter composed eight actual-hook reports through authenticated HTTP, served snapshots, session end and reader rendering, plus stale-on-handshake/off-ingress and fresh-off matcher suppression. Artifacts and their candidate-qualified SHA-256 manifest are retained at /tmp/spacedock-dispatch/drc-4025-review-*.md and drc-4025-review-manifest.json. Reviewer scratch-fixture failures are disclosed in their artifacts; none changed candidate bytes.

FO identified burndown step 3's conditional rerun after docs/Mode 2 changes. That specific new-byte requirement superseded the initial once-only plan; the final suite ran in the reserved C6 slot after review. Dashboard: 3,384 tests in 98.062 seconds, OK, two skips. Scripts: 505 tests in 19.922 seconds, OK, one skip. Fresh combined coverage: 86.7 percent. Ruff, format, mypy, embedded lint, plugin validator, version parity, and native Claude/AGY validators all pass on this same candidate. Final logs are /tmp/spacedock-dispatch/drc-4025-final-{dashboard-suite,script-suite,coverage}.log. Dashboard skips are Windows-only path semantics and the host's git-lfs hook behavior; script skip is opt-in live Terminal automation. No contention failure occurred in the final run. Original failure/recovery evidence above remains unchanged.

Fresh origin/main is still 4b2120d. The clean candidate has two DCO commits, 37 files, 1,255 additions and 133 deletions. Runtime 13/514, support 17/688 and docs 7/186 remain within tolerance. The reviewable PR title and exact body are /tmp/spacedock-dispatch/drc-4025-pr-title.txt and drc-4025-pr-body.md. No mirrored GitHub issue was found; the body links the Linear issue without inventing an autoclose line. Publication is the remaining implementation step; supported-platform CI and merge are the fresh review stage's responsibility.

## Stage Report: implementation

PR: https://github.com/spacedock-dev/cargento/pull/335
Head: 735785dd3699df01d2ec1b7dbd7de1fa9bbaa66e; base: 4b2120d.
The exact title, body and head were read back after creation and match the supplied draft.

- DONE: Approved Linear drafts and labels are written and verified before product work; implementation follows the measured C6 contract and all six acceptance criteria.
  The implementation entry records the verified pre-code Linear writes; the six acceptance-evidence lines below cite the implemented boundaries and independent proofs.
- DONE: The bounded hook-to-snapshot-to-reader feature is implemented with meaningful red-first tests, privacy/off/timing proofs, and a passing Mode 2 browser walk.
  Red-first and Mode 2 evidence remain recorded above; the final candidate and independent artifacts preserve the socket, reader, privacy, off-state and timing results.
- DONE: Canonical checks, sync-docs, full security review in the worktree, and measured surface within tolerance precede the issue-specific PR and durable evidence report.
  Final validation, five independent review artifacts, measured surface and PR 335 readback are recorded below on the unchanged candidate head.
Checklist totals: DONE 3; SKIPPED 0; FAILED 0.

### Acceptance evidence

AC-1: committed shape-only Claude/Codex captures and retained harmless live-call evidence; test_irreversible.py:252 replays the measured field through actual hooks/sockets. Lens 1 independently verified capture hashes and success/failure behavior.
AC-2: test_irreversible.py:215,232,284 covers all documented forms/wrappers, exclusions and ingress forgery. Lens 1's 41 fresh-hook cases and arbiter's eight composed cases found no private sentinel in accepted, retained, served or rendered reports.
AC-3: test_irreversible.py:516,523 executes both assembled reader surfaces. Mode 2 screenshots under docs/screenshots/drc-4025-* cover report, empty, disabled and unsupported states; the actual walk proved session routing and redraw/focus preservation. Lens 3 and critic inspected the retained images.
AC-4: test_irreversible.py:340,383,437,459 covers coalescing/end/order/caps/restart/counts. Lens 2 reproduced 16 concurrent reports, actual history-file exclusion and a 1,530-delivery reference oracle; lens 3 verified 27 retained/20 displayed with unchanged risk collection; critic verified orphan reports and exact served expiry.
AC-5: test_irreversible.py:274,301,360,401 covers no-events, missing/off state, actual listener replacement and respawn argv through child parser/config. Lens 2 and arbiter independently reproduced malformed enablement, replacement, stale-on/off ingress and fresh-off matcher suppression.
AC-6: test_irreversible.py:320,332 runs forced sleep/spin and rejected GIL-regex in actual hook subprocesses. Lens 1 reproduced sleep at 68.81-71.42 ms, spin at 82.23-83.95 ms, and delayed success with no late report. Normal matching was measured separately; no universal deadline is claimed.

### Verification and review

Final canonical dashboard: 3,384 tests, 98.062 seconds, OK, two skips. Final script suite: 505 tests, 19.922 seconds, OK, one skip. Fresh coverage: 86.7 percent.
Skipped cases are Windows-only path behavior, this host's git-lfs hook behavior, and explicitly opt-in live Terminal automation; no skip is represented as a passed platform proof.
Ruff, format, mypy, embedded lint, plugin validation, version parity and native Claude/AGY validators pass. Both hook copies and all three byte-pin owners agree; versions and the COMPATIBILITY sync marker are unchanged.
The initial 3,384-test run had two failures/one error; 164 affected tests recovered them. That history and the premature oracle edits before FO disposition remain disclosed above. The final rerun was required by burndown after Mode 2/docs changed bytes.
Review budget: three independent lenses, one completeness critic and one reproducing arbiter; five workers used, zero confirmed findings, no review-driven candidate edits. All reviewed the final head.
Independent artifacts: /tmp/spacedock-dispatch/drc-4025-review-{lens1,lens2,lens3,critic,arbiter}.md; hashes in drc-4025-review-manifest.json. Their addressable worker handles remain available.

### Surface and handoff

Actual runtime: 13 files / 514 changed lines; tests/oracles/support: 17 / 688; docs: 7 / 186. All stay within each approved range plus 25 percent tolerance.
Delivery: two DCO commits, 37 files, 1,255 additions and 133 deletions. PR 335 is on the reviewed head; readback reported BLOCKED while required PR checks/review remained pending.
The branch is pushed and tracked worktree clean. All implementation-owned review servers and harness probe processes are stopped; only ignored screenshots/probe evidence remain locally.
The exact PR draft and evidence were sent to FO before creation; publication used the captain's standing delivery authorization without a new approval round. No merge or post-merge Linear reconciliation occurred.
Remaining risks are the accepted incomplete lexical coverage, duplicate/reordered reports, logical expiry/current-run loss on restart, enabled-replacement race and qualified timing. Supported-platform CI and fresh Copilot/PR review remain the next stage's work.

### Summary

C6 now reports the admitted command shapes with fixed labels and explicit evidence limits, from hook reduction through bounded memory retention to session detail and Attention. Implementation is complete and PR 335 is ready for the fresh review stage.

## Stage Report: review

Verdict: **REJECTED / NO-GO**. PR https://github.com/spacedock-dev/cargento/pull/335; head `735785dd3699df01d2ec1b7dbd7de1fa9bbaa66e`; base `4b2120dac7dfe0ca63ebe8c5fc7f28d8d4fc1801`; MERGEABLE / BLOCKED, not CLEAN.
Depth: full adversarial security review retained from three independent lenses, completeness critic and reproducing arbiter; one fresh reviewer used, zero additional workers, no candidate edits or repeated owned suites.

- DONE: Independently account for all six approved ACs using the actual candidate and boundary evidence, with the required security lenses and reproducing arbitration completed before opening the PR.
  Five SHA-verified candidate-qualified artifacts and production diff cover all six; AC-2 scheduling proof and AC-6 Windows containment remain unfulfilled as detailed below.
- DONE: Read current-head CI and all top-level/Copilot inline comments, investigate new findings read-only, and route any owned material correction with its evidence and proposed disposition.
  All 12 check-run head SHAs match; Windows and quality-gate fail; top-level reviews and inline comments are both empty, including Copilot; FO authorized the one owned Material fix.
- DONE: Report GO or NO-GO with exact PR/head/mergeability, review evidence, actual surface, checklist accounting and safe worktree/merge handoff state.
  NO-GO; correction package below preserves scope and thresholds; worktree remains clean and required for correction, so removal and merge are not ready.
Checklist totals: DONE 3; SKIPPED 0; FAILED 0 review tasks. Acceptance proof: AC-2 partial and AC-6 failed on Windows; this accounting does not claim passing CI.

### Acceptance evidence and limits

AC-1: lens1 verified both real shape-capture hashes against recorder originals and harmless success/failure driver outputs; actual-hook replay covers Bash/tool_input.command. Claude PostToolUseFailure is excluded; Codex success/failure share PostToolUse. No live calls repeated here or successful-effect claim made.
AC-2: lens1's 41 actual-hook cases and 19 ingress refusals, lens2's authenticated refusals, and arbiter's eight hook-to-HTTP-to-reader cases prove fixed six-field/private-sentinel boundaries locally; Windows test_irreversible.py:223 misses four positive reports, so supported-platform socket scheduling evidence is not green.
AC-3: lens3 executes both assembled routes, escapes hostile owner text and distinguishes absence/off/unsupported states; retained Mode 2 live drive proves routing/redraw/focus. Fresh reviewer inspected corrected Attention/session and unsupported screenshots; this is retained browser evidence, not a new browser walk.
AC-4: lens2 compares 1,530 deliveries to an independent ordering/cap oracle (1,000 global, 20/session), checks concurrent/end survival and actual history exclusion; lens3 proves 27 retained/20 displayed; critic serves orphan reports then exact 24h expiry. Logical/current-run retention, duplicates and collection-paced redraw remain explicit limits.
AC-5: lens2 and arbiter exercise malformed/missing/off enablement, stale-on/off HTTP rejection and fresh-off matcher suppression; authored listener replacement and real spawn argv through child parser/config prove off propagation. No detached OS daemon respawn was independently launched; approved enabled-replacement race remains.
AC-6: lens1 separately measures actual sleep/spin exit and completed-late-success suppression; GIL-regex negative control times out. Current-head Windows sleep subprocess exceeds the authored 250ms startup-inclusive window, so supported-platform containment is unproved; nominal 5ms and 250ms limits remain unchanged.
Artifacts: /tmp/spacedock-dispatch/drc-4025-review-{lens1,lens2,lens3,critic,arbiter}.md; all five SHA-256 values match drc-4025-review-manifest.json and head 735785d. Zero pre-PR findings; one new current-head CI proof finding.

### Current-head finding and authorized correction

F1 released user/workflow: Windows operator receives admitted Bash after-tool command reports through the normal hook process.
F1 observable harm: four documented positive socket cases fail and actual sleep-hook exit proof times out; the required supported-platform quality gate blocks delivery. This does not establish a lexical product defect or universal scheduling failure.
F1 affected boundary: value-ac[AC-2] positive/private-byte socket evidence; value-ac[AC-6] actual-hook 250ms supported-CI containment; contract[AGENTS.md#quality-gate] required platform checks must pass.
F1 trigger: run 34847818390/job 103988008758 on the exact head, test_irreversible.py:223 missing sqlite3 DROP, rm -Rf, Codex rtk psql DROP and Codex rtk proxy rm -fR reports; line 327 raises subprocess.TimeoutExpired(0.25) for forced sleep. 3,384 tests / 191.518s / four failures / one error / 45 skips; Windows script tests never ran.
Materiality: Material proof failure. Ownership: C6 implementation. Proposed disposition: fix; distinct FO authorization received before any candidate mutation or reviewer rerun. No extra security lens or arbiter needed for the observed CI assertion; cause remains to be isolated.
Diagnosis: run_hook includes Python/import startup before main, while its 250ms parent timer starts before process launch. The 90-positive matrix also conflates fixed lexical/socket correctness with the production daemon's intentional total-start/join-over-5ms discard. Neither causal explanation is proved by the Windows log alone.
Authorized assignment: isolate startup/import, actual-main, matcher/result and process-exit phases with bounded diagnostics; correct the platform/oracle boundary. A readiness handshake may exclude interpreter/import setup only if actual main, daemon worker and real process exit remain inside unchanged 250ms and the excluded startup cost is reported separately. Deterministic socket scheduling/clock control may isolate lexical/private-byte proof only; retain separate unmodified nominal-5ms discard, completed-late-success suppression, sleep/spin shutdown and rejected GIL-regex proofs. Do not delete Windows coverage, weaken positives, raise caps or change production thresholds; run required changed-boundary checks and current-head CI, then return to this reviewer.
Correction inputs: `drc-4025/correction-inputs/review-1/briefing.json` and `briefing.review.jsonl` in the state checkout; rejected snapshot `drc-4025/review-rejected-735785d.md`. The log deliberately awaits implementation's disposition and closing Resolution; FO alone records review/1 after correction. No gate prepare or round record ran here.

### CI, surface and safe handoff

Checks: ten success, two failure, all at 735785d. Quality Gate run 34847818390: lint, mypy, Python 3.11 floor, coverage (86.5%), Ubuntu and macOS pass; Windows and aggregator fail. Validate 34847818269, compatibility smoke 34847818259 and version guard 34847818420 pass. Local 86.7% coverage is distinct from CI's 86.5%.
Raw current-head evidence: code-worktree ignored docs/screenshots/c6-fresh-review/{windows-failure.log,checks.json,reviews.json,inline-comments.json}; actual job summaries were read, not merely check badges.
Surface independently recomputed: runtime 13 files/514 changed lines vs 11–14/450–850; support 17/688 vs 12–15/500–950; docs 7/186 vs 4–6/100–200. Over upper file estimates: support 13.3%, docs 16.7%, within 25%; all LOC ranges satisfied. Total 37 files, +1,255/-133, two DCO commits. ACs unchanged.
Tracked candidate worktree clean; no review server, harness, test suite or daemon launched. Preserve this worktree for correction, PR 224 and sibling work. No merge, branch removal, main reset or Linear update. FO owns eventual merge/removal/reconciliation ordering.
State transport: FO authorized id drc-4025 plus folder-form index.md migration and only the consumed triage room-ref relocation. Old gate identities/digest/approval/application and all room bytes are preserved; status --validate is the shipped validator. The requested gate validate CLI does not exist (exit 2), so no such pass is claimed.

### Summary

Fresh review confirms the retained independent security and reader evidence but rejects this head because Windows leaves required C6 proofs and CI incomplete. Implementation receives one authorized correction with unchanged scope and thresholds; the reviewer remains addressable for the corrected head.


## Stage Report: implementation

- DONE: Diagnose and correct the authorized Windows lexical/socket and containment proof failure while preserving all six ACs and production timing thresholds.
  DCO commits cd37839 and a6c3fcb change only test_irreversible.py; all 90 socket positives and separate real-thread deadline/containment proofs pass on Windows.
- DONE: Run required changed-boundary checks and current-head CI, preserving exact failure and phase evidence and updating the existing PR with DCO commits.
  PR335 head a6c3fcb0a0b95301e1731047ff6d9c5e952540a0 has all 12 checks successful and CLEAN; run34909173461 preserves actual Windows phases.
- DONE: Record all three correction outcomes and actual scope, append the canonical round response and closing advisory Resolution, then return to the retained reviewer.
  Same review/1 log now includes annotation:drc-4025:windows-proof-fixed and resolution:drc-4025:ensign:review-1; FO owns recording and retained-reviewer dispatch.

### Summary

The correction isolates lexical/privacy proof from allowed best-effort scheduling loss and measures interpreter/import startup separately from actual hook work and real exit. Runtime, web assets, production thresholds, enablement rules, report fields and all six ACs are unchanged.
The first correction exposed three diagnostic errors on Windows; distinct FO FIX authorized their correction before a6c3fcb edits. Normal-only observation uses the existing 3s bound; forced sleep/spin and completed late success retain 250ms.

### Acceptance evidence

- AC-1/2: recorded Claude/Codex replay and 90 deterministic socket positives enforce the exact six fields and private-byte exclusion; wrong event/tool, malformed/oversized/ambiguous input and forged ingress still abstain. Copying input into a report or admitting an unknown identifier fails these assertions.
- AC-3: unchanged assembled-reader and Mode2 evidence from735785d retains honest labels, caveats, empty/off/unsupported states and corrected Attention styling; claiming success or all-clear fails the owned reader assertions.
- AC-4: unchanged composed coordinator/snapshot tests retain duplicates, order disclosure, caps, expiry, end and restart semantics; dropping either report in one collection or persisting across restart fails them.
- AC-5: fresh off/missing hooks, off replacement ingress and respawn checks still pass; entering the matcher or accepting/re-enabling a report under off fails them.
- AC-6: Windows sleep and spin returned no report and exited in176.495/219.313ms after88.995/81.363ms startup; each remains below250ms through actual main and real exit.
- Late success: startup80.394ms, main-to-exit191.419ms; matcher_end2701.1456054 > report_return2701.1229473, report_present=false. Waiting for worker completion replaces arbitrary80ms padding; late publication or wrong ordering fails.
- Normal matching: five real accepted reports, main-to-exit310.752–322.699ms, startup80.299–105.471ms; measured separately within3s, without a250ms normal-path claim.
- Injected GIL-regex: timeout250ms after81.792ms startup; exact fixed stderr marker plus empty stdout and no report asserted. Only this test control emits a diagnostic; normal/sleep/spin/late hook stdout and stderr remain empty.

### Verification and preserved failures

- Original Windows735785d run34847818390:3384tests/191.518s, four failures, one error,45skips; script step did not run. Its log alone does not establish the failing timing phase.
- Windowscd37839 run34850970910:3387tests/229.132s, one failure, two errors,45skips; all90 positives and sleep/spin passed, but normal measurement, fixed late padding and regex file marker failed. Preserved without rewriting this run as green.
- Final Windowsa6c3fcb run34909173461/job104192628325:3387tests/174.899s,45skips;361scripts/11.384s,4skips; no new skip introduced by this correction.
- Final local:20 focused tests;3387dashboard/93.451s,2skips;505scripts/19.376s,1skip;86.7%coverage. Skips remain Windows-only path, this host's git-lfs behavior and opt-in Terminal automation.
- CI coverage:3387tests/98.270s,1skip;505scripts/14.489s,4skips;86.5%. Ruff/format/mypy/embedded/plugin/version/native validators pass; initial formatting check needed one formatter-only correction before final suite.
- Logs are in the candidate's ignored docs/screenshots: drc-4025-rejected-windows.log, drc-4025-correction-windows.log, drc-4025-correction-final-{focused,dashboard,scripts,static,coverage,windows,ci-coverage}.log. Full phase records are retained there.

### Surface and handoff

- Final PR:37files,+1425/-133 =1558changedLOC, four DCO commits. Runtime13/514 and docs7/186 unchanged; support17/858 versus pre-correction17/688, within approved tolerance.
- sync-docs found no correction drift; version fields and COMPATIBILITY sync marker unchanged. Prior five-person independent review and browser artifacts remain valid for unchanged runtime; no extra review fanout or full-suite repetition after this green candidate.
- Proposed FO projection: Cycle 1 — review: 1 owned Material proof failure fixed; 0 declined; final37files/1558changedLOC (runtime13/514 unchanged, support17/858 from17/688, docs7/186 unchanged); all six ACs unchanged; exact-head CI green on a6c3fcb; return to retained reviewer.
- Canonical response is advisory only. No round recorded, gate prepared, merge, cleanup, or Linear reconciliation performed by this worker.

## Stage Report: review (cycle 2)

- DONE: Independently account for all six approved ACs using the actual candidate and boundary evidence, with the required security lenses and reproducing arbitration completed before opening the PR.
  Runtime/web are byte-unchanged from the five-worker security-reviewed head 735785d; corrected test boundaries and actual Windows phase evidence now close the formerly missing AC-2/AC-6 proof.
- DONE: Read current-head CI and all top-level/Copilot inline comments, investigate new findings read-only, and route any owned material correction with its evidence and proposed disposition.
  All 12 check-run objects name a6c3fcb and SUCCESS; actual Windows job and preserved red logs read; top-level reviews and inline comments both empty, including Copilot; F1 fixed, no new finding.
- DONE: Report GO or NO-GO with exact PR/head/mergeability, review evidence, actual surface, checklist accounting and safe worktree/merge handoff state.
  GO on PR335 / a6c3fcb0a0b95301e1731047ff6d9c5e952540a0 / CLEAN / MERGEABLE; tracked worktree clean, correction complete, FO retains cleanup/merge ownership.

### Verdict and review depth

**GO / PASSED.** PR https://github.com/spacedock-dev/cargento/pull/335; head `a6c3fcb0a0b95301e1731047ff6d9c5e952540a0`; base `4b2120dac7dfe0ca63ebe8c5fc7f28d8d4fc1801`. All three review checklist items DONE; SKIPPED 0; FAILED 0.
Full adversarial security depth remains the original three independent lenses, completeness critic and reproducing arbiter. This retained-reviewer pass uses zero additional agents and no broad suite/browser rerun: only test_irreversible.py changed after reviewed head735785d (+180/-10 across two DCO correction commits).
The immutable review/1 room contains original finding/reviewer revise plus implementation disposition/closing Resolution; pointer `round:drc-4025:review:1` was read. F1 is fixed within its authorized scope; zero declined findings and zero new findings. The room was not edited or recorded again.

### Acceptance evidence

AC-1: retained lens1 capture-hash/live-driver evidence and measured Claude/Codex Bash/tool_input.command replay remain valid. Current deterministic replay still drives real main and socket, including Claude failure-event exclusion; it neither assumes alternate fields nor infers successful effects. No live capture repeated here.
AC-2: all 90 literal/wrapper/harness positives remain; only worker scheduling and elapsed-clock controls are replaced in that lexical/privacy oracle. Actual matcher, reduction, main, transport, ingress, retained and served projections remain exercised. Independent sensitivity probe passes the control and makes missing matcher result, missing report, wrong fixed label and bypassed main each fail the same authored socket assertion; copied private bytes/unknown patterns remain covered by unchanged negative/forgery tests and the original security lenses.
AC-3: unchanged reader assets retain lens3 assembled-route/escaping/absence proofs and Mode2 browser routing/redraw/focus evidence. Fixed shape labels, successful-effect disclaimer and empty/off/unsupported wording remain; no new browser walk was warranted for a test-only correction.
AC-4: unchanged ledger/reader evidence from lens2, lens3, critic and arbiter retains concurrent/coalesced/end survival, 1,530-delivery ordering oracle, 1,000 global/20-session caps, exact logical 24h expiry, restart loss, actual history exclusion and 27-retained/20-displayed counts. No durable history or exactly-once claim is added.
AC-5: unchanged actual-hook missing/off matcher suppression, off-replacement authenticated ingress and spawn argv through real child parser/config evidence remain. A detached OS daemon was not independently relaunched; the approved enabled-replacement race remains explicit.
AC-6: fresh Windows log34909173461/job104192628325 shows forced sleep176.495ms and spin219.313ms from parent stdin release through actual main, socket path, daemon worker, diagnostic write and real process exit. Startup88.995/81.363ms is separately measured and excluded, as FO authorized; each containment assertion remains250ms and silent/no-report.
Completed late success:191.419ms after80.394ms startup; matcher_end2701.1456054 > report_return2701.1229473, report_present=false, no socket report. This proves the worker completed after return and before real exit, rather than relying on fixed padding.
The injected GIL-regex still times out at250ms after81.792ms startup; its exact fixed stderr marker proves matcher entry, with empty stdout/no report. Only this negative control writes that marker. The production nominal wait stays0.005; the separate completed-worker6ms clock control proves late-result discard without altering that value.
Normal matching is separate: all five Windows normal observations emitted the expected report, main-to-exit310.752–322.699ms, startup80.299–105.471ms, under the ordinary3s observation bound. Neither this path nor interpreter/import startup is claimed below250ms; no universal scheduling guarantee is claimed.

### Independent sensitivity and preserved CI evidence

Independent probe: code-worktree `docs/screenshots/c6-review-cycle2/oracle-sensitivity.py`, invoked via `python3 -B -m docs.screenshots.c6-review-cycle2.oracle-sensitivity`. It restricts the existing matrix to one literal across both harnesses/three wrappers, then injects four child-process-only counterfactuals; control passes, each mutant gives one expected assertion failure and zero errors. No candidate byte changes; owned fixture listeners/processes cleaned up.
Fresh raw checks/reviews/comments/Windows log and probe results are under ignored `docs/screenshots/c6-review-cycle2/`. Four workflow check families are green on the exact head: Quality Gate34909173461, Validate34909173482, compatibility34909173491, version guard34909173470. Current-head checks API confirms all12 SHAs and conclusions; no stale badge inference.
Windows final:3,387 dashboard tests/174.899s/45skips and361 script tests/11.384s/4skips. Quality Gate job summaries show no unsuccessful/skipped steps. CI coverage86.5% (3,387/1skip;505scripts/4skips) is distinct from retained local86.7% (3,387/2skips;505/1skip). No correction added a skip.
Original735785d Windows red remains four failures/one error/45skips. Intermediatecd37839 red remains one failure/two errors/45skips: fixed late padding exceeded containment, normal timing incorrectly shared250ms, regex file marker was empty. Read retained logs; the final correction replaces those diagnostic mistakes without rewriting them as passes or increasing the forced-case limit.

### Surface and cleanup handoff

Independently recomputed final surface:37files,+1,425/-133=1,558changedLOC. Runtime13/514 and docs7/186 unchanged; support17/858 versus original17/688. Approved ranges are runtime11–14/450–850, support12–15/500–950, docs4–6/100–200 plus25% tolerance; support file overage13.3% and docs16.7% remain within tolerance, every LOC range satisfied. All six ACs and production thresholds/caps remain unchanged.
Tracked worktree clean and four candidate DCO commits pushed; no pending correction or review-owned process remains. Worktree is ready for FO cleanup after preserving its ignored screenshots/log/probe evidence; FO then owns merge, branch deletion and reconciliation. This reviewer removed nothing, merged nothing, did not touch PR224/siblings, and made no Linear or gate-authority changes.

### Summary

The authorized correction now separates lexical/privacy evidence from scheduling and proves the actual Windows hook/exit boundary without changing the production contract. Current-head CI and the bounded independent review support GO; retained startup, best-effort scheduling, current-run retention and coverage limits remain explicit.
