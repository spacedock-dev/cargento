from __future__ import annotations

import argparse
import contextlib
import errno
import hashlib
import http.client
import http.server
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest import mock

from .page_harness import PageJsHarness
from .support import (
    SERVER_PATH,
    dashboard,
    serve_until_closed,
)

if TYPE_CHECKING:
    import email.message


class InstalledContractCharacterizationTest(unittest.TestCase):
    """The installed executable contract that extraction must preserve."""

    # macOS arm64 platform runners can be contended while the complete suite
    # runs. Keep a finite readiness ceiling, but leave enough room for an
    # owned foreground child to bind and atomically publish its state file.
    OWNED_INSTANCE_READY_TIMEOUT_SEC = 60.0

    def setUp(self) -> None:
        self._spacedock_enabled = dashboard.__dict__["SPACEDOCK_ENABLED"]
        self._window_hours = dashboard.Handler.window_hours
        self._server_started = dashboard.__dict__["SERVER_STARTED"]
        with dashboard._lock:
            dashboard._hook_notifs.clear()
            dashboard._last_popup.clear()
            dashboard._last_popup_message.clear()
            dashboard._last_state.clear()
            dashboard._hook_generation.clear()
        with dashboard._collect_memo_lock:
            dashboard._collect_memo.clear()
        # Route-shape tests exercise successful /api/notify requests, but do
        # not assert native delivery. Execute the notification code while
        # keeping its osascript process off the host.
        original_run = dashboard.subprocess.run

        def run_without_native_delivery(*args: Any, **kwargs: Any) -> Any:
            command = args[0] if args else kwargs.get("args")
            if (
                isinstance(command, (list, tuple))
                and command
                and command[0] == "/usr/bin/osascript"
            ):
                return subprocess.CompletedProcess(command, 0)
            return original_run(*args, **kwargs)

        notify_patcher = mock.patch.object(
            dashboard.subprocess, "run", side_effect=run_without_native_delivery
        )
        notify_patcher.start()
        self.addCleanup(notify_patcher.stop)

    def tearDown(self) -> None:
        dashboard.__dict__["SPACEDOCK_ENABLED"] = self._spacedock_enabled
        dashboard.Handler.window_hours = self._window_hours
        dashboard.__dict__["SERVER_STARTED"] = self._server_started
        with dashboard._collect_memo_lock:
            dashboard._collect_memo.clear()

    @staticmethod
    def _candidate_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            return int(listener.getsockname()[1])

    @staticmethod
    def _clean_env(cargento_home: Path) -> dict[str, str]:
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env["PYTHONNOUSERSITE"] = "1"
        env["CARGENTO_HOME"] = str(cargento_home)
        return env

    @staticmethod
    def _response(
        port: int,
        method: str,
        path: str,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, email.message.Message, bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            return response.status, response.headers, response.read()
        finally:
            conn.close()

    def _await_owned_instance(
        self, port: int, proc: subprocess.Popen[bytes], state_path: Path
    ) -> None:
        deadline = time.monotonic() + self.OWNED_INSTANCE_READY_TIMEOUT_SEC
        last_observation = "no health response"
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                stdout, stderr = proc.communicate(timeout=2)
                self.fail(f"launcher exited: {stdout!r} {stderr!r}")
            try:
                code, _, body = self._response(port, "GET", "/api/health")
                health = json.loads(body) if code == 200 else {}
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                last_observation = f"health request failed: {type(exc).__name__}: {exc}"
                time.sleep(0.05)
                continue
            if code != 200:
                last_observation = f"health returned HTTP {code}"
                time.sleep(0.05)
                continue
            if health.get("pid") != proc.pid:
                self.fail(f"port {port} is served by pid {health.get('pid')}, not child {proc.pid}")
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                last_observation = (
                    f"owned health from pid {proc.pid}, but state {state_path} was unreadable: "
                    f"{type(exc).__name__}: {exc}"
                )
                time.sleep(0.05)
                continue
            self.assertEqual(proc.pid, state.get("pid"))
            self.assertEqual(port, state.get("port"))
            return
        self.fail(
            f"owned child {proc.pid} did not become healthy with its state file within "
            f"{self.OWNED_INSTANCE_READY_TIMEOUT_SEC:.0f}s: {last_observation}"
        )

    def _owns_instance(self, port: int, proc: subprocess.Popen[bytes], state_path: Path) -> bool:
        if proc.poll() is not None:
            return False
        try:
            code, _, body = self._response(port, "GET", "/api/health")
            health = json.loads(body) if code == 200 else {}
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return False
        return health.get("pid") == proc.pid and state.get("pid") == proc.pid

    def test_launcher_runs_from_an_unrelated_working_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = self._clean_env(root / "state")
            proc = subprocess.run(
                [sys.executable, str(SERVER_PATH), "--diagnose", "--json"],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
                check=False,
            )
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("platform", json.loads(proc.stdout))

    def test_cli_help_diagnose_status_stop_and_invalid_arguments_are_stable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            port = self._candidate_port()
            env = self._clean_env(root / "state")
            state_path = root / "state" / f"cargento-{port}.json"
            server = subprocess.Popen(
                [sys.executable, str(SERVER_PATH), "--port", str(port)],
                cwd=root,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            cases = (
                ("help", ["--help"], 0, "usage:"),
                ("diagnose", ["--diagnose", "--json"], 0, '"harnesses"'),
                ("status", ["--port", str(port), "--status"], 0, "running"),
                ("stop", ["--port", str(port), "--stop"], 0, "stopped"),
                ("invalid", ["--unknown-flag"], 2, "unrecognized arguments"),
            )
            try:
                self._await_owned_instance(port, server, state_path)
                for label, args, expected, text in cases:
                    with self.subTest(path=label):
                        proc = subprocess.run(
                            [sys.executable, str(SERVER_PATH), *args],
                            cwd=root,
                            env=env,
                            capture_output=True,
                            text=True,
                            encoding="utf-8",
                            timeout=30,
                            check=False,
                        )
                        self.assertEqual(expected, proc.returncode, proc.stderr)
                        self.assertIn(text, proc.stdout + proc.stderr)
            finally:
                if self._owns_instance(port, server, state_path):
                    subprocess.run(
                        [sys.executable, str(SERVER_PATH), "--port", str(port), "--stop"],
                        cwd=root,
                        env=env,
                        capture_output=True,
                        timeout=15,
                        check=False,
                    )
                if server.poll() is None:
                    server.terminate()
                    with contextlib.suppress(subprocess.TimeoutExpired):
                        server.wait(timeout=5)
                if server.poll() is None:
                    server.kill()
                server.wait(timeout=5)
                if server.stdout is not None:
                    server.stdout.close()
                if server.stderr is not None:
                    server.stderr.close()

    def test_http_routes_pin_status_content_type_and_response_shapes(self) -> None:
        httpd = dashboard.ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
        thread = serve_until_closed(httpd)
        with mock.patch.object(
            dashboard,
            "collect",
            return_value={"generated": 1.0, "sessions": [], "harnesses": []},
        ):
            try:
                cases = (
                    ("GET", "/", None, 200, "text/html; charset=utf-8", None),
                    (
                        "GET",
                        "/api/data",
                        None,
                        200,
                        "application/json",
                        {"generated", "sessions", "harnesses"},
                    ),
                    (
                        "GET",
                        "/api/health",
                        None,
                        200,
                        "application/json",
                        {"ok", "pid", "port", "started"},
                    ),
                    (
                        "POST",
                        "/api/notify",
                        b'{"session_id":"12345678"}',
                        200,
                        "application/json",
                        {"ok"},
                    ),
                    ("GET", "/missing", None, 404, "text/html;charset=utf-8", None),
                )
                for method, path, body, status, ctype, keys in cases:
                    with self.subTest(path=path):
                        code, headers, received = self._response(
                            httpd.server_port, method, path, body
                        )
                        self.assertEqual(status, code)
                        self.assertEqual(ctype, headers["Content-Type"])
                        if status == 404:
                            self.assertIsNone(headers.get("Cache-Control"))
                        else:
                            self.assertEqual("no-store", headers["Cache-Control"])
                        if keys is not None:
                            self.assertEqual(keys, set(json.loads(received)))
                code, headers, received = self._response(
                    httpd.server_port, "POST", "/api/shutdown", b""
                )
                self.assertEqual(200, code)
                self.assertEqual("application/json", headers["Content-Type"])
                self.assertEqual("no-store", headers["Cache-Control"])
                self.assertEqual({"ok", "stopping"}, set(json.loads(received)))
            finally:
                httpd.shutdown()
                thread.join(timeout=5)

    def test_host_origin_dns_rebinding_and_request_limits_are_preserved(self) -> None:
        captured_addresses: list[tuple[str, int]] = []

        class StopServingError(Exception):
            pass

        class CapturingServer:
            def __init__(self, address: tuple[str, int], _: Any) -> None:
                captured_addresses.append(address)

            def serve_forever(self) -> None:
                raise StopServingError

            def server_close(self) -> None:
                pass

        # The shipped launcher, rather than this test's fixture, owns the
        # required bind address. Capture the constructor call from main() so a
        # regression to 0.0.0.0 cannot pass merely because this test chose 127.
        with (
            mock.patch.object(sys, "argv", ["server.py", "--port", "4553"]),
            mock.patch.object(dashboard, "LoopbackHTTPServer", CapturingServer),
            mock.patch.object(dashboard, "write_state"),
            mock.patch.object(dashboard, "remove_state"),
            mock.patch.object(dashboard, "diag"),
            self.assertRaises(StopServingError),
        ):
            dashboard.main()
        self.assertEqual([("127.0.0.1", 4553)], captured_addresses)

        httpd = dashboard.ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
        thread = serve_until_closed(httpd)
        try:
            port = httpd.server_port
            code, _, _ = self._response(
                port, "GET", "/api/health", headers={"Host": "evil.example"}
            )
            self.assertEqual(403, code)
            code, _, _ = self._response(
                port,
                "POST",
                "/api/notify",
                b"{}",
                {"Origin": "https://evil.example", "Content-Type": "application/json"},
            )
            self.assertEqual(403, code)
            code, _, _ = self._response(
                port,
                "POST",
                "/api/notify",
                b"{}",
                {"Origin": f"http://127.0.0.1:{port}", "Content-Type": "application/json"},
            )
            self.assertEqual(200, code)
            code, _, _ = self._response(
                port, "POST", "/api/notify", b"x", {"Content-Length": "65537"}
            )
            self.assertEqual(413, code)
            code, _, _ = self._response(
                port, "POST", "/api/notify", b"x", {"Content-Length": "not-a-number"}
            )
            self.assertEqual(413, code)
            code, _, _ = self._response(
                port,
                "GET",
                "/",
                headers={
                    "Sec-Fetch-Site": "cross-site",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Dest": "document",
                },
            )
            self.assertEqual(200, code)
        finally:
            httpd.shutdown()
            thread.join(timeout=5)

    def test_health_performs_no_harness_store_reads(self) -> None:
        httpd = dashboard.ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
        thread = serve_until_closed(httpd)
        try:
            # These are the store-access primitives used by collectors. Health
            # must remain a pure liveness response even if somebody bypasses
            # collect() and later reaches into a harness store directly.
            with (
                mock.patch.object(dashboard, "collect") as collect,
                mock.patch("builtins.open", side_effect=AssertionError("health read a file")),
                mock.patch.object(
                    dashboard.os,
                    "scandir",
                    side_effect=AssertionError("health scanned a directory"),
                ),
                mock.patch.object(
                    dashboard.glob,
                    "glob",
                    side_effect=AssertionError("health globbed a store"),
                ),
                mock.patch.object(
                    dashboard.sqlite3,
                    "connect",
                    side_effect=AssertionError("health opened SQLite"),
                ),
            ):
                code, _, body = self._response(httpd.server_port, "GET", "/api/health")
            self.assertEqual(200, code)
            self.assertTrue(json.loads(body)["ok"])
            collect.assert_not_called()
        finally:
            httpd.shutdown()
            thread.join(timeout=5)

    def test_collection_memo_holds_its_lock_across_one_scan(self) -> None:
        entered = threading.Event()
        release = threading.Event()
        second_done = threading.Event()
        bodies: list[bytes] = []

        def scan(*_: Any) -> dict[str, Any]:
            entered.set()
            self.assertTrue(release.wait(timeout=5), "test did not release the scan")
            return {"generated": 1.0, "sessions": [], "harnesses": []}

        def second_request() -> None:
            bodies.append(dashboard.collect_json(24, False))
            second_done.set()

        with mock.patch.object(dashboard, "collect", side_effect=scan) as collect:
            first = threading.Thread(
                target=lambda: bodies.append(dashboard.collect_json(24, False))
            )
            second = threading.Thread(target=second_request)
            first.start()
            self.assertTrue(entered.wait(timeout=5), "first scan did not begin")
            second.start()
            self.assertFalse(second_done.wait(timeout=0.2), "second request scanned concurrently")
            release.set()
            first.join(timeout=5)
            second.join(timeout=5)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(1, collect.call_count)
        self.assertEqual(2, len(bodies))
        self.assertEqual(bodies[0], bodies[1])

    def test_collection_memo_releases_its_lock_after_failure(self) -> None:
        good = {"generated": 1.0, "sessions": [], "harnesses": []}
        with mock.patch.object(
            dashboard, "collect", side_effect=(RuntimeError("broken store"), good)
        ):
            with self.assertRaisesRegex(RuntimeError, "broken store"):
                dashboard.collect_json(24, False)
            self.assertEqual(good, json.loads(dashboard.collect_json(24, False)))

    def test_session_end_cannot_be_undone_by_a_slow_notification(self) -> None:
        httpd = dashboard.ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
        thread = serve_until_closed(httpd)
        entered = threading.Event()
        release = threading.Event()
        notification: list[tuple[int, bytes]] = []

        def slow_lookup(*_: Any) -> tuple[bool, str]:
            entered.set()
            self.assertTrue(release.wait(timeout=5), "test did not release notification")
            return True, "user-event"

        def post_notification() -> None:
            code, _, body = self._response(
                httpd.server_port,
                "POST",
                "/api/notify",
                json.dumps(
                    {
                        "session_id": "12345678-session",
                        "message": "permission needed",
                        "transcript_path": "/slow.jsonl",
                    }
                ).encode(),
            )
            notification.append((code, body))

        try:
            with (
                mock.patch.object(dashboard, "claude_hook_user_event", side_effect=slow_lookup),
                mock.patch.object(dashboard, "notify_mac"),
            ):
                worker = threading.Thread(target=post_notification)
                worker.start()
                self.assertTrue(entered.wait(timeout=5), "notification did not begin")
                code, _, body = self._response(
                    httpd.server_port,
                    "POST",
                    "/api/notify",
                    b'{"session_id":"12345678-session","hook_event_name":"SessionEnd"}',
                )
                self.assertEqual(200, code)
                self.assertEqual({"ok": True, "cleared": "session_end"}, json.loads(body))
                release.set()
                worker.join(timeout=5)
            self.assertFalse(worker.is_alive())
            self.assertEqual([(200, b'{"ok":true,"superseded":true}')], notification)
            self.assertNotIn("12345678", dashboard._hook_notifs)
        finally:
            release.set()
            httpd.shutdown()
            thread.join(timeout=5)

    def test_daemon_respawn_uses_the_absolute_stable_launcher(self) -> None:
        args = argparse.Namespace(port=4553, window_hours=24.0, no_spacedock=False, daemon=True)
        with tempfile.TemporaryDirectory() as tmp:
            log_file = str(Path(tmp) / "cargento.log")
            with mock.patch.object(dashboard.subprocess, "Popen") as popen:
                popen.return_value = mock.Mock(pid=1)
                dashboard.spawn_detached(args, log_file)
        self.assertEqual(str(SERVER_PATH), popen.call_args.args[0][1])

    def test_copied_plugin_launches_without_repository_imports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copied_plugin = root / "copied-plugin" / "cargento"
            shutil.copytree(SERVER_PATH.parents[2], copied_plugin)
            launcher = copied_plugin / "skills" / "cargento" / "server.py"
            cwd = root / "unrelated"
            cwd.mkdir()
            cargento_home = root / "state"
            port = self._candidate_port()
            env = self._clean_env(cargento_home)
            state_path = cargento_home / f"cargento-{port}.json"
            proc = subprocess.Popen(
                [sys.executable, str(launcher), "--port", str(port)],
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            owned = False
            try:
                self._await_owned_instance(port, proc, state_path)
                owned = True
                code, headers, body = self._response(port, "GET", "/")
                self.assertEqual(200, code)
                self.assertEqual("text/html; charset=utf-8", headers["Content-Type"])
                self.assertTrue(body.startswith(b"<!doctype html>"))
            finally:
                stop: subprocess.CompletedProcess[bytes] | None = None
                # A live owned process has exclusive possession of its port,
                # so the copied --stop command cannot reach a foreign server.
                if owned and self._owns_instance(port, proc, state_path):
                    stop = subprocess.run(
                        [sys.executable, str(launcher), "--port", str(port), "--stop"],
                        cwd=cwd,
                        env=env,
                        capture_output=True,
                        timeout=15,
                        check=False,
                    )
                if proc.poll() is None:
                    proc.terminate()
                    with contextlib.suppress(subprocess.TimeoutExpired):
                        proc.wait(timeout=5)
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=5)
                if proc.stdout is not None:
                    proc.stdout.close()
                if proc.stderr is not None:
                    proc.stderr.close()
                if owned:
                    self.assertIsNotNone(stop, "owned launcher disappeared before safe --stop")
                    assert stop is not None
                    self.assertEqual(0, stop.returncode, stop.stderr.decode("utf-8", "replace"))
                    self.assertTrue(dashboard.await_release(port, timeout=5))
                    self.assertEqual([], list(cargento_home.iterdir()))

    def test_windows_detached_argv_preserves_an_absolute_launcher_path(self) -> None:
        args = argparse.Namespace(port=4553, window_hours=24.0, no_spacedock=False, daemon=True)
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(dashboard.os.path, "abspath", return_value="C:\\plugin\\server.py"),
            mock.patch.object(dashboard.subprocess, "DETACHED_PROCESS", 8, create=True),
            mock.patch.object(dashboard.subprocess, "CREATE_NEW_PROCESS_GROUP", 512, create=True),
            mock.patch.object(dashboard.subprocess, "Popen") as popen,
        ):
            popen.return_value = mock.Mock(pid=1)
            dashboard.spawn_detached(args, str(Path(tmp) / "cargento.log"))
        self.assertEqual("C:\\plugin\\server.py", popen.call_args.args[0][1])
        self.assertEqual(520, popen.call_args.kwargs["creationflags"])

    def test_main_and_detached_spawn_forward_current_arguments(self) -> None:
        spawned = mock.Mock(pid=99)
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.dict(os.environ, {"CARGENTO_HOME": tmp}),
            mock.patch.object(dashboard.os, "name", "nt"),
            mock.patch.object(
                sys,
                "argv",
                [
                    "server.py",
                    "--port",
                    "6789",
                    "--window-hours",
                    "7.5",
                    "--no-spacedock",
                    "--daemon",
                ],
            ),
            mock.patch.object(dashboard, "spawn_detached", return_value=spawned) as spawn,
            mock.patch.object(dashboard, "await_spawned", return_value=("started", 0)),
            mock.patch.object(dashboard, "diag"),
            self.assertRaises(SystemExit) as caught,
        ):
            dashboard.main()
        self.assertEqual(0, caught.exception.code)
        forwarded = dashboard.forwarded_args(spawn.call_args.args[0])
        self.assertEqual(["--port", "6789", "--window-hours", "7.5", "--no-spacedock"], forwarded)
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(dashboard.subprocess, "Popen") as popen,
        ):
            popen.return_value = spawned
            dashboard.spawn_detached(spawn.call_args.args[0], str(Path(tmp) / "cargento.log"))
        self.assertEqual(
            ["--port", "6789", "--window-hours", "7.5", "--no-spacedock"],
            popen.call_args.args[0][2:],
        )

    def test_served_page_bytes_equal_the_embedded_page(self) -> None:
        page = dashboard.PAGE.encode()
        style = re.search(r"<style>\n(.*?)</style>", dashboard.PAGE, re.DOTALL)
        script = re.search(r"<script>\n(.*?)</script>", dashboard.PAGE, re.DOTALL)
        assert style is not None
        assert script is not None
        self.assertEqual(93_713, len(page))
        self.assertEqual(
            "3a2264edda06e9caf1fbd34c0226ad8c3b0b320f206a87676c183492a5241b37",
            hashlib.sha256(page).hexdigest(),
        )
        self.assertEqual(27_180, len(style.group(1).encode()))
        self.assertEqual(
            "e96a2292642bfc40d4bd40e9c23c733cf8d8ef524f55dfb9328685ac53f02cf1",
            hashlib.sha256(style.group(1).encode()).hexdigest(),
        )
        self.assertEqual(66_237, len(script.group(1).encode()))
        self.assertEqual(
            "bfe260f4c9807d4a59de41f2a37b3711e76547fc67acc73f9201ff11da4a0e48",
            hashlib.sha256(script.group(1).encode()).hexdigest(),
        )
        httpd = dashboard.ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
        thread = serve_until_closed(httpd)
        try:
            code, _, served = self._response(httpd.server_port, "GET", "/")
            self.assertEqual(200, code)
            self.assertEqual(page, served)
        finally:
            httpd.shutdown()
            thread.join(timeout=5)


