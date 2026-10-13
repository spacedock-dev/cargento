"""A reader's selected home keeps charges and receipts together across the rename."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import abstention_ledger as authority
import drift_replay
import legacy_paths


class SpendUpgradeTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def charge_in_next_process(self, *, cap: int = 2) -> dict[str, object]:
        script = """
import contextlib, json, sys
from types import SimpleNamespace
from unittest import mock
account = contextlib.nullcontext() if sys.platform == 'win32' else mock.patch('pwd.getpwuid', return_value=SimpleNamespace(pw_dir=sys.argv[1]))
with account:
    import abstention_ledger as authority
    import drift_replay
    import analyze_campaign, claude_route_verification, mark_abstention, levels_cases, redact_session
    from compass_runtime.config import build_runtime_config
    ledger = drift_replay.Ledger(drift_replay.LEDGER_PATH, cap=int(sys.argv[2]))
    before = ledger.used()
    charged = ledger.charge('new-call')
    config = build_runtime_config(environ={'HOME': sys.argv[1]}, platform_name='linux', os_name='posix', launcher_path='server.py')
    print(json.dumps({'path': ledger.path, 'before': before, 'charged': charged,
                      'after': ledger.used(), 'dashboard': config.state_home,
                      'fixed': [authority.LEDGER_PATH, analyze_campaign.LEDGER_PATH,
                                analyze_campaign.REPLAY_PATH, str(claude_route_verification.STATE_PATH),
                                str(claude_route_verification.PRIVATE_DIR), str(claude_route_verification.ACTIVATION_PATH),
                                mark_abstention.STORE_HOME, redact_session.CONFIG],
                      'stores': [mark_abstention.HOME, levels_cases.HOME, drift_replay.HOME]}))
