"""The event envelope: what is accepted, what it means, and what it may patch."""

from __future__ import annotations

import unittest
from typing import Any

from cargento_runtime import events

from . import support

NOW = 1_700_000_000.0
# A UUID whose first eight characters are the prefix the Claude collector keys on.
SESSION = "abcdef12-3456-7890-abcd-ef1234567890"
PREFIX = "abcdef12"


def envelope(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"v": 1, "event": "turn_started", "session_id": SESSION}
    payload.update(overrides)
    return payload


class ParseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = support.make_config()

    def parse(self, payload: dict[str, Any], *, harness: str = "claude", seq: int = 1) -> Any:
        return events.parse(harness, payload, arrival_seq=seq, config=self.config, now=NOW)

    def test_a_valid_envelope_becomes_an_event_keyed_on_the_collector_prefix(self) -> None:
        result = self.parse(envelope())
        assert isinstance(result, events.Event)
        self.assertEqual(PREFIX, result.sid)
        self.assertEqual(SESSION, result.session_id)
        self.assertEqual("turn_started", result.event)
        self.assertEqual("claude", result.harness)

    def test_an_unsupported_version_reports_incompatible_rather_than_being_ignored(self) -> None:
        # The whole point of the distinction: an adapter too old for this server
        # is something the user can fix, and the unknown-name rule would hide it.
        result = self.parse(envelope(v=99))
        self.assertEqual(events.Rejected(events.REJECT_INCOMPATIBLE), result)

    def test_a_missing_version_is_incompatible(self) -> None:
        payload = envelope()
        del payload["v"]
        self.assertEqual(events.Rejected(events.REJECT_INCOMPATIBLE), self.parse(payload))

    def test_a_boolean_version_is_not_read_as_one(self) -> None:
        # bool is a subclass of int in Python, so `True` would pass a bare
        # isinstance check and then compare equal to version 1.
        self.assertEqual(events.Rejected(events.REJECT_INCOMPATIBLE), self.parse(envelope(v=True)))

    def test_an_unknown_event_name_is_rejected_not_accepted_into_state(self) -> None:
        result = self.parse(envelope(event="rm_minus_rf"))
        self.assertEqual(events.Rejected(events.REJECT_UNKNOWN_EVENT), result)

    def test_the_version_is_checked_before_the_vocabulary(self) -> None:
        # An adapter from the future may use a name this build has never heard
        # of; reporting that as an unknown name would send the user hunting for a
        # typo instead of an upgrade.
        result = self.parse(envelope(v=99, event="not_a_known_name"))
        self.assertEqual(events.Rejected(events.REJECT_INCOMPATIBLE), result)

    def test_a_harness_without_a_registered_normalizer_is_refused(self) -> None:
        # The identity mapping has to be established per harness before its
        # adapter ships. A passthrough default would quietly skip that step.
        result = self.parse(envelope(), harness="goose")
        self.assertEqual(events.Rejected(events.REJECT_UNKNOWN_HARNESS), result)

    def test_a_session_id_too_short_to_map_is_refused(self) -> None:
        # Seven characters would match every row sharing the prefix, which is a
        # guess rather than a lookup.
        result = self.parse(envelope(session_id="abcdef1"))
        self.assertEqual(events.Rejected(events.REJECT_UNMAPPABLE), result)

    def test_a_session_id_that_is_not_uuid_shaped_is_refused(self) -> None:
        result = self.parse(envelope(session_id="../../etc/passwd"))
        self.assertEqual(events.Rejected(events.REJECT_UNMAPPABLE), result)

    def test_a_missing_session_id_is_malformed(self) -> None:
        payload = envelope()
        del payload["session_id"]
        self.assertEqual(events.Rejected(events.REJECT_MALFORMED), self.parse(payload))

    def test_an_oversized_session_id_is_malformed(self) -> None:
        result = self.parse(envelope(session_id="a" * (events.MAX_ID_LEN + 1)))
        self.assertEqual(events.Rejected(events.REJECT_MALFORMED), result)

    def test_unrelated_native_fields_are_discarded_rather_than_rejected(self) -> None:
        # A harness adding a field must not take out its own adapter, and the
        # prompt text it added must not survive into anything Cargento holds.
        result = self.parse(envelope(prompt="my secret prompt", tool_input={"cmd": "ls"}))
        assert isinstance(result, events.Event)
        self.assertNotIn("prompt", vars(result))
        self.assertNotIn("my secret prompt", repr(result))

    def test_the_allowlist_matches_the_fields_the_event_actually_carries(self) -> None:
        # Both sides of the envelope contract in one assertion, so adding a field
        # to one without the other fails here rather than silently.
        carried = {
            "event",
            "session_id",
            "timestamp",
            "source_instance_id",
            "source_sequence",
            "cwd",
            "subagent_id",
            "transcript_path",
        }
        self.assertEqual(events.ALLOWED_FIELDS, carried | {"v"})

    def test_optional_hints_are_carried_through(self) -> None:
        result = self.parse(
            envelope(
                cwd="/w/proj",
                subagent_id="child-1",
                transcript_path="/store/projects/-w-proj/abcdef12.jsonl",
                source_instance_id="inst-1",
                source_sequence=7,
            )
        )
        assert isinstance(result, events.Event)
        self.assertEqual("/w/proj", result.cwd)
        self.assertEqual("child-1", result.subagent_id)
        self.assertEqual(7, result.source_sequence)
        self.assertEqual("inst-1", result.source_instance_id)

    def test_a_wrongly_typed_hint_is_dropped_and_the_event_still_parses(self) -> None:
        result = self.parse(envelope(cwd=12345, subagent_id=["a"]))
        assert isinstance(result, events.Event)
        self.assertIsNone(result.cwd)
        self.assertIsNone(result.subagent_id)

    def test_a_negative_source_sequence_is_dropped(self) -> None:
        result = self.parse(envelope(source_sequence=-1))
        assert isinstance(result, events.Event)
        self.assertIsNone(result.source_sequence)

    def test_a_boolean_source_sequence_is_dropped(self) -> None:
        result = self.parse(envelope(source_sequence=True))
        assert isinstance(result, events.Event)
        self.assertIsNone(result.source_sequence)

    def test_arrival_seq_is_taken_from_the_caller_not_the_body(self) -> None:
        # The server mints this under its ingress lock. A payload field claiming
        # one would let a hook choose its own place in the order.
        result = self.parse(envelope(arrival_seq=999), seq=4)
        assert isinstance(result, events.Event)
        self.assertEqual(4, result.arrival_seq)


