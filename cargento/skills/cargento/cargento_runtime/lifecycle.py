"""Process lifecycle: the state file, port probes, stop, and daemon detach."""

from __future__ import annotations

import argparse
import contextlib
import errno
import http.client
import json
import math
import os
import select
import socket
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from cargento_runtime import config as runtime_config
from cargento_runtime import http_api
from cargento_runtime import io as runtime_io

if TYPE_CHECKING:
    from collections.abc import Callable

    from cargento_runtime.config import RuntimeConfig

_FORK: Callable[[], int] | None = getattr(os, "fork", None)
_SETSID: Callable[[], int] | None = getattr(os, "setsid", None)


def tcp_port(value: str) -> int:
    """An argparse type for a real TCP port, rather than any Python integer."""
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer from 1 to 65535") from exc
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("must be from 1 to 65535")
    return port


def cargento_home(config: RuntimeConfig) -> str:
    """Where the state file and the daemon log live.

    One layout on every platform. Platform-correct runtime directories
    (XDG_RUNTIME_DIR, %LOCALAPPDATA%) would be three code paths and three ways
    for --status to look somewhere the server never wrote. A nonblank
    CARGENTO_HOME is authoritative, which is the rule the harness store
    variables in STORE_ENV_VARS already follow, and ``build_runtime_config``
    has already applied it — so this reads the frozen value rather than the
    environment a second time.

    ``state_home``, not ``str(state_dir)``: round-tripping an override through a
    native Path rewrites its separators on Windows, which changes the string
    --status prints and breaks the dirname contract callers rely on.
    """
    return config.state_home


def state_path(config: RuntimeConfig, port: int) -> str:
    return os.path.join(cargento_home(config), f"cargento-{port}.json")


def log_path(config: RuntimeConfig, port: int) -> str:
    return os.path.join(cargento_home(config), f"cargento-{port}.log")


def ensure_cargento_home(config: RuntimeConfig) -> str:
    """Create the state directory, owner-only, and return it.

    0o700 because the log carries tracebacks with local paths in them. The mode
    is advisory: it does not apply to a directory that already exists, and
    Windows ignores it.
    """
    home = cargento_home(config)
    os.makedirs(home, mode=0o700, exist_ok=True)
    return home


