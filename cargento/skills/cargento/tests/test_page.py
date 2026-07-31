from __future__ import annotations

import hashlib
import http.client
import http.server
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest import mock

from cargento_runtime import cli, diagnostics, http_api, lifecycle
from cargento_runtime import io as runtime_io

from .page_harness import APP_JS, PAGE_TEXT, PageJsHarness
from .support import (
    frontend_page,
    make_server,
    serve_until_closed,
    state_of,
)

SKILL_DIR = Path(__file__).resolve().parents[1]

if TYPE_CHECKING:
    import email.message


class FrontendAssetContractTest(unittest.TestCase):
    """The shipped frontend asset boundary and assembled page contract."""

    def test_runtime_package_has_one_canonical_top_level_identity(self) -> None:
        self.assertNotIn("cargento.skills.cargento.cargento_runtime", sys.modules)
        assert frontend_page.__file__ is not None
        self.assertTrue(Path(frontend_page.__file__).resolve().is_relative_to(SKILL_DIR))

    def test_package_initializers_stay_empty(self) -> None:
        self.assertEqual(b"", (SKILL_DIR / "cargento_runtime" / "__init__.py").read_bytes())
        self.assertEqual(b"", (SKILL_DIR / "cargento_runtime" / "web" / "__init__.py").read_bytes())

    def test_assets_stay_inside_the_installed_skill(self) -> None:
        for name in ("index.html", "styles.css", "app.js"):
            with self.subTest(asset=name):
                self.assertTrue(frontend_page.asset_path(name).resolve().is_relative_to(SKILL_DIR))

    def test_load_page_preserves_all_three_byte_oracles(self) -> None:
        assembled = frontend_page.load_page()
        styles = frontend_page.asset_path("styles.css").read_bytes()
        script = frontend_page.asset_path("app.js").read_bytes()
        self.assertEqual(104_781, len(assembled))
        self.assertEqual(
            "36df2da2598ae85fc0aa03ed0f965cf4d0265abba81048e283642f1a48b5f60b",
            hashlib.sha256(assembled).hexdigest(),
        )
        self.assertEqual(32_644, len(styles))
        self.assertEqual(
            "492b2f422fc6fbdb93f888e87c84463e445f2d9dee2c81959f377ba070c6b999",
            hashlib.sha256(styles).hexdigest(),
        )
        self.assertEqual(71_841, len(script))
        self.assertEqual(
            "13995ebe16b929e19abb632151ebb5bbe198026bfefbb1b45b1604272612f5f1",
            hashlib.sha256(script).hexdigest(),
        )

    def test_load_page_names_a_missing_asset(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(frontend_page, "WEB_DIR", Path(tmp)),
            self.assertRaisesRegex(FileNotFoundError, "index.html"),
        ):
            frontend_page.load_page()

    def test_load_page_rejects_invalid_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            web = Path(tmp)
            (web / "index.html").write_text("{{CARGENTO_STYLES}}{{CARGENTO_APP}}", encoding="utf-8")
            (web / "styles.css").write_text("", encoding="utf-8")
            (web / "app.js").write_bytes(b"\xff")
            with (
                mock.patch.object(frontend_page, "WEB_DIR", web),
                self.assertRaises(UnicodeDecodeError),
            ):
                frontend_page.load_page()

    def test_load_page_rejects_each_malformed_template_slot(self) -> None:
        cases = (
            ("{{CARGENTO_APP}}", "index.html must contain one CARGENTO_STYLES slot"),
            ("{{CARGENTO_STYLES}}", "index.html must contain one CARGENTO_APP slot"),
            (
                "{{CARGENTO_STYLES}}{{CARGENTO_STYLES}}{{CARGENTO_APP}}",
                "index.html must contain one CARGENTO_STYLES slot",
            ),
        )
        for template, message in cases:
            with self.subTest(template=template), tempfile.TemporaryDirectory() as tmp:
                web = Path(tmp)
                (web / "index.html").write_text(template, encoding="utf-8")
                (web / "styles.css").write_text("css", encoding="utf-8")
                (web / "app.js").write_text("js", encoding="utf-8")
                with (
                    mock.patch.object(frontend_page, "WEB_DIR", web),
                    self.assertRaisesRegex(RuntimeError, f"^{re.escape(message)}$"),
                ):
                    frontend_page.load_page()

    def test_early_cli_paths_do_not_read_missing_assets(self) -> None:
        cases = (
            ("help", ["--help"], 0, "usage:"),
            ("diagnose", ["--diagnose", "--json"], 0, '"harnesses"'),
            ("status", ["--port", "1", "--status"], 1, "not running"),
            ("stop", ["--port", "1", "--stop"], 0, "nothing running"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            skill = Path(tmp) / "skill"
            shutil.copytree(SKILL_DIR, skill)
            for name in ("index.html", "styles.css", "app.js"):
                (skill / "cargento_runtime" / "web" / name).unlink()
            env = dict(os.environ)
            env.pop("PYTHONPATH", None)
            env["PYTHONNOUSERSITE"] = "1"
            for label, args, expected_code, expected_text in cases:
                with self.subTest(path=label):
                    proc = subprocess.run(
                        [sys.executable, str(skill / "server.py"), *args],
                        cwd=tmp,
                        env=env,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        timeout=30,
                        check=False,
                    )
                    self.assertEqual(expected_code, proc.returncode, proc.stderr)
                    self.assertIn(expected_text, proc.stdout + proc.stderr)
                    self.assertNotIn("cannot load frontend assets", proc.stderr)

    def test_early_cli_paths_never_call_the_canonical_page_loader(self) -> None:
        cases = (
            ("help", ["--help"], 0),
            ("diagnose", ["--diagnose", "--json"], None),
            ("status", ["--status"], 0),
            ("stop", ["--stop"], 0),
        )
        for label, args, expected_exit in cases:
            with self.subTest(path=label):
                calls: list[str] = []

                def record_load(
                    observed: list[str] = calls,
                    path: str = label,
                ) -> bytes:
                    observed.append(path)
                    return b"must not be read"

                with (
                    mock.patch.object(frontend_page, "load_page", side_effect=record_load),
                    mock.patch.object(sys, "argv", ["server.py", *args]),
                    mock.patch.object(diagnostics, "diagnose", return_value={}),
                    mock.patch.object(diagnostics, "render_diagnosis", return_value=""),
                    mock.patch.object(
                        lifecycle, "instance_status", return_value={"state": "running"}
                    ),
                    mock.patch.object(lifecycle, "render_status", return_value="running"),
                    mock.patch.object(lifecycle, "stop_instance", return_value=("stopped", 0)),
                    mock.patch.object(runtime_io, "diag"),
                    mock.patch.object(sys, "stdout", io.StringIO()),
                ):
                    if label == "help":
                        # argparse prints usage and exits itself.
                        with self.assertRaises(SystemExit) as caught:
                            cli.main()
                        self.assertEqual(expected_exit, caught.exception.code)
                    else:
                        code = cli.main()
                        if expected_exit is not None:
                            self.assertEqual(expected_exit, code)
                self.assertEqual([], calls, f"{label} read frontend assets")

    def test_serving_uses_the_canonical_loader_before_binding(self) -> None:
        with (
            mock.patch.object(
                frontend_page,
                "load_page",
                side_effect=RuntimeError("review loader probe"),
            ),
            mock.patch.object(
                http_api,
                "CargentoHTTPServer",
                side_effect=AssertionError("bound before canonical loader"),
            ),
            mock.patch.object(sys, "argv", ["server.py"]),
            mock.patch.object(sys, "stderr", io.StringIO()) as stderr,
        ):
            try:
                cli.main()
            except SystemExit as exc:
                self.assertEqual(1, exc.code)
            except AssertionError as exc:
                self.fail(str(exc))
        self.assertEqual(
            "Cargento: cannot load frontend assets (RuntimeError: review loader probe).\n",
            stderr.getvalue(),
        )

    def test_serving_reports_asset_failure_before_log_creation_or_bind(self) -> None:
        unreadable_error = "PermissionError" if os.name == "nt" else "IsADirectoryError"
        cases = (
            ("missing", "FileNotFoundError", "index.html"),
            ("unreadable", unreadable_error, "index.html"),
            ("invalid UTF-8", "UnicodeDecodeError", "invalid start byte"),
            (
                "malformed template",
                "RuntimeError",
                "index.html must contain one CARGENTO_STYLES slot",
            ),
        )
        for mutation, error_type, detail in cases:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                skill = root / "skill"
                shutil.copytree(SKILL_DIR, skill)
                web = skill / "cargento_runtime" / "web"
                if mutation == "missing":
                    (web / "index.html").unlink()
                elif mutation == "unreadable":
                    (web / "index.html").unlink()
                    (web / "index.html").mkdir()
                elif mutation == "invalid UTF-8":
                    (web / "app.js").write_bytes(b"\xff")
                else:
                    (web / "index.html").write_text("no slots", encoding="utf-8")
                state = root / "state"
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                    listener.bind(("127.0.0.1", 0))
                    listener.listen()
                    port = listener.getsockname()[1]
                    env = dict(os.environ)
                    env.pop("PYTHONPATH", None)
                    env["PYTHONNOUSERSITE"] = "1"
                    env["CARGENTO_HOME"] = str(state)
                    proc = subprocess.run(
                        [
                            sys.executable,
                            str(skill / "server.py"),
                            "--daemon",
                            "--port",
                            str(port),
                        ],
                        cwd=root,
                        env=env,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        timeout=30,
                        check=False,
                    )
                self.assertEqual(1, proc.returncode)
                self.assertTrue(
                    proc.stderr.startswith(
                        f"Cargento: cannot load frontend assets ({error_type}: "
                    ),
                    proc.stderr,
                )
                self.assertIn(detail, proc.stderr)
                self.assertTrue(proc.stderr.endswith(").\n"), proc.stderr)
                self.assertFalse(state.exists())


class InstalledContractCharacterizationTest(unittest.TestCase):
    """The installed executable contract that extraction must preserve."""

    def setUp(self) -> None:
        with state_of().hook_lock:
            state_of().hook_notifications.clear()
            state_of().last_popup.clear()
            state_of().last_popup_message.clear()
            state_of().last_session_state.clear()
            state_of().hook_generation.clear()
        with state_of().collect_memo_lock:
            state_of().collect_memo.clear()
        # Route-shape tests exercise successful /api/notify requests, but do
        # not assert native delivery. Execute the notification code while
        # keeping its osascript process off the host.
        original_run = subprocess.run

        def run_without_native_delivery(*args: Any, **kwargs: Any) -> Any:
            command = args[0] if args else kwargs.get("args")
            if (
                isinstance(command, (list, tuple))
                and command
                and command[0] == "/usr/bin/osascript"
            ):
                return subprocess.CompletedProcess(command, 0)
            return original_run(*args, **kwargs)

        notify_patcher = mock.patch.object(
            subprocess, "run", side_effect=run_without_native_delivery
        )
        notify_patcher.start()
        self.addCleanup(notify_patcher.stop)

    def tearDown(self) -> None:
        with state_of().collect_memo_lock:
            state_of().collect_memo.clear()

    @staticmethod
    def _response(
        port: int,
        method: str,
        path: str,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, email.message.Message, bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            return response.status, response.headers, response.read()
        finally:
            conn.close()

    def test_served_page_bytes_equal_the_frontend_page(self) -> None:
        page = frontend_page.load_page()
        httpd = make_server(page_bytes=page)
        thread = serve_until_closed(httpd)
        try:
            code, _, served = self._response(httpd.server_port, "GET", "/")
            self.assertEqual(200, code)
            self.assertEqual(page, served)
        finally:
            httpd.shutdown()
            thread.join(timeout=5)


class CargentoServerTest(PageJsHarness):
    def test_page_marks_repeated_refresh_failures_as_stalled(self) -> None:
        self.assertIn('id="live-status"', PAGE_TEXT)
        self.assertIn("window.__refreshFailures < 2", PAGE_TEXT)
        self.assertIn("stalled · last update", PAGE_TEXT)
        self.assertIn("console.error", PAGE_TEXT)
        self.assertIn("latestSettledRefresh", PAGE_TEXT)
        self.assertIn("sequence < latestSettledRefresh", PAGE_TEXT)

    def test_entity_slugs_elide_in_the_middle_not_the_tail(self) -> None:
        """Entity slugs in one workflow share a long prefix and differ only at
        the end, so tail truncation rendered two different entities as the same
        string. The full value stays available as a title attribute."""
        self.assertIn("function sdSlug(slug)", APP_JS)
        self.assertIn('title="${esc(ent.slug)}">${esc(sdSlug(ent.slug))}', APP_JS)

        node = shutil.which("node")
        if node is None:
            self.skipTest("node not installed; CI runs this branch")
        # Just the helper and its constants. Taking the whole prefix would drag
        # in top-level browser globals (`location`) that node does not have.
        source = re.search(r"const SD_SLUG_MAX = .*?\n}\n", APP_JS, re.DOTALL)
        assert source is not None, "sdSlug and its constants moved"
        # Run the real function rather than restating its arithmetic here.
        probe = (
            source.group(0) + "\nconst cases = ['drc-3832',"
            " 'datarecce-recce-cloud-infra-pr-1573',"
            " 'datarecce-recce-cloud-infra-pr-1587'];\n"
            "console.log(JSON.stringify(cases.map(sdSlug)));\n"
        )
        with tempfile.TemporaryDirectory() as holder:
            script = Path(holder) / "probe.mjs"
            script.write_text(probe, encoding="utf-8")
            # Explicit UTF-8 both ways. node reads and writes UTF-8; `text=True`
            # alone decodes through the locale codec, so on Windows (cp1252) the
            # ellipsis comes back as "â€¦" — three characters, which fails both
            # the "elided" and the width assertion below for a reason that has
            # nothing to do with the code under test.
            proc = subprocess.run(
                [node, str(script)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
                check=True,
            )
        short, first, second = json.loads(proc.stdout)

        self.assertEqual("drc-3832", short)  # under the cap, untouched
        self.assertNotEqual(first, second)  # the whole point
        for rendered, full in ((first, "…-pr-1573"), (second, "…-pr-1587")):
            self.assertTrue(rendered.endswith(full[1:]), rendered)
            self.assertIn("…", rendered)
            self.assertLessEqual(len(rendered), 22)

    def test_output_rate_rows_use_hoverable_harness_badges(self) -> None:
        self.assertIn(
            '<span class="rrow-badge">${badge(r.key, true)}</span>',
            APP_JS,
        )

    def test_pi_badge_uses_the_explicit_pi_label(self) -> None:
        # A generic fallback monogram hides a missing harness presentation entry.
        rendered = self._run_page_js("console.log(JSON.stringify(HARNESS.pi));")
        self.assertEqual({"code": "PI", "name": "Pi"}, rendered)

    def test_page_ships_trailing_rate_sparklines(self) -> None:
        self.assertIn("SPARK_WINDOW_SEC = 300", APP_JS)
        self.assertIn("const rateHistory = []", APP_JS)
        self.assertIn("const sessRateHistory = new Map()", APP_JS)
        self.assertIn("function recordRates", APP_JS)
        self.assertIn("function sparkSVG", APP_JS)
        self.assertIn('class="spark-wrap"', APP_JS)
        self.assertIn('class="rate-spark"', APP_JS)
        # Buffers only grow on fresh payloads and drop points past the window.
        self.assertIn("recordRates(data)", APP_JS)
        self.assertIn("arr.shift()", APP_JS)

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_sparkline_buffers_behave_correctly(self) -> None:
        checks = """
const out = {};
{
  const arr = [];
  for(let t = 0; t <= 400; t += 5) pushPoint(arr, t, t);
  pushPoint(arr, 400, 999); // same-timestamp replay must be ignored
  out.pruned = {len: arr.length, first: arr[0].t,
                last: arr[arr.length-1].t, lastV: arr[arr.length-1].v};
}
{
  // Two live sessions whose display ids truncate identically must not
  // share one buffer (Gemini "session-*" fallback ids all become
  // "session-" after display truncation).
  recordRates({generated: 1000, summary: {rate_per_min: 14}, sessions: [
    {harness:"gemini", session:"session-", sid:"session-aaaa", rate_per_min:5},
    {harness:"gemini", session:"session-", sid:"session-bbbb", rate_per_min:9}]});
  const a = sessRateHistory.get("gemini:session-aaaa");
  const b = sessRateHistory.get("gemini:session-bbbb");
  out.aliasing = {buffers: sessRateHistory.size,
                  a: a && a[0] && a[0].v, b: b && b[0] && b[0].v};
  __setNow(1005);
  recordRates({generated: 1005, summary: {rate_per_min: 6}, sessions: [
    {harness:"gemini", session:"session-", sid:"session-aaaa", rate_per_min:6}]});
  const a2 = sessRateHistory.get("gemini:session-aaaa") || [];
  out.dropped = {buffers: sessRateHistory.size, aLen: a2.length};
}
{
  // Points carry the VIEWER's clock: a skewed/lagging server `generated`
  // must not shift timestamps, and a replayed `generated` records nothing.
  __setNow(1010);
  recordRates({generated: 999111, summary: {rate_per_min: 3}, sessions: []});
  const last = rateHistory[rateHistory.length-1];
  const lenBefore = rateHistory.length;
  __setNow(1011);
  recordRates({generated: 999111, summary: {rate_per_min: 4}, sessions: []});
  out.clock = {t: last.t, v: last.v, replayDropped: rateHistory.length === lenBefore};
}
{
  const pts = [{t:900, v:0}, {t:950, v:50}, {t:1000, v:100}];
  const svg = sparkSVG(pts, 1000, 100, 46, true);
  const nums = (svg.match(/-?\\d+(\\.\\d+)?/g) || []).map(Number);
  out.svg = {hasLine: svg.includes("<polyline"),
             finite: nums.length > 0 && nums.every(Number.isFinite),
             single: !sparkSVG([{t:1000, v:1}], 1000, 100, 46, true)
                       .includes("<polyline")};
}
console.log(JSON.stringify(out));
"""
        out = self._run_page_js(checks)
        # 300s window over t=0..400 step 5 keeps t=100..400; duplicate dropped.
        self.assertEqual({"len": 61, "first": 100, "last": 400, "lastV": 400}, out["pruned"])
        self.assertEqual({"buffers": 2, "a": 5, "b": 9}, out["aliasing"])
        # Departed session-bbbb is pruned; session-aaaa accumulates.
        self.assertEqual({"buffers": 1, "aLen": 2}, out["dropped"])
        # Viewer-clock stamping: server said 999111, viewer clock said 1010.
        self.assertEqual({"t": 1010, "v": 3, "replayDropped": True}, out["clock"])
        self.assertEqual({"hasLine": True, "finite": True, "single": True}, out["svg"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_mcp_tool_names_reach_the_page_as_a_service_and_an_action(self) -> None:
        # An MCP tool arrives under its wire name — a mangled triple joined by
        # double underscores. Printed raw it puts the transport's naming scheme
        # on screen instead of the service being called. Anything that is not an
        # MCP wire name must pass through untouched.
        checks = """
const out = {};
out.linear = humanTool("running mcp__claude_ai_Linear__list_issues");
out.plain = humanTool("running Bash");
out.github = humanTool("mcp__github__search_code");
out.hyphenated = humanTool("mcp__claude-in-chrome__computer");
out.pluginPrefix = humanTool("mcp__plugin_figma_figma__authenticate");
// Nothing that merely looks similar should be rewritten.
out.notMcp = humanTool("some__other__thing");
out.nullish = humanTool(null);
console.log(JSON.stringify(out));
"""
        out = self._run_page_js(checks)
        self.assertEqual("running Linear · list issues", out["linear"])
        self.assertEqual("running Bash", out["plain"], "rewrote an ordinary tool name")
        self.assertEqual("github · search code", out["github"])
        self.assertEqual("claude-in-chrome · computer", out["hyphenated"])
        self.assertEqual("figma figma · authenticate", out["pluginPrefix"])
        self.assertEqual("some__other__thing", out["notMcp"])
        self.assertEqual("", out["nullish"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_every_working_card_draws_the_same_anatomy(self) -> None:
        # Two cards stacked in one column with different parts present reads as
        # missing data. A turn with no estimate still draws its track, marked
        # indeterminate, rather than dropping a row of the card.
        checks = """
const base = {
  harness:"claude", session:"12345678", sid:"12345678", project:"proj",
  title:"t", last_prompt:"", state:"working", state_detail:"running Bash",
  active:true, last_activity:990, rate_per_min:100, total:0, done:0, open:0,
  progress_pct:0, eta_h:null, subagents:[], tasks:[]
};
const out = {};
out.estimated = workingCard({generated:1000},
  {...base, turn:{elapsed_h:"1m", eta_h:"3m", pct:26, long:false}});
out.unestimated = workingCard({generated:1000},
  {...base, turn:{elapsed_h:"1m", eta_h:null, pct:null, long:false}});
console.log(JSON.stringify({
  bothHaveTrack: [out.estimated, out.unestimated]
    .map(h => (h.match(/class="turnbar"/g) || []).length),
  onlyOneIndeterminate: [out.estimated, out.unestimated]
    .map(h => h.includes("turnfill indeterminate")),
  // The negative was stated on every card as well as once above the fold.
  noTaskFiller: !out.estimated.includes("no tracked tasks")}));
"""
        out = self._run_page_js(checks)
        self.assertEqual([1, 1], out["bothHaveTrack"], "a working card dropped its track")
        self.assertEqual([False, True], out["onlyOneIndeterminate"])
        self.assertTrue(out["noTaskFiller"], "the empty-task filler line came back")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_browser_notifications_fire_only_on_transitions_the_server_missed(self) -> None:
        # Exactly one layer may notify per transition
        # (design decision D-3 in docs/design-cross-platform.md).
        checks = """
__els.app = {innerHTML:""};
const blocked = {
  harness:"claude", session:"12345678", sid:"12345678", project:"proj",
  title:null, last_prompt:"", state:"needs_input", state_detail:"open question",
  active:true, last_activity:100, blocked_since:970, rate_per_min:0,
  total:0, done:0, open:0, progress_pct:0, eta_h:null, turn:null,
  subagents:[], tasks:[]
};
const idle = {...blocked, state:"idle", state_detail:"awaiting your message"};
const payload = (sessions, native) => ({
  generated:1000, window_hours:24, show_all:false, native_notify:native,
  harnesses:[], sessions,
  summary:{needs_input:0, working:0, rate_per_min:0, active_sessions:1,
           open_tasks:0, progress_pct:0, total_tasks:0, total_done:0}
});
const reset = perm => {
  __notifications = []; __notifyPermission = perm;
  notifyState = new Map(); notifyPrimed = false;
};
const out = {};

// The server already popped natively: the page must stay silent.
reset("granted");
render(payload([idle], "osascript"));
render(payload([blocked], "osascript"));
out.nativeOwnsIt = __notifications.length;

// No native backend (Linux/Windows today): the page notifies.
reset("granted");
render(payload([idle], ""));
render(payload([blocked], ""));
out.browserFired = __notifications.length;
out.body = __notifications[0] && __notifications[0].body;
out.tag = __notifications[0] && __notifications[0].tag;

// Still blocked on later refreshes: notify on the transition, not repeatedly.
render(payload([blocked], ""));
render(payload([blocked], ""));
out.noRepeat = __notifications.length;

// Cleared, then blocked again: that is a new transition.
render(payload([idle], ""));
render(payload([blocked], ""));
out.refired = __notifications.length;

// A session already blocked when the page opens must not pop on first paint.
reset("granted");
render(payload([blocked], ""));
out.primed = __notifications.length;

// Permission not granted: record state, raise nothing.
reset("default");
render(payload([idle], ""));
render(payload([blocked], ""));
out.ungranted = __notifications.length;

// Inactive sessions are outside the window and never notify.
reset("granted");
render(payload([{...idle, active:false}], ""));
render(payload([{...blocked, active:false}], ""));
out.inactive = __notifications.length;
console.log(JSON.stringify(out));
"""
        out = self._run_page_js(checks)
        self.assertEqual(0, out["nativeOwnsIt"], "would double-notify on macOS")
        self.assertEqual(1, out["browserFired"])
        self.assertEqual("[proj] open question", out["body"])
        self.assertEqual("claude:12345678", out["tag"])
        self.assertEqual(1, out["noRepeat"], "notified again while already blocked")
        self.assertEqual(2, out["refired"])
        self.assertEqual(0, out["primed"], "popped for a pre-existing block on first paint")
        self.assertEqual(0, out["ungranted"])
        self.assertEqual(0, out["inactive"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_notification_permission_control_reflects_state(self) -> None:
        checks = """
__els.app = {innerHTML:""};
const payload = native => ({
  generated:1000, window_hours:24, show_all:false, native_notify:native,
  harnesses:[], sessions:[],
  summary:{needs_input:0, working:0, rate_per_min:0, active_sessions:0,
           open_tasks:0, progress_pct:0, total_tasks:0, total_done:0}
});
const out = {};
__notifyPermission = "default"; out.prompt = notifyControl(payload(""));
__notifyPermission = "denied";  out.denied = notifyControl(payload(""));
__notifyPermission = "granted"; out.granted = notifyControl(payload(""));
__notifyPermission = "default"; out.native  = notifyControl(payload("osascript"));

// Granting re-renders so the button disappears without a reload.
__notifyPermission = "default";
render(payload(""));
out.buttonBefore = __els.app.innerHTML.includes("Enable notifications");
requestNotifyPermission();
out.buttonWhilePending = __els.app.innerHTML.includes("Enable notifications");
await __settle(); await __settle();
out.buttonAfter = __els.app.innerHTML.includes("Enable notifications");
console.log(JSON.stringify(out));
"""
        out = self._run_page_js(checks)
        self.assertIn("Enable notifications", out["prompt"])
        self.assertIn("notifications blocked", out["denied"])
        self.assertEqual("", out["granted"], "no control once permission is granted")
        self.assertEqual("", out["native"], "server owns popups; no control needed")
        self.assertTrue(out["buttonBefore"])
        self.assertTrue(out["buttonWhilePending"], "must not clear before permission settles")
        self.assertFalse(out["buttonAfter"], "control should clear after granting")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_page_works_without_the_notification_api(self) -> None:
        # Older or locked-down browsers expose no Notification constructor.
        checks = """
__els.app = {innerHTML:""};
Notification = undefined;
const d = {
  generated:1000, window_hours:24, show_all:false, native_notify:"",
  harnesses:[], sessions:[],
  summary:{needs_input:0, working:0, rate_per_min:0, active_sessions:0,
           open_tasks:0, progress_pct:0, total_tasks:0, total_done:0}
};
render(d);
requestNotifyPermission();
console.log(JSON.stringify({
  permission: notifyPermission(), control: notifyControl(d), rendered: !!__els.app.innerHTML
}));
"""
        out = self._run_page_js(checks)
        self.assertEqual("unsupported", out["permission"])
        self.assertEqual("", out["control"])
        self.assertTrue(out["rendered"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_needs_input_ui_uses_block_anchor_and_displayed_count(self) -> None:
        checks = """
__els.app = {innerHTML:""};
const activeNeed = {
  harness:"claude", session:"12345678", sid:"12345678", project:"sample",
  title:null, last_prompt:"Fallback prompt", state:"needs_input",
  state_detail:"permission needed", active:true, last_activity:100,
  blocked_since:970, rate_per_min:0, total:0, done:0, open:0,
  progress_pct:0, eta_h:null, turn:null, subagents:[], tasks:[]
};
const inactiveNeed = {...activeNeed, sid:"old", session:"old", active:false};
const data = {
  generated:1000, window_hours:24, show_all:true, harnesses:[],
  summary:{needs_input:99, working:0, rate_per_min:0, active_sessions:1,
           open_tasks:0, progress_pct:0, total_tasks:0, total_done:0},
  sessions:[activeNeed, inactiveNeed]
};
const row = needRow(data, activeNeed);
render(data);
console.log(JSON.stringify({
  rowUsesPrompt: row.includes("Fallback prompt"),
  rowUsesAnchor: row.includes(">30s<"),
  title: document.title,
  shownNeeds: (__els.app.innerHTML.match(/class="need"/g) || []).length
}));
"""
        out = self._run_page_js(checks)
        self.assertEqual(
            {
                "rowUsesPrompt": True,
                "rowUsesAnchor": True,
                "title": "(1!) Cargento",
                "shownNeeds": 1,
            },
            out,
        )

    def test_long_turn_warning_uses_styled_tooltip_not_native_title(self) -> None:
        # The (!) icon must use the app's styled tooltip (fast, themed), not
        # the native title attribute (multi-second hover delay).
        self.assertNotIn('class="lwarn" title=', APP_JS)
        self.assertIn('<span class="ltip">', APP_JS)
        self.assertIn('class="lwarn" tabindex="0"', APP_JS)
        self.assertIn(".lwarn:hover .ltip", PAGE_TEXT)
        self.assertIn("transition-delay:.2s", PAGE_TEXT)

    def test_page_restores_sparkline_hover_and_focus_after_render(self) -> None:
        # render() replaces #app's innerHTML every poll; the hover crosshair
        # and keyboard focus on the rate sparkline must be restored after.
        self.assertIn("sparkPointer", APP_JS)
        self.assertIn("restoreSparkState", APP_JS)
        self.assertIn("restoreSparkState(sparkFocused, savedPointer)", APP_JS)
        self.assertIn("preventScroll", APP_JS)

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_sparkline_hover_lifecycle_across_renders_and_window_exit(self) -> None:
        # A pointer leaving the window fires no in-document pointermove, so the
        # crosshair has to be cleared on mouseout instead.
        checks = """
const out = {};
const wrap = {
  id: "spark-main",
  dataset: {now: "1000"},
  style: {},
  closest(sel){ return sel === "#spark-main" ? this : null; },
  getBoundingClientRect(){
    return {left: 0, top: 0, right: 100, bottom: 46, width: 100, height: 46};
  },
  focus(){ document.activeElement = this; __fire("focusin", {target: this}); }
};
const tip = {style: {}, appendChild(){}};
const xline = {style: {}, parentElement: wrap};
__els["spark-main"] = wrap; __els["spark-tip"] = tip; __els["spark-x"] = xline;
__els["app"] = {innerHTML: ""};
pushPoint(rateHistory, 995, 100);
pushPoint(rateHistory, 1000, 200);
const d = {generated: 1000, window_hours: 24, show_all: false, harnesses: [],
           summary: {needs_input: 0, working: 0, rate_per_min: 200,
                     total_tasks: 0, open_tasks: 0, progress_pct: 0,
                     total_done: 0},
           sessions: []};
__fire("pointermove", {target: wrap, clientX: 50, clientY: 20});
out.hoverShown = tip.style.opacity == 1;
render(d);
out.restoredAfterRender = tip.style.opacity == 1;
__fire("mouseout", {relatedTarget: null});   // pointer left the window
out.clearedOnExit = tip.style.opacity == 0 && sparkPointer === null;
render(d);
out.staysHiddenAfterRender = tip.style.opacity == 0;
wrap.focus();
render(d);
out.focusRestored = document.activeElement === wrap && tip.style.opacity == 1;
console.log(JSON.stringify(out));
"""
        out = self._run_page_js(checks)
        self.assertEqual(
            {
                "hoverShown": True,
                "restoredAfterRender": True,
                "clearedOnExit": True,
                "staysHiddenAfterRender": True,
                "focusRestored": True,
            },
            out,
        )
