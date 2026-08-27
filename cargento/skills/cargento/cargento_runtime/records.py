"""Pure operations over untrusted harness records."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any, Final

# C0 and DEL, the zero-width space, the two directional marks, and the bidi
# embedding and isolate ranges. Listed one by one across U+200B to U+200F rather
# than as a range, because U+200C and U+200D are inside it and must survive:
# ZWNJ is orthographic in Persian and several Indic scripts, sitting inside
# words, and ZWJ is what composes an emoji sequence. Neither can reorder text,
# so keeping them costs no protection, and stripping them would break a title in
# those scripts anywhere in the product, not only on the row that prompted this.
_UNSAFE_CHARS = re.compile("[\\x00-\\x1f\\x7f\\u200b\\u200e\\u200f\\u202a-\\u202e\\u2066-\\u2069]+")


def safe_text(value: Any, limit: int) -> str:
    """Untrusted text, safe to put on a row: no control characters, bounded.

    The bidi and isolate ranges are stripped alongside the C0 set, and not for
    tidiness: those characters reorder how the text after them renders, so a
    harness record could make a row read as something it does not say. Legitimate
    right-to-left text does not need them, since bidi resolves implicitly.
    """
    text = str(value or "").encode("utf-8", "replace").decode("utf-8")
    text = _UNSAFE_CHARS.sub(" ", text)
    return text[:limit]


def iso_epoch(value: Any) -> float | None:
    """One ISO-8601 string as epoch seconds, or nothing. **The repo-wide rule.**

    Every ISO timestamp Cargento reads comes from outside it — a transcript, a
    SQLite column, a vendor's usage endpoint, a hook payload — and the one thing
    they do not agree on is whether the offset is there at all. So the rule is
    stated once, here, and the parsers that need it call this rather than
    `fromisoformat().timestamp()`:

    **An offset-less stamp is UTC.**

    That is a decision about which wrong answer is survivable, and it was made
    against measurement rather than taste (2026-08-06). Every source checked on a
    live machine sends an explicit offset, and every one of them sends `+00:00`:
    Claude and Pi transcript records, Copilot's `assistant_usage_events.created_at`,
    and all four `resets_at` fields on Anthropic's usage endpoint. So a naive stamp
    from any of them would be one of those same UTC values with the suffix dropped,
    and reading it as UTC recovers the right instant.

    `.timestamp()` on a naive datetime does the opposite: it reads the value as
    *server-local*. In UTC+8 that is an eight-hour error in the direction that
    matters most, making a stamp look older than it is — old enough to fall out of
    an activity window and hide a live session, which is the failure this codebase
    treats as the worst kind.

    Display is unaffected and stays local: `sessions.format_reset` and
    `lifecycle` both `.astimezone()` an epoch value for rendering. This function is
    about reading an instant, not about showing one.

    `Z` is normalized because `fromisoformat` rejected it before Python 3.11 and
    the floor is 3.11; keeping the substitution costs nothing and documents the
    spelling vendors actually send.
    """
    if not isinstance(value, str):
        return None
    text = value.replace("Z", "+00:00") if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


def parse_ts(ts: Any) -> float | None:
    """One ISO-8601 record stamp as epoch seconds, or nothing.

    An offset-less stamp is read as **UTC**, which is the repo-wide rule for every
    ISO string arriving from outside (see `iso_epoch`). Without the explicit
    `tzinfo`, `.timestamp()` reads a naive value as *server-local*, so the same
    transcript produced a reading that moved with the reader's timezone — eight
    hours out in UTC+8, which is enough to place a live turn outside the activity
    window and hide the session.
    """
    return iso_epoch(ts)


def parse_utc_sql(value: Any) -> float:
    """One SQL datetime as epoch seconds, or 0.

    SQLite has no timestamp type, so these arrive as text and usually without an
    offset. Same rule as everywhere else: no offset means UTC. The space-for-T
    substitution is what makes `fromisoformat` accept SQLite's own default
    spelling; 0 rather than None because the callers window on this and treat 0 as
    "not in the window".
    """
    return iso_epoch(str(value).replace(" ", "T")) or 0


def norm_epoch(value: Any) -> float:
    if not isinstance(value, (int, float)) or value <= 0:
        return 0
    return value / 1000 if value > 1e12 else value


def extract_text(value: Any, depth: int = 0) -> str:
    if depth > 4 or value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = (extract_text(item, depth + 1) for item in value)
        return " ".join(part for part in parts if part)[:2000]
    if isinstance(value, dict):
        for key in ("text", "content", "message", "prompt", "value"):
            if key in value:
                text = extract_text(value[key], depth + 1)
                if text:
                    return text
    return ""


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def message_dict(record: Any) -> dict[str, Any]:
    return as_dict(as_dict(record).get("message"))


def alnum(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def record_fingerprint(record: Any) -> bytes:
    raw = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8", "replace"
    )
    return hashlib.blake2b(raw, digest_size=16).digest()


def gemini_records(record: Any) -> tuple[Any, ...]:
    snapshot = record.get("$set")
    messages = snapshot.get("messages") if isinstance(snapshot, dict) else None
    if isinstance(messages, list):
        return tuple(message for message in messages if isinstance(message, dict))
    return (record,)


def incremental_gemini_records(
    record: Any,
    state: dict[str, Any],
) -> tuple[Any, ...]:
    snapshot = record.get("$set")
    messages = snapshot.get("messages") if isinstance(snapshot, dict) else None
    if not isinstance(messages, list):
        return (record,)
    messages = tuple(message for message in messages if isinstance(message, dict))
    previous_count = state["gemini_snapshot_count"]
    start = 0
    if (
        previous_count
        and len(messages) >= previous_count
        and record_fingerprint(messages[previous_count - 1]) == state["gemini_snapshot_tail"]
    ):
        start = previous_count
    state["gemini_snapshot_count"] = len(messages)
    state["gemini_snapshot_tail"] = record_fingerprint(messages[-1]) if messages else None
    return messages[start:]


def model_signal(record: dict[str, Any], harness: str, limit: int) -> str | None:
    """The model one transcript record declares, bounded, or nothing.

    Codex re-declares the model at the head of every turn, in a `turn_context`
    record written one to six lines after each `task_started`. The last such
    record a rollout carries is therefore the model the session is running on
    now, which is the only question this answers: it reports a value, not a
    history, so a caller keeps the newest hit and does not compare it to the
    ones before it.

    Gated on the harness for the reason `_turn_signal` is gated: `scan_turns`
    runs this over five harnesses' transcripts, and an ungated read would let
    any of them publish a model out of a record that merely shares a type name.

    Nothing is inferred. A harness with no such record, a payload with no
    `model`, a non-string value, and a string that bounds away to nothing all
    yield None, which every consumer reads as "not measured" rather than as a
    statement about which model ran.
    """
    if harness != "codex" or record.get("type") != "turn_context":
        return None
    value = as_dict(record.get("payload")).get("model")
    if not isinstance(value, str):
        return None
    # Untrusted vendor text on its way to the DOM: bounded here, escaped again
    # at the render site.
    return safe_text(value, limit).strip() or None


def usage_signal(record: dict[str, Any], harness: str) -> int | None:
    """The measured output tokens one transcript record reports, or nothing.

    Claude assistant records are the only scanner input with a reviewed usage
    shape. The harness gate is part of the contract: ``scan_turns`` feeds records
    from five harnesses through this function, and a coincidentally Claude-shaped
    record from another one must not turn an unmeasured session into a zero-token
    session.

    Zero is a real reading when the record explicitly reports it. Missing,
    negative, boolean, and non-integer values are unmeasured and return None.
    """
    if harness != "claude" or record.get("type") != "assistant":
        return None
    value = as_dict(message_dict(record).get("usage")).get("output_tokens")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def tool_outcome(
    record: dict[str, Any], harness: str, limit: int
) -> tuple[dict[str, str], list[tuple[str, bool]]]:
    """The tool calls a record issues and the outcomes a record reports, as
    ``({tool_use_id: tool name}, [(tool_use_id, failed)])``.

    Claude only. Every other harness gets two empty containers, which read as
    "not measured" rather than as "nothing failed": Codex's tool-output records
    carry no error field at all (measured over 15 local rollouts), Copilot's
    analyzer sees no tool-end record, and Droid's block shape looks the same as
    Claude's but no failing Droid call has ever been captured — unmeasured
    semantics do not ship here. Gated on the harness for the same reason
    `_turn_signal` and `model_signal` are: `scan_turns` runs this over five
    harnesses' transcripts, and it is also the cheap way to keep the cost of
    walking content blocks off the four that would learn nothing from it.

    The name and the outcome arrive on different records — the name on the
    `tool_use` block, `is_error` on the `tool_result` block that points back at
    its id — so the id is the only join between them and both halves are
    returned rather than one flattened answer.

    A tool NAME, never its input. The input is the user's command text, and
    nothing here needs it: the consumer counts a run and names the tool it ran
    (see docs/design-runtime-architecture.md for who owns that count).
    """
    if harness != "claude" or record.get("type") not in ("assistant", "user"):
        return ({}, [])
    content = message_dict(record).get("content")
    if not isinstance(content, list):
        return ({}, [])
    calls: dict[str, str] = {}
    results: list[tuple[str, bool]] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "tool_use":
            block_id, name = block.get("id"), block.get("name")
            if isinstance(block_id, str) and block_id and isinstance(name, str):
                # Untrusted vendor text on its way to the DOM: bounded here,
                # escaped again at the render site.
                bounded = safe_text(name, limit).strip()
                if bounded:
                    calls[block_id] = bounded
        elif block_type == "tool_result":
            block_id = block.get("tool_use_id")
            if isinstance(block_id, str) and block_id:
                results.append((block_id, bool(block.get("is_error"))))
    return (calls, results)


def _turn_signal(record: dict[str, Any], harness: str) -> tuple[str, Any] | None:
    record_type = record.get("type")
    if harness == "codex":
        if record_type != "event_msg":
            return None
        payload = as_dict(record.get("payload"))
        payload_type = payload.get("type")
        if payload_type == "task_started":
            return ("start", payload.get("started_at"))
        if payload_type in ("task_complete", "turn_aborted"):
            return ("end", None)
        return None
    if harness == "copilot":
        if record_type == "user.message":
            return ("prompt", None)
        if record_type in ("session.task_complete", "session.shutdown", "abort"):
            return ("end", None)
        return None
    if harness == "gemini":
        if record_type != "user":
            return None
        content = record.get("content")
        if isinstance(content, list) and any(
            isinstance(item, dict) and "functionResponse" in item for item in content
        ):
            return None
        return ("prompt", None)
    if harness == "droid":
        if record_type != "message":
            return None
        message = message_dict(record)
        if message.get("role") != "user":
            return None
        content = message.get("content")
        if isinstance(content, list) and any(
            isinstance(item, dict) and item.get("type") == "tool_result" for item in content
        ):
            return None
        return ("prompt", None)
    if record_type != "user" or record.get("isMeta"):
        return None
    content = message_dict(record).get("content")
    if isinstance(content, list) and any(
        isinstance(item, dict) and item.get("type") == "tool_result" for item in content
    ):
        return None
    if isinstance(content, str) and content.lstrip().startswith(
        ("<local-command-stdout>", "<local-command-caveat>")
    ):
        return None
    return ("prompt", None)


# ---------------------------------------------------------------------------
# Harness-injected prompts
#
# A "user" record is not the same thing as an operator instruction. Every
# harness writes its own machinery into that channel — skill bodies, hook
# feedback, compaction summaries, subagent notifications — and a reader that
# treats those as things a person said reports the wrong goal, the wrong stage,
# and the wrong idea of who is waiting on whom.
#
# The lists below were derived rather than guessed: 2,737 Codex user-role texts
# across 457 `rollout-*.jsonl` files, and 21,899 Claude user-role texts across
# 3,769 transcripts matching the collector's own glob. Every entry carries its
# measured count, and nothing without one is here.
#
# The two harnesses do not share a vocabulary, which is why there are two sets
# rather than one. Codex spells its injections with underscores
# (`<recommended_plugins>`) and Claude with hyphens (`<local-command-caveat>`);
# only five names appear in both. An unmeasured harness gets the union, because
# there is no evidence to narrow it and every name in either set is machinery no
# operator opens a prompt with.

# `<image>` is a WRAPPER, not a rejection. All 36 Codex records that open with
# one carry real operator text after it, so rejecting on the tag would drop
# genuine prompts. Claude spells the same thing `[Image: source: /path/…]` in
# plain text, and there the opposite holds: 385 of 386 such records are nothing
# but image markers, and they reach the empty-after-stripping rejection instead.
# The 386th spells it `[Image source:` with no colon, which is why the separator
# is a class rather than a literal. The attribute matcher is loose because Codex
# writes `name=[Image #1]` unquoted, spaces and `#` and `]` included.
_PROMPT_IMAGE_WRAPPER_RE = re.compile(
    r"^\s*(?:<image\b[^>]*>\s*(?:</image>)?|\[Image[:\s][^\]]*\])\s*",
    re.IGNORECASE,
)

# Only a tag that opens the text, so prose merely containing markup later on is
# left alone. The trailing class separates `<skill>` from a sentence beginning
# "<3 this".
_PROMPT_LEADING_TAG_RE = re.compile(r"^</?([A-Za-z][A-Za-z0-9_-]*)[\s>/]")

# The slash-command tags — `<command-message>`, `<command-name>`,
# `<command-args>` — are deliberately absent from both sets. They WRAP the
# operator's intent rather than replacing it: a slash command is what the
# person asked for, spelled in the harness's own markup. `transcripts.prompt_title`
# already owns rendering them, through a dedicated `_COMMAND_NAME_RE` /
# `_COMMAND_ARGS_RE` path that reads the bytes back out as
# `/claude-code-review 1287 - with a fresh pair of eyes...`, so rejecting them
# here would have left two primitives in one runtime disagreeing about the same
# record. Measured before removal: 1,493 of 15,109 `_turn_signal`-reachable
# Claude prompts carried a `<command-name>` with non-empty `<command-args>` and
# every one was rejected, which left 213 of 3,100 collector-gated sessions with
# no recoverable operator intent at all.
#
# `<teammate-message>` stays listed, and the cost is accepted rather than
# overlooked: a message from another agent is not the operator's instruction,
# so the 563 sessions carrying one show nothing from it.

# Measured leading a Codex user-role record; counts are corpus occurrences.
_CODEX_USER_TAGS = frozenset(
    {
        "recommended_plugins",  # 226
        "skill",  # 99
        "teammate-message",  # 90
        "environment_context",  # 42
        "subagent_notification",  # 36
        "task-notification",  # 34
        "local-command-stdout",  # 18
        "bash-input",  # 14
        "bash-stdout",  # 14
        "user_shell_command",  # 5
        "turn_aborted",  # 3
    }
)

# Measured in the same rollouts, but on a `developer`-role record rather than a
# user-role one. They are listed because the role a Codex build files an
# injection under has already moved once — `turn_aborted` appears under both —
# and the cost is asymmetric: an unlisted tag renders harness markup as a
# person's words, while a listed one that never arrives costs nothing.
_CODEX_DEVELOPER_TAGS = frozenset(
    {
        "permissions",  # 410
        "skills_instructions",  # 388
        "apps_instructions",  # 377
        "plugins_instructions",  # 377
        "multi_agent_mode",  # 359
        "collaboration_mode",  # 53
        "app-context",  # 3
    }
)

# Measured leading a Claude user-role record.
_CLAUDE_USER_TAGS = frozenset(
    {
        "task-notification",  # 1771
        "teammate-message",  # 1176
        "local-command-caveat",  # 1064
        "local-command-stdout",  # 620
        "bash-input",  # 242
        "bash-stdout",  # 241
        "channel",  # 8 — a Slack-plugin envelope, request text inside the tag
        "system-reminder",  # 4
        "local-command-stderr",  # 1
    }
)

_INJECTED_TAGS = {
    "codex": _CODEX_USER_TAGS | _CODEX_DEVELOPER_TAGS,
    "claude": _CLAUDE_USER_TAGS,
}
_ANY_INJECTED_TAG = frozenset[str]().union(*_INJECTED_TAGS.values())

# Injections no tag regex can reach, because the harness writes them as prose.
# Shared across harnesses rather than split: two were measured in both corpora,
# none of the rest is a phrase an operator opens a prompt with, so splitting
# would buy nothing and would make a harness that borrows another's wording
# silently wrong.
_INJECTED_PROMPT_PREFIXES = (
    "# AGENTS.md instructions",  # codex 164
    "Analyze this conversation and determine",  # claude 1084
    "Another Claude session sent a message:",  # codex 130, claude 636
    "Base directory for this skill:",  # claude 3051
    "Caveat: The messages below were generated by the user while running",  # claude 43
    "Stop hook feedback:",  # claude 581
    "This session is being continued from a previous conversation",  # claude 355
    "[Request interrupted by user",  # codex 4, claude 294
    "[external_agent_tool_result]",  # codex 4
)

# Matched whole rather than as a prefix. All 97 occurrences are exactly this
# word, and as a prefix it would reject "Warmup the cache before the run",
# which is an operator saying something.
_INJECTED_PROMPTS = frozenset({"Warmup"})


def strip_prompt_wrappers(text: str) -> str:
    """Peel the harness's image markers off the front of a user prompt.

    Repeatedly, because one message can carry several screenshots and each
    arrives as its own marker. What is left is either the operator's own words
    or nothing at all.
    """
    stripped = text.strip()
    while True:
        shorter = _PROMPT_IMAGE_WRAPPER_RE.sub("", stripped, count=1).strip()
        if shorter == stripped:
            return stripped
        stripped = shorter


def injected_prompt(text: str, harness: str) -> bool:
    """Is this user-record text the harness talking, rather than the operator?

    True means the record is machinery: a skill body, a hook's feedback, a
    compaction summary, an envelope around something else. Callers use it to
    decide what may stand in for a person's intent, so a false positive costs a
    real prompt and a false negative reports markup as a goal.
    """
    body = strip_prompt_wrappers(text)
    if not body:
        return True
    tag = _PROMPT_LEADING_TAG_RE.match(body)
    if tag:
        return tag.group(1).casefold() in _INJECTED_TAGS.get(harness, _ANY_INJECTED_TAG)
    return body in _INJECTED_PROMPTS or body.startswith(_INJECTED_PROMPT_PREFIXES)


# ---------------------------------------------------------------------------
# The instruction line
#
# Widths first, in one place, because they were in two and drifted: the 80 was
# applied inside `transcripts.analyze_codex_transcript` and the 140 at
# `collectors/codex.py`, so no reader could see both at once.
#
# 140 is the width `last_prompt` has always been clipped to and is kept rather
# than rederived; 80 is the width `transcripts.prompt_title` already defaults to.
PROMPT_TITLE_CAP_CHARS: Final = 80
LAST_PROMPT_CAP_CHARS: Final = 140
# The line-2 cap. It lives here rather than in `config` because the width is not
# a tuning knob — it is the same untrusted-text bound `last_prompt` carries, on a
# field published beside it — and `config.py` is a documented merge hotspot.
INSTRUCTION_CAP_CHARS: Final = 140

# A prompt this short states no work. Measured on Claude's 204-session cohort
# (DRC-4266): 60 of 204 newest real prompts are six words or fewer — "proceed",
# "commit, push, and create a PR" — and 24 are three or fewer.
#
# Six, not a character count, and the distinction is the whole finding. A "<40
# characters" rule was measured and rejected: it would replace 402 good lines to
# fix 81 bad ones, because most short prompts are short AND informative
# ("create a pr"). This threshold never substitutes for the newest prompt; it
# only decides whether a SECOND, labelled line is worth adding beneath it, which
# is the one use a length rule survives.
_CONTINUATION_MAX_WORDS: Final = 6


def bare_continuation(text: str) -> bool:
    """Does this prompt carry an instruction, or only tell the agent to go on?

    True for "proceed" and "yes, do that"; false for "resolve the blocker and
    create the pr". Callers use it to decide whether a labelled second line
    earns its space, never to replace what the operator actually said.

    Give it a RENDERED line, not a raw record. A slash command arrives as sixty
    characters of markup that counts as six words and reads as a continuation,
    while the line a person sees is `/burndown DRC-4266 and the board`.
    `transcripts.states_work` is the pairing that gets this right.
    """
    return len(strip_prompt_wrappers(text).split()) <= _CONTINUATION_MAX_WORDS


# A rendered directive that is one slash-command token and nothing else. The
# name is matched against the set below; the shape only isolates it.
_BARE_COMMAND_RE = re.compile(r"^/([A-Za-z0-9][A-Za-z0-9:._-]*)$")

# Slash commands that drive the harness rather than the work, with their
# occurrence counts as the last published goal in the local corpus. Shared
# across harnesses rather than split per harness, on the same reasoning as the
# injected-prose prefixes above: `clear` and `login` were measured in both, and
# none of the rest is a name one harness could mean differently.
_HARNESS_CONTROL_COMMANDS: Final = frozenset(
    {
        "add-dir",  # claude 2
        "clear",  # claude 72, codex 1
        "context",  # claude 2
        "exit",  # claude 7
        "insights",  # claude 1
        "login",  # claude 70, codex 3
        "mcp",  # claude 11
        "model",  # claude 5
        "plugin",  # claude 21
        "reload-plugins",  # claude 7
        "reload-skills",  # claude 1
        "stickers",  # claude 1
    }
)


def harness_control(rendered: str | None) -> bool:
    """Whether a *rendered* directive drives the harness rather than the work.

    Applied to what `transcripts.prompt_title` produces, not to the raw record:
    the raw spelling is `<command-name>/clear</command-name>` and the value
    actually published is `/clear`, so a predicate reading the raw text never
    meets the one the page shows.

    A measured name list and NOT the structural rule "a bare command carries no
    arguments, so it carries no goal". That rule was checked against the same
    corpus and is wrong: bare-command goals are also skill invocations —
    `/create-pr`, `/cargento:cargento`, `/security-review` — and a skill invoked
    with no arguments is exactly what the operator asked for. Argument-carrying
    commands are untouched either way; `prompt_title` renders those as
    `/code-review 1287 with fresh eyes`, which never matches here.

    Lives in `records` rather than in either caller because two surfaces publish
    the same reading of the same directive: `observer.py` picks a session goal
    and `transcripts.states_work` picks the instruction line beneath a session
    title. Two lists would be two chances to disagree about whether `/clear` is
    an objective.
    """
    match = _BARE_COMMAND_RE.match(rendered or "")
    return match is not None and match.group(1).casefold() in _HARNESS_CONTROL_COMMANDS


def instruction_line(
    label: str,
    text: str | None,
    at: float | None,
    *,
    limit: int = INSTRUCTION_CAP_CHARS,
) -> dict[str, Any] | None:
    """One published line-2 reading, bounded, or nothing.

    ``label`` is what the page prefixes the line with — the reason a stale or
    second-hand line is survivable at all — so a reading with no label is not
    published. ``at`` is the record's own stamp; the page renders the age from
    it, and 0 means unstamped rather than "now".

    The bound is the cap plus one because `transcripts.clip` appends its ellipsis
    AFTER cutting to the cap, so a clipped title is cap + 1 characters and a
    scrub at the cap takes the `…` back off — 29 of 1,906 published Claude lines
    ended in an unmarked mid-token cut that way. `safe_text` only ever shortens,
    so this cannot truncate what rendering already bounded. The same reasoning,
    and the same `+ 1`, guards line 1 in `transcripts.codex_instruction`.
    """
    bounded = safe_text(text, limit + 1).strip()
    if not bounded or not label:
        return None
    return {"label": label, "text": bounded, "at": at if at and at > 0 else 0}
