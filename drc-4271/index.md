---
id:
title: 'DEC-7 · Decision: May a walk-away time read as an all-clear on partial coverage?'
status: triage
source: https://linear.app/recce/issue/DRC-4271
started: 2026-08-28T03:48:15Z
completed:
verdict:
score: 0.9
worktree:
issue:
pr:
mod-block:
linear-status: 'Backlog'
milestone: 'Spend attention well'
release: 'r1'
estimate: ''
reconciled:
gates:
    version: 1
    records:
        - id: gate:drc-4271:triage
          stage: triage
          attempts:
            - id: gate-attempt:drc-4271-triage-1
              briefing:
                id: briefing:drc-4271:triage:attempt-1:revision-1
                digest: sha256:4f6a45bae71cbb68387a48cf39223c54f2df00cd07f3fb567124391fcc4354be
                room-ref: ./review/triage/briefing-1
---

[DRC-4271](https://linear.app/recce/issue/DRC-4271) — Linear priority Medium, no estimate. Filed
2026-08-28 by this workflow's own DRC-4029 cycle.

**Release row `r1` is inherited, not labelled.** The issue carries no `release:*` label. `burndown`'s
rule for an unlabelled item is to give it the earliest release row among the issues it settles, and
it settles DRC-4029 — the board's only `release:r1` item, now parked at `blocked` behind exactly this
decision. So its effective row is `r1`, and `score: 0.9` reflects that inheritance rather than a
label. Anything that re-derives the row must re-derive it from the `blocks` edge, not from this
field.

The authoritative body lives in Linear.

## Problem

### The question, in one sentence

**May Cargento publish a single walk-away clock time whose plain reading is "everything will be
done by then", when the coverage that licenses that reading is partial?**

The captain rules on that sentence. Everything below exists to make it answerable.

### The framing correction this triage had to make first

DEC-7's body was written on 2026-08-28 by this workflow's own DRC-4029 cycle. Re-derived against the
code and the live stores, **its central question is posed on the wrong axis**, and the two readings
it offers ("D5 was cancelled for the promise" vs "for the coverage") share a false premise.

D5's absent signal was **needs-input detection** — the row "nothing is currently blocked" in
DRC-4028's own table. D6's partial coverage is **ETA coverage**. These are different signals.
DEC-7 asks whether "information present but partial" differs from "information absent", which is
only a meaningful question if it is the *same* information. It is not.

This matters because it decides what "publishing the coverage beside the time" buys. An all-clear
is a claim about **demands on your attention**. Publishing *ETA* coverage beside the number
discloses nothing about the claim the reader is actually relying on. A reader told "3:40, covering
4 of 6 sessions" has learned how many turns carry an estimate; they have not learned whether one of
the rows that cannot report a gate will block at 3:10.

### What the code says (re-derived, not accepted from DEC-7)

Every `file:line` DEC-7 cites resolves and says what it claims. The three load-bearing ones:

| Claim | Verified at | Falsified by |
|---|---|---|
| `turn_progress` publishes no ETA once a turn exceeds its own history | `turns.py:394-407` — `cands = sorted(d for d in history if d >= elapsed)`; empty ⇒ `"eta_h": None` | history drawn from a global rather than per-session pool, or the empty branch publishing a figure |
| The only flag a working row can carry is `long turn`, at 900 s | `config.py:444` (`long_turn_warn_sec=900`) + `web/calm.js:76-90`, whose comment reads "No third flag" | a third `flag =` assignment on a `st === "work"` row, or a different threshold |
| No numeric ETA is published; `eta_h` is a formatted string floored to whole minutes | `sessions.py:94-104` (`fmt_duration`), used at `turns.py:399` | a numeric field in the payload |

Two smaller ones also hold: the ask card publishes `age_sec` and no deadline (`aggregate.py:619-628`),
and `turn_progress` returns `None` outright for any non-`working` session (`turns.py:388`).

One correction to the mechanism, not the conclusion. DEC-7 says the rows without an ETA "are the
rows running longest". The excluded set is broader: it is every non-working row, every row whose
turn outruns its **own session's** history, **and every session on its first turn**, which has no
history at all and may be short. The bias direction survives — measured below — but the mechanism is
not purely "the longest rows".

### What reproduced, what did not

**The turn distribution reproduced.** DEC-7 measured 94 turns across 11 sessions once. I re-ran the
runtime's own scanner (`turns.scan_turns`) over the live Claude store across five independent
slicings, 124 to 558 turns:

| Slice | turns | median | p75 | p90 | p95 | ≥10m | ≥20m |
|---|---|---|---|---|---|---|---|
| DEC-7's claim | 94 | 2m03s | 5m50s | 11m22s | 15m17s | 15% | 3% |
| modified ≤24h | 124 | 2m33s | 5m40s | 11m41s | 14m38s | 15% | 3% |
| modified ≤72h | 215 | 2m03s | 5m15s | 11m05s | 13m00s | 13% | 2% |
| modified ≤7d | 375 | 2m21s | 5m29s | 11m24s | 16m37s | 13% | 4% |
| 150 most recent | 558 | 2m05s | 5m29s | 12m20s | 16m54s | 15% | 4% |

Median, p90, ≥10m and ≥20m all land on DEC-7's figures. p75 came out 5m15s–5m40s against its 5m50s,
and p95 straddles its 15m17s. **The conclusion that rests on this — half of all turns finish inside
two minutes, so the minimum is useless — is robust and I am willing to stand behind it.**

**The coverage figure did not reproduce, and it understated coverage badly.** DEC-7's "one live
collect: two working sessions, one carrying an ETA" is n=1 and should not have been load-bearing.
Replaying `turn_progress`' own rule over every turn (an ETA exists at elapsed *e* iff some prior
turn ≥ *e*, so a turn is covered only on `[0, max(history)]`):

