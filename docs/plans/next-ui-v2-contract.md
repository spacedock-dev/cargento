# next-UI v2 — the shared contract

Transient. Delete this file when the refactor ships.

The target design is the prototype committed alongside it:

- [`docs/future-ui-exploration/v2-prototype/Cargento-v2.dc.html`](../future-ui-exploration/v2-prototype/Cargento-v2.dc.html)
  — the full UI: Projects, Project detail, Session detail, Sessions (Session operations), Attention.
- [`docs/future-ui-exploration/v2-prototype/cargento-observed.js`](../future-ui-exploration/v2-prototype/cargento-observed.js)
  — the data shape every view reads, with the derivation rules.

The prototype is a design artifact, not code to port. Do not copy its markup into
the app. Take from it the view structure, the column sets, the exact label
wording, the colour semantics, the type scale, and the empty-state sentences.

Where this contract and the prototype disagree, the **prototype wins** for
visual and copy decisions; this contract wins for architecture and process.

## 1. The board never asserts more than a source published

This is the governing rule of the whole refactor and the reason it exists. Every
field that can be absent renders as an explicit reason, never as a zero, a dash,
an empty string, or an optimistic default.

- `"No pending step published"` — not `"—"`, not blank
- `"Harness does not report blocks"` — not `"No blocks"`
- `"Title not published"` — not the session id as a fallback title
- `"Exact location not published"` — not the repo name guessed from a path
- `"no figure yet"` + the reason it is absent — not `0%`
- `"Waiting on one complete token-rate window."` — the reason, stated

