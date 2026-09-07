# Design: a source the board could not read says so

Owner for the fourth state of a store read: **opened, and nothing in it recognised.** The module
map, including which file owns each collector and which owns the read-only SQLite helpers, belongs
to [design-runtime-architecture.md](design-runtime-architecture.md); this document owns the decision
to publish that state on the row, the two branches that were rejected, how far the disclosure
reaches per collector, and (since U-5) what a raise inside a collector costs.

## U-1: there were four states and the page rendered three

A collector's read of a SQLite store lands in one of four places, and only the first three had a
rendering:

| The read | The row |
|---|---|
| Opened, everything recognised | The readings, as measured |
| Would not open | The collector's own `return []` or `return None`, so no row or a bare one |
| Opened, a reading raised | Swallowed per reading, so the row keeps the rest. True of every collector only since U-5 |
| **Opened, nothing recognised** | **Identical to the third, and silent** |

The reader's version of that fourth row is sharper than a missing value. Measured on the board with
a fabricated payload driving the real bundle:

- A row whose store yielded nothing, with a stale mtime, rendered
  `Antigravity | Title not published | trio/app | Exact location not published | — | — | —`.
- The *same* store read, with a fresh mtime, rendered `NOW · WORKING` and `generating…`.
- A session that had genuinely done nothing rendered exactly like the first.

So the blank-row framing the issue was filed under is the idle arm of two, and the working arm is
the worse one: `generating…` is a positive claim about work nobody observed.

## U-2: `store_errors` reaches no reader, so a published field was required either way

This is the measurement that settles the design regardless of which branch is taken.
`io.record_store_error` writes into `state.store_errors`, and that dict is read only by
`diagnostics.diagnose`, which only the `--diagnose` path calls. It appears in no `/api/data` key,
it never sets the payload's `harness["error"]` (only an exception escaping `collect` does), and a
grep for it under `cargento_runtime/web/` returns nothing.

So "route the fourth state through the store-error boundary" is not a fix that reaches a screen. It
relocates the silence.

## U-3: the disclosure is a published per-row field, for all five SQLite collectors

`sessions.base_session` declares `source_gaps`: the readings this row's collector could not take
from a store it opened, by name, from the `UNREAD_*` vocabulary in the same module. Empty means "no
unread reading reported" and never "the store held nothing". The page renders it as
`Source not fully read: <names>` in the row's identity cell, on the live lane and the history lane
both, because those are the two arms above, and repeats it on the session page's meta line.

Five collectors open SQLite: `antigravity.py`, `copilot.py`, `cursor.py`, `goose.py` and
`opencode.py`. The other five read files. All five report through this one field, which is what makes
the sentence one sentence rather than five.

| Collector | What it discloses | What it does not |
|---|---|---|
| `antigravity.py` | Both rungs of the `steps` ladder spent: message history and token accounting | A subagent store's own failure, which costs the parent a slice of its rate and is not the parent's source |
| `copilot.py` | `assistant_usage_events` absent, on every row the store feeds: token accounting | A missing `session-store.db`, which is not a store that half-read. An unopenable one does disclose: the open is lazy, so the failure lands at the `SELECT` |
| `cursor.py` | The `meta` query raised, the `meta` rows decoded to no object, the model read raised, the gate read did not settle | An open that failed, since there is then no source to have half-read |
| `goose.py` | `messages` raised, `usage_ledger` raised | The per-message JSON parse, which loses one message rather than a reading |
| `opencode.py` | The `message` read raised, the `part` read raised | An empty `session` table, which the select ladder cannot tell from a healthy empty store |

A list of names rather than a boolean. "Something could not be read" is not actionable, and a bare
`False` would mean both "nothing failed" and "this collector never looks": null's job done by
false, one field over from the DRC-4101 shape `events.py` names.

### Rejected

- **Routing it through the store-error boundary, the way `copilot.py` records a schema miss.** It
  would withdraw a title and a workspace that were correct, and it would overturn a decision
  `cursor.py`'s `_meta` already records against exactly that: *"routing that through the store-error
  boundary would withdraw a title and a workspace that were fine."* Two collectors had recorded
  decisions cutting opposite ways on the same question, and a harness-agnostic mechanism has to
  reconcile them rather than pick a side.
- **Deciding it per collector.** That preserves by design the inconsistency the issue was filed
  about. The field is declared for every row in `base_session` for the reason that comment gives: a
  key present for only some harnesses makes every consumer test for presence rather than for a
  value.
- **A `<details>` disclosure.** One the reader has to open is one they can leave shut, and this
  sentence qualifies a claim that is already on screen beside it. It also adds no row to
  [design-reader-state.md](design-reader-state.md), because a redraw has nothing to throw away.

## U-4: two readings a disclosure must not claim

