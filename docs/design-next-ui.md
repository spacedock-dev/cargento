# Design: the dashboard UI

This document records the interface first released behind `?next=true` and the decisions that
survived its promotion to the default dashboard. The runtime module map remains in
[design-runtime-architecture.md](design-runtime-architecture.md).

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
that copy the canonical `web/styles.css` and removed the legacy stylesheet. Its light root,
`prefers-color-scheme: dark` override, type scale, selection tokens, responsive rules, and reduced
motion treatment now describe the only UI.

Space Grotesk and Space Mono subsets travel inside the assembled page as data URLs. A missing or
malformed font is a canonical asset failure and prevents startup before the socket binds. There is
no font route or browser request to a provider. Licenses and source hashes live under `web/fonts/`.

## NUI-3: the released route and storage namespace remain stable

The fragment grammar is `#n=sessions`, `#n=projects`, `#n=attention`,
`#n=project:<encoded-project>`, or a session route carrying encoded project, harness, and complete
session id. Invalid and retired fragments normalize to Sessions. Hash changes are both navigation
output and browser-history input, so reload, pasted links, and back or forward preserve the view.

Browser state keeps its `cargento.next.*` namespace. That prefix is no longer a firewall between
two live bundles; it is compatibility with storage written during the preview and protection from
stale `cargento.leader` records written by the removed dashboard. The current leader uses
`cargento.next.leader` and `cargento.next.revision` so a stale old lease cannot demote it.

## NUI-4: the canonical bundle fails before bind

`cli.main` assembles one required page before creating a daemon log, binding, forking, or spawning a
Windows child. Failure in the shell, stylesheet, any script part, or any embedded font is fatal and
reported as a frontend asset error. Requests never read source files, and each server instance owns
its already assembled bytes.

The runtime inventory and copied-plugin tests enumerate the root assets explicitly. They prove an
installed copy is complete rather than relying on recursive copying to conceal an omitted file.

## NUI-5: chrome and navigation reflect the current payload

The header reports running sessions and subagents from the payload and exposes a needs-input button
only when intervention exists. Projects and Sessions are the primary navigation; Attention is
reached through that button or `a`. Shortcuts `a`, `p`, and `s` are case-insensitive and do not run
while a form control owns focus or Meta, Control, or Alt is held. The preview's `dashboard mode`
button and `d` shortcut were removed during promotion because `/` now serves this same interface.

Projects groups the current payload by display label and splits active evidence from recently
observed groups. Sessions separates Active now from Recent history. The active group retains gate
priority and the working attention ladder, while history remains reachable without presenting its
last observed state as a current operation. Every row carries the exact route needed by project or
session detail.

Two consecutive fetch failures show a stalled notice beside the last good payload. A manual retry
uses the same serialized refresh path. The page forwards only `all=1` to `/api/data`; `next=true`
never changes collection. Every client-derived age uses the payload's generated time rather than
the browser clock.

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

The project header folds those same per-entity states into an `N entities unhealthy` count. It
renders the count only when at least one named plan exists. A plan with no published entities
reports a measured zero; no plan omits the count and its divider. Stages do not become steps, and
the header makes no step-health claim.

The payload does not distinguish an initial entity from a completed one, and it carries no pull
request state. PLAN therefore has no completion glyph, completion count, merge state or review
state. Its three empty messages keep the payload's distinctions: no Spacedock declaration, a first
officer whose workflow has no fresh entities, and an ensign whose plan lives with its first officer.
The main column and rail are separate section-block regions. The activity layer fills the two
reserved work-state blocks without rebuilding PLAN.

## NUI-7: project activity is a current-payload answer

GOING ON answers from the project's session rows. Sessions waiting for input keep payload order
because the server has already established their precedence. Re-sorting that queue in the browser
would erase evidence the collector supplied. Behind them come the working rows, on the same stable
long-turn and session-ID ladder as the sessions overview. Their cards share the payload clock,
harness labels and measured wait or token-rate phrases with that overview, then route with both the
project label and session ID.

Each activity card also names its published subagents. The compact list keeps payload order and
shows at most six rows, followed by `+N more` when the payload carries more. An elapsed age appears
only when `started_at` is measurable against the payload's `generated` clock; missing or invalid
stamps leave the name in place without inventing an age. The age uses the NUI-5 duration grammar.
Malformed subagent collections produce no list, and malformed entries keep the neutral `subagent`
fallback used by session detail.

The rate phrase preserves the payload's distinction between absence and zero. A session from a
rate-blind harness carries `rate_per_min: null`; a reporting harness that measured no output in the
window carries `0`. The summary remains the sum of present measurements, while the harness strip
qualifies that total as a floor whenever an active session's source is blind, or any discovered
collector failed. This keeps the scalar useful without turning an unmeasured session into a
confident `0 /m`.

