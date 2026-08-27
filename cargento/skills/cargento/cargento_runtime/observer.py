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

# A rendered directive that is one slash-command token and nothing else. The
# name is matched against the set below; the shape only isolates it.
_BARE_COMMAND_RE = re.compile(r"^/([A-Za-z0-9][A-Za-z0-9:._-]*)$")

# Slash commands that drive the harness rather than the work, with their
# occurrence counts as the last published goal in the local corpus. Shared
# across harnesses rather than split per harness, on `records`'s reasoning for
# its injected-prose prefixes: `clear` and `login` were measured in both, and
# none of the rest is a name one harness could mean differently.
_HARNESS_CONTROL_COMMANDS = frozenset(
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
_BLOCK_INDICATORS = (
    "i'm blocked",
    "i am blocked",
    "i'm stuck",
    "i am stuck",
    "waiting for you",
    "waiting for your",
    "waiting for approval",
    "not permitted",
    "permission denied",
)


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
    """Whether a user message is a generic skill-load directive, not a goal."""
    stripped = text.strip().lower()
    return any(stripped.startswith(prefix) for prefix in _GENERIC_OPENER_PREFIXES)


def _is_harness_control(rendered: str | None) -> bool:
    """Whether a *rendered* directive is a harness control rather than a goal.

    Applied to what `prompt_title` produces, not to the raw record, which is why
    the guard beside it could not do this job: `_is_generic_opener` reads
    `<command-name>/clear</command-name>` and the value actually published is
    `/clear`. The two spellings never met, so 200 of 1,469 published Claude
    goals (13.6%) and 4 of 141 Codex ones were a bare `/clear`, `/login`,
    `/plugin` or `/mcp` sitting in the ordinary goal slot, indistinguishable
    from a derived objective; in 25 of them a real objective the session
    contained was displaced.

    A measured name list and NOT the structural rule "a bare command carries no
    arguments, so it carries no goal". That rule was checked against the same
    corpus first and is wrong: 39 further bare-command goals are skill
    invocations — `/create-pr`, `/cargento:cargento`, `/security-review` — and
    a skill invoked with no arguments is exactly what the operator asked for.
    Argument-carrying commands are untouched either way; `prompt_title` renders
    those as `/code-review 1287 with fresh eyes`, which never matches here.
    """
    match = _BARE_COMMAND_RE.match(rendered or "")
    return match is not None and match.group(1).casefold() in _HARNESS_CONTROL_COMMANDS


# `type: "message"` is Pi's shape and Droid's, and `_parse_message_record`
# deliberately takes no harness parameter (the shapes below are disjoint across
# the whole local corpus, so the union needs no gate). That leaves the shared
# shape with no single name to hand the injected-tag lookup, which is exactly
# the case `records.injected_prompt` documents: a harness it has no measured
# vocabulary for gets the union of every measured set.
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


def _message_from(role: Any, content: Any, harness: str) -> dict[str, str] | None:
    """The (role, text) pair for one already-unwrapped message, or None.

    The one place the injected-shape rejection is applied, so every harness arm
    below gets it. Without it, teaching the parser the Claude and Codex shapes
    would publish a harness's own machinery as the operator's goal on 51.6% of
    Codex rollouts and 62.5% of Claude sessions — a confident wrong answer where
    there is a silent sentinel today, which is the worse of the two failures.
    """
    if role not in ("user", "assistant"):
        return None
    if _blocks_carry_tool_result(content):
        return None
    text = records.extract_text(content).strip()
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


def _claude_message(record: dict[str, Any], record_type: str) -> dict[str, str] | None:
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
    return _message_from(message.get("role") or record_type, message.get("content"), "claude")


def _parse_message_record(record: Any) -> dict[str, str] | None:
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
        return _message_from(message.get("role"), message.get("content"), _SHARED_MESSAGE_HARNESS)
    if record_type in ("user", "assistant"):
        return _claude_message(record, record_type)
    if record_type == "response_item":
        payload = records.as_dict(record.get("payload"))
        if payload.get("type") != "message":
            return None
        return _message_from(payload.get("role"), payload.get("content"), "codex")
    return None


def _dedup_key(record: dict[str, Any]) -> str:
    """The record's own identity, or empty when it carries none.

    Not ``record["id"]``, which is what this read before: **0 of 8,312 Claude
    and 0 of 14,389 Codex records carry a top-level ``id``**, so the key
    degraded silently to the message text and a prompt repeated verbatim later
    in the session kept its first, oldest position. Claude spells it ``uuid``
    and Codex ``payload.id``; Pi and Droid do spell it ``id``.
    """
    for value in (
        record.get("uuid"),
        record.get("id"),
        records.as_dict(record.get("payload")).get("id"),
    ):
        if isinstance(value, str) and value:
            return value
    return ""


def _extract_messages(config: RuntimeConfig, path: str) -> list[dict[str, str]]:
    """User and assistant texts from a JSONL transcript, head + tail bounded.

    The head carries the opening directive; the tail carries the recent window.
    Records are deduped by their own id so the overlap region between head and
    tail does not double-count, and returned in **record-timestamp** order.

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
    try:
        head = runtime_io.read_prefix_bytes(path, max_bytes=config.observer_head_bytes)
    except OSError:
        head = b""
    head_lines = head.decode("utf-8", "replace").split("\n")
    tail_lines = runtime_io.read_tail(config, path)
    ordered: list[tuple[float, int, dict[str, str]]] = []
    seen: set[str] = set()
    # Carried forward so a stampless record sorts beside the stamped one before
    # it rather than ahead of the whole file.
    last_ts = 0.0
    for position, raw in enumerate(head_lines + tail_lines):
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
        parsed = _parse_message_record(record)
        if parsed is None:
            continue
        key = _dedup_key(record) or parsed["text"]
        if key in seen:
            continue
        seen.add(key)
        ordered.append((last_ts, position, parsed))
    ordered.sort(key=lambda item: (item[0], item[1]))
    return [parsed for _ts, _position, parsed in ordered]


def _user_directives(config: RuntimeConfig, messages: list[dict[str, str]]) -> list[str]:
    """Concrete user directives, newest last, openers and controls dropped.

    Two rejections, and they read different spellings of the same message on
    purpose: `_is_generic_opener` reads the raw text, `_is_harness_control`
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
        if _is_harness_control(rendered):
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
    # `_is_harness_control` above, on the rendered name) — but published raw
    # it reads as `<command-message>…`, which was 60 of 400 Claude sessions and
    # 5 of 457 Codex rollouts. `prompt_title`
    # already owns that rendering (`/review 1287 — with fresh eyes`), and
    # strips the wrapper tags off everything else.
    goal = transcripts.prompt_title(config, directives[-1], limit=config.observer_goal_cap_chars)
    if not goal:
        return NO_GOAL, None
    return records.safe_text(goal, config.observer_goal_cap_chars), None


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
            pos = lower.find(indicator)
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
    fallback: there is no second location a sidecar belongs in.
    """
    path = sidecar_path(config, harness, sid)
    if path is None:
        return None
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(result))
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
