# Pushback session fixtures

Seven Claude Code sessions in which the person steered the agent back after it drifted. Each one has
a goal the person set, an outcome, drift that is visible in the transcript, and a steering message.
They are reference material for the Intent and drift work: what drift looks like in a real session,
and what the person typed when they noticed it.

```
tests/raw_sessions/<session_id>/
    steering-excerpts.txt     committed: every message the annotation cites
    <session_id>.jsonl        gitignored: the full sanitized session log, local only
    <session_id>/subagents/   gitignored: its subagents' logs, sanitized the same way
tests/annotated_sessions/<session_id>/
    annotation.md             committed: the goal -> drift -> steering map
```

## What is committed, and what is not

The full session log stays on the machine that made it. Teammates are not comfortable having
session transcripts in a public repository, even sanitized, so `.gitignore` excludes every
`*.jsonl` under both directories. Only what each annotation needs is committed:

- `steering-excerpts.txt` holds every message an annotation row cites, with pushback marked. It
  contains only the person's typed messages and Claude's reply text, never tool calls or tool output.
- `annotation.md` holds the overall goal and outcome, a lookup table of goal -> drift -> steering
  per part, the pushback messages, every row in time order, and a **Why Claude got confused** note
  for each pushback.

A bare `#N` is a message number. `PR #N` is a pull request. Message numbers count the session's
top-level conversation with tool calls and tool output dropped:

- A typed message counts as one. A slash command counts as one typed message, written as
  `/command args`.
- All of Claude's reply text between two typed messages, joined, counts as one. That includes
  text the harness wrote in Claude's place, such as a usage-limit notice.
- Not counted: messages from other agents, task notifications, interrupt markers, compaction
  summaries, and anything inside a subagent.

A line in a Claude reply that quotes another session's prompts is replaced with
`[OTHER_SESSION_LINE_REMOVED]`.

## Redaction

The original four sessions use `scripts/redact_session.py`. The October 5 collection uses its
generic rules plus private, session-specific rules for the full logs. Names, handles,
organisations and places are kept in local configuration, never committed. The repository
redactor's default configuration is `~/.cargento/redaction.json`:

```json
{
  "v": 1,
  "home_user_prefix": "<the start of your macOS user name>",
  "repository_under_home": "repos/<org>/cargento",
  "self_tag": "NAME_1",
  "names": [{"pattern": "Full Name|\\bFirst\\b|handle", "tag": "NAME_1"}],
  "orgs": [{"pattern": "Company|company", "tag": "ORG_NAME_1"}],
  "places": ["City", "Country"]
}
```

A name pattern matches case-insensitively unless it sets `"case_sensitive": true`, which short
initials need. `self_tag` is the tag of the person whose chat messages are kept; everyone else's
message body is removed.

The JSONL is parsed line by line and redacted value by value, so line counts, key counts, types and
tool-use ids match the source. A string value that itself holds JSON is redacted inside and written
back in its own layout, and left untouched when nothing in it changed. A path outside this
repository becomes `/[EXTERNAL_PATH_N]`: absolute, and numbered per distinct path, so a write
outside the working directory still reads as outside and two directories never merge into one. A
runner's own name survives the hidden directory (`/[EXTERNAL_PATH_1]/python3`), so a check run
through it is still a check.

Those three rules are what make the original four redacted copies replayable. Measured on that
collection on 2026-10-03, against the originals with their subagent logs cut at the same moment: the live level
and the listed checks are the same at all 31 pushback cuts. Six cuts still differ in shell-call
counts, because the board's 8 MiB backward scan reaches a little further or less far when a line's
length changes. [The drift replay check](../docs/drift-replay/README.md) replays these copies.

| Tag | Replaces |
|---|---|
| `[REDACTED_SECRET_N]` | API keys, tokens, JWTs, signed-URL signatures and credentials, private keys |
| `[PII_ANONYMIZED_N]` | Email addresses, phone numbers and reviewed identifying personal-context spans |
| `[NAME_N]` | People's names, usernames and handles, including the home-directory segment of paths |
| `[ORG_NAME_N]` | Company and organisation names, and workspace slugs in tracker and chat URLs |
| `[ID_REDACTED_N]` | Account, user, workspace, page, project and chat channel identifiers |
| `[INTERNAL_HOST_N]` | Private-network addresses, internal hosts and machine names |
| `[TZ_REDACTED]` | Time zone names and abbreviations, which give away where someone lives |
| `[LOCATION_REDACTED]` | Country and city names that say where someone lives |
| `/[EXTERNAL_PATH_N]` | A path under the home directory outside this repository (local JSONL) |
| `[EXTERNAL_PATH]` | A private path omitted from an extracted conversation |
| `[OTHER_SESSION_LINE_REMOVED]` | A line quoting another session's prompt |
| `[CROSS_SESSION_LISTING_REMOVED]` | Tool output listing other sessions' prompts (local JSONL) |
| `[THIRD_PARTY_MESSAGE_REMOVED]` | The body of a chat message someone else wrote (local JSONL) |

