from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, ClassVar

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import capture_terminal_identity as recorder

ROOT = Path(__file__).resolve().parents[2]
CAPTURES = ROOT / "docs" / "captures"


class ShapeTest(unittest.TestCase):
    def test_a_device_is_recorded_as_a_shape_and_never_as_the_device(self) -> None:
        # The whole privacy property for this recorder. A tty device names one
        # terminal on one machine; its shape names none.
        # Falsified by: any digit surviving into the shape.
        self.assertEqual("ttys###", recorder.shape("ttys006"))
        shaped = recorder.shape("/dev/ttys006")
        self.assertEqual("ttys###", shaped)
        self.assertNotIn("006", shaped or "")

    def test_a_hex_identifier_is_masked_whole(self) -> None:
        # A session id is hex, so masking only the digits would leave half of it
        # readable. Every hex character inside a digit-bearing run goes.
        # Falsified by: a letter of a UUID surviving.
        shaped = recorder.shape("9CA2A0AB-1F3D-4E5A-8B7C-D0E1F2A3B4C5")
        self.assertEqual("########-####-####-####-############", shaped)

    def test_a_pane_name_keeps_its_punctuation(self) -> None:
        # `%3` is what tells a reader this is a tmux pane handle at all.
        self.assertEqual("%#", recorder.shape("%3"))

    def test_a_word_with_no_digits_survives(self) -> None:
        # A shape that erased every name would answer no question.
        self.assertEqual("Apple_Terminal", recorder.shape("Apple_Terminal"))
        self.assertEqual("tmux", recorder.shape("tmux"))

    def test_an_absent_reading_shapes_to_nothing(self) -> None:
        self.assertIsNone(recorder.shape(None))
        self.assertIsNone(recorder.shape(""))
        # `ps` writes `??` for a process with no controlling terminal on macOS
        # and `?` on Linux. Both are an absence, not a device, and neither may
        # read as a shape -- the suite runs on three platforms.
        self.assertIsNone(recorder.shape("??"))
        self.assertIsNone(recorder.shape("?"))


class EnvironmentTest(unittest.TestCase):
    ENVIRON: ClassVar[dict[str, str]] = {
        "TMUX": "/private/tmp/tmux-501/drc4382,59500,0",
        "TMUX_PANE": "%3",
        "TERM_PROGRAM": "Apple_Terminal",
        "TERM_SESSION_ID": "9CA2A0AB-1F3D-4E5A-8B7C-D0E1F2A3B4C5",
        "WINDOWID": "12345",
    }

    def test_a_variable_is_recorded_as_presence_and_shape_only(self) -> None:
        # Falsified by: the socket path, which names a user's temp directory,
        # reaching the record.
        seen = recorder.environment(self.ENVIRON)
        self.assertTrue(seen["multiplexer"]["TMUX"]["present"])
        self.assertNotIn("501", json.dumps(seen))
        self.assertNotIn("tmux-501", json.dumps(seen))
        self.assertEqual("%#", seen["multiplexer"]["TMUX_PANE"]["shape"])

    def test_an_absent_variable_is_recorded_as_absent_rather_than_dropped(self) -> None:
        # A name that never appears cannot be told from one this build stopped
        # sending unless the absent case is written down.
        seen = recorder.environment({})
        for name in recorder.EMULATOR_VARS:
            with self.subTest(variable=name):
                self.assertIn(name, seen["emulator"]["vars"])
                self.assertFalse(seen["emulator"]["vars"][name]["present"])
                self.assertIsNone(seen["emulator"]["vars"][name]["shape"])

    def test_the_term_program_value_is_kept_and_no_other_value_is(self) -> None:
        # `TERM_PROGRAM` is a vendor vocabulary word, on the reasoning the
        # captures README gives for `notification_type`. Its neighbours are not.
        seen = recorder.environment(self.ENVIRON)
        self.assertEqual("Apple_Terminal", seen["emulator"]["TERM_PROGRAM_value"])
        self.assertNotIn("9CA2A0AB", json.dumps(seen))
        self.assertEqual(
            "########-####-####-####-############",
            seen["emulator"]["vars"]["TERM_SESSION_ID"]["shape"],
        )

    def test_an_unknown_term_program_is_not_written_through_unbounded(self) -> None:
        # The value is trusted as a vocabulary word, so it is bounded like the
        # tool name in `capture_hook.py` rather than copied whole.
        seen = recorder.environment({"TERM_PROGRAM": "x" * 500})
        self.assertLessEqual(len(seen["emulator"]["TERM_PROGRAM_value"]), recorder.MAX_TOKEN_CHARS)


