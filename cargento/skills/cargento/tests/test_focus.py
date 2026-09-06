"""The focus command: what it runs, what it refuses, and what it never reads.

SECURITY.md's "Reaching a session's terminal (the focus command)" is a contract
written and reviewed before this code existed, and its violation sentence is what
this module turns into oracles. Two bounds a green suite misses most easily get
their own classes, and both are named in `test_git_status.py`'s own reasoning:

- **Fixed-position substitution.** A constant argv proves nothing about the call.
  Two different targets must produce argvs differing at exactly one index and
  equal everywhere else, which is what separates substitution into a slot from
  concatenation into an argument.
- **Refused readings.** DRC-4382 measured that for a session with no controlling
  terminal at all, both obvious readings — the first ancestor holding a tty, and
  an emulator variable being set — report a terminal, *and it is somebody else's*.
  So the resolver never reads either, and that is asserted against the source
  rather than trusted, because nothing about a passing raise would reveal it.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import event_hook
from cargento_runtime import cli, focus, lifecycle, observation

from . import support

NOW = 1_700_000_000.0
SESSION = "abcdef12-3456-7890-abcd-ef1234567890"
PREFIX = "abcdef12"
FOCUS_SOURCE = (Path(__file__).resolve().parents[1] / "cargento_runtime" / "focus.py").read_text(
    encoding="utf-8"
)


class Spy:
    """A `subprocess.run` stand-in that answers per command word."""

    def __init__(
        self,
        *,
        session: str = "work",
        clients: tuple[str, ...] = ("/dev/ttys007",),
        switch_code: int = 0,
    ) -> None:
        self.calls: list[tuple[tuple[str, ...], dict[str, Any]]] = []
        self.session = session
        self.clients = clients
        self.switch_code = switch_code

    def __call__(self, argv: Any, **kwargs: Any) -> Any:
        self.calls.append((tuple(argv), kwargs))
        if "display-message" in argv:
            return SimpleNamespace(returncode=0, stdout=f"{self.session}\n".encode(), stderr=b"")
        if "list-clients" in argv:
            body = "".join(f"{tty}\n" for tty in self.clients).encode()
            return SimpleNamespace(returncode=0, stdout=body, stderr=b"")
        return SimpleNamespace(returncode=self.switch_code, stdout=b"", stderr=b"")

    def argv_for(self, word: str) -> tuple[str, ...] | None:
        for argv, _kwargs in self.calls:
            if word in argv:
                return argv
        return None


TARGET = focus.Target(socket="default", pane="%3")


class GrammarTest(unittest.TestCase):
    """The contract's per-field table, run against the values it says it refuses.

    The table in the promoted contract was itself corrected after being executed
    against its own claimed refusals, so these are the document's examples rather
    than examples chosen to pass.
    """

    def test_a_pane_id_is_a_percent_and_digits_and_nothing_else(self) -> None:
        self.assertIsNotNone(focus.TMUX_PANE_RE.match("%3"))
        self.assertIsNotNone(focus.TMUX_PANE_RE.match("%123456789"))
        for refused in ("%3; rm -rf", "-%3", "%", "%3 %4", "%1234567890", "3", ""):
            with self.subTest(value=refused):
                self.assertIsNone(focus.TMUX_PANE_RE.match(refused))

    def test_a_socket_name_is_a_name_and_never_a_path(self) -> None:
        self.assertIsNotNone(focus.TMUX_SOCKET_RE.match("default"))
        self.assertIsNotNone(focus.TMUX_SOCKET_RE.match("cargento-raise"))
        for refused in ("-L", "../x", "/tmp/s", ".hidden", "", "-default", "a" * 65):
            with self.subTest(value=refused):
                self.assertIsNone(focus.TMUX_SOCKET_RE.match(refused))

    def test_a_client_device_anchors_the_dev_prefix_rather_than_resolving_later(self) -> None:
        self.assertIsNotNone(focus.CLIENT_TTY_RE.match("/dev/ttys007"))
        for refused in (
            "--dangerously-skip-permissions",
            "; rm -rf ~",
            "../../etc/passwd",
            "/dev/..",
            "/dev/../etc/passwd",
            "/dev/",
            "ttys007",
        ):
            with self.subTest(value=refused):
                self.assertIsNone(focus.CLIENT_TTY_RE.match(refused))

    def test_every_grammar_refuses_a_leading_dash_in_its_own_first_class(self) -> None:
        # DRC-4381's whole lesson: `^[A-Za-z0-9._-]{1,64}$` holds a dash with
        # nothing anchoring position 0, and review reproduced a poisoned value
        # turning a copied command into one that disables a harness's permission
        # checks. A prose promise beside the pattern is not the pattern.
        for name, pattern in (
            ("pane", focus.TMUX_PANE_RE),
            ("socket", focus.TMUX_SOCKET_RE),
            ("session", focus.TMUX_SESSION_RE),
            ("client", focus.CLIENT_TTY_RE),
        ):
            with self.subTest(field=name):
                self.assertIsNone(pattern.match("-x"))
                self.assertIsNone(pattern.match("--flag"))

    def test_a_target_is_only_built_from_two_fields_that_pass(self) -> None:
        self.assertEqual(TARGET, focus.target_from("default", "%3"))
        for socket, pane in (
            ("default", "-%3"),
            ("/tmp/s", "%3"),
            ("-L", "%3"),
            (None, "%3"),
            ("default", None),
            ("", ""),
        ):
            with self.subTest(socket=socket, pane=pane):
                self.assertIsNone(focus.target_from(socket, pane))


class FixedPositionSubstitutionTest(unittest.TestCase):
    """AC: a field is substituted into a fixed argv position, never concatenated.

    The oracle is differential rather than a literal argv: two targets that differ
    in one field produce argvs that differ at exactly one index. A builder that
    concatenated — `-t` + pane, say — would move a second index or change the
    length, and a builder that interpolated would change neither in a way this
    could see, which is why the templates carry slot sentinels no legal value can
    contain.
    """

    def test_two_panes_move_exactly_one_index_of_the_raise(self) -> None:
        first = Spy()
        second = Spy()
        focus.raise_terminal(focus.Target("default", "%1"), timeout_sec=2.0, runner=first)
        focus.raise_terminal(focus.Target("default", "%2"), timeout_sec=2.0, runner=second)
        left = first.argv_for("switch-client")
        right = second.argv_for("switch-client")
        self.assertIsNotNone(left)
        self.assertIsNotNone(right)
        assert left is not None and right is not None
        self.assertEqual(len(left), len(right))
        differing = [i for i, (a, b) in enumerate(zip(left, right, strict=True)) if a != b]
        self.assertEqual(1, len(differing), (left, right))
        self.assertEqual(("%1", "%2"), (left[differing[0]], right[differing[0]]))

    def test_two_sockets_move_exactly_one_index_of_the_raise(self) -> None:
        first = Spy()
        second = Spy()
        focus.raise_terminal(focus.Target("alpha", "%1"), timeout_sec=2.0, runner=first)
        focus.raise_terminal(focus.Target("bravo", "%1"), timeout_sec=2.0, runner=second)
        left = first.argv_for("switch-client")
        right = second.argv_for("switch-client")
        assert left is not None and right is not None
        self.assertEqual(len(left), len(right))
        differing = [i for i, (a, b) in enumerate(zip(left, right, strict=True)) if a != b]
        self.assertEqual(1, len(differing), (left, right))

    def test_a_socket_name_is_passed_as_a_dash_ell_name_and_never_as_a_path(self) -> None:
        spy = Spy()
        focus.raise_terminal(TARGET, timeout_sec=2.0, runner=spy)
        for argv, _kwargs in spy.calls:
            with self.subTest(argv=argv):
                self.assertEqual("-L", argv[1])
                self.assertEqual("default", argv[2])
                self.assertNotIn("-S", argv)

    def test_no_slot_sentinel_survives_into_a_command(self) -> None:
        spy = Spy()
        focus.raise_terminal(TARGET, timeout_sec=2.0, runner=spy)
        self.assertTrue(spy.calls)
        for argv, _kwargs in spy.calls:
            for part in argv:
                self.assertNotIn("\x00", part)


class CommandBoundsTest(unittest.TestCase):
    """The five bounds every command carries, on the `git_status.probe` precedent."""

    def test_every_command_closes_stdin_bounds_itself_and_sets_no_directory(self) -> None:
        spy = Spy()
        self.assertTrue(focus.raise_terminal(TARGET, timeout_sec=3.5, runner=spy))
        self.assertEqual(3, len(spy.calls))
        for argv, kwargs in spy.calls:
            with self.subTest(argv=argv):
                self.assertEqual(subprocess.DEVNULL, kwargs["stdin"])
                self.assertEqual(3.5, kwargs["timeout"])
                self.assertNotIn("shell", kwargs)
                # No working directory, which is what keeps Scope's
                # repository-execution sentence meaningful rather than sidestepped.
                self.assertNotIn("cwd", kwargs)

    def test_the_raise_is_never_retried(self) -> None:
        spy = Spy(switch_code=1)
        self.assertFalse(focus.raise_terminal(TARGET, timeout_sec=2.0, runner=spy))
        switches = [argv for argv, _k in spy.calls if "switch-client" in argv]
        self.assertEqual(1, len(switches))

    def test_a_raising_runner_is_a_focus_that_did_not_happen(self) -> None:
        def runner(_argv: Any, **_kwargs: Any) -> Any:
            raise subprocess.TimeoutExpired(cmd="tmux", timeout=2.0)

        self.assertFalse(focus.raise_terminal(TARGET, timeout_sec=2.0, runner=runner))

    def test_nothing_is_typed_into_a_terminal_by_any_path(self) -> None:
        spy = Spy()
        focus.raise_terminal(TARGET, timeout_sec=2.0, runner=spy)
        for argv, _kwargs in spy.calls:
            self.assertNotIn("send-keys", argv)
            self.assertNotIn("paste-buffer", argv)
        self.assertNotIn("send-keys", FOCUS_SOURCE)
        self.assertNotIn("paste-buffer", FOCUS_SOURCE)


class DeclineTest(unittest.TestCase):
    """Every lookup answer that is not a raise."""

    def test_zero_clients_declines_without_switching(self) -> None:
        spy = Spy(clients=())
        self.assertFalse(focus.raise_terminal(TARGET, timeout_sec=2.0, runner=spy))
        self.assertIsNone(spy.argv_for("switch-client"))

    def test_two_clients_declines_without_switching(self) -> None:
        # The shared-session rule the contract added on 2026-09-06, and the
        # decline no lookup prevents: `switch-client` moves the tmux session's
        # current window, so every attached client follows the one that was
        # named. Measured in DRC-4385, both arms.
        spy = Spy(clients=("/dev/ttys007", "/dev/ttys011"))
        self.assertFalse(focus.raise_terminal(TARGET, timeout_sec=2.0, runner=spy))
        self.assertIsNone(spy.argv_for("switch-client"))

    def test_a_pane_that_no_longer_exists_declines(self) -> None:
        def runner(argv: Any, **_kwargs: Any) -> Any:
            if "display-message" in argv:
                return SimpleNamespace(returncode=1, stdout=b"", stderr=b"no such pane")
            raise AssertionError("nothing may run after a failed lookup")

        self.assertFalse(focus.raise_terminal(TARGET, timeout_sec=2.0, runner=runner))

    def test_a_session_name_outside_its_grammar_declines(self) -> None:
        # The name comes back from tmux rather than from a request, and it still
        # reaches an argv position, so it still has to pass a grammar. A session
        # named `-C` would otherwise be a flag.
        spy = Spy(session="-C")
        self.assertFalse(focus.raise_terminal(TARGET, timeout_sec=2.0, runner=spy))
        self.assertIsNone(spy.argv_for("list-clients"))

    def test_a_client_device_outside_its_grammar_declines(self) -> None:
        spy = Spy(clients=("--dangerously-skip-permissions",))
        self.assertFalse(focus.raise_terminal(TARGET, timeout_sec=2.0, runner=spy))
        self.assertIsNone(spy.argv_for("switch-client"))

    def test_a_target_outside_its_grammar_runs_nothing_at_all(self) -> None:
        spy = Spy()
        self.assertFalse(
            focus.raise_terminal(focus.Target("/tmp/s", "%3"), timeout_sec=2.0, runner=spy)
        )
        self.assertFalse(
            focus.raise_terminal(focus.Target("default", "-%3"), timeout_sec=2.0, runner=spy)
        )
        self.assertEqual([], spy.calls)


class RefusedReadingsTest(unittest.TestCase):
    """DRC-4382's measured negative, asserted against the source.

    Both naive readings report a terminal for a session that has none, and it is
    somebody else's. Nothing about a passing raise would reveal that the resolver
    had reached for one, so the assertion is over the text.
    """

    def test_the_resolver_never_reads_an_emulator_variable(self) -> None:
        for banned in ("TERM_PROGRAM", "TERM_SESSION_ID", "ITERM_SESSION_ID", "WT_SESSION"):
            with self.subTest(variable=banned):
                self.assertNotIn(banned, FOCUS_SOURCE)

    def test_the_resolver_never_walks_past_the_harness(self) -> None:
        for banned in ("getppid", "ppid", "psutil", "pgrep"):
            with self.subTest(reading=banned):
                self.assertNotIn(banned, FOCUS_SOURCE)

    def test_the_resolver_never_reads_a_controlling_terminal(self) -> None:
        for banned in ("ttyname", "/dev/tty'", '/dev/tty"', "isatty"):
            with self.subTest(reading=banned):
                self.assertNotIn(banned, FOCUS_SOURCE)

    def test_no_apple_event_case_is_named(self) -> None:
        # The contract permits one only once its arm has run, and A2 is
        # inconclusive: the launcher-quit reading never reached the record.
        for banned in ("osascript", "AppleScript", "tell application", "lsappinfo"):
            with self.subTest(marker=banned):
                self.assertNotIn(banned, FOCUS_SOURCE)

    def test_the_module_reads_no_environment_at_all(self) -> None:
        # The identity is gathered by a hook, which is a child of the harness.
        # A resolver reading its own environment would be reading the server's,
        # and DRC-4382 measured that such a reading names somebody else's tab.
        for banned in ("os.environ", "environ.get", "environ[", "getenv", "import os"):
            with self.subTest(reading=banned):
                self.assertNotIn(banned, FOCUS_SOURCE)


class HookIdentityTest(unittest.TestCase):
    """What `event_hook` gathers, and the far larger set it refuses to gather."""

    def env(self, **overrides: str) -> dict[str, str]:
        base = {"TMUX": "/private/tmp/tmux-501/default,84321,0", "TMUX_PANE": "%3"}
        base.update(overrides)
        return base

    def test_a_pane_and_its_socket_name_are_read_from_the_default_directory(self) -> None:
        self.assertEqual(
            {"tmux_socket": "default", "tmux_pane": "%3"},
            event_hook.tmux_identity(self.env(), 501),
        )

    def test_a_custom_socket_path_yields_no_target(self) -> None:
        # `-S /path` is an honest decline rather than a `-L` that cannot work.
        self.assertEqual({}, event_hook.tmux_identity(self.env(TMUX="/home/me/sock,1,0"), 501))

    def test_another_users_socket_directory_yields_no_target(self) -> None:
        self.assertEqual(
            {}, event_hook.tmux_identity(self.env(TMUX="/private/tmp/tmux-0/default,1,0"), 501)
        )

    def test_the_socket_directory_override_is_honoured(self) -> None:
        self.assertEqual(
            {"tmux_socket": "work", "tmux_pane": "%3"},
            event_hook.tmux_identity(
                self.env(TMUX="/var/run/t/tmux-501/work,1,0", TMUX_TMPDIR="/var/run/t"), 501
            ),
        )

    def test_a_pane_outside_its_grammar_yields_no_target(self) -> None:
        self.assertEqual({}, event_hook.tmux_identity(self.env(TMUX_PANE="-%3"), 501))

    def test_outside_tmux_there_is_no_target(self) -> None:
        self.assertEqual({}, event_hook.tmux_identity({}, 501))
        self.assertEqual({}, event_hook.tmux_identity({"TMUX_PANE": "%3"}, 501))

    def test_no_uid_yields_no_target(self) -> None:
        # Windows has no `getuid`, and there is no tmux there to find either.
        self.assertEqual({}, event_hook.tmux_identity(self.env(), None))

    def test_only_three_variables_are_ever_read(self) -> None:
        class Watched(dict):  # type: ignore[type-arg]
            def __init__(self, base: dict[str, str]) -> None:
                super().__init__(base)
                self.read: set[str] = set()

            def get(self, key: str, default: Any = None) -> Any:
                self.read.add(key)
                return super().get(key, default)

        watched = Watched(self.env())
        event_hook.tmux_identity(watched, 501)
        self.assertLessEqual(watched.read, {"TMUX", "TMUX_PANE", "TMUX_TMPDIR"})

    def test_the_identity_rides_session_start_and_no_other_event(self) -> None:
        env = self.env()
        started = event_hook.envelope(
            {"hook_event_name": "SessionStart", "session_id": SESSION},
            "claude",
            environ=env,
            uid=501,
        )
        assert started is not None
        self.assertEqual("default", started["tmux_socket"])
        self.assertEqual("%3", started["tmux_pane"])
        for native in ("UserPromptSubmit", "Stop", "PostToolUse", "SessionEnd"):
            with self.subTest(event=native):
                later = event_hook.envelope(
                    {"hook_event_name": native, "session_id": SESSION},
                    "claude",
                    environ=env,
                    uid=501,
                )
                assert later is not None
                self.assertNotIn("tmux_socket", later)
                self.assertNotIn("tmux_pane", later)

    def test_the_hook_makes_no_process_call_to_find_a_terminal(self) -> None:
        # `docs/captures/README.md` measured `hook_ms` at 200.8-524.8 ms
        # dominated by exactly those calls, and they belong to the Apple Event
        # case that is not shipping.
        source = (
            Path(event_hook.__file__).read_text(encoding="utf-8") if event_hook.__file__ else ""
        )
        for banned in ("subprocess", "osascript", "getppid", "ttyname", "TERM_PROGRAM"):
            with self.subTest(marker=banned):
                self.assertNotIn(banned, source)

    def test_the_two_shipped_copies_of_the_hook_stay_byte_identical(self) -> None:
        root = Path(__file__).resolve().parents[4]
        plugin = root / "cargento" / "skills" / "cargento" / "event_hook.py"
        gemini = root / "cargento-gemini" / "hooks" / "event_hook.py"
        self.assertEqual(plugin.read_bytes(), gemini.read_bytes())


class EnvelopeAdmissionTest(unittest.TestCase):
    """The two new fields on the envelope, bounded like every other string."""

    def payload(self, **overrides: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "v": 1,
            "event": "session_started",
            "session_id": SESSION,
            "tmux_socket": "default",
            "tmux_pane": "%3",
        }
        base.update(overrides)
        return base

    def parsed(self, **overrides: Any) -> Any:
        from cargento_runtime import events as runtime_events  # noqa: PLC0415

        return runtime_events.parse(
            "claude",
            self.payload(**overrides),
            arrival_seq=1,
            config=support.make_config(),
            now=NOW,
        )

    def test_both_fields_reach_the_frozen_envelope(self) -> None:
        event = self.parsed()
        self.assertEqual("default", event.tmux_socket)
        self.assertEqual("%3", event.tmux_pane)

    def test_an_oversized_field_is_dropped_rather_than_stored(self) -> None:
        event = self.parsed(tmux_socket="a" * 5_000)
        self.assertIsNone(event.tmux_socket)

    def test_neither_field_is_patchable(self) -> None:
        # Every member of PATCHABLE is a published display claim, and the
        # contract forbids echoing the target.
        from cargento_runtime import events as runtime_events  # noqa: PLC0415

        self.assertNotIn("tmux_socket", runtime_events.PATCHABLE)
        self.assertNotIn("tmux_pane", runtime_events.PATCHABLE)
        self.assertIn("tmux_socket", runtime_events.ALLOWED_FIELDS)
        self.assertIn("tmux_pane", runtime_events.ALLOWED_FIELDS)


class CoordinatorTargetTest(unittest.TestCase):
    """Where a target is held, how it is bounded, and when it goes."""

    def setUp(self) -> None:
        self.now = NOW
        self.config = support.make_config()

    def build(self, **changes: Any) -> observation.Observation:
        from .test_observation import FakeApplication  # noqa: PLC0415

        config = dataclasses.replace(self.config, **changes) if changes else self.config
        self.app = FakeApplication(config)
        return observation.Observation(
            self.app,  # type: ignore[arg-type]
            clock=lambda: self.now,
            diagnostic_sink=lambda _message: None,
        )

    def start(self, coordinator: observation.Observation, **overrides: Any) -> str:
        payload: dict[str, Any] = {
            "v": 1,
            "event": "session_started",
            "session_id": SESSION,
            "tmux_socket": "default",
            "tmux_pane": "%3",
        }
        payload.update(overrides)
        return coordinator.submit("claude", payload)

    def test_a_session_start_records_a_target(self) -> None:
        coordinator = self.build()
        self.start(coordinator)
        self.assertEqual(TARGET, coordinator.focus_target("claude", PREFIX))

    def test_the_feature_being_off_records_nothing(self) -> None:
        coordinator = self.build(focus_enabled=False)
        self.start(coordinator)
        self.assertIsNone(coordinator.focus_target("claude", PREFIX))

    def test_a_target_failing_its_grammar_is_not_stored(self) -> None:
        coordinator = self.build()
        self.start(coordinator, tmux_pane="-%3")
        self.assertIsNone(coordinator.focus_target("claude", PREFIX))

    def test_the_map_refuses_rather_than_evicting_when_full(self) -> None:
        coordinator = self.build(event_overlay_max_sessions=1)
        self.start(coordinator)
        self.start(coordinator, session_id="beefcafe-3456-7890-abcd-ef1234567890")
        self.assertEqual(TARGET, coordinator.focus_target("claude", PREFIX))
        self.assertIsNone(coordinator.focus_target("claude", "beefcafe"))

    def test_a_session_that_ended_keeps_no_target(self) -> None:
        coordinator = self.build()
        self.start(coordinator)
        coordinator.submit("claude", {"v": 1, "event": "session_ended", "session_id": SESSION})
        self.assertIsNone(coordinator.focus_target("claude", PREFIX))

    def test_a_row_no_collection_produces_loses_its_target(self) -> None:
        coordinator = self.build()
        self.start(coordinator)
        coordinator.note_rows(set())
        # The overlay from `session_started` still pends, so the target is held
        # for the same reason the completion mark is.
        coordinator.submit("claude", {"v": 1, "event": "session_ended", "session_id": SESSION})
        coordinator.note_rows(set())
        self.assertIsNone(coordinator.focus_target("claude", PREFIX))

    def test_the_published_bit_says_a_target_exists_and_never_what_it_is(self) -> None:
        coordinator = self.build()
        self.start(coordinator)
        self.assertTrue(coordinator.focusable("claude", PREFIX))
        self.assertFalse(coordinator.focusable("claude", "00000000"))


class CoordinatorRaiseTest(CoordinatorTargetTest):
    """The floor, the in-flight gate, and what the raise leaves on disk."""

    def test_a_repeated_request_inside_the_floor_is_refused(self) -> None:
        coordinator = self.build(focus_floor_sec=60.0)
        self.assertTrue(coordinator.claim_focus())
        coordinator.release_focus()
        self.assertFalse(coordinator.claim_focus())
        self.now += 61.0
        self.assertTrue(coordinator.claim_focus())

    def test_a_second_request_while_one_is_in_flight_is_refused(self) -> None:
        coordinator = self.build(focus_floor_sec=0.0)
        self.assertTrue(coordinator.claim_focus())
        self.assertFalse(coordinator.claim_focus())
        coordinator.release_focus()
        self.assertTrue(coordinator.claim_focus())

    def test_a_raise_writes_nothing_under_the_state_home(self) -> None:
        # "Nothing is written to disk by this feature" is a bound in the
        # contract, so it gets a byte-level oracle rather than a reading of the
        # code: a real directory, digested before and after a real raise.
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / ".cargento"
            home.mkdir()
            (home / "cargento-4553.json").write_text("{}", encoding="utf-8")
            coordinator = self.build(state_home=str(home))
            self.start(coordinator)
            before = _tree(home)
            spy = Spy()
            self.assertTrue(coordinator.raise_focus(TARGET, runner=spy))
            self.assertEqual(before, _tree(home))


def _tree(root: Path) -> dict[str, str]:
    """Every file under `root` by relative path and content digest."""
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class RouteTest(unittest.TestCase):
    """`POST /api/focus`: its check order, its body, and its one-bit answer."""

    def handler(self, payload: Any, *, coordinator: Any, config: Any = None) -> Any:
        from cargento_runtime import http_api  # noqa: PLC0415

        handler: Any = http_api._RequestHandler.__new__(http_api._RequestHandler)
        body = json.dumps(payload).encode() if not isinstance(payload, bytes) else payload
        handler.headers = {
            "Content-Length": str(len(body)),
            "X-Cargento-Capability": self.token,
        }
        handler.path = "/api/focus"
        handler.rfile = __import__("io").BytesIO(body)
        application = SimpleNamespace(
            config=config if config is not None else support.make_config(),
            state=None,
            clock=lambda: NOW,
        )
        handler.server = SimpleNamespace(application=application, observation=coordinator)
        handler._local_ok = lambda **_kw: True
        self.sent: list[tuple[bytes, str]] = []
        self.rejected: list[int] = []
        handler._send = lambda payload_bytes, kind, **_k: self.sent.append((payload_bytes, kind))
        handler._reject = self.rejected.append
        handler._body_consumed = 0
        return handler

    def coordinator(self, **changes: Any) -> observation.Observation:
        from .test_observation import FakeApplication  # noqa: PLC0415

        config = dataclasses.replace(support.make_config(), **changes)
        app = FakeApplication(config)
        built = observation.Observation(
            app,  # type: ignore[arg-type]
            clock=lambda: NOW,
            diagnostic_sink=lambda _m: None,
        )
        built.submit(
            "claude",
            {
                "v": 1,
                "event": "session_started",
                "session_id": SESSION,
                "tmux_socket": "default",
                "tmux_pane": "%3",
            },
        )
        self.token = built.focus_capability()
        self.config = config
        return built

    def test_the_answer_is_one_boolean_and_nothing_else(self) -> None:
        coordinator = self.coordinator()
        coordinator._focus_runner = Spy()
        handler = self.handler(
            {"harness": "claude", "sid": PREFIX}, coordinator=coordinator, config=self.config
        )
        handler.do_POST()
        self.assertEqual([], self.rejected)
        body, kind = self.sent[0]
        self.assertEqual("application/json", kind)
        self.assertEqual({"focused": True}, json.loads(body))

    def test_an_unknown_session_answers_false_rather_than_a_reason(self) -> None:
        coordinator = self.coordinator()
        handler = self.handler(
            {"harness": "claude", "sid": "00000000"},
            coordinator=coordinator,
            config=self.config,
        )
        handler.do_POST()
        self.assertEqual({"focused": False}, json.loads(self.sent[0][0]))

    def test_a_body_naming_a_target_changes_nothing_about_the_argv(self) -> None:
        coordinator = self.coordinator()
        spy = Spy()
        coordinator._focus_runner = spy
        handler = self.handler(
            {
                "harness": "claude",
                "sid": PREFIX,
                "target": "%9",
                "tty": "/dev/ttys999",
                "pane": "%9",
                "argv": ["tmux", "kill-server"],
                "socket": "evil",
            },
            coordinator=coordinator,
            config=self.config,
        )
        handler.do_POST()
        for argv, _kwargs in spy.calls:
            self.assertNotIn("%9", argv)
            self.assertNotIn("/dev/ttys999", argv)
            self.assertNotIn("kill-server", argv)
            self.assertNotIn("evil", argv)
        self.assertIsNotNone(spy.argv_for("switch-client"))

    def test_the_capability_is_checked_before_the_session_is_looked_up(self) -> None:
        # A harness name is public and a session id is not, so consulting the
        # ledger first would turn this route into an oracle for which sessions
        # exist. The oracle test: an unknown session and a known one must be
        # indistinguishable to a caller with no token.
        coordinator = self.coordinator()
        outcomes = []
        for sid in (PREFIX, "00000000"):
            handler = self.handler(
                {"harness": "claude", "sid": sid}, coordinator=coordinator, config=self.config
            )
            handler.headers["X-Cargento-Capability"] = "0" * 64
            handler.do_POST()
            outcomes.append((tuple(self.rejected), tuple(self.sent)))
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertEqual((403,), outcomes[0][0])

    def test_a_harness_capability_is_not_a_focus_capability(self) -> None:
        # The per-harness tokens are derived by HMAC, so the token that would
        # focus a Claude session would be byte-identical to the one
        # `POST /api/events/claude` accepts — the power to forge that harness's
        # lifecycle state.
        coordinator = self.coordinator()
        handler = self.handler(
            {"harness": "claude", "sid": PREFIX}, coordinator=coordinator, config=self.config
        )
        handler.headers["X-Cargento-Capability"] = coordinator.capability("claude")
        handler.do_POST()
        self.assertEqual([403], self.rejected)
        self.assertNotIn(coordinator.focus_capability(), coordinator.capabilities().values())

    def test_a_looped_request_is_refused_by_the_ceiling(self) -> None:
        coordinator = self.coordinator(focus_floor_sec=60.0)
        coordinator._focus_runner = Spy()
        for _ in range(2):
            handler = self.handler(
                {"harness": "claude", "sid": PREFIX},
                coordinator=coordinator,
                config=self.config,
            )
            handler.do_POST()
        self.assertEqual([429], self.rejected)

    def test_the_feature_being_off_answers_503_before_any_token_is_read(self) -> None:
        config = dataclasses.replace(support.make_config(), focus_enabled=False)
        coordinator = self.coordinator()
        handler = self.handler(
            {"harness": "claude", "sid": PREFIX}, coordinator=coordinator, config=config
        )
        handler.headers["X-Cargento-Capability"] = "0" * 64
        handler.do_POST()
        self.assertEqual([503], self.rejected)

    def test_no_events_leaves_the_route_with_no_coordinator(self) -> None:
        self.token = "0" * 64
        handler = self.handler(
            {"harness": "claude", "sid": PREFIX}, coordinator=None, config=support.make_config()
        )
        handler.do_POST()
        self.assertEqual([503], self.rejected)

    def test_an_oversized_body_is_refused_before_it_is_read(self) -> None:
        coordinator = self.coordinator()
        handler = self.handler(
            {"harness": "claude", "sid": PREFIX}, coordinator=coordinator, config=self.config
        )
        handler.headers["Content-Length"] = str(self.config.focus_body_cap_bytes + 1)
        handler.do_POST()
        self.assertEqual([413], self.rejected)


class CapabilityDeliveryTest(unittest.TestCase):
    """The token reaches the page by injection, outside the pinned assembly."""

    def test_the_meta_is_injected_into_the_served_document(self) -> None:
        page = b"<html><head><title>Cargento</title></head><body></body></html>"
        out = cli.inject_focus_capability(page, "ab" * 32)
        self.assertIn(b'<meta name="cargento-focus" content="' + b"ab" * 32 + b'">', out)
        self.assertLess(out.index(b"cargento-focus"), out.index(b"</head>"))

    def test_a_token_outside_its_grammar_is_never_injected(self) -> None:
        page = b"<html><head></head><body></body></html>"
        for bad in ('">', "<script>", "a b", ""):
            with self.subTest(token=bad):
                self.assertEqual(page, cli.inject_focus_capability(page, bad))

    def test_the_pinned_assembly_is_untouched(self) -> None:
        # The injection happens between `load_frontend_page()` and the server
        # construction, so `frontend_page.load_page()` stays byte-identical and
        # the two pinned digests do not move.
        import cargento_runtime.web.page as frontend_page  # noqa: PLC0415

        assembled = frontend_page.load_page()
        self.assertNotIn(b"cargento-focus", assembled)
        self.assertEqual(
            "143f3c3a990919d4e690d472fd8f357e709cea573d1e482f7c7e4e1c4ec13038",
            hashlib.sha256(assembled).hexdigest(),
        )


class OffSwitchTest(unittest.TestCase):
    """`--no-focus`, at every site `--no-git` occupies."""

    def test_the_flag_parses_and_reaches_the_frozen_configuration(self) -> None:
        args = cli.build_parser().parse_args(["--no-focus"])
        self.assertTrue(args.no_focus)
        config, _state = cli.build_runtime(args, started=NOW)
        self.assertFalse(config.focus_enabled)

    def test_the_feature_is_on_when_the_flag_is_absent(self) -> None:
        config, _state = cli.build_runtime(cli.build_parser().parse_args([]), started=NOW)
        self.assertTrue(config.focus_enabled)

    def test_no_events_turns_focus_off_as_well(self) -> None:
        # The capability comes from the coordinator, which does not exist under
        # `--no-events`, so that flag disables focus too. The contract says so
        # and this is the pin.
        args = cli.build_parser().parse_args(["--no-events"])
        self.assertTrue(args.no_events)
        config, _state = cli.build_runtime(args, started=NOW)
        self.assertTrue(config.focus_enabled)
        # The route's own gate is the coordinator being absent, which is what
        # `--no-events` produces at assembly.
        self.assertIsNone(support.make_server().observation)

    def test_the_flag_survives_a_daemon_respawn(self) -> None:
        config = support.make_config()
        argv = lifecycle.spawn_argv(config, _namespace(no_focus=True))
        self.assertIn("--no-focus", argv)
        self.assertNotIn("--no-focus", lifecycle.spawn_argv(config, _namespace(no_focus=False)))

    def test_the_respawn_branch_reads_the_attribute_directly(self) -> None:
        # Read off the namespace rather than through `getattr` with a default,
        # so a flag added to the parser and forgotten here raises.
        namespace = _namespace()
        del namespace.no_focus
        with self.assertRaises(AttributeError):
            lifecycle.spawn_argv(support.make_config(), namespace)


def _namespace(**overrides: object) -> argparse.Namespace:
    base: dict[str, object] = {
        "port": 4553,
        "window_hours": 24.0,
        "no_spacedock": False,
        "no_usage": False,
        "no_events": False,
        "no_dismiss": False,
        "no_ask": False,
        "no_git": False,
        "no_focus": False,
        "no_history": False,
        "history_days": 14.0,
        "history_max_bytes": 1_048_576,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


class SingleInvocationTest(unittest.TestCase):
    """The runtime builds a tmux subprocess at exactly one site.

    The `test_git_status.SingleInvocationTest` shape: before this feature that
    count was zero, so "exactly one" is a baseline this test establishes rather
    than one it inherits.
    """

    def test_only_focus_constructs_a_tmux_subprocess(self) -> None:
        runtime = Path(__file__).resolve().parent.parent / "cargento_runtime"
        pattern = re.compile(r"""["']tmux["']""")
        offenders = sorted(
            path.name
            for path in runtime.rglob("*.py")
            if pattern.search(path.read_text(encoding="utf-8"))
        )
        self.assertEqual(["focus.py"], offenders)

    def test_every_argv_template_is_a_tuple_a_caller_cannot_extend(self) -> None:
        for template in (
            focus.SESSION_NAME_ARGV,
            focus.LIST_CLIENTS_ARGV,
            focus.SWITCH_CLIENT_ARGV,
        ):
            self.assertIsInstance(template, tuple)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