- **80%** of turns carry an ETA at the moment they end (77% over 24h, 80% over 558 turns).
- **64–71%** of working wall-clock is covered by an ETA.

So coverage is roughly four rows in five, not one in two.

**But the bias is far worse than DEC-7 claimed, and this is new measurement neither issue had:**

- Uncovered turns are **4–5× longer** than covered ones: median 7m56s vs 2m05s, mean 11m15s vs
  3m34s (n=558).
- Of the **slowest 10%** of turns, fewer than half carried an ETA when they ended (23 of 55).

**And the statistic D6 would actually publish is wrong, in the direction that destroys its own
value.** Simulating the maximum over 362 sampled instants that had ≥2 working sessions:

| concurrent working sessions | full coverage | published max is EARLIER than the truth | median understatement | p90 | worst |
|---|---|---|---|---|---|
| k = 2 | 30% | 69% | 2m40s | 15m34s | 27m20s |
| k = 3–4 | **0 of 82** | 87% | **9m50s** | 16m28s | 20m40s |
| all k ≥ 2 | 23% | 74% | 3m05s | 15m34s | 27m20s |

**"Nine of ten harnesses" is stale.** DEC-7 and the milestone both repeat D5's figure. Four
harnesses now set `reports_needs_input=True` — Claude, Codex, Copilot, Cursor (`aggregate.py:252,
266, 302, 322`), landed in `131ba49` (DRC-4184, 2026-08-23), `57eaf7e` (DRC-4201) and `2357af3`
(DRC-4202, both 2026-08-24). It is **six of ten**, not nine. Falsified by a `grep -c
'reports_needs_input=True' cargento_runtime/aggregate.py` returning anything but 4.

That has a consequence nobody has recorded: **D5's own stated reopening condition — "a harness other
than Claude starting to report needs-input state" — has been met three times**, the day after it was
cancelled.

### Does the D5 precedent settle it?

Checked against DRC-4028's own text rather than DEC-7's summary of it. Three things the summary
misses:

1. **D5's recorded reasons are explicitly ranked, and the weightiest is neither the promise nor the
   coverage.** "Three reasons, in order of weight" opens with *"**D6 already exists and the board
   prefers it.** DRC-4029 is the narrower version that stays honest without any wedge detection, and
   it is the last Release 1 item left on the board."* Reasons 2 and 3 are the r2-gated-on-r3
   sequencing contradiction and its own low scores. The "no information at all" passage DEC-7 quotes
   sits in the *gate diagnosis*, not among the ranked reasons.

2. **The record already concedes the honesty of the coverage-scoped version, and rejects it on
   value.** Verbatim: *"The alternative to cancelling is re-scoping to a scoped all-clear: clear for
   N minutes among the sessions whose state Cargento can actually determine, naming the covered set
   on screen. **That is honest**, and it is a materially different and less appealing product than
   the one scored, because the reader has to hold in their head which of their sessions the promise
   excludes."* So on the honesty axis the precedent points at *Yes*; it rejected that option because
   it is worth less, not because it lies.

