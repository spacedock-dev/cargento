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
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from unittest import mock

from .support import (
    LegacyDashboardTestCase,
    dashboard,
)


class CargentoServerTest(LegacyDashboardTestCase):
    def test_notify_endpoint_accepts_valid_non_object_and_deep_json(self) -> None:
        httpd = dashboard.ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
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
            with mock.patch.object(dashboard, "notify_mac") as notify:
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
        httpd = dashboard.ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
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
        httpd = dashboard.ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
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

        def fake_collect(window_hours: float, show_all: bool) -> dict[str, Any]:
            with calls_lock:
                calls.append((window_hours, show_all))
            dashboard.time.sleep(0.02)
            return {"window_hours": window_hours, "show_all": show_all}

        with mock.patch.object(dashboard, "collect", fake_collect):
            with ThreadPoolExecutor(max_workers=12) as pool:
                bodies = list(pool.map(lambda _: dashboard.collect_json(24, False), range(24)))
            alternate = dashboard.collect_json(24, True)

        self.assertEqual(1, calls.count((24, False)))
        self.assertEqual(1, calls.count((24, True)))
        self.assertEqual(1, len(set(bodies)))
        self.assertNotEqual(bodies[0], alternate)
        self.assertEqual(2, len(dashboard._collect_memo))

    def test_collector_failure_is_exposed_in_harness_status(self) -> None:
        def fail(*_args: object) -> list[dict[str, Any]]:
            raise RuntimeError("broken store")

        harnesses = [("test", "Test", lambda: True, fail)]
        with (
            mock.patch.object(dashboard, "HARNESSES", harnesses),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            result = dashboard.collect(24, False)

        self.assertTrue(result["harnesses"][0]["discovered"])
        self.assertEqual("RuntimeError: broken store", result["harnesses"][0]["error"])

    def test_health_reports_identity_without_scanning_any_store(self) -> None:
        httpd = dashboard.ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            # The readiness wait and --status poll this in a loop. If it ever
            # reaches collect(), a liveness check costs a full multi-harness
            # filesystem scan.
            with mock.patch.object(dashboard, "collect") as collect:
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
        httpd = dashboard.ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
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
                self.assertIn(dashboard.normalize_host(value), dashboard.Handler.LOCAL_HOSTS)

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
                self.assertNotIn(dashboard.normalize_host(value), dashboard.Handler.LOCAL_HOSTS)

    def test_reuse_address_is_off_only_on_windows(self) -> None:
        # POSIX: SO_REUSEADDR just bypasses TIME_WAIT, so restarts work.
        # Windows: it lets a second process bind an already-bound port.
        self.assertTrue(dashboard.reuse_address_allowed("posix"))
        self.assertFalse(dashboard.reuse_address_allowed("nt"))

    def test_bind_errors_explain_themselves(self) -> None:
        in_use = OSError(errno.EADDRINUSE, "Address already in use")
        self.assertIn("already in use", dashboard.bind_error_message(in_use, 4553))
        self.assertIn("4553", dashboard.bind_error_message(in_use, 4553))
        denied = OSError(errno.EACCES, "Permission denied")
        self.assertIn("not permitted", dashboard.bind_error_message(denied, 4553))
        other = OSError(errno.EINVAL, "Invalid argument")
        self.assertIn("cannot bind", dashboard.bind_error_message(other, 4553))

    def test_windows_error_codes_are_recognized(self) -> None:
        # winerror, not errno, is what Windows populates. 10013 is also what an
        # in-use port reports once SO_EXCLUSIVEADDRUSE is set.
        for winerror, expected in ((10048, "already in use"), (10013, "not permitted")):
            with self.subTest(winerror=winerror):
                exc = OSError()
                exc.winerror = winerror  # type: ignore[attr-defined]
                self.assertIn(expected, dashboard.bind_error_message(exc, 4553))

    def test_server_binds_and_serves(self) -> None:
        httpd = dashboard.LoopbackHTTPServer(("127.0.0.1", 0), dashboard.Handler)
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
        httpd = dashboard.LoopbackHTTPServer(("127.0.0.1", 0), dashboard.Handler)
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

    def test_exclusive_port_option_is_requested_before_bind(self) -> None:
        # Clearing SO_REUSEADDR stops Cargento hijacking someone else's port;
        # SO_EXCLUSIVEADDRUSE is what stops anyone hijacking Cargento's. Only
        # meaningful if it is applied before bind().
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
            # The fake option number is rejected by the OS; that path warns,
            # which is correct behaviour but noise in the test output.
            mock.patch.object(dashboard, "diag"),
        ):
            httpd = dashboard.LoopbackHTTPServer(("127.0.0.1", 0), dashboard.Handler)
            httpd.server_close()

        self.assertIn("setsockopt:65531", order)
        self.assertEqual("bind", order[-1], "options must be set before bind()")
        self.assertLess(order.index("setsockopt:65531"), order.index("bind"))

    def test_shutdown_endpoint_answers_before_it_stops_the_server(self) -> None:
        httpd = dashboard.LoopbackHTTPServer(("127.0.0.1", 0), dashboard.Handler)
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
        handler = object.__new__(dashboard.Handler)
        handler.server = mock.Mock()
        handler.wfile = mock.Mock()
        stopped = threading.Event()
        handler.server.shutdown.side_effect = stopped.set
        with mock.patch.object(handler, "_send", side_effect=BrokenPipeError):
            handler._shutdown()
        self.assertTrue(stopped.wait(timeout=2), "the failed reply cancelled the shutdown")
        handler.server.shutdown.assert_called_once_with()

    def test_shutdown_endpoint_refuses_a_cross_site_post(self) -> None:
        httpd = dashboard.LoopbackHTTPServer(("127.0.0.1", 0), dashboard.Handler)
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
        handler = dashboard.Handler.__new__(dashboard.Handler)
        handler.headers = email.message.Message()
        handler.headers["Host"] = "localhost"
        handler.headers["Origin"] = "http://localhost"
        handler.server = mock.Mock(server_port=80)
        self.assertTrue(handler._local_ok())
        handler.server = mock.Mock(server_port=4553)
        self.assertFalse(handler._local_ok())
