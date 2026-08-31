---
id: future-ui-command-surface
title: Future UI command surface
status: crucible
source: Captain commission on 2026-08-31 and the 2026-08-27 project-cockpit debrief
started: 2026-08-31T01:41:26Z
completed:
verdict:
score: 1.0
worktree:
issue:
pr:
gates:
    version: 1
    records:
        - id: gate:future-ui-command-surface:framing
          stage: framing
          attempts:
            - id: gate-attempt:future-ui-command-surface-framing-1
              briefing:
                id: briefing:future-ui-command-surface:framing:attempt-1:revision-1
                digest: sha256:b54e1f3645d96a20d0552028105924257bcea0210a18525175fb534fe5e25818
                room-ref: ./review/framing/briefing-1
              resolution:
                type: Resolution
                id: resolution:spacedock:future-ui-command-surface:framing:1
                briefing: briefing:future-ui-command-surface:framing:attempt-1:revision-1
                by: person:captain
                at: "2026-08-31T01:40:53.077749Z"
                decision: approve
                reason: Captain approved the bold, falsifiable command-surface direction and authorized three-harness reconnaissance.
              application:
                target-stage: reconnaissance
                state: consumed
        - id: gate:future-ui-command-surface:crucible
          stage: crucible
          attempts:
            - id: gate-attempt:future-ui-command-surface-crucible-1
              briefing:
                id: briefing:future-ui-command-surface:crucible:attempt-1:revision-1
                digest: sha256:ecc7de4a47b63f39adfd78dda3829d3871b08fc42cfdbb7f6040263c2907966a
                room-ref: ./review/crucible/briefing-1
              withdrawal:
                by: agent:first-officer
                at: "2026-08-31T03:19:13.882442Z"
                reason: Correction cycle 1 produced checkpoint 578d77a and a fresh ACCEPT re-review; the open attempt bound to rejected snapshot 05332a4 is stale.
            - id: gate-attempt:future-ui-command-surface-crucible-2
              briefing:
                id: briefing:future-ui-command-surface:crucible:attempt-2:revision-1
                digest: sha256:0ea5f7614ac270ec7de85c6b0cac7678a57dc1e188b1fc4e0bd6fc37b0a79698
                room-ref: ./review/crucible/briefing-2
              resolution:
                type: Resolution
                id: resolution:spacedock:future-ui-command-surface:crucible:2
                briefing: briefing:future-ui-command-surface:crucible:attempt-2:revision-1
                by: person:captain
                at: "2026-08-31T03:30:27.854026Z"
                decision: revise
                reason: 'Captain accepts the project-first direction and requires another iteration: omit workflow absence UI when no Spacedock evidence exists; replace opaque Refresh stalled with a clear live-update state, impact, and recovery; show Captain state only for Spacedock and only when it carries an evidence-backed request; progressively disclose Assignment and Next instead of rendering unexplained empty cards, while keeping current activity as the session lede.'
review-round:
    id: round:future-ui-command-surface:crucible:3
    stage: crucible
    cycle: 3
    briefing:
        id: briefing:future-ui-command-surface:crucible:round-3
        digest: sha256:ac5870356eedc67fecbc0215fa1619f7f88e2eb6ae63a1a712814cbc99156623
        room-ref: ./review/crucible/round-3
---

## Design bet

A project-first command surface can make a mixed fleet of Codex, Claude Code, and AGY sessions understandable at a glance by leading with the situation and required response, while a session drill-down can expose top-line purpose and live activity without confusing provenance with priority.

The experiment may replace the current information architecture, navigation, and visual hierarchy. Preserving the existing Next UI layout is not a success condition.

## Baseline and command risk

The 2026-08-27 debrief converged on Assignment, Execution, and Command for a project cockpit, but the current integrated Next UI must be re-observed across all three target harnesses. The primary risks are that project-wide state becomes an inventory, session detail buries the current action, unavailable evidence is rendered as certainty, or provenance receives more visual authority than the fact it qualifies.

Reconnaissance must establish the current baseline with the live dashboard rather than inherit the debrief's conclusion as fact.

## Method

Launch observed Codex, Claude Code, and AGY sessions that perform distinguishable work. Inspect the live project overview and each session drill-down in Chrome. Capture screenshots and source-bound state, then give fresh reviewers separate antagonistic lenses. Implement material findings sequentially on `feat/future-ui`, checkpoint the exact bytes, and repeat from the accepted checkpoint until the crucible gate recommends reframe, revise, or accept.

## Acceptance criteria

**AC-1 — The project overview communicates the overall situation and the most important required response before session inventory or evidence detail.**
Verified by: a fresh-reviewer five-second Chrome scan over the live three-harness project state followed by questions asking what is happening, what needs attention first, and who owns that response. The criterion fails if the reviewer must open a session or Evidence to answer, chooses a lower-risk item because it has greater visual weight, or cannot distinguish captain action from FO work.

**AC-2 — A session drill-down exposes its assignment, current activity, execution state, next action, and captain responsibility without presenting missing data as fact.**
Verified by: live drill-downs for the observed Codex, Claude Code, and AGY sessions plus adversarial states where assignment, child handoff, or authority evidence is absent. The criterion fails if any available top-line fact requires opening Evidence, an absent fact receives invented content, or a missing-source problem is assigned to the captain without an exact request or proven blocking choice.

**AC-3 — Project scope, selected-session scope, and evidence provenance remain distinct while users move between overview and drill-down.**
Verified by: navigating project and session permalinks across two projects and three harnesses while checking headings, selected scope, and API identifiers. The criterion fails if a session filter silently changes ownership of a project fact, browser-local context leaks to another scope, or an unbound result is displayed as the current assignment's result.

**AC-4 — Material semantic and hierarchy failures are caught before a checkpoint is accepted.**
Verified by: each iteration record links the pre-change screenshot, fresh antagonistic finding, reproduced evidence, disposition, implemented checkpoint, focused checks, and post-change screenshot. The criterion fails when a product correction lacks a subsequent fresh review or when a material finding is accepted or dismissed without reproduction.

**AC-5 — The candidate remains an isolated future direction.**
Verified by: `git branch --show-current` reports `feat/future-ui` for durable workflow checkpoints and the recorded starting `main` commit remains outside workflow-authored product mutations. The criterion fails if any workflow-generated UI commit or PR targets `main`.

## Iteration record

No product checkpoint yet. Framing and live reconnaissance establish round 1.

### Feedback Cycles

No correction cycles yet.

## Known limits

Some harness records may omit assignments, child handoffs, or exact authority. The UI must name those limits and their bounded owner rather than reconstruct absent content. Browser-local human context does not transfer across browsers. Console origins may be read-only.

## Out of scope

This experiment does not ship to `main`, promise write access to session consoles, fabricate missing harness data, or turn every evidence source into a primary dashboard region.

## Reconnaissance evidence

The live server ran the `feat/future-ui` bytes at `b29c34b7c28d01f66dcc67baebf7a663ab279ed7` on `http://127.0.0.1:4553/?next=true`. The overview capture observed 3 projects, 10 sessions, and three simultaneously running marked sessions; the later API snapshot at `2026-08-31T01:50:31Z` showed the two one-turn sessions idle and the Codex first officer still working.

### Observed sessions and source limits

| Harness | Exact identity | Distinguishable observed work | Live API/UI source limit |
|---|---|---|---|
| Codex | `01a0555c-2da3-7c23-bd26-4ea2e275d18a` (`01a0555c` display key) | Active first-officer turn after the captain's `I approve, continue`, with subagent `Harvey` | API exposed the last prompt, one bounded `agent` narration, state, and subagent, but `tasks: []` and `spacedock: null`; no durable assignment, next action, or captain responsibility was available. Codex prompt/instruction fields are active-window backward reads (`collectors/codex.py:188-196, 242-250`) capped at 80/140 characters. |
| Claude Code | `8b3e5aa1-4ed6-4ac9-91f0-7d148c3ea631` (`8b3e5aa1` API identity) | `CLAUDE-RECON-20260831`: read `README.md` and report what Cargento is, without edits; CLI completed successfully | API contained the full bounded prompt as `instruction.label=asked`, but the collector groups and publishes the first eight UUID characters. The 80-character title/140-character instruction policy is explicit (`collectors/claude.py:669-689`, `records.py:1012-1017`). |
| AGY | `49fad07a-21aa-4b2e-9c14-ecfcbcf67ab8` (`49fad07a` display key) | `AGY-RECON-20260831`: read `README.md` and report what Cargento is, without edits; CLI completed successfully | API found workspace, identity, state, and activity, but returned `title: null`, `last_prompt: ""`, and no instruction. The collector reads bounded public-log head/tail because conversation bodies are protobuf, and gets prompts only from `HandleUserInput` before `Forwarding user message` (`collectors/antigravity.py:72-95, 129-169`); that marker was absent in this session's live log. |

