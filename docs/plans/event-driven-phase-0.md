# Event-driven session observation, Phase 0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce the measurements that gate DRC-4080, make the Claude collector cheap enough that those measurements mean something, and close the two quota opt-out defects that must be fixed before any later phase can claim the security contract is preserved.

**Architecture:** No new subsystem. Phase 0 is a repeatable benchmark script under `scripts/`, three behaviour-preserving changes inside `collectors/claude.py` plus one new bounded cache on `RuntimeState`, and two small correctness fixes in `lifecycle.py` and `quota.py`. Nothing in this phase adds an event path, a snapshot, or an HTTP endpoint.

**Tech Stack:** Python 3.11 standard library only. `unittest` for tests, `coverage` for the ratchet, `ruff` and `mypy --strict` for the gate.

**Scope note.** This plan covers Phase 0 only. Phase 1 (materialized snapshot and SSE) gets its own plan, written after Task 7 lands, because two of its inputs are Phase 0 outputs: the direct-GET freshness threshold the design states as "2.5-second-or-better" has to be chosen against measured post-fix collection time, and the selective-reuse gate decides whether Phase 1's publish protocol is built for per-harness merges or for one full aggregate per floor. Writing those tasks now would mean guessing both.

**Design owner:** [`event-driven-session-observation.md`](event-driven-session-observation.md). This plan implements its Phase 0 section and must not restate its rationale.

## Global Constraints

- Standard library only. No dependency may be added, ever. Python floor is 3.11, owned by `COMPATIBILITY.md`.
- `ruff check .` with `select = ALL` and `ruff format --check` must pass. Curated ignores live in `pyproject.toml`.
- `mypy` must pass under `--strict`.
- `coverage report` must meet `fail_under = 73` in `pyproject.toml`. The threshold only ratchets up. Never lower it.
- Tests run on Ubuntu, macOS and Windows. Any path, process or filesystem assumption needs an OS guard or a skip.
- Never edit a `version` field in any manifest. The tag-driven Release workflow owns all five, and `version-guard` fails a PR that touches them.
- Every commit uses `git commit -s` for DCO. Commit subject format is `<type>(<scope>): <description>`.
- `docs/plans/*.md` is inside the sync-docs tone gate: no em dashes, en dashes, or curly quotes in this file or any doc you edit.
- New runtime files must not invert R-2, the inward-only dependency rule. `test_runtime_import_graph_matches_the_reviewed_allowlist` enforces it. Phase 0 adds no runtime module, so this constraint should stay untriggered. If you find yourself adding one, stop and revisit the design doc.
- Behaviour-preserving means byte-identical `/api/data` output for the same store contents. Tasks 2 through 4 each prove that with an equivalence test, not by inspection.
- Run the pre-PR suite from `AGENTS.md` before opening the PR. Do not rely on CI to surface failures.

---

### Task 1: Reproducible collection benchmark

The Phase 0 gate needs numbers anyone can regenerate on any machine. Today the only figures are from one developer's laptop, recorded in the design doc as provisional. This task makes them reproducible before any code changes them.

**Files:**
- Create: `scripts/bench_collect.py`
- Create: `scripts/tests/test_bench_collect.py`

**Interfaces:**
- Consumes: `cargento_runtime.cli.build_application(config, state, clock=...)`, `cargento_runtime.config.build_runtime_config`, `cargento_runtime.state.build_runtime_state`.
- Produces: `measure(app, *, repeat: int) -> dict[str, Any]` returning `{"total_ms": float, "per_harness_ms": dict[str, float], "discovery_ms": float, "repeat": int}`, and `format_report(result: dict[str, Any]) -> str`. Task 7 calls `measure` and pastes `format_report` output into the design doc.

**Two signatures to get right, both verified against the source:**

- `Application.__init__` is `(config, state, harnesses, *, native_notifier, popup_notifier, diagnostic_sink, clock=time.time)`. Do not construct it directly. Use `cli.build_application(config, state, clock=time.time)`, which is how both the CLI and `tests/support.build_app` build one.
- `Application.collect` is `collect(self, *, show_all: bool)`. `show_all` is a required keyword and there is no `window_hours` parameter; the window comes from `config.window_hours`. Every call in this task passes `show_all=False`.

- [ ] **Step 1: Write the failing test**

Create `scripts/tests/test_bench_collect.py`:

```python
from __future__ import annotations

import unittest

from scripts import bench_collect


class FakeSpec:
    """HarnessSpec's identity field is `key`, not `name`.

    Verified against aggregate.HarnessSpec, whose fields are: collect, discover,
    key, label, usage, usage_is_fetch.
    """

    def __init__(self, key: str) -> None:
        self.key = key


class FakeApp:
    """Stands in for Application: two harnesses, one slow and one fast."""

    def __init__(self) -> None:
        self.collect_calls = 0

    def collect(self, *, show_all: bool) -> dict[str, object]:
        # Mirrors Application.collect exactly: show_all is keyword-only and
        # required, and there is no window_hours parameter.
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/jaredmscott/repos/recce/cargento && python3 -m unittest scripts.tests.test_bench_collect -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.bench_collect'`.

- [ ] **Step 3: Write minimal implementation**

Create `scripts/bench_collect.py`:

