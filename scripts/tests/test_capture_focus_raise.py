from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import capture_focus_raise as recorder
import capture_terminal_identity as identity

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "capture_focus_raise.py"

if TYPE_CHECKING:
    from collections.abc import Sequence


class Spy:
    """An executor that records what it was asked to run and runs nothing.

    Every test that exercises an arm uses one. A recorder whose arms are only
    reachable on a machine with a particular arrangement is a recorder nobody
    checks, and this one must never move a window from a test.
    """

    def __init__(self, code: int = 0, codes: Sequence[int] = ()) -> None:
        self.calls: list[list[str]] = []
        self.code = code
        # A status per call, for the arms that run more than one command and
        # need them to differ: A2's launcher has to succeed for its quit step to
        # be reached at all, so one status for the whole arm cannot express
        # "the launcher opened and the close found nothing".
        self.codes = list(codes)

    def __call__(self, argv: Sequence[str], allowed: bool) -> int:
        if not allowed:
            raise AssertionError("an arm command was reached without its flag")
        self.calls.append(list(argv))
        if self.codes:
            return self.codes[min(len(self.calls), len(self.codes)) - 1]
        return self.code


class SpawnSpy:
    """The second seam. A4 starts its process through `posix_spawn`, not through
    the executor, and until this existed the suite spawned three real raises
    while every `Spy` in it reported nothing had run."""

    def __init__(self, pid: int = 4242, code: int = 0) -> None:
        self.calls: list[list[str]] = []
        self.pid = pid
        self.code = code

    def __call__(self, argv: Sequence[str], allowed: bool) -> tuple[int | None, int]:
        if not allowed:
            raise AssertionError("a disclaimed spawn was reached without its flag")
        self.calls.append(list(argv))
        return self.pid, self.code


def readers(
    *,
    frontmost: str | None = "com.google.Chrome",
    selected: str | None = "ttys006",
    clients: tuple[str, ...] = ("ttys004",),
    panes: tuple[str, ...] = ("%1", "%2"),
    tabs: dict[str, int] | None = None,
    responsible: int | None = 48170,
    name: str | None = "Terminal",
) -> recorder.Readers:
    """A whole machine's readings, as data.

    `frontmost` defaults to something that is not a subject of any arm, because
    that is the honest common case: the operator is looking at a browser.
    """
    counts = tabs if tabs is not None else {"tabs": 1, "busy_tabs": 1}
    state: dict[str, str | None] = {"selected": selected}

    def terminal_selected() -> str | None:
        return state["selected"]

    return recorder.Readers(
        frontmost=lambda: frontmost,
        terminal_selected=terminal_selected,
        tmux_selected=lambda _socket, client: state["selected"] if client else None,
        tmux_clients=lambda _socket: [{"tty": tty} for tty in clients],
        tmux_panes=lambda _socket: list(panes),
        terminal_tabs=lambda _device: dict(counts),
        responsible=lambda _pid: responsible,
        name_of=lambda pid: name if pid is not None else None,
    )


def patch_devices(case: unittest.TestCase, devices: tuple[str, ...]) -> None:
    """Stand in for the one Apple Event that lists every tab's device."""
    patcher = unittest.mock.patch.object(recorder, "_terminal_devices", lambda _r: list(devices))
    patcher.start()
    case.addCleanup(patcher.stop)


def mark_moved(record: dict[str, Any]) -> dict[str, Any]:
    """A record that moved, on the axis this arm's move would show up on.

    Both `moved` and `changed`, never one alone: the two are derived from the
    same pair of raw readings, so a record carrying one without the other is a
    shape `run_arm` cannot produce. It matters more since the verdict credits
    movement to a mechanism by reading WHICH axis changed -- a test that set
    `moved` alone would be handing the composer a shape no machine can.
    """
    on_screen = record["selected"]["source"] == recorder.SOURCE_NONE
    record["frontmost"]["changed"] = on_screen
    record["selected"]["changed"] = not on_screen
    record["moved"] = True
    record["outcome"] = recorder.outcome_of(record)
    return record


def mark_still(record: dict[str, Any]) -> dict[str, Any]:
    """The other half of `mark_moved`: nothing changed on either axis."""
    record["frontmost"]["changed"] = False
    record["selected"]["changed"] = False
    record["moved"] = False
    record["outcome"] = recorder.outcome_of(record)
    return record


class WaitSpy:
    """The handshake seam. A2 hands off to a daemon this suite must never start.

    Returns a canned payload per handshake suffix and records what was waited
    for, so a test can drive the whole four-phase orchestration -- launcher,
    handshake, quit, raise -- without a fork, a window or a real poll.
    """

    def __init__(self, **payloads: dict[str, Any] | None) -> None:
        self.waited: list[str] = []
        self.payloads = payloads

    def __call__(self, path: str) -> dict[str, Any] | None:
        self.waited.append(path)
        return self.payloads.get(path.rsplit(".", 1)[-1])


class ArmTableTest(unittest.TestCase):
    def test_every_arm_the_issue_names_is_implemented(self) -> None:
        # The arm list is the deliverable. An arm quietly absent is the failure
        # mode a reproduction test cannot see, because it only reads what is
        # there.
        # Falsified by: a missing arm.
        self.assertEqual(
            ["a0", "a1", "a2", "a3", "a4", "a5", "a6", "a7", "a8", "a9"],
            sorted(recorder.ARMS_BY_ID),
        )

    def test_the_negative_control_runs_first(self) -> None:
        # A control that runs after the positives cannot make them mean
        # anything: by then the instrument has already been trusted.
        self.assertEqual("a8", recorder.ARMS[0].id)
        self.assertEqual(recorder.EXPECT_HOLD, recorder.ARMS[0].expectation)

    def test_every_arm_that_writes_a_durable_grant_says_so(self) -> None:
        # A reader deciding whether to authorise an arm needs its cost before,
        # not after. A3 writes a TCC grant reversible only with `tccutil`.
        # Falsified by: an Apple Event arm with no side effect named.
        for arm in recorder.ARMS:
            uses_apple_events = any(
                "osascript" in " ".join(step["argv"])
                for step in recorder.plan(arm, recorder.Targets())
            )
            with self.subTest(arm=arm.id):
                if uses_apple_events and arm.expectation == recorder.EXPECT_MOVE:
                    self.assertIsNotNone(arm.durable_side_effect)
        self.assertIn(
            "tccutil reset AppleEvents", recorder.ARMS_BY_ID["a3"].durable_side_effect or ""
        )

    def test_the_cross_app_arm_targets_finder_rather_than_an_absent_emulator(self) -> None:
        # iTerm2 is not installed on the machine that takes this capture, so an
        # arm aimed at it would record a failure of the machine as a failure of
        # the mechanism. Finder is not the daemon's responsible process either,
        # which is the property the arm actually needs.
        arm = recorder.ARMS_BY_ID["a3"]
        self.assertEqual("Finder", arm.target_app)
        self.assertIn("Finder", " ".join(recorder.plan(arm, recorder.Targets())[0]["argv"]))

    def test_the_wrong_socket_control_omits_the_socket_flag(self) -> None:
        # A9's whole content. If `-L` survived, it would be A5 under another
        # name and would read as a second positive.
        # Falsified by: `-L` in A9's argv.
        targets = recorder.Targets(client="ttys004", pane="%2")
        a9 = recorder.plan(recorder.ARMS_BY_ID["a9"], targets)[0]["argv"]
        a5 = recorder.plan(recorder.ARMS_BY_ID["a5"], targets)[0]["argv"]
        self.assertNotIn("-L", a9)
        self.assertIn("-L", a5)
        self.assertEqual([w for w in a5 if w not in {"-L", recorder.TMUX_SOCKET}], a9)

    def test_the_socket_and_session_are_minted_here_rather_than_taken_from_a_flag(self) -> None:
        # An operator's own socket label can be a project name, and a name in an
        # argv is a name in the record. Minting removes the string rather than
        # redacting it.
        self.assertEqual("cargento-raise", recorder.TMUX_SOCKET)
        argv = recorder.plan(recorder.ARMS_BY_ID["a5"], recorder.Targets(client="c", pane="%1"))
        self.assertIn(recorder.TMUX_SOCKET, argv[0]["argv"])