### Captures

- [Project overview with all three harnesses running](reconnaissance/overview-three-harnesses.jpg) — 1844×1067; project inventory leads, while Progress is blank and Estimate/Delegation read `no estimate`, `no confidence`, and `not measured`.
- [Project drill-down](reconnaissance/project-recce-cargento.jpg) — says `This project declares no workflow`, then leads with `GOING ON`; the workstream records only two `became idle` events labelled `C` and `A`.
- [Codex session](reconnaissance/session-codex-01a0555c.jpg) — `I approve, continue`, one `agent` narration, Codex identity, and `Harvey`.
- [Claude Code session](reconnaissance/session-claude-8b3e5aa1.jpg) — truncated marked prompt, identity/state, and token total; no separate assignment line.
- [AGY session](reconnaissance/session-agy-49fad07a.jpg) — project label fallback, identity, and idle state; no prompt or activity description.

### Fact versus inference inventory

| Surface | Source-backed fact | UI inference or unsupported conclusion |
|---|---|---|
| Overview | API reported three projects, ten in-window sessions, three working states, and one Codex subagent at capture time. | Row order and large empty metric columns imply a project-control summary, but they do not establish overall situation, response priority, ownership, or captain action. |
| Project | Seven payload sessions shared the `recce/cargento` label; the active Codex session had a last prompt, current narration, and subagent. | `This project declares no workflow` is not supported. This entity and workflow exist, but every selected session had `spacedock: null`; the renderer maps absence to a declaration (`next-project.js:106-114`). |
| Codex | Last prompt was `I approve, continue`; the bounded agent line and `Harvey` were present in `/api/data`. | Treating either transient line as the durable assignment or next action would be inference. The drill-down does not make the absence explicit. |
| Claude Code | API held the marked prompt in both `last_prompt` and `instruction`, and the one-turn CLI result proved completion. | The UI hides the available instruction because an 80-character ellipsized title is treated as echoing its 140-character source (`next-boot.js:92-111`); the remaining heading is not the full assignment. |
| AGY | CLI output and public log prove the exact session and marked task; API proves identity, project, and idle/working lifecycle. | The heading `recce/cargento` is only the renderer's fallback from missing title/prompt to project (`next-session.js:39-44`), not the session assignment. Empty prompt data is not proof that no assignment existed. |
| Workstream | Two harness state transitions were observed after the marked turns ended. | `C`/`A` plus `became idle` is not the semantic timeline requested in prior source context and cannot explain what completed or what response follows. |

Prior source context remains a hypothesis, not live proof: clkao wanted the debrief's semantic timeline rendered, described the sidecar LLM as provisional because user configuration burden was unclear, confirmed the branch was committed, and left additional dislikes unenumerated.

### Ranked findings

1. **Critical command risk — mixed source gap and UI overclaim:** the live commissioned workflow is rendered as `This project declares no workflow`. Codex does not publish Spacedock attribution here, but the renderer converts missing data into certainty rather than naming the limit.
2. **High comprehension risk — UI hierarchy failure:** the overview leads with inventory and empty progress/estimate/delegation columns, not situation, required response, or owner. Available running/idle facts are secondary and no missing captain-action source is identified.
3. **High comprehension risk — pure UI failure:** Claude's full bounded assignment is in `/api/data`, but the title-echo suppression removes it and leaves only the shorter ellipsized heading.
4. **High command risk — mixed AGY source gap and fallback failure:** the observed AGY prompt is absent because the current public log lacks the collector's prompt marker; the UI silently substitutes the project name instead of labelling assignment unavailable.
5. **High command risk — source gap exposed without a contract:** Codex shows a transient approval prompt and process narration but no durable assignment, next action, or captain responsibility. The page neither supplies those facts nor says which source/owner must provide them.
6. **Medium comprehension risk — UI semantics failure:** the workstream's `C`/`A became idle` events identify neither the completed work nor its consequence, so it is an event list rather than the requested semantic timeline.

## Stage Report: reconnaissance

- DONE: Produce one observed, distinguishable live session from Codex, Claude Code, and AGY with exact session identities and source limits.
  The marked real sessions above were exercised through each native CLI and matched to live `/api/data`; changing any UUID, marker, or collector boundary would break that match.
- DONE: Capture the live project overview and each session drill-down, separating source-backed facts from UI inference.
  Five 1844×1067 browser captures and the fact-versus-inference table cover overview, project, and all three exact sessions; a missing route or payload mismatch would render an outside-payload/absent capture instead.
- DONE: Rank findings by comprehension or command risk and distinguish UI failures from unavailable underlying data.
  Six reproduced findings are ordered Critical/High/Medium and each names UI, source, or mixed ownership; the classification would fail if the cited API field contradicted it.

### Summary

Three real, marked harness sessions established that the current Next UI cannot yet answer assignment, next action, or captain responsibility consistently. The strongest failures are a false no-workflow assertion, an overview led by empty inventory metrics, suppression of Claude data the API already has, and silent fallbacks where AGY/Codex sources are absent.

## Prototyping iteration 1 — command truth before inventory

The captain approved approach A: a project command brief and four-part session frame, with the explicit bounded captain state `CAPTAIN — No request observed` plus `Current payload only`. The design and implementation plan were checkpointed at `a986c6f`; the exact candidate bytes were checkpointed and pushed on `feat/future-ui` at `05332a4` before any after-capture.

### Before evidence

- [Overview inventory baseline](reconnaissance/overview-three-harnesses.jpg)
- [False project workflow conclusion](reconnaissance/project-recce-cargento.jpg)
- [Codex transcript-led baseline](reconnaissance/session-codex-01a0555c.jpg)
- [Claude clipped-assignment baseline](reconnaissance/session-claude-8b3e5aa1.jpg)
- [AGY project-name fallback baseline](reconnaissance/session-agy-49fad07a.jpg)

### Antagonistic findings and dispositions

| Reproduced finding | Evidence-bound disposition in `05332a4` |
|---|---|
| Missing `spacedock` records became the certain claim `This project declares no workflow`. | Replaced with `Workflow source unavailable for these sessions`; the positive first-officer and ensign empty states remain source-gated. |
| Empty Progress/Estimate/Delegation inventory displaced situation, response, and owner on the overview. | Replaced the five-column table with a captain lede and priority-sorted project briefs led by `SITUATION` and `RESPONSE`; asks outrank executing and idle projects. |
| Claude's full published `asked` instruction was suppressed when its shorter ellipsized title echoed it. | The session `ASSIGNMENT` frame renders the full published instruction independently of title deduplication and labels `Claude transcript` as its source. |
| AGY's absent prompt silently became the project name. | The identity heading may still fall back for navigation, but the command frame states `Assignment unavailable` and `Not published`, each owned by `AGY CLI log`. |
| Codex exposed transient approval/narration without a durable assignment, next action, or captain contract. | The frame labels the narration as execution context, states assignment/next are unavailable from `Codex transcript`, and bounds captain state to `No request observed · Current payload only`. |
| `C`/`A became idle` looked like a semantic timeline without explaining work or consequence. | Renamed the region `OBSERVED STATE CHANGES`, uses full harness registry labels, and states only tab-local observed transitions. It does not claim semantic or causal coverage. |

### Candidate byte proof and focused checks

- Branch/checkpoint: `feat/future-ui` at pushed commit `05332a4`.
- Assembled `?next=true` response: 240,258 bytes; SHA-256 `f3b472ceac42279b52556b8d170630c1eea13e5b3861a990a14c0a3f8b9974be`.
- Red proof: the new overview/session/project/workstream assertions failed against the pre-candidate renderers; the keyboard activation assertion separately failed before focus/Enter support was added.
- Green proof: 81 focused behavior and byte-contract tests passed across `test_next_projects`, `test_next_session`, `test_next_project`, `test_next_workstream`, and `test_next_page`.
- Static proof: changed Python tests passed Ruff check and format; `scripts/lint_embedded.py`, `scripts/validate_plugins.py`, and `git diff --check` passed.

