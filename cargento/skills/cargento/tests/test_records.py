"""The repo-wide ISO-8601 rule: an offset-less stamp means UTC.

The rule only has teeth on a machine whose local time is not UTC: where it is,
a naive-means-local bug and a naive-means-UTC fix produce identical numbers, so
an assertion cannot tell them apart. That is why the original defect survived in
`parse_ts` and `quota._epoch` unnoticed, and it shapes this file into two layers.

Every assertion here states the contract directly, comparing against an
explicitly UTC-constructed instant. Those run everywhere, and they discriminate
on any developer machine that is not itself UTC, which is where the defect was
found.

On top of that, the tests marked with `needs_tz` **force** a non-UTC timezone, so
the discrimination does not depend on where the suite happens to run. That needs
`time.tzset`, which is Unix-only, so they skip on Windows rather than erroring:
the first version of this file called it unconditionally and took out the whole
`platform-tests` Windows job. The contract-level assertions still run there.
"""

from __future__ import annotations

import datetime as dt
import os
import time
import unittest
from contextlib import contextmanager
from typing import TYPE_CHECKING

from cargento_runtime import quota, records

if TYPE_CHECKING:
    from collections.abc import Iterator

# +08:00 with no DST, so the offset is the same in every season and a failure
# reads as a timezone bug rather than as a date-dependent flake. This is also
# the offset the defect was found on.
TZ = "Asia/Taipei"

# `time.tzset` exists on Unix only. Probed rather than keyed off `sys.platform`
# so the skip follows the capability the tests actually need.
HAS_TZSET = hasattr(time, "tzset")
needs_tz = unittest.skipUnless(
    HAS_TZSET, "time.tzset is Unix-only, so the process timezone cannot be forced here"
)


@contextmanager
def tz(name: str) -> Iterator[None]:
    """Run the body with `TZ` set, restoring both the variable and libc's cache.

    `time.tzset` is what actually moves `datetime.timestamp()`'s idea of local
    time; setting the environment variable alone changes nothing in a process
    that has already read it. Callers must carry `@needs_tz`.
    """
    before = os.environ.get("TZ")
    os.environ["TZ"] = name
    time.tzset()
    try:
        yield
    finally:
        if before is None:
            del os.environ["TZ"]
        else:
            os.environ["TZ"] = before
        time.tzset()


class IsoEpochTest(unittest.TestCase):
    # 2026-01-02T03:04:05Z, chosen so every field differs and a transposition
    # cannot pass by symmetry.
    UTC_EPOCH = dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.UTC).timestamp()

    @needs_tz
    def test_a_naive_stamp_is_read_as_utc_not_as_local(self) -> None:
        # The regression. Under +08:00 the old `fromisoformat().timestamp()`
        # returned this instant minus eight hours, which is what pushed a live
        # turn out of the activity window.
        with tz(TZ):
            self.assertEqual(self.UTC_EPOCH, records.iso_epoch("2026-01-02T03:04:05"))

    @needs_tz
    def test_the_naive_reading_does_not_move_with_the_timezone(self) -> None:
        readings = []
        for name in ("UTC", TZ, "America/New_York"):
            with tz(name):
                readings.append(records.iso_epoch("2026-01-02T03:04:05"))
        self.assertEqual([self.UTC_EPOCH] * 3, readings)

    @needs_tz
    def test_an_explicit_offset_is_honoured_rather_than_overridden(self) -> None:
        # The common case in practice: every source measured on 2026-08-06 sends
        # one. A fix that forced UTC onto an aware stamp would break these.
        with tz(TZ):
            self.assertEqual(self.UTC_EPOCH, records.iso_epoch("2026-01-02T03:04:05+00:00"))
            self.assertEqual(self.UTC_EPOCH, records.iso_epoch("2026-01-02T11:04:05+08:00"))
            self.assertEqual(self.UTC_EPOCH, records.iso_epoch("2026-01-01T22:04:05-05:00"))

    @needs_tz
    def test_a_trailing_z_is_accepted(self) -> None:
        with tz(TZ):
            self.assertEqual(self.UTC_EPOCH, records.iso_epoch("2026-01-02T03:04:05Z"))

    def test_unusable_input_is_nothing_rather_than_a_guess(self) -> None:
        unusable: tuple[object, ...] = (
            "",
            "not a date",
            "2026-13-45T99:99:99",
            None,
            1_700_000_000,
            [],
            {},
        )
        for value in unusable:
            self.assertIsNone(records.iso_epoch(value), repr(value))