Membership is `state`, and `active` is only a freshness gate on top of it. The two were conflated
once, and the block filtered on `active` alone. Every session still inside the display window
qualified, so a repository running one live Codex session rendered eleven cards, ten of them idle
and captioned "awaiting your message", under a header that read `1 running`. The header and the
sessions overview were both right, because both read `state`. A payload has one answer to what is
going on, and a block that derives its own from a different field will eventually contradict the
rest of the page.

DONE is deliberately narrower. It walks each project session and its Claude task list in payload
order, selecting only tasks whose published status is `completed`. It does not sort by task times or
deduplicate subjects. Task identity is local to a session, and the same subject can represent two
real pieces of work. Spacedock entities are not a completion source: terminal entities do not reach
this payload, and the remaining plan rows carry no completed marker.

Both blocks render an explicit empty sentence. DONE names the payload because it is a view of the
latest snapshot, not a retained history or a claim that a project has never completed work. A
time-ordered list would require the persistent-history decision tracked in DRC-4234.

## NUI-8: session detail stays inside the current payload

A session route carries the project display label and full session ID. The detail lookup requires
both. A stale route, including the right ID under the wrong project label, gets an explicit
outside-payload state instead of a guessed row. The flat session table now emits the same route as
the project activity cards, so it no longer stops at project detail.

The header uses `title`, then `last_prompt`, with the first matching question as a fallback.
Beneath it, on the detail header, the flat session table and each GOING ON card, sits the row's
`instruction`: a labelled second line carrying what the session is working on now, since the title
above it answers a different question and on a long Claude session answers it about work that
finished hours ago. One renderer serves all three, so the rule for when a line may be shown has a
single definition. The line renders only with its label and the age of the record it came from,
and it is dropped when the payload publishes none, when the label is not one the runtime issues,
when its text equals the title, and when the title ends in an ellipsis and the text continues it,
which is one prompt reaching the two lines at their two clip widths. Not the reverse: a short
title that merely opens a longer, genuinely newer instruction is the case the line exists for, so
a plain prefix test would delete exactly what was added. Over 2,931 rows of one local store the
equality branch suppresses 13 lines and the clipped-title branch 30, while the reverse rule fires
on none of them.

Each surface clips the line to what it can carry. The detail header and the table row wrap it; a
GOING ON card holds it to one line, because that block is scanned rather than read and a card that
grows whenever the newest prompt is long pushes the next card off the fold. The label and the age
are never in the part that clips. The card renders the line as a span rather than a paragraph,
since the card is a button and takes phrasing content only.

The age sits outside the label span. `.next-instruction-label` uppercases, which turned "asked, 4m:"
into "ASKED, 4M:". A duration whose unit is a capital letter reads as an initialism, and the whole
prefix reads as one label rather than as a label and a measurement. In the session table line 1
takes a label of its own, but only on rows where line 2 stands under it: a labelled second line
below a bare first line reads as a caption for the row, and a lone "title:" on every row of a table
whose column is already headed SESSION buys nothing.

The projects overview reads the same field for a different purpose. Its `last instruction` cell
takes the newest session in the group and prefers `instruction.text` where the label is `asked`,
falling back to `last_prompt` and then `title`. That label is the newest genuine prompt with the
harness-injected shapes dropped and slash markup read back out, while `last_prompt` on every
harness but Codex is the raw record: on the same 2,931 rows, 114 carry an `asked` line, 15 of those
differ from `last_prompt`, and 2 have no `last_prompt` at all. The other two labels stay out of
that cell, which has nowhere to put a label and would otherwise present an agent quoting itself, or
a line that is explicitly not the newest thing asked, as the project's last instruction.

The header's metadata is built only from measurements the row carries: the registry label, short
session ID, and activity detail. A working row labels its measured `turn.elapsed_h` as the current start age;
an absent, empty, or malformed turn measurement removes that clause instead of falling back to the
transcript's creation time. A needs-input row derives its blocked age against the payload's
`generated` clock. An idle row may use the same clock for an explicitly named session-start age.
Those two client-derived ages use the NUI-5 duration grammar; the working turn keeps the server's
published string. Missing timestamps remove those clauses. They never become zero.

The header also carries a static rail for the three published states: warning for needs input,
accent for working, and muted for idle. Matching visually hidden text keeps the state from becoming
a color-only cue. Unknown state values produce neither rail nor label. The needs-input article edge
remains a separate alert treatment around the detail view; the header rail provides orientation and
does not replace it.

