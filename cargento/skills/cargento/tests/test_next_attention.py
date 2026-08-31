from __future__ import annotations

import json
import shutil
import unittest

from .next_harness import NextPageJsHarness


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextAttentionBehaviorTest(NextPageJsHarness):
    def model(self, payload: object) -> object:
        encoded = json.dumps(payload)
        return self._run_page_js(
            "\n".join(
                (
                    f"nextData = JSON.parse({json.dumps(encoded)});",
                    "console.log(JSON.stringify(nextAttentionModel(nextData)));",
                )
            )
        )

    def test_exact_spacedock_ask_is_captain_and_publishes_one_checkpoint(self) -> None:
        model = self.model(
            {
                "generated": 10_000,
                "sessions": [
                    {
                        "harness": "claude",
                        "sid": "claude-exact",
                        "project": "alpha/repo",
                        "state": "needs_input",
                        "spacedock": {"role": "first-officer"},
                        "tasks": [
                            {"id": "done", "subject": "Already done", "status": "completed"},
                            {"id": "checks", "subject": "Run checks", "status": "pending"},
                        ],
                    }
                ],
                "asks": [
                    {
                        "id": "ask-claude",
                        "session_id": "claude-exact",
                        "project": "alpha/repo",
                        "question": "Approve deploy",
                        "age_sec": 480,
                    }
                ],
            }
        )
        assert isinstance(model, dict)

        self.assertEqual("CAPTAIN", model["needs"][0]["responsibility"])
        self.assertEqual("Run checks", model["needs"][0]["checkpoint"]["subject"])
        self.assertEqual([], model["next"])

    def test_same_label_spacedock_sibling_does_not_borrow_captain_authority(self) -> None:
        model = self.model(
            {
                "sessions": [
                    {
                        "harness": "codex",
                        "sid": "plain-owner",
                        "project": "beta/app",
                        "state": "needs_input",
                        "spacedock": None,
                    },
                    {
                        "harness": "claude",
                        "sid": "spacedock-sibling",
                        "project": "beta/app",
                        "state": "idle",
                        "spacedock": {"role": "first-officer"},
                    },
                ],
                "asks": [
                    {
                        "id": "ask-plain",
                        "session_id": "plain-owner",
                        "project": "beta/app",
                        "question": "Approve plain work",
                        "age_sec": 60,
                    }
                ],
            }
        )
        assert isinstance(model, dict)

        self.assertEqual("NEEDS YOU", model["needs"][0]["responsibility"])

    def test_bare_needs_input_has_no_question_or_authority(self) -> None:
        model = self.model(
            {
                "generated": 10_000,
                "sessions": [
                    {
                        "harness": "antigravity",
                        "sid": "bare-gate",
                        "project": "gamma/tool",
                        "state": "needs_input",
                        "state_detail": "Waiting for a bounded choice",
                        "blocked_since": 9_400,
                    }
                ],
                "asks": [],
            }
        )
        assert isinstance(model, dict)

        self.assertEqual("input", model["needs"][0]["primaryKind"])
        self.assertNotIn("responsibility", model["needs"][0])

    def test_mismatched_ask_project_stays_on_its_exact_owner_as_secondary_attribution(self) -> None:
        model = self.model(
            {
                "sessions": [
                    {
                        "harness": "codex",
                        "sid": "conflict-owner",
                        "project": "delta/plain",
                        "state": "needs_input",
                        "spacedock": None,
                    }
                ],
                "asks": [
                    {
                        "id": "ask-conflict",
                        "session_id": "conflict-owner",
                        "project": "other/label",
                        "question": "Which project owns this?",
                        "age_sec": 90,
                    }
                ],
            }
        )
        assert isinstance(model, dict)

        self.assertEqual(
            ["ask", "attribution"],
            [signal["kind"] for signal in model["needs"][0]["signals"]],
        )
        self.assertEqual([], model["risk"])

    def test_multiple_exact_asks_stay_together_and_unmatched_ask_stays_independent(self) -> None:
        model = self.model(
            {
                "sessions": [
                    {
                        "harness": "claude",
                        "sid": "multi-owner",
                        "project": "epsilon/repo",
                        "state": "needs_input",
                        "spacedock": None,
                    }
                ],
                "asks": [
                    {
                        "id": "newer-exact",
                        "session_id": "multi-owner",
                        "project": "epsilon/repo",
                        "question": "Newer exact question",
                        "age_sec": 100,
                    },
                    {
                        "id": "older-exact",
                        "session_id": "multi-owner",
                        "project": "epsilon/repo",
                        "question": "Older exact question",
                        "age_sec": 900,
                    },
                    {
                        "id": "unmatched",
                        "session_id": "missing-owner",
                        "project": "zeta/repo",
                        "question": "Unmatched question",
                        "age_sec": 20,
                    },
                ],
            }
        )
        assert isinstance(model, dict)

        self.assertEqual('session:["claude","multi-owner"]', model["needs"][0]["key"])
        self.assertEqual(
            ["Newer exact question", "Older exact question"],
            [ask["question"] for ask in model["needs"][0]["asks"]],
        )
        self.assertEqual("ask:unmatched", model["needs"][1]["key"])

    def test_equal_age_asks_keep_payload_order_before_stable_identity(self) -> None:
        model = self.model(
            {
                "sessions": [
                    {
                        "harness": "claude",
                        "sid": "zeta-owner",
                        "project": "zeta/repo",
                        "state": "needs_input",
                        "spacedock": None,
                    }
                ],
                "asks": [
                    {
                        "id": "earlier-exact",
                        "session_id": "zeta-owner",
                        "project": "zeta/repo",
                        "question": "Earlier exact question",
                        "age_sec": 300,
                    },
                    {
                        "id": "later-unmatched",
                        "session_id": "missing-owner",
                        "project": "alpha/repo",
                        "question": "Later unmatched question",
                        "age_sec": 300,
                    },
                ],
            }
        )
        assert isinstance(model, dict)

        self.assertEqual(
            ['session:["claude","zeta-owner"]', "ask:later-unmatched"],
            [subject["key"] for subject in model["needs"]],
        )
