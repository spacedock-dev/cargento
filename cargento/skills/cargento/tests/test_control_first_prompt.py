"""A session that opened with a harness control drafts no goal, and says why (DRC-4766).

Measured 2026-10-01 over the local Claude Code store, counts only: 550 of 1,601 sessions open
with a harness-control record (`/clear` 326, `/login` 115), and the goal drafted from a
session's first prompt (item 2 of
[DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy))
offered the command as the reader's goal. The owner ruled that such a session drafts nothing
and says there is no first prompt to draft from, and that the draft never reaches for a later
record instead: the first-prompt read never does (SECURITY.md).

The transcripts are hand-written in the record shapes `test_slash_command_direction` documents,
with placeholder prose only.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

from cargento_runtime import annotations as annotation_store
from cargento_runtime import sessions as runtime_sessions
from cargento_runtime import transcripts

from .fixtures import _iso, _jsonl
from .support import HarnessContractTestCase, make_runtime
from .test_next_intent_draft import FIRST, LATEST, _DraftPage, intent_of, visible_text
from .test_slash_command_direction import CAVEAT, local_command, prompt_command

LATER = "Build the placeholder parser and test every token type"
WHY_CLEAR = "This session opened with /clear, so there is no first prompt to draft a goal from."


def _user(when: float, content: str, **extra: Any) -> dict[str, Any]:
    return {
        "type": "user",
        "timestamp": _iso(when),
        "message": {"role": "user", "content": content},
        **extra,
    }


def _control_records(when: float, name: str, args: str = "") -> list[dict[str, Any]]:
    """A local command as Claude Code records it: the caveat, the command, its output."""
    return [
        _user(when, CAVEAT, isMeta=True),
        _user(when + 1, local_command(name, args)),
        _user(when + 2, "<local-command-stdout></local-command-stdout>"),
    ]


def _store(opening: list[dict[str, Any]]) -> Any:
    """A collector store builder whose transcript opens with `opening`, then real work."""

    def build(root: Path, when: float, sid: str, _title: str) -> dict[str, str]:
        projects = root / "projects"
        _jsonl(
            projects / "-w-proj" / f"{sid}.jsonl",
            [
                *opening,
                _user(when + 10, LATER),
                {
                    "type": "assistant",
                    "timestamp": _iso(when + 11),
                    "message": {"usage": {"output_tokens": 10}, "content": []},
                },
            ],
            when + 11,
        )
        return {"PROJECTS_DIR": str(projects), "TASKS_DIR": str(root / "tasks")}

    return build


class TheCollectorPublishesAControlFirstPromptTest(HarnessContractTestCase):
    def row(self, opening: list[dict[str, Any]]) -> dict[str, Any]:
        (row,) = self.sessions_for(self.collect(_store(opening), when=self.NOW), "claude")
        return row

    def test_a_session_opened_with_clear_publishes_the_control_and_says_it_is_one(self) -> None:
        row = self.row(_control_records(self.NOW - 100, "clear"))
        self.assertIs(True, row["first_prompt_control"])
        # The first record stays the first prompt, as session history keeps it: the
        # control is what was typed first, and the later prompt is never read for it.
        self.assertEqual("/clear", row["first_prompt"])
        self.assertNotEqual(LATER, row["first_prompt"])

    def test_a_control_with_arguments_is_still_a_control(self) -> None:
        row = self.row(_control_records(self.NOW - 100, "compact", "keep the parser notes"))
        self.assertIs(True, row["first_prompt_control"])

    def test_a_skill_or_plain_first_prompt_is_not_a_control(self) -> None:
        skill = [_user(self.NOW - 100, prompt_command("review"))]
        plain = [_user(self.NOW - 100, "Add retry with backoff to the webhook handler.")]
        for name, opening in (("skill", skill), ("plain", plain)):
            with self.subTest(opening=name):
                self.assertIs(False, self.row(opening)["first_prompt_control"])

    def test_the_absent_value_is_not_a_control(self) -> None:
        self.assertIs(
            False, runtime_sessions.base_session("claude", "s", "p")["first_prompt_control"]
        )


class TheFirstPromptReadStopsAtTheControlTest(unittest.TestCase):
    def test_the_read_never_moves_past_a_control_to_a_later_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            config, state = make_runtime()
            path = Path(home, "claude.jsonl")
            rows = [*_control_records(1780019200.0, "login"), _user(1780019210.0, LATER)]
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
            result = transcripts.first_prompt(config, state, str(path), "claude")
        self.assertEqual(
            {
                "first_prompt": "/login",
                "first_prompt_at": 1780019201.0,
                "first_prompt_control": True,
            },
            result,
        )


class AControlIsNeverAdoptedAsTheFirstPromptTest(unittest.TestCase):
    def test_the_server_refuses_to_adopt_a_control_first_prompt(self) -> None:
        row = {
            "harness": "claude",
            "first_prompt": "/clear",
            "first_prompt_at": 10.0,
            "first_prompt_control": True,
        }
        self.assertEqual(("", None), annotation_store.prompt_candidate(row, "first-prompt"))
        row["first_prompt_control"] = False
        self.assertEqual(("/clear", 10.0), annotation_store.prompt_candidate(row, "first-prompt"))


CONTROL = '__s.first_prompt = "/clear"; __s.first_prompt_control = true;\n'


@unittest.skipUnless(shutil.which("node"), "node not available")
class ThePageDraftsNoGoalOverAControlTest(_DraftPage):
    def goal_box(self, intent: str) -> str:
        box = re.search(r'<textarea[^>]*data-next-cockpit-held-kind="goal"[^>]*>([^<]*)<', intent)
        assert box is not None
        return box.group(1)

    def test_a_control_first_session_drafts_nothing_and_says_why(self) -> None:
        intent = intent_of(self.html(CONTROL))
        text = visible_text(intent)
        self.assertEqual("", self.goal_box(intent))
        self.assertIn(WHY_CLEAR, text)
        self.assertNotIn("data-next-cockpit-drafted", intent)
        self.assertNotIn("Looks right", text)
        self.assertNotIn("from your prompt", text)

    def test_the_latest_prompt_is_not_drafted_in_its_place(self) -> None:
        intent = intent_of(self.html(CONTROL))
        self.assertNotIn(LATEST, self.goal_box(intent))

    def test_the_why_names_the_command_and_not_its_arguments(self) -> None:
        setup = (
            '__s.first_prompt = "/compact keep the parser notes";'
            " __s.first_prompt_control = true;\n"
        )
        text = visible_text(intent_of(self.html(setup)))
        self.assertIn("This session opened with /compact, so there is no first prompt", text)
        self.assertNotIn("keep the parser notes", text)

    def test_a_typed_goal_needs_no_why(self) -> None:
        setup = (
            CONTROL + '__s.annotation_goal = "Ship the retry queue"; __s.annotation_revision = 1;\n'
        )
        self.assertNotIn("no first prompt to draft", visible_text(intent_of(self.html(setup))))

    def test_a_first_prompt_that_is_no_control_still_drafts(self) -> None:
        intent = intent_of(self.html("__s.first_prompt_control = false;\n"))
        self.assertEqual(FIRST, self.goal_box(intent))
        self.assertNotIn("no first prompt to draft", visible_text(intent))

    def test_the_sessions_goal_cell_names_no_prompt_over_a_control(self) -> None:
        out = self.drive(
            CONTROL,
            'navigateNext({view:"sessions"});\nawait __settle();\n'
            "console.log(JSON.stringify(__els.app.innerHTML));",
        )
        assert isinstance(out, str)
        cell = re.search(r'data-next-operation-fact="goal">([\s\S]*?)</span>', out)
        assert cell is not None
        text = visible_text(cell.group(1))
        self.assertIn("Add a goal", text)
        self.assertNotIn("/clear", text)
        self.assertNotIn(LATEST, text)
