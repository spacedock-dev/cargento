# Design: what counts as a harness row

Owner for the question "is this one harness or two?". The registry's mechanics (the `HarnessSpec`
contract, the failure boundary, why no collector raises a popup) belong to
[design-runtime-architecture.md](design-runtime-architecture.md) R-5; this document owns the
judgement calls about which products get their own row, and records the one case where that judgement
had to be revisited.

## H-1: a row is a product a user can name, not a store format

Adding a harness is cheap by design: a module under `collectors/` and a row in
`default_harnesses`. The cost that is not cheap is a wrong row, because the row is what the user
sees. The harness key reaches `/api/data`, the label draws the chip and every session badge, and the
order draws the strip. A row that groups two things the user thinks of separately is a lie told ten
times a minute on a dashboard whose whole job is telling you what is running.

So the test is the user's vocabulary, not the parser's. Two stores in different formats are one row
when a user would name them as one product; one store is two rows if a user would name two.

## H-2: Gemini CLI and Antigravity were one row, and retirement ended that

Antigravity CLI writes per-conversation SQLite stores inside the Gemini home. Gemini CLI wrote JSONL
transcripts under `~/.gemini/tmp`. They were collected as one row, and the reasoning was written into
the collector:

> One registry key covers both source families: legacy Gemini CLI JSONL transcripts and current
> Antigravity CLI per-conversation SQLite stores. They share a discovery result, an error boundary
> and a display label, so they are one collector rather than two.

Under H-1 that was defensible while both were Google's current coding-agent surface: a user signed in
to Google, saw one vendor, and the two formats were an implementation detail of that vendor's
migration. The clause that carried it was "they share a display label".

Gemini CLI stopped serving consumer accounts on 2026-06-18, and Antigravity CLI succeeds it for those
users. The shared label stopped being true at that moment, and the failure was not subtle: every live
Antigravity session rendered under the name and logo of the product it had replaced. The Gemini half
was the quieter half, because a consumer machine's stores stop growing and so surface only under
`?all=1`.

That is not the same as the harness being gone, and the distinction matters here rather than only in
`COMPATIBILITY.md`, which owns it: enterprise Code Assist and API-key authentication were explicitly
unaffected, so Gemini CLI still writes `~/.gemini/tmp` for those users. The split below is therefore
better justified than a pure-history reading suggests. One row would mislabel not just old
transcripts but live enterprise sessions.

They are now two rows, `gemini` and `antigravity`, with two collector modules. Three things made the
split cheap, and they are worth noticing because they are the shape of a good seam:

- The store layer had never merged them. `config.py` always resolved `gemini.tmp` and
  `antigravity.root` separately, and `--diagnose` always reported them as two paths.
- The two arms shared no private helper. The Antigravity block used protobuf and log readers; the
  legacy arm used the Gemini JSONL transcript analyzers. The split was a move, not a rewrite.
- The four plugin manifests already described "Gemini, Antigravity" as two harnesses, so the split
  made the shipped description true rather than requiring the byte-identical five-way edit that
  changing it would have meant.

The Gemini row stays rather than being deleted. A machine that ran Gemini CLI keeps its history, an
enterprise or API-key machine is still writing to it, and deleting a collector is the one change in
this area that cannot be undone by a user.

### Why not relabel the single row instead

Renaming the row to Antigravity was the smaller diff and was rejected: legacy Gemini sessions would
then have carried Antigravity's name, which is the same defect pointing the other way, and the
published key `gemini` would have kept describing Antigravity data. It also would have forced the
manifest-description edit that the split avoids entirely.

### Why the legacy row keeps Gemini's icon and Antigravity has none

The star is Gemini's mark and belongs on Gemini's data. Antigravity renders its `AG` monogram, the
same fallback Pi and Droid already use, because borrowing another product's logo is worse than
showing two letters, and inventing one is worse still.

## H-3: the presentation table and the registry are one contract, tested as one

The page's `HARNESS` table in `web/spark.js` and the Python registry are two hand-written lists of the
same set, and nothing connected them. A label changed on one side only passed the entire suite, which
is exactly how a retired product's name could have survived this split.

`test_the_harness_table_matches_the_registry_in_key_order_and_label` now executes the page script under
node, dumps the table, and compares keys, labels and order against `default_harnesses`. A companion test
requires every row to carry a unique two-letter monogram, since that is the icon fallback and a
duplicate makes two badges ambiguous. Both were mutation-checked against a renamed label, a duplicated
monogram, and a dropped row.

Order is part of the assertion because registry order is chip order.

## H-4: harness counts are stated in prose, so they drift

Ten rows are described in about fifteen places across the README, the shipped skill body, the design
docs, a page comment and a test docstring. Nothing derives them, so every count is a claim a reader
can find wrong.

The split turned up two that had been wrong since they were written: `design-runtime-architecture.md`
described the original monolith as holding "ten harness collectors" when it held nine, and a plan doc
counted eight. Both had been contradicted elsewhere in their own files the whole time.

The rule that follows: a count next to a harness list is part of the list. Change one, check the
other, and treat a count that disagrees with `default_harnesses` as a defect rather than a rounding
of it. Counts describing a past state stay as they were: `design-session-identity.md`'s "nine
collectors each derived the project label their own way" is history, and correct history.