class AuthorizationTest(unittest.TestCase):
    """No arm runs without its own flag. The hard rule, from four directions."""

    def test_the_executor_refuses_without_the_flag(self) -> None:
        # The single gate. Every path that could move a window comes through
        # here.
        # Falsified by: a command running on `allowed=False`.
        with self.assertRaises(recorder.RefusedError):
            recorder._execute(["/usr/bin/osascript", "-e", "beep"], allowed=False)

    def test_an_unauthorized_arm_starts_no_process_at_all(self) -> None:
        # Not "runs and is marked": the spy asserts it was never called.
        # Falsified by: any argv reaching the executor for an unauthorized arm.
        patch_devices(self, ("ttys006", "ttys009"))
        for arm in recorder.ARMS:
            spy = Spy()
            record = recorder.run_arm(
                arm, allowed=False, readers=readers(), execute=spy, spawn=SpawnSpy()
            )
            with self.subTest(arm=arm.id):
                self.assertEqual([], spy.calls)
                self.assertFalse(record["authorized"])
                self.assertEqual(recorder.OUTCOME_NOT_AUTHORIZED, record["outcome"])
                self.assertTrue(all(c["ran"] is False for c in record["commands"]))

    def test_every_arm_has_its_own_flag_and_no_flag_covers_two(self) -> None:
        # One flag for all of them would let an operator authorise A3's durable
        # TCC grant while meaning to authorise A0's `lsappinfo`.
        flags = [recorder.flag_for(arm.id) for arm in recorder.ARMS]
        self.assertEqual(len(flags), len(set(flags)))
        parsed = recorder.build_parser().parse_args(["--arm", "a5", "--allow-a5"])
        self.assertTrue(recorder.authorized("a5", parsed))
        for arm in recorder.ARMS:
            if arm.id != "a5":
                with self.subTest(arm=arm.id):
                    self.assertFalse(recorder.authorized(arm.id, parsed))

    def test_the_disclaimed_spawn_refuses_without_its_flag_too(self) -> None:
        # Found by running the suite, not by reading the code. `posix_spawn` is
        # a SECOND way to start a process, `_execute` never saw it, and the
        # injected executor could not intercept it -- so this suite spawned
        # three real `osascript` raises while every spy in it reported nothing
        # had run. They declined, because the target device held no tab, which
        # was the arrangement's luck rather than the gate's doing.
        # Falsified by: a disclaimed spawn reachable on `allowed=False`.
        with self.assertRaises(recorder.RefusedError):
            recorder._spawn_disclaimed(["/usr/bin/true"], allowed=False)

    def test_every_way_of_starting_a_process_is_gated_on_the_same_word(self) -> None:
        # The enumeration that closes the class of defect above rather than the
        # one instance of it: each function that starts a process takes
        # `allowed` and refuses on it.
        # Falsified by: a third spawn path appearing without a gate.
        source = SCRIPT.read_text(encoding="utf-8")
        starters = [
            block.split("(")[0]
            for block in source.split("\ndef ")[1:]
            if "subprocess.run(" in block.split("\ndef ")[0]
            or "lib.posix_spawn(" in block.split("\ndef ")[0]
        ]
        # `_read` is the exception and is named here rather than left implied:
        # it takes the readings, never an arm's command, and moves nothing.
        self.assertEqual(["_read", "_execute", "_spawn_disclaimed"], starters)
        for name in ("_execute", "_spawn_disclaimed"):
            gate = source.split(f"def {name}(")[1].split("\ndef ")[0]
            with self.subTest(starter=name):
                self.assertIn("allowed", gate.split(")")[0])
                self.assertIn("RefusedError", gate)

    def test_the_window_quitting_step_carries_a_second_flag(self) -> None:
        # A2 opens a window and then closes one. The close is the step that
        # touches something an operator opened, so it is gated on its own.
        # Falsified by: a quit step reachable on `--allow-a2` alone.
        steps = recorder.plan(recorder.ARMS_BY_ID["a2"], recorder.Targets(device="ttys009"))
        gated = [step for step in steps if step.get("requires_flag")]
        self.assertEqual([recorder.A2_QUIT_FLAG], [step["requires_flag"] for step in gated])
        self.assertIn("close w saving no", " ".join(gated[0]["argv"]))

    def test_the_gated_step_does_not_run_even_when_the_arm_is_authorized(self) -> None:
        # Falsified by: `--allow-a2` alone reaching the close.
        patch_devices(self, ("ttys006", "ttys009"))
        spy = Spy()
        record = recorder.run_arm(
            recorder.ARMS_BY_ID["a2"],
            allowed=True,
            readers=readers(),
            execute=spy,
            spawn=SpawnSpy(),
        )
        quits = [c for c in record["commands"] if c["requires_flag"]]
        self.assertTrue(quits)
        self.assertTrue(all(c["ran"] is False for c in quits))
        self.assertFalse(any("close w saving no" in " ".join(call) for call in spy.calls))

    def test_the_cli_refuses_an_unflagged_arm_loudly_and_writes_nothing(self) -> None:
        # This recorder is not a hook, so nothing reads a non-zero code as a
        # block, and a silent zero would be the operator's likeliest mistake.
        # The sibling swallows argparse's 2 for the opposite reason.
        # Falsified by: exit 0, or a file appearing.
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "capture.jsonl"
            for arm in recorder.ARMS:
                done = subprocess.run(
                    [sys.executable, str(SCRIPT), "--arm", arm.id, "--out", str(out)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                with self.subTest(arm=arm.id):
                    self.assertNotEqual(0, done.returncode)
                    self.assertIn(recorder.flag_for(arm.id), done.stderr)
                    self.assertIn("Nothing ran", done.stderr)
                    self.assertFalse(out.exists())


class AlreadyThereTrapTest(unittest.TestCase):
    """A positive that cannot be told from 'it was already there' is unreachable."""

    def test_an_app_target_already_in_front_runs_nothing(self) -> None:
        # The trap in its plainest form: Finder already frontmost makes "it
        # moved" and "it was already there" the same after-state.
        # Falsified by: an activate reaching the executor.
        spy = Spy()
        record = recorder.run_arm(
            recorder.ARMS_BY_ID["a3"],
            allowed=True,
            readers=readers(frontmost="com.apple.finder"),
            execute=spy,
            spawn=SpawnSpy(),
        )
        self.assertEqual([], spy.calls)
        self.assertEqual(recorder.OUTCOME_INCONCLUSIVE, record["outcome"])
        self.assertEqual(recorder.WHY_ALREADY_THERE, record["precondition"]["why"])
        self.assertTrue(record["precondition"]["target_was_already_the_current_state"])

    def test_the_same_arm_runs_when_the_target_is_not_already_in_front(self) -> None:
        # The positive control for the guard above. A guard that refused
        # everything would also pass the test above.
        spy = Spy()
        record = recorder.run_arm(
            recorder.ARMS_BY_ID["a3"],
            allowed=True,
            readers=readers(),
            execute=spy,
            spawn=SpawnSpy(),
        )
        self.assertEqual(1, len(spy.calls))
        self.assertTrue(record["precondition"]["satisfied"])

    def test_a_terminal_target_is_chosen_to_differ_from_the_selected_tab(self) -> None:
        # Not checked afterwards -- CHOSEN. The target is picked from the tabs
        # that are not the selected one, so the trap has no way to arise.
        # Falsified by: a target equal to the before-state.
        patch_devices(self, ("ttys006", "ttys009"))
        targets, before, precondition = recorder.resolve(
            recorder.ARMS_BY_ID["a1"], readers=readers(selected="ttys006")
        )
        self.assertEqual("ttys006", before.selected)
        self.assertEqual("ttys009", targets.device)
        self.assertTrue(precondition["satisfied"])

    def test_a_single_terminal_tab_leaves_no_distinct_target_and_runs_nothing(self) -> None:
        # One tab means every raise is a no-op that looks like a success.
        # Falsified by: an arm running against its own tab.
        patch_devices(self, ("ttys006",))
        spy = Spy()
        record = recorder.run_arm(
            recorder.ARMS_BY_ID["a1"],
            allowed=True,
            readers=readers(selected="ttys006"),
            execute=spy,
            spawn=SpawnSpy(),
        )
        self.assertEqual([], spy.calls)
        self.assertEqual(recorder.WHY_NO_DISTINCT_TARGET, record["precondition"]["why"])
        self.assertEqual(recorder.OUTCOME_INCONCLUSIVE, record["outcome"])

    def test_an_arm_that_cannot_establish_a_before_state_is_not_an_arm(self) -> None:
        # `SECURITY.md`'s focus section makes a raise on a lookup
        # that found nothing a violation, and the same reasoning applies to the
        # measurement: with no before there is no after to compare it to.
        # Falsified by: a command running with `frontmost` unreadable.
        patch_devices(self, ("ttys006", "ttys009"))
        for arm in recorder.ARMS:
            spy = Spy()
            record = recorder.run_arm(
                arm, allowed=True, readers=readers(frontmost=None), execute=spy, spawn=SpawnSpy()
            )
            with self.subTest(arm=arm.id):
                self.assertEqual([], spy.calls)
                self.assertEqual(recorder.WHY_NO_BEFORE, record["precondition"]["why"])
                self.assertEqual(recorder.OUTCOME_INCONCLUSIVE, record["outcome"])

    def test_a_device_more_than_one_live_tab_sits_on_is_refused(self) -> None:
        # Measured in DRC-4382 and carried into the contract: macOS recycles the
        # device, three tabs matched one device with one of them busy, and a
        # raise on an ambiguous lookup is a violation. Refused before anything is
        # aimed anywhere rather than after.
        # Falsified by: an arm running against a device two live tabs hold.
        patch_devices(self, ("ttys006", "ttys009"))
        spy = Spy()
        record = recorder.run_arm(
            recorder.ARMS_BY_ID["a1"],
            allowed=True,
            readers=readers(tabs={"tabs": 3, "busy_tabs": 2}),
            execute=spy,
            spawn=SpawnSpy(),
        )
        self.assertEqual([], spy.calls)
        self.assertEqual(recorder.WHY_AMBIGUOUS, record["precondition"]["why"])
        self.assertEqual(2, record["precondition"]["live_candidates_on_the_target_device"])

    def test_the_ambiguity_arm_needs_its_arrangement_before_it_runs(self) -> None:
        # A7 is about two clients. With one attached it is A5 with a different
        # label, and would report a positive for a question nobody asked.
        # Falsified by: A7 running against a single client.
        spy = Spy()
        record = recorder.run_arm(
            recorder.ARMS_BY_ID["a7"],
            allowed=True,
            readers=readers(clients=("ttys004",)),
            execute=spy,
            spawn=SpawnSpy(),
        )
        self.assertEqual([], spy.calls)
        self.assertEqual(recorder.WHY_NO_ARRANGEMENT, record["precondition"]["why"])
        pair = recorder.run_arm(
            recorder.ARMS_BY_ID["a7"],
            allowed=True,
            readers=readers(clients=("ttys004", "ttys005"), selected="%1"),
            execute=Spy(),
            spawn=SpawnSpy(),
        )
        self.assertTrue(pair["precondition"]["satisfied"])
        self.assertEqual(2, pair["precondition"]["clients_attached"])


class RecordShapeTest(unittest.TestCase):
    def record(self, arm_id: str = "a1", **over: Any) -> dict[str, Any]:
        patch_devices(self, over.pop("devices", ("ttys006", "ttys009")))
        return recorder.run_arm(
            recorder.ARMS_BY_ID[arm_id],
            allowed=over.pop("allowed", True),
            readers=over.pop("readers", readers()),
            execute=over.pop("execute", Spy()),
            spawn=over.pop("spawn", SpawnSpy()),
        )

    def test_a_record_carries_the_full_key_set_the_verdict_reads(self) -> None:
        # The team-registry test exists because a reproduction test alone passed
        # while an arm was missing five keys: a verdict that reads arms as given
        # data cannot notice a field that is not there.
        # Falsified by: any arm missing a key, or carrying one nobody declared.
        for arm in recorder.ARMS:
            with self.subTest(arm=arm.id):
                self.assertEqual(recorder.ARM_KEYS, frozenset(self.record(arm.id)))

    def test_every_nested_block_carries_its_declared_key_set(self) -> None:
        # The same failure one level down, which the top-level check cannot see.
        # `--dry-run` advertises these lists, so a mismatch is a dry-run that
        # promises a field the recorder does not write.
        # Falsified by: a precondition or command key added in one place only.
        record = self.record()
        self.assertEqual(frozenset(recorder.PRECONDITION_KEYS), frozenset(record["precondition"]))
        for command in record["commands"]:
            self.assertEqual(frozenset(recorder.COMMAND_KEYS), frozenset(command))

    def test_an_arm_records_what_ran_as_an_argv_list(self) -> None:
        # The deliverable's first requirement, and a list rather than a string
        # because a string is a shell command and this recorder never runs one.
        record = self.record()
        self.assertTrue(record["commands"])
        for command in record["commands"]:
            self.assertIsInstance(command["argv"], list)
            self.assertTrue(all(isinstance(word, str) for word in command["argv"]))

    def test_an_arm_records_before_and_after_on_both_axes(self) -> None:
        # Frontmost application and selected-tab-or-pane, before and after, plus
        # whether anything moved. An arm missing a before is not an arm.
        record = self.record()
        for axis in ("frontmost", "selected"):
            with self.subTest(axis=axis):
                self.assertIn("before", record[axis])
                self.assertIn("after", record[axis])
                self.assertIn("changed", record[axis])
        self.assertIn("moved", record)

    def test_the_responsible_process_of_the_issuer_is_recorded_for_every_arm(self) -> None:
        # The variable the whole question turns on. On this machine a daemon
        # after a double fork and three days under launchd still answers
        # Terminal, which is why a success under it proves nothing on its own.
        for arm in recorder.ARMS:
            with self.subTest(arm=arm.id):
                found = self.record(arm.id)["responsible"]
                self.assertEqual("Terminal", found["name"])
                self.assertFalse(found["is_self"])
                self.assertEqual(arm.issuer, found["issuer_kind"])

    def test_output_is_discarded_rather_than_parsed(self) -> None:
        # The contract's "nothing is read back", asserted on the record and on
        # the source: a raise that reported its own success would be evidence of
        # nothing, which is why the before-and-after probes exist.
        for command in self.record()["commands"]:
            self.assertTrue(command["output_discarded"])
        source = SCRIPT.read_text(encoding="utf-8")
        gate = source.split("def _execute(")[1].split("\ndef ")[0]
        self.assertIn("stdout=subprocess.DEVNULL", gate)
        self.assertIn("stderr=subprocess.DEVNULL", gate)
        self.assertNotIn("capture_output", gate)


class RedactionTest(unittest.TestCase):
    def test_the_device_under_test_survives(self) -> None:
        # The whole reason `shape()` is not reused. `ttys006` masked to
        # `ttys###` answers no question this file asks.
        # Falsified by: a masked device in a record.
        patch_devices(self, ("ttys006", "ttys009"))
        record = recorder.run_arm(
            recorder.ARMS_BY_ID["a1"],
            allowed=True,
            readers=readers(),
            execute=Spy(),
            spawn=SpawnSpy(),
        )
        self.assertEqual("ttys006", record["selected"]["before"])
        self.assertEqual("ttys009", record["precondition"]["target_device"])
        # The argv the raise was aimed with carries the device whole too, or the
        # record could not say what the command actually targeted.
        self.assertIn("/dev/ttys009", " ".join(record["commands"][0]["argv"]))

    def test_only_the_ancestry_chain_carries_a_shaped_device(self) -> None:
        # The record mixes two conventions on purpose, so the boundary is pinned
        # rather than left to drift. The chain is context about which processes
        # the issuer sits under and goes through the sibling's masking; every
        # value under test stays whole.
        # Falsified by: a masked device outside `ancestry`, or a whole one inside.
        patch_devices(self, ("ttys006", "ttys009"))
        record = recorder.run_arm(
            recorder.ARMS_BY_ID["a1"],
            allowed=True,
            readers=readers(),
            execute=Spy(),
            spawn=SpawnSpy(),
        )
        without_chain = dict(record)
        without_chain.pop("ancestry")
        self.assertNotIn("ttys###", json.dumps(without_chain))
        for entry in record["ancestry"]["chain"]:
            with self.subTest(depth=entry["depth"]):
                self.assertIsNone(identity.shape(entry["tty"]) != entry["tty"] or None)

    def test_the_frontmost_application_is_named_only_when_an_arm_targets_it(self) -> None:
        # The redaction the sibling never needed. `before` is whatever the
        # operator was looking at, and that can be a password manager.
        # Falsified by: an arbitrary bundle identifier in a record.
        self.assertEqual("other", recorder.app_label("com.agilebits.onepassword"))
        self.assertEqual("other", recorder.app_label("com.google.Chrome"))
        self.assertEqual("Terminal", recorder.app_label("com.apple.Terminal"))
        self.assertEqual("Finder", recorder.app_label("com.apple.finder"))
        self.assertIsNone(recorder.app_label(None))
        patch_devices(self, ("ttys006", "ttys009"))
        blob = json.dumps(
            recorder.run_arm(
                recorder.ARMS_BY_ID["a1"],
                allowed=True,
                readers=readers(frontmost="com.agilebits.onepassword"),
                execute=Spy(),
                spawn=SpawnSpy(),
            )
        )
        self.assertNotIn("onepassword", blob)
        self.assertNotIn("agilebits", blob)

    def test_movement_between_two_unnamed_applications_is_still_detected(self) -> None:
        # The defect the redaction above would introduce if it were applied
        # first: two applications that both redact to `other` compare equal, so
        # a real move reads as a no-op. Computed on the RAW pair instead, which
        # is the sibling's rule for agreement between two readings.
        # Falsified by: `changed` false for a move between two `other` apps.
        moved = recorder._moved(
            recorder.Snapshot(frontmost="com.apple.Safari"),
            recorder.Snapshot(frontmost="com.tinyspeck.slackmacgap"),
        )
        self.assertTrue(moved)
        self.assertEqual("other", recorder.app_label("com.apple.Safari"))
        self.assertEqual("other", recorder.app_label("com.tinyspeck.slackmacgap"))

    def test_no_window_title_is_ever_read(self) -> None:
        # A Terminal window's title is the running command and the working
        # directory -- a repository, a branch, a customer.
        # Falsified by: `name of` or `custom title` in any script.
        scripts = [
            recorder.raise_terminal_tab("ttys006"),
            recorder.selected_terminal_tty(),
            recorder.close_window_on_device("ttys006"),
            recorder.EVERY_TERMINAL_TAB_TTY,
            recorder.open_launcher_window("cmd"),
            recorder.activate_app("Finder"),
        ]
        for script in scripts:
            with self.subTest(script=script[:40]):
                self.assertNotIn("custom title", script)
                self.assertNotIn("name of", script)
                self.assertNotIn("processes", script)

    def test_a_home_path_in_an_argv_is_redacted_on_the_way_into_the_record(self) -> None:
        # A2's launcher argv names the interpreter, this script and the capture
        # file, all absolute and all under a home directory. Nothing else in the
        # file goes near a path, and this is the only reason the rule exists.
        # Falsified by: a home directory in a record.
        redacted = recorder.redact_argv(
            [
                "/Users/someone/.pyenv/bin/python3 /Users/someone/repos/acme/x.py --out /tmp/a/b.jsonl"
            ]
        )
        self.assertNotIn("someone", redacted[0])
        self.assertNotIn("acme", redacted[0])
        self.assertIn("<path>/python3", redacted[0])
        self.assertIn("<path>/b.jsonl", redacted[0])

    def test_a_device_node_and_a_system_binary_survive_the_path_rule(self) -> None:
        # Both start with a slash and neither names anybody. A rule that ate
        # `/dev/ttys006` would delete the value under test, and one that ate
        # `/usr/bin/osascript` would stop a reader checking which binary ran.
        # Falsified by: `<path>/ttys006` anywhere.
        kept = recorder.redact_argv(["/usr/bin/osascript", "-e", 'tty of t is "/dev/ttys006"'])
        self.assertEqual("/usr/bin/osascript", kept[0])
        self.assertIn("/dev/ttys006", kept[2])

    def test_the_recorded_argv_of_the_a2_launcher_carries_no_home_directory(self) -> None:
        # End to end over the arm that actually has the problem.
        # Falsified by: a real home path in the A2 record.
        patch_devices(self, ("ttys006", "ttys009"))
        # The minted path stands in for `tempfile.mkdtemp`'s, which on a real
        # run is under a user's temp directory and on Windows carries no forward
        # slash at all. Supplied by the test so the assertion measures the
        # redaction rather than the runner's own filesystem layout.
        minted = "/Users/someone/scratch/cargento-raise-x9/a2"
        with unittest.mock.patch.object(recorder, "_mint_handshake", lambda: minted):
            record = recorder.run_arm(
                recorder.ARMS_BY_ID["a2"],
                allowed=True,
                readers=readers(),
                execute=Spy(),
                spawn=SpawnSpy(),
                wait=WaitSpy(),
                extra_flags=frozenset({recorder.A2_QUIT_FLAG}),
            )
        blob = json.dumps(record["commands"])
        self.assertIn("<path>/a2", blob, "the launcher argv must carry the minted path")
        self.assertNotIn("/Users/", blob)
        self.assertNotIn("someone", blob)

    def test_the_recorder_cannot_reach_the_network(self) -> None:
        # The user has a Cargento running, and a recorder that posted to it
        # would contaminate the thing being measured -- and a raise recorder
        # posting anywhere would also be an exfiltration path for a device.
        source = SCRIPT.read_text(encoding="utf-8")
        for banned in ("import socket", "import urllib", "import http", "requests"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, source)

    def test_nothing_is_typed_into_a_terminal_by_any_path(self) -> None:
        # The ask lane's direction invariant, which the focus contract says this
        # feature leaves unchanged. `send-keys` contradicts it outright.
        # Falsified by: any keystroke path in the recorder.
        source = SCRIPT.read_text(encoding="utf-8")
        for banned in ("send-keys", "send_keys", "keystroke", "key code"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, source)


class ReuseTest(unittest.TestCase):
    def test_the_sibling_is_imported_rather_than_copied(self) -> None:
        # The ancestry walk, the controlling-terminal read, the `/dev/tty` probe
        # and the tab lookup all live in one place.
        # Falsified by: a second copy of `walk` drifting from the first.
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("import capture_terminal_identity as identity", source)
        for reused in (
            "identity.ps_rows",
            "identity.walk",
            "identity.ancestry",
            "identity._fd_tty",
        ):
            with self.subTest(reused=reused):
                self.assertIn(reused, source)
        self.assertNotIn("def walk(", source)
        self.assertNotIn("def ps_rows(", source)

    def test_the_maskers_are_not_reused_on_any_reading(self) -> None:
        # `shape()` and `mask()` destroy the device, and the device is the value
        # under test. The one place a shaped value appears is inside the
        # sibling's own `walk`, where an ancestor NAME is shaped and no device
        # this file measures passes through.
        # Falsified by: `identity.shape(` on a reading here.
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("identity.shape(", source)
        self.assertNotIn("identity.mask(", source)

    def test_the_ancestry_walk_labels_nothing_a_harness(self) -> None:
        # Nothing here is a harness, and `walk` keys its harness role off a name
        # it is handed. An unknown key gives it an empty executable set, so no
        # ancestor is mislabelled rather than mislabelled quietly.
        chain = identity.walk(
            [
                {"pid": 1, "ppid": 2, "ucomm": "python3.12", "comm": "/x/python3.12", "tty": "s"},
                {"pid": 2, "ppid": 0, "ucomm": "Terminal", "comm": "/A/Terminal", "tty": "??"},
            ],
            harness="",
        )
        self.assertEqual(["recorder", "emulator"], [entry["role"] for entry in chain])


class VerdictTest(unittest.TestCase):
    def arm(self, arm_id: str = "a1", **over: Any) -> dict[str, Any]:
        with unittest.mock.patch.object(
            recorder, "_terminal_devices", lambda _r: ["ttys006", "ttys009"]
        ):
            record = recorder.run_arm(
                recorder.ARMS_BY_ID[arm_id],
                allowed=over.pop("allowed", True),
                readers=over.pop("readers", readers()),
                execute=over.pop("execute", Spy()),
                spawn=over.pop("spawn", SpawnSpy()),
            )
        for key, value in over.items():
            record[key] = value
        record["outcome"] = recorder.outcome_of(record)
        return record

    def test_the_verdict_is_derived_from_the_arm_records_rather_than_declared(self) -> None:
        # Nothing in an evidence file may be a number a person typed. Every
        # field below is recomputed from the arms handed in.
        # Falsified by: a verdict field that survives a change to its arms.
        first = self.arm()
        found = recorder.verdict([first], base=recorder.base_of(first))
        self.assertEqual(recorder.RECORD_VERDICT, found["record"])
        self.assertEqual(1, found["invocations"])
        self.assertEqual(["a1"], found["arms"])
        self.assertEqual(VERDICT_KEYS_EXPECTED, frozenset(found))
        second = json.loads(json.dumps(first))
        second["arm"] = "a3"
        pair = recorder.verdict([first, second], base=recorder.base_of(first))
        self.assertEqual(["a1", "a3"], pair["arms"])
        self.assertEqual(2, pair["invocations"])

    def test_an_arm_that_never_ran_contributes_null_rather_than_a_negative(self) -> None:
        # A composed verdict fails toward a confident green: "it did not move"
        # and "nobody asked it to" are different answers, and reading the second
        # as the first turns an unauthorised file into evidence of failure.
        # Falsified by: `moved` false for an arm nothing ran.
        blank = self.arm(allowed=False)
        summary = recorder.verdict([blank], base=recorder.base_of(blank))
        self.assertIsNone(summary["per_arm"]["a1"]["moved"])
        self.assertEqual(0, summary["per_arm"]["a1"]["ran"])
        self.assertEqual(recorder.VERDICT_NO_ARM_RAN, summary["verdict"])

    def test_a_control_that_moved_something_invalidates_the_file(self) -> None:
        # The instrument check. A recorder that moves a window when told to aim
        # at nothing cannot vouch for the arms that were aimed at something, so
        # this outranks every positive in the file.
        # Falsified by: a green verdict beside a failed control.
        control = mark_moved(self.arm("a8"))
        positive = self.arm("a1")
        positive["frontmost"]["after_is_the_target"] = True
        mark_moved(positive)
        found = recorder.verdict([control, positive], base=recorder.base_of(control))
        self.assertEqual(recorder.OUTCOME_CONTROL_FAILED, control["outcome"])
        self.assertFalse(found["controls_held"])
        self.assertEqual(recorder.VERDICT_CONTROLS_FAILED, found["verdict"])

    def test_a_control_that_held_still_does_not_by_itself_prove_a_raise_works(self) -> None:
        # The other half: a file of nothing but controls holding still says the
        # instrument works and nothing about the question.
        control = mark_still(self.arm("a8"))
        found = recorder.verdict([control], base=recorder.base_of(control))
        self.assertTrue(found["controls_held"])
        # `unmeasured`, not `does_not_work`: this file holds controls and nothing
        # else, so it cannot say either way. The distinction is the whole point
        # of the test whose name is above it.
        self.assertEqual("unmeasured", found["socket_raise"])
        self.assertEqual("unmeasured", found["apple_event_raise"])

    def test_a_success_under_the_exempt_identity_is_not_read_as_a_general_grant(self) -> None:
        # The finding this whole capture exists for. A raise from a process
        # macOS attributes to Terminal is that application automating itself,
        # which is an exemption rather than a grant, so it may not roll up to
        # the same answer an alien identity would give.
        # Falsified by: A1 alone reading as `a_raise_works_from_an_alien_...`.
        a1 = self.arm("a1")
        a1["frontmost"]["after_is_the_target"] = True
        mark_moved(a1)
        found = recorder.verdict([a1], base=recorder.base_of(a1))
        self.assertEqual("only_from_the_exempt_responsible_identity", found["apple_event_raise"])
        self.assertEqual("unmeasured", found["socket_raise"])
        self.assertEqual(["Terminal"], found["per_arm"]["a1"]["responsible_names"])

    def test_a_success_from_an_alien_responsible_identity_is_the_stronger_answer(self) -> None:
        # A4 and A2 are the arms that can produce it, and they are separated
        # from A1 by their issuer rather than by a label anyone typed.
        # Falsified by: a disclaimed success reading the same as a same-app one.
        alien = self.arm("a4")
        alien["frontmost"]["after_is_the_target"] = True
        mark_moved(alien)
        found = recorder.verdict([alien], base=recorder.base_of(alien))
        self.assertEqual("works_from_an_alien_responsible_identity", found["apple_event_raise"])
        # The arms that ran touched no socket, so the file says so rather than
        # letting an Apple Event answer stand in for one.
        self.assertEqual("unmeasured", found["socket_raise"])
        self.assertEqual(recorder.ISSUER_DISCLAIMED, found["per_arm"]["a4"]["issuer"])

    def test_an_inconclusive_arm_is_not_counted_as_having_run(self) -> None:
        # The trap's consequence in the summary: an arm skipped because its
        # target was already there must not be summarised as one that ran and
        # found nothing.
        # Falsified by: `ran` counting an inconclusive arm.
        skipped = self.arm("a3", readers=readers(frontmost="com.apple.finder"))
        found = recorder.verdict([skipped], base=recorder.base_of(skipped))
        self.assertEqual(recorder.OUTCOME_INCONCLUSIVE, skipped["outcome"])
        self.assertEqual(0, found["per_arm"]["a3"]["ran"])
        self.assertEqual([recorder.WHY_ALREADY_THERE], found["per_arm"]["a3"]["why_not"])

    def test_the_outcome_is_derived_from_the_record_rather_than_set_by_the_caller(self) -> None:
        # Every arm label comes back out of the same function, over data.
        # Falsified by: an outcome that survives its evidence changing.
        moved = self.arm("a1")
        moved["moved"] = True
        moved["frontmost"]["after_is_the_target"] = False
        moved["selected"]["after_is_the_target"] = False
        self.assertEqual(recorder.OUTCOME_MOVED_ELSEWHERE, recorder.outcome_of(moved))
        moved["frontmost"]["after_is_the_target"] = True
        self.assertEqual(recorder.OUTCOME_MOVED_TO_TARGET, recorder.outcome_of(moved))
        moved["moved"] = False
        self.assertEqual(recorder.OUTCOME_DID_NOT_MOVE, recorder.outcome_of(moved))
        moved["moved"] = None
        self.assertEqual(recorder.OUTCOME_DID_NOT_MOVE, recorder.outcome_of(moved))


VERDICT_KEYS_EXPECTED = recorder.VERDICT_KEYS


class CommandLineTest(unittest.TestCase):
    def run_recorder(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

    def test_the_dry_run_prints_every_arm_and_runs_nothing(self) -> None:
        # What an operator reads before authorising anything, so it has to be
        # complete: an arm missing from it is an arm nobody weighed.
        # Falsified by: an arm absent from the dry run.
        done = self.run_recorder("--dry-run")
        self.assertEqual(0, done.returncode, done.stderr)
        for arm in recorder.ARMS:
            with self.subTest(arm=arm.id):
                self.assertIn(f"=== {arm.id} ", done.stdout)
                self.assertIn(recorder.flag_for(arm.id), done.stdout)
        self.assertIn("NOTHING BELOW RUNS", done.stdout)
        self.assertIn(recorder.A2_QUIT_FLAG, done.stdout)

    def test_the_dry_run_prints_the_argv_of_every_step(self) -> None:
        # "Exactly what each arm WOULD run". A dry run that named a command
        # without showing it would leave the operator authorising a description.
        # Falsified by: a step printed without its argv.
        printed = "\n".join(recorder.dry_run())
        for arm in recorder.ARMS:
            for step in recorder.plan(arm, recorder.Targets()):
                if not step["argv"]:
                    continue
                with self.subTest(arm=arm.id, purpose=step["purpose"]):
                    self.assertIn(json.dumps(step["argv"]), printed)

    def test_the_dry_run_advertises_the_key_set_the_recorder_actually_writes(self) -> None:
        # A dry run promising a field the recorder does not write is the same
        # defect as an arm missing five keys, read from the other end.
        printed = "\n".join(recorder.dry_run())
        self.assertIn(", ".join(sorted(recorder.ARM_KEYS)), printed)
        self.assertIn(", ".join(recorder.PRECONDITION_KEYS), printed)
        self.assertIn(", ".join(recorder.COMMAND_KEYS), printed)

    def test_the_dry_run_names_the_trap_and_the_gate(self) -> None:
        # Two things the operator has to be able to read off it: that an
        # already-there target runs nothing, and that A2's quit is separately
        # gated.
        printed = "\n".join(recorder.dry_run())
        self.assertIn("inconclusive", printed)
        self.assertIn("NOT PASSED", printed)
        self.assertIn(f"[needs {recorder.A2_QUIT_FLAG}]", printed)

    def test_a_second_verdict_over_the_same_file_compares_rather_than_appends(self) -> None:
        # `--verdict` is what a reader runs to check the derivation, and the
        # sibling's appended blindly -- two verdict lines in a git-tracked
        # evidence file, exit 0, and a red suite on the count.
        # Falsified by: a second run growing the file.
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "capture.jsonl"
            with unittest.mock.patch.object(
                recorder, "_terminal_devices", lambda _r: ["ttys006", "ttys009"]
            ):
                for arm_id in ("a8", "a1"):
                    identity.append(
                        str(out),
                        recorder.run_arm(
                            recorder.ARMS_BY_ID[arm_id],
                            allowed=True,
                            readers=readers(),
                            execute=Spy(),
                            spawn=SpawnSpy(),
                        ),
                    )
            first = self.run_recorder("--verdict", str(out))
            self.assertEqual(0, first.returncode, first.stderr)
            self.assertIn("appended", first.stdout)
            lines = len(out.read_text(encoding="utf-8").splitlines())
            second = self.run_recorder("--verdict", str(out))
            self.assertEqual(0, second.returncode, second.stderr)
            self.assertIn("reproduced", second.stdout)
            self.assertEqual(lines, len(out.read_text(encoding="utf-8").splitlines()))
            printed = self.run_recorder("--report", str(out))
            self.assertEqual(0, printed.returncode, printed.stderr)
            # The evidence beside the label: `--report` printing an outcome and
            # hiding the readings it came from is how a reader was left unable
            # to check the sibling's derivation.
            self.assertIn("after_is_the_target", printed.stdout)
            self.assertIn("controls_held=", printed.stdout)

    def test_a_verdict_that_no_longer_matches_its_arms_exits_non_zero(self) -> None:
        # Drift between the arms and the committed verdict has to be an exit
        # code, not a silent second line.
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "capture.jsonl"
            with unittest.mock.patch.object(
                recorder, "_terminal_devices", lambda _r: ["ttys006", "ttys009"]
            ):
                identity.append(
                    str(out),
                    recorder.run_arm(
                        recorder.ARMS_BY_ID["a1"],
                        allowed=True,
                        readers=readers(),
                        execute=Spy(),
                        spawn=SpawnSpy(),
                    ),
                )
            self.run_recorder("--verdict", str(out))
            records = [json.loads(line) for line in out.read_text().splitlines()]
            records[-1]["per_arm"]["a1"]["invocations"] = 99
            out.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in records))
            drifted = self.run_recorder("--verdict", str(out))
            self.assertEqual(1, drifted.returncode)
            self.assertIn("DIFFERS", drifted.stderr)

    def test_a_bare_invocation_names_what_it_needs_and_runs_nothing(self) -> None:
        done = self.run_recorder()
        self.assertEqual(2, done.returncode)
        self.assertIn("--arm is required", done.stderr)


class ReaderParseTest(unittest.TestCase):
    """The parsers, held to output shapes taken off this machine rather than recalled.

    Desk research has got a field name, a unit or a rendering wrong every time
    it was checked against a live install here, so each shape below was read off
    a real command before it was written down.
    """

    def fake_read(self, answers: dict[str, tuple[int, str]]) -> Any:
        def _read(argv: Sequence[str]) -> tuple[int, str]:
            key = " ".join(argv)
            for prefix, answer in answers.items():
                if key.startswith(prefix):
                    return answer
            return 1, ""

        return unittest.mock.patch.object(recorder, "_read", _read)

    def test_the_frontmost_read_is_two_calls_and_unquotes_the_value(self) -> None:
        # `lsappinfo front` answers an ASN, and only a second call turns that
        # into a bundle id. Measured shapes: `ASN:0x0-0x143a439:` and
        # `"CFBundleIdentifier"="com.google.Chrome"`.
        # Falsified by: a parser that keeps the quotes or the key.
        with self.fake_read(
            {
                "/usr/bin/lsappinfo front": (0, "ASN:0x0-0x143a439:"),
                "/usr/bin/lsappinfo info": (0, '"CFBundleIdentifier"="com.google.Chrome"'),
            }
        ):
            self.assertEqual("com.google.Chrome", recorder.read_frontmost())

    def test_an_unavailable_frontmost_read_is_an_absence_rather_than_a_guess(self) -> None:
        # A before-state that cannot be read must be None, because that is what
        # makes the arm inconclusive instead of confidently wrong.
        with self.fake_read({"/usr/bin/lsappinfo front": (1, "")}):
            self.assertIsNone(recorder.read_frontmost())
        with self.fake_read(
            {
                "/usr/bin/lsappinfo front": (0, "ASN:0x0-0x1:"),
                "/usr/bin/lsappinfo info": (0, "no equals sign here"),
            }
        ):
            self.assertIsNone(recorder.read_frontmost())

    def test_a_terminal_with_no_windows_reads_as_no_selection(self) -> None:
        # The script returns the empty string there on purpose, so "no before
        # state" stays distinguishable from "a before state that is empty".
        with self.fake_read({"/usr/bin/osascript": (0, "")}):
            self.assertIsNone(recorder.read_terminal_selected())
        with self.fake_read({"/usr/bin/osascript": (0, "/dev/ttys006")}):
            self.assertEqual("/dev/ttys006", recorder.read_terminal_selected())

    def test_a_process_with_no_controlling_terminal_is_not_read_as_a_device(self) -> None:
        # `ps` writes `??` there, `??` is truthy, and DRC-4382 put one straight
        # into an AppleScript query against `/dev/??`.
        with self.fake_read({"/usr/bin/osascript": (0, "??")}):
            self.assertIsNone(recorder.read_terminal_selected())

    def test_the_tmux_reads_go_to_this_recorders_own_socket(self) -> None:
        # A read against the default socket would answer about the operator's
        # own sessions, which is both the wrong answer and one this file may not
        # record.
        # Falsified by: a tmux read with no `-L`.
        seen: list[list[str]] = []

        def _read(argv: Sequence[str]) -> tuple[int, str]:
            seen.append(list(argv))
            return 0, "%3"

        with unittest.mock.patch.object(recorder, "_read", _read):
            self.assertEqual("%3", recorder.read_tmux_selected("cargento-raise", "ttys004"))
        self.assertEqual(["tmux", "-L", "cargento-raise"], seen[0][:3])
        # No client attached means no pane, and no command at all.
        seen.clear()
        with unittest.mock.patch.object(recorder, "_read", _read):
            self.assertIsNone(recorder.read_tmux_selected("cargento-raise", None))
        self.assertEqual([], seen)

    def test_a_client_list_keeps_devices_and_drops_everything_else(self) -> None:
        # `client_session` is a name the operator chose. The tty is an ordinal.
        with self.fake_read({"tmux": (0, "/dev/ttys004\t123\n??\t456\n/dev/ttys005\t789")}):
            self.assertEqual(
                [{"tty": "ttys004"}, {"tty": "ttys005"}],
                recorder.read_tmux_clients("cargento-raise"),
            )
        with self.fake_read({"tmux": (1, "")}):
            self.assertEqual([], recorder.read_tmux_clients("cargento-raise"))
            self.assertEqual([], recorder.read_tmux_panes("cargento-raise"))

    def test_a_responsible_process_is_named_from_a_closed_set(self) -> None:
        # An arbitrary `ucomm` is an arbitrary program name, and the operator's
        # own tooling is not this file's to record.
        # Falsified by: a program name outside the set reaching a record.
        with self.fake_read({"ps": (0, "Terminal")}):
            self.assertEqual("Terminal", recorder.process_name(48170))
        with self.fake_read({"ps": (0, "SomePrivateApp")}):
            self.assertEqual("other", recorder.process_name(48170))
        with self.fake_read({"ps": (1, "")}):
            self.assertIsNone(recorder.process_name(48170))
        self.assertIsNone(recorder.process_name(None))

    @unittest.skipUnless(sys.platform == "darwin", "responsibility API is macOS-only")
    def test_this_process_is_attributed_to_its_launching_terminal(self) -> None:
        # The measured finding the whole arm list rests on, asserted against the
        # live machine rather than recalled: a process in this tree answers a
        # responsible pid that is not itself.
        # Falsified by: a self-responsible recorder, which would make A1 a grant.
        mine = recorder.responsible_pid(os.getpid())
        self.assertIsNotNone(mine)
        self.assertNotEqual(os.getpid(), mine)


class ExecutorTest(unittest.TestCase):
    """The real gate body, against targets that move nothing."""

    def test_an_authorized_command_runs_and_its_status_is_kept(self) -> None:
        # The interpreter rather than `/usr/bin/true` and `/usr/bin/false`.
        # Those two are the obvious targets that move nothing, and they moved
        # nothing on macOS and on Ubuntu and then failed on Windows, where
        # neither path exists: the executor returned 127 for "could not start"
        # and the assertion read it as a wrong exit status. `_execute` itself is
        # platform-neutral, so its test should be too, and the arms that are
        # genuinely macOS-only are gated by their own flags rather than by a
        # path that happens not to resolve.
        self.assertEqual(0, recorder._execute([sys.executable, "-c", ""], allowed=True))
        self.assertEqual(
            1, recorder._execute([sys.executable, "-c", "raise SystemExit(1)"], allowed=True)
        )

    def test_a_command_that_cannot_start_is_a_status_rather_than_a_crash(self) -> None:
        # A recorder that raises mid-arm leaves the machine in a state it never
        # recorded a before for.
        self.assertEqual(127, recorder._execute(["/nonexistent/nope"], allowed=True))

    def test_a_handshake_file_survives_an_unwritable_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "handshake.ready")
            recorder._write_json(path, {"pid": 1})
            self.assertEqual({"pid": 1}, json.loads(Path(path).read_text()))
        recorder._write_json("/nonexistent/dir/x.json", {"pid": 1})


