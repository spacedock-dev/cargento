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
from typing import TYPE_CHECKING, Any, NamedTuple

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
    # One fact type for a check and a write; `subject` tells them apart. The
    # ruling `claude_tool_reports` cites, item 6.
    "check_run": "tool_report",
    "path_written": "tool_report",
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


def _cached_text(value: Any, cap: int) -> str | None:
    """One re-read sidecar string, bounded and scrubbed, or nothing.

    The isinstance was once the whole check, on the argument that the observer
    had already bounded what it wrote. That holds on the fresh path and not
    here, where the sidecar is re-read under `state_read_cap_bytes` from a file
    any local process could have rewritten: a type check is not a bound. One
    cap for all three rather than a threshold each, because nobody would tune a
    stage name apart from a reason literal and `config.py` grows a field per
    feature as it is.
    """
    return records.safe_text(value, cap) if isinstance(value, str) else None


# Which arm produced a published goal. "unknown" is for a sidecar written
# before the field existed, and is never inferred into one of the other two.
_GOAL_SOURCES = frozenset({"deterministic", "model"})


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
        # A sidecar written before goal provenance existed carries neither
        # field. "unknown" rather than "deterministic": defaulting to the
        # latter would relabel every already-cached model goal as something a
        # source published, which is the one substitution DRC-4509 forbids.
        cached_source = cached_payload.get("goal_source")
        # Every one of these is re-read from a file any local process could have
        # rewritten, so each is checked on the way out rather than only on the
        # way in. `goal` above was already checked and `goal_source` is checked
        # against a frozen set; these four were not, and a dict here reaches the
        # served payload verbatim. `deterministic_goal` is a goal line, so it
        # carries the same bound a freshly derived one does.
        raw_deterministic = cached_payload.get("deterministic_goal")
        return {
            "goal": goal,
            "deterministic_goal": (
                records.safe_text(raw_deterministic, config.observer_goal_cap_chars)
                if isinstance(raw_deterministic, str)
                else None
            ),
            "goal_source": cached_source if cached_source in _GOAL_SOURCES else "unknown",
            "stage": _cached_text(cached_payload.get("stage"), config.observer_block_cap_chars),
            "block": _cached_text(cached_payload.get("block"), config.observer_block_cap_chars),
            "reason": _cached_text(cached_payload.get("reason"), config.observer_block_cap_chars),
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
            # A third writer of `goal`, and a model wrote it: this arm is only
            # reached with a caller in hand.
            result["goal_source"] = "model"
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


# The checks a Claude Code session ran and the files it wrote, as the
# transcript recorded them. The ruling `claude_tool_reports` cites owns every
# rule below; the closed runner list and the result patterns are its "The
# closed lists" section, written out, with the owner's rulings and the review's
# clarifications of 2026-09-24.
#
# Called from `collect` only, never from `_semantic_history_source_events`, so
# the history store never sees these facts; `semantic_history._FACT_EVENT_TYPES`
# not naming the type is the second wall (item 6).
_TOOL_REPORT_KINDS = frozenset({"check_run", "path_written"})
TOOL_REPORT_MAX_ENTRIES = 12
TOOL_REPORT_LINE_CHARS = 120
# The existing ledger cap (`reading.LEDGER_SUMMARY_CAP_CHARS`), which item 5 names.
TOOL_REPORT_TAIL_CHARS = 180
TOOL_REPORT_PATH_CHARS = 240
_WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_PYTHON_RE = re.compile(r"^python(?:\d+(?:\.\d+)?)?$")
_DURATION_RE = re.compile(r"^\d+(?:\.\d+)?[smhd]?$")
_REDIRECT_RE = re.compile(r"^(?:\d*>&\d+|&>.*|\d*>>?.+|<.+)$")
# One shell line in tokens: quoted runs, command substitutions, escapes, the
# joiners, the redirects (`2>&1`, `>&2`, `&>`) that must not read as a
# background `&`, and a `#` that may start a comment.
_SHELL_TOKEN_RE = re.compile(
    r"""'[^']*'?|"(?:\\.|[^"\\])*"?|\$\((?:[^()]|\([^()]*\))*\)?|`[^`]*`?|\\.|&&|\|\||[;|\n]"""
    r"""|\d*>&\d*|&>|&|#[^\n]*|[^'"\;|&\n>`$#]+|.""",
    re.DOTALL,
)
_SHELL_JOINERS = frozenset({"&&", "||", ";", "|", "\n", "&"})
_SUBSTITUTION_RE = re.compile(r"\$\((?:[^()]|\([^()]*\))*\)?|`[^`]*`?")
_HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
_WRAPPER_PAIRS = (["poetry", "run"], ["pipenv", "run"], ["pnpm", "exec"])
_UV_VALUE_OPTIONS = frozenset(
    {"--with", "--with-requirements", "--python", "-p", "--project", "--directory", "--extra",
     "--group", "--package", "--env-file", "--index"}
)  # fmt: skip
# Runners named by their first word, by their first two, and by three.
_CHECK_WORDS = frozenset(
    {
        "pytest", "py.test", "nose2", "tox", "nox", "jest", "vitest", "mocha", "rspec",
        "phpunit", "ctest", "flake8", "pylint", "eslint", "stylelint", "golangci-lint",
        "rubocop", "shellcheck", "mypy", "pyright", "tsc",
    }
)  # fmt: skip
_CHECK_PAIRS = frozenset(
    {
        ("npm", "test"), ("pnpm", "test"), ("yarn", "test"), ("bun", "test"),
        ("deno", "test"), ("go", "test"), ("cargo", "test"), ("cargo", "nextest"),
        ("mvn", "test"), ("gradle", "test"), ("./gradlew", "test"), ("dotnet", "test"),
        ("rake", "test"), ("swift", "test"), ("make", "test"), ("make", "check"),
        ("pnpm", "build"), ("yarn", "build"), ("cargo", "build"), ("go", "build"),
        ("make", "build"), ("mvn", "package"), ("gradle", "build"), ("./gradlew", "build"),
        ("dotnet", "build"), ("swift", "build"), ("vite", "build"), ("ruff", "check"),
        ("cargo", "clippy"), ("cargo", "check"), ("go", "vet"),
    }
)  # fmt: skip
_CHECK_TRIPLES = frozenset(
    {
        ("bundle", "exec", "rspec"), ("npm", "run", "test"), ("pnpm", "run", "test"),
        ("npm", "run", "build"), ("pnpm", "run", "build"), ("bun", "run", "build"),
    }
)  # fmt: skip
# Runners that are checks only with `--check` among their words.
_CHECK_FLAGGED = frozenset({("black",), ("prettier",), ("ruff", "format")})
# A check that rewrites files is a change too, and ages every pass, its own
# included (review, 2026-09-24).
_FIX_FLAGS = frozenset({"--fix", "--write", "--fix-only", "--unsafe-fixes"})
_INTERPRETERS = frozenset({"node", "bash", "sh", "zsh"})
_SHELL_BUILTINS = frozenset({"test", "[", "[["})
_INFO = "\u2139"  # node's summary glyph, written as an escape so review can read it
# Item 2, source (ii): summary lines. A failure anywhere in the tail wins over a
# pass, because a run that printed both failed. Matched per line: node prints
# its pass and fail counts on lines of their own.
_SUMMARY_FAILED = re.compile(
    rf"\b[1-9]\d* failed\b|^FAILED \(|^\s*Tests:.*\b[1-9]\d* failed|^{_INFO} fail [1-9]\d*\s*$"
    r"|^FAIL\b|test result: FAILED|\b[1-9]\d* errors?\b(?! \(\d+ fixed, 0 remaining\))",
    re.MULTILINE,
)
# A pass counts only when nothing else in the tail records a failure (owner,
# 2026-09-24). Node's pass count alone is not a pass: node prints the fail count
# on the line after it, so a tail that kept one and lost the other says nothing
# about failures. Go's `ok  <pkg>` is not a pass either: go passes come from the
# error flag alone. unittest's `OK` must be the whole line.
_SUMMARY_PASSED = re.compile(
    rf"\b\d+ passed\b|^OK\s*$|^\s*Tests:\s.*\b\d+ passed|^{_INFO} fail 0\s*$"
    r"|test result: ok|^Success: no issues found|^All checks passed!",
    re.MULTILINE,
)
# Source (iii): may record a failure, never a pass. Node's cancelled count is
# one: a timed-out test prints `fail 0` beside it and exits 1 (measured on node
# 26, review 2026-09-24).
_FAILURE_MARKER = re.compile(
    r"\u2716|failing tests:|AssertionError|ERR_ASSERTION|^FAILED |^ERROR |--- FAIL:|panicked at"
    rf"|error TS\d*|^{_INFO} cancelled [1-9]\d*\s*$",
    re.MULTILINE,
)
# A pass that ran nothing is not a pass, from the flag or from a summary: it
# reads "ran, result not recorded". go's `[no test files]` counts only when no
# package printed `ok`.
_RAN_NOTHING = re.compile(
    rf"^{_INFO} pass 0\s*$|(?<![\d.])0 passed\b|^Ran 0 tests\b|\[no tests to run\]",
    re.MULTILINE,
)
_NO_TEST_FILES = re.compile(r"\[no test files\]")
_GO_OK = re.compile(r"^ok\s", re.MULTILINE)
_RESULT_ORDER = {"failed": 0, "not-recorded": 1, "passed": 2}
# A true error flag is a run that exited nonzero only when Claude Code says so;
# any other flagged result is a call that never ran: a rejection, a cancelled
# parallel call, a sibling error, a hook block or an input error (measured:
# 89% of flagged Bash results open this way; verifier, 2026-09-24).
_EXITED_RE = re.compile(r"\AExit code [1-9]\d*\b")
# Claude Code moved the call to the background itself: no result is recorded.
_MOVED_TO_BACKGROUND_RE = re.compile(
    r"\A(?:Command running in background with ID: "
    r"|Command did not complete within its \d+s timeout and was moved to the background)"
)
# Owner, 2026-09-24: the closed read-only list. A segment that is neither a
# check nor on it is timed, never kept as text; DRC-4692's levels compare the
# time with each check's latest pass. Counted, never listed, never drift.
_READ_ONLY_WORDS = frozenset(
    {"ls", "cat", "head", "tail", "grep", "rg", "find", "wc", "pwd", "echo", "which", "file",
     "stat", "tree", "less"}
)  # fmt: skip
_READ_ONLY_PAIRS = frozenset({"git status", "git log", "git diff", "git show"})
# Options that make a read-only command write or run something, per command:
# `find -o` is an OR and stays read-only, `tree -o` writes a file.
_WRITING_OPTIONS = {
    "find": frozenset(
        {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprint0", "-fprintf", "-fls"}
    ),
    "tree": frozenset({"-o"}),
    "git diff": frozenset({"--output"}),
    "git log": frozenset({"--output"}),
    "git show": frozenset({"--output"}),
}
_HARMLESS_REDIRECT_RE = re.compile(r"^(?:\d*>&\d+|\d*>/dev/null|&>/dev/null)$")


def _without_heredoc_bodies(command: str) -> str:
    """The command with every heredoc body removed: its lines are data."""
    kept: list[str] = []
    end = ""
    for line in command.split("\n"):
        if end:
            end = "" if line.strip() == end else end
            continue
        kept.append(line)
        match = _HEREDOC_RE.search(line)
        if match:
            end = match.group(2)
    return "\n".join(kept)


def _command_segments(command: str) -> list[tuple[str, str]]:
    """`(segment, joiner after it)` for each part of one shell line, outside quotes.

    Joiners are `&&`, `||`, `;`, `|`, a newline, and `&`, which sends the
    segment before it to the background. `2>&1`, `>&2` and `&>` are
    redirects. A comment is dropped, a subshell's parentheses are shed, and a
    heredoc body is not a command.
    """
    segments: list[tuple[str, str]] = []
    current: list[str] = []
    for match in _SHELL_TOKEN_RE.finditer(_without_heredoc_bodies(command)):
        token = match.group()
        if token in _SHELL_JOINERS:
            segments.append(("".join(current).strip(), token))
            current = []
        elif token.startswith("#") and (not current or current[-1][-1:].isspace()):
            continue
        else:
            current.append(token)
    segments.append(("".join(current).strip(), ""))
    return [(text.strip("()").strip(), joiner) for text, joiner in segments if text.strip("() ")]


def _segment_words(segment: str) -> list[str]:
    """Shell words of a segment, with every substituted command shown as `$(…)`."""
    text = _SUBSTITUTION_RE.sub("$(\u2026)", segment)
    try:
        return shlex.split(text)
    except ValueError:
        return text.split()


def _skip_options(words: list[str], takes_value: frozenset[str]) -> list[str]:
    while words and words[0].startswith("-"):
        words = words[2:] if words[0] in takes_value else words[1:]
    return words


def _stripped(words: list[str]) -> tuple[list[str], bool]:
    """Item 3's stripping, and whether `rtk` wrapped the runner (owner, 2026-09-24)."""
    rtk = False
    while words:
        if _ASSIGNMENT_RE.match(words[0]):
            words = words[1:]
        elif words[:2] == ["rtk", "proxy"] or words[0] == "rtk":
            words, rtk = words[2:] if words[1:2] == ["proxy"] else words[1:], True
        elif words[:2] == ["uv", "run"]:
            words = _skip_options(words[2:], _UV_VALUE_OPTIONS)
        elif words[:2] in _WRAPPER_PAIRS:
            words = words[2:]
        elif words[0] in ("npx", "bunx", "time"):
            words = words[1:]
        elif words[0] == "timeout":
            # `-s KILL` and `-k 5` carry a value; `--signal=KILL` does not.
            words = _skip_options(words[1:], frozenset({"-s", "-k", "--signal", "--kill-after"}))
            words = words[1:] if words and _DURATION_RE.match(words[0]) else words
        else:
            break
    return words, rtk


def _strip_runner_prefix(words: list[str]) -> list[str]:
    return _stripped(words)[0]


def _names_a_test_file(word: str) -> bool:
    """`test` or `tests` as a whole word of a file name, split on `_`, `-` and `.`.

    Owner, 2026-09-24: `run_tests.py` and `test.sh` count, and `runtests.py` and
    `fetch_latest_creds.py` do not.
    """
    name = os.path.basename(word).lower()
    return bool(set(re.split(r"[_.-]", name)) & {"test", "tests"}) and ("/" in word or "." in name)


def _runner_words(words: list[str]) -> list[str]:
    """The words with an interpreter or runner path shed to its name."""
    name = os.path.basename(words[0])
    if "/" in words[0] and (
        _PYTHON_RE.match(name) or name in _INTERPRETERS or name in _CHECK_WORDS
    ):
        return [name, *words[1:]]
    return words


def _is_named_runner(words: list[str]) -> bool:
    if _PYTHON_RE.match(words[0]):
        return words[1:3] in (["-m", "pytest"], ["-m", "unittest"])
    if (
        words[0] in _CHECK_WORDS
        or tuple(words[:2]) in _CHECK_PAIRS
        or tuple(words[:3]) in _CHECK_TRIPLES
    ):
        return True
    flagged = tuple(words[:1]) in _CHECK_FLAGGED or tuple(words[:2]) in _CHECK_FLAGGED
    return flagged and "--check" in words


def _is_test_program(words: list[str]) -> bool:
    """A program file whose name has `test` or `tests` as a word, run directly or
    by an interpreter; and `node --test`."""
    first = words[0]
    if first == "node" and "--test" in words:
        return True
    if _PYTHON_RE.match(first) or first in _INTERPRETERS:
        return len(words) > 1 and not words[1].startswith("-") and _names_a_test_file(words[1])
    return _names_a_test_file(first)


def _is_check(words: list[str]) -> bool:
    """Whether a stripped segment's runner is on the ruling's closed list."""
    if not words or words[0] in _SHELL_BUILTINS:
        return False
    words = _runner_words(words)
    return _is_named_runner(words) or _is_test_program(words)


def _reads_only(text: str, words: list[str]) -> bool:
    """Whether one segment is on the closed read-only list.

    A substituted command, a process substitution or a redirect into a file
    runs or writes something the list does not name (review, 2026-09-24).
    """
    if any(mark in text for mark in ("$(", "`", "<(", ">(")):
        return False
    if any(">" in word and not _HARMLESS_REDIRECT_RE.match(word) for word in words):
        return False
    writing = _WRITING_OPTIONS.get(words[0]) or _WRITING_OPTIONS.get(" ".join(words[:2]))
    if writing and writing & {w.split("=", 1)[0] for w in words[1:]}:
        return False
    return " ".join(words[:2]) in _READ_ONLY_PAIRS or words[0] in _READ_ONLY_WORDS


def _check_identity(directory: str, words: list[str]) -> str:
    """Item 4's "same check": the directory it ran in and its stripped segment,
    without redirects (review, 2026-09-24: the directory is part of it)."""
    return directory + "\0" + " ".join(word for word in words if not _REDIRECT_RE.match(word))


def _tool_result_blocks(transcript: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for record in transcript:
        if record.get("type") != "user" or record.get("isSidechain") is True:
            continue
        content = records.message_dict(record).get("content")
        for block in content if isinstance(content, list) else ():
            if isinstance(block, dict) and block.get("type") == "tool_result":
                call_id = block.get("tool_use_id")
                if isinstance(call_id, str) and call_id:
                    results[call_id] = block
    return results


def _claude_tool_uses(
    transcript: list[dict[str, Any]],
) -> Iterator[tuple[float, str, str, str, dict[str, Any]]]:
    """`(at, cwd, call id, tool name, input)` for the root session's calls;
    subagents are DRC-4687's."""
    for record in transcript:
        if record.get("type") != "assistant" or record.get("isSidechain") is True:
            continue
        content = records.message_dict(record).get("content")
        at = _record_timestamp(record)
        if not isinstance(content, list) or at is None:
            continue
        cwd = record.get("cwd")
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            call_id, name, tool_input = block.get("id"), block.get("name"), block.get("input")
            if isinstance(call_id, str) and isinstance(name, str) and isinstance(tool_input, dict):
                yield at, cwd if isinstance(cwd, str) else "", call_id, name, tool_input


def _tool_result_text(block: dict[str, Any]) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(part.get("text"))
            for part in content
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        )
    return ""


def _ran_nothing(tail: str) -> bool:
    return bool(_RAN_NOTHING.search(tail)) or (
        bool(_NO_TEST_FILES.search(tail)) and not _GO_OK.search(tail)
    )


def _tail_result(tail: str) -> tuple[str, str] | None:
    """Sources (ii) and (iii), failure first; a pass needs no failure beside it."""
    if _SUMMARY_FAILED.search(tail):
        return "failed", "summary"
    if _FAILURE_MARKER.search(tail):
        return "failed", "marker"
    if _SUMMARY_PASSED.search(tail) and not _ran_nothing(tail):
        return "passed", "summary"
    return None


def _flag_result(flag: object, *, last: bool, all_and: bool, alone: bool) -> str:
    """What the call's error flag says about one check in it (review and
    verifier, 2026-09-24).

    The flag is the whole call's status. A pass through `&&` alone passes every
    check, and a pass otherwise speaks for the last segment. A failure speaks
    only for a call of one segment, after `cd`, assignments and wrappers are
    stripped, since any other stage may be the one that failed.
    """
    if not isinstance(flag, bool):
        return ""
    if flag:
        return "failed" if alone else ""
    return "passed" if last or all_and else ""


def _check_line(words: list[str]) -> str:
    """The runner form and the rest of its own segment, masked, redacted, clipped.

    Its own segment only, never the rest of the shell line (owner, 2026-09-24).
    Each word is masked before the words are joined and re-quoted.
    """
    masked = records.mask_words(words)
    line = " ".join(shlex.quote(word) if re.search(r"\s", word) else word for word in masked)
    bounded = records.redact_clip(line, TOOL_REPORT_LINE_CHARS)
    return records.safe_text(bounded, len(bounded))


def _written_path(raw: object, cwd: str) -> str | None:
    """A written path relative to the working directory, or None outside it."""
    if not isinstance(raw, str) or not raw.strip() or not cwd:
        return None
    base = os.path.normpath(cwd)
    target = os.path.normpath(raw if os.path.isabs(raw) else os.path.join(base, raw))
    try:
        relative = os.path.relpath(target, base)
    except ValueError:
        return None
    if relative == os.curdir or relative.split(os.sep)[0] == os.pardir:
        return None
    return relative.replace(os.sep, "/")


def _is_fixer(words: list[str]) -> bool:
    """A formatter or fixer run: a change that ages every pass (verifier,
    2026-09-24), whether or not it is also a check."""
    if not words:
        return False
    words = _runner_words(words)
    flags = {word.split("=", 1)[0] for word in words[1:]}
    if _FIX_FLAGS & flags:
        return True
    if words[0] == "black" or words[:2] == ["ruff", "format"]:
        return "--check" not in flags
    return words[0] == "prettier" and "-w" in flags


class _ShellCall:
    """One Bash call, split into segments, with the facts every rule reads."""

    def __init__(
        self, at: float, cwd: str, tool_input: dict[str, Any], *, moved: bool = False
    ) -> None:
        command = tool_input.get("command")
        self.at = at
        self.segments = _command_segments(command if isinstance(command, str) else "")
        self.all_background = tool_input.get("run_in_background") is True or moved
        self.words: list[tuple[list[str], bool]] = [
            _stripped(_segment_words(text)) for text, _ in self.segments
        ]
        self.directories = self._directories(cwd)
        self.meaningful = [
            i for i, (words, _rtk) in enumerate(self.words) if words and words[0] != "cd"
        ]
        self.checks = [i for i in self.meaningful if _is_check(self.words[i][0])]
        self.fixers = [i for i in self.meaningful if _is_fixer(self.words[i][0])]
        self.changing_others = [
            i
            for i in self.meaningful
            if i not in self.checks and not _reads_only(self.segments[i][0], self.words[i][0])
        ]

    def _directories(self, cwd: str) -> list[str]:
        """The directory each segment runs in, following the call's `cd`s."""
        current, found = cwd, []
        for words, _rtk in self.words:
            found.append(current)
            if words[:1] == ["cd"] and len(words) > 1 and words[1] != "-":
                current = os.path.normpath(os.path.join(current or "/", words[1]))
        return found

    def background(self, index: int) -> bool:
        """`&` sends the whole and-or list before it to the background, back to
        the previous `;`, newline or `&` (verifier, 2026-09-24)."""
        if self.all_background:
            return True
        ends = (joiner for _, joiner in self.segments[index:] if joiner in ("", ";", "\n", "&"))
        return next(ends, "") == "&"

    def unestablished(self, index: int) -> bool:
        """Whether a `||` before the segment leaves its execution unknown."""
        return any(joiner == "||" for _, joiner in self.segments[:index])

    def changes(self) -> bool:
        """Whether any segment may change files without a recorded write."""
        return bool(self.fixers or self.changing_others)

    def launches(self) -> int:
        """Background launches: the call, or each `&`-ended list in it."""
        return 1 if self.all_background else sum(j == "&" for _, j in self.segments)


class _ToolReportTally:
    """The full scan of one transcript's calls, and the entries chosen from it."""

    def __init__(self, results: dict[str, dict[str, Any]]) -> None:
        self.results = results
        self.runs: dict[str, list[dict[str, Any]]] = {}
        self.writes: dict[str, dict[str, Any]] = {}
        self.last_write_at = float("-inf")
        # Order of the shell calls that ran, and which of them may change files,
        # for the press alone (`changed_after`); layer 1's fields are untouched.
        self.shell_seq = 0
        self.changing_seqs: list[int] = []
        self.scan: dict[str, Any] = {
            "last_changing_command_at": None,
            **dict.fromkeys(
                (
                    "shell_calls", "check_runs", "distinct_checks", "other_commands",
                    "read_only_commands", "background", "unknown_flags", "written_paths",
                    "outside_paths", "write_attempts", "not_run", "failed", "passed",
                    "not_recorded",
                    "listed", "more",
                ),
                0,
            ),
        }  # fmt: skip

    def add(self, at: float, cwd: str, call_id: str, name: str, tool_input: dict[str, Any]) -> None:
        if name in _WRITE_TOOLS:
            self._add_write(at, cwd, call_id, name, tool_input)
        elif name == "Bash":
            self._add_shell(at, cwd, call_id, tool_input)

    def _add_write(
        self, at: float, cwd: str, call_id: str, name: str, tool_input: dict[str, Any]
    ) -> None:
        result = self.results.get(call_id)
        if result is None or result.get("is_error") is True:
            # Not established as written (review, 2026-09-24): an attempt.
            self.scan["write_attempts"] += 1
            return
        # A written file ages every earlier pass wherever it is. Only the path is
        # read: never `content`, `old_string`, `new_string` or `edits`.
        self.last_write_at = max(self.last_write_at, at)
        path = _written_path(tool_input.get("file_path") or tool_input.get("notebook_path"), cwd)
        if path is None:
            self.scan["outside_paths"] += 1
            return
        self.writes[path] = {"at": at, "record_id": call_id, "tool": name}

    def _add_shell(self, at: float, cwd: str, call_id: str, tool_input: dict[str, Any]) -> None:
        result = self.results.get(call_id)
        text = _tool_result_text(result) if result is not None else ""
        if result is not None and result.get("is_error") is True and not _EXITED_RE.match(text):
            # V3: the call never ran, so it is no run and supersedes nothing.
            self.scan["not_run"] += 1
            return
        self.scan["shell_calls"] += 1
        self.shell_seq += 1
        call = _ShellCall(at, cwd, tool_input, moved=bool(_MOVED_TO_BACKGROUND_RE.match(text)))
        if call.changes():
            self.changing_seqs.append(self.shell_seq)
        if call.changes():
            self.scan["last_changing_command_at"] = at
        if call.fixers:
            self.last_write_at = max(self.last_write_at, at)
        self.scan["background"] += call.launches()
        foreground = [i for i in call.meaningful if not call.background(i)]
        if foreground and not [i for i in call.checks if i in foreground]:
            self.scan["other_commands"] += 1
            self.scan["read_only_commands"] += not call.changes()
        self._add_runs(call, call_id, result, text)

    def _add_runs(
        self, call: _ShellCall, call_id: str, result: dict[str, Any] | None, text: str
    ) -> None:
        flag = result.get("is_error") if result is not None else None
        # Redaction runs over the whole read window before the tail is cut (item 5).
        tail = records.redact_secrets(text)[-TOOL_REPORT_TAIL_CHARS:]
        all_and = all(joiner == "&&" for _, joiner in call.segments[:-1])
        # V8: output speaks for a check only when it is the call's one check,
        # background ones counted, and nothing else in the call may print.
        attributable = len(call.checks) == 1 and not call.changing_others
        for index in call.checks:
            words, rtk = call.words[index]
            background = call.background(index)
            if background:
                outcome, source = "not-recorded", ""
            else:
                self.scan["check_runs"] += 1
                if result is None or call.unestablished(index):
                    outcome, source = "not-recorded", ""
                else:
                    outcome, source = self._outcome(
                        tail,
                        rtk=rtk,
                        attributable=attributable,
                        flag_result=_flag_result(
                            flag,
                            last=index == len(call.segments) - 1,
                            all_and=all_and,
                            alone=len(call.meaningful) == 1,
                        ),
                    )
                self.scan["unknown_flags"] += (
                    result is not None and not isinstance(flag, bool) and outcome == "not-recorded"
                )
            self.runs.setdefault(_check_identity(call.directories[index], words), []).append(
                {
                    "at": call.at,
                    "record_id": call_id,
                    "title": _check_line(words),
                    "result": outcome,
                    "result_source": source,
                    "recorded": result is not None,
                    "background": background,
                    # Held for the press only (`claude_check_tails`); never
                    # copied onto the published entry.
                    "tail": tail if result is not None else "",
                    "seq": self.shell_seq,
                    "changes_later_in_call": any(
                        i > index for i in (*call.fixers, *call.changing_others)
                    ),
                    # V7: a fixer at or after this check in the call ages its pass.
                    "fixes": any(i >= index for i in call.fixers),
                }
            )

    @staticmethod
    def _outcome(tail: str, *, rtk: bool, attributable: bool, flag_result: str) -> tuple[str, str]:
        """By item 2's order, as the review rounds narrowed it: a result that
        cannot be attributed reads "ran, result not recorded"."""
        failed_summary = bool(_SUMMARY_FAILED.search(tail))
        failure_text = failed_summary or bool(_FAILURE_MARKER.search(tail))
        if rtk:
            # rtk may rewrite output, so its runs read the flag alone (owner),
            # and failure text beside a passing flag withholds it (V5).
            if flag_result == "passed" and failure_text:
                return "not-recorded", ""
            return (flag_result, "flag") if flag_result else ("not-recorded", "")
        if flag_result == "passed":
            # V4: only a failure summary overrides a passing flag; a marker, or
            # a run of nothing, only withholds it.
            if failed_summary:
                return ("failed", "summary") if attributable else ("not-recorded", "")
            if failure_text or _ran_nothing(tail):
                return "not-recorded", ""
        if flag_result:
            return flag_result, "flag"
        from_tail = _tail_result(tail) if attributable else None
        return from_tail if from_tail is not None else ("not-recorded", "")

    def _check_entry(self, history: list[dict[str, Any]]) -> dict[str, Any]:
        latest = history[-1]
        if latest["background"]:
            source = "Claude Bash call run in the background, no result recorded"
        elif latest["recorded"]:
            source = "Claude Bash call and paired result"
        else:
            source = "Claude Bash call, no result recorded yet"
        entry: dict[str, Any] = {
            "kind": "check_run",
            "subject": "check",
            "at": latest["at"],
            "record_id": latest["record_id"],
            "title": latest["title"],
            "result": latest["result"],
            "earlier_failed": any(run["result"] == "failed" for run in history[:-1]),
            "before_last_change": latest["result"] == "passed"
            and (latest["fixes"] or self.last_write_at > latest["at"]),
            # Whether a command that may change files followed this run, in its
            # own call or a later one, in command order: the press's
            # `changed_after`, published so the live level can block on it
            # (DRC-4692). Timestamps cannot order two segments of one call.
            "changed_after": self._changed_after(latest),
            "source": source,
            "rank": _RESULT_ORDER[latest["result"]],
        }
        if latest["result_source"]:
            entry["result_source"] = latest["result_source"]
        return entry

    def entries(self, sid: str) -> list[dict[str, Any]]:
        # A check that only ever ran in the background has no run to list
        # (item 1); a background re-run still supersedes an earlier result.
        histories = [h for h in self.runs.values() if not all(run["background"] for run in h)]
        candidates = [self._check_entry(history) for history in histories]
        for entry in candidates:
            self.scan[str(entry["result"]).replace("-", "_")] += 1
        candidates.extend(
            {
                "kind": "path_written",
                "subject": "write",
                "at": write["at"],
                "record_id": write["record_id"],
                "title": records.safe_text(path, TOOL_REPORT_PATH_CHARS),
                "source": f"Claude {write['tool']} call",
                "rank": len(_RESULT_ORDER),
            }
            for path, write in self.writes.items()
        )
        # Item 4: failed, then no recorded result, then passed, then written
        # paths, newest first within each. The page shows the kept ones in time
        # order (orchestrator, 2026-09-24).
        candidates.sort(key=lambda row: (row["rank"], -float(row["at"])))
        listed = candidates[:TOOL_REPORT_MAX_ENTRIES]
        self.scan.update(
            distinct_checks=len(histories),
            written_paths=len(self.writes),
            listed=len(listed),
            more=len(candidates) - len(listed),
        )
        return [
            {**{k: v for k, v in row.items() if k != "rank"}, "harness": "claude", "sid": sid}
            for row in listed
        ]

    def tails(self) -> dict[str, str]:
        """Each check's latest foreground run's redacted output tail, by call id."""
        latest = (history[-1] for history in self.runs.values())
        return {
            run["record_id"]: run["tail"] for run in latest if not run["background"] and run["tail"]
        }

    def _changed_after(self, run: dict[str, Any]) -> bool:
        return bool(run["changes_later_in_call"]) or any(
            seq > run["seq"] for seq in self.changing_seqs
        )

    def changed_after(self) -> frozenset[tuple[str, str]]:
        """(call id, check line) for each latest run a later command may have changed.

        In command order: a changing segment after the check in its own call,
        or any later call that ran and may change files. A change before the
        check, or a read-only command after it, does not count.
        """
        latest = (history[-1] for history in self.runs.values())
        return frozenset(
            (run["record_id"], run["title"]) for run in latest if self._changed_after(run)
        )


class PressChecks(NamedTuple):
    """What a press reads of a session's checks beyond the published facts."""

    tails: dict[str, str]
    changed_after: frozenset[tuple[str, str]]


def claude_check_press(
    config: RuntimeConfig, transcript_path: str, *, max_bytes: int | None = None
) -> PressChecks:
    """The output tails a press may carry to a model, and the passes a later
    command may have changed, both keyed by the call's record id.

    Read again at the press rather than published: the owner ruled that the
    model sees each check's redacted tail (DRC-4677, Q1), and it stays off the
    fact, the page and history, so only a reading the reader allowed tool
    output for ever holds it. The same scan and bounds as
    `claude_tool_reports`, so both belong to the run that fact lists.
    """
    transcript = _work_records(config, transcript_path, max_bytes=max_bytes)
    tally = _ToolReportTally(_tool_result_blocks(transcript))
    for call in _claude_tool_uses(transcript):
        tally.add(*call)
    return PressChecks(tally.tails(), tally.changed_after())


def claude_check_tails(
    config: RuntimeConfig, transcript_path: str, *, max_bytes: int | None = None
) -> dict[str, str]:
    """The output tails `claude_check_press` reads, alone."""
    return claude_check_press(config, transcript_path, max_bytes=max_bytes).tails


def press_checks(config: RuntimeConfig, state: RuntimeState, harness: str, sid: str) -> PressChecks:
    """`claude_check_press` for one session, found as `collect` finds it; empty elsewhere."""
    transcript_path = (
        observer.resolve_transcript(config, state, harness, sid) if harness == "claude" else None
    )
    if not transcript_path:
        return PressChecks({}, frozenset())
    return claude_check_press(config, transcript_path)


def claude_tool_reports(
    config: RuntimeConfig,
    transcript_path: str,
    sid: str,
    *,
    max_bytes: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The listed checks and written paths, and the full-scan counts behind them.

    Claude Code only, and published into the observed record only:
    [DEC-23](docs/design-reading-a-session.md#dec-23-a-claude-code-sessions-record-of-its-checks-may-show-the-work)
    """
    transcript = _work_records(config, transcript_path, max_bytes=max_bytes)
    tally = _ToolReportTally(_tool_result_blocks(transcript))
    for call in _claude_tool_uses(transcript):
        tally.add(*call)
    return tally.entries(sid), tally.scan


def _session_work_evidence(
    config: RuntimeConfig,
    transcript_path: str,
    identity: dict[str, str],
    events: list[dict[str, Any]],
    tool_report_scans: list[dict[str, Any]],
) -> dict[str, int]:
    """Pi's demonstrated results and Claude Code's checks, appended for `collect`.

    Not for the history source: `_semantic_history_source_events` calls
    `_work_evidence` alone, which is what keeps the checks out of the store.
    """
    harness, sid = identity["harness"], identity["sid"]
    rows, support = _work_evidence(config, transcript_path, harness, sid)
    events.extend(rows)
    if harness == "claude":
        report_rows, scan = claude_tool_reports(config, transcript_path, sid)
        events.extend(report_rows)
        tool_report_scans.append({**identity, **scan})
    return support


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
            if event["kind"]
            in {"prepared_dispatch", "task_started", "task_result", "outcome", *_TOOL_REPORT_KINDS}
        ),
    )


def _in_context(session: Mapping[str, Any]) -> bool:
    """Whether a row is inside the window the project context reads.

    `active` is the collector's window reading, but a hook's idle overlay
    overwrites it with False to mean "no turn running" (`events.reduce_overlays`),
    and the page's pulse and notify logic depend on that. A row the hooks stopped
    is still in the window: it is exactly the row a reader opens to see what the
    turn did, and reading it as out of the window dropped every check and file
    about three seconds after the stop (DRC-4705).
    """
    return session.get("active") is True or (
        session.get("acquisition") == "event" and session.get("state") == "idle"
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
        and _in_context(session)
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
        and _in_context(session)
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
    current = {
        key: records.safe_text(value, config.observer_block_cap_chars)
        for key, value in current.items()
    }
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
        if not _in_context(session) or session_project != project or (harness, sid) == focus:
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
    # `record_id` joined the hash on 2026-09-12 (DRC-4544 item 2), and only
    # when present. `_dedupe_project_events` already keys on it, so two events
    # differing in nothing else both survive as facts, and without it here
    # they shared one `fact_id`: the reading ledger then emitted two rows under
    # one citation handle and the page's `Map` kept whichever came last.
    # Appended conditionally so a fact with no record behind it keeps the id
    # it had. The ids of record-bearing facts moved once: a citation stored
    # before this to such a fact no longer resolves and the page demotes it to
    # UNCITED, and `semantic_history` dedupes on the id so those events are
    # recorded a second time. Accepted rather than migrated, per decisions.md;
    # no schema bump.
    record_id = source_event.get("record_id")
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
        *((record_id,) if record_id not in (None, "") else ()),
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
        "subject",
        "result",
        "result_source",
        "earlier_failed",
        "before_last_change",
        "changed_after",
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


# What an observer snapshot may claim about its own authorship. Read from the
# row's `goal_source` rather than assumed: the deterministic arm is the default
# and stamping every snapshot model-derived put a false claim in a durable store
# (DRC-4533). "unknown" is a sidecar written before the field existed, and it
# claims neither rather than defaulting to the one that is wrong more often.
_OBSERVER_ACTOR_CLAIMS = {
    "model": "model-derived observer snapshot",
    "deterministic": "deterministically derived observer snapshot",
}
_OBSERVER_ACTOR_CLAIM_UNKNOWN = "observer snapshot, derivation not recorded"


def _observer_actor_claim(goal_source: object) -> str:
    """What this snapshot may say about who derived it."""
    if isinstance(goal_source, str):
        return _OBSERVER_ACTOR_CLAIMS.get(goal_source, _OBSERVER_ACTOR_CLAIM_UNKNOWN)
    return _OBSERVER_ACTOR_CLAIM_UNKNOWN


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
            "actor_claim": _observer_actor_claim(observer_row.get("goal_source")),
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
    tool_report_scans: list[dict[str, Any]] = []
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
        work_support = _session_work_evidence(
            config, transcript_path, identity, events, tool_report_scans
        )
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
                # Per session, never on a row: every sentence the page writes
                # about checks reads these full-scan counts, as item 4 of the
                # ruling `claude_tool_reports` cites requires.
                "tool_reports": tool_report_scans,
                "unavailable": unavailable,
                "omitted": omitted_rows,
            },
        },
    }