"""
        result = subprocess.run(
            [sys.executable, "-c", script, str(self.root), str(cap)],
            env={
                **os.environ,
                "HOME": str(self.root),
                "USERPROFILE": str(self.root),
                "COMPASS_HOME": str(self.root / "override"),
                "PYTHONPATH": os.pathsep.join(
                    [
                        str(Path(__file__).resolve().parents[1]),
                        str(Path(__file__).resolve().parents[2] / "compass/skills/compass"),
                    ]
                ),
            },
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        return cast("dict[str, object]", json.loads(result.stdout))

    def test_a_reader_charges_in_the_legacy_home_without_hiding_the_dashboard_store(self) -> None:
        old = self.root / ".cargento/drift-replay/spend.json"
        old.parent.mkdir(parents=True)
        old.write_text(json.dumps({"v": 1, "calls": [{"key": "old-call"}]}))
        result = self.charge_in_next_process()
        self.assertEqual(str(old), result["path"])
        self.assertEqual(1, result["before"])
        self.assertEqual(2, result["after"])
        self.assertTrue(result["charged"])
        self.assertEqual(2, len(json.loads(old.read_text())["calls"]))
        self.assertFalse((self.root / ".compass").exists())
        self.assertEqual(str(old.parents[1]), result["dashboard"])
        for path in cast("list[str]", result["fixed"]):
            self.assertTrue(Path(path).resolve().is_relative_to(old.parents[1].resolve()), path)
        self.assertEqual([str(self.root / "override")] * 3, result["stores"])

    def test_a_reader_with_both_homes_charges_only_in_the_new_home(self) -> None:
        old = self.root / ".cargento/drift-replay/spend.json"
        old.parent.mkdir(parents=True)
        old.write_text(json.dumps({"v": 1, "calls": [{"key": "old-call"}]}))
        before = old.read_bytes()
        (self.root / ".compass").mkdir()
        result = self.charge_in_next_process()
        self.assertEqual(str(self.root / ".compass/drift-replay/spend.json"), result["path"])
        self.assertEqual(0, result["before"])
        self.assertEqual(before, old.read_bytes())

    def test_a_reader_with_neither_home_starts_in_the_new_default(self) -> None:
        result = self.charge_in_next_process()
        self.assertEqual(str(self.root / ".compass/drift-replay/spend.json"), result["path"])
        self.assertEqual(0, result["before"])
        self.assertEqual(1, result["after"])
        self.assertFalse((self.root / ".cargento").exists())

    def test_a_reader_at_the_old_spend_cap_cannot_get_a_new_budget_by_renaming(self) -> None:
        old = self.root / ".cargento/drift-replay/spend.json"
        old.parent.mkdir(parents=True)
        old.write_text(json.dumps({"v": 1, "calls": [{"key": str(i)} for i in range(7)]}))
        before = old.read_bytes()
        result = self.charge_in_next_process(cap=7)
        self.assertEqual(7, result["before"])
        self.assertEqual(7, result["after"])
        self.assertFalse(result["charged"])
        self.assertEqual(str(old), result["path"])
        self.assertEqual(before, old.read_bytes())
        self.assertFalse((self.root / ".compass").exists())

    def test_a_reader_who_upgraded_cannot_reset_the_replay_call_cap(self) -> None:
        with (
            mock.patch.dict(os.environ, {"HOME": str(self.root)}, clear=True),
            mock.patch.object(authority, "real_home", return_value=str(self.root)),
        ):
            old = self.root / ".cargento" / "drift-replay" / "spend.json"
            new = Path(os.path.expanduser("~/.compass/drift-replay/spend.json"))
            old.parent.mkdir(parents=True)
            old.write_text(json.dumps({"v": 1, "calls": [{"key": "old-call"}]}))
            selected = authority.canonical_store_path("drift-replay", "spend.json")
            assert selected is not None
            new = Path(selected)
            self.assertEqual(old, new)
            ledger = drift_replay.Ledger(str(new), cap=2)
            self.assertEqual(1, ledger.used())
            self.assertTrue(ledger.charge("new-call"))
            self.assertFalse(ledger.charge("over-cap"))
            self.assertEqual(2, ledger.used())
            restarted = drift_replay.Ledger(str(new), cap=2)
            self.assertEqual(2, restarted.used())
            self.assertFalse(restarted.charge("after-restart"))
            self.assertEqual(
                ["old-call", "new-call"],
                [call["key"] for call in json.loads(new.read_text())["calls"]],
            )
            self.assertFalse((self.root / ".compass").exists())
            self.assertEqual(0, drift_replay.Ledger(str(new.with_name("other.json"))).used())

    def test_a_reader_who_upgraded_keeps_the_account_fixed_qualification_charges(self) -> None:
        old = self.root / ".cargento" / "drc-4666-spend.json"
        new = self.root / ".compass" / old.name
        old.parent.mkdir()
        old.write_text(
            json.dumps(
                {
                    "v": 1,
                    "calls": [
                        {
                            "id": "old",
                            "at": 100.0,
                            "case": "a" * 16,
                            "producer": "claude",
                            "status": "ok",
                            "marks_digest": "b" * 64,
                            "inputs_digest": "c" * 64,
                        }
                    ],
                    "runs": [],
                }
            )
        )
        with (
            mock.patch.dict(os.environ, {"HOME": str(self.root)}, clear=True),
            mock.patch.object(authority, "real_home", return_value=str(self.root)),
            mock.patch.object(authority, "continuation", return_value=None),
        ):
            ledger = authority.Ledger(
                authority.canonical_store_path(old.name),
                cap=2,
                marks_digest="b" * 64,
                inputs_digest="c" * 64,
                producer="claude",
            )
            self.assertEqual(1, ledger.used())
            self.assertEqual("", ledger.check())
            ledger.charge("d" * 16)
            self.assertEqual(2, ledger.used())
            self.assertIn("2 of 2", ledger.check())
            with self.assertRaises(authority.SpendCapError):
                ledger.charge("e" * 16)
        self.assertFalse(new.parent.exists())
        self.assertEqual(2, len(json.loads(old.read_text())["calls"]))
        self.assertFalse(new.parent.exists())

    def test_a_reader_who_relocated_the_store_retains_the_legacy_setting_precedence(self) -> None:
        with mock.patch.dict(os.environ, {"HOME": str(self.root)}, clear=True):
            self.assertEqual(str(self.root / ".compass"), legacy_paths.store_home())
            (self.root / ".cargento").mkdir()
            self.assertEqual(str(self.root / ".cargento"), legacy_paths.store_home())
            os.environ["CARGENTO_HOME"] = "old-home"
            self.assertEqual("old-home", legacy_paths.store_home())
            os.environ["COMPASS_HOME"] = "new-home"
            self.assertEqual("new-home", legacy_paths.store_home())
            os.environ["COMPASS_HOME"] = ""
            self.assertEqual(str(self.root / ".cargento"), legacy_paths.store_home())
            del os.environ["COMPASS_HOME"]
            del os.environ["CARGENTO_HOME"]
            (self.root / ".compass").mkdir()
            self.assertEqual(str(self.root / ".compass"), legacy_paths.store_home())

    def test_a_reader_cannot_replace_an_old_receipt_with_a_symlink_to_widen_access(self) -> None:
        old = self.root / ".cargento" / "ledger.json"
        old.parent.mkdir()
        target = self.root / "private.json"
        target.write_text("{}")
        old.symlink_to(target)
        with self.assertRaises(authority.LedgerError):
            authority._review_json(str(old), "ledger", cap=1024)


class CampaignUpgradeTest(unittest.TestCase):
    def test_a_reader_who_upgraded_keeps_the_one_attempt_route_cap(self) -> None:
        fixtures = importlib.import_module("test_claude_route_verification")
        fixture = fixtures.RouteSidecarGuards()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        new = fixture.root / ".compass"
        old = fixture.root / ".cargento"
        new.rename(old)
        fixture.state = old / fixture.state.name
        fixture.context_dir = old / fixture.context_dir.name
        fixture.context_path = fixture.context_dir / "context.json"
        fixture.ui_file = fixture.context_dir / fixture.ui_file.name
        fixture.context["source_files"][0]["path"] = str(fixture.ui_file)
        fixture.write_private(fixture.context_path, fixture.context)
        fixture.body["context_sha256"] = fixture.route.sha(fixture.context_path.read_bytes())
        fixture.profile.write_text(json.dumps(fixture.body))
        fixture.review["profile_digest"] = fixture.route.profile_binding(fixture.body)
        fixture.handoff.write_text(json.dumps(fixture.review))
        with (
            mock.patch.object(fixture.route, "STATE_PATH", fixture.state),
            mock.patch.object(fixture.route, "PRIVATE_DIR", fixture.context_dir),
            mock.patch.object(
                fixture.route, "ACTIVATION_PATH", old / "claude-route-live00.ACTIVATED.json"
            ),
        ):
            fixture.initialize()
            current = fixture.verifier()
            current.reserve(fixture.request())
            self.assertTrue(fixture.state.is_file())
            self.assertEqual(1, current.budget_view()["route_attempts"])
            with self.assertRaises(fixture.route.RefusalError):
                fixture.verifier().reserve(fixture.request())
        self.assertFalse(new.exists())

    def test_a_reader_who_upgraded_keeps_campaign_charges_and_their_receipt_chain(self) -> None:
        fixtures = importlib.import_module("test_analyze_campaign")
        fixture = fixtures.CampaignReservations()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        old_home = fixture.root / ".cargento"
        old_home.mkdir()
        old = old_home / "analyze-closure-spend.json"
        (old_home / "drift-replay").mkdir()
        fixture.replay.rename(old_home / "drift-replay/spend.json")
        fixture.qualification.rename(old_home / "drc-4666-spend.json")
        # Only the reviewed manifest is synthetic. Account lookup is isolated
        # before import; every ledger and receipt path is resolved by launch code.
        script = """
