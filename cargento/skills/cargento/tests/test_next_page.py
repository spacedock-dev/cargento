from __future__ import annotations

import base64
import hashlib
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, cast
from unittest import mock

from cargento_runtime.web import page as frontend_page

from .next_harness import NextPageJsHarness

if TYPE_CHECKING:
    from collections.abc import Callable


# --- The size guard's parser (DRC-4596) ---------------------------------------
#
# What it can see, and what it cannot. Every function below reads ONE rule at a
# time out of the stylesheet text. That is deliberate -- the alternative costed
# at triage, a selector-prefix scope plus a suffix allowlist, inspects 137 rules
# and fails 68, so the only route to green is a ~70-entry allowlist maintained
# by whoever is trying to get CI green. At that size the allowlist is the
# specification and the assertion measures nothing.
#
# The cost of reading one rule at a time is a blind spot that is structural, not
# a parser weakness, and it is stated here rather than implied away: where a
# sentence takes its size from one rule, its family from a second and its
# line-height from a third, no regex can join them. Two such sentences render
# today -- `.next-operation-fact--unknown strong` (163 strings at 12.5px) and
# `.next-cockpit-recovery small` (18 strings at 12.5px). Neither is in any
# census below, and neither is caught by any assertion here. THIS GUARD DOES NOT
# ESTABLISH A UNIVERSAL 15px FLOOR and must not be cited as one; DRC-4602 sizes
# the residual and only a computed style sees the composed class. A size guard
# that passed while sentences rendered below its claimed floor would be this
# milestone's own defect shipped as its remedy.
#
# Every function takes CSS TEXT rather than a path, so the mutant tests can feed
# a modified copy through the same code without touching the working tree -- no
# byte-pin oracle moves, and the falsifier is a committed test rather than a
# procedure someone promises they ran.

SENTENCE_FLOOR_PX = 15.0
"""Written as a literal, never read from `--fs-sentence`.

Reading the floor out of the token makes every assertion below vacuous:
retuning `--fs-sentence` to 12px in a scratch copy took the sub-floor census
from 19 rules to 0 while the test stayed green.
"""

LABEL_FLOOR_PX = 11.0


def _css_body(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)


def _type_tokens(css: str) -> dict[str, float]:
    """The `--fs-*` table from the single `:root` block."""
    roots = re.findall(r"(?:\A|\n):root\{([^}]*)\}", _css_body(css), re.DOTALL)
    if len(roots) != 1:
        raise AssertionError(f"expected exactly one :root block, found {len(roots)}")
    return {
        name: float(value) for name, value in re.findall(r"--(fs-[a-z0-9-]+):([0-9.]+)px", roots[0])
    }


def _rules(css: str) -> list[tuple[str, str]]:
    """Every rule as (selector text, declarations), `:root` and at-rules dropped."""
    out: list[tuple[str, str]] = []
    for block in re.finditer(r"([^{}]+)\{([^{}]*)\}", _css_body(css)):
        selector = block.group(1).strip()
        if not selector or selector.startswith(("@", ":root")):
            continue
        out.append((selector, block.group(2)))
    return out


def _declared_size(decls: str, tokens: dict[str, float]) -> float | None:
    """The size a rule declares, resolving `var(--fs-*)` against `:root` first.

    Without the indirection every rule in scope declares a token name rather
    than a number, so a literal scan passes all of them and measures nothing.
    """
    token = re.search(r"font-size:\s*var\(--(fs-[a-z0-9-]+)\)", decls) or re.search(
        r"font:[^;]*?var\(--(fs-[a-z0-9-]+)\)", decls
    )
    if token:
        return tokens.get(token.group(1))
    # The lookbehind keeps `font:10.5px/1.5` from matching the weight slot; the
    # same defect in an earlier draft resolved that shorthand to 0.5px.
    literal = re.search(r"font-size:\s*([0-9.]+)px", decls) or re.search(
        r"font:[^;{}]*?(?<![0-9.])([0-9.]+)px", decls
    )
    return float(literal.group(1)) if literal else None


def _declared_line_height(decls: str) -> float | None:
    """A rule's own prose line-height, from the longhand or the `font:` slash slot.

    The shorthand alternative is load-bearing: the sentence rules in this sheet
    are written `font:500 var(--fs-sentence)/1.55 var(--sans)`, and a pattern
    that only accepted a px literal before the slash saw 25 sentence rules where
    there are 68.
    """
    longhand = re.search(r"line-height:\s*([0-9.]+)", decls)
    if longhand:
        return float(longhand.group(1))
    shorthand = re.search(r"font:[^;{}]*?(?:[0-9.]+px|var\(--fs-[a-z0-9-]+\))/([0-9.]+)", decls)
    return float(shorthand.group(1)) if shorthand else None


def _is_mono(decls: str) -> bool:
    return "var(--mono)" in decls or "monospace" in decls


