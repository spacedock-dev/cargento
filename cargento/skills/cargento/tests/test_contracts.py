from __future__ import annotations

import ast
import contextlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar
from unittest import mock

from cargento_runtime import aggregate
from cargento_runtime import sessions as runtime_sessions
from cargento_runtime.collectors import codex as codex_collector

from . import test_claude, test_codex, test_copilot, test_droid, test_pi
from .fixtures import (
    HARNESSES,
    STORE_CONSTANTS,
    build_opencode,
    build_pi,
)
from .support import (
    HarnessContractTestCase,
    LegacyDashboardTestCase,
    dashboard,
    make_runtime,
)

SKILL_DIR = Path(__file__).resolve().parents[1]
RUNTIME_DIR = SKILL_DIR / "cargento_runtime"
RUNTIME_PREFIX = "cargento_runtime"
FORBIDDEN_RUNTIME_PREFIX = "cargento.skills.cargento.cargento_runtime"

if TYPE_CHECKING:
    from cargento_runtime.config import RuntimeConfig
    from cargento_runtime.state import RuntimeState


class ApplicationIsolationTest(unittest.TestCase):
    """Two applications in one process must share nothing.

    The design requires it because a contract test starts two servers with
    different configurations and proves requests and notification state do not
    cross. Everything asserted here is what "do not cross" has to mean.
    """

    @staticmethod
    def _spec(
        key: str,
        *,
        discover_error: BaseException | None = None,
        collect_error: BaseException | None = None,
        sessions: int = 1,
    ) -> aggregate.HarnessSpec:
        """A runtime-native harness: it reads the config and state it is given."""

        def discover(config: RuntimeConfig, state: RuntimeState) -> bool:
            if discover_error is not None:
                raise discover_error
            state.store_errors[f"{key}-discovered"] = config.home
            return True

        def collect(
            config: RuntimeConfig,
            state: RuntimeState,
            now: float,
            window_hours: float,
            show_all: bool,
        ) -> list[dict[str, Any]]:
            if collect_error is not None:
                raise collect_error
            rows = []
            for index in range(sessions):
                row = runtime_sessions.base_session(key, f"{key}-{index}", config.home)
                # Carry the inputs into the row so a crossed config, state,
                # clock or window is visible in the collection itself.
                row["last_activity"] = now
                row["title"] = f"{id(state)}|{window_hours}|{show_all}"
                rows.append(row)
            return rows

        return aggregate.HarnessSpec(key=key, label=key.title(), discover=discover, collect=collect)

    def _application(
        self,
        *,
        home: str,
        started: float,
        clock: float,
        notifier: str,
        harnesses: tuple[aggregate.HarnessSpec, ...],
        platform_name: str = "linux",
    ) -> tuple[aggregate.Application, RuntimeConfig, RuntimeState, list[str], list[str]]:
        config, state = make_runtime(started=started, home=home, platform_name=platform_name)
        diagnostics: list[str] = []
        popups: list[str] = []
        application = aggregate.Application(
            config,
            state,
            harnesses,
            # Echo the argument: the field must be derived from this
            # application's platform, never from ambient sys.platform.
            native_notifier=lambda platform: f"{notifier}@{platform}",
            popup_notifier=lambda title, message: popups.append(f"{title}:{message}"),
            diagnostic_sink=diagnostics.append,
            clock=lambda: clock,
        )
        return application, config, state, diagnostics, popups

    def test_two_applications_share_no_config_state_memo_clock_or_notifier(self) -> None:
        first, config_a, state_a, diag_a, popups_a = self._application(
            home="/home/a",
            started=11.0,
            clock=1000.0,
            notifier="notifier-a",
            harnesses=(self._spec("alpha"),),
        )
        second, config_b, state_b, diag_b, popups_b = self._application(
            home="/home/b",
            started=22.0,
            clock=2000.0,
            notifier="notifier-b",
            harnesses=(self._spec("beta"),),
            platform_name="win32",
        )

        data_a = first.collect(show_all=True)
        data_b = second.collect(show_all=True)

        # The clock is per application, so "generated" cannot be shared.
        self.assertEqual(1000.0, data_a["generated"])
        self.assertEqual(2000.0, data_b["generated"])
        # The native-notify field comes from the injected notifier, called with
        # this application's platform. Mutation-checked: reading sys.platform
        # here instead of config.platform_name previously passed the suite.
        self.assertEqual(f"notifier-a@{config_a.platform_name}", data_a["native_notify"])
        self.assertEqual(f"notifier-b@{config_b.platform_name}", data_b["native_notify"])
        self.assertNotEqual(config_a.platform_name, config_b.platform_name)
        # Each application saw only its own registry.
        self.assertEqual(["alpha"], [h["key"] for h in data_a["harnesses"]])
        self.assertEqual(["beta"], [h["key"] for h in data_b["harnesses"]])
        # Each collector read its own config and state, not the other's.
        self.assertEqual(["/home/a"], [s["project"] for s in data_a["sessions"]])
        self.assertEqual(["/home/b"], [s["project"] for s in data_b["sessions"]])
        self.assertEqual(
            f"{id(state_a)}|{config_a.window_hours}|True", data_a["sessions"][0]["title"]
        )
        self.assertEqual(
            f"{id(state_b)}|{config_b.window_hours}|True", data_b["sessions"][0]["title"]
        )
        # Discovery also received the right config and state.
        self.assertEqual({"alpha-discovered": "/home/a"}, state_a.store_errors)
        self.assertEqual({"beta-discovered": "/home/b"}, state_b.store_errors)
        # Separate sinks, separate popup notifiers, separate start times.
        self.assertEqual(([], []), (diag_a, diag_b))
        self.assertIsNot(popups_a, popups_b)
        self.assertEqual((11.0, 22.0), (state_a.server_started, state_b.server_started))

    def test_the_collection_memo_does_not_cross_applications(self) -> None:
        first, _, state_a, _, _ = self._application(
            home="/home/a",
            started=11.0,
            clock=1000.0,
            notifier="notifier-a",
            harnesses=(self._spec("alpha"),),
        )
        second, _, state_b, _, _ = self._application(
            home="/home/b",
            started=22.0,
            clock=2000.0,
            notifier="notifier-b",
            harnesses=(self._spec("beta"),),
        )

        body_a = first.collect_json(show_all=False)
        body_b = second.collect_json(show_all=False)

        self.assertNotEqual(body_a, body_b)
        self.assertEqual(1, len(state_a.collect_memo))
        self.assertEqual(1, len(state_b.collect_memo))
        # A warm read comes from the application's own memo, not the neighbour's.
        self.assertEqual(body_a, first.collect_json(show_all=False))
        self.assertEqual(body_b, second.collect_json(show_all=False))
        self.assertEqual(1, len(state_a.collect_memo))
        # A different show_all is a different key, so it is a second entry.
        first.collect_json(show_all=True)
        self.assertEqual(2, len(state_a.collect_memo))
        self.assertEqual(1, len(state_b.collect_memo))

    def test_the_memo_expires_on_the_injected_clock(self) -> None:
        # Mutation-checked: reading time.time() instead of self.clock() in the
        # freshness comparison previously passed the whole suite, which would
        # make every warm read look stale under an injected clock.
        now = [1000.0]
        config, state = make_runtime()
        collections: list[float] = []

        def collect(
            _config: RuntimeConfig,
            _state: RuntimeState,
            when: float,
            _window_hours: float,
            _show_all: bool,
        ) -> list[dict[str, Any]]:
            collections.append(when)
            return []

        application = aggregate.Application(
            config,
            state,
            (aggregate.HarnessSpec(key="a", label="A", discover=lambda *_: True, collect=collect),),
            native_notifier=lambda _platform: "",
            popup_notifier=lambda *_: None,
            diagnostic_sink=lambda _message: None,
            clock=lambda: now[0],
        )

        application.collect_json(show_all=False)
        self.assertEqual([1000.0], collections)
        # Still inside the window: served warm, and the entry carries the
        # injected clock's timestamp rather than a real reading.
        now[0] += config.collect_memo_sec / 2
        application.collect_json(show_all=False)
        self.assertEqual([1000.0], collections)
        self.assertEqual(1000.0, state.collect_memo[(config.window_hours, False)]["ts"])
        # Past the window: collected again, and the entry is re-stamped.
        now[0] = 1000.0 + config.collect_memo_sec + 1
        application.collect_json(show_all=False)
        self.assertEqual([1000.0, now[0]], collections)
        self.assertEqual(now[0], state.collect_memo[(config.window_hours, False)]["ts"])

    def test_a_discovery_failure_marks_only_that_harness_absent(self) -> None:
        application, _, _, diagnostics, _ = self._application(
            home="/home/a",
            started=11.0,
            clock=1000.0,
            notifier="notifier-a",
            harnesses=(
                self._spec("broken", discover_error=OSError("no store")),
                self._spec("healthy"),
            ),
        )

        data = application.collect(show_all=True)

        broken, healthy = data["harnesses"]
        self.assertEqual(
            ("broken", False, None), (broken["key"], broken["discovered"], broken["error"])
        )
        self.assertEqual(
            ("healthy", True, None), (healthy["key"], healthy["discovered"], healthy["error"])
        )
        # An absent store is not an error, so nothing is reported.
        self.assertEqual([], diagnostics)
        self.assertEqual(["healthy"], [s["harness"] for s in data["sessions"]])

    def test_a_collector_failure_sets_only_its_own_error(self) -> None:
        application, _, _, diagnostics, _ = self._application(
            home="/home/a",
            started=11.0,
            clock=1000.0,
            notifier="notifier-a",
            harnesses=(
                self._spec("broken", collect_error=RuntimeError("broken store")),
                self._spec("healthy"),
            ),
        )

        data = application.collect(show_all=True)

        broken, healthy = data["harnesses"]
        self.assertTrue(broken["discovered"])
        self.assertEqual("RuntimeError: broken store", broken["error"])
        self.assertIsNone(healthy["error"])
        # The failure is reported through the injected sink, never printed.
        self.assertEqual(["[broken] collector error: RuntimeError: broken store"], diagnostics)
        # The surviving harness still contributes its sessions.
        self.assertEqual(["healthy"], [s["harness"] for s in data["sessions"]])


