"""The migration cannot silently leave a shipped part or reader state unowned."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
COMMAND = ROOT / "scripts" / "frontend_inventory.py"


class AMigrationMaintainerSeesAnUnownedContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        web = self.root / "cargento/skills/cargento/cargento_runtime/web"
        web.mkdir(parents=True)
        (web / "page.py").write_text('APP_PARTS: tuple[str, ...] = ("one.js",)\n')
        (web / "one.js").write_text('const KEY = "cargento.fixture.preference";\n')
        (self.root / "docs").mkdir()
        (self.root / "docs/design-reader-state.md").write_text(
            "## The inventory\n\n| Reader state | Across a redraw | Where |\n"
            "|---|---|---|\n| Reader draft | Kept | one.js |\n\n## Next\n"
        )
        (self.root / "tests").mkdir()
        (self.root / "tests/oracle.py").write_text("# fixture oracle\n")
        self.inventory: dict[str, Any] = {
            "schema": 1,
            "parts": [self.row("one.js")],
            "reader_state": [self.row("Reader draft", disposition="store-held")],
            "storage": [self.row("cargento.fixture.preference", format="string")],
            "surfaces": [self.row("Draft editor")],
            "routes": [self.row("Session permalink")],
        }

    @staticmethod
    def row(name: str, **extra: str) -> dict[str, object]:
        return {
            "name": name,
            "owner": "DRC-4823",
            "oracles": ["tests/oracle.py"],
            "contract": "The reader keeps their draft.",
            **extra,
        }

    def run_check(self) -> subprocess.CompletedProcess[str]:
        inventory = self.root / "inventory.json"
        inventory.write_text(json.dumps(self.inventory))
        return subprocess.run(
            [sys.executable, str(COMMAND), "--root", str(self.root), "--inventory", str(inventory)],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_a_complete_map_passes_without_loading_the_runtime(self) -> None:
        result = self.run_check()
        self.assertEqual(0, result.returncode, result.stderr)

    def test_a_new_script_part_requires_a_migration_owner(self) -> None:
        web = self.root / "cargento/skills/cargento/cargento_runtime/web"
        (web / "page.py").write_text('APP_PARTS = ("one.js", "two.js")\n')
        (web / "two.js").write_text("")
        result = self.run_check()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("two.js", result.stderr)

    def test_a_new_reader_state_cannot_be_silently_forgotten(self) -> None:
        doc = self.root / "docs/design-reader-state.md"
        doc.write_text(
            doc.read_text().replace("\n\n## Next", "\n| Caret | Kept | one.js |\n\n## Next")
        )
        result = self.run_check()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("Caret", result.stderr)

    def test_a_new_persisted_preference_requires_a_format_contract(self) -> None:
        source = self.root / "cargento/skills/cargento/cargento_runtime/web/one.js"
        source.write_text(source.read_text() + 'const EXTRA = "cargento.fixture.new";\n')
        result = self.run_check()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("cargento.fixture.new", result.stderr)

    def test_a_missing_behavioral_oracle_refuses_the_map(self) -> None:
        (self.root / "tests/oracle.py").unlink()
        result = self.run_check()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("oracle", result.stderr)

    def test_a_duplicate_owner_row_does_not_hide_a_missing_contract(self) -> None:
        self.inventory["parts"].append(self.row("one.js"))
        result = self.run_check()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("duplicate", result.stderr)

    def test_an_oracle_cannot_escape_the_checkout(self) -> None:
        self.inventory["parts"][0]["oracles"] = ["../outside.py"]
        result = self.run_check()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("outside", result.stderr)


if __name__ == "__main__":
    unittest.main()
