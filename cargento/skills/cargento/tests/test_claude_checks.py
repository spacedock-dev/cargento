"""What a Claude Code reader sees of the checks a session ran and the files it wrote.

DEC-23 (docs/design-reading-a-session.md) is the ruling. Every fixture below is
built from the field SHAPES in
`docs/captures/claude/transcript-tool-shapes-2.1.281-macos.jsonl`: an assistant
record holding a `tool_use` block (`id`, `name`, `input`), and a user record
holding the `tool_result` block that points back at it (`tool_use_id`,
`content`, and `is_error` on a shell result only). No text here came from a real
transcript.
"""

from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from cargento_runtime import observer, project_context, semantic_history
from cargento_runtime.config import build_runtime_config
from cargento_runtime.state import build_runtime_state

SID = "4a1c9e7d-0000-4000-8000-000000000001"
SHORT = SID[:8]
START = dt.datetime(2026, 9, 24, 3, 0, 0, tzinfo=dt.UTC)
# Synthetic, and deliberately obvious: a real prefix followed by a run of one letter.
FAKE_KEY = "sk-ant-api03-" + "Q" * 95
# Node's summary glyph and failure glyph, written as escapes so review can read them.
INFO = "\u2139"
CROSS = "\u2716"


class Transcript:
    """A Claude Code transcript in the recorded shapes, one call at a time."""

    def __init__(self, cwd: Path) -> None:
        self.cwd = str(cwd)
        self.rows: list[dict[str, Any]] = []
        self.seconds = 0
        self.calls = 0

    def _stamp(self) -> str:
        self.seconds += 5
        return (START + dt.timedelta(seconds=self.seconds)).isoformat().replace("+00:00", "Z")

    def _entry(self, kind: str, content: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
        row: dict[str, Any] = {
            "type": kind,
            "uuid": f"u{len(self.rows)}",
            "parentUuid": f"u{len(self.rows) - 1}" if self.rows else None,
            "isSidechain": False,
            "cwd": self.cwd,
            "sessionId": SID,
            "timestamp": self._stamp(),
            "message": {"role": kind, "content": content},
        }
        row.update(extra)
        self.rows.append(row)
        return row

    def prompt(self, text: str) -> None:
        self._entry("user", [{"type": "text", "text": text}])

    def call(self, name: str, tool_input: dict[str, Any], *, sidechain: bool = False) -> str:
        self.calls += 1
        call_id = f"toolu_{self.calls:03d}"
        self._entry(
            "assistant",
            [
                {
                    "type": "tool_use",
                    "id": call_id,
                    "name": name,
                    "input": tool_input,
                    "caller": {"type": "direct"},
                }
            ],
            isSidechain=sidechain,
        )
        return call_id

    def result(self, call_id: str, content: Any, **block: Any) -> None:
        tool_use_result = block.pop("tool_use_result", {})
        self._entry(
            "user",
            [{"type": "tool_result", "tool_use_id": call_id, "content": content, **block}],
            toolUseResult=tool_use_result,
        )

    def bash(self, command: str, output: str = "", *, is_error: Any = False, **extra: Any) -> str:
        call_id = self.call("Bash", {"command": command, **extra})
        self.result(call_id, output, is_error=is_error)
        return call_id

    def write(self, path: str, content: str = "print('hello')\n") -> None:
        call_id = self.call("Write", {"file_path": path, "content": content})
        self.result(call_id, f"File created successfully at: {path}")

    def edit(self, path: str, old: str = "a", new: str = "b") -> None:
        call_id = self.call("Edit", {"file_path": path, "old_string": old, "new_string": new})
        self.result(call_id, f"The file {path} has been updated successfully.")

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(row) for row in self.rows) + "\n", encoding="utf-8")


class ClaudeChecksTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cwd = self.root / "work" / "billing"
        self.cwd.mkdir(parents=True)
        self.path = self.root / "claude" / "projects" / "-work-billing" / f"{SID}.jsonl"
        self.config = build_runtime_config(
            environ={"HOME": str(self.root), "CARGENTO_HOME": str(self.root / "state")},
            platform_name="linux",
            os_name="posix",
            launcher_path=self.root / "server.py",
            store_root_overrides={"claude.projects": str(self.root / "claude" / "projects")},
        )
        self.session = Transcript(self.cwd)
        self.session.prompt("Add retry with backoff to the webhook handler.")

    def file(self, name: str) -> str:
        return str(self.cwd / name)

    def read(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        self.session.save(self.path)
        return project_context.claude_tool_reports(self.config, str(self.path), SHORT)

    def checks(self) -> list[dict[str, Any]]:
        return [event for event in self.read()[0] if event["subject"] == "check"]

    def only_check(self) -> dict[str, Any]:
        found = self.checks()
        self.assertEqual(1, len(found), found)
        return found[0]


class WhatAReaderSeesOfTheChecksASessionRan(ClaudeChecksTestCase):
    def test_a_fixed_check_reads_as_passed_with_its_earlier_failure_noted_once(self) -> None:
        self.session.write(self.file("src/retry.py"))
        self.session.bash("python3 -m pytest tests", "1 failed, 4 passed in 0.31s", is_error=True)
        self.session.bash("python3 -m pytest tests", "5 passed in 0.29s", is_error=False)

        events, scan = self.read()

        checks = [event for event in events if event["subject"] == "check"]
        writes = [event for event in events if event["subject"] == "write"]
        self.assertEqual(1, len(checks))
        self.assertEqual("passed", checks[0]["result"])
        self.assertEqual("flag", checks[0]["result_source"])
        self.assertIs(True, checks[0]["earlier_failed"])
        self.assertEqual("python3 -m pytest tests", checks[0]["title"])
        self.assertEqual(["src/retry.py"], [event["title"] for event in writes])
        self.assertEqual(2, scan["check_runs"])
        self.assertEqual(1, scan["distinct_checks"])
        self.assertEqual(1, scan["written_paths"])

    def test_a_piped_run_whose_tail_says_two_failed_is_a_failure_whatever_the_flag(self) -> None:
        self.session.bash(
            "pytest -q 2>&1 | tail -3",
            "FAILED tests/test_retry.py::test_backoff\n2 failed, 3 passed",
        )
        check = self.only_check()
        self.assertEqual("failed", check["result"])
        self.assertEqual("summary", check["result_source"])

    def test_a_piped_node_run_that_kept_only_an_assertion_marker_is_a_failure(self) -> None:
        tail = (
            "  code: 'ERR_ASSERTION',\n  actual: 2,\n  expected: 3,\n  operator: 'strictEqual'\n}"
        )
        self.session.bash("node --test 2>&1 | tail -20", tail, is_error=False)
        check = self.only_check()
        self.assertEqual("failed", check["result"])
        self.assertEqual("marker", check["result_source"])

    def test_a_piped_run_that_left_no_summary_or_marker_is_never_a_pass(self) -> None:
        self.session.bash("pytest -q 2>&1 | tail -2", "collected 5 items\n.....", is_error=False)
        check = self.only_check()
        self.assertEqual("not-recorded", check["result"])
        self.assertNotIn("result_source", check)

    def test_a_pass_never_rests_on_a_missing_or_malformed_error_flag(self) -> None:
        flags: tuple[Any, ...] = (None, "false", 0, [], {})
        for flag in flags:
            with self.subTest(flag=flag):
                self.setUp()
                call_id = self.session.call("Bash", {"command": "pytest"})
                block = {} if flag is None else {"is_error": flag}
                self.session.result(call_id, "", **block)
                check = self.only_check()
                self.assertEqual("not-recorded", check["result"])
                self.assertEqual(1, self.read()[1]["unknown_flags"])

    def test_node_prints_its_counts_one_per_line_and_fail_zero_is_a_pass(self) -> None:
        passing = f"{INFO} tests 5\n{INFO} suites 0\n{INFO} pass 5\n{INFO} fail 0\n{INFO} cancelled 0\n{INFO} duration_ms 52"
        failing = f"{INFO} tests 5\n{INFO} suites 0\n{INFO} pass 3\n{INFO} fail 2\n{INFO} cancelled 0\n{INFO} duration_ms 55"
        for output, expected in ((passing, "passed"), (failing, "failed")):
            with self.subTest(expected=expected):
                self.setUp()
                self.session.bash("node --test 2>&1 | tail -8", output, is_error=False)
                check = self.only_check()
                self.assertEqual(expected, check["result"])
                self.assertEqual("summary", check["result_source"])

    def test_a_node_pass_count_alone_is_not_a_pass(self) -> None:
        self.session.bash(
            "node --test 2>&1 | head -3", f"{INFO} tests 5\n{INFO} pass 5", is_error=False
        )
        self.assertEqual("not-recorded", self.only_check()["result"])

    def test_a_check_after_cd_is_listed_and_its_flag_is_read(self) -> None:
        self.session.bash("cd services/billing && python3 -m unittest", "", is_error=True)
        check = self.only_check()
        self.assertEqual("python3 -m unittest", check["title"])
        self.assertEqual("failed", check["result"])
        self.assertEqual("flag", check["result_source"])

    def test_a_flag_is_read_through_and_and_never_through_a_semicolon_or_pipe(self) -> None:
        for command, expected in (
            ("pytest && echo done", "passed"),
            ("pytest; echo done", "not-recorded"),
            ("pytest | tee out.log", "not-recorded"),
            ("pytest || true", "not-recorded"),
        ):
            with self.subTest(command=command):
                self.setUp()
                self.session.bash(command, "", is_error=False)
                self.assertEqual(expected, self.only_check()["result"])

    def test_wrappers_and_assignments_are_stripped_before_the_runner_is_matched(self) -> None:
        for command, title in (
            ("CI=1 uv run pytest -q", "pytest -q"),
            ("timeout 60 npx jest --ci", "jest --ci"),
            ("poetry run mypy src", "mypy src"),
            ("time cargo test", "cargo test"),
            ("python3 scripts/run_tests.py -j 4", "python3 scripts/run_tests.py -j 4"),
            ("./test.sh", "./test.sh"),
            ("ruff format --check .", "ruff format --check ."),
            ("tsc --noEmit", "tsc --noEmit"),
        ):
            with self.subTest(command=command):
                self.setUp()
                self.session.bash(command, "", is_error=False)
                self.assertEqual(title, self.only_check()["title"])

    def test_a_check_line_is_its_own_segment_and_never_the_rest_of_the_shell_line(self) -> None:
        self.session.bash("cd api && pytest -q 2>&1 | tail -3 ; echo done", "3 passed")
        title = self.only_check()["title"]
        self.assertEqual("pytest -q 2>&1", title)

    def test_a_program_file_is_a_check_only_when_test_stands_alone_in_its_name(self) -> None:
        for command, is_check in (
            ("python3 scripts/run_tests.py", True),
            ("./test.sh", True),
            ("bash ci/unit-tests.sh", True),
            ("python3 runtests.py", False),
            ("python3 fetch_latest_creds.py", False),
            ("./contest.sh", False),
        ):
            with self.subTest(command=command):
                self.setUp()
                self.session.bash(command, "", is_error=False)
                self.assertEqual(is_check, bool(self.checks()))

    def test_a_pass_summary_beside_any_record_of_failure_is_a_failure(self) -> None:
        for output, source in (
            ("1 failed, 9 passed in 0.4s", "summary"),
            ("AssertionError: retries\n9 passed", "marker"),
        ):
            with self.subTest(output=output):
                self.setUp()
                self.session.bash("pytest 2>&1 | tail -4", output, is_error=False)
                check = self.only_check()
                self.assertEqual("failed", check["result"])
                self.assertEqual(source, check["result_source"])

    def test_go_and_unittest_passes_need_the_flag_or_the_whole_summary_line(self) -> None:
        for command, output, expected in (
            ("go test ./... | tail -2", "ok  \texample.com/retry\t0.2s", "not-recorded"),
            ("go test ./...", "ok  \texample.com/retry\t0.2s", "passed"),
            ("python3 -m unittest 2>&1 | tail -1", "OK (skipped=1)", "not-recorded"),
            ("python3 -m unittest 2>&1 | tail -1", "Ran 4 tests in 0.01s\n\nOK", "passed"),
        ):
            with self.subTest(command=command, output=output):
                self.setUp()
                self.session.bash(command, output, is_error=False)
                self.assertEqual(expected, self.only_check()["result"])

    def test_commands_that_only_read_are_told_apart_from_ones_that_may_change_things(
        self,
    ) -> None:
        self.session.bash("git status && git diff --stat", "", is_error=False)
        self.session.bash("cd src && ls | wc -l", "", is_error=False)
        self.session.bash("find . -name '*.py' | head", "", is_error=False)
        self.session.bash("echo ready > status.txt", "", is_error=False)
        self.session.bash("find . -name '*.pyc' -delete", "", is_error=False)
        self.session.bash("pip install requests", "", is_error=False)
        events, scan = self.read()
        self.assertEqual([], events)
        self.assertEqual(6, scan["other_commands"])
        self.assertEqual(3, scan["read_only_commands"])
        self.assertIsNotNone(scan["last_changing_command_at"])

    def test_a_session_that_only_read_records_no_changing_command(self) -> None:
        self.session.bash("git log --oneline -5", "", is_error=False)
        self.assertIsNone(self.read()[1]["last_changing_command_at"])

    def test_a_check_on_a_later_line_of_a_multiline_command_is_found(self) -> None:
        self.session.bash("cd services/api\npytest -q", "", is_error=True)
        check = self.only_check()
        self.assertEqual("pytest -q", check["title"])
        self.assertEqual("failed", check["result"])
        self.assertEqual("flag", check["result_source"])

    def test_only_and_may_follow_a_runner_whose_flag_is_read(self) -> None:
        for command in ("pytest\necho done", "pytest ; echo", "pytest | cat", "pytest || true"):
            with self.subTest(command=command):
                self.setUp()
                self.session.bash(command, "", is_error=False)
                self.assertEqual("not-recorded", self.only_check()["result"])

    def test_pytest_errors_are_failures_by_summary_and_by_marker(self) -> None:
        for output, source in (
            ("1 error in 0.20s", "summary"),
            ("3 passed, 2 errors in 0.4s", "summary"),
            ("ERROR tests/test_retry.py - ImportError: no module", "marker"),
        ):
            with self.subTest(output=output):
                self.setUp()
                self.session.bash("pytest 2>&1 | tail -3", output, is_error=False)
                check = self.only_check()
                self.assertEqual("failed", check["result"])
                self.assertEqual(source, check["result_source"])

    def test_a_pass_that_ran_nothing_is_not_a_pass(self) -> None:
        for command, output in (
            ("node --test 2>&1 | tail -3", f"{INFO} tests 0\n{INFO} pass 0\n{INFO} fail 0"),
            ("pytest 2>&1 | tail -1", "0 passed in 0.01s"),
            ("python3 -m unittest 2>&1 | tail -3", "Ran 0 tests in 0.000s\n\nOK"),
            ("go test ./...", "ok  \texample.com/retry\t0.2s [no tests to run]"),
        ):
            with self.subTest(command=command):
                self.setUp()
                self.session.bash(command, output, is_error=False)
                self.assertEqual("not-recorded", self.only_check()["result"])

    def test_a_changing_segment_is_timed_even_inside_a_check_command(self) -> None:
        self.session.bash("pytest", "5 passed", is_error=False)
        self.session.bash("pip install requests && pytest", "5 passed", is_error=False)
        events, scan = self.read()
        check = next(event for event in events if event["subject"] == "check")
        self.assertEqual(check["at"], scan["last_changing_command_at"])
        self.assertEqual(0, scan["other_commands"])

    def test_a_changing_command_after_a_pass_is_timed_after_it(self) -> None:
        self.session.bash("pytest", "5 passed", is_error=False)
        self.session.bash("git commit -am wip", "", is_error=False)
        events, scan = self.read()
        check = next(event for event in events if event["subject"] == "check")
        self.assertGreater(scan["last_changing_command_at"], check["at"])
        self.assertNotIn("git commit", json.dumps(scan))

    def test_a_changing_command_launched_in_the_background_is_still_timed(self) -> None:
        call_id = self.session.call("Bash", {"command": "npm run dev", "run_in_background": True})
        self.session.result(call_id, "Command running in background with ID: b2.")
        scan = self.read()[1]
        self.assertEqual(1, scan["background"])
        self.assertIsNotNone(scan["last_changing_command_at"])

    def test_commands_off_the_closed_list_are_counted_and_never_listed(self) -> None:
        self.session.bash("grep -rn retry_after src", "", is_error=True)
        self.session.bash("ls docs/missing.md", "ls: docs/missing.md: No such file", is_error=True)
        self.session.bash("test -f setup.cfg && echo yes", "", is_error=True)
        self.session.bash("[ -d build ] || mkdir build", "", is_error=False)
        self.session.bash("ruff format .", "3 files reformatted", is_error=False)
        events, scan = self.read()
        self.assertEqual([], events)
        self.assertEqual(5, scan["shell_calls"])
        self.assertEqual(5, scan["other_commands"])
        self.assertEqual(0, scan["check_runs"])

    def test_a_background_test_launch_is_counted_and_never_listed_or_read_as_a_result(
        self,
    ) -> None:
        call_id = self.session.call("Bash", {"command": "node --test", "run_in_background": True})
        self.session.result(
            call_id,
            "Command running in background with ID: b1. You will be notified.",
            is_error=False,
            tool_use_result={"backgroundTaskId": "b1", "stdout": "", "stderr": ""},
        )
        self.session.bash("pytest &", "", is_error=False)
        events, scan = self.read()
        self.assertEqual([], events)
        self.assertEqual(2, scan["background"])
        self.assertEqual(0, scan["check_runs"])

    def test_a_pass_followed_by_a_write_is_marked_before_the_last_change(self) -> None:
        self.session.bash("pytest", "5 passed", is_error=False)
        self.session.edit(self.file("src/retry.py"))
        check = self.only_check()
        self.assertEqual("passed", check["result"])
        self.assertIs(True, check["before_last_change"])

    def test_a_pass_after_the_last_write_is_not_marked(self) -> None:
        self.session.edit(self.file("src/retry.py"))
        self.session.bash("pytest", "5 passed", is_error=False)
        self.assertIs(False, self.only_check()["before_last_change"])

    def test_one_check_piped_differently_each_time_is_still_one_check(self) -> None:
        self.session.bash("node --test 2>&1 | tail -20", f"{CROSS} retries\nERR_ASSERTION")
        self.session.bash("node --test 2>&1 | tail -5", f"{INFO} pass 5\n{INFO} fail 0")
        self.session.bash("node --test 2>&1 | grep -E 'pass|fail'", f"{INFO} pass 5\n{INFO} fail 0")
        self.session.bash("node --test", "", is_error=False)
        check = self.only_check()
        self.assertEqual("passed", check["result"])
        self.assertIs(True, check["earlier_failed"])
        self.assertEqual("node --test", check["title"])

    def test_a_run_still_in_flight_has_no_result_yet(self) -> None:
        self.session.call("Bash", {"command": "pytest"})
        check = self.only_check()
        self.assertEqual("not-recorded", check["result"])
        self.assertIn("no result recorded yet", check["source"])

    def test_a_subagents_checks_are_left_for_their_own_layer(self) -> None:
        call_id = self.session.call("Bash", {"command": "pytest"}, sidechain=True)
        self.session.result(call_id, "", is_error=True)
        events, scan = self.read()
        self.assertEqual([], events)
        self.assertEqual(0, scan["shell_calls"])


class WhatAReaderSeesOfTheFilesASessionWrote(ClaudeChecksTestCase):
    def test_a_written_path_reads_relative_to_the_working_directory(self) -> None:
        self.session.write(self.file("src/retry.py"))
        self.session.edit(self.file("src/retry.py"))
        self.session.edit(self.file("tests/test_retry.py"))
        events, scan = self.read()
        self.assertEqual(
            ["src/retry.py", "tests/test_retry.py"], sorted(event["title"] for event in events)
        )
        self.assertEqual(2, scan["written_paths"])

    def test_a_path_outside_the_working_directory_is_counted_and_not_listed(self) -> None:
        self.session.write(str(self.root / "elsewhere" / "notes.md"))
        events, scan = self.read()
        self.assertEqual([], events)
        self.assertEqual(1, scan["outside_paths"])

    def test_a_reader_never_sees_what_a_file_said(self) -> None:
        self.session.write(self.file("src/retry.py"), content="WRITTEN_BODY_SENTINEL")
        self.session.edit(self.file("src/retry.py"), old="OLD_SENTINEL", new="NEW_SENTINEL")
        published = json.dumps(self.read())
        for sentinel in ("WRITTEN_BODY_SENTINEL", "OLD_SENTINEL", "NEW_SENTINEL", "updated"):
            with self.subTest(sentinel=sentinel):
                self.assertNotIn(sentinel, published)

    def test_an_edit_the_harness_refused_wrote_nothing(self) -> None:
        call_id = self.session.call("Edit", {"file_path": self.file("a.py")})
        self.session.result(call_id, "File has not been read yet.", is_error=True)
        events, scan = self.read()
        self.assertEqual([], events)
        self.assertEqual(0, scan["written_paths"])


class WhatAReaderIsNeverShownOfACommandLine(ClaudeChecksTestCase):
    def test_a_key_across_the_line_clip_never_reaches_the_page(self) -> None:
        for lead in range(100, 125):
            with self.subTest(lead=lead):
                self.setUp()
                padding = "k" * max(0, lead - len("pytest --token="))
                self.session.bash(f"pytest --token={padding}{FAKE_KEY}", "", is_error=False)
                title = self.only_check()["title"]
                self.assertNotIn(FAKE_KEY[:20], title)
                self.assertNotIn("Q" * 12, title)

    def test_a_password_in_any_form_redaction_cannot_see_is_masked(self) -> None:
        value = "hunter2x"
        for command in (
            f"PGPASSWORD={value} pytest tests/db",
            f"pytest --password {value}",
            f"pytest --password={value}",
            f"pytest --dsn postgres://app:{value}@localhost/test",
        ):
            with self.subTest(command=command.split()[0]):
                self.setUp()
                self.session.bash(command, "", is_error=False)
                published = json.dumps(self.read())
                self.assertNotIn(value, published)


class WhichChecksAReaderIsShownFirst(ClaudeChecksTestCase):
    def test_failures_are_kept_before_passes_and_the_rest_are_counted(self) -> None:
        for n in range(10):
            self.session.bash(f"pytest tests/test_pass_{n}.py", "1 passed", is_error=False)
        for n in range(3):
            self.session.bash(f"pytest tests/test_fail_{n}.py", "1 failed", is_error=True)
        self.session.write(self.file("src/a.py"))
        self.session.write(self.file("src/b.py"))
        events, scan = self.read()
        self.assertEqual(12, len(events))
        self.assertEqual(3, sum(event.get("result") == "failed" for event in events))
        self.assertEqual(0, sum(event["subject"] == "write" for event in events))
        self.assertEqual(3, scan["more"])
        self.assertEqual(12, scan["listed"])
        self.assertEqual(13, scan["distinct_checks"])
        self.assertEqual(2, scan["written_paths"])
        self.assertEqual(3, scan["failed"])
        self.assertEqual(10, scan["passed"])


class WhereTheChecksGoOnceCollected(ClaudeChecksTestCase):
    NOW = START.timestamp() + 3600

    def setUp(self) -> None:
        super().setUp()
        patcher = mock.patch.object(observer.CodexGoalModel, "__call__", return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def collect(self, harness: str = "claude") -> dict[str, Any]:
        self.session.save(self.path)
        state = build_runtime_state(self.config, started=self.NOW)
        rows = [
            {
                "project": "billing",
                "harness": harness,
                "sid": SHORT,
                "last_activity": self.NOW,
                "active": True,
            }
        ]
        return project_context.collect(
            self.config, state, rows, "billing", now=self.NOW, focus=(harness, SHORT)
        )

    def test_the_observed_record_shows_the_checks_and_writes_as_their_own_type(self) -> None:
        self.session.write(self.file("src/retry.py"))
        self.session.bash("pytest", "1 failed", is_error=True)
        self.session.bash("pytest", "5 passed", is_error=False)
        context = self.collect()
        facts = [f for f in context["semantic"]["facts"] if f.get("type") == "tool_report"]
        self.assertEqual({"check", "write"}, {fact["subject"] for fact in facts})
        check = next(fact for fact in facts if fact["subject"] == "check")
        self.assertEqual("passed", check["result"])
        self.assertIs(True, check["earlier_failed"])
        self.assertEqual({"harness": "claude", "sid": SHORT}, check["source_session"])
        scans = context["sources"]["work"]["tool_reports"]
        self.assertEqual([("claude", SHORT)], [(row["harness"], row["sid"]) for row in scans])
        self.assertEqual(2, scans[0]["check_runs"])
        self.assertEqual(2, context["sources"]["work"]["live"])

    def test_a_reader_who_restarts_finds_none_of_them_in_session_history(self) -> None:
        self.session.bash("pytest", "5 passed", is_error=False)
        self.session.write(self.file("src/retry.py"))
        self.collect()
        stored = Path(semantic_history.store_path(self.config))
        text = stored.read_text(encoding="utf-8") if stored.exists() else ""
        self.assertIn("Add retry with backoff", text)
        self.assertNotIn("tool_report", text)
        self.assertNotIn("src/retry.py", text)

    def test_the_history_source_never_reads_the_checks_at_all(self) -> None:
        # The first wall. `semantic_history._FACT_EVENT_TYPES` is the second,
        # and with it alone the store test above would stay green.
        self.session.bash("pytest", "5 passed", is_error=False)
        self.session.write(self.file("src/retry.py"))
        self.session.save(self.path)
        events = project_context._semantic_history_source_events(
            self.config, str(self.path), "claude", SHORT, since=0.0, max_bytes=1 << 20
        )
        self.assertTrue(events)
        self.assertEqual(set(), {e["kind"] for e in events} & {"check_run", "path_written"})

    def test_a_session_on_another_harness_gains_nothing(self) -> None:
        self.session.bash("pytest", "5 passed", is_error=False)
        with mock.patch.object(observer, "resolve_transcript", return_value=str(self.path)):
            context = self.collect(harness="pi")
        self.assertEqual([], context["sources"]["work"]["tool_reports"])
        self.assertFalse(
            [f for f in context["semantic"]["facts"] if f.get("type") == "tool_report"]
        )


if __name__ == "__main__":
    unittest.main()
