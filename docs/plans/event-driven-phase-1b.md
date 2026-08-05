# Event-driven session observation, Phase 1b Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve `GET /api/stream` as a bounded, heartbeat-driven SSE revision stream, and run a collection producer only while a stream is connected.

**Architecture:** One new runtime module, `stream.py`, holding the connected clients and their one-slot mailboxes. It imports no runtime module, so `state` can own a registry the same way it owns the snapshot. `aggregate` notifies the registry when it publishes a revision. `http_api` serves the endpoint. `lifecycle` runs the producer thread, started after daemonization and stopped with the server.

**Tech Stack:** Python 3.11 standard library only. `unittest`, `coverage`, `ruff`, `mypy --strict`.

## Why this is server-only

Phase 1b in the design doc is the stream plus the client plus the quota lease. This plan is the server half:

- **1b, this plan.** `/api/stream`, connection budgets, heartbeats, write timeouts, one-slot mailboxes, shutdown, and the demand-scoped producer. **The page is not changed and keeps polling every five seconds**, so the endpoint is inert until 1c connects to it. That is deliberate: the thread, lock and shutdown discipline is the risky part of Phase 1 and it is worth reviewing on its own, against tests, rather than alongside a JavaScript rewrite.
- **1c, next.** `EventSource` in the page, leader-tab election, reconnect, removing the poll, the quota consent lease, and the time-derived-field tick. That is where user-visible behaviour changes.

An inert endpoint for one PR cycle is the cost. The benefit is that when 1c lands, every failure it produces is a client failure, because the server contract is already proven.

**Ticket:** DRC-4084. **Design owner:** [`event-driven-session-observation.md`](event-driven-session-observation.md) § Phase 1. **Stacked on:** the Phase 1a branch, PR #84, which is itself stacked on #83.

## Global Constraints

- Standard library only. Python floor 3.11.
- `ruff check .` (`select = ALL`), `ruff format --check .`, `mypy --strict` must pass.
- `coverage report` must meet `fail_under`. It only ratchets up.
- Tests run on Ubuntu, macOS and Windows. A test that blocks on a socket needs a timeout on both ends, or Windows CI hangs rather than fails.
- Never edit a `version` field.
- `git commit -s` for DCO.
- `docs/plans/*.md` is inside the tone gate: no em dashes, en dashes, or curly quotes.
- **R-2.** `stream.py` imports no runtime module. Each new module or edge needs a reviewed entry in `RuntimeImportGraphTest.EXPECTED`.
- **New runtime modules must be added to `CARGENTO_RUNTIME_FILES` in `scripts/validate_plugins.py`.** Phase 1a shipped a module without it and the installed-copy route test caught it as a handler crash. Do not repeat that.
- **Never hold a lock across a socket write.** The publisher takes the registry lock only to drop a revision into each client's mailbox. The handler takes nothing while writing.
- **The producer must not run when nobody is connected.** An idle daemon does zero filesystem work today and this phase must not regress that.

---

### Task 1: The stream registry

**Files:**
- Create: `cargento/skills/cargento/cargento_runtime/stream.py`
- Modify: `cargento/skills/cargento/cargento_runtime/state.py` (own a registry)
- Modify: `cargento/skills/cargento/tests/test_contracts.py` (allowlist)
- Modify: `scripts/validate_plugins.py` (`CARGENTO_RUNTIME_FILES`)
- Test: `cargento/skills/cargento/tests/test_stream.py`

**Interfaces:**
- Produces:
  - `class StreamClient` with `wait(timeout) -> Revision | None`, `offer(revision)`, `close()`, and `closed` as a property.
  - `class StreamRegistry` with `register(*, limit) -> StreamClient | None` (None when the budget is full), `release(client)`, `publish(revision)`, `close_all()`, and `count` as a property.
  - `Revision` is re-used from `snapshot`, but `stream.py` must not import it. Type the mailbox as `tuple[float, int]` directly and say why in a comment.

A one-slot mailbox, not a queue. A slow client must fall behind by losing intermediate revisions, never by growing an unbounded backlog. The newest revision is the only one worth delivering, because the client refetches the whole payload anyway.

- [ ] **Step 1: Write the failing test**

