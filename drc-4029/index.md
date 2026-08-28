---
id:
title: 'D6 · Come back at 3:40'
status: triage
source: https://linear.app/recce/issue/DRC-4029
started: 2026-08-28T02:02:06Z
completed:
verdict:
score: 0.9
worktree:
issue:
pr:
mod-block:
linear-status: Todo
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
            - id: gate-attempt:drc-4029-triage-2
              briefing:
                id: briefing:drc-4029:triage:attempt-2:revision-1
                digest: sha256:c6c24f78cfab7f53ababcabac4a388b4c133966150d0cb1f6494d5e3a6ed83dd
                room-ref: ./review/triage/briefing-2
              resolution:
                type: Resolution
                id: resolution:spacedock:drc-4029:triage:2
                briefing: briefing:drc-4029:triage:attempt-2:revision-1
                by: person:captain
                at: "2026-08-28T05:33:39.372966Z"
                decision: approve
                reason: 'RULING: CANCEL DRC-4029. The captain ruled at the cycle-2 triage gate that D6 is cancelled rather than re-scoped. Accepts the recommendation and its five ranked reasons, the decisive one being that triage measured the ceiling shared by every statistic the DEC-7 ruling permits rather than testing candidates one at a time: an oracle assuming perfect estimates and total coverage had a median lead of 1m16s across 375 multi-session instants and reached the twenty-minute window the item was scored on 0 times, so the constraint is the quantity and no implementation can beat it. The strongest genuinely-open candidate, the settled minimum plus a suppression rule, was built and measured and failed on both axes at once — 0 of 375 renders at T=20m, and at T=10m it rendered three times and reality beat it three times by a median of 10m42s. Two further reasons the captain should be recorded as having seen: the item degrades as the product improves, because a minimum over more rows is smaller, so B2 landing makes D6 less useful rather than more; and where the statistic works at one session it duplicates the card own rendered estimate. A reopening condition is written into the drafted body as a re-runnable probe rather than a judgement, so cancellation is reversible on evidence. Evidence quality noted: DRC-4271 probe was re-run unchanged and one figure was reported as drifted rather than repeated, and code claims were re-checked at v0.17.1 after main moved. SCOPE OF THIS APPROVAL: drafted writes 1 to 3 only — the DRC-4029 body rewrite and move to Canceled, the milestone correction, and the state/labels/relations edit. Drafted write 4, the one-sentence edit to DRC-4272, was NOT authorized: the captain did not answer that question and it remains open. DRC-4272 is to be left untouched.'
              application:
                target-stage: implementation
                state: pending
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

---

## Triage cycle 2 — 2026-08-28 · re-scope or cancel

The first cycle escalated and the captain ruled. This cycle answers what the ruling deliberately
left open: **is there a fourth statistic that carries the narrow claim honestly and is worth
building, or should this item be cancelled?** Everything above this line is the record of cycle 1
and is not edited.

### Linear edits made — cycle 2

**Nothing has been written to Linear this cycle.** Captured before any other work, as the pre-edit
record; the drafts below are what the gate authorizes.

#### Pre-edit record — captured 2026-08-28

The issue body's Linear `updatedAt` is `2026-08-28T04:37:02.285Z`; the issue still carries no
comments (`list_comments` returned zero). State `Todo`, `blockedBy: []`, `relatedTo` DRC-4271,
DRC-4172, DRC-4028, DRC-4272. Labels `origin:workshop`, `alternative`, `cutoff:unsettled`,
`release:r1`, `journey:mid-flight`.

This is the body `implementation` wrote at the end of cycle 1, read back live — **including the two
emphasis boundaries Linear's serializer moved**, which the FO dispositioned Polish/decline and which
are therefore part of the record rather than a transcription error on my part. They are visible in
"Two corrections to this issue's own claims" below: `**The **` before the code span, and a second
bullet that lost its opening bold entirely.

##### Current issue body — DRC-4029 "D6 · Come back at 3:40"

````markdown
Board item **D6**. **Blocked 2026-08-28** on a product decision nobody had filed, and released the same day when that decision was ruled. Triaged that day against the code and against this machine's live stores. Every sentence of the 2026-08-23 body is either restated below or preserved verbatim under *History*.

**Release row:** r1 · **Journey stage:** Mid-flight · **Outcome group:** Spend attention well

## What it is

One clock time instead of twelve ETAs: a time you could write on a calendar, computed over the per-turn estimates every working card already shows.

## The decision landed 2026-08-28, and the answer is No

