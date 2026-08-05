#!/usr/bin/env python3
"""Measure how long an event takes to reach a published revision.

`bench_collect.py` measures what a collection costs. This measures something the
user actually waits for: the gap between an adapter posting an event and a
connected dashboard being told there is a new revision to fetch.

The question it exists to settle is whether the collection floor is worth
engineering around. The design says a matched `input_requested` should publish
immediately; what ships publishes at the next allowed collection instant, which
is `collect_memo_sec` in the worst case. Removing that means retaining a live
collection instead of the bytes retained today, which is a real refactor. So:
measure first, decide second.

Three latencies, because they are the three the trade depends on:

    ordinary    a store_changed, which waits out the coalescing window
    urgent      an input_requested, which is exempt from the window
    floored     the same urgent event arriving just after a collection, so the
                floor is the whole wait and the worst case is visible

Run:

    python3 scripts/bench_event_latency.py            # 20 samples per case
    python3 scripts/bench_event_latency.py --samples 50

The application is built the way the CLI builds one, so a collection really does
read this machine's stores. What is being measured is still the scheduling, not
the scan: the three cases differ only in when the event arrives relative to the
floor, so the scan cost is common to all three and cancels out of the comparison.
`bench_collect.py` is what measures the scan itself.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "cargento" / "skills" / "cargento"

SESSION = "abcdef12-3456-7890-abcd-ef1234567890"


def _envelope(event: str) -> dict[str, Any]:
    return {"v": 1, "event": event, "session_id": SESSION}


def _coordinator() -> tuple[Any, Any]:
    """An application and a coordinator over it, built the way the CLI builds one.

    Imported here rather than at module scope for the reason `bench_collect.py`
    does the same: `sys.path` has to carry the skill directory before the runtime
    resolves. `no_usage` is on so a benchmark can never make an outbound vendor
    request, which would pollute the timing as well as the network.
    """
    if str(SKILL_DIR) not in sys.path:
        sys.path.insert(0, str(SKILL_DIR))
    from cargento_runtime import cli, observation  # noqa: PLC0415

    runtime_args = argparse.Namespace(
        port=4553, window_hours=24.0, no_spacedock=False, no_usage=True
    )
    config, state = cli.build_runtime(runtime_args, started=time.time())
    app = cli.build_application(
        config, state, clock=time.time, diagnostic_sink=lambda _message: None
    )
    return app, observation.Observation(app, diagnostic_sink=lambda _message: None)


def _config() -> Any:
    return _coordinator()[0].config


def _wait_for_publish(app: Any, deadline: float) -> float | None:
    """Seconds until the next publish, or None if none arrived before `deadline`.

    Polled rather than hooked, because a hook would change the very scheduling
    being measured. The poll interval is far below the smallest wait in play.
    """
    key = (app.config.window_hours, False)
    before = app.snapshot.current(key)
    start = time.perf_counter()
    while time.perf_counter() - start < deadline:
        current = app.snapshot.current(key)
        if current is not None and (before is None or current[0] != before[0]):
            return time.perf_counter() - start
        time.sleep(0.002)
    return None


def sample(case: str) -> float | None:
    """One end-to-end latency for `case`, in seconds."""
    app, coordinator = _coordinator()
    # A row must exist for the overlay to attach to, and the floor must be open,
    # so prime with one collection before timing anything.
    app.collect_json(show_all=False)
    coordinator.start()
    try:
        if case == "floored":
            # Arrive immediately after a collection, so the floor is the whole
            # wait. This is the worst case the design note argues about.
            coordinator.submit("claude", _envelope("input_requested"))
            return _wait_for_publish(app, deadline=10.0)
        event = "input_requested" if case == "urgent" else "store_changed"
        # Open the floor first: without this every case measures the floor and the
        # comparison between ordinary and urgent says nothing.
        time.sleep(app.config.collect_memo_sec + 0.05)
        coordinator.submit("claude", _envelope(event))
        return _wait_for_publish(app, deadline=10.0)
    finally:
        coordinator.stop()


def report(samples: int) -> str:
    config = _config()
    out: list[str] = [
        f"Event to published revision, {samples} samples per case.",
        "",
        f"  collect_memo_sec    {config.collect_memo_sec}",
        f"  event_coalesce_sec  {config.event_coalesce_sec}",
        "",
        f"  {'case':10} {'p50':>9} {'p95':>9} {'max':>9}  {'n':>4}",
    ]
    for case in ("ordinary", "urgent", "floored"):
        taken = [value for _ in range(samples) if (value := sample(case)) is not None]
        if not taken:
            out.append(f"  {case:10} {'no publish observed':>30}")
            continue
        taken.sort()

        def pct(fraction: float, values: list[float] = taken) -> float:
            return values[min(len(values) - 1, int(len(values) * fraction))]

        out.append(
            f"  {case:10} {statistics.median(taken) * 1000:8.1f}ms "
            f"{pct(0.95) * 1000:8.1f}ms {taken[-1] * 1000:8.1f}ms  {len(taken):4}"
        )
    out += [
        "",
        "ordinary waits out the coalescing window; urgent is exempt from it;",
        "floored arrives just after a collection, so the floor is the whole wait.",
        "The gap between urgent and floored is what an overlay-only republication",
        "would remove, and the only number that justifies building it.",
    ]
    return "\n".join(out)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=20, help="samples per case")
    args = parser.parse_args(argv[1:])
    print(report(max(1, args.samples)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
