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
    REGISTRY,
    STORE_KEYS,
    collect,
    config_patch,
    frontend_page,
    make_server,
    serve_until_closed,
    state_of,
    store_patch,
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
        for name in ("index.html", "styles.css", *frontend_page.APP_PARTS):
            with self.subTest(asset=name):
                self.assertTrue(frontend_page.asset_path(name).resolve().is_relative_to(SKILL_DIR))

    def test_load_page_preserves_all_three_byte_oracles(self) -> None:
        # Per-part first, deliberately. Every part feeds the assembled page, so a
        # one-part edit fails the assembled oracle too — and when that assertion
        # runs first it is the only one that ever reports, which is how the
        # per-part figures below went stale without anything noticing. Naming the
        # part that moved is also the more useful failure of the two.
        expected_parts = {
            "spark.js": (
                22_302,
                "b1fb777472fb2d7fa0c92bbab1e4ca2889137fe5ebc1741821bded8e065407ed",
            ),
            "regular.js": (
                25_814,
                "a6147d07cb7eca98380962cc7bdaf3a96924e65e283ff8a6a03577f06670b435",
            ),
            "mode.js": (
                1_938,
                "6baf5aa67046d4fca5027646f7797ed55f555c7d96f9e7bf8cfee516316c00a4",
            ),
            "usage.js": (
                41_207,
                "96f225d9d7c5e57e499b00f25bc98d98b6ed144bf11e9816ce822ca0df8475d3",
            ),
            "controls.js": (
                3_363,
                "b45a331ff631f4293b463765c85f45ae9bc2b5b7b43401034727a5867a1ac0e7",
            ),
            "calm.js": (
                35_881,
                "b1d73d7f0f20322306b91f1b30378aab2ab8c7cb3ef9d73aa8ea4bf663b90904",
            ),
            "notify.js": (
                3_185,
                "afd7a8ff735ea52b95e31a22f60f024d0bb752b7063860abc0e7bb1ae1c0fcae",
            ),
            "main.js": (
                7_985,
                "d756dcc8bfc7a67fab0e2aa085e897e52d611ac8a96c4f1bb3e1f42b6fa59faf",
            ),
            "live.js": (
                6_176,
                "661a904fca78f02d00f40a7ac8b9f1f8973ddff90bf8db123de5e336d063211f",
            ),
        }
        self.assertEqual(tuple(expected_parts), frontend_page.APP_PARTS)
        for name, (size, digest) in expected_parts.items():
            with self.subTest(part=name):
                data = frontend_page.asset_path(name).read_bytes()
                self.assertEqual(size, len(data))
                self.assertEqual(digest, hashlib.sha256(data).hexdigest())

        styles = frontend_page.asset_path("styles.css").read_bytes()
        self.assertEqual(40_557, len(styles))
        self.assertEqual(
            "57acb7356a9ccffbafe5e8cb8e109f168d9263df7c8a826c2c77dba1f7cff424",
            hashlib.sha256(styles).hexdigest(),
        )

        assembled = frontend_page.load_page()
        self.assertEqual(188_704, len(assembled))
        self.assertEqual(
            "c75eff394555636bf04d1589be45ea5a921102ef39dad1a3e0bf521b9d50ccfc",
            hashlib.sha256(assembled).hexdigest(),
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
            for name in frontend_page.APP_PARTS:
                (web / name).write_text("", encoding="utf-8")
            (web / "main.js").write_bytes(b"\xff")
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
                for name in frontend_page.APP_PARTS:
                    (web / name).write_text("js", encoding="utf-8")
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
            for name in ("index.html", "styles.css", *frontend_page.APP_PARTS):
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
                    (web / "main.js").write_bytes(b"\xff")
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
            state_of().snapshot.clear()
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
            state_of().snapshot.clear()

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

    def test_the_harness_table_matches_the_registry_in_key_order_and_label(self) -> None:
        # The page's HARNESS table and the Python registry are two hand-written
        # lists of the same thing, and nothing else compares them: renaming a
        # harness on one side only used to pass the entire suite, which is how
        # Antigravity sessions could keep rendering under Gemini's name and
        # icon after Gemini CLI was retired. Order matters too — registry order
        # is the order the page draws its chips.
        rendered = self._run_page_js(
            "console.log(JSON.stringify(Object.keys(HARNESS).map(k => [k, HARNESS[k].name])));"
        )
        self.assertEqual(
            [[spec.key, spec.label] for spec in REGISTRY],
            rendered,
        )

    def test_only_the_harnesses_with_token_accounting_declare_a_rate(self) -> None:
        # Rate coverage is partial and the page has to be told which half it is
        # looking at, because a harness that never measured and a session that
        # generated nothing both publish 0. Asserted as a literal set, not as a
        # re-read of the registry: comparing the flag to itself would hold no
        # matter which way a row was set. OpenCode, Cursor and Droid read no
        # token accounting at all, and Copilot's store carries AI-Unit quota
        # receipts with no per-message token counts — flipping one of them on
        # here without teaching its collector to fill `rate_per_min` would make
        # the page render a fabricated zero as a measurement.
        self.assertEqual(
            {"claude", "codex", "pi", "gemini", "antigravity", "goose"},
            {spec.key for spec in REGISTRY if spec.reports_rate},
        )

    def test_the_payload_publishes_the_rate_window_and_the_rate_coverage(self) -> None:
        # Both facts the burn surfaces need, and neither is derivable from a
        # session row. Every page-side test feeds a synthetic payload, so without
        # this one the server could stop sending either field and the page would
        # quietly fall back to its own default while the whole suite stayed green.
        # The window is patched to a value nothing else uses: asserting the
        # shipped 600 would also pass for a hardcoded 600.
        with (
            tempfile.TemporaryDirectory() as tmp,
            store_patch(**dict.fromkeys(STORE_KEYS, tmp)),
            config_patch(rate_window_sec=420),
        ):
            data = collect()

        self.assertEqual(420, data["rate_window_sec"])
        self.assertEqual(
            {spec.key: spec.reports_rate for spec in REGISTRY},
            {h["key"]: h["reports_rate"] for h in data["harnesses"]},
        )

    def test_a_consumption_only_entry_shows_its_figure_by_default(self) -> None:
        # Copilot reports what it spent but not what it is allowed, so its
        # entry carries `used` and no window gauges. Before `used` existed such
        # an entry rendered as a harness name and a timestamp with no number at
        # all, because every extras slot defaults to off — a row that reads as
        # broken. The figure must survive the DEFAULT config, untouched.
        rendered = self._run_page_js(
            "const e = {harness:'copilot', state:'ok', asOf: 1700000000, used:'16.61 AIU'};"
            "console.log(JSON.stringify({cfg: usageCfg, html: usageEntry(e)}));"
        )
        self.assertFalse(
            any(rendered["cfg"][k] for k in ("burn", "today", "cost")),
            "this test is only meaningful while the extras default to off",
        )
        html = rendered["html"]
        self.assertIn("16.61 AIU", html)
        self.assertIn('<span class="u-wlab">used</span>', html)

    def test_a_consumption_figure_is_not_dressed_up_as_a_gauge(self) -> None:
        # No limit means no fraction, so no track and no percentage. Rendering
        # one would invite reading an absolute figure as "16% of something".
        rendered = self._run_page_js(
            "const e = {harness:'copilot', state:'ok', asOf: 1700000000, used:'16.61 AIU'};"
            "console.log(JSON.stringify({html: usageEntry(e)}));"
        )
        html = rendered["html"]
        self.assertNotIn("cm-track", html)
        self.assertNotIn("cm-fill", html)
        self.assertNotIn("u-pct", html)
        # Scoped to the figure's own row: the harness icon is a percent-encoded
        # data URI, so a bare "%" search over the whole entry always matches.
        row = html[html.index('<div class="u-wrow">') : html.index("</div>", html.index("u-used"))]
        self.assertNotIn("%", row)

    def test_windowed_harnesses_keep_their_gauges(self) -> None:
        # The `used` row is additive, not a replacement: a harness publishing
        # windows must still render its bars and percentages.
        rendered = self._run_page_js(
            "const e = {harness:'codex', state:'ok', asOf: 1700000000,"
            " fiveH:{pct:63, reset:'14:20'}, week:{pct:31, reset:'Thu'}};"
            "console.log(JSON.stringify({html: usageEntry(e)}));"
        )
        html = rendered["html"]
        self.assertIn("cm-track", html)
        self.assertIn("63%", html)
        self.assertIn("31%", html)
        self.assertNotIn('<span class="u-wlab">used</span>', html)

    def test_a_reset_reads_as_a_countdown_not_a_clock_time(self) -> None:
        # "Thu 02:00" measured 92px in a 76px column, so it rendered as
        # "Thu 02:…" and named neither the day nor the hour. A countdown is
        # shorter and answers the question the window actually raises.
        rendered = self._run_page_js(
            "const t = nowSec();"
            "const cases = ["
            " ['minutes',   {resetAt: t + 16*60}],"
            " ['hours',     {resetAt: t + 2*3600 + 16*60}],"
            " ['days',      {resetAt: t + 86400 + 5*3600}],"
            " ['far',       {resetAt: t + 30*86400 + 21*3600}],"
            # Inexact remainders, so the truncation is actually exercised. With
            # whole multiples only, rounding and flooring agree and a countdown
            # that rounds UP passes: it would promise time the user has not got.
            " ['part hour', {resetAt: t + 86400 + 5*3600 + 31*60}],"
            " ['part min',  {resetAt: t + 2*3600 + 16*60 + 45}],"
            " ['under a min', {resetAt: t + 30}],"
            " ['exactly now', {resetAt: t}],"
            # The harness pins the page clock near zero, so a past instant is
            # expressed as a small step back: a large one would go negative and
            # be rejected as "no instant at all", which a real epoch never can.
            " ['past',      {resetAt: t - 300}],"
            " ['no instant', {reset: 'Thu 02:00'}],"
            " ['neither',   {}],"
            " ['junk',      {resetAt: 'soon', reset: 'Thu 02:00'}],"
            " ['zero',      {resetAt: 0, reset: 'Thu 02:00'}]];"
            "console.log(JSON.stringify(cases.map(c => [c[0], usageReset(c[1])])));"
        )
        got = dict(rendered)
        self.assertEqual("16m", got["minutes"])
        self.assertEqual("2h 16m", got["hours"])
        self.assertEqual("1d 5h", got["days"])
        self.assertEqual("30d 21h", got["far"])
        # Truncated down, never up: a countdown that rounds up overstates the
        # time left, which is the direction that misleads.
        self.assertEqual("1d 5h", got["part hour"])
        self.assertEqual("2h 16m", got["part min"])
        self.assertEqual("<1m", got["under a min"])
        # At or past the reset the window has rolled, so the percentage beside it
        # is the old one. "due" says so without inventing the new number.
        self.assertEqual("due", got["exactly now"])
        self.assertEqual("due", got["past"])
        # A producer that ships only the words still renders them.
        self.assertEqual("Thu 02:00", got["no instant"])
        self.assertEqual("Thu 02:00", got["junk"])
        self.assertEqual("Thu 02:00", got["zero"])
        self.assertEqual("—", got["neither"])

    def test_the_reset_row_keeps_the_absolute_time_in_its_tooltip(self) -> None:
        # The countdown replaces the clock time on screen; it must not lose it.
        rendered = self._run_page_js(
            "const e = {harness:'claude', state:'ok', asOf: 1700000000,"
            " week:{pct:77, reset:'Thu 02:00', resetAt: nowSec() + 86400 + 5*3600}};"
            "console.log(JSON.stringify({html: usageEntry(e)}));"
        )
        html = rendered["html"]
        self.assertIn('title="resets Thu 02:00"', html)
        self.assertIn("↺ 1d 5h", html)
        # The clock time is not also printed as the label, or the column is back
        # to the width that truncated.
        self.assertNotIn(">↺ Thu 02:00<", html)

    def test_a_borrowed_authority_names_the_harness_it_spends(self) -> None:
        # Pi has no allowance of its own, so a Pi row that says only "Pi" hides
        # whose quota is going. The provider id arrives raw and the page maps it,
        # because naming is presentation and the harness table lives here.
        rendered = self._run_page_js(
            "const cases = ["
            " ['mapped codex',   {harness:'pi', provider:'openai-codex', model:'gpt-5.6-sol'}],"
            " ['mapped claude',  {harness:'pi', provider:'anthropic', model:'claude-opus-5'}],"
            " ['mapped copilot', {harness:'pi', provider:'github-copilot', model:'x'}],"
            " ['unmapped key',   {harness:'pi', provider:'groq', model:'llama-4'}],"
            " ['unknown id',     {harness:'pi', provider:'brand-new-co', model:'x-1'}],"
            " ['model only',     {harness:'pi', provider:null, model:'gpt-5'}],"
            " ['neither',        {harness:'claude', provider:null, model:null}],"
            " ['prototype key',  {harness:'pi', provider:'constructor', model:'m'}]];"
            # Visible text as well as markup: the wrapper's class is literally
            # "via", so asserting on the HTML cannot tell the label apart from
            # the class name.
            "console.log(JSON.stringify(cases.map(c => [c[0],"
            " authorityBit(c[1]).replace(/<[^>]*>/g, '')])));"
        )
        got = dict(rendered)
        # A provider Cargento has a row for is named as that harness.
        self.assertEqual("via Codex · gpt-5.6-sol", got["mapped codex"])
        self.assertEqual("via Claude · claude-opus-5", got["mapped claude"])
        self.assertEqual("via Copilot · x", got["mapped copilot"])
        # One with no row keeps its own name. Claiming a harness that is not
        # involved would invent a session.
        self.assertEqual("via groq · llama-4", got["unmapped key"])
        # An unrecognised id passes through rather than being dropped or guessed.
        self.assertEqual("via brand-new-co · x-1", got["unknown id"])
        # "via gpt-5" would read as the model owning the quota.
        self.assertEqual("gpt-5", got["model only"])
        # Nothing to say, nothing rendered — no stray separator.
        self.assertEqual("", got["neither"])
        # `own()` exists because every plain object inherits `constructor`; a
        # provider named for an Object.prototype key must not resolve to it.
        self.assertEqual("via constructor · m", got["prototype key"])

    def test_the_authority_is_never_dressed_as_the_sessions_own_harness(self) -> None:
        # The icon trap: HARNESS carries an icon for Claude and Codex, so showing
        # the borrowed one's glyph is easy and wrong — a Claude mark on a Pi row
        # reads as a Claude session, which is the confusion this removes.
        rendered = self._run_page_js(
            "const s = {harness:'pi', provider:'anthropic', model:'claude-opus-5'};"
            "console.log(JSON.stringify({bit: authorityBit(s),"
            " meta: authorityMeta(s), empty: authorityMeta({harness:'pi'})}));"
        )
        self.assertNotIn("cm-ico", rendered["bit"])
        self.assertNotIn("mask:url", rendered["bit"])
        self.assertNotIn("<img", rendered["bit"])
        # The separator belongs to the helper, so a row with no authority does
        # not render a dangling " · ".
        self.assertTrue(rendered["meta"].startswith(" · "))
        self.assertEqual("", rendered["empty"])

    def test_a_monthly_cycle_renders_its_own_gauge_and_its_money(self) -> None:
        # Cursor meters spend against a monthly billing cycle. Exercised by
        # executing the shipped script rather than reading it, because that is
        # how Copilot's missing `used` row was found: the entry looked right in
        # Python and rendered as a name and a timestamp. Both figures must
        # survive the DEFAULT config, so `month` defaults on.
        rendered = self._run_page_js(
            "const e = {harness:'cursor', state:'ok', asOf: 1700000000,"
            " month:{pct:68, reset:'Sep 04'}, used:'$13.50 of $20.00'};"
            "console.log(JSON.stringify({cfg: usageCfg, html: usageEntry(e)}));"
        )
        self.assertTrue(rendered["cfg"]["month"], "the monthly slot must default to shown")
        html = rendered["html"]
        self.assertIn('<span class="u-wlab">mo</span>', html)
        self.assertIn("68%", html)
        self.assertIn("Sep 04", html)
        self.assertIn("cm-track", html)
        self.assertIn("$13.50 of $20.00", html)
        # The label says the window it actually is. "5h" or "wk" on a month
        # would be a wrong label on a real number.
        self.assertNotIn('<span class="u-wlab">wk</span>', html)
        self.assertNotIn('<span class="u-wlab">5h</span>', html)

    def test_hiding_the_monthly_slot_leaves_the_money_visible(self) -> None:
        # `used` is not gated by the stats config, so turning the bar off still
        # leaves a number rather than a row that reads as broken.
        rendered = self._run_page_js(
            "usageCfg.month = false;"
            "const e = {harness:'cursor', state:'ok', asOf: 1700000000,"
            " month:{pct:68, reset:'Sep 04'}, used:'$13.50 of $20.00'};"
            "console.log(JSON.stringify({html: usageEntry(e)}));"
        )
        html = rendered["html"]
        self.assertNotIn("68%", html)
        self.assertIn("$13.50 of $20.00", html)

    # The burn projection's series is built in the page from the percentages as
    # they arrive, so every one of these tests drives the real sampler by
    # rendering a sequence of payloads through usageBody() and then reads what
    # the entry says. Timestamps are the payload's own `asOf`, which is what the
    # sampler keys on, and the viewer clock is pinned with __setNow so the
    # countdowns are arithmetic rather than a race with the wall clock.
    # Every payload carries two windows, on two harnesses, so one run can hold
    # two scenarios that differ in exactly one input. They have to ride in the
    # SAME payload rather than being fed in turn: usageSample() drops the buffers
    # a payload does not carry, which is what keeps the map bounded, so
    # alternating harnesses would wipe each other's history. Each `feed` call is
    # one reading of both windows, and `asOf` is the only clock the sampler
    # counts — repeating it is a replayed payload, not a new reading.
    _BURN_FEED = (
        "usageCfg.burn = true;"
        "const feed = (asOf, a, b) => {"
        " const win = w => w.resetAt == null ? {pct: w.pct}"
        "   : {pct: w.pct, reset:'Thu 02:00', resetAt: w.resetAt};"
        " const ea = {harness:'claude', state:'ok', asOf, fiveH: win(a)};"
        " const eb = {harness:'codex', state:'ok', asOf, fiveH: win(b)};"
        " usageBody({usage: [ea, eb]});"
        " return {a: usageEntry(ea), b: usageEntry(eb)};};"
        # The projection line only, so an assertion cannot be satisfied by text
        # from the gauge above it.
        "const burnLine = html => (html.match(/<span class=\"u-burn[^]*?<\\/span>/) || [''])[0];"
    )

    def test_a_burn_projection_reads_unknown_until_it_has_readings_to_stand_on(self) -> None:
        # The warm-up state is the whole reason this signal is honest. There is
        # no history when a tab opens, the buffer dies on reload, and the samples
        # only accrue while a tab is open with usage on — so the first minutes of
        # every session have nothing to say and must say exactly that. "Unknown"
        # and "measured" are different answers and only one of them is available
        # at load; a projection that printed a figure off an empty buffer would
        # be wrong precisely when the reader opened the dashboard to ask whether
        # to start something.
        rendered = self._run_page_js(
            self._BURN_FEED +
            # The viewer clock tracks each reading as it lands, which is what a
            # live tab looks like and keeps the staleness bound out of a test
            # about the warm-up.
            "const w = pct => ({pct, resetAt: 3400});"
            "const out = {};"
            "__setNow(1000); out.one = burnLine(feed(1000, w(60), w(60)).a);"
            "__setNow(1300); out.two = burnLine(feed(1300, w(70), w(70)).a);"
            "__setNow(1600); out.three = burnLine(feed(1600, w(80), w(80)).a);"
            "console.log(JSON.stringify(out));"
        )
        # One reading is a level, not a rate. Two span a single 300s interval,
        # where one point of integer rounding is the entire measurement.
        self.assertIn("warming up · 1 of 3", rendered["one"])
        self.assertIn("warming up · 2 of 3", rendered["two"])
        for state in ("one", "two"):
            with self.subTest(readings=state):
                # No rate, no ceiling, no wall: an empty buffer must never render
                # as a measured one, in any of the words a measured one uses.
                self.assertNotIn("%/h", rendered[state])
                self.assertNotIn("wall", rendered[state])
                # And "warming up" is not "stale" either. A tab that opened a
                # moment ago is short of readings; it is not being served a frozen
                # one, and the two send the reader to different places.
                self.assertNotIn("stale", rendered[state])
                # No tone either. An unknown that raises a colour is an unknown
                # pretending to be a finding.
                self.assertIn('class="u-burn"', rendered[state])
                # The tooltip has to name why it is cold, or the reader reads a
                # bug instead of a warm-up.
                self.assertIn("only while this tab is open", rendered[state])
                self.assertIn("lost on reload", rendered[state])
        # The third reading spans 600s — two intervals — and only then projects:
        # 60 → 70 → 80 over 600s is 120%/h, and the last 20 points take about 10m.
        self.assertIn("~120%/h · wall 9m–10m", rendered["three"])

    def test_the_burn_row_states_the_quantities_and_never_races_the_reset(self) -> None:
        # This row used to end in a verdict — "resets first" or "may fill first" —
        # and across three review rounds every defect found in this signal was in
        # that verdict rather than in the numbers under it: the fitted rate and its
        # band came through a 4,000-case randomised sweep with no false-safe
        # reading. A binary claim composed over uncertain evidence fails toward the
        # reassuring answer, so the verdict is gone and the quantities stay.
        # That makes the row's independence from `resetAt` testable rather than a
        # promise: two windows fed byte-identical readings must render byte-
        # identical burn rows however far apart their resets fall. Four series, one
        # for each state the row can reach once it has history, and each fed to two
        # windows — one whose reset is 3m out at the first reading and 7m past by
        # the last, and one resetting nearly three hours out. A reset instant
        # already behind the clock used to produce the most reassuring reading the
        # band had.
        rendered = self._run_page_js(
            self._BURN_FEED + "const series = {proj: [60, 70, 80], slow: [40, 40, 41],"
            " spent: [98, 99, 100], warm: [30, 34]};"
            "const pairs = {};"
            "for(const [name, vals] of Object.entries(series)){"
            # The buffers are keyed per harness and slot and only cleared when a
            # payload stops carrying them, so one run of four series has to empty
            # them by hand: a rise from the previous series' last value is not a
            # roll and would not restart anything.
            " burnHistory.clear();"
            " let last;"
            " vals.forEach((pct, i) => { const asOf = 4000 + i * 300; __setNow(asOf);"
            "  last = feed(asOf, {pct, resetAt: 4200}, {pct, resetAt: 15000});});"
            " pairs[name] = [burnLine(last.a), burnLine(last.b)];}"
            "console.log(JSON.stringify(pairs));"
        )
        self.assertEqual(["proj", "slow", "spent", "warm"], sorted(rendered))
        for name, (early, late) in rendered.items():
            with self.subTest(state=name):
                self.assertEqual(early, late)
                # None of the verdict's vocabulary survives, in the label or the
                # tooltip, and no reading may be phrased against the reset at all.
                for gone in (
                    "resets first",
                    "may fill first",
                    "before it could fill",
                    "not ruled out",
                    "reset unknown",
                    "resets in",
                ):
                    self.assertNotIn(gone, early)
                # The warn tone existed only to signal "cannot rule out filling",
                # so no reading carries it.
                self.assertNotIn("u-burn warn", early)
        # The quantities the reader is left with, on the resolved series: the rate,
        # the wall as the interval its own band spans, and the ± that produced it.
        # 60 → 70 → 80 over 600s is 10 points per 300s, so 120%/h ±6, and the last
        # 20 points (19.5 to 20.5 of them, at integer resolution) take 9m to 10m.
        proj = rendered["proj"][0]
        self.assertIn("~120%/h · wall 9m–10m", proj)
        self.assertIn("±6%/h", proj)
        self.assertIn('class="u-burn"', proj)
        # A full window is the one reading that keeps a tone, because it is a level
        # the payload published rather than anything fitted here.
        self.assertIn('class="u-burn hot"', rendered["spent"][0])
        self.assertIn("window spent", rendered["spent"][0])

    def test_a_single_point_of_rounding_never_becomes_a_rate(self) -> None:
        # The published percentage is an integer and the server floors its quota
        # fetch at 300s (config.usage_poll_floor_sec), so the difference of two
        # samples carries up to a whole point of pure rounding. 40 → 40 → 41 is
        # a measured rise of one point: the true rise is anywhere from just above
        # zero to just under two, which over a 600s span is 0 to 12%/h. So no
        # rate is printed. A ceiling is, because that is the part the samples
        # support, and the only instant a ceiling supports is the earliest the
        # window could be full — which is a bound in one direction and belongs in
        # the tooltip, where it can say so.
        rendered = self._run_page_js(
            self._BURN_FEED + "__setNow(1600);"
            # One rounding step each, and the levels differ so the bound each
            # ceiling implies differs with them: the first window is 59 points from
            # full, the second 9.
            "const step = (asOf, a, b) =>"
            " feed(asOf, {pct: a, resetAt: 605000}, {pct: b, resetAt: 3000});"
            "step(1000, 40, 90); step(1300, 40, 90);"
            "const last = step(1600, 41, 91);"
            "console.log(JSON.stringify({week: burnLine(last.a), near: burnLine(last.b)}));"
        )
        for key in ("week", "near"):
            with self.subTest(window=key):
                # A ceiling says what it is. "~6%/h" off one rounding step would
                # be the fitted number presented as a measurement.
                self.assertIn("under 12%/h", rendered[key])
                self.assertNotIn("~", rendered[key])
                self.assertIn("too small for a span of integer percentages", rendered[key])
                # A ceiling names no wall on the row: an "under" figure paired with
                # a time reads as a schedule, and the samples are equally consistent
                # with this window not filling at all — which the tooltip says.
                self.assertNotIn("wall", rendered[key])
                self.assertIn("not filling at all", rendered[key])
        # The one instant a ceiling does support, and it is dated off the level:
        # 58.5 points at 12%/h for the first window, 8.5 for the second. Both take
        # the published integer's own half point of rounding on the way, because
        # the early end of a bound is the figure a reader acts on.
        self.assertIn("not be full for another 4h 52m", rendered["week"])
        self.assertIn("not be full for another 42m", rendered["near"])

    def test_a_window_with_no_reset_time_loses_nothing_from_the_projection(self) -> None:
        # The live Claude capture carries a `weekly_scoped` limit with no
        # `resets_at`, and `_shape_window` omits `resetAt` entirely rather than
        # sending a zero. That used to cost the row its verdict and, when the
        # instant was merely missing, its wall as well. It now costs nothing: the
        # projection never reads the field, so the two windows here — identical
        # readings, one with a reset instant and one without — must render the same
        # burn row, and the one that reports no reset time still gets its rate and
        # its wall interval in full.
        rendered = self._run_page_js(
            self._BURN_FEED + "__setNow(1600);"
            # 10 → 14 → 18 is 4 points per 300s. Only the reset instant differs.
            "const step = (asOf, pct) => feed(asOf, {pct}, {pct, resetAt: 3400});"
            "step(1000, 10); step(1300, 14);"
            "const last = step(1600, 18);"
            "console.log(JSON.stringify({none: burnLine(last.a), has: burnLine(last.b),"
            " row: last.a}));"
        )
        # 48%/h ±6, 82 points to go: between 1h 30m and 1h 57m of headroom.
        self.assertIn("~48%/h · wall 1h 30m–1h 57m", rendered["none"])
        self.assertEqual(rendered["none"], rendered["has"])
        # Nothing on the row is phrased against a reset it may not have, and the
        # old "reset unknown" state is gone rather than renamed.
        for gone in ("reset unknown", "no reset time", "resets first", "cannot be answered"):
            self.assertNotIn(gone, rendered["none"])
        # The gauge above it is unchanged: a window with no reset instant already
        # renders an em dash there, and the projection does not invent one.
        self.assertIn("↺ —", rendered["row"])

    def test_a_frozen_reading_stops_projecting_rather_than_republishing_one_fit(self) -> None:
        # `asOf` is under no obligation to advance. A stored Antigravity receipt
        # keeps being served with a frozen one for up to window_hours after its
        # harness stops (quota.py), and burnPush() drops a repeat of an `asOf` it
        # already holds — so the buffer stops growing while the page goes on
        # rendering every 5s. Nothing inside the buffer bounds its own age: the
        # sample count and the span were both satisfied hours ago and stay
        # satisfied forever, so the row republished one fit indefinitely. Observed
        # as byte-identical burn rows three hours apart whose newest reading was
        # 10,800s old, beside a reset countdown visibly still moving.
        # The bound is therefore against the viewer clock — the only clock that can
        # see the gap between the payload and now — and not against the rest of the
        # buffer, which is exactly what a frozen feed leaves intact.
        rendered = self._run_page_js(
            self._BURN_FEED + "const w = pct => ({pct, resetAt: 40000});"
            "const step = (asOf, pct) =>"
            " { __setNow(asOf); return feed(asOf, w(pct), w(pct)); };"
            "step(1000, 60); step(1300, 66);"
            "const out = {live: burnLine(step(1600, 72).a)};"
            # Nothing newer arrives. Re-feeding the same `asOf` is a re-render and
            # not a reading — the sampler keys on the timestamp — so each of these
            # moves the viewer clock and leaves the buffer untouched.
            "const at = t => { __setNow(t); return burnLine(feed(1600, w(72), w(72)).a); };"
            "out.edge = at(2200); out.past = at(2201); out.hours = at(12400);"
            # Same frozen buffer, and the payload's own level now reads 100. The
            # `asOf` is one it already holds, so this changes no sample.
            "out.full = burnLine(feed(1600, w(100), w(100)).a);"
            # Three fresh readings and the row projects again: the state is left by
            # evidence, not by waiting it out.
            "step(12700, 78); step(13000, 84);"
            "out.fed = burnLine(step(13300, 90).a);"
            "console.log(JSON.stringify(out));"
        )
        # 60 → 66 → 72 is 6 points per 300s: 72%/h ±6, with 28 points to go.
        self.assertIn("~72%/h · wall 21m–25m", rendered["live"])
        # The bound is 600s, two arrival intervals at the server's 300s quota
        # floor, and it is a bound rather than a target: at exactly 600s of age the
        # same fit still stands, and the countdowns have simply moved on with the
        # clock. One second past it, nothing is published.
        self.assertIn("~72%/h · wall 11m–15m", rendered["edge"])
        for key in ("past", "hours"):
            with self.subTest(age=key):
                # No rate, no ceiling, no wall — and no tone, because a reading
                # nobody took is not a finding.
                self.assertNotIn("%/h", rendered[key])
                self.assertNotIn("wall", rendered[key])
                self.assertIn('class="u-burn"', rendered[key])
                # The tooltip has to say the reading is old rather than that
                # Cargento is broken, and name the bound it failed.
                self.assertIn("nothing current to fit", rendered[key])
                self.assertIn("within 10m of now", rendered[key])
        # The age is on the row, not just in the tooltip: "stale" on its own reads
        # as a Cargento fault, and the number is what tells the reader whether
        # their harness went quiet ten minutes ago or stopped this morning.
        self.assertIn("stale · last reading 10m ago", rendered["past"])
        self.assertIn("stale · last reading 3h 0m ago", rendered["hours"])
        # The defect, stated as the assertion that would have caught it: the same
        # buffer three hours later must not render the row it rendered at the time.
        self.assertNotEqual(rendered["live"], rendered["hours"])
        # A full window outranks the age of the buffer, because it is not a
        # projection: the level came from the payload being rendered, the bar beside
        # it reads 100%, and the row's age is already stated by the band's own "as
        # of" line. Burying "the wall is here" under a note about staleness is the
        # one direction this row must never fail in.
        self.assertIn("window spent", rendered["full"])
        self.assertNotIn("stale", rendered["full"])
        # 78 → 84 → 90 over the same 600s span, and the trailing hour has dropped
        # every reading from the frozen stretch, so this is a clean three-sample
        # fit: 72%/h again, now with 10 points left.
        self.assertIn("~72%/h · wall 7m–9m", rendered["fed"])

    def test_the_burn_series_ignores_a_replayed_reading_and_restarts_on_a_roll(self) -> None:
        # Two ways a naive buffer lies. A payload can be re-rendered — the same
        # `asOf` arrives on every 5s poll while the server's quota fetch sits
        # behind its 300s floor, and a UI action re-renders the payload already
        # in hand — so a sampler that counted renders would reach three
        # "readings" of one fetch in fifteen seconds and project off nothing. And
        # a window that rolls falls from 97 to 3, which fitted across the
        # discontinuity is a steep decline into a wall that is never coming.
        replay = self._run_page_js(
            # The clock sits on the reading being replayed, so this stays a test
            # about the sampler rather than about the staleness bound.
            self._BURN_FEED + "__setNow(1000);"
            "const w = pct => ({pct, resetAt: 3400});"
            "feed(1000, w(40), w(40)); feed(1000, w(44), w(44));"
            "console.log(JSON.stringify({line: burnLine(feed(1000, w(44), w(44)).a)}));"
        )
        # Three payloads, one instant: one reading. A percentage that changes
        # within the same `asOf` does not buy a second one either — the sampler
        # keys on the timestamp, which is what makes a re-render free.
        self.assertIn("warming up · 1 of 3", replay["line"])
        roll = self._run_page_js(
            self._BURN_FEED + "__setNow(1600);"
            "const w = pct => ({pct, resetAt: 3400});"
            "feed(1000, w(60), w(60)); feed(1300, w(70), w(70));"
            "const out = {before: burnLine(feed(1600, w(80), w(80)).a)};"
            # The window rolls: a new allowance, a new reset, and a percentage
            # that falls instead of rising.
            "const rolled = pct => ({pct, resetAt: 21400});"
            "out.after = burnLine(feed(1900, rolled(5), rolled(5)).a);"
            "console.log(JSON.stringify(out));"
        )
        # Sanity: the same feed does project once the instants advance, so the
        # assertion above is about the replay and not about a dead sampler.
        self.assertIn("wall", roll["before"])
        # The roll throws the history away and warms up again rather than fitting
        # a slope across a window that no longer exists.
        self.assertIn("warming up · 1 of 3", roll["after"])
        self.assertNotIn("%/h", roll["after"])

    def test_the_burn_series_restarts_when_the_reset_instant_moves(self) -> None:
        # A fall is not the only sign of a window roll, and on its own it misses
        # the roll that matters most. Both windows here carry the SAME four
        # percentages, 10 → 14 → 18 → 22; the only difference is that the first
        # window's reset instant moves on the fourth reading. That is a new
        # allowance whose level climbed straight past where the old one stood, so
        # nothing fell, and a buffer watching only for a fall keeps both sides and
        # fits one slope across two allowances. Note which way that lies: the
        # pre-roll samples sit BELOW the new window's own start, which flattens the
        # fit, understates the new window's rate, and pushes its wall out — the
        # reassuring direction, on evidence that does not support it.
        rendered = self._run_page_js(
            self._BURN_FEED + "__setNow(1900);"
            # Identical readings; the reset instant is the only variable. The first
            # window's moves on the last step, the second's never does.
            "const step = (asOf, pct, moved) =>"
            " feed(asOf, {pct, resetAt: moved ? 19750 : 1750}, {pct, resetAt: 19750});"
            "step(1000, 10, false); step(1300, 14, false); step(1600, 18, false);"
            "const last = step(1900, 22, true);"
            "console.log(JSON.stringify({rolled: burnLine(last.a),"
            " held: burnLine(last.b)}));"
        )
        # The moved instant throws the history away, exactly as a fall does.
        self.assertIn("warming up · 1 of 3", rendered["rolled"])
        self.assertNotIn("%/h", rendered["rolled"])
        # And the control proves the restart is evidence-driven rather than
        # unconditional: the same four readings under one unmoved instant still
        # project, at 4 points per 300s — 48%/h ±4.8, with 78 points left to burn,
        # which the band spans as 1h 28m to 1h 49m.
        self.assertIn("~48%/h · wall 1h 28m–1h 49m", rendered["held"])

    def test_the_ceiling_a_slow_window_prints_is_a_real_upper_bound(self) -> None:
        # The "under X%/h" figure is the whole reading on a slow row, and the
        # earliest-full bound in its tooltip is derived from it, so it has to bound
        # every slope the samples are consistent with. Understating it understates
        # both — the phantom-headroom direction. The error that bounds it is not a
        # constant: with n integer samples the worst the ±0.5 rounding can do to the
        # fitted rise is 0.5·Σ|wᵢ| where wᵢ = span·(tᵢ - t̄)/Σ(tⱼ - t̄)², which is 1.0
        # whole point at three samples, 1.2 at four, and climbs towards 1.5 as the
        # buffer fills. A bound that assumes the three-sample figure stops being a
        # bound at the fourth sample. Four readings 300s apart, the server's own
        # fetch floor:
        rendered = self._run_page_js(
            self._BURN_FEED + "__setNow(1900);"
            # Both windows hold a rise too small to print as a rate, and differ
            # only in its shape.
            "const step = (asOf, a, b) =>"
            " feed(asOf, {pct: a, resetAt: 5900}, {pct: b, resetAt: 5900});"
            "step(1000, 89, 89); step(1300, 89, 90); step(1600, 90, 90);"
            "const last = step(1900, 90, 91);"
            "console.log(JSON.stringify({flat: burnLine(last.a),"
            " step: burnLine(last.b)}));"
        )
        # 89, 89, 90, 90 fits a rise of 1.2 points over 900s, and the rounding can
        # move that by 1.2 either way — so those four integers are equally
        # consistent with true values 88.5 … 90.499, a rise of 2.4 points, 9.6%/h.
        # The three-sample expression would have printed 8%/h, a fifth low, and
        # dated the earliest wall 12m later than the samples allow.
        self.assertIn("under 9.6%/h", rendered["flat"])
        self.assertNotIn("under 8%/h", rendered["flat"])
        self.assertIn("not be full for another 59m", rendered["flat"])
        # 89, 90, 90, 91 fits 1.8 points, and 1.8 + 1.2 is a true rise of up to 3
        # over 900s: 12%/h. Here the fitted slope plus its own error is what binds,
        # rather than the resolution floor, so a ceiling pinned to the floor alone
        # would understate this one too.
        self.assertIn("under 12%/h", rendered["step"])
        self.assertIn("not be full for another 42m", rendered["step"])
        for key in ("flat", "step"):
            with self.subTest(shape=key):
                # A ceiling is one-ended, and the tooltip has to keep the other end
                # open: these readings are as consistent with a window going
                # nowhere as with one 42m from full.
                self.assertIn("not filling at all", rendered[key])
                self.assertIn('class="u-burn"', rendered[key])

    def test_a_projected_wall_is_published_as_the_interval_its_band_spans(self) -> None:
        # The wall is a quantity and stays, but not as a point. A point wall is the
        # exact input a reader uses to make the comparison this row has stopped
        # making for them, and at this fit's resolution a point invites that
        # comparison at a precision the samples have not got: four readings 300s
        # apart, 80, 81, 83, 84, fit 16.8%/h with a worst-case error of 4.8, so the
        # same four integers are equally consistent with 21.6%/h and with 12%/h.
        # Publishing "57m" against a reset 50m out would have the reader conclude
        # "fine" from evidence that says "possibly not" — the removed verdict,
        # reconstructed in their head. So both ends are printed.
        # The level carries the same ±0.5 as the slope: 84 means 83.5 … 84.5, and
        # the early end is dated off the smaller headroom, because that end is the
        # one a reader acts on.
        rendered = self._run_page_js(
            self._BURN_FEED + "__setNow(1900);"
            # Identical percentages; the reset instant is the only difference, and
            # these two instants are the pair that used to produce opposite
            # verdicts — 4900 read as "may fill first", 4500 as "resets first".
            "const step = (asOf, pct) =>"
            " feed(asOf, {pct, resetAt: 4900}, {pct, resetAt: 4500});"
            "step(1000, 80); step(1300, 81); step(1600, 83);"
            "const last = step(1900, 84);"
            "console.log(JSON.stringify({open: burnLine(last.a),"
            " safe: burnLine(last.b)}));"
        )
        # 15.5 points at 21.6%/h is 43m; 16.5 at 12%/h is 1h 22m.
        self.assertIn("~17%/h · wall 43m–1h 22m", rendered["open"])
        self.assertIn("between 43m and 1h 22m from now", rendered["open"])
        # The point estimate, 3428s, is not the published figure. It is what the
        # row used to lead with and it sits a quarter of an hour inside the early
        # end of its own band.
        self.assertNotIn("57m", rendered["open"])
        # The rate still carries its own ±, so the interval can be checked against
        # the figure that produced it rather than taken on trust.
        self.assertIn("±4.8%/h", rendered["open"])
        # And the reader is pointed at the countdown to compare it with, which is
        # the comparison this row declines to make.
        self.assertIn("↺ countdown on this row", rendered["open"])
        # The two instants that used to divide these rows now divide nothing: same
        # readings, same row, whichever side of the band the reset falls on.
        self.assertEqual(rendered["open"], rendered["safe"])
        near = self._run_page_js(
            self._BURN_FEED + "const w = pct => ({pct, resetAt: 9000});"
            "__setNow(1000); feed(1000, w(80), w(80));"
            "__setNow(1300); feed(1300, w(90), w(90));"
            "__setNow(1600);"
            "console.log(JSON.stringify({near: burnLine(feed(1600, w(99), w(99)).a)}));"
        )
        # The ends can also round together, and a window a minute from full at
        # 114%/h does it: both 0.5 and 1.5 points are gone inside the minute. One
        # figure then, because "wall <1m–<1m" makes a sharp reading look vague, and
        # the tooltip says the same thing the same way rather than reading "between
        # <1m and <1m". (The row is HTML, so the "<" arrives escaped.)
        self.assertIn("~114%/h · wall &lt;1m", near["near"])
        self.assertIn("in about &lt;1m: both ends of the band", near["near"])
        self.assertNotIn("&lt;1m–", near["near"])
        self.assertNotIn("between &lt;1m", near["near"])

    def test_the_burn_error_band_widens_as_the_buffer_fills(self) -> None:
        # BURN_HISTORY_SEC is an hour, so a tab left open for one holds about a
        # dozen samples at the 300s fetch floor — the ordinary case, not an edge
        # one. At twelve evenly spaced readings the worst-case error on the fitted
        # rise is 1.38 points, not the 1.0 that three samples give, and both the
        # printed ± and the resolution floor have to move with it or the row gets
        # more confident as it gets more data.
        rendered = self._run_page_js(
            self._BURN_FEED + "__setNow(4300);"
            "const step = (asOf, a, b) =>"
            " feed(asOf, {pct: a, resetAt: 9000}, {pct: b, resetAt: 17000});"
            # Twelve readings 300s apart: a 55m span. The first window climbs 3
            # points a step; the second creeps from 90 to 91 halfway through.
            "let last;"
            "for(let i = 0; i < 12; i++) last = step(1000 + i * 300, 40 + 3 * i,"
            " i < 7 ? 90 : 91);"
            "console.log(JSON.stringify({fast: burnLine(last.a),"
            " creep: burnLine(last.b)}));"
        )
        # The rate itself is unaffected — 3 points per 300s is 36%/h either way —
        # so the ± is what is under test. 1.38 points over 3300s is 1.5%/h; the
        # three-sample expression would print 1.1%/h and sell the figure as a third
        # sharper than the samples support. The wall interval is where that shows
        # on the row: a dozen readings of a steady climb resolve it to four minutes.
        self.assertIn("~36%/h · wall 42m–47m", rendered["fast"])
        self.assertIn("±1.5%/h", rendered["fast"])
        self.assertNotIn("±1.1%/h", rendered["fast"])
        # The creeping window is the one that matters. Its fitted rise is 1.35
        # points, under the floor either way, so it prints a ceiling — and the
        # honest ceiling is 3%/h, which puts the earliest it could be full at 2h 48m.
        # The three-sample bound's 2.2%/h would push that out past three and a half
        # hours, an hour of headroom these readings do not support.
        self.assertIn("under 3%/h", rendered["creep"])
        self.assertIn("not be full for another 2h 48m", rendered["creep"])
        self.assertIn('class="u-burn"', rendered["creep"])

    def test_the_warm_up_counts_whichever_requirement_is_still_short(self) -> None:
        # Two requirements gate a projection, a count and a span, and the headline
        # has to name the one that is actually unmet. `asOf` is stamped by the
        # producer, not by the server's 300s fetch floor — Antigravity stamps every
        # pushed receipt with the moment it arrived (quota.py), and Codex re-derives
        # one per turn — so nine readings can land inside four minutes.
        fast = self._run_page_js(
            self._BURN_FEED + "__setNow(1240);"
            "const w = pct => ({pct, resetAt: 9000});"
            "let last;"
            "for(let i = 0; i < 9; i++) last = feed(1000 + i * 30, w(40 + i), w(40 + i));"
            "console.log(JSON.stringify({nine: burnLine(last.a)}));"
        )
        # Nine readings is not the shortfall; four minutes of span is. "9 of 3"
        # reads as a broken counter and sends the reader after the wrong bug.
        self.assertIn("warming up · 4m of 10m", fast["nine"])
        self.assertNotIn("9 of 3", fast["nine"])
        wide = self._run_page_js(
            self._BURN_FEED + "__setNow(4000);"
            # Two readings 50 minutes apart: span satisfied, count not.
            "const w = pct => ({pct, resetAt: 9000});"
            "feed(1000, w(40), w(40));"
            "const last = feed(4000, w(46), w(46));"
            "console.log(JSON.stringify({wide: burnLine(last.a)}));"
        )
        # The other way round, the count is what is missing and the count is what
        # is named — a span already past its requirement must not be printed as a
        # shortfall either.
        self.assertIn("warming up · 2 of 3", wide["wide"])
        self.assertNotIn("of 10m", wide["wide"])

    def test_the_burn_projection_stays_an_opt_in_and_still_accrues_while_off(self) -> None:
        # The default is deliberate, not an oversight. The series starts empty in
        # every new tab, so a default-on projection would read "warming up" under
        # every window for the first ten minutes of every session, which teaches
        # the reader that the band is half-built. Opt-in means the row is asked
        # for by someone who has read what it measures. The cost of that choice
        # is paid down by sampling regardless of the switch: turning it on shows
        # whatever history the tab already has instead of starting another wait.
        rendered = self._run_page_js(
            "const u = (asOf, pct) => ({harness:'claude', state:'ok', asOf,"
            " fiveH:{pct, reset:'Thu 02:00', resetAt: 3400}});"
            "__setNow(1600);"
            "const before = usageCfg.burn;"
            "usageBody({usage:[u(1000, 60)]});"
            "usageBody({usage:[u(1300, 70)]});"
            "const off = usageEntry(u(1300, 70));"
            "usageCfg.burn = true;"
            "const on = usageEntry(u(1300, 70));"
            "console.log(JSON.stringify({before, label: USAGE_STATS.find(s => s[0] === 'burn')[1],"
            " off, on}));"
        )
        self.assertFalse(rendered["before"], "the burn projection must default to off")
        # Off means absent, not dimmed: no row, no tooltip, no reserved space.
        self.assertNotIn("u-burn", rendered["off"])
        # The gauge it sits under is untouched by the switch.
        self.assertIn("70%", rendered["off"])
        # Switching it on finds the two readings the page took while it was off.
        self.assertIn("warming up · 2 of 3", rendered["on"])
        # The popover names it as a projection. "burn rate" would promise the
        # measured throughput figure the working cards carry, which this is not.
        self.assertEqual("burn projection", rendered["label"])

    def test_the_stats_config_offers_every_window_a_harness_can_publish(self) -> None:
        # The configure popover is hand-written alongside the slots the renderer
        # reads. A slot with no row here can never be turned back on once off.
        rendered = self._run_page_js(
            "console.log(JSON.stringify({stats: USAGE_STATS.map(s => s[0]),"
            " cfg: Object.keys(usageCfg)}));"
        )
        self.assertEqual(rendered["stats"], rendered["cfg"])
        for slot in ("fiveH", "week", "month"):
            self.assertIn(slot, rendered["stats"])

    def test_every_harness_has_a_two_letter_monogram(self) -> None:
        # The monogram is the icon fallback, so a harness with no ICON_PATH
        # entry (Pi, Antigravity, Droid) shows it and a blank one shows nothing.
        rendered = self._run_page_js(
            "console.log(JSON.stringify(Object.keys(HARNESS).map(k => [k, HARNESS[k].code])));"
        )
        self.assertEqual([spec.key for spec in REGISTRY], [key for key, _ in rendered])
        for key, code in rendered:
            with self.subTest(harness=key):
                self.assertRegex(code, r"^[A-Z]{2}$")
        self.assertEqual(
            len({code for _, code in rendered}),
            len(rendered),
            "two harnesses share a monogram, so their badges are ambiguous",
        )

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

    # A board of working sessions plus the strip that says, per harness, whether
    # a rate from it is a measurement at all. Copilot is the rate-less row: its
    # sessions carry the same 0 Claude's would for a session that generated
    # nothing, and only `reports_rate` separates the two facts.
    BURN_FIXTURE = """
const sess = (sid, harness, rate) => ({
  harness, session: sid, sid, project: "proj", title: sid, last_prompt: "",
  state: "working", state_detail: "running Bash", active: true, last_activity: 990,
  rate_per_min: rate, total: 0, done: 0, open: 0, progress_pct: 0, eta_h: null,
  turn: null, subagents: [], tasks: [], spacedock: null});
const strip = [
  {key: "claude", label: "Claude", discovered: true, error: null, reports_rate: true},
  {key: "codex", label: "Codex", discovered: true, error: null, reports_rate: true},
  {key: "copilot", label: "Copilot", discovered: true, error: null, reports_rate: false}];
const board = (sessions, over) => Object.assign(
  {generated: 1000, rate_window_sec: 600, harnesses: strip, sessions,
   summary: {rate_per_min: 0}}, over || {});
// What the card claims about burn: the pill's word, and its tooltip.
const pill = h => (h.match(/>(fastest[a-z ]*)</) || [null, null])[1];
const pillTip = h => (h.match(/class="pill" title="([^"]*)"/) || [null, null])[1];
"""

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_fastest_working_session_is_the_only_one_marked(self) -> None:
        # The regular view answers "which session is burning fastest" with a
        # marker, not an order: the card column is sorted server-side on values
        # that do not tick, and re-sorting it on rate would move cards under the
        # reader every poll. The marker has to be unambiguous — exactly the rows
        # holding the maximum carry it — and it has to stop claiming a maximum
        # over the whole board once part of the board cannot be compared.
        checks = (
            self.BURN_FIXTURE
            + """
const out = {};
const all = [sess("fast", "codex", 3100), sess("slow", "claude", 40),
             sess("zero", "claude", 0)];
const cards = (sessions, over) => {
  const d = board(sessions, over);
  return sessions.map(s => workingCard(d, s));
};
out.marked = cards(all).map(pill);
// A rate-less session on the board weakens the claim to the subset that can be
// compared, and says how many rows it could not see.
const withMute = [...all, sess("mute", "copilot", 0)];
out.hedged = cards(withMute).map(pill);
out.hedgedTip = pillTip(cards(withMute)[0]);
// Two sessions at the same rate are a tie, not a winner. Marking one of them
// would assert an order the numbers do not contain.
out.tied = cards([sess("a", "codex", 500), sess("b", "claude", 500),
                  sess("c", "claude", 10)]).map(pill);
// Nothing generating is not a race. Neither is a board where nothing measured.
out.allZero = cards([sess("a", "claude", 0), sess("b", "codex", 0)]).map(pill);
out.allUnknown = cards([sess("a", "copilot", 0), sess("b", "copilot", 0)]).map(pill);
// The claim is scoped to what this view draws cards for. An idle session can
// still carry a non-zero trailing mean, and it must not take the marker from a
// session that is actually generating.
const idleHotter = [sess("fast", "codex", 300),
                    {...sess("stopped", "claude", 9000), state: "idle", active: false}];
out.idleIgnored = [pill(cards([idleHotter[0]], {sessions: idleHotter})[0]),
                   pillTip(cards([idleHotter[0]], {sessions: idleHotter})[0])];
console.log(JSON.stringify(out));
"""
        )
        out = self._run_page_js(checks)
        self.assertEqual(["fastest", None, None], out["marked"], "the marker is not unique")
        self.assertEqual(["fastest known", None, None, None], out["hedged"])
        self.assertEqual(
            "3,100 tok/min, the highest of the 3 working sessions that report a rate, with 1"
            " reporting none — measured as a 10m mean, not as this instant",
            out["hedgedTip"],
            "the marker overstated what it could compare",
        )
        self.assertEqual(["fastest", "fastest", None], out["tied"], "a tie was broken arbitrarily")
        self.assertEqual([None, None], out["allZero"], "marked a fastest session on a quiet board")
        self.assertEqual([None, None], out["allUnknown"], "ranked harnesses that report no rate")
        self.assertEqual("fastest", out["idleIgnored"][0])
        self.assertIn("the highest of the 1 working session that report", out["idleIgnored"][1])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_working_card_says_when_the_rate_is_unknown_rather_than_zero(self) -> None:
        # Copilot, OpenCode, Cursor and Droid read no token accounting, so their
        # rows publish 0. Omitting the meter left a blank corner that reads as
        # zero, and drawing the sparkline would have been a flat line asserting a
        # measured silence. Both are claims about a number nobody has.
        checks = (
            self.BURN_FIXTURE
            + """
const out = {};
// A buffer with points, so a suppressed sparkline is a decision and not an
// absence of data.
for(const key of ["copilot:mute", "claude:zero"]){
  sessRateHistory.set(key, [{t: 900, v: 0}, {t: 950, v: 0}]);
}
const d = board([sess("mute", "copilot", 0), sess("zero", "claude", 0)]);
const mute = workingCard(d, d.sessions[0]);
const zero = workingCard(d, d.sessions[1]);
out.unknown = [mute.includes("rate unknown"), mute.includes(">0<"),
               mute.includes("class=\\"rate-spark\\""),
               mute.includes("reports no token accounting")];
// A measured zero is a different fact and prints its number.
out.measuredZero = [zero.includes(">0<"), zero.includes("rate unknown"),
                    zero.includes("tok / min")];
console.log(JSON.stringify(out));
"""
        )
        out = self._run_page_js(checks)
        self.assertEqual(
            [True, False, False, True],
            out["unknown"],
            "a rate-less harness was rendered as a measurement",
        )
        self.assertEqual(
            [True, False, True], out["measuredZero"], "a measured zero lost its number"
        )

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_rate_surfaces_name_the_window_the_payload_gave_them(self) -> None:
        # The figure is a trailing mean, and the window is the server's to
        # choose. Every surface that shows it reads the window off the payload,
        # so the words and the arithmetic cannot drift: a hardcoded "10 min"
        # would go on reading 10 min the day the server changed it.
        checks = (
            self.BURN_FIXTURE
            + """
const out = {};
const cap = h => (h.match(/class="tile-cap">([^<]*)</) || [null, null])[1];
const tile = over => rateTile(board([sess("fast", "codex", 3100)], over));
out.tenMin = cap(tile());
out.fiveMin = cap(tile({rate_window_sec: 300}));
out.ninetyMin = cap(tile({rate_window_sec: 5400}));
const stale = board([sess("fast", "codex", 3100)]);
delete stale.rate_window_sec;
out.absent = cap(rateTile(stale));
out.zeroIsNotAWindow = cap(tile({rate_window_sec: 0}));
// The per-session tooltip names both windows it depends on, and they differ:
// the number is a mean over the server's window, the line is the client-side
// buffer's five minutes of those means. The server window here is deliberately
// NOT 300 — at 300 it equals SPARK_WINDOW_SEC, and the assertion below would
// hold just as well for code that read one window and printed it twice.
sessRateHistory.set("codex:fast", [{t: 900, v: 10}, {t: 950, v: 20}]);
const d = board([sess("fast", "codex", 3100)], {rate_window_sec: 900});
out.sparkTip = (workingCard(d, d.sessions[0])
  .match(/class="rate-spark" title="([^"]*)"/) || [null, null])[1];
console.log(JSON.stringify(out));
"""
        )
        out = self._run_page_js(checks)
        self.assertEqual("tok / min · 10m mean", out["tenMin"])
        self.assertEqual("tok / min · 5m mean", out["fiveMin"], "the window label is hardcoded")
        self.assertEqual("tok / min · 1h 30m mean", out["ninetyMin"])
        self.assertEqual("tok / min · 10m mean", out["absent"], "a payload without the field")
        self.assertEqual("tok / min · 10m mean", out["zeroIsNotAWindow"])
        self.assertEqual("3,100 tok/min (15m mean) · line trails the last 5m", out["sparkTip"])
        # Nothing on these surfaces may present the mean as a reading of now.
        for claim in ("right now", "live", "current", "instant"):
            with self.subTest(claim=claim):
                self.assertNotIn(claim, out["tenMin"])
                self.assertNotIn(claim, out["sparkTip"])

    # Six discovered harnesses that report a rate, plus a discovered Droid that
    # does not. Five reporting harnesses is not a stress case: Claude, Codex, Pi,
    # Gemini and Antigravity on one machine is enough.
    WIDE_STRIP = """
const wide = [["claude", "Claude", true], ["codex", "Codex", true], ["pi", "Pi", true],
  ["gemini", "Gemini", true], ["antigravity", "Antigravity", true],
  ["goose", "Goose", true], ["droid", "Droid", false]]
  .map(([key, label, reports_rate]) =>
    ({key, label, discovered: true, error: null, reports_rate}));
const wideSessions = [sess("a", "claude", 300), sess("b", "codex", 250),
  sess("c", "pi", 200), sess("d", "gemini", 150), sess("e", "antigravity", 100),
  sess("f", "goose", 50), sess("g", "droid", 0)];
"""

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_rate_tile_keeps_the_row_the_unmeasured_dash_exists_for(self) -> None:
        # The rate-less row is the whole point of telling absence from zero, and
        # it sorts last so that it is never compared against a real number. A cap
        # applied to the sorted list therefore cut it first: on a board with five
        # reporting harnesses the dash was not dimmed, it was gone, and the tile
        # went back to showing only measured harnesses with nothing saying so.
        checks = (
            self.BURN_FIXTURE
            + self.WIDE_STRIP
            + """
const out = {};
const html = rateTile(board(wideSessions, {harnesses: wide, summary: {rate_per_min: 1050}}));
out.rows = (html.match(/class="rrow"/g) || []).length;
out.droidPresent = html.includes(">Droid<");
out.dashes = (html.match(/>—</g) || []).length;
// Last place, and with no bar: a rate-less harness must never draw a fill that
// reads as a share of the total.
out.dashIsLast = html.lastIndexOf(">—<") > html.lastIndexOf(">50<");
out.fills = (html.match(/class="rrow-fill" style="width:0%"/g) || []).length;
// The cap still applies to the rows that ARE ranked, so the tile stays short:
// eight reporting harnesses plus Droid is six rows, not nine.
const more = [...wide, {key: "copilot", label: "Copilot", discovered: true,
  error: null, reports_rate: true}, {key: "cursor", label: "Cursor",
  discovered: true, error: null, reports_rate: true}];
const wider = rateTile(board([...wideSessions, sess("h", "copilot", 400),
  sess("i", "cursor", 350)], {harnesses: more, summary: {rate_per_min: 1800}}));
out.cappedRows = (wider.match(/class="rrow"/g) || []).length;
out.cappedKeepsDroid = wider.includes(">Droid<");
console.log(JSON.stringify(out));
"""
        )
        out = self._run_page_js(checks)
        self.assertEqual(6, out["rows"], "the tile dropped a discovered harness")
        self.assertTrue(out["droidPresent"], "the rate-less row was cut, not dimmed")
        self.assertEqual(1, out["dashes"])
        self.assertTrue(out["dashIsLast"], "the unmeasured row left last place")
        self.assertEqual(1, out["fills"], "an unmeasured harness drew a bar")
        self.assertEqual(6, out["cappedRows"], "the ranked rows stopped being capped")
        self.assertTrue(out["cappedKeepsDroid"], "the cap ate the unmeasured row again")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_output_rate_total_says_when_it_is_only_a_floor(self) -> None:
        # `summary.rate_per_min` sums every active session's rate, and a harness
        # that never measures contributes the same 0 as a session that generated
        # nothing. Unqualified, the tile's numeral reads as the board's output
        # while being the measured part of it — Claude and Droid on screen, Droid
        # burning hard, and the hero shows the Claude-only figure.
        checks = (
            self.BURN_FIXTURE
            + """
const out = {};
const val = h => (h.match(/class="tile-val">([^<]*)</) || [null, null])[1];
const sub = h => (h.match(/class="tile-sub"[^>]*>([^<]*)</) || [null, null])[1];
const subTip = h => (h.match(/class="tile-sub" title="([^"]*)"/) || [null, null])[1];
const tile = (sessions, total) =>
  rateTile(board(sessions, {summary: {rate_per_min: total}}));
const mixed = tile([sess("a", "claude", 450), sess("b", "copilot", 0)], 450);
out.floored = [val(mixed), sub(mixed)];
out.flooredTip = subTip(mixed);
// Every active session measured: an exact figure, and no hedge on it.
const clean = tile([sess("a", "claude", 450)], 450);
out.exact = [val(clean), sub(clean)];
// A measured zero is not an absence. A board generating nothing states 0, not a
// floor of 0, or the qualifier stops meaning anything.
const quiet = tile([sess("a", "claude", 0)], 0);
out.measuredZero = [val(quiet), sub(quiet)];
// An idle Droid session still spends its own trailing mean into the sum, so it
// still makes the total a floor — the sum is over active sessions, not working
// ones, and the wording says which.
const idleMute = tile([sess("a", "claude", 450),
  {...sess("b", "copilot", 0), state: "idle"}], 450);
out.idleCounts = sub(idleMute);
// An inactive session is outside the window and outside the sum both.
const stale = tile([sess("a", "claude", 450),
  {...sess("b", "copilot", 0), active: false}], 450);
out.inactiveIgnored = [val(stale), sub(stale)];
console.log(JSON.stringify(out));
"""
        )
        out = self._run_page_js(checks)
        self.assertEqual(
            ["≥ 450", "no rate from 1 of 2 active sessions — a floor"],
            out["floored"],
            "the hero total summed an unmeasured session as zero, unqualified",
        )
        self.assertEqual(
            "Copilot reports no token accounting, so what its sessions are burning is"
            " missing from this total — and is not zero.",
            out["flooredTip"],
        )
        self.assertEqual(["450", None], out["exact"], "hedged a total it could fully account for")
        self.assertEqual(["0", None], out["measuredZero"], "a measured zero was called a floor")
        self.assertEqual("no rate from 1 of 2 active sessions — a floor", out["idleCounts"])
        self.assertEqual(["450", None], out["inactiveIgnored"], "counted a session outside the sum")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_harness_whose_collector_failed_is_not_a_measured_zero(self) -> None:
        # aggregate.py publishes `discovered: true`, an `error` string and NO
        # sessions for a harness whose collector raised. `reports_rate` still says
        # the harness does report a rate, because that is a property of the harness
        # rather than of the attempt — so a tile taking it at face value drew the
        # row as a measured 0 with a bar, and the floor note, which counts only
        # active sessions, found nothing missing behind a harness that published
        # none and printed the total as exact. A harness that failed to read is the
        # definition of unmeasured, and the strongest reason a total is a floor.
        checks = (
            self.BURN_FIXTURE
            + """
const out = {};
const val = h => (h.match(/class="tile-val">([^<]*)</) || [null, null])[1];
const sub = h => (h.match(/class="tile-sub"[^>]*>([^<]*)</) || [null, null])[1];
const subTip = h => (h.match(/class="tile-sub" title="([^"]*)"/) || [null, null])[1];
// Each split row as (harness, cell, cell tooltip), in rendered order, so the
// dash can be told from a zero AND the reason it gives from the other reason.
const rowCells = h => [...h.matchAll(/class="rrow-badge">.*?class="htip">([^<]*)<\\/span>/g)]
  .map((m, i) => {
    const cells = [...h.matchAll(/class="rrow-v"(?: title="([^"]*)")?>([^<]*)</g)];
    return [m[1], cells[i][2], cells[i][1] === undefined ? null : cells[i][1]];
  });
// One strip apart from the error, so nothing else can account for a difference.
const okStrip = [strip[0], {...strip[1]}];
const errStrip = [strip[0], {...strip[1], error: "OSError: [Errno 13] Permission denied"}];
const one = [sess("live", "claude", 2010)];
const tileOf = (sessions, harnesses, total) =>
  rateTile(board(sessions, {harnesses, summary: {rate_per_min: total}}));
const errored = tileOf(one, errStrip, 2010);
out.errRows = rowCells(errored);
out.errVal = [val(errored), sub(errored)];
out.errTip = subTip(errored);
out.errBars = (errored.match(/class="rrow-fill" style="width:0%"/g) || []).length;
// The same board with the collector intact: Codex published nothing because it
// HAS nothing, which is a measured zero and still reads as one.
const ok = tileOf(one, okStrip, 2010);
out.okRows = rowCells(ok);
out.okVal = [val(ok), sub(ok)];
// Both holes at once, each counted as itself: a session whose harness takes no
// measurement, and a harness that could not be read at all.
const mixed = tileOf([sess("live", "claude", 2010), sess("mute", "copilot", 0)],
  [...errStrip, strip[2]], 2010);
out.mixed = [val(mixed), sub(mixed)];
out.mixedTip = subTip(mixed);
// Two failures agree with themselves, and name both harnesses.
const two = tileOf(one, [strip[0], {...strip[1], error: "OSError: a"},
  {...strip[2], error: "OSError: b"}], 2010);
out.twoLine = sub(two);
out.twoTip = subTip(two);
// A collector that raised partway can still have published rows. Their numbers
// came out of a read that failed, so a card says unknown rather than printing
// one, and the marker will not race it against a harness that was read.
const partial = board([sess("live", "claude", 2010), sess("half", "codex", 5000)],
  {harnesses: errStrip, summary: {rate_per_min: 7010}});
const halfCard = workingCard(partial, partial.sessions[1]);
out.partialCard = [halfCard.includes("rate unknown"), halfCard.includes(">5,000<")];
out.partialLeaders = [...burnLeaders(partial).keys];
console.log(JSON.stringify(out));
"""
        )
        out = self._run_page_js(checks)
        self.assertEqual(
            [
                ["Claude", "2,010", None],
                [
                    "Codex",
                    "—",
                    "this harness could not be read, so its share is unknown — not zero",
                ],
            ],
            out["errRows"],
            "a harness whose collector raised was drawn as a measured zero",
        )
        self.assertEqual(
            ["≥ 2,010", "1 harness could not be read — a floor"],
            out["errVal"],
            "the total was presented as exact with a harness missing from it",
        )
        self.assertEqual(
            "Codex failed to collect, so none of its sessions reached this total"
            " — unread, not idle.",
            out["errTip"],
        )
        self.assertEqual(1, out["errBars"], "the unread harness drew a bar")
        self.assertEqual(
            [["Claude", "2,010", None], ["Codex", "0", None]],
            out["okRows"],
            "a harness that was read and had nothing lost its measured zero",
        )
        self.assertEqual(["2,010", None], out["okVal"], "hedged a total nothing was missing from")
        self.assertEqual(
            [
                "≥ 2,010",
                "no rate from 1 of 2 active sessions · 1 harness could not be read — a floor",
            ],
            out["mixed"],
            "the note reported one hole and dropped the other",
        )
        self.assertEqual(
            "Copilot reports no token accounting, so what its sessions are burning is"
            " missing from this total — and is not zero."
            " Codex failed to collect, so none of its sessions reached this total"
            " — unread, not idle.",
            out["mixedTip"],
        )
        self.assertEqual("2 harnesses could not be read — a floor", out["twoLine"])
        self.assertEqual(
            "Codex, Copilot failed to collect, so none of their sessions reached this total"
            " — unread, not idle.",
            out["twoTip"],
        )
        self.assertEqual(
            [True, False], out["partialCard"], "a row from a failed read printed its number"
        )
        self.assertEqual(["claude:live"], out["partialLeaders"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_burn_leader_is_worked_out_once_per_payload(self) -> None:
        # Every card asked the same question of the same payload: two passes over
        # the session list, each session re-scanning the harness strip, once per
        # card, every five seconds. The answer is a property of the payload, so it
        # is computed once and held under the payload's own identity.
        checks = (
            self.BURN_FIXTURE
            + """
const out = {};
const many = n => Array.from({length: n}, (_, i) => sess("s" + i, "claude", i * 10));
// Count the strip scans by wrapping the page's own lookup.
const real = rateKnown;
let calls = 0;
rateKnown = (d, s) => { calls++; return real(d, s); };
const draw = d => { calls = 0; d.sessions.forEach(s => workingCard(d, s)); return calls; };
const first = board(many(20));
out.firstPass = draw(first);
out.samePayloadAgain = draw(first);   // toggleIdle, a mode switch: cache hit
out.freshPayload = draw(board(many(20)));
out.scalesLinearly = draw(board(many(40)));
console.log(JSON.stringify(out));
"""
        )
        out = self._run_page_js(checks)
        # 20 inside the one burnLeaders pass, plus the one lookup each card makes
        # for its own meter. Recomputed per card it was 20 * 20 + 20 = 420.
        self.assertEqual(40, out["firstPass"], "burnLeaders was recomputed for every card")
        self.assertEqual(20, out["samePayloadAgain"], "a re-render of one payload recomputed it")
        self.assertEqual(40, out["freshPayload"], "a new payload reused a stale answer")
        self.assertEqual(80, out["scalesLinearly"], "the cost is still quadratic in cards")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_hero_sparkline_label_names_the_window_of_every_number_in_it(self) -> None:
        # The graphic's spoken form said "output rate, trailing 5 minutes, now N
        # tokens per minute": "now" over a trailing mean, and the line's five
        # minutes standing next to a figure averaged over the server's window.
        # Screen-reader users got the one wording on the board that still claimed
        # immediacy.
        checks = """
const out = {};
const aria = h => (h.match(/aria-label="([^"]*)"/) || [null, null])[1];
out.empty = aria(heroSpark({rate_window_sec: 600}));
pushPoint(rateHistory, 995, 400);
out.oneSample = aria(heroSpark({rate_window_sec: 600}));
pushPoint(rateHistory, 1000, 450);
out.tenMin = aria(heroSpark({rate_window_sec: 600}));
out.ninetyMin = aria(heroSpark({rate_window_sec: 5400}));
out.stalePayload = aria(heroSpark({}));
console.log(JSON.stringify(out));
"""
        out = self._run_page_js(checks)
        self.assertEqual(
            "output rate, no line yet — it needs a second sample",
            out["empty"],
            "described a line the buffer cannot draw",
        )
        self.assertEqual(
            "output rate, latest sample 400 tokens per minute, a 10m mean,"
            " no line yet — it needs a second sample",
            out["oneSample"],
        )
        self.assertEqual(
            "output rate, latest sample 450 tokens per minute, a 10m mean, line trails the last 5m",
            out["tenMin"],
        )
        self.assertEqual(
            "output rate, latest sample 450 tokens per minute, a 1h 30m mean,"
            " line trails the last 5m",
            out["ninetyMin"],
            "the spoken figure borrowed the line's window",
        )
        self.assertEqual(
            "output rate, latest sample 450 tokens per minute, a 10m mean, line trails the last 5m",
            out["stalePayload"],
            "a payload without the field",
        )
        # The number is a trailing mean. Nothing spoken over it may say otherwise.
        for claim in ("now ", "right now", "current", "live", "instant"):
            with self.subTest(claim=claim):
                self.assertNotIn(claim, out["tenMin"])

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
    def test_the_notification_title_names_the_harness_that_is_waiting(self) -> None:
        # It said "Claude is waiting on you" for every row, which was harmless
        # while Claude was the only harness that could report needs-input and a
        # lie the moment a second one could.
        checks = """
__els.app = {innerHTML:""};
const row = (harness) => ({
  harness, session:"12345678", sid:"12345678", project:"proj",
  title:null, last_prompt:"", state:"needs_input", state_detail:"open question",
  active:true, last_activity:100, blocked_since:970, rate_per_min:0,
  total:0, done:0, open:0, progress_pct:0, eta_h:null, turn:null,
  subagents:[], tasks:[]
});
const payload = (sessions, harnesses) => ({
  generated:1000, window_hours:24, show_all:false, native_notify:"",
  harnesses, sessions,
  summary:{needs_input:0, working:0, rate_per_min:0, active_sessions:1,
           open_tasks:0, progress_pct:0, total_tasks:0, total_done:0}
});
const registry = [{key:"claude", label:"Claude", discovered:true, error:null},
                  {key:"antigravity", label:"Antigravity", discovered:true, error:null}];
const reset = () => {
  __notifications = []; __notifyPermission = "granted";
  notifyState = new Map(); notifyPrimed = false;
};
const out = {};

reset();
render(payload([{...row("claude"), state:"idle"}], registry));
render(payload([row("claude")], registry));
out.claude = __notifications[0] && __notifications[0].title;

reset();
render(payload([{...row("antigravity"), state:"idle"}], registry));
render(payload([row("antigravity")], registry));
out.antigravity = __notifications[0] && __notifications[0].title;

// An unknown key falls back to the key rather than to a hardcoded name, so it
// reads oddly instead of reading wrongly.
reset();
render(payload([{...row("newharness"), state:"idle"}], registry));
render(payload([row("newharness")], registry));
out.unknown = __notifications[0] && __notifications[0].title;
console.log(JSON.stringify(out));
"""
        out = self._run_page_js(checks)
        self.assertEqual("Claude is waiting on you", out["claude"])
        self.assertEqual("Antigravity is waiting on you", out["antigravity"])
        self.assertEqual("newharness is waiting on you", out["unknown"])

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
