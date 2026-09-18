---
id:
title: "Adopt a three-tier caveat rule and put the long form behind redraw-safe disclosures"
status: review
source: "https://linear.app/recce/issue/DRC-4591/adopt-a-three-tier-caveat-rule-and-put-the-long-form-behind-redraw"
started: 2026-09-17T10:42:56Z
completed: ""
verdict: ""
score: 0.6
worktree: .worktrees/spacedock-ensign-drc-4591
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
                state: consumed
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
- **AC-7 — offline:** No rendered product string carries a bare `DEC-N` token, and **no rendered product string on the fixtures below carries a `docs/` href**. The two halves have different coverage and the criterion states which: the `DEC-N` half is genuinely universal, because `RuntimeDecisionCitationsTest` reads every `.py`, `.js`, `.css` and `.html` under `cargento_runtime` as whole files, so a bare token anywhere fails it regardless of which arm renders it; the `docs/` href half is **enumerated**, resting on the rendered fixtures named in its verifier, because no whole-file checker exists for it. Narrowed 2026-09-18 after an audit found the original wording implied universal coverage for both halves. **Verified by:** `tests/test_documentation.py::RuntimeDecisionCitationsTest::test_runtime_pointers_resolve` stays green, and a grep shows every `DEC-N` under `cargento_runtime` is inside a `//` or `/* */` comment. **Falsified by:** implementing Tier 3 as the issue literally words it — a `docs/design-reading-a-session.md#dec-16` link inside a tier-2 body, which is both a dead link in an installed plugin and a checker hit.
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

## Stage Report: implementation

- DONE: Write every gate-approved draft for THIS group's issues to Linear as the FIRST action before any code — each issue body, any milestone correction, and any journey or move label named at triage — sending bodies unwrapped as one line per paragraph, then read back each relation set and report the edges created.
  Written before the first code read: DRC-4591 body, DRC-4594 body, and DRC-4591's two-change milestone correction (DRC-4594's triage declared none owed). No label writes — both issues already carry `journey:mid-flight` and `move:sharpen`. Relations read back after the writes and **unchanged on both**: DRC-4591 blocks [4595, 4594], blockedBy [4589, 4587]; DRC-4594 blockedBy [4589, 4591, 4587, 4588]. **Zero new edges** — every DRC-#### the bodies mention was already a relation. Four emphasis-run boundary moves reported below, not repaired.
