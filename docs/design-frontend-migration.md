# Frontend migration contract

This record owns the React migration boundaries and measurement method. The
[runtime architecture](design-runtime-architecture.md) owns the module map; the
[reader-state inventory](design-reader-state.md#the-inventory) owns what a redraw must keep.
The migration preserves the [existing promises](promise-map.md), including their limits.

## Ownership before replacement

[The machine-readable inventory](../scripts/frontend-migration.json) maps each legacy script
part, visible surface, route, reader-state row and persisted browser key to its migration owner
and existing behavioral oracles. One row has one owner. A shared helper is migrated before its
callers, rather than copied into each view. The shell owns the revision/value helpers that
Intent currently reads from the project renderer.

`python3 scripts/frontend_inventory.py` checks the map without importing the dashboard or reading
local session stores. New script parts, reader-state rows and quoted storage namespaces require
inventory entries. Duplicate rows, missing owners and missing or escaping oracle paths refuse
the map. Surface and route rows are a reviewed enumeration, not proof that a static scanner can
discover every workflow. Existing Node VM tests protect semantic contracts; they cannot certify
native undo, composition, open option lists or browser layout.

## Separate pages during migration

The legacy renderer replaces all of `#app`. Mounting React inside that tree would destroy its
root on the next refresh. The migration therefore uses two whole pages, selected once when the
Python process starts. A request or URL never selects the renderer, and neither does an
environment variable or a stored setting: the launch flag is the only input. React is the default
and `--frontend legacy` is the explicit process-level rollback, forwarded to a detached child
rather than left to its own default. A selected build that cannot load refuses before the socket
is bound, says how to roll back and never serves the other page. Until the candidate passed the
complete parity and measurement gates, legacy was the default and any route React had not ported
said so in the page, naming the later step by what it brings, never by a tracker key, because
that text ships in the page.

The served page and published build identity must refer to the same renderer. Identity is derived
from deterministic content, independent of release versions and per-run capabilities. The focus
capability is injected at startup at an unambiguous template position; it is never built into the
tracked artifact.

## Build and development boundaries

React/TypeScript source lives outside the plugin. Pinned Node 26 and pnpm build a tracked Vite
artifact, so repository, tag, stable and source-archive installs work without Node. Core HTML is
self-contained and offline. Packaging decides whether the existing optional xterm assets remain
lazy same-origin files or become part of that HTML, with their size/startup cost measured. Fonts
and bundled modules retain their licenses and provenance. Canonical builds use Linux unless a
cross-platform probe establishes byte equality.

In development Python owns the document and API origin. The explicitly enabled page imports
Vite modules and the React-refresh preamble from a validated loopback child. Strict ports,
an owned-child handshake and exact origin checks prevent accidentally loading a different local
process. Production exposes no HMR path. Build plugins and dependency scripts never receive
release push credentials; publication verifies the exact fresh or resumed target tree.

## Lint and format

Biome, pinned exactly, lints and formats `frontend/**/*.{ts,tsx,mts,mjs}`, the two root tool configs
and `biome.json`. `pnpm lint` runs `biome check` with warnings as errors, so one command covers rules
and formatting; `pnpm format` rewrites. CSS, HTML and the captured JSON fixtures are outside the file
set: the fixtures are byte-exact Python captures, and the previous linter never read the CSS or HTML.
Line width is 100, the same as ruff's.

`biome.json` starts from no preset and enables, rule by rule, what the ESLint configuration it
replaced enforced: the JavaScript recommended set, typescript-eslint strict without type
information, the react-hooks rules and react-refresh. Biome's own recommended preset adds
accessibility and style policy that configuration never carried, so it stays off. Import organizing
is off for the same reason, and because CSS side-effect imports are order-sensitive.

After a Biome upgrade, probe one defect per rule class and confirm `pnpm lint` fails on it. The
React Compiler checks (set-state-in-effect, purity, refs, immutability, globals, static components,
error boundaries, `useMemo` returns, set-state-in-render) come from `nursery/useReactCompiler`,
which is experimental and can change between releases without a deprecation. The compiler reports
only on functions that look like components or hooks and return JSX.

Three kinds of difference were weighed and settled:

- **Stricter in Biome, so relaxed.** `noShadowRestrictedNames` rejects any global name, where ESLint
  rejects only a handful; `noUnsafeOptionalChaining` rejects a cast over an optional read, which a
  test uses on purpose; `useComponentExportOnlyModules` rejects unexported helper components, which
  react-refresh skips in `*.test.*` files. Each is off for test files only. `useErrorCause` does not
  require a catch parameter, matching ESLint's default.
- **No equivalent, accepted.** `no-dynamic-delete` (Biome's `noDelete` flags static keys instead,
  the opposite rule), `ban-ts-comment` for `@ts-nocheck` and undescribed `@ts-expect-error`
  (`@ts-ignore` is covered, and none is used), `triple-slash-reference`, `no-invalid-regexp` for
  string-built patterns, `no-useless-assignment`, empty or constructor-only classes, and unused
  trailing parameters in the `.mjs` scripts (`tsc` covers them in TypeScript). Biome also has one
  global set, so a browser-only global in a Node script is not rejected.
- **Not applicable.** The compiler's `config`, `gating`, `unsupported-syntax` and
  `incompatible-library` diagnostics: no compiler configuration is in use, and the build does not
  run the compiler.

A suppression carries its reason in the `biome-ignore` comment. Three exist: the timeline's context
read re-runs on the board revision without reading it, the terminal test harness exports nothing,
and one `hasOwnProperty.call` stays because `Object.hasOwn` would change the shipped page.

## Candidate packaging

The core page embeds compiled JavaScript and CSS as base64 data resources. These are packaged
bytes, not HTTP asset downloads. Encoding adds roughly a third to their size, which counts against
the HTML budget. It preserves comparison operators, regular expressions and tagged raw templates
without allowing their text to change the HTML parser's state. A global replacement of `<` would
break operators; replacing only script end tags would miss HTML comment and script parser states.
The browser tests must execute hostile literals, rather than infer safety from a string check.

A data module has its own `import.meta.url`. The build must therefore refuse residual imports,
chunk-relative resource construction and unexpected emitted assets instead of silently resolving
them against that URL. API requests must use the document's Python origin; the typed client layer
must prove that boundary on the served page. Packaging smoke proves the embedded core and served
build identity. The page reads only that origin through the typed client. The existing framing policy
remains in force.

The fifteen packaged font faces and their ranges come from the existing canonical descriptors and
WOFF2 payloads. Their licenses and source records remain packaged. Bundled JavaScript has its own
full license inventory derived from actual compiler module ownership, not the list of development
dependencies. Missing ownership or licenses refuse packaging. Build provenance uses relative paths
and content hashes; release versions, machine paths, timestamps and per-run capabilities do not
enter the artifact.

The optional terminal remains a lazy same-origin exception. Its JavaScript and CSS total 495,775
raw bytes before embedding overhead, which every reader would otherwise download at first open.
There is no measured startup benefit to bundling it. Installed checks distinguish the React core's
offline launch from the existing terminal renderer's local asset and read-only stream checks;
they do not stand in for the React terminal's own browser proof, described under Sessions below.

Python verifies the selected document and license payload against packaged integrity metadata.
That detects missing, corrupt or stale build output. It does not authenticate a local actor who
replaces the artifact and its metadata together. A selected bad build fails before binding;
recovery commands remain available. The legacy page keeps its original bytes throughout
the migration.

## Integrated development

The contributor command owns a Vite worker and the actual foreground Python launcher. Python
serves the document, APIs and SSE; Vite serves modules and hot refresh. Its startup ticket is
read once, and a fresh HMAC challenge binds both exact loopback origins, the worker PID and both
process generations. The shared secret stays in owned IPC and a private startup file, which the
supervisor removes after readiness. This prevents adopting an accidental listener; it does not
authenticate against another process able to read the same user's private files.

Vite's built-in host, CORS, token and filesystem settings do not establish the whole boundary.
They accept extra loopback authorities, and the measured source-directory symlink test escaped
the configured filesystem allowlist. Admission therefore checks exact raw Host/Origin headers
and canonical filesystem paths before Vite dispatch. An unbound public WebSocket dispatcher
receives only admitted upgrades. HMR retains Vite's token check; its token-free ping protocol
still passes the same exact host, origin and path admission.
Python keeps its own origin, framing and capability checks; its routes never proxy through Vite.

All harness and platform data-location inputs point inside the owned scratch tree, and Python
checks the actual resolved collector candidates before starting. Windows retains only the system
directory inputs its socket loader requires. Model calls, quota fetching and native actions are
disabled. Normal development exposes no focus capability; a separate inert fixture verifies
capability transport and refusal without claiming a terminal was raised.

Hot refresh preserves the document's development identity. Explicit Python restart waits for the
old child to close, repeats the worker admission and changes the backend generation and build.
The contributor reloads for that instance. Worker failure stops Python too; interruption, EOF and
failed startup clean only captured children and owned files. Production uses its committed page
and content identity, with no development modules or HMR endpoint.

## Typed client and store

The React data layer lives in `frontend/src/{api,store,transport,storage}` and owns every request,
timer, event stream and browser-storage key the page uses. Components subscribe to one external
immutable store and never fetch, poll, open a stream or touch `localStorage` themselves. A runtime
owner starts and disposes those resources explicitly. It is idempotent under StrictMode and HMR
replacement, aborts only requests it started, closes only streams it opened, and holds the
pending-action registry and the one per-document storage instance for as long as it lives.

The legacy source wins wherever a prose description disagrees with it, because the port must keep
rollback compatible. Measured differences from the first written port map, all resolved toward the
legacy code: the guardrail cap keeps the first fifty valid rules on read and the last fifty on add;
the twelve-hold select deferral resets only when a deferred commit is waiting, never past the cap;
the usage load counts an empty-key entry against its 200 before dropping it; and a real navigation
does not release the leader lease, because the stream reports closed before `pagehide` fires.
The refresh controller, election and revision logic were checked differentially against the real
legacy files over thousands of random schedules with no divergence.

Rules the layer keeps that a green suite does not enforce on its own:

- An action is sent once. A POST is never retried, a second focus press while one is in flight is
  answered locally as throttled, and an empty harness, session or capability sends nothing.
- A refusal, an outage and an unreadable body stay distinct from an empty healthy board, and the
  last accepted data survives a failed read.
- The exact harness and session pair is the identity of a request. The compatibility key
  (`sid`, falling back to the display session) names storage entries only.
- A read of any storage family writes nothing, so a mount or poll cannot trim or rewrite a value
  the legacy page would still accept.

The fixtures under `frontend/test/fixtures/client-contract/` are captured from the real
application and HTTP server with models, quota fetching and native actions off, and a guard counts
that none ran. `python3 scripts/regen_client_fixtures.py` rewrites them and `--check` fails when
the server's answer has drifted. The Python suite regenerates every file and compares bytes, and
the TypeScript suite replays each recorded request and classification, so a backend change breaks
both sides. The standard library's error pages vary by Python version, so an error page is recorded
as its status and the markers it must contain rather than as raw text, and the stream heartbeat is
cut at its first frame so its bytes do not depend on reader speed. Routes that need a model, a
native action or a per-run value are listed with their reason in the index instead of being
written by hand.

Storage conformance runs the real legacy page in Chromium against the real backend, in both
directions for all twelve families. A direction is labelled by what exercised it: the page's own UI,
passive page behaviour, a legacy function run in the page when no reachable control exists without a
model or credential path, or a codec-level check. The receipt counts each kind and does not fold
them into one total.

## React shell, routes and controls

The shell is a separate React page, not a layer over the legacy one. One tree holds the page and
five live regions as siblings, and the regions are never inside the subtree a route replaces, because
a node that arrives carrying its text is the one a reader's software skips. Announcements are
written once per standing key, forgotten when the pending action that caused them ends so the next
press is spoken again, and counted under StrictMode so a double effect cannot repeat one.

Routes keep the released fragment grammar exactly. The router was checked against the real legacy
parser over hundreds of generated fragments, and a browser test drives the legacy page and the React
page in the same Chromium and compares the canonical hash, document title, current navigation item,
breadcrumb, history depth after Back, reload and Escape for every route contract. A bare or malformed
fragment lands on the Sessions view, a retired held-to alias opens its exact session, and an
unknown `from` is dropped. `?all=1` is the only query that widens data, and the retired `next` query
is never read by the page.

Absences are stated. Before the first payload the page says it is waiting, a refresh failure shows
nothing at one failure and a notice naming the retry interval at two consecutive failures, a newer
server build asks for a reload, and no view prints a count it has not measured. Two deliberate
differences from the legacy page: the header says "Waiting for the first board." before the first
payload, where legacy printed zeros that read as a measured empty board, and Retry uses
`aria-disabled` instead of `disabled` so keyboard focus survives its own removal.

Copy briefing announces why it cannot copy (the project is no longer in the payload) instead of blaming
the clipboard. The control that copies a session link, the project briefing, the "Attention updated"
announcement and the notification control are each built in the step that owns the surface they sit on.

Shared controls keep reader state the redraw would otherwise discard. A keyed focus lane restores
the same control or a named fallback without scrolling an offscreen one, a field memory keeps an
unsaved draft, caret, undo and composition across live updates, and an open native select holds the
poll commit for at most twelve consecutive attempts and catches up once on change or blur.
Disclosures keep their node and open state, hold background commits for the 200 ms motion, and skip
the hold under reduced motion. Headless Chromium draws a select's popup outside the DOM, so the
browser proof covers the focus, deferral and catch-up contract around it and picks the option
programmatically rather than reading the popup.

## Sessions, session detail, the timeline and the terminal

The observed model that Sessions, the header counts and session detail all stand on is a full port of
the legacy `next-observed.js`, checked by executing the real legacy file next to it over hundreds of
generated payloads with no difference, and by mutants that show the comparison can fail. The header
counts and the rows come from the same collection, never an authored number. The Sessions screen and
the detail page were compared the same way against the real legacy views over about a thousand seeds,
then in one Chromium against the same board: group membership and order, row text, absence sentences
and the one-step link to each session. A harness whose store could not be read is named, which the
legacy page does not do. A question answer posts one numeric `index`, only a confirmed answer retires
the question, and a second press while one is in flight sends nothing.

The timeline filter keeps `active`, `all` and `decisions` per project and session in the existing
graph-mode storage key, with the caller's choice over the stored one over the default, and the old
empty-scope key dropped. The terminal stays lazy, local and offline: nothing loads before the press,
then exactly the two vendored xterm assets. It is output-only in the strongest sense the legacy page
allows, since the legacy page sends no client frame at all and the server revokes a socket that sends
one, so the browser proof asserts zero client frames while typing, pasting and pressing keys. Its
lifetime follows the exact harness and session, so leaving the route and returning keeps the retained
screen and StrictMode opens one socket. Follow is measured against the live position, not the scroll
maximum, because the legacy page's own textarea rule makes xterm's helper element 44 px tall.

The timeline and the terminal are mounted in the project view's Decisions and Console tabs.

## The Intent log and the Intent panel

The Intent log (`#n=intent`) and the panel on the session page (the goal and expected-outcome editor,
the prompt menu, later directions, Keep, discard and the live monitor switch) are ports of the legacy
`next-intent.js` and the editor half of `next-cockpit.js`. Every pure function was checked by running the
legacy function next to its TypeScript twin over generated inputs, with mutants that show the comparison
can fail; the differential caught one real divergence (a chosen prompt kept past a store that was
switched off). A browser proof serves one board to the legacy page and the React page in one Chromium and
compares the log and each editor state.

The editors are native. A revision announced over the real stream, a poll, StrictMode and an IME
composition leave the node, text, caret, selection and native undo where they were; the proof types, moves
the caret, composes through the debugger protocol and lets revisions land. Unsaved text survives leaving
the route and returning, but the node and its undo history do not, because the Intent view unmounts; that
limit is stated rather than hidden. Nothing is sent by a mount, StrictMode, a poll or a route change, a
save is one POST and never retried, and a save in flight when the reader navigates away is sent once.

What the Analyze step builds on is exported from `frontend/src/intent`: `DirectionQuestion` (Keep settles
through the annotation route until a reading is supplied), `openPendingDirection` for Update intent
instead (one direction read, nothing saved), `intentForReading`, the live monitor switch and the shared
reading-feedback lane. The per-entry Add to my intent buttons of the legacy activity list are drawn by the
Drift step's numbered activity list.

## The Drift card, Analyze and Steer back

The Drift section of the session page (the live and analysis levels, the reading card, Analyze and its
consent, the result, Cancel, Steer back and the departures raised while the reader was away) and the
numbered activity list it cites are ports of the drift half of `next-cockpit.js`. The pure parts (the
reading shape contract, result wording, route and refusal ranking, level, correction arithmetic, the
numbered list) were run next to the lifted legacy source over hundreds of generated cases each; the flip
ledger and job cues are covered by behaviour tests. One browser proof serves a scripted board to the legacy
page and the React page and compares the whole card in every state: no reading, pending, withheld,
completed, failed, cancelling, superseded, a gap and the lane off.

Only an explicit press after consent starts a reading. Mounting, StrictMode, a poll, a reconnect, a route
change, hover, focus and a key press send nothing, and every POST is one attempt that is never retried. One
exception is stated rather than hidden: a Steer back box the reader opened and left unedited composes again,
once, when the record it was composed from changes. That is a deterministic server read of the correction the
reader asked for, never a model call; a closed box and an edited one send nothing. A press sends what the card
it was made on showed: the receiver, both destinations, the model and the revision floor as drawn. Where the
board has moved since (a card can be held while a board arrives), nothing is sent and the card says why: a
changed destination or reader, or the revision sentence. A server refusal of a changed destination answers
with the stated reason and sends nothing more. A refusal on an adopted prompt is drawn from the shared request lane the Keep
action writes. Steer back composes an editable correction (2000 code points) that is only ever copied, never
written to the session; the proof drives typing, caret, selection and native undo through board ticks, IME
composition through the debugger protocol, a paste over the cap, and a pointer held through the click.

Deviations, each recorded rather than hidden. The card, the numbered list and the departures hold the last
board they drew while the reader is in the correction box (untouched or edited), composing, or holding a
pointer on a control they left it for, and say "Updates are paused" instead of the legacy whole-page queue,
because the shell's display gate is wired to open selects. The box keeps its node, caret, selection and undo
for as long as it holds focus; a stale mark that moves it after the reader leaves it remounts the box, and the
words survive but native undo does not. A failed read of the project's observed record says "could not be
read" where the legacy page, which reads only the focused session's record, says "not read yet": the Intent
panel here reads both, and neither sentence is an empty record. Dismissal has no legacy web surface (nothing in
the web assets calls the dismiss route), so none was built.

## Project views, steering and the Console

The Projects list and history, project detail with its workflow plans, the scope tree and switcher, the
recovery briefing, the human-context notes, Now and Course, the workstream panel, the steering bar, local
and workflow-stage tripwires, the Decisions timeline with its lanes and the Console operating rail
(delegation, waiting, capacity as the project page draws them) are ports of the project half of the legacy
page. The pure functions were run next to the legacy source, the whole legacy page loaded in one `vm`
for the project model, over hundreds to thousands of generated boards each, with sensitivity mutants and
non-vacuity floors so a green run cannot be an empty comparison. Two browser proofs serve one board to the
legacy page and the React page in one Chromium: the project views over the list and every project state
(no sessions, stale focus, a failed read, no plan, ended without an end stamp, hostile text), and the
steering, tripwire, Decisions and Console surfaces over a real backend, including the retained terminal.

Drafts and notes are native editors keyed by the exact project or session: text, caret, selection and
native undo survive board revisions, tab changes and a route away and back, and are never reused for
another project, which is the defect the Intent step found. Tripwires and steering text are browser
preferences. They are never sent to a session and the surfaces say they are not enforcement. A stage
condition saves through one explicit POST with the shared 15 second bound, never retried, and a lost or
non-JSON answer says "Could not save the stage condition." The workstream observes the board from the
first payload (the shell starts it) and keeps the legacy collapse key without adopting the old
unnamespaced one; a missing window reads "since this tab opened", never zero.

Deviations, each recorded rather than hidden: Add human context is not offered at a focused session (the
legacy page offered a button that opened an editor nothing drew); the recovery strip, Now and Course build
delegation lanes from the project-scope assignments, where the legacy page read a cache the Decisions tab
happened to seed, while the Decisions tab builds them from the selected scope's own context read, a
focused session's when one is selected, as the legacy page does; a
non-record member of the hierarchy is skipped where legacy throws; the tripwire box takes focus when it
opens and gives it back to its button, and an Enter that commits an IME composition adds no rule; a usage
entry with no harness name states the absence where legacy throws; disclosures use the shared accordion;
panels are plain sections inside the shell's tab panel. Not ported because nothing in the legacy source
calls them: `nextCockpitNowState`, `ActiveDelegation`, `NeedsYou`, `SystemDetails`, `TaskSubject`,
`MemoFields`, `ProjectStatus`, `RecoveryOutcome` and `nextProjectWorkstream`.

## Attention, notifications, capacity and the consent controls

The Attention view (exact-owner asks and checkpoints, gates, risks, outcomes and coverage), the
notification control and owner, the capacity strip, the usage consent and the observer-model consent
controls are ports of `next-attention.js`, `next-notify.js`, `next-capacity.js` and the Console observer
parts of `next-cockpit.js`. The models and text builders were run next to the legacy source over
hundreds to thousands of generated boards, the owner in lockstep over 300 sequences, and two browser
proofs compare the rendered pages in one Chromium and use a scripted `Notification` API: nothing here
ever creates a native notification.

Consent is a press and nothing else. The quota parameter rides `/api/data` only after an explicit yes
answered on this origin and stops when it is turned off; unanswered and declined send nothing and read no
credential, through mount, StrictMode, polls, reconnects, route changes, reload and another tab's storage
event. An answer removed from storage is withdrawn at the next read, where the legacy page kept a copy in
memory alive until reload. The observer-model press names the consent and the offer the reader saw and is
refused locally, with a rendered sentence and no request, if either changed; quota consent never
authorizes it, and a double click sends one request. The notification prompt opens only from its button,
a reload with permission already granted raises nothing for gates already on the board, a native lane
suppresses the browser's, and the lane report is one attempt that names no session. The runtime now says
whether this tab holds the live stream, so only that tab raises a workflow stage banner.

Deviations from the legacy page, recorded rather than hidden: the lane report is sent as soon as the
reader grants rather than at the next payload; a stamp that is not a date prints without a time, where the
legacy Attention view throws and draws nothing; a board that published no session collection says so
instead of printing "0 of 0"; a usage entry with no harness name is drawn with the absence stated; the
unknown reading count clause is dropped where legacy printed "null readings"; answering the usage
question refreshes the board by hand, as legacy did, and focus lands on the new switch instead of being
lost; and Console usage sits in the Console rail where the project page draws its operating rail. A board
with usage but no session collection (the server always publishes one) draws the Sessions view's absence
sentence without the capacity strip.

## Reader state and storage

Each reader-state row specifies stable identity, stored state, retained deferral or a mechanism
that can be retired only after a browser proves it unnecessary. Unmanaged text selection remains
an explicit limit, not an invented guarantee. Native editors may require uncontrolled elements
and refs: replacing a textarea or writing its value can erase undo even when its text looks right.
Open selects, composition, disclosure motion and pointer dispatch retain their tested behavior.

Browser storage remains readable in both directions while the legacy rollback exists. Preserve
key formats, value types, scope, TTLs and bounds, including dormant keys until their retirement is
justified. Unsaved Intent and correction text remains in memory rather than browser storage.
Actions run only after explicit reader presses; mounting, StrictMode and HMR cannot start readings,
clipboard writes, saves or credential-backed usage fetches.

## Fluidity measurements

Measure the assembled production page against controlled small, median and large session cohorts.
Record fixture sizes, page digest/bytes, browser version, platform and sampling method. Use repeated
new-document loads and actual background polls to measure first render, poll-to-paint and long tasks.
Count removed nodes and whether edited/open nodes keep identity. Track listener, timer and socket
counts over repeated navigation, without calling an unobserved metric zero.

Before cutover, compare the same fixtures, browser and method. Set timing budgets from measured
baseline medians with a documented noise margin; bundle growth has its own explicit allowance.
Edited or open nodes must not be replaced by unrelated updates. Resource counts must settle rather
than grow with navigation. A fast component test is not a browser performance measurement.

[The pre-React receipt](frontend-baseline.json) records three complete runs: three first-render
observations and nine poll observations per cohort. The 5/50/250 cohorts are controlled scenarios,
not a measured distribution of real users. Each run starts a fresh browser profile; later cohorts
share that profile and may reuse browser/font caches. Update samples invoke the actual
`nextRefreshPoll` path, not a manual refresh that bypasses its open-select hold. The metric ends
two animation frames after the title marker appears, so it is a frame-boundary proxy rather than
proof of compositor presentation.

The receipt binds the runtime page and both measurement scripts by digest. On the same recorded
machine/browser/method, the timing budget is the baseline median multiplied by 1.5 plus 50 ms.
Core HTML allows 25% growth; packaging accounts separately for the optional terminal. These are
comparison budgets, not cross-platform CI deadlines. Native goal typing kept words, caret and
focus in every run, while its node was replaced. Correction undo and composition remain separate
browser obligations. TCP, EventSource resource counts and retained detached nodes were not measured.

To repeat it, run this command three times with distinct output filenames, after setting
`CARGENTO_BASELINE_CHROME` to the Chrome executable:

```bash
node scripts/frontend_baseline.mjs --output /tmp/cargento-baseline-1.json --samples 3 --navigations 5
```

The probe owns its headless browser/profile and synthetic Python backend. It refuses a busy backend
port, reads no real session stores and disables models, usage and native focus. Compare the complete
reports and their source bindings; an incomplete report or unsupported metric is not a zero.

[The React receipt](frontend-fluidity.json) holds three complete runs of `scripts/frontend_fluidity.mjs`
against the assembled React page, on the same platform, fixtures, browser family and method as the
baseline, composed and judged by `scripts/frontend_cutover.py`. The driver is the baseline driver with
seven differences, listed in the receipt. The React page has no global poll function, so the update
trigger is the page's own 20 second fallback-poll callback, captured from `setInterval` and invoked: the
background-poll path with its open-select and motion deferrals, not a manual refresh. The runs also count
open streams and removed nodes per update, hold an opened disclosure and the prompt select beside the typed
goal, check that native undo survives, and read a second navigation series after a forced collection. A
test holds the shared instrumentation to the baseline's own text apart from the two additions it declares.
A control block re-runs the unchanged baseline driver and page on the same day with the same Chrome, so
machine drift is visible: its medians sit within noise of the recorded baseline.

On 2026-10-09 (Chrome 156.0.8078.12 against the baseline's 156.0.8078.4, a load average near 2 on ten
cores, measured against the final shipped page after the last rebuild) every timing budget passed by a wide
margin. First-render medians were 134.2, 94.2 and 128.1 ms against budgets of 199.1, 159.5 and 192.8;
poll-to-paint medians were 45.1, 46.4 and 63.6 ms against 119.8, 121.4 and 146.4; no run recorded a long
task. Against the legacy page re-run the same day with the same Chrome (control medians of 90.9, 62.6 and
96.5 ms first render, taken under a heavier load of about 5), React's first render is slower by 48%, 50% and
33%, inside every budget, and poll-to-paint is level (45.1, 46.4 and 63.6 ms against 47.3, 47.3 and
64.2). The core page is 1,376,372 bytes against a ceiling of 1,816,276 and the legacy page's 1,453,021,
which is 5.3% smaller; the optional terminal assets (488,663 and 7,112 bytes) are accounted apart, as they
were. The typed goal, an opened disclosure and the focused prompt select kept their nodes through a poll
that changed every row title, and the draft, caret, focus and native undo survived, where the baseline
replaced the goal node on every poll. The cohort polls removed no node; the editor update removed two.

Read the baseline's way, with no collection forced, the page's JavaScript event listeners grow by 37 per
navigation round (1,815 to 2,000 across five rounds through Projects, Attention and Sessions) where the
legacy page held 48, and its node count grows by 531 a round where the legacy page's grew by 583 with no
listeners on those nodes. Timers, intervals, WebSockets and the one live stream stay flat. After a forced
collection before each reading, listeners, nodes and documents are exactly constant (207, 664 and 1) in all
three runs, so the raw growth is detached nodes the browser had not yet collected, not retained ones. The rule
is that resource counts must settle rather than grow with navigation, and retained growth is what matters, so
the settle criterion is evaluated after a forced collection: every counter must be exactly constant across
the five rounds, and a mutation that leaves a count higher after collection fails it. The uncollected series
stays in the receipt as `gc_pending`, round by round beside the legacy page's own, informational and not a
budget. The forced-collection criterion was ruled by the migration lead at cutover review on 2026-10-09,
under the owner's standing delegation; the owner has not reviewed it. The first composition judged the
raw listener series and recorded it as a failed budget, and that receipt was recomposed from its own runs
under the ruling. A later rebuild changed the page, and the runs recorded here were taken against that final
page and judged under the ruling from the start.

```bash
node scripts/frontend_fluidity.mjs --output /tmp/cargento-fluidity-1.json --chrome "$CARGENTO_FLUIDITY_CHROME"
python3 scripts/frontend_cutover.py fluidity --run /tmp/cargento-fluidity-1.json --run … --run … \
  --control /tmp/cargento-legacy-1.json --control … --control …
python3 scripts/frontend_cutover.py check
python3 scripts/frontend_cutover.py check --final
```

Run the first command three times with distinct names, and the unchanged
`node scripts/frontend_baseline.mjs --port 4581 --chrome "$CARGENTO_FLUIDITY_CHROME"` three times for the
control; the driver owns its browser, backend and ports (4581 to 4586, 4594, 4595 and 4597 to 4599) and
refuses a busy one. `check` re-derives every figure and verdict from the embedded runs, so an edited
verdict fails, and it checks the source bindings. `--final` also fails on any gap or failed budget and
requires the receipt to be bound to the page that ships: any later rebuild of the React page changes its
digest and needs measuring again.

## The cutover receipt

[The mapped receipt](frontend-cutover-receipt.json) maps every row of the ownership map (20 parts, 39
surfaces, 17 routes, 45 reader-state rows and 12 storage families) to the React-side proof that stands for
it: a vitest file and test title, a browser proof and its step, a Python test for server code both pages
share, or a fluidity verdict. A row is proven, proven with a recorded deviation (the entry links the
paragraph that records it), deferred to a named owner, or an explicit gap. `python3
scripts/frontend_cutover.py check` fails when a row has no mapping, when a mapped file, title or step no
longer exists or matches more than one step, and when a deviation links a heading that is not there. A
test runs it, so a new surface cannot ship without a mapping and a renamed proof cannot leave a row
quietly unproven. It proves that the named proof exists, not that it is adequate: each mapping was chosen
against the row's contract text, and a reviewer owns that judgement.

A second block lists, for each surface class, the proof for keyboard operation, 320 and 375 CSS px, 200%
zoom (640 CSS px, or the reader's text at 200%) and native editor continuity (undo and composition), says
why a cell does not apply, or records a gap. The receipt holds none: the terminal's Open, Jump to live and
Close controls, the Attention controls and the capacity window rows and consent buttons each have a browser
step that operates them by key.

Every parity proof can run against the shipped `react.html` rather than the development server:
`CARGENTO_E2E_BUNDLE=production` makes the Python backend serve the minified page, `pnpm
test:production:browser` runs all eleven, and CI runs them as the `Frontend production bundle` job in two
shards. The receipt's `production_artifact` block names that runner and job, and `check` fails if either
goes missing from the package scripts or the workflow's steps. The limits it states are these. The controls
proof mounts the controls gallery, a combination of shared controls no one page draws together, so in the
shipped composition those controls are proven through the shell, sessions, project, intent, drift and
attention proofs and not by the gallery's own cases. The storage proof's React side is the storage codec
bundled minified in a browser, not a served page. Three harness-only readings are replaced on the shipped
page by what a reader can observe (the terminal owner's counters become the renderer count and the open
sockets, the console's accepted-board count becomes the count of board answers, and a manual refresh
becomes another tab's revision announcement), and the proofs say so where they do it. StrictMode double
effects exist only in development, so the development run of every proof stays in CI beside the
production one.

The legacy compatibility seam `next-cockpit-compat.js` has no React twin by design. The React timeline and
terminal are native components, so nothing lends them globals, and the file leaves with the legacy page.

## Cutover and final verification

Complete candidate parity, native editor checks, degraded states and measured budgets before the
default flip. Retain an explicit process-level rollback through cleanup, then remove legacy code
only after equivalent coverage exists. Hold releases until the final same-main-build browser,
Python-only install and backend-connected development checks pass.

The default flip is one constant, `DEFAULT_FRONTEND`, which the parser, `build_runtime_config` and
the detached child's argument list all read. The explicit `--frontend legacy` keeps its page,
assets, byte pins and tests until retirement. Tests that launch the legacy page now name the
rollback on purpose rather than lean on a default, and the committed client-contract fixtures pin
`legacy` for the same reason: a change of default renderer must not rewrite their bytes.

Candidate parity runs against the shipped bytes as well as the development server. Setting
`CARGENTO_E2E_BUNDLE=production` makes the shared proof support (`frontend/e2e/support/world.mjs`) start the
Python backend with `--frontend react` and no development ticket, so it serves the minified `react.html`;
the default stays the development server, and a StrictMode-specific assertion keeps running there because
the production build has no double effect. A proof that serves a scratch copy of the tree (a harness
entry, the controls gallery or a deliberate mutation) has that copy packaged with the same `packageFrontend`
the tracked artifact comes from, so it is served a production build too. Measured on a desktop, all eleven
parity proofs passed in production mode with no behavioural difference from development; the harness-hosted
proofs differ from the shipped page in composition, which the receipt's `production_artifact.limits` states.
`pnpm test:production:browser` runs them, and CI runs two shards of it as `Frontend production bundle`.
The two native `frontend` legs share their proofs with a second job, `Frontend proofs`, so no leg runs
every proof in one sitting.

The hold is a tracked `RELEASE_HOLD` file at the repository root. `release_transition.py resolve`
refuses while main carries it, so a fresh release and a resume stop in the credential-free job
before any verifier, tag move or push, and `assert-checkout` reads main again in the publishing job, so a hold
merged while the verifiers ran still stops a resume before the bump, the tag move or `stable`; the owner lifts it by deleting the file in a reviewed pull
request. The release skill owns the procedure.

The Intent and drift study remains paused. Controlled reading fixtures prove frontend parity,
not model accuracy. Earlier failed measurements stay failed. A future study resume must bind the
final runtime again rather than reuse a pre-migration source binding.