### After evidence from the committed candidate

- [Overview command brief](prototyping/overview-command-brief.jpg) — `CAPTAIN — No request observed` is immediately qualified by `Current payload only`; project briefs answer situation and response without empty estimate/delegation columns. SHA-256 `b28008226414bf9f2c85b2162ce7be0931d06911e8708ed275c96f0e7e3834a3`.
- [Project source boundary](prototyping/project-recce-cargento.jpg) — says `Workflow source unavailable for these sessions` and `OBSERVED STATE CHANGES`. SHA-256 `b3a809b2b317645462bbaf5c783b3d908197d37cec63f3a50ae932a4d4851f0c`.
- [Codex command frame, same identity `01a0555c-2da3-7c23-bd26-4ea2e275d18a`](prototyping/session-codex-01a0555c.jpg) — assignment and next facts name `Codex transcript` as their unavailable owner; execution retains the bounded agent narration. SHA-256 `82e5faa89c99626353a1ba24e0e91918d872db9c2d00ca40d50290bfabf8fbc9`.
- [Claude command frame, same API identity `8b3e5aa1`](prototyping/session-claude-8b3e5aa1.jpg) — the full marked assignment renders despite the clipped title. SHA-256 `ba052fc64fcd6d3959e15798ac092406f83cfb1d3b6e4bef3798e6ee3b7d5fe1`.
- [AGY command frame, same identity `49fad07a-21aa-4b2e-9c14-ecfcbcf67ab8`](prototyping/session-agy-49fad07a.jpg) — missing assignment and next action are explicitly owned by `AGY CLI log`. SHA-256 `984822d31b7366f2a100f6191852a06cc38a0d5d63e03e97b7fba11a79dd4d42`.

## Stage Report: prototyping

- DONE: Implement a coherent, lede-first overview and session drill-down that materially resolves the six reproduced reconnaissance risks instead of adding more inventory regions.
  Commit `05332a4` replaces the overview inventory with one command brief, adds one four-part session frame, bounds the project/workstream claims, and the five tied captures reproduce each correction.
- DONE: Keep every semantic claim source-bound: remove the false workflow certainty, expose available Claude assignment data, and label unavailable Codex or AGY command facts with their bounded owner.
  The same-identity after-captures show workflow uncertainty, Claude's complete published assignment, and exact `Codex transcript`/`AGY CLI log` ownership without invented next or captain actions.
- DONE: Commit exact candidate bytes on feat/future-ui, recompute frontend byte pins, run focused tests, and capture tied before/after evidence for the next fresh crucible review.
  Pushed `05332a4` pins the 240,258-byte assembled response at SHA-256 `f3b472ceac42279b52556b8d170630c1eea13e5b3861a990a14c0a3f8b9974be`; 81 focused tests and both static validators passed before the five Chrome captures.

### Summary

The first prototype now puts captain state and project situation ahead of inventory, gives every session an assignment/execution/next/captain frame, and names source gaps without turning them into instructions for the captain. The candidate is ready for a fresh crucible review; no crucible judgment is recorded here.

## Crucible review — recommendation: revise

**REVISE.** The command-surface direction survives: the live overview makes the one executing session and bounded captain state visible, and each exact harness drill-down now separates assignment, execution, next action, and captain responsibility without inventing unavailable facts. Acceptance is blocked by two reproduced corrections within this interaction model, so the evidence supports neither a reframe nor acceptance yet.

### Acceptance and cross-harness disposition

| Question | Live answer at `05332a4` | Disposition |
|---|---|---|
| Overall situation | Overview says `1 session executing`; its captain lede says `No request observed` and immediately qualifies that with `Current payload only`. | AC-1 passes. The command brief leads before the three project rows and no lower-risk row has greater semantic weight. |
| Assignment | Claude renders the complete published `asked` instruction. Codex and AGY render `Assignment unavailable` and name `Codex transcript` or `AGY CLI log`. | AC-2 passes this fact; no project-name or transient narration is promoted to assignment. |
| Execution and current activity | All three frames render state/detail; Codex alone adds its published `agent` narration and live subagent as bounded context. | AC-2 passes the source boundary, subject to the elapsed-label correction below. |
| Next action | All three live records truthfully say `Not published` with their source owner. The ask and in-progress-task fixtures select the exact ask first and the first published in-progress task second. | AC-2 passes; missing data is not assigned to the captain. |
| Captain responsibility | All three say `No request observed · Current payload only`; the exact-ask fixture instead says `Respond` with the escaped question. | AC-1/2 pass; the current payload has `asks: []`. |
| Scope and provenance | Overview, `recce/cargento`, and all three session permalinks retain distinct breadcrumbs and exact API identities; the same-label caveat remains visible. | AC-3 and AC-5 pass. Branch is `feat/future-ui` at `05332a4`; no product mutation reached `main`. |

All six reconnaissance findings remain closed in the live candidate: workflow absence is uncertain rather than declarative; the overview is lede-first; Claude assignment suppression is gone; AGY project fallback no longer stands in for assignment; Codex gaps name their source owner; and state changes use full harness labels with tab-local scope.

### Material findings and required correction

1. **Accepted — accessibility semantics block acceptance.** The overview has zero headings, the two `role=tab` controls have no `aria-controls` or `tabpanel`, every route keeps the generic document title `Cargento`, and the project route nests an unlabeled `<main>` inside `#app`'s `<main>` (`next-chrome.js:48-60`, `index.html:6,11`, `next-project.js:167-174`). This impairs structural navigation and route identification even though visible hierarchy is strong. Revise with a route-specific title, a real overview heading, a correctly related tab/tabpanel pattern, and one main landmark.
2. **Accepted — working elapsed time needs a truthful noun.** The Codex header rendered `started 5m ago` while the API distinguished the much older `started_at` from `turn.elapsed_h`; `next-session.js:113-116` deliberately reads the turn field but omits `turn` from the label. Revise to `turn started … ago` (or equivalent) so the current-activity cue cannot be read as session start.

Keyboard Enter navigation and a visible focus ring passed on the overview brief; the 320 px overview and session frames reflowed with `scrollWidth == clientWidth`; sampled dark-theme text contrast ranged from 6.49:1 to 14.88:1; reduced-motion behavior remains pinned by the focused asset test. Those results dispose of keyboard reachability, reflow, core contrast, and motion as material blockers in this round, but do not cancel the semantic failures above.

### Current evidence and checks

- [Overview command brief](crucible/overview-live.jpg), [project drill-down](crucible/project-live.jpg), [Codex](crucible/session-codex-live.jpg), [Claude](crucible/session-claude-live.jpg), and [AGY](crucible/session-agy-live.jpg) are fresh 1844×1067 captures from server PID 74085 and exact candidate `05332a4`.
- [Keyboard focus](crucible/overview-keyboard-focus.jpg) shows the live focus indicator; [320 px reflow](crucible/overview-320px.jpg) records the narrow hierarchy without horizontal overflow.
- `/api/data` at `2026-08-31T02:35:14Z` reproduced the exact three identities, one working Codex session, no asks, full Claude `asked` instruction, and unavailable Codex/AGY assignments; renderer source and fixtures supplied the adversarial ask, task, missing-source, scope, and elapsed cases.
- The assembled candidate remains 240,258 bytes at SHA-256 `f3b472ceac42279b52556b8d170630c1eea13e5b3861a990a14c0a3f8b9974be`. All 81 focused behavior/byte tests, `scripts/lint_embedded.py`, `scripts/validate_plugins.py`, and `git diff --check` passed; the focused tests would fail if ask priority, full Claude assignment, source owners, keyboard routing, bounded workflow/state labels, responsive byte pins, or reduced motion regressed.

Captain gate: choose **revise** and return these two accepted findings to prototyping. A fresh crucible review after both corrections is required by AC-4 before acceptance.

## Stage Report: crucible

- DONE: Independently test the committed live candidate with fresh Codex, Claude Code, and AGY evidence across visual hierarchy, information architecture, command truth, session drill-down, accessibility, and adversarial states.
  Commit `05332a4`, current API data, seven fresh browser captures, source inspection, semantic/keyboard/reflow checks, and 81 focused fixture tests exercise each requested lens; changing any cited route, identity, semantic count, source owner, or fixture outcome breaks the evidence.
