"""Tests for the embedded-asset linter."""

from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lint_embedded


class ExtractTest(unittest.TestCase):
    PAGE = "<html><style>\n.a{color:red}\n</style><script>\nconst x = 1;\n</script></html>"

    def test_extract_returns_block_contents(self) -> None:
        self.assertEqual("const x = 1;\n", lint_embedded.extract(self.PAGE, "script"))
        self.assertEqual(".a{color:red}\n", lint_embedded.extract(self.PAGE, "style"))

    def test_extract_missing_tag_is_fatal(self) -> None:
        with self.assertRaises(SystemExit):
            lint_embedded.extract("<html></html>", "script")


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
