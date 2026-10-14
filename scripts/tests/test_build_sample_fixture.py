"""The fixture builder's rewrites: they make a capture read the same on any day."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import build_sample_fixture as bf

CAPTURED = 1_790_000_000.0


class RewriteTest(unittest.TestCase):
    def test_a_time_near_the_capture_moves_and_a_far_one_does_not(self) -> None:
        moved = bf.shift_numbers({"near": CAPTURED - 60, "far": CAPTURED - 86400}, CAPTURED, 1000)
        self.assertEqual({"near": CAPTURED - 1060, "far": CAPTURED - 86400}, moved)

    def test_small_numbers_and_booleans_are_left_alone(self) -> None:
        node = {"count": 7, "flag": True, "nested": [3, {"n": 1.5}]}
        self.assertEqual(node, bf.shift_numbers(node, CAPTURED, 1000))

    def test_the_session_id_is_renamed_in_keys_and_values(self) -> None:
        node = {"f7352072": ["claude:f7352072", {"sid": "f7352072"}]}
        self.assertEqual(
            {"sample": ["claude:sample", {"sid": "sample"}]},
            bf.rename(node, "f7352072", "sample"),
        )

    def test_a_duration_reads_in_the_servers_short_form(self) -> None:
        self.assertEqual(
            ["45s", "11m", "2h 5m", "3d 4h"],
            [
                bf.fmt_duration(s)
                for s in (45, 11 * 60 + 20, 2 * 3600 + 5 * 60, 3 * 86400 + 4 * 3600)
            ],
        )

    def test_the_last_record_is_the_latest_fact_time(self) -> None:
        context = {"semantic": {"facts": [{"at": 5}, {"at": 9.5}, {"at": None}, {}]}}
        self.assertEqual(9.5, bf.last_record_time(context))


if __name__ == "__main__":
    unittest.main()
