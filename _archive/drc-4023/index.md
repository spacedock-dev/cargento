---
id: drc-4023
title: 'C4 · My goals across sessions'
status: done
source: https://linear.app/recce/issue/DRC-4023
started: 2026-09-14T12:49:38Z
completed: 2026-09-15T02:06:09Z
verdict: PASSED
score: 0.2
worktree: .worktrees/spacedock-ensign-drc-4023
issue:
pr: pr-merge:337
mod-block:
linear-status: Done
milestone: 'Steer before waste'
release: 'later'
estimate: 'L'
reconciled: 2026-09-15T02:05:36Z
promise: P2
move: extend
gates:
    version: 1
    records:
        - id: gate:drc-4023:triage
          stage: triage
          attempts:
            - id: gate-attempt:drc-4023-triage-1
              briefing:
                id: briefing:drc-4023:triage:attempt-1:revision-1
                digest: sha256:aaff5fdde76caabee8fb748744e17ac8fa702983d9851fbe47ec3e1e949438e6
                room-ref: ./review/triage/briefing-1
              resolution:
                type: Resolution
                id: resolution:spacedock:drc-4023:triage:1
                briefing: briefing:drc-4023:triage:attempt-1:revision-1
                by: agent:first-officer
                at: "2026-09-14T13:18:30.087371Z"
                decision: approve
                reason: Accept bounded board-and-retained union with separate provenance, honest absence and preserved withdrawal; seven detailed ACs directly reviewed, three completed triage items, measured source/browser gaps, separate scope tolerances and serialized frontend integration. Existing captain scope and completion grant covers the recommended approach.
                conn:
                    quote: yes I approve the scope. go ahead and take your recommended approach for the following tickets needed to close out this milestone, I trust you
                    source: Captain message in this conversation, 2026-09-14
              application:
                target-stage: implementation
                state: consumed
        - id: gate:drc-4023:review
          stage: review
          attempts:
            - id: gate-attempt:drc-4023-review-1
              briefing:
                id: briefing:drc-4023:review:attempt-1:revision-1
                digest: sha256:ffc9b09414c9365e9807ac1a29871542f157891a2e9cae7789fc6cf35df76801
                room-ref: ./review/review/briefing-1
              resolution:
                type: Resolution
                id: resolution:spacedock:drc-4023:review:1
                briefing: briefing:drc-4023:review:attempt-1:revision-1
                by: agent:first-officer
                at: "2026-09-15T02:03:17.75228Z"
                decision: approve
                reason: Fresh GO verifies all seven unchanged ACs, three DONE and no failed/skipped checklist items. Current head 09cd65d has twelve successful checks and CLEAN mergeability. Owned malformed-cache finding fixed, canonical implementation/1 recorded before retained-arbiter PASS; all scope budgets respected. Approve actual merge and six-step reconciliation.
                conn:
                    quote: yes I approve the scope. go ahead and take your recommended approach for the following tickets needed to close out this milestone, I trust you
                    source: Captain message in this session approving the recommended milestone ticket scopes on 2026-09-14, followed by repeated continue directives
              application:
                target-stage: done
                state: consumed
review-round:
    id: round:drc-4023:implementation:1
    stage: implementation
    cycle: 1
    briefing:
        id: briefing:drc-4023:implementation:round-1
        digest: sha256:c0b8a4a2ae73ff05e5c83eed7dc75fce6089ce928cfc6d1d0e7ad27613116358
        room-ref: ./review/implementation/round-1
archived: 2026-09-15T02:06:09Z
---