Create `cargento/skills/cargento/tests/test_stream.py`:

```python
"""The SSE client registry: one-slot mailboxes, budgets, and shutdown."""

from __future__ import annotations

import threading
import unittest

from cargento_runtime import stream as runtime_stream


class StreamClientTest(unittest.TestCase):
    def test_wait_returns_the_offered_revision(self) -> None:
        client = runtime_stream.StreamClient()
        client.offer((1000.0, 5))
        self.assertEqual((1000.0, 5), client.wait(timeout=0.01))

    def test_wait_times_out_to_none_so_the_caller_can_heartbeat(self) -> None:
        self.assertIsNone(runtime_stream.StreamClient().wait(timeout=0.01))

    def test_the_mailbox_holds_one_slot_and_keeps_the_newest(self) -> None:
        # A slow reader falls behind by skipping revisions, never by growing a
        # backlog. The client refetches the whole payload, so only the newest
        # revision is worth delivering.
        client = runtime_stream.StreamClient()
        client.offer((1000.0, 1))
        client.offer((1000.0, 2))
        client.offer((1000.0, 3))
        self.assertEqual((1000.0, 3), client.wait(timeout=0.01))
        self.assertIsNone(client.wait(timeout=0.01))

    def test_close_wakes_a_waiter_and_marks_the_client_closed(self) -> None:
        client = runtime_stream.StreamClient()
        woke = threading.Event()

        def waiter() -> None:
            client.wait(timeout=5.0)
            woke.set()

        thread = threading.Thread(target=waiter, daemon=True)
        thread.start()
        client.close()
        self.assertTrue(woke.wait(timeout=2.0), "close must wake a blocked waiter")
        self.assertTrue(client.closed)
        thread.join(timeout=2.0)


class StreamRegistryTest(unittest.TestCase):
    def test_register_returns_a_client_and_counts_it(self) -> None:
        registry = runtime_stream.StreamRegistry()
        client = registry.register(limit=2)
        self.assertIsNotNone(client)
        self.assertEqual(1, registry.count)

    def test_register_refuses_past_the_budget(self) -> None:
        registry = runtime_stream.StreamRegistry()
        self.assertIsNotNone(registry.register(limit=1))
        self.assertIsNone(registry.register(limit=1), "the budget must be a hard cap")
        self.assertEqual(1, registry.count)

    def test_release_frees_a_slot(self) -> None:
        registry = runtime_stream.StreamRegistry()
        first = registry.register(limit=1)
        assert first is not None
        registry.release(first)
        self.assertEqual(0, registry.count)
        self.assertIsNotNone(registry.register(limit=1))

    def test_publish_reaches_every_registered_client(self) -> None:
        registry = runtime_stream.StreamRegistry()
        a = registry.register(limit=4)
        b = registry.register(limit=4)
        assert a is not None and b is not None
        registry.publish((1000.0, 9))
        self.assertEqual((1000.0, 9), a.wait(timeout=0.01))
        self.assertEqual((1000.0, 9), b.wait(timeout=0.01))

    def test_publish_with_no_clients_is_a_no_op(self) -> None:
        runtime_stream.StreamRegistry().publish((1000.0, 1))

    def test_close_all_closes_every_client_and_empties_the_registry(self) -> None:
        registry = runtime_stream.StreamRegistry()
        client = registry.register(limit=4)
        assert client is not None
        registry.close_all()
        self.assertTrue(client.closed)
        self.assertEqual(0, registry.count)

    def test_a_released_client_stops_receiving(self) -> None:
        registry = runtime_stream.StreamRegistry()
        client = registry.register(limit=4)
        assert client is not None
        registry.release(client)
        registry.publish((1000.0, 2))
        self.assertIsNone(client.wait(timeout=0.01))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/jaredmscott/repos/recce/cargento && python3 -m unittest cargento.skills.cargento.tests.test_stream -v`

Expected: FAIL with `ImportError: cannot import name 'stream' from 'cargento_runtime'`.

- [ ] **Step 3: Write the implementation**

Create `cargento_runtime/stream.py`:

