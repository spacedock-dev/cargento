"""The migration inventory cannot silently lose an owner, a contract or an oracle."""

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
        storage = self.root / "frontend/src/storage"
        storage.mkdir(parents=True)
        (storage / "keys.ts").write_text("const KEY = 'cargento.fixture.preference';\n")
        (self.root / "docs").mkdir()
        (self.root / "frontend/src").mkdir(exist_ok=True)
        (self.root / "frontend/src/one.ts").write_text("export function holdDraft() {}\n")
        (self.root / "docs/design-reader-state.md").write_text(
            "## The inventory\n\n| Reader state | Across a redraw | Where |\n"
            "|---|---|---|\n| Reader draft | Kept | `frontend/src/one.ts`: `holdDraft` |\n\n## Next\n"
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

    def test_a_part_row_still_needs_an_owner_a_contract_and_an_oracle(self) -> None:
        del self.inventory["parts"][0]["owner"]
        result = self.run_check()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("one.js", result.stderr)

    def test_a_new_reader_state_cannot_be_silently_forgotten(self) -> None:
        doc = self.root / "docs/design-reader-state.md"
        doc.write_text(
            doc.read_text().replace("\n\n## Next", "\n| Caret | Kept | one.ts |\n\n## Next")
        )
        result = self.run_check()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("Caret", result.stderr)

    def cite(self, where: str) -> subprocess.CompletedProcess[str]:
        doc = self.root / "docs/design-reader-state.md"
        original = doc.read_text()
        doc.write_text(original.replace("`frontend/src/one.ts`: `holdDraft`", where))
        try:
            return self.run_check()
        finally:
            doc.write_text(original)

    def test_a_cited_owner_file_that_is_gone_refuses_the_map(self) -> None:
        result = self.cite("`frontend/src/gone.ts`: `holdDraft`")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("owner frontend/src/gone.ts", result.stderr)

    def test_a_cited_owner_symbol_the_file_no_longer_names_refuses_the_map(self) -> None:
        result = self.cite("`frontend/src/one.ts`: `holdDraft`, `renamedAway`")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("renamedAway is not in the file", result.stderr)
        self.assertNotIn("holdDraft is not", result.stderr)

    def test_a_dotted_owner_symbol_needs_every_part_and_a_key_is_not_a_symbol(self) -> None:
        self.assertNotEqual(0, self.cite("`frontend/src/one.ts`: `holdDraft.nowhere`").returncode)
        self.assertEqual(
            0,
            self.cite("`frontend/src/one.ts`: `holdDraft`, `cargento.next.some-key`").returncode,
        )

    def test_a_new_persisted_preference_requires_a_format_contract(self) -> None:
        keys = self.root / "frontend/src/storage/keys.ts"
        keys.write_text(keys.read_text() + "const EXTRA = 'cargento.fixture.new';\n")
        result = self.run_check()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("cargento.fixture.new", result.stderr)

    def test_a_row_that_names_a_file_that_is_gone_refuses_the_map(self) -> None:
        (self.root / "tests/oracle.py").unlink()
        result = self.run_check()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("missing or outside oracle tests/oracle.py", result.stderr)

    def test_the_committed_inventory_names_no_file_that_does_not_exist(self) -> None:
        inventory = json.loads((ROOT / "scripts/frontend-migration.json").read_text())
        named = {
            oracle
            for group in ("parts", "surfaces", "routes", "reader_state", "storage")
            for row in inventory[group]
            for oracle in row["oracles"]
        }
        self.assertEqual([], sorted(name for name in named if not (ROOT / name).is_file()))

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
