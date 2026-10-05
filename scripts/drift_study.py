"""Model-free, separate-cohort drift studies; loading a log grants no Analyze policy."""

from __future__ import annotations

import datetime as dt
import json
import math
import re
import sys
from collections import Counter, defaultdict
from itertools import pairwise
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

import levels_cases as lc

ACTIVE_GAP_SECONDS = 1800.0
PROOF_KINDS = ("person-correction", "failed-check", "retraction", "sibling-result")
GAP_CLASSES = ("defect", "status", "scope-or-plan", "communication", "none", "unclear")
_RUNTIME = Path(__file__).resolve().parents[1] / "cargento/skills/cargento"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))
from cargento_runtime.records import injected_prompt  # noqa: E402 - load the canonical filter


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
            if payload["role"] == "user" and injected_prompt(text, "codex"):
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
        if not _valid_case(case, ids, body["kind"]) or not _valid_mark(case, marks, body["kind"]):
            return False
        ids.add(case["id"])
    if set(marks) - ids:
        return False
    if body["kind"] == "gap-truth":
        return isinstance(body.get("exposures"), list) and all(
            isinstance(row, dict)
            and row.get("id") in ids
            and row.get("arm") in ("realistic", "adopted", "part", "current", "hindsight")
            for row in body["exposures"]
        )
    return isinstance(body.get("episodes"), list) and all(
        _valid_episode(episode, cases) for episode in body["episodes"]
    )


def _valid_mark(case: Mapping[str, Any], marks: Mapping[str, Any], kind: str) -> bool:
    mark = marks.get(case["id"])
    required = kind == "gap-truth" or "in-drift" in case.get("roles", ()) or case["id"] in marks
    if required and (
        not isinstance(mark, dict)
        or mark.get("gap") not in ("yes", "no", "unclear")
        or mark.get("class") not in GAP_CLASSES
    ):
        return False
    if not isinstance(mark, dict):
        return True
    if any(
        not isinstance(mark.get(field, []), list)
        for field in ("message_times", "relevant_causes", "proof")
    ):
        return False
    return all(
        _number(at) is not None and 0 < at <= case["cut"]
        for field in ("message_times", "relevant_causes")
        for at in mark.get(field) or ()
    ) and all(_valid_proof(proof, case["cut"]) for proof in mark.get("proof", []))


def _valid_proof(proof: Any, cut: float) -> bool:
    return (
        isinstance(proof, dict)
        and proof.get("kind") in PROOF_KINDS
        and _number(proof.get("at")) is not None
        and proof["at"] > cut
        and isinstance(proof.get("points_to_gap"), bool)
    )


def _valid_case(case: Any, ids: set[str], kind: str) -> bool:
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
    return kind != "in-drift" or (
        isinstance(case.get("session_key"), str)
        and re.fullmatch(r"[0-9a-f]{16}", case["session_key"]) is not None
        and isinstance(case.get("roles"), list)
        and bool(case["roles"])
        and all(role in ("in-drift", "outside-span") for role in case["roles"])
    )


def _valid_episode(episode: Any, cases: list[Any]) -> bool:
    if (
        not isinstance(episode, dict)
        or not isinstance(episode.get("id"), str)
        or not isinstance(episode.get("sid"), str)
        or not episode["sid"]
    ):
        return False
    if not re.fullmatch(r"[0-9a-f]{16}", episode["id"]):
        return False
    start, push = _number(episode.get("start")), _number(episode.get("push"))
    if start is None or push is None or start >= push:
        return False
    stops, events = episode.get("window_stops"), episode.get("active_events")
    if not isinstance(stops, list) or not isinstance(events, list):
        return False
    measured = {case["cut"] for case in cases if case["sid"] == episode.get("sid")}
    before = episode.get("before")
    return (
        (before is None or (_number(before) is not None and before < start and before in measured))
        and all(_number(at) is not None and start <= at < push and at in measured for at in stops)
        and len(set(stops)) == len(stops)
        and all(_number(at) is not None and start <= at <= push for at in events)
    )


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


