---
id:
title: "Make each tab name its own panel and carry a derived state cue"
status: review
source: "https://linear.app/recce/issue/DRC-4592/make-each-tab-name-its-own-panel-and-carry-a-derived-state-cue"
started: 2026-09-17T10:42:56Z
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
promise: "P2"
move: "sharpen"
estimate: ""
reconciled: ""
gates:
    version: 1
    records:
        - id: gate:drc-4592:triage
          stage: triage
          attempts:
            - id: gate-attempt:drc-4592-triage-1
              briefing:
                id: briefing:drc-4592:triage:attempt-1:revision-1
                digest: sha256:59f08b25f02a0f595c5047d41c2fc962aedd364f94a55e4a55421b62fa173c03
                room-ref: ./review/triage/briefing-1
              resolution:
                type: Resolution
                id: resolution:spacedock:drc-4592:triage:1
                briefing: briefing:drc-4592:triage:attempt-1:revision-1
                by: agent:first-officer
                at: "2026-09-17T10:54:08.329177Z"
                decision: approve
                reason: 'Checklist 4 done / 0 skipped / 0 failed; AC-1..AC-7 resolve. AC-4 was unfalsifiable as filed and now carries the five-row source-collection table the solution had promised, naming its three collections explicitly, with Held to''s source corrected from an authored constant to session.departures under the existing lane rule — which is the measured-invariant the repository already keeps about counting a structurally-present default. The recon''s largest risk was refuted against the tree rather than accepted: the context load already happens on every project-detail render before the strip is built, so the cue adds no fetch and this stays a presentational change.'
                conn:
                    quote: I pre-approve all the triage and merge gates, just automate this entire process and do it
                    source: Captain, this session, 2026-09-17
              application:
                target-stage: implementation
                state: consumed
---

