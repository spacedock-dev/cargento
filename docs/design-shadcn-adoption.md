# Adopting shadcn/ui and Tailwind 4

This record owns what was measured before the frontend moved to shadcn/ui components and a Tailwind 4
stylesheet, the ruling that came out of it, and the rules every layer of the migration follows. The
[frontend record](design-frontend-migration.md) owns what the React page is and how it was held to the page
it replaced; the [reader-state inventory](design-reader-state.md#the-inventory) owns what a redraw must keep.

## Verdict

Go, with conditions. Nothing measured stops the migration layer by layer. With the whole adopted set bundled
and running, the page stays inside every fluidity time budget, every browser proof that was run passes on
macOS, the CSS gates hold with no new exception, and Windows and Linux x64 install and build under the
unchanged policy. Two conditions come with it. The disclosure and popover layers must not merge until the
production drift proof is clean in a Linux container five times in a row, because the full set crashed
Chromium's renderer in that proof (see the gates section) and the cause is not known. And every layer
re-measures fluidity and recomposes the receipt, because the Python suite checks its final form on every pull
request. The work is larger than installing a package: ten things in the tree break or silently misbehave
under a naive install, and each is listed under the finding that exposed it.

The ten, in the order they are met:

1. pnpm writes a supply-chain exclusion for a package younger than its release-age policy instead of refusing it.
2. The `shadcn` command line is 282 packages as a dev dependency.
3. `shadcn init` cannot detect this repository's layout.
4. `shadcn add` installs an unrelated npm package named `cn` and imports it.
5. Two components import a whole icon library for two chevrons.
6. Under the scale reset, default size, radius, animation and data-variant classes generate nothing, silently.
7. Tailwind's `dark:` variant emits a `prefers-color-scheme` rule, and the vendored classes read variables the
   page does not declare; both fail the production CSS contract.
8. Vendored files nothing uses still emit CSS, because Tailwind reads files as text.
9. The development server, the unit-test config and `tsconfig.json` each need the toolchain or the alias
   written into them separately.
10. Biome rejects the vendored files' formatting and their export shape.

Owner rulings: popovers use the shadcn Popover; tailwind-merge is kept; the page is served from the reader's
own machine, so growth in size is accepted and the guard against slowness is time, not bytes. After the
measurement the owner confirmed (2026-10-10) that the component flavour is Base UI and that the fluidity
receipt's byte ceiling is re-based to 2,000,000 bytes, to be raised again if a layer needs it.

## What was measured, and how

Every figure below came from a throwaway branch off `main` at `cde1188b` (never merged) on one machine
(macOS arm64, Node 26.10.0, pnpm 12.9.1, Chrome 156) unless a row says otherwise. The branch added
`tailwindcss` and `@tailwindcss/vite` 4.3.3, `@base-ui/react` 1.8.0, `class-variance-authority` 0.7.1,
`clsx` 2.1.1 and `tailwind-merge` 3.7.0, vendored eight shadcn components (Button, Accordion, Collapsible,
Popover, NativeSelect, Input, Textarea, Label) and rendered each of them, hidden, from the real page so the
bundle carried and ran them. The browser behaviour comparison was run in headless Chromium through
Playwright 1.63 against one small page per library, and the popover and a pending button were repeated by
hand in headed Chrome 156.

## Findings

### Installing under the pnpm policy

`pnpm add` succeeds under `ignoreScripts`, `strictDepBuilds`, `allowBuilds: {}`, `strictPeerDependencies` and
the frozen lockfile, with no build script and no approval. The lockfile carries the Tailwind native packages
for every platform (twelve `@tailwindcss/oxide-*` variants, including linux x64 and win32 x64), so no
platform needs a resolution of its own.

Three things were not what the plan assumed.

- `@base-ui/react` 1.9.0 was published a day before the measurement and is younger than pnpm's minimum
  release age. pnpm did not refuse it: it wrote `minimumReleaseAgeExclude` entries for it and for
  `@base-ui/utils` into `pnpm-workspace.yaml`, which switches the supply-chain delay off for those packages.
  The branch pins 1.8.0 instead (published 2026-09-04) and the workspace file is unchanged. A change that
  adds a `minimumReleaseAgeExclude` line is a change to the security policy and is reviewed as one.
- Adding the `shadcn` command line as a dev dependency adds 282 packages to the lockfile for a tool that runs
  on a developer's machine a few times a year. `pnpm dlx shadcn@4.21.4 <command>` runs the same pinned version
  without touching the lockfile, and was measured to start in 1.4 seconds with the store warm. The procedure
  uses `dlx` with an exact version.
- `shadcn init` stops with "could not detect a supported framework": the Vite config lives in `frontend/`, not
  at the repository root. `components.json` is written by hand (Base UI flavour, `frontend/src/styles/tailwind.css`
  as the stylesheet, `@/ui` as the component directory) and `shadcn add` works from it.

### What `shadcn add` writes

- The registry item lists `cn` as an npm dependency. `shadcn add` therefore added the npm package `cn` 0.4.0
  (published by the shadcn author, 380 KB unpacked, "a drop-in replacement for clsx and tailwind-merge") to
  `package.json` and wrote `import { cn } from "cn"` into every component. The branch removed the package,
  wrote `frontend/src/lib/utils.ts` and rewrote the imports. Every later `add` needs the same two steps, which
  the procedure records.
- Two components import from `lucide-react`, a package of hundreds of icons, for two chevrons. They are two
  inline SVGs in `frontend/src/ui/icons.tsx`.
- Defaults are written for shadcn's own scale: `text-sm`, `rounded-lg`, `h-8`, thirty-two `dark:` classes, and
  `data-open:` and `animate-in` classes that come from `tw-animate-css` and `shadcn/tailwind.css`. Under
  Cargento's scale reset (below) the size, radius and animation classes generate nothing, silently. The branch
  rewrote them with one script (`text-sm` to `text-body`, `rounded-lg` to `rounded-control`, `h-8` to
  `min-h-11`, `dark:` and animation classes removed). The vendored files are Cargento's code after that, and a
  scan test must catch a default-scale class entering one (see the rules).
- `shadcn/tailwind.css` is not imported. It is 16 KB of custom variants, keyframes and scroll-fade utilities;
  the vendored files use two of its variants (`data-open` and `data-closed`), which are copied into the entry
  stylesheet.

### The single-file build and the CSS gates

- `pnpm build` passes: one chunk, one CSS asset, no `@import` and no non-`data:` `url()` in the built CSS, the
  fifteen fonts, and a thirteenth bundled licence (Base UI, its utilities and floating-positioning packages,
  tailwind-merge, clsx and cva) found and written by the existing notices step. The notices step covers
  packages, not copied source: the licence text of the copied shadcn files is not in `react-licenses.txt` and
  has to be added.
- `css.test.ts` fails once, on the Tailwind entry's `@import`. A two-line allowance, for exactly
  `@import 'tailwindcss/theme.css' layer(theme);` and `@import 'tailwindcss/utilities.css' layer(utilities);`,
  is enough, and a third import still fails. The type-size, variable and scheme tests pass.
- `css-contract.mjs` passes in development and production-bundle mode with the inventory of exceptions
  unchanged, once the token bridge is complete. Before that it failed in production mode with five undeclared
  custom properties (`--foreground`, `--secondary`, `--radius-md`, `--accordion-panel-height` and
  `--transform-origin`; the last two are set at run time by Base UI) and with a `prefers-color-scheme` rule
  that Tailwind's default `dark:` variant emits. The bridge declares the missing variables and redefines the
  `dark` variant so it never emits a media query. The contract compares `--ink*` registers as strings only
  (`rgbOf` strips whitespace and nothing more), so any colour form works as long as those registers are not
  redefined.
- It does not check 44 px targets. Several proofs do on the real routes (`controls-continuity.mjs`,
  `capacity-parity.mjs` and others); the contract would need a step to cover the component gallery.

### Cascade, layers and the terminal stylesheet

Tailwind puts utilities in a cascade layer, and an unlayered rule beats any layered one, so the thirteen
hand-written sheets were wrapped, mechanically, in `@layer legacy { ... }` below the `theme` and `utilities`
layers. Preflight is not imported: the UA defaults that the exact-set exceptions rely on (`offScale`,
`uaLinks`, `uaFocusRing`) do not move, which the unchanged inventory shows. The terminal stylesheet is
loaded at run time from `/assets/xterm.css` and is unlayered, so it now beats the layered page rules wherever
they overlap; the terminal proof passes in both bundle modes. An overlap that matters would be a regression in
how the terminal host looks, which a proof about behaviour does not measure, so the layer that touches the
terminal checks it by eye.

### Source detection

Tailwind reads files as text, not imports. With the default settings it read all thirteen vendored files and
emitted 27.7 KB of utility CSS for components nothing used. Boundaries work: `source(none)` plus
`@source '..'` and `@source not` globs for tests, the gallery and stylesheets removes it (1,609,020 bytes
against 1,609,756 for the page with eight used components). Vendoring each component in the layer that first
uses it, and deleting one with no importer, keeps the scan honest.

### Scale and tokens

`@theme { --text-*: initial; --radius-*: initial; --color-*: initial; }` followed by the five type steps, four
radii and the semantic colours mapped onto the existing tokens as hex works: a default `text-sm` generates
nothing. shadcn's own `--accent` and Cargento's `--accent` are different things (a hover surface and a lime
colour), so the semantic names are reached only through `--color-*`, and plain `--foreground` and
`--secondary` are declared because the vendored classes read them directly.

### tailwind-merge

Kept, as ruled. Unconfigured it reads Cargento's type steps as colours: `twMerge('text-body', 'text-muted-foreground')`
returns only `text-muted-foreground`. shadcn's own `cn` package has the same behaviour. The branch configures
`extendTailwindMerge` with the five steps and four radii, and a test reads the theme names from the entry
stylesheet and fails if a step or radius exists that the configuration does not know, and a real conflict
(`p-2` then `p-4`) still resolves.

### Flavour

React Aria (`react-aria-components` 1.22) and Base UI were compared in Chromium on the four things Cargento
depends on. Base UI is the choice. The detail is in the table.

| Behaviour | Base UI 1.8.0 | React Aria 1.22 |
|---|---|---|
| Pending button stays focusable, ignores click, Enter, Space | yes; `aria-disabled` set, no `disabled`; app supplies `aria-busy` and any announcement | yes; `aria-disabled` set; announces the button's own label assertively only when focused; no `aria-busy` |
| Closed section revealed by same-document fragment navigation | yes with `hiddenUntilFound` (`beforematch` fires) | yes, always on |
| Same, on a fresh load of a client-rendered page | no | no |
| Open popover with a polite live region beside the app root | live region stays exposed in every modal mode; focus can be left on the trigger; portal can mount in a given container | default modal mode makes the live region `inert`, so announcements are lost; fixable only with `isNonModal`, which loses the stock dialog focus handling |
| Controlled open state | follows an external store exactly; one change callback per click; never writes back | follows; writes back an out-of-range value through its own callback |
| Raw JS, Button, Button plus Accordion, plus Popover (over react-dom alone, 219,486 bytes) | +7,857, +22,762, +113,348 | +37,191, +42,725, +96,532 |

Both fail a deep link on a fresh load because the page mounts after the browser's fragment pass; the page has
to re-apply the hash after first render if it wants one. In headed Chrome 156 `window.find()` did not reveal a
closed section; the browser's own find bar could not be driven by the available tooling, so the in-page find
claim rests on the fragment-navigation behaviour and is not confirmed with the real bar.

### Cost in time

Three fresh fluidity runs per page on the same machine, base page against the page carrying the adopted set:

| | Base page (1,376,448 bytes) | With the adopted set (1,609,756 bytes) |
|---|---|---|
| First render median, small / median / large cohort | 145.5 / 95.7 / 127.8 ms | 149.1 / 95.0 / 127.8 ms |
| Poll to paint median, small / median / large | 45.7 / 46.1 / 63.2 ms | 45.5 / 45.5 / 63.3 ms |
| Long tasks | none | none |
| Budgets (first render, poll to paint) | pass | pass |
| Resource counts after collection | constant | constant |

The page grew by 233 KB and first render moved by at most 3.6 ms, inside the run-to-run spread. The byte
ceiling in the fluidity receipt (1.25 times the replaced page, 1,816,276 bytes) was a proxy for that cost; the
time budgets are the guard. The owner re-based the ceiling to 2,000,000 bytes, which keeps the proxy as a
tripwire and leaves room for the display components that may still be adopted. A layer that would cross it
raises it in its own pull request, with its measured times.

### Tooling

- Biome: the vendored files fail formatting (shadcn writes double quotes) and fail
  `useComponentExportOnlyModules` for the variant helpers they export next to components. One override for
  `frontend/src/ui/**` turns that rule off, and `biome format --write` on that directory is a step after every
  `add`.
- TypeScript 6 rejects `baseUrl` (deprecated); `paths` alone resolves the `@/` alias. With `skipLibCheck: false`
  the new packages' types check cleanly.
- The owned development server (`frontend/dev/vite-worker.mjs`) creates its own Vite server with
  `configFile: false`, so it needs `tailwindcss()` and the alias of its own; without them every
  `@/ui/...` import returned 500 and the development proofs timed out. The unit-test config
  (`vitest.config.mts`) needs the alias too. Three configs, one alias.
- jsdom 30 needs no polyfill for Button, Accordion, Popover or NativeSelect (seven tests, no warnings).
  NativeSelect keeps `document.activeElement.tagName === 'SELECT'`.
- Linux (arm64 container, Node 26.10): `pnpm build:check` reproduces the macOS artifact byte for byte,
  `pnpm test` passes (1,439 tests) and `pnpm typecheck` passes.
- Continuous integration on the throwaway pull request (the three platform legs of the frontend job): the frozen
  install takes 5 seconds on Windows, 6 on macOS and 2 on Linux, under the unchanged policy; the clean preview
  build takes 3, 1 and 1 seconds; the canonical rebuild on Linux x64 reproduces the tracked artifact byte for
  byte; the owned development lifecycle tests and the Python plus Vite hot refresh proof pass on all three.
  The unit-test step took 159 seconds on Windows (110 on macOS, 113 on Linux) against a step limit of 180, so
  the Windows margin is 21 seconds and shrinks with every added test.
- Windows found one defect in the branch's own test change: the allowance for the Tailwind entry compared a
  relative path with a forward slash, and Windows reports a backslash, so the narrow `@import` allowance did not
  apply. The comparison normalises separators now. Any new path comparison in a test needs the same care.

### Gates that were run on the branch

Dev and production-bundle `css-contract.mjs`, terminal, controls, shell, sessions and intent proofs (all
pass), the owned development lifecycle tests and the Python plus Vite development proof (pass), and the whole
vitest suite (1,432 tests at the time). The full proof set was not run on the branch.

### What the gates already require, and what broke

- `scripts/tests/test_frontend_cutover.py` runs `frontend_cutover.py check --final` against the committed
  receipts, in the Python suite, on every pull request. Any change to the page therefore turns the Python
  jobs red until the fluidity receipt is re-measured and composed again. The earlier assumption that only the
  release hold reads the final form was wrong. Every layer re-measures three times (about 45 seconds on this
  machine) and recomposes; `compose` does not carry the embedded legacy control block over, so the layer
  restores it, and this should be one command.
- On Linux the production-bundle drift proof crashed Chromium's renderer ("Target crashed", then every later
  step failing on `about:blank`) in 7 of 13 container runs (three of six with the container's shared memory raised
  to 2 GB, so it is not shared memory) and in 2 of 2 runs of the pull request's Ubuntu production job, with the
  full adopted set bundled and rendered. The unmodified page passed 5 of 5; Tailwind
  alone passed 5 of 5; the light components (Button, Input, Textarea, Label, NativeSelect with tailwind-merge)
  passed 5 of 5; the set with Accordion and Collapsible and without Popover passed 5 of 5; the set with
  Popover and without Accordion and Collapsible passed 5 of 5. The same proof passed on macOS. The cause is not
  known: no single component reproduces it, and only the full set does. It is a risk the disclosure and popover
  layers carry: each runs the production drift proof repeatedly in a Linux container (five clean runs) before
  its pull request opens, and the first layer that reproduces the crash finds its cause before merging.

