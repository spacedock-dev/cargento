# Pushback session fixtures

Claude Code sessions, four from each of two contributors, in which the person steered the agent back
after it drifted. Each one has a goal the person set, an outcome, drift that is visible in the
transcript, and a steering message. They are reference material for the Intent and drift work: what
drift looks like in a real session, and what the person typed when they noticed it.

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
  `/command args`. A typed message that the app running the session prefixed with its own
  `<system_instruction>` or `<user-preferences>` block counts as one too, without that block.
  `scripts/drift_replay.py` does not count these yet, so its numbers run behind the second
  contributor's annotations.
- All of Claude's reply text between two typed messages, joined, counts as one. That includes
  text the harness wrote in Claude's place, such as a usage-limit notice.
- Not counted: messages from other agents, task notifications, interrupt markers, compaction
  summaries, and anything inside a subagent.

A line in a Claude reply that quotes another session's prompts is replaced with
`[OTHER_SESSION_LINE_REMOVED]`.

## Redaction

Every excerpt, every annotation and every local JSONL was passed through the same redactor, now
`scripts/redact_session.py`. This README was written by hand and names no one. The script holds the
generic rules. The names, handles, organisations and places that identify real people come from a
local file, `~/.cargento/redaction.json`, which each contributor keeps for themselves and never
commits:

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

Those three rules are what make the redacted copies replayable. Measured on the first contributor's
four sessions on 2026-10-03, against the originals with their subagent logs cut at the same moment:
the live level and the listed checks are the same at all 31 pushback cuts. Six cuts still differ in
shell-call counts, because the board's 8 MiB backward scan reaches a little further or less far when
a line's length changes. [The drift replay check](../docs/drift-replay/README.md) replays these
copies.

| Tag | Replaces |
|---|---|
| `[REDACTED_SECRET_N]` | API keys, tokens, JWTs, signed-URL signatures and credentials, private keys |
| `[PII_ANONYMIZED_N]` | Email addresses |
| `[NAME_N]` | People's names, usernames and handles, including the home-directory segment of paths |
| `[ORG_NAME_N]` | Company and organisation names, and workspace slugs in tracker and chat URLs |
| `[ID_REDACTED_N]` | Account, user, workspace, page, project and chat channel identifiers |
| `[INTERNAL_HOST_N]` | Private-network and tailnet addresses, machine names, personal hosts and tunnel names |
| `[TZ_REDACTED]` | Time zone names and abbreviations, which give away where someone lives |
| `[LOCATION_REDACTED]` | Country and city names, and CDN edge codes, that say where someone lives |
| `/[EXTERNAL_PATH_N]` | A path under the home directory outside this repository (local JSONL) |
| `[CROSS_SESSION_LISTING_REMOVED]` | Tool output listing other sessions' prompts (local JSONL) |
| `[THIRD_PARTY_MESSAGE_REMOVED]` | The body of a chat message someone else wrote (local JSONL) |
| `[LOCAL_TIME]` | A clock time in a message body not marked UTC, which beside the UTC header gives away the writer's offset (second contributor's excerpts and annotations) |

`[NAME_N]` and `[ORG_NAME_N]` come from one fixed table per contributor, so a number means the same
person or organisation in all of that contributor's sessions, and nothing across contributors. A
bare first name that two people share gets its own number, because the transcript cannot say which
person it means. Every other numbered tag is assigned per session, by first appearance.

Redacting an organisation also redacts it inside URLs and paths. A link to another organisation's
repository therefore reads `github.com/[ORG_NAME_N]/...`, and this checkout's own path reads
`/Users/[NAME_1]/repos/[ORG_NAME_2]/cargento`. The public `spacedock-dev` organisation, loopback
addresses, issue keys (`DRC-NNNN`), session IDs, the documented `AKIAIOSFODNN7EXAMPLE` placeholder
and Claude's `noreply` commit trailer are left as they are. Base64 image data is left untouched so
that images still decode.

## How the sessions were chosen

For the first contributor, the selection covered every Claude Code session log on one machine
modified in the 30 days before 2026-10-02, with at least four typed messages and a first message
inside that window. Messages from other agents, task notifications and compaction summaries were
filtered out. Candidate steering messages were then flagged by uppercase words that are not common
acronyms, and by corrective wording ("no,", "I said", "why did you", "still", "actually", "you
didn't"). Each flag was then read by hand. Four sessions were kept in which a goal, an outcome,
drift and steering could all be shown from the transcript. A session full of personal details was
passed over for that reason.

The second contributor's selection covered top-level session logs whose first message fell in the 30
days before 2026-10-05, with at least four typed messages. Sessions a script started through the
Python SDK or headless CLI were left out, which left 37. Those sessions are mostly in Traditional
Chinese, so the flags also matched Chinese corrective wording (不是, 不對, 我說, 你說, 為什麼, 其實, 等等, 到底).
Four were kept. A support thread full of an outside company's people and data was passed over, and
so were the two longest sessions (748 and 328 typed messages), most of them short approvals. Their
annotations are written in English; each quote stays verbatim and carries an `(EN: …)` translation.
That run also tagged personal hosts, tailnet addresses, tunnel names, CDN edge codes, device ids,
review share links and local clock times with a local wrapper around the redactor, removed quoted
teammate remarks as `[THIRD_PARTY_MESSAGE_REMOVED]`, and redacted the numbered conversation with the
same instance as its JSONL, so a tag in an excerpt names the same value as in the log.

One agent annotated each session, and a second agent then reviewed the annotation against the whole
transcript. The reviewer checked every cited message number, its speaker, each quote word for word
(typos kept), and whether each "why" is visible in the transcript or marked as inferred. Two more
reviewers then checked the generated files: one hunted for privacy leaks, and the other checked the
files against the annotations and the source logs.