```python
"""Connected SSE clients and their one-slot revision mailboxes.

A mailbox holds one revision, not a queue. A client that reads slowly must fall
behind by skipping intermediate revisions rather than by growing an unbounded
backlog, and skipping costs it nothing: it refetches the whole payload on the
revision it does see, so only the newest one is worth delivering.

This module imports nothing from the runtime, which is what lets `state` own a
registry and `http_api` serve from it without a cycle. The revision type is
written out rather than imported from `snapshot` for the same reason; the two
must stay the same shape, which the tests assert.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from _thread import LockType

# Structurally identical to snapshot.Revision. Not imported, to keep this
# module free of runtime dependencies.
Revision = tuple[float, int]


class StreamClient:
    """One connected stream: a one-slot mailbox and a wake-up."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._pending: Revision | None = None
        self._closed = False

    @property
    def closed(self) -> bool:
        with self._condition:
            return self._closed

    def offer(self, revision: Revision) -> None:
        """Replace whatever is waiting. Newest wins; nothing queues."""
        with self._condition:
            self._pending = revision
            self._condition.notify_all()

    def wait(self, *, timeout: float) -> Revision | None:
        """The pending revision, or None on timeout or close.

        None is the heartbeat signal as well as the shutdown signal, so the
        caller checks `closed` to tell them apart.
        """
        with self._condition:
            if self._pending is None and not self._closed:
                self._condition.wait(timeout)
            pending, self._pending = self._pending, None
            return pending

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()


class StreamRegistry:
    """Every connected stream on one runtime, behind one short-held lock.

    The lock is taken to add, drop, or hand a revision to each mailbox. It is
    never held across a socket write: the handler writes outside it entirely.
    """

    def __init__(self) -> None:
        self._lock: LockType = threading.Lock()
        self._clients: set[StreamClient] = set()

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._clients)

    def register(self, *, limit: int) -> StreamClient | None:
        """A new client, or None when the budget is full.

        A hard cap rather than a queue: every stream costs a thread and a
        socket for as long as it lives, so the honest answer past the cap is a
        refusal the caller can turn into a 503.
        """
        client = StreamClient()
        with self._lock:
            if len(self._clients) >= limit:
                return None
            self._clients.add(client)
            return client

    def release(self, client: StreamClient) -> None:
        with self._lock:
            self._clients.discard(client)
        client.close()

    def publish(self, revision: Revision) -> None:
        with self._lock:
            clients = list(self._clients)
        # Outside the lock: offer() takes each client's own condition, and a
        # publisher must never be able to block another publisher.
        for client in clients:
            client.offer(revision)

    def close_all(self) -> None:
        """Wake and drop every client. Shutdown calls this."""
        with self._lock:
            clients = list(self._clients)
            self._clients.clear()
        for client in clients:
            client.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest cargento.skills.cargento.tests.test_stream -v`

Expected: PASS, 11 tests.

- [ ] **Step 5: Give the runtime a registry**

In `state.py`, beside the snapshot field:

```python
    # Connected SSE clients, owned here for the same reason the snapshot is:
    # they belong to the runtime, not to whichever object serves a request.
    streams: runtime_stream.StreamRegistry = field(init=False)
```

and in `__post_init__`:

```python
        self.streams = runtime_stream.StreamRegistry()
```

Import `from cargento_runtime import stream as runtime_stream` alongside the snapshot import.

- [ ] **Step 6: Register the module everywhere it must be registered**

Two inventories, both of which Phase 1a proved are easy to miss:

1. `RuntimeImportGraphTest.EXPECTED` in `test_contracts.py`: add `"cargento_runtime.stream": set()`, and add `"cargento_runtime.stream"` to the `"cargento_runtime.state"` set.
2. `CARGENTO_RUNTIME_FILES` in `scripts/validate_plugins.py`: add `"skills/cargento/cargento_runtime/stream.py"` in alphabetical position.

- [ ] **Step 7: Assert the two revision shapes cannot drift**

Add to `test_stream.py`:

```python
class RevisionShapeTest(unittest.TestCase):
    def test_the_stream_revision_matches_the_snapshot_revision(self) -> None:
        """stream.py deliberately does not import snapshot, so pin the shape."""
        from cargento_runtime import snapshot as runtime_snapshot

        self.assertEqual(runtime_snapshot.Revision, runtime_stream.Revision)
```

- [ ] **Step 8: Run the suite and the gate**

