"""Live delivery: leader election, the SSE stream, and the fallback poll.

Executed under node against the real page script, like every other page test:
string assertions on this logic would rot silently, executed ones do not.
"""

from __future__ import annotations

import json
from typing import Any

from .page_harness import PageJsHarness


class PageLiveTest(PageJsHarness):
    @staticmethod
    def prelude(
        *,
        lease: dict[str, object] | None = None,
        event_source: bool = True,
        storage: bool = True,
    ) -> str:
        """Globals the live path reads at load: storage, and EventSource.

        `lease` seeds an existing leader so a test can start as a follower.
        `event_source=False` is the browser that cannot stream at all.
        `storage=False` is private browsing, where setItem throws.
        """
        seed = "{}" if lease is None else json.dumps({"cargento.leader": json.dumps(lease)})
        store = (
            f"""
let __store = {seed};
const localStorage = {{
  getItem(k){{ return Object.prototype.hasOwnProperty.call(__store, k) ? __store[k] : null; }},
  setItem(k, v){{ __store[k] = String(v); }},
  removeItem(k){{ delete __store[k]; }}
}};
"""
            if storage
            else """
let __store = {};
const localStorage = {
  getItem(){ return null; },
  setItem(){ throw new Error("private browsing"); },
  removeItem(){ throw new Error("private browsing"); }
};
"""
        )
        source = (
            """
let __sources = [];
class EventSource {
  constructor(url){
    this.url = url;
    this.listeners = {};
    this.closed = false;
    __sources.push(this);
  }
  addEventListener(type, fn){ (this.listeners[type] = this.listeners[type] || []).push(fn); }
  close(){ this.closed = true; }
  emit(type, data){ (this.listeners[type] || []).forEach(f => f({data})); }
}
"""
            if event_source
            else "\n"
        )
        return (
            store
            + source
            + """
const setTimeout = fn => { fn(); return 1; };
"""
        )

    SAMPLE = (
        '{"generated": 1000, "sessions": [], "harnesses": [], '
        '"native_notify": "", "show_all": false}'
    )

    def _boot(self, checks: str, **prelude: Any) -> Any:
        fixture = f"""
__els.app = {{className: "", innerHTML: ""}};
__fetchImpl = () => Promise.resolve({{ok: true, json: () => Promise.resolve({self.SAMPLE})}});
"""
        return self._run_page_js(fixture + checks, prelude=self.prelude(**prelude))

    def test_a_lone_tab_becomes_leader_and_opens_one_stream(self) -> None:
        out = self._boot(
            """
await __settle();
console.log(JSON.stringify({
  sources: __sources.length,
  url: __sources.length ? __sources[0].url : null,
  leader: JSON.parse(__store["cargento.leader"] || "null"),
}));
"""
        )
        self.assertEqual(1, out["sources"], "a lone tab must stream")
        self.assertEqual("/api/stream", out["url"])
        self.assertIsNotNone(out["leader"])

    def test_a_follower_opens_no_stream_while_a_fresh_lease_is_held(self) -> None:
        """The six-connection-per-origin cap is why this matters.

        Every tab holding an EventSource burns one of the browser's six
        connections to this origin. Past that, fetches queue forever and the
        board freezes behind a healthy-looking indicator.
        """
        out = self._boot(
            """
await __settle();
console.log(JSON.stringify({sources: __sources.length}));
""",
            lease={"id": "another-tab", "ts": 1000 * 1000},
        )
        self.assertEqual(0, out["sources"], "a follower must not hold a connection")

    def test_a_stale_lease_is_taken_over(self) -> None:
        """A leader that closed its tab must not strand every follower."""
        out = self._boot(
            """
await __settle();
const before = __sources.length;
__setNow(1000 + 60);           // the old lease is now far past stale
__runInterval(2000);           // the election tick
await __settle();
console.log(JSON.stringify({before, after: __sources.length}));
""",
            lease={"id": "dead-tab", "ts": 1000 * 1000},
        )
        self.assertEqual(0, out["before"])
        self.assertEqual(1, out["after"], "a stale lease must be claimed")

    def test_a_revision_event_refetches_and_fans_out_to_followers(self) -> None:
        out = self._boot(
            """
await __settle();
const before = __fetchCalls.length;
__sources[0].emit("revision", "1700000000.7");
await __settle();
console.log(JSON.stringify({
  fetched: __fetchCalls.length > before,
  broadcast: __store["cargento.revision"],
}));
"""
        )
        self.assertTrue(out["fetched"], "a revision must trigger a refetch")
        self.assertEqual("1700000000.7", out["broadcast"], "followers learn through storage")

    def test_a_repeated_revision_does_not_refetch(self) -> None:
        """The stream replays its last id on reconnect, so this is not theory."""
        out = self._boot(
            """
await __settle();
__sources[0].emit("revision", "1700000000.7");
await __settle();
const after_first = __fetchCalls.length;
__sources[0].emit("revision", "1700000000.7");
await __settle();
console.log(JSON.stringify({after_first, after_repeat: __fetchCalls.length}));
"""
        )
        self.assertEqual(out["after_first"], out["after_repeat"])

    def test_a_follower_refetches_on_a_storage_broadcast(self) -> None:
        out = self._boot(
            """
await __settle();
const before = __fetchCalls.length;
__fire("window:storage", {key: "cargento.revision", newValue: "1700000000.9"});
await __settle();
console.log(JSON.stringify({fetched: __fetchCalls.length > before}));
""",
            lease={"id": "another-tab", "ts": 1000 * 1000},
        )
        self.assertTrue(out["fetched"], "a follower must follow the leader's revisions")

    def test_the_five_second_poll_is_gone_when_streaming_is_available(self) -> None:
        out = self._boot(
            """
await __settle();
console.log(JSON.stringify({periods: __intervalPeriods()}));
"""
        )
        self.assertNotIn(5000, out["periods"], "the five-second poll must not survive")

    def test_a_browser_without_eventsource_keeps_the_five_second_poll(self) -> None:
        """Degrade to today's behaviour rather than to a frozen board."""
        out = self._boot(
            """
await __settle();
console.log(JSON.stringify({periods: __intervalPeriods()}));
""",
            event_source=False,
        )
        self.assertIn(5000, out["periods"])

    def test_a_slow_fallback_poll_survives_alongside_the_stream(self) -> None:
        """A safety net: no election or stream bug may leave the page frozen."""
        out = self._boot(
            """
await __settle();
const before = __fetchCalls.length;
__runInterval(20000);
await __settle();
console.log(JSON.stringify({fetched: __fetchCalls.length > before}));
"""
        )
        self.assertTrue(out["fetched"])

    def test_private_browsing_still_streams(self) -> None:
        """setItem throws with no storage, and the page must not die on it."""
        out = self._boot(
            """
await __settle();
console.log(JSON.stringify({sources: __sources.length}));
""",
            storage=False,
        )
        self.assertEqual(1, out["sources"], "no storage means every tab leads itself")

    def test_stopping_the_server_closes_the_stream(self) -> None:
        out = self._boot(
            """
await __settle();
stopLive();
console.log(JSON.stringify({closed: __sources[0].closed}));
"""
        )
        self.assertTrue(out["closed"], "a terminal stop must not leave a stream open")

    def test_a_leader_yields_to_a_foreign_lease_even_when_that_lease_is_stale(self) -> None:
        """The throttled-tab bug: two hidden tabs each streaming forever.

        Chrome throttles a hidden page's timers to about one wake-up a minute,
        far past the six-second stale window, so a leader routinely reads a
        stale foreign lease. Yielding only on a *live* one let both tabs stomp
        each other's lease and keep a stream, which is exactly the connection
        exhaustion the election exists to prevent.
        """
        out = self._boot(
            """
await __settle();
const led = isLeader && __sources.length === 1;
// Another tab claims it, then time moves far past stale for both.
__store["cargento.leader"] = JSON.stringify({id: "other-tab", ts: 1000 * 1000});
__setNow(1000 + 600);
__runInterval(2000);
await __settle();
console.log(JSON.stringify({led, stillLeader: isLeader, closed: __sources[0].closed}));
"""
        )
        self.assertTrue(out["led"], "the tab must start as leader for this to mean anything")
        self.assertFalse(out["stillLeader"], "a foreign lease must demote, stale or not")
        self.assertTrue(out["closed"], "demotion must close the stream")

    def test_a_closed_stream_is_reopened_rather_than_held_dead(self) -> None:
        """A 503 past the server's cap fails the connection permanently.

        readyState goes to CLOSED and the browser must not reconnect, so without
        an error listener the tab would hold a dead source, keep the lease, and
        never recover: the whole browser silently degrades to the slow poll.
        """
        out = self._boot(
            """
await __settle();
const first = __sources.length;
__sources[0].readyState = 2;              // CLOSED, as a 503 leaves it
__sources[0].emit("error", null);
const yielded = !isLeader;
__runInterval(2000);                      // the next election tick
await __settle();
console.log(JSON.stringify({first, yielded, sources: __sources.length}));
"""
        )
        self.assertEqual(1, out["first"])
        self.assertTrue(out["yielded"], "a dead stream must yield leadership")
        self.assertEqual(2, out["sources"], "the next tick must open a fresh stream")

    def test_a_storage_event_cannot_refetch_after_the_server_is_stopped(self) -> None:
        """The stopped panel is terminal; the storage listener outlives stopLive."""
        out = self._boot(
            """
await __settle();
serverStopped = true;
stopLive();
const before = __fetchCalls.length;
__fire("window:storage", {key: "cargento.revision", newValue: "1700000000.42"});
await __settle();
console.log(JSON.stringify({fetched: __fetchCalls.length > before}));
"""
        )
        self.assertFalse(out["fetched"], "nothing may repaint a board for a server that is gone")

    def test_a_leader_hands_its_lease_back_when_the_page_hides(self) -> None:
        out = self._boot(
            """
await __settle();
const held = !!__store["cargento.leader"];
__fire("window:pagehide", {});
console.log(JSON.stringify({held, after: __store["cargento.leader"] || null}));
"""
        )
        self.assertTrue(out["held"])
        self.assertIsNone(out["after"], "handoff must not cost the full stale window")
