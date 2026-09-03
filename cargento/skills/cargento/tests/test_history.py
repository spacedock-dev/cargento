"""The history store: what this server observed, kept on this machine.

`SECURITY.md`'s "Local history (the session history store)" section is the
contract these tests hold the code to. The bounds are DEC-6's ruling (Linear
DRC-4234), not this file's preferences, and the expected values here are
literals or come from `test_sessions.DECLARED_SESSION_FIELDS` rather than from
`history.py`'s own constants — a test that reads the subject's constants proves
only that the subject is self-consistent.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cargento_runtime import history
from cargento_runtime import sessions as runtime_sessions

from .support import make_config
from .support import os_name as support_os_name

if TYPE_CHECKING:
    from cargento_runtime.config import RuntimeConfig

# Every field that can carry operator text onto a row. The first four are the
# ones the contract's never-list enumerates; the last three are the nested
# carriers it does not, which the runtime itself enumerates and which a store
# retaining whole rows would retain. AC2 exists because the never-list is
# incomplete against the row.
SENTINELS = {
    "title": "SENTINEL-TITLE-e1",
    "last_prompt": "SENTINEL-PROMPT-e2",
    "state_detail": "SENTINEL-DETAIL-e3",
    "instruction": "SENTINEL-INSTRUCTION-e4",
    "task_subject": "SENTINEL-TASKSUBJECT-e5",
    "task_active_form": "SENTINEL-ACTIVEFORM-e6",
    "subagent_name": "SENTINEL-SUBAGENT-e7",
}


def loaded_row(state: str = "working", *, last_activity: float = 1_000.0) -> dict[str, Any]:
    """A published row carrying operator text in every field that can hold it."""
    row = runtime_sessions.base_session("claude", "sid-1", "recce/cargento")
    row.update(
        {
            "state": state,
            "last_activity": last_activity,
            "own_activity": last_activity,
            "title": SENTINELS["title"],
            "last_prompt": SENTINELS["last_prompt"],
            "state_detail": SENTINELS["state_detail"],
            "instruction": {"text": SENTINELS["instruction"], "kind": "plan"},
            "tasks": [
                {
                    "subject": SENTINELS["task_subject"],
                    "activeForm": SENTINELS["task_active_form"],
                    "status": "in_progress",
                }
            ],
            "subagents": [{"name": SENTINELS["subagent_name"], "sid": "child-1"}],
        }
    )
    return row


class HistoryStoreTestCase(unittest.TestCase):
    """One temporary state home per test, so no test reads another's store."""

    def setUp(self) -> None:
        self._home = tempfile.TemporaryDirectory()
        self.addCleanup(self._home.cleanup)
        self.state_home = self._home.name
        self.diagnostics: list[str] = []

    def config(self, **changes: Any) -> RuntimeConfig:
        fields: dict[str, Any] = {
            "state_home": self.state_home,
            "state_dir": Path(self.state_home),
            "os_name": support_os_name(),
        }
        fields.update(changes)
        return make_config(**fields)

    def store_bytes(self, config: RuntimeConfig) -> bytes:
        with open(history.store_path(config), "rb") as handle:
            return handle.read()


class NothingPromptDerivedReachesTheStoreTest(HistoryStoreTestCase):
    """AC2: nothing in the store is prompt-derived, proven against a fixture
    that would carry it.

    Read at the bytes rather than at the schema on purpose. A schema assertion
    passes for a store that retains `tasks` and `subagents` wholesale, because
    those keys are themselves published; what the never-list bans is the text
    inside them. Reading the file is the only check that catches a nested
    carrier, which is the exposure triage found the contract's never-list omits.
    """

    def test_no_operator_text_appears_anywhere_in_the_store_bytes(self) -> None:
        config = self.config()
        history.record(config, [loaded_row()], now=1_000.0)
        raw = self.store_bytes(config)
        for field, sentinel in SENTINELS.items():
            with self.subTest(field=field):
                self.assertNotIn(
                    sentinel.encode("utf-8"),
                    raw,
                    f"{field} reached the history store",
                )

    def test_the_store_kept_the_observation_it_was_given(self) -> None:
        # The negative above is satisfiable by a store that writes nothing at
        # all, so it is paired with the positive: the recording cycle really did
        # run and really did keep the transition.
        config = self.config()
        history.record(config, [loaded_row()], now=1_000.0)
        payload = json.loads(self.store_bytes(config))
        self.assertEqual(1, len(payload["entries"]))
        self.assertEqual("working", payload["entries"][0]["state"])


