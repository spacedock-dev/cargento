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