class NormalizeSessionIdTest(unittest.TestCase):
    """The normalizer on its own, because the pending map calls it directly.

    `parse` refuses an unregistered harness before it gets here, so these cover
    the other caller: the coordinator resolving a native id against a collected
    row without a whole envelope to hand.
    """

    def test_claude_maps_a_uuid_onto_the_collectors_prefix(self) -> None:
        self.assertEqual(PREFIX, events.normalize_session_id("claude", SESSION))

    def test_an_unregistered_harness_maps_to_nothing(self) -> None:
        self.assertIsNone(events.normalize_session_id("goose", SESSION))

    def test_the_registry_only_holds_harnesses_whose_adapter_has_shipped(self) -> None:
        # Phase 2a ships no producer, so Claude is the only mapping established.
        # Antigravity joins this set in the phase that adds its hooks.json.
        self.assertEqual({"claude"}, set(events.IDENTITY_NORMALIZERS))


class TimestampTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = support.make_config()

    def parse(self, **overrides: Any) -> events.Event:
        result = events.parse(
            "claude", envelope(**overrides), arrival_seq=1, config=self.config, now=NOW
        )
        assert isinstance(result, events.Event)
        return result

    def test_an_iso_stamp_with_z_is_parsed_to_epoch_seconds(self) -> None:
        self.assertEqual(1_700_000_000.0, self.parse(timestamp="2023-11-14T22:13:20Z").timestamp)

    def test_an_offset_stamp_is_parsed(self) -> None:
        self.assertEqual(
            1_700_000_000.0, self.parse(timestamp="2023-11-14T23:13:20+01:00").timestamp
        )

    def test_a_naive_stamp_is_read_as_utc(self) -> None:
        self.assertEqual(1_700_000_000.0, self.parse(timestamp="2023-11-14T22:13:20").timestamp)

    def test_a_missing_stamp_falls_back_to_arrival(self) -> None:
        self.assertEqual(NOW, self.parse().timestamp)

    def test_an_unparseable_stamp_falls_back_to_arrival(self) -> None:
        self.assertEqual(NOW, self.parse(timestamp="last tuesday").timestamp)

    def test_a_stamp_hours_in_the_future_is_replaced_by_arrival(self) -> None:
        # A hook in a container whose clock runs ahead must not be able to pin a
        # row. Believing it would read as fresh activity for as long as the skew
        # lasts, which is the failure the store-timestamp filter already prevents.
        future = self.parse(timestamp="2023-11-15T22:13:20Z")
        self.assertEqual(NOW, future.timestamp)

    def test_a_stamp_inside_the_skew_tolerance_is_kept(self) -> None:
        # Sampling noise, not a broken clock: the same tolerance the store
        # timestamps get.
        seconds = self.config.future_skew_tolerance_sec / 2
        kept = self.parse(timestamp="2023-11-14T22:14:20Z")
        self.assertGreater(kept.timestamp, NOW)
        self.assertLessEqual(kept.timestamp - NOW, seconds + 1)


class OverlayMappingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = support.make_config()

    def event(self, name: str, *, seq: int = 1, at: float = NOW) -> events.Event:
        return events.Event(
            harness="claude",
            event=name,
            sid=PREFIX,
            session_id=SESSION,
            timestamp=at,
            arrival_seq=seq,
        )

    def overlay(self, name: str, **kwargs: Any) -> events.Overlay | None:
        return events.overlay_for(self.event(name, **kwargs), config=self.config)

    def test_a_prompt_means_working_with_a_deadline(self) -> None:
        overlay = self.overlay("turn_started")
        assert overlay is not None
        self.assertEqual(events.OVERLAY_WORKING, overlay.kind)
        self.assertEqual(NOW + self.config.overlay_working_ttl_sec, overlay.expires_at)

    def test_a_permission_reply_means_working_again(self) -> None:
        overlay = self.overlay("input_resolved")
        assert overlay is not None
        self.assertEqual(events.OVERLAY_WORKING, overlay.kind)

    def test_a_permission_request_means_needs_input_with_no_expiry(self) -> None:
        # The asymmetry is the point. A real permission wait can last hours, so a
        # generic timeout would clear a live alert while the user was at lunch.
        overlay = self.overlay("input_requested")
        assert overlay is not None
        self.assertEqual(events.OVERLAY_NEEDS_INPUT, overlay.kind)
        self.assertIsNone(overlay.expires_at)

    def test_a_stop_means_idle_only_after_the_dwell(self) -> None:
        overlay = self.overlay("turn_stopped")
        assert overlay is not None
        self.assertEqual(events.OVERLAY_IDLE, overlay.kind)
        self.assertFalse(overlay.applies(now=NOW))
        self.assertTrue(overlay.applies(now=NOW + self.config.overlay_idle_dwell_sec))

    def test_the_idle_dwell_is_well_above_the_coalescing_window(self) -> None:
        # The dwell exists so a stop followed immediately by a new prompt resolves
        # inside one publish. A dwell at or below the coalescing window would not
        # cover the case it was added for.
        self.assertGreater(self.config.overlay_idle_dwell_sec, 0.15 * 4)

    def test_the_working_deadline_matches_what_the_collectors_mean_by_working(self) -> None:
        # Tied to the existing threshold rather than chosen separately: an overlay
        # outliving it would claim Working for a session the scan calls Idle.
        self.assertEqual(self.config.working_threshold_sec, self.config.overlay_working_ttl_sec)

    def test_hint_events_produce_no_overlay(self) -> None:
        # These mean the store probably moved. A hint has no business patching a
        # display field, and session_started says nothing about activity at all.
        for name in ("store_changed", "tasks_changed", "reconcile_required", "session_started"):
            with self.subTest(name):
                self.assertIsNone(self.overlay(name))

    def test_session_ended_produces_no_overlay_and_retires_instead(self) -> None:
        ended = self.event("session_ended")
        self.assertIsNone(events.overlay_for(ended, config=self.config))
        self.assertTrue(events.retires_overlays(ended))

    def test_only_session_ended_retires(self) -> None:
        self.assertFalse(events.retires_overlays(self.event("turn_stopped")))

    def test_only_reconcile_required_asks_for_reconciliation(self) -> None:
        self.assertTrue(events.requires_reconcile(self.event("reconcile_required")))
        self.assertFalse(events.requires_reconcile(self.event("store_changed")))

    def test_a_subagent_event_is_recorded_as_its_own_kind(self) -> None:
        overlay = self.overlay("subagent_started")
        assert overlay is not None
        self.assertEqual(events.OVERLAY_SUBAGENT, overlay.kind)

    def test_every_event_name_is_either_an_overlay_a_retirement_or_a_hint(self) -> None:
        # No name may fall through unclassified: an event that means nothing to
        # any of the three paths would be accepted and then dropped in silence.
        for name in sorted(events.EVENT_NAMES):
            with self.subTest(name):
                event = self.event(name)
                classified = (
                    events.overlay_for(event, config=self.config) is not None
                    or events.retires_overlays(event)
                    or events.requires_reconcile(event)
                    or name in {"session_started", "store_changed", "tasks_changed"}
                )
                self.assertTrue(classified)


class ReduceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = support.make_config()

    def overlay(self, kind: str, *, seq: int, at: float = NOW, **kwargs: Any) -> events.Overlay:
        return events.Overlay(
            harness="claude", sid=PREFIX, arrival_seq=seq, kind=kind, at=at, **kwargs
        )

    def test_an_empty_ledger_patches_nothing(self) -> None:
        self.assertEqual({}, events.reduce_overlays([], now=NOW))

    def test_working_patches_state_and_marks_the_row_event_acquired(self) -> None:
        patch = events.reduce_overlays(
            [self.overlay(events.OVERLAY_WORKING, seq=1, expires_at=NOW + 90)], now=NOW
        )
        self.assertEqual("working", patch["state"])
        self.assertTrue(patch["active"])
        self.assertEqual(events.ACQUISITION_EVENT, patch["acquisition"])

    def test_needs_input_records_when_the_wait_began(self) -> None:
        patch = events.reduce_overlays(
            [self.overlay(events.OVERLAY_NEEDS_INPUT, seq=1, at=NOW - 30)], now=NOW
        )
        self.assertEqual("needs_input", patch["state"])
        self.assertEqual(NOW - 30, patch["blocked_since"])

    def test_working_clears_a_standing_blocked_since(self) -> None:
        patch = events.reduce_overlays(
            [
                self.overlay(events.OVERLAY_NEEDS_INPUT, seq=1),
                self.overlay(events.OVERLAY_WORKING, seq=2, expires_at=NOW + 90),
            ],
            now=NOW,
        )
        self.assertEqual("working", patch["state"])
        self.assertIsNone(patch["blocked_since"])

    def test_arrival_order_decides_not_timestamp_order(self) -> None:
        # Two hook processes that raced. Only the server's own counter is
        # trustworthy enough to order them, so the later arrival wins even though
        # its own clock says it happened first.
        patch = events.reduce_overlays(
            [
                self.overlay(events.OVERLAY_WORKING, seq=1, at=NOW, expires_at=NOW + 90),
                self.overlay(events.OVERLAY_NEEDS_INPUT, seq=2, at=NOW - 600),
            ],
            now=NOW,
        )
        self.assertEqual("needs_input", patch["state"])

    def test_reducing_is_independent_of_the_order_the_ledger_is_iterated_in(self) -> None:
        # At-least-once, possibly reordered delivery: the reducer sorts, so a
        # ledger handed over backwards must produce the same answer.
        ledger = [
            self.overlay(events.OVERLAY_NEEDS_INPUT, seq=1),
            self.overlay(events.OVERLAY_WORKING, seq=2, expires_at=NOW + 90),
        ]
        self.assertEqual(
            events.reduce_overlays(ledger, now=NOW),
            events.reduce_overlays(list(reversed(ledger)), now=NOW),
        )

    def test_reducing_twice_gives_the_same_patch(self) -> None:
        ledger = [self.overlay(events.OVERLAY_WORKING, seq=1, expires_at=NOW + 90)]
        self.assertEqual(
            events.reduce_overlays(ledger, now=NOW), events.reduce_overlays(ledger, now=NOW)
        )

    def test_an_expired_working_overlay_stops_patching(self) -> None:
        # A missed stop must not pin Working. Past the deadline the collector's
        # own reading of the store is what shows.
        ledger = [self.overlay(events.OVERLAY_WORKING, seq=1, expires_at=NOW + 90)]
        self.assertEqual({}, events.reduce_overlays(ledger, now=NOW + 91))

    def test_a_needs_input_overlay_never_expires_on_its_own(self) -> None:
        ledger = [self.overlay(events.OVERLAY_NEEDS_INPUT, seq=1, at=NOW)]
        patch = events.reduce_overlays(ledger, now=NOW + 86_400)
        self.assertEqual("needs_input", patch["state"])

    def test_an_expired_overlay_does_not_truncate_the_replay_behind_it(self) -> None:
        # Skipping rather than stopping. The dead overlay is deliberately the
        # earlier of the two: with it last, stopping and skipping agree, and the
        # first version of this test could not tell them apart.
        ledger = [
            self.overlay(events.OVERLAY_WORKING, seq=1, at=NOW - 100, expires_at=NOW - 10),
            self.overlay(events.OVERLAY_NEEDS_INPUT, seq=2, at=NOW - 5),
        ]
        self.assertEqual("needs_input", events.reduce_overlays(ledger, now=NOW)["state"])

    def test_a_stop_inside_its_dwell_does_not_yet_override_working(self) -> None:
        ledger = [
            self.overlay(events.OVERLAY_WORKING, seq=1, expires_at=NOW + 90),
            self.overlay(
                events.OVERLAY_IDLE, seq=2, effective_at=NOW + self.config.overlay_idle_dwell_sec
            ),
        ]
        self.assertEqual("working", events.reduce_overlays(ledger, now=NOW)["state"])
        self.assertEqual(
            "idle",
            events.reduce_overlays(ledger, now=NOW + self.config.overlay_idle_dwell_sec)["state"],
        )

    def test_a_subagent_overlay_does_not_change_the_parents_state(self) -> None:
        # A child starting says nothing about what the parent is doing, and the
        # parent's subagent list is the collector's to reconstruct.
        ledger = [self.overlay(events.OVERLAY_SUBAGENT, seq=1, subagent_id="child-1")]
        self.assertEqual({}, events.reduce_overlays(ledger, now=NOW))

    def test_a_subagent_overlay_does_not_erase_a_live_needs_input(self) -> None:
        ledger = [
            self.overlay(events.OVERLAY_NEEDS_INPUT, seq=1),
            self.overlay(events.OVERLAY_SUBAGENT, seq=2, subagent_id="child-1"),
        ]
        self.assertEqual("needs_input", events.reduce_overlays(ledger, now=NOW)["state"])


