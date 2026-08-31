# Future UI Attention Queue Design

**Status:** Draft for captain review on 2026-08-31

## Decision

The opt-in `?next=true` page will open on an exception-first `Attention` route. `Projects` will
remain the complete project map, and `Sessions` will remain the flat session inventory. All three
will be adjacent primary navigation links.

Attention will summarize the latest observed payload, disclose reporting coverage, rank only
source-backed exceptions, show published upcoming checkpoints, and compress everything else. It
will never translate missing evidence into an all-clear, a prediction, a repository identity, a
completion cause, or a human-authority claim.

This document specifies behavior. It does not authorize implementation.

## Purpose

A person supervising many agents should answer these questions within five seconds:

1. What needs me now?
2. What is blocked, failing, or risky?
3. What is moving?
4. What source-published checkpoint comes next?
5. What stopped and still needs a closing decision?
6. Which sources could not report enough evidence for me to look away?

The design makes the hard fleet question legible without weakening the exact facts Cargento already
collects. The page selects and orders facts; it does not generate a semantic interpretation with a
model.

## Non-goals

This iteration will not:

- change the stable dashboard or serve the new surface without `?next=true`;
- merge or target `main`;
- add a sidecar model, generated summary, forecast, or numerical severity score;
- infer a repository from the last two path segments in `session.project`;
- call an observed stop “finished,” “unread,” “successful,” “failed,” or “died” without a source
  that publishes that distinction;
- infer progress from token rate, activity from task progress, or health from silence;
- use Cargento-derived `eta_h` or `turn.eta_h` as a source-published prediction;
- add queue-level answer, dismiss, steer, or guardrail controls; existing controls remain on their
  current detail surfaces;
- replace the complete Projects or Sessions inventories with the exception queue.

## Terms and truth rules

The design uses four distinct concepts:

- A **fact** is a bounded value in the current `/api/data` payload.
- A **capability** says whether a discovered harness can publish a class of fact. Silence is useful
  only when the matching capability is known.
- A **signal** is a deterministic browser classification over facts, such as `loop != null` becoming
  `Repeated tool failures`.
- A **claim** is the visible sentence. Every claim below names its exact fact and predicate.

The payload clock owns source ages. Item age uses `generated` minus a source timestamp or the
payload's own `asks[].age_sec`. Browser time may describe only the age of the last successful HTTP
refresh in the accepted stale-data notice.

Missing, malformed, or contradictory values drop the unsupported claim. They never fall back to a
stronger interpretation. Fixed UI copy may explain the smaller fact that remains.

## User questions and owning views

| Question | Owning view | Answer |
|---|---|---|
| What deserves attention? | Attention | Ranked exceptions, published checkpoints, compact fleet remainder, and coverage. |
| Is every project represented? | Projects | Every session in the current payload, grouped by display label exactly once. |
| Which exact session supplied this fact? | Sessions or session detail | Harness, full session ID, state, source-backed context, and exact route. |
| What is this project doing? | Project detail | Its current sessions and any Spacedock workflow evidence, without treating the display label as directory identity. |
| What is this agent doing now? | Session detail | Current activity first, then supported assignment, next task, and exact request. |
| Is it safe to look away? | Attention coverage | A bounded coverage answer, never an unconditional all-clear. |

## Route and navigation model

The top-level routes are:

- `#n=attention` — default;
- `#n=projects` — complete project map;
- `#n=sessions` — flat session inventory.

Existing detail routes remain `#n=project:<encoded-project>` and
`#n=session:<encoded-project>:<encoded-session>`. A bare fragment, an invalid fragment, and the old
`#n=overview` token normalize to `#n=attention`. The `next=true` query remains the only switch that
selects these bytes.

Primary navigation uses three native links inside `nav[aria-label="Primary"]`, with
`aria-current="page"` on the current route. These are routes, not an ARIA tab widget. Tab and
Shift+Tab move through Attention, Projects, and Sessions in that order; Enter follows the focused
link. Guarded `a`, `p`, and `s` shortcuts mirror the links and retain the current input/modifier
guards.

The primary navigation remains visible on every detail route. A project breadcrumb links to
Attention and Projects. A session breadcrumb links to Attention, Projects, and its containing
project. Browser Back preserves the actual origin route; breadcrumbs provide canonical navigation
without pretending to know where the person came from.

## Layout wireframes

Wide layout, at least 900 CSS pixels:

