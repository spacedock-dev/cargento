"""Marker provenance is private, validated and covered by the committed digest."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import TYPE_CHECKING

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import drift_replay as dr

if TYPE_CHECKING:
    from tests.test_drift_replay import _Home, _Session
else:
    from test_drift_replay import _Home, _Session


class ClaimMarkerProvenance(unittest.TestCase):
    def test_import_keeps_old_mark_and_blind_answers_in_the_digest(self) -> None:
        with _Session() as s:
            home = _Home(s)
            key = home.ids[0]
            Path(home.paths["claim_items"]).write_text(json.dumps({"items": [{"id": key}]}))
            old = {"true": "yes", "visible": "yes", "reason": "Launch only"}
            Path(home.paths["claim_marks"]).write_text(json.dumps({"marks": {key: old}}))
            new = {
                "true": "yes",
                "visible": "no",
                "reason": "No liveness proof",
                "provenance": {
                    "resolution": "agreed",
                    "markers": [
                        {"marker": "agent-blind-A", "true": "yes", "visible": "no"},
                        {"marker": "agent-blind-B", "true": "yes", "visible": "no"},
                    ],
                },
            }
            incoming = s.home / "incoming.json"
            incoming.write_text(json.dumps({"marks": {key: new}}))
            self.assertEqual(
                0, dr.import_claim_marks(home=str(s.home), path=str(incoming), say=lambda _m: None)
            )
            saved = json.loads(Path(home.paths["claim_marks"]).read_text())["marks"][key]
            self.assertEqual(old, saved["previous"])
            self.assertEqual(new["provenance"], saved["provenance"])
            digest = json.loads(s.claim_digest.read_text())
            self.assertEqual(1, digest["agreement"]["agreed"])
            self.assertEqual("agents", digest["markers"])

    def test_unknown_item_and_unlabelled_answers_refuse_before_writing(self) -> None:
        with _Session() as s:
            home = _Home(s)
            key = home.ids[0]
            Path(home.paths["claim_items"]).write_text(json.dumps({"items": [{"id": key}]}))
            for supplied_key, provenance in (
                ("unknown", {"resolution": "agreed", "markers": []}),
                (key, {"resolution": "agreed", "markers": [{"true": "yes", "visible": "no"}]}),
            ):
                incoming = s.home / "incoming.json"
                incoming.write_text(
                    json.dumps(
                        {
                            "marks": {
                                supplied_key: {
                                    "true": "yes",
                                    "visible": "no",
                                    "reason": "No proof",
                                    "provenance": provenance,
                                }
                            }
                        }
                    )
                )
                self.assertEqual(
                    1,
                    dr.import_claim_marks(
                        home=str(s.home), path=str(incoming), say=lambda _m: None
                    ),
                )
                self.assertFalse(Path(home.paths["claim_marks"]).exists())
