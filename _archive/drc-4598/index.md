---
id:
title: "Re-expose the timeline's own filter instead of shipping one of its modes as a dead-end tab"
status: done
source: "https://linear.app/recce/issue/DRC-4598/re-expose-the-timelines-own-filter-instead-of-shipping-one-of-its"
started: 2026-09-17T11:07:58Z
completed: 2026-09-18T02:29:08Z
verdict: PASSED
score: 0.6
worktree: .worktrees/spacedock-ensign-drc-4592
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
        - id: gate:drc-4598:triage
          stage: triage
          attempts:
            - id: gate-attempt:drc-4598-triage-1
              briefing:
                id: briefing:drc-4598:triage:attempt-1:revision-1
                digest: sha256:e047a15d19b8b88c56ca09d82410ce1dba85e9513b101bf35e69d203c169e50a
                room-ref: ./review/triage/briefing-1
              resolution:
                type: Resolution
                id: resolution:spacedock:drc-4598:triage:1
                briefing: briefing:drc-4598:triage:attempt-1:revision-1
                by: agent:first-officer
                at: "2026-09-17T11:20:30.129046Z"
                decision: approve
                reason: 'Checklist 5 done / 0 skipped / 0 failed; AC-1..AC-8 resolve and all read unevidenced, which is correct at a triage gate. Both criteria the recon found unverifiable are dropped with reasons rather than carried as decoration: one had no offline path because the repository''s test shim is a node DOM with no layout engine and its remaining half was a process act rather than a property of the finished change, the other was a process obligation on a future issue and is replaced by a criterion that writes the route-change constraint where a merge proposer will actually meet it. The stage read DRC-4592''s seven approved criteria before writing its own, since both edit the same panel branch chain, and recorded the one adjacency and a third independent reason the relabel is rejected. It also avoided a self-citation that would have made its own report evidence its first criterion.'
                conn:
                    quote: I pre-approve all the triage and merge gates, just automate this entire process and do it
                    source: Captain, this session, 2026-09-17
              application:
                target-stage: implementation
                state: consumed
        - id: gate:drc-4598:review
          stage: review
          attempts:
            - id: gate-attempt:drc-4598-review-1
              briefing:
                id: briefing:drc-4598:review:attempt-1:revision-1
                digest: sha256:40e8fb4646231c4f27c1d275f3b64282b345569b4231b7b2b69a1879db5e8ae8
                room-ref: ./review/review/briefing-1
              resolution:
                type: Resolution
                id: resolution:spacedock:drc-4598:review:1
                briefing: briefing:drc-4598:review:attempt-1:revision-1
                by: agent:first-officer
                at: "2026-09-18T02:27:43.162923Z"
                decision: approve
                reason: 'Review returned GO. Its AC-2 was the criterion the storage collision violated verbatim, and the fix was proved in both directions on a live board with two real projects, with the seeded expectation that had encoded the defect as correct rewritten on a multi-project fixture rather than patched. PR #364 merged as f4561750.'
                conn:
                    quote: I pre-approve all the triage and merge gates, just automate this entire process and do it
                    source: 'Captain''s answer to the burndown dispatch question at the start of this session, reaffirmed as: if you approve that the PRs are good and can be merged, than go ahead and merge the PRs. do not gate on me.'
              application:
                target-stage: done
                state: consumed
archived: 2026-09-18T02:29:08Z
---

