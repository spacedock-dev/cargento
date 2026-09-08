from __future__ import annotations

import json
import re
import shutil
import unittest
from typing import Any

from .next_harness import NEXT_STYLES, NextPageJsHarness


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextAttentionV2Test(NextPageJsHarness):
    FIXTURE = """
__els.app = {innerHTML: ""};
nextData = {generated: 10000, ask: true, asks: [], harnesses: [
  {key: "claude", label: "Claude", reports_needs_input: true, reports_rate: true},
  {key: "antigravity", label: "Antigravity", reports_needs_input: false, reports_rate: false}
], sessions: [
  {harness: "claude", sid: "risk", project: "one", state: "working",
    title: "Inspect failures", loop: {errors: 4, tool: "Bash"}},
  {harness: "antigravity", sid: "quiet", project: "two", state: "idle"}
]};
nextRoute = {view: "attention", project: null, session: null};
"""

    def test_board_risks_do_not_move_the_observed_session_denominator(self) -> None:
        out = self._run_page_js(
            self.FIXTURE
            + """
const original = nextObserved(nextData);
nextData.usage = [{harness: "claude", state: "ok", week: {pct: 90}}];
const pressure = nextObserved(nextData);
nextData.sessions[1].project = "one";
const collision = nextObserved(nextData);
nextAttention = nextAttentionModel(nextData);
renderNext();
console.log(JSON.stringify({original, pressure, collision, html: __els.app.innerHTML}));
"""
        )
        assert isinstance(out, dict)
        for model in (out["original"], out["pressure"], out["collision"]):
            self.assertEqual(2, model["totals"]["sessions"])
            self.assertIn("1 of 2 sessions carry a subject", model["coverage"]["observed"])
        self.assertEqual(0, len(out["original"]["boardRisks"]))
        self.assertEqual(1, len(out["pressure"]["boardRisks"]))
        self.assertEqual(2, len(out["collision"]["boardRisks"]))
        self.assertIn("1 of 2 sessions carry a subject", out["html"])
        self.assertIn("not sessions, so not in that denominator", out["html"])

    def test_the_risk_note_tracks_the_sessions_and_cards_link_to_their_owner(self) -> None:
        out = self._run_page_js(
            self.FIXTURE
            + """
const variants = [];
for(let n = 2; n <= 3; n++){
  if(n === 3) nextData.sessions.push({harness: "claude", sid: "third", project: "three", state: "idle"});
  nextAttention = nextAttentionModel(nextData);
  const before = JSON.stringify(nextData);
  renderNext();
  variants.push({html: __els.app.innerHTML, unchanged: before === JSON.stringify(nextData)});
}
console.log(JSON.stringify(variants));
"""
        )
        assert isinstance(out, list)
        for count, row in enumerate(out, 2):
            self.assertTrue(row["unchanged"])
            self.assertIn(
                f"1 of {count} sessions · every one names the source that published it",
                row["html"],
            )
            self.assertIn('data-next-route="session:one:claude:risk"', row["html"])
            self.assertIn("source · claude", row["html"])

    def test_unknown_coverage_and_identity_collisions_keep_neutral_rules(self) -> None:
        html = self._run_page_js(
            self.FIXTURE
            + """
nextData.sessions[1].project = "one";
nextAttention = nextAttentionModel(nextData);
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)
        self.assertRegex(
            html,
            r'data-next-coverage-harness="antigravity"[\s\S]*?'
            r'class="next-attention-square" data-known="false"',
        )
        self.assertRegex(html, r'data-next-board-risk="collision" data-tone="unknown"')
        self.assertRegex(
            NEXT_STYLES,
            r"\.next-attention-square\{[^}]*background:var\(--line2\)",
        )
        self.assertRegex(
            NEXT_STYLES,
            r'\.next-attention-item\[data-tone="unknown"\]\{[^}]*border-left-color:var\(--line2\)',
        )
        self.assertIn("Not on this board yet", html)
        for code in ("C4", "C6", "C1", "F3", "E5"):
            self.assertIn(f'data-next-open="{code}"', html)

    def test_a_risk_owns_its_session_once_and_its_link_opens_that_session(self) -> None:
        out = self._run_page_js(
            self.FIXTURE
            + """
Object.assign(nextData.sessions[0], {state: "idle", loop: null,
  finished_at: 9000, dirty: true, changed: 3});
nextAttention = nextAttentionModel(nextData);
renderNext();
const attention = __els.app.innerHTML;
const route = attention.match(/data-next-route="(session:[^"]+)"/)[1];
__fire("click", {target: {closest(selector){
  return selector === "[data-next-route]" ? {dataset: {nextRoute: route}} : null;
}}, preventDefault(){}, stopPropagation(){}});
renderNext();
console.log(JSON.stringify({attention, route: nextRoute, html: __els.app.innerHTML}));
"""
        )
        assert isinstance(out, dict)
        key = 'data-next-attention-subject="session:[&quot;claude&quot;,&quot;risk&quot;]"'
        self.assertEqual(1, out["attention"].count(key))
        self.assertEqual("session", out["route"]["view"])
        self.assertEqual("risk", out["route"]["session"])
        self.assertIn('data-next-session-detail="risk"', out["html"])

    def test_a_risk_keeps_its_published_assignment(self) -> None:
        html = self._run_page_js(
            self.FIXTURE
            + """
