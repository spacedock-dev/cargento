"""DRC-4661: two dashboards sharing one Cargento home lose no saved intent.

Every writer in `annotations` re-reads the file under `state.annotation_lock`,
which is a `threading.Lock` on one `RuntimeState`. A second dashboard is a
second state, usually a second process, so that lock never met it: a writer
paused after its read let the other dashboard commit, then renamed its older
copy over the newer one. Two states in one process reproduce it exactly,
because each carries its own lock, and the last test runs two real processes.

The rule each case holds: every write that answered `stored` is still on
disk afterwards, and no revision number is used twice. A guarded writer that
lost the race is refused with the stale-revision answer it already had.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest import mock

from cargento_runtime import annotations as annotation_store
from cargento_runtime import reading as runtime_reading
from cargento_runtime import sessions as runtime_sessions
from cargento_runtime.state import RuntimeState, build_runtime_state

from .support import make_runtime

if TYPE_CHECKING:
    from collections.abc import Callable

SKILL_DIR = Path(__file__).resolve().parents[1]
SID = "0123456789abcdef-shared-home"
FIRST = "Add retry with backoff to the webhook handler."
START = 1_800_000_000.0
FIRST_AT = START + 5
# How long the second dashboard is given to commit while the first is paused
# after its read. Before the fix it committed in milliseconds.
BLOCKED_FOR = 0.6


def _row(**extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = dict(runtime_sessions.base_session("claude", SID, "billing"))
    row.update(
        {
            "project": "billing",
            "state": "working",
            "active": True,
            "last_activity": START + 3600,
            "first_prompt": FIRST,
            "first_prompt_at": FIRST_AT,
        }
    )
    row.update(extra)
    return row


class _PauseAfterRead:
    """Stop one thread straight after its read of the store, until released."""

    def __init__(self) -> None:
        self.paused = threading.Event()
        self.release = threading.Event()
        self.thread: threading.Thread | None = None
        self._real = annotation_store._read_store

    def __call__(self, config: Any) -> Any:
        store = self._real(config)
        if threading.current_thread() is self.thread and not self.paused.is_set():
            self.paused.set()
            self.release.wait(10)
        return store


class _SharedHomeCase(unittest.TestCase):
    def setUp(self) -> None:
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        self.config, self.first = make_runtime(state_home=home, state_dir=Path(home))
        # The second dashboard: its own state, so its own `annotation_lock`.
        self.second: RuntimeState = build_runtime_state(self.config, started=START)

    def entry(self) -> Any:
        return annotation_store.find(annotation_store._read(self.config), "claude", SID)

    def race(self, first: Callable[[], str], second: Callable[[], str]) -> tuple[str, str, bool]:
        """Run `first` paused after its read, then `second`, then resume `first`.

        Returns both outcomes and whether `second` committed while `first` sat
        between its read and its write, which is the window the fix closes.
        """
        pause = _PauseAfterRead()
        outcomes: dict[str, str] = {}

        def run(name: str, write: Callable[[], str]) -> None:
            outcomes[name] = write()

        one = threading.Thread(target=run, args=("first", first))
        two = threading.Thread(target=run, args=("second", second))
        pause.thread = one
        with mock.patch.object(annotation_store, "_read_store", pause):
            one.start()
            try:
                self.assertTrue(pause.paused.wait(10), "the first writer never read the store")
                two.start()
                two.join(BLOCKED_FOR)
                committed_while_paused = not two.is_alive()
            finally:
                pause.release.set()
                one.join(20)
                if two.ident is not None:
                    two.join(20)
        self.assertFalse(one.is_alive() or two.is_alive(), "a writer never finished")
        return outcomes["first"], outcomes["second"], committed_while_paused

    def goal(self, state: RuntimeState, text: str, now: float) -> Callable[[], str]:
        return lambda: annotation_store.annotate(
            self.config, state, "claude", SID, goal=text, now=now
        )

    def assert_numbers_unique(self, entry: Any) -> None:
        numbers = [revision["n"] for revision in entry["revisions"]]
        self.assertEqual(sorted(set(numbers)), numbers)


class TheIssuesInterleavingTest(_SharedHomeCase):
    """The reproduction on the issue, step for step."""

    def test_an_older_save_resumed_after_a_newer_commit_keeps_both_revisions(self) -> None:
        first, second, overlapped = self.race(
            self.goal(self.first, "Older goal typed at 100", START + 100),
            self.goal(self.second, "Newer goal typed at 101", START + 101),
        )

        self.assertFalse(overlapped, "the second dashboard committed inside the first's window")
        self.assertEqual((annotation_store.OUTCOME_STORED,) * 2, (first, second))
        entry = self.entry()
        self.assertEqual([1, 2], [revision["n"] for revision in entry["revisions"]])
        self.assertEqual(
            ["Older goal typed at 100", "Newer goal typed at 101"],
            [revision["goal"] for revision in entry["revisions"]],
        )


class EveryWriterSharesTheBoundaryTest(_SharedHomeCase):
    """One case per writer: a stale writer never drops what the other committed."""

    def seed(self, goal: str = "Seeded goal", lines: list[str] | None = None) -> None:
        outcome = annotation_store.annotate(
            self.config, self.first, "claude", SID, goal=goal, lines=lines, now=START + 50
        )
        self.assertEqual(annotation_store.OUTCOME_STORED, outcome)

    def add_line(self, state: RuntimeState, text: str, fact: str, **over: Any) -> Callable[[], str]:
        arguments: dict[str, Any] = {
            "source_id": fact,
            "text": text,
            "entry_at": FIRST_AT + 60,
            "expected_revision": 0,
            "now": FIRST_AT + 120,
        }
        arguments.update(over)
        return lambda: annotation_store.add_direction(self.config, state, _row(), **arguments)

    def test_outcome_lines_a_stale_list_is_refused_rather_than_written_over(self) -> None:
        def lines(state: RuntimeState, text: str) -> Callable[[], str]:
            return lambda: annotation_store.annotate(
                self.config, state, "claude", SID, lines=[text], expected_revision=0, now=START
            )

        first, second, overlapped = self.race(
            lines(self.first, "First dashboard's line"),
            lines(self.second, "Second dashboard's line"),
        )

        self.assertFalse(overlapped)
        self.assertEqual(annotation_store.OUTCOME_STORED, first)
        self.assertEqual(annotation_store.OUTCOME_REFUSED, second)
        entry = self.entry()
        self.assertEqual(
            ["First dashboard's line"], [x["text"] for x in entry["revisions"][-1]["lines"]]
        )
        self.assert_numbers_unique(entry)

    def test_prompt_adoption_never_replaces_a_goal_committed_after_its_empty_check(self) -> None:
        adopt = lambda: annotation_store.adopt(  # noqa: E731
            self.config,
            self.first,
            _row(),
            source="first-prompt",
            expected_text=FIRST,
            expected_at=FIRST_AT,
            now=START + 100,
        )

        first, second, overlapped = self.race(
            adopt, self.goal(self.second, "Typed on the other dashboard", START + 101)
        )

        self.assertFalse(overlapped)
        self.assertEqual((annotation_store.OUTCOME_STORED,) * 2, (first, second))
        entry = self.entry()
        self.assertEqual("Typed on the other dashboard", entry["revisions"][-1]["goal"])
        self.assertEqual(
            [FIRST, "Typed on the other dashboard"], [r["goal"] for r in entry["revisions"]]
        )
        self.assert_numbers_unique(entry)

    def test_add_direction_a_stale_line_is_refused_and_the_committed_one_stays(self) -> None:
        first, second, overlapped = self.race(
            self.add_line(self.first, "Use the placeholder lexer", "fact:aaaaaaaaaaaaaaaa"),
            self.add_line(self.second, "Keep the parser tests", "fact:bbbbbbbbbbbbbbbb"),
        )

        self.assertFalse(overlapped)
        self.assertEqual(annotation_store.OUTCOME_STORED, first)
        self.assertEqual(annotation_store.OUTCOME_REFUSED, second)
        entry = self.entry()
        self.assertEqual(
            ["fact:aaaaaaaaaaaaaaaa"],
            [line["source_id"] for line in entry["revisions"][-1]["lines"]],
        )
        self.assertIsNotNone(entry.get("settled"))

    def test_outcome_line_adoption_and_its_settlement_survive_a_typed_goal(self) -> None:
        adopting = self.add_line(
            self.first,
            "Use the placeholder lexer",
            "fact:aaaaaaaaaaaaaaaa",
            adopt="first-prompt",
            expected_prompt=FIRST,
            expected_prompt_at=FIRST_AT,
        )

        first, second, overlapped = self.race(
            adopting, self.goal(self.second, "Typed on the other dashboard", FIRST_AT + 130)
        )

        self.assertFalse(overlapped)
        self.assertEqual((annotation_store.OUTCOME_STORED,) * 2, (first, second))
        entry = self.entry()
        latest = entry["revisions"][-1]
        self.assertEqual("Typed on the other dashboard", latest["goal"])
        self.assertEqual(["fact:aaaaaaaaaaaaaaaa"], [x.get("source_id") for x in latest["lines"]])
        self.assertEqual(FIRST_AT + 60, entry["settled"]["through"])
        self.assert_numbers_unique(entry)

    def test_keep_over_a_draft_settles_without_losing_the_other_dashboards_goal(self) -> None:
        keep = lambda: annotation_store.adopt(  # noqa: E731
            self.config,
            self.first,
            _row(),
            source="first-prompt",
            expected_text=FIRST,
            expected_at=FIRST_AT,
            now=START + 100,
            expected_revision=0,
            settle_through=START + 90,
        )

        first, second, overlapped = self.race(
            keep, self.goal(self.second, "Typed on the other dashboard", START + 101)
        )

        self.assertFalse(overlapped)
        self.assertEqual((annotation_store.OUTCOME_STORED,) * 2, (first, second))
        entry = self.entry()
        self.assertEqual("Typed on the other dashboard", entry["revisions"][-1]["goal"])
        self.assertEqual(START + 90, entry["settled"]["through"])
        self.assert_numbers_unique(entry)

    def test_a_settlement_and_a_newer_goal_both_stand_in_either_order(self) -> None:
        def settle(state: RuntimeState) -> Callable[[], str]:
            return lambda: annotation_store.settle(
                self.config, state, "claude", SID, through=START + 80, now=START + 100
            )

        for order in ("settle-first", "goal-first"):
            with self.subTest(order=order):
                self.setUp()
                self.seed()
                if order == "settle-first":
                    first, second, overlapped = self.race(
                        settle(self.first), self.goal(self.second, "Newer goal", START + 101)
                    )
                else:
                    first, second, overlapped = self.race(
                        self.goal(self.first, "Newer goal", START + 101), settle(self.second)
                    )
                self.assertFalse(overlapped)
                self.assertEqual((annotation_store.OUTCOME_STORED,) * 2, (first, second))
                entry = self.entry()
                self.assertEqual("Newer goal", entry["revisions"][-1]["goal"])
                self.assertEqual(START + 80, entry["settled"]["through"])
                self.assert_numbers_unique(entry)

    def test_a_discard_is_not_undone_by_a_save_that_read_before_it(self) -> None:
        self.seed()
        clear = lambda: annotation_store.clear(  # noqa: E731
            self.config, self.second, "claude", SID, now=START + 102
        )

        first, second, overlapped = self.race(
            self.goal(self.first, "Saved just before the discard", START + 101), clear
        )

        self.assertFalse(overlapped)
        self.assertEqual((annotation_store.OUTCOME_STORED,) * 2, (first, second))
        entry = self.entry()
        self.assertTrue(annotation_store.is_discarded(entry))
        self.assertEqual(2, annotation_store.discarded_revision(entry))

    def test_a_save_after_a_discard_never_reuses_a_revision_number(self) -> None:
        self.seed()
        clear = lambda: annotation_store.clear(  # noqa: E731
            self.config, self.first, "claude", SID, now=START + 100
        )

        first, second, overlapped = self.race(
            clear, self.goal(self.second, "Typed after the discard", START + 101)
        )

        self.assertFalse(overlapped)
        self.assertEqual((annotation_store.OUTCOME_STORED,) * 2, (first, second))
        entry = self.entry()
        # Revision 1 was discarded, so the save over the record is 2, not 1.
        self.assertEqual([2], [revision["n"] for revision in entry["revisions"]])
        self.assertEqual("Typed after the discard", entry["revisions"][-1]["goal"])

    def test_a_reading_outcome_does_not_write_away_a_newer_goal(self) -> None:
        self.seed()
        withheld = lambda: annotation_store.record_withheld(  # noqa: E731
            self.config,
            self.first,
            "claude",
            SID,
            reason=next(iter(runtime_reading.WITHHELD)),
            spent=True,
            job_id="5a4ed0e0f0a1e5",
        )

        first, second, overlapped = self.race(
            withheld, self.goal(self.second, "Newer goal", START + 101)
        )

        self.assertFalse(overlapped)
        self.assertEqual((annotation_store.OUTCOME_STORED,) * 2, (first, second))
        entry = self.entry()
        self.assertEqual("Newer goal", entry["revisions"][-1]["goal"])
        self.assertEqual(1, entry.get("readings"))
        self.assertIn("5a4ed0e0f0a1e5", entry.get("jobs", ()))

    def test_forget_does_not_write_away_a_session_saved_while_it_swept(self) -> None:
        self.seed()
        annotation_store.clear(self.config, self.first, "claude", SID, now=START + 60)
        other = lambda: annotation_store.annotate(  # noqa: E731
            self.config, self.second, "claude", "another-session", goal="Kept", now=START + 101
        )

        first, second, overlapped = self.race(lambda: annotation_store.forget(self.config), other)

        self.assertFalse(overlapped)
        self.assertEqual(annotation_store.FORGET_SWEPT, first)
        self.assertEqual(annotation_store.OUTCOME_STORED, second)
        entries = annotation_store._read(self.config)
        self.assertIsNone(annotation_store.find(entries, "claude", SID))
        kept = annotation_store.find(entries, "claude", "another-session")
        assert kept is not None
        self.assertEqual("Kept", kept["revisions"][-1]["goal"])


class ABusyStoreIsReportedNotWrittenTest(_SharedHomeCase):
    """Another process holding the store past the wait: nothing is written, and it says so."""

    def test_a_save_that_cannot_take_the_lock_answers_unwritable_and_writes_nothing(self) -> None:
        said: list[str] = []
        holder = subprocess.Popen(
            [
                sys.executable,
                "-c",
                _HOLD_LOCK,
                str(SKILL_DIR),
                annotation_store.lock_path(self.config),
            ],
            stdout=subprocess.PIPE,
        )
        self.addCleanup(holder.kill)
        assert holder.stdout is not None
        self.assertEqual(b"held\n", holder.stdout.readline())
        with mock.patch.object(annotation_store, "_STORE_LOCK_WAIT_SECONDS", 0.2):
            outcome = annotation_store.annotate(
                self.config,
                self.first,
                "claude",
                SID,
                goal="Typed while another process held the store",
                now=START,
                diagnostic_sink=said.append,
            )

        self.assertEqual(annotation_store.OUTCOME_UNWRITABLE, outcome)
        self.assertFalse(os.path.exists(annotation_store.store_path(self.config)))
        self.assertTrue(any("annotation store" in line for line in said), said)


# Holds the store's lock from a second process until killed. Run on every
# platform the suite runs on, so windows-latest exercises the `msvcrt` branch.
_HOLD_LOCK = textwrap.dedent(
    """
    import sys, time
    sys.path.insert(0, sys.argv[1])
    from cargento_runtime import io as runtime_io
    with runtime_io.held_file_lock(sys.argv[2], wait=5.0) as held:
        print("held" if held else "not held", flush=True)
        time.sleep(60)
    """
)

_SAVER = textwrap.dedent(
    """
    import json, os, sys, time
    from pathlib import Path
    sys.path.insert(0, sys.argv[1])
    from cargento_runtime import annotations as store
    from cargento_runtime.config import build_runtime_config
    from cargento_runtime.state import build_runtime_state
    home, name, count = sys.argv[2], sys.argv[3], int(sys.argv[4])
    config = build_runtime_config(
        environ={**os.environ, "HOME": home, "CARGENTO_HOME": os.path.join(home, "state")},
        platform_name=sys.platform,
        os_name=os.name,
        launcher_path=Path(home) / "server.py",
    )
    state = build_runtime_state(config, started=time.time())
    go = os.path.join(home, "go")
    while not os.path.exists(go):
        time.sleep(0.01)
    outcomes = [
        store.annotate(config, state, "claude", "shared", goal=f"{name} save {k}")
        for k in range(count)
    ]
    print(json.dumps(outcomes))
    """
)


class TwoProcessesOnOneHomeTest(unittest.TestCase):
    """Two real dashboards' worth of processes, saving into one home at once."""

    SAVES = 30

    def test_every_save_from_both_processes_takes_its_own_revision_number(self) -> None:
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        env = {k: v for k, v in os.environ.items() if not k.startswith("CARGENTO_")}
        procs = [
            subprocess.Popen(
                [sys.executable, "-c", _SAVER, str(SKILL_DIR), home, name, str(self.SAVES)],
                stdout=subprocess.PIPE,
                env=env,
            )
            for name in ("one", "two")
        ]
        for proc in procs:
            self.addCleanup(_kill, proc)
        time.sleep(0.3)
        Path(home, "go").touch()
        outcomes = []
        for proc in procs:
            out, _ = proc.communicate(timeout=120)
            self.assertEqual(0, proc.returncode)
            outcomes.extend(json.loads(out))

        self.assertEqual([annotation_store.OUTCOME_STORED] * 2 * self.SAVES, outcomes)
        data = json.loads(Path(home, "state", "cargento-annotations.json").read_text("utf-8"))
        (entry,) = data["entries"]
        numbers = [revision["n"] for revision in entry["revisions"]]
        # Sixty stored saves are sixty revision numbers: the last is 60 and the
        # kept tail is consecutive. A lost update leaves the last number short.
        self.assertEqual(2 * self.SAVES, numbers[-1])
        self.assertEqual(list(range(numbers[0], numbers[-1] + 1)), numbers)


def _kill(proc: subprocess.Popen[bytes]) -> None:
    with contextlib.suppress(OSError):
        proc.kill()
    with contextlib.suppress(subprocess.TimeoutExpired, OSError):
        proc.wait(5)


if __name__ == "__main__":
    unittest.main()