class EveryStoredFieldIsAPublishedFieldTest(HistoryStoreTestCase):
    """AC1: every field in the store is a field the board publishes, and none is
    on the never-list.

    Both expected sets come from outside `history.py`: the published set is
    `test_sessions`'s hand-written declaration, and the ban list is a literal
    here. Reading `history.OBSERVATION_FIELDS` for both sides would prove only
    that the module agrees with itself.
    """

    # The contract's four named carriers plus the three nested ones it omits.
    # `spacedock` is a third nested object with the same exposure.
    BANNED = (
        "title",
        "last_prompt",
        "state_detail",
        "instruction",
        "tasks",
        "subagents",
        "spacedock",
    )

    def published_fields(self) -> frozenset[str]:
        from .test_sessions import CargentoServerTest  # noqa: PLC0415

        return frozenset(CargentoServerTest.DECLARED_SESSION_FIELDS)

    def test_the_record_keeps_only_fields_the_board_already_publishes(self) -> None:
        record = history.observation(loaded_row())
        assert record is not None
        self.assertTrue(
            set(record) <= self.published_fields(),
            f"history keeps unpublished fields: {sorted(set(record) - self.published_fields())}",
        )

    def test_the_record_holds_no_operator_text_carrier(self) -> None:
        record = history.observation(loaded_row())
        assert record is not None
        self.assertEqual(frozenset(), frozenset(record) & frozenset(self.BANNED))

    def test_the_declared_field_tuple_is_what_a_record_actually_has(self) -> None:
        # Keeps the tuple the oracle above reads honest against the builder: a
        # field added to one and not the other would otherwise pass both.
        record = history.observation(loaded_row())
        assert record is not None
        self.assertEqual(set(history.OBSERVATION_FIELDS), set(record))

    def test_a_row_keyed_on_a_working_directory_is_not_what_gets_stored(self) -> None:
        # The never-list bans the paths the project label is derived from. The
        # label is kept (D4); a raw cwd is not, and no `cwd` key is published.
        record = history.observation(loaded_row())
        assert record is not None
        self.assertNotIn("cwd", record)
        self.assertEqual("recce/cargento", record["project"])


class EvictionTest(HistoryStoreTestCase):
    """AC3: eviction is by age first and the cap cannot resurrect a dropped
    observation."""

    def entries(self, stamps: list[float]) -> list[history.Observation]:
        return [
            history.Observation(
                harness="claude",
                sid=f"s{int(stamp)}",
                project="p/q",
                state="working",
                last_activity=stamp,
            )
            for stamp in stamps
        ]

    def test_records_outside_the_retention_window_are_gone(self) -> None:
        kept = history.evict(
            self.entries([100.0, 5_000.0]),
            now=10_000.0,
            retention_sec=6_000.0,
            max_bytes=1_048_576,
        )
        self.assertEqual([5_000.0], [e["last_activity"] for e in kept])

    def test_inside_the_window_the_size_cap_drops_the_oldest_first(self) -> None:
        # Falsified by a refuse-when-full policy like the dismissal store's,
        # under which the NEWEST records would be the ones missing.
        stamps = [float(x) for x in range(1_000, 1_100)]
        kept = history.evict(
            self.entries(stamps),
            now=1_100.0,
            retention_sec=1_000_000.0,
            max_bytes=400,
        )
        self.assertLess(len(kept), len(stamps))
        surviving = [e["last_activity"] for e in kept]
        self.assertEqual(sorted(surviving), surviving)
        self.assertEqual(max(stamps), surviving[-1], "the newest observation was evicted")
        self.assertNotIn(min(stamps), surviving, "the oldest observation survived the cap")

    def test_raising_the_cap_after_an_age_eviction_brings_nothing_back(self) -> None:
        config = self.config(history_retention_sec=500.0)
        history.record(config, [loaded_row(last_activity=1_000.0)], now=1_000.0)
        # A second collection, far enough on that the first observation is
        # outside the window, which writes the file without it.
        history.record(config, [loaded_row("idle", last_activity=9_000.0)], now=9_000.0)
        after_eviction = self.store_bytes(config)
        raised = self.config(history_retention_sec=500.0, history_max_bytes=8_388_608)
        entries, reset = history.load(raised)
        self.assertIsNone(reset)
        self.assertEqual(after_eviction, self.store_bytes(raised))
        self.assertNotIn(1_000.0, [e["last_activity"] for e in entries])


