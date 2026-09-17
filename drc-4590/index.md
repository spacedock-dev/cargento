---
id:
title: "Add a control primitive with one primary action per tab and a disabled state that survives greyscale"
status: review
source: "https://linear.app/recce/issue/DRC-4590/add-a-control-primitive-with-one-primary-action-per-tab-and-a-disabled"
started: 2026-09-17T10:42:56Z
completed: ""
verdict: ""
score: 0.6
worktree: .worktrees/spacedock-ensign-drc-4588
issue: ""
pr: "#362"
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
        - id: gate:drc-4590:triage
          stage: triage
          attempts:
            - id: gate-attempt:drc-4590-triage-1
              briefing:
                id: briefing:drc-4590:triage:attempt-1:revision-1
                digest: sha256:4127aed007a76074a97a696eee95dfe9e01ca24b9d4dec3e1b62f100ce5f0012
                room-ref: ./review/triage/briefing-1
              resolution:
                type: Resolution
                id: resolution:spacedock:drc-4590:triage:1
                briefing: briefing:drc-4590:triage:attempt-1:revision-1
                by: agent:first-officer
                at: "2026-09-17T11:02:29.102184Z"
                decision: approve
                reason: 'Checklist 4 done / 0 skipped / 0 failed; AC-1..AC-8 resolve. Three scope calls are all narrowing rather than widening and each is evidenced: the primary-per-tab criterion reaches one tab of five and is filed out rather than stretched to fit, the no-own-radius criterion is accepted on its enumerated verifier against 24 rules over six corner treatments, and the rename is declined rather than reversing DRC-4561''s shipped ruling and pulling SECURITY.md into a styling change. The stage also corrected the recon''s own contrast figures by recomputing from the shipped tokens, and found two compelled test dependencies by reading the tests rather than the diff, declaring them in the estimate instead of letting them surface as an overrun.'
                conn:
                    quote: I pre-approve all the triage and merge gates, just automate this entire process and do it
                    source: Captain, this session, 2026-09-17
              application:
                target-stage: implementation
                state: consumed
---

