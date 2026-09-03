#!/usr/bin/env python3
"""Record the two stores a dispatched Claude teammate lives in, as shape only.

DRC-4344 rests on two measurements that cannot be looked up: where a top-level
transcript's first timestamped record actually sits, and which member fields the
teams registry carries on this harness build. Both come off real stores, so both
need a recorder rather than an assertion.

It is committed rather than kept as a one-off because one of the values it
writes is a digest. A reader who cannot see the derivation cannot tell a salted
hash from a raw identifier, and `docs/captures/README.md` promises the former.

Two modes:

    registry  the store shapes: member field names and their types, the
              transcript header field names and types, the record kinds each
              transcript opens with, and the index of the first record carrying
              a timestamp
    drive     the arms of a live board drive, reduced to arity and verdicts,
              from `/api/data` payloads saved to disk

**What it will not write.** Field NAMES, type names, closed harness vocabularies
and counts. Never a field's value, with the single exception of a closed
vocabulary token (`backendType`, a record `type`), which is the class
`docs/captures/README.md` already admits for `tool` and `notification_type`. The
registry's `prompt` field is operator text: it is recorded by name and never by
value. No agent label of any kind is recorded from a drive payload, because every
label on that board is either a workflow-generated identifier or a description a
person wrote.

`tests/test_documentation.py` holds both files to that, keys included.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from typing import Any

FORMAT = 2
SALT = "drc-4344:"
# Enough to place a store without naming it, and short enough that the value is
# plainly a digest rather than an identifier that happens to be hex.
DIGEST_CHARS = 12
# The head of a transcript is all this needs: the control records come first and
# the first stamp was measured at index 3 and 6.
HEADER_RECORDS = 12


# `bool` before `int` deliberately: `isinstance(True, int)` is true in Python,
# and every liveness flag in these stores would otherwise record as an int.
_TYPE_NAMES: tuple[tuple[type, str], ...] = (
    (bool, "bool"),
    (int, "int"),
    (float, "float"),
    (str, "string"),
    (list, "list"),
    (dict, "object"),
)


def type_name(value: object) -> str:
    """The JSON type of a value, as a name. The value itself is never returned."""
    if value is None:
        return "null"
    for kind, name in _TYPE_NAMES:
        if isinstance(value, kind):
            return name
    return "unknown"


def salted(text: str) -> str:
    """A store path reduced to a digest, so records group without naming it."""
    return hashlib.sha256((SALT + text).encode()).hexdigest()[:DIGEST_CHARS]


def harness_version() -> str:
    try:
        done = subprocess.run(
            # Resolved on PATH by design: the recorder asks the harness that wrote
            # the stores which version it is.
            ["claude", "--version"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    first = done.stdout.strip().split()
    return first[0] if first else "unknown"


def envelope(version: str) -> dict[str, Any]:
    return {
        "format": FORMAT,
        "harness": "claude",
        "os": platform.system().lower(),
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "claude_version": version,
    }


def registry_shape(path: str, base: dict[str, Any]) -> dict[str, Any]:
    """One registry's field names, their types, and the liveness flag per member."""
    with open(path, encoding="utf-8") as handle:
        registry = json.load(handle)
    fields: dict[str, set[str]] = {}
    members: list[dict[str, Any]] = []
    for member in registry.get("members") or ():
        if not isinstance(member, dict):
            continue
        for key, value in member.items():
            fields.setdefault(key, set()).add(type_name(value))
        flag = member.get("isActive")
        backend = member.get("backendType")
        members.append(
            {
                # A closed vocabulary. The member's name is not recorded at all.
                "backendType": backend if isinstance(backend, str) else None,
                "isActive_present": "isActive" in member,
                "isActive": flag if isinstance(flag, bool) else None,
                "joinedAt_type": type_name(member.get("joinedAt")),
            }
        )
    return {
        **base,
        "record": "team_registry_shape",
        "registry": salted(path),
        "registry_mtime_age_days": round((time.time() - os.path.getmtime(path)) / 86400, 1),
        "top_level_keys": sorted(key for key in registry if isinstance(key, str)),
        "member_fields": {key: sorted(value) for key, value in sorted(fields.items())},
        "member_count": len(members),
        "members": members,
    }


def header_shape(path: str) -> dict[str, Any]:
    """A transcript's opening record kinds, its field names, and the first stamp."""
    kinds: list[str | None] = []
    first_stamped: int | None = None
    fields: dict[str, set[str]] = {}
    with open(path, "rb") as source:
        for index, line in enumerate(source):
            if index >= HEADER_RECORDS:
                break
            try:
                record = json.loads(line)
            except ValueError:
                kinds.append(None)
                continue
            if not isinstance(record, dict):
                kinds.append(None)
                continue
            kind = record.get("type")
            kinds.append(kind if isinstance(kind, str) else None)
            for key, value in record.items():
                fields.setdefault(key, set()).add(type_name(value))
            if first_stamped is None and isinstance(record.get("timestamp"), str):
                first_stamped = index
    return {
        "record_types_in_order": kinds,
        "first_timestamped_record_index": first_stamped,
        "header_fields": {key: sorted(value) for key, value in sorted(fields.items())},
    }


def top_level_transcripts(projects: str, limit: int) -> list[str]:
    found = [
        path
        for path in glob.glob(os.path.join(projects, "*", "*.jsonl"))
        if "-agent-" not in os.path.basename(path)
        and not os.path.basename(path).startswith("agent-")
    ]
    return sorted(found, key=os.path.getmtime, reverse=True)[:limit]


def legacy_transcripts(projects: str, limit: int) -> list[str]:
    found = glob.glob(os.path.join(projects, "*", "*", "subagents", "agent-*.jsonl"))
    return sorted(found, key=os.path.getmtime, reverse=True)[:limit]


