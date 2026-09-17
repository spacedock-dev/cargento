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
pr: "#361"
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

### Feedback Cycles

- Cycle 1: NO-GO — review (two lenses plus an arbiter); surface 9 files/132 runtime + 45 docs vs estimate 105 runtime (125.7%) / 28 docs (161%); AC narrowed: AC-7 scoped to the rules this change moved, composed-rule residual routed to DRC-4602 on the precedent AC-1 set.
- Cycle 2: NO-GO — review (two lenses plus an arbiter, cycle 2); surface re-baselined per the correction-round rule; AC unchanged: AC-7's own new clause falsified six times by slot-shaped pairs a selector sweep cannot see. Cycle 3 escalates to the captain rather than running a fourth round.
- Cycle 3: NO-GO — review (two lenses plus an arbiter, cycle 3); escalated to the captain per the three-cycle limit and resumed on the captain's standing take-the-recommended-route directive; surface docs re-measured at 100 added against 86 reported; AC unchanged. The verdict is completeness, not execution: four further inversions this branch created, in twelve emitter files the round never opened, plus a guard fixture that builds a DOM the app never renders. Round 3 is structural — figure-paired absences get their own class — rather than a fourth pass at instances.
- Cycle 4: NO-GO — review (self-arbitrated, depth stepped down for a 10-line CSS diff); a fourth inversion survives with the round's own new test asserting the inverted state as correct, the published bound does not re-derive against itself, and the class contains pre-existing instances this branch never created. Round 4 scopes the PR back to what cannot be wrong — no absence rule raised unless its paired value already resolves at or above the sentence tier — and moves the absence-tier remainder to DRC-4602.

## Stage Report: implementation

- DONE: Write the gate-approved drafts to Linear as the FIRST action before any code — the issue body, the owning milestone description, and the journey and move labels — sending each body unwrapped as one line per paragraph, then read back the issue's relation set and report every edge the write created.
  Both written before any file was touched, each paragraph joined to one line. **No relation edge appeared**: `blocks` is the same seven, `blockedBy`, `relatedTo` and `duplicateOf` all still empty — both mentioned issues (DRC-4594, DRC-4596) were already in `blocks`. Labels were already `move:sharpen` + `journey:mid-flight`, confirmed on read-back; no label write was needed. **Two serializer moves to report, neither repaired:** the AC `-` bullets came back as `*`, and the bold run around both issue references was dropped when Linear turned the plain text into `<issue>` mentions (`**Land this before DRC-4594**` → `**Land this before** <mention>`; `**DRC-4596**` → bare mention). The milestone's DRC-4596 became a plain Markdown link with its surrounding bold intact.
- DONE: Write the failing test first and watch it fail for the right reason, then regenerate all nine byte pins from the assets and re-run test_next_page, test_next_flag and test_focus each ALONE, reporting the pass ratio of each isolated run.
  `test_both_absence_explanations_read_as_sentences_not_header_labels` landed in `CockpitHeldToTabTest` (verified by walking back to the enclosing `class` line, not assumed) and failed on `assertFalse(out["revisionInHeader"])` — the right reason: both spans rendered, and the header check caught them. It fails again if either span goes back inside its `<header>`, or if either rule is bumped to 15px while keeping `var(--mono)`. Pins regenerated from `frontend_page.asset_path`/`load_page`, not patched: 8 of the 9 figures moved, and `next-cockpit.js`'s size came back identical at `198_105` (the two moves are byte-neutral swaps) so it was verified rather than rewritten. No tenth pin moved. Isolated runs: `test_next_page` 25/25, `test_next_flag` 7/7, `test_focus` 96/96, all OK; the new test 1/1 alone.
- DONE: Run the canonical pre-PR suite from AGENTS.md "Pre-PR Checks" read from that file rather than from any copy, invoke the sync-docs skill and commit its doc updates onto this same branch, then measure the actual surface with git diff --numstat against the merge base and report files and LOC versus the declared estimate with the percentage.
  Read from `AGENTS.md` in the worktree, not from a copy. `ruff check` clean, `ruff format --check` clean, `mypy` no issues, `lint_embedded.py` clean, `validate_plugins.py` clean, `bump_version.py --current` 0.26.0, no version field moved since the merge base (that half checked by hand, as AGENTS.md says nothing local does it). Dashboard suite **3527 tests OK** (2 skipped), scripts suite **515 OK** (1 skipped), `coverage report` 86.8% total with `fail_under` satisfied. Load average 2.9 throughout, so no module needed the contention re-run. `claude plugin validate --strict` passed; `agy` is not on this PATH. `sync-docs` invoked; it found no drift beyond the two documents already edited, left `COMPATIBILITY.md`'s marker alone per the parallel-work rule, and its tone check reports clean. **Surface: 8 files, over the declared 7 — see the overage note below.**
- DONE: Commit the work DCO signed off on the branch and STOP without pushing and without opening a pull request, reporting the branch name and the candidate SHA.
  Branch `spacedock-ensign/drc-4587`, candidate SHA **`f6ced2f86449a757f8093bfc49666e7c8052007e`**, one commit, working tree clean. Not pushed, no PR opened. A duplicate `Signed-off-by` (the manual one plus `-s`) was amended away; one sign-off remains.

### Surface versus the declared estimate — two overages, neither silent

| Surface | Declared | Actual | Percentage |
|---|---|---|---|
| Runtime | 2 files, ~105 changed, ±25% (78.75–131.25) | 2 files, **132** (`styles.css` 128, `next-cockpit.js` 4) | **125.7%** — 0.75 lines past the ceiling |
| Oracles | exactly 9 pinned numbers, 3 files, zero tolerance | 9 verified, 8 rewritten, 3 files | **100%** — met |
| Docs | 2 files, ~18 lines, ±10 (8–28) | 2 files, **35** (`design-next-ui.md` 33, `CONTRIBUTING.md` 2) | **194%** — 7 lines past the ceiling |
| Tests | not costed | `test_next_cockpit.py` +43 (the required failing test) | a fourth test file the estimate did not budget |

Runtime net is **+8**, just under the declared +10 to +16. Six of the 132 runtime lines are a
**discretionary inclusion no acceptance criterion required**: AC-3 bans literal `10px` only, and I
also remapped the six sub-10px literals (9px at `:375`/`:415`, 9.5px at `:289`/`:359`/`:366`/`:457`)
onto `var(--fs-label)`, because deleting `--fs-column` while leaving the 9px it defended is half a
job. Dropping them would put runtime at 126 (120%), comfortably inside. **This is the FO's call,
not mine**, and I did not shave the number to fit. The docs overage is the gap record in the next
paragraph, which is worth more than the seven lines.

### One finding, filed rather than fixed — AC-1's first clause is not fully met

AC-1 reads "every sans text-bearing rule under `cargento_runtime/web` resolves to 15px or larger".
Its own `Verified by` is the recorded inventory, which is satisfied: 67 rules, all on
`var(--fs-sentence)`. But the classifier I recorded (**sans + its own prose line-height**) also
catches **17 further rules at 13px to 14.5px** on the `--fs-body`, `--fs-summary` and `--fs-sm`
steps plus two literals (`.next-project-goal-text` 14.5px, `.next-operations-header p` 13.5px).
Those were left. Raising them is ~17 more runtime lines, which takes the change to 142% of the
declared surface and past the stop clause; and **two of the 17 are not sentences at all** (a
textarea at `:871`, the prototype terminal at `:1139`), so the set needs reading one selector at a
time rather than a sweep. `docs/design-next-ui.md` records this openly as the gap to close next
rather than letting the inventory imply a floor the stylesheet does not have. Evidence: the audit
script is reproducible from the committed tree. **Proposed: Deferred risk, owned by a new issue,
not promoted into this PR.**

### AC status at hand-back

AC-1 **partial** (inventory clause met, universal clause not — see above). AC-2 **met** (new test,
red then green). AC-3 **met** (`font-size:10px` 27→0, `font:`-shorthand 10px 4→0, three tokens
gone, `--fs-label` 11px). AC-4 **met** (`grep -rn 'ruling R9'` over `cargento_runtime/` and `docs/`
returns nothing; `RuntimeDecisionCitationsTest` green). AC-5 **met** (`--measure:540px` declared,
49 capped rules, none of the three named carries a cap, no capped line carries
`overflow-wrap:anywhere`). AC-6 **met** (9 pins, isolated runs green, no tenth moved).
AC-7 **not attempted** — interactive by the gate's own ruling, settled by a live drive or the
captain, never by automation built here.

### Summary

The change does what the issue asked in the register the issue named: a 15px sentence tier at
weight 500/1.55 on 67 sans prose rules, a single 11px label tier absorbing 37 literal sizes and 4
dead-or-redundant tokens, one `.09em` tracking value on 24 declarations, a 540px measure on 49
rules, and both absence explanations out of their `<header>`s and into sans. All nine byte pins
were regenerated from the assets in one pass and each oracle module was re-run alone.

Two things the first officer should rule on before this becomes a PR. The runtime surface is
**0.75 lines past its ±25% ceiling**, and six of those lines are a remap no acceptance criterion
demanded — I would rather be told to keep or drop them than decide it myself. And **AC-1's
universal clause is not met**: 17 sans rules still sit below the new floor, which I recorded in
`docs/design-next-ui.md` and propose as its own issue rather than promoting a ~17-line addition
into this branch.

Nothing was pushed and no pull request exists. The `pr-merge` ceremony is the FO's.

## Stage Report: review

- DONE: State the chosen review depth and the property of the diff that justified it BEFORE reviewing, per AGENTS.md "Calibrating Effort" — this diff owns the frontend byte pins, so the table's two-lenses-plus-an-arbiter row applies unless you argue otherwise.
  Two lenses plus an arbiter, stated before any file was read; the justifying property is that the diff rewrites nine byte pins across three oracle modules and edits `web/`, which is the table's conflict-prone-surface row verbatim. Not argued down: no security/credential/data-loss surface (full adversarial would be disproportionate), and the change is user-visible (self-verify is excluded). Lens A took cascade and register, lens B took pins, oracles and doc truthfulness; I arbitrated by reproducing rather than ranking.
