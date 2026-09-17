---
id:
title: "Reorder Held to so its purpose and its inputs come before the caveats"
status: triage
source: "https://linear.app/recce/issue/DRC-4594/reorder-held-to-so-its-purpose-and-its-inputs-come-before-the-caveats"
started: 2026-09-17T10:47:44Z
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
        - id: gate:drc-4594:triage
          stage: triage
          attempts:
            - id: gate-attempt:drc-4594-triage-1
              briefing:
                id: briefing:drc-4594:triage:attempt-1:revision-1
                digest: sha256:6aaaf381bea6b6871b95e31f6f6bca13d022a8f34d6daee336b942a1fac70e79
                room-ref: ./review/triage/briefing-1
---

[DRC-4594](https://linear.app/recce/issue/DRC-4594/reorder-held-to-so-its-purpose-and-its-inputs-come-before-the-caveats) — Reorder Held to so its purpose and its inputs come before the caveats

Seeded 2026-09-17 from the live Linear read of the Clean and Cogent UI/UX milestone.
Linear owns the current issue body, its relations and its resources; triage fetches them
live and validates them against the tree before anything is built. No triage, approval,
implementation or delivery is claimed here.

---

# Triage — DRC-4594 (2026-09-17)

Measured against branch `spacedock-ensign/drc-4587` @ `3cc7ef49` (the post-DRC-4587 tree), not
against `main`. DRC-4587 moves the type scale underneath every pixel figure this issue was filed
with, so figures taken on `main` are already stale and are demoted to history below rather than
restated.

## User value brief

A reader who opens `Held to` for the first time — mid-flight, with a session running and a
question about whether it is still on task — meets what the tab cannot do before what it is for,
and so never reaches the two boxes that are the point. Putting one sentence of purpose above the
caveats, and the reading above the record of what the session did, is what makes the tab legible
on first sight.

Promise [P2 — "What is it doing, and when should I come back?"](../promise-map.md#how-work-links-to-a-promise);
move `sharpen`: the promise is already kept, and this makes the surface behind it precise. No
promise text changes, which is what `sharpen` asserts.

**User-visible property:** AC-1, AC-2 and AC-3 below are all things a user sees on first sight of the
tab. The move is not `none`, so no "nobody sees this" sentence is owed.

### Labels to set

`journey:mid-flight` and `move:sharpen` are **already set on the live issue**. `implementation`
sets nothing; it writes the body only.

## Linear edits made

**Nothing has been written to Linear.** This section is the pre-edit record and the drafts. The
gate authorizes the write; `implementation` performs it as its first action.

### Captured original — issue DRC-4594

Read live 2026-09-17. `updatedAt: 2026-09-17T06:37:37.583Z`, status `Backlog`, priority High,
labels `move:sharpen`, `journey:mid-flight`, `discovered-by-agent`, `Design`, milestone
`Clean and Cogent UI/UX`, blocked by DRC-4587, DRC-4588, DRC-4589, DRC-4591. Verbatim body:

```markdown
## User value

A reader opening Held to for the first time notices this immediately. Today the tab leads with what it cannot do and buries what it is for, so the reader never reaches the two boxes that are the point.

## The Problem

Concede the hard part first: a tab where you type a brief, ask the board to read a session against it, and are guaranteed it will never tell the agent anything is a concept most users have not met, and no layout makes a reader infer it. What styling did do is put the disclaimers before the idea.

The panel opens with its two textareas, immediately follows them with a 48-word paragraph whose 42 middle words explain why this session cannot be raised, then runs four consecutive sections that each report that nothing is here, before reaching COUNTS — whose caption's whole job is to say the five numbers above do not relate.

Nothing in the WHAT YOU ASKED FOR block says what typing buys. The tab does answer it once, four sections down, inside a CLI instruction. The five count labels spend 32 words, and two of them restate the uppercase section headings directly above them. "Held to" is itself a verb fragment with no object.

**Measured**

* Section order in the capture: WHAT YOU ASKED FOR, the re-entry paragraph, OBSERVED RECORD, READING, DEPARTURES RAISED TO YOU (split in two), COUNTS, HOW IT LANDED
* The re-entry paragraph concatenates three independently computed strings into one `<p>` at next-cockpit.js:2281: a 6-word link sentence, a 32-word raise-unavailable sentence, a 10-word resume clause
* Its two lines sit \~28px apart against \~18-20px elsewhere on the tab — the only prose paragraph containing an inline anchor; `#app a` is `display:inline-flex;align-items:center` (styles.css:37)
* Four consecutive sections read "No entry in the observed record names this session", "Nothing has been typed…", "No reading has been made at your request", "Nothing watches for a departure on its own"
* The five COUNTS labels total 32 words; the first two restate FROM THE READING YOU ASKED FOR (next-cockpit.js:1922) and FROM THE CHECKS RUN WHILE YOU WERE AWAY (:1813)
* "your words" (next-cockpit.js:1035, 10px mono) restates the TYPED GOAL label above it and the placeholder beside it
* Held to is 974px, the largest container in the cockpit, at 91 words per control

**In the attached screenshot**

1. Inputs at y=145; \~300 words of caveat follow
2. Re-entry: 48 words, 42 about what cannot be done
3. Four sections in a row report that nothing is here
4. Five count labels spend 32 words; two restate headings

## The Solution

Add a lede as the first child of `.next-cockpit-held`, at the sentence tier in full ink, worded to what the board actually does — a reading happens when the reader asks for one, and nothing watches on its own:

> "Type what you were after. Ask for a reading and Cargento lists where this session went elsewhere. It never tells the agent anything — steering stays yours."

Do not ship any wording implying an automatic check; the unasked lane is off by default and this same tab tells the reader to restart with a flag.

Reorder to **WHAT YOU ASKED FOR → READING → DEPARTURES RAISED TO YOU → COUNTS → HOW IT LANDED → OBSERVED RECORD.**

Split the re-entry paragraph into a control plus two labelled rows, available path first: the anchor on its own line as a primary action (keeping `data-next-focus="cockpit-held-reentry"`, a managed focus lane per `docs/design-reader-state.md`), then a `Re-entry` row and a `Raise` row, with the tmux/platform sentence moved verbatim into a disclosure. Lifting the anchor out of the `<p>` also fixes the leading inflation.

Delete the "your words" sub-label. Strip the restated qualifier from each count label ("Departures in the reading you asked for" → "In the reading you asked for") and group the five rows under mono DEPARTURES and RAISES sub-labels; values and their null-to-"not published" branch untouched.

## Acceptance

- [ ] A reader meets one sentence of what the tab is for before any caveat, and that sentence does not claim an automatic reading
- [ ] Section order places READING and DEPARTURES above COUNTS and HOW IT LANDED, with OBSERVED RECORD last
- [ ] The re-entry block leads with the action; the raise limitation and its platform explanation both survive, one of them behind a disclosure
- [ ] `data-next-focus="cockpit-held-reentry"` survives the restructure and focus is not lost on redraw
- [ ] Count labels drop the restated section qualifier; every `line()` value argument and the single-pass derivation are unchanged
- [ ] The "your words" sub-label and its rule are gone

---

Complaint **C4** · tabs: held-to · severity **major** · effort **L** · blocked by <issue id="f85f4e54-7342-4ca5-89d0-d2062c634b0f" href="https://linear.app/recce/issue/DRC-4587/raise-board-sentences-to-a-15px-tier-and-collapse-six-sub-12px-tokens">DRC-4587</issue>, <issue id="9f986820-b05e-4e41-ad70-e9d03d5bcc25" href="https://linear.app/recce/issue/DRC-4588/always-render-the-held-to-reading-control-disabled-with-its-reason">DRC-4588</issue>, <issue id="53b75c53-66ba-4dce-a929-2dc0e89a453e" href="https://linear.app/recce/issue/DRC-4589/split-the-three-inks-onto-label-value-and-absence-roles-so-a-label">DRC-4589</issue>, <issue id="52b62297-1dea-4804-ac6d-3ac8416f3359" href="https://linear.app/recce/issue/DRC-4591/adopt-a-three-tier-caveat-rule-and-put-the-long-form-behind-redraw">DRC-4591</issue>

Raised from user feedback; mechanism and figures established by a measured audit of the live board and the shipped stylesheet.
```

### Captured original — milestone `Clean and Cogent UI/UX`

Read live 2026-09-17. `id: 5e3b8b68-f7d7-429c-b4c8-682cd86f8b2b`, progress 1.92. Verbatim
description:

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

### Drafted correction — milestone `Clean and Cogent UI/UX`

**None owed by this issue.** The rewrite below changes nothing the milestone asserts: "Held to
ordering" remains on the `What is left` list, the contrast reasoning is untouched, and the
`Waits on` sentence stays true.

One drift was observed and is deliberately **not** drafted here: `What is left` says "Twelve
issues", and DRC-4602 was filed on 2026-09-17 out of DRC-4587's implementation, making it
thirteen. That drift belongs to whichever stage owns DRC-4602's filing — this branch editing the
milestone would collide with it for no gain (`AGENTS.md` Parallel Work: shared surfaces are
merged once, not per branch).

### Drafted rewrite — issue DRC-4594

The draft is shorter than the original (roughly 470 words of body against 640), the stale figures
are dated and demoted rather than deleted, and the ordering contradiction the original did not
know about is resolved in the body rather than left to the implementer.

```markdown
## User value

A reader opening Held to for the first time — mid-flight, asking whether a running session is
still on task — meets what the tab cannot do before what it is for, so they never reach the two
boxes that are the point. One sentence of purpose above the caveats, and the reading above the
record, is what makes the tab legible on first sight.

## The Problem

Concede the hard part first: a tab where you type a brief, ask the board to read a session
against it, and are guaranteed it will never tell the agent anything is a concept most users
have not met, and no layout makes a reader infer it. What styling did do is put the disclaimers
before the idea.

The panel opens with its two textareas, follows them immediately with a 48-word paragraph whose
42 middle words explain why this session cannot be raised, then runs four consecutive sections
that each report that nothing is here, before reaching COUNTS — whose caption's whole job is to
say the five numbers above do not relate.

Nothing in the WHAT YOU ASKED FOR block says what typing buys. The tab answers it once, four
sections down, inside a CLI instruction.

**Measured on `spacedock-ensign/drc-4587` @ 3cc7ef49, the tree this lands on**

* Render order today: WHAT YOU ASKED FOR, the re-entry paragraph, OBSERVED RECORD, A LATER
  DIRECTION, READING, DEPARTURES RAISED TO YOU (four parts, COUNTS the fourth), HOW IT LANDED,
  the Intent-log pointer — built at `next-cockpit.js:2375-2380`
* The re-entry paragraph concatenates three independently computed strings into one `<p>`
  (`next-cockpit.js:2280`): a 6-word link sentence, a 32-word raise-unavailable sentence (31 on
  the reachable branch), a 10-word resume clause. 48 words on the default board
* `#app a` is `display:inline-flex;align-items:center` (`styles.css:45`), and this is the only
  prose paragraph on the tab carrying an inline anchor
* Four consecutive sections read "No entry in the observed record names this session"
  (`:1157`), "Nothing has been typed…" (`:1696`), "No reading has been made at your request"
  (`:1935`), "Nothing watches for a departure on its own" (`:1823`)
* The five COUNTS labels (`:1900-1904`) total 32 words; the first two restate FROM THE READING
  YOU ASKED FOR (`:1922`) and FROM THE CHECKS RUN WHILE YOU WERE AWAY (`:1813`)
* `your words` (`next-cockpit.js:1036`) and the TYPED GOAL label above it now render at the
  same size, ink and family — both `var(--fs-label)` mono `--ink3` (`styles.css:869-870`). After
  DRC-4587 it is not a sub-label at all, it is a second label saying less

## The Solution

**A lede**, as the first child of `.next-cockpit-held`, at the sentence tier in full ink, worded
to what the board actually does — a reading happens when the reader asks for one, and nothing
watches on its own:

> "Type what you were after. Ask for a reading, and Cargento lists where this session departed
> from it. It never writes into the session, so steering stays yours."

Ship no wording implying an automatic check: the unasked lane is off by default
(`next-cockpit.js:1814`) and this same tab tells the reader to restart with `--unasked-readings`.

**Reorder** to WHAT YOU ASKED FOR → A LATER DIRECTION → READING → DEPARTURES RAISED TO YOU
(COUNTS inside it) → HOW IT LANDED → OBSERVED RECORD, with the Intent-log pointer still the
tab's last line. This is one line moved in `nextCockpitHeldTo`. Two constraints the original
filing did not know about are settled below.

**Split the re-entry paragraph** into a primary action plus two labelled rows, available path
first: the anchor on its own line (keeping `data-next-focus="cockpit-held-reentry"`, a managed
focus lane per [reader state](…/docs/design-reader-state.md)), then a `Re-entry` row and a
`Raise` row, with the tmux/platform sentence moved verbatim behind DRC-4591's disclosure. All
three raise branches and all three resume branches keep their own sentence.

**Delete the `your words` sub-label** and its rule. **Strip the repeated quantity noun** from
each count label ("Departures in the reading you asked for" → "From the reading you asked for")
and group the five rows under mono DEPARTURES and RAISES sub-labels — 32 words to 28 including
the two new sub-labels. Every `line()` value argument, the null-to-"not published" branch, and
`nextCockpitReadingDepartures`'s single-pass derivation are untouched.

## The ordering, settled

The original section list had seven slots and omitted `nextCockpitConflict` (A LATER DIRECTION,
`next-cockpit.js:2193`), because that block renders only once something has been typed and the
capture was of an unannotated session. Its comment (`:2370-2372`) states a two-sided placement
constraint: above the reading because it constrains one, below the record because it cites rows
from it. Nothing in the suite pins either half.

1. **The "above the reading" half is kept.** A later direction changes what a reading means, so
   it is read first.
2. **The "below the record" half is overturned, deliberately.** The record moving last is the
   point of this issue; the conflict block's rows carry their own text and age inline, so they
   are readable without the record above them. One sentence is positionally anchored and is
   reworded with the move: "…is in the record read above" (`:2217`) becomes "…is in the observed
   record read for this session". No test pins that string. The comment at `:2370-2372` is
   rewritten to record the overturn and its reason.
3. **OBSERVED RECORD is the last *section*, not the last line.** The Intent-log pointer
   (`nextCockpitDeparturesKept`) is a one-line pointer off the tab, is already asserted to be the
   tab's final slot (`test_next_cockpit.py:7767`), and stays there.
4. **COUNTS does not move independently.** It is emitted inside DEPARTURES RAISED TO YOU
   (`:1786`, `:1898`); extracting it would split the single-pass derivation that
   `AGENTS.md`'s second Measured Invariant protects. "COUNTS below DEPARTURES" holds by
   construction and cannot regress.

## Acceptance

- [ ] A reader meets one sentence of what the tab is for before any caveat, and that sentence
      does not claim an automatic reading
- [ ] Section order is WHAT YOU ASKED FOR → A LATER DIRECTION → READING → DEPARTURES RAISED TO
      YOU → HOW IT LANDED → OBSERVED RECORD, pinned by a test, with the Intent-log pointer last
- [ ] No sentence on the tab claims the observed record is above it
- [ ] The re-entry block leads with the action; the raise limitation and its platform
      explanation both survive, one of them behind a disclosure, and the containment check that
      the block is inside its section is kept rather than loosened
- [ ] `data-next-focus="cockpit-held-reentry"` survives the restructure and focus is restored
      on redraw
- [ ] Count labels drop the repeated quantity noun; every `line()` value argument and the
      single-pass derivation are unchanged
- [ ] The `your words` sub-label, its rule, and the comment that cites it are gone

## History

**Filed 2026-09-17, superseded 2026-09-17 at triage.** These figures were measured on a live
board running a pre-DRC-4587 tree and are not reproducible on the tree this change lands on.
They are kept because they are why the issue was filed, not because they are current:

* "Its two lines sit ~28px apart against ~18-20px elsewhere on the tab." DRC-4587 repointed the
  re-entry paragraph to `500 15px/1.55` (`styles.css:1032`), so both numbers moved. The
  mechanism — `#app a{display:inline-flex}`, now `styles.css:45` — is unchanged, and lifting the
  anchor out of the `<p>` still removes it. Not re-measured: three further PRs in this milestone
  land before this one.
* "Held to is 974px, the largest container in the cockpit, at 91 words per control." Live-render
  geometry on the same pre-DRC-4587 tree. `.next-cockpit-held` carries no width of its own, so
  the figure was a property of the cockpit grid at that capture's viewport.
* `"your words" (next-cockpit.js:1035, 10px mono)`. It is `:1036` (`:1035` is the label span it
  restates), and after DRC-4587 it is `var(--fs-label)`, 11px — the same size as the label above
  it, not a step below it.
* The `Measured` line citing `next-cockpit.js:2281` for the re-entry paragraph: the template is
  at `:2280`.
* The original Solution's section list, and the Problem's claim that two count labels "restate
  the uppercase section headings directly above them". The labels sit in COUNTS, a sibling part,
  not under those headings; what is removed is the repeated quantity noun, which is what the
  original Solution actually prescribed.

---

Complaint **C4** · tabs: held-to · severity **major** · effort **L**

Raised from user feedback; mechanism and figures established by a measured audit of the live
board and the shipped stylesheet, re-checked against `spacedock-ensign/drc-4587` at triage.
```

> The drafted body drops the `blocked by <issue …>` inline run and the "In the attached
> screenshot" list. The blockers are Linear relations and render themselves; the screenshot
> callouts restate four bullets already in `Measured`. The attachment itself stays on the issue.

## The adversarial read

**Is the problem still real?** Yes, on the post-DRC-4587 tree. Every structural claim was
re-checked: `nextCockpitHeldTo` still emits `nextCockpitWorkEvidence` first
(`next-cockpit.js:2375`), no lede exists (`:2410` opens straight onto the bound header and the
fields grid), the re-entry `<p>` is still three strings concatenated (`:2280`), the five count
labels still total 32 words (`:1900-1904`), and `your words` is still emitted at `:1036`.

**Is the approach still the one that fits?** Yes, with two amendments the body now carries. The
issue's own diagnosis of the count labels is looser than its prescription, and the prescription
is right. And DRC-4587 changed the "your words" argument in this issue's favour: it is no longer a
smaller tier that duplicates, it is the same tier that duplicates.

**Does any part describe a state that no longer exists?** Four citations and all three pixel
figures. All are demoted to the dated History section rather than deleted.

**One claim the original did not make, found in the tree.** DRC-4587 changed
`.next-cockpit-held-sub` from a literal `10px` to `var(--fs-label)`, which is the same
`11px` the `.next-cockpit-held-label` above it now uses (`styles.css:869-870`). The sub-label and
the label it restates are now typographically identical.

**A stale comment the reorder must carry.** `next-cockpit.js:3465-3468` explains the
conflict-retype handler by reference to "the box the stylesheet labels \"your words\"". Deleting
the label falsifies that comment. It is rewritten in the same commit; `AGENTS.md`'s Code Comments
section is why this is not left for later.

**Not re-measured, on purpose.** The 974px width, the ~28px leading and the "91 words per
control" figure are live-render geometry. DRC-4588, DRC-4589 and DRC-4591 all land between this
tree and this issue's own PR, and each moves type or layout. Measuring now would produce a
figure stale before it is used. No acceptance criterion depends on any of the three.

## Acceptance criteria

- **AC-1 — offline:** The first child of `.next-cockpit-held` is a lede at the sentence tier in `--ink`, and its text index in the rendered tab precedes the index of every absence sentence and of `next-cockpit-held-reentry`. **Verified by:** a new assertion in `test_next_cockpit.py` comparing `html.indexOf('next-cockpit-held-lede')` against `html.indexOf('next-cockpit-held-reentry')` and against the four absence strings; today there is no such class and the first comparison returns `-1`. **Falsified by:** emitting the lede anywhere after the fields grid, or omitting it.
- **AC-2 — offline:** The lede claims no automatic reading: its text contains no form of "watch", "automatic" or "checks for you", and it names the reader's own ask. **Verified by:** a string assertion on the lede's extracted text in `test_next_cockpit.py`, run on a board with `__dashboard.unasked` unset — the default. **Falsified by:** wording the lede so it is false on the default board, which is the board the `--unasked-readings` instruction four sections down exists for.
- **AC-3 — offline:** The rendered tab's section order is WHAT YOU ASKED FOR, A LATER DIRECTION, READING, DEPARTURES RAISED TO YOU, HOW IT LANDED, OBSERVED RECORD, with `next-cockpit-departures-kept` last of all. **Verified by:** a new chain of `assertLess` calls over `html.find` for the six `<h2>` strings plus the pointer class, rendered on an annotated session with a pending later direction so all six exist; today only the DEPARTURES/HOW IT LANDED/pointer pair is pinned (`test_next_cockpit.py:7766-7767`) and the other four slots are unpinned. **Falsified by:** moving any section, including re-raising OBSERVED RECORD, which is exactly the regression no current test can see.
- **AC-4 — offline:** No sentence rendered on the tab asserts that the observed record is above it. **Verified by:** an assertion that the conflict block's text contains "is in the observed record read for this session" and that the string "record read above" appears nowhere in the rendered tab; `next-cockpit.js:2217` carries the old phrase today and no test pins it. **Falsified by:** moving OBSERVED RECORD last while leaving the phrase, which ships a false sentence through a green suite.
- **AC-5 — offline:** The re-entry block renders the anchor as its own line before any limitation sentence, and all three raise branches and all three resume branches still render their own sentence, one of them behind a disclosure. **Verified by:** the rewritten probe in `test_next_cockpit.py` (currently `:6648-6650`) extracting the whole `next-cockpit-held-reentry` container instead of one `<p>`, keeping the `inside: at > held && at < closes` containment check unchanged, and asserting the anchor's index is below every limitation sentence across the six branch combinations. **Falsified by:** loosening the containment check to "after the header", which is the exact regression the comment at `:6651-6653` says that check was added for.
- **AC-6 — offline:** `data-next-focus="cockpit-held-reentry"` is present on the anchor after the restructure, and a redraw with that lane marked restores focus to it. **Verified by:** the existing `cockpit-held-reentry` assertion in `test_next_cockpit.py:6677`, plus a managed-lane restoration case driving `nextRestoreFocus` at that name and reading `document.activeElement`. **Falsified by:** wrapping the anchor in a new element that takes the attribute, which keeps the string assertion green while focus lands on the wrapper.
- **AC-7 — offline:** No count label begins with the quantity noun its group sub-label supplies, the five rows sit under mono DEPARTURES and RAISES sub-labels, and the five `line()` value arguments are unchanged. **Verified by:** string assertions on the five labels plus the two sub-labels, and the seven positional value reads at `test_next_cockpit.py:7399` and siblings, which read `class="next-cockpit-count-value"` by position and must stay green untouched. **Falsified by:** rewording any `line()` value argument or collapsing the null-to-"not published" branch while relabelling.
- **AC-8 — offline:** The `your words` span, its `.next-cockpit-held-sub` rule, and the comment citing it are all gone. **Verified by:** `grep -c 'next-cockpit-held-sub'` over `next-cockpit.js` and `styles.css` returning 0 (today 1 each, at `:1036` and `:870`), and `grep -n 'your words' next-cockpit.js` returning only `:872` and `:2403` — the save-failure sentence and the ended-session sentence, neither of which is a label — where today it also returns the span at `:1036` and the handler comment at `:3467`. **Falsified by:** deleting the span and leaving the rule, or leaving the handler comment at `:3465-3468` that explains itself by that label.
- **AC-9 — offline:** All nine frontend byte pins agree with the assets in one pass. **Verified by:** `test_next_page.py` (next-cockpit.js size and digest, styles.css size and digest, assembled size and digest), `test_next_flag.py:67/69` (assembled size and digest) and `test_focus.py:1024` (assembled digest) all green, each figure recomputed from the assets rather than from another test. **Falsified by:** recomputing one file and reasoning about the rest, which leaves the other two modules red on numbers that were each correct for a tree that no longer exists.
- **AC-10 — interactive:** Keyboard tab order through the restructured re-entry block reaches the anchor before the disclosure, and the disclosure's open state survives a redraw. **Verified by:** a live board at `127.0.0.1:4553` with an annotated session, tabbing into the block and then forcing a redraw. **Falsified by:** a disclosure whose open state is browser-default rather than DRC-4591's redraw-safe lane. **Not automated here, and deliberately:** the redraw-safe disclosure primitive is DRC-4591's deliverable and rides the same PR; if DRC-4591 ships a harness for it, this criterion becomes offline and should be moved.

`AC-1`, `AC-2` and `AC-3` are the three a user sees directly. Every criterion above is expected to scan as
unevidenced at this gate: `implementation` and `review` supply the evidence.

## Expected surface, with tolerance

Measured against `spacedock-ensign/drc-4587` @ `3cc7ef49`. **Runtime and oracles are costed
separately**, because on this issue the oracles are the larger half.

| Surface | Files | Net LOC | Tolerance |
|---|---|---|---|
| Runtime | `web/next-cockpit.js`, `web/styles.css` | +45 | ±15 |
| Behavioural tests | `tests/test_next_cockpit.py` | +70 | ±25 |
| Byte-pin oracles | `tests/test_next_page.py`, `tests/test_next_flag.py`, `tests/test_focus.py` | 9 figures, ~0 LOC | exact |
| Docs | `docs/design-reader-state.md` | +1 row | 0-1 |

Runtime detail: lede (+4), the one-line reorder in `nextCockpitHeldTo` plus its rewritten comment
(+6/-4), the re-entry restructure (+20), the conflict sentence reword (+1/-1), count relabel and
grouping (+8), the `your words` span and the handler comment that cites it (-5), and four
stylesheet rules (+4/-1).

**No new test file, and no required check compels one.** The change adds no module, so the
import-graph and runtime-file inventories in `scripts/validate_plugins.py` are untouched; every
assertion lands in modules that already exist.

**Semantics that may move:** the order a reader meets the six sections in, and one sentence in
the conflict block. Nothing about what any figure counts, what the store holds, or what the
producer may say — `docs/design-reading-a-session.md`'s seven-rule shape contract and the
single-pass derivation are both untouched by construction.

**Docs:** if DRC-4591's disclosure carries reader state of its own, this issue's instance of it
earns a row in `docs/design-reader-state.md`. That is one row, and `sync-docs` before the PR is
where it lands. Nothing in CI compels it, which is why it is declared here.

**The estimate's known risk.** DRC-4588, DRC-4589 and DRC-4591 all rewrite parts of this same tab
and all land before this issue's own PR. The runtime figure is against the tree as it stands
today; if DRC-4591's disclosure primitive turns out to need a wrapper the re-entry block cannot
reuse, the re-entry half doubles. That is the one line item worth re-checking at the start of
implementation rather than at review.

## Approach, and the simplest rejected alternative

**Chosen:** move one line in `nextCockpitHeldTo`, add a lede, restructure the re-entry block on
DRC-4591's disclosure, relabel the counts, delete the duplicate sub-label — and pin the resulting
order with a test, because today nothing does.

**Simplest rejected alternative: reorder only, and skip the lede.** It is a one-line change and
it does move the four absence sections below the reading. It cannot deliver the value, because
the issue's first complaint is not the order — it is that nothing on the tab says what typing
buys. A reader who reaches the textareas sooner still has no sentence telling them what a
reading is or that Cargento will not act on it, and the tab's only answer stays four sections
down inside a CLI instruction. The order is what stops the caveats arriving first; the lede is
what makes arriving anywhere worth it.

**Second rejected alternative: keep OBSERVED RECORD above A LATER DIRECTION** to preserve both
halves of the in-tree constraint. Rejected because the record is the first of the four absence
sections and demoting it is most of the issue's value, and because the constraint's cost is one
positionally-anchored sentence that is cheaper to reword than to design around. The overturn is
recorded in the drafted body and in the code comment, so the next reader argues with a stated
ruling rather than re-deriving one.

## Stage Report: triage

- DONE: Capture the live Linear issue body and the owning milestone description verbatim under `## Linear edits made` as the pre-edit record before drafting anything, and draft the rewrite of each beside it without writing either to Linear.
  Both captured in fenced blocks under `## Linear edits made` with their read timestamps; the issue rewrite is drafted beside them and the milestone correction is declared not-owed with its reason. Zero Linear writes: only `get_issue`, `get_milestone`, `list_comments` (empty) and one `list_issues` read were called.
- DONE: Write the acceptance criteria into `## Acceptance criteria` as bullets shaped `- **AC-N — offline:** {property}. **Verified by:** {…}. **Falsified by:** {…}`
  Ten criteria under the literal heading, hyphenated ids, each bold label closed on the line it opens; nine offline and one interactive, with the interactive one saying what would make it offline. Scanner output pasted below.
- DONE: Declare the expected surface with tolerance, costing the byte-pin oracles separately from the runtime, and measure every figure against the POST-DRC-4587 tree on branch `spacedock-ensign/drc-4587`, not against main
  Four-row table separating runtime (+45 ±15 across two web files) from behavioural tests (+70 ±25), the nine byte-pin figures (exact, three modules), and one doc row. Every figure read from the `spacedock-ensign/drc-4587` worktree at `3cc7ef49`; the three live-render figures the issue was filed with are demoted to a dated History section rather than restated, and no criterion depends on them.
- DONE: Settle the ordering against the in-tree constraint the recon found the issue contradicts
  Settled in four numbered rulings in the drafted body: the conflict block's "above the reading" half kept, its "below the record" half overturned deliberately with the one positionally-anchored sentence reworded and the code comment rewritten, OBSERVED RECORD ruled last *section* rather than last line (the Intent-log pointer keeps the slot `test_next_cockpit.py:7767` already pins), and COUNTS ruled not independently movable. Two criteria pin the result, because nothing in the suite pins four of the six slots today.

### Summary

The issue survives the adversarial read on the post-DRC-4587 tree — every structural claim
re-verified — but four citations and all three pixel figures are stale, and they are dated and
demoted rather than deleted. DRC-4587 strengthened one argument in passing: `.next-cockpit-held-sub`
moved from a literal `10px` to `var(--fs-label)`, so "your words" is now the same size, ink and
family as the label it duplicates. The substantive gap was the ordering: the original section list
omitted `nextCockpitConflict`, whose comment states a two-sided placement constraint and whose
prose says "the record read above" — moving OBSERVED RECORD last while leaving that sentence would
ship a falsehood through a fully green suite, since nothing pins either the sentence or four of the
six slots. Both halves are now settled in the drafted body, and two acceptance criteria close the
test gap. Nothing was written to Linear; the gate authorizes that write.
