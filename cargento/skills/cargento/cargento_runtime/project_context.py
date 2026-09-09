"""Read-only observer, gate, and captain-instruction context for one project."""

from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from . import claude_data, observer, records, semantic_history, spacedock, transcripts
from . import io as runtime_io
from . import sessions as runtime_sessions
from . import state as runtime_state

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from .config import RuntimeConfig
    from .state import RuntimeState

MAX_PROJECT_EVENTS = 100
MAX_PROJECT_OBSERVERS = 3
MAX_PROJECT_ATTENTION_SESSIONS = 64
MAX_ACTIVE_CHILD_OBSERVERS = 3
MAX_SEMANTIC_LINE = 112
SEMANTIC_CURRENT_HORIZON_SEC = 15 * 60
SEMANTIC_BURST_EPSILON_SEC = 2
MAX_PRIMARY_ACTIVITY_NODES = 5
MAX_PRIMARY_STEERING_NODES = 3
SEMANTIC_HISTORY_HORIZON_SEC = 24 * 60 * 60
SEMANTIC_BACKFILL_MAX_BYTES = 32 * 1024 * 1024
WORKFLOW_DISCOVERY_TIMEOUT_SEC = 2.0
WORKFLOW_DISCOVERY_CACHE_SEC = 30.0
WORKFLOW_DISCOVERY_MAX_BYTES = 64 * 1024
WORKFLOW_DISCOVERY_MAX_DIRS = 64
WORKFLOW_DISCOVERY_SOURCE = "spacedock status --discover"

_DIRECTIVE_PREFIX_RE = re.compile(
    r"^(?:please\s+|captain(?:\s+(?:says|asks|adds|clarifies|refines|clarification|refinement|correction))?\s*[:—-]\s*)+",
    re.IGNORECASE,
)
_DIRECTIVE_TAGS = (
    ("corrected", ("correction", "correct this", "fix the")),
    ("reframed", ("reframe", "refinement", "clarification", "change direction")),
    ("answered", ("answer to", "answered")),
    ("generated", ("new acceptance", "add a new", "create a new")),
)
_TASK_DIRECTIVE_RE = re.compile(
    r"^(?:add|append|build|compare|create|design|diagnose|fix|implement|inspect|make|"
    r"prepare|remove|replace|review|revise|run|test|update|verify|write)\b",
    re.IGNORECASE,
)
_AUTHORIZATION_ANSWER_RE = re.compile(
    r"\b(?:approve|authorize)(?:d)?\b[^.\n]*\bpush(?:ing)?\b[^.\n]*\bPR\b",
    re.IGNORECASE,
)
_AUTHORIZATION_RESULT_RE = re.compile(
    r"\bpush(?:ed|ing)\b[^.\n]*\b(?:created|opened|published)\b[^.\n]*\bPR\b",
    re.IGNORECASE,
)
_SEMANTIC_FACT_TYPES = {
    "steer": "user_message",
    "prepared_dispatch": "prepared_dispatch",
    "task_started": "work_birth",
    "task_result": "work_result",
    "outcome": "result",
    "gate": "gate_decision",
    "checkpoint": "result",
    "decision": "decision",
    "test_result": "result",
    "ask_resolution": "decision",
}
_DISPATCH_BUILD_RE = re.compile(r"^\s*spacedock\s+dispatch\s+build(?:\s+(.*))?$", re.IGNORECASE)
# This is transcript grammar from the dispatch contract, not a location we create or write.
_DISPATCH_DIRECTORY = "/tmp/spacedock-dispatch"  # noqa: S108 — legacy producer path; checked file reads below.
DISPATCH_MAX_BYTES = 64 * 1024
_DISPATCH_FILE_PREFIX = f"{_DISPATCH_DIRECTORY}/spacedock-ensign-"
_DISPATCH_VALUE_OPTIONS = {
    "--checklist-file",
    "--host",
    "--stage",
    "--stamp",
    "--workflow-dir",
}
_CODEX_ENSIGN_TASK_RE = re.compile(r"^spacedock_ensign_([a-z0-9_]+?)(?:_cycle\d+)?$")


def _discovery_result(state: str, reason: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {
        "state": state,
        "source": WORKFLOW_DISCOVERY_SOURCE,
        "workflows": [],
    }
    if reason:
        result["reason"] = reason
    return result


def _parse_discovery_output(
    config: RuntimeConfig,
    state: RuntimeState,
    root: str,
    stdout: object,
) -> dict[str, Any]:
    if not isinstance(stdout, str) or (
        len(stdout.encode("utf-8", "replace")) > WORKFLOW_DISCOVERY_MAX_BYTES
    ):
        return _discovery_result("error", "Spacedock discovery returned invalid output")
    raw_paths = [line.strip() for line in stdout.splitlines() if line.strip()]
    base = os.path.realpath(os.path.join(root, ".spacedock"))
    workflows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_path in raw_paths[:WORKFLOW_DISCOVERY_MAX_DIRS]:
        if not os.path.isabs(raw_path):
            continue
        candidate = os.path.realpath(raw_path)
        try:
            contained = os.path.commonpath((base, candidate)) == base
        except ValueError:
            contained = False
        name = os.path.basename(candidate)
        if (
            not contained
            or os.path.dirname(candidate) != base
            or not name
            or name in seen
            or not os.path.isdir(candidate)
        ):
            continue
        seen.add(name)
        definition = spacedock.read_workflow(
            config,
            state,
            candidate,
            definition_root=base,
        )
        workflows.append(
            {
                "workflow": name,
                "goal": str((definition or {}).get("goal") or ""),
                "stages": list((definition or {}).get("stages") or []),
                "definition": "read" if definition is not None else "unavailable",
            }
        )
    if raw_paths and not workflows:
        return _discovery_result(
            "error", "Spacedock discovery returned no valid project workflow paths"
        )
    result = _discovery_result("observed" if workflows else "none")
    result["workflows"] = workflows
    return result


def _run_project_workflow_discovery(
    config: RuntimeConfig,
    state: RuntimeState,
    root: str,
    runner: Any,
    binary_resolver: Any = shutil.which,
) -> dict[str, Any]:
    executable = os.environ.get("SPACEDOCK_BIN") or binary_resolver("spacedock")
    if not executable or not os.path.isabs(executable):
        return _discovery_result(
            "unavailable", "Spacedock discovery command requires an absolute path"
        )
    argv = [executable, "status", "--discover"]
    try:
        completed = runner(
            argv,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=WORKFLOW_DISCOVERY_TIMEOUT_SEC,
            check=False,
            shell=False,
            env={"PATH": os.defpath, "HOME": config.home, "LANG": "C.UTF-8"},
        )
    except FileNotFoundError:
        return _discovery_result("unavailable", "Spacedock discovery command unavailable")
    except subprocess.TimeoutExpired:
        return _discovery_result("error", "Spacedock discovery timed out")
    except (OSError, ValueError):
        return _discovery_result("error", "Spacedock discovery could not run")
    if completed.returncode != 0:
        return _discovery_result(
            "error", f"Spacedock discovery exited with status {completed.returncode}"
        )
    return _parse_discovery_output(config, state, root, completed.stdout)


def discover_project_workflows(
    config: RuntimeConfig,
    state: RuntimeState,
    project_root: str,
    *,
    now: float,
    runner: Any = subprocess.run,
    binary_resolver: Any = shutil.which,
    force: bool = False,
) -> dict[str, Any]:
    """Discover commissioned workflows from one verified project root.

    Spacedock owns workflow discovery. Cargento invokes its fixed read-only
    command without a shell, then accepts only immediate children of this
    project's ``.spacedock`` directory. The browser receives derived plan
    scalars, never filesystem paths or a way to invoke the command itself.
    """
    if not config.spacedock_enabled:
        return _discovery_result("unavailable", "Spacedock observation is disabled")
    root = os.path.realpath(project_root)
    if not os.path.isabs(project_root) or not os.path.isdir(root):
        return _discovery_result("unavailable", "project root unavailable")
    with state.cache_lock:
        cached = state.spacedock_discovery_cache.get(root)
    if cached and not force and now - cached[0] < WORKFLOW_DISCOVERY_CACHE_SEC:
        return copy.deepcopy(cached[1])

    result = _run_project_workflow_discovery(config, state, root, runner, binary_resolver)

    detached = copy.deepcopy(result)
    with state.cache_lock:
        runtime_state.bounded_put(
            state.spacedock_discovery_cache,
            root,
            (now, detached),
            limit=config.max_cache_entries,
        )
    return copy.deepcopy(detached)


def _transcript_cwd(
    config: RuntimeConfig,
    state: RuntimeState,
    harness: str,
    transcript_path: str,
) -> str:
    if harness == "claude":
        return claude_data.session_cwd(config, state, transcript_path)
    if harness == "codex":
        return str(transcripts.codex_meta(config, state, transcript_path).get("cwd") or "")
    if harness == "pi":
        return str(transcripts.pi_meta(config, state, transcript_path).get("cwd") or "")
    return ""


def _project_workflow_discovery(
    config: RuntimeConfig,
    state: RuntimeState,
    analysis_sessions: Sequence[Mapping[str, Any]],
    project: str,
    *,
    now: float,
    refresh: bool,
    runner: Any = subprocess.run,
    binary_resolver: Any = shutil.which,
) -> dict[str, Any]:
    for session in analysis_sessions:
        harness = str(session.get("harness") or "")
        sid = str(session.get("sid") or "")
        transcript_path = observer.resolve_transcript(config, state, harness, sid)
        if transcript_path is None:
            continue
        cwd = _transcript_cwd(config, state, harness, transcript_path)
        identity = runtime_sessions.project_identity(config, cwd)
        root = runtime_sessions.project_root(cwd)
        recorded_key = str(session.get("project_key") or "")
        recorded_label = str(session.get("project") or "")
        if not root or not identity:
            continue
        # The transcript cwd must agree with the collector's stable identity.
        # A label-only legacy request remains valid only for its own session.
        if recorded_key and recorded_key != identity.get("key"):
            continue
        if project not in {identity.get("key"), recorded_key, recorded_label}:
            continue
        return discover_project_workflows(
            config,
            state,
            root,
            now=now,
            runner=runner,
            binary_resolver=binary_resolver,
            force=refresh,
        )
    return _discovery_result("unavailable", "project root unavailable from observed sessions")


def _semantic_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8", "replace")
    return f"{prefix}:{hashlib.sha256(payload).hexdigest()[:16]}"


def _transcript_signature(transcript_path: str) -> dict[str, int] | None:
    try:
        info = os.stat(transcript_path)
    except OSError:
        return None
    return {"size": info.st_size, "mtime_ns": info.st_mtime_ns}


def _observe_session(
    config: RuntimeConfig,
    state: RuntimeState,
    transcript_path: str,
    identity: tuple[str, str],
    *,
    now: float,
    refresh: bool,
    child_activity_fallback: bool = False,
    model_consent: bool = False,
) -> dict[str, Any] | None:
    harness, sid = identity
    signature = _transcript_signature(transcript_path)
    cached = observer.read_sidecar(config, harness, sid)
    cached_payload = cached if isinstance(cached, dict) else {}
    raw_cached_model = cached_payload.get("model")
    cached_model = raw_cached_model if isinstance(raw_cached_model, dict) else {}
    if not refresh:
        observed_at = cached_payload.get("observed_at")
        goal = cached_payload.get("goal")
        if not isinstance(observed_at, (int, float)) or not isinstance(goal, str):
            return None
        model_metadata = dict(cached_model)
        model_metadata["status"] = (
            "cached" if cached_payload.get("transcript") == signature else "cached-stale"
        )
        return {
            "goal": goal,
            "stage": cached_payload.get("stage"),
            "block": cached_payload.get("block"),
            "reason": cached_payload.get("reason"),
            "model": model_metadata,
            "observed_at": observed_at,
            "snapshot_status": model_metadata["status"],
        }

    caller = observer.CodexGoalModel(
        config,
        child_assignment=child_activity_fallback,
        consent=model_consent,
        session_key=f"{harness}:{sid}",
    )
    model = caller if config.observer_model_enabled and model_consent else None
    result = observer.analyze(
        config,
        state,
        transcript_path,
        now=now,
        window_sec=config.window_hours * 3600,
        model=model,
    )
    if child_activity_fallback and model is not None and result.get("goal") == observer.NO_GOAL:
        result["goal"] = observer.derive_child_assignment(config, transcript_path, model)
        if result["goal"] != observer.NO_GOAL:
            result["reason"] = "derived-from-readable-child-activity"
    model_metadata = caller.metadata()
    sidecar = {
        **result,
        "model": model_metadata,
        "transcript": signature,
        "observed_at": now,
    }
    observer.write_sidecar(config, harness, sid, sidecar)
    return {
        **result,
        "model": model_metadata,
        "observed_at": now,
        "snapshot_status": "refreshed",
    }


def _instruction_event(
    config: RuntimeConfig,
    record: Any,
    harness: str,
    sid: str,
) -> dict[str, Any] | None:
    """One timestamped user-role message, excluding known tool/meta records."""
    if not isinstance(record, dict):
        return None
    message = observer.parse_message_record(record)
    if message is None or message.get("role") != "user":
        return None
    at = records.parse_ts(record.get("timestamp") or "")
    text = message["text"].strip()
    if at is None or not text:
        return None
    title = _semantic_line(text, min(MAX_SEMANTIC_LINE, config.observer_goal_cap_chars))
    if not title:
        return None
    event: dict[str, Any] = {
        "at": at,
        "kind": "steer",
        "phase": "user-role instruction",
        "title": title,
        "source": "timestamped non-meta user-role record",
        "harness": harness,
        "sid": sid,
        "intent_promotable": _intent_promotable(text, title),
    }
    record_id = record.get("id")
    if isinstance(record_id, str) and record_id:
        event["record_id"] = record_id
        event["turn_id"] = record_id
        event["branch_id"] = record_id
    parent_id = record.get("parentId")
    if isinstance(parent_id, str) and parent_id:
        event["parent_id"] = parent_id
    lower = text.casefold()
    for tag, markers in _DIRECTIVE_TAGS:
        if any(marker in lower for marker in markers):
            event["steering_tag"] = tag
            event["tag_source"] = "explicit user-role wording"
            break
    return event


def _intent_promotable(text: str, title: str) -> bool:
    """Reject rows that cannot stand alone as a useful semantic directive."""
    normalized = re.sub(r"[^a-z0-9]+", " ", title.casefold()).strip()
    if normalized in {
        "continue",
        "do it",
        "go ahead",
        "no",
        "ok",
        "okay",
        "why do we need that",
        "why do we need this",
        "yes",
    }:
        return False
    lowered = text.lstrip().casefold()
    stripped_title = title.strip()
    looks_like_non_intent = (
        re.match(r"^[,.;:)}\]]", stripped_title) is not None
        or re.match(
            r"^(?:raise\s+[a-z_][a-z0-9_]*\s*\(|(?:find|ls|cat|sed|rg)\s+(?:~?/|\.\.?/))",
            stripped_title,
            re.IGNORECASE,
        )
        is not None
        or re.match(r"^(?:saved|wrote|written|created)\b.*\s(?:to|at)\s+/", lowered) is not None
    )
    if looks_like_non_intent:
        return False
    if lowered.startswith(
        (
            "command failed",
            "error:",
            "exception:",
            "fatal:",
            "traceback (most recent call last)",
        )
    ):
        return False
    if re.match(
        r"^(?:\.?\.?/|\.venv/|python(?:3)?\s|uv\s+run\s|npm\s|pytest(?:\s|$))",
        lowered,
    ):
        return False
    words = re.findall(r"[a-z0-9]+", normalized)
    return len(words) >= 3 and len(normalized) >= 12


def _semantic_line(text: str, limit: int) -> str:
    """A short directive/task label from real text, without its envelope prose."""
    candidates: list[str] = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("#*- ").strip()
        if not line or line.startswith(("<", "```", "Message Type:", "Task name:", "Sender:")):
            continue
        line = _DIRECTIVE_PREFIX_RE.sub("", line)
        if not line:
            continue
        candidates.append(line)
    if not candidates:
        return ""
    chosen = candidates[0]
    sentence = re.split(r"(?<=[.!?])\s+", chosen, maxsplit=1)[0]
    sentence = re.sub(r"\s+", " ", sentence).strip()
    return records.safe_text(sentence, limit)


def _task_assignment(text: str, artifact: str) -> str:
    """Select the current task directive, not a preceding status sentence."""
    if artifact:
        return ""
    candidates: list[tuple[int, int, str]] = []
    for index, raw in enumerate(text.splitlines()):
        line = raw.strip().lstrip("#*- ").strip()
        if not line or line.startswith(("```", "Message Type:", "Task name:", "Sender:")):
            continue
        task_match = re.match(r"^Task:\s*(.+)$", line, re.IGNORECASE)
        if task_match:
            candidates.append((4, index, task_match.group(1)))
            continue
        if _TASK_DIRECTIVE_RE.match(line):
            priority = 5 if "stage report" in line.casefold() else 3
            candidates.append((priority, index, line))
    if candidates:
        _priority, _index, chosen = max(candidates, key=lambda item: (item[0], -item[1]))
        return _semantic_line(chosen, MAX_SEMANTIC_LINE)
    return _semantic_line(text, MAX_SEMANTIC_LINE)


def _record_timestamp(record: dict[str, Any]) -> float | None:
    message = record.get("message")
    message_ts = message.get("timestamp") if isinstance(message, dict) else None
    return records.parse_ts(record.get("timestamp") or message_ts or "")


def _dispatch_identity(command_line: str) -> tuple[str, str, str] | None:
    match = _DISPATCH_BUILD_RE.match(command_line)
    if match is None:
        return None
    try:
        tokens = shlex.split(match.group(1) or "")
    except ValueError:
        return None
    slug = ""
    stage = ""
    workflow_binding = ""
    index = 0
    while index < len(tokens):
        part = tokens[index]
        if part in {"|", "&&", ";"} or part.startswith((">", "1>", "2>")):
            break
        if part in _DISPATCH_VALUE_OPTIONS:
            value = tokens[index + 1] if index + 1 < len(tokens) else ""
            if part == "--stage" and spacedock.SD_STAGE_RE.fullmatch(value):
                stage = value
            elif part == "--workflow-dir":
                workflow_binding = value
            index += 2
            continue
        if part.startswith("-"):
            index += 1
            continue
        if not slug and spacedock.SD_STAGE_RE.fullmatch(part):
            slug = part
        index += 1
    return (workflow_binding, slug, stage) if slug else None


def _subagent_tasks(arguments: dict[str, Any]) -> list[str]:
    tasks: list[str] = []
    task = arguments.get("task")
    if isinstance(task, str) and task.strip():
        tasks.append(task)
    batch = arguments.get("tasks")
    if isinstance(batch, list):
        for item in batch:
            if not isinstance(item, dict):
                continue
            value = item.get("task")
            if isinstance(value, str) and value.strip():
                tasks.append(value)
    return tasks


def _dispatch_directories() -> tuple[str, ...]:
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    if runtime and os.path.isabs(runtime):
        return (os.path.join(runtime, "spacedock-dispatch"), _DISPATCH_DIRECTORY)
    return (_DISPATCH_DIRECTORY,)


def _dispatch_artifact(text: str) -> str:
    for directory in _dispatch_directories():
        pattern = re.escape(directory + "/spacedock-ensign-") + r"[A-Za-z0-9][A-Za-z0-9._-]*\.md"
        match = re.search(pattern, text)
        if match is not None:
            return match.group(0)
    return ""


def _dispatch_artifact_identity(artifact: str) -> tuple[str, str] | None:
    directory, name = os.path.split(artifact)
    if (
        directory not in _dispatch_directories()
        or not name.startswith("spacedock-ensign-")
        or not name.endswith(".md")
    ):
        return None
    name = name[len("spacedock-ensign-") : -len(".md")]
    slug, separator, stage = name.rpartition("-")
    if not separator or not spacedock.SD_STAGE_RE.fullmatch(slug):
        return None
    if not spacedock.SD_STAGE_RE.fullmatch(stage):
        return None
    return slug, stage


def _read_dispatch_artifact(artifact: str) -> str:
    if (
        _dispatch_artifact_identity(artifact) is None
        or not hasattr(os, "O_NOFOLLOW")
        or not hasattr(os, "getuid")
    ):
        return ""
    directory = os.path.dirname(artifact)
    try:
        resolved_directory = os.path.realpath(directory)
        if os.path.dirname(os.path.realpath(artifact)) != resolved_directory:
            return ""
        # The directory fd anchors the open even if an entry is replaced between
        # realpath and open. Inspect the opened file, never a pre-open stat.
        with contextlib.ExitStack() as stack:
            directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            stack.callback(os.close, directory_fd)
            if os.fstat(directory_fd).st_uid != os.getuid():
                return ""
            descriptor = os.open(
                os.path.basename(artifact),
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=directory_fd,
            )
            with os.fdopen(descriptor, "rb") as handle:
                info = os.fstat(handle.fileno())
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.getuid()
                    or info.st_mode & 0o022
                    or info.st_size > DISPATCH_MAX_BYTES
                ):
                    return ""
                raw = handle.read(DISPATCH_MAX_BYTES + 1)
                return raw.decode("utf-8", "replace") if len(raw) <= DISPATCH_MAX_BYTES else ""
    except (OSError, ValueError):
        return ""