[DRC-4598](https://linear.app/recce/issue/DRC-4598/re-expose-the-timelines-own-filter-instead-of-shipping-one-of-its) — Re-expose the timeline's own filter instead of shipping one of its modes as a dead-end tab

Seeded 2026-09-17 from the live Linear read of the Clean and Cogent UI/UX milestone.
Linear owns the current issue body, its relations and its resources; triage fetches them
live and validates them against the tree before anything is built. No triage, approval,
implementation or delivery is claimed here.

# Triage — 2026-09-17

Measured against `spacedock-ensign/drc-4587` @ `a251ca4a`, not against `main`. That branch's
working tree is **dirty** (a sibling is mid-flight in `styles.css`, `test_next_cockpit.py` and
`docs/design-next-ui.md`), so every figure below was taken from `git show HEAD:` rather than from
the checkout. Line numbers are from the committed tree at that SHA.

## Linear edits made

Nothing has been written to Linear. The captured originals are the pre-edit record; the drafted
rewrites below are what `implementation` writes once the gate approves them.

### Captured original — DRC-4598 issue body (verbatim, 2026-09-17)

```markdown
## User value

A reader on the Decisions tab notices this when they want the other views. Today Decisions ships one mode of a three-mode timeline with the timeline's own filter suppressed, so the other two modes are unreachable.

## The Problem

Decisions is rendered by `nextCockpitDecisionSummary(...)` plus `nextCockpitTimeline(group, focus, "decisions")`, which reaches `projectSemanticTimeline` (project.js:1763). That renderer ships its own three-button filter — Active, All events, Decisions — which the cockpit hides by passing `controls:false`. So the cockpit promotes one of the renderer's three modes to a top-level route and makes the other two unreachable anywhere.

The cost shows in the measurement: Decisions holds 10 words, 1 sentence, 63 characters and zero interactive elements in a 93px panel, below roughly 500px of chrome that has not changed. Course is a different renderer over the same semantic fact substrate, and returns 29 words in 158px. Together with Now, three tabs buy 69 words and one control.

These are floors for a quiet, unannotated session, not a property of the tabs — which is exactly why the obvious fix, merging the three into one Activity tab, is **not** the right first move.

**Measured**

* next-cockpit.js:3329-3331 — the Decisions branch is `nextCockpitDecisionSummary(...)` + `nextCockpitTimeline(context.group, focus, "decisions")`
* mode `decisions` selects a different event source (`projectDecisionEvents` vs `projectGlobalEvents`), sets `controls:false` and injects an `eventPrefix`
* `projectSemanticTimeline` (project.js:1763) owns a three-button Active / All events / Decisions filter that the cockpit suppresses
* Measured: Decisions 10 words / 1 sentence / 63 chars / 0 interactive / 93px; Course 29 / 2 / 161 / 1 / 158px; Now 30 / 4 / 211 / 0 / 196px — 69 words and 1 control across the three
* Course renders two separate observations over two windows: "No state changes observed in the last 37m" and "No source-backed course changes observed in the last 24 hours"
* NUI-3 (docs/design-next-ui.md:123-129) normalizes retired fragments to Projects, and `nextRouteFromFragment` (next-boot.js:90-128) has no alias table, so a retired tab slug would be parsed as a session focus id
* `nextCockpitProjectScope()` (next-cockpit.js:2895) is dead code with no callers

**In the attached screenshot**

1. Whole panel: one label and one sentence, 93px
2. Decisions is one of the timeline's three modes
3. Its filter is suppressed with `controls:false`
4. Three tabs buy 69 words and one control

## The Solution

Do the reversible half now and price the rest.

Re-expose the filter the renderer already owns: render `projectSemanticTimeline`'s three modes as a `role="radiogroup"` of three buttons inside the Decisions panel — Everything, State changes, Decisions — defaulting to the current mode and persisting the choice in browser storage, so the other two modes stop being unreachable. This adds a control to a tab that has none and costs no route change.

Then measure the three thin panels on a **busy, annotated** project and attach the figures to this issue before anyone proposes merging the tabs: the 10/29/30-word figures are floors from one quiet session, and a merge sized to the empty state produces a single long scroll the moment there is anything to read.

If a merge is still wanted after that, price it as a route change, not a layout change: it needs a new alias branch in `nextRouteFromFragment` plus an amendment to NUI-3, because retired slugs currently fall through to the session-focus parse rather than redirecting.

Separately, delete `nextCockpitProjectScope()` at next-cockpit.js:2895 — it composes a sentence about the tab system and has no callers, so nothing it says has ever reached a reader.

## Acceptance

- [ ] The Decisions panel exposes all three timeline modes through the renderer's own control, with the selection persisted
- [ ] Word, sentence and control counts for Now, Course and Decisions are measured on a busy annotated project and recorded on this issue
- [ ] No route slug changes and no fragment behaviour changes in this issue
- [ ] `nextCockpitProjectScope()` is deleted
- [ ] Any subsequent merge proposal cites the busy-project figures and names the NUI-3 amendment it requires

---

Complaint **C3** · tabs: course, decisions · severity **minor** · effort **M** · blocked by DRC-4592

Raised from user feedback; mechanism and figures established by a measured audit of the live board and the shipped stylesheet.
```

### Captured original — milestone "Clean and Cogent UI/UX" description (verbatim, 2026-09-17)

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

### Drafted milestone correction

**No edit from this issue.** The milestone names "the timeline filter" in its *What is left* list, which
stays true, and its *How this was measured* paragraph already carries the two rulings this triage
depends on — that the density figures are floors from a quiet session, and that merging the three
thin tabs is a route change plus an NUI-3 amendment rather than a layout change. Nothing this issue
changes makes any sentence in the description false.

The one independently-false sentence, `Twelve issues.` (DRC-4602 was filed on 2026-09-17 and makes
it thirteen), is already claimed by DRC-4592's gate-approved triage. Restating it here would put two
sibling triages on the same line of the same shared record. Left alone deliberately.

### Drafted issue rewrite — DRC-4598

```markdown
## User value

Anyone mid-flight who opens Decisions and wants the wider view hits this. The Decisions tab is one
of three modes of a renderer whose own three-button filter the cockpit switches off, so the other
two modes — the filtered activity view and the all-events view — are reachable nowhere in the next
UI. Promise **P2** (what is it doing, and when should I come back?), move **sharpen**: the renderer
already draws all three; this stops hiding two of them.

## The Problem

`nextCockpitTimeline` (next-cockpit.js:3249) calls `projectSemanticTimeline` with
`{mode:"decisions", controls:false, eventPrefix:…}` at :3270-3272. Two things follow. The pinned
`mode` swaps the event source — `projectDecisionEvents` instead of `projectGlobalEvents`
(project.js:1769-1771) — and `controls:false` deletes the renderer's own filter at project.js:1790.
The cockpit promoted one of three modes to a top-level route and took the other two off the board.

The machinery to undo it is already installed and already inert:

* `projectSemanticTimeline` resolves its mode from `projectGraphModeBySession` (project.js:1767)
  whenever `options.mode` is not one of the three, so a reader-set mode needs no new state.
* `nextCockpitTimeline` already rewrites the filter's buttons for the cockpit's dispatcher:
  `.replaceAll('data-calm="project-graph-mode"', 'data-next-cockpit-action="graph-mode"')` at :3273.
  It matches nothing today, because `controls:false` emitted no buttons.
* The cockpit's `graph-mode` arm (next-cockpit.js:3553-3557) already accepts all three modes, writes
  `projectGraphModeBySession` and calls `renderNext()`.
* `nextCockpitTimeline`'s `mode = "active"` default parameter is dead — it has exactly one caller,
  which hardcodes `"decisions"`.

So three of the four pieces of the fix are already shipped and unreachable behind one flag.

Separately, `nextCockpitProjectScope()` (next-cockpit.js:2895-2901) has no callers. It composes a
sentence about how session selection filters the tabs that has never reached a reader.

## The Solution

Re-expose the filter the renderer owns, using the state and the dispatcher that are already there.

**Stop pinning the mode, stop suppressing the control.** Pass `{defaultMode:"decisions",
eventPrefix:…}` instead of `{mode:"decisions", controls:false, eventPrefix:…}`. `projectSemanticTimeline`
honours `options.defaultMode` in place of its `|| "active"` fallback, so an untouched Decisions tab
renders exactly what it renders today and a reader who presses a button gets the other two modes.
The panel heading follows the resolved mode rather than the caller's argument, so it stops saying
RECORDED DECISIONS over an all-events list.

**Keep the renderer's own labels and its own control shape.** Active / All events / Decisions, in
`role="group"` with `aria-pressed`. Not a `role="radiogroup"` and not a relabel — see *Rejected* below.

**Keep `eventPrefix` in all three modes.** It draws a per-event scope cue from `event.fact`, which
`projectGlobalEvents` sets on every event it builds (project.js:1463), so the cue is available and
useful in the wider modes too. Dropping it on mode change would silently lose which session an event
came from at exactly the point the list gets longer.

**Persist the choice across a reload.** `projectGraphModeBySession` is an in-memory Map; mirror it to
one `cargento.next.*` key so the mode survives a reload the way the workstream collapse does, and add
its row to `docs/design-reader-state.md` — the mode is reader-set state that survives a redraw and has
no row there today, which is a pre-existing gap this change makes load-bearing.

**Delete `nextCockpitProjectScope()`** at next-cockpit.js:2895-2901. Note the adjacent and very
similarly named `nextCockpitProjectScopeKind()` at :116 has 16 callers and must survive.

**Record the merge price where a future proposer will hit it.** Two sentences under
[NUI-3](docs/design-next-ui.md) stating that retiring a tab slug is a route change: `nextRouteFromFragment`
(next-boot.js:90-128) has no alias table, so a retired 3-part slug is parsed as a session focus id
rather than redirected. That puts the constraint on disk instead of in a comment thread.

## Rejected

**A `role="radiogroup"` of Everything / State changes / Decisions.** Three reasons, any one
sufficient. (1) `projectSemanticTimeline`'s filter is shared — it is also called bare from the legacy
project view at project.js:1956 — so relabelling it changes a surface this issue does not own.
(2) The proposed labels invert the modes: `active` is the *filtered* subset (`projectVisibleRegistry`
at project.js:1537 keeps only FO lanes and current lanes) and `all` is every lane, so "Everything"
over `active` is backwards. (3) "State changes" collides with `OBSERVED STATE CHANGES`, the Course
heading DRC-4592's acceptance pins unchanged at next-project.js:350 and next-workstream.js:421.
A correct radiogroup would also need `aria-checked` plus a roving tabindex; the existing
`role="group"` + `aria-pressed` is already the right shape for a filter toggle group, and swapping the
attribute without the keyboard model ships worse accessibility than it replaces. The issue's own title
asks to re-expose *the timeline's own filter*; substituting a different control is the opposite.

## Acceptance

See the entity's `## Acceptance criteria`.

---

Complaint **C3** · tabs: decisions · severity **minor** · effort **S** · blocked by DRC-4592

## History — superseded 2026-09-17 by triage

**The density figures are retired, not restated.** The issue as filed carried Decisions at
10 words / 1 sentence / 63 chars / 0 interactive / 93px, Course at 29 / 2 / 161 / 1 / 158px and Now at
30 / 4 / 211 / 0 / 196px, totalling "69 words and 1 control". Those were read off a live board on a
pre-DRC-4587 tree; DRC-4587 moved the type scale underneath every pixel figure. They were not
re-measured and are not acceptance criteria here. The attached screenshot
(`b1f81191-50b1-42f1-8c01-862192a6d426`) remains the only source for them, and the milestone
description already records that they are floors from one quiet session.

**One line reference moved; the other was never wrong.** NUI-3 was filed as
docs/design-next-ui.md:123-129 and is at :176 on the post-DRC-4587 tree. The
`next-cockpit.js:3329-3331` reference is exact on `main` @ `6702fb5c` and on
`spacedock-ensign/drc-4587` @ `a251ca4a` alike; a recon pass reported it as 3330-3331 and that
correction is itself the error.

**Two acceptance criteria were dropped rather than carried.** The busy-project measurement and the
merge-proposal obligation are not properties of this change; the reasons are recorded in the
entity's triage findings, and the constraint the second one existed to enforce is now written into
NUI-3 by this issue instead.
```

## Triage findings — checked against the code, not the prose

**The problem is still real, and every mechanism claim holds on the post-DRC-4587 tree.** Verified at
`a251ca4a` from the committed blobs: the Decisions branch at next-cockpit.js:3329-3330; the options
object at :3270-3272 carrying `mode:"decisions"`, `controls:false` and `eventPrefix`; the filter built
over `["active","all","decisions"]` at project.js:1790-1796 and suppressed by `options.controls === false`
at :1790; the event-source swap at project.js:1769-1771. DRC-4587 touched no line of either file — both
part digests are unchanged from `main`.

**The fix is three-quarters already shipped, which is why the estimate is S and not M.** This was the
recon's proposed cheaper alternative and it checks out in full:

* project.js:1767 — `projectSemanticTimeline` already falls back to
  `projectGraphModeBySession.get(String(projectQuerySession || "")) || "active"` whenever
  `options.mode` is not one of the three. No new state is needed for a reader-set mode.
* next-cockpit.js:3273 — the cockpit already rewrites the filter's `data-calm` attribute into its own
  `data-next-cockpit-action="graph-mode"`. That `replaceAll` matches nothing today. It was written for
  a control the same commit switched off.
* next-cockpit.js:3553-3557 — the `graph-mode` arm already accepts all three modes, writes the Map and
  redraws. Key agreement checked: the arm writes `projectGraphModeBySession.set(projectQuerySession, …)`
  and the renderer reads `.get(String(projectQuerySession || ""))`; `nextCockpitTimeline` sets
  `projectQuerySession = focus ? sessKey(focus) : ""` at :3264, so both sides agree at project scope
  and at session scope.
* `.pc-graph-filter` is already fully styled at styles.css:1164-1166, unscoped, so it renders correctly
  inside the cockpit with **no CSS change at all**. That drops `styles.css` from the file list and
  removes two byte pins the recon had budgeted.

**The default must be carried, and two existing tests are the oracle for it.** Without
`options.defaultMode`, dropping the `mode` pin makes an untouched Decisions tab resolve to `"active"`,
which swaps the event source and empties the decision rows. `test_decisions_view_preserves_canonical_metadata_and_compacts_scan_line`
(test_next_cockpit.py:2050) and `test_decisions_use_fact_scope_not_selected_session` (:1398) both assert
on `pc-graph-row` articles produced by `projectDecisionEvents`, so a default that resolved to `active`
turns them red. They are not repaired by this change — they are what proves it did not regress.

**No existing assertion forbids the filter, and the three that look like they do are on other routes.**
test_next_cockpit.py:1004-1006 (`SEMANTIC TIMELINE`, `graph-mode` and `project-graph-mode` absent) runs
on the **Course** route, where `nextCockpitTimeline` is not rendered; :1079 runs on **Now**; the
aria-pressed-count-zero assertion at :8083 runs on **Held to**. :2025's `data-arg="decisions"`, despite
its test name mentioning a "decisions filter", asserts on the tab button emitted at next-cockpit.js:2957.
Checked one at a time; none is a Decisions-panel contract.

**The `unwired_cockpit_actions` contract already passes and keeps passing.** test_contracts.py:881 requires
every rendered `data-next-cockpit-action` literal to have a dispatcher arm. `graph-mode` appears as a
literal in the `replaceAll` at :3273 and has its arm at :3553, so it is already in both sets. Making the
control reachable changes nothing this gate measures.

**`eventPrefix` is safe in all three modes.** It reads `nextCockpitFactScope(event.fact)`, and
`projectGlobalEvents` sets `fact` on every event it builds (project.js:1463). Keeping it is the decision;
dropping it on mode change would lose the per-event scope cue exactly when the list gets longer.

**The reader-state row is owed whether or not storage is added.** `projectGraphModeBySession` is a
module-level Map that survives a redraw and has no row in `docs/design-reader-state.md` today — a
pre-existing gap, invisible because the control is off. `ReaderStateInventoryTest`
(test_documentation.py:2201) derives only over lanes whose names carry Capture/Restore, so a missing row
is a review miss and not a red test. Adding the localStorage mirror makes the row unambiguous.

**The dead helper is real and its neighbour is not.** `nextCockpitProjectScope()` occupies
next-cockpit.js:2895-2901 and a repo-wide grep returns the definition and nothing else.
`nextCockpitProjectScopeKind()` at :116 has 16 call sites. A grep-and-delete on the shorter name is a
prefix match on the longer one.

**AC2 as filed is dropped, with the reason recorded.** It asked for word, sentence and control counts on a
busy annotated project, *recorded on this issue*. Three separate problems. The pixel half cannot be
reproduced in this repository at all: `tests/page_harness.py` drives `tests/page_worker.js`, a hand-rolled
node DOM shim with no jsdom, no browser and no `getBoundingClientRect`, so there is no layout engine to
measure against. The "recorded on this issue" half is a process act, not a property of the finished
change. And what the criterion existed for — stopping a merge being priced off empty-session floors — is
delivered durably by AC-6 below, which puts the constraint in NUI-3 where a proposer reads it, rather
than in a figure on a ticket that goes stale the next time the type scale moves. The floors are already
recorded in the milestone description and in the attached screenshot.

**AC5 as filed is dropped, with the reason recorded.** "Any subsequent merge proposal cites the
busy-project figures and names the NUI-3 amendment it requires" is an obligation on an issue that may
never be filed, and nothing in this repository can verify it. AC-6 converts it into an on-disk property:
the constraint is written into the design document the proposal would have to amend, where
`scripts/validate_plugins.py` resolves its anchor and a reviewer meets it.

**This issue and DRC-4592 edit the same branch chain.** Both change `nextCockpitPanel`'s dispatch region
in next-cockpit.js — DRC-4592 at the tab strip (`nextCockpitTabList`, :2949, and its call site at :3354)
and here at the Decisions arm (:3329-3330) — and both force the same part digest. Read against DRC-4592's
gate-approved acceptance, there is **no contradiction and one adjacency**:

* DRC-4592's AC-3 pins `OBSERVED STATE CHANGES` unchanged at next-project.js:350 and next-workstream.js:421.
  This triage's *Rejected* section refuses the "State changes" relabel partly for that reason, so the two
  agree rather than collide.
* DRC-4592 adds a per-tab derived cue counting `projectDecisionFacts` for Decisions. That cue counts
  decision facts and is independent of which timeline mode the panel is showing, so a reader on
  "All events" sees a Decisions cue that still counts decisions. Correct, and worth naming so a reviewer
  does not read it as drift.
* DRC-4592 touches `styles.css`; this issue does not. The `styles.css` pins move once, in DRC-4592's half
  of the PR.
* DRC-4592 is a blocker of this issue in Linear and lands in the same PR (PR 5 of 6, with DRC-4597).

**Nothing here needs a product decision that has not been filed.** No decision issue opened; not sent back
to `selection`.

**Labels.** `journey:mid-flight` and `move:sharpen` are already correct on the issue. No label change.

## Acceptance criteria

- **AC-1 — offline:** The Decisions panel renders the timeline's own three-button filter, and pressing
  each of the three buttons redraws the panel in that mode — `active` and `all` drawing from
  `projectGlobalEvents` and `decisions` from `projectDecisionEvents`. **Verified by:** a
  `test_next_cockpit.py` harness drive of `#n=project:cargento:decisions` asserting the
  `pc-graph-filter` element is present with three buttons carrying
  `data-next-cockpit-action="graph-mode"`, then clicking `all` and asserting the rendered row set
  changes and `data-graph-mode="all"` appears on the `pc-semantic-timeline` section; today the element
  is absent, so the first half fails. **Falsified by:** the panel rendering no filter, or a press that
  leaves `data-graph-mode` unchanged after a redraw.
- **AC-2 — offline:** A Decisions panel nobody has pressed a filter button on renders exactly what it
  renders today — decision rows from `projectDecisionEvents` under the RECORDED DECISIONS heading.
  **Verified by:** `test_decisions_view_preserves_canonical_metadata_and_compacts_scan_line`
  (test_next_cockpit.py:2050) and `test_decisions_use_fact_scope_not_selected_session` (:1398), both
  unmodified; they pass today and pass after the change. **Falsified by:** dropping the `mode` pin
  without honouring `options.defaultMode`, which resolves the untouched panel to `active`, swaps the
  event source at project.js:1769-1771 and empties the `pc-graph-row` sets both tests count.
- **AC-3 — offline:** The panel heading names the mode on screen: `RECORDED DECISIONS` in decisions
  mode and `SEMANTIC TIMELINE` in the other two. **Verified by:** a harness drive asserting the `<h2>`
  text after a press of `all` and again after a press back to `decisions`; today the heading is
  computed from `nextCockpitTimeline`'s hardcoded argument and cannot change. **Falsified by:** a
  heading that keeps saying RECORDED DECISIONS over an all-events list.
- **AC-4 — offline:** The chosen mode is written to one `cargento.next.*` storage key and read back on
  load, and `docs/design-reader-state.md` carries a row for it naming the lane and its owner.
  **Verified by:** a `test_next_cockpit.py` drive asserting the key appears in the harness's `__store`
  writes after a press, plus a second drive seeded with `storage={…}` asserting the first render takes
  the stored mode; and the row's presence in the inventory table. **Falsified by:** a press that writes
  nothing, a seeded store the first render ignores, or a lane added to the code with no row in the
  inventory.
- **AC-5 — offline:** `nextCockpitProjectScope(` appears nowhere in `cargento_runtime/web/`, and
  `nextCockpitProjectScopeKind(` still has its 16 call sites. **Verified by:** a grep-shaped assertion
  over the web sources for both names; today the first returns its definition at next-cockpit.js:2895.
  **Falsified by:** deleting the wrong name, which takes `nextCockpitProjectScopeKind` with it and turns
  the scope-cue assertions across the cockpit red.
- **AC-6 — offline:** `docs/design-next-ui.md`'s NUI-3 section states that retiring a tab slug is a route
  change, naming that `nextRouteFromFragment` has no alias table and parses an unknown 3-part slug as a
  session focus id. **Verified by:** the sentences' presence under the NUI-3 heading, and
  `scripts/validate_plugins.py` resolving the heading anchor any citation of it uses. **Falsified by:**
  the section not saying it, or saying it somewhere a merge proposal would not read.
- **AC-7 — offline:** No route slug changes and no fragment behaviour changes. **Verified by:**
  `git diff` showing `cargento_runtime/web/next-boot.js` untouched, and the existing route tests
  (`nextRouteFromFragment` coverage, including the four-tab / five-tab sets) re-run unmodified; they pass
  today. **Falsified by:** any edit to `NEXT_PROJECT_TABS`, `NEXT_SESSION_TABS` or `nextRouteFromFragment`.
- **AC-8 — interactive:** The chosen mode survives a real browser reload of the dashboard.
  **Verified by:** picking `All events` on Decisions at `127.0.0.1:4553`, reloading the page, and
  observing the panel come back in that mode. **Falsified by:** the panel returning to decisions mode
  after a reload. Declared interactive deliberately: `tests/page_worker.js` is a node DOM shim whose
  `localStorage` is a plain object, so AC-4 proves the key is written and read but not that a browser
  keeps it.

**User-visible criterion:** AC-1 is a property a user can see — three buttons on a tab that has none
today, and two views of the record that are reachable nowhere in the next UI.

**Interactive count:** one of eight, and it is the reload half of AC-4 rather than a criterion of its
own substance. No harness is proposed to automate it; a real-browser lane would be a milestone-sized
piece of work for one assertion about `localStorage`, which the shim already exercises in every other
respect.

## Expected surface and tolerance

**Runtime — ~25 net LOC across 2 files, ±40%.** The wide tolerance is deliberate: the storage mirror is
the only part whose shape is not already fixed by existing code, and it is also the only part that could
reasonably double.

| File | Change | Net LOC |
|---|---|---|
| `cargento_runtime/web/next-cockpit.js` | options object at :3270-3272 loses `mode`/`controls` and gains `defaultMode`; heading at :3275 follows the resolved mode; delete `nextCockpitProjectScope` (:2895-2901, **−7**) | ~+3 |
| `cargento_runtime/web/project.js` | honour `options.defaultMode` in the resolution at :1767; a small shared resolver so the cockpit heading and the renderer cannot disagree; load/save of `projectGraphModeBySession` against one storage key | ~+22 |

**Files NOT touched, against the recon's list:** `next-boot.js` (no route change — AC-7 pins this) and
`styles.css` (`.pc-graph-filter` is already styled unscoped at styles.css:1164-1166). Dropping them
removes three byte pins from the recon's budget, `styles.css`'s two and `next-boot.js`'s one.

**Semantics that may move:** which events the Decisions panel draws, once a reader presses a button; the
panel's own heading; one new browser-storage key. No payload field, no route, no new module. `sessions`,
`DECLARED_SESSION_FIELDS`, `events.PATCHABLE` and `history.OBSERVATION_FIELDS` are all untouched — this
reads what the renderer already computes.

**Oracles — costed separately, 7 pinned figures across 3 files.** Current values on
`spacedock-ensign/drc-4587` @ `a251ca4a`, read from `git show HEAD:` because that worktree is dirty.
Recompute from the assets; never resolve one of these textually.

| File | Figures |
|---|---|
| `tests/test_next_page.py` | `next-cockpit.js` part `198_105` / `16f67be92f133b9e837d137a96847723861a0128d4d91a0164ad63d9ab2190f6`; `project.js` part `106_941` / `8d404a66a0fe5a8a021854b64fc48c80aeed260628efadde80c64862d07ce63e`; assembled `914_344` (:710) and `2165bf68d82b7f98853561d56b3f0300240095a964bd040d74b080de45080ce6` (:711-714) |
| `tests/test_next_flag.py:67,69` | assembled `914_344` and `2165bf68…` |
| `tests/test_focus.py:1024` | assembled `2165bf68…`, inside `test_the_pinned_assembly_is_untouched` — a focus-meta test, and the copy most easily missed |

`styles.css`'s two pins (`111_050` / `91a303b22906b2f94fcd0f023a4c001388e840efa9f245d08e22822b1180b754`) and
`next-boot.js`'s (`27_352` / `b71d627f…`) do **not** move for this issue. DRC-4592 moves the `styles.css`
pair in the same PR.

**Existing-test repairs: zero expected.** Checked one at a time rather than assumed — the three
assertions that look like Decisions-panel contracts are on the Course, Now and Held to routes, and the
two Decisions-route tests are the AC-2 oracle and stay unmodified. If the implementation does need to
repair one, that is a signal the default mode was not carried and AC-2 should be re-read before the
test is edited.

**New behavioural tests — ~6 cases, ~130 LOC, all in `tests/test_next_cockpit.py`.**

**Doc surfaces — 2 edits.** One inventory row in `docs/design-reader-state.md` (AC-4) and two sentences
under NUI-3 in `docs/design-next-ui.md` (AC-6). Three further prose surfaces describe Decisions as
showing recorded decisions only — README.md:147, `cargento/skills/cargento/SKILL.md`:64 and
docs/design-next-ui.md:39 — and all three stay **true**: the tab still opens on recorded decisions, and
the filter is an opt-in widening. Leaving `SKILL.md` alone also keeps the shipped-skill validator out of
this change.

**Compelled-check survey.** No required check compels a new test file. No new module, so
`CARGENTO_RUNTIME_FILES` in `scripts/validate_plugins.py` is unchanged and no import-graph allowlist
applies; `scripts/lint_embedded.py` lints the edited JS in place; `ReaderStateInventoryTest` derives only
over Capture/Restore-named lanes, so AC-4's row is a **review** obligation and not a red test — which is
why it is written as a criterion. Editing `docs/design-next-ui.md` and `docs/design-reader-state.md` makes
this a `code=true` diff for the quality gate regardless, since the runtime cites heading anchors in both.
If a runtime comment cites an `NUI-N` or `D-N` label, `RuntimeDecisionCitationsTest` requires that exact
anchor to resolve.

**Approach chosen, and the simplest rejected alternative.** Chosen: stop pinning the mode and stop
suppressing the control, and let the existing Map, the existing dispatcher arm and the existing
stylesheet rule carry the rest. Rejected: the `role="radiogroup"` of Everything / State changes /
Decisions that the issue proposes. It cannot deliver more value than the chosen approach — both make the
same two modes reachable — and it costs a relabel of a control shared with the legacy project view
(project.js:1956), a label set that inverts `active` and `all`, a collision with the `OBSERVED STATE
CHANGES` heading DRC-4592 pins, and an `aria-checked` plus roving-tabindex keyboard model that the
existing `role="group"` toggle group does not need. Half-done, it ships worse accessibility than it
replaces.

**PR sequencing.** PR 5 of 6, with DRC-4592 and DRC-4597. Only one in-flight PR may touch
`cargento_runtime/web/`. DRC-4592 is a Linear blocker of this issue and edits the same
`nextCockpitPanel` chain; DRC-4597 governs `styles.css`. All three land as one PR against a `styles.css`
and an assembled page pinned once.

## Stage Report: triage

- DONE: Capture the live Linear issue body and the owning milestone description verbatim under `## Linear edits made` as the pre-edit record before drafting anything, and draft the rewrite of each beside it without writing either to Linear.
  Both captured from the live Linear read at the top of `## Linear edits made`; the issue rewrite is drafted under `### Drafted issue rewrite — DRC-4598` and the milestone under `### Drafted milestone correction`, which records a deliberate no-edit. No Linear write was made.
- DONE: Write the acceptance criteria into `## Acceptance criteria` as bullets shaped `- **AC-N — offline:** {property}. **Verified by:** {…}. **Falsified by:** {…}` — the scanner needs the exact heading, a HYPHENATED AC-N, and a bold label that closes on the line it opens.
  Eight criteria, each bold label closing on its opening line. One character deviates from the checklist text quoted above: its worked example names the first criterion by number, and this report writes that as `AC-N`, because quoting the number verbatim makes `--ac-scan` report the first criterion as evidenced by this very report. `status --read … --ac-scan` returns all eight, and all eight are expected to read as unevidenced at this gate — evidence is `implementation`'s and `review`'s to supply.
- DONE: Declare the expected surface with tolerance, costing the byte-pin oracles separately from the runtime, and measure every figure against the POST-DRC-4587 tree on branch `spacedock-ensign/drc-4587`, not against main.
  `## Expected surface and tolerance`: ~25 net LOC across 2 files ±40%, oracles costed separately at 7 figures across 3 files. Every figure read from `git show a251ca4a:` because that worktree's checkout is dirty in `styles.css`, `test_next_cockpit.py` and `docs/design-next-ui.md`.
- DONE: State plainly that this issue edits the same nextCockpitPanel branch chain as DRC-4592, whose triage is already gate-approved, and read that entity acceptance criteria before writing yours so the two do not contradict.
  Read all seven of `drc-4592/index.md`'s criteria before writing. Recorded under *This issue and DRC-4592 edit the same branch chain*: no contradiction, one adjacency worth naming (DRC-4592's Decisions cue counts decision facts and stays correct when the panel shows another mode). That entity's third criterion, which pins `OBSERVED STATE CHANGES` unchanged, is the third reason the "State changes" relabel is rejected here.
