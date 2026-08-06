"""The repo-wide ISO-8601 rule: an offset-less stamp means UTC.

Every test here forces a **non-UTC** timezone before parsing. That is the whole
point of the file: on a UTC machine a naive-means-local bug and a
naive-means-UTC fix produce identical numbers, so a suite that does not move the
clock cannot tell them apart. CI runners are UTC, which is why the original
defect survived in `parse_ts` and `quota._epoch` unnoticed.
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


@contextmanager
def tz(name: str) -> Iterator[None]:
    """Run the body with `TZ` set, restoring both the variable and libc's cache.

    `time.tzset` is what actually moves `datetime.timestamp()`'s idea of local
    time; setting the environment variable alone changes nothing in a process
    that has already read it.
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

    def test_a_naive_stamp_is_read_as_utc_not_as_local(self) -> None:
        # The regression. Under +08:00 the old `fromisoformat().timestamp()`
        # returned this instant minus eight hours, which is what pushed a live
        # turn out of the activity window.
        with tz(TZ):
            self.assertEqual(self.UTC_EPOCH, records.iso_epoch("2026-01-02T03:04:05"))

    def test_the_naive_reading_does_not_move_with_the_timezone(self) -> None:
        readings = []
        for name in ("UTC", TZ, "America/New_York"):
            with tz(name):
                readings.append(records.iso_epoch("2026-01-02T03:04:05"))
        self.assertEqual([self.UTC_EPOCH] * 3, readings)

    def test_an_explicit_offset_is_honoured_rather_than_overridden(self) -> None:
        # The common case in practice: every source measured on 2026-08-06 sends
        # one. A fix that forced UTC onto an aware stamp would break these.
        with tz(TZ):
            self.assertEqual(self.UTC_EPOCH, records.iso_epoch("2026-01-02T03:04:05+00:00"))
            self.assertEqual(self.UTC_EPOCH, records.iso_epoch("2026-01-02T11:04:05+08:00"))
            self.assertEqual(self.UTC_EPOCH, records.iso_epoch("2026-01-01T22:04:05-05:00"))

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


class ParseTsTest(unittest.TestCase):
    """`parse_ts` is the transcript reader: Claude, Pi, turns, transcripts."""

    def test_a_naive_transcript_stamp_is_utc(self) -> None:
        with tz(TZ):
            self.assertEqual(
                dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.UTC).timestamp(),
                records.parse_ts("2026-01-02T03:04:05"),
            )

    def test_it_agrees_with_the_shared_helper(self) -> None:
        # Both readers must not drift again, which is how they came to disagree.
        with tz(TZ):
            for value in ("2026-01-02T03:04:05", "2026-01-02T03:04:05Z", "bad"):
                self.assertEqual(records.iso_epoch(value), records.parse_ts(value), value)


class ParseUtcSqlTest(unittest.TestCase):
    """`parse_utc_sql` reads Copilot's and Goose's SQLite text columns."""

    def test_sqlites_space_separated_default_spelling_is_read_as_utc(self) -> None:
        with tz(TZ):
            self.assertEqual(
                dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.UTC).timestamp(),
                records.parse_utc_sql("2026-01-02 03:04:05"),
            )

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

    def test_a_naive_reset_stamp_is_utc(self) -> None:
        # An eight-hour error here moves the countdown and, since A5, the burn
        # projection that fires off `resetAt`.
        with tz(TZ):
            self.assertEqual(
                dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.UTC).timestamp(),
                quota._epoch("2026-01-02T03:04:05"),
            )

    def test_an_offset_bearing_reset_stamp_is_honoured(self) -> None:
        with tz(TZ):
            self.assertEqual(
                dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.UTC).timestamp(),
                quota._epoch("2026-01-02T03:04:05+00:00"),
            )

    def test_a_numeric_stamp_still_passes_through_unchanged(self) -> None:
        # The endpoint has sent both shapes; epoch seconds carry no timezone
        # question and must not be routed through the ISO reader.
        with tz(TZ):
            self.assertEqual(1_700_000_000.0, quota._epoch(1_700_000_000))
            self.assertIsNone(quota._epoch(0))
            self.assertIsNone(quota._epoch(True))


if __name__ == "__main__":
    unittest.main()
