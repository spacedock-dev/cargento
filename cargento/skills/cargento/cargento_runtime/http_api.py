"""The loopback HTTP service: one server instance, one application, one page."""

from __future__ import annotations

import contextlib
import errno
import json
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import parse_qs, urlparse

from cargento_runtime import io as runtime_io
from cargento_runtime import notifications, quota
from cargento_runtime import snapshot as runtime_snapshot
from cargento_runtime import stream as runtime_stream

if TYPE_CHECKING:
    from cargento_runtime.aggregate import Application


def normalize_host(value: str) -> str:
    """Reduce a ``Host`` header to a bare, lowercased hostname.

    Naive ``rsplit(":", 1)`` mishandles two legitimate forms: a bracketed IPv6
    authority (``[::1]`` with no port becomes ``[:``) and any host whose case
    differs from the allowlist, even though DNS names are case-insensitive and
    ``LOCALHOST`` is as valid as ``localhost``. Both were rejected as non-local.
    """
    host = (value or "").strip()
    if host.startswith("["):
        end = host.find("]")
        if end < 0:
            return ""
        # Only a port may follow the bracketed literal. Without this check
        # "[::1]evil.example" reduced to "::1" and passed as loopback.
        rest = host[end + 1 :]
        if rest and not (rest.startswith(":") and rest[1:].isdigit()):
            return ""
        return host[1:end].lower()
    if host.count(":") > 1:
        return host.lower()  # bare IPv6 with no port
    if ":" not in host:
        return host.lower()
    name, _, port = host.rpartition(":")
    # Same rule as the bracketed branch: only a numeric port may follow, so
    # "localhost:evil.example" does not reduce to "localhost".
    return name.lower() if port.isdigit() else ""


def reuse_address_allowed(os_name: str) -> bool:
    """Whether the listening socket should set ``SO_REUSEADDR``.

    On POSIX the option only bypasses ``TIME_WAIT``, which is what lets the
    dashboard restart immediately after a kill — worth keeping. On Windows the
    same option means something else entirely: a second process may bind a port
    that is *already bound*, with undefined delivery between the two sockets. A
    stray second Cargento would silently steal half the requests, and any local
    process could hijack the port of a server handing out local session data.
    """
    return os_name != "nt"


def bind_error_message(exc: OSError, port: int) -> str:
    """Explain a failed bind instead of dumping a raw traceback."""
    winerror = getattr(exc, "winerror", None)
    if exc.errno == errno.EADDRINUSE or winerror == 10048:  # WSAEADDRINUSE
        return (
            f"Cargento: port {port} is already in use. If that is a dashboard "
            f"already running, use it: curl -s http://127.0.0.1:{port}/api/data. "
            f"Otherwise pick another port with --port."
        )
    if exc.errno == errno.EACCES or winerror == 10013:  # WSAEACCES
        # On Windows this is also what an in-use port reports once
        # SO_EXCLUSIVEADDRUSE is set, so name both causes.
        return (
            f"Cargento: not permitted to bind port {port} — it may already be "
            f"held by another process, reserved by the system, or blocked by "
            f"local policy. Try another port with --port."
        )
    return f"Cargento: cannot bind 127.0.0.1:{port} — {type(exc).__name__}: {exc}"


class CargentoHTTPServer(ThreadingHTTPServer):
    """Loopback listener that refuses to share its port on Windows.

    It owns exactly one application and one assembled page, both read from the
    instance rather than from a module global, so two servers can run in one
    interpreter without either one answering with the other's data.
    """

    def __init__(
        self,
        address: tuple[str, int],
        application: Application,
        page_bytes: bytes,
    ) -> None:
        self.application = application
        self.page_bytes = page_bytes
        # Instance attribute, set before the bind that reads it: the class
        # default would be sampled from the host os.name at import, which is
        # the ambient read D-4 exists to stop.
        self.allow_reuse_address = reuse_address_allowed(application.config.os_name)
        super().__init__(address, _RequestHandler)

    def server_bind(self) -> None:
        # Windows-only socket option, and the complement of the reuse policy
        # rather than an independent switch: Winsock rejects SO_REUSEADDR on a
        # socket already carrying SO_EXCLUSIVEADDRUSE (WSAEINVAL 10022), so both
        # have to come from one decision. Clearing SO_REUSEADDR stops *us* from
        # hijacking someone else's port; this stops anyone else hijacking ours.
        # Gated on this application's config, not the host: reading the host
        # here let a posix-configured application on a Windows host ask for both
        # and fail every bind. Also gated on the constant existing, which it does
        # not on POSIX, where getattr returns None.
        exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if exclusive is not None and not self.allow_reuse_address:
            try:
                self.socket.setsockopt(socket.SOL_SOCKET, exclusive, 1)
            except OSError as exc:
                # Bind anyway, but say so: without this option the port can be
                # hijacked, and silently dropping the guarantee is worse than
                # a noisy one-line warning at startup.
                runtime_io.diag(
                    f"Cargento: could not claim the port exclusively ({exc}); continuing",
                    self.application.diagnostic_sink,
                )
        super().server_bind()


