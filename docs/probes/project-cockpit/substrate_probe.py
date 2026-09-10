# ruff: noqa: INP001 - standalone probe under a hyphenated artifact directory
"""Read-only project-cockpit substrate probe against a running Cargento.

The report carries structural evidence only. Project labels, session ids,
questions, options, goals, prompts, and transcript paths never leave memory.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNTIME_ROOT = REPO_ROOT / "cargento" / "skills" / "cargento"
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from cargento_runtime import cli, observer  # noqa: E402


def _fetch(port: int) -> dict[str, Any]:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/data",
        headers={"Host": f"127.0.0.1:{port}"},
    )
    try:
        with opener.open(request, timeout=5) as response:
            value = json.loads(response.read(4 << 20))
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read Cargento on port {port}: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise TypeError("Cargento returned a non-object payload")
    return value


def _token_map(values: list[str], prefix: str) -> dict[str, str]:
    return {value: f"{prefix}{index:02d}" for index, value in enumerate(sorted(set(values)), 1)}


def _project_evidence(payload: dict[str, Any], now: float) -> tuple[dict[str, Any], dict[str, str]]:
    rows = [row for row in payload.get("sessions", []) if isinstance(row, dict)]
    labels = [str(row.get("project") or "") for row in rows]
    labels = [label for label in labels if label]
    project_tokens = _token_map(labels, "p")
    groups = []
    for label, token in project_tokens.items():
        members = [row for row in rows if str(row.get("project") or "") == label]
        harnesses = sorted({str(row.get("harness") or "") for row in members})
        activity = [float(row.get("last_activity") or 0) for row in members]
        groups.append(
            {
                "project": token,
                "sessions": len(members),
                "active": sum(bool(row.get("active")) for row in members),
                "harnesses": harnesses,
                "newest_activity_age_sec": round(max(0.0, now - max(activity, default=0.0))),
            }
        )
    empty_labels = sum(not str(row.get("project") or "") for row in rows)
    duplicate_ids = len(rows) - len(
        {(str(row.get("harness") or ""), str(row.get("sid") or "")) for row in rows}
    )
    return (
        {
            "status": "observed" if groups else "unavailable",
            "source": "/api/data sessions[].project",
            "projects": groups,
            "project_count": len(groups),
            "empty_project_labels": empty_labels,
            "session_identity_collisions": duplicate_ids,
            "identity_note": "project is a display label; session identity is (harness, sid)",
        },
        project_tokens,
    )


def _session_evidence(
    payload: dict[str, Any], now: float
) -> tuple[dict[str, Any], dict[tuple[str, str], str]]:
    rows = [row for row in payload.get("sessions", []) if isinstance(row, dict)]
    keys = [(str(row.get("harness") or ""), str(row.get("sid") or "")) for row in rows]
    session_tokens = {key: f"s{index:02d}" for index, key in enumerate(sorted(set(keys)), 1)}
    active = [row for row in rows if bool(row.get("active"))]
    states: dict[str, int] = {}
    for row in active:
        state = str(row.get("state") or "unknown")
        states[state] = states.get(state, 0) + 1
    activity = [float(row.get("last_activity") or 0) for row in active]
    return (
        {
            "status": "observed" if rows else "unavailable",
            "source": "/api/data sessions[]",
            "rows": len(rows),
            "active": len(active),
            "active_states": dict(sorted(states.items())),
            "newest_active_age_sec": round(max(0.0, now - max(activity, default=0.0))),
            "oldest_active_age_sec": round(max(0.0, now - min(activity, default=now))),
            "identity": "(harness, sid); display session id is non-authoritative",
        },
        session_tokens,
    )


def _ask_evidence(
    payload: dict[str, Any],
    project_tokens: dict[str, str],
    session_tokens: dict[tuple[str, str], str],
) -> dict[str, Any]:
    capability = payload.get("ask") is True
    asks = [ask for ask in payload.get("asks", []) if isinstance(ask, dict)] if capability else []
    entries = []
    for ask in asks:
        key = (str(ask.get("harness") or ""), str(ask.get("session_id") or ""))
        entries.append(
            {
                "project": project_tokens.get(str(ask.get("project") or ""), "unmapped"),
                "session": session_tokens.get(key, "unmatched"),
                "age_sec": ask.get("age_sec") if isinstance(ask.get("age_sec"), int) else None,
                "option_count": len(ask.get("options", []))
                if isinstance(ask.get("options"), list)
                else 0,
            }
        )
    return {
        "status": "observed_nonempty"
        if asks
        else ("observed_empty" if capability else "unavailable"),
        "source": "running process AskRegistry via /api/data asks[]",
        "capability": capability,
        "count": len(asks),
        "entries": entries,
        "persistence": "process memory only; registration supplies project and session labels",
    }


def _runtime(port: int) -> tuple[Any, Any]:
    parser = cli.build_parser()
    args = parser.parse_args(
        ["--port", str(port), "--window-hours", "168", "--no-usage", "--no-events"]
    )
    return cli.build_runtime(args, started=time.time())


def _observer_evidence(
    payload: dict[str, Any],
    session_tokens: dict[tuple[str, str], str],
    port: int,
    now: float,
) -> dict[str, Any]:
    config, state = _runtime(port)
    candidates = [
        row
        for row in payload.get("sessions", [])
        if isinstance(row, dict) and row.get("harness") in {"claude", "pi"}
    ]
    candidates.sort(key=lambda row: float(row.get("last_activity") or 0), reverse=True)
    for row in candidates:
        harness, sid = str(row.get("harness") or ""), str(row.get("sid") or "")
        transcript = observer.resolve_transcript(config, state, harness, sid)
        if transcript is None:
            continue
        entity_dir = observer.resolve_entity_dir(config, state, transcript)
        result = observer.analyze(config, state, transcript, entity_dir=entity_dir)
        goal = str(result.get("goal") or "")
        return {
            "status": "observed",
            "source": "real local transcript through observer.analyze; model callers disabled",
            "session": session_tokens.get((harness, sid), "unmatched"),
            "harness": harness,
            "transcript_age_sec": round(max(0.0, now - os.path.getmtime(transcript))),
            "goal_state": "sentinel" if goal == observer.NO_GOAL else "deterministic",
            "memory_available": bool(result.get("memory")),
            "stage_available": bool(result.get("stage")),
            "block_available": bool(result.get("block")),
            "entity_mapping_available": entity_dir is not None,
            "persistence": "probe is read-only; /api/observe would write a session sidecar",
        }
    return {
        "status": "unavailable",
        "source": "observer.resolve_transcript found no readable Claude or Pi transcript",
        "candidate_sessions": len(candidates),
    }


def _browser_goal_evidence() -> dict[str, Any]:
    web = RUNTIME_ROOT / "cargento_runtime" / "web"
    scripts = "\n".join(path.read_text(encoding="utf-8") for path in sorted(web.glob("*.js")))
    declared = sorted(set(re.findall(r'const\s+[A-Z0-9_]*KEY\s*=\s*"([^"]+)"', scripts)))
    project_goal_keys = [value for value in declared if "goal" in value.lower()]
    return {
        "status": "unavailable" if not project_goal_keys else "declared_unexercised",
        "source": "shipped browser JavaScript localStorage declarations",
        "declared_keys": declared,
        "project_goal_keys": project_goal_keys,
        "failure": "no shipped project-goal storage key, schema, writer, or conflict rule",
        "trust_boundary": "browser origin; server cannot read localStorage",
    }


def probe(port: int) -> dict[str, Any]:
    now = time.time()
    payload = _fetch(port)
    project_evidence, project_tokens = _project_evidence(payload, now)
    session_evidence, session_tokens = _session_evidence(payload, now)
    generated = float(payload.get("generated") or 0)
    return {
        "schema": 1,
        "measured_at": round(now),
        "dashboard": {
            "port": port,
            "snapshot_age_sec": round(max(0.0, now - generated)),
            "capabilities": sorted(key for key in ("ask", "dismiss", "usage") if key in payload),
            "harness_errors": {
                str(item.get("key")): str(item.get("error"))
                for item in payload.get("harnesses", [])
                if isinstance(item, dict) and item.get("error")
            },
        },
        "project_grouping": project_evidence,
        "active_sessions": session_evidence,
        "outstanding_asks": _ask_evidence(payload, project_tokens, session_tokens),
        "observer_output": _observer_evidence(payload, session_tokens, port, now),
        "browser_project_goal": _browser_goal_evidence(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=4553)
    args = parser.parse_args()
    try:
        result = probe(args.port)
    except (RuntimeError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