class OwnerOnlyWriteTest(HistoryStoreTestCase):
    """AC4: the file is created owner-only through a temp file and a rename."""

    @unittest.skipIf(os.name == "nt", "the mode is advisory on Windows")
    def test_the_store_is_owner_only_from_the_open_call(self) -> None:
        config = self.config()
        history.record(config, [loaded_row()], now=1_000.0)
        self.assertEqual(0o600, os.stat(history.store_path(config)).st_mode & 0o777)

    @unittest.skipIf(os.name == "nt", "the mode is advisory on Windows")
    def test_the_directory_is_owner_only(self) -> None:
        home = os.path.join(self.state_home, "nested")
        config = self.config(state_home=home, state_dir=Path(home))
        history.record(config, [loaded_row()], now=1_000.0)
        self.assertEqual(0o700, os.stat(home).st_mode & 0o777)

    def test_a_failed_write_leaves_no_temp_file_behind(self) -> None:
        # The store home is a file rather than a directory, so makedirs fails
        # and the write reports rather than raising.
        blocked = os.path.join(self.state_home, "blocked")
        with open(blocked, "w", encoding="utf-8") as handle:
            handle.write("not a directory")
        config = self.config(state_home=blocked, state_dir=Path(blocked))
        self.assertFalse(
            history.save(config, [], diagnostic_sink=self.diagnostics.append),
        )
        self.assertTrue(any("history store" in line for line in self.diagnostics))
        self.assertFalse(
            [name for name in os.listdir(self.state_home) if name.endswith(".tmp")],
        )


class UnreadableStoreIsDiscardedTest(HistoryStoreTestCase):
    """AC5: an unreadable store is discarded, the board starts empty, and the
    reason is distinguishable."""

    def write_store(self, payload: object) -> None:
        with open(os.path.join(self.state_home, history.STORE_FILENAME), "w") as handle:
            handle.write(payload if isinstance(payload, str) else json.dumps(payload))

    def test_corrupt_bytes_start_empty_and_report_a_corruption_reset(self) -> None:
        self.write_store("{not json at all")
        entries, reset = history.load(self.config())
        self.assertEqual((), entries)
        self.assertEqual(history.RESET_UNREADABLE, reset)

    def test_a_version_the_build_cannot_read_reports_a_version_reset(self) -> None:
        # D1: distinguishable from corruption, because a corruption reset may be
        # the user's disk and a version reset is ours.
        self.write_store({"v": history.SCHEMA_VERSION + 1, "entries": []})
        entries, reset = history.load(self.config())
        self.assertEqual((), entries)
        self.assertEqual(history.RESET_VERSION, reset)

    def test_a_store_larger_than_the_cap_is_discarded_unread(self) -> None:
        self.write_store({"v": history.SCHEMA_VERSION, "entries": []})
        entries, reset = history.load(self.config(history_max_bytes=4))
        self.assertEqual((), entries)
        self.assertEqual(history.RESET_UNREADABLE, reset)

    def test_no_file_at_all_is_a_first_run_and_not_a_reset(self) -> None:
        # Reporting a reset here would tell a new user their history was lost.
        entries, reset = history.load(self.config())
        self.assertEqual((), entries)
        self.assertIsNone(reset)

    def test_one_malformed_record_does_not_discard_the_others(self) -> None:
        self.write_store(
            {
                "v": history.SCHEMA_VERSION,
                "entries": [
                    {
                        "harness": "claude",
                        "sid": "a",
                        "project": "p",
                        "state": "idle",
                        "last_activity": 5.0,
                    },
                    {"harness": "claude", "sid": "b"},
                ],
            }
        )
        entries, reset = history.load(self.config())
        self.assertIsNone(reset)
        self.assertEqual(["a"], [e["sid"] for e in entries])


