"""A reader's expected outcome, written as a checklist and read one line at a time (DRC-4685).

[DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy)
item 3 turns the single expected output into up to six lines, each at most 240 characters on one
line, each recording its source, each read as its own constraint. Every test here is a sentence
about the person who typed those lines: what they get back, what they are refused and why, and
what never reaches a model they did not ask to run.
"""

from __future__ import annotations

import contextlib
import dataclasses
import http.client
import json
import os
import pathlib
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast
from unittest import mock

from cargento_runtime import annotations as annotation_store
from cargento_runtime import cli, history, observer, reading, unasked
from cargento_runtime import sessions as runtime_sessions
from cargento_runtime.config import RuntimeConfig, build_runtime_config
from cargento_runtime.state import build_runtime_state

from .support import make_config, make_runtime, make_server, serve_until_closed
from .support import os_name as support_os_name

NOW = 1_800_000_000.0
REPO = pathlib.Path(__file__).resolve().parents[4]
SIX = [
    "Failed events retry with backoff",
    "Events that still fail go to a dead-letter table",
    "Tests cover the retry path",
    "Tests cover the failure path",
    "The public API does not change",
    "The logging migration stays out of this branch",
]


def _config(root: Path, **changes: Any) -> RuntimeConfig:
    config = build_runtime_config(
        environ={"HOME": str(root), "CARGENTO_HOME": str(root / "state")},
        platform_name="linux",
        os_name="posix",
        launcher_path=root / "server.py",
    )
    return dataclasses.replace(config, **changes) if changes else config


class _StoreCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = _config(self.root)
        self.state = build_runtime_state(self.config, started=NOW)

    def entry(self, sid: str = "s-1") -> annotation_store.Annotation:
        found = annotation_store.find(annotation_store.load(self.config), "claude", sid)
        assert found is not None
        return found

    def write_raw(self, payload: Any) -> None:
        path = annotation_store.store_path(self.config)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)


class SixLinesAreKeptAndShownOneByOneTest(_StoreCase):
    def test_a_reader_who_types_six_lines_gets_six_lines_back_each_marked_typed(self) -> None:
        outcome = annotation_store.annotate(
            self.config, self.state, "claude", "s-1", goal="Harden the ingest", lines=SIX, now=NOW
        )

        self.assertEqual(annotation_store.OUTCOME_STORED, outcome)
        lines = self.entry()["revisions"][-1]["lines"]
        self.assertEqual(SIX, [line["text"] for line in lines])
        self.assertEqual(["typed"] * 6, [line["source"] for line in lines])
        published = annotation_store.published(self.entry())
        self.assertEqual(SIX, [published[f"line_{k}"] for k in range(1, 7)])
        self.assertEqual(["typed"] * 6, [published[f"line_{k}_source"] for k in range(1, 7)])
        self.assertEqual("", published["lines_why"])

    def test_a_240_character_line_is_kept_whole(self) -> None:
        line = "x" * 240

        annotation_store.annotate(self.config, self.state, "claude", "s-1", lines=[line], now=NOW)

        self.assertEqual(line, self.entry()["revisions"][-1]["lines"][0]["text"])

    def test_a_session_with_no_lines_says_why_rather_than_rendering_blanks(self) -> None:
        annotation_store.annotate(self.config, self.state, "claude", "s-1", goal="G", now=NOW)

        published = annotation_store.published(self.entry())
        self.assertEqual(annotation_store.NO_LINES_TYPED, published["lines_why"])
        self.assertEqual("", published["line_1"])
        self.assertIsNone(published["line_1_source"])
        self.assertEqual(
            annotation_store.NO_LINES_TYPED, annotation_store.published(None)["lines_why"]
        )

    def test_a_seventh_line_is_refused_and_nothing_is_minted(self) -> None:
        annotation_store.annotate(self.config, self.state, "claude", "s-1", lines=SIX, now=NOW)
        with open(annotation_store.store_path(self.config), "rb") as handle:
            before = handle.read()

        outcome = annotation_store.annotate(
            self.config, self.state, "claude", "s-1", lines=[*SIX, "a seventh"], now=NOW + 1
        )

        self.assertEqual(annotation_store.OUTCOME_REFUSED, outcome)
        with open(annotation_store.store_path(self.config), "rb") as handle:
            self.assertEqual(before, handle.read())
        self.assertEqual(1, self.entry()["revisions"][-1]["n"])

    def test_a_line_over_240_characters_is_refused_rather_than_saved_clipped(self) -> None:
        outcome = annotation_store.annotate(
            self.config, self.state, "claude", "s-1", lines=["y" * 241], now=NOW
        )

        self.assertEqual(annotation_store.OUTCOME_REFUSED, outcome)
        self.assertEqual((), annotation_store.load(self.config))

    def test_a_pasted_line_break_collapses_so_each_line_stays_one_line(self) -> None:
        annotation_store.annotate(
            self.config,
            self.state,
            "claude",
            "s-1",
            lines=["retry with\nbackoff", "no \u202ereordering"],
            now=NOW,
        )

        texts = [line["text"] for line in self.entry()["revisions"][-1]["lines"]]
        self.assertEqual(["retry with backoff", "no  reordering"], texts)

    def test_an_empty_line_is_dropped_rather_than_stored(self) -> None:
        annotation_store.annotate(
            self.config, self.state, "claude", "s-1", lines=["one", "  ", "", "two"], now=NOW
        )

        texts = [line["text"] for line in self.entry()["revisions"][-1]["lines"]]
        self.assertEqual(["one", "two"], texts)

    def test_saving_the_same_list_again_mints_no_revision(self) -> None:
        annotation_store.annotate(self.config, self.state, "claude", "s-1", lines=SIX, now=NOW)

        again = annotation_store.annotate(
            self.config, self.state, "claude", "s-1", lines=list(SIX), now=NOW + 5
        )

        self.assertEqual(annotation_store.OUTCOME_UNCHANGED, again)
        self.assertEqual(1, self.entry()["revisions"][-1]["n"])

    def test_saving_only_the_goal_leaves_the_lines_alone(self) -> None:
        annotation_store.annotate(self.config, self.state, "claude", "s-1", lines=SIX, now=NOW)

        annotation_store.annotate(
            self.config, self.state, "claude", "s-1", goal="new goal", now=NOW + 1
        )

        latest = self.entry()["revisions"][-1]
        self.assertEqual(SIX, [line["text"] for line in latest["lines"]])
        self.assertEqual("new goal", latest["goal"])

    def test_an_empty_list_clears_every_line(self) -> None:
        annotation_store.annotate(self.config, self.state, "claude", "s-1", lines=SIX, now=NOW)

        annotation_store.annotate(self.config, self.state, "claude", "s-1", lines=[], now=NOW + 1)

        self.assertEqual((), self.entry()["revisions"][-1]["lines"])

    def test_a_stale_list_from_a_second_tab_is_refused(self) -> None:
        annotation_store.annotate(self.config, self.state, "claude", "s-1", lines=["a"], now=NOW)
        annotation_store.annotate(
            self.config, self.state, "claude", "s-1", lines=["b"], now=NOW + 1
        )

        stale = annotation_store.annotate(
            self.config,
            self.state,
            "claude",
            "s-1",
            lines=["a", "c"],
            expected_revision=1,
            now=NOW + 2,
        )

        self.assertEqual(annotation_store.OUTCOME_REFUSED, stale)
        self.assertEqual(["b"], [line["text"] for line in self.entry()["revisions"][-1]["lines"]])

    def test_a_list_naming_the_current_revision_is_saved(self) -> None:
        annotation_store.annotate(self.config, self.state, "claude", "s-1", lines=["a"], now=NOW)

        outcome = annotation_store.annotate(
            self.config,
            self.state,
            "claude",
            "s-1",
            lines=["a", "c"],
            expected_revision=1,
            now=NOW + 2,
        )

        self.assertEqual(annotation_store.OUTCOME_STORED, outcome)