def write_state(
    config: RuntimeConfig,
    port: int,
    *,
    started: float,
    capabilities: dict[str, str] | None = None,
    diagnostic_sink: Callable[[str], None] = print,
) -> None:
    """Record this process as the instance serving `port`.

    Written by every instance that binds, daemon or foreground: --status and
    --stop are worth having either way, and a file that exists only sometimes
    is a file whose absence tells you nothing.

    Written through a temp file and os.replace so a reader mid-write sees the
    old file or the new one, never half of one.

    `capabilities` is how an adapter learns its event-ingress token. This file is
    the only place it is published, and it is chmodded to owner-only for that
    reason: the token is what stands between a local process and the ability to
    forge lifecycle state. The mode is advisory, exactly as
    `ensure_cargento_home`'s is, and Windows ignores it, so `SECURITY.md` records
    what that does and does not buy rather than implying isolation.
    """
    payload: dict[str, Any] = {
        "pid": os.getpid(),
        "port": port,
        "started": started,
        "log": log_path(config, port),
        "python": sys.executable,
    }
    if capabilities:
        payload["capabilities"] = capabilities
    target = state_path(config, port)
    tmp = f"{target}.{os.getpid()}.tmp"
    try:
        ensure_cargento_home(config)
        # Opened through os.open with the mode in the call rather than chmodded
        # afterwards: a chmod leaves a window in which the file exists
        # world-readable, and the token is in it from the first byte.
        handle_fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(handle_fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        os.replace(tmp, target)
    except OSError as exc:
        runtime_io.diag(
            f"Cargento: could not write {target} ({exc}); --status will not see this instance",
            diagnostic_sink,
        )
        with contextlib.suppress(OSError):
            os.unlink(tmp)


def read_state(config: RuntimeConfig, port: int) -> dict[str, Any] | None:
    """The recorded state for `port`, or None if there is none to trust.

    Read to a cap and with RecursionError caught, because "none to trust" has to
    include a corrupt file and not just a missing one. The payload write_state
    produces is a few hundred bytes; deeply nested JSON blows the recursion
    limit rather than raising ValueError, which tracebacked straight out of
    --status and --stop. do_POST already catches RecursionError for the same
    reason on the same parser.
    """
    cap = config.state_read_cap_bytes
    try:
        with open(state_path(config, port), "rb") as handle:
            raw = handle.read(cap + 1)
        if len(raw) > cap:
            return None
        data = json.loads(raw or b"null")
    except (OSError, ValueError, RecursionError):
        return None
    return data if isinstance(data, dict) else None


def remove_state(config: RuntimeConfig, port: int) -> None:
    with contextlib.suppress(OSError):
        os.unlink(state_path(config, port))


def probe_port(port: int, timeout: float = 1.0) -> tuple[str, dict[str, Any] | None]:
    """What is listening on `port`: Cargento, something else, or nothing.

    Returns ("cargento", health) | ("foreign", None) | ("closed", None).

    The distinction is the entire point of this function. "Something is
    listening" reading as "Cargento is running" is how a stop command ends up
    aimed at an unrelated local server.
    """
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request("GET", "/api/health")
        response = conn.getresponse()
        body = response.read(4096)
        if response.status != 200:
            return ("foreign", None)
        data = json.loads(body)
    except (OSError, http.client.HTTPException):
        return ("closed", None)
    except (ValueError, RecursionError):
        return ("foreign", None)  # answered 200 with something that is not JSON
    finally:
        conn.close()
    if not isinstance(data, dict):
        return ("foreign", None)
    pid = data.get("pid")
    reported_port = data.get("port")
    started = data.get("started")
    if (
        data.get("ok") is not True
        or not isinstance(pid, int)
        or isinstance(pid, bool)
        or pid <= 0
        or not isinstance(reported_port, int)
        or isinstance(reported_port, bool)
        or reported_port != port
        or not isinstance(started, int | float)
        or isinstance(started, bool)
        or not math.isfinite(started)
    ):
        return ("foreign", None)
    return ("cargento", data)


def port_released(config: RuntimeConfig, port: int) -> bool:
    """Whether a new listener could take `port` — the question --stop's caller
    actually has, since what follows a stop is usually a start.

    By binding, because binding is the question. Tried and rejected: a TCP
    connect probe. Connecting to a listening socket that nothing is accepting
    from still completes, so it cannot see the window between `serve_forever()`
    returning and `server_close()` running — and worse, each probe leaves an
    unaccepted connection in the backlog, so after `request_queue_size` of them
    the probe starts reporting "gone" for a port that is still bound. Same
    reuse semantics as the real listener, so this answers for that listener and
    not for a hypothetical one with different options.
    """
    windows = config.os_name == "nt"
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if http_api.reuse_address_allowed(config.os_name):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # Windows-only, and the same option CargentoHTTPServer.server_bind
            # sets. Without it the probe is more permissive than the listener it
            # answers for: a foreign socket holding the port with SO_REUSEADDR
            # admits a plain bind but not an exclusive one, so the probe would
            # report a port released that the real listener cannot take.
            exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
            if exclusive is not None and not http_api.reuse_address_allowed(config.os_name):
                sock.setsockopt(socket.SOL_SOCKET, exclusive, 1)
            sock.bind(("127.0.0.1", port))
    except OSError as exc:
        # Only "the address is in use" is evidence the port is held. EACCES on a
        # privileged port, or an exhausted fd table, says nothing about use —
        # and answering False there made --stop sit out its entire timeout and
        # then report an instance still listening when it had already stopped.
        # Where a bind cannot answer the question, say so by answering True: the
        # caller is deciding whether to keep waiting, not whether to trust it.
        winerror = getattr(exc, "winerror", None)
        if exc.errno == errno.EADDRINUSE or winerror == 10048:  # WSAEADDRINUSE
            return False
        # On Windows an in-use port also reports EACCES once SO_EXCLUSIVEADDRUSE
        # is in play — the same ambiguity bind_error_message already names.
        return not (windows and (exc.errno == errno.EACCES or winerror == 10013))
    return True


def await_release(config: RuntimeConfig, port: int, timeout: float | None = None) -> bool:
    """Wait for `port` to become bindable. Returns whether it did.

    Always probes at least once, so a zero timeout still answers.

    The default is read here rather than bound in the signature: a default
    evaluated at import cannot be patched, so a caller lowering the release
    timeout — every test that does — silently waited the full five seconds
    anyway.
    """
    limit = config.stop_release_timeout_sec if timeout is None else timeout
    deadline = time.monotonic() + limit
    while True:
        if port_released(config, port):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)


