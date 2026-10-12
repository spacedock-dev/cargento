"""An upgrade keeps the reader's local state with one authority for each selected state file."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from compass_runtime import annotations as annotation_store
from compass_runtime import (
    copied_corrections,
    deliveries,
    departures,
    dismissals,
    ends,
    history,
    lifecycle,
    notifications,
    reach,
    reading_policy,
    supervise,
    tripwires,
)
from compass_runtime.config import build_runtime_config
from compass_runtime.state import build_runtime_state


class UpgradeTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        # Each client in these upgrade cases starts with an open runner; a
        # preceding shutdown proof in the same worker must not stand for it.
        patcher = mock.patch.object(supervise, "_SHUTDOWN", threading.Event())
        patcher.start()
        self.addCleanup(patcher.stop)

    def config(self, **env: str) -> Any:
        return build_runtime_config(
            environ={"HOME": str(self.root), **env},
            platform_name="linux",
            os_name="posix",
            launcher_path=self.root / "server.py",
        )

    def test_a_reader_who_upgraded_keeps_one_store_until_the_new_home_exists(self) -> None:
        old = self.root / ".cargento"
        new = self.root / ".compass"
        self.assertEqual(new, self.config().state_dir)
        old.mkdir()
        self.assertEqual(old, self.config().state_dir)
        new.mkdir()
        self.assertEqual(new, self.config().state_dir)
        self.assertEqual("old-setting", self.config(CARGENTO_HOME="old-setting").state_home)
        self.assertEqual(
            "new-setting",
            self.config(CARGENTO_HOME="old-setting", COMPASS_HOME="new-setting").state_home,
        )
        # A blank new variable is set-but-empty: it chooses the default home,
        # and does not consult an independently configured legacy override.
        self.assertEqual(new, self.config(CARGENTO_HOME="old-setting", COMPASS_HOME="").state_dir)

    def test_a_reader_who_upgraded_is_told_when_the_temporary_fallback_is_in_use(self) -> None:
        home = self.root / ".cargento"
        home.mkdir()
        server = Path(__file__).resolve().parents[1] / "server.py"
        environment = {
            "HOME": str(self.root),
            "USERPROFILE": str(self.root),
            "CARGENTO_QUIET_HOURS": "22:00-08:00",
        }
        result = subprocess.run(
            [sys.executable, str(server), "--diagnose"],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("legacy store " + str(home), result.stdout)
        self.assertIn("CARGENTO_QUIET_HOURS", result.stdout)
        self.assertIn("fallback removed at 1.0.0", result.stdout)
        self.assertEqual([], list(home.iterdir()))
        environment["COMPASS_HOME"] = str(self.root / ".compass")
        environment["COMPASS_QUIET_HOURS"] = "22:00-08:00"
        result = subprocess.run(
            [sys.executable, str(server), "--diagnose"],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn("upgrading", result.stdout)

    def test_a_reader_who_upgraded_keeps_their_saved_intent_and_outcome_line(self) -> None:
        home = self.root / ".cargento"
        home.mkdir()
        config = self.config()
        state = build_runtime_state(config, started=100.0)
        annotation_store.annotate(
            config, state, "pi", "session", goal="Ship it", output="A green PR", now=100.0
        )
        new = home / "compass-annotations.json"
        old = home / "cargento-annotations.json"
        new.rename(old)
        before = old.read_bytes()
        restarted = build_runtime_state(config, started=101.0)
        entry = annotation_store.find(annotation_store.active(config, restarted), "pi", "session")
        assert entry is not None
        self.assertEqual("Ship it", entry["revisions"][-1]["goal"])
        self.assertEqual("A green PR", entry["revisions"][-1]["lines"][0]["text"])
        annotation_store.annotate(
            config, restarted, "pi", "session", goal="Ship the fix", now=102.0
        )
        self.assertFalse(new.exists())
        self.assertTrue(before != old.read_bytes())
        entry = annotation_store.find(
            annotation_store.active(config, build_runtime_state(config, started=103.0)),
            "pi",
            "session",
        )
        assert entry is not None
        self.assertEqual("Ship the fix", entry["revisions"][-1]["goal"])
        self.assertFalse((self.root / ".compass").exists())

    def test_a_reader_who_upgraded_can_find_the_running_dashboard(self) -> None:
        home = self.root / ".cargento"
        home.mkdir()
        old = home / "cargento-48679.json"
        old.write_text(json.dumps({"pid": 12, "port": 48679}), encoding="utf-8")
        before = old.read_bytes()
        config = self.config()
        old_state = lifecycle.read_state(config, 48679)
        assert old_state is not None
        self.assertEqual(12, old_state["pid"])
        lifecycle.write_state(config, 48679, started=100.0)
        new_state = lifecycle.read_state(config, 48679)
        assert new_state is not None
        self.assertNotEqual(12, new_state["pid"])
        self.assertTrue(before != old.read_bytes())
        self.assertFalse((home / "compass-48679.json").exists())
        self.assertIsNone(lifecycle.read_state(config, 48680))

    def test_a_reader_who_upgraded_keeps_saved_permission_and_used_capacity(self) -> None:
        home = self.root / ".cargento"
        home.mkdir()
        config = self.config()
        reading_policy.set_consent(config, True, now=100.0)
        self.assertEqual("", reading_policy.reserve(config, now=100.0)["reason"])
        new = reading_policy.store_path(config)
        old = home / "cargento-reading-permission.sqlite3"
        new.rename(old)
        before = old.read_bytes()
        answer = reading_policy.status(config, now=101.0)
        self.assertTrue(answer["consent"])
        self.assertEqual(1, answer["used"])
        reading_policy.set_consent(config, False, now=102.0)
        self.assertFalse(reading_policy.status(config, now=103.0)["consent"])
        self.assertTrue(before != old.read_bytes())
        self.assertFalse(new.exists())

    def test_a_reader_prefers_current_permission_when_both_databases_exist(self) -> None:
        config = self.config()
        reading_policy.set_consent(config, True, now=100.0)
        reading_policy.reserve(config, now=100.0)
        new = reading_policy.store_path(config)
        old = new.with_name("cargento-reading-permission.sqlite3")
        old.write_bytes(new.read_bytes())
        with sqlite3.connect(old) as db:
            db.execute("UPDATE permission SET allowed=0 WHERE id=1")
            db.execute("INSERT INTO spends VALUES (101.0)")
        answer = reading_policy.status(config, now=102.0)
        self.assertTrue(answer["consent"])
        self.assertEqual(1, answer["used"])
        self.assertEqual(new, reading_policy.store_path(config))

    def test_a_reader_who_upgraded_keeps_every_saved_session_record(self) -> None:
        home = self.root / ".cargento"
        home.mkdir()
        config = self.config()
        entry = {
            "harness": "pi",
            "sid": "one",
            "at": 100.0,
            "seen_activity": 100.0,
            "lane": "popup",
            "outcome": deliveries.OUTCOME_HANDED_OVER,
            "project": "project",
            "state": "working",
            "last_activity": 100.0,
        }
        for module in (ends, dismissals, deliveries, departures, history):
            with self.subTest(surface=module.__name__):
                new = Path(module.store_path(config))
                old = new.with_name(new.name.replace("compass", "cargento", 1))
                old.write_text(json.dumps({"v": module.SCHEMA_VERSION, "entries": [entry]}))
                loaded = module.load(config)
                held = loaded[0] if module is history else loaded
                self.assertEqual("one", held[0]["sid"])
                self.assertTrue(module.save(config, ()))
                loaded = module.load(config)
                self.assertEqual((), loaded[0] if module is history else loaded)
                self.assertFalse(old.exists())
                self.assertFalse(new.exists())
                loaded = module.load(config)
                self.assertEqual((), loaded[0] if module is history else loaded)
        rule: dict[str, Any] = {
            "id": "a" * 64,
            "workflow": "demo",
            "stage": "build",
            "revision": "a" * 32,
            "state": "armed",
            "saved_at": 100.0,
            "trip": None,
        }
        old = home / "cargento-tripwires.json"
        old.write_text(json.dumps({"v": 1, "rules": [rule]}))
        self.assertEqual({rule["id"]: rule}, tripwires.load(config))
        self.assertTrue(tripwires.save(config, {}))
        self.assertEqual({}, tripwires.load(config))
        self.assertFalse(old.exists())
        old = home / "cargento-copied-corrections.json"
        old.write_text(
            json.dumps(
                {
                    "v": 1,
                    "entries": [
                        {
                            "harness": "pi",
                            "sid": "one",
                            "copies": [
                                {"digest": "a" * 64, "copied_at": 100.0, "ino": 1, "offset": 0}
                            ],
                            "matches": [],
                        }
                    ],
                }
            )
        )
        self.assertIn(("pi", "one"), copied_corrections.load(config))
        self.assertTrue(copied_corrections.forget(config))
        self.assertEqual({}, copied_corrections.load(config))
        self.assertFalse(old.exists())

    def test_a_reader_who_forgets_history_does_not_see_old_records_return(self) -> None:
        home = self.root / ".cargento"
        home.mkdir()
        config = self.config()
        entry = {
            "harness": "pi",
            "sid": "forgotten",
            "at": 100.0,
            "project": "private goal",
            "state": "working",
            "last_activity": 100.0,
        }
        for module in (history, ends):
            for both in (False, True):
                with self.subTest(surface=module.__name__, both=both):
                    new = home / Path(module.store_path(config)).name.replace(
                        "cargento", "compass", 1
                    )
                    old = new.with_name(new.name.replace("compass", "cargento", 1))
                    payload = json.dumps({"v": module.SCHEMA_VERSION, "entries": [entry]})
                    old.write_text(payload)
                    if both:
                        new.write_text(payload)
                    loaded = module.load(config)
                    self.assertEqual(
                        "forgotten", (loaded[0] if module is history else loaded)[0]["sid"]
                    )
                    self.assertTrue(module.forget(config))
                    loaded = module.load(config)
                    self.assertEqual((), loaded[0] if module is history else loaded)
                    self.assertFalse(old.exists())
                    self.assertFalse(new.exists())

    def test_a_reader_who_clears_a_goal_leaves_no_quote_in_either_departure_file(self) -> None:
        home = self.root / ".cargento"
        home.mkdir()
        config = self.config()
        quoted = {
            "harness": "claude",
            "sid": "s1",
            "at": 100.0,
            "constraint": "never push to main",
            "clause": "your own sentence",
            "reading": "a model paragraph about that sentence",
            "evidence": "the check that failed",
            "revision": 3,
            "cutoff": 99.0,
            "cutoff_text": "what the reading read",
        }
        other = {**quoted, "sid": "s2", "clause": "another session's sentence"}
        new = home / "compass-departures.json"
        old = home / "cargento-departures.json"
        payload = json.dumps({"v": departures.SCHEMA_VERSION, "entries": [quoted, other]})
        new.write_text(payload)
        old.write_text(payload)
        self.assertTrue(departures.withdraw(config, "claude", "s1"))
        for path in (new, old):
            with self.subTest(file=path.name):
                rows = {row["sid"]: row for row in departures._load_at(config, str(path))}
                self.assertEqual(
                    ("", "", "", ""),
                    tuple(rows["s1"][k] for k in ("clause", "reading", "evidence", "cutoff_text")),
                )
                self.assertTrue(rows["s1"]["withdrawn"])
                # The spend the checks made still counts, and another session is untouched.
                self.assertEqual(
                    (100.0, 3, 99.0),
                    (rows["s1"]["at"], rows["s1"]["revision"], rows["s1"]["cutoff"]),
                )
                self.assertEqual("another session's sentence", rows["s2"]["clause"])
        # Removing the selected file must not bring the words back through the fallback.
        new.unlink()
        self.assertEqual("", departures.load(config)[0]["clause"])

    def test_a_reader_who_forgets_annotations_leaves_no_discard_record_in_the_other_file(
        self,
    ) -> None:
        home = self.root / ".cargento"
        home.mkdir()
        config = self.config()
        record = {
            "harness": "claude",
            "sid": "s1",
            "revisions": [],
            "discarded": 123.0,
            "discarded_revision": 1,
        }
        words = {"harness": "claude", "sid": "s2", "revisions": [{"n": 1, "goal": "Ship it"}]}
        new = home / "compass-annotations.json"
        old = home / "cargento-annotations.json"
        new.write_text(json.dumps({"v": annotation_store.SCHEMA_VERSION, "entries": []}))
        old.write_text(
            json.dumps({"v": annotation_store.SCHEMA_VERSION, "entries": [record, words]})
        )
        self.assertEqual(annotation_store.FORGET_SWEPT, annotation_store.forget(config))
        remaining = json.loads(old.read_text())["entries"]
        self.assertEqual(
            ["s2"], [entry["sid"] for entry in remaining], "words stay, the record goes"
        )
        self.assertEqual(annotation_store.FORGET_NOTHING, annotation_store.forget(config))

    def test_a_reader_revoking_in_an_older_build_withdraws_compass_permission(self) -> None:
        config = self.config()
        reading_policy.set_consent(config, True, now=100.0)
        new = reading_policy.store_path(config)
        old = new.with_name("cargento-reading-permission.sqlite3")
        new.rename(old)
        self.assertTrue(reading_policy.status(config, now=101.0)["consent"])
        with sqlite3.connect(old) as db:
            db.execute("UPDATE permission SET allowed=0 WHERE id=1")
        self.assertFalse(reading_policy.status(config, now=102.0)["consent"])
        self.assertFalse(new.exists())

    def test_a_reader_using_two_builds_cannot_spend_more_than_twelve_attempts(self) -> None:
        config = self.config()
        reading_policy.set_consent(config, True, now=100.0)
        for n in range(7):
            self.assertEqual("", reading_policy.reserve(config, now=100.0 + n)["reason"])
        new = reading_policy.store_path(config)
        old = new.with_name("cargento-reading-permission.sqlite3")
        new.rename(old)
        self.assertEqual(7, reading_policy.status(config, now=110.0)["used"])

        # An older build opens its own filename without this build's selector.
        # Use its SQLite transaction and the same rolling cap, not a patched
        # Compass selector that would also change when that selector is mutated.
        def older_reserve(now: float) -> bool:
            with sqlite3.connect(old, isolation_level=None) as db:
                db.execute("BEGIN IMMEDIATE")
                used = db.execute(
                    "SELECT count(*) FROM spends WHERE at > ?", (now - reading_policy.DAY_SEC,)
                ).fetchone()[0]
                admitted = int(used) < reading_policy.DAILY_CAP
                if admitted:
                    db.execute("INSERT INTO spends VALUES (?)", (now,))
                db.execute("COMMIT")
                return admitted

        admitted = 0
        for n in range(10):
            if n % 2:
                admitted += older_reserve(111.0 + n)
            else:
                admitted += reading_policy.reserve(config, now=111.0 + n)["reason"] == ""
        self.assertEqual(5, admitted)
        self.assertEqual(12, reading_policy.status(config, now=125.0)["used"])
        self.assertEqual("daily-cap", reading_policy.reserve(config, now=126.0)["reason"])
        with sqlite3.connect(old) as db:
            self.assertEqual(12, db.execute("SELECT count(*) FROM spends").fetchone()[0])
        self.assertFalse(older_reserve(127.0))
        self.assertFalse(new.exists())

    def test_a_reader_with_legacy_files_in_the_new_home_gets_an_upgrade_notice(self) -> None:
        home = self.root / ".compass"
        home.mkdir()
        (home / "cargento-48679.json").write_text('{"pid": 12, "port": 48679}')
        server = Path(__file__).resolve().parents[1] / "server.py"
        result = subprocess.run(
            [sys.executable, str(server), "--diagnose"],
            env={"HOME": str(self.root), "USERPROFILE": str(self.root)},
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("legacy state file " + str(home / "cargento-48679.json"), result.stdout)
        self.assertIn("used in place", result.stdout)
        self.assertIn("fallback removed at 1.0.0", result.stdout)

    def test_a_reader_uses_legacy_settings_only_when_the_new_name_is_unset(self) -> None:
        config = self.config()
        with mock.patch.dict(
            os.environ,
            {
                "CARGENTO_REACH_URL": "https://example.test/hook",
                "CARGENTO_QUIET_HOURS": "22:00-08:00",
            },
            clear=True,
        ):
            self.assertEqual("https://example.test/hook", reach.resolve_reach_url(config))
            self.assertEqual((22, 0, 8, 0), notifications.resolve_quiet_hours(config))
            os.environ["COMPASS_REACH_URL"] = "file:///private"
            os.environ["COMPASS_QUIET_HOURS"] = "invalid"
            self.assertIsNone(reach.resolve_reach_url(config))
            self.assertIsNone(notifications.resolve_quiet_hours(config))
            del os.environ["COMPASS_REACH_URL"]
            del os.environ["COMPASS_QUIET_HOURS"]
            os.environ["CARGENTO_REACH_URL"] = "file:///private"
            os.environ["CARGENTO_QUIET_HOURS"] = "invalid"
            self.assertIsNone(reach.resolve_reach_url(config))
            self.assertIsNone(notifications.resolve_quiet_hours(config))

    def test_a_reader_prefers_current_records_when_both_filenames_exist(self) -> None:
        home = self.root / ".compass"
        home.mkdir()
        config = self.config()
        entry = {
            "harness": "pi",
            "sid": "old",
            "at": 100.0,
            "seen_activity": 100.0,
            "lane": "popup",
            "outcome": deliveries.OUTCOME_HANDED_OVER,
            "project": "project",
            "state": "working",
            "last_activity": 100.0,
        }
        for module in (ends, dismissals, deliveries, departures, history):
            with self.subTest(surface=module.__name__):
                new = home / Path(module.store_path(config)).name
                old = new.with_name(new.name.replace("compass", "cargento", 1))
                old.write_text(json.dumps({"v": module.SCHEMA_VERSION, "entries": [entry]}))
                loaded = module.load(config)
                self.assertEqual("old", (loaded[0] if module is history else loaded)[0]["sid"])
                new.write_text(
                    json.dumps({"v": module.SCHEMA_VERSION, "entries": [{**entry, "sid": "new"}]})
                )
                loaded = module.load(config)
                self.assertEqual("new", (loaded[0] if module is history else loaded)[0]["sid"])
                self.assertTrue(module.save(config, ()))
                self.assertFalse(old.exists())
                new.unlink()

    def test_a_reader_forgetting_copied_corrections_removes_both_records(self) -> None:
        home = self.root / ".compass"
        home.mkdir()
        config = self.config()
        new = home / "compass-copied-corrections.json"
        old = home / "cargento-copied-corrections.json"
        payload: dict[str, Any] = {
            "v": 1,
            "entries": [
                {
                    "harness": "pi",
                    "sid": "old",
                    "copies": [{"digest": "a" * 64, "copied_at": 100.0, "ino": 1, "offset": 0}],
                    "matches": [],
                }
            ],
        }
        old.write_text(json.dumps(payload))
        self.assertIn(("pi", "old"), copied_corrections.load(config))
        payload["entries"][0]["sid"] = "new"
        new.write_text(json.dumps(payload))
        self.assertEqual({("pi", "new")}, set(copied_corrections.load(config)))
        self.assertTrue(copied_corrections.forget(config))
        self.assertEqual({}, copied_corrections.load(config))
        self.assertFalse(old.exists())
        self.assertFalse(new.exists())

    def test_a_reader_prefers_the_new_tripwire_and_can_clear_both_copies(self) -> None:
        home = self.root / ".compass"
        home.mkdir()
        config = self.config()
        old = home / "cargento-tripwires.json"
        new = home / "compass-tripwires.json"
        rule: dict[str, Any] = {
            "id": "a" * 64,
            "workflow": "demo",
            "stage": "build",
            "revision": "a" * 32,
            "state": "armed",
            "saved_at": 100.0,
            "trip": None,
        }
        old.write_text(json.dumps({"v": 1, "rules": [rule]}))
        self.assertEqual({rule["id"]: rule}, tripwires.load(config))
        new.write_text(json.dumps({"v": 1, "rules": [{**rule, "stage": "review"}]}))
        loaded = tripwires.load(config)
        assert loaded is not None
        self.assertEqual("review", loaded[rule["id"]]["stage"])
        self.assertTrue(tripwires.save(config, {}))
        self.assertFalse(old.exists())
        self.assertEqual({}, tripwires.load(config))

    def test_a_reader_stopping_a_dashboard_removes_both_state_records(self) -> None:
        home = self.root / ".compass"
        home.mkdir()
        config = self.config()
        old = home / "cargento-48679.json"
        new = home / "compass-48679.json"
        old.write_text('{"pid": 12}')
        recorded = lifecycle.read_state(config, 48679)
        assert recorded is not None
        self.assertEqual(12, recorded["pid"])
        new.write_text('{"pid": 13}')
        recorded = lifecycle.read_state(config, 48679)
        assert recorded is not None
        self.assertEqual(13, recorded["pid"])
        lifecycle.remove_state(config, 48679)
        self.assertIsNone(lifecycle.read_state(config, 48679))
        self.assertFalse(old.exists())
        self.assertFalse(new.exists())

    def test_a_reader_clearing_intent_removes_words_from_the_legacy_store(self) -> None:
        for both in (False, True):
            with self.subTest(both=both):
                home = self.root / ("both" if both else "old")
                config = self.config(COMPASS_HOME=str(home))
                state = build_runtime_state(config, started=100.0)
                annotation_store.annotate(
                    config, state, "pi", "one", goal="private goal", now=100.0
                )
                new = home / "compass-annotations.json"
                old = home / "cargento-annotations.json"
                new.rename(old)
                if both:
                    new.write_bytes(old.read_bytes())
                state = build_runtime_state(config, started=101.0)
                self.assertEqual(
                    annotation_store.OUTCOME_STORED,
                    annotation_store.clear(config, state, "pi", "one", now=102.0),
                )
                self.assertNotIn("private goal", old.read_text() if old.exists() else "")
                annotation_store.forget(config)
                self.assertEqual((), annotation_store.load(config))

    def test_a_reader_keeps_notification_hours_until_the_new_home_exists(self) -> None:
        old_home = self.root / ".cargento"
        new_home = self.root / ".compass"
        old_home.mkdir()
        old = old_home / "quiet_hours"
        old.write_text("22:00-08:00")
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual((22, 0, 8, 0), notifications.resolve_quiet_hours(self.config()))
            new_home.mkdir()
            (new_home / "quiet_hours").write_text("21:00-07:00")
            self.assertEqual((21, 0, 7, 0), notifications.resolve_quiet_hours(self.config()))
        self.assertEqual("22:00-08:00", old.read_text())

    def test_a_reader_uses_legacy_notification_hours_only_without_current_settings(self) -> None:
        config = self.config()
        with mock.patch.dict(os.environ, {"CARGENTO_QUIET_HOURS": "22:00-08:00"}, clear=True):
            self.assertEqual((22, 0, 8, 0), notifications.resolve_quiet_hours(config))
            os.environ["COMPASS_QUIET_HOURS"] = "21:00-07:00"
            self.assertEqual((21, 0, 7, 0), notifications.resolve_quiet_hours(config))


class StandaloneUpgradeTest(unittest.TestCase):
    def test_a_reader_who_upgraded_keeps_hooks_mcp_and_statusline_on_the_same_store(self) -> None:
        root = Path(__file__).resolve().parents[4]
        paths = [
            root / "compass/skills/compass" / name
            for name in ("event_hook.py", "agy_hook.py", "mcp_server.py", "statusline_hook.py")
        ]
        paths += [
            root / name / "hooks/event_hook.py" for name in ("compass-gemini", "compass-droid")
        ]
        for index, path in enumerate(paths):
            with self.subTest(hook=path), tempfile.TemporaryDirectory() as temp:
                spec = importlib.util.spec_from_file_location(f"upgrade_hook_{index}", path)
                assert spec and spec.loader
                module = importlib.util.module_from_spec(spec)
                with mock.patch.dict(sys.modules, {spec.name: module}):
                    spec.loader.exec_module(module)
                home = Path(temp)
                old_home = home / ".cargento"
                new_home = home / ".compass"
                with mock.patch.dict(os.environ, {"HOME": temp, "USERPROFILE": temp}, clear=True):
                    self.assertEqual(str(new_home), module.state_home())
                    old_home.mkdir()
                    self.assertEqual(str(old_home), module.state_home())
                    os.environ["CARGENTO_HOME"] = "old-setting"
                    os.environ["COMPASS_HOME"] = ""
                    self.assertEqual(str(old_home), module.state_home())
                    del os.environ["COMPASS_HOME"]
                    del os.environ["CARGENTO_HOME"]
                    new = old_home / "compass-48679.json"
                    old = old_home / "cargento-48679.json"
                    old.write_text(
                        json.dumps(
                            {
                                "port": 48679,
                                "capabilities": dict.fromkeys(
                                    ("claude", "codex", "gemini", "droid", "antigravity"), "a" * 64
                                ),
                            }
                        )
                    )
                    before = old.read_bytes()
                    if hasattr(module, "state_file"):
                        self.assertEqual(str(old), module.state_file(48679))
                        self.assertEqual("a" * 64, module.capability(48679, "claude"))
                    elif hasattr(module, "capability"):
                        self.assertEqual("a" * 64, module.capability(48679))
                    else:
                        self.assertEqual([48679], module._published_ports())
                    new.write_text(
                        json.dumps(
                            {
                                "port": 48680,
                                "capabilities": dict.fromkeys(("claude", "antigravity"), "b" * 64),
                            }
                        )
                    )
                    if hasattr(module, "state_file"):
                        self.assertEqual("b" * 64, module.capability(48679, "claude"))
                    elif hasattr(module, "capability"):
                        self.assertEqual("b" * 64, module.capability(48679))
                    else:
                        self.assertEqual([48680], module._published_ports())
                    self.assertEqual(before, old.read_bytes())
                    new_home.mkdir()
                    self.assertEqual(str(new_home), module.state_home())
                    os.environ["CARGENTO_HOME"] = "old-setting"
                    self.assertEqual("old-setting", module.state_home())
                    os.environ["COMPASS_HOME"] = "new-setting"
                    self.assertEqual("new-setting", module.state_home())


class EveryHomeSelectorTest(unittest.TestCase):
    def test_a_reader_gets_the_same_home_from_every_standalone_client(self) -> None:
        root = Path(__file__).resolve().parents[4]
        paths = [
            root / "compass/skills/compass" / name
            for name in ("event_hook.py", "agy_hook.py", "statusline_hook.py", "mcp_server.py")
        ]
        paths += [
            root / name / "hooks/event_hook.py" for name in ("compass-gemini", "compass-droid")
        ]
        paths += [root / "scripts/legacy_paths.py"]
        modules = []
        for index, path in enumerate(paths):
            spec = importlib.util.spec_from_file_location(f"selector_{index}", path)
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            with mock.patch.dict(sys.modules, {spec.name: module}):
                spec.loader.exec_module(module)
            modules.append((path.name + str(index), module))
        cases: tuple[tuple[str, bool, bool, dict[str, str], str], ...] = (
            ("neither", False, False, {}, ".compass"),
            ("legacy only", True, False, {}, ".cargento"),
            ("new only", False, True, {}, ".compass"),
            ("both", True, True, {}, ".compass"),
            ("new empty", True, True, {}, ".compass"),
            (
                "both overrides",
                True,
                False,
                {"COMPASS_HOME": "new-setting", "CARGENTO_HOME": "old-setting"},
                "new-setting",
            ),
            ("legacy override", True, False, {"CARGENTO_HOME": "old-setting"}, "old-setting"),
            (
                "blank new",
                True,
                False,
                {"COMPASS_HOME": "", "CARGENTO_HOME": "old-setting"},
                ".cargento",
            ),
            ("blank legacy", True, False, {"CARGENTO_HOME": ""}, ".cargento"),
        )
        for label, legacy, current, overrides, selected in cases:
            with self.subTest(state=label), tempfile.TemporaryDirectory() as temp:
                home = Path(temp)
                if legacy:
                    (home / ".cargento").mkdir()
                    (home / ".cargento" / "records.json").write_text("{}")
                if current:
                    (home / ".compass").mkdir()
                    if label != "new empty":
                        (home / ".compass" / "records.json").write_text("{}")
                env = {"HOME": temp, "USERPROFILE": temp, **overrides}
                expected = str(home / selected) if selected.startswith(".") else selected
                config = build_runtime_config(
                    environ=env,
                    platform_name="linux",
                    os_name="posix",
                    launcher_path=home / "server.py",
                )
                self.assertEqual(expected, config.state_home)
                with mock.patch.dict(os.environ, env, clear=True):
                    for name, module in modules:
                        with self.subTest(client=name):
                            select = getattr(module, "state_home", None) or module.store_home
                            self.assertEqual(config.state_home, select())
                for name in ("opencode_plugin.js", "pi_extension.js"):
                    with self.subTest(client=name):
                        source = (root / "compass/skills/compass" / name).read_text()
                        script = r"const m=await import('data:text/javascript;base64,'+Buffer.from(process.argv[1]+'\nexport {state_home};').toString('base64')); console.log(m.state_home());"
                        result = subprocess.run(
                            [
                                shutil.which("node") or "node",
                                "--input-type=module",
                                "-e",
                                script,
                                source,
                            ],
                            env=env,
                            capture_output=True,
                            text=True,
                            check=False,
                            timeout=10,
                        )
                        self.assertEqual(0, result.returncode, result.stderr)
                        self.assertEqual(config.state_home, result.stdout.strip())
