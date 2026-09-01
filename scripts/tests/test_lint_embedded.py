"""Tests for the frontend source linter."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lint_embedded


def write_page_module(
    web: Path,
    parts: tuple[str, ...],
) -> None:
    """A minimal page.py exposing APP_PARTS, the way the real loader does."""
    names = "".join(f'"{name}", ' for name in parts)
    source = f"APP_PARTS = ({names})\n"
    (web / "page.py").write_text(source, encoding="utf-8")


def write_frontend(
    web: Path,
    *,
    html: str = '<main id="app"></main>',
    css: str = ".app{color:red}\n",
    js: str = "const app = 1;\n",
    stray_js: bool = False,
) -> None:
    """Write the smallest frontend accepted by the linter."""
    (web / "index.html").write_text(html, encoding="utf-8")
    (web / "styles.css").write_text(css, encoding="utf-8")
    (web / "app.js").write_text(js, encoding="utf-8")
    write_page_module(web, ("app.js",))
    if stray_js:
        (web / "stray.js").write_text("const stray = 1;\n", encoding="utf-8")


def run_main_against(web: Path) -> tuple[int, str]:
    output = StringIO()
    with (
        mock.patch.object(lint_embedded, "WEB_DIR", web),
        mock.patch.object(sys, "argv", ["lint_embedded.py"]),
        redirect_stdout(output),
    ):
        return lint_embedded.main(), output.getvalue()


class LoadFrontendTest(unittest.TestCase):
    def test_load_frontend_concatenates_the_named_parts_in_app_parts_order(self) -> None:
        # "zz.js" before "aa.js" proves the order comes from APP_PARTS,
        # not from a sorted directory listing.
        with tempfile.TemporaryDirectory() as tmp:
            web = Path(tmp)
            (web / "index.html").write_text('<main id="app"></main>', encoding="utf-8")
            (web / "styles.css").write_text(".a{color:red}\n", encoding="utf-8")
            (web / "zz.js").write_text("const first = 1;\n", encoding="utf-8")
            (web / "aa.js").write_text("const second = 2;\n", encoding="utf-8")
            write_page_module(web, ("zz.js", "aa.js"))
            self.assertEqual(
                (
                    '<main id="app"></main>',
                    ".a{color:red}\n",
                    "const first = 1;\nconst second = 2;\n",
                ),
                lint_embedded.load_frontend(web),
            )

    def test_load_frontend_names_a_missing_page_module(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            self.assertRaisesRegex(FileNotFoundError, "page.py"),
        ):
            lint_embedded.load_frontend(Path(tmp))

    def test_load_frontend_names_a_missing_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            web = Path(tmp)
            (web / "app.js").write_text("const x = 1;\n", encoding="utf-8")
            write_page_module(web, ("app.js",))
            with self.assertRaisesRegex(FileNotFoundError, "index.html"):
                lint_embedded.load_frontend(web)

    def test_a_part_named_but_missing_on_disk_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            web = Path(tmp)
            (web / "index.html").write_text("<main></main>", encoding="utf-8")
            (web / "styles.css").write_text("", encoding="utf-8")
            write_page_module(web, ("ghost.js",))
            with self.assertRaisesRegex(FileNotFoundError, "ghost.js"):
                lint_embedded.load_frontend(web)

    def test_load_frontend_rejects_invalid_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            web = Path(tmp)
            (web / "index.html").write_bytes(b"\xff")
            (web / "styles.css").write_text("", encoding="utf-8")
            (web / "app.js").write_text("", encoding="utf-8")
            write_page_module(web, ("app.js",))
            with self.assertRaises(UnicodeDecodeError):
                lint_embedded.load_frontend(web)


class LoadAppPartsTest(unittest.TestCase):
    def test_an_empty_part_list_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            web = Path(tmp)
            write_page_module(web, ())
            with self.assertRaisesRegex(ValueError, "APP_PARTS"):
                lint_embedded.load_app_parts(web)

    def test_a_malformed_part_list_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            web = Path(tmp)
            (web / "page.py").write_text('APP_PARTS = ["app.js"]\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "APP_PARTS"):
                lint_embedded.load_app_parts(web)


class CheckStrayScriptsTest(unittest.TestCase):
    def test_a_script_not_named_in_app_parts_is_a_finding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            web = Path(tmp)
            (web / "app.js").write_text("const x = 1;\n", encoding="utf-8")
            (web / "stray.js").write_text('const id = `<i id="ghost"></i>`;\n', encoding="utf-8")
            write_page_module(web, ("app.js",))
            problems = lint_embedded.check_stray_scripts(web)
        self.assertEqual(1, len(problems))
        self.assertIn("stray.js", problems[0])

    def test_a_fully_registered_directory_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            web = Path(tmp)
            (web / "a.js").write_text("const a = 1;\n", encoding="utf-8")
            (web / "b.js").write_text("const b = 2;\n", encoding="utf-8")
            write_page_module(web, ("b.js", "a.js"))
            self.assertEqual([], lint_embedded.check_stray_scripts(web))


class FrontendMainTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_main_rejects_a_syntax_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            web = Path(tmp)
            write_frontend(web, js="const = ;\n")
            result, output = run_main_against(web)

        self.assertEqual(1, result)
        self.assertIn("node --check", output)

    def test_main_rejects_broken_css(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            web = Path(tmp)
            write_frontend(web, css=".app{color:red\n")
            result, output = run_main_against(web)

        self.assertEqual(1, result)
        self.assertIn("unclosed brace", output)

    def test_main_rejects_a_missing_dom_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            web = Path(tmp)
            write_frontend(
                web,
                js='document.getElementById("ghost");\n',
            )
            result, output = run_main_against(web)

        self.assertEqual(1, result)
        self.assertIn("ghost", output)

    def test_main_rejects_a_stray_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            web = Path(tmp)
            write_frontend(web, stray_js=True)
            result, output = run_main_against(web)

        self.assertEqual(1, result)
        self.assertIn("stray.js", output)
        self.assertIn("APP_PARTS", output)


class CheckCssTest(unittest.TestCase):
    def test_clean_css_passes(self) -> None:
        self.assertEqual([], lint_embedded.check_css(".a{color:red}\n.b{margin:0}\n"))

    def test_unbalanced_brace_is_flagged(self) -> None:
        problems = lint_embedded.check_css(".a{color:red}}\n")
        self.assertTrue(any("unbalanced" in problem for problem in problems))

    def test_unclosed_brace_is_flagged(self) -> None:
        problems = lint_embedded.check_css(".a{color:red\n")
        self.assertTrue(any("unclosed" in problem for problem in problems))

    def test_empty_rule_is_flagged(self) -> None:
        problems = lint_embedded.check_css(".a{ }\n")
        self.assertTrue(any("empty rule" in problem for problem in problems))


class CheckDomIdsTest(unittest.TestCase):
    def test_reference_to_static_id_passes(self) -> None:
        page = '<div id="app"></div>'
        js = 'document.getElementById("app");'
        self.assertEqual([], lint_embedded.check_dom_ids(page, js))

    def test_reference_to_js_created_id_passes(self) -> None:
        page = "<div></div>"
        js = ';html = `<span id="spark-x"></span>`; document.getElementById("spark-x");'
        self.assertEqual([], lint_embedded.check_dom_ids(page, js))

    def test_missing_id_is_flagged(self) -> None:
        problems = lint_embedded.check_dom_ids("<div></div>", 'document.getElementById("ghost");')
        self.assertEqual(1, len(problems))
        self.assertIn("ghost", problems[0])


@unittest.skipUnless(shutil.which("node"), "node not available")
class CheckJsTest(unittest.TestCase):
    def test_valid_js_passes(self) -> None:
        self.assertEqual([], lint_embedded.check_js("const x = 1;\n", allow_missing_node=False))

    def test_syntax_error_is_flagged(self) -> None:
        problems = lint_embedded.check_js("const = ;\n", allow_missing_node=False)
        self.assertEqual(1, len(problems))
        self.assertIn("node --check", problems[0])


class CheckJsWithoutNodeTest(unittest.TestCase):
    def test_missing_node_fails_by_default(self) -> None:
        with mock.patch("lint_embedded.shutil.which", return_value=None):
            problems = lint_embedded.check_js("const x = 1;", allow_missing_node=False)
        self.assertEqual(1, len(problems))

    def test_missing_node_downgrades_with_flag(self) -> None:
        with mock.patch("lint_embedded.shutil.which", return_value=None):
            self.assertEqual([], lint_embedded.check_js("const x = 1;", allow_missing_node=True))


class NonLatin1PageTest(unittest.TestCase):
    """The page carries an arrow glyph. Writing the extracted JS through a
    locale codec (cp1252 on Windows) raises instead of linting it."""

    def test_check_js_handles_characters_outside_latin_1(self) -> None:
        findings = lint_embedded.check_js(
            'const arrow = "\u2192"; const box = "\u2500";\n',
            allow_missing_node=True,
        )

        self.assertEqual([], findings)


class MainAgainstRealPageTest(unittest.TestCase):
    def test_real_page_is_clean(self) -> None:
        argv = ["lint_embedded.py"]
        if not shutil.which("node"):
            argv.append("--allow-missing-node")
        with mock.patch.object(sys, "argv", argv):
            self.assertEqual(0, lint_embedded.main())


if __name__ == "__main__":
    unittest.main()
