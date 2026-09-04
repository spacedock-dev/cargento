from __future__ import annotations

import shutil
import unittest

from .next_harness import NextPageJsHarness, storage_prelude

CONSENT_KEY = "cargento.next.usage.consent"

# One payload, three windows, chosen so the ranking rule is testable rather than
# asserted. Elapsed is (windowSec - (resetAt - generated)) / windowSec, so:
#   claude 5-hour   78% used, 55% elapsed -> budget ends ~47m from now
#   codex  5-hour   34% used, 12% elapsed -> budget ends ~70m from now
#   codex  weekly   88% used, 91% elapsed -> lasts to reset with room to spare
# The highest level is the one that is fine, and a window a third spent is not.
GENERATED = 1_700_000_000
# `.replace` rather than a format string: the payload is JavaScript and every
# brace in it would have to be doubled to survive one.
PAYLOAD = """
nextData = {
  generated: __GENERATED__,
  window_hours: 24,
  summary: {working: 0, needs_input: 0},
  sessions: [],
  asks: [],
  harnesses: [
    {key: "claude", label: "Claude Code", discovered: true, error: null},
    {key: "codex", label: "Codex", discovered: true, error: null}
  ],
  usage_fetch: true,
  usage: [
    {harness: "claude", state: "ok", asOf: __GENERATED__,
     fiveH: {pct: 78, windowSec: 18000, resetAt: __GENERATED__ + 8100}},
    {harness: "codex", state: "ok", asOf: __GENERATED__,
     fiveH: {pct: 34, windowSec: 18000, resetAt: __GENERATED__ + 15840},
     week: {pct: 88, windowSec: 604800, resetAt: __GENERATED__ + 54432}}
  ]
};
""".replace("__GENERATED__", str(GENERATED))


@unittest.skipUnless(shutil.which("node"), "node not available")
class UsageConsentGateTest(NextPageJsHarness):
    """`usage=1` is the page's consent, so the page must not send it by accident.

    The server fires the credential-backed fetch for no request that omits the
    parameter, which makes this builder the whole of the consent gate. Until
    2026-09-04 the page had no disclosure at all and sent the parameter never,
    so the contract in SECURITY.md was satisfied only because the feature never
    acted. These tests are the binding that keeps both halves true together.
    """

    def _poll_url(self, prelude: str) -> list[str]:
        out = self._run_page_js(
            PAYLOAD
            + """
await __settle();
console.log(JSON.stringify(__fetchCalls.map(call => call[0])));
""",
            prelude
            + """
__els.app = {innerHTML: ""};
__fetchImpl = async () => ({ok: true, json: async () => ({
  window_hours: 24,
  summary: {working: 0, needs_input: 0},
  sessions: []
})});
""",
        )
        assert isinstance(out, list)
        return out

    def test_an_unanswered_disclosure_sends_no_usage_parameter(self) -> None:
        # The default, and the one that must never drift: a reader who has been
        # asked nothing has agreed to nothing, so no credential is read.
        self.assertEqual(["/api/data"], self._poll_url(storage_prelude({})))

    def test_a_declined_disclosure_sends_no_usage_parameter(self) -> None:
        self.assertEqual(["/api/data"], self._poll_url(storage_prelude({CONSENT_KEY: "declined"})))

    def test_an_unrecognised_stored_answer_is_treated_as_unanswered(self) -> None:
        # A tampered or half-written value must fall to the safe side rather
        # than to whichever branch a truthiness test happens to take.
        self.assertEqual(["/api/data"], self._poll_url(storage_prelude({CONSENT_KEY: "yes"})))

    def test_a_granted_disclosure_carries_the_usage_parameter(self) -> None:
        self.assertEqual(
            ["/api/data?usage=1"], self._poll_url(storage_prelude({CONSENT_KEY: "granted"}))
        )

    def test_both_parameters_ride_the_same_request(self) -> None:
        # The server parses `all` and `usage` independently, so all four forms
        # are reachable and the builder must emit the pair rather than one.
        prelude = storage_prelude({CONSENT_KEY: "granted"}) + 'location.search = "?all=1";\n'
        self.assertEqual(["/api/data?all=1&usage=1"], self._poll_url(prelude))


