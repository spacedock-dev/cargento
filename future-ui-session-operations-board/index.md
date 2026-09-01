---
id:
title: Session Operations Board
status: reconnaissance
source: Captain rejection of future-ui-command-surface on 2026-09-01
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
        - id: gate:future-ui-session-operations-board:framing
          stage: framing
          attempts:
            - id: gate-attempt:future-ui-session-operations-board-framing-1
              briefing:
                id: briefing:future-ui-session-operations-board:framing:attempt-1:revision-1
                digest: sha256:0af4a0e2729c814dd724d3b4236c0b350bee235e8df0c65e1f25fadfaf3c2b53
                room-ref: ./review/framing/briefing-1
              resolution:
                type: Resolution
                id: resolution:spacedock:future-ui-session-operations-board:framing:1
                briefing: briefing:future-ui-session-operations-board:framing:attempt-1:revision-1
                by: person:captain
                at: "2026-09-01T00:04:15.863052Z"
                decision: approve
                reason: Captain approved the Session Operations Board direction and explicitly requested preparation retry after the corrected artifact path was identified.
              application:
                target-stage: reconnaissance
                state: consumed
---

Replace the Attention-first ranking model with an exact-session operations board that lets a person scan the fleet and answer where each session is, what it is doing now, what it may do next, and whether it is blocked.

## Design bet

Cargento will become easier to understand if exact sessions are the irreducible unit of the default view. Four fleet facts lead; one comparable session surface carries WHERE, NOW, NEXT, and BLOCKED. Exceptions change sorting and emphasis but never replace or aggregate away sessions.

## Baseline and command risk

The accepted command-surface checkpoint hides fleet state behind attention subjects. It reports contradictory running and moving counts, promotes identity coverage above current work, collapses seven exact sessions into one risk, and offers no route that compares WHERE, NOW, NEXT, and BLOCKED fleet-wide. Browser-default link color, orphan list numbering, and a shared CSS class also corrupt the visual hierarchy.

## Method

Use real Codex, Claude Code, and Antigravity sessions to test the truth boundary for location, activity, plans, and blockage. Prototype the Session Operations Board on `feat/future-ui`. After each correction, run fresh visual, semantic, and cross-harness review before another captain gate.

## Acceptance criteria

**AC-1 — The default view exposes fast fleet facts without contradiction.**
Verified by: a live capture and payload comparison showing total observed sessions, working sessions, exact requests, and reported blocks are computed from the same exact-session population.

**AC-2 — A five-second scan identifies every operational session and its four command facts.**
Verified by: fresh reviewers can locate each exact session and state its WHERE, NOW, NEXT, and BLOCKED values without opening another route; unsupported facts read as not published or unknown rather than empty panels.

**AC-3 — Exceptions never erase fleet context.**
Verified by: collision, request, risk, and missing-source fixtures preserve one visible row per exact session while changing only row emphasis, badges, or sort order.

**AC-4 — Source limits remain truthful across Codex, Claude Code, and Antigravity.**
Verified by: live three-harness evidence distinguishes reported, inferred, unknown, and absent facts; an in-progress task appears under NOW, and only a pending published step may appear under NEXT.

**AC-5 — The visual system makes status and navigation legible.**
Verified by: wide and 320-pixel captures show no browser-default links, orphan numbering, false active stripes, clipped command facts, or horizontal overflow; semantic status colors and focus states meet the repository's accessibility checks.

## Iteration record

The prior `future-ui-command-surface` experiment remains archived at commit `1cb112e`. This successor records the captain's rejection of the Attention model and approval of the Session Operations Board direction.

## Known limits

Cargento currently preserves a lossy project display label rather than exact directory, repository, branch, or worktree location. Codex and Claude publish different kinds of plan evidence; Antigravity publishes no native next-action list and cannot always report blocked state.

## Out of scope

This experiment does not merge to `main`, claim exact filesystem location from project labels, or redesign stable UI outside `?next=true`.
