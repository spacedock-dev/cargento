"""The published dashboard snapshot: revisions, variants, and staleness."""

from __future__ import annotations

import unittest

from cargento_runtime import snapshot as runtime_snapshot


class SnapshotTest(unittest.TestCase):
    def _snap(self, started: float = 1000.0) -> runtime_snapshot.Snapshot:
        return runtime_snapshot.Snapshot(server_started=started)

    def test_publishing_returns_a_monotonic_counter(self) -> None:
        snap = self._snap()
        first = snap.publish((24.0, False), b'{"a":1}')
        second = snap.publish((24.0, False), b'{"a":2}')
        self.assertEqual(first[1] + 1, second[1])

    def test_the_counter_is_shared_across_keys_so_it_orders_the_whole_process(self) -> None:
        # A client holds one cursor, not one per variant, so a per-key counter
        # would let ?all=1 and the default view report the same number for
        # different states.
        snap = self._snap()
        a = snap.publish((24.0, False), b"{}")
        b = snap.publish((24.0, True), b"{}")
        self.assertNotEqual(a[1], b[1])

    def test_the_revision_carries_the_server_start_stamp(self) -> None:
        snap = self._snap(started=1234.5)
        self.assertIsNone(snap.current((24.0, False)))
        published = snap.publish((24.0, False), b"{}")
        self.assertEqual(published[0], 1234.5)

    def test_current_returns_the_published_bytes_and_its_revision(self) -> None:
        snap = self._snap()
        rev = snap.publish((24.0, False), b'{"x":1}')
        got = snap.current((24.0, False))
        self.assertIsNotNone(got)
        assert got is not None
        self.assertEqual(got, (rev, b'{"x":1}'))

    def test_an_unpublished_key_is_absent_rather_than_empty(self) -> None:
        self.assertIsNone(self._snap().current((24.0, True)))

    def test_age_measures_from_the_publish_clock(self) -> None:
        snap = self._snap()
        snap.publish((24.0, False), b"{}", now=500.0)
        age = snap.age((24.0, False), now=502.5)
        self.assertIsNotNone(age)
        assert age is not None
        self.assertAlmostEqual(age, 2.5)

    def test_age_of_an_unpublished_key_is_none_not_zero(self) -> None:
        # Zero would read as "fresh" and skip the collection a cold GET needs.
        self.assertIsNone(self._snap().age((24.0, False), now=1.0))

    def test_format_revision_is_stable_and_restart_qualified(self) -> None:
        self.assertEqual(runtime_snapshot.format_revision((1700000000.0, 7)), "1700000000.7")

    def test_two_snapshots_with_different_starts_never_collide(self) -> None:
        # The whole point of the pair: a tab holding revision 512 from a previous
        # process must not treat the new process's revision 3 as older.
        a = self._snap(started=1000.0).publish((24.0, False), b"{}")
        b = self._snap(started=2000.0).publish((24.0, False), b"{}")
        self.assertEqual(a[1], b[1])
        self.assertNotEqual(a, b)


if __name__ == "__main__":
    unittest.main()
