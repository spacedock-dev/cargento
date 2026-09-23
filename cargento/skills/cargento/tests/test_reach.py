"""Unit tests for the off-machine reach nudge module (DRC-4034, DEC-4)."""

from __future__ import annotations

import http.server
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from unittest import mock

from cargento_runtime import reach
from cargento_runtime.config import build_runtime_config
from cargento_runtime.state import build_runtime_state

from .support import poll_fast


def make_config(**overrides: Any) -> Any:
    state_dir = overrides.pop("state_dir", None) or tempfile.mkdtemp()
    environ = {"CARGENTO_HOME": state_dir}
    return build_runtime_config(
        environ=environ,
        platform_name="darwin",
        os_name="posix",
        launcher_path=Path("/path/to/server.py"),
        **overrides,
    )


class MockReachServer(http.server.HTTPServer):
    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _MockReachHandler)
        self.received_requests: list[dict[str, Any]] = []


class _MockReachHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        server: MockReachServer = self.server  # type: ignore[assignment]
        server.received_requests.append(
            {
                "path": self.path,
                "headers": dict(self.headers),
                "body": body,
                "json": json.loads(body.decode("utf-8")),
            }
        )
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok": true}')


class ReachNudgeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.server = MockReachServer()
        self.server_thread = threading.Thread(target=poll_fast(self.server), daemon=True)
        self.server_thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/webhook"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def test_payload_contains_strictly_counts_and_no_other_fields(self) -> None:
        payload_bytes = reach.format_reach_payload(needs_input=3, finished_unread=2)
        parsed = json.loads(payload_bytes.decode("utf-8"))
        self.assertEqual(parsed, {"needs_input": 3, "finished_unread": 2})
        self.assertEqual(set(parsed.keys()), {"needs_input", "finished_unread"})

    def test_opener_disables_proxies_and_refuses_redirects(self) -> None:
        with mock.patch("urllib.request.build_opener") as mock_build:
            reach.build_reach_opener()
            mock_build.assert_called_once()
            args = mock_build.call_args[0]
            proxies = [h for h in args if isinstance(h, urllib.request.ProxyHandler)]
            self.assertEqual(len(proxies), 1)
            self.assertEqual(getattr(proxies[0], "proxies", None), {})
            self.assertIn(reach._NoRedirects, args)
            no_redirect = reach._NoRedirects()
            req = mock.MagicMock()
            self.assertIsNone(no_redirect.redirect_request(req, None, 302, "Found", {}, "http://x"))

    def test_resolve_reach_url_from_config(self) -> None:
        cfg = make_config(reach_url=self.url)
        self.assertEqual(reach.resolve_reach_url(cfg), self.url)

    def test_resolve_reach_url_from_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = make_config(state_dir=td)
            url_file = os.path.join(td, "reach_url")
            with open(url_file, "w", encoding="utf-8") as f:
                f.write(f"  {self.url}\n")
            self.assertEqual(reach.resolve_reach_url(cfg), self.url)

    def test_no_reach_switch_disables_url_resolution(self) -> None:
        cfg = make_config(reach_url=self.url, reach_enabled=False)
        self.assertIsNone(reach.resolve_reach_url(cfg))

    def test_nudge_delivered_when_active_session_enters_needs_input(self) -> None:
        cfg = make_config(reach_url=self.url)
        state = build_runtime_state(cfg, started=100.0)
        sessions = [
            {"sid": "s1", "harness": "claude", "active": True, "state": "needs_input"},
            {"sid": "s2", "harness": "claude", "active": True, "state": "working"},
        ]
        sent = reach.maybe_reach_nudge(cfg, state, sessions, now=100.0)
        self.assertTrue(sent)
        self.assertEqual(len(self.server.received_requests), 1)
        req = self.server.received_requests[0]
        self.assertEqual(req["json"], {"needs_input": 1, "finished_unread": 0})
        self.assertEqual(req["headers"]["Content-Type"], "application/json")

    def test_nudge_throttled_by_cooldown_interval(self) -> None:
        cfg = make_config(reach_url=self.url, reach_cooldown_sec=60.0)
        state = build_runtime_state(cfg, started=100.0)
        sessions1 = [
            {"sid": "s1", "harness": "claude", "active": True, "state": "needs_input"},
        ]
        self.assertTrue(reach.maybe_reach_nudge(cfg, state, sessions1, now=100.0))
        self.assertEqual(len(self.server.received_requests), 1)

        # Same counts within cooldown -> no post
        self.assertFalse(reach.maybe_reach_nudge(cfg, state, sessions1, now=110.0))
        self.assertEqual(len(self.server.received_requests), 1)

        # Different counts within cooldown -> throttled, no post yet
        sessions2 = [
            {"sid": "s1", "harness": "claude", "active": True, "state": "needs_input"},
            {"sid": "s2", "harness": "codex", "active": True, "state": "needs_input"},
        ]
        self.assertFalse(reach.maybe_reach_nudge(cfg, state, sessions2, now=120.0))
        self.assertEqual(len(self.server.received_requests), 1)

        # Cooldown elapsed -> post sent with updated counts
        self.assertTrue(reach.maybe_reach_nudge(cfg, state, sessions2, now=165.0))
        self.assertEqual(len(self.server.received_requests), 2)
        self.assertEqual(
            self.server.received_requests[1]["json"], {"needs_input": 2, "finished_unread": 0}
        )

    def test_no_reach_flag_never_attempts_post(self) -> None:
        cfg = make_config(reach_url=self.url, reach_enabled=False)
        state = build_runtime_state(cfg, started=100.0)
        sessions = [
            {"sid": "s1", "harness": "claude", "active": True, "state": "needs_input"},
        ]
        sent = reach.maybe_reach_nudge(cfg, state, sessions, now=100.0)
        self.assertFalse(sent)
        self.assertEqual(len(self.server.received_requests), 0)

    def test_diagnostics_sink_never_leaks_credential_url(self) -> None:
        diagnostics: list[str] = []
        cfg = make_config(reach_url="http://127.0.0.1:1/invalid_secret_token_12345")
        state = build_runtime_state(cfg, started=100.0)
        sessions = [
            {"sid": "s1", "harness": "claude", "active": True, "state": "needs_input"},
        ]
        sent = reach.maybe_reach_nudge(
            cfg,
            state,
            sessions,
            now=100.0,
            diagnostic_sink=diagnostics.append,
        )
        self.assertFalse(sent)
        combined_logs = " ".join(diagnostics)
        self.assertNotIn("invalid_secret_token_12345", combined_logs)