class AncestryTest(unittest.TestCase):
    # One `ps` reading per process, in the shape the recorder parses.
    TERMINAL_ARM: ClassVar[list[dict[str, Any]]] = [
        {
            "pid": 100,
            "ppid": 101,
            "ucomm": "python3.12",
            "comm": "/Users/someone/bin",
            "tty": "ttys006",
        },
        {
            "pid": 101,
            "ppid": 102,
            "ucomm": "2.1.261",
            "comm": "/opt/homebrew/bin/claude",
            "tty": "ttys006",
        },
        {"pid": 102, "ppid": 103, "ucomm": "bash", "comm": "/bin/bash", "tty": "ttys006"},
        {"pid": 103, "ppid": 1, "ucomm": "login", "comm": "/usr/bin/login", "tty": "ttys006"},
        {"pid": 1, "ppid": 0, "ucomm": "launchd", "comm": "/sbin/launchd", "tty": "??"},
    ]

    def test_an_ancestor_is_recorded_by_name_and_never_by_its_path(self) -> None:
        # `ps -o comm=` is a PATH truncated to 16 characters, so its basename can
        # be a username. The record carries the accounting name instead.
        # Falsified by: `someone` appearing anywhere in the chain.
        chain = recorder.walk(self.TERMINAL_ARM, harness="claude")
        self.assertNotIn("someone", json.dumps(chain))
        self.assertEqual(
            ["recorder", "harness", "shell", "login", "init"], [n["role"] for n in chain]
        )

    def test_the_harness_is_found_by_depth(self) -> None:
        # The question B5 asks first: is the harness reachable from the hook at
        # all, and how far up.
        chain = recorder.walk(self.TERMINAL_ARM, harness="claude")
        found = recorder.ancestry(chain)
        self.assertTrue(found["reached_harness"])
        self.assertEqual(1, found["depth_to_harness"])
        self.assertEqual("ttys###", found["harness_tty"])

    def test_a_version_string_is_not_read_as_a_name(self) -> None:
        # `ps -o ucomm=` reports this harness as its own version number, so the
        # role has to come from the executable rather than from the name.
        chain = recorder.walk(self.TERMINAL_ARM, harness="claude")
        self.assertEqual("#.#.###", chain[1]["name"])
        self.assertEqual("harness", chain[1]["role"])

    def test_a_terminal_inherited_from_the_launcher_is_not_the_harness_terminal(self) -> None:
        # THE CONTROL. A harness started in its own session has no terminal, but
        # the ppid chain still climbs into whatever launched it -- here a second
        # harness sitting in a real tab. A reader that takes the first ancestor
        # with a tty gets a terminal that belongs to somebody else, so the record
        # keeps the two apart.
        # Falsified by: `harness_tty` reporting the launcher's device.
        detached = [
            {"pid": 200, "ppid": 201, "ucomm": "python3.12", "comm": "/x/python3.12", "tty": "??"},
            {
                "pid": 201,
                "ppid": 202,
                "ucomm": "2.1.261",
                "comm": "/opt/homebrew/bin/claude",
                "tty": "??",
            },
            {"pid": 202, "ppid": 203, "ucomm": "bash", "comm": "/bin/bash", "tty": "??"},
            {
                "pid": 203,
                "ppid": 1,
                "ucomm": "2.1.260",
                "comm": "/opt/homebrew/bin/claude",
                "tty": "ttys001",
            },
            {"pid": 1, "ppid": 0, "ucomm": "launchd", "comm": "/sbin/launchd", "tty": "??"},
        ]
        found = recorder.ancestry(recorder.walk(detached, harness="claude"))
        self.assertTrue(found["reached_harness"])
        self.assertIsNone(found["harness_tty"])
        self.assertEqual(3, found["first_ancestor_with_a_tty_depth"])
        self.assertTrue(found["a_terminal_is_reachable_past_the_harness"])

    def test_a_multiplexer_is_recorded_as_a_role(self) -> None:
        # In a pane the chain stops at the tmux server, and the emulator is not
        # in it at all. That difference is the arm's whole signature.
        pane = [
            {
                "pid": 300,
                "ppid": 301,
                "ucomm": "python3.12",
                "comm": "/x/python3.12",
                "tty": "ttys008",
            },
            {
                "pid": 301,
                "ppid": 302,
                "ucomm": "2.1.261",
                "comm": "/opt/homebrew/bin/claude",
                "tty": "ttys008",
            },
            {"pid": 302, "ppid": 1, "ucomm": "tmux", "comm": "/opt/homebrew/bin/tmux", "tty": "??"},
            {"pid": 1, "ppid": 0, "ucomm": "launchd", "comm": "/sbin/launchd", "tty": "??"},
        ]
        found = recorder.ancestry(recorder.walk(pane, harness="claude"))
        self.assertTrue(found["reached_multiplexer"])
        self.assertFalse(found["reached_emulator"])
        self.assertEqual(2, found["depth_to_multiplexer"])

    def test_a_cycle_or_a_missing_parent_stops_the_walk(self) -> None:
        # `ps` is read from a live machine, so the recorder cannot assume the
        # chain terminates.
        looped = [
            {"pid": 400, "ppid": 401, "ucomm": "python3.12", "comm": "/x/python3.12", "tty": "??"},
            {"pid": 401, "ppid": 400, "ucomm": "bash", "comm": "/bin/bash", "tty": "??"},
        ]
        self.assertEqual(2, len(recorder.walk(looped, harness="claude")))