```python
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
import pstats
import statistics
import sys
import time
from typing import Any


def measure(app: Any, *, repeat: int) -> dict[str, Any]:
    """Median wall-clock cost of a full collect, and of each harness inside it.

    Every sample is a real collect against the caller's stores. The per-harness
    figures come from wrapping each registry entry's collector, so they sum to
    the total minus serialization rather than being estimated.
    """
    if repeat < 1:
        raise ValueError("repeat must be at least 1")
    totals: list[float] = []
    per_harness: dict[str, list[float]] = {}
    discovery: list[float] = []
    for _ in range(repeat):
        started = time.perf_counter()
        app.collect(show_all=False)
        totals.append((time.perf_counter() - started) * 1000.0)
    return {
        "total_ms": statistics.median(totals),
        "per_harness_ms": {name: statistics.median(v) for name, v in per_harness.items()},
        "discovery_ms": statistics.median(discovery) if discovery else 0.0,
        "repeat": repeat,
    }


def format_report(result: dict[str, Any]) -> str:
    lines = [
        f"repeat: {result['repeat']}",
        f"total_ms: {result['total_ms']}",
        f"discovery_ms: {result['discovery_ms']}",
    ]
    for name, value in sorted(
        result["per_harness_ms"].items(), key=lambda kv: -float(kv[1])
    ):
        lines.append(f"  {name}: {value} ms")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--window-hours", type=float, default=24.0)
    parser.add_argument("--profile", action="store_true", help="cProfile one collect by function")
    args = parser.parse_args(argv[1:])

    from cargento_runtime import cli

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest scripts.tests.test_bench_collect -v`

Expected: PASS, 3 tests.

- [ ] **Step 5: Fill in the per-harness and discovery timing**

`measure` currently returns empty `per_harness_ms` and a zero `discovery_ms`, so the report is not yet useful. Wrap the registry so each harness is timed separately. `HarnessSpec` identifies a harness by `key`, not `name`. Its full field set, verified against `aggregate.HarnessSpec`, is `collect`, `discover`, `key`, `label`, `usage`, `usage_is_fetch`. A real registry has ten entries, and `app.harnesses` is a tuple.

`HarnessSpec` is declared `@dataclass(frozen=True)` at `aggregate.py:31`, so assigning over `spec.collect` raises `FrozenInstanceError`. Wrap at the registry level instead: build a new tuple with `dataclasses.replace(spec, collect=wrapped, discover=wrapped_discover)` for each entry, assign it to `app.harnesses` for the duration of the measurement, and restore the original tuple in a `finally`.

Add to `measure`, before the sample loop:

```python
    specs = tuple(getattr(app, "harnesses", ()) or ())
    for spec in specs:
        per_harness.setdefault(spec.key, [])
```

Each wrapper records its own duration in milliseconds into `per_harness[spec.key]`, or into `discovery` for `discover`, then delegates to the original callable and returns its result unchanged. A wrapper must not swallow an exception: the per-harness failure boundary lives in `Application.collect` and the benchmark must not change which harnesses fail.

Add two tests: a two-harness fake yields two entries in `per_harness_ms`, and a raising collector still leaves `app.harnesses` identical to the original tuple afterwards.

- [ ] **Step 6: Run the suite and the gate**

Run:
```bash
python3 -m unittest scripts.tests.test_bench_collect -v
ruff check scripts/bench_collect.py scripts/tests/test_bench_collect.py
ruff format --check scripts/bench_collect.py scripts/tests/test_bench_collect.py
mypy
```
Expected: all pass.

- [ ] **Step 7: Record the pre-fix baseline**

Run and keep the output for Task 7:
```bash
python3 scripts/bench_collect.py --repeat 7 | tee /tmp/cargento-bench-pre.txt
python3 scripts/bench_collect.py --profile | head -40 | tee /tmp/cargento-profile-pre.txt
```

This is the "before" side of the comparison Tasks 2 through 4 have to beat. If `total_ms` is already low on this machine because its Claude store is small, say so in Task 7 rather than treating the fix as unnecessary: the cost scales with historical transcript count, not with active sessions.

- [ ] **Step 8: Commit**

```bash
git add scripts/bench_collect.py scripts/tests/test_bench_collect.py
git commit -s -m "test(bench): add a reproducible collection benchmark (DRC-4080)"
```

---

### Task 2: Stop globbing every subagent directory twice

`claude.collect` calls `agent_transcripts(transcript)` at line 236 and then `load_subagents(config, transcript, now)` at line 237, and `load_subagents` calls `agent_transcripts` again internally. Every session prefix therefore pays the subagent glob twice. `agent_files` is genuinely used later, at lines 254 and 392, so the fix is to pass the list in rather than to delete the call.

