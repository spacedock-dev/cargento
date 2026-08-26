# Design: the next UI bundle

This document owns why the opt-in UI is a separate frontend artifact, how two pages on one origin
stay out of each other's state, and how to remove the split. The runtime module map remains in
[design-runtime-architecture.md](design-runtime-architecture.md).

## NUI-1: two precomputed pages make the flag a routing property

Before this work, `web/page.py` assembled `index.html`, `styles.css` and `APP_PARTS` into one byte
string. `cli.py` loaded it before bind and `CargentoHTTPServer` served that object for every `/`
request. A condition inside that script could hide new UI, but it could not preserve the old page's
bytes. Every frontend branch would move the old page's size and digest oracles.

The next UI instead has its own shell, stylesheet and `NEXT_PARTS` under `web/next/`.
`load_next_page()` assembles a second byte string, and the `/` handler selects it only when the first
`next` query value is exactly `true`. With the flag absent, the handler still returns the same
`load_page()` object assembled from untouched inputs.

The query flag was chosen over `GET /next` because it composes with `?all=1` and leaves one base URL
to paste. A separate path would preserve the same byte guarantee and remains viable. The rejected
option is a client-side flag inside `APP_PARTS`: it would change the frozen bundle, execute both
interfaces in one global scope, and recreate the byte-pin conflict on every frontend PR.

## NUI-2: copied tokens keep the stylesheets independent

`web/next/styles.css` carries a copy of the default stylesheet's token block, with the dark values at
the root because this UI is dark unconditionally. It does not import, extend or extract tokens from
`web/styles.css`.

That duplication is deliberate. Extracting a shared token file would change the default page and
make both bundles depend on later edits to one source. Importing the old stylesheet would also load
all of the old component rules into the preview. A copied block costs two spellings, but it lets each
bundle change without moving the other bundle's bytes.

The same cost applies to small JavaScript rules both pages need, including escaping, relative time
and status marks. When wording is visible in both interfaces, a cross-bundle equality test is the
check against drift. Sharing a script part would couple the two assembly orders and is not the fix.

## NUI-3: one origin needs a state firewall

Separate bytes do not separate browser state. Both pages use the same origin, so they share
`location.hash` and `localStorage`.

The default bundle treats any fragment containing `session=` as its session route. The next bundle
therefore uses one `#n=` token: `overview`, `project:<encoded-project>` or
`session:<encoded-project>:<encoded-session>`. No form contains that substring. Hash changes are
the browser-history input as well as the output of breadcrumb and Escape navigation, so shared
project and session links survive a reload without another state store. Every storage key written
by the next bundle begins `cargento.next.`. In particular, a later next-page stream may use
`cargento.next.leader` and `cargento.next.revision`; it must not read or write the default page's
`cargento.leader` or `cargento.revision` lease.

`tests/test_next_isolation.py` freezes both directions. State left by the next page cannot change a
default-page render or display mode, and the next page cannot disturb a foreign default-page lease.
That file is the milestone firewall, not a fixture later work may relax.

## NUI-4: the preview fails closed without taking down the dashboard

The default bundle is required. If it cannot be assembled, `cli.main` reports the asset error and
returns before binding. The next bundle is optional and loads under its own exception boundary. A
failure there produces a warning, leaves the default bytes attached to the server, and makes only a
flagged request return 503.

Both pages are assembled once before serving and stored on the server instance. No request reads
source files, and two servers in one interpreter cannot answer with each other's pages. The explicit
runtime inventory and copied-plugin tests cover the nested assets because a recursive copy alone
would carry them without proving they were expected.

## NUI-5: the chrome counts the payload it actually has

The next page has its own `/api/data` loop because its script shares no scope with the default
bundle. It polls at the default bundle's named 5 s fallback cadence and forwards `all=1` only when
the page query carries it. The distinction matters on the server: collection is memoized by the
`show_all` value, so an all-sessions tab beside a regular tab causes a second filesystem pass.

The chrome does not repair or reinterpret the payload. Running means `summary.working`, not
`summary.active_sessions`, because the latter also includes sessions waiting for input. The gate
pill comes from `summary.needs_input`, subagents are counted from the rows, and the project/session
line names the payload's `window_hours` rather than implying a machine-wide inventory. Two
consecutive fetch failures put a stalled marker beside the last good payload; a single failed poll
does not flash the page on a transient miss.

The overview chrome owns `projects` and `sessions` body slots without owning either view. The
projects slot now groups the current payload by its display label and renders the measured task
progress and current state. Estimate and delegation stay visibly withheld: neither value exists at
project scope, and folding per-session values would turn a guess into a measurement. The
sessions slot now renders the current payload in three independent blocks: the gate queue keeps
the server's order, working rows use the established attention ladder, and the idle tail puts the
nearest activity first. The session-detail renderer in NUI-8 consumes the route each row carries.
`dashboard mode` performs a full navigation to `/`, which drops the next-page fragment and lets the
default bundle choose its saved display mode.

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
does not prove which session owns it and leaves the owner blank. `stalled Nm` starts after 600
seconds against the payload's `generated` clock. That floor is one complete token-rate evidence
window. The 90-second collector threshold answers a different question: whether recent store
activity is enough to call a session working.

