#!/usr/bin/env python3
"""Make the few illustration edits the sample session needs, after it has been anonymized.

The sample is a real session, anonymized by `scripts/sanitize_session.py`. One thing in the real
record hides what Compass is meant to show: the agent piped its test commands through `tail`, which
hides the exit status, so Compass rightly reads those checks as "ran, result not recorded". This
script records the two failing test runs the way Claude Code records any failed command (no pipe,
the error flag set, "Exit code 1" first in the output). Everything it changes is listed in the
edits file and in [sample-session/README.md](sample-session/README.md), so the sample never
claims to
be a byte-for-byte record.

    shape_sample_session.py --edits shaping.json --input in.jsonl --output out.jsonl

Each edit names a Bash command by a fragment it contains, a text replacement inside that command,
and the exit code to record. The script refuses an edit that matches nothing, so a re-run over a
changed session cannot silently do less than it says.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _result_text(block: dict[str, Any]) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return ""


def _tool_blocks(records: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Every content block in the file with the record that holds it."""
    found: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for record in records:
        content = (record.get("message") or {}).get("content")
        found.extend(
            (record, b)
            for b in (content if isinstance(content, list) else [])
            if isinstance(b, dict)
        )
    return found


def _rewrite_command(
    blocks: list[tuple[dict[str, Any], dict[str, Any]]], edit: dict[str, Any]
) -> str:
    """Apply one edit's text replacement to the single command it names; return that call's id."""
    fragment, (old, new) = edit["command_contains"], edit["replace"]
    named = [
        b
        for _, b in blocks
        if b.get("type") == "tool_use"
        and fragment in str((b.get("input") or {}).get("command", ""))
    ]
    if len(named) != 1:
        msg = f"edit for {fragment!r} matched {len(named)} commands, expected exactly one"
        raise SystemExit(msg)
    command = named[0]["input"]["command"]
    if old not in command:
        msg = f"edit for {fragment!r} found the command but not {old!r}"
        raise SystemExit(msg)
    named[0]["input"]["command"] = command.replace(old, new)
    return str(named[0]["id"])


def shape(records: list[dict[str, Any]], edits: list[dict[str, Any]]) -> list[str]:
    """Apply every edit in place; return one note per edit saying what changed."""
    notes: list[str] = []
    for edit in edits:
        blocks = _tool_blocks(records)
        call_id = _rewrite_command(blocks, edit)
        code = int(edit["exit_code"])
        if code:
            for record, block in blocks:
                if block.get("type") == "tool_result" and block.get("tool_use_id") == call_id:
                    text = f"Exit code {code}\n{_result_text(block)}"
                    block["content"] = text
                    block["is_error"] = True
                    record["toolUseResult"] = f"Error: {text}"
        notes.append(f"{edit['command_contains']}: recorded exit code {code}, pipe removed")
    return notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--edits", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    edits = json.loads(args.edits.read_text(encoding="utf-8"))["edits"]
    records = [
        json.loads(line)
        for line in args.input.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    notes = shape(records, edits)
    args.output.write_text(
        "".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in records),
        encoding="utf-8",
    )
    for note in notes:
        print(note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