- DONE: Also settle AC2 and AC5, which the recon found are not verifiable in this repository at all.
  Both dropped with reasons recorded in the triage findings. The second criterion's pixel half has no offline path — `tests/page_worker.js` is a node DOM shim with no layout engine — and its "recorded on this issue" half is a process act rather than a property. The fifth is replaced by a criterion that writes the route-change constraint into NUI-3, where a merge proposer meets it.

### Summary

The issue's own diagnosis is right and its prescription is oversized. Three of the four pieces of the
fix are already shipped and inert: `projectSemanticTimeline` already falls back to
`projectGraphModeBySession` when no mode is pinned, `nextCockpitTimeline` already rewrites the filter's
buttons for the cockpit dispatcher, and the `graph-mode` arm already accepts all three modes. The work
is to stop passing `mode:"decisions", controls:false`, carry a `defaultMode` so an untouched tab renders
what it renders today, mirror the mode to storage, and delete the dead helper — ~25 net LOC across two
files rather than a new radiogroup.

The `role="radiogroup"` relabel is rejected on three independent grounds, the strongest being that the
proposed labels invert the modes: `active` is the filtered subset and `all` is everything, so
"Everything" over `active` is backwards. `styles.css` and `next-boot.js` drop out of the file list
entirely, taking three byte pins with them. Two existing Decisions-route tests are the oracle for the
default-mode regression and are deliberately left unmodified; zero test repairs are expected, and a
repair being needed is itself the signal that the default was dropped.

