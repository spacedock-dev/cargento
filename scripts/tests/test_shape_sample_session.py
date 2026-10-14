"""The illustration edits: what they change in the record, and that they refuse to do nothing."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import shape_sample_session as sh


def session() -> list[dict[str, Any]]:
    return [
        {
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "t1",
                        "input": {"command": "python3 -m unittest a.B.c -v 2>&1 | tail -20"},
                    }
                ]
            }
        },
        {
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "t1", "content": "FAILED (failures=1)"}
                ]
            },
            "toolUseResult": {"stdout": "FAILED (failures=1)"},
        },
        {
            "message": {
                "content": [
                    {"type": "tool_use", "id": "t2", "input": {"command": "ruff check . | tail -3"}}
                ]
            }
        },
    ]


EDIT = {
    "command_contains": "unittest a.B.c",
    "replace": [" 2>&1 | tail -20", " 2>&1"],
    "exit_code": 1,
}


class ShapeTest(unittest.TestCase):
    def test_a_failed_run_is_recorded_the_way_claude_code_records_one(self) -> None:
        records = session()
        sh.shape(records, [EDIT])
        use = records[0]["message"]["content"][0]
        result = records[1]["message"]["content"][0]
        self.assertEqual("python3 -m unittest a.B.c -v 2>&1", use["input"]["command"])
        self.assertIs(result["is_error"], True)
        self.assertTrue(result["content"].startswith("Exit code 1\n"))
        self.assertTrue(str(records[1]["toolUseResult"]).startswith("Error: Exit code 1"))

    def test_no_other_command_is_touched(self) -> None:
        records = session()
        sh.shape(records, [EDIT])
        self.assertEqual(
            "ruff check . | tail -3", records[2]["message"]["content"][0]["input"]["command"]
        )

    def test_an_edit_that_matches_nothing_or_twice_refuses(self) -> None:
        with self.assertRaises(SystemExit):
            sh.shape(session(), [{**EDIT, "command_contains": "no such command"}])
        twice = session() + session()
        with self.assertRaises(SystemExit):
            sh.shape(twice, [EDIT])

    def test_an_edit_whose_replacement_is_missing_refuses(self) -> None:
        with self.assertRaises(SystemExit):
            sh.shape(session(), [{**EDIT, "replace": [" | head -9", ""]}])


if __name__ == "__main__":
    unittest.main()
