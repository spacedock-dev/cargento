from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from cargento_runtime import records
from cargento_runtime import turns as runtime_turns

from .support import make_runtime


class TurnStartTest(unittest.TestCase):
    @staticmethod
    def _record(second: int, *, payload: str = "x") -> dict[str, Any]:
        return {
            "type": "assistant",
            "timestamp": f"2026-01-01T00:00:{second:02d}Z",
            "message": {"content": payload},
        }

    @staticmethod
    def _write(path: Path, records_to_write: list[dict[str, Any]]) -> None:
        path.write_text(
            "".join(json.dumps(record) + "\n" for record in records_to_write),
            encoding="utf-8",
        )

    def test_a_zero_based_scan_records_the_first_timestamp(self) -> None:
        first = "2026-01-01T00:00:00Z"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.jsonl"
            self._write(path, [self._record(0), self._record(1)])
            config, state = make_runtime()
            scan = runtime_turns.scan_turns(config, state, str(path), "claude")

        assert scan is not None
        self.assertTrue({"first_ts", "scanned_from_zero"}.issubset(runtime_turns._RESULT_FIELDS))
        self.assertEqual(records.parse_ts(first), scan["first_ts"])
        self.assertTrue(scan["scanned_from_zero"])
        self.assertEqual(records.parse_ts(first), runtime_turns.started_at(scan))

    def test_first_sight_of_an_oversized_file_withholds_the_tail_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "oversized.jsonl"
            self._write(path, [self._record(second, payload="x" * 80) for second in range(10)])
            config, state = make_runtime(turn_scan_max_bytes=240)
            self.assertGreater(path.stat().st_size, config.turn_scan_max_bytes)
            scan = runtime_turns.scan_turns(config, state, str(path), "claude")

        assert scan is not None
        self.assertFalse(scan["scanned_from_zero"])
        self.assertIsNotNone(scan["first_ts"], "the tail still has a first parsed record")
        self.assertIsNone(runtime_turns.started_at(scan))

    def test_incremental_growth_past_the_bound_keeps_the_measured_start(self) -> None:
        first = "2026-01-01T00:00:00Z"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "growing.jsonl"
            self._write(path, [self._record(0)])
            config, state = make_runtime(turn_scan_max_bytes=240)
            scan = runtime_turns.scan_turns(config, state, str(path), "claude")
            for second in range(1, 10):
                with path.open("a", encoding="utf-8") as output:
                    output.write(json.dumps(self._record(second)) + "\n")
                scan = runtime_turns.scan_turns(config, state, str(path), "claude")

            self.assertGreater(path.stat().st_size, config.turn_scan_max_bytes)

        assert scan is not None
        self.assertTrue(scan["scanned_from_zero"])
        self.assertEqual(records.parse_ts(first), scan["first_ts"])
        self.assertEqual(records.parse_ts(first), runtime_turns.started_at(scan))

    def test_an_oversized_unscanned_delta_withholds_the_original_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "jump.jsonl"
            self._write(path, [self._record(0)])
            config, state = make_runtime(turn_scan_max_bytes=240)
            first = runtime_turns.scan_turns(config, state, str(path), "claude")
            with path.open("a", encoding="utf-8") as output:
                for second in range(1, 10):
                    output.write(json.dumps(self._record(second, payload="x" * 80)) + "\n")
            after = runtime_turns.scan_turns(config, state, str(path), "claude")

        assert first is not None
        assert after is not None
        self.assertIsNotNone(runtime_turns.started_at(first))
        self.assertFalse(after["scanned_from_zero"])
        self.assertIsNone(runtime_turns.started_at(after))

    def test_an_evicted_entry_withholds_rather_than_regressing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evicted.jsonl"
            self._write(path, [self._record(0)])
            config, state = make_runtime(turn_scan_max_bytes=240)
            before = runtime_turns.scan_turns(config, state, str(path), "claude")
            for second in range(1, 10):
                with path.open("a", encoding="utf-8") as output:
                    output.write(json.dumps(self._record(second)) + "\n")
                before = runtime_turns.scan_turns(config, state, str(path), "claude")
            state.turn_scan.pop(str(path))
            rebuilt = runtime_turns.scan_turns(config, state, str(path), "claude")

        assert before is not None
        assert rebuilt is not None
        self.assertIsNotNone(runtime_turns.started_at(before))
        self.assertFalse(rebuilt["scanned_from_zero"])
        self.assertIsNone(runtime_turns.started_at(rebuilt))


if __name__ == "__main__":
    unittest.main()