## Stage Report: implementation

- DONE: Built on the shared group branch, not its own.
  This issue is one of three in the tier-5 group (with DRC-4592 and DRC-4597); the full checklist
  report lives on `drc-4592/index.md`. Branch `spacedock-ensign/drc-4592`, candidate `43a8e9ba`.
- DONE: Gate-approved issue body written to Linear as the first action.
  Written unwrapped, one line per paragraph. Labels `journey:mid-flight` and `move:sharpen` were
  already correct, so no label write; no milestone edit from this issue, as its triage ruled.
  Relation edge created by the body write: **`relatedTo` DRC-4587**, read back after the write.
  Three emphasis runs containing a code span lost their mark at the span boundary
  (`**Keep** \`eventPrefix\``, `**Delete** \`nextCockpitProjectScope()\``, `**A** \`role="radiogroup"\``)
  and one relative link was wrapped as `(<docs/design-next-ui.md>)`. Reported, not repaired.
- DONE: All eight acceptance criteria satisfied, seven offline and one interactive.
  Six new cases in `CockpitTimelineFilterTest`, each written red first. AC-2 is proved by its two
  named oracles left unmodified: dropping `defaultMode` turns
  `test_decisions_view_preserves_canonical_metadata_and_compacts_scan_line` and
  `test_decisions_use_fact_scope_not_selected_session` red, measured. AC-8 (the mode surviving a
  real browser reload) is interactive by declaration and was not exercised: the node DOM shim's
  `localStorage` is a plain object, so AC-4 proves the key is written and read back and no more.
