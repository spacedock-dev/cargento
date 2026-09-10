from __future__ import annotations

import contextlib
import http.server
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from typing import ClassVar
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import serve_operator_cockpit as cockpit


def git(root: Path | None, *args: str) -> str:
    command = ["git"]
    if root is not None:
        command.extend(["-C", str(root)])
    command.extend(args)
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


class BranchCheckoutTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.remote = root / "remote.git"
        self.seed = root / "seed"
        self.checkout_path = root / "checkout"
        git(None, "init", "--bare", "--quiet", str(self.remote))
        git(None, "init", "--quiet", str(self.seed))
        git(self.seed, "config", "user.email", "test@example.com")
        git(self.seed, "config", "user.name", "Test")
        git(self.seed, "switch", "-c", cockpit.DEFAULT_BRANCH)
        (self.seed / "marker").write_text("one\n", encoding="utf-8")
        git(self.seed, "add", "marker")
        git(self.seed, "commit", "--quiet", "-m", "one")
        git(self.seed, "remote", "add", "clkao", str(self.remote))
        git(self.seed, "push", "--quiet", "-u", "clkao", cockpit.DEFAULT_BRANCH)
        self.manager = cockpit.BranchCheckout(
            self.checkout_path,
            str(self.remote),
            cockpit.DEFAULT_BRANCH,
        )
        self.manager.initialize()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_fetch_advances_the_clean_checkout_only_by_fast_forward(self) -> None:
        before = cockpit.git_head(self.checkout_path)
        (self.seed / "marker").write_text("two\n", encoding="utf-8")
        git(self.seed, "commit", "--quiet", "-am", "two")
        git(self.seed, "push", "--quiet", "clkao", cockpit.DEFAULT_BRANCH)
        expected = cockpit.git_head(self.seed)

        update = self.manager.fetch_and_fast_forward()

        self.assertEqual(before, update.before)
        self.assertEqual(expected, update.after)
        self.assertTrue(update.changed)
        self.assertEqual(expected, cockpit.git_head(self.checkout_path))
        self.assertTrue(cockpit.git_clean(self.checkout_path))

    def test_divergence_is_refused_without_moving_the_checkout(self) -> None:
        git(self.checkout_path, "config", "user.email", "test@example.com")
        git(self.checkout_path, "config", "user.name", "Test")
        (self.checkout_path / "local").write_text("local\n", encoding="utf-8")
        git(self.checkout_path, "add", "local")
        git(self.checkout_path, "commit", "--quiet", "-m", "local")
        before = cockpit.git_head(self.checkout_path)
        (self.seed / "remote").write_text("remote\n", encoding="utf-8")
        git(self.seed, "add", "remote")
        git(self.seed, "commit", "--quiet", "-m", "remote")
        git(self.seed, "push", "--quiet", "clkao", cockpit.DEFAULT_BRANCH)

        with self.assertRaisesRegex(cockpit.IntegrationError, "diverged"):
            self.manager.fetch_and_fast_forward()

        self.assertEqual(before, cockpit.git_head(self.checkout_path))

    def test_script_has_no_destructive_checkout_recovery(self) -> None:
        source = Path(cockpit.__file__).read_text(encoding="utf-8")
        self.assertNotIn("reset --hard", source)
        self.assertNotIn("checkout --", source)

    def test_acceptance_marker_requires_an_exact_remote_checkpoint(self) -> None:
        marker = Path(self.temp.name) / "state" / "accepted-remote"
        checkpoint = cockpit.git_head(self.checkout_path)

        self.assertEqual(2, cockpit.accept_remote(marker, "main"))
        self.assertFalse(marker.exists())
        self.assertEqual(0, cockpit.accept_remote(marker, checkpoint))
        self.assertEqual(checkpoint, marker.read_text(encoding="utf-8").strip())

    def test_acceptance_marker_promotes_a_rebased_review_to_remote(self) -> None:
        marker = Path(self.temp.name) / "state" / "accepted-remote"
        accepted = cockpit.git_head(self.checkout_path)
        (self.seed / "review-only").write_text("review\n", encoding="utf-8")
        git(self.seed, "add", "review-only")
        git(self.seed, "commit", "--quiet", "-m", "review")
        review = cockpit.git_head(self.seed)
        cockpit.accept_remote(marker, accepted)

        class RecordingBackend:
            current = None

            def __init__(self) -> None:
                self.replacements: list[tuple[Path, str, str]] = []

            def replace(self, root: Path, checkpoint: str, source: str) -> None:
                self.replacements.append((root, checkpoint, source))

            def stop(self) -> None:
                return

        backend = RecordingBackend()
        coordinator = cockpit.Coordinator(
            self.manager,
            backend,  # type: ignore[arg-type]
            self.seed,
            review,
            marker,
            1,
        )

        coordinator.tick()

        self.assertTrue(coordinator.following_remote)
        self.assertEqual([(self.checkout_path, accepted, "remote")], backend.replacements)
        self.assertFalse(marker.exists())