class SkippedGateTest(unittest.TestCase):
    """An arm whose defining step was skipped is inconclusive, not a positive.

    A2 exists to answer one question: does a raise still work once the terminal
    that launched the daemon is gone. Quitting that window is the step that makes
    it that question. `--allow-a2-quit-window` was parsed and never consumed, so
    the step was skipped unconditionally, the raise ran with the launcher still
    alive, and the arm reported `moved_to_target`. The verdict then counted it
    as an Apple Event positive.

    That is the same failure as reading an unauthorised arm as a negative, from
    the other end: a positive composed over evidence the arm did not gather.
    """

    def test_an_arm_with_a_skipped_gated_step_is_inconclusive(self) -> None:
        # Falsified by: `outcome_of` reading only whether something moved.
        record = VerdictTest().arm("a2")
        record["moved"] = True
        # The OTHER two rules satisfied, so only the gate can produce the
        # answer below. Both of `_unanswered`'s later rules read `inconclusive`
        # for a2, and a record that trips both proves neither -- which is what
        # this test did until a mutation walked through it.
        record["responsible"]["after_launcher_quit_name"] = "launchd"
        record["responsible"]["after_launcher_quit_is_self"] = False
        skipped = [c for c in record["commands"] if c.get("requires_flag") and not c["ran"]]
        self.assertTrue(skipped, "a2 must carry a gated step for this to mean anything")
        self.assertEqual(
            recorder.OUTCOME_INCONCLUSIVE,
            recorder.outcome_of(record),
            "an arm that skipped its defining step has not answered its question",
        )


