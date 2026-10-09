# ruff: noqa: INP001 -- standalone, test-only contributor fixture
"""Run the real CLI over synthetic Claude Code transcripts, for the Intent step's browser tests.

Nothing but the transcripts is synthetic. The collector, the project-context reader, the annotation
store, `/api/annotate`, `/api/direction` and `/api/annotations` are the real ones, so a browser
proof reads what a reader's page would. The transcripts live in the scratch tree the launcher points
every harness store at; no real store, model, clipboard, notification or terminal is read or called.

What the board holds, by design:

- `intent-1`: a session with two prompts and no saved words, so its goal box arrives drafted from
  the first prompt and its "Use your prompt" menu offers two prompts;
- `intent-2`: a session the reader saves words against. Once a goal is saved for it, two more person
  messages land in its transcript a moment later, which is what makes later directions the page can
  ask about, open whole and settle;
- `intent-4`: another session of the same kind, kept for tests that compare the two renderers over
  later directions without disturbing `intent-2`;
- `intent-3`: a session in a second project, which the Intent log lists beside the first.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "cargento/skills/cargento"))

from cargento_runtime import annotations as annotation_store  # noqa: E402
from cargento_runtime import cli  # noqa: E402

STARTED = time.time()

SESSIONS: dict[str, dict[str, Any]] = {
    "intent-1": {
        "cwd": "/w/alpha",
        "prompts": (
            "Fix the login redirect so a signed-in reader lands on their last page.",
            "Then add a regression test for the redirect.",
        ),
    },
    "intent-2": {"cwd": "/w/alpha", "prompts": ("Ship the queue worker behind a flag.",)},
    "intent-3": {"cwd": "/w/unlabelled", "prompts": ("Tidy the unlabelled project.",)},
    "intent-4": {"cwd": "/w/alpha", "prompts": ("Rename the worker's settings file.",)},
}
SAYS_MORE = ("intent-2", "intent-4")
LATERS = (
    "Keep the flag off by default and say so in the release note.",
    "Also write the rollback steps down before anything else is changed.",
)


def _stamp(when: float) -> str:
    return dt.datetime.fromtimestamp(when, tz=dt.UTC).isoformat().replace("+00:00", "Z")


def _record(sid: str, cwd: str, kind: str, text: str, when: float, index: int) -> dict[str, Any]:
    return {
        "type": kind,
        "uuid": f"{sid}-{index}",
        "parentUuid": f"{sid}-{index - 1}" if index else None,
        "isSidechain": False,
        "cwd": cwd,
        "sessionId": sid,
        "timestamp": _stamp(when),
        "message": {"role": kind, "content": [{"type": "text", "text": text}]},
    }


def _path(sid: str, cwd: str) -> Path:
    root = Path(os.environ["CLAUDE_CONFIG_DIR"]) / "projects" / cwd.replace("/", "-")
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{sid}.jsonl"


def write_transcripts() -> None:
    for sid, spec in SESSIONS.items():
        rows = []
        for index, prompt in enumerate(spec["prompts"]):
            rows.append(
                _record(sid, spec["cwd"], "user", prompt, STARTED - 600 + index * 120, 2 * index)
            )
            rows.append(
                _record(
                    sid,
                    spec["cwd"],
                    "assistant",
                    "Working on it.",
                    STARTED - 590 + index * 120,
                    2 * index + 1,
                )
            )
        path = _path(sid, spec["cwd"])
        path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def append_later(sid: str) -> None:
    spec = SESSIONS[sid]
    path = _path(sid, spec["cwd"])
    count = len(path.read_text(encoding="utf-8").splitlines())
    with path.open("a", encoding="utf-8") as handle:
        for index, words in enumerate(LATERS):
            row = _record(sid, spec["cwd"], "user", words, time.time() + 1 + index, count + index)
            handle.write(json.dumps(row) + "\n")


_ANNOTATE = annotation_store.annotate
_ADOPT = annotation_store.adopt
_APPENDED: set[str] = set()


def _say_more_once(sid: str) -> None:
    if sid in SAYS_MORE and sid not in _APPENDED:
        _APPENDED.add(sid)
        threading.Timer(0.6, append_later, args=(sid,)).start()


def annotate_then_say_more(config: Any, state: Any, harness: str, sid: str, **kwargs: Any) -> Any:
    outcome = _ANNOTATE(config, state, harness, sid, **kwargs)
    if kwargs.get("goal") and outcome == "stored":
        _say_more_once(sid)
    return outcome


def adopt_then_say_more(config: Any, state: Any, row: dict[str, Any], **kwargs: Any) -> Any:
    outcome = _ADOPT(config, state, row, **kwargs)
    if outcome == "stored":
        _say_more_once(str(row.get("sid")))
    return outcome


if __name__ == "__main__":
    write_transcripts()
    annotation_store.annotate = annotate_then_say_more
    annotation_store.adopt = adopt_then_say_more
    raise SystemExit(cli.main())
