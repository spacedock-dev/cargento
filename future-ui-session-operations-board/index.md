---
id:
title: Session Operations Board
status: prototyping
source: Captain rejection of future-ui-command-surface on 2026-09-01
started: 2026-09-01T00:07:26Z
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

## Reconnaissance evidence

The live server rendered the `feat/future-ui` checkpoint at `1cb112e` on
`http://127.0.0.1:4553/?next=true`. A `/api/data` observation generated at
`2026-09-01T00:11:31Z` contained seven exact sessions in the 24-hour window: one
working session, six idle sessions, one running subagent, four of four reported tasks
complete, no exact requests, and zero reported `needs_input` sessions. That last
number is not fleet-wide proof of no blockage: the harness registry says Antigravity
does not report `needs_input`.

### Exact observed sessions

| Harness | Exact source identity | Live observation | Source boundary for WHERE / NOW / NEXT / BLOCKED |
|---|---|---|---|
| Codex | `01a0555c-2da3-7c23-bd26-4ea2e275d18a` (`01a0555c` display key) | The live first-officer session was working with subagent `Einstein`; all four published plan items were already complete. | WHERE is only the lossy `recce/cargento` label. NOW is source-backed as `running 1 subagent`. No pending or in-progress plan step publishes NEXT. Codex can report `needs_input`, and this exact session had no request, so BLOCKED is **not reported**, not disproved. |
| Claude Code | `8b3e5aa1-4ed6-4ac9-91f0-7d148c3ea631` (`8b3e5aa1` API identity) | The real `CLAUDE-RECON-20260831` session completed its one-turn README task and was idle. Its transcript and the live API agree on the assignment. | WHERE is only the lossy project label. NOW is source-backed as `awaiting your message`; the assignment is published. The transcript publishes no NEXT. Claude can report `needs_input`, and this exact session had no request, so BLOCKED is **not reported**, not disproved. |
| Antigravity | `49fad07a-21aa-4b2e-9c14-ecfcbcf67ab8` (`49fad07a` display key) | The real `AGY-RECON-20260831` session completed its README task and was idle. The generated transcript preserves the marked request, while the bounded public CLI log preserves identity and lifecycle but lacks the `HandleUserInput` prompt marker before `Forwarding user message`. | WHERE is only the lossy project label and NOW is source-backed as idle. The current collector deliberately reads the public log, so assignment and NEXT are not published to the API even though the generated transcript records the request. Antigravity does not report `needs_input`; BLOCKED is therefore **unknown**, not false. |

### Live captures

- [Project overview](reconnaissance/overview-projects.jpg) — 1531×1103; two project rows aggregate seven payload sessions, so six `recce/cargento` sessions disappear behind one label.
- [Flat session inventory](reconnaissance/overview-sessions.jpg) — 1531×1047; all seven payload sessions render, but exact IDs and WHERE / NOW / NEXT / BLOCKED are not comparable visible columns.
- [Codex exact-session drill-down](reconnaissance/session-codex-01a0555c.jpg) — full UUID in the breadcrumb, source-backed current activity, completed plan, live subagent, and the expanded missing-assignment/NEXT disclosure.
- [Claude Code exact-session drill-down](reconnaissance/session-claude-8b3e5aa1.jpg) — collector identity, source-backed full assignment, idle state, and the expanded missing-NEXT disclosure.
- [Antigravity exact-session drill-down](reconnaissance/session-agy-49fad07a.jpg) — full UUID in the breadcrumb, idle state, and the expanded public-log assignment/NEXT limit.

### Fact versus inference inventory

