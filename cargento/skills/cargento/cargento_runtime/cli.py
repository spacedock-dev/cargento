"""Argument parsing, runtime assembly, and the three serve branches."""

from __future__ import annotations

import argparse
import contextlib
import ipaddress
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from cargento_runtime import (
    aggregate,
    diagnostics,
    history,
    http_api,
    lifecycle,
    notifications,
    observation,
)
from cargento_runtime import config as runtime_config
from cargento_runtime import interaction_prototype as runtime_interaction
from cargento_runtime import io as runtime_io
from cargento_runtime import state as runtime_state
from cargento_runtime.web import page as frontend_page

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from cargento_runtime.config import RuntimeConfig
    from cargento_runtime.state import RuntimeState

DESCRIPTION = """Cargento: live coding-agent session activity across harnesses.

Stdlib-only local server. Supported harnesses (each shown only if its local
data is discovered): Claude Code, Codex, Pi, Gemini CLI (retired, legacy
stores only), Antigravity CLI, GitHub Copilot CLI, OpenCode, Cursor CLI,
Goose, Factory Droid. Serves a summary UI at http://127.0.0.1:<port>/ and
JSON at /api/data.
"""

LAUNCHER_PATH = Path(__file__).resolve().parents[1] / "server.py"


def collected_session_ids(application: aggregate.Application) -> frozenset[str]:
    """Freeze collected identities before registration can cause effects."""
    _revision, body = application.collect_json(show_all=True)
    try:
        payload = json.loads(body)
    except (ValueError, json.JSONDecodeError):
        return frozenset()
    rows = payload.get("sessions") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return frozenset()
    return frozenset(
        f"{row['harness']}:{row['sid']}"
        for row in rows
        if isinstance(row, dict)
        and isinstance(row.get("harness"), str)
        and isinstance(row.get("sid"), str)
    )


def build_server(
    address: tuple[str, int],
    application: aggregate.Application,
    page_bytes: bytes,
    coordinator: observation.Observation | None,
    *,
    interaction_session: str | None,
    interaction_registration_file: Path | None,
) -> http_api.CargentoHTTPServer:
    """Attach the opt-in collected-session origin without changing normal serving."""
    prototype = None
    if interaction_session is not None:
        known_sessions = collected_session_ids(application)
        prototype = runtime_interaction.InteractionPrototype(
            collected_session_id=interaction_session,
            session_exists=known_sessions.__contains__,
            registration_file=interaction_registration_file,
        )
    return http_api.CargentoHTTPServer(
        address,
        application,
        page_bytes,
        coordinator,
        interaction_prototype=prototype,
    )


def runtime_environ(home: str | None = None) -> dict[str, str]:
    """Capture ambient process inputs at the executable boundary.

    The one place the environment is read. Everything downstream takes the
    result as an argument, which is what lets the whole runtime be exercised
    for another platform on any runner (design decision
    [D-4](docs/design-cross-platform.md#d-4)).
    """
    environ = dict(os.environ)
    resolved_home = os.path.expanduser("~") if home is None else home
    environ["HOME"] = resolved_home
    if sys.platform == "win32":
        environ["USERPROFILE"] = resolved_home
    return environ


# The two binds the rest of the runtime works against. Not a taste for round
# numbers: everything that talks *to* the server talks to loopback, and loopback
# is an interface of both of these and of nothing else. `--status` and `--stop`
# probe `127.0.0.1:<port>`; the four hook forwarders and the MCP server refuse a
# non-loopback destination by design (SECURITY.md's first invariant); the
# announced URL is loopback. A single-interface bind like `--host 10.0.0.2`
# leaves all of them talking to a closed port, and the worst of them is not the
# dead hook — `--stop` reads "not running", exits 0, and deletes the live
# instance's state file, event-ingress capability tokens and all, while the
# server keeps serving. Binding one interface is a reasonable thing to want; it
# needs the bind address threaded through the state file and every client, and
# refusing it is the honest answer until that exists.
BIND_HOSTS = ("127.0.0.1", "0.0.0.0")  # noqa: S104 — the documented wildcard opt-in


