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

import event_hook
from cargento_runtime import cli, diagnostics, http_api, lifecycle, notifications
from cargento_runtime import io as runtime_io

from .page_harness import APP_JS, PAGE_TEXT, STYLES, PageJsHarness
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
                46_460,
                "e44eb8e73af3f6fe9c98f5dd65d763f6508b7bf029c98dcc308bf6688541a71e",
            ),
            "regular.js": (
                49_297,
                "81df3a571d3fbb17ad11c1584977f45cab3722bde6f7a027a02c911d0f962f43",
            ),
            "mode.js": (
                4_619,
                "526b9cae4ee29f756e2e00fca6c88213a1a7423cb5daa111dfbde59c0d121561",
            ),
            "usage.js": (
                51_910,
                "8fe192960d45c33ae10c19ac2b31171f4df3264e826c899f59131b0d354e5548",
            ),
            "controls.js": (
                7_271,
                "f1fe1ebd088d69c14f72364e88249f625cdba4d82f95239992dc76daceabcd0e",
            ),
            "ask.js": (
                7_755,
                "7ff71070fabf53c55754a3263825eb3c330ed1457bc8661d983d694df97ea218",
            ),
            "calm.js": (
                57_010,
                "2b531a9362240ec782ade0e7f9c91b4d7256cc6bb71f35608286fde034c3ae89",
            ),
            "session.js": (
                6_988,
                "d1fcdde8cee18cdc9757f025437c87602313ae56b9cc98b3c5a5e96aaa8fd224",
            ),
            "notify.js": (
                7_802,
                "da59647fec9a96f917f4908332604fd4fd3fba34d43be2750e25c2b4341b7250",
            ),
            "observer.js": (
                2_874,
                "aeef4f2ad3d702d434bfdafbc5123dec0f216a858b197b6ae00bc61fcf1873d9",
            ),
            "main.js": (
                11_805,
                "7d0cc625be52c14b1c52aec418d516c608a1d5ee7b843157c028be332fee6b7c",
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
        self.assertEqual(59_936, len(styles))
        self.assertEqual(
            "bfa562c732a7f534fe12f81af48db17985cecacaa8a8a621e58f0b3610bd7667",
            hashlib.sha256(styles).hexdigest(),
        )

        assembled = frontend_page.load_page()
        self.assertEqual(320_199, len(assembled))
        self.assertEqual(
            "9b1f9ea435cba66402e02835b57a50c8b77e498aa0e43c6018b12cf24bf0b4ff",
            hashlib.sha256(assembled).hexdigest(),
        )

    def test_both_layers_render_the_same_ask_sentence(self) -> None:
        # The two layers hardcode this sentence in two languages, and nothing
        # else compares them: `waiting_title`'s docstring records the gate lane
        # drifting apart the moment more than one harness could raise it. No node
        # needed — the JS is read as text.
        source = frontend_page.asset_path("notify.js").read_text(encoding="utf-8")
        # Matched in CODE rather than anywhere in the file. An `assertIn` over the
        # whole source is satisfied by a comment mentioning the sentence, so the
        # literal this test exists to pin could be changed while it stayed green.
        code = "\n".join(
            line for line in source.splitlines() if not line.lstrip().startswith(("/*", "*", "//"))
        )
        fallback = notifications.ASK_HARNESS_FALLBACK
        self.assertIn(f'|| "{fallback}") + " is asking you"', code)
        self.assertEqual(f"{fallback} is asking you", notifications.asking_title(""))
        # And the Python side composes it the same way round.
        self.assertEqual("Claude is asking you", notifications.asking_title("Claude"))

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


class RateSplitHeightTest(unittest.TestCase):
    """The rate tile's per-harness split is capped, and the cap is derived.

    `.hero` stretches its three tiles to one height, so an uncapped split made
    the two count tiles beside it grow with the harness count. The cap is written
    as arithmetic over two custom properties rather than a pixel total, and one
    of those has to keep agreeing with the badge that actually sets a row's
    height.
    """

    @staticmethod
    def _rule(selector: str) -> str:
        css = frontend_page.asset_path("styles.css").read_text(encoding="utf-8")
        # Matched on the exact selector plus its brace, so `.rate-rows` cannot
        # accidentally return the `.rate-rows:focus-visible` block.
        needle = selector + "{"
        start = css.index(needle) + len(needle)
        body: str = css[start : css.index("}", start)]
        return body

    def test_the_row_height_variable_matches_the_badge_that_sets_it(self) -> None:
        # The comment on `.rate-rows` says `--rrow-h` mirrors `.btile`. This is
        # what makes that true rather than aspirational: resize the badge and
        # this fails, instead of the cap silently keeping the old figure and
        # clipping a row or leaving a gap.
        rrow_h = re.search(r"--rrow-h:(\d+)px", self._rule(".rate-rows"))
        btile_h = re.search(r"height:(\d+)px", self._rule(".btile"))
        assert rrow_h is not None and btile_h is not None
        self.assertEqual(btile_h.group(1), rrow_h.group(1))

    def test_the_split_is_capped_at_three_rows_and_scrolls(self) -> None:
        rule = self._rule(".rate-rows")
        # Three rows and the two gaps between them, not four and not three gaps.
        self.assertIn("max-height:calc(var(--rrow-h) * 3 + var(--rrow-gap) * 2)", rule)
        self.assertIn("overflow-y:auto", rule)
        # The value column is right-aligned, so a scrollbar that appears with the
        # fourth row must not shift the numbers under it.
        self.assertIn("scrollbar-gutter:stable", rule)
        # The gap the cap does its arithmetic over has to be the gap in force.
        gap = re.search(r"--rrow-gap:(\d+)px", rule)
        assert gap is not None
        self.assertIn("gap:var(--rrow-gap)", rule)


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

    def test_the_rate_split_renders_one_capped_scroll_region(self) -> None:
        # Executed rather than grepped, because the thing under test is that the
        # rows land inside the capped container: a split that rendered them as
        # siblings of it would still match a string assertion on the opening tag.
        # Nine discovered harnesses, which is what the strip already carries.
        rendered = self._run_page_js(
            "const hs = ['claude','codex','pi','gemini','antigravity','copilot',"
            " 'opencode','cursor','goose'].map(k => ({key: k, label: k,"
            " discovered: true, error: null, reports_rate: true}));"
            "const ss = hs.map((h, i) => ({harness: h.key, sid: 's' + i,"
            " session: 's' + i, active: true, rate_per_min: 100 - i, state: 'working',"
            " state_detail: '', project: 'p/q', title: 't', last_activity: 990,"
            " total: 0, done: 0, open: 0, progress_pct: 0, eta_h: null, turn: null,"
            " subagents: [], tasks: [], spacedock: null}));"
            "const d = {generated: 1000, window_hours: 24, show_all: false,"
            " rate_window_sec: 600, harnesses: hs, sessions: ss,"
            " summary: {needs_input: 0, working: 9, rate_per_min: 500,"
            "  active_sessions: 9, open_tasks: 0, progress_pct: 0, total_tasks: 0,"
            "  total_done: 0}};"
            "const html = rateTile(d);"
            "const open = html.indexOf('class=\"rate-rows\"');"
            "const close = html.indexOf('</div>', html.lastIndexOf('rrow-v'));"
            "console.log(JSON.stringify({"
            ' containers: (html.match(/class="rate-rows"/g) || []).length,'
            " focusable: html.includes('tabindex=\"0\"'),"
            " labelled: html.includes('aria-label=\"output rate by harness\"'),"
            ' rows: (html.match(/class="rrow"/g) || []).length,'
            " rowsInside: open > -1 && open < html.indexOf('class=\"rrow\"')}));"
        )
        # One container, not one per row.
        self.assertEqual(1, rendered["containers"])
        # More rows than the cap shows, which is the case the cap exists for.
        self.assertGreater(rendered["rows"], 3)
        self.assertTrue(rendered["rowsInside"], "the rows are not inside the container")
        # A capped scroll region no keyboard can reach hides its overflow rows
        # outright, and this one has no keys of its own the way calm's body does.
        self.assertTrue(rendered["focusable"])
        self.assertTrue(rendered["labelled"])

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

    def test_only_the_two_harnesses_with_a_gate_path_declare_one(self) -> None:
        # The same shape as `reports_rate` above and for the same reason, on the
        # field where getting it wrong is worse. A harness with no gate detection
        # publishes no needs-input row, which is the identical payload a harness
        # WITH detection publishes when nothing is waiting -- so a row, a count and
        # a quiet board cannot say which of the two they are. Declaring it per
        # harness is what lets a reader tell "nothing is waiting" from "nothing
        # here could tell you".
        #
        # A literal set, not a re-read of the registry: comparing the flag to
        # itself would pass whichever way a row was set. Flipping one on here
        # without teaching its collector to emit `needs_input` would publish a
        # promise the board cannot keep, which is strictly worse than the gap.
        self.assertEqual(
            {"claude", "codex"},
            {spec.key for spec in REGISTRY if spec.reports_needs_input},
        )

    def test_the_gate_flag_matches_the_harnesses_that_actually_have_a_path(self) -> None:
        # The check that would have caught the defect this test was written for.
        # `reports_needs_input` is a hand-set bool, and the first review of the
        # change that added it found Codex shipping gate detection through the
        # event overlay while its own strip chip said "no gate detection" -- the
        # exact inversion the disclosure exists to prevent, pinned green by a
        # sibling test asserting a literal set.
        #
        # So derive the truth instead of restating it. A gate reaches the board by
        # exactly two routes: a collector that sets the state itself, which is
        # Claude alone, or an adapter that maps `input_requested`, which is
        # whatever `EVENTS_BY_HARNESS` says today. Anyone adding the second kind
        # gets a failure here rather than a lying chip.
        by_adapter = {
            harness
            for harness, table in event_hook.EVENTS_BY_HARNESS.items()
            if "input_requested" in table.values()
        }
        self.assertEqual(
            {"claude"} | by_adapter,
            {spec.key for spec in REGISTRY if spec.reports_needs_input},
        )

    def test_the_payload_publishes_the_gate_coverage_per_harness(self) -> None:
        # Nine of the ten rows are silent about gates by construction, and the page
        # cannot derive that from anything else it is sent. Without this the server
        # could stop publishing the flag and every page-side test would stay green,
        # because they all feed synthetic payloads.
        with (
            tempfile.TemporaryDirectory() as tmp,
            store_patch(**dict.fromkeys(STORE_KEYS, tmp)),
        ):
            data = collect()

        self.assertEqual(
            {spec.key: spec.reports_needs_input for spec in REGISTRY},
            {h["key"]: h["reports_needs_input"] for h in data["harnesses"]},
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
            " ['provider only',  {harness:'pi', provider:'anthropic', model:null}],"
            " ['blank model',    {harness:'goose', provider:null, model:'   '}],"
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
        # "via gpt-5" would read as the model owning the quota, so the value is
        # labelled instead. The label is also what gives the dash below a
        # referent: a bare "—" in a metadata line says nothing in particular is
        # missing.
        self.assertEqual("model gpt-5", got["model only"])
        # Not nothing. Every session runs on some model, so an unfilled `model` is
        # a gap in Cargento's reading rather than a fact about the session, and a
        # blank slot is indistinguishable from a measurement. Four harnesses in
        # ten report no model, so this is the common row and not an edge.
        self.assertEqual("model —", got["neither"])
        # The dash belongs to the model, so a known authority does not absorb it.
        self.assertEqual("via Claude · model —", got["provider only"])
        # Whitespace is not a reading. A producer that ships "   " gets the dash,
        # not a pill containing nothing.
        self.assertEqual("model —", got["blank model"])
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
        # The separator belongs to the helper, so no caller has to know whether
        # anything rendered.
        self.assertTrue(rendered["meta"].startswith(" · "))
        # And there is always something now: the model slot is a slot. A row with
        # neither provider nor model still carries its dash, so this helper no
        # longer has an empty return at all.
        self.assertTrue(rendered["empty"].startswith(" · "))
        self.assertIn("model —", rendered["empty"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_session_says_its_model_is_unread_rather_than_leaving_the_slot_blank(self) -> None:
        # The rate meter's argument, applied to the model. Four harnesses in ten
        # report no model after this batch, so an omitted clause would leave the
        # commonest row silently claiming nothing — and a blank slot renders
        # identically to a measurement, which is the one collapse this field is
        # here to prevent. Unlike consumption, absence here is never a fact about
        # the world: every session runs on some model, so the only thing missing
        # is our reading of it, and the tooltip has to say so in those terms.
        checks = """
const out = {};
const seen = h => h.replace(/<[^>]*>/g, "");
const titleOf = h => (h.match(/title="([^"]*)"/) || [null, ""])[1];
const unread = authorityBit({harness: "goose", provider: null, model: null});
out.unread = [seen(unread).includes("—"), seen(unread) === "model —",
              titleOf(unread).includes("Goose"), unread.includes(">0<")];
out.tip = titleOf(unread);
// A measured model is a different fact and prints its string, with no dash.
const known = authorityBit({harness: "goose", provider: null, model: "gpt-5"});
out.measured = [seen(known), known.includes("—")];
// A harness with no row in the table names itself rather than "undefined", and a
// row with no harness at all still says something.
out.unknownHarness = titleOf(authorityBit({harness: "brand-new-cli", model: null}));
out.noHarness = titleOf(authorityBit({model: null}));
// The same dash on a harness that DOES read a model: Claude publishes null for
// every session that is not active, so this is the ordinary inactive-Claude row,
// rendered on a board where the card above it reads `model claude-opus-5`.
out.claude = titleOf(authorityBit({harness: "claude", provider: null, model: null}));
// And on the borrowed-authority path, where the note is appended to the quota
// clause rather than standing alone.
out.borrowed = titleOf(
  authorityBit({harness: "pi", provider: "anthropic", model: null}));
console.log(JSON.stringify(out));
"""
        out = self._run_page_js(checks)
        self.assertEqual(
            [True, True, True, False],
            out["unread"],
            "an unread model was rendered as a measurement, a blank, or a zero",
        )
        self.assertIn("unknown — not unset", out["tip"])
        # Whose gap it is: Cargento's, and only for this reading. The sentence is
        # pinned verbatim because every clause in it is load-bearing.
        self.assertEqual(
            "Cargento read no model for this Goose session on this refresh, so which"
            " model it runs on is unknown — not unset. Every session runs on some"
            " model.",
            out["tip"],
        )
        # Two claims the sentence must never make. "Goose does not report the model"
        # is about the vendor and nobody measured it. "Cargento does not read a
        # model for <Harness> sessions" is about coverage and is flatly false on six
        # of ten harnesses, each of which publishes null for individual sessions:
        # Claude for anything inactive, Codex for any `?all=1` row, Copilot when the
        # usage row truncates, Cursor by store design. Worse than wrong, it tells
        # the reader the gap is intended, which is how the bug report never gets
        # filed. A session-level sentence is honest on all three roads to the dash:
        # a harness with no reader, a reader that returned nothing here, and a store
        # that could not be read this time.
        self.assertNotIn("does not report", out["tip"])
        self.assertNotIn("does not read a model for", out["tip"])
        self.assertNotIn(" sessions", out["tip"])
        self.assertEqual(["model gpt-5", False], out["measured"])
        self.assertIn("brand-new-cli", out["unknownHarness"])
        self.assertNotIn("undefined", out["unknownHarness"])
        self.assertNotIn("undefined", out["noHarness"])
        # The Claude row is the finding this wording exists for: the old sentence
        # told a reader looking at a cancelled Claude session that Cargento does not
        # read models for Claude, three inches under a Claude card showing one.
        self.assertEqual(
            "Cargento read no model for this Claude session on this refresh, so which"
            " model it runs on is unknown — not unset. Every session runs on some"
            " model.",
            out["claude"],
        )
        self.assertNotIn("does not read a model for", out["borrowed"])
        self.assertIn("Cargento read no model for this Pi session", out["borrowed"])
        # Naming the harness is allowed; claiming something about it is not. Every
        # sentence above scopes the name inside "this <name> session".
        for tip in (out["tip"], out["claude"], out["borrowed"], out["noHarness"]):
            self.assertIn("Cargento read no model for this", tip)
            self.assertIn("Every session runs on some model.", tip)

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_subagent_model_shows_only_where_two_readings_disagree(self) -> None:
        # The rule is a claim about two measurements. `child !== parent` is the
        # spelling that reads naturally and is wrong: the parent's model is null on
        # the four harnesses that report none and on any session the other six
        # could not read, so that comparison is true for every measured child on
        # those rows and would print "this one is running somewhere else"
        # across a whole board on the strength of one reading. One reading against
        # a gap is not a comparison, and the case below that guards it is
        # `childOnly`.
        checks = """
const out = {};
const shown = (parent, child) =>
  childModelShown({harness: "claude", provider: null, model: parent}, child);
out.differ = shown("claude-opus-5", {name: "review", model: "claude-fable-5"});
out.same = shown("claude-opus-5", {name: "review", model: "claude-opus-5"});
out.childOnly = shown(null, {name: "review", model: "claude-fable-5"});
out.parentOnly = shown("claude-opus-5", {name: "review", model: null});
out.neither = shown(null, {name: "review", model: null});
// Whitespace is not a reading on either side.
out.blankChild = shown("claude-opus-5", {name: "review", model: "   "});
out.blankParent = shown("   ", {name: "review", model: "claude-fable-5"});
// No case folding, no suffix stripping, no prefix match: two vendor strings are
// one model when they are the same string. Anything looser is inference, and an
// inferred match hides exactly the fact this chip exists to show.
out.caseDiff = shown("GPT-5", {name: "review", model: "gpt-5"});
out.prefix = shown("gpt-5", {name: "review", model: "gpt-5-mini"});
// A producer still shipping bare labels degrades to name-only rather than
// rendering "[object Object]" — which is what lets the collectors convert one at
// a time.
out.bareString = shown("claude-opus-5", "review");
out.names = [subName({name: "review", model: "m"}), subName("review"), subName(null),
             subName({}), subName({name: 7})];
out.models = [subModel({name: "r", model: "m"}), subModel("r"), subModel(null),
              subModel({name: "r"}), subModel({name: "r", model: 7})];
console.log(JSON.stringify(out));
"""
        out = self._run_page_js(checks)
        self.assertEqual("claude-fable-5", out["differ"])
        self.assertIsNone(out["same"], "the parent's own model was repeated under its child")
        self.assertIsNone(
            out["childOnly"],
            "a measured child was called 'differs' against a parent nobody read —"
            " this fires on four harnesses in ten and on any unread session of the"
            " other six",
        )
        self.assertIsNone(out["parentOnly"])
        self.assertIsNone(out["neither"])
        self.assertIsNone(out["blankChild"])
        self.assertIsNone(out["blankParent"])
        self.assertEqual("gpt-5", out["caseDiff"], "two vendor strings were folded into one model")
        self.assertEqual("gpt-5-mini", out["prefix"])
        self.assertIsNone(out["bareString"])
        self.assertEqual(["review", "review", "", "", "7"], out["names"])
        self.assertEqual(["m", None, None, None, None], out["models"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_subagent_chip_is_drawn_only_for_the_child_that_differs(self) -> None:
        # The predicate above, through the card that renders it. There must be
        # exactly one definition of the rule for both views to read, so a card that
        # re-derived it inline would pass the predicate test and fail here.
        checks = (
            self.SPEND_FIXTURE
            + """
const out = {};
const parent = sess("s1", "claude", {model: "claude-opus-5", subagents: [
  {name: "elsewhere", model: "claude-fable-5"},
  {name: "alongside", model: "claude-opus-5"},
  {name: "unmeasured", model: null},
  "still-a-string"]});
const card = workingCard(board([parent]), parent);
out.chips = (card.match(/class="subpill-m"/g) || []).length;
out.names = [...card.matchAll(/class="subdot"><\\/span>([^<]*)/g)].map(m => m[1]);
out.chipText = [...card.matchAll(/class="subpill-m"[^>]*>([^<]*)/g)].map(m => m[1]);
out.chipTip = (card.match(/class="subpill-m" title="([^"]*)"/) || [null, ""])[1];
// A parent nobody read draws no chip at all, however many children report one.
const blind = sess("s2", "claude", {model: null, subagents: [
  {name: "a", model: "claude-fable-5"}, {name: "b", model: "claude-opus-5"}]});
out.blindChips = (workingCard(board([blind]), blind).match(/class="subpill-m"/g) || []).length;
// The +N tail still counts elements, not chips.
const many = sess("s3", "claude", {model: "m0", subagents:
  Array.from({length: 9}, (_, i) => ({name: "sub" + i, model: "m" + i}))});
const manyCard = workingCard(board([many]), many);
out.more = manyCard.includes("+3 more");
out.manyChips = (manyCard.match(/class="subpill-m"/g) || []).length;
console.log(JSON.stringify(out));
"""
        )
        out = self._run_page_js(checks)
        self.assertEqual(1, out["chips"], "the chip was drawn for a child that matches its parent")
        # Every child keeps its name whatever shape it arrived in.
        self.assertEqual(["elsewhere", "alongside", "unmeasured", "still-a-string"], out["names"])
        self.assertEqual(["claude-fable-5"], out["chipText"])
        # "this session", not "its parent session". Antigravity flattens a whole
        # subtree onto the root card, so the session named in the tooltip is not
        # every chipped child's parent — but it is always the session the
        # comparison was made against, which is what the wording must describe.
        self.assertEqual(
            "this subagent runs on claude-fable-5, not the claude-opus-5 this session is on",
            out["chipTip"],
        )
        self.assertEqual(0, out["blindChips"], "an unread parent produced a wall of chips")
        self.assertTrue(out["more"])
        # Six pills are drawn, and `m0` is the parent's own, so five of the six
        # differ from it.
        self.assertEqual(5, out["manyChips"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_hostile_model_string_cannot_reach_the_dom_as_markup(self) -> None:
        # Model names are vendor text read out of a transcript, a protobuf blob or
        # a SQLite ledger — untrusted on exactly the same footing as a title. This
        # page builds HTML by concatenation, so an unescaped value is markup and an
        # unescaped tooltip is an attribute break. Both the session's model and a
        # child's are new values reaching the DOM, in a body and in a `title=`, so
        # escaping one is not escaping the other.
        checks = (
            self.SPEND_FIXTURE
            + """
const out = {};
const bad = '<img src=x> gpt-5" onmouseover=y';
const probe = h => [h.includes("<img"), h.includes("&lt;img"),
                    h.includes('" onmouseover'), h.includes("&quot; onmouseover")];
const solo = sess("s1", "claude", {model: bad});
out.session = probe(workingCard(board([solo]), solo));
out.sessionBit = probe(authorityBit(solo));
// The unread tooltip interpolates the harness, which is payload text too.
out.harnessTip = probe(authorityBit({harness: bad, model: null}));
// The child's model reaches a body and a tooltip of its own, and the tooltip
// also interpolates the parent's model — three places, one value.
const parent = sess("s2", "claude", {model: "safe-1",
  subagents: [{name: "reviewer", model: bad}]});
out.child = probe(workingCard(board([parent]), parent));
const hostileParent = sess("s3", "claude", {model: bad,
  subagents: [{name: "reviewer", model: "safe-2"}]});
out.childTip = probe(workingCard(board([hostileParent]), hostileParent));
// And the child's own name, which grew a second render site in the same edit.
const named = sess("s4", "claude", {model: null, subagents: [{name: bad, model: null}]});
out.childName = probe(workingCard(board([named]), named));
console.log(JSON.stringify(out));
"""
        )
        out = self._run_page_js(checks)
        clean = [False, True, False, True]
        for where in ("session", "sessionBit", "harnessTip", "child", "childTip", "childName"):
            with self.subTest(where=where):
                self.assertEqual(clean, out[where], "a model string reached the DOM as markup")

    # A board with one harness that keeps a per-request billing ledger and one
    # that keeps none, which is every real board: Copilot is the only harness
    # that fills `consumption`, and the other nine declare it and leave it unset.
    # `window_hours` is 6 rather than the shipped 24 so a clause that hardcoded a
    # window instead of reading the payload cannot pass.
    SPEND_FIXTURE = """
const sess = (sid, harness, over) => Object.assign({
  harness, session: sid, sid, project: "proj", title: sid, last_prompt: "",
  state: "working", state_detail: "running Bash", active: true, last_activity: 990,
  provider: null, model: null, consumption: null, rate_per_min: 10, total: 0,
  done: 0, open: 0, progress_pct: 0, eta_h: null, turn: null, subagents: [],
  tasks: [], spacedock: null}, over || {});
const board = (sessions, over) => Object.assign(
  {generated: 1000, window_hours: 6, rate_window_sec: 600, show_all: false,
   summary: {needs_input: 0, working: 1, rate_per_min: 10, active_sessions: 1,
             open_tasks: 0, progress_pct: 0, total_tasks: 0, total_done: 0},
   harnesses: [
     {key: "copilot", label: "Copilot", discovered: true, error: null, reports_rate: false},
     {key: "claude", label: "Claude", discovered: true, error: null, reports_rate: true}],
   sessions}, over || {});
// Visible text with the tags stripped. The figure also appears inside the
// element's own tooltip, so an assertion against the HTML cannot tell what the
// reader sees from what the hover says.
const seen = h => h.replace(/<[^>]*>/g, "");
const tipOf = h => (h.match(/title="([^"]*)">used /) || [null, null])[1];
"""

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_session_consumption_figure_keeps_its_unit_and_is_never_money(self) -> None:
        # The server publishes this field as text with the unit inside it because
        # AIU is not currency and the rate that would convert it is not on the
        # machine. The page therefore prints the string it was handed: pulling the
        # numeral out and labelling it here is how a subscription unit becomes a
        # dollar figure nobody can check. Three states, and the third is absence:
        # nine harnesses in ten leave the field unset, so unset must not read as a
        # zero, and a measured zero must not read as unset.
        checks = (
            self.SPEND_FIXTURE
            + """
const out = {};
const bit = over => consumptionBit(board([]), sess("s", "copilot", over));
const measured = bit({consumption: "6.43 AIU"});
const zero = bit({consumption: "0.00 AIU"});
out.measured = seen(measured);
out.measuredTip = tipOf(measured);
out.zero = seen(zero);
out.zeroTip = tipOf(zero);
// Unset, on the harness that could have filled it and on one that never does.
out.unsetCopilot = bit({consumption: null});
out.unsetClaude = consumptionBit(board([]), sess("s", "claude"));
// A bare number is refused rather than printed. It is the one shape that would
// put an unlabelled numeral on the page, and AIU, tokens and dollars would then
// be three quantities sharing one axis.
out.bareNumber = bit({consumption: 6.43});
out.emptyString = bit({consumption: ""});
// A figure this page cannot parse is still a figure. It falls through to the
// measured wording rather than being called a zero or dropped.
const odd = bit({consumption: "AIU 6.43"});
out.unparsed = [seen(odd), /measured zero/.test(tipOf(odd))];
// Escaped like every other payload-derived string, in the body and in the
// tooltip both. The rule is about where a value came from rather than about how
// much the page trusts today's producer of it, and this page builds HTML by
// concatenation, so an unescaped figure is markup and an unescaped tooltip is an
// attribute break.
const hostile = bit({consumption: '<img src=x> 1 AIU" onmouseover=y'});
out.hostile = [hostile.includes("<img"), hostile.includes("&lt;img"),
               hostile.includes('" onmouseover'), hostile.includes("&quot; onmouseover")];
// What the reader sees may not read as money at all; the tooltip says "not
// dollars" on purpose, so it is held only to carrying no currency symbol.
out.visibleMoney = [out.measured, out.zero]
  .filter(t => /[$€£]/.test(t) || /cost|spend|dollar/i.test(t));
out.tipSymbols = [out.measuredTip, out.zeroTip].filter(t => /[$€£]/.test(t));
console.log(JSON.stringify(out));
"""
        )
        out = self._run_page_js(checks)
        self.assertEqual("used 6.43 AIU", out["measured"])
        self.assertEqual(
            "6.43 AIU charged to this session over the last 6h, from the per-request"
            " billing ledger Copilot keeps. AI Units — not dollars, and the rate that"
            " would convert them is not on this machine.",
            out["measuredTip"],
            "the figure lost the window it was measured over, or its unit disclaimer",
        )
        # The zero prints, unadorned, the way the rate meter prints a real 0.
        # Suppressing it is what would make it indistinguishable from a harness
        # that keeps no ledger at all.
        self.assertEqual("used 0.00 AIU", out["zero"])
        self.assertEqual(
            "A measured zero, not a missing reading: Copilot kept a billing ledger over"
            " the last 6h and recorded no charge against this session — or none large"
            " enough to show at two decimal places.",
            out["zeroTip"],
            "a measured zero did not say it was measured",
        )
        # No slot, so no dash: absence takes the `used` label with it, and a
        # metadata line with no `used` in it claims nothing about spend.
        self.assertEqual("", out["unsetCopilot"], "an unmeasured session rendered a figure")
        self.assertEqual("", out["unsetClaude"], "a harness with no ledger rendered a figure")
        self.assertEqual("", out["bareNumber"], "an unlabelled numeral reached the page")
        self.assertEqual("", out["emptyString"])
        self.assertEqual(["used AIU 6.43", False], out["unparsed"])
        self.assertEqual(
            [False, True, False, True],
            out["hostile"],
            "the figure reached the DOM as markup, or broke out of its tooltip",
        )
        self.assertEqual([], out["visibleMoney"], "the visible figure read as money")
        self.assertEqual([], out["tipSymbols"], "a currency symbol reached a tooltip")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_row_the_window_does_not_cover_says_so_where_it_can_be_read(self) -> None:
        # The figure is a slice of a ledger summed over `window_hours`, and
        # `?all=1` lists rows whose last event predates that window entirely. Such
        # a row's share is 0.00 arithmetically rather than by measurement, so the
        # bare clause had a month-old session announcing it spent nothing while it
        # meant "nothing in the last 6h". The window therefore has to reach the
        # visible words: a tooltip is where a reader confirms what they already
        # read, not where they find out they read it wrong.
        checks = (
            self.SPEND_FIXTURE
            + """
const out = {};
const bit = over => consumptionBit(board([]), sess("s", "copilot", over));
// The predicate is the server's own `active`, so the page is not re-deriving a
// freshness rule from timestamps the server already compared.
const stale = bit({consumption: "0.00 AIU", active: false, state: "idle"});
out.stale = seen(stale);
out.staleTip = tipOf(stale);
// A row the window does not cover can still hold a charge inside it — a ledger
// row younger than the session's last event. It is real spend and prints, but
// it is the window's share rather than the session's total, and says so.
const partial = bit({consumption: "6.43 AIU", active: false, state: "idle"});
out.partial = seen(partial);
out.partialTip = tipOf(partial);
// A covered row keeps the short clause. The qualification is not a hedge to
// sprinkle everywhere: on an active row the window IS the session's, and four
// words of chrome per card is what that would cost.
out.covered = seen(bit({consumption: "6.43 AIU", active: true}));
out.coveredZero = seen(bit({consumption: "0.00 AIU", active: true}));
// A payload that does not say takes the qualified wording. An absent field is
// not evidence of coverage, and this is the cheaper of the two mistakes.
out.unstated = seen(bit({consumption: "0.00 AIU", active: undefined}));
// The window is the payload's here too, not a literal.
out.wide = seen(consumptionBit(board([], {window_hours: 168}),
                               sess("s", "copilot", {consumption: "0.00 AIU", active: false})));
// Still one span, so the qualifier hovers to the same tooltip rather than
// going quiet halfway through the phrase.
out.spans = (stale.match(/<span/g) || []).length;
console.log(JSON.stringify(out));
"""
        )
        out = self._run_page_js(checks)
        self.assertEqual("used 0.00 AIU in the last 6h", out["stale"])
        self.assertEqual(
            "About the window, not the session: Copilot kept a billing ledger over the"
            " last 6h and this session wrote nothing inside it, so the zero is what the"
            " window holds rather than what the session spent. Whatever it ran up while"
            " it was running is older than the window and is counted nowhere on this page.",
            out["staleTip"],
            "an out-of-window zero claimed to be a reading about the session",
        )
        self.assertEqual("used 6.43 AIU in the last 6h", out["partial"])
        self.assertIn("not everything the session spent", out["partialTip"])
        self.assertEqual("used 6.43 AIU", out["covered"], "a covered row grew a qualifier")
        self.assertEqual("used 0.00 AIU", out["coveredZero"])
        self.assertEqual(
            "used 0.00 AIU in the last 6h",
            out["unstated"],
            "an unstated `active` was read as coverage",
        )
        self.assertEqual("used 0.00 AIU in the last 168h", out["wide"])
        self.assertEqual(1, out["spans"], "the qualifier left the tooltip's span")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_consumption_clause_renders_where_the_live_rows_are(self) -> None:
        # The working card and the needs-input row, beside the borrowed-authority
        # note and in the same metadata line. Not the idle list, which is clipped
        # behind a toggle and carries exactly one number — an age — so a second
        # unit there is the fault calm.js fixed by splitting `signal` in two.
        # And no dangling separator on the nine harnesses that fill nothing.
        checks = (
            self.SPEND_FIXTURE
            + """
const out = {};
const spender = sess("cp1", "copilot", {consumption: "6.43 AIU"});
const blocked = sess("cp2", "copilot", {consumption: "0.00 AIU",
  state: "needs_input", state_detail: "open question", blocked_since: 900});
const stopped = sess("cp3", "copilot", {consumption: "8.94 AIU",
  state: "idle", state_detail: "awaiting your message"});
const plain = sess("cl1", "claude", {provider: null, model: null});
const d = board([spender, blocked, stopped, plain]);
const metaOf = h => seen((h.match(/class="(?:card|need)-meta">(.*?)<\\/div>/) || [null, ""])[1]);
out.working = metaOf(workingCard(d, spender));
out.needs = metaOf(needRow(d, blocked, 1));
out.idle = seen(idleRow(d, stopped));
// A row whose harness keeps no ledger ends at its session id: the separator
// belongs to the helper, so nothing renders a trailing " · ".
out.plain = metaOf(workingCard(d, plain));
// The clause sits with the authority note rather than replacing it — a Pi
// session on Copilot quota would carry both facts, and they are two facts.
const borrowed = sess("pi1", "pi", {provider: "github-copilot", model: "gpt-5",
  consumption: "1.20 AIU"});
out.both = metaOf(workingCard(d, borrowed));
console.log(JSON.stringify(out));
"""
        )
        out = self._run_page_js(checks)
        # Copilot fills `consumption` and, on this fixture, no model — so the same
        # line carries a printed figure and an unread dash, which is the pairing
        # that makes the two absences readable side by side.
        # Four sessions on the label `proj`, three of them live, so these two
        # rows also carry the shared-label marker. Pinned in the same string
        # rather than dodged with a per-row label, because a board of four
        # sessions in one project is what this fixture is.
        self.assertEqual("proj 3 live · cp1 · model — · used 6.43 AIU", out["working"])
        # The needs row leads with the harness badge, whose tooltip text survives
        # the tag strip; the clause still lands at the end of the same line.
        self.assertEqual("Copilotproj 3 live · cp2 · model — · used 0.00 AIU", out["needs"])
        # A harness with no ledger says nothing about spend and still declares the
        # model slot: the consumption clause vanishes, the model dash does not.
        # The two absences are different — no `used` claims nothing, whereas every
        # session does run on some model.
        self.assertEqual(
            "proj 3 live · cl1 · model —", out["plain"], "a session with no ledger drew a stray dot"
        )
        self.assertEqual("proj · pi1 · via Copilot · gpt-5 · used 1.20 AIU", out["both"])
        self.assertNotIn("AIU", out["idle"], "the idle drawer grew a second unit")
        self.assertNotIn("used", out["idle"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_no_board_level_figure_is_summed_out_of_one_harnesss_units(self) -> None:
        # There is no cross-harness AIU: nine harnesses report none, and GitHub's
        # conversion rate is not on the machine. A hero numeral or a footer over
        # this field would repeat the output-rate tile's own fault — one harness's
        # measurement printed as the board's — so the per-session figures are the
        # only place the unit appears, and the harness total belongs to the usage
        # tile, which is the one surface that reads the same ledger.
        checks = (
            self.SPEND_FIXTURE
            + """
const out = {};
const d = board([sess("cp1", "copilot", {consumption: "6.43 AIU"}),
                 sess("cp2", "copilot", {consumption: "8.94 AIU"})],
                {summary: {needs_input: 0, working: 2, rate_per_min: 20,
                           active_sessions: 2, open_tasks: 0, progress_pct: 0,
                           total_tasks: 0, total_done: 0}});
__els.app = {innerHTML: "", className: ""};
render(d);
const html = __els.app.innerHTML;
out.perSession = ["used 6.43 AIU", "used 8.94 AIU"].map(t => html.includes(t));
// The sum, at both the precision the field prints and the one a naive add gives.
out.summed = ["15.37", "15.370", "15.4"].filter(t => html.includes(t));
// Nothing above the session rows carries the unit: the hero tiles and the
// subnote are everything the page states about the board as a whole.
const hero = html.slice(html.indexOf('class="hero"'), html.indexOf('class="stack"'));
out.heroUnits = /AIU/.test(hero);
console.log(JSON.stringify(out));
"""
        )
        out = self._run_page_js(checks)
        self.assertEqual([True, True], out["perSession"], "a session lost its own figure")
        self.assertEqual([], out["summed"], "the page summed one harness's units into a total")
        self.assertFalse(out["heroUnits"], "an AIU figure reached a board-level tile")

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

    # The per-model sub-limits. Anthropic's usage response carries them in
    # `limits[]` as the elements whose `kind` is `weekly_scoped`, and quota.py
    # shapes them onto the Claude entry as `models`: a list ordered by label,
    # each row a percentage that may carry no reset at all — the recorded
    # response carried none. Every test below executes usageEntry() and reads
    # the row it produced, because the failure worth catching here is not a
    # missing row but a row that renders and says the wrong thing.
    # `cells` takes the entry apart one `.u-wrow` at a time so an assertion is
    # always about a named row: searching the whole entry for "↺ —" cannot tell
    # which row lost its countdown, and the harness icon is a percent-encoded
    # data URI, so a bare search over the entry matches almost anything.
    _MODELS = r"""
const cells = html => html.split('<div class="u-wrow">').slice(1).map(r => ({
  lab: (r.match(/<span class="u-wlab"[^>]*>([^<]*)</) || [])[1],
  ltitle: (r.match(/<span class="u-wlab" title="([^"]*)"/) || [])[1] || null,
  pct: (r.match(/<span class="u-pct"[^>]*>([^<]*)</) || [])[1] || null,
  reset: (r.match(/<span class="u-reset"[^>]*>([^<]*)</) || [])[1] || null,
  rtitle: (r.match(/<span class="u-reset" title="([^"]*)"/) || [])[1] || null,
  burn: (r.match(/<span class="u-burn[^>]*>([^<]*)</) || [])[1] || null}));
const labWidth = html => (html.match(/--ulab:(\d+)px/) || [null, null])[1];
const claude = models => ({harness: 'claude', state: 'ok', asOf: 1700000000,
  fiveH: {pct: 41, reset: '14:20', resetAt: nowSec() + 3600},
  week: {pct: 62, reset: 'Thu 02:00', resetAt: nowSec() + 86400}, models});
"""

    def test_the_per_model_limits_get_their_own_rows_and_get_them_by_default(self) -> None:
        # A3's outcome is "switch model instead of stopping", and choosing between
        # two models means seeing both at once, before the tighter of them blocks
        # you. So these are rows in the band rather than a disclosure, they sit
        # under the weekly window they subdivide rather than replacing it, and
        # they are on by DEFAULT: a comparison nobody has switched on arrives
        # after the fact, and so does a row that only appears once its own model
        # becomes the binding constraint.
        # quota.py owns row order — it sorts on the one field of a row that does
        # not tick — and a second opinion here is how two polls come to disagree
        # about which row is where. So the labels are fed in an order NEITHER
        # direction of a sort produces: two of them would have caught an ascending
        # sort and passed a descending one, which is a mutation that survived this
        # test the first time it was swept.
        rendered = self._run_page_js(
            self._MODELS + "const e = claude([{label:'Sonnet', pct:31},"
            " {label:'Fable', pct:7},"
            " {label:'Opus', pct:96, reset:'Thu 02:00', resetAt: nowSec() + 86400}]);"
            "console.log(JSON.stringify({cfg: usageCfg.models, cells: cells(usageEntry(e)),"
            " html: usageEntry(e)}));"
        )
        self.assertTrue(rendered["cfg"], "the per-model rows must default to shown")
        cells = rendered["cells"]
        self.assertEqual(["5h", "wk", "Sonnet", "Fable", "Opus"], [c["lab"] for c in cells])
        # Each is a gauge in its own right, with its own percentage and bar.
        self.assertEqual(["41%", "62%", "31%", "7%", "96%"], [c["pct"] for c in cells])
        self.assertEqual(5, rendered["html"].count("cm-fill"))
        # A model name is longer than "wk" and can be truncated by its column, so
        # every model row carries the whole of its label in a tooltip. The window
        # labels are two characters and carry none, because a tooltip repeating
        # visible text is noise the reader learns to ignore.
        self.assertEqual([None, None, "Sonnet", "Fable", "Opus"], [c["ltitle"] for c in cells])

    def test_a_per_model_row_with_no_reset_reads_as_unknown(self) -> None:
        # The measured case: the recorded response carried no `resets_at` on its
        # scoped element at all, so a per-model row can be a percentage with no
        # countdown behind it. Both halves of the column have to say so. Lending
        # it the weekly countdown would put a figure on the row that this limit
        # never published, and a blank column reads as a row still loading.
        rendered = self._run_page_js(
            self._MODELS + "const e = claude([{label:'Fable', pct:88}]);"
            "console.log(JSON.stringify({cells: cells(usageEntry(e))}));"
        )
        week, model = rendered["cells"][1], rendered["cells"][2]
        self.assertEqual("↺ —", model["reset"])
        self.assertEqual("resets at an unknown time", model["rtitle"])
        # The percentage it does have is still published: no countdown is not no
        # figure.
        self.assertEqual("88%", model["pct"])
        # The weekly row keeps its own countdown, which is what proves the model
        # row did not take it: an entry-wide search would match this row.
        self.assertEqual("↺ 1d 0h", week["reset"])
        self.assertEqual("resets Thu 02:00", week["rtitle"])

    def test_the_label_column_is_measured_and_capped_rather_than_sized_by_eye(self) -> None:
        # The column is sized per entry from the longest label that entry
        # actually draws, so a Codex, Copilot or Cursor tile — which never
        # receives a model name — keeps the width it had and the full width of
        # its bar. Widths are asserted as literal pixels rather than against
        # U_LAB_ADVANCE_PX and U_LAB_MAX_CHARS: an expectation sized off the
        # constants it is checking moves with them, and holds at any cap.
        # 7.11px per character is the measured advance (SF Mono at --fs-2xs,
        # 1266/2048 em, the widest face in the --mono stack), so five characters
        # are 36px, eight are 57px and ten are 72px. The eight-character case is
        # there to pin the advance itself: at 7.2px per character five and ten
        # characters both still round to 36 and 72.
        rendered = self._run_page_js(
            self._MODELS + "const long = 'M'.repeat(40);"
            "console.log(JSON.stringify(Object.fromEntries(["
            " ['none',    labWidth(usageEntry(claude(undefined)))],"
            " ['four',    labWidth(usageEntry(claude([{label:'Opus', pct:5}])))],"
            " ['five',    labWidth(usageEntry(claude([{label:'Fable', pct:5}])))],"
            " ['eight',   labWidth(usageEntry(claude([{label:'Opus 4.5', pct:5}])))],"
            " ['ten',     labWidth(usageEntry(claude([{label:'Sonnet 4.5', pct:5}])))],"
            " ['eleven',  labWidth(usageEntry(claude([{label:'Claude Opus', pct:5}])))],"
            " ['forty',   labWidth(usageEntry(claude([{label: long, pct:5}])))],"
            " ['undrawn', labWidth(usageEntry(claude([{label: long, pct: null}])))],"
            " ['hidden',  (usageCfg.models = false,"
            "              labWidth(usageEntry(claude([{label: long, pct:5}]))))]])));"
        )
        # No model rows, no property: the stylesheet owns the width the window
        # labels need, and an entry restating it there would make that width
        # unchangeable from the one place it belongs.
        self.assertIsNone(rendered["none"])
        # Four characters are 29px, which is under the floor `used` established,
        # so the property still does not appear.
        self.assertIsNone(rendered["four"])
        self.assertEqual("36", rendered["five"])
        self.assertEqual("57", rendered["eight"])
        self.assertEqual("72", rendered["ten"])
        # Past ten the tile runs out, not the name: eleven characters and forty
        # get the same column and truncate into it.
        self.assertEqual("72", rendered["eleven"])
        self.assertEqual("72", rendered["forty"])
        # A row that was not drawn must not widen the column it was going to sit
        # in — neither one the payload gave no percentage nor one the reader
        # switched off.
        self.assertIsNone(rendered["undrawn"])
        self.assertIsNone(rendered["hidden"])

    def test_a_per_model_row_without_a_usable_label_is_not_rendered_at_all(self) -> None:
        # `scope.model.id` arrived null in the capture, so the display name is the
        # whole of a row's identity. quota.py drops a row that has none, and the
        # page must not resurrect one under a placeholder or a coerced value: an
        # unlabelled bar sitting under the weekly bar reads as a second weekly
        # figure disagreeing with the first, and "42" or "null" as a model name is
        # a wrong label on a real percentage.
        rendered = self._run_page_js(
            self._MODELS + "const e = claude([{label:null, pct:99}, {label:'', pct:98},"
            " {label:42, pct:97}, {label:{}, pct:96}, {label:'Fable', pct:88}]);"
            "console.log(JSON.stringify({cells: cells(usageEntry(e)),"
            " width: labWidth(usageEntry(e))}));"
        )
        self.assertEqual(["5h", "wk", "Fable"], [c["lab"] for c in rendered["cells"]])
        # Their percentages are gone with them, and asserted row by row: the
        # harness icon is a percent-encoded data URI, so `assertNotIn("97%")`
        # over the whole entry matches the icon path and passes for free.
        self.assertEqual(["41%", "62%", "88%"], [c["pct"] for c in rendered["cells"]])
        # Nor may a dropped row size the column: `Fable` is five characters.
        self.assertEqual("36", rendered["width"])

    def test_a_hostile_model_label_is_escaped_and_kept_whole_in_its_tooltip(self) -> None:
        # The label is vendor text on its way into markup the page builds by
        # concatenation. quota.py bounds it to 40 characters and collapses control
        # characters, and says plainly that markup passes through verbatim — so
        # the escape is this side's job and nothing else does it.
        rendered = self._run_page_js(
            self._MODELS + "const label = '<img src=x onerror=alert(1)>';"
            "const e = claude([{label, pct:88}]);"
            "console.log(JSON.stringify({cells: cells(usageEntry(e)),"
            " html: usageEntry(e)}));"
        )
        self.assertNotIn("<img", rendered["html"])
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", rendered["html"])
        # The whole label, not a leading fragment of it: a column this narrow
        # truncates on screen, and the tooltip is where the rest of the name
        # lives. Asserted as an equality, because assertIn on a fragment passes
        # on a fragment.
        self.assertEqual("&lt;img src=x onerror=alert(1)&gt;", rendered["cells"][2]["ltitle"])
        # The truncation itself is the stylesheet's half of this, and the two
        # files can only agree by name: the script writes `--ulab` on the entry
        # and the row rule reads it, and without the clip a long label escapes its
        # cell and collides with the bar instead of ellipsing. The floor is
        # declared here rather than passed as a `var()` fallback, so the width the
        # window labels need is a value in the stylesheet that can be found and
        # changed rather than an argument buried in a shorthand.
        self.assertIn("--ulab:30px}", STYLES)
        self.assertIn("grid-template-columns:var(--ulab) ", STYLES)
        rule = re.search(r"\.u-wlab\{([^}]*)\}", STYLES)
        assert rule is not None
        for declaration in ("overflow:hidden", "text-overflow:ellipsis", "white-space:nowrap"):
            self.assertIn(declaration, rule.group(1))

    def test_a_per_model_row_is_never_given_a_burn_projection(self) -> None:
        # The decision, and the governing principle of this band decides it. A
        # per-model row's only identity is a vendor display name that two rows can
        # share, so one buffer would hold two series and publish the first row's
        # slope on the second. And the recorded response gave the scoped element
        # no reset instant, which is exactly the input burnPush() needs to notice
        # a limit rolling: a fall is the only other sign, and a limit that rolls
        # and then climbs past where the old one stood never falls. The fit would
        # span two allowances and read SLOWER than the truth, pushing its wall
        # out — the reassuring direction, on a series nobody has watched move.
        # So nothing is sampled and nothing is fitted. With the projection on the
        # row SAYS that, rather than going quiet: a silent model row beneath a
        # weekly row reading "~4%/h · wall 2h 10m" is read as a limit that is not
        # filling, and an absence that reads as good news is the failure this
        # whole band was rebuilt to avoid.
        rendered = self._run_page_js(
            self._MODELS + "const e = claude([{label:'Fable', pct:88},"
            " {label:'Sonnet 4.5', pct:12}]);"
            "const off = usageEntry(e);"
            "usageCfg.burn = true;"
            # Through usageBody(), which is the one sampling point, so the window
            # buffers really do fill while the model rows really do not.
            "usageBody({usage: [e]});"
            "usageBody({usage: [Object.assign({}, e, {asOf: 1700000300})]});"
            "console.log(JSON.stringify({slots: BURN_SLOTS, keys: [...burnHistory.keys()],"
            " off: cells(off).map(c => c.burn), on: cells(usageEntry(e)).map(c => c.burn)}));"
        )
        # The buffers the payload filled, and they are the window slots only. A
        # model key here would mean a series keyed on a display name.
        self.assertEqual(["fiveH", "week", "month"], rendered["slots"])
        self.assertEqual(["claude:fiveH", "claude:week"], sorted(rendered["keys"]))
        # Off is off for every row, model rows included: no dimmed line, no
        # reserved space.
        self.assertEqual([None, None, None, None], rendered["off"])
        five, week, fable, sonnet = rendered["on"]
        self.assertEqual("warming up · 2 of 3", five)
        self.assertEqual("warming up · 2 of 3", week)
        # Not a rate, not a ceiling, not a warm-up that will never finish — the
        # third answer, and it is stated rather than left as a gap.
        for reading in (fable, sonnet):
            self.assertEqual("not projected", reading)
            self.assertNotIn("%/h", reading)
            self.assertNotIn("warming", reading)

    def test_the_unprojected_model_row_says_why_in_its_own_words(self) -> None:
        # The word alone reads as a Cargento fault, exactly as bare "stale" did.
        # The hover has to name the two reasons and point at the row that does
        # carry a rate, or the reader is left to assume the figure was simply
        # dropped.
        rendered = self._run_page_js(
            self._MODELS + "usageCfg.burn = true;"
            "const e = claude([{label:'Fable', pct:88}]);"
            "const row = usageEntry(e).split('<div class=\"u-wrow\">')[3];"
            "console.log(JSON.stringify({title:"
            ' (row.match(/<span class="u-burn" title="([^"]*)"/) || [])[1] || null}));'
        )
        title = rendered["title"]
        self.assertIsNotNone(title, "the model row carried no burn tooltip at all")
        self.assertIn("display name", title)
        self.assertIn("no reset instant", title)
        self.assertIn("read slower than the truth", title)
        self.assertIn("weekly", title)

    def test_the_unprojected_tooltip_does_not_claim_a_parent_row_that_is_absent(self) -> None:
        # The tooltip pointed the reader at "the weekly window these subdivide has
        # its own row in this tile" unconditionally. Two states make that false and
        # the reader can see both: the weekly stat switched off, and an entry that
        # carries fiveH and models but no week at all, which the fetch permits
        # because it only bails when BOTH named windows are missing. Claiming a row
        # that is not on screen is the same defect as claiming a measurement that
        # was not taken, one layer down.
        for setup, case in (
            ("usageCfg.week = false;", "weekly switched off"),
            ("", "entry carries no week"),
        ):
            entry = (
                "const e = claude([{label:'Fable', pct:88}]);"
                if setup
                else "const e = claude([{label:'Fable', pct:88}]); delete e.week;"
            )
            rendered = self._run_page_js(
                self._MODELS
                + "usageCfg.burn = true;"
                + setup
                + entry
                + "const rows = usageEntry(e).split('<div class=\"u-wrow\">');"
                "console.log(JSON.stringify({title:"
                ' (rows[rows.length - 1].match(/<span class="u-burn" title="([^"]*)"/)'
                " || [])[1] || null}));"
            )
            title = rendered["title"]
            self.assertIsNotNone(title, case)
            self.assertIn("not on screen", title, case)
            self.assertNotIn("has its own row in this tile", title, case)

        # And the claim survives where it is true, so the fix is not "never say it".
        rendered = self._run_page_js(
            self._MODELS + "usageCfg.burn = true;"
            "const e = claude([{label:'Fable', pct:88}]);"
            "const rows = usageEntry(e).split('<div class=\"u-wrow\">');"
            "console.log(JSON.stringify({title:"
            ' (rows[rows.length - 1].match(/<span class="u-burn" title="([^"]*)"/)'
            " || [])[1] || null}));"
        )
        self.assertIn("has its own row in this tile", rendered["title"])
        self.assertNotIn("not on screen", rendered["title"])

    def test_the_per_model_rows_have_a_switch_and_the_last_stat_lock_covers_it(self) -> None:
        # A row with no entry in the popover can never be turned back on once
        # off, and the last shown stat must refuse to be turned off at all: a band
        # with every stat hidden is indistinguishable from a broken one.
        rendered = self._run_page_js(
            self._MODELS + "const out = {label: USAGE_STATS.find(s => s[0] === 'models')[1]};"
            # Everything else off, one call at a time, exactly as a reader clicks.
            "for(const k of ['fiveH', 'week', 'month']) usageAction('ustat', k);"
            "out.only = USAGE_STATS.filter(([k]) => usageCfg[k]).map(([k]) => k);"
            "usageCfgOpen = true;"
            'out.locked = /data-arg="models"[^>]*aria-disabled="true"/.test(usageCfgPop());'
            "usageAction('ustat', 'models');"
            "out.stillOn = usageCfg.models;"
            # And the rows are the only thing left in the band, which is the state
            # the lock exists to keep reachable.
            "out.cells = cells(usageEntry(claude([{label:'Fable', pct:88}])));"
            "console.log(JSON.stringify(out));"
        )
        # Named as limits rather than as models: the row is a quota, and "models"
        # alone would read as a list of what the harness is running.
        self.assertEqual("per-model limits", rendered["label"])
        self.assertEqual(["models"], rendered["only"])
        self.assertTrue(rendered["locked"], "the last shown stat was offered as switchable")
        self.assertTrue(rendered["stillOn"], "the last shown stat was switched off")
        self.assertEqual(["Fable"], [c["lab"] for c in rendered["cells"]])

    def test_the_disclosure_banner_renders_in_flow_on_both_surfaces(self) -> None:
        # Two surfaces assemble the banner separately — calm from `calmLedger`,
        # regular from `render`'s innerHTML — and only the byte pins would
        # notice a lost call site, with a digest mismatch that invites
        # re-pinning rather than investigating. `usageBandCalm`'s sibling test
        # above exists because a row rendered in neither surface once shipped.
        rendered = self._run_page_js(
            "const d = {usage: [{harness: 'claude', state: 'ok'}], usage_fetch: true};"
            "const before = {calm: usageBanner(d), regular: usageBanner(d, true)};"
            "usageAction('umodal', 'on');"
            "const after = {calm: usageBanner(d), regular: usageBanner(d, true)};"
            "console.log(JSON.stringify({before, after, on: usageEnabled,"
            " seen: usageModalSeen}));"
        )
        for view in ("calm", "regular"):
            with self.subTest(view=view):
                html = rendered["before"][view]
                # The outer element exactly once. Counted on `role="region"`,
                # not on the `u-banner` class prefix, which the four inner
                # element classes share.
                self.assertEqual(1, html.count('role="region"'))
                self.assertIn("Keep usage on", html)
                self.assertIn("Turn it off", html)
                # In flow, not a gate. `aria-modal` would announce it as one.
                self.assertNotIn("aria-modal", html)
                self.assertNotIn("u-overlay", html)
                # Answered once, gone from both — the consent is the state, not
                # the markup.
                self.assertEqual("", rendered["after"][view])
        self.assertTrue(rendered["seen"])
        # "Keep usage on" asserts the master switch rather than assuming it:
        # `configure` is reachable while the banner is up, so a reader can turn
        # usage off there first and then answer the banner.
        self.assertTrue(rendered["on"])
        # Only the regular placement carries its own border: `.wrap` owns gaps
        # rather than separators, and calm's row sits inside the frame's rules.
        self.assertIn("standalone", rendered["before"]["regular"])
        self.assertNotIn("standalone", rendered["before"]["calm"])

    def test_the_banner_reaches_the_session_view_too(self) -> None:
        # The third surface, and the one that caught a real collision: #131's
        # session branch called `usageModal`, which this branch renames, and the
        # two merged without a textual conflict. Driven through `render()`
        # rather than by calling the function, because "the call site still
        # exists and still resolves" is the whole assertion.
        rendered = self._run_page_js(
            "__els.app = {innerHTML: '', className: '', querySelectorAll: () => []};"
            "const d = {generated: 1000, window_hours: 24, show_all: false,"
            " rate_window_sec: 600, harnesses: [], sessions: [],"
            " summary: {needs_input: 0, working: 0, rate_per_min: 0, active_sessions: 0,"
            "  open_tasks: 0, progress_pct: 0, total_tasks: 0, total_done: 0},"
            " usage: [{harness: 'claude', state: 'ok'}], usage_fetch: true};"
            "setDisplayMode('session');"
            "render(d);"
            "console.log(JSON.stringify({html: __els.app.innerHTML,"
            " cls: __els.app.className}));",
            prelude="const __store = {};\nconst localStorage = {"
            "getItem: k => (k in __store ? __store[k] : null),"
            "setItem: (k, v) => { __store[k] = String(v); }};\nconst navigator = {};",
        )
        self.assertEqual("wrap session", rendered["cls"])
        self.assertEqual(1, rendered["html"].count('role="region"'))
        self.assertIn("standalone", rendered["html"])

    def test_answering_the_banner_after_turning_usage_off_leaves_it_on(self) -> None:
        # The regression the in-flow placement introduced. Under the modal the
        # board was covered, so `configure` was unreachable until the
        # disclosure was answered and the two controls could not disagree.
        # Falsifying edit: drop `usageEnabled = true` from the `umodal` else
        # branch — this reads False, and the reader who clicked "Keep usage on"
        # gets no usage.
        rendered = self._run_page_js(
            "usageAction('uon');"  # the master switch, off
            "const off = usageEnabled;"
            "usageAction('umodal', 'on');"  # then "Keep usage on"
            "console.log(JSON.stringify({off, on: usageEnabled,"
            " stored: __store['cargento.usageEnabled']}));",
            prelude="const __store = {};\nconst localStorage = {"
            "getItem: k => (k in __store ? __store[k] : null),"
            "setItem: (k, v) => { __store[k] = String(v); },"
            "removeItem: k => { delete __store[k]; }};\nconst navigator = {};",
        )
        self.assertFalse(rendered["off"])
        self.assertTrue(rendered["on"])
        self.assertEqual("1", rendered["stored"])

    def test_both_bands_render_the_per_model_rows(self) -> None:
        # Two surfaces consume this list — the regular view's card and the calm
        # view's strip — and they are assembled separately. Copilot's `used` row
        # existed and rendered in neither for exactly this reason.
        rendered = self._run_page_js(
            self._MODELS + "const d = {usage: [claude([{label:'Fable', pct:88}])]};"
            "console.log(JSON.stringify({calm: usageBandCalm(d),"
            " regular: usageSectionRegular(d)}));"
        )
        for view in ("calm", "regular"):
            with self.subTest(view=view):
                html = rendered[view]
                self.assertIn('<span class="u-wlab" title="Fable">Fable</span>', html)
                self.assertIn("88%", html)
                self.assertIn("--ulab:36px", html)

    def test_a_stat_added_after_a_reader_last_saved_keeps_its_own_default(self) -> None:
        # The saved config is adopted key by key, and only for the keys it
        # carries. Rewriting every key from the stored object was the old
        # behaviour, and under it every default-on stat added from here on would
        # ship switched off for exactly the readers who had once opened
        # `configure` — silently, and looking like the feature never landed.
        def prelude(cfg: dict[str, bool]) -> str:
            store = json.dumps({"cargento.usageCfg": json.dumps(cfg)})
            return (
                f"let __store = {store};\nconst localStorage = {{"
                "getItem(k){ return Object.prototype.hasOwnProperty.call(__store, k)"
                " ? __store[k] : null; }, setItem(k, v){ __store[k] = String(v); }};\n"
            )

        stale = {
            "fiveH": True,
            "week": True,
            "month": True,
            "burn": False,
            "today": False,
            "cost": False,
        }
        rendered = self._run_page_js(
            "console.log(JSON.stringify(usageCfg));", prelude=prelude(stale)
        )
        self.assertTrue(rendered["models"], "a key the saved config never had was read as off")
        # Everything the reader did choose is still honoured, so this is not a
        # loader that ignores storage.
        self.assertFalse(rendered["burn"])
        self.assertTrue(rendered["week"])
        # And an explicit choice about the new stat outranks its default.
        chosen = self._run_page_js(
            "console.log(JSON.stringify(usageCfg));",
            prelude=prelude({**stale, "models": False}),
        )
        self.assertFalse(chosen["models"], "an explicit off was overridden by the default")

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
    def test_the_harness_strip_says_which_rows_cannot_report_a_gate(self) -> None:
        # The strip is where a reader asks what these rows cover, so it is where
        # the answer belongs. Four states, and the fourth is the one that matters:
        # an absent flag must claim nothing, because "this harness cannot report a
        # gate" is a much louder sentence than a missing field earns -- it tells
        # the reader the gap is by design, which is how a bug report does not get
        # filed. Same discipline harnessRateKnown() applies to its fallback.
        checks = """
const row = (over) => Object.assign(
  {key:"codex", label:"Codex", discovered:true, error:null,
   reports_needs_input:false}, over || {});
console.log(JSON.stringify({
  blind:   harnessStrip([row()]),
  able:    harnessStrip([row({key:"claude", label:"Claude",
                              reports_needs_input:true})]),
  broken:  harnessStrip([row({error:"OSError: nope"})]),
  absent:  harnessStrip([row({discovered:false})]),
  noField: harnessStrip([{key:"codex", label:"Codex", discovered:true, error:null}])}));
"""
        out = self._run_page_js(checks)

        self.assertIn("no gate detection", out["blind"])
        self.assertNotIn("no gate detection", out["able"])
        # A collector that raised outranks it: whatever the store might have said
        # was never read, so the harness's own capability is not the fact to lead
        # with. Same precedence the strip already gives `error` over `no data`.
        self.assertIn("collector error", out["broken"])
        self.assertNotIn("no gate detection", out["broken"])
        self.assertIn("no data", out["absent"])
        self.assertNotIn("no gate detection", out["noField"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_zero_needs_you_tile_says_how_much_of_the_board_it_speaks_for(self) -> None:
        # "Needs you 0 · Nothing is waiting on you." over a board of ten harnesses
        # where one can detect a gate is the same false reassurance cargento#116
        # was filed for, and waitingOnYou() only fixed the half of it that the ask
        # lane caused. Nine rows are silent about gates by construction, so the
        # zero has to say what it covers. Scoped to the empty case deliberately:
        # a non-zero tile draws its per-harness breakdown, which shows the reader
        # which rows the number came from.
        checks = """
const row = (key, label, over) => Object.assign(
  {key, label, discovered:true, error:null, reports_needs_input:false}, over || {});
const out = {};
out.mixed = countTile("Needs you", gateEmpty({harnesses:[
  row("claude", "Claude", {reports_needs_input:true}),
  row("codex", "Codex"), row("copilot", "Copilot")]}), [], true);
out.claudeOnly = countTile("Needs you", gateEmpty({harnesses:[
  row("claude", "Claude", {reports_needs_input:true})]}), [], true);
out.noField = countTile("Needs you", gateEmpty({harnesses:[
  {key:"codex", label:"Codex", discovered:true, error:null}]}), [], true);
console.log(JSON.stringify(out));
"""
        out = self._run_page_js(checks)

        # The claim is scoped to what could not tell, and it names them, so the
        # sentence is a quantity rather than a hedge.
        self.assertIn("Codex", out["mixed"])
        self.assertIn("Copilot", out["mixed"])
        self.assertNotIn("Nothing is waiting on you.", out["mixed"])
        # Every discovered row can report, so the old sentence is true as written.
        self.assertIn("Nothing is waiting on you.", out["claudeOnly"])
        # And a payload that never sent the flag claims nothing either way.
        self.assertIn("Nothing is waiting on you.", out["noField"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_zero_tile_counts_a_harness_it_could_not_read_at_all(self) -> None:
        # The first version of this named the blind rows and silently dropped the
        # ones whose collector raised -- which are the rows that could have told
        # you, so the tooltip read as a complete enumeration while omitting the
        # load-bearing gap. `rateFloor` settled this shape already: an unread
        # harness makes the figure a floor and says so.
        checks = """
const row = (key, label, over) => Object.assign(
  {key, label, discovered:true, error:null, reports_needs_input:false}, over || {});
const out = {};
// Every row can report, but one of them could not be read this refresh.
out.unreadOnly = gateEmpty({harnesses:[
  row("claude", "Claude", {reports_needs_input:true, error:"PermissionError: nope"}),
  row("codex", "Codex", {reports_needs_input:true})]});
// Both kinds at once.
out.both = gateEmpty({harnesses:[
  row("claude", "Claude", {reports_needs_input:true, error:"OSError: nope"}),
  row("copilot", "Copilot")]});
// Neither: the old sentence is true as written.
out.clean = gateEmpty({harnesses:[
  row("claude", "Claude", {reports_needs_input:true}),
  row("codex", "Codex", {reports_needs_input:true})]});
console.log(JSON.stringify(out));
"""
        out = self._run_page_js(checks)

        # A row nobody could read is not an all-clear, even when every harness
        # present is gate-capable.
        self.assertNotEqual("Nothing is waiting on you.", out["unreadOnly"]["empty"])
        self.assertIn("Claude", out["unreadOnly"]["emptyTip"])
        # And when both kinds are present the tooltip names both, so the reader
        # is not told a partial list is the whole of it.
        self.assertIn("Copilot", out["both"]["emptyTip"])
        self.assertIn("Claude", out["both"]["emptyTip"])
        # Nothing to disclose, so nothing is claimed.
        self.assertEqual("Nothing is waiting on you.", out["clean"]["empty"])
        self.assertNotIn("emptyTip", out["clean"])

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
    def test_the_card_column_says_when_two_live_sessions_share_a_project_label(self) -> None:
        # The card view has no grouping to lean on, so without a marker the two
        # agents about to overwrite each other read as two unrelated cards. The
        # gate row carries it for the same reason it counts as live: answering
        # that gate is the keystroke that lets one session write over the other.
        checks = """
const base = {harness: "claude", session: "aaa", sid: "aaa", project: "repo/proj",
  title: "t", last_prompt: "", state: "working", state_detail: "running Bash",
  active: true, last_activity: 990, rate_per_min: 100, total: 0, done: 0, open: 0,
  progress_pct: 0, eta_h: null, turn: null, subagents: [], tasks: [], spacedock: null};
const s = o => Object.assign({}, base, o);
const mate = s({sid: "bbb", session: "bbb", harness: "codex", rate_per_min: 3000});
const gate = s({sid: "ccc", session: "ccc", state: "needs_input",
                state_detail: "permission needed", blocked_since: 900});
const solo = s({sid: "ddd", session: "ddd", project: "repo/solo"});
const dead = s({sid: "eee", session: "eee", state: "idle", active: false,
                last_activity: 400});
const strip = [
  {key: "claude", label: "Claude", discovered: true, error: null, reports_rate: true},
  {key: "codex", label: "Codex", discovered: true, error: null, reports_rate: true}];
const d = {generated: 1000, rate_window_sec: 600, harnesses: strip,
           summary: {rate_per_min: 0}, sessions: [base, mate, gate, solo, dead]};
const has = h => h.includes('class="dupmark"');
const out = {};
out.card = has(workingCard(d, base));
out.mate = has(workingCard(d, mate));
out.solo = has(workingCard(d, solo));
out.gate = has(needRow(d, gate, 1, null));
// An idle row on the same label is not one of the sessions in the collision:
// it has stopped, so it is not about to write anything.
out.dead = has(idleRow(d, dead));
// The marker sits with the project label it is about, not in the pill row —
// the card's pills claim things about burn, and this claims nothing about burn.
out.headrow = workingCard(d, base).split('class="card-title"')[0];
out.pillTip = (workingCard(d, mate).match(/class="pill" title="([^"]*)"/) || [])[1];
console.log(JSON.stringify(out));
"""
        out = self._run_page_js(checks)
        self.assertEqual(
            [True, True, False, True, False],
            [out["card"], out["mate"], out["solo"], out["gate"], out["dead"]],
            "the shared-label marker is on the wrong set of rows",
        )
        self.assertNotIn("dupmark", out["headrow"], "the marker landed in the pill row")
        self.assertTrue(
            (out["pillTip"] or "").startswith("3,000 tok/min, the highest of the"),
            f"the fastest pill's tooltip is no longer the card's first pill: {out['pillTip']}",
        )

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
    def test_browser_notifications_cover_an_arriving_ask_where_the_server_cannot(self) -> None:
        # The same split as a gate (design decision D-3), keyed on the ask id
        # rather than on a transition: a question has no prior state, and it
        # leaves the payload for good once answered, withdrawn or expired.
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
const ask = (id, over) => Object.assign({
  id, harness:"claude", session_id:"12345678-90ab-cdef-1234-567890abcdef",
  project:"repo/proj", question:"Ship it?", options:["yes", "no"], age_sec:1
}, over || {});
/* A registry row, because a label is only ever resolved through one: with
   harnesses:[] every case below would read "An agent" and prove nothing. */
const registry = [{key:"claude", label:"Claude", discovered:true, error:null}];
const payload = (asks, native, sessions) => ({
  generated:1000, window_hours:24, show_all:false, native_notify:native,
  harnesses:registry, sessions:sessions || [], ask:true, asks,
  summary:{needs_input:0, working:0, rate_per_min:0, active_sessions:1,
           open_tasks:0, progress_pct:0, total_tasks:0, total_done:0}
});
const reset = perm => {
  __notifications = []; __notifyPermission = perm;
  notifyState = new Map(); notifyPrimed = false; notifiedAsks = new Set();
};
const out = {};

// The server already popped natively: the page must stay silent.
reset("granted");
render(payload([ask("a1")], "osascript"));
out.nativeOwnsIt = __notifications.length;

// No native backend (Linux/Windows today): the page notifies, and it notifies
// on the FIRST payload it sees. An ask id is single-use and nothing ever
// re-registers it, so there is no repeat for priming to protect against — and
// the reader who opened the tab because an agent said it would ask lands here.
reset("granted");
render(payload([ask("a1")], ""));
out.firstPaint = __notifications.length;
out.title = __notifications[0] && __notifications[0].title;
out.body = __notifications[0] && __notifications[0].body;
out.tag = __notifications[0] && __notifications[0].tag;

// Still pending on the next poll: notified once, not once per refresh.
render(payload([ask("a1")], ""));
out.noRepeat = __notifications.length;

// A second question is its own alert with its own tag, so it cannot replace the
// banner for a question still on the board.
render(payload([ask("a1"), ask("a2")], ""));
out.second = __notifications.length;
out.secondTag = __notifications[1] && __notifications[1].tag;

// Two arriving in one pass coalesce: `ask_max_pending` is 16 and this layer has
// no cooldown, so one banner names the count instead of stacking sixteen.
reset("granted");
render(payload([ask("b1"), ask("b2")], ""));
out.burst = __notifications.length;
out.burstTitle = __notifications[0] && __notifications[0].title;

// Permission not granted: record the ids, raise nothing. Then granting it must
// not dump a banner for a question already on the board.
reset("default");
render(payload([ask("c1")], ""));
out.ungranted = __notifications.length;
__notifyPermission = "granted";
render(payload([ask("c1")], ""));
out.afterGrant = __notifications.length;

// An unattributable harness names no harness. The registry is non-empty here,
// so "An agent" is proved to come from a failed lookup.
reset("granted");
render(payload([ask("d1", {harness:"unknown", session_id:""})], ""));
out.unknownTitle = __notifications[0] && __notifications[0].title;

// The session pass still works, and keeps its own tag.
reset("granted");
render(payload([], "", [idle]));
render(payload([ask("e1")], "", [blocked]));
out.both = __notifications.length;
out.bothTags = __notifications.map(n => n.tag).sort();
console.log(JSON.stringify(out));
"""
        out = self._run_page_js(checks)
        self.assertEqual(0, out["nativeOwnsIt"], "would double-notify on macOS")
        self.assertEqual(1, out["firstPaint"])
        self.assertEqual("Claude is asking you", out["title"])
        self.assertEqual("Ship it? · repo/proj", out["body"])
        self.assertEqual("cargento-ask:a1", out["tag"])
        self.assertEqual(1, out["noRepeat"], "notified again for a question already seen")
        self.assertEqual(2, out["second"])
        self.assertEqual("cargento-ask:a2", out["secondTag"])
        self.assertEqual(1, out["burst"], "one banner per pass, however many arrived")
        self.assertEqual("2 questions are waiting for your answer", out["burstTitle"])
        self.assertEqual(0, out["ungranted"])
        self.assertEqual(0, out["afterGrant"], "granting permission dumped the whole board")
        self.assertEqual("An agent is asking you", out["unknownTitle"])
        self.assertEqual(2, out["both"])
        self.assertEqual(["cargento-ask:e1", "claude:12345678"], out["bothTags"])

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
const row = needRow(data, activeNeed, 1);
render(data);
console.log(JSON.stringify({
  rowUsesPrompt: row.includes("Fallback prompt"),
  rowUsesAnchor: row.includes(">30s<"),
  title: document.title,
  shownNeeds: (__els.app.innerHTML.match(/class="need[ "]/g) || []).length
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

    # ── the gate queue ──────────────────────────────────────────────────────
    # The blocked sessions were already a list on screen. These are about the
    # queue it became: an order that means something, a position, a handle per
    # row, and a cursor that walks it. Every one executes the page rather than
    # matching its source, because a queue is behaviour.

    # `blocked_since` values are what the payload's own sort ranks on, so the
    # fixture states them in the order the server would have published — this
    # exercises the page's job, which is to render that order and number it,
    # not to re-derive it. row_order() in aggregate.py is tested for the sort.
    GATE_FIXTURE = """
let __revealed = 0;
let __focused = null;
// Every [data-calm] control in the rendered markup, as something that answers
// getAttribute() and focus() the way a real element would.
const __controls = () => [...__app.innerHTML.matchAll(
    /data-calm="([^"]*)"(?: data-arg="([^"]*)")?/g)].map(m => ({
  getAttribute: a => a === "data-calm" ? m[1]
    : (a === "data-arg" ? (m[2] === undefined ? null : m[2]) : null),
  focus(){ __focused = m[1] + ":" + (m[2] === undefined ? "" : m[2]); }
}));
const __app = {innerHTML: "", className: "",
  querySelectorAll: () => __controls(),
  // Selector-aware: a stub that answers everything makes "the cursor was
  // scrolled into view" pass even when the page asked for the wrong element.
  querySelector(sel){
    if(sel !== ".need.cursor") return null;
    if(!__app.innerHTML.includes('class="need cursor"')) return null;
    return {scrollIntoView(){ __revealed++; }};
  }};
__els.app = __app;
const gate = (sid, blockedSince, detail) => ({
  harness: "claude", session: sid, sid: sid, project: "repo/proj",
  title: "gate-" + sid, last_prompt: "p", state: "needs_input",
  state_detail: detail === undefined ? "permission needed" : detail,
  active: true, last_activity: 900, blocked_since: blockedSince,
  rate_per_min: 0, total: 0, done: 0, open: 0, progress_pct: 0, eta_h: null,
  turn: null, subagents: [], tasks: [], spacedock: null
});
const gateBoard = sessions => ({
  generated: 1000, window_hours: 24, show_all: false, harnesses: [],
  summary: {needs_input: sessions.length, working: 0, rate_per_min: 0,
            active_sessions: sessions.length, open_tasks: 0, progress_pct: 0,
            total_tasks: 0, total_done: 0},
  sessions
});
// The queue as rendered: each row's ordinal and which session it belongs to,
// read back off the DOM rather than from the model that produced it.
const queueOnScreen = () => [...__app.innerHTML.matchAll(
  /class="need(?: cursor)?"><span class="need-n">(\\d+)<[\\s\\S]*?class="need-title">gate-([^<]*)</g)]
  .map(m => m[1] + ":" + m[2]);
const cursorOn = () => (__app.innerHTML.match(
  /class="need cursor">[\\s\\S]*?class="need-title">gate-([^<]*)</) || [])[1] || null;
const key = e => __fire("keydown", Object.assign(
  {target: {tagName: "BODY"}, preventDefault(){}}, e));
"""

    def run_gates(self, checks: str, *, clipboard: str = "none") -> Any:
        clip = {
            "none": "const navigator = {};",
            "ok": (
                "let __wrote = [];\nconst navigator = {clipboard: {writeText(s){"
                " __wrote.push(s); return Promise.resolve(); }}};"
            ),
        }[clipboard]
        prelude = (
            "const localStorage = {getItem: () => null, setItem(){}};\n"
            + clip
            + "\nlet __timers = [];\nconst setTimeout = fn => { __timers.push(fn); };\n"
        )
        return self._run_page_js(self.GATE_FIXTURE + checks, prelude=prelude)

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_band_renders_the_gates_as_a_numbered_queue(self) -> None:
        # Three separate pings cost more attention than one list of three, and a
        # list only reads as a queue if it says where you are in it and how much
        # is left. The band head carries the total; the rows carry their place.
        checks = """
render(gateBoard([gate("aaa", 100), gate("bbb", 500), gate("ccc", 800)]));
const h = __app.innerHTML;
console.log(JSON.stringify({
  queue: queueOnScreen(),
  waiting: (h.match(/class="band-n">([^<]*)</) || [])[1],
  hint: (h.match(/class="band-keys">([^<]*)</) || [])[1],
  handles: (h.match(/class="need-copy"/g) || []).length,
  title: document.title
}));
"""
        out = self.run_gates(checks)
        # Payload order preserved and numbered from the top: the page does not
        # re-sort what the server already ranked.
        self.assertEqual(["1:aaa", "2:bbb", "3:ccc"], out["queue"])
        self.assertEqual("3 waiting", out["waiting"])
        self.assertEqual("j k step · ⏎ copy id", out["hint"])
        self.assertEqual(3, out["handles"], "a gate row with no way to take it")
        self.assertEqual("(3!) Cargento", out["title"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_single_gate_is_not_told_to_step_between_rows(self) -> None:
        # A hint for a movement that cannot move is noise, and the copy handle
        # is exactly as useful with one row as with five.
        checks = """
render(gateBoard([gate("solo", 100)]));
console.log(JSON.stringify({
  hint: (__app.innerHTML.match(/class="band-keys">([^<]*)</) || [])[1],
  waiting: (__app.innerHTML.match(/class="band-n">([^<]*)</) || [])[1]
}));
"""
        out = self.run_gates(checks)
        self.assertEqual("⏎ copy id", out["hint"])
        self.assertEqual("1 waiting", out["waiting"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_queue_cursor_steps_and_survives_the_poll(self) -> None:
        # #app is rebuilt from scratch every poll, so a cursor that lives in the
        # DOM is a cursor that lasts five seconds. It also must not move on its
        # own: a highlight that wanders between polls is worse than none.
        checks = """
const board = gateBoard([gate("aaa", 100), gate("bbb", 500), gate("ccc", 800)]);
const out = {};
render(board);
out.startsAtHead = cursorOn();
key({key: "j"});
out.afterJ = cursorOn();
out.revealedOnMove = __revealed;
render(board);                       // the next poll, same payload
out.afterPoll = cursorOn();
out.revealedOnPoll = __revealed;     // must not have grown
key({key: "k"});
out.afterK = cursorOn();
key({key: "k"});
out.clampsAtTop = cursorOn();
key({key: "j"}); key({key: "j"}); key({key: "j"});
out.clampsAtBottom = cursorOn();
console.log(JSON.stringify(out));
"""
        out = self.run_gates(checks)
        self.assertEqual("aaa", out["startsAtHead"], "the queue opens somewhere other than the top")
        self.assertEqual("bbb", out["afterJ"])
        self.assertEqual(1, out["revealedOnMove"])
        self.assertEqual("bbb", out["afterPoll"], "the poll moved the cursor")
        # Scrolling on every poll would drag the page under a reader looking
        # somewhere else; only a keystroke earns it.
        self.assertEqual(1, out["revealedOnPoll"])
        self.assertEqual("aaa", out["afterK"])
        self.assertEqual("aaa", out["clampsAtTop"])
        self.assertEqual("ccc", out["clampsAtBottom"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_answering_a_gate_advances_the_pass_without_stranding_the_cursor(self) -> None:
        # The whole mechanism: nothing marks a gate handled locally, because a
        # local mark is a claim the page did not measure and a wrong one hides a
        # gate that is still open. The server stops calling the session
        # needs_input, its row leaves the payload, and the cursor inherits.
        checks = """
const out = {};
render(gateBoard([gate("aaa", 100), gate("bbb", 500), gate("ccc", 800)]));
out.head = cursorOn();
// Answer the head gate: the next payload simply does not carry it.
render(gateBoard([gate("bbb", 500), gate("ccc", 800)]));
out.afterHeadCleared = cursorOn();
out.renumbered = queueOnScreen();
// Now stand on the tail and answer something above it. An index-based cursor
// would slide onto a different session here; a key-based one does not.
key({key: "j"});
out.movedToTail = cursorOn();
render(gateBoard([gate("ccc", 800)]));
out.tailKept = cursorOn();
render(gateBoard([]));
out.emptyQueue = cursorOn();
out.bandGone = !__app.innerHTML.includes("Needs your input");
console.log(JSON.stringify(out));
"""
        out = self.run_gates(checks)
        self.assertEqual("aaa", out["head"])
        self.assertEqual(
            "bbb", out["afterHeadCleared"], "the cursor was stranded on an answered gate"
        )
        self.assertEqual(["1:bbb", "2:ccc"], out["renumbered"])
        self.assertEqual("ccc", out["movedToTail"])
        self.assertEqual("ccc", out["tailKept"], "answering another gate moved the cursor off mine")
        self.assertIsNone(out["emptyQueue"])
        self.assertTrue(out["bandGone"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_a_gate_that_cannot_say_what_it_wants_says_so(self) -> None:
        # The per-row text reaches disk only sometimes (docs/design-needs-input.md).
        # An empty detail used to render an empty div — the same blank a row with
        # nothing more to add would leave — so the one row a reader cannot triage
        # was also the one row that looked ordinary.
        checks = """
render(gateBoard([gate("has", 100, "Force push to main?"),
                  gate("none", 500, null),
                  gate("empty", 800, "")]));
const h = __app.innerHTML;
console.log(JSON.stringify({
  spoken: h.includes(">Force push to main?<"),
  unreadable: (h.match(/class="need-detail none"/g) || []).length,
  says: h.includes(">what it wants is not readable here<"),
  neverUndefined: !h.includes("undefined") && !h.includes("null<")
}));
"""
        out = self.run_gates(checks)
        self.assertTrue(out["spoken"], "a detail that exists was not rendered")
        self.assertEqual(2, out["unreadable"], "an absent detail rendered as a blank line")
        self.assertTrue(out["says"])
        self.assertTrue(out["neverUndefined"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_enter_takes_the_gate_the_cursor_is_on(self) -> None:
        # Answering happens in the session's own terminal, so the act the queue
        # can offer is the id that finds it. Enter must take the row under the
        # cursor and not, say, the first one.
        checks = """
const out = {};
render(gateBoard([gate("aaa", 100), gate("bbb", 500)]));
key({key: "j"});
key({key: "Enter"});
await __settle();
out.wrote = __wrote;
out.labelled = __app.innerHTML.includes(">copied<");
out.othersUnchanged = (__app.innerHTML.match(/>copy id</g) || []).length;
console.log(JSON.stringify(out));
"""
        out = self.run_gates(checks, clipboard="ok")
        self.assertEqual(["bbb"], out["wrote"], "Enter copied the wrong session's id")
        self.assertTrue(out["labelled"], "no feedback that the id was copied")
        self.assertEqual(1, out["othersUnchanged"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_bands_copy_button_reaches_the_one_clipboard_implementation(self) -> None:
        # The band's handle is a [data-calm] control routed by the global click
        # listener, which lives in calm.js. Fired as a click, not by calling the
        # action directly: a guard added to that listener — a displayMode check,
        # say — would take the button out of service, and every other test here
        # drives it through the keyboard, which does not go through the listener.
        checks = """
render(gateBoard([gate("aaa", 100), gate("bbb", 500)]));
const btn = /data-calm="copy" data-arg="([^"]*)"/g;
const args = [...__app.innerHTML.matchAll(btn)].map(m => m[1]);
// The second row's button, resolved the way closest() would resolve it.
__fire("click", {target: {closest: sel => sel === "[data-calm]" ? {
  getAttribute: a => a === "data-calm" ? "copy" : (a === "data-arg" ? args[1] : null)
} : null}});
await __settle();
console.log(JSON.stringify({
  args, wrote: __wrote, labelled: __app.innerHTML.includes(">copied<")
}));
"""
        out = self.run_gates(checks, clipboard="ok")
        self.assertEqual(["claude:aaa", "claude:bbb"], out["args"])
        self.assertEqual(["bbb"], out["wrote"], "the click did not reach calmCopyId")
        self.assertTrue(out["labelled"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_regular_view_leaves_the_pages_own_scroll_keys_alone(self) -> None:
        # Calm binds the arrows and Space because its ledger scrolls inside its
        # own frame. The regular view is an ordinary long page, so taking those
        # would remove paging and line-scrolling — and remove them only while
        # something is blocked, since the branch returns early on an empty queue.
        checks = """
const out = {};
let prevented = [];
const press = k => __fire("keydown", {key: k, target: {tagName: "BODY"},
                                      preventDefault(){ prevented.push(k); }});
render(gateBoard([gate("aaa", 100), gate("bbb", 500)]));
for(const k of [" ", "ArrowDown", "ArrowUp", "PageDown", "Home"]) press(k);
out.scrollKeysFree = prevented;
out.cursorUnmoved = cursorOn();
// Snapshot: `__wrote` is the same array the Enter below pushes to.
out.nothingCopied = [...__wrote];
prevented = [];
for(const k of ["j", "k", "Enter"]) press(k);
out.queueKeysTaken = prevented;
console.log(JSON.stringify(out));
"""
        out = self.run_gates(checks, clipboard="ok")
        self.assertEqual([], out["scrollKeysFree"], "the band swallowed a page scroll key")
        self.assertEqual("aaa", out["cursorUnmoved"], "an arrow key moved the queue cursor")
        self.assertEqual([], out["nothingCopied"], "Space copied a session id")
        self.assertEqual(["j", "k", "Enter"], out["queueKeysTaken"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_keyboard_focus_on_a_gate_handle_survives_the_render_it_triggers(self) -> None:
        # #app is rebuilt wholesale, so the focused element stops existing.
        # Activating `copy id` from the keyboard re-renders to show "copied", and
        # without the hand-off calm mode already does, focus lands on <body> and
        # the next Tab restarts at the top of the document. Same control, same
        # rebuild, so it needs the same treatment in both views.
        checks = """
const out = {};
render(gateBoard([gate("aaa", 100), gate("bbb", 500)]));
// Tab to the second row's handle, then activate it.
document.activeElement = {getAttribute: a => a === "data-calm" ? "copy"
  : (a === "data-arg" ? "claude:bbb" : null)};
calmAction("copy", "claude:bbb");
await __settle();
out.afterActivation = __focused;
// And an ordinary poll must not drop it either.
__focused = null;
render(gateBoard([gate("aaa", 100), gate("bbb", 500)]));
out.afterPoll = __focused;
console.log(JSON.stringify(out));
"""
        out = self.run_gates(checks, clipboard="ok")
        self.assertEqual("copy:claude:bbb", out["afterActivation"], "focus fell off the handle")
        self.assertEqual("copy:claude:bbb", out["afterPoll"], "the poll dropped keyboard focus")

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_an_emptied_queue_does_not_keep_its_cursor(self) -> None:
        # Otherwise the key outlives the queue, and the same session blocking
        # again later inherits a cursor that should have been on whichever gate
        # has waited longest.
        checks = """
const out = {};
render(gateBoard([gate("aaa", 100), gate("bbb", 500)]));
key({key: "j"});
out.moved = cursorOn();
render(gateBoard([]));            // every gate answered
out.cleared = waitCursorKey;
// `bbb` blocks again, behind a gate that has waited longer.
render(gateBoard([gate("ccc", 50), gate("bbb", 900)]));
out.head = cursorOn();
console.log(JSON.stringify(out));
"""
        out = self.run_gates(checks)
        self.assertEqual("bbb", out["moved"])
        self.assertIsNone(out["cleared"], "the cursor outlived the queue")
        self.assertEqual("ccc", out["head"], "a stale cursor beat the longest-waiting gate")

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


class AttentionOrderTest(PageJsHarness):
    """One attention ordering, read by both views.

    The card view used to render its sections in payload order, so a board with
    a long-running turn or a freshly-woken idle session put the two views'
    sequences in different orders on the same payload. These execute both views
    against one payload rather than asserting on either comparator's source.
    """

    # A board that exercises every rung of the ladder, published in the order
    # aggregate.py would publish it: gates longest-blocked first, then working
    # and idle rows in bare session-id order. Every fixture below states its ids
    # so that id order is the WRONG answer, so neither the payload's sequence
    # nor the tiebreaker can produce the expected order on its own.
    ATTENTION_FIXTURE = """
let __focused = null;
const __controls = () => [...__els.app.innerHTML.matchAll(
    /data-calm="([^"]*)"(?: data-arg="([^"]*)")?/g)].map(m => ({
  getAttribute: a => a === "data-calm" ? m[1]
    : (a === "data-arg" ? (m[2] === undefined ? null : m[2]) : null),
  focus(){ __focused = m[1]; }
}));
__els.app = {innerHTML: "", className: "",
             querySelectorAll: () => __controls(), querySelector: () => null};
let __scrollTop = 0;
__els["cm-body"] = {get scrollTop(){ return __scrollTop; },
                    set scrollTop(v){ __scrollTop = v; },
                    querySelector: () => null};
const sess = o => Object.assign({
  harness: "claude", session: "s", sid: "s", project: "repo/proj", title: null,
  last_prompt: "", state: "idle", state_detail: "", active: false,
  last_activity: 99000, rate_per_min: 0, total: 0, done: 0, open: 0,
  progress_pct: 0, eta_h: null, turn: null, subagents: [], tasks: [],
  spacedock: null}, o);
const attnBoard = sessions => ({
  generated: 100000, window_hours: 24, show_all: false, harnesses: [],
  rate_window_sec: 600,
  summary: {needs_input: 0, working: 0, rate_per_min: 0, active_sessions: 0,
            open_tasks: 0, progress_pct: 0, total_tasks: 0, total_done: 0},
  sessions});
const busyRow = (sid, over) => sess(Object.assign({
  sid, session: sid, title: sid, state: "working", active: true,
  state_detail: "running Bash", last_activity: 99990}, over || {}));
const quietRow = (sid, at) => sess({sid, session: sid, title: sid,
                                    last_activity: at});
const gateRow = (sid, since) => sess({sid, session: sid, title: sid,
  state: "needs_input", active: true, state_detail: "permission needed",
  last_activity: since, blocked_since: since});
const LONG = {elapsed_h: "2h", eta_h: null, pct: 99, long: true};
const bandOrder = () => [...__els.app.innerHTML.matchAll(
  /class="need-title">([^<]*)/g)].map(m => m[1]);
const cardOrder = () => [...__els.app.innerHTML.matchAll(
  /class="card-title">([^<]*)/g)].map(m => m[1]);
const idleOrder = () => [...__els.app.innerHTML.matchAll(
  /class="idle-title">([^<]*)/g)].map(m => m[1]);
const calmOrderOnScreen = () => [...__els.app.innerHTML.matchAll(
  /class="cm-title"[^>]*>([^<]*)/g)].map(m => m[1]);
"""

    def run_attention(self, checks: str) -> Any:
        prelude = (
            "const localStorage = {getItem: () => null, setItem(){}};\n"
            "const navigator = {};\n"
            "let __timers = [];\nconst setTimeout = fn => { __timers.push(fn); };\n"
        )
        return self._run_page_js(self.ATTENTION_FIXTURE + checks, prelude=prelude)

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_working_cards_lead_with_the_long_running_turn(self) -> None:
        # Rank 1 before rank 2, the same rung calm's ladder has always had. Safe
        # to move a card on, where rate is not: `long` latches within a turn
        # (turns.py's candidate median is non-decreasing in elapsed), so a card
        # moves at most once per turn rather than on every poll.
        checks = """
const out = {};
const board = attnBoard([busyRow("work-a"), busyRow("work-b"),
                         busyRow("work-c", {turn: LONG})]);
render(board);
out.hoisted = cardOrder();
// Same payload a minute later: the hoist must not churn as the rows age.
render({...board, generated: 100060});
out.stable = cardOrder();
// A working row with no turn at all is the ordinary case for a non-Claude
// collector, and it must not throw the whole ordering out.
render(attnBoard([busyRow("work-a", {turn: null}), busyRow("work-b")]));
out.nullTurn = cardOrder();
console.log(JSON.stringify(out));
"""
        out = self.run_attention(checks)
        self.assertEqual(["work-c", "work-a", "work-b"], out["hoisted"])
        self.assertEqual(["work-c", "work-a", "work-b"], out["stable"])
        self.assertEqual(["work-a", "work-b"], out["nullTurn"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_the_idle_list_leads_with_the_most_recently_active(self) -> None:
        # The idle block is clipped, so this ordering decides which idle rows a
        # reader ever sees without clicking. Most recently active first, taken
        # from calm unchanged: the two views' visible idle rows must not be
        # opposite ends of the same list.
        checks = """
const out = {};
// Ids ascend as the activity descends, so server order is the wrong answer.
const board = attnBoard([quietRow("aaa", 90000), quietRow("bbb", 95000),
                         quietRow("ccc", 99000)]);
render(board);
out.recentFirst = idleOrder();
// Two rows quiet since the same instant fall through to the session id, the
// same last tiebreaker every other ordering uses.
render(attnBoard([quietRow("zzz", 95000), quietRow("mmm", 95000)]));
out.ties = idleOrder();
console.log(JSON.stringify(out));
"""
        out = self.run_attention(checks)
        self.assertEqual(["ccc", "bbb", "aaa"], out["recentFirst"])
        self.assertEqual(["mmm", "zzz"], out["ties"])

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_both_views_order_the_same_payload_the_same_way(self) -> None:
        # The anti-drift fence, and the only assertion a duplicated comparator
        # fails. The card view's three sections and calm's single ledger are
        # different renderings of one ladder, so the sequence a reader reads down
        # the page must be the same sequence in both.
        checks = """
const out = {};
const board = attnBoard([
  // Gates as the server publishes them: longest-blocked first.
  gateRow("gate-old", 98000), gateRow("gate-new", 99900),
  busyRow("work-plain-a"), busyRow("work-plain-b"),
  busyRow("work-long", {turn: LONG}),
  quietRow("idle-oldest", 90000), quietRow("idle-mid", 95000),
  quietRow("idle-newest", 99000)]);
render(board);
out.regular = bandOrder().concat(cardOrder(), idleOrder());
setDisplayMode("calm");
out.calmSort = calmSort;
out.calm = calmOrderOnScreen();
console.log(JSON.stringify(out));
"""
        out = self.run_attention(checks)
        self.assertEqual("attention", out["calmSort"], "calm's default order moved")
        self.assertEqual(
            [
                "gate-old",
                "gate-new",
                "work-long",
                "work-plain-a",
                "work-plain-b",
                "idle-newest",
                "idle-mid",
                "idle-oldest",
            ],
            out["calm"],
        )
        self.assertEqual(out["calm"], out["regular"], "the two views disagree on one payload")
