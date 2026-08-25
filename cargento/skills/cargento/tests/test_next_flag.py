from __future__ import annotations

import contextlib
import http.client
import io
import os
import socket
import sys
import tempfile
import unittest
from typing import Any
from unittest import mock

from cargento_runtime import cli, lifecycle
from cargento_runtime.web import page as frontend_page

from .support import PAGE_BYTES, make_server, serve_until_closed

NEXT_BYTES = b"<html>next bundle</html>"


class NextPageFlagTest(unittest.TestCase):
    def _server(self, next_page_bytes: bytes | None) -> Any:
        try:
            return make_server(next_page_bytes=next_page_bytes)
        except TypeError as exc:
            self.fail(f"server factory does not accept next_page_bytes: {exc}")

    @staticmethod
    def _get(port: int, path: str) -> tuple[int, bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.request("GET", path)
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def test_the_unflagged_page_is_byte_identical_to_todays(self) -> None:
        httpd = self._server(NEXT_BYTES)
        thread = serve_until_closed(httpd)
        try:
            for path in (
                "/",
                "/?all=1",
                "/?next=false",
                "/?next=1",
                "/?next=TRUE",
                "/?nextish=true",
                "/?next=false&next=true",
            ):
                with self.subTest(path=path):
                    self.assertEqual((200, PAGE_BYTES), self._get(httpd.server_port, path))
        finally:
            httpd.shutdown()
            thread.join(timeout=5)

    def test_only_the_exact_string_true_serves_the_next_bundle(self) -> None:
        httpd = self._server(NEXT_BYTES)
        thread = serve_until_closed(httpd)
        try:
            for path in ("/?next=true", "/?next=true&next=false"):
                with self.subTest(path=path):
                    code, body = self._get(httpd.server_port, path)
                    self.assertEqual(200, code)
                    self.assertEqual(NEXT_BYTES, body)
                    self.assertNotEqual(PAGE_BYTES, body)
        finally:
            httpd.shutdown()
            thread.join(timeout=5)

    def test_a_missing_next_bundle_leaves_the_unflagged_page_serving(self) -> None:
        httpd = self._server(None)
        thread = serve_until_closed(httpd)
        try:
            next_code, _ = self._get(httpd.server_port, "/?next=true")
            self.assertEqual(503, next_code)
            self.assertEqual((200, PAGE_BYTES), self._get(httpd.server_port, "/"))
        finally:
            httpd.shutdown()
            thread.join(timeout=5)

    def test_shared_server_factory_serves_the_canonical_next_page_by_default(self) -> None:
        httpd = make_server()
        thread = serve_until_closed(httpd)
        try:
            self.assertEqual(
                (200, frontend_page.load_next_page()),
                self._get(httpd.server_port, "/?next=true"),
            )
        finally:
            httpd.shutdown()
            thread.join(timeout=5)


class NextPageCliBoundaryTest(unittest.TestCase):
    @staticmethod
    def _run_with_next_loader(next_loader: object) -> tuple[int, str, list[bytes | None]]:
        observed: list[bytes | None] = []

        def close_server(_config: object, server: Any, _port: int, **_kwargs: object) -> None:
            observed.append(server.next_page_bytes)
            server.server_close()

        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]

        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.dict(os.environ, {"CARGENTO_HOME": tmp}),
            mock.patch.object(sys, "argv", ["server.py", "--port", str(port), "--no-events"]),
            mock.patch.object(frontend_page, "load_next_page", side_effect=next_loader),
            mock.patch.object(lifecycle, "serve", side_effect=close_server),
            contextlib.redirect_stderr(io.StringIO()) as stderr,
        ):
            code = cli.main()
        return code, stderr.getvalue(), observed

    def test_a_broken_next_bundle_does_not_prevent_the_old_page_from_binding(self) -> None:
        code, stderr, observed = self._run_with_next_loader(RuntimeError("broken next bundle"))

        self.assertEqual(0, code)
        self.assertEqual([None], observed)
        self.assertIn("cannot load next frontend assets", stderr)
        self.assertIn("broken next bundle", stderr)

    def test_a_loaded_next_bundle_is_attached_to_the_server(self) -> None:
        code, stderr, observed = self._run_with_next_loader(lambda: NEXT_BYTES)

        self.assertEqual(0, code)
        self.assertEqual([NEXT_BYTES], observed)
        self.assertEqual("", stderr)


if __name__ == "__main__":
    unittest.main()
