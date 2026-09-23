#!/usr/bin/env python3
"""Run a unittest discovery across worker processes, with unittest's own result.

The CI quality gate ran the dashboard suite single-process on multi-core
runners, six times per pull request. This runner keeps unittest's discovery,
fixtures and verdict, and spreads the work:

- Every worker repeats the exact ``discover`` call the serial command makes.
  That is load-bearing, not tidiness: 29 test modules never import
  ``tests/support.py`` and get their temporary ``HOME`` and ``CARGENTO_HOME``
  only because discovery imports it first. A worker that imported just its
  own modules would run those against the developer's real home.
- The unit of work is a whole test class, so ``setUpClass`` keeps its meaning.
  Classes go into one queue, largest first, and each worker pulls until it is
  empty. Measured 2026-09-23: 131s serial, 33.8s with four workers, with the
  same 3705 tests and verdict. A timings file was tried and gained 0.2s at four
  workers, so the queue orders on test count alone and nothing goes stale.
- Workers are started with ``spawn`` everywhere, which is what Windows does
  anyway, so a pass on Linux says something about the other two.
- ``--coverage`` starts coverage inside each worker with a data suffix; run
  ``coverage combine`` afterwards. Coverage is imported only when asked for,
  because the runtime floor installs no coverage.

``setUpModule`` runs once per worker that receives a class from that module,
rather than once per module. One module defines it, to start and stop a log
patch, which is indifferent to that.

Usage mirrors ``python -m unittest discover``::

    python scripts/run_tests.py -s cargento/skills/cargento/tests -t .
    python scripts/run_tests.py -s scripts/tests -t scripts/tests -j 4 --coverage
"""

from __future__ import annotations

import argparse
import multiprocessing
import os
import queue
import sys
import time
import traceback
import unittest
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator
    from multiprocessing.queues import Queue

# How long the parent waits on the result queue before checking whether its
# workers are still alive. A worker that dies without a word is reported as an
# error on every class it never finished, never waited on forever.
POLL_SECONDS = 5.0
JOIN_SECONDS = 30.0


def iter_tests(suite: unittest.TestSuite) -> Iterator[unittest.TestCase]:
    """Yield every test case in a nested suite, in discovery order."""
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from iter_tests(item)
        else:
            yield item


def unit_of(test: unittest.TestCase) -> str:
    """Name the class a test belongs to: the runner's unit of work."""
    kind = type(test)
    return f"{kind.__module__}.{kind.__qualname__}"


def discover(start: str, top: str | None, pattern: str) -> dict[str, list[unittest.TestCase]]:
    """Discover like ``unittest discover`` and group the cases by class."""
    suite = unittest.TestLoader().discover(start, pattern=pattern, top_level_dir=top)
    units: dict[str, list[unittest.TestCase]] = {}
    for test in iter_tests(suite):
        units.setdefault(unit_of(test), []).append(test)
    return units


def summarise(unit: str, result: unittest.TestResult) -> dict[str, Any]:
    """Reduce a result to picklable strings the parent can merge and print."""
    return {
        "unit": unit,
        "run": result.testsRun,
        "failures": [(str(test), text) for test, text in result.failures],
        "errors": [(str(test), text) for test, text in result.errors],
        "skipped": [(str(test), text) for test, text in result.skipped],
        "expected": [(str(test), text) for test, text in result.expectedFailures],
        "unexpected": [str(test) for test in result.unexpectedSuccesses],
    }


def worker(
    index: int, config: dict[str, Any], tasks: Queue[str | None], results: Queue[tuple[Any, ...]]
) -> None:
    """Run classes from ``tasks`` until the sentinel, reporting each one."""
    cov = None
    if config["coverage"]:
        import coverage  # noqa: PLC0415 - optional, and absent on the runtime floor

        cov = coverage.Coverage(data_suffix=True)
        cov.start()
    try:
        units = discover(config["start"], config["top"], config["pattern"])
        while (unit := tasks.get()) is not None:
            result = unittest.TestResult()
            try:
                # A fresh result makes this a top-level run, so TestSuite opens
                # and closes the class and module fixtures itself.
                unittest.TestSuite(units.get(unit, []))(result)
            except BaseException:  # noqa: BLE001 - report a unit, never lose it
                result.errors.append(
                    (unittest.FunctionTestCase(lambda: None), traceback.format_exc())
                )
            results.put(("unit", index, summarise(unit, result)))
    except BaseException:  # noqa: BLE001 - a crashed worker is a reported error
        results.put(("crash", index, traceback.format_exc()))
    finally:
        if cov is not None:
            cov.stop()
            cov.save()
        results.put(("done", index))