The payload does not distinguish an initial entity from a completed one, and it carries no pull
request state. PLAN therefore has no completion glyph, completion count, merge state or review
state. Its three empty messages keep the payload's distinctions: no Spacedock declaration, a first
officer whose workflow has no fresh entities, and an ensign whose plan lives with its first officer.
The main column and rail are separate section-block regions. The activity layer fills the two
reserved work-state blocks without rebuilding PLAN.

## NUI-7: project activity is a current-payload answer

GOING ON answers from the project's session rows. Sessions waiting for input keep payload order
because the server has already established their precedence. Re-sorting that queue in the browser
would erase evidence the collector supplied. The remaining active rows use the same stable
long-turn and session-ID ladder as the sessions overview. Their cards share the payload clock,
harness labels and measured wait or token-rate phrases with that overview, then route with both the
project label and session ID.

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

The header uses `title`, then `last_prompt`, with the first matching question as a fallback. Its
metadata is built only from measurements the row carries: the registry label, short session ID,
activity detail, and a started or blocked age against the payload's `generated` clock. A missing
timestamp removes its clause. It never becomes zero.

Questions render only when the payload advertises the ask capability. Matching is exact on the
full session ID, keeps payload order, and shows every match. The callout uses the same
`<harness> is asking you` sentence as native and browser notifications. Each option posts its
numeric index to the existing `/api/answer` endpoint. Only `answered: true` confirms the action;
otherwise the question stays put with a failure note keyed to its ask ID. There is no optimistic
removal.

Task provenance stays Claude-only because no other collector publishes that list. The count is
derived from the rows being rendered, and their payload order is unchanged. Subagents also keep
payload order. Their live dot is static, and elapsed time appears only when `started_at` was
measured; model names are outside this view. The footer prefers measured session output tokens,
falls back to measured turn output tokens, and distinguishes an absent reading from a real zero.

Reusing `web/session.js` or `web/ask.js` would join the two script scopes and break the default-page
byte firewall. A new session endpoint would duplicate the current payload and expand the HTTP
surface without supplying new evidence. The separate `next-session.js` part needs neither. It also
adds no retained history; that decision remains DRC-4234.

## NUI-9: the workstream starts when this tab starts observing

The server still publishes one current snapshot. `next-workstream.js` therefore builds a bounded
ledger only from advancing payloads seen by this tab. The first successful payload establishes the
session and ask baseline without turning existing state into invented history. Later payloads add
state transitions, newly measured turn stops and newly observed asks in timestamp order. Replayed
payloads add nothing.

Every advancing payload also contributes one sample per session with its project, state and
measured token rate. These samples are the evidence the later delegation panel needs; transitions
alone cannot recover the intervals between them. State events keep both sides of the transition for
the same reason. The 100,000-logical-entry cap was chosen against the observed 22-session case at
the five-second poll cadence: six hours produces 95,040 samples before transition entries. Whole
payload groups are dropped oldest-first. Only a single payload larger than the entire cap is
tail-bounded, a defensive path far outside the measured population.

The section names the retained span rather than copying the mock's fixed six-hour label. Before a
span exists it says `since this tab opened`; elapsed labels come from payload `generated` times, not
the viewer clock. The rail is empty until a post-baseline event arrives and says so explicitly.
Reloading discards the ledger. Only the collapsed preference survives, under the next bundle's
storage namespace and behind a storage failure boundary.

Rendering consumes the ledger through a project-window function rather than reading its mutable
arrays. A future server history source can replace that function without changing the rail, but no
such source or retention policy is implied here. DRC-4234 owns that later decision.

## NUI-10: project controls demonstrate local state, not delivery

The project rail includes STEER and GUARDRAILS because the preview needs the interaction shape, but
neither is a session-control surface. Submitting a steer keeps a bounded draft record in that tab,
renders the escaped draft, and says both that it was not delivered and that Cargento has no session
write path. It makes no request. A disabled field was rejected because it could not demonstrate the
interaction, while an enabled field with no receipt would look like a successful send.

Guardrail rules are viewer preferences. They are stored under a project-label key in the next
bundle's localStorage namespace, capped at 50 rules of 500 characters, and kept in memory if storage
throws. The project label is enough for a local preview preference. It is not stable enough for a
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

## What this does not decide

The second bundle does not create durable event, turn or UI history. History-backed regions remain
windowed or withheld after reload. Whether Cargento should persist session history is the follow-up
decision in [DRC-4234](https://linear.app/recce/issue/DRC-4234); it is not a prerequisite for the
opt-in UI.

Project and session rows are live from the existing payload. Their detail views render only that
snapshot: the project shows the honest Spacedock plan, while the session shows its current asks,
tasks, subagents and measured token total.

## Way back

If maintaining two implementations costs more than the compatibility window is worth, promote
`load_next_page()` to `/` and delete `APP_PARTS` in one PR. Recompute the old byte oracles once at
that cutover. The namespaced state means no migration is needed to remove the preview.

The other reversible choice is the URL shape. The second blob can move to `GET /next` without
merging the bundles. Neither rollback requires a backend data migration, and neither is part of the
flagged milestone.
