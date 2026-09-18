---
id:
title: "Invert the briefing's emphasis and let its all-absent grid collapse"
status: review
source: "https://linear.app/recce/issue/DRC-4593/invert-the-briefings-emphasis-and-let-its-all-absent-grid-collapse"
started: 2026-09-17T10:42:56Z
completed: ""
verdict: ""
score: 0.6
worktree: .worktrees/spacedock-ensign-drc-4589
issue: ""
pr: "pr-merge:364"
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
        - id: gate:drc-4593:triage
          stage: triage
          attempts:
            - id: gate-attempt:drc-4593-triage-1
              briefing:
                id: briefing:drc-4593:triage:attempt-1:revision-1
                digest: sha256:e88c57f07f3f52af5ff00ebf209e64b7df6fab30f1a98bb62718f2c8e9f0006c
                room-ref: ./review/triage/briefing-1
              resolution:
                type: Resolution
                id: resolution:spacedock:drc-4593:triage:1
                briefing: briefing:drc-4593:triage:attempt-1:revision-1
                by: agent:first-officer
                at: "2026-09-17T11:02:35.073148Z"
                decision: approve
                reason: 'Checklist 3 done / 1 skipped / 0 failed, and the skip is approved as a scope reduction. The collapse mechanism was measured rather than repaired: an all-absent briefing is 171px under today''s grid and 171px under the proposed one, because grid rows already size to content, so the remaining prize is about 16px of padding. Repairing a mechanism with zero measured payoff is exactly the scope the stage definition warns against, and the ensign put the reduction to the gate rather than taking it. AC-1..AC-6 resolve. The stage also found DRC-4587 made this surface worse in two measured ways and widened AC-4 to bind ordering rather than separation alone, and proved by running rather than reading that the whole briefing carries exactly one absent node.'
                conn:
                    quote: I pre-approve all the triage and merge gates, just automate this entire process and do it
                    source: Captain, this session, 2026-09-17
              application:
                target-stage: implementation
                state: consumed
        - id: gate:drc-4593:review
          stage: review
          attempts:
            - id: gate-attempt:drc-4593-review-1
              briefing:
                id: briefing:drc-4593:review:attempt-1:revision-1
                digest: sha256:e40ed998b2c60a65dac809130aaa9954b56f9ecb0b8a80b400a7f27d52e66e0c
                room-ref: ./review/review/briefing-1
---

