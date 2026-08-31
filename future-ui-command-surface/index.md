---
id:
title: Future UI command surface
status: framing
source: Captain commission on 2026-08-31 and the 2026-08-27 project-cockpit debrief
started:
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
                state: pending
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
