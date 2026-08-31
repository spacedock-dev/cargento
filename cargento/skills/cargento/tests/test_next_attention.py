from __future__ import annotations

import json
import re
import shutil
import unittest

from .next_harness import NEXT_STYLES, NextPageJsHarness


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

    def render(self, payload: object) -> str:
        encoded = json.dumps(payload)
        rendered = self._run_page_js(
            "\n".join(
                (
                    f"nextData = JSON.parse({json.dumps(encoded)});",
                    "console.log(JSON.stringify(nextAttentionView(nextAttentionModel(nextData))));",
                )
            )
        )
        assert isinstance(rendered, str)
        return rendered

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

    def test_exact_ask_renders_its_lower_ranked_loop_fact_without_a_risk_duplicate(self) -> None:
        payload = {
            "sessions": [
                {
                    "harness": "claude",
                    "sid": "ask-loop-owner",
                    "project": "alpha/repo",
                    "state": "needs_input",
                    "loop": {"errors": 4, "tool": "Bash"},
                }
            ],
            "asks": [
                {
                    "id": "ask-loop",
                    "session_id": "ask-loop-owner",
                    "project": "alpha/repo",
                    "question": "Approve deploy",
                }
            ],
        }
        model = self.model(payload)
        assert isinstance(model, dict)

        self.assertEqual(
            ["ask", "loop"], [signal["kind"] for signal in model["needs"][0]["signals"]]
        )
        self.assertEqual([], model["risk"])
        html = self.render(payload)
        self.assertIn("Approve deploy", html)
        self.assertIn("Bash failed 4 times", html)

    def test_long_turn_without_source_task_has_no_checkpoint(self) -> None:
        long_model = self.model(
            {
                "sessions": [
                    {
                        "harness": "codex",
                        "sid": "long-owner",
                        "project": "beta/repo",
                        "state": "working",
                        "turn": {"long": True, "eta_h": "2h"},
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

    def test_risk_subject_keeps_published_task_without_coming_next_duplicate(self) -> None:
        payload = {
            "sessions": [
                {
                    "harness": "codex",
                    "sid": "risk-task-owner",
                    "project": "beta/repo",
                    "state": "working",
                    "turn": {"long": True, "eta_h": "2h"},
                    "tasks": [{"subject": "Publish the report", "status": "pending"}],
                }
            ]
        }
        model = self.model(payload)
        assert isinstance(model, dict)

        risk = model["risk"][0]
        self.assertEqual(["long-turn", "task"], [signal["kind"] for signal in risk["signals"]])
        self.assertEqual("Publish the report", risk["checkpoint"]["subject"])
        self.assertEqual([], model["next"])
        self.assertIn("Publish the report", self.render(payload))

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
            {"usage": [{"harness": "claude", "state": "ok", "fiveH": {"pct": 69}}]}
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
        sessions = [
            {
                "harness": "claude",
                "sid": "same",
                "project": "claude/label",
                "state": "working",
                "turn": {"long": True},
            },
            {
                "harness": "codex",
                "sid": "same",
                "project": "codex/label",
                "state": "working",
                "turn": {"long": True},
            },
            {
                "harness": "antigravity",
                "sid": "same",
                "project": "agy/label",
                "state": "working",
                "turn": {"long": True},
            },
        ]
        payload = {
            "harnesses": [
                {"key": "claude"},
                {"key": "codex"},
                {"key": "antigravity"},
            ],
            "sessions": sessions,
        }
        first_model = self.model(payload)
        reversed_model = self.model({**payload, "sessions": list(reversed(sessions))})
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

    def test_collision_represents_members_once_and_malformed_signals_do_not_move_valid_risk(
        self,
    ) -> None:
        model = self.model(
            {
                "sessions": [
                    {
                        "harness": "claude",
                        "sid": "loop-valid",
                        "project": "alpha/repo",
                        "state": "working",
                        "loop": {"errors": 2, "tool": "Bash"},
                    },
                    {"harness": "codex", "sid": "one", "project": "beta/app", "state": "idle"},
                    {
                        "harness": "antigravity",
                        "sid": "two",
                        "project": "beta/app",
                        "state": "idle",
                    },
                    {
                        "harness": "claude",
                        "sid": "bad-loop",
                        "project": "bad/loop",
                        "state": "working",
                        "loop": {"errors": 0},
                    },
                    {
                        "harness": "codex",
                        "sid": "bad-turn",
                        "project": "bad/turn",
                        "state": "working",
                        "turn": {"long": "true"},
                    },
                    {
                        "harness": "antigravity",
                        "sid": "bad-stop",
                        "project": "bad/stop",
                        "state": "idle",
                        "finished_at": "yesterday",
                        "dirty": "yes",
                        "changed": "3",
                    },
                ],
                "asks": [{"id": "bad-ask", "question": "   ", "session_id": "loop-valid"}],
                "usage": [{"harness": "claude", "state": "ok", "fiveH": {"pct": "92"}}],
            }
        )
        assert isinstance(model, dict)

        self.assertEqual(
            ["loop", "collision"], [subject["primaryKind"] for subject in model["risk"]]
        )
        collision = model["risk"][1]
        self.assertEqual(2, len(collision["memberKeys"]))
        healthy_keys = {
            f"session:{json.dumps([row['harness'], row['sid']], separators=(',', ':'))}"
            for row in model["healthy"]["sessions"]
        }
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
                    {
                        "harness": "claude",
                        "sid": "duplicate",
                        "project": "beta/app",
                        "state": "idle",
                    },
                    {
                        "harness": "claude",
                        "sid": "duplicate",
                        "project": "beta/app",
                        "state": "idle",
                    },
                    {"harness": "codex", "sid": "distinct", "project": "beta/app", "state": "idle"},
                ]
            }
        )
        one_exact_member = self.model(
            {
                "sessions": [
                    {
                        "harness": "claude",
                        "sid": "duplicate",
                        "project": "beta/app",
                        "state": "idle",
                    },
                    {
                        "harness": "claude",
                        "sid": "duplicate",
                        "project": "beta/app",
                        "state": "idle",
                    },
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

    def test_collision_renders_each_member_task_with_exact_attribution(self) -> None:
        payload = {
            "harnesses": [
                {"key": "claude", "label": "Claude Code", "discovered": True},
                {"key": "codex", "label": "Codex", "discovered": True},
            ],
            "sessions": [
                {
                    "harness": "claude",
                    "sid": "collision-claude",
                    "project": "beta/app",
                    "state": "working",
                    "tasks": [{"subject": "Run Claude checks", "status": "in_progress"}],
                },
                {
                    "harness": "codex",
                    "sid": "collision-codex",
                    "project": "beta/app",
                    "state": "idle",
                    "tasks": [{"subject": "Publish Codex notes", "status": "pending"}],
                },
            ],
        }
        model = self.model(payload)
        assert isinstance(model, dict)

        collision = model["risk"][0]
        self.assertEqual(
            ["collision", "task", "task"],
            [signal["kind"] for signal in collision["signals"]],
        )
        self.assertEqual([], model["next"])
        html = self.render(payload)
        for expected in (
            "Run Claude checks",
            "Publish Codex notes",
            "Claude Code · collision-claude",
            "Codex · collision-codex",
        ):
            self.assertIn(expected, html)

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
                        "harness": "claude",
                        "sid": "dirty-stop",
                        "project": "alpha/dirty",
                        "state": "idle",
                        "finished_at": 7_000,
                        "dirty": True,
                        "changed": 3,
                    },
                    {
                        "harness": "codex",
                        "sid": "unknown-stop",
                        "project": "beta/unknown",
                        "state": "idle",
                        "finished_at": 6_000,
                        "dirty": None,
                    },
                    {
                        "harness": "antigravity",
                        "sid": "clean-stop",
                        "project": "gamma/clean",
                        "state": "idle",
                        "finished_at": 5_000,
                        "dirty": False,
                    },
                    {
                        "harness": "antigravity",
                        "sid": "scan-only",
                        "project": "delta/scan",
                        "state": "idle",
                        "dirty": True,
                        "changed": 3,
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
                        "harness": "antigravity",
                        "sid": "scan-only",
                        "project": "delta/scan",
                        "state": "idle",
                        "dirty": True,
                        "changed": 3,
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

    def test_duplicate_exact_stops_keep_the_first_source_owner_and_reading(self) -> None:
        model = self.model(
            {
                "sessions": [
                    {
                        "harness": "claude",
                        "sid": "duplicate-stop",
                        "project": "alpha/first",
                        "state": "idle",
                        "finished_at": 7_000,
                        "dirty": True,
                        "changed": 3,
                    },
                    {
                        "harness": "claude",
                        "sid": "duplicate-stop",
                        "project": "beta/later",
                        "state": "idle",
                        "finished_at": 6_000,
                        "dirty": False,
                        "changed": 0,
                    },
                ]
            }
        )
        assert isinstance(model, dict)

        self.assertEqual(1, len(model["close"]))
        close = model["close"][0]
        self.assertEqual("stop-dirty", close["primaryKind"])
        self.assertEqual({"finishedAt": 7_000, "changedEntries": 3}, close["signals"][0]["detail"])
        self.assertEqual("alpha/first", close["session"]["project"])
        self.assertEqual(0, close["sourceIndex"])

    def test_risk_subject_renders_its_lower_ranked_stop_without_close_duplicate(self) -> None:
        payload = {
            "sessions": [
                {
                    "harness": "claude",
                    "sid": "risk-stop-owner",
                    "project": "alpha/risk-stop",
                    "state": "idle",
                    "loop": {"errors": 3, "tool": "Bash"},
                    "finished_at": 7_000,
                    "dirty": True,
                    "changed": 2,
                }
            ]
        }
        model = self.model(payload)
        assert isinstance(model, dict)

        risk = model["risk"][0]
        self.assertEqual(["loop", "stop-dirty"], [signal["kind"] for signal in risk["signals"]])
        self.assertEqual([], model["close"])
        html = self.render(payload)
        self.assertIn("Bash failed 3 times", html)
        self.assertIn("2 changed entries", html)

    def test_close_subject_keeps_published_task_without_coming_next_duplicate(self) -> None:
        payload = {
            "sessions": [
                {
                    "harness": "codex",
                    "sid": "close-task-owner",
                    "project": "beta/close-task",
                    "state": "idle",
                    "finished_at": 8_000,
                    "dirty": None,
                    "tasks": [{"subject": "Archive the result", "status": "pending"}],
                }
            ]
        }
        model = self.model(payload)
        assert isinstance(model, dict)

        close = model["close"][0]
        self.assertEqual(["stop-unknown", "task"], [signal["kind"] for signal in close["signals"]])
        self.assertEqual("Archive the result", close["checkpoint"]["subject"])
        self.assertEqual([], model["next"])
        self.assertIn("Archive the result", self.render(payload))

    def test_published_tasks_and_healthy_remainder_exclude_higher_section_subjects(self) -> None:
        model = self.model(
            {
                "sessions": [
                    {
                        "harness": "claude",
                        "sid": "progress-first",
                        "project": "alpha/progress",
                        "state": "working",
                        "tasks": [
                            {"subject": "Pending first", "status": "pending"},
                            {"subject": "In progress second", "status": "in_progress"},
                        ],
                    },
                    {
                        "harness": "codex",
                        "sid": "pending-working",
                        "project": "beta/pending",
                        "state": "working",
                        "tasks": [{"subject": "Pending working", "status": "pending"}],
                    },
                    {
                        "harness": "antigravity",
                        "sid": "pending-idle",
                        "project": "gamma/pending",
                        "state": "idle",
                        "tasks": [{"subject": "Pending idle", "status": "pending"}],
                    },
                    {
                        "harness": "claude",
                        "sid": "risk-owner",
                        "project": "delta/risk",
                        "state": "working",
                        "loop": {"errors": 2},
                        "tasks": [{"subject": "Keep on risk", "status": "in_progress"}],
                    },
                    {
                        "harness": "claude",
                        "sid": "moving",
                        "project": "delta/moving",
                        "state": "working",
                    },
                    {
                        "harness": "codex",
                        "sid": "quiet",
                        "project": "epsilon/quiet",
                        "state": "idle",
                    },
                    {
                        "harness": "antigravity",
                        "sid": "unknown",
                        "project": "zeta/unknown",
                        "state": "other",
                    },
                ],
            }
        )
        eta_only_model = self.model(
            {
                "eta_h": 2,
                "sessions": [
                    {
                        "harness": "claude",
                        "sid": "eta-only",
                        "project": "eta/only",
                        "state": "working",
                        "turn": {"eta_h": 1},
                    }
                ],
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

    def test_discovered_harness_capabilities_bound_coverage_and_failures(self) -> None:
        agy_payload = {
            "harnesses": [
                {
                    "key": "antigravity",
                    "label": "AGY",
                    "discovered": True,
                    "reports_needs_input": False,
                    "reports_rate": False,
                    "error": None,
                }
            ],
            "sessions": [
                {
                    "harness": "antigravity",
                    "sid": "agy-idle",
                    "project": "agy/project",
                    "state": "idle",
                }
            ],
            "asks": [],
        }
        failure_payload = {
            "ask": True,
            "harnesses": [
                {
                    "key": "claude",
                    "label": "Claude Code",
                    "discovered": True,
                    "reports_needs_input": True,
                    "reports_rate": True,
                    "error": "PermissionError: /Users/private/transcript.jsonl",
                },
                {
                    "key": "ghost",
                    "label": "Not discovered",
                    "discovered": False,
                    "reports_needs_input": True,
                    "reports_rate": True,
                    "error": None,
                },
            ],
            "sessions": [],
            "asks": [],
        }
        agy_model = self.model(agy_payload)
        failure_model = self.model(failure_payload)
        assert isinstance(agy_model, dict)
        assert isinstance(failure_model, dict)

        gate_counts = {
            key: agy_model["coverage"]["gates"][key]
            for key in ("discovered", "reporting", "unknown", "failed")
        }
        self.assertEqual(
            {"discovered": 1, "reporting": 0, "unknown": 1, "failed": 0},
            gate_counts,
        )
        self.assertEqual(1, failure_model["coverage"]["gates"]["failed"])
        self.assertEqual([], failure_model["needs"])
        agy_html = self.render(agy_payload)
        failure_html = self.render(failure_payload)
        self.assertIn("1 session with no published exception", agy_html)
        self.assertNotIn("AGY is clear", agy_html)
        self.assertIn("1 failed", failure_html)
        self.assertNotIn("PermissionError", failure_html)
        self.assertNotIn("/Users/private/transcript.jsonl", failure_html)

    def test_exact_request_and_empty_copy_respect_capability_and_payload_window(self) -> None:
        ask_disabled_html = self.render({"sessions": [], "asks": []})
        ask_enabled_html = self.render({"ask": True, "sessions": [], "asks": []})
        empty_html = self.render({"window_hours": 24, "sessions": [], "harnesses": [], "asks": []})

        self.assertNotIn("No exact requests published", ask_disabled_html)
        self.assertIn("No exact requests published", ask_enabled_html)
        self.assertIn("No sessions in this 24h payload", empty_html)
        self.assertIn("COVERAGE", empty_html)
        self.assertNotIn("no agents exist", empty_html.lower())

    def test_compressed_remainder_heading_says_only_no_published_exception(self) -> None:
        html = self.render(
            {
                "harnesses": [
                    {
                        "key": "antigravity",
                        "label": "AGY",
                        "discovered": True,
                        "reports_needs_input": False,
                        "reports_rate": False,
                        "error": None,
                    }
                ],
                "sessions": [
                    {
                        "harness": "antigravity",
                        "sid": "quiet-owner",
                        "project": "alpha/quiet",
                        "state": "idle",
                    }
                ],
            }
        )

        self.assertIn("NO PUBLISHED EXCEPTION (1)</h2>", html)
        self.assertNotIn("HEALTHY FLEET", html)
        self.assertIn("No published exception; coverage applies", html)
        self.assertIn('href="#n=projects"', html)

    def test_attention_uses_semantic_lists_and_the_five_part_item_grammar(self) -> None:
        payload = {
            "generated": 10_000,
            "harnesses": [
                {
                    "key": "claude",
                    "label": "Claude Code",
                    "discovered": True,
                    "reports_needs_input": True,
                    "reports_rate": True,
                    "error": None,
                }
            ],
            "sessions": [
                {
                    "harness": "claude",
                    "sid": "ask-owner",
                    "project": "alpha/ask",
                    "state": "needs_input",
                    "tasks": [{"subject": "Run checks", "status": "pending"}],
                },
                {
                    "harness": "claude",
                    "sid": "risk-owner",
                    "project": "beta/risk",
                    "state": "working",
                    "loop": {"errors": 4, "tool": "Bash"},
                },
                {
                    "harness": "claude",
                    "sid": "stop-owner",
                    "project": "gamma/stop",
                    "state": "idle",
                    "finished_at": 9_000,
                    "dirty": None,
                },
                {
                    "harness": "claude",
                    "sid": "task-owner",
                    "project": "delta/task",
                    "state": "working",
                    "tasks": [{"subject": "Publish docs", "status": "in_progress"}],
                },
                {
                    "harness": "claude",
                    "sid": "healthy-owner",
                    "project": "epsilon/quiet",
                    "state": "idle",
                },
            ],
            "asks": [
                {
                    "id": "ask-one",
                    "session_id": "ask-owner",
                    "project": "alpha/ask",
                    "question": "Approve deploy",
                    "age_sec": 480,
                }
            ],
        }
        html = self.render(payload)

        self.assertEqual(1, html.count("<h1 "))
        self.assertEqual(5, html.count("<h2"))
        self.assertEqual(4, html.count('<ol id="next-attention-'))
        self.assertEqual(4, html.count("<li><article"))
        self.assertEqual(4, html.count('data-next-attention-part="why"><a '))
        self.assertEqual(1, html.count('<details class="next-attention-coverage-details">'))
        self.assertNotIn('<details class="next-attention-coverage-details" open', html)
        ask_item = html.split('data-next-attention-subject="session:[&quot;claude&quot;,', 1)[1]
        ask_item = ask_item.split("</article>", 1)[0]
        grammar = [
            'data-next-attention-part="why"',
            'data-next-attention-part="outcome"',
            'data-next-attention-part="now"',
            'data-next-attention-part="next"',
            'data-next-attention-part="source"',
        ]
        self.assertEqual(
            sorted(html.index(label) for label in grammar), [html.index(label) for label in grammar]
        )
        self.assertTrue(all(label in ask_item for label in grammar))
        risk_item = html.split('data-next-attention-kind="loop"', 1)[1].split("</article>", 1)[0]
        self.assertNotIn('data-next-attention-part="next"', risk_item)
        healthy = html.split('data-next-attention-section="healthy"', 1)[1]
        self.assertNotIn("<article", healthy)
        self.assertIn('href="#n=projects"', healthy)

    def test_all_model_subject_kinds_render_bounded_source_claims(self) -> None:
        html = self.render(
            {
                "generated": 10_000,
                "harnesses": [
                    {
                        "key": "claude",
                        "label": "Claude Code",
                        "discovered": True,
                        "reports_needs_input": True,
                        "reports_rate": True,
                        "error": None,
                    }
                ],
                "sessions": [
                    {
                        "harness": "claude",
                        "sid": "bare",
                        "project": "bare/input",
                        "state": "needs_input",
                        "state_detail": "Choose a bounded option",
                        "blocked_since": 9_400,
                    },
                    {
                        "harness": "claude",
                        "sid": "loop",
                        "project": "risk/loop",
                        "state": "working",
                        "loop": {"errors": 4, "tool": "Bash"},
                    },
                    {
                        "harness": "claude",
                        "sid": "long",
                        "project": "risk/long",
                        "state": "working",
                        "turn": {"long": True, "elapsed_h": "3h", "eta_h": "soon"},
                    },
                    {
                        "harness": "claude",
                        "sid": "dirty",
                        "project": "stop/dirty",
                        "state": "idle",
                        "finished_at": 8_000,
                        "dirty": True,
                        "changed": 3,
                    },
                    {
                        "harness": "claude",
                        "sid": "clean",
                        "project": "stop/clean",
                        "state": "idle",
                        "finished_at": 8_100,
                        "dirty": False,
                    },
                    {
                        "harness": "claude",
                        "sid": "unknown",
                        "project": "stop/unknown",
                        "state": "idle",
                        "finished_at": 8_200,
                        "dirty": None,
                    },
                    {
                        "harness": "claude",
                        "sid": "task",
                        "project": "next/task",
                        "state": "working",
                        "tasks": [{"subject": "Ship docs", "status": "in_progress"}],
                    },
                ],
                "usage": [
                    {
                        "harness": "claude",
                        "state": "ok",
                        "fiveH": {"pct": 92, "resetAt": 12_000},
                    }
                ],
            }
        )

        for claim in (
            "Input signal observed",
            "Repeated tool failures",
            "Bash failed 4 times",
            "Long-running turn",
            "Quota pressure",
            "92% reported",
            "Stop observed with uncommitted work",
            "3 changed entries",
            "Stop observed; git state clean",
            "Stop observed; git state not measured",
            "Published task",
            "Ship docs",
        ):
            self.assertIn(claim, html)
        self.assertNotIn("soon", html)
        self.assertNotIn("exhaust", html.lower())

    def test_outcome_uses_exact_assignment_or_one_distinct_workflow_goal(self) -> None:
        def outcome_html(session: dict[str, object]) -> str:
            payload = {
                "sessions": [
                    {
                        "harness": "claude",
                        "sid": "outcome-owner",
                        "project": "alpha/outcome",
                        "state": "needs_input",
                        "title": "Title is context only",
                        "last_prompt": "Prompt is context only",
                        **session,
                    }
                ],
                "asks": [
                    {
                        "id": "outcome-ask",
                        "session_id": "outcome-owner",
                        "project": "alpha/outcome",
                        "question": "What next?",
                    }
                ],
            }
            html = self.render(payload)
            self.assertIn('data-next-attention-part="outcome"', html)
            return html.split('data-next-attention-part="outcome"', 1)[1].split("</p>", 1)[0]

        assignment = outcome_html(
            {"instruction": {"label": "asked", "text": "Ship the exact assignment"}}
        )
        one_goal = outcome_html(
            {
                "spacedock": {
                    "workflows": [
                        None,
                        {"workflow": "launch", "goal": "Ship the next page"},
                        {"workflow": "review", "goal": "Ship the next page"},
                    ]
                }
            }
        )
        conflicting = outcome_html(
            {
                "spacedock": {
                    "workflows": [
                        {"workflow": "launch", "goal": "Ship the next page"},
                        {"workflow": "review", "goal": "Check the release"},
                    ]
                }
            }
        )
        context_only = outcome_html({})

        self.assertIn("Ship the exact assignment", assignment)
        self.assertIn("Ship the next page", one_goal)
        self.assertIn("alpha/outcome", conflicting)
        self.assertNotIn("Ship the next page", conflicting)
        self.assertNotIn("Check the release", conflicting)
        for outcome in (assignment, one_goal, conflicting, context_only):
            self.assertNotIn("Title is context only", outcome)
            self.assertNotIn("Prompt is context only", outcome)

    def test_malformed_instruction_and_goal_values_fall_back_to_identity(self) -> None:
        malformed_values: tuple[object, ...] = ({"nested": "value"}, ["value"], 7)

        def outcome_html(session: dict[str, object]) -> str:
            html = self.render(
                {
                    "sessions": [
                        {
                            "harness": "claude",
                            "sid": "malformed-owner",
                            "project": "alpha/outcome",
                            "state": "needs_input",
                            **session,
                        }
                    ],
                    "asks": [
                        {
                            "id": "malformed-ask",
                            "session_id": "malformed-owner",
                            "project": "alpha/outcome",
                            "question": "What next?",
                        }
                    ],
                }
            )
            return html.split('data-next-attention-part="outcome"', 1)[1].split("</p>", 1)[0]

        outcomes = [
            outcome_html({"instruction": {"label": "asked", "text": value}})
            for value in malformed_values
        ]
        outcomes.extend(
            outcome_html({"spacedock": {"workflows": [{"workflow": "launch", "goal": value}]}})
            for value in malformed_values
        )

        for outcome in outcomes:
            self.assertIn(">IDENTITY<", outcome)
            self.assertIn("alpha/outcome", outcome)
            self.assertNotIn(">OUTCOME<", outcome)
            self.assertNotIn("[object Object]", outcome)

    def test_unrepresentable_reset_drops_checkpoint_without_taking_down_view(self) -> None:
        html = self.render(
            {
                "usage": [
                    {
                        "harness": "claude",
                        "state": "ok",
                        "fiveH": {"pct": 92, "resetAt": 1e300},
                    }
                ]
            }
        )

        self.assertIn("Quota pressure", html)
        self.assertNotIn('data-next-attention-part="next"', html)

    def test_hostile_payload_text_stays_text_and_does_not_change_subject_order(self) -> None:
        marker = "<img src=x onerror=alert(1)><script>alert(2)</script>"

        def payload(suffix: str) -> dict[str, object]:
            return {
                "generated": 10_000,
                "harnesses": [
                    {
                        "key": "claude",
                        "label": f"Claude {suffix}",
                        "discovered": True,
                        "reports_needs_input": True,
                        "reports_rate": True,
                        "error": "PermissionError: /tmp/transcript.jsonl",
                    },
                    {
                        "key": "codex",
                        "label": f"Codex {suffix}",
                        "discovered": True,
                        "reports_needs_input": True,
                        "reports_rate": True,
                        "error": None,
                    },
                ],
                "sessions": [
                    {
                        "harness": "codex",
                        "sid": f"ask/id:{suffix}",
                        "project": f"alpha/project:{suffix}",
                        "state": "needs_input",
                        "title": suffix,
                        "last_prompt": suffix,
                        "instruction": {"label": "asked", "text": f"Assignment {suffix}"},
                        "spacedock": {
                            "workflows": [{"workflow": suffix, "goal": f"Goal {suffix}"}]
                        },
                        "tasks": [{"subject": f"Task {suffix}", "status": "pending"}],
                        "path": f"/tmp/{suffix}",
                        "transcript_path": f"/tmp/transcript-{suffix}",
                    },
                    {
                        "harness": "codex",
                        "sid": "risk-owner",
                        "project": "beta/risk",
                        "state": "working",
                        "loop": {"errors": 4, "tool": f"Tool {suffix}"},
                    },
                    {
                        "harness": "codex",
                        "sid": "input-owner",
                        "project": "gamma/input",
                        "state": "needs_input",
                        "state_detail": f"Detail {suffix}",
                    },
                ],
                "asks": [
                    {
                        "id": "hostile-ask",
                        "session_id": f"ask/id:{suffix}",
                        "project": f"alpha/project:{suffix}",
                        "question": f"Question {suffix}",
                        "options": [f"Option {suffix}"],
                    }
                ],
                "usage": [
                    {
                        "harness": "codex",
                        "state": "ok",
                        "models": [{"label": f"Model {suffix}", "pct": 91}],
                    }
                ],
            }

        benign_model = self.model(payload("plain"))
        hostile_model = self.model(payload(marker))
        hostile_html = self.render(payload(marker))
        assert isinstance(benign_model, dict)
        assert isinstance(hostile_model, dict)

        self.assertEqual(
            [subject["primaryKind"] for subject in benign_model["needs"]],
            [subject["primaryKind"] for subject in hostile_model["needs"]],
        )
        self.assertEqual(
            [subject["primaryKind"] for subject in benign_model["risk"]],
            [subject["primaryKind"] for subject in hostile_model["risk"]],
        )
        self.assertIn("&lt;img", hostile_html)
        self.assertNotIn("<img", hostile_html)
        self.assertNotIn("<script", hostile_html)
        self.assertNotIn("onerror=", hostile_html)
        self.assertNotIn("PermissionError", hostile_html)
        self.assertNotIn("/tmp/transcript", hostile_html)
        self.assertIn("alpha%2Fproject%3A%3Cimg", hostile_html)
        self.assertIn("ask%2Fid%3A%3Cimg", hostile_html)

    def test_sections_show_three_initial_subjects_then_expand_without_reordering(self) -> None:
        payload = {
            "sessions": [
                {
                    "harness": "claude",
                    "sid": f"owner-{index}",
                    "project": f"project-{index}",
                    "state": "needs_input",
                }
                for index in range(4)
            ],
            "asks": [
                {
                    "id": f"ask-{index}",
                    "session_id": f"owner-{index}",
                    "project": f"project-{index}",
                    "question": f"Question {index}",
                    "age_sec": 400 - index,
                }
                for index in range(4)
            ],
        }
        encoded = json.dumps(payload)
        out = self._run_page_js(
            "\n".join(
                (
                    f"nextData = JSON.parse({json.dumps(encoded)});",
                    "const model = nextAttentionModel(nextData);",
                    "console.log(JSON.stringify({",
                    "  keys: model.needs.map(subject => subject.key),",
                    "  collapsed: nextAttentionView(model, new Set()),",
                    '  expanded: nextAttentionView(model, new Set(["needs"]))',
                    "}));",
                )
            )
        )

        self.assertEqual(4, len(out["keys"]))
        self.assertEqual(1, out["collapsed"].count("<li hidden>"))
        self.assertIn('aria-expanded="false"', out["collapsed"])
        self.assertIn("Show 1 more", out["collapsed"])
        self.assertNotIn("<li hidden>", out["expanded"])
        self.assertIn('aria-expanded="true"', out["expanded"])
        self.assertIn("Show fewer (hide 1)", out["expanded"])
        for html in (out["collapsed"], out["expanded"]):
            positions = [html.index(key.replace('"', "&quot;")) for key in out["keys"]]
            self.assertEqual(sorted(positions), positions)
            for key in out["keys"]:
                self.assertEqual(1, html.count(key.replace('"', "&quot;")))

    def test_attention_styles_cover_wide_narrow_focus_hit_targets_and_motion(self) -> None:
        self.assertIn("@media(min-width:900px)", NEXT_STYLES)
        self.assertIn("@media(max-width:899px)", NEXT_STYLES)
        self.assertIn("min-block-size:44px", NEXT_STYLES)
        self.assertIn("min-inline-size:44px", NEXT_STYLES)
        self.assertIn("overflow-wrap:anywhere", NEXT_STYLES)
        self.assertIn(".next-attention a:focus-visible", NEXT_STYLES)
        self.assertIn("prefers-reduced-motion:reduce", NEXT_STYLES)
        self.assertIsNone(re.search(r"(?:^|[;{])order:", NEXT_STYLES))
