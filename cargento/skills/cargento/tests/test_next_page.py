from __future__ import annotations

import re
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, cast
from unittest import mock

from cargento_runtime.web import page as frontend_page

from .next_harness import NextPageJsHarness

if TYPE_CHECKING:
    from collections.abc import Callable


class NextPageAssetContractTest(unittest.TestCase):
    @staticmethod
    def _loader() -> Callable[[], bytes]:
        loader = getattr(frontend_page, "load_next_page", None)
        if loader is None:
            raise AssertionError("page.py does not expose load_next_page")
        return cast("Callable[[], bytes]", loader)

    @staticmethod
    def _write_bundle(web: Path, template: str) -> None:
        next_web = web / "next"
        next_web.mkdir()
        (next_web / "index.html").write_text(template, encoding="utf-8")
        (next_web / "styles.css").write_text(".next{color:red}\n", encoding="utf-8")
        (next_web / "next-boot.js").write_text("const first = 1;\n", encoding="utf-8")
        (next_web / "next-chrome.js").write_text("const middle = 2;\n", encoding="utf-8")
        (next_web / "next-projects.js").write_text("const projects = 3;\n", encoding="utf-8")
        (next_web / "next-project.js").write_text("const project = 4;\n", encoding="utf-8")
        (next_web / "next-activity.js").write_text("const activity = 5;\n", encoding="utf-8")
        (next_web / "next-session.js").write_text("const session = 6;\n", encoding="utf-8")
        (next_web / "next-workstream.js").write_text("const workstream = 7;\n", encoding="utf-8")
        (next_web / "next-delegation.js").write_text("const delegation = 8;\n", encoding="utf-8")
        (next_web / "next-controls.js").write_text("const controls = 9;\n", encoding="utf-8")
        (next_web / "next-sessions.js").write_text("const sessions = 3;\n", encoding="utf-8")
        (next_web / "next-render.js").write_text("const second = 2;\n", encoding="utf-8")

    def test_load_next_page_resolves_the_patched_web_dir_at_call_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            web = Path(tmp)
            self._write_bundle(
                web,
                "<style>{{CARGENTO_STYLES}}</style><script>{{CARGENTO_APP}}</script>",
            )
            with mock.patch.object(frontend_page, "WEB_DIR", web):
                actual = self._loader()()

        self.assertEqual(
            b"<style>.next{color:red}\n</style>"
            b"<script>const first = 1;\nconst middle = 2;\n"
            b"const sessions = 3;\nconst projects = 3;\n"
            b"const project = 4;\nconst activity = 5;\n"
            b"const session = 6;\nconst workstream = 7;\nconst delegation = 8;\n"
            b"const controls = 9;\n"
            b"const second = 2;\n</script>",
            actual,
        )

    def test_the_next_template_has_exactly_one_of_each_slot(self) -> None:
        cases = (
            ("{{CARGENTO_APP}}", "next/index.html must contain one CARGENTO_STYLES slot"),
            ("{{CARGENTO_STYLES}}", "next/index.html must contain one CARGENTO_APP slot"),
            (
                "{{CARGENTO_STYLES}}{{CARGENTO_STYLES}}{{CARGENTO_APP}}",
                "next/index.html must contain one CARGENTO_STYLES slot",
            ),
            (
                "{{CARGENTO_STYLES}}{{CARGENTO_APP}}{{CARGENTO_APP}}",
                "next/index.html must contain one CARGENTO_APP slot",
            ),
        )
        for template, message in cases:
            with self.subTest(template=template), tempfile.TemporaryDirectory() as tmp:
                web = Path(tmp)
                self._write_bundle(web, template)
                with (
                    mock.patch.object(frontend_page, "WEB_DIR", web),
                    self.assertRaisesRegex(RuntimeError, f"^{re.escape(message)}$"),
                ):
                    self._loader()()

    def test_every_next_part_exists_and_is_named(self) -> None:
        next_web = frontend_page.WEB_DIR / "next"
        if not next_web.is_dir():
            self.fail("web/next does not exist")
        self.assertEqual(
            (
                "next-boot.js",
                "next-chrome.js",
                "next-sessions.js",
                "next-projects.js",
                "next-project.js",
                "next-activity.js",
                "next-session.js",
                "next-workstream.js",
                "next-delegation.js",
                "next-controls.js",
                "next-render.js",
            ),
            frontend_page.NEXT_PARTS,
        )
        actual = {path.name for path in next_web.glob("*.js")}
        self.assertEqual(set(frontend_page.NEXT_PARTS), actual)
        for name in frontend_page.NEXT_PARTS:
            with self.subTest(part=name):
                self.assertGreater((next_web / name).stat().st_size, 0)

    def test_the_next_asset_directory_is_not_a_python_package(self) -> None:
        next_web = frontend_page.WEB_DIR / "next"
        if not next_web.is_dir():
            self.fail("web/next does not exist")
        self.assertEqual([], sorted(path.name for path in next_web.glob("*.py")))

    def test_every_css_variable_the_next_page_uses_is_declared(self) -> None:
        next_web = frontend_page.WEB_DIR / "next"
        if not next_web.is_dir():
            self.fail("web/next does not exist")
        styles = (next_web / "styles.css").read_text(encoding="utf-8")
        page = frontend_page.load_next_page().decode()
        declared = set(re.findall(r"(--[\w-]+)\s*:", styles))
        used = set(re.findall(r"var\((--[\w-]+)", page))
        self.assertEqual(set(), used - declared, "next page uses CSS variables nothing declares")

    def test_reduced_motion_keeps_the_static_live_cue_without_animation(self) -> None:
        styles = (frontend_page.WEB_DIR / "next" / "styles.css").read_text(encoding="utf-8")
        live_rule = re.search(r"\.next-live \.next-status-dot\{([^}]*)\}", styles)
        reduced = re.search(
            r"@media\(prefers-reduced-motion:reduce\)\{"
            r"\.next-live \.next-status-dot\{([^}]*)\}\}",
            styles,
        )

        self.assertIsNotNone(live_rule)
        self.assertIsNotNone(reduced)
        self.assertIn("color:var(--accent-ink)", live_rule.group(1) if live_rule else "")
        self.assertIn("animation:next-live-pulse", live_rule.group(1) if live_rule else "")
        self.assertIn("animation:none", reduced.group(1) if reduced else "")


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextPageBehaviorTest(NextPageJsHarness):
    def test_the_next_bundle_reads_query_values(self) -> None:
        out = self._run_page_js(
            'console.log(JSON.stringify({view: qs("view"), missing: qs("missing")}));',
            'location.search = "?view=project";\n',
        )

        self.assertEqual({"view": "project", "missing": None}, out)

    def test_esc_escapes_all_five_characters(self) -> None:
        out = self._run_page_js(
            "console.log(JSON.stringify(esc(`<img src=x onerror='1' data-note=\"&\">`)));"
        )

        self.assertEqual(
            "&lt;img src=x onerror=&#39;1&#39; data-note=&quot;&amp;&quot;&gt;",
            out,
        )

    def test_the_next_bundle_mounts_the_overview_breadcrumb(self) -> None:
        out = self._run_page_js(
            "console.log(JSON.stringify(__els.app.innerHTML));",
            '__els.app = {innerHTML: ""};\n',
        )

        self.assertIn(
            '<nav class="next-breadcrumb" aria-label="Breadcrumb">'
            "<span>Cargento | overview</span></nav>",
            out,
        )


if __name__ == "__main__":
    unittest.main()