```text
Cargento | ATTENTION   PROJECTS   SESSIONS                 ● 3 moving

ATTENTION
OBSERVED NOW   2 need you · 1 at risk · 3 moving · 4 quiet
COVERAGE       Gates: 2/3 reporting · 1 unknown | Ends: fleet coverage unknown

NEEDS YOU NOW (2)
Question waiting · Ship release · alpha · Captain · Claude · 8m
NOW  Approve deploy
NEXT Run checks

AT RISK (1)
Repeated tool failures · beta / 7f12 · Claude · current turn
NOW  Bash failed 4 times

CLOSE THE LOOP (1)
Stop observed · gamma / 9ac1 · Codex · 22m
NOW  3 changed entries

COMING NEXT (2)
Published task · delta / 18ab · Claude
NOW  working
NEXT Deploy docs

HEALTHY FLEET · NO PUBLISHED EXCEPTION
7 other sessions · 3 moving · 4 quiet                     View all projects →
```

Narrow layout, 320 CSS pixels:

```text
Cargento
[Attention] [Projects] [Sessions]

ATTENTION
2 need you · 1 at risk
Coverage: gates 2/3 reporting · 1 unknown

NEEDS YOU NOW (2)
┌ Question waiting · 8m
│ Ship release · alpha
│ NOW   Approve deploy
│ NEXT  Run checks
│ Captain · Claude
└

AT RISK (1)
┌ Repeated tool failures
│ beta · 7f12
│ NOW   Bash failed 4 times
│ Claude
└

HEALTHY FLEET
7 with no published exception
3 moving · 4 quiet
[View all projects]
```

At narrow widths, each semantic column becomes a labelled line inside the same item. Missing lines
disappear; an empty `NEXT` label never remains. The page has no horizontal viewport scroll at 320
CSS pixels.

## Attention brief

The route starts with one h1, `Attention`, followed by two compact lines.

`OBSERVED NOW` counts subjects in each visible section plus moving and quiet sessions in the
compressed remainder. It says `observed` because the counts describe the current payload window,
not the machine. It never says `all clear`, `safe`, `healthy`, or `nothing needs you`.

`COVERAGE` leads with the capability most likely to create a false all-clear: needs-input reporting.
For each discovered harness:

- `error != null` means reporting failed for this payload;
- `error == null && reports_needs_input == true` means its gate silence is meaningful;
- `error == null && reports_needs_input == false` means gates are unknown;
- `discovered == false` stays outside the current-fleet denominator.

The visible line reports `Gates: X/Y reporting · N unknown`, adds `M failed` when needed, and says
`Ends: fleet coverage not reported`. `Y` is the number of discovered harnesses; every harness falls
into exactly one of reporting, unknown, or failed. A secondary native details disclosure, closed by
default, lists harness names, token-rate coverage, and positive stop-observation counts. It uses the
same plain-language source names as session source coverage.

The current payload has no fleet capability flag for stop observation, termination cause, git-at-
stop probing, tasks, or checkpoints. The disclosure reports positive row evidence, such as
`Stops observed on 2 sessions`, and adds `fleet coverage not reported`. It never turns absent row
values into a denominator. `Termination cause not reported` is the honest answer to whether an agent
died quietly.

Coverage remains visible even when every count is zero. Provenance stays compact, but uncertainty
never hides behind a click.

## Queue subjects and de-duplication

The browser first builds subjects, then attaches signals.

- A matched session subject is keyed by `harness + sid`.
- All unresolved asks whose `session_id` resolves to that exact session attach to its subject in
  payload order.
- An ask with no exact session match remains an ask subject keyed by `ask.id`.
- A quota subject is keyed by `harness + window/model key`.
- A display-label conflict is keyed by the exact display label.

A session subject appears in its highest ordered section only. Lower-section signals become short,
source-backed lines on that item. Thus a session with an exact ask and repeated tool failures stays
under Needs you now and mentions the failure once; it does not become a second At risk card.
Multiple asks on one exact session remain separate question lines inside that subject so no required
response disappears.

When a display-label conflict subject enters At risk, it represents its member sessions for
top-level de-duplication. Those sessions do not also inflate Healthy fleet, although Projects and
Sessions still show every exact row. A session subject with several asks ranks by its oldest ask
and uses the first matching ask's payload position as its final ask tie-break.

