---
id:
title: "Always render the Held to reading control, disabled with its reason, instead of deleting the tab's only verb"
status: review
source: "https://linear.app/recce/issue/DRC-4588/always-render-the-held-to-reading-control-disabled-with-its-reason"
started: 2026-09-17T06:57:18Z
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
        - id: gate:drc-4588:triage
          stage: triage
          attempts:
            - id: gate-attempt:drc-4588-triage-1
              briefing:
                id: briefing:drc-4588:triage:attempt-1:revision-1
                digest: sha256:6ff390e1f625ee01e5db6a5931c1aa8327ee1f13aafb795bb58aa6815b920f5c
                room-ref: ./review/triage/briefing-1
              resolution:
                type: Resolution
                id: resolution:spacedock:drc-4588:triage:1
                briefing: briefing:drc-4588:triage:attempt-1:revision-1
                by: agent:first-officer
                at: "2026-09-17T07:17:30.177173Z"
                decision: approve
                reason: 'Checklist 3 done / 0 skipped / 0 failed; AC-1..AC-6 resolve, four offline and two interactive, with AC-6 the user-visible criterion. Triage''s R1 is the finding that matters: aria-disabled restores the click that disabled was suppressing and neither handler gates on the reason, so AC-4 pins the handler gate with calls===0 and a role=status refusal rather than shipping a control that spends model capacity from a state the page calls unavailable. R2 was escalated to the captain on a premise triage itself corrected: DRC-4565 carries two acceptance criteria and neither is this one, so what inverts is two implementation-stage assertions at test_next_cockpit.py:6554-6555 carrying a docstring AC label, not an approved criterion. The captain was shown the corrected framing and approved proceeding. R3 drops the producer half, taking the surface from 11 files to 6.'
                conn:
                    quote: okay yes, go ahead
                    source: Captain, this session, 2026-09-17, answering the corrected R2 framing directly
              application:
                target-stage: implementation
                state: consumed
---

