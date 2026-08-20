---
title: Session view with Spacedock visibility
status: backlog
source: captain seed
id: qsvfrrs3832xn9qe9x7eqp90
---

Cargento's dashboard has two overview modes — `regular` and `calm` — that summarize all
sessions. There is no per-session view. The reference (`/private/tmp/image (1).png`)
shows a "Task Map": a dispatch tree of work items connected by dependency edges with
stage-colored nodes, plus panels for recent completions, active claims, available, and
blocked. A session view should render that dispatch tree for one session and add a
high-level goal — a sprint or stated objective — if the session carries one (stated in
its workflow/roadmap context, or derived from the entities it is driving).

## Problem

An operator watching one active session (a first officer driving a sprint) cannot see,
for that session alone, the dispatch tree of what it is working or the high-level goal it
is pursuing. The overview modes aggregate all sessions and do not render per-session
dependency trees. Today the only way to see a session's workflow state is to read the
entity directory by hand. This task adds a session view without touching the existing
`regular`/`calm` overviews or any other dashboard surface.

## Proposed approach

{Ideation: a new view mode (e.g., `session`) selectable alongside `regular`/`calm`,
keyed to one session id, rendering (a) a dispatch tree from the session's workflow
entity state — reusing `cargento_runtime/spacedock.py` for the entity/stage/worktree
data and `cargento_runtime/sessions.py` for session identity — and (b) a high-level goal
line derived from the workflow's roadmap/sprint context when the session is a first
officer driving a named sprint, or stated explicitly otherwise. The reference image's
Task Map is the target shape.}

## Risk evidence

{Backlog: confirm the dashboard's view-mode switch (`web/mode.js`) can host a third
mode additively, and that the entity-state data needed for a per-session dispatch tree
is reachable from a single session id without a cross-session scan.}

## Expected surface and tolerance

Estimate: {ideation fills}
Semantics this may change: {ideation fills}

## Acceptance criteria

{Ideation: at least one AC measures the end value — selecting the session view for a
known FO session renders its dispatch tree with the correct entity nodes, edges, and
stages — verified by a test or a live render, and one AC measures the goal line against
a baseline that can move the wrong way (e.g., a sprint goal stated in the workflow
context is shown; a session with no goal shows none, not a fabricated one).}

## Test plan

{Ideation fills.}

### Feedback Cycles

## Out of scope

- Changing the `regular` or `calm` overviews — this task is additive only.
- A new data source: the dispatch tree reuses the existing `spacedock.py`/`sessions.py`
  reads; no new collector or API endpoint for cross-session data.
- Goal inference beyond stated/derived-from-workflow-context — no LLM summarization of
  the session transcript for this task.
