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

    def test_the_need_you_button_keeps_visible_keyboard_focus(self) -> None:
        styles = (frontend_page.WEB_DIR / "next" / "styles.css").read_text(encoding="utf-8")
        button = re.search(r"\.next-gate\{([^}]*)\}", styles)
        focus = re.search(r"\.next-gate:focus-visible\{([^}]*)\}", styles)

        self.assertIsNotNone(button)
        self.assertIsNotNone(focus)
        button_rules = dict(re.findall(r"([\w-]+):([^;]+)", button.group(1) if button else ""))
        focus_rules = dict(re.findall(r"([\w-]+):([^;]+)", focus.group(1) if focus else ""))
        self.assertEqual("none", button_rules.get("appearance"))
        self.assertEqual("inherit", button_rules.get("font"))
        self.assertEqual("pointer", button_rules.get("cursor"))
        self.assertEqual("2px solid var(--ink)", focus_rules.get("outline"))
        self.assertEqual("3px", focus_rules.get("outline-offset"))

    def test_the_next_palette_tracks_system_light_and_dark_themes(self) -> None:
        styles = (frontend_page.WEB_DIR / "next" / "styles.css").read_text(encoding="utf-8")
        light = re.search(r"\A:root\{([^}]*)\}", styles, re.DOTALL)
        dark = re.search(
            r"@media\(prefers-color-scheme:dark\)\{\s*:root\{([^}]*)\}\s*\}",
            styles,
            re.DOTALL,
        )
        expected = {
            "light": {
                "--bg": "#f6f3ec",
                "--panel": "#fffdf8",
                "--ink": "#26241d",
                "--ink2": "#423e33",
                "--ink3": "#615d52",
                "--line": "#ded7c7",
                "--accent": "oklch(0.80 0.16 122)",
                "--alert": "oklch(0.48 0.20 27)",
                "--sunk": "#f0ece2",
                "--line2": "#b3aa95",
                "--accent-ink": "oklch(0.34 0.07 130)",
                "--warn": "oklch(0.74 0.11 78)",
                "--warnink": "oklch(0.44 0.10 70)",
            },
            "dark": {
                "--bg": "#1a1916",
                "--panel": "#222019",
                "--ink": "#efece3",
                "--ink2": "#c9c5ba",
                "--ink3": "#a19d92",
                "--line": "#3a362c",
                "--accent": "oklch(0.84 0.17 122)",
                "--alert": "oklch(0.76 0.17 27)",
                "--sunk": "#161512",
                "--line2": "#5a5245",
                "--accent-ink": "oklch(0.86 0.10 128)",
                "--warn": "oklch(0.78 0.11 78)",
                "--warnink": "oklch(0.82 0.10 76)",
            },
        }

        self.assertIsNotNone(light)
        self.assertIsNotNone(dark)
        blocks = {
            "light": light.group(1) if light else "",
            "dark": dark.group(1) if dark else "",
        }
        for theme, values in expected.items():
            tokens = dict(re.findall(r"(--[\w-]+):([^;]+);", blocks[theme]))
            with self.subTest(theme=theme):
                self.assertEqual(values, {name: tokens.get(name) for name in values})

        def luminance(value: str) -> float:
            channels = [int(value[index : index + 2], 16) / 255 for index in (1, 3, 5)]
            linear = [
                channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
                for channel in channels
            ]
            return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

        def contrast(first: str, second: str) -> float:
            high, low = sorted((luminance(first), luminance(second)), reverse=True)
            return (high + 0.05) / (low + 0.05)

        for theme, surface in (("light", "--sunk"), ("dark", "--panel")):
            values = expected[theme]
            for ink in ("--ink", "--ink2", "--ink3"):
                with self.subTest(theme=theme, ink=ink):
                    self.assertGreater(contrast(values[ink], values[surface]), 4.5)
            with self.subTest(theme=theme, focus="--ink"):
                self.assertGreater(contrast(values["--ink"], values["--bg"]), 3.0)

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

    def test_activity_subagent_names_can_shrink_inside_the_card(self) -> None:
        styles = (frontend_page.WEB_DIR / "next" / "styles.css").read_text(encoding="utf-8")
        pill = re.search(r"\.next-activity-subagent\{([^}]*)\}", styles)
        name = re.search(r"\.next-activity-subagent-name\{([^}]*)\}", styles)

        self.assertIsNotNone(pill)
        self.assertIsNotNone(name)
        self.assertIn("min-width:0", pill.group(1) if pill else "")
        self.assertIn("max-width:100%", pill.group(1) if pill else "")
        self.assertIn("min-width:0", name.group(1) if name else "")
        self.assertIn("overflow-wrap:anywhere", name.group(1) if name else "")

    def test_session_detail_state_rails_use_the_fixed_palette(self) -> None:
        styles = (frontend_page.WEB_DIR / "next" / "styles.css").read_text(encoding="utf-8")
        inset = re.search(
            r"\.next-session-detail\[data-next-session-state\] "
            r"\.next-session-detail-header\{([^}]*)\}",
            styles,
        )

        self.assertIsNotNone(inset)
        self.assertIn("padding-left:16px", inset.group(1) if inset else "")
        for state, color in (
            ("needs_input", "var(--warn)"),
            ("working", "var(--accent)"),
            ("idle", "var(--line2)"),
        ):
            with self.subTest(state=state):
                rule = re.search(
                    rf'\.next-session-detail\[data-next-session-state="{state}"\] '
                    r"\.next-session-detail-header\{([^}]*)\}",
                    styles,
                )
                self.assertIsNotNone(rule)
                self.assertIn(f"box-shadow:inset 3px 0 {color}", rule.group(1) if rule else "")

    def test_load_next_page_preserves_its_byte_oracles(self) -> None:
        # Per-part first, deliberately. Every part feeds the assembled page, so a
        # one-part edit fails the assembled oracle too. Naming the part that moved
        # is the more useful failure of the two.
        expected_parts = {
            "next-boot.js": (
                4_918,
                "4b801dc5c185732eaddd86501f1e866cb062d11a739e2696df5a45044aac9a3f",
            ),
            "next-chrome.js": (
                6_959,
                "f2e6605bc2db6ecc7f46f5055c5619581c10bce06356e8b56ca31cdcd2294382",
            ),
            "next-sessions.js": (
                3_961,
                "6e2fd02868a09b1437cd719192da8da08b4fabe4c352b351e0d9c37f94fc0e32",
            ),
            "next-projects.js": (
                4_450,
                "c430a56866fd1219b97267375f2b0b3bad3acf3b2dfbcb34c54e51e6845a68ce",
            ),
            "next-project.js": (
                8_057,
                "6896fd91fe77c9a239ae4282c530697aac7b9281855ccb50d9f41c1e14f8c62c",
            ),
            "next-activity.js": (
                4_370,
                "0c3cb4fca08ba93793e746b466cbd323bf13668c6941062bdfe4e79cda21c657",
            ),
            "next-session.js": (
                11_338,
                "7d827a707f187d3673a88b3c73c6ac9fa104c2c3640ead9305604f6590d62b70",
            ),
            "next-workstream.js": (
                11_676,
                "e3e45f1153c7351b05d813159cfbd16aa6f715b1364968ab1e417076459349ce",
            ),
            "next-delegation.js": (
                6_848,
                "a5d75baaa2f4ac4489c854e76320d7a0861086bff47932626196e664ce6cb203",
            ),
            "next-controls.js": (
                6_777,
                "4da6527bbf6401db716ab5807748ac01a64aecce996e993ff9e0b42c22fdc811",
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
        self.assertEqual(21_164, len(styles))
        self.assertEqual(
            "396a89c79204d39f7a54592e4b36f1c03e3f318e3d4ffa5cedc8e9499fe16ec1",
            hashlib.sha256(styles).hexdigest(),
        )

        assembled = frontend_page.load_next_page()
        self.assertEqual(95_036, len(assembled))
        self.assertEqual(
            "c1ae4c13372cf8629d1fcebeb652eae0660dbec11a253848de11637156875f44",
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

    def test_payload_clock_durations_use_compact_second_through_day_tiers(self) -> None:
        out = self._run_page_js(
            """
nextData = {generated: 10000};
const values = [null, NaN, Infinity, -1, 0, 59.9, 60, 3599, 3600, 7740,
  86400, 90 * 86400 + 3 * 3600];
console.log(JSON.stringify({
  formatted: values.map(nextFormatDuration),
  since: [null, "bad", 10010, 9700].map(nextDurationSince)
}));
"""
        )

        self.assertEqual(
            [
                None,
                None,
                None,
                None,
                "0s",
                "59s",
                "1m",
                "59m",
                "1h 0m",
                "2h 9m",
                "1d 0h",
                "90d 3h",
            ],
            out["formatted"],
        )
        self.assertEqual([None, None, "0s", "5m"], out["since"])

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
