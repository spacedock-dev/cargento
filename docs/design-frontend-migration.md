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
gated React build state that they are unavailable.

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
build identity, while the unavailable preview has no API client yet. The existing framing policy
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
they do not imply the unavailable React preview already has terminal parity.

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
