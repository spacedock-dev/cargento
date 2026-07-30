from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .support import LegacyDashboardTestCase, dashboard


class PageJsHarness(LegacyDashboardTestCase):
    """Runs the dashboard page's real JS under node against a stub DOM.

    Shared by every test that asserts on page *behaviour* rather than on the
    text of ``PAGE``: string assertions rot silently, executed ones do not.
    """

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
const location = {search: ""};
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
const clearInterval = id => { __clearedIntervals.push(id); };
const setInterval = () => 73;
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
        match = re.search(r"<script>\n(.*?)</script>", dashboard.PAGE, re.DOTALL)
        assert match is not None
        script = match.group(1)
        with tempfile.TemporaryDirectory() as tmp:
            js = Path(tmp) / "page_test.js"
            # Checks run inside an async IIFE so they can await the async
            # stubs (permission settles on a microtask, as in a browser).
            # Explicit UTF-8 both ways: the page carries glyphs outside Latin-1,
            # and on Windows the default is the locale codec (cp1252), which
            # raises instead of running the check. node speaks UTF-8.
            js.write_text(
                self.PAGE_JS_STUBS
                + prelude
                + script
                + "\n;(async () => {\n"
                + checks
                + "\n})();\n",
                encoding="utf-8",
            )
            proc = subprocess.run(
                [shutil.which("node") or "node", str(js)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
                check=False,
            )
        self.assertEqual(0, proc.returncode, proc.stderr)
        return json.loads(proc.stdout.strip().splitlines()[-1])