class ALineKeepsItsSourceTest(_StoreCase):
    """Only the server may say a line came from an entry, and an edit makes it typed."""

    def seed_entry_line(self) -> None:
        self.write_raw(
            {
                "v": 2,
                "entries": [
                    {
                        "harness": "claude",
                        "sid": "s-1",
                        "revisions": [
                            {
                                "n": 1,
                                "at": NOW,
                                "goal": "G",
                                "lines": [
                                    {
                                        "text": "from the record",
                                        "source": "entry",
                                        "source_id": "f-9",
                                    },
                                    {"text": "typed one", "source": "typed"},
                                ],
                            }
                        ],
                    }
                ],
            }
        )

    def test_a_line_added_from_an_entry_reads_back_with_its_entry(self) -> None:
        self.seed_entry_line()

        published = annotation_store.published(self.entry())

        self.assertEqual("entry", published["line_1_source"])
        self.assertEqual("f-9", published["line_1_source_id"])
        self.assertEqual("typed", published["line_2_source"])
        self.assertEqual("", published["line_2_source_id"])

    def test_resaving_an_unchanged_entry_line_keeps_its_source(self) -> None:
        self.seed_entry_line()

        annotation_store.annotate(
            self.config,
            self.state,
            "claude",
            "s-1",
            lines=["from the record", "typed one", "a third"],
            now=NOW + 1,
        )

        lines = self.entry()["revisions"][-1]["lines"]
        self.assertEqual(
            {"text": "from the record", "source": "entry", "source_id": "f-9"}, lines[0]
        )

    def test_editing_an_entry_line_saves_it_as_typed(self) -> None:
        self.seed_entry_line()

        annotation_store.annotate(
            self.config,
            self.state,
            "claude",
            "s-1",
            lines=["from the record, edited", "typed one"],
            now=NOW + 1,
        )

        self.assertEqual(
            {"text": "from the record, edited", "source": "typed"},
            self.entry()["revisions"][-1]["lines"][0],
        )

    def test_a_client_cannot_claim_a_line_came_from_an_entry(self) -> None:
        outcome = annotation_store.annotate(
            self.config,
            self.state,
            "claude",
            "s-1",
            lines=cast("Any", [{"text": "forged", "source": "entry", "source_id": "f-1"}]),
            now=NOW,
        )

        self.assertEqual(annotation_store.OUTCOME_REFUSED, outcome)
        self.assertEqual((), annotation_store.load(self.config))

    def test_an_unknown_line_source_on_disk_refuses_the_whole_entry(self) -> None:
        self.write_raw(
            {
                "v": 2,
                "entries": [
                    {
                        "harness": "claude",
                        "sid": "s-1",
                        "revisions": [
                            {"n": 1, "at": NOW, "goal": "old", "lines": []},
                            {
                                "n": 2,
                                "at": NOW,
                                "goal": "G",
                                "lines": [{"text": "x", "source": "model"}],
                            },
                        ],
                    }
                ],
            }
        )

        # Dropping only the bad revision would bring back older words the reader replaced.
        self.assertEqual((), annotation_store.load(self.config))

    def test_seven_lines_on_disk_refuse_the_whole_entry(self) -> None:
        self.write_raw(
            {
                "v": 2,
                "entries": [
                    {
                        "harness": "claude",
                        "sid": "s-1",
                        "revisions": [
                            {
                                "n": 1,
                                "at": NOW,
                                "goal": "G",
                                "lines": [{"text": f"l{k}", "source": "typed"} for k in range(7)],
                            }
                        ],
                    }
                ],
            }
        )

        self.assertEqual((), annotation_store.load(self.config))


