"""The migration inventory follows shipped behavior throughout the refactor."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


class AContributorCannotForgetAnExistingReaderContractTest(unittest.TestCase):
    def test_every_shipped_part_and_reader_state_has_a_migration_owner(self) -> None:
        # Keep this dependency visible to the docs-only gate's literal inventory.
        self.assertTrue((ROOT / "docs/design-reader-state.md").is_file())
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/frontend_inventory.py")],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
