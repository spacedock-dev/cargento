from __future__ import annotations

import shutil
import unittest

from .next_harness import NextPageJsHarness


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextObservedTest(NextPageJsHarness):
    FIXTURE = """
const payload = {
  generated: 10000, ask: true, rate_window_sec: 600,
  summary: {working: 999, needs_input: 999},
  harnesses: [
    {key: 'claude', label: 'Claude', discovered: true,
     reports_needs_input: true, reports_rate: true},
    {key: 'codex', label: 'Codex', discovered: true,
     reports_needs_input: true, reports_rate: true},
    {key: 'agy', label: 'Antigravity', discovered: true,
     reports_needs_input: false, reports_rate: false},
    {key: 'droid', label: 'Droid', discovered: false,
     reports_needs_input: false, reports_rate: false}
  ],
  sessions: [
    {sid: 'build', harness: 'claude', project: 'alpha', state: 'working', active: true,
     title: 'Build', state_detail: 'running Bash', rate_per_min: 120,
     instruction: {label: 'asked', text: 'Build the parser', at: 9800},
     turn: {elapsed_h: '4m', eta_h: null, long: false},
     tasks: [{subject: 'Parse', status: 'in_progress'},
             {subject: 'Validate', status: 'pending'}],
     subagents: [{name: 'one', model: null}, {name: 'two', active: false}]},
    {sid: 'gate', harness: 'codex', project: 'alpha', state: 'needs_input',
     title: 'Approve', blocked_since: 9340, state_detail: 'approval needed'},
    {sid: 'dirty', harness: 'claude', project: 'alpha', state: 'working',
     title: 'Stopped', ended_at: 9400, finished_at: 9390, dirty: true, changed: 3},
    {sid: 'unknown', harness: 'agy', project: 'beta', state: 'working',
     title: null, rate_per_min: 0, source_gaps: ['message history']},
    {sid: 'loop', harness: 'claude', project: 'beta', state: 'idle',
     title: 'Failures', loop: {errors: 4, failures: 6, tool: 'Bash'}},
    {sid: 'end-unknown', harness: 'codex', project: 'gamma', state: 'idle',
     title: 'Finished', ended_at: 9300, finished_at: 9290, dirty: null},
    {sid: 'end-clean', harness: 'agy', project: 'gamma', state: 'idle',
     title: 'Gone', ended_at: 9200, dirty: false, changed: 0},
    {sid: 'quiet', harness: 'agy', project: 'delta', state: 'idle', title: null},
    {sid: 'exact', harness: 'codex', project: 'epsilon', state: 'idle', title: 'Choose'},
    {sid: 'stop-dirty', harness: 'claude', project: 'zeta', state: 'idle',
     finished_at: 9100, dirty: true, changed: 2},
    {sid: 'stop-clean', harness: 'claude', project: 'zeta', state: 'idle',
     finished_at: 9100, dirty: false, changed: 0},
    {sid: 'stop-unknown', harness: 'claude', project: 'zeta', state: 'idle',
     finished_at: 9100, dirty: null},
    {sid: 'other', harness: 'agy', project: 'theta', state: 'starting',
     state_detail: 'An unrecognised state detail'}
  ].map(s => ({active: false, last_activity: 9900, tasks: [], subagents: [], ...s})),
  asks: [
    {id: 'a', harness: 'codex', session_id: 'gate', question: 'Approve?', age_sec: 660},
    {id: 'b', harness: 'codex', session_id: 'exact', question: 'Which branch?', age_sec: 60},
    {id: 'c', harness: 'codex', session_id: 'exact', question: 'Which target?', age_sec: 30}
  ],
  history: [
    {sid: 'build', harness: 'claude', project: 'alpha', state: 'working', last_activity: 1000},
    {sid: 'build', harness: 'claude', project: 'alpha', state: 'needs_input', last_activity: 1600},
    {sid: 'build', harness: 'claude', project: 'alpha', state: 'working', last_activity: 1800},
    {sid: 'build', harness: 'claude', project: 'alpha', state: 'idle', last_activity: 2200}
  ],
  usage: []
};
"""

    WALK = """
function assertAbsence(value, path = 'model') {
  if (!value || typeof value !== 'object') return;
  for (const [key, child] of Object.entries(value)) {
    if (key.endsWith('Text')) {
      if (typeof child !== 'string' || !child.trim()) throw Error(path + '.' + key);
      if (typeof value[key.slice(0, -4) + 'Known'] !== 'boolean') {
        throw Error(path + '.' + key + ' lacks Known');
      }
    }
    assertAbsence(child, path + '.' + key);
  }
}
"""

    def test_every_denominator_comes_from_the_same_thirteen_sessions(self) -> None:
        out = self._run_page_js(
            self.FIXTURE
            + """
const m = nextObserved(payload);
console.log(JSON.stringify({totals: m.totals, counters: m.counters.map(c =>
  [c.label, c.value, c.noteText]), counts: Object.fromEntries(m.projects.map(p =>
  [p.key, p.countLine])), coverage: m.coverage,
  risks: m.risks.map(r => r.sid).sort(), board: m.boardRisks.map(r => r.kind).sort(),
  active: m.active.length, history: m.history.length,
  activeProjects: m.activeProjects.map(p => p.key), rest: m.restProjects.map(p => p.key)}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual(
            {
                "sessions": 13,
                "running": 1,
                "needs": 1,
                "ended": 3,
                "quiet": 6,
                "subagents": 2,
                "reportsBlock": 9,
                "exactRequests": 2,
            },
            out["totals"],
        )
        self.assertEqual(
            [
                ["ACTIVE NOW", 4, "13 recently observed"],
                ["WORKING", 2, "2 waiting on you"],
                ["EXACT REQUESTS", 2, "2 of 13 sessions carry an exact request"],
                ["REPORTED BLOCKS", 9, "9 of 13 sessions report block state"],
            ],
            out["counters"],
        )
        self.assertEqual(
            {
                "alpha": "3 sessions · 1 working · 1 waiting on you · 1 ended",
                "beta": "2 sessions · 1 working · 1 quiet",
                "gamma": "2 sessions · 2 ended",
                "delta": "1 session · 1 quiet",
                "epsilon": "1 session · 1 quiet",
                "zeta": "3 sessions · 3 quiet",
                "theta": "1 session · 1 in no counted state",
            },
            out["counts"],
        )
        self.assertEqual(
            "9 of 13 sessions carry a subject: 2 waiting on you · 3 at risk · 4 to close the loop.",
            out["coverage"]["observed"],
        )
        self.assertEqual(
            "The other 4: 2 moving · 1 quiet · 1 in no counted state; of these, 1 partially read.",
            out["coverage"]["quiet"],
        )
        self.assertEqual(
            "9 of 13 sessions report block state · 4 unknown · ends observed on 3 sessions",
            out["coverage"]["gates"],
        )
        self.assertEqual(4, len(out["coverage"]["rows"]))
        self.assertNotIn("No exact request published", out["coverage"]["caveats"])
        self.assertIn("Termination cause not reported.", out["coverage"]["caveats"])
        self.assertEqual(["dirty", "loop", "stop-dirty"], out["risks"])
        self.assertEqual(["collision"] * 4, out["board"])
        self.assertEqual((4, 9), (out["active"], out["history"]))
        self.assertEqual(["alpha", "epsilon", "beta"], out["activeProjects"])
        self.assertEqual(["zeta", "delta", "gamma", "theta"], out["rest"])

    def test_every_text_has_a_nonempty_value_and_known_boolean(self) -> None:
        out = self._run_page_js(
            self.FIXTURE
            + self.WALK
            + """
assertAbsence(nextObserved(payload));
assertAbsence(nextObserved({}));
console.log(JSON.stringify(true));
"""
        )
        self.assertTrue(out)

    def test_absence_walk_rejects_null_empty_undefined_and_missing_known(self) -> None:
        out = self._run_page_js(
            self.WALK
            + """
const rejected = [null, '', undefined].map(text => {
  try { assertAbsence({nested: [{newText: text, newKnown: false}]}); return false; }
  catch (_) { return true; }
});
try { assertAbsence({newText: 'Reason'}); rejected.push(false); }
catch (_) { rejected.push(true); }
console.log(JSON.stringify(rejected));
"""
        )
        self.assertEqual([True] * 4, out)

    def test_board_quota_and_collision_never_change_session_denominators(self) -> None:
        out = self._run_page_js(
            self.FIXTURE
            + """
const before = nextObserved(payload);
payload.usage = [{harness: 'codex', state: 'ok',
  week: {pct: 81, windowSec: 604800, resetAt: 130960}}];
const quota = nextObserved(payload);
payload.sessions.find(s => s.sid === 'quiet').project = 'theta';
payload.sessions.find(s => s.sid === 'exact').project = 'theta';
const collision = nextObserved(payload);
console.log(JSON.stringify({lengths: [before, quota, collision].map(m => m.boardRisks.length),
  totals: [before, quota, collision].map(m => m.totals.sessions),
  observed: [before, quota, collision].map(m => m.coverage.observed)}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual([4, 5, 6], out["lengths"])
        self.assertEqual([13, 13, 13], out["totals"])
        self.assertEqual([out["observed"][0]] * 3, out["observed"])

    def test_pure_stable_ranking_and_shared_session_objects(self) -> None:
        out = self._run_page_js(
            self.FIXTURE
            + """
const before = JSON.stringify(payload);
const a = nextObserved(payload);
const unchanged = before === JSON.stringify(payload);
nextData = {sessions: [{sid: 'unrelated', project: 'wrong', state: 'needs_input'}]};
nextWorkstreamGroups = [];
const b = nextObserved(payload);
payload.sessions.reverse();
const c = nextObserved(payload);
console.log(JSON.stringify({unchanged, deterministic: JSON.stringify(a) === JSON.stringify(b),
  order: a.projects.map(p => p.key), reverse: c.projects.map(p => p.key),
  shared: a.projects.every(p => p.sessions.every(s => a.sessions.includes(s)))}));
"""
        )
        assert isinstance(out, dict)
        self.assertTrue(out["unchanged"])
        self.assertTrue(out["deterministic"])
        self.assertTrue(out["shared"])
        self.assertEqual(
            ["alpha", "epsilon", "beta", "zeta", "delta", "gamma", "theta"], out["order"]
        )
        self.assertEqual(out["order"], out["reverse"])

    def test_six_outcomes_use_observed_stops_ends_and_git_without_readership_claims(self) -> None:
        out = self._run_page_js(
            self.FIXTURE
            + """
const m = nextObserved(payload);
console.log(JSON.stringify(Object.fromEntries(m.sessions.map(s => [s.sid,
  {outcome: s.outcomeText, known: s.outcomeKnown, glyph: s.outcomeGlyph,
   where: s.whereText, whereKnown: s.whereKnown, rateKnown: s.rateKnown,
   git: s.gitText, gitKnown: s.gitKnown, tone: s.tone}]))));
"""
        )
        assert isinstance(out, dict)
        expected = {
            "dirty": ("Session ended with uncommitted work", "△", "bad", "3 changed entries", True),
            "end-clean": (
                "Session ended; git state clean",
                "✓",
                "ok",
                "Git state reported clean",
                True,
            ),
            "end-unknown": (
                "Session ended; git state not measured",
                "◦",
                "unknown",
                "Git state was not measured",
                False,
            ),
            "stop-dirty": (
                "Stop observed with uncommitted work",
                "△",
                "bad",
                "2 changed entries",
                True,
            ),
            "stop-clean": (
                "Stop observed; git state clean",
                "✓",
                "ok",
                "Git state reported clean",
                True,
            ),
            "stop-unknown": (
                "Stop observed; git state not measured",
                "◦",
                "unknown",
                "Git state was not measured",
                False,
            ),
        }
        for sid, values in expected.items():
            with self.subTest(sid=sid):
                session = out[sid]
                self.assertTrue(session["known"])
                self.assertEqual(
                    values,
                    tuple(session[key] for key in ("outcome", "glyph", "tone", "git", "gitKnown")),
                )
        self.assertFalse(out["build"]["known"])
        self.assertEqual("No stop or end observed", out["build"]["outcome"])
        self.assertEqual("", out["build"]["glyph"])
        self.assertFalse(out["unknown"]["rateKnown"])
        for session in out.values():
            self.assertEqual("Exact location not published", session["where"])
            self.assertFalse(session["whereKnown"])

    def test_the_three_end_kinds_are_named_and_quiet_authorises_nothing(self) -> None:
        """DRC-4512: how it landed is two axes, and neither one implies the other.

        The composed one-line outcome merges an end with a git reading, which
        is why it cannot answer either question on its own. `landing` separates
        them: what was observed to end, and who says the work finished.
        """
        out = self._run_page_js(
            self.FIXTURE
            + """
const scan = JSON.parse(JSON.stringify(payload));
scan.sessions.find(s => s.sid === 'quiet').acquisition = 'scan-only';
const m = nextObserved(scan);
console.log(JSON.stringify(Object.fromEntries(m.sessions.map(s => [s.sid, {
  endKind: s.landing.endKind, end: s.landing.endText, endKnown: s.landing.endKnown,
  claimKind: s.landing.claimKind, claim: s.landing.claimText,
  claimKnown: s.landing.claimKnown,
  independent: s.landing.independentText,
  independentKnown: s.landing.independentKnown,
  outcome: s.outcomeText}]))));
"""
        )
        assert isinstance(out, dict)
        # One row per end kind the board can reach, including the two that
        # authorise nothing. `quiet` carries `acquisition: scan-only` in this
        # payload only, because no event can ever reach such a row and its
        # silence therefore means something different from `loop`'s.
        kinds = {
            "dirty": "session-end",
            "end-clean": "session-end",
            "end-unknown": "session-end",
            "stop-dirty": "turn-stop",
            "stop-clean": "turn-stop",
            "stop-unknown": "turn-stop",
            "loop": "idle-unknown",
            "exact": "idle-unknown",
            "quiet": "unobservable",
            "build": "running",
            "gate": "running",
        }
        for sid, kind in kinds.items():
            with self.subTest(sid=sid):
                self.assertEqual(kind, out[sid]["endKind"])
        self.assertEqual(
            "A session end was observed",
            out["end-clean"]["end"],
        )
        self.assertEqual(
            "A turn stop was observed; no session end was",
            out["stop-clean"]["end"],
        )
        # Quiet authorises nothing, and says which kind of quiet it is.
        self.assertEqual(
            "Idle with completion unknown: no stop and no end was observed",
            out["loop"]["end"],
        )
        self.assertEqual(
            "No event from this harness can reach this row, so no stop or end can be observed",
            out["quiet"]["end"],
        )
        for sid in ("loop", "exact", "quiet", "build", "gate"):
            with self.subTest(sid=sid):
                self.assertFalse(out[sid]["endKnown"])
                self.assertEqual("none", out[sid]["claimKind"])
                self.assertFalse(out[sid]["claimKnown"])
                self.assertEqual("Nothing has claimed this session finished", out[sid]["claim"])
        # Only the six that ended or stopped carry a finish claim, and every one
        # of them attributes it to the session rather than to an observer.
        for sid in ("dirty", "end-clean", "end-unknown", "stop-dirty", "stop-clean"):
            with self.subTest(sid=sid):
                self.assertTrue(out[sid]["endKnown"])
                self.assertEqual("agent", out[sid]["claimKind"])
                self.assertEqual("The agent reported it finished", out[sid]["claim"])
        # The second axis never reads true on this board, and it states the
        # limit rather than rendering blank. A dirty tree is work, not the
        # requested output, and a clean one is not a deliverable either.
        self.assertEqual(
            {
                (
                    "3 changed entries were observed, which shows work happened "
                    "and not that the requested output exists"
                ),
                ("The working tree was observed clean, which is not evidence a deliverable exists"),
                (
                    "2 changed entries were observed, which shows work happened "
                    "and not that the requested output exists"
                ),
                (
                    "Git state was not measured, so nothing was observed apart "
                    "from the session's own account"
                ),
            },
            {session["independent"] for session in out.values()},
        )
        for sid, session in out.items():
            with self.subTest(sid=sid):
                self.assertFalse(session["independentKnown"])
        # The lift left the composed line byte-identical: `next-attention.js`
        # looks its risk labels up by these exact strings.
        self.assertEqual("Session ended with uncommitted work", out["dirty"]["outcome"])
        self.assertEqual("No stop or end observed", out["quiet"]["outcome"])

    def test_history_derives_closed_intervals_changes_and_partial_floor(self) -> None:
        out = self._run_page_js(
            self.FIXTURE
            + """
const p = nextObserved(payload).projects.find(p => p.key === 'alpha');
console.log(JSON.stringify({delegation: p.delegation, changes: p.changes,
  note: p.changeNoteText, goal: p.goalText, gap: p.goalGapText}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual(83, out["delegation"]["pct"])
        self.assertTrue(out["delegation"]["pctKnown"])
        # Absent, not false: a ratio takes no floor, so the field should not exist
        # at all. Asserting absence is what stops it being reintroduced.
        self.assertNotIn("pctFloor", out["delegation"])
        self.assertEqual(
            "Measured over observed working and needs-input intervals.",
            out["delegation"]["noteText"],
        )
        self.assertEqual(3, len(out["changes"]))
        self.assertEqual("1 of 3 unattended · last 2h 30m", out["note"])
        self.assertEqual("Build the parser", out["goal"])
        self.assertEqual("2 of 3 sessions publish no goal.", out["gap"])

    def test_absent_geometry_and_companion_booleans_describe_their_evidence(self) -> None:
        out = self._run_page_js(
            self.FIXTURE
            + """
const m = nextObserved(payload);
const alpha = m.projects.find(p => p.key === 'alpha');
const delta = m.projects.find(p => p.key === 'delta');
console.log(JSON.stringify({
  measured: [alpha.goalSrcKnown, alpha.changeNoteKnown, alpha.delegation.humanKnown,
    alpha.delegation.windowKnown, alpha.delegation.noteKnown],
  absent: [delta.goalSrcKnown, delta.changeNoteKnown, delta.delegation.humanKnown,
    delta.delegation.windowKnown, delta.delegation.noteKnown],
  delta: delta.delegation, tps: alpha.delegation.tpsKnown,
  waited: ['gate', 'quiet'].map(sid => m.sessions.find(s => s.sid === sid).waitedKnown),
  counters: m.counters.map(c => c.noteKnown), open: m.open
}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual([True] * 5, out["measured"])
        self.assertEqual([False, True, True, True, False], out["absent"])
        self.assertFalse(out["delta"]["pctKnown"])
        self.assertIsNone(out["delta"]["pct"])
        self.assertEqual("no figure yet", out["delta"]["pctText"])
        self.assertFalse(out["tps"])
        self.assertEqual([True, False], out["waited"])
        self.assertEqual([True] * 4, out["counters"])
        self.assertIn(
            [
                "E6",
                "Finished and never read",
                (
                    "Nothing on the board publishes whether you have read a finished session. "
                    "The dismissal store is server-side and does not reach the page."
                ),
            ],
            out["open"],
        )

    def test_quota_clocks_recent_zero_and_sublimits_stay_separate(self) -> None:
        out = self._run_page_js(
            self.FIXTURE
            + self.WALK
            + """
payload.usage = [{harness: 'claude', state: 'ok',
  fiveH: {pct: 25, windowSec: 10000, resetAt: 19800,
          recent: {pctPerMin: 0, samples: 12, spanSec: 120}},
  week: {pct: 81, windowSec: 10000, resetAt: 11900},
  month: {pct: 10, resetAt: 9000},
  models: [{label: 'Fable', pct: 0}]}];
const m = nextObserved(payload);
assertAbsence({windows: m.windows, sublimits: m.sublimits});
console.log(JSON.stringify({windows: m.windows, sublimits: m.sublimits}));
"""
        )
        assert isinstance(out, dict)
        windows = {row["slot"]: row for row in out["windows"]}
        self.assertEqual(3, len(windows))
        self.assertEqual("12.5\N{MULTIPLICATION SIGN}", windows["fiveH"]["paceText"])
        self.assertEqual("bad", windows["fiveH"]["tone"])
        self.assertEqual("1.0\N{MULTIPLICATION SIGN}", windows["week"]["paceText"])
        self.assertEqual("want", windows["week"]["tone"])
        self.assertFalse(windows["month"]["paceKnown"])
        self.assertEqual("unknown", windows["month"]["tone"])
        self.assertIn("Measured at zero", windows["fiveH"]["recentText"])
        self.assertTrue(windows["fiveH"]["recentKnown"])
        self.assertEqual(1, len(out["sublimits"]))
        self.assertEqual(0, out["sublimits"][0]["used"])
        self.assertNotIn("paceText", out["sublimits"][0])

    def test_stops_attribution_and_ambiguous_asks_keep_their_evidence(self) -> None:
        out = self._run_page_js(
            """
const payload = {generated: 10000, ask: true, sessions: [
  {harness: 'claude', sid: 'same', project: 'a', state: 'working',
   finished_at: 9000, active: true},
  {harness: 'codex', sid: 'same', project: 'b', state: 'idle',
   finished_at: 9000, dirty: true, changed: 2}
], asks: [{id: 'ambiguous', session_id: 'same', question: 'Who owns this?'}]};
const m = nextObserved(payload);
console.log(JSON.stringify({risks: m.risks.map(r => r.kind),
  board: m.boardRisks.map(r => r.kind), exact: m.totals.exactRequests,
  outcomes: m.sessions.map(s => s.outcomeKnown)}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual(["attribution", "stop-dirty"], out["risks"])
        self.assertEqual(["ask"], out["board"])
        self.assertEqual(0, out["exact"])
        self.assertEqual([False, True], out["outcomes"])

    def test_model_sessions_retain_controls_and_use_the_shipped_token_validation(self) -> None:
        out = self._run_page_js(
            self.FIXTURE
            + self.WALK
            + """
document.querySelector = selector => selector === NEXT_FOCUS_META
  ? {getAttribute: () => 'test-capability'} : null;
payload.sessions[0].focusable = true;
payload.sessions[0].resume_id = 'published-resume-token';
const m = nextObserved(payload);
assertAbsence(m);
const session = m.sessions[0];
const raise = nextSessionRaiseControl(session);
const resume = nextSessionResumeControl(session);
payload.sessions[0].resume_id = '-invalid-option';
payload.sessions[0].focusable = false;
const invalid = nextObserved(payload);
console.log(JSON.stringify({focusable: session.focusable, resume_id: session.resume_id,
  command: nextResumeCommand(session), raise, resume,
  rejected: nextResumeCommand(invalid.sessions[0]), absentRaise: nextSessionRaiseControl(invalid.sessions[0]),
  preservedInvalid: invalid.sessions[0].resume_id,
  sameCounts: JSON.stringify(m.totals) === JSON.stringify(invalid.totals),
  sameTone: session.tone === invalid.sessions[0].tone,
  absentToken: m.sessions[1].resume_id,
  noHarnessPair: !('harnessText' in session) && !('harnessKnown' in session)}));
"""
        )
        assert isinstance(out, dict)
        self.assertTrue(out["focusable"])
        self.assertEqual("published-resume-token", out["resume_id"])
        self.assertEqual("claude --resume published-resume-token", out["command"])
        self.assertIn('data-next-raise-session="build"', out["raise"])
        self.assertIn(
            'data-next-copy-command="claude --resume published-resume-token"', out["resume"]
        )
        self.assertEqual("", out["rejected"])
        self.assertEqual("", out["absentRaise"])
        self.assertEqual("-invalid-option", out["preservedInvalid"])
        self.assertIsNone(out["absentToken"])
        self.assertTrue(out["sameCounts"])
        self.assertTrue(out["sameTone"])
        self.assertTrue(out["noHarnessPair"])

    def test_recency_keeps_a_session_in_the_working_lane_without_claiming_liveness(self) -> None:
        out = self._run_page_js(
            """
const m = nextObserved({sessions: [
  {sid: 'recent', harness: 'claude', project: 'p', state: 'working', active: false},
  {sid: 'live', harness: 'claude', project: 'p', state: 'working', active: true},
  {sid: 'ended', harness: 'claude', project: 'p', state: 'working', active: true, ended_at: 99},
  {sid: 'unmeasured', harness: 'claude', project: 'p', state: 'working', active: null}
]});
console.log(JSON.stringify({sessions: m.sessions.map(s => [s.sid, s.isWorking, s.isLive]),
  active: m.active.map(s => s.sid), running: m.totals.running,
  working: m.counters.find(c => c.label === 'WORKING').value}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual(
            [
                ["recent", True, False],
                ["live", True, True],
                ["ended", False, False],
                ["unmeasured", True, False],
            ],
            out["sessions"],
        )
        self.assertEqual(["live", "recent", "unmeasured"], out["active"])
        self.assertEqual(1, out["running"])
        self.assertEqual(3, out["working"])

    def test_capacity_empty_reasons_are_available_even_for_a_filtered_empty_list(self) -> None:
        out = self._run_page_js(
            self.FIXTURE
            + self.WALK
            + """
const empty = nextObserved(payload);
payload.usage = [{harness: 'codex', state: 'ok', week: {pct: 10}}];
const populated = nextObserved(payload);
assertAbsence(empty);
assertAbsence(populated);
console.log(JSON.stringify([empty, populated].map(m => [m.capacityEmptyText,
  m.capacityEmptyKnown, m.capacityEmptyNoteText, m.capacityEmptyNoteKnown, m.windows.length])));
"""
        )
        self.assertEqual(
            [
                [
                    "No quota windows published.",
                    False,
                    "No vendor window has been read for this harness.",
                    False,
                    count,
                ]
                for count in (0, 1)
            ],
            out,
        )

    def test_timeline_matches_the_shipped_window_without_counting_an_unobserved_tail(self) -> None:
        out = self._run_page_js(
            """
const payload = {generated: 10000, sessions: [
  {sid: 'one', harness: 'claude', project: 'p', state: 'idle'}
], history: [
  {sid: 'one', harness: 'claude', project: 'p', state: 'working', last_activity: 9400},
  {sid: 'one', harness: 'claude', project: 'p', state: 'idle', last_activity: 9700}
]};
nextObserveWorkstream(payload);
const oldWindow = nextWorkstreamProjectWindow('p');
const p = nextObserved(payload).projects[0];
console.log(JSON.stringify({legacy: nextWorkstreamWindowLabel(oldWindow),
  window: p.delegation.windowText, note: p.changeNoteText, pct: p.delegation.pct,
  pctKnown: p.delegation.pctKnown, changes: p.changes,
  legacyClock: nextWorkstreamClock(9700)}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual("last 10m", out["legacy"])
        self.assertEqual("last 10m", out["window"])
        self.assertEqual("1 of 1 unattended · last 10m", out["note"])
        self.assertFalse(out["pctKnown"])
        self.assertIsNone(out["pct"])
        self.assertEqual(
            [
                {
                    "at": out["legacyClock"],
                    "filled": True,
                    "label": "became idle",
                    "harness": "claude",
                    "kind": "state",
                }
            ],
            out["changes"],
        )
        self.assertRegex(out["changes"][0]["at"], r"^\d{2}:\d{2}$")

    def test_trend_matches_two_complete_six_hour_windows_and_withholds_gaps(self) -> None:
        for steps, expected in (
            ("[[6800, 'needs_input'], [17600, 'working'], [50000, 'idle']]", 50),
            (
                "[[6800, 'working'], [28400, 'needs_input'], [39200, 'working'], [50000, 'idle']]",
                -50,
            ),
            ("[[6800, 'working'], [50000, 'idle']]", 0),
        ):
            with self.subTest(delta=expected):
                out = self._run_page_js(
                    self.WALK
                    + f"""
const identity = {{sid: 'one', harness: 'claude', project: 'p'}};
const payload = {{generated: 50000, sessions: [{{...identity, state: 'idle'}}],
  history: {steps}.map(([at, state]) => ({{...identity, last_activity: at, state}}))}};
nextObserveWorkstream(payload);
const p = nextObserved(payload).projects[0];
assertAbsence(p);
const legacy = nextDelegationTrend(nextWorkstreamProjectWindow('p'));
payload.generated += 1;
const gap = nextObserved(payload).projects[0].delegation;
console.log(JSON.stringify({{trend: p.delegation.trendText, delta: p.delegation.trendDelta,
  known: p.delegation.trendKnown, legacy, gap}}));
"""
                )
                assert isinstance(out, dict)
                self.assertEqual(expected, out["legacy"])
                self.assertEqual(expected, out["delta"])
                self.assertEqual(f"{expected:+}" if expected > 0 else str(expected), out["trend"])
                self.assertTrue(out["known"])
                self.assertFalse(out["gap"]["trendKnown"])
                self.assertIsNone(out["gap"]["trendDelta"])
                self.assertEqual(
                    "Two complete six-hour delegation readings are not available",
                    out["gap"]["trendText"],
                )

    def test_goal_normalization_keeps_internal_whitespace_authoritative(self) -> None:
        out = self._run_page_js(
            """
const m = nextObserved({sessions: [{sid: 'goal', harness: 'claude', project: 'p',
  instruction: {label: 'asked', text: '  Build  the\\n parser.  '}}]});
console.log(JSON.stringify(m.projects[0].goalText));
"""
        )
        self.assertEqual("Build  the\n parser.", out)

    def test_active_and_history_key_sets_are_disjoint(self) -> None:
        out = self._run_page_js(
            self.FIXTURE
            + """
payload.asks.push({id: 'ended-question', harness: 'agy', session_id: 'end-clean',
  question: 'Read this result?'});
const m = nextObserved(payload);
const activeKeys = new Set(m.active.map(nextSessionKey));
const historyKeys = new Set(m.history.map(nextSessionKey));
console.log(JSON.stringify({intersection: [...activeKeys].filter(key => historyKeys.has(key)),
  asksActive: ['exact', 'end-clean'].map(sid => m.active.some(s => s.sid === sid && s.isActive)),
  predicates: m.active.every(s => s.isActive) && m.history.every(s => !s.isActive)}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual([], out["intersection"])
        self.assertEqual([True, True], out["asksActive"])
        self.assertTrue(out["predicates"])

    def test_active_length_plus_history_length_equals_totals_sessions(self) -> None:
        out = self._run_page_js(
            self.FIXTURE
            + """
// A duplicate request row must not numerically cancel the missing unknown row.
payload.asks = [];
const m = nextObserved(payload);
const allKeys = m.sessions.map(nextSessionKey).sort();
const laneKeys = [...m.active, ...m.history].map(nextSessionKey).sort();
console.log(JSON.stringify({total: m.totals.sessions, laneTotal: m.active.length + m.history.length,
  keys: JSON.stringify(allKeys) === JSON.stringify(laneKeys),
  awkward: m.history.some(s => s.sid === 'other' && !s.isActive && !s.isLive)}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual(13, out["total"])
        self.assertEqual(out["total"], out["laneTotal"])
        self.assertTrue(out["keys"])
        self.assertTrue(out["awkward"])

    def test_unrecognised_and_absent_states_publish_a_reason_and_keep_exact_requests(self) -> None:
        out = self._run_page_js(
            self.FIXTURE
            + self.WALK
            + """
const source = payload.sessions.find(s => s.sid === 'other');
const cases = ['starting', undefined, null, ''].map(state => {
  source.state = state;
  const m = nextObserved(payload);
  assertAbsence(m);
  const s = m.sessions.find(s => s.sid === 'other');
  return [s.state, s.nowText, s.nowKnown, s.isActive, m.history.includes(s)];
});
payload.asks.push({id: 'other-question', harness: 'agy', session_id: 'other', question: 'Continue?'});
const m = nextObserved(payload);
console.log(JSON.stringify({cases, askedActive: m.active.some(s => s.sid === 'other'),
  askedHistory: m.history.some(s => s.sid === 'other')}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual(
            [
                [state, "No state published", False, False, True]
                for state in ("starting", "", "", "")
            ],
            out["cases"],
        )
        self.assertTrue(out["askedActive"])
        self.assertFalse(out["askedHistory"])

    def test_lanes_inherit_shipped_bucket_order_without_resorting_gates(self) -> None:
        out = self._run_page_js(
            """
const payload = {generated: 10000, ask: true, sessions: [
  {sid: 'idle-old', state: 'idle', last_activity: 8000},
  {sid: 'short-z', state: 'working'},
  {sid: 'gate-z', state: 'needs_input'},
  {sid: 'idle-ask', state: 'idle', last_activity: 9950},
  {sid: 'long-z', state: 'working', turn: {long: true}},
  {sid: 'gate-a', state: 'needs_input'},
  {sid: 'end-long', state: 'working', turn: {long: true}, ended_at: 9900},
  {sid: 'other', state: 'starting'},
  {sid: 'short-a', state: 'working'},
  {sid: 'idle-b', state: 'idle', last_activity: 9000},
  {sid: 'idle-a', state: 'idle', last_activity: 9000},
  {sid: 'other-ask'}
].map(s => ({harness: 'claude', project: 'p', ...s})), asks: [
  {id: 'idle-question', session_id: 'idle-ask', question: 'Choose?'},
  {id: 'other-question', session_id: 'other-ask', question: 'Continue?'}
]};
const before = JSON.stringify(payload);
const m = nextObserved(payload);
nextData = payload;
const buckets = nextSessionBlocks();
const ordered = [...buckets.gates, ...buckets.working, ...buckets.idle, ...buckets.other];
console.log(JSON.stringify({active: m.active.map(s => s.sid), history: m.history.map(s => s.sid),
  legacyActive: ordered.filter(s => nextOperationsIsActive(s, payload.asks)).map(s => s.sid),
  legacyHistory: ordered.filter(s => !nextOperationsIsActive(s, payload.asks)).map(s => s.sid),
  unchanged: before === JSON.stringify(payload),
  shared: [...m.active, ...m.history].every(s => m.sessions.includes(s))}));
"""
        )
        assert isinstance(out, dict)
        self.assertEqual(
            ["gate-z", "gate-a", "long-z", "short-a", "short-z", "idle-ask", "other-ask"],
            out["active"],
        )
        self.assertEqual(["end-long", "idle-a", "idle-b", "idle-old", "other"], out["history"])
        self.assertEqual(out["legacyActive"], out["active"])
        self.assertEqual(out["legacyHistory"], out["history"])
        self.assertTrue(out["unchanged"])
        self.assertTrue(out["shared"])


@unittest.skipUnless(shutil.which("node"), "node not available")
class ObservedLandingCountsOneAsOneTest(NextPageJsHarness):
    """A copy defect the review's own fixes put on screen.

    The sentence predates this branch, and nothing rendered it: HOW IT LANDED
    is what gave the independent axis a surface, so "1 changed entries were
    observed" reached a reader for the first time because of a fix.
    """

    def test_the_independent_axis_agrees_with_itself_about_a_count_of_one(self) -> None:
        out = self._run_page_js(
            """
const landing = changed => nextObservedLanding(
  {state:"idle", harness:"claude", dirty:true, changed}, true, false).independentText;
console.log(JSON.stringify({
  one: landing(1),
  several: landing(4),
  none: landing(0),
  unmeasured: nextObservedLanding({state:"idle", harness:"claude"}, true, false).independentText,
}));
"""
        )
        assert isinstance(out, dict)
        self.assertTrue(out["one"].startswith("1 changed entry was observed"))
        self.assertTrue(out["several"].startswith("4 changed entries were observed"))
        # Zero is still plural, which is what English does and what the
        # dirty-with-nothing-changed case actually reads as.
        self.assertTrue(out["none"].startswith("0 changed entries were observed"))
        self.assertTrue(out["unmeasured"].startswith("Git state was not measured"))
