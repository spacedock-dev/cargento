---
title: Pi agent view shows Spacedock state
status: backlog
source: captain seed
id: a7674hm6a9stycspp7ramje7
---

Cargento already derives Spacedock workflow cartography for Claude first officers —
`collectors/claude.py` decides a session is a first officer from its transcript's
`agentSetting`, then asks `cargento_runtime/spacedock.py` for the workflow strip
(entity directory, per-entity `status` stage, live-worker attribution). The Pi
collector (`collectors/pi.py`) does not yet surface this, so a Pi first officer driving
a Spacedock workflow renders on the dashboard without the workflow context a Claude
officer gets.

## Problem

A Pi first officer running `spacedock pi` writes the same durable state a Claude officer
does (entity files under the workflow's state checkout, `spacedock-ensign-<slug>-<stage>`
worker names), and Cargento's Spacedock parser is harness-agnostic, but the Pi collector
never calls it. So the dashboard's session card for a Pi FO omits the "where is each work
item on its workflow" strip that the design (`docs/design-spacedock.md`, S-1..S-4) exists
to provide — the sessions that most need it (long-lived Pi officers taking work in via
intake) show `dispatchable: []` and nothing else.

## Proposed approach

{Ideation: how `collectors/pi.py` classifies a Pi session as a first officer (the Pi
equivalent of Claude's `agentSetting` marker) and where the `spacedock.read_workflow`
strip plugs into the Pi collection lane, reusing the existing harness-agnostic parser
rather than duplicating it.}

## Risk evidence

{Backlog: the check that decides whether design should start — confirm a Pi FO
transcript carries a discoverable first-officer marker and that `spacedock.py`'s
`entity_dir`/`dispatchable` inputs are reachable from Pi session metadata.}

## Expected surface and tolerance

Estimate: {ideation fills}
Semantics this may change: {ideation fills}

## Acceptance criteria

{Ideation: at least one AC measures the end value — a Pi FO session on the dashboard
shows the same workflow strip a Claude FO session does — against a baseline that can
move the wrong way, verified by a test or a live scenario, not by a grep over
`pi.py` or this README.}

## Test plan

{Ideation fills.}

### Feedback Cycles

## Out of scope

- Rewriting `spacedock.py` — it is harness-agnostic by design (S-2); this task wires
  the Pi collector to it, it does not change the parser.
- Adding new Spacedock cartography features (entity titles, verdicts, scores) — S-4
  deliberately takes only the stage; this task does not widen that.
