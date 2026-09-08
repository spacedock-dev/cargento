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
    {sid: 'build', harness: 'claude', project: 'alpha', state: 'working',
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
     finished_at: 9100, dirty: null}
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

    def test_every_denominator_comes_from_the_same_twelve_sessions(self) -> None:
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
                "sessions": 12,
                "running": 2,
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
                ["ACTIVE NOW", 4, "12 recently observed"],
                ["WORKING", 2, "2 waiting on you"],
                ["EXACT REQUESTS", 2, "2 of 12 sessions carry an exact request"],
                ["REPORTED BLOCKS", 9, "9 of 12 sessions report block state"],
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
            },
            out["counts"],
        )
        self.assertEqual(
            "9 of 12 sessions carry a subject: 2 waiting on you · 3 at risk · 4 to close the loop.",
            out["coverage"]["observed"],
        )
        self.assertEqual(
            "The other 3: 2 moving · 1 quiet; of these, 1 partially read.",
            out["coverage"]["quiet"],
        )
        self.assertEqual(
            "9 of 12 sessions report block state · 3 unknown · ends observed on 3 sessions",
            out["coverage"]["gates"],
        )
        self.assertEqual(4, len(out["coverage"]["rows"]))
        self.assertNotIn("No exact request published", out["coverage"]["caveats"])
        self.assertIn("Termination cause not reported.", out["coverage"]["caveats"])
        self.assertEqual(["dirty", "loop", "stop-dirty"], out["risks"])
        self.assertEqual(["collision"] * 4, out["board"])
        self.assertEqual((4, 9), (out["active"], out["history"]))
        self.assertEqual(["alpha", "beta"], out["activeProjects"])
        self.assertEqual(["zeta", "delta", "epsilon", "gamma"], out["rest"])

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
        self.assertEqual([12, 12, 12], out["totals"])
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
        self.assertEqual(["alpha", "beta", "zeta", "delta", "epsilon", "gamma"], out["order"])
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
        self.assertTrue(out["delegation"]["pctFloor"])
        self.assertIn("2 sessions have no closed working interval", out["delegation"]["noteText"])
        self.assertEqual(3, len(out["changes"]))
        self.assertEqual("1 of 3 unattended · last 20m", out["note"])
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
        self.assertEqual([False] * 5, out["absent"])
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