@unittest.skipUnless(shutil.which("node"), "node not available")
class UsageDisclosureTest(NextPageJsHarness):
    def test_the_disclosure_names_the_credential_read_and_the_request(self) -> None:
        out = self._run_page_js(
            PAYLOAD
            + """
console.log(JSON.stringify({html: nextUsageDisclosure(nextData)}));
""",
            storage_prelude({}),
        )
        html = out["html"]
        self.assertIn("data-next-usage-consent", html)
        # The two facts a reader is consenting to. Asserted because a disclosure
        # that omits either is not one.
        self.assertIn("reading the credential", html)
        self.assertIn("once every five minutes", html)
        self.assertIn("--no-usage", html)

    def test_the_disclosure_is_absent_when_no_vendor_would_fetch(self) -> None:
        # A disk-read or pushed-receipt harness raises no capability flag, and
        # disclosing a request that will not happen trains the reader to dismiss
        # the one that will.
        out = self._run_page_js(
            PAYLOAD
            + """
nextData.usage_fetch = false;
console.log(JSON.stringify({html: nextUsageDisclosure(nextData)}));
""",
            storage_prelude({}),
        )
        self.assertEqual("", out["html"])

    def test_the_disclosure_is_absent_once_answered_and_the_switch_replaces_it(self) -> None:
        out = self._run_page_js(
            PAYLOAD
            + """
console.log(JSON.stringify({
  disclosure: nextUsageDisclosure(nextData),
  switch: nextUsageSwitch(nextData)
}));
""",
            storage_prelude({CONSENT_KEY: "granted"}),
        )
        self.assertEqual("", out["disclosure"])
        # The contract promises the setting can be changed later. This is it.
        self.assertIn('data-next-usage-answer="declined"', out["switch"])
        self.assertIn("Turn off", out["switch"])

    def test_answering_stores_the_answer_and_asks_for_the_fetch(self) -> None:
        out = self._run_page_js(
            PAYLOAD
            + """
__els.app = {innerHTML: ""};
navigateNext({view: "sessions", project: null, session: null});
const button = {dataset: {nextUsageAnswer: "granted"}};
__fire("click", {target: {closest: sel =>
  sel === "[data-next-usage-answer]" ? button : null}, preventDefault(){}});
await __settle();
console.log(JSON.stringify({
  stored: __store[CONSENT_KEY_LITERAL],
  writes: __storageWrites,
  calls: __fetchCalls.map(call => call[0])
}));
""".replace("CONSENT_KEY_LITERAL", '"' + CONSENT_KEY + '"'),
            storage_prelude({}),
        )
        self.assertEqual("granted", out["stored"])
        self.assertIn(CONSENT_KEY, out["writes"])
        # And the answer reaches the server on the very next request, rather
        # than waiting out a poll interval and reading as though it did nothing.
        self.assertIn("/api/data?usage=1", out["calls"])


