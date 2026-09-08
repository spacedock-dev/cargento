# Operator cockpit × v2: the reconciliation contract

Transient. Delete this file when the reconciliation ships.

Two working designs met. The cockpit prototype (this branch, PR #312) turns the project page
into a recovery briefing with a scope rail and four panels. The v2 refactor (`#314`, on `main`)
rebuilt the same page around identity, stated goal, going on, how things ended and a four-panel
rail, under a contract that the board never asserts more than a source published.

Neither is broken. PR #312's CI was green on its own head with 147 new tests; the branch suite
runs 2537 tests. `main` runs 2433. The conflict is that both implement `nextProjectView`, and
`main` moved out from under the branch after it was written.

The durable v2 rules live in [`docs/design-next-ui.md`](../design-next-ui.md) and
[`docs/design-runtime-architecture.md`](../design-runtime-architecture.md), and the design the
board was built to is at
[`docs/future-ui-exploration/v2-prototype/`](../future-ui-exploration/v2-prototype/Cargento-v2.dc.html).
The cockpit's own review, including the four states it left open, is at
[`docs/probes/project-cockpit/DESIGN_REVIEW.md`](../probes/project-cockpit/DESIGN_REVIEW.md).

## The decision

**The cockpit's information architecture is the project page.** Decided by the captain:

- The **Scope rail keeps the left column.** It is the cockpit's, not v2's.
- v2's four rail panels — **Delegation, Waiting on you, Capacity, Tripwires** — move into
  **Console**, which becomes one coherent operations panel.
- The briefing (`ASSIGNMENT | EXECUTION | COMMAND` plus latest evidence and direction) stays
  persistent above the tab bar, and `Now / Course / Decisions / Console` switch beneath it.

## Rulings

These resolve the consequences of that decision and are binding. They are not open for a worker
to re-decide.

### RC-1 · P3 stays visible at project scope

Moving "Waiting on you" into a tab weakens a promise the board makes:
[P3](../promise-map.md#p3-is-anything-waiting-on-me) is "one queue of everything blocked on you".
Behind a tab it is not.

So the briefing's **COMMAND** column names a session in this project that is waiting on the
reader, with its raise and copy-resume controls, whenever one exists — always visible, never
behind a tab. Console holds the full queue and its detail. **Both silent is a defect**; a test
must assert that a waiting session in the project reaches the briefing.

### RC-2 · The scope rail must widen

No longer optional. The design review measured truncation at 1954px and named it: the rail
renders `PROJE… carge…` and `SE…Cl… i…awaiting y…`. Choosing the rail is choosing to fix it.
A session's harness and a usable fragment of its title must both be legible at 1280px and above,
and the rail must degrade to something readable rather than a column of ellipses below that.

### RC-3 · Omission is not deletion

The v2 refactor's own ruling R1, and it applies again. Every v2 project-detail surface finds a
home in the cockpit; none is dropped because the cockpit did not draw it:

| v2 surface | Where it goes |
| -- | -- |
| Stated goal, its source, and the goal-gap sentence | the briefing's `ASSIGNMENT` column |
| Going on | `Now` — and the cockpit's own duplicate `GOING ON` in Console is removed, not kept alongside |
| How things ended: six outcomes, glyph, git line | `Now`, beside execution — v2 paired them deliberately |
| Observed state changes, with its unattended count | `Course`, which is the same idea already |
| Delegation, Waiting on you, Capacity, Tripwires | `Console` — and Console's own duplicate `DELEGATION` is removed |
| Shared-label caveat | the project identity block, as now |

Where two implementations of the same thing now exist, **keep the shipped v2 one** and delete the
cockpit's duplicate. v2's is the one with tests on `main`, the absence contract applied, and the
measured delegation semantics behind it.

### RC-4 · v2's absence contract answers the review's four open states

The design review closes by naming what needs "a clear state": *registration, missing evidence,
empty history, and unmeasured delegation*. v2 already has the answer, and it is §1: every field
that can be absent renders **the reason it is absent**, never a blank, a dash, a zero, or an
optimistic default.

- terminal not registered → say so, and say what registration would require
- evidence absent → say which reading is missing, not an empty disclosure
- empty history → the window it found nothing in, which is what `changeEmptyText` already does
- unmeasured delegation → `no figure yet` plus the reason, which the v2 rail already renders

Prefer a reason string the model already publishes over a new one. If you must add one, it follows
the same rule and goes in your report.

### RC-5 · The mono/sans split is meaningful

The cockpit is currently almost entirely Space Mono. Under v2, **mono means the string came from
a source; sans means the board is talking.** Section labels, identifiers, timestamps, harness
names and machine-published strings stay mono. Sentences the board says — `Select one exact
session to open its read-only console.`, `Captain not needed`, every reason string — become sans
at 12.5px or larger. Ruling R9 from the v2 refactor is the test: read it aloud, and if it is the
board talking it is a sentence.

### RC-6 · Merge, never rebase

This PR deliberately preserves clkao's three prototype commits and their authorship, and says so
in its body. A rebase rewrites them. Merge `main` into the branch.

### RC-7 · `SECURITY.md` counts are assertions, not prose

The branch's `SECURITY.md` states how many expressions in `cargento_runtime` reach an input
payload, and names the modules. `test_documentation` checks those numbers. After the merge they
are almost certainly wrong: re-derive them from the merged tree rather than carrying them over,
and if the count moved, say why in your report.

### RC-8 · These merged clean and are probably broken anyway

`git merge` reported no conflict in these, and `main` rewrote the views they test. A clean textual
merge that breaks at runtime is a documented failure mode in this repository. Check each by
running it, not by reading it:

`test_next_project.py`, `test_next_delegation.py`, `test_next_controls.py`,
`test_next_workstream.py`, `test_documentation.py`, `scripts/validate_plugins.py`,
`docs/design-reader-state.md`, `docs/design-runtime-architecture.md`.

### RC-9 · Stylesheet regions

`styles.css` carries seven banner-delimited regions with one owner each, from the v2 refactor.
The merge adds two more, in this order after `SESSION`:

```
/* ===== COCKPIT ===== */     the shell, scope rail, briefing, tab bar, panels
/* ===== SUBSTRATE ===== */   project.js: semantic timeline and terminal substrate
```

Edit only your own region, and put your media queries at the end of it. A shared responsive block
at the bottom of the file is how four concurrent sessions collide.

### RC-10 · Byte pins

`tests/test_next_page.py` pins a length and SHA-256 per `APP_PARTS` entry, the same pair for
`styles.css`, and the assembled page; `tests/test_next_flag.py` pins the assembled **length and
digest in two different tests**; `tests/test_focus.py` pins the assembled digest. **Four sites
across three files.** Recompute from the assets by running the oracle, never by reasoning:

```
python3 -c "import hashlib,pathlib,sys; sys.path.insert(0,'cargento/skills/cargento/cargento_runtime/web'); import page; \
d=pathlib.Path('cargento/skills/cargento/cargento_runtime/web/styles.css').read_bytes(); a=page.load_page(); \
print('styles',len(d),hashlib.sha256(d).hexdigest()); print('assembled',len(a),hashlib.sha256(a).hexdigest())"
```

Only the merge session and the final integration session touch them. Everyone else leaves them
alone and does not report them as findings.

## Ownership

`next-cockpit.js` is 1433 lines and holds the scope tree, the switcher, command attention, and all
four panels. It cannot be edited by two sessions at once, so the cockpit work is **sequential**.

| Session | Owns |
| -- | -- |
| **M** merge | every conflicted file, the RC-8 list, the new regions, the pins. No design work. |
| **A1** structure | `next-cockpit.js`, `next-project.js`, the `COCKPIT` region. RC-1, RC-3 folding, duplicate removal. |
| **A2** design | the same files, after A1. RC-2, RC-4, RC-5, the empty `Now` panel, Evidence and More discoverability. |
| **B** substrate | `project.js`, the `SUBSTRATE` region, `test_next_cockpit.py`'s substrate cases. |
| **C** backend | `project_context.py`, `semantic_history.py`, `interaction_prototype.py`, `http_api.py`, `sessions.py`, `observer.py`, `collectors/codex.py`, `cli.py`, `SECURITY.md`. |
| **D** docs | `docs/`, `scripts/validate_plugins.py`, `scripts/serve_operator_cockpit.py`, the PR body. |

B and C run alongside A1. D runs after A2. Nothing runs before M.

## Do not run the full suite

Concurrent suites on this repository manufacture failures that read as regressions: loopback port
binds in `test_http_api`, `subprocess.TimeoutExpired` in `test_lifecycle`, socket timeouts in
`test_quota`. Run only the modules you own. If one of those three fails, re-run that module alone
before believing it, and report both results.