class ObserveTest(unittest.TestCase):
    PAYLOAD: ClassVar[dict[str, Any]] = {
        "session_id": "abcd1234-0000-4000-8000-000000000000",
        "hook_event_name": "SessionStart",
        "cwd": "/Users/someone/secret-project",
        "transcript_path": "/Users/someone/.claude/projects/x/y.jsonl",
        "prompt": "a prompt nobody should see",
    }
    PROBE: ClassVar[dict[str, Any]] = {
        "fd_tty": {"0": None, "1": None, "2": None},
        "ps_tty": "ttys006",
        "dev_tty_open": True,
        "tmux_client_tty": None,
        "tmux_pane_tty": None,
        "emulator_lookup": {
            "method": "terminal_app_applescript_tty",
            "tabs_matching_harness_tty": 1,
            "busy_tabs_matching_harness_tty": 1,
            "tabs_matching_tmux_client_tty": None,
            "busy_tabs_matching_tmux_client_tty": None,
        },
    }

    def record(self, **over: Any) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "payload": self.PAYLOAD,
            "harness": "claude",
            "arm": "terminal_app",
            "environ": EnvironmentTest.ENVIRON,
            "processes": AncestryTest.TERMINAL_ARM,
            "probe": self.PROBE,
            "elapsed_ms": 11.5,
            "harness_version": "2.1.261",
            "at": "2026-09-05T00:00:00Z",
        }
        kwargs.update(over)
        return recorder.observe(**kwargs)

    def test_a_record_carries_no_payload_value_but_the_session_prefix(self) -> None:
        # The rule this whole directory exists for.
        # Falsified by: a prompt, a cwd or a transcript path in the bytes.
        blob = json.dumps(self.record())
        for secret in ("a prompt nobody should see", "secret-project", "someone", ".jsonl"):
            with self.subTest(secret=secret):
                self.assertNotIn(secret, blob)
        self.assertEqual("abcd1234", self.record()["session"])

    def test_a_record_carries_the_key_set_the_verdict_reads(self) -> None:
        # An arm missing a key passes a reproduction check that reads arms as
        # given data, which is how a sibling capture shipped five missing keys.
        self.assertEqual(recorder.ARM_KEYS, frozenset(self.record()))

    def test_no_device_reaches_the_record(self) -> None:
        probe = dict(self.PROBE, ps_tty="/dev/ttys006", tmux_pane_tty="/dev/ttys008")
        blob = json.dumps(self.record(probe=probe))
        self.assertNotIn("/dev/", blob)
        self.assertNotIn("006", blob)

    def test_the_agreement_between_two_readings_is_computed_and_not_asserted(self) -> None:
        # Two ways of asking the same question, and the record says whether they
        # answered the same. Shapes agree here because both are `ttysNNN`; the
        # comparison is made on the raw readings before they are shaped, or it
        # would be true by construction.
        agreeing = self.record()["tty"]
        self.assertTrue(agreeing["harness_tty_agrees_with_hook_ps_tty"])
        moved = [dict(row) for row in AncestryTest.TERMINAL_ARM]
        moved[1]["tty"] = "ttys009"
        self.assertFalse(self.record(processes=moved)["tty"]["harness_tty_agrees_with_hook_ps_tty"])

    def test_a_hook_stdin_without_a_terminal_is_recorded_as_such(self) -> None:
        # `os.ttyname(0)` is the reading the issue names first, and a hook's fd 0
        # is the payload pipe. The record must be able to say so.
        self.assertIsNone(self.record()["tty"]["hook_fd0"])


