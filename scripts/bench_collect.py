#!/usr/bin/env python3
"""Measure Cargento collection cost, per harness and in total.

Phase 0 of the event-driven observation plan gates on these numbers, so they
have to be reproducible on a reviewer's machine rather than quoted from one
laptop. Timing uses perf_counter and reports a median, because a cold page
cache makes a single sample useless.
"""

from __future__ import annotations

import argparse
import cProfile
import dataclasses
import pstats
import statistics
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

# The bar the event-driven plan sets for building per-harness dirty invalidation.
# Owned by docs/plans/event-driven-session-observation.md; change it there first.
SELECTIVE_REUSE_BAR = 0.25

# The dashboard runtime is not an installed package. server.py imports it with
# the skill directory as sys.path[0], and this script has to arrange the same.
SKILL_DIR = Path(__file__).resolve().parents[1] / "cargento" / "skills" / "cargento"


def timed(inner: Callable[..., Any], samples: list[float]) -> Callable[..., Any]:
    """Wrap a registry callable so each call appends its duration to ``samples``.

    The duration is recorded in a finally and the exception is re-raised
    untouched: the per-harness failure boundary belongs to Application.collect,
    and swallowing here would change which harnesses the benchmark reports as
    broken.
    """

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            return inner(*args, **kwargs)
        finally:
            samples.append((time.perf_counter() - started) * 1000.0)

    return wrapped


def measure(app: Any, *, repeat: int) -> dict[str, Any]:
    """Median wall-clock cost of a full collect, and of each harness inside it.

    Every sample is a real collect against the caller's stores. The per-harness
    figures come from wrapping each registry entry's collector, so they sum to
    the total minus serialization rather than being estimated.

    HarnessSpec is frozen, so a wrapper cannot be assigned over spec.collect.
    The registry is rebuilt with dataclasses.replace for the duration of the
    measurement and the original tuple is restored in a finally, which keeps a
    benchmark run from leaving instrumentation behind on a live application.
    """
    if repeat < 1:
        raise ValueError("repeat must be at least 1")
    totals: list[float] = []
    per_harness: dict[str, list[float]] = {}
    discovery: list[float] = []
    discover_calls: list[float] = []
    specs = tuple(getattr(app, "harnesses", ()) or ())
    for spec in specs:
        per_harness.setdefault(spec.key, [])
    if specs:
        app.harnesses = tuple(
            dataclasses.replace(
                spec,
                collect=timed(spec.collect, per_harness[spec.key]),
                discover=timed(spec.discover, discover_calls),
            )
            for spec in specs
        )
    try:
        for _ in range(repeat):
            mark = len(discover_calls)
            started = time.perf_counter()
            app.collect(show_all=False)
            totals.append((time.perf_counter() - started) * 1000.0)
            # Every harness is probed on every collect, so one sample is the
            # whole discovery cost of one collect rather than of one probe.
            discovery.append(sum(discover_calls[mark:]))
    finally:
        if specs:
            app.harnesses = specs
    return {
        "total_ms": statistics.median(totals),
        # An undiscovered harness never has its collector called, so it has no
        # samples and is left out rather than reported as zero.
        "per_harness_ms": {name: statistics.median(v) for name, v in per_harness.items() if v},
        "discovery_ms": statistics.median(discovery) if discovery else 0.0,
        "repeat": repeat,
    }


def selective_reuse(result: dict[str, Any]) -> dict[str, Any]:
    """What per-harness dirty invalidation could save on this machine.

    The dirty harness is the one whose cost cannot be skipped, so the saving
    available to reuse is the total minus the largest single harness. That makes
    the whole question one number: reuse clears a 25% bar whenever the largest
    harness is at most 75% of collection time.

    Absolute milliseconds are not comparable across machines, and one machine's
    absolute figures are what made this question look settled when it was not.
    The share is comparable, which is why the report leads with it.
    """
    per = {k: float(v) for k, v in result["per_harness_ms"].items()}
    total = float(result["total_ms"])
    if not per or total <= 0:
        return {"largest": None, "share": None, "saving": None}
    largest = max(per, key=lambda k: per[k])
    share = per[largest] / total
    return {"largest": largest, "share": share, "saving": 1.0 - share}


def format_report(result: dict[str, Any]) -> str:
    lines = [
        f"repeat: {result['repeat']}",
        f"total_ms: {result['total_ms']}",
        f"discovery_ms: {result['discovery_ms']}",
    ]
    for name, value in sorted(result["per_harness_ms"].items(), key=lambda kv: -float(kv[1])):
        lines.append(f"  {name}: {value} ms")
    reuse = selective_reuse(result)
    if reuse["share"] is not None:
        verdict = "clears" if reuse["saving"] >= SELECTIVE_REUSE_BAR else "below"
        lines += [
            "",
            f"largest harness: {reuse['largest']} at {reuse['share']:.1%} of collection time",
            (
                f"selective-reuse saving: {reuse['saving']:.1%} "
                f"({verdict} the {SELECTIVE_REUSE_BAR:.0%} bar)"
            ),
            "",
            "One machine cannot settle this: the figure is a property of how your history is",
            "distributed across harnesses, not of the product. A store dominated by one harness",
            "reports a low saving; a balanced multi-harness store reports a high one. If you run",
            "several harnesses, the share above is worth reporting on DRC-4080.",
        ]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--window-hours", type=float, default=24.0)
    parser.add_argument("--profile", action="store_true", help="cProfile one collect by function")
    args = parser.parse_args(argv[1:])

    if str(SKILL_DIR) not in sys.path:
        sys.path.insert(0, str(SKILL_DIR))
    # Deferred on purpose: sys.path has to carry SKILL_DIR before the runtime
    # resolves, and keeping it out of module scope also lets measure() and
    # format_report() be imported without the runtime tree present.
    from cargento_runtime import cli  # noqa: PLC0415

    # build_runtime freezes config and state with no side effects, and takes the
    # same namespace shape the CLI parses. usage_fetch_enabled is off here on
    # purpose: a benchmark must never make an outbound vendor quota request, and
    # a fetch would pollute the timing besides.
    runtime_args = argparse.Namespace(
        port=4553,
        window_hours=args.window_hours,
        no_spacedock=False,
        no_usage=True,
    )
    config, state = cli.build_runtime(runtime_args, started=time.time())
    # build_application, not Application(...): the constructor also requires the
    # harness registry and three injected sinks, and the CLI is what assembles
    # them. The no-op sink keeps store diagnostics out of the report.
    app = cli.build_application(
        config,
        state,
        clock=time.time,
        diagnostic_sink=lambda _message: None,
    )
    if args.profile:
        profiler = cProfile.Profile()
        profiler.enable()
        app.collect(show_all=False)
        profiler.disable()
        pstats.Stats(profiler).sort_stats("cumulative").print_stats(25)
        return 0
    print(format_report(measure(app, repeat=args.repeat)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
