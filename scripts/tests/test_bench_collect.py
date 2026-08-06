from __future__ import annotations

import contextlib
import dataclasses
import io
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bench_collect

if TYPE_CHECKING:
    from collections.abc import Callable

# Long enough that a wrapper's measured duration is above any platform's clock
# granularity, short enough that the whole module still runs in milliseconds.
DISCOVER_SLEEP = 0.001
COLLECT_SLEEP = 0.002


@dataclasses.dataclass(frozen=True)
class FakeSpec:
    """HarnessSpec's identity field is `key`, not `name`.

    Verified against aggregate.HarnessSpec, whose fields are: collect, discover,
    key, label, usage, usage_is_fetch. Frozen for the same reason the real one
    is, which is what forces measure to rebuild the registry with
    dataclasses.replace rather than assigning over spec.collect.
    """

    key: str
    label: str
    discover: Callable[..., bool]
    collect: Callable[..., list[str]]


def fake_spec(
    key: str,
    *,
    sessions: tuple[str, ...] = (),
    calls: list[tuple[Any, ...]] | None = None,
    fails: bool = False,
) -> FakeSpec:
    """One registry entry whose collector records the arguments it was handed."""

    def discover(config: Any, state: Any) -> bool:
        del config, state
        time.sleep(DISCOVER_SLEEP)
        return True

    def collect(
        config: Any, state: Any, now: float, window_hours: float, show_all: bool
    ) -> list[str]:
        if calls is not None:
            calls.append((config, state, now, window_hours, show_all))
        time.sleep(COLLECT_SLEEP)
        if fails:
            raise RuntimeError("collector exploded")
        return list(sessions)

    return FakeSpec(key=key, label=key.title(), discover=discover, collect=collect)


class FakeRegistryApp:
    """Stands in for Application over a small registry.

    collect mirrors Application.collect: discover each spec, then call the
    collector of every discovered one with the same five positional arguments
    the real Collector contract takes. It deliberately does not swallow a
    collector exception, so the restore-on-failure test exercises measure's
    finally rather than this fake's error handling.
    """

    def __init__(self, harnesses: tuple[FakeSpec, ...]) -> None:
        self.harnesses = harnesses

    def collect(self, *, show_all: bool) -> dict[str, object]:
        sessions: list[str] = []
        for spec in self.harnesses:
            if not spec.discover(None, None):
                continue
            sessions.extend(spec.collect(None, None, 0.0, 24.0, show_all))
        return {"sessions": sessions}


class FakeApp:
    """Stands in for Application: two harnesses, one slow and one fast."""

    def __init__(self) -> None:
        self.collect_calls = 0

    def collect(self, *, show_all: bool) -> dict[str, object]:
        # Mirrors Application.collect exactly: show_all is keyword-only and
        # required, and there is no window_hours parameter.
        del show_all
        self.collect_calls += 1
        return {"sessions": [], "generated": 0.0}


class MeasureTest(unittest.TestCase):
    def test_measure_reports_total_and_repeat_count(self) -> None:
        app = FakeApp()
        result = bench_collect.measure(app, repeat=3)
        self.assertEqual(result["repeat"], 3)
        self.assertEqual(app.collect_calls, 3)
        self.assertIsInstance(result["total_ms"], float)
        self.assertGreaterEqual(result["total_ms"], 0.0)

    def test_measure_rejects_a_non_positive_repeat(self) -> None:
        with self.assertRaises(ValueError):
            bench_collect.measure(FakeApp(), repeat=0)

    def test_format_report_names_every_measured_harness(self) -> None:
        report = bench_collect.format_report(
            {
                "total_ms": 285.0,
                "per_harness_ms": {"claude": 270.0, "codex": 15.0},
                "discovery_ms": 0.4,
                "repeat": 5,
            }
        )
        self.assertIn("claude", report)
        self.assertIn("codex", report)
        self.assertIn("285.0", report)


class RegistryTimingTest(unittest.TestCase):
    """Per-harness and discovery timing, and the registry restore that pays for it."""

    def test_every_collected_harness_gets_its_own_figure(self) -> None:
        app = FakeRegistryApp((fake_spec("claude", sessions=("a",)), fake_spec("codex")))
        result = bench_collect.measure(app, repeat=2)
        self.assertEqual(sorted(result["per_harness_ms"]), ["claude", "codex"])
        self.assertGreater(result["per_harness_ms"]["claude"], 0.0)
        self.assertGreater(result["discovery_ms"], 0.0)

    def test_the_wrapped_collector_is_delegated_to_unchanged(self) -> None:
        calls: list[tuple[Any, ...]] = []
        app = FakeRegistryApp((fake_spec("claude", sessions=("a", "b"), calls=calls),))
        bench_collect.measure(app, repeat=1)
        self.assertEqual(calls, [(None, None, 0.0, 24.0, False)])

    def test_the_registry_is_restored_after_a_clean_run(self) -> None:
        original = (fake_spec("claude"),)
        app = FakeRegistryApp(original)
        bench_collect.measure(app, repeat=1)
        self.assertIs(app.harnesses, original)

    def test_a_raising_collector_still_restores_the_registry(self) -> None:
        """A wrapper must not swallow: the failure boundary is Application.collect's."""
        original = (fake_spec("claude", fails=True),)
        app = FakeRegistryApp(original)
        with self.assertRaises(RuntimeError):
            bench_collect.measure(app, repeat=1)
        self.assertIs(app.harnesses, original)