[DRC-4592](https://linear.app/recce/issue/DRC-4592/make-each-tab-name-its-own-panel-and-carry-a-derived-state-cue) — Make each tab name its own panel and carry a derived state cue

Seeded 2026-09-17 from the live Linear read of the Clean and Cogent UI/UX milestone.
Linear owns the current issue body, its relations and its resources; triage fetches them
live and validates them against the tree before anything is built. No triage, approval,
implementation or delivery is claimed here.

---

# Triage — 2026-09-17

Measured against **`spacedock-ensign/drc-4587` @ `3cc7ef49`** (the tree PR 5 lands on), not `main`.
Worktree: `.worktrees/spacedock-ensign-drc-4587`. Nothing below was written to Linear.

## Linear edits made

**Nothing has been written to Linear. This section is the pre-edit record plus the drafts the
gate authorizes `implementation` to write.**

### Captured original — DRC-4592 issue body (verbatim, 2026-09-17)

```markdown
## User value

Anyone choosing where to look next notices this. Today the five tab names do not say what is behind them and carry no cue about whether anything is there.

## The Problem

A newcomer navigates by matching the label they clicked against the first thing they see, and that match fails on three of five tabs: Now opens onto GOING ON, Course onto OBSERVED STATE CHANGES, Held to onto WHAT YOU ASKED FOR. "Held to" is a grammatical fragment and the word "held" appears nowhere in the panel.

The strip itself is five bare mono labels; the only difference between selected and unselected is a 2px border colour and ink3 to ink. Behind those identical labels the content ranges from 63 to 2132 characters, and three of the five destinations have zero or one interactive element, so a reader has no way to rank them before clicking.

The figure that would have told them already exists and is filed behind the click: Course's own panel header carries "0 of 0 unattended · last 37m". On top of that the cockpit uses a private vocabulary — departure, raise, reading, revision, observed record — that is nowhere resolved on screen.

**Measured**

* Tab-to-first-heading mismatch on three of five: Now → GOING ON; Course → OBSERVED STATE CHANGES; Held to → WHAT YOU ASKED FOR. Decisions and Console echo their labels
* styles.css:710-713 — `.next-cockpit-tabs button` renders label text only, `color:var(--ink3)`, `font:var(--fs-sm) var(--mono)`; selection is `border-bottom-color:var(--ink2)`
* Content behind the five labels: 211 / 161 / 63 / 1059 / 2132 chars; interactive elements 0 / 1 / 0 / 5 / 4
* Course capture: "0 of 0 unattended · last 37m" is right-aligned in the OBSERVED STATE CHANGES header at y≈532, 28px below the tab strip at y≈504 — inside the panel the tab gates
* The strip is four tabs at project scope and five only with a session in focus (next-boot.js:48, 59); styles.css:1126 grids four columns at narrow widths
* `nextCockpitPanel` (next-cockpit.js:3311-3344) builds only the selected tab's body from three or more independent sections, so `nextCockpitTabList` (:2949) currently has no collection to count
* `nextCockpitNowState` (:2975-2991) renders three fixed divs and no session collection

**In the attached screenshot**

1. Tab "Course" opens onto OBSERVED STATE CHANGES
2. "0 of 0 unattended · last 37m" sits inside the panel
3. Five bare labels, 14px mono, no count or state cue
4. Decisions: 10 words, 63 chars, 0 controls, 93px

## The Solution

Two halves.

**Complete the labels rather than renaming them.** Add a one-line lede under the strip on every tab, at the sentence tier in ink2, each naming its tab word: "Now: what is running in this project this minute, and how sessions here have ended"; "Course: direction changes Cargento observed in the session record"; "Held to: what you asked this session for, and how its record measures against it". Define the three load-bearing nouns inline at first use — at the DEPARTURES header, "A departure is a place the record does not match what you typed"; at READING, "A reading is one model pass over the record, made only when you press for it"; beside the revision stamp, "Each save is a revision".

Do **not** rename OBSERVED STATE CHANGES — it is emitted from next-project.js:350 and next-workstream.js:421, shared with the workstream view, and the panel reports state changes (37m) and source-backed course changes (24h) as two separate measurements.

**Put a derived cue on each label, with four states, not three:** `{count}` from the collection the panel maps over, `0` for a collection read and empty, `·` for one never published, and a dimmed `…` while the async context has not arrived — rendering `·` there would assert an absence the board has not established. Name the source collection per tab in a table; Now and Console take no cue, since neither renders a countable collection. Each state carries a visually-hidden gloss.

## Acceptance

- [ ] Every tab renders a lede naming the tab word and what the panel holds
- [ ] Departure, reading and revision are each defined once, inline, at first use
- [ ] OBSERVED STATE CHANGES is unchanged and both Course measurements keep their own window
- [ ] Each cue reads `.length` from the collection its own panel renders; no cue is authored and none falls back to 0 when the collection is undefined
- [ ] A tab whose context has not loaded shows a distinct pending mark, never the not-observed mark
- [ ] Now and Console render no cue rather than a fabricated one

---

Complaint **C3** · tabs: all · severity **major** · effort **M** · blocked by DRC-4587, DRC-4589

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

**One line, and only one.** The issue's rewrite falsifies nothing in the milestone: "the tab strip" is still
listed under *What is left* and the foundations are unchanged. One sentence is independently false —
`Twelve issues` — because DRC-4602 was filed on 2026-09-17 from DRC-4587's implementation and rides PR 6.
Change `Twelve issues.` to `Thirteen issues.` and leave every other word alone. Nothing else in the
description is touched by this issue, and widening the edit would collide with five sibling triages.

### Drafted issue rewrite — DRC-4592

```markdown
## User value

Anyone mid-flight who is deciding where to look next hits this. The five cockpit tab names do not
say what is behind them and give no cue whether anything is there, so the reader clicks to find out.
Promise **P2** (what is it doing, and when should I come back?), move **sharpen**: the tabs already
reach the right panels; this makes the choice between them readable before the click.

## The Problem

A newcomer navigates by matching the label they clicked against the first thing they see, and that
match fails on three of five tabs: Now opens onto GOING ON, Course onto OBSERVED STATE CHANGES,
Held to onto WHAT YOU ASKED FOR. "Held to" is not authored at all — `nextCockpitHumanLabel`
(next-cockpit.js:273-276) turns the route token `held-to` into a sentence fragment by replacing
`[-_]` with a space and capitalising, and the word "held" appears nowhere in the panel.

The strip is five bare mono labels. Post-DRC-4587 the only selected/unselected difference is still a
2px border colour and `--ink3` → `--ink` (styles.css:719-720), so a reader cannot rank the five
destinations. The figure that would rank Course is already derived and filed inside the panel the
tab gates: `project.changeNoteText`, built at next-observed.js:211 as
`${changes.filter(c => c.filled).length} of ${changes.length} unattended · …`, renders in the
OBSERVED STATE CHANGES header at next-project.js:350-351.

On top of that the cockpit uses a private vocabulary — departure, reading, revision — that is not
resolved where it is first used.

## The Solution

Two halves, and no renames.

**A lede per tab.** One line under the strip on every tab, at `--fs-sentence` in `--ink2`, each
naming its own tab word:

| Tab | Lede |
|---|---|
| Now | Now: what is running in this project this minute, and how sessions here have ended. |
| Course | Course: direction changes Cargento observed in the session record. |
| Decisions | Decisions: rulings found in the record, and what each one has been spent on. |
| Console | Console: the read-only terminal of one selected session, and the controls for it. |
| Held to | Held to: what you asked this session for, and how its record measures against it. |

The lede needs its own stylesheet rule. `.next-cockpit-scope-note` (emitted at next-cockpit.js:3320)
has zero matching rules in `styles.css` and renders as an unstyled paragraph today; a lede added the
same way would look like a defect.

Define the three load-bearing nouns inline at first use: at the DEPARTURES RAISED TO YOU header
(next-cockpit.js:1782), "A departure is a place the record does not match what you typed"; beside the
revision stamp (`next-cockpit-held-revision`), "Each save is a revision"; and at the READING header,
a definition of a reading **only if `NEXT_READING_OFFER` (next-cockpit.js:2027-2030) does not already
render there** — it already says what a reading reads, and a second sentence saying the same thing is
a regression, not a fix.

Do **not** rename OBSERVED STATE CHANGES. It is emitted from next-project.js:350 and
next-workstream.js:421, shared with the workstream view, and the panel reports state changes (37m)
and source-backed course changes (24h) as two separate measurements.

**A derived cue per label, four states.** `{count}` from the collection that tab's own panel maps
over; `0` for a collection read and found empty; `·` for a collection the board has never published;
a dimmed `…` while the context carrying it has not arrived. Each state carries a visually-hidden
gloss (`.next-visually-hidden` already exists at styles.css:54). A tab whose panel renders no
countable collection takes no cue at all rather than a fabricated one.

### Source collection per tab

| Tab | Collection the cue counts | The panel section that maps over it | Availability |
|---|---|---|---|
| Now | *none* — `nextCockpitNowState` (:2975-2991) renders three fixed divs | — | no cue |
| Course | `context.project.changes` | `nextProjectChanges` (next-project.js:344-361) maps over exactly this array | synchronous, from `nextData` |
| Decisions | `projectDecisionFacts(canonical)` off the same `semantic` `nextCockpitDecisionSummary` selects (next-cockpit.js:3075-3086) | the list `nextCockpitCaptainDecisionCounts` iterates and the RECORDED DECISIONS timeline draws | project-scope context |
| Console | *none* — a terminal surface and controls, no countable collection | — | no cue |
| Held to | `session.departures`, resolved by the existing lane rule at next-cockpit.js:1771-1780 | DEPARTURES RAISED TO YOU (:1757-1788), reached on both return paths of `nextCockpitReading` | synchronous, from `nextData` |

Held to takes **no** cue when `nextData.annotate !== true`: that panel renders no collection at all,
which is the same rule Now and Console are under, not an absence to assert with `·`.

Copy the four-state discipline from next-cockpit.js:1771-1780 rather than inventing one. The lane
there yields `null` instead of `0` precisely because a length read off a list `base_session` declares
empty on every row would report the schema (DRC-4559, and AGENTS.md's first Measured Invariant). A
cue that falls back to `0` reproduces that exact defect.

`nextCockpitTabList()` (:2949) takes no arguments today and is called bare from `nextProjectCockpit`
(:3354), where `context`, `focus` and `observation` are all in scope. It must keep resolving its tab
set from `nextRoute.focus`, as the comment at :3312-3315 requires, so the nav and the panel cannot
disagree about which tabs exist.

## Acceptance

See the entity's `## Acceptance criteria`.

---

Complaint **C3** · tabs: all · severity **major** · effort **M** · blocked by DRC-4587, DRC-4589

## History — superseded 2026-09-17 by triage

The issue as filed (2026-09-17 02:21 UTC) carried a `**Measured**` block of live-board figures —
per-tab content of 211 / 161 / 63 / 1059 / 2132 characters, interactive-element counts of
0 / 1 / 0 / 5 / 4, the Course header at y≈532 against the strip at y≈504, and Decisions at 10 words
/ 63 chars / 0 controls / 93px — together with `styles.css:710-713` and `styles.css:1126` line
references. Those figures were taken on the pre-DRC-4587 tree. DRC-4587 moved the type scale
underneath them and the stylesheet line numbers to :719-721 and :1134. The structural claims all
re-confirmed against `spacedock-ensign/drc-4587` @ `3cc7ef49`; the pixel and character figures were
not re-measured and are retired rather than restated. The attached screenshot
(`7dafae0f-06a6-4067-b4b0-a1fac42a086f`) remains the only source for them.

The original solution promised "Name the source collection per tab in a table" and contained no
table. The table above is that repair.
```

## Triage findings — checked against the code, not the prose

**The problem is still real.** `.next-cockpit-tabs button` (styles.css:719) still emits label text
only, `color:var(--ink3)`, `font:var(--fs-sm) var(--mono)`, with selection carried by
`border-bottom-color:var(--ink2)` and `color:var(--ink)` at :720. `nextCockpitTabList()` at :2949
still emits `>${label}</button>` with no cue slot. All three heading mismatches confirmed at source:
GOING ON (next-activity.js:62), OBSERVED STATE CHANGES (next-project.js:350, next-workstream.js:421),
WHAT YOU ASKED FOR (next-cockpit.js:2410). DRC-4587's `next-cockpit.js` diff touched only
`nextCockpitLanded` and `nextCockpitHeldTo` headers; every line number the recon cited in that file
is unmoved.

**The recon's largest risk does not exist.** The recon warned that a Course or Decisions cue on an
unselected tab would sit at the pending mark forever, or else force the strip to issue network
requests for panels nobody opened. Measured: `next-project.js:386` already calls
`nextCockpitLoadContext(group, null)` unconditionally on every project-detail render, and only then
builds `nextProjectCockpit` at :397, which calls `nextCockpitTabList()`. The project-scope context is
therefore already requested on every tab, including Now and Console. **The strip issues no fetch of
its own, and no fetch is added.** The Decisions cue resolves from a round-trip the board already
makes; `nextCockpitWorkSource` already falls back to that same project entry.

This also kills the only expensive alternative. Warming the context *from the strip* would have cost
one `/api/project-context` per project per payload — `aggregate.py:851` sets `"generated": now`, so
`settled.revision >= revision` fails on every payload, and payloads arrive every 5–20 s
(`NEXT_UNCOORDINATED_POLL_MS` / `NEXT_FALLBACK_POLL_MS`, next-live.js:8-9). Rejected: it buys nothing
the existing call already buys.

**Held to's cue is departures, not held fields.** `NEXT_COCKPIT_HELD_FIELDS` is an authored constant;
counting it would be the authored cue AC-4 forbids. `session.departures` is the collection the panel
actually renders, it is synchronous from `nextData`, and next-cockpit.js:1771-1780 already holds the
measured rule for reading it honestly. Both return paths of `nextCockpitReading` (:2068 and :2129)
append `nextCockpitDepartures`, and `nextCockpitReading` is unconditional in Held to's evidence
chain, so the section is always rendered when a session is focused and annotations are on.

**Nothing here needs a product decision that has not been filed.** No decision issue opened; not sent
back to `selection`.

## Acceptance criteria

- **AC-1 — offline:** Each of the five tabs renders exactly one lede paragraph directly under the
  tab strip, whose text contains that tab's own label word and names what the panel holds.
  **Verified by:** a `tests/page_harness.py` drive per tab asserting the lede element is present once
  and its text starts with the tab word; today no lede element exists on any tab, so all five fail.
  **Falsified by:** rendering a tab with no lede, with two, or with a lede whose text omits its own
  tab word.
- **AC-2 — offline:** "Departure" is defined at the DEPARTURES RAISED TO YOU header and "revision"
  beside the revision stamp, each exactly once per rendered panel, and the reading definition is not
  duplicated where `NEXT_READING_OFFER` already renders. **Verified by:** a harness drive of Held to
  asserting each definition string occurs exactly once in the panel HTML, and asserting the
  `NEXT_READING_OFFER` text occurs exactly once. **Falsified by:** a second copy of any of the three
  sentences, or a definition rendered somewhere other than the first use of its noun.
- **AC-3 — offline:** The string `OBSERVED STATE CHANGES` is unchanged at next-project.js:350 and
  next-workstream.js:421, and `changeNoteText` still carries two separately-windowed measurements.
  **Verified by:** the existing workstream and project tests plus a grep-shaped assertion that both
  emitters still produce the literal; they pass today. **Falsified by:** renaming the heading at
  either site, or collapsing the 37m and 24h windows into one figure.
- **AC-4 — offline:** Each cue on Course, Decisions and Held to reads `.length` from the collection
  named in the source-collection table for that tab — `context.project.changes`,
  `projectDecisionFacts` off the semantic `nextCockpitDecisionSummary` selects, and
  `session.departures` under the lane rule — and no cue is authored or defaults to `0` when its
  collection is absent. **Verified by:** varying each fixture collection's length across at least
  three values and asserting the rendered cue moves with it, plus the Measured-Invariant check that
  the cue reads differently when nothing happened than when something happened and found nothing;
  no cue exists today, so every case fails. **Falsified by:** a cue that holds steady while its
  fixture collection grows, or that renders `0` when the collection is `undefined`.
- **AC-5 — offline:** A tab whose source context has not arrived renders the dimmed pending mark,
  and a tab whose collection was published-and-never-filled renders the not-observed mark; the two
  marks are different characters and carry different visually-hidden glosses. **Verified by:**
  withholding the `nextCockpitContexts` entry so the render takes the "Loading semantic context…"
  arm and asserting the pending mark, against a fixture publishing a null collection and asserting
  the not-observed mark. **Falsified by:** the two states rendering the same mark or the same gloss.
- **AC-6 — offline:** Now and Console render no cue element at all, and neither does Held to when
  `nextData.annotate !== true`. **Verified by:** harness drives of all three cases asserting the cue
  element is absent from the button, not merely empty. **Falsified by:** an empty cue span, a `0`,
  or a `·` appearing on any of the three.
- **AC-7 — offline:** The tab set the strip renders still resolves from `nextRoute.focus`, so the
  nav and the panel name the same tabs. **Verified by:** the existing focus/no-focus tab tests
  (four tabs at project scope, five with focus) re-run after the `nextCockpitTabList` signature
  change; they pass today. **Falsified by:** resolving the strip's tab set from the passed `focus`
  argument instead of the route, which makes the nav and panel disagree on a stale route.

**Interactive:** none. Every criterion above is reproducible offline through
`tests/page_harness.py` / `tests/page_worker.js`, which `test_next_cockpit.py` already uses to drive
the tab strip. The issue's own pixel and character figures are **not** acceptance criteria and are
retired to history rather than re-measured.

**User-visible criterion:** AC-1 and AC-4 are both properties a user can see — a sentence under the
strip naming the tab, and a number on the label that tracks what is behind it.

## Expected surface and tolerance

**Runtime — ~105 net LOC across 2 files, ±30%.**

| File | Change | Net LOC |
|---|---|---|
| `cargento_runtime/web/next-cockpit.js` | `nextCockpitTabList(context, focus, observation)` + its one call site at :3354; a `nextCockpitTabCue` helper carrying the four states and the visually-hidden gloss; a per-tab lede map; the departure and revision definitions | ~90 |
| `cargento_runtime/web/styles.css` | `.next-cockpit-lede` at `--fs-sentence` / `--ink2`, and `.next-cockpit-tab-cue` with its dimmed pending variant | ~15 |

**Semantics that may move:** what the tab strip renders inside each button, and one paragraph added
per panel. No route change, no fetch added, no payload field added, no new module. `sessions`,
`DECLARED_SESSION_FIELDS`, `events.PATCHABLE` and `history.OBSERVATION_FIELDS` are all untouched —
this reads published fields, it does not publish one.

**Oracles — costed separately, 9 pinned figures across 3 files plus 3 exact-string repairs.**
Current values on `spacedock-ensign/drc-4587` @ `3cc7ef49` (all moved from the recon's `main`
figures — recompute from the assets, never textually):

| File | Figures |
|---|---|
| `tests/test_next_page.py` | `next-cockpit.js` part `198_105` + `16f67be9…`; `styles.css` `111_050` + `91a303b2…`; assembled `914_344` + `2165bf68…` |
| `tests/test_next_flag.py:67,69` | assembled `914_344` + `2165bf68…` |
| `tests/test_focus.py:1024` | assembled `2165bf68…` |

Three existing assertions pin the exact button text and break the moment a cue enters the button:
`test_next_cockpit.py:1065` (`f">{label}</button>"` per tab), `:1067` (`">Now</button>"`), `:1493`
(`'aria-selected="true" tabindex="0">Course</button>'`). Repair, do not delete — they are the only
thing binding the label to its button.

**New behavioural tests — ~7 cases, ~150 LOC, all in `tests/test_next_cockpit.py`.**

**Compelled-check survey.** No required check compels a new test file here. No new module means
`CARGENTO_RUNTIME_FILES` in `scripts/validate_plugins.py` is unchanged and no import-graph allowlist
applies. `scripts/lint_embedded.py` lints the added JS and CSS in place. `docs/design-reader-state.md`
needs no new row: the cue is derived on every render and leaves nothing in the DOM for `renderNext`
to restore. If implementation cites a `D-N`/`DEC-N` label in a comment, `RuntimeDecisionCitationsTest`
requires that exact heading anchor to exist — budget a `docs/design-next-ui.md` heading if the lede
vocabulary is recorded there.

**Approach chosen, and the simplest rejected alternative.** Chosen: read each cue from a collection
already resolved on the render path, and add no fetch. Rejected: have the strip call
`nextCockpitLoadContext` itself, which the recon proposed as the way to make an unselected tab's cue
resolve. It cannot deliver more value than the chosen approach — `next-project.js:386` already makes
that exact call on every render — and it costs one `/api/project-context` per project per payload,
every 5–20 s, for readers parked on Now.

**PR sequencing.** PR 5 of 6, with DRC-4598 and DRC-4597. Only one in-flight PR may touch
`cargento_runtime/web/`. DRC-4598 is blocked on this issue and DRC-4597 governs `styles.css`, so all
three must land as one PR against a `styles.css` and an assembled page pinned once.

## Stage Report: triage

- DONE: Capture the live Linear issue body and the owning milestone description verbatim under `## Linear edits made` as the pre-edit record before drafting anything, and draft the rewrite of each beside it without writing either to Linear.
  Both captured verbatim from `get_issue DRC-4592` and `get_milestone "Clean and Cogent UI/UX"`; drafts sit beside them. No Linear write call was made in this stage.
- DONE: Write the acceptance criteria into `## Acceptance criteria` as bullets shaped `- **AC-1 — offline:** {property}. **Verified by:** {…}. **Falsified by:** {…}`
  Seven criteria, hyphenated ids, each bold label closing on the line it opens; `status --read --ac-scan` resolves all seven (see Summary).
- DONE: Declare the expected surface with tolerance, costing the byte-pin oracles separately from the runtime, and measure every figure against the POST-DRC-4587 tree on branch `spacedock-ensign/drc-4587`, not against main
  Runtime ~105 LOC ±30% across 2 files; oracles costed separately as 9 pinned figures + 3 exact-string repairs, all read from `.worktrees/spacedock-ensign-drc-4587` @ `3cc7ef49`. Every figure moved from the recon's main values (assembled `911_302` → `914_344`).
- DONE: Repair AC4, which the recon showed is unfalsifiable as filed
  A five-row source-collection table is written into the issue rewrite and AC-4 names its three collections explicitly. Held to's source was corrected from the authored `NEXT_COCKPIT_HELD_FIELDS` to `session.departures` under the existing lane rule.

### Summary

The recon's largest risk is refuted rather than accepted: `next-project.js:386` already calls
`nextCockpitLoadContext(group, null)` on every project-detail render, before `nextProjectCockpit`
builds the strip at :397, so a cue on an unselected tab resolves from a round-trip the board already
makes and the strip adds no fetch. That turns this back into a presentational change and lets the
estimate stay at ~105 runtime LOC. The measured alternative — warming from the strip — was rejected
because `aggregate.py:851` stamps `"generated": now`, so it would cost one `/api/project-context`
per project every 5-20s for readers parked on Now.

Two corrections to the issue as filed. Held to's cue counts `session.departures` under the
`null`-not-`0` rule at next-cockpit.js:1771-1780, not the authored `NEXT_COCKPIT_HELD_FIELDS`. And
the reading definition is conditional: `NEXT_READING_OFFER` already ships one, so AC-2 asserts it
occurs exactly once rather than requiring a second.

Proof of the AC shape is the scanner, not the prose: `status --read .spacedock-state/drc-4592.md
--ac-scan` returns all seven `AC-1`..`AC-7`, each on its own line. Per the stage definition's own
2026-09-17 measurement, un-hyphenating an id or wrapping a bold label before its closing marker drops
that criterion while the scan still exits 0; that shape was not re-probed here, because the stage
definition forbids probing in the shared state checkout.
No decision issue was needed; the milestone correction is one word (`Twelve` → `Thirteen`, DRC-4602).

## Stage Report: implementation

- DONE: Write every gate-approved draft for THIS group's issues to Linear as the FIRST action before any code — each issue body, any milestone correction, and any journey or move label named at triage — sending bodies unwrapped as one line per paragraph, then read back each relation set and report the edges created.
  All three bodies written before the first code read, unwrapped one line per paragraph. Labels
  already correct on all three, so no label write. Milestone: `Twelve issues.` → **`Fifteen
  issues.`**, not the gate-approved `Thirteen` — a live count at write time returns fifteen
  (DRC-4604 and DRC-4606 were filed after triage drafted the correction). Flagged rather than
  silently written; the gate approved the correction's purpose, which is that the number be true.
  **Relation edges created, read back after each write:** DRC-4592 gained `relatedTo` DRC-4559;
  DRC-4598 gained `relatedTo` DRC-4587; DRC-4597 gained `relatedTo` DRC-4593. No `blocks`/`blockedBy`
  edge moved. **Emphasis boundaries moved by Linear's own renderer, reported and not repaired:** six
  runs across the three bodies (4592 ×1, 4598 ×3, 4597 ×2) where an emphasis run containing a code
  span lost its mark at the span boundary. Table delimiter rows normalised to `| -- |`, and two
  relative links were wrapped as `(<path>)`.
- DONE: Write the failing test first for each issue and watch it fail for the right reason, then regenerate every byte pin your changes move from the assets and re-run test_next_page, test_next_flag and test_focus each ALONE, reporting each pass ratio.
  18 new cases written first, all 18 red before any runtime edit, each for its own reason
  (`nextCockpitTabCue is not defined`, `'SCOPE · Claude' != 'SCOPE'`, `1 != 0` ledes, and so on).
  Pins recomputed from the assets, never textually: `next-cockpit.js` and `project.js` parts,
  `styles.css` `114_550`, assembled `933_180` / `75da98ab…`. Two assertions pin the assembled length
  and three the digest; all five updated. Alone: **test_next_page 33/33, test_next_flag 7/7,
  test_focus 96/96.**
- DONE: Before finishing, resolve BOTH branches of every value-and-absence ternary you touch and confirm no absence you raise renders larger than the value it replaces; a test asserting an absence alone is not evidence, it must compare against its paired value.
  Two ternaries introduced. The tab cue chooses between a figure and two absence marks: all three
  rules restate `--fs-machine`, resolved through the cascade and compared as two new rows in
  `AnAbsenceNeverOutranksTheValueItReplacesTest.PAIRS` plus a dedicated size-equality check in
  `test_next_page`. The rail title chooses between a published title and `Session title not
  published`: one element, one size rule, and the rail's withheld rule reduced to `font-family`
  only, with the test asserting exactly one rule in the sheet colours `[data-next-withheld]`.
  Third pair added: `.next-cockpit-scope-title` against `.next-cockpit-scope-meta`.
  **Mutation-checked, 12 of 12 killed.** The falsifying changes: raising `--pending` to
  `--fs-sentence`; a held-to cue defaulting to `0`; pending and unobserved sharing one mark; the
  decisions cue reading `nextCockpitSemantic`'s `{facts:[]}` default; the strip taking its tab set
  from the `focus` argument; a missing lede; the sid back on the title; a second withheld colour
  rule; hoisting on a mixed group; dropping `defaultMode`; a press that writes no storage; a heading
  read from the caller. Dropping `defaultMode` also turns AC-2's two named oracles red
  (`test_decisions_view_preserves_canonical_metadata_and_compacts_scan_line`,
  `test_decisions_use_fact_scope_not_selected_session`), both left unmodified.
- DONE: Run the canonical pre-PR suite from AGENTS.md "Pre-PR Checks" read from that file, invoke sync-docs and commit its updates, then report the actual surface against each issue's declared estimate.
  Read from `AGENTS.md` and run whole: ruff clean, `ruff format --check` clean, `mypy --strict`
  clean, `lint_embedded.py` clean, `validate_plugins.py` clean, `bump_version.py --current` 0.26.0,
  no version field moved since the merge base, **3560 dashboard tests OK (2 skipped)**, **515 script
  tests OK (1 skipped)**, coverage **86.8%** against `fail_under = 73`. `claude plugin validate
  --strict` passed; `agy` is not installed here. `sync-docs` run and its updates committed on this
  branch: `design-runtime-architecture.md` (project.js now owns the timeline mode and its storage
  mirror; next-cockpit.js owns the strip's lede and cue), `design-next-ui.md` (NUI-3 gains the
  route-change constraint; the Decisions paragraph gains the filter), `design-reader-state.md` (one
  new lane row). `COMPATIBILITY.md`'s marker deliberately untouched per the parallel-work rule.
  **Surface — over the combined band on comments alone.** Runtime raw net **+248** across 3 files
  against a combined declared **154** (**161%**), but **+128** of those lines are decision comments
  the repository's Code Comments standard asks for; executable net is **+138**, **90%** of declared
  and inside every per-issue band (`next-cockpit.js` code +100 vs ~113 declared, `project.js` +30 vs
  13–31, `styles.css` +8 vs ~19). Reported rather than treated as a design reset, because the
  measured excess is entirely prose; the captain owns that call before the PR opens.
- DONE: Commit DCO signed off on your branch and STOP without pushing and without opening a pull request, reporting the branch and candidate SHA.
  Branch `spacedock-ensign/drc-4592`, candidate `43a8e9ba`, signed off. Not pushed, no PR opened.

### Summary

The three issues share `nextCockpitPanel`'s branch chain and the frontend byte pins, so they land as
one commit on one branch; the PR body owes one `Implements` line each. The one defect class this
milestone has paid four review cycles for was met head on: both branches of each new
value-and-absence ternary resolve at one tier, the pair is asserted against the cascade rather than
against a rendered board, and every new assertion was mutation-checked.

Three things a reviewer should know. The milestone number written is **fifteen**, not the approved
thirteen, because the approved figure was already stale. `nextCockpitDepartureLaneCount` is lifted
out of `nextCockpitDepartures` rather than copied, so the Held-to cue and the section it describes
cannot disagree about what an empty `departures` list means. And `data-scope-owner` was restored
onto the rail's `<a>` when the session cue that used to carry it left the card, which two existing
tests caught.

**Filed, not fixed — two issues, neither promoted into this PR.** **DRC-4608**:
`.next-cockpit-scope-note` (the Now-tab focus note) still has zero matching rules in `styles.css`
and renders at the browser's default size, which the new lede directly above it makes obvious.
**DRC-4609**: the legacy project view's `projectAction` collapses any graph-mode argument that is
not `"all"` to `"active"`, so that view's own `Decisions` button is unreachable. Both pre-existing;
neither is a regression this change created.

## Stage Report: review

Reviewed `spacedock-ensign/ui-integration` @ **2fa5a2f4** (PR #364), frozen. 12 checks pass on that
exact head, `mergeStateStatus` CLEAN. This report covers the whole group; the per-issue verdicts sit
on each entity.

- DONE: State the chosen review depth and the diff property that justified it BEFORE reviewing, per AGENTS.md "Calibrating Effort".
  **Two lenses plus an arbiter**, stated before the first read. Justifying property: the diff touches
  `cargento_runtime/web/` byte pins **and** `SKILL.md` — two of the three conflict-prone surfaces —
  across 554 changed lines of `next-cockpit.js`. Not full adversarial: no credential handling, no
  data loss, one `localStorage` key. Lenses ran in their own throwaway worktrees; I arbitrated by
  re-running every finding rather than ranking it, and refuted none of the eight put to me.
- DONE: Reproduce every acceptance criterion of every issue in your group from its own Verified by clause, against 2fa5a2f4.
  All 21 (7 + 6 + 8) driven from their own clauses; 18 offline cases green in 0.365 s across
  `CockpitTabsNameTheirPanelTest`, `CockpitScopeRailCardTest`, `CockpitTimelineFilterTest`, plus the
  two unmodified AC-2 oracles in `NextCockpitCompositionTest`. This issue's seven all reproduce.
- DONE: RUN THE FALSIFIER, NOT JUST THE VERIFIER. For each criterion, execute its Falsified by condition and show it reds.
  **43 mutations run.** This issue's 18 falsifiers all RED — no lede / two ledes / a lede without its
  tab word; a duplicated departure and revision definition; the heading renamed at either emitter;
  a cue held steady, defaulted to `0`, or read off `nextCockpitSemantic`'s `{facts:[]}`; pending and
  unobserved sharing a mark or a gloss; an empty cue span; a held-to cue with `annotate` off; the
  tab set taken from the `focus` argument. **One of this issue's falsifiers SURVIVES** — see below.
- DONE: For every criterion, report which of three it is: universal/universal, enumerated/enumerated, or UNIVERSAL WORDING WITH AN ENUMERATED VERIFIER.
  **Seven category-(c) instances across the group; four are this issue's.** AC-1 "each of the five
  tabs" — enumerated, but the five-set is closed by `test_no_route_slug_and_no_fragment_behaviour_changes`
  pinning `NEXT_PROJECT_TABS`/`NEXT_SESSION_TABS`, so mitigated. AC-2 "once per rendered panel" —
  verified on one panel. AC-3 — see FAILED below. AC-4 — the Course arm's absent case is reachable in
  the test only by handing `changes:null`, which the application never produces: `next-observed.js:205`
  builds it with `.map`, so it is always an array. Everything else is (b) or (a); AC-4's three-tab
  sweep over 3 lengths plus the unobserved arm is the strongest verifier in the set.
- DONE: Resolve rendered properties through tests/css_cascade.py down real element paths.
  Used for the withheld-title pair only, through `WithheldTitleKeepsTheAbsenceInkTest`
  (`test_next_cockpit.py:6425`), which walks `div.next-cockpit-scope-tree > a >
  span.next-cockpit-scope-line > span.next-cockpit-scope-title` — no `#app` id on that path, so the
  `matches()` trap does not apply. No property concluded by counting rules or reading specificity.
- DONE: Exclude the byte-pin oracles from every mutation check you run.
  Every mutation selected a single method or class, never a module that carries a pin. Where I
  widened, I widened to `test_next_cockpit` **only** (319 tests, 6.1 s, no pins in it) and verified
  the collection count first, so a `SURVIVED` could not be a silent zero-collection.
- DONE: Re-derive every byte pin from the assets rather than from any list.
  Derived with `hashlib` off `frontend_page.asset_path` / `load_page()`: `next-cockpit.js`
  **228_956 / 66b4f462…**, `styles.css` **120_893 / 59f31388…**, `project.js` **109_267 / d1f78af9…**,
  assembled **958_263 / 38818e11…**. The integrator's three reported values agree exactly. Two
  assertions pin the assembled length (`test_next_page:1352`, `test_next_flag:67`) and three the
  digest (`test_next_page:1354`, `test_next_flag:69`, `test_focus:1024`); all five match the tree.
- DONE: Scrutinise the integrator's own self-caught regression and its fix, and look for a second instance of the same shape.
  Fix confirmed: `next-cockpit.js:3788` reads `terminal.state === "loading"`, not a `loading` flag.
  Mutating it back to `terminal.loading === true` → RED; collapsing unread→`false` on either
  capability → RED; degrading the observer's `undefined` sentinel to `null` → RED, all against
  `ConsoleSetupNeverCallsAnUnreadCapabilityOffTest`. One no-op noted: `capabilities.terminal === true`
  is behaviourally identical to a truthy gate (`null` is falsy) — defensive, not load-bearing.
  **A second instance exists and is this issue's cue — finding M3 below.**
- DONE: Check the two refutations the integrator made rather than accepting them.
  **Both upheld, by execution.** (1) `projectAction` occurs exactly once in the whole runtime — its
  own definition — and no `data-calm` / `dataset.calm` dispatcher exists anywhere; `next-cockpit.js:3705`
  and `:3742` rewrite the attribute before render. Dead. (2) Ran `nextObservedLanding` under node
  across all five `endKind` arms: `endText` and `claimText` nonempty in every one (`BLANK SLOTS: 0`),
  because `endWhy` ends in a `|| "No stop or end observed while the session is running"`.
- DONE: Write a `## Stage Report: review` into EVERY entity file in your group, and give a GO or NO-GO without editing the branch.
  Written to all three. The branch was never edited: all mutation work ran in `/tmp/rv2-drc4592rv`,
  a throwaway worktree at 2fa5a2f4, reverted after every case and confirmed clean.
- FAILED: AC-3's stated falsifier does not falsify it.
  "Collapsing the 37m and 24h windows into one figure" leaves the test GREEN. An early
  `return "all time"` in `nextWorkstreamWindowLabel` collapses every window — the tab default, 37m,
  24h, days — onto one label and neither the method nor the whole class notices, because the verifier
  is four `assertIn` greps over JS source text that render nothing and call nothing. The heading half
  is sound (renaming at either emitter reds it). Found by Lens B, reproduced by me.

### Findings — this issue's share

**M3 (Material candidate, task-owned).** The Decisions cue reports a **failed** context read as
"decisions not loaded yet". `nextCockpitContexts` has three writers; `next-cockpit.js:3187` writes
`{data:null, revision, error:true}` on failure. `nextCockpitTabCue`'s decisions arm reads only
`.data`, so a finished-and-failed request renders `…` with the gloss *"decisions not loaded yet"* —
a claim that a request is in flight about one that is not. The panel beside it reads `.error`
(`:3677`) and says *"Semantic context unavailable."* The cue's own comment at `:3320-3324` asserts
they cannot disagree. Executed independently by me (a probe seeding the exact failure write: cue
`{state:"pending"}`, panel `Semantic context unavailable.`) and by Lens A on a failing fetch stub.
The correct pattern is one screen away at `nextCockpitAttentionCoverage` (`:433-437`), which reads
`entry.error`. Evidence fields — released user/normal workflow: any `/api/project-context` failure;
observable harm: a `…` that never resolves; field 3: `value-ac[AC-5]`, which enumerates two states
and leaves failure in the pending arm; trigger: the probe above.

**M2 (Material candidate, shared with DRC-4598).** Measured on a live board: with the timeline in
`all` mode the tab reads **"Decisions · 22 · 22 decisions"** and the lede *"Decisions: rulings found
in the record…"* over a panel headed **SEMANTIC TIMELINE** with **35** all-event rows. On a second
project the cue read "0 / No decisions observed" over an all-events list. A count beside rows it was
not derived from is the frontend shared contract's own rule. Neither issue's criteria contemplate it,
because the two were triaged apart.

**Invariant note (not blocking).** The Course cue's `{state:"unobserved"}` arm is unreachable from
the application, so a board one payload old reads `0` exactly as a board that watched all day and saw
nothing does — AGENTS.md's first Measured Invariant test question answering "the same". The panel
beside it carries the window qualifier ("since this tab opened"); the cue drops it. Contrast the
Held-to cue, which gets this right via `nextCockpitDepartureLaneCount`'s `null`.

### Summary

This issue's seven criteria all reproduce and 18 of its 19 falsifiers red, which is the strongest
falsifier record in the group. Two things are owed. AC-3's second half has no verifier at all: every
window label can be collapsed to one string with the test green, and the docstring names exactly that
as its falsifier. And the cue this issue ships reads the wrong field of a three-writer map (M3) — the
same shape the integrator self-caught at `8b9b57a8`, a second instance, found where the checklist
said to look.

**Verdict: NO-GO**, on the PR rather than on this issue's substance. The blocker belongs to DRC-4598
(a persisted graph-mode key with no project in it, falsifying that issue's own AC-2 on a live board);
the group lands as one PR, so it blocks this one too. This issue's own owed work is the AC-3 verifier
and M3. Findings route to `implementation` unchanged; I fixed nothing and edited no branch.

## Stage Report: review (cycle 1 addendum — mutation re-verification)

Re-ran every SURVIVED verdict from the report above under the handed-over harness (7 semantic
modules, 564 tests, the three byte-pin oracles excluded by regex), with a substitution-applied proof
on each: target-string count before and after, plus the file's sha256 prefix. Baseline clean:
`ran=564 failures=0 errors=0`. **Widening changed one of this issue's verdicts.**

- DONE: Confirm your mutation actually applied before reading its verdict.
  Every case now prints `APPLIED: <file> <sha-before>-><sha-after>; target N->M`. No case in either
  round was a no-op: my first-round runner already refused to run a case whose pattern was absent
  (it reported `PATTERN-MISS` three times and I re-targeted each), so the failure mode the integrator
  hit did not occur here. The one that bit me was the opposite and I did not guard against it —
  **a narrow selection making a guarded property look unguarded.**
- DONE: Confirm the named rail-card token mutation.
  Redefining `--fs-2xs:11.5px` to `16.5px` in `:root`, above `--fs-sm:14px`. Applied-proof:
  `styles.css` `59f31388e4d3`->`2d919a6426a1`, target 1->0. **KILLED**, and by the right two tests:
  `NextPageAssetContractTest.test_the_rail_card_puts_the_title_above_its_meta_in_two_registers` and
  `AnAbsenceNeverRendersLargerThanItsValueTest.test_no_absence_declares_a_larger_size_than_the_value_it_replaces`
  on exactly the `.next-cockpit-scope-title` / `.next-cockpit-scope-meta` pair. Pins excluded, so
  this is a semantic kill rather than a stylesheet edit firing an oracle. Detail on `drc-4597`.
- FAILED → **WITHDRAWN**: "AC-3's stated falsifier does not falsify it."
  **I was wrong, and the correction is the same shape as the rule I was sent.** Collapsing every
  window label with an early `return "all time"` in `nextWorkstreamWindowLabel` (applied-proof:
  `next-workstream.js` `9680ee01d192`->`c7df1bd8d3fe`) is **KILLED by four tests** —
  `test_the_heading_names_the_real_twelve_minute_window`,
  `test_a_withheld_figure_over_a_seeded_window_names_that_window`,
  `test_a_seeded_window_reports_a_figure_past_the_live_six_hour_ceiling` and
  `test_no_trend_until_two_complete_six_hour_windows_exist`, all in `test_next_delegation`. Lens B
  reported the survival against the method and the class; I reproduced it at the same width and
  recorded it as a property gap. It is not one: the two windows are guarded, by a module neither of
  us loaded. What remains is real but much smaller — **AC-3's own verifier is four `assertIn` greps
  over source text and does not bind its second clause**; the property survives on another suite's
  back. Verifier hygiene, not an unguarded property. Not blocking.
- DONE: Re-verify the remaining survivors at full width.
  AC-6's absence-only method (`if(true) return ""` in `nextCockpitTabCueHtml`, applied-proof
  `66b4f4628511`->`65de1a9be583`): **KILLED** at 564 by `test_the_pending_mark_and_the_never_observed_mark_are_different`
  and `test_local_tab_permalink_and_arrow_keys_preserve_project_session_route`. Stands as a
  within-method hygiene note only. The capability gate's `=== true` relaxed to a truthy test
  (`b45bb0299bd5`) survives all 564 and is **withdrawn as a finding**: it is an equivalent mutant —
  `null`, `true` and `false` render identically through either gate, so nothing could detect it.

### M4 (Material candidate) — `nextCockpitContexts` is NOT safe, and for a different reason than the first map

The integrator asked for this to be checked rather than accepted. Checked, by execution, and its
reasoning is wrong on both halves.

**Three writers, not two.** `next-cockpit.js:3182` (resolve), `:3187` (reject), and
**`next-render.js:81`** — the explicit observer refresh, which Lens A's enumeration missed. The third
writes `{data, revision}` with no `error` key, so a successful refresh does correctly clear the flag.

**Five reachable states, not three.** The claim "`nextCockpitLoadContext` only replaces an entry on
resolve" misses that the catch arm writes too, and that what it writes is a **merge, not a
replacement**: `{data: settled && settled.data || null, revision, error:true}` keeps the *previous*
data and stamps the error over it. So an entry can be absent, resolved, failed-with-no-data, or
**failed-while-holding-stale-data** — and `.data` alone cannot tell the last one from a clean resolve.

Executed on the fixture, writing the catch arm's shape verbatim over a loaded context:

| entry state | cue | `nextCockpitTimeline` |
|---|---|---|
| resolved | `{state:"count", value:1}` | 1 row |
| **failed, stale data held** | `{state:"count", value:1}` — identical | 1 row, **no** "Semantic context unavailable." |
| failed, no prior data | `{state:"pending"}` — "not loaded yet" | "Semantic context unavailable." |

So the middle row is worse than M3: neither the cue nor the panel says anything at all, and both
present stale figures as current. `nextCockpitProjectObservation` (`:3150`) returns
`entry && entry.data || null` and drops `.error` entirely, so everything downstream of it inherits
this. Two readers in the tree already get it right — `nextCockpitAttentionCoverage` (`:433`) and the
lane reader (`:1221`, `:1236`), both testing `entry.error` **outside** the `!data` branch. Two get it
wrong: `nextCockpitTimeline` (`:3676`, which tests `error` only *inside* `!entry.data`) and this
issue's new cue.

**Scope split, which matters for the disposition.** The panel half is **pre-existing** — the same
`:3363-3364` shape is at the merge base `21a0e935`. What this PR adds is a third wrong reader, on the
tab label, which is the most visible surface on the board. M3 and M4 close together: read
`entry.error` before `entry.data`, the way `:433` already does.

### M5 (Polish) — the trade at project scope, weighed

Executed: `nextCockpitConsoleCapabilities(group, null)` returns `{terminal:null, observer:false}` and
Console at project scope renders **"How this server was started — terminal bridge not read yet,
observer model off"**, permanently. `focus` is `null`, so no lookup is ever attempted and nothing can
resolve it.

The trade is not uniform. **With a session selected the change is a clear improvement** and the
regression it fixed was real — a refreshing terminal reported `null` on every poll. **Without one it
is a lateral move**: nothing is pending, nothing will settle, and "not read yet" is as wrong as "off"
was, in the other direction. The `observer:false` half is honest at both scopes, because the project
entry does resolve and publishes no model. The missing value is a fourth one — *no session selected;
the terminal bridge is per-session* — which is both true and actionable, where the current sentence
is neither. Small, and it can ride the round M1 already forces rather than buying its own.

### Summary

One withdrawal, one downgrade, one new Material candidate. The withdrawal is mine: I called AC-3's
window clause unguarded after reproducing a lens's survival at the same narrow width, and four tests
in `test_next_delegation` kill it. The rule that caught it is the one I was sent — confirm the
mutation applied, then confirm at a width that can see the guard — and it cost me a wrong finding in
the first direction and would have cost a wrong refutation in the second.

The `nextCockpitContexts` check the integrator asked for does not clear the map. It has a fifth state
its own reasoning did not account for, in which a failed refresh renders as a clean read on both the
cue and the panel.

**Verdict unchanged: NO-GO**, still on DRC-4598's M1. This issue's owed work is now M3+M4 together,
AC-3's verifier as hygiene, and M5 riding the same round.

## Stage Report: review (cycle 2 — re-check of the M3/M4/M5 fix)

Re-checked at **26223372**; pins re-derived and matching, harness baseline `ran=577 failures=0
errors=0`. Shared evidence on `drc-4598/index.md`. **Verdict on this issue: GO.**

- DONE: **Condition 2 — the map's five states stay distinguishable.** PASS on the defect. The fix
  adds one classifier, `nextCockpitEntryState` / `nextCockpitContextRead`, and both surfaces ask it
  rather than each keying off `.data`. Measured across four reachable states, cue and panel together:

  | entry state | cue | `nextCockpitTimeline` |
  |---|---|---|
  | ready | count 1 | 1 row |
  | **stale** (failed over loaded data) | count 1 | 1 row, no notice |
  | **unavailable** (failed, no data) | `{state:"unavailable"}`, mark `—`, gloss "could not be read" | "Semantic context unavailable." |
  | absent | pending | "Loading semantic context" |

  **M3 is closed**: a finished failure no longer says "not loaded yet", it gets its own mark and its
  own words, and the two surfaces agree at every state because there is one answer and both ask for
  it. The new `—` is distinct from `…` and `·`, so AC-5's distinctness requirement now covers four
  marks rather than three.
- DONE: **Condition 2, the half my wording got wrong — reported as a partial, not waved through.**
  I pre-registered that `stale` must make both surfaces say unavailable. The fix instead **rules**
  that `stale` renders exactly as `ready`, states the ruling in the code, and files the copy question
  as **DRC-4613**. I accept it: the defect I filed was the two surfaces disagreeing and a finished
  read being called "not loaded yet", and both are closed. What my wording additionally demanded is
  new on-screen copy nobody specified, which belongs in a filed issue rather than this PR. Flagging
  only that the ruling is a worker's and is disclosed — the captain may want it, and I am not
  treating my own pre-registration as authority over scope.
- DONE: The comment now records what the next writer would break.
  It names all three writers including `next-render.js:81`, says the `.catch` **merges rather than
  replaces**, and states the by-construction invariant — every write is `.set(key, {...})` with a
  fresh object literal, so no reader sees a half-written entry, and "a single `entry.data = ...`
  would end it". That is the part a future change gets wrong silently, and it is written down.
- DONE: **M5 addressed.** The code now says a capability "not read yet for one that nothing will ever
  read is the same error inverted", and `projectTerminalLookup` preserves `unavailable` alongside
  `registered` across a re-check. That second half fixes a defect adjacent to mine that I did not
  find: a default bridge-off console flipped "terminal bridge off" to "not read yet" on every poll,
  because the revision advances on every payload and that is what releases the guard.
- DONE: AC-3's verifier, carried forward.
  Unchanged and still hygiene rather than a gap — the property is guarded by `test_next_delegation`,
  as the cycle-1 addendum establishes. Not re-opened, not to be fixed.

### Summary

The fix goes past where both reviewers independently landed. Teaching the cue to read `.error` would
have closed only the state DRC-4589's reviewer found; the classifier closes that one, names the
stale-over-failure state neither enumeration had, and puts the panel and the cue on one answer so
they cannot drift apart again. The one place it stops short is on purpose, stated, and filed.

**Verdict: GO** on this issue.

## Stage Report: review (cycle 3 — re-check at ddd422bf)

The head moved from `26223372` to **ddd422bf** while cycle 2 was in flight. The change is confined to
the graph-mode key and its tests, so nothing on this issue's own surface moved: `next-cockpit.js` is
byte-identical at both heads (**233_309 / b0e24842…**), as is `styles.css` (**121_011 / f1d8a9bc…**).
Assembled is now **965_309 / e79d000c…** and the three pin sites agree. Harness baseline
`ran=579 failures=0 errors=0`. **Verdict: GO, unchanged.**

- DONE: Re-confirm this issue's findings survive the repoint.
  The cycle-2 result stands without re-running the state probes, because the classifier this issue
  owns is in `next-cockpit.js` and that file did not change between the two heads — verified by
  digest rather than by reading the diff. M3 closed, M4's five states classified once and read by
  both surfaces, M5 addressed.
- DONE: Re-confirm at full width.
  All 579 tests green on the new head, so nothing in the key change disturbed the context-read
  classifier or the tab cue.
- DONE: AC-3's verifier — unchanged, still hygiene rather than a gap, still not to be fixed.

### Summary

Nothing on this issue moved. Recorded so the gate does not have to infer it from a silence, and so
the GO is anchored to a head that exists rather than to the one it was written against.

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