## What each pattern becomes

| Pattern | Decision | Reason |
|---|---|---|
| Button, link-as-button | adopt Button; links use `buttonVariants` on a plain `<a>` | Base UI Button always sets `role="button"`, which would hide a link |
| Pending button | adopt, `aria-disabled` and `aria-busy` kept, ghost label kept | Base UI keeps it focusable; `aria-busy` and the announcement are Cargento's |
| Disclosure, accordion variant | adopt Accordion and Collapsible with `hiddenUntilFound` | needs the reactive store first; state precedence is specified in that layer |
| Disclosure, popover variant | adopt Popover (owner ruling), non-modal, initial focus left on the trigger | live regions must stay exposed |
| Disclosure, menu variant | keep native | not dismissed by Escape by design; not a popover |
| Select | adopt NativeSelect; keep it a real `<select>` | `displayGate` defers polls while a native select is focused |
| Textarea, input | restyle with Textarea and Input classes; stay uncontrolled | native undo and composition |
| Tabs (`ProjectTabs`) | decided in the project layer after a test of automatic activation and modifier keys | hand-rolled roving tabindex over the route |
| `role="status"` banner | Alert only if it stays polite | Alert defaults to an assertive role |
| `<progress>`, `title` tooltips | keep native | nothing gained; hover-only text is worse on touch |
| Badge, Card, Separator, Empty | adopt where a hand-written equivalent exists, for consistency | owner brief; vendored in the layer that uses them |