if __name__ == "__main__":
    unittest.main()


class SelectiveReuseTest(unittest.TestCase):
    """The share is the comparable figure; absolute milliseconds are not.

    A single machine's absolute timings are what made this question look settled
    when it was not, so these tests pin the share and the bar rather than any
    duration.
    """

    def test_one_dominant_harness_reports_a_small_saving(self) -> None:
        r = bench_collect.selective_reuse(
            {"total_ms": 108.4, "per_harness_ms": {"claude": 100.6, "codex": 4.1}}
        )
        self.assertEqual(r["largest"], "claude")
        self.assertAlmostEqual(r["share"], 100.6 / 108.4, places=6)
        self.assertLess(r["saving"], bench_collect.SELECTIVE_REUSE_BAR)

    def test_a_balanced_store_clears_the_bar(self) -> None:
        r = bench_collect.selective_reuse(
            {"total_ms": 100.0, "per_harness_ms": {"a": 30.0, "b": 25.0, "c": 25.0, "d": 20.0}}
        )
        self.assertEqual(r["largest"], "a")
        self.assertAlmostEqual(r["saving"], 0.70, places=6)
        self.assertGreaterEqual(r["saving"], bench_collect.SELECTIVE_REUSE_BAR)

    def test_the_bar_is_exactly_at_a_75_percent_largest_share(self) -> None:
        # The documented criterion: reuse clears 25% iff the largest harness is
        # at most 75% of collection time. Pin the boundary, not a rounded number.
        r = bench_collect.selective_reuse(
            {"total_ms": 100.0, "per_harness_ms": {"big": 75.0, "rest": 25.0}}
        )
        self.assertAlmostEqual(r["saving"], 0.25, places=6)
        self.assertGreaterEqual(r["saving"], bench_collect.SELECTIVE_REUSE_BAR)

    def test_no_discovered_harness_reports_nothing_rather_than_zero(self) -> None:
        r = bench_collect.selective_reuse({"total_ms": 0.5, "per_harness_ms": {}})
        self.assertIsNone(r["largest"])
        self.assertIsNone(r["share"])

    def test_the_report_leads_with_the_share_and_says_one_machine_cannot_settle_it(self) -> None:
        report = bench_collect.format_report(
            {
                "total_ms": 108.4,
                "per_harness_ms": {"claude": 100.6, "codex": 4.1},
                "discovery_ms": 0.34,
                "repeat": 7,
            }
        )
        self.assertIn("largest harness: claude", report)
        self.assertIn("92.8%", report)
        self.assertIn("below the 25% bar", report)
        self.assertIn("One machine cannot settle this", report)


class SimulationSpecTest(unittest.TestCase):
    """Parsing a simulation spec, where a silent misread is the failure to avoid."""

    def test_a_named_profile_resolves_to_its_counts(self) -> None:
        self.assertEqual(
            bench_collect.parse_simulation("balanced-five"),
            bench_collect.SIMULATIONS["balanced-five"],
        )

    def test_a_named_profile_is_copied_rather_than_handed_out(self) -> None:
        # The caller is free to mutate what it gets; the table behind it is not.
        parsed = bench_collect.parse_simulation("two-harness")
        parsed["claude"] = 999
        self.assertEqual(bench_collect.SIMULATIONS["two-harness"]["claude"], 20)

    def test_harness_pairs_parse_to_session_counts(self) -> None:
        self.assertEqual(
            bench_collect.parse_simulation("claude=3, codex=4"), {"claude": 3, "codex": 4}
        )

    def test_an_unknown_harness_is_an_error_rather_than_a_skip(self) -> None:
        # Silently generating nothing would report a share for a profile the
        # caller never ran, which is the whole failure this ticket exists over.
        with self.assertRaises(ValueError):
            bench_collect.parse_simulation("clade=3")

    def test_an_unknown_profile_name_is_an_error(self) -> None:
        with self.assertRaises(ValueError):
            bench_collect.parse_simulation("balanced")

    def test_a_non_integer_count_is_an_error(self) -> None:
        with self.assertRaises(ValueError):
            bench_collect.parse_simulation("claude=lots")

    def test_a_negative_count_is_an_error(self) -> None:
        with self.assertRaises(ValueError):
            bench_collect.parse_simulation("claude=-1")