class CargentoServerTest(PageJsHarness):
    def test_page_marks_repeated_refresh_failures_as_stalled(self) -> None:
        self.assertIn('id="live-status"', dashboard.PAGE)
        self.assertIn("window.__refreshFailures < 2", dashboard.PAGE)
        self.assertIn("stalled · last update", dashboard.PAGE)
        self.assertIn("console.error", dashboard.PAGE)
        self.assertIn("latestSettledRefresh", dashboard.PAGE)
        self.assertIn("sequence < latestSettledRefresh", dashboard.PAGE)

    def test_entity_slugs_elide_in_the_middle_not_the_tail(self) -> None:
        """Entity slugs in one workflow share a long prefix and differ only at
        the end, so tail truncation rendered two different entities as the same
        string. The full value stays available as a title attribute."""
        self.assertIn("function sdSlug(slug)", dashboard.PAGE)
        self.assertIn('title="${esc(ent.slug)}">${esc(sdSlug(ent.slug))}', dashboard.PAGE)

        node = shutil.which("node")
        if node is None:
            self.skipTest("node not installed; CI runs this branch")
        js = "\n".join(re.findall(r"<script[^>]*>\n?(.*?)</script>", dashboard.PAGE, re.DOTALL))
        # Just the helper and its constants. Taking the whole prefix would drag
        # in top-level browser globals (`location`) that node does not have.
        source = re.search(r"const SD_SLUG_MAX = .*?\n}\n", js, re.DOTALL)
        assert source is not None, "sdSlug and its constants moved"
        # Run the real function rather than restating its arithmetic here.
        probe = (
            source.group(0) + "\nconst cases = ['drc-3832',"
            " 'datarecce-recce-cloud-infra-pr-1573',"
            " 'datarecce-recce-cloud-infra-pr-1587'];\n"
            "console.log(JSON.stringify(cases.map(sdSlug)));\n"
        )
        with tempfile.TemporaryDirectory() as holder:
            script = Path(holder) / "probe.mjs"
            script.write_text(probe, encoding="utf-8")
            # Explicit UTF-8 both ways. node reads and writes UTF-8; `text=True`
            # alone decodes through the locale codec, so on Windows (cp1252) the
            # ellipsis comes back as "â€¦" — three characters, which fails both
            # the "elided" and the width assertion below for a reason that has
            # nothing to do with the code under test.
            proc = subprocess.run(
                [node, str(script)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
                check=True,
            )
        short, first, second = json.loads(proc.stdout)

        self.assertEqual("drc-3832", short)  # under the cap, untouched
        self.assertNotEqual(first, second)  # the whole point
        for rendered, full in ((first, "…-pr-1573"), (second, "…-pr-1587")):
            self.assertTrue(rendered.endswith(full[1:]), rendered)
            self.assertIn("…", rendered)
            self.assertLessEqual(len(rendered), 22)

    def test_output_rate_rows_use_hoverable_harness_badges(self) -> None:
        self.assertIn(
            '<span class="rrow-badge">${badge(r.key, true)}</span>',
            dashboard.PAGE,
        )

    def test_pi_badge_uses_the_explicit_pi_label(self) -> None:
        # A generic fallback monogram hides a missing harness presentation entry.
        rendered = self._run_page_js("console.log(JSON.stringify(HARNESS.pi));")
        self.assertEqual({"code": "PI", "name": "Pi"}, rendered)

    def test_page_ships_trailing_rate_sparklines(self) -> None:
        # Overall + per-session trailing sparklines: client-side ring buffers
        # over a 5-minute window, rendered as SVG in the rate tile and cards.
        self.assertIn("SPARK_WINDOW_SEC = 300", dashboard.PAGE)
        self.assertIn("const rateHistory = []", dashboard.PAGE)
        self.assertIn("const sessRateHistory = new Map()", dashboard.PAGE)
        self.assertIn("function recordRates", dashboard.PAGE)
        self.assertIn("function sparkSVG", dashboard.PAGE)
        self.assertIn('class="spark-wrap"', dashboard.PAGE)
        self.assertIn('class="rate-spark"', dashboard.PAGE)
        # Buffers only grow on fresh payloads and drop points past the window.
        self.assertIn("recordRates(data)", dashboard.PAGE)
        self.assertIn("arr.shift()", dashboard.PAGE)

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_sparkline_buffers_behave_correctly(self) -> None:
        # Execute the page's actual JS (ring buffers + SVG generation) under
        # node with a minimal DOM stub, and assert on observable behavior.
        checks = """
const out = {};
{
  const arr = [];
  for(let t = 0; t <= 400; t += 5) pushPoint(arr, t, t);
  pushPoint(arr, 400, 999); // same-timestamp replay must be ignored
  out.pruned = {len: arr.length, first: arr[0].t,
                last: arr[arr.length-1].t, lastV: arr[arr.length-1].v};
}
{
  // Two live sessions whose display ids truncate identically must not
  // share one buffer (Gemini "session-*" fallback ids all become
  // "session-" after display truncation).
  recordRates({generated: 1000, summary: {rate_per_min: 14}, sessions: [
    {harness:"gemini", session:"session-", sid:"session-aaaa", rate_per_min:5},
    {harness:"gemini", session:"session-", sid:"session-bbbb", rate_per_min:9}]});
  const a = sessRateHistory.get("gemini:session-aaaa");
  const b = sessRateHistory.get("gemini:session-bbbb");
  out.aliasing = {buffers: sessRateHistory.size,
                  a: a && a[0] && a[0].v, b: b && b[0] && b[0].v};
  __setNow(1005);
  recordRates({generated: 1005, summary: {rate_per_min: 6}, sessions: [
    {harness:"gemini", session:"session-", sid:"session-aaaa", rate_per_min:6}]});
  const a2 = sessRateHistory.get("gemini:session-aaaa") || [];
  out.dropped = {buffers: sessRateHistory.size, aLen: a2.length};
}
{
  // Points carry the VIEWER's clock: a skewed/lagging server `generated`
  // must not shift timestamps, and a replayed `generated` records nothing.
  __setNow(1010);
  recordRates({generated: 999111, summary: {rate_per_min: 3}, sessions: []});
  const last = rateHistory[rateHistory.length-1];
  const lenBefore = rateHistory.length;
  __setNow(1011);
  recordRates({generated: 999111, summary: {rate_per_min: 4}, sessions: []});
  out.clock = {t: last.t, v: last.v, replayDropped: rateHistory.length === lenBefore};
}
{
  const pts = [{t:900, v:0}, {t:950, v:50}, {t:1000, v:100}];
  const svg = sparkSVG(pts, 1000, 100, 46, true);
  const nums = (svg.match(/-?\\d+(\\.\\d+)?/g) || []).map(Number);
  out.svg = {hasLine: svg.includes("<polyline"),
             finite: nums.length > 0 && nums.every(Number.isFinite),
             single: !sparkSVG([{t:1000, v:1}], 1000, 100, 46, true)
                       .includes("<polyline")};
}
console.log(JSON.stringify(out));
"""
        out = self._run_page_js(checks)
        # 300s window over t=0..400 step 5 keeps t=100..400; duplicate dropped.
        self.assertEqual({"len": 61, "first": 100, "last": 400, "lastV": 400}, out["pruned"])
        self.assertEqual({"buffers": 2, "a": 5, "b": 9}, out["aliasing"])
        # Departed session-bbbb is pruned; session-aaaa accumulates.
        self.assertEqual({"buffers": 1, "aLen": 2}, out["dropped"])
        # Viewer-clock stamping: server said 999111, viewer clock said 1010.
        self.assertEqual({"t": 1010, "v": 3, "replayDropped": True}, out["clock"])
        self.assertEqual({"hasLine": True, "finite": True, "single": True}, out["svg"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_browser_notifications_fire_only_on_transitions_the_server_missed(self) -> None:
        # Exactly one layer may notify per transition
        # (design decision D-3 in docs/design-cross-platform.md).
        checks = """
__els.app = {innerHTML:""};
const blocked = {
  harness:"claude", session:"12345678", sid:"12345678", project:"proj",
  title:null, last_prompt:"", state:"needs_input", state_detail:"open question",
  active:true, last_activity:100, blocked_since:970, rate_per_min:0,
  total:0, done:0, open:0, progress_pct:0, eta_h:null, turn:null,
  subagents:[], tasks:[]
};
const idle = {...blocked, state:"idle", state_detail:"awaiting your message"};
const payload = (sessions, native) => ({
  generated:1000, window_hours:24, show_all:false, native_notify:native,
  harnesses:[], sessions,
  summary:{needs_input:0, working:0, rate_per_min:0, active_sessions:1,
           open_tasks:0, progress_pct:0, total_tasks:0, total_done:0}
});
const reset = perm => {
  __notifications = []; __notifyPermission = perm;
  notifyState = new Map(); notifyPrimed = false;
};
const out = {};

// The server already popped natively: the page must stay silent.
reset("granted");
render(payload([idle], "osascript"));
render(payload([blocked], "osascript"));
out.nativeOwnsIt = __notifications.length;

// No native backend (Linux/Windows today): the page notifies.
reset("granted");
render(payload([idle], ""));
render(payload([blocked], ""));
out.browserFired = __notifications.length;
out.body = __notifications[0] && __notifications[0].body;
out.tag = __notifications[0] && __notifications[0].tag;

// Still blocked on later refreshes: notify on the transition, not repeatedly.
render(payload([blocked], ""));
render(payload([blocked], ""));
out.noRepeat = __notifications.length;

// Cleared, then blocked again: that is a new transition.
render(payload([idle], ""));
render(payload([blocked], ""));
out.refired = __notifications.length;

// A session already blocked when the page opens must not pop on first paint.
reset("granted");
render(payload([blocked], ""));
out.primed = __notifications.length;

// Permission not granted: record state, raise nothing.
reset("default");
render(payload([idle], ""));
render(payload([blocked], ""));
out.ungranted = __notifications.length;

// Inactive sessions are outside the window and never notify.
reset("granted");
render(payload([{...idle, active:false}], ""));
render(payload([{...blocked, active:false}], ""));
out.inactive = __notifications.length;
console.log(JSON.stringify(out));
"""
        out = self._run_page_js(checks)
        self.assertEqual(0, out["nativeOwnsIt"], "would double-notify on macOS")
        self.assertEqual(1, out["browserFired"])
        self.assertEqual("[proj] open question", out["body"])
        self.assertEqual("claude:12345678", out["tag"])
        self.assertEqual(1, out["noRepeat"], "notified again while already blocked")
        self.assertEqual(2, out["refired"])
        self.assertEqual(0, out["primed"], "popped for a pre-existing block on first paint")
        self.assertEqual(0, out["ungranted"])
        self.assertEqual(0, out["inactive"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_notification_permission_control_reflects_state(self) -> None:
        checks = """
__els.app = {innerHTML:""};
const payload = native => ({
  generated:1000, window_hours:24, show_all:false, native_notify:native,
  harnesses:[], sessions:[],
  summary:{needs_input:0, working:0, rate_per_min:0, active_sessions:0,
           open_tasks:0, progress_pct:0, total_tasks:0, total_done:0}
});
const out = {};
__notifyPermission = "default"; out.prompt = notifyControl(payload(""));
__notifyPermission = "denied";  out.denied = notifyControl(payload(""));
__notifyPermission = "granted"; out.granted = notifyControl(payload(""));
__notifyPermission = "default"; out.native  = notifyControl(payload("osascript"));

// Granting re-renders so the button disappears without a reload.
__notifyPermission = "default";
render(payload(""));
out.buttonBefore = __els.app.innerHTML.includes("Enable notifications");
requestNotifyPermission();
out.buttonWhilePending = __els.app.innerHTML.includes("Enable notifications");
await __settle(); await __settle();
out.buttonAfter = __els.app.innerHTML.includes("Enable notifications");
console.log(JSON.stringify(out));
"""
        out = self._run_page_js(checks)
        self.assertIn("Enable notifications", out["prompt"])
        self.assertIn("notifications blocked", out["denied"])
        self.assertEqual("", out["granted"], "no control once permission is granted")
        self.assertEqual("", out["native"], "server owns popups; no control needed")
        self.assertTrue(out["buttonBefore"])
        self.assertTrue(out["buttonWhilePending"], "must not clear before permission settles")
        self.assertFalse(out["buttonAfter"], "control should clear after granting")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_page_works_without_the_notification_api(self) -> None:
        # Older or locked-down browsers expose no Notification constructor.
        checks = """
__els.app = {innerHTML:""};
Notification = undefined;
const d = {
  generated:1000, window_hours:24, show_all:false, native_notify:"",
  harnesses:[], sessions:[],
  summary:{needs_input:0, working:0, rate_per_min:0, active_sessions:0,
           open_tasks:0, progress_pct:0, total_tasks:0, total_done:0}
};
render(d);
requestNotifyPermission();
console.log(JSON.stringify({
  permission: notifyPermission(), control: notifyControl(d), rendered: !!__els.app.innerHTML
}));
"""
        out = self._run_page_js(checks)
        self.assertEqual("unsupported", out["permission"])
        self.assertEqual("", out["control"])
        self.assertTrue(out["rendered"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_needs_input_ui_uses_block_anchor_and_displayed_count(self) -> None:
        checks = """
__els.app = {innerHTML:""};
const activeNeed = {
  harness:"claude", session:"12345678", sid:"12345678", project:"sample",
  title:null, last_prompt:"Fallback prompt", state:"needs_input",
  state_detail:"permission needed", active:true, last_activity:100,
  blocked_since:970, rate_per_min:0, total:0, done:0, open:0,
  progress_pct:0, eta_h:null, turn:null, subagents:[], tasks:[]
};
const inactiveNeed = {...activeNeed, sid:"old", session:"old", active:false};
const data = {
  generated:1000, window_hours:24, show_all:true, harnesses:[],
  summary:{needs_input:99, working:0, rate_per_min:0, active_sessions:1,
           open_tasks:0, progress_pct:0, total_tasks:0, total_done:0},
  sessions:[activeNeed, inactiveNeed]
};
const row = needRow(data, activeNeed);
render(data);
console.log(JSON.stringify({
  rowUsesPrompt: row.includes("Fallback prompt"),
  rowUsesAnchor: row.includes(">30s<"),
  title: document.title,
  shownNeeds: (__els.app.innerHTML.match(/class="need"/g) || []).length
}));
"""
        out = self._run_page_js(checks)
        self.assertEqual(
            {
                "rowUsesPrompt": True,
                "rowUsesAnchor": True,
                "title": "(1!) Cargento",
                "shownNeeds": 1,
            },
            out,
        )

    def test_long_turn_warning_uses_styled_tooltip_not_native_title(self) -> None:
        # The (!) icon must use the app's styled tooltip (fast, themed), not
        # the native title attribute (multi-second hover delay).
        self.assertNotIn('class="lwarn" title=', dashboard.PAGE)
        self.assertIn('<span class="ltip">', dashboard.PAGE)
        self.assertIn('class="lwarn" tabindex="0"', dashboard.PAGE)
        self.assertIn(".lwarn:hover .ltip", dashboard.PAGE)
        self.assertIn("transition-delay:.2s", dashboard.PAGE)

    def test_page_restores_sparkline_hover_and_focus_after_render(self) -> None:
        # render() replaces #app's innerHTML every poll; the hover crosshair
        # and keyboard focus on the rate sparkline must be restored after.
        self.assertIn("sparkPointer", dashboard.PAGE)
        self.assertIn("restoreSparkState", dashboard.PAGE)
        self.assertIn("restoreSparkState(sparkFocused, savedPointer)", dashboard.PAGE)
        self.assertIn("preventScroll", dashboard.PAGE)

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_sparkline_hover_lifecycle_across_renders_and_window_exit(self) -> None:
        # Behavioral coverage for the interaction layer: hover shows on
        # pointermove, survives a full render() DOM swap, is CLEARED when the
        # pointer leaves the window (no in-document pointermove fires), stays
        # cleared on later renders, and keyboard focus is restored.
        checks = """
const out = {};
const wrap = {
  id: "spark-main",
  dataset: {now: "1000"},
  style: {},
  closest(sel){ return sel === "#spark-main" ? this : null; },
  getBoundingClientRect(){
    return {left: 0, top: 0, right: 100, bottom: 46, width: 100, height: 46};
  },
  focus(){ document.activeElement = this; __fire("focusin", {target: this}); }
};
const tip = {style: {}, appendChild(){}};
const xline = {style: {}, parentElement: wrap};
__els["spark-main"] = wrap; __els["spark-tip"] = tip; __els["spark-x"] = xline;
__els["app"] = {innerHTML: ""};
pushPoint(rateHistory, 995, 100);
pushPoint(rateHistory, 1000, 200);
const d = {generated: 1000, window_hours: 24, show_all: false, harnesses: [],
           summary: {needs_input: 0, working: 0, rate_per_min: 200,
                     total_tasks: 0, open_tasks: 0, progress_pct: 0,
                     total_done: 0},
           sessions: []};
__fire("pointermove", {target: wrap, clientX: 50, clientY: 20});
out.hoverShown = tip.style.opacity == 1;
render(d);
out.restoredAfterRender = tip.style.opacity == 1;
__fire("mouseout", {relatedTarget: null});   // pointer left the window
out.clearedOnExit = tip.style.opacity == 0 && sparkPointer === null;
render(d);
out.staysHiddenAfterRender = tip.style.opacity == 0;
wrap.focus();
render(d);
out.focusRestored = document.activeElement === wrap && tip.style.opacity == 1;
console.log(JSON.stringify(out));
"""
        out = self._run_page_js(checks)
        self.assertEqual(
            {
                "hoverShown": True,
                "restoredAfterRender": True,
                "clearedOnExit": True,
                "staysHiddenAfterRender": True,
                "focusRestored": True,
            },
            out,
        )

    def test_state_file_roundtrips_and_names_itself_per_port(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.dict(os.environ, {"CARGENTO_HOME": tmp}),
        ):
            dashboard.write_state(4553)
            dashboard.write_state(9999)
            self.assertTrue(os.path.exists(os.path.join(tmp, "cargento-4553.json")))
            state = dashboard.read_state(4553)
            assert state is not None
            self.assertEqual(os.getpid(), state["pid"])
            self.assertEqual(4553, state["port"])
            self.assertEqual(dashboard.log_path(4553), state["log"])
            self.assertEqual(sys.executable, state["python"])
            # Two instances on two ports do not overwrite each other.
            other = dashboard.read_state(9999)
            assert other is not None
            self.assertEqual(9999, other["port"])
            dashboard.remove_state(4553)
            self.assertIsNone(dashboard.read_state(4553))
            dashboard.remove_state(4553)  # removing twice is not an error

    def test_read_state_returns_none_for_absent_corrupt_and_non_object_files(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.dict(os.environ, {"CARGENTO_HOME": tmp}),
        ):
            self.assertIsNone(dashboard.read_state(4553))
            Path(dashboard.state_path(4553)).write_text("{not json", encoding="utf-8")
            self.assertIsNone(dashboard.read_state(4553))
            Path(dashboard.state_path(4553)).write_text("[1,2]", encoding="utf-8")
            self.assertIsNone(dashboard.read_state(4553))

    def test_write_state_reports_and_survives_an_unwritable_home(self) -> None:
        # A dashboard that cannot write its state file still serves; --status
        # just cannot see it. This must never be fatal.
        with tempfile.TemporaryDirectory() as tmp:
            blocker = os.path.join(tmp, "home")
            Path(blocker).write_text("not a directory", encoding="utf-8")
            with mock.patch.dict(os.environ, {"CARGENTO_HOME": blocker}):
                with mock.patch.object(dashboard, "diag") as diag:
                    dashboard.write_state(4553)
                self.assertTrue(diag.called)

    def test_probe_port_classifies_cargento_foreign_and_closed(self) -> None:
        httpd = dashboard.ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        port = httpd.server_port
        try:
            kind, health = dashboard.probe_port(port, timeout=2)
            self.assertEqual("cargento", kind)
            assert health is not None
            self.assertEqual(os.getpid(), health["pid"])
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)
        # Same port, now nothing listening.
        self.assertEqual(("closed", None), dashboard.probe_port(port, timeout=1))

    def test_probe_port_calls_a_non_cargento_listener_foreign(self) -> None:
        class Other(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"hi")

            def log_message(self, *args: object) -> None:
                pass

        httpd = dashboard.ThreadingHTTPServer(("127.0.0.1", 0), Other)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            # 200 but not JSON: something else owns this port. Reporting it as
            # Cargento is how a stop command ends up aimed at an unrelated
            # process.
            self.assertEqual(("foreign", None), dashboard.probe_port(httpd.server_port, timeout=2))
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_probe_port_rejects_recursive_and_lookalike_health_payloads(self) -> None:
        invalid = (
            ("recursive JSON", b"[" * 2000 + b"]" * 2000),
            ("truthy ok", b'{"ok":"yes","pid":7,"port":4553,"started":1}'),
            ("boolean pid", b'{"ok":true,"pid":true,"port":4553,"started":1}'),
            ("zero pid", b'{"ok":true,"pid":0,"port":4553,"started":1}'),
            ("wrong port", b'{"ok":true,"pid":7,"port":9999,"started":1}'),
            ("missing start time", b'{"ok":true,"pid":7,"port":4553}'),
        )
        for label, body in invalid:
            with (
                self.subTest(payload=label),
                mock.patch.object(http.client, "HTTPConnection") as connection,
            ):
                response = connection.return_value.getresponse.return_value
                response.status = 200
                response.read.return_value = body
                self.assertEqual(("foreign", None), dashboard.probe_port(4553))
                connection.return_value.close.assert_called_once_with()

    def test_instance_status_covers_running_stale_foreign_and_absent(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.dict(os.environ, {"CARGENTO_HOME": tmp}),
        ):
            health = {"ok": True, "pid": 4242, "port": 4553, "started": 1000.0}
            with mock.patch.object(dashboard, "probe_port", return_value=("cargento", health)):
                running = dashboard.instance_status(4553)
            self.assertEqual("running", running["state"])
            self.assertEqual(4242, running["pid"])

            with mock.patch.object(dashboard, "probe_port", return_value=("closed", None)):
                self.assertEqual("absent", dashboard.instance_status(4553)["state"])
                dashboard.write_state(4553)
                stale = dashboard.instance_status(4553)
            self.assertEqual("stale", stale["state"])
            self.assertEqual(os.getpid(), stale["pid"])

            with mock.patch.object(dashboard, "probe_port", return_value=("foreign", None)):
                self.assertEqual("foreign", dashboard.instance_status(4553)["state"])

    def test_render_status_names_the_state_and_never_suggests_a_kill(self) -> None:
        running = dashboard.render_status(
            {"state": "running", "port": 4553, "pid": 7, "started": 1000.0, "log": "/l"}
        )
        self.assertIn("running", running)
        self.assertIn("pid 7", running)
        self.assertIn("http://127.0.0.1:4553/", running)
        stale = dashboard.render_status({"state": "stale", "port": 4553, "pid": 7, "log": "/l"})
        self.assertIn("--stop", stale)
        foreign = dashboard.render_status({"state": "foreign", "port": 4553, "pid": None})
        self.assertIn("another process", foreign)
        self.assertIn("Nothing was stopped", foreign)
        self.assertIn("not running", dashboard.render_status({"state": "absent", "port": 4553}))

    def test_render_status_survives_a_started_value_it_cannot_convert(self) -> None:
        # Keep render_status defensive even though probe_port now rejects
        # non-finite values. Tests and callers can still construct a status
        # directly, and a value outside time_t must not replace a line with a
        # traceback.
        for started in (1e19, -1e19, float("inf"), float("nan")):
            with self.subTest(started=started):
                line = dashboard.render_status(
                    {"state": "running", "port": 4553, "pid": 7, "started": started, "log": "/l"}
                )
                self.assertIn("running", line)
                self.assertIn("since unknown", line)

    def test_port_released_is_false_while_a_server_still_holds_the_port(self) -> None:
        httpd = dashboard.LoopbackHTTPServer(("127.0.0.1", 0), dashboard.Handler)
        port = httpd.server_port
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            self.assertFalse(dashboard.port_released(port), "bound and serving")
            httpd.shutdown()
            thread.join(timeout=5)
            # The accept loop has exited but the socket is still open. A connect
            # probe cannot see this state, and repeated connects fill the
            # backlog and then wrongly report the port gone; binding sees it.
            for _ in range(dashboard.LoopbackHTTPServer.request_queue_size + 3):
                self.assertFalse(dashboard.port_released(port), "bound, not accepting")
        finally:
            httpd.server_close()
            thread.join(timeout=2)
        self.assertTrue(dashboard.port_released(port), "closed")

    def test_stop_instance_waits_for_the_port_before_claiming_it_stopped(self) -> None:
        # A server that answers the shutdown POST but never releases the port
        # must not be reported as stopped: the caller's next move is a start.
        running = {"state": "running", "port": 4553, "pid": 7, "started": 1000.0, "log": "/l"}
        with (
            mock.patch.object(dashboard, "instance_status", return_value=running),
            mock.patch.object(dashboard, "port_released", return_value=False) as released,
            mock.patch.object(dashboard, "STOP_RELEASE_TIMEOUT_SEC", 0.2),
            mock.patch.object(http.client, "HTTPConnection") as conn,
        ):
            conn.return_value.getresponse.return_value.status = 200
            message, code = dashboard.stop_instance(4553)
        self.assertEqual(1, code)
        self.assertIn("still listening", message)
        self.assertNotIn("stopped (pid", message)
        self.assertGreater(released.call_count, 1, "it never waited")

    def test_await_release_sleeps_between_failed_probes(self) -> None:
        with (
            mock.patch.object(dashboard, "port_released", side_effect=(False, True)) as released,
            mock.patch.object(dashboard.time, "sleep") as sleep,
        ):
            self.assertTrue(dashboard.await_release(4553, timeout=1))
        self.assertEqual(2, released.call_count)
        sleep.assert_called_once_with(0.05)

    def test_stop_instance_reports_a_refused_shutdown_response(self) -> None:
        running = {"state": "running", "port": 4553, "pid": 7, "started": 1000.0, "log": "/l"}
        with (
            mock.patch.object(dashboard, "instance_status", return_value=running),
            mock.patch.object(dashboard, "await_release") as released,
            mock.patch.object(http.client, "HTTPConnection") as connection,
        ):
            response = connection.return_value.getresponse.return_value
            response.status = 503
            message, code = dashboard.stop_instance(4553)
        self.assertEqual(1, code)
        self.assertIn("refused to stop", message)
        self.assertIn("503", message)
        released.assert_not_called()
        connection.return_value.close.assert_called_once_with()

    def test_status_flag_exits_zero_only_when_running(self) -> None:
        for state, expected in (("running", 0), ("stale", 1), ("foreign", 1), ("absent", 1)):
            with (
                mock.patch.object(
                    dashboard,
                    "instance_status",
                    return_value={"state": state, "port": 4553, "pid": 1},
                ),
                mock.patch.object(sys, "argv", ["server.py", "--status"]),
                mock.patch.object(dashboard, "diag"),
                self.assertRaises(SystemExit) as caught,
            ):
                dashboard.main()
            self.assertEqual(expected, caught.exception.code, state)

    def test_stop_instance_stops_a_running_server_over_http(self) -> None:
        httpd = dashboard.LoopbackHTTPServer(("127.0.0.1", 0), dashboard.Handler)
        port = httpd.server_port
        loop_exited = threading.Event()
        allow_close = threading.Event()
        result: list[tuple[str, int]] = []

        def serve_with_delayed_close() -> None:
            try:
                httpd.serve_forever()
            finally:
                loop_exited.set()
                allow_close.wait(timeout=10)
                httpd.server_close()

        thread = threading.Thread(target=serve_with_delayed_close, daemon=True)
        thread.start()
        stop_thread = threading.Thread(
            target=lambda: result.append(dashboard.stop_instance(port)),
            daemon=True,
        )
        try:
            stop_thread.start()
            self.assertTrue(loop_exited.wait(timeout=5), "serve_forever did not stop")
            self.assertFalse(dashboard.port_released(port), "the delayed close lost its bind")
            self.assertTrue(
                stop_thread.is_alive(),
                "stop_instance returned before the listener released its port",
            )
            allow_close.set()
            stop_thread.join(timeout=10)
            self.assertFalse(stop_thread.is_alive(), "stop_instance did not notice the release")
            self.assertEqual(1, len(result))
            message, code = result[0]
            self.assertEqual(0, code, message)
            self.assertIn("stopped", message)
            self.assertTrue(dashboard.port_released(port), "the port is still bound")
            thread.join(timeout=10)
            self.assertFalse(thread.is_alive())
        finally:
            allow_close.set()
            with contextlib.suppress(OSError):
                httpd.shutdown()
            stop_thread.join(timeout=2)
            thread.join(timeout=2)
            with contextlib.suppress(OSError):
                httpd.server_close()

    @unittest.skipIf(os.name == "nt", "POSIX SO_REUSEADDR/TIME_WAIT semantics")
    def test_port_release_probe_matches_the_listener_during_time_wait(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        listener.listen()
        client = socket.create_connection(("127.0.0.1", port), timeout=2)
        accepted, _ = listener.accept()
        try:
            # The server endpoint closes first, putting this local address in
            # TIME_WAIT after the client observes EOF and closes. Cargento's
            # listener can rebind here because it uses SO_REUSEADDR, so its
            # release probe must use the same option or report a false hold.
            accepted.close()
            self.assertEqual(b"", client.recv(1))
            client.close()
            listener.close()
            self.assertTrue(dashboard.port_released(port))
        finally:
            with contextlib.suppress(OSError):
                accepted.close()
            with contextlib.suppress(OSError):
                client.close()
            with contextlib.suppress(OSError):
                listener.close()

    def test_stop_instance_removes_a_stale_state_file_and_succeeds(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.dict(os.environ, {"CARGENTO_HOME": tmp}),
        ):
            dashboard.write_state(4553)
            # port_released is mocked alongside probe_port because the stale
            # branch now waits for the port too. Left live it asks the real
            # 4553, so the result would depend on what the machine is running.
            with (
                mock.patch.object(dashboard, "probe_port", return_value=("closed", None)),
                mock.patch.object(dashboard, "port_released", return_value=True),
            ):
                message, code = dashboard.stop_instance(4553)
            self.assertEqual(0, code)
            self.assertIn("stale", message)
            self.assertIsNone(dashboard.read_state(4553))

    def test_stop_instance_will_not_call_it_stopped_while_the_port_is_held(self) -> None:
        # main() removes the state file *before* it closes the listener, so a
        # stop already in progress reaches the absent/stale branches with the
        # port still bound. Exit 0 there meant "nothing running" for a port that
        # the very next start could not bind.
        for state, probe in (("stale", True), ("absent", False)):
            with (
                self.subTest(state=state),
                tempfile.TemporaryDirectory() as tmp,
                mock.patch.dict(os.environ, {"CARGENTO_HOME": tmp}),
            ):
                if probe:
                    dashboard.write_state(4553)
                with (
                    mock.patch.object(dashboard, "probe_port", return_value=("closed", None)),
                    mock.patch.object(dashboard, "port_released", return_value=False),
                    mock.patch.object(dashboard, "STOP_RELEASE_TIMEOUT_SEC", 0.1),
                ):
                    message, code = dashboard.stop_instance(4553)
                self.assertEqual(1, code)
                self.assertIn("still holding the port", message)
                self.assertNotIn("nothing running", message)
                if probe:
                    # It did not own the port, so it does not get to tidy up.
                    self.assertIsNotNone(dashboard.read_state(4553))

    def test_stop_instance_lets_the_port_settle_a_lost_connection(self) -> None:
        # A concurrent --stop, or the page's own button, can take the server down
        # while this request is in flight. The reset that causes is not evidence
        # the stop failed, and reporting exit 1 for it broke the documented
        # unconditional-stop idempotency about 3 runs in 5.
        running = {"state": "running", "port": 4553, "pid": 7, "started": 1000.0, "log": "/l"}
        for released, expected_code, expected in ((True, 0, "stopped"), (False, 1, "could not")):
            with (
                self.subTest(released=released),
                mock.patch.object(dashboard, "instance_status", return_value=running),
                mock.patch.object(dashboard, "port_released", return_value=released),
                mock.patch.object(dashboard, "STOP_RELEASE_TIMEOUT_SEC", 0.1),
                mock.patch.object(http.client, "HTTPConnection") as conn,
            ):
                conn.return_value.getresponse.side_effect = ConnectionResetError(
                    errno.ECONNRESET, "Connection reset by peer"
                )
                message, code = dashboard.stop_instance(4553)
            self.assertEqual(expected_code, code, message)
            self.assertIn(expected, message)

    def test_port_released_only_reads_address_in_use_as_still_held(self) -> None:
        # EACCES on a privileged port says nothing about whether the port is in
        # use, and answering "held" for it made --stop wait out its whole
        # timeout and then claim an instance was still listening when it had
        # stopped. Where a bind cannot answer, the answer is not "held".
        cases = (
            (errno.EADDRINUSE, False),
            # Windows reports an in-use port as EACCES once SO_EXCLUSIVEADDRUSE
            # is in play, so it counts as held there; on POSIX it only ever means
            # privilege, which is no evidence about use at all.
            (errno.EACCES, os.name != "nt"),
            (errno.EPERM, True),
            (errno.EMFILE, True),
            (errno.ENFILE, True),
        )
        for code, expected in cases:
            with (
                self.subTest(errno=errno.errorcode.get(code, code)),
                mock.patch.object(
                    dashboard.socket, "socket", side_effect=OSError(code, os.strerror(code))
                ),
            ):
                self.assertEqual(expected, dashboard.port_released(4553))
        # A real privileged port: nothing listens on 1, but binding is refused.
        if os.name != "nt" and os.geteuid() != 0:
            self.assertTrue(dashboard.port_released(1), "EACCES read as a held port")

    def test_read_state_rejects_a_corrupt_file_instead_of_raising(self) -> None:
        # json.load raises RecursionError, not ValueError, past the nesting
        # limit, and it tracebacked straight out of --status and --stop. "None if
        # there is none to trust" has to cover corrupt, not only missing.
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.dict(os.environ, {"CARGENTO_HOME": tmp}),
        ):
            path = Path(dashboard.state_path(4553))
            for label, body in (
                ("deeply nested", "[" * 30000 + "]" * 30000),
                ("truncated", '{"pid": 1'),
                ("not an object", "[1, 2, 3]"),
                ("empty", ""),
                ("oversized", "0" * (dashboard.STATE_READ_CAP_BYTES + 1024)),
                (
                    "oversized valid object",
                    '{"pid": 1}' + " " * dashboard.STATE_READ_CAP_BYTES,
                ),
                (
                    "oversized UTF-8 object",
                    json.dumps(
                        {"note": "é" * 40000},
                        ensure_ascii=False,
                    ),
                ),
            ):
                with self.subTest(body=label):
                    path.write_text(body, encoding="utf-8")
                    self.assertIsNone(dashboard.read_state(4553))
                    # And the commands built on it still explain themselves.
                    with mock.patch.object(dashboard, "probe_port", return_value=("closed", None)):
                        self.assertIn(
                            "not running", dashboard.render_status(dashboard.instance_status(4553))
                        )

    def test_daemon_explains_a_log_it_cannot_open(self) -> None:
        # ensure_cargento_home() is makedirs(exist_ok=True), which succeeds for
        # an existing directory whatever its mode — so the likeliest bad home of
        # all, one that exists and is not writable, got past that guard and
        # raised in daemon_redirect_stdio after the fork, where no message can
        # reach the terminal that asked.
        if os.name == "nt":
            self.skipTest("POSIX directory modes do not apply on Windows")
        with tempfile.TemporaryDirectory() as tmp:
            home = os.path.join(tmp, "readonly")
            os.makedirs(home)
            os.chmod(home, 0o500)
            try:
                with (
                    mock.patch.dict(os.environ, {"CARGENTO_HOME": home}),
                    mock.patch.object(sys, "argv", ["server.py", "--port", "4553", "--daemon"]),
                    mock.patch.object(dashboard, "diag") as diag,
                    mock.patch.object(dashboard, "LoopbackHTTPServer") as bind,
                    mock.patch.object(dashboard, "fork_daemon") as fork,
                    mock.patch.object(dashboard, "spawn_detached") as spawn,
                    self.assertRaises(SystemExit) as caught,
                ):
                    dashboard.main()
            finally:
                # Restore before TemporaryDirectory tries to remove it, and
                # before this frame can leave a 0o500 directory behind.
                os.chmod(home, 0o700)
        self.assertEqual(1, caught.exception.code)
        bind.assert_not_called()
        fork.assert_not_called()
        spawn.assert_not_called()
        said = " ".join(str(call.args[0]) for call in diag.call_args_list)
        self.assertIn("CARGENTO_HOME", said)
        self.assertIn(home, said)

    def test_stop_instance_refuses_to_touch_a_port_owned_by_something_else(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.dict(os.environ, {"CARGENTO_HOME": tmp}),
        ):
            dashboard.write_state(4553)
            with mock.patch.object(dashboard, "probe_port", return_value=("foreign", None)):
                message, code = dashboard.stop_instance(4553)
            self.assertEqual(1, code)
            self.assertIn("another process", message)
            # The state file is evidence, not garbage: leave it alone.
            self.assertIsNotNone(dashboard.read_state(4553))

    def test_stop_instance_is_idempotent_when_nothing_is_running(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.dict(os.environ, {"CARGENTO_HOME": tmp}),
            mock.patch.object(dashboard, "probe_port", return_value=("closed", None)),
            mock.patch.object(dashboard, "port_released", return_value=True),
        ):
            message, code = dashboard.stop_instance(4553)
        self.assertEqual(0, code)
        self.assertIn("nothing running", message)

    def test_stop_flag_exits_with_the_code_stop_instance_returned(self) -> None:
        with (
            mock.patch.object(dashboard, "stop_instance", return_value=("nope", 1)) as stop,
            mock.patch.object(sys, "argv", ["server.py", "--port", "4553", "--stop"]),
            mock.patch.object(dashboard, "diag") as diag,
            self.assertRaises(SystemExit) as caught,
        ):
            dashboard.main()
        self.assertEqual(1, caught.exception.code)
        stop.assert_called_once_with(4553)
        diag.assert_called_once_with("nope")

    def test_fork_daemon_returns_parent_role_without_touching_setsid(self) -> None:
        calls: list[str] = []

        def fake_fork() -> int:
            calls.append("fork")
            return 4242  # a pid: this process is the original

        def fake_setsid() -> int:
            calls.append("setsid")
            return 0

        role, fd = dashboard.fork_daemon(fork=fake_fork, setsid=fake_setsid)
        os.close(fd)
        self.assertEqual("parent", role)
        self.assertEqual(["fork"], calls)

    def test_fork_daemon_double_forks_and_sessions_the_daemon(self) -> None:
        calls: list[str] = []
        exited: list[int] = []

        def fake_fork() -> int:
            calls.append("fork")
            return 0  # child both times: this process becomes the daemon

        def fake_setsid() -> int:
            calls.append("setsid")
            return 0

        role, fd = dashboard.fork_daemon(
            fork=fake_fork, setsid=fake_setsid, exit_intermediate=exited.append
        )
        os.close(fd)
        self.assertEqual("daemon", role)
        # setsid between the two forks: the second fork is what guarantees the
        # daemon is not a session leader and can never acquire a terminal.
        self.assertEqual(["fork", "setsid", "fork"], calls)
        self.assertEqual([], exited)

    def test_fork_daemon_exits_the_intermediate_child(self) -> None:
        forks = iter([0, 9999])  # child, then parent-of-grandchild
        exited: list[int] = []
        role, fd = dashboard.fork_daemon(
            fork=lambda: next(forks),
            setsid=lambda: 0,
            exit_intermediate=exited.append,
        )
        os.close(fd)
        # The intermediate's only job was setsid. In production os._exit never
        # returns; the injected stub does, so the role is reported for the test.
        self.assertEqual([0], exited)
        self.assertEqual("daemon", role)

    # await_daemon is POSIX-only by construction: it waits on the pipe with
    # select(), which on Windows accepts sockets and nothing else, so a pipe fd
    # raises there. main() never reaches it on Windows — that platform takes the
    # re-spawn path and await_spawned — so the function is unreachable rather
    # than broken. Skipped rather than rewritten rather than pretending: without
    # the skip the second of these two passed on Windows for the wrong reason,
    # because select() raising produced the same exit code it asserts.
    @unittest.skipIf(os.name == "nt", "select() cannot watch a pipe on Windows; POSIX-only path")
    def test_await_daemon_reports_the_pid_the_daemon_announced(self) -> None:
        read_fd, write_fd = os.pipe()
        try:
            os.write(write_fd, b"31337\n")
        finally:
            os.close(write_fd)
        message, code = dashboard.await_daemon(read_fd, 4553, "/tmp/c.log", timeout=2)
        self.assertEqual(0, code)
        self.assertIn("pid 31337", message)
        self.assertIn("http://127.0.0.1:4553/", message)
        self.assertIn("/tmp/c.log", message)

    @unittest.skipIf(os.name == "nt", "select() cannot watch a pipe on Windows; POSIX-only path")
    def test_await_daemon_reports_failure_when_the_daemon_says_nothing(self) -> None:
        read_fd, write_fd = os.pipe()
        os.close(write_fd)  # daemon died before announcing
        message, code = dashboard.await_daemon(read_fd, 4553, "/tmp/c.log", timeout=1)
        self.assertEqual(1, code)
        self.assertIn("/tmp/c.log", message)

    @unittest.skipIf(os.name == "nt", "select() cannot watch a pipe on Windows; POSIX-only path")
    def test_await_daemon_does_not_report_a_pipe_error_as_a_timeout(self) -> None:
        read_fd, write_fd = os.pipe()
        os.close(write_fd)
        with mock.patch.object(
            dashboard.select,
            "select",
            side_effect=OSError(errno.EBADF, os.strerror(errno.EBADF)),
        ):
            message, code = dashboard.await_daemon(read_fd, 4553, "/tmp/c.log", timeout=10)
        self.assertEqual(1, code)
        self.assertIn("readiness pipe", message)
        self.assertIn("/tmp/c.log", message)
        self.assertNotIn("within 10s", message)

    def test_daemon_rejects_the_flags_it_cannot_combine_with(self) -> None:
        for other in ("--diagnose", "--stop", "--status"):
            with (
                mock.patch.object(sys, "argv", ["server.py", "--daemon", other]),
                self.assertRaises(SystemExit) as caught,
                contextlib.redirect_stderr(io.StringIO()),
            ):
                dashboard.main()
            self.assertEqual(2, caught.exception.code, other)

    def test_daemon_explains_a_home_it_cannot_create_instead_of_tracebacking(self) -> None:
        # CARGENTO_HOME is user-facing in README, SKILL.md, SECURITY.md and
        # COMPATIBILITY.md, so pointing it somewhere unusable is an ordinary
        # mistake. write_state() already degrades for a foreground run; without
        # this guard only --daemon crashed, and with a raw traceback.
        with tempfile.TemporaryDirectory() as tmp:
            not_a_dir = os.path.join(tmp, "occupied")
            Path(not_a_dir).write_text("", encoding="utf-8")
            with (
                mock.patch.dict(os.environ, {"CARGENTO_HOME": not_a_dir}),
                mock.patch.object(sys, "argv", ["server.py", "--port", "4553", "--daemon"]),
                mock.patch.object(dashboard, "diag") as diag,
                # A traceback here would escape before either of these is used.
                mock.patch.object(dashboard, "LoopbackHTTPServer") as bind,
                mock.patch.object(dashboard, "fork_daemon") as fork,
                self.assertRaises(SystemExit) as caught,
            ):
                dashboard.main()
        self.assertEqual(1, caught.exception.code)
        bind.assert_not_called()
        fork.assert_not_called()
        said = " ".join(str(call.args[0]) for call in diag.call_args_list)
        self.assertIn("CARGENTO_HOME", said)
        self.assertIn("--daemon", said)
        self.assertIn(not_a_dir, said)

    def test_forwarded_args_carries_the_flags_the_child_needs_and_drops_daemon(self) -> None:
        args = argparse.Namespace(port=4553, window_hours=12.0, no_spacedock=True, daemon=True)
        forwarded = dashboard.forwarded_args(args)
        self.assertEqual(["--port", "4553", "--window-hours", "12.0", "--no-spacedock"], forwarded)
        # --daemon must not be forwarded: the child is an ordinary foreground
        # run that happens to own no console. Forwarding it would re-spawn
        # forever.
        self.assertNotIn("--daemon", forwarded)
        plain = dashboard.forwarded_args(
            argparse.Namespace(port=1, window_hours=24.0, no_spacedock=False, daemon=True)
        )
        self.assertEqual(["--port", "1", "--window-hours", "24.0"], plain)

    def test_spawn_detached_uses_a_fixed_argv_and_detaching_flags(self) -> None:
        args = argparse.Namespace(port=4553, window_hours=24.0, no_spacedock=False, daemon=True)
        with tempfile.TemporaryDirectory() as tmp:
            log_file = os.path.join(tmp, "c.log")
            with mock.patch.object(dashboard.subprocess, "Popen") as popen:
                popen.return_value = mock.Mock(pid=321)
                dashboard.spawn_detached(args, log_file)
        argv = popen.call_args.args[0]
        self.assertEqual(sys.executable, argv[0])
        self.assertTrue(argv[1].endswith("server.py"))
        self.assertEqual(["--port", "4553", "--window-hours", "24.0"], argv[2:])
        self.assertEqual(dashboard.subprocess.DEVNULL, popen.call_args.kwargs["stdin"])
        self.assertTrue(popen.call_args.kwargs["close_fds"])
        # 0 on POSIX, where these creationflags do not exist; the call must
        # still be well-formed so the test runs everywhere.
        self.assertIsInstance(popen.call_args.kwargs["creationflags"], int)

    def test_await_spawned_reports_the_child_that_answered(self) -> None:
        health = {"ok": True, "pid": 777, "port": 4553, "started": 1.0}
        proc = mock.Mock(returncode=None, pid=777)
        proc.poll.return_value = None
        with mock.patch.object(dashboard, "probe_port", return_value=("cargento", health)):
            message, code = dashboard.await_spawned(proc, 4553, "/tmp/c.log", timeout=2)
        self.assertEqual(0, code)
        self.assertIn("pid 777", message)
        self.assertIn("http://127.0.0.1:4553/", message)

    def test_await_spawned_does_not_mistake_another_cargento_for_its_own_child(self) -> None:
        # The Windows failure this exists to prevent: the child loses the bind
        # to a dashboard already on that port, and the parent's readiness poll
        # gets a perfectly valid /api/health answer — from the *other*
        # instance. Reporting success there tells the user their daemon
        # started when it did not, and hands back a pid they do not own.
        health = {"ok": True, "pid": 999, "port": 4553, "started": 1.0}
        with tempfile.TemporaryDirectory() as tmp:
            log_file = os.path.join(tmp, "c.log")
            Path(log_file).write_text("Cargento: port 4553 is already in use.", encoding="utf-8")
            proc = mock.Mock(returncode=1, pid=777)
            proc.poll.return_value = 1
            with mock.patch.object(dashboard, "probe_port", return_value=("cargento", health)):
                message, code = dashboard.await_spawned(proc, 4553, log_file, timeout=2)
        self.assertEqual(1, code)
        self.assertNotIn("pid 999", message)
        self.assertIn("already in use", message)

    def test_await_spawned_keeps_waiting_while_a_foreign_answer_and_a_live_child(self) -> None:
        # Same mismatch, but the child is still running: the answer is not
        # evidence about our child either way, so this must time out rather
        # than claim success.
        health = {"ok": True, "pid": 999, "port": 4553, "started": 1.0}
        proc = mock.Mock(returncode=None, pid=777)
        proc.poll.return_value = None
        with mock.patch.object(dashboard, "probe_port", return_value=("cargento", health)):
            message, code = dashboard.await_spawned(proc, 4553, "/tmp/c.log", timeout=0.3)
        self.assertEqual(1, code)
        self.assertNotIn("pid 999", message)

    def test_await_spawned_surfaces_the_log_when_the_child_exits_at_once(self) -> None:
        # This is the case that keeps D-1's promise on Windows: the parent
        # cannot see the child's failed bind, so it shows the child's log.
        with tempfile.TemporaryDirectory() as tmp:
            log_file = os.path.join(tmp, "c.log")
            Path(log_file).write_text("Cargento: port 4553 is already in use.", encoding="utf-8")
            proc = mock.Mock(returncode=1)
            proc.poll.return_value = 1
            with mock.patch.object(dashboard, "probe_port", return_value=("closed", None)):
                message, code = dashboard.await_spawned(proc, 4553, log_file, timeout=2)
        self.assertEqual(1, code)
        self.assertIn("already in use", message)

    def test_await_spawned_gives_up_after_the_timeout(self) -> None:
        proc = mock.Mock(returncode=None)
        proc.poll.return_value = None
        with mock.patch.object(dashboard, "probe_port", return_value=("closed", None)):
            message, code = dashboard.await_spawned(proc, 4553, "/tmp/c.log", timeout=0.3)
        self.assertEqual(1, code)
        self.assertIn("/tmp/c.log", message)

    def test_log_tail_reads_the_end_and_never_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_file = os.path.join(tmp, "c.log")
            Path(log_file).write_bytes(b"x" * 3000 + b"LAST LINE")
            tail = dashboard.log_tail(log_file, limit=200)
            self.assertIn("LAST LINE", tail)
            self.assertLessEqual(len(tail), 200)
            self.assertIn("could not read", dashboard.log_tail(os.path.join(tmp, "nope.log")))
            Path(log_file).write_bytes(b"")
            self.assertIn("empty", dashboard.log_tail(log_file))


class ReviewFixTest(unittest.TestCase):
    """Regressions found by the adversarial review passes on PR #7."""

    NOW = 1_700_000_000.0


class VerificationFixTest(unittest.TestCase):
    """Regressions found by the adversarial pass that tried to refute the fixes."""

    NOW = 1_700_000_000.0
    FUTURE = NOW + 86_400


class GlobUnderTest(unittest.TestCase):
    # A legal directory name on every supported platform — deliberately not
    # using "*" or "?", which Windows forbids in filenames. Interpolated into a
    # glob pattern, "[...]" is a character class that matches nothing, so
    # discovery returned zero sessions with no error at all.
    HOSTILE = "A [Contractor]"


# ---------------------------------------------------------------------------
# Behavioural contract suite.
#
# Written from expectation rather than derived from a bug: for every harness,
# state what the dashboard must do, then assert it. These run natively on each
# CI runner, so the same contract is checked against real macOS, Linux and
# Windows filesystem semantics.


class CalmModeTest(PageJsHarness):
    """The calm display mode and the switch between it and the regular view.

    Calm mode renders the same ``/api/data`` payload as a dense ledger. These
    execute the page's real JS: every assertion is about what the page does
    with a payload, not about the text of ``PAGE``.
    """

    # Globals the page reads at load (localStorage) or feature-detects
    # (navigator.clipboard), plus a hand-fired setTimeout so the transient
    # "copied" label clears deterministically instead of after a real 1.4s.
    @staticmethod
    def prelude(saved: str | None = None, *, clipboard: str = "none") -> str:
        seed = "{}" if saved is None else json.dumps({"cargento.displayMode": saved})
        clip = {
            "none": "const navigator = {};",
            "ok": (
                "let __wrote = [];\nconst navigator = {clipboard: {writeText(s){"
                " __wrote.push(s); return Promise.resolve(); }}};"
            ),
            "denied": (
                "const navigator = {clipboard: {writeText(){"
                ' return Promise.reject(new Error("denied")); }}};'
            ),
        }[clipboard]
        return f"""
let __store = {seed};
const localStorage = {{
  getItem(k){{ return Object.prototype.hasOwnProperty.call(__store, k) ? __store[k] : null; }},
  setItem(k, v){{ __store[k] = String(v); }}
}};
{clip}
let __timers = [];
const setTimeout = fn => {{ __timers.push(fn); return __timers.length; }};
const __tick = () => {{ const t = __timers; __timers = []; t.forEach(f => f()); }};
"""

    # A payload builder shared by the checks below. `mk` fills in every field
    # base_session() ships so a test only states what it is exercising.
    FIXTURE = """
let __focused = null;
// Every [data-calm] control in the rendered markup, as something that answers
// getAttribute() and focus() the way a real element would.
const __controls = () => [...__els.app.innerHTML.matchAll(
    /data-calm="([^"]*)"(?: data-arg="([^"]*)")?/g)].map(m => ({
  getAttribute: a => a === "data-calm" ? m[1]
    : (a === "data-arg" ? (m[2] === undefined ? null : m[2]) : null),
  focus(){ __focused = m[1] + ":" + (m[2] === undefined ? "" : m[2]); }
}));
__els.app = {innerHTML: "", className: "", querySelectorAll: () => __controls()};
let __scrollTop = 0;
let __revealed = 0;
// Selector-aware on purpose: a stub that answers every selector makes
// "the cursor was scrolled into view" pass even when the page asked for the
// wrong element, or for nothing at all.
__els["cm-body"] = {
  get scrollTop(){ return __scrollTop; }, set scrollTop(v){ __scrollTop = v; },
  querySelector(sel){
    if(sel !== ".cm-row.focus") return null;
    if(!__els.app.innerHTML.includes('class="cm-row focus')) return null;
    return {scrollIntoView(){ __revealed++; }};
  }
};
const mk = o => Object.assign({
  harness: "claude", session: "1234abcd", sid: "1234abcd", project: "repo/proj",
  title: null, last_prompt: "", state: "idle", state_detail: "awaiting your message",
  active: false, last_activity: 99000, rate_per_min: 0, total: 0, done: 0, open: 0,
  progress_pct: 0, eta_h: null, turn: null, subagents: [], tasks: [], spacedock: null
}, o);
const payload = sessions => ({
  generated: 100000, window_hours: 24, show_all: false, native_notify: "osascript",
  harnesses: [{key: "claude", label: "Claude Code", discovered: true, error: null},
              {key: "codex", label: "Codex", discovered: false, error: null}],
  summary: {needs_input: 1, working: 1, rate_per_min: 1234, active_sessions: 2,
            open_tasks: 1, progress_pct: 50, total_tasks: 2, total_done: 1},
  sessions
});
const blocked = mk({sid: "aaa1", session: "aaa1", title: "Approve deploy?",
  state: "needs_input", active: true, last_activity: 99700, blocked_since: 99700,
  state_detail: "open question (AskUserQuestion), waiting 5m"});
const busy = mk({sid: "bbb2", session: "bbb2", harness: "codex", project: "repo/other",
  title: "Migrate warehouse sync", state: "working", active: true,
  state_detail: "running Bash", last_activity: 99990, rate_per_min: 2010,
  turn: {elapsed_h: "20m", eta_h: "39m", pct: 34, long: true},
  subagents: ["Final whole-branch review"], last_prompt: "migrate the sync",
  tasks: [{status: "completed", subject: "Map every call site", activeForm: null},
          {status: "in_progress", subject: "Convert chain", activeForm: "Converting chain"},
          {status: "pending", subject: "Re-run suite", activeForm: null}]});
const quiet = mk({sid: "ccc3", session: "ccc3", title: "Old thing", last_activity: 90000});
const board = () => payload([blocked, busy, quiet]);
const rows = () => (__els.app.innerHTML.match(/class="cm-row/g) || []).length;
// A row is identified by (harness, sid) — the same pair sessKey() builds.
const K = (harness, sid) => harness + ":" + sid;
"""

    def run_calm(self, checks: str, *, saved: str = "calm", clipboard: str = "none") -> Any:
        return self._run_page_js(
            self.FIXTURE + checks, prelude=self.prelude(saved, clipboard=clipboard)
        )

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_display_switch_persists_and_is_bound_to_c_in_both_modes(self) -> None:
        checks = """
const out = {};
out.startedCalm = displayMode;                    // seeded from localStorage
render(board());
out.calmClass = __els.app.className;
out.calmFrame = __els.app.innerHTML.includes("cm-frame");
out.switchShown = __els.app.innerHTML.includes('data-calm="mode" data-arg="calm"' +
  ' aria-pressed="true"');

// `c` leaves calm, and the switch is still there to come back with.
__fire("keydown", {key: "c", target: {}, preventDefault(){}});
out.afterKey = displayMode;
out.stored = __store["cargento.displayMode"];
out.regularClass = __els.app.className;
out.regularKeepsSwitch = __els.app.innerHTML.includes('class="modebar"');
out.regularKeepsTiles = __els.app.innerHTML.includes('class="tile"');
out.noFrameInRegular = !__els.app.innerHTML.includes("cm-frame");

// ...and back again, this time by clicking the segment.
calmAction("mode", "calm");
out.clickedBack = displayMode;
out.storedBack = __store["cargento.displayMode"];

// A value neither mode is ignored rather than blanking the page.
calmAction("mode", "sideways");
out.rejectsJunk = displayMode;
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertEqual("calm", out["startedCalm"], "saved mode not honoured on load")
        self.assertEqual("wrap calm", out["calmClass"])
        self.assertTrue(out["calmFrame"])
        self.assertTrue(out["switchShown"])
        self.assertEqual("regular", out["afterKey"], "`c` did not leave calm mode")
        self.assertEqual("regular", out["stored"], "the switch was not persisted")
        self.assertEqual("wrap", out["regularClass"])
        self.assertTrue(out["regularKeepsSwitch"], "no way back to calm from regular")
        self.assertTrue(out["regularKeepsTiles"], "regular mode lost its hero tiles")
        self.assertTrue(out["noFrameInRegular"])
        self.assertEqual("calm", out["clickedBack"])
        self.assertEqual("calm", out["storedBack"])
        self.assertEqual("calm", out["rejectsJunk"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_page_still_loads_when_storage_is_unavailable(self) -> None:
        # Private browsing and sandboxed contexts throw on localStorage access.
        checks = """
__els.app = {innerHTML: "", className: ""};
const d = {generated: 1000, window_hours: 24, show_all: false, native_notify: "",
  harnesses: [], sessions: [],
  summary: {needs_input: 0, working: 0, rate_per_min: 0, active_sessions: 0,
            open_tasks: 0, progress_pct: 0, total_tasks: 0, total_done: 0}};
render(d);
setDisplayMode("calm");
console.log(JSON.stringify({
  mode: displayMode, rendered: __els.app.innerHTML.includes("cm-frame")}));
"""
        # No prelude at all: neither localStorage nor navigator exists.
        out = self._run_page_js(checks)
        self.assertEqual("calm", out["mode"], "storage failure blocked the switch")
        self.assertTrue(out["rendered"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_ledger_lists_every_session_exactly_once(self) -> None:
        # A ledger that silently drops a session is worse than no ledger.
        checks = """
const out = {};
render(board());
const h = __els.app.innerHTML;
out.rows = rows();
out.perSession = [K("claude", "aaa1"), K("codex", "bbb2"), K("claude", "ccc3")]
  .map(k => (h.match(new RegExp('data-arg="' + k + '"', "g")) || []).length);
out.note = h.includes("showing all 3");
out.footer = h.includes("3 sessions · 1 harnesses · 1,234 tok/min");
out.legend = [h.includes("1 needs you"), h.includes("1 working"), h.includes("1 idle")];
// Column values come straight from the payload.
out.doing = h.includes("open question (AskUserQuestion), waiting 5m");
// Only the project may be truncated; the session id identifies the row.
out.where = h.includes('class="cm-proj">repo/other</span><span class="cm-sess">· bbb2<');
out.metrics = ["5m wait", "2,010 /m", "2h 46m idle"].map(m => h.includes(m));
// Signal bar only for a working session with a turn percentage.
out.bars = (h.match(/class="cm-track"/g) || []).length;
out.barWidth = h.includes("width:34%");
// An unrecognised state is still a row, in the idle bucket.
render(payload([mk({sid: "z", session: "z", state: "banana"})]));
out.unknownState = rows();
out.unknownIdle = __els.app.innerHTML.includes("1 idle");
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertEqual(3, out["rows"])
        # Each row carries its sid twice: the row itself and its `copy id` button.
        self.assertEqual([2, 2, 2], out["perSession"])
        self.assertTrue(out["note"])
        self.assertTrue(out["footer"], "footer counts disagree with the payload")
        self.assertEqual([True, True, True], out["legend"])
        self.assertTrue(out["doing"])
        self.assertTrue(out["where"])
        self.assertEqual([True, True, True], out["metrics"])
        self.assertEqual(1, out["bars"], "only a working turn should draw a signal bar")
        self.assertTrue(out["barWidth"])
        self.assertEqual(1, out["unknownState"], "a state the page does not know dropped a row")
        self.assertTrue(out["unknownIdle"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_flags_use_only_signals_the_payload_carries(self) -> None:
        # The design fixture also flagged "stalled" and "failed". The server has
        # no detector for either, so calm mode must not invent them.
        checks = """
const out = {};
render(board());
calmAction("open", "claude:aaa1");
calmAction("open", "codex:bbb2");
calmAction("open", "claude:ccc3");
const each = k => { calmAction("open", k); const h = __els.app.innerHTML;
  calmAction("open", k); return h; };
const hb = each(K("claude", "aaa1")), hw = each(K("codex", "bbb2")),
      hq = each(K("claude", "ccc3"));
out.blockedFlag = hb.includes(">your call<");
out.blockedWhy = hb.includes("Blocked on you for 5m");
out.longFlag = hw.includes(">long turn<");
out.longWhy = hw.includes("This request is running long (or estimated to).");
out.staleFlag = hq.includes(">stale<");
out.staleWhy = hq.includes("No activity for 2h 46m");
out.noInvented = !/&gt;stalled&lt;|>stalled<|>failed</.test(hb + hw + hq);
// A working session inside the long-turn threshold carries no flag.
render(payload([mk({sid: "s", session: "s", state: "working", active: true,
  last_activity: 99999, turn: {elapsed_h: "2m", eta_h: "3m", pct: 40, long: false}})]));
out.shortTurnUnflagged = !__els.app.innerHTML.includes('class="cm-flag"');
out.flagChipZero = __els.app.innerHTML.includes("◆ 0 flagged");
// An idle session inside the stale threshold carries no flag either.
render(payload([mk({sid: "t", session: "t", last_activity: 99000})]));
out.freshIdleUnflagged = !__els.app.innerHTML.includes('class="cm-flag"');
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["blockedFlag"])
        self.assertTrue(out["blockedWhy"])
        self.assertTrue(out["longFlag"])
        self.assertTrue(out["longWhy"], "calm mode reworded the long-turn signal")
        self.assertTrue(out["staleFlag"])
        self.assertTrue(out["staleWhy"])
        self.assertTrue(out["noInvented"], "flagged a signal the payload cannot support")
        self.assertTrue(out["shortTurnUnflagged"])
        self.assertTrue(out["flagChipZero"])
        self.assertTrue(out["freshIdleUnflagged"])

    def test_the_long_turn_wording_has_exactly_one_source(self) -> None:
        # The ⚠️ tooltip and the calm flag explanation are the same sentence;
        # two copies is how they drift apart.
        self.assertIn("const LONG_TURN_NOTE =", dashboard.PAGE)
        self.assertEqual(
            1,
            dashboard.PAGE.count("This request is running long (or estimated to)."),
            "the long-turn sentence is duplicated instead of shared",
        )

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_filters_and_orderings_agree_with_the_counts_they_advertise(self) -> None:
        checks = """
const out = {};
render(board());
// Attention order puts the blocker first, then the warning, then the quiet row.
const order = h => [...h.matchAll(/data-arg="[a-z]+:(aaa1|bbb2|ccc3)" role="button"/g)]
  .map(m => m[1]);
out.attention = order(__els.app.innerHTML);
calmAction("sort", "recent");
out.recent = order(__els.app.innerHTML);
out.recentPressed = __els.app.innerHTML.includes('data-arg="recent" aria-pressed="true"');
calmAction("sort", "repo");
out.repoDividers = (__els.app.innerHTML.match(/class="cm-div"/g) || []).length;
out.repoLabels = ["repo/other", "repo/proj"].map(p =>
  __els.app.innerHTML.indexOf('cm-div-k">' + p));
out.repoRows = rows();
calmAction("sort", "attention");

// A legend chip filters to its own bucket and reports the narrowing.
calmAction("open", "codex:bbb2");
calmCursorKey = "codex:bbb2";
calmAction("state", "needs");
out.filterResetsRow = [calmOpenKey, calmCursorKey];
out.needsOnly = [rows(), __els.app.innerHTML.includes("showing 1 of 3")];
out.clearOffered = __els.app.innerHTML.includes('data-calm="clear"');
calmAction("state", "needs");
out.chipIsAToggle = [calmStateOnly, rows()];

// The flagged chip narrows to flagged rows; every board row is flagged here.
calmAction("open", "codex:bbb2");
calmAction("flag", null);
out.flagFilterResetsRow = [calmOpenKey, calmCursorKey];
out.flagged = [calmFlagOnly, rows()];
calmAction("clear", null);
out.cleared = [calmFlagOnly, calmStateOnly, rows()];

// A filter that matches nothing offers its own way out.
render(payload([busy]));
calmAction("state", "idle");
const empty = __els.app.innerHTML;
out.emptyState = empty.includes("Nothing matches this filter")
  && empty.includes("Show all 1");
out.emptyHasNoRows = rows();
calmAction("clear", null);
out.recovered = rows();

// No sessions at all is a different message, with the window and the escape.
render(payload([]));
out.noData = __els.app.innerHTML.includes("No session activity in the last 24h")
  && __els.app.innerHTML.includes('href="?all=1"');
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertEqual(["aaa1", "bbb2", "ccc3"], out["attention"])
        self.assertEqual(["bbb2", "aaa1", "ccc3"], out["recent"], "recent order is not by age")
        self.assertTrue(out["recentPressed"])
        self.assertEqual(2, out["repoDividers"])
        self.assertLess(out["repoLabels"][0], out["repoLabels"][1], "repo groups not sorted")
        self.assertEqual(3, out["repoRows"], "grouping lost a row")
        self.assertEqual([None, None], out["filterResetsRow"], "a filter left a row expanded")
        self.assertEqual([None, None], out["flagFilterResetsRow"])
        self.assertEqual([1, True], out["needsOnly"])
        self.assertTrue(out["clearOffered"])
        self.assertEqual([None, 3], out["chipIsAToggle"])
        self.assertEqual([True, 3], out["flagged"])
        self.assertEqual([False, None, 3], out["cleared"])
        self.assertTrue(out["emptyState"])
        self.assertEqual(0, out["emptyHasNoRows"])
        self.assertEqual(1, out["recovered"])
        self.assertTrue(out["noData"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_row_order_does_not_churn_between_polls(self) -> None:
        # A row that swaps places under the cursor is worse than a row in the
        # wrong place. Every ordering has to be a function of things that do not
        # change while the reader is reading: collect() makes the same call.
        checks = """
const out = {};
// Eight sessions with ages spread across minute boundaries, plus three that
// are actively generating (their last_activity advances with every poll).
const many = [];
for(let i = 0; i < 8; i++){
  many.push(mk({sid: "idle-" + i, session: "idle-" + i,
    project: "repo/p" + (i % 3), last_activity: 100000 - 59 - i * 61}));
}
for(let i = 0; i < 3; i++){
  many.push(mk({sid: "work-" + i, session: "work-" + i, state: "working",
    active: true, project: "repo/p" + (i % 3), last_activity: 99990 + i,
    rate_per_min: 100 * i}));
}
// What a real poll looks like: a generating session wrote at some arbitrary
// moment since the last poll, so its age jitters; and collect() re-sorts the
// array server-side, so the client may not lean on the payload's own order.
const LAG = [[1, 4, 2], [3, 1, 4], [0, 3, 1], [4, 2, 3], [2, 0, 4], [1, 3, 0], [3, 4, 1]];
const at = (t, k) => {
  const lag = LAG[k % LAG.length];
  const sessions = many.map(s => s.state === "working"
    ? {...s, last_activity: t - lag[Number(s.sid.slice(-1))]} : s);
  // Reverse on alternate polls: payload order must not decide row order.
  return {...payload(k % 2 ? sessions.slice().reverse() : sessions), generated: t};
};
const snap = () => [...__els.app.innerHTML.matchAll(
    /data-arg="[a-z]+:([a-z]+-\\d)" role/g)].map(m => m[1]);

for(const sort of ["attention", "recent", "repo"]){
  calmAction("sort", sort);
  render(at(100000, 0));
  const first = snap();
  // Six more polls, five seconds apart: enough for several rows to tick over a
  // whole minute and for every working row to have written again.
  const same = [];
  for(let k = 1; k <= 6; k++){
    render(at(100000 + k * 5, k));
    same.push(snap().join() === first.join());
  }
  out[sort] = {rows: first.length, stable: same.every(Boolean), order: first};
}
// A session that genuinely goes quiet is allowed — and expected — to move.
calmAction("sort", "attention");
render(at(100000, 0));
const before = snap();
const next = at(100010, 2);
render({...next, sessions: next.sessions.map(s =>
  s.sid === "work-1" ? {...s, state: "idle", active: false, last_activity: 90000} : s)});
out.realChangeMoves = snap().join() !== before.join();
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        for sort in ("attention", "recent", "repo"):
            with self.subTest(sort=sort):
                self.assertEqual(11, out[sort]["rows"], "a row went missing")
                self.assertTrue(
                    out[sort]["stable"],
                    f"{sort} order churned between polls: {out[sort]['order']}",
                )
        # Working rows sort ahead of idle ones under both attention and recent.
        self.assertEqual(
            ["work-0", "work-1", "work-2"], out["attention"]["order"][:3], "working rows not first"
        )
        self.assertEqual(["work-0", "work-1", "work-2"], out["recent"]["order"][:3])
        # Idle rows stay in most-recent-first order.
        self.assertEqual(["idle-0", "idle-1", "idle-2", "idle-3"], out["attention"]["order"][3:7])
        self.assertTrue(out["realChangeMoves"], "a session that changed state did not move")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_an_expanded_row_shows_what_the_regular_card_shows(self) -> None:
        checks = """
const out = {};
const sd = {role: "first-officer", workflows: [{workflow: "wf", stages: ["a", "b"],
  entities: [{slug: "ent", stage: "b", live: true, cycle: "c1"}]}]};
render(payload([Object.assign({}, busy, {spacedock: sd})]));
out.collapsedFirst = !__els.app.innerHTML.includes("cm-exp");
calmAction("open", "codex:bbb2");
const h = __els.app.innerHTML;
out.expanded = h.includes("cm-exp");
out.caret = h.includes('class="cm-caret">–<');
out.ariaExpanded = h.includes('aria-expanded="true"');
out.turn = h.includes("20m elapsed · ~39m left (est)") && h.includes("34%");
out.subagent = h.includes("Final whole-branch review");
out.prompt = h.includes("migrate the sync");
// Tasks: in-progress first and shown by its activeForm, completed last.
out.taskNote = h.includes("tasks · 1 of 3 done");
out.taskOrder = ["Converting chain…", "Re-run suite", "Map every call site"]
  .map(t => h.indexOf(t));
out.spacedock = h.includes("spacedock wf") && h.includes("first officer");
out.meta = h.includes("session bbb2") && h.includes("Claude");
// Collapsing again, and only one row open at a time.
calmAction("open", "codex:bbb2");
out.collapsed = !__els.app.innerHTML.includes("cm-exp");
render(board());
calmAction("open", "claude:aaa1");
calmAction("open", "codex:bbb2");
out.onlyOneOpen = (__els.app.innerHTML.match(/class="cm-exp"/g) || []).length;
// A turn with no percentage draws no bar and says so in words.
render(payload([mk({sid: "n", session: "n", state: "working", active: true,
  last_activity: 99999, turn: {elapsed_h: "9m", eta_h: null, pct: null, long: false}})]));
calmAction("open", "claude:n");
out.noPct = !__els.app.innerHTML.includes("cm-turn-pct")
  && __els.app.innerHTML.includes("9m elapsed · running longer than recent turns");
// A session with nothing extra expands to just its identity line.
render(payload([quiet]));
calmAction("open", "claude:ccc3");
const bare = __els.app.innerHTML;
out.bare = [bare.includes("cm-exp"), bare.includes("cm-tasks"),
            bare.includes("cm-subs"), bare.includes("session ccc3")];
// The title doubles as the prompt here, so it is not quoted twice.
out.noEchoedPrompt = !bare.includes("cm-quote");
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["collapsedFirst"], "rows should start collapsed")
        self.assertTrue(out["expanded"])
        self.assertTrue(out["caret"])
        self.assertTrue(out["ariaExpanded"])
        self.assertTrue(out["turn"])
        self.assertTrue(out["subagent"])
        self.assertTrue(out["prompt"])
        self.assertTrue(out["taskNote"])
        self.assertEqual(sorted(out["taskOrder"]), out["taskOrder"], "task order is wrong")
        self.assertNotIn(-1, out["taskOrder"])
        self.assertTrue(out["spacedock"], "the Spacedock strip is missing from calm mode")
        self.assertTrue(out["meta"])
        self.assertTrue(out["collapsed"])
        self.assertEqual(1, out["onlyOneOpen"])
        self.assertTrue(out["noPct"])
        self.assertEqual([True, False, False, True], out["bare"])
        self.assertTrue(out["noEchoedPrompt"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_hostile_session_text_cannot_reach_the_dom_as_markup(self) -> None:
        # Titles, prompts, task subjects and subagent names all come from files
        # a project can write. Calm mode builds HTML strings, so every one of
        # them has to go through esc().
        checks = """
const bad = '<img src=x onerror=alert(1)>"><b>';
render(payload([mk({sid: bad, session: bad, project: bad, title: bad,
  state: "working", active: true, state_detail: bad, last_prompt: "p " + bad,
  last_activity: 99999, subagents: [bad], harness: bad,
  turn: {elapsed_h: bad, eta_h: bad, pct: 50, long: true},
  tasks: [{status: "pending", subject: bad, activeForm: bad}]})]));
calmAction("open", "claude:" + bad);
const h = __els.app.innerHTML;
console.log(JSON.stringify({
  noTag: !h.includes("<img") && !h.includes("<b>"),
  escaped: h.includes("&lt;img src=x onerror=alert(1)&gt;"),
  attrsClosed: !h.includes('title=""><b>'),
  rows: rows()
}));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["noTag"], "hostile session text reached the DOM as markup")
        self.assertTrue(out["escaped"])
        self.assertTrue(out["attrsClosed"], "hostile text broke out of an attribute")
        self.assertEqual(1, out["rows"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_keyboard_drives_the_ledger(self) -> None:
        checks = """
const out = {};
let __prevented = 0;
const key = (k, target) => { const before = __prevented;
  __fire("keydown", {key: k, target: target || {}, preventDefault(){ __prevented++; }});
  return __prevented - before; };
render(board());
out.cursorStartsAtTop = __els.app.innerHTML.includes('class="cm-row focus"');
key("j"); out.down1 = calmCursorKey;
key("j"); out.down2 = calmCursorKey;
key("j"); out.clampsAtBottom = calmCursorKey;
key("k"); out.up = calmCursorKey;
key("ArrowUp"); out.arrowUp = calmCursorKey;
key("ArrowUp"); out.clampsAtTop = calmCursorKey;
key("Enter"); out.enterOpens = calmOpenKey;
key(" "); out.spaceCloses = calmOpenKey;
key("f"); out.fFilters = calmFlagOnly;
key("Escape"); out.escapeClears = [calmFlagOnly, calmStateOnly, calmOpenKey];
// Moving the cursor brings it into view; a plain poll does not yank the list.
__revealed = 0;
key("j"); out.revealedOnMove = __revealed;
render(lastData); out.revealedOnPoll = __revealed;
// Keys the ledger does not own are left alone.
key("j", {tagName: "TEXTAREA"}); out.textareaSafe = calmCursorKey;
key("q"); out.unknownKeySafe = calmCursorKey;
// The browser scrolls on Space and the arrows unless the page says otherwise.
out.prevented = [key(" "), key("ArrowDown"), key("ArrowUp"), key("q")];
key(" ");  // leave nothing expanded for the checks below
// A modifier means the chord belongs to the browser or the OS, not to us.
const mode0 = displayMode;
out.modifiersIgnored = ["metaKey", "ctrlKey", "altKey"].map(mod => {
  __fire("keydown", {key: "c", [mod]: true, target: {}, preventDefault(){}});
  return displayMode === mode0;   // checked per modifier: two toggles cancel out
});
// Enter belongs to whatever focusable thing has focus, such as the empty
// state's "Show all sessions" link.
render(payload([]));
const link = {tagName: "A", closest: () => ({})};
out.linkKeepsEnter = key("Enter", link) === 0;
render(board());
// Nothing to move to is not an error, and nothing opens.
render(payload([]));
key("j"); key("Enter");
out.emptySafe = [calmOpenKey, __els.app.innerHTML.includes("cm-empty")];
// Ledger keys stay in the ledger: `j` in regular mode must not move a cursor.
setDisplayMode("regular");
render(board());
calmCursorKey = null;
key("j"); out.regularIgnoresJ = calmCursorKey;
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["cursorStartsAtTop"], "no keyboard cursor on first paint")
        self.assertEqual("codex:bbb2", out["down1"])
        self.assertEqual("claude:ccc3", out["down2"])
        self.assertEqual("claude:ccc3", out["clampsAtBottom"], "cursor ran off the end")
        self.assertEqual("codex:bbb2", out["up"])
        self.assertEqual("claude:aaa1", out["arrowUp"])
        self.assertEqual("claude:aaa1", out["clampsAtTop"], "cursor ran off the start")
        self.assertEqual("claude:aaa1", out["enterOpens"])
        self.assertIsNone(out["spaceCloses"])
        self.assertTrue(out["fFilters"])
        self.assertEqual([False, None, None], out["escapeClears"])
        self.assertEqual(1, out["revealedOnMove"])
        self.assertEqual(1, out["revealedOnPoll"], "a poll scrolled the list on its own")
        self.assertEqual("codex:bbb2", out["textareaSafe"], "stole a key from a text field")
        self.assertEqual("codex:bbb2", out["unknownKeySafe"])
        self.assertEqual(
            [1, 1, 1, 0], out["prevented"], "the browser would scroll as well as the ledger"
        )
        self.assertEqual(
            [True, True, True],
            out["modifiersIgnored"],
            "a modifier chord (cmd/ctrl/alt + c) toggled the display mode",
        )
        self.assertTrue(out["linkKeepsEnter"], "swallowed Enter from a focused link")
        self.assertEqual([None, True], out["emptySafe"])
        self.assertIsNone(out["regularIgnoresJ"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_five_second_poll_does_not_disturb_the_view(self) -> None:
        # render() replaces #app wholesale. Everything the reader set has to
        # survive that: the open row, the cursor, the filters, the scroll.
        checks = """
const out = {};
render(board());
calmAction("sort", "recent");
calmAction("state", "work");
calmAction("open", "codex:bbb2");
calmCursorKey = "codex:bbb2";
__scrollTop = 137;
render(board());
const h = __els.app.innerHTML;
out.scroll = __scrollTop;
out.openKept = h.includes("cm-exp");
out.cursorKept = h.includes('class="cm-row focus open"');
out.sortKept = h.includes('data-arg="recent" aria-pressed="true"');
out.filterKept = calmStateOnly;
// Re-filtering, though, is a new list: keeping the old offset would drop the
// reader into the middle of rows they have not seen.
__scrollTop = 137;
calmAction("clear", null);
out.scrollResetOnFilter = __scrollTop;
__scrollTop = 137;
calmAction("sort", "repo");
out.scrollResetOnSort = __scrollTop;
// A session that disappears must not leave the cursor stranded.
calmAction("sort", "attention");
calmCursorKey = "nope:gone";
render(board());
out.strandedCursor = (__els.app.innerHTML.match(/class="cm-row focus/g) || []).length;
// The stall indicator the refresh loop writes into exists in calm mode too.
out.liveIds = __els.app.innerHTML.includes('id="live-dot"')
  && __els.app.innerHTML.includes('id="live-status"');
out.notifyControlPlaced = calmLedger(Object.assign(board(), {native_notify: ""}))
  .includes("Enable notifications");
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertEqual(137, out["scroll"], "the poll reset the ledger scroll")
        self.assertTrue(out["openKept"], "the poll collapsed the open row")
        self.assertTrue(out["cursorKept"], "the poll lost the keyboard cursor")
        self.assertTrue(out["sortKept"])
        self.assertEqual("work", out["filterKept"])
        self.assertEqual(0, out["scrollResetOnFilter"], "a re-filter kept a stale scroll offset")
        self.assertEqual(0, out["scrollResetOnSort"], "a re-sort kept a stale scroll offset")
        self.assertEqual(1, out["strandedCursor"], "cursor vanished with its session")
        self.assertTrue(out["liveIds"], "calm mode cannot show a stalled refresh")
        self.assertTrue(out["notifyControlPlaced"], "no way to grant notifications in calm mode")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_two_harnesses_sharing_a_session_id_stay_two_rows(self) -> None:
        # dedupe_sessions keys on (harness, sid), so the same sid CAN reach the
        # page twice on different harnesses. The rest of the page already
        # treats that pair as identity (sessKey, the notification map); keying
        # the ledger on a bare sid would expand both rows at once and leave the
        # cursor unable to tell them apart.
        checks = """
const out = {};
const clash = "019fa752";
render(payload([
  mk({sid: clash, session: clash, harness: "claude", project: "repo/a", title: "Claude one"}),
  mk({sid: clash, session: clash, harness: "codex", project: "repo/b", title: "Codex one"})]));
out.bothRows = rows();
calmAction("open", K("claude", clash));
const h = __els.app.innerHTML;
out.onlyOneExpanded = (h.match(/class="cm-exp"/g) || []).length;
out.expandedTheRightOne = h.indexOf("Claude one") < h.indexOf("cm-exp")
  && h.indexOf("cm-exp") < h.indexOf("Codex one");
out.cursorIsScoped = calmCursorKey;
// j must step from one to the other, not sit still.
__fire("keydown", {key: "j", target: {}, preventDefault(){}});
out.moved = calmCursorKey;
// And the clipboard still gets the bare session id, not the row key.
calmAction("copy", K("codex", clash));
await __settle();
out.copied = __wrote;
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks, clipboard="ok")
        self.assertEqual(2, out["bothRows"], "two harnesses collapsed into one row")
        self.assertEqual(1, out["onlyOneExpanded"], "one click expanded both rows")
        self.assertTrue(out["expandedTheRightOne"])
        self.assertEqual("claude:019fa752", out["cursorIsScoped"])
        self.assertEqual("codex:019fa752", out["moved"], "the cursor could not tell them apart")
        self.assertEqual(["019fa752"], out["copied"], "copied the row key instead of the id")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_an_unexpected_status_or_harness_cannot_render_undefined(self) -> None:
        # Every plain object inherits truthy `constructor` and `toString` from
        # Object.prototype, so a lookup like TABLE[x.status] || FALLBACK skips
        # its own fallback for those keys and paints `undefined` as both the
        # glyph and the CSS colour.
        checks = """
render(payload([mk({sid: "p", session: "p", harness: "constructor",
  state: "working", active: true, last_activity: 99999, rate_per_min: 5,
  tasks: [{status: "constructor", subject: "poisoned", activeForm: null},
          {status: "toString", subject: "also poisoned", activeForm: null},
          {status: "in_progress", subject: "real one", activeForm: "Working"}]})]));
calmAction("open", K("constructor", "p"));
const h = __els.app.innerHTML;
console.log(JSON.stringify({
  noUndefined: !h.includes("undefined"),
  rows: rows(),
  tasksRendered: (h.match(/class="cm-task"/g) || []).length,
  realTaskFirst: h.indexOf("Working…") < h.indexOf("poisoned")}));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["noUndefined"], "an inherited key rendered as undefined")
        self.assertEqual(1, out["rows"])
        self.assertEqual(3, out["tasksRendered"], "a poisoned status dropped a task row")
        self.assertTrue(out["realTaskFirst"], "inherited keys broke the task ordering")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_keyboard_focus_survives_the_poll(self) -> None:
        # The ledger's controls are real focusable buttons, and render() throws
        # the focused one away every five seconds. Without this, tabbing to a
        # control and pressing it is a race against the refresh.
        checks = """
const out = {};
render(board());
const find = act => __controls().find(c => c.getAttribute("data-calm") === act);
// Focus a control that carries an argument, and one that does not.
document.activeElement = __controls().find(c =>
  c.getAttribute("data-calm") === "copy" &&
  c.getAttribute("data-arg") === K("claude", "aaa1"));
__focused = null;
render(board());
out.withArg = __focused;
document.activeElement = find("flag");
__focused = null;
render(board());
out.withoutArg = __focused;
// A control that is gone after the payload changed must not steal focus.
document.activeElement = __controls().find(c =>
  c.getAttribute("data-arg") === K("claude", "ccc3"));
__focused = null;
render(payload([blocked]));
out.departed = __focused;
// Focus outside the ledger is left alone.
document.activeElement = {getAttribute: () => null};
__focused = null;
render(board());
out.untracked = __focused;
document.activeElement = null;
__focused = null;
render(board());
out.noFocus = __focused;
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertEqual("copy:claude:aaa1", out["withArg"], "focus was lost across the poll")
        self.assertEqual("flag:", out["withoutArg"])
        self.assertIsNone(out["departed"], "focus jumped to an unrelated control")
        self.assertIsNone(out["untracked"], "stole focus from outside the ledger")
        self.assertIsNone(out["noFocus"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_harness_that_reports_no_rate_does_not_read_as_zero(self) -> None:
        # Copilot, OpenCode, Cursor and Droid never populate rate_per_min, and
        # the regular view omits the meter rather than printing a zero. Calm
        # mode printing "0 /m" would make the two modes disagree.
        checks = """
render(payload([
  mk({sid: "cp", session: "cp", harness: "copilot", state: "working", active: true,
      last_activity: 99999, rate_per_min: 0}),
  mk({sid: "cl", session: "cl", state: "working", active: true,
      last_activity: 99999, rate_per_min: 1200})]));
const h = __els.app.innerHTML;
console.log(JSON.stringify({
  zero: h.includes(">0 /m<"), dash: h.includes(">—<"), real: h.includes(">1,200 /m<")}));
"""
        out = self.run_calm(checks)
        self.assertFalse(out["zero"], 'printed a fabricated "0 /m" for a rate-less harness')
        self.assertTrue(out["dash"])
        self.assertTrue(out["real"], "lost the rate for a harness that does report one")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_copy_id_reports_what_the_clipboard_actually_did(self) -> None:
        checks = """
const out = {};
render(board());
calmAction("copy", "claude:aaa1");
await __settle();
out.wrote = __wrote;
out.label = __els.app.innerHTML.includes(">copied<");
out.otherRowsUnchanged = (__els.app.innerHTML.match(/>id</g) || []).length;
__tick();
out.reverts = !__els.app.innerHTML.includes(">copied<");
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks, clipboard="ok")
        self.assertEqual(["aaa1"], out["wrote"], "copy id wrote the wrong value")
        self.assertTrue(out["label"], "no feedback that the id was copied")
        self.assertEqual(2, out["otherRowsUnchanged"])
        self.assertTrue(out["reverts"], "the copied label never clears")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_copy_id_never_claims_a_copy_the_browser_refused(self) -> None:
        # An unfocused document or a non-secure context rejects the write. A
        # confident "copied" there costs the reader the id they wanted.
        checks = """
render(board());
calmAction("copy", "claude:aaa1");
await __settle(); await __settle();
const h = __els.app.innerHTML;
console.log(JSON.stringify({lied: h.includes(">copied<"), told: h.includes(">blocked<")}));
"""
        denied = self.run_calm(checks, clipboard="denied")
        self.assertFalse(denied["lied"], "claimed a copy the clipboard rejected")
        self.assertTrue(denied["told"])
        # And with no Clipboard API at all.
        absent = self.run_calm(checks)
        self.assertFalse(absent["lied"])
        self.assertTrue(absent["told"])

    def test_every_css_variable_the_page_uses_is_declared(self) -> None:
        # A `var(--typo)` renders as nothing at all and no linter here sees it.
        style = re.search(r"<style>(.*?)</style>", dashboard.PAGE, re.DOTALL)
        assert style is not None
        declared = set(re.findall(r"(--[\w-]+)\s*:", style.group(1)))
        used = set(re.findall(r"var\((--[\w-]+)", dashboard.PAGE))
        self.assertEqual(set(), used - declared, "page uses CSS variables nothing declares")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_column_headers_share_the_scrollers_width(self) -> None:
        # Headers and rows lay out on the same grid. As a SIBLING of the
        # scrolling body the header keeps the full frame width while the rows
        # lose the scrollbar's, and the whole delta lands in the one flexible
        # track, so every label from `where` rightward sits off its data. Only
        # invisible where scrollbars are overlays, which is to say only on the
        # machine this was built on.
        checks = """
render(board());
const h = __els.app.innerHTML;
console.log(JSON.stringify({
  nested: h.includes('<div class="cm-body" id="cm-body"><div class="cm-head">'),
  headings: h.includes("<span>where</span>")}));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["nested"], "the column headers are outside the scroll container")
        self.assertTrue(out["headings"])
        self.assertIn(".cm-head{position:sticky;top:0;", dashboard.PAGE)

    def test_a_focused_quick_action_can_actually_be_seen(self) -> None:
        # The row's quick action lives in a container held at opacity:0 until
        # hover. Ancestor opacity composites the whole subtree as a group, so a
        # focused child cannot make itself visible — the row has to. Without
        # this the ledger has one invisible tab stop per row.
        self.assertIn(".cm-row:focus-within .cm-q{opacity:1}", dashboard.PAGE)

    def test_no_control_drops_its_focus_ring_without_replacing_it(self) -> None:
        style = re.search(r"<style>(.*?)</style>", dashboard.PAGE, re.DOTALL)
        assert style is not None
        rules = re.findall(r"\n\s*([^\n{]*:focus-visible[^\n{]*)\{([^}]*)\}", style.group(1))
        self.assertGreater(len(rules), 4, "focus-visible rules disappeared; is the regex stale?")
        for selector, body in rules:
            with self.subTest(selector=selector.strip()):
                if "outline:none" in body:
                    self.assertIn(
                        "box-shadow",
                        body,
                        "removes the browser focus ring and puts nothing in its place",
                    )

    def test_the_calm_palette_has_a_dark_counterpart(self) -> None:
        # Calm mode adds surfaces and a second flag tone. Declaring them only
        # in the light block leaves a light-on-light ledger after dark.
        dark = re.search(
            r"@media \(prefers-color-scheme:dark\)\{(.*?)\n  \}", dashboard.PAGE, re.DOTALL
        )
        assert dark is not None
        for name in ("--sunk", "--line2", "--accent-ink", "--warn", "--warnink"):
            with self.subTest(token=name):
                self.assertIn(name, dark.group(1))

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_stop_button_arms_then_posts_and_shows_the_stopped_panel(self) -> None:
        checks = """
const out = {};
render(board());
out.shown = __els.app.innerHTML.includes('data-calm="stop"');
out.armedBefore = __els.app.innerHTML.includes("sure?");

// First click only arms it: the page cannot undo a stop.
__fire("click", {target: {closest: sel => sel === "[data-calm]"
  ? {getAttribute: a => a === "data-calm" ? "stop" : null} : null}});
out.armedAfter = __els.app.innerHTML.includes("sure?");
out.postedYet = __fetchCalls.filter(c => c[0] === "/api/shutdown").length;

// A refresh must not disarm it — #app is rebuilt every 5s and the button
// would flicker under the reader's cursor.
render(board());
out.survivesRender = __els.app.innerHTML.includes("sure?");

__fetchImpl = () => Promise.resolve({ok: true});
__fire("click", {target: {closest: sel => sel === "[data-calm]"
  ? {getAttribute: a => a === "data-calm" ? "stop" : null} : null}});
await __settle(); await __settle();
const posted = __fetchCalls.filter(c => c[0] === "/api/shutdown");
out.posted = posted.length;
out.method = posted.length ? posted[0][1].method : null;
out.stoppedPanel = __els.app.innerHTML.includes("Cargento stopped");
out.buttonGone = __els.app.innerHTML.includes('data-calm="stop"');
out.title = document.title;
out.refreshTimer = refreshTimer;
out.clearedIntervals = __clearedIntervals;
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["shown"])
        self.assertFalse(out["armedBefore"])
        self.assertTrue(out["armedAfter"])
        self.assertEqual(0, out["postedYet"])
        self.assertTrue(out["survivesRender"])
        self.assertEqual(1, out["posted"])
        self.assertEqual("POST", out["method"])
        self.assertTrue(out["stoppedPanel"])
        self.assertFalse(out["buttonGone"])
        self.assertIn("stopped", out["title"])
        self.assertIsNone(out["refreshTimer"])
        self.assertEqual([73], out["clearedIntervals"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_armed_stop_button_keeps_focus_and_accepts_keyboard_activation(self) -> None:
        checks = """
const out = {trials: []};
const stopButton = {
  tagName: "BUTTON",
  getAttribute: a => a === "data-calm" ? "stop" : null,
  closest(sel){
    return sel === "[data-calm]" || sel === '[data-calm="stop"]' ||
      sel === "a[href],button,select,textarea,input,[tabindex]" ? this : null;
  },
  focus(){ document.activeElement = this; }
};
__els["stop-control"] = stopButton;
const clickStop = () => __fire("click", {target: stopButton});
__fetchImpl = () => Promise.resolve({ok: true});

for(const key of [" ", "Enter"]){
  stopArmed = false; stopError = ""; serverStopped = false; stopFocusPending = false;
  refreshTimer = 73; document.activeElement = null; __fetchCalls = [];
  render(board());
  clickStop();
  const armed = __els.app.innerHTML.includes("sure?");
  const focusKept = document.activeElement === stopButton;
  __fire("keydown", {key, target: stopButton, preventDefault(){}});
  const armedAfterKey = __els.app.innerHTML.includes("sure?");
  clickStop();  // the native click generated by Space or Enter
  await __settle(); await __settle();
  out.trials.push({key, armed, focusKept, armedAfterKey,
    posts: __fetchCalls.filter(c => c[0] === "/api/shutdown").length,
    stopped: __els.app.innerHTML.includes("Cargento stopped")});
}
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertEqual(2, len(out["trials"]))
        for trial in out["trials"]:
            with self.subTest(key=repr(trial["key"])):
                self.assertTrue(trial["armed"])
                self.assertTrue(
                    trial["focusKept"],
                    "arming re-rendered the focused button away",
                )
                self.assertTrue(
                    trial["armedAfterKey"],
                    "the activation key disarmed before the button could click",
                )
                self.assertEqual(1, trial["posts"])
                self.assertTrue(trial["stopped"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_stop_disarms_on_escape_and_on_a_click_elsewhere(self) -> None:
        checks = """
const out = {};
const clickStop = () => __fire("click", {target: {closest: sel => sel === "[data-calm]"
  ? {getAttribute: a => a === "data-calm" ? "stop" : null} : null}});
const clickAway = () => __fire("click", {target: {closest: () => null}});

render(board());
clickStop();
out.armed = __els.app.innerHTML.includes("sure?");
__fire("keydown", {key: "Escape", preventDefault(){}, target: {tagName: "DIV"}});
out.afterEsc = __els.app.innerHTML.includes("sure?");

clickStop();
out.armedAgain = __els.app.innerHTML.includes("sure?");
clickAway();
out.afterClickAway = __els.app.innerHTML.includes("sure?");

// A click on a *different* control is an answer too. Otherwise the armed
// state outlives the moment it was armed in, and a single later click on
// stop takes the server down with no confirmation at all.
const clickControl = (act) => __fire("click", {target: {closest: sel => sel === "[data-calm]"
  ? {getAttribute: a => a === "data-calm" ? act : null} : null}});
clickStop();
out.armedOnceMore = __els.app.innerHTML.includes("sure?");
clickControl("flag");
out.afterOtherControl = __els.app.innerHTML.includes("sure?");
clickStop();                    // must re-arm, not fire
out.rearmed = __els.app.innerHTML.includes("sure?");
await __settle(); await __settle();
out.nothingPosted = __fetchCalls.filter(c => c[0] === "/api/shutdown").length;
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["armed"])
        self.assertFalse(out["afterEsc"])
        self.assertTrue(out["armedAgain"])
        self.assertFalse(out["afterClickAway"])
        self.assertTrue(out["armedOnceMore"])
        self.assertFalse(out["afterOtherControl"], "a click on another control left stop armed")
        self.assertTrue(out["rearmed"])
        self.assertEqual(0, out["nothingPosted"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_failed_stop_reports_inline_and_leaves_the_page_live(self) -> None:
        checks = """
const out = {};
render(board());
const clickStop = () => __fire("click", {target: {closest: sel => sel === "[data-calm]"
  ? {getAttribute: a => a === "data-calm" ? "stop" : null} : null}});
clickStop();
__fetchImpl = () => Promise.resolve({ok: false, status: 403});
clickStop();
await __settle(); await __settle();
// The server is still running, so the page must not claim otherwise.
out.stoppedPanel = __els.app.innerHTML.includes("Cargento stopped");
out.error = __els.app.innerHTML.includes("stop failed");
out.rows = rows();
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertFalse(out["stoppedPanel"])
        self.assertTrue(out["error"])
        self.assertEqual(3, out["rows"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_poll_starting_after_the_stop_never_reaches_the_network(self) -> None:
        checks = """
const out = {};
render(board());
// The page's own bottom-of-script `refresh()` already fired once at load,
// before this check ever ran — count from here, not from zero.
const before = __fetchCalls.filter(c => String(c[0]).startsWith("/api/data")).length;
serverStopped = true;
renderStopped();
await refresh();
out.stillStopped = __els.app.innerHTML.includes("Cargento stopped");
out.noFetch = __fetchCalls.filter(c => String(c[0]).startsWith("/api/data")).length - before;
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["stillStopped"])
        self.assertEqual(0, out["noFetch"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_poll_in_flight_across_the_stop_does_not_repaint_the_panel(self) -> None:
        # The one the entry guard above cannot cover: this poll had already
        # called fetch before the stop landed, so it settles afterwards. The
        # panel surviving is now the render() guard's doing, so this also
        # asserts what only refresh()'s own post-await guard can protect: a
        # payload that arrived after the stop must not be absorbed into the rate
        # history, which does not go through render() and would otherwise leave
        # a sample recorded for a server that was already gone.
        checks = """
const out = {};
render(board());
let releaseData;
const later = () => { const d = board(); d.generated = d.generated + 60; return d; };
__fetchImpl = (url) => String(url).startsWith("/api/data")
  ? new Promise(r => { releaseData = () =>
      r({ok: true, json: () => Promise.resolve(later())}); })
  : Promise.resolve({ok: true});          // /api/shutdown answers at once
const poll = refresh();                   // in flight, deliberately unsettled

const clickStop = () => __fire("click", {target: {closest: sel => sel === "[data-calm]"
  ? {getAttribute: a => a === "data-calm" ? "stop" : null} : null}});
clickStop(); clickStop();                 // arm, then confirm
await __settle(); await __settle();
out.stoppedAfterStop = __els.app.innerHTML.includes("Cargento stopped");
const ratesBefore = rateHistory.length;
const generatedBefore = lastGenerated;

releaseData();
await poll; await __settle(); await __settle();
out.stoppedAfterLatePoll = __els.app.innerHTML.includes("Cargento stopped");
out.dashboardBack = __els.app.innerHTML.includes("cm-frame");
out.title = document.title;
out.ratesGrew = rateHistory.length - ratesBefore;
out.generatedMoved = lastGenerated !== generatedBefore;
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertEqual(0, out["ratesGrew"], "a payload that arrived after the stop was recorded")
        self.assertFalse(out["generatedMoved"], "the stale payload advanced lastGenerated")
        self.assertTrue(out["stoppedAfterStop"])
        self.assertTrue(out["stoppedAfterLatePoll"], "a late poll repainted the stopped panel")
        self.assertFalse(out["dashboardBack"])
        self.assertIn("stopped", out["title"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_keystroke_disarms_the_stop_just_like_a_click(self) -> None:
        # The keyboard drives the same controls the mouse does — `c` is the mode
        # button, `f` the flag, Enter opens a row — so disarming only on click
        # left the armed state outliving the interaction it was armed in, and one
        # later click on stop would end the server unconfirmed.
        checks = """
const out = {trials: []};
const shutdowns = () => __fetchCalls.filter(c => String(c[0]) === "/api/shutdown").length;
const clickStop = () => __fire("click", {target: {closest: sel => sel === "[data-calm]"
  ? {getAttribute: a => a === "data-calm" ? "stop" : null} : null}});
const key = k => __fire("keydown", {key: k, target: {}, preventDefault(){}});
__fetchImpl = () => Promise.resolve({ok: true});

const trial = async (label, act) => {
  displayMode = "calm"; calmOpenKey = null; calmCursorKey = null;
  calmFlagOnly = false; calmStateOnly = null;
  stopArmed = false; stopError = ""; serverStopped = false;
  render(board());
  clickStop();
  const armed = stopArmed;
  act();
  const stillArmed = __els.app.innerHTML.includes("sure?");
  const before = shutdowns();
  clickStop();                                    // ONE further click
  await __settle(); await __settle();
  return {label, armed, stillArmed, posts: shutdowns() - before,
    stopped: __els.app.innerHTML.includes("Cargento stopped")};
};
for(const [label, act] of [
    ["c", () => key("c")], ["f", () => key("f")], ["Enter", () => key("Enter")],
    ["j", () => key("j")], ["k", () => key("k")], ["ArrowDown", () => key("ArrowDown")]]){
  out.trials.push(await trial(label, act));
}
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertEqual(6, len(out["trials"]))
        for trial in out["trials"]:
            with self.subTest(key=trial["label"]):
                self.assertTrue(trial["armed"], "the first click did not arm it")
                self.assertFalse(trial["stillArmed"], "the keystroke left stop armed")
                self.assertEqual(0, trial["posts"], "one click after a keystroke stopped it")
                self.assertFalse(trial["stopped"], "the server was stopped unconfirmed")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_stopped_panel_takes_no_keyboard_side_effects(self) -> None:
        # render()'s guard stops the paint but not what happens on the way there.
        # setDisplayMode writes localStorage *before* it paints, so `c` on the
        # terminal panel looked inert while durably flipping the saved mode for
        # the next run; and the calm keys went on calling preventDefault(),
        # swallowing page scrolling on a page that is no longer live.
        checks = """
const out = {};
let prevented = 0;
const key = k => __fire("keydown", {key: k, target: {},
  preventDefault(){ prevented++; }});
const clickStop = () => __fire("click", {target: {closest: sel => sel === "[data-calm]"
  ? {getAttribute: a => a === "data-calm" ? "stop" : null} : null}});
__fetchImpl = () => Promise.resolve({ok: true});
render(board());
out.modeBefore = displayMode;
out.storedBefore = __store["cargento.displayMode"];
clickStop(); clickStop();
await __settle(); await __settle();
out.stopped = __els.app.innerHTML.includes("Cargento stopped");

prevented = 0;
["c", "j", "k", "ArrowDown", "ArrowUp", "Enter", " ", "f", "Escape"].forEach(key);
out.storedAfter = __store["cargento.displayMode"];
out.modeAfter = displayMode;
out.prevented = prevented;
out.stillStopped = __els.app.innerHTML.includes("Cargento stopped");
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["stopped"])
        self.assertTrue(out["stillStopped"])
        self.assertEqual(
            out["storedBefore"], out["storedAfter"], "a keystroke persisted a mode change"
        )
        self.assertEqual(out["modeBefore"], out["modeAfter"], "a keystroke changed the mode")
        self.assertEqual(0, out["prevented"], "the terminal panel still swallows keystrokes")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_nothing_repaints_over_the_stopped_panel(self) -> None:
        # refresh() is not the only way into render(): fourteen other call sites
        # end in render(lastData), and the keydown listener is bound to
        # `document`, so nothing in #app gates it. One `c` was enough to put a
        # live-looking board back with a stale needs-input count in the title.
        checks = """
const out = {};
render(board());
__fetchImpl = () => Promise.resolve({ok: true});
const clickStop = () => __fire("click", {target: {closest: sel => sel === "[data-calm]"
  ? {getAttribute: a => a === "data-calm" ? "stop" : null} : null}});
clickStop(); clickStop();
await __settle(); await __settle();
out.stopped = __els.app.innerHTML.includes("Cargento stopped");
out.title = document.title;

const key = k => __fire("keydown", {key: k, target: {}, preventDefault(){}});
const live = () => __els.app.innerHTML.includes("cm-frame")
  || __els.app.innerHTML.includes('class="tile"');

// `c` toggles the display mode, which ends in render(lastData).
key("c");
out.afterC = {stopped: __els.app.innerHTML.includes("Cargento stopped"),
  live: live(), title: document.title};

// The calm ledger keys, and a direct call for the paths keys cannot reach.
key("f"); key("j"); key("k"); key("Escape"); key("Enter");
out.afterKeys = {stopped: __els.app.innerHTML.includes("Cargento stopped"), live: live()};

calmAction("flag", null);
toggleIdle();
setDisplayMode("regular");
render(board());
out.afterDirect = {stopped: __els.app.innerHTML.includes("Cargento stopped"),
  live: live(), title: document.title};
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["stopped"])
        self.assertIn("stopped", out["title"])
        for label in ("afterC", "afterKeys", "afterDirect"):
            with self.subTest(after=label):
                self.assertTrue(out[label]["stopped"], f"{label} repainted over the stopped panel")
                self.assertFalse(out[label]["live"], f"{label} brought the dashboard back")
        # The title is part of the panel: a stale needs-input count there says
        # a session wants you, for a server that cannot tell you either way.
        self.assertIn("stopped", out["afterC"]["title"])
        self.assertIn("stopped", out["afterDirect"]["title"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_stop_is_not_counted_as_a_failed_refresh(self) -> None:
        # The same race down the catch arm: the server has gone, so the poll in
        # flight rejects. A stop the reader asked for is not a refresh failure,
        # and counting it as one drives the "stalled · retrying every 5s"
        # bookkeeping for a server that is never coming back.
        checks = """
const out = {};
render(board());
let failData;
__fetchImpl = (url) => String(url).startsWith("/api/data")
  ? new Promise((_, reject) => { failData = () => reject(new Error("connection refused")); })
  : Promise.resolve({ok: true});
const poll = refresh();

const clickStop = () => __fire("click", {target: {closest: sel => sel === "[data-calm]"
  ? {getAttribute: a => a === "data-calm" ? "stop" : null} : null}});
clickStop(); clickStop();
await __settle(); await __settle();

failData();
await poll; await __settle(); await __settle();
out.stillStopped = __els.app.innerHTML.includes("Cargento stopped");
out.failures = window.__refreshFailures || 0;
console.log(JSON.stringify(out));
"""
        out = self.run_calm(checks)
        self.assertTrue(out["stillStopped"])
        # No assertion on the stalled banner here: it is written to #live-status
        # and #live-dot, which the DOM stub does not register, so any such check
        # would pass whatever the code did. The failure count is the observable.
        self.assertEqual(0, out["failures"], "a deliberate stop was counted as a refresh failure")


class DocumentationMatchesCodeTest(unittest.TestCase):
    """Reviewers found documentation describing behaviour the code no longer
    had, twice. These assert the claims against the implementation."""

    SKILL = (SERVER_PATH.parent / "SKILL.md").read_text(encoding="utf-8")

    def posix_roots(self) -> dict[str, list[str]]:
        roots: dict[str, list[str]] = dashboard.resolve_store_roots(
            platform_name="darwin", environ={}, home="/HOME"
        )
        return roots

    def test_documented_store_paths_are_the_ones_searched(self) -> None:
        # Every "~/..." path in the data-source list must be a real default.
        # ".claude/settings" (the user's own hook config) and ".cargento" (Cargento's
        # own state and log directory) are not harness stores, so the store-root
        # assertion below does not apply to them.
        excluded_prefixes = (".claude/settings", ".cargento")
        documented = {
            "~/" + match
            for match in re.findall(r"`~/([\w./*<>-]+?)[`/]", self.SKILL)
            if not match.startswith(excluded_prefixes)
        }
        searched = {
            root.replace("/HOME", "~") for roots in self.posix_roots().values() for root in roots
        }
        for path in sorted(documented):
            with self.subTest(documented=path):
                self.assertTrue(
                    any(
                        root.startswith(path.rstrip("/")) or path.startswith(root)
                        for root in searched
                    ),
                    f"SKILL.md documents {path} but nothing searches it: {sorted(searched)}",
                )

    def test_documented_env_overrides_are_the_ones_honoured(self) -> None:
        documented = {
            name
            for name in (
                "CLAUDE_CONFIG_DIR",
                "CODEX_HOME",
                "GEMINI_CLI_HOME",
                "COPILOT_HOME",
                "PI_CODING_AGENT_DIR",
                "PI_CODING_AGENT_SESSION_DIR",
            )
            if f"`{name}`" in self.SKILL
        }
        self.assertEqual(set(dashboard.STORE_ENV_VARS), documented)
        # And each one actually redirects its store.
        for name, key, expected in (
            ("CLAUDE_CONFIG_DIR", "claude.projects", "/opt/x/projects"),
            ("CODEX_HOME", "codex.sessions", "/opt/x/sessions"),
            ("GEMINI_CLI_HOME", "gemini.tmp", "/opt/x/.gemini/tmp"),
            ("COPILOT_HOME", "copilot.root", "/opt/x"),
            ("PI_CODING_AGENT_DIR", "pi.sessions", "/opt/x/sessions"),
            ("PI_CODING_AGENT_SESSION_DIR", "pi.sessions", "/opt/x"),
        ):
            with self.subTest(env=name):
                roots = dashboard.resolve_store_roots(
                    platform_name="linux", environ={name: "/opt/x"}, home="/HOME"
                )
                self.assertEqual([expected], roots[key])

    def test_the_documented_python_floor_matches_the_tooling(self) -> None:
        self.assertIn("Python 3.11+", self.SKILL)
        pyproject = (SERVER_PATH.parents[3] / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('python_version = "3.11"', pyproject)
        self.assertIn('target-version = "py311"', pyproject)

    def test_documented_urls_use_the_address_the_server_binds(self) -> None:
        # The listener is IPv4-only, so "localhost" can resolve to ::1 and fail.
        self.assertNotIn("http://localhost:4553", self.SKILL)
        self.assertIn("http://127.0.0.1:4553", self.SKILL)


class DaemonLifecycleTest(unittest.TestCase):
    """The real thing: detach, outlive the caller, answer --status, stop.

    Everything else in this file tests a piece. This tests the promise.
    """

    SERVER = str(SERVER_PATH)

    @staticmethod
    def _free_port() -> int:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            return int(probe.getsockname()[1])

    def _run(self, *flags: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, self.SERVER, *flags],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    def test_daemon_outlives_its_caller_and_stops_on_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, "CARGENTO_HOME": tmp}
            port = self._free_port()
            flags = ("--port", str(port))
            try:
                start = self._run(*flags, "--daemon", env=env)
                self.assertEqual(0, start.returncode, start.stdout + start.stderr)
                # The starting process has exited by now. Everything below runs
                # against a server whose parent is gone.
                self.assertIn(f"http://127.0.0.1:{port}/", start.stdout)
                self.assertIn("pid ", start.stdout)

                kind, health = dashboard.probe_port(port, timeout=10)
                self.assertEqual("cargento", kind, start.stdout)
                assert health is not None
                self.assertNotEqual(os.getpid(), health["pid"])

                state = json.loads(Path(tmp, f"cargento-{port}.json").read_text(encoding="utf-8"))
                self.assertEqual(health["pid"], state["pid"])

                status = self._run(*flags, "--status", env=env)
                self.assertEqual(0, status.returncode, status.stdout + status.stderr)
                self.assertIn("running", status.stdout)

                stopped = self._run(*flags, "--stop", env=env)
                self.assertEqual(0, stopped.returncode, stopped.stdout + stopped.stderr)
                self.assertIn("stopped", stopped.stdout)

                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    if dashboard.probe_port(port, timeout=1)[0] == "closed":
                        break
                    time.sleep(0.2)
                self.assertEqual("closed", dashboard.probe_port(port, timeout=1)[0])
                self.assertFalse(Path(tmp, f"cargento-{port}.json").exists())

                after = self._run(*flags, "--status", env=env)
                self.assertEqual(1, after.returncode)
                self.assertIn("not running", after.stdout)
            finally:
                # Never leave a detached server behind, however this test ended.
                self._run(*flags, "--stop", env=env)

    def test_a_busy_port_still_explains_itself_under_daemon(self) -> None:
        """D-1's promise: binding happens before detaching, so this message
        reaches the terminal that asked for it and not just a log file."""
        httpd = dashboard.LoopbackHTTPServer(("127.0.0.1", 0), dashboard.Handler)
        # Closes the listener when the loop exits, so the reaping --stop below
        # does not sit out the whole release timeout waiting for a socket that
        # only the outer finally was ever going to close.
        thread = serve_until_closed(httpd)
        port = httpd.server_port
        try:
            with tempfile.TemporaryDirectory() as tmp:
                env = {**os.environ, "CARGENTO_HOME": tmp}
                try:
                    result = self._run("--port", str(port), "--daemon", env=env)
                    self.assertEqual(1, result.returncode, result.stdout + result.stderr)
                    self.assertIn(f"port {port}", result.stdout + result.stderr)
                finally:
                    # If the busy-port race let the bind through anyway, this
                    # reaps the detached daemon before the temp dir is gone. It
                    # also stops this fixture, which is a real Handler on the
                    # same port and indistinguishable from a stray daemon.
                    reap = self._run("--port", str(port), "--stop", env=env)
                    self.assertEqual(0, reap.returncode, reap.stdout + reap.stderr)
        finally:
            httpd.shutdown()
            thread.join(timeout=5)
            with contextlib.suppress(OSError):
                httpd.server_close()


if __name__ == "__main__":
    unittest.main()
