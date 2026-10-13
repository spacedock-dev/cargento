"""The previous interface's script parts are frozen except for the owner's rename.

The dashboard no longer ships or serves them; `scripts/frozen_page.py` loads them from
`scripts/frozen-page/` for the paused Intent and drift study. `scripts/drift_replay.py` evaluates
`frozen_page.load_script()` in `scripts/drift_page.js`, and the study (`docs/drift-replay/`) binds
the digest of that text into its ledger. A changed byte would unfreeze the study without a word and
only surface when it resumes, so each part and the concatenation are pinned here. If a part must
change beyond that rename, re-qualify it and re-pin these values together. The named test
projection preserves the historical pins; it does not certify the renamed study bytes.
"""

from __future__ import annotations

import hashlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import frozen_page


def original_product_name(text: str) -> str:
    """Restore only the three product-name spellings for historical hash checks.

    A test-only comparison with recorded bytes, never certification of the renamed producer or
    study source. Their live qualification still requires evidence.
    """
    return (
        text.replace("Compass", "Cargento")
        .replace("COMPASS", "CARGENTO")
        .replace("compass", "cargento")
    )


# Sizes and sha256 of each part, as the previous interface's own byte pins recorded them.
PARTS: dict[str, tuple[int, str]] = {
    "next-boot.js": (
        33_605,
        "6f715008874b7808b7603bebf64c645e911974ce3127797958cd608a5d344fef",
    ),
    "next-observed.js": (
        38_284,
        "8146b3f920969ab0e49ab692c9de0101f4cab9ae46b8f7b95614ecb7eaf14321",
    ),
    "next-attention.js": (
        56_867,
        "8ef7eb569ea810188a2acb7803d9b4f8fb2e28c68183fc98a66f3081d439d7cb",
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
        112_662,
        "81e7f6490f9d6c2e128549aff8bb54c2f6bebaec15b03bfebe3e057b4ef8f587",
    ),
    "next-chrome.js": (
        47_523,
        "7db3fd27ce6476497e6dfbc7787de2d3f37d5d4f47b5950c8059aa1907a72da7",
    ),
    "next-capacity.js": (
        32_261,
        "986a0b0d74771bbb9f1d9df520dbb6c91d5916685fe365a64eff61c29acab7cc",
    ),
    "next-sessions.js": (
        28_110,
        "cb1a2e1b55e77173db53f0de9259cdece48e8f6006eac6ce0f22a7bada3672bd",
    ),
    "next-projects.js": (
        5_829,
        "0324f6aebe951a37bde0f710c73c77f1007d26159a5b33e453b54711b4263348",
    ),
    "next-project.js": (
        22_222,
        "b53f885f953cdd9e36df772084e79dab54387bbcd6e3e3b8a754b2923f526152",
    ),
    "next-intent.js": (
        22_160,
        "f70dc642cbadb1895c5679eaa177aeca9f65fe5be3f95a566f41bd7c4fb19000",
    ),
    "next-activity.js": (
        6_467,
        "f44d5da254b7a6be30b05a4c03bfd83050608b0d9da35910c3e640a742c0e2cc",
    ),
    "next-session.js": (
        45_325,
        "be261ca408a7cc46e2ce23982628783e0f5516a10f19cfe75300e6c48233d0c7",
    ),
    "next-workstream.js": (
        18_659,
        "9680ee01d19296e87cf9b35230a51a7e98ddc764c5bfb80f0e18e7723ece8a04",
    ),
    "next-delegation.js": (
        12_735,
        "aa8e8ab3a5531e28ee08f555f901fd29d873aecd4bdd0e498199036efe16dfc2",
    ),
    "next-controls.js": (
        24_435,
        "9f571fa45f6a44c7365e247e23e7c59dc0931238e0c2f6d1f7e18791e3ede2b0",
    ),
    "next-cockpit.js": (
        544_135,
        "94f587ee211f3fcea35c584c8df90f28013a20c771ddd592a9d4143eeb85babb",
    ),
    "next-render.js": (
        17_875,
        "4321205e01ee774a3575df6f8c1ea3b5b4d7381b1cb19c469a3fb03d81e89c88",
    ),
    "next-live.js": (
        4_124,
        "33b82c3744091b3975a59ec77eae57c272993bd7fdf78a8a9bada64905f18ab9",
    ),
}
SCRIPT = (
    1084981,
    "392e3d83dee6d5bf504ff4f38fafac7c63d1dca0a2913284525cba4ea85a9fb9",
)
WHY = (
    "{name} is bound by the paused Intent and drift study (`frozen_page.load_script()` feeds "
    "`scripts/drift_page.js`, and its ledger binds the digest). Its bytes must not change; "
    "re-opening the study means re-qualifying it and re-pinning `scripts/tests/test_frozen_page.py`."
)


class TheStudyBoundPartsAreFrozenTest(unittest.TestCase):
    def test_the_part_list_and_order_are_the_studys(self) -> None:
        self.assertEqual(tuple(PARTS), frozen_page.APP_PARTS, WHY.format(name="APP_PARTS"))

    def test_each_part_keeps_its_size_and_digest(self) -> None:
        for name, (size, digest) in PARTS.items():
            with self.subTest(part=name):
                data = original_product_name(
                    (frozen_page.FROZEN_DIR / name).read_bytes().decode("utf-8")
                ).encode("utf-8")
                self.assertEqual(size, len(data), WHY.format(name=name))
                self.assertEqual(digest, hashlib.sha256(data).hexdigest(), WHY.format(name=name))

    def test_the_text_the_replay_evaluates_keeps_its_size_and_digest(self) -> None:
        script = original_product_name(frozen_page.load_script()).encode("utf-8")
        self.assertEqual(SCRIPT[0], len(script), WHY.format(name="load_script()"))
        self.assertEqual(
            SCRIPT[1], hashlib.sha256(script).hexdigest(), WHY.format(name="load_script()")
        )


class TheLoaderRefusesAnEmptyPartTest(unittest.TestCase):
    """`load_script` carries no integrity metadata, and an emptied part once served silently."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="compass-frozen-page-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(frozen_page.FROZEN_DIR, self.root, dirs_exist_ok=True)
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(frozen_page, "FROZEN_DIR", self.root).start()

    def test_the_untouched_copy_still_loads(self) -> None:
        self.assertTrue(frozen_page.load_script())

    def test_an_empty_or_blank_script_part_refuses_by_name(self) -> None:
        for name in frozen_page.APP_PARTS:
            for blank in ("", " \n\t\n"):
                with self.subTest(part=name, blank=blank):
                    original = (self.root / name).read_bytes()
                    (self.root / name).write_text(blank, encoding="utf-8")
                    try:
                        with self.assertRaisesRegex(RuntimeError, f"{name} is empty"):
                            frozen_page.load_script()
                    finally:
                        (self.root / name).write_bytes(original)


class TheDashboardNoLongerCarriesThemTest(unittest.TestCase):
    def test_no_part_remains_under_the_shipped_web_directory(self) -> None:
        web = Path(__file__).resolve().parents[2] / "compass/skills/compass/compass_runtime/web"
        for name in frozen_page.APP_PARTS:
            with self.subTest(part=name):
                self.assertFalse((web / name).exists())


if __name__ == "__main__":
    unittest.main()
