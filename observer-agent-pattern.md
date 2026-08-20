---
title: Observer agent pattern beside an active session
status: backlog
source: captain seed
id: f8p2czcsjwr53v167t1akbvj
---

An active coding session (a first officer, or any long-running agent) accumulates context
a bystander cannot easily recover: what it set out to do, what it decided, where it got
stuck, what it is doing right now. An observer agent — a separate agent that sits beside
an active session, reads its transcript read-only, and derives its goal and the
important things (decisions, blocks, in-flight work) — would let an operator (or another
agent, or a dashboard) ask "what is this session for and what matters in it right now?"
without interrupting the session or relying on the session's own self-report.

## Problem

There is no pattern for an agent that passively observes another active session and
produces a durable, queryable summary of its goal and salient facts. The session's own
transcript is the raw material, but it is long, unstructured, and interleaved with tool
noise. Cargento already reads session transcripts read-only (the collectors), and
Spacedock already derives workflow state from durable files — but neither derives a
goal/salience summary from a live transcript. This task designs the observer pattern:
where it reads, what it derives, how it stays read-only, and how its output is consumed
(by Cargento's session view, by an operator, by another agent).

## Proposed approach

{Ideation: the observer is a read-only agent (no mutation of the observed session's
repo or state) that reads the observed session's transcript via the same bounded,
freshness-windowed reads Cargento collectors use, derives a goal line (from the session's
opening directive, its workflow/roadmap context, or its in-flight entity titles) and a
salience set (decisions, blocks, current stage, open findings), and writes its output to
a durable sidecar (a file the session view reads). Decide: is the observer a dispatched
ensign, a standing background agent, or a Cargento-side analyzer in `transcripts.py`?
The riskiest mechanism is deriving a goal that is not fabricated when the transcript
carries none — exercise that first.}

## Risk evidence

{Backlog: confirm a read-only agent can read another session's transcript without
joining it (intercom/subagent read vs. transcript file read), and that the "derive a
goal, do not fabricate one" failure mode is exercisable before building.}

## Expected surface and tolerance

Estimate: {ideation fills}
Semantics this may change: {ideation fills}

## Acceptance criteria

{Ideation: at least one AC measures the end value — an observer attached to a known
session produces a goal line and salience set that match the session's actual stated
objective and in-flight work, verified by a live scenario with a negative case (a
session with no stated goal produces "no goal derived", not a hallucinated one). One
AC proves the observer never mutates the observed session's repo/state.}

## Test plan

{Ideation fills.}

### Feedback Cycles

## Out of scope

- Making the observer write to the observed session's workflow state — it is read-only
  by design; its output is a sidecar, not entity state.
- Replacing Cargento's existing collectors — the observer is a new pattern, not a
  refactor of `collectors/*.py`.
- Real-time streaming — this task designs the derive-and-write pattern; live streaming
  of the observer's output is a follow-up.
