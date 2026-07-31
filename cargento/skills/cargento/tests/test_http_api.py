from __future__ import annotations

import contextlib
import email.message
import errno
import http.client
import http.server
import io
import json
import os
import socket
import subprocess
import sys
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from unittest import mock

from cargento_runtime import aggregate, cli, http_api, lifecycle, notifications
from cargento_runtime import io as runtime_io

from .support import (
    PAGE_BYTES,
    RuntimeTestCase,
    collect,
    collect_json,
    make_runtime,
    make_server,
    serve_until_closed,
    state_of,
)


def _application(os_name: str) -> Any:
    """An application whose config claims `os_name`, whatever the host is.

    The port-sharing tests below turn on a config that *disagrees* with the
    host, which is the only way to tell a config read from an ambient one.
    """
    config, state = make_runtime(os_name=os_name)
    return aggregate.Application(
        config,
        state,
        (),
        native_notifier=lambda _platform: "",
        popup_notifier=lambda _title, _message: None,
        diagnostic_sink=lambda _line: None,
    )


class CargentoServerTest(RuntimeTestCase):
    def test_notify_endpoint_accepts_valid_non_object_and_deep_json(self) -> None:
        httpd = make_server()
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        bodies = [
            json.dumps({"session_id": "12345678", "message": "before\u0000after"}).encode(),
            b"[1,2,3]",
            b"null",
            b'"text"',
            (b"[" * 1200) + b"0" + (b"]" * 1200),
        ]
        try:
            with mock.patch.object(notifications, "notify_mac") as notify:
                for body in bodies:
                    conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=2)
                    conn.request(
                        "POST",
                        "/api/notify",
                        body=body,
                        headers={"Content-Type": "application/json"},
                    )
                    response = conn.getresponse()
                    self.assertEqual(200, response.status)
                    self.assertEqual(b'{"ok":true}', response.read())
                    conn.close()
            self.assertNotIn("\x00", notify.call_args.args[1])
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_cross_site_fetch_metadata_is_rejected(self) -> None:
        httpd = make_server()
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=2)
            conn.request("GET", "/api/data", headers={"Sec-Fetch-Site": "cross-site"})
            response = conn.getresponse()
            self.assertEqual(403, response.status)
            response.read()
            conn.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_cross_site_request_boundary(self) -> None:
        # Chrome labels *any* navigation whose initiator was another origin
        # "cross-site" — including a user clicking a link to the dashboard.
        # Rejecting those returned 403 for an ordinary way to open the page
        # (found by loading it in a real browser). Serving a top-level
        # document navigation is safe: the initiator cannot read a
        # cross-origin document. Everything that *can* read stays blocked.
        navigation = {"Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"}
        cases = [
            # (method, path, headers, expected status, why)
            ("GET", "/", {"Sec-Fetch-Site": "cross-site", **navigation}, 200, "link to page"),
            (
                "GET",
                "/api/data",
                {"Sec-Fetch-Site": "cross-site", **navigation},
                200,
                "link to api",
            ),
            ("GET", "/", {"Sec-Fetch-Site": "none", **navigation}, 200, "typed/bookmarked"),
            ("GET", "/api/data", {"Sec-Fetch-Site": "same-origin"}, 200, "the page's own poll"),
            # Readable by the initiator — must stay blocked.
            (
                "GET",
                "/api/data",
                {
                    "Sec-Fetch-Site": "cross-site",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Dest": "empty",
                },
                403,
                "cross-site fetch",
            ),
            (
                "GET",
                "/",
                {
                    "Sec-Fetch-Site": "cross-site",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Dest": "iframe",
                },
                403,
                "framed by another site",
            ),
            (
                "GET",
                "/api/data",
                {"Sec-Fetch-Site": "cross-site", "Origin": "https://evil.example", **navigation},
                403,
                "cross-origin Origin header",
            ),
            # A cross-site form submission is also a "navigation", so POST
            # must never take the relaxed path.
            (
                "POST",
                "/api/notify",
                {"Sec-Fetch-Site": "cross-site", **navigation},
                403,
                "cross-site form POST",
            ),
            ("GET", "/", {"Host": "evil.example"}, 403, "DNS rebinding"),
        ]
        httpd = make_server()
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            for method, path, headers, expected, why in cases:
                with self.subTest(why=why):
                    conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)
                    body = b'{"session_id":"x"}' if method == "POST" else None
                    conn.request(method, path, body=body, headers=headers)
                    response = conn.getresponse()
                    self.assertEqual(expected, response.status)
                    response.read()
                    conn.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_collect_json_single_flights_concurrent_cold_requests(self) -> None:
        calls: list[tuple[float, bool]] = []
        calls_lock = threading.Lock()

        # Read the window off the application under test, so a collect_json that
        # ignored its window argument is visible here rather than silent.
        def fake_collect(app: aggregate.Application, *, show_all: bool) -> dict[str, Any]:
            with calls_lock:
                calls.append((app.config.window_hours, show_all))
            time.sleep(0.02)
            return {"window_hours": app.config.window_hours, "show_all": show_all}

        with mock.patch.object(aggregate.Application, "collect", fake_collect):
            with ThreadPoolExecutor(max_workers=12) as pool:
                bodies = list(pool.map(lambda _: collect_json(24, False), range(24)))
            alternate = collect_json(24, True)

        self.assertEqual(1, calls.count((24, False)))
        self.assertEqual(1, calls.count((24, True)))
        self.assertEqual(1, len(set(bodies)))
        self.assertNotEqual(bodies[0], alternate)
        self.assertEqual(2, len(state_of().collect_memo))

    def test_a_requested_window_reaches_the_collection_and_its_memo_key(self) -> None:
        # The window is a request-time argument: /api/data must collect and
        # report the window it was asked for, not the configured default.
        # Mutation-checked: dropping build_app()'s window override, so every
        # request silently used the configured window, passed the suite.
        with mock.patch.object(aggregate, "default_harnesses", lambda _notifier: ()):
            requested = json.loads(collect_json(6, False))
            default = json.loads(collect_json(24, False))

            self.assertEqual(6, requested["window_hours"])
            self.assertEqual(24, default["window_hours"])
            self.assertIn((6, False), state_of().collect_memo)
            self.assertIn((24, False), state_of().collect_memo)

    def test_collector_failure_is_exposed_in_harness_status(self) -> None:
        def fail(*_args: object) -> list[dict[str, Any]]:
            raise RuntimeError("broken store")

        harnesses = (aggregate.HarnessSpec("test", "Test", lambda _config, _state: True, fail),)
        with (
            mock.patch.object(aggregate, "default_harnesses", lambda _notifier: harnesses),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            result = collect(24, False)

        self.assertTrue(result["harnesses"][0]["discovered"])
        self.assertEqual("RuntimeError: broken store", result["harnesses"][0]["error"])

    def test_health_reports_identity_without_scanning_any_store(self) -> None:
        httpd = make_server()
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            # The readiness wait and --status poll this in a loop. If it ever
            # reaches collect(), a liveness check costs a full multi-harness
            # filesystem scan.
            with mock.patch.object(aggregate.Application, "collect") as collect:
                conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=2)
                conn.request("GET", "/api/health")
                response = conn.getresponse()
                status = response.status
                payload = json.loads(response.read())
                conn.close()
            collect.assert_not_called()
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)
        self.assertEqual(200, status)
        self.assertTrue(payload["ok"])
        self.assertEqual(os.getpid(), payload["pid"])
        self.assertEqual(httpd.server_port, payload["port"])
        self.assertIsInstance(payload["started"], (int, float))

    def test_health_is_refused_from_a_non_local_host_header(self) -> None:
        httpd = make_server()
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=2)
            conn.putrequest("GET", "/api/health", skip_host=True)
            conn.putheader("Host", "evil.example")
            conn.endheaders()
            response = conn.getresponse()
            self.assertEqual(403, response.status)
            response.read()
            conn.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)