class RequiredEvidenceTest(unittest.TestCase):
    """An arm that did not gather its own defining evidence answered nothing.

    A2 ran all three steps, quit the launcher window and moved a Terminal tab,
    and reported `moved_to_target`. But the two fields that say WHO issued the
    raise once the launcher was gone came back null, and those fields are the
    entire difference between A2 and A1. Without them the record is consistent
    with the launcher still being alive, which is the case three other arms
    already cover.

    Movement is not the evidence here. The responsible identity is, and an arm
    may declare the fields it cannot answer without.
    """

    def test_an_arm_missing_its_declared_evidence_is_inconclusive(self) -> None:
        # Falsified by: `outcome_of` reading movement alone.
        record = VerdictTest().arm("a2")
        record["moved"] = True
        # Every step ran, so the gated-step rule beside this one cannot answer
        # and the missing field is the only thing left that can.
        for step in record["commands"]:
            step["ran"] = True
        record["responsible"]["after_launcher_quit_is_self"] = True
        record["responsible"]["after_launcher_quit_name"] = None
        self.assertEqual(
            recorder.OUTCOME_INCONCLUSIVE,
            recorder.outcome_of(record),
            "a2 without its post-quit responsible identity has not answered its question",
        )

    def test_the_same_arm_with_its_evidence_is_read_normally(self) -> None:
        record = VerdictTest().arm("a2")
        record["moved"] = True
        record["responsible"]["after_launcher_quit_name"] = "python3"
        record["responsible"]["after_launcher_quit_is_self"] = True
        record["frontmost"]["after_is_the_target"] = True
        for step in record["commands"]:
            step["ran"] = True
        self.assertEqual(recorder.OUTCOME_MOVED_TO_TARGET, recorder.outcome_of(record))

    def test_every_arm_that_declares_evidence_names_a_real_field(self) -> None:
        blank = VerdictTest().arm("a2")
        for arm in recorder.ARMS:
            for path in arm.requires_evidence:
                with self.subTest(arm=arm.id, path=path):
                    cursor: Any = blank
                    for key in path:
                        self.assertIn(key, cursor, f"{arm.id} declares a field no record carries")
                        cursor = cursor[key]


