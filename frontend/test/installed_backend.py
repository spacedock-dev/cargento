# ruff: noqa: INP001 -- standalone contributor executable, never an installed package
"""Controlled installed-copy smoke server; stdin EOF owns its lifetime.

All runtime imports come from the explicitly supplied plugin copy. The optional
legacy terminal fixture uses synthetic HTTP registration and stream output; it
starts no terminal, tmux, notification, provider, or child process.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote


class SyntheticTerminal:
    def __init__(self, api: Any) -> None:
        self.api = api
        self.origin: Any = None
        self.output: Any = None
        self.disconnected: Any = None
        self.stop_event = threading.Event()
        self.renewal: threading.Thread | None = None

    def prepare(self) -> Any:
        self.origin = self.api.TmuxOrigin(
            server_socket="/synthetic/installed-smoke.sock",
            server_pid="1001",
            session_id="$1",
            session_name="installed-smoke",
            window_id="@1",
            window_index="0",
            window_name="synthetic-stream",
            pane_id="%1",
            pane_index="0",
            pane_tty="/synthetic/tty",
            pane_cols="80",
            pane_rows="24",
        )
        return self.origin

    def start_client(self, port: int, token: str, session: str, lease: float, origin: Any) -> None:
        def renew() -> None:
            status, registered = self.api.request(
                port,
                "POST",
                "/api/interaction/register",
                {
                    "registration_token": token,
                    "cargento_session_id": session,
                    "origin": origin.as_dict(),
                },
            )
            if status != 200 or registered.get("state") != "registered":
                return
            while not self.stop_event.wait(lease / 3):
                try:
                    _, result = self.api.request(
                        port,
                        "POST",
                        "/api/interaction/renew",
                        {
                            "origin_id": registered["origin_id"],
                            "lease_token": registered["lease_token"],
                        },
                    )
                except OSError:
                    return
                if result.get("state") != "renewed":
                    return

        self.renewal = threading.Thread(target=renew, daemon=True)
        self.renewal.start()

    def start_read_only_stream(self, origin: Any, output: Any, disconnected: Any) -> None:
        self.output, self.disconnected = output, disconnected
        output(origin.pane_id, "Installed synthetic read-only terminal\r\n")

    def bind_origin(self, origin: Any) -> None:
        if self.origin is not None and origin != self.origin:
            raise self.api.OriginUnavailableError("synthetic registered origin changed")
        self.origin = origin

    def stop_read_only_stream(self) -> None:
        callback, self.disconnected = self.disconnected, None
        if callback is not None:
            callback()

    def inspect(self, origin: Any) -> Any:
        if self.stop_event.is_set():
            raise self.api.OriginUnavailableError("synthetic terminal stopped")
        return origin

    def capture(self, origin: Any) -> str:
        self.inspect(origin)
        return "Installed synthetic read-only terminal\r\n"

    def connected(self, _origin: Any) -> bool:
        return not self.stop_event.is_set()

    def stop(self) -> None:
        self.stop_event.set()
        self.stop_read_only_stream()
        if self.renewal is not None:
            self.renewal.join(2)


def isolated_environment(scratch: Path, environ: dict[str, str], *, os_name: str) -> dict[str, str]:
    """Keep only Windows loader inputs and this smoke's owned locations."""
    result = {
        "HOME": str(scratch),
        "USERPROFILE": str(scratch),
        "CARGENTO_HOME": str(scratch / "state"),
        "PATH": str(scratch / "no-executables"),
    }
    if os_name == "nt":
        # Winsock/side-by-side loading needs the actual OS directory. This is
        # not a harness root or executable search path; do not guess C:\\Windows.
        for name, value in environ.items():
            if name.upper() in {"SYSTEMROOT", "WINDIR"}:
                result[name.upper()] = value
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin-root", type=Path, required=True)
    parser.add_argument("--frontend", choices=("legacy", "react"), required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--terminal-fixture", action="store_true")
    parser.add_argument(
        "--focus-token",
        default="",
        help="synthetic hex token for parser smoke only; native focus stays disabled",
    )
    args = parser.parse_args()
    if args.port != 0 and not 4581 <= args.port <= 4599:
        parser.error("owned smoke port must be 0 or 4581..4599")
    if args.terminal_fixture and args.frontend != "legacy":
        parser.error("the existing Console smoke belongs to legacy, not the React scaffold")
    if args.focus_token and (
        len(args.focus_token) > 128 or not set(args.focus_token) <= set("0123456789abcdefABCDEF")
    ):
        parser.error("synthetic focus token must be at most 128 hex characters")
    return args


def main() -> int:
    args = parse_args()
    skill = args.plugin_root.resolve() / "skills/cargento"
    sys.path.insert(0, str(skill))
    modules = {
        name: importlib.import_module(f"cargento_runtime.{name}")
        for name in (
            "config",
            "cli",
            "state",
            "aggregate",
            "http_api",
            "sessions",
            "interaction_prototype",
            "web.page",
        )
    }
    for module in modules.values():
        if not Path(module.__file__).resolve().is_relative_to(skill):
            raise RuntimeError("smoke runtime escaped the installed copy")
    page = modules["web.page"].load_frontend_page(args.frontend)
    with tempfile.TemporaryDirectory(prefix="cargento-installed-backend-") as temporary:
        scratch = Path(temporary)
        # The child environment and explicit runtime config independently refuse
        # host stores. No Node executable is visible to runtime subprocesses.
        isolated = isolated_environment(scratch, dict(os.environ), os_name=os.name)
        os.environ.clear()
        os.environ.update(isolated)
        config = modules["config"].build_runtime_config(
            environ=dict(os.environ),
            platform_name=sys.platform,
            os_name=os.name,
            launcher_path=skill / "server.py",
            port=args.port,
            frontend=args.frontend,
            spacedock_enabled=False,
            tripwires_enabled=False,
            usage_fetch_enabled=False,
            model_calls_disabled=True,
            git_probe_enabled=False,
            focus_enabled=False,
            irreversible_enabled=False,
            dismissals_enabled=False,
            annotations_enabled=False,
            ask_enabled=False,
            reach_enabled=False,
            quiet_hours_enabled=False,
            history_enabled=False,
        )
        state = modules["state"].build_runtime_state(config, started=time.time())
        project = "installed-smoke-project"
        sid = "disposable-tmux-origin:1"
        row = modules["sessions"].base_session("codex", sid, project)
        row.update(active=True, state="idle", last_activity=time.time())
        harnesses = (
            (
                modules["aggregate"].HarnessSpec(
                    "codex", "Codex", lambda *_: True, lambda *_: [dict(row)]
                ),
            )
            if args.terminal_fixture
            else ()
        )
        application = modules["aggregate"].Application(
            config,
            state,
            harnesses,
            native_notifier=lambda _: "disabled",
            popup_notifier=lambda *_: None,
            diagnostic_sink=lambda message: print(message, file=sys.stderr),
            frontend_page_bytes=page,
        )
        api = modules["interaction_prototype"]
        prototype = (
            api.InteractionPrototype(SyntheticTerminal(api), lease_sec=3)
            if args.terminal_fixture
            else None
        )
        server = modules["http_api"].CargentoHTTPServer(
            ("127.0.0.1", args.port),
            application,
            modules["cli"].inject_focus_capability(page, args.focus_token),
            interaction_prototype=prototype,
        )
        thread = threading.Thread(
            target=lambda: server.serve_forever(poll_interval=0.05), daemon=True
        )
        thread.start()
        try:
            ready = {
                "ready": True,
                "port": server.server_port,
                "frontend": args.frontend,
                "runtime": str(Path(modules["config"].__file__).resolve()),
            }
            if prototype is not None:
                deadline = time.monotonic() + 10
                while (
                    prototype.resolve_session(server.server_port, f"codex:{sid}").get("state")
                    != "registered"
                ):
                    if time.monotonic() >= deadline:
                        raise RuntimeError("synthetic terminal registration did not complete")
                    time.sleep(0.02)
                ready["terminal_fragment"] = (
                    f"#n=project:{quote(project, safe='')}:{quote('codex:' + sid, safe='')}:console"
                )
                ready["terminal_fixture"] = (
                    "synthetic HTTP registration and read-only stream; no native terminal"
                )
            print(json.dumps(ready), flush=True)
            # EOF or one line requests shutdown; no unowned signal/process kill.
            sys.stdin.readline()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
