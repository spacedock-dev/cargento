"""The drift replay check: its key, its blind order, its ledger, and what it may commit.

The check replays recorded pushback sessions through Cargento's drift detectors against the owner's
marks. These tests build small synthetic sessions; nothing here reads a real session log.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Self
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import drift_replay as dr

START = dt.datetime(2026, 9, 24, 3, 0, tzinfo=dt.UTC)
SID = "11111111-2222-3333-4444-555555555555"


def _stamp(seconds: float) -> str:
    return (START + dt.timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def _at(seconds: float) -> float:
    return (START + dt.timedelta(seconds=seconds)).timestamp()


def _user(seconds: float, text: Any, **extra: Any) -> dict[str, Any]:
    return {
        "type": "user",
        "timestamp": _stamp(seconds),
        "uuid": f"u{seconds}",
        "message": {"content": text},
        **extra,
    }


def _claude(seconds: float, text: str) -> dict[str, Any]:
    return {
        "type": "assistant",
        "timestamp": _stamp(seconds),
        "uuid": f"a{seconds}",
        "message": {"content": [{"type": "text", "text": text}]},
    }


def _stop(seconds: float) -> dict[str, Any]:
    return {
        "type": "system",
        "subtype": "stop_hook_summary",
        "timestamp": _stamp(seconds),
        "isSidechain": False,
    }


# A session: an ask, a reply, a stop; a drifted reply, a stop, a pushback; a fix, a stop; a
# follow-up push with no drift of its own; and two ordinary turns.
RECORDS = [
    _user(0, "/clear"),
    _user(1, "Build the importer and nothing else."),
    _claude(2, "Starting the importer."),
    _stop(3),
    _user(3.5, "continue"),
    _user(4, [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]),
    _user(5, "Another Claude session sent a message: hello"),
    _claude(6, "I also rewrote the exporter while I was there."),
    _stop(7),
    _user(8, "No. I said the importer ONLY."),
    _claude(9, "Reverted the exporter."),
    _stop(10),
    _user(11, "keep it that way"),
    _claude(12, "Will do."),
    _stop(13),
    _user(14, "[Request interrupted by user]"),
    _user(15, "thanks, carry on"),
    _claude(16, "Carrying on."),
    _stop(17),
]

ANNOTATION = """# A title

## Overall goal

Import things.

## 1 · Build the importer

**Goal:** Build the importer only.

**Outcome:** The importer, after a revert.

