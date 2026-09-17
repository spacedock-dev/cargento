---
id:
title: "Raise board sentences to a 15px tier and collapse six sub-12px tokens into one label tier"
status: implementation
source: "https://linear.app/recce/issue/DRC-4587/raise-board-sentences-to-a-15px-tier-and-collapse-six-sub-12px-tokens"
started: 2026-09-17T06:57:18Z
completed: ""
verdict: ""
score: 0.6
worktree: .worktrees/spacedock-ensign-drc-4587
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
        - id: gate:drc-4587:triage
          stage: triage
          attempts:
            - id: gate-attempt:drc-4587-triage-1
              briefing:
                id: briefing:drc-4587:triage:attempt-1:revision-1
                digest: sha256:362f9c821d8668a774b54631467fcd63ed739fddb1b71595d411e77a591c5784
                room-ref: ./review/triage/briefing-1
              resolution:
                type: Resolution
                id: resolution:spacedock:drc-4587:triage:1
                briefing: briefing:drc-4587:triage:attempt-1:revision-1
                by: agent:first-officer
                at: "2026-09-17T07:13:24.114614Z"
                decision: approve
                reason: 'Checklist 3 done / 0 skipped / 0 failed; AC-1..AC-7 resolve and each names the value its command returns today, so each can fail in both directions. Triage narrowed scope rather than widening it: a second structural move AC-2 always required, a refuted recon collision at styles.css:940, and a third dead token. Surface declared at runtime ~105 lines over 2 files plus 9 pinned oracle figures at zero tolerance. Nothing written to Linear yet; this authorizes that write.'
                conn:
                    quote: I pre-approve all the triage and merge gates, just automate this entire process and do it
                    source: Captain, this session, in answer to the gate-authority question on 2026-09-17
              application:
                target-stage: implementation
                state: consumed
---