Coming next excludes sessions already present in Needs you now, At risk, or Close the loop. Their
published next task appears on their existing item. This rule keeps one subject in one place without
discarding its checkpoint.

## Signal taxonomy and source predicates

### Needs you now

| Visible claim | Exact predicate | Allowed detail | Forbidden inference |
|---|---|---|---|
| `Question waiting` | Non-empty `asks[].question`; exact session match when `session_id` equals `sessions[].sid`. | Question, `age_sec`, ask options count, harness, project display label, and exact session route. | The question caused the session's state. |
| `CAPTAIN` | The matched ask owner has a non-null object-valued, non-array Spacedock record. | Human responsibility on that exact subject. | Authority from another session with the same project label. |
| `NEEDS YOU` | An exact ask exists and the matched owner lacks Spacedock evidence, or the ask has no resolvable owner. | Neutral human attention. | Captain authority or verified project ownership. |
| `Input signal observed` | Session `state == "needs_input"` with no matched exact ask. | Escaped `state_detail` when non-empty and age from valid `blocked_since`. | A question, request wording, or answer options. |

An unresolved exact ask ranks above a bare needs-input state because it supplies an actionable
question. Exact asks sort by greatest `age_sec`, then payload ask order. Bare input signals sort by
oldest valid `blocked_since`; rows without a valid stamp follow stamped rows.

### At risk

| Visible claim | Exact predicate | Allowed detail | Forbidden inference |
|---|---|---|---|
| `Attribution conflict` | An ask's `session_id` resolves, but its non-empty `project` differs from that session's `project`; or boolean `dirty`/integer `changed` is published without a valid `finished_at`; or `finished_at` coexists with a working/active row. | The two bounded readings, labelled by source. | Which reading is correct. |
| `Repeated tool failures` | Session `loop` is an object and `loop.errors` is a positive integer. | Error count and escaped `loop.tool` when present. | Intent, productivity, root cause, or future failure. |
| `Quota pressure` | A parent usage entry has `state == "ok"`, and one nested window/model row has integer `pct >= 70`. | Exact percent and valid `resetAt`; 90+ is critical copy/color, 70–89 is warning copy/color. | Exhaustion time or future consumption rate. |
| `Long-running turn` | `state == "working"` and `turn.long === true`. | Source-published current activity and `turn.elapsed_h` as the bounded runtime reading. | That the session is stuck, or that `turn.eta_h` will prove completion. |
| `Identity collision` | At least two current sessions share the same non-empty `project` display label. | Count, exact session identities, and the existing collision caveat. | Same directory, repository, branch, or causal interference. |

An attribution conflict on a subject with an exact ask remains under Needs you now and appears as a
secondary signal. The same signal ranks first in At risk only when no higher-section signal owns
the subject. Within At risk, kinds sort in the table's order. Attribution conflicts use source
order; loops use descending error count; quota items use descending percent then earliest valid reset;
long turns use stable identity because the payload publishes no numeric turn-start value; label
collisions use descending session count. Stable identity tie-breaks are defined below.

Collector failures belong in coverage, not as synthetic session items, because a failed collector
publishes no trustworthy session identity to route to.

### Close the loop

| Visible claim | Exact predicate | Allowed detail | Forbidden inference |
|---|---|---|---|
| `Stop observed with uncommitted work` | Valid `finished_at`, `state == "idle"`, and `dirty === true`. | Age and `${changed} changed entries` when `changed` is a non-negative integer. | Files rather than porcelain entries, unfinished task, failure, or unread status. |
| `Stop observed; git state clean` | Same stop predicate and `dirty === false`. | Stop age and exact clean reading. | Successful outcome or completed project. |
| `Stop observed; git state not measured` | Same stop predicate and `dirty == null`. | Stop age plus the explicit measurement limit. | Clean tree. |

Close-the-loop items sort dirty, unknown, then clean. Each group sorts by oldest `finished_at`, then
stable identity. The section title is a call to inspect or dismiss; it is not proof that the person
has not read the result.

No current predicate supports `died`, `crashed`, `finished`, `successful`, or `unread`. A future
termination-cause or read-receipt field may add those signals only with its own capability metadata.

### Coming next

| Visible claim | Exact predicate | Allowed detail | Forbidden inference |
|---|---|---|---|
| `Published task` | First task with `status == "in_progress"`; otherwise first task with `status == "pending"`, preserving source order. | Escaped `activeForm` or `subject`, status, and owning exact session. | Estimated completion or dependency order beyond source order. |
| `Published reset` | A quota-pressure item's selected window has a valid numeric `resetAt`. | Absolute/local reset wording derived from that instant. | That capacity will be available or work will resume. |

