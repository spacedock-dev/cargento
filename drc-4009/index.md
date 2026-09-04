---
id: drc-4009
title: 'A6 · Overrun likelihood before you start'
status: triage
source: https://linear.app/recce/issue/DRC-4009
started: 2026-09-04T02:34:11Z
completed:
verdict:
score: 0.2
worktree:
issue:
pr:
mod-block:
linear-status: Todo
milestone: 'Don''t burn capacity'
release: 'later'
estimate: 'XL'
reconciled:
promise: P4
move: extend
gates:
    version: 1
    records:
        - id: gate:drc-4009:triage
          stage: triage
          attempts:
            - id: gate-attempt:drc-4009-triage-1
              briefing:
                id: briefing:drc-4009:triage:attempt-1:revision-1
                digest: sha256:938670134a8248158cee0c690dd982811e78a4c9327d723eadfe40ff58f5c811
                room-ref: ./review/triage/briefing-1
---

[DRC-4009](https://linear.app/recce/issue/DRC-4009) — Linear priority Low, estimate XL.

The authoritative issue body lives in Linear and is deliberately not copied here: a copy taken at
commission time would be a second, staler statement of the problem, and this workflow exists partly
because stale statements of a problem get built. `triage` fetches it live, reviews it adversarially
against the current codebase, and writes the sharpened version back to Linear.

## Problem

Checked against `main` at `4de75d2` (H1 both PRs merged), not restated from the issue. Every claim
below names the file and the line that settles it, and the change that would falsify it.

**The issue's method is banned outright, not merely uncertain.** A6 estimates task size "using a
size estimate matched by shape against similar past sessions", and `items.json` spells the shape out
as "a prompt's text predicts its duration". The history contract bans prompt text with no exception:
`SECURITY.md`, "Local history (the session history store)", first never-item — "Prompt text, of any
session, at any point, whatever field carries it." DEC-6's ruling (DRC-4234) says the same. So the
first stacked guess is not a guess the code could be built to test; it names an input the store may
never hold. *Falsified by:* a never-list that permits any prompt-derived field.

**What the store actually holds is five fields per state transition.** `history.Observation` and
`OBSERVATION_FIELDS` (`history.py:79-104`) are `harness`, `sid`, `project`, `state`,
`last_activity`, and the module docstring says why a derived record rather than a row copy. Three
consequences the issue does not carry:

- **No token count, no consumption, no rate.** None of the three is in DEC-6's kept-list or in
  `SECURITY.md`'s, and the contract adds "The store may never widen the set of fields it keeps".
  Adding one is an amendment to a promoted contract, which is a captain's call, not a scoping choice.
- **No session end.** The published `state` vocabulary is three values — `_STATE_RANK` in
  `aggregate.py:26` is `needs_input`, `working`, `idle`. A session that ends stops transitioning and
  falls out of the board's 24-hour window; nothing records that it finished. P5's own limit says so:
  "Telling a session that died from one that finished is not shipped yet."
- **`last_activity` is the whole subtree.** `sessions.py:327-334` — the session, its task files, and
  every subagent and child transcript. A span derived from two consecutive observations is a
  difference of subtree stamps, not a task duration, and no test anywhere establishes how far a
  subagent moves a parent's stamp.

**Per-session quota attribution does not exist for nine harnesses of ten.** The issue calls this a
guess; it is worse than a guess. `consumption` is filled only by Copilot, and carries its own unit as
text because AIU, tokens and dollars are three different quantities (`sessions.py:282-295`).
`rate_per_min` is output tokens over a ten-minute mean and is null for four of the ten harnesses —
"OpenCode, Cursor and Droid read no token accounting, and Copilot's store carries only quota
receipts" (`aggregate.py:191-197`). Output tokens are also not what a vendor meters. *Falsified by:*
a second harness filling `consumption`, or a weighted-unit field appearing on the row.

**The second guess becomes a question the store can answer, and the store answers it badly.** "Is a
past session meaningfully similar?" reduces, once prompt text is banned, to the only similarity keys
the store holds: `project` and `harness`. So the question is whether a project-and-harness cohort
predicts anything — and the store cannot yet be asked, because it holds zero closed spans (measured
below), while two of the session ids in it appear under five harness keys each, so the harness half
of the key is not reliably one session. *Falsified by:* a store in which every sid appears under
exactly one harness.

**The composition step is an artifact this repository built, measured, deleted, and wrote down as
"keep rejected".** `docs/design-usage-quota.md`, "The burn row's race verdict, built and then deleted
(2026-08-06)": three review rounds found five false-green defects, all five inside the verdict and
none in the quantities; the fitted slope survived a 4,000-case randomised sweep with no false-safe
result. Its conclusion is the general one — "a verdict composed over uncertain evidence fails toward
confident green, and a false green is worse than no light" — followed by "This is the judgement that
killed A9 on the Visibility board" and "It is written down here because reintroducing it will look
like an improvement rather than a regression." `items.json` records A6 as `subsetOf: A9`, both
answering "should I start". A likelihood is a verdict with a decimal point on it.

**And the surface A6 would attach to is not there.** This is the finding that was not expected.

- `payload.usage` has exactly one consumer in the shipped page: `next-attention.js:355-388`, which
  raises a risk card only at `pct >= 70`. There is no usage band, no per-session cost row, no burn
  row. *Falsified by:* any other `usage` reference under `cargento_runtime/web/` — a grep across
  `*.js`, `*.html` and `*.css` returns five lines, all inside that block.
- **No projection ships at all.** `docs/design-usage-quota.md` Q-9 is titled "promotion retired the
  client-side burn projection" and states the promoted interface "does not predict exhaustion or
  compare it with reset time". No runtime code computes a slope, a fill interval or a time to the
  wall. Two comments still speak of it as live (`quota.py:233`, `tests/test_records.py:241`); they
  are stale by the promotion.
- **The page never asks for a quota fetch.** `next-render.js:24` is the only request builder and
  sends `/api/data` or `/api/data?all=1`. `http_api.py:465-472` fires `request_usage_fetch()` only on
  `usage=1`. So Claude's and Cursor's credential-backed windows are never fetched in normal use, and
  no test asserts otherwise. *Falsified by:* a `usage` parameter on any request the page builds.

**Therefore `promise-map.md` P4 is false where it matters most to A6.** It promises "the burn rate
projected to the wall" and says "On top of that sit per-model sub-limits, per-session cost, the
projected burn rate, and a ranking of which session is burning fastest right now." No projection
exists, per-session cost is one harness, and none of it renders below 70 per cent. A6 is a P4
`extend` resting on a clause of P4 the product does not keep.

**What the only real store contains.** Measured on this machine rather than argued. The store at
`~/.cargento/cargento-history.json` holds 25 entries spanning 2026-09-02 20:08 to 2026-09-03 17:23,
17 distinct session ids across six harnesses and ten project labels — and **zero `(harness, sid)`
pairs with more than one entry**, so zero observed transitions and zero closed working spans. Two
session ids appear under five harness keys each, all `working`, which would count one real session
five times in any cohort keyed on harness. **The honest caveat:** the file's mtime is 2026-09-03
17:24 and H1 PR 1 merged at 2026-09-03 20:25, so this is a development sample from H1's own build,
not production evidence. The conclusion is not "the store will stay empty" but "nobody has yet
measured what a real store accumulates", and the estimate would rest entirely on that unmeasured
quantity. *Falsified by:* a store on any machine holding a closed `working` to non-`working` pair.

**What the panel scores mean for the estimate's honesty.** Risk-adjusted impact 32 against impact 66
is the largest gap in its row, and detector risk 34 with `detectorConfidence: low` is the panel
saying it did not believe the detector could be built. The number A6 would print is therefore the one
number on the board whose own confidence is lowest, rendered in the same type as four measured
percentages. That is the failure Q-10 rejected for cross-authority comparison, arriving from a
different direction.

**Still true from the original body:** the problem is real — a person does decide whether to start
work against a window, and A1, A2 and the reset countdown do not answer it. The "Waits on" edge on
H1 is satisfied and was converted to `relatedTo` by H1's reconcile.

## Proposed approach

**A6 is not buildable as filed.** Three independent reasons, each sufficient on its own: its named
method needs a field the contract bans; its target quantity is measured for one harness of ten; and
its composition step is the artifact the repository deleted and recorded as keep-rejected. A fourth,
found here, is that the surface it composes against no longer renders.

So the honest product of this triage is a filed decision, drafted below as **DEC-12**, with a
`blocks` edge onto this issue. The question is bigger than A6 and has a second dependent: E7
(DRC-4040) says "with the wall projected inside the configured window", and no projection exists, so
E7 rests on the same unshipped mechanism.

**Recommended answer: option B — quantities, never a composed verdict.** Under B this issue is
re-scoped to the narrowest thing a reader can see and Cargento can honestly measure: per
`(project, harness)`, the spread of closed working spans the server actually observed, published as
named figures with their sample count and their limitation on the surface, beside the reset
checkpoint the quota card already carries. The reader races the two. Cargento never says whether it
is safe to start.

**Simplest rejected alternative: print the likelihood anyway, from the cohort span and the current
rate.** It cannot deliver the value. The rate is output tokens for six harnesses and null for four,
the span is a subtree-stamp difference truncated at first sighting, and the quota is account-scoped —
so the likelihood would be a composition of three proxies with no error bar the reader can see
through. That is the five-defect shape Q-9 measured, and every slip on the way to it comes out
optimistic: a wrong number looks wrong, a wrong verdict looks like good news.

**Delivery shape under B:** one PR. It touches `cargento_runtime/web/`, so it must be the single
in-flight web PR (see AGENTS.md, Parallel Work).

**Review tier under B:** two lenses plus an arbiter. AGENTS.md's Calibrating Effort table puts a
change owning a conflict-prone surface there, and this one owns two of the three named — the `web/`
byte pins and `config.py`.

**Two findings to file rather than fold in**, both larger than a wording fix and neither in scope
here:

1. The page never sends `usage=1`, so credential-backed Claude and Cursor quota never fetches in
   normal use. That is a shipped promise (P4, DEC-1's whole cost) with no live path.
2. Two session ids in the live store appear under five harness keys each. Either session identity is
   colliding across collectors or the store is recording one session five times; either way a
   cohort keyed on harness would be wrong.

The P4 correction is **not** a third filing: whichever option the captain rules, P4's text changes,
so it belongs to DEC-12's outcome.

## Linear edits made

Nothing has been written to Linear. Everything below is a draft; the gate authorizes the write.

### Pre-edit record

Captured 2026-09-04 before any drafting, from `get_issue DRC-4009` and
`get_milestone "Don't burn capacity"`.

**The live DRC-4009 body, verbatim:**

````text
## User value

A person about to start a new task notices this once Cargento can say how likely it is to overrun the window before they commit to it, instead of finding out partway through. P4, extend: an overrun-likelihood estimate is a new clause, since the promise today reports the wall and the burn rate but not the risk of starting new work against it.

## What needs to be done

Estimate the likelihood a new task overruns the current window before the person starts it, using a size estimate matched by shape against similar past sessions.

Requires H1's session history store first. Cargento has no persistent per-session store today, only a state file. Fold this item's storage needs into H1's scoping rather than specifying it twice.

It rests on three stacked guesses: that a prompt's text predicts its duration, that a past session is meaningfully similar, and, since quota is account-scoped with no session attribution, that overrun risk can be assigned to one session at all rather than only to the account.

## Waits on

<issue id="b119a23f-5d65-4dcd-b471-c116835f06ca" href="https://linear.app/recce/issue/DRC-4044/h1-keep-a-history-of-what-happened">DRC-4044</issue> (H1, keep a history of what happened)

## Scores (blind-panel medians)

| Impact | Risk-adjusted impact | Access | Build | Detector risk |
| -- | -- | -- | -- | -- |
| 66 | 32 | 78 | 75 | 34 |

Score legend: see the Visibility 2x2 board README.
````

**The `Don't burn capacity` milestone description, verbatim:**

````text
## The user value

**Your quota in one place across vendors: the windows that reset, per-model sub-limits, cost per session, and the burn rate projected to the wall.**

## What remains

[DRC-4009](<https://linear.app/recce/issue/DRC-4009/a6-overrun-likelihood-before-you-start>): Cargento tells you how likely a task is to overrun your quota window before you start it, instead of finding out partway through.
[DRC-4334](<https://linear.app/recce/issue/DRC-4334/usage-fetcher-droid-windows-from-apibillinglimits-with-factory-api-key>): Droid's 5-hour, 7-day and 30-day windows show up in the usage band for a person on a Factory individual plan, instead of Droid being the one harness with sessions on the board and no usage number.

## What shipped, and what it changed here

2026-09-02: [DRC-4073](<https://linear.app/recce/issue/DRC-4073/usage-fetcher-droid-quota-via-factory-5h7d30d-windows-and-credits>) closed on its documented-verdict clause. Droid's `/limits` route is pinned and captured, the account on the working machine has no window for Factory to report (organization billing, not token-rate-limits billing), and DEC-10 ([DRC-4333](<https://linear.app/recce/issue/DRC-4333/dec-10-decision-which-credential-may-cargento-send-to-factory-for>)) settled the credential the reader will send. The reader itself is [DRC-4334](<https://linear.app/recce/issue/DRC-4334/usage-fetcher-droid-windows-from-apibillinglimits-with-factory-api-key>) above.

## Waits on

[DRC-4334](<https://linear.app/recce/issue/DRC-4334/usage-fetcher-droid-windows-from-apibillinglimits-with-factory-api-key>) waits on an account, not an issue: a Factory account on token-rate-limits billing that can run the recorded probe, so the windowed response shape is captured before a parser is written against it.
````

### Labels

`journey:usage` and `move:extend` are already set and both remain correct under option B — the move
table allows an `extend` to change its own promise, which is what the P4 correction needs. Nothing
for `implementation` to write. Under option A the issue is cancelled and the labels are moot.

### Drafted DEC-12, to file and link before this issue is rewritten

DEC-11 is taken (DRC-4342), so this is DEC-12. Title: `DEC-12 · Decision: May Cargento publish a
projection or a likelihood about quota it has not measured?`. Milestone: `Don't burn capacity`.
Relations: `blocks` DRC-4009; `blocks` DRC-4040 (E7) — recommended, because E7's trigger is a
projection that does not exist.

**The question, in one sentence a person can say yes or no to:** may Cargento compute and publish a
figure about quota exhaustion — a projection, a likelihood, or any verdict derived from them — when
every input it can legally compute is a proxy the reader cannot see through?

**The evidence, from the code and the live store rather than from any issue's prose:** the eight
findings in this entity's `## Problem` section, each with its file, line and falsifier. The four that
bear hardest: no projection ships and Q-9 says the promotion retired it; the page never asks for the
credential-backed fetch, so two vendors' windows never arrive; per-session consumption exists for one
harness of ten; and the only real history store holds zero closed working spans, from a build that
predates the merge.

**The options, in increasing order of what Cargento asserts.**

A. **No projection and no likelihood, ever.** Q-9's judgement is promoted from a design note to a
standing rule. A6 is cancelled. E7 is re-gated on a trigger that is not a projection, which the
attention card's percentage threshold already is. *Costs:* P4's headline is corrected to retract a
clause rather than to gain one, which is a visible walk-back on the promise that justified DEC-1.
*Forecloses:* A6, and E7's projected-wall trigger.

B. **Quantities only, never a composed verdict.** Cargento may publish named, measured quantities
with their sample count and their limitation on the surface, and may never collapse them into a
likelihood, a light, or a verdict. A6 is re-scoped to the cohort working-span figure alone. *Costs:*
the smallest of the four — no contract amendment, no new published field, one PR. *Forecloses:*
nothing A does not already foreclose. *Reason to distrust the lean:* B is the same "narrow, bounded,
guardrails" argument that carried DEC-1 and DEC-3, and the record shows that argument being made a
third time on the strength of the first two going well. B also leaves P4 promising a projection
nobody is building, so B is only honest if the P4 retraction rides with it.

C. **B, plus amend DEC-6's kept-list** so history may keep a per-session consumption figure and a
session-end stamp, giving the estimate a measured basis. *Costs:* a third amendment to the history
contract, landing before any code as DRC-4330 did for the first; a new published session-end field,
which P5 says is not shipped; and consumption exists for one harness of ten, so nine rows would carry
nothing. *Forecloses:* nothing, and buys an estimate honest for Copilot alone.

D. **Publish the likelihood.** Reverses Q-9 explicitly. *Costs:* the five false-green defects Q-9
measured are re-admitted, and the record predicted in advance that this would look like an
improvement. *Forecloses:* the ability to cite Q-9 as settled anywhere else.

**Does the precedent settle it?** Not quite, and the gap is the reason to file. Q-9 is a design-doc
judgement, not a filed decision, and the A9 cut was an owner call on a board item that deliberately
left A6 alive — `items.json` records that the cut lifted A6's redundancy penalty rather than taking
A6 with it. So the captain has already declined once to let the A9 ruling reach A6. DEC-3's handling
of C7 is the closer precedent and points the other way: C7 was cancelled rather than gated on a
second decision, on the grounds that its own body already concluded it was unreachable and at
risk-adjusted 31 it was not worth a second decision to establish that again. A6 sits at 32. The
difference is that A6's body does not concede unreachability, and A6 has a live sibling in E7.

**What is already settled and is not being reopened:** DEC-1 (the quota fetch), DEC-6 (the store may
exist, on by default, bounded), and the never-list. Nothing here proposes prompt text in the store.

**Recommended answer: B, with the P4 retraction riding with it.**

### Drafted rewrite of DRC-4009, contingent on a B ruling

Send unwrapped — join each paragraph to one line before sending. Superseded content is demoted, not
deleted.

````text
## User value

A person deciding whether to start work in this project notices this when Cargento shows how long work here has actually taken, beside the reset it already shows, instead of leaving them to guess. P4, extend: the spread of observed working spans is a new clause, and the same edit retracts P4's claim to project a burn rate to the wall, which the promoted interface does not do.

## What needs to be done

Publish, per project and harness, the spread of closed working spans this server observed in its own history store — median, 80th percentile, longest, and the sample count — and render one line naming them, their unit, and what they are a measurement of. Show nothing for a cohort below the minimum sample count.

Cargento states the quantity and never the conclusion. No likelihood, no light, no comparison against a reset or a quota level. The reader races the figures against the reset checkpoint the quota card already carries.

The figures are truncated low by construction and the surface says so: an observation is written only on a state change, so a session already working when the server started opens its span at first sighting rather than at the real start, and last_activity is the whole subtree including subagents.

Ruled at DEC-12. The three stacked guesses the earlier body named are not carried forward: the first needs prompt text, which the history contract bans outright; the third needs per-session consumption, which one harness of ten reports.

## Historical, superseded 2026-09-04

The body below is what was believed when this issue was filed on 2026-08-03, kept as the record of what was believed and when. Triage against main at 4de75d2 found its method unbuildable — the size estimate it names is derived from prompt text, which SECURITY.md's history never-list bans in any field — and found that the surface it composes against was retired by the interface promotion.

[the captured body above, verbatim]

## Scores (blind-panel medians)

[unchanged]
````

### Drafted milestone correction

Two authorized edits to `Don't burn capacity`, and nothing else moves. `save_milestone` has no patch
operation, so build them by script from the capture above, assert each target passage is present
exactly once before replacing, and diff — **expect exactly two hunks.**

1. In `## The user value`, the headline clause `and the burn rate projected to the wall` becomes
   `and how long work in a project has actually taken`. The projection is not shipped; Q-9 retired
   it.
2. In `## What remains`, the DRC-4009 line becomes: Cargento shows how long work in this project has
   actually taken, beside the reset it already shows, so you can judge whether to start. Gated on
   DEC-12 until the captain rules whether Cargento may project or only measure.

Edit 1 changes the milestone headline, which is the promise-map P4 headline restated. If the captain
rules A rather than B, edit 1 stands and edit 2 becomes a cancellation note instead.

### Write mechanics `implementation` must not rediscover

- Send every body unwrapped; entity files here are hard-wrapped at 100 columns and Linear reads those
  newlines as hard breaks.
- Do not end an emphasis run immediately before a code span in anything authored here; the drafts
  above already avoid it. Write approved drafts verbatim and report any boundary move rather than
  repairing it.
- Every issue reference becomes a mention and a mention creates `relatedTo` edges nobody asked for,
  markdown links included. Read the relation set back after each body write.
- Check a Linear error against read-back state before retrying it: adding `relatedTo` converts an
  existing blocking relation, and the call reports a removal failure while everything landed.

## Expected surface and tolerance

For the option B build. Oracles are costed separately from the runtime, per the DRC-4037 rule.

**Runtime — about 150 lines across 5 files.**

| File | Lines | What |
|---|---|---|
| `cargento_runtime/history.py` | ~70 | A pure derivation over `tuple[Observation, ...]`: closed spans per `(project, harness)`, the three figures and `n`. Stays inside this module on purpose — see below. |
| `cargento_runtime/aggregate.py` | ~15 | Publish the field beside `history`, keyed the same way so absent means "draw nothing". |
| `cargento_runtime/config.py` | ~8 | The minimum sample count. Reuse `history_retention_sec` for the lookback rather than adding a second knob. |
| `web/next-project.js` | ~40 | The one rendered line, and nothing when the field is absent. |
| `web/styles.css` | ~15 | |

**Oracles — about 420 lines across 5 files, two of them compelled rather than chosen.**

| File | Lines | Compelled? |
|---|---|---|
| `tests/test_history.py` | ~250 | Chosen. Below-threshold, unclosed span, first-sighting truncation, retention boundary, the published field-set pin. |
| `tests/test_next_project.py` | ~120 | Chosen. Renders with and without the field. |
| `tests/test_next_page.py` | ~16 | **Compelled.** Per-part byte pins and the assembled-page digest for any `web/` change. H1 PR 2 changed exactly 16 lines here. |
| `tests/test_contracts.py` | ~20 | Chosen. |
| `tests/test_config_diagnostics.py` | ~30 | **Compelled** by the new config field. H1 PR 1 changed it by 15 lines, PR 2 by 31. |

**Docs — `promise-map.md` P4 (the `extend` move allows it, and the retraction is required),
`docs/design-usage-quota.md` (a subsection recording why this is a quantity and not a verdict,
pointing at Q-9), and one clause in `SKILL.md`'s Project paragraph — the conflict hotspot; keep the
edit inside the paragraph the feature belongs to.**

**A new runtime module would compel four more one-line edits** — `scripts/validate_plugins.py`'s
`CARGENTO_RUNTIME_FILES`, `docs/design-runtime-architecture.md`, `AGENTS.md`'s tree, and
`scripts/bench_collect.py`. Measured on H1 PR 1, which added `history.py` and touched all four.
Keeping the derivation inside `history.py` is what avoids them, and it is a design constraint rather
than a coincidence: `history.py` is a leaf over `config` and a pure derivation adds no edge.

**Total: about 570 lines across 12 files. Tolerance: runtime ±40 per cent, oracles ±60 per cent** —
to roughly 800 lines and 14 files before it is an overrun that needs explaining. The asymmetry is
deliberate and is the DRC-4037 lesson: there the runtime landed at exactly the declared figure while
the oracles came in at 9 files and +541 against 6 declared.

**Semantics this may move:** P4's text, and `SKILL.md`'s description of what the board shows. Neither
is moved by the code.

**Which parts rest on a mechanism nobody has yet exercised.** Named explicitly, given this week's
three overruns.

1. **The input has never been observed to exist.** The only history store on this machine holds zero
   closed working spans, and it predates the merge. Whether any cohort on a real machine clears a
   minimum sample count is unmeasured. If none does, the feature renders nothing on the machine it
   was built for. This is the largest risk in the estimate and it is not remote.
2. **The truncation bias has no measured size.** `last_activity` is a subtree stamp; nothing
   establishes how far a subagent moves a parent's.
3. **The harness key may not be a valid cohort key.** Two session ids in the live store appear under
   five harness keys each.

**Before any of this is built, run the cheapest check that can fail:** leave a dashboard running for
a working day and count closed spans in the store. If the answer is near zero, option B does not
deliver a visible figure either and the honest ruling is A.

## Acceptance criteria

Contingent on a B ruling at the gate. Under A they are void; under C they gain a fourth for the
amendment landing first.

**AC1 — the published figures exist exactly when they were measured. (offline)**
For a history store holding at least `N` closed working spans for a `(project, harness)` cohort,
`/api/data` publishes for that cohort an object carrying the median, the 80th percentile, the longest
span in seconds and the sample count; for a cohort at `N-1` it publishes nothing for that cohort.
*Verified by:* a unit test in `tests/test_history.py` over fixture observation tuples at `N` and
`N-1`. *Falsified by:* a cohort at `N-1` acquiring the object, or the median moving when a span
outside the retention window is added.

**AC2 — a reader sees the figures and the sample count, or sees nothing. (offline, user-visible)**
The project view renders one line naming the three figures, their unit, the sample count and what
they are a measurement of, and renders nothing at all when the payload carries no object for that
cohort. *Verified by:* a page-script test in `tests/test_next_project.py` executing the built page
against a payload with and without the field. *Falsified by:* the line rendering with the sample
count absent, or rendering any figure when the field is absent.

**AC3 — no verdict can be added without a test failing. (offline)**
The published object's key set is exactly the four names above. *Verified by:* a contract test in
`tests/test_contracts.py` pinning the key set. *Falsified by:* adding a fifth key — a likelihood, a
tone, a comparison against a reset — which the pin rejects. This is the criterion that makes option B
enforceable rather than a promise, and it is a real pin rather than a prose grep: the expected value
is a literal set stated in the test, and the production code can diverge from it.

**AC4 — a span is only ever what was stored, never inferred. (offline)**
A span is counted only where the store holds a `working` observation followed by a non-`working`
observation for the same `(harness, sid)`. A sid whose first stored observation is `idle`, and one
whose `working` observation has no successor, both contribute nothing. A span opening at first
sighting is counted at its stored length even where the real work started earlier, and the rendered
line says the figures are truncated low. *Verified by:* unit tests over both fixtures asserting the
sample count does not move, plus AC2's render test asserting the qualifier. *Falsified by:* the
derivation reading a start from `started_at` or any source other than a stored observation.

**AC5 — the figures move as work happens. (interactive)**
On a live board against a real project, an observed `working` to `idle` transition raises that
cohort's sample count by exactly one and the figures change accordingly. *Verified by:*
`live session:<recorded drive>` — `curl /api/data` before and after a transition, comparing the
sample count. *Falsified by:* the count not moving across an observed transition, which is also the
negative case: a poll with no transition must leave it unchanged.

## Test plan

Test-first, per the workflow rule. Write AC3's key-set pin before the derivation exists and watch it
fail for the right reason; then AC1's threshold cases; then AC4's two exclusion fixtures; then the
render test; then recompute the byte pins from the assets rather than resolving any conflict in them
textually. AC5 is the live scenario and is graded on the durable before/after state of the payload
plus the observed line, with the no-transition poll as the negative case that reds it.

Run the full suite once. Confirm any failure in `test_http_api`, `test_page`, `test_lifecycle` or
`test_quota` by running that module alone before believing it — a sibling worktree manufactures those
(AGENTS.md, Parallel Work).

## Review depth

Two lenses plus an arbiter, per AGENTS.md's Calibrating Effort table: the change owns two of the three
named conflict-prone surfaces, the `web/` byte pins and `config.py`. Not full adversarial — no
credential, no data loss, and nothing leaves the machine. The arbiter reproduces findings rather than
ranking them.

### Feedback Cycles

## Out of scope

- Any likelihood, verdict, light or comparison against a reset or a quota level. That is what DEC-12
  rules on and what AC3 pins against.
- Restoring the burn projection the promotion retired. It is a consequence of DEC-12's ruling, not
  part of this issue.
- Amending DEC-6's kept-list to admit consumption or a session-end stamp. That is option C.
- The two findings recommended for filing: the page never sending `usage=1`, and the five-harness
  session-id collision in the live store.
- Prompt-derived size estimation, in any form. The contract bans it and no ruling here reopens it.

## Stage Report: triage

- DONE: Pre-edit record first — the live DRC-4009 body and the `Don't burn capacity` milestone
  description copied verbatim under `## Linear edits made` before any drafting — then the rewrite and
  any milestone correction drafted in this entity only, nothing written to Linear; and the
  adversarial read done against the tree at today's `main` tip with H1 merged (the history store, its
  published `history` field, the seeded panels): every claim in the body checked against the code and
  named as still true or as describing a state that no longer exists, above all the three stacked
  guesses the body itself names (prompt text predicts duration; a past session is meaningfully
  similar; overrun risk can be attributed to one session when quota is account-scoped), each turned
  into a question the code or the stores can answer, with what the history store actually records
  (five fields, no prompt text by contract) set against what an estimate would need.
  Both captures taken from Linear before drafting; nine claims checked at `4de75d2`, each with a file,
  a line and a falsifier. Guess 1 answered by `SECURITY.md`'s never-list; guess 2 by the store's only
  similarity keys and its five-harness sid collision; guess 3 by `sessions.py:282-295` (`consumption`
  is Copilot alone) and `aggregate.py:191-197` (`rate_per_min` null for four harnesses).
- DONE: A decision on whether A6 is buildable as filed or needs a product decision nobody has filed
  — if the overrun estimate cannot be attributed to a session, or needs a field the history contract
  bans, the honest product is a filed decision issue with its `blocks` edge drafted, and this issue's
  rewrite says so rather than guessing; if it is buildable, the narrowest shape that a user can see
  (the estimate on the row before a task starts) with the simplest rejected alternative and why it
  cannot deliver the value, the delivery shape and review tier from AGENTS.md's table, and whether it
  touches `cargento_runtime/web/`.
  Not buildable as filed, on both named triggers. DEC-12 drafted with its one-sentence question, four
  options with costs, the precedent read honestly both ways, and a `blocks` edge onto DRC-4009 plus a
  recommended one onto DRC-4040. Recommended answer B, with the contingent narrow shape, its rejected
  alternative, one PR, two lenses plus an arbiter, and yes it touches `cargento_runtime/web/`.
- DONE: Acceptance criteria as end-state properties, each offline or interactive with a
  `Verified by:` and a `Falsified by:`, at least one a property a user can see, plus an expected
  surface with tolerance that costs the oracles separately and names the compelled test edits — and,
  given this week's three overruns, an explicit statement of which parts of the estimate rest on a
  mechanism nobody has yet exercised (the DRC-4037 rule: cost the oracles the repository's contracts
  will demand, not only the ones the feature wants).
  Five ACs, four offline and one interactive, AC2 user-visible. AC3 pins the published key set, which
  is what makes option B enforceable and is not a prose grep — a fifth key fails it. Surface: ~150
  runtime lines over 5 files against ~420 oracle lines over 5, two compelled (`test_next_page.py`'s
  byte pins, `test_config_diagnostics.py`'s config field), with the four further edits a new module
  would have compelled named and designed around. Three unexercised mechanisms stated, the first
  being that the input has never been observed to exist.

### Summary

A6 is not buildable as filed, for three independent reasons and a fourth nobody expected. Its size
estimate needs prompt text, which the history contract bans in any field; its target quantity is
measured for one harness of ten; its composition step is the burn-row verdict this repository built,
measured, deleted and recorded as keep-rejected; and the surface it would compose against was retired
by the interface promotion — no projection ships, and the page never sends `usage=1`, so Claude's and
Cursor's windows are never fetched at all. The live history store was measured rather than assumed:
25 entries, 17 session ids, **zero closed working spans**, from a build predating the merge. So the
honest product is DEC-12, drafted here with a recommendation of option B (quantities, never a
composed verdict) and the contingent narrow rewrite, ACs and surface estimate ready for that ruling.
Two further findings are recommended for filing rather than folded in.