@unittest.skipUnless(shutil.which("node"), "node not available")
class CapacityStripTest(NextPageJsHarness):
    def test_rows_rank_by_when_the_budget_ends_not_by_level(self) -> None:
        out = self._run_page_js(
            PAYLOAD
            + """
const rows = nextCapacityRows(nextData);
console.log(JSON.stringify(rows.map(row => ({
  harness: row.harness, slot: row.slot, pct: row.pct,
  elapsed: Math.round(row.elapsed * 100),
  ends: row.windowMinutesLeft == null ? null : Math.round(row.windowMinutesLeft)
}))));
""",
            storage_prelude({}),
        )
        assert isinstance(out, list)
        # The whole point of the surface: the highest percentage sorts LAST,
        # because it is the one with room, and a window a third spent sorts
        # above it because it runs dry first.
        self.assertEqual(
            [("claude", "fiveH", 78), ("codex", "fiveH", 34), ("codex", "week", 88)],
            [(row["harness"], row["slot"], row["pct"]) for row in out],
        )
        self.assertEqual([55, 12, 91], [row["elapsed"] for row in out])
        self.assertEqual([47, 70, 1251], [row["ends"] for row in out])

    def test_the_bar_carries_the_level_as_fill_and_the_clock_as_a_tick(self) -> None:
        out = self._run_page_js(
            PAYLOAD
            + """
const rows = nextCapacityRows(nextData);
console.log(JSON.stringify({html: nextCapacityRow(rows[0])}));
""",
            storage_prelude({}),
        )
        html = out["html"]
        self.assertIn("width:78%", html)
        self.assertIn("left:55.00%", html)
        # Both halves in the accessible label too, since the reading is the gap
        # between them and a screen reader gets no gap.
        self.assertIn("78% of budget used, 55% of the window elapsed", html)

    def test_a_window_with_no_published_length_gets_no_tick_and_no_projection(self) -> None:
        out = self._run_page_js(
            PAYLOAD
            + """
nextData.usage = [{harness: "claude", state: "ok", asOf: nextData.generated,
  month: {pct: 93, resetAt: nextData.generated + 86400}}];
const rows = nextCapacityRows(nextData);
console.log(JSON.stringify({
  count: rows.length,
  elapsed: rows[0].elapsed,
  ends: rows[0].windowMinutesLeft,
  html: nextCapacityRow(rows[0])
}));
""",
            storage_prelude({}),
        )
        self.assertEqual(1, out["count"])
        # Absent, not zero and not guessed. A missing length removes the claim.
        self.assertIsNone(out["elapsed"])
        self.assertIsNone(out["ends"])
        self.assertIn("next-capacity-noclock", out["html"])
        self.assertIn("not projected", out["html"])
        self.assertIn("publishes no clock", out["html"])

    def test_an_unreadable_entry_publishes_no_row(self) -> None:
        # `refused` and `lapsed` carry no figures at all, and a strip that
        # rendered them as 0% would read as an empty window rather than an
        # unknown one.
        out = self._run_page_js(
            PAYLOAD
            + """
nextData.usage = [
  {harness: "claude", state: "refused", asOf: nextData.generated},
  {harness: "claude", state: "lapsed", asOf: nextData.generated}
];
console.log(JSON.stringify({rows: nextCapacityRows(nextData).length}));
""",
            storage_prelude({}),
        )
        self.assertEqual(0, out["rows"])

    def test_no_window_means_no_strip_and_no_placeholder(self) -> None:
        out = self._run_page_js(
            PAYLOAD
            + """
nextData.usage = [];
nextData.usage_fetch = false;
console.log(JSON.stringify({html: nextCapacityView(nextData)}));
""",
            storage_prelude({}),
        )
        self.assertEqual("", out["html"])

    def test_the_prospect_states_both_paces_when_both_are_measured(self) -> None:
        out = self._run_page_js(
            PAYLOAD
            + """
nextData.usage[0].fiveH.recent = {pctPerMin: 0.2667, samples: 4, spanSec: 1800};
const rows = nextCapacityRows(nextData);
const row = rows.find(entry => entry.harness === "claude");
console.log(JSON.stringify({html: nextCapacityProspect(row, 3, "")}));
""",
            storage_prelude({}),
        )
        html = out["html"]
        # Two measured paces, never one fitted rate with a synthetic band: where
        # they disagree, that disagreement is the uncertainty.
        self.assertIn("at this window's average pace", html)
        self.assertIn("at the recent pace", html)
        self.assertIn("Measured while 3 agents were working", html)

    def test_the_prospect_says_so_when_the_recent_pace_is_unmeasured(self) -> None:
        out = self._run_page_js(
            PAYLOAD
            + """
const rows = nextCapacityRows(nextData);
const row = rows.find(entry => entry.harness === "claude");
console.log(JSON.stringify({html: nextCapacityProspect(row, 1, "")}));
""",
            storage_prelude({}),
        )
        self.assertIn("Recent pace not measured", out["html"])
        self.assertIn("1 agent was working", out["html"])

    def test_the_project_spread_comes_from_observed_spans(self) -> None:
        # A6's shape-match, keyed on project and duration rather than on prompt
        # text: the store keeps state transitions, and a session's span is the
        # distance between its first and last.
        out = self._run_page_js(
            PAYLOAD
            + """
nextData.history = [
  {harness: "claude", sid: "a", project: "recce/cargento", state: "working",
   last_activity: nextData.generated - 3600},
  {harness: "claude", sid: "a", project: "recce/cargento", state: "idle",
   last_activity: nextData.generated - 1800},
  {harness: "claude", sid: "b", project: "recce/cargento", state: "working",
   last_activity: nextData.generated - 900},
  {harness: "claude", sid: "b", project: "recce/cargento", state: "idle",
   last_activity: nextData.generated - 300}
];
console.log(JSON.stringify({html: nextCapacityProjectSpread(nextData)}));
""",
            storage_prelude({}),
        )
        html = out["html"]
        self.assertIn("recce/cargento", html)
        self.assertIn("from 2 observed", html)
        self.assertIn("10m", html)
        self.assertIn("30m", html)

    def test_one_observed_session_is_not_a_spread(self) -> None:
        out = self._run_page_js(
            PAYLOAD
            + """
nextData.history = [
  {harness: "claude", sid: "a", project: "p", state: "working",
   last_activity: nextData.generated - 600},
  {harness: "claude", sid: "a", project: "p", state: "idle",
   last_activity: nextData.generated - 60}
];
console.log(JSON.stringify({html: nextCapacityProjectSpread(nextData)}));
""",
            storage_prelude({}),
        )
        self.assertEqual("", out["html"])