3. **D5's blessing of D6 was conditional, and the condition is exactly this question.** D6 was
   preferred because it *"delivers the walk-away behaviour **without claiming safety**"*. A D6 that
   reads as an all-clear is claiming safety, and is therefore D5 rebuilt — no longer the item D5's
   cancellation reasoning pointed at.

**So: the precedent does not settle the question as DEC-7 posed it, because DEC-7 posed it on the
wrong axis. Re-posed on the right axis, it constrains the answer tightly.** D5 says a scoped
promise is honest but low-value, and it says D6 earns its place only by not claiming safety. Both
point the same way.

## Proposed approach

### The three answers, with costs and what each forecloses

**1 · Yes, with the coverage published beside the time.**

- *Costs:* D6 builds at roughly its scored size (XS, build 15), with the frontend half in
  `cargento_runtime/web/`, which allows one in-flight PR at a time.
- *What it forecloses:* it re-makes D5's promise while disclosing the wrong quantity. The published
  ETA coverage says nothing about the six of ten harnesses that cannot report a gate, which is the
  coverage an all-clear actually rests on.
- *What the measurement adds:* the number it would publish is earlier than the truth 74% of the
  time, by a median of 9m50s once three sessions are running. So the disclosure would sit beside a
  figure that is unreliable in the direction that erodes the value it was scored for — "supports
  pre-committing to a 20 minute errand" — while 3% of turns exceed twenty minutes anyway.

**2 · No.**

- *Costs:* the "Spend attention well" group keeps no buildable walk-away item. All three candidate
  statistics are now refused with numbers attached, so a No most likely sends DRC-4029 to
  cancellation or a re-scope.
- *Second-order cost, and the captain should see it:* D5's weightiest cancellation reason was "D6
  exists and the board prefers it". Cancelling D6 removes that reason retroactively, which is a
  reason to look at D5 again — and D5's stated reopening condition has already been met.
- *What it forecloses:* nothing permanent. The same product becomes available once needs-input
  coverage is broad enough, which is B2's live queue (DRC-4014, In Progress, seven children).

**3 · Only at full coverage.**

- *This one is now refuted rather than open.* Full ETA coverage across every working row held at
  23% of sampled instants, and **0 of 82** at three-to-four concurrent sessions — precisely the
  parallel-worktree load `AGENTS.md` calls normal here.
- *Costs:* the whole feature gets built and then essentially never renders.
- *What it forecloses:* it is non-delivery dressed as honest refusal. It also fails silently, which
  is the failure mode the `fastest` ordering's convention exists to refuse.

### Recommended answer: **No**

A walk-away time may not be published in a form whose plain reading is an all-clear. Three reasons,
in order of weight:

1. **The disclosure does not cover the claim.** An all-clear is a claim about demands on attention.
   That claim rests on needs-input coverage, which is four harnesses of ten. Publishing ETA coverage
   beside the number discloses a different quantity, so answer 1 does not actually mitigate the risk
   it is designed to mitigate.
2. **Even the narrow completion claim is unreliable.** 74% of the time the published maximum is
   earlier than the true last completion; at three or four sessions it is 87% of the time by a
   median of 9m50s.
3. **The precedent, read on its own text, already weighed this trade and came down against.** D5
   conceded the scoped promise is honest and rejected it as "materially different and less
   appealing". Nothing measured here improves that; the new numbers make it worse.

**"No" is narrower than "cancel D6", and this stage should not conflate them.** The narrow claim
DRC-4029 already settled — *the soonest expected completion among turns we can estimate*, coverage
beside it, never "the soonest moment anything will want you" — is not an all-clear and is untouched
by this ruling. What this triage establishes is that none of the three measured statistics can carry
even that narrow claim. Whether DRC-4029 is therefore re-scoped or cancelled belongs to its own
cycle, once this decision releases it.

### What is already settled and is not being reopened

- Whatever ships is *the soonest expected completion among turns we can estimate*, with coverage
  published beside it — never "the soonest moment anything will want you". Settled 2026-08-23.
- D4 shipped in 0.6.x and covers unpredictable arrivals. That is why the narrow claim is enough.
- The `ask_operator` deadline is not an input to this number. Settled 2026-08-28 and confirmed here
  at `aggregate.py:619-628`.

### One thing to file separately, not to decide here

