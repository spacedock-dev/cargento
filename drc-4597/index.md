---
id:
title: "Rebuild the scope rail card around the session title"
status: review
source: "https://linear.app/recce/issue/DRC-4597/rebuild-the-scope-rail-card-around-the-session-title"
started: 2026-09-17T11:07:52Z
completed: ""
verdict: ""
score: 0.6
worktree: .worktrees/spacedock-ensign-drc-4592
issue: ""
pr: ""
mod-block: ""
linear-status: "Backlog"
milestone: Clean and Cogent UI/UX
release: ""
promise: "P1"
move: "sharpen"
estimate: ""
reconciled: ""
gates:
    version: 1
    records:
        - id: gate:drc-4597:triage
          stage: triage
          attempts:
            - id: gate-attempt:drc-4597-triage-1
              briefing:
                id: briefing:drc-4597:triage:attempt-1:revision-1
                digest: sha256:3a2d2f42e557a511b2192e864cc04a2dc2fda662b1747e948127f7fbcbb2755d
                room-ref: ./review/triage/briefing-1
              resolution:
                type: Resolution
                id: resolution:spacedock:drc-4597:triage:1
                briefing: briefing:drc-4597:triage:attempt-1:revision-1
                by: agent:first-officer
                at: "2026-09-17T11:17:29.344019Z"
                decision: approve
                reason: 'Checklist 5 done / 0 skipped / 0 failed; AC-1..AC-6 resolve, five offline and one interactive. Two recon-refuted claims are struck and dated into history rather than built: the scope rail is not present at every scroll position (zero sticky rules, align-items:start, hidden below 1280px, gated on more than one session) and the ordering requirement is already shipped with a test binding it, so a literal implementation would have replaced a tested tiebreak with an untested one. A third correction was found at this stage rather than inherited. The captain''s absence-ink ruling is applied as a regression guard on the end state rather than re-decided, which is the correct treatment of a settled ruling, and the entity tells implementation to verify the Read-before-building bullet rather than author it.'
                conn:
                    quote: I pre-approve all the triage and merge gates, just automate this entire process and do it
                    source: Captain, this session, 2026-09-17
              application:
                target-stage: implementation
                state: consumed
---

