---
id:
title: "Split the three inks onto label, value and absence roles so a label stops sharing its ink with its own answer"
status: review
source: "https://linear.app/recce/issue/DRC-4589/split-the-three-inks-onto-label-value-and-absence-roles-so-a-label"
started: 2026-09-17T10:42:56Z
completed: ""
verdict: ""
score: 0.6
worktree: .worktrees/spacedock-ensign-drc-4589
issue: ""
pr: ""
mod-block: ""
linear-status: "Backlog"
milestone: Clean and Cogent UI/UX
release: ""
promise: "P2"
move: "sharpen"
estimate: ""
reconciled: ""
gates:
    version: 1
    records:
        - id: gate:drc-4589:triage
          stage: triage
          attempts:
            - id: gate-attempt:drc-4589-triage-1
              briefing:
                id: briefing:drc-4589:triage:attempt-1:revision-1
                digest: sha256:18eef156a11c3741c78044c1444200f5f04a40dba4c36064f428c95e11e2eae6
                room-ref: ./review/triage/briefing-1
              resolution:
                type: Resolution
                id: resolution:spacedock:drc-4589:triage:1
                briefing: briefing:drc-4589:triage:attempt-1:revision-1
                by: agent:first-officer
                at: "2026-09-17T10:52:14.735098Z"
                decision: approve
                reason: 'Checklist 4 done / 0 skipped / 0 failed; AC-1..AC-7 resolve with AC-7 the user-visible interactive criterion. Every figure was rebuilt against the post-DRC-4587 worktree rather than main, which is what the dispatch asked and what made the LABEL register reachable at the new 11px --fs-label. Three issue claims were refuted against the tree and demoted to dated history rather than deleted, the largest being AC2''s DELEGATION claim whose literal implementation would have brightened an absence. The captain''s absence-ink ruling was applied and followed into the two consequences it creates rather than re-decided: AC-1 scoped to present values with absence and caption exempt, and AC-4''s three data-absence renderings required to differ without colour since the ruling removes the waiting-on-you ink lift.'
                conn:
                    quote: I pre-approve all the triage and merge gates, just automate this entire process and do it
                    source: Captain, this session, 2026-09-17, answering the gate-authority question
              application:
                target-stage: implementation
                state: consumed
---

