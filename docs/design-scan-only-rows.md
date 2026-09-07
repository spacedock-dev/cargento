# Design: a row no event can reach says so

Owner for the decision that `acquisition` **renders** rather than being deleted, for what the six
harnesses carrying it are told to a reader, and for the declared-field-set property that had been
asserted over the wrong object. The module map, including which file owns the stamping site and
which owns the event vocabulary, belongs to
[design-runtime-architecture.md](design-runtime-architecture.md). The two situations Idle covers and
why only an event separates them belong to N-9 in
[design-needs-input.md](design-needs-input.md#n-9-idle-was-two-situations-and-only-an-event-can-separate-them);
this document owns what happens on the screen once the field exists.

## S-1: the field was a disclosure nobody could reach

`Application._mark_unreachable_by_events` stamps `acquisition` with `events.ACQUISITION_SCAN` for
every harness absent from `events.IDENTITY_NORMALIZERS`. Six carry it: pi, copilot, cursor, goose,
opencode and droid. Two docstrings say what it is for. The stamping site's says that without it "an
unmarked row would mean either 'did not finish' or 'cannot be seen from here'";
`sessions.base_session`'s says that a row which cannot carry `finished_at` "says so through
`acquisition` instead".

It said so to nobody. A grep for the name under `cargento_runtime/web/` returned nothing, and the
result on the board was measured before this shipped, with a fabricated payload driving the real
bundle. A Goose idle row and a Claude idle row with no stop observed rendered the same five cells,
character for character (each row is quoted whole, cell separators added):

- `Goose | Goose idle, scan-only | COPY ID ‖ solo/app | Exact location not published ‖ — ‖ — ‖ —`
- `Claude Code | Claude idle, no stop observed | COPY ID ‖ solo/app | Exact location not published ‖ — ‖ — ‖ —`

For the Claude row the absent stop means *did not finish*. For the Goose row it means *cannot be
seen from here*. The reader had nothing to tell those apart, which is the collapse the field was
defined to prevent.

### Rejected: deleting the field

The alternative on the table was removing `acquisition` and the method that sets it, on the grounds
that a disclosure reaching no pixel is dead weight. It was rejected because the code has already
committed to the disclosure in two docstrings and one design record, and deleting the field makes
all three false in the other direction: they would then describe a reading Cargento declines to
take rather than one it takes and hides. The honest repair for a documented disclosure that does not
happen is to make it happen.

## S-2: what the row says, and where

One sentence in the identity cell, beside the unread-source sentence #302 put there and styled with
it:

```
Read by scanning: no turn end can be observed here
```

The identity cell rather than a column slot, for the reason
[design-unread-sources.md](design-unread-sources.md) gives about its own sentence: the fact is about
the whole row's source, not about any one reading, and the two lanes are the row's two arms. It
repeats on the session page's meta line, lowercased, so a reader who clicks through from a disclosed
row does not arrive at a page asserting the state alone.

**Not a `<details>`.** #302 settled this and this sentence does not reopen it: a disclosure the
reader can leave shut cannot qualify a claim already on screen beside it. It adds no row to
[design-reader-state.md](design-reader-state.md) either, because a redraw has nothing to throw away.

**Unconditional on `state`.** The field is a property of the harness, so the sentence is true on a
working row as well as an idle one, and the working arm is where a reader most needs it: that row
will stop, and nothing will tell them that it did. Gating on `state === "idle"` would have made the
sentence appear at the moment it stopped being actionable.

**One exact string.** `acquisition` is published, so it is untrusted. The page renders on
`=== "scan-only"` and on nothing else, because a truthy check prints the sentence for
`"event"` (the value that means the opposite) as readily as for a hostile one. A published
`finished_at` on the same row suppresses it: that combination is unreachable from this server, since
`events.parse` refuses the six harnesses' envelopes outright, but the sentence claims a stop could
not be observed and a stamp beside it would make that false on the reader's screen.

## S-3: `acquisition` is null on the other four, and null is a reading

`base_session` now declares the field for every harness at None, which makes three values rather
than two:

| Value | Reading |
|---|---|
| `None` | The harness has an event adapter and no event has landed on this row |
| `events.ACQUISITION_EVENT` | An event reached this row |
| `events.ACQUISITION_SCAN` | No event can ever reach it |

Declared for all ten and not only for the six that fill it, on the rule `provider`, `model` and
`consumption` already follow in the same function: a key present on only some rows makes every
consumer test for presence rather than for a value. Two tests had been written the wrong way round
against exactly this field, asserting `assertNotIn("acquisition", row)` for Claude, and both now
read the value.

`blocked_since` joined `base_session` in the same change and for the same reason. It was published
by the Claude, Copilot and Cursor collectors only, and it is in `events.PATCHABLE`, which means an
event envelope could add it to a row that had never carried it.

## S-4: the property this rested on was asserted over the wrong object

`tests/test_sessions.py` has a hand-written table of the payload's declared field names, and the
comment beside it says it "is the place that has to be edited" when a field arrives. The assertion
built rows through `sessions.base_session` and compared key sets, so it measured the constructor's
return value and nothing after it. Every field written onto a row later was outside its reach, which
is the whole class `acquisition` and `blocked_since` belong to.

Measured at `5bca94b`: an undeclared key added to every published row in `Application.collect` left
all 2,325 tests passing. So adding a name to the table bought nothing until the assertion reached a
payload.

`PublishedSessionFieldSetTest` is that assertion. It builds each of the ten harnesses' stores in
turn, runs a full collection, and compares the published row's key set to the table. The same
mutation now fails on all ten and names `undeclared_probe`. Beside it, one structural check that
`events.PATCHABLE` is a subset of the table, because no store fixture can produce the row an
envelope patches and that is the half with an untrusted writer on it.

Both halves are kept. The constructor's check is fast and harness-free, and its comment now says
what it cannot see.

### Rejected: a union rather than an equal set

Declaring the two names and asserting `set(row) <= DECLARED` would have passed without changing
`base_session`, and it re-admits by design the defect the table exists to prevent: a name declared
for some rows and absent from others still makes every consumer test for presence. The set is equal
on every published row or the property is not one.
