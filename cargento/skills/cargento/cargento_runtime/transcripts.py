"""Shared first-line metadata, prompt titles, and non-Claude transcript analysis."""

from __future__ import annotations

import json
import os
import re
import unicodedata
from typing import TYPE_CHECKING, Any, Final

from . import io as runtime_io
from . import records
from . import state as runtime_state

if TYPE_CHECKING:
    from collections.abc import Callable

    from .config import RuntimeConfig
    from .state import RuntimeState

# ---------------------------------------------------------------------------
# First-line metadata cache (JSONL harnesses write immutable line-1 metadata)


def first_line_meta(
    config: RuntimeConfig,
    state: RuntimeState,
    path: str,
    parse: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    """parse(first-line JSON dict) -> dict; cached per path. Not cached on
    read/parse failure so a partially written first line retries later."""
    with state.cache_lock:
        m = state.metadata_cache.get(path)
    if m is not None:
        return m
    d = runtime_io.read_first_json(config, path)
    if not d:
        return {}
    m = parse(d)
    with state.cache_lock:
        cached = state.metadata_cache.get(path)
        if cached is not None:
            return cached
        runtime_state.bounded_put(state.metadata_cache, path, m, limit=config.max_cache_entries)
        return m


def codex_meta(config: RuntimeConfig, state: RuntimeState, path: str) -> dict[str, Any]:
    """Codex rollout line 1 (session_meta): identity, cwd, and whether the
    file is a subagent thread (thread_source == "subagent")."""

    def parse(d: dict[str, Any]) -> dict[str, Any]:
        # Every field is untyped JSON from disk — one malformed rollout must
        # not AttributeError the whole Codex collector.
        p = d.get("payload")
        if not isinstance(p, dict):
            p = {}
        spawn = records.as_dict(
            records.as_dict(records.as_dict(p.get("source")).get("subagent")).get("thread_spawn")
        )
        nickname = p.get("agent_nickname")
        agent_path = p.get("agent_path")
        label = (
            nickname
            if isinstance(nickname, str) and nickname
            # basename(), not rsplit("/"): on Windows the recorded path is
            # backslash-separated, and a hardcoded "/" would keep the whole
            # path as the agent's label.
            else (
                os.path.basename(agent_path) if isinstance(agent_path, str) and agent_path else None
            )
        )
        return {
            "session_id": p.get("session_id") or p.get("id"),
            "parent_session_id": (
                spawn.get("parent_thread_id") if isinstance(spawn, dict) else None
            ),
            "cwd": p.get("cwd"),
            "subagent": p.get("thread_source") == "subagent",
            "agent_label": label or None,
        }

    return first_line_meta(config, state, path, parse)


def gemini_meta(config: RuntimeConfig, state: RuntimeState, path: str) -> dict[str, Any]:
    """Gemini chat recording line 1: sessionId, kind (main|subagent),
    directories (cwd list)."""

    def parse(d: dict[str, Any]) -> dict[str, Any]:
        dirs = d.get("directories")
        return {
            "session_id": d.get("sessionId"),
            "kind": d.get("kind"),
            "cwd": dirs[0] if isinstance(dirs, list) and dirs else None,
        }

    return first_line_meta(config, state, path, parse)


def copilot_meta(config: RuntimeConfig, state: RuntimeState, path: str) -> dict[str, Any]:
    """Copilot events.jsonl line 1 is normally session.start with
    data.context.cwd."""

    def parse(d: dict[str, Any]) -> dict[str, Any]:
        data = records.as_dict(d.get("data"))
        ctx = records.as_dict(data.get("context"))
        return (
            {"cwd": ctx.get("cwd") or data.get("cwd")} if d.get("type") == "session.start" else {}
        )

    return first_line_meta(config, state, path, parse)


def droid_meta(config: RuntimeConfig, state: RuntimeState, path: str) -> dict[str, Any]:
    """Droid transcript line 1 (session_start): id, session title, cwd."""

    def parse(d: dict[str, Any]) -> dict[str, Any]:
        if d.get("type") != "session_start":
            return {}
        return {
            "session_id": d.get("id"),
            "title": d.get("sessionTitle") or d.get("title"),
            "cwd": d.get("cwd"),
        }

    return first_line_meta(config, state, path, parse)


def pi_meta(config: RuntimeConfig, state: RuntimeState, path: str) -> dict[str, Any]:
    """Pi v3's immutable session header: identity and workspace only."""

    def parse(d: dict[str, Any]) -> dict[str, Any]:
        if d.get("type") != "session":
            return {}
        session_id = d.get("id")
        cwd = d.get("cwd")
        parent_session = d.get("parentSession")
        return {
            "session_id": session_id if isinstance(session_id, str) else None,
            "cwd": cwd if isinstance(cwd, str) else None,
            "parent_session": parent_session if isinstance(parent_session, str) else None,
        }

    return first_line_meta(config, state, path, parse)


# ---------------------------------------------------------------------------
# Prompt titles

# Harness-injected wrappers around a user prompt. A slash command arrives as
# `<command-name>/plugin</command-name>` and a dispatched worker's instructions
# as `<teammate-message teammate_id="...">`, so the naive "first line of the
# first prompt" title renders raw markup. Measured over 248 real transcripts,
# 138 titles began with one of these.
_PROMPT_TAG_RE = re.compile(r"</?[a-z][a-z0-9-]*(?:\s[^>]*?)?/?>", re.IGNORECASE)
_COMMAND_NAME_RE = re.compile(r"<command-name>\s*(.*?)\s*</command-name>", re.DOTALL)
_COMMAND_ARGS_RE = re.compile(r"<command-args>\s*(.*?)\s*</command-args>", re.DOTALL)
# A filesystem path, not a URL: `://` is excluded so a GitHub link survives
# whole, since the repo and PR number in it are the informative part. Absolute
# paths otherwise eat the entire title budget and say nothing a basename does
# not, and a dispatch prompt naming a UUID temp file is the worst of them.
_PROMPT_PATH_RE = re.compile(r"(?<!:)(?<![\w/])(?:~|/[^\s/]+)(?:/[^\s/]+)+/?")


def shorten_paths(config: RuntimeConfig, text: str) -> str:
    """Collapse long absolute filesystem paths in a title to their last segment."""

    def basename(match: re.Match[str]) -> str:
        path = match.group(0)
        # Only collapse a path long enough to be the problem this solves. Across
        # the transcripts sampled the median slash-run is 11 characters and the
        # 90th percentile is 140: the short ones are mostly not paths at all, and
        # collapsing them corrupts real content. `^/api/v1/users$` became
        # `^users$` before this.
        if len(path) < config.prompt_path_collapse_min_length:
            return path
        return path.rstrip("/").rpartition("/")[2] or path

    return _PROMPT_PATH_RE.sub(basename, text)


def clip(text: str, limit: int) -> str:
    """Trim to ``limit`` on a word boundary where one is close enough.

    Cutting mid-word reads as damage rather than as truncation: "tell all
    subagents and tea" looks like a bug. Falling back to a hard cut keeps the
    bound absolute for a single long token such as a URL.
    """
    if len(text) <= limit:
        return text
    head = text[:limit].rstrip()
    space = head.rfind(" ")
    # Only honour a boundary in the last third, so one long token cannot
    # shrink the title to a couple of words.
    kept = head[:space] if space > limit * 2 // 3 else head
    # A hard cut can land on punctuation, and ".…" reads as a typo.
    kept = kept.rstrip(" .,;:-_/(")
    # It can also land inside a decomposed grapheme, leaving accent marks whose
    # base character was cut away to combine with the ellipsis instead.
    while kept and unicodedata.combining(kept[-1]):
        kept = kept[:-1]
    return kept + "…"


def prompt_title(config: RuntimeConfig, text: str, limit: int = 80) -> str | None:
    """A readable one-line title from a raw user prompt, or None.

    Slash commands keep their name and any arguments, so `/plugin` reads as
    `/plugin` rather than as the markup it arrived in. Everything else has its
    wrapper tags removed and falls back to the first line with real content in
    it, which is what makes a `<teammate-message>` show the instruction instead
    of the envelope.
    """
    name = _COMMAND_NAME_RE.search(text)
    if name and name.group(1):
        args = _COMMAND_ARGS_RE.search(text)
        command = name.group(1).strip()
        argument = _PROMPT_TAG_RE.sub(" ", args.group(1)).strip() if args else ""
        joined = f"{command} {argument}".strip() if argument else command
        return clip(" ".join(shorten_paths(config, joined).split()), limit) or None
    for line in _PROMPT_TAG_RE.sub("", text).split("\n"):
        collapsed = " ".join(shorten_paths(config, line).split())
        if collapsed:
            return clip(collapsed, limit)
    return None


# ---------------------------------------------------------------------------
# Transcript analyzers (tail pass -> title, prompt, usage, activity)


def analyze_codex_transcript(config: RuntimeConfig, path: str) -> dict[str, Any]:
    """Codex rollout tail: user_message (prompt/title), token_count (usage),
    tool calls. Turn spans come from scan_turns; cwd/subagents from meta."""
    info: dict[str, Any] = {
        "title": None,
        "last_prompt": None,
        "usage_events": [],
        "last_tool": None,
        "last_event_ts": 0,
        "rate_limits": None,  # newest in the tail: (epoch, the raw rate_limits dict)
    }
    for line in runtime_io.read_tail(config, path):
        if not line or line[0] != "{":
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        ep = records.parse_ts(d.get("timestamp") or "")
        if ep:
            info["last_event_ts"] = max(info["last_event_ts"], ep)
        t = d.get("type")
        p = records.as_dict(d.get("payload"))
        if t == "event_msg":
            pt = p.get("type")
            if pt == "user_message":
                msg = p.get("message")
                msg = msg.strip() if isinstance(msg, str) else ""
                info["last_prompt"] = msg
                info["title"] = msg.split("\n")[0][:80] or None
            elif pt == "token_count":
                out = records.as_dict(records.as_dict(p.get("info")).get("last_token_usage")).get(
                    "output_tokens"
                )
                if ep and out:
                    info["usage_events"].append((ep, out))
                # Quota snapshot, written by the CLI beside the token figures.
                limits = records.as_dict(p.get("rate_limits"))
                held = info["rate_limits"]
                if ep and limits and (held is None or ep >= held[0]):
                    info["rate_limits"] = (ep, limits)
        elif t == "response_item" and p.get("type") in ("function_call", "custom_tool_call"):
            info["last_tool"] = p.get("name")
    return info


def analyze_gemini_transcript(config: RuntimeConfig, path: str) -> dict[str, Any]:
    """Gemini chats/*.jsonl tail: type 'user' | 'gemini' records with
    per-message tokens; resumed-session $set snapshots are expanded."""
    info: dict[str, Any] = {
        "title": None,
        "last_prompt": None,
        "usage_events": [],
        "last_tool": None,
        "last_event_ts": 0,
    }
    seen = set()
    for line in runtime_io.read_tail(config, path):
        if not line or line[0] != "{":
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        for message in records.gemini_records(d):
            fingerprint = records.record_fingerprint(message)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            ep = records.parse_ts(message.get("timestamp") or "")
            if ep:
                info["last_event_ts"] = max(info["last_event_ts"], ep)
            t = message.get("type")
            if t == "user":
                txt = records.extract_text(message.get("content")).strip()
                if txt:
                    info["last_prompt"] = txt
                    info["title"] = txt.split("\n")[0][:80]
            elif t == "gemini":
                toks = message.get("tokens") or {}
                if ep and isinstance(toks, dict) and toks.get("output"):
                    info["usage_events"].append((ep, toks["output"]))
                for tc in records.as_list(message.get("toolCalls")):
                    if isinstance(tc, dict) and tc.get("name"):
                        info["last_tool"] = tc.get("name")
    return info


def _copilot_agent_key(d: dict[str, Any], data: dict[str, Any]) -> str:
    """One subagent's identity, the same across its started/completed/failed events.

    ``agentId`` is tried first because it is the only candidate that holds the
    same value on all three, measured on a live store. The others do not:
    ``subagent.completed`` carries a *different* top-level ``id`` from
    ``subagent.started``, so keying on ``id`` never matched and the caller's
    drop-oldest fallback did all the retiring. That is accidentally right for one
    child and wrong for two — it retires whichever pill happens to be first —
    and now that a pill carries a model, the wrong model goes with the wrong
    label. ``agentId`` is also the value the billing ledger's ``agent_id`` column
    holds, though nothing joins on it; see ``collectors/copilot.py``.

    Coerced to text because the result is a dict key and the record is untrusted:
    a JSON list under ``agentId`` is unhashable, and one would raise out of the
    analyzer and take every other reading of the session with it.
    """
    for candidate in (d.get("agentId"), data.get("id"), data.get("subagentId"), d.get("id")):
        if isinstance(candidate, (str, int, float)) and not isinstance(candidate, bool):
            text = str(candidate)
            if text:
                return text
    return ""


# The two `permissionRequest.kind` spellings recorded in
# `docs/captures/copilot/permission-events-1.0.78-macos.jsonl`. Nothing else is
# published: the value reaches a session card, and an allow-list of a closed
# vendor vocabulary is the only version of that which cannot put an unmeasured
# string on screen. A kind added upstream falls back to an unqualified wait,
# which still reports the gate.
_COPILOT_PERMISSION_KINDS: Final = frozenset({"shell", "url"})


def _copilot_request_key(data: dict[str, Any]) -> str:
    """One permission request's identity, or "" when the record does not carry one.

    ``data.requestId`` and nothing else: it is 1:1 across requested/completed in
    6 of 6 pairs in the capture, which is what lets an answer close the gate it
    actually answered rather than whichever one is open.

    Coerced to text for the same reason ``_copilot_agent_key`` is — the result is
    a dict key and the record is untrusted, so an unhashable value would raise out
    of the analyzer and take every other reading of the session with it. "" is
    returned for a request with no usable id, and the caller drops it: a gate that
    cannot be keyed cannot ever be closed, so recording one would leave a session
    red for the rest of its life.
    """
    value = data.get("requestId")
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return str(value)
    return ""


def _copilot_permission_kind(data: dict[str, Any]) -> str | None:
    """What kind of thing is being asked about, or None when it is not a known one.

    ``permissionRequest.kind`` is read and branched on before anything else under
    it, because the key set is kind-dependent rather than a union: ``kind="url"``
    carries ``{intention, kind, toolCallId, url}`` and none of the shell keys. An
    adapter written from a flattened key list reads fields that do not exist.

    Nothing else under ``permissionRequest`` is read at all. ``fullCommandText``,
    ``commands``, ``commandSegments``, ``possiblePaths``, ``possibleUrls`` and
    ``intention`` are the command line and a model's prose, which is the class
    ``docs/captures/README.md`` excludes and which has no business on a card.
    """
    request = records.as_dict(data.get("permissionRequest"))
    kind = request.get("kind")
    return kind if kind in _COPILOT_PERMISSION_KINDS else None


def analyze_copilot_events(config: RuntimeConfig, path: str) -> dict[str, Any]:
    """Copilot events.jsonl tail: typed events with data payloads. Field
    names inside data are de-facto (not a stable API) — extracted
    defensively."""
    info: dict[str, Any] = {
        "title": None,
        "last_prompt": None,
        "usage_events": [],
        "last_tool": None,
        "last_event_ts": 0,
        "cwd": None,
        # Started-but-not-finished subagents, one `{"name": str, "model": str |
        # None}` each. This is an internal pre-publication shape: the collector
        # adds the always-present `started_at` key, which stays None because
        # Copilot exposes no child transcript here. `model` is the child's own
        # reading and None means the event did not report one — never a guess.
        #
        # The model is carried raw and bounded by the collector, which caps it to
        # the width `sessions` declares for every model on the payload. That
        # width cannot be read from here: this module may not import `sessions`
        # (`test_contracts` pins the runtime import graph), and a second literal
        # 40 beside the declared one is how two caps drift apart. The collector
        # already sanitises the session's own model through one function, so the
        # child goes through the same door rather than a copy of it.
        "pending_agents": {},
        # Permission requests with no answer behind them, `requestId ->
        # {"at": float, "kind": str | None}` in the order they were asked. A
        # non-empty map at the end of the tail is a prompt standing in front of a
        # person: the capture has `permission.requested` on disk in the first
        # frame the dialog is visible, and `permission.completed` arriving only
        # when they answer, 23-48 s later.
        #
        # `at` is the request's own timestamp and 0 when it would not parse; the
        # collector dates the wait from it. `kind` is the closed vocabulary above
        # and nothing else from the request is carried, so no command line and no
        # model's prose can reach a card through this map.
        #
        # Bounded by the tail read, like every other accumulator here. Truncation
        # can only lose a request, never invent one, because the file is append
        # ordered and an answer never precedes its own question.
        #
        # Two things empty it: the answer, and a later `user.message`. The second
        # is the liveness bound — see the branch that does it.
        "pending_permissions": {},
    }
    for line in runtime_io.read_tail(config, path):
        if not line or line[0] != "{":
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        ep = records.parse_ts(d.get("timestamp") or "")
        if ep:
            info["last_event_ts"] = max(info["last_event_ts"], ep)
        t = d.get("type")
        data = records.as_dict(d.get("data"))
        if t == "session.start":
            ctx = records.as_dict(data.get("context"))
            info["cwd"] = ctx.get("cwd") or data.get("cwd") or info["cwd"]
        elif t == "user.message":
            # A prompt the person typed retires every request standing in front
            # of it, and this is the only thing that retires one but the answer.
            # A request whose answer never reached disk — the terminal closed on
            # the dialog, the process killed — otherwise stands for the whole
            # activity window, and it outranks the busy test, so a session that
            # was resumed and is demonstrably working reads Needs input against
            # its own live activity.
            #
            # Keyed on `user.message` and not on "any record written after the
            # request", which is the wider rule the same evidence would allow:
            # the capture has the file quiescent for the whole 36, 44 and 48 s a
            # gate stood, so nothing at all follows a standing request there. But
            # those arms ran no subagent, and a child writing into the parent's
            # file while the parent's dialog stands would silence a real gate
            # under exactly the fan-out where a gate is most likely. A typed
            # prompt needs no such assumption: the dialog owns the input while it
            # is up, so a new user message means it is gone.
            info["pending_permissions"].clear()
            txt = records.extract_text(data).strip()
            if txt:
                info["last_prompt"] = txt
                info["title"] = txt.split("\n")[0][:80]
        elif t == "tool.execution_start":
            name = data.get("toolName") or data.get("name") or data.get("tool")
            if name:
                info["last_tool"] = str(name)
        elif t == "permission.requested":
            request_key = _copilot_request_key(data)
            if request_key:
                info["pending_permissions"][request_key] = {
                    "at": ep,
                    "kind": _copilot_permission_kind(data),
                }
        elif t == "permission.completed":
            # Every `result.kind` closes it, and that is the measured part rather
            # than a simplification. The capture records four spellings —
            # `approved`, `cancelled`, `denied-interactively-by-user`, and
            # `denied-no-approval-rule-and-could-not-request-from-user` — and the
            # last is a headless auto-denial that opens and closes its pair in
            # 1 ms. Branching on the answer would either hold a denied session red
            # forever or flicker a card for every run nobody is watching; the
            # question is over either way, so the join is on `requestId` alone.
            info["pending_permissions"].pop(_copilot_request_key(data), None)
        elif t == "subagent.started":
            label = (
                data.get("name")
                or data.get("agentName")
                or data.get("agent")
                or data.get("agentType")
                or "subagent"
            )
            # The model comes off the same JSON object the label does, so the two
            # are paired by construction rather than by a join. That is the whole
            # reason this is the source: the ledger's `agent_id` is
            # `sidekick-<agentName>-<epoch ms>`, related to the published label by
            # string construction only, and recovering one from the other means
            # prefix-parsing an id — inference, which a measured value must never
            # be mixed with.
            raw = data.get("model")
            info["pending_agents"][_copilot_agent_key(d, data)] = {
                "name": records.safe_text(label, 70),
                "model": raw if isinstance(raw, str) and raw.strip() else None,
            }
        elif t in ("subagent.completed", "subagent.failed"):
            # `failed` retires the pill for the same reason `completed` does: the
            # child is not running. It was unhandled, so a failed subagent kept
            # its pill for the rest of the session — measured live, on a child
            # that failed with "No response generated" — and it would now keep a
            # model badge with it.
            key = _copilot_agent_key(d, data)
            if key in info["pending_agents"]:
                info["pending_agents"].pop(key)
            elif info["pending_agents"]:  # unmatched key scheme: drop oldest
                info["pending_agents"].pop(next(iter(info["pending_agents"])))
    return info


def analyze_droid_transcript(config: RuntimeConfig, path: str) -> dict[str, Any]:
    """Droid transcript tail: {type: "message", timestamp, message: {role,
    content: [Anthropic-style blocks]}}."""
    info: dict[str, Any] = {
        "title": None,
        "last_prompt": None,
        "usage_events": [],
        "last_tool": None,
        "last_event_ts": 0,
    }
    for line in runtime_io.read_tail(config, path):
        if not line or line[0] != "{":
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        ep = records.parse_ts(d.get("timestamp") or "")
        if ep:
            info["last_event_ts"] = max(info["last_event_ts"], ep)
        if d.get("type") != "message":
            continue
        msg = records.message_dict(d)
        content = msg.get("content")
        blocks = content if isinstance(content, list) else []
        if msg.get("role") == "user":
            if any(isinstance(c, dict) and c.get("type") == "tool_result" for c in blocks):
                continue
            txt = records.extract_text(content).strip()
            if txt:
                info["last_prompt"] = txt
                info["title"] = txt.split("\n")[0][:80]
        elif msg.get("role") == "assistant":
            for c in blocks:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    info["last_tool"] = c.get("name")
    return info
