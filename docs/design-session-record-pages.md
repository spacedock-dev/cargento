# Reading a session's record in pages

A week-long session can leave only one prompt inside the 400,000-byte transcript
tail because images and tool output fill that allowance. The record list needs a
reader-requested backward page, independent of the durable semantic history.
Opening the session requests its newest fifty entries. Each Show more press asks
for another page. The server retains no page or transcript bytes between requests.
The [runtime architecture](design-runtime-architecture.md#r-1-one-responsibility-per-file-and-the-launcher-owns-none)
owns module placement and dependency direction.

## Route contract

`GET /api/session-record` takes `project`, `session` (`harness:sid`), `limit`
(default 50, clamped to 1 through 50), and optional `before`. The handler applies
the project-context loopback, origin and bounded identity guards, matches exactly
one collected session in that project, and resolves its existing transcript.
It requests no model, analysis, workflow evidence or whole-message text.

The response contains `session`, `entries`, `next`, `reached_start`, `bound`,
`scanned_bytes`, `kinds`, and `state`. Entries are the existing semantic facts,
ordered by descending `at` and ascending `fact_id`, at most `limit`. They use
the same fact builders, redaction, 112-character title ceiling, copied-correction
marking and `for_page` removal of server-only fields as project context. Merge
them by `fact_id`. `kinds` is always `["user_message", "agent_message"]`:
checks and workflow facts remain in their bounded project-context sources.
Claude pages include user and top-level agent messages. Codex pages include user
messages; the existing `AGENT_MESSAGE_HARNESSES` builder does not admit Codex
assistant records. This route does not expand that builder's content contract.

Each message entry also carries `ordinal`, its fixed number: its rank among every message in the
session, oldest first. It is published only when the message index has read the transcript to its
end, and an entry the index does not hold carries none. The [fixed positions](#fixed-positions)
section owns how it is computed.

An `ok` page has a non-null `next` until it consumes the record down to byte zero.
`reached_start` is measured by consumption, including the oldest line, rather
than defaulted from an empty result. `bound` is `bytes` or `time` only when the
scan stops short of both the requested count and the start. An image-filled
page with no entries can still have a continuation. `scanned_bytes` counts the
actual file bytes read by the page reader, including reread boundary fragments;
it does not include the ordinary collection used to match session identity.

`state` is `ok`, `stale`, `unsupported`, or `unavailable`. Other harnesses are
unsupported. Unknown or ambiguous project/session matches and missing sources
are unavailable. Non-ok responses carry no entries or continuation and report
`reached_start: false`; they have established no record boundary. A client must
discard its cursor on `stale` and restart at the newest page. It must not retry
unsupported or unavailable responses as empty records.

## Byte cursors and allowances

Configuration owns `RECORD_PAGE_MAX_BYTES` (64 MiB) and
`RECORD_PAGE_MAX_SECONDS` (5 seconds). Both were 16 MiB and 2 seconds until 2026-10-13, when the
owner raised them to match the press's own 64 MiB read: a page that has to cross a screenshot-heavy
stretch to reach what a reading cites then needs fewer requests. Reads use 64 KiB chunks and stop after
finding the requested count, without scanning the rest of the file. The time
allowance is checked before each chunk and each decoded line. A blocking local
filesystem operation or a single decode must return before that check can run
again; the allowance is not an operating-system I/O cancellation deadline.

The opaque cursor is authenticated with a random key owned by this server. It
names a source identity digest, device, inode, the latest observed size and
modification time, backward offset and boundary-discard flag. Length, charset, authentication,
canonical encoding, integer range and offset range are checked before seeking.
The key carries no session information and no page cache; restarting the server
invalidates old cursors. Cursors do not contain a filesystem path or message text.
Another file, a replacement, a shorter file, or a same-size modified file answers
stale, including shrinkage after an earlier append. Append-only growth preserves the original snapshot end, so new records do
not appear among older pages. A same-inode rewrite followed by growth cannot be
distinguished from an append by these stamps; the harness's append-only contract
is required. A source changed during the request is checked again before reply.

Chunk-boundary fragments are joined before decoding. A chunk with no line boundary in it is held and
joined once with the others when a boundary or the start arrives; joining each one as it was read
re-copied the growing partial line every time, so a single 20 MiB line cost 1.8 seconds and a 65 MiB
line spent the whole 5-second clock at 33 MiB, which would have left Show more retrying the same line
without ever discarding it. Invalid partial final lines
are ignored, as they are by the existing context builders. At a byte-bound stop,
the unconsumed boundary line is reread with the next request's fresh allowance.
A single line larger than a whole allowance is skipped through its delimiter,
across as many requests as necessary, so a large image cannot trap Show more.
This also limits an oversized message record: a message encoded in a line larger
than 64 MiB cannot be recovered by these pages (a press, which keeps its own 16 MiB line limit, skips
a message line over 16 MiB). This is a bounded source reader,
not a guarantee that arbitrary-size JSON records can be decoded. Pagination
follows file order and sorts each returned page by time; it does not sort an
unread portion of a transcript whose timestamps disagree with file order.


## Shared reads for Intent actions

`scan_source` shares this reader's chunks, line boundaries and regular-file
identity checks with the direction and prompt lookups. It has no cursor, retains
no page, and supplies each complete line to a private visitor inside the clock
allowance. Unlike a page cursor, an Intent read requires the exact stamp to remain
unchanged, including size. It never stops at the first match: a conflicting source
identity later in the consumed allowance must still be able to refuse the words.
The direction and opening-source allowances, reason tokens, measured costs and
limits belong to the [long-session Intent contract](design-reading-a-session.md#long-session-direction-and-prompt-reads).
A `POST /api/direction` batch feeds every requested id through one such walk,
sharing its allowance and file-stamp checks without retaining source words on the
server. Each id is checked for conflicting copies throughout the consumed range.
The linked Intent contract owns the request bounds and ordered result shapes.
Record pagination and its public response remain unchanged.

## Why semantic history could stay thin

Synthetic failing-first tests proved that age pruning and the 512-event project
cap can remove a source's facts while keeping its size/mtime scan marker. The
unchanged-source fast path then returns zero bytes indefinitely. Another
failing-first test proved that label and canonical git-key callers create
independent buckets for the same collected project. These reproduce the failure
mechanisms; no live transcript or prompt corpus was copied or used to establish
which mechanism produced the owner's particular store.

A read-only, count-only inspection on the same date found two directions for
the focused session in the git-key bucket and twenty-two in its label bucket.
Both scan markers used schema 5 and carried no coverage digest. This confirms
the split buckets and unverified markers in the live store, without proving
which earlier eviction or pruning event left the key bucket thin.

Backfill markers now bind the digest of the retained source event identities.
Lost, legacy or mismatched coverage earns a full bounded rescan, including when
the source has grown. A scan may advance an incremental marker only if the store
still holds the prior coverage it read against. Its expected coverage is checked
against the events retained after merge, eviction and age pruning. A zero-byte
skip never mints another marker; an empty forgiving scan is not proof of a read.
The backfill schema moves from 5 to 6 so old markers earn their coverage again.
Failed writes and unreadable or over-cap stores cannot authorize a skipped read.

Unambiguous display labels use the collected canonical project key, merging
legacy label events and invalidating their old scan claims. A display label used
by distinct keys cannot join them. The history's existing 24-hour and project
bounds remain. Conservative invalidation can cause repeated bounded rescans when
the requested coverage exceeds those bounds. This repair does not replace the
store's per-runtime lock with a cross-process transaction, enlarge its read cap,
or change what Analyze drift reads. Project context's history merge, workflow
joins and semantic projections still consume that bounded store; the paged list
does not depend on it.

## Reading the newest end again

The first page is a snapshot of the record's newest fifty message entries, and the board's own context
carries only what lies in the newest 400,000 bytes of the transcript, plus a bounded number of agent
messages. A page left open on a working session therefore saw a message arrive through the context and
then lose it when large tool output moved the tail past it, though the record still held it. Measured on
2026-10-14: the list rose from 66 to 74 entries and fell back to 66, eight entries lost, all of them
absent from the opening snapshot and from the context's facts and present in the record, which grew
from 96 to 105 messages.

The page now asks for the newest page again when the session's published activity changes. The route
and its cursors are unchanged and the server retains no records: the byte cursor already binds a snapshot
end, so an append never shifts an older page, and a request without `before` is the newest page. The
page merges what comes back by `fact_id`, leaves the older cursor and paging state alone, and never
drops an entry it holds. When more than one page arrived since the last read it follows older pages
until the newest page meets an entry it already holds, up to 20 pages, and past that starts again from
the newest entries and says so. [Reader state](design-reader-state.md#the-inventory) owns the rule.

## Fixed positions

The page used to number what it held, so a number moved when a check displaced another, when a check
ran again, and when Show more loaded an older page. The owner ruled on 2026-10-14 that an entry keeps
its place in the session instead. The server publishes it and the page draws it.

`entry_numbers.py` holds one `MessageIndex` per transcript: the time and fact id of every message,
kept sorted, nothing of what was said. A pass reads forward from the last consumed byte through the
last whole line, reading each line through `record_pages._fact`, the reader the record pages use, so
the index and the pages cannot disagree about what a message is. It reads in title-only mode: the
fact id hashes the 112-character title and never the full text, and masking a 256 KiB single-word
message took minutes in the first build, which hung the collection that calls the index. A transcript only gains records at
its end, so the index is extended from the bytes appended since and the pass is paid once. A shrunk
or replaced file resets it, a last record still missing its newline is numbered as a page reads it and
read again whole on the next pass, and a line over 16 MiB is skipped to its delimiter. A page parses a line up to its 64 MiB budget,
but masking a message that size takes minutes and this pass runs on every collection of the
focused session, so a message on a line between the two is listed by a page without a number and
no other number depends on it. The pass has its own allowance
(`entry_index_max_seconds`, 5 seconds, the record page bound), and an index that has not reached the
end of the file publishes nothing, because a partial rank is a wrong number. The cache holds at most
`entry_index_limit` (16) transcripts.

A message's number is its rank by `(time, fact id)`. A check or file is `(m, k)`: the number of the
message it follows (messages at or before its first call) and its place among every check, file and
launch the transcript read holds with the same anchor, by `(first call, key)`. The tally counts
candidates whether the listing of twelve keeps them or not, so an eviction leaves a gap and moves
nothing. A failed check that a later pass covers, and a check that has only run in the background,
leave the listing and keep their place for the same reason. The first call is the earliest of a check's own runs, a file's first write, or a launch's
time, which is what keeps a re-run check at its first place. The project context publishes
`ordinal` and `ordinal_sub` for the focused session only; the record pages and the focused
context's message facts publish `ordinal`.

Measured on 2026-10-14 with a generated 62,922,526-byte transcript of 2,344 records, 781 messages
and 40,000-character tool results between them: the first request built the index in 0.18 seconds,
and the next request, over an unchanged file, in 70 microseconds. A test over a generated 60 MiB
transcript holds the first pass inside the record page bound.

Known limits. A file rewritten in place to a larger size under the same inode is not noticed as a
replacement, so its index keeps the old keys until it shrinks or is replaced; a transcript only
appends in every harness read so far. A message written late with an earlier time takes its place in the middle and moves
the ones after it. The check tally reads the newest 8 MiB of the parent and subagent transcripts, so
where an older check lies beyond it the labels of the oldest listed entries can change. A check
that came from a subagent transcript is anchored by its time among the parent's messages.

## Reading for a finished press

A reading cites what its press read, and a press reads further back than the board's tail-bound
record holds. When an analysis this page watched ends by storing a reading, the page reads older pages
for the session with the same route and cursors until every cited entry is one it holds, the record
reaches its start, or the record holds an entry from before the intent's window opened. It stops on a
page that fails or moves nothing, after 20 pages (1,000 entries), and when the reader leaves, which
aborts the page in flight. A second press while it runs shares the run. Nothing else, no poll and no
reload, asks for it. [Reader state](design-reader-state.md#the-inventory) owns the rule and its stops.
The server is unchanged: each page is an ordinary request with the ordinary allowances and retains
nothing.

## Measurements

Measured locally on 2026-10-12, with a generated 61,021,280-byte JSONL fixture:
300 synthetic user records, sixty 1,016,000-character image payloads, and 120
compact records at each end. No real prompt text was used. Measurements call the
page reader directly and exclude fixture creation and identity collection.

| Page | Entries | File bytes read | Seconds | Stop |
|---|---:|---:|---:|---|
| Newest | 50 | 65,536 | 0.003166 | Count |
| Second | 50 | 65,536 | 0.002227 | Count |
| Third, entering images | 37 | 16,777,216 | 0.085692 | Bytes |
| Fourth, deep in images | 16 | 16,777,216 | 0.085460 | Bytes |
| Fifth | 16 | 16,777,216 | 0.085906 | Bytes |
| Sixth | 50 | 12,218,209 | 0.065146 | Count |
| Seventh | 50 | 15,937 | 0.002119 | Count |
| Oldest | 31 | 6,087 | 0.001270 | Start |

The table above was taken at the earlier 16 MiB and 2-second allowances. On 2026-10-13, at 64 MiB and
5 seconds, a page over 100 synthetic 1,016,000-character image lines read its 64 MiB in 0.12 seconds and
stopped on bytes, and a single synthetic 65 MiB line reached the same stop in 0.02 seconds, where it had
spent 5.0 seconds on time before the join was made linear. A single 20 MiB line read in 0.04 seconds.

All eight pages together yielded all 300 identities, each once. The 2-second
allowance leaves headroom over the measured deep page while bounding work on a
busy machine. Byte and clock stop tests establish continuation independently of
these timings. Tests also cover chunk and page boundaries, privacy and fact
parity, copied flags, file changes, cursor authentication, both supported
harnesses and unsupported sources. Mutation checks caught a dropped boundary
join, default-true start, missing bound continuation, unmasked titles and a
removed stale-source guard.

## Rejected alternatives

- A forward cold scan of the whole file at every open spends work and reads
  information before the reader asks for it.
- Enlarging `tail_bytes` increases every ordinary collection's cost and still
  cannot make a finite tail cover a week-long session.
- Caching server pages retains information after the request and introduces
  invalidation and memory costs the list does not need. The message index is not
  this: it holds a time and a hash per message and nothing the reader wrote.
- Numbering the loaded entries on the page, one integer sequence, moves every number
  below a change: when the twelve checks reshuffle, when a check runs again and when
  an older page loads. That was the behaviour before the fixed positions.
- One integer sequence over messages and checks together cannot hold still, since
  the checks are chosen by rank and a new one can leave the listing; a check is
  numbered by the message it follows instead.
- Paging by timestamp cannot uniquely place equal-time records and cannot hold
  a stable boundary when timestamps arrive out of order. Byte offsets can.
- Putting checks in pages would mix independently bounded child and workflow
  evidence into the parent transcript's message record and broaden its contract.