Published reset stays on its At risk quota item rather than duplicating the subject under Coming
next. Coming next therefore contains source-published session tasks in the current contract.

Top-level `eta_h` and `turn.eta_h` are Cargento estimates derived from task or turn history. They do
not satisfy the source-published rule and do not appear in Attention. A future explicit checkpoint
or ETA needs an owning source, an instant or bounded text value, and capability metadata before it
can enter this taxonomy.

Coming-next subjects sort in-progress before pending, then working before idle, then stable
identity. Task order inside a subject remains payload order.

### Healthy fleet

Healthy fleet contains every current session subject neither placed nor represented in the four
sections above. It is a compressed remainder, not a list of healthy verdicts.

The visible sentence is `N sessions with no published exception`, followed by exact state counts
such as `3 moving · 4 quiet`. `Moving` requires `state == "working"`; `quiet` requires
`state == "idle"`. Unknown states get an `unknown state` count and never join either bucket.

The section carries the qualifier `No published exception; coverage applies` and links to Projects.
It does not enumerate session cards or add a disclosure; Projects owns the complete map.

## Stable tie-breaks

No item receives a severity score. Every comparator is a visible rule:

1. fixed section order: Needs you now, At risk, Close the loop, Coming next, Healthy fleet;
2. fixed signal-kind order within each section;
3. the kind-specific age or magnitude described above;
4. harness order from `harnesses[]`;
5. normalized raw project display label, escaped only at render time;
6. full `sid`;
7. source array position, then stable source ID when present.

The comparator may use a payload array index only as its final tie-break. It may not parse display
strings such as `turn.elapsed_h`, token-rate labels, or formatted reset text back into numbers.

## Queue-item grammar

Every expanded item follows the same reading order:

1. **Why it matters** — one fixed signal label and optional secondary signal count.
2. **Outcome or identity** — a source-backed assignment/workflow goal when exactly attributable;
   otherwise project display label, harness, and exact session identity.
3. **Now** — exact question, state detail, loop count, quota percent, stop reading, or task state.
4. **Next known checkpoint** — only a published task or reset instant; omit the entire line when
   absent.
5. **Source, responsibility, or age** — harness/source and valid age; `CAPTAIN` or `NEEDS YOU` only
   under the exact ask rules.

An exact subject's `asked` instruction supplies its assignment. One distinct non-empty Spacedock
workflow goal on that exact session supplies its outcome. `last_prompt` and clipped titles remain
identity/context, never durable outcomes. If several workflows supply different goals, the item
uses identity rather than choosing one.

The item heading is the sole route link. Nested answer or control buttons do not appear in this
iteration. Fixed labels may be visually compact, but screen-reader order must match the five-part
grammar.

## Source and capability coverage contract

| Capability or fact | Current owner | Fleet-negative claim allowed? |
|---|---|---|
| Exact requests | `asks[]` and top-level `ask` capability | Only `No exact requests published` when `ask === true`; absence of the top-level capability means unavailable, not zero. |
| Needs-input state | `harnesses[].reports_needs_input`, `error`, and session `state` | Yes, per discovered reporting harness with no collector error. Blind or failed harnesses remain unknown. |
| Token rate | `harnesses[].reports_rate`, `error`, and session `rate_per_min` | Yes for measurement presence, never for productivity or health. |
| Tasks/checkpoints | Session `tasks[]` | Positive row claims only; no fleet capability exists. |
| Loop signal | Session `loop` | Positive row claims only; absence is not fleet proof of no thrash. |
| Long turn | Session `turn.long` | Positive row claims only; absence of `turn` is unmeasured. |
| Stop observation | Session `finished_at` and `acquisition` | Positive row claims only; no fleet capability exists. |
| Git at stop | Session `dirty`, `changed`, and matching `finished_at` | Positive/unknown row claims only; null never means clean. |
| Project identity | Session `project` display label | No. It is a lossy label; collisions require a caveat. |
| Spacedock authority | Exact session's non-null Spacedock record | Only for that exact session and its asks. |
| Quota/reset | `usage[]` window/model records with `state`, `pct`, and `resetAt` | Positive row claims only; missing usage may be unsupported, disabled, unavailable, or not fetched. |
| Termination cause/read state | No current field | Never. Coverage says not reported. |

