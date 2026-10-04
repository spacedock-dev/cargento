"""Replay the shipped page reducers, rather than treating a stored verdict as the page."""

from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import drift_replay as dr


@unittest.skipUnless(shutil.which("node"), "page replay requires node")
class TheReplayMeasuresThePage(unittest.TestCase):
    def test_failed_check_only_is_secondary_with_a_reader_and_copy_uses_page_numbers(self) -> None:
        payload: dict[str, Any] = {
            "snapshot": True,
            "reader_available": True,
            "session": {
                "harness": "claude",
                "sid": "synthetic",
                "annotation_revision": 1,
                "annotation_window_start": 10,
            },
            "annotation": {"revision": 1, "goal": "Keep parser focused", "at": 10},
            "facts": [
                {
                    "fact_id": "failure",
                    "type": "tool_report",
                    "subject": "check",
                    "result": "failed",
                    "at": 20,
                    "summary": "Parser checks",
                    "source_session": {"harness": "claude", "sid": "synthetic"},
                }
            ],
            "scan": {"last_user_at": 15},
            "correctionParts": ["A check failed at 12:00", {"entry": "failure"}, "."],
        }
        measured = dr._page_states([payload])[0]
        self.assertEqual("steer-secondary", measured["page_state"])
        self.assertEqual("A check failed at 12:00 (#1 in Cargento).", measured["correction_text"])
        payload["reader_available"] = False
        self.assertEqual("steer-primary", dr._page_states([payload])[0]["page_state"])
        payload["facts"].append(
            {
                "fact_id": "later",
                "type": "user_message",
                "at": 30,
                "summary": "Keep the tests readable",
                "by": "you",
                "source_session": {"harness": "claude", "sid": "synthetic"},
            }
        )
        self.assertEqual("question", dr._page_states([payload])[0]["page_state"])
        payload["annotation"]["settled_through"] = 30
        self.assertEqual("nothing", dr._page_states([payload])[0]["page_state"])

    def test_retained_scan_anchor_reaches_the_actual_page_and_composer(self) -> None:
        _config, _pc, _live, correction, _reading = dr._runtime()
        row = {
            "harness": "claude",
            "sid": "synthetic",
            "annotation_revision": 1,
            "annotation_goal": "Tests pass",
            "annotation_window_start": 10,
        }
        facts = [
            {
                "fact_id": "failed",
                "type": "tool_report",
                "subject": "check",
                "result": "failed",
                "at": 30,
                "summary": "Parser checks",
                "source_session": {"harness": "claude", "sid": "synthetic"},
            }
        ]
        steer = dr._steer(correction, row, facts, 10, 20)
        self.assertTrue(steer["offered"])
        assessment = {
            "revision_read": 1,
            "read_at": 40,
            "window_start": 10,
            "criteria": {
                "goal": {"result": "unverifiable", "cites": []},
                "line_1": {"result": "unverifiable", "cites": []},
            },
        }
        payload = {
            "session": row,
            "facts": facts,
            "scan": {"last_user_at": 20},
            "annotation": {"revision": 1, "goal": "Tests pass", "line_1": "Tests pass"},
            "assessment": assessment,
            "level": "high",
            "unsettled": 0,
        }
        measured = dr._page_states([payload])[0]
        self.assertEqual("failed-check", measured["answer"])
        self.assertEqual("steer-secondary", measured["page_state"])

    def test_goal_only_departure_is_separate_from_the_not_enough_level(self) -> None:
        reading = {
            "revision_read": 1,
            "read_at": 100,
            "window_start": 10,
            "criteria": {"goal": {"result": "departure", "cites": ["said"]}},
        }
        entry = {
            "id": "said",
            "type": "agent_message",
            "at": 20,
            "author": "agent",
            "text": "I changed the unrelated module.",
            "title": "I changed the unrelated module.",
            "source": "Claude reply",
        }
        page = dr._page_states(
            [
                {
                    "assessment": reading,
                    "annotation": {"revision": 1, "goal": "Change the parser only"},
                    "entries": [entry],
                    "level": "not_enough",
                    "unsettled": 0,
                }
            ]
        )[0]
        self.assertEqual("departs", page["answer"])
        self.assertEqual("not_enough", page["level"])

    def test_missing_line_answer_cannot_show_none_or_low(self) -> None:
        page = dr._page_states(
            [
                {
                    "assessment": {
                        "revision_read": 1,
                        "read_at": 100,
                        "criteria": {
                            "goal": {"result": "unverifiable", "cites": []},
                            "line_1": {"cites": []},
                        },
                    },
                    "annotation": {"revision": 1, "goal": "Fix parser", "line_1": "Tests pass"},
                    "entries": [],
                    "level": "none_or_low",
                    "unsettled": 0,
                }
            ]
        )[0]
        self.assertEqual("cant-tell", page["answer"])
        self.assertEqual("not_enough", page["level"])

    def test_claims_do_not_make_the_intent_answer_depart(self) -> None:
        page = dr._page_states(
            [
                {
                    "assessment": {
                        "revision_read": 1,
                        "read_at": 100,
                        "criteria": {
                            "goal": {"result": "unverifiable", "cites": []},
                            "claims": {"result": "not shown by the record", "cites": ["said"]},
                        },
                    },
                    "annotation": {"revision": 1, "goal": "Fix parser"},
                    "entries": [
                        {
                            "id": "said",
                            "type": "agent_message",
                            "author": "agent",
                            "at": 20,
                            "text": "The reviews are running.",
                            "title": "The reviews are running.",
                            "source": "Claude reply",
                        }
                    ],
                    "level": "medium",
                    "unsettled": 0,
                }
            ]
        )[0]
        self.assertEqual("cant-tell", page["answer"])
        self.assertEqual("medium", page["level"])

    def test_malformed_reading_has_no_page_level(self) -> None:
        page = dr._page_states(
            [
                {
                    "assessment": {"unrecognized": "field"},
                    "annotation": {"revision": 1, "goal": "Fix parser"},
                    "entries": [],
                    "level": "high",
                    "unsettled": 0,
                }
            ]
        )[0]
        self.assertEqual("malformed", page["answer"])
        self.assertIsNone(page["level"])