[DRC-4588](https://linear.app/recce/issue/DRC-4588/always-render-the-held-to-reading-control-disabled-with-its-reason) — Always render the Held to reading control, disabled with its reason, instead of deleting the tab's only verb

Seeded 2026-09-17 from the live Linear read of the Clean and Cogent UI/UX milestone.
Linear owns the current issue body, its relations and its resources; triage fetches them
live and validates them against the tree before anything is built. No triage, approval,
implementation or delivery is claimed here.

---

## Linear edits made

**Nothing in this section has been written to Linear.** The captured originals below are the
pre-edit record; the drafts are what `implementation` writes once the gate approves them.

### Captured original — DRC-4588 issue body (verbatim, read 2026-09-17)

```markdown
## User value

A reader who has just typed a goal notices this when they look for the thing that acts on it. Today the control that reads a session against your words is removed from the page exactly when nobody has typed anything yet — which is when a newcomer is looking for it.

## The Problem

Held to's job is a three-step chain — type a goal, save it, ask for a reading of the session against it — and in the state a newcomer lands in, the third control is not rendered at all. Under READING there is one sentence and nothing to press.

`nextCockpitReadingStates` returns a reason when both annotation fields are empty, and `nextCockpitReading` uses that reason to take an early `return close(...)` at next-cockpit.js:2079-2082, before `nextCockpitReadingControl` is ever called. Four things vanish together: the "Ask for a reading" button, the NEXT_READING_OFFER paragraph, the sending disclosure and the "N model requests recorded" counter. All three other paths (2097, 2107, 2128) call the control.

The suppression is not required by the gating — the button already carries a disabled arm and computes `enabled = authorized && !reason && !pending`. So the tab's stated purpose has no affordance on the tab, and the 363 words a reader does get are caveats attached to a capability whose control they have never seen.

**Measured**

* Screenshot: under READING the entire content is "Nothing has been typed for this session, so there is nothing to read it against." — no button, no offer paragraph, no request counter
* next-cockpit.js:2079-2082 returns the reason paragraph alone; `nextCockpitReadingControl` is at :1999 and NEXT_READING_OFFER is emitted only at :2097
* next-cockpit.js:2008 already computes `enabled = authorized && !reason && !pending`; :2019-2021 already supports a disabled arm
* Held to: 4 interactive elements against 363 words = 91 words per control; 2 of the 4 are the empty goal/expected-output textareas
* The save button is emitted hidden while `draft === saved` (next-cockpit.js:821-824, styles.css:866), so a keyboard user tabbing the empty form meets no save control
* next-cockpit.js:3429-3430 reveals the save control on the first keystroke without a redraw

**In the attached screenshot**

1. READING: one sentence, no button, no request count
2. Early return at :2079 drops four elements at once
3. 4 controls for 363 words; 2 are empty textareas
4. Save button hidden until the box is dirty

## The Solution

Delete the early return at next-cockpit.js:2079-2082 and always call `nextCockpitReadingControl(session, annotation, model)`, passing the reason through. The control already computes the same reason internally and prints it after the button, so this restores the button, the offer paragraph, the disclosure and the counter, removes the duplicated sentence, and the button arrives disabled because `enabled` is already false.

Extend the reason rather than replacing it: keep "Nothing has been typed for this session, so there is nothing to read it against." verbatim and append "Save a goal above to enable a reading."

**Required, not a nice-to-have:** rendering the control also renders `${count} model requests recorded`, derived via `nextNumber(annotation.reading_count) || 0`, which coerces an unpublished field to 0 — the structurally-present-default failure AGENTS.md records under Measured Invariants as the repeat defect here. Render the count only when `reading_count` was actually published, and say "not published" otherwise; verify against `sessions.base_session` what the field holds when nothing ran.

Wire the reason to the control with `aria-describedby`, copying the discard pattern at next-cockpit.js:2330-2333 that already does this correctly. Finally, emit the save control `disabled` rather than `hidden` so a keyboard user meets it, keeping `hidden` for `held-clear`.

## Acceptance

- [ ] On an untouched session, READING renders the "Ask for a reading" button (disabled), the offer paragraph, the disclosure and the request counter
- [ ] The empty-annotation sentence still renders verbatim, beneath the button rather than in place of it
- [ ] "0 model requests recorded" never renders for a session whose annotation carries no `reading_count`; the absent case says so in words
- [ ] The disabled button carries `aria-describedby` pointing at its reason paragraph
- [ ] Tabbing the empty form reaches a disabled save control rather than skipping it

---

Complaint **C4** · tabs: held-to · severity **blocker** · effort **M** · depends on nothing

Raised from user feedback; mechanism and figures established by a measured audit of the live board and the shipped stylesheet.
```

### Captured original — milestone "Clean and Cogent UI/UX" description (verbatim, read 2026-09-17)

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

### Labels to set

Already correct on the live issue; `implementation` confirms rather than changes them.

- `journey:mid-flight` → **P2**, "What is it doing, and when should I come back?"
- `move:sharpen` — the promise is kept and this makes it more precise. Not `keep`: the board says
  nothing untrue in this state, it says too little. The reader is not misinformed about the session;
  they are unable to act on it.

### Drafted rewrite — DRC-4588 issue body

```markdown
## User value

A reader who has just opened Held to looks for the control that acts on their words, and in the
state a newcomer lands in that control is not on the page at all. Rendering it present and inert,
with the reason it cannot fire, gives the tab an affordance for its own stated purpose.

P2 (What is it doing, and when should I come back?) · move `sharpen`.

## The problem

Held to is a three-step chain — type a goal, save it, ask for a reading of the session against it —
and the third control is not rendered until the first two are done. `nextCockpitReading` takes an
early `return close(...)` at next-cockpit.js:2079-2082 whenever `nextCockpitReadingStates` returns a
reason, before `nextCockpitReadingControl` (:1999) is reached. Four things vanish together: the
"Ask for a reading" button, the NEXT_READING_OFFER paragraph, the sending disclosure and the request
counter. The other three paths (:2097, :2107, :2128) all call the control.

The suppression is not required by the gating. The control recomputes the same reason itself at
:2000-2008 and already carries an inert arm at :2019-2021, so the early return is redundant with the
gate it is standing in for.

It also breaks a rule the design already states. `docs/design-reading-a-session.md` says under
Repeated calls that each reading is counted and "the count is shown beside the control". In the
untouched state neither the count nor the control is shown, so the only state in which the count
would be zero is the one state where the rule does not hold.

Second defect, same tab and same shape: the save control is emitted `hidden` while
`draft === saved` (:821-824, :1043, styles.css:866), so a keyboard user tabbing the empty form meets
no save control at all.

**Measured 2026-09-17 against main @f83dd5f5.** Every line reference above was read in the tree, not
carried from the earlier body.

## The solution

1. Delete the early return at :2079-2082 so `nextCockpitReadingControl` runs in all four reason
   states — discard, nothing-typed, model-unread, model-disabled. The control prints the reason
   after the button, so the sentence is moved rather than lost.
2. Extend the nothing-typed reason: keep "Nothing has been typed for this session, so there is
   nothing to read it against." verbatim and append "Save a goal above to enable a reading."
3. Emit `reading-ask` with `aria-disabled="true"` rather than `disabled`, which is the ruling this
   repository already made at next-boot.js:385-386 — the control keeps its place in the tab order
   and the click reaches a handler that says why — with a matching
   `.next-cockpit-reading button[aria-disabled="true"]` rule in styles.css.
   **Gate `nextCockpitAskForReading` on the same reason the control renders.** It gates only on
   `pending` today (:2440). Changing the attribute without adding the gate lets a press from a
   refused state reach `POST /api/reading` and spend the reader's own model capacity — it ships the
   defect the criterion was written to close.
4. Wire the reason paragraph to the button with `id` + `aria-describedby`, copying the discard
   pattern at :2330-2333.
5. Emit the save control `aria-disabled="true"` rather than `hidden`, keeping `hidden` for
   `held-clear`, and gate `nextCockpitHeldSave` the same way. `nextCockpitHeldControl` (:821) and
   `nextCockpitHeldToggle` (:826) each take a boolean `shown`, so both need a state argument;
   `nextCockpitHeldToggle` is what :3430 calls on a keystroke without a redraw. Add
   `.next-cockpit-held-field button[aria-disabled="true"]` — there is no such rule today, and the
   only inert selectors in the sheet are styles.css:84, :119 and :947.

**Not doing:** making `reading_count` absent on an untouched session. See History.

## Acceptance

- [ ] On an untouched session the READING block renders the "Ask for a reading" button, the
      NEXT_READING_OFFER paragraph, the sending disclosure and the request counter
- [ ] The empty-annotation sentence renders verbatim and exactly once, after the button rather than
      in place of it
- [ ] The request counter's figure is derived from the published `reading_count` and not authored:
      a fixture carrying 3 renders 3, and an untouched session renders 0
- [ ] The reading button is focusable while refused, carries `aria-describedby` pointing at the id
      of its reason paragraph, and a press in that state makes no network call and leaves a
      `role="status"` message giving the reason
- [ ] Tabbing the untouched goal field reaches a save control that is present and inert rather than
      absent, and a press while inert makes no `/api/annotate` call
- [ ] A reader who has typed nothing can see on Held to that a reading is something this tab does,
      and one sentence naming what would have to change for it to fire

## History

### 2026-09-17 — rewritten at triage

Three instructions in the body as filed were checked against the tree and do not hold. They are kept
here because the reasoning that produced them is sound and only the conclusions are wrong.

**"emit the save control `disabled`" and "the disabled button carries `aria-describedby`".** A
`disabled` button is removed from the browser tab order, so "tabbing reaches a disabled save
control" is false by construction and an `aria-describedby` on a `disabled` button is never
announced. This repository already ruled the other way at next-boot.js:385-386 for DRC-4390, with
the matching `[aria-disabled="true"]` rule at styles.css:119. Both instructions become
`aria-disabled`, and both handlers grow the gate the attribute no longer provides.

**"render the count only when `reading_count` was actually published, and say 'not published'
otherwise".** The reasoning cites the structurally-present-default invariant correctly but the field
does not fit it. The invariant's test is whether the figure differs between "nothing ran" and "it ran
and found nothing"; `reading_count` does differ, because a press increments `readings` in the store
whether or not a reading comes back, and a refused read-back leaves the count non-zero beside
`reading_refused`. Zero presses is a true count of presses, not a fact about the schema. Making the
field absent would also mean changing an existing declared field's absent value rather than adding a
name, which the two set-equality tests that guard the three declaration sites cannot see — the
safety net AGENTS.md describes does not cover this move. The criterion becomes a derivation check
instead: the figure must come from the published field.

**"All three other paths call the control", and the scope that follows from it.** True, but the
early return governs four states and the body argues only the nothing-typed one. The other three —
discarded, model-unread, model-disabled — are changed by the same deletion. Rendering the control in
all four is deliberate: a control that appears and disappears by state is the inconsistency being
fixed, and the model-disabled reason already tells the reader how to turn the capability on, which
is worth more beside a visible button than alone. This overturns the second half of what
tests/test_next_cockpit.py:6539-6555 labels DRC-4565 AC7, which asserts the offer is withheld on
both the discarded and the never-typed rows. Exactly two assertions invert — `assertEqual(0,
discarded["ask"])` at :6554 and `assertEqual(0, never["ask"])` at :6555 — and both become 1. The
two sentence assertions above them at :6551-6553 are untouched, which is AC7's load-bearing claim:
the discarded row says the discard sentence and not "nothing typed".

**DRC-4565 is closed and shipped** — Done 2026-09-14 via PR #330 — so this is a change to a shipped
contract rather than to work in flight, and it is raised at the gate rather than made inside the
diff. Two things bound how large the claim is, both checked rather than assumed. DRC-4565's Linear
body carries only two acceptance criteria, and neither is the withheld-offer claim; and no
drc-4565 entity survives in the state checkout or its archive to say what that numbering was
against. The "AC7" label exists only in the test's own docstring, and four unrelated docstrings in
the same file carry an "AC7" belonging to other issues. So what R2 overturns is an
implementation-stage test assertion carrying an AC label, not a criterion a captain approved on the
issue.

The "363 words" and "91 words per control" figures came from a screenshot and were not re-checked;
they are not load-bearing for anything above.
```

### Drafted rewrite — milestone "Clean and Cogent UI/UX"

One word-level correction. Everything else in the description survives the rewrite unchanged, so it
is not restated here.

Under **What is left**, third bullet — replace:

> * **Always render the Held to reading control**, disabled with its reason, instead of deleting the tab's only verb exactly when a newcomer looks for it.

with:

> * **Always render the Held to reading control**, present and inert with its reason, instead of deleting the tab's only verb exactly when a newcomer looks for it.

"disabled" is now the wrong word for what ships: the control is `aria-disabled`, keeps its place in
the tab order, and refuses the press in its handler. Leaving the milestone saying "disabled" would
describe the thing the triage ruled against.

Nothing else in the description is made false by this issue. "Twelve issues" is unchanged, "Waits
on: nothing outside this milestone" is unchanged, and the three-foundations framing still holds —
this issue gates DRC-4594.

---

## Triage: adversarial read

### Is the problem still real

Yes, and every mechanical claim in the body is exact against main @f83dd5f5.

- next-cockpit.js:2079-2082 is the early `return close(...)`; `nextCockpitReadingControl` is defined
  at :1999 and called only at :2097, :2107 and :2128, all downstream.
- :2008 is `const enabled = authorized && !reason && !pending;` and :2020 emits
  `${enabled ? "" : " disabled"}`.
- The empty-annotation sentence is :1696, NEXT_READING_OFFER is :2027, the discard aria pattern is
  :2330-2333, the save control is `hidden` at :821-824 and revealed without a redraw at :3429-3430,
  and styles.css:866 is `.next-cockpit-held-field button[hidden]{display:none}`.

### What the body gets wrong

Three things, all in the prescribed solution rather than the diagnosis. They are recorded in the
drafted History section above and ruled on below.

### What the body missed — the finding that changes the work

`nextCockpitAskForReading` (:2438-2440) gates on `pending` alone. It does not read `authorized`, and
it does not read `nextCockpitReadingStates`. Today that is safe, because `disabled` means the click
never reaches it. The issue's own AC4 requires `aria-describedby` to be announced, which requires the
button to be focusable, which requires `aria-disabled` — and `aria-disabled` restores the click. So
the change as filed, implemented literally, produces a button that a reader can press from the
nothing-typed, model-disabled and unauthorized states, and each press issues `POST /api/reading` and
spends the reader's own model capacity. The same hole exists on `nextCockpitHeldSave` (:2577),
which never checks `draft !== saved`.

The handler gate is therefore not an optional refinement — it is the half of this change that keeps
the other half from being a regression. It is in the drafted body as step 3 and step 5, and in AC4
and AC5 as an explicit no-network-call assertion.

### A test that will not catch the regression

tests/test_next_cockpit.py:5092 asserts `assertRegex(out["during"], r'reading-ask"[^>]*disabled')`.
`aria-disabled="true"` contains the substring `disabled`, so this assertion passes unchanged whether
the attribute is `disabled` or `aria-disabled` — it cannot distinguish the two and must not be cited
as proof that either shipped. Any new assertion on the attribute has to pin the full attribute name
and assert the absence of the bare form.

---

## Rulings

Four decisions the gate is asked to confirm. Each has a recommendation.

**R1 — `aria-disabled`, not `disabled`, on both controls, with handler gates. Recommended: adopt.**
The repository has already ruled this once (next-boot.js:385-386, DRC-4390) and carries the CSS for
it. The alternative — keep `disabled` — makes AC4 and AC5 unsatisfiable as written rather than
merely hard to verify. Cost of adopting: two handler gates, two CSS rules, and the discipline that
every inert control here refuses its own press.

**R2 — render the control in all four reason states, overturning the second half of DRC-4565 AC7.
Recommended: adopt.** The prior test asserts the offer is withheld on the discarded row as well as
the never-typed one, with the rationale that withholding is "what makes the sentence load-bearing
rather than decoration". DRC-4588's thesis is that withholding the control is the defect; the two
cannot both stand. AC7's actual claim — the discarded row says the discard sentence and not "nothing
typed" — survives untouched, and only the two `assertEqual(0, …["ask"])` lines invert. The
alternative, restricting the deletion to the nothing-typed arm, preserves a state-dependent
affordance, which is the inconsistency the issue exists to remove.

**R3 — do not make `reading_count` absent. Recommended: adopt (drop the producer half).** Reasoning
in the drafted History. Concretely this removes annotations.py, sessions.py, next-intent.js,
test_annotations.py and test_sessions.py from the change — five files and roughly twenty net runtime
lines — and avoids touching a published per-session field's absent value, which the two
set-equality tests guarding the three declaration sites cannot detect a mistake in.

**R4 — keep the save-control half in this issue rather than splitting it out. Recommended: adopt.**
It is a second defect, but it is on the same tab, in the same file, and of the same shape. AGENTS.md
is explicit that exactly one PR may touch `cargento_runtime/web/` at a time, so splitting buys a
second full review, a second CI cycle, a second byte-pin recomputation and a merge serialization,
for a change of about six lines. One PR per conflict surface, not one per issue.

### Not filed as a separate decision issue

None of R1–R4 is a product direction question. R1 and R3 are settled by evidence already in the
repository, R2 is a scope ruling inside this issue's own diff, and R4 is a packaging choice AGENTS.md
already has a rule for. The gate is where the captain confirms them; no blocker is added.

---

## Acceptance criteria

- **AC-1 — offline:** On an untouched session the READING block renders the "Ask for a reading" button, the NEXT_READING_OFFER paragraph, the sending disclosure and the request counter. **Verified by:** a `NextPageJsHarness` case in tests/test_next_cockpit.py asserting all four substrings in the returned HTML for an empty annotation; the existing `self.assertFalse(out["empty"]["control"])` at :5245 and the `["unread"]` pair at :5247 invert. **Falsified by:** the early return being left in place, or the control being called only on the nothing-typed arm.
- **AC-2 — offline:** The empty-annotation sentence renders verbatim and exactly once, after the button rather than in place of it. **Verified by:** the same harness — `html.count(sentence) == 1`, and `html.index(sentence) > html.index('data-next-cockpit-action="reading-ask"')`. **Falsified by:** the reason being printed both by the caller and by the control, which is the duplication the early return's deletion could easily reintroduce.
- **AC-3 — offline:** The request counter's figure is derived from the published `reading_count` and not authored: a fixture carrying 3 renders 3, and an untouched session renders 0. **Verified by:** two harness cases differing only in the fixture's `reading_count` (0 and 3), asserting "0 model requests recorded" and "3 model requests recorded" respectively. **Falsified by:** the number being hard-coded, or read from a different field, or the plural arm being inverted. This replaces the filed AC3 per R3.
- **AC-4 — offline:** The reading button is focusable while refused, carries `aria-describedby` pointing at the id of its reason paragraph, and a press in that state makes no network call and leaves a `role="status"` message giving the reason. **Verified by:** asserting the button carries `aria-disabled="true"`; asserting the rendered tag does not match `r'reading-ask"[^>]*\sdisabled[=>\s]'` (the bare form — the existing :5092 regex cannot tell the two apart and is not evidence here); asserting the `aria-describedby` value equals the `id` on the reason paragraph; and — dispatching the click through the existing action handler with a stubbed `fetch`, as the :5085 case already does — asserting `calls === 0` and that the `role="status"` text is the reason. One live pass on the board additionally confirms the control is announced in tab order: the attribute choice does not need this, the tab-order claim does, and that half stays interactive. **Falsified by:** `nextCockpitAskForReading` being left gated on `pending` alone.
- **AC-5 — offline:** Tabbing the untouched goal field reaches a save control that is present and inert rather than absent, and a press while inert makes no `/api/annotate` call. **Verified by:** asserting the `held-save` button renders without `hidden` and with `aria-disabled="true"` while `draft === saved`; asserting a keystroke through `nextCockpitHeldToggle` clears the attribute rather than the `hidden` property; asserting a press while inert makes no `/api/annotate` call; plus the same live tab-order pass as AC-4 for the announcement half, which stays interactive. **Falsified by:** `nextCockpitHeldToggle` still writing `control.hidden`, which is the path :3430 takes on every keystroke and the one a renderer-only fix would miss.
- **AC-6 — interactive:** A reader who has typed nothing can see on Held to that a reading is something this tab does, and one sentence naming what would have to change for it to fire. **Verified by:** opening a board at `127.0.0.1:4553`, focusing a session with no annotation, capturing the READING block to `docs/screenshots/`, and confirming a labelled control plus the extended reason are both present. **Falsified by:** a READING block that renders the control without the reason, or the reason without the control. This is the criterion a user can see; the other five are its mechanism.

**Split:** four offline (AC-1, AC-2, AC-3, and AC-5's attribute and gate half), two interactive
(AC-4's tab-order confirmation, AC-6), with AC-4 and AC-5 labelled by their binding half — the
attribute and the handler gate are offline and falsifiable, the screen-reader announcement is not.
No harness is proposed to automate the interactive half: a tab-order assertion needs a real browser
and this repository has none, so the honest declaration is that it stays interactive.

## Expected surface

Costed in three layers, because they have different risk.

**Runtime — 2 files, ~24 net lines, tolerance ±10.**

| File | Change | Net |
|---|---|---|
| `web/next-cockpit.js` | delete the :2079-2082 return; extend the nothing-typed reason (:1696); `aria-disabled` + `id`/`aria-describedby` in `nextCockpitReadingControl` (:2019-2021); gate `nextCockpitAskForReading` (:2438); state argument on `nextCockpitHeldControl` (:821) and `nextCockpitHeldToggle` (:826) and their two call sites (:1043, :3430); gate `nextCockpitHeldSave` (:2577) | ~+26 / −6 |
| `web/styles.css` | `.next-cockpit-reading button[aria-disabled="true"]` and `.next-cockpit-held-field button[aria-disabled="true"]` | ~+4 |

**Tests — 1 file, ~+130 lines, tolerance ±60.** tests/test_next_cockpit.py. Four existing assertions
invert (:5245, :5247, :6554, :6555); the :6552-6555 docstring needs rewriting to cite R2 rather than
the withheld-offer rationale it currently gives. Roughly five new cases for AC1–AC5.

**Oracles — 3 files, 7 pinned figures, ~10 lines, mechanical.** Costed apart because they carry no
design freedom and recomputing only the first leaves CI red:

| File | Pins |
|---|---|
| `tests/test_next_page.py:682-714` | next-cockpit.js size + digest; styles.css size + digest; assembled length + digest |
| `tests/test_next_flag.py:67-71` | assembled length + digest, separately |
| `tests/test_focus.py:1023-1026` | assembled digest, a third time |

**Total: 6 files.** Down from the recon's 11 — R3 removes annotations.py, sessions.py,
next-intent.js, test_annotations.py and test_sessions.py.

### Producer-side declared fields

**No new declared per-session field is needed, and none should be changed.** `reading_count` already
exists in all three declaration sites — `sessions.base_session` (sessions.py:582, at `0`),
`DECLARED_SESSION_FIELDS` (tests/test_sessions.py, as `annotation_reading_count`) and
`annotations.published` (annotations.py:858). The producer change the filed body asked for would
have altered the absent *value* from `0` to `None` without adding a *name*, and both guarding tests
are set-equality checks over names — they would have stayed green through it. That is a second reason
to decline it, beyond the substantive one in R3.

### What required checks compel

Checked before declaring, per the stage definition. Nothing here compels a new test file:
`CARGENTO_RUNTIME_FILES` gains no entry (no new runtime file), `lint_embedded.py` lints the edited
JS and CSS in place, and `RuntimeDecisionCitationsTest` is not triggered by a bare `DRC-4390` in a
comment — bare tracker keys are outside its grammar, which is how next-boot.js:385 already writes it.
A new comment must not use a `D-n` / `DEC-n` / `AC-n` local label unless it carries a real
repository-relative link with an exact heading anchor.

### Semantics this may move

Two, both intended: what a reader is offered in the discarded and model-disabled states (R2), and
whether an inert control is absent or present-and-refusing (R1). Nothing published by the server
changes, so no collector, no store and no API contract moves.

---

## Approach, and the simplest rejected alternative

**Chosen:** delete the early return, render the control in every state, and make both inert controls
`aria-disabled` with handler gates.

**Rejected — keep `disabled` and delete only the early return.** It is three lines smaller and needs
no handler gate, no CSS and no DRC-4565 conversation. It cannot deliver the value: a `disabled`
button is skipped by the keyboard and its `aria-describedby` is never read, so the reader this issue
is written for — the newcomer who cannot find the verb — still meets a control they cannot reach and
a reason they are never told. It satisfies AC1 and AC2 and fails AC4, AC5 and AC6 while appearing to
have shipped.

## Sequencing

Only one PR may touch `cargento_runtime/web/` at a time (AGENTS.md, Parallel Work). DRC-4587
(type-scale) is in triage concurrently and owns styles.css; every other issue in this milestone is
frontend work, and DRC-4594 — which this issue blocks — edits the same Held to region. Recommended
order: land DRC-4587 first, because it is the milestone's declared foundation and it moves the
stylesheet the other eleven build on, then DRC-4588, then DRC-4594. Each side's recomputed byte pins
are correct only for the tree they were computed on, so a textual merge of two web/ branches ships a
digest wrong for both.

---

## Stage Report: triage

- DONE: Capture the live Linear issue body and the owning milestone description verbatim under `## Linear edits made` as the pre-edit record, before drafting anything, and draft the rewrite of each beside it without writing either to Linear.
  Both captured in fenced blocks from `get_issue`/`get_milestone` reads on 2026-09-17; drafts sit beside them. Nothing written to Linear — the gate authorizes that write.
- DONE: Settle AC5 and AC4 against the repository's existing `aria-disabled` ruling at next-boot.js:385-386, and settle AC3 against `sessions.py:582` and `annotations.py:858`, rewriting or dropping each with the reason recorded rather than leaving an unsatisfiable criterion in the issue.
  R1 adopts `aria-disabled` for both controls (AC4, AC5 rewritten); R3 drops the producer half (AC3 replaced by a derivation check). Reasons recorded in the drafted History section, not deleted.
- DONE: Declare the expected surface with tolerance, costing the byte-pin oracles separately from the runtime, and say whether the producer-side change needs a new declared per-session field in its three declaration sites.
  Runtime 2 files ~24 net ±10; tests 1 file ~+130 ±60; oracles 3 files / 7 pinned figures, mechanical. No new declared field, and no change to an existing one — see "Producer-side declared fields".

### Evidence

- Byte pins are current, so the oracle cost is a recomputation and not a repair: `next-cockpit.js`
  198105 / `3c3fa0eb…` and `styles.css` 108008 / `ea8b79ed…` both match the figures asserted at
  test_next_page.py:682-707. Computed, not read off the test.
- The :5092 regex `r'reading-ask"[^>]*disabled'` was run against both attribute spellings: it matches
  `disabled` and `aria-disabled` alike. It therefore cannot witness R1 either way, and any new
  assertion must pin the full attribute name and the absence of the bare form. Run, not reasoned.
- `nextCockpitAskForReading` (:2438-2440) gates on `pending` alone and `nextCockpitHeldSave` (:2577)
  checks nothing — read in the tree. The browser's `disabled` is the only thing stopping a press
  today, which is why R1 cannot ship without the handler gates.

### Summary

The issue's diagnosis is exact — all ten line references check out against main @f83dd5f5 — and its
prescription is wrong in three places, each recorded in a dated History section rather than deleted.
The finding that changes the work is not in the issue at all: `aria-disabled` restores the click that
`disabled` was suppressing, and neither handler gates on the reason it renders, so implementing AC4
and AC5 literally would ship a button that spends the reader's model capacity from a state the page
says is unavailable. Dropping the producer half (R3) takes the change from 11 files to 6; the one
ruling that overturns a prior decision is R2, which inverts the second half of DRC-4565 AC7 while
leaving its load-bearing claim untouched.

### Evidence (continuation) — heading repair, 2026-09-17

The drafted criteria section was headed `## Acceptance criteria, with verification`, which
`--ac-scan` matches literally and so did not find. Renamed to exactly `## Acceptance criteria`
(this file, one heading line). The two `## Acceptance` headings under `## Linear edits made` were
left byte-identical: they are inside the verbatim capture of the Linear issue body, and renaming
them would falsify the restore point. No criterion, clause or offline/interactive mark changed.

Confirmed from the repo root:

    spacedock status --read drc-4588 --ac-scan --json --workflow-dir docs/roadmap-burndown
    {"command":"read","stage":"triage","acs":[]}   (exit 0)

The named error is gone. **`acs` is empty rather than populated, and that is not specific to this
entity:** the same command against `drc-4587`, whose criteria are already in the README template's
numbered-list shape, also returns `{"command":"read","stage":"triage","acs":[]}`. Two entities with
different criterion formatting and the same empty result, so the empty array is not caused by this
file's shape and reformatting the criteria here would be a guess rather than a fix. Raised to the
first officer rather than chased: writing scratch entities into the shared state checkout to bisect
the scanner is not safe with concurrent writers.

### Evidence (continuation 2) — criteria re-shaped to the parsed form, 2026-09-17

The criteria were prose paragraphs headed `**AC1 — …**` with `*Verified by (offline):*` and
`*Fails if:*`. They now read `- **AC-N — offline:** {property} **Verified by:** {…}
**Falsified by:** {…}`, one bullet per line, copied from a cleanly-parsing archived entity —
`_archive/drc-4020.md` lines 219-228 — rather than from a description of it.

**The cause was the unhyphenated id, not the bullet shape.** Corrected here 2026-09-17 after the
first officer settled it in an isolated throwaway workflow with four criterion shapes in one file:
`**AC-1 —` parses as a bullet, `**AC-3 —` parses as a bare paragraph, and `**AC4 —` does not parse
at all. Bullet versus paragraph and the styling of the `Verified by:` clause are both irrelevant;
the hyphen in `AC-N` is the whole rule. The re-shaping above therefore went further than it needed
to, which is recorded rather than reverted: the bullets parse, the words are unchanged in
substance, and churning a gated entity to restore the old markup would buy nothing.

The one earlier inference that did not hold: comparing this entity against drc-4587 and finding the
same empty result suggested a scanner-side cause. Both files carried unhyphenated ids, so two
samples of the same wrong shape could not discriminate between "my formatting" and "the scanner".
The conclusion that the heading rename had not caused it was sound; the rest was under-supported.

    spacedock status --read drc-4588 --ac-scan --stage triage --json --workflow-dir docs/roadmap-burndown
    acs: AC-1 (line 382), AC-2 (383), AC-3 (384), AC-5 (386), AC-4 (385), AC-6 (387)
    all unevidenced: true, citations: []

All six parse. `unevidenced: true` is the correct state at this gate — triage authors the criteria
and implementation supplies the citations, so nothing was added to make them look satisfied. The
two `## Acceptance` headings in the verbatim capture are still byte-identical, and there is still
exactly one `## Stage Report: triage`.

**AC-4 and AC-5 carry both an offline and an interactive half and are labelled `offline`**, because
the label takes one value and the binding half is the offline one: the attribute and the handler
gate are falsifiable in the harness, the screen-reader announcement is not. The interactive half is
stated inside each verifier and in the Split paragraph, so the declared split is unchanged from
what the gate was first shown.

### R2 — the scope of the DRC-4565 claim, checked

Raised because R2 changes a shipped contract. Confirmed from Linear: **DRC-4565 is Done**,
completed 2026-09-14, shipped in PR #330. Two findings bound how large the claim is, and both cut
against overstating it:

- DRC-4565's Linear body carries exactly two acceptance criteria — a durable record surviving the
  cue's expiry, and no discarded text inside it. **Neither is the withheld-offer claim.**
- No `drc-4565` entity survives in the state checkout or `_archive/`, so nothing on record says
  what that AC numbering ran against. The label "AC7" exists only in the test docstring at
  tests/test_next_cockpit.py:6540, and four unrelated docstrings in the same file (:7826, :7889,
  :8104, :8272) carry an "AC7" belonging to other issues.

So R2 overturns an implementation-stage test assertion that carries an AC label, not a criterion a
captain approved on the issue. Exactly two lines invert, :6554 and :6555, both from 0 to 1. It is
still a change to shipped behaviour in three states and belongs at the gate — but the entity should
not record it as overturning an approved acceptance criterion, because it is not one.

## Stage Report: implementation

- DONE: Write BOTH gate-approved drafts to Linear as the FIRST action before any code — DRC-4588's and DRC-4590's issue bodies, the owning milestone corrections, and any journey or move label named at triage — sending each body unwrapped as one line per paragraph, then read back each issue's relation set and report every edge the write created.
  Both bodies written verbatim, unwrapped; one milestone carries both corrections (4588's "present and inert", 4590's primary clause plus the split-out sentence); labels already correct on both and confirmed rather than changed; follow-ups DRC-4603 and DRC-4604 filed. Edge report below.
- DONE: Write the failing test first for each issue and watch it fail for the right reason, and for DRC-4588 specifically assert the rendered control does NOT match the bare disabled form, since the existing test_next_cockpit.py:5092 regex matches both spellings and cannot witness the change in either direction.
  12 new tests, all watched failing first. Re-verified at final shape by reverting the seven assets to 4fb5ee6d: 5/5 and 7/7 fail, 12/12 pass on the change. The bare-form negative is `assertNotRegex(refused, r'reading-ask"[^>]*\sdisabled[=>\s]')` beside `assertRegex(..., r'reading-ask"[^>]*\saria-disabled="true"')`; changing the emitter back to ` disabled` fails the first, dropping the attribute entirely fails the second.
- DONE: Regenerate every byte pin your changes move from the assets and re-run test_next_page, test_next_flag and test_focus each ALONE, reporting the pass ratio of each isolated run; recompute both size AND digest for every part, because next-cockpit.js has already kept its size across a digest change on this branch.
  Regenerated twice from the assets (never patched textually), the second time after the comment trim. Isolated: test_next_page 31/31, test_next_flag 7/7, test_focus 106/106. 6 part pairs + styles pair + assembled pair; 2 assembled-length and 3 assembled-digest assertions across the three files, matching AGENTS.md's count.
- DONE: Run the canonical pre-PR suite from AGENTS.md "Pre-PR Checks" read from that file rather than any copy, invoke sync-docs and commit its updates to this same branch, then measure the actual surface with git diff --numstat against the merge base and report files and LOC versus each issue's declared estimate with the percentage.
  Command list extracted from the worktree's own AGENTS.md. All green at load average 4.1: ruff, ruff format, mypy, lint_embedded, validate_plugins, bump_version --current (0.26.0, no version field moved), 3540 + 515 tests, coverage 86.8%. sync-docs updated design-next-ui.md (NUI-18), design-reader-state.md and SKILL.md, committed here. **Surface exceeds declared tolerance — see below.**
- DONE: Commit DCO signed off on branch spacedock-ensign/drc-4588 and STOP without pushing and without opening a pull request, reporting the branch name and candidate SHA.
  `spacedock-ensign/drc-4588` @ **2a073801**, signed off, 16 files / +720 / -91. Not pushed; no PR. Base is still 4fb5ee6d (PR 1 unmerged).

### Linear relation edges created

Read back after every write. Mentions create `relatedTo` only where no relation already exists.

- **DRC-4588** gained `relatedTo` **DRC-4390** and **DRC-4565**, both from bare tracker keys in the approved History prose. `blocks DRC-4594` unchanged.
- **DRC-4590** gained `relatedTo` **DRC-4381**, **DRC-4602**, **DRC-4561**, and `blocks` **DRC-4603** and **DRC-4604** from the follow-up filings. Its six **DRC-4587** mentions created no edge, because `blockedBy DRC-4587` already existed.
- **DRC-4603** (new): `blockedBy DRC-4590`, no `relatedTo`. **DRC-4604** (new): `blockedBy DRC-4590`, `relatedTo DRC-4602`.

### Two Linear hazards observed, reported rather than repaired

- **Emphasis boundaries moved on both bodies**, and on DRC-4590 one mark was **dropped entirely**: the bullet authored `* **`+ set a tripwire`**, the only way...` stored as `* `+ set a tripwire`, the only way...`. The measured rule is about an emphasis run ending immediately before a code span; this is the adjacent case, a run that *contains* one, and the serializer splits the run around it (`**Gate** `nextCockpitAskForReading` **on...**`) or loses it. Not repaired, per the standing instruction that repair provably cannot succeed.
- **The milestone `save_milestone` response echoed the pre-write description.** A fresh `get_milestone` confirmed both corrections landed. No retry was issued. The serializer also wrapped the existing DRC-4596 link target in angle brackets.

### Surface against the declared estimates

`git diff --numstat 4fb5ee6d` (the stacked base, which is this branch's real base; against the
`main` merge base the figure is contaminated by PR 1's commits).

| Layer | Declared (4588 + 4590) | Actual | Of declared |
|---|---|---|---|
| Runtime | ~33 net, ±25 | +88 net | **267%** |
| Tests | ~256 net, ±120 | +481 net | **188%** |
| Docs | ~30 net | +60 net | **200%** |
| Files | 13 | 16 | **123%** |
| **Total** | **~324 net, band 179–469** | **+629 net** | **194%** |

**This is beyond the combined tolerance band and needs a captain-visible decision before the PR
opens.** I did not open one, so nothing is committed to by this overrun yet. Three things drive it,
and they are different in kind:

1. **Comments, which the repository's own standard requires.** Runtime additions were 55% comment
   lines. I applied AGENTS.md's own remedy ("if the explanation runs longer than the code it
   explains, the reason belongs in `docs/design-*.md` and the comment shrinks to a reference"),
   which moved the durable rationale into NUI-18 and took runtime from +117 to +88 net and the
   comment share to 45%. The docs line doubles as a result. This is the estimate costing code lines
   where the standard costs both.
2. **Test comments and falsifiability.** `test_next_cockpit.py` is +327 net against a ~130 share.
   The stage requires each test to name what would make it fail, and several existing tests needed
   their claims restated rather than their numbers flipped. I have not trimmed these, because the
   falsifying clause is the thing the gate reads.
3. **Three files beyond the declared 13**, each compelled rather than chosen:
   `tests/test_next_controls.py` (an undeclared literal tag-shape assertion, `type="submit">add ↵`,
   which the class token splits), `docs/design-reader-state.md` (its own canonical rule: the refusal
   lane gained a case), and `SKILL.md` (one sentence, the user-visible half).

The declared-vs-actual gap is in the *estimate's model*, not in scope creep: no criterion was
widened, nothing outside AC-1..AC-8 was built, and both universal criteria stayed enumerated with
their remainders filed.

### Deferred, filed rather than promoted

Nothing was promoted into this branch. DRC-4603 and DRC-4604 carry the two scope reductions triage
made.

### Summary

Both issues are built on one branch, stacked on the unmerged PR 1, and the two halves that make
DRC-4588 safe shipped together: the control is `aria-disabled` so it keeps its place in the tab
order and can be described, and both handlers refuse on the same expression their control renders,
so the press the attribute restores cannot reach `/api/reading` or `/api/annotate` from a refused
state. The captain's condition is met at `test_next_cockpit.py`: the two inverted assertions carry a
replacement comment saying what superseded the withheld-offer decision and why, and the docstring
above them was corrected too, since it made the same claim. DRC-4590 collapses seven control rules
onto `.next-action`, marks the one tab that has an action to mark, and makes disabled dashed rather
than dimmer; both of its universal-sounding criteria are accepted on enumerated verifiers with the
remainders filed as DRC-4603 and DRC-4604. The suite is green (3540 + 515, coverage 86.8%) and the
three byte-pin oracles pass alone. The one thing needing a decision before the PR opens is the
surface at 194% of declared.

### Rebase onto main, 2026-09-17

PR 1 merged as `84d27a53`. `git rebase --onto origin/main 4fb5ee6d` — clean, candidate **1d847b0f**,
`origin/main` now an ancestor. Four conflicts, resolved by line rather than by side.

- **`styles.css`, two hunks, both adjacency rather than semantic.** Each mixed one line that had to
  come from `main` with one that had to come from mine. Took `main`'s reverted bodies for
  `.next-cockpit-held-absent` and `.next-cockpit-reading-stale` (PR 1's final round put both back to
  `--fs-xs`; I never edited either, so my side was only the stale base), and kept my
  `.next-cockpit-held-field button[aria-disabled="true"]` rule and my collapsed
  `.next-cockpit-reading button`. `.next-cockpit-reading button[disabled]` stays deleted: the
  primitive's disabled rule covers `:disabled` and `[aria-disabled="true"]` alike, and this control
  is the aria form now.
- **Three byte-pin files.** Markers resolved in place rather than by `checkout --ours/--theirs`,
  which would have dropped the cleanly auto-merged regions of those files, then every figure
  regenerated from the assets. `APP_PARTS` moved 0 (the rebase changed no JS); `styles.css` and the
  assembled page both moved. New: styles.css `111_658` / `19c58ec2…`, assembled `918_899` /
  `c64dcd86…` across 2 length and 3 digest assertions.

**The value-and-absence check, run on both branches through `tests/css_cascade.py`.** Seven control
pairs resolved through the real cascade in the DOM shape the page emits, including
`.next-cockpit-content`, which qualifies rules and changes what wins. Six pass. One reads OUTRANKED
and is **not a regression and not a ternary**: `.next-session-copy` resolves 11.5px against the rail
reason line at 12.5px, and it resolves 11.5px on `main` too, unchanged by this branch, because the
collapse kept its `font-size:var(--fs-2xs)`. The two are also different regions rather than the two
branches of one slot, so the comparison was a sweep rather than a pair. Recorded because it is a
real gap in the primitive's reach: `.next-action` promises the sentence tier and one of the seven
overrides it back down, which AC-1's verifier cannot see since it checks `border-radius` and
`border:1px` only. It belongs to **DRC-4604**, which already owns the control recipes the enumerated
set does not reach. Not promoted into this branch.

`AnAbsenceNeverOutranksTheValueItReplacesTest`, the guard PR 1 earned, passes.

**Green after the rebase**, at load average 20 with siblings running, which is the condition
AGENTS.md says manufactures failures: none appeared, and no module needed a confirming solo run
beyond the three oracles. Isolated: test_next_page 31/31, test_next_flag 7/7, test_focus 106/106.
Full 3541/3541 and scripts 515/515, coverage 86.8%. ruff, ruff format, mypy, lint_embedded,
validate_plugins, bump_version --current (0.26.0) all clean; no version field moved. My 12 tests and
the captain's replaced comment both survive the rebase. Surface unchanged at 16 files / +720 / -91.

## Stage Report: review

- DONE: State the chosen review depth and the diff property that justified it BEFORE reviewing, per AGENTS.md "Calibrating Effort".
  **Two lenses plus an arbiter**, stated before the first file was read: the diff touches `cargento_runtime/web/` (7 assets, so all three byte-pin oracles) and `SKILL.md` — two of the three named conflict-prone surfaces. Not security/credential/data-loss, so not full adversarial.
- DONE: Reproduce every acceptance criterion of BOTH issues from its own Verified by clause rather than trusting the implementation self-report, and settle any interactive criterion by a live drive or report it explicitly as not attempted.
  All six reproduced against a page I assembled myself, never the branch's assertions. AC-1/2/3 (one untouched-session render): `ask=1`, offer + disclosure present, counter `0`, and `3` from a `reading_count:3` fixture; the sentence occurs **once** and at index 830 against the button at 495. AC-4 driven through the real `document` click listener rather than the direct handler call the branch's own test makes — `calls=0`, `role="status"` carries the reason. AC-5: `<button … held-save … aria-disabled="true">` with no `hidden`, `posts=0`, and a keystroke clears the attribute with `redrew=false`. AC-6 settled by a **live drive** (board on `127.0.0.1:4571`, untouched session, Held to): `tabIndex=0`, `disabled=false`, `aria-describedby` → the extended reason, dashed 1px border, `cursor:not-allowed` — capture at `docs/screenshots/2026-09-17-review-pr362-drc4588-ac6-held-to-untouched-control-present-and-inert.jpg`. I also ran the inverse of AC-4/AC-5, because a gate that refuses everything passes every no-network assertion on the branch: a permitted save reaches `/api/annotate` exactly once.
- DONE: For every value-and-absence ternary this diff touches, resolve BOTH branches with tests/css_cascade.py and confirm no absence renders larger than the value it replaces; a test asserting an absence alone is not evidence.
  Seven pairs resolved on the branch **and** on `84d27a53`. Branch: 0 pairs where the absence outranks the value. Main: 1 — the reading button at 12.5px against its own reason paragraph at 15px, which this change removes by raising the button to the sentence tier. Reading button enabled vs `aria-disabled` is 15.0/15.0, held-save shown vs inert 12.5/12.5, held-absent 12.5 against a 14px textarea. Confirmed live with `getComputedStyle` too: solid `--accent` → dashed `--line2`, same 15px.
- FAILED: Read the Copilot inline review comments as well as any top-level review, confirm CI is green on the CURRENT head SHA with mergeStateStatus, and give a GO or NO-GO verdict without editing the branch.
  CI and the verdict are done; the Copilot half could not be: **no review of any kind exists on #362 and none was requested** (`reviews` empty, `pulls/362/comments` empty, `requested_reviewers: []`; the only comment is the coverage bot). Recorded as FAILED rather than SKIPPED because the check was not available to run, and requesting one is the FO's call — it blocked the merge on #361. CI: 12/12 checks `success` on `1d847b0f8a3b4c300ac293ac17d37b4ee19ed922`, read from that SHA's own `check-runs`, `mergeStateStatus: CLEAN`, `mergeable: MERGEABLE`. **Verdict: NO-GO**, one blocking finding. The branch was not edited.
- DONE: Write a `## Stage Report: review` into BOTH entity files, drc-4588 and drc-4590, each covering that issue's share — the advance guard is per entity and one report will block the group.
  This report and the one in `drc-4590/index.md`, each carrying its own issue's criteria and findings.

### The blocking finding — DRC-4588's own

**BLOCKER. The refusal sentence is printed twice, and then goes false under an enabled button.**
`next-cockpit.js:2491` writes the refusal into `nextCockpitReadingRequests`; `:2063` renders it in a
`role="status"` paragraph; `:2064-2066` renders the identical string again in the `aria-describedby`
target. Nothing ever deletes from that map — the only references are the declaration at `:5`, the
read at `:2036` and the two `set`s.

1. Press the inert control: the sentence goes from 1 occurrence to **2**, adjacent, both 15px/500.
2. Do what it says — save a goal. The button renders **enabled** and the live region beneath it still
   reads *"Nothing has been typed for this session…"*. Clearing it costs a reload or a paid reading.

Reproduced four independent ways: my offline harness, my live browser drive (screenshot
`docs/screenshots/2026-09-17-review-pr362-refusal-sentence-rendered-twice-after-a-refused-press.jpg`,
zero `/api/reading` calls), and both lenses separately. **Created by this branch** — on `84d27a53` the
early return deleted the control, so the press was impossible. Evidence fields: released user on the
newcomer path this issue exists for; observable harm is a false statement in an announced live
region; `value-ac[AC-2]` ("renders verbatim and exactly once") plus
`contract[docs/design-reader-state.md]`, whose rule for this lane is "a fresh press replaces the
response" — and there is no free fresh press from the enabled state. The fix is a condition in the
function the diff already rewrites; the byte pins then recompute, which this branch has done three
times.

### Filed, not promoted — DRC-4588's share

- **The inert `save` says nothing.** `nextCockpitHeldControl` emits `aria-disabled` with no
  `aria-describedby` and no sentence, and `nextCockpitHeldSave` returns at `:2639` silently. The
  comment at `:818-821` says it "says why it cannot fire" and NUI-18 says a refusal is "answered
  rather than dropped" — both are true of the reading control and false of this one. Not a
  regression: it replaces an absent control, and AC-5 asks only for present, inert and no POST.
  Separated from the live control by a 1.73:1 ink step, which is the failure NUI-18 condemns in its
  own words.
- **A new comment claims a verbatim match that does not hold.** `next-cockpit.js:1705-1712` says the
  sentence is the server's, "because `/api/reading` refuses with these same words". `reading.py:241`
  reads *"Nothing **is typed against** this session…"* against the page's *"Nothing **has been typed
  for** this session…"*. The string predates the branch; the claim is new, nothing binds the two, and
  it records a constraint a future editor does not actually have.

### Summary

The dangerous half of this issue shipped correctly. `aria-disabled` restores the click, and both
handlers refuse on the same expression their control renders — traced through argument provenance,
not asserted: renderer and handler both call `nextCockpitAnnotation(session)` and
`nextCockpitObserverModel(group)`, and dropping the `authorized &&` term is safe because every
unauthorized state returns a non-empty refusal. A press from a refused state reached no endpoint on a
live board. What leaked is the message the new gate leaves behind: printed twice, never cleared, and
false as soon as the reader does what it told them to. That is one fix in one function, and it is the
only thing between this PR and a GO.

### Correction round 1, 2026-09-17

One blocking finding, fixed. Candidate **bb56beb** on `spacedock-ensign/drc-4588`, not pushed.

**The regression, and why my own tests missed it.** The gate stored the refusal in
`nextCockpitReadingRequests` and nothing ever deleted from that map — `set` at three sites, `delete`
at none. This change made it reachable: the early return used to remove the control, so there was no
press to store. Reproduced here before fixing, both halves witnessed in one probe rather than one
assertion at a time: `afterPress: 2` (the sentence rendered as the stored message AND as the reason
paragraph, adjacent and identical) and `afterSave: 1` with `stillRefused: false` — the stale sentence
standing under a button the same render had enabled.

My AC-4 test asserted `role="status"` carrying the reason after a press, which is the duplicate, so
it encoded the defect as the expected result. AC-2 checked the untouched render, where the count is
correctly 1, and never pressed. Neither was wrong about its own clause; together they left the
interaction between them unasserted.

**The fix.** A refusal is a state rather than an event: marked `refusal: true`, dropped as soon as
the reason it names stops holding, and rendered through a single node — while a refusal stands it IS
the reason, so the announcement and the description are one paragraph carrying `role="status"` and
the id the button points at. A response stays an event and is kept, because "Reading received."
describes a press that happened rather than a state that holds.

**The mutation check found a defect in the test, not just in the code.** With the single-node render
in place, removing the clear left every rendered assertion green — a stale refusal can no longer
reach any render path, so the symptom is invisible while the entry lives forever. The test now
asserts the lane itself, and both halves are bound: removing the clear fails on `lingering`,
restoring the duplicate render fails on `afterPress`. Recorded because the first version of this
test would have passed over the second half of the finding it was written for.

**Also fixed:** `RuntimeDecisionCitationsTest` failed on a bare `AC-2` in a new comment, which the
grammar requires to be a full link with a heading anchor. The label is removed and the rule stated
instead, per AGENTS.md's "remove unnecessary labels rather than inventing archival headings".

**Green.** Oracles alone: test_next_page 31/31, test_next_flag 7/7, test_focus 106/106. Full 3542
and scripts 515, coverage 86.8%. ruff, ruff format, mypy, lint_embedded, validate_plugins,
bump_version --current all clean. Byte pins regenerated from the assets twice during this round
(the fix and then the comment edit both moved next-cockpit.js): assembled `920_003` / `5b00d698…`.
Surface now 16 files / +808 / −93. The four findings you filed were not touched.

### Correction round 1, the four small findings, 2026-09-17

The FO withdrew "do not fix these here" and cited the captain's standing directive: a small finding
is fixed in the PR in flight, and a fix is not a promotion. Candidate **9cc6f64**, not pushed.

- **The inert `save` comment claimed it "says why it cannot fire".** It does not; the gate returns
  silently. Corrected the comment rather than inventing the behaviour, because the box beside the
  control already shows the draft matches what is stored. The FO's framing decided it: the comment
  is the defect, not the silence.
- **A verbatim-match claim that does not hold.** The comment said the nothing-typed sentence is what
  `/api/reading` refuses with. `reading.REFUSALS` says "Nothing **is typed against** this session"
  where the page says "**has been typed for**". Checked in the tree rather than assumed. The discard
  arm directly above it *does* carry the server's string, which is what made the claim look right;
  the comment now says which is true of which.
- **`.next-stalled button:disabled` inherited the primitive's dashed border**, which NUI-18 defines
  as the register for refusing, on a control that is waiting for a retry it makes itself. Its
  `cursor:wait` already drew that distinction and the border contradicted it. Now states
  `border-style:solid`, and the AC-3 test that owns the criterion asserts it — mutation-checked:
  removing the override fails on `border-style:solid` not found.
- **A stale comment about this change's own effect.** The note above `.next-session-raise` said
  `.next-session-copy` never got a `:focus-visible` ring. It has one now, through `.next-action`,
  which closes the DRC-4381 gap that comment was describing. The raise keeps its own brighter ring,
  which is the distinction the comment exists for.

**Green.** Oracles alone: test_next_page 31/31, test_next_flag 7/7, test_focus 106/106. Full 3542 and
scripts 515. ruff, ruff format, mypy, lint_embedded, validate_plugins clean; docs tone clean. Pins
regenerated from the assets again, since both the comment edits and the CSS moved the bundle:
assembled `920_676` / `1127c596…`, styles.css `112_008` / `af33306f…`.

Branch now carries three commits: `1d847b0` (the feature), `bb56beb` (the regression), `9cc6f64`
(these four).