| Command fact | Source-backed fact | Inference the board must not make | Current UI classification |
|---|---|---|---|
| Fleet | `/api/data` contains seven sessions and the flat table renders seven rows. | Two project labels are not two operational sessions, and a shared label does not establish a shared directory or worktree. | **UI failure:** the default project tab aggregates exact sessions away; the alternate table hides IDs in `data-next-session` attributes rather than showing them. |
| WHERE | Every row has a harness, exact collector identity, and lossy two-segment project label. | `recce/cargento` is not an exact path, repository, branch, or worktree. | **Mixed:** the source lacks exact location, while the UI presents the lossy label without a visible `not published` WHERE fact. |
| NOW | Codex reports working with one named subagent; Claude and Antigravity report idle. Claude also publishes its assignment. | Completed Codex plan items do not explain what the still-running subagent is doing; AGY's project-name heading is not an assignment. | **Mostly source-backed:** drill-down current activity is truthful, but the fleet view does not give NOW a stable comparable label. |
| NEXT | None of the three observed sessions publishes a pending step; each expanded source-coverage note says so. | A completed plan, transient assignment, idle state, or running subagent is not a next action. | **UI hierarchy failure:** truthful disclosures exist only collapsed inside each drill-down, so NEXT cannot be scanned fleet-wide. |
| BLOCKED | No exact request was present. Codex and Claude can report `needs_input`; Antigravity cannot. | `summary.needs_input: 0` cannot prove Antigravity is unblocked, and `awaiting your message` is not a block contract. | **Mixed, command-critical:** the source limitation is real, but no visible per-session `not reported` or `unknown` fact prevents a false all-clear. |
| Status emphasis | Only the first row is working. | A continuous green rail through every ACTIVITY cell does not mean every row is active. | **Pure UI failure:** `.next-session-activity` styles both the detail card and every table activity cell, giving idle rows the active accent. |

### Ranked findings

1. **Critical command risk — fleet context / all four facts:** the default view reduces seven exact sessions to two project rows. A captain cannot identify every session or compare WHERE, NOW, NEXT, and BLOCKED without changing views and opening rows; this is a UI failure because the payload already has all seven session records.
2. **High command risk — BLOCKED:** Antigravity explicitly does not report `needs_input`, yet neither overview nor row exposes BLOCKED as unknown. Any fleet-wide reading of zero reported blocks as zero blocked sessions is unsupported; source and UI share ownership.
3. **High command risk — NEXT:** none of the three live sources publishes a pending next action, but `not published` appears only in a collapsed drill-down disclosure. Completed Codex tasks plus a live subagent make silent inference especially tempting; this is a UI hierarchy failure over a truthful source gap.
4. **High comprehension risk — WHERE:** six sessions collide on `recce/cargento`; the warning says labels are lossy but supplies no exact location or explicit unknown. The missing directory/branch/worktree is a source limit, while presenting the label as the only location cue is a UI failure.
5. **High comprehension risk — identity:** the flat fleet table omits visible exact IDs, and Claude's collector intentionally reduces its source UUID to eight characters. The UI could expose the identities it receives, but it cannot reconstruct Claude's full UUID from the current payload.
6. **Medium comprehension risk — NOW emphasis:** one working row correctly owns the left accent, but the shared `.next-session-activity` selector draws an accent rail through all seven rows. This pure UI defect visually promotes idle activity and weakens the one real working signal.

## Stage Report: reconnaissance

- DONE: observe one real session each from Codex, Claude Code, and AGY, preserving exact session identity and distinguishing missing source data from UI failure.
  The three exact source identities above were matched to the live API and native records; changing a UUID, marked request, prompt-marker boundary, or harness capability would break the classification.
- DONE: capture the live project overview and an exact-session drill-down from the current Next UI without replacing the sessions under study with mock-only evidence.
  Five live 1531-pixel-wide captures preserve the seven-row payload, project aggregation, and all three exact drill-downs; removing a route, source disclosure, or observed session would make the capture set incomplete.
- DONE: record a fact-versus-inference inventory and rank findings by comprehension or command risk against WHERE, NOW, NEXT, and BLOCKED.
  The inventory binds every command fact to `/api/data`, native records, renderer behavior, or an explicit source limit; each ranked finding names source, UI, or mixed ownership.

### Summary

Three real harness sessions show that the current UI reports NOW honestly at drill-down but cannot yet operate as an exact-session board. The default aggregation erases fleet context, WHERE is lossy, NEXT is buried as missing coverage, and BLOCKED is unsafe for Antigravity; the five committed live captures preserve those boundaries for prototyping.