def instance_status(config: RuntimeConfig, port: int) -> dict[str, Any]:
    """Whether Cargento is on `port`, and what to say about it if not."""
    kind, health = probe_port(port)
    state = read_state(config, port)
    recorded_log = (state or {}).get("log") or log_path(config, port)
    if kind == "cargento" and health is not None:
        return {
            "state": "running",
            "port": port,
            "pid": health["pid"],
            "started": health.get("started"),
            "log": recorded_log,
        }
    if kind == "foreign":
        return {"state": "foreign", "port": port, "pid": (state or {}).get("pid")}
    return {
        "state": "stale" if state is not None else "absent",
        "port": port,
        "pid": (state or {}).get("pid"),
        "log": recorded_log,
    }


def render_status(status: dict[str, Any]) -> str:
    """One line describing an instance, for --status and --stop."""
    port = status["port"]
    state = status["state"]
    if state == "running":
        started = status.get("started")
        since = "unknown"
        if isinstance(started, int | float) and started:
            # `started` arrives from whatever answered /api/health — the one
            # process probe_port has just declined to take on trust. A value
            # outside time_t, or NaN, raises here rather than printing a line.
            with contextlib.suppress(OverflowError, ValueError, OSError):
                since = datetime.fromtimestamp(started, tz=UTC).astimezone().strftime("%H:%M")
        return (
            f"Cargento: running on port {port} (pid {status['pid']}, since {since}) "
            f"http://127.0.0.1:{port}/"
        )
    if state == "foreign":
        return (
            f"Cargento: port {port} is held by another process — what answered "
            f"/api/health is not Cargento. Nothing was stopped or removed."
        )
    if state == "stale":
        return (
            f"Cargento: not running on port {port}. A stale state file remains "
            f"(pid {status['pid']}); --stop removes it."
        )
    return f"Cargento: not running on port {port}."


