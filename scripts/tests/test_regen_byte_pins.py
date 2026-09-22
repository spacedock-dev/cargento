"""The round trip DRC-4605 asks for: rewrite exactly what moved, and nothing else.

Every check here runs against a COPY of the tree. Running against the real one
would leave the repository dirty whenever an assertion failed, and the failure
this module is most likely to catch is a script that rewrites too much.

`frontend_page.WEB_DIR` is patched rather than passed, because `load_page()`
reads it through a module global and cannot take a root. Reimplementing the
assembly to make it parameterisable was rejected: a second copy of the assembly
is a second thing to drift, and the pins exist to catch drift.
"""

from __future__ import annotations

import base64
import hashlib
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cargento/skills/cargento"))

import regen_byte_pins
from cargento_runtime.web import page as frontend_page

REPO = Path(__file__).resolve().parents[2]
PINNED = ("test_next_page.py", "test_next_flag.py", "test_focus.py")


class RegenRoundTripTest(unittest.TestCase):
    """A one-asset edit moves a known set of figures. Anything else is a defect."""

    # A one-asset edit is never one pair. The asset feeds the assembled page as
    # well as its own row, and the assembled figures are spread across all three
    # files as two lengths and three digests. Seven figures, and the narrow
    # reading of "the asset's pair" is what DRC-4605 warns kills the falsifier.
    ASSEMBLED: ClassVar[frozenset[tuple[str, str]]] = frozenset(
        {
            ("test_next_page.py", "assembled length"),
            ("test_next_page.py", "assembled digest"),
            ("test_next_flag.py", "assembled length"),
            ("test_next_flag.py", "assembled digest"),
            ("test_focus.py", "assembled digest"),
        }
    )

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.web = root / "web"
        shutil.copytree(frontend_page.WEB_DIR, self.web)
        self.tests = root / "tests"
        self.tests.mkdir()
        for name in PINNED:
            shutil.copy(REPO / "cargento/skills/cargento/tests" / name, self.tests / name)
        patcher = mock.patch.object(frontend_page, "WEB_DIR", self.web)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _paths(self) -> list[Path]:
        return [self.tests / name for name in PINNED]

    def _run(self, *, check: bool = False) -> set[tuple[str, str]]:
        changes = regen_byte_pins.regenerate(self._paths(), check=check)
        return {(c.path.name, c.what) for c in changes}

    def test_an_unchanged_tree_rewrites_nothing(self) -> None:
        before = {p.name: p.read_bytes() for p in self._paths()}
        self.assertEqual(set(), self._run())
        self.assertEqual(before, {p.name: p.read_bytes() for p in self._paths()})

    def test_one_script_part_moves_its_own_pair_and_the_assembled_figures(self) -> None:
        (self.web / "next-live.js").write_text(
            (self.web / "next-live.js").read_text(encoding="utf-8") + "\n// edited\n",
            encoding="utf-8",
        )
        self.assertEqual(
            {
                ("test_next_page.py", "next-live.js size"),
                ("test_next_page.py", "next-live.js digest"),
            }
            | self.ASSEMBLED,
            self._run(),
        )

    def test_styles_moves_its_scalars_and_is_not_skipped_for_being_a_different_shape(self) -> None:
        """`styles.css` is two bare assertEquals, not a table row.

        A script that walks table rows skips it in silence, which is the second
        of the two hazards this issue's own description does not name.
        """
        (self.web / "styles.css").write_text(
            (self.web / "styles.css").read_text(encoding="utf-8") + "\n/* edited */\n",
            encoding="utf-8",
        )
        self.assertEqual(
            {("test_next_page.py", "styles.css size"), ("test_next_page.py", "styles.css digest")}
            | self.ASSEMBLED,
            self._run(),
        )

    def test_a_font_is_pinned_on_its_payload_and_not_on_the_file_that_carries_it(self) -> None:
        """The hazard worth the whole script, and it is not the one I first wrote down.

        `expected_fonts` is the only table that pins something other than the
        file's own bytes: it pins the base64-DECODED payload. For
        `ibm-plex-mono-v20-italic-latin` that is 11,568 bytes against a 15,627
        byte file. A script that reads raw bytes for every table writes real,
        plausible, wrong numbers into 15 entries, and both are genuine sha256s
        of genuine bytes so nothing looks off.

        Re-wrapping the base64 at a different line width is the clean probe: the
        FILE changes, the PAYLOAD does not, and the assembled page does not
        either because `load_styles` joins the lines before embedding them. A
        raw-bytes script moves 15 figures here. A correct one moves none.
        """
        name = "fonts/ibm-plex-mono-v20-italic-latin.woff2.b64"
        asset = self.web / name
        payload = base64.b64decode(
            "".join(asset.read_text(encoding="ascii").splitlines()), validate=True
        )
        rewrapped = base64.b64encode(payload).decode("ascii")
        asset.write_text("\n".join(re.findall(".{1,60}", rewrapped)) + "\n", encoding="ascii")
        self.assertNotEqual(len(asset.read_bytes()), len(payload))

        self.assertEqual(
            set(), self._run(), "a font rewrap moved a pin; the file was read, not the payload"
        )

        page = (self.tests / "test_next_page.py").read_text(encoding="utf-8")
        self.assertIn(hashlib.sha256(payload).hexdigest(), page)
        self.assertNotIn(hashlib.sha256(asset.read_bytes()).hexdigest(), page)

    def test_a_table_that_mimics_a_pin_row_without_being_one_is_not_reported(self) -> None:
        """`expected_faces` maps each font to its template slot and unicode range.

        Its rows are `"name": (` followed by two values, which is the pin shape
        from the outside. It carries no digest. A guard that looks for
        unaccounted TUPLES reports 15 phantom gaps on a clean tree and gets
        deleted for crying wolf; this one looks for unaccounted PINS.

        Recorded as a test because it cost two wrong counts before it was
        understood -- once in a throwaway script, once in the analysis that
        proposed this one.
        """
        self.assertEqual(set(), self._run())

    def test_check_mode_reports_without_writing(self) -> None:
        (self.web / "next-live.js").write_text(
            (self.web / "next-live.js").read_text(encoding="utf-8") + "\n// edited\n",
            encoding="utf-8",
        )
        before = {p.name: p.read_bytes() for p in self._paths()}
        self.assertNotEqual(set(), self._run(check=True))
        self.assertEqual(before, {p.name: p.read_bytes() for p in self._paths()})

    def test_the_rewrite_it_produces_actually_satisfies_the_suite(self) -> None:
        """The check the others cannot make: are the figures RIGHT, not just moved?

        Every assertion above compares what the script says it did. This one
        reads the numbers back out of the rewritten file and re-derives them from
        the assets, which is the only way a wrong-but-consistent script is caught.
        """
        (self.web / "next-live.js").write_text(
            (self.web / "next-live.js").read_text(encoding="utf-8") + "\n// edited\n",
            encoding="utf-8",
        )
        self._run()
        page = (self.tests / "test_next_page.py").read_text(encoding="utf-8")
        data = (self.web / "next-live.js").read_bytes()
        self.assertIn(hashlib.sha256(data).hexdigest(), page)
        assembled = frontend_page.load_page()
        for path in self._paths():
            text = path.read_text(encoding="utf-8")
            if "assembled" in text or "len(page)" in text:
                self.assertIn(hashlib.sha256(assembled).hexdigest(), text)