```bash
python3 -m unittest discover -s cargento/skills/cargento/tests -t .
python3 -m unittest scripts.tests.test_validate_plugins
ruff check . && ruff format --check . && mypy && python3 scripts/validate_plugins.py
```
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -s -m "feat(stream): add the SSE client registry and one-slot mailboxes (DRC-4084)"
```

---

### Task 2: Publish revisions into the registry

**Files:**
- Modify: `cargento/skills/cargento/cargento_runtime/aggregate.py` (`collect_json`)
- Test: `cargento/skills/cargento/tests/test_stream.py`

**Interfaces:**
- Consumes: `state.streams` from Task 1.
- Produces: every newly minted revision reaches every connected client. A reused snapshot does not, because nothing changed.

- [ ] **Step 1: Write the failing test**

```python
class PublishNotifiesStreamsTest(support.RuntimeTestCase):
    def test_a_fresh_collection_reaches_a_connected_client(self) -> None:
        app = support.build_app()
        client = app.state.streams.register(limit=4)
        assert client is not None
        revision, _body = app.collect_json(show_all=False)
        self.assertEqual(revision, client.wait(timeout=0.01))

    def test_a_reused_snapshot_does_not_wake_a_client(self) -> None:
        # Nothing changed, so there is nothing to tell a client about. Waking
        # it would make every warm GET cost every stream a refetch.
        app = support.build_app()
        app.collect_json(show_all=False)
        client = app.state.streams.register(limit=4)
        assert client is not None
        app.collect_json(show_all=False)
        self.assertIsNone(client.wait(timeout=0.01))
```

Add `from . import support` to the module imports.

- [ ] **Step 2: Run test to verify it fails**

Expected: the first test FAILS with `None != (…)`, because nothing publishes yet.

- [ ] **Step 3: Write the implementation**

In `collect_json`, immediately after `revision = self.snapshot.publish(...)` and still inside the lock:

```python
            revision = self.snapshot.publish(key, body, now=self.clock())
            # Only a freshly minted revision is worth announcing. A warm reuse
            # returns above without reaching this line, so a connected client is
            # never woken for a state it already has.
            self.state.streams.publish(revision)
            return revision, body
```

- [ ] **Step 4: Run the tests**

```bash
python3 -m unittest cargento.skills.cargento.tests.test_stream -v
python3 -m unittest discover -s cargento/skills/cargento/tests -t .
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -s -m "feat(aggregate): announce each new revision to connected streams (DRC-4084)"
```

---

### Task 3: Serve `GET /api/stream`

**Files:**
- Modify: `cargento/skills/cargento/cargento_runtime/config.py` (four tunables)
- Modify: `cargento/skills/cargento/cargento_runtime/http_api.py` (`do_GET`, a `_stream` handler)
- Modify: `cargento/skills/cargento/tests/test_contracts.py` (allowlist: `http_api` gains `stream`)
- Test: `cargento/skills/cargento/tests/test_http_api.py`

**Interfaces:**
- Consumes: `state.streams`, `state.snapshot`.
- Produces: `GET /api/stream`, `text/event-stream`. Emits the current revision immediately, then one `event: revision` per publish, and a `: keepalive` comment every heartbeat interval. Returns 503 past the budget.

**Config fields, following the existing `_sec` / `_bytes` naming:**

```python
    stream_max_clients: int
    stream_heartbeat_sec: float
    stream_write_timeout_sec: float