def stop_instance(config: RuntimeConfig, port: int) -> tuple[str, int]:
    """Ask the instance on `port` to stop. Returns (message, exit code).

    Over HTTP, the same route the page's stop button uses — one implementation
    of stopping, and no per-platform signal semantics to reconcile. A server
    wedged badly enough not to serve cannot be stopped this way; SKILL.md keeps
    the platform kill commands for that.
    """
    status = instance_status(config, port)
    state = status["state"]
    if state == "foreign":
        # The state file is evidence about a port we do not own. Leave it.
        return (render_status(status), 1)
    if state == "running":
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        failure = ""
        answered: int | None = None
        try:
            conn.request("POST", "/api/shutdown", body=b"", headers={"Content-Length": "0"})
            response = conn.getresponse()
            response.read(1024)
            answered = response.status
        except (OSError, http.client.HTTPException) as exc:
            # Not evidence the stop failed. A concurrent --stop, or the page's
            # own button, may already have taken the server down while this
            # request was in flight — which reset the connection and reported a
            # failure for a stop that had in fact just happened. Let the port
            # decide instead of this connection.
            failure = f"{type(exc).__name__}: {exc}"
        finally:
            conn.close()
        if answered is not None and answered != 200:
            return (f"Cargento: the instance on port {port} refused to stop ({answered}).", 1)
        # Do not claim it stopped until the port is actually free. The handler
        # answers before shutting down, `shutdown()` takes up to one poll
        # interval to be noticed, and the listening socket closes only after
        # serve_forever() returns — so returning on the 200 alone reported a
        # completed stop while the port was still bound, and the obvious restart
        # (--stop then start again) failed on a busy port.
        if not await_release(config, port):
            if failure:
                return (f"Cargento: could not stop port {port} — {failure}", 1)
            return (
                (
                    f"Cargento: asked the instance on port {port} (pid {status['pid']}) to "
                    f"stop, and it agreed, but it was still listening "
                    f"{config.stop_release_timeout_sec:.0f}s later. "
                    f"Check --status before restarting."
                ),
                1,
            )
        return (f"Cargento: stopped (pid {status['pid']}) on port {port}.", 0)
    # Nothing answered /api/health, which is not the same as nothing holding the
    # port: the serving process removes the state file *before* it closes the
    # listener, so a stop already in progress lands here with the port still
    # bound. Exit 0 has to mean a new listener can take the port, or the
    # unconditional --stop-then-start this promises is not safe.
    if not await_release(config, port):
        return (
            (
                f"Cargento: nothing on port {port} answers /api/health, but something is "
                f"still holding the port. Nothing was stopped or removed."
            ),
            1,
        )
    if state == "stale":
        remove_state(config, port)
        return (f"Cargento: nothing running on port {port}; removed the stale state file.", 0)
    # Nothing there and nothing recorded. Stopping is idempotent on purpose:
    # a script that calls --stop unconditionally should not fail for it.
    return (f"Cargento: nothing running on port {port}.", 0)


def fork_daemon(
    *,
    fork: Callable[[], int] | None = None,
    setsid: Callable[[], int] | None = None,
    exit_intermediate: Callable[[int], None] | None = None,
) -> tuple[str, int]:
    """Split this process into a detached daemon and a reporting parent.

    Returns ("parent", read_fd) in the original process, which must report what
    the daemon says and then exit, and ("daemon", write_fd) in the detached
    process, which must serve.

    Why the parent reports rather than the daemon: an agent's shell tool stops
    capturing output when the process it waited for exits, so a line printed by
    the detached child afterwards is simply lost. The pipe also makes the
    report *true* — the parent says "running" because the daemon said so.

    Why two forks: the first detaches from the caller, setsid leaves the
    session and its controlling terminal, and the second means the daemon is
    not a session leader, so it can never reacquire one.

    The hooks exist so the call sequence can be asserted without a test suite
    that forks itself.
    """
    do_fork = fork or _FORK
    do_setsid = setsid or _SETSID
    do_exit = exit_intermediate or os._exit
    if do_fork is None or do_setsid is None:  # pragma: no cover — POSIX-only path
        raise RuntimeError("--daemon needs fork/setsid; use the Windows re-spawn path")
    read_fd, write_fd = os.pipe()
    if do_fork() > 0:
        os.close(write_fd)
        return ("parent", read_fd)
    os.close(read_fd)
    do_setsid()
    if do_fork() > 0:
        do_exit(0)
    return ("daemon", write_fd)


