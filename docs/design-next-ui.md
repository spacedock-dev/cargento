# Design: the dashboard UI

This document records the interface first released behind `?next=true` and the decisions that
survived its promotion to the default dashboard. The runtime module map remains in
[design-runtime-architecture.md](design-runtime-architecture.md).

It is a record of rationale, including the direction that was rejected, and it is written for
whoever changes this interface next. What the interface promises a user, and what backs each
promise, is owned by [promise-map.md](promise-map.md). Before and after captures live with the
experiment that produced them, in
[the session operations board walkthrough](future-ui-exploration/presentations/future-ui-session-operations-board/README.md),
and they explain a progression rather than a product claim.

The v2 project-level design this interface was built to is kept as the artifact it was
designed in, not as a description of it:
[`Cargento-v2.dc.html`](future-ui-exploration/v2-prototype/Cargento-v2.dc.html) holds the five
views and
[`cargento-observed.js`](future-ui-exploration/v2-prototype/cargento-observed.js) the data shape
they read. Both are design artifacts rather than code, and two of their claims did not survive
contact with the runtime: the end-outcome vocabulary and the delegation floor. Where the
prototype and this document disagree, this document is what shipped.

## Cockpit reconciliation

The project page uses the cockpit's information architecture: a left Scope rail, a persistent
ASSIGNMENT / EXECUTION / COMMAND briefing with latest evidence and direction, and Now / Course /
Decisions / Console tabs beneath it. This preserves the recovery briefing while retaining v2's
rule that every claim needs published evidence. The shared-label caveat stays with project identity.

| Retained v2 surface | Cockpit home |
|---|---|
| Stated goal, source, and goal-gap reason | ASSIGNMENT in the briefing |
| Going on and observed endings, including six outcomes, glyphs and git readings | Now, alongside workflow evidence |
| Observed state changes and unattended count | Course, beside semantic history and completed tasks |
| Delegation, Waiting on you, Capacity, Tripwires | Console |

Where the two designs had the same surface, the v2 renderer survives and the cockpit duplicate
is removed. Its measured delegation and absence rules already had callers and tests; retaining a
second rendering would give the same evidence two interpretations. Decisions shows recorded
decisions and application evidence, not an approval mechanism. The tab opens on that view and
keeps the renderer's own three-button filter, so a reader can widen the same panel to the filtered
activity view or to every event without leaving it.