- DONE: Reproduce and disposition every material finding against the acceptance criteria, especially whether overview and drill-down expose overall situation, assignment, execution, current activity, next action, and captain responsibility without invented certainty.
  The acceptance table closes all six prior risks and holds AC-2/AC-4 on two reproduced defects: missing route semantics and an unqualified turn-elapsed label.
- DONE: Recommend exactly one route—revise, reframe, or accept—with source-bound evidence, focused check results, and current screenshots sufficient for the captain gate.
  REVISE is the sole recommendation; the seven linked captures, API timestamp, source lines, byte hash, and falsifiable check summary bind the gate.

### Summary

The project-first command model is substantially stronger and remains honest across Codex, Claude Code, and AGY, so a reframe is not warranted. Two material but bounded corrections block acceptance: repair route/landmark/tab semantics and qualify working elapsed time as turn time, then run a fresh crucible review.

## Prototyping correction cycle 2

Halley's two accepted findings were corrected without changing the command-surface model. The exact corrected bytes are pushed on `feat/future-ui` at `578d77a`: 241,166 assembled bytes, SHA-256 `9330654d53cccdb5ce52f2baa72d9963bd896a39660f272bcb782c77f54fb239`.

### Correction evidence

- [Overview route semantics](prototyping-cycle-2/overview-route-semantics.jpg) — live title `Cargento — Overview`, visible `Cargento command overview` h1, one main landmark, and reciprocal `next-tab-*`/`next-panel-*` `aria-controls`/`aria-labelledby` pairs. SHA-256 `dfc0f7a4468b8aa2b49d597abdbe04fae2d2b3d3ff1dcfcb08174aba56240ef5`.
- [Project single-main route](prototyping-cycle-2/project-single-main.jpg) — live title `recce/cargento — Cargento`, project h1, and one main landmark after replacing the nested project main element. SHA-256 `11e09ec1d7c520222f1a3841325e4e3cf9ee007920846856422736dbc52be5a5`.
- [Codex turn label](prototyping-cycle-2/session-codex-turn-label.jpg) — same identity `01a0555c-2da3-7c23-bd26-4ea2e275d18a`, route title `I approve, continue — recce/cargento — Cargento`, and `turn started 58s ago` in the capture. SHA-256 `2dcfc1b9be890c949f9fe85b062d2ff50e8824674e4004a472564c7a954b41c3`.

The route-semantic, single-main, and turn-noun assertions first failed against rejected snapshot `05332a4`, then passed after the bounded correction. The final focused batch passed 73 tests across `test_next_chrome`, `test_next_project`, `test_next_session`, and `test_next_page`; Ruff check/format, `scripts/lint_embedded.py`, `scripts/validate_plugins.py`, and `git diff --check` also passed.

## Stage Report: prototyping (cycle 2)

- DONE: Fix the accepted route/title/heading/tab/landmark semantic finding with failing-first behavior tests and exactly one main landmark.
  `test_routes_set_distinct_titles_and_overview_exposes_related_tabs` fails if any route title or reciprocal tab/panel relation disappears; the project renderer test fails if it contributes a nested main, and live Chrome measured one main on overview and project.
- DONE: Fix the accepted turn-elapsed label so current activity cannot be mistaken for session start, with a failing-first behavior test.
  Minute and multi-hour working fixtures now require `turn started` while the idle fixture independently requires `session started`; reverting the noun fails all three assertions, and the same Codex identity reproduces it live.
- DONE: Commit only these corrections on feat/future-ui, update byte pins, run focused checks and validators, and append source-bound correction evidence plus a complete prototyping report.
  Pushed `578d77a` changes only the two accepted semantic corrections and their tests/pins; the 241,166-byte oracle, 73 focused tests, validators, and three committed-byte Chrome captures bind this report.

### Summary

Cycle 2 repairs route identification, structural navigation, landmark uniqueness, and the misleading turn-time noun without changing the approved command hierarchy. The exact corrected checkpoint and live evidence are ready for Halley's required fresh re-review.

## Crucible review cycle 2 — recommendation: accept

**ACCEPT.** Corrected checkpoint `578d77a` closes both round-1 material findings in live Chrome and independent fixtures without regressing the project-first command model. No new material command, comprehension, scope, or accessibility risk survived reproduction, so another correction cycle would optimize beyond the experiment's lede-first stop criterion.

### Round-1 correction proof

| Rejected finding | Fresh proof at `578d77a` | Disposition |
|---|---|---|
| Route/title/heading/tab/landmark semantics | Overview title is `Cargento — Overview`, its visible h1 is `Cargento command overview`, reciprocal tab/panel IDs and selection switch together, and overview/project/session each expose exactly one main landmark. Project and all three session routes have distinct titles and h1 context. | Closed. The live DOM counts, keyboard activation, source diff, and `test_routes_set_distinct_titles_and_overview_exposes_related_tabs` would fail if the correction disappeared. |
| Working elapsed time lacked its source noun | The same Codex identity renders `turn started 11m ago`; its API independently publishes `turn.elapsed_h`, while the idle Claude fixture and route continue to say `session started`. | Closed. Live text and minute/multi-hour/idle fixtures distinguish turn time from session time. |

### Full acceptance cross-check

| Criterion | Current evidence | Verdict |
|---|---|---|
| AC-1: overall situation and response lead | The fresh overview says `1 session executing` and `CAPTAIN — No request observed · Current payload only` before the three project rows. | Pass. |
| AC-2: assignment, execution, next, captain | Claude shows the complete published assignment; Codex and AGY explicitly name unavailable assignment/next owners; all three show execution state and bounded captain responsibility. | Pass. |
| AC-3: scope and provenance | Distinct overview, project, Codex, Claude, and AGY permalinks retain exact breadcrumbs, API identities, route titles, and the same-label caveat. | Pass. |
| AC-4: corrections receive fresh review | This cycle independently reproduces both rejected findings as fixed after correction commit `578d77a`, then re-runs live, fixture, semantic, keyboard, and reflow checks. | Pass. |
| AC-5: isolated direction | Branch is `feat/future-ui` at pushed `578d77a`; the assembled candidate is 241,166 bytes at SHA-256 `9330654d53cccdb5ce52f2baa72d9963bd896a39660f272bcb782c77f54fb239`. | Pass. |

