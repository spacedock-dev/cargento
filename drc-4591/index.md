---
id:
title: "Adopt a three-tier caveat rule and put the long form behind redraw-safe disclosures"
status: triage
source: "https://linear.app/recce/issue/DRC-4591/adopt-a-three-tier-caveat-rule-and-put-the-long-form-behind-redraw"
started: 2026-09-17T10:42:56Z
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
        - id: gate:drc-4591:triage
          stage: triage
          attempts:
            - id: gate-attempt:drc-4591-triage-1
              briefing:
                id: briefing:drc-4591:triage:attempt-1:revision-1
                digest: sha256:d199e2ed0f0025c04c59c89d12094e890604d0ccce26149be8348652b1c3087c
                room-ref: ./review/triage/briefing-1
              resolution:
                type: Resolution
                id: resolution:spacedock:drc-4591:triage:1
                briefing: briefing:drc-4591:triage:attempt-1:revision-1
                by: agent:first-officer
                at: "2026-09-17T10:54:02.434138Z"
                decision: approve
                reason: 'Checklist 5 done / 0 skipped / 0 failed; AC-1..AC-8 resolve with AC-2 the interactive one. The stage re-measured against the post-DRC-4587 tree and found its own issue''s argument had moved: the size-and-contrast half is now false because that PR fixed it, recorded in a thirteen-row claim table naming three dead claims, two understated counts and one wrong line number. The disclosure requirement names a concrete mechanism rather than a category, reusing nextCockpitDisclosureAttr and projectDisclosure with no new plumbing, which is what the dispatch asked for. All eleven pinned figures were read from the post-4587 worktree rather than main.'
                conn:
                    quote: I pre-approve all the triage and merge gates, just automate this entire process and do it
                    source: Captain, this session, 2026-09-17
              application:
                target-stage: implementation
                state: pending
---