[DRC-4023](https://linear.app/recce/issue/DRC-4023) — Linear priority Medium, estimate L.

The live issue and milestone originals are preserved below. Triage drafts their revisions here; implementation publishes them after the gate.

## Problem

The current board-to-Intent population and deterministic/workflow source gap remains; see the evidence and bounded rewrite below.

## Proposed approach

See the corresponding subsection in the dated triage below.

## Linear edits made

Approved drafts published and read back 2026-09-14T13:20:46.669Z: DRC-4023 is In Progress, with journey:mid-flight and move:extend and its three existing labels retained. The issue matches the full approved draft, including its verbatim historical description. The freshly fetched milestone received only the C4 clause/build note and status-free Waits on sentence; C1/C6 clauses and notes were preserved. Originals below remain the 2026-09-14T12:49:12.877Z snapshot; all three issue comments were refreshed with hasNextPage=false.

### Original issue description

````markdown
## User value

A person tracking several sessions at once notices this once they can see each one's stated goal in one place, instead of reopening a transcript to remember what they asked for. P2, extend: a read-only roll-up of each session's stated goal is a new clause on what it's doing now, with no drift judgment attached.

## What needs to be done

Narrowed on 2026-09-11, after the Intent log shipped in PR 317. The one-place read-only view exists and is reachable, so what is left is the population it draws from and the sources it reads.

Three goal sources exist in the tree and the Intent log reads one of them. Fold in the deterministic observer's derived goal and the Spacedock workflow goal, each labelled by source, so a session says what it is for whether or not anyone typed against it.

Cover the board rather than the store. The Intent log's rows are the annotation store's, so a session nobody typed against has no row at all. This issue's population is every session on the board, including the ones with no goal from any source.

Correct the board's own gap line at `next-observed.js` once that lands. It still reads that nothing normalises goals.

Out of scope, because PR 317 built them: the one-place top-level view, the read-only constraint, the no-judgment disclaimer, and keeping the words after the row leaves the board.

The original sentence said to source the goal from Spacedock entity state and that nothing else provides it. That stopped being true when the annotation store and the deterministic observer both began publishing one.

Alternative: this is the narrower version of <issue id="296fccf7-6d98-4305-be7c-e6eebd5c8088" href="https://linear.app/recce/issue/DRC-4022/c3-working-outside-its-scope">DRC-4022</issue> (C3, working outside its scope), it scores higher, and it is the one to build.

## Scores (blind-panel medians)

| Impact | Risk-adjusted impact | Access | Build | Detector risk |
| -- | -- | -- | -- | -- |
| 55 | 47 | 50 | 55 | 8 |

Score legend: see the Visibility 2x2 board README.
````

### Original milestone description

````markdown
## The user value

**For each live session: what it is doing now, what it plans next, how far into the current turn it is, and an estimate of when that turn ends. It tells you when that changes instead of making you poll.**

## What is left

[C1](<https://linear.app/recce/issue/DRC-4020/c1-subagent-workflow-stage-and-a-tripwire-on-it>): Cargento saves a stage you choose for a Spacedock workflow and alerts once when it observes an entity enter that stage; gaps and unavailable sources are stated, and a notification request does not prove a banner appeared.

[C4](<https://linear.app/recce/issue/DRC-4023/c4-my-goals-across-sessions>): every session on the board says what it is for, from whichever source knows, not only the ones you typed against.

[C6](<https://linear.app/recce/issue/DRC-4025/c6-report-the-irreversible-things-that-happened>): Cargento reports destructive command shapes observed after a tool call while you were not watching, such as a force push; a report does not prove the effect succeeded.

## Waits on

Nothing. Every gate this milestone had is clear, so all three are free to start.

## Read before building

* [DRC-4023](<https://linear.app/recce/issue/DRC-4023/c4-my-goals-across-sessions>): the one-place read-only view shipped on 2026-09-11 as the Intent log, and C4 narrowed to what it does not do. Read the issue before building: the view, the read-only constraint and the no-judgment disclaimer are out of scope now, and the remaining work is the population and the two goal sources it does not read.
* [DRC-4025](<https://linear.app/recce/issue/DRC-4025>): read SECURITY.md, "Irreversible actions (hook-side destructive-shape matching)", before building. It permits hook-side pattern identifiers, tool names and timestamps only; the runtime input-reading rule is an allowlist, and the report and its off switch remain unshipped.
* [DRC-4020](<https://linear.app/recce/issue/DRC-4020>): read the [approved C1 triage contract](<https://github.com/spacedock-dev/cargento/blob/425a6bb9d37a9cfba00d4b87fd137ac249f1cfa8/drc-4020.md#acceptance-criteria>): exact workflow/state binding, current entity-file evidence, the measured Codex boot wrapper, first-observation/gap baselines and explicit Rearm are part of the scope. Existing browser notes stay unenforced.
````

## Expected surface and tolerance

See the corresponding subsection in the dated triage below.

## Acceptance criteria

AC-1 through AC-7 below carry the offline/interactive split, concrete proof, and falsifying changes.

## Test plan

See the corresponding subsection in the dated triage below.

## Review depth

Two bounded lenses plus a reproducing arbiter at review; the rationale and boundaries are below.

### Feedback Cycles

- Cycle 1: REJECTED — implementation pre-PR source review / reproducing arbiter; surface 19/612 vs estimate runtime 6/420, behavioral 420, compelled 60 across at most 9 oracle files, docs 6/90 (48.8% runtime, 77.6% behavioral, 43.3% compelled, 61.1% docs); AC unchanged. Owned Material cache-decoding failure fixed on 09cd65d under distinct FO authorization; retained arbiter re-review follows the canonical implementation/1 record.

## Out of scope

See the corresponding subsection in the dated triage below.

## Triage — 2026-09-14

### User value

A person watching several sessions can open the Intent log and see each board session's available goals and their sources, including a clear absence when no source has a goal. P2, extend: this adds the board population and cached deterministic and workflow goals to the existing view, without judging progress against them.

Labels to retain/set: `journey:mid-flight`, `move:extend`; retain `release:later`, `origin:workshop`, and `alternative`. Classification: feature; Medium, L; assigned to Jared Scott; no blockers. Branch supplied by Linear: `feature/drc-4023-c4-my-goals-across-sessions`; no C4 implementation worktree exists. C1/C6 are in sibling worktrees and remain in progress. The complete selection snapshot contains 319 issues and ends with `hasNextPage=false`; selection's completed-issue receipts are already reconciled by the FO.

### Current state and adversarial findings

At main `4b2120d`, `next-intent.js` reads annotation rows only. PR 317's reachable top-level view, retained departed words, revision/readings/discard records, and their disclosures are shipped. The narrowed population/source problem remains real. The September 9, 10, and 11 comments describe this transition; the earlier claim that only Spacedock supplies goals is already superseded. Related annotation/reading issues are context, not permission to rebuild them; C3 is the alternative and C7 remains canceled.

`nextRows()` is the actual dashboard-session collection. `nextIntentLiveProjects()` omits blank project labels, so it cannot answer membership. `nextObservedGoal()` prefers the latest assignment; borrowing it would silently substitute a different source for the requested deterministic derivation. `observer.read_sidecar()` bounds the file but does not validate published prose. `project_context._observe_session(refresh=False)` distinguishes model/unknown provenance and stale signatures, but rejects undated sidecars; it is not the smallest reusable projection. `http_api._observe` triggers analysis and a write and has no observation timestamp, so it cannot serve this list's polling.

`spacedock.read_workflow()` admits only bounded README frontmatter from a commissioned workflow, and `session_workflows()` publishes its title as `goal`. Missing title means no goal; body headings are not a fallback. C1's incoming measured Codex boot wrapper and workflow attachment will broaden that existing published source, but are not merged at this triage. C4 consumes the existing `session.spacedock.workflows` shape and does not implement another discovery path.

### Mode 1 evidence

Promise quoted from `docs/promise-map.md`: “for each live session, what it is doing now, what it plans next, how far into the current turn it is, and an estimate of when that turn ends. It tells you when that changes instead of making you poll.” The shipped backing relevant here is typed goal/expected output beside published source evidence; its limit is that sources differ and a reading is never proof the work was done.

Started the tree on spare port 18743 with isolated `CARGENTO_HOME`, no usage fetch, model, git, focus, history, dismissal, ask, or event actions. `/api/data` contained seven sessions. The primary navigation opened Intent log by mouse and rendered “Nothing has been typed against any session yet.” The seven sessions produced no rows. Screenshot: `docs/screenshots/drc-4023-triage-live-intent-empty.png`.

An isolated fixture server on 18744 served the unchanged assembled page and three board rows (`typed`, `untyped`, `unprojected`, the last with blank project) plus retained annotations and a discarded record. The view showed three typed rows and one discard, omitted `untyped`, retained departed words, and wrongly told the still-present `unprojected` row “Not on the board now, so there is nowhere to open. The words are here.” Screenshot: `docs/screenshots/drc-4023-triage-retained-unprojected.png`. FO disposition: membership/navigation separation is owned by C4; broader navigation redesign is excluded.

With the same three board rows, each forced state removed all rows: off said “Annotations are off for this run”; HTTP 503 said “The annotation store could not be read, so this is unread rather than empty”; delayed response said “Reading the annotation store.” These are the absence cases the new list must correct, while retaining their annotation-specific meaning. No additional product finding was promoted.

The scratch source experiment executed current `read_sidecar`, cached projection and workflow parser with `observer.analyze` patched to fail if invoked. Explicit deterministic text survived; model text and unknown-source text were rejected by the candidate admission; a separately retained `deterministic_goal` survived a model result; the existing reader marked mismatched signatures `cached-stale`; an undated deterministic sidecar remained undated and was rejected by the existing cached projection. Malformed text, absent goal, and `NO_GOAL` supplied no candidate. A titled workflow supplied only its title; an untitled one supplied an empty goal despite a body heading. This is evidence for the proposed rule, not a claim the new projection is implemented. The disposable fixture initially used the wrong stage YAML shape; correcting it to the repository's `stages.states` schema made the parser checks pass.

### Recommended approach

Use one row per `(harness, sid)` in the union of current dashboard sessions and the current retained annotation/discard records. Keep board presence separate from the optional project route. Group board rows and departed retained rows explicitly; derive visible totals and reading denominators from the sets each sentence names. Keep annotation-store eviction wording scoped to retained annotation records, since board-only rows do not occupy that store.

Add a bounded, read-only cached deterministic projection beside `observer.read_sidecar`, and attach it to each published board row through `aggregate`; declare its absent shape in `sessions.base_session`. Admit a nonempty, scrubbed, capped `deterministic_goal`, or the capped `goal` only when `goal_source` explicitly equals `deterministic`. Treat the observer's `NO_GOAL` sentinel as absence. Never use latest assignment or raw model/unknown-provenance goal as this source. A separately retained deterministic goal is still admissible when the preferred goal is model-written.

Every admitted observer line says it is cached and that its currentness has not been checked. Preserve a valid finite observation timestamp when present; otherwise say “Observation time unknown.” Do not resolve or reread transcripts to claim freshness. A changed transcript or a stale cached sidecar therefore never becomes a newly observed/current goal; the list continues to present only the saved derivation and its limit. Missing/malformed/unreadable sidecars render “No cached deterministic goal available,” without implying that analysis found nothing. Reads are bounded per collected row by the existing sidecar cap and add no model call, analyzer call, sidecar write, or new persistent store. Recollecting publishes changed/removed sidecar evidence; rendering, navigation, and annotation fetches do not analyze sessions.

Render typed goal and expected output as typed sources, admitted deterministic goal as a cached derivation, and each already-published workflow goal with its workflow label. Show coexisting sources without overwriting one with another. A missing workflow title says “No workflow goal published”; a disabled Spacedock source says it is off (publish the existing configuration switch if needed); neither is filled from README body. No source yields “No goal available from these sources.” Annotation off/loading/error blocks only typed evidence, not board membership or other sources. Discard records retain their own explanation/readings rules; unrelated deterministic/workflow sources may still show, labeled independently, without restoring withdrawn typed text from history or late annotation responses.

Keep existing annotation generation/revision invalidation and its early removal on discard. Count readings only among retained annotation rows eligible to hold words/readings, never among the new board-only rows. Keep retained departures and their no-verification wording. Remove C4's obsolete “Nothing normalises them yet” gap only when this behavior lands.

Rejected simpler alternative: add workflow/assignment text to the existing annotation list. It leaves every unannotated session absent and changes the requested source. Reusing the richer cached project-context route also drops undated deterministic sidecars and needlessly imports its orchestration boundary. Automatic observation of all sessions would add work and writes absent from this request.

### Acceptance criteria

- **AC-1 — interactive:** Intent log lists every current board session once, plus departed retained annotations/discard records, including a board row without a project and a row with no goal. **Verified by:** Mode 2 browser walk comparing `/api/data` identities and annotation identities with rendered rows; visible text distinguishes “On the board; project not published” from departed rows. **Falsified by:** filtering membership through the project map, omitting the unannotated/no-goal row, duplicate identities, or a misleading departed label.
- **AC-2 — offline:** The assembled page shows available typed goal/output, cached deterministic goal, and each published workflow goal with distinct source labels on one row; no source produces an explicit absence. **Verified by:** extend the existing assembled-page harness with independent three-source and source-empty payloads and assert rendered text. **Falsified by:** latest assignment/model text appearing as deterministic, one source replacing another, or workflow body text appearing as its goal.
- **AC-3 — offline:** Cached deterministic admission is bounded, scrubbed and explicit about provenance and time, without analysis. **Verified by:** table-driven real sidecar reads for deterministic, model-only, model-with-deterministic, unknown provenance, undated, stale signature, malformed, missing, and NO_GOAL cases; assert published text/source/time and rendered cached/currentness-unknown wording; patch analyzer/model/sidecar writer/transcript resolver to fail during collection. **Falsified by:** admitting raw model/unknown text, inventing a timestamp, calling a prohibited producer, or describing stale/undated evidence as current. Include hostile strings and invalid/nonfinite timestamps at the publication boundary.
- **AC-4 — offline and interactive:** Annotation off/loading/error never hides current board rows or their non-annotation sources; missing or disabled workflow evidence remains explicit. **Verified by:** assembled-page async fetch fixtures and Mode 2 browser drives for each state, including an all-sources-empty row and a Spacedock-off payload. **Falsified by:** a whole-view early return, “nothing typed” standing in for a failed read, an off source supplying cached words, or an empty title becoming a goal.
- **AC-5 — offline and interactive:** Discard or withdrawal removes typed words/readings at once; retained departed words, discarded records and departure disclosures retain their established semantics; a separately labeled deterministic/workflow source cannot be mistaken for the withdrawn annotation. **Verified by:** retain and adapt existing actual-store/assembled-page late-response, invalidation, unwritable-discard, off and departed-row tests; browser sequence from typed to discarded while another source exists. **Falsified by:** history or a late response restoring a withdrawn annotation, deleting the discard record, claiming successful withdrawal after its write failed, or restoring its reading.
- **AC-6 — offline:** List totals, typed/discard totals and reading denominators agree with their rendered sets; annotation eviction limits describe that store only. **Verified by:** assembled-page mixed board-only/typed/departed/discard fixtures with at least one assessment and one departure; assert numeric text and actual row collections independently. **Falsified by:** counting a board-only/default row as typed or checked, counting a discard in a reading denominator, or saying the bottom board-only row is next for annotation eviction.
- **AC-7 — offline:** The change remains within existing source/retention contracts and integrates with C1's published workflow attachment without assuming its merge. **Verified by:** session-constructor and every-harness payload equality, reviewed import graph, all three assembled-page byte-pin files, focused existing workflow parsing tests, docs validation, and then the canonical pre-PR suite from `AGENTS.md`; after integrating C1 rerun the focused workflow/source and assembled-page cases. **Falsified by:** an undeclared field/import, stale byte pin, source read outside the admitted caches/frontmatter, or docs still promising the annotation-only population after the feature lands.

### Expected surface and tolerance

Recommended calibrated delivery estimate after gate: 2–3 hours plus CI/merge serialization; uniform full adversarial review would likely take 4–6 hours and is not selected. Triage uses one owner and zero additional readers; tolerance is zero additional agents. C1 owns the only current web implementation branch, so serialize C4's web work after it or explicitly consolidate through the FO; no competing web PR.

Runtime: approximately 260–420 changed lines across five required existing files (`observer.py`, `aggregate.py`, `sessions.py`, `web/next-intent.js`, `web/next-observed.js`), with at most one small `web/styles.css` layout adjustment after visual need is demonstrated. No new runtime module, route, model power, threshold, or store is planned. The existing Spacedock switch can be published from aggregate without changing config. Semantics moved: Intent population, source presentation, cached-evidence absence, board membership versus route availability, and the sentences/counts scoped to those populations.

Behavioral oracles: approximately 260–420 changed lines across `test_observer.py`, `test_next_intent.py`, and `test_sessions.py` (including the collection-level no-analysis proof). Compelled oracles are budgeted separately: approximately 20–60 changed lines across `test_contracts.py` (aggregate→observer import edge), `test_sessions.py` (declaration/payload equality), `test_next_page.py`, `test_next_flag.py`, and `test_focus.py` (all byte pins). `test_next_observed.py` may need a small gap-list expectation update; no new test file is compelled by the inspected contracts. Existing `test_spacedock.py` cases guard title-only parsing. If a producer mapping or strict fake needs a new field, update it in the same existing owning test, not by weakening equality.

Docs: approximately 40–90 changed lines across the shipped skill's Intent paragraph, `docs/promise-map.md` P2 backing/limits, `docs/design-runtime-architecture.md`, and `docs/design-reader-state.md` if the redraw ownership changes. `sync-docs` checks `README.md`, `HOW_TO_USE.md`, and documentation tests; allow at most two further existing docs/oracle files if compelled, explaining each. Do not advance `COMPATIBILITY.md`'s shared sync marker from the branch. The headline promise remains the same; adding source coverage belongs in its backing and limits.

Tolerance: +25% on the upper changed-line estimate in each runtime, behavioral-oracle, compelled-oracle and docs category, not pooled; runtime at most six files, total oracle files at most nine, docs at most six. No new module/test file/store/automatic analysis or source power within tolerance. A larger surface returns to the FO before implementation expands. Full pre-PR suite once, then isolated reruns for contention failures per AGENTS; triage ran only the focused Intent suite (46 tests, passing).

### Review depth and test plan

Two bounded lenses (population/retention behavior and source admission/publication) plus an arbiter who reproduces disputed findings, because this changes `web/` and a published source field. No generic six-agent review; if implementation expands a security boundary, return for that scope decision. Write the source/union absence oracles first, observe the relevant reds, implement, then mutate the defended admission/membership/invalidation source to prove the tests fail; restore by file copy. Run Mode 2 before the PR, then sync-docs and the canonical pre-PR suite. The 46 current Intent tests passed in 0.498s; they protect existing withdrawal/retention/reading behavior, not the unimplemented union. The source experiment made no analyzer call and executed actual current parsers.

### Out of scope

Rebuilding the top-level view; goal history; cross-project grouping/filtering; session writes; model calls or automatically deriving every session's goal; reading judgments; transcript/diff discovery; new workflow discovery/boot instrumentation already owned by C1; broad navigation changes; C6; C7. No Linear rewrite is published during triage.

## Drafted Linear issue description

````markdown
## User value

A person watching several sessions can open the Intent log and see each board session's available goals and their sources, including a clear absence when no source has a goal. P2, extend: this adds the board population and cached deterministic and workflow goals to the existing view, without judging progress against them.

## What needs to be done

Extend the existing Intent log to the union of all current board sessions and retained annotation/discard records, once per harness/session identity. Board membership must not depend on a project link, goal availability, or annotation loading, failure, or off state.

Show typed goals/output, cached deterministic observer goals, and already-published Spacedock workflow titles as distinct sources. Admit separately retained deterministic_goal, or goal only with explicit deterministic provenance; reject model/unknown goal text, malformed text and the no-goal sentinel. Bound and scrub at publication. A saved derivation is cached, with currentness not checked; preserve its observation time or state that it is unknown. No automatic analysis, model calls, transcript resolution, sidecar writes, or new discovery route. An untitled or disabled workflow supplies no goal; never use its README body or latest assignment as a substitute.

Keep the annotation store as the authority for retained/withdrawn words, with existing revision invalidation, discard records, readings, and departures. Distinguish a still-present row with no project from a departed row. Count board rows, typed records, discarded records and reading-eligible rows from their actual populations; scope eviction wording to annotation records. Remove the obsolete C4 gap in next-observed.js after delivery. C1's incoming measured Codex workflow attachment is consumed through the existing published shape after integration, not presumed shipped here.

## Acceptance criteria

* AC-1 (interactive): every board identity and retained record appears once, including unprojected/no-goal rows. Verified by: browser list compared with both API collections. Falsified by: an omitted/duplicate identity or false departed label.
* AC-2 (offline): coexisting sources have separate labels and honest absences. Verified by: assembled-page three-source/empty fixtures. Falsified by: a source substituted or overwritten.
* AC-3 (offline): bounded deterministic admission remains cached and undated when appropriate, without producing analysis. Verified by: actual sidecar provenance/stale/undated/malformed cases and producers patched to fail. Falsified by: model/unknown text, fabricated time/currentness, or a producer call.
* AC-4 (offline/interactive): annotation off/loading/error leaves board rows and other sources visible; workflow off/missing title stays explicit. Verified by: async assembled-page fixtures and browser drives. Falsified by: whole-view disappearance or fabricated workflow goal.
* AC-5 (offline/interactive): withdrawal/discard and retained departed records preserve their existing semantics. Verified by: actual-store and browser discard/late-response sequences. Falsified by: restored typed words/readings or lost retained/discard records.
* AC-6 (offline): counts, reading denominators and eviction copy name the sets they measure. Verified by: mixed-population rendered-row assertions. Falsified by: treating board-only or discarded rows as typed/checked.
* AC-7 (offline): declarations, imports, byte pins, docs and existing source contracts agree. Verified by: the repository's canonical pre-PR checks, plus focused workflow integration after C1. Falsified by: an undeclared field/import, stale pin, broader read, or stale population claim.

## Out of scope

Rebuilding the view; goal history; grouping/filtering; judgment or drift detection; session writes; automatic goal analysis; broad navigation changes; C1/C6 implementation and C7 reopening. C3 remains the alternative. Existing scores, release row and estimate are unchanged.

## Historical scope — superseded 2026-09-14

The following is the verbatim pre-triage description. Its population and sources were correct directions but lacked provenance, absence, and withdrawal rules; those are specified above. Its record of PR 317 and the blind-panel scores is retained.

## User value

A person tracking several sessions at once notices this once they can see each one's stated goal in one place, instead of reopening a transcript to remember what they asked for. P2, extend: a read-only roll-up of each session's stated goal is a new clause on what it's doing now, with no drift judgment attached.

## What needs to be done

Narrowed on 2026-09-11, after the Intent log shipped in PR 317. The one-place read-only view exists and is reachable, so what is left is the population it draws from and the sources it reads.

Three goal sources exist in the tree and the Intent log reads one of them. Fold in the deterministic observer's derived goal and the Spacedock workflow goal, each labelled by source, so a session says what it is for whether or not anyone typed against it.

Cover the board rather than the store. The Intent log's rows are the annotation store's, so a session nobody typed against has no row at all. This issue's population is every session on the board, including the ones with no goal from any source.

Correct the board's own gap line at `next-observed.js` once that lands. It still reads that nothing normalises goals.

Out of scope, because PR 317 built them: the one-place top-level view, the read-only constraint, the no-judgment disclaimer, and keeping the words after the row leaves the board.

The original sentence said to source the goal from Spacedock entity state and that nothing else provides it. That stopped being true when the annotation store and the deterministic observer both began publishing one.

Alternative: this is the narrower version of <issue id="296fccf7-6d98-4305-be7c-e6eebd5c8088" href="https://linear.app/recce/issue/DRC-4022/c3-working-outside-its-scope">DRC-4022</issue> (C3, working outside its scope), it scores higher, and it is the one to build.

## Scores (blind-panel medians)

| Impact | Risk-adjusted impact | Access | Build | Detector risk |
| -- | -- | -- | -- | -- |
| 55 | 47 | 50 | 55 | 8 |

Score legend: see the Visibility 2x2 board README.
````

## Drafted Linear milestone description

````markdown
## The user value

**For each live session: what it is doing now, what it plans next, how far into the current turn it is, and an estimate of when that turn ends. It tells you when that changes instead of making you poll.**

## What is left

[C1](<https://linear.app/recce/issue/DRC-4020/c1-subagent-workflow-stage-and-a-tripwire-on-it>): Cargento saves a stage you choose for a Spacedock workflow and alerts once when it observes an entity enter that stage; gaps and unavailable sources are stated, and a notification request does not prove a banner appeared.

[C4](<https://linear.app/recce/issue/DRC-4023/c4-my-goals-across-sessions>): the Intent log includes every board session and retained annotation/discard record, with typed, cached deterministic and published workflow goals labeled separately; unavailable goals and unknown observation times are stated.

[C6](<https://linear.app/recce/issue/DRC-4025/c6-report-the-irreversible-things-that-happened>): Cargento reports destructive command shapes observed after a tool call while you were not watching, such as a force push; a report does not prove the effect succeeded.

## Waits on

Nothing. No open blocking relation remains.

## Read before building

* [DRC-4023](<https://linear.app/recce/issue/DRC-4023/c4-my-goals-across-sessions>): extend the shipped Intent log population and sources. Preserve annotation withdrawal/discard and retained readings; membership is independent of project navigation and annotation availability. Read existing bounded deterministic sidecars and published workflow titles, without automatic analysis. C1 owns the incoming Codex workflow attachment; a missing title is still no goal.
* [DRC-4025](<https://linear.app/recce/issue/DRC-4025>): read SECURITY.md, "Irreversible actions (hook-side destructive-shape matching)", before building. It permits hook-side pattern identifiers, tool names and timestamps only; the runtime input-reading rule is an allowlist, and the report and its off switch remain unshipped.
* [DRC-4020](<https://linear.app/recce/issue/DRC-4020>): read the [approved C1 triage contract](<https://github.com/spacedock-dev/cargento/blob/425a6bb9d37a9cfba00d4b87fd137ac249f1cfa8/drc-4020.md#acceptance-criteria>): exact workflow/state binding, current entity-file evidence, the measured Codex boot wrapper, first-observation/gap baselines and explicit Rearm are part of the scope. Existing browser notes stay unenforced.
````

The C1/C6 user-value paragraphs and build notes are retained verbatim. The project overview was read from the same fresh snapshot and requires no triage rewrite; its C7 cancellation and C1/C6 context remain. Re-fetch the milestone before implementation writes, preserve the current sibling paragraphs and notes, and apply only C4's population/source correction and the status-free Waits on sentence above. This draft grants no authority to rewrite sibling scope or reconciliation.

## Reproduction notes

The evidence scripts are disposable, declared artifacts at `/tmp/drc-4023-triage-state/source_probe.py` and `/tmp/drc-4023-triage-state/fixture_server.py`; the real payload snapshot is beside them. They import the repository's current modules and unchanged page, not external packages. To repeat after those scratch files are gone, use the fixture table in Mode 1 and AC-3 with the existing `NextIntentViewTest.FIXTURE` and `NextPageJsHarness` from `tests/test_next_intent.py`, `observer.write_sidecar/read_sidecar`, and `spacedock.read_workflow` with the `stages.states` fixture in `tests/test_spacedock.py`. No live account, model consent, or private transcript is needed for the controlled cases. The seven-session live population is a dated observation, not a fixture expectation.

Teardown verified: review tab closed; owned server PID 49223 on 18743 and fixture PID 78652 on 18744 stopped; both ports refused connections afterward. No code worktree was created or changed, no product file changed, and no Linear write occurred.

## Stage Report: triage

- DONE: Preserve fresh issue/milestone originals and check the remaining C4 population/source gap against the shipped Intent log and a Mode 1 walk.
  Verbatim 12:49:12Z snapshot retained above; three live comments read; main `4b2120d` browser walk showed seven board sessions omitted, plus off/error/loading and blank-project membership failures.
- DONE: Draft the smallest provenance-preserving union of board sessions and retained annotations, exercising deterministic cached goals, workflow goals, unknown/off/error states and discard behavior.
  Source experiment exercised real bounded sidecars/frontmatter with analyzer forbidden; Mode 1 retained departed/discard rows; AC-1–6 falsify omission, source substitution, invented freshness, restored withdrawals and wrong denominators.
- DONE: Record falsifiable offline/interactive acceptance criteria, separate runtime/oracle/docs costs with tolerance, and a committed three-item triage report ready for the gate.
  AC-1–7, six-runtime-file ceiling, separate behavioral/compelled-oracle/docs budgets with +25% line tolerances, and zero additional agents; drafts preserve C1/C6 wording and C7 cancellation.

### Summary

Recommend extending the existing Intent log with the board/annotation union and explicitly cached deterministic plus published workflow sources, preserving withdrawal and honest absence. The existing Intent suite passed all 46 tests in 0.498s; it would fail if late responses restored discarded words or retained rows/readings were lost, but does not yet prove the proposed union. All three checklist items are DONE (SKIPPED 0, FAILED 0); no Linear or product-code writes, both owned servers stopped, and the full suite was intentionally not run for this triage.

## Stage Report: triage (cycle 2)

- DONE: Preserve fresh issue/milestone originals and check the remaining C4 population/source gap against the shipped Intent log and a Mode 1 walk.
  Verbatim originals and three comments remain recorded; the main `4b2120d` walk demonstrated the population, off/error/loading and blank-project membership gaps.
- DONE: Draft the smallest provenance-preserving union of board sessions and retained annotations, exercising deterministic cached goals, workflow goals, unknown/off/error states and discard behavior.
  Source-admission evidence and scope are unchanged; the corrected milestone now says “Nothing. No open blocking relation remains,” and its note permits only C4's correction while preserving current sibling scope/reconciliation.
- DONE: Record falsifiable offline/interactive acceptance criteria, separate runtime/oracle/docs costs with tolerance, and a committed three-item triage report ready for the gate.
  AC-1–7, runtime/oracle/docs budgets, caps and tolerances remain unchanged; this latest report retains all three original dispatch signals.

### Summary

Removed duplicated live status from the draft so its implementation write will not immediately make it stale, and restored the three-item dispatch accounting in this latest report. Totals: DONE 3, SKIPPED 0, FAILED 0; no product, Linear, gate, acceptance-criteria or scope changes, and no new tests.

## Implementation progress — source boundary

Linear deep-dive completed through step 6 under the approved triage: feature, Medium/L, no blocking relations, Jared Scott assigned. The narrow approach and seven ACs remain unchanged; key files are observer/aggregate/sessions and the existing Intent/Observed assets. The implicit hazards are annotation revision invalidation, board membership independent of project navigation, and cached evidence never implying freshness.

Backend source and collection proofs are implemented; the first table-driven sidecar run failed on the missing projection and the first collection run failed on its missing field. Fifteen focused source/declaration/import checks passed; the later configuration-off collection check also passed. Mutating provenance admission admitted Model/Unknown words and failed the source test; removing the attachment failed the collection test; both files restored by byte copy. Frontend union/source/annotation-absence tests are intentionally red (5 versus 3 rows, missing source labels, and 2 versus 0 rows for off/loading/error), pending C1 integration. No frontend runtime edits, heavy suite, Mode 2 walk, or review yet.

## Stage Report: implementation

- DONE: Write and read back the approved C4 Linear issue and milestone-only changes before product work, preserving current sibling reconciliation.
  Approved issue/body/labels and In Progress plus milestone-only edits were written and read back before source work (state de23360; 2026-09-14T13:20:46.669Z). Fresh resumed reads preserved C1/C6 reconciliation; no old draft was replayed.
- DONE: Implement the seven approved population/source/withdrawal/counting criteria with red-first boundary proofs and a passing Mode 2 browser walk after C1 integration.
  PR [337](https://github.com/spacedock-dev/cargento/pull/337), candidate 09cd65de9917962d86bd9a7892ac963506679904, integrates C1/C6 base d5b52ab; runtime sources and all seven ACs remain within the approved contract.
  AC-1/2/4: assembled union fixtures and live browser measured 5=3 board+2 retained and actual API10=rendered10, including unprojected/no-goal rows, separately labeled typed/cached/workflow sources, and annotation off/loading/error plus Spacedock off. Filtering membership through project makes the union proof fail.
  AC-3/7: real bounded sidecars cover deterministic/model/unknown/coexisting/undated/stale/malformed/hostile/sentinel and invalid times; collection forbids analyzer/model/writer/transcript resolution, and recollection publishes cache replacement/removal. Raw model admission or removal of the attachment makes its proof fail.
  AC-5/6: live actual-store discard removed typed goal/output/reading while independent sources remained; retained departure/discard and actual-set count tests pass. Restoring late-response acceptance makes withdrawn-word proof fail. Reviewer migration/eviction probe keeps harness identities distinct and retained reading denominators honest.
  Mode 2 screenshots and API snapshot remain under the worktree's ignored docs/screenshots/drc-4023-*; both owned servers/tabs were closed and ports refused. Controlled Held-to project-context reads were intentionally unavailable, so no project-context producer claim is made.
- DONE: Complete the calibrated two-lens plus reproducing-arbiter review, canonical checks and sync-docs within separate scope tolerances, then publish the exact reviewed PR and durable three-item report.
  Exactly two independent lenses plus one reproducing arbiter completed; population found no blocker, source and arbiter reproduced one current-owned malformed-cache collection failure against the exact base. FO-authorized fix and canonical implementation/1 round precede same-arbiter PASS on 09cd65d; [rejected evidence](implementation-rejected-6cbcbb1.md) and [corrected recheck](implementation-correction-recheck-09cd65d.md) preserve attribution and probes.
  New real-file regression first failed RecursionError, then preserved both rows and the corrupt file with unavailable cache evidence. Arbiter's in-memory removal of only the catch makes that same test fail again. The scratch negative-control setup initially lacked postponed annotations; its corrected harness and original setup error are retained separately from candidate evidence.
  Final canonical dashboard3419/103.357s and scripts505/21.781s pass, coverage86.9%; ruff, full formatting, mypy158files, frontend/docs validators, version parity/unchanged manifests and installed Claude/AGY validators pass. Dashboard skips: Windows-only path semantics and git-lfs control installed no hook; scripts skip: live Terminal Apple Events not enabled.
  Initial canonical mypy3typing errors and dashboard3418/2staleC4gap failures/2skips were preserved, narrowly fixed under distinct FO disposition, then11 affected checks and3418 passed. Review correction produced the additional regression red; final3419 result above is the corrected tree. Logs remain together in docs/screenshots/drc-4023-checks.
  Actual vs separate upper estimates: runtime205LOC/5files vs420/max6 (48.8%); behavioral326/3 vs420 (77.6%); compelled26/7 including shared declaration vs60 (43.3%),9 distinct oracle files/max9; docs55/5 vs90/max6 (61.1%). Total612LOC/19files; sevenACs unchanged, no new runtime/test file/module/route/store/source power.
  sync-docs corrected README, shipped Intent paragraph, promise-map P2 backing/limits, reader-state and architecture; tone clean, C1/C6 headline clauses preserved, shared COMPATIBILITY marker untouched. Added docs:none; corrected:5; retired docs:none; unresolved branch docs:none. FO owns post-merge sync-project and the final main marker.
  CI is pending and belongs to the fresh review stage. Product commits are DCO signed and pushed; exact PR body retains Verification and this immutable state audit link after report commit. Worktree clean; no merge/status transition, release or sibling PR224 mutation by this producer.

### Summary

All three dispatched items are DONE; SKIPPED 0; FAILED 0. C4 now lists the complete board-plus-retained population with separate, qualified goal sources and preserves withdrawal; the sole reproduced review finding is fixed and independently falsified. Required test skips and initial failures remain explicit; FO owns the review gate, merge and final reconciliation.


## Stage Report: review

- DONE: Independently account for every approved acceptance criterion against the actual integrated candidate, required pre-PR review evidence, and recorded interactive proofs.
  Read the seven dated-triage ACs, integrated runtime/test/docs diff, immutable implementation/1 room, both independent lenses and retained-arbiter recheck; inspected all seven Mode 2 screenshots, fixture server and actual ten-identity API snapshot. Per-AC evidence follows.
- DONE: Inspect current-head CI and top-level plus Copilot inline comments; investigate any new finding read-only and route its four-field evidence and proposed disposition to FO.
  Exact-head check-runs API returns 12 completed successes, including all three native platforms and quality-gate; PR reviews and paginated inline comments both return empty. No new finding required disposition; the prior P2 has reproduced correction evidence.
- DONE: Report GO or NO-GO with exact PR/head/mergeability, actual scope and three checklist outcomes, retaining the worktree and reviewer handle for correction or safe final handoff.
  GO for PR337 at 09cd65de9917962d86bd9a7892ac963506679904, base d5b52abad006972a14df778573cd3abfe9d4f78d, MERGEABLE/CLEAN. Three DONE, zero SKIPPED/FAILED; code worktree is clean and retained, with this reviewer available for correction.

### Review depth and independent evidence

Required depth was completed once: population/retention lens, source/publication lens, and an arbiter reproducing the disputed finding. This fresh stage assessed their actual artifacts and the integrated candidate, with bounded scrutiny of the two-file correction; no additional worker, product edit, new automation, browser restart or test rerun.
[Rejected candidate and independent lenses](implementation-rejected-6cbcbb1.md), [immutable five-entry implementation/1 room](review/implementation/round-1/briefing.review.jsonl), and [corrected retained-arbiter recheck](implementation-correction-recheck-09cd65d.md) preserve attribution, base comparison, authorization and evidence. The synthetic 60,012-byte malformed cache broke ordinary candidate collection while the exact base published both rows. The narrow RecursionError catch now preserves both identities and the corrupt file; removing only that catch in memory makes the committed regression fail. The separate scratch compilation setup error is not candidate evidence. No unresolved or deferred review finding remains.

### Acceptance evidence

Evidence paths below are relative to the retained code worktree; images and logs remain ignored under docs/screenshots. Test results are the inspected existing executions, not new reviewer executions.
AC-1: docs/screenshots/drc-4023-live-data.json contains ten distinct harness/SID pairs, all visible once in drc-4023-live-union.png. drc-4023-integrated-union.png shows 5=3 board+2 retained, including empty and unprojected; the latter says present without project. test_every_board_session_joins_retained_words_once_even_without_a_project and the independent rename/depart/return/evict probe reject project-filtered membership, duplicate identities and false departure labels.
AC-2: test_all_goal_sources_coexist_with_their_own_labels_and_limits and integrated-union capture show typed goal/output, cached derivation and multiple workflow labels together; unknown observation time and untitled-workflow absence remain explicit. The fixture also carries model prose that does not render. Substituting latest assignment/model/body text or overwriting one source falsifies these oracles.
AC-3: CachedDeterministicGoalTest reads real sidecars across explicit/model/unknown/coexisting/undated/stale/malformed/missing/sentinel cases, hostile strings, cap and invalid/nonfinite timestamps. PublishedSessionFieldSetTest.test_collection_republishes_saved_goals_without_producing_observations forbids analyzer/model/writer/transcript resolver and observes replacement/removal on recollection. Candidate projection admits only scrubbed deterministic words, preserves valid saved time, and the UI says cached/currentness unchecked; the retained arbiter regression additionally defends malformed decoding without losing rows. Provenance admission and missing-attachment mutations are recorded failures.
AC-4: drc-4023-annotations-off.png, -loading.png and -error.png each retain three board rows and independent cached/workflow evidence while qualifying unavailable typed evidence; -spacedock-off.png suppresses workflow words and labels the source off. Matching async assembled-page tests reject whole-view early returns and stale disabled-source text; the empty row has honest source absences.
AC-5: drc-4023-discarded-independent-sources.png and the actual annotation-store fixture preserve the discard record while typed goal/output/reading disappear and cached/workflow labels remain. Existing late-response, confirmed-discard, unwritable-discard and return-during-discard tests remain in the green suite. Read nextIntentInvalidate/load generation guard and the late-response fixture: accepting an old generation restores withdraw-me and falsifies the test. The independent eviction probe removes retained words/readings without discarding another harness sharing the SID.
AC-6: test_reading_counts_and_eviction_rules_name_only_retained_annotations independently asserts four rows, two typed records, one discard and one reading among two eligible annotations, plus a departure. Captures change typed/discard totals from 2/1 to 1/2 after discard while list total stays five. Independent population probe holds a 1-of-1 reading denominator through board-only additions and migration. Counting a board-only/default or discard row as eligible, or assigning eviction order to the board group, falsifies these assertions.
AC-7: C1/C6 are actually integrated at base d5b52ab (merge d34c57f), and C4 consumes existing session.spacedock.workflows only. Inspected test_spacedock title-only/bounded-goal/session-workflows oracles, constructor/every-harness equality and declared aggregate-to-observer import. All three byte-pin owners are updated: test_next_page.py and test_next_flag.py length907975, and those plus test_focus.py digest a7ff3c5130b4b5568b44b055bcd424ff48cf834e980e00c283e5bbb9fca91c35. Integrated suite and exact-head CI exercise these actual assembled assets; the subsequent catch correction changes no web bytes. README, shipped Intent paragraph, promise-map, reader-state and architecture describe the final population/source limits; no new discovery, model power, store or threshold appears.

### Exact candidate, checks and scope

[PR337](https://github.com/spacedock-dev/cargento/pull/337): HEAD09cd65de9917962d86bd9a7892ac963506679904; base d5b52abad006972a14df778573cd3abfe9d4f78d; MERGEABLE, mergeStateStatus CLEAN. Exact-commit check-runs API was inspected after Windows completed: 12/12 success, including [quality-gate and native platform suite](https://github.com/spacedock-dev/cargento/actions/runs/34919056400), [validate](https://github.com/spacedock-dev/cargento/actions/runs/34919056390), [version-guard](https://github.com/spacedock-dev/cargento/actions/runs/34919056402), and [latest-client-smoke](https://github.com/spacedock-dev/cargento/actions/runs/34919056434). No top-level reviewer report, requested reviewer or inline Copilot comment existed at the final read; absence is not a Copilot approval.
Inspected local logs preserve original dashboard3418/two stale-gap failures and mypy errors beside the corrected results. Final corrected artifacts are dashboard-corrected.log:3419/103.357s/2skips; scripts-corrected.log:505/21.781s/1skip; coverage-corrected.log:86.9%. The older dashboard-final.log is3418 before the decoder regression, not the final corrected run. Current CI coverage reports86.7% and passes its threshold; it is not the local86.9% result.
Native CI passes are observed directly, not inferred from local skips. Local dashboard skips cover Windows-only semantics and the git-lfs control with no installed hook; scripts skip the opt-in live Terminal Apple Events case. Controlled Held-to project-context reads were unavailable and provide no producer proof; recorded interactive proofs are accepted as dispatched, not claimed as a fresh reviewer browser drive. Corrupt-cache production prevalence and currentness of saved goals remain unverified by design.
Actual diff is19files/612changedLOC (514added/98removed): runtime205/5files; behavioral326/3; compelled26/7 including shared declaration, nine distinct oracle files; docs55/5. All remain within separate triage ceilings and file limits; seven ACs unchanged. Correction after pre-PR review is only observer.py and test_sessions.py, independently rechecked on this exact head.

### Summary

GO: complete board-plus-retained membership, qualified independent sources and preserved withdrawal are supported by the integrated candidate and owned falsifiable evidence. No new material finding, new correction round, candidate mutation or suite rerun was introduced. Retain the clean code worktree and ignored evidence until FO has preserved what cleanup needs; FO owns merge, worktree removal before branch deletion, Linear reconciliation and terminal archive. No sibling or PR224 was touched.
