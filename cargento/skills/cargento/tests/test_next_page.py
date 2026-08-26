from __future__ import annotations

import hashlib
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
        (next_web / "next-live.js").write_text("const live = 10;\n", encoding="utf-8")

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
            b"const second = 2;\nconst live = 10;\n</script>",
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
                "next-live.js",
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

    def test_load_next_page_preserves_its_byte_oracles(self) -> None:
        # Per-part first, deliberately. Every part feeds the assembled page, so a
        # one-part edit fails the assembled oracle too. Naming the part that moved
        # is the more useful failure of the two.
        expected_parts = {
            "next-boot.js": (
                4_467,
                "37d911e2ddfa839027459d5cbc7f21753e3415a434f603b5fb60e20f37cea7ad",
            ),
            "next-chrome.js": (
                6_475,
                "d1b5c613500a7085b6d1ee0cc524f6ded74770ad0b8dd80b712769455052d7c7",
            ),
            "next-sessions.js": (
                4_371,
                "e423883841b6460e12fdce76ccb5f294365f82a34e67c64ecd3b67861443c995",
            ),
            "next-projects.js": (
                4_211,
                "df0855a9717723a0966267d8921fae3b2ae6b082d3bd6475fb4453714ac9b407",
            ),
            "next-project.js": (
                7_963,
                "8b5eb09d3f7edb62b4c1b88bc8fdddb93db0e025a4b099c41c5dd9ec831982f0",
            ),
            "next-activity.js": (
                3_264,
                "3207c30ecb13c5fc441a5007c28412e56de32f952b0d8da2c858694bf2e12c1a",
            ),
            "next-session.js": (
                8_139,
                "a584f09e0d8813d973acd00ec577a7008f88079dee818979e0802ff7006050e4",
            ),
            "next-workstream.js": (
                11_217,
                "8a0c1ee5835d96744bf7a2d20cec4d936da8032b3c57dba387a414b30505e0e7",
            ),
            "next-delegation.js": (
                6_643,
                "067545d9d3b2a0f8910b61587a7dec32a59640a4e78d69d75588e7833e2d30b3",
            ),
            "next-controls.js": (
                6_761,
                "ef871e0e9dac2f7bd698fdefc1f38ed3b0a17333cca7f68fe53a5f761fef771d",
            ),
            "next-render.js": (
                802,
                "fc842fa72b4c12e25ee34c6aa0403e12689653985be5e198677e3cfb831234b3",
            ),
            "next-live.js": (
                3_470,
                "aa1aaee8762d734fe8841c88a10ece2c5a4e38b8fe6b6df6f26c62d2d7563d3e",
            ),
        }
        self.assertEqual(tuple(expected_parts), frontend_page.NEXT_PARTS)
        for name, (size, digest) in expected_parts.items():
            with self.subTest(part=name):
                data = frontend_page.next_asset_path(name).read_bytes()
                self.assertEqual(size, len(data))
                self.assertEqual(digest, hashlib.sha256(data).hexdigest())

        styles = frontend_page.next_asset_path("styles.css").read_bytes()
        self.assertEqual(19_530, len(styles))
        self.assertEqual(
            "18a8a2bd48dfa58128ec467b0562c3ebf2e1727ae01155cb78bd083af1b67a38",
            hashlib.sha256(styles).hexdigest(),
        )

        assembled = frontend_page.load_next_page()
        self.assertEqual(87_559, len(assembled))
        self.assertEqual(
            "6bfb31b2543a3479cf49ffcdfc6a2c3fa591c2903b925babe2192b16e7bf4eb5",
            hashlib.sha256(assembled).hexdigest(),
        )


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