**D5's reopening condition has been met.** DRC-4028 says it reopens when "a harness other than
Claude starts to report needs-input state"; three did, on 2026-08-24. Neither DRC-4028, DRC-4271 nor
the milestone records this. It belongs on the board whichever way this decision goes, and it is a
separate filing rather than a widening of this issue.

## Linear edits made

**Nothing has been written to Linear. This gate authorizes that write.** Recorded here as the
pre-edit state.

### Original DRC-4271 body — captured verbatim 2026-08-28

> ## The question
>
> D6 wants to publish one clock time a reader can leave the desk on. Triage measured the three candidate statistics the 2026-08-23 review listed and refused all three. What remains is a question about what this product is willing to promise:
>
> **May Cargento publish a single walk-away time whose plain reading is "everything will be done by then", when it knows its coverage is partial and biased toward the fast half of the board?**
>
> ## Why it cannot be settled by an engineer
>
> The statistic that delivers the value and the statistic that is honest are different statistics.
>
> * The **minimum** — the soonest completion among estimable turns — never implies an all-clear, and is useless here. Measured 2026-08-28 over 94 recent turns across 11 sessions: median turn 2m03s. With more than one or two estimable sessions the answer is always "now".
> * The **maximum** — the soonest moment nothing would still be running — is the only candidate that scales with the board. It is also biased optimistic by construction: `turn_progress` publishes no ETA for a turn that already exceeds every past turn, so the rows the maximum cannot see are the rows running longest. And "everything will be done by 3:40" is an all-clear however it is worded, read as one by someone who then leaves.
>
> ## Why the existing precedent does not answer it
>
> D5 (DRC-4028, *Nothing needs you for the next N minutes*) was cancelled on 2026-08-23 for stating the all-clear outright. The recorded reason was that on nine of ten harnesses it would have promised freedom **on no information at all** — an absent signal, not a weak one.
>
> Here the information is present but partial and skewed. Read one way, D5's cancellation was about the coverage and this case is genuinely different. Read the other, it was about the promise itself and coverage is only how it got caught. Both readings fit the record.
>
> ## What each answer costs
>
> * **Yes, with the coverage published beside the time.** D6 becomes buildable at roughly its scored size. The risk is that a reader treats a partial figure as complete, which is the failure D5 was cancelled to avoid, now on stronger data instead of none.
> * **No.** D6 ships the minimum with the coverage line, is honest, and says "come back now" at this repository's normal load — which is not the value it was scored for. Or D6 is cancelled and this group's outcome stays empty until a harness other than Claude reports needs-input state (B2), which is also what would reopen D5.
> * **Only at full coverage** — publish nothing unless every working session carries an estimate. On the one collect measured, coverage was 1 of 2, so the number would have been suppressed. This is a third answer and it should be chosen deliberately rather than arrived at.
>
> ## What is already settled and not being reopened
>
> Whatever ships is *the soonest expected completion among turns we can estimate*, never "the soonest moment anything will want you", with the coverage published beside it. D4 shipped in 0.6.x and covers unpredictable arrivals. That narrowing was settled 2026-08-23 and this decision does not disturb it.

### Drafted rewrite of DRC-4271 — for `implementation` to write once the captain rules

The body above is superseded but **demoted, not deleted**: `implementation` keeps it under a
`## History` heading dated *2026-08-28 — as filed, before the evidence was re-derived*, and writes
above it the captain's ruling plus these corrections, which stand regardless of which way the ruling
goes:

- The question is re-posed on the needs-input axis, with the note that ETA coverage and needs-input
  coverage are different quantities and that the original framing conflated them.
- "nine of ten harnesses" → **six of ten**, cited to `aggregate.py:252, 266, 302, 322` and to
  DRC-4184 / DRC-4201 / DRC-4202.
- "On the one collect measured, coverage was 1 of 2" → replaced by the replayed figures (80% of
  turns, 64–71% of wall-clock) and marked as superseding an n=1 observation.
- The maximum's bias becomes measured rather than asserted: uncovered turns run 4–5× longer, and the
  published maximum is early 74% of the time.
- Answer 3 is recorded as **refuted**, with "0 of 82 instants at k=3–4" attached.
- The D5 precedent section is rewritten around DRC-4028's ranked reasons and its "that is honest"
  sentence.

### Original milestone description — the only section this triage falsifies, captured verbatim

The "Spend attention well" description carries four dated updates. Three are untouched. Only the
2026-08-28 update contains claims this triage falsifies; its second and third paragraphs verbatim:

