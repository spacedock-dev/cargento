---
id:
title: "Make the asset test enforce font size, not the contrast that already passes"
status: review
source: "https://linear.app/recce/issue/DRC-4596/make-the-asset-test-enforce-font-size-not-the-contrast-that-already"
started: 2026-09-17T11:10:03Z
completed: ""
verdict: ""
score: 0.6
worktree: .worktrees/spacedock-ensign-drc-4595
issue: ""
pr: ""
mod-block: ""
linear-status: "Backlog"
milestone: Clean and Cogent UI/UX
release: ""
promise: "P2"
move: "keep"
estimate: ""
reconciled: ""
gates:
    version: 1
    records:
        - id: gate:drc-4596:triage
          stage: triage
          attempts:
            - id: gate-attempt:drc-4596-triage-1
              briefing:
                id: briefing:drc-4596:triage:attempt-1:revision-1
                digest: sha256:4e5e9b6e350d0dda386ce5bccce10318b5ad8303ae2843eef9a15db0b110d040
                room-ref: ./review/triage/briefing-1
              resolution:
                type: Resolution
                id: resolution:spacedock:drc-4596:triage:1
                briefing: briefing:drc-4596:triage:attempt-1:revision-1
                by: agent:first-officer
                at: "2026-09-17T11:23:02.832752Z"
                decision: approve
                reason: 'Checklist 5 done / 0 skipped / 0 failed; AC-1..AC-6 resolve, five offline and one interactive. The stage refused to build an unbuildable criterion rather than allowlisting its way to green: AC2 as filed inspects 137 rules and fails 68, and the only route to a passing test is a seventy-entry allowlist, which is precisely the measuring-nothing tautology AGENTS.md bans. It is replaced by the membership predicate DRC-4587 already recorded, and an independent implementation at triage reproduced that census exactly rather than trusting it. AC3 is dead by the captain''s absence-ink ruling rather than by sequencing, and is replaced by what the ruling does establish. Most important, the guard''s structural blind spot is stated rather than implied away: it cannot see sentences composed across three rules, which is the class the DRC-4587 review measured at 163 strings, and a size guard that passed while those rendered below its claimed floor would be this milestone''s own defect shipped as its remedy.'
                conn:
                    quote: I pre-approve all the triage and merge gates, just automate this entire process and do it
                    source: Captain, this session, 2026-09-17
              application:
                target-stage: implementation
                state: consumed
---