DEC-7 ([DRC-4271](<https://linear.app/recce/issue/DRC-4271/dec-7-decision-may-a-walk-away-time-read-as-an-all-clear-on-partial>)) was ruled by the owner on 2026-08-28 and is closed. The ruling: Cargento may not publish a single walk-away clock time whose plain reading is an all-clear, on partial coverage. Three reasons, in order of weight:

1. **The disclosure does not cover the claim.** An all-clear is a claim about demands on attention, and that claim rests on needs-input coverage — four harnesses of ten. Publishing ETA coverage beside the number discloses a different quantity, so it does not mitigate the risk it was designed to mitigate.
2. **Even the narrow completion claim is unreliable.** The published maximum is earlier than the true last completion 74% of the time; at three or four concurrent sessions it is 87% of the time, by a median of 9m50s.
3. **The precedent already weighed this trade and came down against it.** D5 conceded a coverage-scoped promise "is honest" and rejected it as "materially different and less appealing". The 2026-08-28 measurements make that position worse, not better.

"Only at full coverage" was refuted by measurement rather than declined: full ETA coverage across every working row held at 0 of 82 sampled instants at three-to-four concurrent sessions, the parallel-worktree load `AGENTS.md` calls normal here.

**What the ruling does not decide, deliberately.** It is narrower than cancelling this item. The narrow claim the 2026-08-23 review settled — *the soonest expected completion among turns we can estimate*, with coverage published beside it — is not an all-clear and is untouched. **Whether D6 is re-scoped or cancelled is not decided here.** That belongs to this item's own next cycle, which the ruling releases, and it is why the item moves out of Blocked to Todo rather than to Canceled. DEC-7's gate on this item is removed and replaced with a related edge, so the closed evidence stays reachable without a closed issue holding a live gate.

## Why it was blocked

The 2026-08-23 review said the minimum is the wrong statistic and listed three candidates without choosing. Measuring them against this repository's own stores rules out all three, for three different reasons.

Measured 2026-08-28 over 94 recent turns across 11 sessions: median turn **2m03s**, p75 5m50s, p90 11m22s, p95 15m17s. 15% reach ten minutes, 3% reach twenty. One live collect at that moment: two working sessions, **one** carrying an ETA.

* **The minimum** is now measured useless rather than suspected: half of all turns finish inside two minutes, so the soonest completion is almost always now.
* **"Exclude anything blocked or already flagged"** is half a no-op and half a regression. `turn_progress` already returns nothing unless the session is `working`, so blocked rows were never in the set. The only flag a working row can carry is `long turn`, which fires at fifteen minutes — so excluding flagged rows excludes precisely the turns long enough to be worth walking away on, and lowers the minimum.
* **A later quantile** changes meaning with how many sessions happen to be running: over two estimable rows a p75 is nearly the maximum, over twelve it is a different promise. It has no one-sentence reading, and a one-sentence reading is the entire product.
* **The maximum, "nothing would still be running",** is the only candidate that scales with the board, and it fails twice. It is biased optimistic by construction: a turn gets no ETA exactly when it already exceeds every past turn, so the rows without one are the rows running longest and the maximum is taken over the fast half of the board. And "everything will be done by 3:40" is an all-clear however it is worded, read as one by somebody who then leaves the desk.

**The useful statistic is the one that reads as an all-clear, and the honest ones say "come back now".** That is a decision about what this product is willing to promise, six days after D5 was cancelled for making that promise on absent information. It is filed as a decision issue and this item blocks on it.

## Two corrections to this issue's own claims

* **The **`ask_operator` **deadline is not a better input for *this* number.** It is real — five minutes, swept against the ask's creation time — but it is a deadline for *you to answer*, not an estimate of when work finishes. It bounds an errand from above where D6's number bounds it from below, and one figure carrying both units is the error calm mode's two-column split exists to refuse. It belongs to the D5-shaped item. It also never reaches the browser: the published ask card carries an age and nothing else.
* "Arithmetic over data already on screen" understates the build. `eta_h` is a formatted string floored to whole minutes, and no numeric ETA is published anywhere in the payload. The statistic has to be computed server-side and published as a new field. Build 15 is still about right in size, but the frontend half lands in `cargento_runtime/web/`, which allows one in-flight PR at a time.

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

##### Current milestone description — "Spend attention well"

Only the `## Update 2026-08-28` section is in play this cycle; it is captured verbatim below. The
rest of the description is byte-identical to the capture already held in this entity at cycle 1,
except for the three emphasis boundaries Linear's serializer moved during cycle 1's write, which are
recorded in cycle 1's implementation report and were dispositioned Polish/decline.

````markdown
## Update 2026-08-28 — D6 is blocked on a decision, and this group now has no buildable walk-away item

[DRC-4029](<https://linear.app/recce/issue/DRC-4029/d6-come-back-at-340>) was triaged against the code and against live stores on 2026-08-28 and is **Blocked** on a new decision issue. D5 was cancelled five days earlier, so the outcome this group is named for — look away safely — currently has nothing on it anyone can build.

**What was measured.** 94 recent turns across 11 sessions, on a machine running the parallel-worktree load `AGENTS.md` calls normal here: median turn **2m03s**, p75 5m50s, p90 11m22s, p95 15m17s. 15% of turns reach ten minutes, 3% reach twenty. Re-derived across five slicings of 124–558 turns, which held that shape: median 2m03s–2m33s, p90 10m55s–12m20s, 12–15% of turns at ten minutes, 2–4% at twenty. The single live collect this update first cited — two working sessions, one ETA between them — is an n=1 observation and is superseded by replaying `turn_progress`' own rule over 558 turns: ETA coverage is 80% of turns and 64–71% of wall-clock, materially better than that one collect suggested.

**All three candidate statistics are refused, each for its own reason.** The minimum is confirmed useless rather than merely suspected, since half of all turns finish inside two minutes. "Exclude anything blocked or flagged" is half a no-op — `turn_progress` already publishes nothing for a non-working session — and half a regression, because the only flag a working row carries fires at fifteen minutes, so it strips exactly the turns worth walking away on. A later quantile changes meaning with how many sessions happen to be running. And the maximum, the one candidate that scales with the board, is biased optimistic by construction: a turn loses its ETA precisely when it outruns its own history, so the rows the maximum cannot see are the slow ones.

**Which leaves the decision, and it is a product decision rather than an engineering one.** The useful statistic is the one whose plain reading is an all-clear; the honest ones say "come back now". D5 was cancelled for promising freedom on absent information. The precedent settles more than this update first credited it with, for two reasons. D5's own reasons are explicitly ranked, they lead with "D6 already exists and the board prefers it", and the record concedes that a coverage-scoped promise "is honest" — rejecting it on value rather than on honesty. And the coverage an all-clear rests on is needs-input coverage, not ETA coverage, so publishing the second discloses nothing about the first. That question is filed as a decision issue blocking D6. Recorded here because nothing else records it: needs-input detection reached four harnesses on 2026-08-24, so D5's stated reopening condition — a harness other than Claude reporting needs-input state — has been met.

**One correction to the 2026-08-23 update below.** It records the pending `ask_operator` deadline as "the only demand on the board with a genuine clock" and "a strictly better input than any ETA". Right about the clock, wrong about the direction: an ask deadline says when you must be *back*, not when you are free *until*. It bounds an errand from above where D6's number bounds it from below, and it never reaches the browser at all — the published ask card carries an age and nothing else. It is an input to D5's shape, not D6's.
````

### The question, and how it can be settled by measurement rather than by argument

The ruling forbids a statistic whose plain reading is an all-clear. What it leaves standing is the
narrow claim settled 2026-08-23: *the soonest expected completion among turns we can estimate*, with
coverage beside it. Every statistic still permitted is therefore a claim of one shape:

> Nothing you can predict will be ready before X.

That claim is sound only if X is no later than the true soonest completion among the sessions
running. **So the true soonest completion is a hard ceiling on the entire permitted family** — not a
property of `turn_progress`, not a property of coverage, and not something a better estimator can
move. A fourth statistic can only be a different way of choosing X below that ceiling.

That makes the search finite. Measure the ceiling. If the ceiling is a couple of minutes at the load
this item exists for, there is no fourth statistic, and the refusal is structural rather than a
fourth coincidence.

### What was measured, 2026-08-28 (cycle 2)

`drc-4029/probe_min_lead.py`, committed beside this entity. It reuses DRC-4271's interval
reconstruction verbatim, the same random seed, and the same exhausted draw stream, so **its
multi-session instants are the same 375 instants `probe_max_error.py` samples** — the two probes
measure the minimum and the maximum over one set of moments. 44 sessions and 541 turns over a
seven-day window; 5,922 sampled instants with at least one working session, of which 375 had two or
more and 71 had three or four.

That shared harness was checked rather than assumed. Re-running `probe_max_error.py` unchanged
against the store as it stands today reports the same 44 sessions and 541 turns, and reproduces
DRC-4271's published result: full ETA coverage at three-to-four concurrent sessions is 0 of 71
(DRC-4271: 0 of 82), and the published maximum is earlier than the truth 76% of the time overall and
87% at k = 3–4 (DRC-4271: 74% and 87%). One figure drifted and is reported rather than repeated: the
median understatement at k = 3–4 came out **6m52s today against DRC-4271's 9m50s**, which the ruling
quotes. Same direction, same order of magnitude, different number — the store grows daily, and this
is what "machine-specific by construction" costs. Nothing in either cycle's conclusion turns on it.

At each instant it computes two numbers:

- **published** — the minimum over the rows `turn_progress` can actually estimate. What D6 would
  ship today.
- **oracle** — the minimum over the *true* completion of every live turn, covered or not. What a
  perfect estimator with total coverage would publish. It bounds every possible improvement.

| | renders | median lead | p75 | p90 | ≥5m | ≥10m | ≥20m |
|---|---|---|---|---|---|---|---|
| k = 1, published | 80% | 3m27s | 7m19s | 16m03s | 27.6% | 14.7% | 6.7% |
| k = 1, **oracle** | 100% | 3m40s | 8m40s | 19m11s | 40.6% | 21.4% | 9.4% |
| k = 2, published | 69% | 2m01s | 2m55s | 4m38s | 5.6% | 1.0% | **0.0%** |
| k = 2, **oracle** | 100% | 1m23s | 3m05s | 5m19s | 12.5% | 1.6% | **0.0%** |
| k = 3–4, published | 85% | 2m45s | 4m03s | 5m07s | 12.7% | 0.0% | **0.0%** |
| k = 3–4, **oracle** | 100% | 0m57s | 1m47s | 2m36s | **0.0%** | 0.0% | **0.0%** |
| all k ≥ 2, published | 72% | 2m15s | 3m09s | 4m49s | 6.9% | 0.8% | **0.0%** |
| all k ≥ 2, **oracle** | 100% | 1m16s | 2m41s | 4m59s | 10.1% | 1.3% | **0.0%** |

Three things in that table decide the issue.

**The ceiling is about a minute and a quarter.** At two or more concurrent sessions the oracle
minimum has a median lead of 1m16s and reached twenty minutes in 0 of 375 sampled instants. At three
or four sessions its ninetieth percentile is 2m36s, and it did not reach five minutes once. No
estimator, no coverage work and no fourth statistic can produce a walk-away time from a quantity
that is not there.

**Every available improvement moves the central number the wrong way.** The oracle's median lead is
*earlier* than what `turn_progress` publishes — 1m16s against 2m15s at k ≥ 2, and 57s against 2m45s
at k = 3–4 — because a minimum taken over more rows is smaller. The published figure looks better
than the truth precisely because it cannot see some of the rows. So better estimates, wider ETA
coverage and B2 landing all lower this number. That is unusual enough to state plainly: **D6
degrades as the rest of the product improves.**

One honesty note on that claim, because the wider sample qualifies it. At k = 2 the oracle's *tail*
is slightly fatter than the published figure's — it clears five minutes 12.5% of the time against
5.6% — because the published number is absent altogether at 31% of k = 2 instants, and those absences
count against it. So the comparison there is between a figure that is longer but often missing and
one that is shorter but always right. At k = 3–4 no such qualification applies: the oracle is worse
across the whole distribution, never once reaching five minutes where the published figure did 12.7%
of the time.

**Where the number is useful, the item is redundant.** At one working session the published minimum
has a median lead of 3m27s and clears twenty minutes 6.7% of the time. But at one working session
D6's aggregate *is* that session's own `~Xm left (est)`, already rendered on its card. The item
delivers a figure only where it adds nothing to what is on screen.

The k = 1 row is also the control that makes the zeroes meaningful. The instrument does find windows
of twenty minutes and more when they exist — 6.7% of 5,547 instants at k = 1, 9.4% on the oracle. It
found none at k ≥ 2. The zero is a signal, not a blind instrument.

### The fourth statistic, built and measured

The strongest candidate the ruling leaves open is not a new average. It is the settled narrow claim
plus a **suppression rule**: publish the minimum only when it is at least T minutes out, and render
nothing otherwise. This is the convention calm mode's `fastest` ordering already sets — refuse
visibly rather than publish a figure that means nothing — and it converts "come back now" from a
useless answer into an absent card. It is honest by construction, it needs no new data, and it is
the one candidate none of the three prior refusals covers.

It was measured on the same 375 instants at k ≥ 2. `wrong` means the card said "nothing before X"
and something completed before X:

| threshold | renders | wrong when it renders | by a median of |
|---|---|---|---|
| T = 5m | 6.9% (26/375) | 88% | 4m43s (worst 10m42s) |
| T = 10m | 0.8% (3/375) | **100%** | 10m42s |
| T = 20m | **0.0% (0/375)** | — | — |

**It fails twice over.** At the threshold that carries the item's own stated value it never renders
at all, which is the same non-delivery that refuted "only at full coverage" (0 of 71 instants at
k = 3–4 on today's store, 0 of 82 when DRC-4271 measured it).
Lower the threshold to make it render and it is wrong every time it does — a card that appears
rarely and lies when it appears is worse than no card, because its rarity is what makes a reader
trust it.

That result also closes the probabilistic loophole. A statistic could try to sit *above* the true
minimum on purpose — "90% chance nothing finishes before X" — trading soundness for a longer window.
The suppression measurement is exactly that statistic's empirical form, and its calibration is what
fails: at T = 10m reality beat the published time in 3 firings out of 3, by a median of 10m42s. The
tail this product would need to sell is the tail the data does not have.

Three further candidates were considered and rejected without a probe, because each is refuted by
what the number would say rather than by how often it says it:

- **The soonest completion among long-running turns only** — the inverse of cycle 1's refused
  "exclude anything flagged". It produces a later time, but it is not a walk-away time: it says
  nothing about the other sessions, so a reader cannot leave on it. It answers "when is the thing I
  am waiting for done", which is the per-card ETA already rendered, hoisted to the top by D7's
  attention ordering since 2026-08-21.
- **A completion forecast rather than a clock time** — "four of six done by 3:40". Its plain reading
  is not an all-clear, so the ruling permits it. But it is no longer the product that was scored: D6
  is "one clock time you can write down or hand to somebody", and a forecast is neither writable on
  a calendar nor actionable for leaving the desk. It is progress information, which is what the
  dashboard already is.
- **Any statistic over the maximum, with imputation for the uncovered rows.** Statistically this is
  the interesting fix — the bias DEC-7 measured is correctable in principle. It is out of bounds
  here regardless of merit: every statistic over the maximum publishes "nothing will still be
  running by X", which is the all-clear the captain ruled against. Recorded so the gate can see it
  was considered and why it was not measured, not to reopen it.

### Recommendation: **cancel DRC-4029**

Five reasons, in order of weight.

1. **The permitted family has a measured ceiling and it is about a minute and a half.** At the
   multi-session load this item exists for, a perfect estimator with total coverage has a median
   lead of 1m16s and never reached twenty minutes across 375 instants. The constraint is the
   quantity, not the code.
2. **The item gets worse as the product gets better.** Improving coverage lowers the minimum, by
   arithmetic. B2 landing, better estimates, more harnesses reporting — every direction the roadmap
   is already moving in makes D6 less useful. An item with that shape does not become buildable
   later; it becomes less buildable.
3. **What survives the redundancy penalty is exactly what the ruling forbids.** The item's own
   record says the 42-point penalty against D4 leaves one thing standing: *"supports pre-committing
   to a 20 minute errand"*. After DEC-7 that pre-commitment may not be published, and the
   measurement says the window it would rest on did not occur once in 375 sampled instants. Build 15
   buys a card that either says "come back now" or does not render.
4. **The strongest remaining candidate was built and it failed on both axes at once.** Rare *and*
   wrong is the combination that cannot be tuned out: raising the threshold empties the card,
   lowering it fills the card with figures reality beat 88% of the time.
5. **Where the statistic works, it duplicates a rendered field.** At one session it is the card's own
   `~Xm left (est)`.

Cancelling is the answer to the re-scope-or-cancel question, not a judgement on the reasoning that
produced the item. The 2026-08-23 review was right that the minimum is the wrong statistic; what is
new is that so is everything else the ruling leaves standing.

### What would change the answer

Each is a falsifier with a named test, not a hypothetical.

- **A different workload.** Re-run `probe_min_lead.py`. If the oracle minimum at k ≥ 2 clears twenty
  minutes in a material fraction of instants — say above 10%, against 0 of 375 here — the errand
  value exists and D6 becomes buildable as the plain minimum. That needs much longer turns or far
  fewer concurrent sessions, so it is a claim about how someone works rather than about this code.
  The measurement is machine-specific by construction and another machine re-derives its own.
- **A change in what the product is being asked.** If the question becomes "when is *this* session
  done" rather than "when am I free", the statistic is per-card and shipped. That is not a re-scope
  of D6; it is a different item.
- **Needs-input coverage completing.** If B2 ([DRC-4014](https://linear.app/recce/issue/DRC-4014))
  brings the remaining six harnesses in, an attention-based all-clear rests on complete coverage for
  the first time. That reopens **D5**, whose product that is. It does not reopen D6, whose number is
  a completion estimate and whose ceiling this cycle measured.
- **The mechanism changing.** If `turn_progress` stops drawing history per session, or publishes an
  ETA for a turn that outruns its own history, the coverage and bias figures behind both cycles are
  void and the whole line of reasoning needs re-deriving. Falsified by the empty-`cands` branch at
  `turns.py:405-410` publishing a figure.

### The knock-on to D5, assessed and not acted on

DRC-4028's ranked cancellation reasons lead with *"D6 already exists and the board prefers it"*.
Cancelling D6 removes that reason retroactively, so the assessment the scope notes asked for is
whether that needs a filing or an edit.

**It needs neither a new filing nor a new issue — it needs one sentence changed on
[DRC-4272](https://linear.app/recce/issue/DRC-4272), and that is the captain's call rather than
this cycle's.** DRC-4272 was filed at the end of cycle 1 and already anticipates this exact case in
its closing line, verbatim:

> D5's weightiest recorded cancellation reason was that D6 already exists and the board prefers it.
> If D6 is later cancelled, that reason disappears retroactively and this issue becomes the second
> half of the case for looking at D5 again.

If the gate authorizes cancellation, that conditional becomes a fact and the honest edit is to say
so. Nothing else about D5 changes, and the drafted edit is held in the drafts below rather than
performed.

**What the knock-on is not, and the record should say so before someone reads it the other way.**
Cancelling D6 does not make D5 buildable, for two reasons that stand independently of it:

- DRC-4028's other two ranked reasons — the r2-gated-on-r3 sequencing contradiction and its own
  scores — are untouched by anything in either cycle.
- DEC-7's ruling constrains D5 harder than it constrains D6. D5 *is* the explicit all-clear, and
  needs-input coverage is four harnesses of ten. A ruling that forbids an implied all-clear on
  partial coverage forbids a stated one on thinner coverage a fortiori. D5 becomes eligible for a
  fresh look when B2 closes, which is what DRC-4272 already says and what DRC-4014 owns.

So: two of D5's three cancellation reasons survive, and the ruling adds a new constraint that did
not exist when it was cancelled. The captain may reasonably decide the reopening case is now
stronger, weaker, or unchanged; this cycle records the inputs and does not decide it.

### Passages in the current body that the ruling or DRC-4271 falsified

Six, of which the scope notes named two. Each is quoted from the pre-edit capture above.

**1. The coverage claim, named in the scope notes.** In "Why it was blocked":

> One live collect at that moment: two working sessions, **one** carrying an ETA.

An n=1 observation asserted as fact. DRC-4271's triage replayed `turn_progress`' own rule over 558
turns and got **80% of turns carrying an ETA, and 64–71% of working wall-clock**. Coverage is four
rows in five, not one in two. The milestone was corrected for this on 2026-08-28; the issue was not,
because the correction was not in the approved DEC-7 drafts.

**2. The closing sentence, named in the scope notes.** Same section:

> It is filed as a decision issue and this item blocks on it.

False since 2026-08-28T04:34:36Z. DEC-7 is closed, DRC-4029 is `Todo`, and `blockedBy` is empty —
the gate was replaced with a related edge. The sentence contradicts the body's own ruling section
four paragraphs above it.

**3. The optimistic-bias mechanism is overstated.** In the maximum's bullet:

> the rows without one are the rows running longest

DRC-4271 corrected this explicitly, as a correction to the mechanism rather than to the conclusion:
the uncovered set is broader than "the longest rows". It is every non-working row, every row whose
turn outruns **its own session's** history, and **every session on its first turn**, which has no
history at all and may be short. The bias direction survives and is now measured — uncovered turns
run 4–5× longer, median 7m56s against 2m05s — but the sentence as written describes a cleaner
mechanism than the code has.

**4. An arithmetic slip.** In the same section:

> six days after D5 was cancelled

D5 was cancelled 2026-08-23 and this was written 2026-08-28. Five days. The milestone's own
2026-08-28 update says "five days earlier", so the two records disagree with each other. Not
falsified by the ruling — just wrong, and worth fixing while the body is open.

**5. A heading that assumes an unlanded decision.** The section titled:

> ## What survives for the build, once the decision lands

The decision landed the same day. The section's content — the settled narrow claim, and the
redundancy penalty it must be held against — is still true and is what this cycle measured against;
only its framing is stale.

**6. A precision claim the audit downgraded.** In "Why it was blocked":

> median turn **2m03s**, p75 5m50s, p90 11m22s, p95 15m17s

Not falsified, but DRC-4271's replay across five slicings reproduced the median, p90, ≥10m and ≥20m
figures and reported **p75 and p95 as reproducing only approximately** (p75 came out 5m15s–5m40s;
p95 straddled). The body states all four to the second as though equally firm. The fix is the
sample, not the numbers: 558 turns across five slicings rather than 94 across one.

One further defect in the record, not a falsification and not repaired here. The pre-edit capture
shows Linear's serializer moved two emphasis boundaries in "Two corrections to this issue's own
claims" — `**The **` before a code span, and a second bullet that lost its opening bold. The FO
dispositioned that class Polish/decline in cycle 1. The drafts below are authored so the trigger
does not fire again: no emphasis boundary touches a code span, a link, or a bare issue identifier,
since Linear's auto-mention of bare identifiers splits emphasis runs as well.

### Drafted edits — for the gate to authorize, not yet written

Three writes plus one that belongs to the captain. `implementation` performs 1–3 in order; 4 is
drafted for the captain to authorize or decline separately, because it edits a record this issue
does not own.

#### 1. Rewritten DRC-4029 body, and the state moved to Canceled

The forward-looking body is **3,050 characters against the current body's 5,900** before `History`.
Nothing is deleted: the four sections this cycle supersedes are demoted to dated historical sections
with the specific sentence that failed named in each label, and the five 2026-08-23 blockquotes
already under `History` carry forward untouched.

`## What would reopen it` follows the convention D5 set when it was cancelled, so a later reader
finds the reopening condition where the board already puts it.

````markdown
Board item **D6**. **Cancelled 2026-08-28**, on the measurement below rather than on a change of mind: after DEC-7 ruled, the statistic this item needs was shown to have a ceiling of about ninety seconds at the load it exists for.

**Release row:** r1 · **Journey stage:** Mid-flight · **Outcome group:** Spend attention well

## What it is

One clock time instead of twelve ETAs: a time you could write on a calendar, computed over the per-turn estimates every working card already shows.

## Why it is cancelled

DEC-7 ruled on 2026-08-28 that Cargento may not publish a walk-away clock time whose plain reading is an all-clear, on partial coverage. That ruling was narrower than cancelling this item, and deliberately so: the narrow claim settled 2026-08-23 — *the soonest expected completion among turns we can estimate*, coverage beside it — is not an all-clear and survived it. This section is what happened when that surviving claim was measured.

Every statistic the ruling leaves standing makes one shape of promise: *nothing you can predict will be ready before X*. That is sound only if X is no later than the true soonest completion, so **the true soonest completion is a hard ceiling on every candidate** — including ones nobody has thought of, because the ceiling is a property of the workload rather than of the estimator.

The ceiling was measured over 5,922 sampled instants drawn from 541 turns across 44 sessions, of which 375 had two or more sessions working at once, comparing what this code would publish against a perfect estimator with total coverage:

| at two or more concurrent sessions | median lead | p90 | ≥ 20 minutes |
|---|---|---|---|
| what `turn_progress` would publish | 2m15s | 4m49s | 0 of 375 |
| a perfect estimator, total coverage | 1m16s | 4m59s | 0 of 375 |

At three or four concurrent sessions the perfect estimator's ninetieth percentile is 2m36s, and it did not reach five minutes once.

Three things follow, and together they close the item.

**Better inputs make it worse.** The perfect estimator's median lead is *earlier* than the flawed one's, because a minimum taken over more rows is smaller. Every direction this roadmap is already moving — wider ETA coverage, needs-input detection on more harnesses, better estimates — lowers this number. An item with that shape does not become buildable later.

**The one candidate the ruling left genuinely open fails on both axes at once.** Publishing the minimum only when it is at least T minutes out — refusing visibly, the convention calm mode's `fastest` ordering already sets — renders on 0 of 375 instants at twenty minutes. Lowered to ten minutes it renders three times and reality beat it all three, by a median of 10m42s. Rare and wrong is the combination that cannot be tuned out.

**What survived the redundancy penalty is what the ruling forbids.** This item is a subset of D4 with a penalty of 42, and its own record says one thing survives it: *one clock time you can write down or hand to somebody, which supports pre-committing to a 20 minute errand.* That pre-commitment may no longer be published, and the twenty-minute window it would rest on did not occur once in 375 sampled instants.

Where the number does work, the item is redundant. At a single working session the lead time clears twenty minutes 6.7% of the time — but at a single working session this aggregate is that card's own estimate, already on screen.

## What would reopen it

- **A workload with a real ceiling.** Re-run the probe. If the perfect-estimator minimum at two or more concurrent sessions clears twenty minutes in a material fraction of instants — above 10%, against 0 of 375 here — the errand value exists and this ships as the plain minimum. The measurement is machine-specific by construction and another machine derives its own.
- **`turn_progress` changing its history rule.** If it stops drawing history per session, or publishes an estimate for a turn that has outrun its own history, the coverage and bias figures behind both triage cycles are void and the reasoning needs re-deriving.

What does **not** reopen it: needs-input detection reaching the remaining harnesses. That completes the coverage an *attention* all-clear rests on, which is D5's product, not this one's. This item's number is a completion estimate and its ceiling is the workload.

## Scores

Impact 65, risk-adjusted 47, access 85, build 15, detector risk 18. Estimate XS. Quadrant marked unsettled, within 5 points of the impact cutoff. Left unchanged as the board's record, including at cancellation.

Detector risk 18 was scored against "is the ETA right". It covers none of what actually stopped this: the statistic is wrong for the workload, the number hides its own coverage, and that coverage is biased toward the fast half of the board.

## History
````

The `## History` heading above opens the demoted sections. `implementation` writes them in this
order, then the five existing 2026-08-23 blockquotes verbatim beneath, unchanged:

| New historical section | Label it carries |
|---|---|
| "The decision landed 2026-08-28, and the answer is No" | *2026-08-28 — the DEC-7 ruling as recorded when it landed (carried forward in compressed form above; the full reasoning is on DRC-4271, which is closed)* |
| "Why it was blocked" | *2026-08-28 — as written when the item was blocked. Two figures in it are superseded: the coverage sentence was an n=1 observation and the replay over 558 turns gives 80% of turns and 64–71% of wall-clock; and the closing sentence describes a gate that was removed the same day. "The rows without one are the rows running longest" understates the excluded set, which also holds every session on its first turn. "Six days after D5 was cancelled" is five.* |
| "Two corrections to this issue's own claims" | *2026-08-28 — both still stand and neither is superseded; demoted only because the item is closed* |
| "What survives for the build, once the decision lands" | *2026-08-28 — the decision landed the same day; what this section describes is what the 2026-08-28 measurement was taken against* |

Nothing else moves. Every blockquote already under `History` stays byte-identical, including the
`DRC-4172` link inside it, which cycle 1 confirmed survives because Linear does not convert
references inside blockquotes.

#### 2. Milestone correction — "Spend attention well"

The 2026-08-28 update is amended in place rather than followed by a second section dated the same
day, which would leave two same-day updates disagreeing about whether D6 is blocked. Nothing below
that section is touched.

**Replace the heading:**

> `## Update 2026-08-28 — D6 is blocked on a decision, and this group now has no buildable walk-away item`

with:

> `## Update 2026-08-28 — D6 is cancelled, and this group has no walk-away item left`

**Replace the opening sentence** — currently "was triaged against the code and against live stores
on 2026-08-28 and is **Blocked** on a new decision issue" — with a sentence recording that the item
was triaged, blocked, ruled on and cancelled the same day. The rest of that paragraph, including
"the outcome this group is named for — look away safely — currently has nothing on it anyone can
build", is unchanged and is now literally rather than temporarily true.

**Replace the last two sentences of the "Which leaves the decision" paragraph.** "That question is
filed as a decision issue blocking D6" describes a gate that no longer exists. The needs-input
sentence after it is accurate and stays.

**Append one paragraph**, the only new prose:

````markdown
**The decision was ruled the same day, and D6 was cancelled on what the ruling left standing.** The ruling was No: no walk-away clock time whose plain reading is an all-clear, on partial coverage. It was deliberately narrower than cancelling D6, because the narrow claim — *the soonest expected completion among turns we can estimate* — is not an all-clear and survived it. Measuring that surviving claim closed the item. Every statistic the ruling permits promises "nothing you can predict will be ready before X", which is sound only if X is no later than the true soonest completion, so the true soonest completion is a ceiling on all of them. Across 375 sampled instants with two or more sessions working, a perfect estimator with total coverage had a median lead of **1m16s** and never once reached twenty minutes — the window D6's own surviving value was scored on. The ceiling is the workload, not the estimator, and it moves the wrong way as coverage improves, because a minimum over more rows is smaller. So this group's outcome now waits on B2 completing needs-input coverage, which is D5's shape rather than D6's.
````

#### 3. State, labels and relations

- **State:** `Todo` → `Canceled`.
- **Labels:** unchanged — `origin:workshop`, `alternative`, `cutoff:unsettled`, `release:r1`,
  `journey:mid-flight`. `cutoff:unsettled` stays accurate and the board's record is not revised at
  cancellation, which is the discipline both prior cycles kept with the scores.
- **Relations:** unchanged. The four `relatedTo` edges — DRC-4271, DRC-4172, DRC-4028, DRC-4272 —
  all stay. No new edge is needed: DRC-4272 already relates to this issue.
- **Scores:** unchanged, as recorded in the drafted body.

**One consequence for `selection`, recorded and not acted on.** This was the board's only open
`release:r1` item. Cancelling it leaves Release 1 with nothing open, so the next `selection` pass
picks under rule 3 or later.

#### 4. DRC-4272 — one sentence, for the captain rather than for this cycle

Held separately because it edits a record this issue does not own, and because it is only correct if
the gate approves cancellation. DRC-4272 closes with a conditional that cancellation makes true:

> D5's weightiest recorded cancellation reason was that D6 already exists and the board prefers it.
> If D6 is later cancelled, that reason disappears retroactively and this issue becomes the second
> half of the case for looking at D5 again.

The honest edit is to replace "If D6 is later cancelled" with the fact, and to add the two limits
this cycle established so that the strengthened case is not read as more than it is: D5's other two
ranked cancellation reasons are untouched, and DEC-7's ruling constrains D5 harder than it constrains
D6, since D5 is the stated all-clear on thinner coverage. **Recommended, not drafted as final prose,
and explicitly the captain's call** — the scope notes asked for the assessment and reserved the
decision.

### Acceptance criteria

The product of this cycle is a recommendation and three record writes, so the criteria hold the
measurement and the writes rather than a build.

**Offline** — a fresh agent reproduces these without a human:

1. **The ceiling result reproduces.** *Verified by:* `drc-4029/probe_min_lead.py`, run from
   `cargento/skills/cargento`. At k ≥ 2 the oracle minimum's median lead is under two minutes and its
   ≥20m share is 0%. **Falsified by** that share rising above roughly 10%, which is exactly the
   condition the drafted body names as reopening the item. **Declared machine dependency:** it reads
   the live `~/.claude/projects` store, so the numbers are this machine's and the method is portable.
2. **The suppression rule fails on both axes.** *Verified by:* the same probe's final block. At
   T = 20m it renders on 0 instants; at T = 10m it renders and is wrong every time. **Falsified by**
   a render rate above a few per cent at T = 20m, or a wrong rate that falls as T rises.
3. **The probe shares DRC-4271's harness rather than a re-implementation.** *Verified by:*
   `diff <(sed -n '/^def intervals/,/^    return out/p' drc-4029/probe_min_lead.py) <(sed -n '/^def intervals/,/^    return out/p' drc-4271/probe_max_error.py)` returns empty, and both print the
   same `sessions=` and `turns=` line on the same store. **Falsified by** either diverging, which
   would mean the minimum and maximum were measured over different moments.
4. **The optimistic-bias mechanism still exists in the code.** *Verified by:* `turn_progress`
   returning `eta_h is None` for a scan whose `durations` are all shorter than `elapsed`
   (`turns.py:405-410`). **Falsified by** the empty-`cands` branch publishing a figure, which would
   void the coverage and bias reasoning in both cycles.
5. **The writes land as drafted.** *Verified by:* a post-write `get_issue` on DRC-4029 showing
   `status: Canceled`, the five labels unchanged, the four `relatedTo` edges intact, the Scores line
   byte-identical, and all five 2026-08-23 blockquotes byte-identical under `History`. **Falsified
   by** any of those moving.

**Interactive** — needs the captain:

6. **The cancellation itself.** *Verified by:* the captain's ruling at this gate. Cancelling a board
   item is a product judgement; the measurement bounds it but does not make it.
7. **Whether DRC-4272 is edited.** *Verified by:* the captain's answer. Draft 4 is deliberately not
   written as final prose for this reason.

### Expected surface and tolerance

**This stage's own repository surface: two files, both new, both under this entity's state
directory** — `drc-4029/probe_min_lead.py` and `drc-4029/README.md`. Tolerance: ±0. No file under
`cargento/` changes, and no test runs, because no shipped code is touched.

| Surface | Change | Tolerance |
|---|---|---|
| DRC-4029 body | rewritten to the cancellation; four 2026-08-28 sections demoted to dated history | ±1 issue |
| DRC-4029 state | `Todo` → `Canceled` | exactly 1 |
| "Spend attention well" milestone | the 2026-08-28 update's heading, two sentences, and one appended paragraph | ±1 paragraph |
| DRC-4272 | one sentence, only if the captain authorizes draft 4 | 0 or 1 |

**Semantics that may move: none.** No payload field, no `cargento_runtime/web/` change, no
`tests/test_page.py` byte pins. The build this item was holding open is not being deferred — it is
being closed — so the one-in-flight-PR constraint on `web/` is released rather than scheduled.

### Test plan

No repository test is added or run, because no shipped file changes. The measurement is held by the
committed probe rather than by a unit test, for the reason DRC-4271 gave and this cycle confirms: a
test pinned to one machine's session history asserts the fixture, not the behaviour. The probe is
committed so the *method* is reproducible even though the *numbers* are not; `drc-4029/README.md`
records how to run it and what would falsify each figure.

### Review depth

**Self-verify.** From `AGENTS.md`'s Calibrating Effort table: no user-visible behaviour change and
nothing calls it — this cycle ships no code at all, and its product is a recommendation the gate
rules on. The evidence that would normally justify adversarial lenses is instead carried by the
probe, which a reviewer re-runs in ten seconds rather than reasoning about.

### Out of scope

- **Re-litigating DEC-7.** The ruling is settled and it is the captain's. Where this cycle touches
  it, it applies it.
- **Reopening or re-scoping D5.** Assessed above because the scope notes asked for the assessment;
  the call is the captain's and draft 4 is the whole of what this cycle proposes.
- **B2's remaining six harnesses.** DRC-4014 owns them. This cycle's finding is only that completing
  them does not reopen this item.
- **Revising the scores.** Impact 65, risk-adjusted 47, access 85, build 15, detector risk 18 stay as
  the board's record, at cancellation as before.
- **Repairing the serializer damage in the existing body.** Dispositioned Polish/decline by the FO in
  cycle 1. The drafted rewrite replaces that text anyway and is authored so the trigger does not fire.
- **The `?next=true` frontend.** It renders `elapsed_h` and never `eta_h`, so it never had a home for
  this statistic and now never needs one.

## Stage Report: triage (cycle 2)

- DONE: The re-scope-or-cancel question is answered with a recommendation and the evidence for it: given the ruling that no all-clear may be published, and given all three measured statistics are refused, either name a fourth statistic that carries the narrow claim honestly and is worth its build, or recommend cancellation. Say which, and say what would change the answer.
  **Recommend cancellation.** The evidence is a new probe, `drc-4029/probe_min_lead.py`, which measures the ceiling on every statistic the ruling permits rather than one candidate at a time: any permitted claim is *nothing you can predict will be ready before X*, sound only if X is no later than the true soonest completion. Over 375 instants with two or more sessions working, a perfect estimator with total coverage had a median lead of 1m16s and reached twenty minutes 0 times. The strongest fourth candidate — the settled minimum plus a suppression rule, publishing only when the window is worth leaving on — was built and measured: 0 of 375 renders at T=20m, and at T=10m it rendered 3 times and reality beat it 3 times. Falsified by the k≥2 oracle ≥20m share rising above ~10%, which is the reopening condition written into the drafted body. Three further candidates are recorded as considered and rejected on what they would say rather than how often.
- DONE: Two stale passages in DRC-4029's own body are corrected in the drafted rewrite, both left over from before the ruling: the n=1 coverage claim "One live collect at that moment: two working sessions, one carrying an ETA", superseded by DRC-4271's replay of 80% of turns and 64-71% of wall-clock; and the closing sentence "It is filed as a decision issue and this item blocks on it", which the ruling made false. Report any other passage you find that the ruling or DRC-4271's corrections falsified.
  Both corrected, and **four more found**, listed with quotations under `### Passages in the current body that the ruling or DRC-4271 falsified`: the optimistic-bias mechanism overstated as "the rows without one are the rows running longest" (DRC-4271 corrected the excluded set to include every session on its first turn); "six days after D5 was cancelled" is five, and disagrees with the milestone's own text; a heading that still says "once the decision lands"; and p75/p95 stated to the second when DRC-4271's audit reproduced only the median, p90, ≥10m and ≥20m figures. The drafted body carries the corrections forward and demotes the cycle-1 text to a dated historical section whose label names each failed sentence, so the 2026-08-23 blockquotes stay verbatim.
- DONE: Nothing is written to Linear. If the recommendation is cancellation, the knock-on to D5 is assessed but not acted on: DRC-4028's weightiest cancellation reason was that D6 exists and the board prefers it, and DRC-4272 already records that D5's reopening condition is met. Say whether those need a filing or an edit, and leave it for the captain.
  No Linear write tool was called — only `get_issue`, `get_milestone` and `list_comments`, which returned zero comments. **Neither a filing nor a new issue: one sentence on DRC-4272**, whose closing line already anticipates this case as a conditional that cancellation makes true. Drafted as recommendation 4, deliberately not as final prose, and reserved for the captain. The assessment also records what the knock-on is *not*: D5's other two ranked cancellation reasons are untouched, and DEC-7 constrains D5 harder than D6, since D5 is the stated all-clear on thinner coverage. So the reopening case gains one reason and one new constraint at the same time.

### Evidence exercised rather than asserted

- `probe_min_lead.py` — ran it; the ceiling and suppression tables are its stdout. Falsified by the k≥2 oracle `>=20m` column leaving 0.0%.
- `probe_max_error.py`, DRC-4271's own probe, re-run unchanged — reproduces its published result on today's store (0 of 71 full coverage at k=3–4 against 0 of 82; 87% early at k=3–4, matching). **One figure drifted and is reported rather than repeated:** the k=3–4 median understatement is 6m52s today against the 9m50s the ruling quotes. Same direction and order, different number; the store grows daily.
- `diff` of the `intervals()` function across both probes returns empty, and both print `sessions=44 turns=541` on the same store — so the minimum and the maximum are measured over one set of moments, not two. Falsified by either output diverging.
- `turn_progress` with `durations=[60,120,180]` at elapsed 600 returns `eta_h None`; at elapsed 60 it returns `1m`. Falsified by the empty-`cands` branch publishing a figure, which would void the bias reasoning in both cycles.
- Code claims re-checked at `v0.17.1` after `main` moved: `long_turn_warn_sec=900` at `config.py:444`, and `grep -c 'reports_needs_input=True' aggregate.py` returns 4.

### Summary

The ruling left one question open and it turned out to be answerable by measurement rather than by
argument. Every statistic DEC-7 permits makes the same shape of promise, and that promise is bounded
by the true soonest completion — so instead of testing a fourth candidate, this cycle measured the
bound itself, with an oracle that assumes perfect estimates and total coverage. At the load this item
exists for the bound is about a minute and a quarter, and it never once reached the twenty-minute
window D6's own surviving value was scored on. The item also degrades as the rest of the product
improves, because a minimum over more rows is smaller: B2 landing makes D6 worse, not better.

The strongest genuinely-open candidate was built and measured rather than reasoned about, and it
failed on both axes at once — never rendering at the useful threshold, and wrong every time it
rendered at a lower one. **Recommendation is cancellation**, with a reopening condition written into
the drafted body as a probe a later reader can re-run rather than a judgement they have to trust.

Six falsified passages are corrected in the drafted rewrite, four more than the scope notes named.
Nothing was written to Linear. The knock-on to D5 needs one sentence on DRC-4272 rather than a
filing, and that sentence is the captain's to authorize.