class ReadScriptTest(unittest.TestCase):
    """The read scripts are run, not mocked.

    `EVERY_TERMINAL_TAB_TTY` shipped broken and nothing noticed, because every
    test that needed it patched `_terminal_devices` and every arm that ran took
    a path around it: the controls aim at a constructed device, the tmux arms
    read tmux, and the baseline observes. It set `text item delimiters` inside
    a `tell application "Terminal"` block, which asks Terminal for a property it
    does not have, so the read returned `-10006` and `_terminal_devices` gave
    back an empty list on every call. Every Apple Event arm then declined with
    `no_target_distinct_from_the_current_state`, which reads exactly like an
    arrangement the operator failed to set up.

    A mock cannot catch that. Only running the script can, so this does.
    """

    #: The READ scripts. Deliberately named rather than discovered, so that a
    #: raise script can never be swept into a test that executes what it finds.
    READS = ("SELECTED_TERMINAL_TTY", "EVERY_TERMINAL_TAB_TTY")

    @staticmethod
    def terminal_is_running() -> bool:
        """Whether Terminal is ALREADY up, without launching it to find out.

        `darwin` is not the condition, and asking AppleScript is not the probe.
        A `tell application "Terminal"` on a headless runner launches Terminal
        and then waits for an app that never becomes ready, so the first version
        of this guard did not fail on CI, it HUNG: two scripts, twenty seconds
        each, forty seconds added to the macOS job before the timeout fired.
        `pgrep` answers the same question and starts nothing.
        """
        if sys.platform != "darwin":
            return False
        # `ps` rather than `pgrep`: on the machine this was written on, pgrep
        # matches nothing for Terminal by name OR by path while `ps -eo comm`
        # lists it plainly, so a pgrep probe skipped everywhere and the test
        # could never have failed. That is the defect it exists to catch,
        # wearing the guard's clothes.
        listed = subprocess.run(
            ["/bin/ps", "-eo", "comm="],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return any(
            line.strip().endswith("/Terminal.app/Contents/MacOS/Terminal")
            for line in listed.stdout.splitlines()
        )

    def test_every_read_script_runs(self) -> None:
        if not self.terminal_is_running():
            raise unittest.SkipTest(
                "Terminal is not running; nothing to read and nothing to launch"
            )
        for name in self.READS:
            script = getattr(recorder, name)
            with self.subTest(script=name):
                done = subprocess.run(
                    ["/usr/bin/osascript", "-e", script],
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
                self.assertEqual(0, done.returncode, f"{name}: {done.stderr.strip()}")

    def test_no_script_sets_a_global_property_inside_a_tell_block(self) -> None:
        # The shape rather than the instance, so it holds on a machine that
        # cannot run AppleScript at all.
        source = SCRIPT.read_text(encoding="utf-8")
        for block in source.split('tell application "Terminal"')[1:]:
            body = block.split("end tell")[0]
            with self.subTest(block=body[:40]):
                self.assertNotIn(
                    "set text item delimiters",
                    body,
                    "text item delimiters belongs to the script, not to Terminal",
                )


class NoteAndReportTest(unittest.TestCase):
    def test_a_capture_can_carry_the_arrangement_its_records_cannot(self) -> None:
        # The `_provenance` precedent the rest of `docs/captures/` sets: how the
        # arms were set up is arrangement, and no arm record can hold it.
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "capture.jsonl"
            done = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--note",
                    "two Terminal tabs, one tmux client",
                    "--out",
                    str(out),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertEqual(0, done.returncode, done.stderr)
            written = json.loads(out.read_text().splitlines()[0])
            self.assertEqual(recorder.RECORD_NOTE, written["record"])
            printed = recorder.report([written])
            self.assertIn("two Terminal tabs", printed[0])

    def test_a_note_without_a_capture_file_is_refused(self) -> None:
        done = subprocess.run(
            [sys.executable, str(SCRIPT), "--note", "x"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(2, done.returncode)

    def test_a_verdict_over_a_file_with_no_arms_says_so(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "capture.jsonl"
            out.write_text(json.dumps({"record": recorder.RECORD_NOTE, "note": "x"}) + "\n")
            done = subprocess.run(
                [sys.executable, str(SCRIPT), "--verdict", str(out)],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertEqual(1, done.returncode)
            self.assertIn("no arms", done.stderr)


class DisclaimedSpawnTest(unittest.TestCase):
    """A4's mechanism, exercised against a target that moves nothing."""

    ABSENT: ClassVar[str] = "responsibility_spawnattrs_setdisclaim is macOS-only"

    @unittest.skipUnless(sys.platform == "darwin", ABSENT)
    def test_a_disclaimed_child_is_its_own_responsible_process(self) -> None:
        # The one variable this whole capture turns on, measured rather than
        # assumed -- and measured against `/usr/bin/true`, which raises nothing.
        # An ordinary child inherits this process's responsible pid; a
        # disclaimed one answers itself.
        # Falsified by: a disclaimed child still answering the parent's.
        mine = recorder.responsible_pid(os.getpid())
        child, code = recorder._spawn_disclaimed(["/usr/bin/true"], allowed=True)
        self.assertEqual(0, code)
        self.assertIsNotNone(child)
        assert child is not None
        theirs = recorder.responsible_pid(child)
        self.assertEqual(child, theirs)
        self.assertNotEqual(mine, theirs)
        self.assertEqual(0, recorder._reap(child))

    @unittest.skipUnless(sys.platform == "darwin", ABSENT)
    def test_the_child_exit_status_is_recorded_rather_than_the_spawn_result(self) -> None:
        # A spawn succeeds long before the raise it started has an answer, so
        # recording its return would report every A4 as a clean zero.
        # Falsified by: a failing child recorded as 0.
        child, code = recorder._spawn_disclaimed(["/usr/bin/false"], allowed=True)
        self.assertEqual(0, code)
        assert child is not None
        self.assertEqual(1, recorder._reap(child))


if __name__ == "__main__":
    unittest.main()


class MechanismVerdictTest(unittest.TestCase):
    """A socket raise and an Apple Event raise answer different questions.

    Falsified by: the first version of `verdict`, which reduced every positive
    to a statement about the responsible identity. Five tmux arms, none of which
    causes macOS to consult a responsible process at all, composed to
    `only_the_exempt_responsible_identity_raises` -- a causal claim about TCC
    read off arms that never touched it. That is the shape this repository has
    twice shipped and twice had to withdraw, and the instrument built to avoid
    it had it.
    """

    def arm(self, arm_id: str, **over: Any) -> dict[str, Any]:
        # Built through `run_arm` rather than hand-written, so a record that
        # drifts from what the recorder writes fails here too.
        with unittest.mock.patch.object(
            recorder, "_terminal_devices", lambda _r: ["ttys006", "ttys009"]
        ):
            record = recorder.run_arm(
                recorder.ARMS_BY_ID[arm_id],
                allowed=True,
                readers=readers(),
                execute=Spy(),
                spawn=SpawnSpy(),
            )
        mark_moved(record)
        for key, value in over.items():
            record[key] = value
        return record

    def socket_positive(self) -> dict[str, Any]:
        return self.arm("a5")

    def composite(self) -> dict[str, Any]:
        """A6 as it was actually recorded: the tmux half moved, the raise declined.

        Read off `docs/captures/focus/raise-appleevent-macos.jsonl` line 3 rather
        than imagined -- `selected.source` tmux with `changed` true, `frontmost`
        unchanged, tmux step exit 0, `osascript` step exit 1.
        """
        record = self.arm("a6")
        record["frontmost"]["changed"] = False
        record["selected"]["changed"] = True
        record["commands"][0]["exit_status"] = 0
        record["commands"][1]["exit_status"] = 1
        return record

    def test_an_arms_movement_is_credited_to_the_mechanism_that_caused_it(self) -> None:
        # DRC-4389, reproduced over the two committed records rather than
        # imagined: a6 declares BOTH mechanisms, its tmux half moved a pane and
        # its `osascript` half exited 1, and a3's Apple Event moved nothing.
        # Recomputing over those two answered
        # `apple_event_raise=only_from_the_exempt_responsible_identity` -- for a
        # mechanism that failed in both arms that exercised it -- because the
        # verdict read one `moved` flag per arm and both findings read it.
        #
        # Falsified by: a `_finding` that reads `summary["moved"]`.
        cross_app = mark_still(self.arm("a3"))
        found = recorder.verdict([self.composite(), cross_app], base={})
        self.assertEqual("works", found["socket_raise"])
        self.assertEqual(
            "does_not_work",
            found["apple_event_raise"],
            "a6's tmux movement may not stand in for the Apple Event that declined",
        )

    def test_a_mechanism_whose_step_never_ran_contributes_null_rather_than_a_negative(
        self,
    ) -> None:
        # The per-arm null rule, one level down. A step that never ran is not a
        # raise that failed, so an arm that stopped after its tmux half leaves
        # the Apple Event finding unmeasured rather than negative -- the same
        # confident-green failure this file has already had twice, at the
        # mechanism level.
        #
        # Falsified by: attributing a mechanism's answer from the arm's flag
        # rather than from its own step.
        stopped = self.composite()
        del stopped["commands"][1]
        found = recorder.verdict([stopped], base={})
        self.assertEqual("works", found["socket_raise"])
        self.assertEqual("unmeasured", found["apple_event_raise"])

    def test_the_mechanism_of_a_step_is_recoverable_from_a_file_that_predates_the_key(
        self,
    ) -> None:
        # The two committed captures were written before commands declared a
        # mechanism, and `--verdict` over them has to keep reproducing their
        # committed answers. So the reader falls back to the binary in `argv[0]`.
        #
        # Falsified by: reading `command["mechanism"]` directly.
        older = self.composite()
        for command in older["commands"]:
            command.pop("mechanism", None)
        found = recorder.verdict([older, mark_still(self.arm("a3"))], base={})
        self.assertEqual("works", found["socket_raise"])
        self.assertEqual("does_not_work", found["apple_event_raise"])

    def test_every_step_declares_the_mechanism_its_binary_implies(self) -> None:
        # The declaration and the argv have to agree, or the fallback above and
        # the key disagree on the same file. Checked against the arm's own
        # mechanism tuple as well, so a step added to an arm that does not
        # declare its mechanism fails here rather than silently widening a
        # finding.
        for arm in recorder.ARMS:
            steps = recorder.plan(arm, recorder.Targets(device="ttys009"))
            declared: set[str] = set()
            for step in steps:
                with self.subTest(arm=arm.id, purpose=step["purpose"]):
                    self.assertEqual(
                        recorder.mechanism_of(step["argv"]),
                        step["mechanism"],
                        "a step's declared mechanism must match the binary it runs",
                    )
                if step["mechanism"]:
                    declared.add(step["mechanism"])
            with self.subTest(arm=arm.id):
                self.assertEqual(set(arm.mechanism), declared)

    def test_a_socket_raise_claims_nothing_about_the_responsible_identity(self) -> None:
        out = recorder.verdict([self.socket_positive()], base={})
        self.assertEqual("works", out["socket_raise"])
        self.assertEqual(
            "unmeasured",
            out["apple_event_raise"],
            "no arm consulted a responsible identity, so the file may not report one",
        )

    def test_an_apple_event_raise_is_reported_separately_from_a_socket_one(self) -> None:
        apple = self.arm("a1")
        out = recorder.verdict([self.socket_positive(), apple], base={})
        self.assertEqual("works", out["socket_raise"])
        self.assertEqual("only_from_the_exempt_responsible_identity", out["apple_event_raise"])

    def test_controls_alone_do_not_read_as_a_failed_raise(self) -> None:
        # The per-arm rule applied one level up, and the level it was missed on.
        # A control that held still is not a raise that failed: nobody asked it
        # to move. Reading a file of controls as `does_not_work` is the same
        # confident-green failure as reading an unauthorised arm as a negative.
        #
        # Falsified by: a `_finding` that returns `does_not_work` when no
        # must-move arm of that mechanism ran. Measured live: a run where the
        # pty clients failed to attach left a5 and a7 at `ran=0`, and the
        # verdict reported `socket_raise=does_not_work` off a8 and a9 alone.
        controls = [mark_still(self.arm("a8")), mark_still(self.arm("a9"))]
        out = recorder.verdict(controls, base={})
        self.assertTrue(out["controls_held"])
        self.assertEqual(
            "unmeasured",
            out["socket_raise"],
            "two controls holding still say nothing about whether a raise works",
        )

    def test_every_arm_declares_its_mechanism(self) -> None:
        for arm in recorder.ARMS:
            self.assertIsInstance(arm.mechanism, tuple, arm.id)
            for name in arm.mechanism:
                self.assertIn(name, recorder.MECHANISMS, arm.id)


class LauncherQuitArmTest(unittest.TestCase):
    """A2's four phases, driven end to end without a fork, a window or a poll.

    The arm had never worked. Its launcher command carried a literal placeholder
    where a path belonged, so bash read `<a` as a stdin redirect and the daemon
    never started; nothing anywhere read the two files the daemon wrote or wrote
    the one it waited for; the wait step carried an empty argv and the runner's
    own `continue` dropped it; the raise step declared `issued_by: daemon` and
    nothing read it, so the parent issued the raise with the launcher window
    still open -- A1's raise wearing A2's label; the daemon's field names did not
    match the record's; and the quit step named an unresolvable placeholder
    device against a script with no error branch, so it exited 0 having closed
    nothing.

    None of this re-runs the arm. The launcher-quit question is still open, and
    these hold the instrument that would answer it.
    """

    READY: ClassVar[dict[str, Any]] = {
        "pid": 4242,
        "responsible_name": "osascript",
        "responsible_is_self": True,
        "launcher_device": "ttys012",
    }
    DONE: ClassVar[dict[str, Any]] = {
        "raise_issued": True,
        "after_launcher_quit_name": "launchd",
        "after_launcher_quit_is_self": False,
        "exit_status": 0,
    }

    def setUp(self) -> None:
        patch_devices(self, ("ttys006", "ttys009"))
        self.scratch = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.scratch, ignore_errors=True)
        self.handshake = str(Path(self.scratch) / "a2")
        # The scratch directory is removed when the arm finishes, so what the
        # parent wrote into it has to be captured as it is written rather than
        # read back afterwards.
        self.written: list[tuple[str, dict[str, Any]]] = []
        original = recorder._write_json

        def watched(path: str, payload: dict[str, Any]) -> None:
            self.written.append((path, payload))
            original(path, payload)

        patcher = unittest.mock.patch.object(recorder, "_write_json", watched)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_a2(
        self,
        *,
        ready: Any = ...,
        done: Any = ...,
        codes: Sequence[int] = (),
        flags: frozenset[str] = frozenset({recorder.A2_QUIT_FLAG}),
    ) -> tuple[dict[str, Any], Spy, WaitSpy]:
        spy = Spy(codes=codes)
        waiter = WaitSpy(
            ready=self.READY if ready is ... else ready,
            done=self.DONE if done is ... else done,
        )
        with unittest.mock.patch.object(recorder, "_mint_handshake", lambda: self.handshake):
            record = recorder.run_arm(
                recorder.ARMS_BY_ID["a2"],
                allowed=True,
                readers=readers(),
                execute=spy,
                spawn=SpawnSpy(),
                wait=waiter,
                extra_flags=flags,
            )
        return record, spy, waiter

    def test_the_launcher_command_carries_a_path_rather_than_a_placeholder(self) -> None:
        # Defect 1. `<a scratch handshake file this recorder mints>` went
        # verbatim into a shell command, where bash reads `<a` as a stdin
        # redirect: `a: No such file or directory`, and the daemon never ran.
        # The committed capture carries that literal in its recorded argv.
        #
        # Falsified by: a placeholder reaching a command that runs.
        record, spy, _ = self.run_a2()
        launcher = " ".join(spy.calls[0])
        self.assertIn("--a2-handshake", launcher)
        self.assertNotIn(recorder.PLACEHOLDER["handshake"], launcher)
        for metacharacter in ("<", ">", "|", ";", "&"):
            with self.subTest(metacharacter=metacharacter):
                self.assertNotIn(
                    metacharacter,
                    launcher.split("do script ")[1],
                    "the launcher is read by a shell, so a metacharacter in it is a command",
                )
        self.assertIn(self.handshake, launcher)
        del record

    def test_a_minted_handshake_names_a_directory_that_exists(self) -> None:
        # The other half: a path the daemon can actually write to, and one the
        # parent removes rather than leaving behind per invocation.
        minted = recorder._mint_handshake()
        self.addCleanup(shutil.rmtree, os.path.dirname(minted), ignore_errors=True)
        self.assertTrue(os.path.isdir(os.path.dirname(minted)))
        recorder._write_json(minted + recorder.READY_SUFFIX, {"pid": 1})
        self.assertEqual({"pid": 1}, recorder._read_json(minted + recorder.READY_SUFFIX))

    def test_the_wait_for_the_daemon_is_recorded_rather_than_dropped(self) -> None:
        # Defect 3. The step carried `"argv": []` and the runner's
        # `if not step["argv"]: continue` dropped it, so an arm that stalled
        # waiting for a daemon left no trace of having waited at all.
        #
        # Falsified by: a4 commands where three ran.
        record, _, waiter = self.run_a2()
        waits = [c for c in record["commands"] if not c["argv"]]
        self.assertEqual(1, len(waits), "the wait is a step and belongs in the record")
        self.assertTrue(waits[0]["ran"])
        self.assertEqual(0, waits[0]["exit_status"])
        self.assertEqual(4, len(record["commands"]))
        self.assertIn(self.handshake + recorder.READY_SUFFIX, waiter.waited)
        self.assertIn(
            (self.handshake + recorder.RELEASE_SUFFIX, {"launcher_quit": True}), self.written
        )
        self.assertFalse(
            os.path.isdir(self.scratch), "the scratch handshake is removed rather than accumulated"
        )

    def test_a_daemon_that_never_reports_is_a_status_rather_than_a_silence(self) -> None:
        # The same step on the unhappy path. A wait that timed out has to be
        # readable as one, and the two steps behind it must not run.
        record, spy, _ = self.run_a2(ready=None)
        waits = [c for c in record["commands"] if not c["argv"]]
        self.assertEqual(recorder.EXIT_TIMED_OUT, waits[0]["exit_status"])
        self.assertEqual([False, False], [c["ran"] for c in record["commands"][2:]])
        self.assertEqual(1, len(spy.calls), "only the launcher may have run")
        self.assertEqual(recorder.OUTCOME_INCONCLUSIVE, record["outcome"])

    def test_the_raise_is_issued_by_the_daemon_and_never_by_the_parent(self) -> None:
        # Defect 4, and the reason the arm could never answer its question. The
        # step declared `issued_by: detached_daemon_past_its_launcher` and
        # `run_arm` branched only on `spawned`, so the raise went through the
        # ordinary runner with the launcher window still open. That is A1's
        # measurement recorded under A2's name.
        #
        # Falsified by: the parent's executor seeing the raise script.
        record, spy, _ = self.run_a2()
        self.assertEqual(2, len(spy.calls), "the launcher and the quit, and nothing else")
        for call in spy.calls:
            with self.subTest(call=call[-1][:40]):
                self.assertNotIn("focus declined", " ".join(call))
        raised = record["commands"][3]
        self.assertTrue(raised["ran"])
        self.assertEqual(self.DONE["exit_status"], raised["exit_status"])
        self.assertIn("focus declined", " ".join(raised["argv"]))

    def test_the_daemons_exit_status_is_the_one_recorded(self) -> None:
        # Not the parent's, which never ran anything for that step. A daemon
        # whose raise declined has to read as a decline.
        record, _, _ = self.run_a2(done={**self.DONE, "exit_status": 1})
        self.assertEqual(1, record["commands"][3]["exit_status"])

    def test_the_record_carries_the_responsible_identity_the_daemon_measured(self) -> None:
        # Defect 5, both halves. The daemon wrote `responsible_after_quit_name`
        # while the record read `after_launcher_quit_name`, so the field that is
        # the entire difference between A2 and A1 was null in the committed
        # capture; and the `responsible` block that WAS filled came from the
        # recorder's own pid, which every arm shares and which answers Terminal
        # regardless of what the daemon is.
        #
        # Falsified by: a2 reporting the recorder's responsible process.
        record, _, _ = self.run_a2()
        found = record["responsible"]
        self.assertEqual(self.READY["responsible_name"], found["name"])
        self.assertTrue(found["is_self"])
        self.assertEqual(self.DONE["after_launcher_quit_name"], found["after_launcher_quit_name"])
        self.assertIs(False, found["after_launcher_quit_is_self"])
        self.assertNotEqual(recorder.OUTCOME_INCONCLUSIVE, record["outcome"])

    def test_the_quit_step_names_the_device_the_daemon_reported(self) -> None:
        # Defect 6, first half. `_plan_a2` passed the literal
        # `<the launcher's device>`, which no tab can hold, so the step could
        # never have closed the launcher window. The device is not knowable
        # until the daemon reports it, which is why the plan prints a
        # placeholder and the runner rebuilds the argv.
        #
        # Falsified by: a quit argv that survives the handshake unchanged.
        record, spy, _ = self.run_a2()
        quit_argv = " ".join(spy.calls[1])
        self.assertIn(f"/dev/{self.READY['launcher_device']}", quit_argv)
        self.assertNotIn(recorder.PLACEHOLDER["launcher"], quit_argv)
        self.assertIn(
            f"/dev/{self.READY['launcher_device']}", " ".join(record["commands"][2]["argv"])
        )

    def test_a_close_that_finds_no_window_declines_rather_than_succeeding(self) -> None:
        # Defect 6, second half. The script had no `else` and no `error`, unlike
        # the raise script beside it, so `exit_status: 0` did not separate
        # closing the launcher window from finding nothing to close -- and the
        # committed capture records that step at 0 having provably closed
        # nothing, because the device it named cannot exist.
        script = recorder.close_window_on_device("ttys012")
        self.assertIn("error ", script)
        self.assertIn("number 1", script)

    def test_a_quit_that_did_not_close_leaves_the_daemon_unreleased(self) -> None:
        # What the decline above buys. A parent that cannot prove the launcher
        # window is gone must not let the daemon raise, because a raise with the
        # launcher alive is the case three other arms already cover.
        #
        # Falsified by: releasing the daemon on any quit status.
        record, spy, waiter = self.run_a2(codes=(0, 1))
        self.assertEqual(2, len(spy.calls))
        self.assertNotIn(self.handshake + recorder.DONE_SUFFIX, waiter.waited)
        self.assertFalse(record["commands"][3]["ran"])
        self.assertEqual(recorder.OUTCOME_INCONCLUSIVE, record["outcome"])
        self.assertIn(
            (self.handshake + recorder.RELEASE_SUFFIX, {"launcher_quit": False}), self.written
        )

    def test_a2_opens_no_window_without_the_flag_that_closes_it(self) -> None:
        # The leak, and the reason it is a leak: an arm whose gated step is
        # unauthorised is already `inconclusive`, so opening a window it may not
        # close buys no evidence and leaves one on the operator's desk per run.
        #
        # Falsified by: any command running on `--allow-a2` alone.
        record, spy, waiter = self.run_a2(flags=frozenset())
        self.assertEqual([], spy.calls)
        self.assertEqual([], waiter.waited)
        self.assertTrue(all(c["ran"] is False for c in record["commands"]))
        self.assertEqual(recorder.OUTCOME_INCONCLUSIVE, record["outcome"])

    def test_the_daemon_reads_its_controlling_terminal_before_it_detaches(self) -> None:
        # After `setsid` there is no controlling terminal to read, so the order
        # is the whole of it: read late and the launcher's device is null and
        # the quit step has no window it can name.
        #
        # Falsified by: the read moved below the detach.
        source = SCRIPT.read_text(encoding="utf-8")
        body = source.split("def a2_daemon(")[1].split("\ndef ")[0]
        self.assertLess(
            body.index("_controlling_device()"),
            body.index("os.setsid()"),
            "the controlling terminal must be read before the daemon detaches",
        )


class DaemonCoreTest(unittest.TestCase):
    """The daemon's own half, with the fork left out of it.

    `a2_daemon` fused a double fork, a poll, a raise and two file writes into one
    function, which is why it was the only block in the recorder with no test at
    all -- coverage reported its entire body missing -- and why five of the six
    defects lived in it or on the read side it never had. The fork is now a
    wrapper and everything measured is below it.
    """

    def setUp(self) -> None:
        self.scratch = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.scratch, ignore_errors=True)
        self.handshake = str(Path(self.scratch) / "a2")

    def test_the_daemon_reports_what_it_is_before_it_waits(self) -> None:
        # The parent cannot name the launcher window, and cannot tell the
        # daemon's identity from its own, unless this file arrives first.
        spy = Spy()
        recorder.a2_daemon_core(
            self.handshake,
            "ttys009",
            launcher_device="ttys012",
            readers=readers(responsible=4242, name="osascript"),
            execute=spy,
            wait=lambda _path: {"launcher_quit": True},
            pid=4242,
        )
        ready = recorder._read_json(self.handshake + recorder.READY_SUFFIX)
        self.assertEqual(
            {
                "pid": 4242,
                "responsible_name": "osascript",
                "responsible_is_self": True,
                "launcher_device": "ttys012",
            },
            ready,
        )

    def test_a_released_daemon_raises_and_reports_the_fields_the_record_reads(self) -> None:
        # The field names are the defect: the daemon wrote
        # `responsible_after_quit_*` and the record read `after_launcher_quit_*`,
        # with no reader anywhere to notice they had never met.
        #
        # Falsified by: a rename on either side alone.
        spy = Spy(code=0)
        done = recorder.a2_daemon_core(
            self.handshake,
            "ttys009",
            launcher_device="ttys012",
            readers=readers(responsible=4242, name="launchd"),
            execute=spy,
            wait=lambda _path: {"launcher_quit": True},
            pid=4242,
        )
        self.assertEqual(1, len(spy.calls))
        self.assertIn("/dev/ttys009", " ".join(spy.calls[0]))
        self.assertEqual(recorder._read_json(self.handshake + recorder.DONE_SUFFIX), done)
        self.assertTrue(done["raise_issued"])
        self.assertEqual("launchd", done["after_launcher_quit_name"])
        self.assertTrue(done["after_launcher_quit_is_self"])
        self.assertEqual(0, done["exit_status"])
        for field in ("after_launcher_quit_name", "after_launcher_quit_is_self"):
            with self.subTest(field=field):
                self.assertIn(("responsible", field), recorder.ARMS_BY_ID["a2"].requires_evidence)

    def test_the_daemon_issues_no_raise_while_its_launcher_is_alive(self) -> None:
        # The condition that makes A2 a different question from A1. A daemon the
        # parent could not release, or released with the window still standing,
        # raises nothing rather than answering A1's question under A2's name.
        #
        # Falsified by: a raise on any release, or on none.
        for release, why in (
            (None, recorder.A2_NOT_RELEASED),
            ({"launcher_quit": False}, recorder.A2_LAUNCHER_ALIVE),
        ):
            with self.subTest(why=why):
                spy = Spy()
                done = recorder.a2_daemon_core(
                    self.handshake,
                    "ttys009",
                    launcher_device="ttys012",
                    readers=readers(),
                    execute=spy,
                    wait=lambda _path, answer=release: answer,  # type: ignore[misc]
                    pid=4242,
                )
                self.assertEqual([], spy.calls)
                self.assertFalse(done["raise_issued"])
                self.assertEqual(why, done["why"])
                self.assertIsNone(done.get("after_launcher_quit_name"))

    def test_the_wait_gives_up_rather_than_polling_forever(self) -> None:
        # The parent's side of the same handshake, against a file that never
        # arrives. A recorder that blocks here holds an operator's terminal.
        self.assertIsNone(
            recorder._await_json(self.handshake + recorder.DONE_SUFFIX, timeout=0.05, poll=0.01)
        )
        recorder._write_json(self.handshake + recorder.DONE_SUFFIX, {"raise_issued": False})
        self.assertEqual(
            {"raise_issued": False},
            recorder._await_json(self.handshake + recorder.DONE_SUFFIX, timeout=0.05, poll=0.01),
        )

    def test_a_partial_handshake_file_reads_as_not_there_yet(self) -> None:
        # Both sides poll, so a reader can open a file between the writer's
        # `open` and its flush. That is the ordinary case, not an error.
        Path(self.handshake + recorder.READY_SUFFIX).write_text('{"pid": 4', encoding="utf-8")
        self.assertIsNone(recorder._read_json(self.handshake + recorder.READY_SUFFIX))
        Path(self.handshake + recorder.READY_SUFFIX).write_text("[1, 2]", encoding="utf-8")
        self.assertIsNone(recorder._read_json(self.handshake + recorder.READY_SUFFIX))

    def test_the_controlling_terminal_read_answers_a_bare_device_or_nothing(self) -> None:
        # What the daemon reports as its launcher's device, so the parent's quit
        # step can name a window. Read here in whatever this suite runs in: a
        # terminal, or a runner with none. Both are legitimate answers; a
        # `/dev/` prefix or `ps`'s own `??` is not, because the close script
        # builds `/dev/<device>` itself.
        found = recorder._controlling_device()
        if found is not None:
            self.assertNotIn("/", found)
            self.assertNotIn("?", found)

    def test_the_daemon_is_gated_on_the_arms_own_flags(self) -> None:
        # It issues a raise through `_execute`, so it is a way to move a window,
        # so it is gated like every other. A hidden flag is not a gate.
        done = subprocess.run(
            [sys.executable, str(SCRIPT), "--a2-daemon", "--a2-handshake", self.handshake],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(3, done.returncode)
        self.assertIn("Nothing ran", done.stderr)
        self.assertFalse(Path(self.handshake + recorder.READY_SUFFIX).exists())
        # And the launcher passes what the gate demands. The two have to agree
        # or the arm's own daemon refuses itself, which is a gate that measures
        # nothing wearing the clothes of one that does.
        launcher = " ".join(recorder._a2_launcher_argv(self.handshake, "ttys009"))
        self.assertIn(recorder.flag_for("a2"), launcher)
        self.assertIn(recorder.A2_QUIT_FLAG, launcher)