[DRC-4591](https://linear.app/recce/issue/DRC-4591/adopt-a-three-tier-caveat-rule-and-put-the-long-form-behind-redraw) — Adopt a three-tier caveat rule and put the long form behind redraw-safe disclosures

Seeded 2026-09-17 from the live Linear read of the Clean and Cogent UI/UX milestone.
Linear owns the current issue body, its relations and its resources; triage fetches them
live and validates them against the tree before anything is built. No triage, approval,
implementation or delivery is claimed here.

---

## Triage — 2026-09-17

Measured against the **post-DRC-4587 tree**, worktree `.worktrees/spacedock-ensign-drc-4587`
at `3cc7ef49` (the burndown doc commit) whose code tip is `f6ced2f8`
*feat(web): raise board sentences to a 15px tier and collapse the label tier*. Every figure below
was re-derived there, not quoted from the issue and not taken from `main`.

### Is the problem still real?

**Yes, and post-4587 it is sharper than the issue describes — but for a different reason than the
issue gives.** The issue's headline argument is a *contrast/size* argument: caveats are 12.5px/400
ink3 at APCA Lc 44.1, so the hedged sentences are the ones a reader is least equipped to read.
DRC-4587 retired that argument. `styles.css:952` is now
`.next-cockpit-reading-why{margin:0;color:var(--ink3);font:500 var(--fs-sentence)/1.55 var(--sans);max-width:var(--measure)}`
with `--fs-sentence:15px` (`styles.css:26`). The caveats are no longer small.

What survives, and what the rewrite must lead with instead, is **volume and register collapse**:

- `styles.css:922` `.next-cockpit-count-label` and `styles.css:952` `.next-cockpit-reading-why`
  now carry the **identical font shorthand** — `500 var(--fs-sentence)/1.55 var(--sans)`,
  `max-width:var(--measure)`. Post-4587, nothing about *size* distinguishes a caveat from the
  finding it qualifies; only ink does, and separating ink is DRC-4589, this issue's other blocker.
- Raising the caveats to 15px/1.55 did not shorten them. The same 69 words now occupy **more**
  vertical space than the panel measurement in the issue was taken against, so the issue's
  "hundreds of words the reader skips" claim is understated on the tree this will land on, not
  overstated.

### Which of the issue's cited claims still resolve on the post-4587 tree?

| Issue claim | Post-4587 verdict |
|---|---|
| `next-cockpit.js:2154` `two axes, read separately`, and `:2159` `Neither card implies the other.` | **Holds, both lines exact.** The duplication is real and unmoved. |
| "…once at **10px**" | **DEAD.** `styles.css:963` is now `.next-cockpit-landed-axes{color:var(--ink3);font:500 var(--fs-sentence)/1.55 var(--sans);max-width:var(--measure)}`. DRC-4587 repointed it to 15px *and* moved the span out of its `<header>`. The aside is still worth deleting, but the reason is duplication, never size — and AC4's "at or above the sentence tier" is **already satisfied by both statements today**, so AC4 as written can pass without this issue doing anything. It must be rewritten around uniqueness. |
| "73% of Held-to characters are 12.5px/400 ink3 at APCA Lc 44.1" | **DEAD** for the caveat class (see above). Unreproducible offline in any case. |
| COUNTS closes with 69 words in two paragraphs (37 + 32) | **Holds, and reproduces from source.** `next-cockpit.js:1904-1907` is 37 words; `NEXT_COCKPIT_STEER_BY_HAND` at `:1736-1738` is 32, emitted at `:1787`. Two different functions with two different owners. |
| "the one operational instruction … is the fifth word" | Near enough: the text is "Five figures, and no arithmetic between them." — the instruction starts at word 3. Immaterial. |
| `project.js:795-798`, 30-word recipe as one `<p class="pc-substrate-empty">` | **Holds, 30 words exact**, two `<code>` flags, no list. |
| `nextCockpitDisclosureAttr` at `:15`, used at 5 sites | **Understated.** Defined at `:15`, used at **13** sites (`:267, :312, :577, :2056, :2677, :2755, :2774, :3052, :3065, :3092, :3129, :3237, :3242`). The mechanism is far more established than the issue implies; that lowers the risk of the new helper. |
| restore lane generic at `:3360-3371` | `:3358-3377`. `nextCockpitBeforeRender` calls `projectCaptureDisclosureStates()` at `:3363`, so **both bundles' disclosure systems already run in one before-render pass.** Console inherits redraw safety from `projectDisclosure` with zero new plumbing. |
| `projectCaptureDisclosureStates` at `project.js:77` | **Wrong: `:74`.** `projectDisclosure` at `:53` is correct. |
| `nextCockpitWhy` | **Genuinely new** — no occurrence anywhere in the tree. |
| `tests/test_next_cockpit.py:5299` pins the deleted string | **Holds at :5299 exactly**, and it is still the only test in `tests/` referencing any of the four caveat strings. |
| `--unasked-readings` must stay visible | `next-cockpit.js:1824`, inside an unconditional `next-cockpit-reading-why`. AC6 is a real constraint, not already satisfied. |

### What the recon did not check, and got wrong

1. **The recon's headline risk is overstated.** It warned that `test_next_cockpit.py:5741/:5757`
   (now `:5784/:5800` post-4587) `assertNotIn('class="next-cockpit-reading-why"', …)` would flip red
   if `nextCockpitWhy` reused that class. They will not: both read `out["notAsked"]` /
   `out["stands"]`, which are built by a single-row `row(...)` helper (`:5758`) over one reading
   **criteria** row — not over the app. Nothing in COUNTS, DEPARTURES, HOW IT LANDED or Console
   reaches them. The tier-2 body may reuse `next-cockpit-reading-why` without touching those two.
2. **The real coupling is one the recon named for the wrong reason.**
   `tests/test_next_cockpit.py:5183` does
   `block = html.slice(html.indexOf('class="next-cockpit-reading"'))` — a slice **to end of
   document**, not to end of section — then takes the **first** `class="next-cockpit-reading-why">`
   match in it. Its three assertions (`:5243`, `:5246`, `:5250`) are on reading-section sentences.
   The constraint this places on the change is narrow and precise: **`nextCockpitWhy` must not be
   applied anywhere inside `next-cockpit-reading`, and no new `reading-why` may be emitted between
   the reading section's start and its own first caveat.** All four target sites sit after it, so
   the plan as drafted is safe — but a fifth site would not be.
3. **A closed `<details>` keeps its body in `innerHTML`** (innerHTML is markup, not rendered text),
   so AC1 is assertable in the existing node/jsdom driver with no browser. Confirmed by reading the
   driver's `read()` helpers, which already slice raw `innerHTML`.
4. **`RuntimeDecisionCitationsTest` scans the whole runtime tree, not just comments.**
   `tests/test_documentation.py:38` calls `citation_errors(root, …/cargento_runtime)` over the
   directory. A rendered product string containing the bare token `DEC-16` would need to be the
   entire link text of a same-line repository-relative link with an exact heading fragment — which
   is also a dead link in an installed plugin, where no `docs/` sits beside the page. **Ruling
   below.**

### Ruling: Tier 3 does not ship a `docs/` link

The issue's Tier 3 ("rulings and rationale move to `docs/design-reading-a-session.md`, linked once
from inside a tier-2 body") cannot be built as written. Two independent reasons: the shipped page
has no `docs/` beside it, and a `DEC-N` token in runtime source is governed by
`RuntimeDecisionCitationsTest`. **Tier 3 in this issue means: the sentence is removed from the
panel and its full form lives in `docs/design-reading-a-session.md`, cited from a `.js` source
comment in the existing grammar — never from rendered HTML.** No user-facing `docs/` href, no
user-facing `DEC-N` token. The anchors are present and resolve today: `DEC-15` (`:17`), `DEC-15b`
(`:33`), `DEC-16` (`:130`), `DEC-17` (`:173`), `DEC-18` (`:399`).

### Does the approach still fit?

Yes, and it is cheaper than the issue implies. Both mechanisms exist, both are already wired into
one before/after-render pass (`:3358-3377`), and `nextCockpitAfterRender` restores only when
`nextRoute.view === "project"` — Held to and Console are both project-view tabs, so both sites are
covered. The one change to the solution text is the HOW IT LANDED bullet: "delete the 10px aside"
becomes "delete the duplicated aside", because 4587 already fixed its size.

## User value

A user mid-flight who opens Held to or Console to decide whether a session needs them reads to the
end of a panel and hits sixty-nine words of qualification standing between the five numbers and the
next thing they came for — set, post-DRC-4587, in exactly the same type as the finding above it.
They skip it, and the honesty Cargento paid for buys nothing. Tiering puts the claim inline and the
rationale one click away, so the panel answers the question at a glance and still holds every
sentence for the reader who wants it.

Promise [P2 — "What is it doing, and when should I come back?"](../../promise-map.md#how-work-links-to-a-promise);
move `sharpen`. This does not add a capability — it makes an answer the board already gives
reachable in one read.

## Labels

Already correct on the live issue; `implementation` writes no label change.

- `journey:mid-flight` — present
- `move:sharpen` — present

## Expected surface

Costed separately, measured against the post-4587 tree.

**Runtime — 3 files, +45 LOC net, tolerance ±20.**

| File | Work | LOC |
|---|---|---|
| `next-cockpit.js` | new `nextCockpitWhy(control, summary, body)` beside `nextCockpitDisclosureAttr` at `:15`; rewrite `:1904-1907` (COUNTS), `:1787` (`NEXT_COCKPIT_STEER_BY_HAND`), `:2154`+`:2159` (HOW IT LANDED) | +30 |
| `project.js` | `:795-798` one `<p>` → `projectDisclosure("terminal-registration", …)` wrapping a numbered two-step `<ol>` | +10 |
| `styles.css` | delete `.next-cockpit-landed-axes` (`:963`); add summary + tier-2 body rules | +5 |

**Oracles — 11 pinned figures across 3 test files, recomputed from the assets, never textually.**

| File | Figures | Current post-4587 value |
|---|---|---|
| `tests/test_next_page.py` | `project.js` size+digest (`:635-636`), `next-cockpit.js` size+digest (`:683-684`), `styles.css` size+digest (`:702-706`), assembled size+digest (`:709-714`) | `106_941`/`8d404a66…`, `198_105`/`16f67be9…`, `111_050`/`91a303b2…`, `914_344`/`2165bf68…` |
| `tests/test_next_flag.py` | assembled length `:67`, digest `:69` | `914_344`, `2165bf68…` |
| `tests/test_focus.py` | assembled digest `:1024` | `2165bf68…` |

Note `next-cockpit.js` is **198_105 bytes on both main and post-4587 while its digest changed** —
4587's edit was byte-neutral. Recomputing only the sizes and reasoning that an unchanged size means
an unchanged digest is exactly the mistake that tree invites.

**Behavioural tests — 1 fixture edit + 4 new, ~+70 lines in `tests/test_next_cockpit.py`.**
`:5299` `axes: block.includes("two axes, read separately")` becomes an occurrence count on the
independence claim (AC-4). New assertions for AC-1, AC-3, AC-5, AC-6. `tests/test_project.py` gains
one for the Console site.

**Docs.** `docs/design-reading-a-session.md` gains the tier-3 body for any sentence removed from a
panel. The three-tier rule itself is a UI ruling and belongs as a new `NUI-18` in
`docs/design-next-ui.md`, which DRC-4587 has just established as the owner of "which selectors are
sentences".

**Compelled by an existing required check, not chosen:** `scripts/lint_embedded.py` lints the new
JS/CSS; `RuntimeDecisionCitationsTest` governs any `DEC-N` that enters `cargento_runtime` (ruled
above: none enters rendered HTML). No new module, so no import-graph gate fires. **The declared
tolerance covers the runtime; if the oracle or docs half overruns, that is the DRC-4037 shape and
the estimating method gets fixed rather than the tolerance stretched.**

## Approach, and the simplest rejected alternative

**Chosen.** Three tiers; `nextCockpitWhy` for the `next-` surface, `projectDisclosure` for `pc-`.
Concretely: `nextCockpitWhy` **reuses** `nextCockpitDisclosureAttr` (it does not replace it) and so
inherits the existing generic restore lane at `:3358-3377` with no registration; `projectDisclosure`
at `project.js:53` is reused **as-is**, and its capture already runs inside the same before-render
pass at `:3363`. Two mechanisms rather than one because the two bundles keep separate open-state
maps keyed differently, and unifying them is a refactor this issue does not need.

**Rejected: just delete the caveats, or cut them to one sentence each.** It is one CSS-free edit and
it is the cheapest thing that makes the panels short. It cannot deliver the value because every one
of these sentences is load-bearing — "no arithmetic between them" is the operational instruction
that stops a reader summing five counts that measure different things, and `NEXT_COCKPIT_STEER_BY_HAND`
is half of a deliberate two-place statement ([DEC-16](../../design-reading-a-session.md#dec-16-cargento-does-not-write-into-a-session),
recorded in the comment at `next-cockpit.js:1732-1735`). Shortening them trades a readability
problem for a correctness one. The whole point of the tier rule is that **nothing is deleted.**

**Rejected: a bare `<details>` at the Console site.** One line shorter than `projectDisclosure` and
it snaps shut on every redraw — the board redraws on live payload, so the user would lose the recipe
mid-read. Named here because it is the obvious implementation and the reason against it is not
visible in the diff.

## Acceptance criteria

- **AC-1 — offline:** Every caveat sentence that exists on the pre-change tree still exists verbatim in the assembled bundle, inline or inside a disclosure body, and no absence marker is replaced by a blank. **Verified by:** a string-presence assertion in `tests/test_next_cockpit.py` over the four sentences at `next-cockpit.js:1904-1907`, `:1736-1738`, `:2159` and `project.js:795-798`, read from `__els.app.innerHTML` — a closed `<details>` still contributes its body to `innerHTML`, so no browser is needed; today all four are present as unconditional `<p>` text. **Falsified by:** deleting or paraphrasing any of the four, or rendering an empty `<details>` in place of one.
- **AC-2 — interactive:** A disclosure opened at COUNTS, DEPARTURES or Console is still open after the board redraws, on both the `next-` and `pc-` surfaces. **Verified by:** partly offline — a node/jsdom driver that sets `details.open = true`, calls `nextCockpitBeforeRender()` / `renderNext()` / `nextCockpitAfterRender()` (`next-cockpit.js:3358-3377`, `projectCaptureDisclosureStates` at `project.js:74`) and reads `open` back; the genuine click-to-toggle-to-redraw path needs a live board walk at `127.0.0.1:4553` under the `visual-review-and-fix` skill. **Falsified by:** a bare `<details>` at either site, or a helper that emits no `data-next-cockpit-disclosure` / `data-pc-disclosure` attribute, which makes the restore lane skip it.
- **AC-3 — offline:** COUNTS renders all five rows and their `not published` values unconditionally; only the explanatory paragraphs may collapse. **Verified by:** the nine existing `re.findall(r'class="next-cockpit-count-value">([^<]*)<', …)` assertions in `tests/test_next_cockpit.py` (`:7399`, `:7426`, `:7563`, `:7579`, `:7595`, `:7619`, `:7635`, `:7679`, `:7683`), which today return five-element lists such as `["not published", "1", "3", "3", "2"]` and must still do so. **Falsified by:** moving any `line(...)` row inside a disclosure body that renders conditionally, or a helper with no empty-body branch that swallows a row when its text is empty.
- **AC-4 — offline:** The string `two axes, read separately` appears nowhere in the runtime, and the card-independence claim is stated exactly once in `HOW IT LANDED`, adjacent to the cards. **Verified by:** a grep for the deleted string returning zero hits under `cargento_runtime`, plus an occurrence count of exactly 1 for the independence claim in the rendered `next-cockpit-landed` block. **Falsified by:** leaving both statements in place, or deleting both. *Note: the original AC's "at or above the sentence tier" clause is dropped — DRC-4587 repointed `styles.css:963` to `--fs-sentence`, so both statements already satisfy it and the criterion could pass without this issue acting. Uniqueness is the property that still binds.*
- **AC-5 — offline:** `tests/test_next_cockpit.py:5299` no longer pins a string this change deletes. **Verified by:** that line reads an occurrence count of the surviving independence claim rather than `block.includes("two axes, read separately")`; the full suite is green. **Falsified by:** leaving `:5299` unedited, which turns it red the moment AC-4 lands.
- **AC-6 — offline:** The `--unasked-readings` instruction (`next-cockpit.js:1824`) stays visible without a click. **Verified by:** an assertion that the substring `--unasked-readings` does not occur after any `<summary>` within its own `next-cockpit-departure-part`; today it sits in an unconditional `<p class="next-cockpit-reading-why">`. **Falsified by:** wrapping the unasked part's first paragraph in the new helper.
- **AC-7 — offline:** No rendered product string carries a bare `DEC-N` token or a `docs/` href. **Verified by:** `tests/test_documentation.py::RuntimeDecisionCitationsTest::test_runtime_pointers_resolve` stays green, and a grep shows every `DEC-N` under `cargento_runtime` is inside a `//` or `/* */` comment. **Falsified by:** implementing Tier 3 as the issue literally words it — a `docs/design-reading-a-session.md#dec-16` link inside a tier-2 body, which is both a dead link in an installed plugin and a checker hit.
- **AC-8 — offline:** The reading section's first `next-cockpit-reading-why` is unchanged in position and content. **Verified by:** the three assertions at `tests/test_next_cockpit.py:5243`, `:5246`, `:5250` stay green — they read the first `reading-why` in a slice that runs to end of document (`:5183`), so any new one emitted earlier hijacks them. **Falsified by:** applying `nextCockpitWhy` anywhere inside `next-cockpit-reading`.

**User-visible criterion:** AC-1 and AC-3 together are the property a user sees — the panel gets
shorter without any sentence leaving the page, and the five numbers never move.

## Linear edits made

**Nothing has been written to Linear.** The captures below are the pre-edit record; the rewrites
below them are drafts this gate authorizes. `implementation` performs the write as its first action.

### Captured original — DRC-4591 issue body, verbatim as of 2026-09-17T06:37:37Z

```markdown
## User value

Anyone who reads a panel to the end notices this. Today every caveat is inline prose at the same size and ink as the finding it qualifies, so the honesty costs hundreds of words and is skipped.

## The Problem

Cargento has no rule for where a long caveat lives, so every one of them renders as a `<p>` in the reading flow at the same size as the finding it qualifies. Held to carries 363 words, 19 sentences and 2132 characters against 4 controls in a 974px panel, and 73% of its characters are the 12.5px/400 ink3 that measures APCA Lc 44.1 — the longest, most carefully hedged sentences are the ones a reader is least equipped to read. The honesty is paid for in vertical space and then skipped.

Three sites carry the bulk. COUNTS closes with 69 words in two paragraphs under five numbers, and the one operational instruction in them — do not add these up — is the fifth word of the first sentence. HOW IT LANDED says the cards are independent twice, once at 10px. Console's terminal block renders a 30-word CLI recipe as running prose in which `--interaction-origin-session` breaks across a line wrap.

The bundle already owns the disclosure mechanism and does not use it here.

**Measured**

* Held to: 363 words / 19 sentences / 2132 chars / 4 controls / 974px. Console: 166 words / 10 sentences / 1059 chars / 732px
* 73% of Held-to characters are 12.5px/400 ink3 at APCA Lc 44.1 against a requirement of 100
* COUNTS caveats measured at 69 words in two paragraphs (37 + 32) under five rows occupying about 99px
* "two axes, read separately" (next-cockpit.js:2154, 10px) and "Neither card implies the other." (:2159) state the same thing twice, roughly 100px apart
* project.js:795-798 renders the 30-word registration recipe as one paragraph; the capture shows it wrapping to four lines with a flag broken across the first wrap
* `nextCockpitDisclosureAttr` (next-cockpit.js:15) with `<details>` is already used at :267, :312, :577, :2056 and :2774; the restore lane at :3360-3371 is generic over `[data-next-cockpit-disclosure]`
* project.js has its own persisted helper, `projectDisclosure` at :53, restored by `projectCaptureDisclosureStates` at :77

**In the attached screenshot**

1. COUNTS closes with 69 words under five numbers
2. Caveats ink3 12.5px, same register as the findings
3. "two axes" and "Neither card implies" say one thing twice
4. Five rows are 99px; their caveats are 75px

## The Solution

Three tiers, one helper, three CSS rules, **nothing deleted**.

* **Tier 1, always visible** — one clause of twelve words or fewer carrying the claim itself, including every "not published", at the sentence tier in the absence register.
* **Tier 2, disclosure** — everything past that clause, behind a 2-4 word summary naming what is inside.
* **Tier 3** — rulings and rationale move to `docs/design-reading-a-session.md`, linked once from inside a tier-2 body.

Add `nextCockpitWhy(control, summary, body)` beside `nextCockpitDisclosureAttr` so open state survives a redraw with no registration, and use `projectDisclosure` (not a bare `<details>`) for the Console site, or it snaps shut on every redraw.

Apply at four places:

* **COUNTS** — inline "Do not add these up — each counts a different thing." plus a disclosure summarised "What a count does not say".
* **DEPARTURES** — keep `NEXT_COCKPIT_STEER_BY_HAND` on its own section, shortened to the claim, with the remainder behind "Why no raise goes further".
* **HOW IT LANDED** — delete the 10px aside, keep one footer reading "Neither card implies the other: evidence of an end and a claim of completion are separate questions", and update the fixture at `tests/test_next_cockpit.py:5299`, which pins the deleted string.
* **Console** — the recipe becomes a numbered two-step list behind "How to register a terminal".

## Acceptance

- [ ] Every caveat sentence still exists verbatim, either inline or one click away; no absence marker is replaced by a blank
- [ ] Disclosure open state survives a redraw on both the `next-` and `pc-` surfaces, using each bundle's own persisted helper
- [ ] COUNTS renders its five rows and their "not published" values unconditionally; only the explanatory paragraphs collapse
- [ ] "two axes, read separately" is gone and the independence claim is stated once, at or above the sentence tier, adjacent to the cards
- [ ] `tests/test_next_cockpit.py:5299` is updated in the same change
- [ ] The `--unasked-readings` instruction stays visible rather than moving behind a summary

---

Complaint **C3** · tabs: held-to, console, chrome · severity **major** · effort **M** · blocked by DRC-4587, DRC-4589

Raised from user feedback; mechanism and figures established by a measured audit of the live board and the shipped stylesheet.
```

### Drafted rewrite — DRC-4591 issue body

```markdown
## User value

A user mid-flight who opens Held to or Console to decide whether a session needs them reads to the end of a panel and hits sixty-nine words of qualification between the five numbers and the next thing they came for — set, after DRC-4587, in exactly the same type as the finding above it. They skip it, and the honesty Cargento paid for buys nothing. Tiering puts the claim inline and the rationale one click away, so the panel answers at a glance and still holds every sentence for the reader who wants it.

Promise **P2** ("What is it doing, and when should I come back?") · move `sharpen`.

## The Problem

Cargento has no rule for where a long caveat lives, so every one renders as a `<p class="next-cockpit-reading-why">` in the reading flow. After DRC-4587 that paragraph and the finding-label beside it carry the **identical** font shorthand — `styles.css:922` and `:952` are both `500 var(--fs-sentence)/1.55 var(--sans)` capped at `--measure`. Nothing about size separates a caveat from what it qualifies; only ink does, and that is DRC-4589. Raising the type did not shorten the text, so the vertical cost went up.

Three sites carry the bulk, all reproducible from source:

* **COUNTS** closes with 69 words in two paragraphs under five numbers — 37 at `next-cockpit.js:1904-1907` and 32 in `NEXT_COCKPIT_STEER_BY_HAND` (`:1736-1738`, emitted at `:1787`). They are two functions with two owners. The one operational instruction, "no arithmetic between them", is buried third.
* **HOW IT LANDED** states card independence twice: `two axes, read separately` (`:2154`) and `Neither card implies the other.` (`:2159`).
* **Console** renders a 30-word CLI registration recipe as one `<p class="pc-substrate-empty">` (`project.js:795-798`) with two flags that wrap.

Both bundles already own a redraw-safe disclosure mechanism and neither uses it at these sites.

**Verified against the post-DRC-4587 tree (`f6ced2f8`)**

* 37 + 32 = 69 COUNTS words, and the 30-word Console recipe, all reproduce from source
* `nextCockpitDisclosureAttr` (`next-cockpit.js:15`) is used at **13** sites, not five
* The restore lane at `:3358-3377` is generic over `[data-next-cockpit-disclosure]` and calls `projectCaptureDisclosureStates()` (`project.js:74`) in the same pass, so both bundles already restore together
* `nextCockpitWhy` does not exist anywhere in the tree

**Superseded by DRC-4587 — see the history section**

The size and contrast half of the original argument no longer holds: `.next-cockpit-reading-why` is now 15px/500, and `.next-cockpit-landed-axes` (`styles.css:963`) is no longer 10px.

## The Solution

Three tiers, one new helper, three CSS rules, **nothing deleted**.

* **Tier 1, always visible** — one clause of twelve words or fewer carrying the claim itself, including every "not published".
* **Tier 2, disclosure** — everything past that clause, behind a 2-4 word summary naming what is inside.
* **Tier 3** — a sentence too long for tier 2 is removed from the panel and its full form written into `docs/design-reading-a-session.md`, cited from a **source comment** in the existing citation grammar. **No `docs/` href and no `DEC-N` token may reach rendered HTML**: an installed plugin has no `docs/` beside the page, and `RuntimeDecisionCitationsTest` scans all of `cargento_runtime`, not just its comments.

Add `nextCockpitWhy(control, summary, body)` beside `nextCockpitDisclosureAttr`, **reusing** it rather than replacing it, so open state survives a redraw with no registration. Reuse `projectDisclosure` (`project.js:53`) as-is for Console — a bare `<details>` snaps shut on every redraw. Give the tier-2 body a **no-body branch that falls back to inline**, so an empty body never silently swallows a caveat.

Apply at four places, and **nowhere inside `next-cockpit-reading`** — `tests/test_next_cockpit.py:5183` reads the first `reading-why` in a slice that runs to end of document, so an earlier one hijacks three assertions.

* **COUNTS** — inline "Do not add these up — each counts a different thing.", remainder behind "What a count does not say".
* **DEPARTURES** — `NEXT_COCKPIT_STEER_BY_HAND` shortened to its claim, remainder behind "Why no raise goes further". The `--unasked-readings` instruction (`:1824`) stays inline.
* **HOW IT LANDED** — delete the duplicated `two axes, read separately` aside and its `styles.css:963` rule, keep one footer: "Neither card implies the other: evidence of an end and a claim of completion are separate questions". Update `tests/test_next_cockpit.py:5299`, which pins the deleted string.
* **Console** — the recipe becomes a numbered two-step list behind "How to register a terminal".

Record the three-tier rule as `NUI-18` in `docs/design-next-ui.md`, which DRC-4587 established as the owner of which selectors are sentences.

## Acceptance criteria

AC-1 through AC-8 are held in the burndown entity `drc-4591.md` with their `Verified by:` and `Falsified by:` clauses and their offline/interactive split. AC-2 is the only interactive one.

## Cost

Runtime +45 LOC across `next-cockpit.js`, `project.js`, `styles.css` (±20). Oracles: **11 pinned byte figures** across `tests/test_next_page.py`, `tests/test_next_flag.py` and `tests/test_focus.py`, recomputed from the assets. `next-cockpit.js` kept its byte count across DRC-4587 while its digest moved — recompute both.

---

## History

### 2026-09-17 — superseded by DRC-4587

Filed 2026-09-17 against a pre-DRC-4587 tree. Three claims in the original body no longer describe the code and are kept here because they are why the issue was filed:

* "73% of Held-to characters are the 12.5px/400 ink3 that measures APCA Lc 44.1." `.next-cockpit-reading-why` is now `500 15px/1.55` (`styles.css:952`).
* "HOW IT LANDED says the cards are independent twice, **once at 10px**." `styles.css:963` was repointed to `--fs-sentence` and the span moved out of its `<header>`. The duplication survives; the size defect does not.
* The original AC "…stated once, **at or above the sentence tier**, adjacent to the cards." Both statements already meet the tier clause, so it no longer binds. AC-4 now binds on uniqueness alone.

Panel measurements — Held to 363 words / 974px, Console 166 words / 732px, five rows at 99px — were taken on the live board before DRC-4587 and DRC-4589 moved the type scale. They are not reproducible from the tree and are not re-asserted.

The original "Measured" block also carried two line references that were already wrong when filed: `projectCaptureDisclosureStates` is at `project.js:74` (not `:77`), and the restore lane spans `:3358-3377` (not `:3360-3371`).

---

Complaint **C3** · tabs: held-to, console, chrome · severity **major** · effort **M** · blocked by DRC-4587, DRC-4589

Raised from user feedback; mechanism re-verified against the post-DRC-4587 tree at triage on 2026-09-17.
```

### Captured original — milestone "Clean and Cogent UI/UX" description, verbatim as of 2026-09-17

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

One sentence in "What is left" is now false and one is now incomplete. Nothing else in the
milestone needs touching for this issue, and **the other in-flight triages own their own edits** —
this is deliberately the minimum this issue makes false.

**Change 1 — the first foundation bullet is done.** `Raise board sentences to a 15px tier` shipped
as `f6ced2f8`. Replace the bullet list preamble sentence and that bullet:

> Twelve issues. Three are foundations and everything else depends on them:
>
> * **Raise board sentences to a 15px tier** and collapse six sub-12px tokens into one label tier.

with:

> Twelve issues. Three are foundations and everything else depends on them; the first has landed.
>
> * ~~**Raise board sentences to a 15px tier**~~ — landed, `f6ced2f8`. `--fs-sentence:15px` and
>   `--measure:540px` exist and 65 sans prose rules point at them.

**Change 2 — "no contrast fix available" now needs its consequence stated.** After DRC-4587 the
caveat paragraph and the finding label beside it carry the identical font shorthand, so size no
longer separates them at all. Append to the third paragraph of "The user value":

> Raising the sentence tier was the first half and it landed; it also removed size as a separator,
> so a caveat and the finding it qualifies are now set identically and only ink can tell them
> apart. That makes `ink-roles` load-bearing for caveat tiering rather than merely adjacent to it.

**Not changed.** The "How this was measured" APCA disclaimer stands as written — it already says the
figures are audit-only and unreproducible, which is exactly the property this triage re-confirmed.
The `Waits on` section stands. The count "Twelve issues" stands; DRC-4602 was filed into PR 6 and
the captain's sequence, not into this milestone's headline count.

## Stage Report: triage

- DONE: Capture the live Linear issue body and the owning milestone description verbatim under `## Linear edits made` as the pre-edit record before drafting anything, and draft the rewrite of each beside it without writing either to Linear.
  Both captures fenced verbatim from `get_issue DRC-4591` (updatedAt 2026-09-17T06:37:37Z) and `get_milestone "Clean and Cogent UI/UX"`; drafted rewrite and a two-change milestone correction sit beside them. No Linear write was made — `save_issue`/`save_milestone` were never called.
- DONE: Write the acceptance criteria into `## Acceptance criteria` as bullets shaped `- **AC-1 — offline:** {property}. **Verified by:** {…}. **Falsified by:** {…}`
  Eight bullets, AC-1..AC-8, hyphenated ids, each bold label closing on its own opening line; AC-2 is the only `interactive` one. Verified by running `status --read drc-4591.md --ac-scan`, which resolves all eight rather than returning `{"acs":[]}`.
- DONE: Declare the expected surface with tolerance, costing the byte-pin oracles separately from the runtime, and measure every figure against the POST-DRC-4587 tree on branch `spacedock-ensign/drc-4587`, not against main
  Runtime +45 LOC / ±20 across three web assets, costed per file; oracles costed separately as 11 pinned figures, each read from the post-4587 worktree (`3cc7ef49`, code tip `f6ced2f8`): assembled `914_344`/`2165bf68…`, `styles.css` `111_050`/`91a303b2…`, `next-cockpit.js` `198_105`/`16f67be9…`, `project.js` `106_941`/`8d404a66…`. None of these are the main-branch figures the recon quoted.
- DONE: Check every claim the issue makes about the caveat sites against the tree, and state plainly which of its cited line numbers still resolve after DRC-4587 moved the type scale.
  Thirteen-row claim table in the triage section. Three claims are dead (the 10px aside, the 12.5px/Lc 44.1 caveat register, and the original AC4's "at or above the sentence tier" clause, which now passes without this issue acting); two were understated (13 disclosure sites, not 5; restore lane `:3358-3377`, not `:3360-3371`); one was wrong (`projectCaptureDisclosureStates` at `project.js:74`, not `:77`). All three word counts — 37, 32, 30 — reproduce from source on the post-4587 tree.
- DONE: make sure the redraw-safe disclosure requirement names the concrete mechanism rather than the category — say whether this reuses `projectDisclosure` or replaces it
  Stated in "Approach": `nextCockpitWhy` **reuses** `nextCockpitDisclosureAttr` (`next-cockpit.js:15`) and inherits the existing generic restore lane; `projectDisclosure` (`project.js:53`) is reused **as-is** for Console, and `nextCockpitBeforeRender` already calls `projectCaptureDisclosureStates()` at `:3363`, so neither surface needs new plumbing. AC-2 names both attribute contracts as its falsifier.

### Summary

Re-measuring against the post-DRC-4587 tree changed the issue's argument rather than confirming it.
The size-and-contrast half is now false — `.next-cockpit-reading-why` is 15px/500 and the
`.next-cockpit-landed-axes` 10px rule is gone — but the underlying defect is sharper, because
DRC-4587 gave the caveat and the finding-label beside it the **identical** font shorthand
(`styles.css:922` and `:952`), so size no longer separates them at all and the same 69 words now
cost more vertical space than when the issue was filed. The rewrite leads with volume and register
collapse, demotes the three superseded claims to a dated history section, and rules that Tier 3
ships no `docs/` href and no `DEC-N` token into rendered HTML — the issue's literal wording is both
a dead link in an installed plugin and a `RuntimeDecisionCitationsTest` hit. Two findings correct
the recon: its headline test risk (`:5784`/`:5800`) is scoped to a single reading-criteria row and
cannot fire, while the real coupling it missed is `:5183`, whose slice runs to end of document —
recorded as AC-8.
