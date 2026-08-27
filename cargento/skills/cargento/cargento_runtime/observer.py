"""The observer agent: a read-only analyzer that derives goal + stage + block.

Sits beside an active session, reads its transcript and workflow entity dir
read-only, and writes one sidecar (``<harness>_<sid>.observer.json``) the
observer panel renders. The analyzer never mutates the observed session's
repo or state; the sidecar is written to the observer's own store under
``config.state_dir``.

The goal is derived deterministically from the most recent concrete user
directive in the transcript. A session whose only content is a generic
skill-load opener with no assistant output short-circuits to ``"no goal
derived"`` without calling the model — the rule-based sentinel that bounds
the model and prevents fabrication. A model callable may enhance the
derivation; on any failure it degrades to the deterministic fallback, never
to a crash or a hallucination.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
from typing import TYPE_CHECKING, Any, Protocol

from . import io as runtime_io
from . import records, spacedock, transcripts

if TYPE_CHECKING:
    from collections.abc import Callable

    from .config import RuntimeConfig
    from .state import RuntimeState

NO_GOAL = "no goal derived"
NO_GOAL_REASON = "generic-opener-only-no-work"

# How many recent messages a model caller is shown. Twenty is one working
# stretch on the sessions this was read against, not a tuned figure.
_MODEL_CONTEXT_MESSAGES = 20

# A session id in a sidecar filename. Deliberately narrower than anything a
# harness actually emits: the value reaches `os.path.join`, and `safe_text`
# strips control characters without touching a separator or a `..`.
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

# Generic skill-load directives that carry no goal by themselves. Measured
# against real Pi session transcripts: the opening line is a harness-injected
# wrapper, not a user objective.
_GENERIC_OPENER_PREFIXES = (
    "use $",
    "skill(",
)

# Block indicators, scanned in the newest assistant message only. Self-state
# phrases, and not the bare words this started with: `cannot`, `can't`,
# `unable`, `failed to` and `error:` match ordinary reporting prose — "I can't
# reproduce it any more, so the fix holds" published a finished session as
# blocked, and "error:" matches any agent quoting a log line it has already
# dealt with. A false block is worse than no block: it is the one field on the
# panel a reader would act on.
# `blocked on` was the last bare phrase left, and it is now gone for the same
# reason: measured over 857 sessions once the parser reached Claude and Codex,
# it produced 4 blocks and all 4 were prose about a PR or another issue —
# "the PR is blocked only by required review", "your conclusion that … is still
# blocked on Spacedock PR work is correct". None was the agent's own state. Two
# of them hit the 200-character cap with the triggering phrase truncated away,
# so the rendered card showed a block whose visible text contained no block
# language at all. The first-person forms above already carry the real case.
#
# `not permitted`, `permission denied` and `waiting for your` are the remainder,
# and they go the same way. Re-measured over the whole local Claude corpus (3,774
# transcripts, 2,828 with an assistant message) the table produced 7 blocks and
# those three supplied 4 of them — every one inside a quoted or fenced span, two
# of them again truncated away by the 200-character cap. They are replaced below
# by the self-state forms that carry the real case; those forms match 0 records
# today, which is the point. An indicator that never fires costs nothing, and
# these three cost a wrong answer each.
_BLOCK_INDICATORS = (
    "i'm blocked",
    "i am blocked",
    "i'm stuck",
    "i am stuck",
    "waiting for you",
    "waiting for approval",
    "i'm waiting for your",
    "i am waiting for your",
    "i'm not permitted",
    "i am not permitted",
    "i don't have permission",
    "i do not have permission",
)

# What may not follow an indicator. `waiting for you` is a prefix of `waiting for
# your`, so without this the bare phrase would keep matching the possessive the
# line above removes — and the two are not the same claim: "waiting for you." is
# a hand-off, "waiting for your PR to land" is a report about someone else.
_BLOCK_TRAILING_RE = re.compile(r"[A-Za-z0-9]")


class ModelCaller(Protocol):
    """A cheap model invocation that derives a goal line, or None on failure.

    The callable receives the most recent turns of the transcript — the *tail*,
    which is what a goal line is derived from; the head is where the opening
    directive lives and both are already folded into the deterministic goal —
    plus the entity's current stage, and returns a goal line, or None if it
    cannot produce one. None is the only failure signal: the analyzer degrades
    to the deterministic fallback rather than raising.

    Nothing in the shipped tree passes one. It is the seam for the derivation
    the design calls for and this module does not yet make, kept typed so the
    bound above (the sentinel short-circuit, the cap on what goes out and on
    what comes back) is written down before there is a caller to forget it.
    """

    def __call__(self, recent_text: str, entity_stage: str) -> str | None: ...


def _is_generic_opener(text: str) -> bool:
    """Whether a user message is a generic skill-load directive, not a goal.

    One concept with ``records.injected_prompt`` and two disjoint lists: both ask
    "is this the harness talking". They are kept apart because this is a *goal*
    rule and that is a *record* rule — a generic opener is a real user message
    that states nothing, so no other reader should be made to drop it — but a
    phrase that belongs on both has to be added to both.
    """
    stripped = text.strip().lower()
    return any(stripped.startswith(prefix) for prefix in _GENERIC_OPENER_PREFIXES)


# `type: "message"` is Pi's shape and Droid's, and `_parse_message_record`
# deliberately takes no harness parameter (the shapes below are disjoint across
# the whole local corpus, so the union needs no gate). That leaves the shared
# shape with no single name to hand the injected-tag lookup, which is exactly
# the case `records.injected_prompt` documents: a harness it has no measured
# vocabulary for gets the union of every measured set.
#
# So this value is deliberately NOT a key of `records._INJECTED_TAGS`, and the
# dict miss is the mechanism rather than an accident. The Droid half of the name
# is aspirational: `resolve_transcript` answers for claude, codex and pi only, so
# no Droid transcript reaches this module today.
_SHARED_MESSAGE_HARNESS = "pi-or-droid"


def _blocks_carry_tool_result(content: Any) -> bool:
    """Whether a content list holds a tool_result block, in either spelling.

    Claude and Pi write ``type: "tool_result"``; Codex writes the same echo as a
    ``function_call_output`` payload, which never reaches here because it is not
    a ``message``. A user turn carrying one is a system echo, not a directive.
    """
    return isinstance(content, list) and any(
        isinstance(block, dict) and block.get("type") == "tool_result" for block in content
    )


def _message_from(role: Any, content: Any, harness: str, cap: int) -> dict[str, str] | None:
    """The (role, text) pair for one already-unwrapped message, or None.

    The one place the injected-shape rejection is applied, so every harness arm
    below gets it. Without it, teaching the parser the Claude and Codex shapes
    would publish a harness's own machinery as the operator's goal on 51.6% of
    Codex rollouts and 62.5% of Claude sessions — a confident wrong answer where
    there is a silent sentinel today, which is the worse of the two failures.

    `cap` is `observer_model_context_chars` and not `extract_text`'s own default,
    because the block half scans this text for an indicator ANYWHERE in it rather
    than reading its opening. On the bare-string harnesses (Pi and Droid, whose
    content is a string and not a list of blocks) the 2,000-character default put
    an indicator past that offset out of reach and the block came back empty,
    with nothing on the panel saying so. The bound this passes is the one the
    module already vouches for on the value it hands the caller.
    """
    if role not in ("user", "assistant"):
        return None
    if _blocks_carry_tool_result(content):
        return None
    text = records.extract_text(content, cap=cap).strip()
    if not text:
        return None
    if role == "assistant":
        return {"role": "assistant", "text": text}
    # The operator's own words, with the harness's image markers peeled off the
    # front — `strip_prompt_wrappers` is what makes `[Image #1] fix the build`
    # publishable as a goal rather than as a marker.
    body = records.strip_prompt_wrappers(text)
    if not body or records.injected_prompt(text, harness):
        return None
    return {"role": "user", "text": body}


def _claude_message(record: dict[str, Any], record_type: str, cap: int) -> dict[str, str] | None:
    """One (role, text) pair from a Claude ``user``/``assistant`` record, or None.

    A subagent's transcript is interleaved into its parent's file, and a
    subagent's prompt is the parent agent's dispatch rather than the operator's.
    Measured with this parser over the local Claude corpus, the record supplying
    the goal was ``isSidechain`` on 74 of 394 sessions. Neither this function's
    predecessor nor ``records._turn_signal`` tested the flag; ``isMeta``, which
    both refuse, is the harness's own bookkeeping and goes with it.
    """
    if record.get("isSidechain") or record.get("isMeta"):
        return None
    message = records.message_dict(record)
    return _message_from(message.get("role") or record_type, message.get("content"), "claude", cap)


def _parse_message_record(record: Any, cap: int) -> dict[str, str] | None:
    """One (role, text) pair from a JSONL message record, or None.

    Three record shapes, additively: ``type: "message"`` with a nested
    ``message.role`` (Pi and Droid), ``type: "user"``/``"assistant"`` (Claude),
    and ``type: "response_item"`` with ``payload.type == "message"`` (Codex).
    Requiring the first alone is what returned zero messages on 3,769 of 3,769
    local Claude transcripts and 457 of 457 Codex rollouts.

    No ``harness`` parameter, and that is a measurement rather than a shortcut:
    the three shapes are disjoint over the whole local corpus (0 of 457 Codex
    and 0 of 600 Claude files carry a top-level ``type == "message"``; Codex
    carries no ``user``/``assistant`` record and Claude no ``response_item``),
    and this function has one call chain in which the caller has already
    resolved a single file for a single requested harness.

    Guards every field the way the collectors guard theirs: untyped JSON from
    disk.
    """
    if not isinstance(record, dict):
        return None
    record_type = record.get("type")
    if record_type == "message":
        message = records.message_dict(record)
        return _message_from(
            message.get("role"), message.get("content"), _SHARED_MESSAGE_HARNESS, cap
        )
    if record_type in ("user", "assistant"):
        return _claude_message(record, record_type, cap)
    if record_type == "response_item":
        payload = records.as_dict(record.get("payload"))
        if payload.get("type") != "message":
            return None
        return _message_from(payload.get("role"), payload.get("content"), "codex", cap)
    return None


def _dedup_key(record: dict[str, Any]) -> str:
    """The record's own identity, or empty when it carries none.

    Not ``record["id"]``, which is what this read before: **0 of 8,312 Claude
    and 0 of 14,389 Codex records carry a top-level ``id``**, so the key
    degraded silently to the message text and a prompt repeated verbatim later
    in the session kept its first, oldest position. Claude spells it ``uuid``
    and Codex ``payload.id``; Pi and Droid do spell it ``id``.

    Empty is a real answer and not a failure: ``payload.id`` is absent on 500 of
    the 655 Codex user-message records (76.3%) the DISJOINT windows this module
    now cuts return, measured over the whole local rollout store. The count
    matters less than the instrument: the same measurement on the old
    ``head + read_tail`` concatenation gives 599 of 785, and the surplus is the
    overlap region counted twice, which is the bug ``_window_lines`` fixes. The
    share is 76.3% either way, so the load-bearing claim (about three quarters
    carry no id) does not rest on which instrument you use. The caller's fallback
    is positional for that reason — see ``_window_lines``.
    """
    for value in (
        record.get("uuid"),
        record.get("id"),
        records.as_dict(record.get("payload")).get("id"),
    ):
        if isinstance(value, str) and value:
            return value
    return ""


def _window_lines(config: RuntimeConfig, path: str) -> list[str]:
    """The head window's lines then the tail window's, with no line in both.

    Cut apart on byte offsets rather than deduped afterwards, because the two
    windows overlap on any file under ``observer_head_bytes + tail_bytes`` —
    completely, on any file the tail read swallows whole. The old concatenation
    leaned on the dedup key to collapse that overlap, and the key falls back to
    the message TEXT on the 76.4% of Codex user records carrying no
    ``payload.id``: a prompt repeated verbatim later in the session was then
    dropped as a duplicate of its own first occurrence, and the goal stayed on
    whatever came between them. Disjoint windows make that fallback positional,
    so the only thing the key still has to collapse is a genuine replay — a
    resumed transcript rewriting earlier records, which carry their original ids.
    """
    tail_lines = runtime_io.read_tail(config, path)
    try:
        size = os.path.getsize(path)
    except OSError:
        return tail_lines
    if size <= config.tail_bytes:
        # The tail read took the whole file, so the head window is a prefix of
        # what is already here.
        return tail_lines
    try:
        head = runtime_io.read_prefix_bytes(path, max_bytes=config.observer_head_bytes)
    except OSError:
        return tail_lines
    # The first byte the tail read covers. A head line starting at or after it is
    # in `tail_lines` already; one starting before it cannot be, because the tail
    # read drops its own partial first line.
    floor = size - config.tail_bytes
    head_lines: list[str] = []
    offset = 0
    for raw in head.split(b"\n"):
        if offset >= floor:
            break
        head_lines.append(raw.decode("utf-8", "replace"))
        offset += len(raw) + 1
    return head_lines + tail_lines


def _extract_messages(config: RuntimeConfig, path: str) -> list[dict[str, str]]:
    """User and assistant texts from a JSONL transcript, head + tail bounded.

    The head carries the opening directive; the tail carries the recent window.
    ``_window_lines`` keeps the two disjoint, and records are deduped by their
    own id so a resumed transcript's replayed block does not double-count.
    Returned in **record-timestamp** order.

    Ordering by timestamp and not by list position, because list position is
    not record order. The concatenation itself is fine — the head is read
    first and the tail last, so `head_lines + tail_lines` already runs oldest
    to newest across the two windows. What file position cannot express is a
    file whose own records are out of order: a resumed session replays the
    earlier transcript's records into the new file, and the replayed block
    carries its original stamps while sitting after records written later, so
    `directives[-1]` would be the replayed opening prompt.

    Stated honestly, this is a correctness invariant rather than a measured
    win: over the whole local corpus the sort reorders 0 of 3,494 non-empty
    message lists and changes 0 published goals. It is kept because the shape
    it guards against is real (`resume`), cheap to hold, and silent when it
    fires. File order breaks ties, which is what keeps a transcript whose
    records carry no stamp reading exactly as it did before.
    """
    ordered: list[tuple[float, int, dict[str, str]]] = []
    seen: set[str] = set()
    # Carried forward so a stampless record sorts beside the stamped one before
    # it rather than ahead of the whole file.
    last_ts = 0.0
    for position, raw in enumerate(_window_lines(config, path)):
        if not raw or not raw.lstrip().startswith("{"):
            continue
        try:
            record = json.loads(raw)
        except (ValueError, json.JSONDecodeError):
            continue
        if not isinstance(record, dict):
            continue
        stamp = records.parse_ts(record.get("timestamp"))
        if stamp:
            last_ts = stamp
        parsed = _parse_message_record(record, config.observer_model_context_chars)
        if parsed is None:
            continue
        key = _dedup_key(record) or f"#{position}"
        if key in seen:
            continue
        seen.add(key)
        ordered.append((last_ts, position, parsed))
    ordered.sort(key=lambda item: (item[0], item[1]))
    return [parsed for _ts, _position, parsed in ordered]


def _user_directives(config: RuntimeConfig, messages: list[dict[str, str]]) -> list[str]:
    """Concrete user directives, newest last, openers and controls dropped.

    Two rejections, and they read different spellings of the same message on
    purpose: `_is_generic_opener` reads the raw text, `records.harness_control`
    reads what `prompt_title` will publish. Filtering here rather than at the
    point of publication is what lets a `/clear` fall back to the objective
    the session already contains instead of erasing it.
    """
    kept: list[str] = []
    for msg in messages:
        if msg["role"] != "user" or _is_generic_opener(msg["text"]):
            continue
        rendered = transcripts.prompt_title(
            config, msg["text"], limit=config.observer_goal_cap_chars
        )
        if records.harness_control(rendered):
            continue
        kept.append(msg["text"])
    return kept


def _has_assistant_output(messages: list[dict[str, str]]) -> bool:
    return any(msg["role"] == "assistant" for msg in messages)


def _derive_goal_deterministic(
    config: RuntimeConfig,
    messages: list[dict[str, str]],
) -> tuple[str, str | None]:
    """A goal line from the most recent concrete directive, or the sentinel.

    Returns (goal, reason). The reason is ``NO_GOAL_REASON`` when the
    short-circuit fires, None otherwise. The short-circuit is the
    deterministic fallback that bounds the model: when the only user
    message is a generic opener and no assistant text was produced, the
    analyzer returns the sentinel without calling the model.
    """
    directives = _user_directives(config, messages)
    if not directives and not _has_assistant_output(messages):
        return NO_GOAL, NO_GOAL_REASON
    if not directives:
        # Assistant work exists but no concrete directive was found: the
        # goal is unknown, not fabricated.
        return NO_GOAL, None
    # `prompt_title` rather than `split("\n")[0]`, and the reason is the one
    # shape `records.injected_prompt` deliberately admits. A slash command is
    # the operator's intent spelled in the harness's markup, so it is not
    # rejected as machinery (the harness's own controls are, but by
    # `records.harness_control` above, on the rendered name) — but published raw
    # it reads as `<command-message>…`, which was 60 of 400 Claude sessions and
    # 5 of 457 Codex rollouts. `prompt_title`
    # already owns that rendering (`/review 1287 — with fresh eyes`), and
    # strips the wrapper tags off everything else. It also collapses a long
    # absolute path to its basename (`transcripts.shorten_paths`), so a goal
    # naming a temp file reads as the file rather than as the path to it.
    goal = transcripts.prompt_title(config, directives[-1], limit=config.observer_goal_cap_chars)
    if not goal:
        return NO_GOAL, None
    # Cap plus one, for the reason `records.instruction_line` carries the same
    # `+ 1`: `transcripts.clip` appends its ellipsis AFTER cutting to the cap, so
    # a clipped goal is cap + 1 characters and a scrub at the cap took the `…`
    # straight back off — an unmarked mid-token cut on 8 of the 1,295 goals the
    # local Claude corpus publishes (269 of which clip at all). `safe_text` only
    # ever shortens, so this cannot lengthen what rendering already bounded.
    return records.safe_text(goal, config.observer_goal_cap_chars + 1), None


def _derive_stage(
    config: RuntimeConfig,
    state: RuntimeState,
    workflow_dir: str | None,
    entity_dir: str | None,
    now: float,
    window_sec: float,
) -> str:
    """The newest in-flight entity's stage, or empty.

    Through ``read_entities``, not ``entity_files(...)[0]``'s raw ``status``
    scalar, and the difference is the project-read contract rather than tidiness.
    Two of that function's guards are load-bearing on this path:

    - the freshness window, without which a workflow retired months ago
      publishes a stage for a session that merely discovered it;
    - ``status in declared``, which SECURITY.md names as the per-file
      discriminator standing in for :func:`spacedock.read_workflow`'s
      containment check. A ``split-root`` workflow's state directory
      legitimately sits outside its definition directory, so nothing else
      bounds what a file under it may say. Reading the scalar directly
      published an arbitrary line of an unverified file; a declared stage is a
      name the README already vouched for, and one ``SD_STAGE_RE`` has matched.

    ``--no-spacedock`` withdraws the project reads for this route the same way
    it does for a strip: the transcript half of the observer is a transcript
    read and survives, the two frontmatter reads do not.
    """
    if not config.spacedock_enabled or not workflow_dir or not entity_dir:
        return ""
    workflow = spacedock.read_workflow(config, state, workflow_dir)
    if workflow is None:
        return ""
    entities = spacedock.read_entities(
        config, state, entity_dir, workflow["stages"], now, window_sec
    )
    return entities[0][1] if entities else ""


def _indicator_hit(lower: str, indicator: str) -> int:
    """Where one indicator matches as a whole phrase in lowercased text, or -1.

    Scans past a rejected hit rather than stopping at it: `str.find` returns the
    first occurrence, and "waiting for your PR" earlier in a message must not
    hide a genuine "waiting for you." later in it.
    """
    start = 0
    while (pos := lower.find(indicator, start)) >= 0:
        if not _BLOCK_TRAILING_RE.match(lower, pos + len(indicator)):
            return pos
        start = pos + 1
    return -1


def _derive_block(
    config: RuntimeConfig,
    messages: list[dict[str, str]],
) -> str:
    """One open block from the newest assistant message, or empty.

    A bounded keyword scan over that one message: if its text carries a block
    indicator, the sentence around the first hit is the block. Nothing is
    inferred; a message without an indicator yields no block.

    The newest message and not a walk back through all of them. Scanning
    backwards found a block that had been reported and then resolved twenty
    turns earlier and published it as current, which is a worse answer than
    none — this is the one field on the panel a reader would act on.
    """
    for msg in reversed(messages):
        if msg["role"] != "assistant":
            continue
        text = msg["text"]
        lower = text.lower()
        for indicator in _BLOCK_INDICATORS:
            pos = _indicator_hit(lower, indicator)
            if pos < 0:
                continue
            # Extract the sentence around the indicator.
            start = text.rfind(". ", 0, pos)
            start = start + 2 if start >= 0 else 0
            end = text.find(". ", pos)
            end = end + 1 if end >= 0 else len(text)
            sentence = text[start:end].strip()
            if sentence:
                return records.safe_text(sentence, config.observer_block_cap_chars)
        return ""  # the newest assistant message had nothing; do not walk back
    return ""


def analyze(
    config: RuntimeConfig,
    state: RuntimeState,
    transcript_path: str,
    *,
    now: float,
    window_sec: float,
    model: ModelCaller | Callable[[str, str], str | None] | None = None,
) -> dict[str, Any]:
    """Derive goal + stage + block from a session transcript, read-only.

    Returns ``{"goal": str, "stage": str, "block": str, "reason": str | None}``.
    The goal is either a derived goal line or the literal ``"no goal derived"``
    sentinel. The stage comes from the entity dir's frontmatter ``status``.
    The block is one sentence from recent assistant text containing a block
    indicator, or empty.

    The model callable is optional. When provided and the deterministic
    short-circuit does not fire, the model may enhance the goal; on any
    failure (returning None) the deterministic goal is kept. The
    short-circuit always bypasses the model.
    """
    messages = _extract_messages(config, transcript_path)
    goal, reason = _derive_goal_deterministic(config, messages)
    workflow_dir, entity_dir = resolve_workflow(config, state, transcript_path)
    # Once, not once per consumer. The two frontmatter reads are cached on
    # (path, mtime, size), but resolving twice also scanned the transcript head
    # twice, and the model arm below reads the same value the result publishes.
    stage = _derive_stage(config, state, workflow_dir, entity_dir, now, window_sec)

    # The short-circuit bypasses the model entirely: a no-goal session must
    # never produce a fabricated goal, regardless of what the model says.
    if goal != NO_GOAL and model is not None:
        recent = " ".join(msg["text"] for msg in messages[-_MODEL_CONTEXT_MESSAGES:])
        # Bounded like every other string that crosses this boundary. The rest
        # of the module caps what it *publishes*; this caps what it hands out,
        # because a transcript tail is the one unbounded value here and the
        # callable is not this module's code.
        recent = records.safe_text(recent, config.observer_model_context_chars)
        try:
            enhanced = model(recent, stage)
        except Exception:  # noqa: BLE001 — a model failure degrades, never crashes
            enhanced = None
        if isinstance(enhanced, str) and enhanced.strip():
            goal = records.safe_text(enhanced.strip(), config.observer_goal_cap_chars)

    block = _derive_block(config, messages)
    return {"goal": goal, "stage": stage, "block": block, "reason": reason}


def sidecar_path(config: RuntimeConfig, harness: str, sid: str) -> str | None:
    r"""The sidecar path for one session, or None if either name is not a name.

    The sidecar lives under the observer's own store (``config.state_dir``),
    never under the observed session's repo or state tree — and the check that
    keeps it there is the grammar, not the join. ``safe_text`` strips control
    characters and truncates; it passes ``/``, ``\`` and ``..`` straight
    through, so a session id carrying separators walked out of the store and
    truncated whatever it landed on. Both components must be plain names.
    """
    if not _SAFE_ID_RE.match(harness) or not _SAFE_ID_RE.match(sid):
        return None
    root = os.path.join(str(config.state_dir), "observer")
    path = os.path.join(root, f"{harness}_{sid}.json")
    # Belt as well as braces: the grammar above is the guard, and this asserts
    # the result of the join rather than trusting it, the way
    # `spacedock.read_workflow` asserts its README's containment.
    if os.path.dirname(os.path.normpath(path)) != os.path.normpath(root):
        return None
    return path


def write_sidecar(
    config: RuntimeConfig, harness: str, sid: str, result: dict[str, Any]
) -> str | None:
    """Write the observer sidecar to the observer's own store; return its path.

    None when the names are not writable ones, which is a refusal rather than a
    fallback: there is no second location a sidecar belongs in. None as well
    when the write itself fails, so that an `OSError` cannot reach the handler
    and turn a full disk into an unhandled 500.

    What the caller then does with the derivation is NOT "serves it from memory",
    which an earlier draft of this docstring claimed: `http_api` answers 400 and
    discards it. That is the wrong code for a server-side write failure and the
    wrong disposal for work already done, but choosing between 200 with a
    best-effort sidecar and 500 is a route policy rather than a write concern, so
    this records the behaviour instead of asserting a better one. The `OSError`
    arm below is unreached by any test (see DRC-4269).

    Temp file plus `os.replace`, and `0o600` in the `os.open` call rather than a
    chmod afterwards, both the same shape as `lifecycle.write_state` and
    `dismissals.save` and for the same two reasons: a reader mid-write sees the
    old file or the new one, and the file is never briefly world-readable. This
    one holds prompt-derived text — the goal is the operator's own words, run
    through `records.safe_text` — which is why the mode matters on a file that
    used to inherit the umask. The mode is advisory and Windows ignores it, as
    `SECURITY.md` records for the other two.
    """
    path = sidecar_path(config, harness, sid)
    if path is None:
        return None
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        handle_fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(handle_fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(result))
        os.replace(tmp, path)
    except OSError:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        return None
    return path


def read_sidecar(config: RuntimeConfig, harness: str, sid: str) -> dict[str, Any] | None:
    """Read the observer sidecar, or None if absent, unnamed or malformed."""
    path = sidecar_path(config, harness, sid)
    if path is None:
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.loads(handle.read(config.state_read_cap_bytes))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _mtime(path: str) -> float:
    """One file's mtime, or 0 when it went away between the glob and the stat."""
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def resolve_transcript(
    config: RuntimeConfig,
    state: RuntimeState,
    harness: str,
    sid: str,
) -> str | None:
    """Find the transcript file path for one session, or None.

    A bounded glob over the harness's store roots, matching the session id
    against the first-line metadata the collectors already use. Read-only;
    no file is opened for writing.
    """
    if not _SAFE_ID_RE.match(harness) or not _SAFE_ID_RE.match(sid):
        return None
    if harness == "claude":
        # `projects/<encoded-cwd>/<session-id>.jsonl`: the transcripts are one
        # directory deeper than the store root, which `collectors/claude.py`
        # globs as ("*", "*.jsonl"). A flat glob here matched nothing, so
        # `?harness=claude` was a 404 on every machine.
        #
        # Matched on the stem and not with `sid in basename`, because a
        # substring match hands back whichever session happens to contain the
        # characters — `sid=a` observed an arbitrary transcript. The dashboard
        # shortens an id for display, so a prefix is accepted, and only when it
        # is unambiguous: two matches is no answer, not the first one.
        found = [
            path
            for path in runtime_io.glob_stores(config, "claude.projects", "*", "*.jsonl")
            if os.path.basename(path).removesuffix(".jsonl").startswith(sid)
        ]
        return found[0] if len(found) == 1 else None
    if harness == "codex":
        # `sessions/<yyyy>/<mm>/<dd>/rollout-<timestamp>-<uuid>.jsonl`. Neither
        # branch beside this one transfers: the Claude stem match cannot be
        # reused because a rollout's uuid sits at the *end* of the filename, and
        # Pi's `pi_meta` reads a different first line. So the id is matched
        # against `session_meta`, the same field `collectors/codex.py` keys on.
        #
        # One `session_id` is legitimately spread over several files: a resume
        # and each subagent thread write their own rollout under it. Those two
        # multiplicities are not the same, and they are resolved separately —
        # subagent threads are excluded, resumes are picked by newest mtime —
        # which is also the order `collectors/codex.py` does it in: it drops a
        # subagent rollout (`if meta.get("subagent"): continue`) before it keeps
        # the newest file per session id.
        #
        # Excluded and not merely outranked, because a subagent rollout carries
        # its PARENT's `session_id` — 262 of 262 locally — so max-mtime hands
        # back the child whenever the child is the file being written, and
        # `analyze` then publishes the parent agent's dispatch prompt as the
        # operator's goal. In 262 of 262 local subagent runs there is a window
        # where that is what the resolver returns, covering 32.8 h of 102.8 h of
        # aggregate subagent wall-clock; the frozen corpus shows 0 because every
        # one of its 31 mixed groups was measured after the parent resumed
        # writing. The meta is already read for the id match, so this is free.
        found = []
        for path in runtime_io.glob_stores(
            config, "codex.sessions", "*", "*", "*", "rollout-*.jsonl"
        ):
            meta = transcripts.codex_meta(config, state, path)
            if meta.get("subagent") or meta.get("session_id") != sid:
                continue
            found.append(path)
        return max(found, key=_mtime) if found else None
    if harness != "pi":
        return None
    # Pi's default store is nested and a custom one is flat, so both shapes are
    # globbed, the same pair `collectors/pi.py` reads.
    for pattern in (("*.jsonl",), ("*", "*.jsonl")):
        for path in runtime_io.glob_stores(config, "pi.sessions", *pattern):
            if transcripts.pi_meta(config, state, path).get("session_id") == sid:
                return path
    return None


def resolve_workflow(
    config: RuntimeConfig,
    state: RuntimeState,
    transcript_path: str,
) -> tuple[str | None, str | None]:
    """``(workflow_dir, entity_dir)`` from the transcript's boot records.

    Reuses the read-only boot scan the Spacedock cartography already proved
    safe. Both, not just the entity directory: the stage reader needs the
    workflow README's declared stages to discriminate what it reads out of the
    state directory, and the entity directory alone cannot produce them.

    ``(None, None)`` when the session runs no workflow, and also under
    ``--no-spacedock``, so the switch turns off the boot scan too rather than
    only the frontmatter reads behind it.
    """
    if not config.spacedock_enabled:
        return None, None
    boot = spacedock.transcript_boot(config, state, transcript_path)
    for workflow_dir in spacedock.workflow_dirs(config, boot):
        entity_dir = spacedock.boot_entity_dir(boot, workflow_dir)
        if entity_dir:
            return workflow_dir, entity_dir
    return None, None