`[NAME_N]` and `[ORG_NAME_N]` come from a fixed table within each collection. Numbers are stable
across that collection's sessions, but are not an identity key across the two collections. In the
original four, a bare first name that two people share gets its own number, because the transcript
cannot say which person it means. Other numbered tags are local to each session.

In the original collection, redacting an organisation also redacts it inside URLs and paths. A link
to another organisation's repository therefore reads `github.com/[ORG_NAME_N]/...`, and this
checkout's own path reads `/Users/[NAME_1]/repos/[ORG_NAME_2]/cargento`. The public `spacedock-dev` organisation, loopback
addresses, issue keys (`DRC-NNNN`), session IDs, the documented `AKIAIOSFODNN7EXAMPLE` placeholder
and Claude's `noreply` commit trailer are left as they are. Base64 image data is left untouched so
that images still decode.

## How the sessions were chosen

### Original four sessions

The selection covered every Claude Code session log on one machine modified in the 30 days before
2026-10-02, with at least four typed messages and a first message inside that window. Messages from
other agents, task notifications and compaction summaries were filtered out. Candidate steering
messages were then flagged by uppercase words that are not common acronyms, and by corrective
wording ("no,", "I said", "why did you", "still", "actually", "you didn't"). Each flag was then read
by hand. Four sessions were kept in which a goal, an outcome, drift and
steering could all be shown from the transcript. A session full of personal details was passed over
for that reason.

One agent annotated each session, and a second agent then reviewed the annotation against the whole
transcript. The reviewer checked every cited message number, its speaker, each quote word for word
(typos kept), and whether each "why" is visible in the transcript or marked as inferred. Two more
reviewers then checked the generated files: one hunted for privacy leaks, and the other checked the
files against the annotations and the source logs.

### October 5 collection

This collection adds three sessions from one contributor's own logs. The scan covered all 255
top-level JSONL logs across the local Claude projects. Of these, 161 had a first message in the
September 5 to October 5, 2026 UTC window; 145 identified themselves as SDK sessions and were
excluded. Subagent logs were not read or included.

| Session | First message date (UTC) | Why it was selected |
|---|---|---|
| `77600bad-6170-419c-8287-c1caea12ddc5` | 2026-09-22 | Corrections to proposal scope, audience and presentation. |
| `67257572-b20a-4125-9c76-72faa4bf0693` | 2026-09-29 | Action items assigned to the wrong person, then corrected by the user. |
| `da7d5c96-901e-456e-ada2-0fdb3ced19fe` | 2026-10-01 | An outdated plugin version identified by the user and rerun. |

One agent annotated each conversation and a separate reviewer checked it against the full
extracted text. The reviews retained 20 pushbacks, removed four requests or approvals that had
been mistaken for steering, and rejected a fourth candidate: a disabled review workflow did not
establish agent drift. Other candidates lacked a goal-drift-steering-outcome sequence, contained
only synthetic tasks, or were passed over in favour of narrower examples. No candidate in this
collection was excluded as predominantly personal; the invoice examples encountered were synthetic.

The Chinese messages stay in Chinese, with typos and wording preserved apart from redaction.
Tool results, meta messages, compaction summaries, slash-command wrappers, interrupt markers and
agent messages are excluded from the excerpts. Consecutive Claude text records are joined using
the numbering convention above. The private HTML artifact numbers those records separately, so
its message numbers differ from the fixture numbers; every fixture citation uses the joined
numbering. Excluded command records can leave gaps in the excerpt numbers. A row's time identifies
the original text record, which can fall within a joined reply.

Full logs are never committed. The private ZIP for this collection contains only the sanitized
top-level logs for `77600bad-6170-419c-8287-c1caea12ddc5` and
`67257572-b20a-4125-9c76-72faa4bf0693`. The contributor excluded
`da7d5c96-901e-456e-ada2-0fdb3ced19fe`: its embedded screenshots contain identifying content and
other-session prompts, which text redaction cannot remove while leaving image bytes unchanged.
Its text-only excerpts and annotation remain in the PR; its full log is not cleared for sharing.
The ZIP contains no subagents, configuration, source originals, or HTML artifact.
Public repository paths, session IDs, issue keys, loopback addresses and documented placeholder
credentials are preserved. Name aliases next to Chinese characters use Latin-token boundaries;
ordinary Unicode word boundaries can miss them. These logs have not been through the original
collection's drift-replay equivalence check.