```

with defaults `stream_max_clients=8`, `stream_heartbeat_sec=15.0`, `stream_write_timeout_sec=10.0`. Eight is above the browsers' six-per-origin cap, so the server is not the thing that refuses first; the cap exists to bound threads, not to police tabs.

- [ ] **Step 1: Write the failing test**

Add to `test_http_api.py`, using the raw `http.client` pattern the neighbouring tests use. Do not invent a helper; `CargentoServerTest` has no shared response helper beyond the one Phase 1a added.

```python
class StreamEndpointTest(RuntimeTestCase):
    """The SSE contract: immediate state, then one event per revision."""

    @staticmethod
    def _open_stream(port: int) -> tuple[http.client.HTTPConnection, Any]:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/api/stream")
        return conn, conn.getresponse()

    def test_the_stream_opens_with_the_correct_content_type(self) -> None:
        # 200, text/event-stream, no-store.

    def test_the_current_revision_arrives_immediately(self) -> None:
        # A client must not wait for the next change to learn where it is.
        # Read the first event and assert it is `event: revision`.

    def test_a_new_revision_is_delivered(self) -> None:
        # Open the stream, force a collection (state_of().snapshot.clear() then
        # collect_json), and read the next event.

    def test_a_cross_site_fetch_is_refused(self) -> None:
        # Sec-Fetch-Site: cross-site with a document-navigation shape must be
        # 403 on this route, unlike /api/data. A long-lived data stream is not
        # a document navigation.

    def test_the_budget_refuses_past_the_cap(self) -> None:
        # With stream_max_clients patched to 1, the second concurrent stream
        # gets 503 rather than a thread.
```

Fill each body with real socket reads. Every read needs a timeout, or Windows CI hangs instead of failing.

- [ ] **Step 2: Run test to verify it fails**

Expected: 404 on `/api/stream`.

- [ ] **Step 3: Add the config fields**

Add the three fields to `RuntimeConfig` and their defaults to `build_runtime_config`, in the same relative position as the other server tunables.

- [ ] **Step 4: Write the handler**

In `http_api.py`:

```python
    def _stream(self) -> None:
        """The SSE revision stream.

        Strictly same-origin: `do_GET` relaxes its check for document
        navigations so a link to the dashboard works, and a long-lived data
        stream is not a document navigation. Re-checking here with the strict
        form is what keeps that relaxation off this route.
        """
        if not self._local_ok():
            self.send_error(403)
            return
        application = self.server.application
        config = application.config
        state = application.state
        client = state.streams.register(limit=config.stream_max_clients)
        if client is None:
            # A refusal, not a queue: every stream costs a thread and a socket.
            self.send_error(503)
            return
        try:
            self._stream_forever(client)
        finally:
            state.streams.release(client)

    def _stream_forever(self, client: Any) -> None:
        application = self.server.application
        config = application.config
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        # A peer that stops reading must not pin this thread forever. The
        # unbounded default is the real shutdown risk here, not server_close.
        with contextlib.suppress(OSError):
            self.connection.settimeout(config.stream_write_timeout_sec)
        current = application.state.snapshot.current(
            (config.window_hours, False)
        )
        if current is not None:
            # Immediately, so a client learns where it is without waiting for
            # the next change.
            self._emit(current[0])
        while not client.closed:
            revision = client.wait(timeout=config.stream_heartbeat_sec)
            if client.closed:
                return
            if revision is None:
                if not self._write_raw(b": keepalive\n\n"):
                    return
                continue
            if not self._emit(revision):
                return

    def _emit(self, revision: Any) -> bool:
        rendered = runtime_snapshot.format_revision(revision)
        payload = f"id: {rendered}\nevent: revision\ndata: {rendered}\n\n"
        return self._write_raw(payload.encode())

    def _write_raw(self, payload: bytes) -> bool:
        """Write and flush, reporting whether the peer is still there.

        No lock is held here. A blocked write must never be able to stall a
        publisher or a collection.
        """
        try:
            self.wfile.write(payload)
            self.wfile.flush()
        except (OSError, ValueError):
            return False
        return True
```

Route it in `do_GET`, before the 404:

```python
        elif url.path == "/api/stream":
            self._stream()
```

- [ ] **Step 5: Run the tests**

```bash
python3 -m unittest cargento.skills.cargento.tests.test_http_api -v
python3 -m unittest discover -s cargento/skills/cargento/tests -t .
```

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -s -m "feat(http): serve a bounded SSE revision stream at /api/stream (DRC-4084)"
```

---

### Task 4: Close streams on shutdown

A stream handler blocks in `client.wait` for up to a heartbeat interval and then writes. `server.shutdown()` stops the accept loop but does not touch handler threads, and `daemon_threads` means nothing joins them. Shutdown must wake them so the process does not sit holding sockets it has promised to release.