## Rules every layer follows

1. One stack. Each layer changes `react.html`, so layers land in dependency order from one stack, each rebuilt
   from a clean `node_modules`. Every layer re-measures fluidity three times and recomposes the receipt, because
   the Python suite checks the final form on every pull request, so each layer's page is release-qualified when
   it merges. The release hold stays. A merged layer that regresses is reverted by its own pull request and its
   receipts reconciled.
2. Keep public APIs: `Disclosure`, `ActionButton` and `HeldTextarea` keep their props.
3. Own the code. A component is vendored into `frontend/src/ui/` in the layer that first uses it, tuned to
   Cargento's scale, with a header naming the upstream component, the CLI version, the registry source and a
   hash of the upstream file as fetched (the registry serves each item as JSON, so the hash is the hash of its
   `content`). Upstream MIT licence text for copied code ships in `react-licenses.txt`. A vendored file with
   no importer in shipped code is deleted. After every `add`: remove the `cn` package it adds, rewrite the
   `cn` import, run `biome format --write frontend/src/ui`, and run the scale rewrite.
4. Native stays native where the reader-state contract needs it: the held select, the uncontrolled textarea,
   `title`, `<progress>`, the live regions, and the menu disclosure variant until a ruling changes it. Each is
   a recorded decision with its reason.