class LegacyHarnessAdapterTest(LegacyDashboardTestCase):
    """The transitional adapter must refuse to serve a second application.

    Its wrapped collectors still read module globals, so running them for
    another application's config and state would silently produce that
    application's rows from this one's stores.
    """

    def test_a_foreign_application_cannot_drive_the_legacy_harnesses(self) -> None:
        config, state = dashboard._legacy_runtime()
        spec = dashboard._harness_specs(config, state)[0]
        foreign_config, foreign_state = make_runtime(home="/home/foreign")

        # The bound pair is accepted.
        self.assertIsInstance(spec.discover(config, state), bool)

        for label, wrong_config, wrong_state in (
            ("foreign config", foreign_config, state),
            ("foreign state", config, foreign_state),
            ("both foreign", foreign_config, foreign_state),
        ):
            with self.subTest(mismatch=label):
                with self.assertRaisesRegex(RuntimeError, "another application"):
                    spec.discover(wrong_config, wrong_state)
                with self.assertRaisesRegex(RuntimeError, "another application"):
                    spec.collect(wrong_config, wrong_state, 1.0, 24.0, False)

    def test_a_wrapped_call_reassigning_state_config_does_not_lock_out_the_spec(self) -> None:
        # The wrapped collectors call _legacy_runtime() re-entrantly, which
        # rebinds state.config. Keying the check off state.config instead of the
        # bound object would therefore reject every harness after the first, and
        # only 156 unrelated collector tests would notice.
        config, state = dashboard._legacy_runtime()
        seen: list[bool] = []

        def legacy_collect(_now: float, _window: float, _show_all: bool) -> list[dict[str, Any]]:
            dashboard._legacy_runtime()  # rebinds state.config, as the real ones do
            seen.append(state.config is not config)
            return []

        registry = (("probe", "Probe", dashboard._Legacy(lambda: True, legacy_collect)),)
        with mock.patch.object(dashboard, "_HARNESS_ROWS", registry):
            spec = dashboard._harness_specs(config, state)[0]
            spec.collect(config, state, 1.0, 24.0, False)
            # The bound pair still works after state.config moved underneath it.
            spec.collect(config, state, 2.0, 24.0, False)
            self.assertTrue(spec.discover(config, state))

        self.assertEqual([True, True], seen, "the probe did not rebind state.config")

    def test_the_registry_order_is_pinned(self) -> None:
        # Registry order is the collection order AND the order /api/data lists
        # harnesses in, which is the order the page renders its harness chips.
        # Mutation-checked: moving a row silently reordered the chips and passed
        # the whole suite, and each remaining extraction task flips one row.
        self.assertEqual(
            [
                "claude",
                "codex",
                "pi",
                "gemini",
                "copilot",
                "opencode",
                "cursor",
                "goose",
                "droid",
            ],
            [spec.key for spec in dashboard.HARNESSES],
        )

    def test_a_moved_collector_is_wired_natively_not_re_wrapped(self) -> None:
        # Once a collector speaks the runtime contract its row must stop going
        # through the legacy adapter, or the extraction bought nothing.
        native = {
            key
            for key, _label, source in dashboard._HARNESS_ROWS
            if not isinstance(source, dashboard._Legacy)
        }
        self.assertEqual({"codex", "copilot", "droid", "pi"}, native)
        self.assertIs(
            codex_collector.collect,
            next(s.collect for s in dashboard.HARNESSES if s.key == "codex"),
        )

    def test_the_registry_keys_and_labels_survive_the_adapter(self) -> None:
        # The adapter changes the calling convention, not the registry itself.
        self.assertEqual(
            [(key, label) for key, label, _source in dashboard._HARNESS_ROWS],
            [(spec.key, spec.label) for spec in dashboard.HARNESSES],
        )


