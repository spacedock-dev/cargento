"""Argument parsing, runtime assembly, and the three serve branches."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from cargento_runtime import aggregate, diagnostics, http_api, lifecycle, notifications
from cargento_runtime import config as runtime_config
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


def runtime_environ(home: str | None = None) -> dict[str, str]:
    """Capture ambient process inputs at the executable boundary.

    The one place the environment is read. Everything downstream takes the
    result as an argument, which is what lets the whole runtime be exercised
    for another platform on any runner (design decision D-4).
    """
    environ = dict(os.environ)
    resolved_home = os.path.expanduser("~") if home is None else home
    environ["HOME"] = resolved_home
    if sys.platform == "win32":
        environ["USERPROFILE"] = resolved_home
    return environ


def build_parser() -> argparse.ArgumentParser:
    """The CLI surface. argparse owns --help and its own usage errors."""
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument("--port", type=lifecycle.tcp_port, default=4553)
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="report where each harness's data is searched for, and exit",
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
        port=args.port,
        window_hours=args.window_hours,
        spacedock_enabled=not args.no_spacedock,
        usage_fetch_enabled=not args.no_usage,
    )
    return config, runtime_state.build_runtime_state(config, started=started)


def bound_popup_notifier(
    config: RuntimeConfig,
    diagnostic_sink: Callable[[str], None],
) -> Callable[[str, str], None]:
    """The application's popup notifier: config and sink bound, two arguments left."""

    def notify(title: str, message: str) -> None:
        notifications.notify_mac(config, title, message, diagnostic_sink=diagnostic_sink)

    return notify


def build_application(
    config: RuntimeConfig,
    state: RuntimeState,
    *,
    diagnostic_sink: Callable[[str], None] = print,
    clock: Callable[[], float] = time.time,
) -> aggregate.Application:
    """One application over one config and state, with every service injected."""
    popup_notifier = bound_popup_notifier(config, diagnostic_sink)
    return aggregate.Application(
        config,
        state,
        # The same callable the Claude collector notifies through, so the
        # transcript path and the hook path cannot diverge.
        aggregate.default_harnesses(popup_notifier, usage_fetch_enabled=config.usage_fetch_enabled),
        native_notifier=notifications.native_notifier,
        popup_notifier=popup_notifier,
        diagnostic_sink=diagnostic_sink,
        clock=clock,
    )


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
    if args.daemon and (args.diagnose or args.stop or args.status):
        # Each of those three exits without serving, so --daemon cannot apply.
        # Accepting it silently would teach that it had been honored.
        parser.error("--daemon cannot be combined with --diagnose, --stop or --status")
    config, state = build_runtime(args, started=started)

    if args.diagnose:
        report = diagnostics.diagnose(build_application(config, state))
        runtime_io.diag(
            json.dumps(report, indent=2) if args.json else diagnostics.render_diagnosis(report),
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
    try:
        page_bytes = frontend_page.load_page()
    except (OSError, UnicodeError, RuntimeError) as exc:
        print(
            f"Cargento: cannot load frontend assets ({type(exc).__name__}: {exc}).",
            file=sys.stderr,
        )
        return 1
    log_file = lifecycle.log_path(config, args.port)
    if args.daemon and not lifecycle.prepare_daemon_home(config, log_file):
        # Reported already; the message has to reach the terminal that asked,
        # which is why this is checked before anything detaches.
        return 1

    if args.daemon and config.os_name == "nt":
        # No fork on Windows: re-spawn, then wait to be sure (D-2). This branch
        # returns before any bind, so the parent never holds the port it handed
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

    # Bind to loopback only — this exposes local session data.
    #
    # Bind before detaching. bind_error_message() exists so a busy port gets an
    # explanation rather than a traceback, and SKILL.md tells the agent to look
    # for an already-running dashboard when it sees one. Forking first would
    # send that message to a log file nobody has been told about yet, and
    # report success.
    try:
        server = http_api.CargentoHTTPServer(
            ("127.0.0.1", args.port),
            build_application(config, state),
            page_bytes,
        )
    except OSError as exc:
        runtime_io.diag(http_api.bind_error_message(exc, args.port), print)
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