- DONE: Write the failing test first for each issue and watch it fail for the right reason, then regenerate every byte pin your changes move from the assets and re-run test_next_page, test_next_flag and test_focus each ALONE, reporting each pass ratio.
  Red baseline before any runtime edit: 17 tests, **12 failed / 5 passed**. The two errors were `ValueError: substring not found` on `next-cockpit-held-lede` and on the COUNTS `<summary>` — the thing under test did not exist. The five that passed are AC-1, AC-6, AC-7, AC-8 (4591) and AC-6 (4594), which are **preservation** criteria that must hold before and after; each was mutation-checked instead. Pins recomputed from the assets, not textually: `project.js` 107_368/`30a7281c…`, `next-cockpit.js` 206_375/`acd0170d…`, `styles.css` 114_262/`b293e085…`, assembled 926_407/`6a90a8c7…`. **9 distinct figures across 11 assertion sites** (4591 declared 11, counting the assembled pair's three re-pins). Alone, after: `test_next_page` **31/31 OK**, `test_next_flag` **7/7 OK**, `test_focus` **96/96 OK**.
- DONE: Before finishing, resolve BOTH branches of every value-and-absence ternary you touch and confirm no absence you raise renders larger than the value it replaces; a test asserting an absence alone is not evidence, it must compare against its paired value.
  `cargento/skills/cargento/tests/css_cascade.py` **does not exist on this base** — the dispatch said it would. Built the equivalent instead: `PairedBranchRegisterTest` resolves both branches through the cascade and compares them, and pins the token table so a rename cannot make two branches compare equal by both resolving to nothing. `.next-cockpit-landed-value` 15px vs `--absent` 15px (ink only) — no raise. COUNTS has no absence class at all: one `next-cockpit-count-value` rule serves the figure and its `not published`, asserted against the emitter because a second class added there is what a CSS-only check could not see. The tier-2 summary resolves at 15px, at or above the 15px body it hides. The oracle found **one open instance this change did not create**: `.next-cockpit-reading-clause-absent` is 15px against its paired `.next-cockpit-reading-clause` at 12.5px (`next-cockpit.js:1752`, `:2128-2129`). **Filed as DRC-4607, not fixed here**, and pinned in `KNOWN_OPEN` so a new violation fails and so does fixing that one without moving it off the list.
- DONE: Run the canonical pre-PR suite from AGENTS.md "Pre-PR Checks" read from that file, invoke sync-docs and commit its updates, then report the actual surface against each issue's declared estimate.
  Read from `AGENTS.md` itself, not a copy. `ruff check` clean, `ruff format --check` 222 files clean, `mypy` 163 files clean, `lint_embedded.py` clean, `validate_plugins.py` clean, `bump_version.py --current` 0.26.0, **no version line moved** since the merge base. Dashboard suite **3562 OK / 2 skipped** (136s, load 9.08 — no contention-module failures to re-confirm). `scripts/tests` **515 OK / 1 skipped**. `coverage report` **86.8%** against `fail_under = 73`. Both native validators pass. `sync-docs` run and committed as `6c5f4c94`. Surface below.
- DONE: Commit DCO signed off on your branch and STOP without pushing and without opening a pull request, reporting the branch and candidate SHA.
  Branch `spacedock-ensign/drc-4591`, candidate SHA **`6c5f4c94`** (implementation `86a9ec14`, docs `6c5f4c94`), both `Signed-off-by`. Not pushed, no PR opened.

### Surface against estimate

Measured against the stack base `2a073801`, not `main`: this branch is stacked and a `main` merge base
would report three siblings' work as this change's.

| Half | Declared (4591 + 4594) | Actual | Verdict |
|---|---|---|---|
| Runtime | +90, tolerance ±35 | **net +105** (`next-cockpit.js` +75, `styles.css` +23, `project.js` +7) | **inside**, 117% of declared |
| Behavioural tests | +140, tolerance ±25 | **net +658** | **4x beyond tolerance** |
| Byte-pin oracles | 9 figures, ~0 LOC, exact | 9 figures, 11 sites, ±0 net | inside |
| Docs | +1 row (4594); no figure (4591) | net +57 | over, no tolerance was declared |

**The test overrun is a design reset the captain owns, and it is an estimating-method failure rather
than a scope failure.** Both triages priced the behavioural half at ~70 lines while declaring eight
acceptance criteria each. In this suite a criterion costs about 35 lines: a fixture, an embedded JS
render probe and its assertions. Sixteen criteria at that rate is ~560 lines before the two
additions neither estimate contained — the ~90-line cascade oracle the dispatch's own defect-class
rule requires, and the ~53-line Console disclosure test. The runtime, which is what carries merge
risk, came in inside tolerance. This is the `AGENTS.md` shape: the estimating method gets fixed
rather than the tolerance stretched.

### Linear write hazards observed

- **Four emphasis-run boundary moves**, all on runs containing a code span or a mention, all
  reported rather than repaired: `**Verified against the post-DRC-4587 tree (`f6ced2f8`)**` split
  into four marks; `**No `docs/` href and no `DEC-N` token may reach rendered HTML**` into three;
  `**nowhere inside `next-cockpit-reading`**` into two; `**Superseded by DRC-4587 — see the history
  section**` into two. On DRC-4594: `**Measured on `spacedock-ensign/drc-4587` @ …**` and
  `**Delete the `your words` sub-label**` moved the same way.
- **Every DRC-#### became a mention**, and **no mention created a new relation** — each one already
  had one. Read back on both issues after the write.
- No `save_issue` error to check against read-back state; all three writes returned the landed body.

### One deviation from the approved draft, and why

The draft's COUNTS tier-1 wording was "Do not add these up — each counts a different thing.", a new
sentence replacing "Five figures, and no arithmetic between them." **AC-1 binds harder**: every
caveat sentence on the pre-change tree must survive verbatim, and replacing one falsifies it. The
existing sentence is seven words, carries the same operational instruction, and satisfies the
twelve-word tier-1 rule, so it is kept verbatim and the remainder goes behind the summary the draft
names. Same reasoning at HOW IT LANDED: the footer reads `Neither card implies the other.` verbatim
plus the deleted aside's reason as a second sentence, rather than the draft's colon form, which
would have dropped the pinned period. The Console recipe is the one place AC-1 could not be met
literally — a numbered two-step list cannot be the same string as a single sentence — so the test
asserts the load-bearing fragments instead: both flags, "inside the tmux pane for this exact session
with that file", and "Output is read-only."

### Summary

Both issues built on one branch, because exactly one in-flight PR may touch `cargento_runtime/web/`.
DRC-4591 adds `nextCockpitWhy`, which reuses `nextCockpitDisclosureAttr` so the existing restore
lane reopens a tier-2 body after a redraw with no registration, and Console reuses
`projectDisclosure` for the same reason; the only deletion is the duplicated `two axes, read
separately` aside, whose reason joins the footer that already made its claim. DRC-4594 adds the
lede, moves the observed record from first to last, and rewords the one sentence that was anchored
to the record's old position rather than leaving it claiming a place it no longer has. Six
mutations were run against the tests that were green at the red baseline and all six were killed;
a seventh initially **SURVIVED** because it landed in a reading-section branch the fixture never
renders, which is the "an arm that never ran" shape — AC-8's test now renders a stored reading so
that branch executes, and the mutation is killed.

### Rebase note — 2026-09-17

Rebased with `--onto spacedock-ensign/drc-4588 2a073801`, so only this branch's own commits replay
onto PR 2's rebased tip `1d847b0f`, one clean commit over merged `main`. Everything from `f6ced2f8`
through `4fb5ee6d` is excluded as the upstream boundary.

`4fb5ee6d` was deliberately **not** replayed. It raises seven value rules to the sentence tier and
its own message refuses the alternative; merged `main` does the thing it refuses, lowering the
absences and leaving the values alone. Those are two incompatible resolutions of one defect, and
replaying it would have reversed a merged decision inside a commit this task did not write. The
first officer confirmed the merged resolution stands and that the remainder is DRC-4602's.

Two conflicts in this branch's own commit were resolved rather than skipped. `styles.css` kept the
base's `.next-cockpit-reading-stale` rule, because PR 361's review lowered it on purpose, and added
only the three new `.next-cockpit-why` rules. The three byte-pin modules were resolved
**structurally and then recomputed from the assets**, never textually: each side held a figure
correct for a tree that no longer exists. `styles.css` and the assembled page both moved
(`113_433`/`de683e43…` and `925_578`/`76c2c418…`); `project.js` and `next-cockpit.js` did not, which
was checked rather than assumed — the new base's diff against the old one touches neither file.

The resolver was reconciled as the first officer directed. This branch's own resolver is deleted and
both surviving guards are built on the merged `tests/css_cascade.py`. `RAISED_ABSENCES` held exactly
one entry, the `two axes, read separately` span this change deletes, and it did **not** fail when
that class went: `resolve` walks the path and inherits, so the absence still resolved to 15.0 off
the section and compared equal to its value. That is the census's own second docstring failure
reproduced in the test named for it. The entry is replaced by the landing card's real value/absence
pair, and `test_the_retired_axes_span_stays_retired` holds the half no resolver can see.

DRC-4607 was re-measured against `main` and its first finding **withdrawn**: the reading-clause pair
is 12.5px against 12.5px there and is not inverted, so that reading was an artifact of the stale
base. The issue now carries the pair that is real and shipped — `.next-project-value--known` at
11.5px by inheritance against `--absent` at a declared 12.5px, which a per-rule census structurally
cannot resolve.

Four mutations were run against the reconciled guards and all four were killed: the summary dropped
to the label tier, a second class on the COUNTS absence branch, the landing absence raised above its
value, and the deleted aside restored.

Re-verified after the rebase: `ruff`, `ruff format`, `mypy`, `lint_embedded`, `validate_plugins` and
both native validators clean; dashboard suite **3562 OK / 2 skipped**; `scripts/tests` **515 OK / 1
skipped**; coverage **86.8%** against `fail_under = 73`; no version field moved; tone clean. The
three pin modules alone: `test_next_page` **31/31**, `test_next_flag` **7/7**, `test_focus` **96/96**.

Surface against the new base `1d847b0f`: 11 files, net **+787** — runtime **+105**, tests **+625**,
docs **+57**. The runtime half is unchanged by the rebase and still inside the combined ±35; the
test half is 40 lines smaller than before, because deleting this branch's resolver gave back more
than the census repointing cost.

## Stage Report: review

- DONE: State the chosen review depth and the diff property that justified it BEFORE reviewing, per AGENTS.md "Calibrating Effort".
  **Two lenses plus an arbiter**, chosen and dispatched before any review read, because the diff owns `cargento_runtime/web/` and its three byte-pin oracle modules at once. I am the arbiter and reproduced every finding rather than ranking it; three lens findings were refuted or corrected below.
- DONE: Reproduce every acceptance criterion of every issue in your group from its own Verified by clause, against 2fa5a2f4.
  AC-1..AC-8 each have a live verifier and all pass. Verifier and test id per criterion in the table below. Full suite at the frozen head: **3639 OK / 2 skipped**, load 7.5 (no contention-module red to re-confirm); `scripts/tests` 515 OK / 1 skipped; `validate_plugins.py` exit 0.
- FAILED: RUN THE FALSIFIER, NOT JUST THE VERIFIER. For each criterion, execute its Falsified by condition and show it reds.
  Six of eight red as written — AC-1 (paraphrase a caveat), AC-3 (a `line()` row moved into the disclosure body: 12 tests across 5 classes), AC-4/AC-5 (aside restored: 4 tests incl. the whole-runtime walk), AC-6 (instruction behind a click), AC-8 (a why inside `next-cockpit-reading`). **Two do not.** See NO-GO below.
- DONE: For every criterion, report which of three it is.
  (a) AC-4, and AC-7's `DEC-N` half. (b) AC-2, AC-3, AC-5, AC-6, AC-8. **(c) AC-1** — "every caveat sentence on the pre-change tree" is derived for `next-cockpit.js` only; the `project.js` site is four hand-listed fragments. **(c) AC-7's `docs/` half** — narrowed 2026-09-18 to "the rendered fixtures named in its verifier", but that enumeration is one fixture (the held-to tab) and omits the `pc-` surface this issue itself added a tier-2 body to.
- DONE: Resolve rendered properties through tests/css_cascade.py down real element paths.
  Tier-2 summary 15.0px against the `reading-why` body it hides at 15.0px (summary ≥ body holds at equality); `--fs-sentence` is 15px. AC-4's note premise confirmed: both independence statements already sat at the sentence tier, so the dropped "at or above the sentence tier" clause could not have bound.
- DONE: Exclude the byte-pin oracles from every mutation check you run.
  Every kill judgement below is from `test_next_cockpit` / `test_documentation`. `test_next_page`, `test_next_flag` and `test_focus` fired on all nine mutations and are discounted in all nine.
- DONE: Re-derive every byte pin from the assets rather than from any list.
  Recomputed all 20 parts plus styles.css and the assembled page with `hashlib` against `frontend_page.asset_path`/`load_page`. **All agree**, including the three the integrator reported: assembled 958_263 / `38818e11…`, styles.css 120_893 / `59f31388…`, next-cockpit.js 228_956 / `66b4f462…`. The three pin modules alone: 48/48, 7/7, 96/96.
- DONE: Scrutinise the integrator's own self-caught regression and its fix; confirm the test kills the mutants claimed; look for a second instance of the same shape.
  Fix is correct: `projectTerminalLookup` (project.js:685) does write `{state:"registered", loading:true}` on every revision-advancing re-check, so the flag read was wrong and `state` is the tri-state. All three claimed mutants killed by `ConsoleSetupNeverCallsAnUnreadCapabilityOffTest` — the `loading` read, the `Boolean()` pair, and unavailable-as-unknown — and the refresh test guards itself with `assertTrue(out["loading"])` so it cannot pass vacuously. **No second instance of the loading-vs-state shape**: `loading` is read at exactly one site, the writer's own re-entrancy guard. One weaker adjacent instance, measured not reasoned: the new tab-cue reader (next-cockpit.js:3331-3333) keys off `entry.data` alone while its sibling `nextCockpitTimeline` (:3675) also requires the project-scope entry, so with the focused context settled first the Decisions tab shows `{state:"count", value:1}` over a panel reading "Loading semantic context…". **Transient** — it heals on the next redraw, which I measured. Non-blocking, but the comment added at :3320-3324 claims the two "cannot read different facts", which is true at project scope and false at focused scope.
- DONE: Check the two refutations the integrator made rather than accepting them.
  **Both hold, by execution.** `projectAction` appears exactly once in the 958_263-byte assembled bundle — its own definition; no caller, no `data-calm` dispatcher anywhere, and the cockpit rewrites that attribute to `data-next-cockpit-action="graph-mode"` before render, so project.js:402's two-value collapse is unreachable and the live handler (:4079) passes the raw arg through the three-value validator. `nextObservedLanding` over a 1120-row cross-product of its inputs returned **zero** blank `endText`/`claimText`/`independentText`; every reason branch is a non-empty literal or has a non-empty `||` fallback.
- DONE: Write a `## Stage Report: review` into EVERY entity file in your group, and give a GO or NO-GO without editing the branch.
  Written to drc-4591 and drc-4594. Branch untouched: `git status --porcelain` empty, HEAD 2fa5a2f4 after every mutation.

### Verdict: NO-GO — two of AC-1/AC-3/AC-7's own Falsified-by conditions do not red

The runtime is correct and nothing user-visible is broken; I drove AC-2 on a **live board** (real `summary.click()`, then both an explicit `renderNext()` and a genuine payload poll, `generated` 1789684638.40 → 1789684650.83) and both surfaces stayed open — `details.next-cockpit-console-setup` carrying `data-next-cockpit-disclosure` and the `pc-` recipe carrying `data-pc-disclosure="terminal-registration"`. Three test-side gaps block, each clearable without a CI round because the PR is not open:

1. **AC-7's falsifier does not red on the surface this issue added.** A live `<a href="docs/design-reading-a-session.md#dec-16">` inside the rendered Console recipe (project.js:853) survives all **3639** behavioural tests. That is AC-7's Falsified-by clause verbatim — "a `docs/design-reading-a-session.md#dec-16` link inside a tier-2 body" — applied to the tier-2 body DRC-4591 created, and in an installed plugin it is a dead link. It reds on the `next-` surface only. No defect ships: an independent `emitted_strings` sweep over all 20 web JS files found **zero** rendered literals carrying `docs/` or a bare `DEC-N`.
2. **AC-3's second falsifier does not red.** Removing `nextCockpitWhy`'s empty-body guard outright (next-cockpit.js:35) survives all 3639 behavioural tests, so the reachable off-line re-entry arm would emit `<p class="next-cockpit-reading-why"></p>`. The comment at :30-33 claims two fallbacks; only the empty-`<details>` one is pinned.
3. **AC-1's fourth named site is not verbatim on this tree.** `grep -c "Registration requires starting the dashboard with" project.js` is 1 at base `21a0e935` and **0** at 2fa5a2f4. The implementation disclosed this and its reasoning is good — a numbered two-step list cannot be one sentence — but AC-1 as written is falsified by its own clause and must be reconciled in the criterion, not passed silently. Relatedly, deleting "Run the registration client" from step 2 while leaving the four pinned fragments intact survives all 3639 tests, shipping a registration procedure with its act removed.

### Summary

Every AC-1..AC-8 verifier exists, runs and passes, and six of eight falsifiers red hard — AC-4's whole-runtime walk and AC-1's merge-base-derived sentence set are genuinely universal instruments, and `tests/js_literals.py` was written to close exactly this defect class. What blocks is narrower: two stated Falsified-by conditions do not red when applied where the criteria point them, both on the `pc-`/Console half this issue extended, and AC-1's fourth sentence no longer exists verbatim. All three are one-test or one-sentence fixes. Lens A's F2 was refuted as first run (its mutation broke a pinned fragment's capitalisation) and confirmed only on a faithful re-run; its AC-2 live half, reported NOT ATTEMPTED, I settled myself on a live board.

### Addendum — no-op check on the surviving mutants, and the second look at `nextCockpitContexts`

**Every SURVIVED result above was re-checked for the no-op failure the integrator hit, and all survive it.** Asserting the anchor was present before `str.replace` is not enough — it proves the edit ran, not that it reached the render. Both blockers were re-verified three ways: the mutated token counted in the source file, counted in the assembled bundle, and **counted in rendered HTML**.

- **AC-7 / the `docs/` href.** Anchor 1 occurrence before; mutated token 1 in `project.js`, 2 in the 958_263-byte bundle, and **1 in the rendered Console tab** with `"How to register a terminal"` present — so the dead link genuinely draws, and 3639 behavioural tests still pass. Not a no-op.
- **AC-3 / the empty-body guard.** `grep -c 'if(!text) return "";'` goes 1 → 0, and rendering `HeldToOrderingTest.tab()` then yields exactly **one** `<p class="next-cockpit-reading-why"></p>`, inside the re-entry block, in the fixture the ACs themselves use: `…<span class="next-cockpit-held-reentry-text">Terminal raise: off for this run.</span></div><p class="next-cockpit-reading-why"></p></div>`. The arm is reachable and rendered, which the report above asserted and this measures. Not a no-op.

**`nextCockpitContexts` — who writes it, in what states.** Three writers, no `delete`, no `clear`: `next-cockpit.js:3182` `{data, revision}` on passive resolve; `next-cockpit.js:3187` `{data: settled.data || null, revision, error:true}` on passive reject; `next-render.js:81` `{data, revision}` on observer-model resolve. **The integrator's claim is correct and I confirm it independently:** every `.set` sits inside a `.then`/`.catch`, so an entry is only ever replaced on settle and no in-flight marker is written onto it — structurally unlike `projectTerminalBySession`, where `projectTerminalLookup` writes `{state:"registered", loading:true}` at *request* time. Both cross-writer races are guarded on purpose (`:3168` blocks a passive load during an observer request; `:3180`/`:3185` bail when `next-render.js:72` has dropped the request). So the loading-vs-state shape is genuinely absent.

**What the same question surfaces that the conclusion does not cover: the three writers do not agree on the field set.** Only the reject writer carries `error`, and only it carries data it did not fetch. Driving that real path — settle, then reject on the next revision — measured: fields go `["data","revision"]` → `["data","error","revision"]`, `error === true`, `data` is **the identical object** from before, and `nextCockpitTimeline` renders the stale rows with no "Semantic context unavailable" and no "Loading semantic context". The reader at `:3677` consults `entry.error` only inside the branch that surviving stale data stops it reaching. This is the same family as the terminal defect but in the worse direction — that one reported a working capability as unknown, this reports a failed read as fine.

**Pre-existing, with one new inheritor.** `:3677`/`:3721` are not this branch's code. The tab-cue reader this branch adds at `:3331-3333` is, and it inherits the blindness: measured `{state:"count", value:1}` **identically before and after** the context fetch failed, so a failed read is indistinguishable from a fresh one on the tab strip. The comment added beside it argues at length that a `pending` state is owed at both scopes because calling an unread collection "not published" reports the schema rather than the session — AGENTS.md's first Measured Invariant. That argument extends to the error state and was not carried there. **Not promoted into this PR** per AGENTS.md; it is one more row for the cue's state set, and it belongs in its own issue alongside the `:3677` half. The verdict above is unchanged.

### Re-check contract — what the fix round must make red (AC-3 and AC-7)

Held here so the re-check does not depend on anyone's recollection. Run each against the fix commit, from the repo root, with `python3 -m unittest discover -s cargento/skills/cargento/tests -t .`. **`test_next_page`, `test_next_flag` and `test_focus` fire on every asset edit and are discounted in all of these** — a fix is proven only by a *behavioural* red.

**Before trusting any SURVIVED verdict, prove the mutation was not a no-op.** Count the mutated token in the source file, in `frontend_page.load_page()`, and in rendered HTML. The first two prove the edit landed; only the third proves it reached the thing under test.

- **AC-3.** Delete `if(!text) return "";` from `nextCockpitWhy` (`next-cockpit.js:35`). Must red behaviourally. Today it reds nothing while `HeldToOrderingTest.tab()` renders exactly one `<p class="next-cockpit-reading-why"></p>` in the re-entry block. The paired mutation — returning an empty `<details>` instead — already reds at `:10816`; the fix is the other fallback the comment at `:30-33` claims and nothing pins.
- **AC-7.** Put `<a href="docs/design-reading-a-session.md#dec-16">Why</a>` inside the rendered Console recipe (`project.js:853`, the `Output is read-only.` paragraph). Must red behaviourally. Today it survives all 3639 and renders once on the Console tab.

**On the AC-7 fix specifically: widening the fixture by one surface is the weaker repair, and this tree already has the stronger one.** A second fixture still cannot fail on the surface nobody thought to add — which is the argument `tests/js_literals.py`'s own docstring makes, and the reason AC-4's `test_the_retired_axes_span_stays_retired` walks every `.py`/`.js`/`.css`/`.html` under `cargento_runtime` instead of naming files. The derived form of AC-7's `docs/` half is about ten lines and I ran it during this review: sweep `emitted_strings` over every `web/*.js`, reject any literal containing `docs/` or matching `(?<![A-Za-z0-9_-])DEC-\d+(?![A-Za-z0-9_-])`, and assert the file count to keep a walk that reaches nothing from passing. **On 2fa5a2f4 it returns zero hits across all 20 files**, so it lands green on the current tree and reds on the mutation above — and it would have caught this without anyone naming the Console surface. Its one blind spot, worth stating in its docstring rather than leaving implicit: `emitted_strings` splits template literals at `${...}`, so a href composed through a hole is out of its reach.

### Correction — re-measured at `9959f623`, and the contract re-anchored off line numbers

Everything above was measured at `2fa5a2f4`. The head has since moved to `9959f623` ("let the Decisions cue and its panel resolve one read"). **Re-measured at the new head rather than assumed:**

- **The no-data half is closed.** Driving the reject writer with no prior data: `nextCockpitContextRead` → `"unavailable"`, cue `{state:"unavailable"}`, panel "Semantic context unavailable.", no rows. Cue and panel now agree, and the new `nextCockpitContextRead` is a single classifier both call, which also closes the focused-scope divergence reported above (the cue keying off `entry.data` while the panel also required the project entry). Confirmed fixed; the report above stands as a record of the tree it was measured on.
- **The stale-data-plus-error half is still open at `9959f623`.** Same drive with a prior settled entry: fields `["data","error","revision"]`, `error === true`, `data` still present, and `nextCockpitContextRead` returns **`"ready"`** — its `if(entry && entry.data && …)` returns before the `failed` line is reached, so `error` is only consulted when data is absent. Cue `{state:"count", value:1}`, panel renders the rows, saying neither "unavailable" nor "loading".
- **One thing the fix changed about this half, worth stating precisely.** Cue and panel were independently blind to it before; they are now *jointly* blind through one classifier. That is a net improvement, not a regression — the remaining repair is one condition in `nextCockpitContextRead` rather than two readers kept in step — but "the cue and the panel agree" must not be read as "the state is handled".
- **Per the first officer this is fix-not-file**, because the cue is code this PR introduced; `:3677`'s pre-existing half is DRC-4613. The split follows what this PR introduced, not what the defect touches.

**Contract anchors re-derived, and the contract re-stated without line numbers.** One commit moved the guard 35 → 36, the re-entry return 2561 → 2562, `test_the_reentry_block_leads_with_the_action` 11119 → 11149 and `FOCUS_ON` 7681 → 7682; `project.js`'s recipe paragraph did not move. A contract meant to survive a fix round cannot be anchored on numbers that drift under it, so locate each site by its string instead:

| site | locate with |
|---|---|
| AC-3 guard | `grep -n 'if(!text) return "";' next-cockpit.js` (1 occurrence) |
| AC-7 recipe | `grep -n 'Output is read-only.' project.js` (1 occurrence) |
| AC-5 re-entry return | `grep -n 'next-cockpit-held-reentry-action' next-cockpit.js` (1 occurrence) |
| AC-5 fixture | `grep -n 'FOCUS_ON = ' tests/test_next_cockpit.py` |

**AC-3 re-confirmed still open at `9959f623`** by execution: deleting the guard leaves **3640** behavioural tests green with only the three excluded byte pins firing. The suite grew by one test with the cue fix; the blocker did not move.

### Re-check at `26223372` — AC-7 FAIL, AC-3 FAIL, restoration PASS

Contracts run as pinned. Suite is **3652** tests; the three byte-pin oracles are discounted throughout, so each result below is a behavioural read. Both contracts located their sites by string, as re-anchored, and both anchors still resolved to exactly one occurrence.

**AC-7 — FAIL.** The falsifier still does not red: a `docs/design-reading-a-session.md#dec-16` href in the rendered Console recipe leaves **3652 behavioural tests green**, only the byte pins firing. It did not land as the derived sweep; `emitted_strings` has no new call site, and the repair is a widened fixture that renders five tabs and asserts `assertNotIn("docs/design-", html)` over each.

**The reason it fails is one layer below the gap it was meant to close, and it is measured, not inferred.** Instrumenting that fixture's own console arm: `recipeDrawn: False`, `mutatedHrefDrawn: False`, with `consoleLen: 16977`, the terminal section present and `pc-terminal-absence` present. The tab is visited; the *recipe* is never drawn, because the registration branch needs a terminal entry the fixture does not set up. So the assertion runs over HTML that does not contain the thing under test, and the per-tab non-vacuity guard (`assertGreater(len(html), 2000)`) passes because the tab drew something else. That is the same "an arm that never ran" shape, one level down — which is precisely what a fixture cannot defend against and a source sweep can.

**The derived form catches this exact mutation.** Run at `26223372` with the href planted: 20 files swept, **1 hit**, in `project.js`. Green on the clean tree, red on the mutation, and it needs nobody to have thought of the Console surface. The remaining repair is to replace the five-tab render with that sweep, or — if the rendered check is wanted as well — to add the terminal fixture that makes the recipe draw and assert `recipeDrawn` before asserting over it.

**AC-3 — FAIL.** Deleting `if(!text) return "";` from `nextCockpitWhy` still leaves **3652 behavioural tests green**. Not a no-op: with the guard gone, `HeldToOrderingTest.tab()` renders exactly one `<p class="next-cockpit-reading-why"></p>`, in the re-entry block, in the fixture the ACs themselves use. Unchanged from the `2fa5a2f4` and `9959f623` measurements.

**The `sed` restoration — PASS, on a check that resolves values rather than reading lines.** Comparing `26223372` against `9959f623` by AST: five classes define `ANNOTATED` before and after, none added, none removed, and **no assignment changed**. Resolving the attributes at import time rather than trusting the source: every one of the five carries its own `ANNOTATED` (`own=True`), so **nothing falls through the MRO to another class's fixture** — the failure shape you asked about is absent. Three distinct values across the five, with two deliberate source-level aliases (`CockpitCuesReachTheReaderTest` sharing `CockpitHeldToTabTest`'s object, `HeldToPositionalSentencesTest` sharing `HeldToOrderingTest`'s), both identical to their pre-damage form. Worth recording that my first pass compared AST dumps and would have scored those two aliases as opaque strings of equal length; the resolved read is what actually answers the question.

### Re-check at `ddd422bf` — AC-7 PASS, AC-3 FAIL

Head derived rather than taken on trust: `git branch -a --contains ddd422bf` gives `spacedock-ensign/ui-integration`, whose local and remote tips are both `ddd422bf`, so this is the tip and nothing was newer when I measured. Suite **3654**; byte pins discounted. Both contract anchors still resolved to exactly one occurrence — nothing in either contract rests on a line number, which is why this re-point cost nothing.

**AC-7 — PASS.** It landed as the derived sweep, and it meets the spec on all four points:

- **Sweeps every script:** `sorted(web.glob("*.js"))` over `cargento_runtime/web`, 20 files today.
- **Both halves red.** A `docs/design-reading-a-session.md#dec-16` href planted in the rendered Console recipe now fails `test_no_rendered_string_carries_a_docs_link_or_a_decision_token` **and nothing else** — the same mutation that survived all 3652 at `26223372`. A bare `DEC-16` planted in the same rendered string fails it too. Clean tree green (10/10 in the class).
- **File count asserted:** `assertGreater(len(scripts), 15, "the bundle walk found almost no scripts")`, so a walk reaching nothing cannot pass an empty loop. Measured 20 against a floor of 15.
- **Blind spot stated:** the docstring records that `emitted_strings` splits a template literal at each `${...}`, so an href composed through a hole is out of reach, and says the answer is a different instrument rather than a longer list.

One deliberate non-issue, recorded so nobody narrows it later: the token half uses `\bDEC-\d+\b` where this review's sweep used `(?<![A-Za-z0-9_-])DEC-\d+(?![A-Za-z0-9_-])`. `\b` treats a hyphen as a boundary, so it is *looser* — it would also flag `FOO-DEC-16`. That errs toward flagging, never toward missing, so it is the safe direction and should stay.

**AC-3 — FAIL, unchanged across four heads.** Deleting `if(!text) return "";` from `nextCockpitWhy` leaves **3654 behavioural tests green**, only the three byte pins firing; survivor confirmed against the full suite, not a module. Not a no-op — the guard count goes 1 → 0 and the ACs' own fixture then renders one empty `<p class="next-cockpit-reading-why"></p>` in the re-entry block. This commit did not touch it and was not expected to.

### Correction — my stale-state claim was wrong from `26223372` onward

**I carried a measurement forward instead of re-taking it, which is the error I spent this review flagging in others.** In my reports on `26223372` and `ddd422bf` I wrote that the stale-data-plus-error state "still returns `ready` from `nextCockpitContextRead`". That was measured at `9959f623` and asserted at two later heads without being re-run. It is false at both.

Measured at `ddd422bf`, driving the real reject writer over a settled entry: `entryState` **`"stale"`**, `readState` **`"stale"`**, `shows: true`. `nextCockpitEntryState` — which does not exist at `2fa5a2f4` or `9959f623` and appears at `26223372` — returns `"stale"` for data-with-error and `"ready"` for data-without, so the classifier **does** separate the two states. DRC-4589's reviewer was right about that half and I was wrong.

What I actually observed remains true and is the other half: the cue still reads `{state:"count", value:1}` and the panel still renders the rows, because `stale` and `ready` render identically at both call sites. **That is a ruling, not an oversight**, and the comment at `next-cockpit.js:3224` states it as one — keeping the last known rows is defensible, and a staleness sentence would be new copy nobody specified. The separation exists so DRC-4613 can act on it without a refactor. So "cue and panel agree" is right, "and are both wrong" is not: the agreement is deliberate and documented. Nothing further is owed here.

The general lesson is the one this review has been applying outward and failed to apply inward: **a state claim is only as current as the head it was measured on.** Three heads moved under this re-check; the contracts survived because they are string-anchored and re-run, and this claim did not because it was neither.

### AC-3 disambiguated — the conflation was inside this criterion, not between two issues

Measured at `ddd422bf`, because a correction accepted on trust is worth no more than a finding accepted on trust.

**The test that was grepped is this issue's own AC-3 test, not DRC-4592's.** `test_the_five_count_rows_and_their_absences_never_collapse` opens `"""AC-3. Only the explanatory paragraph may go behind a summary."""` and lives in `CaveatTieringTest`, which is DRC-4591's class. DRC-4592's AC-3 is a different subject entirely — `OBSERVED STATE CHANGES` unchanged at `next-project.js:350`. So the "two issues, same criterion number" account does not describe what happened, though the hazard it names is real and larger than two: **ten issues in this burndown each carry an `AC-3`**, so a bare criterion number is ambiguous ten ways and should never be the search key.

**The real conflation is between two manifestations of one falsifier.** AC-3's second falsifying condition — "a helper with no empty-body branch that swallows a row when its text is empty" — bites `nextCockpitWhy` two different ways depending on the caller:

| caller passes | missing guard produces | caught? |
|---|---|---|
| a summary **and** an empty body | `<details><summary>…</summary><p></p></details>` — a control opening onto emptiness | asserted at `:11217`, but **unfalsifiable in this fixture** |
| **no** summary and an empty body | a bare `<p class="next-cockpit-reading-why"></p>` | **not caught at all** |

Measured with the guard deleted: `test_the_five_count_rows_and_their_absences_never_collapse` **passes**, and the tab renders **1** empty `<p class="next-cockpit-reading-why"></p>` and **0** empty `<details>` bodies. The new `assertNotEqual("", body.strip(), "the disclosure opens onto an empty body")` is a genuine assertion, but COUNTS always passes a non-empty literal body, so the `!text` branch never fires there and no mutation of that guard can red it. The reachable arm is the other one — the re-entry raise branch at `{why:"", whyLabel:""}`, which takes the `!summary` path and emits the bare empty paragraph.

**So the contract's AC-3 entry is restated to name the shape rather than the number.** Locate with `grep -n 'if(!text) return "";' next-cockpit.js`; delete that line; the fix is proven only when a behavioural test reds **on the no-summary arm** — an assertion that no `<p class="next-cockpit-reading-why">` is rendered empty, anywhere on the tab. An assertion aimed only at a disclosure's body cannot reach it, which is why the first repair did not.