class RuntimeImportGraphTest(unittest.TestCase):
    """Every runtime dependency is reviewed in the task that introduces it."""

    EXPECTED: ClassVar[dict[str, set[str]]] = {
        "cargento_runtime": set(),
        "cargento_runtime.aggregate": {
            "cargento_runtime.config",
            "cargento_runtime.io",
            "cargento_runtime.sessions",
            "cargento_runtime.state",
        },
        "cargento_runtime.collectors": set(),
        "cargento_runtime.collectors.copilot": {
            "cargento_runtime.config",
            "cargento_runtime.io",
            "cargento_runtime.sessions",
            "cargento_runtime.state",
            "cargento_runtime.transcripts",
            "cargento_runtime.turns",
        },
        "cargento_runtime.collectors.droid": {
            "cargento_runtime.config",
            "cargento_runtime.io",
            "cargento_runtime.sessions",
            "cargento_runtime.state",
            "cargento_runtime.transcripts",
            "cargento_runtime.turns",
        },
        "cargento_runtime.collectors.pi": {
            "cargento_runtime.config",
            "cargento_runtime.io",
            "cargento_runtime.records",
            "cargento_runtime.sessions",
            "cargento_runtime.state",
            "cargento_runtime.transcripts",
            "cargento_runtime.turns",
        },
        "cargento_runtime.collectors.codex": {
            "cargento_runtime.config",
            "cargento_runtime.io",
            "cargento_runtime.sessions",
            "cargento_runtime.state",
            "cargento_runtime.transcripts",
            "cargento_runtime.turns",
        },
        "cargento_runtime.config": set(),
        "cargento_runtime.io": {
            "cargento_runtime.config",
            "cargento_runtime.state",
        },
        "cargento_runtime.records": set(),
        "cargento_runtime.sessions": {"cargento_runtime.config"},
        "cargento_runtime.state": {"cargento_runtime.config"},
        "cargento_runtime.transcripts": {
            "cargento_runtime.config",
            "cargento_runtime.io",
            "cargento_runtime.records",
            "cargento_runtime.state",
        },
        "cargento_runtime.turns": {
            "cargento_runtime.config",
            "cargento_runtime.io",
            "cargento_runtime.records",
            "cargento_runtime.sessions",
            "cargento_runtime.state",
        },
        "cargento_runtime.web": set(),
        "cargento_runtime.web.page": set(),
    }

    @staticmethod
    def _module_name(path: Path) -> str:
        relative = path.relative_to(SKILL_DIR).with_suffix("")
        parts = list(relative.parts)
        if parts[-1] == "__init__":
            parts.pop()
        return ".".join(parts)

    def _relative_target(self, module: str, node: ast.ImportFrom, *, is_package: bool) -> str:
        package = module.split(".") if is_package else module.split(".")[:-1]
        if node.level > len(package):
            self.fail(f"{module} has a relative import that climbs above cargento_runtime")
        base = package[: len(package) - node.level + 1]
        if not base or base[0] != RUNTIME_PREFIX:
            self.fail(f"{module} has a relative import that climbs above cargento_runtime")
        return ".".join([*base, *([node.module] if node.module else [])])

    def _run_graph_fixture(
        self,
        source: str,
        expected_dependencies: set[str],
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            runtime_dir = skill_dir / "cargento_runtime"
            runtime_dir.mkdir()
            module_path = runtime_dir / "fixture.py"
            module_path.write_text(source, encoding="utf-8")
            expected = {"cargento_runtime.fixture": expected_dependencies}
            with (
                mock.patch.multiple(
                    sys.modules[__name__],
                    SKILL_DIR=skill_dir,
                    RUNTIME_DIR=runtime_dir,
                ),
                mock.patch.object(self, "EXPECTED", expected),
            ):
                self.test_runtime_import_graph_matches_the_reviewed_allowlist()

    def test_importfrom_namespace_aliases_are_rejected(self) -> None:
        forbidden = (
            "from cargento.skills.cargento import cargento_runtime\n",
            "from cargento.skills.cargento import cargento_runtime as runtime\n",
            "from cargento.skills.cargento import cargento_runtime, server\n",
        )
        for source in forbidden:
            with (
                self.subTest(source=source),
                self.assertRaisesRegex(AssertionError, "namespace-qualified runtime import"),
            ):
                self._run_graph_fixture(source, set())

    def test_canonical_import_forms_remain_legal(self) -> None:
        source = """
import cargento_runtime.web.page
from cargento_runtime.web import page
from . import page as sibling_page
"""
        self._run_graph_fixture(
            source,
            {
                "cargento_runtime.page",
                "cargento_runtime.web",
                "cargento_runtime.web.page",
            },
        )

    def test_relative_import_cannot_climb_above_runtime(self) -> None:
        with self.assertRaisesRegex(AssertionError, "climbs above cargento_runtime"):
            self._run_graph_fixture("from .. import server\n", set())

    def test_runtime_import_graph_matches_the_reviewed_allowlist(self) -> None:
        actual: dict[str, set[str]] = {}
        for path in sorted(RUNTIME_DIR.rglob("*.py")):
            module = self._module_name(path)
            dependencies: set[str] = set()
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertFalse(
                            alias.name == FORBIDDEN_RUNTIME_PREFIX
                            or alias.name.startswith(f"{FORBIDDEN_RUNTIME_PREFIX}."),
                            f"{module} uses namespace-qualified runtime import {alias.name}",
                        )
                        if alias.name == RUNTIME_PREFIX or alias.name.startswith(
                            f"{RUNTIME_PREFIX}."
                        ):
                            dependencies.add(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    imported = (
                        self._relative_target(
                            module,
                            node,
                            is_package=path.name == "__init__.py",
                        )
                        if node.level
                        else (node.module or "")
                    )
                    candidates = [
                        imported,
                        *(f"{imported}.{alias.name}" for alias in node.names),
                    ]
                    for candidate in candidates:
                        self.assertFalse(
                            candidate == FORBIDDEN_RUNTIME_PREFIX
                            or candidate.startswith(f"{FORBIDDEN_RUNTIME_PREFIX}."),
                            f"{module} uses namespace-qualified runtime import {candidate}",
                        )
                    if imported == RUNTIME_PREFIX or imported.startswith(f"{RUNTIME_PREFIX}."):
                        if imported == RUNTIME_PREFIX or node.module is None:
                            dependencies.update(f"{imported}.{alias.name}" for alias in node.names)
                        else:
                            dependencies.add(imported)
            dependencies.discard(module)
            actual[module] = dependencies
        self.assertEqual(self.EXPECTED, actual)

    def test_moved_symbols_exist_only_on_their_runtime_owner(self) -> None:
        io_symbols = (
            "glob_stores",
            "read_tail",
            "reverse_lines",
            "sqlite_ro_uri",
            "record_store_error",
        )
        record_symbols = (
            "safe_text",
            "parse_ts",
            "as_dict",
            "record_fingerprint",
            "gemini_records",
            "_turn_signal",
        )
        session_symbols = (
            "encoded_home_prefix",
            "HOME_PREFIX",
            "project_label",
            "project_from_cwd",
            "fmt_duration",
            "age",
            "is_fresh",
            "newest_plausible",
            "dedupe_sessions",
            "assign_display_ids",
            "base_session",
            "rate_from",
            "working_detail",
        )
        transcript_symbols = (
            "first_line_meta",
            "codex_meta",
            "gemini_meta",
            "copilot_meta",
            "droid_meta",
            "pi_meta",
            "shorten_paths",
            "clip",
            "prompt_title",
            "analyze_codex_transcript",
            "analyze_gemini_transcript",
            "analyze_copilot_events",
            "analyze_droid_transcript",
        )
        turn_symbols = (
            "_apply_turn_record",
            "_latest_turn_context",
            "scan_turns",
            "turns_from_events",
            "turn_progress",
        )
        for symbol in (
            *io_symbols,
            *record_symbols,
            *session_symbols,
            *transcript_symbols,
            *turn_symbols,
        ):
            with self.subTest(symbol=symbol):
                self.assertFalse(hasattr(dashboard, symbol))
        self.assertTrue(all(hasattr(dashboard.runtime_io, symbol) for symbol in io_symbols))
        self.assertTrue(all(hasattr(dashboard.records, symbol) for symbol in record_symbols))
        # HOME_PREFIX is deliberately gone rather than relocated: project_label
        # derives the encoded prefix from config.home on every call.
        self.assertTrue(
            all(
                hasattr(dashboard.runtime_sessions, symbol)
                for symbol in session_symbols
                if symbol != "HOME_PREFIX"
            )
        )
        self.assertFalse(hasattr(runtime_sessions, "HOME_PREFIX"))
        self.assertTrue(
            all(hasattr(dashboard.runtime_transcripts, symbol) for symbol in transcript_symbols)
        )
        self.assertIs(sys.modules["cargento_runtime.io"], dashboard.runtime_io)
        self.assertIs(sys.modules["cargento_runtime.records"], dashboard.records)
        self.assertIs(sys.modules["cargento_runtime.sessions"], dashboard.runtime_sessions)
        self.assertTrue(all(hasattr(dashboard.runtime_turns, s) for s in turn_symbols))
        self.assertIs(sys.modules["cargento_runtime.transcripts"], dashboard.runtime_transcripts)
        self.assertIs(sys.modules["cargento_runtime.turns"], dashboard.runtime_turns)

    def test_importing_lower_runtime_layers_performs_no_external_operation(self) -> None:
        # Reading ambient state or opening a file, socket, browser, log, or child
        # during import would make copied-plugin discovery and diagnostics unsafe.
        script = """
import builtins
import cargento_runtime
import dataclasses
import io
import json
import logging
import ntpath
import os
import pathlib
import posixpath
import socket
import subprocess
import threading
import time
import types
import typing
import webbrowser

def forbidden(*_args, **_kwargs):
    raise AssertionError("runtime import performed an external operation")

class ForbiddenEnvironment:
    get = forbidden
    __getitem__ = forbidden
    __contains__ = forbidden
    __iter__ = forbidden
    items = forbidden
    keys = forbidden
    values = forbidden

builtins.open = forbidden
io.open = forbidden
os.environ = ForbiddenEnvironment()
os.access = forbidden
os.listdir = forbidden
os.lstat = forbidden
os.scandir = forbidden
os.stat = forbidden
os.walk = forbidden
pathlib.Path.exists = forbidden
pathlib.Path.is_dir = forbidden
pathlib.Path.is_file = forbidden
pathlib.Path.iterdir = forbidden
pathlib.Path.open = forbidden
pathlib.Path.read_bytes = forbidden
pathlib.Path.read_text = forbidden
socket.socket = forbidden
subprocess.Popen = forbidden
subprocess.run = forbidden
time.monotonic = forbidden
time.perf_counter = forbidden
time.time = forbidden
webbrowser.open = forbidden
logging.Logger._log = forbidden

import cargento_runtime.config
import cargento_runtime.io
import cargento_runtime.records
import cargento_runtime.sessions
import cargento_runtime.state
import cargento_runtime.transcripts
import cargento_runtime.turns
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=SKILL_DIR,
            env={**os.environ, "PYTHONPATH": str(SKILL_DIR)},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)


class CollectorAgreementTest(LegacyDashboardTestCase):
    def test_claude_and_codex_agree_on_one_directory(self) -> None:
        # DRC-3963. The reported case: one worktree, two harnesses, two
        # different project strings — Claude showed the whole encoded path
        # ("git-spacedock-research-spacedock-subspace") while Codex showed a
        # bare basename. Same directory has to read the same on every row.
        now = dashboard.time.time()
        home = "/Users/cl"
        cwd = f"{home}/git/spacedock-research/spacedock/subspace"
        iso = dashboard.datetime.fromtimestamp(now - 5, dashboard.UTC).isoformat()
        encoded = runtime_sessions.encoded_home_prefix(cwd)  # Claude's projects/ dir name
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "projects" / encoded
            project_dir.mkdir(parents=True)
            (project_dir / "aaaa1111-0000-0000-0000-000000000000.jsonl").write_text(
                json.dumps(
                    {
                        "type": "user",
                        "timestamp": iso,
                        "cwd": cwd,
                        "message": {"role": "user", "content": "hi"},
                    }
                )
                + "\n"
            )
            rollout = Path(tmp) / "codex" / "2026" / "07" / "28"
            rollout.mkdir(parents=True)
            sid = "019f855d-aaaa-7000-8000-000000000001"
            (rollout / f"rollout-2026-07-28T09-36-23-{sid}.jsonl").write_text(
                json.dumps(
                    {
                        "timestamp": iso,
                        "type": "session_meta",
                        "payload": {"id": sid, "cwd": cwd, "source": "exec"},
                    }
                )
                + "\n"
            )
            with (
                mock.patch.object(dashboard, "PROJECTS_DIR", str(Path(tmp) / "projects")),
                mock.patch.object(dashboard, "TASKS_DIR", str(Path(tmp) / "no-tasks")),
                mock.patch.object(dashboard, "CODEX_SESSIONS_DIR", str(Path(tmp) / "codex")),
                mock.patch.dict(
                    dashboard.STORE_ROOTS,
                    {
                        "claude.projects": [str(Path(tmp) / "projects")],
                        "claude.tasks": [str(Path(tmp) / "no-tasks")],
                        "codex.sessions": [str(Path(tmp) / "codex")],
                    },
                ),
                mock.patch.object(dashboard, "HOME", home),
            ):
                claude = dashboard.collect_claude(now, 24, False)
                config, state = dashboard._legacy_runtime()
                codex = codex_collector.collect(config, state, now, 24, False)

        self.assertEqual(1, len(claude))
        self.assertEqual(1, len(codex))
        self.assertEqual("spacedock/subspace", claude[0]["project"])
        self.assertEqual(claude[0]["project"], codex[0]["project"])


class HarnessContractTest(HarnessContractTestCase):
    """One behavioural contract, asserted against every harness.

    The rest of the suite grew out of specific bugs, so it covers Claude deeply
    and the other seven thinly. This states what the dashboard must do and
    checks all of them, on whichever OS the runner is.
    """

    def test_pi_store_is_registered_as_a_harness(self) -> None:
        # Removing Pi from the registry would make a valid store invisible.
        self.assertIs(sys.modules["cargento_server"], dashboard)
        self.assertNotIn("cargento.skills.cargento.cargento_runtime", sys.modules)
        self.assertEqual(
            {id(dashboard)},
            {
                id(module.dashboard)
                for module in (test_claude, test_codex, test_copilot, test_droid, test_pi)
            },
        )
        data = self.collect(build_pi, when=self.NOW)
        self.assertTrue(
            any(harness["key"] == "pi" for harness in data["harnesses"]),
            "Pi store must appear in the harness registry",
        )

    def test_a_fresh_store_is_discovered_and_reads_working(self) -> None:
        for key, build in HARNESSES:
            with self.subTest(harness=key, fixture=build.__name__):
                data = self.collect(build, when=self.NOW)
                harness = next(h for h in data["harnesses"] if h["key"] == key)
                self.assertTrue(harness["discovered"], "store present but not discovered")
                self.assertIsNone(harness["error"])
                sessions = self.sessions_for(data, key)
                self.assertEqual(1, len(sessions), f"expected one session, got {sessions}")
                self.assertEqual("working", sessions[0]["state"])

    def test_a_stale_store_reads_idle_but_still_appears(self) -> None:
        for key, build in HARNESSES:
            with self.subTest(harness=key, fixture=build.__name__):
                data = self.collect(build, when=self.NOW - 7200)
                sessions = self.sessions_for(data, key)
                self.assertEqual(1, len(sessions))
                self.assertEqual("idle", sessions[0]["state"])

    def test_an_absent_store_is_not_discovered_and_is_not_an_error(self) -> None:
        # "No harness here" and "harness broken" must never look the same.
        data = self.collect(lambda *_a: {}, when=self.NOW)
        for harness in data["harnesses"]:
            with self.subTest(harness=harness["key"]):
                self.assertFalse(harness["discovered"])
                self.assertIsNone(harness["error"])
        self.assertEqual([], data["sessions"])

    def test_a_future_dated_store_does_not_read_working(self) -> None:
        # A clock-skewed store must not invent activity, on any harness.
        for key, build in HARNESSES:
            with self.subTest(harness=key, fixture=build.__name__):
                data = self.collect(build, when=self.NOW + 86_400)
                for session in self.sessions_for(data, key):
                    self.assertNotEqual("working", session["state"])
                    self.assertEqual(0, session["rate_per_min"])

    def test_one_session_in_two_candidate_roots_yields_one_row(self) -> None:
        # De-duplication has to be wired into collect(), not merely available:
        # scanning every candidate root is what makes a migrated store appear
        # twice, and only the full pass can collapse it.
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty"
            empty.mkdir()
            first, second = Path(tmp) / "one", Path(tmp) / "two"
            build_opencode(first, self.NOW, self.SID, self.TITLE)
            build_opencode(second, self.NOW - 60, self.SID, self.TITLE)
            patches: dict[str, str] = {n: str(empty / n) for n in STORE_CONSTANTS}
            patches["OPENCODE_DATA"] = str(first)
            with contextlib.ExitStack() as stack:
                for name, value in patches.items():
                    stack.enter_context(mock.patch.object(dashboard, name, value))
                # primary == candidates[0], so the whole list is scanned.
                stack.enter_context(
                    mock.patch.dict(
                        dashboard.STORE_ROOTS,
                        {"opencode.data": [str(first), str(second)]},
                    )
                )
                stack.enter_context(mock.patch.object(dashboard, "notify_mac"))
                stack.enter_context(mock.patch.object(dashboard.time, "time", lambda: self.NOW))
                data = dashboard.collect(24, show_all=True)

        opencode = [s for s in data["sessions"] if s["harness"] == "opencode"]
        self.assertEqual(1, len(opencode), f"duplicate rows: {opencode}")
        self.assertEqual(self.NOW, opencode[0]["last_activity"], "kept the staler copy")
        self.assertEqual(1, data["summary"]["active_sessions"])

    def test_a_corrupt_store_never_breaks_the_collector(self) -> None:
        # Every store file replaced with junk: the harness may vanish or report
        # an error, but collection must complete and the others must survive.
        for key, build in HARNESSES:
            with (
                self.subTest(harness=key, fixture=build.__name__),
                tempfile.TemporaryDirectory() as tmp,
            ):
                empty = Path(tmp) / "empty"
                empty.mkdir()
                patches: dict[str, str] = {n: str(empty / n) for n in STORE_CONSTANTS}
                store = Path(tmp) / "store"
                patches.update(build(store, self.NOW, self.SID, self.TITLE))
                for path in store.rglob("*"):
                    if path.is_file():
                        path.write_bytes(b"\x00\xff not a valid store at all \xfe")
                with contextlib.ExitStack() as stack:
                    for name, value in patches.items():
                        stack.enter_context(mock.patch.object(dashboard, name, value))
                    stack.enter_context(mock.patch.object(dashboard, "notify_mac"))
                    data = dashboard.collect(24, show_all=True)  # must not raise
                self.assertIsInstance(data["sessions"], list)


class HostilePathContractTest(unittest.TestCase):
    """Store paths users really have. Every character here is legal on macOS,
    Linux and Windows; the ones Windows forbids (<>:"/\\|?*) are excluded so the
    same contract runs on all three."""

    NOW = 1_700_000_000.0
    SID = "abcdef12-3456-7890-abcd-ef1234567890"
    HOSTILE = (
        "A [Contractor]",  # glob character class
        "100% pure",  # SQLite URI percent-decoding
        "Ünïcode Café",  # non-ASCII
        "a#b",  # URI fragment
        "with space",
        "it's & more",
        "plus+equals=sign",
        "semi;colon,comma",
        "dollar$at@tilde~",
        "brace{s}paren(s)",
    )

    def test_every_harness_survives_a_hostile_store_path(self) -> None:
        for component in self.HOSTILE:
            for key, build in HARNESSES:
                with self.subTest(path=component, harness=key, fixture=build.__name__):
                    with tempfile.TemporaryDirectory() as tmp:
                        empty = Path(tmp) / "empty"
                        empty.mkdir()
                        patches: dict[str, str] = {n: str(empty / n) for n in STORE_CONSTANTS}
                        patches.update(
                            build(Path(tmp) / component / "store", self.NOW, self.SID, "T")
                        )
                        with contextlib.ExitStack() as stack:
                            for name, value in patches.items():
                                stack.enter_context(mock.patch.object(dashboard, name, value))
                            stack.enter_context(mock.patch.object(dashboard, "notify_mac"))
                            stack.enter_context(
                                mock.patch.object(dashboard.time, "time", lambda: self.NOW)
                            )
                            data = dashboard.collect(24, show_all=True)
                    found = [s for s in data["sessions"] if s["harness"] == key]
                    self.assertEqual(1, len(found), f"{key} lost its session under {component!r}")
