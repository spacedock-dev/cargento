# Pushback session fixtures

Four Claude Code sessions in which the person steered the agent back after it drifted. Each one has
a goal the person set, an outcome, drift that is visible in the transcript, and a steering message.
They are reference material for the Intent and drift work: what drift looks like in a real session,
and what the person typed when they noticed it.

```
tests/raw_sessions/<session_id>/
    steering-excerpts.txt     committed: every message the annotation cites
    <session_id>.jsonl        gitignored: the full sanitized session log, local only
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

Every excerpt, every annotation and every local JSONL was passed through the same redactor. This
README was written by hand and names no one. The JSONL was parsed line by line and redacted value
by value, so line counts, key counts, types and tool-use ids match the source. Two kinds of value
change shape. A string value that itself holds JSON was redacted inside and re-serialised, which
flattens a pretty-printed blob onto one line. An object key that is a path outside this repository
became a numbered `[EXTERNAL_PATH_N]`, so two keys never collapse into one.

| Tag | Replaces |
|---|---|
| `[REDACTED_SECRET_N]` | API keys, tokens, JWTs, signed-URL signatures and credentials, private keys |
| `[PII_ANONYMIZED_N]` | Email addresses |
| `[NAME_N]` | People's names, usernames and handles, including the home-directory segment of paths |
| `[ORG_NAME_N]` | Company and organisation names, and workspace slugs in tracker and chat URLs |
| `[ID_REDACTED_N]` | Account, user, workspace, page, project and chat channel identifiers |
| `[INTERNAL_HOST_N]` | Private-network addresses |
| `[TZ_REDACTED]` | Time zone names and abbreviations, which give away where someone lives |
| `[LOCATION_REDACTED]` | Country and city names that say where someone lives |
| `[EXTERNAL_PATH]`, `[EXTERNAL_PATH_N]` | Paths under the home directory outside this repository (local JSONL) |
| `[CROSS_SESSION_LISTING_REMOVED]` | Tool output listing other sessions' prompts (local JSONL) |
| `[THIRD_PARTY_MESSAGE_REMOVED]` | The body of a chat message someone else wrote (local JSONL) |

`[NAME_N]` and `[ORG_NAME_N]` come from one fixed table, so a number means the same person or
organisation in all four sessions. A bare first name that two people share gets its own number,
because the transcript cannot say which person it means. Every other numbered tag is assigned per
session, by first appearance.

Redacting an organisation also redacts it inside URLs and paths. A link to another organisation's
repository therefore reads `github.com/[ORG_NAME_N]/...`, and this checkout's own path reads
`/Users/[NAME_1]/repos/[ORG_NAME_2]/cargento`. The public `spacedock-dev` organisation, loopback
addresses, issue keys (`DRC-NNNN`), session IDs, the documented `AKIAIOSFODNN7EXAMPLE` placeholder
and Claude's `noreply` commit trailer are left as they are. Base64 image data is left untouched so
that images still decode.

## How the sessions were chosen

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