[DRC-4590](https://linear.app/recce/issue/DRC-4590/add-a-control-primitive-with-one-primary-action-per-tab-and-a-disabled) — Add a control primitive with one primary action per tab and a disabled state that survives greyscale

Seeded 2026-09-17 from the live Linear read of the Clean and Cogent UI/UX milestone.
Linear owns the current issue body, its relations and its resources; triage fetches them
live and validates them against the tree before anything is built. No triage, approval,
implementation or delivery is claimed here.

## Linear edits made

Nothing has been written to Linear. The two captures below are the pre-edit record; the drafts that
follow them are what `implementation` writes once the gate approves.

### Captured original — DRC-4590 issue body (verbatim, read 2026-09-17)

```markdown
## User value

Anyone arriving on a tab notices this in the first second. Today no control anywhere in the cockpit is marked as the main one, so every tab presents its actions as a flat set and the reader has to infer which matters.

## The Problem

A reader cannot tell what the main action is because the stylesheet has no way to say it. There is no shared button class and no radius token — `grep -c -- "--radius"` returns 0 against 43 literal radius declarations — so every control is an ad-hoc recipe: five corner treatments (0, 3, 6, 9, 999px) and four resting inks across the cockpit's controls.

Because every one is a variation on "faint outlined box or bare text", the system has spent its whole range on the secondary tier and has nothing left to mark one control as the one to press. `--accent` does appear at rest, but only ever to mark a selected or toggled state.

Two specific casualties. `+ set a tripwire`, the sole way to create a tripwire, is given the shared outlined recipe on styles.css:335 and stripped of it on :336 — borderless, unpadded, 10.5px ink3 — so it reads as a third line of prose between two 12.5px sentences, with an invisible 44px hit band around it. And `clear` and `discard everything` carry the same five declarations, so dropping an unsaved draft and deleting every revision look identical.

**Measured**

* `grep -c -- "--radius"` returns 0 against 43 literal radius declarations; there is no shared button class
* Control recipes: `.next-gate` 999px amber (styles.css:68), `.next-notify-button` 3px ink2 (70), `.next-stalled` 3px ink (83), `.next-session-copy` 3px ink3 11.5px (91), `.next-steer button` 6px ink2 10px mono (335), `.next-guardrail-add` borderless ink3 10.5px (336), `.next-guardrail-row` 9px ink2 (343), `.next-cockpit-reading button` square `--line2` (946)
* Every `--accent` occurrence inside a button rule is a focus ring, a hover border, or a selected/toggled state; the cockpit's own selected-tab underline is `--ink2` (styles.css:712), not accent
* styles.css:947 `.next-cockpit-reading button[disabled]{color:var(--ink3);cursor:default}` is the complete disabled rule; the border stays `--line2` at a measured 1.61:1, below the 3:1 non-text bar
* ink3 is already the body ink for 73% of Held to, so a disabled control is drawn in prose ink
* styles.css:865 and :874 give `clear` and `discard everything` the same five declarations, differing only by `padding:0`
* The capture puts "+ set a tripwire" at y=564 between prose at y=525 and y=602 — 39px and 38px apart, against a 44px minimum on an unmarked control
* styles.css:869-872 rules colour out on the discard control: `--clay` reads as an observation, and this is a control

**In the attached screenshot**

1. "+ set a tripwire": borderless 10.5px ink3 prose
2. Five corner radii, four resting inks, no primitive
3. Disabled = one colour step in the body ink
4. Nothing on any tab is marked as the main action

## The Solution

Add `--radius-control:3px`, `--control-bd:var(--ink3)` and `--control-pad:9px 14px` to `:root`, then define two shared classes: `.next-action` (inline-flex, 44px min block size, 1px ink3 border, 3px radius, transparent background, ink text, sentence tier) with `:hover` moving the border to `--accent` and `:focus-visible` an accent outline; and `.next-action--primary` adding an accent border and weight 500.

Use `--ink3` (5.67:1) rather than `--line2` (1.61:1) for the resting border so the box clears the 3:1 non-text bar. Disabled becomes `border-style:dashed; border-color:var(--line2); color:var(--ink3); cursor:not-allowed` — dashed versus solid is the differentiator, because no ink choice can carry it.

Assign exactly one `.next-action--primary` per tab: Now/Course/Decisions "Open this session"; Console the registration-copy control when the bridge is off; Held to "Ask for a reading".

Collapse `.next-notify-button`, `.next-stalled button`, `.next-session-copy`, `.next-steer button`, `.next-usage-switch button`, `.next-guardrail-add` and `.next-cockpit-reading button` onto `.next-action`, keeping only layout-specific declarations.

Give `.next-cockpit-held-discard button` a box and hang a heavier border on `[aria-describedby]`, which is exactly the armed state one click from deleting every revision; rename the per-field `clear` to `drop draft` and update `tests/test_next_cockpit.py:4210`, which pins the literal.

Do not fold `.next-cockpit-tabs button` in — a tab is a selection, not an action. Delete the dead `.next-tabs` rules at styles.css:86-88.

## Acceptance

- [ ] One `--radius-control` token and one `.next-action` class exist; no control rule declares its own radius or resting border
- [ ] Exactly one `.next-action--primary` renders per tab, and neither the steer submit nor the tripwire add control is one
- [ ] A disabled control is distinguishable in greyscale by border style, not by ink alone
- [ ] "+ set a tripwire" renders with a visible box whose boundary matches its 44px hit area
- [ ] "discard everything" is visibly heavier than "clear"/"drop draft", with no hue introduced
- [ ] `tests/test_next_cockpit.py:4210` is updated alongside the label rename
- [ ] The dead `.next-tabs` rules are deleted rather than migrated

---

Complaint **cross-cutting** · tabs: all · severity **major** · effort **L** · blocked by DRC-4587

Raised from user feedback; mechanism and figures established by a measured audit of the live board and the shipped stylesheet.
```

### Captured original — "Clean and Cogent UI/UX" milestone description (verbatim, read 2026-09-17)

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

Contrast computed from the shipped tokens and independently recomputed during triage, matching to the decimal. APCA from the same pairs at the sizes they render at — **audit-only: no APCA implementation, table or fixture exists in the repository, so these figures cannot be reproduced from the tree.** DRC-4596 adds the guardrail that would, and lands after the change the figures justify. Density, ink distribution and control counts read off the live DOM at `127.0.0.1:4553`. Density figures are floors — they were taken on a quiet, unannotated session, and a busy project has more text, not less.

Eleven claims were raised and rejected rather than filed. The two worth knowing: brightening the inks cannot fix C1, and merging the three thin tabs is a route change plus an amendment to NUI-3, not a layout change.
```

### Drafted rewrite — DRC-4590 issue body

Every figure below was measured on the **post-DRC-4587 tree**, branch `spacedock-ensign/drc-4587`
at `3cc7ef49`, not on `main`. DRC-4587 moved the type scale and shifted every line number the
original body cited.

```markdown
## User value

Anyone arriving on a cockpit tab notices this in the first second: no control anywhere on the board
is marked as the main one, so a tab presents its actions as a flat set and the reader infers which
matters. This gives the board one shared control primitive, a disabled state a reader can see
without relying on colour, and a visible box on the one control that is today drawn as prose.

P2 — *what is it doing, and when should I come back?* — move `sharpen`. The promise is kept; the
controls that serve it become legible as controls.

## The problem

The stylesheet has no way to say "this one". There is no shared control class and no radius token:
`grep -c -- "--radius" styles.css` returns 0 against 43 literal `border-radius` declarations. So
every control is its own recipe. A sweep of the stylesheet's resting control rules — a selector
naming a `button`, a `summary`, or a class the JS puts on one, excluding state and `:hover`
variants — finds **24 rules that declare their own radius or resting border**, across **six corner
treatments**: none, 3px, 4px, 6px, 9px and 999px.

Because every one of the 24 is a variation on "faint outlined box" or "bare text", the whole range
is spent on the secondary tier and nothing is left to mark one control as the one to press.
`--accent` never appears at rest on a control — only as a focus ring, a hover border, or a
selected, toggled or copied state.

Two named casualties:

* **`+ set a tripwire`**, the only way to create a tripwire, is given the shared outlined recipe at
  `styles.css:343` and stripped of it at `:344` — `border:0;padding:0`, `--ink3`, a literal 10.5px.
  It renders as a line of prose that happens to be clickable, inside the 44px hit band every
  control inherits from `styles.css:44`. The box is invisible and the target is 44px, so what the
  reader can see and what they can hit do not agree.
* **Disabled is one ink step in the body ink.** `styles.css:955`
  `.next-cockpit-reading button[disabled]{color:var(--ink3);cursor:default}` is the complete rule.
  The border stays `--line2` at 1.61:1 against `--panel`, below the 3:1 non-text bar, and `--ink3`
  is the resting colour of 9 of the 20 `.next-cockpit-held-*` rules — so a disabled control is
  drawn in the ink the prose around it already uses. In greyscale it is indistinguishable.

And `clear` (drop one unsaved box) and `discard everything` (delete every revision) carry the same
five declarations at `styles.css:873` and `:882`, differing only by `padding:0`, so two acts of
very different consequence look identical.

**Measured** — post-DRC-4587 tree, `spacedock-ensign/drc-4587` @ `3cc7ef49`:

* `grep -c -- "--radius" styles.css` → 0. `grep -c "border-radius" styles.css` → 43.
  `grep -c "next-action" styles.css` → 0.
* 24 resting control rules declare their own radius or border; 6 corner treatments; radii
  `{3px, 4px, 6px, 9px, 999px}` plus `border:0`.
* `--accent` at rest on a control: zero occurrences. The cockpit's selected-tab underline is
  `--ink2` (`styles.css:720`), not accent.
* Contrast recomputed from the shipped tokens (`--line2 #403f33`, `--ink3 #9b9484`,
  `--panel #1c1c16`): `--line2` on `--panel` **1.61:1**, `--ink3` on `--panel` **5.67:1**.
* Two disabled rules exist, not one: `styles.css:955` and `styles.css:92`
  (`.next-stalled button:disabled{cursor:wait;color:var(--ink3)}`). The `cursor:wait` there is
  deliberate and must survive.
* `.next-tabs` is dead: zero references across every `.js`, `.py` and `.html` in the repository.
  It survives at five sites in the stylesheet — `:65`, `:72`, `:94`, `:95`, `:96` — and two of
  those are shared selector groups carrying live classes (`.next-header`/`.next-header-right`/
  `.next-tabs-row` at `:65`; `.next-crumb`/`.next-menu button` at `:72`), so the class is removed
  from a selector list rather than by deleting a line range.

## The solution

**One primitive.** Add `--radius-control:3px`, `--control-bd:var(--ink3)` and
`--control-pad:9px 14px` to `:root`. Define `.next-action` — inline-flex, 44px min block size,
1px `--ink3` border, `--radius-control`, transparent background, `--ink` text, sentence tier — with
`:hover` moving the border to `--accent` and `:focus-visible` an accent outline. Define
`.next-action--primary` adding an accent resting border and weight 500. `--ink3` (5.67:1) rather
than `--line2` (1.61:1) for the resting border, so the box clears the 3:1 non-text bar.

**Disabled survives greyscale.** `border-style:dashed`, `border-color:var(--line2)`,
`color:var(--ink3)`, `cursor:not-allowed`. Dashed against solid is the differentiator, because no
ink choice can carry it. `.next-stalled button:disabled` keeps `cursor:wait` as an explicit
override — that control is waiting, not refusing, and collapsing the two loses the distinction.

**Seven rules collapse onto it**, keeping only layout-specific declarations:
`.next-notify-button` (`:78`), `.next-stalled button` (`:91`), `.next-session-copy` (`:99`),
`.next-steer button` and `.next-guardrail-add-input button` (`:343`), `.next-usage-switch button`
(`:418`), `.next-guardrail-add` (`:343`/`:344`, losing its `border:0;padding:0` override) and
`.next-cockpit-reading button` (`:954`). Two constraints: `.next-session-copy` must keep
`position:relative;z-index:1;` as the first declarations of its own rule
(`tests/test_next_sessions.py:453` asserts that prefix), and
`tests/test_next_chrome.py:1104` asserts `background:transparent` inside the
`.next-session-copy{…}` rule — that assertion moves to the primitive in the same PR, and the
DRC-4381 `:focus-visible` gap the same test's comment describes is closed by the collapse, so the
comment is rewritten rather than left standing.

**One primary, where one exists.** `Held to`'s "Ask for a reading" (`next-cockpit.js:2019`) takes
`.next-action--primary`. `Now`, `Course`, `Decisions` and `Console` get none, because they have no
main action to mark — see *What this issue does not do*.

**The irreversible control gets a box.** `.next-cockpit-held-discard button` takes `.next-action`,
and `[aria-describedby]` — exactly the armed state, one press from deleting every revision — takes
a heavier border. No hue: `styles.css:877-880` already rules colour out on this control, because
`--clay` reads as an observation about the session and this is a control. The per-field `clear`
stays bare text, which is what makes the weight difference read.

**Delete the dead `.next-tabs`.** Remove the three `.next-tabs`-only rules at `:94`, `:95`, `:96`,
and remove the class from the two shared selector groups at `:65` and `:72`. Do not fold
`.next-cockpit-tabs button` in — a tab is a selection, not an action.

## What this issue does not do

**It does not invent the four missing controls.** `Course` and `Decisions` emit no `<button>` at
all (`nextProjectChanges`, `nextCockpitCoursePanel`, `nextCockpitCompletedWork`,
`nextCockpitDecisionSummary`, `nextCockpitTimeline`). `Now` emits only navigation cards
(`next-activity.js:38`, `:71`), which are selections on the same reasoning that excludes the tab
strip. `Console`'s only action controls are the steer submit and the tripwire add
(`nextProjectRail` → `nextProjectGuardrails(…, includeSteer = true)` at `next-delegation.js:291`),
and this issue's own acceptance forbids either being a primary. `grep -rn "Open this"` finds two
sites, both `<a>` elements inside prose, neither a per-tab control; `projectTerminalAbsence`
(`project.js:772-798`) renders only `<p>` and `<code>`, so there is no registration-copy control to
promote. Deciding what `Course`'s main action *is* is a product question, and it is filed
separately rather than answered here.

**It does not collapse the remaining control recipes.** Five further action rules declare their own
radius or resting border and are not in this issue's set: `.next-rail-wait-controls button`
(`:321`), `.next-usage-consent-actions button` (`:412`), `.next-session-answer-options button`
(`:662`), `.next-cockpit-recovery>header button` (`:823`) and
`.next-cockpit-conflict-choices button` (`:1062`). Filed separately, on the precedent DRC-4602 set
for DRC-4587's universal clause. Rules deliberately exempt for the life of the primitive, each with
its reason: `.next-gate` (`:76`) and `.next-session-raise` (`:109`) carry `--amber` at rest as a
state signal the neutral primitive would erase, and the second has its own look test-pinned;
`.next-guardrail-row` (`:351`) is a `role="switch"`, a state rather than an act;
`.next-cockpit-tabs button` (`:719`) is a selection; `.next-menu>summary` (`:1074`) and
`.pc-timeline-event>summary` (`:1169`) are disclosures; and `.pc-terminal-open`/`.pc-terminal-bar
button` (`:1140`) and `.pc-graph-filter button` (`:1159`) belong to the legacy project view that
`styles.css:15` records as awaiting the v2 pass.

**It does not rename `clear`.** See *Historical* below.

## Acceptance

<!-- implementation: copy the eight criteria from this entity's `## Acceptance criteria` section
     here verbatim, in the `* **AC-N — offline:** … **Verified by:** … **Falsified by:** …`
     shape DRC-4602 uses on the board. They are not restated here, because a second copy of an
     eight-item list is a copy that goes stale, and this one is machine-read where it lives. -->

---

Complaint **cross-cutting** · tabs: all · severity **major** · effort **L** · blocked by DRC-4587

## Historical — superseded 2026-09-17 at triage

Recorded because the reasoning was sound against the tree it was written on, and a later reader
needs to know it was considered rather than missed.

* **"Exactly one `.next-action--primary` per tab", with Now/Course/Decisions marked "Open this
  session" and Console the registration-copy control.** Three of the five named targets do not
  exist as controls, and the Console target does not exist at all. Restyling cannot satisfy this;
  building it is a feature with its own routing, state and tests. Narrowed to the one target that
  exists and filed separately.
* **"No control rule declares its own radius or resting border", stated universally.** The sweep
  finds 24 such rules. The universal clause was accepted here on its enumerated verifier, exactly
  as DRC-4587's AC-1 was, and the remainder is filed as its own issue on that precedent.
* **Rename the per-field `clear` to `drop draft`, and update `tests/test_next_cockpit.py:4210`.**
  Dropped. DRC-4561 ruled on this collision and the ruling is recorded in three places:
  `next-cockpit.js:2283-2291` ("Labelled `discard everything` and never `clear`… two buttons in one
  block carrying one word is the defect rather than the fix"), `SECURITY.md:1266-1273` ("Naming
  both is the point, because the shorter name is the one printed on the button"), and
  `tests/test_next_cockpit.py:4208-4209`. The defect this issue actually reports is that the two
  controls *look* identical, which the box-versus-bare-text weight difference fixes without
  touching either name. Renaming would reverse a shipped ruling, drag `SECURITY.md` into a styling
  PR, and buy nothing the weight difference does not.
* **"The dead `.next-tabs` rules at styles.css:86-88."** The class survives at five sites, two of
  them shared selector groups with live classes, so a line range would delete live rules.
* **Line numbers throughout the original body** (`:68`, `:70`, `:83`, `:91`, `:335`, `:336`,
  `:343`, `:865`, `:874`, `:946`, `:947`) were read on `main` before DRC-4587. Every one has moved.
* **"ink3 is already the body ink for 73% of Held to."** The denominator was never stated and the
  figure is not reproducible from the tree. Replaced with the recomputable 9 of 20
  `.next-cockpit-held-*` rules.
* **"The capture puts '+ set a tripwire' at y=564 between prose at y=525 and y=602 — 39px and 38px
  apart."** A screenshot measurement, not derivable from the tree, and taken before DRC-4587 moved
  the sentence tier underneath it. Replaced with the reproducible statement: the control declares
  `border:0;padding:0` and inherits the 44px hit band at `styles.css:44`.
* **"Five corner treatments" and "four resting inks."** Six corner treatments; the original missed
  4px at `.pc-terminal-open` and `.pc-timeline-event>summary`.
```

### Drafted milestone correction — "Clean and Cogent UI/UX"

Only the sentence this issue makes false needs to move. In **What is left**, the tail sentence reads
"a control primitive with one primary action per tab"; that clause is now false, because four of the
five tabs have no action to mark. Replace that clause with:

> a control primitive with a primary action on the one tab that has one

and append one sentence to the same paragraph:

> Two issues were split out of the primitive at triage: giving the other four tabs a main action to
> mark, which is a product question rather than a styling one, and the ten control recipes the
> primitive's enumerated set does not reach.

Nothing else in the milestone description is falsified by this issue. The APCA paragraph, the three
foundations and the **Waits on** section are untouched. The milestone's "89% of the characters on
Held to" figure is outside this issue's scope and is not corrected here — it carries the same
undefined-denominator problem as the issue's own 73%, and DRC-4596's guardrail is where a
reproducible version of it belongs.

### Labels to set

`journey:mid-flight` (P2) and `move:sharpen` — both already present on the issue and both correct.
The promise is kept and this makes it more precise, so `docs/promise-map.md` does not change
([the move table](../../promise-map.md#how-work-links-to-a-promise)).

### Follow-up issues for `implementation` to file

Neither is a blocker; both are filed at the same time as the rewrite so the scope reduction is
visible on the board rather than only here.

1. **"Four cockpit tabs have no action to mark, so the primary treatment reaches one of five."**
   Product design plus build. `Course` and `Decisions` emit no control at all, `Now` emits only
   navigation cards, and `Console`'s only two controls are the ones DRC-4590 forbids marking.
   Needs a ruling on what each tab's main action *is* before anything is styled. Blocked by
   DRC-4590. Labels `journey:mid-flight`, `move:extend` — it is a new clause, not a sharpening.
2. **"Five further control recipes still declare their own radius or resting border."** The
   remainder of the 24-rule sweep after DRC-4590's seven and the named exemptions:
   `.next-rail-wait-controls button`, `.next-usage-consent-actions button`,
   `.next-session-answer-options button`, `.next-cockpit-recovery>header button`,
   `.next-cockpit-conflict-choices button`. Same shape as DRC-4602, and for the same reason:
   DRC-4590's AC-1 is accepted on an enumerated verifier, so the gap is scheduled rather than
   implied away. Blocked by DRC-4590. Labels `journey:mid-flight`, `move:sharpen`.

## Acceptance criteria

Every "returns today" figure below was measured on branch `spacedock-ensign/drc-4587` at
`3cc7ef49` — the tree this work lands on — not on `main`.

- **AC-1 — offline:** `:root` declares `--radius-control`, the stylesheet declares one `.next-action` rule that owns the resting box, and none of the seven enumerated rules — `.next-notify-button`, `.next-stalled button`, `.next-session-copy`, `.next-steer button`, `.next-guardrail-add`, `.next-usage-switch button`, `.next-cockpit-reading button` — declares its own `border-radius` or its own `border:1px`. **Verified by:** a test that parses `styles.css`, asserts both new names present, and asserts each of the seven selector bodies free of `border-radius` and of a resting `border:` shorthand; today `grep -c -- "--radius-control"` and `grep -c "next-action"` each return 0 and all seven carry their own recipe. **Falsified by:** a rule kept alongside the primitive — the collapse done by adding `.next-action` to a selector group instead of removing the duplicated declarations, which reads as passing in a grep for the class name.
- **AC-2 — offline:** `Held to` renders exactly one `.next-action--primary`; `Now`, `Course`, `Decisions` and `Console` render none; and neither the steer submit nor the tripwire add control carries the class on any tab. **Verified by:** a node-driven test that renders each of the five cockpit panels and counts `next-action--primary` occurrences, expecting `{held-to: 1, now: 0, course: 0, decisions: 0, console: 0}`, plus a direct assertion that the emitters at `next-controls.js:127` and `:156` do not carry it; today every count is 0. **Falsified by:** a second primary reaching `Held to` through the conflict-settle or discard control, or the count test asserting only the `Held to` total, which would pass while a stray primary sat on `Console`.
- **AC-3 — offline:** A disabled control differs from its enabled self by `border-style`, and `.next-stalled button:disabled` still resolves `cursor:wait`. **Verified by:** asserting `border-style:dashed` in the primitive's disabled rule and `cursor:wait` in the stalled override, with the two rules' specificity ordered so the later wins; today `grep -c "border-style:dashed" styles.css` returns 0 and the only `cursor:not-allowed` in the file is at `:127`. **Falsified by:** the disabled state expressed as `border-color` alone, which greps as a border change and vanishes in greyscale, or the stalled control collapsed onto `not-allowed`, which says "refused" about a control that is waiting.
- **AC-4 — offline:** `+ set a tripwire` resolves a visible 1px border and a block size of 44px, and no longer declares `border:0` or `padding:0`. **Verified by:** asserting the `.next-guardrail-add` rule body carries neither `border:0` nor `padding:0` and that the control inherits `min-block-size:44px` from `styles.css:44`; today `:344` declares both. **Falsified by:** padding restored to the rule at a value that makes the box smaller than the 44px hit band, which leaves the visible boundary and the target disagreeing in the other direction.
- **AC-5 — offline:** `discard everything` carries `.next-action`, its armed state (`[aria-describedby]`) carries a heavier border than its resting state, the per-field `clear` control keeps `border:0`, and no rule in the discard block names `--clay`, `--amber` or `--accent`. **Verified by:** four assertions over the `.next-cockpit-held-discard`/`-field` rule bodies; today the discard and the field controls carry the same five declarations differing only by `padding:0`, and the block names no hue. **Falsified by:** the armed state distinguished by border colour rather than width, which is the hue the comment at `styles.css:877-880` rules out, or `clear` boxed too, which removes the weight difference this criterion exists for.
- **AC-6 — offline:** `.next-tabs` appears nowhere in the stylesheet, and `.next-header`, `.next-header-right`, `.next-tabs-row`, `.next-crumb` and `.next-menu button` each still resolve the declarations they shared with it. **Verified by:** `grep -c '\.next-tabs[^-]' styles.css` returning 0 against 5 today (sites `:65`, `:72`, `:94`, `:95`, `:96`), plus an assertion that the two formerly-shared rule bodies are unchanged. **Falsified by:** the five sites removed as a line range, which deletes the `display:flex` group at `:65` and the border reset at `:72` that four live classes depend on.
- **AC-7 — offline:** Every frontend byte pin equals a value regenerated from the assets. **Verified by:** `test_next_page`, `test_next_flag` and `test_focus` each run alone and green — eight size/digest pairs in `test_next_page.py` (six parts, `styles.css`, the assembled page), the length and digest pair in `test_next_flag.py:67`/`:69`, and the digest at `test_focus.py:1024`; today all of them carry the post-DRC-4587 values, `914_344` / `2165bf68…` assembled and `111_050` / `91a303b2…` for `styles.css`. **Falsified by:** one assembled digest site updated and the other two left, which the Parallel Work section records as the exact failure this suite produces.
- **AC-8 — interactive:** On a live board a reader can tell the disabled reading control from the enabled one, and the tripwire control from the prose around it, with colour removed. **Verified by:** a greyscale capture of `Held to` with the reading control disabled and of the tripwire strip, saved under `docs/screenshots/`, showing the dashed border and the tripwire box. **Falsified by:** a capture taken in colour, where the ink step alone carries the distinction and the criterion cannot fail.

AC-3, AC-4, AC-5 and AC-8 are properties a reader sees. AC-8 is the only interactive one, and no
harness is proposed for it: greyscale legibility is a judgement about perception, and the offline
half (AC-3's `border-style`, AC-4's border and block size) is the mechanism that judgement rests on
rather than a substitute for it.

**AC-1 and AC-2 are accepted on their verifiers, not on their text.** The sweep finds 24 resting
control rules, and four of the five cockpit tabs have no action to mark, so a universal reading of
either would be unsatisfiable by this change. Both are enumerated deliberately, on the precedent
DRC-4602 set for DRC-4587's AC-1, and the remainder of each is filed as its own issue above rather
than implied away.

## Expected surface

Measured against `spacedock-ensign/drc-4587` @ `3cc7ef49`. The oracles are costed separately from
the runtime because they behave differently: the runtime figure is a judgement about the work, the
oracle figure is arithmetic that is either regenerated correctly or wrong.

**Runtime — 7 files, net +9 lines (+20 / −11). Tolerance ±15 lines, ±1 file.**

| File | Edit | Lines |
|---|---|---|
| `web/styles.css` | 1 token line; 5 new rules (`.next-action`, `:hover`, `:focus-visible`, `--primary`, disabled); 7 collapse edits; 2 discard rules; 1 `cursor:wait` override; delete `:94`–`:96`; strip the class from `:65` and `:72` | +18 / −11 |
| `web/next-notify.js` | one class token at `:167` | ±1 |
| `web/next-chrome.js` | one class token at `:656` | ±1 |
| `web/next-boot.js` | class tokens at `:258` and `:315` | ±2 |
| `web/next-controls.js` | class tokens at `:127`, `:154`, `:156` | ±3 |
| `web/next-capacity.js` | one class token at `:170` | ±1 |
| `web/next-cockpit.js` | `.next-action--primary` at `:2019`, `.next-action` at `:2331` | ±2 |

`project.js` is **not** touched — it was in the original `filesTouched` only for the Console
registration-copy control, which does not exist. `SECURITY.md` is **not** touched, because the
`clear` rename is dropped.

**Oracles — 3 files, 19 literal replacements, net 0 lines. Tolerance: zero.** Six part pairs
(`next-boot`, `next-notify`, `next-chrome`, `next-capacity`, `next-controls`, `next-cockpit`), the
`styles.css` pair and the assembled pair in `test_next_page.py`; the length and digest in
`test_next_flag.py`; the digest in `test_focus.py`. Two assembled-length assertions and three
assembled-digest assertions across the three files. Regenerate every one with `hashlib.sha256` over
the bytes and `frontend_page.load_page()`; never patch one textually.

**Tests — 2 files, ~6 tests, ~+120 lines. Tolerance ±3 tests, ±60 lines.** The stylesheet-shape
tests (AC-1, AC-3, AC-4, AC-5, AC-6) belong beside the existing ones in `test_next_page.py`; the
per-tab primary count (AC-2) needs a rendered panel, so it belongs in `test_next_cockpit.py`.

**Compelled, and the reason declared before the work starts** — the DRC-4037 lesson is that the
estimate was not wrong about the work, it was wrong about what the repository's contracts would
demand of it. Two dependencies the issue's `filesTouched` does not name, both found by reading the
tests rather than the diff:

* `tests/test_next_chrome.py:1104` asserts `background:transparent` **inside the
  `.next-session-copy{…}` rule body**. The collapse moves that declaration to the primitive, so the
  assertion moves with it. The same test's comment says the DRC-4381 `:focus-visible` gap is
  "standing"; the collapse closes it, so the comment is rewritten. **+1 file, ~6 lines.**
* `tests/test_next_sessions.py:453` asserts the `.next-session-copy` rule *starts* with
  `position:relative;z-index:1;`. A collapse that keeps layout-specific declarations first
  satisfies it by construction — but it is a prefix assertion, so it binds declaration order and
  not just presence. **0 lines if the constraint is respected; 1 file if it is not.**

**Docs — 1 file, ~+30 lines.** `docs/design-next-ui.md` takes the control-primitive section: the
24-rule sweep, the seven this change collapses, the five handed to the follow-up, and the named
exemptions with their reasons. `sync-docs` runs before the PR opens as usual.

**Total declared: 13 files, ~+160 net lines** — 7 runtime, 3 oracle, 2 test, 1 compelled test, 1
doc. The recon's figure was "95 net runtime LOC across 14 files"; the runtime half is much smaller
than that (+9) and the count is 13 rather than 14, because `project.js` and `SECURITY.md` drop out
and `test_next_chrome.py` comes in.

**Semantics this change may move.** Three, each deliberate: the DRC-4381 `:focus-visible` gap on
`.next-session-copy` closes as a side effect of the collapse (an improvement, but a behaviour
change a reviewer should see named rather than discover); `.next-cockpit-reading button`'s disabled
cursor moves from `default` to `not-allowed`; and `+ set a tripwire` gains a visible box, which
changes the tripwire strip's vertical rhythm and is the one thing in this change a reader will
notice without being told.

**Approach chosen, and the simplest alternative rejected.** Chosen: `.next-action` is a real class
that the JS emitters add, at the cost of editing six JS files and therefore six byte pins.
Rejected: define the primitive as a selector group in `styles.css` alone —
`.next-action,.next-notify-button,.next-stalled button,…{…}` — which touches one file, moves six
figures instead of twelve, and satisfies AC-1's text exactly. It cannot deliver the value: the
point of a primitive is that the *next* control opts in by writing one class, and a selector group
means every new control must be appended to a growing list in the stylesheet, which is precisely
the ad-hoc-recipe drift that produced the 24 rules this issue is filed against. It would also leave
the follow-up guard with nothing to assert against.

## One decision for the captain

Everything above is drafted and needs only approval. One thing is a reversal rather than a
refinement, so it is asked rather than assumed:

**The issue asks to rename the per-field `clear` to `drop draft`. I recommend dropping the
rename.** DRC-4561 ruled on this exact collision and the ruling is recorded in three places
(`next-cockpit.js:2283-2291`, `SECURITY.md:1266-1273`, `tests/test_next_cockpit.py:4208-4209`),
each arguing that naming the two acts differently — `clear` and `discard everything` — *is* the
fix. The defect this issue actually reports is that the two controls look identical, and AC-5's
box-versus-bare-text weight difference fixes that without touching either name. Renaming would
reverse a shipped ruling, pull `SECURITY.md` into a styling PR, and buy nothing the weight
difference does not. If you want the rename anyway, it is one label, one test literal, one code
comment and one `SECURITY.md` paragraph — roughly +25 lines and one more file on the estimate.

## Stage Report: triage

- DONE: Capture the live Linear issue body and the owning milestone description verbatim under `## Linear edits made` as the pre-edit record before drafting anything, and draft the rewrite of each beside it without writing either to Linear.
  Both captured verbatim from `get_issue DRC-4590` and `get_milestone "Clean and Cogent UI/UX"` before any drafting; the rewrite and the milestone correction sit below them. Nothing was written to Linear — `implementation` owns that write.
- DONE: Write the acceptance criteria into `## Acceptance criteria` as bullets shaped `- **AC-N — offline:** {property}. **Verified by:** {…}. **Falsified by:** {…}` (the shape, quoted from the checklist)
  Eight criteria, hyphenated ids, each bold label closing on the line it opens. `status --read … --ac-scan` resolves all eight; a paragraph rewrite would have resolved only the short ones.
- DONE: Declare the expected surface with tolerance, costing the byte-pin oracles separately from the runtime, and measure every figure against the POST-DRC-4587 tree on branch `spacedock-ensign/drc-4587`, not against main.
  Every figure taken in `.worktrees/spacedock-ensign-drc-4587` at `3cc7ef49`. Runtime +9 net across 7 files (±15 lines, ±1 file); oracles costed separately at 19 literal replacements across 3 files with zero tolerance; two compelled test dependencies declared up front.
- DONE: Repair AC2, which the recon showed is a feature request rather than a restyle. Also correct AC7, which names the wrong lines. Decide and record whether the missing controls are in scope or are a separate issue.
  The primary-count criterion narrowed to `Held to` plus a zero-count on the other four; the dead-class criterion rewritten to remove the class from five sites including two shared selector groups. Missing controls ruled **out of scope** and filed as a separate `move:extend` issue.

### Summary

The mechanical half of this issue survived the read and the expensive half did not. Four findings
changed the scope. **The primary-per-tab criterion cannot be satisfied by restyling**: `Course` and `Decisions` emit no
`<button>` at all, `Now` emits only navigation cards, and `Console`'s only two action controls are
the steer submit and the tripwire add, which the criterion itself forbids marking — so a primary
reaches one tab of five, and the other four are a product question filed separately rather than
answered here. **The first criterion's universal clause is unsatisfiable**: a sweep of resting control rules finds
24 that declare their own radius or border across six corner treatments, not the seven the Solution
names, so it is enumerated and accepted on its verifier on the precedent DRC-4602 set for
DRC-4587 — with the five remaining action rules filed and the exempt ones named with reasons.
**The `clear` → `drop draft` rename is dropped**: DRC-4561 ruled on that collision in three places,
and the defect actually reported is that the two controls *look* identical, which the
box-versus-bare-text weight difference fixes without reversing a shipped ruling or pulling
`SECURITY.md` into a styling PR. That one is put to the captain rather than assumed. **AC7's line
range would delete live rules** — `.next-tabs` survives at five sites and two are shared selector
groups carrying `.next-header`, `.next-tabs-row`, `.next-crumb` and `.next-menu button`.

Two figures in the original body were not reproducible and are replaced rather than requoted: the
"73% of Held to" ink share (no denominator; replaced with 9 of 20 `.next-cockpit-held-*` rules) and
the `y=564 … 39px and 38px` capture geometry (a screenshot measurement taken before DRC-4587 moved
the sentence tier; replaced with the tree-derivable `border:0;padding:0` against the 44px band at
`styles.css:44`). The recon's own contrast "correction" was itself the error: recomputing from the
shipped tokens gives `--line2` on `--panel` at **1.61:1** and `--ink3` at **5.67:1**, matching the
issue rather than the recon's 1.60/5.68. Two compelled test dependencies the `filesTouched` list
does not name were found by reading the tests — `test_next_chrome.py:1104` asserts
`background:transparent` inside the `.next-session-copy` rule body, which the collapse moves, and
`test_next_sessions.py:453` binds that rule's declaration *order* by prefix. Both are declared in
the estimate rather than left to surface as an overrun.

## Stage Report: implementation

Built with DRC-4588 on one branch, per the captain's tier-grouping ruling. Candidate **1d847b0f**
on `spacedock-ensign/drc-4588`, rebased onto `main` @ `84d27a53`, PR #362.

- DONE: Write BOTH gate-approved drafts to Linear as the FIRST action before any code, sending each body unwrapped as one line per paragraph, then read back each issue's relation set and report every edge the write created.
  DRC-4590's body written verbatim and unwrapped, with the eight criteria substituted into `## Acceptance` from this entity's own `## Acceptance criteria` in the `* **AC-N — offline:**` shape the comment specified. Milestone correction applied (the primary-action clause plus the split-out sentence), sharing one description with DRC-4588's correction. Labels `journey:mid-flight` and `move:sharpen` already correct, confirmed rather than changed. Follow-ups DRC-4603 and DRC-4604 filed. Edges below.
- DONE: Write the failing test first for each issue and watch it fail for the right reason.
  Seven tests, all watched failing first, then re-verified at final shape by reverting the seven assets to the pre-change base: 7/7 fail there, 7/7 pass on the change. What each proves, and the change that breaks it: `.next-action` is one rule owning the box (adding the class to a selector group instead of removing the duplicated declarations fails it); none of the seven enumerated rules keeps `border-radius` or `border:1px`; the disabled rule is `border-style:dashed` and `.next-stalled button:disabled` still resolves `cursor:wait` (expressing disabled as `border-color` alone fails it, and so does collapsing the stalled control onto `not-allowed`); `.next-guardrail-add` declares neither `border:0` nor `padding:0`; the armed discard carries `border-width` and the discard block names no hue (distinguishing the armed state by colour fails it); `.next-tabs` is absent while its five former co-selectors still resolve their shared declarations (deleting the five sites as a line range fails it); and per-tab primary counts are `{held-to:1, now:0, course:0, decisions:0, console:0}` with the steer submit and tripwire add asserted clean (a page total instead of per-tab passes with a stray primary on Console, which is why it is counted per tab).
- DONE: Regenerate every byte pin your changes move from the assets and re-run test_next_page, test_next_flag and test_focus each ALONE, reporting the pass ratio of each isolated run.
  Regenerated from the assets three times (twice pre-rebase, once after), never patched textually. Isolated after the rebase: test_next_page 31/31, test_next_flag 7/7, test_focus 106/106. Final: styles.css `111_658` / `19c58ec2…`, assembled `918_899` / `c64dcd86…`, across 2 length and 3 digest assertions. Six JS parts moved; `APP_PARTS` moved 0 across the rebase itself.
- DONE: Run the canonical pre-PR suite from AGENTS.md read from that file, invoke sync-docs and commit its updates, then measure the actual surface against the declared estimate.
  All green post-rebase at load average 20: ruff, ruff format, mypy, lint_embedded, validate_plugins, bump_version --current (0.26.0, no version field moved), 3541 + 515 tests, coverage 86.8%. sync-docs added NUI-18 to `docs/design-next-ui.md`, carrying this issue's 24-rule sweep, the enumerated seven, the named exemptions and the rejected selector-group alternative. Surface below.
- DONE: Commit DCO signed off and STOP without pushing and without opening a pull request.
  Done at `2a073801`, rebased to **1d847b0f**. The FO pushed and opened #362; I neither pushed nor opened it.

### Linear relation edges created

**DRC-4590** gained `relatedTo` **DRC-4381**, **DRC-4602** and **DRC-4561**, all from bare tracker
keys in the approved body, and `blocks` **DRC-4603** and **DRC-4604** from the follow-up filings.
`blocks DRC-4595` and `blockedBy DRC-4587` were already there and are unchanged. Its six **DRC-4587**
mentions created no edge, because `blockedBy DRC-4587` already existed: a mention creates a
`relatedTo` only where no relation stands. DRC-4603 carries `blockedBy DRC-4590` and no `relatedTo`;
DRC-4604 carries `blockedBy DRC-4590` and `relatedTo DRC-4602`.

**One serializer loss to report rather than repair**, on this issue's body specifically: the bullet
authored `* **` + a code span + `**, the only way to create a tripwire…` stored with the bold mark
**dropped entirely**. The measured rule covers an emphasis run ending immediately before a code
span; this is the adjacent case, a run that *contains* one, and the serializer either splits it
(`**Delete the dead** `.next-tabs`**.**`) or loses it. Authored correctly and reported, per the
standing instruction that repair provably cannot succeed.

### Surface: what splits, and what does not

The figures in DRC-4588's report are **combined across both issues** and should not be read as
either one's. The branch is 16 files, +720 / −91, net 629, against a combined declared ~324 net.

Wholly attributable, by file:

| Belongs to | Files | Lines |
|---|---|---|
| DRC-4590 alone | `next-boot.js`, `next-capacity.js`, `next-chrome.js`, `next-controls.js`, `next-notify.js`, `test_next_chrome.py`, `test_next_controls.py` | +35 / −13 |
| DRC-4588 alone | `SKILL.md`, `design-reader-state.md` | +2 / −2 |
| Shared | `styles.css`, `next-cockpit.js`, `test_next_cockpit.py`, `test_next_page.py`, `test_next_flag.py`, `test_focus.py`, `design-next-ui.md` | the rest |

So DRC-4590 reaches **14 of the 16 files** against 13 declared. Inside the shared files, a
keyword scan puts roughly 134 of `test_next_page.py`'s 151 additions in this issue's new test class,
42 of `test_next_cockpit.py`'s 344 in its AC-2 test, about 21 of `styles.css`'s 42 additions, and
about 3 of `next-cockpit.js`'s 83. **That scan is a heuristic, not a measurement**, and it is
reported as one: it attributes by matching selector and identifier names, which cannot see a line
that serves both. Three things are jointly caused and not splittable even in principle: the byte
pins (both issues moved the same assets, and the assembled figure is fed by every part), NUI-18
(one heading covering both rulings, because the second is only safe given the first), and the
suite runs. **The honest summary is that DRC-4590's own share is not separable below file
granularity**, and the overrun finding belongs to the pair rather than to either issue.

### What this issue did not build, deliberately

Both universal-sounding criteria are accepted on enumerated verifiers, as triage ruled: AC-1 against
the seven named rules rather than all 24, AC-2 against the one tab that has an action to mark rather
than five. The remainders are **DRC-4604** (five further control recipes) and **DRC-4603** (four
tabs with no action to mark). The `clear` → `drop draft` rename stays dropped. Nothing was promoted.

One finding recorded against DRC-4604 rather than fixed here: resolved through `tests/css_cascade.py`,
`.next-session-copy` renders 11.5px while the prose beside it is 12.5px, because the collapse kept
its `font-size:var(--fs-2xs)`. It reads 11.5px on `main` too, so this branch did not cause it, and
AC-1's verifier cannot see it because it checks `border-radius` and `border:1px` only.

### Summary

The stylesheet now has one way to say "this one". `.next-action` owns the resting box behind a class
a control opts into, seven rules collapse onto it, and the primary treatment marks the single tab
that has an action to mark. Disabled is dashed rather than dimmer, because `--ink3` is the resting
colour of the prose these controls sit in and an ink step alone disappears in greyscale; the stalled
control keeps `cursor:wait` as an explicit override, since it is waiting rather than refusing. The
dead `.next-tabs` class is removed from two shared selector groups rather than by line range, which
is what the criterion as filed would have deleted. The work was built with DRC-4588 on one branch,
so its surface is separable only down to whole files, and that is stated rather than estimated away.

## Stage Report: review

- DONE: State the chosen review depth and the diff property that justified it BEFORE reviewing, per AGENTS.md "Calibrating Effort".
  **Two lenses plus an arbiter**, stated before the first file was read. The justifying property is this issue's: it moves seven JS assets and `styles.css`, so it owns all three frontend byte-pin oracles, and the branch also touches `SKILL.md`. Two of the three named conflict-prone surfaces, and no security, credential or data-loss path — so not full adversarial.
- DONE: Reproduce every acceptance criterion of BOTH issues from its own Verified by clause rather than trusting the implementation self-report, and settle any interactive criterion by a live drive or report it explicitly as not attempted.
  **AC-1:** `:root` carries `--radius-control:3px`, one `.next-action` rule owns the box, and my own sweep of the sheet for rules declaring their own radius or resting `border:1px` returns none of the seven. **AC-2:** reproduced independently across all five panels — `{now:0, course:0, decisions:0, console:0, held-to:1}`; `.next-action` itself reaches 1/1/1/3/3, the extra one on every tab being the shared `.next-notify-button` chrome. **AC-3:** resolved live with `getComputedStyle` rather than by grep — enabled `solid` `rgb(198,224,122)`, disabled `dashed` `rgb(64,63,51)`; `.next-stalled button:disabled` declares only `cursor:wait;color`, and wins on specificity (0,2,1) regardless of order. **AC-4:** live, `+ set a tripwire` resolves `solid 1px rgb(155,148,132)`, `padding 9px 14px`, **`min-block-size:44px`** and a measured box of 177×44. **AC-5:** discard carries `.next-action`, armed `[aria-describedby]` is `border-width:2px` against the resting 1px, `clear` keeps `border:0`, and no rule in the discard block names `--clay`, `--amber` or `--accent`. **AC-6:** `.next-tabs` (not `-row`) appears nowhere in the sheet, and `git grep` on `84d27a53` confirms no JS or HTML ever emitted it — it was dead, so the two rules removed with it were unreachable; the five survivors resolve byte-identically across the sheets. **AC-7:** recomputed from the assets myself — `styles.css` `111_658`/`19c58ec2…`, assembled `918_899`/`c64dcd86…`, found in exactly **2 length and 3 digest** assertions across the three files, matching AGENTS.md's count. **AC-8 settled by a live drive**, not deferred: board on `127.0.0.1:4571` under `grayscale(1)`, captures at `docs/screenshots/2026-09-17-review-pr362-drc4590-ac8-greyscale-disabled-reading-control-dashed.png` and `…-greyscale-console-tripwire-box.jpg` — the dashed refusal and the tripwire box both read with colour removed.
- DONE: For every value-and-absence ternary this diff touches, resolve BOTH branches with tests/css_cascade.py and confirm no absence renders larger than the value it replaces; a test asserting an absence alone is not evidence.
  Seven pairs resolved through `tests/css_cascade.py` on the branch **and** on `84d27a53`. Branch: **0** pairs where the absence outranks the value. Main: **1** — the reading button resolved 12.5px against its own reason paragraph at 15px, an inversion that never fired only because the two never co-existed, and which this change removes by raising the button to the sentence tier. Discard resting vs armed is 15.0/15.0 differing only in border width, where on main the two resolved identically.
- FAILED: Read the Copilot inline review comments as well as any top-level review, confirm CI is green on the CURRENT head SHA with mergeStateStatus, and give a GO or NO-GO verdict without editing the branch.
  CI and the verdict are done; the Copilot half could not be. **No review of any kind exists on #362 and none was requested** — `reviews` empty, `pulls/362/comments` empty, `requested_reviewers: []`, the only comment being the coverage bot. FAILED rather than SKIPPED because the check was unavailable, and requesting one is the FO's call: it blocked the merge on #361. CI is 12/12 `success` read from `1d847b0f8a3b4c300ac293ac17d37b4ee19ed922`'s own `check-runs`, `mergeStateStatus: CLEAN`. **Verdict: NO-GO**, on a finding that belongs to DRC-4588 rather than to this issue. The branch was not edited.
- DONE: Write a `## Stage Report: review` into BOTH entity files, drc-4588 and drc-4590, each covering that issue's share — the advance guard is per entity and one report will block the group.
  This report and the one in `drc-4588/index.md`, each carrying its own issue's criteria and findings.

### Nothing in DRC-4590's share blocks

The blocking finding is DRC-4588's doubled-and-then-false refusal sentence; its report carries it.
Every collapse here resolves correctly. The emitter coverage was checked by enumerating emitters
rather than grepping for the class: all seven collapsed selectors have every element that can match
them carrying `next-action`, including the two `.next-stalled` emitters of which only the retry one
contains a button.

### Filed, not promoted — DRC-4590's share

- **`.next-stalled button:disabled` now renders dashed.** It declares only `cursor:wait;color`, so
  `border-style:dashed` reaches it from the primitive. NUI-18 says dashed means *refusing* and that
  this control is *waiting*, "and collapsing the two loses a distinction a reader acts on" — after
  this change the only surviving distinction is `cursor`, which is mouse-only and absent from a
  screenshot. Created here, visual, transient state.
- **`.next-session-copy` grew while the irreversible `.next-session-raise` did not.** Copy goes
  `4px 7px` → `9px 14px` and `--line2` → `--ink3`; raise is on the exempt list and kept `4px 7px`.
  The prominence half is **plausible rather than confirmed**: the mechanism the comment names —
  filled, on the warn line — still holds, and no criterion binds relative weight. The **stale comment
  is confirmed**: `styles.css:121-127` still says the copy control "never got" the `:focus-visible`
  ring, which `.next-action:focus-visible` now gives it. `test_next_chrome.py`'s comment on the same
  fact was updated on this branch and this one was not.
- **The armed discard's heavier border keys off `warning`, not `armed`.** `next-cockpit.js:2351`.
  The `aria-describedby` half predates; the branch attached a visual state signal to the same
  condition, so a missing armed sentence would leave an armed control unmarked. Low.
- **Two size jumps worth an eyes-on pass rather than a finding.** `.next-notify-button` and
  `.next-usage-switch button` go from ~11–12.5px mono to 15px sans, and the reading button loses
  `background:var(--panel)` so the board's one primary is a 1px accent border plus weight 500 with no
  fill. All three are the stated intent of NUI-18, and `--ink3` at 5.67:1 against `--line2` at 1.61:1
  is a real contrast gain — recorded so they are seen rather than discovered.

### The two enumerations, checked

Both hold. **DRC-4604's five** are the complete remainder: my own sweep of the branch finds only
`.pc-terminal-open,.pc-terminal-bar button` beyond them, and that is `project.js`, which NUI-18 names
as an exemption ("the legacy project view"). **DRC-4603's four** hold for tab-panel action
candidates: `Now`, `Course` and `Decisions` emit no panel control, and Console's are the steer submit
and the tripwire add. The quota-consent pair that also renders on Console is a consent prompt rather
than a tab action, and it is already DRC-4604's.

### Summary

This half of the branch is clean. The primitive collapses the seven it claims, every emitter that can
match them was updated, the dead `.next-tabs` surgery removed nothing live, and all twenty-plus byte
pins recompute to the values the tests carry with the assembled length and digest appearing in
exactly the 2 and 3 places AGENTS.md records. Both universal-sounding criteria are honestly enumerated
and both remainders are accurately filed. The four items above are worth issues, and none of them is
worth a CI round: the NO-GO on #362 is DRC-4588's finding, not this issue's.
