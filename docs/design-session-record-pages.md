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

Configuration owns `RECORD_PAGE_MAX_BYTES` (16 MiB) and
`RECORD_PAGE_MAX_SECONDS` (2 seconds). Reads use 64 KiB chunks and stop after
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

Chunk-boundary fragments are joined before decoding. Invalid partial final lines
are ignored, as they are by the existing context builders. At a byte-bound stop,
the unconsumed boundary line is reread with the next request's fresh allowance.
A single line larger than a whole allowance is skipped through its delimiter,
across as many requests as necessary, so a large image cannot trap Show more.
This also limits an oversized message record: a message encoded in a line larger
than 16 MiB cannot be recovered by these pages. This is a bounded source reader,
not a guarantee that arbitrary-size JSON records can be decoded. Pagination
follows file order and sorts each returned page by time; it does not sort an
unread portion of a transcript whose timestamps disagree with file order.

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
  invalidation and memory costs the list does not need.
- Paging by timestamp cannot uniquely place equal-time records and cannot hold
  a stable boundary when timestamps arrive out of order. Byte offsets can.
- Putting checks in pages would mix independently bounded child and workflow
  evidence into the parent transcript's message record and broaden its contract.
