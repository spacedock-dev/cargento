"""The sample-session sanitizer: what it replaces, what it must keep, and what it must refuse to ship.

Every value here is invented. The real mapping, which holds originals, lives outside the repository.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sanitize_session as ss

SALT = "test-salt"
UID = "11111111-2222-4333-8444-555555555555"
PARENT = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
CHILD = "99999999-8888-4777-8666-555555555555"
MAPPING = {
    "salt": SALT,
    "day_shift": -10,
    "time_shift_seconds": 3600,
    "ai_title": "A neutral title",
    "literals": [
        {
            "from": "/Users/pat/repos/zeta/atlas",
            "to": "/Users/dev/repos/acme/dashboard",
            "category": "path",
        },
        {"from": "/Users/pat", "to": "/Users/dev", "category": "home"},
        {"from": "Pat Example", "to": "Alex Doe", "category": "name"},
        {"from": "pat@zeta.io", "to": "dev@example.com", "category": "email"},
        {"from": "atlas", "to": "dashboard", "category": "project"},
        {"from": "zeta", "to": "acme", "category": "org", "word": True},
    ],
    "hashes": ["abc1234"],
    "numbers": ["41000000001"],
}


def records() -> list[dict[str, object]]:
    return [
        {
            "type": "user",
            "uuid": PARENT,
            "parentUuid": "00000000-0000-4000-8000-000000000000",
            "sessionId": UID,
            "cwd": "/Users/pat/repos/zeta/atlas",
            "timestamp": "2026-07-31T01:00:00.000Z",
            "message": {"role": "user", "content": "Fix atlas for Pat Example, mail pat@zeta.io"},
        },
        {
            "type": "assistant",
            "uuid": CHILD,
            "parentUuid": PARENT,
            "sessionId": UID,
            "timestamp": "2026-07-31T01:00:30.250Z",
            "message": {
                "role": "assistant",
                "id": "msg_0123456789abcdefghij",
                "content": [
                    {"type": "thinking", "thinking": "private thought", "signature": "x" * 40},
                    {
                        "type": "text",
                        "text": "Run ran on commit abc1234 in /Users/pat/repos/zeta/atlas/src",
                    },
                    {
                        "type": "tool_use",
                        "id": "toolu_ABCDEFGHIJKLMNOP",
                        "name": "Bash",
                        "input": {"command": "gh run view 41000000001 --repo zeta/atlas"},
                    },
                ],
            },
        },
        {
            "type": "user",
            "uuid": "bbbbbbbb-cccc-4ddd-8eee-ffffffffffff",
            "parentUuid": CHILD,
            "sessionId": UID,
            "timestamp": "2026-07-31T01:00:31Z",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_ABCDEFGHIJKLMNOP",
                        "content": json.dumps({"path": "/Users/pat/x", "owner": "Pat Example"}),
                    }
                ],
            },
        },
        {"type": "ai-title", "aiTitle": "An old title about atlas", "sessionId": UID},
    ]


class SanitizerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "in.jsonl"
        self.target = self.root / "out.jsonl"
        self.mapping_path = self.root / "mapping.json"
        self.source.write_text("".join(json.dumps(r) + "\n" for r in records()), encoding="utf-8")
        self.mapping_path.write_text(json.dumps(MAPPING), encoding="utf-8")
        self.mapping = ss.Mapping.load(self.mapping_path)

    def run_it(self) -> list[dict[str, object]]:
        ss.sanitize(self.mapping, self.source, self.target)
        return [json.loads(line) for line in self.target.read_text(encoding="utf-8").splitlines()]

    def test_a_replacement_is_the_same_everywhere_and_longest_first(self) -> None:
        out = self.run_it()
        text = self.target.read_text(encoding="utf-8")
        self.assertEqual("/Users/dev/repos/acme/dashboard", out[0]["cwd"])
        self.assertIn("Fix dashboard for Alex Doe, mail dev@example.com", text)
        self.assertIn("/Users/dev/repos/acme/dashboard/src", text)
        self.assertNotIn("atlas", text)
        self.assertNotIn("Pat Example", text)

    def test_a_word_only_entry_leaves_a_longer_word_alone(self) -> None:
        self.source.write_text(
            json.dumps({"type": "x", "text": "zeta and zetas and a zeta."}) + "\n", encoding="utf-8"
        )
        out = self.run_it()
        self.assertEqual("acme and zetas and a acme.", out[0]["text"])

    def test_ids_are_regenerated_consistently_so_chains_stay_linked(self) -> None:
        out = self.run_it()
        uuids = {r["uuid"] for r in out if "uuid" in r}
        self.assertEqual(3, len(uuids))
        self.assertNotIn(PARENT, uuids)
        self.assertEqual(out[0]["uuid"], out[1]["parentUuid"])
        self.assertEqual(out[1]["uuid"], out[2]["parentUuid"])
        self.assertEqual({out[0]["sessionId"]}, {r["sessionId"] for r in out if "sessionId" in r})
        use = out[1]["message"]["content"][1]  # type: ignore[index]
        result = out[2]["message"]["content"][0]  # type: ignore[index]
        self.assertEqual(use["id"], result["tool_use_id"])
        self.assertNotEqual("toolu_ABCDEFGHIJKLMNOP", use["id"])
        self.assertEqual(len("toolu_ABCDEFGHIJKLMNOP"), len(use["id"]))

    def test_the_same_input_gives_the_same_output_and_another_salt_gives_another(self) -> None:
        first = json.dumps(self.run_it())
        self.assertEqual(first, json.dumps(self.run_it()))
        self.mapping.salt = "another"
        self.assertNotEqual(first, json.dumps(self.run_it()))

    def test_a_string_that_holds_json_is_cleaned_inside_and_stays_valid_json(self) -> None:
        inner = self.run_it()[2]["message"]["content"][0]["content"]  # type: ignore[index]
        self.assertEqual({"path": "/Users/dev/x", "owner": "Alex Doe"}, json.loads(inner))

    def test_times_move_by_one_fixed_offset_so_gaps_survive(self) -> None:
        out = self.run_it()
        self.assertEqual("2026-07-21T02:00:00.000Z", out[0]["timestamp"])
        self.assertEqual("2026-07-21T02:00:30.250Z", out[1]["timestamp"])
        self.assertEqual("2026-07-21T02:00:31Z", out[2]["timestamp"])

    def test_thinking_blocks_are_dropped_and_the_record_stays(self) -> None:
        content = self.run_it()[1]["message"]["content"]  # type: ignore[index]
        self.assertEqual(["text", "tool_use"], [block["type"] for block in content])

    def test_commit_hashes_and_run_numbers_keep_their_length_and_change(self) -> None:
        text = self.target.read_text(encoding="utf-8") if self.run_it() else ""
        self.assertNotIn("abc1234", text)
        self.assertNotIn("41000000001", text)
        self.assertRegex(text, r"commit [0-9a-f]{7} in")
        self.assertRegex(text, r"run view \d{11} --repo")

    def test_numbers_from_one_run_stay_close_together(self) -> None:
        self.mapping.numbers = ["41000000001", "41000000048"]
        cleaner = ss.Sanitizer(self.mapping)
        a, b = int(cleaner.text("41000000001")), int(cleaner.text("41000000048"))
        self.assertEqual(47, b - a)

    def test_a_parent_that_the_cut_removed_becomes_null(self) -> None:
        out = self.run_it()
        self.assertIsNone(out[0]["parentUuid"])

    def test_the_title_is_replaced_when_the_mapping_names_one(self) -> None:
        self.assertEqual("A neutral title", self.run_it()[3]["aiTitle"])

    def test_any_other_email_home_and_secret_is_replaced_whatever_the_mapping_says(self) -> None:
        cleaner = ss.Sanitizer(self.mapping)
        text = cleaner.text(
            "mail someone@other.org at /Users/stranger/code with sk-abcdefghijklmnopqrstuv0123"
        )
        self.assertIn("user@example.com", text)
        self.assertIn("/Users/dev/code", text)
        self.assertIn("<REDACTED_TOKEN>", text)
        self.assertNotIn("stranger", text)

    def test_verification_passes_a_clean_output(self) -> None:
        self.run_it()
        self.assertEqual([], ss.verify(self.mapping, self.source, self.target))

    def test_verification_catches_a_leaked_original_in_every_form(self) -> None:
        self.run_it()
        for leak in ("Pat Example", "pat%20example", "PAT EXAMPLE"):
            with self.subTest(leak=leak):
                clean = self.target.read_text(encoding="utf-8")
                self.target.write_text(
                    clean + json.dumps({"type": "x", "t": leak}) + "\n", encoding="utf-8"
                )
                problems = ss.verify(self.mapping, self.source, self.target)
                self.assertTrue(any("original still present" in p for p in problems), problems)
                self.target.write_text(clean, encoding="utf-8")

    def test_verification_catches_a_broken_chain_and_a_lost_line(self) -> None:
        self.run_it()
        rows = [json.loads(line) for line in self.target.read_text(encoding="utf-8").splitlines()]
        rows[2]["parentUuid"] = "00000000-1111-4222-8333-444444444444"
        self.target.write_text("".join(json.dumps(r) + "\n" for r in rows[:3]), encoding="utf-8")
        problems = ss.verify(self.mapping, self.source, self.target)
        self.assertTrue(any("line count" in p for p in problems), problems)
        self.assertTrue(any("parentUuid" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
