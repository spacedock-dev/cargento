"""Replay the shipped page reducers, rather than treating a stored verdict as the page."""

from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import drift_replay as dr


@unittest.skipUnless(shutil.which("node"), "page replay requires node")
class TheReplayMeasuresThePage(unittest.TestCase):
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
