from __future__ import annotations

import base64
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
    def _fake_font_styles() -> str:
        return "".join(
            f'@font-face{{src:url("{slot}")}}\n' for _name, slot in frontend_page.NEXT_FONT_ASSETS
        )

    @staticmethod
    def _write_bundle(web: Path, template: str) -> None:
        next_web = web / "next"
        next_web.mkdir()
        (next_web / "index.html").write_text(template, encoding="utf-8")
        (next_web / "styles.css").write_text(
            NextPageAssetContractTest._fake_font_styles() + ".next{color:red}\n",
            encoding="utf-8",
        )
        for name, _slot in frontend_page.NEXT_FONT_ASSETS:
            asset = next_web / name
            asset.parent.mkdir(parents=True, exist_ok=True)
            asset.write_text("d09GMg==\n", encoding="ascii")
        (next_web / "next-boot.js").write_text("const first = 1;\n", encoding="utf-8")
        (next_web / "next-attention.js").write_text("const attention = 2;\n", encoding="utf-8")
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

        embedded_styles = self._fake_font_styles()
        for _name, slot in frontend_page.NEXT_FONT_ASSETS:
            embedded_styles = embedded_styles.replace(
                slot,
                "data:font/woff2;base64,d09GMg==",
            )
        self.assertEqual(
            (f"<style>{embedded_styles}.next{{color:red}}\n</style>").encode()
            + b"<script>const first = 1;\nconst attention = 2;\nconst middle = 2;\n"
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

    def test_the_next_stylesheet_requires_exactly_one_slot_per_font(self) -> None:
        name, slot = frontend_page.NEXT_FONT_ASSETS[0]
        cases = (
            ("", f"next/styles.css must contain one {slot} slot"),
            (slot * 2, f"next/styles.css must contain one {slot} slot"),
        )
        for replacement, message in cases:
            with self.subTest(replacement=replacement), tempfile.TemporaryDirectory() as tmp:
                web = Path(tmp)
                self._write_bundle(
                    web,
                    "<style>{{CARGENTO_STYLES}}</style><script>{{CARGENTO_APP}}</script>",
                )
                stylesheet = web / "next" / "styles.css"
                stylesheet.write_text(
                    stylesheet.read_text(encoding="utf-8").replace(slot, replacement),
                    encoding="utf-8",
                )
                with (
                    mock.patch.object(frontend_page, "WEB_DIR", web),
                    self.assertRaisesRegex(RuntimeError, f"^{re.escape(message)}$"),
                ):
                    frontend_page.load_next_styles()

        self.assertTrue(name.endswith(".woff2.b64"))

    def test_the_next_stylesheet_rejects_invalid_font_payloads(self) -> None:
        name, _slot = frontend_page.NEXT_FONT_ASSETS[0]
        for payload in ("not base64!", "T1RUTw=="):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as tmp:
                web = Path(tmp)
                self._write_bundle(
                    web,
                    "<style>{{CARGENTO_STYLES}}</style><script>{{CARGENTO_APP}}</script>",
                )
                (web / "next" / name).write_text(payload, encoding="ascii")
                with (
                    mock.patch.object(frontend_page, "WEB_DIR", web),
                    self.assertRaisesRegex(
                        RuntimeError,
                        rf"^next font asset {re.escape(name)} must be base64 WOFF2$",
                    ),
                ):
                    frontend_page.load_next_styles()

    def test_a_missing_next_font_stays_inside_the_next_loader_boundary(self) -> None:
        name, _slot = frontend_page.NEXT_FONT_ASSETS[0]
        with tempfile.TemporaryDirectory() as tmp:
            web = Path(tmp)
            self._write_bundle(
                web,
                "<style>{{CARGENTO_STYLES}}</style><script>{{CARGENTO_APP}}</script>",
            )
            (web / "next" / name).unlink()
            with (
                mock.patch.object(frontend_page, "WEB_DIR", web),
                self.assertRaises(FileNotFoundError),
            ):
                frontend_page.load_next_page()

    def test_every_next_part_exists_and_is_named(self) -> None:
        next_web = frontend_page.WEB_DIR / "next"
        if not next_web.is_dir():
            self.fail("web/next does not exist")
        self.assertEqual(
            (
                "next-boot.js",
                "next-attention.js",
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

    def test_the_next_page_embeds_the_design_fonts_from_pinned_local_assets(self) -> None:
        expected_fonts = {
            "fonts/space-grotesk-v22-vietnamese.woff2.b64": (
                6_772,
                "d699664b145bfeeccc66a4cce7fa55e14eb63efd7ec6b0b2ec52e25dd98f3917",
            ),
            "fonts/space-grotesk-v22-latin-ext.woff2.b64": (
                18_924,
                "054c266fbb441ee059365dba0885d206f67ca05b375de869b88e02ebfccc9b9d",
            ),
            "fonts/space-grotesk-v22-latin.woff2.b64": (
                22_320,
                "a0d054c4af557de20afd6ca59f47ab353bcaec49c63ff04b6c9d39d0f8910557",
            ),
            "fonts/space-mono-v17-regular-vietnamese.woff2.b64": (
                4_116,
                "1ab5cb4b90a56d6031db3618250a1f1bb52a275df5a0ec9ae8e62686550f1af4",
            ),
            "fonts/space-mono-v17-regular-latin-ext.woff2.b64": (
                9_752,
                "b4f90459adf4851575a46d9a492c17ee34c97fe40d56979521de67d1ee77d75a",
            ),
            "fonts/space-mono-v17-regular-latin.woff2.b64": (
                9_464,
                "e0c8e616bda27642f4c3cebaecff6525d901e73afc8a227cbbb0f2af4810f300",
            ),
            "fonts/space-mono-v17-bold-vietnamese.woff2.b64": (
                4_168,
                "e9c42e9aad5bf74da01a810f8777a1ce45d924c4f28faf3a19b046b8f813321c",
            ),
            "fonts/space-mono-v17-bold-latin-ext.woff2.b64": (
                9_732,
                "512458b32bf452ac0e4b33fd6277bf4f07821acefb59db2d1498aa107679a1a6",
            ),
            "fonts/space-mono-v17-bold-latin.woff2.b64": (
                9_552,
                "af7cf6d2b897ec453acdcdacde4e9bcc8410718af5914de865b453e09f10eebc",
            ),
        }
        vietnamese_range = (
            "U+0102-0103,U+0110-0111,U+0128-0129,U+0168-0169,U+01A0-01A1,"
            "U+01AF-01B0,U+0300-0301,U+0303-0304,U+0308-0309,U+0323,U+0329,"
            "U+1EA0-1EF9,U+20AB"
        )
        latin_ext_range = (
            "U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,"
            "U+0304,U+0308,U+0329,U+1D00-1DBF,U+1E00-1E9F,U+1EF2-1EFF,"
            "U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF"
        )
        latin_range = (
            "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,"
            "U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,"
            "U+2212,U+2215,U+FEFF,U+FFFD"
        )
        expected_faces = {
            "fonts/space-grotesk-v22-vietnamese.woff2.b64": (
                "{{CARGENTO_FONT_SPACE_GROTESK_V22_VIETNAMESE}}",
                vietnamese_range,
            ),
            "fonts/space-grotesk-v22-latin-ext.woff2.b64": (
                "{{CARGENTO_FONT_SPACE_GROTESK_V22_LATIN_EXT}}",
                latin_ext_range,
            ),
            "fonts/space-grotesk-v22-latin.woff2.b64": (
                "{{CARGENTO_FONT_SPACE_GROTESK_V22_LATIN}}",
                latin_range,
            ),
            "fonts/space-mono-v17-regular-vietnamese.woff2.b64": (
                "{{CARGENTO_FONT_SPACE_MONO_V17_REGULAR_VIETNAMESE}}",
                vietnamese_range,
            ),
            "fonts/space-mono-v17-regular-latin-ext.woff2.b64": (
                "{{CARGENTO_FONT_SPACE_MONO_V17_REGULAR_LATIN_EXT}}",
                latin_ext_range,
            ),
            "fonts/space-mono-v17-regular-latin.woff2.b64": (
                "{{CARGENTO_FONT_SPACE_MONO_V17_REGULAR_LATIN}}",
                latin_range,
            ),
            "fonts/space-mono-v17-bold-vietnamese.woff2.b64": (
                "{{CARGENTO_FONT_SPACE_MONO_V17_BOLD_VIETNAMESE}}",
                vietnamese_range,
            ),
            "fonts/space-mono-v17-bold-latin-ext.woff2.b64": (
                "{{CARGENTO_FONT_SPACE_MONO_V17_BOLD_LATIN_EXT}}",
                latin_ext_range,
            ),
            "fonts/space-mono-v17-bold-latin.woff2.b64": (
                "{{CARGENTO_FONT_SPACE_MONO_V17_BOLD_LATIN}}",
                latin_range,
            ),
        }
        self.assertEqual(
            tuple((name, marker) for name, (marker, _range) in expected_faces.items()),
            frontend_page.NEXT_FONT_ASSETS,
        )
        for name, (size, digest) in expected_fonts.items():
            with self.subTest(font=name):
                encoded = "".join(
                    frontend_page.next_asset_path(name).read_text(encoding="ascii").splitlines()
                )
                payload = base64.b64decode(encoded, validate=True)
                self.assertEqual(b"wOF2", payload[:4])
                self.assertEqual(size, len(payload))
                self.assertEqual(digest, hashlib.sha256(payload).hexdigest())

        styles = frontend_page.next_asset_path("styles.css").read_text(encoding="utf-8")
        raw_faces = [line for line in styles.splitlines() if line.startswith("@font-face{")]
        for name, (marker, unicode_range) in expected_faces.items():
            with self.subTest(face=name):
                matches = [face for face in raw_faces if marker in face]
                self.assertEqual(1, len(matches))
                self.assertIn(f"unicode-range:{unicode_range}", matches[0])

        assembled = frontend_page.load_next_page().decode()
        self.assertNotIn("fonts.googleapis.com", assembled)
        self.assertNotIn("fonts.gstatic.com", assembled)
        self.assertNotIn("{{CARGENTO_FONT_", assembled)
        self.assertEqual(9, assembled.count("data:font/woff2;base64,"))
        assembled_faces = re.findall(r"@font-face\{([^}]*)\}", assembled)
        grotesk = [face for face in assembled_faces if "font-family:'Space Grotesk'" in face]
        mono = [face for face in assembled_faces if "font-family:'Space Mono'" in face]
        self.assertEqual(3, len(grotesk))
        self.assertTrue(all("font-weight:400 700" in face for face in grotesk))
        self.assertEqual(6, len(mono))
        self.assertEqual(3, sum("font-weight:400;" in face for face in mono))
        self.assertEqual(3, sum("font-weight:700;" in face for face in mono))

        expected_notices = {
            "fonts/SpaceGrotesk-OFL.txt": (
                4_402,
                "c6dec685825f73b18c20926fddc65e8315642e12986f15db0699170940a09efc",
            ),
            "fonts/SpaceMono-OFL.txt": (
                4_392,
                "8e4ee42b2553e1e01504e61cb0d46d148cd8c9e5eacaa3622a7df2d4f2955b9f",
            ),
        }
        for name, (size, digest) in expected_notices.items():
            with self.subTest(notice=name):
                notice = frontend_page.next_asset_path(name).read_bytes()
                self.assertEqual(size, len(notice))
                self.assertEqual(digest, hashlib.sha256(notice).hexdigest())
        sources = frontend_page.next_asset_path("fonts/SOURCES.txt").read_text(encoding="utf-8")
        self.assertIn("Space Grotesk v22", sources)
        self.assertIn("Space Mono v17", sources)
        for _size, digest in expected_fonts.values():
            self.assertIn(digest, sources)

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
        light = re.search(r"(?:\A|\n):root\{([^}]*)\}", styles, re.DOTALL)
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
            r"@media\(prefers-reduced-motion:reduce\)\{\s*"
            r"([^{}]+)\{([^}]*)\}",
            styles,
        )

        self.assertIsNotNone(live_rule)
        self.assertIsNotNone(reduced)
        self.assertIn("color:var(--accent-ink)", live_rule.group(1) if live_rule else "")
        self.assertIn("animation:next-live-pulse", live_rule.group(1) if live_rule else "")
        self.assertIn(".next-live .next-status-dot", reduced.group(1) if reduced else "")
        self.assertIn("animation:none", reduced.group(2) if reduced else "")

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

    def test_operator_text_breaks_an_unbreakable_token(self) -> None:
        # The instruction line quotes what the operator typed, and 50 of 1,789
        # published lines carry a single token over 80 characters (longest 113) —
        # pasted URLs, which `shorten_paths` leaves whole on purpose because the
        # repo and issue number in them are the informative part. Under
        # `max-width:760px` the detail padding drops to 0, so one such token
        # gives the whole page a horizontal scrollbar. Every comparable surface
        # in this stylesheet already guards it.
        styles = (frontend_page.WEB_DIR / "next" / "styles.css").read_text(encoding="utf-8")
        for selector in (
            r"\.next-operation-identity,\.next-operation-fact",
            r"\.next-session-detail-instruction",
        ):
            with self.subTest(selector=selector):
                rule = re.search(selector + r"\{([^}]*)\}", styles)
                self.assertIsNotNone(rule)
                self.assertIn("overflow-wrap:anywhere", rule.group(1) if rule else "")

    def test_session_detail_state_rails_use_the_fixed_palette(self) -> None:
        styles = (frontend_page.WEB_DIR / "next" / "styles.css").read_text(encoding="utf-8")
        for state, color in (
            ("needs_input", "var(--warn)"),
            ("working", "var(--accent)"),
            ("idle", "var(--line2)"),
        ):
            with self.subTest(state=state):
                rule = re.search(
                    rf'\.next-session-detail\[data-next-session-state="{state}"\] '
                    r"\.next-session-current\{([^}]*)\}",
                    styles,
                )
                self.assertIsNotNone(rule)
                self.assertIn(f"border-left-color:{color}", rule.group(1) if rule else "")

    def test_load_next_page_preserves_its_byte_oracles(self) -> None:
        # Per-part first, deliberately. Every part feeds the assembled page, so a
        # one-part edit fails the assembled oracle too. Naming the part that moved
        # is the more useful failure of the two.
        expected_parts = {
            "next-boot.js": (
                10_734,
                "eb9571b96a984c1c0b28ad4fdab534a9384efa8f2f219608749a7381fe95bdb3",
            ),
            "next-attention.js": (
                42_051,
                "9ce3a282a6b002ab9d10b2d373a223c7fb23e048e09ba4f883e4e085e07bb5bf",
            ),
            "next-chrome.js": (
                15_401,
                "74563a98b0ccf6738cdd35f6326f160a9412b678600aee283304a6640fe50ad9",
            ),
            "next-sessions.js": (
                11_566,
                "f0a4c655e10ab356011faae99537e792b3eec160705dfce37c245a7d3e03488c",
            ),
            "next-projects.js": (
                10_277,
                "031c077b56a4115b59b064967d6e751bc3f8a475e4633f1b7ffebe5d24e76174",
            ),
            "next-project.js": (
                8_512,
                "439021748213a21ed311dd1ce931dd500b538ad9cd0317e11d0fc716c1699903",
            ),
            "next-activity.js": (
                5_281,
                "2a74e8ebcd5374ec6b585aceaeaa38818108531edc4bdbe21240e5c45f415858",
            ),
            "next-session.js": (
                15_800,
                "55f5fe8d1582f212981df916ccf225aa2b22348a2977d809fbb506dce20ae0de",
            ),
            "next-workstream.js": (
                11_703,
                "09a077bdbe24d302fe8494e9a3b050b1ff26a0f3a22c31147f81c7592ca4f3dd",
            ),
            "next-delegation.js": (
                7_544,
                "d11ed2749ae3aa351fe26c1205665b6f4b57553aa17d0ce1ecc027371a6e7e7b",
            ),
            "next-controls.js": (
                6_777,
                "4da6527bbf6401db716ab5807748ac01a64aecce996e993ff9e0b42c22fdc811",
            ),
            "next-render.js": (
                2_163,
                "2a9edf6943322da17f5d2bd891fd67c90cfa52db783995615e5f3260fcea3461",
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
        self.assertEqual(39_216, len(styles))
        self.assertEqual(
            "13c9366fdc967de108aa15ee17be956dc2a9532b78e56c52576f8fb2131cd2b7",
            hashlib.sha256(styles).hexdigest(),
        )

        assembled = frontend_page.load_next_page()
        self.assertEqual(316_939, len(assembled))
        self.assertEqual(
            "da859c807b7c0e5d15201e1e8ee5afce081c38e1aee19b52a568b51e847df8c6",
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

    def test_the_default_bundle_mounts_primary_session_navigation(self) -> None:
        out = self._run_page_js(
            "console.log(JSON.stringify(__els.app.innerHTML));",
            '__els.app = {innerHTML: ""};\n',
        )

        self.assertIn(
            '<nav aria-label="Primary"><a href="#n=projects">Projects</a>'
            '<a href="#n=sessions" aria-current="page">Sessions</a></nav>',
            out,
        )
        self.assertNotIn('class="next-breadcrumb" aria-label="Breadcrumb"', out)
        self.assertNotIn("overview", out)


if __name__ == "__main__":
    unittest.main()