5. A layer deletes the CSS it replaces in the same layer and moves the gate edits with it (size, focus,
   absence, target size, exact-set exceptions, mutation fixtures); the pull request shows each gate still
   failing against a mutation that removes the rule.
6. A layer re-points the proofs for what it moves to roles and `data-slot`; no new class-name selector enters
   a proof.
7. No new type size, colour space or motion outside the existing tokens. A scan fails a default-scale class
   (`text-sm`, `rounded-lg`) and an arbitrary font size in a component, because under the reset they would
   silently style nothing. A hand-written CSS ratchet records the exact byte total and its counting rule, fails
   when the actual total differs, and a CI check fails when the record rose against the pull request base.
8. Adoption follows the owner's brief: use the shadcn component wherever a hand-written pattern has a
   corresponding one, for consistency, unless it cannot keep a reader-state contract. Each layer is held to the
   fluidity time budgets and the proofs.
9. Review tier: the form-control layer gets full adversarial review (typed words); the disclosure and popover
   layers get two lenses plus an arbiter; others follow `AGENTS.md`.
10. Each layer runs `sync-docs` and updates the documents its change makes false.

## The pull request procedure for a component

```bash
pnpm dlx shadcn@4.21.4 add <component> -y
pnpm remove cn                                  # the registry lists the npm package `cn` as a dependency
sed -i 's#from "cn"#from "@/lib/utils"#' frontend/src/ui/<component>.tsx
pnpm exec biome format --write frontend/src/ui
pnpm build && pnpm build:check
```

