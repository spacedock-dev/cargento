# Event-driven session observation, Phase 1a Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the response memo with a versioned in-memory snapshot whose revision survives a server restart, without changing what any client sees.

**Architecture:** One new runtime module, `snapshot.py`, holding the published `(revision, bytes)` value and its lock. `Application.collect_json` becomes a thin reader over it. `/api/data` gains a revision header and keeps its freshness guarantee. No background thread, no new endpoint, no client change.

**Tech Stack:** Python 3.11 standard library only. `unittest`, `coverage`, `ruff`, `mypy --strict`.

## Why this is its own PR

Phase 1 in the design doc is snapshot plus SSE. Those split cleanly and this is the first half:

- **1a, this plan.** Snapshot plumbing. Invisible to users: the JSON body, its freshness, and the five-second page poll are all unchanged. Reviewable as a pure refactor with one new observable, a response header.
- **1b, next.** `GET /api/stream`, leader-tab election, browser reconnect, the demand-scoped producer, the time-derived-field tick, and the quota consent lease. That is where behaviour changes.

Deliberately no background producer here. A producer exists to keep the snapshot warm for a connected stream, and there is no stream until 1b. Building one now would mean a timer with no consumer, which is exactly the "no work while nobody is looking" regression the design warns about.

**Ticket:** DRC-4084. **Design owner:** [`event-driven-session-observation.md`](event-driven-session-observation.md) § Phase 1. **Stacked on:** the Phase 0 branch, PR #83. Do not retarget this branch at `main` until #83 merges.

## Global Constraints

- Standard library only. No dependency, ever. Python floor 3.11, owned by `COMPATIBILITY.md`.
- `ruff check .` (`select = ALL`) and `ruff format --check .` must pass.
- `mypy` must pass under `--strict`.
- `coverage report` must meet `fail_under` in `pyproject.toml`. It only ratchets up.
- Tests run on Ubuntu, macOS and Windows.
- Never edit a `version` field. `version-guard` fails the PR.
- `git commit -s` for DCO. Subject format `<type>(<scope>): <description>`.
- `docs/plans/*.md` is inside the sync-docs tone gate: no em dashes, en dashes, or curly quotes.
- **R-2, inward-only imports.** `snapshot.py` must import no runtime module except `config` for types. Adding it requires a reviewed entry in `RuntimeImportGraphTest.EXPECTED` in `cargento/skills/cargento/tests/test_contracts.py`. That entry is the ownership decision, not a formality: if you find yourself adding `aggregate` to snapshot's set, the design is wrong.
- **Behaviour-preserving.** For the same store contents, `/api/data` must return byte-identical JSON with the same worst-case staleness as today. Task 5 proves it.

---

### Task 1: The snapshot container

**Files:**
- Create: `cargento/skills/cargento/cargento_runtime/snapshot.py`
- Modify: `cargento/skills/cargento/tests/test_contracts.py` (the `EXPECTED` allowlist)
- Test: `cargento/skills/cargento/tests/test_snapshot.py`

**Interfaces:**
- Consumes: `cargento_runtime.config.RuntimeConfig` for typing only, under `TYPE_CHECKING`.
- Produces:
  - `Revision = tuple[float, int]`, the pair `(server_started, counter)`.
  - `class Snapshot` with `publish(key, body) -> Revision`, `current(key) -> tuple[Revision, bytes] | None`, and `age(key, now) -> float | None`.
  - `format_revision(rev: Revision) -> str` rendering `"<server_started:.0f>.<counter>"`.

`key` is the existing memo key shape, `(window_hours, show_all)`, so the two response variants stay separate exactly as they are today.

- [ ] **Step 1: Write the failing test**

Create `cargento/skills/cargento/tests/test_snapshot.py`:

```python
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
        rev, _body = snap.current((24.0, False)) or (None, None)
        self.assertIsNone(rev)
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
        self.assertAlmostEqual(snap.age((24.0, False), now=502.5), 2.5)

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/jaredmscott/repos/recce/cargento && python3 -m unittest cargento.skills.cargento.tests.test_snapshot -v`