RC-1 protects [P3's promise of one queue of everything blocked on the reader](promise-map.md#p3-is-anything-waiting-on-me).
Putting all waiting evidence behind the Console tab would weaken that promise: a reader returning
to Now could miss a session that needs them. COMMAND therefore names a waiting project session
above the tabs whenever one exists, with raise and copy-resume controls wherever supported.
Console holds the full queue and its detail. Selecting another tab or focusing a non-waiting
sibling must not hide the project wait. Both surfaces silent while a session waits is a defect;
the cockpit regression test checks the briefing before the tab bar across tabs and scopes.

The original review measured truncated harness names and titles even at 1954px. Keeping that rail
would defeat its purpose as a way to choose a session. The Scope rail now has a 264px column at
1280px and above, with separate readable space for harness names and session titles; below 1280px
it becomes a scope switcher. Missing terminal registration, evidence, history
or delegation renders the reason for the missing reading. Source strings use mono; sentences the
board says use sans at 15px or larger. Evidence and More remain named disclosures.

The terminal bridge, semantic history and model-assisted goal analysis remain prototypes.
Human context and tripwires stay browser-local and deliver no instruction to an agent. Semantic
history has its own server store and is not removed by the session-history `--forget` command.
The optional observer model requires explicit enablement and scoped disclosure consent. Console
reuses the quota disclosure pattern with a separate stored answer and an explicit Summarize this
session action. Granting consent alone sends nothing, and passive refreshes remain local. Its
prompt cap and the local dispatch and terminal trust boundaries belong to
[SECURITY.md](../SECURITY.md#observer-model-calls).

The [import review and captures](probes/project-cockpit/DESIGN_REVIEW.md) predate this reconciliation.
They record the original design, including the truncation and absence states that prompted it.

## NUI-1: promotion leaves one precomputed page

The preview originally used a second shell, stylesheet, script list, and server byte string so its
development could not move the legacy page's byte pins. Once the interface was released and chosen
as the replacement, keeping both implementations stopped buying isolation and started creating two
failure boundaries, two asset inventories, and a permanent routing decision.

Promotion moved the released assets to canonical `web/` and made `load_page()` the only assembler.
The retired `next` query now returns 404 rather than preserving a second dashboard URL. The legacy
HTML, stylesheet, scripts, loader, and tests were deleted together, so there is no fallback that can
silently become the product again.

The promoted script files keep their `next-*` names. Renaming every internal symbol and test would
expand the conflict surface without changing behavior, while the single `APP_PARTS` list and root
asset paths make bundle ownership unambiguous.

## NUI-2: one stylesheet owns the interface

During preview, copying the token block kept the two stylesheets byte-independent. Promotion made
that copy the canonical `web/styles.css` and removed the legacy stylesheet. The v2 refactor drops
light mode and the `prefers-color-scheme` override. One dark root now owns the palette: `--amber`
replaces `--warn`, `--clay` replaces `--alert`, and `--ink` replaces `--accent-ink` and
`--warnink`. Selection still uses `--sel-bg` and `--sel-bd`, and reduced motion disables pulses.

The stylesheet stays one file because splitting it would change the loader, linter and asset
contracts. Nine banner-delimited regions divide ownership instead:

| Banner | Owns |
|---|---|
| `FOUNDATION` | Tokens, reset, type scale, fonts and shared motion rules |
| `CHROME` | Navigation, breadcrumbs, live summary, notices and shared row controls |
| `PROJECTS` | Projects overview, project detail and its main column |
| `RAIL` | The v2 operations panels now composed in Console |
| `SESSIONS` | Session operations and its capacity strip |
| `ATTENTION` | Attention |
| `SESSION` | Session detail |
| `COCKPIT` | Scope rail, briefing, tab bar and cockpit panels |
| `SUBSTRATE` | Semantic timeline and terminal substrate in `project.js` |

Assign one owner to each region during parallel work. Keep media queries at the end of their own
region; a shared responsive block would make every view edit the same tail. Moving a rule between
regions is an ownership change, not incidental cleanup.

Board sentences have a 15px floor (`--fs-sentence`), at weight 500 and line-height 1.55. Labels
identifiers, timestamps, rates and compact controls sit on one tier, `--fs-label` at 11px. Four
`:root` steps used to sit below 11px, at 9px, 9.5px, 10px and 10.5px, a 3px band nobody can rank,
and 9px was the smallest step in the file. **Counts here read "at or below 12px" inclusively**, so
the band held seven tokens: `--fs-column` 9px, `--fs-label` 9.5px, `--fs-meta` 10px,
`--fs-meta-detail` 10.5px, `--fs-machine` 11px, `--fs-2xs` 11.5px and `--fs-breadcrumb` 12px. Three
of the seven had no callers anywhere and were deleted: `--fs-column`, `--fs-meta` and
`--fs-breadcrumb`. `--fs-meta-detail` had four callers and was folded into `--fs-label`; `--fs-2xs`
has forty-one and stays. The issue said six because it omitted `--fs-2xs`.

The floor left 12.5px on the strength of an APCA reading that put `--ink`, the brightest colour in
the palette, below the body-text requirement there. **Those figures are audit-only: no APCA
implementation, table or fixture exists in this repository, so they cannot be reproduced from the
tree**, which is the same caveat the milestone carries. What the tree does say is that this was
never a contrast defect: `--ink` on `--bg` recomputes to 16.36:1 and the asset test asserting more
than 4.5:1 is green. No issue here adds an APCA implementation, so the audit
figures stay audit-only. DRC-4596 guards the **px floors** the audit motivated, which is a
different and weaker property than reproducing it. The absence explanations the prototype placed at 10px are sentences, so
they take the sentence tier, and two of them had to leave an `<h2>`'s `<header>` to get there.
**Raising an absence is not safe on its own.** An absence and the value it replaces are chosen by a
ternary, so they never co-exist in one render: no sweep of co-existing selectors sees the pair, and
neither does reading a populated board, because only one branch is ever on screen. Raise the
absence without its value and the gap reads larger than the fact it stands in for. So only two
absences are on the sentence tier here, the two named above, and each is safe for a reason that
does not depend on finding every pair: "two axes, read separately" is drawn beside values already
on that tier, and "No revision saved yet" shares one class with the revision line it alternates
with, so both branches resolve identically whatever the tier is.
`AnAbsenceNeverOutranksTheValueItReplacesTest` asserts exactly those two and nothing wider.
**Every other absence keeps the size it had**, and DRC-4602 owns the audit that can raise them
safely, because doing so needs a census of the emitters that this stylesheet cannot supply. The
stylesheet
retains scale tokens and literal sizes. The asset test pins the dark palette and checks text inks
above 4.5:1 on the ground, panel and inset surfaces. Since DRC-4596 it also enforces size, and the
census below is its output rather than a hand count: every `--fs-*` token resolves at or above 11px
with `--fs-sentence` pinned to 15px, the px literals below the label floor are an exact registry, and
every rule passing the membership test resolves at or above a literal 15.0 except an exact recorded
inventory. **What it still cannot see is a sentence composed across several rules.** Where one rule
sets the size, a second the family and a third the line-height, no single-rule census can join them,
and the two that render that way today are named at the end of this section. It does not enforce
spacing between contrast steps.

What counts as a sentence is a test, not a judgement call, so a reviewer argues with a list:
**an element is on the sentence tier when its resolved style is sans with a prose line-height.**
Resolved, not declared. Both properties come through the cascade, either may be inherited from an
ancestor, and the two may arrive from different rules, so the element is the unit and a single rule
is not. Mono is a string a source published, and a label resolves to no prose line-height at all.

That distinction is the whole difficulty. **A census that reads one rule at a time will understate
the set**, because it cannot see an element whose family, size and line-height are assembled from
three rules, and it will report clean while such an element still renders below the floor on
screen. Two of those are named below; how many exist, and what to do about them, is DRC-4602's.

Sixty-five rules on the old `--fs-xs` step qualified when the tier was drawn, plus the two absence
explanations above; **seventy rules resolve to `var(--fs-sentence)` today**, the three added since
being DRC-4590's control primitive and the two DRC-4595 raised with the steer caveat. Forty-seven of
them also cap at `--measure` (540px, about 72 characters at this tier). The twenty-three that do not
are the ones a cap would clamp wrongly: eight carry `overflow-wrap:anywhere`, thirteen are layout
boxes, fields or grid children rather than single lines, and `.next-cockpit-content` and
`.next-cockpit-recovery>div` are the prose containers, where 540px would clamp the cards inside them
instead of the sentences. These counts are asserted by `NextPageAssetContractTest`, so they move with
the sheet rather than with whoever last read it.

One member of the sixty-seven was exchanged for another on 2026-09-17, and all three counts above
are unchanged because of that exchange rather than in spite of it: `.next-cockpit-authority>span`
left the tier and `.next-cockpit-authority>small` joined it, both of them capped. The span prints
`FO INSPECTING` and `FO CONTINUES`, which are state names a source published, so the rule above
always excluded it. The sweep that raised the tier admitted it anyway, and full ink on top of
15px made the loudest string on the page the one piece of vocabulary the page never defines. It is
now a mono chip at `--fs-label`, glossed once beside the briefing heading. The `<small>` that took
its place is the line saying whether the captain is needed: prose the board wrote, and the string
a reader opening a project is actually looking for.

**The floor is not yet universal, and this is the gap DRC-4602 sizes.** Nineteen further sans
rules pass the same test at 13px to 14.5px: seven on `--fs-sm`, three on `--fs-body`, two on
`--fs-summary`, and seven literals (one 14.5px, three 13.5px, one 14px, two 13px). DRC-4596 records
them as an exact inventory, so a rule leaving the sentence tier for a lower one reds the same way a
new sub-floor rule does. Beyond them sit **two that no single-rule census can see**, because their
size, family and line-height are composed across three rules each. Those two are
`.next-operation-fact--unknown strong`, which takes 12.5px and mono from one rule, a flip back to
sans from a second and its line-height from a third, and `.next-cockpit-recovery small`, which takes
12.5px from its own rule and inherits sans and the line-height from the cell. **No offline guard in
this repository sees either**, and DRC-4596's must not be read as establishing a universal floor;
only a computed style reaches them.

They were left alone: raising them is another nineteen rules of review surface, and some of the
nineteen are not sentences at all (a textarea and two prototype rules), so the set needs reading
one selector at a time rather than a sweep.

**Element counts carry the date and the commit they were taken at, or they do not belong here.**
The board renders whatever sessions exist, so one shape counted 163 elements and then 183 forty
minutes later, at `3cc7ef49` and `4fb5ee6d` on 2026-09-17, both reported by the reviewer rather
than measured here. The stylesheet was not identical across that pair, `4fb5ee6d` changed it by
thirteen lines, but none of those lines matches `operation-fact`, so the rules resolving the shape
that was counted were the same for both readings. The narrower claim is the true one. A bare number reads as a
property of the code when it is a property of an afternoon. The stable unit is the rule, or the
element shape, never its population.

Twenty-four declarations carry `.09em`: the whole `.13em` and `.14em` groups, plus eight of the
eleven in the `.1em` and `.08em` groups. The other three of those eleven keep their own value
because their content is not uppercase. `.next-cockpit-work-type` prints a fact type such as
`gate_decision`, `.next-intent-key` a session key, and `.next-cockpit-scope strong` a scope name.

**The uppercase label tier is not uniform, and this change did not make it so.** Six further rules
print capitals on some other value: `.next-capacity-head span` (`WINDOW`, `USED`),
`.next-capacity-models small` (`WITHIN THIS WEEKLY BUDGET`) and `.next-capacity-row small` (`USED`,
`PACE`, `BUDGET ENDS`, `RESETS`) at `.06em`; the course and direction header badges
(`EXACT DIRECTION`, `EXACT DECISION`) and `.next-scope-cue` (`PROJECT`, `SESSION`, `SCOPE UNKNOWN`)
at `.07em`; and the recovery memo field labels (`OUTCOME`, `FOCUS`) at `.04em`. They survived
because the issue inventoried four tracking values and the stylesheet had seven, so sweeping the
four named groups never reached the other six declarations. Count the values in the tree, not in
the issue.

Four ink registers sit in the one `:root` block and name what an ink is for rather than which ink
it is: `--ink-label`, `--ink-value`, `--ink-absence` and `--ink-caption`. They exist because a
label and its own answer were drawn in the same colour, and because twenty-one cockpit and session
label rules each spelled `var(--ink3)` in their own declaration block, so moving the label tier
meant editing twenty-one rules by hand and hoping none of them was a value.

The palette has three inks and the roles need four, so `--ink-label` and `--ink-absence` both
resolve to `--ink3`. That is a ruling, not an accident. `--ink3` on panel is 5.67:1, just above the
floor the asset test asserts, so labels cannot go dimmer, and brightening them makes them compete
with values. Labels can afford the double-up because they also carry uppercase, tracking and mono,
while an absence is a sans sentence, so family and case already separate the two. Brightening an
absence was refused on a different ground: the failure this board is built against is the confident
wrong answer, so a missing fact must not read as loudly as a present one.

An absence therefore separates from its value on shape, never on tone. A figure slot keeps its own
ink and gains a family swap plus a leading em dash from `[data-next-absent]::before`, stamped at
emission because no selector can tell a null from a real `0`. The three kinds of absence a reading
paragraph can state carry `data-absence="not-observed|waiting-on-you|run-config"` and are told
apart by a left rule: dim and solid, bright and solid, dotted. All three survive greyscale, which
colour alone would not.

The pair to watch when editing any of this is a value and the absence that replaces it. They are
chosen by a ternary, so they never co-exist in one render and no single rule holds both sides; a
selector sweep and a live board both miss it. Resolve both branches through the cascade and compare
them, which is what `AnAbsenceNeverOutranksTheValueItReplacesTest` and
`AnAbsentVariantBorrowsItsSizeFromTheValueItReplacesTest` do.

Space Grotesk and Space Mono subsets travel inside the assembled page as data URLs. A missing or
malformed font is a canonical asset failure and prevents startup before the socket binds. There is
no font route or browser request to a provider. Licenses and source hashes live under `web/fonts/`.

## NUI-3: the released route and storage namespace remain stable

The fragment grammar is `#n=sessions`, `#n=projects`, `#n=attention`,
`#n=project:<encoded-project>`, or a session route carrying encoded project, harness, and complete
session id. The bare URL, invalid fragments and retired fragments normalize to Projects. Hash
changes are both navigation output and browser-history input, so reload, pasted links, and back or
forward preserve the view.

Browser state keeps its `cargento.next.*` namespace. That prefix is no longer a firewall between
two live bundles; it is compatibility with storage written during the preview and protection from
stale `cargento.leader` records written by the removed dashboard. The current leader uses
`cargento.next.leader` and `cargento.next.revision` so a stale old lease cannot demote it.

**Retiring a tab slug is a route change, not a layout change.** `nextRouteFromFragment` in
`next-boot.js` has no alias table, so a three-part fragment whose last part is no longer in
`nextCockpitTabs(null)` is not redirected: it falls through to the focus arm and is parsed as a
session focus id, landing the reader on a session filter that matches nothing. A proposal that
merges or drops a tab therefore owes an alias for the retired slug and an amendment to this
section, and cannot be priced as a change to the strip alone.

## NUI-4: the canonical bundle fails before bind

`cli.main` assembles one required page before creating a daemon log, binding, forking, or spawning a
Windows child. Failure in the shell, stylesheet, any script part, or any embedded font is fatal and
reported as a frontend asset error. Each server instance owns its already assembled page bytes.

The optional terminal adds two local asset routes, `/assets/xterm.js` and `/assets/xterm.css`.
They read the vendored files only for loopback peers under the normal origin checks, and return
404 unless interaction is enabled. Inlining the terminal library was rejected because it would
roughly double the page for a feature disabled by default. A CDN fetch was rejected because
dashboard assets must not require an external request. The vendored bytes are pinned by size and
digest, with license and provenance beside them; no browser SRI or cross-origin attribute remains.

The runtime inventory and copied-plugin tests enumerate the root assets explicitly. They prove an
installed copy is complete rather than relying on recursive copying to conceal an omitted file.

## NUI-5: chrome and navigation reflect the current payload

The header counts running sessions and all observed subagents from the shared derivation,
including quiet subagents. Running requires working state, no observed end, and the published
`active` flag. A reported-block button appears while a session is waiting on the reader in that
model. Projects, Sessions, Attention and Intent log all have primary navigation links; the fourth arrived with the annotation work, which needed a surface whose rows outlive the board. Shortcuts `p`, `s`, and
`a` are case-insensitive and do not run while a form control or editable content owns focus or
Meta, Control, or Alt is held. `Escape` follows the same restrictions and returns from session
detail to its project, and from any other view to Projects. In a tripwire draft it cancels the
draft first. The preview's `dashboard mode` button and `d` shortcut were removed during promotion
because `/` now serves this same interface.

Projects groups the current payload by display label and splits active evidence from recently
observed groups. Sessions separates Active now from Recent history. The active group retains gate
priority and the working attention ladder, while history remains reachable without presenting its
last observed state as a current operation. Every row carries the exact route needed by project or
session detail.

Two consecutive fetch failures show a stalled notice beside the last good payload. A manual retry
uses the same serialized refresh path. The page forwards `all=1` to `/api/data` and adds `usage=1`
only while quota-fetch consent is granted; `next=true` never changes collection. Every
client-derived age uses the payload's generated time rather than the browser clock.

## NUI-6: a project keeps its workflows separate

A project is a display-label fold over sessions, while a Spacedock plan is a workflow strip on one
of those sessions. The project page does not flatten those two levels. It creates one PLAN block per
distinct workflow name, in the order the names first appear in the payload. Folding two names into
one sequence would invent an order neither workflow declared. Keeping only the first strip would
silently hide work.

The detail header repeats the shared-label caveat from the overview. Navigation does not turn a
display label into proof that its sessions came from the same directory.

Repeated strips with the same workflow name do merge. The first strip establishes stage order, and
stages found only on later strips append in their first-seen order. An entity slug appears once. A
live copy replaces a non-live copy; equal-liveness copies keep the first occurrence. Rows then sort
by the merged stage order. This makes concurrent first-officer observations stable without
duplicating an entity or treating two different workflows as one plan.

Ownership stays narrower than grouping. A live entity's source session proves its harness, so that
row may show the harness and derive `blocked on you` from the source session. A non-live roster row
does not prove which session owns it and leaves the owner blank. `stalled <duration>` starts after
600 seconds against the payload's `generated` clock and uses the NUI-5 duration grammar. That floor
is one complete token-rate evidence window. The 90-second collector threshold answers a different
question: whether recent store activity is enough to call a session working.

The project plan section folds those same per-entity states into an `N entities unhealthy` count.
It renders the count only when at least one named plan exists. A plan with no published entities
reports a measured zero; no plan omits the count. Stages do not become steps, and the section
makes no step-health claim.

The payload does not distinguish an initial entity from a completed one, and it carries no pull
request state. PLAN therefore has no completion glyph, completion count, merge state or review
state. No Spacedock declaration omits the wrapper. A first officer whose workflow has no fresh
entities and an ensign whose plan lives with its first officer keep distinct empty messages. The
cockpit keeps plans in Now alongside current activity and observed endings. Completed tasks and
state changes live in Course. The stated goal stays in the briefing, and Console holds waiting
requests, delegation, capacity and browser-local controls.

## NUI-7: project activity is a current-payload answer

GOING ON reads the project's derived sessions in payload order. It includes event-backed working
sessions, sessions waiting for input and sessions with an exact request. Their cards share the
payload clock and measured wait or token-rate phrases with the sessions overview, then route with
the project label, harness and full session ID. A working state without the freshness flag still
counts as working elsewhere; it does not enter this block as observed running work.

Each activity card also names its published subagents. The compact list puts live subagents first
and keeps payload order within the live and quiet groups. It shows at most six rows, followed by
`+N more` when the payload carries more. An elapsed age appears only when `started_at` is
measurable against the payload's `generated` clock; missing or invalid stamps leave the name in
place without inventing an age. The age uses the NUI-5 duration grammar. Malformed subagent
collections produce no list, and malformed entries keep the neutral `subagent` fallback used by
session detail.

The rate phrase preserves the payload's distinction between absence and zero. A session from a
rate-blind harness carries `rate_per_min: null`; a reporting harness that measured no output in
the window carries `0`. The card shows a rate only when the harness reports it, its collector has
no error, and that session has no token-accounting gap. Otherwise it says `Token rate not
reported`, keeping an unmeasured session distinct from a measured `0 /m`.

Working membership starts with `state`, excludes observed ends, and uses `active` as a freshness
gate on top. An exact request independently keeps its card reachable. `state` and `active` were
conflated once, and the block filtered on `active` alone. Every session still inside the display
window qualified, so a repository running one live Codex session rendered eleven cards, ten of
them idle and captioned "awaiting your message", under a header that read `1 running`. The header
and the sessions overview were both right, because both read `state`. A payload has one answer to
what is going on, and a block that derives its own from a different field will eventually
contradict the rest of the page.

COMPLETED TASKS is deliberately narrower. It walks each project session and whatever task list
that session published, in payload order, selecting only tasks whose published status is
`completed`. It does not sort by task times or deduplicate subjects. Task identity is local to a
session, and the same subject can represent two real pieces of work. Spacedock entities are not a
completion source: terminal entities do not reach this payload, and the remaining plan rows carry
no completed marker.

The activity blocks render explicit empty sentences. COMPLETED TASKS names the payload because it
is a view of the latest snapshot, not a retained task history or a claim that a project has never
completed work. HOW THINGS ENDED is separate and contains only observed session ends. A stop on an
idle session remains visible in Sessions and Attention without becoming a session end.

The outcome vocabulary has six readings, composed from two observed events and three git states:

| Event | Dirty | Clean | Unknown |
|---|---|---|---|
| Stop | `Stop observed with uncommitted work` | `Stop observed; git state clean` | `Stop observed; git state not measured` |
| End | `Session ended with uncommitted work` | `Session ended; git state clean` | `Session ended; git state not measured` |

A positive finite `ended_at` supports an end. Idle state with a positive `finished_at` supports a
stop. An end takes precedence if both exist. A boolean `dirty` chooses dirty or clean; absent git
measurement stays unknown. No stop or end yields `No stop or end observed`. These readings
establish neither readership, unpushed commits nor termination cause; a clean tree is not proof
that the work succeeded.

## NUI-8: session detail stays inside the current payload

A session route carries the project display label, harness and full session ID. The detail lookup
requires all three. Older routes without a harness resolve only when there is exactly one match. A
stale route, including the right ID under the wrong project label, gets an explicit
outside-payload state instead of a guessed row. The flat session table now emits the same route as
the project activity cards, so it no longer stops at project detail.

The header uses the published `title`, or `Title not published`. A last prompt may appear under
its own label; it never becomes a fallback title. The row's `instruction` supplies attributed
current context on session detail, the operations table and each GOING ON card. This answers a
different question from the title, which on a long Claude session can still name work that
finished hours ago. One renderer serves all three, so the rule for when a line may be shown has a
single definition. The line renders only with its source label and measured age, and is dropped
when the payload publishes none or its label is not one the runtime issues. Where a caller supplies
the displayed title, the helper also suppresses equal text and a continuation of a title clipped
with an ellipsis: one prompt reaching two lines at their two clip widths. Not the reverse: a short
title that merely opens a longer, genuinely newer instruction is the case the line exists for, so
a plain prefix test would delete exactly what was added. Over 2,931 rows of one local store the
equality branch suppresses 13 lines and the clipped-title branch 30, while the reverse rule fires
on none of them.

Each surface clips the line to what it can carry. The detail header and the table row wrap it; a
GOING ON card holds it to one line, because that block is scanned rather than read and a card that
grows whenever the newest prompt is long pushes the next card off the fold. The label and the age
are never in the part that clips. The card renders the line as a span rather than a paragraph,
since the card is a button and takes phrasing content only.

The age sits outside the label span. `.next-instruction-label` uppercases, which turned "asked,
4m:" into "ASKED, 4M:". A duration whose unit is a capital letter reads as an initialism, and the
whole prefix reads as one label rather than as a label and a measurement. The former session table
labelled its title only when a second instruction line appeared, to keep that line from reading as
an unlabelled caption. The v2 table names the published title in SESSION and keeps the
instruction's own source label.

The project goal uses the newest session, by last activity, that publishes an `asked` instruction
or a Spacedock workflow goal. It labels that source and counts sessions with neither. Goals remain
source statements, without normalization across sessions. An `asked` instruction wins over a
workflow goal on the same session. The overview now shows each member's published title, current
activity and pending step instead of selecting one last-instruction cell.

The earlier cell preferred `asked` over raw `last_prompt` for a measured reason: over 2,931 rows,
114 carried an `asked` line, 15 differed from `last_prompt`, and 2 had no `last_prompt` at all.
Using an `agent` or `earlier` instruction without its label would turn quoted or older context
into a claim about the newest request. That distinction still governs the goal's source label.

The header keeps the registry label, full session ID and measured activity metadata. A working row
labels its measured `turn.elapsed_h` as the current start age; an absent, empty, or malformed turn
measurement removes that clause instead of falling back to the transcript's creation time. A
needs-input row derives its blocked age against the payload's `generated` clock. An idle row may
use the same clock for an explicitly named session-start age. Those two client-derived ages use
the NUI-5 duration grammar; the working turn keeps the server's published string. Missing
timestamps remove those clauses. They never become zero.

The detail rail follows the derived observation tone: accent for a supported good reading, amber
for attention, clay for uncommitted work at an observed stop or end, and neutral for unknown.
Visually hidden text still names a recognized published state. A state alone cannot imply a clean
outcome, and an observed end with unknown git state does not inherit the working color. The needs-input article edge
remains a separate treatment.

The detail health callout is bounded to two measurements already present on the row:
`turn.long` and the failed-tool-loop peak in `loop`. A long turn keeps the `LONG TURN` label;
when both measurements exist, the loop sentence replaces the generic long-turn explanation rather
than producing a second notice. A loop without a long turn uses `FAILED TOOL LOOP`, and remains
visible after the session stops because the server retains that peak until the next prompt. A
missing or malformed positive integer count removes the loop notice. Neither path infers a stalled
or failed outcome. The canonical bundle keeps the MCP tool-name formatter near the detail renderer
that uses it.

Questions render only when the payload advertises the ask capability. Matching uses exact
ownership by full session ID and harness when present; a harness-free request needs one
unambiguous owner. It keeps payload order and shows every match. The callout uses the same
`<harness> is asking you` sentence as native notifications. Each option posts its numeric index to
the existing `/api/answer` endpoint. Only `answered: true` confirms the action; otherwise the
question stays put with a failure note keyed to its ask ID. There is no optimistic removal.

Task provenance is whichever collectors fill the list, not a harness allowlist. Two do today,
`collectors/claude.py` and `collectors/codex.py`, and both readers gate on the published field
rather than on the harness name so a third needs no edit here. The gate was once written against
the harness name, while Claude was the only collector filling the field, and that spelling hid a
Codex plan the moment one arrived; the comments in `next-session.js` and `next-activity.js` record
the change. The count is derived from the rows being rendered, and their payload order is
unchanged. Session-detail subagents keep payload order. Only live subagents pulse, unless reduced
motion disables animation, and elapsed time appears only when `started_at` was measured, using the
NUI-5 duration grammar; model names are outside this view. For sessions whose published state is
working, the footer prefers measured turn output tokens. For waiting and idle sessions, it prefers
the measured session total. Either state falls back to the other measured source and labels the
visible number `this turn` or `this session` from the source it actually chose. An absent reading
stays absent and a real zero stays visible, so a lifetime total cannot read as if it described the
current request.

A new session endpoint would duplicate the current payload and expand the HTTP surface without
supplying new evidence. The `next-session.js` part renders from the canonical payload and adds no
retained history; that decision remains DRC-4234.

## NUI-9: the workstream starts from the store, then from this tab

`next-workstream.js` builds a bounded ledger from the local history the server publishes plus every
advancing payload this tab sees. On the first payload it replays `history`, the record of state
changes DRC-4234 authorised the server to keep. Each stored record becomes a batch holding every
session known at that stamp, so a replayed window and a polled one are the same shape: an
observation holds until the next one arrives. A session's first stored record is the baseline a
later change is measured against and is not listed as a change itself, and its last stored record
closes its span rather than opening one: the store records what changed, never when the server
stopped, so nothing observed the end of a final `working` record and holding it to the first payload
counted a closed laptop as time an agent worked. With the store off, or on a
machine that has never run with it, the first payload establishes the session and ask baseline and
nothing older exists. Later payloads add state transitions, newly measured turn stops and newly
observed asks in timestamp order. Replayed payloads add nothing.

Every advancing payload also contributes one sample per session with its project, state and
measured token rate. These samples are the evidence the later delegation panel needs; transitions
alone cannot recover the intervals between them. State events keep both sides of the transition for
the same reason. Once a project first appears, its window keeps every later payload boundary. A
boundary with no rows for that project records its absence without inventing an idle session.

One classifier owns the attended or agent-side meaning of each state transition. A transition out
of `needs_input`, or from `idle` to `working`, is an attended boundary. Its workstream node is hollow
and it does not enter the unattended count. Delegation uses those boundaries as human-turn
candidates, then applies the same-answer rule in NUI-11. A transition into `needs_input` is also
hollow because it opens a gate, but it is agent-side. Other transitions, including `working` to
`idle`, use filled nodes and count as unattended.

The 100,000-logical-entry cap was chosen against the observed 22-session case at the five-second
poll cadence: six hours produces 95,040 samples before transition entries. An advancing payload
with no samples or events costs one logical entry, so empty boundaries cannot grow outside the cap.
Whole payload groups are dropped oldest-first. Only a single payload larger than the entire cap is
tail-bounded, a defensive path far outside the measured population.

The section names the retained span rather than copying the mock's fixed six-hour label. Before a
span exists it says `since this tab opened`; elapsed labels come from payload `generated` times, not
the viewer clock. The span reads in days once it passes one, because the shipped retention is
fourteen of them and `last 336h` is not a figure anyone reads as two weeks. Its header always keeps
the `N of M unattended` ratio; expansion appends the retained span instead of replacing that ratio.
The timeline is empty until an event arrives and says which window it found none in, rather than
asserting the tab's lifetime. Reloading discards the in-tab ledger and rebuilds it from the store.
Only the collapsed preference survives in the browser, under the next bundle's storage namespace and
behind a storage failure boundary.

Rendering consumes the ledger through a project-window function rather than reading its mutable
arrays. That is what let the server history source arrive without changing the timeline: the seeding
pass appends groups through the same path a payload takes, and the renderer never learned it had
happened.

## NUI-10: project controls demonstrate local state, not delivery

The board carries STEER and TRIPWIRES because the dashboard needs the interaction shape,
but neither is a session-control surface. The add control reads `+ set a tripwire`. Submitting a steer keeps a bounded draft record in that tab,
retaining the newest 20 drafts and rendering every retained draft from oldest to newest. Each
escaped receipt says both that it was not delivered and that Cargento has no session write path. It
makes no request. A disabled field was rejected because it could not demonstrate the interaction,
while an enabled field with no receipt would look like a successful send.

The steer composer is built once, in the project chrome above the tab strip, rather than inside
TRIPWIRES. DRC-4595 moved it: as the last child of a section captioned "local only · nothing
enforces these" it was 86% of the way down the Console panel, subordinate to a section it has
nothing to do with, and absent from the other four tabs. The chrome is where a project-scoped draft
belongs, and a single call site is what makes "renders once" provable: a second builder stood in
`next-controls.js` with no caller and was deleted for that reason.

**The correction no longer waits for the press.** It used to be built from the stored drafts, so
before the first keystroke the control promised delivery and said nothing about what it does.
A caveat now sits above the field in every render: one sentence on the sentence tier saying there is
no write path and that anything typed is a note to yourself. Raising it alone would have drawn the
warning larger than the words it warns about, so the field was raised with it and the pair is
asserted as a pair. The `send ⏎` submit keeps its wording under this ruling, which retains the
control specifically to demonstrate the interaction shape; renaming it is filed separately.

Tripwire rules are viewer preferences. They are stored under a project-label key in the next
bundle's localStorage namespace, capped at 50 rules of 500 characters, and kept in memory if storage
throws. The project label is enough for a local browser preference. It is not stable enough for a
server store that changes what agents do. Stored values are untrusted input, so both loaded and new
rules pass through the shared escaping function every time they render. The panel header and standing note
say that no observer is enforcing them.

Two existing boundaries rule out wiring up either control. DEC-2 does not permit unsolicited free
text into a running session. The ask lane only returns a numeric option index for a question the
agent initiated; its A-2 rule exists specifically so the loopback endpoint cannot introduce text
into agent context. Reusing that endpoint for steer text would remove the protection that made its
loopback exposure acceptable. A disk-backed guardrail store also waits on a stable project key and
an autonomous-observer decision.

`next-controls.js` therefore owns rendering and browser events only. It adds no HTTP route, POST,
MCP operation, persisted runtime state or model call, so the audited mutating-route inventory and
the direction invariant do not change.

<a id="nui-11"></a>

## NUI-11: delegation is wall time inside the observed evidence

Console's delegation figure integrates adjacent sample batches from the workstream ledger,
whether they came from this tab's own polls or from the store NUI-9 seeds it with. A batch owns the wall-clock interval until the next advancing payload, clipped to the
displayed window. That makes an irregular refresh cost the time it actually spans instead of one
vote in a poll-count average. A non-empty interval with at least one working session and no gate
adds to the numerator, denominator and observed coverage. Any `needs_input` session makes the
interval denominator-only while still advancing coverage. An all-idle interval advances coverage
but enters neither side of the ratio because no agent ran.

A zero-row project batch is different from idle. It proves only that the global payload advanced,
so its interval adds no numerator, denominator or observed coverage. A later reappearance cannot
recover the missing state or create a human turn. The evidence floor and the two-window trend both
stay withheld across that unknown gap.

The known cases still choose a deliberate bias. If a gate stays open over lunch, the whole observed
gap counts as human time, so the percentage is biased **down**, not silently corrected upward. The
project could not proceed without an answer during that gap; subtracting part of it would invent
availability. A gate that opens or closes between two polls still has up to one poll interval of
uncertainty in either direction. Transitions that both happen between polls are not recoverable from
snapshots.

Ten minutes is the minimum observed evidence window because each published `rate_per_min` is
itself a trailing ten-minute mean. An all-idle window still has no denominator and remains
withheld. Below that floor the block says `no figure yet` and prints no percentage, bar, token
rate or human-turn count. The headline grows with the retained span up to six hours, the window
the ledger cap was sized to preserve at the measured 22-session population. That ceiling is the
tab's, not the store's: a seeded window is measured whole, because retention there is the reader's
own setting and clamping a fourteen-day store to six hours would report six hours under a caption
naming two weeks. A trend needs two independent full observed windows: it compares the latest six
hours with the six before them only when twelve retained hours exist. At the measured population the
cap may prevent that condition, in which case no trend is more honest than a flat arrow.

For each delegated interval, the session rates in that payload are summed and those per-payload
aggregates are time-weighted over the delegated wall time that was measured. The denominator is that
measured span rather than every delegated second, because the store keeps no token rate at all: a
seeded fortnight beside one measured hour would otherwise spread that hour's area across the whole
window and print a floor two orders of magnitude under the rate it came from. A session whose
harness cannot measure rate makes the result a `≥` floor; if nothing in the delegated intervals has
a measured rate, or no delegated interval exists, the token figure is absent rather than zero. Human-turn candidates are
transitions out of `needs_input` and `idle` to `working` prompt boundaries. Delegation coalesces an
immediate same-session `needs_input` to `idle` transition followed by `idle` to `working` into one
inferred answer. A direct gate-to-working transition still counts once, and a later prompt boundary
after another same-session state transition counts separately. Other sessions do not clear or
consume the pending resumption.

The payload has no response identifier, so the pairing uses harness and session ID without an
invented time threshold. Events before the displayed window still establish pending state, but only
events inside the window increment its count. Gate openings, ask registrations and turn stops remain
agent-side events and do not increment it.

The number survives a reload and a restart as far back as the store reaches, and no further. What
the store holds is state changes, not token rates, so a window that predates this tab reports its
percentage and human turns while withholding or flooring the rate. DRC-4234 authorised the store;
its bounds and its off switch are in `SECURITY.md`.

## NUI-12: motion means observed activity, not mere attention

Live treatments make two different claims. The header always marks its running and subagent
summary as live, including when both counts are zero, because the cue is about the current payload
rather than an individual session. Live subagents in session detail, working sessions in GOING ON
and the project overview, and active working rows in Sessions use motion only for observed
activity. A listed subagent may be quiet; `nextSubagentIsLive` decides which ones pulse. Working
rows also require `active` and no observed session end. No browser timer infers that work is
alive.

A gate stays amber and static even when its session still has `active: true`. It is important, but
it is waiting rather than moving, and animation must not turn attention priority into a claim of
progress. A working row whose `active` flag has lapsed likewise keeps its place in the working
group without the live dot.

The pulse changes only opacity. Under `prefers-reduced-motion: reduce`, animation is disabled
while the static dot and `next-live` class remain, so liveness does not depend on motion. All of
these selectors and keyframes live in the canonical `web/styles.css`.

## NUI-13: one transport keeps the released namespace

Tabs elect one leader through `cargento.next.leader`, fan revisions out through storage, and retain
`cargento.next.revision`. Those names survive promotion so stored preview state remains compatible
and a stale `cargento.leader` lease from the removed dashboard cannot affect the canonical page.
There is now one bundle and therefore one leader population.

A permanently closed stream yields and retries on the next two-second election tick. A 20-second
poll runs beside SSE as a safety net; a browser without `EventSource` uses the five-second poll as
its whole transport. Both call the same serialized refresh function, so failures drive the same
stalled notice. The server stream budget and revision rules do not change.

## NUI-14: the specified fonts travel inside the page

The design names Space Grotesk at weights 400 through 700 and Space Mono at weights 400 and 700.
The canonical bundle ships upstream Latin, Latin Extended, and Vietnamese WOFF2 subsets. `page.py`
validates each packaged payload and embeds it as a data URL while assembling the one-page response.

There is no font route, provider request, or optional font failure boundary. Missing or malformed
font data prevents the canonical page from loading before bind. Each family keeps its upstream SIL
Open Font License beside the assets, and `web/fonts/SOURCES.txt` records source URLs, decoded sizes,
and hashes.

## NUI-15: command facts keep their source and their scope

The first command-surface prototype gave every project a workflow-absence panel, gave every
session four equally weighted command cells, and showed a top-level captain line even when no exact
request existed. Those regions were structurally consistent and operationally misleading. An
empty panel looked like a fault, a missing fact looked like a negative fact, and `CAPTAIN` implied
Spacedock authority on sessions that had published none.

The corrected surface renders a command claim only when its owner publishes the supporting fact.
An `asked` instruction is an assignment. An `agent` or `earlier` instruction is current execution
context, not an assignment. The first in-progress source task may explain NOW, and the first pending
source task may supply NEXT. An exact ask supplies a response fact. `CAPTAIN` requires both that ask
and an object-valued Spacedock record on the exact owning session; otherwise the request says
`NEEDS YOU`. A needs-input state without an exact ask can report the bounded block state, but it
cannot invent a question or authority.

These rules operate on exact identity. Ask ownership resolves by full session ID and, when the ask
publishes it, harness. An ask without a harness resolves only when its session ID has one payload
match. Display label never owns the ask. A project display label is useful for grouping but is not
a repository, directory, branch, worktree, or authority boundary. A same-label collision keeps its
warning and exact member routes rather than choosing one session as the owner.

Absent optional facts leave no primary placeholder. A project with no Spacedock record omits the
workflow wrapper instead of saying that a workflow source is unavailable. Session detail omits an
assignment when none was published. Its fixed fact grid states absent measurements explicitly;
missing next-action provenance also stays in a closed source coverage disclosure when there is no
exact request. The fixed operational columns may state their bounded absence, such as no pending
source task, because the column itself answers a stable question. They do not translate that
absence into intent, completion, or an all-clear.

Current activity leads session detail. Its known state, source-backed activity, and running
subagents occupy one region because they answer the same question: what is happening now. Session
title and harness metadata remain identity beneath that lede. Assignment and exact request follow
only when published; the fixed NEXT STEP fact states why a step is absent. Health, answer
controls, tasks, and token evidence remain below the command facts. This hierarchy prevents a
session title from competing with its current work or making attached subagents look like
unrelated sessions.

<a id="nui-16"></a>

## NUI-16: operations lead; observation stays reachable

The exception-first Attention route was implemented and tested before the operations board. Its
taxonomy was source-bound, disclosed coverage, and ranked exact requests, risks, observed stops,
and published tasks. In live review, that direction still buried the operator's first questions.
A reader had to decode queue categories and coverage before finding where sessions were, what each
was doing now, what came next, and whether it was blocked. The compressed remainder also made
recently observed sessions look too much like current operations. More ranking did not solve the
information hierarchy.

Session operations initially became the default route. The v2 design moves the entry point up to
Projects, so the reader first finds the project and then its sessions. Sessions remains the fleet
operations view, with four bounded counts: active now, working, exact requests, and reported
blocks. `Active now` means working or needs-input state without an observed end, or an exact
request. It is not the number of rows in the payload. That distinction prevents a 24-hour
observation window from reading as a list of open harness processes.

The body makes the time boundary visible. Active now contains only exact sessions with active
evidence and gives each one stable WHERE, NOW, NEXT, and BLOCKED columns. WHERE is the project
display label and explicitly withholds exact location. NOW prefers an in-progress source task,
then bounded state detail. NEXT uses a pending source task or names that no pending step was
published. BLOCKED distinguishes a reported block, a source-backed no-block reading, and a harness
whose block state is unknown. Recent history retains identity, project scope, the last published
activity and a QUIET or ENDED label where supported. It also shows measured stop/end outcomes and
git evidence, but omits NEXT and BLOCKED. An ENDED row reported its own end; mere presence in
history proves neither an open nor a closed process.

Wide rows share one grid definition with their column header, so values do not drift between rows.
The harness and title remain visible while the full session ID moves behind a dedicated copy
control. The control exposes the ID in its accessible label and tooltip, writes it to the clipboard,
and announces success without navigating. Routes include project label, harness, and full session
ID so equal IDs from different harnesses cannot select the wrong row.

The 320-pixel layout changes form instead of squeezing the table. The fleet strip becomes a
compact two-by-two summary. Each active session becomes a nearly full-width card with identity
across the top and WHERE, NOW, NEXT, and BLOCKED in a two-by-two fact grid. Recent history keeps
its activity and observed outcome beside identity and scope. Labels that would repeat desktop
column headers appear inside cards only at responsive widths. This preserves scan order without a
page-level horizontal viewport.

Projects follows the same hierarchy one level up. It separates active projects from recently
observed projects. An active project shows its grouping identity, summary counts, the shared-label
caveat when applicable, and one line per observed member session with title, NOW and NEXT. The
grouping can contain quiet or ended members alongside active work. A project stays active while
any member is working, waiting or carrying an exact request. Historical projects retain identity
and counts but omit member activity lines. Project detail then owns workflow and grouped activity;
session detail owns the exact session's current activity and progressive command facts. No level
repeats a broader summary merely because it can.

The same order governs inside a panel, and Console is where it was breached. Measured at 1680x1057,
its first operational heading began 341px into a 968px panel: 309px of that was an exact-session
terminal, an observer-model notice and a raw status line, three blocks describing capabilities a
default run has switched off. They never change while a reader works, and the figures under them
change minute to minute. The panel now emits the scope header, the select-a-session prompt at
project scope, the operations rail, and then one disclosure holding the setup blocks. Nothing left
the page.

Two rules keep that honest. The disclosure summary reads the capability flags, not the rendered
bodies: the terminal section returns empty with no focus and the status line returns empty with no
sessions, so a summary derived from what came back would report an enabled bridge as off. And a
capability that is on is operational content, so its section renders expanded and outside the
disclosure rather than collapsed with the rest.

## NUI-17: the gate queue hands over a command, and only where one was measured

A gate-queue row names a session that is waiting and then leaves the reader to find its terminal.
That is the weakest point of the thing this board is best at: it can tell you a session on this
machine has been blocked for eleven minutes without telling you where it is.

The row therefore carries one control that copies the command that harness's own CLI takes to
re-enter that session. It rides the SOURCE line rather than the item's lede, because it must not
compete with the wait reason, and it reuses the session-ID control's markup, its copied and failed
states, and its live region, so a reader who has learned one control has learned the other. It is on
the gate queue's rows alone. Every section of Attention names a session, so a control placed by
identity would render four times over, and a small affordance on every row is furniture rather than
an affordance. This one answers "it is waiting on me, get me there", which is the question only
Needs you asks.

Coverage is two harnesses of the ten, and the table of verbs is measured rather than documented:
`claude --resume <session-id>` read off Claude Code 2.1.261's help, `codex resume <SESSION_ID>` off
Codex 0.153.4's. A harness absent from that table gets no control at all, because a guessed verb
costs the reader a failed command on top of the hunt it was meant to replace. The rule the page
applies is total: no published token, no control. That is why Codex repeats an id it already
publishes as `sid` into `resume_id` rather than letting the page infer resumability from the harness
key, and why Claude publishes the whole transcript stem there. Claude's `sid` is that stem's first
eight characters, and `claude --resume 27d10654` answers that the argument is not a UUID and matches
no session title (measured on 2.1.261).

### Re-entering a live session was the question to settle first

The obvious objection is that a reader copies this command while the session is still running and
puts a second process on one conversation. Both harnesses refuse, and both say so rather than doing
it quietly. Claude Code declines interactively with
`Can't open — this session is running in another terminal`, and its background variant starts a copy
and reports that the original conversation is unchanged. Codex declines with `thread-store conflict: thread <id> already has an active writer`,
observed by running two `codex exec resume` calls against one id. Both were measured on the
installed CLIs, not inferred.

So the control carries no warning. A warning would describe a hazard the harnesses already close,
and the worst case is a refusal that names what to do next. That is also why this is written down:
re-deriving it means installing two CLIs and deliberately racing them against one conversation, and
whoever changes this control next will ask the same question first.

The token the command is built from comes off a filename in a store the harness owns, so it is
untrusted like every other reading here. The grammar that guards it, and the `-`-leading token that
grammar exists to refuse, are in [SECURITY.md](../SECURITY.md).

### A control's answer outlives the render, and it is not a server fact

One row of a longer inventory. [What reader state survives a redraw](design-reader-state.md) is the
owner of that list and of the two rules every row follows; this section keeps only the reasoning
specific to a control cue, including the alternative that was rejected.

`renderNext` replaces the whole of `#app` on every revision event, and the live lane fires one of
those about as often as anything happens on the machine. A state written onto the node the click
found therefore dies with the next render, which is how both row controls shipped: the colour cue
for copied, sent, declined, throttled and failed was lost, while the screen-reader announcement
survived because the live region sits outside `#app` and is held in a module variable.

The obvious fix, and the one the issue asking for this proposed, is to carry the state in the model
so a render re-emits it. That was rejected, and the reason is worth keeping. None of these states is
a server fact. A copy succeeded or failed in one browser's clipboard, and a raise was accepted from
one tab. The server has no way to know either, and the payload is shared by every viewer, so one
reader's confirmation would paint the same row for everyone else looking at it.

So the state lives in the page, in a map keyed by lane, harness and session id. Three bounds make
that safe to hold. It caps at 32 entries and evicts the least recently written, because the key
space is one entry per control per session and a long-lived tab would otherwise accumulate them for
sessions that ended hours ago. Each entry expires after 30 seconds, which is above the 20 second
fallback poll, so a cue always survives at least one full render cycle rather than having its life
decided by when the next payload happens to arrive. And the expiry exists at all because a cue with
no clock behind it paints a row that has since changed hands.

Two things follow from the same reasoning. The refusal of a second raise is page-wide rather than
per-row, because one raise is in flight for the whole page: a per-row cue would tell the reader that
only the row they clicked second is unavailable, which is false about every other row. And the map
is consulted by a sweep over the controls in the document rather than only the node the click found.
Writing to that node alone left a completed raise painting the working look for up to a poll cycle
while the live region beside it already said the raise was sent. Two channels of one page
contradicting each other is worse than a cue that was merely missing, which is what the same case
produced before any of this.

## NUI-18: one control primitive, and an inert control stays on the page

Two rulings, taken together because the second is only safe given the first.

**The stylesheet had no way to say "this one."** There was no shared control class and no radius
token: 43 literal `border-radius` declarations and zero `--radius` anywhere. A sweep of the resting
control rules (a selector naming a `button`, a `summary`, or a class the JS puts on one, excluding
state and `:hover` variants) found **24 rules declaring their own radius or resting border, across
six corner treatments**: none, 3px, 4px, 6px, 9px and 999px. Because every one was a variation on
"faint outlined box" or "bare text", the whole range was spent on the secondary tier and nothing was
left to mark the one control to press. `--accent` never appeared at rest on a control at all.

`.next-action` is that primitive, with `--radius-control`, `--control-bd` and `--control-pad`. It is
a class a control opts into by writing it, **not** a selector group in the stylesheet. The group was
tried on paper and rejected: it touches one file instead of seven and satisfies the same grep, but it
means every new control must be appended to a growing list in the sheet, which is precisely the
ad-hoc drift that produced the 24 recipes. The resting border is `--ink3` (5.67:1 on `--panel`)
rather than `--line2` (1.61:1), because a box a reader is meant to see has to clear the 3:1
non-text bar.

Seven rules collapse onto it. The criterion was stated universally and **is not**: it is accepted on
an enumerated verifier, with five further action rules filed as their own issue and the exempt ones
named with their reasons in the sheet: `--amber` state signals, a `role="switch"`, a selection, two
disclosures, and the legacy project view. `.next-action--primary` reaches exactly one tab, because
four of the five have no action to mark at all; what each of those tabs' main action should *be* is
a product question filed separately rather than answered in a restyle.

**Disabled is dashed, not dimmer.** `--ink3` is the resting colour of the prose these controls sit
in, so a disabled control drawn one ink step down was being drawn in the body ink and disappeared
entirely in greyscale. `border-style` carries it because no ink choice can. `.next-stalled
button:disabled` keeps `cursor:wait` as an explicit override: that control is waiting, not refusing,
and collapsing the two loses a distinction a reader acts on.

### An inert control is present and refusing, never absent

The reading control was deleted outright whenever a reason withheld it, which took the button, the
offer paragraph, the sending disclosure and the request counter off the page together, in the one
state a newcomer lands in. It is now rendered in all four reason states, with the reason printed
after it rather than in place of it.

This **supersedes** the DRC-4565-era ruling that the offer stays withheld on the discarded and
never-typed rows. That ruling's argument was that withholding is what makes the sentence
load-bearing rather than decoration. What changed is that the sentence is now bound to the control
through `aria-describedby`: it explains the button instead of competing with it, and withholding the
button was costing the reader the tab's only verb in the two states they most often arrive in. The
narrower claim that ruling was really making, that a discarded row says the discard sentence and
not "nothing typed", is untouched and still asserted.

**`aria-disabled`, not `disabled`, and the handler gate ships with it.** The browser's attribute
takes a control out of the tab order and silences its `aria-describedby`, so a reader who cannot
find the verb would meet a control they cannot reach and a reason they are never told. The same
ruling was already taken for the RAISE control. But `aria-disabled` **restores the click that
`disabled` was suppressing**, and the two handlers behind these controls gated on nothing that could
refuse it: a press would have reached `POST /api/reading` and spent the reader's own model capacity
from a state the page calls unavailable. So each handler refuses on the *same* expression its
control renders, from one function, rather than computing its own answer. A handler with a second
opinion can refuse a press the button offered, or take one the button refused. The refusal is
answered rather than dropped, because a clicked control that goes silent is indistinguishable from a
dead one.

## NUI-19: a caveat has three tiers

Cargento pays for its honesty in vertical space, and before this rule it paid the same price for
every sentence. Each caveat rendered as one `<p class="next-cockpit-reading-why">` in the reading
flow, so COUNTS closed with sixty-nine words under five numbers and the one operational
instruction in them was the third sentence. DRC-4587 made this worse rather than better: raising
board sentences to `--fs-sentence` gave `.next-cockpit-count-label` and `.next-cockpit-reading-why`
the identical font shorthand, so size stopped separating a caveat from the finding it qualifies.

A caveat now goes in one of three tiers, and the rule is about placement rather than length:

1. Tier 1 is always visible. It is one clause carrying the claim itself, twelve words or fewer,
   plus every absence value. If a reader acts on it, it is tier 1. "Five figures, and no arithmetic
   between them." is tier 1, and so is every `not published`.
2. Tier 2 sits behind a disclosure. It holds everything past that clause, under a summary of two to
   four words naming what is inside. `nextCockpitWhy` provides it on the `next-` surface and
   `projectDisclosure` on the `pc-` one.
3. Tier 3 is the design records. A sentence too long for tier 2 leaves the panel, and its full form
   is written here or in [design-reading-a-session.md](design-reading-a-session.md), cited from a
   source comment in the citation grammar `AGENTS.md` describes.

Tiering deletes nothing. Every sentence that existed before the rule still exists after it, inline
or one click away. The rule sanctions one exception, for a claim stated twice: the
`two axes, read separately` aside said what the footer under the same cards already said, and a
duplicate is not a tier.

### Tier 3 ships no `docs/` href and no `DEC-N` token

The obvious build of tier 3 is a link from the disclosure body to the design record. It cannot
ship, for two independent reasons, and both are invisible in a diff:

- An installed plugin has no `docs/` directory beside the page. The link resolves in a checkout
  and 404s everywhere the product actually runs.
- `RuntimeDecisionCitationsTest` reads every `.py`, `.js`, `.css` and `.html` under
  `cargento_runtime` as a whole file, not as comments. A bare `DEC-16` in a product string is a
  checker hit whether or not a reader ever sees it.

So tier 3 cites from a **source comment**, in the grammar the checker already enforces, and the
rendered page carries neither the token nor the path.

### The control is never smaller than what it hides

A tier-2 summary is set at `--fs-sentence`, the same tier as the body it reveals, because it
carries the only words a reader has for deciding whether to open it. A control set below the text
it conceals is the same defect class as an absence set above the value it replaces, which
DRC-4587 shipped in ten places across four review rounds: the two halves are chosen by a branch
and never render together, so no selector sweep and no walk of a populated board can see the pair.
Resolve both branches through the cascade and compare them.

## What this does not decide

Promotion itself did not create durable history. DRC-4234 subsequently authorized the bounded
local state-change store used by the workstream and delegation readings in NUI-9 and NUI-11.
That store is independent of which frontend is canonical, and its limits remain in
[SECURITY.md](../SECURITY.md#local-history-the-session-history-store).

Project and session identities, Spacedock plans, asks, tasks, subagents and token totals come from
the current payload. The project timeline and delegation figure also read the retained observation
window. Neither view supplies a durable task-completion history or a record of what the reader saw.

## Promotion boundary

The promotion deliberately removes the rollback-by-query path. Recovering the retired dashboard
would now be a source-control revert, not a runtime flag, so startup and routing cannot disagree
about which UI is supported. The retired query returns 404; it is neither an alias nor a rollback
surface.