- DONE: Zero existing-test repairs needed on this issue's own surface, as triage predicted.
  One assertion did move, and it belongs to this issue: `assertNotIn("All events", …)` in
  `test_focus_keeps_project_status_and_canonical_labels_from_all_context` forbade the filter's own
  button text. Triage checked three assertions that looked like Decisions contracts and found them
  on other routes; it did not reach this one. Rewritten to assert what it was guarding — the panel
  still resolves to `decisions` with `all` unpressed — rather than deleted.

### Summary

Three quarters of the fix was already shipped and inert, exactly as triage read it. The work was to
stop passing `mode:"decisions", controls:false`, carry a `defaultMode`, add one shared resolver so
the panel heading and the renderer cannot disagree, mirror the mode to `cargento.next.graph.mode`,
and delete the dead `nextCockpitProjectScope`. `styles.css` needed nothing for this issue;
`next-boot.js` was not touched, and AC-7 pins that.

`project.js` came in at +30 executable lines against a declared ~+22 (±40% → 13–31), at the top of
its band. `docs/design-reader-state.md` gained the lane row and `docs/design-next-ui.md`'s NUI-3
gained the route-change constraint AC-6 asks for.

## Stage Report: review

Reviewed `spacedock-ensign/ui-integration` @ **2fa5a2f4** (PR #364), frozen. 12 checks pass on that
head, `mergeStateStatus` CLEAN. The group's shared evidence — byte pins, the capability-read fix, the
two refutations, the mutation method — is written out once on `drc-4592/index.md`.

- DONE: State the chosen review depth and the diff property that justified it BEFORE reviewing.
  **Two lenses plus an arbiter**, stated up front; justifying property, the `web/` byte pins and
  `SKILL.md`. I arbitrated by re-running every finding. The blocker below came from a lens and was
  confirmed by me on a live board, which is why it is stated as measured rather than reasoned.
- DONE: Reproduce every acceptance criterion from its own Verified by clause, against 2fa5a2f4.
  AC-1, AC-3 to AC-7 reproduce offline through `CockpitTimelineFilterTest` (6 cases, green). AC-2 has
  no method of its own by design: its oracles are `test_decisions_view_preserves_canonical_metadata_and_compacts_scan_line`
  and `test_decisions_use_fact_scope_not_selected_session`, both unmodified in `NextCockpitCompositionTest`,
  and I ran both. **AC-2 nonetheless fails on a live board — see FAILED.** AC-8 is interactive and is
  **settled PASS by live drive**.
- DONE: RUN THE FALSIFIER, NOT JUST THE VERIFIER.
  All this issue's falsifiers RED. `controls:false` restored → AC-1 red. A press that sets nothing →
  AC-1 red. `defaultMode:"active"` → **both** AC-2 oracles red, independently, which is exactly what
  that criterion claims. The heading hard-coded to `RECORDED DECISIONS` → AC-3 red. `projectStoreGraphModes()`
  dropped → AC-4 red. `projectLoadGraphModes()` dropped → AC-4 red. The prefix-collision delete
  (`nextCockpitProjectScopeKind(` → `nextCockpitProjectScope(`, all 15 sites) → AC-5 red. `alias table`
  removed from NUI-3 → AC-6 red. `NEXT_PROJECT_TABS` edited → AC-7 red.
- DONE: For every criterion, report which of three it is.
  **AC-2 is the group's worst category-(c): "a Decisions panel nobody has pressed a filter button on"
  is universal over panels and projects, and both oracles are single-project fixtures.** That is what
  let the blocker through green CI. AC-5's wording says "16 call sites" while the verifier asserts
  `assertGreaterEqual(…, 15)` — an honest documented amendment, not a gap: one of triage's sixteen was
  the call inside the helper this change deletes, and the live count is exactly 15. AC-1, AC-5, AC-7
  are (a); AC-3, AC-4, AC-6 are (b).
- DONE: Resolve rendered properties through tests/css_cascade.py down real element paths.
  No rendered-size property is at issue for this change — `.pc-graph-filter` was already styled
  unscoped and `styles.css` is untouched by this issue. Cascade work done for the group is on
  `drc-4597/index.md`. Nothing here was concluded by counting rules.
- DONE: Exclude the byte-pin oracles from every mutation check you run.
  Single-method or single-class selection throughout; one widening to `test_next_cockpit` only, whose
  collection count (319) I verified before trusting a SURVIVED.
- DONE: Re-derive every byte pin from the assets rather than from any list.
  `project.js` **109_267 / d1f78af9…**, `next-cockpit.js` **228_956 / 66b4f462…**, assembled
  **958_263 / 38818e11…**. All derived with `hashlib` off the assets and all matching the tree; full
  list on `drc-4592/index.md`.
- DONE: Scrutinise the integrator's self-caught regression and look for a second instance.
  Fix confirmed by four mutations against `ConsoleSetupNeverCallsAnUnreadCapabilityOffTest`. The
  second instance is DRC-4592's Decisions cue reading `.data` where the writer distinguishes failure
  with `.error`; recorded on that entity.
- DONE: Check the two refutations the integrator made rather than accepting them.
  **Both upheld, by execution**, and the first is this issue's line. `projectAction` occurs exactly
  once in the whole runtime — its own definition — and no `data-calm` / `dataset.calm` dispatcher
  exists anywhere; `next-cockpit.js:3705` rewrites the attribute to the cockpit's own action before
  render. The `arg === "all" ? "all" : "active"` collapse at `project.js:402` is genuinely
  unreachable. Both lenses reached the same conclusion independently. Worth deleting so a future
  `data-calm` dispatcher cannot resurrect it, but it breaks nothing today.
- DONE: Write a `## Stage Report: review` into EVERY entity file in your group, and give a GO or NO-GO without editing the branch.
  Written to all three. All mutation work in `/tmp/rv2-drc4592rv`, reverted and clean; the branch was
  never edited. The dashboard I drove ran from that throwaway worktree on port 4599 and was killed.
- FAILED: AC-2 is falsified on a live board. **This is the blocker.**
  See M1 below.

### Findings — this issue's share

**M1 (Material, task-owned, BLOCKING).** *The persisted graph-mode key carries no project, so one
press changes every project's Decisions tab and now survives a reload.*
`projectSetGraphMode` and `projectResolveGraphMode` key on `String(projectQuerySession || "")`. At
**project scope** `next-cockpit.js:3682` / `:3866` set `projectQuerySession = ""` — for every project.
The key is therefore the literal empty string, globally. Before this PR `projectGraphModeBySession`
was in-memory only, so the collision died with the tab; this change mirrors it to
`cargento.next.graph.mode`, so it persists and there is no UI that clears it.

Measured on a live board at 127.0.0.1:4599 serving the reviewed tree (assembled 958_263 / 38818e11,
verified before driving), in a real browser:

1. `#n=project:recce%2Fcargento:decisions` opened `RECORDED DECISIONS`, `data-graph-mode="decisions"`,
   22 rows, store empty. Pressed **All events** → `SEMANTIC TIMELINE`, mode `all`, 35 rows, store
   `{"":"all"}`.
2. `location.reload()` → mode still `all`, 35 rows. **AC-8 passes.**
3. `#n=project:recce%2Frecce-cloud-infra:decisions` — a different project, **never pressed** —
   opened `SEMANTIC TIMELINE`, `data-graph-mode="all"`, `all` `aria-pressed="true"`, `decisions`
   unpressed, store still the one global `{"":"all"}`.

Step 3 is AC-2 verbatim — *"A Decisions panel nobody has pressed a filter button on renders exactly
what it renders today"* — and it is false. Both of AC-2's named oracles pass because both are
single-project fixtures, and `test_the_chosen_mode_is_written_to_storage_and_read_back_on_load`
**seeds the collided key as correct** (`storage={KEY: json.dumps({"": "all"})}`), so the suite is
green over the defect. Two records also say the opposite of the behaviour: the key's own comment
(*"a reader who picked a mode on one session has not chosen one for every other"*) and the new
`docs/design-reader-state.md` row (*"kept per session key"* — there is no session key at project
scope). Evidence fields — released user and normal workflow: press a filter on one project, open
another; observable harm: the second project's Decisions tab opens in all-events mode with its
Decisions button unpressed, and a reload does not clear it; field 3: `value-ac[AC-2]` and
`value-ac[AC-4]`; trigger: the three steps above. Fix shape: put the project in the key
(`nextCockpitStableKey(group)` is in scope at both write sites), or resolve the project-scope
fallback separately from the session map. Found by Lens A on a two-project fixture; I confirmed it on
a live board rather than accepting the fixture.

**M2 (Material candidate, shared with DRC-4592).** With the timeline in `all` mode the tab reads
**"Decisions · 22 · 22 decisions"** and DRC-4592's lede says *"Decisions: rulings found in the
record…"* over a panel headed **SEMANTIC TIMELINE** showing **35** all-event rows; on the second
project, "0 / No decisions observed" over an all-events list. A count beside rows it was not derived
from is the frontend shared contract's own rule. Reachable without M1 the moment a reader presses
All events themselves, so fixing M1 does not close it. Lower severity, same round.

**Minor.** `nextCockpitTimeline`'s early return (`:3677-3681`) hard-codes `<h2>SEMANTIC TIMELINE</h2>`,
so an untouched Decisions tab reads SEMANTIC TIMELINE while loading and flips to RECORDED DECISIONS
when the context lands. AC-3 asserts the heading only after the context is present.

**Verifier note (V5).** `assertIn("all", written["store"][KEY])` cannot tell the value from the key:
writing the right mode to the wrong scope survives the method, and is caught only by siblings in the
same class. Given M1 that assertion is the one that should have been the oracle.

### Summary

Three quarters of this change was already shipped and inert, as triage read it, and the filter itself
works: three buttons, both other modes reachable, the heading following the resolved mode, the
untouched tab still resolving to decisions, and — proved on a real browser — the chosen mode
surviving a reload. AC-8 is settled PASS, not asserted.

The fourth quarter is the defect. Making the mode persistent without putting the project in the key
turned a per-tab quirk into a stored preference that silently rewrites every other project's
Decisions tab, and AC-2 — the criterion written precisely to catch a dropped default — could not see
it because both its oracles hold one project. The suite is green over it and one of its own tests
seeds the collided key as correct.

**Verdict: NO-GO.** M1 blocks the merge; M2 rides the same round. Findings route to `implementation`
with their evidence unchanged, never re-triaged. I fixed nothing and edited no branch.

## Stage Report: review (cycle 1 addendum — mutation re-verification)

Re-ran every SURVIVED verdict under the handed-over harness (7 semantic modules, 564 tests, byte-pin
oracles excluded by regex), each with a substitution-applied proof: target-string count before and
after plus the file's sha256 prefix. Baseline `ran=564 failures=0 errors=0`. **Nothing changes this
issue's verdict, and the blocker does not depend on a mutation at all.**

- DONE: Confirm your mutation actually applied before reading its verdict.
  Every case prints `APPLIED: <file> <sha-before>-><sha-after>; target N->M`. No no-ops occurred in
  either round. Two of my findings on the sibling issues were wrong for the inverse reason — a narrow
  selection hiding a guard — and are withdrawn on `drc-4592` and `drc-4597`. **M1 is unaffected: it
  was never a mutation result.** It is a live-board observation on an unmodified tree, so there is no
  substitution whose application could be in doubt.
- DONE: Re-verify this issue's survivor at full width.
  The AC-4 storage assertion's weak direction — a press writing the right mode to the **wrong scope**
  (`projectGraphModeBySession.set("some-other-scope", mode)`, applied-proof `project.js`
  `d1f78af91a95`->`ffa3c772e29b`, target 1->0) — is **KILLED at 564** by
  `test_the_decisions_panel_carries_the_filter_and_a_press_changes_the_mode` and
  `test_the_panel_heading_names_the_mode_on_screen`, both in this issue's own class. So V5 narrows to
  a within-method hygiene note: `assertIn("all", store[KEY])` cannot tell the value from the key, but
  its siblings can. Not blocking, and **not the gap that let M1 through** — that gap is AC-2's
  single-project fixtures, which no mutation at any width would have exposed, because the defect
  needs a *second project* to be visible at all.
- DONE: All of this issue's falsifiers re-confirmed applied.
  `defaultMode:"active"` -> both AC-2 oracles red; `controls:false` restored -> AC-1 red;
  `projectStoreGraphModes()` dropped -> AC-4 red; `projectLoadGraphModes()` dropped -> AC-4 red;
  the heading hard-coded -> AC-3 red; the 15-site prefix-collision delete -> AC-5 red;
  `NEXT_PROJECT_TABS` edited -> AC-7 red; `alias table` removed from NUI-3 -> AC-6 red.

### M4 (Material candidate) — the `nextCockpitContexts` check, and it reaches this issue's panel

The integrator asked for its own reasoning about this map to be checked. Checked by execution; it
does not hold. Full evidence on `drc-4592/index.md`; the part that is this issue's:

`nextCockpitLoadContext`'s **catch** arm (`next-cockpit.js:3187`) writes
`{data: settled && settled.data || null, revision, error:true}` — a **merge, not a replacement**. It
keeps the previous data and stamps the error over it, so a failed poll over an already-loaded context
produces a state `.data` alone cannot distinguish from a clean resolve. There is also a **third
writer**, `next-render.js:81` (the explicit observer refresh), which the earlier enumeration missed.

`nextCockpitTimeline` tests `entry.error` only **inside** its `!entry.data` branch (`:3676-3678`), so
in that state it renders the timeline from stale data and never says "Semantic context unavailable."
Executed: stale-with-error rendered 1 row with no unavailable notice, byte-identical to the resolved
render. **This half is pre-existing** — the same shape sits at the merge base `21a0e935:3363-3364` —
so it is not a regression this change introduced, but this issue owns the function and the fix is one
line: test `entry.error` before `entry.data`, as `nextCockpitAttentionCoverage` (`:433`) already does.

Filing it here rather than promoting it: it is not what blocks the merge, and the round M1 already
forces is the cheap place for it.

### The blocker, restated after re-verification

**M1 stands, unchanged and unmutated.** The graph-mode key is `String(projectQuerySession || "")`,
which is the empty string for every project at project scope, and this change persists it to
`cargento.next.graph.mode`. Measured in a real browser against a server serving the reviewed tree
(assembled 958_263 / 38818e11, verified before driving): pressing **All events** on `recce/cargento`
left `recce/recce-cloud-infra` — a project never pressed — opening its Decisions tab with
`data-graph-mode="all"`, `all` `aria-pressed="true"`, heading `SEMANTIC TIMELINE`, store `{"":"all"}`,
and a reload did not clear it.

That is AC-2 verbatim. No mutation is involved, so none of the re-verification touches it. Its two
oracles pass because both hold one project, and
`test_the_chosen_mode_is_written_to_storage_and_read_back_on_load` **seeds the collided key as
correct**, which is why 564 green tests and twelve green checks say nothing about it.

### Summary

The re-run corrected two findings on the sibling issues and none here. This issue's one verifier note
(V5) narrows to within-method hygiene, because its siblings kill the mutation at full width. What
none of it reaches is the blocker: a defect that needs two projects to be visible cannot be found by
mutating a one-project fixture at any width, which is the more useful lesson than the mutation
hygiene — **the fixture's shape, not the assertion's strength, is what hid M1.**

**Verdict unchanged: NO-GO.** M1 blocks the merge. M2 (the decisions count rendered beside
non-decision rows) and M4 (the stale-after-failure read in `nextCockpitTimeline`) ride the same
round. Findings route to `implementation` with their evidence unchanged; I fixed nothing and edited
no branch.

## Pre-registered check for the M1/M4 fix (written before the fix exists)

Not a report of work done. Written now, deliberately, so the pass conditions are fixed before the
fix is visible — the same reason a falsifier is written before the verifier. If this session is lost,
whoever takes the re-check inherits the conditions rather than re-deriving them from a green suite.

**Three things must hold. A fix that satisfies only the first is the fix the integrator was about to
write, and M4 says it is not enough.**

1. **The key carries the project.** Press a mode on project A, open project B untouched, and B must
   render `data-graph-mode="decisions"` with `decisions` `aria-pressed="true"`. Then press a mode on
   B and re-open A: A must still hold its own. Two projects, both directions — a fix that namespaces
   the key but resolves the fallback from the wrong scope passes the first half and fails the second.
2. **The map's five states stay distinguishable.** After the fix, seed `{data:<stale>, revision, error:true}`
   over a loaded context — the catch arm's shape verbatim — and both the cue and `nextCockpitTimeline`
   must say the context is unavailable. Today both render byte-identical to a clean resolve. A fix
   that only teaches the cue `.error` inside a `!data` branch does not move this, because `!data` is
   false in that state. Also check `next-render.js:81`, the third writer: a successful explicit
   refresh must clear `error`, and it does today — a fix must not regress that while adding a guard.
3. **The fixture must be able to fail.** A multi-project fixture is mandatory but not sufficient:
   `test_the_chosen_mode_is_written_to_storage_and_read_back_on_load` currently **seeds the collided
   key** `{"": "all"}` as the expected value. That seed must change, or the oracle keeps asserting the
   defect whatever the key becomes. Prove the new fixture can fail by mutating the fixed key back to
   the collided one and watching it red.

**Method, fixed in advance.** Every mutation under the handed-over harness at full width (564 + the
new cases, byte pins excluded), each with a substitution-applied proof — target count before and
after plus the file's sha256 prefix. Narrow selection is what produced two wrong findings in cycle 1;
the check does not repeat it. **And the fixture is checked against a live board, not instead of one:**
a real dashboard serving the fixed tree, two real projects, the assembled digest verified before
driving. The fixture's shape, not the assertion's strength, is what hid M1, so a fixture agreeing
with itself is not evidence.

**What would make me wrong.** If the fix removes the storage mirror entirely rather than keying it,
conditions 1 and 3 dissolve and only 2 remains — that is a legitimate answer to M1 (the mirror is
what turned a per-tab quirk into a persisted one) and should not be argued down for not matching
this plan. AC-4 would then need the captain, since it asks for the key by name.

## Stage Report: review (cycle 2 — re-check of the M1/M4 fix)

Re-checked at **26223372**. Pins re-derived from the assets before anything else: `next-cockpit.js`
**233_309 / b0e24842…**, `project.js` **110_869 / baae001e…**, `styles.css` **121_011 / f1d8a9bc…**,
assembled **964_336 / 387e71e0…**; all five pin sites agree with the tree. Harness baseline
`ran=577 failures=0 errors=0`. The three pre-registered conditions are the contract and all three
pass. **Verdict on this issue: GO.**

- DONE: **Condition 1 — the key carries the project, proved in BOTH directions.** PASS, on a live
  board with two real projects, store cleared first:
  1. `recce/cargento` Decisions opens `decisions` / RECORDED DECISIONS, store empty.
  2. Press **All events** -> `all`, store `{"project:recce/cargento":"all"}` — scoped, not `""`.
  3. `recce/recce-cloud-infra`, **never pressed** -> `decisions` / RECORDED DECISIONS / `decisions`
     `aria-pressed="true"`. **This is the step that failed before the fix.**
  4. Press **Active** on B -> store holds both keys separately.
  5. Return to A -> **still `all`**. The second direction holds.
  Falsifiers with applied-proof: reverting `projectGraphModeScope` to the collided key (`project.js`
  `baae001e206f`->`31dbdb5e1687`, target 1->0) reds 2 including the new two-project test; and
  **namespacing the write while resolving the read from the old scope** (`baae001e206f`->`fc37afcd8fa5`)
  reds **4**. That second one is the exact half-fix my pre-registration warned about, and it is caught.
  The per-session distinction survives: a focused scope resolves to `codex:focus-1`, the same shape
  the old code built, so a per-session choice migrates rather than being flattened by a project-only key.
- DONE: **Condition 3 — the fixture can fail.** PASS. The collided seed is **gone, not adjusted**:
  `{"project:cargento": "all"}`, with a comment saying why changing it is part of the fix rather than
  fallout. Proved able to fail — seeding `{"": "all"}` back (`test_next_cockpit.py` `6a11a06eb8e5`->`9871a80f1ce3`)
  reds `test_the_chosen_mode_is_written_to_storage_and_read_back_on_load`. A new
  `test_a_mode_pressed_on_one_project_does_not_follow_the_reader_to_another` covers both directions.
- DONE: **The legacy-entry hazard — checked, and it does not fire.** Measured live with storage set
  to exactly what an earlier build leaves, `{"": "all"}`, and nothing else: the Decisions tab opens
  **`decisions` / RECORDED DECISIONS**. The legacy key does not match a project, because the scope
  now resolves to `project:<name>` at project view. The only scope that still resolves to `""` is a
  non-project route (measured: `nonProjectResolves: "all"`), which is the legacy project view's
  pre-existing bucket and whose own control remains unreachable — `projectAction` still has no
  dispatcher. Not a regression.
  **One cosmetic residue, measured not reasoned:** the orphan row is immortal. After a press the store
  read `{"":"all","project:recce/cargento":"all"}`. `projectLoadGraphModes` validates values but not
  key shapes, so it loads the orphan and `projectStoreGraphModes` re-serializes the whole map. A
  key-shape filter in the loader would drop it and would also guard the next key change. Polish.
- DONE: AC-8 re-confirmed with the scoped key — `all` survives a real browser reload, heading
  SEMANTIC TIMELINE, store intact.
- DONE: Condition 2 (the five states) — PASS on the defect. Full detail on `drc-4592/index.md`.

### Still open on this issue

**M2 is not addressed, and correctly so.** Measured at the fixed head: with mode `all`, the tab still
reads **"Decisions · 22 · 22 decisions"** over a **SEMANTIC TIMELINE** heading. That is the same
question as the `stale` copy ruling — what a cue should say when the panel beside it is showing
something else — and the fix files that as DRC-4613 rather than inventing copy here. Right call; it
should not be promoted into this PR. Noting it so the gate sees it was measured, not missed.

### Summary

The fix is the one the criterion asked for and the halves were checked separately, which is what I
pre-registered because a write-only namespace passes the first half. It does not: reverting either
half reds the suite, and the live board shows a never-pressed second project opening on its own
default with the first project keeping its choice. The oracle that used to assert the defect now
asserts the fix and was proved able to fail.

**Verdict: GO** on this issue. M2 rides DRC-4613; the orphan row is Polish.

## Stage Report: review (cycle 3 — re-check at ddd422bf, the composite key)

Cycle 2 was run against `26223372` and the key changed under it, so those M1 results are void and
this supersedes them. Re-pointed to **ddd422bf**. Pins re-derived from the assets first: `project.js`
**111_842 / 0fcc61b6…**, `next-cockpit.js` **233_309 / b0e24842…**, `styles.css` **121_011 /
f1d8a9bc…**, assembled **965_309 / e79d000c…**, all agreeing with the three pin sites. Harness
baseline `ran=579 failures=0 errors=0`. **Verdict: GO.**

The key is now `${project}\u0000${session}` — both halves, session empty at project scope — and
`projectLoadGraphModes` drops any key that is not exactly one `\u0000`-joined pair.

- DONE: **Condition 1 — both directions, live board, two real projects**, store cleared first.
  1. `recce/cargento` Decisions opens `decisions` / RECORDED DECISIONS, store empty.
  2. Press **All events** -> `all`, store `{"recce/cargento\u0000":"all"}`.
  3. `recce/recce-cloud-infra`, never pressed -> **`decisions` / RECORDED DECISIONS**.
  4. Press **Active** on B -> both keys held separately.
  5. Return to A -> **still `all`**.
  Falsifiers, each with applied-proof and run at full width:
  - session-only (the original collided key), `0fcc61b60d78`->`97ade2e37e7c`: **4 red**.
  - **project-only key**, `0fcc61b60d78`->`89a24d84e24a`: **1 red**,
    `test_two_sessions_in_one_project_keep_their_own_modes`. This is the implementer's first caution,
    now guarded by a test rather than by a comment. A project-only key passes direction one and fails
    the per-session half, exactly as it warned.
  - namespace the write, resolve the read from the old scope, `0fcc61b60d78`->`0c93b99edc6f`: **5 red**.
- DONE: **The per-session half, verified live rather than only by mutation.** With project scope
  holding `all`, focusing a session in the same project and pressing `decisions` left the store
  holding two independent entries — `"recce/cargento\u0000": "all"` and
  `"recce/cargento\u0000claude:7985111d": "decisions"` — and project scope still resolved to `all`
  afterwards. Both halves of the composite key are in use on a real board, not only in a fixture.
- DONE: **Condition 3 — the fixture can fail.** The AC-4 seed is now composite
  (`{"cargento" + NUL_CHAR: "all"}`). Seeding the collided `{"": "all"}` back
  (`test_next_cockpit.py` `50090a837701`->`c9de45aa623b`) reds it. Gone, not adjusted.
- DONE: **The legacy-entry hazard — now closed rather than merely inert.** This is the one item that
  changed character since cycle 2, in the right direction. Measured live with storage seeded to
  `{"": "all", "codex:focus-1": "active"}`, both shapes an earlier build could have written:
  - Decisions opens **`decisions` / RECORDED DECISIONS** — neither legacy row leaks.
  - **After one press the store is exactly `{"recce/cargento\u0000":"all"}`.** Both legacy rows are
    *retired*, not carried. The immortal-orphan residue I filed as Polish in cycle 2 is fixed.
  - Falsifier: deleting the key-shape filter (`0fcc61b60d78`->`b5b63394feba`) reds
    `test_a_key_shape_this_build_cannot_parse_is_dropped_on_load`. The migration has its own guard.
  The separator choice is load-bearing and the comment says why: a scheme whose legacy empty key
  parsed as a real project would hand the old collision to the new key.
- DONE: **AC-8 re-confirmed at this head.** After a real browser reload the mode is still `all`,
  heading SEMANTIC TIMELINE, and both composite keys survive.

### Unchanged

**M2 is still open and still correctly out of scope** — measured again here: with mode `all` the tab
reads "Decisions · 22 · 22 decisions" over a SEMANTIC TIMELINE heading. Same question as the `stale`
copy ruling, filed as DRC-4613.

### Summary

The second commit answers the caution the first one's author left rather than the criterion alone:
the key carries project **and** session, so the per-session distinction survives, and the shape is
decidable enough that the loader can retire what an earlier build wrote. Three of the four runtime
falsifiers are shapes a reasonable fix could have taken — session-only, project-only, and write-only
namespacing — and each reds a different test, which is the property I wanted from the halves being
checked separately.

**Verdict: GO.** Nothing outstanding on this issue but M2, which belongs to DRC-4613.

## Stage Report: review (final — carry-forward check at c88cc110)

Applied the carry-forward rule I pre-registered before this commit existed, rather than the diffstat.
**Verdict: GO carries at c88cc110.**

- DONE: Re-derive the runtime assets. All four byte-identical to `ddd422bf`: `next-cockpit.js`
  **233_309 / b0e24842…**, `project.js` **111_842 / 0fcc61b6…**, `styles.css` **121_011 / f1d8a9bc…**,
  assembled **965_309 / e79d000c…**. Every pin site in `test_next_page.py`, `test_next_flag.py` and
  `test_focus.py` matches the derived values.
- DONE: **Apply the dependency rule, not the diffstat.** Both test files this commit edits hold
  classes my verdicts rest on, so "the runtime did not move" does not carry them on its own — that is
  the same mistake as reading a stylesheet digest to clear a verdict whose assertions live elsewhere.
  Byte-compared the eight classes by AST extraction at both heads. **All eight identical:**
  `CockpitTimelineFilterTest` (399 lines, `661af82a3473`), `CockpitTabsNameTheirPanelTest` (289,
  `d214c8a1eeb7`), `CockpitScopeRailCardTest` (220, `9b1f902ffeaf`), `WithheldTitleKeepsTheAbsenceInkTest`
  (55, `84713913781e`), `ConsoleSetupNeverCallsAnUnreadCapabilityOffTest` (244, `df8b9cb7aa70`),
  `NextCockpitCompositionTest` (4060, `451741e8e285`), `AnAbsenceNeverRendersLargerThanItsValueTest`
  (62, `4f0b64348eee`), `NextPageAssetContractTest` (1182, `a89452f01b14`).
- DONE: **Close the gap in my own rule.** A class-body hash misses a shared helper or module constant
  those classes call, which would move behaviour without moving the class. Hashed the non-class
  top-level of both test modules plus `next_harness.py`, `page_harness.py`, `css_cascade.py`,
  `js_literals.py` and `page_worker.js`. All seven identical across the two heads.
- DONE: Unconditional re-run. `ran=579 failures=0 errors=0`, the same count as `ddd422bf` — the +120
  test lines went into classes none of my conditions touch, which is consistent with a commit whose
  subject is another issue's branch matrix.
- DONE: CI on this head, read rather than assumed. 10 of 12 pass; `Tests (macos-latest)` and
  `Tests (windows-latest)` were still pending when I looked, and `mergeStateStatus` was `BLOCKED` on
  their absence rather than on a failure. The merge gate is the first officer's; recording the state
  I actually saw and the head it belonged to.

### Summary

Nothing my verdicts depend on moved: not the four runtime assets, not the eight test classes, not the
shared harness. I did not re-run the live two-project drive, and the reason is stated rather than
assumed — that drive measured runtime behaviour, and the runtime is byte-identical to the tree I
measured it on.

**GO carries at c88cc110**, subject to the two platform jobs finishing green.