Expected: FAIL with `ImportError: cannot import name 'snapshot' from 'cargento_runtime'`.

- [ ] **Step 3: Write the implementation**

Create `cargento_runtime/snapshot.py`:

```python
"""The published dashboard snapshot: one built response per variant, versioned.

The revision is a pair, not an integer. A counter alone restarts at zero with
the process, so a tab frozen at revision 512 across a dashboard restart would
treat every later revision as older and never refetch again. Pairing it with
the server start stamp makes a restart visibly discontinuous, and the client
discards its cursor when the first element changes.

The counter is per process rather than per variant, so it orders every
published state a client could hold a cursor against.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from _thread import LockType

# (window_hours, show_all): the response variants, keyed as the memo keyed them.
SnapshotKey = tuple[float, bool]
# (server_started, counter)
Revision = tuple[float, int]


def format_revision(revision: Revision) -> str:
    """The wire form: restart stamp, a dot, the counter."""
    started, counter = revision
    return f"{started:.0f}.{counter}"


class Snapshot:
    """One process's published responses, guarded by its own lock.

    The lock is held only across a dict read or write, never across collection
    and never across a socket write. A published entry is an immutable tuple, so
    a reader that has taken one cannot be torn by a concurrent publish.
    """

    def __init__(self, *, server_started: float) -> None:
        self.server_started = server_started
        self._lock: LockType = threading.Lock()
        self._counter = 0
        self._entries: dict[SnapshotKey, tuple[Revision, bytes, float]] = {}

    def publish(self, key: SnapshotKey, body: bytes, *, now: float = 0.0) -> Revision:
        with self._lock:
            self._counter += 1
            revision = (self.server_started, self._counter)
            self._entries[key] = (revision, body, now)
            return revision

    def current(self, key: SnapshotKey) -> tuple[Revision, bytes] | None:
        with self._lock:
            entry = self._entries.get(key)
        if entry is None:
            return None
        revision, body, _published_at = entry
        return revision, body

    def age(self, key: SnapshotKey, *, now: float) -> float | None:
        """Seconds since this variant was published, or None if it never was.

        None rather than zero: zero reads as fresh, which would let a cold GET
        skip the collection it needs.
        """
        with self._lock:
            entry = self._entries.get(key)
        if entry is None:
            return None
        return now - entry[2]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_snapshot -v`

Expected: PASS, 9 tests.

- [ ] **Step 5: Add the reviewed allowlist entry**

`RuntimeImportGraphTest.EXPECTED` in `cargento/skills/cargento/tests/test_contracts.py` is keyed by module name with a set of runtime imports. Add, in alphabetical position:

```python
        # The published snapshot is a passive container: it holds bytes and a
        # revision and takes a lock. It imports no runtime module, which is what
        # lets both aggregate and the HTTP layer depend on it without a cycle.
        "cargento_runtime.snapshot": set(),
```

- [ ] **Step 6: Run the contract test**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_contracts -v`

Expected: PASS. If `test_runtime_import_graph_matches_the_reviewed_allowlist` fails, read the diff it prints: it means `snapshot.py` imported something it should not.

- [ ] **Step 7: Commit**

```bash
git add cargento/skills/cargento/cargento_runtime/snapshot.py \
        cargento/skills/cargento/tests/test_snapshot.py \
        cargento/skills/cargento/tests/test_contracts.py
