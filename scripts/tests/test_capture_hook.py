"""The capture hook: it records shape, and it must never record content."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import capture_hook


class ShapeTest(unittest.TestCase):
    """A capture line carries what happened, never what was said."""

    # Not a credential: a canary string asserted absent from every capture.
    SECRET = "the-user-said-something-private"  # noqa: S105

    def _payload(self) -> dict[str, object]:
        return {
            "hook_event_name": "PreToolUse",
            "session_id": "9f3c1a2e-7b44-4d1e-9999-000000000000",
            "transcript_path": f"/Users/someone/.claude/projects/x/{self.SECRET}.jsonl",
            "cwd": f"/Users/someone/work/{self.SECRET}",
            "tool_name": "Bash",
            "tool_input": {"command": f"echo {self.SECRET}"},
            "prompt": self.SECRET,
            "message": self.SECRET,
        }

    def _line(self) -> dict[str, object]:
        return capture_hook.shape_of(self._payload(), event="PreToolUse", salt="s", elapsed_ms=1.25)

    def test_no_field_of_the_payload_leaks_into_the_line(self) -> None:
        """The one assertion that matters most.

        Serialised and searched rather than checked field by field, so a future
        field added to the capture cannot smuggle content past a per-key check.
        """
        rendered = json.dumps(self._line())
        self.assertNotIn(self.SECRET, rendered)

    def test_every_never_record_key_is_absent_by_name_too(self) -> None:
        line = self._line()
        for forbidden in capture_hook.NEVER_RECORD:
            with self.subTest(field=forbidden):
                self.assertNotIn(forbidden, line)

    def test_the_session_is_truncated_to_the_collector_prefix(self) -> None:
        """Eight characters, which is what the collectors key on."""
        self.assertEqual("9f3c1a2e", self._line()["session"])

    def test_the_working_directory_becomes_a_salted_digest(self) -> None:
        a = capture_hook.shape_of(self._payload(), event="x", salt="salt-a", elapsed_ms=0)
        b = capture_hook.shape_of(self._payload(), event="x", salt="salt-b", elapsed_ms=0)
        self.assertTrue(a["project"], "sessions must still be distinguishable")
        self.assertNotEqual(a["project"], b["project"], "the salt must actually salt")
        self.assertNotIn(self.SECRET, str(a["project"]))

    def test_the_payload_keys_are_recorded_because_that_is_the_adapter_contract(self) -> None:
        keys = self._line()["keys"]
        assert isinstance(keys, list)
        self.assertIn("tool_input", keys, "which fields arrive is the thing being studied")
        self.assertEqual(sorted(keys), keys, "sorted, so shapes compare across runs")

    def test_the_tool_name_is_kept_but_its_arguments_are_not(self) -> None:
        line = self._line()
        self.assertEqual("Bash", line["tool"])
        self.assertNotIn(self.SECRET, json.dumps(line))

    def test_the_hook_records_its_own_cost(self) -> None:
        """The p99 budget the adapter-semantics gate asks for."""
        self.assertEqual(1.25, self._line()["hook_ms"])

    def test_a_payload_with_nothing_recognisable_still_produces_a_line(self) -> None:
        line = capture_hook.shape_of({}, event="Stop", salt="s", elapsed_ms=0)
        self.assertEqual("Stop", line["event"])
        self.assertEqual("", line["session"])


class RecordTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(
            unittest.mock.patch.dict("os.environ", {"CARGENTO_CAPTURE_DIR": str(self.dir)})
        )

    def _run(self, payload: object, argv: list[str] | None = None) -> int:
        text = json.dumps(payload) if not isinstance(payload, bytes) else payload.decode()
        stdin = unittest.mock.MagicMock()
        stdin.buffer.read.return_value = text.encode()
        with unittest.mock.patch.object(sys, "stdin", stdin):
            return capture_hook.main(argv or ["capture_hook.py"])

    def _lines(self) -> list[dict[str, object]]:
        return capture_hook.load_captures(self.dir)

    def test_one_event_appends_one_line(self) -> None:
        self.assertEqual(0, self._run({"hook_event_name": "Stop", "session_id": "abcd1234"}))
        lines = self._lines()
        self.assertEqual(1, len(lines))
        self.assertEqual("Stop", lines[0]["event"])

    def test_the_harness_event_name_wins_over_argv(self) -> None:
        self._run({"hook_event_name": "Stop"}, ["capture_hook.py", "FromArgv"])
        self.assertEqual("Stop", self._lines()[0]["event"])

    def test_argv_names_the_event_for_a_harness_that_does_not(self) -> None:
        self._run({"session_id": "abcd1234"}, ["capture_hook.py", "FromArgv"])
        self.assertEqual("FromArgv", self._lines()[0]["event"])

    def test_malformed_json_is_recorded_as_an_unknown_event_not_a_crash(self) -> None:
        stdin = unittest.mock.MagicMock()
        stdin.buffer.read.return_value = b"{not json"
        with unittest.mock.patch.object(sys, "stdin", stdin):
            self.assertEqual(0, capture_hook.main(["capture_hook.py"]))
        self.assertEqual("unknown", self._lines()[0]["event"])

    def test_an_unwritable_capture_directory_still_exits_zero(self) -> None:
        """A hook runs on the user's critical path and may never fail them."""
        with unittest.mock.patch.dict(
            "os.environ", {"CARGENTO_CAPTURE_DIR": "/proc/nonexistent/nope"}
        ):
            self.assertEqual(0, self._run({"hook_event_name": "Stop"}))

    def test_the_salt_is_created_once_and_reused(self) -> None:
        first = capture_hook.salt_for(self.dir)
        self.assertEqual(first, capture_hook.salt_for(self.dir))
        self.assertTrue(first)

    def test_a_torn_line_does_not_stop_the_reader(self) -> None:
        target = self.dir / "claude-x.jsonl"
        target.write_text('{"event":"Stop"}\n{"event":"tor\n{"event":"SessionEnd"}\n', "utf-8")
        self.assertEqual(["Stop", "SessionEnd"], [e["event"] for e in self._lines()])


class ReportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def _write(self, events: list[tuple[str, str, float]]) -> None:
        lines = [
            json.dumps(
                {
                    "v": 1,
                    "at": at,
                    "event": event,
                    "session": session,
                    "keys": ["session_id"],
                    "tool": "",
                    "hook_ms": 0.5,
                    "os": "posix",
                }
            )
            for event, session, at in events
        ]
        (self.dir / "claude-x.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_an_empty_directory_says_so_rather_than_pretending(self) -> None:
        self.assertIn("No captures", capture_hook.report(self.dir))

    def test_a_turn_is_bounded_by_prompt_and_stop(self) -> None:
        self._write(
            [
                ("UserPromptSubmit", "aaaa1111", 1.0),
                ("PreToolUse", "aaaa1111", 2.0),
                ("PostToolUse", "aaaa1111", 3.0),
                ("Stop", "aaaa1111", 4.0),
            ]
        )
        turns = capture_hook.turns_for(
            capture_hook.load_captures(self.dir), start="UserPromptSubmit", end="Stop"
        )
        self.assertEqual([["UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"]], turns)

    def test_two_concurrent_sessions_do_not_interleave_into_one_turn(self) -> None:
        """A global ordering would invent transitions neither session made."""
        self._write(
            [
                ("UserPromptSubmit", "aaaa1111", 1.0),
                ("UserPromptSubmit", "bbbb2222", 1.5),
                ("PreToolUse", "aaaa1111", 2.0),
                ("Stop", "bbbb2222", 2.5),
                ("Stop", "aaaa1111", 3.0),
            ]
        )
        turns = capture_hook.turns_for(
            capture_hook.load_captures(self.dir), start="UserPromptSubmit", end="Stop"
        )
        self.assertIn(["UserPromptSubmit", "PreToolUse", "Stop"], turns)
        self.assertIn(["UserPromptSubmit", "Stop"], turns)
        for turn in turns:
            self.assertEqual(1, turn.count("Stop"), "a turn must not absorb another's stop")

    def test_the_report_names_cardinality_shape_and_the_p99(self) -> None:
        self._write([("UserPromptSubmit", "a", 1.0), ("Stop", "a", 2.0)])
        text = capture_hook.report(self.dir)
        self.assertIn("Event cardinality", text)
        self.assertIn("Payload shape per event", text)
        self.assertIn("p99", text)

    def test_the_install_snippet_names_every_event_and_the_privacy_promise(self) -> None:
        text = capture_hook.install_snippet()
        for event in ("SessionStart", "PermissionRequest", "SubagentStart", "SessionEnd"):
            self.assertIn(event, text)
        self.assertIn("no prompts", text)


if __name__ == "__main__":
    unittest.main()
