"""Shared test runtime.

The seam the suite patches: one shared ``RuntimeState``, and one mutable
store-override mapping that ``runtime()`` folds into a freshly built config.
Redirecting a store is ``mock.patch.dict(STORE_OVERRIDES, {...})``.
"""

from __future__ import annotations

import atexit
import contextlib
import dataclasses
import importlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from typing import Any
from unittest import mock

from cargento_runtime import aggregate, cli, diagnostics, http_api, notifications
from cargento_runtime.collectors import claude as claude_collector
from cargento_runtime.config import CARGENTO_HOME_ENV, RuntimeConfig, build_runtime_config
from cargento_runtime.state import RuntimeState, build_runtime_state

from .fixtures import STORE_CONSTANTS

SERVER_PATH = Path(__file__).resolve().parents[1] / "server.py"
sys.path.insert(0, str(SERVER_PATH.parent))
frontend_page = importlib.import_module("cargento_runtime.web.page")
PAGE_BYTES = frontend_page.load_page()
NEXT_PAGE_BYTES = frontend_page.load_next_page()

HOOK_PATH = SERVER_PATH.parent / "notify_hook.py"
HOOK_SPEC = importlib.util.spec_from_file_location("cargento_notify_hook", HOOK_PATH)
assert HOOK_SPEC is not None
assert HOOK_SPEC.loader is not None
dashboard_hook = importlib.util.module_from_spec(HOOK_SPEC)
sys.modules[HOOK_SPEC.name] = dashboard_hook
HOOK_SPEC.loader.exec_module(dashboard_hook)

# The state home every test gets unless it patches CARGENTO_HOME for itself.
# Unset, config.py falls back to the developer's real ~/.cargento, and since
# DRC-4039 that means every collection reads their real dismissal store — the
# suite's verdict then depends on what they happen to have dismissed. Seeded into
# the process environment rather than injected inside runtime() so config.py
# still sees the honest variable in both directions: an explicit patch overwrites
# it, and an environ built with the key removed still has it removed, which is
# how the unset-fallback case stays testable. Assigned rather than defaulted: an
# exported CARGENTO_HOME is the same leak as no CARGENTO_HOME, and letting one
# through would make the suite's result depend on the developer's shell.
#
# One directory per process, not per test: runtime() is also called from classes
# with no shared setUp of their own, so a per-test directory could not reach them
# all. Nothing the suite writes here is read back by a later test — every test
# that exercises the dismissal store points state_home at its own directory.
_STATE_HOME = tempfile.TemporaryDirectory(prefix="cargento-test-home-")
STATE_HOME = _STATE_HOME.name
atexit.register(_STATE_HOME.cleanup)
os.environ[CARGENTO_HOME_ENV] = STATE_HOME

# Store key -> path. Patch with mock.patch.dict; runtime() folds it into config.
STORE_OVERRIDES: dict[str, Any] = {}  # str, or a tuple/list of candidates
# RuntimeConfig field -> value, applied by runtime() after the build: how a test
# lowers a threshold or a cap.
CONFIG_OVERRIDES: dict[str, Any] = {}

# Constant name as the harness-contract fixtures spell it -> store key.
STORE_KEYS: dict[str, str] = {
    "PROJECTS_DIR": "claude.projects",
    "TASKS_DIR": "claude.tasks",
    "TEAMS_DIR": "claude.teams",
    "CODEX_SESSIONS_DIR": "codex.sessions",
    "PI_SESSIONS_DIR": "pi.sessions",
    "GEMINI_TMP": "gemini.tmp",
    "ANTIGRAVITY_CLI_DIR": "antigravity.root",
    "COPILOT_DIR": "copilot.root",
    "OPENCODE_DATA": "opencode.data",
    "CURSOR_CHATS": "cursor.chats",
    "GOOSE_DB": "goose.db",
    "FACTORY_PROJECTS": "droid.projects",
}
assert set(STORE_KEYS) == set(STORE_CONSTANTS), "store name map drifted from the fixtures"

SERVER_STARTED = 1_700_000_000.0
_STATE: RuntimeState | None = None


