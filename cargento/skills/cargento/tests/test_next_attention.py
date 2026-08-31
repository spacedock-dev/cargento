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

    def test_loop_signal_uses_positive_integer_errors_only(self) -> None:
        loop_model = self.model(
            {
                "sessions": [
                    {
                        "harness": "claude",
                        "sid": "loop-owner",
                        "project": "alpha/repo",
                        "state": "working",
                        "loop": {"errors": 4, "tool": "Bash"},
                    }
                ]
            }
        )
        model_without_loop = self.model(
            {
                "sessions": [
                    {
                        "harness": "claude",
                        "sid": "loop-owner",
                        "project": "alpha/repo",
                        "state": "working",
                        "loop": {"errors": "4", "tool": "Bash"},
                    }
                ]
            }
        )
        assert isinstance(loop_model, dict)
        assert isinstance(model_without_loop, dict)

        self.assertEqual("loop", loop_model["risk"][0]["primaryKind"])
        self.assertEqual(
            {"errors": 4, "tool": "Bash"},
            loop_model["risk"][0]["signals"][0]["detail"],
        )
        self.assertEqual([], model_without_loop["risk"])

    def test_long_turn_requires_working_state_and_has_no_checkpoint(self) -> None:
        long_model = self.model(
            {
                "sessions": [
                    {
                        "harness": "codex",
                        "sid": "long-owner",
                        "project": "beta/repo",
                        "state": "working",
                        "turn": {"long": True, "eta_h": "2h"},
                        "tasks": [{"subject": "Do not become a checkpoint", "status": "pending"}],
                    },
                    {
                        "harness": "codex",
                        "sid": "invalid-long",
                        "project": "gamma/repo",
                        "state": "idle",
                        "turn": {"long": True},
                    },
                ]
            }
        )
        assert isinstance(long_model, dict)

        self.assertEqual("long-turn", long_model["risk"][0]["primaryKind"])
        self.assertNotIn("checkpoint", long_model["risk"][0])
        self.assertEqual(1, len(long_model["risk"]))

    def test_quota_pressure_uses_published_percent_and_valid_reset_only(self) -> None:
        quota_model = self.model(
            {
                "usage": [
                    {
                        "harness": "claude",
                        "state": "ok",
                        "fiveH": {"pct": 92, "resetAt": 12_000},
                        "week": {"pct": 69, "resetAt": 11_000},
                        "models": [{"label": "Opus", "pct": 91, "resetAt": "soon"}],
                    }
                ]
            }
        )
        quota_69_model = self.model(
            {
                "usage": [{"harness": "claude", "state": "ok", "fiveH": {"pct": 69}}]
            }
        )
        assert isinstance(quota_model, dict)
        assert isinstance(quota_69_model, dict)

        self.assertEqual("quota", quota_model["risk"][0]["primaryKind"])
        self.assertEqual(92, quota_model["risk"][0]["signals"][0]["detail"]["pct"])
        self.assertEqual("critical", quota_model["risk"][0]["signals"][0]["detail"]["tone"])
        self.assertEqual([], quota_69_model["risk"])
        self.assertEqual({"resetAt": 12_000}, quota_model["risk"][0]["checkpoint"])
        self.assertEqual([], quota_model["next"])
        self.assertNotIn("checkpoint", quota_model["risk"][1])

    def test_equal_long_turns_follow_harness_order_when_input_reverses(self) -> None:
        payload = {
            "harnesses": [
                {"key": "claude"},
                {"key": "codex"},
                {"key": "antigravity"},
            ],
            "sessions": [
                {"harness": "claude", "sid": "same", "project": "claude/label", "state": "working", "turn": {"long": True}},
                {"harness": "codex", "sid": "same", "project": "codex/label", "state": "working", "turn": {"long": True}},
                {"harness": "antigravity", "sid": "same", "project": "agy/label", "state": "working", "turn": {"long": True}},
            ],
        }
        first_model = self.model(payload)
        reversed_model = self.model({**payload, "sessions": list(reversed(payload["sessions"]))})
        assert isinstance(first_model, dict)
        assert isinstance(reversed_model, dict)

        first_keys = [subject["key"] for subject in first_model["risk"]]
        reversed_input_keys = [subject["key"] for subject in reversed_model["risk"]]
        self.assertEqual(
            [
                'session:["claude","same"]',
                'session:["codex","same"]',
                'session:["antigravity","same"]',
            ],
            first_keys,
        )
        self.assertEqual(first_keys, reversed_input_keys)

    def test_collision_represents_members_once_and_malformed_signals_do_not_move_valid_risk(self) -> None:
        model = self.model(
            {
                "sessions": [
                    {"harness": "claude", "sid": "loop-valid", "project": "alpha/repo", "state": "working", "loop": {"errors": 2, "tool": "Bash"}},
                    {"harness": "codex", "sid": "one", "project": "beta/app", "state": "idle"},
                    {"harness": "antigravity", "sid": "two", "project": "beta/app", "state": "idle"},
                    {"harness": "claude", "sid": "bad-loop", "project": "bad/loop", "state": "working", "loop": {"errors": 0}},
                    {"harness": "codex", "sid": "bad-turn", "project": "bad/turn", "state": "working", "turn": {"long": "true"}},
                    {"harness": "antigravity", "sid": "bad-stop", "project": "bad/stop", "state": "idle", "finished_at": "yesterday", "dirty": "yes", "changed": "3"},
                ],
                "asks": [{"id": "bad-ask", "question": "   ", "session_id": "loop-valid"}],
                "usage": [{"harness": "claude", "state": "ok", "fiveH": {"pct": "92"}}],
            }
        )
        assert isinstance(model, dict)

        self.assertEqual(["loop", "collision"], [subject["primaryKind"] for subject in model["risk"]])
        collision = model["risk"][1]
        self.assertEqual(2, len(collision["memberKeys"]))
        healthy_keys = {f'session:{json.dumps([row["harness"], row["sid"]], separators=(",", ":"))}' for row in model["healthy"]["sessions"]}
        self.assertFalse(set(collision["memberKeys"]) & healthy_keys)
        rendered = self._run_page_js(
            "\n".join(
                (
                    f"nextData = JSON.parse({json.dumps(json.dumps({'sessions': []}))});",
                    f"const subject = JSON.parse({json.dumps(json.dumps(collision))});",
                    "console.log(JSON.stringify(nextAttentionSubjectHtml(subject, {generated: null})));",
                )
            )
        )
        self.assertNotIn("repository", rendered)
        self.assertNotIn("directory", rendered)
        self.assertNotIn("branch", rendered)
        self.assertNotIn("worktree", rendered)

    def test_collision_deduplicates_exact_members_before_counting_or_representing(self) -> None:
        model = self.model(
            {
                "sessions": [
                    {"harness": "claude", "sid": "duplicate", "project": "beta/app", "state": "idle"},
                    {"harness": "claude", "sid": "duplicate", "project": "beta/app", "state": "idle"},
                    {"harness": "codex", "sid": "distinct", "project": "beta/app", "state": "idle"},
                ]
            }
        )
        one_exact_member = self.model(
            {
                "sessions": [
                    {"harness": "claude", "sid": "duplicate", "project": "beta/app", "state": "idle"},
                    {"harness": "claude", "sid": "duplicate", "project": "beta/app", "state": "idle"},
                ]
            }
        )
        assert isinstance(model, dict)
        assert isinstance(one_exact_member, dict)

        collision = model["risk"][0]
        self.assertEqual("collision", collision["primaryKind"])
        self.assertEqual(
            ['session:["claude","duplicate"]', 'session:["codex","distinct"]'],
            collision["memberKeys"],
        )
        self.assertEqual(collision["memberKeys"], model["representedSessionKeys"])
        self.assertEqual([], one_exact_member["risk"])

    def test_same_harness_and_model_scope_coalesces_valid_quota_signals(self) -> None:
        model = self.model(
            {
                "usage": [
                    {
                        "harness": "claude",
                        "state": "ok",
                        "models": [{"label": "Opus", "pct": 91, "resetAt": 15_000}],
                    },
                    {
                        "harness": "claude",
                        "state": "ok",
                        "models": [{"label": "Opus", "pct": 92, "resetAt": 16_000}],
                    },
                ]
            }
        )
        assert isinstance(model, dict)

        self.assertEqual(1, len(model["risk"]))
        quota = model["risk"][0]
        self.assertEqual("quota:claude:model:Opus:0", quota["key"])
        self.assertEqual([92, 91], [signal["detail"]["pct"] for signal in quota["signals"]])
        self.assertEqual({"resetAt": 16_000}, quota["checkpoint"])

    def test_idle_stops_require_a_valid_stop_and_keep_git_readings_bounded(self) -> None:
        model = self.model(
            {
                "generated": 10_000,
                "sessions": [
                    {
                        "harness": "claude", "sid": "dirty-stop", "project": "alpha/dirty",
                        "state": "idle", "finished_at": 7_000, "dirty": True, "changed": 3,
                    },
                    {
                        "harness": "codex", "sid": "unknown-stop", "project": "beta/unknown",
                        "state": "idle", "finished_at": 6_000, "dirty": None,
                    },
                    {
                        "harness": "antigravity", "sid": "clean-stop", "project": "gamma/clean",
                        "state": "idle", "finished_at": 5_000, "dirty": False,
                    },
                    {
                        "harness": "antigravity", "sid": "scan-only", "project": "delta/scan",
                        "state": "idle", "dirty": True, "changed": 3,
                    },
                ],
            }
        )
        assert isinstance(model, dict)

        dirty_model = {**model, "close": [model["close"][0]]}
        unknown_model = {**model, "close": [model["close"][1]]}
        clean_model = {**model, "close": [model["close"][2]]}
        scan_only_model = self.model(
            {
                "sessions": [
                    {
                        "harness": "antigravity", "sid": "scan-only", "project": "delta/scan",
                        "state": "idle", "dirty": True, "changed": 3,
                    }
                ]
            }
        )
        assert isinstance(scan_only_model, dict)

        self.assertEqual("stop-dirty", dirty_model["close"][0]["primaryKind"])
        self.assertEqual(3, dirty_model["close"][0]["signals"][0]["detail"]["changedEntries"])
        self.assertEqual("stop-unknown", unknown_model["close"][0]["primaryKind"])
        self.assertEqual("stop-clean", clean_model["close"][0]["primaryKind"])
        self.assertEqual([], scan_only_model["close"])
        dirty_html = self._run_page_js(
            "\n".join(
                (
                    f"const subject = JSON.parse({json.dumps(json.dumps(dirty_model['close'][0]))});",
                    "console.log(JSON.stringify(nextAttentionSubjectHtml(subject, {generated: 10000})));",
                )
            )
        )
        assert isinstance(dirty_html, str)
        for forbidden in ("files", "failed", "unread", "unfinished", "successful", "died"):
            self.assertNotIn(forbidden, dirty_html.lower())

    def test_published_tasks_and_healthy_remainder_exclude_higher_section_subjects(self) -> None:
        model = self.model(
            {
                "sessions": [
                    {
                        "harness": "claude", "sid": "progress-first", "project": "alpha/progress",
                        "state": "working", "tasks": [
                            {"subject": "Pending first", "status": "pending"},
                            {"subject": "In progress second", "status": "in_progress"},
                        ],
                    },
                    {
                        "harness": "codex", "sid": "pending-working", "project": "beta/pending",
                        "state": "working", "tasks": [{"subject": "Pending working", "status": "pending"}],
                    },
                    {
                        "harness": "antigravity", "sid": "pending-idle", "project": "gamma/pending",
                        "state": "idle", "tasks": [{"subject": "Pending idle", "status": "pending"}],
                    },
                    {
                        "harness": "claude", "sid": "risk-owner", "project": "delta/risk",
                        "state": "working", "loop": {"errors": 2},
                        "tasks": [{"subject": "Keep on risk", "status": "in_progress"}],
                    },
                    {"harness": "claude", "sid": "moving", "project": "delta/moving", "state": "working"},
                    {"harness": "codex", "sid": "quiet", "project": "epsilon/quiet", "state": "idle"},
                    {"harness": "antigravity", "sid": "unknown", "project": "zeta/unknown", "state": "other"},
                ],
            }
        )
        eta_only_model = self.model(
            {
                "eta_h": 2,
                "sessions": [{
                    "harness": "claude", "sid": "eta-only", "project": "eta/only",
                    "state": "working", "turn": {"eta_h": 1},
                }],
            }
        )
        assert isinstance(model, dict)
        assert isinstance(eta_only_model, dict)

        self.assertEqual(
            [
                'session:["claude","progress-first"]',
                'session:["codex","pending-working"]',
                'session:["antigravity","pending-idle"]',
            ],
            [subject["key"] for subject in model["next"]],
        )
        self.assertEqual("In progress second", model["next"][0]["checkpoint"]["subject"])
        self.assertEqual([], eta_only_model["next"])
        self.assertEqual([], eta_only_model["needs"])
        self.assertEqual([], eta_only_model["risk"])
        self.assertEqual([], eta_only_model["close"])
        self.assertEqual(1, model["healthy"]["moving"])
        self.assertEqual(1, model["healthy"]["quiet"])
        self.assertEqual(1, model["healthy"]["unknown"])
