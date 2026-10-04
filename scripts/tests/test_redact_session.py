"""The session redactor: what it hides, and what it must keep so a replay still reads the same.

Every name here is invented. The real names live in a local config the repository never holds.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import redact_session as rs

CONFIG = {
    "v": 1,
    "home_user_prefix": "pat",
    "repository_under_home": "repos/acme/cargento",
    "self_tag": "NAME_1",
    "names": [
        {"pattern": "Pat Example|\\bPat\\b|patex", "tag": "NAME_1"},
        {"pattern": "\\bKQ\\b", "tag": "NAME_2", "case_sensitive": True},
    ],
    "orgs": [{"pattern": "Acme", "tag": "ORG_NAME_1"}],
    "places": ["Springfield"],
}


def _redactor(literals: tuple[str, ...] = ()) -> rs.Redactor:
    return rs.Redactor(rs.Config(CONFIG), literals)


class WhatIsHidden(unittest.TestCase):
    def test_names_orgs_places_emails_and_time_zones(self) -> None:
        got = _redactor().text("Pat Example (pat@acme.io) at Acme in Springfield, 9am CST. ok kq")
        self.assertEqual(
            got,
            "[NAME_1] ([PII_ANONYMIZED_1]) at [ORG_NAME_1] in [LOCATION_REDACTED], 9am [TZ_REDACTED]. ok kq",
        )

    def test_utc_offsets_and_iso_offsets_say_where_someone_is(self) -> None:
        got = _redactor().text(
            "UTC+8 then 2026-10-01T09:00:00+08:00 and 2026-10-01T09:00:00Z, asia/taipei"
        )
        self.assertNotIn("+08:00", got)
        self.assertNotIn("UTC+8", got)
        self.assertNotIn("taipei", got)
        self.assertIn("09:00:00Z", got)

    def test_long_unpunctuated_prose_is_still_redacted(self) -> None:
        prose = " ".join(["Pat Example met Robin"] * 40)
        self.assertNotIn("Pat Example", _redactor().value(prose))

    def test_every_id_in_a_page_url_and_a_bare_page_id_field(self) -> None:
        page, view = "a" * 32, "b" * 32
        got = _redactor().text(
            f'https://www.notion.so/Title-{page}?v={view}#{"c" * 32} {{"page_id": "{"d" * 32}"}}'
        )
        for hexid in ("a" * 32, "b" * 32, "c" * 32, "d" * 32):
            self.assertNotIn(hexid, got)

    def test_a_case_sensitive_initial_leaves_the_lowercase_word_alone(self) -> None:
        self.assertEqual(_redactor().text("ask KQ, not kq"), "ask [NAME_2], not kq")

    def test_a_credential_and_a_signed_url_signature(self) -> None:
        got = _redactor().text(
            "key ghp_" + "a" * 36 + " url https://x.test/f?X-Goog-Signature=abcdef0123456789"
        )
        self.assertNotIn("ghp_a", got)
        self.assertNotIn("abcdef0123456789", got)
        self.assertIn("[REDACTED_SECRET_", got)

    def test_a_harness_keyed_capability_is_hidden(self) -> None:
        hexed = "ab" * 32
        got = _redactor().text(f'{{"claude": "{hexed}", "note": "capability token: {hexed}"}}')
        self.assertNotIn(hexed, got)
        self.assertEqual(got.count("[REDACTED_SECRET_1]"), 2)
        commit = "cd" * 32
        self.assertIn(commit, _redactor().text(f"tree {commit}"))

    def test_the_documented_placeholder_key_is_kept(self) -> None:
        self.assertIn("AKIAIOSFODNN7EXAMPLE", _redactor().text("AKIAIOSFODNN7EXAMPLE"))

    def test_a_listing_of_other_sessions_prompts_is_removed_whole(self) -> None:
        listing = "\n".join(
            f"#{i} abcdef0{i} proj 12K FIRST: 'something private'" for i in range(4)
        )
        self.assertEqual(_redactor().value(listing), "[CROSS_SESSION_LISTING_REMOVED]")

    def test_someone_elses_chat_message_body_is_removed_and_yours_is_kept(self) -> None:
        text = (
            "=== Message from Pat Example <pat@acme.io> (U0123456789) at 1 === \nmine\n"
            "\n=== Message from Robin <robin@acme.io> (U0987654321) at 2 === \ntheirs"
        )
        got = _redactor().value(text)
        self.assertIn("mine", got)
        self.assertNotIn("theirs", got)
        self.assertIn("[THIRD_PARTY_MESSAGE_REMOVED]", got)

    def test_an_identifier_seen_in_a_url_is_hidden_where_it_appears_bare(self) -> None:
        uid = "9c0ffee1-ab12-4cd3-8ef4-0123456789ab"
        found = rs.literals([])
        self.assertEqual(found, set())
        got = _redactor((uid,)).text(f"project 9c0ffee1-… and {uid}")
        self.assertNotIn("9c0ffee1", got)


class WhatAReplayNeedsKept(unittest.TestCase):
    def test_an_outside_path_stays_absolute_and_numbered_per_path(self) -> None:
        r = _redactor()
        got = r.text("/Users/pat/notes/a.md /Users/pat/other/b.md /Users/pat/notes/a.md")
        parts = got.split()
        self.assertTrue(all(p.startswith("/[EXTERNAL_PATH_") for p in parts))
        self.assertEqual(parts[0], parts[2])
        self.assertNotEqual(parts[0], parts[1])

    def test_a_runner_keeps_its_name_so_a_check_stays_a_check(self) -> None:
        got = _redactor().text("/Users/pat/.pyenv/versions/3.12/bin/python3 -m unittest x")
        self.assertRegex(got, r"^/\[EXTERNAL_PATH_1\]/python3 -m unittest x$")

    def test_this_repository_keeps_its_path_shape(self) -> None:
        got = _redactor().text("cd /Users/pat/repos/acme/cargento && ruff check .")
        self.assertEqual(got, "cd /Users/[NAME_1]/repos/[ORG_NAME_1]/cargento && ruff check .")

    def test_json_held_in_a_string_is_left_untouched_when_nothing_in_it_changes(self) -> None:
        pretty = json.dumps({"ok": True, "n": [1, 2]}, indent=2)
        self.assertEqual(_redactor().value(pretty), pretty)

    def test_json_held_in_a_string_keeps_its_layout_when_redacted(self) -> None:
        pretty = json.dumps({"who": "Pat Example", "n": 1}, indent=4)
        got = _redactor().value(pretty)
        self.assertEqual(json.loads(got), {"who": "[NAME_1]", "n": 1})
        self.assertIn('\n    "who"', got)

    def test_image_data_is_untouched(self) -> None:
        blob = "KQ" * 300
        self.assertEqual(_redactor().value(blob), blob)


class TheFixtureLayout(unittest.TestCase):
    def test_every_line_parses_and_subagents_land_where_a_replay_reads_them(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sid = "abc"
            src = Path(tmp, "proj")
            (src / sid / "subagents").mkdir(parents=True)
            rows = [{"type": "user", "uuid": "u1", "message": {"content": "Pat said hi"}}, {"x": 1}]
            (src / f"{sid}.jsonl").write_text(
                "".join(json.dumps(r) + "\n" for r in rows) + "not json\n"
            )
            (src / sid / "subagents" / "agent-1.jsonl").write_text(json.dumps(rows[0]) + "\n")
            out = Path(tmp, "out")
            result = rs.redact_session(rs.Config(CONFIG), str(src / f"{sid}.jsonl"), str(out), ())
            parent = (out / sid / f"{sid}.jsonl").read_text().splitlines()
            child = out / sid / sid / "subagents" / "agent-1.jsonl"
            self.assertEqual(result["skipped"], 1)
            self.assertEqual(
                [json.loads(line)["uuid"] if "uuid" in line else None for line in parent],
                ["u1", None],
            )
            self.assertIn("[NAME_1] said hi", parent[0])
            self.assertTrue(child.exists())
            self.assertEqual(
                os.path.getmtime(child), os.path.getmtime(src / sid / "subagents" / "agent-1.jsonl")
            )


if __name__ == "__main__":
    unittest.main()