The browser must not derive a capability by scanning for one lucky non-null session field. A
positive field proves that row only. Fleet ratios require published harness metadata.

## Projects contract

Projects is the complete map for the current payload window. Every session appears in exactly one
group keyed by its `project` display label, including sessions with no Attention signal. The view
uses the term `display label` wherever grouping ambiguity matters.

Rows show only supported aggregates: session counts, exact ask/risk/stop counts, current state
counts, source task progress, and concrete Spacedock workflow chips. Missing estimate, delegation,
workflow, response, or progress facts do not leave labelled gaps.

Projects sorts groups by exact requests, At risk signals, Close-the-loop signals, active work, then
quiet groups. Stable first-seen project order breaks ties. This is an explainable attention order,
not a project-health score. A `View all projects` link from Healthy fleet focuses the Projects h1.

Two or more sessions with one display label always retain the existing collision caveat. The page
must not say they share a repository, worktree, branch, or directory.

## Project-detail contract

Project detail answers what the selected display-label group is doing. It preserves the accepted
rules from checkpoint `94f19d3`:

- omit the entire workflow region when no grouped session supplies Spacedock evidence;
- keep distinct workflow strips distinct;
- render `GOING ON` from current session state, not `active` alone;
- render completed source tasks without claiming retained history;
- retain exact session routes, same-label caveat, workstream window, and local-only control labels;
- never aggregate exact-session authority across the group.

Project detail adds no second Attention summary. Its existing session cards retain the exact state
and routes that support the queue. It must not create a project-level risk or authority claim from
unrelated siblings.

## Sessions and session-detail contract

Sessions remains a complete flat inventory for the current payload window. It preserves exact ask
order, the working long-turn ladder, nearest-idle order, full session routes, and the shared-label
caveat.

Session detail preserves the four-part progressive frame from `94f19d3`:

1. current activity always leads;
2. `ASSIGNMENT` appears only for an `asked` instruction;
3. `NEXT` appears only for the first in-progress or pending source task and is suppressed as a
   duplicate response when an exact ask owns the next human action;
4. exact asks render `NEEDS YOU`, or `CAPTAIN` only when that same session supplies Spacedock.

Missing command facts remain in secondary, collapsed, plain-language source coverage. Attention
links do not change this hierarchy; they only select the exact session.

## Transitions and refresh behavior

Each successful payload replaces the previous signal set atomically. The browser recomputes
subjects, sections, and tie-breaks from that payload. The live status announces count changes only;
it does not say why an item moved between sections.

Focus never follows a reordered item. If the focused subject survives a refresh, focus stays on its
route link. If it disappears, programmatic focus moves to the containing section heading, which
receives `tabindex="-1"`; if the section also disappears, focus moves to the Attention h1 by the
same mechanism. A polite status region announces count changes only,
such as `Attention updated: 2 need you, 1 at risk`.

The accepted refresh boundary remains:

- first `/api/data` failure stays quiet;
- second consecutive failure preserves the last successful payload and says live refresh failed;
- the notice states stale risk, last-success age when known, active automatic retry cadence, and a
  serialized `Retry now` action;
- a successful refresh clears the failure count and notice.

While stale, source-derived item ages and ordering remain frozen to the retained payload's
`generated` clock. Only the notice's last-success age advances with browser time.

## Keyboard and screen-reader behavior

- The page has one `main` landmark and one h1 for the active route.
- Primary navigation is a labelled nav of native links with `aria-current`, not a partial tab
  pattern.
- Attention sections use h2 headings with visible counts. Each queue is an ordered list of list
  items; each expanded item has one article and one heading link.
- The five-part grammar is the DOM order. CSS never reorders it.
- Fixed labels accompany values; color, animation, and position never carry a signal alone.
- Coverage uncertainty is visible text. Its closed-by-default details control uses native
  summary/details semantics.
- Refresh status uses a polite status region. It does not repeatedly announce the whole queue.
- Enter follows item and navigation links. Escape on detail routes follows the existing breadcrumb
  behavior without trapping focus.
- Motion reduction disables live-dot and transition animation. Reordering uses no motion.
- At 320 CSS pixels, all labels wrap, every interactive control has at least a 44-CSS-pixel block
  size and a 44-CSS-pixel inline hit area, and the document has no horizontal viewport overflow.