git commit -s -m "feat(snapshot): add the versioned published-response container (DRC-4084)"
```

---

### Task 2: Serve `/api/data` from the snapshot

Replace the memo with the snapshot, preserving the anti-stampede property and the freshness guarantee. The memo held its lock across collection so concurrent tabs shared one filesystem scan; that behaviour must survive, and it is why the collection lock stays separate from the snapshot lock.

**Files:**
- Modify: `cargento/skills/cargento/cargento_runtime/aggregate.py` (`Application.__init__`, `collect_json`)
- Modify: `cargento/skills/cargento/tests/test_contracts.py` (`aggregate` gains `cargento_runtime.snapshot`)
- Test: `cargento/skills/cargento/tests/test_http_api.py`, `cargento/skills/cargento/tests/test_snapshot.py`

**Interfaces:**
- Consumes: `Snapshot`, `Revision`, `SnapshotKey` from Task 1.
- Produces: `Application.snapshot` attribute, and `Application.collect_json(*, show_all) -> tuple[Revision, bytes]`. **The return type changes.** Task 3 updates the one production caller. `support.collect_json` in the test helpers returns bytes and must keep doing so, so update it to unpack.

- [ ] **Step 1: Write the failing test**

Add to `cargento/skills/cargento/tests/test_snapshot.py`:

```python
class ApplicationSnapshotTest(support.RuntimeTestCase):
    """collect_json publishes, reuses inside the floor, and recollects after it."""

    def test_a_second_call_inside_the_floor_reuses_the_published_bytes(self) -> None:
        app = support.build_app()
        calls: list[int] = []
        real = app.collect

        def counting(*, show_all: bool) -> dict[str, object]:
            calls.append(1)
            return real(show_all=show_all)

        app.collect = counting  # type: ignore[method-assign]
        first_rev, first_body = app.collect_json(show_all=False)
        second_rev, second_body = app.collect_json(show_all=False)
        self.assertEqual(len(calls), 1, "the second call must not recollect")
        self.assertEqual(first_body, second_body)
        self.assertEqual(first_rev, second_rev, "reuse must not mint a revision")

    def test_the_two_variants_are_published_separately(self) -> None:
        app = support.build_app()
        default_rev, _ = app.collect_json(show_all=False)
        all_rev, _ = app.collect_json(show_all=True)
        self.assertNotEqual(default_rev, all_rev)
        self.assertIsNotNone(app.snapshot.current((app.config.window_hours, False)))
        self.assertIsNotNone(app.snapshot.current((app.config.window_hours, True)))

    def test_a_stale_snapshot_recollects_and_mints_a_new_revision(self) -> None:
        app = support.build_app()
        first_rev, _ = app.collect_json(show_all=False)
        # Advance past the floor rather than sleeping: the clock is injected.
        base = app.clock()
        app.clock = lambda: base + app.config.collect_memo_sec + 1  # type: ignore[method-assign]
        second_rev, _ = app.collect_json(show_all=False)
        self.assertGreater(second_rev[1], first_rev[1])
```

Import `support` at the top of the module and add `from . import support`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_snapshot -v`

Expected: FAIL. `collect_json` returns `bytes`, so unpacking into two names raises `ValueError` or the attribute `app.snapshot` does not exist.

- [ ] **Step 3: Write the implementation**

In `aggregate.py`, add to `Application.__init__` after `self.state = state`:

```python
        self.snapshot = runtime_snapshot.Snapshot(server_started=state.server_started)
```

and import the module alongside the other runtime imports:

```python
from cargento_runtime import snapshot as runtime_snapshot
```

Replace `collect_json` with:

```python
    def collect_json(self, *, show_all: bool) -> tuple[runtime_snapshot.Revision, bytes]:
        """The published response for one variant, collecting only if stale.

        Two locks, deliberately. `collect_memo_lock` is still held across
        collection, so concurrent tabs share one filesystem and SQLite scan
        instead of stampeding a cold entry. The snapshot's own lock is taken
        only to read or write the published tuple, so a slow reader can never
        block a collection and a collection can never block a reader.
        """
        state = self.state
        key: runtime_snapshot.SnapshotKey = (self.config.window_hours, show_all)
        fresh = self.snapshot.age(key, now=self.clock())
        if fresh is not None and fresh < self.config.collect_memo_sec:
            current = self.snapshot.current(key)
            if current is not None:
                return current
        with state.collect_memo_lock:
            # Re-check under the lock: another thread may have collected while
            # this one waited, which is the whole point of holding it.
            fresh = self.snapshot.age(key, now=self.clock())
            if fresh is not None and fresh < self.config.collect_memo_sec:
                current = self.snapshot.current(key)
                if current is not None:
                    return current
            body = json.dumps(self.collect(show_all=show_all)).encode()
            revision = self.snapshot.publish(key, body, now=self.clock())
            return revision, body
```

Leave `state.collect_memo` and `CollectMemoEntry` in place for now; Task 4 removes them once nothing reads them.

