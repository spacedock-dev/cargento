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