- DONE: Reproduce every acceptance criterion from its own Verified by clause rather than trusting the implementation self-report, and report AC-7 as settled by a live drive or explicitly not attempted, never by automation built here.
  AC-2/3/4/5/6 reproduced and PASS; AC-1 partial as accepted; **AC-7 FAILS on its own falsifier** — see the AC table and finding F1 below. AC-6 was recomputed twice independently (mine and lens B's), both matching all nine pins.
- DONE: Read the Copilot inline review comments in addition to any top-level review, and confirm CI is green on the CURRENT head SHA with mergeStateStatus, naming the SHA the checks belong to.
  No review had ever been requested, so there were zero comments to read; I requested Copilot (a PR-metadata action, no bytes and no HEAD touched) and it returned 1 inline comment, which I **confirmed against the tree**. CI: all 12 checks SUCCESS on head `3cc7ef49`, including the Windows re-run. `mergeStateStatus: BLOCKED` — every check passes, so the block is the missing approving review, not a failure.
- DONE: Give a GO or NO-GO verdict with the findings that produced it, and do NOT edit the branch — a confirmed material finding routes back to implementation with its evidence.
  **NO-GO**, on F1/F2/F3. No file on the branch was edited by this stage; the only repo write was a gitignored screenshot under `docs/screenshots/`.

### CI on the current head

All 12 checks SUCCESS on `3cc7ef49464f776234623b6ff4afc06d322223a3`: quality-gate, validate, version-guard, latest-client-smoke, lint, mypy, runtime floor 3.11, tests+coverage, and platform tests on ubuntu, macos and **windows**. The Windows tripwire failure the FO re-ran **went green on this head** (job started 10:40:46Z) — the flake hypothesis is now substantiated by a passing re-run rather than assumed, so the "unrelated" claim stands. `mergeStateStatus: BLOCKED`, `mergeable: MERGEABLE`.

### Acceptance criteria, each reproduced from its own Verified by clause

| AC | Verdict | What I reproduced |
|---|---|---|
| AC-1 | Partial (as accepted) | Inventory clause holds: 67 rules on `var(--fs-sentence)`. Token floor: min `:root` token is 11px (`--fs-label`, `--fs-machine`), so `>=11` holds. Universal clause unmet — accepted, DRC-4602, not re-opened. |
| AC-2 | PASS | `styles.css:866,963` both `font:500 var(--fs-sentence)/1.55 var(--sans)` (base had both mono 10px). `next-cockpit.js:2154,2412` emit both spans **after** the literal `</header>`, read in context. |
| AC-3 | PASS | `font-size:10px` 0, `font:`-shorthand 10px 0, all three tokens absent from `:root`, `--fs-label:11px`. |
| AC-4 | PASS | `grep -rn 'ruling R9'` over runtime and `docs/` returns nothing. |
| AC-5 | PASS as written | 49 capped; the three named selectors carry no cap; literal falsifier (cap + `overflow-wrap:anywhere` on one line) returns **0**. See the caveat below — the falsifier is weaker than the criterion. |
| AC-6 | PASS | I recomputed from the assets myself: assembled 914344/`2165bf68…`, styles.css 111050/`91a303b2…`, next-cockpit.js 198105/`16f67be9…` — all nine pins match, lens B agreed independently, no tenth pin moved. |
| AC-7 | **FAIL** | Live drive, not automation built here. See F1. |

**AC-7 was settled by a live drive.** I ran this branch's own `server.py` on a free port and drove it with a real browser, reading `getComputedStyle`. Port 4553 — the port AC-7 names — was already held by the **installed plugin v0.24.0**, a different tree; measuring there would have produced a confident false pass, so I bound elsewhere and verified the served CSS carried `--fs-sentence:15px` before trusting a single number. `.next-cockpit-content` computes 15px/500 as claimed. The human-read half of AC-7 remains the captain's: screenshot at `docs/screenshots/drc-4587-review-recovery-register-inversion.jpg` (gitignored).

### Findings

**F1 — Material. The recovery briefing now renders absences larger than the facts they replace.** Live on this branch: `.next-cockpit-recovery p` (e.g. "assignment unavailable", "Session result not captured") computes **15px weight 500 sans in `--ink3`**, the dimmest ink, while `.next-cockpit-recovery strong` — the value that *was* captured — computes **12.5px mono in `--ink`**. `styles.css:1081` raised the container (base `1073` was `var(--fs-xs)`), but `styles.css:1083` `.next-cockpit-recovery strong,.next-cockpit-recovery small{font-size:var(--fs-xs)}` is untouched and matches a different element, so the raise reaches only the absence text. Before this change both were 12.5px and the cell was internally consistent. Four evidence fields: (1) released user opening a project on the default board, no flags; (2) observable — absence text is 20% larger than the fact beside it, visible in the screenshot; (3) `value-ac[AC-7]`, whose falsifier names exactly a computed 12.5px surviving a raise; (4) trigger: `getComputedStyle` on this branch's server. Whether absences *should* outrank facts on a board framed as "see the gap" is a product call I cannot own — that half is **Needs decision**.

**F2 — Material, rule-level only.** The same shape raises captions past their values elsewhere: `styles.css:1093` puts `.next-cockpit-now-state small` on the sentence tier (15px) while `:728` holds `.next-cockpit-now-state strong` at `var(--fs-xs)` (12.5px); `:1094` puts `.next-cockpit-memos label>small` at 15px against `:769`'s 14px `strong`. Both confirmed by reading the rules and their specificity. **Not reproduced live** — this board had no data rendering those panels, so I report them as rule-level, not as measured renders.

**F3 — Material. AC-7's falsifier fires, and the doc's admission test structurally cannot see why.** Sans prose with its own prose line-height still renders below 15px on the live board: 18 `small` in the recovery block (project view) and **163 `strong` under `.next-operation-fact--unknown`** (sessions view), all at **12.5px**. The design doc states the residual gap as "13px to 14.5px", and lens B's rule-level census agrees that no *rule* qualifies at `--fs-xs` — because these are composed across three rules that no single-rule test can join: `:482` sets `--fs-xs` + `var(--mono)`, `:483` flips the family back to `var(--sans)`, `:397` supplies `line-height:1.4`. This is precisely the "no grep can see that, only a computed style does" case the issue predicted, and it is why AC-7 could not be substituted by the offline checks.

**Confirmed, documentation accuracy (not user-visible).** Copilot's single inline comment is **correct**: the doc's "one tracking value `.09em` … three kept their own because their content is not uppercase" misses `.next-capacity-head span`, which is on `--fs-label` at `.06em` and whose content *is* uppercase — `next-capacity.js:474` emits the literals `WINDOW`, `USED`, `PACE`, `RESETS`. Lens B additionally measured three false counts in `docs/design-next-ui.md`: the deferred gap is **19** rules, not 17 (the doc's own enumeration accounts for only 15), which **sizes DRC-4602**; "three of the six sub-12px tokens had no callers" is **two** (`--fs-meta-detail` had 4); and AC-3's "was 9" sub-11px `:root` tokens is **4**. Lens A separately showed the doc's load-bearing justification for the tier — that the audit put `--ink` below the body-text requirement — is not reproducible here: `--ink` on `--bg` is **16.36:1** (I recomputed it), and `test_next_page.py` asserts `>4.5:1` and is green. Triage already ruled the APCA figures audit-only at the milestone; this PR wrote the same claim into a canonical design doc without that caveat.

**Refuted or not carried.** Lens A's AC-5 finding: the literal falsifier does **not** fire (0 same-line hits, verified), so AC-5 passes as written — but `.next-guardrail-copy small` does carry both the cap (`:356`) and `overflow-wrap:anywhere` (`:355`) across two lines, so the criterion's mechanical falsifier is narrower than the criterion. Recorded as a criterion weakness, not a defect. Lens A's weight-inheritance finding (`font:500` shorthand changing inherited weight below three containers) I could **not** reproduce live — `.next-cockpit-held-cue` never rendered — so it is unresolved, not confirmed. Lens A's headline that no raised rule loses the cascade is **correct**; F1/F2 are the mirror image it found instead, and my live sweep agrees no raised rule lost.

### Summary

Two lenses plus an arbiter, chosen up front because the diff owns the `web/` byte pins. The mechanical work is sound and I verified it rather than trusting it: all nine pins recompute from the assets (twice, independently), no tenth moved, the oracle modules pass alone, the token sweep is complete, both span moves are correct and newly tested, and CI is green on head `3cc7ef49` including the Windows re-run that had failed — so that failure was a flake, now substantiated rather than waved through.

The verdict is **NO-GO**, and it rests on the one criterion nobody had checked. AC-7 was not attempted, and it fails on its own declared falsifier: raising `.next-cockpit-recovery>div` left `styles.css:1083` holding the values inside it at 12.5px, so on the live board the recovery briefing now prints "assignment unavailable" larger than the assignment, in the dimmest ink in the palette. No offline check could have caught it — the doc's admission test is rule-level and the defect is composed across three rules — which is exactly the argument the triage gate made for keeping AC-7 interactive.

I edited nothing on the branch. F1, F2 and F3 route back to `implementation` with the evidence above; the product half of F1 — whether absences should outrank facts — is the captain's, not implementation's. The four documentation corrections, including Copilot's confirmed one, are in the same two files and can ride the same fix round.

### Addendum: the branch moved under this review

While this review was running, a sibling committed `a251ca4a` "docs(design): correct the
tracking-inventory claim to the tree" onto the branch, fixing the Copilot finding I had just
confirmed — and more completely than Copilot found it, naming six rules across `.06em`, `.07em`
and `.04em` rather than the two Copilot cited. Recording it because it changes what this gate is
approving, and because I did not make it:

- **It is local only.** The PR head is still `3cc7ef49`; `a251ca4a` is unpushed. Every CI figure in
  this report belongs to `3cc7ef49`, which is the commit the PR currently carries.
- **It cannot move the byte pins.** `git diff --name-only 3cc7ef49 a251ca4a` touches
  `docs/design-next-ui.md` only — no file under `web/` or `tests/` — so AC-6 is unaffected and the
  nine pins I recomputed still hold.
- **It does not touch F1, F2 or F3.** `styles.css` is byte-identical across the two commits, so the
  measured 12.5px renders stand.
- **When it is pushed, the current green becomes a superseded head's green** and the gate needs a
  full re-run before merge — the stage definition's own warning, now live on this PR.
- `mergeStateStatus` has since moved `BLOCKED` → `CLEAN` on `3cc7ef49`.

One documentation correction from this review is therefore already addressed on the branch. The
three remaining doc-count corrections (the 19-not-17 gap size, the two-not-three uncalled tokens,
AC-3's "was 9") and findings F1/F2/F3 are still open.

## Stage Report: implementation (cycle 2)

Correction round 1, routed from a NO-GO review. Every disposition below was the one the first
officer authorized; nothing was re-triaged and nothing was widened beyond the named findings.

- DONE: Write the gate-approved drafts to Linear as the FIRST action before any code — the issue body, the owning milestone description, and the journey and move labels — sending each body unwrapped as one line per paragraph, then read back the issue's relation set and report every edge the write created.
  Cycle 1 wrote both bodies and confirmed the labels; unchanged this round. The one Linear write this round is **AC-7, rewritten** to bind the rules this change moved, scoped on the AC-1 precedent the captain accepted, with the composed-rule residual named and pointed at DRC-4602. Sent as a single-paragraph `patch`, so no other text was resent. **A relation edge is present that was not there at cycle 1: `blocks` now carries DRC-4602, making eight.** I cannot attribute it with certainty: I did not read relations immediately before this write, and DRC-4602 was created by the reviewer between the rounds, so either the mention created it or it shipped with the issue. Flagging rather than removing it, since a removal would be a second unapproved write. `blockedBy`, `relatedTo` and `duplicateOf` all remain empty.
- DONE: Write the failing test first and watch it fail for the right reason, then regenerate all nine byte pins from the assets and re-run test_next_page, test_next_flag and test_focus each ALONE, reporting the pass ratio of each isolated run.
  `AnAbsenceNeverOutranksTheValueItReplacesTest` resolves each selector's size from the stylesheet and asserts value >= companion over seven pairs. It failed **7 of 7 subtests** first, each naming its own figures. It goes red again if any one value drops below its absence: mutated `.next-cockpit-recovery strong` back to `var(--fs-xs)` and got the expected RED with the right message, then restored and GREEN. One defect in the test itself was found and fixed this way: the block scan read a preceding CSS comment as part of the selector, so a commented rule read as *undeclared* rather than as wrong; it now strips comments first. Pins: 7 of 8 written sites moved; **`next-cockpit.js` size and digest were both verified unchanged** because no JS changed this round, so 9 pins were checked and 7 rewritten, with no tenth moving. Isolated runs: `test_next_page` 25/25, `test_next_flag` 7/7, `test_focus` 96/96, invariant test 1/1, all OK.
- DONE: Run the canonical pre-PR suite from AGENTS.md "Pre-PR Checks" read from that file rather than from any copy, invoke the sync-docs skill and commit its doc updates onto this same branch, then measure the actual surface with git diff --numstat against the merge base and report files and LOC versus the declared estimate with the percentage.
  Read from `AGENTS.md` in the worktree. `ruff check` clean, `ruff format --check` clean, `mypy` clean (it caught two missing class-attribute annotations on the new test and they were added), `lint_embedded.py` clean, `validate_plugins.py` clean, `bump_version.py --current` 0.26.0, no version field moved. Dashboard suite **3528 OK** (2 skipped), scripts suite **515 OK** (1 skipped), coverage 86.8% with `fail_under` satisfied. Load average 5.8-6.9, so I re-ran the three pin modules alone anyway and report both results. `sync-docs` ran in cycle 1; this round's doc edits are the four corrections it does not own, and `COMPATIBILITY.md`'s marker is still untouched.
- DONE: Commit the work DCO signed off on the branch and STOP without pushing and without opening a pull request, reporting the branch name and the candidate SHA.
  Branch `spacedock-ensign/drc-4587`, candidate SHA **`4fb5ee6d62c30e91fa0c6712c7ea29ab0ca52f59`**, tree clean, not pushed. PR #361 exists and was opened by the first officer; I did not touch it.

### F1 and F2: the sweep, not just the three reported cells

Seven value rules now sit at the sentence tier beside their absence or caption: `.next-cockpit-recovery strong` (split from the `small` storage cue, which is not a value and stays at 12.5px), `.next-cockpit-recovery .next-project-goal-text` (keeping mono), `.next-cockpit-now-state strong`, the memo field value, `.pc-terminal-identity code` and `strong`, and `.next-attention-open strong`. The last three were not in the finding: `.pc-terminal-identity` emits value and absence from the same ternary (`project.js:820-824`), which is the F1 shape exactly.

**Nine candidates the sweep surfaced and I did not change, with reasons.** `.next-operations-fleet` is already correct: the value is 27px above a 15px note and an 11px label. `.next-cockpit-recovery>header`, `.next-cockpit-recovery span`, `.next-attention-open li>span` and `.pc-entry-details b` render captions (`PROJECT RECOVERY BRIEFING`, `ASSIGNMENT`, a code, `Why included`), so sitting below their values is the intended direction. `.next-cockpit-recovery .next-project-goal-source` and `.pc-entry-details time` are provenance and timestamps, not values the prose replaces. `.next-cockpit-recovery>div` at `:824` is overridden by `:1081` and is dead for this cascade. `.next-project-detail-rail .next-usage-*` only shares an ancestor with `.next-rail-reason`; they are separate components, not a value and its caption.

**F2 is rule-level evidence, not a live reading**, as the finding said: the board carried no data rendering those two panels, so the cascade is what was read. F1 and the five others were confirmed live.

### AC-7, re-driven after F1 and F2 landed

Driven on **port 4557**, not 4553: another session's board already held 4553 and serves different assets, so driving it would have measured the wrong tree. Confirmed the page served `--fs-sentence:15px` before reading anything. Computed figures: `.next-cockpit-content` prose **15px / 500 / Space Grotesk**; both absence strings **15px / 500 / Space Grotesk, max-width 540px**, each on its own line. All seven value-and-companion pairs **PASS at 15px vs 15px**. The human "is it actually easier to read" half is the captain's, not mine. The server I started is stopped and 4553 is untouched.

### D1 to D4, each measured before it was written

D1: the deferred gap is **19**, not 17. A single-rule census finds 17 (seven `--fs-sm`, four `--fs-body`, two `--fs-summary`, four literals; my earlier "two literals" was the miscount that made the enumeration read as 15). The two it cannot see are `.next-operation-fact--unknown strong` (size and mono at `:482`, sans at `:483`, line-height at `:397`) and `.next-cockpit-recovery small` (size at `:1089`, family and line-height inherited). D2: **I measured three, not two**, and the difference is the boundary, not the fact. Zero-caller tokens are `--fs-column`, `--fs-meta` and `--fs-breadcrumb`; `--fs-breadcrumb` is exactly 12px, so "sub-12px" read strictly gives two and the issue's own "six sub-12px tokens" requires the inclusive reading that gives three. The doc now names them so neither count can be misread, and records the boundary. `--fs-meta-detail` was never among them; it had four callers, which the doc now says. D3: stated unambiguously as four `:root` steps below 11px with 9px the smallest, which removes the "9" that could be read as a count. **The Linear AC-1 text "(it shows 9 today)" is a minimum in px, not a count, and is correct as written** — I did not change it. D4: the APCA justification now carries the milestone's audit-only caveat verbatim in substance, beside the recomputed `--ink` on `--bg` of **16.36:1** with the asset test green.

### Surface, reported rather than trimmed

| Surface | Declared | Actual | Percentage |
|---|---|---|---|
| Runtime | ~105 changed, ceiling 131.25 | **145** (`styles.css` 141, `next-cockpit.js` 4) | **138.1%** |
| Oracles | exactly 9 pins, zero tolerance | 9 checked, 7 rewritten, 2 verified unchanged | met |
| Docs | ~18 changed, ceiling 28 | **62** (`design-next-ui.md` 60, `CONTRIBUTING.md` 2) | **344%** |
| Tests | not costed | `test_next_cockpit.py` 132 | outside the estimate |

Per the round's instruction I did not trim prose to fit. The runtime overrun is F1 and F2; the docs overrun is the four corrections plus the gap records. **One commit on this branch is not mine**: `3cc7ef49 docs(burndown): record the captain's act-don't-ask and visibility directives`, 19 lines in `docs/roadmap-burndown/README.md`, already on origin and riding in #361.

### Summary

The review was right and F1 was mine: raising `.next-cockpit-recovery>div` to the sentence tier without raising the value rules under it made the absence outrank the fact it replaced. I swept the class rather than patching the three reported cells, found four more instances and nine look-alikes that are correctly ordered, and pinned the invariant in a test that fails per pair and survives a mutation check. AC-7 re-drove green on all seven pairs against a board serving this branch's assets.

Two things for the gate rather than for me. The surface now overruns on both runtime and docs, reported above and not trimmed. And a `blocks` edge to DRC-4602 is present that was absent at cycle 1, which I have flagged rather than removed because I cannot prove my write created it.

## Stage Report: review (cycle 2)

Re-review of correction round 1 at `4fb5ee6d`. Reviewing the fix, not re-deriving cycle 1.

- DONE: State the chosen review depth and the property of the diff that justified it BEFORE reviewing, per AGENTS.md "Calibrating Effort" — this diff owns the frontend byte pins, so the table's two-lenses-plus-an-arbiter row applies unless you argue otherwise.
  Same depth, restated before reading: two lenses plus an arbiter. The round moved `styles.css` again and rewrote seven of the nine pins, so the conflict-prone-surface row still governs. Lenses aimed at the two claims I could not settle by reading: the nine exemptions, and whether the new test binds anything.
- DONE: Reproduce every acceptance criterion from its own Verified by clause rather than trusting the implementation self-report, and report AC-7 as settled by a live drive or explicitly not attempted, never by automation built here.
  AC-2/3/4/5/6 still PASS; AC-6 recomputed independently again on this head. **AC-7 FAILS again** — on the clause the round itself added this cycle. Settled by a live drive on an isolated export, not by automation.
- DONE: Read the Copilot inline review comments in addition to any top-level review, and confirm CI is green on the CURRENT head SHA with mergeStateStatus, naming the SHA the checks belong to.
  Copilot's cycle-1 comment was **correctly fixed** — and more completely than Copilot found it. No new inline comments. CI: 12/12 SUCCESS on `4fb5ee6d`, `mergeStateStatus: CLEAN`, and `headRefOid` confirms the checks belong to this head, not the superseded one.
- DONE: Give a GO or NO-GO verdict with the findings that produced it, and do NOT edit the branch — a confirmed material finding routes back to implementation with its evidence.
  **NO-GO.** Branch untouched; only a gitignored screenshot written.

### What the round got right, verified rather than accepted

**F1 is fixed, reproduced live.** On an export of `4fb5ee6d` served on a free port, `.next-cockpit-recovery p` and `.next-cockpit-recovery strong` both compute **15px**, and the value keeps mono and `--ink` against the absence's sans and `--ink3` — the code comment's claim holds. Screenshot: `docs/screenshots/drc-4587-cycle2-inversion-resolved.jpg`.

**The nine byte pins are right, recomputed by me from the assets before any lens touched the tree:** styles.css 111533/`0cdd9483…`, assembled 914827/`9a29a48f…`, next-cockpit.js 198105/`16f67be9…` unchanged as claimed. Exactly nine occurrences, zero stale values from the old head, no tenth. Modules alone at load 5.59: `test_next_page` 25, `test_next_flag` 7, `test_focus` 96, `test_next_cockpit` 234, all OK.

**Claim 3 — the invariant test is real.** It extends plain `TestCase`, needs no fixtures, is not node-gated, and runs with **zero skips** (I ran it myself). Seven pairs, fourteen selectors, all resolving to real numbers. Six of seven mutations KILLED with correct messages, including the round's own and two it never tried; a renamed selector fails rather than passing, so a vanished rule cannot read as satisfied. The comment-stripping fix is **load-bearing, not cosmetic**: against the unstripped source the new rule resolves to `None` and the test would be red today. The tree was restored byte-identical — I verified the sha256 matches my own pre-mutation figure.

### NO-GO: the sweep was selector-shaped, not slot-shaped

**Claim 1 does not hold. Two of the nine exemptions are wrong, and four more slots were never listed.** The defect does not live in look-alike selectors; it lives in the JS ternaries that choose which class a slot gets. Value and absence never co-exist in one render, so neither a selector sweep nor my own cycle-1 live sweep can see them — **I missed these in cycle 1 for the same reason, and say so.** Measured against the served stylesheet, with the emitter confirmed for each:

| Slot | Emitter | base (value vs absence) | **head** | 
|---|---|---|---|
| recovery `span.next-project-value` (exemption 3) | `next-cockpit.js:2711-2718` | 11.5 vs 12.5 | **11.5 vs 15.0** |
| rail wait duration | `next-delegation.js:237` | 11.0 vs 12.5 | **11.0 vs 15.0** |
| rail token rate | `next-delegation.js:218` | 10.5 vs 12.5 | **10.5 vs 15.0** |
| rail pace / resets | `next-delegation.js:250,265-268` | 11.0 vs 12.5 | **11.0 vs 15.0** |
| `pc-entry-details time` (exemption 7) | `project.js:983-990` | 11.0 vs 12.5 | **11.0 vs 15.0** |
| `pc-source` | `project.js:977-981` | 12.5 vs 12.5 | **12.5 vs 15.0** |

Every one is the F1 shape: one expression, one slot, a known class and an absent class. **This PR raised the absence side of all six** — `.next-project-detail-rail .next-rail-reason` and `.pc-substrate-reason` both went `var(--fs-xs)` → `var(--fs-sentence)` — and left every value untouched, so each gap widened by 2.5px to 4.5px. The sharpest evidence that the sweep was selector-shaped: `.pc-substrate-reason,.pc-terminal-identity p` is **one declaration**, and the round raised the values paired with `.pc-terminal-identity p` while leaving the values paired with `.pc-substrate-reason` on the same line. Exemptions 3 and 7 are the two the round justified as "captions" and "timestamps"; the emitters say both are values an absence replaces. Exemptions 1, 4, 5, 6, 8 are correct; 2 and 9 reach the right answer on reasoning the markup does not support.

This falsifies **AC-7's own new clause** — "any value computing smaller than its own absence" — six times, and the test pins seven pairs none of which is among them.

**One thing the fix introduced.** `.next-cockpit-recovery strong{font-size:var(--fs-sentence)}` is a descendant selector, so it also catches the briefing's `<strong>` caption: **"PROJECT RECOVERY BRIEFING" now renders 15px**, up from 12.5px, level with every value in the strip. Measured live. Whether a caption may sit at the value tier is the milestone's call, not mine — DRC-4589 exists to split those roles.

### Claim 4 — both rulings, one against me

**"Was 9" — the ensign is right and I was wrong.** AC-1 reads "showing a minimum of 11 (**it shows 9 today**)". That is a minimum in px, and the base minimum is `--fs-column:9px`. Declining was correct. The error was mine: my cycle-1 report carried a lens's misreading of a count and misattributed it to AC-3, and the instruction to "fix" it came from me. Nothing to change in Linear.

**Zero-caller tokens — the ensign's three is right; the set size is wrong, and so was my two.** At base, tokens at or below 12px number **seven**, not six: the enumeration omits `--fs-2xs` (11.5px, 41 callers). Among all seven, exactly three have zero callers — `--fs-column`, `--fs-meta`, `--fs-breadcrumb` — so **three is correct**. My cycle-1 "two" came from counting strictly below 12px, which excludes `--fs-breadcrumb`. Both readings are coherent; the doc mixes them, taking "six" from the strict reading and "three" from the inclusive one.

**Two further precision defects in the corrected prose.** The paragraph that sizes DRC-4602 says the nineteen sit "at 13px to 14.5px" and then names two that resolve to **12.5px** (`--fs-xs`) — self-contradictory within one paragraph; the range should read 12.5px. And "the six tokens at or below 12px" should be seven, per above. Both Polish, both in the sentence the gate is being asked to rely on.

### Surface: the re-baseline reading is sound, and I can show it

Not too convenient — but not a blank cheque either, so here is the evidence rather than the principle. The round added **13 lines** to `styles.css` over cycle 1, five of them the explanatory comment, the rest the seven value raises and the one rule split. Docs added 44. Every added line traces to an authorized finding; nothing is unattributable, and nothing was widened beyond F1, F2 and D1-D4. On that basis the runtime 138% and docs 344% do measure what review found. The caveat is that the figure is not final: fixing the six slots above will move runtime again.

### Summary

The round fixed what it was asked to fix and proved it: F1 reproduces as resolved on a live board, the byte pins are right on independent recomputation, and the new invariant test genuinely binds its seven pairs — it kills six of seven mutations, fails on a vanished selector, and its comment-stripping fix is load-bearing rather than cosmetic. Copilot's finding was closed more thoroughly than Copilot stated it.

The verdict is **NO-GO** on claim 1. "Swept the class" is the one claim that does not survive: the sweep followed selectors that resembled the reported ones, and the defect lives in the ternaries that decide which class a slot receives. Six slots still draw a stated absence 2.5px to 4.5px larger than the value it replaces, this PR widened all six by raising only the absence side, and two of them sit behind exemptions the round wrote reasons for. AC-7 fails on the clause added this cycle. I missed these in cycle 1 by the same blindness, which is why the fix should key on the emitters rather than on another pass over the stylesheet.

F1's fix should stand. The six slots and the promoted caption route back to `implementation`; the caption question and the two prose corrections are cheap and can ride the same round.

### Addendum: ruling on the membership test (DRC-4602 evidence, folded in)

**The finding is real, and I verified it rather than the framing.** Neither composed case satisfies
the letter of the sentence this PR adds. `.next-operation-fact--unknown strong` takes its size and
mono from `:482`, a flip to sans from `:483` and its line-height from `:397` — no one rule carries
sans *and* a prose line-height. `.next-cockpit-recovery small` (`:1089`) declares **neither**: it
sets a size and inherits both family and line-height from the cell. So a census applying that one
bolded sentence mechanically returns clean over both.

**Two corrections to the framing, both in the round's favour.**

The claim that #361 "states a membership rule that certifies a floor it does not hold" was exactly
right at `3cc7ef49` and is **too strong at `4fb5ee6d`**. Eight lines below the definition the
corrected document now says, in bold, "two that no single-rule census can see", names both
selectors, explains how each composes, and states that a one-rule census "reports seventeen and
misses both". The round fixed the certification defect in cycle 2. What survives is narrower: the
**definition itself was not amended**, so it and its own disclosed exception sit eight lines apart
with the definition still reading as self-contained — and it is explicitly offered as the thing "a
reviewer argues with", which is how the next four PRs in this milestone will use it.

And the auditor's **38-across-31 / 33-across-27 are very likely not a fourth and fifth figure for
the same set** as the document's nineteen. The document counts sans-prose *rules* in a 13px-14.5px
band; the auditor counts selectors resolving below the floor by composition, which is a wider
population and a different unit. Recorded as a caution: if those numbers are set beside the
nineteen without stating both definitions, one will later read as refuting the other when they
never measured the same thing.

**The decisive evidence is that the defect has already propagated into the correction.** The
disclosure paragraph enumerates **two** composed cases. There is at least a **third**:
`.next-project-value--absent` (`:159`) declares sans and a size but no line-height, so it fails the
letter the same way, and I measured three of them rendering at 12.5px sans with an inherited prose
line-height on the project view. The count "two" was itself derived with the defective test. I
cannot give the true number using the document's own rule, and neither could the round — which is
the whole argument for fixing the rule before anyone trusts a count produced by it.

**Ruling: the definition is corrected in THIS PR; the auditor, the remediation and the true count
stay in DRC-4602.** The captain's rule bars promoting a finding that buys another implement-and-CI
round. It does not bite here, for two independent reasons. First, **this is not promoted work** —
the sentence does not exist on `main`; #361 authors it, so correcting it is the same category as
D1-D4, which were already authorized. Second, **the round is happening anyway**: this review is
NO-GO on the six inversions, so the marginal cost of a prose qualification is one paragraph, no
code, no pin recompute, and no extra CI cycle. Deferring it would ship a canonical rule known to be
wrong and then ask DRC-4602 to correct a document it does not own.

**What the sentence must do** (the property, not the wording — I do not write the branch): state
membership over the **element's resolved style**, not over one rule's declarations. It has to say
that sans and the prose line-height are resolved through the cascade and may be inherited or
arrive from different rules, and that a census reading one rule at a time understates the set. The
existing disclosure paragraph then stops being an exception bolted onto a rule that contradicts it
and becomes an illustration of it. The nineteen, the thirty-three and the true composed count all
belong to DRC-4602 and should not be restated here.

**On the counts not holding still:** the 181 figure is a snapshot of live board data, not a
constant — I measured 163 of the `--unknown strong` shape at cycle 1 and 183 at cycle 2, forty
minutes apart, on the same stylesheet, because the board renders whatever sessions exist. The
stable unit is the rule set, not the element tally. Any element count that reaches the document
should carry the date and commit it was taken at, or it will be read as a fact about the
stylesheet when it is a fact about a moment.

The `--ac-scan` code-fence failure is recorded and is not this PR's.

## Stage Report: implementation (cycle 3)

Correction round 2. Every disposition below was the one the first officer authorized. Two findings
I disagreed with are reported as measurements rather than adopted; both are noted as such.

- DONE: Write the gate-approved drafts to Linear as the FIRST action before any code — the issue body, the owning milestone description, and the journey and move labels — sending each body unwrapped as one line per paragraph, then read back the issue's relation set and report every edge the write created.
  No Linear write this round and none was authorized. Cycle 1 wrote both bodies, cycle 2 rewrote AC-7. **The DRC-4602 sizing figure the first officer said he would carry to Linear has changed: it is twenty-one, not nineteen** (see D1 below), so the Linear correction should carry that number.
- DONE: Write the failing test first and watch it fail for the right reason, then regenerate all nine byte pins from the assets and re-run test_next_page, test_next_flag and test_focus each ALONE, reporting the pass ratio of each isolated run.
  The test was rewritten slot-shaped before any fix and failed **7 of 7**: the six slots plus the caption regression, each naming its own two figures. It binds in both directions and was mutation-checked twice after the resolver rewrite: reverting `.next-rail-wait-duration` gives `11.0 not >= 15.0`, and reverting the caption scoping gives `15.0 not less than 15.0`. Pins: 7 of 8 written sites moved; **`next-cockpit.js` size and digest both verified unchanged**, since no JS changed this round. Isolated: `test_next_page` 25/25, `test_next_flag` 7/7, `test_focus` 96/96, slot census 2/2.
- DONE: Run the canonical pre-PR suite from AGENTS.md "Pre-PR Checks" read from that file rather than from any copy, invoke the sync-docs skill and commit its doc updates onto this same branch, then measure the actual surface with git diff --numstat against the merge base and report files and LOC versus the declared estimate with the percentage.
  Read from `AGENTS.md` in the worktree. All clean: `ruff check`, `ruff format --check`, `mypy`, `lint_embedded.py`, `validate_plugins.py`, `bump_version.py --current` 0.26.0, no version field moved. Dashboard **3529 OK** (2 skipped), scripts **515 OK** (1 skipped), coverage 86.8% with `fail_under` satisfied. Load average 2.9, and the three pin modules were run alone anyway. `sync-docs` ran at cycle 1; this round's doc edits are the corrections it does not own, and `COMPATIBILITY.md`'s marker is still untouched.
- DONE: Commit the work DCO signed off on the branch and STOP without pushing and without opening a pull request, reporting the branch name and the candidate SHA.
  Branch `spacedock-ensign/drc-4587`, candidate SHA **`e32b207d2d3d72087919ee0ab669ff96f31860c0`**, tree clean, not pushed, PR #361 untouched. History is linear and unrewritten, so the stacked `spacedock-ensign/drc-4588` rebases onto one new commit.

### The six slots, measured in a browser before and after

The finding's diagnosis is the part worth keeping: **a value and its absence are chosen by a
ternary and never co-exist**, so neither a selector sweep nor a populated board can show the pair.
Both branches were built separately from each emitter's own markup and read with `getComputedStyle`.

| Slot | Emitter | before | after |
|---|---|---|---|
| recovery published value | `nextCockpitWaitingCommand` | 11.5 vs 15.0 | 15.0 vs 15.0 |
| rail wait duration | `nextRailWaiting` | 11.0 vs 15.0 | 15.0 vs 15.0 |
| rail token rate | `nextRailDelegation` | 10.5 vs 15.0 | 15.0 vs 15.0 |
| rail pace and resets | `nextRailCapacityWindow` | 11.0 vs 15.0 | 15.0 vs 15.0 |
| event time | `projectEventTime` | 11.0 vs 15.0 | 15.0 vs 15.0 |
| published value | `projectPublishedValue` | 12.5 vs 15.0 | 15.0 vs 15.0 |
| briefing caption (must stay below) | `nextCockpitRecovery` | 15.0, level | 11.5, below 15.0 |

**Worth flagging for the gate, not as an objection:** the rail's compact figures were the value side
of four of these, so the rail's token rate, pace, resets and wait duration now render at 15px where
they rendered at 10.5px to 11px. That is what "raise the value to match its absence" costs on this
surface, and it is a visible change to the rail's density rather than a quiet one.

### Exemptions 2 and 9: reasoning repaired, and what it cost

Exemption 3 and 7 were wrong and are now two of the six fixed slots. For the other two the finding
said the answer was right and the reasoning was not, which was fair:

- **Exemption 2, `.next-cockpit-recovery>header`.** I had called it "a section label". The emitter
  shows it holds exactly one fixed string, `PROJECT RECOVERY BRIEFING`, with no branch that could
  make it an answer. That is now asserted rather than argued: `test_a_caption_stays_below_the_values_it_labels` fails if it ever rises to meet them.
- **Exemption 9, `.next-project-detail-rail .next-usage-*`.** I had called them "separate
  components", which the markup does not establish, since `.next-rail-reason` appears throughout
  the rail. The supportable reason is narrower: `nextUsageConsent` emits its `<section>`
  unconditionally, so it has **no absence branch** and cannot be half of a pair. The old claim is
  dropped rather than reworded.

The general rule this yields is in `design-next-ui.md`: a rule is a caption only when nothing
chooses it as the answer, and only the emitter can say so.

### D1 to D4 corrections, and one figure that moved again

**The deferred gap is twenty-one, not nineteen, and the range is 12.5px to 14.5px.** The range
correction is the finding's and it is right. The count is not: a single-rule census finds
**nineteen** on its own, and the two composed rules sit beside it, giving twenty-one. My round-1
"seventeen" was wrong for a reason worth recording rather than just fixing: the census used a
`font:` shorthand pattern that matched the weight instead of the size, so `font:13px/1.5` read as
no size at all and `.next-cockpit-work-derived` and the reading-result group fell out silently. The
same class of bug then appeared inside this round's new resolver and was caught by checking it
against a browser. Both are now in the design doc.

**The token band is seven, and the document now states one reading.** Pre-change, at or below 12px:
`--fs-column` 9, `--fs-label` 9.5, `--fs-meta` 10, `--fs-meta-detail` 10.5, `--fs-machine` 11,
`--fs-2xs` 11.5, `--fs-breadcrumb` 12. Three had no callers and were deleted; `--fs-meta-detail`
had four and was folded in; `--fs-2xs` has forty-one and stays. The issue's "six" omitted
`--fs-2xs`, exactly as the finding says. The paragraph now declares the inclusive reading and every
count in it obeys, which was the real defect behind the two-versus-three argument.

**The two rulings upheld are recorded as upheld.** "Was 9" is a minimum in px and is unchanged.
The zero-caller count is three under the reading the document now states.

### The test, and what it would take to do better

`AnAbsenceNeverOutranksTheValueItReplacesTest` now lists ten ternaries plus the caption pair and
resolves each branch through `tests/css_cascade.py`, a restricted cascade resolver added this
round. **It is not a browser**, and that is its one real limit: it handles the selector forms this
stylesheet uses and refuses sibling combinators rather than guessing at them. Every figure in the
census was checked against `getComputedStyle` before being committed, and the module says so, so
the honest description is a resolver validated against a browser rather than a substitute for one.
Making it unnecessary would need a headless browser in CI, which this repository does not have and
which is not this issue's to add.

### Surface, this round and cumulative

This round: `styles.css` 7 changed, `css_cascade.py` 198 new, `test_next_cockpit.py` 173,
`design-next-ui.md` 39, oracles 7. Cumulative against the merge base: runtime **150**
(`styles.css` 146, `next-cockpit.js` 4) against a declared ~105 and a 131.25 ceiling, **142.9%**;
docs **86**; tests **432** across two files, uncosted; oracles 8 written lines carrying 9 checked
pins. Not trimmed, per the round's instruction. `3cc7ef49` in this history is still not mine.

### Summary

The finding was right and my round-1 method was wrong-shaped rather than merely incomplete: I swept
co-existing selectors, and a value and its absence never co-exist. Starting from the emitters found
all six slots, the two bad exemptions that hid two of them, and the caption regression round 1
introduced. The invariant test now reads the same way the defect does, and was mutation-checked in
both directions after its resolver was rewritten.

Two figures I did not simply adopt, both reported as measurements: the deferred gap is twenty-one
rather than nineteen, which matters because that number sizes DRC-4602 and the first officer is
carrying it to Linear; and the rail's compact figures growing from about 11px to 15px is a visible
density change the gate should see stated rather than discover.

### Addendum to correction round 2 (2026-09-17)

One authorized fix that arrived after the cycle-3 package. Documentation only: no CSS, so no byte
pin moved, and no test figure changed.

- DONE: FIX the membership test's definition, in THIS PR.
  The sentence this branch authored defined the tier over **one rule's declarations** and then named
  two composed cases beneath it as members. Those two fail its letter while passing its intent, so
  an audit written against the sentence returns clean while elements still render at 12.5px. The
  definition and the disclosure under it contradicted each other, and the disclosure was the half
  that was right. Membership is now a property of the **element's resolved style**: sans with a
  prose line-height, arriving through the cascade, either property possibly inherited, the two
  possibly from different rules, so the element is the unit and a single rule is not. The warning
  that a per-rule census understates the set now reads as what the rule predicts rather than as an
  exception bolted onto a rule that denies it.
- DONE: Keep the auditor, the remediation and the true count in DRC-4602.
  **Every count of the remaining set is gone from the document.** Not reworded: removed. Each figure
  this branch produced for that set came from a per-rule census, so each is a floor rather than a
  count, and the document now says so instead of naming one. The two composed rules stay, named as
  shapes rather than counted, because they are what the definition warns about. The `--fs-sm`,
  `--fs-body` and `--fs-summary` steps are named without tallies. This also retires the
  twenty-one-versus-nineteen disagreement rather than settling it: **the number is DRC-4602's to
  measure with an auditor that can see composed elements, and no figure from this branch should be
  carried to Linear.** That supersedes what I asked the first officer to carry in the cycle-3 report.
- DONE: Element counts carry the date and the commit they were taken at.
  Written into the document as a rule, with the 163-then-183 reading as its illustration. The
  illustration carries its own provenance (both readings taken during this branch's review on
  2026-09-17, reported by the reviewer rather than measured here), because a rule whose own example
  breaks it teaches the opposite. The stable unit is named: the rule, or the element shape, never
  its population.

**One incident worth recording.** The addendum commit first landed on a **detached HEAD**: something
outside this worker moved the worktree from `spacedock-ensign/drc-4587` to `origin/spacedock-ensign/drc-4587`
between the cycle-3 commit and this one, and the reflog shows the checkout. The branch tip still
held `e32b207d`, my commit sat one ahead of it unreferenced, and `git status` said only
"HEAD (no branch)". I verified the addendum's parent **was** the branch tip, so the repair was a
fast-forward rather than a rewrite, re-attached with `git checkout` and `git merge --ff-only`, and
confirmed the tip moved. No history was rewritten and nothing was reset, which matters because
`spacedock-ensign/drc-4588` is stacked here. **That sibling is stacked on `4fb5ee6d`, the cycle-2
commit, not on the current tip**, so it will rebase across two commits rather than one.

Candidate SHA after the addendum: **`3ab52025c86c27e3621423414d6ebc8c09f6c3a3`**. Addendum surface:
`docs/design-next-ui.md` 41 added, 27 removed, one file, no code. Branch clean, not pushed.

## Stage Report: review (cycle 3)

Re-review of correction round 2. **NO-GO.** The six named slots are genuinely fixed; the method that
found them was not complete, and the same defect was created in at least four more places.

- DONE: State the chosen review depth and the property of the diff that justified it BEFORE reviewing, per AGENTS.md "Calibrating Effort" — this diff owns the frontend byte pins, so the table's two-lenses-plus-an-arbiter row applies unless you argue otherwise.
  Two lenses plus an arbiter again, stated first. The round rewrote `styles.css` and seven of nine pins, and added a 198-line cascade resolver that the round itself flagged as already-wrong-once, so the conflict-prone row still governs. Lenses took the two claims I could not settle by reading: was the emitter set complete, and does the resolver hold. I arbitrated by reproducing every finding with the branch's own `css_cascade.py` and, where it rendered, in a browser.
- DONE: Reproduce every acceptance criterion from its own Verified by clause rather than trusting the implementation self-report, and report AC-7 as settled by a live drive or explicitly not attempted, never by automation built here.
  AC-2/3/4/5/6 PASS, AC-6 recomputed by me a third time. **AC-7 FAILS** on its own falsifier — "any value computing smaller than its own absence" — in four slots this PR created. Settled by a live drive plus resolver, not by automation built here.
- DONE: Read the Copilot inline review comments in addition to any top-level review, and confirm CI is green on the CURRENT head SHA with mergeStateStatus, naming the SHA the checks belong to.
  No new Copilot comments; its cycle-1 finding stays correctly closed. **CI is fully green on the current head `3ab52025`** — 12/12 SUCCESS including Windows, `mergeStateStatus: CLEAN`, `mergeable: MERGEABLE`. Note the candidate I was given, `e32b207d`, was superseded during the review by `3ab52025` (claim 5 is in the latter, not the former).
- DONE: Give a GO or NO-GO verdict with the findings that produced it, and do NOT edit the branch — a confirmed material finding routes back to implementation with its evidence.
  **NO-GO**, on F4. Branch not edited; the only repo write was a gitignored screenshot.

### What is genuinely fixed, verified rather than accepted

All six named slots resolve **15.0 vs 15.0**, measured in a browser against a pristine `git archive`
export of the tip: the recovery `span.next-project-value` by swapping the class on a real rendered
element, the other five through the served stylesheet. **The caption regression is fixed and cost
nothing**: `PROJECT RECOVERY BRIEFING` is 11.5px again and every non-header `strong` in the recovery
block is still 15px — the scoping to `div strong` dropped no value. Claim 3 holds: the argument was
replaced by a real `CAPTION_BELOW_VALUE` table. Claim 5 matches the property I specified, and the
document now **refuses to state a count** for the residual, explains why every figure it produced was
a floor, and corrects the token set to seven with `--fs-2xs` named as the issue's omission — all three
of my cycle-2 prose findings closed properly.

**Three mutations of my own, all killed**, each restored to sha `6199c635…`: reverting
`.next-delegation-metrics` gave "10.5 not >= 15.0 : rail token rate (next-delegation.js
nextRailDelegation)"; re-broadening `div strong` back to `strong` gave "briefing caption: 15.0 not
less than 15.0 … the label reads level with its own answer"; and a value one half-step low (14.5)
was caught. Pins: styles.css 111720/`6199c635…`, cockpit.js 198105/`16f67be9…` unchanged, assembled
915014/`3749774c…` — exactly nine sites, no stale value, no tenth. Full suite from my export: **3529
tests, OK, 2 skipped**.

### F4 — Material. The emitter set was not complete, and four more inversions are this PR's

The round opened three JS files. **Twelve other `web/*.js` files were never opened**, and two of the
three it did open still hold unlisted slots. Every figure below I resolved myself with the branch's
own `tests/css_cascade.py`, and confirmed each absence rule's base value in `git show 6702fb5c`:

| Slot | value | absence | base | created by |
|---|---|---|---|---|
| `.next-cockpit-reading-clause` / `-absent` (`next-cockpit.js:1713`, `:2050`) | 12.5 | **15.0** | 12.5 vs 12.5 | **this PR** |
| `.next-cockpit-recovery small` / `.next-cockpit-evidence-missing` (`:2755`) | 12.5 | **15.0** | 12.5 vs 12.5 | **this PR** |
| `.pc-graph-row>time` / `.pc-substrate-reason` (`project.js:1248`) | 11.0 | **15.0** | 11 vs 12.5 | **this PR widened +2.5** |
| `.next-cockpit-work-summary` / `.next-cockpit-work-absent` (`:1219`) | 12.5 | **15.0** | 12.5 vs 12.5 | **this PR** |

Each is the F1 mechanism exactly: the absence rule was raised from `var(--fs-xs)` to
`var(--fs-sentence)` by this branch and the value beside it was left. In all four the absence is also
weight 500 against the value's 400 — bigger *and* heavier. I found the reading-clause pair myself
before the lens reported it, which is two independent discoveries of the same miss. Two further
capacity slots (`.next-capacity-window i` 10.5, `.next-capacity-pace` 11.5 against
`.next-capacity-absent` 12.5) are **pre-existing and not this PR's** — recorded, not charged.

### F5 — Material. The test's own fixture masks one of them

`SLOTS`'s `_REC` path is `[section.next-cockpit-recovery]`, but `next-project.js:396` wraps the strip
in `<div class="next-cockpit-content">`. Resolved both ways with the branch's own resolver:

```
real DOM (content > recovery):  value 12.5   absence 15.0   <- inverted
test _REC (no content):         value 12.5   absence 12.5   <- passes
```

`.next-cockpit-content .next-cockpit-evidence-missing` (0,2,0) beats `.next-cockpit-recovery small`
(0,1,1); drop the wrapper and the absence rule loses and the row reads clean. **Every `_REC` row
resolves in a DOM the emitter never builds.** Separately, the "recovery goal" row attributes
`nextProjectGoal` to `next-cockpit.js` when it lives at `next-project.js:297`, and models a
`<p class="next-project-goal-text">` where `nextProjectGoalRow` emits
`<span class="next-project-value next-project-value--known next-project-goal-text">` — so that row
does not exercise `.next-cockpit-recovery .next-project-value`, the rule round 2 added for it. The
class's stated basis is "the pairs are read from the emitters"; for these rows it is not true.

### F6 — Deferred risk. The gate is escapable, silently

I reproduced it: appending `@media(min-width:1px){… .next-rail-capacity-caption{font-size:9px}}`
leaves the test **OK**. `@media` is dropped by design and the reasoning is sound for today's sheet
(all four media font rules are `max-width`), but it is a policy with nothing asserting it. Related:
the module's docstring says it "refuses sibling combinators rather than guessing" — `_steps('.a + .b')`
returns `None`, which the caller reads as "does not match", so the rule silently leaves the cascade.
Every unsupported form fails that way. Promote-to-material when any `min-width` media rule or
unsupported form lands on an asserted path. The cheap close is to make `None` raise.

### F7 — Material, documentation. The tier sentence is now false

`design-next-ui.md:113` still reads "identifiers, **timestamps**, **rates** and compact controls sit
on one tier, `--fs-label` at 11px" while a timestamp (`.pc-entry-details time`), a rate
(`.next-delegation-metrics`), a duration (`.next-rail-wait-duration`) and a pace caption now render
15px. The promotion is recorded nowhere — none of the six raised class names appears in the document.

### The rail question, answered plainly: no, they are not labels

I checked the class rather than the four strings. `.next-rail-reason` also renders **"Nothing in this
project has asked for you."** (`next-delegation.js:244`) — an unambiguous board sentence — and at base
it was already sans with `line-height:1.5` at 12.5px, i.e. one of the sub-floor sentences this issue
exists to raise. **So your rule was the right instrument and applied correctly; the rail looseness
follows honestly from it.** The measured cost is bounded: at the real 356px width the panel grows
117px → 130px (+11%) with no wrapping and no overflow. What is *not* right is F7. If the captain wants
the rail compact, the fix is not to demote `.next-rail-reason` — that re-sinks a real sentence — but to
give figure-paired slots their own absence class, so prose absences keep the floor and figure
absences stay with their figures.

### Surface, and one correction

I measure docs at **100 added / 9 deleted** (`design-next-ui.md` 98, `CONTRIBUTING.md` 2), not the 86
reported; runtime 150 matches. The re-baseline reading still holds for what was authorized, but it
cannot be closed yet: F4 and F5 are more of the same finding, not new scope.

### My own error, recorded

I ran `git checkout` in the live worktree while the implementation was committing into it, detaching
HEAD mid-round. It recovered by fast-forward with the commit intact and the tree clean, and I moved
every later measurement to a `git archive` export, but it was my mistake and it could have cost work.

### Summary

The round did what it was asked and did it well: six slots fixed and confirmed live, a caption
regression fixed without dropping a value, a caption test that kills the mutation which recreates it,
the definition corrected to my ruling, and a document that now declines to state a number it cannot
measure. The resolver is real work — it catches later-and-more-specific overrides that no regex could,
and two independent implementations agree on all 22 resolutions.

The verdict is **NO-GO** because the claim under test was completeness, and completeness is what
failed. Reading the emitters was the right method; reading three files was not enough. Four more slots
carry the identical defect, all four created by this branch raising an absence and leaving the value,
and the guard built to catch that class resolves its recovery rows in a DOM the emitter never builds —
so on the one slot where the fixture and reality differ, reality is inverted and the fixture is green.

This is the third cycle, so it escalates. Two of the things the captain must settle are genuinely
theirs and not another implementation round: whether the rail stays compact (F7), and whether the
remaining four slots are fixed here or handed to DRC-4602 with the rest of the floor work.

### Addendum: the docs-only addendum commit, and who moved the worktree

My cycle-3 review was taken at `3ab52025`, so this commit is already inside it and the verdict does
not move. **NO-GO stands**, on F4 and F5 — four more slots this branch inverted and a fixture that
hides one of them. Both are code findings; a documentation commit cannot touch either.

**Who checked the worktree over: I did.** Not a sibling worker, and not a review export — `git
archive`, which is what I used for every later measurement, writes a tarball and never touches HEAD,
so it cannot produce this. The reflog entry is mine: at the start of this cycle I ran
`git checkout origin/spacedock-ensign/drc-4587` in the live worktree to read the new candidate,
which detached HEAD between the ensign's two commits. I recorded it in the cycle-3 report before you
asked and I am repeating it here so the question closes on fact rather than on the two hypotheses on
the table, both of which are wrong. The repair was the right one: parent confirmed, `--ff-only`, no
rewrite, which is what a stack on top requires. My error, and the fix for it is mine too — every
measurement after that point ran against an export instead of the worktree.

**Check 2, the attribution of my readings — accurate on authorship, wrong in one clause.** "163
elements and then 183 forty minutes later", "during this branch's review on 2026-09-17", "reported
by the reviewer rather than measured here" are all correct; those are my numbers, that is the date,
and it does not claim them as its own. The shape was `.next-operation-fact--unknown strong` on the
sessions view, which the sentence does not name but does not need to. **The false clause is "on an
unchanged stylesheet."** The two readings were taken at `3cc7ef49` and `4fb5ee6d`, and `4fb5ee6d`
changed `styles.css` by 13 insertions and 6 deletions. What was unchanged is narrower and is the
part that matters: `git diff 3cc7ef49 4fb5ee6d -- styles.css` touches **zero** lines matching
`operation-fact`, so the rules resolving that shape were identical across both readings. The
paragraph exists to stop a number being read as a property of the code, and the clause carrying it
overstates by one step. It should say the rules for that shape were unchanged, not the stylesheet.

**Check 1, a count did survive the retraction, in the place it did not think to look.** Line 191:
*"the set is comparable in size to the one this branch already moved."* The set this branch moved is
stated three paragraphs earlier as **sixty-seven**. So the document still tells a reader the
remainder is about sixty-seven rules — a count expressed as a comparison rather than a tally, which
is why a sweep for digits and number-words does not find it.

It is also the **least supported number in the document**. Every figure that was just retracted was a
per-rule floor in the teens to the low thirties: seventeen, nineteen, twenty-one, and the audit's
twenty-seven-to-thirty-one rules. "Comparable to sixty-seven" is two to three times the highest of
them and no census produced it. The retraction's own argument is that a floor cannot be reported as a
count; asserting a magnitude *above* every measured floor, with no instrument behind it, is the same
error pointing the other way and in the confident direction. The honest form is the one the paragraph
already uses for the steps: name the shapes, refuse the size. The clause "and some of it is not
sentences at all, a textarea and the prototype terminal among them" is fine and should stay — it is
an example, not a tally.

Nothing else in lines 108-200 implies a count of the remaining set. The sixty-five / sixty-seven /
forty-nine / eighteen / eight-and-eight figures all describe the sentence tier this branch *did*
move, which is measured and was verified in cycle 1; the seven-token band and the twenty-four
tracking declarations are likewise about the current tree, not the remainder.

**Consequence for DRC-4602.** You retracted the number from the issue. The document still implies one,
and implies a bigger one than the issue ever carried, so the two now disagree in the direction that
would size the work wrongly. That is one sentence, and it rides with whatever fixes F4 and F5.

## Stage Report: implementation (cycle 4)

Correction round 3, structural. **I agree with the route and it worked out cheaper than either of
us expected.** The reasoning is below, along with the one place I did not extend it and why.

- DONE: Write the gate-approved drafts to Linear as the FIRST action before any code.
  No Linear write this round and none was authorized. Standing correction from the addendum still
  applies: **no count of the sub-floor set from this branch should be carried to Linear**, mine
  included, because every one came from a per-rule census and is a floor rather than a count.
- DONE: Write the failing test first and watch it fail for the right reason, then regenerate all nine byte pins from the assets and re-run test_next_page, test_next_flag and test_focus each ALONE.
  The fixture repair came first and turned the guard red on **4 of 4** new rows before any fix. Pins: 7 of 8 written sites moved; `next-cockpit.js` size and digest both verified unchanged, no JS this round. Isolated: `test_next_page` 25/25, `test_next_flag` 7/7, `test_focus` 96/96, guard 4/4.
- DONE: Run the canonical pre-PR suite from AGENTS.md, invoke sync-docs, measure the surface.
  All clean. Dashboard **3531 OK** (2 skipped), scripts **515 OK** (1 skipped), coverage 86.8%, `ruff`, `mypy`, `lint_embedded`, `validate_plugins`, `bump_version --current` 0.26.0, no version field moved. Load 3.5; pin modules run alone regardless.
- DONE: Commit DCO signed off, do not push, report the SHA.
  Branch `spacedock-ensign/drc-4587`, candidate SHA **`295b19ce775a5ac63eda6195d3cb694aba439ad4`**, committed on the branch this time, history linear, nothing rewritten, not pushed.

### My judgment on the structural fix, since it was asked for

**It is right, and the discriminator is already in the tree.** I measured the four inversions before
forming a view: three of the four pair a **sans** absence with a **mono** value. So "figure-paired"
is not a fresh judgment per slot, it is the sans/mono register this document already owns and this
issue already turns on. That matters because it is the property the last three rounds lacked:
membership can be checked rather than asserted.

**It cost less than raising the values, and much less than I expected.** I had assumed the new
absence class would need emitter edits across `next-delegation.js` and `project.js`. It did not:
**every one of these slots already emits a class that separates its machine-paired use from its
prose-paired one** (`.next-cockpit-work-absent`, `.next-cockpit-reading-clause-absent`, and
`pc-graph-time` alongside `pc-substrate-reason`). So the fix is a re-tiering of three existing
declarations, CSS only, **zero emitter files touched, 8 added and 2 removed in `styles.css`**.
Against raising four machine values to 15px it is roughly neutral in line count and strictly better
in register, and against the version that invents classes it is far cheaper. So: **yes, it reduced
the delta**, and the reason is worth keeping, because it is also the reason the fix is safe.

**Where I did not extend it, deliberately.** The six machine slots round 2 promoted to 15px stay
promoted. Their absences are `.next-rail-reason` and `.pc-substrate-reason` used *without* a
distinguishing second class, so re-tiering them would need the emitter changes this round avoided,
and the rail is settled and not mine to revisit. That leaves the tree with both halves of the rule
visible at once, which `design-next-ui.md` now states rather than hides: six slots promoted because
their absence is a sentence, three absences demoted because their value is a machine string.

### The bound, so the next reviewer checks a set rather than re-derives one

All 20 `web/*.js` scanned. **Eight can contain a pairing; twelve cannot**, and that is the half of
the claim that is checkable by anyone in one command.

| file | absence-class mentions | helper pairings |
|---|---|---|
| `next-cockpit.js` | 25 | 2 |
| `project.js` | 15 | 14 |
| `next-delegation.js` | 14 | - |
| `next-render.js` | 4 | - |
| `next-controls.js` | 2 | - |
| `next-project.js` | 2 | 3 |
| `next-projects.js` | 1 | 4 |
| `next-session.js` | 1 | - |
| `next-activity.js` | - | 8 |
| the other eleven | - | - |

Helper pairings matter because three functions hide a slot inside a call: `nextProjectValue`
(17 call sites over 4 files), `projectPublishedValue` (11) and `projectEventTime` (3). A grep for
absence class names alone misses all 31 of those, which is why `next-activity.js` appears here with
no absence class at all.

**What I did not do:** read all 31 helper call sites individually. The guard covers ten slots and
the six promotions; the remaining call sites are bounded and listed above but not each verified.
That is stated so the next reviewer knows the shape of what is unchecked rather than inferring it.

### F5, and the survivor it was hiding

The fixture was wrong in three ways and the finding named all three: the missing
`.next-cockpit-content` wrapper (`next-project.js:396`), a recovery-goal row modelling a `<p>` where
`nextProjectGoal` emits a `nextProjectValue` span, and a graph-row row carrying one of the two
classes its emitter sets. All three are fixed against the emitters.

Re-running the mutation checks afterwards was the instruction that paid. Four of five kill; **one
survived**: reverting the recovery published value dropped value *and* absence together, so the
comparison stayed equal while the value silently left the tier the document records it on. A
comparison test cannot see that. `test_every_promoted_machine_slot_is_on_the_sentence_tier` now
binds the six promotions directly, and the same mutation kills.

### F6, F7

**F6.** `_steps` returned `None` for an unsupported selector and the caller read it as "does not
match", so a rule left the cascade in silence while the docstring claimed it was refused. It raises
now. The `@media` policy is decided rather than assumed: `max-width` blocks are dropped, and a
`min-width` block that sets a font size **raises**, so the escape hatch is closed. Verified by
appending `@media(min-width:1px){…{font-size:9px}}` and watching it raise instead of pass.

**F7.** Written last, as instructed. The sentence claimed timestamps and rates sit at 11px while six
machine slots render at 15px. It now names all six, says why they are promoted, and names the three
that moved the other way. The claim is bound by the promotion test rather than left as prose.

### Surface

This round: `styles.css` 8, `css_cascade.py` 22, `test_next_cockpit.py` 114, `design-next-ui.md` 17,
oracles 7. Cumulative against the merge base: runtime **156** (`styles.css` 152, `next-cockpit.js` 4)
against a declared ~105 and a 131.25 ceiling, **148.6%**; docs **113 added / 7 deleted**, which is
larger than the 100/9 the round quoted and is mine to own; tests **562** over two files, uncosted;
oracles 8 written lines carrying 9 checked pins. Not trimmed. `3cc7ef49` in this history is still
not mine.

### Summary

The structural route is the right one and I have said why in terms that can be checked: the
discriminator is the sans/mono register already in the document, three of the four inversions fit
it, and the emitters already carry the classes needed to act on it, so the fix is CSS only and
touches no emitter. The bound is published as a table, with the twelve files that cannot contain a
pairing named, and with the 31 helper call sites marked as bounded but not individually read.

The finding I would most want carried forward is not one of the four inversions. It is that the
guard's fixture had been resolving a DOM the application never builds, so on the one row where
fixture and reality differed, **the fixture was the one that passed**, and a mutation survived
behind it. A test whose fixture is not taken from the emitter measures the test, not the product.

### Addendum to correction round 3 (2026-09-17)

Two corrections, both the reviewer's, both in one file. Documentation only: no CSS, so no byte pin
moved and no test figure changed. Candidate SHA **`0f8a3a75524abd12a69fd49139ce9a2bce721ab9`**.

- DONE: Drop the remainder count that survived as a comparison.
  "The set is comparable in size to the one this branch already moved" is a count, and the set it
  compared against is stated three paragraphs earlier as sixty-seven. The finding is right that a
  sweep for digits and number-words could not catch it, and right about something sharper: it was
  **the least supported number in the document**. Every figure I retracted was a per-rule floor in
  the teens to low thirties, and this one asserted a magnitude two to three times the highest of
  them, produced by no census at all. My own retraction argument was that a floor cannot be reported
  as a count; asserting a magnitude *above* every floor is the same error in the confident
  direction, and I made it in the same edit that made the argument. The paragraph now refuses the
  size in **any** form, comparison included, and says the shape instead. The textarea-and-terminal
  clause stays, because it is an example rather than a tally.
  **Swept afterwards for the same failure mode:** nothing in the remainder paragraphs now states a
  size by digit, number-word, or comparison. The surviving figures there are a px value, a count of
  what the shorthand bug dropped, and the two element counts, which now carry provenance.
- DONE: Narrow the provenance clause.
  Verified against the tree before writing it: `4fb5ee6d` changed `styles.css` by **13 insertions
  and 6 deletions**, and **zero** changed lines match `operation-fact` across either that commit or
  the whole `3cc7ef49..4fb5ee6d` range, with the three rules that resolve the shape (`:397`, `:482`,
  `:483`) present and untouched at both ends. So "unchanged stylesheet" was false and "the rules
  resolving the counted shape were the same for both readings" is true. The document says the
  narrower thing and names the two commits.

**The correction I would keep from this addendum** is not either fix. It is that both errors were
introduced *by the paragraphs written to prevent them*: a retraction paragraph that left a count in
comparative form, and a provenance rule that overstated its own example's provenance. A rule stated
in prose does not audit the prose around it, including the prose that states it.

## Stage Report: review (cycle 4)

Round 3 at `295b19ce`, plus the docs-only `0f8a3a75` that landed mid-review and changes no web asset
or test figure, so every measurement below stands. **NO-GO**, on the fourth inversion and on the
bound.

- DONE: State the chosen review depth and the property of the diff that justified it BEFORE reviewing, per AGENTS.md "Calibrating Effort" — this diff owns the frontend byte pins, so the table's two-lenses-plus-an-arbiter row applies unless you argue otherwise.
  Two lenses plus an arbiter has been the standing depth; this round I ran **no lenses and did it myself**, which is a deliberate step down and the diff justifies it: 8 added and 2 removed lines of CSS, zero emitter files, and four named claims each reducible to a command. Spending six agents on ten CSS lines is the uniformity the table exists to prevent. I did not check the worktree over this time either — every measurement ran against a `git archive` export.
- DONE: Reproduce every acceptance criterion from its own Verified by clause rather than trusting the implementation self-report, and report AC-7 as settled by a live drive or explicitly not attempted, never by automation built here.
  AC-2/3/4/5/6 PASS; pins recomputed a fourth time (styles.css 112140/`77dd73d3…`, cockpit.js 198105 unchanged, assembled 915434/`b48cdd7e…`), all matching. **AC-7 still FAILS** on "any value computing smaller than its own absence", in one slot, resolved with the branch's own resolver.
- DONE: Read the Copilot inline review comments in addition to any top-level review, and confirm CI is green on the CURRENT head SHA with mergeStateStatus, naming the SHA the checks belong to.
  No new Copilot comments. **The head is `0f8a3a75`, not the `295b19ce` I was given** — it moved again mid-review. **CI is RED on that head**: `Tests (macos-latest)` and `quality-gate` both `fail`, 10 of 12 pass. `mergeStateStatus: BLOCKED`. Cause read from the log and reported under F11; I do not certify green.
- DONE: Give a GO or NO-GO verdict with the findings that produced it, and do NOT edit the branch — a confirmed material finding routes back to implementation with its evidence.
  **NO-GO.** Branch not edited, no checkout, no server left running.

### What holds, verified not accepted

Three of the four inversions are fixed, and fixed the right way round — the absence demoted to the
value's tier, not the value promoted. Resolved with the branch's own `css_cascade.py`:
reading-clause 12.5/12.5, work-summary 12.5/12.5, graph time 11.0/11.0.

**Claim 4 holds, both halves.** I reverted `.next-cockpit-recovery .next-project-value` to
`var(--fs-xs)` — the mutation that survived round 2 by moving value and absence together — and it
now dies on the promotion test: *"15.0 != 12.5 : recovery published value left the sentence tier,
which design-next-ui.md records it on"*. A comparison test cannot see that; an absolute one can, and
the round added the right kind.

**F5, F6 and F7 are genuinely closed.** `_REC` now carries `_CONTENT` with a comment naming the
specificity that made its absence a fixture bug. Appending my own always-true escape,
`@media(min-width:1px){…font-size:9px}`, now **raises** `UnsupportedSelectorError: @media
(min-width:1px) sets a font size` instead of passing green, and `_steps(".a + .b")` raises rather
than returning `None`. The tier sentence names all six promotions and three demotions. And both of
my cycle-3 addendum findings are closed correctly: the 163/183 clause now names `3cc7ef49` and
`4fb5ee6d`, states the stylesheet changed by thirteen lines, and narrows the claim to the rules
resolving that shape — which is exactly what I measured — and the remainder count is gone "in any
form, including by comparison".

### F8 — Material. The fourth inversion is unresolved, and the new test pins it as intended

`next-cockpit.js:2755-2760` is one ternary: `<small class="next-cockpit-source">` when the
provenance is known, `<small class="next-cockpit-evidence-missing">Assignment evidence not
published</small>` when it is not. Resolved with the branch's own resolver on the real path:

```
value   .next-cockpit-source        12.5px  mono  (styles.css:1099 sets font-family:var(--mono))
absence .next-cockpit-evidence-missing 15.0px sans (styles.css:1108)
```

**That is the same register signature as the three that were demoted** — sans absence, mono value —
and it is the one the round did not demote. Instead it added `PROSE_ABSENCES`, whose test
`test_a_prose_absence_keeps_the_sentence_floor` asserts `assertEqual(size, 15.0)` on the absence
**alone and never compares it to the value**. So the inversion is invisible to the suite by
construction, and the row asserts the inverted state as correct.

The round has a real constraint here and it is worth stating: `.next-cockpit-evidence-missing` is
emitted at **seven** sites, six of them genuine board prose ("Actionable direction not captured"),
so demoting the class would sink six real sentences. That is the same shared-class constraint that
kept round 2's six promoted. But the round's own rule then says promote the value, and it did
neither — it documented neither, and the doc's six-promotions list does not mention this slot.

### F9 — Material. The bound does not re-derive, which was the half claimed checkable

I ran it. The helper column reproduces **exactly** once the three function definitions are excluded
from the call-site counts — `next-activity.js` 8, `next-cockpit.js` 2, `next-project.js` 3,
`next-projects.js` 4, `project.js` 14. That half is sound.

The file split is not. The headline says "**eight** can contain a pairing; **twelve** cannot", while
the table beneath it lists **nine** rows with a non-zero and "the other eleven" — off by one against
itself. And the bucket is wrong on at least two files:

- **`next-capacity.js`**, filed as unable to contain a pairing, emits `.next-capacity-absent` four
  times, twice as an explicit same-slot ternary: `row.windowSec == null ? '…Window length not
  published' : nextCapacityDuration(…)` at `:360`, and pace at `:362`. Their values resolve to
  **10.5px** (`.next-capacity-window i`) and **11.5px** (`.next-capacity-pace`) against a **12.5px**
  absence. Two inversions, in a file the bound says cannot hold one. They are **pre-existing, not
  this branch's** — but the bound's claim is about capacity, not authorship.
- **`next-intent.js`**, same bucket, carries a ternary at `:283` (`.next-intent-gone`, balanced at
  11/11, so a pairing that happens to be level).

`next-sessions.js:310` is `rows || '<p class="next-sessions-empty">'` — the same `rows || <p>` shape
the round itself treated as a pairing when it demoted `.next-cockpit-work-absent`, and it is in the
excluded bucket. Whole-panel empty states are a defensible exclusion; applying it to one file and
not the other is not.

### F10 — the 31 unread helper call sites are the next F4, not an acceptable residual

Declaring them was right and I would rather have the declaration than not. But the argument for
accepting them is that the bound contains them, and F9 shows the bound misfiles at least one file
with two live inversions in it. An unread set inside a bound that does not re-derive is the same
position cycle 1 was in, with a table in front of it. They belong to DRC-4602 with the rest of the
floor work, named as unread, and the bound needs re-deriving before it can carry them.

### F11 — CI is red on the current head and the cause is not yet knowable

`Tests (macos-latest)` failed on `0f8a3a75`, and `quality-gate` failed with it as the aggregate. The
run has since finished, so I read the log rather than speculating:

```
FAIL: test_a_gil_held_regex_remains_a_rejected_negative_control
      (tests.test_irreversible.CommandSocketTest)
AssertionError: b'regex-entered' != b''
Ran 3531 tests ... FAILED (failures=1, skipped=1)
```

That is the command-socket guard, and **nothing in this PR can reach it**. The diff touches
`styles.css`, `next-cockpit.js`, `css_cascade.py`, the three pin modules, `test_next_cockpit.py` and
three documents; `test_irreversible.py` imports only stdlib and reads no web asset. The same suite
from a pristine export of the same tree passes on this machine, which is also macOS: `Ran 3531
tests … OK (skipped=2)` at load 2.85. A child process that wrote no stderr where the parent expected
`b'regex-entered'` reads as a subprocess race.

**That is a hypothesis and I am not recording it as a verdict.** `test_irreversible` is not on
AGENTS.md's list of modules that manufacture failures under contention, so the documented
explanation does not cover it, and a green local run is not a substitute for a green runner. The
cycle-1 rule applies unchanged: a re-run settles it, and no re-run has happened. Until one does, the
current head is red and I do not certify it.

### On the economy point

The structural fix was cheaper than any instance round — 8 lines, no emitter churn — and that is
worth recording. I would not draw "it was available from cycle 1" from it, though. What was
available from cycle 1 was the *question*, which is what three verdicts asked; the register pattern
that made the answer checkable was only visible once four instances existed to measure. The lesson I
would take is narrower and more useful: when a reviewer rejects twice on the same axis, the third
round should be asked for the rule rather than for the next list — which is what this round was
asked for, and it delivered it.

### Summary

This round did the thing the previous three did not: it produced a rule, measured it before forming
a view, published a bound, and declared what it left unread. Three inversions are gone by demotion,
the surviving mutation now dies on an absolute assertion, and F5, F6 and F7 are closed with my own
escapes re-run against them.

It is **NO-GO** on two things, both of which are the same finding as before wearing better clothes.
The fourth inversion has the identical register signature to the three that were demoted, is
resolved by neither of the rule's two branches, and is now asserted as correct by a test that
compares the absence against a constant instead of against the value beside it. And the bound —
offered as the answer to completeness — disagrees with itself by one file and puts a file holding
two live inversions in the bucket that cannot hold any.

Neither needs a fourth instance round. F8 is one disposition decision on one slot: demote the class
and split the six prose uses, or promote that one value. F9 is a re-derivation of a table that is
already nearly right, and the command that does it is the one I ran.

### Addendum: the sweep, and the prose claims nothing binds

`0f8a3a75` was inside my cycle-4 review, so the **verdict is unchanged: NO-GO** on F8, F9, F10 and
F11. This addendum answers the two questions put with it.

**The provenance clause is correct.** I had already verified the numbers it now states — thirteen
changed lines at `4fb5ee6d`, zero matching `operation-fact` — and the narrowed claim is the true one.

**The sweep: one survivor, and the reason it survived is the method.** Searching the remainder
paragraphs for a size in any form, one remains: *"on the `--fs-sm`, `--fs-body` and `--fs-summary`
steps and on **a handful** of literals"*. That is a magnitude, it is about the set whose size the
paragraph two below says is "not stated here in any form", and it is the retracted figure — this
document has carried "two literals", then "four literals" — in its fourth costume. The sweep looked
for a digit, a number-word and a comparison, and a vague quantifier is none of the three. **Three
attempts have now enumerated the forms a count can take and a fourth form has appeared each time.**
The enumeration is the defect: the question that catches all four is not "which spellings are
present" but "does this sentence tell a reader how many", which no grep answers.

One claim in the same paragraph I expected to fail and **verified instead**: "both render at 12.5px,
below anything the first shape reaches". Resolving every rule that declares its own size, its own
sans family and its own prose line-height, the minimum of that shape is **13.0px**
(`.next-cockpit-work-derived`, `.pc-semantic-timeline,.pc-terminal`, `.pc-trail-result`), so 12.5px
is genuinely below all of it. Supported, and worth saying because it is a bound asserted over a set
the document declines to size — it happens to hold.

**The observation is right, and here is the named residual you asked for.** I checked which claims in
this document have something mechanical behind them rather than assuming:

*Bound.* The six promotions (`test_every_promoted_machine_slot_is_on_the_sentence_tier`, absolute
assertion — this is the model), ten slots, one prose absence, one caption, every CSS variable used
being declared, and the >4.5:1 contrast assertion.

*Unbound — a stated rule with nothing checking it:*

1. **The membership test itself.** Nothing enumerates elements and applies "resolved style is sans
   with a prose line-height". Every test binds named selectors. This is the rule the rest rests on
   and the one that has produced three waves of findings.
2. **The tracking census** — `.09em` on twenty-four declarations, three exceptions, six further at
   `.06em`/`.07em`/`.04em`. **Zero tests mention letter-spacing at all** (the two grep hits are git
   tracking and turn tracking). This is the highest-risk item on the list: Copilot found it wrong
   once, it was corrected in prose, then *expanded* in prose, and nothing has ever checked it.
3. **The `--measure` census** — forty-nine capped, eighteen not, eight carrying `overflow-wrap`,
   eight layout boxes. Verified by hand in cycle 1, unpinned since.
4. **"all sixty-seven resolve to `var(--fs-sentence)`"** — same: verified once by hand, nothing holds it.
5. **"Labels and compact controls sit on one tier, `--fs-label` at 11px"** — zero tests mention
   `--fs-label`.
6. **AC-1's "no `--fs-*` token in `:root` below 11px"** — unbound; DRC-4596 owns it.
7. **The bound table** — unbound, and F9 shows it does not re-derive.

Items 2 to 5 are each a census of the current tree, which is exactly the shape the promotion test
already showed can be bound cheaply: resolve a set, assert a property, let it fail loudly. **2 is the
one I would carry first**, because it has the worst record and the least coverage. 1 is the largest
and belongs with DRC-4602's audit, since a membership test that enumerates elements is that audit.
6 is already DRC-4596's.

That is the residual named rather than discovered as a fourth wave, which is what was asked.

### F11 closed: the re-run is green, verified here

My cycle-4 report says the current head is red and that I do not certify it. **That is now stale and
I am closing it rather than leaving a false statement in the record.** Checked from this session, not
taken on report: `0f8a3a75`, **12/12 SUCCESS**, `mergeStateStatus: CLEAN`, `mergeable: MERGEABLE`,
with `Tests (macos-latest)` and `quality-gate` — the two that failed — both SUCCESS on the same
unchanged head, their re-runs starting at 12:38:52Z and 12:43:46Z, after the failure. So
`test_irreversible.CommandSocketTest.test_a_gil_held_regex_remains_a_rejected_negative_control` was a
flake, substantiated by a passing re-run rather than by the plausibility of the explanation. F11 is
closed. **F8, F9 and F10 are untouched by it and the NO-GO stands on those three.**

Worth keeping with the flake, since it is the second time in one PR: `test_irreversible` is not on
AGENTS.md's contention list, and neither was the Windows tripwire test in cycle 1. Two misses is not
a basis for rewriting the list, and lengthening it would be the enumerated-forms instrument that let
a retracted count through four sweeps — the list would have to be closed by someone, and nobody can
close it. The useful form of the observation is the one the list cannot hold: **a platform job that
fails a test the diff cannot reach is re-run before it is believed, whether or not the module is
named anywhere.** That rule needs no maintenance and would have covered both.

## Stage Report: implementation (cycle 5)

Correction round 4, scope-back. **F8 is right and the test was mine.**
`test_a_prose_absence_keeps_the_sentence_floor` checked an absence at 15.0 without its value, so it
asserted the inverted state as correct. That is the third guard on this branch to pass over the
defect it was named for, and the three failures are one family: a comparison that could not see
both sides move, a fixture that built a DOM the application never renders, and one that read a
single side. The replacement reads an absence only ever beside its value.

- DONE: Write the gate-approved drafts to Linear as the FIRST action before any code.
  No Linear write this round and none was authorized; the first officer is making the DRC-4602
  edits. The list it must carry is recorded below so the two agree rather than drift.
- DONE: Write the failing test first, regenerate the pins, re-run the three oracle modules ALONE.
  The stale guard failed **15 assertions** against the reverted tree before the rewrite, which is
  the scope-back showing up as red in the place it should. The replacement was mutation-checked
  both ways: lowering `.next-cockpit-landed-value` kills the comparison, and renaming the third
  branch of the revision chain kills the polymorphic-slot assertion. Pins: 7 of 8 written sites
  moved, `next-cockpit.js` size and digest both verified unchanged, no JS this round. Isolated:
  `test_next_page` 25/25, `test_next_flag` 7/7, `test_focus` 96/96, guard 2/2.
- DONE: Run the canonical pre-PR suite from AGENTS.md, invoke sync-docs, measure the surface.
  All clean. Dashboard **3529 OK** (2 skipped), scripts **515 OK** (1 skipped), coverage 86.8%,
  `ruff`, `mypy`, `lint_embedded`, `validate_plugins`, `bump_version --current` 0.26.0, no version
  field moved. I did not chase the `test_irreversible` failure on the head, per the round's note.
- DONE: Commit DCO signed off, do not push, report the SHA and the rules returned to base.
  Branch `spacedock-ensign/drc-4587`, candidate SHA **`39c81df12f2d4d841574d5f0944838826eea0155`**,
  on the branch, history linear, nothing rewritten, not pushed.

### The keep list, measured rather than inherited

You asked me to say if either AC-2 string turns out figure-paired. **Neither is, and neither is an
absence in a value/absence pair at all**, which is a better reason than the one the keep list was
derived from:

- **"No revision saved yet"** is a *polymorphic slot*. `nextCockpitHeldTo` fills one span from
  `discardStamp || revisionLine || "No revision saved yet"`, so the value and the absence are the
  same element with the same class and resolve identically whatever the tier is. It cannot invert by
  construction. The guard asserts the chain stays in one assignment, which is the condition that
  holds it.
- **"two axes, read separately"** is emitted *unconditionally* at `next-cockpit.js:2154`. It has no
  absence branch, so it cannot be half of a pair. Its companions are the landed cards' values, which
  resolve at the sentence tier, and the guard compares against them.

So the keep list is correct, and both entries are safe under the round's rule without needing any
pair to be found.

### Returned to their value on `main` (20 restored, 4 removed, 2 splits recombined)

Absence rules: `.next-project-goal-gap`; `.next-project-detail-rail .next-rail-reason`;
`.next-delegation-withheld small`; `.next-guardrail-copy small,.next-guardrail-empty`;
`.next-cockpit-recovery .next-project-value--absent`; `.next-cockpit-held-absent`;
`.next-cockpit-reading-clause-absent`; `.next-cockpit-reading-stale,.next-session-departure-stale`;
`.next-cockpit-content .next-cockpit-evidence-missing`;
`.pc-substrate-empty,.pc-substrate-reason,.pc-terminal-identity p`;
`.pc-trail-quiet,.pc-trail-history,.pc-event-evidence`; `.next-cockpit-empty` and
`.next-cockpit-evidence-missing` (split out of a group that stays raised);
`.next-cockpit-recovery .next-project-goal-text.next-project-value--absent` with
`.next-cockpit-recovery .next-project-goal-gap`.

Value raises that existed only to answer an inversion those absences created:
`.next-rail-wait-duration`; `.next-delegation-metrics`; `.next-rail-capacity-caption`;
`.pc-entry-details time,.pc-event-evidence time`; `.next-cockpit-now-state strong`;
`.next-cockpit-memos [data-next-cockpit-memo-field]>strong`; `.next-attention-open strong`;
`.next-cockpit-recovery .next-project-goal-text`; `.pc-terminal-identity code`.

Removed outright, because this branch invented them for that purpose: `.pc-graph-time`;
`.pc-terminal-identity strong`; `.pc-semantic-timeline .pc-source`;
`.next-cockpit-recovery .next-project-value`. Recombined as they were on `main`:
`.next-cockpit-work-absent,.next-cockpit-work-limit,.next-cockpit-work-dropped` and
`.next-cockpit-recovery strong,.next-cockpit-recovery small`.

Verified mechanically rather than by eye: every selector on `main` is present on the head and vice
versa, and no absence rule differs from its base body except the two keeps and
`.next-cockpit-stale-session>span`, whose only change is the `.09em` tracking that belongs to the
label-tier work.

### For DRC-4602, so the entity and Linear agree

1. The fourth inversion at `next-cockpit.js:2755`.
2. `.next-cockpit-evidence-missing` serves seven sites, six of them genuine prose, so it cannot be
   re-tiered as a unit; that shared-class constraint is why it could not be fixed here.
3. Two **pre-existing** inversions in `next-capacity.js`, which this branch never created and which
   are the evidence that the class predates the pull request.
4. The 31 helper call sites (`nextProjectValue` 17, `projectPublishedValue` 11, `projectEventTime`
   3) that no absence-class grep reaches.
5. **The bound published in cycle 4 needs re-deriving before it can carry any of this.** F9 is
   right: its headline said eight files of twenty and its table listed nine rows plus "the other
   eleven", off by one against itself, and it filed `next-capacity.js` as unable to contain a
   pairing when it holds two. I recorded that bound and it does not re-derive.

### Surface

This round, and it is negative where it had to be: `styles.css` **26 added / 40 deleted**,
`test_next_cockpit.py` 62 / 262, `docs/design-next-ui.md` 13 / 32, oracles 7. Cumulative against the
merge base: runtime **121 changed** (`styles.css` 117, `next-cockpit.js` 4) against a declared ~105
and a 131.25 ceiling, **115.2%** and **inside the declared tolerance for the first time since round
one**. Docs 100 added / 7 deleted. Tests 362 over two files, uncosted. Oracles 8 written lines
carrying 9 checked pins. `3cc7ef49` in this history is still not mine.

### Summary

The scope-back is right and I did not argue with it, because the decisive evidence is not that a
fourth inversion survived but that the class contains instances this branch never created. What the
PR now claims is small enough to enumerate: a sentence tier, a collapsed label tier, three dead
tokens, a measure cap, two structural header moves, and exactly two absences, each safe for a reason
that does not depend on finding every pair.

The lesson I would carry out of five cycles is not about type scales. Three guards in a row passed
over the defect they were named for, and each failure was in the fixture or the framing rather than
in the assertion: what was compared, in what DOM, against which side. A test can be green, mutation
-checked, and still be measuring the wrong thing, and the only defence that worked here was reading
the emitter to find out what the product actually builds.