class OffMeansOffTest(HistoryStoreTestCase):
    """AC6: with the store off, nothing is written and nothing is read back."""

    def test_nothing_is_written_when_the_store_is_off(self) -> None:
        config = self.config(history_enabled=False)
        history.record(config, [loaded_row()], now=1_000.0)
        self.assertFalse(os.path.exists(history.store_path(config)))

    def test_an_existing_store_is_not_read_back_when_off(self) -> None:
        # Falsified by gating only the write, which would leave the board
        # opening with a memory the user asked it not to keep.
        on = self.config()
        history.record(on, [loaded_row()], now=1_000.0)
        self.assertTrue(os.path.exists(history.store_path(on)))
        entries, reset = history.load(self.config(history_enabled=False))
        self.assertEqual((), entries)
        self.assertIsNone(reset)


class ForgetTest(HistoryStoreTestCase):
    """AC8's file half: `--forget` deletes the store whether or not it is on."""

    def test_the_file_is_removed(self) -> None:
        config = self.config()
        history.record(config, [loaded_row()], now=1_000.0)
        self.assertTrue(history.forget(config))
        self.assertFalse(os.path.exists(history.store_path(config)))

    def test_it_removes_the_file_even_with_the_store_disabled(self) -> None:
        # Falsified by deleting only when enabled: someone who turned the
        # feature off and then asked for the file to go must not be told there
        # was nothing to delete.
        on = self.config()
        history.record(on, [loaded_row()], now=1_000.0)
        self.assertTrue(history.forget(self.config(history_enabled=False)))
        self.assertFalse(os.path.exists(history.store_path(on)))

    def test_deleting_a_store_that_is_not_there_reports_it(self) -> None:
        self.assertFalse(history.forget(self.config()))


class TransitionsAreDerivedTest(HistoryStoreTestCase):
    """The record is a transition, not a sample: what makes the file grow with
    what changed rather than with how often the board was collected."""

    def test_an_unchanged_state_records_nothing_new(self) -> None:
        config = self.config()
        history.record(config, [loaded_row("working", last_activity=1_000.0)], now=1_000.0)
        history.record(config, [loaded_row("working", last_activity=1_100.0)], now=1_100.0)
        entries, _ = history.load(config)
        self.assertEqual(1, len(entries))

    def test_a_changed_state_is_recorded_once(self) -> None:
        config = self.config()
        history.record(config, [loaded_row("working", last_activity=1_000.0)], now=1_000.0)
        history.record(config, [loaded_row("idle", last_activity=1_100.0)], now=1_100.0)
        entries, _ = history.load(config)
        self.assertEqual(["working", "idle"], [e["state"] for e in entries])

    def test_the_baseline_survives_a_restart(self) -> None:
        # The baseline is read from the store rather than from process memory,
        # so the first collection after a restart does not re-record every
        # session's current state as a fresh transition.
        config = self.config()
        history.record(config, [loaded_row("working", last_activity=1_000.0)], now=1_000.0)
        history.record(config, [loaded_row("working", last_activity=2_000.0)], now=2_000.0)
        entries, _ = history.load(config)
        self.assertEqual(1, len(entries))

    def test_a_row_with_no_activity_reading_records_nothing(self) -> None:
        # One-sided on purpose: a 0 stamp is the declared default rather than a
        # measurement, and an observation stamped at the epoch is one age
        # eviction drops on its next pass.
        config = self.config()
        row = loaded_row()
        row["last_activity"] = 0
        history.record(config, [row], now=1_000.0)
        self.assertFalse(os.path.exists(history.store_path(config)))