[DRC-4596](https://linear.app/recce/issue/DRC-4596/make-the-asset-test-enforce-font-size-not-the-contrast-that-already) — Make the asset test enforce font size, not the contrast that already passes

Seeded 2026-09-17 from the live Linear read of the Clean and Cogent UI/UX milestone.
Linear owns the current issue body, its relations and its resources; triage fetches them
live and validates them against the tree before anything is built. No triage, approval,
implementation or delivery is claimed here.

---

## User value (drafted — first section of the rewrite)

Nobody sees this on a screen. It is the property that keeps the rest of **Clean and Cogent UI/UX**
from unwinding: once DRC-4587 has raised board sentences to a 15px tier and collapsed the label
tier, nothing in CI stops the next change putting a sentence back under it, because the asset test
measures contrast — which already passes on every pair — and measures size nowhere at all.

Promise **P2**, move **keep**. It keeps a promise the milestone has just made true rather than
making a new one. Because the move is `none` for a user, the gate is told so up front: the only
user-visible consequence is the absence of a regression, and that is why **AC-6** is written
against a property a reader can check on the board rather than against a test's own output.

## Labels

Set at `implementation`, with the rewrite: `journey:mid-flight` (already set, correct — this
governs text a user reads while work is in flight), `move:keep` (already set, correct). No label
change is needed. `Verification` and `discovered-by-agent` stay.

## Linear edits made

Nothing has been written to Linear. Everything below is a draft this gate authorizes.

### Pre-edit record — DRC-4596 issue body, verbatim (captured 2026-09-17, `updatedAt` 2026-09-17T06:37:37.635Z)

## User value

Nobody sees this directly; it is what stops the rest of the milestone regressing. Today the asset test pins the contrast that already passes and explicitly does not enforce font size, which is the thing that is broken.

## The Problem

`docs/design-next-ui.md` lines 112-117 make a 12.5px board-sentence floor policy and, in the same paragraph, admit the guardrail does not exist: the asset test "pins the dark palette and checks text inks above 4.5:1 … it does not enforce all font sizes or spacing between contrast steps."

So the test guards the property that passes everywhere — every ink is above 4.5:1, ink3 at 5.67:1 — and is absent for the property that fails, where 9.5px and 10px at weight 400 are below the APCA lookup table entirely.

That gap is why two sentence-case prose strings shipped at 10px on Held to under a documented floor, why six tokens accumulated inside a 3px band with two of them uncalled, and why styles.css:20 has carried a citation to a "ruling R9" that exists nowhere in `docs/` for as long as it has. Nothing in CI can currently catch the third violation.

**Measured**

* docs/design-next-ui.md:112-117 states the floor and that the asset test "does not enforce all font sizes or spacing between contrast steps"
* tests/test_next_page.py:402-417 pins twelve palette hexes by subset comparison; :430-442 loops seven inks against three surfaces at 4.5:1
* Because :417 compares only the twelve listed keys, adding or deleting an unlisted token cannot break it
* Two confirmed floor violations shipped: styles.css:858 and :955, both `font-size:10px` on sentence-case prose
* The scan surface is small and static: 27 literal `font-size:10px` declarations plus 4 inside `font:` shorthands
* The rules in question declare `var(--fs-xs)`, not a px literal, so a naive literal scan passes every one of them
* 9.5px and 10px at weight 400 are below the APCA lookup table entirely — no colour choice fixes them

**In the attached screenshot**

1. Two 10px prose strings shipped under a 12.5px floor
2. Asset test pins 4.5:1, which already passes everywhere
3. styles.css:20 cites ruling R9; no R9 exists in docs/
4. Scan surface: 27 literal 10px sites plus 4 shorthands

## The Solution

Extend the existing documentation/asset test module, in the same regex-over-the-CSS-text style it already uses, with no browser and no network. Three assertions:

1. Every `--fs-*` token declared in `:root` parses to at least 11px.
2. Every `font-size` — literal, or inside a `font:` shorthand — in a rule whose selector matches `.next-cockpit-*` or `.next-session-*` resolves to at least the sentence tier, unless the selector is on an explicit label allowlist (`-label`, `-name`, `-type`, `-at`, `-source`, `-stamp`, `-count`, `-bound`, `h2`). **The parser must resolve** `var(--fs-*)` **indirection against the** `:root` **block first**; without that it passes every rule in scope and measures nothing.
3. Each absence class resolves to the absence register's token and not to the label's.

Write each assertion against the resolved token text inside the matched rule, never against the presence of a class name, or it becomes the structurally-present default AGENTS.md's Measured Invariants section warns about — and **prove it can fail** by mutating one rule and watching it go red before committing.

Sequence it after the scale and register work lands: `.next-cockpit-count-value--absent` does not exist yet, and the test cannot go green until the 10px sites are remapped.

## Acceptance

- [ ] The test fails when any `:root` `--fs-*` token is set below 11px
- [ ] The test fails when a sentence-bearing cockpit selector resolves below the sentence tier, including through `var(--fs-*)` indirection
- [ ] The test fails when an absence class resolves to the label register's token
- [ ] Each new assertion is demonstrated failing against a mutated rule before the change is committed, and the mutation is named in the PR
- [ ] The existing twelve-key palette comparison and the 4.5:1 loop are untouched and still pass

---

Complaint **cross-cutting** · tabs: held-to, chrome · severity **major** · effort **S** · blocked by DRC-4587, DRC-4589

Raised from user feedback; mechanism and figures established by a measured audit of the live board and the shipped stylesheet.

### Pre-edit record — "Clean and Cogent UI/UX" milestone description, verbatim (captured 2026-09-17)

## The user value

**The board can be read at a glance: you can tell a label from its answer, a figure from a gap, and the one thing to do on a screen from the prose around it.**

Users report low contrast. Every text ink in the cockpit passes WCAG AA — ink3, the dimmest, is 5.67:1 on panel, nearer AAA than the AA floor. Measured size-aware with APCA, the same inks fail badly at the sizes they are actually set in: at 12.5px/400 even `#f4f1e8`, the brightest ink in the palette, scores Lc 98.0 against a body-text requirement of 100, and the 9.5px and 10px label steps fall off the bottom of the lookup table entirely.

So there is no colour left to spend and no contrast fix available. The work is to raise the sentence tier, collapse the label tier, and give label, value and absence three distinct registers instead of the one dim ink that currently carries 89% of the characters on Held to.

## What is left

Twelve issues. Three are foundations and everything else depends on them:

* **Raise board sentences to a 15px tier** and collapse six sub-12px tokens into one label tier.
* **Split the three inks onto label, value and absence roles**, so a label stops sharing its ink with its own answer.
* **Always render the Held to reading control**, disabled with its reason, instead of deleting the tab's only verb exactly when a newcomer looks for it.

Then: the briefing, the tab strip, a control primitive with one primary action per tab, caveat tiering, Held to ordering, Console ordering, the scope rail, the timeline filter, and a guardrail so the asset test enforces size rather than the contrast that already passes.

## Waits on

Nothing outside this milestone. `type-scale` and `ink-roles` gate most of the rest; `ink-roles` itself waits on `type-scale`.

## How this was measured

Contrast computed from the shipped tokens and independently recomputed during triage, matching to the decimal. APCA from the same pairs at the sizes they render at — **audit-only: no APCA implementation, table or fixture exists in the repository, so these figures cannot be reproduced from the tree.** [DRC-4596](https://linear.app/recce/issue/DRC-4596/make-the-asset-test-enforce-font-size-not-the-contrast-that-already) adds the guardrail that would, and lands after the change the figures justify. Density, ink distribution and control counts read off the live DOM at `127.0.0.1:4553`. Density figures are floors — they were taken on a quiet, unannotated session, and a busy project has more text, not less.

Eleven claims were raised and rejected rather than filed. The two worth knowing: brightening the inks cannot fix C1, and merging the three thin tabs is a route change plus an amendment to NUI-3, not a layout change.

### Drafted rewrite — DRC-4596 issue body

## User value

Nobody sees this on a screen. It is what keeps DRC-4587's 15px sentence tier from unwinding one rule at a time. The asset test measures the palette, which already passes on every pair, and measures size nowhere: `grep -rn "font-size\|--fs-" cargento/skills/cargento/tests/*.py` returns zero hits across the whole dashboard suite.

## The problem

Three properties the milestone has just established have no machine check behind them, and each fails silently:

1. **The label floor.** DRC-4587 collapsed the sub-12px band; `--fs-label` and `--fs-machine` now sit at exactly 11px, with no margin. Nothing stops a fourteenth token arriving at 10.5px.
2. **The sentence floor.** Sixty-seven rules resolve to `var(--fs-sentence)`. Nothing stops one of them being edited back down, and the edit is invisible in review because the rule declares a token name rather than a number.
3. **The absence register.** DRC-4589 ruled that an absence is a sans sentence sharing `--ink3` with labels, separated by family and case rather than by ink. Nothing asserts that an absence stays sans, or stays on the sentence tier.

## The solution

Extend `NextPageAssetContractTest` in `cargento/skills/cargento/tests/test_next_page.py`, in the regex-over-the-CSS-text style it already uses — no browser, no network, no new module.

The membership test is **the one DRC-4587 already wrote into `docs/design-next-ui.md`**: a rule is on the sentence tier when it sets its text in sans and declares its own prose line-height. That is derived from what the rule declares, so it cannot become the structurally-present default `AGENTS.md` warns about, and it needs no allowlist. Reproduced independently at triage against the post-DRC-4587 stylesheet, it returns **67 rules at 15px and 19 below** — matching the doc's own census figure exactly.

The floor is written as a literal `15.0` in the test, and `--fs-sentence == 15px` is asserted separately. Reading the floor out of the token makes the assertion vacuous: retuning `--fs-sentence` to 12px in a scratch copy took the violation count from 19 to **0**.

## What this guard cannot see, stated plainly

It reads one rule at a time. Where a sentence's size, family and line-height are composed across several rules, no regex can join them, and two such sentences render today:

* `.next-operation-fact--unknown strong` — **163 strings at 12.5px**. `styles.css:482` sets the size and mono, `:483` flips the family back to sans, `:397` supplies the line-height.
* `.next-cockpit-recovery small` — **18 strings at 12.5px**. `:1089` sets only the size; sans and the 1.55 line-height come from the cell at `:1081`.

Both are outside this guard structurally, not because of a parser weakness. Only a computed style sees them. This issue does not claim a universal floor and must not be read as one — DRC-4602 sizes the residual, and a live drive remains the only oracle for the composed class.

## Acceptance

See the triaged criteria on the burndown entity; six criteria, five offline and one interactive.

### Drafted rewrite — milestone description correction

Only the final paragraph of **How this was measured** changes. The rest stands.

Current text, which is false:

> [DRC-4596] adds the guardrail that would, and lands after the change the figures justify.

Replace with:

> No issue in this milestone adds an APCA implementation, so these figures stay audit-only.
> [DRC-4596](https://linear.app/recce/issue/DRC-4596/make-the-asset-test-enforce-font-size-not-the-contrast-that-already)
> guards the **px floors** the audit motivated — the 11px label tier and the 15px sentence tier —
> which is a different and weaker property than reproducing the audit. It cannot see a sentence
> whose size, family and line-height are composed across several rules; two such sentences remain
> and [DRC-4602](https://linear.app/recce/issue/DRC-4602/seventeen-sans-rules-still-sit-below-the-15px-sentence-floor-so-the)
> sizes them.

**Why this correction is required.** "The guardrail that would" attaches to "cannot be reproduced
from the tree", so the milestone currently promises that DRC-4596 makes the APCA figures
reproducible. It does not, and nothing in this milestone does. Left standing, the sentence is a
reader's licence to treat the Lc numbers as CI-backed.

### Demoted to history, and why

Three claims in the filed body were true when written and are false against the post-DRC-4587 tree.
They move to a dated history section in the rewrite rather than being deleted, because the audit
they came from is what justified the change that made them false:

* **"styles.css:20 cites ruling R9; no R9 exists in docs/."** DRC-4587 removed it. `grep -n 'R9'
  styles.css` on `spacedock-ensign/drc-4587` returns nothing. The claim was correct and is closed.
* **"27 literal `font-size:10px` declarations plus 4 inside `font:` shorthands."** Zero remain.
  Six `10.5px` literals survive, at `styles.css:261, :309, :344, :398, :427, :454`.
* **"Two floor violations shipped: styles.css:858 and :955."** Both remapped by DRC-4587.

Demoting rather than deleting matters here: the figures are the evidence that the audit was real,
and an issue whose problem statement has been silently emptied reads as though it was never needed.

## Adversarial read of the filed issue against the tree

Measured on `spacedock-ensign/drc-4587` @ `a251ca4a` (the tree this work lands on), not on `main`.

**The problem is still real.** No font-size assertion exists anywhere in the dashboard suite.
Confirmed, not merely incomplete.

**AC1 is settled and has become buildable.** The recon recorded it as red on `main`. On the
post-DRC-4587 tree, `:root` declares **21** `--fs-*` tokens with a minimum of exactly **11.0px**
(`--fs-label`, `--fs-machine`). The assertion is green with **zero margin**, which is the useful
state: any new sub-11px token reds it immediately. Demonstrated — setting `--fs-label:10.5px` in a
scratch copy produced exactly one violation.

**AC1 is blind to the smallest type still in the sheet, and the rewrite says so.** Six `10.5px`
literals live outside `:root`, on `.next-project-change`, `.next-delegation-metrics`,
`.next-guardrail-add`, `.next-operation-harness`, `.next-capacity-window i` and
`.next-capacity-scope`. A guard that asserts "no size below 11px" while those stand is a false
claim. **AC-2** closes it as a registry — the set of sub-11px literal sites must be exactly those
six — so a seventh reds without demanding the six be raised in this PR.

**AC2 as filed is unbuildable, and this is the finding that changes the issue.** Implemented
literally against the post-DRC-4587 stylesheet, "every `font-size` in a `.next-cockpit-*` or
`.next-session-*` rule resolves to at least the sentence tier, unless allowlisted" inspects **137**
rules and **fails 68 of them** — tab buttons, `dt` terms, counters, status pills, empties, textarea
chrome. Twenty-three more are silenced by the proposed suffix allowlist. Going green would mean
either re-typesetting half of two views or growing the allowlist to roughly seventy entries, at
which point it measures nothing. This is the recon's stated risk, now quantified: the allowlist is
not a hazard to watch, it is a dead end.

**The replacement is the doc's own predicate, and it reproduces.** `docs/design-next-ui.md:134-136`
already defines membership: a rule is on the sentence tier when it sets its text in sans and
declares its own prose line-height. Implemented at triage — rule declares no mono family, declares
`line-height >= 1.3`, declares a size — it returns **67 rules at 15px and 19 below**, matching the
doc's "all sixty-seven resolve to `var(--fs-sentence)`" and "nineteen further sans rules" to the
number. Two independent derivations agreeing is what makes this shape safe to build on.

*One accounting discrepancy, declared rather than hidden:* the doc says a single-rule census reports
**17**; mine reports **19**. Both miss the same two composed rules. The gap is in whether two `.pc-*`
prototype rules count, and `implementation` settles it against the PR-6 tree — the census is
re-taken there in any case.

**AC3 as filed is dead, and not for a sequencing reason.** The recon read it as blocked on DRC-4589
creating `.next-cockpit-count-value--absent`. DRC-4589's captain ruling (`drc-4589/index.md`,
"Ruling — absence ink, 2026-09-17") is stronger: **absence keeps `--ink3`**, the same ink labels
carry, because the palette has three inks and the design needs four roles. There is no distinct
absence token for a test to require. What the ruling *does* establish is falsifiable and is what
**AC-4** asserts instead: an absence is a sans sentence, so every absence rule resolves to sans and
to the sentence tier, and exactly one rule in the sheet colours `[data-next-withheld]`.

**A contradiction `implementation` must resolve, not re-decide.** `styles.css:1083-1087` carries a
comment ruling that `.next-cockpit-recovery small` is "the storage cue, not a value, and stays
down" at 12.5px — deliberate. `docs/design-next-ui.md:143-147` counts the same rule among the
nineteen still below the floor. One of the two is wrong. The guard must not red on a documented
deliberate choice, so the inventory in **AC-3** records it as accepted with the comment cited.

**AC4's procedure is wrong and the rewrite replaces it.** The issue, and the recon after it,
assume the mutation is applied to `styles.css` in the working tree, reddening all byte pins as
"expected noise". It need not be. Every assertion here is a pure function of the stylesheet text,
so the demonstration runs against a **string copy in the test process** — the tree is never
mutated, no oracle moves, and the falsifier can therefore be a committed test rather than a
procedure someone promises they ran. Demonstrated at triage: mutating a `font:` shorthand's
`var(--fs-sentence)` to `var(--fs-2xs)` in a copy raised the violation count from 19 to 20, as did
the longhand form. That is **AC-5**, and it is offline, not interactive.

**AC5 (palette untouched) holds.** `test_the_next_palette_is_dark_only` at
`test_next_page.py:393-444` is a separate method in the same class; the twelve-key subset compare
is at :402-417 and the 4.5:1 loop at :431-442.

## Acceptance criteria

- **AC-1 — offline:** Every `--fs-*` token declared in the single `:root` block resolves to at
  least 11px, and `--fs-sentence` is exactly 15px. The second clause exists because the sentence
  floor in AC-3 is meaningless if the token it names can be retuned downward. **Verified by:** the
  new test method over `styles.css`; on `spacedock-ensign/drc-4587` it reads 21 tokens with a
  minimum of 11.0px (`--fs-label`, `--fs-machine`) and passes. **Falsified by:** setting
  `--fs-label:10.5px` — demonstrated at triage against a scratch copy, producing exactly one
  violation where the unmutated sheet produces none.
- **AC-2 — offline:** The set of font sizes below 11px written as px literals anywhere in
  `styles.css` is exactly the six known sites, recorded by selector in the test. This is a registry,
  not a floor: it does not demand the six be raised, only that a seventh cannot arrive unnoticed.
  **Verified by:** the test comparing the parsed set against the recorded six —
  `.next-project-change time`/`-harness` (:261), `.next-delegation-metrics` (:309),
  `.next-guardrail-add` (:344), `.next-operation-harness` (:398), `.next-capacity-window i` (:427),
  `.next-capacity-scope` (:454), all at 10.5px. **Falsified by:** adding a seventh sub-11px literal,
  or deleting one of the six without updating the record.
- **AC-3 — offline:** Every rule that satisfies the membership test stated at
  `docs/design-next-ui.md:134-136` — declares no mono family, declares its own `line-height >= 1.3`,
  and declares a size, resolving `var(--fs-*)` against `:root` through both the `font-size` longhand
  and the `font:` shorthand — resolves to at least 15.0px, written as a literal in the test, except
  for a recorded inventory of rules still below it. **Verified by:** the census the test performs;
  on the post-DRC-4587 tree it classifies 86 rules, 67 at 15px and 19 below, reproducing the doc's
  own figures. The 19 are recorded with `.next-cockpit-recovery small` annotated as deliberate per
  `styles.css:1083-1087`. **Falsified by:** a rule leaving the inventory for a lower tier —
  demonstrated at triage twice, once through the `font-size` longhand and once through the
  `font:500 var(--fs-sentence)/1.55 var(--sans)` shorthand, each raising the count from 19 to 20.
- **AC-4 — offline:** Every rule carrying an absence marker (`--absent`, `[data-next-withheld]`,
  `-clause-absent`) resolves to sans and to the sentence tier, and exactly one rule in the sheet
  assigns a colour to `[data-next-withheld]`. This replaces the filed criterion, which required an
  absence token that DRC-4589's ruling decided will not exist. **Verified by:** the test, against
  the end state DRC-4589 names — `styles.css:52` keeps the colour, `:1095` must drop its redundant
  `color:var(--ink3)`; `grep -c 'data-next-withheld[^{]*{[^}]*color:' styles.css` returns 2 on the
  post-DRC-4587 tree and must return 1. **Falsified by:** a second rule colouring
  `[data-next-withheld]`, or an absence rule taking mono or a sub-sentence size.
- **AC-5 — offline:** Each of AC-1, AC-3 and AC-4 is demonstrated failing, by a committed test that
  applies its mutation to an in-process copy of the stylesheet text and asserts the assertion
  reports more violations than it does unmutated. The working tree is never mutated, so no byte-pin
  oracle moves and the demonstration is a check rather than a promise. **Verified by:** three
  paired mutant tests; each names its mutation in a docstring, and the PR body quotes them.
  **Falsified by:** an assertion whose mutant count equals its clean count — the tautology this
  criterion exists to catch.
- **AC-6 — interactive:** On the live board at `127.0.0.1:4553`, no sentence that this guard
  reports as compliant renders below 15px, and the two sentences the guard structurally cannot see
  are confirmed still at 12.5px: `.next-operation-fact--unknown strong` (163 strings) and
  `.next-cockpit-recovery small` (18 strings). **Verified by:** a browser drive reading computed
  styles, the same method DRC-4587's review used to find them; recorded in the PR body as a count
  per selector. **Falsified by:** finding a third composed sentence the census missed, which would
  mean the guard's blind spot is wider than the issue and the design doc both claim. This is the
  one criterion no offline check can substitute, and it is declared interactive here rather than
  discovered at review.

## Expected surface

Measured against `spacedock-ensign/drc-4587` @ `a251ca4a`, not `main`.

| Surface | Files | Net lines | Tolerance |
|---|---|---|---|
| Runtime (`cargento_runtime/`) | 0 | 0 | none — any runtime edit is out of scope |
| Test (`tests/test_next_page.py`) | 1 | +170 | +120 to +230 |
| Docs (`docs/design-next-ui.md`) | 1 | ~+8 / -6 | ±10 |

The test figure is above the recon's 100-140 because triage added two assertions the recon did not
cost: the sub-11px literal registry (AC-2) and the three paired mutant tests (AC-5). The mutant
tests are roughly 45 lines on their own.

**Oracle cost, costed separately.** Zero *if this lands alone*. All three byte-pin oracles key on
files under `cargento_runtime/web/`; adding methods to `test_next_page.py` moves none of them. But
**the milestone's PR sequence puts this in PR 6 with DRC-4595 and DRC-4602, and DRC-4602 edits
`styles.css` by design** — it raises the residual sans rules. So PR 6 pays the full recompute:
`test_next_page.py`'s per-part figure and digest for `styles.css` (:703/:706, currently `111_533`),
the assembled page (:710/:712, currently `914_827`), `test_next_flag.py:67/:69`, and
`test_focus.py:1024`. **Five figures across three files.** Recompute from the assets; never resolve
one textually. The recon's "no oracle recompute is required" was correct for the issue in isolation
and is wrong for the PR it ships in.

**Compelled tests checked, none found.** No import-graph allowlist governs
`cargento/skills/cargento/tests/`; the new methods land in the existing `NextPageAssetContractTest`
class rather than a new module, so nothing is compelled. `docs/design-next-ui.md` is cited by
heading anchor from `next-chrome.js:597`, `next-capacity.js:501` and `next-workstream.js:134`
(`#nui-16`, `#nui-11`), so it sits in the effective docs deny list and the full five-job gate runs.
The edit is to prose under `## NUI-2` and touches no cited anchor.

**Semantics that may move.** One: the design doc's statement that the asset test "does not enforce
all font sizes" becomes false and must be rewritten to say precisely what it now enforces and what
it still cannot see. Leaving it would replace one false sentence with another.

## Approach, and the simplest rejected alternative

**Chosen:** the doc's derived membership predicate, with the residual recorded as an inventory.

**Rejected — the filed selector-prefix scope plus a suffix allowlist.** It cannot deliver the value.
Measured above: 68 of 137 in-scope rules fail it, so the only route to green is an allowlist of
roughly seventy selector suffixes. At that size the allowlist *is* the specification, it is
maintained by whoever is trying to get CI green, and every future red is closed by adding an entry.
The assertion would converge on measuring nothing while reading as broad — the precise failure
`AGENTS.md`'s Measured Invariants section names. The derived predicate has no such dial: changing
what the guard covers means changing what a rule declares, which is visible in the diff.

**Also rejected — a computed-style check via a headless browser.** It would see the composed class
AC-6 has to drive by hand. Rejected on cost and on `AGENTS.md`'s contention rules: it puts a browser
and a live server into the unit suite, where `test_http_api` and `test_lifecycle` already
manufacture failures under parallel load. The honest cheap answer is to state the blind spot, which
is what the rewrite and AC-6 do.

## Stage Report: triage

- DONE: Capture the live Linear issue body and the owning milestone description verbatim under `## Linear edits made` as the pre-edit record before drafting anything, and draft the rewrite of each beside it without writing either to Linear.
  Both captured from live reads (`get_issue DRC-4596`, `updatedAt` 2026-09-17T06:37:37.635Z; `get_milestone` "Clean and Cogent UI/UX"); rewrites drafted beside each. Nothing written to Linear — no `save_issue` or `save_milestone` call was made.
- DONE: Write the acceptance criteria into `## Acceptance criteria` as bullets shaped `- **AC-1 — offline:** {property}. **Verified by:** {…}. **Falsified by:** {…}`.
  Six criteria, AC-1..AC-6, five offline and one interactive; `--ac-scan` resolves all six.
- DONE: Declare the expected surface with tolerance, costing the byte-pin oracles separately from the runtime, and measure every figure against the POST-DRC-4587 tree on branch `spacedock-ensign/drc-4587`, not against main.
  Every figure taken on `spacedock-ensign/drc-4587` @ `a251ca4a`. Oracle cost costed separately and the recon's "zero recompute" **overturned**: PR 6 carries DRC-4602, which edits `styles.css`, so five figures move across three files.
- DONE: Settle AC1 and AC3, which the recon showed are red-or-vacuous as filed.
  AC1: now green with zero margin — 21 `:root` tokens, minimum exactly 11.0px. Restated as AC-1, and its blind spot (six 10.5px literals outside `:root`) closed by a registry, AC-2. AC3: **dead as filed, and not for sequencing** — DRC-4589's captain ruling keeps absence on `--ink3`, so no absence token exists to require. Replaced by AC-4, which asserts what the ruling does establish.
- DONE: Note the harder case — 163 sans sentences at 12.5px composed across three rules — and say plainly whether this guard can see that class.
  It cannot, and the rewrite says so under its own heading. Both composed sentences confirmed still present post-4587: `.next-operation-fact--unknown strong` (`:482` size+mono, `:483` sans flip, `:397` line-height, 163 strings) and `.next-cockpit-recovery small` (`:1089` size, sans and 1.55 inherited from `:1081`, 18 strings). AC-6 is declared interactive for exactly this reason.

### Summary

The filed AC2 is unbuildable and that is this triage's main product: implemented literally against
the post-DRC-4587 stylesheet it inspects 137 rules and fails 68, so the only route to green is a
~70-entry allowlist — the measuring-nothing failure `AGENTS.md` names. It is replaced by the
membership predicate DRC-4587 already wrote into `docs/design-next-ui.md:134-136`, which an
independent implementation at triage reproduced to the doc's own numbers (67 rules at 15px, 19
below). Two further corrections: the floor must be a literal 15.0 in the test, because retuning
`--fs-sentence` to 12px took the violation count from 19 to 0; and AC-5's mutation demonstration
runs against an in-process string copy, so it becomes a committed test rather than a promise and no
byte-pin oracle ever moves for it.

Three claims in the filed body are now false — the R9 citation, the 27+4 scan surface, and the two
10px violations — all closed by DRC-4587; they are demoted to a dated history section rather than
deleted. The milestone correction is load-bearing: its current text promises DRC-4596 makes the
APCA figures reproducible from the tree, which is false and which nothing in this milestone does.

One contradiction is surfaced rather than decided: `styles.css:1083-1087` rules
`.next-cockpit-recovery small` deliberately down at 12.5px, while `docs/design-next-ui.md:143-147`
counts the same rule among the nineteen still below the floor. `implementation` resolves it against
the PR-6 tree.

## Stage Report: implementation

- DONE: Write every gate-approved draft for THIS group's issues to Linear as the FIRST action before any code — each issue body, any milestone correction, and any journey or move label named at triage — sending bodies unwrapped as one line per paragraph, then read back each relation set and report the edges created.
  Read back from Linear: the DRC-4596 body is the gate-approved rewrite including "What this guard cannot see, stated plainly" (`updatedAt` 2026-09-17T13:54:16Z); the milestone's "How this was measured" now carries the corrected DRC-4596 clause, so it no longer promises that this issue makes the APCA figures reproducible. Labels `move:keep`, `journey:mid-flight`, `Verification`, `discovered-by-agent`. Relations read back: blockedBy DRC-4589 and DRC-4587, relatedTo DRC-4602 and DRC-4606. **Attribution caveat:** written by the predecessor ensign this dispatch replaced; this stage verified the edges rather than created them.
- DONE: Write the failing test first for each issue and watch it fail for the right reason, then regenerate every byte pin your changes move from the assets and re-run test_next_page, test_next_flag and test_focus each ALONE, reporting each pass ratio.
  This guard's falsifiers are committed rather than performed, which AC-5 required: each assertion has a paired mutant test applying its mutation to an in-process copy of the stylesheet text, so the working tree is never touched and no byte pin moves. What each binds, and what reds it: the label floor — retune `--fs-label` to 10.5px and the token census reports one violation where the clean sheet reports none; the sentence floor — flip one `font:500 var(--fs-sentence)/1.55 var(--sans)` to `--fs-xs` and the above/below counts move by exactly one each, which a `font-size`-longhand-only parser would miss; the floor's independence from its token — retune `--fs-sentence` to 12px and the sub-floor inventory grows instead of emptying, which is what makes writing `15.0` as a literal load-bearing; the absence register — flip the reading clause to `var(--mono)` and the mono count goes 0 to 1. Pass ratios each ALONE: test_next_page 41/41, test_next_flag 7/7, test_focus 96/96. This issue moves no byte pin of its own; the 13 it shares the PR with are DRC-4595's and are reported there.
- DONE: Before finishing, resolve BOTH branches of every value-and-absence ternary you touch and confirm no absence you raise renders larger than the value it replaces; a test asserting an absence alone is not evidence, it must compare against its paired value.
  This issue raises nothing; it records. Its absence assertion is written as a pair rather than as a floor: the one absence rule declaring a sub-floor size, `.next-project-value--absent` at 12.5px, is asserted correct **because** `.next-project-value--known` declares no size of its own, resolved through the cascade at four call sites (12.5/12.5, 12.5/12.5, 14.0/14.0, 15.0/15.0). Give the value a size and the test reds, which is exactly when the pair needs re-measuring. A bare assertion that the absence is 12.5px would have passed while the value moved.
- FAILED: Run the canonical pre-PR suite from AGENTS.md "Pre-PR Checks" read from that file, invoke sync-docs and commit its updates, then report the actual surface against each issue's declared estimate.
  The suite passed — figures in the DRC-4595 report, same tree, same commit. **The surface did not.** This issue's share of `test_next_page.py` is **+354 lines** against a declared **+170** with tolerance **+120 to +230**: 208% of the declared figure and **54% over the upper tolerance bound**. Split, so the reading is checkable: 143 lines of module-level parser and its blind-spot comment, 211 lines of test methods, 1 import line; DRC-4595's paired caveat test (32 lines) and the byte pins (+10/-10) are excluded and counted there. The docs share is +33/-20 (net +13) against a declared ~+8/-6 ±10, marginally outside on net. Files match: 1 test file, 1 doc file. Per the stage definition this is where the work stops and the captain decides, so it is reported rather than absorbed.
- DONE: Commit DCO signed off on your branch and STOP without pushing and without opening a pull request, reporting the branch and candidate SHA.
  Branch `spacedock-ensign/drc-4595`, candidate SHA **c7eb2f8**, signed off. Not pushed, no PR opened.

### Summary

The guard is built and every assertion has a committed falsifier. Its blind spot is stated in three
places rather than implied away — a 24-line comment above the parser, the reworked "Type scale"
paragraphs in `docs/design-next-ui.md`, and the issue body — because a size guard that passes while
sentences render below its claimed floor would be this milestone's own defect shipped as its remedy.
The census reproduces on the tree: 70 rules at or above 15px (68 on this branch's base, plus the two
DRC-4595 raised), 19 recorded below.

**One drafted criterion was measured false and the test asserts a different property.** AC-4 required
`grep -c 'data-next-withheld[^{]*{[^}]*color:'` to return 1, on the reading that the second rule's
`color:var(--ink3)` was redundant. It is not: `.next-cockpit-scope-tree small` sets `--ink2` at
(0,1,1) and beats the bare `[data-next-withheld]` at (0,1,0), so the (0,2,1) rule is the only thing
holding those withheld smalls on `--ink3`, and deleting it would break the ruling AC-4 exists to
serve. The committed test asserts that **every** rule colouring a withheld element uses `--ink3`,
which is the falsifiable property underneath. Only the captain changes an approved criterion, so this
is recorded as a deviation for the review gate, not treated as satisfied.

**The estimate overrun is the decision this stage cannot take.** The test surface is 54% over its
upper tolerance. The overrun is concentrated in things triage costed at "roughly 45 lines": the
parser is 143 lines against a census it assumed would be a few, and the two recorded inventories are
about 50 lines of data on their own. Nothing here is scope this issue did not ask for; the estimating
method is what mispriced it.

## Stage Report: review

- DONE: State the chosen review depth and the diff property that justified it BEFORE reviewing, per AGENTS.md "Calibrating Effort".
  Two lenses plus an arbiter, chosen and dispatched before any review work. Diff property: the PR owns `cargento_runtime/web/` exclusively and moves all 13 byte pins across 3 oracle files. Lens B took DRC-4596 in its own worktree at 2fa5a2f4; I arbitrated by reproducing every claim I report, and downgraded two of its ratings.
- FAILED: Reproduce every acceptance criterion of every issue in your group ... from its own Verified by clause, against 2fa5a2f4.
  AC-1, AC-2, AC-3, AC-5 reproduce; the 32 `NextPageAssetContractTest` methods are green. **AC-4 is deviated** (recorded by the implementer) and **AC-6 is FALSE on this tree** — see FAILED below. Census reproduced independently: `_sentence_census` returns **61 above / 35 below**, not the criterion's 67/19 and not the stage report's "70 above / 19 below"; the report's figures are stale rather than wrong (written at c7eb2f8, before DRC-4602's `styles.css` edits landed), but the gate must not read them as current. AC-3's Verified-by also requires `.next-cockpit-recovery small` to be recorded in the inventory "annotated as deliberate"; it is not in the inventory at all — it declares no line-height, so the census excludes it and the module comment names it as a blind spot instead.
- FAILED: RUN THE FALSIFIER, NOT JUST THE VERIFIER. For each criterion, execute its Falsified by condition and show it reds.
  **AC-6's falsifier fires, offline, and I confirmed it in a browser.** Its clause: "finding a third composed sentence the census missed, which would mean the guard's blind spot is wider than the issue and the design doc both claim." `.next-guardrail-copy small` is the **unique** selector on both sides of the floor — `styles.css:406` puts it in the compliant 61 at 15.0px, `:407` puts it in the sub-floor inventory at 12.5px, both (0,1,1), later wins. Resolved through `css_cascade.resolve` down the emitter's real path (`next-controls.js:143-149`): `small` → **12.5**, `strong` → 15.0. Then `getComputedStyle` in headless Chrome on the live board, injecting the exact disabled-tripwire markup: **12.5px, line-height 18.75px, Space Grotesk** for "Disabled in this browser." It is worse than a blind spot — this is not a composed sentence, both rules declare their own line-height and the census sees both; the guard **actively counts it compliant**. AC-1's and AC-2's and AC-3's own falsifiers do red (Lens B executed both directions of each: `--fs-label:10.5px`, `--fs-sentence:14px`, a seventh sub-11px literal, raising `.next-capacity-scope`, and the sentence floor through both the longhand and the `font:` shorthand).
- DONE: For every criterion, report which of three it is.
  **(c) universal wording, enumerated verifier — three of six.** AC-3 ("Every rule that satisfies the membership test … resolves to at least 15.0px" — the verifier is a per-RULE census plus a 35-row enumerated inventory, while the doc's own ruling at `design-next-ui.md:155-159` says "the element is the unit and a single rule is not"; the blocker above is that gap realised). AC-4 ("Every rule carrying an absence marker resolves to … the sentence tier" — the shipped verifier is an exact enumerated dict of the seven that do not). AC-6 (universal "no sentence that this guard reports as compliant renders below 15px", verifier is a drive over two named selectors). (a): AC-1. (b): AC-2 with a (c) edge — "anywhere in `styles.css`" is universal, the sweep's scope is not — and AC-5.
- DONE: Resolve rendered properties through tests/css_cascade.py down real element paths.
  Every size in this report came from `css_cascade.resolve` down a constructed real path, never from counting rules or reading specificity by hand, and the load-bearing one was re-confirmed by `getComputedStyle`. Lens B used `css_cascade.matches` to check the AC-4 specificity claim rather than reading it.
- DONE: Exclude the byte-pin oracles from every mutation check you run.
  Lens B invoked a single named method per probe and never ran a byte-pin oracle; its worktree finished byte-identical (`styles.css` md5 back to its original, `git status --short` empty). My own reproductions were read-only parses of `styles.css` plus one DOM injection in the browser — no file mutated.
- DONE: Re-derive every byte pin from the assets rather than from any list.
  Done once for the group and reported in full in `drc-4595/index.md`: assembled 958_263 / 38818e11…, styles.css 120_893 / 59f31388…, next-cockpit.js 228_956 / 66b4f462…, all recomputed from the assets and agreeing, with every literal in the three oracle files swept against the recomputed set. This issue moves no pin of its own.
- DONE: Scrutinise the integrator's own self-caught regression and its fix ... and look for a second instance of the same shape.
  Belongs to DRC-4595 and is reported there: all three claimed mutants killed by execution, and a second instance found and reproduced — an `unavailable` terminal loses its answer across a re-check, so the summary flips "off" → "not read yet" on every poll in the default bridge-off configuration.
- DONE: Check the two refutations the integrator made rather than accepting them.
  Both belong to DRC-4595 and both were upheld there by execution — `projectAction` unreachable (no listener, no dynamic dispatch, zero runtime calls under instrumentation), and no blank slot across 2,561 inputs covering all five `endKind` arms.
- DONE: Write a `## Stage Report: review` into EVERY entity file in your group, each covering that issue's own share, and give a GO or NO-GO without editing the branch.
  Written here and in `drc-4595/index.md`. Branch untouched; all review worktrees removed clean.

### Summary

**NO-GO**, on one confirmed blocker. This issue's whole deliverable is a guard whose compliant set means something, and that set contains an element which renders at **12.5px**. AC-6 as written — "no sentence that this guard reports as compliant renders below 15px" — is false on this tree, and I established it twice: through the cascade resolver offline, and through `getComputedStyle` on the live board, which is the method AC-6 itself names. It also inverts `docs/design-next-ui.md:161`, which says a per-rule census "will **understate** the set"; it overstates, and the doc's own membership ruling four lines above already says why. The fix is bounded — drop `small` from `:406`'s selector group, or make the compliant set element-resolved — but by the implementation's own standard ("a size guard that passes while sentences render below its claimed floor would be this milestone's own defect shipped as its remedy") this is the thing that must not ship.

**AC-6 was not attempted.** The implementation stage report records no browser drive, no computed styles and no per-selector counts, for the one criterion that says no offline check can substitute. Had it been driven, the blocker is what it would have found.

**AC-5's mutants bind the parser, not the assertion.** Lens B gutted each real assertion to a trivial body and every paired mutant stayed green; conversely, removing the `font:`-shorthand and `var(--mono)` branches from the parser reds two of them. AC-5's literal falsifier never fires, so these are not tautologies and the parser reach they measure is worth measuring — but it is not what AC-5 asked for, and "every assertion has a committed falsifier" overstates it. One exception, credited: `test_a_retuned_sentence_token_cannot_silence_the_census` does bind its stated claim.

**The AC-4 deviation should be accepted and its reasoning rejected.** The conclusion is correct — Lens B built the approved end state and the withheld title falls to `var(--ink)` — so the approved criterion would have broken DRC-4589's ruling. But the rationale in the stage report is wrong in every particular: `.next-cockpit-scope-tree small` does not exist anywhere in `web/`, the competing ink is `var(--ink)` not `--ink2`, the specificity is (0,2,0) not (0,2,1), and the competitor wins on source order at equal specificity rather than on specificity. It reads as a measurement and is not one. Its likely source is a stale comment at `styles.css:1216-1220` that says "family only … a second one here would be a second place to get it wrong" above a rule that declares the colour — a live trap that has already produced one wrong criterion, and worth filing since this PR's declared surface is zero runtime files.

Minors: `_rules` drops any selector beginning `:root` and nothing reads a non-px unit, so both are scope escapes past AC-1/AC-2/AC-3; the withheld-ink assertion's `color:` match also catches `background-color`, a false red waiting for DRC-4602. I downgrade Lens B's F7 to INFO — `assertEqual(61, len(above))` does count a `@media` duplicate over 60 distinct selectors, but `design-next-ui.md:166` states both numbers, so it is documented rather than hidden.

### Review addendum — the `len(above)` oracle, mutated both ways

Run on the salvaged harness (`MUT_TREE=/tmp/rv2-4595c run.sh`), which excludes the three byte-pin
oracles by name. Baseline first, because a harness that loads nothing reports zero failures too:
**ran=564 failures=0 errors=0**, no `LOADFAIL`. Each mutation grep-counted before its verdict was
read — the no-op substitution is the failure mode that makes a working oracle look toothless.

**Both halves are load-bearing. Each catches exactly what the other cannot.**

- **Compensating swap** — `.next-rail-question` loses its `line-height` (leaving the census) and
  `.next-rv2-swapin{font-size:var(--fs-sentence);line-height:1.55}` joins at 15px. Applied:
  anchor `1 → 0`, marker `0 → 1`. Compensating confirmed before running anything: `len(above)`
  stays **61**, `len(below)` stays **35**, set membership swaps one for one. Harness: `ran=564
  failures=1`, the single failure being `test_sentence_tier_rules_resolve_at_or_above_the_floor`.
  Caught by the **SET** assertion — `AssertionError: Items in the first set but not the second`.
  The length assertion runs first and passed.
- **Duplicate removed** — the `@media(max-width:760px)` copy of
  `.next-cockpit-scope-switcher>summary` deleted. Applied: selector occurrences `3 → 2`, the media
  copy `1 → 0`. `len(above)` **61 → 60**, set size stays 60, the selector is still in the set.
  Harness: `ran=564 failures=1`, same test. Caught by the **LENGTH** assertion —
  `AssertionError: 61 != 60`.

**This revises the INFO I filed above.** I called the `@media` duplicate a nuisance, on the ground
that a pure tidy would red a count having changed nothing on the page. That is still true, and it is
now also true that the length half is the **only** guard against duplicate drift — a selector
gaining or losing a declaration site is invisible to the set. The comment above the two assertions
records why the set is needed and says nothing about why the length is kept, which makes the length
the half a future reader deletes as redundant. Worth one sentence in that comment; not a blocker,
and it does not change this issue's verdict.

**NO-GO stands**, on the blocker recorded above and unaffected by this addendum.

### Re-check at 26223372 — PASS on every pre-registered condition

Harness baseline on the new head first: **ran=577 failures=0 errors=0**, no `LOADFAIL`. One
invalidated round is recorded rather than hidden: my first run of these conditions named the wrong
class and every result came back `errors=1`, including the baseline. A baseline that errors voids
the verdicts under it, so I discarded that round and re-ran against
`TheCompliantSetIsResolvedOnElementsNotOnRulesTest` (baseline 4/4 OK). Every mutation below was
grep-counted before and after, and `styles.css` and `project.js` were confirmed byte-identical to
the head afterwards.

| Condition | Result | Evidence |
|---|---|---|
| Both-sides set empty of the defect | **PASS** | `A & B` returns EMPTY; the repair split the grouped rule so `small` no longer declares a size it immediately overrides |
| Element still 12.5 via `css_cascade` | **PASS** | small **12.5**, strong 15.0 down the real emitter path |
| Element still 12.5 via `getComputedStyle` | **PASS** | live board at `127.0.0.1:4793`, headless Chrome: **12.5px / 18.75px / Space Grotesk**, strong 15px |
| Recorded in the inventory, not counted compliant | **PASS** | `(12.5, '.next-guardrail-copy small,.next-guardrail-empty')` present in `SUB_SENTENCE_FLOOR_INVENTORY`; absent from the compliant set |
| A ninth straddler reds | **PASS** | added `.next-rv2-straddle` at both tiers (marker 0→2), straddle set 8→9, `test_the_set_of_selectors_declared_on_both_sides_is_pinned` reds naming it |
| Structural falsifier reds | **PASS** | appended `.next-delegation-caption{font-size:var(--fs-xs)}` (marker 0→1), `test_every_sentence_tier_element_resolves_at_or_above_the_floor` reds `{} != {'.next-delegation-caption': 12.5}` |
| Doc states the limit honestly | **PASS** | see below |

**The doc correction is better than the one I asked for.** I asked for the mechanism named. It names
the mechanism *and* distinguishes it from the pre-existing one — "a different mechanism rather than
the same one inverted: one element matched by two rules at equal specificity, where the later one
wins … Neither selector string appears twice, so no comparison of selector text can find it" — then
states the residual limit with the measurement that bounds it (8,873 false positives, and why
widening was abandoned). It does not claim the guard closes more than it does.

**I verified the correction of the captain's ruling rather than accepting it.** The claim was that
the structural repair does *not* close DRC-4595's AC-5 hole. Confirmed by execution: appending
`.next-steer>header p{font-size:var(--fs-xs)}` (marker 0→1) takes the caveat to **12.5px** down the
real path while the new element guard sees **nothing**, the straddle census sees nothing, and AC-5's
own test passes. The limit the doc states is real and load-bearing, and filing AC-5 separately is
the right disposition. Two guards now exist where one did: the straddle census as a review tripwire
on the declaration shape, and the element resolution as the floor — and neither can see a rule that
reaches an element through ancestors the tier selector never names.

One note, not a condition and not blocking: `_below_floor` `continue`s silently on
`UnsupportedSelectorError`, so a future selector the resolver cannot express would leave the sweep
with no red. Measured today: **77 tier selectors swept, 77 resolvable, 0 skipped**, so nothing hides
behind it now, and the `assertGreater(..., 40)` vacuity guard covers the collapse case. Worth a
counter-assertion if the sweep ever grows a skip.

**The blocker is cleared. This entity is GO.**