def daemon_redirect_stdio(log_file: str) -> None:
    """Point stdio at the log, once there is nothing left to say on the terminal.

    dup2 rather than reassigning sys.stdout: writes from C and an uncaught
    traceback go to fd 1 and 2 directly, and those are exactly the output a
    detached failure leaves behind.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    with open(os.devnull, "rb") as devnull:
        os.dup2(devnull.fileno(), 0)
    with open(log_file, "ab", buffering=0) as handle:
        os.dup2(handle.fileno(), 1)
        os.dup2(handle.fileno(), 2)


def daemon_announce(write_fd: int) -> None:
    """Tell the waiting parent this process is serving, and how to name it."""
    with contextlib.suppress(OSError):
        os.write(write_fd, f"{os.getpid()}\n".encode())
    with contextlib.suppress(OSError):
        os.close(write_fd)


def await_daemon(
    config: RuntimeConfig,
    read_fd: int,
    port: int,
    log_file: str,
    timeout: float | None = None,
) -> tuple[str, int]:
    """Wait for the forked daemon's pid. Returns (message, exit code).

    POSIX only, and unreachable elsewhere: select() on Windows accepts sockets
    and nothing else, so watching a pipe fd raises there. The launcher gives
    Windows the re-spawn path and await_spawned instead.

    The timeout default is read here, not bound in the signature, for the same
    reason as await_release: a value frozen at import cannot be lowered.
    """
    limit = config.daemon_ready_timeout_sec if timeout is None else timeout
    deadline = time.monotonic() + limit
    seen = b""
    died = False
    pipe_error: OSError | None = None
    try:
        while time.monotonic() < deadline:
            ready, _, _ = select.select([read_fd], [], [], 0.1)
            if not ready:
                continue
            chunk = os.read(read_fd, 64)
            if not chunk:
                died = True  # closed the pipe without announcing
                break
            seen += chunk
            if b"\n" in seen:
                break
    except OSError as exc:
        seen = b""
        pipe_error = exc
    finally:
        with contextlib.suppress(OSError):
            os.close(read_fd)
    pid = seen.strip().decode("ascii", "replace")
    if pid.isdigit():
        return (f"Cargento: http://127.0.0.1:{port}/ (pid {pid}, log {log_file})", 0)
    if pipe_error is not None:
        return (
            (
                f"Cargento: could not read the background server's readiness pipe "
                f"({type(pipe_error).__name__}: {pipe_error}) — check {log_file}."
            ),
            1,
        )
    if died:
        # Distinguished from the timeout because it is a different thing to go
        # and look at, and reporting a 10s wait that in fact took a moment sent
        # readers hunting for a hang that never happened.
        return (
            (
                f"Cargento: the background server exited before it began serving. "
                f"Its output was:\n{log_tail(log_file)}"
            ),
            1,
        )
    return (
        (
            f"Cargento: started in the background, but it did not report ready "
            f"within {limit:.0f}s — check {log_file}."
        ),
        1,
    )


def spawn_argv(config: RuntimeConfig, args: argparse.Namespace) -> list[str]:
    """The complete argv for a re-spawned child, built from parsed values.

    One contract, not a flags-only helper plus a caller that prefixes an
    interpreter and a script: the whole list lives here, so a Windows-path
    assertion can check the thing that actually runs.

    ``config.launcher_path`` is the only respawn target. Every opt-out the
    parent was given is forwarded, because Windows has no fork and so a daemon
    is always a respawn: a flag dropped here is a flag silently ignored for
    every Windows daemon user. --daemon is the one deliberate omission, since
    the child is an ordinary foreground run that happens to own no console and
    forwarding the flag would re-spawn forever. Rebuilding from the namespace
    rather than filtering argv means a future flag has to be added here
    consciously.
    """
    argv = [
        sys.executable,
        str(config.launcher_path),
        "--port",
        str(args.port),
        "--window-hours",
        str(args.window_hours),
    ]
    if args.no_spacedock:
        argv.append("--no-spacedock")
    if args.no_usage:
        argv.append("--no-usage")
    if args.no_git:
        argv.append("--no-git")
    if args.no_events:
        argv.append("--no-events")
    if args.no_dismiss:
        argv.append("--no-dismiss")
    if args.no_ask:
        argv.append("--no-ask")
    # Forward the bind host only when the operator chose a non-default address,
    # so a Windows --daemon re-spawn keeps a --host 0.0.0.0 bind instead of
    # silently reverting to loopback.
    host = getattr(args, "host", "127.0.0.1")
    if host != "127.0.0.1":
        argv.extend(["--host", host])
    return argv


def spawn_detached(
    config: RuntimeConfig, args: argparse.Namespace, log_file: str
) -> subprocess.Popen[bytes]:
    """Re-spawn the launcher with no console attached (Windows has no fork)."""
    creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0
    )
    with open(log_file, "ab", buffering=0) as handle:
        return subprocess.Popen(  # noqa: S603 — fixed argv from parsed flags, no shell
            spawn_argv(config, args),
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=handle,
            creationflags=creationflags,
            close_fds=True,
        )


def log_tail(log_file: str, limit: int = 2000) -> str:
    """The end of the daemon log — the only account of a failure the parent
    could not watch happen."""
    try:
        with open(log_file, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - limit))
            data = handle.read()
    except OSError:
        return f"(could not read {log_file})"
    return data.decode("utf-8", "replace").strip() or f"({log_file} is empty)"


def await_spawned(
    config: RuntimeConfig,
    proc: subprocess.Popen[bytes],
    port: int,
    log_file: str,
    timeout: float | None = None,
) -> tuple[str, int]:
    """Wait for the re-spawned child to answer. Returns (message, exit code).

    Windows cannot report the child's bind() to the parent, so the parent
    observes the consequence instead. That is what keeps the POSIX promise that
    a busy port explains itself on the terminal rather than only in a log.

    Which is why the answer has to be matched against the child's own pid. A
    dashboard already on that port answers /api/health perfectly well, and
    treating that as proof told the user their daemon had started when it had
    in fact lost the bind, handing back a pid belonging to someone else's
    process. The pid is in the health payload for exactly this reason.
    """
    limit = config.daemon_ready_timeout_sec if timeout is None else timeout
    deadline = time.monotonic() + limit
    foreign = False
    while time.monotonic() < deadline:
        kind, health = probe_port(port, timeout=0.5)
        if kind == "cargento" and health is not None:
            if health.get("pid") == proc.pid:
                return (
                    f"Cargento: http://127.0.0.1:{port}/ (pid {health['pid']}, log {log_file})",
                    0,
                )
            foreign = True  # someone else's dashboard; our child lost the bind
        if proc.poll() is not None:
            return (
                (
                    f"Cargento: the background server exited immediately "
                    f"(code {proc.returncode}). Its output was:\n{log_tail(log_file)}"
                ),
                1,
            )
        time.sleep(0.2)
    if foreign:
        return (
            (
                f"Cargento: port {port} is already served by a different Cargento, so "
                f"the one just started could not bind it. Look at that instance with "
                f"--status, or pick another port with --port."
            ),
            1,
        )
    return (
        (
            f"Cargento: started in the background, but nothing answered on port "
            f"{port} within {limit:.0f}s — check {log_file}."
        ),
        1,
    )


def prepare_daemon_home(
    config: RuntimeConfig,
    log_file: str,
    *,
    diagnostic_sink: Callable[[str], None] = print,
) -> bool:
    """Whether the state home and log are usable. Reports why if they are not.

    Explains a home that cannot be used, rather than tracebacking out of the
    documented start command. write_state() already degrades this way for a
    foreground run; detaching has nowhere to put its log without it.

    The log is opened here too, for the same reason the socket is bound before
    detaching: makedirs(exist_ok=True) succeeds for a directory that already
    exists whatever its mode, so the likeliest bad home of all — one that exists
    and is not writable — got past the guard and raised in daemon_redirect_stdio
    (or spawn_detached) instead, after the point where a message can still reach
    the terminal that asked. Failing there produced a raw traceback and then told
    the user to check the very file that could not be opened.
    """
    try:
        ensure_cargento_home(config)
        with open(log_file, "ab"):
            pass
    except OSError as exc:
        runtime_io.diag(
            f"Cargento: cannot use {cargento_home(config)} for the daemon state and log "
            f"({type(exc).__name__}: {exc}). Point {runtime_config.CARGENTO_HOME_ENV} at a "
            f"writable directory, or drop --daemon to run in the foreground.",
            diagnostic_sink,
        )
        return False
    return True


def run_producer(
    server: http_api.CargentoHTTPServer,
    *,
    stop: threading.Event,
    interval: float | None = None,
) -> None:
    """Keep the snapshot warm while at least one stream is connected.

    The fallback path. When a server carries a coordinator, `serve` runs that
    instead and this is never reached; it stays for a server assembled without
    one, which is what `--no-events` and a good many test doubles are.

    With no client this loop does nothing at all: no collection, no store
    access. An idle daemon costs what it costs today, which is nothing, and a
    timer that collected regardless would be exactly the regression this phase
    exists to avoid.

    A collection failure is swallowed and retried on the next tick. The
    per-harness failure boundary already reports the cause, and a producer that
    died on one bad read would leave every connected dashboard frozen with no
    indication why.
    """
    application = getattr(server, "application", None)
    if application is None:
        # A server double without an application: nothing to collect for, and a
        # thread that raised here would surface as an unhandled exception from a
        # daemon thread, which is noise rather than a signal.
        return
    period = application.config.stream_producer_interval_sec if interval is None else interval
    while not stop.wait(period):
        if application.state.streams.count == 0:
            continue
        try:
            application.collect_json(show_all=False)
        except Exception as exc:  # noqa: BLE001 (a bad read must not stop the loop)
            runtime_io.diag(
                f"Cargento: producer collection failed: {exc}",
                application.diagnostic_sink,
            )


def serve(
    config: RuntimeConfig,
    server: http_api.CargentoHTTPServer,
    port: int,
    *,
    started: float,
    announce_fd: int | None = None,
    diagnostic_sink: Callable[[str], None] = print,
) -> None:
    """Announce, record, serve, and clean up after only this instance.

    127.0.0.1, not localhost: on some systems "localhost" resolves to ::1
    first, and this listener is IPv4-only, so the literal address is the one
    that always connects.
    """
    runtime_io.diag(f"Cargento: http://127.0.0.1:{port}/", diagnostic_sink)
    observation = getattr(server, "observation", None)
    write_state(
        config,
        port,
        started=started,
        # Published here rather than at assembly because the tokens name a
        # *serving* process. A run that never binds writes no state file, so it
        # publishes no capability either.
        capabilities=observation.capabilities() if observation is not None else None,
        diagnostic_sink=diagnostic_sink,
    )
    if announce_fd is not None:
        # After write_state, so --status works the instant the parent returns.
        daemon_announce(announce_fd)
    # Started here rather than at assembly: on the daemon path serve() runs
    # after the fork, so no thread is ever created in a process about to be
    # replaced. The coordinator subsumes the producer's periodic tick, so exactly
    # one of the two runs and they can never both collect.
    producer_stop = threading.Event()
    producer: threading.Thread | None = None
    if observation is not None:
        observation.start()
    else:
        producer = threading.Thread(
            target=run_producer, args=(server,), kwargs={"stop": producer_stop}, daemon=True
        )
        producer.start()
    try:
        server.serve_forever()
    finally:
        producer_stop.set()
        if producer is not None:
            producer.join(timeout=2)
        if observation is not None:
            # Before the streams close: a coordinator mid-collection would
            # otherwise publish into a registry being torn down.
            with contextlib.suppress(Exception):
                observation.stop(timeout=config.stop_release_timeout_sec)
        # Converge every exit path on the same cleanup: --stop, a signal, and an
        # exception all have to release the streams, not just the endpoint.
        # getattr rather than a bare attribute: a test double may stand in for
        # the server without carrying an application, and cleanup must not be
        # the thing that raises on the way out.
        application = getattr(server, "application", None)
        if application is not None:
            with contextlib.suppress(Exception):
                application.state.streams.close_all()
            # And every parked ask poll. `POST /api/shutdown` declines them
            # too, but it is only one way out: a signal, an exception and a
            # `--stop` from another process all leave through here, and a poll
            # nobody declined holds silently until the process exits under it.
            with contextlib.suppress(Exception):
                application.state.asks.decline_all()
        remove_state(config, port)
        with contextlib.suppress(OSError):
            server.server_close()