class HostAndSocketTest(unittest.TestCase):
    def test_host_header_forms_that_are_all_loopback(self) -> None:
        # rsplit(":", 1) mangled the bracketed IPv6 form into "[:" and never
        # folded case, so both were rejected as non-local.
        for value in (
            "127.0.0.1",
            "127.0.0.1:4553",
            "localhost",
            "LOCALHOST",
            "LocalHost:4553",
            "[::1]",
            "[::1]:4553",
            "::1",
        ):
            with self.subTest(host=value):
                self.assertIn(http_api.normalize_host(value), http_api._RequestHandler.LOCAL_HOSTS)

    def test_host_header_forms_that_are_not_loopback(self) -> None:
        for value in (
            "",
            "evil.example",
            "evil.example:4553",
            "127.0.0.1.evil.example",
            "[",
            "[]",
            "192.168.1.5",
            # Only a port may follow a bracketed literal. Ignoring the rest
            # made "[::1]evil.example" reduce to "::1" and pass as loopback.
            "[::1]evil.example",
            "[::1]xyz:99",
            "[::1].",
            "[::1]:notaport",
            # Unbracketed authorities need the same port validation, or
            # "localhost:evil.example" reduces to "localhost".
            "localhost:evil.example",
            "127.0.0.1:evil.example",
            "localhost:",
        ):
            with self.subTest(host=value):
                self.assertNotIn(
                    http_api.normalize_host(value), http_api._RequestHandler.LOCAL_HOSTS
                )

    def test_reuse_address_is_off_only_on_windows(self) -> None:
        # POSIX: SO_REUSEADDR just bypasses TIME_WAIT, so restarts work.
        # Windows: it lets a second process bind an already-bound port.
        self.assertTrue(http_api.reuse_address_allowed("posix"))
        self.assertFalse(http_api.reuse_address_allowed("nt"))

    def test_bind_errors_explain_themselves(self) -> None:
        in_use = OSError(errno.EADDRINUSE, "Address already in use")
        self.assertIn("already in use", http_api.bind_error_message(in_use, 4553))
        self.assertIn("4553", http_api.bind_error_message(in_use, 4553))
        denied = OSError(errno.EACCES, "Permission denied")
        self.assertIn("not permitted", http_api.bind_error_message(denied, 4553))
        other = OSError(errno.EINVAL, "Invalid argument")
        self.assertIn("cannot bind", http_api.bind_error_message(other, 4553))

    def test_windows_error_codes_are_recognized(self) -> None:
        # winerror, not errno, is what Windows populates. 10013 is also what an
        # in-use port reports once SO_EXCLUSIVEADDRUSE is set.
        for winerror, expected in ((10048, "already in use"), (10013, "not permitted")):
            with self.subTest(winerror=winerror):
                exc = OSError()
                exc.winerror = winerror  # type: ignore[attr-defined]
                self.assertIn(expected, http_api.bind_error_message(exc, 4553))

    def test_server_binds_and_serves(self) -> None:
        httpd = make_server()
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)
            conn.request("GET", "/api/data")
            response = conn.getresponse()
            self.assertEqual(200, response.status)
            response.read()
            conn.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)


