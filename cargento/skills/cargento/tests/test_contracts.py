from __future__ import annotations

import ast
import contextlib
import http.client
import json
import os
import runpy
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar
from unittest import mock

from cargento_runtime import aggregate, cli, http_api, notifications, records
from cargento_runtime import io as runtime_io
from cargento_runtime import sessions as runtime_sessions
from cargento_runtime import transcripts as runtime_transcripts
from cargento_runtime import turns as runtime_turns
from cargento_runtime.collectors import claude as claude_collector
from cargento_runtime.collectors import codex as codex_collector

from .fixtures import (
    HARNESSES,
    STORE_CONSTANTS,
    build_opencode,
    build_pi,
)
from .support import (
    REGISTRY,
    SERVER_PATH,
    STORE_OVERRIDES,
    HarnessContractTestCase,
    RuntimeTestCase,
    collect,
    collect_claude,
    config_patch,
    make_runtime,
    runtime,
    serve_until_closed,
    store_patch,
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
        usage_entries: list[dict[str, Any]] | None = None,
        usage_error: BaseException | None = None,
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

        usage: aggregate.UsageProvider | None = None
        if usage_entries is not None or usage_error is not None:

            def usage(
                config: RuntimeConfig,
                state: RuntimeState,
                now: float,
                window_hours: float,
            ) -> list[dict[str, Any]]:
                del config, state, now, window_hours
                if usage_error is not None:
                    raise usage_error
                return list(usage_entries or [])

        return aggregate.HarnessSpec(
            key=key, label=key.title(), discover=discover, collect=collect, usage=usage
        )

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

    def _get(self, port: int, path: str) -> tuple[int, bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.request("GET", path)
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def _post(self, port: int, path: str, payload: dict[str, Any]) -> bytes:
        body = json.dumps(payload).encode()
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.request("POST", path, body=body, headers={"Content-Type": "application/json"})
            return conn.getresponse().read()
        finally:
            conn.close()

    def test_two_servers_answer_only_for_their_own_application(self) -> None:
        # The design requires this: CargentoHTTPServer stores exactly one
        # application and one page, and handlers read them off the server
        # instance. Two live servers in one interpreter must not cross.
        first, config_a, state_a, _, popups_a = self._application(
            home="/home/a",
            started=11.0,
            clock=1000.0,
            notifier="notifier-a",
            harnesses=(self._spec("alpha"),),
        )
        second, config_b, state_b, _, popups_b = self._application(
            home="/home/b",
            started=22.0,
            clock=2000.0,
            notifier="notifier-b",
            harnesses=(self._spec("beta"),),
        )
        servers = [
            http_api.CargentoHTTPServer(("127.0.0.1", 0), app, page)
            for app, page in ((first, b"<page-a>"), (second, b"<page-b>"))
        ]
        threads = [serve_until_closed(httpd) for httpd in servers]
        port_a, port_b = (httpd.server_port for httpd in servers)
        try:
            # The page is per instance, not a module global.
            self.assertEqual((200, b"<page-a>"), self._get(port_a, "/"))
            self.assertEqual((200, b"<page-b>"), self._get(port_b, "/"))

            data_a = json.loads(self._get(port_a, "/api/data")[1])
            data_b = json.loads(self._get(port_b, "/api/data")[1])
            self.assertEqual(["alpha"], [h["key"] for h in data_a["harnesses"]])
            self.assertEqual(["beta"], [h["key"] for h in data_b["harnesses"]])
            # Each collected on its own injected clock and config.
            self.assertEqual((1000.0, 2000.0), (data_a["generated"], data_b["generated"]))
            self.assertEqual(["/home/a"], [row["project"] for row in data_a["sessions"]])
            self.assertEqual(["/home/b"], [row["project"] for row in data_b["sessions"]])

            # /api/health reports each server's own port and start stamp.
            health_a = json.loads(self._get(port_a, "/api/health")[1])
            health_b = json.loads(self._get(port_b, "/api/health")[1])
            self.assertEqual((port_a, 11.0), (health_a["port"], health_a["started"]))
            self.assertEqual((port_b, 22.0), (health_b["port"], health_b["started"]))

            # A notification POST lands in the receiving server's state only,
            # and pops through that application's own notifier.
            self._post(port_a, "/api/notify", {"session_id": "aaaaaaaa", "message": "permission"})
            self.assertIn("aaaaaaaa", state_a.hook_notifications)
            self.assertEqual({}, dict(state_b.hook_notifications))
            self.assertEqual(1, len(popups_a))
            self.assertEqual([], popups_b)

            # Give B its own standing hook, then end that session on A. A
            # SessionEnd is the most destructive payload there is; it must not
            # reach across.
            self._post(port_b, "/api/notify", {"session_id": "aaaaaaaa", "message": "permission"})
            self.assertIn("aaaaaaaa", state_b.hook_notifications)
            self._post(
                port_a,
                "/api/notify",
                {"session_id": "aaaaaaaa", "hook_event_name": "SessionEnd"},
            )
            self.assertNotIn("aaaaaaaa", state_a.hook_notifications)
            self.assertIn("aaaaaaaa", state_b.hook_notifications)
            self.assertEqual(1, state_a.hook_generation["aaaaaaaa"])
            self.assertEqual(0, state_b.hook_generation.get("aaaaaaaa", 0))
            self.assertNotEqual(config_a.home, config_b.home)
        finally:
            for httpd, thread in zip(servers, threads, strict=True):
                httpd.shutdown()
                thread.join(timeout=5)

    def test_health_reports_the_captured_start_stamp_without_a_second_clock_read(self) -> None:
        # --status and the daemon readiness wait poll this in a loop. Sampling a
        # clock in the handler would report a different uptime on every poll for
        # one unchanging process, so the value must be the sentinel that
        # build_runtime_state captured.
        sentinel = 1_234_567.5
        application, _, state, _, _ = self._application(
            home="/home/a",
            started=sentinel,
            clock=9_999_999.0,
            notifier="notifier-a",
            harnesses=(),
        )
        self.assertEqual(sentinel, state.server_started)
        httpd = http_api.CargentoHTTPServer(("127.0.0.1", 0), application, b"<page>")
        thread = serve_until_closed(httpd)
        try:
            first = json.loads(self._get(httpd.server_port, "/api/health")[1])
            second = json.loads(self._get(httpd.server_port, "/api/health")[1])
        finally:
            httpd.shutdown()
            thread.join(timeout=5)

        self.assertEqual(sentinel, first["started"])
        # Same value on a second poll, and never the application's clock.
        self.assertEqual(first["started"], second["started"])
        self.assertEqual(os.getpid(), first["pid"])

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

    def test_usage_key_appears_only_when_a_provider_is_discovered(self) -> None:
        entry = {"harness": "quota", "state": "ok", "asOf": 999, "week": {"pct": 62}}
        with_provider, _, _, _, _ = self._application(
            home="/home/a",
            started=11.0,
            clock=1000.0,
            notifier="notifier-a",
            harnesses=(self._spec("plain"), self._spec("quota", usage_entries=[entry])),
        )
        without_provider, _, _, _, _ = self._application(
            home="/home/b",
            started=11.0,
            clock=1000.0,
            notifier="notifier-b",
            harnesses=(self._spec("plain"),),
        )

        self.assertEqual([entry], with_provider.collect(show_all=True)["usage"])
        # No provider anywhere: the key is absent and the page stays dormant.
        self.assertNotIn("usage", without_provider.collect(show_all=True))

    def test_a_usage_failure_is_contained_to_diagnostics(self) -> None:
        application, _, _, diagnostics, _ = self._application(
            home="/home/a",
            started=11.0,
            clock=1000.0,
            notifier="notifier-a",
            harnesses=(self._spec("quota", usage_error=RuntimeError("torn snapshot")),),
        )

        data = application.collect(show_all=True)

        # The harness's session rows survive, its strip shows no error, and the
        # band gets an empty list rather than disappearing.
        self.assertEqual(["quota"], [s["harness"] for s in data["sessions"]])
        self.assertIsNone(data["harnesses"][0]["error"])
        self.assertEqual([], data["usage"])
        self.assertTrue(any("torn snapshot" in line for line in diagnostics))

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


class LauncherContractTest(unittest.TestCase):
    """server.py is the stable entry point and owns nothing else."""

    def test_the_launcher_is_only_a_call_into_the_cli(self) -> None:
        # This file is what users and every harness manifest point at, so its
        # shape is a contract: one import, one call, no re-exports.
        source = SERVER_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom | ast.Import)]
        self.assertEqual(1, len(imports), "the launcher imports more than the CLI")
        only = imports[0]
        assert isinstance(only, ast.ImportFrom)
        self.assertEqual("cargento_runtime.cli", only.module)
        self.assertEqual(["main"], [alias.name for alias in only.names])
        # No definitions and no assignments that could re-export a symbol,
        # anywhere in the tree rather than only at the top level: `if True:` with
        # a collector nested under it would pass a tree.body-only check.
        banned = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Assign
        offenders = [type(n).__name__ for n in ast.walk(tree) if isinstance(n, banned)]
        self.assertEqual([], offenders, "the launcher defines or assigns something")

    def test_running_the_launcher_calls_the_cli_exactly_once(self) -> None:
        # runpy executes the real file under __main__, which is the only way to
        # prove the `if __name__` guard wires through to cli.main and that the
        # exit code is the one main returned.
        calls: list[object] = []

        def fake_main(*args: object, **kwargs: object) -> int:
            calls.append((args, kwargs))
            return 7

        with (
            mock.patch.object(cli, "main", fake_main),
            self.assertRaises(SystemExit) as caught,
        ):
            runpy.run_path(str(SERVER_PATH), run_name="__main__")

        self.assertEqual(7, caught.exception.code)
        self.assertEqual(1, len(calls))

    def test_importing_the_runtime_opens_no_store_socket_or_subprocess(self) -> None:
        # Import must be inert: --diagnose, --status and --stop all assemble a
        # runtime first, and a module that scanned a store or bound a port at
        # import time would make those unusable exactly when they are needed.
        probe = (
            "import importlib, pkgutil, socket, sqlite3, subprocess, sys\n"
            # The root arrives as argv, never interpolated into this source: a
            # Windows path's backslashes would be read as escape sequences.
            "sys.path.insert(0, sys.argv[1])\n"
            "import cargento_runtime\n"
            "def boom(*a, **k):\n"
            "    raise AssertionError('side effect at import')\n"
            "socket.socket.bind = boom\n"
            "socket.socket.connect = boom\n"
            "subprocess.Popen.__init__ = boom\n"
            "sqlite3.connect = boom\n"
            "names = [m.name for m in pkgutil.walk_packages(\n"
            "    cargento_runtime.__path__, 'cargento_runtime.')]\n"
            "for name in names:\n"
            "    importlib.import_module(name)\n"
            "assert len(names) >= 20, names\n"
            "print('OK', len(names))\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", probe, str(SERVER_PATH.parent)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("OK", result.stdout)

    def test_every_runtime_module_resolves_inside_the_skill_directory(self) -> None:
        # A copied plugin has no repository around it. Walking the package and
        # checking each module's __file__ proves nothing resolved back to a
        # checkout, and it inspects every module rather than a maintained list.
        probe = (
            "import importlib, pkgutil, sys\n"
            "from pathlib import Path\n"
            # Same rule as the probe above: the root is argv, not source.
            "root = Path(sys.argv[1]).resolve()\n"
            "sys.path.insert(0, str(root))\n"
            "import cargento_runtime\n"
            "from cargento_runtime.web import page\n"
            "names = [m.name for m in pkgutil.walk_packages(\n"
            "    cargento_runtime.__path__, 'cargento_runtime.')]\n"
            # is_relative_to, not a string prefix: Windows differs from POSIX in
            # separator and in drive-letter case, and both would defeat a prefix.
            "for name in names:\n"
            "    mod = importlib.import_module(name)\n"
            "    assert mod.__file__, name\n"
            "    resolved = Path(mod.__file__).resolve()\n"
            "    assert resolved.is_relative_to(root), (name, str(resolved))\n"
            "for asset in ('index.html', 'styles.css', 'app.js'):\n"
            "    found = page.asset_path(asset).resolve()\n"
            "    assert found.is_relative_to(root), (asset, str(found))\n"
            "print('OK', len(names))\n"
        )
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in {"PYTHONPATH", "PYTHONHOME"}
        }
        env["PYTHONNOUSERSITE"] = "1"
        result = subprocess.run(
            [sys.executable, "-c", probe, str(SERVER_PATH.parent)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            # An unrelated working directory: nothing may resolve via ".".
            cwd=tempfile.gettempdir(),
            env=env,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("OK", result.stdout)


class HarnessRegistryTest(RuntimeTestCase):
    """The registry is nine collector modules and nothing else."""

    def test_the_registry_order_is_pinned(self) -> None:
        # Registry order is the collection order AND the order /api/data lists
        # harnesses in, which is the order the page renders its harness chips.
        # Mutation-checked: moving a row silently reordered the chips and passed
        # the whole suite.
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
            [spec.key for spec in REGISTRY],
        )

    def test_no_registry_callback_resolves_into_the_launcher(self) -> None:
        # Every callback must resolve to a collector module. Claude's is the one
        # exception: the registry wraps it to bind the popup notifier, so it
        # resolves to aggregate.
        for spec in REGISTRY:
            with self.subTest(harness=spec.key):
                for role, fn in (("discover", spec.discover), ("collect", spec.collect)):
                    module = getattr(fn, "__module__", "")
                    self.assertNotEqual(
                        "cargento_runtime.cli",
                        module,
                        f"{spec.key}.{role} is defined in the launcher",
                    )
                    allowed = module.startswith("cargento_runtime.collectors.") or (
                        spec.key == "claude"
                        and role == "collect"
                        and module == "cargento_runtime.aggregate"
                    )
                    self.assertTrue(allowed, f"{spec.key}.{role} resolves to {module!r}")
        # Every unwrapped callback is the module attribute itself, not a copy.
        self.assertIs(
            codex_collector.collect,
            next(s.collect for s in REGISTRY if s.key == "codex"),
        )

    def test_the_claude_wrapper_delegates_to_the_claude_collector(self) -> None:
        # The one wrapped row: prove the wrapper is a binding and not a
        # reimplementation, by checking what its closure actually calls.
        spec = next(s for s in REGISTRY if s.key == "claude")
        closed_over = [cell.cell_contents for cell in (spec.collect.__closure__ or ())]
        self.assertIn(claude_collector, closed_over)

    def test_the_claude_row_notifies_through_the_registrys_own_notifier(self) -> None:
        # Claude is the only collector that notifies during collection, so its
        # notifier is bound when the registry is built. Mutation-checked: handing
        # the collector a silent notifier instead passed the whole suite, because
        # every other popup test patches notify_mac underneath the binding and so
        # cannot tell which callable the registry actually passed down.
        now = 1_700_000_000.0
        prefix = "abcdef12"
        fired: list[tuple[str, str]] = []
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "projects" / "-w-proj"
            project.mkdir(parents=True)
            transcript = project / f"{prefix}-0000-0000-0000-000000000000.jsonl"
            transcript.write_text(json.dumps({"type": "user", "uuid": "u"}) + "\n")
            # Quiet, so the standing hook decides the state rather than activity.
            os.utime(transcript, (now - 300, now - 300))
            with (
                store_patch(PROJECTS_DIR=str(Path(tmp) / "projects")),
                store_patch(TASKS_DIR=str(Path(tmp) / "tasks")),
            ):
                config, state = runtime()
                with state.hook_lock:
                    state.hook_notifications[prefix] = {"ts": now, "message": "permission"}
                spec = next(
                    s
                    for s in aggregate.default_harnesses(
                        lambda title, message: fired.append((title, message))
                    )
                    if s.key == "claude"
                )
                found = spec.collect(config, state, now, 24, True)

        self.assertEqual(["needs_input"], [s["state"] for s in found])
        self.assertEqual(1, len(fired), "the registry's notifier was not the one used")
        self.assertIn("permission", fired[0][1])

    def test_the_registry_keys_and_labels_match_the_runtime_default(self) -> None:
        # default_harnesses binds Claude's notifier; nothing downstream may
        # otherwise rewrite the registry the runtime declares.
        runtime_registry = aggregate.default_harnesses(lambda _title, _message: None)
        self.assertEqual(
            [(spec.key, spec.label) for spec in runtime_registry],
            [(spec.key, spec.label) for spec in REGISTRY],
        )


class RuntimeImportGraphTest(unittest.TestCase):
    """Every runtime dependency is reviewed in the task that introduces it."""

    EXPECTED: ClassVar[dict[str, set[str]]] = {
        "cargento_runtime": set(),
        "cargento_runtime.aggregate": {
            "cargento_runtime.collectors",
            "cargento_runtime.config",
            "cargento_runtime.io",
            "cargento_runtime.sessions",
            "cargento_runtime.state",
        },
        # The CLI is the assembly point, so it may import any runtime module.
        "cargento_runtime.cli": {
            "cargento_runtime.aggregate",
            "cargento_runtime.config",
            "cargento_runtime.diagnostics",
            "cargento_runtime.http_api",
            "cargento_runtime.io",
            "cargento_runtime.lifecycle",
            "cargento_runtime.notifications",
            "cargento_runtime.state",
            "cargento_runtime.web",
        },
        "cargento_runtime.collectors": set(),
        "cargento_runtime.diagnostics": {
            "cargento_runtime.aggregate",
            "cargento_runtime.config",
            "cargento_runtime.io",
        },
        "cargento_runtime.collectors.claude": {
            "cargento_runtime.claude_data",
            "cargento_runtime.config",
            "cargento_runtime.io",
            "cargento_runtime.notifications",
            "cargento_runtime.sessions",
            "cargento_runtime.spacedock",
            "cargento_runtime.state",
            "cargento_runtime.turns",
        },
        "cargento_runtime.collectors.copilot": {
            "cargento_runtime.config",
            "cargento_runtime.io",
            "cargento_runtime.sessions",
            "cargento_runtime.state",
            "cargento_runtime.transcripts",
            "cargento_runtime.turns",
        },
        "cargento_runtime.collectors.cursor": {
            "cargento_runtime.config",
            "cargento_runtime.io",
            "cargento_runtime.sessions",
            "cargento_runtime.state",
        },
        "cargento_runtime.collectors.droid": {
            "cargento_runtime.config",
            "cargento_runtime.io",
            "cargento_runtime.sessions",
            "cargento_runtime.state",
            "cargento_runtime.transcripts",
            "cargento_runtime.turns",
        },
        "cargento_runtime.collectors.gemini": {
            "cargento_runtime.config",
            "cargento_runtime.io",
            "cargento_runtime.records",
            "cargento_runtime.sessions",
            "cargento_runtime.state",
            "cargento_runtime.transcripts",
            "cargento_runtime.turns",
        },
        "cargento_runtime.collectors.goose": {
            "cargento_runtime.config",
            "cargento_runtime.io",
            "cargento_runtime.records",
            "cargento_runtime.sessions",
            "cargento_runtime.state",
            "cargento_runtime.turns",
        },
        "cargento_runtime.collectors.opencode": {
            "cargento_runtime.config",
            "cargento_runtime.io",
            "cargento_runtime.records",
            "cargento_runtime.sessions",
            "cargento_runtime.state",
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
        "cargento_runtime.notifications": {
            "cargento_runtime.claude_data",
            "cargento_runtime.config",
            "cargento_runtime.io",
            "cargento_runtime.records",
            "cargento_runtime.state",
        },
        "cargento_runtime.spacedock": {
            "cargento_runtime.config",
            "cargento_runtime.sessions",
            "cargento_runtime.state",
        },
        "cargento_runtime.claude_data": {
            "cargento_runtime.config",
            "cargento_runtime.io",
            "cargento_runtime.records",
            "cargento_runtime.state",
            "cargento_runtime.transcripts",
        },
        "cargento_runtime.collectors.codex": {
            "cargento_runtime.config",
            "cargento_runtime.io",
            "cargento_runtime.records",
            "cargento_runtime.sessions",
            "cargento_runtime.state",
            "cargento_runtime.transcripts",
            "cargento_runtime.turns",
        },
        "cargento_runtime.config": set(),
        "cargento_runtime.http_api": {
            "cargento_runtime.aggregate",
            "cargento_runtime.io",
            "cargento_runtime.notifications",
        },
        "cargento_runtime.lifecycle": {
            "cargento_runtime.config",
            "cargento_runtime.http_api",
            "cargento_runtime.io",
        },
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
        launcher_source = SERVER_PATH.read_text(encoding="utf-8")
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
        notification_symbols = (
            "normalized_notification_type",
            "notification_disposition",
            "native_notifier",
            "notify_mac",
            "hook_generation",
            "current_hook",
            "maybe_popup",
            "IDLE_NOTIFICATION_TYPES",
            "CLEARING_NOTIFICATION_TYPES",
        )
        spacedock_symbols = (
            "sd_frontmatter_lines",
            "sd_read_workflow",
            "sd_read_entities",
            "sd_session_workflows",
            "SPACEDOCK_FO",
            "SD_STAGE_RE",
        )
        lifecycle_symbols = (
            "tcp_port",
            "cargento_home",
            "state_path",
            "log_path",
            "ensure_cargento_home",
            "write_state",
            "read_state",
            "remove_state",
            "probe_port",
            "port_released",
            "await_release",
            "instance_status",
            "render_status",
            "stop_instance",
            "fork_daemon",
            "daemon_redirect_stdio",
            "daemon_announce",
            "await_daemon",
            "forwarded_args",
            "spawn_detached",
            "log_tail",
            "await_spawned",
        )
        http_symbols = (
            "normalize_host",
            "reuse_address_allowed",
            "bind_error_message",
            "LoopbackHTTPServer",
            "Handler",
        )
        diagnostics_symbols = (
            "store_primaries",
            "candidate_report",
            "render_diagnosis",
        )
        claude_collector_symbols = (
            "load_tasks",
            "claude_agent_transcripts",
            "load_claude_subagents",
            "collect_claude",
            "claude_spacedock",
            "CLAUDE_SUBAGENT_GLOBS",
        )
        claude_data_symbols = (
            "claude_session_title",
            "claude_last_user_event",
            "analyze_transcript",
            "claude_session_cwd",
            "claude_hook_user_event",
            "claude_agent_identity",
            "claude_agent_setting",
            "claude_prefix_is_agent",
            "INPUT_TOOLS",
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
            *claude_data_symbols,
            *notification_symbols,
            *claude_collector_symbols,
            *diagnostics_symbols,
            *http_symbols,
            *lifecycle_symbols,
            *spacedock_symbols,
        ):
            with self.subTest(symbol=symbol):
                # The launcher has no namespace to check, so the contract is on
                # its source: none of these may reappear there.
                self.assertNotIn(symbol, launcher_source)
        self.assertTrue(all(hasattr(runtime_io, symbol) for symbol in io_symbols))
        self.assertTrue(all(hasattr(records, symbol) for symbol in record_symbols))
        # HOME_PREFIX is deliberately gone rather than relocated: project_label
        # derives the encoded prefix from config.home on every call.
        self.assertTrue(
            all(
                hasattr(runtime_sessions, symbol)
                for symbol in session_symbols
                if symbol != "HOME_PREFIX"
            )
        )
        self.assertFalse(hasattr(runtime_sessions, "HOME_PREFIX"))
        self.assertTrue(all(hasattr(runtime_transcripts, symbol) for symbol in transcript_symbols))
        self.assertIs(sys.modules["cargento_runtime.io"], runtime_io)
        self.assertIs(sys.modules["cargento_runtime.records"], records)
        self.assertIs(sys.modules["cargento_runtime.sessions"], runtime_sessions)
        self.assertTrue(all(hasattr(runtime_turns, s) for s in turn_symbols))
        self.assertIs(sys.modules["cargento_runtime.transcripts"], runtime_transcripts)
        self.assertIs(sys.modules["cargento_runtime.turns"], runtime_turns)

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


class CollectorAgreementTest(RuntimeTestCase):
    def test_claude_and_codex_agree_on_one_directory(self) -> None:
        # DRC-3963. The reported case: one worktree, two harnesses, two
        # different project strings — Claude showed the whole encoded path
        # ("git-spacedock-research-spacedock-subspace") while Codex showed a
        # bare basename. Same directory has to read the same on every row.
        now = time.time()
        home = "/Users/cl"
        cwd = f"{home}/git/spacedock-research/spacedock/subspace"
        iso = datetime.fromtimestamp(now - 5, UTC).isoformat()
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
                store_patch(PROJECTS_DIR=str(Path(tmp) / "projects")),
                store_patch(TASKS_DIR=str(Path(tmp) / "no-tasks")),
                store_patch(CODEX_SESSIONS_DIR=str(Path(tmp) / "codex")),
                mock.patch.dict(
                    STORE_OVERRIDES,
                    {
                        "claude.projects": [str(Path(tmp) / "projects")],
                        "claude.tasks": [str(Path(tmp) / "no-tasks")],
                        "codex.sessions": [str(Path(tmp) / "codex")],
                    },
                ),
                config_patch(home=home),
            ):
                claude = collect_claude(now, 24, False)
                config, state = runtime()
                codex = codex_collector.collect(config, state, now, 24, False)

        self.assertEqual(1, len(claude))
        self.assertEqual(1, len(codex))
        self.assertEqual("spacedock/subspace", claude[0]["project"])
        self.assertEqual(claude[0]["project"], codex[0]["project"])


class HarnessContractTest(HarnessContractTestCase):
    """One behavioural contract, asserted against every harness.

    The rest of the suite grew out of specific bugs, so it covers Claude deeply
    and the other eight thinly. This states what the dashboard must do and
    checks all of them, on whichever OS the runner is.
    """

    def test_pi_store_is_registered_as_a_harness(self) -> None:
        # Removing Pi from the registry would make a valid store invisible.
        # One runtime package, imported by its own name. A namespace-qualified
        # copy would give every module a second identity and a second cache.
        self.assertNotIn("cargento.skills.cargento.cargento_runtime", sys.modules)
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
                stack.enter_context(store_patch(**patches))
                # primary == candidates[0], so the whole list is scanned. This
                # override carries BOTH roots, which store_patch cannot express.
                stack.enter_context(
                    mock.patch.dict(
                        STORE_OVERRIDES,
                        {"opencode.data": str(first)},
                    )
                )
                stack.enter_context(mock.patch.object(notifications, "notify_mac"))
                stack.enter_context(mock.patch.object(time, "time", lambda: self.NOW))
                data = collect(24, show_all=True)

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
                    stack.enter_context(store_patch(**patches))
                    stack.enter_context(mock.patch.object(notifications, "notify_mac"))
                    data = collect(24, show_all=True)  # must not raise
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
                            stack.enter_context(store_patch(**patches))
                            stack.enter_context(mock.patch.object(notifications, "notify_mac"))
                            stack.enter_context(mock.patch.object(time, "time", lambda: self.NOW))
                            data = collect(24, show_all=True)
                    found = [s for s in data["sessions"] if s["harness"] == key]
                    self.assertEqual(1, len(found), f"{key} lost its session under {component!r}")
