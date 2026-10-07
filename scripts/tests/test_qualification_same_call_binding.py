"""Same-call derivation avoids duplicate validation, never later admission reads."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import abstention_ledger as ledger
import analyze_campaign as campaigns

if TYPE_CHECKING:
    from tests import test_qualification_conditional_priority as fixtures
else:
    import test_qualification_conditional_priority as fixtures


class SameCallAncestorBindings(unittest.TestCase):
    fixture_class: ClassVar[type[fixtures.QualificationConditionalPriority]] = (
        fixtures.QualificationConditionalPriority
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture_class.setUpClass()
        cls.addClassCleanup(cls.fixture_class.doClassCleanups)

    def setUp(self) -> None:
        self.fixture = self.fixture_class()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.current = self.fixture.activate()

    def test_pure_bindings_equal_fresh_public_helpers_without_validation_reentry(self) -> None:
        isolation = self.current.parent
        clause = isolation.parent
        login = clause.parent
        successor = login.parent
        for previous, public_name, pure_name, prefix in (
            (successor, "login_resume_parent_binding", "_login_resume_parent_binding", 32),
            (
                login,
                "clause_continuation_parent_binding",
                "_clause_continuation_parent_binding",
                34,
            ),
            (clause, "clause_isolation_parent_binding", "_clause_isolation_parent_binding", 36),
        ):
            with self.subTest(helper=public_name):
                expected = getattr(campaigns, public_name)(previous)
                state = previous._state()
                root = previous._parent_state()
                native = ledger.read(campaigns.QUALIFICATION_PATH)["calls"][:prefix]
                before = copy.deepcopy((state, root, native))
                self.assertTrue(hasattr(campaigns, pure_name), "pure same-call derivation missing")
                with (
                    mock.patch.object(
                        previous, "_state", side_effect=AssertionError("revalidated")
                    ),
                    mock.patch.object(
                        previous, "_parent_state", side_effect=AssertionError("revalidated")
                    ),
                ):
                    actual = getattr(campaigns, pure_name)(previous, state, root, native)
                self.assertEqual(expected, actual)
                self.assertEqual(before, (state, root, native))
                self.assertEqual(prefix, actual["native_calls"])
                if public_name == "clause_continuation_parent_binding":
                    self.assertEqual(
                        ledger.digest(previous.parent._state()), actual["first_epoch_digest"]
                    )
                elif public_name == "clause_isolation_parent_binding":
                    self.assertEqual(
                        ledger.digest(previous.parent.parent._state()), actual["first_epoch_digest"]
                    )
                    self.assertEqual(
                        ledger.digest(previous.parent._state()), actual["second_epoch_digest"]
                    )

    def test_one_admission_never_reenters_public_binding_validators(self) -> None:
        with (
            mock.patch.object(
                campaigns,
                "login_resume_parent_binding",
                side_effect=AssertionError("duplicate login validation"),
            ),
            mock.patch.object(
                campaigns,
                "clause_continuation_parent_binding",
                side_effect=AssertionError("duplicate clause validation"),
            ),
            mock.patch.object(
                campaigns,
                "clause_isolation_parent_binding",
                side_effect=AssertionError("duplicate isolation validation"),
            ),
        ):
            state = self.current._state()
        self.assertEqual([], state["calls"])

    def test_one_admission_bounds_duplicate_reads_while_still_reading_evidence(self) -> None:
        with mock.patch.object(ledger, "_review_json", wraps=ledger._review_json) as reads:
            self.current._parent_state()
        # This fixture previously needed5671 JSON opens for one admission.
        # Count work, not elapsed time; Windows filesystem latency varies.
        self.assertGreater(reads.call_count, 100)
        self.assertLess(reads.call_count, 1500)

    def test_later_admission_refuses_changed_or_deleted_ancestor_evidence(self) -> None:
        login = self.current.parent.parent.parent
        login_call = login._state()["calls"][-1]["id"]
        paths = (
            self.fixture.native_fixture.grant_paths[5],
            self.current.parent.parent.epoch_dir / "TRANSITION.json",
            self.current.parent.parent.epoch_dir / "RESEAL.json",
            login.receipts / (login_call + "-SETTLED.json"),
            self.current.parent.receipts / "qualification-0-BATCH.json",
        )
        for path in paths:
            raw = path.read_bytes()
            for action in ("changed", "deleted"):
                with self.subTest(path=path.name, action=action):
                    self.current._state()
                    if action == "changed":
                        path.write_bytes(b"{}")
                    else:
                        path.unlink()
                    try:
                        with self.assertRaises(ledger.LedgerError):
                            self.current._state()
                    finally:
                        path.write_bytes(raw)
                    self.current._state()


if __name__ == "__main__":
    unittest.main()