def _sentence_census(css: str) -> tuple[list[tuple[str, float]], list[tuple[str, float]]]:
    """Split every sentence-tier rule into (at or above the floor, below it).

    Membership is the test `docs/design-next-ui.md` states under "Type scale":
    a rule is on the sentence tier when it sets its text in sans and declares
    its own prose line-height. Derived from what the rule declares, so it cannot
    become the structurally-present default AGENTS.md warns about, and it needs
    no allowlist.
    """
    tokens = _type_tokens(css)
    above: list[tuple[str, float]] = []
    below: list[tuple[str, float]] = []
    for selector, decls in _rules(css):
        if _is_mono(decls):
            continue
        height = _declared_line_height(decls)
        if height is None or height < 1.3:
            continue
        size = _declared_size(decls, tokens)
        if size is None:
            continue
        (above if size >= SENTENCE_FLOOR_PX else below).append((selector, size))
    return above, below


def _sub_label_floor_literals(css: str) -> set[tuple[str, float]]:
    """Every px literal below the label floor, written outside `:root`."""
    found: set[tuple[str, float]] = set()
    for selector, decls in _rules(css):
        sizes = [float(value) for value in re.findall(r"font-size:\s*([0-9.]+)px", decls)]
        sizes += [
            float(value) for value in re.findall(r"font:[^;{}]*?(?<![0-9.])([0-9.]+)px", decls)
        ]
        found.update((selector, size) for size in sizes if size < LABEL_FLOOR_PX)
    return found


