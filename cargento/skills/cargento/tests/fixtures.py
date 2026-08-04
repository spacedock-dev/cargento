from __future__ import annotations

import contextlib
import json
import os
import sqlite3
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


def protobuf_varint(value: int) -> bytes:
    encoded = bytearray()
    while value > 0x7F:
        encoded.append((value & 0x7F) | 0x80)
        value >>= 7
    encoded.append(value)
    return bytes(encoded)


def protobuf_bytes_field(number: int, value: bytes) -> bytes:
    return protobuf_varint((number << 3) | 2) + protobuf_varint(len(value)) + value


def protobuf_int_field(number: int, value: int) -> bytes:
    return protobuf_varint(number << 3) + protobuf_varint(value)


def write_antigravity_metadata(path: Path, blob: bytes) -> None:
    with contextlib.closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE trajectory_metadata_blob (id TEXT PRIMARY KEY, data BLOB)")
        connection.execute("INSERT INTO trajectory_metadata_blob VALUES ('main', ?)", (blob,))
        connection.commit()


STORE_CONSTANTS = (
    "PROJECTS_DIR",
    "TASKS_DIR",
    "CODEX_SESSIONS_DIR",
    "PI_SESSIONS_DIR",
    "GEMINI_TMP",
    "ANTIGRAVITY_CLI_DIR",
    "COPILOT_DIR",
    "OPENCODE_DATA",
    "CURSOR_CHATS",
    "GOOSE_DB",
    "FACTORY_PROJECTS",
)


def _iso(when: float) -> str:
    return datetime.fromtimestamp(when, tz=UTC).isoformat()