## Empty, stale, partial, and conflicting states

### No sessions

Attention says `No sessions in this <window_hours>h payload`. It still renders coverage. It does not
say no agents exist, no work is running, or nothing needs the reader.

Projects and Sessions render route-specific empty sentences. They do not redirect to Attention.

### No published exceptions

The brief shows zero section counts, and the page omits empty Needs you now, At risk, Close the
loop, and Coming next sections. Healthy fleet says `N sessions with no published exception` and
keeps the coverage qualifier visible. It never says `all clear`.

### Partial reporting

A discovered harness with `error != null` contributes `reporting failed` to coverage. The UI does
not expose raw exception text in the primary surface. A discovered harness without a capability
contributes `unknown`, not zero. Sessions successfully published by other harnesses remain visible.

### Conflicting signals

Attribution conflicts rank first in At risk. The item prints the bounded readings side by side and
uses neutral copy such as `Sources disagree`. It does not choose a winner. Exact asks still remain
visible and neutral if their owner cannot be resolved.

### Duplicate project labels

The conflict is scope ambiguity, not proof of concurrent work in one repository. Attention shows
one Identity collision subject; Projects and Sessions retain each exact row and route.

### Missing or malformed facts

Malformed signals are dropped at their predicate boundary. The subject can still appear from a
different valid signal. A malformed item never takes down the route or changes another subject's
rank.

### Missing detail subject

A project or session route whose subject is absent from the latest payload says `Not present in the
current payload` and links to the appropriate complete map. It does not claim deletion or
completion.

## Security and escaping

All payload text is untrusted. Render sites escape questions, options, titles, project labels,
state detail, task text, workflow names/goals, tool names, harness labels, and error-independent
identities before interpolation. Route segments use `encodeURIComponent`; route parsing catches
decode failures and falls back to Attention.

The primary Attention route renders no raw collector exception, filesystem path, transcript path,
HTML, Markdown, or model output. It adds no network destination and no write endpoint. Existing ask
answers remain on the loopback session-detail path and keep their current request validation.

Attention preferences, if later required, must use the `cargento.next.` storage namespace. This
design needs no new preference or storage key.

## Data-flow boundaries

The server remains the owner of collection, normalization, redaction, event reduction, asks,
dismissals, git probing, Spacedock cartography, quota shape, and harness capability metadata. The
browser receives one published snapshot and does not re-read stores.

The browser may perform only these deterministic transformations:

1. validate source predicates without repairing malformed values;
2. resolve an ask by exact `session_id`;
3. build row-, ask-, quota-, and display-label subjects;
4. attach named signals from the taxonomy;
5. select each session subject's highest section;
6. apply the documented comparator chain;
7. render escaped claims and coverage.

The classification layer must be pure: equal payload bytes produce equal subjects, sections, and
order. It receives no browser clock, local model, network response, or retained observation history.
Refresh state surrounds the result but does not change its facts.

## Exact acceptance scenarios

The implementation must encode these as behavior tests before production changes:

1. **Claude exact ask with Spacedock:** a Claude session owns `Approve deploy`, has a non-null
   Spacedock record, and has a pending task. Attention places it first under Needs you now, renders
   `CAPTAIN`, shows the task once as its checkpoint, and session detail agrees.
2. **Codex ask beside a same-label Spacedock sibling:** the exact Codex ask owner has no Spacedock;
   an unrelated sibling does. Attention, Projects, and session detail all render `NEEDS YOU`; none
   borrows captain authority.
3. **AGY gate-blind silence:** AGY is discovered with `reports_needs_input == false`, no error, and
    no ask. Coverage counts AGY as unknown. Healthy fleet counts its idle session as having no
    published exception only when no other signal represents it; the page never says AGY is clear.
4. **Bare gate:** a session publishes `state == needs_input`, `state_detail`, and `blocked_since`
   without an ask. The item says `Input signal observed`, shows the bounded detail/age, and invents
   no question or authority.
5. **Repeated Claude tool failures:** `loop == {errors: 4, tool: "Bash"}` places the exact session
   in At risk and says Bash failed four times. Removing `loop` removes that claim.
6. **Long Codex turn without a source task:** `turn.long === true` creates one At risk item. A
   populated `turn.eta_h` does not create a checkpoint or ETA claim.