def order_units(units: dict[str, list[unittest.TestCase]]) -> list[str]:
    """Largest class first, so the long ones start early and the queue balances."""
    return sorted(units, key=lambda unit: (-len(units[unit]), unit))


def report(total: dict[str, Any], elapsed: float, jobs: int) -> bool:
    """Print unittest's closing report to stderr and return the verdict."""
    out = sys.stderr
    out.write("\n")
    for flavour, key in (("ERROR", "errors"), ("FAIL", "failures")):
        for name, text in total[key]:
            out.write(f"{'=' * 70}\n{flavour}: {name}\n{'-' * 70}\n{text}\n")
    out.write(f"{'-' * 70}\nRan {total['run']} tests in {elapsed:.3f}s ({jobs} workers)\n\n")
    extras = [
        f"{label}={len(total[key])}"
        for label, key in (
            ("failures", "failures"),
            ("errors", "errors"),
            ("skipped", "skipped"),
            ("expected failures", "expected"),
            ("unexpected successes", "unexpected"),
        )
        if total[key]
    ]
    ok = not (total["failures"] or total["errors"] or total["unexpected"]) and total["run"] > 0
    out.write(("OK" if ok else "FAILED") + (f" ({', '.join(extras)})" if extras else "") + "\n")
    return ok


def collect(results: Queue[tuple[Any, ...]], procs: list[Any]) -> tuple[dict[str, Any], set[str]]:
    """Merge worker reports until every worker is done, or every worker is gone."""
    total: dict[str, Any] = {
        "run": 0,
        "failures": [],
        "errors": [],
        "skipped": [],
        "expected": [],
        "unexpected": [],
    }
    seen: set[str] = set()
    done = 0
    while done < len(procs):
        try:
            message = results.get(timeout=POLL_SECONDS)
        except queue.Empty:
            if not any(proc.is_alive() for proc in procs):
                break
            continue
        if message[0] == "unit":
            summary = message[2]
            seen.add(summary["unit"])
            for key in total:
                total[key] += summary[key]
            sys.stderr.write("F" if summary["failures"] or summary["errors"] else ".")
            sys.stderr.flush()
        elif message[0] == "crash":
            total["errors"].append((f"worker {message[1]}", message[2]))
        else:
            done += 1
    return total, seen


def run(start: str, top: str | None, pattern: str, jobs: int, *, coverage: bool) -> bool:
    """Discover, fan out across ``jobs`` workers, merge, report, return the verdict."""
    started = time.perf_counter()
    units = discover(start, top, pattern)
    order = order_units(units)
    jobs = max(1, min(jobs, len(order)))
    context = multiprocessing.get_context("spawn")
    tasks: Queue[str | None] = context.Queue()
    results: Queue[tuple[Any, ...]] = context.Queue()
    for unit in order:
        tasks.put(unit)
    for _ in range(jobs):
        tasks.put(None)
    config = {"start": start, "top": top, "pattern": pattern, "coverage": coverage}
    procs = [
        context.Process(target=worker, args=(index, config, tasks, results))
        for index in range(jobs)
    ]
    for proc in procs:
        proc.start()

    total, seen = collect(results, procs)
    for proc in procs:
        proc.join(timeout=JOIN_SECONDS)
    total["errors"].extend(
        (unit, "the worker exited before reporting this class")
        for unit in order
        if unit not in seen
    )
    total["errors"].extend(
        (f"worker pid {proc.pid}", f"exit code {proc.exitcode}")
        for proc in procs
        if proc.exitcode not in (0, None)
    )
    return report(total, time.perf_counter() - started, jobs)


def main(argv: list[str] | None = None) -> int:
    """Parse ``unittest discover``-style arguments and run."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-s", "--start-directory", dest="start", default=".")
    parser.add_argument("-t", "--top-level-directory", dest="top", default=None)
    parser.add_argument("-p", "--pattern", default="test*.py")
    parser.add_argument(
        "-j", "--jobs", type=int, default=os.cpu_count() or 2, help="worker processes"
    )
    parser.add_argument("--coverage", action="store_true", help="record coverage in each worker")
    args = parser.parse_args(argv)
    if args.top:
        sys.path.insert(0, os.path.abspath(args.top))
    ok = run(args.start, args.top, args.pattern, args.jobs, coverage=args.coverage)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
