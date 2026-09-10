from __future__ import annotations

import shutil
import unittest

from .next_harness import NextPageJsHarness, storage_prelude


@unittest.skipUnless(shutil.which("node"), "node not available")
class NextObserverConsentTest(NextPageJsHarness):
    FIXTURE = """
location.hash = "#n=project:cargento:codex%3Afocus-1:console";
__els.app = {innerHTML:""};
const dashboard = {generated:105, window_hours:24,
  summary:{working:1,needs_input:0}, harnesses:[{key:"codex",label:"Codex"}],
  sessions:[{sid:"focus-1",harness:"codex",project:"cargento",project_key:"repo/cargento",
    state:"working",active:true,last_activity:104,title:"Inspect consent",subagents:[]}]};
const context = {observers:[],child_assignments:[],semantic:{facts:[],projections:{}},
  observer_model:{enabled:true,max_prompt_bytes:16384,
    disclosure:"Send redacted transcript excerpts to OpenAI through Codex? 16 KiB per prompt."}};
__fetchImpl = async url => ({ok:true,json:async () =>
  String(url).startsWith("/api/project-context") ? context : dashboard});
const clickObserver = action => __fire("click",{preventDefault(){},target:{
  dataset:{nextObserverAction:action},closest(selector){
    return selector === "[data-next-observer-action]" ? this : null;
  }}});
"""

    def test_a_reader_sees_disclosure_before_any_model_request(self) -> None:
        out = self._run_page_js(
            """
await __settle(); await __settle();
console.log(JSON.stringify({html:__els.app.innerHTML,urls:__fetchCalls.map(row=>row[0])}));
""",
            storage_prelude({}) + self.FIXTURE,
        )
        self.assertIn("Send redacted transcript excerpts", out["html"])
        self.assertIn("Allow model summaries", out["html"])
        self.assertIn("private prose", out["html"])
        self.assertFalse(any("observer_model=1" in url for url in out["urls"]))

    def test_an_older_passive_read_cannot_replace_the_requested_summary(self) -> None:
        out = self._run_page_js(
            """
await __settle(); await __settle();
clickObserver("allow");
const pending=[];
__fetchImpl=url=>new Promise(resolve=>pending.push({url:String(url),resolve}));
nextData.generated=106; renderNext();
const passive=pending.find(row=>row.url.includes("session=codex%3Afocus-1"));
clickObserver("request");
const model=pending.find(row=>row.url.includes("observer_model=1"));
model.resolve({ok:true,json:async()=>({...context,observers:[{sid:"focus-1",harness:"codex",
  goal:"Fresh model answer",model:{status:"used"}}]})});
await __settle(); await __settle();
const fresh=__els.app.innerHTML.includes("Fresh model answer");
passive.resolve({ok:true,json:async()=>({...context,observers:[{sid:"focus-1",harness:"codex",
  goal:"Old cached answer",model:{status:"cached"}}]})});
await __settle(); await __settle();
console.log(JSON.stringify({fresh,html:__els.app.innerHTML}));
""",
            storage_prelude({}) + self.FIXTURE,
        )
        self.assertTrue(out["fresh"])
        self.assertIn("Fresh model answer", out["html"])
        self.assertNotIn("Old cached answer", out["html"])

    def test_passive_reads_wait_for_the_requested_summary_then_resume(self) -> None:
        out = self._run_page_js(
            """
await __settle(); await __settle();
clickObserver("allow");
const pending=[];
__fetchImpl=url=>new Promise(resolve=>pending.push({url:String(url),resolve}));
const passiveCount=()=>pending.filter(row=>row.url.includes("session=codex%3Afocus-1")&&
  !row.url.includes("observer_model=1")).length;
clickObserver("request");
nextData.generated=106; renderNext();
const during=passiveCount();
pending.find(row=>row.url.includes("observer_model=1")).resolve({ok:true,json:async()=>context});
await __settle(); await __settle();
nextData.generated=107; renderNext();
console.log(JSON.stringify({during,after:passiveCount()}));
""",
            storage_prelude({}) + self.FIXTURE,
        )
        self.assertEqual(0, out["during"])
        self.assertEqual(1, out["after"])

    def test_allowing_summaries_waits_for_the_readers_explicit_request(self) -> None:
        out = self._run_page_js(
            """
await __settle(); await __settle();
clickObserver("allow"); await __settle();
const allowed=__fetchCalls.filter(row=>String(row[0]).includes("observer_model=1")).length;
const offered=__els.app.innerHTML;
clickObserver("request"); await __settle(); await __settle();
console.log(JSON.stringify({allowed,offered,
  requests:__fetchCalls.map(row=>row[0]).filter(url=>url.includes("observer_model=1"))}));
""",
            storage_prelude({}) + self.FIXTURE,
        )
        self.assertEqual(0, out["allowed"])
        self.assertIn("Summarize this session", out["offered"])
        self.assertEqual(
            [
                (
                    "/api/project-context?project=repo%2Fcargento&session=codex%3Afocus-1"
                    "&refresh=1&observer_model=1"
                )
            ],
            out["requests"],
        )

    def test_a_disabled_model_explains_its_absence_and_refuses_requests(self) -> None:
        out = self._run_page_js(
            """
await __settle(); await __settle();
context.observer_model.enabled=false;
clickObserver("allow"); clickObserver("request"); await __settle();
console.log(JSON.stringify({html:__els.app.innerHTML,
  requested:__fetchCalls.some(row=>String(row[0]).includes("observer_model=1"))}));
""",
            storage_prelude({}) + self.FIXTURE,
        )
        self.assertIn("Observer model is disabled for this run", out["html"])
        self.assertFalse(out["requested"])

    def test_a_requested_summary_shows_the_exact_sessions_goal_and_model_status(self) -> None:
        out = self._run_page_js(
            """
await __settle(); await __settle();
context.observers=[{sid:"other",harness:"codex",goal:"Wrong session"},
  {sid:"focus-1",harness:"codex",goal:"Inspect <local> consent",model:{status:"used"}}];
clickObserver("allow"); clickObserver("request"); await __settle(); await __settle();
const result=__els.app.innerHTML;
context.observers=[];
clickObserver("request"); await __settle(); await __settle();
console.log(JSON.stringify({result,absent:__els.app.innerHTML}));
""",
            storage_prelude({}) + self.FIXTURE,
        )
        self.assertIn("Inspect &lt;local&gt; consent", out["result"])
        self.assertIn("Model status: <code>used</code>", out["result"])
        self.assertNotIn("Wrong session", out["result"])
        self.assertIn("No goal summary was published by this refresh", out["absent"])

    def test_missing_disclosure_withholds_the_action_and_explains_why(self) -> None:
        out = self._run_page_js(
            """
await __settle(); await __settle();
context.observer_model.disclosure="";
clickObserver("allow"); clickObserver("request"); await __settle();
console.log(JSON.stringify({html:__els.app.innerHTML,
  requested:__fetchCalls.some(row=>String(row[0]).includes("observer_model=1"))}));
""",
            storage_prelude({}) + self.FIXTURE,
        )
        self.assertIn(
            "Observer disclosure is unavailable; model requests are withheld", out["html"]
        )
        self.assertFalse(out["requested"])

    def test_project_scope_asks_the_reader_to_select_an_exact_session(self) -> None:
        out = self._run_page_js(
            """
await __settle(); await __settle();
navigateNext({view:"project",project:"cargento",tab:"console"});
await __settle(); await __settle();
clickObserver("allow"); clickObserver("request"); await __settle();
console.log(JSON.stringify({html:__els.app.innerHTML,
  requested:__fetchCalls.some(row=>String(row[0]).includes("observer_model=1"))}));
""",
            storage_prelude({}) + self.FIXTURE,
        )
        self.assertIn(
            "Select one exact session to request an optional model goal summary", out["html"]
        )
        self.assertFalse(out["requested"])

    def test_declining_and_quota_consent_do_not_authorize_session_content(self) -> None:
        out = self._run_page_js(
            """
await __settle(); await __settle();
nextSetUsageConsent("granted"); clickObserver("request");
clickObserver("decline"); clickObserver("request"); await __settle();
console.log(JSON.stringify({html:__els.app.innerHTML,
  requested:__fetchCalls.some(row=>String(row[0]).includes("observer_model=1"))}));
""",
            storage_prelude({}) + self.FIXTURE,
        )
        self.assertIn("Model summaries are off in this browser", out["html"])
        self.assertFalse(out["requested"])

    def test_the_readers_consent_survives_reload_without_automatic_requests(self) -> None:
        out = self._run_page_js(
            """
await __settle(); await __settle();
console.log(JSON.stringify({html:__els.app.innerHTML,
  requested:__fetchCalls.some(row=>String(row[0]).includes("observer_model=1"))}));
""",
            storage_prelude({"cargento.observer-model-consent.v1": "granted"}) + self.FIXTURE,
        )
        self.assertIn("Summarize this session", out["html"])
        self.assertFalse(out["requested"])

    def test_a_pending_request_cannot_be_duplicated_and_failure_keeps_local_analysis(self) -> None:
        out = self._run_page_js(
            """
await __settle(); await __settle();
localStorage.setItem=()=>{throw new Error("storage blocked");};
clickObserver("allow");
let reject;
__fetchImpl=()=>new Promise((_resolve,fail)=>{reject=fail;});
clickObserver("request"); clickObserver("request");
const pending=__els.app.innerHTML;
reject(new Error("offline")); await __settle(); await __settle();
console.log(JSON.stringify({pending,html:__els.app.innerHTML,
  requests:__fetchCalls.filter(row=>String(row[0]).includes("observer_model=1")).length}));
""",
            storage_prelude({}) + self.FIXTURE,
        )
        self.assertIn("Request in progress", out["pending"])
        self.assertEqual(1, out["requests"])
        self.assertIn("The summary request failed. Local analysis remains available", out["html"])