class ApplyPatchTest(unittest.TestCase):
    def test_only_patchable_fields_are_written(self) -> None:
        # The collector owns everything else. A reducer that grew a key by mistake
        # must not be able to rewrite a title or a token rate.
        session = {"title": "real title", "tokens": 1234, "state": "idle"}
        events.apply_patch(session, {"state": "working", "title": "forged", "tokens": 0})
        self.assertEqual("working", session["state"])
        self.assertEqual("real title", session["title"])
        self.assertEqual(1234, session["tokens"])

    def test_the_patchable_set_is_exactly_the_documented_five(self) -> None:
        self.assertEqual(
            {"state", "state_detail", "active", "blocked_since", "acquisition"},
            set(events.PATCHABLE),
        )

    def test_every_key_a_reducer_emits_is_patchable(self) -> None:
        # Otherwise a reducer could produce a field that apply_patch silently
        # drops, and the overlay would look applied while doing nothing.
        config = support.make_config()
        emitted: set[str] = set()
        for kind in (events.OVERLAY_WORKING, events.OVERLAY_NEEDS_INPUT, events.OVERLAY_IDLE):
            overlay = events.Overlay(harness="claude", sid=PREFIX, arrival_seq=1, kind=kind, at=NOW)
            emitted |= set(
                events.reduce_overlays([overlay], now=NOW + config.overlay_idle_dwell_sec)
            )
        self.assertLessEqual(emitted, set(events.PATCHABLE))