class PublishedFieldTest(HistoryStoreTestCase):
    """The board carries the history, so a panel can be seeded from it.

    Built over stub harnesses the way `test_dismissals` is, because the subject
    is what `collect` publishes rather than what any real store contains.
    """

    def spec(self, rows: list[dict[str, Any]]) -> Any:
        from cargento_runtime import aggregate  # noqa: PLC0415
        from cargento_runtime import sessions as rs  # noqa: PLC0415

        def discover(config: Any, state: Any) -> bool:
            del config, state
            return True

        def collect(
            config: Any, state: Any, now: float, window_hours: float, show_all: bool
        ) -> list[dict[str, Any]]:
            del config, state, now, window_hours, show_all
            out = []
            for row in rows:
                session = rs.base_session("claude", row["sid"], "recce/cargento")
                session.update(row)
                out.append(session)
            return out

        return aggregate.HarnessSpec(
            key="claude", label="Claude", discover=discover, collect=collect
        )

    def application(self, rows: list[dict[str, Any]], *, config: RuntimeConfig) -> Any:
        from cargento_runtime import aggregate  # noqa: PLC0415
        from cargento_runtime import history as h  # noqa: PLC0415
        from cargento_runtime.state import build_runtime_state  # noqa: PLC0415

        state = build_runtime_state(config, started=1_700_000_000.0)
        application = aggregate.Application(
            config,
            state,
            (self.spec(rows),),
            native_notifier=lambda platform: f"stub@{platform}",
            popup_notifier=lambda *_: None,
            diagnostic_sink=self.diagnostics.append,
            clock=lambda: 5_000.0,
        )
        application.history_lane = h.Lane(config, diagnostic_sink=self.diagnostics.append)
        return application

    def test_a_collection_publishes_the_observations_it_recorded(self) -> None:
        config = self.config()
        rows = [{"sid": "sid-1", "state": "working", "last_activity": 4_900.0}]
        payload = self.application(rows, config=config).collect(show_all=True)
        self.assertEqual(1, len(payload["history"]))
        self.assertEqual("working", payload["history"][0]["state"])
        self.assertEqual("recce/cargento", payload["history"][0]["project"])

    def test_no_operator_text_reaches_the_published_field_either(self) -> None:
        # The store's bytes are checked by AC2; this is the other exit, because a
        # field published to the browser is as much a disclosure as a file.
        config = self.config()
        rows = [
            {
                "sid": "sid-1",
                "state": "working",
                "last_activity": 4_900.0,
                "title": SENTINELS["title"],
                "state_detail": SENTINELS["state_detail"],
                "tasks": [{"subject": SENTINELS["task_subject"], "status": "in_progress"}],
            }
        ]
        payload = self.application(rows, config=config).collect(show_all=True)
        published = json.dumps(payload["history"])
        for sentinel in SENTINELS.values():
            self.assertNotIn(sentinel, published)

    def test_the_field_is_absent_when_the_store_is_off(self) -> None:
        config = self.config(history_enabled=False)
        rows = [{"sid": "sid-1", "state": "working", "last_activity": 4_900.0}]
        payload = self.application(rows, config=config).collect(show_all=True)
        self.assertNotIn("history", payload)

    def test_a_version_reset_is_reported_to_the_header(self) -> None:
        with open(os.path.join(self.state_home, history.STORE_FILENAME), "w") as handle:
            json.dump({"v": history.SCHEMA_VERSION + 1, "entries": []}, handle)
        config = self.config()
        rows = [{"sid": "sid-1", "state": "working", "last_activity": 4_900.0}]
        payload = self.application(rows, config=config).collect(show_all=True)
        self.assertEqual(history.RESET_VERSION, payload["history_reset"])

    def test_a_clean_open_reports_no_reset(self) -> None:
        config = self.config()
        rows = [{"sid": "sid-1", "state": "working", "last_activity": 4_900.0}]
        payload = self.application(rows, config=config).collect(show_all=True)
        self.assertNotIn("history_reset", payload)

    def test_a_collection_with_no_lane_publishes_nothing_and_does_not_raise(self) -> None:
        # The pre-history behaviour, which is what makes the lane an assembly
        # change rather than a branch in the collection.
        from cargento_runtime import aggregate  # noqa: PLC0415
        from cargento_runtime.state import build_runtime_state  # noqa: PLC0415

        config = self.config()
        state = build_runtime_state(config, started=1_700_000_000.0)
        app = aggregate.Application(
            config,
            state,
            (self.spec([{"sid": "sid-1", "state": "working", "last_activity": 4_900.0}]),),
            native_notifier=lambda platform: f"stub@{platform}",
            popup_notifier=lambda *_: None,
            diagnostic_sink=self.diagnostics.append,
            clock=lambda: 5_000.0,
        )
        payload = app.collect(show_all=True)
        self.assertEqual([], payload["history"])
        self.assertFalse(os.path.exists(history.store_path(config)))