The detail health callout is bounded to two measurements already present on the row:
`turn.long` and the failed-tool-loop peak in `loop`. A long turn keeps the `LONG TURN` label;
when both measurements exist, the loop sentence replaces the generic long-turn explanation rather
than producing a second notice. A loop without a long turn uses `FAILED TOOL LOOP`, and remains
visible after the session stops because the server retains that peak until the next prompt. A
missing or malformed positive integer count removes the loop notice. Neither path infers a stalled
or failed outcome. The canonical bundle keeps the MCP tool-name formatter near the detail renderer
that uses it.

Questions render only when the payload advertises the ask capability. Matching is exact on the
full session ID, keeps payload order, and shows every match. The callout uses the same
`<harness> is asking you` sentence as native notifications. Each option posts its
numeric index to the existing `/api/answer` endpoint. Only `answered: true` confirms the action;
otherwise the question stays put with a failure note keyed to its ask ID. There is no optimistic
removal.

Task provenance stays Claude-only because no other collector publishes that list. The count is
derived from the rows being rendered, and their payload order is unchanged. Subagents also keep
payload order. Their live dot pulses unless reduced motion disables animation, and elapsed time
appears only when `started_at` was measured, using the NUI-5 duration grammar; model names are
outside this view. For working sessions,
the footer prefers measured turn output tokens. For waiting and idle sessions, it prefers the
measured session total. Either state falls back to the other measured source and labels the visible
number `this turn` or `this session` from the source it actually chose. An absent reading stays
absent and a real zero stays visible, so a lifetime total cannot read as if it described the current
request.

A new session endpoint would duplicate the current payload and expand the HTTP surface without
supplying new evidence. The `next-session.js` part renders from the canonical payload and adds no
retained history; that decision remains DRC-4234.

## NUI-9: the workstream starts when this tab starts observing

The server still publishes one current snapshot. `next-workstream.js` therefore builds a bounded
ledger only from advancing payloads seen by this tab. The first successful payload establishes the
session and ask baseline without turning existing state into invented history. Later payloads add
state transitions, newly measured turn stops and newly observed asks in timestamp order. Replayed
payloads add nothing.

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
the viewer clock. Its header always keeps the `N of M unattended` ratio; expansion appends the
retained span instead of replacing that ratio. The rail is empty until a post-baseline event arrives
and says so explicitly. Reloading discards the ledger. Only the collapsed preference survives,
under the next bundle's storage namespace and behind a storage failure boundary.

Rendering consumes the ledger through a project-window function rather than reading its mutable
arrays. A future server history source can replace that function without changing the rail, but no
such source or retention policy is implied here. DRC-4234 owns that later decision.

## NUI-10: project controls demonstrate local state, not delivery

The project rail includes STEER and GUARDRAILS because the dashboard needs the interaction shape, but
neither is a session-control surface. Submitting a steer keeps a bounded draft record in that tab,
retaining the newest 20 drafts and rendering every retained draft from oldest to newest. Each
escaped receipt says both that it was not delivered and that Cargento has no session write path. It
makes no request. A disabled field was rejected because it could not demonstrate the interaction,
while an enabled field with no receipt would look like a successful send.

Guardrail rules are viewer preferences. They are stored under a project-label key in the next
bundle's localStorage namespace, capped at 50 rules of 500 characters, and kept in memory if storage
throws. The project label is enough for a local browser preference. It is not stable enough for a
server store that changes what agents do. Stored values are untrusted input, so both loaded and new
rules pass through the shared escaping function every time they render. The header and every row
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

## NUI-11: delegation is wall time inside this tab's evidence

The project rail's delegation figure integrates adjacent sample batches from the in-tab workstream
ledger. A batch owns the wall-clock interval until the next advancing payload, clipped to the
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
the ledger cap was sized to preserve at the measured 22-session population. A trend needs two
independent full observed windows: it compares the latest six hours with the six before them only
when twelve retained hours exist. At the measured population the cap may prevent that condition,
in which case no trend is more honest than a flat arrow.

For each delegated interval, the session rates in that payload are summed and those per-payload
aggregates are time-weighted over delegated wall time. A session whose harness cannot measure rate
makes the result a `≥` floor; if nothing in the delegated intervals has a measured rate, or no
delegated interval exists, the token figure is absent rather than zero. Human-turn candidates are
transitions out of `needs_input` and `idle` to `working` prompt boundaries. Delegation coalesces an
immediate same-session `needs_input` to `idle` transition followed by `idle` to `working` into one
inferred answer. A direct gate-to-working transition still counts once, and a later prompt boundary
after another same-session state transition counts separately. Other sessions do not clear or
consume the pending resumption.

The payload has no response identifier, so the pairing uses harness and session ID without an
invented time threshold. Events before the displayed window still establish pending state, but only
events inside the window increment its count. Gate openings, ask registrations and turn stops remain
agent-side events and do not increment it.