class AnOlderStoreStillReadsTest(_StoreCase):
    def test_an_old_single_expected_output_reads_as_one_typed_line(self) -> None:
        self.write_raw(
            {
                "v": 1,
                "entries": [
                    {
                        "harness": "claude",
                        "sid": "s-1",
                        "revisions": [{"n": 3, "at": NOW, "goal": "G", "output": "a CSV export"}],
                    }
                ],
            }
        )

        latest = self.entry()["revisions"][-1]

        self.assertEqual(({"text": "a CSV export", "source": "typed"},), latest["lines"])
        self.assertEqual("a CSV export", annotation_store.published(self.entry())["line_1"])

    def test_an_old_empty_expected_output_reads_as_no_lines(self) -> None:
        self.write_raw(
            {
                "v": 1,
                "entries": [
                    {
                        "harness": "claude",
                        "sid": "s-1",
                        "revisions": [{"n": 3, "at": NOW, "goal": "G", "output": ""}],
                    }
                ],
            }
        )

        self.assertEqual((), self.entry()["revisions"][-1]["lines"])

    def test_the_next_save_writes_lines_and_no_output_key(self) -> None:
        self.write_raw(
            {
                "v": 1,
                "entries": [
                    {
                        "harness": "claude",
                        "sid": "s-1",
                        "revisions": [{"n": 3, "at": NOW, "goal": "G", "output": "a CSV export"}],
                    }
                ],
            }
        )

        annotation_store.annotate(self.config, self.state, "claude", "s-1", goal="G2", now=NOW + 1)

        with open(annotation_store.store_path(self.config), encoding="utf-8") as handle:
            written = json.load(handle)
        self.assertEqual(annotation_store.SCHEMA_VERSION, written["v"])
        for revision in written["entries"][0]["revisions"]:
            self.assertNotIn("output", revision)
            self.assertIn("lines", revision)
        self.assertEqual(
            [{"text": "a CSV export", "source": "typed"}],
            written["entries"][0]["revisions"][-1]["lines"],
        )

    def legacy_reading(self, output: dict[str, Any]) -> dict[str, Any]:
        return {
            "revision_read": 3,
            "revision_read_at": NOW,
            "read_at": NOW + 10,
            "stamp": "read at 10:00",
            "cutoff": "Read 1 of 1 entries.",
            "scope": "mid-flight",
            "scope_text": reading.SCOPE_TEXT["mid-flight"],
            "ended_at_read": None,
            "criteria": {
                "goal": {
                    "result": reading.RESULT_UNVERIFIABLE,
                    "cites": [],
                    "detail": "",
                    "clause": "G",
                    "why": "",
                },
                "output": output,
            },
        }

    def seed_reading(self, output: dict[str, Any]) -> None:
        self.write_raw(
            {
                "v": 1,
                "entries": [
                    {
                        "harness": "claude",
                        "sid": "s-1",
                        "revisions": [{"n": 3, "at": NOW, "goal": "G", "output": "a CSV export"}],
                        "readings": 1,
                        "assessment": self.legacy_reading(output),
                    }
                ],
            }
        )

    def test_a_reading_stored_before_this_change_still_loads_with_its_outcome_as_line_one(
        self,
    ) -> None:
        self.seed_reading(
            {
                "result": reading.RESULT_DEPARTURE,
                "cites": ["f1"],
                "detail": "no CSV was written",
                "clause": "a CSV export",
                "why": "",
            }
        )

        entry = self.entry()

        self.assertNotIn("refused", entry)
        assessment = entry["assessment"]
        self.assertEqual({"goal", "line_1"}, set(assessment["criteria"]))
        self.assertEqual("a CSV export", assessment["criteria"]["line_1"]["clause"])
        self.assertIsNone(assessment["evidence_through"])

    def test_a_legacy_output_nobody_typed_is_dropped_rather_than_shown_as_a_line(self) -> None:
        # Stored with its reason, and stored before `why` existed, which is the same field with
        # the reason missing.
        for reason in ({"why": reading.WHY_NOT_ASKED}, {}):
            with self.subTest(reason=reason):
                self.seed_reading(
                    {
                        "result": reading.RESULT_UNVERIFIABLE,
                        "cites": [],
                        "detail": "",
                        "clause": "",
                        **reason,
                    }
                )

                self.assertEqual({"goal"}, set(self.entry()["assessment"]["criteria"]))

    def test_a_reading_with_a_gap_in_its_lines_is_refused_whole(self) -> None:
        criterion = {
            "result": reading.RESULT_UNVERIFIABLE,
            "cites": [],
            "detail": "",
            "clause": "x",
            "why": "",
        }
        reading_value = self.legacy_reading(criterion)
        reading_value["criteria"] = {"goal": criterion, "line_1": criterion, "line_3": criterion}
        self.write_raw(
            {
                "v": 2,
                "entries": [
                    {
                        "harness": "claude",
                        "sid": "s-1",
                        "revisions": [{"n": 3, "at": NOW, "goal": "G", "lines": []}],
                        "assessment": reading_value,
                    }
                ],
            }
        )

        entry = self.entry()
        self.assertTrue(entry.get("refused"))
        self.assertNotIn("assessment", entry)

    def test_a_reading_keeps_the_time_its_evidence_ran_through(self) -> None:
        criterion = {
            "result": reading.RESULT_UNVERIFIABLE,
            "cites": [],
            "detail": "",
            "clause": "x",
            "why": "",
        }
        reading_value = self.legacy_reading(criterion)
        reading_value["criteria"] = {"goal": criterion, "line_1": criterion}
        reading_value["evidence_through"] = NOW - 60
        self.write_raw(
            {
                "v": 2,
                "entries": [
                    {
                        "harness": "claude",
                        "sid": "s-1",
                        "revisions": [{"n": 3, "at": NOW, "goal": "G", "lines": []}],
                        "assessment": reading_value,
                    }
                ],
            }
        )

        self.assertEqual(NOW - 60, self.entry()["assessment"]["evidence_through"])