def _jsonl(path: Path, records: list[dict[str, Any]], when: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    os.utime(path, (when, when))


def _sqlite(path: Path, statements: list[tuple[str, tuple[Any, ...]]], when: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    try:
        for sql, params in statements:
            con.execute(sql, params)
        con.commit()
    finally:
        con.close()
    os.utime(path, (when, when))


def build_claude(root: Path, when: float, sid: str, title: str) -> dict[str, str]:
    projects = root / "projects"
    _jsonl(
        projects / "-w-proj" / f"{sid}.jsonl",
        [
            {"type": "user", "uuid": "u1", "timestamp": _iso(when), "message": {"content": title}},
            {
                "type": "assistant",
                "timestamp": _iso(when),
                "message": {"usage": {"output_tokens": 10}, "content": []},
            },
        ],
        when,
    )
    return {"PROJECTS_DIR": str(projects), "TASKS_DIR": str(root / "tasks")}


def build_codex(root: Path, when: float, sid: str, title: str) -> dict[str, str]:
    _jsonl(
        root / "2024" / "01" / "02" / "rollout-1.jsonl",
        [
            {
                "type": "session_meta",
                "timestamp": _iso(when),
                "payload": {"id": sid, "cwd": "/w/proj"},
            },
            {
                "type": "event_msg",
                "timestamp": _iso(when),
                "payload": {"type": "user_message", "message": title},
            },
        ],
        when,
    )
    return {"CODEX_SESSIONS_DIR": str(root)}


def build_pi(root: Path, when: float, sid: str, title: str) -> dict[str, str]:
    _jsonl(
        root / "--w-proj--" / f"2026-07-29_{sid}.jsonl",
        [
            {"type": "session", "version": 3, "id": sid, "timestamp": _iso(when), "cwd": "/w/proj"},
            {
                "type": "message",
                "id": "user0001",
                "parentId": None,
                "timestamp": _iso(when),
                "message": {"role": "user", "content": title, "timestamp": int(when * 1000)},
            },
        ],
        when,
    )
    return {"PI_SESSIONS_DIR": str(root)}


def build_gemini(root: Path, when: float, sid: str, title: str) -> dict[str, str]:
    _jsonl(
        root / "proj" / "chats" / f"session-{sid}.jsonl",
        [
            {"sessionId": sid, "kind": "main", "directories": ["/w/proj"]},
            {"type": "user", "timestamp": _iso(when), "content": title},
        ],
        when,
    )
    return {"GEMINI_TMP": str(root)}


def build_antigravity(root: Path, when: float, sid: str, title: str) -> dict[str, str]:
    conversations = root / "conversations"
    _sqlite(
        conversations / f"{sid}.db",
        [("CREATE TABLE steps (idx INTEGER, step_type INTEGER, metadata BLOB)", ())],
        when,
    )
    cache = root / "cache" / "last_conversations.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({f"/w/{title}": sid}), encoding="utf-8")
    (root / "log").mkdir(parents=True, exist_ok=True)
    # The collector derives conversations/, log/ and cache/ from the one root.
    return {"ANTIGRAVITY_CLI_DIR": str(root)}


def build_copilot(root: Path, when: float, sid: str, title: str) -> dict[str, str]:
    _jsonl(
        root / "session-state" / sid / "events.jsonl",
        [
            {
                "type": "session.start",
                "timestamp": _iso(when),
                "data": {"context": {"cwd": "/w/proj"}},
            },
            {"type": "user.message", "timestamp": _iso(when), "data": {"text": title}},
        ],
        when,
    )
    return {"COPILOT_DIR": str(root)}


def build_opencode(root: Path, when: float, sid: str, title: str) -> dict[str, str]:
    _sqlite(
        root / "opencode.db",
        [
            (
                "CREATE TABLE session (id TEXT, parent_id TEXT, directory TEXT, title TEXT, time_updated INTEGER, time_archived INTEGER)",
                (),
            ),
            (
                "INSERT INTO session VALUES (?, NULL, '/w/proj', ?, ?, NULL)",
                (sid, title, int(when * 1000)),
            ),
            (
                "CREATE TABLE session_message (session_id TEXT, type TEXT, time_created INTEGER, data TEXT)",
                (),
            ),
            (
                "INSERT INTO session_message VALUES (?, 'user', ?, ?)",
                (sid, int(when * 1000), json.dumps({"text": title})),
            ),
        ],
        when,
    )
    return {"OPENCODE_DATA": str(root)}


def build_cursor(root: Path, when: float, sid: str, title: str) -> dict[str, str]:
    _sqlite(
        root / "w" / sid / "store.db",
        [
            ("CREATE TABLE meta (value TEXT)", ()),
            ("INSERT INTO meta VALUES (?)", (json.dumps({"name": title}).encode().hex(),)),
        ],
        when,
    )
    return {"CURSOR_CHATS": str(root)}


def build_goose(root: Path, when: float, sid: str, title: str) -> dict[str, str]:
    stamp = datetime.fromtimestamp(when, tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
    database = root / "sessions.db"
    _sqlite(
        database,
        [
            (
                "CREATE TABLE sessions (id TEXT, description TEXT, working_dir TEXT, updated_at TEXT, session_type TEXT, parent_session_id TEXT, archived_at TEXT)",
                (),
            ),
            (
                "INSERT INTO sessions VALUES (?, ?, '/w/proj', ?, NULL, NULL, NULL)",
                (sid, title, stamp),
            ),
            (
                "CREATE TABLE messages (session_id TEXT, role TEXT, created_timestamp INTEGER, content_json TEXT)",
                (),
            ),
            (
                "CREATE TABLE usage_ledger (session_id TEXT, created_timestamp INTEGER, output_tokens INTEGER)",
                (),
            ),
        ],
        when,
    )
    return {"GOOSE_DB": str(database)}


def build_droid(root: Path, when: float, sid: str, title: str) -> dict[str, str]:
    _jsonl(
        root / "proj" / f"{sid}.jsonl",
        [
            {
                "type": "session_start",
                "id": sid,
                "sessionTitle": title,
                "cwd": "/w/proj",
                "timestamp": _iso(when),
            },
            {
                "type": "message",
                "timestamp": _iso(when),
                "message": {"role": "user", "content": title},
            },
        ],
        when,
    )
    return {"FACTORY_PROJECTS": str(root)}


# (harness key reported in /api/data, fixture builder)
HARNESSES: tuple[tuple[str, Any], ...] = (
    ("claude", build_claude),
    ("codex", build_codex),
    ("pi", build_pi),
    ("gemini", build_gemini),
    ("antigravity", build_antigravity),
    ("copilot", build_copilot),
    ("opencode", build_opencode),
    ("cursor", build_cursor),
    ("goose", build_goose),
    ("droid", build_droid),
)
