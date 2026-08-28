from __future__ import annotations

import atexit
import contextlib
import json
import shutil
import subprocess
import threading
from pathlib import Path
from typing import IO, Any

from cargento_runtime.web import page as frontend_page

from .support import RuntimeTestCase

WEB_DIR = frontend_page.WEB_DIR
APP_JS = frontend_page.load_script()
STYLES = (WEB_DIR / "styles.css").read_text(encoding="utf-8")
PAGE_TEXT = (
    (WEB_DIR / "index.html")
    .read_text(encoding="utf-8")
    .replace("{{CARGENTO_STYLES}}", STYLES)
    .replace("{{CARGENTO_APP}}", APP_JS)
)


WORKER_PATH = Path(__file__).resolve().parent / "page_worker.js"


class PageJsWorker:
    """One node process, reused by every page-JS check in the run.

    Spawning node per check cost 40ms of each check's 44ms on macOS, across 425
    checks. The worker keeps the isolation (a fresh `vm` context per check) and
    drops the spawn. See `page_worker.js` for the framing and the reasoning.
    """

    # Checks to run before starting a fresh process. Every check compiles the
    # 260KB page script into its own context, and V8 reclaims those lazily:
    # measured, the worker sat at 430MB after the suite's 425 checks and kept
    # climbing to 592MB when the same checks were run three times over. Nothing
    # is leaking that a restart cannot clear, and a restart costs one 40ms spawn,
    # so the process is replaced periodically rather than left to grow with
    # however many page tests the suite comes to hold.
    CHECK_BUDGET = 150

    def __init__(self) -> None:
        self._checks = 0
        self._noise: list[bytes] = []
        self._spawn()
        atexit.register(self.close)

    def _spawn(self) -> None:
        self._proc = subprocess.Popen(
            [shutil.which("node") or "node", str(WORKER_PATH)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        # Drained on a thread rather than read on demand. The worker answers on
        # stdout and reports check failures in that reply, so stderr only ever
        # carries node's own noise — but an undrained pipe fills at 64KB and
        # blocks the worker mid-write, which would hang the run rather than fail
        # it. Kept so a worker that dies has something to say.
        #
        # Handed the pipe rather than reading `self._proc`, which a restart
        # rebinds: a thread that followed the attribute would end up reading the
        # replacement's stderr alongside its own drain.
        self._drain = threading.Thread(
            target=self._collect_stderr, args=(self._proc.stderr,), daemon=True
        )
        self._drain.start()

    def _collect_stderr(self, pipe: IO[bytes] | None) -> None:
        if pipe is None:  # pragma: no cover — stderr is always a pipe here
            return
        for line in pipe:
            self._noise.append(line)

    def run(self, source: str) -> tuple[bool, str, str]:
        """Run one check. Returns (ok, stdout, error text)."""
        if self._checks >= self.CHECK_BUDGET:
            self.close()
            self._spawn()
            self._checks = 0
        self._checks += 1
        assert self._proc.stdin is not None
        assert self._proc.stdout is not None
        # Explicit UTF-8 both ways: the page carries glyphs outside Latin-1, and
        # on Windows the default is the locale codec (cp1252), which raises
        # instead of running the check. node speaks UTF-8.
        body = source.encode("utf-8")
        try:
            self._proc.stdin.write(f"{len(body)}\n".encode("ascii") + body)
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:  # pragma: no cover — worker died
            raise AssertionError(f"page-JS worker died: {self._stderr()}") from exc
        header = self._proc.stdout.readline()
        if not header:  # pragma: no cover — worker died mid-check
            raise AssertionError(f"page-JS worker died: {self._stderr()}")
        reply = json.loads(self._read_exactly(int(header)).decode("utf-8"))
        return bool(reply["ok"]), reply.get("out", ""), reply.get("err", "")

    def _read_exactly(self, length: int) -> bytes:
        assert self._proc.stdout is not None
        chunks: list[bytes] = []
        remaining = length
        while remaining:
            chunk = self._proc.stdout.read(remaining)
            if not chunk:  # pragma: no cover — worker died mid-reply
                raise AssertionError(f"page-JS worker died: {self._stderr()}")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _stderr(self) -> str:  # pragma: no cover — only reached on a dead worker
        self._drain.join(timeout=2)
        return b"".join(self._noise).decode("utf-8", "replace")

    def close(self) -> None:
        proc = self._proc
        if proc.poll() is None:
            # Closing stdin is the shutdown signal: the worker finishes what it
            # is running, then exits on end-of-stream.
            with contextlib.suppress(OSError):
                if proc.stdin is not None:
                    proc.stdin.close()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:  # pragma: no cover — stdin ignored
                proc.kill()
                proc.wait(timeout=5)
        # Explicitly, not at collection: a recycled worker's pipes would
        # otherwise be closed by the finalizer, which reports them as an
        # unclosed-file ResourceWarning in the middle of an unrelated test.
        self._drain.join(timeout=5)
        for pipe in (proc.stdout, proc.stderr):
            if pipe is not None:
                with contextlib.suppress(OSError):
                    pipe.close()


_WORKER: PageJsWorker | None = None


def page_js_worker() -> PageJsWorker:
    """The run's worker, started on the first check that needs it."""
    global _WORKER  # noqa: PLW0603 — one worker process per test process
    if _WORKER is None:
        _WORKER = PageJsWorker()
    return _WORKER


class PageJsHarness(RuntimeTestCase):
    """Runs the dashboard page's real JS under node against a stub DOM.

    Shared by every test that asserts on page *behaviour* rather than on the
    text of the page: string assertions rot silently, executed ones do not.
    """

    APP_JS = APP_JS

    # Functional DOM/window stubs for executing the page script under node:
    # listeners are captured so tests can fire synthetic events, and
    # getElementById serves whatever elements a test registers in __els.
    PAGE_JS_STUBS = """
const __listeners = {};
const __els = {};
const __fire = (type, ev) => (__listeners[type] || []).forEach(f => f(ev));
// Deterministic viewer clock: sparkline points are stamped with Date.now()
// at receipt, so tests pin it and advance it explicitly via __setNow.
let __nowSec = 1000;
const __setNow = s => { __nowSec = s; };
Date.now = () => __nowSec * 1000;
let __assignedLocations = [];
const location = {
  search: "",
  hash: "",
  assign(value){ __assignedLocations.push(String(value)); }
};
const document = {
  addEventListener(type, fn){ (__listeners[type] = __listeners[type] || []).push(fn); },
  getElementById(id){ return __els[id] || null; },
  createElement(){ return {textContent: "", style: {}, appendChild(){}}; },
  createTextNode(){ return {textContent: ""}; },
  activeElement: null,
  hidden: false,
  title: ""
};
const window = {addEventListener(type, fn){
  (__listeners["window:" + type] = __listeners["window:" + type] || []).push(fn); }};
// Records what the page requested and lets a test choose the reply. The old
// never-settling stub is the default, so existing tests behave identically.
let __fetchCalls = [];
let __fetchImpl = () => new Promise(() => {});
const fetch = (...args) => { __fetchCalls.push(args); return __fetchImpl(...args); };
let __clearedIntervals = [];
// Intervals are recorded rather than run, so a test drives the page's clock
// itself. __runInterval fires every timer registered at one period, which is
// how the live tests exercise the election tick and the fallback poll without
// waiting real seconds.
let __intervals = [];
const clearInterval = id => { __clearedIntervals.push(id); };
const setInterval = (fn, ms) => { __intervals.push({fn, ms}); return __intervals.length; };
const __runInterval = ms => __intervals.filter(i => i.ms === ms).forEach(i => i.fn());
const __intervalPeriods = () => __intervals.map(i => i.ms);
// Notification stub: records what the page would have raised, with a
// permission value tests can set. Defined here so every page test runs with a
// browser-notification-capable environment, as a real browser would.
let __notifications = [];
let __notifyPermission = "default";
function Notification(title, opts){ __notifications.push(Object.assign({title}, opts)); }
Object.defineProperty(Notification, "permission", {get: () => __notifyPermission});
// Settles on a later microtask, as the real API does: a synchronous stub let
// code that re-renders immediately (before permission resolves) pass.
Notification.requestPermission = cb => Promise.resolve().then(() => {
  __notifyPermission = "granted";
  if(cb) cb("granted");
  return "granted";
});
const __settle = () => new Promise(r => setImmediate(r));
"""

    def _run_page_js(self, checks: str, prelude: str = "") -> Any:
        """`prelude` runs before the page script, for globals the page reads at
        load time (localStorage) or feature-detects (navigator.clipboard)."""
        # Checks run inside an async IIFE so they can await the async stubs
        # (permission settles on a microtask, as in a browser). The promise is
        # parked on `globalThis` because the worker awaits it to know the check
        # is done — under the old process-per-check design that signal was node
        # exiting when its event loop drained.
        source = (
            self.PAGE_JS_STUBS
            + prelude
            + self.APP_JS
            + "\n;globalThis.__cargentoDone = (async () => {\n"
            + checks
            + "\n})();\n"
        )
        ok, out, err = page_js_worker().run(source)
        self.assertTrue(ok, err)
        return json.loads(out.strip().splitlines()[-1])