class TheStoreNeverOutgrowsItsReadLimitTest(_StoreCase):
    """Owner ruling, 2026-09-24: a store over the read limit was ignored and then overwritten.

    The read limit is 16 MiB, and a write trims oldest-first until the file fits under it, so
    the next read always reads what the last write kept.
    """

    def full_entry(self, index: int, char: str) -> annotation_store.Annotation:
        text = char * 240
        criterion = {
            "result": reading.RESULT_DEPARTURE,
            "cites": tuple(
                f"{index:04d}".ljust(annotation_store.KEY_CAP_CHARS, "k") for _ in range(12)
            ),
            "detail": text,
            "clause": text,
            "why": "",
        }
        return cast(
            "annotation_store.Annotation",
            {
                "harness": "claude",
                "sid": f"s-{index:04d}",
                "revisions": tuple(
                    {
                        "n": n,
                        "at": NOW + index + n / 100,
                        "goal": text,
                        "lines": tuple({"text": text, "source": "typed"} for _ in range(6)),
                    }
                    for n in range(1, 17)
                ),
                "readings": 1,
                "assessment": {
                    "revision_read": 16,
                    "revision_read_at": NOW,
                    "read_at": NOW,
                    "stamp": "s",
                    "cutoff": "c",
                    "scope": "mid-flight",
                    "scope_text": reading.SCOPE_TEXT["mid-flight"],
                    "ended_at_read": None,
                    "evidence_through": NOW,
                    "criteria": {
                        name: dict(criterion)
                        for name in ("goal", *(f"line_{k}" for k in range(1, 7)))
                    },
                },
            },
        )

    def test_the_read_limit_is_sixteen_mib(self) -> None:
        self.assertEqual(16 * 1024 * 1024, self.config.annotation_read_cap_bytes)

    def test_every_count_bound_full_still_writes_and_reads_back_whole(self) -> None:
        entries = [self.full_entry(i, "a") for i in range(self.config.annotation_max_sessions)]

        self.assertTrue(annotation_store.save(self.config, entries))

        size = os.path.getsize(annotation_store.store_path(self.config))
        self.assertLessEqual(size, self.config.annotation_read_cap_bytes)
        loaded = annotation_store.load(self.config)
        self.assertEqual(self.config.annotation_max_sessions, len(loaded))
        self.assertEqual(16, len(loaded[-1]["revisions"]))
        self.assertEqual(6, len(loaded[-1]["revisions"][-1]["lines"]))

    def test_a_store_that_would_pass_the_limit_is_trimmed_oldest_first_rather_than_lost(
        self,
    ) -> None:
        # Astral characters serialise as twelve bytes each under `ensure_ascii`, so the count
        # bounds alone permit a store several times the read limit.
        entries = [
            self.full_entry(i, "\U0001f600") for i in range(self.config.annotation_max_sessions)
        ]

        self.assertTrue(annotation_store.save(self.config, entries))

        size = os.path.getsize(annotation_store.store_path(self.config))
        self.assertLessEqual(size, self.config.annotation_read_cap_bytes)
        loaded = annotation_store.load(self.config)
        self.assertGreater(len(loaded), 0, "the store was discarded on read")
        self.assertLess(len(loaded), len(entries))
        newest = f"s-{self.config.annotation_max_sessions - 1:04d}"
        self.assertIn(newest, {entry["sid"] for entry in loaded})
        self.assertNotIn("s-0000", {entry["sid"] for entry in loaded})

    def test_a_store_exactly_at_the_limit_is_kept_and_one_byte_less_drops_the_oldest(self) -> None:
        entries = [self.full_entry(i, "b") for i in range(3)]
        annotation_store.save(self.config, entries)
        exact = os.path.getsize(annotation_store.store_path(self.config))

        at_limit = dataclasses.replace(self.config, annotation_read_cap_bytes=exact)
        annotation_store.save(at_limit, entries)
        self.assertEqual(3, len(annotation_store.load(at_limit)))

        under = dataclasses.replace(self.config, annotation_read_cap_bytes=exact - 1)
        annotation_store.save(under, entries)
        kept = annotation_store.load(under)
        self.assertEqual(["s-0001", "s-0002"], [entry["sid"] for entry in kept])


# --------------------------------------------------------------------------------- producer


class _Config:
    reading_settle_sec = 8.0
    annotation_text_cap_chars = 240


def _pi_fact(fact_id: str, at: float, summary: str = "wrote the retry loop") -> dict[str, Any]:
    return {
        "fact_id": fact_id,
        "type": "work_result",
        "by": "agent",
        "summary": summary,
        "at": at,
        "evidence": {"source": "transcript", "confidence": "high"},
        "source_session": {"harness": "pi", "sid": "p1"},
    }


def _reply(names: list[str], **over: dict[str, Any]) -> str:
    body = {name: {"result": "consistent", "cites": [1], "detail": ""} for name in names}
    body.update(over)
    return json.dumps(body)