class SimulatedStoreTest(unittest.TestCase):
    """The generated store, and the guard against measuring the caller's own."""

    def test_every_store_key_is_overridden_not_only_the_generated_ones(self) -> None:
        # A simulation that overrode only claude would leave nine stores pointing
        # at the caller's real home, and the share would be of a machine nobody
        # has. This is the assertion that keeps the simulation a simulation.
        with tempfile.TemporaryDirectory() as tmp:
            overrides = bench_collect.build_simulated_store(
                Path(tmp), {"claude": 1}, now=time.time(), records=1
            )
        self.assertEqual(sorted(overrides), sorted(bench_collect.ALL_STORE_KEYS))
        for key, path in overrides.items():
            self.assertTrue(path.startswith(tmp), f"{key} escaped the scratch tree: {path}")

    def test_an_ungenerated_harness_points_somewhere_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            overrides = bench_collect.build_simulated_store(
                Path(tmp), {"claude": 1}, now=time.time(), records=1
            )
            # goose.db names a file rather than a directory, so its stand-in has
            # to be a path that does not exist, not the shared empty directory.
            self.assertFalse(Path(overrides["goose.db"]).exists())
            self.assertEqual(list(Path(overrides["codex.sessions"]).iterdir()), [])

    def test_claudes_two_stores_get_two_different_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            overrides = bench_collect.build_simulated_store(
                Path(tmp), {"claude": 1}, now=time.time(), records=1
            )
        self.assertNotEqual(overrides["claude.projects"], overrides["claude.tasks"])

    def test_sessions_are_spread_across_the_requested_project_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            overrides = bench_collect.build_simulated_store(
                Path(tmp), {"claude": 6}, now=time.time(), records=1, projects=3
            )
            projects = sorted(p.name for p in Path(overrides["claude.projects"]).iterdir())
        # Not cosmetic: a directory per session made a store shaped like the
        # Phase 0 machine cost 4.8x what the machine itself costs.
        self.assertEqual(len(projects), 3)

    def test_out_of_window_sessions_are_written_but_not_in_the_window(self) -> None:
        now = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            overrides = bench_collect.build_simulated_store(
                Path(tmp), {"claude": 2}, now=now, records=1, cold=5, projects=1
            )
            written = list(Path(overrides["claude.projects"]).rglob("*.jsonl"))
            recent = [f for f in written if f.stat().st_mtime > now - 3600]
        self.assertEqual(len(written), 7)
        self.assertEqual(len(recent), 2)


class SimulationReportTest(unittest.TestCase):
    def test_the_report_prints_what_was_asked_for_and_what_was_collected(self) -> None:
        report = bench_collect.format_report(
            {
                "total_ms": 30.0,
                "per_harness_ms": {"claude": 10.0, "codex": 10.0, "pi": 10.0},
                "discovery_ms": 0.3,
                "sessions": {"claude": 2, "codex": 2, "pi": 2},
                "repeat": 5,
            },
            {
                "spec": "demo",
                "counts": {"claude": 2, "codex": 2, "pi": 2},
                "records": 4,
                "record_bytes": 1024,
                "cold": 0,
                "projects": 2,
            },
        )
        self.assertIn("simulated store: demo", report)
        self.assertIn("claude=2", report)
        self.assertIn("A synthetic store measures", report)
        self.assertNotIn("One machine cannot settle this", report)

    def test_a_store_no_collector_recognised_says_so_instead_of_reporting_a_share(self) -> None:
        # The share would still compute, and would still look plausible. Printing
        # a count of zero next to the count asked for is what makes it visible.
        report = bench_collect.format_report(
            {
                "total_ms": 1.0,
                "per_harness_ms": {"claude": 0.5},
                "discovery_ms": 0.1,
                "sessions": {},
                "repeat": 1,
            },
            {
                "spec": "demo",
                "counts": {"claude": 4},
                "records": 4,
                "record_bytes": 1024,
                "cold": 0,
                "projects": 1,
            },
        )
        self.assertIn("NOTHING", report)


class SimulationEndToEndTest(unittest.TestCase):
    """The generated store, run through the real runtime and its real collectors.

    Inspecting the generated files proves nothing: the question is whether the
    collectors recognise them, and only a collection can answer it. A generator
    that drifts from a store shape fails here rather than reporting a confident
    share of an empty store.
    """

    def test_each_generated_harness_collects_the_sessions_it_was_asked_for(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = bench_collect.main(
                [
                    "bench_collect",
                    "--simulate",
                    "claude=2,codex=2,pi=2,gemini=2,copilot=2,droid=2",
                    "--simulate-records",
                    "2",
                    "--simulate-projects",
                    "2",
                    "--repeat",
                    "1",
                ]
            )
        report = buffer.getvalue()
        self.assertEqual(code, 0)
        self.assertIn(
            "collected:                 claude=2, codex=2, copilot=2, droid=2, gemini=2, pi=2",
            report,
        )
        self.assertNotIn("NOTHING", report)

    def test_an_unparseable_spec_exits_non_zero_without_measuring(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            code = bench_collect.main(["bench_collect", "--simulate", "nope=1"])
        self.assertEqual(code, 2)
        self.assertIn("unknown simulation", buffer.getvalue())

    def test_listing_the_profiles_needs_no_runtime_and_names_them_all(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = bench_collect.main(["bench_collect", "--list-simulations"])
        self.assertEqual(code, 0)
        for name in bench_collect.SIMULATIONS:
            self.assertIn(name, buffer.getvalue())
