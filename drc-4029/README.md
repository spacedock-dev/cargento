# DRC-4029 (D6) — triage cycle 2 evidence probe

One read-only probe behind the ceiling table in `index.md`. It answers the question the DEC-7 ruling
left open: whether **any** statistic the ruling permits can produce a walk-away time.

Run from the skill root so `cargento_runtime` imports:

    cd cargento/skills/cargento
    python3 <path>/probe_min_lead.py

## What it measures, and why the oracle column is the point

Every statistic the ruling permits promises *nothing you can predict will be ready before X*. That
is sound only if X is no later than the true soonest completion, so the true soonest completion is a
hard ceiling on the whole family. The probe reports two minima at each sampled instant:

- **published** — the minimum over rows `turn_progress` can estimate. What D6 would ship today.
- **oracle** — the minimum over the *true* completion of every live turn, covered or not. What a
  perfect estimator with total coverage would publish, so it bounds every possible improvement.

A short oracle lead refutes the whole family at once, rather than one candidate at a time.

The final block measures the strongest candidate the ruling leaves open — publish the minimum only
when it is at least T minutes out — and reports both how often it would render and how often reality
beat it when it did.

## Falsifiers

- **The ceiling.** The k ≥ 2 oracle `>=20m` share rising above roughly 10% falsifies the
  cancellation and reopens the item; it is the reopening condition the drafted issue body names.
- **The suppression rule.** A render rate above a few per cent at T = 20m, or a wrong rate that
  falls as T rises, falsifies "rare and wrong".
- **The mechanism.** If `turn_progress` stops drawing history per session, or publishes a figure for
  a turn that outruns its own history, the reconstruction here no longer models the shipped code.

## Machine dependency, declared

It reads the live `~/.claude/projects` store, so **the numbers are this machine's and the method is
portable** — another machine re-derives its own. That is why this is not committed as a unit test: a
test pinned to one machine's session history asserts the fixture rather than the behaviour.

`intervals()` and the sampling loop are lifted verbatim from `../drc-4271/probe_max_error.py`, and
the seed and exhausted draw stream are the same, so the multi-session instants sampled here are the
same instants that probe measures the maximum over. Keep them identical: if they drift, the minimum
and the maximum are no longer being measured over one set of moments.