class _ProducerCase(unittest.TestCase):
    ROW: dict[str, Any] = {"harness": "pi", "sid": "p1", "state": "working", "ended_at": None}  # noqa: RUF012

    def setUp(self) -> None:
        self.prompts: list[str] = []
        self.caps: list[int] = []

    def model(self, raw: str) -> Any:
        def run(prompt: str, *, output_cap_bytes: int) -> tuple[str, str]:
            self.prompts.append(prompt)
            self.caps.append(output_cap_bytes)
            return raw.encode("utf-8")[:output_cap_bytes].decode("utf-8", "ignore"), "ok"

        return run

    def produce(
        self,
        raw: str,
        *,
        lines: list[str] | None = None,
        facts: list[dict[str, Any]] | None = None,
        read_lines: bool = True,
    ) -> Any:
        revision = {
            "n": 2,
            "at": 10.0,
            "goal": "Harden the ingest",
            "lines": [
                {"text": text, "source": "typed"} for text in (SIX if lines is None else lines)
            ],
        }
        return reading.produce(
            cast("Any", _Config()),
            self.ROW,
            [revision],
            facts if facts is not None else [_pi_fact("f1", 100.0)],
            now=500.0,
            stamp_text="read",
            model=self.model(raw),
            read_lines=read_lines,
        )


class EachLineIsAskedOnItsOwnTest(_ProducerCase):
    def test_each_line_is_posed_in_its_own_tag_and_named_in_the_answer_shape(self) -> None:
        self.produce(_reply(["goal", *(f"line_{k}" for k in range(1, 7))]))

        prompt = self.prompts[0]
        for k, text in enumerate(SIX, start=1):
            with self.subTest(line=k):
                self.assertIn(f'<outcome_line n="{k}">\n{text}\n</outcome_line>', prompt)
                self.assertIn(f'"line_{k}": {{', prompt)
        self.assertIn("Answer each line on its own", prompt)
        self.assertNotIn("<expected_output>", prompt)

    def test_six_lines_come_back_as_six_criteria_beside_the_goal(self) -> None:
        assessment, why, spent = self.produce(_reply(["goal", *(f"line_{k}" for k in range(1, 7))]))

        self.assertEqual(("", True), (why, spent))
        assert assessment is not None
        self.assertEqual(
            ["goal", "line_1", "line_2", "line_3", "line_4", "line_5", "line_6"],
            list(assessment["criteria"]),
        )
        self.assertEqual(SIX[3], assessment["criteria"]["line_4"]["clause"])
        self.assertEqual(reading.RESULT_CONSISTENT, assessment["criteria"]["line_4"]["result"])

    def test_an_old_single_expected_output_is_read_as_line_one(self) -> None:
        assessment, _why, _spent = reading.produce(
            cast("Any", _Config()),
            self.ROW,
            [{"n": 1, "at": 10.0, "goal": "G", "output": "a CSV export"}],
            [_pi_fact("f1", 100.0)],
            now=500.0,
            stamp_text="read",
            model=self.model(_reply(["goal", "line_1"])),
            read_lines=True,
        )

        assert assessment is not None
        self.assertEqual({"goal", "line_1"}, set(assessment["criteria"]))
        self.assertEqual("a CSV export", assessment["criteria"]["line_1"]["clause"])

    def test_a_line_resting_only_on_the_agents_narration_is_not_verifiable_while_another_stands(
        self,
    ) -> None:
        narration = {**_pi_fact("n1", 90.0, "said it was finished"), "type": "tool_use"}
        facts = [narration, _pi_fact("f1", 100.0)]
        raw = _reply(
            ["goal", "line_1", "line_2"],
            line_1={"result": "consistent", "cites": [1], "detail": ""},
            line_2={"result": "consistent", "cites": [2], "detail": ""},
        )

        assessment, _why, _spent = self.produce(raw, lines=SIX[:2], facts=facts)

        assert assessment is not None
        self.assertEqual(reading.WHY_NO_WORK_SHOWN, assessment["criteria"]["line_1"]["why"])
        self.assertEqual(reading.RESULT_UNVERIFIABLE, assessment["criteria"]["line_1"]["result"])
        self.assertEqual(reading.RESULT_CONSISTENT, assessment["criteria"]["line_2"]["result"])

    def test_a_check_that_does_not_show_a_lines_verdict_withdraws_only_that_line(self) -> None:
        passed = {
            "type": reading.TOOL_REPORT_TYPE,
            "subject": reading.CHECK_SUBJECT,
            "result": "passed",
        }
        ledger = (
            {**_ledger_entry("c1", 100.0), **passed},
            {**_ledger_entry("c2", 110.0), **passed},
        )
        selection = reading.Selection(cast("Any", ledger))
        parsed: dict[str, dict[str, Any]] = {
            "goal": {"token": "", "cites": (), "detail": ""},
            "line_1": {"token": "departure", "cites": (1,), "detail": "the retry loop is missing"},
            "line_2": {"token": "consistent", "cites": (2,), "detail": ""},
        }

        criteria = reading.resolve(
            parsed, selection, goal="", lines=SIX[:2], detail_cap_chars=240, window_start=50.0
        )

        self.assertEqual(reading.WHY_CHECK_DOES_NOT_SHOW_IT, criteria["line_1"]["why"])
        self.assertEqual(reading.RESULT_CONSISTENT, criteria["line_2"]["result"])

    def test_with_no_work_in_the_record_no_line_is_asked_and_the_goal_still_is(self) -> None:
        person = {
            **_pi_fact("m1", 100.0, "please harden the ingest"),
            "type": "user_message",
            "by": "person:jared",
        }

        assessment, _why, _spent = self.produce(_reply(["goal", "line_1"]), facts=[person])

        assert assessment is not None
        self.assertNotIn("<outcome_line", self.prompts[0])
        self.assertIn("<goal>", self.prompts[0])
        for k in range(1, 7):
            with self.subTest(line=k):
                self.assertEqual(reading.WHY_NOT_ASKED, assessment["criteria"][f"line_{k}"]["why"])
        self.assertNotEqual(reading.WHY_NOT_ASKED, assessment["criteria"]["goal"]["why"])


