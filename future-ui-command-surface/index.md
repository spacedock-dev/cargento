---
id:
title: Future UI command surface
status: prototyping
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
