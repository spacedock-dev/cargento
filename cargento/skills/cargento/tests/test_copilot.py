from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cargento_runtime.collectors import copilot as copilot_collector

from .support import (
    RuntimeTestCase,
    runtime,
    store_patch,
)


def write_events(root: Path, base: str, sid: str, iso: str, prompt: str) -> Path:
    """One `<base>/<sid>/events.jsonl` holding a session start and one prompt."""
    events = root / base / sid / "events.jsonl"
    events.parent.mkdir(parents=True, exist_ok=True)
    events.write_text(
        json.dumps(
            {"type": "session.start", "timestamp": iso, "data": {"context": {"cwd": "/w/p"}}}
        )
        + "\n"
        + json.dumps({"type": "user.message", "timestamp": iso, "data": {"text": prompt}})
        + "\n"
    )
    return events


def write_ledger(root: Path, rows: list[tuple[str | None, int, float]]) -> None:
    """A session-store.db whose usage rows are (session_id, nano_aiu, epoch).

    Column names and types are the ones a live `~/.copilot/session-store.db`
    carries; the table there has 23 columns and this writes the five the
    collector reads or joins on.
    """
    root.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(root / "session-store.db")
    con.execute(
        "CREATE TABLE assistant_usage_events ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT,"
        " model TEXT, total_nano_aiu INTEGER, created_at TEXT)"
    )
    con.executemany(
        "INSERT INTO assistant_usage_events (session_id, model, total_nano_aiu, created_at)"
        " VALUES (?, 'gpt-5.6-terra', ?, ?)",
        [(sid, nano, datetime.fromtimestamp(when, UTC).isoformat()) for sid, nano, when in rows],
    )
    con.commit()
    con.close()
    # discover() needs a session-state dir to consider the harness present.
    (root / "session-state" / "abcd").mkdir(parents=True, exist_ok=True)


def add_row(root: Path, session_id: str | None, amount: Any, created_at: Any) -> None:
    """One raw usage row, for the shapes `write_ledger`'s typed tuples cannot hold."""
    con = sqlite3.connect(root / "session-store.db")
    con.execute(
        "INSERT INTO assistant_usage_events (session_id, model, total_nano_aiu, created_at)"
        " VALUES (?, 'm', ?, ?)",
        (session_id, amount, created_at),
    )
    con.commit()
    con.close()


def unreadable_shapes(now: float) -> list[tuple[str, Any, Any]]:
    """Every way one row can hold spend Cargento can neither size nor place.

    `(label, total_nano_aiu, created_at)`. The first three are charges that are
    not a nano-AIU quantity — including the negative, whose meaning the store
    does not document, so it is a number Cargento cannot bank rather than a
    credit it may subtract. The last two are rows that place themselves nowhere:
    a stamp that will not parse, and one far enough ahead of the clock that
    `sessions.age` refuses it.

    Both surfaces sweep this same list, so the tile and the session row cannot
    end up disagreeing about which rows they were able to read.
    """
    stamp = datetime.fromtimestamp(now - 60, UTC).isoformat()
    return [
        ("a null charge", None, stamp),
        ("a charge that is not a number", "not a number", stamp),
        ("a negative charge", -5_000_000_000, stamp),
        ("a stamp that will not parse", 1_000_000_000, "not a timestamp"),
        (
            "a stamp ahead of the clock",
            1_000_000_000,
            datetime.fromtimestamp(now + 86_400, UTC).isoformat(),
        ),
    ]