**Files:**
- Modify: `cargento/skills/cargento/cargento_runtime/http_api.py` (`_shutdown`)
- Modify: `cargento/skills/cargento/cargento_runtime/lifecycle.py` (`serve` cleanup)
- Test: `cargento/skills/cargento/tests/test_http_api.py`, `cargento/skills/cargento/tests/test_lifecycle.py`

- [ ] **Step 1: Write the failing test**

```python
    def test_shutdown_closes_open_streams_promptly(self) -> None:
        # Open a stream, POST /api/shutdown, and assert the stream ends within
        # well under one heartbeat interval. Without close_all it would hang
        # until the heartbeat, and on a long heartbeat that reads as a hang.
```

Assert the read returns empty (peer closed) inside about two seconds, with the heartbeat patched high enough that a passing test cannot be the heartbeat firing.

- [ ] **Step 2: Run test to verify it fails**

Expected: the read blocks until the heartbeat rather than ending at shutdown.

- [ ] **Step 3: Write the implementation**

In `_shutdown`, before starting the shutdown thread:

```python
        # Wake every stream first. shutdown() stops the accept loop but never
        # touches handler threads, and a stream is asleep in wait() rather than
        # in the socket, so nothing else would tell it to stop.
        self.server.application.state.streams.close_all()
```

In `lifecycle.serve`'s `finally`, before `server_close()`:

```python
        with contextlib.suppress(Exception):
            server.application.state.streams.close_all()
```

so a `--stop`, a signal, or an exception all converge on the same cleanup.

- [ ] **Step 4: Run the tests**

```bash
python3 -m unittest cargento.skills.cargento.tests.test_http_api cargento.skills.cargento.tests.test_lifecycle -v
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -s -m "fix(http): wake and close open streams on shutdown (DRC-4084)"
```

---

### Task 5: The demand-scoped producer

**Files:**
- Modify: `cargento/skills/cargento/cargento_runtime/config.py` (`stream_producer_interval_sec`)
- Modify: `cargento/skills/cargento/cargento_runtime/lifecycle.py` (producer thread, started in `serve`)
- Test: `cargento/skills/cargento/tests/test_lifecycle.py`

**Interfaces:**
- Produces: `lifecycle.run_producer(server, *, stop: threading.Event) -> None`, and `serve` starting it after `write_state` and stopping it in the `finally`.

The producer collects on an interval **only while at least one stream is connected**. With zero clients it sleeps and touches nothing. Started inside `serve`, which on the daemon path runs after the fork, so the thread is never created in a process that is about to be replaced.

- [ ] **Step 1: Write the failing test**

```python
class ProducerTest(unittest.TestCase):
    def test_the_producer_does_nothing_with_no_connected_stream(self) -> None:
        # Run a few intervals with an empty registry and assert collect_json was
        # never called. This is the "idle daemon does zero filesystem work"
        # guarantee, and it is the one this whole phase most easily breaks.

    def test_the_producer_collects_while_a_stream_is_connected(self) -> None:
        # Register a client, run, assert collect_json was called at least once.

    def test_the_stop_event_ends_the_producer_promptly(self) -> None:
        # Set the event and assert the thread exits well inside one interval.

    def test_a_collection_error_does_not_kill_the_producer(self) -> None:
        # Make collect_json raise once, then succeed. The loop must survive:
        # a dead producer is a silently frozen dashboard.
```

Use a short interval and an injected stop event; never sleep for a real five seconds in a test.

- [ ] **Step 2: Run test to verify it fails**

Expected: `AttributeError: module 'cargento_runtime.lifecycle' has no attribute 'run_producer'`.

- [ ] **Step 3: Write the implementation**

```python
def run_producer(
    server: http_api.CargentoHTTPServer,
    *,
    stop: threading.Event,
    interval: float | None = None,
) -> None:
    """Keep the snapshot warm while at least one stream is connected.

    With no client this loop does nothing at all: no collection, no store
    access. An idle daemon costs what it costs today, which is nothing, and a
    timer that collected regardless would be the regression this phase exists
    to avoid.

    A collection failure is swallowed and retried on the next tick. The
    per-harness failure boundary already reports the cause, and a producer that
    died on one bad read would leave every connected dashboard frozen with no
    indication why.
    """
    application = server.application
    period = application.config.stream_producer_interval_sec if interval is None else interval
    while not stop.wait(period):
        if application.state.streams.count == 0:
            continue
        try:
            application.collect_json(show_all=False)
        except Exception as exc:  # noqa: BLE001 (a bad read must not stop the loop)
            runtime_io.diag(f"Cargento: producer collection failed: {exc}", print)
```