import contextlib, json, sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
account = contextlib.nullcontext() if sys.platform == 'win32' else mock.patch('pwd.getpwuid', return_value=SimpleNamespace(pw_dir=sys.argv[1]))
with account:
    import analyze_campaign as module
    import test_analyze_campaign as fixtures
    with mock.patch.object(module, 'MANIFEST_PATH', sys.argv[2]):
        manifest = Path(sys.argv[2])
        if sys.argv[3] == 'seed':
            body = json.loads(manifest.read_text())
            body['phase'] = 'prepared'
            body.pop('activation_anchor', None)
            manifest.write_text(json.dumps(body))
            anchor = module.Campaign().initialize()
            body.update(phase='sealed', activation_anchor=anchor)
            manifest.write_text(json.dumps(body))
            campaign = module.Campaign()
            charge = campaign.reserve('replay', campaign.manifest['slots']['replay'][0], 'a'*64)
            campaign.settle(charge, 'usable')
            campaign.accept_batch('replay', 0, fixtures.acceptance(campaign, 'replay', 0))
        else:
            campaign = module.Campaign()
            module._history(campaign.manifest)
            before = len(campaign._state()['calls'])
            campaign.reserve('replay', campaign.manifest['slots']['replay'][1], 'a'*64)
            print(json.dumps({'before': before, 'after': len(campaign._state()['calls']), 'path': campaign.path}))
"""
        environment = {
            **os.environ,
            "HOME": str(fixture.root),
            "USERPROFILE": str(fixture.root),
            "PYTHONPATH": os.pathsep.join(
                (str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parent))
            ),
        }
        environment.pop("COMPASS_HOME", None)
        environment.pop("CARGENTO_HOME", None)
        for phase in ("seed", "upgrade"):
            result = subprocess.run(
                [sys.executable, "-c", script, str(fixture.root), str(fixture.manifest), phase],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
                timeout=20,
            )
            self.assertEqual(0, result.returncode, result.stderr)
        answer = json.loads(result.stdout)
        self.assertEqual(str(old), answer["path"])
        self.assertEqual(1, answer["before"])
        self.assertEqual(2, answer["after"])
        self.assertEqual(2, len(json.loads(old.read_text())["calls"]))
        self.assertFalse((fixture.root / ".compass").exists())