- [ ] **Step 4: Update the allowlist and the test helper**

In `test_contracts.py`, add `"cargento_runtime.snapshot"` to the `"cargento_runtime.aggregate"` set.

In `cargento/skills/cargento/tests/support.py`, `collect_json` currently returns the bytes. Keep its signature and unpack:

```python
def collect_json(window_hours: float = 24, show_all: bool = False) -> bytes:
    _revision, body = build_app(window_hours).collect_json(show_all=show_all)
    return body
```

Read the current body of that helper before editing and preserve whatever else it does.

- [ ] **Step 5: Run the tests**

Run:
```bash
python3 -m unittest cargento.skills.cargento.tests.test_snapshot cargento.skills.cargento.tests.test_contracts -v
python3 -m unittest discover -s cargento/skills/cargento/tests -t .
```
Expected: PASS. Any other failure is a caller of `collect_json` you have not updated; fix the caller, not the return type.

- [ ] **Step 6: Commit**

```bash
git add cargento/skills/cargento/cargento_runtime/aggregate.py \
        cargento/skills/cargento/tests/test_snapshot.py \
        cargento/skills/cargento/tests/test_contracts.py \
        cargento/skills/cargento/tests/support.py
git commit -s -m "feat(aggregate): serve /api/data from the versioned snapshot (DRC-4084)"
```

---

### Task 3: Expose the served revision on the wire

A client cannot compare cursors it cannot see. The revision goes in a response header, not the JSON body, so the documented body contract is untouched and `curl` output is unchanged.

**Files:**
- Modify: `cargento/skills/cargento/cargento_runtime/http_api.py` (`_send`, `do_GET`)
- Test: `cargento/skills/cargento/tests/test_http_api.py`

**Interfaces:**
- Consumes: `collect_json` returning `(Revision, bytes)` from Task 2.
- Produces: response header `X-Cargento-Revision: <started>.<counter>` on `/api/data`. No other route sets it.

- [ ] **Step 1: Write the failing test**

Add to `cargento/skills/cargento/tests/test_http_api.py`, matching how the existing tests in that module build a server:

```python
class DataRevisionHeaderTest(...):
    """/api/data names the revision it served, so a client can hold a cursor."""

    def test_the_header_is_present_and_restart_qualified(self) -> None:
        # Build a server the way the neighbouring tests do, GET /api/data, then:
        #   header = response.headers["X-Cargento-Revision"]
        #   self.assertRegex(header, r"^\d+\.\d+$")
        # and assert the counter half increments across a stale re-request while
        # the stamp half does not change within one process.

    def test_the_body_is_unchanged_by_the_header(self) -> None:
        # json.loads(body) must still parse and must contain "sessions" and
        # "generated", exactly as before this task.

    def test_health_and_root_do_not_carry_a_revision(self) -> None:
        # Only /api/data publishes a cursor; a page load or a liveness probe
        # carrying one would invite a client to treat it as comparable.
```

Fill each body in using the existing helpers in that module (`support.make_server`, `support.serve_until_closed`). Read two neighbouring tests first and copy their structure exactly rather than inventing a new one.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_http_api -v`

Expected: FAIL with `KeyError: 'X-Cargento-Revision'`.

- [ ] **Step 3: Write the implementation**

Give `_send` an optional header map rather than a revision-specific parameter, so a later task can add a second header without touching the signature again:

```python
    def _send(
        self,
        body: bytes,
        ctype: str,
        code: int = 200,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)
```

In `do_GET`, at the `/api/data` branch:

```python
            revision, body = self.server.application.collect_json(show_all=show_all)
            self._send(
                body,
                "application/json",
                headers={"X-Cargento-Revision": runtime_snapshot.format_revision(revision)},
            )
```

Import `snapshot as runtime_snapshot` in `http_api.py` and add `"cargento_runtime.snapshot"` to the `"cargento_runtime.http_api"` set in the allowlist.

- [ ] **Step 4: Run the tests**

Run:
```bash
python3 -m unittest cargento.skills.cargento.tests.test_http_api cargento.skills.cargento.tests.test_contracts -v
python3 -m unittest discover -s cargento/skills/cargento/tests -t .
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cargento/skills/cargento/cargento_runtime/http_api.py \
        cargento/skills/cargento/tests/test_http_api.py \
        cargento/skills/cargento/tests/test_contracts.py