Import `threading` in `lifecycle.py` if it is not already imported.

In `serve`, after `write_state` and before `serve_forever`:

```python
    producer_stop = threading.Event()
    producer = threading.Thread(
        target=run_producer, args=(server,), kwargs={"stop": producer_stop}, daemon=True
    )
    producer.start()
```

and in the `finally`, before the stream cleanup:

```python
        producer_stop.set()
        producer.join(timeout=2)
```

- [ ] **Step 4: Run the tests**

```bash
python3 -m unittest cargento.skills.cargento.tests.test_lifecycle -v
python3 -m unittest discover -s cargento/skills/cargento/tests -t .
```

- [ ] **Step 5: Prove the idle guarantee end to end**

Start a daemon, leave it alone with no tab and no stream, and confirm it performs no collection: patch nothing, just watch that the snapshot's revision does not advance over several intervals.

```bash
cd cargento/skills/cargento
python3 server.py --port 4599 --daemon
sleep 12
curl -s -D - -o /dev/null http://127.0.0.1:4599/api/data | grep -i x-cargento-revision
python3 server.py --stop --port 4599
```

The first GET must report revision counter 1: nothing collected before it asked.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -s -m "feat(lifecycle): collect on an interval only while a stream is connected (DRC-4084)"
```

---

### Task 6: Document it, then open the stacked PR

**Files:**
- Modify: `docs/design-runtime-architecture.md` (module table)
- Modify: `docs/plans/event-driven-session-observation.md` (Phase 1 progress)
- Modify: `COMPATIBILITY.md` only if a per-OS caveat emerged in testing

- [ ] **Step 1: Update the module map**

Add a `stream.py` row: connected SSE clients and their one-slot mailboxes, importing no runtime module. Note that `state` owns the registry for the same reason it owns the snapshot.

- [ ] **Step 2: Update the design plan**

Mark the stream, budgets, heartbeats, shutdown and the demand-scoped producer as shipped in 1b, and record that the client, quota lease and time tick remain in 1c. Tone gate applies.

- [ ] **Step 3: Full gate**

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

- [ ] **Step 4: Commit and open the PR**

```bash
git push -u origin HEAD
gh pr create --base feature/drc-4084-phase-1-materialized-snapshot-and-sse-delivery
```

`--base` must be the Phase 1a branch. Verify with `gh pr view --json baseRefName`. The stack is now three deep: #83, #84, this. Each merge requires retargeting and rebasing the one above it.

---

## Self-Review

**Spec coverage against Phase 1's remaining bullets:**

| Requirement | Where |
|---|---|
| SSE revision stream, restart-qualified IDs | Task 3, ids are `format_revision` output |
| Immediate current-state delivery | Task 3 |
| Server-wide connection budget | Tasks 1, 3 |
| Read/write timeouts | Task 3, `settimeout` on the connection |
| One-slot queues | Task 1 |
| Heartbeats | Task 3 |
| Services start only after daemonization | Task 5, the producer starts inside `serve` |
| Shutdown order | Task 4 |
| Demand-scoped producer, stops with zero readers | Task 5 |
| Leader-tab election, browser reconnect | 1c |
| Time-derived field tick | 1c |
| Quota consent lease | 1c |
| `?all=1` stays on its polling fallback | By construction: the producer collects the default window only, and no client change lands here |

**Placeholder scan:** Tasks 3, 4 and 5 give test names with described assertions rather than full bodies, because each needs real socket or thread choreography whose exact shape depends on the neighbouring helpers. Every one names its file, its assertion and its failure mode. The implementation code is complete in all three.

**Type consistency:** `stream.Revision` and `snapshot.Revision` are both `tuple[float, int]`, pinned equal by a test in Task 1 Step 7 because the modules deliberately do not import each other. `StreamRegistry.register` returns `StreamClient | None` in Task 1 and every caller in Task 3 checks for None. `run_producer` takes a keyword-only `stop` in Task 5 and `serve` passes it that way.
