from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, ClassVar

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import capture_team_registry as recorder


class TypeNameTest(unittest.TestCase):
    def test_a_type_is_reported_by_name_and_never_by_value(self) -> None:
        # The whole privacy property in one function: every branch returns a
        # type name, so no caller can get the value back by accident.
        cases: list[tuple[object, str]] = [
            (None, "null"),
            (True, "bool"),
            (3, "int"),
            (3.5, "float"),
            ("a prompt nobody should see", "string"),
            ([1, 2], "list"),
            ({"a": 1}, "object"),
            (object(), "unknown"),
        ]
        for value, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(expected, recorder.type_name(value))
        names = {recorder.type_name(value) for value, _ in cases}
        self.assertNotIn("a prompt nobody should see", names)

    def test_bool_is_not_reported_as_int(self) -> None:
        # `isinstance(True, int)` is true in Python, so the bool branch has to
        # come first or every liveness flag records as an int.
        self.assertEqual("bool", recorder.type_name(False))


class SaltedTest(unittest.TestCase):
    def test_a_store_path_is_recorded_as_a_salted_digest(self) -> None:
        # The README promises a digest rather than an identifier, and a reader
        # can only check that against a committed derivation.
        digest = recorder.salted("/Users/someone/.claude/teams/session-abcd1234/config.json")
        self.assertEqual(recorder.DIGEST_CHARS, len(digest))
        self.assertRegex(digest, r"^[0-9a-f]+$")
        self.assertNotIn("someone", digest)
        self.assertNotIn("abcd1234", digest)

    def test_the_digest_is_stable_and_path_dependent(self) -> None:
        self.assertEqual(recorder.salted("/a"), recorder.salted("/a"))
        self.assertNotEqual(recorder.salted("/a"), recorder.salted("/b"))


class RegistryShapeTest(unittest.TestCase):
    def test_a_member_field_is_recorded_by_name_and_its_prompt_is_not_read(self) -> None:
        # `prompt` is operator text. The recorder must name the field and never
        # carry what was in it.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "leadSessionId": "abcd1234",
                        "members": [
                            {
                                "agentId": "worker@session-abcd1234",
                                "name": "worker",
                                "backendType": "tmux",
                                "joinedAt": 1_700_000_000_000,
                                "isActive": False,
                                "prompt": "go and rewrite the billing module",
                            },
                            "not a member",
                        ],
                    }
                ),
                encoding="utf-8",
            )
            record = recorder.registry_shape(str(path), {"harness": "claude"})

        blob = json.dumps(record)
        self.assertNotIn("rewrite the billing module", blob)
        self.assertNotIn("worker", blob, "a member's name is not recorded either")
        self.assertIn("prompt", record["member_fields"], "the field is named")
        self.assertEqual(["string"], record["member_fields"]["prompt"])
        self.assertEqual(1, record["member_count"], "a non-dict member is skipped")
        self.assertEqual(
            {
                "backendType": "tmux",
                "isActive_present": True,
                "isActive": False,
                "joinedAt_type": "int",
            },
            record["members"][0],
        )


class HeaderShapeTest(unittest.TestCase):
    def test_the_first_timestamped_record_index_is_measured_not_assumed(self) -> None:
        # The measurement DRC-4344 rests on: a top-level transcript opens with
        # untimestamped control records, so the index is not 0.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.jsonl"
            path.write_text(
                "\n".join(
                    [
                        json.dumps({"type": "agent-setting"}),
                        json.dumps({"type": "mode"}),
                        json.dumps({"type": "permission-mode"}),
                        json.dumps({"type": "user", "timestamp": "2026-01-01T00:00:00Z"}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            shape = recorder.header_shape(str(path))

        self.assertEqual(3, shape["first_timestamped_record_index"])
        self.assertEqual(
            ["agent-setting", "mode", "permission-mode", "user"],
            shape["record_types_in_order"],
        )
        self.assertEqual(["string"], shape["header_fields"]["timestamp"])

    def test_a_malformed_line_is_recorded_as_an_unreadable_kind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.jsonl"
            path.write_text('not json\n["a list"]\n', encoding="utf-8")
            shape = recorder.header_shape(str(path))
        self.assertEqual([None, None], shape["record_types_in_order"])
        self.assertIsNone(shape["first_timestamped_record_index"])


class DriveArmTest(unittest.TestCase):
    PAYLOAD: ClassVar[dict[str, Any]] = {
        "sessions": [
            {
                "harness": "claude",
                "sid": "df15489c-0000",
                "state": "working",
                "state_detail": "running 1 subagent",
                "subagents": [
                    {
                        "name": "a-teammate",
                        "model": None,
                        "started_at": 1.0,
                        "active": True,
                        "parent": None,
                    },
                    {
                        "name": "its-worker",
                        "model": None,
                        "started_at": 2.0,
                        "active": True,
                        "parent": "a-teammate",
                    },
                    {
                        "name": "a-finished-one",
                        "model": None,
                        "started_at": 3.0,
                        "active": False,
                        "parent": None,
                    },
                ],
            }
        ]
    }

    def test_an_arm_records_arity_and_never_a_label(self) -> None:
        # Every label on a real board is a workflow identifier or a description
        # someone wrote, so none of them may reach the file.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "payload.json"
            path.write_text(json.dumps(self.PAYLOAD), encoding="utf-8")
            record = recorder.drive_arm(str(path), "positive", "df15489c", {"harness": "claude"})

        blob = json.dumps(record)
        for label in ("a-teammate", "its-worker", "a-finished-one"):
            self.assertNotIn(label, blob)
        self.assertEqual(3, record["published_total"])
        self.assertEqual(2, record["direct_children"])
        self.assertEqual(1, record["grandchildren"])
        self.assertEqual(1, record["distinct_parents_named"])
        self.assertEqual(2, record["active_true"])
        self.assertEqual(1, record["active_false"])
        self.assertEqual(3, record["published_with_a_measured_start"])
        self.assertTrue(record["element_keys_uniform"])
        self.assertEqual("running N subagents", record["state_detail_shape"])
        self.assertEqual(1, record["state_detail_subagent_count"])


class MainTest(unittest.TestCase):
    def test_drive_mode_writes_one_record_per_arm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = Path(tmp) / "payload.json"
            payload.write_text(json.dumps(DriveArmTest.PAYLOAD), encoding="utf-8")
            out = Path(tmp) / "nested" / "capture.jsonl"
            code = recorder.main(
                [
                    "drive",
                    "--lead",
                    "df15489c",
                    "--out",
                    str(out),
                    "--arm",
                    f"positive={payload}",
                    "--arm",
                    f"negative={payload}",
                ]
            )
            # Read inside the temporary directory's lifetime.
            written = out.read_text(encoding="utf-8").strip().splitlines()
            arms = [json.loads(line)["arm"] for line in written]

        self.assertEqual(0, code)
        # The output directory is created rather than required, so a first run works.
        self.assertEqual(["positive", "negative"], arms)

    def test_a_malformed_arm_is_refused_rather_than_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "capture.jsonl"
            with self.assertRaises(SystemExit):
                recorder.main(["drive", "--lead", "abcd1234", "--out", str(out), "--arm", "oops"])
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