class ReviewFixTest(unittest.TestCase):
    """Regressions found by the adversarial review passes on PR #7."""

    NOW = 1_700_000_000.0

    def test_a_page_on_another_local_port_cannot_post(self) -> None:
        # Every port on this machine is the same *site*, so Sec-Fetch-Site says
        # "same-site" for a page served from another local port. A hostname-only
        # Origin check trusted it, and text/plain is CORS-safelisted so no
        # preflight would have stopped the request.
        httpd = make_server()
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        port = httpd.server_port
        cases = [
            (f"http://127.0.0.1:{port}", 200, "the dashboard's own page"),
            (f"http://localhost:{port}", 200, "same port, other spelling"),
            ("http://localhost:9999", 403, "another local dev server"),
            ("http://127.0.0.1:9999", 403, "another local port"),
            ("http://localhost", 403, "port 80"),
            ("https://evil.example", 403, "remote origin"),
        ]
        try:
            for origin, expected, why in cases:
                with self.subTest(why=why):
                    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                    conn.request(
                        "POST",
                        "/api/notify",
                        body=b'{"session_id":"aaaaaaaa"}',
                        headers={"Origin": origin, "Content-Type": "text/plain"},
                    )
                    response = conn.getresponse()
                    self.assertEqual(expected, response.status)
                    response.read()
                    conn.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def _options_requested(self, os_name: str, exclusive_option: int) -> list[int]:
        """Socket options the listener asks for under a given configured OS."""
        options: list[int] = []
        real_setsockopt = socket.socket.setsockopt

        def traced_setsockopt(sock: Any, level: int, option: int, value: Any) -> Any:
            options.append(option)
            return real_setsockopt(sock, level, option, value)

        with (
            mock.patch.object(socket.socket, "setsockopt", traced_setsockopt),
            mock.patch.object(socket, "SO_EXCLUSIVEADDRUSE", exclusive_option, create=True),
            # The fake option number is rejected by the OS, so that path warns;
            # silence it here.
            mock.patch.object(runtime_io, "diag"),
        ):
            httpd = make_server(application=_application(os_name))
            httpd.server_close()
        return options

    def test_reuse_and_exclusive_options_are_never_both_requested(self) -> None:
        # Winsock rejects SO_REUSEADDR on a socket that already carries
        # SO_EXCLUSIVEADDRUSE (WSAEINVAL 10022), so these are complements of one
        # decision, not independent switches. Taking reuse from the config while
        # taking exclusivity from the host's socket module set BOTH on a Windows
        # host running a posix-configured application, and every bind there died
        # — including the two-server and health-stamp contracts below, which say
        # nothing about ports and were failing on Windows for this reason alone.
        exclusive = 0xFFFB
        posix = self._options_requested("posix", exclusive)
        windows = self._options_requested("nt", exclusive)

        self.assertIn(socket.SO_REUSEADDR, posix)
        self.assertNotIn(exclusive, posix)

        self.assertIn(exclusive, windows)
        self.assertNotIn(socket.SO_REUSEADDR, windows)

    def test_exclusive_port_option_is_requested_before_bind(self) -> None:
        # Clearing SO_REUSEADDR stops Cargento hijacking someone else's port;
        # SO_EXCLUSIVEADDRUSE is what stops anyone hijacking Cargento's. Only
        # meaningful if it is applied before bind(). The config has to say "nt"
        # for the option to be in play at all, so the assertion holds on every
        # host rather than only on Windows runners.
        order: list[str] = []
        real_setsockopt = socket.socket.setsockopt
        real_bind = socket.socket.bind

        def traced_setsockopt(self: Any, level: int, option: int, value: Any) -> Any:
            order.append(f"setsockopt:{option}")
            return real_setsockopt(self, level, option, value)

        def traced_bind(self: Any, address: Any) -> Any:
            order.append("bind")
            return real_bind(self, address)

        with (
            mock.patch.object(socket.socket, "setsockopt", traced_setsockopt),
            mock.patch.object(socket.socket, "bind", traced_bind),
            mock.patch.object(socket, "SO_EXCLUSIVEADDRUSE", 0xFFFB, create=True),
            # The fake option number is rejected by the OS, so that path warns;
            # silence it here.
            mock.patch.object(runtime_io, "diag"),
        ):
            httpd = make_server(application=_application("nt"))
            httpd.server_close()

        self.assertIn("setsockopt:65531", order)
        self.assertEqual("bind", order[-1], "options must be set before bind()")
        self.assertLess(order.index("setsockopt:65531"), order.index("bind"))

    def test_shutdown_endpoint_answers_before_it_stops_the_server(self) -> None:
        httpd = make_server()
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)
            conn.request("POST", "/api/shutdown", body=b"", headers={"Content-Length": "0"})
            response = conn.getresponse()
            # This proves the client gets a 200 and that the server actually
            # stops (via the join/is_alive check below) — it does not pin how
            # shutdown is implemented, e.g. that it must run on its own thread.
            self.assertEqual(200, response.status)
            self.assertEqual(b'{"ok":true,"stopping":true}', response.read())
            conn.close()
            thread.join(timeout=10)
            self.assertFalse(thread.is_alive(), "serve_forever did not return")
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_shutdown_still_runs_when_the_client_drops_during_the_reply(self) -> None:
        handler = object.__new__(http_api._RequestHandler)
        handler.server = mock.Mock()
        handler.wfile = mock.Mock()
        stopped = threading.Event()
        handler.server.shutdown.side_effect = stopped.set
        with mock.patch.object(handler, "_send", side_effect=BrokenPipeError):
            handler._shutdown()
        self.assertTrue(stopped.wait(timeout=2), "the failed reply cancelled the shutdown")
        handler.server.shutdown.assert_called_once_with()

    def test_shutdown_endpoint_refuses_a_cross_site_post(self) -> None:
        httpd = make_server()
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=2)
            conn.request(
                "POST",
                "/api/shutdown",
                body=b"",
                headers={"Content-Length": "0", "Sec-Fetch-Site": "cross-site"},
            )
            response = conn.getresponse()
            self.assertEqual(403, response.status)
            response.read()
            conn.close()
            # Still serving: a refused stop must not stop anything.
            conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=2)
            conn.request("GET", "/api/health")
            self.assertEqual(200, conn.getresponse().status)
            conn.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)