def _ledger_entry(fact_id: str, at: float) -> dict[str, Any]:
    return {
        "id": fact_id,
        "type": "work_result",
        "by": "agent",
        "summary": "wrote it",
        "at": at,
        "author": reading.AUTHOR_AGENT,
        "source": "transcript \u00b7 high",
        "work": True,
    }


class TheReplyAndThePromptHaveRoomForSevenTest(_ProducerCase):
    def worst_reply(self) -> str:
        detail = "\u00e9" * 240
        body = {
            name: {"result": "departure", "cites": list(range(1000, 1012)), "detail": detail}
            for name in ("goal", *(f"line_{k}" for k in range(1, 7)))
        }
        return json.dumps(body, indent=2, ensure_ascii=False)

    def test_the_reply_cap_is_8192_bytes(self) -> None:
        self.produce(_reply(["goal", "line_1"]))

        self.assertEqual([reading.REPLY_CAP_BYTES], self.caps)
        self.assertEqual(8_192, reading.REPLY_CAP_BYTES)

    def test_a_reply_exactly_at_the_cap_keeps_all_seven_answers(self) -> None:
        raw = self.worst_reply()
        size = len(raw.encode("utf-8"))
        self.assertLess(size, reading.REPLY_CAP_BYTES)
        raw = raw[:-1] + " " * (reading.REPLY_CAP_BYTES - size) + "}"
        self.assertEqual(reading.REPLY_CAP_BYTES, len(raw.encode("utf-8")))
        names = ["goal", *(f"line_{k}" for k in range(1, 7))]

        parsed = reading.parse_reply(raw, names)

        self.assertEqual(["departure"] * 7, [parsed[name]["token"] for name in names])

    def test_a_reply_cut_in_the_middle_of_a_line_keeps_every_answer_before_the_cut(self) -> None:
        raw = self.worst_reply()
        cut = raw[: raw.index('"line_5"') + 40]
        names = ["goal", *(f"line_{k}" for k in range(1, 7))]

        parsed = reading.parse_reply(cut, names)

        self.assertEqual(["departure"] * 5 + ["", ""], [parsed[name]["token"] for name in names])

    def test_a_cut_reply_never_turns_every_line_into_cant_tell(self) -> None:
        # The produce-level half: the model's reply is cut at the cap by the exec layer.
        raw = _reply(
            ["goal", *(f"line_{k}" for k in range(1, 7))],
            line_6={"result": "consistent", "cites": [1], "detail": "x" * 20_000},
        )

        assessment, _why, _spent = self.produce(raw)

        assert assessment is not None
        self.assertEqual(reading.RESULT_CONSISTENT, assessment["criteria"]["line_1"]["result"])
        self.assertNotIn("result", assessment["criteria"]["line_6"])
        self.assertEqual(reading.WHY_UNREADABLE, assessment["criteria"]["line_6"]["why"])

    def test_the_worst_intent_fits_its_share_and_leaves_room_for_the_record(self) -> None:
        astral = "\U0001f600" * 240
        header = reading._header(astral, (astral,) * 6, tool_note=True)

        size = len(header.encode("utf-8"))
        self.assertLessEqual(size, reading.INTENT_SHARE_BYTES)
        self.assertEqual(9_216, reading.INTENT_SHARE_BYTES)
        self.assertGreaterEqual(observer.OBSERVER_MODEL_MAX_PROMPT_BYTES - size, 7_168)

    def test_an_intent_over_its_share_drops_every_line_together(self) -> None:
        huge = "\U0001f600" * 2_000
        ledger = reading.build_ledger([_pi_fact("f1", 100.0)], "pi", "p1")

        prompt, selection = reading.build_prompt(
            ledger, goal="G", lines=(huge,) * 6, max_bytes=observer.OBSERVER_MODEL_MAX_PROMPT_BYTES
        )

        self.assertNotIn("<outcome_line", prompt)
        self.assertIs(False, selection.asked_output)


class AReadingSaysHowFarItsEvidenceRanTest(_ProducerCase):
    def test_evidence_through_is_the_newest_entry_even_one_the_prompt_had_no_room_for(self) -> None:
        # Person-authored entries are reserved first, so a newer agent entry is the one left out.
        people = [
            {
                **_pi_fact(f"m{i}", 100.0 + i, "please " + "harden the ingest " * 9),
                "type": "user_message",
                "by": "person:jared",
            }
            for i in range(120)
        ]
        newest = _pi_fact("late", 900.0)

        assessment, _why, _spent = self.produce(_reply(["goal"]), facts=[*people, newest])

        assert assessment is not None
        self.assertNotIn("wrote the retry loop", self.prompts[0])
        self.assertEqual(900.0, assessment["evidence_through"])

    def test_a_record_with_no_usable_time_says_so_with_none(self) -> None:
        assessment, _why, _spent = self.produce(_reply(["goal"]), facts=[_pi_fact("f1", 0.0)])

        assert assessment is not None
        self.assertIsNone(assessment["evidence_through"])


# ------------------------------------------------------------------------------ unasked lane


