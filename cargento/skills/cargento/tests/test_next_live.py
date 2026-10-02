from __future__ import annotations

import json
import shutil
import unittest
from typing import Any

from cargento_runtime.web import page as frontend_page

from .next_harness import NextPageJsHarness


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextLiveBehaviorTest(NextPageJsHarness):
    PAYLOAD = (
        '{"generated":1000,"window_hours":24,"summary":{"working":0,'
        '"needs_input":0},"harnesses":[],"sessions":[]}'
    )

    @staticmethod
    def prelude(
        *,
        store: dict[str, str] | None = None,
        event_source: bool = True,
        storage: bool = True,
    ) -> str:
        seed = json.dumps(store or {})
        storage_stub = (
            f"""
let __store = {seed};
let __storageReads = [];
let __storageWrites = [];
let __storageRemoves = [];
const localStorage = {{
  getItem(k){{
    __storageReads.push(k);
    return Object.prototype.hasOwnProperty.call(__store, k) ? __store[k] : null;
  }},
  setItem(k, v){{ __storageWrites.push(k); __store[k] = String(v); }},
  removeItem(k){{ __storageRemoves.push(k); delete __store[k]; }}
}};
"""
            if storage
            else """
let __store = {};
let __storageReads = [];
let __storageWrites = [];
let __storageRemoves = [];
const localStorage = {
  getItem(k){ __storageReads.push(k); return null; },
  setItem(k){ __storageWrites.push(k); throw new Error("private browsing"); },
  removeItem(k){ __storageRemoves.push(k); throw new Error("private browsing"); }
};
"""
        )
        source_stub = """
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
  emit(type, data){ (this.listeners[type] || []).forEach(fn => fn({data})); }
}
"""
        return storage_stub + (source_stub if event_source else "let __sources = [];\n")

    def _boot(self, checks: str, **prelude: Any) -> Any:
        fixture = f"""
location.search = "";
__els.app = {{innerHTML: ""}};
let __nextShouldFail = false;
__fetchImpl = async () => __nextShouldFail
  ? {{ok: false, json: async () => ({{}})}}
  : {{ok: true, json: async () => ({self.PAYLOAD})}};
"""
        return self._run_page_js(fixture + checks, prelude=self.prelude(**prelude))

    def test_a_poll_does_not_close_the_list_the_reader_is_choosing_from(self) -> None:
        """The one lane the redraw cannot rebuild from a key.

        `renderNext` replaces the whole of `#app` and every other reader-state
        lane is put back afterwards from a key: focus, carets, drafts,
        disclosures. A native option popup has neither a key nor an API to
        reopen it, so a poll landing mid-choice shuts the list. Measured on
        Projects, where the stage-condition dropdown closed before a selection
        could be made.
        """
        out = self._boot(
            """
await refreshNext();
let renders = 0;
const paint = renderNext;
renderNext = (...args) => { renders += 1; return paint(...args); };

const choice = {tagName: "SELECT"};
__els.app.contains = node => node === choice;
document.activeElement = choice;

await refreshNext();
await refreshNext();
const whileOpen = renders;
const pending = !!nextDeferredRender;

document.activeElement = null;
__fire("blur", {target: choice});
const afterBlur = renders;

document.activeElement = choice;
await refreshNext(true);
const afterManual = renders;

console.log(JSON.stringify({whileOpen, pending, afterBlur, afterManual}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual(0, out["whileOpen"], "a poll repainted under an open list")
        self.assertTrue(out["pending"], "the deferred paint was dropped rather than held")
        self.assertEqual(1, out["afterBlur"], "the board did not catch up when the list closed")
        # A manual refresh is the reader asking for a redraw, so it paints even
        # over an open list rather than being swallowed by the same guard.
        self.assertGreater(out["afterManual"], out["afterBlur"])

    def test_a_committed_choice_catches_the_board_up_without_waiting_for_blur(self) -> None:
        """A keyboard selection commits while the list still holds focus."""
        out = self._boot(
            """
await refreshNext();
let renders = 0;
const paint = renderNext;
renderNext = (...args) => { renders += 1; return paint(...args); };

const choice = {tagName: "SELECT"};
__els.app.contains = node => node === choice;
document.activeElement = choice;
await refreshNext();
const whileOpen = renders;

__fire("change", {target: choice});
console.log(JSON.stringify({whileOpen, afterChange: renders}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual(0, out["whileOpen"])
        self.assertEqual(1, out["afterChange"], "committing a choice left the board stale")

    def test_a_list_left_focused_cannot_freeze_the_board(self) -> None:
        """The bound, because a board that never repaints is the worse failure."""
        out = self._boot(
            """
await refreshNext();
let renders = 0;
const paint = renderNext;
renderNext = (...args) => { renders += 1; return paint(...args); };

const choice = {tagName: "SELECT"};
__els.app.contains = node => node === choice;
document.activeElement = choice;

for(let i = 0; i < NEXT_MAX_DEFERRED_RENDERS + 2; i += 1) await refreshNext();
console.log(JSON.stringify({cap: NEXT_MAX_DEFERRED_RENDERS, renders}));
"""
        )
        assert isinstance(out, dict)
        # Deferrals stop at the cap and the board repaints from then on, so the
        # count is the number of polls past it rather than zero.
        self.assertEqual(2, out["renders"], "the cap did not release the board")
        self.assertEqual(12, out["cap"])

    def test_polling_fallback_elects_and_renews_one_stage_notification_owner(self) -> None:
        for store, expected in (
            ({}, 1),
            ({"cargento.next.leader": json.dumps({"id": "other", "ts": 1e15})}, 0),
        ):
            with self.subTest(owner=expected):
                out = self._boot(
                    """
await __settle();
__notifyPermission = "granted";
nextSyncNotifications({sessions:[],tripwires:{enabled:true,rules:[]}});
nextSyncNotifications({sessions:[],tripwires:{enabled:true,rules:[{event_id:"stage:new",workflow:"flow",why:"Observed entry"}]}});
console.log(JSON.stringify({notifications:__notifications.length,leader:nextIsLeader,
  periods:__intervals.map(item=>item.ms),sources:__sources.length}));
""",
                    event_source=False,
                    store=store,
                )
                self.assertEqual(expected, out["notifications"])
                self.assertEqual(bool(expected), out["leader"])
                self.assertIn(2000, out["periods"])
                self.assertEqual(0, out["sources"])

    def test_a_lone_next_tab_becomes_leader_and_opens_one_stream(self) -> None:
        out = self._boot(
            """
await __settle();
console.log(JSON.stringify({
  sources: __sources.length,
  url: __sources.length ? __sources[0].url : null,
  leader: JSON.parse(__store["cargento.next.leader"] || "null")
}));
"""
        )

        self.assertEqual(1, out["sources"])
        self.assertEqual("/api/stream", out["url"])
        self.assertIsNotNone(out["leader"])

    def test_a_second_next_tab_follows_a_fresh_next_lease(self) -> None:
        out = self._boot(
            """
await __settle();
console.log(JSON.stringify({sources: __sources.length, periods: __intervalPeriods()}));
""",
            store={
                "cargento.next.leader": json.dumps({"id": "another-next-tab", "ts": 1000 * 1000})
            },
        )

        self.assertEqual(0, out["sources"])
        self.assertIn(20_000, out["periods"])

    def test_a_stale_next_lease_is_taken_over(self) -> None:
        out = self._boot(
            """
await __settle();
const before = __sources.length;
__setNow(1060);
__runInterval(2000);
await __settle();
console.log(JSON.stringify({before, after: __sources.length}));
""",
            store={"cargento.next.leader": json.dumps({"id": "dead-next-tab", "ts": 1000 * 1000})},
        )

        self.assertEqual(0, out["before"])
        self.assertEqual(1, out["after"])

    def test_a_leader_yields_to_a_foreign_lease_even_after_it_goes_stale(self) -> None:
        out = self._boot(
            """
await __settle();
const led = nextIsLeader && __sources.length === 1;
__store["cargento.next.leader"] = JSON.stringify({id: "other-tab", ts: 1000 * 1000});
__setNow(1600);
__runInterval(2000);
await __settle();
console.log(JSON.stringify({led, stillLeader: nextIsLeader, closed: __sources[0].closed}));
"""
        )

        self.assertTrue(out["led"])
        self.assertFalse(out["stillLeader"])
        self.assertTrue(out["closed"])

    def test_the_next_bundle_never_touches_the_legacy_lease(self) -> None:
        legacy = {
            "cargento.leader": json.dumps({"id": "old-tab", "ts": 1000 * 1000}),
            "cargento.revision": "old-revision",
        }
        out = self._boot(
            """
await __settle();
console.log(JSON.stringify({
  sources: __sources.length,
  leader: __store["cargento.leader"],
  revision: __store["cargento.revision"],
  reads: __storageReads,
  writes: __storageWrites,
  removes: __storageRemoves
}));
""",
            store=legacy,
        )

        self.assertEqual(1, out["sources"], "the old lease must not make a next tab follow")
        self.assertEqual(legacy["cargento.leader"], out["leader"])
        self.assertEqual(legacy["cargento.revision"], out["revision"])
        for accesses in (out["reads"], out["writes"], out["removes"]):
            self.assertNotIn("cargento.leader", accesses)
            self.assertNotIn("cargento.revision", accesses)

    def test_a_revision_refetches_and_fans_out_on_the_next_key(self) -> None:
        out = self._boot(
            """
await __settle();
const before = __fetchCalls.length;
__sources[0].emit("revision", "1700000000.7");
await __settle();
console.log(JSON.stringify({
  fetched: __fetchCalls.length > before,
  revision: __store["cargento.next.revision"]
}));
"""
        )

        self.assertTrue(out["fetched"])
        self.assertEqual("1700000000.7", out["revision"])

    def test_a_replayed_stream_revision_does_not_refetch(self) -> None:
        out = self._boot(
            """
await __settle();
__sources[0].emit("revision", "1700000000.7");
await __settle();
const afterFirst = __fetchCalls.length;
__sources[0].emit("revision", "1700000000.7");
await __settle();
console.log(JSON.stringify({afterFirst, afterReplay: __fetchCalls.length}));
"""
        )

        self.assertEqual(out["afterFirst"], out["afterReplay"])

    def test_a_next_follower_refetches_on_the_namespaced_broadcast(self) -> None:
        out = self._boot(
            """
await __settle();
const before = __fetchCalls.length;
__fire("window:storage", {key: "cargento.next.revision", newValue: "1700000000.9"});
await __settle();
console.log(JSON.stringify({fetched: __fetchCalls.length > before}));
""",
            store={
                "cargento.next.leader": json.dumps({"id": "another-next-tab", "ts": 1000 * 1000})
            },
        )

        self.assertTrue(out["fetched"])

    def test_streaming_replaces_the_fast_poll_but_keeps_the_safety_poll(self) -> None:
        out = self._boot(
            """
await __settle();
console.log(JSON.stringify({periods: __intervalPeriods()}));
"""
        )

        self.assertIn(2_000, out["periods"])
        self.assertIn(20_000, out["periods"])
        self.assertNotIn(5_000, out["periods"])

    def test_a_browser_without_eventsource_keeps_the_fast_poll(self) -> None:
        out = self._boot(
            """
await __settle();
console.log(JSON.stringify({periods: __intervalPeriods()}));
""",
            event_source=False,
        )

        self.assertIn(5_000, out["periods"])
        self.assertNotIn(20_000, out["periods"])

    def test_a_closed_stream_falls_back_and_reopens_on_the_election_tick(self) -> None:
        out = self._boot(
            """
await __settle();
__sources[0].readyState = 2;
__sources[0].emit("error", null);
const yielded = !nextIsLeader;
const beforePoll = __fetchCalls.length;
__runInterval(20000);
await __settle();
const fallbackFetched = __fetchCalls.length > beforePoll;
__runInterval(2000);
await __settle();
console.log(JSON.stringify({
  yielded,
  closed: __sources[0].closed,
  fallbackFetched,
  sources: __sources.length
}));
"""
        )

        self.assertTrue(out["yielded"])
        self.assertTrue(out["closed"])
        self.assertTrue(out["fallbackFetched"])
        self.assertEqual(2, out["sources"])

    def test_failed_fallback_polls_explain_the_streaming_retry_cadence(self) -> None:
        html = self._boot(
            """
await __settle();
__sources[0].readyState = 2;
__sources[0].emit("error", null);
__nextShouldFail = true;
__runInterval(20000);
await __settle();
__runInterval(20000);
await __settle();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )

        self.assertIn('data-next-state="stalled"', html)
        self.assertIn("Live refresh failed twice in a row", html)
        self.assertIn("No data has been received in this tab", html)
        self.assertIn("Retrying automatically every 20s", html)
        self.assertNotIn("stream stopped", html.lower())

    def test_refresh_classifies_before_publishing_and_retains_the_last_success(self) -> None:
        out = self._boot(
            """
await refreshNext();
const retainedData = nextData;
const retainedAttention = nextAttention;
const firstKeys = nextAttention.needs.map(subject => subject.key);
const retainedHtml = __els.app.innerHTML;
const classify = nextAttentionModel;
nextAttentionModel = payload => {
  if(payload.generated === 2000) throw new Error("classifier rejected payload");
  return classify(payload);
};
__fetchImpl = async () => ({ok: true, json: async () => ({
  generated: 2000,
  window_hours: 24,
  summary: {working: 0, needs_input: 0},
  harnesses: [],
  asks: [{id: "new", question: "Replace retained state", session_id: "new"}],
  sessions: [{harness: "codex", sid: "new", project: "new", state: "needs_input"}]
})});
await refreshNext();
console.log(JSON.stringify({
  sameData: nextData === retainedData,
  sameAttention: nextAttention === retainedAttention,
  firstKeys,
  retainedKeys: nextAttention.needs.map(subject => subject.key),
  retainedHtml,
  html: __els.app.innerHTML,
  failures: nextRefreshFailures
}));
"""
        )

        self.assertTrue(out["sameData"])
        self.assertTrue(out["sameAttention"])
        self.assertEqual(out["firstKeys"], out["retainedKeys"])
        self.assertEqual(out["retainedHtml"], out["html"])
        self.assertEqual(1, out["failures"])
        self.assertNotIn("Live refresh failed", out["html"])

    def test_older_automatic_refresh_cannot_overwrite_newer_manual_recovery(self) -> None:
        out = self._boot(
            """
await refreshNext();
let releaseAutomatic = null;
let releaseManual = null;
let request = 0;
__fetchImpl = async () => new Promise(resolve => {
  request += 1;
  if(request === 1) releaseAutomatic = resolve;
  else releaseManual = resolve;
});
const automatic = refreshNext();
const manual = refreshNext(true);
releaseManual({ok: true, json: async () => ({
  generated: 3000,
  window_hours: 24,
  summary: {working: 0, needs_input: 1},
  harnesses: [],
  asks: [{id: "newer", question: "Keep newer", session_id: "newer"}],
  sessions: [{harness: "codex", sid: "newer", project: "newer", state: "needs_input"}]
})});
await manual;
const afterManual = {
  generated: nextData.generated,
  keys: nextAttention.needs.map(subject => subject.key),
  html: __els.app.innerHTML,
  failures: nextRefreshFailures
};
releaseAutomatic({ok: true, json: async () => ({
  generated: 2000,
  window_hours: 24,
  summary: {working: 0, needs_input: 1},
  harnesses: [],
  asks: [{id: "older", question: "Do not restore older", session_id: "older"}],
  sessions: [{harness: "claude", sid: "older", project: "older", state: "needs_input"}]
})});
await automatic;
console.log(JSON.stringify({
  afterManual,
  final: {
    generated: nextData.generated,
    keys: nextAttention.needs.map(subject => subject.key),
    html: __els.app.innerHTML,
    failures: nextRefreshFailures
  }
}));
"""
        )

        self.assertEqual(3000, out["afterManual"]["generated"])
        self.assertEqual(out["afterManual"], out["final"])
        self.assertIn('data-next-session="newer"', out["final"]["html"])
        self.assertNotIn('data-next-session="older"', out["final"]["html"])
        self.assertEqual(0, out["final"]["failures"])

    HELD_GETS = """
await __settle(); await __settle();
const releases = [];
let paints = 0;
const paint = renderNext;
renderNext = (...args) => { paints += 1; return paint(...args); };
const payload = generated => ({ok: true, headers: {get: name =>
    name === "X-Cargento-Revision" ? `1700.${generated}` : null},
  json: async () => ({generated, window_hours: 24, summary: {working: 0, needs_input: 0},
    harnesses: [], sessions: []})});
__fetchImpl = async () => new Promise(resolve => { releases.push(resolve); });
"""

    def test_a_reader_whose_save_is_followed_by_stream_wakes_sees_one_paint_after_at_most_two_data_fetches(
        self,
    ) -> None:
        out = self._boot(
            self.HELD_GETS
            + """
// The save's own awaited refresh, then the stream's wakes for the collections it caused.
const saved = refreshNext();
await __settle();
__sources[0].emit("revision", "1700.5");
__sources[0].emit("revision", "1700.6");
await __settle();
const queuedGets = releases.length;
releases[0](payload(5)); await __settle(); await __settle();
const paintsAfterFirst = paints;
releases[1](payload(6));
await saved;
await __settle();
console.log(JSON.stringify({queuedGets, gets: releases.length, paintsAfterFirst, paints,
  generated: nextData.generated}));
"""
        )
        self.assertEqual(1, out["queuedGets"])
        self.assertEqual(2, out["gets"])
        self.assertEqual(0, out["paintsAfterFirst"], "the dropped answer was painted")
        self.assertEqual(1, out["paints"])
        self.assertEqual(6, out["generated"])

    def test_a_refresh_awaited_after_a_write_is_answered_by_a_fetch_that_started_after_it(
        self,
    ) -> None:
        out = self._boot(
            self.HELD_GETS
            + """
const before = refreshNext();
await __settle();
// The write lands here; the awaited refresh must not resolve on the fetch already out.
let resolved = false;
const after = refreshNext().then(() => { resolved = true; });
releases[0](payload(1)); await __settle(); await __settle(); await __settle();
const early = resolved;
releases[1](payload(2)); await after; await before;
console.log(JSON.stringify({early, resolved, generated: nextData.generated}));
"""
        )
        self.assertFalse(out["early"])
        self.assertTrue(out["resolved"])
        self.assertEqual(2, out["generated"])

    def test_a_stream_revision_this_tab_already_fetched_fetches_nothing(self) -> None:
        out = self._boot(
            self.HELD_GETS
            + """
const first = refreshNext(); await __settle();
releases[0](payload(9)); await first; await __settle();
const counts = [];
for(const revision of ["1700.9", "1700.8", "1700.10", "1800.1"]){
  const before = releases.length;
  __sources[0].emit("revision", revision);
  await __settle();
  counts.push(releases.length - before);
  if(releases.length > before){ releases[releases.length - 1](payload(10)); await __settle(); }
}
console.log(JSON.stringify({counts, wrote: __storageWrites.filter(k =>
  k === "cargento.next.revision").length}));
"""
        )
        # Already fetched, older, newer, and a restart (a new start stamp is always newer).
        self.assertEqual([0, 0, 1, 1], out["counts"])
        # Only the stream's own announcements are broadcast; a GET never writes the key.
        self.assertEqual(2, out["wrote"])

    def test_private_browsing_still_streams(self) -> None:
        out = self._boot(
            """
await __settle();
console.log(JSON.stringify({sources: __sources.length}));
""",
            storage=False,
        )

        self.assertEqual(1, out["sources"])

    def test_pagehide_releases_only_the_next_lease(self) -> None:
        legacy = json.dumps({"id": "old-tab", "ts": 1000 * 1000})
        out = self._boot(
            """
await __settle();
const held = !!__store["cargento.next.leader"];
__fire("window:pagehide", {});
console.log(JSON.stringify({
  held,
  next: __store["cargento.next.leader"] || null,
  legacy: __store["cargento.leader"]
}));
""",
            store={"cargento.leader": legacy},
        )

        self.assertTrue(out["held"])
        self.assertIsNone(out["next"])
        self.assertEqual(legacy, out["legacy"])

    def test_next_live_source_contains_no_legacy_key_literal(self) -> None:
        path = frontend_page.WEB_DIR / "next-live.js"
        if not path.is_file():
            self.fail("next-live.js does not exist")
        source = path.read_text(encoding="utf-8")

        self.assertNotIn("cargento.leader", source)
        self.assertNotIn("cargento.revision", source)