def bind_host(value: str) -> str:
    """An argparse type for the dashboard's bind address.

    Two accepted values, and IPv6 is not among them: the server is IPv4-only, so
    ``::`` or ``::1`` is out of scope and rejected at parse time rather than
    becoming a confusing bind failure. See ``BIND_HOSTS`` for why a single
    non-loopback interface is refused rather than allowed and left broken.

    ``ipaddress`` rather than a hand-rolled dotted-quad split, which is where
    this started: ``int()`` accepts a sign, surrounding whitespace and
    non-ASCII digits, so ``"+1.2.3.4"`` and ``"1.2.3.4\n"`` parsed and then
    reached ``socket.bind`` — the confusing bind failure the check exists to
    turn into a usage error.
    """
    try:
        ipaddress.IPv4Address(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"must be an IPv4 address, one of {' or '.join(BIND_HOSTS)}"
        ) from exc
    if value not in BIND_HOSTS:
        raise argparse.ArgumentTypeError(
            f"must be {' or '.join(BIND_HOSTS)}. A single-interface bind is refused rather "
            "than half-supported: --status, --stop, the hook forwarders and the MCP server all "
            "reach the dashboard over loopback, which such a bind does not answer"
        )
    return value


def positive_float(value: str) -> float:
    """A float above zero, or an argparse error naming what was wrong.

    Zero or negative is refused rather than clamped: a retention window of zero
    days is a store that evicts everything it records, which reads as the store
    being broken rather than as the operator having turned it off — and there is
    already a switch that turns it off. Rejected at parse time, so a daemon
    cannot be respawned with a bound the parent would not have accepted.
    """
    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a number") from None
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError(f"must be greater than zero, not {value!r}")
    return number


def positive_int(value: str) -> int:
    """An int above zero, or an argparse error naming what was wrong."""
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a whole number") from None
    if number <= 0:
        raise argparse.ArgumentTypeError(f"must be greater than zero, not {value!r}")
    return number