[DRC-4587](https://linear.app/recce/issue/DRC-4587/raise-board-sentences-to-a-15px-tier-and-collapse-six-sub-12px-tokens) — Raise board sentences to a 15px tier and collapse six sub-12px tokens into one label tier

Seeded 2026-09-17 from the live Linear read of the Clean and Cogent UI/UX milestone.
Linear owns the current issue body, its relations and its resources; triage fetches them
live and validates them against the tree before anything is built. No triage, approval,
implementation or delivery is claimed here.

---

## Triage: DRC-4587 (2026-09-17)

Adversarial read against `main` @`6702fb5c`. Every figure below was re-checked against the
tree by this stage; the independent recon's figures all reproduced, and two claims of its own
did not survive (noted inline). Nothing has been written to Linear.

### User value brief

Anyone reading the board sees this on every screen all day: the prose is set below the size at
which any ink in the palette can carry it, so the board reads dim however bright the colour.
Raising the sentence tier is the only lever left, because the contrast half of the complaint
measurably already passes.

Promise [P2 — what is it doing, and when should I come back](../promise-map.md#how-work-links-to-a-promise),
move `sharpen`. The board already answers the question; this makes the answer legible.

### Labels to set

`move:sharpen` and `journey:mid-flight` are already on the issue. No label change is needed;
`implementation` sets nothing new.

### Linear edits made

Nothing written yet. This gate authorizes the write.

#### Captured original — issue body (verbatim, pre-edit, read 2026-09-17)

```markdown
## User value

Anyone reading the board notices this on every screen, all day. Today the prose is set below the size at which any colour in the palette can carry it, so the board reads as dim no matter how bright the ink.

## The Problem

Readers say the text is dim and hard to make out. The colour half of that is measurably false and there is nowhere to go with it: on `--panel`, ink is 15.15:1, ink2 9.81:1 and ink3 5.67:1, all above the 4.5:1 AA bar the asset test pins. The size-aware measurement locates the real failure. At 12.5px/400 on `--bg`, ink3 scores APCA Lc 44.1, ink2 Lc 70.2 and ink — the brightest colour in the system — Lc 98.0, all against a body-text requirement of 100. Even a maximally bright body misses. The 9.5px and 10px label steps at weight 400 fall below the APCA lookup table entirely, so no colour choice makes them meet a body-text criterion at all. Six scale tokens sit at or below 12px inside a 3px band (9, 9.5, 10, 10.5, 11, 12), and two of them have zero callers. Two sentence-case prose strings on Held to already breach the project's own documented 12.5px floor, at 10px.

**Measured**

* APCA on `--bg`, reverse polarity, 12.5px/400: ink3 Lc 44.1, ink2 Lc 70.2, ink Lc 98.0 — all against a requirement of 100
* 9.5px and 10px at weight 400 are below the APCA lookup table entirely
* WCAG AA passes everywhere on `--panel`: ink 15.15:1, ink2 9.81:1, ink3 5.67:1 — this is not a contrast-ratio defect
* Space Grotesk unitsPerEm 1000, sxHeight 486 (fontTools): 12.5px yields a 6.08px x-height; 15px yields 7.29px, +20%
* Six tokens at or below 12px: `--fs-column` 9, `--fs-label` 9.5, `--fs-meta` 10, `--fs-meta-detail` 10.5, `--fs-machine` 11, `--fs-breadcrumb` 12
* `--fs-column` and `--fs-meta` have zero callers anywhere under `cargento_runtime/web` (verified: 0 `var()` references each)
* Two confirmed floor violations on Held to, both 10px/400: "No revision saved yet" (styles.css:858) and "two axes, read separately" (styles.css:955)
* styles.css:20 justifies the 9px token with "see ruling R9"; no R9 exists under `docs/`
* `var(--fs-xs)` has exactly 148 call sites, several of them chrome rather than prose

**In the attached screenshot**

1. Body prose 12.5px: brightest ink Lc 98 vs 100 required
2. "No revision saved yet" at 10px, below the APCA table
3. "two axes, read separately" 10px in a label slot
4. Headings 10px/700 vs body 12.5px: 2.5px of rank

## The Solution

Add `--fs-sentence:15px` to `:root` and repoint the prose selectors to it, rather than raising `--fs-xs` (148 sites, several of them chrome: `.next-status-dot`, `.next-header-right`, the primary nav, the held-field buttons, the `.next-cockpit-content` base font, and a monospace goal block where a 20% rise in a 0.612-em face is a much larger width change). Set board sentences to weight 500 and line-height 1.55.

Fix the two floor violations structurally, not by bumping them in place: `.next-cockpit-held-revision` is an absence explanation, so move it out of the `<header>` onto its own line at the sentence tier in sans, keeping its polymorphic slot (discard stamp / revision line / "No revision saved yet").

Collapse the label tier: delete `--fs-column` and `--fs-meta` (zero callers), set `--fs-label:11px`, remap the 27 literal `font-size:10px` sites plus 4 in `font:` shorthands onto it, and replace four tracking values (.13em ×9, .14em ×7, .1em ×3, .08em ×8) with one .09em on the uppercase tier. Delete the "ruling R9" comment along with the token it defends.

Cap the prose measure: `--measure:540px` (72 characters at 15px, against ~155 today) on the sentence-bearing selectors only, never on published machine strings that carry `overflow-wrap:anywhere`.

Recompute the two assembled-length and three digest assertions across `tests/test_next_page.py`, `tests/test_next_flag.py` and `tests/test_focus.py` from the assets — see AGENTS.md, Parallel Work, on frontend byte pins.

## Acceptance

- [ ] No rule under `cargento_runtime/web` renders sentence-case prose below 15px, and no token in `:root` is below 11px
- [ ] "No revision saved yet" and "two axes, read separately" both render at the sentence tier in sans; neither is reclassified as a label to exempt it
- [ ] `--fs-column` and `--fs-meta` are gone from `:root` and from every call site; no literal `font-size:10px` remains in a `.next-cockpit-*` or `.next-session-*` rule
- [ ] The "see ruling R9" comment is deleted rather than repointed at an invented heading
- [ ] Prose lines cap at 540px; `.next-cockpit-work-summary`, `.next-cockpit-reading-clause` and `.next-session-departure-base` keep the full column
- [ ] The two assembled-length and three digest assertions are recomputed from the assets, not patched textually

---

Complaint **C1** · tabs: all · severity **blocker** · effort **L** · depends on nothing

Raised from user feedback; mechanism and figures established by a measured audit of the live board and the shipped stylesheet. Contrast computed from the tokens, APCA at the sizes they render at, density and control counts read off the live DOM. Density figures are floors — taken on a quiet, unannotated session.
```

#### Captured original — milestone description (verbatim, pre-edit, read 2026-09-17)

Milestone `Clean and Cogent UI/UX` (`5e3b8b68-f7d7-429c-b4c8-682cd86f8b2b`), project
`Cargento: Visibility 2x2 Roadmap`.

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

Contrast computed from the shipped tokens; APCA from the same pairs at the sizes they render at; density, ink distribution and control counts read off the live DOM at `127.0.0.1:4553`. Density figures are floors — they were taken on a quiet, unannotated session, and a busy project has more text, not less.

Eleven claims were raised and rejected rather than filed. The two worth knowing: brightening the inks cannot fix C1, and merging the three thin tabs is a route change plus an amendment to NUI-3, not a layout change.
```

#### Drafted rewrite — issue body

```markdown
## User value

Anyone reading the board sees this on every screen all day. The prose is set below the size at
which any ink in the palette can carry it, so the board reads dim however bright the colour.
Raising the sentence tier is the only lever left: the contrast half of the complaint already
passes.

Promise **P2**, move **sharpen**.

## The problem

Two registers, one wrong size each.

**Sentences.** Board prose renders at `--fs-xs` 12.5px (`styles.css:1070`). The audit puts even
the brightest ink at APCA Lc 98 there against a body requirement of 100, so no colour choice
fixes it. WCAG is not the defect: on `--panel`, ink is 15.15:1, ink2 9.81:1, ink3 5.67:1 — all
above the 4.5:1 the asset test pins at `tests/test_next_page.py:442`, all recomputed from the
tokens and matching to the decimal.

**Labels.** Six scale tokens sit at or below 12px inside a 3px band (`styles.css:21-22`):
`--fs-column` 9, `--fs-label` 9.5, `--fs-meta` 10, `--fs-meta-detail` 10.5, `--fs-machine` 11,
`--fs-breadcrumb` 12. **Three of the six are dead** — `--fs-column`, `--fs-meta` and
`--fs-breadcrumb` each have zero `var()` callers anywhere under `cargento_runtime/web`. Thirty-one
rules carry a literal 10px (27 `font-size:10px`, 4 inside `font:` shorthands), and four tracking
values (.13em ×9, .14em ×7, .1em ×3, .08em ×8) spread one uppercase register across four settings.

**Two strings breach a written ruling.** `docs/design-next-ui.md:112-115` already rules that
absence explanations are sentences and lose to the sentence floor. "No revision saved yet"
(`styles.css:858`) and "two axes, read separately" (`styles.css:955`) both render at 10px mono.
Both also sit inside a `<header>` beside an `<h2>` — `next-cockpit.js:2412` and `:2154` — so
neither can reach the sentence tier without moving.

`styles.css:20` defends the 9px token with "see ruling R9". No typography R9 exists under `docs/`.

## The solution

**The register is the classifier.** Sans is the board talking; mono is a string a source
published. That rule is already written at `styles.css:940` and in `docs/design-next-ui.md`. It
decides which selectors move, and the resulting inventory is recorded in `design-next-ui.md` so a
reviewer argues with a list instead of re-deriving one.

1. Add `--fs-sentence:15px` to `:root` and repoint the **sans** prose selectors to it at weight
   500 / line-height 1.55. Do not raise `--fs-xs`: its 148 call sites include chrome
   (`.next-status-dot` :45, `.next-header-right` :59, the primary nav :60, the held-field buttons
   :865) and three mono blocks (:884, :934, :1092) where Space Mono is declared at discrete
   weights only, so 500 would synthesize.
2. Move `.next-cockpit-held-revision` (`next-cockpit.js:2412`) and `.next-cockpit-landed-axes`
   (`:2154`) out of their `<header>`s onto their own lines at the sentence tier in sans, each
   keeping its polymorphic slot.
3. Collapse the label tier: delete `--fs-column`, `--fs-meta` and `--fs-breadcrumb`; set
   `--fs-label:11px`; remap all 31 literal-10px sites onto it; replace the .13em and .14em groups
   with one .09em, reading the .1em and .08em groups individually first — not every one of them is
   on the uppercase tier. Delete the "ruling R9" comment with the token it defends.
4. Cap the measure at `--measure:540px` on sans prose only, never on a rule carrying
   `overflow-wrap:anywhere`.
5. Recompute **nine** frontend byte pins from the assets in one pass — see Acceptance 6.
6. Update the three places that assert the old floor: `docs/design-next-ui.md:55` and `:112`, and
   `CONTRIBUTING.md:264`. Prose only — `design-next-ui.md` carries runtime heading-anchor
   citations, so renaming a heading there turns `test_documentation` red.

## Acceptance criteria

Each criterion is an end-state property with its own falsifier. Six are offline; one is
interactive and is the only check that the tier actually reads better.

- **AC-1 — offline:** every sans text-bearing rule under `cargento_runtime/web` resolves to 15px
  or larger, and no `--fs-*` token in `:root` is below 11px. **Verified by:** the sentence-tier
  inventory in `docs/design-next-ui.md` — every selector on it resolves to `var(--fs-sentence)` by
  grep — plus `grep -oE '\-\-fs-[a-z-]+:[0-9.]+px' styles.css` showing a minimum of 11 (it shows 9
  today). **Falsified by:** any inventory selector still on `var(--fs-xs)`, or `--fs-label` left at
  9.5px; the grep names the offender.
- **AC-2 — offline:** "No revision saved yet" and "two axes, read separately" each render in sans
  at `var(--fs-sentence)`, and neither span is a child of a `<header>`. **Verified by:**
  `grep -n 'next-cockpit-held-revision\|next-cockpit-landed-axes' styles.css` showing `var(--sans)`
  and `var(--fs-sentence)` on both, and the same classes emitted after `</header>` in
  `next-cockpit.js`. **Falsified by:** bumping the literal to 15px while leaving
  `font-family:var(--mono)`, or leaving either span inside its header; `test_next_cockpit.py:4694`
  matches the revision line by class rather than position, so the move alone keeps it green.
- **AC-3 — offline:** `--fs-column`, `--fs-meta` and `--fs-breadcrumb` are gone from `:root`,
  `--fs-label` is 11px, and no literal 10px font size remains anywhere under `web/`.
  **Verified by:** zero hits for each token name, `grep -c 'font-size:10px'` = 0 (27 today) and
  `grep -cE 'font:[^;]*10px'` = 0 (4 today). **Falsified by:** deleting a token that still has a
  caller — `test_every_css_variable_the_canonical_page_uses_is_declared` turns red naming it.
- **AC-4 — offline:** no "ruling R9" reference remains under `cargento_runtime/` or `docs/`.
  **Verified by:** `grep -rn 'ruling R9'` over both returning nothing (it returns styles.css:20
  today), with `RuntimeDecisionCitationsTest` green. **Falsified by:** repointing it at an invented
  heading — the citation checker resolves each target and requires the exact fragment.
- **AC-5 — offline:** `--measure:540px` is declared and applied only to sans prose, and
  `.next-cockpit-work-summary`, `.next-cockpit-reading-clause` and `.next-session-departure-base`
  carry no cap. **Verified by:** `grep -n 'max-width:var(--measure)' styles.css` listing only sans
  selectors and none of the three named (it lists none today). **Falsified by:** the cap landing on
  a rule that also carries `overflow-wrap:anywhere`; one grep shows both on the same line.
- **AC-6 — offline:** all nine frontend byte pins equal values regenerated from the assets in the
  same pass — `test_next_page.py` :683-684 (`next-cockpit.js` size and digest), :703/:705
  (stylesheet size and digest), :710/:712 (assembled length and digest); `test_next_flag.py`
  :67/:69; `test_focus.py` :1024. **Verified by:** the dashboard suite green, with `test_next_page`,
  `test_next_flag` and `test_focus` each re-run alone, since AGENTS.md documents concurrent suites
  manufacturing failures in exactly these modules. **Falsified by:** patching one pin and reasoning
  about the rest — the other two files stay red; a tenth pin moving means the change touched an
  asset outside the declared surface.
- **AC-7 — interactive:** on a live board at `http://127.0.0.1:4553`, board sentences compute to
  15px at weight 500, and both absence strings read in sans on their own line. **Verified by:**
  `getComputedStyle` on `.next-cockpit-content` prose and on both absence strings, plus a human
  read of whether the tier is actually easier — nothing in the repository tests that, and it is the
  claim the whole change rests on. **Falsified by:** a computed size still 12.5px because a more
  specific `var(--fs-xs)` rule wins the cascade; no grep can see that, only the live board reports
  it.

## Sequencing

One PR. AGENTS.md allows exactly one PR to touch `cargento_runtime/web/`, and all seven issues
this blocks are web/ changes. **Land this before DRC-4594**, which rewrites the same
`next-cockpit.js:2410-2412` / `styles.css:855-866` lines. **DRC-4596** edits
`tests/test_next_page.py:419-443` while this repins :683-712 in the same file; sequence it after.

## History

**2026-09-17 — superseded by triage.** The body above replaces the original filing. What changed:

* The original named **two** dead tokens. There are **three**: `--fs-breadcrumb:12px`
  (`styles.css:22`) also has zero `var()` callers. Measured, not inferred.
* The original named **five** byte-pin assertions. There are **nine**: `test_next_page.py` also
  pins the per-part stylesheet (`108_008` + digest) and `next-cockpit.js` (`198_105` + digest) in
  the same method, and this change moves both.
* The original restructured only `.next-cockpit-held-revision`. `.next-cockpit-landed-axes` sits in
  the `HOW IT LANDED` header with the same shape and needs the same move; acceptance 2 always
  required both, and the solution did not.
* The original's six acceptance criteria were rewritten. Three could not be verified as written
  ("sentence-case prose" and "reclassified as a label" name no property in the tree; "recomputed,
  not patched textually" is unobservable in a result). Each criterion now carries a falsifier and
  an offline/interactive mark.
* The APCA figures (Lc 44.1 / 70.2 / 98.0) are retained as the audit's, **unreproducible from this
  repository** — `grep -r APCA` over `cargento/` and `docs/*.md` returns zero hits. Every figure
  they rest on (sizes, weights, surfaces, palette) was confirmed, and the WCAG half recomputed to
  the decimal. DRC-4596 closes the gap, after this change rather than before it.
* The "~155 characters today" measure figure is dropped: it depends on rendered column width and
  the stylesheet declares no `--measure` token to compare against.
```

#### Drafted rewrite — milestone description

One correction. The milestone states the APCA figures as measured fact, and nothing in the
repository can reproduce them; the guardrail that would (DRC-4596) lands after the change they
justify. Everything else in the description survives triage unchanged, including the twelve-issue
count and the foundation ordering.

Replace the final paragraph of **How this was measured**'s first sentence — from "Contrast
computed from the shipped tokens" to "…at `127.0.0.1:4553`" — with:

```markdown
Contrast computed from the shipped tokens and independently recomputed during triage, matching to
the decimal. APCA from the same pairs at the sizes they render at — **audit-only: no APCA
implementation, table or fixture exists in the repository, so these figures cannot be reproduced
from the tree.** DRC-4596 adds the guardrail that would, and lands after the change the figures
justify. Density, ink distribution and control counts read off the live DOM at `127.0.0.1:4553`.
```

No other milestone edit. The `type-scale` / `ink-roles` gating in **Waits on** is still true.

### Adversarial read

**Is the problem still real?** Yes. Every checkable figure in the issue reproduced exactly against
`main` @`6702fb5c`: the six tokens at `styles.css:21-22`, `var(--fs-xs)` = 148, `font-size:10px`
= 27 and four more in `font:` shorthands, tracking .13em ×9 / .14em ×7 / .1em ×3 / .08em ×8, both
floor violations at `:858` and `:955`, the "ruling R9" comment at `:20` with no R9 under `docs/`,
and `grep -c measure styles.css` = 0.

**Is the approach still the one that fits?** Yes, and the simplest alternative is measurably
worse. Raising `--fs-xs` to 15px touches 148 sites including chrome and three mono blocks; Space
Mono is declared at discrete weights (`styles.css:5-10`), so the weight-500 half would synthesize
there, and a 20% rise in a 0.612-em face is a large width change. It would resize the chrome to
fix the prose and still not separate the two registers. Brightening the inks is refuted by the
audit's own numbers — ink is already the brightest colour in the palette.

**Does any part of the body describe a state that no longer exists?** No. Two parts describe a
state more weakly than the tree supports: `docs/design-next-ui.md:112-115` already *rules* on the
10px absence strings, so those are breaches of a written ruling rather than a proposal; and three
tokens are dead rather than two.

**Two recon claims did not survive.** (1) The recon read acceptance 3 and 5 as colliding on
`styles.css:940` — `.next-cockpit-reading-evidence,.next-session-departure-base{…font-size:10px…}`
— and concluded the selector group must be split. It does not. Exemption from the measure cap
requires no declaration, so remapping that rule's literal onto `var(--fs-label)` satisfies 3 while
adding no `max-width` satisfies 5. Both members are mono published strings and take identical
treatment; `next-session.js:475` confirms `.next-session-departure-base` carries
`baseline + window`, a composed machine string. (2) Neither the issue nor the recon noticed that
`.next-cockpit-landed-axes` is also inside a `<header>` (`next-cockpit.js:2154`), so the
restructure is two moves, not one.

**No product decision is missing.** The register classifier (sans = the board talking, mono = a
published string) is already ruled at `styles.css:940` and in `docs/design-next-ui.md`; this
change applies it rather than inventing it.

### Expected surface and tolerance

Runtime and oracles costed separately, per the stage definition.

| Surface | Files | Lines changed | Tolerance |
|---|---|---|---|
| Runtime | `styles.css`, `next-cockpit.js` | ~105 changed, net +10 to +16 | ±25% on changed lines; any **third** runtime file is a signal to stop |
| Oracles | `test_next_page.py`, `test_next_flag.py`, `test_focus.py` | exactly 9 pinned numbers | **zero** — a tenth means an undeclared asset moved |
| Docs | `docs/design-next-ui.md`, `CONTRIBUTING.md` | 3 assertion lines + ~15 for the tier inventory | ±10 lines |

Seven files total. The changed-line figure is the honest review surface: `styles.css` is written
one rule per line, so the 31 literal remaps, 16-plus tracking normalizations and ~20 prose
repoints are nearly all in place. Net added is small; changed is what a reviewer reads.

**No required check compels a new test file.** Checked: `test_every_css_variable_the_canonical_page_uses_is_declared`
asserts used-minus-declared is empty, so deleting three zero-caller tokens is safe and adding
`--fs-sentence` / `--measure` is safe whether or not every one is used;
`RuntimeDecisionCitationsTest` applies only if a new comment cites a doc heading, and the grammar
is in AGENTS.md; `scripts/lint_embedded.py` lints the frontend source in place;
`test_documentation.py` opens `design-next-ui.md` by heading anchor, so prose edits pass and
heading renames do not. Enforcement of the new floor is **DRC-4596's** deliverable, not this one's
— adding it here would widen scope into a blocked issue.

**Semantics this may move:** rendered size, weight and line width of board prose on every screen;
the DOM position of two spans. It moves no published field, no API shape and no session data.
`test_next_cockpit.py:4694` is the only test reading either span and matches by class.

### Gate asks

1. Approve the drafted issue body and the one-paragraph milestone correction for writing to Linear
   at `implementation`.
2. Confirm the sequencing: this PR lands before DRC-4594 and before DRC-4596, both of which edit
   lines this one rewrites. DRC-4594 is **not** folded in — that would widen scope.
3. Confirm that acceptance 7 stays interactive rather than being deferred. It is the only check
   that the 15px tier reads better, which is the entire premise.

## Stage Report: triage

- DONE: Capture the live Linear issue body and the owning milestone description verbatim under `## Linear edits made` as the pre-edit record, before drafting anything, and draft the rewrite of each beside it without writing either to Linear.
  Both captured from `get_issue DRC-4587` and `get_milestone` on 2026-09-17 into `## Linear edits made`, each in a fenced block, with the drafted rewrite beside it. Nothing written to Linear; the section opens by saying so.
- DONE: Repair every acceptance criterion the recon showed cannot be verified as written — criteria 1, 2 and 6 are non-mechanical, and criteria 3 and 5 collide on styles.css:940 — so each surviving criterion is an end-state property with its own `Verified by:` and `Falsified by:` clause, marked offline or interactive.
  Seven criteria, six offline and one interactive, each with both clauses. 1 now verifies against a recorded sentence-tier inventory produced by the sans/mono register rule already ruled at styles.css:940; 6 replaces "not patched textually" with nine named pin sites plus the isolated re-runs AGENTS.md requires. The 3-versus-5 collision is refuted rather than repaired: exemption from the measure cap needs no declaration, so the shared rule takes one remap and no split.
- DONE: Declare the expected surface with tolerance, costing the byte-pin oracles separately from the runtime, and name the three dead tokens the recon found against the issue's two.
  Three-row table: runtime ~105 changed lines over 2 files at ±25%; oracles exactly 9 pinned numbers over 3 files at zero tolerance; docs ~18 lines over 2 files at ±10. Three dead tokens named in the problem statement, the acceptance criteria and the dated history section, with `--fs-breadcrumb` flagged as the one the issue missed.

### Summary

Re-checked every figure in the issue against `main` @`6702fb5c` and ran each oracle I wrote into
an acceptance criterion, so the pre-change values are measured rather than asserted: `--fs-*`
minimum 9px, `font-size:10px` ×27, `font:`-shorthand 10px ×4, "ruling R9" present at
styles.css:20 with no R9 under `docs/`, `max-width:var(--measure)` ×0. Each criterion's falsifier
is the same command returning the post-change value.

Two findings changed the issue rather than confirming it. `.next-cockpit-landed-axes`
(next-cockpit.js:2154) sits inside a `<header>` exactly as `.next-cockpit-held-revision` does, so
acceptance 2 always required two structural moves while the solution described one — neither the
issue nor the recon caught it. And the recon's styles.css:940 collision does not exist: both
members of that selector group are mono published strings (next-session.js:475 composes
`baseline + window`), and exempting a rule from the measure cap requires no declaration, so no
split is needed. I also refuted the issue's two-dead-token count in favour of three.

The milestone needs one correction only — it states the APCA figures as measured fact, and nothing
in the repository can reproduce them. Drafted as a single replacement paragraph that keeps the
figures, marks them audit-only, and names DRC-4596 as the guardrail that lands after them. The
gate is asked to approve both writes, confirm this PR lands ahead of DRC-4594 and DRC-4596, and
confirm acceptance 7 stays interactive — it is the only check that the 15px tier actually reads
better.

### Repair: machine-readable acceptance criteria (2026-09-17)

`spacedock status --read drc-4587 --ac-scan --json --workflow-dir docs/roadmap-burndown` now
returns `{"command":"read","stage":"triage","acs":[...]}` listing AC-1 through AC-7 at lines 229,
235, 242, 247, 251, 256 and 264, each `unevidenced: true`. That flag is expected at this gate —
README.md:245-248 says citations resolve from later stage reports, so criteria authored at
`triage` scan unevidenced by design.

The heading rename alone was necessary but not sufficient, and the intermediate states are worth
recording because each is a distinct failure mode:

- `## Acceptance` → `Error: no ## Acceptance criteria section in this file` (the loud failure).
- `## Acceptance criteria` over numbered `1. **(offline)**` items → `{"acs":[]}`. No error, no
  criteria. README.md:236-239 names this as "the quieter half of the same failure" and it is what
  the entity would have carried to the gate had I stopped at the rename.
- `## Acceptance criteria` over `**AC-N — …**` paragraph items whose bold label wrapped across two
  lines → one criterion found, AC-4, the only one short enough to close its bold on one line. A
  partial scan is the most misleading of the three.
- The shape README.md:241-243 specifies — a bullet list, `- **AC-N — offline:** {property}.
  **Verified by:** … **Falsified by:** …` — resolves all seven.

Reformatting the seven items went beyond the literal instruction to rename the heading only. I did
it because step 3's stated success condition ("lists your seven criteria") cannot be met by the
rename, and because README.md:236-243 specifies the item shape as part of the same contract rather
than as a style preference. No criterion's property, `Verified by:` or `Falsified by:` text
changed in substance; AC-1, AC-4 and AC-5 additionally now name the pre-change value each command
returns today (9, `styles.css:20`, none), which I had measured but left in the stage report.

The verbatim `## Acceptance` heading inside `## Linear edits made` is untouched —
`git diff -U0` over the file shows exactly one `-## Acceptance` / `+## Acceptance criteria` pair,
and the captured original still reads `## Acceptance` at line 110.

Re-confirmed with the `--stage triage` form of the command as well:
`spacedock status --read drc-4587 --ac-scan --stage triage --json --workflow-dir docs/roadmap-burndown`
returns seven entries with ids AC-1 through AC-7, all `unevidenced: true`. Both forms agree, so the
scan does not depend on the stage being inferred from frontmatter.