def _dispatch_file_assignment(artifact: str) -> str:
    """Read the bounded human work title from one exact dispatch artifact."""
    if _dispatch_artifact_identity(artifact) is None:
        return ""
    prefix = "You are working on:"
    for raw in _read_dispatch_artifact(artifact).splitlines()[:40]:
        line = raw.strip()
        if line.startswith(prefix):
            return records.safe_text(line[len(prefix) :].strip(), MAX_SEMANTIC_LINE)
    return ""


def _subagent_specs(arguments: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    specs: list[tuple[str, str, str, str]] = []
    task = arguments.get("task")
    if isinstance(task, str) and task.strip():
        contributor = arguments.get("agent") or arguments.get("name") or ""
        binding = arguments.get("work_item") or arguments.get("task_id") or ""
        specs.append((task, str(contributor), str(binding), _dispatch_artifact(task)))
    batch = arguments.get("tasks")
    if isinstance(batch, list):
        for item in batch:
            if not isinstance(item, dict):
                continue
            value = item.get("task")
            if not isinstance(value, str) or not value.strip():
                continue
            contributor = item.get("agent") or item.get("name") or ""
            binding = item.get("work_item") or item.get("task_id") or ""
            specs.append((value, str(contributor), str(binding), _dispatch_artifact(value)))
    return specs


def _work_records(
    config: RuntimeConfig, transcript_path: str, *, max_bytes: int | None = None
) -> list[dict[str, Any]]:
    transcript: list[dict[str, Any]] = []
    bounded = list(
        runtime_io.reverse_lines(
            config,
            transcript_path,
            max_bytes=max_bytes or config.turn_scan_max_bytes,
        )
    )
    for raw_bytes in reversed(bounded):
        raw = raw_bytes.decode("utf-8", "replace")
        if not raw or not raw.lstrip().startswith("{"):
            continue
        try:
            record = json.loads(raw)
        except (ValueError, json.JSONDecodeError, RecursionError):
            continue
        if isinstance(record, dict):
            transcript.append(record)
    return transcript


def _result_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return records.safe_text(content, 16_000)
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return records.safe_text("\n".join(parts), 16_000)


def _paired_results(transcript: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for record in transcript:
        message = record.get("message")
        if not isinstance(message, dict) or message.get("role") != "toolResult":
            continue
        call_id = message.get("toolCallId")
        if isinstance(call_id, str):
            results[call_id] = {
                "succeeded": message.get("isError") is not True,
                "text": _result_text(message),
                "at": _record_timestamp(record),
            }
    return results


def _dispatch_count(command: str) -> int:
    return sum(_dispatch_identity(line) is not None for line in command.splitlines())


def _dispatch_events(
    command: str,
    *,
    at: float,
    result: dict[str, Any] | None,
    harness: str,
    sid: str,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for command_line in command.splitlines():
        identity = _dispatch_identity(command_line)
        if identity is None:
            continue
        workflow_binding, slug, stage = identity
        title = slug + (f" → {stage}" if stage else " dispatched")
        events.append(
            {
                "at": at,
                "kind": "prepared_dispatch",
                "phase": "Spacedock dispatch preparation",
                "title": title,
                "source": "Pi bash tool call"
                + (" and paired result" if result is not None else ""),
                "harness": harness,
                "sid": sid,
                "entity": slug,
                "workflow_binding": workflow_binding,
                "stage": stage,
                "dispatch_artifact": (f"{_DISPATCH_FILE_PREFIX}{slug}-{stage}.md" if stage else ""),
                "dispatch_artifact_prefix": f"{_DISPATCH_FILE_PREFIX}{slug}-",
                "succeeded": result.get("succeeded") if result is not None else None,
            }
        )
    return events


def _validation_event(
    result: dict[str, Any] | None,
    *,
    at: float,
    harness: str,
    sid: str,
) -> dict[str, Any] | None:
    if not result or result.get("succeeded") is not True:
        return None
    match = re.search(r"(?<!\d)(\d+)\s+passed(?:\s+in\s+[\d.]+s)?", str(result.get("text", "")))
    if match is None:
        return None
    count = int(match.group(1))
    return {
        "at": at,
        "kind": "outcome",
        "phase": "validation result",
        "title": f"{count} validation checks passed",
        "source": "Pi bash tool call and paired successful result",
        "harness": harness,
        "sid": sid,
        "checks_passed": count,
    }


def _subagent_category(combined: str) -> str:
    if re.match(r"^(?:review|inspect)\b", combined):
        return (
            "Implementation review completed"
            if "implementation" in combined
            else "Technical review completed"
        )
    if re.match(r"^implement\b", combined):
        return "Implementation pass completed"
    if re.match(r"^(?:design|write\b.*\bdesign)\b", combined):
        return "Design result produced"
    if re.match(r"^(?:perform\s+)?(?:independent\s+)?acceptance\b", combined):
        return "Independent acceptance completed"
    return ""


def _subagent_result_counts(text: str, tasks: list[str]) -> tuple[int, int]:
    completed = re.search(r"(?:children|tasks?):\s*(\d+)\s+completed", text, re.IGNORECASE)
    failed = re.search(r"(\d+)\s+failed", text, re.IGNORECASE)
    completed_count = int(completed.group(1)) if completed else len(tasks)
    failed_count = int(failed.group(1)) if failed else 0
    return completed_count, failed_count


def _subagent_has_substantive_review(result: Mapping[str, Any]) -> bool:
    for key in ("review_findings", "findings"):
        findings = result.get(key)
        if isinstance(findings, list) and any(
            isinstance(finding, str) and finding.strip() for finding in findings
        ):
            return True
    text = str(result.get("text", ""))
    match = re.search(r"(?im)^\s*review changed the course\s*:\s*$", text)
    if match is None:
        return False
    return any(
        re.match(r"^\s*[-*]\s+\S", line)
        for line in text[match.end() :].splitlines()
        if line.strip()
    )


def _subagent_result_title(tasks: list[str], result: dict[str, Any]) -> str:
    if _subagent_result_pending(result):
        return ""
    text = str(result.get("text", ""))
    lowered = text.casefold()
    if "acceptance cannot be requested explicitly" in lowered or (
        "cannot supply" in lowered and "reviewer result" in lowered
    ):
        return ""
    combined = " ".join(tasks).casefold()
    if result.get("succeeded") is not True:
        return "Independent acceptance was unavailable" if "acceptance" in combined else ""
    title = _subagent_category(combined)
    if not title:
        return ""
    if re.match(r"^(?:review|inspect)\b", combined):
        return title if _subagent_has_substantive_review(result) else "Review call returned"
    contributors, failures = _subagent_result_counts(text, tasks)
    if contributors > 1:
        title += f" by {contributors} contributors"
    if failures:
        title += f" with {failures} contributor failure"
        if failures != 1:
            title += "s"
    return title


def _subagent_result_pending(result: dict[str, Any]) -> bool:
    text = str(result.get("text", "")).casefold()
    return any(marker in text for marker in ("detached", "running in the background"))


def _subagent_events(
    arguments: dict[str, Any],
    *,
    call_key: str,
    at: float,
    result: dict[str, Any] | None,
    harness: str,
    sid: str,
) -> list[dict[str, Any]]:
    specs = _subagent_specs(arguments)
    tasks = [spec[0] for spec in specs]
    if not specs:
        return []
    rows: list[dict[str, Any]] = []
    for index, (task, contributor, binding, artifact) in enumerate(specs):
        assignment = _task_assignment(task, artifact)
        title = assignment or _semantic_line(task, MAX_SEMANTIC_LINE)
        if not title:
            continue
        rows.append(
            {
                "at": at,
                "kind": "task_started",
                "phase": "ordinary subagent task",
                "title": title,
                "source": "Pi subagent task label",
                "harness": harness,
                "sid": sid,
                "lineage": f"{call_key}:{index}",
                "work_item_binding": binding,
                "contributor_ref": contributor,
                "dispatch_artifact": artifact,
                "assignment": assignment,
                "worker_kind": "ensign" if artifact else "subagent",
                "stage": "started",
            }
        )
    if result is None or _subagent_result_pending(result):
        return rows
    result_title = _subagent_result_title(tasks, result)
    result_at = result.get("at")
    outcome_at = float(result_at) if isinstance(result_at, (int, float)) else at
    text = str(result.get("text", ""))
    completed = re.search(r"(?:children|tasks?):\s*(\d+)\s+completed", text, re.IGNORECASE)
    failed = re.search(r"(\d+)\s+failed", text, re.IGNORECASE)
    complete_count = int(completed.group(1)) if completed else len(tasks)
    failure_count = int(failed.group(1)) if failed else 0
    if len(tasks) == 1 or (complete_count == len(tasks) and failure_count == 0):
        for index, (task, contributor, binding, artifact) in enumerate(specs):
            item_title = result_title or _subagent_result_title([task], result)
            if not item_title and artifact and result.get("succeeded") is True:
                item_title = "Dispatch result returned"
            if not item_title:
                continue
            rows.append(
                {
                    "at": outcome_at,
                    "kind": "task_result",
                    "phase": "ordinary subagent result",
                    "title": item_title,
                    "source": "Pi subagent task label and paired result",
                    "harness": harness,
                    "sid": sid,
                    "lineage": f"{call_key}:{index}",
                    "work_item_binding": binding,
                    "contributor_ref": contributor,
                    "dispatch_artifact": artifact,
                    "assignment": _task_assignment(task, artifact),
                    "worker_kind": "ensign" if artifact else "subagent",
                    "stage": "completed",
                }
            )
    elif result_title:
        rows.append(
            {
                "at": outcome_at,
                "kind": "outcome",
                "phase": "ordinary subagent batch result",
                "title": result_title,
                "source": "Pi subagent batch call and paired result",
                "harness": harness,
                "sid": sid,
                "contributors": len(tasks),
            }
        )
    return rows


def _tool_call_events(
    block: dict[str, Any],
    *,
    at: float,
    results: dict[str, dict[str, Any]],
    harness: str,
    sid: str,
) -> list[dict[str, Any]]:
    call_id = block.get("id")
    call_key = call_id if isinstance(call_id, str) else ""
    arguments = block.get("arguments")
    args = arguments if isinstance(arguments, dict) else {}
    result = results.get(call_key)
    if block.get("name") == "bash":
        command = args.get("command")
        dispatches = _dispatch_events(
            command if isinstance(command, str) else "",
            at=at,
            result=result,
            harness=harness,
            sid=sid,
        )
        validation = _validation_event(result, at=at, harness=harness, sid=sid)
        return dispatches + ([validation] if validation is not None else [])
    if block.get("name") != "subagent":
        return []
    return _subagent_events(
        args,
        call_key=call_key,
        at=at,
        result=result,
        harness=harness,
        sid=sid,
    )


def _tool_support(
    block: dict[str, Any], results: dict[str, dict[str, Any]]
) -> dict[str, int] | None:
    name = block.get("name")
    if name not in {"bash", "subagent"}:
        return None
    support = {"tool_calls": 1, "dispatch_builds": 0, "subagent_calls": 0, "pending_subagents": 0}
    arguments = block.get("arguments")
    args = arguments if isinstance(arguments, dict) else {}
    if name == "bash" and isinstance(args.get("command"), str):
        support["dispatch_builds"] = _dispatch_count(args["command"])
    if name != "subagent" or not _subagent_tasks(args):
        return support
    support["subagent_calls"] = 1
    call_id = block.get("id")
    pair = results.get(call_id) if isinstance(call_id, str) else None
    pending = pair is None or _subagent_result_pending(pair)
    support["pending_subagents"] = int(pending)
    return support


def _assistant_branch_identity(
    record: dict[str, Any], records_by_id: dict[str, dict[str, Any]]
) -> dict[str, str]:
    record_id = record.get("id")
    parent_id = record.get("parentId")
    if not isinstance(record_id, str) or not record_id:
        return {}
    identity = {"record_id": record_id}
    if isinstance(parent_id, str) and parent_id:
        identity["parent_id"] = parent_id
    branch_id = record_id
    cursor = record
    seen: set[str] = {record_id}
    while True:
        ancestor_id = cursor.get("parentId")
        if not isinstance(ancestor_id, str) or not ancestor_id or ancestor_id in seen:
            return identity
        seen.add(ancestor_id)
        ancestor = records_by_id.get(ancestor_id)
        if ancestor is None:
            return identity
        message = ancestor.get("message")
        if isinstance(message, dict) and message.get("role") == "user":
            identity["turn_id"] = ancestor_id
            identity["branch_id"] = branch_id
            return identity
        branch_id = ancestor_id
        cursor = ancestor


def _assistant_tool_calls(
    transcript: list[dict[str, Any]],
) -> Iterator[tuple[float, dict[str, Any], dict[str, str]]]:
    records_by_id = {
        str(record["id"]): record
        for record in transcript
        if isinstance(record.get("id"), str) and record.get("id")
    }
    for record in transcript:
        message = record.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        content = message.get("content")
        at = _record_timestamp(record)
        if not isinstance(content, list) or at is None:
            continue
        identity = _assistant_branch_identity(record, records_by_id)
        for block in content:
            if isinstance(block, dict) and block.get("type") == "toolCall":
                yield at, block, identity


def _work_evidence(
    config: RuntimeConfig,
    transcript_path: str,
    harness: str,
    sid: str,
    *,
    max_bytes: int | None = None,
    since: float | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Demonstrated Pi results plus counts for suppressed supporting telemetry."""
    stats = {
        "tool_calls": 0,
        "dispatch_builds": 0,
        "subagent_calls": 0,
        "pending_subagents": 0,
        "suppressed_tool_calls": 0,
        "collapsed_contributors": 0,
    }
    if harness != "pi":
        return [], stats
    transcript = _work_records(config, transcript_path, max_bytes=max_bytes)
    results = _paired_results(transcript)

    events: list[dict[str, Any]] = []
    for at, block, identity in _assistant_tool_calls(transcript):
        support = _tool_support(block, results)
        if support is None:
            continue
        for key, value in support.items():
            stats[key] += value
        found = _tool_call_events(
            block,
            at=at,
            results=results,
            harness=harness,
            sid=sid,
        )
        for event in found:
            event.update(identity)
        found = _events_after(found, since)
        for event in found:
            artifact = str(event.get("dispatch_artifact") or "")
            assignment = _dispatch_file_assignment(artifact)
            if assignment:
                event["assignment"] = assignment
                event["source"] = (
                    str(event.get("source") or "") + " and bounded dispatch artifact title"
                )
        events.extend(found)
        if not found:
            stats["suppressed_tool_calls"] += 1
        for event in found:
            stats["collapsed_contributors"] += max(0, int(event.get("contributors", 1)) - 1)
    return events, stats


def _events_after(events: list[dict[str, Any]], since: float | None) -> list[dict[str, Any]]:
    floor = float(since) if isinstance(since, (int, float)) else float("-inf")
    return [event for event in events if float(event.get("at") or 0) >= floor]


def work_events(
    config: RuntimeConfig,
    transcript_path: str,
    harness: str,
    sid: str,
) -> list[dict[str, Any]]:
    """Demonstrated Pi results; supporting tool and lifecycle facts stay suppressed."""
    return _work_evidence(config, transcript_path, harness, sid)[0]


def instruction_events(
    config: RuntimeConfig,
    transcript_path: str,
    harness: str,
    sid: str,
    *,
    max_bytes: int | None = None,
    since: float | None = None,
) -> list[dict[str, Any]]:
    """Timestamped non-meta user-role messages from the bounded transcript tail."""
    events: list[dict[str, Any]] = []
    seen: set[tuple[float, str]] = set()
    source = (
        [
            line.decode("utf-8", "replace")
            for line in reversed(
                list(runtime_io.reverse_lines(config, transcript_path, max_bytes=max_bytes))
            )
        ]
        if max_bytes is not None
        else runtime_io.read_tail(config, transcript_path)
    )
    for raw in source:
        if not raw or not raw.lstrip().startswith("{"):
            continue
        try:
            record = json.loads(raw)
        except (ValueError, json.JSONDecodeError, RecursionError):
            continue
        event = _instruction_event(config, record, harness, sid)
        if event is None:
            continue
        if since is not None and float(event.get("at") or 0) < since:
            continue
        key = (event["at"], event["title"])
        if key in seen:
            continue
        seen.add(key)
        events.append(event)
    return events


def _codex_dispatch_artifact(task_name: str) -> tuple[str, str, str, str] | None:
    match = _CODEX_ENSIGN_TASK_RE.fullmatch(task_name)
    if match is None:
        return None
    stem = match.group(1).replace("_", "-")
    artifact = next(
        (
            candidate
            for directory in _dispatch_directories()
            if _read_dispatch_artifact(candidate := f"{directory}/spacedock-ensign-{stem}.md")
        ),
        "",
    )
    identity = _dispatch_artifact_identity(artifact)
    if identity is None or not os.path.isfile(artifact):
        return None
    entity, stage = identity
    assignment = _dispatch_file_assignment(artifact)
    workflow = ""
    for raw in _read_dispatch_artifact(artifact).splitlines()[:80]:
        if "--workflow-dir" not in raw:
            continue
        try:
            parts = shlex.split(raw.strip())
        except ValueError:
            continue
        if "--workflow-dir" in parts:
            index = parts.index("--workflow-dir") + 1
            if index < len(parts):
                workflow = parts[index]
                break
    if not assignment or not workflow:
        return None
    return artifact, workflow, entity, stage


def codex_dispatch_events(
    config: RuntimeConfig,
    transcript_path: str,
    harness: str,
    sid: str,
    *,
    since: float,
    max_bytes: int = SEMANTIC_BACKFILL_MAX_BYTES,
) -> list[dict[str, Any]]:
    """Exact Codex spawn calls bound to readable Spacedock dispatch artifacts."""
    if harness != "codex":
        return []
    events: list[dict[str, Any]] = []
    bounded = list(runtime_io.reverse_lines(config, transcript_path, max_bytes=max_bytes))
    for raw_bytes in reversed(bounded):
        try:
            record = records.as_dict(json.loads(raw_bytes.decode("utf-8", "replace")))
        except (ValueError, json.JSONDecodeError, RecursionError):
            continue
        at = _record_timestamp(record)
        payload = records.as_dict(record.get("payload"))
        if (
            at is None
            or at < since
            or record.get("type") != "response_item"
            or payload.get("type") != "function_call"
            or payload.get("name") != "spawn_agent"
        ):
            continue
        arguments = payload.get("arguments")
        try:
            args = records.as_dict(json.loads(arguments)) if isinstance(arguments, str) else {}
        except (ValueError, json.JSONDecodeError, RecursionError):
            continue
        task_name = args.get("task_name")
        metadata = _codex_dispatch_artifact(task_name) if isinstance(task_name, str) else None
        if metadata is None:
            continue
        artifact, workflow, entity, stage = metadata
        event = {
            "at": at,
            "kind": "prepared_dispatch",
            "phase": "Spacedock dispatch",
            "title": _dispatch_file_assignment(artifact),
            "source": "Codex spawn_agent call and structured Spacedock dispatch artifact",
            "harness": harness,
            "sid": sid,
            "entity": entity,
            "workflow_binding": workflow,
            "stage": stage,
            "dispatch_artifact": artifact,
        }
        call_id = payload.get("call_id") or payload.get("id")
        if isinstance(call_id, str) and call_id:
            event["record_id"] = call_id
        metadata_passthrough = records.as_dict(
            payload.get("internal_chat_message_metadata_passthrough")
        )
        turn_id = metadata_passthrough.get("turn_id")
        if isinstance(turn_id, str) and turn_id:
            event["turn_id"] = turn_id
            event["branch_id"] = turn_id
        events.append(event)
    return events


def _semantic_history_source_events(
    config: RuntimeConfig,
    transcript_path: str,
    harness: str,
    sid: str,
    *,
    since: float,
    max_bytes: int,
) -> list[dict[str, Any]]:
    events = instruction_events(
        config,
        transcript_path,
        harness,
        sid,
        max_bytes=max_bytes,
        since=since,
    )
    work_rows, _support = _work_evidence(
        config,
        transcript_path,
        harness,
        sid,
        max_bytes=max_bytes,
        since=since,
    )
    events.extend(work_rows)
    events.extend(
        codex_dispatch_events(
            config,
            transcript_path,
            harness,
            sid,
            since=since,
            max_bytes=max_bytes,
        )
    )
    return events


def _incremental_history_events(
    config: RuntimeConfig,
    state: RuntimeState,
    project: str,
    transcript_path: str,
    harness: str,
    sid: str,
    *,
    now: float,
) -> tuple[list[dict[str, Any]], dict[str, int] | None]:
    signature = _transcript_signature(transcript_path)
    if signature is None:
        return [], None
    source_identity = f"{harness}:{sid}"
    scan_bytes = semantic_history.backfill_scan_bytes(
        config,
        state,
        project,
        source_identity,
        signature,
        full_max_bytes=SEMANTIC_BACKFILL_MAX_BYTES,
    )
    if not scan_bytes:
        return [], signature
    return (
        _semantic_history_source_events(
            config,
            transcript_path,
            harness,
            sid,
            since=now - SEMANTIC_HISTORY_HORIZON_SEC,
            max_bytes=scan_bytes,
        ),
        signature,
    )


def _dedupe_project_events(
    events: list[dict[str, Any]], *, limit: int | None = None
) -> list[dict[str, Any]]:
    deduped: dict[tuple[object, ...], dict[str, Any]] = {}
    for event in events:
        key = (
            event.get("kind"),
            event.get("at"),
            event.get("title"),
            event.get("workflow_binding") or event.get("workflow"),
            event.get("entity"),
            event.get("lineage"),
            event.get("work_item_binding"),
            event.get("record_id"),
        )
        deduped.setdefault(key, event)
    ordered = sorted(deduped.values(), key=lambda event: float(event["at"]), reverse=True)
    return ordered[:limit] if limit is not None else ordered


def _merge_support_counts(target: dict[str, int], incoming: Mapping[str, int]) -> None:
    for key in target:
        target[key] += incoming[key]


def _timeline_counts(timeline: list[dict[str, Any]]) -> tuple[int, int, int]:
    return (
        sum(1 for event in timeline if event["kind"] == "gate"),
        sum(1 for event in timeline if event["kind"] == "steer"),
        sum(
            1
            for event in timeline
            if event["kind"] in {"prepared_dispatch", "task_started", "task_result", "outcome"}
        ),
    )


def _context_sessions(
    sessions: Sequence[Mapping[str, Any]], project: str, focus: tuple[str, str] | None
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]], str, int]:
    selected = [
        session
        for session in sessions
        if (
            str(session.get("project_key") or session.get("project") or "") == project
            or str(session.get("project") or "") == project
        )
        and session.get("active") is True
    ]
    selected.sort(key=lambda item: float(item.get("last_activity") or 0), reverse=True)
    if focus is None:
        return (
            selected[:MAX_PROJECT_OBSERVERS],
            selected[MAX_PROJECT_OBSERVERS:],
            "selected project",
            0,
        )
    analysis = [
        session
        for session in selected
        if (str(session.get("harness") or ""), str(session.get("sid") or "")) == focus
    ]
    return analysis, [], "focused session", len(selected) - len(analysis)


def _analysis_context_sessions(
    sessions: Sequence[Mapping[str, Any]], project: str, focus: tuple[str, str] | None
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]], str, int]:
    analysis, omitted, _, _ = _context_sessions(sessions, project, None)
    focused, _, scope, surrounding_active = _context_sessions(sessions, project, focus)
    if focus is None:
        return analysis, omitted, scope, surrounding_active
    known = {
        (str(session.get("harness") or ""), str(session.get("sid") or "")) for session in analysis
    }
    return (
        [
            *analysis,
            *(
                session
                for session in focused
                if (str(session.get("harness") or ""), str(session.get("sid") or "")) not in known
            ),
        ],
        [],
        scope,
        surrounding_active,
    )


def _attention_context_sessions(
    sessions: Sequence[Mapping[str, Any]], project: str
) -> tuple[list[Mapping[str, Any]], dict[str, Any]]:
    selected = [
        session
        for session in sessions
        if (
            str(session.get("project_key") or session.get("project") or "") == project
            or str(session.get("project") or "") == project
        )
        and session.get("active") is True
    ]
    selected.sort(key=lambda item: float(item.get("last_activity") or 0), reverse=True)
    scanned = selected[:MAX_PROJECT_ATTENTION_SESSIONS]
    omitted = max(0, len(selected) - len(scanned))
    return scanned, {
        "state": "incomplete" if omitted else "complete",
        "scanned": len(scanned),
        "total": len(selected),
        "omitted": omitted,
        "source": "bounded active-session final-output scan",
    }


def _gate_event(
    config: RuntimeConfig,
    current: dict[str, str],
    slug: str,
    entity_id: str,
    entity_title: str,
    workflow: str,
    workflow_binding: str,
    _harness: str,
    _sid: str,
) -> dict[str, Any] | None:
    at = records.parse_ts(current.get("at", ""))
    decision = current.get("decision", "")
    if at is None or not decision:
        return None
    stage = current.get("stage", "unknown stage")
    application_state = current.get("application_state", "")
    phase = "gate decision" + (f" · application {application_state}" if application_state else "")
    reason = records.safe_text(current.get("reason", ""), config.observer_block_cap_chars)
    detail = workflow
    if reason:
        detail += f" · {reason}"
    workflow_entity = records.safe_text(entity_id, 128)[:10] if entity_id else slug
    return {
        "at": at,
        "kind": "gate",
        "phase": phase,
        "title": f"{slug} · {stage} · {decision}",
        "detail": detail,
        "source": "Spacedock entity gate frontmatter",
        "scope": "project",
        "workflow": workflow,
        "workflow_binding": workflow_binding,
        "entity": workflow_entity,
        "entity_slug": slug,
        "entity_title": records.safe_text(entity_title, config.observer_block_cap_chars),
        "stage": stage,
        "decision": decision,
        "by": current.get("by", ""),
        "application_state": application_state,
        "target_stage": current.get("target_stage", ""),
    }


def _gate_field(body: str, block: str, current: dict[str, str], gate_stage: str) -> str:
    if body.startswith("stage:") and block == "gate":
        gate_stage = body[len("stage:") :].strip().strip("\"'")
        current["stage"] = gate_stage
    elif block == "resolution":
        for key in ("at", "decision", "by", "reason"):
            if body.startswith(key + ":"):
                current[key] = body[len(key) + 1 :].strip().strip("\"'")
                break
    elif block == "application" and body.startswith("state:"):
        current["application_state"] = body[len("state:") :].strip().strip("\"'")
    elif block == "application" and body.startswith("target-stage:"):
        current["target_stage"] = body[len("target-stage:") :].strip().strip("\"'")
    return gate_stage


def gate_events(
    config: RuntimeConfig,
    lines: list[str],
    slug: str,
    workflow: str,
    harness: str,
    sid: str,
    *,
    workflow_binding: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """All timestamped gate decisions and the untimestamped briefing count."""
    events: list[dict[str, Any]] = []
    current: dict[str, str] = {}
    block = ""
    gate_stage = ""
    briefings = 0
    entity_id = next(
        (raw[len("id:") :].strip().strip("\"'") for raw in lines if raw.startswith("id:")),
        "",
    )
    entity_title = next(
        (raw[len("title:") :].strip().strip("\"'") for raw in lines if raw.startswith("title:")),
        "",
    )

    def flush() -> None:
        event = _gate_event(
            config,
            current,
            slug,
            entity_id,
            entity_title,
            workflow,
            workflow_binding or workflow,
            harness,
            sid,
        )
        if event is not None:
            events.append(event)

    for raw in lines:
        body = raw.strip()
        if body.startswith("- id: gate:"):
            flush()
            current = {}
            gate_stage = ""
            block = "gate"
        elif body.startswith("- id: gate-attempt:"):
            flush()
            current = {"stage": gate_stage} if gate_stage else {}
            block = "attempt"
        elif body == "briefing:":
            briefings += 1
            block = "briefing"
        elif body == "resolution:":
            block = "resolution"
        elif body == "application:":
            block = "application"
        else:
            gate_stage = _gate_field(body, block, current, gate_stage)
    flush()
    return events, briefings


def _gate_context(
    config: RuntimeConfig,
    state: RuntimeState,
    transcript_path: str,
    harness: str,
    sid: str,
) -> tuple[list[dict[str, Any]], int]:
    events: list[dict[str, Any]] = []
    briefings = 0
    boot = spacedock.transcript_boot(config, state, transcript_path)
    for workflow_dir in spacedock.workflow_dirs(config, boot):
        workflow = spacedock.read_workflow(config, state, workflow_dir)
        entity_dir = spacedock.boot_entity_dir(boot, workflow_dir)
        if workflow is None or not entity_dir:
            continue
        for slug, path, info in spacedock.entity_files(config, entity_dir):
            try:
                lines = spacedock.read_frontmatter(
                    config, path, config.spacedock_entity_bytes, info
                )
            except spacedock.SdMismatchError:
                continue
            found, prepared = gate_events(
                config,
                lines,
                slug,
                str(workflow["name"]),
                harness,
                sid,
                workflow_binding=str(workflow_dir),
            )
            events.extend(found)
            briefings += prepared
    return events, briefings


def _project_peer_gate_context(
    config: RuntimeConfig,
    state: RuntimeState,
    sessions: Sequence[Mapping[str, Any]],
    project: str,
    focus: tuple[str, str] | None,
) -> tuple[list[dict[str, Any]], int]:
    """Read only project state from peers; their transcript facts stay excluded."""
    if focus is None:
        return [], 0
    events: list[dict[str, Any]] = []
    briefings = 0
    for session in sessions:
        harness = str(session.get("harness") or "")
        sid = str(session.get("sid") or "")
        session_project = str(session.get("project_key") or session.get("project") or "")
        if (
            session.get("active") is not True
            or session_project != project
            or (harness, sid) == focus
        ):
            continue
        transcript_path = observer.resolve_transcript(config, state, harness, sid)
        if transcript_path is None:
            continue
        found, prepared = _gate_context(config, state, transcript_path, harness, sid)
        events.extend(found)
        briefings += prepared
    return events, briefings


def _prepared_dispatches(events: list[dict[str, Any]]) -> list[tuple[str, str, str, str, str]]:
    prepared: list[tuple[str, str, str, str, str]] = []
    for event in events:
        if event.get("kind") != "prepared_dispatch":
            continue
        artifact = str(event.get("dispatch_artifact") or "")
        prefix = str(event.get("dispatch_artifact_prefix") or "")
        workflow = str(event.get("workflow_binding") or "")
        entity = str(event.get("entity") or "")
        stage = str(event.get("stage") or "")
        if workflow and entity and (artifact or prefix):
            prepared.append((artifact, prefix, workflow, entity, stage))
    return prepared


def _artifact_bindings(
    artifact: str, prepared: list[tuple[str, str, str, str, str]]
) -> set[tuple[str, str, str]]:
    bindings: set[tuple[str, str, str]] = set()
    for exact, prefix, workflow, entity, prepared_stage in prepared:
        if exact and artifact == exact:
            bindings.add((workflow, entity, prepared_stage))
            continue
        if not artifact.startswith(prefix) or not artifact.endswith(".md"):
            continue
        stage = artifact[len(prefix) : -len(".md")]
        if stage and spacedock.SD_STAGE_RE.fullmatch(stage):
            bindings.add((workflow, entity, stage))
    return bindings


def _exact_gate_aliases(
    events: list[dict[str, Any]],
) -> tuple[dict[tuple[str, str], tuple[str, str]], dict[str, set[tuple[str, str]]]]:
    by_workflow: dict[tuple[str, str], tuple[str, str]] = {}
    by_entity: dict[str, set[tuple[str, str]]] = {}
    for event in events:
        if event.get("kind") != "gate":
            continue
        workflow = str(event.get("workflow_binding") or "")
        entity = str(event.get("entity") or "")
        if not workflow or not entity:
            continue
        canonical = (workflow, entity)
        for alias in {entity, str(event.get("entity_slug") or "")} - {""}:
            by_workflow[(workflow, alias)] = canonical
            by_entity.setdefault(alias, set()).add(canonical)
    return by_workflow, by_entity


def _bind_exact_gate_alias(
    event: dict[str, Any],
    by_workflow: dict[tuple[str, str], tuple[str, str]],
    by_entity: dict[str, set[tuple[str, str]]],
) -> None:
    if event.get("kind") == "gate":
        return
    workflow = str(event.get("workflow_binding") or "")
    entity = str(event.get("entity") or "")
    canonical = by_workflow.get((workflow, entity)) if workflow and entity else None
    if canonical is None and not workflow and entity:
        candidates = by_entity.get(entity, set())
        canonical = next(iter(candidates)) if len(candidates) == 1 else None
    if canonical is None:
        return
    event["workflow_binding"], event["entity"] = canonical
    event["source"] = str(event.get("source") or "") + " and exact gate entity alias"


def _bind_dispatch_artifacts(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bind a consumed dispatch file only to its exact prepared artifact."""
    prepared = _prepared_dispatches(events)
    gate_aliases, gate_entities = _exact_gate_aliases(events)

    normalized: list[dict[str, Any]] = []
    for source_event in events:
        event = dict(source_event)
        artifact = str(event.get("dispatch_artifact") or "")
        identity = _dispatch_artifact_identity(artifact)
        if event.get("kind") in {"task_started", "task_result"} and identity is not None:
            entity, stage = identity
            event.update(
                {
                    "entity": entity,
                    "stage": stage,
                    "title": (
                        f"{entity} · {stage} result returned"
                        if event.get("kind") == "task_result"
                        else f"{entity} · {stage} dispatched"
                    ),
                    "source": str(event.get("source") or "")
                    + " and structured dispatch artifact path",
                }
            )
        bindings = _artifact_bindings(artifact, prepared)
        if event.get("kind") in {"task_started", "task_result"} and len(bindings) == 1:
            workflow, entity, stage = next(iter(bindings))
            event.update(
                {
                    "workflow_binding": workflow,
                    "entity": entity,
                    "stage": stage,
                    "title": (
                        f"{entity} · {stage} result returned"
                        if event.get("kind") == "task_result"
                        else f"{entity} · {stage} dispatched"
                    ),
                    "source": str(event.get("source") or "") + " and exact prepared-dispatch match",
                }
            )
        _bind_exact_gate_alias(event, gate_aliases, gate_entities)
        normalized.append(event)
    return normalized


def _focused_persisted_facts(
    history: Mapping[str, Any], focus: tuple[str, str]
) -> list[dict[str, Any]]:
    wanted = {"harness": focus[0], "sid": focus[1]}
    facts: list[dict[str, Any]] = []
    for row in history.get("events", []):
        if not isinstance(row, Mapping):
            continue
        fact = row.get("fact")
        if not isinstance(fact, dict):
            continue
        if fact.get("source_session") == wanted or fact.get("parent_session") == wanted:
            facts.append(fact)
    return facts


def _allow_exact_gate_evidence(
    allowed: set[str],
    evidence: Mapping[str, Any],
    gate_aliases: dict[tuple[str, str], tuple[str, str]],
    gate_entities: dict[str, set[tuple[str, str]]],
) -> None:
    work_item_id = str(evidence.get("work_item_id") or "")
    if work_item_id:
        allowed.add(work_item_id)
    workflow = str(evidence.get("workflow_binding") or "")
    entity = str(evidence.get("workflow_entity") or evidence.get("entity") or "")
    if not entity:
        return
    alias_event = {"kind": "task_started", "workflow_binding": workflow, "entity": entity}
    _bind_exact_gate_alias(alias_event, gate_aliases, gate_entities)
    canonical_work_item, _kind, _label, _binding = _semantic_work_identity(
        alias_event, "task_started"
    )
    if canonical_work_item:
        allowed.add(canonical_work_item)


def _focused_gate_events(
    evidence_events: list[dict[str, Any]],
    gate_events: list[dict[str, Any]],
    child_assignments: list[dict[str, Any]],
    persisted_history: Mapping[str, Any],
    focus: tuple[str, str],
) -> tuple[list[dict[str, Any]], set[str]]:
    normalized = _bind_dispatch_artifacts([*evidence_events, *gate_events])
    gate_aliases, gate_entities = _exact_gate_aliases(normalized)
    allowed = {
        work_item_id
        for event in normalized
        if event.get("kind") != "gate"
        for work_item_id, _kind, _label, _binding in [
            _semantic_work_identity(event, str(event.get("kind") or ""))
        ]
        if work_item_id
    }
    for evidence in child_assignments:
        _allow_exact_gate_evidence(allowed, evidence, gate_aliases, gate_entities)
    for evidence in _focused_persisted_facts(persisted_history, focus):
        _allow_exact_gate_evidence(allowed, evidence, gate_aliases, gate_entities)
    kept: list[dict[str, Any]] = []
    for event in normalized:
        if event.get("kind") != "gate":
            continue
        work_item_id, _kind, _label, _binding = _semantic_work_identity(event, "gate")
        if work_item_id in allowed:
            kept.append(event)
    return kept, allowed


def _scope_gate_events(
    events: list[dict[str, Any]],
    history_events: list[dict[str, Any]],
    gate_events: list[dict[str, Any]],
    focus: tuple[str, str] | None,
    child_assignments: list[dict[str, Any]],
    persisted_history: Mapping[str, Any],
) -> set[str]:
    allowed: set[str] = set()
    if focus is not None:
        gate_events, allowed = _focused_gate_events(
            [*events, *history_events],
            gate_events,
            child_assignments,
            persisted_history,
            focus,
        )
    events.extend(gate_events)
    history_events.extend(gate_events)
    return allowed


def _semantic_work_identity(
    source_event: dict[str, Any], raw_kind: str
) -> tuple[str, str, str, str]:
    binding = str(source_event.get("work_item_binding") or "")
    if raw_kind in {"task_started", "task_result"} and source_event.get("entity"):
        workflow_binding = str(source_event.get("workflow_binding") or "")
        artifact = str(source_event.get("dispatch_artifact") or "")
        work_item_id = (
            semantic_history.workflow_work_item_id(workflow_binding, str(source_event["entity"]))
            if workflow_binding
            else _semantic_id("workflow-item-artifact", artifact)
        )
        label = str(source_event["entity"])
        if source_event.get("stage"):
            label += f" · {source_event['stage']}"
        return work_item_id, "workflow_item", label, binding
    if raw_kind in {"prepared_dispatch", "gate"} and source_event.get("entity"):
        workflow_binding = str(source_event.get("workflow_binding") or "unbound-workflow")
        return (
            semantic_history.workflow_work_item_id(workflow_binding, str(source_event["entity"])),
            "workflow_item",
            str(
                source_event.get("entity_title")
                or source_event.get("entity_slug")
                or source_event["entity"]
            ),
            binding,
        )
    if raw_kind not in {"task_started", "task_result"} or not source_event.get("lineage"):
        return "", "unknown", "", binding
    work_item_id = (
        _semantic_id("work-item", "bound", binding)
        if binding
        else _semantic_id("work-item", "one-off", source_event["lineage"])
    )
    return (
        work_item_id,
        "unknown" if binding else "one_off",
        str(source_event.get("title") or "one-off work"),
        binding,
    )


def _semantic_actor_claim(source_event: dict[str, Any], raw_kind: str) -> str:
    if raw_kind == "steer":
        return "timestamped non-meta user-role record"
    if raw_kind in {"prepared_dispatch", "task_started", "task_result", "outcome"}:
        return "session assistant/tool exchange"
    if raw_kind == "gate":
        return str(source_event.get("by") or "decision author unavailable")
    return ""


def _semantic_fact_from_event(
    source_event: dict[str, Any], raw_kind: str, fact_type: str, work_item_id: str
) -> dict[str, Any]:
    fact_id = _semantic_id(
        "fact",
        raw_kind,
        source_event.get("harness"),
        source_event.get("sid"),
        source_event.get("at"),
        source_event.get("workflow_binding"),
        source_event.get("entity"),
        source_event.get("lineage"),
        source_event.get("title"),
    )
    fact: dict[str, Any] = {
        "fact_id": fact_id,
        "at": source_event.get("at"),
        "type": fact_type,
        "source_kind": raw_kind,
        "summary": source_event.get("title"),
        "scope": "project" if raw_kind == "gate" else "session",
        "actor_claim": _semantic_actor_claim(source_event, raw_kind),
        "work_item_id": work_item_id or None,
        "evidence": {"source": source_event.get("source"), "confidence": "exact"},
    }
    for key in (
        "stage",
        "decision",
        "by",
        "application_state",
        "target_stage",
        "assignment",
        "worker_kind",
    ):
        if source_event.get(key) not in (None, ""):
            fact[key] = source_event[key]
    if raw_kind == "steer":
        fact["intent_promoted"] = source_event.get("intent_promotable") is True
    if raw_kind == "gate" and source_event.get("entity"):
        fact["workflow_entity"] = source_event["entity"]
    harness = records.safe_text(source_event.get("harness"), 32)
    sid = records.safe_text(source_event.get("sid"), 128)
    if raw_kind != "gate" and harness and sid:
        fact["source_session"] = {"harness": harness, "sid": sid}
    branch = {
        key: source_event[key]
        for key in ("record_id", "parent_id", "turn_id", "branch_id")
        if source_event.get(key) not in (None, "")
    }
    if branch:
        fact["branch"] = {
            "harness": source_event.get("harness"),
            "sid": source_event.get("sid"),
            **branch,
        }
    lineage = str(source_event.get("lineage") or "")
    if lineage:
        call_key = lineage.rsplit(":", 1)[0]
        fact["batch_id"] = _semantic_id(
            "batch", source_event.get("harness"), source_event.get("sid"), call_key
        )
    return fact


def _semantic_intent(fact: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    projection_id = _semantic_id("intent", fact["fact_id"])
    projection = {
        "projection_id": projection_id,
        "at": fact["at"],
        "kind": "operator_intent",
        "summary": fact["summary"],
        "derived_from": fact["fact_id"],
        "confidence": "derived-deterministic",
    }
    relation = {
        "from": projection_id,
        "to": fact["fact_id"],
        "type": "derived_from",
        "confidence": "exact",
        "provenance": "bounded semantic-line extraction",
    }
    return projection, relation


def _append_semantic_intent(
    fact: dict[str, Any],
    intent_summaries: set[str],
    intent_projections: list[dict[str, Any]],
    relations: list[dict[str, Any]],
) -> None:
    projection, relation = _semantic_intent(fact)
    summary_key = str(projection["summary"]).casefold().strip()
    if summary_key in intent_summaries:
        return
    intent_summaries.add(summary_key)
    intent_projections.append(projection)
    relations.append(relation)


def _semantic_source_binding(
    source_event: dict[str, Any], work_item_kind: str, binding: str
) -> dict[str, str]:
    if binding:
        return {"source": "explicit task binding", "value": binding}
    if source_event.get("dispatch_artifact"):
        return {
            "source": "structured Spacedock dispatch artifact",
            "value": str(source_event["dispatch_artifact"]),
        }
    if work_item_kind != "workflow_item":
        return {"source": "Pi subagent call", "value": str(source_event.get("lineage") or "")}
    value = (
        str(source_event.get("workflow_binding") or "unbound-workflow")
        + ":"
        + str(source_event.get("entity") or "")
    )
    return {"source": "Spacedock entity slug", "value": value}


def _semantic_work_label(
    work_item: dict[str, Any],
    source_event: dict[str, Any],
    raw_kind: str,
    work_item_label: str,
    has_entity_title: bool,
) -> bool:
    if raw_kind == "gate" and source_event.get("entity_title"):
        work_item["label"] = work_item_label
        return True
    if (
        raw_kind in {"task_started", "task_result"}
        and source_event.get("dispatch_artifact")
        and not has_entity_title
    ):
        work_item["label"] = work_item_label
    return has_entity_title


def _semantic_work_item(
    work_items: dict[str, dict[str, Any]],
    titled_work_items: set[str],
    work_item_id: str,
    work_item_kind: str,
    work_item_label: str,
    source_event: dict[str, Any],
    raw_kind: str,
) -> dict[str, Any]:
    work_item = work_items.setdefault(
        work_item_id,
        {
            "work_item_id": work_item_id,
            "label": work_item_label,
            "kind": work_item_kind,
            "source_bindings": [],
            "contributor_refs": [],
        },
    )
    if _semantic_work_label(
        work_item,
        source_event,
        raw_kind,
        work_item_label,
        work_item_id in titled_work_items,
    ):
        titled_work_items.add(work_item_id)
    return work_item


def _semantic_work_relation(
    source_event: dict[str, Any], raw_kind: str, fact_id: str, work_item_id: str
) -> dict[str, Any] | None:
    relation_type = {
        "prepared_dispatch": "binds_to",
        "task_started": "binds_to",
        "task_result": "progresses",
        "gate": "decides",
    }.get(raw_kind)
    if relation_type is None:
        return None
    return {
        "from": fact_id,
        "to": work_item_id,
        "type": relation_type,
        "confidence": "structural" if raw_kind in {"prepared_dispatch", "gate"} else "exact",
        "provenance": source_event.get("source"),
    }


def _semantic_topology_relations(
    source_event: dict[str, Any], raw_kind: str, fact_id: str, work_item_id: str
) -> list[dict[str, Any]]:
    """Return graph topology only when the source records the endpoint relation."""
    harness = str(source_event.get("harness") or "")
    sid = str(source_event.get("sid") or "")
    if not harness or not sid:
        return []
    fo_id = f"fo:{harness}:{sid}"
    task_id = f"task:{work_item_id}"
    if raw_kind == "prepared_dispatch":
        relation_type, source_id, target_id = "dispatches_to", fo_id, task_id
    elif raw_kind == "task_result":
        relation_type, source_id, target_id = "returns_to", task_id, fo_id
    else:
        return []
    return [
        {
            "from": source_id,
            "to": target_id,
            "type": relation_type,
            "confidence": "structural" if raw_kind == "prepared_dispatch" else "exact",
            "provenance": source_event.get("source"),
            "evidence_ref": fact_id,
        }
    ]


def _semantic_observer_facts(observers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for observer_row in observers:
        observed_at = observer_row.get("observed_at")
        goal = observer_row.get("goal")
        if not isinstance(observed_at, (int, float)) or not isinstance(goal, str):
            continue
        fact: dict[str, Any] = {
            "fact_id": _semantic_id(
                "observer",
                observer_row.get("harness"),
                observer_row.get("sid"),
                observed_at,
                goal,
            ),
            "at": observed_at,
            "type": "observer_snapshot",
            "summary": goal,
            "scope": "session",
            "actor_claim": "model-derived observer snapshot",
            "work_item_id": None,
            "evidence": {
                "source": observer_row.get("source"),
                "confidence": "derived",
                "snapshot_status": observer_row.get("snapshot_status"),
            },
        }
        harness = records.safe_text(observer_row.get("harness"), 32)
        sid = records.safe_text(observer_row.get("sid"), 128)
        if harness and sid:
            fact["source_session"] = {"harness": harness, "sid": sid}
        facts.append(fact)
    return facts


def _semantic_trail_heads(
    fact_by_work_item: dict[str, list[dict[str, Any]]], facts: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    heads: list[dict[str, Any]] = []
    for work_item_id, item_facts in fact_by_work_item.items():
        newest = max(item_facts, key=lambda fact: float(fact.get("at") or 0))
        state_facts = [
            fact
            for fact in item_facts
            if fact.get("type") in {"stage_transition", "prepared_dispatch"} and fact.get("stage")
        ]
        state_fact = (
            max(state_facts, key=lambda fact: float(fact.get("at") or 0)) if state_facts else None
        )
        dispatches = [
            fact
            for fact in item_facts
            if fact.get("type") == "prepared_dispatch"
            and fact.get("source_kind") == "prepared_dispatch"
        ]
        status = {
            "prepared_dispatch": "prepared",
            "work_birth": "requested",
            "work_result": "outcome",
            "result": "returned",
            "gate_decision": "decision",
        }.get(str(newest.get("type")), "latest")
        head = {
            "work_item_id": work_item_id,
            "status": status,
            "latest_meaningful_event": newest["fact_id"],
            "dispatch_count": len(dispatches),
        }
        if state_fact is not None:
            head["stage"] = state_fact["stage"]
            head["state_fact"] = state_fact["fact_id"]
            if state_fact.get("type") == "stage_transition" and float(
                state_fact.get("at") or 0
            ) >= float(newest.get("at") or 0):
                head["status"] = "current stage"
        heads.append(head)
    at_by_id = {fact["fact_id"]: float(fact.get("at") or 0) for fact in facts}
    return sorted(
        heads,
        key=lambda head: at_by_id.get(str(head["latest_meaningful_event"]), 0),
        reverse=True,
    )


def _semantic_assignments(
    fact_by_work_item: dict[str, list[dict[str, Any]]],
    work_items: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    assignments: list[dict[str, Any]] = []
    for work_item_id, item_facts in fact_by_work_item.items():
        births = [fact for fact in item_facts if fact.get("type") == "work_birth"]
        if not births:
            continue
        birth = max(births, key=lambda fact: float(fact.get("at") or 0))
        latest = max(item_facts, key=lambda fact: float(fact.get("at") or 0))
        completed = latest.get("type") == "work_result"
        work_item = work_items[work_item_id]
        assignments.append(
            {
                "projection_id": _semantic_id("assignment", work_item_id, birth["fact_id"]),
                "work_item_id": work_item_id,
                "assignment_fact": birth["fact_id"],
                "state_fact": latest["fact_id"],
                "at": latest.get("at"),
                "state": "completed" if completed else "awaiting_result",
                "worker_kind": birth.get("worker_kind") or "subagent",
                "assignment": birth.get("assignment") or work_item.get("label"),
                "contributor_refs": list(work_item.get("contributor_refs") or []),
            }
        )
    return sorted(assignments, key=lambda row: float(row.get("at") or 0), reverse=True)


def _activity_nodes(representatives: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clusters: list[list[dict[str, Any]]] = []
    for representative in sorted(representatives, key=lambda row: float(row.get("at") or 0)):
        if not clusters:
            clusters.append([representative])
            continue
        cluster = clusters[-1]
        first = cluster[0]
        same_batch = bool(representative.get("batch_id")) and representative.get(
            "batch_id"
        ) == first.get("batch_id")
        near = (
            float(representative.get("at") or 0) - float(first.get("at") or 0)
            <= SEMANTIC_BURST_EPSILON_SEC
        )
        if not (same_batch or near):
            cluster = []
            clusters.append(cluster)
        cluster.append(representative)

    nodes: list[dict[str, Any]] = []
    for cluster in clusters:
        cluster.sort(key=lambda row: float(row.get("at") or 0), reverse=True)
        work_item_ids = [
            work_item_id for member in cluster for work_item_id in member["work_item_ids"]
        ]
        if len(cluster) == 1:
            node = dict(cluster[0])
            node["kind"] = "work"
        else:
            node = {
                "kind": "burst",
                "at": cluster[0].get("at"),
                "count": len(cluster),
                "work_item_ids": work_item_ids,
                "latest_event": cluster[0].get("latest_event"),
                "retry_count": sum(int(member.get("retry_count") or 0) for member in cluster),
            }
        nodes.append(node)
    return sorted(nodes, key=lambda row: float(row.get("at") or 0), reverse=True)[
        :MAX_PRIMARY_ACTIVITY_NODES
    ]


def _semantic_activity_projection(
    work_items: dict[str, dict[str, Any]],
    trail_heads: list[dict[str, Any]],
    facts: list[dict[str, Any]],
    *,
    now: float | None = None,
) -> dict[str, Any]:
    """Bound the primary graph without turning old requests into current state."""
    if not facts:
        return {"nodes": [], "historical_unresolved": 0}
    fact_by_id = {str(fact["fact_id"]): fact for fact in facts}
    reference_at = (
        float(now)
        if isinstance(now, (int, float))
        else max((float(fact.get("at") or 0) for fact in facts), default=0)
    )
    current_after = reference_at - SEMANTIC_CURRENT_HORIZON_SEC

    def label_key(work_item_id: str) -> str:
        label = str(work_items.get(work_item_id, {}).get("label") or "")
        return re.sub(r"[^a-z0-9]+", " ", label.casefold()).strip()

    current: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for head in trail_heads:
        latest = fact_by_id.get(str(head.get("latest_meaningful_event")))
        if latest is None or float(latest.get("at") or 0) < current_after:
            continue
        if head.get("status") not in {"prepared", "requested", "outcome", "decision"}:
            continue
        current.append((head, latest))

    # An exact repeated assignment is one work lane with retry history, not a
    # new primary node each time the orchestrator redispatches it.
    grouped: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for head, latest in current:
        key = label_key(str(head["work_item_id"])) or str(head["work_item_id"])
        grouped.setdefault(key, []).append((head, latest))
    representatives: list[dict[str, Any]] = []
    for members in grouped.values():
        members.sort(key=lambda pair: float(pair[1].get("at") or 0), reverse=True)
        head, latest = members[0]
        representatives.append(
            {
                "at": latest.get("at"),
                "batch_id": latest.get("batch_id"),
                "status": head.get("status"),
                "work_item_ids": [str(pair[0]["work_item_id"]) for pair in members],
                "latest_event": latest["fact_id"],
                "retry_count": len(members) - 1,
            }
        )
    nodes = _activity_nodes(representatives)

    represented_keys = {
        label_key(work_item_id) for node in nodes for work_item_id in node.get("work_item_ids", [])
    }
    historical_keys = {
        label_key(str(head["work_item_id"]))
        for head in trail_heads
        if head.get("status") == "requested"
        and label_key(str(head["work_item_id"])) not in represented_keys
    }
    represented_ids = {
        work_item_id for node in nodes for work_item_id in node.get("work_item_ids", [])
    }
    historical_dispatches = sum(
        head.get("status") == "requested" and str(head["work_item_id"]) not in represented_ids
        for head in trail_heads
    )
    return {
        "nodes": nodes,
        "historical_unresolved": len(historical_keys),
        "historical_dispatches": historical_dispatches,
        "current_after": current_after,
    }


def _recent_steering_nodes(
    intents: list[dict[str, Any]], paired_intent_ids: set[str] | None = None
) -> list[dict[str, Any]]:
    low_signal = re.compile(
        r"^(?:how far are we\b|is this a raw subagent\b|oh\b.*\b(?:i see|got it)\b|"
        r"ok(?:ay)?\b|thanks?\b)",
        flags=re.IGNORECASE,
    )
    directive = re.compile(
        r"^(?:also\b|before\b|do not\b|don't\b|let's\b|no,?\s+that\b|redispatch\b|"
        r"use\b|we\b.*\b(?:orient|resume|continue)\b)|"
        r"\b(?:must|should|do|keep|make|redispatch|remove|replace|revise|show|update)\b",
        flags=re.IGNORECASE,
    )
    paired = paired_intent_ids or set()
    candidates = [
        intent
        for intent in intents
        if (
            str(intent.get("projection_id") or "") in paired
            or (
                not str(intent.get("summary") or "").strip().endswith("?")
                and not low_signal.match(str(intent.get("summary") or "").strip())
                and directive.search(str(intent.get("summary") or "").strip())
            )
        )
    ]
    selected: list[dict[str, Any]] = []
    selected_tokens: list[tuple[float, list[str]]] = []
    for candidate in sorted(candidates, key=lambda row: float(row.get("at") or 0), reverse=True):
        summary = str(candidate.get("summary") or "").casefold().strip()
        at = float(candidate.get("at") or 0)
        tokens = [
            token
            for token in re.findall(r"[a-z0-9]+", summary)
            if token
            not in {
                "a",
                "again",
                "an",
                "can",
                "could",
                "let",
                "please",
                "the",
                "this",
                "us",
                "would",
                "you",
            }
        ]
        duplicate = any(
            prior_at - at <= SEMANTIC_CURRENT_HORIZON_SEC
            and tokens
            and prior_tokens
            and tokens[0] == prior_tokens[0]
            and (
                len(set(tokens) & set(prior_tokens)) / min(len(set(tokens)), len(set(prior_tokens)))
            )
            >= 0.8
            for prior_at, prior_tokens in selected_tokens
        )
        if duplicate:
            continue
        selected_tokens.append((at, tokens))
        selected.append(candidate)
    return selected[:MAX_PRIMARY_STEERING_NODES]


def _structural_steering_episodes(
    intents: list[dict[str, Any]],
    facts: list[dict[str, Any]],
    relations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    facts_by_id = {str(fact["fact_id"]): fact for fact in facts}
    reaction_types = {"work_birth", "work_result", "gate_decision", "result", "decision"}
    reactions = [fact for fact in facts if fact.get("type") in reaction_types]
    episodes: list[dict[str, Any]] = []
    for intent in intents:
        source_fact = facts_by_id.get(str(intent.get("derived_from") or ""))
        source_branch = source_fact.get("branch") if source_fact else None
        if not isinstance(source_branch, dict):
            continue
        source_record = source_branch.get("record_id")
        source_harness = source_branch.get("harness")
        source_sid = source_branch.get("sid")
        if not source_record or not source_harness or not source_sid:
            continue
        candidates = []
        for reaction in reactions:
            reaction_branch = reaction.get("branch")
            if not isinstance(reaction_branch, dict):
                continue
            if (
                reaction_branch.get("turn_id") == source_record
                and reaction_branch.get("harness") == source_harness
                and reaction_branch.get("sid") == source_sid
                and reaction_branch.get("branch_id")
            ):
                candidates.append(reaction)
        if not candidates:
            continue
        reaction = min(
            candidates,
            key=lambda fact: (float(fact.get("at") or 0), str(fact.get("fact_id") or "")),
        )
        episode_id = _semantic_id(
            "episode", intent["projection_id"], reaction["fact_id"], "structural"
        )
        episodes.append(
            {
                "episode_id": episode_id,
                "intent_id": intent["projection_id"],
                "adaptation_fact": reaction["fact_id"],
                "confidence": "structural",
                "provenance": "assistant branch descends from the user turn",
            }
        )
        relations.append(
            {
                "from": intent["projection_id"],
                "to": reaction["fact_id"],
                "type": "elicits",
                "confidence": "structural",
                "provenance": "assistant branch descends from the user turn",
            }
        )
    return sorted(
        episodes,
        key=lambda episode: float(facts_by_id[str(episode["adaptation_fact"])].get("at") or 0),
        reverse=True,
    )


def _semantic_model(
    events: list[dict[str, Any]],
    observers: list[dict[str, Any]],
    *,
    now: float | None = None,
) -> dict[str, Any]:
    """Immutable source facts, explicit relations, and replaceable projections."""
    ordered = sorted(
        _bind_dispatch_artifacts(events), key=lambda event: float(event.get("at") or 0)
    )
    facts: list[dict[str, Any]] = []
    work_items: dict[str, dict[str, Any]] = {}
    titled_work_items: set[str] = set()
    contributors: dict[str, dict[str, Any]] = {}
    relations: list[dict[str, Any]] = []
    intent_projections: list[dict[str, Any]] = []
    intent_summaries: set[str] = set()
    fact_by_work_item: dict[str, list[dict[str, Any]]] = {}
    for source_event in ordered:
        raw_kind = str(source_event.get("kind") or "")
        fact_type = _SEMANTIC_FACT_TYPES.get(raw_kind)
        if fact_type is None:
            continue
        work_item_id, work_item_kind, work_item_label, binding = _semantic_work_identity(
            source_event, raw_kind
        )
        fact = _semantic_fact_from_event(source_event, raw_kind, fact_type, work_item_id)
        fact_id = str(fact["fact_id"])
        facts.append(fact)
        if raw_kind == "steer" and fact.get("intent_promoted") is True:
            _append_semantic_intent(fact, intent_summaries, intent_projections, relations)
        if not work_item_id:
            continue
        work_item = _semantic_work_item(
            work_items,
            titled_work_items,
            work_item_id,
            work_item_kind,
            work_item_label,
            source_event,
            raw_kind,
        )
        source_binding = _semantic_source_binding(source_event, work_item_kind, binding)
        if source_binding not in work_item["source_bindings"]:
            work_item["source_bindings"].append(source_binding)
        fact_by_work_item.setdefault(work_item_id, []).append(fact)
        work_relation = _semantic_work_relation(source_event, raw_kind, fact_id, work_item_id)
        if work_relation is not None:
            relations.append(work_relation)
        relations.extend(
            _semantic_topology_relations(source_event, raw_kind, fact_id, work_item_id)
        )
        contributor_ref = str(source_event.get("contributor_ref") or "")
        if contributor_ref:
            contributor_id = _semantic_id("contributor", contributor_ref)
            contributors.setdefault(
                contributor_id,
                {
                    "contributor_id": contributor_id,
                    "source_label": contributor_ref,
                    "identity_status": "unverified source label",
                },
            )
            if contributor_id not in work_item["contributor_refs"]:
                work_item["contributor_refs"].append(contributor_id)
            relations.append(
                {
                    "from": contributor_id,
                    "to": work_item_id,
                    "type": "contributes_to",
                    "confidence": "source-labeled",
                    "provenance": source_event.get("source"),
                }
            )

    facts.extend(_semantic_observer_facts(observers))
    facts.sort(key=lambda fact: float(fact.get("at") or 0), reverse=True)
    trail_heads = _semantic_trail_heads(fact_by_work_item, facts)
    assignments = _semantic_assignments(fact_by_work_item, work_items)
    steering_episodes = _structural_steering_episodes(intent_projections, facts, relations)
    paired_intent_ids = {str(episode["intent_id"]) for episode in steering_episodes}
    activity = _semantic_activity_projection(work_items, trail_heads, facts, now=now)
    activity["steering"] = _recent_steering_nodes(intent_projections, paired_intent_ids)
    return {
        "facts": facts,
        "work_items": list(work_items.values()),
        "contributors": list(contributors.values()),
        "relations": relations,
        "projections": {
            "operator_intents": intent_projections,
            "trail_heads": trail_heads,
            "assignments": assignments,
            "activity": activity,
            "steering_episodes": steering_episodes,
            "candidate_goal_shifts": [],
        },
    }


def _history_sources(
    semantic: dict[str, Any], history: dict[str, Any]
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    facts = list(semantic.get("facts") or [])
    work_items = list(semantic.get("work_items") or [])
    facts_by_id = {str(fact.get("fact_id")): fact for fact in facts}
    work_by_id = {
        str(item.get("work_item_id")): item for item in work_items if item.get("work_item_id")
    }
    for event in history.get("events", []):
        if not isinstance(event, dict):
            continue
        fact = event.get("fact")
        item = event.get("work_item")
        if isinstance(fact, dict) and fact.get("fact_id"):
            facts_by_id.setdefault(str(fact["fact_id"]), fact)
        if isinstance(item, dict) and item.get("work_item_id"):
            work_by_id.setdefault(str(item["work_item_id"]), item)
    return facts_by_id, work_by_id


def _history_intents(
    history: dict[str, Any],
    facts_by_id: dict[str, dict[str, Any]],
    projections: dict[str, Any],
    relations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    intents = list(projections.get("operator_intents") or [])
    intent_ids = {str(intent.get("derived_from")) for intent in intents}
    for event in history.get("events", []):
        if not isinstance(event, dict):
            continue
        fact = facts_by_id.get(str(event.get("source_ref") or ""))
        if (
            fact is None
            or fact.get("intent_promoted") is not True
            or str(fact.get("fact_id")) in intent_ids
        ):
            continue
        intent, relation = _semantic_intent(fact)
        intents.append(intent)
        relations.append(relation)
        intent_ids.add(str(fact["fact_id"]))
    return intents


def _history_activity_nodes(
    history: dict[str, Any], current_event_ids: set[str]
) -> list[dict[str, Any]]:
    consequential = {
        "assignment",
        "checkpoint",
        "gate_decision",
        "result",
        "final_output",
        "stage_transition",
    }
    nodes: list[dict[str, Any]] = []
    for event in history.get("events", []):
        if not isinstance(event, dict):
            continue
        if (
            event.get("event_type") not in consequential
            or not event.get("work_binding")
            or str(event.get("source_ref") or "") in current_event_ids
        ):
            continue
        nodes.append(
            {
                "kind": "work",
                "at": event.get("at"),
                "status": (
                    "prepared"
                    if event.get("event_type") == "assignment"
                    else "decision"
                    if event.get("event_type") == "gate_decision"
                    else "outcome"
                ),
                "work_item_ids": [event["work_binding"]],
                "latest_event": event.get("source_ref"),
                "history_event_type": event.get("event_type"),
            }
        )
    return nodes[:MAX_PRIMARY_ACTIVITY_NODES]


def _materialize_history_topology(
    facts: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    relation_keys: set[tuple[Any, ...]],
) -> None:
    for fact in facts:
        work_item_id = str(fact.get("work_item_id") or "")
        source_kind = str(fact.get("source_kind") or "")
        branch = fact.get("branch")
        if not work_item_id or not isinstance(branch, dict):
            continue
        evidence = fact.get("evidence")
        source_event = {
            "harness": branch.get("harness"),
            "sid": branch.get("sid"),
            "source": evidence.get("source") if isinstance(evidence, dict) else None,
        }
        topology = _semantic_topology_relations(
            source_event, source_kind, str(fact.get("fact_id") or ""), work_item_id
        )
        for relation in topology:
            key = _semantic_relation_key(relation)
            if key not in relation_keys:
                relations.append(relation)
                relation_keys.add(key)


def _semantic_relation_key(relation: Mapping[str, Any]) -> tuple[Any, ...]:
    key: tuple[Any, ...] = (
        relation.get("from"),
        relation.get("to"),
        relation.get("type"),
    )
    if relation.get("type") in {"dispatches_to", "returns_to"}:
        return (*key, relation.get("evidence_ref"))
    return key


def _merge_semantic_history(
    semantic: dict[str, Any], history: dict[str, Any], *, now: float
) -> dict[str, Any]:
    """Let persisted meaning outlive the bounded source tail without becoming authority."""
    facts_by_id, work_by_id = _history_sources(semantic, history)
    facts = sorted(facts_by_id.values(), key=lambda fact: float(fact.get("at") or 0), reverse=True)
    projections = semantic.get("projections")
    if not isinstance(projections, dict):
        projections = {}
        semantic["projections"] = projections
    relations = list(semantic.get("relations") or [])
    relation_keys = {_semantic_relation_key(row) for row in relations if isinstance(row, dict)}
    _materialize_history_topology(facts, relations, relation_keys)
    for event in history.get("events", []):
        if not isinstance(event, dict):
            continue
        for relation in event.get("relations", []):
            if not isinstance(relation, dict):
                continue
            key = _semantic_relation_key(relation)
            if key in relation_keys:
                continue
            relations.append(relation)
            relation_keys.add(key)
    intents = _history_intents(history, facts_by_id, projections, relations)
    fact_by_work_item: dict[str, list[dict[str, Any]]] = {}
    for fact in facts:
        work_item_id = str(fact.get("work_item_id") or "")
        if work_item_id:
            fact_by_work_item.setdefault(work_item_id, []).append(fact)
    trails = _semantic_trail_heads(fact_by_work_item, facts)
    assignments = _semantic_assignments(fact_by_work_item, work_by_id)
    episodes = _structural_steering_episodes(intents, facts, relations)
    paired = {str(episode["intent_id"]) for episode in episodes}
    activity = _semantic_activity_projection(work_by_id, trails, facts, now=now)
    current_event_ids = {str(node.get("latest_event") or "") for node in activity.get("nodes", [])}
    activity["history_nodes"] = _history_activity_nodes(history, current_event_ids)
    activity["steering"] = _recent_steering_nodes(intents, paired)
    semantic["facts"] = facts
    semantic["work_items"] = list(work_by_id.values())
    semantic["relations"] = relations
    projections["operator_intents"] = sorted(
        intents, key=lambda intent: float(intent.get("at") or 0), reverse=True
    )
    projections["trail_heads"] = trails
    projections["assignments"] = assignments
    projections["activity"] = activity
    projections["steering_episodes"] = episodes
    semantic["history"] = {
        "event_count": len(history.get("events", [])),
        "window_sec": history.get("window_sec", semantic_history.HISTORY_WINDOW_SEC),
        "cursors": history.get("cursors", {}),
        "persisted": history.get("persisted") is True,
        "events": [
            {
                key: event.get(key)
                for key in (
                    "event_id",
                    "event_type",
                    "at",
                    "source_identity",
                    "source_ref",
                    "work_binding",
                    "summary",
                )
            }
            for event in history.get("events", [])
            if isinstance(event, dict)
        ],
    }
    return semantic


def _focused_semantic_history(
    history: dict[str, Any],
    focus: tuple[str, str],
    allowed_gate_work_items: set[str],
) -> dict[str, Any]:
    """Project facts cross session boundaries; transcript facts do not."""
    focused_events: list[dict[str, Any]] = []
    wanted = {"harness": focus[0], "sid": focus[1]}
    for event in history.get("events", []):
        if not isinstance(event, dict):
            continue
        fact = event.get("fact")
        if not isinstance(fact, dict):
            continue
        if (
            fact.get("type") == "gate_decision"
            and fact.get("work_item_id") not in allowed_gate_work_items
        ):
            continue
        if fact.get("scope") in {"project", "workflow"}:
            focused_events.append(event)
            continue
        if fact.get("source_session") == wanted or fact.get("parent_session") == wanted:
            focused_events.append(event)
    return {**history, "events": focused_events}


def _focused_graph_scope(
    focus: tuple[str, str], child_assignments: list[dict[str, Any]]
) -> tuple[set[tuple[str, str]], set[str]]:
    wanted = {"harness": focus[0], "sid": focus[1]}
    allowed_sessions = {(focus[0], focus[1])}
    allowed_work_items: set[str] = set()
    for assignment in child_assignments:
        if not isinstance(assignment, dict) or assignment.get("parent_session") != wanted:
            continue
        observer_sid = records.safe_text(assignment.get("observer_sid"), 128)
        if observer_sid:
            allowed_sessions.add((focus[0], observer_sid))
        work_item_id = records.safe_text(assignment.get("work_item_id"), 256)
        if work_item_id:
            allowed_work_items.add(work_item_id)
    return allowed_sessions, allowed_work_items


def _fact_session_identity(fact: Mapping[str, Any], key: str) -> tuple[str, str]:
    value = fact.get(key)
    if not isinstance(value, dict):
        return "", ""
    return str(value.get("harness") or ""), str(value.get("sid") or "")


def _focused_graph_facts(
    semantic: Mapping[str, Any],
    allowed_sessions: set[tuple[str, str]],
    allowed_work_items: set[str],
) -> list[dict[str, Any]]:
    session_facts: list[dict[str, Any]] = []
    for fact in semantic.get("facts", []):
        if not isinstance(fact, dict):
            continue
        if (
            _fact_session_identity(fact, "source_session") not in allowed_sessions
            and _fact_session_identity(fact, "parent_session") not in allowed_sessions
        ):
            continue
        session_facts.append(copy.deepcopy(fact))
        work_item_id = str(fact.get("work_item_id") or "")
        if work_item_id:
            allowed_work_items.add(work_item_id)
    project_facts = [
        copy.deepcopy(fact)
        for fact in semantic.get("facts", [])
        if isinstance(fact, dict)
        and fact.get("scope") in {"project", "workflow"}
        and str(fact.get("work_item_id") or "") in allowed_work_items
    ]
    facts_by_id = {
        str(fact["fact_id"]): fact
        for fact in [*session_facts, *project_facts]
        if fact.get("fact_id")
    }
    return sorted(facts_by_id.values(), key=lambda fact: float(fact.get("at") or 0), reverse=True)


def _focused_semantic_graph(
    semantic: dict[str, Any],
    focus: tuple[str, str],
    child_assignments: list[dict[str, Any]],
    *,
    now: float,
) -> dict[str, Any]:
    """Filter the project graph by exact provenance instead of rebuilding it."""
    allowed_sessions, allowed_work_items = _focused_graph_scope(focus, child_assignments)
    facts = _focused_graph_facts(semantic, allowed_sessions, allowed_work_items)
    facts_by_id = {str(fact["fact_id"]): fact for fact in facts}
    work_items = {
        str(item["work_item_id"]): copy.deepcopy(item)
        for item in semantic.get("work_items", [])
        if isinstance(item, dict) and str(item.get("work_item_id") or "") in allowed_work_items
    }
    contributor_ids = {
        str(contributor_id)
        for item in work_items.values()
        for contributor_id in item.get("contributor_refs", [])
        if contributor_id
    }
    contributors = [
        copy.deepcopy(contributor)
        for contributor in semantic.get("contributors", [])
        if isinstance(contributor, dict)
        and str(contributor.get("contributor_id") or "") in contributor_ids
    ]
    original_projections = semantic.get("projections")
    if not isinstance(original_projections, dict):
        original_projections = {}
    intents = [
        copy.deepcopy(intent)
        for intent in original_projections.get("operator_intents", [])
        if isinstance(intent, dict) and str(intent.get("derived_from") or "") in facts_by_id
    ]
    projection_ids = {
        str(intent.get("projection_id") or "") for intent in intents if intent.get("projection_id")
    }
    node_ids = set(facts_by_id) | set(work_items) | contributor_ids | projection_ids
    relations = [
        copy.deepcopy(relation)
        for relation in semantic.get("relations", [])
        if isinstance(relation, dict)
        and (
            str(relation.get("evidence_ref") or "") in facts_by_id
            or (
                str(relation.get("from") or "") in node_ids
                and str(relation.get("to") or "") in node_ids
            )
        )
    ]
    fact_by_work_item: dict[str, list[dict[str, Any]]] = {}
    for fact in facts:
        work_item_id = str(fact.get("work_item_id") or "")
        if work_item_id and work_item_id in work_items:
            fact_by_work_item.setdefault(work_item_id, []).append(fact)
    trails = _semantic_trail_heads(fact_by_work_item, facts)
    assignments = _semantic_assignments(fact_by_work_item, work_items)
    episodes = _structural_steering_episodes(intents, facts, relations)
    paired = {str(episode["intent_id"]) for episode in episodes}
    activity = _semantic_activity_projection(work_items, trails, facts, now=now)
    activity["steering"] = _recent_steering_nodes(intents, paired)
    history = semantic.get("history")
    if not isinstance(history, dict):
        history = {}
    history_events = [
        copy.deepcopy(event)
        for event in history.get("events", [])
        if isinstance(event, dict) and str(event.get("source_ref") or "") in facts_by_id
    ]
    return {
        **copy.deepcopy(semantic),
        "facts": facts,
        "work_items": list(work_items.values()),
        "contributors": contributors,
        "relations": relations,
        "projections": {
            **copy.deepcopy(original_projections),
            "operator_intents": intents,
            "trail_heads": trails,
            "assignments": assignments,
            "activity": activity,
            "steering_episodes": episodes,
        },
        "history": {**copy.deepcopy(history), "events": history_events},
    }


def _semantic_for_focus(
    semantic: dict[str, Any],
    focus: tuple[str, str] | None,
    child_assignments: list[dict[str, Any]],
    *,
    now: float,
) -> dict[str, Any]:
    if focus is None:
        return semantic
    return _focused_semantic_graph(semantic, focus, child_assignments, now=now)


def _authorization_resolved(request: Mapping[str, Any], facts: list[dict[str, Any]]) -> bool:
    source = request.get("source_session")
    request_at = float(request.get("at") or 0)
    for fact in facts:
        if float(fact.get("at") or 0) <= request_at or fact.get("source_session") != source:
            continue
        evidence = fact.get("evidence")
        if not isinstance(evidence, dict) or evidence.get("confidence") != "exact":
            continue
        text = str(fact.get("detail") or fact.get("summary") or "")
        if fact.get("type") == "user_message" and _AUTHORIZATION_ANSWER_RE.search(text):
            return True
        if fact.get("type") == "result" and _AUTHORIZATION_RESULT_RE.search(text):
            return True
    return False


def _command_attention_projection(semantic: Mapping[str, Any]) -> list[dict[str, Any]]:
    facts = [fact for fact in semantic.get("facts", []) if isinstance(fact, dict)]
    labels = {
        str(item.get("work_item_id") or ""): str(item.get("label") or "")
        for item in semantic.get("work_items", [])
        if isinstance(item, dict)
    }
    projected: list[dict[str, Any]] = []
    for fact in facts:
        request = fact.get("authorization_request")
        if not isinstance(request, dict) or request.get("status") != "open":
            continue
        if _authorization_resolved(fact, facts):
            continue
        work_item_id = str(fact.get("work_item_id") or "")
        label = labels.get(work_item_id) or "Codex session result"
        projected.append(
            {
                "projection_id": _semantic_id("command-attention", fact.get("fact_id")),
                "at": fact.get("at"),
                "owner": "CAPTAIN",
                "kind": str(request.get("kind") or "authorization"),
                "label": label,
                "question": str(request.get("question") or ""),
                "work_item_id": work_item_id or None,
                "source_fact": fact.get("fact_id"),
                "evidence": copy.deepcopy(fact.get("evidence") or {}),
            }
        )
    return sorted(projected, key=lambda item: float(item.get("at") or 0), reverse=True)


def _with_command_attention(
    semantic: dict[str, Any], coverage: Mapping[str, Any]
) -> dict[str, Any]:
    projections = semantic.get("projections")
    if not isinstance(projections, dict):
        projections = {}
        semantic["projections"] = projections
    projections["command_attention"] = _command_attention_projection(semantic)
    projections["command_attention_coverage"] = dict(coverage)
    return semantic


def _active_child_assignments(
    config: RuntimeConfig,
    state: RuntimeState,
    session: Mapping[str, Any],
    *,
    now: float,
    refresh: bool,
    model_consent: bool = False,
) -> list[dict[str, Any]]:
    hierarchy = session.get("subagent_hierarchy")
    if not isinstance(hierarchy, list):
        return []
    assignments: list[dict[str, Any]] = []
    parent_harness = records.safe_text(session.get("harness"), 32)
    parent_sid = records.safe_text(session.get("sid"), 128)
    parent_session = (
        {"harness": parent_harness, "sid": parent_sid} if parent_harness and parent_sid else None
    )
    for raw_child in hierarchy[:MAX_ACTIVE_CHILD_OBSERVERS]:
        if not isinstance(raw_child, dict):
            continue
        child = records.as_dict(raw_child)
        row: dict[str, Any] = {
            "name": records.safe_text(child.get("name") or "subagent", 70),
            "depth": child.get("depth"),
            "parent_name": child.get("parent_name"),
            "observer_sid": child.get("observer_sid"),
            **({"parent_session": parent_session} if parent_session else {}),
        }
        workflow_entity = child.get("workflow_entity")
        workflow_stage = child.get("workflow_stage")
        workflow_binding = child.get("workflow_binding")
        if isinstance(workflow_entity, str) and isinstance(workflow_stage, str):
            row.update(
                {
                    "workflow_entity": workflow_entity,
                    "workflow_stage": workflow_stage,
                    **(
                        {"workflow_binding": workflow_binding}
                        if isinstance(workflow_binding, str) and workflow_binding
                        else {}
                    ),
                    **(
                        {
                            "work_item_id": semantic_history.workflow_work_item_id(
                                workflow_binding, workflow_entity
                            )
                        }
                        if isinstance(workflow_binding, str) and workflow_binding
                        else {}
                    ),
                }
            )
        exact = child.get("assignment")
        if isinstance(exact, str) and exact:
            assignments.append(
                {
                    **row,
                    "assignment": exact,
                    "confidence": "exact",
                    "source": child.get("assignment_status") or "exact parent dispatch",
                }
            )
            continue
        child_sid = child.get("observer_sid")
        if not isinstance(child_sid, str) or not child_sid:
            assignments.append({**row, "assignment": None, "confidence": "unavailable"})
            continue
        transcript_path = observer.resolve_transcript(config, state, "codex", child_sid)
        if transcript_path is None:
            assignments.append({**row, "assignment": None, "confidence": "unavailable"})
            continue
        observed = _observe_session(
            config,
            state,
            transcript_path,
            ("codex", child_sid),
            now=now,
            refresh=refresh,
            child_activity_fallback=True,
            model_consent=model_consent,
        )
        if observed is None:
            assignments.append({**row, "assignment": None, "confidence": "unavailable"})
            continue
        goal = observed.get("goal")
        if not isinstance(goal, str) or not goal or goal == observer.NO_GOAL:
            assignments.append({**row, "assignment": None, "confidence": "unavailable"})
            continue
        assignments.append(
            {
                **row,
                "assignment": goal,
                "confidence": "derived",
                "source": (
                    "bounded child observer snapshot"
                    if observed.get("snapshot_status") == "refreshed"
                    else "cached child observer snapshot"
                ),
                "observed_at": observed.get("observed_at"),
                "snapshot_status": observed.get("snapshot_status"),
            }
        )
    return assignments


def collect(
    config: RuntimeConfig,
    state: RuntimeState,
    sessions: Sequence[Mapping[str, Any]],
    project: str,
    *,
    now: float,
    refresh: bool = False,
    focus: tuple[str, str] | None = None,
    model_consent: bool = False,
) -> dict[str, Any]:
    """Observer results and a real project event log for exact-label sessions."""
    analysis_sessions, omitted, scope, surrounding_active = _analysis_context_sessions(
        sessions, project, focus
    )
    attention_sessions, attention_coverage = _attention_context_sessions(sessions, project)
    workflow_discovery = _project_workflow_discovery(
        config,
        state,
        analysis_sessions,
        project,
        now=now,
        refresh=refresh,
    )
    observers: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    history_events: list[dict[str, Any]] = []
    gate_events: list[dict[str, Any]] = []
    history_source_scans: dict[str, dict[str, int]] = {}
    unavailable: list[dict[str, str]] = []
    briefings = 0
    child_assignments: list[dict[str, Any]] = []
    support_totals = {
        "tool_calls": 0,
        "dispatch_builds": 0,
        "subagent_calls": 0,
        "pending_subagents": 0,
        "suppressed_tool_calls": 0,
        "collapsed_contributors": 0,
    }
    omitted_rows = [
        {
            "harness": str(session.get("harness") or ""),
            "sid": str(session.get("sid") or ""),
            "reason": f"bounded to {MAX_PROJECT_OBSERVERS} newest active sessions",
        }
        for session in omitted
    ]
    for session in analysis_sessions:
        harness = str(session.get("harness") or "")
        sid = str(session.get("sid") or "")
        identity = {"harness": harness, "sid": sid}
        is_focused = focus is not None and (harness, sid) == focus
        if is_focused and harness == "codex":
            child_assignments = _active_child_assignments(
                config,
                state,
                session,
                now=now,
                refresh=refresh,
                model_consent=model_consent,
            )
        transcript_path = observer.resolve_transcript(config, state, harness, sid)
        if transcript_path is None:
            unavailable.append({**identity, "reason": "transcript reader unavailable"})
            continue
        result = _observe_session(
            config,
            state,
            transcript_path,
            (harness, sid),
            now=now,
            refresh=refresh and is_focused,
            model_consent=model_consent,
        )
        if result is not None:
            observers.append(
                {
                    **identity,
                    **result,
                    "source": "cached observer snapshot"
                    if str(result.get("snapshot_status", "")).startswith("cached")
                    else "bounded transcript and entity state",
                }
            )
        events.extend(instruction_events(config, transcript_path, harness, sid))
        work_rows, work_support = _work_evidence(config, transcript_path, harness, sid)
        events.extend(work_rows)
        backfill_rows, signature = _incremental_history_events(
            config, state, project, transcript_path, harness, sid, now=now
        )
        history_events.extend(backfill_rows)
        source_identity = f"{harness}:{sid}"
        if signature is not None:
            history_source_scans[source_identity] = signature
        _merge_support_counts(support_totals, work_support)
        gate_rows, prepared = _gate_context(config, state, transcript_path, harness, sid)
        gate_events.extend(gate_rows)
        briefings += prepared

    project_gate_rows, prepared = _project_peer_gate_context(config, state, sessions, project, None)
    gate_events.extend(project_gate_rows)
    briefings += prepared
    _scope_gate_events(
        events,
        history_events,
        gate_events,
        None,
        child_assignments,
        semantic_history.read(config, state, project),
    )

    timeline = _dedupe_project_events(events, limit=MAX_PROJECT_EVENTS)
    history_timeline = _dedupe_project_events(history_events)
    gate_count, steer_count, work_count = _timeline_counts(timeline)
    semantic = _semantic_model(timeline, observers, now=now)
    history_semantic = _semantic_model(history_timeline, observers, now=now)
    history = semantic_history.update(
        config,
        state,
        project,
        history_semantic,
        attention_sessions,
        child_assignments,
        now=now,
        source_scans=history_source_scans,
    )
    semantic = _with_command_attention(
        _semantic_for_focus(
            _merge_semantic_history(semantic, history, now=now),
            focus,
            child_assignments,
            now=now,
        ),
        attention_coverage,
    )
    return {
        "observer_model": {
            "enabled": config.observer_model_enabled,
            "max_prompt_bytes": observer.OBSERVER_MODEL_MAX_PROMPT_BYTES,
            "disclosure": (
                "Send redacted transcript excerpts and workflow stage to OpenAI through Codex "
                "for a goal summary? Each prompt is capped at 16 KiB, with a 60-second timeout "
                "and one call in flight per session. A focused refresh can include up to three "
                "active child sessions. --no-observer-model refuses calls for this run."
            ),
        },
        "project": project,
        "focus": {
            "harness": focus[0],
            "sid": focus[1],
            "observed": any(
                row.get("harness") == focus[0] and row.get("sid") == focus[1] for row in observers
            ),
        }
        if focus
        else None,
        "observers": observers,
        "events": timeline,
        "semantic": semantic,
        "workflow_discovery": workflow_discovery,
        "child_assignments": child_assignments,
        "sources": {
            "scope": scope,
            "surrounding_active": surrounding_active,
            "observer": {
                "live": len(observers),
                "unavailable": unavailable,
                "omitted": omitted_rows,
            },
            "gate": {
                "live": gate_count,
                "untimestamped_prepare": briefings,
                "status_history": "unavailable",
            },
            "steer": {
                "live": steer_count,
                "unavailable": unavailable,
                "omitted": omitted_rows,
            },
            "work": {
                "live": work_count,
                "support": support_totals,
                "unavailable": unavailable,
                "omitted": omitted_rows,
            },
        },
    }