class TerminalLookupTest(unittest.TestCase):
    def test_the_lookup_asks_for_the_device_terminal_app_actually_reports(self) -> None:
        # Measured, not assumed: Terminal.app's `tty` property is the full device
        # path, and the same query against the bare name returns 0 tabs rather
        # than an error -- a clean, wrong negative.
        # Falsified by: a query that omits the `/dev/` prefix.
        self.assertIn('"/dev/ttys006"', recorder.tab_query("ttys006"))
        self.assertIn('"/dev/ttys006"', recorder.tab_query("/dev/ttys006"))

    def test_the_lookup_counts_tabs_rather_than_windows(self) -> None:
        # Measured, and it changed an answer. `every tab of every window whose
        # tty is X` binds the filter to the WINDOW and then counts all of its
        # tabs, so a two-tab window answered 2 for a device only one tab sits on.
        # A tty names one tab, so the count has to be taken per tab.
        # Falsified by: a query whose `whose` clause selects windows.
        query = recorder.tab_query("ttys006")
        self.assertIn("tabs of", query)
        self.assertNotIn("window whose", query)

    def test_both_candidate_devices_are_looked_up(self) -> None:
        # In a pane the harness's tty is a pty tmux made, and no Terminal tab
        # sits on it. If only that one were looked up, the arm would read as a
        # flat negative when a second identifier does find the window.
        # Falsified by: a lookup that asks about one device.
        counted = {"tabs": 7, "busy_tabs": 3}
        found = recorder.lookup(
            harness_tty="ttys006", client_tty="ttys004", count=lambda _device: counted
        )
        self.assertEqual(7, found["tabs_matching_harness_tty"])
        self.assertEqual(7, found["tabs_matching_tmux_client_tty"])
        absent = recorder.lookup(harness_tty=None, client_tty=None, count=lambda _device: counted)
        self.assertIsNone(absent["tabs_matching_harness_tty"])
        self.assertIsNone(absent["tabs_matching_tmux_client_tty"])

    def test_a_stale_tab_is_counted_separately_from_a_live_one(self) -> None:
        # Measured, and it is the caveat a raise would ship without: two dead
        # tabs both reported `/dev/ttys004` because macOS recycles the device and
        # a finished tab keeps the string. A count that did not separate live
        # from stale would say a tty names one window when it named three.
        # Falsified by: a lookup carrying only a total.
        found = recorder.lookup(
            harness_tty="ttys006",
            client_tty=None,
            count=lambda _device: {"tabs": 3, "busy_tabs": 1},
        )
        self.assertEqual(3, found["tabs_matching_harness_tty"])
        self.assertEqual(1, found["busy_tabs_matching_harness_tty"])

    def test_a_quoted_device_cannot_close_the_script(self) -> None:
        # The device is read off `ps`, so it is not trusted to be a device.
        self.assertNotIn('""', recorder.tab_query('ttys0"6'))