[DRC-4593](https://linear.app/recce/issue/DRC-4593/invert-the-briefings-emphasis-and-let-its-all-absent-grid-collapse) — Invert the briefing's emphasis and let its all-absent grid collapse

Seeded 2026-09-17 from the live Linear read of the Clean and Cogent UI/UX milestone.
Linear owns the current issue body, its relations and its resources; triage fetches them
live and validates them against the tree before anything is built. No triage, approval,
implementation or delivery is claimed here.

---

## Triage: adversarial read (2026-09-17, against `spacedock-ensign/drc-4587` @ 3cc7ef49)

Every figure below was taken on the **post-DRC-4587 tree**, not on `main`. DRC-4587 moves the type
scale underneath this issue, and it changed the defect's shape rather than leaving it alone. Three
kinds of evidence: the stylesheet and the JS read directly; the headless-node harness executed; and
one live drive of the board at `127.0.0.1:4571` in a 1680x1057 viewport at dpr 1.

### Is the problem still real? Yes, and post-4587 it is sharper than the issue says.

Measured live, computed styles inside the briefing:

| element | size | ink | family |
|---|---|---|---|
| authority `<span>` "FO INSPECTING" | **15px** | `--ink` | sans |
| COMMAND attention row `<strong>` | 12.5px | `--ink` | sans |
| captain line `<small>` "Captain state unknown" | 12.5px | `--ink3` | sans |
| ASSIGNMENT label `<span>` | 11.5px | `--ink3` | mono |
| ASSIGNMENT value `<strong>` "Not observed" | **12.5px** | `--ink3` | sans |
| ASSIGNMENT caption `<small>` "Assignment evidence not published" | **15px** | `--ink3` | sans |

Two things follow that the issue, written pre-4587, could not have known.

**The brightest string is now also the largest.** Pre-4587 the FO chip and the captain line were both
12.5px and the gap was colour alone; styles.css:1091 now sets `.next-cockpit-authority>span` to the
sentence tier, so the gap is colour *and* size. The issue's premise strengthened.

**A second inversion appeared, inside ASSIGNMENT.** styles.css:1095 lifted
`.next-cockpit-evidence-missing` to the sentence tier while styles.css:1083 held
`.next-cockpit-recovery strong,small` at `--fs-xs`. The result is a cell where the *caption* is 15px
and the *value* it explains is 12.5px, both `--ink3`. The issue described "three ink3s with a 1px
size delta"; what is there now is three ink3s in the wrong order. AC-4 below is widened to bind the
ordering, not just the separation.

### The collapse cannot earn its keep. Measured, and recommended for removal.

The Solution asks for `data-all-absent` plus `auto-fit,minmax(210px,max-content)`, "measuring the
resulting height rather than predicting it". Measured, in the live DOM, by cloning the section and
reducing all three data cells to a label plus one absence line:

| variant | section height |
|---|---|
| all-absent, today's `repeat(3,minmax(0,1fr))` | **171px** |
| all-absent, `repeat(auto-fit,minmax(210px,max-content))` | **171px** |
| the above, plus cell padding `10px 12px` -> `6px 12px` | 155px |
| the above, plus the absent caption dropped to the value tier | 151px |
| populated, as the board actually stands | 349-390px (volatile; it re-renders) |

**The grid change buys exactly zero.** CSS grid rows already size to content, so an all-absent
briefing has already collapsed before any of this lands. The whole remaining prize is about 20px of
padding on a 171px block, and none of it comes from the mechanism the issue names. The 300x150px
EXECUTION cell in the screenshot is not the grid padding a small cell — it is one tall sibling
stretching its row-mates in the *populated* case, which no height change can recover because the
tallest cell sets the row either way.

The recon had already found the mechanism unbuildable as specified (`.next-project-value--absent` is
emitted only by `nextProjectValue`, and exactly **one** node in the whole briefing carries it —
measured, not inferred, by executing the harness fixture). Repairing it would mean stamping a
per-cell absent flag at emission in `next-cockpit.js`. That repair is real work whose measured payoff
is zero. **Recommendation: drop the stamp, drop the grid change, drop the collapse criterion.** The
gate is asked to rule on this; the padding reduction is available separately as a one-line change
with no detection mechanism at all, if the captain wants the 16px.

### Does any part of the body describe a state that no longer exists?

Four claims are now false, all of them pixel or line figures taken pre-4587:

- "tab content does not begin until y~547" — measured **666** on the post-4587 tree.
- "the EXECUTION cell spans x~575-875, y~270-420" — the cells measure **334x280** at this viewport.
- "styles.css:841 / :830 / :813 / :816" — the block moved; it is now **849 / 839 / 821 / 824**, and
  ":830" was the `strong` rule rather than the `small` rule even on `main` (off by one).
- "15.15:1 on panel" — correct for `--panel`, but the briefing sits on `#app`, which is `--bg`. The
  real ratio is **16.36:1**. Higher, so the argument is unaffected.

### The "None recorded" convention does not exist

`grep` across `*.js`, `*.py`, `*.css` and `*.md` returns **nothing** for "None recorded". The Solution
treats it as the existing empty-collection convention; it would be a new string, and the "one glossary
line" has no home either — `docs/design-next-ui.md` carries no absence-wording section. Inventing a
convention and its documentation in the same change is the shape AGENTS.md's "a fix can create the
defect it closes" warns about, so the rewrite below does **not** introduce it.

What is there instead is five phrasings built from three verbs — *observed*, *published*, *captured*.
The rewrite keeps two and retires the third, on a rule derived from the tier rather than from taste:
**a value says what was not observed; a caption says what was not published.** "captured" leaves the
briefing. No new word enters it.

### The chip demotion argues with DRC-4587's own list, on DRC-4587's own rule

`docs/design-next-ui.md` states the test: *"a rule is on the sentence tier when it sets its text in
sans and declares its own prose line-height. Mono is a string a source published."* `FO INSPECTING` is
a string the workflow published, not prose. Setting it as a mono chip at the label tier is that rule
applied, not broken — but the document's counts (sixty-seven, forty-nine, eighteen) move by one and
must be amended in the same PR. Checked: those counts are not pinned by `test_documentation.py`.

### Verified by execution, not by reading

`cargento/skills/cargento/tests/test_next_cockpit.py:735` asserts "Assignment evidence not published"
inside `NextCockpitCompositionTest.test_briefing_names_missing_readings_before_any_disclosure`. I ran
that fixture through the harness and printed the producer: `briefing.task.known === false`, provenance
`null`, and the string renders. That is precisely the arm AC-6 suppresses, so the assertion must be
**re-pointed**, not extended. The same run returned `next-project-value--absent` count **1** for the
whole briefing, which is what refutes the collapse mechanism above.

### Composition with DRC-4589 (they share PR 3)

DRC-4589 declares the label/value/absence registers and repoints the cockpit rules to them, naming
the same override lines this issue names. **DRC-4589 lands its registers first and DRC-4593 consumes
them.** This issue must not declare a register of its own; where the rewrite says "the absence
register", it means DRC-4589's. If the two land in one PR, 4589's hunk is applied first and 4593 is
written against it, never the reverse. I did not rule on the DRC-4589/DRC-4597 `styles.css:1081`
contradiction: neither has triaged, and it does not touch this issue's surface.

## Linear edits made

**Nothing has been written to Linear.** The two records below are the verbatim pre-edit capture; the
drafts beneath them are what `implementation` writes once this gate approves.

### Captured original — DRC-4593 issue body (verbatim, 2026-09-17)

```markdown
## User value

Anyone opening a project notices this before anything else. Today the briefing spends the top half of the first screen on three cells that usually all say nothing was observed.

## The Problem

The PROJECT RECOVERY BRIEFING is redrawn above every tab, so it is the densest thing in the cockpit by exposure, and tab content does not begin until y≈547 in all five captures.

Its brightest string is "FO INSPECTING", given full `--ink` by styles.css:841 — the sibling `--fo-continues` variant deliberately drops to ink3, so ink here is a chosen emphasis step. Meanwhile "Captain not needed", the one line telling the reader they have nothing to do, is a `<small>` at ink3. The strongest emphasis in the chrome is spent on Spacedock vocabulary that appears nowhere else and is never defined, and the reassurance is the dimmest thing in the card.

The grid wastes the space as well: `repeat(3,minmax(0,1fr))` pads the EXECUTION cell to roughly 300×150px to say three words. And the block states one absence in five phrasings built from three verbs — Not observed, not published, published no goal, no execution observed, not captured — implying epistemic distinctions that mostly do not exist.

**Measured**

* styles.css:841 `.next-cockpit-authority--fo-inspecting>span{color:var(--ink)}` — 15.15:1 on panel, the brightest token; :843 drops the `--fo-continues` sibling to ink3
* "Captain not needed" is emitted as a `<small>` (next-cockpit.js:563-568) styled ink3 by `.next-cockpit-recovery small` (styles.css:830)
* `fo-inspecting` is computed at next-cockpit.js:556-557 from incomplete attention coverage or open FO items — it says nothing about what the agent is doing
* styles.css:813 `grid-template-columns:repeat(3,minmax(0,1fr))` with `>div{padding:10px 12px}` (:816); the EXECUTION cell spans x≈575-875, y≈270-420 for one line at y=304
* LATEST EVIDENCE is already a grid child (next-cockpit.js:2770-2776, `grid-column:span 2`, styles.css:818), not a separate band
* In an absent cell the label (ink3 11.5px mono), the value (ink3 12.5px sans) and the caption (ink3 12.5px) are one ink with a one-pixel size difference
* Eight absence claims across seven lines of chrome, in five phrasings from three verbs
* Tab panel content begins at y≈547 in every capture

**In the attached screenshot**

1. "FO INSPECTING" is the brightest string on the page
2. "Captain not needed" is a `<small>` at ink3
3. EXECUTION cell: \~300×150px for three words
4. Tab content starts at y≈547 on all five tabs

## The Solution

Reallocate the emphasis without asserting anything unobserved.

Keep `FO INSPECTING` and `FO CONTINUES` verbatim as a trailing mono chip at the label tier — do **not** substitute "Agent is looking, not changing anything", which is fabricated — and gloss them once beside the heading: "FO is the first officer, the agent driving this workflow; Captain is you." Drop the authority span to ink2 and give the captain-truth line full ink at weight 500, with `--amber` reserved for the inverse state.

Leave `REFRESH · refresh workflow discovery` as the attention row it is; it is emitted only when discovery is in error or unavailable (next-cockpit.js:459-470), so demoting it deletes a live signal.

Apply the label/value registers inside the override block at styles.css:1071-1075, not the base rules at 829-831 which those lines override; keep the known/absent tone split at 1071/1072, the only working epistemic cue in the block, and lift the absent value one step off the label.

Let the grid collapse when everything in it is absent: stamp `data-all-absent` when every value carries `.next-project-value--absent` and switch to `auto-fit,minmax(210px,max-content)` with tighter padding, **measuring** the resulting height rather than predicting it.

Fix the vocabulary by auditing each producer's value, not the rendered string: `None` renders "Not observed", an empty collection renders "None recorded" — so "No execution observed", which derives from `!sessions.length`, becomes the latter. Keep "This session published no goal", which names its subject. Suppress "Assignment evidence not published" only when `briefing.task.known` is false.

## Acceptance

- [ ] The reader-facing captain line is the brightest string in the COMMAND cell; FO INSPECTING and FO CONTINUES survive verbatim as a glossed chip
- [ ] No briefing string asserts agent behaviour the board did not observe, and the REFRESH attention row is unchanged
- [ ] In an absent briefing cell the label, value and caption occupy three distinct registers
- [ ] An all-absent briefing collapses to a measured, smaller height with every sentence still rendered
- [ ] Absence wording is chosen from the producer's value (None versus empty), documented by one glossary line, and pinned by a unit test
- [ ] "Assignment evidence not published" still renders when a task is known and its provenance is not

---

Complaint **C2** · tabs: chrome (all five) · severity **major** · effort **M** · blocked by DRC-4589

Raised from user feedback; mechanism and figures established by a measured audit of the live board and the shipped stylesheet.
```

### Captured original — "Clean and Cogent UI/UX" milestone description (verbatim, 2026-09-17)

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

### Drafted rewrite — DRC-4593 issue body (NOT written to Linear)

```markdown
## User value

Anyone opening a project reads this block before anything else, because it is redrawn above every
tab. Today its loudest string is `FO INSPECTING` — internal workflow vocabulary, never glossed, and
computed from attention coverage rather than from anything the agent is doing — while the one line
that tells the reader they are off the hook is the dimmest and smallest thing in the same cell.

Promise **P2** — *what is it doing, and when should I come back?* Move **sharpen**: the same
information, weighted so the answer outranks the label that names it.

## The problem

Measured on the post-DRC-4587 tree, live, at 1680x1057:

| in the COMMAND cell | size | ink |
|---|---|---|
| `FO INSPECTING` (`.next-cockpit-authority>span`) | 15px | `--ink` |
| the attention row | 12.5px | `--ink` |
| `Captain not needed` / `Captain state unknown` | 12.5px | `--ink3` |

DRC-4587 lifted the authority span to the sentence tier (styles.css:1091), so the brightest string is
now the largest one as well. `fo-inspecting` is computed at next-cockpit.js:556-557 from
`coverage.state !== "complete" || system.length` — it reports attention coverage, not agent activity.

The same pass left a second inversion inside ASSIGNMENT: styles.css:1095 raised
`.next-cockpit-evidence-missing` to 15px while styles.css:1083 held the value at 12.5px, so an absent
cell now reads label 11.5px mono `--ink3`, value 12.5px sans `--ink3`, caption **15px** sans `--ink3`.
Three inks, and the least important of the three is the biggest.

The block also states absence in five phrasings from three verbs — observed, published, captured —
implying distinctions that do not exist.

## The solution

**Reallocate the emphasis.** Set `FO INSPECTING` / `FO CONTINUES` verbatim as a trailing mono chip at
the label tier, and gloss them once beside the briefing heading: *"FO is the first officer, the agent
driving this workflow; Captain is you."* Do not substitute invented prose about what the agent is
doing. Give the captain-truth line the sentence tier at full `--ink`, weight 500. `--amber` stays the
captain-needed cue it already is (styles.css:846).

Demoting the chip argues with DRC-4587's sentence-tier list on that list's own rule — *mono is a
string a source published* — so amend the list and its three counts in `docs/design-next-ui.md` in
the same change.

Leave the FO attention row alone. It is emitted only when workflow discovery errors or is unavailable
(next-cockpit.js:462-470); demoting it deletes a live signal.

**Fix the registers.** Consume the label/value/absence registers DRC-4589 declares — do not declare a
fourth here — and apply them in the briefing so that a caption is never set larger than the value it
explains.

**Fix the vocabulary on a rule, not on taste.** A value says what was not *observed*; a caption says
what was not *published*. "captured" leaves the briefing: `Actionable direction not captured` and
`Session result not captured` become observed-form. `This session published no goal` stays — it names
its subject. No new absence phrase is introduced; "None recorded" appears nowhere in the repository
and is not adopted. Suppress `Assignment evidence not published` when `briefing.task.known` is false,
where the value already says `Not observed` and the caption only repeats it.

## Not doing: the all-absent collapse

Dropped on measurement — see the dated history below.

## Acceptance

- [ ] `FO INSPECTING` and `FO CONTINUES` survive verbatim as a mono chip at the label tier, with a
      one-line gloss beside the briefing heading
- [ ] On a live board the captain-truth line is the largest and brightest string in the COMMAND cell,
      and the authority chip is neither
- [ ] No briefing string asserts agent behaviour the board did not observe, and the FO attention row
      renders unchanged
- [ ] In an absent briefing cell the label, value and caption occupy three distinct registers, and no
      caption is set larger than the value it explains
- [ ] Absence wording is derived from the producer's tier on a two-verb rule, "captured" no longer
      appears in the briefing, and no new absence phrase is introduced
- [ ] `Assignment evidence not published` renders when the task is known and its provenance is not,
      and does not render when the task is unknown

---

## History

**2026-09-17 — the all-absent grid collapse was dropped, on measurement.** The original body asked to
stamp `data-all-absent` and switch to `repeat(auto-fit,minmax(210px,max-content))` with tighter
padding, measuring the result. Measured live on the post-DRC-4587 tree, an all-absent briefing is
**171px** under today's `repeat(3,minmax(0,1fr))` and **171px** under `auto-fit` — grid rows already
size to content, so the briefing has collapsed before the change lands. The remaining prize is ~16px
of cell padding, available as a one-line change needing no detection mechanism. The detection
mechanism as specified could not fire in any case: `.next-project-value--absent` is emitted only by
`nextProjectValue` (next-projects.js:11) and exactly one node in the whole briefing carries it, while
ASSIGNMENT, EXECUTION and COMMAND emit their absences as bare `<strong>`.

**2026-09-17 — four figures in the original body were superseded by DRC-4587.** Tab content begins at
**y=666**, not y~547. The data cells measure **334x280**, not ~300x150. The stylesheet lines moved:
813/816/830/841 are now **821/824/839/849**, and the "830" citation named the `strong` rule rather
than the `small` one even before the move. The contrast figure 15.15:1 was computed against `--panel`;
the briefing sits on `--bg`, where the real ratio is **16.36:1** — higher, so the argument holds.

**2026-09-17 — the "None recorded" empty-collection convention was found not to exist.** The original
Solution treated it as the established spelling for an empty collection. It appears nowhere in the
repository, and `docs/design-next-ui.md` has no absence-wording section to host the glossary line, so
adopting it would have created a convention and its documentation in one change. Replaced by the
two-verb rule above, which introduces no new word.

---

Complaint **C2** · tabs: chrome (all five) · severity **major** · effort **M** · blocked by DRC-4589
```

### Drafted correction — "Clean and Cogent UI/UX" milestone description (NOT written to Linear)

One paragraph is now false and one addition is owed. Under **How this was measured**, replace the
`127.0.0.1:4553` sentence with:

```markdown
Density, ink distribution and control counts read off the live DOM at `127.0.0.1`. Density figures are floors — they were taken on a quiet, unannotated session, and a busy project has more text, not less. **Every pixel and word-count figure in this milestone's issues was taken before the 15px sentence tier landed and is stale**: tab content now begins at y=666 rather than y≈547, and the briefing's data cells measure 334×280 rather than ~300×150. Re-measure against the current tip during triage rather than quoting the filed figure.
```

Nothing else in the milestone changes. Its **What is left** count stays at twelve: this issue narrows,
it does not close, and no sibling is created.

### Labels to set

Already correct on the issue; `implementation` sets nothing new.

- `journey:mid-flight` — present. The reader is mid-flight, deciding whether to intervene.
- `move:sharpen` — present. Same information, re-weighted; nothing new is surfaced and nothing is cut.

## Acceptance criteria

- **AC-1 — offline:** The briefing renders `FO INSPECTING` and `FO CONTINUES` verbatim as a trailing
  mono chip at the label tier, and a one-line gloss naming FO and Captain appears beside the briefing
  heading. **Verified by:** a `test_next_cockpit.py` fixture asserting both strings are present, that
  the authority `<span>` matches the chip selector rather than the sentence-tier rule at
  styles.css:1091, and that the gloss string is in the `<header>` of `.next-cockpit-recovery`; today
  the strings are present but the span resolves to `--fs-sentence` and no gloss exists.
  **Falsified by:** substituting prose for either state name, or dropping the gloss.
- **AC-2 — interactive:** On a live board at `127.0.0.1`, the captain-truth line is the largest and
  brightest string in the COMMAND cell, and the authority chip is neither the largest nor the
  brightest. **Verified by:** loading `#n=project:<label>` and reading `getComputedStyle` on
  `.next-cockpit-authority>span`, its sibling `<strong>`, and the captain `<small>`; today that
  returns 15px `--ink` for the chip against 12.5px `--ink3` for the captain line, which is the defect.
  **Falsified by:** any board state where the chip still outranks the captain line on either size or
  ink. A CI proxy asserts the selectors only and is explicitly not this criterion.
- **AC-3 — offline:** No briefing string asserts agent behaviour the board did not observe, and the FO
  attention row renders unchanged. **Verified by:** a fixture driving `discovery.state === "error"`
  and asserting the attention row's text and `<strong>` shape are byte-identical to today's, plus a
  grep-shaped assertion that the authority block contains no verb describing agent activity.
  **Falsified by:** demoting the attention row, or introducing a string such as "Agent is looking".
- **AC-4 — offline:** In an absent briefing cell the label, value and caption resolve to three
  distinct registers, and no caption resolves to a larger size than the value it explains.
  **Verified by:** a fixture reading the three declarations for an absent ASSIGNMENT cell out of the
  assembled stylesheet and asserting three distinct (size, ink) pairs with caption <= value; today
  that returns label 11.5px/`--ink3`, value 12.5px/`--ink3`, caption 15px/`--ink3` — two registers,
  and inverted. **Falsified by:** any pair collapsing, or the caption regaining the larger size.
- **AC-5 — offline:** Absence wording is derived from the producer's tier on the two-verb rule, the
  word "captured" no longer appears in the briefing, and no absence phrase absent from the repository
  today is introduced. **Verified by:** a fixture asserting the produced briefing HTML contains no
  "captured", that `!sessions.length` and `task === None` each reach their declared string, and a
  `grep` asserting "None recorded" is still absent from the tree. **Falsified by:** retaining
  "captured" anywhere in the block, or adding a fourth verb.
- **AC-6 — offline:** `Assignment evidence not published` renders when `briefing.task.known` is true
  and provenance is absent, and does not render when `briefing.task.known` is false. **Verified by:**
  two fixtures, one per arm; the false arm is today's `test_next_cockpit.py:735`, which I ran and
  confirmed renders the string with `task.known === false`, so that assertion is re-pointed rather
  than extended. **Falsified by:** either arm rendering the other's outcome.

**Offline/interactive split:** five offline, one interactive (AC-2). AC-2 is the user-visible property
the stage requires, and it is a rendered-size-and-contrast judgement against a painted surface, so a
CSS-selector assertion is a proxy for it and is not offered as the criterion. No harness is proposed
to automate it — DRC-4596 in this milestone is the guardrail that would make size assertable in CI,
and it lands after this change by design.

## Expected surface, with tolerance

Costed on the post-DRC-4587 tree. Runtime and oracles are separate, because the oracle cost is fixed
by touching `web/` at all and does not scale with the change.

| surface | files | net LOC | tolerance |
|---|---|---|---|
| runtime | `next-cockpit.js`, `styles.css` | 30-40 | +/- 15 |
| docs | `docs/design-next-ui.md` | ~10 | +/- 6 |
| tests | `tests/test_next_cockpit.py` | 90-140 | +/- 50 |
| **oracles** | `test_next_page.py`, `test_next_flag.py`, `test_focus.py` | 9 figures | exact |

**The nine pinned figures**, all currently at their post-DRC-4587 values, all recomputed from the
assets and never resolved textually:

- `test_next_page.py:683/684` — `next-cockpit.js` size `198_105` and its digest
- `test_next_page.py:703/705` — `styles.css` size `111_050` and its digest
- `test_next_page.py:710/712` — assembled `914_344` and digest `2165bf68...`
- `test_next_flag.py:67/69` — the same assembled length and digest, held separately
- `test_focus.py:1024` — the same assembled digest, a third time

**Semantics that may move.** The rendered size and ink of four selectors in the briefing; five
absence strings; one suppression branch. No data, no collector, no store, no published session field.

**Required checks that compel work beyond the estimate.** `docs/design-next-ui.md` is cited with
heading anchors by four runtime files, which puts it on the effective docs deny list — so this is a
`code=true` change and all five measurable quality-gate jobs run; and renaming any heading in it turns
`test_documentation.py` red. No import-graph allowlist, protocol fake or new test module is compelled:
every new test lands in `test_next_cockpit.py` beside its siblings. The estimate's known weak point is
the test column — DRC-4037 came in at 9 files and +541 against 6 declared — so the tolerance there is
deliberately the widest of the four.

## Approach chosen, and the simplest rejected alternative

**Chosen:** re-tier the four selectors and rewrite five strings, consuming DRC-4589's registers.

**Rejected — brighten the captain line and leave the chip alone.** It is one declaration and no
restructuring. It cannot deliver the value: the milestone's own audit establishes that `--ink` is
already the brightest token in the palette and still falls below the body-text requirement at 12.5px,
so there is no colour left to spend. The captain line can only win by taking size, which means the
chip has to give size up, which is the restructure.

**Also rejected — keep the collapse and repair its mechanism.** Measured at 171px before and 171px
after; see the history section. Repairing a mechanism whose measured payoff is zero is the scope
widening the stage definition warns against.

## Stage Report: triage

- DONE: Capture the live Linear issue body and the owning milestone description verbatim under `## Linear edits made` as the pre-edit record before drafting anything, and draft the rewrite of each beside it without writing either to Linear.
  Both captured verbatim in fenced blocks under `## Linear edits made`; the rewrite and the milestone correction sit beside them. No Linear write was made — `get_issue`/`get_milestone` only.
- DONE: Write the acceptance criteria into `## Acceptance criteria` as bullets shaped `- **AC-N — offline:** {property}. **Verified by:** {…}. **Falsified by:** {…}`
  (the checklist's own example id is elided above: the scanner reads this report for citations, so quoting the template literally makes the first criterion scan as evidenced at a gate where every criterion should still be unevidenced)
  Six hyphenated bullets, each bold label closing on the line it opens; `status --read drc-4593 --ac-scan` resolves all six (run after this report was written, since the scanner requires the stage report to exist).
- DONE: Declare the expected surface with tolerance, costing the byte-pin oracles separately from the runtime, and measure every figure against the POST-DRC-4587 tree on branch `spacedock-ensign/drc-4587`, not against main.
  Four-row surface table with per-row tolerance, oracles costed separately as nine fixed figures. Every figure re-read from the 4587 worktree at 3cc7ef49: assembled `914_344`/`2165bf68…`, styles.css `111_050`, next-cockpit.js `198_105`. Four stale pixel figures corrected by a live drive (y≈547 → 666; ~300×150 → 334×280).
- SKIPPED: Repair the collapse mechanism, which the recon showed cannot fire as specified.
  Not repaired — measured away. All-absent briefing is 171px under today's grid and 171px under `auto-fit,minmax(210px,max-content)`: grid rows already size to content, so the mechanism's measured payoff is zero and repairing it would be scope the stage definition warns against. The "None recorded" half was noted as instructed and is not adopted — the rewrite uses a two-verb rule that introduces no new string. Dropping the criterion is put to the gate; it is a scope reduction, not an ensign decision.

### Summary

The issue is still real and post-DRC-4587 it is worse than filed: the type-scale change lifted `FO INSPECTING` to 15px/`--ink` against a 12.5px/`--ink3` captain line, so the brightest string is now also the largest, and it introduced a second inversion where an absent cell's caption (15px) outsizes the value it explains (12.5px). Two of the original six acceptance criteria did not survive contact — the collapse (measured at 171px before and after, so the named mechanism buys nothing) and the "None recorded" convention (absent from the repository), both demoted to a dated history section rather than deleted. Measured against the stage's own "shorter than what it replaced" test: the rewrite's current half is 698 words against the captured original's 794, 12% shorter; counting the required history section it runs to 978, which is the history doing its job rather than the rewrite growing. Three findings were proved by execution rather than by reading: `test_next_cockpit.py:735` runs with `task.known === false` and so must be re-pointed rather than extended; the whole briefing carries exactly one `.next-project-value--absent` node, which is what refutes the collapse detection; and the four heights above were read off a live board, not predicted.

## Stage Report: implementation

Built with DRC-4589 on one branch, `spacedock-ensign/drc-4589`, candidate SHA `b9642e3`. The full
checklist evidence is in `drc-4589/index.md`; this report covers what is specific to this issue.

- DONE: Write every gate-approved draft for THIS group's issues to Linear as the FIRST action before any code — each issue body, any milestone correction, and any journey or move label named at triage — sending bodies unwrapped as one line per paragraph, then read back each relation set and report the edges created.
  Body written unwrapped before the first code edit (`updatedAt` 2026-09-17T12:51:44Z), and the milestone's "How this was measured" paragraph replaced with the stale-figures warning. Labels already correct, so nothing was written. Relation read-back: blockedBy DRC-4589 unchanged, blocks still empty, and **one new edge, `relatedTo DRC-4587`**, created by the six DRC-4587 mentions in the problem and history sections.
- DONE: Write the failing test first for each issue and watch it fail for the right reason, then regenerate every byte pin your changes move from the assets and re-run test_next_page, test_next_flag and test_focus each ALONE, reporting each pass ratio.
  Same deviation as the sibling report: implementation first, red proved by reverting the runtime. Against the pre-change tree the gloss was absent from the header, `Assignment evidence not published` rendered with `task.known === false`, `not captured` was present, and `.next-cockpit-authority>small` had no rule at all. Six mutations specific to this issue were killed: chip back on the sentence tier, caption ink collapsed onto the value, AC-6 suppression removed, `captured` wording restored, gloss removed, and one label rule reverted. Pins shared with the sibling; alone: `test_next_page` 35/35, `test_next_flag` 7/7, `test_focus` 96/96.
- DONE: Before finishing, resolve BOTH branches of every value-and-absence ternary you touch and confirm no absence you raise renders larger than the value it replaces; a test asserting an absence alone is not evidence, it must compare against its paired value.
  This issue raises nothing. The briefing's absent value and its caption are both 15px already; the change is the caption's ink moving to `--ink-caption` and the caption no longer rendering at all beside an unobserved task. `TheBriefingsThreeRegistersStayApartTest` resolves label, value and caption through the cascade and then through the registers to their hexes, and asserts caption <= value rather than asserting the caption alone. It resolves the LAST declaration per head, not the first: four of these selectors are declared twice and reading the first reports the pre-DRC-4587 sizes, which would call the inversion fixed while it was still on screen.
- DONE: Run the canonical pre-PR suite from AGENTS.md "Pre-PR Checks" read from that file, invoke sync-docs and commit its updates, then report the actual surface against each issue's declared estimate.
  Whole suite green, figures in the sibling report. This issue's share of the surface: runtime about 27 net across `next-cockpit.js` and `styles.css` (declared 30-40, ±15 → 15-55: in range). Docs 42 net across two files against ~10 ±6 declared: **over**, and honestly so — 10 of it is the sentence-tier amendment this issue owes, and 32 is sync-docs recording DRC-4589's register ruling in the stylesheet contract, which no estimate costed. Tests are counted once in the sibling report and are 3.3x their combined declared bound.
- DONE: Commit DCO signed off on your branch and STOP without pushing and without opening a pull request, reporting the branch and candidate SHA.
  Branch `spacedock-ensign/drc-4589`, candidate SHA `b9642e3`. Not pushed, no PR opened. One PR will carry `Implements DRC-4589` and `Implements DRC-4593`, and the Linear reconcile runs once per issue.

### Summary

The emphasis is reallocated exactly as drafted and nothing was invented about agent behaviour: the
state names survive verbatim, the chip is 11px `#9b9484` mono and the captain line 15px `#f4f1e8`
sans 600, both read off a live board rather than predicted. The gloss sits in the briefing header.
The FO attention row is untouched, and a fixture drives `discovery.state === "error"` to prove it
still renders. "captured" is gone from the briefing on a two-verb rule that introduces no phrase the
tree did not already use, and four pre-existing assertions that pinned the old wording were
re-pointed, including one `assertNotIn` that would otherwise have passed against any board at all.

The one thing the gate should decide rather than accept. **AC-4 asks for three distinct (size, ink)
pairs in an absent cell, and the tree moved underneath it.** A commit already on this base raised
`.next-cockpit-recovery strong` to 15px, so the absent value and its caption are now the same size
and the same ink, and no size or ink move can separate them without either lowering a caption the
stylesheet explicitly refuses to lower or brightening an absence the captain ruled must stay
`--ink3`. What separates them instead is AC-6: with the caption suppressed when the task is unknown,
the only cell that can still render one has a known value at `--ink-value`, so the three pairs are
(11.5, ink3), (15, ink), (15, ink3). The criterion is met, but by closing a route rather than by
re-tiering anything, and that reading is this stage's and should be confirmed.

## Ruling — how AC-4 is met, 2026-09-17

Confirmed by the first officer at the implementation stage, against the reading this stage put to
the gate rather than assumed. Recorded here so a reviewer reads it beside the criterion instead of
re-deriving it from the cascade and concluding the criterion was missed.

**AC-4 is met by AC-6's suppression, not by any size or ink moving.** As filed, AC-4 asks for three
distinct (size, ink) pairs in an absent ASSIGNMENT cell and cites today's figures as label
11.5px/`--ink3`, value 12.5px/`--ink3`, caption 15px/`--ink3`. Those figures are stale: a commit
already on this branch's base, `4fb5ee6d`, raised `.next-cockpit-recovery strong` to 15px, which
fixed the inversion AC-4 names and collapsed the value and its caption onto the same size **and**
the same ink.

Neither of the two ways to separate them directly is available. Lowering the caption back to 12.5px
is refused in the stylesheet's own words at `.next-cockpit-recovery strong` -- it reinstates the
sub-floor sentence DRC-4587 existed to remove. Brightening the absence is refused by the captain's
ruling of 2026-09-17, which is settled and not reopenable: absence keeps `--ink3`, and DRC-4597's
AC4 stands verbatim.

What separates them is that the collapsed pairing can no longer render. AC-6 suppresses
`Assignment evidence not published` when `briefing.task.known` is false, so the only cell that still
carries a caption has a value the board did observe, at `--ink-value`. The three pairs are therefore
(11.5, `--ink3`), (15, `--ink`), (15, `--ink3`) -- distinct, with caption equal to and never larger
than the value it explains. `TheBriefingsThreeRegistersStayApartTest` asserts exactly that, resolving
each selector's LAST declaration through the cascade and then through the registers to a hex, because
four of these selectors are declared twice and reading the first reports the pre-DRC-4587 sizes.

## Stage Report: review

Reviewed `spacedock-ensign/ui-integration` at **2fa5a2f4** (PR #364), read-only. Nothing on the
branch was edited. Shared-checklist evidence — the byte pins, the capability-read scrutiny and the
two refutations — is in `drc-4589/index.md`; this report covers DRC-4593's own share.

- DONE: State the chosen review depth and the diff property that justified it BEFORE reviewing, per AGENTS.md "Calibrating Effort".
  **Two lenses plus an arbiter**, stated before the first check. This issue's own surface is
  `next-cockpit.js` and `styles.css` — both conflict-prone, both byte-pinned — which is the table's
  two-lenses row. Full adversarial is not bought: nothing here touches credentials, a store, or a
  published session field.
- DONE: Reproduce every acceptance criterion of every issue in your group from its own Verified by clause, against 2fa5a2f4.
  AC-1, AC-3, AC-4, AC-5, AC-6 reproduced offline from their clauses. AC-2 settled by live drive
  below. AC-5's universal half reproduced directly: `grep -c captured` over all twenty bundle parts
  returns **0**, and "None recorded" appears nowhere in the tree. AC-6 reproduced from the source —
  `briefing.task.known && briefing.task.provenance ? … : briefing.task.known ? "Assignment evidence
  not published" : ""`, so the false arm cannot render it.
- DONE: RUN THE FALSIFIER, NOT JUST THE VERIFIER. For each criterion, execute its Falsified by condition and show it reds.
  AC-1 (substitute prose for `FO INSPECTING`) reds `TheBriefingSaysWhoIsWaitingBeforeItNamesItself
  Test` 2/2; dropping the gloss reds the module. AC-3 (demote the attention row label) reds it.
  AC-5 reds on both "captured" restorations. AC-6 (remove the suppression) reds 2 tests. AC-4 reds on
  caption-ink-onto-value and on caption-regains-the-larger-size; **its third falsifier survives** —
  see F3. AC-2's offline proxy (chip back on the sentence tier) reds. Each mutation was applied
  alone and reverted; `test_next_cockpit` carries zero byte pins, confirmed by grep before use.
- DONE: For every criterion, report which of three it is.
  AC-1 and AC-6: enumerated wording, enumerated verifier — honest, and both name their arms. **AC-3,
  AC-4 and AC-5 are universal wording with an enumerated verifier.** AC-3 says "no briefing string
  asserts agent behaviour" and checks a verb list. AC-5 says "captured" no longer appears "in the
  briefing" and asserts `assertNotIn` over one rendered fixture — though the universal grep over the
  bundle independently holds. AC-4 is the one with a live consequence, in F3.
- DONE: Resolve rendered properties through tests/css_cascade.py down real element paths.
  `TheBriefingsThreeRegistersStayApartTest` reads rules by **exact selector-head string**, which
  assumes the head it names is the cascade winner — the same assumption that produced this
  milestone's scope-title defect. I re-resolved the cell down a real path
  (`.next-cockpit-content` › `.next-cockpit-recovery` › `div[data-next-cockpit-task…]` › span/strong/
  small) with my own colour resolver over `css_cascade.matches()`. **It agrees**: on the task-known
  arm, label (11.5, `--ink-label`), value (12.5, `--ink-value`), caption (12.5, `--ink-caption`) —
  three distinct pairs, caption never larger. On the unknown arm value and caption do collapse onto
  (12.5, ink3), and AC-6's suppression is what stops that pair co-rendering, exactly as the ruling
  says. The ruling is confirmed by resolution, not accepted from the report.
- DONE: Exclude the byte-pin oracles from every mutation check you run.
  Confirmed `test_next_cockpit` contains none of the five pinned figures before using it as the
  oracle for all nine mutations above.
- DONE: Re-derive every byte pin from the assets rather than from any list.
  All 22 recomputed and all agree; figures and method in `drc-4589/index.md`. Nothing disagrees.
- DONE: Scrutinise the integrator's own self-caught regression and its fix; look for a second instance of the same shape.
  Covered in `drc-4589/index.md`. The fix holds; a second instance exists, is reproduced, and is
  outside both issues in this group.
- DONE: Check the two refutations the integrator made rather than accepting them.
  Both hold, by execution. Detail in `drc-4589/index.md`.
- DONE: Write a `## Stage Report: review` into EVERY entity file in your group, and give a GO or NO-GO without editing the branch.
  This report and DRC-4589's. Branch untouched.

### AC-2, settled by live drive

Not attempted against the board on :4553 — it serves a different tree (892,793 bytes against this
one's 958,263), so driving it would have proved nothing. Started a server from the reviewed worktree
and verified it byte-for-byte first (958,263 / `38818e11…` once the runtime-injected focus meta is
stripped). `getComputedStyle` in the COMMAND cell of a real project:

| string | size | weight | ink | family |
|---|---|---|---|---|
| `FO INSPECTING` (chip) | 11px | 700 | `#9b9484` | Space Mono |
| `Captain state unknown` | **15px** | 600 | **`#f4f1e8`** | Space Grotesk |
| attention `<strong>` | 12.5px | 500 | `#f4f1e8` | Space Grotesk |

The captain line is the largest and is at the brightest ink; the chip is neither the largest nor the
brightest, so AC-2's falsifier — "the chip still outranks the captain line on either size or ink" —
does not fire. The gloss renders beside the briefing heading, which settles AC-1's second half live
as well as offline. Capture in `docs/screenshots/`.

### Findings

- **F3 · Polish · this issue's own criterion.** AC-4's wording asks for "three distinct **registers**";
  its verifier asserts three distinct **(size, ink) pairs**. These are different properties. Executed:
  moving `.next-cockpit-recovery span`'s colour from `--ink-label` onto `--ink-caption` — collapsing
  the label and caption roles onto one register, which is the precise defect DRC-4589 exists to
  remove — **survives all 319 tests in `test_next_cockpit`**, because the sizes still differ so three
  pairs remain. No user-visible loss today (the tree has the label on `--ink-label`), so this is
  Polish and I am not promoting it into this PR. Its promote-to-material condition: any future change
  that equalises two of the three sizes, after which the pair oracle stops separating the roles too.
- **F4 · Polish.** The same test is selector-head-keyed rather than cascade-resolved. It is correct
  today — I checked by resolving the real path — but it is the same shape as the defect this
  milestone already paid for once, and it will not see a later rule that outranks the head it names.

### Summary

GO for DRC-4593. All six criteria hold: five reproduced offline with their falsifiers red, and AC-2
settled on a live board I first proved was serving this exact tree rather than on the one already
running, which was not. The emphasis really has moved — the chip is 11px dim mono against a 15px
bright sans captain line — and "captured" is gone from all twenty bundle parts, not just from the
fixture the test renders.

One thing the gate should decide rather than take from me: AC-4 is met, but its verifier measures
(size, ink) pairs where its wording says registers, and I have an executed mutation that collapses
two roles onto one register while the test stays green. That is worth a follow-up issue, not a fix
here — promoting it buys an implement-and-CI round for something already judged not to block.

**Verdict: GO.** Twelve checks green on 2fa5a2f4, `mergeStateStatus` CLEAN, both Copilot inline
threads read and independently re-refuted, zero unresolved threads.

### Addendum, 2026-09-18 — F3 re-verified under the mutation no-op rule

The integrator asked that no SURVIVED be trusted until the substitution is proved to have applied,
after one of its own falsifiers "survived" because a `perl` substitution had silently not matched.
F3 is the only finding in this group that rests on a survival, so it was re-run with the mutation
proved rather than assumed:

| check | before | mutated | after the run |
|---|---|---|---|
| occurrences of `color:var(--ink-label)` in that rule | 1 | **0** | 0 |
| occurrences of `color:var(--ink-caption)` in that rule | 0 | **1** | 1 |
| resolved ink of the label span, down a real element path | `var(--ink-label)` | **`var(--ink-caption)`** | — |

The file was still mutated when the run finished, so nothing regenerated it. The third row is the one
a grep alone would not give: the mutation did not merely land in the text, it **moved the rendered
property** — label and caption resolve to one register, which is the defect DRC-4589 exists to
remove — and all 319 tests in `test_next_cockpit` still passed. F3 stands as written: AC-4's verifier
measures (size, ink) pairs, the sizes still differ, so the pair oracle cannot see a register collapse.

Every other mutation in this review reported RED, and a RED against a green baseline cannot be a
no-op, so the rule changes nothing else here. The `nextCockpitContexts` audit the same message asked
for is in `drc-4589/index.md`; its result does not touch either of this issue's criteria.

**Verdict unchanged: GO.**

### Disposition correction, 2026-09-18 — F3 is in scope and goes into the fix commit

My report classified F3 as Polish and declined to promote it. **The first officer overruled that, and
the ruling is right.** Three non-falsifying falsifiers from DRC-4592's reviewer had already been
ruled in scope on the grounds that a criterion's own verifier failing to verify is in scope by
definition. F3 is the same class, and one group does not get a softer rule than another.

What settled it is the strength of the proof rather than the finding's size: the mutation was shown
to reach the thing under test — occurrences 1→0 and 0→1, and the **resolved ink moving
`var(--ink-label)` → `var(--ink-caption)` down a real element path** — with 319 tests still green.
That is a demonstrated miss, not a possible one, so "no user-visible loss today" was the wrong test
to apply to it.

Recorded here rather than by editing the finding above, so the reasoning that produced the wrong
disposition stays readable. The verdict is unchanged: **GO**.