Then run the scale rewrite, add the upstream header, add the gallery entry, and delete the CSS the component
replaces.

## What was not verified

The browser's find bar, any screen reader, Firefox and WebKit, touch, and the Windows and Linux x64 timings
outside what the pull request's CI legs recorded. The full browser proof set was not run on the branch.

## Toolchain layer

The first layer adds Tailwind 4.3.3, its Vite plugin, clsx and class-variance-authority. No component,
`cn`, Base UI or tailwind-merge is introduced. The thirteen sheets gain only an outer `legacy` layer;
their rule bodies are unchanged. The entry imports theme and utilities without Preflight.

Scanning all of `frontend/src` emitted utility rules from ordinary words such as `hidden` and `filter`
despite there being no utility callers. The entry therefore scans `ui/**/*.{ts,tsx}` and
`lib/**/*.{ts,tsx}`, excludes tests, the gallery and stylesheets, and uses `source(none)`. A later layer
adds an explicit source glob for any utility caller outside those directories. Nothing is vendored in
this layer. `frontend/build/style-policy.mjs` rejects a vendored module unreachable from the shipped
entry through runtime imports, exports or dynamic imports with literal targets (including template
literals without substitutions). Type-only imports and unreachable modules do not qualify; imports inside `if (false)`
still count. It scans TS and TSX strings outside tests for default scale classes and arbitrary font
sizes, using the pinned Tailwind compiler to distinguish font sizes from colors. Custom variants in
the excluded entry may contain selectors and `@slot;` only; declarations are refused.