def store_patch(**by_constant: str) -> Any:
    """Redirect stores by their fixture constant name, as a context manager.

    ``store_patch(PROJECTS_DIR=path)`` drops into existing ``with`` tuples.
    """
    return mock.patch.dict(
        STORE_OVERRIDES, {STORE_KEYS[name]: value for name, value in by_constant.items()}
    )


def config_patch(**fields: Any) -> Any:
    """Override RuntimeConfig fields for the shared runtime, as a context manager."""
    return mock.patch.dict(CONFIG_OVERRIDES, fields)


def state_of() -> RuntimeState:
    """The shared runtime's state."""
    return runtime()[1]


def runtime() -> tuple[RuntimeConfig, RuntimeState]:
    """The shared test runtime: a fresh config, and the one state per test.

    The config is rebuilt on every call so a store override or a CARGENTO_HOME
    patch applied after setUp is still seen. The state is not, because tests seed
    hook and cache entries and then expect a collection to observe them.
    """
    global _STATE  # noqa: PLW0603 — one shared state per test process
    single = {k: v for k, v in STORE_OVERRIDES.items() if isinstance(v, str)}
    multi = {k: tuple(v) for k, v in STORE_OVERRIDES.items() if not isinstance(v, str)}
    config = build_runtime_config(
        environ=os.environ,
        platform_name=sys.platform,
        os_name=os_name(),
        launcher_path=SERVER_PATH,
        store_root_overrides=single,
    )
    if multi:
        # build_runtime_config takes one root per key; a test pinning several
        # candidates replaces the resolved tuple outright.
        roots = dict(config.store_roots)
        roots.update(multi)
        config = dataclasses.replace(config, store_roots=MappingProxyType(roots))
    if CONFIG_OVERRIDES:
        config = dataclasses.replace(config, **CONFIG_OVERRIDES)
    if _STATE is None:
        _STATE = build_runtime_state(config, started=SERVER_STARTED)
    _STATE.config = config
    return config, _STATE


def os_name() -> str:
    """``os.name``, read through a function so a test can patch the module."""
    return os.name


def reset_runtime() -> RuntimeState:
    """Drop the shared state so the next runtime() call builds a clean one."""
    global _STATE  # noqa: PLW0603 — one shared state per test process
    _STATE = None
    return runtime()[1]


def cfg() -> RuntimeConfig:
    """The shared runtime's config.

    Lifecycle helpers read the state home, timeouts and os_name off a config
    instead of the ambient environment, so a test that patches CARGENTO_HOME has
    to call this INSIDE the patch to get a config that sees it.
    """
    return runtime()[0]


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


def build_app(window_hours: float = 24) -> aggregate.Application:
    """An application over the shared runtime, built the way the CLI builds one."""
    config, state = runtime()
    if window_hours != config.window_hours:
        config = dataclasses.replace(config, window_hours=window_hours)
    return cli.build_application(config, state, clock=time.time)


def collect(window_hours: float = 24, show_all: bool = False) -> dict[str, Any]:
    """One full collection over the shared runtime."""
    return build_app(window_hours).collect(show_all=show_all)


def collect_json(window_hours: float = 24, show_all: bool = False) -> bytes:
    """The published JSON body for one collection over the shared runtime."""
    _revision, body = build_app(window_hours).collect_json(show_all=show_all)
    return body


def diagnose(window_hours: float = 24) -> dict[str, Any]:
    """The diagnostics report for the shared runtime."""
    return diagnostics.diagnose(build_app(window_hours))


def collect_claude(
    now: float,
    window_hours: float,
    show_all: bool,
) -> list[dict[str, Any]]:
    """Run the Claude collector over the shared runtime.

    It raises no popup: since DRC-4192 the popup decision belongs to
    `Application`, which is the only layer that sees a row's final state. Tests
    about popups build an application (see `ApplicationPopupTest`).
    """
    config, state = runtime()
    return claude_collector.collect(config, state, now, window_hours, show_all)