class LaneTest(HistoryStoreTestCase):
    """The recording lane, which is governed by `--no-history` alone."""

    def test_the_lane_records_and_returns_the_whole_history(self) -> None:
        from cargento_runtime.history import Lane  # noqa: PLC0415

        config = self.config()
        lane = Lane(config, diagnostic_sink=self.diagnostics.append)
        first = lane.record([loaded_row("working", last_activity=1_000.0)], now=1_000.0)
        second = lane.record([loaded_row("idle", last_activity=1_100.0)], now=1_100.0)
        self.assertEqual(["working"], [e["state"] for e in first])
        self.assertEqual(["working", "idle"], [e["state"] for e in second])

    def test_the_lane_writes_nothing_when_the_store_is_off(self) -> None:
        from cargento_runtime.history import Lane  # noqa: PLC0415

        config = self.config(history_enabled=False)
        lane = Lane(config, diagnostic_sink=self.diagnostics.append)
        self.assertEqual([], lane.record([loaded_row()], now=1_000.0))
        self.assertFalse(os.path.exists(history.store_path(config)))

    def test_the_reset_reason_is_latched_for_the_life_of_the_run(self) -> None:
        # Re-derived per collection it would announce the reset once and then
        # fall silent while the board it emptied was still on screen, because
        # the first recording rewrites the store.
        from cargento_runtime.history import Lane  # noqa: PLC0415

        with open(os.path.join(self.state_home, history.STORE_FILENAME), "w") as handle:
            handle.write("{corrupt")
        config = self.config()
        lane = Lane(config, diagnostic_sink=self.diagnostics.append)
        lane.record([loaded_row()], now=1_000.0)
        entries, reset = history.load(config)
        self.assertIsNone(reset, "the store on disk is readable again")
        self.assertEqual(1, len(entries))
        self.assertEqual(history.RESET_UNREADABLE, lane.notice())


class ForgetIsACommandAndNotARouteTest(HistoryStoreTestCase):
    """AC8: `--forget` deletes the store and exits, and adds no route."""

    def test_forget_deletes_the_store_and_exits_without_serving(self) -> None:
        import sys  # noqa: PLC0415
        from unittest import mock  # noqa: PLC0415

        from cargento_runtime import cli, http_api  # noqa: PLC0415

        config = self.config()
        history.record(config, [loaded_row()], now=1_000.0)
        path = history.store_path(config)
        self.assertTrue(os.path.exists(path))
        with (
            mock.patch.dict(os.environ, {"CARGENTO_HOME": self.state_home}),
            mock.patch.object(sys, "argv", ["server.py", "--forget"]),
            # Binding a socket here would be the defect: a one-shot command must
            # exit without ever standing a server up.
            mock.patch.object(http_api, "CargentoHTTPServer") as served,
        ):
            code = cli.main()
        self.assertEqual(0, code)
        self.assertFalse(os.path.exists(path))
        served.assert_not_called()

    def test_forget_reports_when_there_was_nothing_to_delete(self) -> None:
        import sys  # noqa: PLC0415
        from unittest import mock  # noqa: PLC0415

        from cargento_runtime import cli  # noqa: PLC0415
        from cargento_runtime import io as runtime_io  # noqa: PLC0415

        with (
            mock.patch.dict(os.environ, {"CARGENTO_HOME": self.state_home}),
            mock.patch.object(sys, "argv", ["server.py", "--forget"]),
            mock.patch.object(runtime_io, "diag") as diag,
        ):
            self.assertEqual(0, cli.main())
        self.assertIn("no history store", " ".join(str(c) for c in diag.call_args_list))

    def test_the_post_surface_did_not_grow(self) -> None:
        # The contract lists "a history file reachable over the port" as a
        # security bug, so the count is asserted rather than trusted: eight POST
        # routes, being the seven-entry exact-match table plus the one prefix
        # match ahead of it, and no path naming history among them.
        import ast  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415

        from cargento_runtime import http_api  # noqa: PLC0415

        source = Path(http_api.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        post = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "do_POST"
        )
        tables = [node for node in ast.walk(post) if isinstance(node, ast.Dict)]
        self.assertEqual(1, len(tables), "do_POST grew a second route table")
        routes = [
            key.value
            for key in tables[0].keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        ]
        self.assertEqual(7, len(routes))
        prefixes = [
            node
            for node in ast.walk(post)
            if isinstance(node, ast.Attribute) and node.attr == "startswith"
        ]
        self.assertEqual(1, len(prefixes))
        for route in routes:
            self.assertNotIn("history", route)
            self.assertNotIn("forget", route)

    def test_no_get_route_serves_the_history_file(self) -> None:
        from pathlib import Path  # noqa: PLC0415

        from cargento_runtime import http_api  # noqa: PLC0415

        source = Path(http_api.__file__).read_text(encoding="utf-8")
        self.assertNotIn(history.STORE_FILENAME, source)
        self.assertNotIn("/api/history", source)


