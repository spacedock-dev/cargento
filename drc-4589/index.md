---
id:
title: "Split the three inks onto label, value and absence roles so a label stops sharing its ink with its own answer"
status: triage
source: "https://linear.app/recce/issue/DRC-4589/split-the-three-inks-onto-label-value-and-absence-roles-so-a-label"
started: 2026-09-17T10:42:56Z
completed: ""
verdict: ""
score: 0.6
worktree: ""
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
                state: pending
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

- **AC-3 — offline:** Every `--absent` rule and both `[data-next-withheld]` rules resolve to one
  declared ABSENCE register, and after the change **exactly one rule in the sheet assigns a colour
  to `[data-next-withheld]`**: styles.css:52 keeps it, styles.css:1089 keeps
  `font-family:var(--sans)` and drops its redundant `color:var(--ink3)`. **Verified by:**
  `grep -c 'data-next-withheld[^{]*{[^}]*color:' styles.css` returns **2** today and must return
  **1**; a `tests/test_next_page.py` assertion pins that count so it cannot drift back.
  **Falsified by:** a second colour-assigning `[data-next-withheld]` rule reappearing, or the
  register resolving to anything other than `--ink3` — which would break DRC-4597's AC4, and the
  captain ruled on 2026-09-17 that it stands verbatim.

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
