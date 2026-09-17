---
id:
title: "Always render the Held to reading control, disabled with its reason, instead of deleting the tab's only verb"
status: triage
source: "https://linear.app/recce/issue/DRC-4588/always-render-the-held-to-reading-control-disabled-with-its-reason"
started: 2026-09-17T06:57:18Z
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
                state: pending
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