class VerdictTest(unittest.TestCase):
    def arm(self, **over: Any) -> dict[str, Any]:
        base = ObserveTest().record()
        for key, value in over.items():
            base[key] = value
        return base

    def test_a_verdict_is_derived_from_the_arms_rather_than_declared(self) -> None:
        arms = [self.arm()]
        found = recorder.verdict(arms, base=recorder.base_of(arms[0]))
        self.assertEqual("terminal_identity_verdict", found["record"])
        self.assertEqual(1, found["invocations"])
        self.assertEqual(["terminal_app"], sorted(found["per_arm"]))

    def test_an_identifier_that_moved_between_invocations_is_reported_unstable(self) -> None:
        # THE PROPERTY A RAISE DEPENDS ON. One reading cannot establish it, so
        # the verdict is computed across invocations of one session.
        # Falsified by: a moving device reported as held still.
        first = self.arm()
        second = json.loads(json.dumps(first))
        second["tty"]["hook_ps_tty"] = "ttyq###"
        found = recorder.verdict([first, second], base=recorder.base_of(first))
        held = found["per_arm"]["terminal_app"]["identifier_held_still"]
        self.assertFalse(held["hook_ps_tty"])
        self.assertTrue(held["TERM_PROGRAM"])

    def test_an_identifier_that_was_never_there_did_not_hold_still(self) -> None:
        # A composed verdict fails toward a confident green: an identifier absent
        # from every reading compares equal to itself, so a naive stability check
        # reports the most useless field in the file as the most reliable one.
        # Falsified by: `true` for an identifier no arm ever saw.
        first = self.arm()
        first["multiplexer"]["TMUX_PANE"] = {"present": False, "shape": None}
        second = json.loads(json.dumps(first))
        found = recorder.verdict([first, second], base=recorder.base_of(first))
        held = found["per_arm"]["terminal_app"]["identifier_held_still"]
        self.assertIsNone(held["TMUX_PANE"])
        self.assertTrue(held["TERM_PROGRAM"])

    def test_the_launcher_trap_is_carried_into_the_verdict(self) -> None:
        # The control's whole finding, and it has to be readable without opening
        # the arms: in the detached arm a terminal IS reachable, just not this
        # session's, so a summary that only said "no terminal" would understate
        # what a naive reader would do here.
        blind = json.loads(json.dumps(self.arm(arm="no_controlling_terminal")))
        blind["tty"]["harness_tty"] = None
        blind["tty"]["hook_ps_tty"] = None
        blind["ancestry"]["a_terminal_is_reachable_past_the_harness"] = True
        found = recorder.verdict([blind], base=recorder.base_of(blind))
        summary = found["per_arm"]["no_controlling_terminal"]
        self.assertEqual("none", summary["locates_a_terminal_by"])
        self.assertTrue(summary["a_terminal_is_reachable_past_the_harness"])

    def test_stability_is_not_claimed_from_a_single_invocation(self) -> None:
        found = recorder.verdict([self.arm()], base=recorder.base_of(self.arm()))
        held = found["per_arm"]["terminal_app"]["identifier_held_still"]
        self.assertIsNone(held["hook_ps_tty"])
        self.assertEqual(1, found["per_arm"]["terminal_app"]["invocations"])

    def test_the_verdict_names_which_launch_modes_the_arm_covers(self) -> None:
        # A print-mode reading and an interactive one are not the same session
        # shape, and a raise is for an interactive session. An arm measured only
        # headless has to be visible as such rather than read as both.
        # Falsified by: an arm summary that cannot say which modes it saw.
        found = recorder.verdict(
            [self.arm(), self.arm(mode="interactive")], base=recorder.base_of(self.arm())
        )
        self.assertEqual(["interactive", "print"], found["per_arm"]["terminal_app"]["modes"])

    def test_an_arm_with_no_terminal_locates_nothing(self) -> None:
        # The control has to read differently or the instrument proves nothing.
        blind = json.loads(json.dumps(self.arm(arm="no_controlling_terminal")))
        blind["tty"]["hook_ps_tty"] = None
        blind["tty"]["harness_tty"] = None
        blind["emulator"]["vars"]["TERM_PROGRAM"] = {"present": False, "shape": None}
        blind["emulator"]["TERM_PROGRAM_value"] = None
        found = recorder.verdict([blind], base=recorder.base_of(blind))
        self.assertEqual(
            "none", found["per_arm"]["no_controlling_terminal"]["locates_a_terminal_by"]
        )

    def test_a_tmux_pane_locates_the_pane_and_says_so(self) -> None:
        pane = json.loads(json.dumps(self.arm(arm="tmux")))
        pane["multiplexer"]["TMUX"] = {"present": True, "shape": None}
        pane["multiplexer"]["TMUX_PANE"] = {"present": True, "shape": "%#"}
        found = recorder.verdict([pane], base=recorder.base_of(pane))
        self.assertEqual("tty+tmux_pane", found["per_arm"]["tmux"]["locates_a_terminal_by"])