| Kind | Time (UTC) | What happened | Messages |
|---|---|---|---|
| You asked | 2026-09-24 03:00 | Build the importer. | #1 |
| Claude drifted | 2026-09-24 03:00 | Rewrote the exporter, see PR #317. | #4, #8 |
| You pushed back | 2026-09-24 03:00 | "the importer ONLY" | #5 |
| Claude did | 2026-09-24 03:00 | Reverted. | #6 |
| You pushed back | 2026-09-24 03:00 | "keep it that way" | #7 |
"""


class _Session:
    """A temporary fixture tree, annotation tree and home, wired into the module."""

    def __init__(self) -> None:
        self.root = tempfile.TemporaryDirectory()
        base = Path(self.root.name)
        self.fixtures = base / "raw"
        self.annotations = base / "annotated"
        self.home = base / "home"
        (self.fixtures / SID).mkdir(parents=True)
        (self.annotations / SID).mkdir(parents=True)
        self.log = self.fixtures / SID / f"{SID}.jsonl"
        self.log.write_text("".join(json.dumps(r) + "\n" for r in RECORDS), encoding="utf-8")
        (self.annotations / SID / "annotation.md").write_text(ANNOTATION, encoding="utf-8")
        self.digest = base / "docs" / "marks-digest.json"
        self.results = base / "docs" / "results.json"
        self.patches = [
            mock.patch.object(dr, "FIXTURES", str(self.fixtures)),
            mock.patch.object(dr, "ANNOTATIONS", str(self.annotations)),
            mock.patch.object(dr, "DIGEST_PATH", str(self.digest)),
            mock.patch.object(dr, "RESULTS_PATH", str(self.results)),
        ]

    def __enter__(self) -> Self:
        for patch in self.patches:
            patch.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        for patch in self.patches:
            patch.stop()
        self.root.cleanup()


class TheConversationIsNumberedAsTheAnnotationsNumberIt(unittest.TestCase):
    def test_typed_messages_and_joined_replies_are_numbered_and_nothing_else_is(self) -> None:
        with _Session() as s:
            found = dr.conversation(str(s.log))
        self.assertEqual(
            [(m.role, m.text) for m in found],
            [
                ("you", "/clear"),
                ("you", "Build the importer and nothing else."),
                ("claude", "Starting the importer."),
                ("you", "continue"),
                ("claude", "I also rewrote the exporter while I was there."),
                ("you", "No. I said the importer ONLY."),
                ("claude", "Reverted the exporter."),
                ("you", "keep it that way"),
                ("claude", "Will do."),
                ("you", "thanks, carry on"),
                ("claude", "Carrying on."),
            ],
        )

    def test_a_slash_command_is_its_command_as_typed(self) -> None:
        record = _user(
            0, "<command-name>/compact</command-name><command-args>remember x</command-args>"
        )
        self.assertEqual(dr._typed(record), "/compact remember x")

    def test_only_top_level_stop_records_are_turn_stops(self) -> None:
        with _Session() as s:
            with s.log.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({**_stop(20), "isSidechain": True}) + "\n")
            self.assertEqual(dr.turn_stops(str(s.log)), [_at(3), _at(7), _at(10), _at(13), _at(17)])


class AScreenNeverShowsWhatCameAfterItsCut(unittest.TestCase):
    def test_a_reply_that_runs_past_a_turn_stop_is_cut_at_the_record(self) -> None:
        with _Session() as s:
            rows = [
                _user(0, "Do the thing."),
                _claude(1, "Starting."),
                _stop(2),
                _user(2.5, "<task-notification>done</task-notification>"),
                _claude(3, "POSTCUT text the screen must not show."),
                _stop(4),
            ]
            s.log.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
            screens: list[str] = []
            dr._screen({"sid": SID, "cut": _at(2)}, "fixtures", "1/1", screens.append)
            self.assertEqual(len(dr.conversation(str(s.log))), 2)
        self.assertNotIn("POSTCUT", "\n".join(screens))
        self.assertIn("Starting.", "\n".join(screens))


class TheKeyIsReadFromTheCommittedAnnotation(unittest.TestCase):
    def test_a_pushback_with_no_drift_of_its_own_continues_the_episode(self) -> None:
        found = dr.events(ANNOTATION)
        self.assertEqual(
            [(e.push, e.drift, e.first) for e in found], [(5, [4, 8], True), (7, [], False)]
        )
        self.assertEqual(found[0].episode, found[1].episode)

    def test_a_pr_number_in_the_prose_is_not_a_message(self) -> None:
        self.assertNotIn(317, [n for e in dr.events(ANNOTATION) for n in e.drift])

    def test_a_part_keeps_its_opening_message_and_its_hindsight_goal(self) -> None:
        part = dr.parts(ANNOTATION)[1]
        self.assertEqual((part.opening, part.goal), (1, "Build the importer only."))


class EveryCutHasItsRoles(unittest.TestCase):
    def test_pushback_before_drift_after_fix_and_ordinary_cuts(self) -> None:
        with _Session():
            cases = {c["cut"]: c for c in dr.session_cases(SID, "fixtures", "salt")}
        self.assertEqual(sorted(cases[_at(7)]["roles"]), ["pushback"])
        self.assertIn("before-drift", cases[_at(3)]["roles"])
        self.assertIn("after-fix", cases[_at(10)]["roles"])
        # The follow-up push (#7) is a pushback cut too, but it is not first of its episode.
        self.assertIn("pushback", cases[_at(10)]["roles"])
        self.assertFalse(any(e["first"] for e in cases[_at(10)]["events"]))

    def test_a_case_id_is_salted(self) -> None:
        self.assertNotEqual(dr.case_id("a", SID, 1.0), dr.case_id("b", SID, 1.0))

    def test_the_build_refuses_a_home_inside_the_repository(self) -> None:
        said: list[str] = []
        self.assertEqual(
            dr.build(home=os.path.join(dr._ROOT, "tmp-home"), source="fixtures", say=said.append), 1
        )
        self.assertFalse(os.path.exists(os.path.join(dr._ROOT, "tmp-home")))


class MarkingIsBlindAndComesFirst(unittest.TestCase):
    def _built(self, s: _Session) -> None:
        dr.build(home=str(s.home), source="fixtures", say=lambda _m: None)

    def test_a_screen_shows_nothing_after_the_cut_and_no_role(self) -> None:
        with _Session() as s:
            self._built(s)
            screens: list[str] = []
            replies = iter(["y", "p"] * 50)
            dr.mark(home=str(s.home), ask=lambda _p: next(replies), say=screens.append)
            shown = "\n".join(screens)
        # The push at #5 is the message right after the pushback cut; a screen never shows it ahead.
        for screen in "\n".join(screens).split("=" * 76):
            if "rewrote the exporter" in screen and "Reverted" not in screen:
                self.assertNotIn("importer ONLY", screen)
        for role in dr.ROLES:
            self.assertNotIn(role, shown)

    def test_reconcile_keeps_the_blind_answer_beside_the_final_one(self) -> None:
        with _Session() as s:
            self._built(s)
            dr.mark(home=str(s.home), ask=lambda _p: "n", say=lambda _m: None)
            dr.reconcile(
                home=str(s.home),
                ask=lambda _p: "y" if "drifted" in _p else "s",
                say=lambda _m: None,
            )
            marks = json.loads((s.home / "drift-replay" / "marks.json").read_text())["marks"]
        disagreed = [m for m in marks.values() if (m.get("final") or {}).get("disagreed")]
        self.assertTrue(disagreed)
        self.assertTrue(all(m["blind"]["drift"] == "no-drift" for m in disagreed))

    def test_marking_closes_once_an_output_exists(self) -> None:
        with _Session() as s:
            self._built(s)
            (s.home / "drift-replay" / "live.json").write_text("{}")
            said: list[str] = []
            self.assertEqual(dr.mark(home=str(s.home), ask=lambda _p: "y", say=said.append), 1)
        self.assertIn("closed", said[-1])

    def test_no_run_starts_before_every_cut_has_a_final_mark_and_the_digest_is_committed(
        self,
    ) -> None:
        with _Session() as s:
            self._built(s)
            paths = dr._paths(str(s.home))
            body = json.loads(Path(paths["cases"]).read_text())
            self.assertIn("final mark", dr._run_refusal(paths, body))
            dr.mark(home=str(s.home), ask=lambda _p: "n", say=lambda _m: None)
            dr.reconcile(home=str(s.home), ask=lambda _p: "n", say=lambda _m: None)
            self.assertIn("not committed", dr._run_refusal(paths, body))


class _Recorder:
    """A model that records each prompt it is handed."""

    def __init__(self, sent: list[str], status: str) -> None:
        self.sent = sent
        self.status = status

    def __call__(self, prompt: str, *, output_cap_bytes: int) -> tuple[str, str]:
        del output_cap_bytes
        self.sent.append(prompt)
        return "", self.status


class TheSpendIsBoundedAndADryRunCostsNothing(unittest.TestCase):
    def test_the_ledger_stops_at_its_cap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = dr.Ledger(os.path.join(tmp, "spend.json"), cap=2)
            self.assertEqual(
                [ledger.charge("a"), ledger.charge("b"), ledger.charge("c")], [True, True, False]
            )
            self.assertEqual(len(ledger.calls()), 2)

    def test_a_dry_run_never_charges(self) -> None:
        sent: list[str] = []
        model = dr._Charged(_Recorder(sent, "cancelled"), None, "k")
        model("p", output_cap_bytes=10)
        self.assertEqual((sent, model.charged), (["p"], False))

    def test_a_capped_call_is_flagged_so_it_is_never_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            model = dr._Charged(
                _Recorder([], "ok"), dr.Ledger(os.path.join(tmp, "s.json"), cap=0), "k"
            )
            model("p", output_cap_bytes=10)
        self.assertEqual((model.capped, model.sent, model.charged), (True, False, False))

    def test_a_capped_call_never_reaches_the_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = dr.Ledger(os.path.join(tmp, "spend.json"), cap=0)
            sent: list[str] = []
            model = dr._Charged(_Recorder(sent, "ok"), ledger, "k")
            self.assertEqual(model("p", output_cap_bytes=10), ("", "cancelled"))
        self.assertEqual(sent, [])


class OutcomesKeepRelevanceApart(unittest.TestCase):
    def test_a_live_flag_is_judged_by_when_its_cause_happened(self) -> None:
        stale, fresh = {"level": "high", "cause_at": 10.0}, {"level": "high", "cause_at": 50.0}
        self.assertEqual(dr._live_bin(stale, drifted=True, start=40.0), "irrelevant-flag")
        self.assertEqual(dr._live_bin(fresh, drifted=True, start=40.0), "relevant-flag")
        self.assertEqual(
            dr._live_bin({"level": "high"}, drifted=True, start=40.0), "unattributed-flag"
        )
        self.assertEqual(dr._live_bin(fresh, drifted=True, start=None), "unattributed-flag")
        self.assertEqual(dr._live_bin(fresh, drifted=False, start=40.0), "false-alarm")
        self.assertEqual(dr._live_bin({"level": "not_enough"}, drifted=True, start=1.0), "withheld")
        self.assertEqual(
            dr._live_bin({"level": "none_or_low"}, drifted=True, start=1.0), "reassured"
        )

    def test_the_cause_is_the_named_rise_else_the_latest_failed_check(self) -> None:
        facts = [
            {"fact_id": "c1", "at": 5.0, "subject": "check", "result": "failed"},
            {"fact_id": "c2", "at": 9.0, "subject": "check", "result": "failed"},
            {"fact_id": "w1", "at": 7.0, "subject": "write"},
        ]
        self.assertEqual(dr._cause_at({"rose_at": "w1"}, facts), 7.0)
        self.assertEqual(dr._cause_at({"rose_at": None}, facts), 9.0)
        self.assertIsNone(dr._cause_at({}, facts[2:]))

    def test_an_apparatus_failure_is_refused_not_withheld(self) -> None:
        self.assertEqual(
            dr._read_bin({"withheld": "model-failed"}, drifted=True, start=1.0), "refused"
        )
        self.assertEqual(
            dr._read_bin({"withheld": "window-empty"}, drifted=True, start=1.0), "withheld"
        )

    def test_a_departure_citing_evidence_from_after_the_drift_began_is_relevant(self) -> None:
        entry = {
            "withheld": "",
            "assessment": {"criteria": {"goal": {"result": "departure", "cites": ["f2"]}}},
            "facts": {"f1": 10.0, "f2": 50.0},
        }
        self.assertEqual(dr._read_bin(entry, drifted=True, start=40.0), "relevant-flag")
        self.assertEqual(dr._read_bin(entry, drifted=True, start=60.0), "irrelevant-flag")
        self.assertEqual(
            dr._read_bin({"withheld": "idle-unknown"}, drifted=True, start=1.0), "withheld"
        )
        consistent = {
            "withheld": "",
            "assessment": {"criteria": {"goal": {"result": "consistent with the evidence read"}}},
        }
        self.assertEqual(dr._read_bin(consistent, drifted=True, start=1.0), "reassured")


if __name__ == "__main__":
    unittest.main()