The number begins again when the tab reloads. It is not durable;
[DRC-4234](https://linear.app/recce/issue/DRC-4234) still owns the decision about persistent history.

## NUI-12: motion means observed activity, not mere attention

The same live treatment appears in four places, with two different claims. The header always marks
its running and subagent summary as live, including when both counts are zero, because the cue is
about the current payload rather than an individual session. Fresh subagents in session detail,
working sessions in GOING ON and active working rows in the sessions overview use the marker only
for observed activity. A listed subagent has passed the collector's freshness test; session rows
and GOING ON cards also require `active`. No browser timer infers that work is alive.

A gate stays amber and static even when its session still has `active: true`. It is important, but
it is waiting rather than moving, and animation must not turn attention priority into a claim of
progress. A working row whose `active` flag has lapsed likewise keeps its place in the working
group without the live dot.

The pulse changes only opacity. Under `prefers-reduced-motion: reduce`, animation is disabled while
the filled accent dot and `next-live` class remain, so liveness does not depend on motion. All of
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
assignment when none was published and places missing next-action provenance in a closed source
coverage disclosure. The fixed operational columns may state their bounded absence, such as no
pending source task, because the column itself answers a stable question. They do not translate
that absence into intent, completion, or an all-clear.

Current activity leads session detail. Its known state, source-backed activity, and running
subagents occupy one region because they answer the same question: what is happening now. Session
title and harness metadata remain identity beneath that lede. Assignment, next action, and exact
request follow only when published. Health, answer controls, tasks, and token evidence remain
below the command facts. This hierarchy prevents a session title from competing with its current
work or making attached subagents look like unrelated sessions.

## NUI-16: operations lead; observation stays reachable

The exception-first Attention route was implemented and tested before the operations board. Its
taxonomy was source-bound, disclosed coverage, and ranked exact requests, risks, observed stops,
and published tasks. In live review, that direction still buried the operator's first questions.
A reader had to decode queue categories and coverage before finding where sessions were, what each
was doing now, what came next, and whether it was blocked. The compressed remainder also made
recently observed sessions look too much like current operations. More ranking did not solve the
information hierarchy.

Session operations therefore became the default route, with Projects beside it as the complete
map. Its fleet strip leads with four bounded counts: active now, working, exact requests, and
reported blocks. `Active now` means a working state, a needs-input state, or an exact request. It is
not the number of rows in the payload. That distinction prevents a 24-hour observation window from
reading as a list of open harness processes.

The body makes the time boundary visible. Active now contains only exact sessions with active
evidence and gives each one stable WHERE, NOW, NEXT, and BLOCKED columns. WHERE is the project
display label and explicitly withholds exact location. NOW prefers an in-progress source task,
then bounded state detail. NEXT uses a pending source task or names that no pending step was
published. BLOCKED distinguishes a reported block, a source-backed no-block reading, and a harness
whose block state is unknown. Recent history retains identity and project scope, but its operational
facts are neutral dashes on wide screens and disappear on narrow screens. It never claims that a
recently observed harness is still open or already closed.

Wide rows share one grid definition with their column header, so values do not drift between rows.
The harness and title remain visible while the full session ID moves behind a dedicated copy
control. The control exposes the ID in its accessible label and tooltip, writes it to the clipboard,
and announces success without navigating. Routes include project label, harness, and full session
ID so equal IDs from different harnesses cannot select the wrong row.

The 320-pixel layout changes form instead of squeezing the table. The fleet strip becomes a compact
two-by-two summary. Each active session becomes a nearly full-width card with identity across the
top and WHERE, NOW, NEXT, and BLOCKED in a two-by-two fact grid. Recent history keeps only identity
and scope. Labels that would repeat desktop column headers appear inside cards only at responsive
widths. This preserves scan order without a page-level horizontal viewport.

Projects follows the same hierarchy one level up. It separates active projects from recently
observed projects. An active project shows its grouping identity, summary counts, and one command
line per exact active session, with NOW, NEXT, and BLOCKED still attached to that session. Historical
projects keep identity and scope but omit stale operational claims. Project detail then owns
workflow and grouped activity; session detail owns the exact session's current activity and
progressive command facts. No level repeats a broader summary merely because it can.

## What this does not decide

Promotion does not create durable event, turn, or UI history. History-backed regions remain
windowed or withheld after reload. Whether Cargento should persist session history is the follow-up
decision in [DRC-4234](https://linear.app/recce/issue/DRC-4234); it is independent of which
frontend is canonical.

Project and session rows are live from the existing payload. Their detail views render only that
snapshot: the project shows the honest Spacedock plan, while the session shows its current asks,
tasks, subagents and measured token total.

## Promotion boundary

The promotion deliberately removes the rollback-by-query path. Recovering the retired dashboard
would now be a source-control revert, not a runtime flag, so startup and routing cannot disagree
about which UI is supported. The retired query returns 404; it is neither an alias nor a rollback
surface.
