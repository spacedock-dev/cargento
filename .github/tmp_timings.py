"""TEMPORARY probe — remove before merge.

Runs the dashboard suite recording per-test wall time, and prints the slowest
tests plus a per-module total. Exists to attribute the macOS/Ubuntu gap to
specific tests rather than guess at it from a wall of progress dots.
"""

import collections
import platform
import re
import subprocess
import sys
import time
import unittest

CALLS: collections.Counter = collections.Counter()
SPENT: collections.Counter = collections.Counter()
_run = subprocess.run


def _key(args):
    if not isinstance(args, (list, tuple)):
        return str(args)[:60]
    import os.path

    parts = [os.path.basename(str(a)) for a in args]
    return (parts[0] + " " + " ".join(p for p in parts[1:3])) [:70]


def run(*a, **kw):
    t0 = time.perf_counter()
    try:
        return _run(*a, **kw)
    finally:
        k = _key(a[0] if a else kw.get("args"))
        SPENT[k] += time.perf_counter() - t0
        CALLS[k] += 1


subprocess.run = run


class TimingResult(unittest.TextTestResult):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.timings = []

    def startTest(self, test):
        self._t0 = time.perf_counter()
        super().startTest(test)

    def stopTest(self, test):
        super().stopTest(test)
        self.timings.append((time.perf_counter() - self._t0, str(test)))


suite = unittest.TestLoader().discover("cargento/skills/cargento/tests", top_level_dir=".")
runner = unittest.TextTestRunner(verbosity=0, resultclass=TimingResult)
started = time.perf_counter()
result = runner.run(suite)
wall = time.perf_counter() - started

out = sys.stderr
print(f"\n===== {platform.platform()} / {platform.machine()} =====", file=out)
print(f"wall {wall:.1f}s over {result.testsRun} tests", file=out)

print("\n----- 40 slowest tests -----", file=out)
for d, n in sorted(result.timings, reverse=True)[:40]:
    print(f"{d:7.2f}s  {n}", file=out)

mod, cnt = collections.Counter(), collections.Counter()
for d, n in result.timings:
    m = re.search(r"tests\.(\w+)\.", n)
    k = m.group(1) if m else n
    mod[k] += d
    cnt[k] += 1
print("\n----- per module -----", file=out)
for k, v in mod.most_common(25):
    print(f"{v:8.1f}s  n={cnt[k]:5d}  {k}", file=out)

print(
    f"\n----- subprocess.run: {sum(SPENT.values()):.1f}s over {sum(CALLS.values())} spawns -----",
    file=out,
)
for k, v in SPENT.most_common(20):
    print(f"{v:8.2f}s  n={CALLS[k]:4d}  {k}", file=out)
out.flush()