git commit -s -m "feat(http): name the served revision in an /api/data header (DRC-4084)"
```

---

### Task 4: Retire the dead memo

`state.collect_memo`, `state.CollectMemoEntry` and `config.collect_memo_sec` are now partly dead: the dict and its TypedDict have no reader, while the interval is still the freshness floor. Delete the dead half and keep the live one, so a future reader does not restore a second cache alongside the snapshot.

**Files:**
- Modify: `cargento/skills/cargento/cargento_runtime/state.py`
- Modify: `cargento/skills/cargento/tests/support.py` (`clear_state`)
- Test: existing suite

**Interfaces:**
- Consumes: nothing new.
- Produces: `RuntimeState` no longer has `collect_memo`; `CollectMemoEntry` is gone. `collect_memo_lock` stays, since Task 2 still holds it across collection. `config.collect_memo_sec` stays, as the freshness floor.

- [ ] **Step 1: Prove they are dead**

Run:
```bash
grep -rn "collect_memo\b\|CollectMemoEntry" --include='*.py' cargento/ scripts/
```
Expected: hits only in `state.py` (the definitions), `support.clear_state`, and any test asserting on the old memo. `collect_memo_lock` hits are separate and must remain. If a production reader still exists, stop: Task 2 is incomplete.

- [ ] **Step 2: Delete the dead members**

Remove the `CollectMemoEntry` TypedDict and the `collect_memo` field from `state.py`. Keep `collect_memo_lock` and add a comment naming its surviving job:

```python
    # Still held across collection so concurrent readers share one scan. The
    # published bytes now live in Application.snapshot, which has its own lock.
    collect_memo_lock: LockType = field(default_factory=threading.Lock)
```

- [ ] **Step 3: Update `clear_state`**

`support.clear_state` promises to empty every cache. Remove its `collect_memo` line, and add nothing: the snapshot belongs to the application, not to state, so a fresh `build_app` already gets a fresh one. Note that in the docstring if it lists what it clears.

- [ ] **Step 4: Run the suite**

Run:
```bash
python3 -m unittest discover -s cargento/skills/cargento/tests -t .
mypy
```
Expected: PASS. `mypy --strict` is what catches a missed reference.

- [ ] **Step 5: Commit**

```bash
git add cargento/skills/cargento/cargento_runtime/state.py cargento/skills/cargento/tests/support.py
git commit -s -m "refactor(state): drop the response memo the snapshot replaced (DRC-4084)"
```

---

### Task 5: Prove it changed nothing, then document it

**Files:**
- Test: `cargento/skills/cargento/tests/test_http_api.py`
- Modify: `docs/design-runtime-architecture.md` (module table, R-2 allowlist prose)
- Modify: `docs/plans/event-driven-session-observation.md` (Phase 1 progress)

- [ ] **Step 1: Write the equivalence test**

The claim is that for identical store contents the response is byte-identical to the pre-change one. Add a test that builds a fixture store, collects twice through two independently constructed applications, and asserts the bodies match apart from the `generated` timestamp:

```python
    def test_the_payload_is_unchanged_apart_from_its_generated_stamp(self) -> None:
        first = json.loads(support.collect_json())
        second = json.loads(support.collect_json())
        first.pop("generated", None)
        second.pop("generated", None)
        self.assertEqual(first, second)
