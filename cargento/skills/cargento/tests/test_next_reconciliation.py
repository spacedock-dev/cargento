from __future__ import annotations

import shutil
import unittest

from . import test_next_cockpit as cockpit_fixtures
from .next_harness import NextPageJsHarness, storage_prelude


@unittest.skipUnless(shutil.which("node"), "node not available")
class ReconciliationReaderTest(NextPageJsHarness):
    def test_a_single_session_console_has_an_exact_session_navigation_link(self) -> None:
        html = self._run_page_js("""
await __settle();
nextData={generated:10000,sessions:[{sid:'one',harness:'codex',project:'repo',state:'idle'}]};
nextRoute={view:'project',project:'repo',tab:'console'};__els.app={innerHTML:''};renderNext();
console.log(JSON.stringify(__els.app.innerHTML));
""")
        self.assertIn('href="#n=project:repo:codex%3Aone:console"', html)
        self.assertIn("Open this session\u2019s console", html)

    def test_an_unfocused_draft_keeps_its_own_scroll_and_resized_height(self) -> None:
        result = self._run_page_js("""
await __settle();
nextData={generated:10000,sessions:[]};nextRoute={view:'projects'};
let replaced=false;
const old={dataset:{nextFocus:'memo:one'},tagName:'TEXTAREA',selectionStart:3,selectionEnd:7,
  scrollTop:80,scrollLeft:4,style:{height:'150px',width:'210px'}};
const fresh={dataset:old.dataset,tagName:'TEXTAREA',style:{},setSelectionRange(a,b){this.caret=[a,b];}};
__els.app={set innerHTML(value){replaced=true;this.html=value;},get innerHTML(){return this.html;},
  querySelectorAll:selector=>selector==='[data-next-focus]'?[replaced?fresh:old]:[]};
document.activeElement=null;renderNext();
console.log(JSON.stringify({scroll:[fresh.scrollTop,fresh.scrollLeft],style:fresh.style,caret:fresh.caret}));
""")
        self.assertEqual([80, 4], result["scroll"])
        self.assertEqual({"height": "150px", "width": "210px"}, result["style"])
        self.assertEqual([3, 7], result["caret"])

    def test_navigation_targets_in_rendered_cards_rows_and_chips_reach_their_routes(self) -> None:
        result = self._run_page_js(
            """
await __settle();await __settle();
const pages=[];
for(const route of [{view:'projects'},{view:'sessions'},{view:'attention'},
  ...NEXT_PROJECT_TABS.map(tab=>({view:'project',project:'cargento',tab}))]){
  nextRoute=route;renderNext();pages.push(__els.app.innerHTML);
}
const tokens=[...new Set(pages.flatMap(html=>[...html.matchAll(/data-next-route="([^"]+)"/g)]
  .map(m=>m[1])))];
const routes=[];
for(const token of tokens){
  const target={dataset:{nextRoute:token},closest:s=>s==='[data-next-route]'?target:null};
  __fire('click',{target,preventDefault(){}});
  routes.push({expected:nextFragmentForRoute(nextRouteFromFragment('#n='+token)),
    actual:nextFragmentForRoute(nextRoute)});
}
const keys=[];
for(const key of ['p','s','a','Escape']){
  __fire('keydown',{key,target:{tagName:'BODY'},preventDefault(){}});keys.push(nextRoute.view);
}
console.log(JSON.stringify({routes,keys}));
""",
            storage_prelude({}) + cockpit_fixtures.NextCockpitCompositionTest.FIXTURE,
        )
        self.assertGreaterEqual(len(result["routes"]), 4)
        for route in result["routes"]:
            self.assertEqual(route["expected"], route["actual"])
        self.assertEqual(["projects", "sessions", "attention", "projects"], result["keys"])

    def test_every_rendered_cockpit_disclosure_has_a_redraw_identity(self) -> None:
        result = self._run_page_js(
            """
await __settle();await __settle();
const html=[];
for(const tab of NEXT_PROJECT_TABS){
  nextRoute={view:'project',project:'cargento',tab};renderNext();html.push(__els.app.innerHTML);
}
console.log(JSON.stringify(html.flatMap(page=>[...page.matchAll(/<details[^>]*>/g)].map(m=>m[0]))));
""",
            storage_prelude({}) + cockpit_fixtures.NextCockpitCompositionTest.FIXTURE,
        )
        self.assertGreater(len(result), 4)
        for opening in result:
            self.assertTrue(
                'class="next-menu"' in opening
                or "data-next-cockpit-disclosure=" in opening
                or "data-pc-disclosure=" in opening,
                opening,
            )

    def test_project_scope_timeline_disclosures_survive_without_a_selected_session(self) -> None:
        result = self._run_page_js("""
nextRoute={view:'project',project:'repo',tab:'decisions'};projectQuerySession='';
const before=projectDisclosure('event:one','Evidence','A source reading');
const attrs=Object.fromEntries([...before.matchAll(/([a-z-]+)="([^"]*)"/g)].map(m=>[m[1],m[2]]));
const details={open:true,getAttribute:name=>attrs[name]};
__els.app={querySelectorAll:selector=>selector==='details[data-pc-disclosure]'?[details]:[]};
projectCaptureDisclosureStates();
const after=projectDisclosure('event:one','Evidence','A source reading');
nextRoute={view:'project',project:'other',tab:'decisions'};
const other=projectDisclosure('event:one','Evidence','Another source');
console.log(JSON.stringify({after,other}));
""")
        self.assertIn(" open", result["after"])
        self.assertNotIn(" open", result["other"])

    def test_a_context_draft_keeps_focus_caret_and_scroll_after_a_redraw(self) -> None:
        result = self._run_page_js(
            """
await __settle();
nextData={generated:10000,sessions:[{sid:'one',harness:'codex',project:'repo',state:'idle'}]};
nextRoute={view:'project',project:'repo',tab:'now'};
const group=nextProjectGroups()[0];
const key=nextCockpitMemoKey(group,null,'outcome');
nextCockpitMemoEditingKey=key; nextCockpitMemoDrafts.set(key,'Keep my place');
__els.app={innerHTML:''};renderNext();
const markup=__els.app.innerHTML.match(/<textarea[^>]*>/)[0];
const named=(markup.match(/data-next-focus="([^"]*)"/)||[])[1];
let replaced=false;
const old={dataset:{nextFocus:named},selectionStart:4,selectionEnd:8,
  scrollTop:17,scrollLeft:3,getBoundingClientRect:()=>({top:-50,bottom:-5,left:0,right:100})};
const fresh={dataset:old.dataset,focus(options){this.options=options;document.activeElement=this;},
  setSelectionRange(a,b){this.caret=[a,b];}};
__els.app={set innerHTML(value){replaced=true;this.html=value;},get innerHTML(){return this.html;},
  querySelectorAll(selector){return selector==='[data-next-focus]'?[replaced?fresh:old]:[];}};
document.activeElement=old;renderNext();
console.log(JSON.stringify({named,focused:document.activeElement===fresh,caret:fresh.caret,
  scroll:[fresh.scrollTop,fresh.scrollLeft],options:fresh.options}));
""",
            storage_prelude({}),
        )
        self.assertTrue(result.get("named"))
        self.assertTrue(result["focused"])
        self.assertEqual([4, 8], result["caret"])
        self.assertEqual([17, 3], result["scroll"])
        self.assertEqual({"preventScroll": True}, result["options"])

    def test_escape_cancels_context_edits_from_the_input_and_done_control(self) -> None:
        result = self._run_page_js(
            """
await __settle();
nextData={generated:10000,sessions:[{sid:'one',harness:'codex',project:'repo',state:'idle'}]};
__els.app={innerHTML:''};
const results=[];
for(const tagName of ['TEXTAREA','BUTTON']){
  nextRoute={view:'project',project:'repo',tab:'now'};
  const key=nextCockpitMemoKey(nextProjectGroups()[0],null,'outcome');
  nextCockpitMemoDrafts.set(key,'Original context');
  const action={dataset:{nextCockpitAction:'memo-edit',arg:key},
    closest:s=>s==='[data-next-cockpit-action]'?action:null};
  __fire('click',{target:action,preventDefault(){}});
  const input={value:'Unfinished change',dataset:{nextCockpitMemoKey:key},
    closest:s=>s==='[data-next-cockpit-memo-input]'?input:null};
  __fire('input',{target:input});
  const target={tagName,closest:s=>s==='[data-next-cockpit-memo-field]'?{}:null};
  let prevented=false;
  __fire('keydown',{target,key:'Escape',preventDefault(){prevented=true;}});
  results.push({prevented,editing:nextCockpitMemoEditingKey,value:nextCockpitReadMemo(key),
    view:nextRoute.view,stored:__store[key]});
}
console.log(JSON.stringify(results));
""",
            storage_prelude({}),
        )
        for result_row in result:
            self.assertEqual(
                {
                    "prevented": True,
                    "editing": None,
                    "value": "Original context",
                    "view": "project",
                    "stored": "Original context",
                },
                result_row,
            )

    def test_the_more_menu_stays_open_after_a_live_redraw(self) -> None:
        result = self._run_page_js("""
await __settle();
nextData={generated:10000,sessions:[{sid:'one',harness:'codex',project:'repo',state:'idle'}]};
nextRoute={view:'project',project:'repo',tab:'now'};
__els.app={innerHTML:''};renderNext();
const summary=__els.app.innerHTML.match(/<summary[^>]*aria-label="More"[^>]*>/)[0];
const key=(summary.match(/data-next-disclosure="([^"]*)"/)||[])[1];
const target={dataset:{nextDisclosure:key},closest:s=>s==='[data-next-disclosure]'?target:null};
__fire('click',{target});renderNext();
console.log(JSON.stringify({summary,menu:__els.app.innerHTML.match(/<details class="next-menu"[^>]*>/)[0]}));
""")
        self.assertIn("data-next-focus=", result["summary"])
        self.assertIn(" open", result["menu"])