7. **Quota pressure with reset:** an `ok` 92-percent window produces one critical At risk item and
   shows its valid `resetAt`. The item makes no exhaustion forecast. A 69-percent fixture produces
   no quota-risk item.
8. **Display-label collision:** two sessions share `beta/app`. Attention says the identities share
   a display label; Projects and Sessions keep both exact routes. No surface says same repository,
   directory, branch, or worktree.
9. **Stopped dirty Codex session:** an idle session with valid `finished_at`, `dirty === true`, and
   `changed == 3` ranks under Close the loop and says `3 changed entries`. It does not say files,
   failed, unread, or unfinished.
10. **Stop without git evidence:** valid `finished_at` and `dirty == null` says git state was not
    measured. Changing null to false changes the bounded line to clean without changing outcome
    language.
11. **No termination evidence:** an idle scan-only AGY row with no `finished_at` produces no
    finished, stopped, or died item. Coverage says termination cause is not reported.
12. **Published Claude task:** a session with an in-progress task appears under Coming next when it
    has no higher signal. A pending task is used only when no in-progress task exists. Task source
    order breaks multiples.
13. **Derived ETA excluded:** top-level `eta_h` and `turn.eta_h` alone produce no Coming next item.
14. **Collector failure:** a discovered Claude harness with `error != null` adds `failed` to
    coverage; zero Claude rows do not lower a needs-you count or imply quiet.
15. **Ask capability disabled:** absence of top-level `ask` prevents the phrase `No exact requests
    published`; it does not manufacture a zero.
16. **Conflicting ask attribution:** an ask resolves to a plain session by `session_id` but names a
    different project. It remains visible and neutral under Needs you now, with the attribution
    conflict as a secondary signal; it is not duplicated under At risk, and neither project owns
    captain authority. Giving that exact session Spacedock changes responsibility to `CAPTAIN`
    without resolving the project mismatch.
17. **No published exceptions:** all four exception/checkpoint sections are absent, the brief shows
    zero counts, Healthy fleet says `no published exception`, and coverage remains visible. The
    strings `all clear` and `safe to leave` are absent.
18. **Empty payload:** zero sessions renders the window-bounded empty state and coverage without
    claiming that no agents exist.
19. **Stale refresh:** the first failure is quiet; the second retains identical item keys/order and
    displays the accepted stale/retry notice. Recovery clears it without moving focus merely
    because the route refreshed.
20. **Responsive and accessible routes:** Attention, Projects, Sessions, project detail, and
    session detail each expose one main and distinct h1/title. Primary links have `aria-current`;
    the 320-pixel layout has no page-level horizontal overflow; DOM order matches the item grammar.
21. **Cross-harness stable ordering:** equal-age Claude, Codex, and AGY fixtures sort by published
    harness order, then project label and full sid. Reordering input sessions without changing
    these keys does not change the result.
22. **Escaping:** hostile text in every item field renders as text, cannot add an element or route,
    and does not alter another subject's rank.

## Implementation seams

The later implementation must preserve the concatenated next-bundle ownership model:

- `next-boot.js` owns the new route tokens, stable identity helpers, payload-clock helpers, and
  exact ask/session resolution shared across views.
- A new `next-attention.js` owns pure signal predicates, subject coalescing, comparator rules,
  coverage shaping, and Attention rendering. It must load after boot and before chrome/render.
- `next-chrome.js` owns primary navigation, route titles, breadcrumbs, guarded shortcuts, visible
  brief counts, and focus restoration hooks.
- `next-projects.js` remains the complete project map and consumes shared signal summaries without
  re-deriving authority.
- `next-sessions.js`, `next-project.js`, and `next-session.js` retain their current ownership and
  exact routes; shared predicates move only when two surfaces would otherwise disagree.
- `next-render.js` dispatches the three top-level routes and keeps refresh state separate from pure
  classification.
- `styles.css` owns the wide grid, narrow stacked grammar, visible focus, reduced motion, and
  no-overflow contract.
- `web/page.py` and `test_next_page.py` add the new part and mechanically regenerated byte pins only
  during implementation.

The first implementation must use existing payload fields. It must not add fleet capability
ratios for stop, git, task, or termination facts until the server publishes explicit metadata.
Such metadata is a separate backend contract change, not a browser inference disguised as coverage.

## Review boundary

Captain review decides whether this source contract and attention hierarchy are correct. No
implementation plan, production edit, test edit, byte-pin change, or browser prototype follows
until the captain approves this written specification.