A derived number that rests on partial data is prefixed with `≥` and carries the
reason in the same block (see the delegation figure: `≥99%` with "≥ because two
sessions have no closed working interval in the retained window").

Any new copy string added during this refactor follows the same rule. If you
cannot name the source that published a value, the UI says so instead of showing
the value.

## 2. Denominators are derived, never authored

Every count in a sentence must be computed from the same collection the rows are
rendered from. This was a real upstream defect (DRC-4453): a project row's
session total and its state words had different denominators. Do not reintroduce
it.

Concretely: the Attention brief's "5 of 12 sessions carry a subject", the
header's running count, the counters strip, and the per-project count line must
all resolve from one session collection in one derivation pass. If a subject is
not a session (quota pressure, identity collision), it is counted in a
**separate** group with its own heading — never folded into the session
denominator.

## 3. Colour carries observation status, not importance

Four inks, and each one means exactly one thing:

| Token | Value | Meaning |
| -- | -- | -- |
| `--accent` | `#c6e07a` | observed, and fine |
| `--amber` | `#e8b45c` | observed, and wants you |
| `--clay` | `#e08a6a` | observed, and the outcome was bad |
| `--ink3` | `#9b9484` | nothing was published |

Unknown never gets colour. That is why Antigravity rows read quieter than Claude
rows — not because they matter less, but because nothing was reported about them.
Do not tint an unknown state to make a row look consistent.

Capacity bars are the one place where the rule needs care: the bar colour follows
**pace against the window's own clock**, not the percentage used. 25% used at
13.3× pace is clay; 81% used at 1.0× pace is amber. High usage on schedule is not
an alarm.

Backgrounds are never tinted. A left border rule may be tinted; a fill may not.

## 4. Type and contrast are fixed

```
--bg      #14140f    ground
--panel   #1c1c16    raised
--sunk    #11110c    inset (right rail)
--line    #2c2c23    hairline
--line2   #403f33    active hairline
--ink     #f4f1e8    primary        ~15:1 on --bg
--ink2    #c9c4b4    secondary      ~9:1
--ink3    #9b9484    tertiary       ~6:1
```

Rules that must hold after the refactor:

- Every sentence is **12.5px or larger**. 10px is permitted only for uppercase
  mono labels and inline metadata.
- No body text below `--ink3`. There is no fourth ink step — if something needs
  to recede further, it needs less prominence in the layout, not dimmer ink.
- Nothing readable is set in a dim tint of the accent. Text on any tinted ground
  is full-opacity `--ink`.
- Fonts: Space Grotesk for prose and headings, Space Mono for identifiers,
  labels, numbers, timestamps and machine-published strings. The split is
  meaningful — mono means "this string came from a source", sans means "this
  sentence is the board talking".

## 5. Milestone honesty

Anything not shipped is labelled as absent rather than drawn as if it works:

- **C4** (stated goals) — goals render as whatever a harness publishes, with a
  line saying how many sessions publish none. No normalisation.
- **C1** (tripwires) — the tripwire panel says "local only · nothing enforces
  these" and holds entries in browser state. Do not wire it to a backend.
- **C6** (irreversible actions) — not on the board. It appears only in the
  "Not on this board yet" list.
- **F3** (attention accounting) — delegation is per-project, not aggregated
  across the week.
- **E5** (unpushed commits) — the board reports uncommitted work only.

The Attention view ends with a "Not on this board yet" list for exactly this
reason: a gap must read as a gap, not as good news.

## Coordinator rulings

These resolve conflicts inside the source material. They are binding on every
workstream and are not open for a worker to re-decide.

### R1 · The prototype is not a feature inventory

The prototype omits surfaces the shipped board already has: the browser
notification control, the refresh-failure notice, the history-reset notice, the
vendor-quota disclosure copy, the SSE/leader live indicator, subagent rows, task
lists, MCP tool-name shortening, and the source-coverage disclosure on session
detail. **Omission from the prototype is not permission to delete.** This
refactor ships no new capability and removes none. If a shipped surface has no
home in the v2 layout, keep it and say so in your report — do not drop it.

### R2 · The fixture's own authored numbers are defects, not specification

`cargento-observed.js` violates §2 in four places. Reproduce its *wording*;
derive its *numbers*:

| Fixture | What it does | What the runtime must do |
| -- | -- | -- |
| `vals.riskNote` in the `.dc.html` | `D.risks.length + ' of 12 sessions'` — `12` is a literal | derive the denominator from the session collection |
| `counters[2]` | `["EXACT REQUESTS", 0, …]` — `0` is a literal | count exact requests from the collection |
| `counters[3]` | `["REPORTED BLOCKS", 0, …]` — `0` is a literal | count reported blocks from the collection |
| `COVERAGE.observed` / `.quiet` / `.gates` | authored sentences, despite the comment claiming derivation | compose from the derived collection |

A literal `12` next to a derived `risks.length` is precisely DRC-4453. The
fixture is a design mock; treat its hardcoded values as placeholders it could
afford and the runtime cannot.

### R3 · `--accent-dim` is a permitted ink

`--accent-dim` (`#8ea254`) measures **6.55:1 on `--bg`**, above the `--ink3`
floor of 6.13:1. §4's "nothing readable in a dim tint of the accent" bars
alpha-composited tints (`color-mix`, `opacity`), not this token. The prototype
uses it for text in three places and it is legible in all three. Do not
introduce any *other* accent tint for text.

### R4 · Keep the embedded fonts

The prototype pulls Space Grotesk and Space Mono from the Google Fonts CDN. The
app embeds pinned base64 WOFF2 subsets so the page stays one self-contained
response with no second asset surface. Keep the embedded fonts; take only the
family/weight choices from the prototype.

### R5 · Light mode is dropped

The board is dark-only after this refactor. The light `:root` palette and the
`@media(prefers-color-scheme:dark)` override both go; the v2 tokens become the
single palette. `--warn` and `--alert` are replaced by `--amber` and `--clay`
respectively, and every existing usage migrates.

### R6 · Byte pins are off-limits to the view workstreams

`tests/test_next_page.py` pins a SHA-256 and a byte length per `APP_PARTS` entry,
the same pair for `styles.css`, and a digest of the assembled page;
`tests/test_next_flag.py` and `tests/test_focus.py` pin that assembled digest
again. **Workstreams A–E must not edit those three files.** Every worker
recomputing them would conflict with every other worker, and each side would be
correct for a tree that no longer exists. The coordinator recomputes all of them
once, in the integration pass.

The scaffolding pass is the one exception: it runs alone, before A–E, and owes
them a green baseline, so it recomputes every pin it moves.

### R8 · One stylesheet, delimited regions, one owner each

`styles.css` stays a single file — it is named by eight call sites across the
tests, the harnesses and `scripts/lint_embedded.py`, and splitting it buys less
than the ripple costs. Ownership is enforced by region instead. The scaffolding
pass lays down these banners, in this order:

```
/* ===== FOUNDATION ===== */   tokens, reset, type scale, fonts   · scaffolding
/* ===== CHROME ===== */       tabs, breadcrumb, live note, nav   · integration
/* ===== PROJECTS ===== */     projects list + project detail     · B
/* ===== RAIL ===== */         the project-detail right rail      · C
/* ===== SESSIONS ===== */     session operations                 · D
/* ===== ATTENTION ===== */    attention                          · E
/* ===== SESSION ===== */      session detail                     · E
```

Edit only your own region. **Put your media queries at the end of your own
region**, not in a shared responsive block at the bottom of the file — a shared
block is a guaranteed conflict between all five of you. Never move a rule
between regions; if a rule looks misfiled, say so in your report and leave it.

### R7 · Do not run the full test suite

Concurrent suites on this repository manufacture failures that read as
regressions — loopback port binds in `test_http_api`, `subprocess.TimeoutExpired`
in `test_lifecycle`, socket-read timeouts in `test_quota`. Run only the
`test_next_*` modules you own. The integration pass runs the suite once.