def layout_records(layout: str, paths: list[str], base: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    indexes: list[int | None] = []
    for path in paths:
        shape = header_shape(path)
        indexes.append(shape["first_timestamped_record_index"])
        out.append(
            {
                **base,
                "record": "transcript_header_shape",
                "layout": layout,
                # Eight characters, the allowance `docs/captures/README.md` states.
                "session": os.path.basename(path)[:8],
                **shape,
            }
        )
    zeroes = sum(1 for index in indexes if index == 0)
    out.append(
        {
            **base,
            "record": "first_timestamp_index_verdict",
            "layout": layout,
            "files": len(paths),
            "first_timestamped_record_index_per_file": indexes,
            "reads_at_index_zero": zeroes,
            "verdict": (
                "a one-line read finds the start stamp"
                if indexes and zeroes == len(indexes)
                else "a one-line read misses the start stamp"
            ),
        }
    )
    return out


def drift_record(
    shapes: list[dict[str, Any]], base: dict[str, Any], read: tuple[str, ...]
) -> dict[str, Any]:
    """What the newest registry adds over the oldest, and which of it is read."""
    oldest = set(shapes[0]["member_fields"])
    newest = set(shapes[-1]["member_fields"])
    return {
        **base,
        "record": "registry_field_drift",
        "older_registry_fields": sorted(oldest),
        "newer_registry_fields": sorted(newest),
        "added": sorted(newest - oldest),
        "removed": sorted(oldest - newest),
        "added_fields_the_runtime_reads": sorted(read),
        # `prompt` lands here, by name. Its value is operator text and is never
        # recorded anywhere in this file.
        "added_fields_deliberately_unread": sorted((newest - oldest) - set(read)),
    }


def record_registry(home: str, base: dict[str, Any]) -> list[dict[str, Any]]:
    registries = sorted(
        glob.glob(os.path.join(home, ".claude", "teams", "*", "config.json")),
        key=os.path.getmtime,
    )
    shapes = [registry_shape(path, base) for path in registries]
    out: list[dict[str, Any]] = list(shapes)
    if len(shapes) >= 2:
        out.append(drift_record(shapes, base, ("isActive",)))
    projects = os.path.join(home, ".claude", "projects")
    out += layout_records("top_level", top_level_transcripts(projects, 8), base)
    out += layout_records("legacy_subagents", legacy_transcripts(projects, 4), base)
    return out


def drive_arm(payload_path: str, arm: str, lead: str, base: dict[str, Any]) -> dict[str, Any]:
    """One arm of a board drive, as arity. No label is read."""
    with open(payload_path, encoding="utf-8") as handle:
        payload = json.load(handle)
    row = next(
        session
        for session in payload["sessions"]
        if session.get("harness") == "claude" and str(session.get("sid", "")).startswith(lead)
    )
    published = row.get("subagents") or []
    children = [entry for entry in published if entry.get("parent") is None]
    workers = [entry for entry in published if entry.get("parent") is not None]
    detail = str(row.get("state_detail") or "")
    return {
        **base,
        "record": "board_drive_arm",
        "arm": arm,
        "lead": lead,
        # One key set across every element, or the always-present rule is broken.
        "element_key_sets": sorted(sorted(entry) for entry in published),
        "element_keys_uniform": len({tuple(sorted(entry)) for entry in published}) <= 1,
        "published_total": len(published),
        "published_with_a_measured_start": sum(
            1 for entry in published if isinstance(entry.get("started_at"), (int, float))
        ),
        "published_with_a_null_start": sum(
            1 for entry in published if entry.get("started_at") is None
        ),
        "direct_children": len(children),
        "grandchildren": len(workers),
        "grandchildren_active": sum(1 for entry in workers if entry.get("active") is True),
        # A count of distinct parents, never the parents themselves.
        "distinct_parents_named": len({entry["parent"] for entry in workers}),
        "active_true": sum(1 for entry in published if entry.get("active") is True),
        "active_false": sum(1 for entry in published if entry.get("active") is False),
        "active_null": sum(1 for entry in published if entry.get("active") is None),
        "state": row.get("state"),
        "state_detail_shape": (
            "running N subagents"
            if detail.startswith("running ") and "subagent" in detail
            else "other"
        ),
        "state_detail_subagent_count": next(
            (int(part) for part in detail.split() if part.isdigit()), None
        ),
        "chrome_running_subagents": sum(
            1
            for session in payload["sessions"]
            for entry in (session.get("subagents") or [])
            if entry.get("active") is not False
        ),
        "chrome_published_subagents": sum(
            len(session.get("subagents") or []) for session in payload["sessions"]
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)

    registry = sub.add_parser("registry", help="record the store shapes")
    registry.add_argument("--home", default=os.path.expanduser("~"))
    registry.add_argument("--out", required=True)

    drive = sub.add_parser("drive", help="record board-drive arms from saved payloads")
    drive.add_argument("--lead", required=True, help="the lead session's 8-character prefix")
    drive.add_argument("--out", required=True)
    drive.add_argument(
        "--arm",
        action="append",
        required=True,
        metavar="NAME=PAYLOAD",
        help="an arm name and the /api/data payload file recording it",
    )

    args = parser.parse_args(argv)
    base = envelope(harness_version())

    if args.mode == "registry":
        records = record_registry(args.home, base)
    else:
        records = []
        for spec in args.arm:
            name, _, path = spec.partition("=")
            if not name or not path:
                parser.error(f"--arm expects NAME=PAYLOAD, got {spec!r}")
            records.append(drive_arm(path, name, args.lead, base))

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        handle.writelines(json.dumps(record, sort_keys=True) + "\n" for record in records)
    print(f"wrote {len(records)} records to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
