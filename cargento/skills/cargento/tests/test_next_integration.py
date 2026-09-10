from __future__ import annotations

import re
import shutil
import unittest

from .next_harness import NextPageJsHarness


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextIntegrationBehaviorTest(NextPageJsHarness):
    # A1 owns placement. Mount the retained v2 renderers at the composition seam
    # so these cases still exercise real payload derivation, rendering and events.
    V2_PROJECT_RENDERERS = """
nextProjectCockpit = context => nextProjectGoal(context.project) +
  nextProjectEndings(context) + nextProjectChanges(context.project) + nextProjectRail(context);
"""

    def test_an_idle_exact_request_reaches_the_waiting_panel_and_active_projects(self) -> None:
        result = self._run_page_js(
            self.V2_PROJECT_RENDERERS
            + """
nextData={generated:10000,ask:true,sessions:[{sid:'asker',harness:'codex',project:'repo',state:'idle'}],
 asks:[{id:'q',session_id:'asker',harness:'codex',project:'repo',question:'Choose the deployment target'}]};
__els.app={innerHTML:''};nextRoute={view:'projects'};renderNext();const projects=__els.app.innerHTML;
nextRoute={view:'project',project:'repo'};renderNext();
console.log(JSON.stringify({projects,detail:__els.app.innerHTML}));
"""
        )
        active = result["projects"].split('data-next-project-group="history"')[0]
        self.assertIn('data-next-project="repo"', active)
        waiting = result["detail"].split('data-next-rail-panel="waiting"')[1].split("</section>")[0]
        self.assertIn("Choose the deployment target", waiting)
        self.assertNotIn("Nothing in this project has asked for you", waiting)

    def test_one_render_shares_one_model_and_malformed_sources_stay_absent(self) -> None:
        result = self._run_page_js(
            self.V2_PROJECT_RENDERERS
            + """
const derive = nextObserved;
let calls = 0;
nextObserved = (...args) => { calls++; return derive(...args); };
nextData = {generated:10000,sessions:[{sid:'one',harness:'codex',project:'repo',state:'idle'}]};
__els.app={innerHTML:''};nextRoute={view:'project',project:'repo'};renderNext();
const count = calls;
const malformed = [{}, [null]].map(harnesses => derive({generated:10000,harnesses,sessions:[]}));
console.log(JSON.stringify({count,absent:malformed.map(m => m.capacityEmptyText)}));
"""
        )
        self.assertEqual(1, result["count"])
        self.assertEqual(["No quota windows published."] * 2, result["absent"])

    def test_clean_and_unmeasured_endings_keep_their_observation_colors(self) -> None:
        html = self._run_page_js(
            self.V2_PROJECT_RENDERERS
            + """
nextData={generated:10000,sessions:[false,null,true].map((dirty,i) => ({
  sid:`end-${i}`,harness:'codex',project:'repo',state:'idle',ended_at:9900,dirty}))};
__els.app={innerHTML:''};nextRoute={view:'project',project:'repo'};renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        for index, tone in enumerate(["ok", "unknown", "bad"]):
            self.assertRegex(
                html,
                f'class="next-project-ending next-project-tone--{tone}" '
                f'data-next-outcome="end-{index}"',
            )

    def test_the_header_and_active_lane_share_end_and_liveness_evidence(self) -> None:
        html = self._run_page_js("""
nextData = {generated: 10000, sessions: [
  ...[0, 1, 2, 3, 4].map(i => ({harness: 'codex', sid: `live-${i}`,
    project: 'repo', state: 'working', active: true})),
  {harness: 'codex', sid: 'ended', project: 'repo', state: 'working',
    active: true, ended_at: 9900}
]};
nextRoute = {view: 'sessions'};
__els.app = {innerHTML: ''};
renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
""")
        self.assertIn("5 running · 0 subagents observed", html)
        self.assertIn("ACTIVE NOW</span><strong>5</strong>", html)
        active, history = html.split('data-next-operation-group="history"')
        self.assertNotIn('data-next-session="ended"', active)
        self.assertIn('data-next-session="ended"', history)

    def test_working_without_liveness_keeps_its_lane_but_never_breathes(self) -> None:
        result = self._run_page_js("""
nextData = {generated: 10000, sessions: [{harness: 'codex', sid: 'inferred',
  project: 'repo', state: 'working', active: false}]};
__els.app = {innerHTML: ''};
nextRoute = {view: 'sessions'}; renderNext();
const sessions = __els.app.innerHTML;
nextRoute = {view: 'projects'}; renderNext();
console.log(JSON.stringify({sessions, projects: __els.app.innerHTML}));
""")
        self.assertIn("0 running", result["sessions"])
        self.assertIn("ACTIVE NOW</span><strong>1</strong>", result["sessions"])
        self.assertNotIn("next-operation-live-glyph", result["sessions"])
        self.assertNotIn("next-project-dot--working", result["projects"])

    def test_waiting_takes_precedence_over_risk_without_erasing_the_signal(self) -> None:
        result = self._run_page_js("""
nextData = {generated: 10000, harnesses: [{key:'claude', reports_needs_input:true}],
  sessions:[{harness:'claude',sid:'gate',project:'repo',state:'needs_input',
    loop:{errors:4, failures:4, tool:'Bash'}}]};
nextAttention = nextAttentionModel(nextData);
__els.app = {innerHTML:''}; nextRoute = {view:'attention'}; renderNext();
const attention = __els.app.innerHTML;
nextRoute = {view:'session',project:'repo',harness:'claude',session:'gate'}; renderNext();
console.log(JSON.stringify({attention, session:__els.app.innerHTML}));
""")
        self.assertIn(
            "1 of 1 session carries a subject: 1 waiting on you · 0 at risk", result["attention"]
        )
        self.assertIn("1 of 1 session reports block state", result["attention"])
        self.assertIn("4 tool calls in a row came back as errors", result["session"])
        self.assertNotIn('data-next-attention-kind="loop"', result["attention"])

    def test_each_capacity_bar_uses_its_pace_and_absence_has_a_reason(self) -> None:
        result = self._run_page_js(
            self.V2_PROJECT_RENDERERS
            + """
nextData = {generated:10000, sessions:[{sid:'one',harness:'codex',project:'repo',state:'idle'}],
 usage:[{harness:'codex',state:'ok',fiveH:{pct:50,windowSec:10000,resetAt:17500},
   week:{pct:81,windowSec:10000,resetAt:11900},month:{pct:30}}]};
__els.app={innerHTML:''}; nextRoute={view:'project',project:'repo'};renderNext();
const rail=__els.app.innerHTML;
nextRoute={view:'sessions'};renderNext();
console.log(JSON.stringify({rail,sessions:__els.app.innerHTML}));
"""
        )
        for slot, tone in [("fiveH", "clay"), ("week", "amber"), ("month", "unknown")]:
            block = (
                result["rail"]
                .split(f'data-next-rail-window="codex:{slot}"')[1]
                .split("</section>")[0]
            )
            self.assertIn(f"next-rail-capacity-fill--{tone}", block)
        self.assertIn("Pace not measured", result["sessions"])
        self.assertIn("Window length not published", result["sessions"])
        self.assertNotIn("&mdash;", result["sessions"])

    def test_live_tab_questions_are_text_and_not_executable_markup(self) -> None:
        result = self._run_page_js(
            self.V2_PROJECT_RENDERERS
            + """
await __settle();
const base = {generated:10000,asks:[],sessions:[{sid:'one',harness:'codex',project:'repo',state:'idle'}]};
nextObserveWorkstream(base);
nextData={...base,generated:10060,asks:[{id:'q',harness:'codex',session_id:'one',project:'repo',
 question:'<img src=x onerror=1>',options:['<script>alert(1)</script>']}]};
nextObserveWorkstream(nextData); nextAttention=nextAttentionModel(nextData);
__els.app={innerHTML:''};nextRoute={view:'project',project:'repo'};renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
"""
        )
        timeline = re.search(r'<section class="next-workstream"[\s\S]*?</section>', result)
        self.assertIsNotNone(timeline)
        assert timeline is not None
        self.assertIn("&lt;img src=x onerror=1&gt;", timeline[0])
        self.assertNotIn("<img", result)
        self.assertNotIn("<script>", result)
        self.assertIn("0 of 1 unattended", timeline[0])