nextData.sessions[0].instruction = {label: "asked", text: "Keep the assigned outcome visible"};
nextAttention = nextAttentionModel(nextData);
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        self.assertIn("Keep the assigned outcome visible", html)

    def test_per_model_quota_pressure_stays_off_the_session_count(self) -> None:
        html = self._run_page_js(
            self.FIXTURE
            + """
nextData.usage = [{harness: "claude", state: "ok", models: [{label: "Extra model", pct: 95}]}];
nextAttention = nextAttentionModel(nextData);
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)
        board = html.split('data-next-attention-section="board-risk"', 1)[1]
        self.assertIn("Extra model", board)
        self.assertIn("95% reported", board)
        self.assertIn("1 of 2 sessions carry a subject", html)


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextAttentionBehaviorTest(NextPageJsHarness):
    def test_partial_coverage_counts_sessions_instead_of_gap_names(self) -> None:
        html = self.render(
            {
                "sessions": [
                    {
                        "harness": "claude",
                        "sid": "a",
                        "project": "a",
                        "state": "working",
                        "source_gaps": ["message history", "token accounting", "token accounting"],
                    },
                    {
                        "harness": "copilot",
                        "sid": "b",
                        "project": "b",
                        "state": "idle",
                        "source_gaps": ["token accounting"],
                    },
                ],
                "asks": [],
            }
        )
        self.assertIn("of these, 2 partially read", html)
        self.assertNotIn("NO PUBLISHED EXCEPTION", html)
        self.assertIn("The other 2: 1 moving · 1 quiet", html)
        self.assertIn("1 moving · 1 quiet", html)

    def test_a_partially_read_remainder_qualifies_both_attention_summaries(self) -> None:
        cases = [
            (["message history", "token accounting"], "idle", 1),
            (["token accounting"], "working", 1),
            ([None, {}, " ", " token accounting "], "working", 1),
            ([], "idle", 0),
            ("token accounting", "idle", 0),
            ([None, {}, " "], "idle", 0),
        ]
        for gaps, state, partial in cases:
            for mixed in (False, True):
                with self.subTest(gaps=gaps, state=state, mixed=mixed):
                    out = self._run_page_js(
                        f"""
__els.app = {{innerHTML: ""}};
const row = {{harness: "copilot", sid: "partial", project: "partial/repo",
  active: true, state: {json.dumps(state)}, source_gaps: {json.dumps(gaps)}}};
nextData = {{generated: 10000, sessions: [row], asks: []}};
if({json.dumps(mixed)}) nextData.sessions.push(
  {{harness: "claude", sid: "clean", project: "clean/repo", state: "idle"}},
  {{harness: "claude", sid: "gate", project: "gate/repo", state: "needs_input",
    source_gaps: ["message history"]}}
);
const original = JSON.stringify(nextData);
nextAttention = nextAttentionModel(nextData);
nextRoute = {{view: "attention", project: null, session: null}};
renderNext();
console.log(JSON.stringify({{html: __els.app.innerHTML, healthy: nextAttention.healthy,
  unread: nextSessionUnread(row), observed: nextObserved(nextData), unchanged: original === JSON.stringify(nextData)}}));
"""
                    )
                    assert isinstance(out, dict)
                    html = out["html"]
                    brief = html.split('class="next-attention-brief"', 1)[1].split("</p>", 1)[0]
                    healthy = out["healthy"]
                    self.assertTrue(out["unchanged"])
                    self.assertEqual(partial, healthy.get("partial"))
                    self.assertEqual(int(state == "working"), healthy["moving"])
                    self.assertEqual(int(state == "idle") + int(mixed), healthy["quiet"])
                    self.assertEqual(0, healthy["unknown"])
                    self.assertEqual(1 + int(mixed), len(healthy["sessions"]))
                    self.assertIn(out["observed"]["coverage"]["quiet"], brief)
                    self.assertNotIn("NO PUBLISHED EXCEPTION", html)
                    if partial:
                        self.assertIn("Source not fully read:", out["unread"])
                    else:
                        self.assertEqual("", out["unread"])

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

    def test_the_risk_row_counts_the_turn_total_and_names_a_barren_turn(self) -> None:
        # The one-liner said the peak run, which understates a turn a success
        # split in two: six failures read as "failed 3 times" (DRC-4021).
        def one(sid: str, loop: dict[str, object]) -> dict[str, object]:
            return {
                "harness": "claude",
                "sid": sid,
                "project": "alpha/repo",
                "state": "working",
                "loop": loop,
            }

        split = self.render({"sessions": [one("s", {"errors": 3, "failures": 6, "tool": "Bash"})]})
        self.assertIn("Bash failed 6 times", split)
        self.assertNotIn("Bash failed 3 times", split)

        barren = self.render(
            {"sessions": [one("s", {"errors": 3, "failures": 3, "barren": True, "tool": "Bash"})]}
        )
        self.assertIn("Bash failed 3 times, nothing succeeded", barren)

        # No tool name, and the barren clause still lands on the other subject.
        anon = self.render({"sessions": [one("s", {"errors": 3, "failures": 4, "barren": True})]})
        self.assertIn("Tool failures reported 4 times, nothing succeeded", anon)

        # Two producers reach this shape now: a payload from before DRC-4021, and
        # a turn the scanner could not finish, which withholds both readings
        # (turns.py). Rendering them alike is deliberate.
        legacy = self.render({"sessions": [one("s", {"errors": 4, "tool": "Bash"})]})
        self.assertIn("Bash failed 4 times", legacy)
        self.assertNotIn("nothing succeeded", legacy)

    def test_the_turn_total_ranks_the_risk_rows_not_the_peak_run(self) -> None:
        # Ordering by the peak put the worse turn second: six failures split by
        # one success ranked below four in a row.
        model = self.model(
            {
                "sessions": [
                    {
                        "harness": "claude",
                        "sid": "run-of-four",
                        "project": "alpha/four",
                        "state": "working",
                        "loop": {"errors": 4, "failures": 4, "tool": "Bash"},
                    },
                    {
                        "harness": "claude",
                        "sid": "six-split",
                        "project": "beta/six",
                        "state": "working",
                        "loop": {"errors": 3, "failures": 6, "tool": "Bash"},
                    },
                ]
            }
        )
        assert isinstance(model, dict)
        self.assertEqual(
            ['session:["claude","six-split"]', 'session:["claude","run-of-four"]'],
            [subject["key"] for subject in model["risk"]],
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
        # `endedAt: None` joined the detail with DRC-4036, and None is the claim:
        # these rows carry a stop and no observed end, which is not the same as
        # a session known to still be running.
        self.assertEqual(
            {"finishedAt": 7_000, "endedAt": None, "changedEntries": 3},
            close["signals"][0]["detail"],
        )
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
        # `"other"` above is fabricated, and deliberately so. No collector can
        # publish it: the only `session_state =` assignments in the runtime are
        # "needs_input" and "working", aggregate.py's _STATE_RANK admits those
        # two plus "idle", and sessions.py publishes "idle" directly. So this
        # asserts the ARITHMETIC — that moving, quiet and unknown partition the
        # healthy set exactly — and not that a third state is reachable. It is
        # kept because the brief's two clauses now have to sum to sessionCount,
        # and unknown is the residue that keeps them summing if the vocabulary
        # ever widens. Read this as a partition oracle, not as evidence of a
        # state anything emits.
        self.assertEqual(1, model["healthy"]["unknown"])
        self.assertEqual(
            len(model["healthy"]["sessions"]),
            model["healthy"]["moving"] + model["healthy"]["quiet"] + model["healthy"]["unknown"],
        )

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
        self.assertIn("The other 1: 1 quiet", agy_html)
        self.assertNotIn("AGY is clear", agy_html)
        self.assertIn("1 failed", failure_html)
        self.assertNotIn("PermissionError", failure_html)
        self.assertNotIn("/Users/private/transcript.jsonl", failure_html)

    def _capability_rows(self) -> list[dict[str, Any]]:
        """Four discovered rows: plain, qualified, capability-off, and failed."""
        return [
            {
                "key": "claude",
                "label": "Claude Code",
                "discovered": True,
                "reports_needs_input": True,
                "reports_needs_input_when": None,
                "reports_rate": True,
                "error": None,
            },
            {
                "key": "codex",
                "label": "Codex",
                "discovered": True,
                "reports_needs_input": True,
                "reports_needs_input_when": "where approvals are enabled",
                "reports_rate": True,
                "error": None,
            },
            {
                "key": "antigravity",
                "label": "AGY",
                "discovered": True,
                "reports_needs_input": False,
                "reports_needs_input_when": "where a caveat would be noise",
                "reports_rate": True,
                "error": None,
            },
            {
                "key": "broken",
                "label": "Broken",
                "discovered": True,
                "reports_needs_input": True,
                "reports_needs_input_when": "where a caveat would be noise",
                "reports_rate": True,
                "error": "PermissionError: /Users/private/transcript.jsonl",
            },
        ]

    def test_a_gate_capability_carries_its_condition_only_where_it_reports(self) -> None:
        # A harness can have a gate mechanism and still be unable to fire it:
        # Codex's is a permission hook, and an operator running with approvals
        # off never reaches it, so the row has to say what the capability
        # depends on or its silence reads as the all-clear.
        #
        # Only on a row that reports. A caveat on "unknown" or "failed"
        # qualifies a capability the line has already said is absent, so it
        # would be noise on the two rows the reader needs least noise on.
        html = self.render({"harnesses": self._capability_rows(), "sessions": [], "asks": []})

        self.assertIn(
            "needs-input reporting, where approvals are enabled ·",
            html,
        )
        self.assertIn("needs-input reporting ·", html)
        self.assertIn("Harness does not report blocks ·", html)
        self.assertIn("Harness source could not be read ·", html)
        self.assertNotIn("where a caveat would be noise", html)
        # The condition qualifies the capability; it does not withdraw it. The
        # mechanism exists, so the count that says how much of the board can
        # report a gate at all is the same with the caveat as without it.
        self.assertIn("Harness sources: 1 failed", html)
        self.assertEqual(5, html.count('data-known="true"'))

    def test_the_gate_condition_is_escaped_like_the_label_beside_it(self) -> None:
        # A registry constant today, and reaching HTML regardless. Escaped on
        # the same rule as the harness label two spans over rather than on a
        # reading of where today's value comes from.
        rows = self._capability_rows()
        rows[1]["reports_needs_input_when"] = 'where <b>approvals</b> are "on"'
        html = self.render({"harnesses": rows, "sessions": [], "asks": []})

        self.assertIn("where &lt;b&gt;approvals&lt;/b&gt; are", html)
        self.assertNotIn("<b>approvals</b>", html)

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

        self.assertIn("The other 1: 1 quiet", html)
        self.assertNotIn("HEALTHY FLEET", html)
        self.assertIn("Harness does not report blocks", html)
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
        self.assertEqual(6, html.count("<h2"))
        self.assertEqual(3, html.count('<ol id="next-attention-'))
        self.assertEqual(4, html.count("<li><article"))
        self.assertEqual(3, html.count('data-next-attention-part="why"><a '))
        self.assertEqual(1, html.count('<details class="next-attention-coverage-details">'))
        self.assertNotIn('<details class="next-attention-coverage-details" open', html)
        ask_item = html.split(
            'data-next-attention-subject="session:[&quot;claude&quot;,&quot;ask-owner&quot;]"', 1
        )[1]
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
        self.assertIn('href="#n=projects"', html)
        self.assertNotIn('data-next-attention-section="healthy"', html)

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
            "Stuck signal",
            "Bash failed 4 times",
            "Long working turn",
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
        self.assertIn("estimated remaining", html)
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

    # Fires the real click at the real listener, so the target answers only the
    # selector the branch under test asks for and every earlier branch in the
    # handler sees the null it would see in a browser.
    CLICK_HELPER = """
const __clickOn = (selector, dataset) => __fire("click", {
  target: {closest(candidate){ return candidate === selector ? {dataset} : null; }},
  preventDefault(){}, stopPropagation(){}
});
"""

    QUEUE_OF_FOUR = """
__els.app = {innerHTML: ""};
nextData = {
  generated: 10000,
  sessions: [0, 1, 2, 3].map(index => ({
    harness: "claude", sid: `owner-${index}`, project: `project-${index}`,
    state: "needs_input"
  })),
  asks: [0, 1, 2, 3].map(index => ({
    id: `ask-${index}`, session_id: `owner-${index}`, project: `project-${index}`,
    question: `Question ${index}`, age_sec: 400 - index
  }))
};
nextAttention = nextAttentionModel(nextData);
nextRoute = {view: "attention", project: null, session: null};
"""

    def test_the_brief_does_not_say_nothing_is_moving_while_two_sessions_work(self) -> None:
        # The reachable half of the mismatch, and the repository's own everyday
        # shape. Two agents in ONE project become a single `collision` subject,
        # which makes both sessions `represented`, which excludes them from
        # `healthy` — and `moving` counts healthy sessions only. So the line read
        # `0 moving` with two agents actively working, six numbers totalling 1
        # against 2 sessions, and nothing on screen said what the numbers were of.
        out = self._run_page_js(
            """
__els.app = {innerHTML: ""};
nextData = {
  generated: 10000,
  sessions: [0, 1].map(index => ({
    harness: "claude", sid: `owner-${index}`, project: "acme/api", state: "working"
  })),
  asks: []
};
nextAttention = nextAttentionModel(nextData);
nextRoute = {view: "attention", project: null, session: null};
renderNext();
console.log(JSON.stringify({
  html: __els.app.innerHTML,
  sessionCount: nextAttention.sessionCount,
  counts: nextAttention.counts
}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual(2, out["sessionCount"])
        self.assertEqual(0, out["counts"]["moving"])
        # The model is right; the sentence was not. What the reader must not be
        # told is that nothing is moving.
        self.assertNotIn("0 moving", out["html"])
        # And the subject clause must carry its own denominator, the way the
        # fleet strip's coverage line does (next-sessions.js:99-104).
        self.assertIn("0 of 2 sessions carry a subject", out["html"])
        self.assertIn("2 moving", out["html"])

    def test_an_empty_payload_does_not_get_a_line_of_zeroes(self) -> None:
        # Found on a real board during the after-walk, and introduced by the
        # change above: the two-clause sentence is longer than the six numbers it
        # replaced, so on an empty payload it read "0 subjects across 0 of 0
        # sessions: 0 need you · 0 at risk · ..." directly above the notice that
        # already says there is nothing. The notice is the better sentence, so
        # the brief stands down rather than competing with it.
        out = self._run_page_js(
            """
__els.app = {innerHTML: ""};
nextData = {generated: 10000, sessions: [], asks: [], window_hours: 6};
nextAttention = nextAttentionModel(nextData);
nextRoute = {view: "attention", project: null, session: null};
renderNext();
console.log(JSON.stringify({html: __els.app.innerHTML}));
"""
        )
        assert isinstance(out, dict)
        self.assertIn("No sessions in this 6h payload", out["html"])
        self.assertNotIn("0 need you", out["html"])
        self.assertIn("0 of 0 sessions carry a subject", out["html"])
        # The label goes with it; an OBSERVED NOW with nothing after it is worse.
        self.assertNotIn("OBSERVED NOW", out["html"])

    def test_the_brief_accounts_for_every_session_in_stated_units(self) -> None:
        # Payload (D): two colliding, one working, one idle. Six numbers totalled
        # 3 against 4 sessions, because four of them count SUBJECTS and two count
        # SESSIONS. Both halves now name their denominator, so the two add up.
        out = self._run_page_js(
            """
__els.app = {innerHTML: ""};
nextData = {
  generated: 10000,
  sessions: [
    {harness: "claude", sid: "a", project: "acme/api", state: "working"},
    {harness: "claude", sid: "b", project: "acme/api", state: "working"},
    {harness: "claude", sid: "c", project: "acme/web", state: "working"},
    {harness: "claude", sid: "d", project: "acme/ops", state: "idle"}
  ],
  asks: []
};
nextAttention = nextAttentionModel(nextData);
nextRoute = {view: "attention", project: null, session: null};
renderNext();
console.log(JSON.stringify({
  html: __els.app.innerHTML,
  sessionCount: nextAttention.sessionCount,
  healthy: nextAttention.healthy.sessions.length
}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual(4, out["sessionCount"])
        self.assertEqual(2, out["healthy"])
        self.assertIn("0 of 4 sessions carry a subject", out["html"])
        self.assertIn("The other 4: 3 moving · 1 quiet", out["html"])

    def test_the_project_row_names_the_unit_of_its_subject_counts(self) -> None:
        # The same two units, in a milder form: here `working` and `quiet` count
        # ALL of the project's sessions rather than only unrepresented ones, so
        # no number is wrong. But `risk` and `close` are still subject counts
        # sitting unlabelled in a list that opens with a session total, so
        # "2 sessions · 1 at risk · 2 working" invites the reader to subtract.
        out = self._run_page_js(
            """
__els.app = {innerHTML: ""};
nextData = {
  generated: 10000,
  sessions: [0, 1].map(index => ({
    harness: "claude", sid: `owner-${index}`, project: "acme/api",
    state: "working", active: true, last_activity: 9999
  })),
  asks: []
};
nextAttention = nextAttentionModel(nextData);
nextRoute = {view: "projects", project: null, session: null};
renderNext();
console.log(JSON.stringify({html: __els.app.innerHTML}));
"""
        )
        assert isinstance(out, dict)
        self.assertIn("2 sessions", out["html"])
        self.assertIn("2 working", out["html"])
        # The project names its measured shared-label scope; board risk stays separate.
        self.assertIn(
            "2 sessions share this display label; shared location is not established", out["html"]
        )
        self.assertNotIn(">1 at risk<", out["html"])

    def test_a_section_the_reader_expanded_is_still_expanded_after_a_render(self) -> None:
        # The pair above hands the view a set; this one earns the set from a
        # click, which nothing did before — the handler that owns
        # `nextAttentionExpandedSections` had no test on it at all.
        out = self._run_page_js(
            self.CLICK_HELPER
            + self.QUEUE_OF_FOUR
            + """
const expand = () => __clickOn("[data-next-attention-toggle]", {nextAttentionToggle: "needs"});
renderNext();
const collapsed = __els.app.innerHTML;
expand();
const expanded = __els.app.innerHTML;
renderNext();
const survived = __els.app.innerHTML;
expand();
const recollapsed = __els.app.innerHTML;
console.log(JSON.stringify({collapsed, expanded, survived, recollapsed}));
"""
        )
        assert isinstance(out, dict)

        self.assertEqual(1, out["collapsed"].count("<li hidden>"))
        self.assertIn("Show 1 more", out["collapsed"])
        # The click renders for itself, and the render after it — the revision or
        # the bare interval — must reach the same markup rather than collapsing
        # the reader's section under them.
        for html in (out["expanded"], out["survived"]):
            self.assertNotIn("<li hidden>", html)
            self.assertIn('aria-expanded="true"', html)
            self.assertIn("Show fewer (hide 1)", html)
        self.assertEqual(out["expanded"], out["survived"])
        self.assertEqual(out["collapsed"], out["recollapsed"])

    def test_the_coverage_panel_keeps_the_readers_open_and_closed_choice_after_redraws(
        self,
    ) -> None:
        # `renderNext` assigns the app's whole innerHTML, so the open state the
        # browser keeps on a `<details>` node dies with the node: the panel
        # closed itself under the reader on the next revision, or within 20
        # seconds on the bare interval (DRC-4410). The page has to own it.
        out = self._run_page_js(
            self.CLICK_HELPER
            + self.QUEUE_OF_FOUR
            + """
const summary = () => __clickOn("[data-next-disclosure]", {nextDisclosure: "attention-coverage"});
renderNext();
const closed = __els.app.innerHTML;
summary();
renderNext();
const opened = __els.app.innerHTML;
renderNext();
const survived = __els.app.innerHTML;
summary();
renderNext();
const reclosed = __els.app.innerHTML;
renderNext();
const closedSurvived = __els.app.innerHTML;
console.log(JSON.stringify({closed, opened, survived, reclosed, closedSurvived}));
"""
        )
        assert isinstance(out, dict)

        tag = '<details class="next-attention-coverage-details"'
        for html in (out["closed"], out["reclosed"], out["closedSurvived"]):
            self.assertIn(f"{tag}>", html)
            self.assertNotIn(f"{tag} open", html)
        for html in (out["opened"], out["survived"]):
            self.assertIn(f"{tag} open>", html)
        self.assertEqual(out["closed"], out["reclosed"])

    def gate_queue_payload(self, harness: str, resume_id: object) -> dict[str, Any]:
        session: dict[str, Any] = {
            "harness": harness,
            "sid": "sid-published",
            "project": "alpha/repo",
            "state": "needs_input",
            "blocked_since": 9_400,
            "title": "Waiting on you",
        }
        if resume_id is not None:
            session["resume_id"] = resume_id
        return {
            "generated": 10_000,
            "harnesses": [{"key": harness, "label": harness.title()}],
            "sessions": [session],
            "asks": [],
        }

    def test_a_gate_queue_row_carries_the_re_entry_command_for_its_own_harness(self) -> None:
        # The command is built from the published id, never from `cwd`: SECURITY.md
        # keeps the working directory a matching hint, and nothing here needs it.
        claude = self.render(
            self.gate_queue_payload("claude", "27d10654-1cb5-481e-8194-6ce868b91bb5")
        )
        self.assertIn(
            'data-next-copy-command="claude --resume 27d10654-1cb5-481e-8194-6ce868b91bb5"',
            claude,
        )
        self.assertIn("COPY COMMAND", claude)

        codex = self.render(
            self.gate_queue_payload("codex", "01a06fac-629f-7c40-9c86-f84c55680151")
        )
        self.assertIn(
            'data-next-copy-command="codex resume 01a06fac-629f-7c40-9c86-f84c55680151"',
            codex,
        )

    def test_no_control_without_a_documented_verb_a_published_id_or_a_shell_safe_one(self) -> None:
        # Four ways to have nothing honest to offer, and all of them render the same
        # row the reader saw before: a harness whose CLI documents no re-entry verb,
        # one whose verb is documented but whose id the payload does not publish,
        # a published id that a shell would read as more than one word, and one a
        # shell reads as a single word that the CLI reads as a flag. The last is the
        # shape quoting would not have caught: `claude --resume` takes an optional
        # value and so never consumes a `-`-leading token, which would leave the
        # reader pasting a permission bypass with the session id silently dropped.
        for harness, resume_id in (
            ("gemini", "aaaa1111-cccc-4444-8888-000000000001"),
            ("claude", None),
            ("claude", "id; rm -rf ~"),
            ("claude", "--dangerously-skip-permissions"),
            ("codex", "--dangerously-bypass-approvals-and-sandbox"),
            ("codex", ""),
        ):
            with self.subTest(harness=harness, resume_id=resume_id):
                html = self.render(self.gate_queue_payload(harness, resume_id))
                self.assertNotIn("data-next-copy-command", html)
                self.assertNotIn("COPY COMMAND", html)

    def test_the_re_entry_command_rides_the_gate_queue_and_no_other_section(self) -> None:
        # A row in AT RISK is not a row waiting on an answer, so it gets no control:
        # the affordance is the gate queue's, and spreading it to every section is
        # how a small control becomes furniture.
        payload = self.gate_queue_payload("claude", "27d10654-1cb5-481e-8194-6ce868b91bb5")
        payload["sessions"][0]["state"] = "working"
        payload["sessions"][0]["active"] = True
        del payload["sessions"][0]["blocked_since"]
        payload["sessions"][0]["loop"] = {"errors": 4, "tool": "Bash"}
        model = self.model(payload)
        assert isinstance(model, dict)
        self.assertEqual([], model["needs"])
        self.assertEqual(1, len(model["risk"]))
        self.assertNotIn("data-next-copy-command", self.render(payload))

    # The capability the server injects into the served document at
    # `cli.inject_focus_capability`. Supplied through the prelude rather than
    # through the payload because that is where the real one arrives: SECURITY.md
    # keeps it out of `/api/data`, so a page that reads it from anywhere else is
    # reading something the server never sends.
    FOCUS_META_PRELUDE = """
document.querySelector = selector => selector === 'meta[name="cargento-focus"]'
  ? {getAttribute: name => (name === "content" ? "0a1b2c3d" : null)}
  : null;
"""

    def render_with_capability(self, payload: object) -> str:
        encoded = json.dumps(payload)
        rendered = self._run_page_js(
            "\n".join(
                (
                    f"nextData = JSON.parse({json.dumps(encoded)});",
                    "console.log(JSON.stringify(nextAttentionView(nextAttentionModel(nextData))));",
                )
            ),
            self.FOCUS_META_PRELUDE,
        )
        assert isinstance(rendered, str)
        return rendered

    def raise_payload(self, focusable: object) -> dict[str, Any]:
        payload = self.gate_queue_payload("claude", "27d10654-1cb5-481e-8194-6ce868b91bb5")
        if focusable is not None:
            payload["sessions"][0]["focusable"] = focusable
        return payload

    def test_a_gate_queue_row_with_a_terminal_raises_beside_the_copy_never_over_it(self) -> None:
        # The copy always works; the raise resolves its target at the moment of the
        # raise and so cannot be promised at render. Drawing it in place of the copy
        # would leave the reader with less than the affordance that always works.
        html = self.render_with_capability(self.raise_payload(True))

        self.assertIn('data-next-raise-session="sid-published"', html)
        self.assertIn('data-next-raise-harness="claude"', html)
        self.assertIn(">RAISE<", html)
        self.assertIn("COPY COMMAND", html)
        self.assertLess(html.index("COPY COMMAND"), html.index(">RAISE<"))
        # Its own class and its own resting look, so the reversible control and the
        # irreversible one do not differ by label alone.
        self.assertIn('class="next-session-raise', html)
        self.assertNotIn('class="next-session-copy next-session-raise', html)
        # No `title`: the copy control's title carries its own payload as the
        # clipboard fallback, and the focus contract forbids echoing a target, so
        # there is nothing a raise could put there.
        raise_button = html[html.index("data-next-raise-session") : html.index(">RAISE<")]
        self.assertNotIn("title=", raise_button)
        # The whole name. `aria-label=` alone admitted one naming the target,
        # which is the clause SECURITY.md governs (DRC-4017 review).
        self.assertIn('aria-label="Raise the terminal this session is running in"', raise_button)

        # The two controls are independent: the event envelope carries the terminal
        # identity for any harness, so a session whose CLI documents no re-entry
        # verb can still report one. The raise stands alone there rather than being
        # withheld for want of a copy to sit beside.
        alone = self.gate_queue_payload("gemini", None)
        alone["sessions"][0]["focusable"] = True
        rendered = self.render_with_capability(alone)
        self.assertIn(">RAISE<", rendered)
        self.assertNotIn("data-next-copy-command", rendered)

    def test_no_raise_without_a_reported_terminal_and_none_without_the_run_capability(self) -> None:
        # Three ways to have nothing to offer. `focusable` false is the majority
        # answer — a session outside tmux, one predating this server run, or any
        # Linux or Windows session — and a missing capability is the feature off for
        # the run, where a request could only ever be refused.
        for focusable in (None, False, "true"):
            with self.subTest(focusable=focusable):
                self.assertNotIn(
                    "data-next-raise-session",
                    self.render_with_capability(self.raise_payload(focusable)),
                )
        self.assertNotIn("data-next-raise-session", self.render(self.raise_payload(True)))

    def test_the_raise_rides_the_gate_queue_and_no_other_section(self) -> None:
        payload = self.raise_payload(True)
        payload["sessions"][0]["state"] = "working"
        payload["sessions"][0]["active"] = True
        del payload["sessions"][0]["blocked_since"]
        payload["sessions"][0]["loop"] = {"errors": 4, "tool": "Bash"}
        model = self.model(payload)
        assert isinstance(model, dict)
        self.assertEqual([], model["needs"])
        self.assertEqual(1, len(model["risk"]))
        self.assertNotIn("data-next-raise-session", self.render_with_capability(payload))

    def test_terminal_reach_is_stated_once_in_coverage_rather_than_on_every_row(self) -> None:
        # A per-row "no terminal" would print on the majority of rows forever. The
        # queue says how far the feature reaches once, where the rest of what the
        # board cannot see is already recorded.
        payload = self.raise_payload(True)
        payload["sessions"].append(
            {
                "harness": "claude",
                "sid": "sid-elsewhere",
                "project": "alpha/repo",
                "state": "needs_input",
                "blocked_since": 9_300,
                "title": "Also waiting",
            }
        )
        # One row first, so the singular branch is rendered rather than assumed.
        lone = self.render_with_capability(self.raise_payload(True))
        self.assertIn("Terminal raise: 1 of 1 waiting row carries a terminal", lone)

        html = self.render_with_capability(payload)
        self.assertIn("Terminal raise: 1 of 2 waiting rows carry a terminal", html)
        self.assertEqual(1, html.count("Terminal raise:"))
        self.assertEqual(1, html.count("data-next-raise-session"))

        off = self.render(payload)
        self.assertIn("Terminal raise: off for this run", off)
        self.assertNotIn("data-next-raise-session", off)

    def test_attention_styles_cover_wide_narrow_focus_hit_targets_and_motion(self) -> None:
        self.assertIn("@media(min-width:900px)", NEXT_STYLES)
        self.assertIn("@media(max-width:899px)", NEXT_STYLES)
        self.assertIn("min-block-size:44px", NEXT_STYLES)
        self.assertIn("min-inline-size:44px", NEXT_STYLES)
        self.assertIn("overflow-wrap:anywhere", NEXT_STYLES)
        self.assertIn(".next-attention a:focus-visible", NEXT_STYLES)
        self.assertIn("prefers-reduced-motion:reduce", NEXT_STYLES)
        self.assertIsNone(re.search(r"(?:^|[;{])order:", NEXT_STYLES))


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextAttentionSessionEndTest(NextPageJsHarness):
    """DRC-4036: a session that is over must not render as one waiting for you."""

    def model(self, sessions: list[dict[str, Any]]) -> Any:
        payload = {"generated": 10_000, "sessions": sessions}
        return self._run_page_js(
            "\n".join(
                (
                    f"nextData = JSON.parse({json.dumps(json.dumps(payload))});",
                    "console.log(JSON.stringify(nextAttentionModel(nextData)));",
                )
            )
        )

    def render(self, sessions: list[dict[str, Any]]) -> str:
        payload = {"generated": 10_000, "sessions": sessions}
        rendered = self._run_page_js(
            "\n".join(
                (
                    f"nextData = JSON.parse({json.dumps(json.dumps(payload))});",
                    "console.log(JSON.stringify(nextAttentionView(nextAttentionModel(nextData))));",
                )
            )
        )
        assert isinstance(rendered, str)
        return rendered

    def row(self, **overrides: Any) -> dict[str, Any]:
        session = {
            "harness": "claude",
            "sid": "ended-1",
            "project": "alpha/repo",
            "state": "idle",
            "last_activity": 9_000,
        }
        session.update(overrides)
        return session

    def test_an_ended_session_reaches_close_the_loop_with_no_stop_beside_it(self) -> None:
        # The lane N-12 exists to strengthen. `nextAttentionStopSignal` used to
        # require a stop AND the idle state, so a session that reported its own
        # end and had no observed stop dropped out of CLOSE THE LOOP entirely —
        # the strongest evidence the section has, discarded for want of a weaker
        # one.
        model = self.model([self.row(ended_at=9_400)])
        assert isinstance(model, dict)
        self.assertEqual(1, len(model["close"]))
        self.assertEqual("end-unknown", model["close"][0]["primaryKind"])
        self.assertEqual(9_400, model["close"][0]["signals"][0]["detail"]["endedAt"])

    def test_an_end_promotes_the_row_whatever_the_scan_says_the_state_is(self) -> None:
        # An end is an observed event and `state` is a collector inference off
        # file recency, so requiring the two to agree would let the weaker
        # reading veto the stronger one.
        model = self.model([self.row(state="working", ended_at=9_400)])
        assert isinstance(model, dict)
        self.assertEqual(["end-unknown"], [item["primaryKind"] for item in model["close"]])

    def test_the_git_reading_still_separates_the_three_endings(self) -> None:
        # Every row carrying a git reading carries a stop too, because
        # `events._side_channel_patch` publishes the reading only alongside a
        # fresh `finished_at`. Distinct projects so the identity-collision
        # subject does not take these rows over.
        model = self.model(
            [
                self.row(
                    sid="e-dirty",
                    project="a/one",
                    finished_at=9_350,
                    ended_at=9_400,
                    dirty=True,
                    changed=3,
                ),
                self.row(
                    sid="e-clean",
                    project="a/two",
                    finished_at=9_250,
                    ended_at=9_300,
                    dirty=False,
                    changed=0,
                ),
                self.row(sid="e-none", project="a/three", ended_at=9_200),
            ]
        )
        assert isinstance(model, dict)
        self.assertEqual(
            ["end-dirty", "end-unknown", "end-clean"],
            [item["primaryKind"] for item in model["close"]],
        )

    def test_uncommitted_work_outranks_an_end_that_left_nothing_behind(self) -> None:
        # Ordering inside CLOSE THE LOOP is by what is at stake, so the git
        # reading leads and the end breaks its ties. An ended dirty tree is the
        # one nobody is coming back to.
        model = self.model(
            [
                self.row(
                    sid="e-clean",
                    project="a/one",
                    finished_at=9_250,
                    ended_at=9_300,
                    dirty=False,
                    changed=0,
                ),
                self.row(sid="s-dirty", project="a/two", finished_at=9_100, dirty=True, changed=2),
                self.row(
                    sid="e-dirty",
                    project="a/three",
                    finished_at=9_350,
                    ended_at=9_400,
                    dirty=True,
                    changed=3,
                ),
            ]
        )
        assert isinstance(model, dict)
        self.assertEqual(
            ["end-dirty", "stop-dirty", "end-clean"],
            [item["primaryKind"] for item in model["close"]],
        )

    def test_a_session_with_no_observed_end_is_never_called_ended(self) -> None:
        # Absence covers a SIGKILL, an adapter-less harness, a session predating
        # this server run and `--no-events`, so it may never be read as an end.
        model = self.model([self.row(finished_at=9_100, dirty=False, changed=0)])
        assert isinstance(model, dict)
        self.assertEqual("stop-clean", model["close"][0]["primaryKind"])
        self.assertIsNone(model["close"][0]["signals"][0]["detail"]["endedAt"])

    def test_the_rendered_card_says_the_session_ended_and_when(self) -> None:
        html = self.render([self.row(finished_at=9_350, ended_at=9_400, dirty=True, changed=3)])
        self.assertIn("Session ended with uncommitted work", html)
        self.assertIn("3 changed entries", html)
        self.assertIn("ended 10m ago", html)

    def test_coverage_counts_ends_and_refuses_to_read_silence_as_life(self) -> None:
        html = self.render([self.row(ended_at=9_400), self.row(sid="quiet-1")])
        self.assertIn("Ends observed on 1 session", html)
        self.assertIn("a session with no observed end is not known to be running", html)

    def test_coverage_says_so_when_no_end_was_observed_at_all(self) -> None:
        html = self.render([self.row(sid="quiet-1")])
        self.assertIn("No session ends observed", html)
        self.assertIn("a session with no observed end is not known to be running", html)

    def test_the_always_visible_coverage_line_carries_the_end_count(self) -> None:
        # The summary sentence renders above the collapsed details on every
        # payload, so a key that does not exist shows every reader `undefined`
        # rather than only the one who expands coverage. Asserted on the half
        # before the `<details>` for exactly that reason.
        html = self.render([self.row(ended_at=9_400), self.row(sid="quiet-1")])
        visible = html.split('<details class="next-attention-coverage-details"')[0]

        self.assertIn("ends observed on 1 session", visible)
        self.assertNotIn("undefined", visible)

    def test_the_visible_coverage_line_counts_no_end_as_none_not_undefined(self) -> None:
        html = self.render([self.row(sid="quiet-1")])
        visible = html.split('<details class="next-attention-coverage-details"')[0]

        self.assertIn("ends observed on 0 sessions", visible)
        self.assertNotIn("undefined", visible)


@unittest.skipUnless(shutil.which("node"), "node not available")
class HealthyBoardBriefTest(NextPageJsHarness):
    """What the brief says when every session is healthy (DRC-4452).

    Not the empty payload, which already stands down: this is the board with
    sessions on it and nothing to report, which is what a machine looks like
    when the product is working.
    """

    BRIEF = re.compile(r'<div class="next-attention-brief">([\s\S]*?)<div class="next-attention-c')

    def brief(self, sessions: str, asks: str = "[]") -> str:
        html = self._run_page_js(
            f"""
__els.app = {{innerHTML: ""}};
nextData = {{generated: 10000, window_hours: 24, ask: true,
  sessions: {sessions}, asks: {asks}}};
nextAttention = nextAttentionModel(nextData);
nextRoute = {{view: "attention", project: null, session: null}};
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)
        match = self.BRIEF.search(html)
        if match is None:  # pragma: no cover — the assertion below reports it
            raise AssertionError(f"no attention brief in {html}")
        return match.group(1)

    ONE_IDLE = """[
  {harness: "claude", sid: "solo", project: "quiet/repo", state: "idle",
   last_activity: 9000}
]"""

    def test_a_healthy_board_names_its_session_count_and_each_empty_queue(self) -> None:
        brief = self.brief(self.ONE_IDLE)
        self.assertIn("0 of 1 session carries a subject", brief)
        self.assertIn("0 waiting on you · 0 at risk · 0 to close the loop", brief)
        self.assertIn("The other 1: 1 quiet", brief)

    def test_the_healthy_line_still_says_the_queues_were_checked(self) -> None:
        # The reachability criterion, and why plain standing-down was rejected:
        # measured, the four category sections return "" on a healthy board, so
        # the only heading left on screen is NO PUBLISHED EXCEPTION and nothing
        # else would tell the reader the queues had been looked at.
        html = self._run_page_js(
            f"""
__els.app = {{innerHTML: ""}};
nextData = {{generated: 10000, window_hours: 24, ask: true,
  sessions: {self.ONE_IDLE}, asks: []}};
nextAttention = nextAttentionModel(nextData);
nextRoute = {{view: "attention", project: null, session: null}};
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)

        self.assertIn("0 waiting on you · 0 at risk · 0 to close the loop", html)
        self.assertIn("The other 1: 1 quiet", html)
        for heading in ("NEEDS YOU NOW", "AT RISK", "CLOSE THE LOOP", "COMING NEXT"):
            self.assertNotIn(f"{heading} (", html)

    def test_the_healthy_line_names_each_state_over_its_own_sessions(self) -> None:
        # Two states, so the tail is a list rather than one phrase, and each
        # entry carries the unit. Zero-count states stay out: a line that opens
        # by saying nothing needs you has no business printing a zero.
        brief = self.brief(
            """[
  {harness: "claude", sid: "a", project: "one/repo", state: "working",
   last_activity: 9900},
  {harness: "claude", sid: "b", project: "two/repo", state: "working",
   last_activity: 9800},
  {harness: "claude", sid: "c", project: "three/repo", state: "idle",
   last_activity: 9000}
]"""
        )

        self.assertIn("The other 3: 2 moving · 1 quiet", brief)
        self.assertNotIn("0 moving", brief)

    def test_a_board_with_one_subject_still_shows_all_four_categories(self) -> None:
        # The half that already held and must be preserved rather than added:
        # a reader looking at a board that DOES have a subject needs the three
        # zeros beside it, because that is how they see the other queues were
        # checked. The standdown is a second condition beside the empty-payload
        # one, not a widening of it.
        brief = self.brief(
            """[
  {harness: "claude", sid: "gate", project: "gate/repo", state: "needs_input",
   last_activity: 9900, blocked_since: 9800}
]"""
        )

        self.assertIn(
            "1 of 1 session carries a subject: 1 waiting on you · 0 at risk · 0 to close the loop",
            brief,
        )

    def test_the_four_the_line_claims_is_the_number_of_categories_rendered(self) -> None:
        # A universal claim over a set, which is the shape that has blocked a
        # merge here before over an unnamed third carve-out. The word is bound
        # to the sections the view actually asks for, not to a count someone
        # wrote down: add a fifth category and this fails.
        out = self._run_page_js(
            """
console.log(JSON.stringify(nextAttentionView.toString()));
"""
        )
        assert isinstance(out, str)
        sections = re.findall(r'nextAttentionSectionHtml\("([a-z]+)"', out)

        self.assertEqual(["needs", "close", "next"], sections)
        self.assertIn('data-next-attention-section="risk"', out)
        self.assertIn("0 at risk", self.brief(self.ONE_IDLE))

    def test_an_empty_payload_still_gets_no_brief_at_all(self) -> None:
        # The neighbouring standdown, kept: with no sessions the notice already
        # says there is nothing, and a line about four empty queues would
        # compete with it.
        html = self._run_page_js(
            """
__els.app = {innerHTML: ""};
nextData = {generated: 10000, window_hours: 6, sessions: [], asks: []};
nextAttention = nextAttentionModel(nextData);
nextRoute = {view: "attention", project: null, session: null};
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        assert isinstance(html, str)

        self.assertIn("No sessions in this 6h payload", html)
        self.assertNotIn("OBSERVED NOW", html)
        self.assertNotIn("queues checked", html)
