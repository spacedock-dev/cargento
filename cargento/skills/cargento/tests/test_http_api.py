from __future__ import annotations

import contextlib
import dataclasses
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
from pathlib import Path
from typing import Any
from unittest import mock

from cargento_runtime import aggregate, cli, http_api, lifecycle, notifications
from cargento_runtime import io as runtime_io
from cargento_runtime import observation as observation_module

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
        # Both variants are published, separately, into the runtime's snapshot.
        snap = state_of().snapshot
        self.assertIsNotNone(snap.current((24, False)))
        self.assertIsNotNone(snap.current((24, True)))

    @staticmethod
    def _get_headers(port: int, path: str) -> tuple[int, email.message.Message, bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.request("GET", path)
            response = conn.getresponse()
            return response.status, response.headers, response.read()
        finally:
            conn.close()

    def test_api_data_names_the_revision_it_served(self) -> None:
        """A client cannot hold a cursor it cannot see.

        The revision rides in a header, not the body, so the documented JSON
        contract and every curl caller are untouched.
        """
        httpd = make_server()
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            port = httpd.server_port
            _code, headers, body = self._get_headers(port, "/api/data")
            first = headers["X-Cargento-Revision"]
            self.assertRegex(first, r"^\d+\.\d+$")
            # The body still parses and still carries its documented keys.
            payload = json.loads(body)
            self.assertIn("sessions", payload)
            self.assertIn("generated", payload)
            # A warm re-read serves the same revision.
            _code, headers, _body = self._get_headers(port, "/api/data")
            self.assertEqual(first, headers["X-Cargento-Revision"])
            # A stale read mints a higher counter against the same start stamp.
            state_of().snapshot.clear()
            _code, headers, _body = self._get_headers(port, "/api/data")
            second = headers["X-Cargento-Revision"]
            self.assertEqual(first.split(".")[0], second.split(".")[0])
            self.assertGreater(int(second.split(".")[1]), int(first.split(".")[1]))
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_only_api_data_carries_a_revision(self) -> None:
        """A page load or a liveness probe must not look like a cursor."""
        httpd = make_server()
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            for path in ("/", "/api/health"):
                with self.subTest(path=path):
                    _code, headers, _body = self._get_headers(httpd.server_port, path)
                    self.assertIsNone(headers.get("X-Cargento-Revision"))
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_a_requested_window_reaches_the_collection_and_its_memo_key(self) -> None:
        # The window is a request-time argument: /api/data must collect and
        # report the window it was asked for, not the configured default.
        # Mutation-checked: dropping build_app()'s window override, so every
        # request silently used the configured window, passed the suite.
        with mock.patch.object(aggregate, "default_harnesses", lambda _notifier, **_kw: ()):
            requested = json.loads(collect_json(6, False))
            default = json.loads(collect_json(24, False))

            self.assertEqual(6, requested["window_hours"])
            self.assertEqual(24, default["window_hours"])
            snap = state_of().snapshot
            self.assertIsNotNone(snap.current((6, False)))
            self.assertIsNotNone(snap.current((24, False)))

    def test_collector_failure_is_exposed_in_harness_status(self) -> None:
        def fail(*_args: object) -> list[dict[str, Any]]:
            raise RuntimeError("broken store")

        harnesses = (aggregate.HarnessSpec("test", "Test", lambda _config, _state: True, fail),)
        with (
            mock.patch.object(aggregate, "default_harnesses", lambda _notifier, **_kw: harnesses),
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


class OverlayLedgerEndpointTest(RuntimeTestCase):
    """`/api/overlays`: the reducer's inputs, for a row `/api/data` cannot explain."""

    @staticmethod
    @contextlib.contextmanager
    def _serving(observation: Any) -> Any:
        httpd = make_server(observation=observation)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield httpd.server_port
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    @staticmethod
    def _get(port: int, headers: dict[str, str] | None = None) -> tuple[int, bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.request("GET", "/api/overlays", headers=headers or {})
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def test_the_ledger_is_served_as_json(self) -> None:
        coordinator = observation_module.Observation(
            _application(os.name), diagnostic_sink=lambda _message: None
        )
        coordinator.submit(
            "claude",
            {
                "v": 1,
                "event": "input_requested",
                "session_id": "abcdef12-3456-7890-abcd-ef1234567890",
            },
        )
        with self._serving(coordinator) as port:
            code, body = self._get(port)
        self.assertEqual(200, code)
        report = json.loads(body)
        self.assertEqual(["needs_input"], [row["kind"] for row in report["overlays"]])
        self.assertEqual("abcdef12", report["overlays"][0]["sid"])

    def test_recorded_disputes_are_served_beside_the_ledger(self) -> None:
        # One request, not two: a dispute is read against the ledger that
        # produced it, and two requests would be two instants.
        coordinator = observation_module.Observation(
            _application(os.name), diagnostic_sink=lambda _message: None
        )
        state = state_of()
        state.dispute_total = 3
        state.disputes.append({"sid": "abcdef12", "collector_state": "needs_input"})
        with self._serving(coordinator) as port:
            code, body = self._get(port)
        self.assertEqual(200, code)
        report = json.loads(body)
        self.assertEqual(3, report["dispute_total"], "the total outlives the ring")
        self.assertEqual(["abcdef12"], [row["sid"] for row in report["disputes"]])
        self.assertIn("overlays", report, "the ledger still rides in the same response")

    def test_no_coordinator_answers_503_rather_than_404(self) -> None:
        # Under `--no-events` the route exists and the ledger does not. A 404
        # would read as a build too old to have the route, which is the wrong
        # thing to conclude while debugging a missing overlay.
        with self._serving(None) as port:
            code, _body = self._get(port)
        self.assertEqual(503, code)

    def test_a_cross_site_navigation_is_refused_unlike_api_data(self) -> None:
        # `do_GET` relaxes its check so a link to the dashboard works. Nothing
        # renders this route, so the relaxation has no reason to reach it.
        with self._serving(None) as port:
            code, _body = self._get(
                port,
                {
                    "Sec-Fetch-Site": "cross-site",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Dest": "document",
                },
            )
        self.assertEqual(403, code)


class UsageReceiptOptOutTest(RuntimeTestCase):
    """POST /api/usage honours the server-side usage opt-out.

    `test_quota.PushedReceiptOptOutTest` covers the gate itself. This covers the
    wiring, which is the half a refactor drops without any unit test noticing:
    the handler has to hand its application's config to the shaping call.
    """

    def _post(self, port: int, body: bytes) -> tuple[int, bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.request(
                "POST", "/api/usage", body=body, headers={"Content-Type": "application/json"}
            )
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def test_pushed_quota_is_discarded_when_usage_is_disabled(self) -> None:
        config, state = make_runtime(usage_fetch_enabled=False)
        application = cli.build_application(config, state, clock=time.time)
        httpd = make_server(application=application)
        thread = serve_until_closed(httpd)
        try:
            status, body = self._post(
                httpd.server_port,
                json.dumps({"quota": {"gemini-5h": {"remaining_fraction": 0.3}}}).encode(),
            )
        finally:
            httpd.shutdown()
            thread.join(timeout=5)
        # 200 on purpose: a status-line command must never see an error.
        self.assertEqual(200, status)
        self.assertEqual(b'{"ok":true,"usage":0}', body)
        self.assertEqual([], state.usage_receipts["antigravity"]["entries"])


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


class RejectedPostDrainTest(unittest.TestCase):
    """A refused POST has its body read before the refusal is written.

    Closing a socket that still holds unread inbound data makes the OS send RST
    rather than FIN, and an RST can discard the reply already written, so the
    client sees ECONNRESET (WSAECONNABORTED on Windows) instead of the 413 it was
    told to expect. That is what failed on the macOS and Windows runners.

    Asserted at the handler rather than through a socket, deliberately. A
    socket-level version of this passes on this machine whether or not the drain
    is there, because the race needs buffer and scheduling conditions a local run
    does not reproduce: it would be a test that cannot fail. Reading the body
    before answering is the behaviour being added, so that is what is pinned.
    """

    class _Handler(http_api._RequestHandler):
        def __init__(self, declared: str, available: bytes) -> None:
            # Headers is an email.message.Message on the real handler; a dict
            # answers the only call the drain makes of it.
            self.headers = email.message.Message()
            self.headers["Content-Length"] = declared
            self.rfile = io.BytesIO(available)
            self.sent: list[int] = []

        def send_error(
            self, code: int, message: str | None = None, explain: str | None = None
        ) -> None:
            # Records the order: the drain has to have happened by now.
            del message, explain
            self.sent.append(code)

    def _reject(self, declared: str, available: bytes) -> tuple[list[int], int]:
        handler = self._Handler(declared, available)
        handler._reject(413)
        return handler.sent, handler.rfile.tell()

    def test_the_declared_body_is_consumed_before_the_error_is_sent(self) -> None:
        sent, consumed = self._reject("2048", b"a" * 2048)
        self.assertEqual([413], sent)
        self.assertEqual(2048, consumed, "the body must be read, or the close sends RST")

    def test_an_oversized_declared_length_is_drained_only_to_the_bound(self) -> None:
        """Bounded: a refusal must not become an unbounded read."""
        cap = http_api._RequestHandler.REJECT_DRAIN_CAP_BYTES
        sent, consumed = self._reject(str(cap * 4), b"b" * (cap + 100))
        self.assertEqual([413], sent)
        self.assertEqual(cap, consumed, "never more than the bound, whatever is declared")

    def test_a_body_shorter_than_declared_does_not_hang(self) -> None:
        """A peer that declares more than it sends must not block the handler.

        BytesIO reports end of stream immediately; a real socket blocks instead,
        which is why the drain is also bounded by a deadline. The socket case is
        covered by test_a_declared_body_never_sent_does_not_stall below.
        """
        sent, consumed = self._reject("100000", b"c" * 10)
        self.assertEqual([413], sent)
        self.assertEqual(10, consumed)

    def test_a_missing_or_unparseable_length_reads_nothing(self) -> None:
        for declared in ("", "not-a-number"):
            with self.subTest(declared=declared):
                sent, consumed = self._reject(declared, b"d" * 50)
                self.assertEqual([413], sent)
                self.assertEqual(0, consumed)

    def test_a_declared_body_never_sent_does_not_stall(self) -> None:
        """The bug my first fix introduced, over a real socket.

        A peer that declares a length and sends nothing made the drain block on
        read1 until the connection timeout, which turned a refusal into a
        five-second hang. A request-limit test sends exactly that shape on
        purpose, so this is a real caller and not a hypothetical one.
        """
        httpd = make_server()
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            started = time.monotonic()
            conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=10)
            try:
                # Declare a body, send none: putrequest/endheaders without a send.
                conn.putrequest("POST", "/api/notify")
                # Above notification_body_cap_bytes, so this takes the rejection
                # path. A declared length UNDER the cap is a different case: the
                # accept path reads it and blocks, which is pre-existing
                # behaviour and not what this test is about.
                conn.putheader("Content-Length", "200000")
                conn.putheader("Content-Type", "application/json")
                conn.endheaders()
                response = conn.getresponse()
                self.assertEqual(413, response.status)
                response.read()
            finally:
                conn.close()
            elapsed = time.monotonic() - started
            self.assertLess(
                elapsed,
                3.0,
                f"a refusal must not wait out the connection timeout, took {elapsed:.1f}s",
            )
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_every_post_rejection_path_drains(self) -> None:
        """The whole class of bug, not the one instance that was reported."""
        source = Path(http_api.__file__).read_text(encoding="utf-8")
        post_region = source[source.index("    def _usage_receipt") :]
        self.assertNotIn(
            "self.send_error(",
            post_region,
            "a POST path answering with send_error instead of _reject will strand its peer",
        )


class StreamEndpointTest(RuntimeTestCase):
    """The SSE contract: immediate state, then one event per revision.

    Every socket read carries a timeout. A blocking read with no deadline turns
    a Windows CI failure into a hang, which reads as infrastructure trouble
    rather than as the bug it is.
    """

    @staticmethod
    def _open(port: int, headers: dict[str, str] | None = None) -> Any:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/api/stream", headers=headers or {})
        return conn, conn.getresponse()

    @staticmethod
    def _read_event(response: Any, *, limit: int = 4096) -> str:
        """Read until a blank line terminates one SSE frame, or the peer ends."""
        chunks: list[bytes] = []
        while len(b"".join(chunks)) < limit:
            byte = response.read(1)
            if not byte:
                break
            chunks.append(byte)
            if b"".join(chunks).endswith(b"\n\n"):
                break
        return b"".join(chunks).decode()

    def test_the_stream_opens_as_an_event_stream(self) -> None:
        httpd = make_server()
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            conn, response = self._open(httpd.server_port)
            try:
                self.assertEqual(200, response.status)
                self.assertEqual("text/event-stream", response.headers["Content-Type"])
                self.assertEqual("no-store", response.headers["Cache-Control"])
            finally:
                conn.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_the_current_revision_arrives_immediately(self) -> None:
        """A client must not wait for the next change to learn where it is."""
        httpd = make_server()
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            # Publish something first, so there is a current revision to send.
            httpd.application.collect_json(show_all=False)
            conn, response = self._open(httpd.server_port)
            try:
                frame = self._read_event(response)
                self.assertIn("event: revision", frame)
                self.assertRegex(frame, r"data: \d+\.\d+")
            finally:
                conn.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_a_new_revision_is_delivered_to_an_open_stream(self) -> None:
        httpd = make_server()
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            httpd.application.collect_json(show_all=False)
            conn, response = self._open(httpd.server_port)
            try:
                first = self._read_event(response)
                # Force a genuinely new revision, then read the next frame.
                state_of().snapshot.clear()
                httpd.application.collect_json(show_all=False)
                second = self._read_event(response)
                self.assertIn("event: revision", second)
                self.assertNotEqual(first, second)
            finally:
                conn.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_a_cross_site_request_is_refused_unlike_api_data(self) -> None:
        """A long-lived data stream is not a document navigation.

        do_GET relaxes its origin check so a link to the dashboard works. This
        route must re-check with the strict form, or that relaxation leaks onto
        a stream any site could open.
        """
        httpd = make_server()
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            conn, response = self._open(
                httpd.server_port,
                {
                    "Sec-Fetch-Site": "cross-site",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Dest": "document",
                },
            )
            try:
                self.assertEqual(403, response.status)
                response.read()
            finally:
                conn.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_the_budget_refuses_past_the_cap(self) -> None:
        """A refusal, not a queue: every stream costs a thread and a socket."""
        httpd = make_server()
        httpd.application.config = dataclasses.replace(
            httpd.application.config, stream_max_clients=1
        )
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            first_conn, first = self._open(httpd.server_port)
            try:
                self.assertEqual(200, first.status)
                second_conn, second = self._open(httpd.server_port)
                try:
                    self.assertEqual(503, second.status)
                    second.read()
                finally:
                    second_conn.close()
            finally:
                first_conn.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)


class StreamShutdownTest(RuntimeTestCase):
    """A stream asleep in wait() has to be woken, or shutdown looks like a hang.

    server.shutdown() stops the accept loop and never touches handler threads,
    and daemon_threads means nothing joins them, so nothing else would tell a
    sleeping stream to stop.
    """

    def test_shutdown_closes_an_open_stream_promptly(self) -> None:
        httpd = make_server()
        # A heartbeat far longer than the assertion window, so a pass cannot be
        # the heartbeat firing rather than the close.
        httpd.application.config = dataclasses.replace(
            httpd.application.config, stream_heartbeat_sec=60.0
        )
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=10)
            conn.request("GET", "/api/stream")
            response = conn.getresponse()
            self.assertEqual(200, response.status)
            ended = threading.Event()

            def drain() -> None:
                while response.read(1):
                    pass
                ended.set()

            reader = threading.Thread(target=drain, daemon=True)
            reader.start()
            httpd.application.state.streams.close_all()
            self.assertTrue(
                ended.wait(timeout=5.0),
                "an open stream must end when the registry closes it",
            )
            conn.close()
            reader.join(timeout=2)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_the_shutdown_endpoint_closes_streams_before_stopping(self) -> None:
        httpd = make_server()
        httpd.application.config = dataclasses.replace(
            httpd.application.config, stream_heartbeat_sec=60.0
        )
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            stream_conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=10)
            stream_conn.request("GET", "/api/stream")
            stream_response = stream_conn.getresponse()
            self.assertEqual(200, stream_response.status)
            ended = threading.Event()

            def drain() -> None:
                while stream_response.read(1):
                    pass
                ended.set()

            reader = threading.Thread(target=drain, daemon=True)
            reader.start()
            stop_conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=10)
            stop_conn.request("POST", "/api/shutdown", body=b"")
            stop_conn.getresponse().read()
            stop_conn.close()
            self.assertTrue(
                ended.wait(timeout=5.0),
                "POST /api/shutdown must wake open streams, not leave them asleep",
            )
            stream_conn.close()
            reader.join(timeout=2)
        finally:
            with contextlib.suppress(Exception):
                httpd.server_close()
            thread.join(timeout=2)


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
            state_of().snapshot.clear()
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
            state_of().snapshot.clear()

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
            # (revision, body): the handler names the revision it served in a
            # header, so the stub has to carry one too.
            return_value=(
                (1.0, 1),
                json.dumps({"generated": 1.0, "sessions": [], "harnesses": []}).encode(),
            ),
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
                _observation: Any = None,
            ) -> None:
                # The coordinator rides along as the fourth argument. Accepted and
                # ignored here: this test characterizes the bind address and the
                # page bytes, and a double that refused the argument would fail
                # for a reason that has nothing to do with either.
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