> **What was measured.** 94 recent turns across 11 sessions, on a machine running the parallel-worktree load `AGENTS.md` calls normal here: median turn **2m03s**, p75 5m50s, p90 11m22s, p95 15m17s. 15% of turns reach ten minutes, 3% reach twenty. One live collect at the same moment: two working sessions, one ETA between them.
>
> **Which leaves the decision, and it is a product decision rather than an engineering one.** The useful statistic is the one whose plain reading is an all-clear; the honest ones say "come back now". D5 was cancelled for promising freedom on absent information. Here the information is present but partial and biased, which is a different case, and the precedent does not settle it either way. That question is filed as a decision issue blocking D6.

### Drafted milestone correction

Replace those two paragraphs only, leaving every other section of the milestone alone (the
`docs-synced-through`-style hazard applies: this is a shared surface and other branches append to
it):

- The distribution paragraph keeps its figures — they reproduced — but gains the larger sample
  (558 turns across five slicings) and drops "One live collect… one ETA between them" in favour of
  the replayed coverage figures.
- The decision paragraph loses "the precedent does not settle it either way". Replace with: the
  precedent settles more than was thought, because DRC-4028's ranked reasons put "D6 already exists
  and the board prefers it" first and explicitly concede that a coverage-scoped promise "is honest",
  rejecting it on value; and because ETA coverage is not the coverage an all-clear rests on.
- Add one sentence recording that needs-input detection reached four harnesses on 2026-08-24, so
  D5's stated reopening condition has been met.

## Expected surface and tolerance

This stage's product is a decision, so the surface is records rather than code. Expected:

| Surface | Change | Tolerance |
|---|---|---|
| DRC-4271 body | rewritten, prior body demoted to dated history; issue closed by `implementation` | ±1 issue |
| DRC-4029 | unblocked and moved per the ruling | exactly 1 |
| "Spend attention well" milestone | two paragraphs of the 2026-08-28 update replaced | ±1 paragraph |
| New issue: D5's reopening condition met | filed, linked to DRC-4028 and DRC-4014 | 0 or 1 |

**No code changes are expected from this issue.** Semantics that may move: none. If the ruling is
Yes, the code change belongs to DRC-4029's cycle and lands in `cargento_runtime/web/` plus a new
published numeric field — one in-flight PR at a time on that directory.

## Acceptance criteria

**Offline** (a fresh agent reproduces these without a human):

1. `grep -c 'reports_needs_input=True' cargento/skills/cargento/cargento_runtime/aggregate.py`
   returns `4`. *Verified by:* the command. Falsified if a fifth harness lands, which would further
   weaken the "absent signal" reading and should reopen this decision rather than be absorbed.
2. `long_turn_warn_sec=900`, and the whole working-row flag vocabulary is one literal.
   *Verified by:* `grep -n 'long_turn_warn_sec=' config.py` returns `444`;
   `grep -c 'flag = "' web/calm.js` returns `2` (`your call` for a blocked row, `long turn` for a
   working one) and `grep -c 'st === "work" && turn && turn.long' web/calm.js` returns `1`.
   Falsified by either count rising — which is what "exclude anything flagged" would need in order
   to be anything but a no-op.
3. `turns.turn_progress` returns `eta_h is None` for a scan whose `durations` are all shorter than
   `elapsed`. *Verified by:* a direct call with a synthetic scan; asserts the optimistic-bias
   mechanism itself, and fails if the empty-`cands` branch ever publishes a figure.
4. The probes behind the tables above re-run and land within the stated ranges. *Verified by:*
   `drc-4271/probe_distribution.py`, `probe_coverage.py`, `probe_max_error.py`, committed beside
   this entity with a README; run from `cargento/skills/cargento`. **Declared machine dependency:**
   they read the live `~/.claude/projects` store, so the *numbers* are this machine's and the
   *method* is portable — another machine re-derives its own. Deliberately not committed as unit
   tests: a test pinned to one machine's session history asserts the fixture, not the behaviour.

**Interactive** (needs the captain):

5. The ruling itself. *Verified by:* the captain's answer at this gate. There is no offline proof of
   a product decision, and no harness should be built to manufacture one.
6. That the drafted milestone correction reads as intended prose. *Verified by:* human review at the
   gate; the voice standard is not machine-checkable.

## Test plan

No code changes, so no test changes. The claims above are held by the four offline checks in the
acceptance criteria rather than by new unit tests; adding a test that pins this machine's turn
distribution would assert the fixture rather than the behaviour, which is the failure
`docs/visibility-2x2` and the Cursor workspace defect both record.

