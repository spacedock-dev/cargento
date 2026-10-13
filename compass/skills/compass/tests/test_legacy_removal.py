"""The temporary rename compatibility layer is gone and must not come back.

Until 1.0.0 every fallback to the pre-Compass names (`~/.cargento`, `CARGENTO_*`, `cargento-` state
files, `cargento.` browser storage keys) carried a marker comment so this test could find it. The
fallbacks were removed for 1.0.0; a marker found now is a new one, and the answer is to not add it.
"""

from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MARKER = "legacy-" + "cargento"
EXCLUDED = {Path(__file__).relative_to(ROOT).as_posix()}


def marked_lines() -> list[str]:
    git = shutil.which("git")
    if git is None:
        return []
    listed = subprocess.run(
        [git, "ls-files", "-z"], cwd=ROOT, capture_output=True, check=False
    ).stdout.decode()
    found: list[str] = []
    for name in sorted(filter(None, listed.split("\0"))):
        path = ROOT / name
        if name in EXCLUDED or not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            continue
        found.extend(f"{name}:{n}" for n, line in enumerate(lines, 1) if MARKER in line)
    return found


class LegacyRemovalTest(unittest.TestCase):
    def test_no_fallback_to_the_pre_compass_names_is_marked_or_kept(self) -> None:
        self.assertEqual([], marked_lines())


if __name__ == "__main__":
    unittest.main()