**Files:**
- Modify: `cargento/skills/cargento/cargento_runtime/collectors/claude.py:96-120` (`load_subagents`) and `:236-237` (the call site)
- Test: `cargento/skills/cargento/tests/test_claude.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `load_subagents(config, transcript, now, *, found: list[tuple[str, float]] | None = None) -> list[dict[str, Any]]`. When `found` is given it is used verbatim and no globbing happens. Task 4 caches what gets passed as `found`.

- [ ] **Step 1: Write the failing test**

Add to `cargento/skills/cargento/tests/test_claude.py`:

```python
class SubagentGlobCostTest(RuntimeTestCase):
    """One subagent scan per session, not two.

    The parent transcript and one fresh subagent transcript are both real files,
    so the test fails if the optimisation changes which subagents are found.
    """

    def test_load_subagents_accepts_a_precomputed_listing(self) -> None:
        config, state = runtime()
        now = time.time()
        with tempfile.TemporaryDirectory() as root:
            parent = os.path.join(root, "abcd1234-session.jsonl")
            Path(parent).write_text("{}\n", encoding="utf-8")
            sess_dir = os.path.join(root, "abcd1234-session")
            os.makedirs(sess_dir)
            child = os.path.join(sess_dir, "agent-worker.jsonl")
            Path(child).write_text("{}\n", encoding="utf-8")

            found = claude_collector.agent_transcripts(parent)
            self.assertTrue(found, "fixture must produce at least one subagent transcript")

            with mock.patch.object(
                claude_collector, "agent_transcripts", side_effect=AssertionError("globbed again")
            ):
                agents = claude_collector.load_subagents(config, parent, now, found=found)

            self.assertEqual([a["label"] for a in agents], ["subagent"])

    def test_precomputed_and_self_scanned_results_are_identical(self) -> None:
        config, state = runtime()
        now = time.time()
        with tempfile.TemporaryDirectory() as root:
            parent = os.path.join(root, "abcd1234-session.jsonl")
            Path(parent).write_text("{}\n", encoding="utf-8")
            sess_dir = os.path.join(root, "abcd1234-session")
            os.makedirs(sess_dir)
            for name in ("agent-a.jsonl", "agent-b.jsonl"):
                Path(os.path.join(sess_dir, name)).write_text("{}\n", encoding="utf-8")

            self.assertEqual(
                claude_collector.load_subagents(config, parent, now),
                claude_collector.load_subagents(
                    config, parent, now, found=claude_collector.agent_transcripts(parent)
                ),
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_claude.SubagentGlobCostTest -v`

Expected: FAIL with `TypeError: load_subagents() got an unexpected keyword argument 'found'`.

- [ ] **Step 3: Write minimal implementation**

In `collectors/claude.py`, change the `load_subagents` signature and its first loop line:

```python
def load_subagents(
    config: RuntimeConfig,
    transcript: str | None,
    now: float,
    *,
    found: list[tuple[str, float]] | None = None,
) -> list[dict[str, Any]]:
    """Running Claude subagents beneath the session directory; fresh mtime =
    running. Covers both layouts in ``SUBAGENT_GLOBS``.

    ``found`` lets a caller that has already listed the directory hand the
    listing over, so one session costs one scan. The collector needs the full
    listing anyway for its parked-parent activity check.
    """
    agents: list[dict[str, Any]] = []
    for fp, mtime in (agent_transcripts(transcript) if found is None else found):
```

Leave the rest of the body unchanged.

- [ ] **Step 4: Update the call site**

At `collectors/claude.py:236-237`, pass the listing through:

```python
        agent_files = agent_transcripts(transcript)
        subagents = load_subagents(config, transcript, now, found=agent_files)
```

- [ ] **Step 5: Run tests to verify they pass**

Run:
```bash
python3 -m unittest cargento.skills.cargento.tests.test_claude -v
```
Expected: PASS, including the pre-existing Claude tests. Those are the equivalence check: if any of them change behaviour, the optimisation is wrong.

- [ ] **Step 6: Prove the collector output is unchanged**

Run the whole suite, not just the Claude module, because `sessions`, `spacedock` and page tests all consume collector output:
```bash
python3 -m unittest discover -s cargento/skills/cargento/tests -t .
```
Expected: PASS with no change in count.

- [ ] **Step 7: Commit**

```bash
git add cargento/skills/cargento/cargento_runtime/collectors/claude.py \
        cargento/skills/cargento/tests/test_claude.py
git commit -s -m "perf(claude): scan each session's subagents once, not twice (DRC-4080)"
```

---

### Task 3: Skip the subagent glob when the session directory is absent

Most historical prefixes have no session directory at all, and `agent_transcripts` still runs every pattern in `SUBAGENT_GLOBS` against a path that does not exist. An `isdir` check replaces two glob syscalls per pattern with one stat.

**Files:**
- Modify: `cargento/skills/cargento/cargento_runtime/collectors/claude.py:77-92` (`agent_transcripts`)
- Test: `cargento/skills/cargento/tests/test_claude.py`

**Interfaces:**
- Consumes: `load_subagents(..., found=...)` from Task 2 (unchanged by this task).
- Produces: no signature change. `agent_transcripts` returns `[]` without globbing when the session directory does not exist.

- [ ] **Step 1: Write the failing test**

Add to `SubagentGlobCostTest` in `test_claude.py`:

```python
    def test_absent_session_directory_is_not_globbed(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            parent = os.path.join(root, "abcd1234-session.jsonl")
            Path(parent).write_text("{}\n", encoding="utf-8")
            # No sibling "abcd1234-session/" directory: the common case for a
            # historical session that never ran a subagent.
            with mock.patch.object(
                claude_collector.runtime_io,
                "glob_under",
                side_effect=AssertionError("globbed a directory that does not exist"),
            ):
                self.assertEqual(claude_collector.agent_transcripts(parent), [])

    def test_present_session_directory_is_still_globbed(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            parent = os.path.join(root, "abcd1234-session.jsonl")
            Path(parent).write_text("{}\n", encoding="utf-8")
            sess_dir = os.path.join(root, "abcd1234-session")
            os.makedirs(sess_dir)
            Path(os.path.join(sess_dir, "agent-a.jsonl")).write_text("{}\n", encoding="utf-8")
            found = claude_collector.agent_transcripts(parent)
            self.assertEqual([os.path.basename(p) for p, _ in found], ["agent-a.jsonl"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_claude.SubagentGlobCostTest -v`

Expected: `test_absent_session_directory_is_not_globbed` FAILS with `AssertionError: globbed a directory that does not exist`.

- [ ] **Step 3: Write minimal implementation**

In `agent_transcripts`, after computing `sess_dir` and before the pattern loop:

```python
    sess_dir = os.path.join(
        os.path.dirname(transcript), os.path.basename(transcript)[: -len(".jsonl")]
    )
    # Most historical prefixes never ran a subagent, so the directory is absent.
    # One stat is cheaper than running every SUBAGENT_GLOBS pattern against a
    # path that cannot match.
    if not os.path.isdir(sess_dir):
        return []
    found: list[tuple[str, float]] = []
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
python3 -m unittest cargento.skills.cargento.tests.test_claude -v
python3 -m unittest discover -s cargento/skills/cargento/tests -t .
```
Expected: PASS.

- [ ] **Step 5: Confirm the improvement is real**

Run: `python3 scripts/bench_collect.py --repeat 7`

Compare `total_ms` against `/tmp/cargento-bench-pre.txt`. Record the delta for Task 7. If there is no measurable change, the machine's Claude store has few historical prefixes; note that rather than reverting, and say so in Task 7.

- [ ] **Step 6: Commit**

```bash
git add cargento/skills/cargento/cargento_runtime/collectors/claude.py \
        cargento/skills/cargento/tests/test_claude.py
git commit -s -m "perf(claude): skip the subagent glob when no session dir exists (DRC-4080)"
```

---

### Task 4: Cache subagent listings on session-directory mtime

Tasks 2 and 3 cut the constant factor. This one cuts the work itself: a session directory whose mtime has not moved cannot have gained or lost a transcript, so its listing can be reused across collections. The parked-parent case makes this delicate, so the cache key is the directory mtime and nothing else.

**Files:**
- Modify: `cargento/skills/cargento/cargento_runtime/state.py:41` area (add one cache field)
- Modify: `cargento/skills/cargento/cargento_runtime/collectors/claude.py:77-92` (`agent_transcripts`)
- Test: `cargento/skills/cargento/tests/test_claude.py`

**Interfaces:**
- Consumes: `agent_transcripts` behaviour from Task 3.
- Produces: `agent_transcripts(transcript, *, config: RuntimeConfig | None = None, state: RuntimeState | None = None) -> list[tuple[str, float]]`. With both `config` and `state` supplied it consults and fills `state.claude_subagent_cache`. With either omitted it behaves exactly as in Task 3, so existing callers and tests keep working.

- [ ] **Step 1: Write the failing test**

Add to `test_claude.py`:

```python
class SubagentListingCacheTest(RuntimeTestCase):
    """A session directory with an unchanged mtime is listed once.

    Keyed on directory mtime rather than on a freshness window, because a
    workflow that runs for hours parks its parent transcript and keeps writing
    only to subagent files. Dropping old prefixes would lose those sessions.
    """

    def _fixture(self, root: str, *names: str) -> str:
        parent = os.path.join(root, "abcd1234-session.jsonl")
        Path(parent).write_text("{}\n", encoding="utf-8")
        sess_dir = os.path.join(root, "abcd1234-session")
        os.makedirs(sess_dir, exist_ok=True)
        for name in names:
            Path(os.path.join(sess_dir, name)).write_text("{}\n", encoding="utf-8")
        return parent

    def test_second_call_with_unchanged_mtime_does_not_glob(self) -> None:
        config, state = runtime()
        with tempfile.TemporaryDirectory() as root:
            parent = self._fixture(root, "agent-a.jsonl")
            first = claude_collector.agent_transcripts(parent, config=config, state=state)
            self.assertTrue(first)
            with mock.patch.object(
                claude_collector.runtime_io,
                "glob_under",
                side_effect=AssertionError("re-globbed an unchanged directory"),
            ):
                second = claude_collector.agent_transcripts(parent, config=config, state=state)
            self.assertEqual(first, second)

    def test_a_new_subagent_file_invalidates_the_entry(self) -> None:
        config, state = runtime()
        with tempfile.TemporaryDirectory() as root:
            parent = self._fixture(root, "agent-a.jsonl")
            first = claude_collector.agent_transcripts(parent, config=config, state=state)
            sess_dir = os.path.join(root, "abcd1234-session")
            # Force a distinct directory mtime: a coarse filesystem timestamp
            # would otherwise make this test pass or fail on timing alone.
            Path(os.path.join(sess_dir, "agent-b.jsonl")).write_text("{}\n", encoding="utf-8")
            os.utime(sess_dir, (time.time() + 5, time.time() + 5))
            second = claude_collector.agent_transcripts(parent, config=config, state=state)
            self.assertEqual(len(first), 1)
            self.assertEqual(len(second), 2)

    def test_without_state_the_behaviour_is_uncached(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            parent = self._fixture(root, "agent-a.jsonl")
            self.assertEqual(
                claude_collector.agent_transcripts(parent),
                claude_collector.agent_transcripts(parent),
            )

    def test_a_parked_parent_keeps_its_subagent_activity(self) -> None:
        """The regression this cache design exists to avoid.

        The parent transcript is hours old; only the subagent file is fresh. The
        session must still report its subagent activity.
        """
        config, state = runtime()
        with tempfile.TemporaryDirectory() as root:
            parent = self._fixture(root, "agent-a.jsonl")
            stale = time.time() - 6 * 3600
            os.utime(parent, (stale, stale))
            found = claude_collector.agent_transcripts(parent, config=config, state=state)
            self.assertEqual(len(found), 1)
            self.assertGreater(found[0][1], stale)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_claude.SubagentListingCacheTest -v`

Expected: FAIL with `TypeError: agent_transcripts() got an unexpected keyword argument 'config'`.

- [ ] **Step 3: Add the cache field**

In `cargento_runtime/state.py`, beside the other Claude caches (near `claude_user_event_cache`):

```python
    # sess_dir -> (directory mtime, listing). A directory whose mtime has not
    # moved cannot have gained or lost a transcript, and keying on mtime rather
    # than on a freshness window keeps a parked parent's subagents visible.
    claude_subagent_cache: dict[str, tuple[float, list[tuple[str, float]]]] = field(
        default_factory=dict
    )
```

- [ ] **Step 4: Write the implementation**

Rewrite `agent_transcripts` in `collectors/claude.py`:

```python
def agent_transcripts(
    transcript: str | None,
    *,
    config: RuntimeConfig | None = None,
    state: RuntimeState | None = None,
) -> list[tuple[str, float]]:
    """(path, mtime) for every subagent transcript belonging to a session.

    With ``config`` and ``state`` the listing is memoised on the session
    directory's mtime, which is what makes a large history cheap. Without them
    the scan is unmemoised, so callers outside a runtime keep working.
    """
    if not transcript:
        return []
    sess_dir = os.path.join(
        os.path.dirname(transcript), os.path.basename(transcript)[: -len(".jsonl")]
    )
    # Most historical prefixes never ran a subagent, so the directory is absent.
    # One stat is cheaper than running every SUBAGENT_GLOBS pattern against a
    # path that cannot match.
    try:
        dir_mtime = os.stat(sess_dir).st_mtime
    except OSError:
        return []  # absent, or a file where a directory was expected
    if not os.path.isdir(sess_dir):
        return []
    cache = None if state is None or config is None else state.claude_subagent_cache
    if cache is not None:
        hit = cache.get(sess_dir)
        if hit is not None and hit[0] == dir_mtime:
            return list(hit[1])
    found: list[tuple[str, float]] = []
    for pattern in SUBAGENT_GLOBS:
        for fp in runtime_io.glob_under(sess_dir, *pattern):
            try:
                found.append((fp, os.path.getmtime(fp)))
            except OSError:
                continue  # transcript rotated/deleted between glob and stat
    if cache is not None and config is not None:
        runtime_state.bounded_put(
            cache, sess_dir, (dir_mtime, list(found)), limit=config.max_cache_entries
        )
    return found
```

Add the imports this needs if they are not already present: `from cargento_runtime import state as runtime_state` and the `RuntimeState` type under `TYPE_CHECKING`. Check the existing import block first and match its style.

The returned list is copied on both the hit and the store path so a caller cannot mutate the cached listing.

- [ ] **Step 5: Thread config and state through the call site**

At `collectors/claude.py:236`:

```python
        agent_files = agent_transcripts(transcript, config=config, state=state)
```

Confirm `state` is in scope in `collect`. If it is not, read the function signature and thread it from the collector's arguments rather than reaching for a global.

- [ ] **Step 6: Run tests to verify they pass**

Run:
```bash
python3 -m unittest cargento.skills.cargento.tests.test_claude -v
python3 -m unittest discover -s cargento/skills/cargento/tests -t .
```
Expected: PASS.

- [ ] **Step 7: Verify the cache is bounded and typed**

Run:
```bash
mypy
ruff check cargento/skills/cargento/cargento_runtime/
```
Expected: PASS. `mypy --strict` is what catches a wrong cache value shape here.

- [ ] **Step 8: Measure**

Run: `python3 scripts/bench_collect.py --repeat 7 | tee /tmp/cargento-bench-post.txt`

Expected: `claude` per-harness time materially below the pre-fix figure on a machine with real history. Keep the file for Task 7.

- [ ] **Step 9: Commit**

```bash
git add cargento/skills/cargento/cargento_runtime/state.py \
        cargento/skills/cargento/cargento_runtime/collectors/claude.py \
        cargento/skills/cargento/tests/test_claude.py
git commit -s -m "perf(claude): memoise subagent listings on session-dir mtime (DRC-4080)"
```

---

### Task 5: Carry `--no-usage` through the Windows respawn

`lifecycle.spawn_argv` rebuilds the child's argv from the parsed namespace and forwards `--port`, `--window-hours` and `--no-spacedock`, but not `--no-usage`. On Windows, which has no fork and so always respawns, `server.py --daemon --no-usage` produces a child that fetches quota. `SECURITY.md` states that with the feature off nothing is fetched, so this is a published-contract violation.

**Files:**
- Modify: `cargento/skills/cargento/cargento_runtime/lifecycle.py:515-539` (`spawn_argv`)
- Test: `cargento/skills/cargento/tests/test_lifecycle.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: no signature change. `spawn_argv` output now contains `--no-usage` when `args.no_usage` is true.

- [ ] **Step 1: Write the failing test**

Add to `cargento/skills/cargento/tests/test_lifecycle.py`:

```python
class SpawnArgvOptOutTest(unittest.TestCase):
    """Every opt-out the parent was given has to reach the respawned child.

    Windows has no fork, so the daemon is always a respawn. A flag dropped here
    is a flag silently ignored for every Windows daemon user.
    """

    def _args(self, **overrides: object) -> argparse.Namespace:
        base = {
            "port": 4553,
            "window_hours": 24.0,
            "no_spacedock": False,
            "no_usage": False,
        }
        base.update(overrides)
        return argparse.Namespace(**base)

    def test_no_usage_is_forwarded(self) -> None:
        config = support.cfg()
        argv = lifecycle.spawn_argv(config, self._args(no_usage=True))
        self.assertIn("--no-usage", argv)

    def test_no_usage_is_absent_when_not_requested(self) -> None:
        config = support.cfg()
        argv = lifecycle.spawn_argv(config, self._args(no_usage=False))
        self.assertNotIn("--no-usage", argv)

    def test_daemon_is_never_forwarded(self) -> None:
        """Forwarding --daemon would respawn forever."""
        config = support.cfg()
        argv = lifecycle.spawn_argv(config, self._args(no_usage=True))
        self.assertNotIn("--daemon", argv)
```

Import `argparse` and `lifecycle` at the top of the module if they are not already imported, and match how the existing tests obtain a config.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_lifecycle.SpawnArgvOptOutTest -v`

Expected: `test_no_usage_is_forwarded` FAILS with `AssertionError: '--no-usage' not found in [...]`.

- [ ] **Step 3: Write minimal implementation**

In `spawn_argv`, beside the existing `no_spacedock` branch:

```python
    if args.no_spacedock:
        argv.append("--no-spacedock")
    if args.no_usage:
        argv.append("--no-usage")
    return argv
```

Update the docstring's promise so the next reader knows the rule: every opt-out is forwarded, `--daemon` deliberately is not.

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
python3 -m unittest cargento.skills.cargento.tests.test_lifecycle -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cargento/skills/cargento/cargento_runtime/lifecycle.py \
        cargento/skills/cargento/tests/test_lifecycle.py
git commit -s -m "fix(lifecycle): forward --no-usage to the respawned daemon (DRC-4080)"
```

---

### Task 6: Discard pushed quota when server-side usage is disabled

`quota.receive_statusline` shapes and stores whatever `POST /api/usage` delivers, without consulting `config.usage_fetch_enabled`. So `--no-usage` suppresses outbound fetching but not pushed retention, and a user who turned usage off still gets a quota band from Antigravity's status line. The lifecycle fields in that payload stay useful as a dirty signal, so the fix drops quota before storage rather than rejecting the request.

**Files:**
- Modify: `cargento/skills/cargento/cargento_runtime/quota.py` (`receive_statusline`)
- Test: `cargento/skills/cargento/tests/test_quota.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `receive_statusline(state, payload, *, now, config: RuntimeConfig | None = None) -> dict[str, Any]`. When `config` is supplied and `config.usage_fetch_enabled` is false, the stored entry list is empty and the response reports `usage: 0`. The endpoint keeps returning 200 so the harness's status line never sees an error.

- [ ] **Step 1: Write the failing test**

Add to `cargento/skills/cargento/tests/test_quota.py`:

```python
class PushedReceiptOptOutTest(RuntimeTestCase):
    """--no-usage means no quota is retained, pushed or fetched.

    SECURITY.md publishes that with the feature off nothing is fetched or
    retained. A pushed receipt is a second way in, so it needs the same gate.
    """

    def _payload(self) -> dict[str, Any]:
        return {
            "quota": {
                "gemini-2.5-pro": {
                    "remaining_fraction": 0.42,
                    "reset_in_seconds": 3600,
                }
            }
        }

    def test_a_receipt_is_stored_when_usage_is_enabled(self) -> None:
        config = support.make_config(usage_fetch_enabled=True)
        state = support.state_of()
        response = quota.receive_statusline(
            state, self._payload(), now=1000.0, config=config
        )
        self.assertGreater(response["usage"], 0)
        self.assertTrue(state.usage_receipts["antigravity"]["entries"])

    def test_quota_is_dropped_before_storage_when_usage_is_disabled(self) -> None:
        config = support.make_config(usage_fetch_enabled=False)
        state = support.state_of()
        response = quota.receive_statusline(
            state, self._payload(), now=1000.0, config=config
        )
        self.assertEqual(response["usage"], 0)
        self.assertEqual(state.usage_receipts["antigravity"]["entries"], [])

    def test_the_endpoint_still_reports_success_when_disabled(self) -> None:
        """A status-line command must never see an error from Cargento."""
        config = support.make_config(usage_fetch_enabled=False)
        state = support.state_of()
        response = quota.receive_statusline(
            state, self._payload(), now=1000.0, config=config
        )
        self.assertTrue(response["ok"])
```

Read the top of `test_quota.py` first and match how it builds a config and state. If `support.make_config` does not accept `usage_fetch_enabled`, use `support.config_patch` instead.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_quota.PushedReceiptOptOutTest -v`

Expected: `test_quota_is_dropped_before_storage_when_usage_is_disabled` FAILS, because the entries list is populated.

- [ ] **Step 3: Write minimal implementation**

In `quota.py`:

```python
def receive_statusline(
    state: RuntimeState,
    payload: dict[str, Any],
    *,
    now: float,
    config: RuntimeConfig | None = None,
) -> dict[str, Any]:
    """Store a pushed status-line receipt. Returns the endpoint's wire response.

    Storing an empty entry list on an unusable payload is deliberate: it stamps
    the arrival, so a harness that stops reporting quota goes stale and drops
    out of the band rather than showing whatever it last said forever.

    With server-side usage disabled the quota fields are dropped before storage,
    not rejected at the door: SECURITY.md promises nothing is retained with the
    feature off, and the response still reports success so a harness's status
    line never surfaces a Cargento error.
    """
    enabled = True if config is None else config.usage_fetch_enabled
    entries = shape_statusline(payload, now) if enabled else []
    with state.usage_fetch_lock:
        state.usage_receipts["antigravity"] = {"ts": now, "entries": entries}
    return {"ok": True, "usage": len(entries)}
```

- [ ] **Step 4: Pass the config from the endpoint**

In `http_api.py`, in `_usage_receipt`, add the argument:

```python
        response = quota.receive_statusline(
            application.state,
            payload,
            now=application.clock(),
            config=application.config,
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run:
```bash
python3 -m unittest cargento.skills.cargento.tests.test_quota cargento.skills.cargento.tests.test_http_api -v
```
Expected: PASS.

- [ ] **Step 6: Add the endpoint-level test**

A unit test on `receive_statusline` does not prove the endpoint wires the config through. Add one to `test_http_api.py` that posts to `/api/usage` on an application built with `usage_fetch_enabled=False` and asserts the response body reports `usage: 0` and that `state.usage_receipts["antigravity"]["entries"]` is empty. Use the existing `support.make_server` and `support.serve_until_closed` helpers, matching how the other `/api/usage` tests in that module are written.

Run: `python3 -m unittest cargento.skills.cargento.tests.test_http_api -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add cargento/skills/cargento/cargento_runtime/quota.py \
        cargento/skills/cargento/cargento_runtime/http_api.py \
        cargento/skills/cargento/tests/test_quota.py \
        cargento/skills/cargento/tests/test_http_api.py
git commit -s -m "fix(quota): drop pushed quota when server-side usage is off (DRC-4080)"
```

---

### Task 7: Evaluate the gates and record the decision

Phase 0 exists to produce a decision, not just faster code. This task writes the measured numbers into the design doc, replacing the provisional single-machine table, and states which gates passed.

**Files:**
- Modify: `docs/plans/event-driven-session-observation.md` (the Recommendation measurement table and the Phase 0 gate list)
- Modify: `SECURITY.md` (record that the two opt-out defects are fixed, if it describes them as exposures)

**Interfaces:**
- Consumes: `bench_collect.measure` and `format_report` from Task 1; `/tmp/cargento-bench-pre.txt` and `/tmp/cargento-bench-post.txt`.
- Produces: a filled measurement table and an explicit gate verdict that Phase 1's plan depends on.

- [ ] **Step 1: Collect the post-fix numbers on every OS you can reach**

Run on each available platform:
```bash
python3 scripts/bench_collect.py --repeat 7
python3 scripts/bench_collect.py --profile | head -40
```

Record the machine's Claude history size alongside each figure, because the cost scales with it:
```bash
python3 -c "import glob,os;p=os.path.expanduser('~/.claude/projects');print(len(glob.glob(p+'/*/*.jsonl')))"
```

If you can only reach one OS, say so explicitly in the doc rather than presenting one platform's numbers as the matrix.

- [ ] **Step 2: Replace the provisional table**

In `docs/plans/event-driven-session-observation.md`, update the Recommendation measurement table with before and after columns and the transcript count each was taken against. Keep the sentence that these must be reproduced elsewhere only if they still have not been.

Remember the tone gate: no em dashes, en dashes, or curly quotes.

- [ ] **Step 3: Evaluate the selective-reuse gate**

The design states: if per-harness reuse saves less than 25% of post-fix collection time, keep the coordinator but run one full aggregate collection per floor, and do not build the dirty queue.

Compute it from the post-fix per-harness figures: the saving available to per-harness reuse is the total minus the largest single harness, as a fraction of the total. Write the arithmetic into the doc so a reviewer can check it, then state the verdict as one sentence.

- [ ] **Step 4: State the remaining gate verdicts**

For each of the other three gates in the Phase 0 section, write either the measured verdict or an explicit "not yet measured, blocks the phase it gates":

- Coarse probe: mutation corpus false negatives and CPU/IO budget on three OSes. This plan does not build the probe, so this is expected to be unmeasured. Say so.
- Adapter semantics: contract or real-CLI fixtures per transition. Unmeasured until Phase 2.
- Operational rollout: CPU duty, memory, thread ceilings, p95 render latency, missed-event repair rate. Unmeasured until Phase 1 delivers a render path.

Do not mark a gate passed because it was not reached.

- [ ] **Step 5: Run the docs gate**

Run:
```bash
python3 scripts/validate_plugins.py
```
Expected: exit 0.

Then run the tone check. Do not retype its pattern here: copy check (e) verbatim out of
`.claude/skills/sync-docs/SKILL.md`, because the pattern is a list of the characters it bans and
reproducing it inside this file would make this file fail its own check. Expected: `tone clean`.

- [ ] **Step 6: Run the full pre-PR suite**

Run the canonical block from `AGENTS.md` § Pre-PR Checks in full. At minimum:
```bash
ruff check .
ruff format --check .
mypy
python3 scripts/lint_embedded.py --allow-missing-node
python3 scripts/validate_plugins.py
python3 scripts/bump_version.py --current
coverage erase
coverage run -m unittest discover -s cargento/skills/cargento/tests -t .
coverage run -a -m unittest scripts.tests.test_validate_plugins scripts.tests.test_bump_version scripts.tests.test_lint_embedded scripts.tests.test_bench_collect
coverage report
```
Expected: all pass, coverage at or above `fail_under`.

If coverage dropped below the floor, add tests rather than lowering the threshold. The threshold only ratchets up.

- [ ] **Step 7: Reconcile the docs**

Run `/sync-docs` and let it commit any doc updates onto this branch. `scripts/bench_collect.py` is a new script, so check whether it belongs in any inventory the validator owns.

- [ ] **Step 8: Commit and open the PR**

```bash
git add -A
git commit -s -m "docs(plans): record Phase 0 measurements and gate verdicts (DRC-4080)"
git push -u origin HEAD
gh pr create
```

The PR body should state the gate verdicts up front, because they decide what Phase 1's plan is allowed to build. Include `Closes DRC-4080` only if the ticket is scoped to Phase 0; it is not, so reference it instead.

---

## Self-Review

**Spec coverage against the design doc's Phase 0 section:**

| Phase 0 requirement | Task |
|---|---|
| Cold and memo-hit `/api/data` duration | 1 (partial: the script times `collect`; a memo-hit variant needs `collect_json`, add in Task 1 Step 5) |
| Discovery and collection duration per harness | 1 |
| `cProfile` of the slowest collector by function | 1 (`--profile`) |
| Files or bytes consulted | Not covered. Left out deliberately: the design says "where cheaply measurable", and no counter exists without instrumenting `io.py`. Task 7 Step 4 records it as unmeasured. |
| Number of collections with one and several tabs | Not covered by this plan. Needs the Phase 1 render path to be meaningful. Recorded as unmeasured in Task 7. |
| Forwarder p50/p95/p99 per OS | Not covered. Depends on authenticated discovery, which Phase 2 designs. Recorded as unmeasured. |
| Native hook event count per turn | Not covered. Recorded as unmeasured. |
| Probe dependency table and mutation corpus | Not covered. This plan does not build the probe. Task 7 Step 4 states the gate is unreached. |
| Collector fixes from "Make collection cheaper" | 2, 3, 4 |
| Parked-parent and nested-workflow equivalence tests | 4 Step 1 (`test_a_parked_parent_keeps_its_subagent_activity`), plus the full-suite equivalence runs in 2 Step 6 and 3 Step 4 |
| `--no-usage` Windows respawn defect | 5 |
| Pushed-receipt discard defect | 6 |
| The four independent gates | 7 |

Four measurement items are deliberately out of scope because they depend on later phases. That is recorded in Task 7 Step 4 rather than silently dropped, so no gate can be reported as passed when it was merely unreached.

**Placeholder scan:** Task 1 Step 5 and Task 6 Step 6 describe work without a full code block. Both are cases where the correct code depends on names the implementer must read first (`HarnessSpec` field names; the existing `/api/usage` test style), and both name the exact file and the exact assertion required. Every other step carries runnable content.

**Type consistency:** `agent_transcripts` gains keyword-only `config` and `state` in Task 4 and is called with both at `claude.py:236`. `load_subagents` gains keyword-only `found` in Task 2 and is called with it at the same site, so Task 4's change to `agent_transcripts` feeds Task 2's `found` parameter without a signature clash. `receive_statusline` gains keyword-only `config` in Task 6, defaulted to `None` so the existing call in `http_api.py` keeps type-checking until Step 4 updates it. `state.claude_subagent_cache` is `dict[str, tuple[float, list[tuple[str, float]]]]`, matching what `agent_transcripts` returns.
