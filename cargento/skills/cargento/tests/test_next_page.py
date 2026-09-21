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
        loader = getattr(frontend_page, "load_page", None)
        if loader is None:
            raise AssertionError("page.py does not expose load_page")
        return cast("Callable[[], bytes]", loader)

    @staticmethod
    def _fake_font_styles() -> str:
        return "".join(
            f'@font-face{{src:url("{slot}")}}\n' for _name, slot in frontend_page.FONT_ASSETS
        )

    @staticmethod
    def _write_bundle(web: Path, template: str) -> None:
        (web / "index.html").write_text(template, encoding="utf-8")
        (web / "styles.css").write_text(
            NextPageAssetContractTest._fake_font_styles() + ".next{color:red}\n",
            encoding="utf-8",
        )
        for name, _slot in frontend_page.FONT_ASSETS:
            asset = web / name
            asset.parent.mkdir(parents=True, exist_ok=True)
            asset.write_text("d09GMg==\n", encoding="ascii")
        # One marker per part, derived from APP_PARTS rather than listed. The
        # hand-written list this replaces went stale the moment a part was added,
        # and the failure named a byte count rather than the missing file. Order
        # and membership are pinned against literals in the two oracle tests
        # below; this fixture only has to make the loader resolvable.
        for name in frontend_page.APP_PARTS:
            (web / name).write_text(f"/*{name}*/\n", encoding="utf-8")

    def test_load_page_resolves_the_patched_web_dir_at_call_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            web = Path(tmp)
            self._write_bundle(
                web,
                "<style>{{CARGENTO_STYLES}}</style><script>{{CARGENTO_APP}}</script>",
            )
            with mock.patch.object(frontend_page, "WEB_DIR", web):
                actual = self._loader()()

        embedded_styles = self._fake_font_styles()
        for _name, slot in frontend_page.FONT_ASSETS:
            embedded_styles = embedded_styles.replace(
                slot,
                "data:font/woff2;base64,d09GMg==",
            )
        self.assertEqual(
            (f"<style>{embedded_styles}.next{{color:red}}\n</style>").encode()
            + b"<script>"
            + "".join(f"/*{name}*/\n" for name in frontend_page.APP_PARTS).encode()
            + b"</script>",
            actual,
        )

    def test_the_next_template_has_exactly_one_of_each_slot(self) -> None:
        cases = (
            ("{{CARGENTO_APP}}", "index.html must contain one CARGENTO_STYLES slot"),
            ("{{CARGENTO_STYLES}}", "index.html must contain one CARGENTO_APP slot"),
            (
                "{{CARGENTO_STYLES}}{{CARGENTO_STYLES}}{{CARGENTO_APP}}",
                "index.html must contain one CARGENTO_STYLES slot",
            ),
            (
                "{{CARGENTO_STYLES}}{{CARGENTO_APP}}{{CARGENTO_APP}}",
                "index.html must contain one CARGENTO_APP slot",
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
        name, slot = frontend_page.FONT_ASSETS[0]
        cases = (
            ("", f"styles.css must contain one {slot} slot"),
            (slot * 2, f"styles.css must contain one {slot} slot"),
        )
        for replacement, message in cases:
            with self.subTest(replacement=replacement), tempfile.TemporaryDirectory() as tmp:
                web = Path(tmp)
                self._write_bundle(
                    web,
                    "<style>{{CARGENTO_STYLES}}</style><script>{{CARGENTO_APP}}</script>",
                )
                stylesheet = web / "styles.css"
                stylesheet.write_text(
                    stylesheet.read_text(encoding="utf-8").replace(slot, replacement),
                    encoding="utf-8",
                )
                with (
                    mock.patch.object(frontend_page, "WEB_DIR", web),
                    self.assertRaisesRegex(RuntimeError, f"^{re.escape(message)}$"),
                ):
                    frontend_page.load_styles()

        self.assertTrue(name.endswith(".woff2.b64"))

    def test_the_next_stylesheet_rejects_invalid_font_payloads(self) -> None:
        name, _slot = frontend_page.FONT_ASSETS[0]
        for payload in ("not base64!", "T1RUTw=="):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as tmp:
                web = Path(tmp)
                self._write_bundle(
                    web,
                    "<style>{{CARGENTO_STYLES}}</style><script>{{CARGENTO_APP}}</script>",
                )
                (web / name).write_text(payload, encoding="ascii")
                with (
                    mock.patch.object(frontend_page, "WEB_DIR", web),
                    self.assertRaisesRegex(
                        RuntimeError,
                        rf"^font asset {re.escape(name)} must be base64 WOFF2$",
                    ),
                ):
                    frontend_page.load_styles()

    def test_a_missing_next_font_stays_inside_the_next_loader_boundary(self) -> None:
        name, _slot = frontend_page.FONT_ASSETS[0]
        with tempfile.TemporaryDirectory() as tmp:
            web = Path(tmp)
            self._write_bundle(
                web,
                "<style>{{CARGENTO_STYLES}}</style><script>{{CARGENTO_APP}}</script>",
            )
            (web / name).unlink()
            with (
                mock.patch.object(frontend_page, "WEB_DIR", web),
                self.assertRaises(FileNotFoundError),
            ):
                frontend_page.load_page()

    def test_every_next_part_exists_and_is_named(self) -> None:
        web = frontend_page.WEB_DIR
        self.assertEqual(
            (
                "next-boot.js",
                "next-observed.js",
                "next-attention.js",
                "next-notify.js",
                "next-cockpit-compat.js",
                "project.js",
                "next-chrome.js",
                "next-capacity.js",
                "next-sessions.js",
                "next-projects.js",
                "next-project.js",
                "next-intent.js",
                "next-activity.js",
                "next-session.js",
                "next-workstream.js",
                "next-delegation.js",
                "next-controls.js",
                "next-cockpit.js",
                "next-render.js",
                "next-live.js",
            ),
            frontend_page.APP_PARTS,
        )
        actual = {path.name for path in web.glob("*.js")}
        self.assertEqual(set(frontend_page.APP_PARTS), actual)
        for name in frontend_page.APP_PARTS:
            with self.subTest(part=name):
                self.assertGreater((web / name).stat().st_size, 0)

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
            "fonts/ibm-plex-mono-v20-regular-vietnamese.woff2.b64": (
                4_000,
                "0a8b854cc18641bd1b8222afa7ec82a75e59bc6501f777744ec87db1b6cd7a2c",
            ),
            "fonts/ibm-plex-mono-v20-regular-latin-ext.woff2.b64": (
                8_860,
                "f1050dc5317b43434c0aeda599d4624c774ffc162e87a8cf204b949b6a85816d",
            ),
            "fonts/ibm-plex-mono-v20-regular-latin.woff2.b64": (
                10_052,
                "c36f509c0a8f9f85f29cb44bc8701d8a9e0b14c499e77a884f789ead7093a7ac",
            ),
            "fonts/ibm-plex-mono-v20-medium-vietnamese.woff2.b64": (
                4_036,
                "b2529fba93fd07a50ffb8fc3d103eb04b0c298d4f6564d2833c44fde286de7e4",
            ),
            "fonts/ibm-plex-mono-v20-medium-latin-ext.woff2.b64": (
                8_848,
                "77f03e26f981c582bdba3a7abed4baa2d3149211c01366bb3ab3ba7622ec4ae5",
            ),
            "fonts/ibm-plex-mono-v20-medium-latin.woff2.b64": (
                10_060,
                "a76f53ca6612e7b3828eec2311098675b7f9849ae4169a8bcef6302aec02a6c0",
            ),
            "fonts/ibm-plex-mono-v20-semibold-vietnamese.woff2.b64": (
                4_116,
                "69744cabbccc9faf77516ce9b744361e1e6be7f8081400006035a153797d2965",
            ),
            "fonts/ibm-plex-mono-v20-semibold-latin-ext.woff2.b64": (
                8_960,
                "1b6b18fd0fd240bc6d5850f4df621484722d4b5d3650ebdd1e3a8bbd81c75854",
            ),
            "fonts/ibm-plex-mono-v20-semibold-latin.woff2.b64": (
                10_120,
                "ad4580d8cb4b5f627c2d18457656732f7f7b070f7837fbc380e08054157e6f6c",
            ),
            "fonts/ibm-plex-mono-v20-italic-vietnamese.woff2.b64": (
                4_416,
                "fe88a1e1a9cdb5b50308f09aaf573987f4ba2177bc6faa5feeb82a47df277bbb",
            ),
            "fonts/ibm-plex-mono-v20-italic-latin-ext.woff2.b64": (
                9_788,
                "c590f625acd1a18021f23486445b03b8435879b406db1003d3fdd7804e9319fb",
            ),
            "fonts/ibm-plex-mono-v20-italic-latin.woff2.b64": (
                11_568,
                "2665f5fbbb334780fa135c7f1dc6e2459061a2d6d44c32b7c1fdbc34cde65ede",
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
            "fonts/ibm-plex-mono-v20-regular-vietnamese.woff2.b64": (
                "{{CARGENTO_FONT_IBM_PLEX_MONO_V20_REGULAR_VIETNAMESE}}",
                vietnamese_range,
            ),
            "fonts/ibm-plex-mono-v20-regular-latin-ext.woff2.b64": (
                "{{CARGENTO_FONT_IBM_PLEX_MONO_V20_REGULAR_LATIN_EXT}}",
                latin_ext_range,
            ),
            "fonts/ibm-plex-mono-v20-regular-latin.woff2.b64": (
                "{{CARGENTO_FONT_IBM_PLEX_MONO_V20_REGULAR_LATIN}}",
                latin_range,
            ),
            "fonts/ibm-plex-mono-v20-medium-vietnamese.woff2.b64": (
                "{{CARGENTO_FONT_IBM_PLEX_MONO_V20_MEDIUM_VIETNAMESE}}",
                vietnamese_range,
            ),
            "fonts/ibm-plex-mono-v20-medium-latin-ext.woff2.b64": (
                "{{CARGENTO_FONT_IBM_PLEX_MONO_V20_MEDIUM_LATIN_EXT}}",
                latin_ext_range,
            ),
            "fonts/ibm-plex-mono-v20-medium-latin.woff2.b64": (
                "{{CARGENTO_FONT_IBM_PLEX_MONO_V20_MEDIUM_LATIN}}",
                latin_range,
            ),
            "fonts/ibm-plex-mono-v20-semibold-vietnamese.woff2.b64": (
                "{{CARGENTO_FONT_IBM_PLEX_MONO_V20_SEMIBOLD_VIETNAMESE}}",
                vietnamese_range,
            ),
            "fonts/ibm-plex-mono-v20-semibold-latin-ext.woff2.b64": (
                "{{CARGENTO_FONT_IBM_PLEX_MONO_V20_SEMIBOLD_LATIN_EXT}}",
                latin_ext_range,
            ),
            "fonts/ibm-plex-mono-v20-semibold-latin.woff2.b64": (
                "{{CARGENTO_FONT_IBM_PLEX_MONO_V20_SEMIBOLD_LATIN}}",
                latin_range,
            ),
            "fonts/ibm-plex-mono-v20-italic-vietnamese.woff2.b64": (
                "{{CARGENTO_FONT_IBM_PLEX_MONO_V20_ITALIC_VIETNAMESE}}",
                vietnamese_range,
            ),
            "fonts/ibm-plex-mono-v20-italic-latin-ext.woff2.b64": (
                "{{CARGENTO_FONT_IBM_PLEX_MONO_V20_ITALIC_LATIN_EXT}}",
                latin_ext_range,
            ),
            "fonts/ibm-plex-mono-v20-italic-latin.woff2.b64": (
                "{{CARGENTO_FONT_IBM_PLEX_MONO_V20_ITALIC_LATIN}}",
                latin_range,
            ),
        }
        self.assertEqual(
            tuple((name, marker) for name, (marker, _range) in expected_faces.items()),
            frontend_page.FONT_ASSETS,
        )
        for name, (size, digest) in expected_fonts.items():
            with self.subTest(font=name):
                encoded = "".join(
                    frontend_page.asset_path(name).read_text(encoding="ascii").splitlines()
                )
                payload = base64.b64decode(encoded, validate=True)
                self.assertEqual(b"wOF2", payload[:4])
                self.assertEqual(size, len(payload))
                self.assertEqual(digest, hashlib.sha256(payload).hexdigest())

        styles = frontend_page.asset_path("styles.css").read_text(encoding="utf-8")
        raw_faces = [line for line in styles.splitlines() if line.startswith("@font-face{")]
        for name, (marker, unicode_range) in expected_faces.items():
            with self.subTest(face=name):
                matches = [face for face in raw_faces if marker in face]
                self.assertEqual(1, len(matches))
                self.assertIn(f"unicode-range:{unicode_range}", matches[0])

        assembled = frontend_page.load_page().decode()
        self.assertNotIn("fonts.googleapis.com", assembled)
        self.assertNotIn("fonts.gstatic.com", assembled)
        self.assertNotIn("{{CARGENTO_FONT_", assembled)
        self.assertEqual(15, assembled.count("data:font/woff2;base64,"))
        assembled_faces = re.findall(r"@font-face\{([^}]*)\}", assembled)
        grotesk = [face for face in assembled_faces if "font-family:'Space Grotesk'" in face]
        mono = [face for face in assembled_faces if "font-family:'IBM Plex Mono'" in face]
        self.assertEqual(3, len(grotesk))
        self.assertTrue(all("font-weight:400 700" in face for face in grotesk))
        self.assertEqual(12, len(mono))

        def face_axes(face: str) -> tuple[str, str]:
            rules = dict(re.findall(r"([\w-]+):([^;]+)", face))
            return rules.get("font-style", ""), rules.get("font-weight", "")

        # Style and weight together. `font-weight:400;` alone counts the italic
        # subsets as upright regulars, and a sheet that had dropped the italics
        # and shipped six regulars would still total twelve faces.
        split: dict[tuple[str, str], int] = {}
        for face in mono:
            split[face_axes(face)] = split.get(face_axes(face), 0) + 1
        self.assertEqual(
            {
                ("normal", "400"): 3,
                ("normal", "500"): 3,
                ("normal", "600"): 3,
                ("italic", "400"): 3,
            },
            split,
        )

        expected_notices = {
            "fonts/SpaceGrotesk-OFL.txt": (
                4_402,
                "c6dec685825f73b18c20926fddc65e8315642e12986f15db0699170940a09efc",
            ),
            "fonts/IBMPlexMono-OFL.txt": (
                4_456,
                "7e6b2818edbd8f6a01ae80641cc8f16a51080d08fb4e532be3a0b6f74adb07da",
            ),
        }
        for name, (size, digest) in expected_notices.items():
            with self.subTest(notice=name):
                notice = frontend_page.asset_path(name).read_bytes()
                self.assertEqual(size, len(notice))
                self.assertEqual(digest, hashlib.sha256(notice).hexdigest())
        # The retired family's licence travelled with its subsets, so its absence
        # is what says the deletion was complete rather than half done.
        self.assertFalse(frontend_page.asset_path("fonts/SpaceMono-OFL.txt").exists())
        sources = frontend_page.asset_path("fonts/SOURCES.txt").read_text(encoding="utf-8")
        self.assertIn("Space Grotesk v22", sources)
        self.assertIn("IBM Plex Mono v20", sources)
        self.assertNotIn("Space Mono v17", sources)
        for _size, digest in expected_fonts.values():
            self.assertIn(digest, sources)

    def test_the_retired_preview_asset_directory_is_absent(self) -> None:
        self.assertFalse((frontend_page.WEB_DIR / "next").exists())

    def test_the_optional_terminal_uses_the_verified_local_vendor_assets(self) -> None:
        assets = {
            "vendor/xterm.js": (
                488_663,
                "14903579ff54664cd72f8e8699e6961a6272c21863ec1c3b118cdc8af5d4a972",
            ),
            "vendor/xterm.css": (
                7_112,
                "854a7c0fb70e8b1a083c16797ab827299fb18744f5ad34f227b48337e33293c6",
            ),
            "vendor/xterm-LICENSE.txt": (
                1_261,
                "b569f629d00f2626a8100df2a1798210535621e42164dfd426a6fe5aac7b0ccd",
            ),
            "vendor/SOURCES.txt": (
                534,
                "426b3d3a2288c8f88c9b960b5089294aa35c7e77a84969650633669b884e2e45",
            ),
        }
        for name, (size, digest) in assets.items():
            with self.subTest(asset=name):
                data = frontend_page.asset_path(name).read_bytes()
                self.assertEqual(size, len(data))
                self.assertEqual(digest, hashlib.sha256(data).hexdigest())

    def test_every_css_variable_the_canonical_page_uses_is_declared(self) -> None:
        styles = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        page = frontend_page.load_page().decode()
        declared = set(re.findall(r"(--[\w-]+)\s*:", styles))
        used = set(re.findall(r"var\((--[\w-]+)", page))
        self.assertEqual(set(), used - declared, "page uses CSS variables nothing declares")

    def test_the_need_you_button_keeps_visible_keyboard_focus(self) -> None:
        styles = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
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

    def test_the_next_palette_is_dark_only(self) -> None:
        styles = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        roots = re.findall(r"(?:\A|\n):root\{([^}]*)\}", styles, re.DOTALL)
        self.assertEqual(1, len(roots))
        self.assertNotIn("prefers-color-scheme", styles)
        # Reconciliation removed the temporary prototype palette (RC-5).
        for retired in ("--warn", "--alert", "--accent-ink", "--warnink"):
            with self.subTest(retired=retired):
                self.assertNotIn(retired, styles)
        expected = {
            "--sunk": "#0f0f0a",
            "--bg": "#14140f",
            "--panel": "#24231b",
            "--raise": "#323025",
            "--line": "#74725f",
            "--line-hi": "#8a8874",
            "--rule": "#35342a",
            "--ink": "#f6f3ea",
            "--ink2": "#cdc7b4",
            "--ink3": "#a39c88",
            "--accent": "#cfe884",
            "--amber": "#f0b95e",
            "--clay": "#e4886a",
        }
        tokens = dict(re.findall(r"(--[\w-]+):([^;]+);", roots[0]))
        self.assertEqual(expected, {name: tokens.get(name) for name in expected})
        # Derived, so the map above cannot quietly become a subset: a fourteenth
        # colour added to :root fails here rather than going unmeasured. Only
        # flat hex counts -- the elevation tokens carry a shadow colour inside a
        # longer value and are not palette entries.
        self.assertEqual(
            set(expected),
            {
                name
                for name, value in tokens.items()
                if re.fullmatch(r"#[0-9a-f]{6}", value.strip())
            },
        )

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

        # --raise joins the surfaces because v3 gives the reader a fourth one to
        # read text off. --ink3 is inert-control text only and is the tightest
        # pair in the grid at 4.84:1 on --raise, so it stays in the loop rather
        # than being excused for the role it plays.
        for surface in ("--bg", "--panel", "--sunk", "--raise"):
            for ink in (
                "--ink",
                "--ink2",
                "--ink3",
                "--accent",
                "--amber",
                "--clay",
            ):
                with self.subTest(surface=surface, ink=ink):
                    self.assertGreater(contrast(tokens[ink], tokens[surface]), 4.5)
        self.assertGreater(contrast(tokens["--ink"], tokens["--bg"]), 3.0)

    def test_a_reader_can_see_the_edge_of_every_control_they_can_reach(self) -> None:
        """WCAG 2.1 SC 1.4.11: a control's visual boundary needs 3:1.

        Nothing in this repository had ever measured a border. The palette test
        above loops every ink against every surface and stops there, so v2
        shipped control boundaries at 1.22:1 with the suite green -- text
        contrast and non-text contrast are different standards over different
        token sets, and passing one says nothing about the other.

        The floor applies to a boundary that bounds a *component*. `--rule`
        divides rows and bounds nothing, so it is out of scope by the standard
        rather than by exemption, which is the only reason it may sit at
        1.26:1 on `--panel`.
        """
        styles = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        roots = re.findall(r"(?:\A|\n):root\{([^}]*)\}", styles, re.DOTALL)
        self.assertEqual(1, len(roots))
        tokens = dict(re.findall(r"(--[\w-]+):\s*([^;]+);", roots[0]))

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

        # Which surface each boundary is permitted to sit on. The adjacency
        # rules are what make this a short list: --sunk only appears inside
        # --panel, --panel only on --bg, --raise only above --bg, so these are
        # the pairs a reader can actually meet.
        permitted = {
            "--line": ("--bg", "--panel", "--sunk"),
            "--line-hi": ("--bg", "--panel", "--sunk", "--raise"),
        }
        for boundary, surfaces in permitted.items():
            for surface in surfaces:
                with self.subTest(boundary=boundary, surface=surface):
                    self.assertGreaterEqual(
                        contrast(tokens[boundary], tokens[surface]),
                        3.0,
                        f"{boundary} on {surface} must meet SC 1.4.11",
                    )

        # --line on --raise measures 2.72:1, which is why --line-hi exists and
        # why that pairing is banned. Asserting the failure keeps the ban
        # honest: brighten --line enough and this line tells you the second
        # token has stopped earning its place.
        self.assertLess(
            contrast(tokens["--line"], tokens["--raise"]),
            3.0,
            "--line on --raise is the banned pairing --line-hi was added for",
        )

        # The floor has to be capable of failing, or it reports a fact about the
        # schema rather than about the palette. A boundary the colour of its own
        # surface must not pass.
        self.assertLess(contrast(tokens["--panel"], tokens["--panel"]), 3.0)

        # --rule is out of scope for SC 1.4.11 and must stay that way: if it
        # ever bounds a control, the exemption it relies on is gone.
        self.assertIn("--rule", tokens)
        self.assertNotIn("--line2", styles)

    def test_a_reader_never_meets_type_below_the_declared_floor(self) -> None:
        """Every font-size is a declared step, and no step is under 13px.

        The v2 audit measured colour and concluded there was no contrast left
        to spend. The size half was never enforced: 78% of font-size
        declarations resolved to 12.5px or smaller and two shipped at 9px.
        """
        styles = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        roots = re.findall(r"(?:\A|\n):root\{([^}]*)\}", styles, re.DOTALL)
        tokens = dict(re.findall(r"(--[\w-]+):\s*([^;]+);", roots[0]))
        steps = {
            name: float(value.rstrip("px"))
            for name, value in tokens.items()
            if name.startswith("--fs-")
        }
        self.assertTrue(steps, "the sheet declares no type scale")

        for name, size in steps.items():
            with self.subTest(step=name):
                self.assertGreaterEqual(size, 13.0, f"{name} is below the 13px floor")

        body = styles[styles.index("}", styles.index(":root{")) :]
        declarations = [raw.strip() for raw in re.findall(r"font-size:\s*([^;}\n]+)", body)]
        self.assertTrue(declarations)

        # Neither exemption is a type size: `inherit` defers to the step an
        # ancestor already chose, and `0` closes the whitespace gap between
        # inline-blocks. Counted rather than waved through, because exempting a
        # literal by spelling it `inherit` everywhere is the cheap way out.
        self.assertEqual(
            {"inherit": 3, "0": 1},
            {
                value: declarations.count(value)
                for value in set(declarations)
                if not value.startswith("var(")
            },
        )

        used: set[str] = set()
        for value in declarations:
            if value in ("inherit", "0"):
                continue
            with self.subTest(declaration=value):
                match = re.fullmatch(r"var\((--fs-[\w-]+)\)", value)
                self.assertIsNotNone(
                    match,
                    f"font-size:{value} is not a declared step -- no literal sizes",
                )
                assert match is not None
                self.assertIn(match.group(1), steps)
                used.add(match.group(1))

        # A step nobody references is scale drift. v2 carried three of them and
        # that is how a scale grows to twenty-four entries.
        self.assertEqual(set(steps), used, "every declared step must be referenced")

        # Sentences sit at or above 15px, so the floor and the sentence tier
        # cannot silently collapse into one another.
        self.assertGreaterEqual(steps["--fs-body"], 15.0)
        self.assertEqual(13.0, steps["--fs-label"])

        # The loop above has to be capable of failing. The predicate it applies
        # must reject the literal this test exists to keep out of the sheet.
        self.assertIsNone(re.fullmatch(r"var\((--fs-[\w-]+)\)", "11px"))

    def test_reduced_motion_keeps_the_static_live_cue_without_animation(self) -> None:
        styles = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        live_rule = re.search(r"\.next-live \.next-status-dot\{([^}]*)\}", styles)
        reduced = re.search(
            r"@media\(prefers-reduced-motion:reduce\)\{\s*"
            r"([^{}]+)\{([^}]*)\}",
            styles,
        )

        self.assertIsNotNone(live_rule)
        self.assertIsNotNone(reduced)
        self.assertIn("color:var(--ink)", live_rule.group(1) if live_rule else "")
        self.assertIn("animation:next-live-pulse", live_rule.group(1) if live_rule else "")
        self.assertIn(".next-live .next-status-dot", reduced.group(1) if reduced else "")
        self.assertIn("animation:none", reduced.group(2) if reduced else "")

    def test_activity_subagent_names_can_shrink_inside_the_card(self) -> None:
        styles = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
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
        styles = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        for selector in (
            r"\.next-operation-identity,\.next-operation-fact",
            r"\.next-session-detail-instruction",
        ):
            with self.subTest(selector=selector):
                rule = re.search(selector + r"\{([^}]*)\}", styles)
                self.assertIsNotNone(rule)
                self.assertIn("overflow-wrap:anywhere", rule.group(1) if rule else "")

    def test_session_detail_tone_rails_use_the_fixed_palette(self) -> None:
        # Keyed on the observation tone, not the raw harness state: the rule carries
        # what was observed, which is what the palette encodes. The state-keyed
        # predecessor could not express `bad`, so a session that ended dirty wore the
        # same rail as one still working.
        styles = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        for tone, color in (
            ("want", "var(--amber)"),
            ("bad", "var(--clay)"),
            ("ok", "var(--accent)"),
        ):
            with self.subTest(tone=tone):
                rule = re.search(
                    rf'\.next-session-detail\[data-tone="{tone}"\] '
                    r"\.next-session-current\{([^}]*)\}",
                    styles,
                )
                self.assertIsNotNone(rule)
                self.assertIn(f"border-left-color:{color}", rule.group(1) if rule else "")
        # Unknown never gets colour, so it must have no override at all rather than a
        # muted one. Absence of the rule is the assertion.
        self.assertIsNone(
            re.search(
                r'\.next-session-detail\[data-tone="unknown"\] \.next-session-current\{',
                styles,
            ),
        )

    def test_project_scope_tree_is_left_at_wide_width_and_stacks_when_narrow(self) -> None:
        styles = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        styles = styles.split("/* ===== COCKPIT ===== */", 1)[1].split(
            "/* ===== SUBSTRATE ===== */", 1
        )[0]
        wide = re.search(r"\.next-cockpit-shell\{([^}]*)\}", styles)
        narrow = re.search(
            r"@media\(max-width:1279px\)\{[\s\S]*?"
            r"\.next-cockpit-shell\{([^}]*)\}",
            styles,
        )

        self.assertIsNotNone(wide)
        self.assertIn("grid-template-columns:264px minmax(0,1fr)", wide.group(1) if wide else "")
        self.assertIsNotNone(narrow)
        self.assertIn("grid-template-columns:1fr", narrow.group(1) if narrow else "")
        self.assertNotIn("overflow-x:auto", wide.group(1) if wide else "")

        wide_switcher = re.search(r"\.next-cockpit-scope-switcher\{([^}]*)\}", styles)
        narrow_tree = re.search(
            r"@media\(max-width:1279px\)\{[\s\S]*?\.next-cockpit-scope-tree\{([^}]*)\}",
            styles,
        )
        narrow_switcher = re.search(
            r"@media\(max-width:1279px\)\{[\s\S]*?\.next-cockpit-scope-switcher\{([^}]*)\}",
            styles,
        )
        self.assertIsNotNone(wide_switcher)
        self.assertIn("display:none", wide_switcher.group(1) if wide_switcher else "")
        self.assertIsNotNone(narrow_tree)
        self.assertIn("display:none", narrow_tree.group(1) if narrow_tree else "")
        self.assertIsNotNone(narrow_switcher)
        self.assertIn("display:block", narrow_switcher.group(1) if narrow_switcher else "")

        project_cue = re.search(r"\.next-scope-cue--project\{([^}]*)\}", styles)
        session_cue = re.search(r"\.next-scope-cue--session\{([^}]*)\}", styles)
        square = re.search(r"\.next-scope-marker--square\{([^}]*)\}", styles)
        round_marker = re.search(r"\.next-scope-marker--round\{([^}]*)\}", styles)
        branch = re.search(r"\.next-scope-cue--session:before\{([^}]*)\}", styles)
        self.assertIsNotNone(project_cue)
        self.assertIn("border-left:2px solid", project_cue.group(1) if project_cue else "")
        self.assertIsNotNone(session_cue)
        self.assertIn("padding-left:18px", session_cue.group(1) if session_cue else "")
        self.assertIsNotNone(square)
        self.assertIn("border-radius:0", square.group(1) if square else "")
        self.assertIsNotNone(round_marker)
        self.assertIn("border-radius:50%", round_marker.group(1) if round_marker else "")
        self.assertIsNotNone(branch)
        self.assertIn("border-top:1px solid", branch.group(1) if branch else "")
        tree = re.search(r"\.next-cockpit-scope-tree\{([^}]*)\}", styles)
        self.assertIsNotNone(tree)
        self.assertNotIn("overflow-x:auto", tree.group(1) if tree else "")

        now_wide = re.search(
            r'\.next-cockpit-panel\[data-next-cockpit-panel="now"\]\{([^}]*)\}', styles
        )
        now_narrow = re.search(
            r"@media\(max-width:760px\)\{[\s\S]*?"
            r'\.next-cockpit-panel\[data-next-cockpit-panel="now"\]\{([^}]*)\}',
            styles,
        )
        self.assertIsNotNone(now_wide)
        self.assertIn(
            "grid-template-columns:repeat(2,minmax(0,1fr))",
            now_wide.group(1) if now_wide else "",
        )
        self.assertIsNotNone(now_narrow)
        self.assertIn("grid-template-columns:1fr", now_narrow.group(1) if now_narrow else "")

    def test_four_cockpit_tabs_fit_the_smallest_phone_without_pills(self) -> None:
        styles = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        phone_tabs = re.search(
            r"@media\(max-width:420px\)\{[\s\S]*?\.next-cockpit-tabs\{([^}]*)\}",
            styles,
        )
        phone_buttons = re.search(
            r"@media\(max-width:420px\)\{[\s\S]*?\.next-cockpit-tabs button\{([^}]*)\}",
            styles,
        )

        self.assertIsNotNone(phone_tabs)
        self.assertIn(
            "grid-template-columns:repeat(4,minmax(0,1fr))",
            phone_tabs.group(1) if phone_tabs else "",
        )
        self.assertNotIn("overflow-x:auto", phone_tabs.group(1) if phone_tabs else "")
        self.assertIsNotNone(phone_buttons)
        self.assertIn("min-width:0", phone_buttons.group(1) if phone_buttons else "")
        self.assertNotIn("border-radius", phone_buttons.group(1) if phone_buttons else "")

    def test_load_page_preserves_its_byte_oracles(self) -> None:
        # Per-part first, deliberately. Every part feeds the assembled page, so a
        # one-part edit fails the assembled oracle too. Naming the part that moved
        # is the more useful failure of the two.
        expected_parts = {
            "next-boot.js": (
                27_352,
                "b71d627fe8cc06bc4210d23c76c0ee5b2ab644ce15a44c9d617ba66fe398847d",
            ),
            "next-observed.js": (
                31_199,
                "05d0574cd61663223ee75e8bb9eed8d10729733b737d79a4fa8943793116cb89",
            ),
            "next-attention.js": (
                56_558,
                "cf7eb26d4135f352efe4cd7256e46f26514ba9b8e19422ac32fc840ac9b4e71a",
            ),
            "next-notify.js": (
                11_092,
                "1a486fb469b06f8b43d5565440e0cfa30d5bbd848dfcc16f92a7aa492bcd23a3",
            ),
            "next-cockpit-compat.js": (
                599,
                "ebc70801be79cd5805a85a281dd0566a08a97bab72d0356ae923d20f60310db4",
            ),
            "project.js": (
                107_252,
                "3061d51ff0df43a953d156780f0d709f6f166322ffe476dc185cf34728b65a4b",
            ),
            "next-chrome.js": (
                40_112,
                "f7d3fc543edb9c9a52be47a7a297fca29ed8482e1f4af35be7a7ee5d7156ba26",
            ),
            "next-capacity.js": (
                32_515,
                "8ab8d4424a16dc74f76cf4c55be994b37c893eb9f0642eaa57f3e8990611520d",
            ),
            "next-sessions.js": (
                19_745,
                "dbb317ce92bf0bd2b5121b43ab50cbe8878f8712fcfa51581a5b01cb87527f4e",
            ),
            "next-projects.js": (
                4_210,
                "cb0f68097034fd1c14bfec1b5aad03a15b203e35c7cd6c70770be08b8e7ae1d6",
            ),
            "next-project.js": (
                20_726,
                "c2c3edbe4b4d1670570b3f10edfa204c8aa2b68747a8f2ea1d1f9f7b74bd6520",
            ),
            "next-intent.js": (
                21_345,
                "809ce97d1824b872b2946f27bf2f7d8c8ed49b994b525fa39e1a4ec8dcc5ce89",
            ),
            "next-activity.js": (
                6_632,
                "62f971c5e2a570068b7e2c3ee72b2499774d14a3b739f6f908962f91b98382f1",
            ),
            "next-session.js": (
                36_504,
                "4a338ab2c9ce6ae7c197e1361df807a54bbf17b05078541cdba26eeef9fc1c9c",
            ),
            "next-workstream.js": (
                18_659,
                "9680ee01d19296e87cf9b35230a51a7e98ddc764c5bfb80f0e18e7723ece8a04",
            ),
            "next-delegation.js": (
                14_508,
                "36ecd098147995ae96b5ca7846c6a4366142da400a27a2dd5dfcef9ace01fdb6",
            ),
            "next-controls.js": (
                18_571,
                "f0161fcc4a258501b66eccecb5f2233e4ff110b9ad11ccd526fdf1adcdf04069",
            ),
            "next-cockpit.js": (
                198_105,
                "3c3fa0ebd4be8c51ad5b79d8f2919e090022f6832ae094b9bd28322be736853c",
            ),
            "next-render.js": (
                9_280,
                "cd8acef3dbba203adcae08a31df58e7d1fecbfc4a0ede483022622618e115341",
            ),
            "next-live.js": (
                3_340,
                "755ae1c40ffeef20f6c5bfddeafbc798e62ac7e9d2ba9365b92d7ba032905e96",
            ),
        }
        self.assertEqual(tuple(expected_parts), frontend_page.APP_PARTS)
        for name, (size, digest) in expected_parts.items():
            with self.subTest(part=name):
                data = frontend_page.asset_path(name).read_bytes()
                self.assertEqual(size, len(data))
                self.assertEqual(digest, hashlib.sha256(data).hexdigest())

        styles = frontend_page.asset_path("styles.css").read_bytes()
        self.assertEqual(120_344, len(styles))
        self.assertEqual(
            "4362cebacc5326932f55961be5adf613c5d95144a20542fac2d2b0ca568757a6",
            hashlib.sha256(styles).hexdigest(),
        )

        assembled = frontend_page.load_page()
        self.assertEqual(988_962, len(assembled))
        self.assertEqual(
            "f620305e0cf49107ca2534960fb8febd2ae2a7d335379ab63f30b1bec5076070",
            hashlib.sha256(assembled).hexdigest(),
        )


@unittest.skipUnless(shutil.which("node"), "node not available")
class OneDepartureRowTreatmentTest(unittest.TestCase):
    """DRC-4514. The design's own note: reuse this row, do not invent a second.

    The review section puts two collections under one heading, and until this
    was pinned the two rows in it rendered in four different sizes each -- 10px
    against 12.5px for the constraint, 12.5px against 11.5px for the clause,
    13.5px against 12.5px for the model's sentence, 10px against 11.5px for the
    evidence line. The third treatment's band is 13 to 13.5px, so the sentence
    at 12.5px was outside it as well as different from its neighbour.

    Asserted as shared SELECTORS rather than as matching values, because two
    declaration lists that happen to agree today are the state this drifted out
    of. One rule cannot disagree with itself.
    """

    def test_one_string_in_the_bundle_states_the_superseded_fact(self) -> None:
        """DRC-4563. Two wordings of one fact is the divergence the log refuses.

        The reading block and the departure row differ only in their subject
        word, so the characters after it are owned once, in the boot part,
        beside the other two sentences more than one surface states. A second
        literal copy anywhere in the bundle is what this counts. It counts
        characters, so a copy broken over a line join would not be seen; what
        it is for is the ordinary way a second wording arrives, which is
        someone typing the sentence again beside the row that wanted it.
        """
        tail = "is current, so it does not describe what you are asking for now."
        counts = {
            name: frontend_page.asset_path(name).read_bytes().decode().count(tail)
            for name in frontend_page.APP_PARTS
        }

        self.assertEqual(1, counts["next-boot.js"], f"the boot part owns it: {counts}")
        self.assertEqual(1, sum(counts.values()), f"and owns it alone: {counts}")

    def test_the_two_departure_rows_are_declared_by_one_rule_each(self) -> None:
        styles = frontend_page.asset_path("styles.css").read_bytes().decode()
        rules: dict[str, list[str]] = {}
        for chunk in styles.split("}"):
            head, _, body = chunk.rpartition("{")
            if head:
                rules.setdefault(head.strip().splitlines()[-1].strip(), []).append(body)

        for cockpit, session in (
            (".next-cockpit-departure", ".next-session-departure"),
            (".next-cockpit-reading-name", ".next-session-departure-name"),
            (".next-cockpit-reading-clause", ".next-session-departure-clause"),
            (".next-cockpit-reading-detail", ".next-session-departure-reading"),
            (".next-cockpit-reading-evidence", ".next-session-departure-base"),
            (".next-cockpit-reading-stale", ".next-session-departure-stale"),
        ):
            with self.subTest(pair=session):
                shared = [
                    head
                    for head in rules
                    if cockpit in head.split(",") and session in head.split(",")
                ]
                self.assertEqual(
                    1,
                    len(shared),
                    f"{session} must share exactly one declaration list with {cockpit}",
                )


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

    def test_the_default_bundle_mounts_primary_project_navigation(self) -> None:
        out = self._run_page_js(
            "console.log(JSON.stringify(__els.app.innerHTML));",
            '__els.app = {innerHTML: ""};\n',
        )

        # All three top-level routes, because this assertion pinned the literal
        # two-link nav and was one of the two places that held Attention off the
        # header while the router, the title and the `a` shortcut all knew it
        # (DRC-4421). Kept as a literal rather than loosened: it is the mounted
        # bundle's own markup, and the order is part of what a reader learns.
        self.assertIn(
            '<nav aria-label="Primary"><a href="#n=projects" aria-current="page">Projects</a>'
            '<a href="#n=sessions">Sessions</a>'
            '<a href="#n=attention">Attention</a>'
            '<a href="#n=intent">Intent log</a></nav>',
            out,
        )
        self.assertNotIn('class="next-breadcrumb" aria-label="Breadcrumb"', out)
        self.assertNotIn("overview", out)


if __name__ == "__main__":
    unittest.main()