def make_server(
    *,
    port: int = 0,
    host: str = "127.0.0.1",
    application: Any = None,
    page_bytes: bytes | None = None,
    next_page_bytes: bytes | None = NEXT_PAGE_BYTES,
    window_hours: float = 24,
    observation: Any = None,
) -> Any:
    """A CargentoHTTPServer over the shared runtime, with CLI-equivalent defaults.

    ``observation`` defaults to None, which is what `--no-events` produces and
    what every test that only needs a page and an application wants.
    """
    return http_api.CargentoHTTPServer(
        (host, port),
        application if application is not None else build_app(window_hours),
        PAGE_BYTES if page_bytes is None else page_bytes,
        observation,
        next_page_bytes=next_page_bytes,
    )


def notify_handler(payload: dict[str, Any], *, application: Any = None) -> Any:
    """A bare request handler wired to an application, for POST-ordering tests.

    Those tests drive ``do_POST`` directly rather than over a socket, because
    they need to suspend it mid-flight and land a second request inside the
    window. The handler reads its application off the server instance, so it gets
    a stand-in carrying exactly that and nothing else.
    """
    handler: Any = http_api._RequestHandler.__new__(http_api._RequestHandler)
    body = json.dumps(payload).encode()
    handler.headers = {"Content-Length": str(len(body))}
    handler.path = "/api/notify"
    handler.rfile = io.BytesIO(body)
    handler.server = SimpleNamespace(
        application=application if application is not None else build_app()
    )
    handler._local_ok = lambda **_kw: True
    handler._send = lambda *_a, **_k: None
    return handler


def serve_until_closed(httpd: Any) -> threading.Thread:
    """Serve on a thread that closes the listening socket when the loop exits.

    Mirrors what the serve path does in its ``try/finally``. Serving without the
    close leaves the port bound after the accept loop has gone — a state the CLI
    never produces, and one that makes anything waiting for the port to come free
    (``--stop``, and therefore any restart) wait for nothing.
    """

    def serve() -> None:
        try:
            httpd.serve_forever()
        finally:
            httpd.server_close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    return thread


def clear_state(state: RuntimeState) -> None:
    """Empty every cache, hook and memo on one state."""
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
        state.snapshot.clear()
    with state.usage_fetch_lock:
        state.usage_fetch_cache.clear()
        state.usage_fetch_inflight.clear()


class RuntimeTestCase(unittest.TestCase):
    """A clean shared runtime, and no test may fire a real popup."""

    def setUp(self) -> None:
        STORE_OVERRIDES.clear()
        CONFIG_OVERRIDES.clear()
        clear_state(reset_runtime())
        # No test may fire a real macOS popup ("[sample] permission" spam
        # during dev runs). Tests asserting popups use their own nested patch.
        notify_patcher = mock.patch.object(notifications, "notify_mac")
        notify_patcher.start()
        self.addCleanup(notify_patcher.stop)
        self.addCleanup(STORE_OVERRIDES.clear)
        self.addCleanup(CONFIG_OVERRIDES.clear)


class PiScanTestCase(unittest.TestCase):
    def setUp(self) -> None:
        _, state = runtime()
        with state.scanner_lock:
            state.pi_scan.clear()


class HarnessContractTestCase(unittest.TestCase):
    NOW = 1_700_000_000.0
    SID = "abcdef12-3456-7890-abcd-ef1234567890"
    TITLE = "Investigate the failing build"

    def setUp(self) -> None:
        # collect() updates transition/cooldown state. Without clearing it here,
        # a shuffled run can inherit a prior test's last_session_state and
        # suppress or invent the transition this contract is meant to observe.
        STORE_OVERRIDES.clear()
        CONFIG_OVERRIDES.clear()
        clear_state(reset_runtime())
        self.addCleanup(STORE_OVERRIDES.clear)
        self.addCleanup(CONFIG_OVERRIDES.clear)

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
                stack.enter_context(store_patch(**patches))
                stack.enter_context(mock.patch.object(notifications, "notify_mac"))
                stack.enter_context(mock.patch.object(time, "time", lambda: self.NOW))
                collected: dict[str, Any] = collect(24, show_all=True)
                return collected

    def sessions_for(self, data: dict[str, Any], key: str) -> list[dict[str, Any]]:
        return [session for session in data["sessions"] if session["harness"] == key]


# The registry as the runtime declares it, for tests that only read keys/labels.
# Named distinctly from fixtures.HARNESSES, which is (key, builder) pairs.
REGISTRY = aggregate.default_harnesses()
