"""Model-free, separate-cohort drift studies; loading a log grants no Analyze policy."""

from __future__ import annotations

import datetime as dt
import json
import math
import re
from itertools import pairwise
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

import levels_cases as lc

ACTIVE_GAP_SECONDS = 1800.0
PROOF_KINDS = ("person-correction", "failed-check", "retraction", "sibling-result")
GAP_CLASSES = ("defect", "status", "scope-or-plan", "communication", "none", "unclear")
INJECTED_PREFIXES = (
    "# AGENTS.md",
    "<environment_context>",
    "<skill_instructions>",
    "<instructions>",
    "<subagents>",
    "<team",
    "<daemon",
    "<base_instructions>",
    "Another Claude session sent a message:",
)


def _number(value: Any) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value):
        return float(value)
    return None


def active_minutes(events: Sequence[float], start: float, end: float) -> float:
    """Elapsed recorded time, with each idle gap capped at thirty minutes (F50)."""
    times = sorted({start, end, *(at for at in events if start <= at <= end)})
    return sum(min(right - left, ACTIVE_GAP_SECONDS) for left, right in pairwise(times)) / 60


def early_catch(
    episode: Mapping[str, Any],
    rows: Mapping[float, Mapping[str, Any]],
    *,
    baseline: Any,
    relevant: Mapping[float, Sequence[float]],
) -> dict[str, float | int] | None:
    """Credit only a measured new cause whose blind mark names that exact cause."""
    if baseline is not None and _number(baseline) is None:
        msg = "The baseline cause was not measured"
        raise ValueError(msg)
    start, push = float(episode["start"]), float(episode["push"])
    stops = sorted(float(at) for at in episode["window_stops"])
    for cut in stops:
        row = rows.get(cut) or {}
        cause = _number(row.get("cause_at"))
        if (
            row.get("level") not in ("medium", "high", "extreme")
            or cause is None
            or not start <= cause <= cut < push
            or cause == baseline
            or cause not in relevant.get(cut, ())
        ):
            continue
        return {
            "cut": cut,
            "stops_before_pushback": sum(cut < at < push for at in stops),
            "active_minutes": active_minutes(episode["active_events"], cut, push),
        }
    return None


def positive_gap(mark: Mapping[str, Any], *, cut: float) -> bool:
    """A positive per-question mark needs a later, specific recorded proof item (F49)."""
    return mark.get("gap") == "yes" and any(
        isinstance(proof, dict)
        and proof.get("kind") in PROOF_KINDS
        and proof.get("points_to_gap") is True
        and (at := _number(proof.get("at"))) is not None
        and at > cut
        for proof in mark.get("proof") or ()
    )


def codex_messages(path: Path) -> dict[str, Any]:
    """Load actual CLI/editor parent messages for a local study, never as runtime facts."""
    messages: list[dict[str, Any]] = []
    injected = 0
    meta: dict[str, Any] | None = None
    before = path.stat()
    with path.open(encoding="utf-8") as stream:
        for raw in stream:
            record = json.loads(raw)
            payload = record.get("payload") or {}
            if record.get("type") == "session_meta":
                if meta is not None:
                    msg = "Ambiguous parent metadata"
                    raise ValueError(msg)
                meta = payload
                if (
                    meta.get("source") not in ("cli", "vscode")
                    or meta.get("thread_source") != "user"
                    or meta.get("agent_path")
                    or meta.get("parent_thread_id")
                ):
                    msg = "Study requires an actual user parent, not an exec or worker"
                    raise ValueError(msg)
            if (
                record.get("type") != "response_item"
                or payload.get("type") != "message"
                or payload.get("role") not in ("user", "assistant")
            ):
                continue
            text = "\n".join(
                str(block.get("text") or "")
                for block in payload.get("content") or ()
                if isinstance(block, dict) and block.get("type") in ("input_text", "output_text")
            )
            if payload["role"] == "user" and text.lstrip().startswith(INJECTED_PREFIXES):
                injected += 1
                continue
            stamp = str(record.get("timestamp") or "")
            try:
                at = dt.datetime.fromisoformat(stamp).timestamp()
            except ValueError:
                continue
            if text.strip():
                messages.append(
                    {
                        "role": "you" if payload["role"] == "user" else "agent",
                        "at": at,
                        "text": text,
                    }
                )
    after = path.stat()
    if meta is None or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        msg = "Source absent or changed during study load"
        raise ValueError(msg)
    return {
        "harness": "codex",
        "qualifies_analyze": False,
        "messages": messages,
        "injected_excluded": injected,
    }