```

That is necessary but weak on its own, so also confirm against the base branch by hand in Step 2.

- [ ] **Step 2: Diff a real response against the Phase 0 branch**

```bash
python3 -c "
import json,sys; sys.path.insert(0,'cargento/skills/cargento')
from tests import support
d=json.loads(support.collect_json()); d.pop('generated',None)
print(json.dumps(d,sort_keys=True))" > /tmp/after.json
git stash && git checkout feature/drc-4080-event-driven-session-observation-materialized-snapshot-sse -- . 2>/dev/null || true
```

Safer alternative, and the one to prefer: check the Phase 0 branch out into a detached worktree, run the same one-liner there, and `diff` the two files. Do not stash and check out over your working tree.

```bash
git worktree add --detach /tmp/p0 feature/drc-4080-event-driven-session-observation-materialized-snapshot-sse
# run the same one-liner in /tmp/p0, write /tmp/before.json
diff /tmp/before.json /tmp/after.json && echo "byte-identical"
git worktree remove /tmp/p0
```

Expected: no diff. If there is one, the refactor changed behaviour and the task is not done.

- [ ] **Step 3: Update the module map**

`docs/design-runtime-architecture.md` owns the module table and the R-2 rule. Add a `snapshot.py` row describing what it owns (the published response bytes and the restart-qualified revision) and note that it imports no runtime module, which is what keeps `aggregate` and `http_api` able to share it without a cycle.

- [ ] **Step 4: Update the design plan's Phase 1 section**

Mark the snapshot, revision pair and `/api/data` freshness rule as shipped, and note that the stream, producer, time tick and consent lease remain in 1b. Do not delete the Phase 1 section: it is still partly unshipped.

Tone gate applies: no em dashes, en dashes or curly quotes.

- [ ] **Step 5: Run the full gate**

```bash
ruff check . && ruff format --check . && mypy
python3 scripts/lint_embedded.py --allow-missing-node
python3 scripts/validate_plugins.py
python3 scripts/bump_version.py --current
coverage erase
coverage run -m unittest discover -s cargento/skills/cargento/tests -t .
coverage run -a -m unittest scripts.tests.test_validate_plugins scripts.tests.test_bump_version \
  scripts.tests.test_lint_embedded scripts.tests.test_bench_collect
coverage report
```
Expected: all pass, coverage at or above `fail_under`.

- [ ] **Step 6: Commit, then open the stacked PR**

```bash
git add -A
git commit -s -m "docs: record the snapshot module and Phase 1a progress (DRC-4084)"
git push -u origin HEAD
gh pr create --base feature/drc-4080-event-driven-session-observation-materialized-snapshot-sse
```

**The `--base` flag is the whole point of the stack.** Without it the PR targets `main` and its diff will include every Phase 0 commit. Verify after opening: `gh pr view --json baseRefName` must show the Phase 0 branch.

Do not merge this before #83. When #83 merges, retarget this PR at `main` (`gh pr edit --base main`) and rebase, because a squash merge rewrites Phase 0 into a single new commit and the old parents stop existing.

---

## Self-Review

**Spec coverage against the design doc's Phase 1 section:**

| Phase 1 requirement | Where |
|---|---|
| Versioned snapshot and publish protocol | Tasks 1, 2 |
| Revision pair surviving restart | Task 1 |
| `/api/data` serves the snapshot | Task 2 |
| Independent direct-GET freshness rule | Task 2, held at `collect_memo_sec` so worst-case staleness is literally unchanged |
| Lazy init on first demand | Task 2, by construction: nothing publishes until the first GET |
| Services start only after daemonization | 1b. No service is started here, which is why it does not arise |
| SSE stream and all its hardening | 1b |
| Demand-scoped producer | 1b, deliberately, per "Why this is its own PR" |
| Time-derived field tick | 1b |
| Quota consent lease | 1b |

**Placeholder scan:** Task 3 Step 1 gives three test names with described assertions rather than full bodies, because the module's server-construction helper differs between test classes and copying the wrong one produces a passing test that starts no server. The file and the exact assertions are named. Task 5 Step 2 offers two approaches and marks the worktree one as preferred; the discouraged variant is shown only because an implementer will otherwise reach for `git stash` on their own.

**Type consistency:** `collect_json` changes from `bytes` to `tuple[Revision, bytes]` in Task 2, and Task 2 Step 4 updates both the production caller path and `support.collect_json`. Task 3 consumes that tuple. `SnapshotKey` is `tuple[float, bool]` in Task 1 and is constructed as `(self.config.window_hours, show_all)` in Task 2, matching. `format_revision` is defined in Task 1 and called in Task 3.