def build_parser() -> argparse.ArgumentParser:
    """The CLI surface. argparse owns --help and its own usage errors."""
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument("--port", type=lifecycle.tcp_port, default=4553)
    parser.add_argument(
        "--host",
        type=bind_host,
        default="127.0.0.1",
        help="bind address: 127.0.0.1 (default) or 0.0.0.0 for remote access",
    )
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="report where each harness's data is searched for, and exit",
    )
    parser.add_argument(
        "--observer-model",
        action="store_true",
        help="offer model goal summaries; requires disclosure consent on refresh",
    )
    parser.add_argument(
        "--no-observer-model",
        "--no-harness-usage",
        action="store_true",
        help="refuse observer model calls for this run, overriding --observer-model",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable --diagnose output")
    parser.add_argument(
        "--no-spacedock",
        action="store_true",
        help="do not read Spacedock workflow definitions (drops the stage strips)",
    )
    parser.add_argument(
        "--no-usage",
        action="store_true",
        help=(
            "for this run, do not fetch vendor quota over the network and do "
            "not publish quota a harness pushed in, regardless of the "
            "dashboard's stored setting. Quota a harness writes into its own "
            "store (Codex, Copilot) still shows"
        ),
    )
    parser.add_argument(
        "--no-git",
        action="store_true",
        help=(
            "do not run the end-of-session git probe in any session's working "
            "repository (the dirty and changed fields then stay empty)"
        ),
    )
    parser.add_argument(
        "--no-focus",
        action="store_true",
        help=(
            "do not raise a session's terminal for this run: no focus command "
            "runs, no terminal identity is recorded, and the page is handed no "
            "capability to ask with. --no-events turns it off as well"
        ),
    )
    parser.add_argument(
        "--no-history",
        action="store_true",
        help=(
            "do not keep a local history of what this server observed for this "
            "run: nothing is written and an existing store is not read back, so "
            "the board opens with no memory of earlier sessions."
        ),
    )
    parser.add_argument(
        "--no-dismiss",
        action="store_true",
        help=(
            "do not read or write the dismissal store for this run: sessions "
            "marked handled come back onto the board and the page offers no "
            "control to clear them. The rollback switch for the dismissal store "
            "Cargento writes on your behalf"
        ),
    )
    parser.add_argument(
        "--no-annotations",
        action="store_true",
        help=(
            "do not read or write the annotation store for this run: the goal "
            "and expected output you typed against a session are neither shown "
            "nor saved, and the page offers no field to type them in. The "
            "rollback switch for the one store holding prose you composed "
            "rather than anything a harness published"
        ),
    )
    parser.add_argument(
        "--no-ask",
        action="store_true",
        help=(
            "do not let a session ask the reader a question for this run: the "
            "register, poll and answer routes refuse and the page offers no "
            "control. The rollback switch for the one feature that answers a "
            "waiting agent"
        ),
    )
    parser.add_argument(
        "--no-events",
        action="store_true",
        help=(
            "do not run the event coordinator for this run: no event overlays, "
            "no coarse store probe, and the older fixed-interval producer keeps "
            "the snapshot warm instead. The independent rollback switch if event "
            "acquisition misbehaves"
        ),
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="report whether a Cargento is running on --port, and exit",
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        help="stop the Cargento running on --port, and exit",
    )
    parser.add_argument(
        "--forget",
        action="store_true",
        help=(
            "delete the local history store, and exit. Refused while a "
            "dashboard is running on --port, which would write it back"
        ),
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="detach and keep running after the session that started it exits",
    )
    parser.add_argument(
        "--window-hours",
        type=float,
        default=24,
        help="sessions with no activity in this window are hidden (default 24)",
    )
    parser.add_argument(
        "--interaction-origin-session",
        help="bind one explicitly registered collected harness:sid to read-only output",
    )
    parser.add_argument(
        "--interaction-origin-registration-file",
        type=Path,
        help="write the one-use session-side tmux registration capability here",
    )
    parser.add_argument(
        "--history-days",
        type=positive_float,
        default=runtime_config.HISTORY_RETENTION_DEFAULT_DAYS,
        help=(
            "how long the local history keeps an observation, in days "
            f"(default {runtime_config.HISTORY_RETENTION_DEFAULT_DAYS:g}). Eviction is by "
            "age first, so narrowing this drops what falls outside it and "
            "widening it again brings nothing back"
        ),
    )
    parser.add_argument(
        "--history-max-bytes",
        type=positive_int,
        default=runtime_config.HISTORY_MAX_BYTES_DEFAULT,
        help=(
            "the size cap on the local history store, in bytes (default "
            f"{runtime_config.HISTORY_MAX_BYTES_DEFAULT}). It is the read cap too: a "
            "file larger than it is discarded unread rather than parsed"
        ),
    )
    return parser


def build_runtime(
    args: argparse.Namespace,
    *,
    started: float,
    launcher_path: Path = LAUNCHER_PATH,
) -> tuple[RuntimeConfig, RuntimeState]:
    """Freeze configuration and create state, with no operational side effects.

    Nothing here touches a store, a socket, or a log. That is what makes
    --diagnose, --status and --stop usable on a machine where serving would
    fail.
    """
    config = runtime_config.build_runtime_config(
        environ=runtime_environ(),
        platform_name=sys.platform,
        os_name=os.name,
        launcher_path=launcher_path,
        host=args.host,
        port=args.port,
        window_hours=args.window_hours,
        spacedock_enabled=not args.no_spacedock,
        usage_fetch_enabled=not args.no_usage,
        observer_model_enabled=args.observer_model and not args.no_observer_model,
        git_probe_enabled=not args.no_git,
        focus_enabled=not args.no_focus,
        dismissals_enabled=not args.no_dismiss,
        annotations_enabled=not args.no_annotations,
        ask_enabled=not args.no_ask,
        history_enabled=not args.no_history,
        history_retention_sec=args.history_days * runtime_config.SECONDS_PER_DAY,
        history_max_bytes=args.history_max_bytes,
    )
    return config, runtime_state.build_runtime_state(config, started=started)


def bound_popup_notifier(
    config: RuntimeConfig,
    diagnostic_sink: Callable[[str], None],
) -> Callable[[str, str], str | None]:
    """The application's popup notifier: config and sink bound, two arguments left.

    Returns the outcome rather than `None`, so the caller that spends the
    cooldown can record what became of the raise it spent it on.
    """

    def notify(title: str, message: str) -> str:
        return notifications.notify_mac(config, title, message, diagnostic_sink=diagnostic_sink)

    return notify


def build_application(
    config: RuntimeConfig,
    state: RuntimeState,
    *,
    diagnostic_sink: Callable[[str], None] = print,
    clock: Callable[[], float] = time.time,
    record_history: bool = True,
) -> aggregate.Application:
    """One application over one config and state, with every service injected.

    `record_history` is the one service a caller has to think about, and only
    one caller says no to it: `--diagnose` reports what the stores hold and must
    not write while doing it. Attached unconditionally, one `--diagnose` into a
    clean `CARGENTO_HOME` created a 26,086-byte store of 189 records spanning
    13.41 days — 176 of them outside `window_hours` and unreachable from a
    serving collection — and `--forget && --diagnose` put back the file the
    delete had just removed.
    """
    popup_notifier = bound_popup_notifier(config, diagnostic_sink)
    application = aggregate.Application(
        config,
        state,
        aggregate.default_harnesses(usage_fetch_enabled=config.usage_fetch_enabled),
        native_notifier=notifications.native_notifier,
        popup_notifier=popup_notifier,
        diagnostic_sink=diagnostic_sink,
        clock=clock,
    )
    if record_history:
        # Attached here rather than reached through the overlay source, which is
        # None forever under --no-events: the store's only off switch is
        # --no-history, so the lane must not hang off an unrelated flag.
        application.history_lane = history.Lane(config, diagnostic_sink=diagnostic_sink)
    return application


def load_frontend_page() -> bytes | None:
    """Assemble the required dashboard page."""
    try:
        return frontend_page.load_page()
    except (OSError, UnicodeError, RuntimeError) as exc:
        print(
            f"Cargento: cannot load frontend assets ({type(exc).__name__}: {exc}).",
            file=sys.stderr,
        )
        return None


def validate_interaction_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Reject a partial collected-session registration boundary."""
    if bool(args.interaction_origin_session) != bool(args.interaction_origin_registration_file):
        parser.error(
            "--interaction-origin-session and --interaction-origin-registration-file "
            "must be used together"
        )


FOCUS_META_NAME = "cargento-focus"
# The focus consumer key is hex, so nothing legitimate is turned away and nothing
# that could close the attribute or open a tag gets in. Checked rather than
# escaped: an escape would make an unexpected token renderable, and a token this
# server did not mint is a bug rather than a value to accommodate.
_FOCUS_TOKEN_CHARS = frozenset("0123456789abcdefABCDEF")


def inject_focus_capability(page: bytes, token: str) -> bytes:
    """Put this run's focus capability into the served document.

    Injected here rather than baked into an asset, and the seam matters: the
    frontend's assembled bytes are pinned by digest in two test files, so a token
    inside `cargento_runtime/web/` would make them non-deterministic. This runs
    between `load_frontend_page()` and the server construction, which leaves
    `frontend_page.load_page()` byte-identical and both pins untouched.

    Returns the page unchanged when there is nothing safe to inject, because a
    page with no control is the documented off state rather than an error.
    """
    if not token or not set(token) <= _FOCUS_TOKEN_CHARS:
        return page
    marker = b"</head>"
    index = page.find(marker)
    if index < 0:
        return page
    meta = f'<meta name="{FOCUS_META_NAME}" content="{token}">'.encode()
    return page[:index] + meta + page[index:]


def run_one_shot(
    args: argparse.Namespace,
    config: RuntimeConfig,
    state: RuntimeState,
) -> int | None:
    """The commands that report and exit, or None when this run is to serve.

    Gathered out of `main` rather than left as four consecutive branches there,
    because `main` sits on ruff's branch cap and `--forget` was the flag that
    put it over. They are one family: each answers a question or performs one
    irreversible act, none of them binds a socket, and `--daemon` is refused
    with all four.
    """
    if args.diagnose:
        # No recording lane: diagnostics read the stores and report, and
        # `SKILL.md` sends the reader here first whenever a harness is missing.
        report = diagnostics.diagnose(build_application(config, state, record_history=False))
        runtime_io.diag(
            json.dumps(report, indent=2) if args.json else diagnostics.render_diagnosis(report),
            print,
        )
        return 0
    if args.forget:
        # In the family of --stop and --status rather than the family of per-run
        # switches, because what it does is not reversible by running the next
        # command without it. It deletes the file whether or not the store is
        # enabled, and it adds no route: nothing over the loopback port can
        # delete history.
        path = history.store_path(config)
        # Refused while an instance is up, because a running dashboard holds its
        # own baseline in memory and republishes it on the next transition: the
        # delete reported success and every record came back. The probe is the
        # one `--status` and `--stop` already use, so it needs neither the home
        # the dashboard was started with nor a state file. It covers the port
        # this invocation names and cannot see an instance on another one, which
        # is why the lane also drops a baseline whose file has gone.
        if lifecycle.instance_status(config, args.port)["state"] == "running":
            runtime_io.diag(
                f"Cargento: a dashboard is running on port {args.port} and would "
                f"write {path} back from memory; stop it with --stop first, then --forget",
                print,
            )
            return 1
        runtime_io.diag(
            f"Cargento: deleted {path}"
            if history.forget(config)
            else f"Cargento: no history store at {path}",
            print,
        )
        return 0
    if args.stop:
        message, code = lifecycle.stop_instance(config, args.port)
        runtime_io.diag(message, print)
        return code
    if args.status:
        status = lifecycle.instance_status(config, args.port)
        runtime_io.diag(lifecycle.render_status(status), print)
        return 0 if status["state"] == "running" else 1
    return None


def main(argv: Sequence[str] | None = None) -> int:
    """Parse, assemble, and run. Returns an exit code.

    argparse keeps its own SystemExit for --help and usage errors; every other
    exit is a returned code, so the CLI is callable from a test without
    catching SystemExit.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    # Sampled before the combination check: the start stamp names this process,
    # and must not shift depending on which validation ran first.
    started = time.time()
    if args.daemon and (args.diagnose or args.stop or args.status or args.forget):
        # Each of those four exits without serving, so --daemon cannot apply.
        # Accepting it silently would teach that it had been honored.
        parser.error("--daemon cannot be combined with --diagnose, --stop, --status or --forget")
    validate_interaction_args(parser, args)
    config, state = build_runtime(args, started=started)

    one_shot = run_one_shot(args, config, state)
    if one_shot is not None:
        return one_shot

    if not runtime_io.sqlite_available():
        runtime_io.diag(
            f"Cargento: sqlite3 unavailable ({runtime_io.SQLITE_IMPORT_ERROR}) — OpenCode, "
            "Cursor and Goose sessions cannot be read; Antigravity still appears "
            "but without its token rate or turn ETA. Install the sqlite3 "
            "extension for this interpreter to enable them.",
            print,
        )
    # After the recovery commands above, so --status and --stop still work on an
    # installation whose assets are missing, and while stderr is still attached.
    page_bytes = load_frontend_page()
    if page_bytes is None:
        return 1
    log_file = lifecycle.log_path(config, args.port)
    if args.daemon and not lifecycle.prepare_daemon_home(config, log_file):
        # Reported already; the message has to reach the terminal that asked,
        # which is why this is checked before anything detaches.
        return 1

    if args.daemon and config.os_name == "nt":
        # No fork on Windows: re-spawn, then wait to be sure
        # ([D-2](docs/design-daemon.md#d-2)).
        # This branch returns before any bind, so the parent never holds the port it handed
        # over, and never constructs a server at all — the spawned foreground
        # child owns the bind and therefore owns reporting a bind failure.
        message, code = lifecycle.await_spawned(
            config,
            lifecycle.spawn_detached(config, args, log_file),
            args.port,
            log_file,
        )
        runtime_io.diag(message, print)
        return code

    # Bind before detaching. bind_error_message() exists so a busy port gets an
    # explanation rather than a traceback, and SKILL.md tells the agent to look
    # for an already-running dashboard when it sees one. Forking first would
    # send that message to a log file nobody has been told about yet, and
    # report success.
    try:
        application = build_application(config, state)
        # Constructed inert and attached both ways: the coordinator reads the
        # application to collect, and the application reads the coordinator for
        # overlays. Nothing has started a thread yet, which is what lets the
        # daemon fork below happen safely.
        coordinator = None
        if not args.no_events:
            coordinator = observation.Observation(application)
            application.overlays = coordinator
        if coordinator is not None and config.focus_enabled:
            # The page is served as fixed bytes with no per-run secret in it, so
            # the capability has to be put there. `--no-events` leaves no
            # coordinator to mint one, which is the second off switch the focus
            # contract names.
            page_bytes = inject_focus_capability(page_bytes, coordinator.focus_capability())
        server = build_server(
            (args.host, args.port),
            application,
            page_bytes,
            coordinator,
            interaction_session=args.interaction_origin_session,
            interaction_registration_file=args.interaction_origin_registration_file,
        )
    except OSError as exc:
        runtime_io.diag(http_api.bind_error_message(exc, args.port, args.host), print)
        return 1

    announce_fd: int | None = None
    if args.daemon:
        role, fd = lifecycle.fork_daemon()
        if role == "parent":
            # The daemon holds its own dup of the listening socket; closing
            # this one keeps a dead daemon from leaving the port looking bound.
            with contextlib.suppress(OSError):
                server.server_close()
            message, code = lifecycle.await_daemon(config, fd, args.port, log_file)
            runtime_io.diag(message, print)
            return code
        announce_fd = fd
        lifecycle.daemon_redirect_stdio(log_file)

    lifecycle.serve(config, server, args.port, started=started, announce_fd=announce_fd)
    return 0