class ContractTest(unittest.TestCase):
    """The rule stated without forcing a timezone, so Windows checks it too.

    These compare against an explicitly UTC-constructed instant, which is the
    contract itself rather than a proxy for it. They cannot fail on a machine
    whose local time is already UTC, and they catch the defect on every machine
    that is not, which includes the one it was found on. The `needs_tz` tests
    above remove that dependency where the platform allows it; these are what
    keeps the Windows runner from asserting nothing at all.
    """

    NAIVE = "2026-01-02T03:04:05"
    EXPECTED = dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.UTC).timestamp()

    def test_every_reader_agrees_a_naive_stamp_is_the_utc_instant(self) -> None:
        # One assertion per reader, because the whole defect was two of the four
        # disagreeing with the other two.
        self.assertEqual(self.EXPECTED, records.iso_epoch(self.NAIVE))
        self.assertEqual(self.EXPECTED, records.parse_ts(self.NAIVE))
        self.assertEqual(self.EXPECTED, records.parse_utc_sql(self.NAIVE.replace("T", " ")))
        self.assertEqual(self.EXPECTED, quota._epoch(self.NAIVE))

    def test_a_naive_stamp_and_its_utc_spelling_are_the_same_instant(self) -> None:
        # The rule as an equality between two inputs rather than against a
        # constant, so it holds whatever the machine's clock is set to.
        for aware in (self.NAIVE + "Z", self.NAIVE + "+00:00"):
            self.assertEqual(records.iso_epoch(aware), records.iso_epoch(self.NAIVE), aware)
            self.assertEqual(records.parse_ts(aware), records.parse_ts(self.NAIVE), aware)

    def test_an_offset_is_never_overridden(self) -> None:
        # Tz-independent by construction: +08:00 and -05:00 name the same instant
        # as the Z spelling, whatever the reader's own zone.
        self.assertEqual(
            records.iso_epoch("2026-01-02T03:04:05Z"),
            records.iso_epoch("2026-01-02T11:04:05+08:00"),
        )
        self.assertEqual(
            records.iso_epoch("2026-01-02T03:04:05Z"),
            records.iso_epoch("2026-01-01T22:04:05-05:00"),
        )


class ParseTsTest(unittest.TestCase):
    """`parse_ts` is the transcript reader: Claude, Pi, turns, transcripts."""

    @needs_tz
    def test_a_naive_transcript_stamp_is_utc(self) -> None:
        with tz(TZ):
            self.assertEqual(
                dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.UTC).timestamp(),
                records.parse_ts("2026-01-02T03:04:05"),
            )

    @needs_tz
    def test_it_agrees_with_the_shared_helper(self) -> None:
        # Both readers must not drift again, which is how they came to disagree.
        with tz(TZ):
            for value in ("2026-01-02T03:04:05", "2026-01-02T03:04:05Z", "bad"):
                self.assertEqual(records.iso_epoch(value), records.parse_ts(value), value)


class UsageSignalTest(unittest.TestCase):
    @staticmethod
    def _record(value: object) -> dict[str, object]:
        return {
            "type": "assistant",
            "message": {"usage": {"output_tokens": value}},
        }

    def test_claude_output_tokens_are_the_only_measured_signal(self) -> None:
        self.assertEqual(37, records.usage_signal(self._record(37), "claude"))
        self.assertEqual(0, records.usage_signal(self._record(0), "claude"))

    def test_a_claude_shaped_record_is_refused_for_every_other_scanned_harness(self) -> None:
        record = self._record(37)
        for harness in ("codex", "copilot", "gemini", "droid"):
            with self.subTest(harness=harness):
                self.assertIsNone(records.usage_signal(record, harness))

    def test_malformed_or_unmeasured_values_are_nothing_not_zero(self) -> None:
        malformed: tuple[object, ...] = (None, True, -1, 1.5, "37", {}, [])
        for value in malformed:
            with self.subTest(value=value):
                self.assertIsNone(records.usage_signal(self._record(value), "claude"))
        self.assertIsNone(
            records.usage_signal(
                {"type": "user", "message": {"usage": {"output_tokens": 37}}},
                "claude",
            )
        )
        self.assertIsNone(records.usage_signal({"type": "assistant"}, "claude"))


class ParseUtcSqlTest(unittest.TestCase):
    """`parse_utc_sql` reads Copilot's and Goose's SQLite text columns."""

    @needs_tz
    def test_sqlites_space_separated_default_spelling_is_read_as_utc(self) -> None:
        with tz(TZ):
            self.assertEqual(
                dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.UTC).timestamp(),
                records.parse_utc_sql("2026-01-02 03:04:05"),
            )

    @needs_tz
    def test_an_offset_bearing_column_is_honoured(self) -> None:
        # Copilot's real store was measured sending these, so the naive branch is
        # a guard rather than the normal path.
        with tz(TZ):
            self.assertEqual(
                dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.UTC).timestamp(),
                records.parse_utc_sql("2026-01-02 11:04:05+08:00"),
            )

    def test_unusable_input_is_zero_because_the_callers_window_on_it(self) -> None:
        for value in (None, "", "nonsense", 0):
            self.assertEqual(0, records.parse_utc_sql(value), repr(value))


class QuotaEpochTest(unittest.TestCase):
    """`quota._epoch` reads `resets_at`, which drives every reset countdown."""

    @needs_tz
    def test_a_naive_reset_stamp_is_utc(self) -> None:
        # An eight-hour error here moves the countdown and, since A5, the burn
        # projection that fires off `resetAt`.
        with tz(TZ):
            self.assertEqual(
                dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.UTC).timestamp(),
                quota._epoch("2026-01-02T03:04:05"),
            )

    @needs_tz
    def test_an_offset_bearing_reset_stamp_is_honoured(self) -> None:
        with tz(TZ):
            self.assertEqual(
                dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.UTC).timestamp(),
                quota._epoch("2026-01-02T03:04:05+00:00"),
            )

    @needs_tz
    def test_a_numeric_stamp_still_passes_through_unchanged(self) -> None:
        # The endpoint has sent both shapes; epoch seconds carry no timezone
        # question and must not be routed through the ISO reader.
        with tz(TZ):
            self.assertEqual(1_700_000_000.0, quota._epoch(1_700_000_000))
            self.assertIsNone(quota._epoch(0))
            self.assertIsNone(quota._epoch(True))


if __name__ == "__main__":
    unittest.main()
