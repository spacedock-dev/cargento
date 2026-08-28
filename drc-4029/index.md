---
id:
title: 'D6 · Come back at 3:40'
status: recorded
source: https://linear.app/recce/issue/DRC-4029
started: 2026-08-28T02:02:06Z
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
estimate: 'XS'
reconciled:
gates:
    version: 1
    records:
        - id: gate:drc-4029:triage
          stage: triage
          attempts:
            - id: gate-attempt:drc-4029-triage-1
              briefing:
                id: briefing:drc-4029:triage:attempt-1:revision-1
                digest: sha256:68bb36cfb18077464006bb4297e358dd61bb4ea0b40c407c6a67b241042bff7a
                room-ref: ./review/triage/briefing-1
              resolution:
                type: Resolution
                id: resolution:spacedock:drc-4029:triage:1
                briefing: briefing:drc-4029:triage:attempt-1:revision-1
                by: person:captain
                at: "2026-08-28T02:21:48.709319Z"
                decision: approve
                reason: 'Captain approved at the triage gate. Accepts the direction: escalate rather than build. The refusal of all three candidate statistics rests on code and measurement rather than argument — turns.py:386 and config.py:444 make candidate 1 a no-op plus a regression, turns.py:402-406 makes the maximum optimistically biased by construction, and 94 sampled turns (median 2m03s) confirm the minimum useless. Zero repository files changed against a zero-file expected surface. Acceptance criteria are absent by contract, not omission, confirmed by --ac-scan returning []. Authorizes the four drafted Linear writes; nothing had been written to Linear at decision time.'
              application:
                target-stage: implementation
                state: consumed
---

