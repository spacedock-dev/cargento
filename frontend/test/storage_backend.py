# ruff: noqa: INP001 -- standalone contributor executable, never an installed package
"""Synthetic legacy-page server for the storage conformance run; stdin EOF owns its lifetime.

Serves the repository's legacy page from the supplied plugin root with two synthetic
sessions and every model, usage, notification and focus path disabled. Nothing here reads a
harness store, starts a terminal, or calls a provider.
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

PROJECT = "storage-conformance"
SESSIONS = (("claude", "claude-sid:one"), ("codex", "codex-sid-two"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin-root", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    if args.port != 0 and not 4581 <= args.port <= 4599:
        parser.error("owned conformance port must be 0 or 4581..4599")
    return args


def main() -> int:
    args = parse_args()
    skill = args.plugin_root.resolve() / "skills/cargento"
    sys.path.insert(0, str(skill))
    modules = {
        name: importlib.import_module(f"cargento_runtime.{name}")
        for name in ("config", "cli", "state", "aggregate", "http_api", "sessions", "web.page")
    }
    for module in modules.values():
        if not Path(str(module.__file__)).resolve().is_relative_to(skill):
            raise RuntimeError("conformance runtime escaped the supplied plugin root")
    page = modules["web.page"].load_frontend_page("legacy")
    with tempfile.TemporaryDirectory(prefix="cargento-storage-conformance-") as temporary:
        scratch = Path(temporary)
        (scratch / "no-executables").mkdir()
        os.environ.clear()
        os.environ.update(
            HOME=str(scratch),
            USERPROFILE=str(scratch),
            CARGENTO_HOME=str(scratch / "state"),
            PATH=str(scratch / "no-executables"),
        )
        config = modules["config"].build_runtime_config(
            environ=dict(os.environ),
            platform_name=sys.platform,
            os_name=os.name,
            launcher_path=skill / "server.py",
            port=args.port,
            frontend="legacy",
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

        def collect(harness: str, sid: str) -> list[dict[str, Any]]:
            row = modules["sessions"].base_session(harness, sid, PROJECT)
            row.update(active=True, state="idle", last_activity=time.time())
            return [row]

        harnesses = tuple(
            modules["aggregate"].HarnessSpec(
                name, name.title(), lambda *_: True, lambda *_, h=name, s=sid: collect(h, s)
            )
            for name, sid in SESSIONS
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
        server = modules["http_api"].CargentoHTTPServer(
            ("127.0.0.1", args.port), application, modules["cli"].inject_focus_capability(page, "")
        )
        thread = threading.Thread(
            target=lambda: server.serve_forever(poll_interval=0.05), daemon=True
        )
        thread.start()
        try:
            print(
                json.dumps(
                    {
                        "ready": True,
                        "port": server.server_port,
                        "project": PROJECT,
                        "sessions": [{"harness": h, "sid": s} for h, s in SESSIONS],
                        "runtime": str(Path(str(modules["config"].__file__)).resolve()),
                    }
                ),
                flush=True,
            )
            sys.stdin.readline()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