class TheUnaskedLaneSeesNoLinesTest(unittest.TestCase):
    """DEC-24 item 12: the unasked lane receives no outcome lines."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = _config(Path(self.temp.name), unasked_enabled=True)
        self.state = build_runtime_state(self.config, started=1_000.0)
        self.prompts: list[str] = []
        self.results: list[Any] = []

    def lane(self) -> unasked.Lane:
        prompts = self.prompts
        results = self.results

        class Model:
            def __init__(self, _config: Any) -> None:
                pass

            def __call__(self, prompt: str, *, output_cap_bytes: int) -> tuple[str, str]:
                del output_cap_bytes
                prompts.append(prompt)
                # A model volunteering answers about lines it was never shown.
                return _reply(["goal", "line_1", "line_2"]), "ok"

        def produce(*args: Any, **kwargs: Any) -> Any:
            result = reading.produce(*args, **kwargs)
            results.append(result)
            return result

        self.enterContext(mock.patch.object(reading, "CodexReadingModel", Model))
        return unasked.Lane(
            self.config,
            popup_notifier=lambda _title, _message: "handed-over",
            diagnostic_sink=lambda _line: None,
            clock=lambda: 5_000.0,
            produce=produce,
            facts_for=lambda _state, _row, _now: [
                {**_pi_fact("f1", 100.0), "source_session": {"harness": "claude", "sid": "s-1"}}
            ],
            spawn=lambda work: work(),
        )

    def consider(self, entry: annotation_store.Annotation) -> None:
        lane = self.lane()
        for state in ("idle", "working"):
            lane.consider(
                self.state,
                [{"harness": "claude", "sid": "s-1", "state": state, "project": "p"}],
                [entry],
                now=5_000.0,
            )

    def test_the_lane_prompt_holds_no_line_and_no_answer_is_kept_for_one(self) -> None:
        entry = cast(
            "annotation_store.Annotation",
            {
                "harness": "claude",
                "sid": "s-1",
                "revisions": (
                    {
                        "n": 1,
                        "at": 10.0,
                        "goal": "Harden the ingest",
                        "lines": tuple({"text": text, "source": "typed"} for text in SIX),
                    },
                ),
            },
        )

        self.consider(entry)

        self.assertEqual(1, len(self.prompts), "the lane never read the goal")
        for text in SIX:
            with self.subTest(line=text):
                self.assertNotIn(text, self.prompts[0])
        self.assertNotIn("outcome_line", self.prompts[0])
        assessment = self.results[0][0]
        assert assessment is not None
        self.assertEqual(["goal"], list(assessment["criteria"]))

    def test_a_session_with_lines_and_no_goal_is_not_read_by_the_lane(self) -> None:
        entry = cast(
            "annotation_store.Annotation",
            {
                "harness": "claude",
                "sid": "s-1",
                "revisions": (
                    {
                        "n": 1,
                        "at": 10.0,
                        "goal": "",
                        "lines": ({"text": "a line", "source": "typed"},),
                    },
                ),
            },
        )

        self.consider(entry)

        self.assertEqual([], self.prompts)
        self.assertEqual([], self.results)


# ----------------------------------------------------------------------------------- history


class HistoryKeepsEachLineOnItsOwnTest(unittest.TestCase):
    def setUp(self) -> None:
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        self.config = make_config(
            state_home=self.home.name, state_dir=Path(self.home.name), os_name=support_os_name()
        )

    def row(self, lines: list[str], activity: float = 1_000.0) -> dict[str, Any]:
        row = runtime_sessions.base_session("claude", "sid-1", "recce/cargento")
        row.update({"state": "working", "last_activity": activity, "own_activity": activity})
        for k, text in enumerate(lines, start=1):
            row[f"annotation_line_{k}"] = text
            row[f"annotation_line_{k}_source"] = "typed"
        return row

    def test_each_line_is_its_own_flat_field_with_its_source(self) -> None:
        history.record(self.config, [self.row(SIX)], now=1_000.0)

        entries, _reset = history.load(self.config)

        self.assertEqual(SIX, [entries[0][f"annotation_line_{k}"] for k in range(1, 7)])  # type: ignore[literal-required]
        self.assertEqual("typed", entries[0]["annotation_line_1_source"])

    def test_a_line_is_capped_at_256_characters_and_scrubbed(self) -> None:
        history.record(self.config, [self.row(["a\u202eb" + "z" * 400])], now=1_000.0)

        entries, _reset = history.load(self.config)

        stored = entries[0]["annotation_line_1"]
        self.assertEqual(256, len(stored))
        self.assertNotIn("\u202e", stored)

    def test_editing_a_line_is_a_transition(self) -> None:
        history.record(self.config, [self.row(["one"])], now=1_000.0)
        history.record(self.config, [self.row(["two"], activity=1_000.0)], now=1_001.0)

        entries, _reset = history.load(self.config)

        self.assertEqual(["one", "two"], [entry["annotation_line_1"] for entry in entries])

    def test_a_version_three_record_brings_its_expected_output_forward_as_line_one(self) -> None:
        path = history.store_path(self.config)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        record = {
            "harness": "claude",
            "sid": "sid-1",
            "project": "recce/cargento",
            "state": "working",
            "last_activity": 1_000.0,
            "annotation_goal": "G",
            "annotation_output": "a CSV export",
            "annotation_revision": 2,
        }
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"v": 3, "entries": [record]}, handle)

        entries, reset = history.load(self.config)

        self.assertIsNone(reset)
        self.assertEqual("a CSV export", entries[0]["annotation_line_1"])
        self.assertEqual("typed", entries[0]["annotation_line_1_source"])
        self.assertEqual("", entries[0]["annotation_line_2"])
        self.assertNotIn("annotation_output", entries[0])

    def test_the_store_version_moved_and_still_reads_the_old_ones(self) -> None:
        self.assertEqual(4, history.SCHEMA_VERSION)
        self.assertEqual((1, 2, 3, 4), history.READABLE_VERSIONS)

    def test_every_line_is_an_allowlisted_carrier_and_the_old_field_is_gone(self) -> None:
        lines = tuple(f"annotation_line_{k}" for k in range(1, 7))
        self.assertEqual(("first_prompt", "annotation_goal", *lines), history.PROMPT_TEXT_ALLOWLIST)
        for name in ("annotation_output",):
            self.assertNotIn(name, history.OBSERVATION_FIELDS)
            self.assertNotIn(name, history.PROMPT_TEXT_ALLOWLIST)
        for name in lines:
            self.assertIn(name, history.PROMPT_DERIVED_CARRIERS)


# -------------------------------------------------------------------------------------- HTTP


class TheAnnotateRouteTakesAListTest(unittest.TestCase):
    def setUp(self) -> None:
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        self.config, self.state = make_runtime(state_home=home, state_dir=Path(home))
        self.application = cli.build_application(self.config, self.state, clock=lambda: NOW)

    @contextlib.contextmanager
    def serving(self) -> Any:
        httpd = make_server(application=self.application)
        thread = serve_until_closed(httpd)
        try:
            yield httpd.server_port
        finally:
            httpd.shutdown()
            thread.join(timeout=5)

    @staticmethod
    def post(port: int, body: bytes) -> tuple[int, bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.request("POST", "/api/annotate", body=body, headers={"Content-Type": "text/plain"})
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def test_a_list_of_lines_is_saved_and_answered_as_stored(self) -> None:
        with self.serving() as port:
            status, body = self.post(
                port, json.dumps({"harness": "claude", "sid": "s-1", "lines": SIX[:2]}).encode()
            )

        self.assertEqual(200, status)
        self.assertEqual("stored", json.loads(body)["outcome"])
        entry = annotation_store.find(annotation_store.load(self.config), "claude", "s-1")
        assert entry is not None
        self.assertEqual(SIX[:2], [line["text"] for line in entry["revisions"][-1]["lines"]])

    def test_anything_but_a_list_of_strings_is_refused_with_400(self) -> None:
        for lines in ("one line", [1, 2], [{"text": "x", "source": "entry"}], {"a": 1}):
            with self.subTest(lines=lines), self.serving() as port:
                status, _body = self.post(
                    port, json.dumps({"harness": "claude", "sid": "s-1", "lines": lines}).encode()
                )
                self.assertEqual(400, status)
        self.assertEqual((), annotation_store.load(self.config))

    def test_a_seventh_line_answers_refused_and_mints_nothing(self) -> None:
        with self.serving() as port:
            status, body = self.post(
                port,
                json.dumps(
                    {"harness": "claude", "sid": "s-1", "lines": [*SIX, "seventh"]}
                ).encode(),
            )

        self.assertEqual(200, status)
        self.assertEqual("refused", json.loads(body)["outcome"])
        self.assertEqual((), annotation_store.load(self.config))

    def test_a_non_integer_expected_revision_is_refused_with_400(self) -> None:
        with self.serving() as port:
            status, _body = self.post(
                port,
                json.dumps(
                    {"harness": "claude", "sid": "s-1", "lines": ["a"], "expected_revision": True}
                ).encode(),
            )

        self.assertEqual(400, status)

    def test_the_body_cap_is_8192_bytes(self) -> None:
        self.assertEqual(8_192, self.config.annotation_body_cap_bytes)
        base = {"harness": "claude", "sid": "s-1", "lines": ["a"], "pad": ""}
        spare = 8_192 - len(json.dumps(base).encode())
        with self.serving() as port:
            fits, _ = self.post(port, json.dumps({**base, "pad": "p" * spare}).encode())
            over, _ = self.post(port, json.dumps({**base, "pad": "p" * (spare + 1)}).encode())

        self.assertEqual((200, 413), (fits, over))

    def test_six_astral_lines_and_a_goal_fit_the_body_the_page_sends(self) -> None:
        astral = "\U0001f600" * 240
        body = json.dumps(
            {
                "harness": "claude",
                "sid": "x" * 64,
                "goal": astral,
                "lines": [astral] * 6,
                "expected_revision": 123456,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()

        self.assertLessEqual(len(body), self.config.annotation_body_cap_bytes)


# -------------------------------------------------------------------------------------- docs


class TheRulingStatesEveryFigureTest(unittest.TestCase):
    """DEC-24 item 3: the layer that first stores or sends lines writes each figure there."""

    def item_three(self) -> str:
        text = (REPO / "docs" / "design-reading-a-session.md").read_text(encoding="utf-8")
        section = text[text.index("## DEC-24") :]
        start = section.index("\n3. The checklist.")
        return re.sub(r"\s+", " ", section[start : section.index("\n4. ", start)])

    def test_each_bound_is_written_into_item_three_as_the_code_holds_it(self) -> None:
        config = make_config()
        item = self.item_three()
        figures = {
            "lines": f"{reading.MAX_OUTCOME_LINES} lines",
            "line cap": f"{config.annotation_text_cap_chars} characters",
            "prompt share": f"{reading.INTENT_SHARE_BYTES:,} of {observer.OBSERVER_MODEL_MAX_PROMPT_BYTES:,} bytes",
            "reply cap": f"{reading.REPLY_CAP_BYTES:,} bytes",
            "body cap": f"{config.annotation_body_cap_bytes:,} bytes",
            "read limit": f"{config.annotation_read_cap_bytes // (1024 * 1024)} MiB",
            "history": f"{history.FIELD_CAP_CHARS} characters",
        }
        for name, figure in figures.items():
            with self.subTest(bound=name):
                self.assertIn(figure, item)
        self.assertNotIn("have no figure yet", item)


if __name__ == "__main__":
    unittest.main()