class _RequestHandler(BaseHTTPRequestHandler):
    server: CargentoHTTPServer

    # Loopback-origin requests only: the Host check defeats DNS rebinding,
    # the Origin check defeats cross-site fetch()es from web pages (both
    # reach 127.0.0.1-bound servers through the victim's browser).
    LOCAL_HOSTS: ClassVar[set[str]] = {"127.0.0.1", "localhost", "::1"}

    # How much of a rejected POST's body to read and throw away. Generously above
    # every accept-path cap so a rejection drains whatever a legitimate client
    # sent, and still a hard bound so a hostile declared length cannot turn a
    # refusal into an unbounded read.
    REJECT_DRAIN_CAP_BYTES: ClassVar[int] = 1 << 20

    # How long to spend draining a rejected body. Bounded in time as well as in
    # bytes: a peer may declare a length it never sends, which a limit test does
    # on purpose and a hostile client would do to stall a handler.
    REJECT_DRAIN_SECONDS: ClassVar[float] = 0.25

    def _drain_body(self) -> None:
        """Read and discard a rejected request's body before answering.

        Closing a socket that still holds unread inbound data makes the OS send
        RST rather than FIN, and an RST can discard the reply already written.
        The client then sees ECONNRESET, or WSAECONNABORTED on Windows, instead
        of the 403 or 413 it was told to expect. That is what failed on the
        macOS and Windows runners.

        Bounded three ways, and all three are load-bearing. By the declared
        length, so a well-behaved client is drained exactly. By
        REJECT_DRAIN_CAP_BYTES, so a hostile declared length cannot turn a
        refusal into an unbounded read. And by REJECT_DRAIN_SECONDS, because a
        peer that declares more than it sends would otherwise stall this handler
        until the connection timeout: `read1` blocks for at least one byte, and
        a request-limit test sends exactly that shape deliberately.
        """
        try:
            declared = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return
        remaining = max(0, min(declared, self.REJECT_DRAIN_CAP_BYTES))
        if not remaining:
            return
        deadline = time.monotonic() + self.REJECT_DRAIN_SECONDS
        previous = None
        try:
            previous = self.connection.gettimeout()
            self.connection.settimeout(self.REJECT_DRAIN_SECONDS)
        except (OSError, AttributeError):
            previous = None  # not a real socket, as in a handler-level test
        try:
            while remaining > 0 and time.monotonic() < deadline:
                try:
                    # read1, not read: one syscall returning what is available,
                    # rather than blocking until the full count arrives.
                    chunk = self.rfile.read1(min(remaining, 65_536))
                except (OSError, ValueError, AttributeError):
                    return
                if not chunk:
                    return  # end of stream, or nothing more is coming
                remaining -= len(chunk)
        finally:
            if previous is not None:
                with contextlib.suppress(OSError):
                    self.connection.settimeout(previous)

    def _reject(self, code: int) -> None:
        """Refuse a POST without stranding the peer mid-write."""
        self._drain_body()
        self.send_error(code)

    def _local_ok(self, *, allow_cross_site_navigation: bool = False) -> bool:
        if normalize_host(self.headers.get("Host") or "") not in self.LOCAL_HOSTS:
            return False
        if (self.headers.get("Sec-Fetch-Site") or "").lower() == "cross-site" and not (
            allow_cross_site_navigation and self._is_document_navigation()
        ):
            return False
        origin = self.headers.get("Origin")
        if not origin:
            return True  # same-origin GETs send none
        # Compare the whole origin, not just the host. Every port on this
        # machine is the *same site*, so Sec-Fetch-Site reports "same-site" for
        # a page served from another local port — and a hostname-only check
        # then trusted it. Any unrelated local dev server could POST here
        # (text/plain is CORS-safelisted, so no preflight would stop it).
        parsed = urlparse(origin)
        if parsed.scheme != "http" or (parsed.hostname or "") not in self.LOCAL_HOSTS:
            return False
        listening_port = getattr(self.server, "server_port", None)
        try:
            # Browsers omit the port when it is the scheme default, so
            # "http://localhost" is a legitimate same-origin value on port 80.
            origin_port = parsed.port if parsed.port is not None else 80
        except ValueError:
            return False  # unparseable port in the Origin header
        return origin_port == listening_port

    def _is_document_navigation(self) -> bool:
        """Whether this is the browser navigating a tab to us, top level.

        Chrome labels *any* navigation whose initiator was another origin
        ``Sec-Fetch-Site: cross-site`` — including one the user started by
        clicking a link to the dashboard. Rejecting those returned 403 for a
        perfectly ordinary way to open the page.

        Serving them is safe: the initiating page cannot read a cross-origin
        document, so there is nothing to exfiltrate, and the Host check above
        still blocks DNS rebinding. Everything else cross-site — ``fetch``,
        XHR, an iframe, a subresource — *can* be read by its initiator and
        stays blocked, which is what ``Sec-Fetch-Dest: document`` distinguishes
        (an iframe reports ``iframe``). GET only: a cross-site form submission
        is also a "navigation", so POST never takes this path.
        """
        return (self.headers.get("Sec-Fetch-Mode") or "").lower() == "navigate" and (
            self.headers.get("Sec-Fetch-Dest") or ""
        ).lower() == "document"

    def _send(
        self,
        body: bytes,
        ctype: str,
        code: int = 200,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _health(self) -> None:
        """Liveness and identity, with no filesystem access.

        `/api/data` can answer "is a dashboard here?" only by scanning every
        harness store on the machine. The daemon readiness wait and --status ask
        that question in a loop, so they need an answer that costs nothing. The
        pid is part of it because "something is listening on the port" is not
        the same claim as "Cargento is running on the port".

        ``started`` is the value ``build_runtime_state`` captured, read straight
        off this server's own state. Sampling a clock here instead would make
        every poll report a different uptime for the same process.
        """
        self._send(
            json.dumps(
                {
                    "ok": True,
                    "pid": os.getpid(),
                    "port": getattr(self.server, "server_port", 0),
                    "started": self.server.application.state.server_started,
                }
            ).encode(),
            "application/json",
        )

    def _shutdown(self) -> None:
        """Stop the server: the page's stop button and --stop both land here.

        Answer first, then stop. `socketserver.shutdown()` blocks until the
        accept loop notices the request and exits, which can take up to one
        poll interval (0.5s by default) — running it on its own thread lets
        this handler return and the connection close immediately, instead of
        holding the client for that long. It also keeps this correct if the
        server class ever stops being a threading one: on a non-threading
        server the handler runs on the serve loop's own thread, and calling
        `shutdown()` inline would then deadlock, exactly as `BaseServer.
        shutdown`'s docstring warns.
        """
        # Wake every stream first. shutdown() stops the accept loop but never
        # touches handler threads, and a stream is asleep in wait() rather than
        # in the socket, so nothing else would tell it to stop.
        with contextlib.suppress(Exception):
            self.server.application.state.streams.close_all()
        try:
            self._send(b'{"ok":true,"stopping":true}', "application/json")
            with contextlib.suppress(OSError, ValueError):
                self.wfile.flush()
        except (OSError, ValueError):
            # The request was accepted even if the peer vanished before it
            # could read the reply. Do not let that disconnect cancel the stop.
            pass
        finally:
            threading.Thread(target=self.server.shutdown, daemon=True).start()

    def do_GET(self) -> None:
        if not self._local_ok(allow_cross_site_navigation=True):
            self.send_error(403)
            return
        url = urlparse(self.path)
        if url.path == "/api/data":
            query = parse_qs(url.query)
            show_all = query.get("all", ["0"])[0] == "1"
            # `usage=1` is the page's consent to the quota fetch riding along
            # on its poll: the page sends it only with the feature switched on
            # and the first-run disclosure already shown. The fetch is a
            # background side effect behind its own floor and in-flight gates;
            # this request is answered from whatever is already cached. A bare
            # request without the parameter never triggers network traffic.
            if query.get("usage", ["0"])[0] == "1":
                self.server.application.request_usage_fetch()
            revision, body = self.server.application.collect_json(show_all=show_all)
            # The cursor rides in a header rather than the body, so the
            # documented JSON contract and every curl caller stay untouched.
            self._send(
                body,
                "application/json",
                headers={"X-Cargento-Revision": runtime_snapshot.format_revision(revision)},
            )
        elif url.path == "/api/stream":
            self._stream()
        elif url.path == "/api/health":
            self._health()
        elif url.path == "/":
            self._send(self.server.page_bytes, "text/html; charset=utf-8")
        else:
            self.send_error(404)

    def _stream(self) -> None:
        """The SSE revision stream.

        Strictly same-origin. `do_GET` relaxes its check for document
        navigations so a link to the dashboard works, and a long-lived data
        stream is not a document navigation, so re-checking here with the
        strict form is what keeps that relaxation off this route.
        """
        if not self._local_ok():
            self.send_error(403)
            return
        application = self.server.application
        state = application.state
        client = state.streams.register(limit=application.config.stream_max_clients)
        if client is None:
            # A refusal, not a queue: every stream costs a thread and a socket
            # for as long as it lives.
            self.send_error(503)
            return
        try:
            self._stream_forever(client)
        finally:
            state.streams.release(client)

    def _stream_forever(self, client: runtime_stream.StreamClient) -> None:
        application = self.server.application
        config = application.config
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        with contextlib.suppress(OSError):
            # A peer that stops reading must not pin this thread forever. The
            # unbounded default is the real risk here, not server_close.
            self.connection.settimeout(config.stream_write_timeout_sec)
        current = application.state.snapshot.current((config.window_hours, False))
        if current is not None and not self._emit(current[0]):
            return
        while True:
            revision = client.wait(timeout=config.stream_heartbeat_sec)
            # Checked after the wait, not in the loop condition: close() lands
            # while this thread is asleep, which is the whole point of it, and a
            # `while not client.closed` header reads to the type checker as a
            # value that cannot change inside the body.
            if client.closed:
                return
            if revision is None:
                if not self._write_raw(b": keepalive\n\n"):
                    return
                continue
            if not self._emit(revision):
                return

    def _emit(self, revision: runtime_snapshot.Revision) -> bool:
        rendered = runtime_snapshot.format_revision(revision)
        return self._write_raw(f"id: {rendered}\nevent: revision\ndata: {rendered}\n\n".encode())

    def _write_raw(self, payload: bytes) -> bool:
        """Write and flush, reporting whether the peer is still there.

        No lock is held here. A blocked write must never be able to stall a
        publisher or a collection.
        """
        try:
            self.wfile.write(payload)
            self.wfile.flush()
        except (OSError, ValueError):
            return False
        return True

    def _usage_receipt(self) -> None:
        """A harness's own quota, forwarded here by its status-line command.

        Guarded exactly like `/api/notify`: `_local_ok()` has already run, the
        declared length is checked before any read, a malformed or non-object
        body degrades to `{}`, and the shaping code publishes derived scalars
        only. Nothing here touches the network or the disk.
        """
        application = self.server.application
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if not 0 <= length <= application.config.usage_receipt_cap_bytes:
            self._reject(413)
            return
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError, RecursionError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        response = quota.receive_statusline(
            application.state,
            payload,
            now=application.clock(),
            config=application.config,
        )
        self._send(json.dumps(response, separators=(",", ":")).encode(), "application/json")

    def do_POST(self) -> None:
        if not self._local_ok():
            self._reject(403)
            return
        path = urlparse(self.path).path
        if path == "/api/shutdown":
            self._shutdown()
            return
        if path == "/api/usage":
            self._usage_receipt()
            return
        if path != "/api/notify":
            self._reject(404)
            return
        # Claude Code Notification-hook payload: {"session_id": ..., "message": ..., ...}
        application = self.server.application
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        # Checked before the read, so an oversized declared length costs nothing
        # and no path here ever reads an unbounded body.
        if not 0 <= length <= application.config.notification_body_cap_bytes:
            self._reject(413)
            return
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError, RecursionError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        response = notifications.handle_payload(
            application.config,
            application.state,
            payload,
            now=time.time(),
            popup_notifier=application.popup_notifier,
        )
        # Compact separators: the notify response is a fixed wire format, and the
        # hook and race tests assert the exact bytes. json.dumps' default spaces
        # would break them.
        self._send(json.dumps(response, separators=(",", ":")).encode(), "application/json")

    def log_message(self, *args: Any) -> None:
        pass  # keep the terminal quiet