[DRC-4597](https://linear.app/recce/issue/DRC-4597/rebuild-the-scope-rail-card-around-the-session-title) — Rebuild the scope rail card around the session title

Seeded 2026-09-17 from the live Linear read of the Clean and Cogent UI/UX milestone.
Linear owns the current issue body, its relations and its resources; triage fetches them
live and validates them against the tree before anything is built. No triage, approval,
implementation or delivery is claimed here.

---

## Triage: adversarial read against the tree

Read 2026-09-17 against **`spacedock-ensign/drc-4587` @ a251ca4a** — the post-DRC-4587 tree this
issue's PR (5th of 6) lands on top of, not `main`. Every line number below is post-4587 and moves
again under DRC-4589 (PR 3) and DRC-4593 (PR 3). Re-resolve them at build time; do not quote them.

**Is the problem still real? Yes, in full.** The inversion is unchanged by DRC-4587:

- `styles.css:805` — `.next-scope-cue>strong{color:var(--ink);font:inherit;font-weight:600}` puts
  the literal constant `SESSION` at the brightest ink in the palette. Built at
  `next-cockpit.js:160`, emitted at `:166`.
- `styles.css:793` — `.next-cockpit-scope-name{font:var(--fs-sm) var(--mono)}` = 14px, inheriting
  `--ink2` from the `a` rule at `:795`.
- `styles.css:802`/`:803` — the title `<small>` at `var(--fs-xs)` (12.5px), `:803` overriding the
  colour to `--ink2`. Smaller than the harness name above it. **Two rules, not one.**
- `styles.css:800` — the state at `var(--fs-xs)` `--ink3`, `:801` raising it to `--ink2` when
  working.
- `styles.css:798` — the cue is `grid-column:1/-1` on every row; `:782` still the fixed
  `264px minmax(0,1fr)` shell.
- `styles.css:36` `min-block-size:44px` plus `padding:7px 8px` at `:795` — the vertical padding is
  **14px, not the 12px the issue claims**.

**DRC-4587 did not touch this rail, and that is on the record rather than an oversight.**
`docs/design-next-ui.md:125` states the rule it swept on: *a rule is on the sentence tier when it
sets its text in sans and declares its own prose line-height. Mono is a string a source published.*
Every string in this rail is mono, so none qualified. `:145-151` names `.next-scope-cue` explicitly
as one of six uppercase rules the label sweep did not reach. **So the rail is still on the legacy
scale** — `--fs-2xs` 11.5px, `--fs-xs` 12.5px, `--fs-sm` 14px — and the tokens the original
Solution names (`--fs-body` 13px, "the label tier") are not the tokens this region uses. Settled
below.

### Three claims in the filing are false against the tree

1. **"present on every tab at every scroll position" — false.** `grep -c position:sticky styles.css`
   returns **0**, and `:782` sets `align-items:start`, so the rail scrolls out of view. It is also
   hidden below 1280px (`styles.css:1116 .next-cockpit-scope-tree{display:none}`) and absent
   entirely for single-session projects (`next-project.js:389-391` gates it on
   `group.sessions.length > 1`). The density argument survives without this sentence; the sentence
   does not.
2. **"Order the rendered array by state — non-idle first" is already shipped.**
   `next-cockpit.js:196-201` ranks working(0) → needs_input(1) → idle(2) → other(3), applied at
   `:226-229`, and `tests/test_next_cockpit.py:7115` binds it. The only difference is the
   *tiebreak*: harness then session key, not "last activity descending". Implementing the sentence
   literally would **replace a tested tiebreak with an untested one for no stated user benefit**.
   Struck from the Solution.
3. **`SESSIONS · 29` as the heading text is wrong.** The rail's first `<a>` is the **project** row
   (`next-cockpit.js:239-242`), so a heading reading `SESSIONS` over a list whose first entry is
   the project mislabels the group. The heading is the literal `SCOPE` at `:258`, which is why it
   is correct today. AC-2 is amended around this below.

### Four rulings this triage makes

**R1 — the two tiers are `--fs-sm` (title) and `--fs-2xs` (meta), not `--fs-body`/`--fs-label`.**
This is a *swap inside the rail's existing scale*, not a new step: 14px already renders in this
card, on the harness name, and the change moves it to the title. 11.5px already renders in this
card, on the cue, and the meta inherits it. Rejected: `--fs-body` 13px — `docs/design-next-ui.md:136`
puts that step on the "gap to close next" list DRC-4587 deliberately left alone, and it is a
sans-sentence question, not a mono one. Rejected: `--fs-label` 11px — adopting it here would
part-sweep the six-rule uppercase group DRC-4587 declined to sweep, which is scope widening.
Rejected: `--fs-sentence` 15px — the title is a published machine string, not a sentence.

**R2 — the twin sid moves to the meta line.** `next-cockpit.js:254` appends ` · ${sid}` to the
title on colliding rows, and the block comment at `:230-235` says the key is deliberately not
otherwise on screen. Clipping line 1 to one line would truncate exactly the disambiguator the
mechanism exists for. The sid becomes the last element of the meta line on twin rows only. This
also **repairs an existing defect for free**: `:222` stamps `data-next-withheld` only when the
subtitle is exactly `Session title not published`, so a title-less twin renders the absence string
dressed as data with no marker. With the sid off the title string, the equality holds and the
marker stamps. That is AC-4's own requirement, not a promotion.

**R3 — the builder takes `value` and `meta`, not `label` and `subtitle`.** One `link()` closure
feeds both the project row and the session rows, and their value lives in opposite slots: the
project's value is its label (`cargento`) with the count as meta, a session's value is its subtitle
(the title) with harness/state as meta. Reordering the DOM globally would put the project's count
above its name. Renaming the two parameters and letting each caller say which of its strings is the
value removes the problem rather than special-casing it. ~15 lines.

**R4 — absence keeps `--ink3`. Not reopened.** The captain ruled on 2026-09-17: DRC-4589's AC3 was
amended around this issue, not the other way. AC-4 stands verbatim. By the time this builds,
`styles.css:1089` should carry `font-family:var(--sans)` only, with the colour coming from the
board-wide `[data-next-withheld]{color:var(--ink3)}` at `styles.css:52`. This triage re-checks that
as a regression guard; it does not re-decide it.

### What breaks, and loudly

Both existing assertions fail with a clear message — the recon's "one regex that could fail
quietly" is refuted:

- `tests/test_next_cockpit.py:1947-1954` pins the exact byte sequence
  `<strong class="next-cockpit-scope-name">Codex</strong><span class="next-cockpit-scope-state …">`
  followed by `assertIn("<small>Shape project cockpit</small>")`. Title-first invalidates both.
- `tests/test_next_cockpit.py:7134` matches `/…scope-state[^"]*">([\s\S]*?)<\/span><small/`, which
  requires the state span to immediately precede the `<small>`. On a miss it yields `""` and
  `:7151 assertEqual("working", …)` and `:7156 assertEqual("idle", …)` fail. Loud, not silent.
- `tests/test_next_page.py:553-567` asserts the `.next-scope-cue--project`, `--session`,
  `--session:before` and marker rules by regex. These survive only because the cue rules are
  **kept** — the cue is dropped from session rows in the builder, not deleted from the sheet (it
  still renders on the project row and at ten other call sites in `next-cockpit.js`).

### One surface the original ignores

`nextCockpitScopeLinks` feeds **two** surfaces: `nextCockpitScopeTree` (`:257`, the ≥1280px rail)
and `nextCockpitScopeSwitcher` (`:269`, a `<details>` disclosure that is the only scope control
≤1279px, `styles.css:1113-1120`). Every rule in the `793-803` block is doubled across
`.next-cockpit-scope-tree` and `.next-cockpit-scope-options`. A two-line card designed for a 264px
column must be checked inside the full-width disclosure too, where `nowrap` will rarely clip.

## Linear edits made

**Nothing has been written to Linear. This gate authorizes that write; `implementation` performs
it.** Labels are already correct and need no change: `journey:open-sessions` (P1,
`docs/promise-map.md:327`) and `move:sharpen`.

### Captured original — issue DRC-4597 body, verbatim, 2026-09-17

~~~markdown
## User value

Anyone picking a session from the rail notices this. Today the card leads with the harness and state and puts the session's own title last, so the only distinguishing text is the least prominent.

## The Problem

The scope rail is a fixed 264px column present on every tab at every scroll position, and it is the only region whose text volume does not drop when a tab is quiet — so it, not the panels, is where the density complaint is generated.

Each session renders as five lines at a measured 110-111px pitch: the `— ○ SESSION` cue, the harness name, the state, then a title that wraps to two lines. In a 980px capture that is six visible cards out of 29 sessions, and three of the five lines are byte-identical on all of them. The header already says "29 sessions · 29 quiet", so the repeated `idle` is a third statement of a fact the reader has been given twice above.

The ranking inside the card is inverted: `.next-scope-cue>strong` — the literal word SESSION, constant across all 29 — is full `--ink`, while the title, the only string identifying *which* session this is, is a `<small>` at ink2 12.5px, smaller than the redundant 14px harness name above it.

**Measured**

* styles.css:774 `.next-cockpit-shell{grid-template-columns:264px minmax(0,1fr)}` — fixed column on every tab
* Capture: cue baselines at y=324, 436, 546, 657, 767, 879 — a 110-111px pitch, six cards visible against a header reading "29 sessions"
* styles.css:797 `.next-scope-cue>strong{color:var(--ink);font:inherit;font-weight:600}` on the literal word SESSION, built at next-cockpit.js:160 and emitted at 166
* styles.css:785 `.next-cockpit-scope-name` at `--fs-sm` 14px mono ink2; :795-796 the title small at 12.5px mono ink2; :793 the state at 12.5px mono ink3
* styles.css:790 — the cue is `grid-column:1/-1` on every row, though the group already has a heading
* `#app a{min-block-size:44px}` (styles.css:36) plus 12px of vertical padding puts the achievable card floor nearer 56px than the 48px a four-line-to-two-line collapse suggests
* styles.css:1081 `small[data-next-withheld]{font-family:var(--sans);color:var(--ink3)}` already marks a withheld title with sans

**In the attached screenshot**

1. Six of 29 cards visible at a 110px pitch
2. "Claude" and "idle" repeat on all 29 cards
3. "SESSION" at full ink outranks the session title
4. Title 12.5px ink2, under a 14px harness name

## The Solution

Two lines per card, harness folded into the meta line, kind printed once.

Drop `.next-scope-cue` from session rows and print `SESSIONS · 29` once in `.next-cockpit-scope-heading`, derived from the same array the rows map over. Keep the marker glyph and the left rule, which encode scope kind non-verbally, and move the word SESSION into a visually-hidden span rather than deleting it, since the `<i>` marker is `aria-hidden` and the cue would otherwise lose its accessible text. Note the ○ signals scope *kind*, not state — the state indicator is `.next-project-dot--working` inside the state span, so do not conflate them.

**Line 1** becomes the title alone as the card's value: `--ink`, `--fs-body`, one clipped line with `overflow:hidden;text-overflow:ellipsis;white-space:nowrap` and the full string in `title=`. Keep it in mono: `session.title` is a string the source published, the sheet's convention is mono for published strings, and sans is already what marks the withheld title at styles.css:1081 — switching would collide with the absence marker.

**Line 2** is the meta: `Claude · idle · 37m` at the label tier in ink3, the state word in ink2 when it is not idle.

Where a single harness covers the whole rail, hoist the name into the heading and omit it per card; keep per-card names when the set has more than one member. The rule to beat for clipping is styles.css:791, not 794-795. Order the rendered array by state before mapping — non-idle first, then last activity descending — and keep `min-block-size:44px`. Measure the resulting pitch rather than quoting a target.

## Acceptance

- [ ] A session card renders two lines, with the title as the brightest and largest string in it
- [ ] The word SESSION appears once per group visually and remains in the accessible name of each cue
- [ ] The harness name is hoisted only when every row in the rail shares one harness
- [ ] A withheld title still renders in sans ink3 and is not dressed as data
- [ ] Cards keep `min-block-size:44px` and `aria-current`, and the selection inset marker is unchanged
- [ ] The post-change pitch is measured in the browser and recorded, not projected

---

Complaint **C3** · tabs: chrome (all five) · severity **minor** · effort **S** · blocked by DRC-4587, DRC-4589

Raised from user feedback; mechanism and figures established by a measured audit of the live board and the shipped stylesheet.
~~~

### Drafted rewrite — issue DRC-4597 body

~~~markdown
## User value

Anyone scanning the scope rail notices this, at the moment they are choosing which session to
open. The card leads with the harness and the state and puts the session's own title last and
smallest, so the only string that tells one card from another is the least prominent one in it.

P1 — *Which of my agents are running?* Move: `sharpen`. The rail already lists every session; this
makes the list readable as a list of sessions rather than a column of near-identical blocks.

## The problem

The scope rail is a fixed 264px column, and it is the only region whose text volume does not drop
when a tab goes quiet — so it, not the panels, is where the density complaint is generated.

Each session renders as four grid rows: the `— ○ SESSION` cue, the harness name, the state, then
the title wrapping to two lines. Three of those lines are byte-identical on every card, and the
project row directly above already states the session count, so the repeated `idle` restates a
fact the reader has just been given.

The ranking inside the card is inverted. The literal constant word `SESSION` is set at the
brightest ink in the palette, while the title — the only string identifying *which* session this
is — is a `<small>` at 12.5px `--ink2`, smaller than the 14px harness name above it.

**Measured on `spacedock-ensign/drc-4587` @ a251ca4a.** Line numbers are post-DRC-4587 and move
again under DRC-4589 and DRC-4593; re-resolve them rather than quoting them.

* `styles.css:805` `.next-scope-cue>strong{color:var(--ink);…}` on the constant word `SESSION`,
  built at `next-cockpit.js:160` and emitted at `:166`
* `styles.css:793` `.next-cockpit-scope-name{font:var(--fs-sm) var(--mono)}` — 14px, `--ink2` by
  inheritance from the `a` rule at `:795`
* `styles.css:802` the title `<small>` at `var(--fs-xs)` 12.5px, `:803` overriding it to `--ink2` —
  two rules, not one
* `styles.css:800` the state at 12.5px `--ink3`, `:801` raising it to `--ink2` when working
* `styles.css:798` the cue is `grid-column:1/-1` on every row
* `styles.css:782` the shell is a fixed `264px minmax(0,1fr)`; `styles.css:36` `min-block-size:44px`
  plus the 14px of vertical padding at `:795` sets the card floor
* `styles.css:52` `[data-next-withheld]{color:var(--ink3)}` board-wide, `styles.css:1089` adding the
  sans family for the rail

**The rail is still on the legacy scale.** DRC-4587 swept the sentence tier on the rule at
`docs/design-next-ui.md:125` — sans plus a declared prose line-height — and every string here is
mono, so none qualified. `--fs-2xs` 11.5px, `--fs-xs` 12.5px and `--fs-sm` 14px are what this
region uses.

## The solution

Two lines per card. The title is line 1 and the card's value; everything else is line 2.

**Line 1** is the title alone: `--ink`, `--fs-sm` (14px), mono, one clipped line
(`overflow:hidden;text-overflow:ellipsis;white-space:nowrap`) with the full string in `title=`.
Mono because `session.title` is a string the source published and the sheet's convention is mono
for published strings; sans already marks a *withheld* title, so switching would collide with the
absence marker. The rule to beat for clipping is the `white-space:normal` reset at
`styles.css:799`, not the colour rules.

**Line 2** is the meta — `Claude · idle · 37m` — at `--fs-2xs` in `--ink3`, the state word in
`--ink2` when it is not idle. The age comes from `nextDurationSince(session.last_activity)`, which
already exists in `next-boot.js:435`. Where every row shares one harness, hoist the name into the
group heading and drop it from the meta; keep it per row when the set has more than one member.

**The builder takes a value and a meta, not a label and a subtitle.** One `link()` closure feeds
the project row and the session rows, and their value sits in opposite slots — the project's value
is its label with the count as meta, a session's is its subtitle with harness and state as meta.
Rename the two parameters and let each caller say which of its strings is the value; reordering
the DOM globally would put the project's count above its own name.

Drop `.next-scope-cue` from session rows, keeping the marker glyph and the left rule, which encode
scope kind non-verbally, and move the word `SESSION` into a `.next-visually-hidden` span
(`styles.css:54`, already defined) rather than deleting it, since the `<i>` marker is
`aria-hidden`. Note the ○ signals scope *kind*, not state — the state indicator is
`.next-project-dot--working` inside the state span; do not conflate them. **Keep the heading
literal `SCOPE`**: the rail's first row is the project, so `SESSIONS · N` over it would mislabel
the group, and the project row's own `N sessions` subtitle already carries the count.

On a twin row — same harness, same state, same title — the sid moves to the end of the **meta**
line. Appending it to the title (`next-cockpit.js:254` today) puts the disambiguator inside the
clipped line, where it is the first thing truncated. Moving it also repairs an existing defect:
`:222` stamps `data-next-withheld` only on an exact match with `Session title not published`, so a
title-less twin currently renders the absence dressed as data with no marker.

`nextCockpitScopeLinks` feeds two surfaces — the ≥1280px `.next-cockpit-scope-tree` and the
≤1279px `.next-cockpit-scope-options` disclosure — and every rule is doubled across both. Check
the card in the disclosure as well as in the 264px column.

Measure the resulting pitch rather than quoting a target.

## Acceptance

- [ ] A session row renders two lines, with the title the largest and brightest string in it
- [ ] The scope kind is stated in words once per group, and each session row keeps `SESSION` in
      its accessible name
- [ ] The harness name is hoisted into the heading only when every row shares one harness
- [ ] A withheld title still renders in sans `--ink3` and is not dressed as data, twin rows
      included
- [ ] Cards keep `min-block-size:44px` and `aria-current`, and the selection inset marker is
      unchanged, on both surfaces
- [ ] The post-change pitch is measured in the browser and recorded, not projected

## History

**2026-09-17 — corrected at triage against `spacedock-ensign/drc-4587` @ a251ca4a.** Three claims
in the original filing did not hold and have been removed from the body above; they are kept here
because the reasoning that followed from them is still visible in the audit that raised this issue.

1. *"present on every tab at every scroll position."* False. `grep -c position:sticky styles.css`
   returns 0 and `styles.css:782` sets `align-items:start`, so the rail scrolls away; it is also
   hidden below 1280px and absent for single-session projects
   (`next-project.js:389-391`). The density argument does not depend on it.
2. *"Order the rendered array by state before mapping — non-idle first, then last activity
   descending."* Already shipped at `next-cockpit.js:196-201`/`:227`, bound by
   `tests/test_next_cockpit.py:7115`. Only the tiebreak differs — harness then session key, not
   last activity — and changing it would swap a tested rule for an untested one with no stated
   user benefit.
3. *"Print `SESSIONS · 29` once in `.next-cockpit-scope-heading`."* The rail's first row is the
   project (`next-cockpit.js:239-242`), so that heading mislabels the group. The heading stays
   `SCOPE`.

The original also named `--fs-body` and "the label tier" as the two sizes. Those are the post-4587
board tokens; the rail was not swept and is still on `--fs-2xs`/`--fs-xs`/`--fs-sm`, so the change
reuses that scale rather than part-adopting a new one. Original line citations (`774`, `785`,
`790`, `793`, `795-796`, `797`, `1081`) were pre-4587 and four of them were already off by one or
mis-scoped on `main`.

---

Complaint **C3** · tabs: chrome (all five) · severity **minor** · effort **S** · blocked by
DRC-4587, DRC-4589
~~~

### Captured original — milestone *Clean and Cogent UI/UX* description, verbatim, 2026-09-17

~~~markdown
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
~~~

### Drafted milestone correction — *Clean and Cogent UI/UX*

**No correction required.** The milestone names "the scope rail" in its *What is left* list and
makes no claim this rewrite falsifies. Its *How this was measured* paragraph already flags the
APCA figures as audit-only and unreproducible from the tree, which remains true.

One thing is **owed to this issue by another PR, and must be verified rather than written here.**
Per the captain's ruling of 2026-09-17, DRC-4587's post-merge reconcile writes one bullet under a
`## Read before building` section on this milestone:

    - DRC-4597: absence keeps ink3; styles.css:1089 keeps only the family swap.

That section does not exist on the milestone as read today (2026-09-17, pre-merge).
`implementation` must confirm it is present before building, and escalate rather than author it if
PR 1 landed without it — a missing bullet means the ruling did not reach the record, which is the
failure the ruling was written to prevent.

## Acceptance criteria

- **AC-1 — offline:** A session row in the scope rail renders two lines, and the session title is
  the largest and brightest string in it — `--fs-sm` in `--ink` on line 1, above a meta line at
  `--fs-2xs` in `--ink3`. **Verified by:** a node fixture in `tests/test_next_cockpit.py` calling
  `nextCockpitScopeLinks(group, null)` and asserting the title element precedes the meta element
  inside each session `<a>`, plus regex assertions over `styles.css` in `tests/test_next_page.py`
  that the title rule resolves to `var(--fs-sm)`/`var(--ink)` and the meta rule to
  `var(--fs-2xs)`/`var(--ink3)`; today the builder emits cue → name → state → `<small>` and the
  title rule is `var(--fs-xs)` at `--ink2` (`styles.css:802-803`). **Falsified by:** restoring the
  `<small>` title after the state span, or letting the title and the meta resolve to the same size
  or the same ink.
- **AC-2 — offline:** The scope kind is stated in words exactly once per group — in the project
  row's own `N sessions` subtitle, derived from the same array the session rows map over — and no
  session row prints `SESSION` visibly, while each keeps it in its accessible name through a
  `.next-visually-hidden` span. **Verified by:** a fixture asserting that no session `<a>` contains
  `class="next-scope-cue"`, that each contains a `.next-visually-hidden` span whose text is
  `SESSION`, and that the project row's subtitle equals `${group.sessions.length} sessions`; the
  builder emits a full cue on every row today (`next-cockpit.js:219`). **Falsified by:** deleting
  the hidden span, hard-coding the count, or reinstating the visible per-row cue. *Amended from the
  original AC — "appears once per group visually" cannot mean the heading, because the rail's first
  row is the project and a `SESSIONS` heading would mislabel it.*
- **AC-3 — offline:** The harness name is printed once in the group heading and omitted from every
  meta line when all rows share one harness, and printed per row when they do not. **Verified by:**
  two fixtures over `nextCockpitScopeLinks` — one single-harness group asserting the harness string
  appears once in the rendered nav, one mixed-harness group asserting it appears on each row and
  not in the heading; the heading is the unconditional literal `SCOPE` today
  (`next-cockpit.js:258`). **Falsified by:** hoisting on a mixed-harness group, or keeping the
  per-row harness on a single-harness group.
- **AC-4 — offline:** A session whose title the source did not publish renders that absence in sans
  at `--ink3` and is not dressed as data, **including on a twin row**. **Verified by:** a fixture
  with two title-less sessions sharing a harness and a state, asserting both carry
  `data-next-withheld` — today neither does, because `next-cockpit.js:222` stamps it only on an
  exact match with `Session title not published` while `:254` appends ` · ${sid}` — plus a grep
  asserting exactly one rule in `styles.css` assigns a colour to `[data-next-withheld]` and that it
  resolves to `--ink3`, with the rail rule at `:1089` supplying only `font-family:var(--sans)`.
  **Falsified by:** re-appending the sid to the title string, or a second `[data-next-withheld]`
  colour rule reappearing. *The colour half is DRC-4589's amended AC3 under the captain's ruling of
  2026-09-17; it is re-checked here as a regression guard, not re-decided.*
- **AC-5 — offline:** Every scope link keeps `min-block-size:44px`, the selected row keeps
  `aria-current="page"` with its `box-shadow:inset 2px 0` marker, and both hold on the ≥1280px
  `.next-cockpit-scope-tree` and the ≤1279px `.next-cockpit-scope-options` disclosure.
  **Verified by:** the existing `styles.css:36` and `:797` rules asserted by regex in
  `tests/test_next_page.py` alongside the new rules, plus a fixture calling
  `nextCockpitScopeLinks(group, focus, "switcher")` and asserting the focused row carries
  `aria-current="page"`. **Falsified by:** a `min-block-size` override in the new card rules, or a
  card shape that renders only in the tree and breaks inside the disclosure.
- **AC-6 — interactive:** The post-change card pitch and the number of cards visible in a 980px
  viewport are measured against a live board and recorded on the issue as measurements, not
  projections. **Verified by:** a browser drive of `127.0.0.1:4553` at 980px on a project with more
  than one session, reading the rendered row box heights off the live DOM, with the capture saved
  under `docs/screenshots/` and the figures written into the issue; no offline suite starts a
  server, so nothing in CI produces this. **Falsified by:** a recorded figure that was computed
  from the stylesheet rather than read off the board, or a missing capture.

## Expected surface

Figures are against `spacedock-ensign/drc-4587` @ a251ca4a. This PR is **5th of 6** and lands after
DRC-4588/4590, DRC-4589/4593 and DRC-4591/4594, all of which touch `styles.css` — so the line
numbers above will have moved and **the byte pins below will not be the ones to write.** Recompute
every pin from the assets at build time; never resolve one textually (`AGENTS.md`, Parallel Work).

**Runtime — 2 files, ~58 changed lines, net ~+24.** Tolerance ±15 lines.

| File | Work | Changed / net |
|---|---|---|
| `cargento_runtime/web/next-cockpit.js` | `link()` value/meta rename, hidden `SESSION` span, harness hoist, sid onto the meta, age from `nextDurationSince` | ~44 / ~+20 |
| `cargento_runtime/web/styles.css` | rules at `793`, `794`, `795`, `798`, `799`, `800`, `802`, `803`, `1089`, `1112` plus the `1113` media query | ~14 rules / ~+4 |

**Oracles, costed separately — 9 pinned figures across 3 files.** These are recomputations, not
authored lines, and they are the reason this PR cannot run in parallel with another `web/` change:

- `tests/test_next_page.py` — the `next-cockpit.js` part size and digest (`:682-685`), the
  `styles.css` size and digest (`:703-707`), the assembled size and digest (`:710-714`). Six.
- `tests/test_next_flag.py:67` and `:69` — assembled length and digest. Two.
- `tests/test_focus.py:1024` — assembled digest. One.

Post-4587 baseline, for recognising a stale figure rather than for copying: styles `111_050`,
assembled `914_344`, assembled digest `2165bf68…`, `next-cockpit.js` `198_105` / `16f67be9…`.

**Tests — ~+150 / −14.** Tolerance +60, because AC-2 through AC-5 each want their own fixture and
the switcher surface doubles two of them.

- `tests/test_next_cockpit.py`: rewrite `:1947-1954` (exact DOM byte sequence) and `:7134` (the
  `</span><small` regex) — **rewrite, not patch**, or they stop binding while staying green; add
  ~5 fixtures for AC-1 to AC-5.
- `tests/test_next_page.py`: ~16 new regex assertions for the title, meta and heading rules. The
  existing cue assertions at `:553-567` must keep passing — the cue rules stay in the sheet, only
  the session rows stop emitting one.

**Compelled test surface: none found.** No new module, so no import-graph allowlist is reached; no
new or renamed document, so `test_documentation.py`'s literal-path scan is unaffected; the asset
test pins inks and not font sizes, and the size guardrail that would change that is DRC-4596, which
lands in PR 6 *after* this. Any code comment added must satisfy `RuntimeDecisionCitationsTest` —
a same-line link to an existing heading anchor.

**Semantics that may move:** the DOM order inside every scope link on both surfaces; the project
row's own two-line shape (it shares `.next-cockpit-scope-name` and `small` with the session rows);
the position of the twin sid; and the condition under which `data-next-withheld` is stamped.

**Approach chosen, and the simplest alternative rejected.** Rejected: leave the four-row card and
swap two declarations only — title to `--ink`/`--fs-sm`, `.next-scope-cue>strong` down to
`--ink3`. It is two lines, moves no DOM, rewrites no test, needs no sid ruling, and still fixes the
inversion. It cannot deliver the value: the card stays four rows at the same pitch, the rail still
shows six of 29, and the density complaint this issue was filed from is untouched. The two-line
collapse is what makes the rail scannable; the ink swap alone only makes each unreadable card
better ordered.

## Stage Report: triage

- DONE: Capture the live Linear issue body and the owning milestone description verbatim under `## Linear edits made` as the pre-edit record before drafting anything, and draft the rewrite of each beside it without writing either to Linear.
  Both captured in tilde fences under `## Linear edits made`; issue rewrite and milestone finding drafted beside them. No Linear write was made — `get_issue` and `get_milestone` only.
- DONE: Write the acceptance criteria into `## Acceptance criteria` as bullets shaped `- **AC-1 — offline:** {property}. **Verified by:** {…}. **Falsified by:** {…}`
  Six bullets, hyphenated ids, bold labels closing on the line they open; `status --read drc-4597 --ac-scan` resolves all six (AC-1..AC-6, five offline, one interactive).
- DONE: Declare the expected surface with tolerance, costing the byte-pin oracles separately from the runtime, and measure every figure against the POST-DRC-4587 tree on branch `spacedock-ensign/drc-4587`, not against main.
  `## Expected surface`: runtime ~58 changed lines / net ~+24 across 2 files (±15); oracles costed apart as 9 pinned figures across 3 files; tests ~+150/−14 (+60). All read at `spacedock-ensign/drc-4587` @ a251ca4a.
- DONE: READ AND APPLY THE CAPTAIN RULING in your scope notes: absence keeps --ink3 … Do not re-open it.
  Ruling R4 records it; AC-4 keeps sans `--ink3` verbatim and re-checks the one-colour-rule end state as a regression guard rather than re-deciding it. The milestone section names the `## Read before building` bullet DRC-4587's reconcile owes and tells `implementation` to verify, not author, it.
- DONE: Separately, correct two claims the recon refuted: the scope rail is NOT present at every scroll position … and the ordering requirement … is ALREADY SHIPPED.
  Both struck from the drafted body and demoted to a dated `## History` section, with a third correction found here: `SESSIONS · N` as the heading mislabels a list whose first row is the project. `grep -c position:sticky styles.css` returns 0 on the post-4587 tree; `align-items:start` at `styles.css:782`; rail hidden below 1280px at `:1116` and gated on `group.sessions.length > 1` at `next-project.js:389`.

### Summary

The problem is real and unchanged by DRC-4587, which deliberately did not sweep this rail —
`docs/design-next-ui.md:125` restricts the sentence tier to sans rules with their own prose
line-height, and every string here is mono. That is the triage's main finding, because it means the
tokens the original Solution named (`--fs-body`, "the label tier") are not the tokens this region
uses; ruling R1 keeps the change inside the rail's existing `--fs-sm`/`--fs-2xs` scale, which makes
it a swap rather than a new step.

Three further rulings: the twin sid moves to the meta line (R2), which repairs the withheld-title
marker that `next-cockpit.js:222` currently misses on twin rows and is therefore AC-4's own
requirement rather than a promotion; the builder takes a `value` and a `meta` instead of a `label`
and a `subtitle` (R3), because the project row and the session rows hold their value in opposite
slots and a global DOM reorder would put the project's count above its name; and the absence ink is
not reopened (R4).

Two existing tests break, both loudly — `test_next_cockpit.py:1947-1954` pins the exact DOM byte
sequence and `:7134` requires the state span to abut the `<small>`, yielding `""` into an
`assertEqual("working", …)`. They need rewriting, not patching. The nine byte-pin figures recorded
here are a post-4587 baseline for spotting a stale number, not values to write: three more `web/`
PRs land between this triage and this build.

## Stage Report: implementation

- DONE: Built on the shared group branch, not its own.
  One of three in the tier-5 group (with DRC-4592 and DRC-4598); the full checklist report lives on
  `drc-4592/index.md`. Branch `spacedock-ensign/drc-4592`, candidate `43a8e9ba`.
- DONE: Gate-approved issue body written to Linear as the first action.
  Written unwrapped. Labels `journey:open-sessions` and `move:sharpen` already correct; no milestone
  edit from this issue, as its triage ruled. Relation edge created: **`relatedTo` DRC-4593**, read
  back after the write. Two emphasis runs containing a code span lost their mark at the boundary
  (`**Measured on** \`spacedock-ensign/drc-4587\``, `**Keep the heading literal** \`SCOPE\``) and one
  in the History list. Reported, not repaired.
- DONE: AC-1 to AC-5 satisfied offline; AC-6 is interactive and is NOT done.
  Five new cases in `CockpitScopeRailCardTest`, each red first. AC-6 asks for the post-change card
  pitch measured against a live board at 980px with a capture under `docs/screenshots/`. No offline
  suite starts a server and this stage's ceremony is commit-and-stop, so it is outstanding and owed
  before the issue closes. Named here rather than quietly marked done.
- DONE: R4 applied, not reopened. The withheld title keeps sans `--ink3`.
  Per the captain's ruling of 2026-09-17. The rail rule is now `font-family:var(--sans)` alone and
  the board-wide `[data-next-withheld]{color:var(--ink3)}` is the only rule in the sheet that
  colours a withheld value; a test asserts that count is exactly one, and adding a second colour
  there was one of the twelve mutations, killed.
- DONE: The `## Read before building` bullet this issue is owed EXISTS, and matches what was built.
  **Corrected 2026-09-17 after the first officer's reply; my first report of this item was wrong
  twice.** It is a comment on the milestone (`38cca5e4`, posted 11:18:20Z), not a section of the
  description, and I read only the description: `get_milestone` returns no comments, so an absence
  there is not an absence. It was also not blocked on PR 1, which merged as `84d27a53` at 13:05:03Z
  under PR #361; DRC-4587's state history shows `Ready for Review` ending at that exact timestamp,
  and my read of it as still open was a few minutes stale.
  Read now and checked against the build rather than taken on report. The bullet's falsifiable end
  state is "exactly one rule in the sheet assigns a colour to `[data-next-withheld]`, and `:1081`
  keeps only its family swap", which is precisely what this change lands and what
  `test_a_withheld_title_is_marked_on_twin_rows_too` asserts: the rail rule reduced to
  `font-family:var(--sans)`, the board-wide rule left as the only colour, and the count pinned at
  one. Adding a second colour rule there was one of the twelve planted mutations, killed. The
  bullet also carries the two-rules-not-one finding and the captain's ruling verbatim; nothing in
  it was re-opened.
  **Lesson for the next worker on this milestone:** contract notes on this board live in a milestone
  COMMENT, because `save_milestone` has no patch operation and resends the whole description.
  Check `list_comments` with the milestone id, not the description alone.

### Summary

The card is two lines: the title alone on line 1 at `--fs-sm` in `--ink`, clipped with the whole
string in `title=`, and harness, state, age and (on a twin) the sid on line 2 at `--fs-2xs` in
`--ink3`. R1 through R4 all applied as ruled. The builder now takes a value and a meta, which is
what lets the project row keep its name above its count while a session row puts its title above its
harness.

Two things worth a reviewer's attention. Moving the sid to the meta line repaired the
withheld-title marker for free, as R2 predicted: `data-next-withheld` is stamped on an exact match,
and a title-less twin never matched while the sid was appended. And `data-scope-owner` had to be
restored onto the `<a>` when the session cue that used to carry it left the card; two existing tests
caught that, which is the reason the anchor carries it now instead.

The two tests triage said would break both broke loudly and were rewritten rather than patched: the
exact DOM byte sequence, and the regex that required the state span to abut a `<small>` and would
otherwise have yielded `""` into an `assertEqual`.