**An empty store is not an unread one.** `cursor.py` reports the `meta` rows decoding to no object,
and stays silent when the query returned no rows at all, because a chat whose first message has
not landed has nothing to recognise yet, and disclosing there would print on every new Cursor
session forever.
That distinction needs a discriminator: three facts used to collapse onto one all-empty tuple out of
`_meta` (the open failed, the query raised, the query returned rows none of which parsed), so
`_meta_fields` now reports whether any row decoded to an object at all. What `parsed` separates is
"no row decoded to a JSON object" from everything else, not "unrecognised" from "not yet filled
in", which is a finer cut than it can make. A `meta` table whose rows *do* decode to objects but
carry keys this build does not recognise stays silent: measured, renamed keys publish
`source_gaps []` with title null and state working, which is U-1's fourth-state row still open.

**A memoized empty reading needs a memoized disclosure.** `_meta` is memoized by mtime across four
cache keys, all-or-nothing, and the "recognised nothing" case is on the memoized path, so a
disclosure computed only on a cache miss would appear once and then go quiet for the store's whole
mtime, which is precisely as long as the wrong row is on screen. The gap text rides the second slot
of the model cache key, which was unused (`""`). A fifth key would have been the tidier layout and
is the wrong trade: `state.cursor_metadata_cache`'s value type lives in a module the collector does
not own, and the disclosure has to travel with the reading it is about.

## U-5: a raise costs the smallest unit it invalidates, and rows already read survive

Owner for the third row of U-1's table, which was a generalisation two collectors did not honour.
`cursor.py` kept the row and emptied the reading, `copilot.py` kept every row and emptied only the
consumption, and `goose.py` returned nothing at all. Three answers to one question, tracking the
order the three were written rather than anything about their stores.

The rule, now the same in all five:

| Where the raise happens | What it costs | What it never costs |
|---|---|---|
| Inside one row's build | That row | The rows already built, this store's or a sibling's |
| Outside a row's build (the connection, the session select, the classification pass) | That store | Every other candidate store for the harness |
| Anywhere | Nothing | The harness. `harness["error"]` is not a rendering of a bad row |

### What the two escapes cost, measured

Against `origin/main` at `5bca94b`, driving a full payload collection with `sessions.base_session`
raising on the fourth row of a six-session store, and reading the counts off the payload rather
than off the collector:

| Arm | Before | After |
|---|---|---|
| Goose, `ValueError` on one row, two stores (3 + 6 sessions) | 0 rows published, harness badged `ValueError: ...`, **no store error recorded** | 8 rows, no badge, one store error against the damaged store only |
| Goose, SQLite error on one row | 0 rows, no badge, one store error | 5 rows, no badge, one store error |
| OpenCode, `ValueError` on one row | 0 rows, harness badged | 5 rows, no badge, one store error |
| OpenCode, SQLite error outside the message guard | 0 rows, harness badged | 5 rows, no badge, one store error |

The first arm is the one that shows why the harness must never be the unit. An exception escaping
`collect` is the only thing that sets `harness["error"]`, and `collect` accumulates across candidate
stores, so one malformed row in one store took a healthy store's three sessions with it *and* left
nothing recorded anywhere. A badge is a claim about the harness; one row is not evidence for it.

### Why the row, and not a field

`cursor.py` and `copilot.py` withdraw a *reading* because their reads are separable and they know
which one raised: `_meta` can name the model read as the failure and keep the title and the
workspace, and `_usage_rows` is a read no row's identity depends on. `goose.py`'s and
`opencode.py`'s per-row bodies are one straight-line build, where an exception says nothing about
which published field is wrong. So the granularity differs because the code differs, and the two
collectors are not being reshaped into their siblings. The four now answer the same question at the
finest grain each can honestly name.

### Why the disclosure is a store error and not a `source_gaps` name

The row is gone, so there is no row to carry a gap. `io.record_store_error` is what is left, and
U-2 measures how thin that is: `--diagnose` is its only reader. It is recorded anyway because the
alternative is a session that vanishes from the board with nothing said anywhere, and retention
bought with silence is the failure mode the fix was supposed to remove. Closing the gap between
"recorded" and "on a screen" is not done here and is not pretended to be.

### Rejected

- **Publishing a thin row in place of the one that raised.** Nothing survives the raise to identify
  it (`sessions.base_session` is the last call in both bodies, so the harness, id and project
  fields would be invented), and U-1 already measured what an invented row renders as:
  `NOW · WORKING` and `generating…`, a positive claim about work nobody observed.
- **Keeping the three collectors deliberately different.** Defensible only if the difference tracked
  something about each harness's store. It tracked authorship order.
- **A narrow `except (ValueError, TypeError)`, matching the class the issues name.** That list was
  measured to be the wrong shape of answer: `opencode.py`'s loop `try` carried no `except` at all,
  so a SQLite error raised outside its one inner guard escaped too. Enumerating what a row body can
  raise produces a list that goes stale the first time a callee changes, and the cost of being wrong
  is a badged harness. The catch is broad and the scope is narrow instead.