`frontend/css-budget.json` records 161,464 bytes and its counting rule. Count UTF-8 bytes after CRLF
to LF normalization, including comments, across every CSS file under `frontend/`, except the
directive-only Tailwind entry. Strip only the mechanical outer `@layer legacy` wrapper. The record
inventories paths; a new sheet outside that inventory fails. Ordinary rules in the excluded entry
fail separately, so moving a rule there cannot hide it. The actual total must equal the record.

CI compares the record with `github.event.pull_request.base.sha`, fetched with full history, and
refuses an increased count or an added counted path. When introducing the record, it derives the
allowance from the base's actual sheets instead of trusting the new record. An implementation PR
cannot grant itself an increase. An owner-approved increase requires a separate reviewed baseline
change, with the justified rules and matching record, landed using an explicit required-check
override; subsequent layers use that new base. There is no label or head-side opt-out in the gate.

The package includes the configuration, entry and any later vendored files in provenance. Copied
shadcn source gets the full upstream MIT notice in `react-licenses.txt`. The component CLI procedure
and upstream-header fields are in [Contributing](../CONTRIBUTING.md#adding-a-shadcn-component).

Measured on 2026-10-10: the page grows from 1,376,448 to 1,376,752 bytes, an increase of 304. JavaScript
stays byte for byte at 701,374 bytes; CSS grows by 229 bytes for layers and bridged variables, with no
utility rules and no imports in the built CSS. Three fresh fluidity runs pass every budget, retain
native editor state and settle resource counts after collection. The historical legacy control is
preserved by `python3 scripts/frontend_cutover.py remeasure`, which first checks the clean build and
leaves the previous receipt untouched if measurement fails.

All development and production proofs pass on macOS, including the owned development worker and
terminal's first asset load. Both CSS bundle modes keep the exception inventory unchanged across
87 views. Linux arm64 reproduces the artifact and passes all twelve production proof commands plus
an extra production drift run. Five deliberate mutations fail: default type scale, arbitrary font
size, an unused vendored module, CSS growth and a rule hidden in the excluded entry. Native Windows
was not run here; the separator normalization is tested, and the unit-test step now allows six
minutes against the spike's measured 159 seconds.

## Button layer

The first component layer vendors Base UI Button with the pinned registry procedure, adds Base UI
1.8.0 and tailwind-merge 3.7.0, and introduces `frontend/src/lib/utils.ts`. Its merger knows the five
type steps and four radii. Tests compare those names with the entry stylesheet, so an added theme
step requires an explicit merger update.

All 46 button elements use Button. The ten anchor elements stay plain links with `buttonVariants`;
no link is rendered through Base UI. Surface-specific tabs, switches, filters and row layouts keep
their own rules through the native variant. ActionButton keeps its public props. Call sites name
their weight explicitly; the wrapper no longer translates deleted shared class names. Surface chrome is expressed by variants and props.

A pending button owns its keyboard and click handling. Base UI's focusable-disabled path cancelled
Escape and the shell shortcuts as well as activation, so Button keeps the native node enabled,
emits `aria-disabled` and `aria-busy`, and suppresses only clicks, Enter and Space. Escape, Tab and
the shell shortcuts remain uncancelled. The unit test checks both halves. An inert action that
must explain a refusal still delivers its press to the handler. The busy label sits over a hidden idle label in an absolute overlay, so the old
answer button's measured growth from 94.23 to 114.63 px is gone. A caller's explicit reserve still
holds a wider busy label at rest and while pending. This verifies exposed ARIA state, not screen-reader announcement.

The shared chrome, copy and raise states, terminal button chrome, answer padding and busy rules
are removed from the sheets. The CSS record falls from 161,464 to 153,203 bytes. The component
gallery includes default, hover, keyboard focus, pending, disabled, retry, long text, primary, quiet
and linked actions, plus an explicit width reservation. The initial adoption measured the gallery at
1280 and 320 px in both bundle modes, alongside real-route type, ring and target checks. The
correction is checked in development; production verification follows the stack-head rebuild.

The target floor stays at 44 CSS px, as in the replaced rule. A first attempt using Tailwind's
rem-based spacing step made the Console tab at least 88 px wide at 200% text size and overflowed
the 320 px shell by one pixel. The shell layout proof caught it; the fixed pixel floor lets text
and padding grow without doubling the minimum width of a tab.

Recorded-answer normalization ignores the shared utility classes and Base UI's redundant native
button role and default tab index. It still compares semantic surface classes, explicit roles,
nondefault tab order, text, targets and action attributes. The recorded fixtures are unchanged.

The utilities layer beats `legacy` regardless of selector specificity. The correction audit moved
conflicting surface chrome into Button variants and props, including menu rows, capacity windows,
memo controls, consent, muted actions, waiting-card padding and Raise refusal borders. The
[call-site audit](design-shadcn-button-audit.md) lists the ownership decisions.
`css-contract.mjs` compares every button instance on its real routes with a computed-style table
from `30bac258`: colour, background, four borders, display, padding, alignment and font. Mutating
the shared ink makes this gate fail. The gallery separately checks memo chrome, the solid retry boundary and both amber Raise
refusal states. The quiet pending border now stays solid on all four sides, preserving its 118.38 px resting width instead
of shrinking to 116.38 px with a bottom border only. The spinner is an inline SVG arc in place of
the CSS border spinner. Both changes are deliberate; neither changes the request or its label.

The fluidity receipt records three runs on 2026-10-10 that pass the unchanged budgets. Core HTML
is 1,436,780 bytes against the 2,000,000-byte ceiling. For 5, 50 and 250 sessions, first-render
medians are 143.7, 93.8 and 126.1 ms, and poll-to-paint medians are 43.1, 44.8 and 59.7 ms. The
receipt retains the historical legacy control; no timing allowance changed.