class VerificationFixTest(unittest.TestCase):
    """Regressions found by the adversarial pass that tried to refute the fixes."""

    NOW = 1_700_000_000.0

    FUTURE = NOW + 86_400

    def test_origin_with_an_implicit_default_port(self) -> None:
        # Browsers omit the port when it is the scheme default, so
        # "http://localhost" is legitimate for a server on port 80.
        handler = http_api._RequestHandler.__new__(http_api._RequestHandler)
        handler.headers = email.message.Message()
        handler.headers["Host"] = "localhost"
        handler.headers["Origin"] = "http://localhost"
        handler.server = mock.Mock(server_port=80)
        self.assertTrue(handler._local_ok())
        handler.server = mock.Mock(server_port=4553)
        self.assertFalse(handler._local_ok())


class InstalledContractCharacterizationTest(unittest.TestCase):
    """The installed executable contract that extraction must preserve."""

    def setUp(self) -> None:
        with state_of().hook_lock:
            state_of().hook_notifications.clear()
            state_of().last_popup.clear()
            state_of().last_popup_message.clear()
            state_of().last_session_state.clear()
            state_of().hook_generation.clear()
        with state_of().collect_memo_lock:
            state_of().collect_memo.clear()
        # Route-shape tests exercise successful /api/notify requests, but do
        # not assert native delivery. Execute the notification code while
        # keeping its osascript process off the host.
        original_run = subprocess.run

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
            subprocess, "run", side_effect=run_without_native_delivery
        )
        notify_patcher.start()
        self.addCleanup(notify_patcher.stop)

    def tearDown(self) -> None:
        with state_of().collect_memo_lock:
            state_of().collect_memo.clear()

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

    def test_http_routes_pin_status_content_type_and_response_shapes(self) -> None:
        httpd = make_server()
        thread = serve_until_closed(httpd)
        # Patched on the application, which is what the handler collects through.
        with mock.patch.object(
            aggregate.Application,
            "collect_json",
            return_value=json.dumps({"generated": 1.0, "sessions": [], "harnesses": []}).encode(),
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
                        if path == "/":
                            self.assertEqual(PAGE_BYTES, received)
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
        captured_pages: list[bytes] = []

        class StopServingError(Exception):
            pass

        class CapturingServer:
            def __init__(
                self,
                address: tuple[str, int],
                _application: Any,
                page_bytes: bytes,
            ) -> None:
                captured_addresses.append(address)
                captured_pages.append(page_bytes)

            def serve_forever(self) -> None:
                raise StopServingError

            def server_close(self) -> None:
                pass

        # The shipped launcher, rather than this test's fixture, owns the
        # required bind address. Capture the constructor call from main() so a
        # regression to 0.0.0.0 cannot pass merely because this test chose 127.
        with (
            mock.patch.object(sys, "argv", ["server.py", "--port", "4553"]),
            mock.patch.object(http_api, "CargentoHTTPServer", CapturingServer),
            mock.patch.object(lifecycle, "write_state"),
            mock.patch.object(lifecycle, "remove_state"),
            mock.patch.object(runtime_io, "diag"),
            self.assertRaises(StopServingError),
        ):
            cli.main()
        self.assertEqual([("127.0.0.1", 4553)], captured_addresses)
        self.assertEqual([PAGE_BYTES], captured_pages)

        httpd = make_server()
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
        httpd = make_server()
        thread = serve_until_closed(httpd)
        try:
            # These are the store-access primitives used by collectors. Health
            # must remain a pure liveness response even if somebody bypasses
            # collect() and later reaches into a harness store directly.
            with (
                mock.patch.object(aggregate.Application, "collect") as collect,
                mock.patch("builtins.open", side_effect=AssertionError("health read a file")),
                mock.patch.object(
                    os,
                    "scandir",
                    side_effect=AssertionError("health scanned a directory"),
                ),
                mock.patch(
                    "cargento_runtime.io.glob.glob",
                    side_effect=AssertionError("health globbed a store"),
                ),
                mock.patch.object(
                    runtime_io.sqlite_module,
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

        def scan(*_: Any, **__: Any) -> dict[str, Any]:
            entered.set()
            self.assertTrue(release.wait(timeout=5), "test did not release the scan")
            return {"generated": 1.0, "sessions": [], "harnesses": []}

        def second_request() -> None:
            bodies.append(collect_json(24, False))
            second_done.set()

        with mock.patch.object(aggregate.Application, "collect", side_effect=scan) as collect:
            first = threading.Thread(target=lambda: bodies.append(collect_json(24, False)))
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
            aggregate.Application, "collect", side_effect=(RuntimeError("broken store"), good)
        ):
            with self.assertRaisesRegex(RuntimeError, "broken store"):
                collect_json(24, False)
            self.assertEqual(good, json.loads(collect_json(24, False)))
