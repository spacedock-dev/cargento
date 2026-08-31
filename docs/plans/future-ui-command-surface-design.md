# Future UI Command Surface Design

**Status:** Captain-approved on 2026-08-31

## Purpose

The `?next=true` surface must answer a command question before it presents inventory. The overview answers, “Where does my attention belong?” A session answers, “What is this agent doing, what happens next, and what does it need from me?” The current five-column overview and transcript-led session page leave those answers implicit or replace missing evidence with confident prose.

## Evidence boundary

The browser may render only facts present in the current API payload. It must not infer intent from a project name, treat a clipped title as a durable assignment, infer a next action from activity narration, or turn an absent workflow record into proof that no workflow exists.

The source owners are:

- Codex command facts: `Codex transcript`
- Claude command facts: `Claude transcript`
- Antigravity command facts: `AGY CLI log`
- Outstanding captain requests: the payload's `asks` collection

An `instruction` whose label is `asked` is a published assignment. The full instruction remains authoritative when a shorter title echoes it. `agent` and `earlier` instructions are context, not assignments. An outstanding ask is the only exact captain request. The first in-progress or pending task is the only published next action when there is no ask. Missing facts use `unavailable` or `not published` and name their source owner.

## Overview: command brief

Replace the five-column project inventory with project briefing rows. Sort projects that contain an outstanding ask first, followed by executing projects and then idle projects. Each row contains:

1. `SITUATION`: the exact outstanding question, an executing-session count, or an idle statement.
2. `RESPONSE`: the exact response needed and `Captain` owner when an ask exists; otherwise `No request observed` with the qualifier `Current payload only`.
3. Bounded context: project name, published workflow chips, task progress when present, latest published assignment when present, and the existing same-label collision caveat.

The page lede uses the same captain state as the highest-priority project. If an ask exists it presents the exact request. Otherwise it reads `CAPTAIN — No request observed` and immediately qualifies the claim with `Current payload only`. It never says `clear` and never implies exhaustive coverage.

## Session: four-part command frame

The title becomes identity and context, not the primary command claim. The command frame appears first and contains:

1. `ASSIGNMENT`: the full `asked` instruction. If none was published, `Assignment unavailable` and the exact harness source owner.
2. `EXECUTION`: the published session state and state detail. An `agent` or `earlier` instruction may appear here with its label as bounded context.
3. `NEXT`: the exact outstanding ask; otherwise the first in-progress task, then the first pending task. If none exists, `Not published` and the exact harness source owner.
4. `CAPTAIN`: `Respond` with the exact ask when one exists. Otherwise `No request observed` with `Current payload only`.

Health warnings, answer controls, tasks, subagents, and token evidence remain below the frame. The frame must escape all untrusted strings and keep source qualifiers accessible as text, not title-only help.

## Project and workstream truth

When selected sessions publish no Spacedock workflow record, the project page says `Workflow source unavailable for these sessions`. It retains the distinct first-officer and ensign empty states that have positive role evidence.

Rename `WORKSTREAM` to `OBSERVED STATE CHANGES`. Rows use the full registry label, such as `Claude Code`, rather than initials such as `CC`. The empty state says that no state changes were observed since the tab opened. This is a tab-local transition log, not a semantic or causal workflow timeline.

## Visual treatment

The command lede and four-part frame use the existing next-page type, color, route, and focus conventions. Semantic labels remain visible at narrow widths; source qualifiers wrap rather than disappear. Project briefing rows stay keyboard-clickable and preserve their route attributes.

## Verification

Behavior tests will prove the previous failures before production code changes:

- overview prioritizes asks and renders situation/response without empty estimate or delegation inventory;
- no-ask captain copy includes `Current payload only`;
- the session frame preserves a full Claude `asked` instruction even when the title clips it;
- Codex and AGY missing assignment/next facts name their exact owners;
- plain project workflow absence is uncertain, not declarative;
- observed state changes use full harness labels and bounded copy.

After focused tests pass, recompute each changed frontend part's byte size and SHA-256 plus the assembled page pins. Capture overview, project, and the same Codex, Claude, and AGY session identities in Chrome from the committed candidate bytes.

## Non-goals

This prototype does not add a sidecar model, synthesize a semantic timeline, change the stable UI, alter collector payloads, or invent estimates, confidence, delegation, workflow, intent, or causal links.
