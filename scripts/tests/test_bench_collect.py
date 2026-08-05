from __future__ import annotations

import dataclasses
import sys
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