def _absence_rules(css: str) -> list[tuple[str, str]]:
    """Rules whose selector carries an absence marker."""
    markers = ("--absent", "[data-next-withheld]", "-clause-absent")
    return [(sel, decls) for sel, decls in _rules(css) if any(m in sel for m in markers)]


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
                notice = frontend_page.asset_path(name).read_bytes()
                self.assertEqual(size, len(notice))
                self.assertEqual(digest, hashlib.sha256(notice).hexdigest())
        sources = frontend_page.asset_path("fonts/SOURCES.txt").read_text(encoding="utf-8")
        self.assertIn("Space Grotesk v22", sources)
        self.assertIn("Space Mono v17", sources)
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
            "--bg": "#14140f",
            "--panel": "#1c1c16",
            "--sunk": "#11110c",
            "--line": "#2c2c23",
            "--line2": "#403f33",
            "--ink": "#f4f1e8",
            "--ink2": "#c9c4b4",
            "--ink3": "#9b9484",
            "--accent": "#c6e07a",
            "--accent-dim": "#8ea254",
            "--amber": "#e8b45c",
            "--clay": "#e08a6a",
        }
        tokens = dict(re.findall(r"(--[\w-]+):([^;]+);", roots[0]))
        self.assertEqual(expected, {name: tokens.get(name) for name in expected})

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

        for surface in ("--bg", "--panel", "--sunk"):
            for ink in (
                "--ink",
                "--ink2",
                "--ink3",
                "--accent",
                "--accent-dim",
                "--amber",
                "--clay",
            ):
                with self.subTest(surface=surface, ink=ink):
                    self.assertGreater(contrast(tokens[ink], tokens[surface]), 4.5)
        self.assertGreater(contrast(tokens["--ink"], tokens["--bg"]), 3.0)

    # --- DRC-4596: the size guard, and the three mutants that falsify it ------

    SUB_LABEL_FLOOR_REGISTRY: ClassVar[set[tuple[float, str]]] = {
        (10.0, ".next-rail-capacity-caption"),
        (10.5, ".next-capacity-scope"),
        (10.5, ".next-capacity-window i"),
        (10.5, ".next-delegation-metrics"),
        (10.5, ".next-operation-harness"),
        (10.5, ".next-project-change time,.next-project-change-harness"),
    }
    """The px literals below the 11px label floor, recorded rather than raised.

    A registry, not a floor: it does not demand these five be raised, only that
    a sixth cannot arrive unnoticed. Triage recorded six against the pre-DRC-4590
    tree; `.next-guardrail-add` left the set when DRC-4590 gave it `.next-action`.
    """

    SUB_SENTENCE_FLOOR_INVENTORY: ClassVar[set[tuple[float, str]]] = {
        (12.5, ".next-cockpit-content .next-cockpit-evidence-missing"),
        (12.5, ".next-cockpit-empty,.next-cockpit-evidence-missing"),
        (12.5, ".next-cockpit-held-absent"),
        (12.5, ".next-cockpit-reading-clause-absent"),
        (12.5, ".next-cockpit-reading-stale,.next-session-departure-stale"),
        (
            12.5,
            ".next-cockpit-recovery .next-project-goal-text.next-project-value--absent,\n.next-cockpit-recovery .next-project-goal-gap",
        ),
        (12.5, ".next-cockpit-recovery .next-project-value--absent"),
        (12.5, ".next-cockpit-work-absent,.next-cockpit-work-limit,.next-cockpit-work-dropped"),
        (12.5, ".next-delegation-withheld small"),
        (12.5, ".next-guardrail-copy small,.next-guardrail-empty"),
        (12.5, ".next-project-detail-rail .next-rail-reason"),
        (12.5, ".next-project-goal-gap"),
        (12.5, ".pc-substrate-empty,.pc-substrate-reason,.pc-terminal-identity p"),
        (12.5, ".pc-trail-quiet,.pc-trail-history,.pc-event-evidence"),
        (13.0, ".next-attention-part"),
        (13.0, ".next-attention-risk-observation p"),
        (13.0, ".next-cockpit-work-derived"),
        (13.0, ".pc-semantic-timeline,.pc-terminal"),
        (13.0, ".pc-trail-result"),
        (13.5, ".next-attention-brief p"),
        (13.5, ".next-attention-risk-identity h3"),
        (13.5, ".next-capacity-prospect"),
        (
            13.5,
            ".next-cockpit-reading-result,.next-cockpit-reading-detail,.next-session-departure-reading",
        ),
        (13.5, ".next-operations-header p"),
        (14.0, ".next-cockpit-held-field textarea"),
        (14.0, ".next-course-episode p,.next-course-episode ul,.next-course-direction p"),
        (14.0, ".next-operation-identity strong,.next-operation-fact strong"),
        (14.0, ".next-session-ask-question"),
        (
            14.0,
            ".next-session-current>strong,.next-session-command-facts strong,.next-session-command-context",
        ),
        (14.0, ".next-session-detail-instruction"),
        (14.0, ".next-session-health"),
        (14.0, ".next-usage-consent"),
        (14.5, ".next-project-goal-text"),
    }
    """The sentence-tier rules still below the floor, which DRC-4602 sizes.

    An exact set, so a rule LEAVING the sentence tier for a lower one reds here
    just as a new sub-floor rule does. `docs/design-next-ui.md` reports the
    single-rule census as seventeen; the two it does not count are the `.pc-*`
    prototype rules, `.pc-semantic-timeline,.pc-terminal` and `.pc-trail-result`.
    That gap was left open at triage and is settled here against the tree.
    """

    def test_the_root_type_tokens_hold_the_label_floor(self) -> None:
        tokens = _type_tokens((frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8"))
        self.assertEqual(21, len(tokens))
        below = {name: size for name, size in tokens.items() if size < LABEL_FLOOR_PX}
        self.assertEqual({}, below)
        # Zero margin is the useful state: --fs-label and --fs-machine sit ON
        # the floor, so any new sub-11px step reds immediately.
        self.assertEqual(LABEL_FLOOR_PX, min(tokens.values()))
        self.assertEqual(SENTENCE_FLOOR_PX, tokens["fs-sentence"])

    def test_a_retuned_label_token_is_caught(self) -> None:
        """Mutation: `--fs-label:11px` -> `10.5px`, applied to an in-process copy.

        The tree is never touched, so no byte-pin oracle moves and this is a
        committed check rather than a procedure someone promises they ran.
        """
        css = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        self.assertEqual({}, {n: s for n, s in _type_tokens(css).items() if s < LABEL_FLOOR_PX})
        mutant = css.replace("--fs-label:11px", "--fs-label:10.5px", 1)
        self.assertNotEqual(css, mutant)
        self.assertEqual(
            {"fs-label": 10.5},
            {n: s for n, s in _type_tokens(mutant).items() if s < LABEL_FLOOR_PX},
        )

    def test_sub_label_floor_literals_are_exactly_the_registry(self) -> None:
        css = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        found = {(size, selector) for selector, size in _sub_label_floor_literals(css)}
        self.assertEqual(self.SUB_LABEL_FLOOR_REGISTRY, found)

    def test_sentence_tier_rules_resolve_at_or_above_the_floor(self) -> None:
        css = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        above, below = _sentence_census(css)
        # Recomputed on the merged tree. The branch this came from read 70 against
        # a pre-squash DRC-4587 tree that raised thirteen rules the narrower #361
        # did not; main resolves 55 and the four branches here add seven.
        self.assertEqual(62, len(above))
        self.assertEqual(
            self.SUB_SENTENCE_FLOOR_INVENTORY, {(size, selector) for selector, size in below}
        )

    def test_a_sentence_rule_edited_below_the_floor_is_caught(self) -> None:
        """Mutation: one `font:` shorthand's `var(--fs-sentence)` -> `var(--fs-xs)`.

        The shorthand form is the one that matters. Every sentence rule in this
        sheet is written `font:500 var(--fs-sentence)/1.55 var(--sans)`, so a
        parser that only read the `font-size` longhand would pass this mutant.
        """
        css = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        mutant = css.replace(
            "font:500 var(--fs-sentence)/1.55 var(--sans)",
            "font:500 var(--fs-xs)/1.55 var(--sans)",
            1,
        )
        self.assertNotEqual(css, mutant)
        clean_above, clean_below = _sentence_census(css)
        mutant_above, mutant_below = _sentence_census(mutant)
        self.assertEqual(len(clean_above) - 1, len(mutant_above))
        self.assertEqual(len(clean_below) + 1, len(mutant_below))

    def test_a_retuned_sentence_token_cannot_silence_the_census(self) -> None:
        """Why SENTENCE_FLOOR_PX is a literal and not read from the token.

        Retuning `--fs-sentence` to 12px would take the sub-floor inventory from
        19 rules to 0 against a token-derived floor. Against the literal the
        inventory grows instead, which is what a reader would want to hear.
        """
        css = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        mutant = css.replace("--fs-sentence:15px", "--fs-sentence:12px", 1)
        self.assertNotEqual(css, mutant)
        _, clean_below = _sentence_census(css)
        _, mutant_below = _sentence_census(mutant)
        self.assertGreater(len(mutant_below), len(clean_below))

    def test_the_steer_caveat_never_outranks_the_field_it_warns_about(self) -> None:
        """DRC-4595's raise, checked as a pair rather than as a floor.

        The caveat and the field are two branches of one control that a reader
        meets together, so the caveat alone proves nothing: raised on its own it
        would draw the warning larger than the words it warns about, the same
        ordering defect as an absence outranking its value. Both sides are read
        here, and equality is the assertion. Drop the field back to
        `var(--fs-xs)` and this reds on the comparison, not on a literal.

        The label above them stays on the label tier on purpose -- `STEER ·
        LOCAL ONLY` is a caption, and DRC-4587's ruling is that a value is never
        drawn smaller than the caption beside it, not that the two match.
        """
        css = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        tokens = _type_tokens(css)
        sizes = {
            selector: _declared_size(decls, tokens)
            for selector, decls in _rules(css)
            if selector in (".next-steer-caveat", ".next-steer-label", ".next-action")
            or selector == ".next-steer input,.next-guardrail-add-input input"
        }
        caveat = sizes[".next-steer-caveat"]
        field = sizes[".next-steer input,.next-guardrail-add-input input"]
        assert caveat is not None and field is not None
        self.assertEqual(field, caveat)
        self.assertEqual(SENTENCE_FLOOR_PX, caveat)
        # The submit sits in the same row as the field; DRC-4590's primitive
        # carries it, so this reds if the promoted control forks a local rule.
        self.assertEqual(field, sizes[".next-action"])
        self.assertEqual(LABEL_FLOOR_PX, sizes[".next-steer-label"])

    def test_absence_rules_stay_sans_and_never_outrank_their_value(self) -> None:
        """DRC-4589's ruling, as far as one rule at a time can carry it.

        The ruling is that an absence is a SANS SENTENCE sharing `--ink3` with
        labels, separated by family and case rather than by ink. The family half
        is checkable per rule. The size half is not, quite: three of these rules
        declare no size at all and inherit one, and the one rule that declares a
        sub-floor size is `.next-project-value--absent` at 12.5px -- which is
        CORRECT, because its paired value resolves to 12.5px too in every
        context that rule reaches. Resolved through the cascade at four call
        sites: session line 12.5/12.5, project scope 12.5/12.5, activity title
        14.0/14.0, cockpit recovery 15.0/15.0. Raising the absence alone would
        make a stated absence render larger than the fact it replaces, which is
        the defect this milestone has already shipped four times.

        So the size clause is bound to the pair rather than to a floor: the
        exception holds only while `.next-project-value--known` declares no size
        of its own. Give the value a size and this reds, which is exactly when
        the pair must be re-measured.
        """
        css = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        tokens = _type_tokens(css)
        absences = _absence_rules(css)
        self.assertEqual(7, len(absences))
        for selector, decls in absences:
            with self.subTest(selector=selector):
                self.assertFalse(_is_mono(decls))
        sized = {
            selector: size
            for selector, decls in absences
            if (size := _declared_size(decls, tokens)) is not None
        }
        below = {sel: size for sel, size in sized.items() if size < SENTENCE_FLOOR_PX}
        # Four rules sit below the floor, and each was measured against the
        # value it replaces rather than asserted alone -- the discipline whose
        # absence cost this milestone four review cycles. All four pairs
        # resolve 12.5/12.5, so none outranks its value:
        #   .next-project-value--absent            vs .next-project-value--known (unsized)
        #   .next-cockpit-recovery ...--absent     vs .next-cockpit-recovery strong      12.5
        #   .next-cockpit-reading-clause-absent    vs .next-cockpit-reading-clause       12.5
        #   .next-cockpit-recovery goal --absent   vs ... .next-project-goal-text        12.5
        self.assertEqual(
            {
                ".next-project-value--absent": 12.5,
                ".next-cockpit-recovery .next-project-value--absent": 12.5,
                ".next-cockpit-reading-clause-absent": 12.5,
                ".next-cockpit-recovery .next-project-goal-text.next-project-value--absent,\n"
                ".next-cockpit-recovery .next-project-goal-gap": 12.5,
            },
            below,
        )
        known = [
            decls for selector, decls in _rules(css) if selector == ".next-project-value--known"
        ]
        self.assertEqual(1, len(known))
        self.assertIsNone(_declared_size(known[0], tokens))

    def test_a_mono_absence_is_caught(self) -> None:
        """Mutation: the reading clause's `var(--sans)` -> `var(--mono)`.

        Family is how an absence is told from a value here, because DRC-4589's
        ruling keeps both on `--ink3`; an absence that took mono would read as a
        string a source published.
        """
        css = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        # The shorthand as this lineage spells it. The branch this test came
        # from read `font:500 var(--fs-sentence)/1.55`, which is the pre-squash
        # DRC-4587 tree; the narrower #361 that merged left this rule on
        # `--fs-xs`, and a mutation string that matches nothing is a mutation
        # test that proves nothing.
        mutant = css.replace(
            ".next-cockpit-reading-clause-absent{font:var(--fs-xs)/1.5 var(--sans)",
            ".next-cockpit-reading-clause-absent{font:var(--fs-xs)/1.5 var(--mono)",
            1,
        )
        self.assertNotEqual(css, mutant)
        self.assertEqual(0, sum(1 for _, decls in _absence_rules(css) if _is_mono(decls)))
        self.assertEqual(1, sum(1 for _, decls in _absence_rules(mutant) if _is_mono(decls)))

    def test_every_rule_colouring_a_withheld_element_keeps_the_absence_ink(self) -> None:
        """DRC-4589's ink ruling, stated as the property rather than as a count.

        The criterion was drafted as "exactly one rule colours
        `[data-next-withheld]`", on the reading that the second such rule's
        `color:var(--ink3)` was redundant with the first. Measured, it is not:
        `.next-cockpit-scope-tree small` sets `color:var(--ink2)` at (0,1,1) and
        beats the bare `[data-next-withheld]` at (0,1,0), so the (0,2,1) rule is
        the only thing holding those withheld smalls on `--ink3`. Dropping it
        would turn them ink2 and break the ruling it was meant to serve. The
        falsifiable property underneath is asserted instead.
        """
        css = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        coloured = [
            (selector, decls)
            for selector, decls in _rules(css)
            if "[data-next-withheld]" in selector and "color:" in decls
        ]
        self.assertEqual(2, len(coloured))
        for selector, decls in coloured:
            with self.subTest(selector=selector):
                # The register rather than the literal, since DRC-4589 made it
                # the single place the ruling can be re-read from.
                self.assertEqual(["var(--ink-absence)"], re.findall(r"color:\s*([^;]+)", decls))

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

    def test_the_rail_card_puts_the_title_above_its_meta_in_two_registers(self) -> None:
        """DRC-4597 AC-1 and AC-4. The title is the card's value and the meta is
        the caption beneath it; a withheld title swaps the family and the ink
        and never the size.
        """
        styles = frontend_page.asset_path("styles.css").read_text(encoding="utf-8")
        title = re.search(r"\.next-cockpit-scope-title\{([^}]*)\}", styles)
        meta = re.search(r"\.next-cockpit-scope-meta\{([^}]*)\}", styles)
        self.assertIsNotNone(title)
        self.assertIsNotNone(meta)
        title_body = title.group(1) if title else ""
        meta_body = meta.group(1) if meta else ""
        self.assertIn("font:var(--fs-sm) var(--mono)", title_body)
        self.assertIn("color:var(--ink)", title_body)
        # One clipped line. `white-space:normal` from the rail's own reset is
        # the rule this has to beat, and the reset no longer selects a bare
        # `span` inside the link, so nothing overrides it at equal specificity.
        self.assertIn("text-overflow:ellipsis", title_body)
        self.assertIn("white-space:nowrap", title_body)
        self.assertIn("font:var(--fs-2xs) var(--mono)", meta_body)
        self.assertIn("color:var(--ink3)", meta_body)
        self.assertNotIn(
            ".next-cockpit-scope-tree span,", styles, "a bare span reset would unclip the title"
        )
        self.assertNotIn(".next-cockpit-scope-name{", styles)
        mark = re.search(r"\.next-cockpit-scope-mark:before\{([^}]*)\}", styles)
        self.assertIsNotNone(mark)
        self.assertIn("border-top:1px solid", mark.group(1) if mark else "")

    def test_the_tab_cue_never_renders_an_absence_larger_than_its_figure(self) -> None:
        """DRC-4592 AC-4 and AC-5. Both branches of the cue's state ternary
        resolve here; the pair is never on screen at one moment, so only the
        stylesheet can be asked whether they agree.
        """
        styles = frontend_page.asset_path("styles.css").read_text(encoding="utf-8")
        sizes = {}
        for selector in (
            ".next-cockpit-tab-cue",
            ".next-cockpit-tab-cue--pending",
            ".next-cockpit-tab-cue--unobserved",
        ):
            block = re.search(re.escape(selector) + r"\{([^}]*)\}", styles)
            self.assertIsNotNone(block, f"{selector} declares no rule of its own")
            body = block.group(1) if block else ""
            token = re.search(r"font:(?:\d+ )?var\(--(fs-[a-z0-9-]+)\)", body)
            self.assertIsNotNone(token, f"{selector} declares no size, so it inherits one")
            sizes[selector] = token.group(1) if token else ""
        self.assertEqual(1, len(set(sizes.values())), f"the cue states disagree on size: {sizes}")
        lede = re.search(r"\.next-cockpit-lede\{([^}]*)\}", styles)
        self.assertIsNotNone(lede)
        self.assertIn("font:var(--fs-sentence)/1.55 var(--sans)", lede.group(1) if lede else "")
        self.assertIn("color:var(--ink2)", lede.group(1) if lede else "")
        define = re.search(r"\.next-cockpit-define\{([^}]*)\}", styles)
        self.assertIsNotNone(define)
        # 500 weight, matching `.next-cockpit-reading-why`: a definition sits in
        # the same register as the caveats it stands beside, not a fourth one.
        self.assertIn(
            "font:500 var(--fs-sentence)/1.55 var(--sans)", define.group(1) if define else ""
        )

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
                27_384,
                "fe0b85a5f87537ce7e1a2a7d8aafaefca675810dff894412530ac9419147df8c",
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
                11_104,
                "2fdc43bbb9382ce92fe972d628b6bf11e0342f35bfa43e9965133c3315b39ad1",
            ),
            "next-cockpit-compat.js": (
                599,
                "ebc70801be79cd5805a85a281dd0566a08a97bab72d0356ae923d20f60310db4",
            ),
            "project.js": (
                109_267,
                "d1f78af91a95d78c71ddfa2f6cfbb985cab7818ad8f9a0452a2a129db4dd2a5f",
            ),
            "next-chrome.js": (
                40_141,
                "fd944ba159be6655d8e0fa8097a22288f7f1042d74c2146bfe1e617a07c70982",
            ),
            "next-capacity.js": (
                32_221,
                "152eeff23367e7216a500593f07acee293c1bfa1b38401befd173a12d462d835",
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
                14_536,
                "48db57de6b518a4c52ceffff7b7f9e9d9a15725670a1cc57aab2c20e03448478",
            ),
            "next-controls.js": (
                18_840,
                "f580b09c634f7a7c2f60584f5fca486a3a28e6fee43ff8152f90e08fc432eed4",
            ),
            "next-cockpit.js": (
                224_110,
                "60f187a139265c87ca37a388db29d854ef0a1206a7db62a658f82b1f032ce008",
            ),
            "next-render.js": (
                8_960,
                "16b2d560b446d47a1bd6d25864705ddce8563076dc26e9abb51f939b7b25860e",
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
        self.assertEqual(120_747, len(styles))
        self.assertEqual(
            "787c0a30fe5859a450e2e6ebb6825acc0f7fe61c7774d21c0a6281f07c38d2dc",
            hashlib.sha256(styles).hexdigest(),
        )

        assembled = frontend_page.load_page()
        self.assertEqual(953_271, len(assembled))
        self.assertEqual(
            "d8ff9423ff1c258fa60b5bb7b1badd1a638a846aa6f19b9a4b6593d1ba9cd4e6",
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


class TheBoardHasOneControlPrimitiveTest(unittest.TestCase):
    """DRC-4590. The stylesheet had no way to say "this one": no shared control
    class and no radius token, so every control was its own recipe and the whole
    range was spent on the secondary tier.

    The sweep that produced this issue found 24 resting control rules over six
    corner treatments. Seven collapse here; the remaining five are filed as
    their own issue and the exempt ones are named with reasons in the sheet, so
    AC-1 and AC-2 are accepted on these enumerated verifiers rather than on a
    universal reading neither could satisfy.
    """

    # The seven the primitive absorbs. Enumerated rather than discovered,
    # because "every control rule" is the claim this issue cannot make.
    COLLAPSED = (
        ".next-notify-button",
        ".next-stalled button",
        ".next-session-copy",
        ".next-steer button",
        ".next-guardrail-add",
        ".next-usage-switch button",
        ".next-cockpit-reading button",
    )

    def setUp(self) -> None:
        raw = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        # Comments out first. They carry commas and selector-shaped text, and
        # a selector head read straight out of the source picks up whatever
        # comment precedes the rule -- which matches nothing and reads as a
        # missing rule rather than as a broken parser.
        self.styles = re.sub(r"/\*.*?\*/", "", raw, flags=re.DOTALL)

    def rule(self, selector: str) -> str:
        """The body of the rule whose selector list contains `selector` exactly.

        Matched on the whole comma-separated head, so `.next-steer button` does
        not silently answer with `.next-steer button:hover`.
        """
        for block in re.finditer(r"([^{}]+)\{([^{}]*)\}", self.styles):
            heads = [head.strip() for head in block.group(1).split(",")]
            if selector in heads:
                return block.group(2)
        return ""

    def test_one_token_and_one_class_own_the_resting_box(self) -> None:
        """AC-1."""
        root = re.findall(r"(?:\A|\n):root\{([^}]*)\}", self.styles, re.DOTALL)
        self.assertTrue(any("--radius-control:" in block for block in root))
        # Exactly one rule owns `.next-action` on its own, so the primitive has
        # a single definition rather than a definition per caller.
        owners = [
            block.group(1).strip()
            for block in re.finditer(r"([^{}]+)\{[^{}]*\}", self.styles)
            if block.group(1).strip() == ".next-action"
        ]
        self.assertEqual(1, len(owners))
        body = self.rule(".next-action")
        self.assertIn("border-radius:var(--radius-control)", body)

    def test_no_collapsed_rule_keeps_its_own_recipe(self) -> None:
        """AC-1's falsifier: the collapse done by adding the class to a
        selector group, leaving the duplicated declarations in place. That
        reads as passing in a grep for the class name and changes nothing."""
        for selector in self.COLLAPSED:
            with self.subTest(selector=selector):
                body = self.rule(selector)
                self.assertNotEqual("", body, f"{selector} has no rule to check")
                self.assertNotIn("border-radius:", body)
                self.assertNotRegex(body, r"(?:^|;)border:1px")

    def test_a_disabled_control_survives_greyscale(self) -> None:
        """AC-3. Ink alone cannot carry this: `--ink3` is the resting colour of
        the prose around these controls, so a disabled one was drawn in the
        body ink and vanished with colour removed."""
        body = self.rule('.next-action[aria-disabled="true"]')
        self.assertIn("border-style:dashed", body)
        self.assertIn("cursor:not-allowed", body)
        # The stalled control is waiting, not refusing, and says so with its
        # own cursor. Collapsing the two loses a distinction a reader acts on.
        stalled = self.rule(".next-stalled button:disabled")
        self.assertIn("cursor:wait", stalled)
        # And it does not inherit the refusal's border either. Dashed is the
        # register for a control refusing a press; this one is waiting for a
        # retry it makes itself, so it states `solid` rather than letting the
        # primitive say the wrong thing about the state. Without this the
        # cursor and the border disagree about what the control is doing.
        self.assertIn("border-style:solid", stalled)
        self.assertGreater(
            self.styles.index(".next-stalled button:disabled"),
            self.styles.index('.next-action[aria-disabled="true"]'),
            "the stalled override must come after the primitive to win at equal specificity",
        )

    def test_the_tripwire_control_gets_the_box_its_hit_area_already_had(self) -> None:
        """AC-4. It was given the shared outlined recipe and stripped of it on
        the next line, so it read as a line of prose inside a 44px target: what
        a reader can see and what they can hit did not agree."""
        body = self.rule(".next-guardrail-add")
        self.assertNotEqual("", body)
        self.assertNotRegex(body, r"(?:^|;)border:0")
        self.assertNotRegex(body, r"(?:^|;)padding:0")
        # The 44px band is inherited rather than redeclared, from the one rule
        # that owns it for every control on the board.
        self.assertIn("min-block-size:44px", self.rule("#app a"))

    def test_the_irreversible_control_is_heavier_than_the_reversible_one(self) -> None:
        """AC-5. `clear` drops one unsaved box and `discard everything` deletes
        every revision, and the two carried the same five declarations."""
        discard = self.rule(".next-cockpit-held-discard button")
        armed = self.rule(".next-cockpit-held-discard button[aria-describedby]")
        self.assertNotEqual("", armed)
        # Width, not hue. The comment above these rules already rules colour
        # out here: `--clay` reads as an observation about the session, and
        # this is a control.
        self.assertRegex(armed, r"border-width:\d")
        block = self.styles[self.styles.index(".next-cockpit-held-discard") :][:800]
        for hue in ("--clay", "--amber", "--accent"):
            with self.subTest(hue=hue):
                self.assertNotIn(hue, block)
        # And the per-field `clear` stays bare text, which is what makes the
        # weight difference read at all. Boxing both removes the contrast this
        # criterion exists for.
        self.assertRegex(self.rule(".next-cockpit-held-field button"), r"(?:^|;)border:0")
        # The discard control takes its box from the primitive, so its own
        # rule no longer contradicts it with a borderless recipe.
        self.assertNotRegex(discard, r"(?:^|;)border:0")
        self.assertNotIn("border-radius:", discard)

    def test_the_dead_tab_strip_class_is_gone_and_its_neighbours_are_not(self) -> None:
        """AC-6. `.next-tabs` has zero references in every `.js`, `.py` and
        `.html` in the repository, but it survives in two shared selector
        groups carrying live classes -- so a line range deletes live rules."""
        self.assertEqual([], re.findall(r"\.next-tabs[^-\w]", self.styles))
        # The four live classes still resolve what they shared with it.
        self.assertIn("display:flex", self.rule(".next-header"))
        self.assertIn("display:flex", self.rule(".next-tabs-row"))
        self.assertIn("display:flex", self.rule(".next-header-right"))
        self.assertRegex(self.rule(".next-crumb"), r"(?:^|;)border:0")
        self.assertRegex(self.rule(".next-menu button"), r"(?:^|;)border:0")


class InkRoleRegistersAreDeclaredOnceAndSpelledNowhereElseTest(unittest.TestCase):
    """DRC-4589 AC-1, AC-3 and AC-6.

    One ink carried label, value, absence and caption. Twenty-one cockpit and
    session label rules each spelled `var(--ink3)` in their own declaration
    block, so moving the label tier meant editing twenty-one rules by hand and
    hoping none of them was a value.

    The registers are what make the next move one line. Nothing here asserts a
    colour changed, because none did: `--ink-label` and `--ink-absence` both
    resolve to `--ink3` under the captain's ruling of 2026-09-17, and
    `--ink-value` to `--ink`. What is asserted is that the indirection exists,
    that no rule bypasses it, and that the four registers live in the one
    `:root` the asset test admits.
    """

    REGISTERS = ("--ink-label", "--ink-value", "--ink-absence", "--ink-caption")

    def setUp(self) -> None:
        raw = (frontend_page.WEB_DIR / "styles.css").read_text(encoding="utf-8")
        self.styles = re.sub(r"/\*.*?\*/", "", raw, flags=re.DOTALL)

    def test_the_four_registers_are_declared_in_the_one_root_block(self) -> None:
        roots = re.findall(r"(?:\A|\n):root\{([^}]*)\}", self.styles, re.DOTALL)
        self.assertEqual(1, len(roots), "a second :root fails the asset test's palette assertion")
        for register in self.REGISTERS:
            with self.subTest(register=register):
                self.assertIn(f"{register}:var(--ink", roots[0])

    def test_no_label_rule_spells_an_ink_token_in_its_own_block(self) -> None:
        """AC-1's oracle, which returned 21 on the tree this branch forked from
        and must return 0. It reads whole declaration blocks, so a rule that
        sets the label size and its own `--ink3` in one block is what fails it.
        """
        offenders = [
            line
            for line in self.styles.splitlines()
            if re.match(r"\.next-(cockpit|session)[^{]*\{[^}]*var\(--fs-label\)", line)
            and "var(--ink3)" in line
        ]
        self.assertEqual([], offenders)

    def test_every_rule_colouring_a_withheld_value_uses_the_absence_register(self) -> None:
        """AC-3 restated as the property rather than as a count.

        It was drafted as "exactly one rule colours `[data-next-withheld]`", on
        the reading that the scope-rail override's colour merely restated the
        base rule, and the captain ruled the override keeps only its family
        swap. DRC-4597 then moved the attribute off a `<small>` and onto
        `span.next-cockpit-scope-title`, which declares `color:var(--ink)` at
        the same (0,1,0) specificity and later in the sheet. On that tree the
        override is the only thing holding a withheld title on the absence
        register, and stripping it rendered an absent title in FULL ink,
        identical to a published one -- the inversion this milestone exists to
        remove. A count could not see that; the register can, and
        `WithheldTitleKeepsTheAbsenceInkTest` resolves the pair through the
        cascade.
        """
        colouring = [
            line
            for line in self.styles.splitlines()
            if re.search(r"data-next-withheld[^{]*\{[^}]*color:", line)
        ]
        self.assertNotEqual([], colouring)
        for line in colouring:
            with self.subTest(rule=line[:60]):
                self.assertIn("var(--ink-absence)", line)
                self.assertNotIn("var(--ink3)", line)

    def test_every_absent_variant_resolves_through_the_absence_register(self) -> None:
        """No `--absent` or `-clause-absent` rule may set an ink token directly:
        the register is the single place the ruling can be re-read from.
        """
        for block in re.finditer(r"([^{}]+)\{([^{}]*)\}", self.styles):
            head, body = block.group(1).strip(), block.group(2)
            if "--absent" not in head and "-clause-absent" not in head:
                continue
            if "color:" not in body:
                continue
            with self.subTest(selector=head):
                self.assertIn("var(--ink-absence)", body)
                self.assertNotIn("var(--ink3)", body)


if __name__ == "__main__":
    unittest.main()