[DRC-4589](https://linear.app/recce/issue/DRC-4589/split-the-three-inks-onto-label-value-and-absence-roles-so-a-label) — Split the three inks onto label, value and absence roles so a label stops sharing its ink with its own answer

Seeded 2026-09-17 from the live Linear read of the Clean and Cogent UI/UX milestone.
Linear owns the current issue body, its relations and its resources; triage fetches them
live and validates them against the tree before anything is built. No triage, approval,
implementation or delivery is claimed here.

---

# Triage — DRC-4589, 2026-09-17

Every figure below was measured on the **post-DRC-4587 tree**, branch `spacedock-ensign/drc-4587`
at `3cc7ef49` (worktree `.worktrees/spacedock-ensign-drc-4587`), not on `main`. DRC-4587 moves the
type scale underneath this issue, so any figure taken on `main` is already stale — the line numbers
in the recon above are pre-4587 and have shifted by roughly +8.

## User value (drafted — first section of the rewrite)

Anyone reading a panel to find one fact meets this the moment they look: the label asking the
question and the value answering it are drawn in the same ink, so the fastest pre-attentive channel
carries nothing and the eye has to fall back on family, size and weight. Absence is worse than
neutral — in COUNTS the words "not published" are byte-identical in treatment to a real figure.

Promise **P2** (*What is it doing, and when should I come back?*), move **`sharpen`**. The promise
is already kept; this makes reading it cheaper. Nothing this issue does changes what the board
claims, only how fast a reader can separate a question from its answer and an answer from a gap.

## Labels

`journey:mid-flight` and `move:sharpen` are **already set on the live issue** — verified in the
`get_issue` read of 2026-09-17. No label write is needed at `implementation`.

## Linear edits made

Nothing has been written to Linear. The captures below are the pre-edit record; the drafts below
them are what `implementation` writes once this gate approves.

### Pre-edit record — DRC-4589 issue body, verbatim (captured 2026-09-17, `updatedAt` 2026-09-17T06:37:37.224Z)

```markdown
## User value

Anyone scanning a panel for one fact notices this the moment they try to find it. Today a label and its own answer are the same colour, so the eye has no tonal cue to separate the question from the value.

## The Problem

On Held to, 1506 of 2068 visible characters (73%) are drawn in ink3 `#9b9484` at 12.5px/400, and 89% of all characters on the tab are ink3 in some role; only 31 characters are in full ink. The section labels are the same ink: the five panel h2s are 10px/700 mono ink3, `.next-cockpit-departure-label` is 9.5px ink3, and the sentences beneath them are ink3 too.

Label and value are therefore separated by family, size, tracking and weight — four channels — with zero tonal separation, the fastest pre-attentive cue carrying nothing. Of the pairings in the captures, exactly one separates on tone: COUNTS, where the label is ink2 and the value ink.

Two blocks break the convention the other way: COUNTS writes "not published" into `.next-cockpit-count-value` at full ink, byte-identical to the real figure 9 three rows below, and Console's DELEGATION renders "no figure yet" in the large bright figure type. The hierarchy is inverted — the dimmest ink carries the most reading, and absence wears the clothes of data.

**Measured**

* Live DOM, Held to: 1506 of 2068 chars (73%) at 12.5px/400 in ink3; 200 chars ink2; 31 chars full ink; 89% of all characters ink3
* Across the stylesheet the dimmest ink is over half of all ink references: 195 `var(--ink3)` against 97 `var(--ink2)` and 77 `var(--ink)`
* Labels render 9.5px/400 (0.76px tracking) and 10px/700 (1.3-1.4px tracking) in Space Mono, all in ink3 — the same colour as the body
* styles.css:915 `.next-cockpit-count-value{color:var(--ink);font:var(--fs-xs)/1.5 var(--mono)}` has no absent variant; next-cockpit.js:1895-1896 writes "not published" into it
* A convention does exist elsewhere: landed cards (styles.css:1058 ink vs 1059 ink3), the briefing (1071/1072, gated by `data-next-cockpit-task-known` at next-cockpit.js:2751) and the scope title (1081) all step absence down
* Seven `--absent` rules plus `[data-next-withheld]` (styles.css:44) all resolve to ink3, the same token as the labels
* One paragraph class carries three different kinds of statement: `.next-cockpit-reading-why` (styles.css:944) holds "Nothing has been typed for this session" (waiting on you), "Start with --unasked-readings" (run config) and "No reading has been made at your request" (not observed), identically
* Only 8 distinct text styles across 46 text nodes on Held to

**In the attached screenshot**

1. Section labels ink3, body ink3: zero tonal step
2. 89% of characters on this tab are ink3 #9b9484
3. COUNTS: "not published" drawn exactly like the 9s
4. TYPED GOAL, your words, 0/240, absence: all ink3

## The Solution

Declare four registers once in the FOUNDATION region and repoint the cockpit rules to them.

* **LABEL** — ink3, mono, 11px/700, uppercase, .09em.
* **VALUE** — ink, weight 500; mono when a source published the string and sans when the board derived it (the sheet's existing convention at styles.css:887-889 and 949-951).
* **ABSENCE** — ink2 in a prose slot, and *critically* keep `color:var(--ink)` where the string sits in a figure slot (COUNTS, DELEGATION), because demoting "not published" to ink2 would make C1 worse on the exact string it is meant to clarify. Differentiate by family and shape instead: add `.next-cockpit-count-value--absent{font-family:var(--sans);font-weight:400}`, stamp `data-next-absent` at emission, and add `[data-next-absent]::before{content:"\2014";margin-right:6px;color:var(--ink3)}` so the status survives greyscale. A zero still renders `0` in ink mono with no dash.
* **CAPTION / PROVENANCE** — ink3, mono, weight 400, no tracking.

Sub-tag the absence paragraphs at emission with `data-absence="not-observed|waiting-on-you|run-config"` and give waiting-on-you ink2 at weight 500 with a 2px inset accent-dim rule, so a reader can scan for what is theirs to act on. No wording changes.

Do not collapse the run-config paragraphs into a disclosure — the `--unasked-readings` sentence is the only content of FROM THE CHECKS RUN WHILE YOU WERE AWAY, and hiding it empties a named collection.

Reviewable rule: **a label and the value answering it must differ by two tone steps and two role cues.**

## Acceptance

- [ ] No `.next-cockpit-*` or `.next-session-*` label rule shares an ink token with the value rule it labels
- [ ] "not published" in COUNTS and "no figure yet" in DELEGATION keep full ink and gain a family change plus a leading em dash; a real 0 renders with neither
- [ ] Every `--absent` rule and `[data-next-withheld]` resolves to one declared absence register rather than to the label ink
- [ ] Absence paragraphs carry `data-absence` with one of three values and render in three visibly distinct ways, with no sentence reworded
- [ ] The `--unasked-readings` sentence still renders in place under FROM THE CHECKS RUN WHILE YOU WERE AWAY
- [ ] The asset test's existing 4.5:1 palette assertion still passes unchanged

---

Complaint **C2** · tabs: all · severity **blocker** · effort **M** · blocked by DRC-4587

Raised from user feedback; mechanism and figures established by a measured audit of the live board and the shipped stylesheet.
```

### Pre-edit record — "Clean and Cogent UI/UX" milestone description, verbatim (captured 2026-09-17)

```markdown
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
```

### Drafted rewrite — DRC-4589 issue body

```markdown
## User value

Anyone reading a panel to find one fact meets this the moment they look: the label asking the question and the value answering it are drawn in the same ink, so the fastest pre-attentive channel carries nothing. Absence is worse than neutral — COUNTS renders "not published" in exactly the treatment a real figure gets.

Promise P2, move `sharpen`. The promise is already kept; this makes reading it cheaper.

## The problem

One ink carries three jobs. Measured on the post-DRC-4587 tree: **21** `.next-cockpit-*` / `.next-session-*` label rules and **35** prose rules independently spell `var(--ink3)` in their own declaration block. There is no register between them, so a change to one cannot move without hand-editing the other, and today they are the same colour on screen.

Two value slots invert the hierarchy in opposite directions:

* **COUNTS** writes the words "not published" into `.next-cockpit-count-value` (styles.css:923, `color:var(--ink)`), which has no absent variant — so an absence renders byte-identical to a real figure. next-cockpit.js:1896.
* **DELEGATION** does *not* do what this issue previously claimed. Both "no figure yet" paths — next-delegation.js:182 (Console tab) and next-delegation.js:209 via `next-observed.js:221`'s `pctText` (project rail) — render inside `.next-delegation-withheld`, which is `color:var(--ink2)` with `strong` at `font:700 16px var(--mono)` (styles.css:310-311). The accent 32px rule `.next-delegation-figure>strong` (styles.css:303) reaches neither.

One paragraph class carries three different kinds of statement identically: `.next-cockpit-reading-why` (styles.css:952) is emitted from **22** sites in next-cockpit.js and holds *waiting on you* ("Nothing has been typed for this session"), *run config* ("Start with `--unasked-readings`") and *not observed* ("No reading has been made at your request") in one treatment. Several of those 22 are neither — 2091 "A reading is stored for this session", 2159 "Neither card implies the other" — so classification is per-site judgement, not a mechanical pass.

## The solution

Declare four registers once inside the single existing `:root` block in the FOUNDATION region and repoint the label, value, absence and caption rules to them.

* **LABEL** — `--ink3`, mono, `--fs-label` (11px post-DRC-4587), 700, uppercase, `.09em`.
* **VALUE** — `--ink`, weight 500; mono when a source published the string, sans when the board derived it.
* **ABSENCE** — **keeps `--ink3`** and differentiates on family and shape, never on brightness. In a figure slot the ink stays exactly where it is today (COUNTS `--ink`, DELEGATION `--ink2`); the cue added is a family swap plus a leading em dash stamped at emission via `data-next-absent`, so the status survives greyscale. A real `0` gets neither.
* **CAPTION / PROVENANCE** — `--ink3`, mono, 400, no tracking.

Sub-tag absence paragraphs at emission with `data-absence="not-observed|waiting-on-you|run-config"`, and distinguish the three **without colour** — the `waiting-on-you` cue is a 2px inset `--accent-dim` rule, so a reader can scan for what is theirs to act on. No sentence is reworded, and the `--unasked-readings` sentence stays rendered in place: it is the only content of FROM THE CHECKS RUN WHILE YOU WERE AWAY, and a disclosure would empty a named collection.

Reviewable rule: **a label and the present value answering it must differ by two tone steps and two role cues.** Absent values are exempt and are governed by the absence register.

## Acceptance

See the triage entity for the criteria with their offline/interactive split and `Verified by:` clauses.

---

Complaint **C2** · tabs: all · severity **blocker** · effort **M** · blocked by DRC-4587

## History — superseded 2026-09-17 at triage

Three claims in the body filed on 2026-09-17 were checked against the tree and do not hold. They
are kept here because the rest of the audit they came from is sound and a later reader needs to
know which parts were retired and why.

1. **"Console's DELEGATION renders 'no figure yet' in the large bright figure type"** — false at
   both emission sites. It is `--ink2` at `700 16px var(--mono)` inside `.next-delegation-withheld`
   (styles.css:310-311). The original AC2, "keep full ink", would therefore have *brightened* an
   absence from `--ink2` to `--ink`, the opposite of this issue's own hierarchy argument.
2. **"Seven `--absent` rules"** — the sheet carries four occurrences over three distinct class
   names (styles.css:159, 735, 1067, 1101). Only 159 and 1067 set a colour; 735 and 1101 set type
   only.
3. **"ABSENCE — ink2 in a prose slot"** — overturned by the captain's ruling of 2026-09-17 (below).

The DOM census — 1506 of 2068 characters, 73%, 89%, 200 / 31 characters, 8 text styles across 46
text nodes — was taken on a live quiet session and was **not** reproduced at triage, which was a
read-only pass against the tree. The mechanism is confirmed from the stylesheet; the magnitudes are
the author's single measurement and must not be quoted in a PR body as though reproduced.

Line numbers in the original body are pre-DRC-4587 and have shifted by roughly +8.

## Ruling — absence ink, 2026-09-17

The captain ruled directly, against a contradiction between this issue and DRC-4597, both governing
the same `[data-next-withheld]` override. **Absence keeps `--ink3`. DRC-4597's AC4 stands verbatim.**

The palette has three inks and this issue needs four roles, so one pair must double up. `--ink3` on
panel is 5.67:1, the floor the asset test's 4.5:1 assertion sits just above, so labels cannot go
dimmer; brightening them makes them compete with values. Labels can afford to keep `--ink3` because
they carry uppercase, tracking and mono as well. An absence is a sans sentence, so family and case
already separate it from a label. And brightening an absence runs against this project's named
defect class — the failure mode here is the confident wrong answer in an absence, so a card whose
title is missing must not read as loudly as one that has it.

The falsifiable end state: after this change **exactly one rule in the sheet assigns a colour to
`[data-next-withheld]`**. styles.css:52 keeps it; styles.css:1089 keeps `font-family:var(--sans)`
and drops its redundant `color:var(--ink3)`.
```

### Drafted rewrite — milestone description correction

Only the "Waits on" and a new "Read before building" section change. Everything else in the
milestone description is still true against the tree and is left alone — the contrast figure 5.67:1
was independently recomputed at this triage from the shipped tokens and matches to the decimal.

Replace the **Waits on** section with:

```markdown
## Waits on

Nothing outside this milestone. `type-scale` and `ink-roles` gate most of the rest; `ink-roles`
itself waits on `type-scale`, which landed on 2026-09-17.
```

Append, after "How this was measured":

```markdown
## Read before building

Rulings made mid-milestone that a later issue's agent will not otherwise have in context.

- DRC-4597: absence keeps ink3; styles.css:1089 keeps only the family swap. DRC-4589 amended its
  own AC3 rather than move the token, so DRC-4597's AC4 stands verbatim.
```

This section does not exist on the milestone today and must be created. `sync-project`'s milestone
template preserves it. It is `burndown` step 4.3 and belongs to this PR's post-merge reconcile,
keyed by issue id.

### Demoted to history, and why

Three factual claims and one solution clause, all listed in the `## History` section of the drafted
rewrite above with the tree evidence that retired each. Nothing was deleted: the DOM census is kept
with an explicit note that it was not reproduced, because the mechanism it supports is independently
confirmed and a later reader needs to know which half is which.

## Acceptance criteria

- **AC-1 — offline:** No `.next-cockpit-*` or `.next-session-*` label rule spells an ink token in
  its own declaration block; every one resolves its colour through the single declared LABEL
  register, and no label register shares an ink token with the register carrying the **present**
  value it labels. Absence rules (`--absent`, `[data-next-withheld]`, `-clause-absent`) and
  caption/provenance rules are explicitly exempt — the first is governed by AC-3, the second is not
  an answer to its label. **Verified by:** `grep -cE '^\.next-(cockpit|session)[^{]*\{[^}]*var\(--fs-label\)' styles.css`
  piped through `grep -c 'var(--ink3)'` returns **21** on the post-DRC-4587 tree and must return
  **0**; the same count over all selectors is **38** today. Which rule is "the value rule it
  labels" is a human pairing judgement with no derivable oracle, so that half is a named review
  obligation at the review gate, not a test. **Falsified by:** any label rule reintroducing a
  literal `color:var(--ink3)` beside `var(--fs-label)`, or a present-value rule moved onto
  `--ink3`.

- **AC-2 — offline:** The ink of each absence string stays exactly where it is today — COUNTS'
  "not published" at `--ink` (styles.css:923) and DELEGATION's "no figure yet" at `--ink2`
  (styles.css:310-311) — and each gains a family swap plus a leading em dash stamped at emission,
  while a real `0` renders with neither. **Verified by:** `tests/test_next_cockpit.py`, extending
  the nine existing `next-cockpit-count-value` assertions, asserts that a `null` count emits
  `data-next-absent` on the value span and a count of `0` emits the span without that attribute;
  `tests/test_next_delegation.py` asserts the same over both "no figure yet" paths
  (next-delegation.js:182 and :209). **Falsified by:** stamping the attribute unconditionally, so
  a real `0` carries the em dash — the failure this issue's own Measured Invariant warns of — or by
  moving either string's ink token.

- **AC-3 — offline (amended 2026-09-18):** Every `--absent` rule and every `[data-next-withheld]`
  rule resolves to one declared ABSENCE register, and **a withheld element resolves the absence ink
  on the element that renders it**. The rule count is no longer part of this criterion.
  **Verified by:** resolving the withheld and published scope titles down a real element path
  through `tests/css_cascade.py` and asserting they differ, which `WithheldTitleKeepsTheAbsenceInkTest`
  pins. **Falsified by:** a withheld element resolving the same ink as its published sibling — which
  is what stripping the rail override's colour produces.

  **Why the count was removed, recorded because it reverses a ruling.** The original wording
  required "exactly one rule in the sheet assigns a colour to `[data-next-withheld]`", and the
  captain's ruling of 2026-09-17 said the override keeps only its family swap. Both were correct on
  the tree they were written against, where the withheld element was a `<small>` with no competing
  colour rule. DRC-4597 then moved `data-next-withheld` onto `span.next-cockpit-scope-title`, which
  declares `color:var(--ink)` at the same `(0,1,0)` specificity and later in the sheet, so it wins on
  source order. Executed rather than argued, twice independently: stripping the override's colour
  returns the count to **1** *and* makes a withheld scope title resolve `var(--ink)`, byte-identical
  to a published one, reddening `WithheldTitleKeepsTheAbsenceInkTest`. **The criterion as written was
  satisfied exactly by the defect.** The count is therefore the wrong property and the rendered ink
  is the right one; the ruling's intent — one place owns the withheld colour — is unchanged, and only
  which rule that is has moved.

- **AC-4 — offline:** Every `.next-cockpit-reading-why` emission that states an absence carries
  `data-absence` with exactly one of `not-observed`, `waiting-on-you`, `run-config`; emissions that
  are not absences carry none; and no sentence is reworded. **Verified by:** a
  `tests/test_next_cockpit.py` case per value asserting the attribute on the rendered block, plus a
  case asserting that next-cockpit.js:2091 ("A reading is stored for this session") and :2159
  ("Neither card implies the other") emit the class **without** the attribute — the mislabelling a
  blanket pass would produce. Wording is held by `git diff` showing no change to any string
  literal in the 22 emission sites. **Falsified by:** tagging all 22 sites, which turns the
  attribute into a structurally-present default that measures nothing.

- **AC-5 — offline:** The `--unasked-readings` sentence still renders in place under FROM THE
  CHECKS RUN WHILE YOU WERE AWAY, not behind a disclosure. **Verified by:** the existing
  `tests/test_next_cockpit.py` coverage of next-cockpit.js:1824 asserts the sentence is in the
  section's own rendered block; it passes today and must still pass. **Falsified by:** wrapping
  that paragraph in a `<details>`, which empties the only content of a named collection.

- **AC-6 — offline:** The asset test's 4.5:1 palette assertion passes unchanged, and no palette hex
  moves. **Verified by:** `test_the_next_palette_is_dark_only` in `tests/test_next_page.py`
  (lines ~393-443) — its token map is a projection (`{name: tokens.get(name) for name in expected}`)
  so new registers inside `:root` pass, but its `re.findall(r"(?:\A|\n):root\{([^}]*)\}", ...)`
  asserts **exactly one** `:root` block, so a second one fails the suite. Independently recomputed
  at triage: `--ink3` on `--panel` is 5.67, on `--bg` 6.13, on `--sunk` 6.28. **Falsified by:**
  editing any of the twelve pinned hexes, or declaring the new registers in a second `:root`.

- **AC-7 — interactive:** On a live board a reader can tell, without reading the words, which line
  is a label, which is its answer and which is a gap — and the three `data-absence` kinds are
  visibly distinct from each other in greyscale. **Verified by:** one screenshot of Held to and one
  of Console taken against the built branch and saved under `docs/screenshots/`, reviewed at the
  review gate against the pre-change capture attached to the Linear issue. This is the one criterion
  with no offline oracle: distinctness is a perceptual claim and the repository has no APCA
  implementation to stand in for it. DRC-4596 adds the size guardrail that would cover part of this
  and lands later by design. **Falsified by:** two of the three absence kinds rendering
  indistinguishably once colour is removed.

## Expected surface

**Runtime: 95-130 net lines across 4 files**, tolerance ±25%.

| File | Net lines | What moves |
|---|---|---|
| `cargento_runtime/web/styles.css` | +45 / −35 | four register declarations inside the one existing `:root`; 21 cockpit/session label rules repointed; `[data-next-withheld]` colour removed at :1089; `--absent` rules unified; `--count-value--absent` and the `[data-next-absent]::before` dash |
| `cargento_runtime/web/next-cockpit.js` | +30 | `data-next-absent` stamped at :1896 only where `value == null`; `data-absence` classified across the absence subset of the 22 `reading-why` sites |
| `cargento_runtime/web/next-delegation.js` | +6 | `data-next-absent` on both withheld paths (:182, :209) |
| `cargento_runtime/web/next-observed.js` | +2 | carry an absence flag beside `pctText` (:221) so :209 can stamp without re-deriving |

`next-project.js` is in the recon's `filesTouched` list and is **not** expected to change: its
`.next-project-value--absent` rules are stylesheet-side only. If it does change, that is a fourth
part pin and the estimate is wrong — say so rather than absorbing it.

**Oracles, costed separately: 9 pin edits across 3 files plus roughly 60 test lines across 2 files.**
Every one of these is a figure recomputed from the built assets, never resolved textually.

| Pin | File:line | Value on the post-4587 tree |
|---|---|---|
| stylesheet size | `tests/test_next_page.py:703` | `111_050` |
| stylesheet digest | `tests/test_next_page.py:705` | `91a303b22906…` |
| assembled length | `tests/test_next_page.py:710` | `914_344` |
| assembled digest | `tests/test_next_page.py:712` | `2165bf68d82b…` |
| assembled length | `tests/test_next_flag.py:67` | `914_344` |
| assembled digest | `tests/test_next_flag.py:69` | `2165bf68d82b…` |
| assembled digest | `tests/test_focus.py:1024` | `2165bf68d82b…` |
| part size + digest | `tests/test_next_page.py:682-684` | `next-cockpit.js` `198_105` / `16f67be92f13…` |
| part size + digest | `tests/test_next_page.py:674-676` | `next-delegation.js` `14_508` / `36ecd0981479…` |

`next-observed.js` adds a tenth and eleventh (its own size and digest) if it is edited — it is in
`frontend_page.APP_PARTS`, and `self.assertEqual(tuple(expected_parts), frontend_page.APP_PARTS)`
at `tests/test_next_page.py:695` means a part cannot be silently skipped.

**Test lines:** ~35 in `tests/test_next_cockpit.py` (AC-2, AC-4), ~15 in
`tests/test_next_delegation.py` (AC-2 over both paths), ~10 in `tests/test_next_page.py` (AC-3's
one-colour-rule count). **No new test file** — every assertion extends a module that already
imports the surface, so no import-graph allowlist, protocol fake or drift-guard is compelled. That
was checked, not assumed: `tests/test_documentation.py` opens `SECURITY.md`, `README.md` and
`SKILL.md` by literal path and none of them change here.

**Semantics that may move:** none. No published field is added, no session field is declared, no
store is touched. The only new emission-time data is two presentational attributes, and AC-2 and
AC-4 each pin the negative case so neither becomes a structurally-present default.

**Merge risk:** this is the only PR that may touch `cargento_runtime/web/` while it is in flight.
It is PR 3 of the milestone's six, paired with DRC-4593, and six issues (DRC-4591 through
DRC-4597) unblock behind it, so every one of them needs `gh pr update-branch` and a full CI cycle
after it lands.

## Approach, and the simplest rejected alternative

**Chosen:** hoist four registers into the one existing `:root` and repoint, keeping every ink token
where it sits. Absence is separated on family and shape rather than brightness.

**Rejected — repoint nothing and simply move the 35 prose rules to `--ink2`.** It is one
find-and-replace and needs no register. It cannot deliver the value: it brightens absences along
with prose (35 of the 35 rules include absence sentences), which is the confident-wrong-answer
failure the captain's ruling names, and it leaves the 21 label rules still spelling their own ink,
so the next change to the label tier is another 21-site hand edit. The register is the part that
makes the *next* change cheap; the colour move is the part that makes this one wrong.

**Rejected — collapse the run-config paragraphs into a `<details>` disclosure.** Smaller diff, real
density win. It empties FROM THE CHECKS RUN WHILE YOU WERE AWAY, whose only content is the
`--unasked-readings` sentence. AC-5 exists to prevent it.

---

## Stage Report: triage

- DONE: Capture the live Linear issue body and the owning milestone description verbatim under `## Linear edits made` as the pre-edit record before drafting anything, and draft the rewrite of each beside it without writing either to Linear.
  Both captured in fenced blocks under `## Linear edits made` from `get_issue DRC-4589` (`updatedAt` 2026-09-17T06:37:37.224Z) and `get_milestone "Clean and Cogent UI/UX"`; drafts follow each. No Linear write was made — no `save_issue` or `save_project` call was issued this stage.
- DONE: Write the acceptance criteria into `## Acceptance criteria` as bullets shaped `- **AC-1 — offline:** {property}. **Verified by:** {…}. **Falsified by:** {…}`.
  Seven criteria, AC-1..AC-7, hyphenated ids, each bold label closing on the line it opens; AC-7 is the one `interactive` criterion and is the user-visible property the stage requires.
- DONE: Declare the expected surface with tolerance, costing the byte-pin oracles separately from the runtime, and measure every figure against the POST-DRC-4587 tree on branch `spacedock-ensign/drc-4587`.
  95-130 net runtime lines across 4 files ±25%, costed separately from 9 pin edits across 3 files plus ~60 test lines across 2 files. Every pin read from the worktree at `3cc7ef49`: assembled `914_344` / `2165bf68…` (not main's `911_302` / `7c0dbcb3…`), stylesheet `111_050` / `91a303b2…`. Checked that no required check compels a new test file.
- DONE: Repair AC2, correct the "seven --absent rules" count, and apply the captain's ruling on absence ink.
  AC2: both "no figure yet" paths (next-delegation.js:182 and :209 via next-observed.js:221's `pctText`) render inside `.next-delegation-withheld` at `--ink2` / `700 16px var(--mono)`; the accent 32px rule at styles.css:303 reaches neither, so AC-2 now fixes each string's ink where it already sits. `--absent` corrected to four occurrences over three class names, two setting no colour. Captain's ruling applied: AC-3 carries the unification claim alone, the "rather than to the label ink" clause is gone, absence keeps `--ink3`, and the rewrite's Solution section was corrected too — the original said absence becomes `--ink2` in prose slots, which is the clause the ruling overturns.

### Summary

Triage rebuilt every measurement against the post-DRC-4587 worktree rather than main, which mattered:
the assembled-page pins have already moved, and `--fs-label` is now 11px, so the LABEL register the
issue specifies is reachable. Three of the issue's claims were refuted against the tree and demoted
to a dated `## History` section rather than deleted, the largest being AC2's DELEGATION claim, whose
literal implementation would have brightened an absence.

Two decisions this stage owns and the gate should look at. First, AC-1 as filed collides with the
captain's ruling: an absent value in a slot whose label is `--ink3` must share `--ink3` under the
ruling, so AC-1 is scoped to *present* values with absence and caption rules explicitly exempt.
Second, the ruling's rationale also kills the issue's `waiting-on-you` lift to `--ink2`, so AC-4's
three `data-absence` renderings are now required to differ without colour — the inset accent-dim
rule carries that cue instead. Neither re-decides the ruling; both follow it into surfaces the
ruling did not name.

AC-1 and AC-3 each got a greppable oracle that returns a wrong number today and a right one after:
21 label rules spelling their own ink must become 0, and 2 colour-assigning `[data-next-withheld]`
rules must become 1. AC-7 is the only interactive criterion, because distinctness is perceptual and
the repository has no APCA implementation to stand in for it.

## Stage Report: implementation

- DONE: Write every gate-approved draft for THIS group's issues to Linear as the FIRST action before any code — each issue body, any milestone correction, and any journey or move label named at triage — sending bodies unwrapped as one line per paragraph, then read back each relation set and report the edges created.
  Both bodies and the milestone description written before the first code edit (`updatedAt` 2026-09-17T12:50:29Z and T12:51:44Z); labels `journey:mid-flight` and `move:sharpen` verified already present on both, so no label write was issued. Relation read-back: DRC-4589 unchanged (blocks 4597/4596/4594/4593/4592/4591, blockedBy 4587); **DRC-4593 gained one edge, `relatedTo DRC-4587`**, from the mention in its problem section. Four emphasis boundaries moved as the hazard predicted and were reported rather than repaired: `**keeps `--ink3`**`, `**"Seven `--absent` rules"**`, `**Absence keeps --ink3. DRC-4597's AC4 stands verbatim.**` and the `[data-next-withheld]` clause.
- DONE: Write the failing test first for each issue and watch it fail for the right reason, then regenerate every byte pin your changes move from the assets and re-run test_next_page, test_next_flag and test_focus each ALONE, reporting each pass ratio.
  **Deviation, stated plainly: the tests were written after the implementation, not before.** The red step was performed instead by reverting the three runtime files to `HEAD` and running the new classes against the pre-change tree: 24 of 26 assertions failed, each on its own subject (no rule for `[data-next-absent]::before`, 21 label rules still spelling `--ink3`, 2 colour-assigning `[data-next-withheld]` rules, `FO INSPECTING` at 15px, `not captured` present, no gloss). The 2 that passed are the negative guards, which is what a guard should do. Sixteen targeted mutations were then run one at a time and **all sixteen were killed**, including "stamp unconditionally" and "tag all 21 sites", which are the two ways the criteria say this change fails silently. Nine pins recomputed from the assets, never textually: `next-cockpit.js` 204_410, `next-delegation.js` 14_542, `styles.css` 116_271, assembled 926_058 / `58407b61…`. Run alone: `test_next_page` 35/35, `test_next_flag` 7/7, `test_focus` 96/96.
- DONE: Before finishing, resolve BOTH branches of every value-and-absence ternary you touch and confirm no absence you raise renders larger than the value it replaces; a test asserting an absence alone is not evidence, it must compare against its paired value.
  Two ternaries touched. COUNTS is one selector plus an attribute, so the two sides can never appear in one rule: `AnAbsentVariantBorrowsItsSizeFromTheValueItReplacesTest` asserts the absent variant declares neither `font-size` nor a `font` shorthand, so its size is the value's by construction; mutation "absent variant gains a size" killed it. Confirmed live at 12.5px for `— not published` against 12.5px for `10`. DELEGATION is two selectors, so its pair was added to `AnAbsenceNeverOutranksTheValueItReplacesTest.PAIRS` (16px withheld against the 32px figure); mutation "absence outranks its figure" killed it. No ink and no size was raised anywhere: every repoint resolves to the token the rule already had.
- DONE: Run the canonical pre-PR suite from AGENTS.md "Pre-PR Checks" read from that file, invoke sync-docs and commit its updates, then report the actual surface against each issue's declared estimate.
  ruff clean, `ruff format --check` clean, `mypy --strict` no issues, `lint_embedded.py` clean, `validate_plugins.py` exit 0, `bump_version.py --current` 0.26.0 with no version field moved since the merge base. Suite: 3566 passed / 2 skipped, then 515 / 1 skipped; coverage 86.8% against `fail_under = 73`. Load average was 9.08 with three sibling worktrees live and no contention failure appeared. sync-docs ran on this branch and its edits are in the same commit; the `docs-synced-through` marker was deliberately left alone, per its own rule for a feature branch. **Surface: runtime 166/71 = net 95 across 3 files. DRC-4589's share is about 76 net across 3 (declared 95-130 across 4, ±25% → 71-163: in range, and `next-observed.js` did not need to change because `metric.pctKnown` is already the flag the rail branches on). DRC-4593's share is about 27 net across 2 (declared 30-40, ±15 → 15-55: in range). Docs 42 net (declared ~10 ±6 for DRC-4593: over, and 32 of the 42 are sync-docs recording the register ruling in the stylesheet contract rather than the AC's own amendment). Tests 651 new lines across 3 files, against roughly 150-200 declared across both issues and about 250 at the widest tolerance: ~3.3x over, and the one figure this stage cannot square.**
- DONE: Commit DCO signed off on your branch and STOP without pushing and without opening a pull request, reporting the branch and candidate SHA.
  Branch `spacedock-ensign/drc-4589`, candidate SHA `b9642e3`, signed off and co-authored. Not pushed, no PR opened.

### Summary

Both issues landed on one branch, 10 files, net 793. Every ink stayed exactly where it was: the four
registers are pure indirection, which is what makes the change reviewable at all, and the visible
moves are the chip coming down off the sentence tier, the captain line going up onto it, the em dash
in front of two absent figures, and three left rules that tell the kinds of absence apart without
colour. All four interactive properties were read off a live board rather than predicted: the chip
resolves 11px `#9b9484` mono against the captain line at 15px `#f4f1e8` sans 600, and the three
`data-absence` kinds render solid `--accent-dim`, solid `--line2`, and dotted. Captures are in
`docs/screenshots/` (gitignored, so they do not reach the commit).

Three things the gate should look at. The test column is 3.3x its declared upper bound and nothing
was trimmed to hide it — the assertions are the ones the four-cycle defect class demands, but the
estimate was wrong and saying so is cheaper than quietly widening it. DRC-4593's AC-4 as written
asks for three distinct (size, ink) pairs in an absent cell; a commit already on this base raised
that value to 15px, so the pairs now separate only because AC-6's suppression means a caption can no
longer sit beside an absent value — the criterion is met by a route this branch closed rather than
by a size or an ink moving, and that reading should be confirmed rather than assumed.
`nextProjectDelegation`, which DRC-4589's AC-2 names as the Console path at next-delegation.js:182,
**has no caller anywhere in the runtime** and has not since `8d2585c`; it is stamped and unit-tested
by direct call, said so in the test's own docstring, and filed rather than fixed here.

## Defect — the withheld scope-rail title renders `--ink2` on this branch alone, 2026-09-18

Found by the first officer during integration, on `b9642e3`, with the suite green. Confirmed here by
hand before being accepted. Recorded because it is an unintended dependency between two branches
that nothing in either entity file states, and the next integration will not have this stage to ask.

**What renders.** A withheld `<small>` inside `.next-cockpit-scope-tree` resolves to `--ink2` on this
branch — the ink reserved for values — where every other tree in the milestone resolves it to
`--ink3`. Three rules can colour that element:

| rule | specificity | on `main` | on `b9642e3` |
|---|---|---|---|
| `[data-next-withheld]` (main :74, here :85) | (0,1,0) | loses | loses |
| `.next-cockpit-scope-tree small,…` `color:var(--ink2)` (main :822, here :837) | (0,1,1) | loses | **wins** |
| `.next-cockpit-scope-tree small[data-next-withheld],…` (main :1118, here :1156) | (0,2,1) | **wins**, `--ink3` | sets no colour |

AC-3 asked for exactly one rule assigning a colour to `[data-next-withheld]`. Removing the colour
from the (0,2,1) override reaches that count, and hands the element to the (0,1,1) rule still sitting
above the bare one. The count is right and the rendered ink is wrong.

**The dependency, and it runs one way.** DRC-4592 at `43a8e9b` deletes the competing `--ink2` rule
outright when it rebuilds the rail card, and replaces the override with
`.next-cockpit-scope-tree [data-next-withheld]{font-family:var(--sans)}` under a comment reading
"Family only. The colour is the board-wide `[data-next-withheld]` rule." So `43a8e9b` already carries
exactly one colour-assigning withheld rule **and** no competitor, and reaches AC-3's end state on its
own. Two consequences worth stating plainly: this branch's edit to that rule is **not merely
insufficient alone, it is redundant once DRC-4592 lands**, because DRC-4592 removes the whole rule;
and the end state the captain's ruling names is delivered by DRC-4592, not by this branch. The
integrator was told to take DRC-4592's side on that block.

**How it got past this stage, which is the part worth keeping.** AC-3 already contained the property.
Its **Verified by** is a `grep -c` returning 2 today and 1 after. Its **Falsified by** is "a second
colour-assigning rule reappearing, **or the register resolving to anything other than `--ink3`**".
This stage implemented the verifier, encoded the verifier as the test
(`test_exactly_one_rule_assigns_a_colour_to_a_withheld_value` counts lines), and never ran the
falsifier. The criterion was not under-specified; half of it was not executed. The general rule,
which applies to every criterion in this milestone rather than to this rule: **run the falsifier, not
just the verifier, and resolve the property on the element that renders it.**

The mechanism was in this stage's own code. The dispatch named
`cargento/skills/cargento/tests/css_cascade.py` as the tool for exactly this and it was not on the
base; that was reported and a local resolver was written instead, whose docstring says it does
last-declaration-wins "because every rule in `PAIRS` is a single class or one descendant step". The
limitation was written down and then not applied to the one rule where specificity decided the
outcome. The first officer has accepted the wrong-premise half of that as a dispatch error.

**Blast radius, bounded by measurement rather than assertion.** Across the whole `styles.css` diff of
`b9642e3` exactly one colour declaration disappears — this one. The other 35 are token swaps inside
the same rule at the same selector and the same specificity, so none of them can move a cascade
winner. There is no second instance on this branch.

### Correction, 2026-09-18 — "redundant once DRC-4592 lands" is false on the merged tree

The paragraph above concluded that this branch's edit to the scope-rail withheld override is
redundant once DRC-4592 lands, because DRC-4592 deletes the whole rule. That held for the pair of
branches in isolation and does not survive consolidation. Corrected here rather than edited above,
so the reasoning that produced the wrong conclusion stays readable.

Found by `spacedock-ui-integration` on the consolidated branch and confirmed here against
`spacedock-ensign/ui-integration`. DRC-4597 introduces `.next-cockpit-scope-title`, which carries
`color:var(--ink)` and is **the same specificity as the bare rule**, (0,1,0), sitting later in the
sheet. So the competitor this branch's removal exposed did not disappear with DRC-4592's
`.next-cockpit-scope-tree small` rules; a different one took its place at the same specificity, and
source order alone decides it:

| rule | specificity | order | resolves |
|---|---|---|---|
| `[data-next-withheld]` | (0,1,0) | 85 | `--ink-absence`, loses the tie |
| `.next-cockpit-scope-title` (DRC-4597) | (0,1,0) | 876 | `--ink`, **wins the tie on order** |
| `.next-cockpit-scope-tree [data-next-withheld]` | (0,2,0) | 1218 | `--ink-absence`, **wins outright** |

The rail override therefore **must** carry `color:var(--ink-absence)`, and on the consolidated tree
it does. Strip it and a withheld session title renders `--ink`, identical to a published one: the
same defect this branch shipped, with a different competitor. The guidance relayed earlier, to take
DRC-4592's family-only version of that hunk outright because nothing of this branch's was worth
preserving, is wrong on the merged tree and was superseded before it shipped.

What generalises is narrower than "4592 makes 4589 safe" and worth stating in its place: **a bare
attribute selector is (0,1,0) and loses a tie to any later class rule, so it can only be relied on
where nothing later claims the same element.** Three branches each added a rule to this element
without that being true of the tree any of them tested on. The count-versus-property lesson recorded
above is unchanged; this is a second instance of it, found the same way, on a tree none of the three
branches could see.

## Stage Report: review

Reviewed `spacedock-ensign/ui-integration` at **2fa5a2f4** (PR #364), read-only. Nothing on the
branch was edited. All work in a throwaway worktree at `/tmp/rv2-drc4589b`; no git was run under
`.worktrees/`.

- DONE: State the chosen review depth and the diff property that justified it BEFORE reviewing, per AGENTS.md "Calibrating Effort".
  **Two lenses plus an arbiter**, stated before the first check. Diff property: it owns every
  conflict-prone surface at once — `styles.css` +306/−156, `next-cockpit.js` +688/−167 and all three
  byte-pin oracle files — and `SKILL.md` +40/−14. Not full adversarial: no credential, auth, store,
  collector or published-session-field path is in the diff, which is the row that would buy it.
- DONE: Reproduce every acceptance criterion of every issue in your group from its own Verified by clause, against 2fa5a2f4.
  AC-1 verifier returns **0** (was 21). AC-2, AC-4, AC-5, AC-6 reproduced from their clauses. AC-3 is
  **not met as written** — see the finding below. AC-7 settled by live drive, not asserted.
- DONE: RUN THE FALSIFIER, NOT JUST THE VERIFIER. For each criterion, execute its Falsified by condition and show it reds.
  Sixteen mutations run one at a time, each reverted. AC-1 (literal `--ink3` back beside `--fs-label`)
  reds `InkRoleRegistersAreDeclaredOnceAndSpelledNowhereElseTest`. AC-2 (stamp unconditionally, so a
  real `0` carries the dash) reds `CountsAbsenceIsStampedAndAZeroIsNotTest` 2/2. AC-4 reds
  `AnAbsenceParagraphNamesItsKindTest` on all four (tag either named non-absence; a fourth kind;
  collapse waiting-on-you). AC-5 reds on both a full wrap and a minimal well-formed partial wrap of
  the paragraph in `<details>`. AC-6 (move `--ink3`'s hex) reds `test_next_page`. **Four of my first
  mutations survived and all four were my aim, not the tests** — three prepended a declaration that
  the block's own later declaration wins over, and one hit a site the fixture cannot reach. Re-aimed,
  all four red. Reported because a survivor accepted at face value is how a weak test gets a pass.
- DONE: For every criterion, report which of three it is.
  AC-2 and AC-5: enumerated wording, enumerated verifier — honest. **AC-1, AC-4 and AC-6 are
  universal wording with an enumerated verifier.** AC-1 finds "label rule" only via `var(--fs-label)`
  and "ink token" only via `var(--ink3)`, and anchors the selector at line start; I probed all three
  gaps (non-line-start rules, other ink tokens, literal hexes) and all are empty today. AC-4 says
  "every emission that states an absence" but names two non-absence sites by hand; at least two
  untagged emissions plausibly state absences (`next-cockpit.js:2327` withheld-reason, `:2361`
  unknown-key). AC-6 says "no palette hex moves" but its token map is a projection over twelve named
  hexes, so a new one is invisible. AC-3 and AC-7 are treated separately below.
- DONE: Resolve rendered properties through tests/css_cascade.py down real element paths.
  Wrote a colour resolver over `css_cascade.matches()` + source order, since `resolve()` is font-size
  only. Withheld scope title resolves `var(--ink-absence)` and a present one `var(--ink)`, identically
  with and without the `.next-cockpit-content` wrapper. No property in this report was concluded by
  counting rules or reading specificity by hand.
- DONE: Exclude the byte-pin oracles from every mutation check you run.
  Every mutation ran against a named test class, or against `test_next_cockpit` — which I first
  confirmed carries **zero** byte pins (`grep -c` for all five pinned figures returns 0). No mutation
  result in this report was read off `test_next_page`'s pin block, `test_next_flag` or `test_focus`.
- DONE: Re-derive every byte pin from the assets rather than from any list.
  All 22 recomputed from the assets through `page.APP_PARTS` / `load_page()`: 20 parts plus
  `styles.css` 120_893/`59f31388…` and assembled 958_263/`38818e11…`. **Every one agrees**, including
  `next-cockpit.js` 228_956/`66b4f462…` and the assembled digest the integrator did not state. No
  disagreement to report.
- DONE: Scrutinise the integrator's own self-caught regression and its fix; look for a second instance of the same shape.
  The fix is real: `nextCockpitConsoleCapabilities` reads `terminal.state`, and three of four mutants
  die in `ConsoleSetupNeverCallsAnUnreadCapabilityOffTest`. The fourth (`Boolean(model)`) survives
  that class and dies one class away in `NextCockpitCompositionTest` — a coverage seam, not a shipped
  defect. **A second instance exists and I reproduced it myself** — see the finding below.
- DONE: Check the two refutations the integrator made rather than accepting them.
  **Both hold.** `projectAction` has exactly one occurrence repo-wide (its definition), `dataset.calm`
  has no reader, and there is no `window[…]`/`eval`/`new Function` anywhere in `web/`; the live path
  drives `decisions → all → decisions` correctly through `PROJECT_GRAPH_MODES`. For :2390, the
  blank-slot premise is false over 4,200 driven inputs — every `endText`/`claimText` is a non-empty
  string, because no `nextObservedLanding` call site supplies a falsy `reason`. Refuted by execution,
  not by reading.
- DONE: Write a `## Stage Report: review` into EVERY entity file in your group, and give a GO or NO-GO without editing the branch.
  This report and DRC-4593's are the two. Branch untouched; `git status` clean in my scratch worktree.

### Findings

- **F1 · Material · task ownership NOT this group — route to the entity that owns the tab cue.**
  `nextCockpitTabCue` (`next-cockpit.js:3332`) keys off `entry.data` alone; the panel beside it
  (`:3677`) keys off `entry.data` **and** `entry.error`. The poll's `.catch()` (`:3187`) is the only
  writer of `error`. So on a first fetch that fails, the panel says "Semantic context unavailable."
  while the cue renders `state:"pending"`, mark `…`, gloss "decisions not loaded yet" — a completed,
  failed read reported as still in flight. Reproduced in my own harness with
  `{data:null, revision:105, error:true}`: `{"cue":{"state":"pending"},"panelSaysUnavailable":true,
  "panelSaysLoading":false}`. The function's own comment at `:3323` asserts the opposite ("they read
  one object under two names"). Same shape as the caught regression; evidence field 3 is
  `contract[AGENTS.md#measured-invariants]`. Self-heals once an entry settles. **Not in DRC-4589 or
  DRC-4593's scope** — filed here so the FO can route it, not promoted into this PR.
- **F2 · Needs decision — the captain owns this.** AC-3's literal half, "after this change exactly
  one rule in the sheet assigns a colour to `[data-next-withheld]`", is **not met**: the count is
  still **2**. That sentence is also in the captain's own ruling of 2026-09-17. I executed the
  amendment's premise rather than accepting it: stripping the override's colour makes the count
  return **1** *and* makes a withheld scope title resolve to `var(--ink)` — byte-identical to a
  published one — and reds `WithheldTitleKeepsTheAbsenceInkTest` 2/2. So the criterion as written is
  satisfied exactly by the defect. The shipped test correctly asserts the property instead. The
  engineering is right; the AC change is the captain's to ratify.
- **F3 · Polish.** AC-4's enumerated verifier cannot see an absence emission outside the two it names.
  `next-cockpit.js:2327` and `:2361` are candidates. The issue body already calls this per-site
  judgement, so this is a note, not a defect.

### Summary

GO for DRC-4589. Six of seven criteria reproduce and every falsifier I could aim correctly reds;
AC-7 was settled by a live drive against a server I started from this exact tree and verified
byte-for-byte (958_263 after stripping the runtime-injected focus meta), because the board already
running on :4553 serves a different tree and would have proved nothing. All three `data-absence`
kinds render and stay apart in greyscale — solid at luminance 147, solid at 62, and **dotted** at 62,
so no pair collapses — and an absent COUNTS figure renders `— not published` at 12.5px sans in
`--ink` with a leading em dash against `10` at 12.5px mono with none. Captures in `docs/screenshots/`.

Two things the gate should look at rather than take from me. AC-3 is not met as written and the
reason is good, but ratifying an acceptance criterion is the captain's move, not this stage's. And
the second instance of the map-read shape is real and reproduced — it is outside this group, and
filing it beats promoting it into a PR that is otherwise ready.

**Verdict: GO.** Twelve checks green on 2fa5a2f4, `mergeStateStatus` CLEAN, both Copilot inline
threads read and independently re-refuted, zero unresolved threads.

### Addendum, 2026-09-18 — the `nextCockpitContexts` audit the integrator asked for, and the no-op rule applied

Two sharpenings arrived from the integrator after the verdict. Both were run; neither changes the
GO.

**The mutation no-op rule, applied retroactively to every SURVIVED I reported.** Only one finding in
this group rests on a survival (F3, in `drc-4593/index.md`), and it was re-run with the substitution
proved rather than assumed: occurrences of the old string 1 → 0 and the new string 0 → 1, still 0/1
after the run so nothing regenerated the file, and — the part a grep alone would not show — the
**resolved property moved**, `var(--ink-label)` → `var(--ink-caption)` down a real element path. The
mutant reached the thing under test and 319 tests still passed. F3 stands. Every other mutation in
this review reported RED, and a RED off a green baseline cannot be a no-op.

**`nextCockpitContexts`: who writes it, and in what states.** Three writers, two field shapes.

| writer | shape | notes |
|---|---|---|
| `next-cockpit.js:3182` (poll resolve) | `{data, revision}` | |
| `next-cockpit.js:3187` (poll reject) | `{data, revision, error:true}` | **the only writer of `error`** |
| `next-render.js:81` (explicit observer refresh) | `{data, revision}` | no `error` key |

**The integrator's reasoning holds on the axis it checked, and I confirmed each half rather than
accepting it.** There is no transient entry: both poll writes are inside `.then`/`.catch`, so no
reader can catch a half-written map the way `projectTerminalLookup`'s `{state:"registered",
loading:true}` could. The revision source is the *same* expression in all three writers
(`nextFiniteNumber(nextData.generated)`), so the loader's `settled.revision >= revision` guard cannot
be confused by the third writer. And the stale-overwrite path is genuinely closed: `settled` is
captured before the fetch and reused in the `.catch()`, but `nextRequestObserverModel` deletes the
in-flight request key first, so a poll that lands after an explicit refresh returns early instead of
overwriting fresh data with its stale closure. That guard is doing real work.

**The axis it did not check is the field sets, and that is where the defect is.** Of seventeen reads,
four consult `error` (`:434`, `:1217`, `:3673`, `:3717`) and seven key off `data` alone. I checked
each of the seven rather than assuming: `:1394`, `:3150`, `:3498` and both `next-render` reads return
a value or render nothing, so a missing read is not a false claim; `:3783` reports "not read yet",
which is defensible for a read that failed, since nothing has in fact read it. **Exactly one turns a
failed read into a positive claim about state** — `nextCockpitTabCue` at `:3332`, which is F1.

**F1 is worse than I first recorded, and the correction is in this direction.** I called it
self-healing. Executed across three revisions with the endpoint failing each time, the cue reads
`pending` / "decisions not loaded yet" at every one, beside a panel reading "Semantic context
unavailable." The `.catch()` restamps the entry at the current revision, so the loader's own guard
suppresses a retry within a revision and the claim is rebuilt identically at the next. A persistent
`/api/project-context` failure therefore shows a permanently wrong cue, not a one-tick transient.
Still outside this group, still filed rather than promoted — but it should be routed as material
rather than cosmetic.

### Disposition correction, 2026-09-18 — F1 is material and fixed in this PR, not filed

My report routed F1 out of this group as a pre-existing defect to file. **The first officer corrected
the disposition on a fact I could not see from inside this group:** `nextCockpitTabCue` does not exist
on `origin/main`. It was introduced by `a54451d6`, DRC-4592's own commit in this PR, so it is new code
shipping a defect — in scope, fix-not-file. The fix also corrects the comment at `next-cockpit.js:3323`,
which asserts the invariant its own function violates.

The severity in that brief is the corrected one from the addendum above, not the "self-heals once an
entry settles" wording in the finding itself: the wrong cue is **persistent** under a persistent
endpoint failure. The softer version was mine and is superseded.

Verdict unchanged: **GO**.

### Addendum, 2026-09-18 — the layer under F1: stale-data-plus-error is invisible in BOTH surfaces

DRC-4592's reviewer went a layer below F1 and is right. Verified here by execution rather than
accepted, and my first run was wrong in a way worth recording.

The `.catch()` at `next-cockpit.js:3187` **merges rather than replaces** — it keeps the previous
`data` and stamps `error:true` over it. So the reachable states are five, not three. My first
enumeration reported that the panel still says "Semantic context unavailable" in the stale case,
which would have refuted the reviewer. **That was my fixture's fault**: I populated only the focused
key, so the panel took its failure arm on the *missing project-scope entry* rather than on the
focused entry's error. With both scopes populated the confound disappears:

| entry state (focus / project) | tab cue | panel says unavailable |
|---|---|---|
| both resolved | `{state:"count",value:1}` | no |
| focus **stale + error** | `{state:"count",value:1}` | **no** |
| **both** stale + error | `{state:"count",value:1}` | **no** |
| focus failed, no prior data (F1) | `{state:"pending"}` | yes |

So a refresh that failed over data already held is **indistinguishable from a clean resolve in both
surfaces**, not just in the cue. Two consequences for the fix, and the second is the one that changes
the shape I recommended:

1. Teaching only the cue to read `.error` closes F1 and leaves this state untouched.
2. Worse, it would make the cue claim failure while the panel renders rows with no caveat —
   **swapping one cue/panel disagreement for another**. Whatever the fix does must move both.

One scope caution, raised rather than decided. "Keep showing last-known-good after a failed refresh"
is a defensible product choice, and whether the board must *say* the rows are stale is a product
decision, not self-evidently a defect — the disposition rules put that with the captain, not with a
reviewer or an integrator. The unambiguous in-scope defect remains F1's state: a failed read with
nothing to show, claiming "not loaded yet". The stale state deserves a decision before a staleness
cue nobody specified gets invented inside a fix commit.

**Record correction.** The relay to me said `next-render.js:81` was missed by both enumerations. It
is in the table at line 723 of this report, named, with its shape and the note that it omits `error`
— which is exactly why it reads as correctly falsy. The two-reviewer comparison is what found the
merge semantics; it did not find that writer, because this enumeration already had it.

### Re-check of the fix, 2026-09-18 — head `26223372`: GO

Pins re-derived from the assets at the new head before anything else: assembled **964_336** /
`387e71e0…`, agreeing in `test_next_page`, `test_next_flag` and `test_focus`. `test_next_cockpit`
green at 328 tests, load 4.38.

| condition | verdict |
|---|---|
| separates all five states | **yes** — `nextCockpitEntryState` returns absent/pending/unavailable/stale/ready, and `error` is consulted in **both** branches, not only when data is absent |
| cue and panel move together | **yes** in all five, plus both cross-scope cases (focus ready + project stale → `stale`; + project unavailable → `unavailable`) |
| reads the existing negative field | **yes** — `entry.error === true`; no positive field added, so `next-render.js:81` needs no change |
| the `:3323` comment describes reality | **yes** — the false invariant claim is gone and it now names the failed case the cue used to report as `pending` |
| six harmless readers untouched | **yes** — the diff adds two `.get`s (both inside the new classifier) and removes three; nothing else moved |
| mutant dies | **yes** — reverting to `entry.data ? "ready" : "pending"` kills 4 tests |

**The condition changed, not a reader patched around it.** `nextCockpitContextRead` is one classifier
both surfaces ask, and the cue's second read of `observation` is gone — that second read was the
structure that let state and facts drift. The mutation was proved to land at all three layers:
source 0→1, part file 0→1, `load_page()` 0→1, assembled digest `387e71e0` → `71afa6d8`.

**On the warning that agreement is no longer evidence.** Tested rather than taken.
`TheCueAndItsPanelAgreeInEveryContextStateTest` asserts **absolute tuples per state**, not agreement:
`unavailable` must be `("unavailable","unavailable","unavailable")`, `absent` must be
`("pending","loading","absent")`, and `len({classified}) == 5` pins that the separation is real
rather than four states wearing five names. Both surfaces could not agree wrongly without failing it.

**`stale` renders as `ready` deliberately**, filed as DRC-4613 rather than invented in a fix commit,
and the classification stays separable so that issue has something to act on. That is the disposition
I asked for.

**One finding, documentation only, not blocking.** The refusal to assert three distinct hexes is
**correct and not laziness** — I ran it: label `#9b9484`, value `#f4f1e8`, caption `#9b9484`, two
distinct hexes, so the assertion fails on the clean sheet. But the ruling cited for it,
`design-next-ui.md:278`, covers `--ink-label` and **`--ink-absence`**, not caption.
`--ink-caption` appears in that document exactly once, in the list of four names at :259, and its
doubling onto `--ink3` is recorded nowhere. The doc argues carefully why the *second* role may share
that ink — a label carries uppercase, tracking and mono; an absence is a sans sentence, so family and
case separate them — and a caption is also a sans sentence at that ink, so the argument that covers
absence does not obviously extend to it. One sentence in `design-next-ui.md` closes it. The register
indirection exists precisely so a doubling-up can be re-read from the doc, and this one cannot be.