@unittest.skipUnless(shutil.which("node"), "node not available")
class QuotaPaceAttentionTest(NextPageJsHarness):
    def test_pace_raises_the_window_a_level_threshold_misses(self) -> None:
        out = self._run_page_js(
            PAYLOAD
            + """
const model = nextAttentionModel(nextData);
const quota = model.risk.filter(subject => subject.kind === "quota");
console.log(JSON.stringify(quota.map(subject => ({
  key: subject.key,
  pct: subject.signals[0].detail.pct,
  reason: subject.signals[0].detail.reason
}))));
""",
            storage_prelude({}),
        )
        assert isinstance(out, list)
        raised = {row["key"]: row for row in out}
        # 34% used with 12% elapsed: below every level threshold, and it runs dry
        # about three hours before it resets.
        self.assertIn("quota:codex:fiveH", raised)
        self.assertEqual("pace", raised["quota:codex:fiveH"]["reason"])
        # 78% is over the level threshold and would have been raised anyway.
        self.assertEqual("level", raised["quota:claude:fiveH"]["reason"])

    def test_a_high_level_that_is_on_pace_is_raised_by_level_alone(self) -> None:
        # 88% used with 91% elapsed finishes the week with room to spare, so
        # pace must not claim it. The level trigger still raises it, unchanged,
        # because a nearly-spent window is worth seeing on its own terms.
        out = self._run_page_js(
            PAYLOAD
            + """
const model = nextAttentionModel(nextData);
const subject = model.risk.find(entry => entry.key === "quota:codex:week");
console.log(JSON.stringify({reason: subject.signals[0].detail.reason}));
""",
            storage_prelude({}),
        )
        self.assertEqual("level", out["reason"])

    def test_an_early_window_is_not_raised_on_a_noisy_ratio(self) -> None:
        # 5% used with 1% elapsed is a five-times pace over almost no time. A
        # signal that fires there is noise, and noise teaches the reader to
        # ignore the row that matters.
        out = self._run_page_js(
            PAYLOAD
            + """
nextData.usage = [{harness: "claude", state: "ok", asOf: nextData.generated,
  fiveH: {pct: 5, windowSec: 18000, resetAt: nextData.generated + 17820}}];
const model = nextAttentionModel(nextData);
console.log(JSON.stringify({
  quota: model.risk.filter(subject => subject.kind === "quota").length
}));
""",
            storage_prelude({}),
        )
        self.assertEqual(0, out["quota"])

    def test_a_few_points_spent_cannot_manufacture_a_pace(self) -> None:
        # The other floor. Half the window gone with 4% spent is a 0.08x pace,
        # nowhere near raising; but the mirror case matters — `pct` is an integer,
        # so a window barely touched must not raise on a ratio that one point of
        # rounding could have produced. 8% used with 11% elapsed clears the time
        # floor and is still held out by the budget floor.
        out = self._run_page_js(
            PAYLOAD
            + """
nextData.usage = [{harness: "claude", state: "ok", asOf: nextData.generated,
  fiveH: {pct: 8, windowSec: 18000, resetAt: nextData.generated + 16020}}];
const model = nextAttentionModel(nextData);
console.log(JSON.stringify({
  quota: model.risk.filter(subject => subject.kind === "quota").length
}));
""",
            storage_prelude({}),
        )
        self.assertEqual(0, out["quota"])