def study_paths(home: Path, root: Path, tag: str) -> dict[str, Path]:
    """Study names cannot select or overwrite the historical replay stores."""
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,25}", tag):
        msg = "A study requires a safe nonempty tag of at most 26 characters"
        raise ValueError(msg)
    base = home / "drift-replay"
    return {
        "cohort": base / f"study-{tag}.json",
        "live": base / f"live-study-{tag}.json",
        "digest": root / "docs/drift-replay" / f"study-{tag}-marks-digest.json",
        "result": root / "docs/drift-replay" / f"results-study-{tag}.json",
    }


def _valid_bundle(body: Mapping[str, Any]) -> bool:
    cases, marks = body.get("cases"), body.get("marks")
    if (
        body.get("kind") not in ("in-drift", "gap-truth")
        or body.get("source") != "fixtures"
        or not isinstance(cases, list)
        or not cases
        or not isinstance(marks, dict)
    ):
        return False
    ids: set[str] = set()
    for case in cases:
        if (
            not isinstance(case, dict)
            or not isinstance(case.get("id"), str)
            or not re.fullmatch(r"[0-9a-f]{16}", case["id"])
            or case["id"] in ids
            or not isinstance(case.get("sid"), str)
            or not case["sid"]
            or _number(case.get("cut")) is None
        ):
            return False
        ids.add(case["id"])
        mark = marks.get(case["id"])
        required = body["kind"] == "gap-truth" or "in-drift" in case.get("roles", ())
        if required and (
            not isinstance(mark, dict)
            or mark.get("gap") not in ("yes", "no", "unclear")
            or mark.get("class") not in GAP_CLASSES
        ):
            return False
        if isinstance(mark, dict) and any(
            _number(at) is None or not 0 < at <= case["cut"]
            for at in mark.get("message_times") or ()
        ):
            return False
    return not (set(marks) - ids)


def import_study(home: Path, root: Path, tag: str, source: Path) -> dict[str, Any]:
    """Close a private cohort before any study output; write only counts and its hash in Git."""
    paths = study_paths(home, root, tag)
    if paths["live"].exists() or paths["result"].exists():
        msg = "Study output already exists; marking is closed"
        raise ValueError(msg)
    body = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(body, dict) or not _valid_bundle(body):
        msg = "Study has missing or invalid cases or initial blind marks"
        raise ValueError(msg)
    frozen = {"v": 1, **body}
    summary = {
        "v": 1,
        "kind": body["kind"],
        "marks_digest": lc.digest(frozen),
        "cases": len(body["cases"]),
        "marked": len(body["marks"]),
        "markers": "agents",
    }
    for key, value in (("cohort", frozen), ("digest", summary)):
        lc._write(str(paths[key]), value)  # noqa: SLF001 - the replay's existing private writer
    return summary


def load_study(home: Path, root: Path, tag: str) -> dict[str, Any]:
    """Refuse to compute output until the exact cohort hash is committed in HEAD."""
    paths = study_paths(home, root, tag)
    body = json.loads(paths["cohort"].read_text(encoding="utf-8"))
    closed = lc.committed_digest(str(root), str(paths["digest"]))
    if isinstance(closed, str) or closed.marks_digest != lc.digest(body) or not _valid_bundle(body):
        msg = "Study marks are absent, changed, or not committed"
        raise ValueError(msg)
    return dict(body)
