from __future__ import annotations

import contextlib
import dataclasses
import importlib
import importlib.util
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest import mock

from cargento_runtime import notifications
from cargento_runtime.collectors import claude as claude_collector
from cargento_runtime.config import RuntimeConfig, build_runtime_config
from cargento_runtime.state import RuntimeState, build_runtime_state

from .fixtures import STORE_CONSTANTS

if TYPE_CHECKING:
    from collections.abc import Callable

SERVER_PATH = Path(__file__).resolve().parents[1] / "server.py"
sys.path.insert(0, str(SERVER_PATH.parent))
frontend_page = importlib.import_module("cargento_runtime.web.page")
PAGE_BYTES = frontend_page.load_page()

SPEC = importlib.util.spec_from_file_location("cargento_server", SERVER_PATH)
assert SPEC is not None
assert SPEC.loader is not None
dashboard = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = dashboard
SPEC.loader.exec_module(dashboard)

HOOK_PATH = SERVER_PATH.parent / "notify_hook.py"
HOOK_SPEC = importlib.util.spec_from_file_location("cargento_notify_hook", HOOK_PATH)
assert HOOK_SPEC is not None
assert HOOK_SPEC.loader is not None
dashboard_hook = importlib.util.module_from_spec(HOOK_SPEC)
sys.modules[HOOK_SPEC.name] = dashboard_hook
HOOK_SPEC.loader.exec_module(dashboard_hook)


def make_config(**changes: Any) -> RuntimeConfig:
    config = build_runtime_config(
        environ={"HOME": "/home/cargento-test"},
        platform_name="linux",
        os_name="posix",
        launcher_path=SERVER_PATH,
    )
    return dataclasses.replace(config, **changes)


def make_runtime(
    *,
    started: float = 1_700_000_000.0,
    **changes: Any,
) -> tuple[RuntimeConfig, RuntimeState]:
    config = make_config(**changes)
    return config, build_runtime_state(config, started=started)


def collect_claude(
    now: float,
    window_hours: float,
    show_all: bool,
    *,
    popup_notifier: Callable[[str, str], None] | None = None,
) -> list[dict[str, Any]]:
    """Run the Claude collector over the legacy runtime this suite resets.

    The collector takes its popup notifier as an argument rather than reaching
    for a module global, so the default here is the same binding the launcher
    hands the application. Tests that assert on popups keep patching
    ``notifications.notify_mac`` underneath it.
    """
    config, state = dashboard._legacy_runtime()
    return claude_collector.collect(
        config,
        state,
        now,
        window_hours,
        show_all,
        popup_notifier=popup_notifier or dashboard._bound_popup_notifier(config),
    )


def serve_until_closed(httpd: Any) -> threading.Thread:
    """Serve on a thread that closes the listening socket when the loop exits.

    Mirrors what ``main()`` does in its ``try/finally``. Serving without the
    close leaves the port bound after the accept loop has gone — a state
    ``main()`` never produces, and one that makes anything waiting for the port
    to come free (``--stop``, and therefore any restart) wait for nothing.
    """

    def serve() -> None:
        try:
            httpd.serve_forever()
        finally:
            httpd.server_close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    return thread


class LegacyDashboardTestCase(unittest.TestCase):
    def setUp(self) -> None:
        with dashboard._lock:
            dashboard._hook_notifs.clear()
            dashboard._last_popup.clear()
            dashboard._last_popup_message.clear()
            dashboard._last_state.clear()
            dashboard._hook_generation.clear()
        with dashboard._cache_lock:
            dashboard._meta_cache.clear()
            dashboard._cwd_cache.clear()
            dashboard._cursor_meta_cache.clear()
            dashboard._agent_class_cache.clear()
            dashboard._claude_title_cache.clear()
            dashboard._claude_user_event_cache.clear()
        with dashboard._scan_lock:
            dashboard._turn_scan.clear()
        with dashboard._collect_memo_lock:
            dashboard._collect_memo.clear()
        _, state = dashboard._legacy_runtime()
        with state.hook_lock:
            state.hook_notifications.clear()
            state.last_popup.clear()
            state.last_popup_message.clear()
            state.last_session_state.clear()
            state.hook_generation.clear()
        with state.cache_lock:
            state.store_errors.clear()
            state.metadata_cache.clear()
            state.claude_title_cache.clear()
            state.claude_user_event_cache.clear()
            state.cwd_cache.clear()
            state.agent_class_cache.clear()
            state.spacedock_role_cache.clear()
            state.spacedock_boot_cache.clear()
            state.spacedock_workflow_cache.clear()
            state.spacedock_entity_cache.clear()
            state.cursor_metadata_cache.clear()
        with state.scanner_lock:
            state.pi_scan.clear()
            state.turn_scan.clear()
        with state.collect_memo_lock:
            state.collect_memo.clear()
        # No test may fire a real macOS popup ("[sample] permission" spam
        # during dev runs). Tests asserting popups use their own nested patch.
        notify_patcher = mock.patch.object(notifications, "notify_mac")
        notify_patcher.start()
        self.addCleanup(notify_patcher.stop)


class PiScanTestCase(unittest.TestCase):
    def setUp(self) -> None:
        with dashboard._scan_lock:
            dashboard._pi_scan.clear()


class HarnessContractTestCase(unittest.TestCase):
    NOW = 1_700_000_000.0
    SID = "abcdef12-3456-7890-abcd-ef1234567890"
    TITLE = "Investigate the failing build"

    def setUp(self) -> None:
        # collect() updates transition/cooldown state. Without clearing it here,
        # a shuffled run can inherit a prior test's _last_state and suppress or
        # invent the transition this contract is meant to observe.
        with dashboard._lock:
            dashboard._hook_notifs.clear()
            dashboard._last_popup.clear()
            dashboard._last_popup_message.clear()
            dashboard._last_state.clear()
            dashboard._hook_generation.clear()

    def collect(self, build: Any, *, when: float, subdir: str = "store") -> dict[str, Any]:
        """Build one harness's store in isolation and run a full collection."""
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty"
            empty.mkdir()
            # Point every store at an empty directory first, so a harness
            # installed on the developer's machine cannot leak into the result.
            patches: dict[str, str] = {name: str(empty / name) for name in STORE_CONSTANTS}
            patches.update(build(Path(tmp) / subdir, when, self.SID, self.TITLE))
            with contextlib.ExitStack() as stack:
                for name, value in patches.items():
                    stack.enter_context(mock.patch.object(dashboard, name, value))
                stack.enter_context(mock.patch.object(notifications, "notify_mac"))
                stack.enter_context(mock.patch.object(dashboard.time, "time", lambda: self.NOW))
                collected: dict[str, Any] = dashboard.collect(24, show_all=True)
                return collected

    def sessions_for(self, data: dict[str, Any], key: str) -> list[dict[str, Any]]:
        return [session for session in data["sessions"] if session["harness"] == key]
