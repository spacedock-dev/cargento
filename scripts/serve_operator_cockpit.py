# ruff: noqa: INP001 - standalone repository script
"""Keep one stable loopback URL on the accepted operator-cockpit checkpoint."""

from __future__ import annotations

import argparse
import contextlib
import http.client
import http.server
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

LOOPBACK = "127.0.0.1"
DEFAULT_REMOTE = "https://github.com/clkao/cargento.git"
DEFAULT_BRANCH = "proto/operator-cockpit"
HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}
MAX_REQUEST_BYTES = 4 << 20
BACKEND_START_TIMEOUT_SEC = 20
# The selected-project endpoint owns at most three sequential model calls, each
# capped at 60 seconds. The former generic 15-second proxy deadline returned a
# 502 while a measured cold request continued normally and wrote all sidecars.
BACKEND_REQUEST_TIMEOUT_SEC = (3 * 60) + 15


class IntegrationError(RuntimeError):
    """An invariant prevented checkout or backend replacement."""


def run_git(root: Path | None, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    command = ["git"]
    if root is not None:
        command.extend(["-C", str(root)])
    command.extend(args)
    return subprocess.run(  # noqa: S603 - command is fixed to git; args never use a shell
        command,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )


def git_head(root: Path) -> str:
    return run_git(root, "rev-parse", "HEAD").stdout.strip()


def git_clean(root: Path) -> bool:
    return not run_git(root, "status", "--porcelain=v1").stdout.strip()


def is_ancestor(root: Path, older: str, newer: str) -> bool:
    result = run_git(root, "merge-base", "--is-ancestor", older, newer, check=False)
    if result.returncode not in {0, 1}:
        raise IntegrationError(result.stderr.strip() or "cannot compare commits")
    return result.returncode == 0


def commit_exists(root: Path, commit: str) -> bool:
    return run_git(root, "cat-file", "-e", f"{commit}^{{commit}}", check=False).returncode == 0


@dataclass(frozen=True)
class CheckoutUpdate:
    before: str
    after: str
    changed: bool


class BranchCheckout:
    """A dedicated remote-branch clone that advances only by fast-forward."""

    def __init__(self, path: Path, remote_url: str, branch: str) -> None:
        self.path = path
        self.remote_url = remote_url
        self.branch = branch

    def initialize(self) -> None:
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            run_git(
                None,
                "clone",
                "--quiet",
                "--single-branch",
                "--branch",
                self.branch,
                "--origin",
                "clkao",
                self.remote_url,
                str(self.path),
            )
        if not (self.path / ".git").exists():
            raise IntegrationError(f"checkout is not a git clone: {self.path}")
        actual = run_git(self.path, "remote", "get-url", "clkao").stdout.strip()
        if actual != self.remote_url:
            raise IntegrationError(
                f"checkout clkao remote is {actual!r}, expected {self.remote_url!r}"
            )
        branch = run_git(self.path, "branch", "--show-current").stdout.strip()
        if branch != self.branch:
            raise IntegrationError(f"checkout branch is {branch!r}, expected {self.branch!r}")

    def fetch_and_fast_forward(self) -> CheckoutUpdate:
        if not git_clean(self.path):
            raise IntegrationError(f"dedicated checkout is dirty: {self.path}")
        before = git_head(self.path)
        run_git(self.path, "fetch", "--quiet", "clkao", self.branch)
        remote = run_git(self.path, "rev-parse", "FETCH_HEAD").stdout.strip()
        if before == remote:
            return CheckoutUpdate(before, before, False)
        if not is_ancestor(self.path, before, remote):
            raise IntegrationError(
                f"remote {self.branch} diverged: {before[:12]} is not an ancestor of {remote[:12]}"
            )
        run_git(self.path, "merge", "--ff-only", remote)
        after = git_head(self.path)
        if after != remote:
            raise IntegrationError(f"fast-forward ended at {after[:12]}, expected {remote[:12]}")
        return CheckoutUpdate(before, after, True)


class PublishedBackend:
    """The backend address and revision atomically visible to proxy threads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._port: int | None = None
        self._checkpoint = "starting"
        self._source = "starting"

    def publish(self, *, port: int, checkpoint: str, source: str) -> None:
        with self._lock:
            self._port = port
            self._checkpoint = checkpoint
            self._source = source

    def snapshot(self) -> tuple[int | None, str, str]:
        with self._lock:
            return self._port, self._checkpoint, self._source


@dataclass
class BackendProcess:
    root: Path
    checkpoint: str
    port: int
    process: subprocess.Popen[bytes]
    log_handle: object


class BackendPool:
    """Blue/green Cargento processes behind one published address."""

    def __init__(
        self,
        published: PublishedBackend,
        python: Path,
        ports: tuple[int, int],
        log_dir: Path,
    ) -> None:
        self.published = published
        self.python = python
        self.ports = ports
        self.log_dir = log_dir
        self.current: BackendProcess | None = None

    def replace(self, root: Path, checkpoint: str, source: str) -> None:
        port = self.ports[0]
        if self.current is not None and self.current.port == port:
            port = self.ports[1]
        server = root / "cargento" / "skills" / "cargento" / "server.py"
        if not server.is_file():
            raise IntegrationError(f"checkpoint has no Cargento launcher: {server}")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        log_handle = (self.log_dir / f"backend-{port}.log").open("ab")
        environment = os.environ.copy()
        environment["CARGENTO_HOME"] = str(self.log_dir / "cargento-home")
        process = subprocess.Popen(  # noqa: S603 - argv is fully controlled here
            [str(self.python), str(server), "--port", str(port), "--no-usage"],
            cwd=root,
            env=environment,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        candidate = BackendProcess(root, checkpoint, port, process, log_handle)
        try:
            self._wait_healthy(candidate)
        except Exception:
            self._stop_one(candidate)
            raise
        previous = self.current
        self.current = candidate
        self.published.publish(port=port, checkpoint=checkpoint, source=source)
        if previous is not None:
            self._stop_one(previous)

    def _wait_healthy(self, backend: BackendProcess) -> None:
        deadline = time.monotonic() + BACKEND_START_TIMEOUT_SEC
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        root = f"http://{LOOPBACK}:{backend.port}"
        while time.monotonic() < deadline:
            if backend.process.poll() is not None:
                raise IntegrationError(f"backend exited with {backend.process.returncode}")
            try:
                with opener.open(root + "/api/health", timeout=2) as response:
                    health = json.loads(response.read(4096))
                if not isinstance(health, dict) or health.get("pid") != backend.process.pid:
                    time.sleep(0.1)
                    continue
                with opener.open(root + "/api/data", timeout=2) as response:
                    payload = json.loads(response.read(MAX_REQUEST_BYTES))
                if isinstance(payload, dict) and isinstance(payload.get("sessions"), list):
                    return
            except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError):
                time.sleep(0.1)
        raise IntegrationError(
            f"backend child {backend.process.pid} on port {backend.port} did not become healthy"
        )

    @staticmethod
    def _stop_one(backend: BackendProcess) -> None:
        if backend.process.poll() is None:
            backend.process.terminate()
            try:
                backend.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                backend.process.kill()
                backend.process.wait(timeout=5)
        with contextlib.suppress(OSError):
            backend.log_handle.close()  # type: ignore[attr-defined]

    def stop(self) -> None:
        if self.current is not None:
            self._stop_one(self.current)
            self.current = None


def reload_script(checkpoint: str) -> bytes:
    quoted = json.dumps(checkpoint)
    script = (
        "<script>(()=>{const initial="
        + quoted
        + ";async function check(){try{const r=await fetch('/__proto/checkpoint',"
        + "{cache:'no-store'});const d=await r.json();if(d.checkpoint!==initial)location.reload();}"
        + "catch(e){}setTimeout(check,1500)}setTimeout(check,1500)})();</script>"
    )
    return script.encode()


class StableProxyHandler(http.server.BaseHTTPRequestHandler):
    """Reverse proxy the selected backend and expose its checkpoint."""

    published: ClassVar[PublishedBackend]
    server_pid: ClassVar[int | None] = None
    backend_request_timeout_sec: ClassVar[float] = BACKEND_REQUEST_TIMEOUT_SEC
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/__proto/checkpoint":
            self._checkpoint()
            return
        self._proxy()

    def do_POST(self) -> None:
        self._proxy()

    def _checkpoint(self) -> None:
        port, checkpoint, source = self.published.snapshot()
        payload = json.dumps(
            {
                "checkpoint": checkpoint,
                "source": source,
                "backend_port": port,
                "pid": self.server_pid,
            },
            separators=(",", ":"),
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _request_body(self) -> bytes:
        raw = self.headers.get("Content-Length")
        if not raw:
            return b""
        try:
            length = int(raw)
        except ValueError as exc:
            raise IntegrationError("invalid request length") from exc
        if length < 0 or length > MAX_REQUEST_BYTES:
            raise IntegrationError("request body exceeds proxy limit")
        return self.rfile.read(length)

    def _proxy(self) -> None:
        port, checkpoint, _source = self.published.snapshot()
        if port is None:
            self.send_error(503, "backend is starting")
            return
        try:
            body = self._request_body()
        except IntegrationError as exc:
            self.send_error(413, str(exc))
            return
        headers = self._forward_headers(port, body)
        connection = http.client.HTTPConnection(
            LOOPBACK,
            port,
            timeout=self.backend_request_timeout_sec,
        )
        try:
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()
            content_type = response.getheader("Content-Type") or ""
            streaming = content_type.startswith("text/event-stream")
            if streaming:
                # A finite test/backend response can already be buffered and
                # close its socket before getresponse() returns. A real live
                # stream keeps the socket, and only that socket needs its read
                # deadline removed.
                if connection.sock is not None:
                    connection.sock.settimeout(None)
                self._stream_response(response)
                return
            payload = response.read(MAX_REQUEST_BYTES + 1)
            if len(payload) > MAX_REQUEST_BYTES:
                self.send_error(502, "backend response exceeds proxy limit")
                return
            if content_type.startswith("text/html"):
                payload = payload.replace(b"</body>", reload_script(checkpoint) + b"</body>", 1)
            self.send_response(response.status, response.reason)
            self._copy_headers(response, content_length=len(payload))
            self.end_headers()
            self.wfile.write(payload)
        except (ConnectionError, OSError, http.client.HTTPException, IntegrationError) as exc:
            if not self.wfile.closed:
                with contextlib.suppress(OSError):
                    self.send_error(502, f"backend unavailable: {type(exc).__name__}")
        finally:
            connection.close()

    def _forward_headers(self, port: int, body: bytes) -> dict[str, str]:
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_HEADERS and key.lower() not in {"host", "content-length"}
        }
        headers["Host"] = f"{LOOPBACK}:{port}"
        headers["Content-Length"] = str(len(body))
        for name in ("Origin", "Referer"):
            if name in headers:
                headers[name] = f"http://{LOOPBACK}:{port}/"
        return headers

    def _stream_response(self, response: http.client.HTTPResponse) -> None:
        self.send_response(response.status, response.reason)
        self._copy_headers(response, content_length=None)
        self.end_headers()
        try:
            while chunk := response.read1(8192):
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def _copy_headers(self, response: http.client.HTTPResponse, content_length: int | None) -> None:
        for name, value in response.getheaders():
            lower = name.lower()
            if lower in HOP_HEADERS or lower == "content-length":
                continue
            self.send_header(name, value)
        if content_length is not None:
            self.send_header("Content-Length", str(content_length))
        self.send_header("Cache-Control", "no-store")


class StableProxy(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class Coordinator:
    """Watch review HEAD and the integration branch, replacing backends safely."""

    def __init__(
        self,
        checkout: BranchCheckout,
        backend: BackendPool,
        review_root: Path | None,
        review_commit: str | None,
        accepted_remote_file: Path,
        interval: float,
    ) -> None:
        self.checkout = checkout
        self.backend = backend
        self.review_root = review_root
        self.review_commit = review_commit
        self.accepted_remote_file = accepted_remote_file
        self.interval = interval
        self.following_remote = review_root is None
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.last_error = ""

    def start(self) -> None:
        self.checkout.initialize()
        update = self.checkout.fetch_and_fast_forward()
        if self.review_root is not None:
            if self.review_commit is None:
                self.review_commit = git_head(self.review_root)
            if git_head(self.review_root) != self.review_commit:
                raise IntegrationError("review checkout HEAD does not match --review-commit")
            if not git_clean(self.review_root):
                raise IntegrationError("review checkout must be clean before serving")
            self.backend.replace(self.review_root, self.review_commit, "review")
        else:
            self.backend.replace(self.checkout.path, update.after, "remote")
        self.thread = threading.Thread(
            target=self._watch,
            name="operator-cockpit-watch",
            daemon=True,
        )
        self.thread.start()

    def _watch(self) -> None:
        while not self.stop_event.wait(self.interval):
            try:
                self.tick()
                self.last_error = ""
            except (IntegrationError, OSError, subprocess.SubprocessError) as exc:
                message = str(exc)
                if message != self.last_error:
                    print(f"operator cockpit watcher: {message}", file=sys.stderr, flush=True)
                self.last_error = message

    def tick(self) -> None:
        update = self.checkout.fetch_and_fast_forward()
        if (
            not self.following_remote
            and self.review_root is not None
            and self.review_commit is not None
        ):
            review_head = git_head(self.review_root)
            if review_head != self.review_commit:
                if not is_ancestor(self.review_root, self.review_commit, review_head):
                    raise IntegrationError("review checkout did not advance by fast-forward")
                if not git_clean(self.review_root):
                    raise IntegrationError("review checkout advanced but is dirty")
                self.backend.replace(self.review_root, review_head, "review")
                self.review_commit = review_head
            if commit_exists(self.checkout.path, self.review_commit) and is_ancestor(
                self.checkout.path, self.review_commit, update.after
            ):
                self.backend.replace(self.checkout.path, update.after, "remote")
                self.following_remote = True
                with contextlib.suppress(OSError):
                    self.accepted_remote_file.unlink()
                return
            accepted = self._accepted_remote()
            if (
                accepted
                and commit_exists(self.checkout.path, accepted)
                and is_ancestor(self.checkout.path, accepted, update.after)
            ):
                self.backend.replace(self.checkout.path, update.after, "remote")
                self.following_remote = True
                with contextlib.suppress(OSError):
                    self.accepted_remote_file.unlink()
            return
        current = self.backend.current
        if current is not None and current.checkpoint != update.after:
            self.backend.replace(self.checkout.path, update.after, "remote")

    def _accepted_remote(self) -> str | None:
        try:
            value = self.accepted_remote_file.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return value if re.fullmatch(r"[0-9a-f]{40}", value) else None

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=5)
        self.backend.stop()


def _state_payload(port: int) -> dict[str, object] | None:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://{LOOPBACK}:{port}/__proto/checkpoint", timeout=2) as response:
            value = json.loads(response.read(4096))
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def stop_existing(pid_file: Path, public_port: int) -> int:
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        print("operator cockpit: no recorded server")
        return 0
    status = _state_payload(public_port)
    if not status or status.get("pid") not in {None, pid}:
        print("operator cockpit: recorded PID does not own the stable URL", file=sys.stderr)
        return 1
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except OSError as exc:
        print(f"operator cockpit: cannot stop PID {pid}: {exc}", file=sys.stderr)
        return 1
    with contextlib.suppress(OSError):
        pid_file.unlink()
    print(f"operator cockpit: stop requested for PID {pid}")
    return 0


def accept_remote(checkpoint_file: Path, checkpoint: str) -> int:
    if not re.fullmatch(r"[0-9a-f]{40}", checkpoint):
        print("operator cockpit: accepted checkpoint must be a full lowercase SHA", file=sys.stderr)
        return 2
    checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
    pending = checkpoint_file.with_suffix(".pending")
    pending.write_text(checkpoint + "\n", encoding="utf-8")
    pending.replace(checkpoint_file)
    print(f"operator cockpit: will follow remote once it contains {checkpoint}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-port", type=int, default=8766)
    parser.add_argument("--backend-port-a", type=int, default=18766)
    parser.add_argument("--backend-port-b", type=int, default=18767)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--remote-url", default=DEFAULT_REMOTE)
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument("--review-root", type=Path)
    parser.add_argument("--review-commit")
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--accept-remote", metavar="CHECKPOINT")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    pid_file = args.state_dir / "server.pid"
    accepted_remote_file = args.state_dir / "accepted-remote"
    if args.stop and args.accept_remote:
        print("operator cockpit: choose --stop or --accept-remote", file=sys.stderr)
        return 2
    if args.stop:
        return stop_existing(pid_file, args.public_port)
    if args.accept_remote:
        return accept_remote(accepted_remote_file, args.accept_remote)
    if args.review_commit and args.review_root is None:
        print("operator cockpit: --review-commit requires --review-root", file=sys.stderr)
        return 2
    args.state_dir.mkdir(parents=True, exist_ok=True)
    published = PublishedBackend()
    StableProxyHandler.published = published
    StableProxyHandler.server_pid = os.getpid()
    checkout = BranchCheckout(args.checkout.resolve(), args.remote_url, args.branch)
    backend = BackendPool(
        published,
        args.python.resolve(),
        (args.backend_port_a, args.backend_port_b),
        args.state_dir.resolve(),
    )
    coordinator = Coordinator(
        checkout,
        backend,
        args.review_root.resolve() if args.review_root else None,
        args.review_commit,
        accepted_remote_file,
        max(0.25, args.poll_seconds),
    )
    try:
        coordinator.start()
        server = StableProxy((LOOPBACK, args.public_port), StableProxyHandler)
    except (IntegrationError, OSError, subprocess.SubprocessError) as exc:
        coordinator.stop()
        print(f"operator cockpit: cannot start: {exc}", file=sys.stderr)
        return 1
    pid_file.write_text(str(os.getpid()), encoding="utf-8")
    stopping = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        if stopping.is_set():
            return
        stopping.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    _port, checkpoint, source = published.snapshot()
    print(
        f"Operator cockpit: http://{LOOPBACK}:{args.public_port}/ ({source} {checkpoint})",
        flush=True,
    )
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
        coordinator.stop()
        with contextlib.suppress(OSError):
            pid_file.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