class CommittedCaptureTest(unittest.TestCase):
    """The files this recorder was written to produce, held to their own claims."""

    GLOBS: ClassVar[tuple[str, ...]] = (
        "claude/terminal-identity-*.jsonl",
        "codex/terminal-identity-*.jsonl",
    )
    NAMES: ClassVar[frozenset[str]] = frozenset(
        {"bash", "zsh", "sh", "login", "launchd", "tmux", "Terminal", "claude", "codex", "node"}
    )
    TOKENS: ClassVar[frozenset[str]] = frozenset(
        {
            "terminal_identity",
            "terminal_identity_verdict",
            "claude",
            "codex",
            "darwin",
            "terminal_app",
            "tmux",
            "no_controlling_terminal",
            "recorder",
            "harness",
            "multiplexer",
            "emulator",
            "shell",
            "login",
            "init",
            "other",
            "SessionStart",
            "UserPromptSubmit",
            "Stop",
            "PreToolUse",
            "PostToolUse",
            "SessionEnd",
            "TaskCompleted",
            "Apple_Terminal",
            "tty",
            "tty+tmux_pane",
            "none",
            "terminal_app_applescript_tty",
            "a_terminal_is_locatable",
            "no_terminal_is_locatable",
            "print",
            "interactive",
        }
    )
    PATTERNS: ClassVar[tuple[re.Pattern[str], ...]] = (
        re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"),
        re.compile(r"^[0-9a-f]{8}$"),
        re.compile(r"^\d+\.\d+\.\d+$"),
        # A shape, and the point of the class is what it EXCLUDES: no digit
        # survives masking, and no "/" means no path can pass as one.
        re.compile(r"^[A-Za-z_%+-]*#[#A-Za-z_%+.-]*$"),
        re.compile(r"^[A-Z_]{3,24}$"),  # an environment variable name
    )

    def files(self) -> list[Path]:
        found: list[Path] = []
        for pattern in self.GLOBS:
            matched = sorted(CAPTURES.glob(pattern))
            self.assertTrue(matched, f"{pattern} must match at least one capture")
            found += matched
        return found

    def records(self, path: Path) -> list[dict[str, Any]]:
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    @classmethod
    def strings(cls, node: Any, trail: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], str]]:
        if isinstance(node, dict):
            out: list[tuple[tuple[str, ...], str]] = []
            for key, value in node.items():
                out.append(((*trail, "<key>"), str(key)))
                out += cls.strings(value, (*trail, str(key)))
            return out
        if isinstance(node, list):
            return [pair for value in node for pair in cls.strings(value, trail)]
        return [(trail, node)] if isinstance(node, str) else []

    def test_every_string_in_a_capture_is_classified(self) -> None:
        # A positive vocabulary, for the reason the teammate captures give: a
        # device path and a shape are the same length, so a bound cannot tell
        # them apart and only enumeration can.
        # Falsified by: any string nobody has classified -- a path, a device, a
        # session id, a socket.
        unclassified = sorted(
            {
                text
                for path in self.files()
                for record in self.records(path)
                for _trail, text in self.strings(record)
                if not (
                    text in self.NAMES
                    or text in self.TOKENS
                    or text in recorder.ARM_KEYS
                    or text in recorder.VERDICT_KEYS
                    or text in recorder.RECORD_FIELD_NAMES
                    or any(p.match(text) for p in self.PATTERNS)
                )
            }
        )
        self.assertEqual([], unclassified, "unclassified strings in a capture file")

    def test_every_arm_carries_the_key_set_the_recorder_writes(self) -> None:
        # The reproduction below reads arms as given data, so it passes over an
        # arm that is missing keys. This is the check that does not.
        for path in self.files():
            for record in self.records(path):
                if record["record"] != recorder.RECORD_ARM:
                    continue
                with self.subTest(file=path.name, arm=record["arm"]):
                    self.assertEqual(recorder.ARM_KEYS, frozenset(record))

    def test_the_committed_verdict_is_reproduced_from_the_committed_arms(self) -> None:
        # Nothing in an evidence file may be a number a person typed.
        # Falsified by: a verdict field the recorder computes differently.
        for path in self.files():
            records = self.records(path)
            arms = [r for r in records if r["record"] == recorder.RECORD_ARM]
            committed = [r for r in records if r["record"] == recorder.RECORD_VERDICT]
            with self.subTest(file=path.name):
                self.assertEqual(1, len(committed))
                base = {k: committed[0][k] for k in recorder.BASE_KEYS}
                self.assertEqual(committed[0], recorder.verdict(arms, base=base))

    def test_the_control_arm_is_present_and_reads_negative(self) -> None:
        # An arm whose answer should be different is what makes the positives
        # worth anything.
        # Falsified by: a capture with only arms that found a terminal.
        for path in self.files():
            per_arm = next(r for r in self.records(path) if r["record"] == recorder.RECORD_VERDICT)[
                "per_arm"
            ]
            with self.subTest(file=path.name):
                self.assertIn("no_controlling_terminal", per_arm)
                self.assertEqual(
                    "none", per_arm["no_controlling_terminal"]["locates_a_terminal_by"]
                )
                self.assertTrue(
                    {a for a, v in per_arm.items() if v["locates_a_terminal_by"] != "none"},
                    "a capture of only negatives measures the instrument",
                )

    def test_stability_was_measured_over_more_than_one_invocation(self) -> None:
        # Two or more invocations per arm, or the file cannot speak to the
        # property a raise depends on.
        for path in self.files():
            per_arm = next(r for r in self.records(path) if r["record"] == recorder.RECORD_VERDICT)[
                "per_arm"
            ]
            for arm, found in per_arm.items():
                with self.subTest(file=path.name, arm=arm):
                    self.assertGreaterEqual(found["invocations"], 2)

    def test_the_recorder_cannot_reach_the_network(self) -> None:
        # The user has a Cargento running, and a recorder that posted to it
        # would contaminate the thing being measured.
        source = (ROOT / "scripts" / "capture_terminal_identity.py").read_text(encoding="utf-8")
        for banned in ("import socket", "import urllib", "import http", "requests"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, source)


class ReRunnableTest(unittest.TestCase):
    def test_the_recorder_appends_a_line_per_invocation_and_exits_zero(self) -> None:
        # A capture nobody can reproduce is an assertion. Running it twice must
        # leave two records and disturb no session.
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "capture.jsonl"
            for _ in range(2):
                done = subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "scripts" / "capture_terminal_identity.py"),
                        "claude",
                        "--arm",
                        "terminal_app",
                        "--out",
                        str(out),
                    ],
                    input=json.dumps(ObserveTest.PAYLOAD),
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                self.assertEqual(0, done.returncode, done.stderr)
            written = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(2, len(written))
            self.assertEqual(recorder.ARM_KEYS, frozenset(written[0]))

    def test_a_broken_payload_still_exits_zero(self) -> None:
        # A hook that fails is felt by the human in the session.
        with tempfile.TemporaryDirectory() as tmp:
            done = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "capture_terminal_identity.py"),
                    "claude",
                    "--arm",
                    "terminal_app",
                    "--out",
                    str(Path(tmp) / "capture.jsonl"),
                ],
                input="not json at all",
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertEqual(0, done.returncode, done.stderr)


if __name__ == "__main__":
    unittest.main()
