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
second rendering would give the same evidence two interpretations. Moving the full waiting queue
into Console must not hide a project wait: COMMAND names a waiting project session above the tabs,
with raise and copy-resume controls wherever supported. Decisions shows recorded decisions and
application evidence, not an approval mechanism.

The Scope rail gives harness names and session titles separate readable space at desktop widths
and becomes a scope switcher on narrower screens. Missing terminal registration, evidence, history
or delegation renders the reason for the missing reading. Source strings use mono; sentences the
board says use sans at 12.5px or larger. Evidence and More remain named disclosures.

The terminal bridge, semantic history and model-assisted goal analysis remain prototypes.
Human context and tripwires stay browser-local and deliver no instruction to an agent. Semantic
history has its own server store and is not removed by the session-history `--forget` command.
The optional observer model requires explicit enablement and scoped disclosure consent; the
browser does not yet supply that consent, so UI reads remain local. Its prompt cap and the local
dispatch and terminal trust boundaries belong to
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

Board sentences have a 12.5px floor (`--fs-xs`). Labels, identifiers, timestamps, rates and
compact controls retain their smaller design sizes, down to 9px column headers. The prototype
placed some absence explanations at 10px; those are sentences the board asks a person to read, so
the sentence floor wins. The stylesheet retains scale tokens and literal sizes. The asset test
pins the dark palette and checks text inks above 4.5:1 on the ground, panel and inset surfaces; it
does not enforce all font sizes or spacing between contrast steps.

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
model. Projects, Sessions and Attention all have primary navigation links. Shortcuts `p`, `s`, and
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

Console includes STEER and TRIPWIRES because the dashboard needs the interaction shape,
but neither is a session-control surface. The add control reads `+ set a tripwire`. Submitting a steer keeps a bounded draft record in that tab,
retaining the newest 20 drafts and rendering every retained draft from oldest to newest. Each
escaped receipt says both that it was not delivered and that Cargento has no session write path. It
makes no request. A disabled field was rejected because it could not demonstrate the interaction,
while an enabled field with no receipt would look like a successful send.

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
