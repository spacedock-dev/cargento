"""The command report boundary, independently of ordinary lifecycle hints."""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import event_hook
from cargento_runtime import aggregate, cli, irreversible, lifecycle, observation, sessions

from . import support
from .next_harness import NextPageJsHarness
from .test_events_ingress import FakeApplication

SESSION = "abcdef12-3456-7890-abcd-ef1234567890"
NOW = 1_700_000_000.0
HOOK = Path(event_hook.__file__).resolve()
ROOT = HOOK.parents[3]


def native(command: Any, **changes: Any) -> dict[str, Any]:
    return {
        "hook_event_name": "PostToolUse",
        "session_id": SESSION,
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_response": "private-output",
        **changes,
    }


def wire(pattern: str = "git_force_push", **changes: Any) -> dict[str, Any]:
    return {
        "v": 1,
        "event": "command_shape_reported",
        "session_id": SESSION,
        "timestamp": datetime.fromtimestamp(NOW, UTC).isoformat(),
        "pattern_id": pattern,
        "tool_name": "Bash",
        **changes,
    }


POSITIVES = (
    ("git push --force private_force", "git_force_push"),
    ("git push -f private_short", "git_force_push"),
    ("git push private_remote private_ref --force-with-lease", "git_force_push"),
    ("git reset --hard", "git_hard_reset"),
    ("git reset --hard private_revision", "git_hard_reset"),
    ("psql -c 'DROP TABLE private_psql;'", "sql_drop_table"),
    ('mysql -e "drop table if exists private_mysql"', "sql_drop_table"),
    ("sqlite3 private_database 'DROP TABLE private_schema.private_table;'", "sql_drop_table"),
    ("rm -r private_r", "recursive_delete"),
    ("rm -R private_R", "recursive_delete"),
    ("rm -rf private_rf", "recursive_delete"),
    ("rm -fr private_fr", "recursive_delete"),
    ("rm -Rf private_Rf", "recursive_delete"),
    ("rm -fR private_fR", "recursive_delete"),
    ("rm -r -f -- /tmp/private_temp private_outside", "recursive_delete"),
)
NEGATIVES = (
    "",
    " ",
    "git push",
    "git push --forceful",
    "git push -vf",
    "git push --force --dry-run",
    "git push --force-with-lease=branch",
    "git -C /repo push --force",
    "git reset --hard -q",
    "git reset --hard a b",
    "rm -f private",
    "rm -rf /tmp/private",
    "rm -rf /private/tmp/private",
    "rm -rf /var/tmp/private",
    "rm -rf /tmp/../private",
    "rm -rf --",
    "rm -rf -v private",
    "git push --force; echo private",
    "git push --force && echo private",
    "git push --force\necho private",
    "git push --force $PRIVATE",
    "git push --force `private`",
    "git push --force > private",
    "git push --force | private",
    "git push --force #private",
    "git push --force private\\ name",
    "sudo git push --force",
    "env PRIVATE=1 git push --force",
    "/usr/bin/git push --force",
    "rtk proxy proxy git push --force",
    "rtk",
    "rtk proxy",
    "git push '--force'",
    "psql -c 'DROP TABLE private; DELETE FROM private;'",
    "psql -c 'DROP TABLE private CASCADE;'",
    "psql -c 'DROP TABLE private' extra",
    "psql -c 'DROP TABLE private",
    "psql -c 'DROP TABLE 123;'",
    'psql -c "DROP TABLE $PRIVATE;"',
    "mysql -e 'DROP TABLE private --comment;'",
    "sqlite3 -flag 'DROP TABLE private;'",
    "git push --force " + "x" * 4096,
    "git push --force " + "x " * 64,
    "git\vpush --force private",
    "git push --force private\x00",
)


class CommandSocketTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config, state = support.make_runtime(
            state_home=self.tmp.name,
            state_dir=Path(self.tmp.name),
            annotations_enabled=False,
            dismissals_enabled=False,
            history_enabled=False,
            event_burst_max=1000,
            focus_enabled=False,
            git_probe_enabled=False,
        )
        spec = aggregate.HarnessSpec(
            "claude",
            "Claude",
            lambda *_: True,
            lambda *_: [sessions.base_session("claude", SESSION[:8], "project")],
        )
        self.app = aggregate.Application(
            self.config,
            state,
            (spec,),
            native_notifier=lambda _: "",
            popup_notifier=lambda *_: None,
            diagnostic_sink=lambda _: None,
            clock=lambda: NOW,
        )
        self.coordinator = observation.Observation(self.app, clock=lambda: NOW)
        self.app.overlays = self.coordinator
        self.received: list[dict[str, Any]] = []
        submit = self.coordinator.submit

        def capture(harness: str, payload: Any) -> str:
            result = submit(harness, payload)
            if result == "accepted" and payload.get("event") == "command_shape_reported":
                self.received.append(payload)
            return result

        patcher = patch.object(self.coordinator, "submit", capture)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.server = support.make_server(application=self.app, observation=self.coordinator)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )
        self.thread.start()
        self.addCleanup(self.close_server)
        self.write_state(True)

    def close_server(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(1)

    def write_state(self, enabled: bool | None) -> None:
        data: dict[str, Any] = {"capabilities": self.coordinator.capabilities()}
        if enabled is not None:
            data["irreversible_enabled"] = enabled
        target = Path(self.tmp.name, f"cargento-{self.port}.json")
        pending = target.with_suffix(".tmp")
        pending.write_text(json.dumps(data))
        pending.replace(target)

    def run_hook(
        self, payload: Any, harness: str = "claude", *, driver: str = "", timeout: float = 3
    ) -> subprocess.CompletedProcess[bytes]:
        code = (
            "import sys; sys.path.insert(0, sys.argv[1]); import event_hook\n"
            + driver
            + "\nraise SystemExit(event_hook.main(['event_hook', sys.argv[2], sys.argv[3]]))"
        )
        return subprocess.run(
            [sys.executable, "-c", code, str(HOOK.parent), harness, str(self.port)],
            input=json.dumps(payload).encode(),
            capture_output=True,
            timeout=timeout,
            env={**os.environ, "CARGENTO_HOME": self.tmp.name},
            check=False,
        )

    def post(self, payload: dict[str, Any], harness: str = "claude") -> dict[str, Any]:
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/events/{harness}",
            data=json.dumps(payload).encode(),
            headers={"X-Cargento-Capability": self.coordinator.capability(harness)},
        )
        with urllib.request.urlopen(request, timeout=2) as response:  # noqa: S310 — fixed loopback URL
            result: dict[str, Any] = json.loads(response.read())
            return result

    def test_every_literal_and_wrapper_reaches_only_fixed_reports_over_a_socket(self) -> None:
        for harness in ("claude", "codex"):
            for wrapper in ("", "rtk ", "rtk proxy "):
                for command, pattern in POSITIVES:
                    with self.subTest(harness=harness, wrapper=wrapper, command=command):
                        before = len(self.received)
                        proc = self.run_hook(native(wrapper + command), harness)
                        self.assertEqual((0, b"", b""), (proc.returncode, proc.stdout, proc.stderr))
                        self.assertEqual(before + 1, len(self.received))
                        report = self.received[-1]
                        self.assertEqual(set(wire()), set(report))
                        self.assertEqual(pattern, report["pattern_id"])
                        self.assertNotIn("private", json.dumps(report))
        served = json.loads(self.app.collect_json(show_all=False)[1])
        self.assertNotIn("private", json.dumps(served["command_reports"]))
        self.assertNotIn("private", str(self.coordinator._command_reports.__dict__))

    def test_ambiguous_malformed_and_oversized_calls_produce_no_report(self) -> None:
        malformed: tuple[Any, ...] = (*NEGATIVES, None, 2, [], {})
        payloads = [native(command) for command in malformed]
        payloads.extend(
            [
                native("git push --force", tool_name="exec_command"),
                native("git push --force", hook_event_name="PreToolUse"),
                native("git push --force", hook_event_name="PostToolUseFailure"),
                native("git push --force", tool_input="bad"),
                native("git push --force", session_id=""),
                native("git push --force", session_id="x" * 201),
            ]
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                proc = self.run_hook(payload)
                self.assertEqual((0, b"", b""), (proc.returncode, proc.stdout, proc.stderr))
        self.assertEqual([], self.received)
        self.assertEqual([], self.coordinator.command_reports())

    def test_recorded_harness_shapes_admit_only_the_measured_after_tool_field(self) -> None:
        for harness, filename in (
            ("claude", "command-shapes-2.1.270-macos.jsonl"),
            ("codex", "command-shapes-0.154.0-macos.jsonl"),
        ):
            records = [
                json.loads(line)
                for line in (ROOT / "docs/captures" / harness / filename).read_text().splitlines()
            ]
            for record in (row for row in records if row["tool"] == "Bash"):
                self.assertEqual("str", record["input_fields"]["command"])
                payload: dict[str, Any] = dict.fromkeys(record["keys"])
                payload.update(
                    hook_event_name=record["event"], tool_name=record["tool"], session_id=SESSION
                )
                payload["tool_input"] = dict.fromkeys(record["input_fields"], "private-description")
                payload["tool_input"]["command"] = "git push --force private-replay"
                before = len(self.received)
                proc = self.run_hook(payload, harness)
                self.assertEqual((0, b"", b""), (proc.returncode, proc.stdout, proc.stderr))
                self.assertEqual(before + int(record["event"] == "PostToolUse"), len(self.received))

    def test_no_events_publishes_no_enablement_and_no_reports(self) -> None:
        self.server.observation = None
        self.app.overlays = None
        lifecycle.write_state(self.config, self.port, started=NOW, capabilities=None)
        self.assertEqual(0, self.run_hook(native("git push --force")).returncode)
        self.assertEqual([], self.received)
        payload = self.app.collect(show_all=False)
        self.assertFalse(payload["irreversible_enabled"])
        self.assertNotIn("command_reports", payload)

    def test_forged_vocabulary_or_extra_private_fields_never_enter_the_ledger(self) -> None:
        for forged in (
            wire(pattern_id="private"),
            wire(tool_name="private"),
            wire(cwd="private"),
            wire(tool_input="private"),
            wire(timestamp="private"),
            wire(v=True),
            wire(pattern_id=[]),
            wire(tool_name={}),
            wire(timestamp=0),
        ):
            self.assertNotEqual("accepted", self.post(forged).get("outcome"))
        self.post(wire(), "gemini")
        self.assertEqual([], self.received)
        self.assertEqual([], self.coordinator.command_reports())

    def test_fresh_off_old_and_missing_state_never_enters_the_matcher(self) -> None:
        marker = Path(self.tmp.name, "matcher-entered")
        driver = (
            "from pathlib import Path; event_hook.irreversible_report = lambda *a: Path("
            + repr(str(marker))
            + ").write_text('entered')"
        )
        for enabled in (False, None, "missing"):
            if enabled == "missing":
                Path(self.tmp.name, f"cargento-{self.port}.json").unlink()
            else:
                assert enabled is None or isinstance(enabled, bool)
                self.write_state(enabled)
            proc = self.run_hook(native("git push --force"), driver=driver)
            self.assertEqual((0, b"", b""), (proc.returncode, proc.stdout, proc.stderr))
            self.assertFalse(marker.exists())
        self.assertEqual([], self.received)
        self.assertEqual(2, self.coordinator.counters.get("event.store_changed"))

    def test_sleep_and_spin_exit_the_actual_hook_without_late_publication(self) -> None:
        drivers = [
            "import time; event_hook.command_shape = lambda _: time.sleep(10)",
            "exec('def spin(_):\\n while True: pass'); event_hook.command_shape = spin",
        ]
        for driver in drivers:
            started = time.monotonic()
            proc = self.run_hook(native("git push --force"), driver=driver, timeout=0.25)
            self.assertLess(time.monotonic() - started, 0.25)
            self.assertEqual((0, b"", b""), (proc.returncode, proc.stdout, proc.stderr))
        self.assertEqual([], self.received)

    def test_a_gil_held_regex_remains_a_rejected_negative_control(self) -> None:
        driver = (
            "import re; event_hook.command_shape = lambda _: re.fullmatch('(a+)+$', 'a'*30+'!')"
        )
        with self.assertRaises(subprocess.TimeoutExpired):
            self.run_hook(native("git push --force"), driver=driver, timeout=0.25)
        self.assertEqual([], self.received)

    def test_duplicate_and_reordered_reports_survive_collection_and_end(self) -> None:
        self.post(wire())
        self.post(
            wire("git_hard_reset", timestamp=datetime.fromtimestamp(NOW - 10, UTC).isoformat())
        )
        self.post(wire())
        self.post({"v": 1, "event": "session_ended", "session_id": SESSION})
        self.coordinator._collect("event")
        payload = json.loads(self.app.collect_json(show_all=False)[1])
        reports = payload["command_reports"]
        self.assertEqual(
            ["git_force_push", "git_force_push", "git_hard_reset"],
            [r["pattern_id"] for r in reports],
        )
        self.assertEqual(reports, payload["sessions"][0]["command_reports"])
        self.assertEqual(NOW, payload["sessions"][0]["ended_at"])
        replacement = observation.Observation(self.app, clock=lambda: NOW)
        self.app.overlays = replacement
        self.assertEqual([], self.app.collect(show_all=False)["command_reports"])

    def test_an_off_replacement_rejects_a_report_even_with_its_current_capability(self) -> None:
        self.close_server()
        self.coordinator.config = dataclasses.replace(self.config, irreversible_enabled=False)
        self.app.config = self.coordinator.config
        self.coordinator = observation.Observation(self.app, clock=lambda: NOW)
        self.app.overlays = self.coordinator
        self.server = support.make_server(
            port=self.port, application=self.app, observation=self.coordinator
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )
        self.thread.start()
        self.write_state(False)
        self.assertEqual("disabled", self.post(wire())["outcome"])
        self.assertEqual([], self.received)
        payload = self.app.collect(show_all=False)
        self.assertFalse(payload["irreversible_enabled"])
        self.assertNotIn("command_reports", payload)
        self.assertIsNone(payload["sessions"][0]["command_reports"])


class CommandRetentionTest(unittest.TestCase):
    def test_caps_retain_newest_reports_and_expiry_removes_them(self) -> None:
        ledger = irreversible.Ledger()
        for n in range(1100):
            ledger.add(
                irreversible.Report("claude", str(n // 22), "git_force_push", "Bash", NOW + n, n),
                now=NOW + 1100,
            )
        reports = ledger.published(now=NOW + 1100)
        self.assertEqual(1000, len(reports))
        self.assertEqual(NOW + 1099, reports[0]["timestamp"])
        self.assertTrue(all(sum(r["sid"] == str(s) for r in reports) == 20 for s in range(50)))
        ledger.add(
            irreversible.Report("claude", "extra", "git_hard_reset", "Bash", NOW + 1200, 1200),
            now=NOW + 1200,
        )
        self.assertEqual(1000, len(ledger.published(now=NOW + 1200)))
        self.assertEqual([], ledger.published(now=NOW + 1200 + 86400))

    def test_respawn_keeps_off_and_the_atomic_state_publishes_the_effective_bit(self) -> None:
        for flags in ([], ["--no-irreversible"], ["--no-events"]):
            args = cli.build_parser().parse_args(flags)
            config, _ = cli.build_runtime(args, started=NOW)
            child = cli.build_parser().parse_args(lifecycle.spawn_argv(config, args)[2:])
            child_config, _ = cli.build_runtime(child, started=NOW)
            self.assertEqual(not flags, child_config.irreversible_enabled)
            with tempfile.TemporaryDirectory() as tmp:
                config = dataclasses.replace(config, state_home=tmp, state_dir=Path(tmp))
                lifecycle.write_state(config, 4553, started=NOW, capabilities={"claude": "test"})
                with patch.dict(os.environ, {"CARGENTO_HOME": tmp}):
                    self.assertEqual(
                        "test" if not flags else None,
                        event_hook.capability(4553, "claude", irreversible=True),
                    )


class CommandReportTest(unittest.TestCase):
    def test_a_matching_command_reduces_to_six_fixed_routing_fields(self) -> None:
        payload = {
            "hook_event_name": "PostToolUse",
            "session_id": SESSION,
            "tool_name": "Bash",
            "tool_input": {"command": "git push --force private-sentinel"},
            "tool_response": "private-output",
            "cwd": "private-directory",
        }
        report = event_hook.irreversible_report(payload, "claude")
        self.assertIsNotNone(report)
        assert report is not None
        self.assertEqual(
            {"v", "event", "session_id", "timestamp", "pattern_id", "tool_name"}, set(report)
        )
        self.assertEqual("git_force_push", report["pattern_id"])
        self.assertNotIn("private", str(report))

    def test_two_reports_survive_one_coalescing_window_and_session_end(self) -> None:
        coordinator = observation.Observation(
            FakeApplication(
                support.make_config(state_home=self.enterContext(tempfile.TemporaryDirectory()))
            ),  # type: ignore[arg-type]
            clock=lambda: NOW,
        )
        report = {
            "v": 1,
            "event": "command_shape_reported",
            "session_id": SESSION,
            "timestamp": "2023-11-14T22:13:20Z",
            "pattern_id": "git_force_push",
            "tool_name": "Bash",
        }
        self.assertEqual("accepted", coordinator.submit("claude", report))
        self.assertEqual("accepted", coordinator.submit("claude", report))
        coordinator.submit("claude", {"v": 1, "event": "session_ended", "session_id": SESSION})
        self.assertEqual(2, len(coordinator.command_reports()))


class CommandReportReaderTest(NextPageJsHarness):
    def test_the_cross_session_count_is_the_rendered_list_and_does_not_change_risk(self) -> None:
        out = self._run_page_js("""
__els.app = {innerHTML: ""};
nextData = {generated: 1700000000, irreversible_enabled: true, sessions: [
  {harness: "claude", sid: "one", project: "project", state: "idle"}
], command_reports: Array.from({length: 25}, (_, i) => ({harness: "claude", sid: "one",
  label: "force push", pattern_id: "git_force_push", tool_name: "Bash", timestamp: 1700000000 - i}))};
nextAttention = nextAttentionModel(nextData);
nextRoute = {view: "attention", project: null, session: null};
renderNext(); const html = __els.app.innerHTML;
console.log(JSON.stringify({html, risks: nextObserved(nextData).risks.length}));
""")
        assert isinstance(out, dict)
        self.assertEqual(0, out["risks"])
        self.assertEqual(20, out["html"].count("Command shape reported: force push"))
        self.assertIn("20 reports shown", out["html"])
        self.assertIn('data-next-route="session:project:claude:one"', out["html"])

    def rendered(
        self,
        *,
        enabled: bool = True,
        harness: str = "claude",
        reports: bool = True,
        view: str = "attention",
    ) -> str:
        report = {
            "harness": harness,
            "sid": "one",
            "pattern_id": "git_force_push",
            "label": "force push",
            "timestamp": NOW,
            "tool_name": "Bash",
        }
        data = {
            "generated": NOW,
            "irreversible_enabled": enabled,
            "command_reports": [report] if reports else [],
            "sessions": [
                {
                    "harness": harness,
                    "sid": "one",
                    "project": "project",
                    "state": "idle",
                    "command_reports": [report] if reports else [],
                }
            ],
        }
        out = self._run_page_js(
            '__els.app = {innerHTML: ""}; nextData = ' + json.dumps(data) + ";"
            "nextAttention = nextAttentionModel(nextData); nextRoute = "
            + json.dumps({"view": view, "project": "project", "harness": harness, "session": "one"})
            + "; renderNext(); console.log(JSON.stringify(__els.app.innerHTML));"
        )
        assert isinstance(out, str)
        return out

    def test_a_reader_sees_a_report_and_its_effect_limit_on_both_surfaces(self) -> None:
        for view in ("attention", "session"):
            html = self.rendered(view=view)
            self.assertIn("Command shape reported: force push", html)
            self.assertIn("A shape match does not prove the action succeeded.", html)
            self.assertIn("1 report", html)

    def test_a_reader_cannot_mistake_missing_reports_for_an_all_clear(self) -> None:
        for view in ("attention", "session"):
            self.assertIn(
                "No matching reports received; missing hooks and unmatched commands can look the same.",
                self.rendered(reports=False, view=view),
            )
            self.assertIn(
                "Command-shape reports are disabled for this run.",
                self.rendered(enabled=False, view=view),
            )
        self.assertIn(
            "Command-shape reporting is unsupported for this harness.",
            self.rendered(harness="gemini", reports=False, view="session"),
        )