class ATamperedStoreCannotReorderTheBoardTest(HistoryStoreTestCase):
    """The store is a file any local process could have replaced, and its four
    strings reach the DOM through `/api/data`.

    The write path is safe by construction: every value comes off a row that has
    already been through `records.safe_text`. The read-back path is not, which is
    why `dismissals.py` bounds its own two strings on the way in and cites the
    same reason. This is that check, one store over.
    """

    def write_store(self, entry: dict[str, Any]) -> None:
        with open(os.path.join(self.state_home, history.STORE_FILENAME), "w") as handle:
            json.dump({"v": history.SCHEMA_VERSION, "entries": [entry]}, handle)

    def base(self, **changes: Any) -> dict[str, Any]:
        entry = {
            "harness": "claude",
            "sid": "sid-1",
            "project": "p/q",
            "state": "working",
            "last_activity": 1_000.0,
        }
        entry.update(changes)
        return entry

    def test_a_bidi_override_in_a_project_label_is_stripped(self) -> None:
        # U+202E reorders how everything after it renders, so a stored label
        # could make a row read as something it does not say.
        self.write_store(self.base(project="safe\u202egnop.exe"))
        entries, reset = history.load(self.config())
        self.assertIsNone(reset)
        self.assertNotIn("\u202e", entries[0]["project"])

    def test_control_characters_are_stripped_from_every_stored_string(self) -> None:
        self.write_store(
            self.base(harness="cla\x00ude", sid="s\x1bid", project="p\x7fq", state="wor\nking")
        )
        entries, _ = history.load(self.config())
        stored = entries[0]
        for field in ("harness", "sid", "project", "state"):
            with self.subTest(field=field):
                self.assertFalse(
                    any(ord(c) < 0x20 or ord(c) == 0x7F for c in str(stored[field])),
                    f"{field} kept a control character",
                )

    def test_an_overlong_stored_string_is_bounded(self) -> None:
        self.write_store(self.base(project="x" * 5_000))
        entries, _ = history.load(self.config())
        self.assertEqual(history.FIELD_CAP_CHARS, len(entries[0]["project"]))

    def test_the_zero_width_joiners_that_compose_an_emoji_survive(self) -> None:
        # ZWJ and ZWNJ cannot reorder text, and stripping them would break a
        # project label in Persian or several Indic scripts. Same carve-out
        # `records` makes, asserted here so an inlined table cannot drift into
        # the stricter range.
        self.write_store(self.base(project="a\u200cb\u200dc"))
        entries, _ = history.load(self.config())
        self.assertEqual("a\u200cb\u200dc", entries[0]["project"])