One non-material accessibility refinement remains: the tab list has no group label, both tabs remain sequential Tab stops, and Left Arrow does not move focus. The [WAI-ARIA tabs pattern](https://www.w3.org/WAI/ARIA/apg/patterns/tabs/) describes a labelled, roving tab list with Left/Right Arrow focus movement. This does not block this gate because both controls are visibly focusable, Tab reaches each, Enter switches `aria-selected` and the correct panel, narrow reflow remains intact, and the observation changes neither command truth nor access to either view; retain it as follow-up rather than restarting the command-surface experiment. The repetitive AGY document title is likewise descriptive and route-distinct, so it is polish rather than a material scope failure.

### Current evidence and checks

- [Overview](crucible-cycle-2/overview-live.jpg), [project](crucible-cycle-2/project-live.jpg), [Codex](crucible-cycle-2/session-codex-live.jpg), [Claude](crucible-cycle-2/session-claude-live.jpg), and [AGY](crucible-cycle-2/session-agy-live.jpg) are fresh 1844×1067 captures from exact checkpoint `578d77a`.
- [Tab keyboard probe](crucible-cycle-2/overview-tab-keyboard-gap.jpg) preserves the non-material follow-up evidence; [320 px overview](crucible-cycle-2/overview-320px.jpg) shows the new h1 and command hierarchy with `scrollWidth == clientWidth == 320`.
- `/api/data` at `2026-08-31T03:07:29Z` contained one working Codex session, no asks, the exact three prior identities, full Claude `asked` content, and unavailable Codex/AGY command facts. The live renderer matched each source boundary.
- All 94 focused tests across `test_next_chrome`, `test_next_projects`, `test_next_session`, `test_next_project`, `test_next_workstream`, and `test_next_page` passed, as did `scripts/lint_embedded.py`, `scripts/validate_plugins.py`, and `git diff --check`. Those tests fail on route/title/relation drift, source-owner or ask/task priority regressions, turn/session noun collapse, workflow overclaim, keyboard routing, or byte-pin changes.

Captain gate: choose **accept** for the future direction at `578d77a`. Acceptance records the exploration outcome on `feat/future-ui`; it does not authorize a merge to `main`.

## Stage Report: crucible (cycle 2)

- DONE: Re-test corrected checkpoint `578d77a` against both recorded round-1 findings and prove route/title/heading/tab/landmark semantics plus the turn-start noun in live and fixture evidence.
  Fresh DOM, screenshots, source, and fixtures close both findings: five distinct routes, one main per route, reciprocal tab/panel selection, and separate `turn started`/`session started` claims.
- DONE: Re-run the full crucible acceptance cross-check across Codex, Claude Code, and AGY, looking for regressions or new material command/comprehension risks rather than trusting the implementer report.
  The exact three identities and current API pass AC-1 through AC-5; 94 focused tests and manual semantic/keyboard/reflow probes found only the explicitly deferred tab-pattern refinement.
- DONE: Publish one source-bound verdict—revise, reframe, or accept—with fresh screenshots and a complete `Stage Report: crucible` suitable for the replacement captain gate.
  ACCEPT is the sole verdict; seven fresh captures, API timestamp, commit and byte hashes, current source, and falsifiable checks bind the replacement gate.

### Summary

The corrected checkpoint preserves the lede-first command hierarchy and now passes both rejected semantic claims across live overview, project, and three-harness drill-downs. No material finding remains; accept the isolated future direction at `578d77a`, with conventional roving-tab behavior retained as a non-blocking follow-up.

## Prototyping correction cycle 3 — evidence-shaped progressive disclosure

The captain retained the project-first direction but rejected four mechanisms in accepted snapshot
`578d77a`: a generic workflow-absence panel, a context-free refresh error, an absence-led captain
banner, and four equally weighted session cells. The correction is committed and pushed on
`feat/future-ui` at exact checkpoint `25401e1f4eb9d35b784b5a5c9728a894537e8d24`.

### Captain and failure-boundary rulings

The captain and first officer ruled that an exact ask from any harness remains operationally
important and may lead neutrally as `NEEDS YOU — <question>`. `CAPTAIN` wording requires both an
exact ask and positive Spacedock evidence on its owning session or project. With no exact ask, no
request lede or empty project response region is rendered.

The `data-next-state="stalled"` threshold means two consecutive `/api/data` refresh attempts failed.
The caught boundary includes a fetch rejection, non-2xx response, JSON parsing error, or local
workstream-observation error; it does not prove the event stream stopped. The corrected notice
therefore retains the last successful payload, says that live refresh attempts failed in a row,
warns that displayed data may be stale, reports last-success age when available, states the active
20-second streaming or 5-second legacy retry cadence, and offers a manually serialized `Retry now`.
The first failure remains quiet and any successful refresh clears the notice.

### Rejected mechanisms and correction

| Captain finding | Evidence-bound correction at `25401e1` |
|---|---|
| `Workflow source unavailable for these sessions` read as broken and added no value. | A project with no non-null `spacedock` record emits no workflow wrapper at all. Concrete plans and the existing positive first-officer/ensign context remain available only when the record supplies that evidence. |
| `Refresh stalled` looked fatal and unexplained. | The notice names failed live refreshes rather than a stopped stream, preserves the last view, reports stale risk/age and exact retry cadence, and provides a safe manual retry. |
| `CAPTAIN — No request observed / Current payload only` elevated absence and appeared outside authority context. | No ask means no banner. A plain exact ask is `NEEDS YOU`; only an ask whose project/session also has Spacedock evidence is `CAPTAIN`. Project rows omit and reflow the entire `RESPONSE` region when no exact request exists. |
| Empty Assignment, Next, and Captain cells competed with what the agent was doing. | Every session leads with `CURRENT ACTIVITY`. Assignment, next task, and needs-you/captain facts are rendered only when present. Missing assignment/next facts move into a closed `SOURCE COVERAGE` details element that names `Codex transcript`, `Claude transcript`, or `AGY CLI log` in plain language. An ask is one response fact, not duplicated as Next and Captain. |

### Failing-first and regression evidence

- Against the rejected renderer, the new overview/project tests produced 3 failures in 21 tests:
  plain asks incorrectly claimed captain authority, no-ask views retained the banner/response cells,
  and plain projects retained the workflow-absence wrapper.
- The new session assertions produced 6 failures in 32 tests: the fixed four-cell frame remained,
  request authority was unconditional, asks were duplicated as Next and Captain, and missing facts
  still occupied primary cards.
- The refresh correction produced 3 initial failures in 29 tests: the copy remained `Refresh
  stalled`, cadence/age/recovery were absent, and the unimplemented Retry action could not release
  its deferred request. An initial attempt to serialize every refresh then caused three existing
  revision/fallback tests to fail; narrowing serialization to repeated manual retries preserved SSE
  revision and safety-poll refreshes while making `Retry now` idempotent.
- Final focused proof: 102 tests passed across `test_next_page`, `test_next_projects`,
  `test_next_project`, `test_next_session`, `test_next_chrome`, and `test_next_live`.
- Full dashboard proof after the exact commit: 2,022 tests passed in 37.286 seconds with 1 skip.
  `scripts/lint_embedded.py`, `scripts/validate_plugins.py`, focused Ruff, and `git diff --check`
  also passed.

### Candidate byte proof

- Assembled `?next=true` response: 244,679 bytes; SHA-256
  `6eedb2be9a89d3ac53c7acf235b81e10bbd921c6b52218aa7c727b35207402db`.
- Changed part pins:
  - `next-chrome.js`: 9,324 bytes; `0bf4ca2ad32480e65069d6b1e116ca920a924adb3a45a6204ae96f4871482f2e`
  - `next-projects.js`: 8,454 bytes; `d3c80921cb169a22eeb2d5c1714864b5866143c8b8dc00b326cf1ffd405b4118`
  - `next-project.js`: 8,273 bytes; `710f05567474b071912107200e1f0c02b829c0113d75c02a65adc2291cb46e21`
  - `next-session.js`: 15,565 bytes; `a6ee15b2f05e0e8ed42953e816a016f1f949ec0cc4af056a3fa59145559eccaf`
  - `next-render.js`: 1,139 bytes; `e44cd6c2ec387032de04564eee1b05ea08bb8fc9ef8611d67370a9b19dcb0cc3`
  - `styles.css`: 27,641 bytes; `6567b05f746c02af9ad18be96790fe485b4c411f42d44bea6594d3e25365019d`

### Tied before/after live evidence

The pushed checkpoint ran at `http://127.0.0.1:4553/?next=true` under recorded PID `17013`; only
that PID was stopped, and port 4553 was verified closed. The live payload generated at
`1788148339.242155` retained the same three prior identities, `asks: []`, one working Codex session,
the full Claude `asked` instruction, and no Spacedock record on these selected sessions.

- Overview before: [absence-led captain banner](prototyping-cycle-2/overview-route-semantics.jpg).
  After: [progressive overview](prototyping-cycle-3/overview-progressive-disclosure.jpg) omits the
  absent request lede and every empty response region while keeping the one executing situation
  first. 1844×1067; SHA-256
  `2f20e373653ec8f503f67d4a974eb05d327255733c12c05fd77898f40b5db70a`.
- Project before: [generic workflow-source panel](prototyping-cycle-2/project-single-main.jpg).
  After: [workflow region omitted](prototyping-cycle-3/project-workflow-omitted.jpg) moves directly
  from project context to `GOING ON` because no selected session supplied Spacedock evidence.
  1844×1067; SHA-256
  `4fd9f7311f97fc20dae6e3b8bff408587aec8e3442d40a1e5eabbe73da0b3fda`.
- Codex before: [four equal command cells](prototyping-cycle-2/session-codex-turn-label.jpg).
  After: [same identity `01a0555c-2da3-7c23-bd26-4ea2e275d18a`](prototyping-cycle-3/session-codex-current-activity.jpg)
  leads with its working state and live subagent; assignment/next absence is only the collapsed
  source-coverage disclosure. 1844×1067; SHA-256
  `e87d9cae99219d9497f97931507e24b3952e9851c99dd1c6609a0c487ae043c5`.
- Claude before: [assignment beside three empty concepts](prototyping/session-claude-8b3e5aa1.jpg).
  After: [same API identity `8b3e5aa1`](prototyping-cycle-3/session-claude-assignment.jpg) leads with
  idle current activity and progressively discloses the complete published assignment below it.
  1844×1067; SHA-256
  `d4929fc4a1ce2b957630751e8cb12c3fbe3829e33a37b9dd92b28241d29bf0f4`.
- AGY before: [unavailable facts as primary cells](prototyping/session-agy-49fad07a.jpg). After:
  [same identity `49fad07a-21aa-4b2e-9c14-ecfcbcf67ab8`](prototyping-cycle-3/session-agy-current-activity.jpg)
  shows only its source-backed idle activity, with missing command facts collapsed beneath it.
  1844×1067; SHA-256
  `4029a544447c7dcacf80f1f0c232e25b7095ea55eaa62a17c29923513c2cf60a`.
- Live recovery: after the exact server was stopped, the page retained all 3 projects, 9 sessions,
  and the last `1 session executing` view while showing
  [the real recovery notice](prototyping-cycle-3/live-refresh-recovery.jpg): `Live refresh failed 3
  times in a row`, `Displayed data may be stale`, `Last updated 56s ago`, automatic 20-second retry,
  and `Retry now`. The production threshold is still two consecutive failures; a closed stream plus
  scheduled polls had produced three attempts by capture time. 1844×1067; SHA-256
  `dc2f273580b657f5828b1e06829bfe7869255b557d40277b52cc66cdcde994f6`.

## Stage Report: prototyping (cycle 3)

- DONE: The project and session views progressively disclose workflow, assignment, next-action,
  and captain concepts only when the source provides meaningful evidence, while current activity
  remains the session lede.
  The live project has no workflow wrapper without Spacedock evidence; all three same-identity
  sessions put `CURRENT ACTIVITY` first; only Claude's published assignment appears as a fact; and
  the focused plain-ask/Spacedock-ask/task fixtures fail if optional concepts reappear without their
  source predicate.
- DONE: The live-update failure state explains what stopped, whether displayed data may be stale,
  and what recovery is happening or available without presenting a context-free error.
  The real stopped-server capture preserves the last view and names failed live refresh attempts,
  stale risk, age, 20-second automatic retry, and `Retry now`; the 5-second legacy, first-failure
  quiet, retained-data, manual serialization, and success-clear paths are independently pinned by
  behavior tests.
- DONE: The corrected candidate is committed and pushed on feat/future-ui with focused behavior
  tests, refreshed byte pins, and before/after live captures covering Codex, Claude Code, and AGY.
  Exact pushed checkpoint `25401e1f4eb9d35b784b5a5c9728a894537e8d24` owns the 244,679-byte
  oracle, 102 focused and 2,022 full-suite passing tests, and the six linked exact-byte captures;
  the branch remains isolated and unmerged.

### Summary

Cycle 3 keeps the accepted project-first direction but removes absence as a command concept.
Workflow and authority now require positive Spacedock evidence, exact asks retain neutral attention
without borrowing captain semantics, sessions lead with observed activity and reveal command facts
only when published, and live-refresh failure is recoverable rather than fatal-looking. The pushed
checkpoint and tied evidence are ready for a fresh independent crucible judgment.

## Crucible cycle 3 — independent progressive-disclosure and recovery attack

This review attacked exact pushed checkpoint
`25401e1f4eb9d35b784b5a5c9728a894537e8d24` without changing the candidate. It did not inherit the
prototyping report's conclusions: the live renderer, source predicates, exact harness identities,
real network failure, and adversarial fixtures were checked independently.

### Verdict: revise one authority predicate

The progressive-disclosure direction and refresh recovery survive the attack, but the overview's
project-level authority predicate does not. A plain asking session can borrow `CAPTAIN` from a
different same-label session even though the product explicitly warns that a shared label is not
proof of the same directory. The overview and exact session then disagree about human
responsibility for the same ask. This is material command truth, so the candidate should be revised,
not accepted or reframed.

### Fresh disposition of the captain's four findings

| Captain finding | Independent proof at `25401e1` | Disposition |
|---|---|---|
| Generic workflow absence was empty and looked broken. | The live `recce/cargento` project proceeds from its scope directly to `GOING ON`; no workflow wrapper or absence message exists because none of the selected sessions publishes Spacedock evidence. `nextProjectPlanBlock` returns an empty string on that predicate. | Closed. The absence concept is omitted rather than decorated. |
| Refresh failure looked fatal and did not explain recovery. | The already-rendered overview was held open while the exact server was stopped. After two real `/api/data` failures, a `role=status` notice said refresh failed twice, warned the displayed data may be stale, gave a 35-second last-success age and 20-second cadence, and exposed `Retry now`; all 3 projects and `1 session executing` remained. Restarting the server cleared the notice automatically and retained the same view. | Closed. The real production failure and recovery boundary matches the claimed model. |
| Absence-led captain language and unconditional authority overclaimed. | With no asks, the live overview has no request banner and no response region. A single-session plain-ask fixture produces `NEEDS YOU`. However, adding a second same-label session with `spacedock: {role: "first-officer", workflows: []}` changes that plain ask to `CAPTAIN` in the overview, while the exact asking-session route remains `NEEDS YOU`. | **Reopened, material.** `nextProjectHasSpacedock(group.sessions)` authorizes from any grouped session instead of the exact ask owner or verified project identity. |
| Four equal session cells buried current activity and elevated missing facts. | Codex, Claude, and AGY all lead with `CURRENT ACTIVITY`. Only Claude's published assignment appears in the primary fact stack. Codex and AGY omit assignment/next from the main hierarchy; the native closed `SOURCE COVERAGE` summary is focusable (`tabIndex == 0`) and opens to the harness-specific source explanation. | Closed. Current activity owns the lede and missing facts are subordinate, operable disclosure rather than primary cards. |

### Material finding and reproduction

**Owner:** `cargento_runtime/web/next/next-projects.js`, specifically
`nextProjectHasSpacedock` / `nextProjectRequestLabel`, plus a mixed-session regression fixture in
`test_next_projects.py`.

The existing plain-ask test contains only the exact plain session, and the existing Spacedock-ask
test puts Spacedock on the asking session. The missing cross-product is decisive:

1. Assign `Plain approval` to plain session `beta-work` in project-label group `beta/app`.
2. Add `beta-spacedock-sibling` with the same project label and a non-null Spacedock object.
3. Render the overview: `CAPTAIN_PLAIN=True`, `NEEDS_YOU_PLAIN=False`, and the row says
   `RESPONSE / Captain · Plain approval`.
4. Render the exact `beta-work` session with that sibling present: `SESSION_NEEDS_YOU=True` and
   `SESSION_CAPTAIN=False`.

This is not merely copy polish. The overview assigns captain authority using group-level evidence,
while the drill-down assigns it using session-level evidence. The same project row also displays the
measured caveat `Same label is not proof of the same directory`, so the grouping mechanism cannot
serve as verified owning-project evidence. The correction should derive authority from the exact
ask owner's session (or a separately verified project identity), then pin the overview/session
agreement in a mixed plain-plus-Spacedock fixture.

### Five-second scan and progressive-disclosure judgment

- [Overview](crucible-cycle-3/overview-live.jpg) exposes the overall situation in one scan: 3
  projects, 9 sessions, and `1 session executing`; no empty request or response concept competes
  with it.
- [Project](crucible-cycle-3/project-live.jpg) preserves scope (`recce/cargento`, latest session
  context, seven-session collision caveat) and leads with the single live activity under `GOING ON`.
- [Codex](crucible-cycle-3/session-codex-live.jpg), exact SID
  `01a0555c-2da3-7c23-bd26-4ea2e275d18a`, says `working · running 1 subagent` first and does not
  invent assignment or next action.
- [Claude](crucible-cycle-3/session-claude-live.jpg), exact API identity `8b3e5aa1`, says idle first
  and then exposes the complete published `asked` assignment.
- [AGY](crucible-cycle-3/session-agy-live.jpg), exact SID
  `49fad07a-21aa-4b2e-9c14-ecfcbcf67ab8`, says idle first and leaves unpublished assignment/next
  facts in the closed source-coverage disclosure.

The progressive-disclosure mechanism therefore passes on current activity, supported assignment,
supported next action, and omission of empty concepts. It fails only at human-responsibility
provenance when project grouping mixes authority sources; that defect is invisible in the no-ask
live payload and required the adversarial mixed fixture.

### Real refresh recovery evidence

- [Two-failure retained state](crucible-cycle-3/refresh-failed-retained.jpg) is a fresh 1844×1123
  production capture after stopping only the server started by this review. The notice is visible,
  all three project rows remain, and `1 session executing` is unchanged.
- [Recovered state](crucible-cycle-3/refresh-recovered.jpg) is a fresh 1844×1123 capture after the
  exact server restarted. The stream's successful refresh clears the notice without a page reload;
  the same three rows and situation remain.
- The stopped server PID `30510` and restarted PID `31652` were each stopped through the launcher;
  port 4553 was verified closed after the review.

The screenshots are byte-preserved JPEG artifacts. Their SHA-256 values are, respectively:
overview `9a2b51b9ba9f8d1192f9aa9289601816bd11d78d97fdf4212e98279ef3dc0cd4`, project
`f2b2d4487827d46b021da1f4628b465b6b88c0a295b2422752c63a55628170f5`, Codex
`49b366ed0aebbc9316e053b1b51617c239e3d18b42e1ee209ab711a70b1d87f2`, Claude
`5fd7756b32078f5165cd540b26ecc47314e3f7450278128d12c58b4df5977318`, AGY
`b88325365568eab8c2eb9daea9074eda63c97d47ce90eb2519e737589c6c999d`, failed refresh
`621fb3b7bda523f4f8eea7cf5a56b3bddc097f4436bbcc1496eabd6086bf2515`, and recovered refresh
`8ae48b1ebb1a2ec7b3e04ac0cc2e4816c82b54ad361d435190c7665f9cb24fb4`.

### Checks and source boundary

- The assembled candidate remains 244,679 bytes with SHA-256
  `6eedb2be9a89d3ac53c7acf235b81e10bbd921c6b52218aa7c727b35207402db`, matching the committed
  byte oracle.
- 115 focused tests passed across `test_next_page`, `test_next_projects`, `test_next_project`,
  `test_next_session`, `test_next_sessions`, `test_next_chrome`, and `test_next_live`.
- `scripts/lint_embedded.py`, `scripts/validate_plugins.py`, and
  `scripts/bump_version.py --current` passed. The repository checkout remained at exact commit
  `25401e1f4eb9d35b784b5a5c9728a894537e8d24` with no candidate modification.
- Passing current tests do not close the material finding because none combines a plain ask owner
  with a different same-label Spacedock session. The inline harness reproduction above supplies
  that missing adversarial evidence.

## Stage Report: crucible (cycle 3)

- DONE: Attack exact checkpoint `25401e1` at the live renderer, source, and adversarial-fixture
  layers and independently disposition all four captain findings.
  Three corrections close under fresh proof; the fourth reopens as a material overview/session
  authority contradiction in the mixed plain-plus-Spacedock fixture.
- DONE: Exercise the same Codex, Claude Code, and AGY identities and judge the five-second scan for
  overall situation, project scope, current activity, supported assignment/next action, and human
  responsibility without empty concepts or buried ledes.
  Situation, scope, activity, assignment, next-action omission, and source coverage pass. Human
  responsibility fails only when unrelated same-label Spacedock evidence promotes a plain ask to
  captain authority in the overview.
- DONE: Prove real refresh failure/recovery, run focused frontend checks, preserve fresh captures,
  and publish one source-bound verdict without modifying the candidate.
  A two-failure production outage retained the full view and exposed actionable status; automatic
  recovery cleared it. Seven fresh captures, 115 passing focused tests, source inspection, and the
  mixed fixture support **REVISE**.

### Summary

The candidate's lede-first progressive disclosure and live recovery are credible and should be
retained. One material predicate still breaks command truth: the project overview borrows captain
authority from any same-label session, while the exact asking session correctly stays neutral.
Revise authority derivation to follow the exact ask owner or a verified project identity, add the
mixed-session regression, and return the corrected checkpoint for a fresh crucible.

## Prototyping correction cycle 4 — exact ask-owner authority

The single material crucible-cycle-3 finding is corrected and pushed on `feat/future-ui` at exact
checkpoint `94f19d3002aca84602cbfba7ea7714ae96c92b94`. The accepted progressive-disclosure and
live-refresh mechanisms are otherwise unchanged.

### Root cause and bounded correction

`nextProjectRequestLabel(group)` discarded the ask's `session_id` and authorized `CAPTAIN` whenever
any session in the shared-label group had a non-null Spacedock record. That predicate contradicted
the adjacent warning that a shared label is not proof of the same directory and let an unrelated
same-label sibling lend authority to the exact plain ask owner.

The corrected predicate receives both the group and ask, resolves only the session whose `sid`
equals `ask.session_id`, and checks Spacedock evidence on that owner alone. An ask without a
resolvable exact session remains the neutral `NEEDS YOU`; the current payload supplies no separately
verified owning-project identity from which broader authority could be proven. Both the overview
lede and project-row response call the same exact-owner predicate, while the session drill-down
continues to derive its wording from that exact session.

Only `next-projects.js`, its behavior fixture, and the mechanically derived byte pins changed.
Workflow progressive disclosure, the four-part session command frame, source coverage, and refresh
failure/recovery code did not change.

### Failing-first authority proof

- At rejected checkpoint `25401e1`, the new mixed fixture adds
  `beta-spacedock-sibling` beside plain ask owner `beta-work`, both under display label `beta/app`.
  The focused test failed exactly because the overview rendered `CAPTAIN — Plain approval` and the
  row rendered `Captain · Plain approval`; the exact `beta-work` session already rendered
  `NEEDS YOU`. This reproduces the crucible contradiction rather than a synthetic adjacent failure.
- After the exact-owner correction, the same mixed fixture requires and receives
  `NEEDS YOU — Plain approval`, `Needs you · Plain approval`, and `NEEDS YOU` on the exact session,
  with every `CAPTAIN` form absent.
- The positive Spacedock-owner path is independently pinned end to end: ask owner `alpha-gate`
  retains `CAPTAIN — Approve the release`, `Captain · Approve the release`, and `CAPTAIN` on its
  exact session. The complete `test_next_projects` module passes all 11 tests.

### Candidate bytes and focused preservation checks

- `next-projects.js`: 8,645 bytes; SHA-256
  `66cb8b5f037ee4ed8806bb06c865c7149e1da69173c51c3bad12ccbd58c1b4ba`.
- Assembled `?next=true` response: 244,870 bytes; SHA-256
  `e4951167c0b803bf15593d89fdf294aa07f22dd243d7cf4d07096f644176fb06`.
- Fresh post-commit proof passed 115 tests across `test_next_page`, `test_next_projects`,
  `test_next_project`, `test_next_session`, `test_next_sessions`, `test_next_chrome`, and
  `test_next_live` in 7.372 seconds. This batch retains the accepted workflow omission, optional
  command facts, collapsed source coverage, two-failure stale notice, last-view retention, safe
  manual retry, successful recovery, route semantics, and byte oracles.
- Focused Ruff check and format, `scripts/lint_embedded.py`, `scripts/validate_plugins.py`,
  `scripts/bump_version.py --current`, and `git diff --check` all passed. The local and remote
  `feat/future-ui` heads both resolved to exact checkpoint `94f19d3`, with a clean product worktree.

### Tied adversarial and live Chrome evidence

The critical ask-authority branch is source-bound by the mixed behavior fixture because the live
payload contained no ask. Fresh Chrome observation of the exact committed server at
`http://127.0.0.1:4553/?next=true` separately checked that the surrounding accepted candidate did
not regress:

- The overview exposed 3 projects, 9 sessions, and `1 session executing`, with no absent-request
  lede and no empty response region. Its viewport capture was 47,429 PNG bytes with SHA-256
  `6e9859c2fba31eb527d5c6fbc89d59e0653cd974070dcf767496f31a25cbdc61`.
- The `recce/cargento` drill-down moved from project context directly to `GOING ON`; no generic
  workflow-absence panel reappeared.
- Exact Codex session `01a0555c-2da3-7c23-bd26-4ea2e275d18a` led with `CURRENT ACTIVITY`, rendered
  `working · running 1 subagent`, and kept `SOURCE COVERAGE` collapsed. Its viewport capture was
  44,609 PNG bytes with SHA-256
  `b0cbd654f154e432cf7732abc18f4f13b8902bde591b0bd98a3779f87eb39c87`.
- The server was the process started for this proof, PID `41207`; it was stopped through the
  launcher and port 4553 was verified closed.

## Stage Report: prototyping (cycle 4)

- DONE: Authority wording on overview and project rows follows the exact ask-owning session, never
  an unrelated same-label session; mixed plain-plus-Spacedock fixtures keep overview and session
  drill-down consistent.
  The failing-first `beta/app` cross-product now stays neutral across all three surfaces, while the
  exact Spacedock-owned `alpha-gate` ask stays captain-authorized across the same surfaces.
- DONE: The bounded fix preserves the accepted progressive-disclosure and refresh-recovery behavior,
  updates byte pins mechanically, and passes the focused frontend checks.
  No workflow, session-frame, source-coverage, or live-recovery implementation changed; the fresh
  115-test batch, validators, live no-ask overview, project, and exact-session observations all pass.
- DONE: The corrected candidate is committed and pushed only on feat/future-ui with tied
  live/adversarial evidence and a complete prototyping report ready for fresh crucible review.
  Exact local and remote checkpoint `94f19d3002aca84602cbfba7ea7714ae96c92b94` owns the
  244,870-byte oracle, the mixed authority fixture, and the source-bound evidence above; it remains
  isolated and unmerged.

### Summary

Cycle 4 removes the one authority leak without changing the accepted command-surface direction.
Human-responsibility wording now follows the exact ask owner, same-label siblings cannot lend
captain semantics, neutral asks remain visible, and Spacedock-owned asks retain their authoritative
lede. The pushed checkpoint and complete source-bound proof are ready for Halley's fresh crucible
review.

## Prototyping cycle 5 — attention queue design contract

The design-only strategic iteration is committed and pushed on `feat/future-ui` at exact checkpoint
`cc2f3237565b932d74199ba8faa237087998ef1b`. It adds only
`docs/plans/future-ui-attention-queue-design.md`; production code, tests, byte pins, and both UI
assemblies are unchanged from accepted baseline `94f19d3`.

The specification makes Attention the default opt-in route, with Projects as the adjacent complete
map and Sessions as the adjacent flat inventory. Its fixed order is Needs you now, At risk, Close
the loop, Coming next, and Healthy fleet; stable predicates and comparator chains replace severity
scores.

The source contract deliberately refuses three requested outcomes the payload cannot prove:
same-label sessions do not establish one repository, a stop is not a finished-but-unread result,
and no current field distinguishes a quiet death. Cargento-derived ETAs are also excluded from the
source-published checkpoint lane. Capability coverage makes those limits visible without turning
silence into an all-clear.

Self-review removed empty `NEXT` placeholders from the wide wireframe, prohibited Healthy fleet
from becoming a duplicate Sessions panel, bound captain authority to the exact ask owner, and made
git-conflict predicates distinguish boolean/integer evidence from present null fields. Placeholder
and ambiguity scans found no unfinished marker or conditional panel, and all 22 acceptance cases
state falsifiable behavior across Claude Code, Codex, and AGY.

### Checks and unchanged-byte proof

- `python3 scripts/validate_plugins.py` passed.
- `git diff --check` passed for the new document.
- The stable page byte oracle passed at 321,790 bytes, SHA-256
  `fe221aa43b27f17859e350cee10296745faa0a560217026d26fab6cafc346a50`.
- The opt-in page byte oracle passed at 244,870 bytes, SHA-256
  `e4951167c0b803bf15593d89fdf294aa07f22dd243d7cf4d07096f644176fb06`.
- Local and remote `feat/future-ui` both resolve to `cc2f3237565b932d74199ba8faa237087998ef1b`.

## Stage Report: prototyping (cycle 5)

- DONE: Write and commit a complete attention-queue design spec on feat/future-ui that makes Attention the default route and Projects and Sessions adjacent top-level views, without changing production UI bytes.
  Exact checkpoint `cc2f323` changes one design document; both stable and opt-in assembled-byte
  oracles retain their accepted sizes and SHA-256 values.
- DONE: Define the queue taxonomy, deterministic ranking, item grammar, source/coverage truth rules, full-project-map access, responsive and accessible behavior, and empty, stale, partial, and conflicting-signal states with no unsupported all-clear or prediction claims.
  The contract maps each visible claim to a predicate, exposes unknown capability coverage, and
  excludes repository, unread-result, termination-cause, authority, and derived-ETA inference.
- DONE: Self-review the spec for placeholders, contradictions, ambiguous source ownership, excess panels, and untestable requirements; include falsifiable behavior scenarios across Codex, Claude Code, and AGY, then stop for captain review before implementation planning.
  The audit corrected four ambiguities and leaves 22 exact cross-harness behavior scenarios; no
  implementation plan, production edit, test edit, byte-pin edit, or browser prototype follows.

### Summary

The captain now has a complete written contract for an exception-first Attention route whose fleet
brief remains honest under partial reporting. The checkpoint is pushed, UI bytes are unchanged,
and work stops here for written-spec review before any implementation planning.

## Prototyping cycle 6 — implementation plan

The captain-approved design at `cc2f323` is now decomposed into a test-first execution plan at
`docs/superpowers/plans/2026-08-31-future-ui-attention-queue.md`. The plan-only checkpoint is
`015eab909fe73f00aa424aac0c00477be3e7eec5`, pushed on `feat/future-ui`; no production source,
test, byte pin, or approved-spec byte changed in this stage.

Nine serialized tasks own one web conflict surface: route migration; exact-owner Needs subjects;
At-risk predicates/order; stop/checkpoint/remainder semantics; coverage/rendering/escaping; project
map reuse; atomic refresh/focus; one mechanical byte-pin regeneration; and final live/validation
proof. Each implementation checkpoint states exact files, interfaces, red command and expected
failure, minimal behavior, green command, and signed-off commit.

The plan defines the `NextAttentionModel`, subject/signal/coverage shapes, stable key forms, fixed
signal names, helper signatures, and exact concatenation seam for `next-attention.js`. Its coverage
matrix maps all 22 approved acceptance scenarios to named tests across Claude Code, Codex, and AGY.

Self-review added non-numbered spec obligations for multiple asks, malformed values, exact outcome
fallback, route-specific empty maps, bare-input and risk comparator details, quota reset
de-duplication, and project collision counts. It removed empty interface bodies, aligned model
fields with renderer needs, and made rate capability distinguish known non-reporting from failure.

### Checks and unchanged-byte proof

- Required header, 9 tasks, 47 checkbox steps, and all 22 numbered scenarios were structurally
  verified; placeholder-pattern scan found no unfinished marker or empty interface body.
- `python3 scripts/validate_plugins.py` and document `git diff --check` passed.
- Stable and opt-in page byte-oracle tests passed unchanged: stable 321,790 bytes at
  `fe221aa43b27f17859e350cee10296745faa0a560217026d26fab6cafc346a50`; opt-in 244,870 bytes at
  `e4951167c0b803bf15593d89fdf294aa07f22dd243d7cf4d07096f644176fb06`.
- Local and remote `feat/future-ui` both resolve to
  `015eab909fe73f00aa424aac0c00477be3e7eec5`.

## Stage Report: prototyping (cycle 6)

- DONE: Write and commit a complete test-first implementation plan at docs/superpowers/plans/2026-08-31-future-ui-attention-queue.md that implements the approved attention-queue spec without changing production code, tests, or byte pins.
  Exact checkpoint `015eab9` adds one plan file; both UI byte oracles retain the design checkpoint's
  exact sizes and digests.
- DONE: Decompose work by clear frontend responsibility and independently testable behavior, with exact files, interfaces, code sketches, failing-test commands and expected failures, minimal implementation steps, passing checks, and signed-off commit checkpoints.
  Nine ordered tasks isolate classification, rendering, maps, refresh, mechanical pins, and live
  proof while keeping every implementation checkpoint red/green and DCO signed.
- DONE: Self-review every approved spec requirement and all 22 acceptance scenarios for task coverage, remove placeholders and inconsistent names, include serialized frontend byte-pin and validation steps, then stop for execution-mode selection.
  The matrix covers scenarios 1–22 and the source-contract edge cases; byte regeneration and the
  full suite occur once, after all web edits, and no execution task has begun.

### Summary

The approved source contract now has a zero-placeholder, task-complete TDD execution plan with one
authoritative interface vocabulary and serialized proof. The plan and report are pushed, product
bytes are unchanged, and work stops for captain selection between subagent-driven and inline
execution.
