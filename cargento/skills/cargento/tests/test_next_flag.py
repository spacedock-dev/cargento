from __future__ import annotations

import contextlib
import hashlib
import http.client
import io
import os
import shutil
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from cargento_runtime import cli, lifecycle
from cargento_runtime.web import page as frontend_page

from .support import make_server, serve_until_closed

NEXT_BYTES = b"<html>next bundle</html>"


class DefaultPageRoutingTest(unittest.TestCase):
    @staticmethod
    def _get(port: int, path: str) -> tuple[int, bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.request("GET", path)
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def test_supported_root_queries_serve_the_one_canonical_page(self) -> None:
        httpd = make_server(page_bytes=NEXT_BYTES)
        thread = serve_until_closed(httpd)
        try:
            for path in (
                "/",
                "/?all=1",
                "/?nextish=true",
            ):
                with self.subTest(path=path):
                    self.assertEqual((200, NEXT_BYTES), self._get(httpd.server_port, path))
        finally:
            httpd.shutdown()
            thread.join(timeout=5)

    def test_retired_next_query_is_not_a_page_alias(self) -> None:
        httpd = make_server(page_bytes=NEXT_BYTES)
        thread = serve_until_closed(httpd)
        try:
            for path in ("/?next=true", "/?next=false", "/?next=", "/?all=1&next=true"):
                with self.subTest(path=path):
                    status, body = self._get(httpd.server_port, path)
                    self.assertEqual(404, status)
                    self.assertNotEqual(NEXT_BYTES, body)
        finally:
            httpd.shutdown()
            thread.join(timeout=5)

    def test_the_canonical_loader_is_the_released_ui_bundle(self) -> None:
        page = frontend_page.load_page()

        self.assertEqual(320_892, len(page))
        self.assertEqual(
            "ccae209cef2931bada6f5711325331f5e5cdefe7042f29e68c451f4306191977",
            hashlib.sha256(page).hexdigest(),
        )

    def test_the_canonical_loader_reads_the_web_root_not_a_preview_directory(self) -> None:
        source = frontend_page.WEB_DIR
        with tempfile.TemporaryDirectory() as tmp:
            web = Path(tmp)
            shutil.copytree(source, web, dirs_exist_ok=True)
            shutil.copytree(source, web / "next", dirs_exist_ok=True)
            template = web / "index.html"
            template.write_text(
                template.read_text(encoding="utf-8").replace(
                    "<title>Cargento</title>",
                    "<title>canonical marker</title>",
                ),
                encoding="utf-8",
            )
            with mock.patch.object(frontend_page, "WEB_DIR", web):
                page = frontend_page.load_page()

        self.assertIn(b"<title>canonical marker</title>", page)

    def test_shared_server_factory_serves_the_canonical_page(self) -> None:
        httpd = make_server()
        thread = serve_until_closed(httpd)
        try:
            expected = (200, frontend_page.load_page())
            self.assertEqual(expected, self._get(httpd.server_port, "/"))
        finally:
            httpd.shutdown()
            thread.join(timeout=5)


class DefaultPageCliBoundaryTest(unittest.TestCase):
    @staticmethod
    def _run_with_loaders(
        page_loader: object,
        preview_loader: object,
    ) -> tuple[int, str, list[bytes]]:
        observed: list[bytes] = []

        def close_server(_config: object, server: Any, _port: int, **_kwargs: object) -> None:
            observed.append(server.page_bytes)
            server.server_close()

        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]

        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.dict(os.environ, {"CARGENTO_HOME": tmp}),
            mock.patch.object(sys, "argv", ["server.py", "--port", str(port), "--no-events"]),
            mock.patch.object(frontend_page, "load_page", side_effect=page_loader),
            mock.patch.object(
                frontend_page,
                "load_next_page",
                side_effect=preview_loader,
                create=True,
            ),
            mock.patch.object(lifecycle, "serve", side_effect=close_server),
            contextlib.redirect_stderr(io.StringIO()) as stderr,
        ):
            code = cli.main()
        return code, stderr.getvalue(), observed

    def test_startup_does_not_probe_a_second_preview_bundle(self) -> None:
        code, stderr, observed = self._run_with_loaders(
            lambda: NEXT_BYTES,
            RuntimeError("defunct preview bundle"),
        )

        self.assertEqual(0, code)
        self.assertEqual([NEXT_BYTES], observed)
        self.assertEqual("", stderr)

    def test_a_broken_canonical_bundle_prevents_binding(self) -> None:
        code, stderr, observed = self._run_with_loaders(
            RuntimeError("broken canonical bundle"),
            lambda: b"unused",
        )

        self.assertEqual(1, code)
        self.assertEqual([], observed)
        self.assertIn("cannot load frontend assets", stderr)
        self.assertIn("broken canonical bundle", stderr)


if __name__ == "__main__":
    unittest.main()
