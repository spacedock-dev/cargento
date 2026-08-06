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
        assembled = frontend_page.load_page()
        styles = frontend_page.asset_path("styles.css").read_bytes()

        self.assertEqual(163_169, len(assembled))
        self.assertEqual(
            "e9347575d40147bf91065a17eb62baad78e2bf1e390dafdbd6d4430b20602ab5",
            hashlib.sha256(assembled).hexdigest(),
        )
        self.assertEqual(40_132, len(styles))
        self.assertEqual(
            "1b48fb41d645485c4485ec9b323765f77002ac769c9927df1d05842b49dcbb71",
            hashlib.sha256(styles).hexdigest(),
        )
        expected_parts = {
            "spark.js": (
                21_511,
                "51442d07feb7d8d76b88afd40dc71db35f141463898583d5c38f1fdef9ee61b9",
            ),
            "regular.js": (
                18_075,
                "6e79b289924590d0f33ddc6c4cd63b2863fe3fb89c1f7ebd4b161a9e359b159a",
            ),
            "mode.js": (
                1_931,
                "a88e29034f1f41d93213e4ab1b3bab9b6759869374d6bf391c4d37ef7e433def",
            ),
            "usage.js": (
                30_311,
                "afdba17070ff9df6d1f4e5c9ea90889d2f09396510ebf4fd24a702d077333a84",
            ),
            "controls.js": (
                3_363,
                "b45a331ff631f4293b463765c85f45ae9bc2b5b7b43401034727a5867a1ac0e7",
            ),
            "calm.js": (
                30_204,
                "e90f850adf637872bcbdb4990393d03e77837096394316925aa5e901eb9146cd",
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
        # and "resets first" are different answers and only one of them is true
        # at load; a projection that defaulted to the reassuring one would be
        # wrong precisely when the reader opened the dashboard to ask whether to
        # start something.
        rendered = self._run_page_js(
            self._BURN_FEED + "__setNow(1600);"
            "const w = pct => ({pct, resetAt: 3400});"
            "const out = {};"
            "out.one = burnLine(feed(1000, w(60), w(60)).a);"
            "out.two = burnLine(feed(1300, w(70), w(70)).a);"
            "out.three = burnLine(feed(1600, w(80), w(80)).a);"
            "console.log(JSON.stringify(out));"
        )
        # One reading is a level, not a rate. Two span a single 300s interval,
        # where one point of integer rounding is the entire measurement.
        self.assertIn("warming up · 1 of 3", rendered["one"])
        self.assertIn("warming up · 2 of 3", rendered["two"])
        for state in ("one", "two"):
            with self.subTest(readings=state):
                # Not a rate, not a wall, and above all not the reassuring
                # verdict: an empty buffer must never read as a measured one.
                self.assertNotIn("%/h", rendered[state])
                self.assertNotIn("wall", rendered[state])
                self.assertNotIn("resets first", rendered[state])
                # No tone either. An unknown that raises a colour is an unknown
                # pretending to be a finding.
                self.assertIn('class="u-burn"', rendered[state])
                # The tooltip has to name why it is cold, or the reader reads a
                # bug instead of a warm-up.
                self.assertIn("only while this tab is open", rendered[state])
                self.assertIn("lost on reload", rendered[state])
        # The third reading spans 600s — two intervals — and only then projects.
        self.assertIn("wall in", rendered["three"])

    def test_the_burn_projection_races_the_wall_against_the_windows_own_reset(self) -> None:
        # The arithmetic, and the comparison that is the point of it: 60 → 70 →
        # 80 over 600s is 10 points per 300s, so 120%/h, and the last 20 points
        # take 600s more. Both entries carry that identical series and differ
        # only in when their window resets, so the verdict is the only thing
        # under test. A percentage answers "how much is gone"; this answers "does
        # it run out before I get it back", which is the decision.
        rendered = self._run_page_js(
            self._BURN_FEED + "__setNow(1600);"
            # Identical percentages, and the reset instant is the only difference:
            # 3400 lands after the projected wall, 2000 before it.
            "const step = (asOf, pct) =>"
            " feed(asOf, {pct, resetAt: 3400}, {pct, resetAt: 2000});"
            "step(1000, 60); step(1300, 70);"
            "const last = step(1600, 80);"
            "console.log(JSON.stringify({wall: burnLine(last.a), safe: burnLine(last.b)}));"
        )
        # Wall at t=2200, reset at t=3400: the window fills first, by 20m.
        self.assertIn("~120%/h · wall in 10m", rendered["wall"])
        self.assertIn("20m before it resets", rendered["wall"])
        # The one reading that earns the alert tone.
        self.assertIn('class="u-burn hot"', rendered["wall"])
        # Same series, reset at t=2000 — before that wall — so the wall is not
        # the finding and is not stated as one. What is worth having instead is
        # where the window gets to by then: 80% plus 400s at 120%/h.
        self.assertIn("~120%/h · resets first", rendered["safe"])
        self.assertIn("about 93%", rendered["safe"])
        self.assertNotIn("wall in", rendered["safe"])
        self.assertIn('class="u-burn"', rendered["safe"])
        # Every rate is marked as an estimate and carries the span's own
        # resolution, because the input is an integer sampled three times.
        self.assertIn("±6%/h", rendered["wall"])

    def test_a_single_point_of_rounding_never_becomes_a_rate(self) -> None:
        # The published percentage is an integer and the server floors its quota
        # fetch at 300s (config.usage_poll_floor_sec), so the difference of two
        # samples carries up to a whole point of pure rounding. 40 → 40 → 41 is
        # a measured rise of one point: the true rise is anywhere from just above
        # zero to just under two, which over a 600s span is 0 to 12%/h. So no
        # rate is printed. A ceiling is, because that is the part the samples
        # support — and it still settles the race whenever even the ceiling
        # resets in time, which the two reset instants here separate.
        rendered = self._run_page_js(
            self._BURN_FEED + "__setNow(1600);"
            # One rounding step each. The first window is 59 points from full with
            # a week to run; the second is 9 points from full and resets in 23m.
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
        # 59 points to go and a week to do it in: 12%/h fills that, so the
        # ceiling does not rule out the wall and the row does not pretend it did.
        self.assertIn("may fill first", rendered["week"])
        self.assertIn('class="u-burn warn"', rendered["week"])
        # 9 points to go and 23m left: even at the ceiling the reset wins first,
        # which is a verdict the samples really do support.
        self.assertIn("resets first", rendered["near"])
        self.assertIn('class="u-burn"', rendered["near"])

    def test_a_window_with_no_reset_time_projects_against_nothing(self) -> None:
        # The live Claude capture carries a `weekly_scoped` limit with no
        # `resets_at`, and `_shape_window` omits `resetAt` entirely rather than
        # sending a zero. With no reset instant there is nothing to race, so the
        # verdict is unknown — never "resets first", which is the reading a zero
        # or a missing field would produce if it were treated as a time. Both
        # measurement states are exercised: a resolved rate, and a rise below the
        # resolution floor.
        rendered = self._run_page_js(
            self._BURN_FEED + "__setNow(1600);"
            # Neither window carries a reset instant. The first is rising fast
            # enough to resolve, the second is not.
            "const step = (asOf, a, b) => feed(asOf, {pct: a}, {pct: b});"
            "step(1000, 10, 40); step(1300, 13, 40);"
            "const last = step(1600, 16, 40);"
            "console.log(JSON.stringify({rate: burnLine(last.a), flat: burnLine(last.b),"
            " row: last.a}));"
        )
        # 3 points per 300s is 36%/h, and 84 points to go is 2h20m — so the wall
        # itself is knowable. Whether it arrives before the reset is not.
        self.assertIn("~36%/h · reset unknown", rendered["rate"])
        self.assertIn("no reset time", rendered["rate"])
        self.assertIn("cannot be answered", rendered["rate"])
        self.assertNotIn("resets first", rendered["rate"])
        # Unresolvable rise and no reset instant: two separate unknowns, and
        # neither collapses into a favourable answer.
        self.assertIn("under 12%/h · reset unknown", rendered["flat"])
        self.assertNotIn("resets first", rendered["flat"])
        # The gauge above it is unchanged: a window with no reset instant already
        # renders an em dash there, and the projection does not invent one.
        self.assertIn("↺ —", rendered["row"])

    def test_the_burn_series_ignores_a_replayed_reading_and_restarts_on_a_roll(self) -> None:
        # Two ways a naive buffer lies. A payload can be re-rendered — the same
        # `asOf` arrives on every 5s poll while the server's quota fetch sits
        # behind its 300s floor, and a UI action re-renders the payload already
        # in hand — so a sampler that counted renders would reach three
        # "readings" of one fetch in fifteen seconds and project off nothing. And
        # a window that rolls falls from 97 to 3, which fitted across the
        # discontinuity is a steep decline into a wall that is never coming.
        replay = self._run_page_js(
            self._BURN_FEED + "__setNow(1600);"
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
        self.assertIn("wall in", roll["before"])
        # The roll throws the history away and warms up again rather than fitting
        # a slope across a window that no longer exists.
        self.assertIn("warming up · 1 of 3", roll["after"])
        self.assertNotIn("%/h", roll["after"])

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
// buffer's five minutes of those means.
sessRateHistory.set("codex:fast", [{t: 900, v: 10}, {t: 950, v: 20}]);
const d = board([sess("fast", "codex", 3100)], {rate_window_sec: 300});
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
        self.assertEqual("3,100 tok/min (5m mean) · line trails the last 5m", out["sparkTip"])
        # Nothing on these surfaces may present the mean as a reading of now.
        for claim in ("right now", "live", "current", "instant"):
            with self.subTest(claim=claim):
                self.assertNotIn(claim, out["tenMin"])
                self.assertNotIn(claim, out["sparkTip"])

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
