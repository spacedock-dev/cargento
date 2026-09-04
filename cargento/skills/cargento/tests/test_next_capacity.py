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
console.log(JSON.stringify({html: nextCapacityProjectSpread(nextData, "claude")}));
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
console.log(JSON.stringify({html: nextCapacityProjectSpread(nextData, "claude")}));
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


@unittest.skipUnless(shutil.which("node"), "node not available")
class CapacityHonestyTest(NextPageJsHarness):
    """The absences, each one a way this surface could have reassured wrongly.

    Every case here was a real defect found by review before it shipped. They
    are grouped because they are one rule: a missing or expired input removes a
    claim, and a measured value is never rendered as an absence.
    """

    def test_a_reset_already_past_leaves_the_window_untimed(self) -> None:
        # The one that would have shipped a false all-clear. A stale disk
        # snapshot describes a window that has since rolled; clamping elapsed to
        # 1 made the pace look tiny, the projected end enormous, and the row
        # rendered "lasts, ~123% spare" over evidence that had expired, with
        # more spare than there was budget left.
        out = self._run_page_js(
            PAYLOAD
            + """
nextData.usage = [{harness: "claude", state: "ok", asOf: nextData.generated - 9000,
  fiveH: {pct: 78, windowSec: 18000, resetAt: nextData.generated - 600}}];
const rows = nextCapacityRows(nextData);
console.log(JSON.stringify({
  elapsed: rows[0].elapsed,
  pace: rows[0].paceRatio,
  ends: rows[0].windowMinutesLeft,
  html: nextCapacityRow(rows[0], nextData.generated)
}));
""",
            storage_prelude({}),
        )
        self.assertIsNone(out["elapsed"])
        self.assertIsNone(out["pace"])
        self.assertIsNone(out["ends"])
        self.assertIn("not projected", out["html"])
        self.assertNotIn("spare", out["html"])
        self.assertIn("publishes no clock", out["html"])

    def test_a_spent_budget_says_spent_rather_than_printing_the_present_minute(self) -> None:
        # Zero minutes left formatted through the clock printed the current
        # time, which reads as a deadline still ahead.
        out = self._run_page_js(
            PAYLOAD
            + """
nextData.usage = [{harness: "claude", state: "ok", asOf: nextData.generated,
  fiveH: {pct: 100, windowSec: 18000, resetAt: nextData.generated + 3600}}];
const rows = nextCapacityRows(nextData);
console.log(JSON.stringify({html: nextCapacityRow(rows[0], nextData.generated)}));
""",
            storage_prelude({}),
        )
        self.assertIn("already spent", out["html"])

    def test_a_recent_pace_measured_at_zero_is_not_reported_as_unmeasured(self) -> None:
        # Three states, not two. The ring publishes `recent` only once two
        # distinct readings support it, so a zero there is evidence that nothing
        # was spent, and "no second reading yet" contradicts the payload.
        out = self._run_page_js(
            PAYLOAD
            + """
nextData.usage[0].fiveH.recent = {pctPerMin: 0, samples: 4, spanSec: 1800};
const rows = nextCapacityRows(nextData);
const row = rows.find(entry => entry.harness === "claude");
console.log(JSON.stringify({html: nextCapacityProspect(row, 2, "")}));
""",
            storage_prelude({}),
        )
        self.assertIn("measured at zero", out["html"])
        self.assertNotIn("no second reading", out["html"])

    def test_the_thin_basis_qualifier_rides_the_reassuring_verdict_too(self) -> None:
        # Carrying it only on the alarm meant comfort was asserted with less
        # evidence than concern.
        out = self._run_page_js(
            PAYLOAD
            + """
nextData.usage = [{harness: "claude", state: "ok", asOf: nextData.generated,
  fiveH: {pct: 2, windowSec: 18000, resetAt: nextData.generated + 17100}}];
const rows = nextCapacityRows(nextData);
console.log(JSON.stringify({
  elapsed: Math.round(rows[0].elapsed * 100),
  html: nextCapacityRow(rows[0], nextData.generated)
}));
""",
            storage_prelude({}),
        )
        self.assertEqual(5, out["elapsed"])
        self.assertIn("spare", out["html"])
        self.assertIn("<em>on ", out["html"])

    def test_budget_ends_names_the_day_when_it_is_not_today(self) -> None:
        # A weekly window's budget can end days out, and an hour-of-day alone
        # names the wrong day.
        out = self._run_page_js(
            PAYLOAD
            + """
const row = nextCapacityRows(nextData).find(entry => entry.slot === "week");
console.log(JSON.stringify({
  ends: nextCapacityClock(row.endsAt, nextData.generated),
  sameDay: nextCapacityClock(nextData.generated + 600, nextData.generated)
}));
""",
            storage_prelude({}),
        )
        # Codex's weekly row outlasts its reset, so take the raw clock: days out
        # must carry a weekday, and an instant later today must not.
        self.assertRegex(
            out["ends"], r"^(Sun|Mon|Tue|Wed|Thu|Fri|Sat) \d\d:\d\d$|^[A-Z][a-z]{2} \d\d$"
        )
        self.assertRegex(out["sameDay"], r"^\d\d:\d\d$")

    def test_the_clock_is_anchored_on_the_payload_not_the_browser(self) -> None:
        # Every other time figure on the board is anchored on `generated`, and
        # mixing anchors makes two columns of one row disagree by the payload's
        # age.
        out = self._run_page_js(
            PAYLOAD
            + """
const a = nextCapacityClock(nextData.generated + 3600, nextData.generated);
const b = nextCapacityClock(nextData.generated + 3600, nextData.generated + 86400);
console.log(JSON.stringify({a, b}));
""",
            storage_prelude({}),
        )
        # The same instant read against a later anchor is no longer "today", so
        # the function is demonstrably using the anchor it was given.
        self.assertNotEqual(out["a"], out["b"])

    def test_the_spread_counts_working_intervals_and_not_idle_gaps(self) -> None:
        # First-to-last counted every gap as run time: a session that worked ten
        # minutes, sat overnight and worked ten more read as fifteen hours.
        out = self._run_page_js(
            PAYLOAD
            + """
const g = nextData.generated;
nextData.history = [
  {harness: "claude", sid: "a", project: "p", state: "working", last_activity: g - 60000},
  {harness: "claude", sid: "a", project: "p", state: "idle", last_activity: g - 59400},
  {harness: "claude", sid: "a", project: "p", state: "working", last_activity: g - 1200},
  {harness: "claude", sid: "a", project: "p", state: "idle", last_activity: g - 600},
  {harness: "claude", sid: "b", project: "p", state: "working", last_activity: g - 3600},
  {harness: "claude", sid: "b", project: "p", state: "idle", last_activity: g - 1800}
];
console.log(JSON.stringify({html: nextCapacityProjectSpread(nextData, "claude")}));
""",
            storage_prelude({}),
        )
        html = out["html"]
        # Session a worked 10m + 10m = 20m, not the 16h5m its first and last
        # records span. Session b worked 30m.
        self.assertIn("20m to 30m", html)
        self.assertIn("from 2 observed", html)

    def test_the_spread_is_scoped_to_the_harness_it_is_printed_under(self) -> None:
        out = self._run_page_js(
            PAYLOAD
            + """
const g = nextData.generated;
nextData.history = [
  {harness: "codex", sid: "x", project: "other", state: "working", last_activity: g - 7200},
  {harness: "codex", sid: "x", project: "other", state: "idle", last_activity: g - 3600},
  {harness: "codex", sid: "y", project: "other", state: "working", last_activity: g - 7200},
  {harness: "codex", sid: "y", project: "other", state: "idle", last_activity: g - 3600}
];
console.log(JSON.stringify({
  claude: nextCapacityProjectSpread(nextData, "claude"),
  codex: nextCapacityProjectSpread(nextData, "codex")
}));
""",
            storage_prelude({}),
        )
        self.assertEqual("", out["claude"])
        self.assertIn("other", out["codex"])

    def test_the_spread_counts_what_it_could_not_measure(self) -> None:
        # Silently excluding them made the range describe a subset while the
        # count named only that subset.
        out = self._run_page_js(
            PAYLOAD
            + """
const g = nextData.generated;
nextData.history = [
  {harness: "claude", sid: "a", project: "p", state: "working", last_activity: g - 3600},
  {harness: "claude", sid: "a", project: "p", state: "idle", last_activity: g - 1800},
  {harness: "claude", sid: "b", project: "p", state: "working", last_activity: g - 3600},
  {harness: "claude", sid: "b", project: "p", state: "idle", last_activity: g - 900},
  {harness: "claude", sid: "c", project: "p", state: "working", last_activity: g - 300}
];
console.log(JSON.stringify({html: nextCapacityProjectSpread(nextData, "claude")}));
""",
            storage_prelude({}),
        )
        # Session c's working record is its last, so nothing observed its end.
        self.assertIn("from 2 observed", out["html"])
        self.assertIn("1 more session has no closed working interval", out["html"])

    def test_two_sessions_do_not_report_their_maximum_as_a_median(self) -> None:
        out = self._run_page_js(
            PAYLOAD
            + """
const g = nextData.generated;
nextData.history = [
  {harness: "claude", sid: "a", project: "p", state: "working", last_activity: g - 3600},
  {harness: "claude", sid: "a", project: "p", state: "idle", last_activity: g - 3000},
  {harness: "claude", sid: "b", project: "p", state: "working", last_activity: g - 3600},
  {harness: "claude", sid: "b", project: "p", state: "idle", last_activity: g - 1800}
];
console.log(JSON.stringify({html: nextCapacityProjectSpread(nextData, "claude")}));
""",
            storage_prelude({}),
        )
        # 10m and 30m: the median is 20m, not the 30m the floor index returned.
        self.assertIn("10m to 30m", out["html"])
        self.assertIn("median <b>20m</b>", out["html"])

    def test_the_disclosure_and_strip_reach_the_rendered_sessions_view(self) -> None:
        # The mount, not the builders. Every other test here calls the builder
        # directly, and the surface this replaces disappeared precisely because
        # a view refactor dropped the call and nothing noticed.
        out = self._run_page_js(
            PAYLOAD
            + """
__els.app = {innerHTML: ""};
navigateNext({view: "sessions", project: null, session: null});
console.log(JSON.stringify({html: __els.app.innerHTML}));
""",
            storage_prelude({}),
        )
        self.assertIn("data-next-usage-consent", out["html"])
        self.assertIn("data-next-capacity", out["html"])

    def test_an_answer_survives_storage_that_refuses_the_write(self) -> None:
        # A blocked-site-data profile could not dismiss the banner at all: every
        # read re-derived from storage, so both buttons were inert.
        out = self._run_page_js(
            PAYLOAD
            + """
const before = nextUsageConsent();
nextSetUsageConsent("declined");
console.log(JSON.stringify({before, after: nextUsageConsent()}));
""",
            """
const localStorage = {
  getItem(){ throw new Error("blocked"); },
  setItem(){ throw new Error("blocked"); },
  removeItem(){ throw new Error("blocked"); }
};
const navigator = {};
location.hash = "";
""",
        )
        self.assertIsNone(out["before"])
        self.assertEqual("declined", out["after"])