class CopilotCollectorTest(RuntimeTestCase):
    def test_copilot_sessions_are_discovered_and_analyzed(self) -> None:
        now = time.time()
        iso = datetime.fromtimestamp(now - 5, UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            events = Path(tmp) / "session-state" / "11112222-aaaa" / "events.jsonl"
            events.parent.mkdir(parents=True)
            events.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "type": "session.start",
                                "timestamp": iso,
                                "data": {"context": {"cwd": "/w/myproj"}},
                            }
                        ),
                        json.dumps(
                            {
                                "type": "user.message",
                                "timestamp": iso,
                                "data": {"text": "fix the login bug"},
                            }
                        ),
                        json.dumps(
                            {
                                "type": "subagent.started",
                                "timestamp": iso,
                                "data": {"id": "a1", "name": "researcher"},
                            }
                        ),
                    ]
                )
                + "\n"
            )

            with store_patch(COPILOT_DIR=str(tmp)):
                config, state = runtime()
                sessions = copilot_collector.collect(config, state, now, 24, False)

        self.assertEqual(1, len(sessions))
        s = sessions[0]
        self.assertEqual("working", s["state"])
        self.assertEqual("w/myproj", s["project"])  # DRC-3963: <parent>/<basename>
        self.assertEqual("fix the login bug", s["last_prompt"])
        self.assertEqual(["researcher"], s["subagents"])

    def test_the_legacy_history_store_is_discovered_and_collected(self) -> None:
        # Copilot moved its sessions between two directories, and the older one
        # is assumed to share the <uuid>/events.jsonl layout. Mutation-checked:
        # dropping history-session-state made those sessions invisible AND
        # undiscoverable, and passed the whole suite.
        now = time.time()
        iso = datetime.fromtimestamp(now - 5, UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            write_events(Path(tmp), "history-session-state", "33334444-bbbb", iso, "old session")
            with store_patch(COPILOT_DIR=str(tmp)):
                config, state = runtime()

                self.assertTrue(copilot_collector.discover(config, state))
                sessions = copilot_collector.collect(config, state, now, 24, False)

        self.assertEqual(["33334444-bbbb"], [s["sid"] for s in sessions])
        self.assertEqual("old session", sessions[0]["last_prompt"])

    def test_a_uuid_in_both_stores_reads_from_the_newer_file(self) -> None:
        # The same uuid can exist in both stores after a migration. The newest
        # file wins, so a stale copy cannot mask live activity. Mutation-checked:
        # preferring the older file passed the whole suite.
        now = time.time()
        fresh_iso = datetime.fromtimestamp(now - 5, UTC).isoformat()
        stale_iso = datetime.fromtimestamp(now - 9000, UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            sid = "55556666-cccc"
            old = write_events(Path(tmp), "history-session-state", sid, stale_iso, "stale prompt")
            new = write_events(Path(tmp), "session-state", sid, fresh_iso, "live prompt")
            os.utime(old, (now - 9000, now - 9000))
            os.utime(new, (now - 5, now - 5))
            with store_patch(COPILOT_DIR=str(tmp)):
                config, state = runtime()
                sessions = copilot_collector.collect(config, state, now, 24, True)

        self.assertEqual(1, len(sessions), "one uuid must yield one row")
        self.assertEqual("live prompt", sessions[0]["last_prompt"])

    def test_the_cwd_falls_back_to_the_first_line_metadata(self) -> None:
        # An idle session is not analyzed, so its project label can only come
        # from the cached first-line metadata. Mutation-checked: dropping that
        # fallback passed the whole suite and every idle row read "copilot".
        now = time.time()
        stale = now - 100_000  # outside the 24-hour window
        iso = datetime.fromtimestamp(stale, UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            events = write_events(Path(tmp), "session-state", "77778888-dddd", iso, "old work")
            os.utime(events, (stale, stale))
            with store_patch(COPILOT_DIR=str(tmp)):
                config, state = runtime()
                sessions = copilot_collector.collect(config, state, now, 24, True)

        self.assertEqual(1, len(sessions))
        self.assertFalse(sessions[0]["active"], "fixture must be outside the window")
        self.assertEqual("w/p", sessions[0]["project"])


class CopilotUsageTest(RuntimeTestCase):
    """Copilot's consumption tile: real spend, no limit, windowed on row time."""

    def test_aiu_rows_sum_into_one_used_entry(self) -> None:
        now = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "copilot"
            # 0.39 AIU + 16.21 AIU, the two models this account actually used.
            write_ledger(root, [("s", 393_690_000, now - 600), ("s", 16_213_200_000, now - 60)])
            with store_patch(COPILOT_DIR=str(root)):
                config, state = runtime()
                entries = copilot_collector.usage(config, state, now, 24)

        self.assertEqual(1, len(entries))
        entry = entries[0]
        self.assertEqual("copilot", entry["harness"])
        self.assertEqual("ok", entry["state"])
        self.assertEqual("16.61 AIU", entry["used"])
        # asOf is the newest contributing row, not the collection time.
        self.assertEqual(int(now - 60), entry["asOf"])
        # Consumption has no limit, so it must never claim a window gauge.
        self.assertNotIn("fiveH", entry)
        self.assertNotIn("week", entry)

    def test_rows_outside_the_window_are_excluded(self) -> None:
        # The figure answers "in the last window_hours", so old spend must not
        # inflate it. Without this the number would drift with how much history
        # happened to be retained.
        now = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "copilot"
            write_ledger(
                root, [("s", 9_000_000_000, now - 8 * 3600), ("s", 1_000_000_000, now - 60)]
            )
            with store_patch(COPILOT_DIR=str(root)):
                config, state = runtime()
                inside = copilot_collector.usage(config, state, now, 24)
                narrow = copilot_collector.usage(config, state, now, 1)

        self.assertEqual("10.00 AIU", inside[0]["used"])
        self.assertEqual("1.00 AIU", narrow[0]["used"])

    def test_no_rows_in_the_window_publishes_nothing(self) -> None:
        now = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "copilot"
            write_ledger(root, [("s", 5_000_000_000, now - 48 * 3600)])
            with store_patch(COPILOT_DIR=str(root)):
                config, state = runtime()
                self.assertEqual([], copilot_collector.usage(config, state, now, 24))

    def test_a_missing_or_schemaless_store_is_a_miss_not_an_error(self) -> None:
        now = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "copilot"
            (root / "session-state" / "abcd").mkdir(parents=True)
            with store_patch(COPILOT_DIR=str(root)):
                config, state = runtime()
                # No database file at all.
                self.assertEqual([], copilot_collector.usage(config, state, now, 24))
                # A database with no usage table: schema drift, not a crash.
                con = sqlite3.connect(root / "session-store.db")
                con.execute("CREATE TABLE sessions (id TEXT)")
                con.commit()
                con.close()
                self.assertEqual([], copilot_collector.usage(config, state, now, 24))

    def test_no_shape_of_unreadable_row_quietly_shrinks_the_tile(self) -> None:
        # This test used to assert "2.00 AIU" here, on the reading that a row
        # Cargento could not parse was a row that did not count. The skip was the
        # poison: the store recorded a charge, the reader was shown a sum without
        # it, and nothing said the sum was short. A lower bound wearing the word
        # "used" is the same wrong number a truncated read publishes, and it goes
        # quiet for the same reason. Mutation-checked shape by shape: dropping
        # `measured = False` restored "2.00 AIU" on all five.
        now = time.time()
        for label, amount, created_at in unreadable_shapes(now):
            with self.subTest(label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "copilot"
                write_ledger(root, [("s", 2_000_000_000, now - 60)])
                add_row(root, "s", amount, created_at)
                with store_patch(COPILOT_DIR=str(root)):
                    config, state = runtime()
                    self.assertEqual([], copilot_collector.usage(config, state, now, 24))

    def test_an_unreadable_row_outside_the_window_costs_the_tile_nothing(self) -> None:
        # A row is placed before its charge is read, and this is why. An old row
        # contributes nothing whatever its charge column holds, so withholding
        # the tile over one would throw a good figure away for a row that never
        # had a vote — and week-old junk is exactly what accumulates in a ledger.
        # It still vouches for the read having reached past the window's edge.
        # Mutation-checked: reading the charge before the stamp withheld the tile.
        now = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "copilot"
            write_ledger(root, [("s", 2_000_000_000, now - 60)])
            add_row(root, "s", None, datetime.fromtimestamp(now - 48 * 3600, UTC).isoformat())
            with store_patch(COPILOT_DIR=str(root)):
                config, state = runtime()
                entries = copilot_collector.usage(config, state, now, 24)

        self.assertEqual("2.00 AIU", entries[0]["used"])


class CopilotConsumptionTest(RuntimeTestCase):
    """Per-session AIU: the measured figure, the measured zero, and no accounting.

    The join these tests exercise is measured rather than assumed. On a live
    `~/.copilot/session-store.db` the distinct `assistant_usage_events.session_id`
    values matched the `session-state/<uuid>` directory names 2 of 2, and those
    basenames are what the collector publishes as `sid`.
    """

    SID_A = "aaaa1111-2222-3333-4444-555555555555"
    SID_B = "bbbb1111-2222-3333-4444-555555555555"

    def _collect(
        self,
        root: Path,
        now: float,
        window_hours: float = 24,
    ) -> dict[str, dict[str, Any]]:
        """Every collected row for a prepared store, keyed by full sid."""
        with store_patch(COPILOT_DIR=str(root)):
            config, state = runtime()
            rows = copilot_collector.collect(config, state, now, window_hours, True)
        return {str(row["sid"]): row for row in rows}

    def test_each_session_row_carries_its_own_share_of_the_ledger(self) -> None:
        now = time.time()
        iso = datetime.fromtimestamp(now - 5, UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "copilot"
            write_events(root, "session-state", self.SID_A, iso, "one")
            write_events(root, "session-state", self.SID_B, iso, "two")
            # Two rows against SID_A. The smaller is a sidekick request, which
            # the store attributes to the session that launched it: on the live
            # store those rows carry an `agent_id`, a `request_multiplier` of
            # 0.33, and a `total_nano_aiu` that already has the multiplier in it.
            write_ledger(
                root,
                [
                    (self.SID_A, 1_016_840_000, now - 60),
                    (self.SID_A, 145_050_000, now - 50),
                    (self.SID_B, 6_428_100_000, now - 40),
                ],
            )
            rows = self._collect(root, now)

        self.assertEqual("1.16 AIU", rows[self.SID_A]["consumption"])
        self.assertEqual("6.43 AIU", rows[self.SID_B]["consumption"])

    def test_a_session_the_ledger_does_not_mention_reads_a_measured_zero(self) -> None:
        # The ledger was read to the end of the window and holds nothing for this
        # session, which is a zero somebody measured. It is a different reading
        # from the None below, and both have to survive into the payload.
        now = time.time()
        iso = datetime.fromtimestamp(now - 5, UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "copilot"
            write_events(root, "session-state", self.SID_A, iso, "spent nothing")
            write_ledger(root, [(self.SID_B, 6_428_100_000, now - 40)])
            rows = self._collect(root, now)

        self.assertEqual("0.00 AIU", rows[self.SID_A]["consumption"])

    def test_no_ledger_at_all_leaves_the_figure_unmeasured(self) -> None:
        # No session-store.db: Cargento has no accounting for this harness, and a
        # session it cannot account for must not read as one that spent nothing.
        now = time.time()
        iso = datetime.fromtimestamp(now - 5, UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "copilot"
            write_events(root, "session-state", self.SID_A, iso, "unaccounted")
            rows = self._collect(root, now)

        self.assertIsNone(rows[self.SID_A]["consumption"])

    def test_a_drifted_ledger_schema_leaves_the_figure_unmeasured(self) -> None:
        # A store that no longer carries assistant_usage_events is the same
        # nothing as a store with no database, not a store full of zeroes.
        now = time.time()
        iso = datetime.fromtimestamp(now - 5, UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "copilot"
            write_events(root, "session-state", self.SID_A, iso, "drifted")
            con = sqlite3.connect(root / "session-store.db")
            con.execute("CREATE TABLE sessions (id TEXT)")
            con.commit()
            con.close()
            rows = self._collect(root, now)

        self.assertIsNone(rows[self.SID_A]["consumption"])

    def test_the_row_and_the_tile_read_the_same_window(self) -> None:
        # The row figure and the harness tile beside it answer the same question
        # over the same span. A lifetime per-session total would hold at 24 hours
        # and diverge the moment the window narrowed, with nothing on the page to
        # say which of the two numbers the reader was looking at.
        now = time.time()
        iso = datetime.fromtimestamp(now - 5, UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "copilot"
            write_events(root, "session-state", self.SID_A, iso, "one session")
            write_ledger(
                root,
                [
                    (self.SID_A, 9_000_000_000, now - 8 * 3600),
                    (self.SID_A, 1_000_000_000, now - 60),
                ],
            )
            wide = self._collect(root, now, 24)
            narrow = self._collect(root, now, 1)
            with store_patch(COPILOT_DIR=str(root)):
                config, state = runtime()
                wide_tile = copilot_collector.usage(config, state, now, 24)
                narrow_tile = copilot_collector.usage(config, state, now, 1)

        self.assertEqual("10.00 AIU", wide[self.SID_A]["consumption"])
        self.assertEqual("10.00 AIU", wide_tile[0]["used"])
        self.assertEqual("1.00 AIU", narrow[self.SID_A]["consumption"])
        self.assertEqual("1.00 AIU", narrow_tile[0]["used"])

    def test_a_row_naming_no_session_still_counts_toward_the_harness(self) -> None:
        # Spend the ledger attributes to nobody is still spend. Dropping it would
        # understate the harness figure; handing it to a session would be worse.
        now = time.time()
        iso = datetime.fromtimestamp(now - 5, UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "copilot"
            write_events(root, "session-state", self.SID_A, iso, "one session")
            write_ledger(
                root, [(self.SID_A, 1_000_000_000, now - 60), (None, 4_000_000_000, now - 50)]
            )
            rows = self._collect(root, now)
            with store_patch(COPILOT_DIR=str(root)):
                config, state = runtime()
                tile = copilot_collector.usage(config, state, now, 24)

        self.assertEqual("1.00 AIU", rows[self.SID_A]["consumption"])
        self.assertEqual("5.00 AIU", tile[0]["used"])

    def test_an_unreadable_row_withholds_the_figure_of_the_session_it_names(self) -> None:
        # The defect this pins: an in-window row naming SID_A whose charge cannot
        # be read published "1.00 AIU" for a session the ledger says spent more,
        # and a null charge with no other row published "0.00 AIU" — a session
        # the store billed, rendered as one that was free, under a tooltip that
        # calls the zero measured. The withdrawal is scoped: SID_B's rows were all
        # readable, so its figure is exact and it keeps it.
        # Mutation-checked shape by shape: dropping the `unmeasured.add(named)`
        # returned SID_A to "1.00 AIU" on all five and passed the rest of the file.
        now = time.time()
        iso = datetime.fromtimestamp(now - 5, UTC).isoformat()
        for label, amount, created_at in unreadable_shapes(now):
            with self.subTest(label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "copilot"
                write_events(root, "session-state", self.SID_A, iso, "billed")
                write_events(root, "session-state", self.SID_B, iso, "also billed")
                write_ledger(
                    root,
                    [
                        (self.SID_A, 1_000_000_000, now - 60),
                        (self.SID_B, 3_000_000_000, now - 55),
                    ],
                )
                add_row(root, self.SID_A, amount, created_at)
                rows = self._collect(root, now)
                with store_patch(COPILOT_DIR=str(root)):
                    config, state = runtime()
                    tile = copilot_collector.usage(config, state, now, 24)

                self.assertIsNone(rows[self.SID_A]["consumption"])
                self.assertEqual("3.00 AIU", rows[self.SID_B]["consumption"])
                self.assertEqual([], tile)

    def test_an_unreadable_row_naming_no_session_withholds_only_the_tile(self) -> None:
        # The scoping decision, stated as a test. An unattributed row belongs to
        # nobody — that is the same reading of the store that keeps such a row's
        # spend out of every session's figure one test above — so an unreadable
        # one takes no session's figure with it. Only the sum it would have fed
        # goes quiet. The alternative, blacking out every session in the harness
        # over one malformed row, hands a rare fault the power to delete a real
        # signal. Mutation-checked: adding every collected sid to `unmeasured`
        # for an unattributed loss made SID_A None and passed the whole file.
        now = time.time()
        iso = datetime.fromtimestamp(now - 5, UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "copilot"
            write_events(root, "session-state", self.SID_A, iso, "attributed")
            write_ledger(root, [(self.SID_A, 1_000_000_000, now - 60)])
            add_row(root, None, None, datetime.fromtimestamp(now - 50, UTC).isoformat())
            rows = self._collect(root, now)
            with store_patch(COPILOT_DIR=str(root)):
                config, state = runtime()
                tile = copilot_collector.usage(config, state, now, 24)

        self.assertEqual("1.00 AIU", rows[self.SID_A]["consumption"])
        self.assertEqual([], tile)

    def test_a_session_older_than_the_window_has_no_zero_to_publish(self) -> None:
        # A zero is a claim that the window was read to its end and covers this
        # session. For a session last active three days ago the second half is
        # false: the ledger has no reach over the hours it was running, so
        # "0.00 AIU" answers a question about the last window_hours in the type
        # of an answer about this session. These are the rows behind "Show all N
        # idle", beside a detail panel that promises what the session spent.
        # The measured zero one test above is the counterpart: an *active*
        # session the window does cover still reads "0.00 AIU", and this must not
        # collapse the two. Mutation-checked: ignoring `active` published
        # "0.00 AIU" here and passed the whole file.
        now = time.time()
        stale = now - 100_000  # three days back, well outside the 24-hour window
        iso = datetime.fromtimestamp(stale, UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "copilot"
            events = write_events(root, "session-state", self.SID_A, iso, "long finished")
            os.utime(events, (stale, stale))
            write_ledger(root, [(self.SID_B, 6_428_100_000, now - 40)])
            rows = self._collect(root, now)

        self.assertFalse(rows[self.SID_A]["active"], "fixture must be outside the window")
        self.assertIsNone(rows[self.SID_A]["consumption"])

    def test_a_session_older_than_the_window_keeps_a_figure_the_window_holds(self) -> None:
        # Only the zero makes the coverage claim. A number claims no more than
        # that these rows exist, which is true however old the session file is,
        # and the tooltip beside it names the window. Withholding it too would
        # lose a real reading to a rule aimed at a false one.
        # Mutation-checked: returning None for every inactive session dropped
        # this figure and passed the whole file.
        now = time.time()
        stale = now - 30 * 3600  # outside a 24-hour window, its spend inside it
        iso = datetime.fromtimestamp(stale, UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "copilot"
            events = write_events(root, "session-state", self.SID_A, iso, "billed late")
            os.utime(events, (stale, stale))
            write_ledger(root, [(self.SID_A, 2_000_000_000, now - 20 * 3600)])
            rows = self._collect(root, now)

        self.assertFalse(rows[self.SID_A]["active"], "fixture must be outside the window")
        self.assertEqual("2.00 AIU", rows[self.SID_A]["consumption"])

    def _capped_ledger(self, root: Path, now: float, older: int) -> None:
        """A ledger longer than the read cap, `older` of whose rows predate 24h.

        The old rows go in first so the newest rows carry the highest ids, which
        is the order the collector reads: id descending, newest first.
        """
        rows: list[tuple[str | None, int, float]] = [
            (self.SID_A, 1_000_000, now - 48 * 3600) for _ in range(older)
        ]
        rows += [
            (self.SID_A, 1_000_000, now - 60)
            for _ in range(copilot_collector._USAGE_ROW_CAP + 1 - older)
        ]
        write_ledger(root, rows)

    def test_a_read_that_reaches_past_the_window_measures_beyond_the_cap(self) -> None:
        # The cap bounds the read, not the answer. A long-lived ledger whose read
        # still got back past the window's far edge has been read to the end of
        # the window, so the figure stands — otherwise every heavy user would
        # lose the signal permanently once their history outgrew the cap.
        now = time.time()
        iso = datetime.fromtimestamp(now - 5, UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "copilot"
            write_events(root, "session-state", self.SID_A, iso, "long history")
            self._capped_ledger(root, now, older=20)
            rows = self._collect(root, now)

        # 5001 rows read, 20 of them older than the window: 4981 in-window rows
        # at 0.001 AIU each.
        self.assertEqual("4.98 AIU", rows[self.SID_A]["consumption"])

    def test_a_read_truncated_inside_the_window_publishes_no_figure(self) -> None:
        # Every row read is inside the window, so there is unread history that
        # could hold any amount of it. A sum over what was read would be a lower
        # bound rendered as a total, and a session absent from it would read as a
        # measured zero. Both surfaces go quiet instead.
        now = time.time()
        iso = datetime.fromtimestamp(now - 5, UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "copilot"
            write_events(root, "session-state", self.SID_A, iso, "torrent")
            self._capped_ledger(root, now, older=0)
            rows = self._collect(root, now)
            with store_patch(COPILOT_DIR=str(root)):
                config, state = runtime()
                tile = copilot_collector.usage(config, state, now, 24)

        self.assertIsNone(rows[self.SID_A]["consumption"])
        self.assertEqual([], tile)

    def test_an_unreadable_stamp_does_not_vouch_for_the_window_being_read(self) -> None:
        # A row whose created_at will not parse places itself nowhere. Read as an
        # age instead, an unparseable stamp becomes an enormous one, which looks
        # exactly like the old row that proves the read reached past the window —
        # and one such row would restore both figures on a truncated read.
        #
        # SID_B carries the assertion, because SID_A no longer can. An unplaceable
        # row now withholds the figure of the session it names, so SID_A reads
        # None whether or not the vouching rule holds, and a test resting on it
        # would pass a build where that rule had been reversed. SID_B is named by
        # no bad row, so only the truncated read stands between it and a figure.
        now = time.time()
        iso = datetime.fromtimestamp(now - 5, UTC).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "copilot"
            write_events(root, "session-state", self.SID_A, iso, "torrent")
            write_events(root, "session-state", self.SID_B, iso, "a trickle beside it")
            self._capped_ledger(root, now, older=0)
            con = sqlite3.connect(root / "session-store.db")
            con.execute(
                "INSERT INTO assistant_usage_events (session_id, total_nano_aiu, created_at)"
                " VALUES (?, 1000000, ?)",
                (self.SID_B, datetime.fromtimestamp(now - 45, UTC).isoformat()),
            )
            # Highest id, so the read sees it first and cannot miss it.
            con.execute(
                "INSERT INTO assistant_usage_events (session_id, total_nano_aiu, created_at)"
                " VALUES (?, 1000000, 'not a timestamp')",
                (self.SID_A,),
            )
            con.commit()
            con.close()
            rows = self._collect(root, now)
            with store_patch(COPILOT_DIR=str(root)):
                config, state = runtime()
                tile = copilot_collector.usage(config, state, now, 24)

        self.assertIsNone(rows[self.SID_A]["consumption"])
        self.assertIsNone(rows[self.SID_B]["consumption"])
        self.assertEqual([], tile)