def score_in_drift(body: Mapping[str, Any], live: Mapping[str, Any]) -> dict[str, Any]:
    """Raw counts by session and episode; annotation spans are not a false-alarm oracle."""
    rows: dict[str, dict[float, Mapping[str, Any]]] = defaultdict(dict)
    relevance: dict[str, dict[float, Sequence[float]]] = defaultdict(dict)
    outside: dict[str, Counter[str]] = defaultdict(Counter)
    classes: dict[str, Counter[str]] = defaultdict(Counter)
    refused = 0
    for case in body["cases"]:
        found = (live.get(case["id"]) or {}).get("arms", {}).get("realistic")
        if not isinstance(found, dict) or found.get("level") is None:
            refused += 1
            continue
        sid, cut = str(case["sid"]), float(case["cut"])
        rows[sid][cut] = found
        flagged = found["level"] in ("medium", "high", "extreme")
        mark = body["marks"].get(case["id"])
        if isinstance(mark, dict):
            classes[mark["class"]]["cuts"] += 1
            classes[mark["class"]]["flagged"] += int(flagged)
            if mark["gap"] == "yes":
                relevance[sid][cut] = mark.get("relevant_causes") or ()
        if "outside-span" in case["roles"]:
            outside[case["session_key"]]["cuts"] += 1
            outside[case["session_key"]]["flagged"] += int(flagged)
    episodes = []
    for episode in body["episodes"]:
        measured = rows[str(episode["sid"])]
        before = measured.get(float(episode["before"])) if episode.get("before") else None
        missing = before is None or any(float(at) not in measured for at in episode["window_stops"])
        caught = (
            None
            if missing
            else early_catch(
                episode,
                measured,
                baseline=(before or {}).get("cause_at"),
                relevant=relevance[str(episode["sid"])],
            )
        )
        public_catch = (
            None
            if caught is None
            else {
                "case": next(
                    case["id"]
                    for case in body["cases"]
                    if case["sid"] == episode["sid"] and case["cut"] == caught["cut"]
                ),
                "stops_before_pushback": caught["stops_before_pushback"],
                "active_minutes": caught["active_minutes"],
            }
        )
        episodes.append(
            {
                "id": episode["id"],
                "stops": len(episode["window_stops"]),
                "baseline_measured": before is not None,
                "window_measured": all(float(at) in measured for at in episode["window_stops"]),
                "early_catch": public_catch,
            }
        )
    return {
        "refused_cuts": refused,
        "outside_annotated_spans": dict(outside),
        "blind_gap_classes": dict(classes),
        "episodes": episodes,
        "early_catches": sum(row["early_catch"] is not None for row in episodes),
    }


def score_gap_truth(body: Mapping[str, Any]) -> dict[str, Any]:
    """Score the frozen question marks, preserving later-proof absences as uncertainty."""
    outcomes: dict[str, str] = {}
    for case in body["cases"]:
        mark = body["marks"][case["id"]]
        gap = mark["gap"]
        outcomes[case["id"]] = (
            ("positive" if positive_gap(mark, cut=case["cut"]) else "unproved-positive")
            if gap == "yes"
            else ("negative" if gap == "no" else "unclear")
        )
    arms: dict[str, Counter[str]] = defaultdict(Counter)
    for exposure in body["exposures"]:
        arms[exposure["arm"]][outcomes[exposure["id"]]] += 1
    return {
        "unique": dict(Counter(outcomes.values())),
        "arms": dict(arms),
        "items": [{"id": key, "outcome": value} for key, value in sorted(outcomes.items())],
    }


def score_study(home: Path, root: Path, tag: str) -> dict[str, Any]:
    """Write a count-only summary after the committed blind marks are verified."""
    body = load_study(home, root, tag)
    paths = study_paths(home, root, tag)
    if body["kind"] == "in-drift":
        live = json.loads(paths["live"].read_text(encoding="utf-8"))
        if live.get("study_digest") != lc.digest(body):
            msg = "Live output belongs to another study cohort"
            raise ValueError(msg)
        summary = score_in_drift(body, live["cases"])
    else:
        summary = score_gap_truth(body)
    result = {
        "v": 1,
        "kind": body["kind"],
        "markers": "agents",
        "marks_digest": lc.digest(body),
        **summary,
    }
    lc._write(str(paths["result"]), result)  # noqa: SLF001 - existing replay writer
    return result


def import_codex(
    home: Path, root: Path, tag: str, source: Path, mask: Callable[[str], str]
) -> dict[str, Any]:
    """Persist one genuinely annotated local parent case without changing Analyze admission."""
    paths = study_paths(home, root, tag)
    if paths["cohort"].exists() or paths["result"].exists():
        msg = "Codex study already exists; annotation is closed"
        raise ValueError(msg)
    spec = json.loads(source.read_text(encoding="utf-8"))
    annotation = spec["annotation"]
    key = annotation.get("id")
    if not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{16}", key):
        msg = "Codex annotation requires a salted case key"
        raise ValueError(msg)
    body = codex_messages(Path(spec["source"]))
    requested, correction = annotation.get("requested_at"), annotation.get("correction_at")
    gap_at = annotation.get("gap_at")
    times = {
        role: {m["at"] for m in body["messages"] if m["role"] == role} for role in ("you", "agent")
    }
    if (
        any(_number(at) is None for at in (requested, correction, gap_at))
        or not requested < gap_at < correction
        or requested not in times["you"]
        or correction not in times["you"]
        or gap_at not in times["agent"]
        or annotation.get("gap") != "yes"
        or annotation.get("class") not in GAP_CLASSES
    ):
        msg = "Annotation requires genuine dated request, agent gap and person correction"
        raise ValueError(msg)
    for message in body["messages"]:
        message["text"] = mask(message["text"])
    private = {**body, "annotation": _mask_value(annotation, mask)}
    summary = {
        "v": 1,
        "kind": "codex-annotation",
        "markers": "agents",
        "cases": 1,
        "id": key,
        "messages": len(body["messages"]),
        "injected_excluded": body["injected_excluded"],
        "qualifies_analyze": False,
        "annotation_digest": lc.digest(private),
    }
    lc._write(str(paths["cohort"]), private)  # noqa: SLF001
    lc._write(str(paths["result"]), summary)  # noqa: SLF001
    return summary


def _mask_value(value: Any, mask: Callable[[str], str]) -> Any:
    if isinstance(value, str):
        return mask(value)
    if isinstance(value, dict):
        return {key: _mask_value(item, mask) for key, item in value.items()}
    if isinstance(value, list):
        return [_mask_value(item, mask) for item in value]
    return value