[DRC-4029](https://linear.app/recce/issue/DRC-4029) — Linear priority Medium, estimate XS.

The authoritative issue body lives in Linear and is deliberately not copied here: a copy taken at
commission time would be a second, staler statement of the problem, and this workflow exists partly
because stale statements of a problem get built. `triage` fetches it live, reviews it adversarially
against the current codebase, and writes the sharpened version back to Linear.

## Problem

A reader watching a dozen sessions has a dozen ETAs and no way to turn them into one decision: can I
leave the desk, and until when. D6 proposes one clock time computed over the per-turn estimates the
dashboard already renders.

**Triage's finding is that the issue cannot be built as written, and the obstacle is a product
decision nobody has filed.** The 2026-08-23 body says so itself — *"That is not a presentation
problem, it is the wrong statistic. Settle it before building"* — and lists three candidates without
choosing. Measuring the three against this repository's own stores does not choose between them
either. It shows that the two honest candidates are useless here and the useful one is the promise
D5 was cancelled for making.

### What was measured, 2026-08-28

One real collect against this machine's live stores, plus the recent-turn history behind every ETA
on it (`state.turn_scan`, which is where `turns.scan_turns` caches each session's last 50 turn
durations). 94 turns pooled across 11 sessions:

| | value |
|---|---|
| median turn | 2m03s |
| p75 | 5m50s |
| p90 | 11m22s |
| p95 | 15m17s |
| longest single recent turn | 68m |
| turns ≥ 10m | 14 of 94 (15%) |
| turns ≥ 20m | 3 of 94 (3%) |

At the moment of the collect: 2 working sessions, **1 of which carried an ETA**. Coverage 50%, on a
box running the very parallel-worktree workload `AGENTS.md` calls normal here.

### What that does to each candidate

`turn_progress` (`cargento_runtime/turns.py:380-406`) estimates a turn's total as the **median of
that session's past turns that lasted at least as long as the current one has so far**. So every
published ETA is bounded above by the session's own recent history. With a median turn of two
minutes, that bound is tight.

* **The minimum** — the issue's own prediction is confirmed rather than asserted. Half of all turns
  finish inside 2m03s, so with more than one or two estimable sessions the soonest completion is
  almost always a couple of minutes out. "Come back at 3:40" becomes "come back now", permanently.
* **Candidate 1, "exclude any already blocked or already flagged", is half a no-op and half a
  regression.** `turn_progress` returns `None` outright unless `session_state == "working"`
  (`turns.py:386`), so blocked sessions are *already* excluded and removing them changes nothing.
  The only flag a working row can carry is `long turn` (`web/calm.js:70-76`), raised from
  `turn.long`, which fires at `long_turn_warn_sec = 900` (`config.py:444`). Excluding flagged rows
  therefore excludes every turn past 15 minutes — the only rows capable of producing a time worth
  walking away on. It lowers the minimum instead of raising it.
* **Candidate 2, a later quantile,** is unstable in the thing it is meant to fix. Over two estimable
  rows a p75 is nearly the maximum; over twelve it is a different promise entirely. A number whose
  meaning changes with how many sessions happen to be running cannot be written on a calendar, and
  it has no one-sentence reading — which is the entire product here.
* **Candidate 3, "the soonest completion that would leave nothing running"** — the maximum over
  estimable turns — is the only one that scales the right way, and it fails for two reasons the
  board has not recorded. **First, it is biased optimistic by construction:** `eta_h` is `None`
  exactly when the current turn already exceeds every past turn (`turns.py:402-406`), so the rows
  with no estimate are precisely the ones running longest. The maximum is taken over the fast half
  of the board and presented as the slow end of it. **Second, and this is the finding that blocks
  the issue:** "everything will be done by 3:40" *is* an all-clear, whatever the wording, and it is
  read as one by a person who then leaves. D5 was cancelled six days earlier for stating exactly
  that on absent information.

**So the useful statistic is the one that reads as an all-clear, and the honest ones are the ones
that say "come back now".** That is not an implementation choice.

### Two other corrections triage owes the record

* **The ask deadline is not the better input the issue claims.** It exists — `ask_deadline_sec =
  300.0` (`config.py:516`), swept against `ask.created` — but it is a deadline *for the reader to
  answer*, not an estimate of when work finishes. It bounds an errand from above ("be back by
  3:05"); D6's number bounds it from below. Mixing the two into one figure puts two units in one
  number, which is the ledger-column error `web/calm.js:200-207` exists to refuse. It is an input to
  the D5-shaped item, not to this one. Separately, the deadline **never reaches the browser at all**
  — the published ask card carries `age_sec` and nothing else (`aggregate.py:619-635`).
* **"Arithmetic over data already on screen" understates the build.** `eta_h` is a *formatted
  string* — `fmt_duration` (`sessions.py:94-104`) floors to whole minutes under an hour — and no
  numeric ETA is published anywhere in the payload. Any statistic must be computed server-side from
  `est_total - elapsed` in seconds and published as a new field. Build 15 is still roughly right in
  size, but it is a runtime change plus a payload field plus a frontend render, and the frontend
  half lands in `cargento_runtime/web/`, which `AGENTS.md` caps at one in-flight PR.

## Proposed approach

**Escalate, do not build.** File one decision issue, link it as a blocker on DRC-4029, and send this
entity back to `selection`. The decision issue asks one question:

> May Cargento publish a single walk-away time whose plain reading is an all-clear, on coverage it
> knows to be partial and biased toward the fast half of the board — six days after D5 was cancelled
> for making that promise on absent information?

The precedent does not settle it either way, which is why it needs the captain rather than an agent.
D5 was cancelled because on nine of ten harnesses it would have promised freedom *on no information
at all*. Here the information is present but partial, and partial is a different case from absent.
Read one way that reopens the promise; read the other, D5's cancellation was about the promise
itself and the coverage was only how it got caught.

**The simplest rejected alternative: ship the minimum with a coverage line and the narrow sentence,
as the 2026-08-23 body proposes.** It is honest, it is small, and it cannot deliver the value. The
only thing that survives D6's own 42-point redundancy penalty against D4 is *"supports
pre-committing to a 20 minute errand"* — and 3% of measured turns reach twenty minutes, while half
finish inside two. The minimum would say "come back now" on almost every load this repository
actually runs. A number that is right and useless is still a card of chrome on every screen.

**The alternative that would make the issue buildable without the decision, and why it is not
proposed:** publish the maximum, but refuse to publish anything at all unless every working session
carries an estimate — turning the coverage bias from a silent error into a visible refusal, which is
the convention `fastest` already sets. On the one collect measured, coverage was 1 of 2, so the
number would have been suppressed. Shipping a figure that blanks itself at normal load is the same
non-delivery as the minimum, arrived at more expensively.

## Linear edits made

**Nothing has been written to Linear.** This section is the pre-edit record plus the drafts the gate
authorizes; `implementation` performs the write as its first action.

### Pre-edit record — captured 2026-08-28

Both captures are verbatim from the live records, fetched this session. The issue body's Linear
`updatedAt` is `2026-08-23T06:03:15.846Z`; the issue carries no comments.

#### Original issue body — DRC-4029 "D6 · Come back at 3:40"

````markdown
Board item **D6**. Reviewed 2026-08-23 after D5 was cancelled, which left this the only walk-away signal on the board and the last Release 1 item.

**Release row:** r1 · **Journey stage:** Mid-flight · **Outcome group:** Spend attention well

## What it is

One clock time instead of twelve ETAs. The soonest moment a turn now running is expected to finish, presented as a time you could write on a calendar.

## What it must not claim, which the original framing did

The board note says "the soonest moment anything will want you". That is not what the data supports and it is the sentence that would make this dishonest.

`turn_progress` yields an ETA only for a session that is **working** and has a past turn at least as long as the current one. So the set it minimises over excludes:

* every **blocked** session, because state must be `working`
* every session whose current turn is already longer than any recent turn, which renders as "running longer than recent turns" with no figure
* every idle session
* a **gate arriving out of nowhere**, which is the single most common thing that actually wants you and has no ETA on any harness

So the honest claim is narrower: *the soonest expected completion among turns we can estimate.* Not the soonest demand on your attention. Ship the narrow sentence, because the wide one is the one that loses trust the first time a permission prompt fires at 3:05.

The mitigation already exists and is why this is still worth building: **D4 shipped in 0.6.x.** Unpredictable demands raise a notification. This item covers the predictable ones, the notifier covers the rest, and neither has to pretend to cover both.

## The flaw that matters most, and it is new

**The minimum degrades to uselessness exactly where this repository works.** With one or two sessions the soonest completion is a useful time. With a dozen working sessions the minimum is almost always a couple of minutes away, so "come back at 3:40" becomes "come back more or less now", permanently, and the signal stops being actionable at precisely the workload `AGENTS.md` calls normal here (several agents in several worktrees at once).

That is not a presentation problem, it is the wrong statistic. Settle it before building. Candidates, none obviously right:

* The soonest completion **among sessions you have nothing else to do about**, excluding any already blocked or already flagged.
* A later quantile rather than the minimum, so one fast session does not set the time for eleven slow ones.
* The soonest completion **that would leave nothing running**, which is a different and arguably more useful promise.

## Say what the number does not cover

Calm mode's `fastest` ordering set the convention: name why a row is unranked rather than sorting unknowns to the bottom as if they were worst. The same problem is sharper here, because a single number hides its own coverage entirely. If six of nine sessions have no estimate, "3:40" is a confident figure resting on three. Publish the coverage beside the time.

## One input this did not have when it was scored

A pending `ask_operator` question carries a real deadline, five minutes by default, after which it declines. That is the only demand on the board with a genuine clock rather than an estimate, and it is a strictly better input than any ETA. The ask lane shipped on 2026-08-23 ([DRC-4172](<https://linear.app/recce/issue/DRC-4172/let-a-session-ask-cargento-a-question-and-wait-for-the-answer-dec-2s>)).

## What to build

The minimum, or whichever statistic the question above settles on, over the per-turn estimates already computed. They render today on every working card as `~Xm left (est)` and drive calm mode's progress bar, so this is arithmetic over data already on screen. That is what build 15 was scored against and it still holds.

## Scores

Impact 65, risk-adjusted 47, access 85, build 15, detector risk 18. Estimate XS. Quadrant marked unsettled, within 5 points of the impact cutoff.

Detector risk 18 now looks low. It was scored against "is the ETA right", and the two findings above are not about ETA accuracy: the statistic may be wrong for the workload, and the number hides its own coverage. Left unchanged as the board's record.

## Redundancy, as scored

A subset of D4 (Notify me when the state changes), which shipped in 0.6.x. Redundancy penalty 42. What survives it: one clock time you can write down or hand to somebody, which supports pre-committing to a 20 minute errand rather than reacting to a ping. Once H2 delivers notifications off the desk, 3:40 will call you and nobody will need to remember it.

## What it assumes, and it is the honest risk

Hand someone a single time to come back and they will leave the desk, so in practice this functions as an all-clear it never states. That gap is where the risk was banked as differentiation. D5 was cancelled for stating the same thing out loud, which makes the gap this item relies on worth naming rather than leaving implicit: the difference is that a wrong time here is an inconvenience, while a wrong all-clear is a broken promise.
````

#### Original milestone description — "Spend attention well"

````markdown
Thematic grouping, not a delivery sequence — sequence by the release:* labels. Outcome group: look away safely. Knowing you are free matters as much as knowing you are needed. Board items in this project: D5, D6, D7, D8, D9, D10, G3, G4, G5, H2 (D1, D2, D3, D4, G1 and G2 already shipped and are excluded), plus three non-board issues.

## Update 2026-08-23 — D5 is cancelled, and D6 is now the only walk-away signal on the board

**D5 is Cancelled** ([DRC-4028](<https://linear.app/recce/issue/DRC-4028/d5-nothing-needs-you-for-the-next-n-minutes>)). The group loses the item that stated the walk-away promise outright, and keeps the one that implies it.

**Why, and it is not the reason the record gave.** D5 was described here and on its own issue as "correctly blocked on C2". That was wrong in a way nobody noticed for three weeks: C2 could never have satisfied it. Wedge detection rests on `records.tool_outcome`, which is Claude-only by construction and stays that way until some other harness records tool failure. So the gate would never have lifted.

The binding constraint was always B2. This item ANDs three inputs, and two of them are Claude-only: nothing is currently blocked (no needs-input detection at all on nine harnesses) and nothing is silently wedged. So on nine of ten harnesses it would have promised the reader is free on the basis of no information. Not a weak signal, an absent one. The gate was re-pointed to B2 to record that, and the item cancelled on the same reasoning: diagnosing the real constraint is what showed it cannot be honest.

What would reopen it: a harness other than Claude reporting needs-input state, which is B2's subject.

**D6 inherits the whole outcome, and its review found two things the board did not.** [DRC-4029](<https://linear.app/recce/issue/DRC-4029/d6-come-back-at-340>) is now the group's only walk-away item and the last Release 1 item anywhere in the project.

* **Its stated claim is wider than its data.** The board note says "the soonest moment anything will want you". `turn_progress` only yields an ETA for a session that is **working** and has a past turn at least as long as the current one, so the minimum excludes every blocked session, every idle one, every turn already longer than its own history, and every gate, which arrives with no ETA on any harness. The honest sentence is *the soonest expected completion among turns we can estimate*. Ship that one. D4 shipped in 0.6.x and covers the unpredictable arrivals, which is why the narrow claim is enough.
* **The minimum degrades exactly at this repository's own workload.** With a dozen working sessions the soonest completion is almost always minutes away, so one clock time becomes "come back now", permanently, at the several-agents-at-once workload `AGENTS.md` calls normal here. That is the wrong statistic rather than a presentation problem, and it wants settling before anyone builds it. Detector risk 18 was scored against ETA accuracy and covers neither finding.

One input D6 did not have when it was scored: a pending `ask_operator` question carries a real five-minute deadline, which is the only demand on the board with a genuine clock rather than an estimate. The ask lane shipped 2026-08-23.

---

## Update 2026-08-21 — D7 and the Cursor defect are both Done

**D7 is Done**, in [spacedock-dev/cargento#134](<https://linear.app/recce/review/featdashboard-order-the-card-view-by-attention-and-mark-two-live-497ff1108b38>). **[DRC-4118](<https://linear.app/recce/issue/DRC-4118/cursor-fix-the-workspace-read-and-publish-subagents-as-children-rather>) is Done**, in [spacedock-dev/cargento#133](<https://linear.app/recce/review/fixcollectors-read-cursors-workspace-from-its-sibling-metajson-and-23885b86becd>).

**D7 was a one-file job on paper and an extraction in practice.** The remaining half was the card view, which had no session ordering at all. Rather than copy calm's comparator into `regular.js`, the build *moved* it: `web/spark.js` now owns `attentionKey` and `attentionSort`, the four comparators moved verbatim, and calm delegates. The evidence that nothing regressed is that the pre-existing calm assertions pass **unchanged** — an unchanged assertion passing proves preservation, an edited one does not.

Two things settled in that build worth carrying: the idle list orders most-recently-active first, and long-turn working cards hoist. The hoist is safe to rank on because `long` **latches** within a turn, so a card moves at most once per turn, which is why the refusal `fastest` makes for token rate does not carry across. The needs-input band is deliberately not sorted client-side, because the server publishes it longest-blocked-first and a second sort would be a second definition of an order `gateQueue` exists to refuse.

**The Cursor defect was worse than filed, and the reason matters more than the fix.** Every Cursor row had read the project name `cursor` since the collector was written, because the six workspace key spellings it tried have **never existed** in the real payload — the value lives in a sibling `meta.json` the collector never opened. [DRC-3963](<https://linear.app/recce/issue/DRC-3963/normalize-project-paths-across-harnesses>) was filed and fixed for this exact symptom and corrected the spellings **against the wrong file**. The collector passed every test it had while reading a field that was never there. That is a fixture-design lesson, not a Cursor one: the tests asserted the code's assumption instead of the store's shape.

Cursor subagents now fold under their parent on `subagentInfo.rootParentAgentId`, an id-to-id edge rather than a heuristic, labelled from `typeName`. That gives Cursor the subagent half of G3 for free. The differing parent/child model test is **synthetic and says so** — `vega` is the only model value present in the live stores, so no measured differing pair was claimed.

**A correction to the historical note below.** It cited `collectors/cursor.py:396-397` as recording that no Cursor row carries a subagent or a subagent model. That citation is now wrong twice: the comment was replaced by #133, and those line numbers are something else entirely. Cursor rows now carry both.

**One interaction between the two PRs, resolved in the merge.** C8's collision marker had a known false positive while Cursor published subagents as peer rows — a parent and its own child, both on a real two-segment label, read as a collision. #133 removes the case, and the merge deleted the caveat from `SKILL.md` and rewrote `spark.js`'s comment to record which change closed it. A stale warning costs a reader more than no warning.

Two small gaps left open on purpose, neither anyone's issue yet: the `◆ N` divider flagged count is asserted nowhere in the suite and documented nowhere in `SKILL.md`. Two defects found and filed instead of fixed in place: [DRC-4164](<https://linear.app/recce/issue/DRC-4164/calmjss-tone-lookup-has-a-dead-fallback-that-bypasses-the-own-guard>) (a dead `CALM_TONE` fallback that bypasses the file's own `own()` guard) and [DRC-4165](<https://linear.app/recce/issue/DRC-4165/the-assembled-page-size-is-pinned-in-two-unlinked-test-files-so-half-a>) (the page size pinned in two unlinked test files — which then bit for real during the C8 build and again in the merge, both times exactly as described).

---

## Status as audited 2026-08-09 (historical; the updates above supersede it on D7, the Cursor citation, D5 and D6)

This group has moved more than the 11% suggests, and two of its remaining items are smaller than their scores imply.

**Shipped since the board.** G3 is Done: the model each session runs on now appears on every card, and on a subagent whose model differs from its parent ([DRC-4050](<https://linear.app/recce/issue/DRC-4050/g3-which-model-each-session-is-running>), implemented by [DRC-4117](<https://linear.app/recce/issue/DRC-4117/show-the-model-on-every-session-card-and-on-a-subagent-whose-model>)). [DRC-4079](<https://linear.app/recce/issue/DRC-4079/pi-sessions-show-which-harnesss-authority-the-session-is-actually>) landed beside it, naming which harness's authority a Pi session is actually spending.

Two corrections:

* **D7 is half finished.** Its "What it needs" is *"Make it the default, and bring it to both display modes"*, and the first half shipped: `web/mode.js:15` sets `calmSort = "attention"`, so the attention sort is calm mode's default already. What remains is the card view alone, which has no session ordering at all — `regular.js` ranks tile rows and the task list, never sessions. One file, and narrower than build 20 implies. *(Done 2026-08-21. It turned out to be four files, because the honest fix was to extract the comparator rather than duplicate it.)*
* **G5 shipped one of its two words.** Health renders as healthy / no-data / collector-error chips (`regular.js:17-25`). Versions are neither shown nor collected anywhere.

Per item, by risk-adjusted impact:

* **H2** (70) — the largest real gap here, confirmed exactly as written: every delivery path requires the user at the machine, and `SKILL.md` records a further gap where idle nudges produce no notification at all on Linux and Windows. It also reopens the local-only question in a **fourth shape** — an outbound push of session state, distinct from DEC-1's read, DEC-2's write into a session, and DEC-3's local file read. No decision issue covers that shape; file one before the work is scheduled.
* **D7** (60) — as above. Release 1, and now a one-file job. *(Done.)*
* **D6** (47) — unshipped, input confirmed present. Reuse the `fastest` ordering's convention for a ranked figure some rows cannot supply, rather than inventing a second one: a single clock time computed over partly-unknown ETAs fails silently otherwise. *(Still the right instinct, and the 2026-08-23 review found the failure is wider than silence: the claim itself was too broad, and the minimum is the wrong statistic at scale.)*
* **D10** (38) — correctly blocked on H1. Its own subset analysis is right that only *transitions which resolved while away* need history; everything else in its example is D7 ordering over live state.
* **D5** (34) — correctly blocked on C2. The all-clear is the product and its three inputs are among the weakest signals on the board. *(Wrong on the gate and superseded: C2 could never have satisfied it, the real constraint was B2, and the item was cancelled 2026-08-23. The second sentence was right and is why it was cancelled.)*
* **D9** (31), **D8** (15), **G4** (15) — unchanged. D9 needs the same user-state foundation E6 and C1 need. D8's own note is the strongest argument against it: inferred stakes that are wrong are worse than no stakes. G4 waits on H1, which its note candidly calls a poor reason to build H1.
* **G5** (11) — health done, versions absent, and the lowest score in the project. If versions are ever wanted the place for them is `--diagnose`, not the strip.

**Open non-board work.** [DRC-4118](<https://linear.app/recce/issue/DRC-4118/cursor-fix-the-workspace-read-and-publish-subagents-as-children-rather>) (Cursor's workspace read, and subagents published as peers rather than children) is still valid: `collectors/cursor.py:396-397` records that no Cursor row carries a subagent or a subagent model yet. *(Done 2026-08-21; that line citation is stale, see the update above.)*
````

### Drafted edits — for the gate to authorize, not yet written

`implementation` performs these four writes as its first action, in this order: file the decision
issue, add the `blocks` edge onto DRC-4029, replace the DRC-4029 body, then insert the milestone
section. The edge is added before the body so the body's claim that the item is blocked is never
briefly false on the board.

#### 1. Decision issue to file (new)

The escalation the stage contract calls for. Not an identifier this workflow mints — see the note in
its own header.

````markdown
**Title:** May a walk-away time read as an all-clear on partial coverage?

**Project:** Cargento: Visibility 2x2 Roadmap · **Milestone:** Spend attention well
**Blocks:** DRC-4029 (D6 · Come back at 3:40)
**Priority:** Medium · **Estimate:** none — this is a decision, not a build
**Labels:** the board's decision-series label if one exists. **The `DEC-N` number is deliberately not
minted here**: Linear is the only writer of identifiers in this project.

---

## The question

D6 wants to publish one clock time a reader can leave the desk on. Triage measured the three candidate statistics the 2026-08-23 review listed and refused all three. What remains is a question about what this product is willing to promise:

**May Cargento publish a single walk-away time whose plain reading is "everything will be done by then", when it knows its coverage is partial and biased toward the fast half of the board?**

## Why it cannot be settled by an engineer

The statistic that delivers the value and the statistic that is honest are different statistics.

* The **minimum** — the soonest completion among estimable turns — never implies an all-clear, and is useless here. Measured 2026-08-28 over 94 recent turns across 11 sessions: median turn 2m03s. With more than one or two estimable sessions the answer is always "now".
* The **maximum** — the soonest moment nothing would still be running — is the only candidate that scales with the board. It is also biased optimistic by construction: `turn_progress` publishes no ETA for a turn that already exceeds every past turn, so the rows the maximum cannot see are the rows running longest. And "everything will be done by 3:40" is an all-clear however it is worded, read as one by someone who then leaves.

## Why the existing precedent does not answer it

D5 (DRC-4028, *Nothing needs you for the next N minutes*) was cancelled on 2026-08-23 for stating the all-clear outright. The recorded reason was that on nine of ten harnesses it would have promised freedom **on no information at all** — an absent signal, not a weak one.

Here the information is present but partial and skewed. Read one way, D5's cancellation was about the coverage and this case is genuinely different. Read the other, it was about the promise itself and coverage is only how it got caught. Both readings fit the record.

## What each answer costs

* **Yes, with the coverage published beside the time.** D6 becomes buildable at roughly its scored size. The risk is that a reader treats a partial figure as complete, which is the failure D5 was cancelled to avoid, now on stronger data instead of none.
* **No.** D6 ships the minimum with the coverage line, is honest, and says "come back now" at this repository's normal load — which is not the value it was scored for. Or D6 is cancelled and this group's outcome stays empty until a harness other than Claude reports needs-input state (B2), which is also what would reopen D5.
* **Only at full coverage** — publish nothing unless every working session carries an estimate. On the one collect measured, coverage was 1 of 2, so the number would have been suppressed. This is a third answer and it should be chosen deliberately rather than arrived at.

## What is already settled and not being reopened

Whatever ships is *the soonest expected completion among turns we can estimate*, never "the soonest moment anything will want you", with the coverage published beside it. D4 shipped in 0.6.x and covers unpredictable arrivals. That narrowing was settled 2026-08-23 and this decision does not disturb it.
````

#### 2. Rewritten DRC-4029 body

Linear state to move to **Blocked**. Length: the forward-looking body is **4,974 characters against
the original's 5,103** — shorter, though not dramatically so, because it absorbs three measured
findings the original did not have. The page as a whole is longer (9,164 characters), and all of
that growth is the dated `## History` section: four sections of the 2026-08-23 body are preserved
there verbatim rather than deleted, two because 2026-08-28 superseded them and two because the body
above compresses them.

What is demoted, and why:

| Section | Why |
|---|---|
| "What it must not claim, which the original framing did" | Compressed into one sentence in the body; the four-bullet exclusion list is the reasoning behind it and is preserved. |
| "What it assumes, and it is the honest risk" | Compressed; it is now the decision's premise rather than a closing caveat. |
| "The flaw that matters most, and it is new" | Superseded — its three candidates are now measured and all three are refused. |
| "One input this did not have when it was scored" | Superseded — refuted; the ask deadline points the other way and is not published to the browser. |
| "What to build" | Superseded — `eta_h` is a formatted string, so this is not arithmetic over what is on screen. |

Nothing is deleted. "What it is", "Say what the number does not cover", "Redundancy, as scored" and
"Scores" are carried forward in the body above, the scores unchanged.

````markdown
Board item **D6**. **Blocked 2026-08-28** on a product decision nobody had filed. Triaged that day against the code and against this machine's live stores. Every sentence of the 2026-08-23 body is either restated below or preserved verbatim under *History*.

**Release row:** r1 · **Journey stage:** Mid-flight · **Outcome group:** Spend attention well

## What it is

One clock time instead of twelve ETAs: a time you could write on a calendar, computed over the per-turn estimates every working card already shows.

## Why it is blocked

The 2026-08-23 review said the minimum is the wrong statistic and listed three candidates without choosing. Measuring them against this repository's own stores rules out all three, for three different reasons.

Measured 2026-08-28 over 94 recent turns across 11 sessions: median turn **2m03s**, p75 5m50s, p90 11m22s, p95 15m17s. 15% reach ten minutes, 3% reach twenty. One live collect at that moment: two working sessions, **one** carrying an ETA.

* **The minimum** is now measured useless rather than suspected: half of all turns finish inside two minutes, so the soonest completion is almost always now.
* **"Exclude anything blocked or already flagged"** is half a no-op and half a regression. `turn_progress` already returns nothing unless the session is `working`, so blocked rows were never in the set. The only flag a working row can carry is `long turn`, which fires at fifteen minutes — so excluding flagged rows excludes precisely the turns long enough to be worth walking away on, and lowers the minimum.
* **A later quantile** changes meaning with how many sessions happen to be running: over two estimable rows a p75 is nearly the maximum, over twelve it is a different promise. It has no one-sentence reading, and a one-sentence reading is the entire product.
* **The maximum, "nothing would still be running",** is the only candidate that scales with the board, and it fails twice. It is biased optimistic by construction: a turn gets no ETA exactly when it already exceeds every past turn, so the rows without one are the rows running longest and the maximum is taken over the fast half of the board. And "everything will be done by 3:40" is an all-clear however it is worded, read as one by somebody who then leaves the desk.

**The useful statistic is the one that reads as an all-clear, and the honest ones say "come back now".** That is a decision about what this product is willing to promise, six days after D5 was cancelled for making that promise on absent information. It is filed as a decision issue and this item blocks on it.

## Two corrections to this issue's own claims

* **The `ask_operator` deadline is not a better input for *this* number.** It is real — five minutes, swept against the ask's creation time — but it is a deadline for *you to answer*, not an estimate of when work finishes. It bounds an errand from above where D6's number bounds it from below, and one figure carrying both units is the error calm mode's two-column split exists to refuse. It belongs to the D5-shaped item. It also never reaches the browser: the published ask card carries an age and nothing else.
* **"Arithmetic over data already on screen" understates the build.** `eta_h` is a formatted string floored to whole minutes, and no numeric ETA is published anywhere in the payload. The statistic has to be computed server-side and published as a new field. Build 15 is still about right in size, but the frontend half lands in `cargento_runtime/web/`, which allows one in-flight PR at a time.

## What survives for the build, once the decision lands

The narrow claim the 2026-08-23 review settled, which this triage did not disturb: whatever ships is *the soonest expected completion among turns we can estimate*, never "the soonest moment anything will want you", and its coverage is published beside it. D4 shipped in 0.6.x and covers the unpredictable arrivals, which is why the narrow claim is enough.

Its stated worth is what the decision should be held against: a subset of D4, redundancy penalty 42, and what survives that penalty is *one clock time you can write down or hand to somebody, which supports pre-committing to a 20 minute errand.* Three per cent of measured turns reach twenty minutes.

The honest risk this item already named is now the reason the decision exists rather than a footnote to it, and the measurement says that gap is wider than it was assumed to be: the rows the number cannot see are the slow ones.

## Scores

Impact 65, risk-adjusted 47, access 85, build 15, detector risk 18. Estimate XS. Quadrant marked unsettled, within 5 points of the impact cutoff. Unchanged.

Detector risk 18 was scored against "is the ETA right" and covers none of the three findings now standing against it: the statistic may be wrong for the workload, the number hides its own coverage, and that hidden coverage is biased toward the fast half of the board. Left unchanged as the board's record.

## History

Carried forward above, not repeated here: what it is, publishing the coverage beside the time, the redundancy penalty, and the scores. The sections below are the ones 2026-08-28 compressed or superseded, kept verbatim as the record of what was believed on 2026-08-23.

### 2026-08-23 — "What it must not claim, which the original framing did" (compressed into the body above)

> The board note says "the soonest moment anything will want you". That is not what the data supports and it is the sentence that would make this dishonest.
>
> `turn_progress` yields an ETA only for a session that is **working** and has a past turn at least as long as the current one. So the set it minimises over excludes:
>
> * every **blocked** session, because state must be `working`
> * every session whose current turn is already longer than any recent turn, which renders as "running longer than recent turns" with no figure
> * every idle session
> * a **gate arriving out of nowhere**, which is the single most common thing that actually wants you and has no ETA on any harness
>
> So the honest claim is narrower: *the soonest expected completion among turns we can estimate.* Not the soonest demand on your attention. Ship the narrow sentence, because the wide one is the one that loses trust the first time a permission prompt fires at 3:05.
>
> The mitigation already exists and is why this is still worth building: **D4 shipped in 0.6.x.** Unpredictable demands raise a notification. This item covers the predictable ones, the notifier covers the rest, and neither has to pretend to cover both.

### 2026-08-23 — "What it assumes, and it is the honest risk" (compressed into the body above)

> Hand someone a single time to come back and they will leave the desk, so in practice this functions as an all-clear it never states. That gap is where the risk was banked as differentiation. D5 was cancelled for stating the same thing out loud, which makes the gap this item relies on worth naming rather than leaving implicit: the difference is that a wrong time here is an inconvenience, while a wrong all-clear is a broken promise.

### 2026-08-23 — "The flaw that matters most, and it is new" (superseded: the three candidates are now measured and all three are refused)

> **The minimum degrades to uselessness exactly where this repository works.** With one or two sessions the soonest completion is a useful time. With a dozen working sessions the minimum is almost always a couple of minutes away, so "come back at 3:40" becomes "come back more or less now", permanently, and the signal stops being actionable at precisely the workload `AGENTS.md` calls normal here (several agents in several worktrees at once).
>
> That is not a presentation problem, it is the wrong statistic. Settle it before building. Candidates, none obviously right:
>
> * The soonest completion **among sessions you have nothing else to do about**, excluding any already blocked or already flagged.
> * A later quantile rather than the minimum, so one fast session does not set the time for eleven slow ones.
> * The soonest completion **that would leave nothing running**, which is a different and arguably more useful promise.

### 2026-08-23 — "One input this did not have when it was scored" (superseded: refuted, see the corrections above)

> A pending `ask_operator` question carries a real deadline, five minutes by default, after which it declines. That is the only demand on the board with a genuine clock rather than an estimate, and it is a strictly better input than any ETA. The ask lane shipped on 2026-08-23 ([DRC-4172](<https://linear.app/recce/issue/DRC-4172/let-a-session-ask-cargento-a-question-and-wait-for-the-answer-dec-2s>)).

### 2026-08-23 — "What to build" (superseded: the estimates are formatted strings, so this is not arithmetic over what is on screen)

> The minimum, or whichever statistic the question above settles on, over the per-turn estimates already computed. They render today on every working card as `~Xm left (est)` and drive calm mode's progress bar, so this is arithmetic over data already on screen. That is what build 15 was scored against and it still holds.
````

#### 3. Milestone correction — "Spend attention well"

Inserted directly after the milestone's opening paragraph and **above** the existing
`## Update 2026-08-23` heading, so the reverse-chronological order the description already keeps is
preserved. Nothing existing is edited or removed; the correction to the 2026-08-23 update is stated
in the new section rather than applied in place, which is the same discipline that update itself
used on the 2026-08-09 audit below it.

````markdown
## Update 2026-08-28 — D6 is blocked on a decision, and this group now has no buildable walk-away item

[DRC-4029](<https://linear.app/recce/issue/DRC-4029/d6-come-back-at-340>) was triaged against the code and against live stores on 2026-08-28 and is **Blocked** on a new decision issue. D5 was cancelled five days earlier, so the outcome this group is named for — look away safely — currently has nothing on it anyone can build.

**What was measured.** 94 recent turns across 11 sessions, on a machine running the parallel-worktree load `AGENTS.md` calls normal here: median turn **2m03s**, p75 5m50s, p90 11m22s, p95 15m17s. 15% of turns reach ten minutes, 3% reach twenty. One live collect at the same moment: two working sessions, one ETA between them.

**All three candidate statistics are refused, each for its own reason.** The minimum is confirmed useless rather than merely suspected, since half of all turns finish inside two minutes. "Exclude anything blocked or flagged" is half a no-op — `turn_progress` already publishes nothing for a non-working session — and half a regression, because the only flag a working row carries fires at fifteen minutes, so it strips exactly the turns worth walking away on. A later quantile changes meaning with how many sessions happen to be running. And the maximum, the one candidate that scales with the board, is biased optimistic by construction: a turn loses its ETA precisely when it outruns its own history, so the rows the maximum cannot see are the slow ones.

**Which leaves the decision, and it is a product decision rather than an engineering one.** The useful statistic is the one whose plain reading is an all-clear; the honest ones say "come back now". D5 was cancelled for promising freedom on absent information. Here the information is present but partial and biased, which is a different case, and the precedent does not settle it either way. That question is filed as a decision issue blocking D6.

**One correction to the 2026-08-23 update below.** It records the pending `ask_operator` deadline as "the only demand on the board with a genuine clock" and "a strictly better input than any ETA". Right about the clock, wrong about the direction: an ask deadline says when you must be *back*, not when you are free *until*. It bounds an errand from above where D6's number bounds it from below, and it never reaches the browser at all — the published ask card carries an age and nothing else. It is an input to D5's shape, not D6's.

---
````

#### 4. Relations

Add `blocks: DRC-4029` on the new decision issue (equivalently, `blockedBy` on DRC-4029). The
existing `relatedTo` edges to DRC-4172 and DRC-4028 stay. No label changes: `release:r1`,
`cutoff:unsettled`, `alternative`, `origin:workshop` and `journey:mid-flight` all still describe the
item accurately, and `cutoff:unsettled` is more accurate now than when it was applied.

### Where this entity goes next

Back to `selection`, per the stage contract's rule for an issue that turns out to need a product
decision nobody has filed. DRC-4029 is not workable until the decision issue is answered, and it was
the board's only open `release:r1` item — so `selection` will be picking under rule 3 or later on its
next pass, not rule 2.

## Expected surface and tolerance

**This stage's own surface: zero repository files.** Everything drafted here is a Linear write that
`implementation` performs as its first action once the gate authorizes it — the DRC-4029 rewrite,
the milestone update, the new decision issue, and the `blockedBy` edge. Tolerance: 0 files, no
tolerance. A repository diff at this stage is a scope error.

**The surface the build would touch, once the decision lands** — recorded so the gate can see what
is being deferred, not proposed for now:

| | expected | tolerance |
|---|---|---|
| `cargento_runtime/turns.py` or a new leaf | numeric seconds beside `eta_h` | ±1 file |
| `cargento_runtime/aggregate.py` | one aggregate field on the collection | ±0 |
| `cargento_runtime/web/` | one render site per view actually served | ±2 files |
| `tests/` | the statistic's own unit tests, plus `test_page.py` byte pins | ±1 file |

**Semantics the change may move.** The published payload gains a field, so `tests/test_contracts.py`
moves. `cargento_runtime/web/` is the one-in-flight-PR conflict surface and `tests/test_page.py`
holds per-part sizes and digests that must be recomputed from the assets rather than merged
textually. Neither is in play while the issue is blocked.

## Acceptance criteria

**None are written, deliberately.** The stage contract makes acceptance criteria conditional on the
statistic being settled, and it is not: it is escalated. Criteria written now would be criteria for
a build whose central quantity is undecided, and the only proof available for them would be a review
of this entity's own prose — which the workflow's rules ban by name.

The criteria that *do* apply are the gate's, and they are the drafts below being written to Linear
faithfully. `implementation` is a Linear-write stage only for this cycle.

## Test plan

No repository test is added or run for this stage, because no repository file changes.

The measurements this triage rests on came from two one-off probes rather than committed tests,
which is what the workflow's rules require of evidence like this:

* `/tmp/drc4029-triage/probe_eta.py` — one real `Application.collect()` against the live stores,
  printing each session's state and turn block. Output: `working=2 with_turn=2 with_eta=1`.
* `/tmp/drc4029-triage/probe_durations.py` — the same collect, then `state.turn_scan`'s cached
  duration history per session. Output: 94 turns across 11 sessions, the percentiles tabled above.

Both read live state and are therefore not reproducible byte-for-byte by a later reader; what a
reader *can* reproduce is the code claims, each of which carries a file and line above and each of
which fails if that line changes. The probes are evidence for the workload characterisation only.

**When the decision lands and the build is scheduled**, the statistic's test is a unit test over
`turn_progress` output shapes with a hand-built session set — not a live collect — because the whole
finding here is that the live distribution moves and the statistic must be right at every point on
it. A coverage-suppression rule, if one is chosen, needs a case where one working row has `eta_h:
None` and the number is withheld.

## Review depth

_Chosen at review from AGENTS.md's Calibrating Effort table._

### Feedback Cycles

**No correction round ran.** No reviewer was dispatched and no gate rejection occurred, so there is
no `Cycle N` line to write; the entry below is a finding-disposition record, which
`## Review-finding disposition` requires to be durable and which reached the worker as a message.

- Disposition 2026-08-28, implementation — finding: Linear's serializer moved five emphasis
  boundaries, three of them in milestone text the approved draft said to leave untouched.
  Worker proposal: Polish / not this task / hold. **FO authorization: DECLINE, materiality Polish.**
  Decided on evidence field 2: the released user's normal workflow is reading that milestone in
  Linear, which renders from its document model rather than from this markdown, so there is no
  observable loss there; the loss appears only in a strict CommonMark renderer outside Linear, which
  is outside what this workflow promises. No repair was authorized and none was made — repairing an
  unapproved change with a second unapproved write compounds a records edit, and the worker's own
  falsifying test (`` `long` **latches** ``, already canonical, round-tripped untouched) indicates
  the normalizer converges on fixed points, so a repair is a likely no-op carrying a write's risk.
  The class was recorded instead as a standing constraint in the workflow README, because
  `save_milestone` has no patch operation and the post-merge reconcile edits a milestone description
  on every completed issue.

## Out of scope

* **Building anything.** The issue is escalated, not planned.
* **Choosing the statistic on the captain's behalf.** Triage measured the candidates and refused all
  three; picking one anyway is the guess the stage exists to prevent.
* **Reopening D5 ([DRC-4028](https://linear.app/recce/issue/DRC-4028), Canceled).** The decision
  issue's answer may bear on it. Acting on that is D5's business, not this one's.
* **Minting the decision issue's board identifier.** The `DEC-N` series is the board's numbering and
  Linear is its only writer; the draft below leaves the number to whoever files it.
* **Revising the scores.** Impact 65, risk-adjusted 47, access 85, build 15, detector risk 18 are
  the board's record and stay unchanged, including the detector risk the 2026-08-23 body already
  flagged as looking low. Triage adds a third reason it looks low and still does not move it.
* **The `?next=true` frontend.** It renders `elapsed_h` and never `eta_h`
  (`web/next/next-session.js:57-61`), so a statistic over ETAs has no existing home there. Whether
  it gets one is the build's question, not triage's.

## Stage Report: triage

- DONE: The original Linear issue body and the owning milestone ("Spend attention well") description are captured verbatim in the entity under `## Linear edits made` BEFORE any other work, and nothing whatsoever has been written to Linear — the drafts stay in the entity for the gate to authorize.
  Captured and committed first, in `62067e0`, before any code was read; the drafts landed in a later commit. No Linear write tool was called this stage — only `get_issue`, `get_milestone` and `list_comments` (which returned zero comments).
- DONE: Every claim the rewrite makes about current behaviour was checked by reading the code in this repository, not by re-reading the issue: in particular whether per-turn ETA estimates still render as `~Xm left (est)`, whether calm mode still drives a progress bar from them, and whether the ask lane's deadline (DRC-4172, shipped) is available as an input.
  All three checked, and two came back with corrections. `~Xm left (est)` is live at `web/regular.js:520` and `web/calm.js:230` — falsified if either literal changes. The progress bar is live at `web/calm.js:796-802` and `739-744`, driven from `turn.pct`; **the issue is wrong that this is calm-only** — `web/regular.js:512-518` draws a `turnbar` from the same field, and `web/next/next-session.js:57-61` renders `elapsed_h` and never `eta_h`. The ask deadline exists server-side (`config.py:516`, `ask_deadline_sec=300.0`, swept in `aggregate.py:632`) but **is not published to the browser**: the ask card carries `age_sec` alone (`aggregate.py:619-635`) — falsified the moment a deadline or remaining-time key joins that dict. One further check the checklist did not name and the rewrite needed: `eta_h` is a formatted string (`turns.py:399` → `sessions.py:94-104`), and no numeric ETA is published anywhere, so "arithmetic over data already on screen" is not what the build is.
- DONE: The issue's own unsettled question — which statistic to publish, given the minimum degrades to "come back now" at the multi-session workload AGENTS.md calls normal here — is either settled with a recommendation and its evidence, or escalated as a decision issue that blocks this one; acceptance criteria are written only if it is settled, and each carries a `Verified by:` clause naming something outside the entity body plus the concrete change that would falsify it.
  **Escalated, not settled**, so no acceptance criteria are written — deliberately, and `## Acceptance criteria` says why. The decision issue is drafted in full under `## Linear edits made` and linked as a blocker. The escalation rests on measurement rather than argument: two one-off probes against this machine's live stores gave 94 recent turns across 11 sessions (median 2m03s, p75 5m50s, p90 11m22s, p95 15m17s; 3% reach twenty minutes) and one live collect with two working sessions and one ETA between them. Against that, the minimum is confirmed useless; candidate 1 is a no-op plus a regression (`turns.py:386` already drops non-working rows, and the only working-row flag fires at `long_turn_warn_sec = 900`, `config.py:444`, so excluding flagged rows strips the long turns); a quantile has no stable reading; and the maximum is biased optimistic by construction (`turns.py:402-406`) and is an all-clear in all but wording — the promise D5 was cancelled for five days earlier.

### Summary

Triage found the issue unbuildable as written and escalated rather than guessing. The 2026-08-23 body already said the statistic was unsettled and listed three candidates; measuring all three against this repository's own stores refuses all three, and what remains is a product decision — whether Cargento may publish a walk-away time whose plain reading is an all-clear, on coverage it knows to be partial and skewed toward the fast half of the board. D5's cancellation is the nearest precedent and does not settle it, because absent information and partial-but-biased information are different cases.

Four writes are drafted and none performed: a new decision issue, a `blocks` edge onto DRC-4029, the rewritten body (forward part 4,974 characters against the original's 5,103, with five superseded or compressed sections preserved verbatim under a dated `## History`), and a milestone section inserted above the existing 2026-08-23 update that also corrects that update's claim about the `ask_operator` deadline. Scores are left untouched, including the detector risk the previous reader flagged as looking low — triage adds a third reason it looks low and still does not move the board's record. Zero repository files changed, which is the whole expected surface for this stage. The entity should return to `selection`; with DRC-4029 blocked, the board has no open `release:r1` item.

## Stage Report: implementation

- DONE: All four approved Linear writes performed in the declared order: (1) file the new decision issue, (2) add its `blocks` edge onto DRC-4029, (3) replace the DRC-4029 body and move its state to Blocked, (4) insert the milestone section above the existing `## Update 2026-08-23` heading in "Spend attention well". The edge must precede the body write, so the body's claim to be blocked is never briefly false on the board.
  Written in that order. The decision issue was minted by Linear as **DRC-4271**; the `blocks` edge was read back and confirmed live *before* the body write was issued, so the ordering guarantee is measured rather than assumed.
- DONE: Each written record read back from Linear AFTER the write and compared against the approved draft — not trusted from the write call's return value. Confirm specifically: the `## History` sections survive verbatim, the Scores block is byte-identical to the original (including the detector risk 18 the record deliberately leaves unmoved), DRC-4029's labels are unchanged, and the milestone's existing 2026-08-23 and 2026-08-09 sections are untouched below the new one.
  Every record read back through a fresh `get_issue`/`get_milestone` call issued after its write; no confirmation below rests on a write call's return value, and every discrepancy found is reported rather than absorbed. HOLDS: all five `## History` blockquotes byte-identical, including the `[DRC-4172](<...>)` link, which was *not* converted to a Linear mention because it sits inside a blockquote. HOLDS: Scores line verbatim — "Impact 65, risk-adjusted 47, access 85, build 15, detector risk 18. Estimate XS." — detector risk 18 unmoved. HOLDS: DRC-4029 labels exactly `origin:workshop`, `alternative`, `cutoff:unsettled`, `release:r1`, `journey:mid-flight`; `relatedTo` DRC-4172 and DRC-4028 both retained; estimate XS, priority Medium, milestone all unchanged. HOLDS: status Blocked, `stateHistory` showing Backlog→Blocked at 02:26:24Z. **The fifth confirmation — the milestone's pre-existing sections untouched — does not hold, and cannot be made to hold through this API.** Three emphasis boundaries moved, in the 2026-08-23, 2026-08-21 and 2026-08-09 sections; text content is unchanged in all three. This is not a satisfiable criterion: `save_milestone` exposes no patch operation, so inserting a section requires resending the whole description through Linear's serializer, and the write that shifted these three sent the captured *clean* bytes verbatim — so resending clean bytes is precisely what produces the shifted form. No worker and no repair write can satisfy it as written, which is why the criterion rather than the work was corrected. Dispositioned Polish / decline by the FO on the evidence in `### Finding` below, which stands unchanged.
- DONE: Zero repository files changed. The expected surface for this cycle is zero files with no tolerance; a repository diff is a scope error. Report the Linear identifier the new decision issue was minted as.
  `git diff --numstat "$(git merge-base main HEAD)"..HEAD` in the worktree returns empty; the worktree is clean and still at `ec10918`, the same commit as main. No branch commit, no PR, no `sync-docs`, no pre-PR suite — none applied this cycle. The decision issue is **DRC-4271**. The two pre-existing entries in the main checkout (` M .gitignore`, `?? docs/roadmap-burndown/`) predate this dispatch and are visible in the session-start git snapshot.

### Finding — Linear's serializer moved five emphasis boundaries; three are in text the drafts said to leave alone

Preserved, not acted on. No repair write was made and no FO authorization was sought for one.

Linear stores rich text and re-serializes to markdown on read. It normalizes **a bold run whose boundary directly touches an inline code span or a link**, moving the mark boundary or splitting the run. Text content is unchanged in all five cases; only emphasis boundaries moved. The class is falsifiable: `` `long` **latches** `` in the 2026-08-21 section has a space between code and bold, was already in canonical form, and came back untouched — so the trigger is adjacency, not the presence of code or links.

Two are in the new DRC-4029 body, under "Two corrections to this issue's own claims": `**The** `ask_operator` **deadline...**` (split around the code span) and `...understates the build. **`eta_h`` (closing `**` moved after the space).

Three are in milestone text the draft explicitly said to leave alone — "Nothing existing is edited or removed": `...the board did not. **[DRC-4029]` (2026-08-23), `[**DRC-4118**](<...>) **is Done**` (2026-08-21), and `**Open non-board work. **[DRC-4118]` (2026-08-09). These were not intended. `save_milestone` has no patch operation, so inserting a section requires resending the whole description, and the pre-existing text round-tripped through the normalizer on the way.

Evidence fields — (1) a person reading the "Spend attention well" description in Linear; (2) no observable harm in Linear's own renderer, which renders from the document model, not from this markdown; a strict CommonMark renderer outside Linear would show literal asterisks where a `**` now follows a space; (3) `contract[docs/roadmap-burndown/.spacedock-state/drc-4029.md#3-milestone-correction--spend-attention-well]`, whose claim is that nothing existing is edited; (4) the three diffs above, observed in the post-write read-back.

Proposed materiality **Polish**, proposed ownership **not this task** — a repair is another unapproved write to a shared record, and the normalized forms look like stable fixed points rather than a transient glitch, so a repair may well be a no-op. Proposed disposition **hold**. My round Resolution is advisory; the FO owns authorization.

### Summary

The four writes the triage gate authorized are on the board in the declared order, drafts used verbatim. The decision issue was minted by Linear as DRC-4271 with no `DEC-N` number invented; it carries no labels, which matches the observed convention rather than a guess — DEC-1, DEC-2, DEC-3, DEC-5 and DEC-6 (DRC-4053, 4054, 4122, 4182, 4234) all carry zero labels, so no decision-series label exists to apply. DRC-4029 is Blocked by DRC-4271, with its labels, scores, estimate and existing relations intact, and the milestone's new 2026-08-28 section sits above the 2026-08-23 heading with all three older sections below it. Zero repository files changed, against a zero-file expected surface with no tolerance.

One thing did not go to plan and is escalated rather than fixed: Linear's markdown serializer moved five emphasis boundaries, three of them inside milestone text the draft said to leave untouched. No repair was attempted, because repairing an unapproved change with a second unapproved write is how a records edit compounds. Two further observations for the record: Linear auto-created a `relatedTo` edge from DRC-4271 to DRC-4028 from the issue mention in the drafted body — accurate, but not something the draft asked for, and left in place; and the drafted title does not follow the existing `DEC-N · Decision: ...` naming pattern the other decision issues use, which is the captain's call to make, not mine.