class FakeBackend(http.server.BaseHTTPRequestHandler):
    posted: ClassVar[bytes] = b""
    health_pid: ClassVar[int] = 999
    project_delay_sec: ClassVar[float] = 0

    def do_GET(self) -> None:
        if self.path == "/":
            self._send(200, b"<html><body>real dashboard</body></html>", "text/html")
            return
        if self.path == "/api/data":
            self._send(200, b'{"sessions":[],"ask":true,"asks":[]}', "application/json")
            return
        if self.path == "/api/health":
            self._send(
                200,
                json.dumps({"ok": True, "pid": type(self).health_pid}).encode(),
                "application/json",
            )
            return
        if self.path == "/api/project-context":
            time.sleep(type(self).project_delay_sec)
            self._send(200, b'{"observers":[]}', "application/json")
            return
        if self.path == "/api/stream":
            self._send(200, b"id: 1\ndata: revision\n\n", "text/event-stream")
            return
        self.send_error(404)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        type(self).posted = self.rfile.read(length)
        self._send(200, b'{"answered":true}', "application/json")

    def _send(self, status: int, payload: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            self.wfile.write(payload)

    def log_message(self, _format: str, *_args: object) -> None:
        return


class StableProxyTest(unittest.TestCase):
    def setUp(self) -> None:
        FakeBackend.posted = b""
        FakeBackend.project_delay_sec = 0
        self.backend_timeout = cockpit.StableProxyHandler.backend_request_timeout_sec
        self.backend = http.server.ThreadingHTTPServer((cockpit.LOOPBACK, 0), FakeBackend)
        self.backend_thread = threading.Thread(target=self.backend.serve_forever, daemon=True)
        self.backend_thread.start()
        published = cockpit.PublishedBackend()
        published.publish(
            port=self.backend.server_port,
            checkpoint="before-checkpoint",
            source="review",
        )
        cockpit.StableProxyHandler.published = published
        cockpit.StableProxyHandler.server_pid = 123
        self.proxy = cockpit.StableProxy((cockpit.LOOPBACK, 0), cockpit.StableProxyHandler)
        self.proxy_thread = threading.Thread(target=self.proxy.serve_forever, daemon=True)
        self.proxy_thread.start()
        self.root = f"http://{cockpit.LOOPBACK}:{self.proxy.server_port}"
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def tearDown(self) -> None:
        cockpit.StableProxyHandler.backend_request_timeout_sec = self.backend_timeout
        self.proxy.shutdown()
        self.proxy.server_close()
        self.backend.shutdown()
        self.backend.server_close()
        self.proxy_thread.join(timeout=5)
        self.backend_thread.join(timeout=5)

    def read(self, path: str) -> tuple[bytes, str]:
        with self.opener.open(self.root + path, timeout=5) as response:
            return response.read(), response.headers.get_content_type()

    def test_page_is_real_backend_html_with_checkpoint_reload_injected(self) -> None:
        payload, content_type = self.read("/")
        self.assertEqual("text/html", content_type)
        self.assertIn(b"real dashboard", payload)
        self.assertIn(b"/__proto/checkpoint", payload)
        self.assertIn(b"before-checkpoint", payload)

    def test_data_and_sse_paths_survive_the_proxy(self) -> None:
        data, data_type = self.read("/api/data")
        stream, stream_type = self.read("/api/stream")
        self.assertEqual("application/json", data_type)
        self.assertEqual({"sessions": [], "ask": True, "asks": []}, json.loads(data))
        self.assertEqual("text/event-stream", stream_type)
        self.assertEqual(b"id: 1\ndata: revision\n\n", stream)

    def test_post_body_and_checkpoint_status_survive_the_proxy(self) -> None:
        request = urllib.request.Request(  # noqa: S310 - loopback URL from test server
            self.root + "/api/answer",
            data=b'{"id":"one","index":0}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.opener.open(request, timeout=5) as response:
            answer = json.load(response)
        checkpoint, _content_type = self.read("/__proto/checkpoint")
        self.assertEqual({"answered": True}, answer)
        self.assertEqual(b'{"id":"one","index":0}', FakeBackend.posted)
        self.assertEqual(
            {
                "checkpoint": "before-checkpoint",
                "source": "review",
                "backend_port": self.backend.server_port,
                "pid": 123,
            },
            json.loads(checkpoint),
        )

    def test_proxy_threads_close_cleanly(self) -> None:
        # The context protects this otherwise empty behavior pin from being
        # optimized into a no-op by a future tearDown rewrite.
        with contextlib.nullcontext():
            self.assertTrue(self.proxy_thread.is_alive())

    def test_backend_deadline_is_configurable_for_bounded_project_analysis(self) -> None:
        FakeBackend.project_delay_sec = 0.05
        cockpit.StableProxyHandler.backend_request_timeout_sec = 0.01
        with self.assertRaises(urllib.error.HTTPError) as refused:
            self.read("/api/project-context")
        self.assertEqual(502, refused.exception.code)

        cockpit.StableProxyHandler.backend_request_timeout_sec = 0.2
        payload, content_type = self.read("/api/project-context")
        self.assertEqual("application/json", content_type)
        self.assertEqual({"observers": []}, json.loads(payload))


class BackendOwnershipTest(unittest.TestCase):
    def test_health_from_an_existing_dashboard_does_not_admit_the_new_child(self) -> None:
        server = http.server.ThreadingHTTPServer((cockpit.LOOPBACK, 0), FakeBackend)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        class Candidate:
            pid = FakeBackend.health_pid + 1
            returncode = None

            @staticmethod
            def poll() -> None:
                return None

        published = cockpit.PublishedBackend()
        pool = cockpit.BackendPool(published, Path(sys.executable), (1, 2), Path("."))
        backend = cockpit.BackendProcess(
            Path("."),
            "checkpoint",
            server.server_port,
            Candidate(),  # type: ignore[arg-type]
            object(),
        )
        try:
            with (
                mock.patch.object(cockpit, "BACKEND_START_TIMEOUT_SEC", 0.15),
                self.assertRaisesRegex(cockpit.IntegrationError, "did not become healthy"),
            ):
                pool._wait_healthy(backend)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
