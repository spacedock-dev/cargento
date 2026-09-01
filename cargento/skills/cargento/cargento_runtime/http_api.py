"""The loopback HTTP service: one server instance, one application, one assembled page."""

from __future__ import annotations

import contextlib
import errno
import ipaddress
import json
import os
import socket
import socketserver
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import ParseResult, parse_qs, urlparse

from cargento_runtime import asks as runtime_asks
from cargento_runtime import dismissals, notifications, quota, records
from cargento_runtime import events as runtime_events
from cargento_runtime import io as runtime_io
from cargento_runtime import observer as runtime_observer
from cargento_runtime import snapshot as runtime_snapshot
from cargento_runtime import stream as runtime_stream

if TYPE_CHECKING:
    from cargento_runtime.aggregate import Application
    from cargento_runtime.observation import Observation


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


def bind_error_message(exc: OSError, port: int, host: str = "127.0.0.1") -> str:
    """Explain a failed bind instead of dumping a raw traceback."""
    winerror = getattr(exc, "winerror", None)
    if exc.errno == errno.EADDRINUSE or winerror == 10048:  # WSAEADDRINUSE
        # 0.0.0.0 is a bind address and not a destination, so the hint keeps
        # loopback there — the wildcard is not connectable, which
        # `_host_admitted` says in as many words. Any other bind is where the
        # printed curl was pointing at the wrong machine.
        reachable = "127.0.0.1" if host in ("127.0.0.1", "0.0.0.0") else host  # noqa: S104
        return (
            f"Cargento: port {port} is already in use. If that is a dashboard "
            f"already running, use it: curl -s http://{reachable}:{port}/api/data. "
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
    return f"Cargento: cannot bind {host}:{port} — {type(exc).__name__}: {exc}"


class CargentoHTTPServer(ThreadingHTTPServer):
    """Loopback listener that refuses to share its port on Windows.

    It owns exactly one application and its assembled page, all read from the
    instance rather than from module globals, so two servers can run in one
    interpreter without either one answering with the other's data.
    """

    def __init__(
        self,
        address: tuple[str, int],
        application: Application,
        page_bytes: bytes,
        observation: Observation | None = None,
    ) -> None:
        self.application = application
        self.page_bytes = page_bytes
        # None under --no-events, and None for the many test doubles that only
        # need a page and an application. `serve` reads it to decide whether to
        # run the coordinator or the older periodic producer.
        self.observation = observation
        # Instance attribute, set before the bind that reads it: the class
        # default would be sampled from the host os.name at import, which is
        # the ambient read D-4 exists to stop.
        self.allow_reuse_address = reuse_address_allowed(application.config.os_name)
        # The bind host from the constructor address, read by _local_ok to
        # decide whether a non-loopback Host header is the operator's opt-in
        # (--host 0.0.0.0) rather than a DNS-rebinding probe.
        self.bound_host = address[0]
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
        # Deliberately NOT `super().server_bind()`. `HTTPServer.server_bind`
        # resolves the bind address to a name with `socket.getfqdn()` — a
        # reverse DNS lookup, on the startup path, for a value nothing here
        # reads. Where the resolver has no answer for 127.0.0.1 it does not fail
        # fast, it waits: on the macOS CI runner that was ~17.5s per bind, which
        # is most of what made the macOS test leg take 316s against Ubuntu's 29s,
        # and it is the same stall a person starting the dashboard on a machine
        # with a slow resolver would sit through before the page came up.
        #
        # `server_name` and `server_port` are still set, because the base class
        # promises them; the name is the host as given rather than whatever the
        # resolver would have called it.
        socketserver.TCPServer.server_bind(self)
        # Read off the bound socket rather than the requested address, so a
        # port of 0 reports the port the OS actually gave.
        bound = self.socket.getsockname()
        self.server_name = str(bound[0])
        self.server_port = int(bound[1])


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

    # Body bytes this request has already taken off the wire. Reset per request,
    # and a class default so a handler-level test that calls one method directly
    # still has it.
    _body_consumed: int = 0

    def _read_body(self, length: int) -> bytes:
        """Read a declared body, remembering how much of it is now gone.

        Every refusal that follows a successful read used to re-drain the same
        bytes: `_drain_body` reads Content-Length again, the peer has nothing
        left to send, and `read1` blocks until REJECT_DRAIN_SECONDS gives up. So
        a validation 400 — an unusable question, a bad option list — cost its
        handler thread the full 250ms drain, measured on the shipped /api/ask
        route. Counting what was consumed leaves the drain for what it is for: a
        peer still mid-write.
        """
        body: bytes = self.rfile.read(length)
        self._body_consumed += len(body)
        return body

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
        remaining = max(0, min(declared - self._body_consumed, self.REJECT_DRAIN_CAP_BYTES))
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

    def _host_admitted(self, host: str) -> bool:
        """Whether a host string is local enough for this server's bind.

        The default loopback bind keeps the exact LOCAL_HOSTS gate. A
        non-loopback bind (--host 0.0.0.0 or an explicit address) is the
        operator's opt-in to remote access, so the gate widens to the address
        they asked for: exactly that address, or under 0.0.0.0 any address a
        client could reach the machine on.

        It widens to *addresses*, never to names, and that is the whole
        rebinding defense rather than a tidiness rule. `Host` and `Origin` are
        attacker-chosen strings, so admitting any non-empty one hands a page on
        `http://evil.example:4553` both `/api/data` and every POST route the
        moment its DNS points at this machine — measured before this narrowing,
        against a 0.0.0.0 bind. Rebinding needs a name to rebind; an operator
        typing a remote dashboard's URL has a literal address to type, so
        refusing every name costs them nothing and closes it.
        """
        if host in self.LOCAL_HOSTS:
            return True
        bound = getattr(self.server, "bound_host", "127.0.0.1")
        if bound == "127.0.0.1":
            return False
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            return False  # a DNS name, or garbage
        if bound == "0.0.0.0":  # noqa: S104
            # The operator asked for every interface, so any address a client
            # could have arrived on is theirs. The wildcard itself is not a
            # connectable destination, and neither is a multicast group.
            return not (literal.is_unspecified or literal.is_multicast)
        # `cli.BIND_HOSTS` no longer produces a bind that reaches here, but this
        # server is constructible directly, so the gate answers for whatever
        # address it was actually given rather than assuming the launcher.
        return host == bound

    def _local_ok(self, *, allow_cross_site_navigation: bool = False) -> bool:
        if not self._host_admitted(normalize_host(self.headers.get("Host") or "")):
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
        if parsed.scheme != "http" or not self._host_admitted(parsed.hostname or ""):
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
        # And every parked poll, for the same reason: a poll is asleep in
        # wait(), not in the socket, so nothing else would tell it to stop.
        # Measured without this line, a poll mid-stop holds silently for the rest
        # of its timeout and then loses the connection when the process exits.
        # The asking session reads that as a transport failure rather than as the
        # decline the contract promises it.
        with contextlib.suppress(Exception):
            self.server.application.state.asks.decline_all()
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
        if url.path == "/" and "next" not in parse_qs(url.query, keep_blank_values=True):
            self._send(self.server.page_bytes, "text/html; charset=utf-8")
        elif not self._get_api(url):
            self.send_error(404)

    def _get_api(self, url: ParseResult) -> bool:
        """Route one GET API path, or return False so `do_GET` can 404 it.

        Split off the page arm rather than kept as one chain: adding the
        observer route took the single method to mccabe 11 against ruff's cap
        of 10, and this file has never needed a complexity exemption. The
        split keeps the next route free rather than buying it one.
        """
        if url.path == "/api/data":
            self._data(url)
        elif url.path == "/api/overlays":
            self._overlays()
        elif url.path == "/api/cleared":
            self._cleared()
        elif url.path.startswith("/api/ask/"):
            # Prefix-matched, so it cannot join the exact-match arms above.
            self._ask_poll(url.path[len("/api/ask/") :])
        elif url.path == "/api/stream":
            self._stream()
        elif url.path == "/api/health":
            self._health()
        elif url.path == "/api/observe":
            self._observe(url)
        else:
            return False
        return True

    def _data(self, url: ParseResult) -> None:
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

    def _observe(self, url: ParseResult) -> None:
        """Trigger the observer analyzer on demand and return the sidecar JSON.

        A thin trigger, not a polling endpoint: read the transcript + entity
        dir, derive goal + stage + block, write the sidecar, return the JSON.
        The operator triggers it by clicking "observe" on a session card.
        Strictly same-origin: the route answers only loopback requests.
        """
        if not self._local_ok():
            self.send_error(403)
            return
        query = parse_qs(url.query)
        harness = query.get("harness", [""])[0]
        sid = query.get("sid", [""])[0]
        if not harness or not sid:
            self.send_error(400, "harness and sid are required")
            return
        application = self.server.application
        config = application.config
        state = application.state
        transcript_path = runtime_observer.resolve_transcript(config, state, harness, sid)
        if transcript_path is None:
            self.send_error(404, "session transcript not found")
            return
        # The same clock and window the collection runs on, so the observer's
        # freshness gate and a strip's agree about what is in flight.
        now = application.clock()
        result = runtime_observer.analyze(
            config,
            state,
            transcript_path,
            now=now,
            window_sec=config.window_hours * 3600,
        )
        if runtime_observer.write_sidecar(config, harness, sid, result) is None:
            # Refused, not fallen back: the names reached the transcript resolver
            # so they are shaped ids, and there is no second place a sidecar goes.
            # A failed write reads the same here, so the message names the
            # outcome rather than one of its two causes.
            self.send_error(400, "the observation could not be recorded")
            return
        self._send(json.dumps(result).encode(), "application/json")

    def _overlays(self) -> None:
        """The live overlay ledger, for diagnosing a row the reducer produced.

        Strictly same-origin, unlike `/api/data`: nothing renders this, so
        `do_GET`'s navigation relaxation has no reason to reach it.

        503 rather than 404 with no coordinator, because under `--no-events` the
        route exists and the ledger does not, and a 404 would read as a build too
        old to have the route.

        Disputes ride along rather than getting a route of their own: they are
        read against the ledger that produced them, and two requests to compare
        them would be two instants.
        """
        if not self._local_ok():
            self.send_error(403)
            return
        observation = self.server.observation
        if observation is None:
            self.send_error(503, "no event coordinator on this server")
            return
        report = observation.ledger_report()
        state = self.server.application.state
        with state.dispute_lock:
            report["dispute_total"] = state.dispute_total
            # Copied, not referenced: an open episode's record is updated in
            # place under that lock, and serializing the live dict outside it
            # could publish a fresh `repeats` beside a stale `last_seen_at`.
            # Shallow is enough; the nested values are written once.
            report["disputes"] = [dict(record) for record in state.disputes]
        self._send(json.dumps(report).encode(), "application/json")

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

    def _cleared(self) -> None:
        """The sessions marked handled: two identifiers and a timestamp each.

        Strictly same-origin, like `/api/overlays`: nothing navigates here, so
        `do_GET`'s navigation relaxation has no reason to reach it.

        A route of its own rather than a variant of `/api/data`. Publishing the
        cleared rows back into `sessions` behind a query flag would put them in
        front of every consumer that derives a total from that array — the tab
        title, the gate queue, calm's idle clip — and each would need to know
        which request it was answering. This answers a different question, so it
        is a different response.
        """
        if not self._local_ok():
            self.send_error(403)
            return
        application = self.server.application
        if not application.config.dismissals_enabled:
            self.send_error(503, "dismissals are disabled on this server")
            return
        entries = dismissals.active(application.config, application.state)
        self._send(
            json.dumps({"cleared": dismissals.rows(entries)}, separators=(",", ":")).encode(),
            "application/json",
        )

    def _ask_poll(self, ask_id: str) -> None:
        """One bounded hold on a question's answer, for the peer that asked it.

        Strictly same-origin, like `/api/cleared`: the poller is a local MCP
        server, and nothing navigates here.

        Bounded rather than held until a reader clicks. A request that returned
        only on an answer would pin a handler thread for as long as a human
        takes, with nothing to join it at shutdown; docs/design-ask-lane.md
        records why that was rejected in favour of a repeated short poll.
        """
        if not self._local_ok():
            self.send_error(403)
            return
        application = self.server.application
        config = application.config
        if not config.ask_enabled:
            # 503 rather than 404, the same call `/api/cleared` makes under
            # `--no-dismiss`: the route exists and the registry does not.
            self.send_error(503, "the ask lane is disabled on this server")
            return
        ask = application.state.asks.get(ask_id)
        if ask is None:
            self.send_error(404)
            return
        outcome = ask.wait(timeout=config.ask_poll_timeout_sec)
        if outcome is None:
            # 204 rather than an empty 200: "nothing yet, ask again" is already
            # in the status line, so there is no body for it to disagree with.
            self.send_response(204)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        name, index = outcome
        answer: dict[str, Any] = {"state": name}
        if index is not None:
            answer["index"] = index
        # Released before the write, not after: the outcome is settled either
        # way, and a peer that vanished mid-reply must not leave a resolved ask
        # in the table for the deadline to sweep.
        application.state.asks.release(ask_id)
        self._send(json.dumps(answer, separators=(",", ":")).encode(), "application/json")

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
            payload = json.loads(self._read_body(length) or b"{}")
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

    def _dismiss(self) -> None:
        """Mark one session handled, or put one back.

        Guarded exactly like `/api/usage`: `_local_ok()` has already run, the
        declared length is checked before any read, and a malformed or non-object
        body degrades to `{}` — which names no session and therefore does nothing.

        No capability token, and that is deliberate rather than an omission. This
        is an action the page takes on the reader's behalf, and `/api/shutdown` —
        a strictly larger power over the same server — is gated by `_local_ok()`
        alone. The body carries no timestamp, so the worst a forged request can do
        is hide a row until that session's next write.

        `persisted` is answered honestly: an unwritable home still hides the row
        for this run, and the page says so rather than implying the mark will
        survive a restart.
        """
        application = self.server.application
        config = application.config
        if not config.dismissals_enabled:
            # 503, not 404, for the reason `/api/overlays` answers 503 with no
            # coordinator: under `--no-dismiss` the route exists and the store
            # does not, and a 404 would read as a build too old to have it.
            self._reject(503)
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if not 0 <= length <= config.dismissal_body_cap_bytes:
            self._reject(413)
            return
        try:
            payload = json.loads(self._read_body(length) or b"{}")
        except (ValueError, json.JSONDecodeError, RecursionError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        state = application.state
        harness, sid = payload.get("harness"), payload.get("sid")
        if payload.get("clear") is False:
            persisted = dismissals.restore(
                config, state, harness, sid, diagnostic_sink=application.diagnostic_sink
            )
        else:
            persisted = dismissals.dismiss(
                config,
                state,
                harness,
                sid,
                now=application.clock(),
                diagnostic_sink=application.diagnostic_sink,
            )
        # The published bodies are dropped rather than waited out. Without this
        # the next GET would serve the pre-dismissal payload for up to
        # `collect_memo_sec`, and a row that stays put for two seconds after the
        # click reads as a control that did not work.
        state.snapshot.clear()
        answer = {
            "ok": True,
            "persisted": persisted,
            "cleared": len(dismissals.active(config, state)),
        }
        self._send(json.dumps(answer, separators=(",", ":")).encode(), "application/json")

    def _events(self, harness: str) -> None:
        """A harness's lifecycle events, forwarded by its own hook.

        The harness comes from the route, never from the body: a payload field
        naming its own source would let one adapter's token post as any harness.
        The route alone proves nothing about the caller, so the capability is
        checked as well, which is the difference between this and `/api/notify`.

        Order is deliberate. Unknown route first, so an unsupported harness is a
        404 and not an authentication oracle. Then the capability. Then the rate
        ceiling, which is independent of the token because a looping adapter holds
        a valid one by definition. Then the length, before any read.
        """
        coordinator = self.server.observation
        if coordinator is None or harness not in runtime_events.IDENTITY_NORMALIZERS:
            self._reject(404)
            return
        if not coordinator.authorized(harness, self.headers.get("X-Cargento-Capability")):
            self._reject(403)
            return
        if not coordinator.within_budget(harness):
            self._reject(429)
            return
        config = self.server.application.config
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if not 0 <= length <= config.event_body_cap_bytes:
            self._reject(413)
            return
        try:
            payload = json.loads(self._read_body(length) or b"{}")
        except (ValueError, json.JSONDecodeError, RecursionError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        outcome = coordinator.submit(harness, payload)
        # Always 200, even for a rejected envelope. The hook must not learn to
        # retry, and must never be the reason an agent session stalls; the
        # outcome string is for diagnostics.
        self._send(
            json.dumps({"ok": True, "outcome": outcome}, separators=(",", ":")).encode(),
            "application/json",
        )

    def do_POST(self) -> None:
        self._body_consumed = 0
        if not self._local_ok():
            self._reject(403)
            return
        path = urlparse(self.path).path
        # Prefix-matched, so it cannot join the exact-match table below.
        if path.startswith("/api/events/"):
            self._events(path[len("/api/events/") :])
            return
        # A table rather than a ladder of ifs: every entry is one route to one
        # handler, and the ladder had grown to the point where the last branch
        # carried a whole request body inline while the ones above it did not.
        route = {
            "/api/shutdown": self._shutdown,
            "/api/usage": self._usage_receipt,
            "/api/dismiss": self._dismiss,
            "/api/ask": self._ask,
            "/api/ask/withdraw": self._withdraw,
            "/api/answer": self._answer,
            "/api/notify": self._notify,
        }.get(path)
        if route is None:
            self._reject(404)
            return
        route()

    def _notify(self) -> None:
        """Claude Code's Notification hook: {"session_id": ..., "message": ..., ...}."""
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
            payload = json.loads(self._read_body(length) or b"{}")
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

    def _ask_unavailable(self, reason: str, *, body_read: bool) -> None:
        """Refuse an ask route at 503, saying which kind of no this is.

        503 for both reasons, because both are honest "not right now" answers
        rather than anything the caller got wrong. What the machine-readable
        reason adds is whether waiting helps: a `disabled` build will never take
        a question and a `busy` one will as soon as a slot frees. A bare 503 was
        indistinguishable from a wrong port, and the stdio server read it as one:
        it walked on to the next candidate and registered the question on a
        second dashboard that had the lane switched on, defeating `--no-ask`.

        `_reject` cannot carry a body, hence `_send` at 503. The drain `_reject`
        would have done is conditional here: on the refusal that happens before
        the body is read it is still required, because closing a socket over
        unread inbound data makes the OS send RST and the reply already written
        can be discarded. After the body has been read it would be actively
        wrong, since a second read on a keep-alive connection would consume the
        next request's bytes.
        """
        if not body_read:
            self._drain_body()
        self._send(
            json.dumps({"ok": False, "reason": reason}, separators=(",", ":")).encode(),
            "application/json",
            503,
        )

    @staticmethod
    def _ask_options(value: Any, *, cap_chars: int, max_options: int) -> tuple[str, ...] | None:
        """The offered options, bounded in count and length, or None if unusable.

        Past `max_options` the leading options are kept rather than a sample,
        and an option that bounds to empty refuses the whole request rather than
        being dropped. Both follow from the answer being an index: the asking
        peer resolves it against its own copy of the list, so keeping a prefix
        stays aligned with that copy while dropping a member from the middle
        would silently shift every later index onto the wrong option.

        A non-string member is refused rather than coerced. `records.safe_text`
        does `str(value or "")`, so it does not fail on one: `[{"a": 1}]`
        published the label `{'a': 1}`, and falsiness rather than type decided
        the rest, which is why `[1, 2]` was accepted while `[0, 1]` was refused.
        The answer is an index into this tuple, so a stringified option is a
        choice the asking session never offered.
        """
        if not isinstance(value, list):
            return None
        offered = value[:max_options]
        if not all(isinstance(item, str) for item in offered):
            return None
        options = tuple(records.safe_text(item, cap_chars).strip() for item in offered)
        # Two is the floor for a question worth putting on the board: one option
        # is not a choice, and nothing can be rendered from an empty list.
        return None if len(options) < 2 or not all(options) else options

    def _ask(self) -> None:
        """Register a question a session is holding its tool call open for.

        Guarded exactly like `/api/dismiss`: `_local_ok()` has already run, the
        declared length is checked before any read, and a malformed or non-object
        body degrades to `{}`.

        Where it differs is that an unusable body is a 400 rather than a 200
        no-op, and the difference is the point. A dismissal naming nothing has
        nothing to do; a caller here is about to wait for an answer, and has to
        learn now that none is coming rather than after the deadline.

        This route also owns the server half of the ask notification, below the
        reply. The browser half is gated by `native_notify` in the payload, which
        is the same reading this makes — exactly one layer alerts for one
        question.

        This is the only place the question and the options are bounded. `asks`
        imports nothing, so it cannot reach `records.safe_text`, and every field
        read below was written by an agent.
        """
        application = self.server.application
        config = application.config
        if not config.ask_enabled:
            self._ask_unavailable("disabled", body_read=False)
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if not 0 <= length <= config.ask_body_cap_bytes:
            self._reject(413)
            return
        try:
            payload = json.loads(self._read_body(length) or b"{}")
        except (ValueError, json.JSONDecodeError, RecursionError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        raw_question = payload.get("question")
        # Type-checked before it is bounded, for the reason `_ask_options` gives:
        # `safe_text` would turn a non-string into its Python repr and publish
        # that as the question. Falling through to the empty string keeps one 400
        # path for every unusable body.
        question = (
            records.safe_text(raw_question, config.ask_question_cap_chars).strip()
            if isinstance(raw_question, str)
            else ""
        )
        options = self._ask_options(
            payload.get("options"),
            cap_chars=config.ask_option_cap_chars,
            max_options=config.ask_max_options,
        )
        if not question or options is None:
            self._reject(400)
            return
        label_cap = config.ask_option_cap_chars
        ask = runtime_asks.PendingAsk(
            # harness and session_id share the option cap: they really are short
            # labels of the same order. `project` does not, and gets its own knob
            # below, because it is a filesystem path.
            harness=records.safe_text(payload.get("harness"), label_cap).strip(),
            session_id=records.safe_text(payload.get("session_id"), label_cap).strip(),
            project=self._ask_project(payload.get("project")),
            question=question,
            options=options,
            created=application.clock(),
        )
        if not application.state.asks.register(
            ask,
            limit=config.ask_max_pending,
            deadline=config.ask_deadline_sec,
            retention=config.ask_retention_sec,
        ):
            self._ask_unavailable("busy", body_read=True)
            return
        # The published bodies are dropped rather than waited out, exactly as a
        # dismissal drops them.
        application.state.snapshot.clear()
        # Dropping the body is not a wake path on its own: nothing collects until
        # something asks it to, and a dashboard with no browser tab open asks for
        # nothing. Measured before this call existed: 18.2 to 22.3 s to first
        # render on the default build, where the page's own 20-second fallback
        # poll was what eventually noticed.
        #
        # After `register` has returned, and never inside it: `note_ask` takes
        # `Observation._lock`, and `_due` reads the registry while holding that
        # lock, so this is the only order that stays acyclic. `AskRegistry` and
        # `Observation.note_ask` carry the same note.
        #
        # None under `--no-events`, where there is no coordinator to wake and
        # `lifecycle.run_producer` is collecting on its own timer instead.
        coordinator = self.server.observation
        if coordinator is not None:
            coordinator.note_ask()
        self._send(
            json.dumps({"ok": True, "id": ask.id}, separators=(",", ":")).encode(),
            "application/json",
        )
        # Gated on the same expression `/api/data` publishes as `native_notify`,
        # and not on `notify_mac`'s own platform guard: the page decides whether
        # to raise its own notification by reading that field, so a second,
        # independent reading is a second place the one-layer rule can drift —
        # and it does drift for an injected notifier.
        #
        # After `_send` and not before, unlike `/api/notify`. osascript runs on
        # this handler thread with a 5s timeout, against the stdio client's 3s
        # register POST: a lost reply is not a retry there, it walks to the next
        # candidate port and registers the question on a second dashboard while
        # this one keeps a card nobody can withdraw, because its id was in the
        # reply that never arrived. `_send` writes through an unbuffered wfile, so
        # the bytes are on the socket by the time this runs.
        if application.native_notifier(config.platform_name):
            notifications.maybe_ask_popup(
                config,
                application.state,
                notifications.AskSubject(
                    label=application.harness_label(ask.harness),
                    question=ask.question,
                    project=ask.project,
                ),
                now=ask.created,
                popup_notifier=application.popup_notifier,
            )

    def _ask_project(self, value: object) -> str:
        """The asking session's directory, bounded but still identifiable.

        `safe_text` truncates from the front, which is wrong for a path: the
        distinctive part is the tail. A 122-character cwd against the old
        120-char label cap published `.../e2e/adop` for a directory named
        `adopt2`, so the card named somewhere that does not exist. An over-long
        path therefore keeps its end and marks the cut.
        """
        config = self.server.application.config
        cap = config.ask_project_cap_chars
        # Stripped at the request body's own cap, not at `cap`: `safe_text`
        # truncates from the front, so pre-trimming to anything near `cap` throws
        # away the very tail this method exists to keep. The body cap already
        # bounds how much can arrive, so this cannot run long.
        project = records.safe_text(value, config.ask_body_cap_bytes).strip()
        if len(project) > cap:
            return "\u2026" + project[-(cap - 1) :]
        return project

    def _withdraw(self) -> None:
        """Take a question off the board on its asking session's behalf.

        The session that asked is the one that gives up: its tool call was
        aborted, or its poll ran out. Without this route the card stayed
        clickable for the rest of the deadline, and the reader's click was
        accepted and thrown away, so a person answered a question nobody was
        listening for and was told nothing about it.

        A 200 for an unknown id, exactly as `/api/answer` gives one: a 404 would
        make this an oracle for which asks exist. The caller reads `withdrawn`.

        Bounded at the answer route's cap rather than the register route's: the
        body carries an id and nothing else.
        """
        application = self.server.application
        config = application.config
        if not config.ask_enabled:
            self._ask_unavailable("disabled", body_read=False)
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if not 0 <= length <= config.ask_answer_body_cap_bytes:
            self._reject(413)
            return
        try:
            payload = json.loads(self._read_body(length) or b"{}")
        except (ValueError, json.JSONDecodeError, RecursionError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        ask_id = payload.get("id")
        withdrawn = isinstance(ask_id, str) and application.state.asks.withdraw(ask_id)
        if withdrawn:
            # The same reason an answer drops it: a card that has left the
            # registry has to leave the board on the next collection, or it goes
            # on offering a choice nobody can act on.
            application.state.snapshot.clear()
        self._send(
            json.dumps({"ok": True, "withdrawn": withdrawn}, separators=(",", ":")).encode(),
            "application/json",
        )

    def _answer(self) -> None:
        """Record the option the reader chose.

        Guarded exactly like `/api/dismiss`, and a no-op in the same way: an
        unknown id, a non-integer index and an out-of-range one all answer 200
        with `answered: false`. A 404 for an unknown id would turn this route
        into an oracle for which asks exist, so the page reads `answered` rather
        than the status line to decide whether anyone heard.
        """
        application = self.server.application
        config = application.config
        if not config.ask_enabled:
            self._reject(503)
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if not 0 <= length <= config.ask_answer_body_cap_bytes:
            self._reject(413)
            return
        try:
            payload = json.loads(self._read_body(length) or b"{}")
        except (ValueError, json.JSONDecodeError, RecursionError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        ask_id, index = payload.get("id"), payload.get("index")
        answered = (
            isinstance(ask_id, str)
            and isinstance(index, int)
            # A bool IS an int in Python, so `"index": true` would otherwise
            # answer option 1 for a body that named no option at all.
            and not isinstance(index, bool)
            and application.state.asks.answer(ask_id, index)
        )
        if answered:
            # The card has to leave the board on the next collection, or it goes
            # on offering a choice that has already been made.
            application.state.snapshot.clear()
        self._send(
            json.dumps({"ok": True, "answered": answered}, separators=(",", ":")).encode(),
            "application/json",
        )

    def log_message(self, *args: Any) -> None:
        pass  # keep the terminal quiet