## Review depth

_Chosen at review._

### Feedback Cycles

## Out of scope

- **Designing D6's build.** Whether DRC-4029 is re-scoped or cancelled is its own cycle, once this
  decision releases it.
- **Reopening D5.** Noted above as a separate filing, deliberately not actioned here.
- **B2's per-harness queue.** Four of ten now report needs-input; the remaining six are DRC-4185
  through DRC-4191 and are not this issue's work.
- **`docs/visibility-2x2/items.json`.** Valid for scores only; its `state` fields are deliberately
  stale and were not read as current.

## Stage Report: triage

- DONE: The question is stated in ONE sentence the captain can rule on, followed by each available answer with what it costs and what it forecloses, and ONE recommended answer with the reason.
  One-sentence question opens `## Problem`; the three answers with costs/foreclosures and the recommendation (**No**) are in `## Proposed approach`.
- DONE: The load-bearing evidence is re-derived from the code and from live stores rather than accepted from DEC-7's own body.
  Three probes committed at `drc-4271/`; every `file:line` DEC-7 cites was opened and resolved.
- DONE: re-check that `turn_progress` publishes no ETA for a turn exceeding its own history (the optimistic-bias claim), naming what would falsify it.
  Confirmed `turns.py:394-407`; exercised by direct call — history `[60,120,180]` at elapsed 600 returns `eta_h None`, at elapsed 60 returns `1m`. Falsified by a global rather than per-session history pool, or by the empty-`cands` branch publishing a figure.
- DONE: re-check that the only working-row flag fires at 900s.
  `config.py:444` is `long_turn_warn_sec=900`; `grep -c 'flag = "' web/calm.js` = 2 and only one is reachable from `st === "work"` (calm.js:76, comment "No third flag"). Falsified by either count rising.
- DONE: re-check the turn-duration distribution that makes the minimum useless.
  Reproduced across five slicings, 124–558 turns: median 2m03s–2m33s, p90 10m55s–12m20s, ≥10m 12–15%, ≥20m 2–4%. Falsified by a median above ~4m, which would make the minimum a usable time.
- DONE: Report any figure you could not reproduce rather than repeating it.
  Two reported as not reproduced: **"coverage was 1 of 2"** (n=1; replay over 558 turns gives 80% of turns / 64–71% of wall-clock) and **"nine of ten harnesses"** (stale — four now report needs-input, `aggregate.py:252,266,302,322`, landed `131ba49`/`57eaf7e`/`2357af3`). p75 5m50s and p95 15m17s reproduced only approximately and are flagged as such.
- DONE: Whether the D5 precedent settles the question, checked against DRC-4028's own recorded cancellation reason rather than against DEC-7's summary of it.
  It does not settle it *as posed*, because DEC-7 conflates ETA coverage with needs-input coverage. Re-posed, it constrains tightly: DRC-4028's ranked reasons lead with "D6 already exists and the board prefers it", and it explicitly concedes a coverage-scoped promise "is honest", rejecting it on value.
- DONE: Nothing is written to Linear, and the decision is NOT recorded as made.
  No Linear write tool was called; all rewrites are drafts under `## Linear edits made`, and `## Proposed approach` recommends without ruling.
- DONE: Do not widen scope into designing D6's build.
  `## Out of scope` parks the re-scope/cancel question in DRC-4029's own cycle.

### Summary

The document under audit was our own, and two of its load-bearing figures did not survive contact
with the stores. Its coverage evidence was a single collect showing 1 of 2; replaying
`turn_progress`' rule over 558 turns puts coverage at 80% of turns — much better than claimed. Its
"nine of ten harnesses" is stale: four harnesses report needs-input as of 2026-08-24, which also
means **D5's own stated reopening condition has already been met** and nobody has recorded it.

The deeper finding is a framing error. DEC-7 asks whether "partial information" differs from D5's
"absent information", but D5's absent signal was needs-input detection while D6's partial coverage
is ETA coverage — different quantities, so publishing the second discloses nothing about the first.
New measurement makes the choice concrete: the maximum D6 would publish is earlier than the truth
74% of the time (median 9m50s at three or four sessions), and full ETA coverage held at 0 of 82
instants at that load, which refutes the "only at full coverage" answer outright.

Recommendation is **No**, narrower than "cancel D6". The captain should also see the second-order
cost: D5's weightiest cancellation reason was that D6 exists and the board prefers it.
