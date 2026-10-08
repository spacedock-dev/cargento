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
Python process starts. A request or URL never selects the renderer. Legacy remains the default
until the candidate passes the complete parity and measurement gates. Unported routes in the
gated React build state that they are not available in the React interface yet and name the later
step by what it brings, never by a tracker key, because that text ships in the page.

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
they do not imply the React page already has terminal parity, which a later step owns.

Python verifies the selected document and license payload against packaged integrity metadata.
That detects missing, corrupt or stale build output. It does not authenticate a local actor who
replaces the artifact and its metadata together. A selected bad build fails before binding;
recovery commands remain available. The default legacy page keeps its original bytes throughout
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

Named for later steps rather than missing: the control that copies a session link arrives with the
sessions step, the "Attention updated" announcement with the Attention step, the notification
control with the notification step, and the project briefing with the project view. Until the
briefing exists, pressing Copy briefing announces that it is not available in the React interface
yet instead of blaming the clipboard.

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

Not mounted yet, and named: the timeline and terminal components are built and proven in their own
browser harness but sit in the project view's Decisions and Console tabs, which the project step owns,
so no route shows them today. The capacity strip belongs to the Attention step, the Intent and drift
panel to the Intent step (the session page shows a stated slot), and the last-reply and
recovery-briefing text lives in the project Console.

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

## Cutover and final verification

Complete candidate parity, native editor checks, degraded states and measured budgets before the
default flip. Retain an explicit process-level rollback through cleanup, then remove legacy code
only after equivalent coverage exists. Hold releases until the final same-main-build browser,
Python-only install and backend-connected development checks pass.

The Intent and drift study remains paused. Controlled reading fixtures prove frontend parity,
not model accuracy. Earlier failed measurements stay failed. A future study resume must bind the
final runtime again rather than reuse a pre-migration source binding.
