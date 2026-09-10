const NEXT_COCKPIT_MEMO_PREFIX = "cargento.cockpit.memo.v2:";
const NEXT_COCKPIT_MEMO_LIMIT = 500;
const nextCockpitContexts = new Map();
const nextCockpitRequests = new Map();
const nextCockpitMemoDrafts = new Map();
const nextCockpitMemoStates = new Map();
const nextCockpitBriefingCopyStates = new Map();
const nextCockpitDisclosureStates = new Map();
let nextCockpitHadDisclosures = false;
let nextCockpitTerminalScreen = null;
let nextCockpitMemoEditingKey = null;
let nextCockpitMemoOriginal = "";

function nextCockpitDisclosureAttr(control){
  const key = [nextRoute && nextRoute.project || "", nextRoute && nextRoute.focus || "", control].join("\n");
  return ` data-next-cockpit-disclosure="${esc(key)}"`;
}

function nextCockpitSourceText(value){
  return `<span class="next-cockpit-source">${esc(value)}</span>`;
}

function nextCockpitStableKey(group){
  const keys = new Set(group.sessions.map(session => String(session.project_key || "")).filter(Boolean));
  return keys.size === 1 ? [...keys][0] : group.label;
}

function nextCockpitMemoKey(group, focus, kind){
  const scope = focus ? sessKey(focus) : "project";
  return NEXT_COCKPIT_MEMO_PREFIX + encodeURIComponent(nextCockpitStableKey(group)) + ":" +
    encodeURIComponent(scope) + ":" + kind;
}

function nextCockpitBoundMemo(value){
  return typeof value === "string" ? value.slice(0, NEXT_COCKPIT_MEMO_LIMIT) : "";
}

function nextCockpitReadMemo(key){
  if(nextCockpitMemoDrafts.has(key)) return nextCockpitBoundMemo(nextCockpitMemoDrafts.get(key));
  try{
    return nextCockpitBoundMemo(localStorage.getItem(key));
  }catch(_error){
    nextCockpitMemoStates.set(key, "error");
    return "";
  }
}

/* The row's eight flat `annotation_*` fields as one object, or null when the
   row carries none. The payload is flat because `history.PROMPT_TEXT_ALLOWLIST`
   admits field names and a name cannot reach inside a mapping; the renderers
   want an object, so the seam is here and they are unchanged.

   Null when nothing was ever typed AND no reason was published, which is a row
   from a build older than the field set rather than an unannotated session: an
   unannotated row carries its absence sentences. */
function nextCockpitAnnotation(session){
  if(!session) return null;
  /* Eight published fields plus `assessment`, which is not one. Nothing
     produces a reading, so no collector declares that key and no row carries
     it; it is read here so the renderer has one shape whether or not a
     producer ever fills it, and `base_session` is not asked to declare a
     field for an object that does not exist. */
  const fields = ["goal", "goal_why", "output", "output_why", "revision",
    "revision_count", "at", "binding_why", "assessment"];
  const known = fields.some(name => {
    const value = session[`annotation_${name}`];
    return value !== undefined && value !== null && value !== "" && value !== 0;
  });
  if(!known) return null;
  return Object.fromEntries(fields.map(name => [name, session[`annotation_${name}`]]));
}

/* The focused session as `nextObserved` derived it, not the raw row
   `nextCockpitFocusedSession` returns. Only the observed copy carries the
   session's own derived goal, and the raw row's missing keys read as
   `undefined`, which is how a `known` flag defaulted to true and drew an
   empty value as a published one. */
function nextCockpitFocusedObserved(group, project){
  const focus = nextCockpitFocusedSession(group);
  if(!focus || !project) return null;
  const key = sessKey(focus);
  return (project.sessions || []).find(session => sessKey(session) === key) || null;
}

/* The focused session's annotation, or null at project scope. Null is not an
   error: with no one session selected there is nobody whose words these would
   be, and STATED GOAL falls back to the harness row alone. */
function nextCockpitFocusedAnnotation(group){
  return nextCockpitAnnotation(nextCockpitFocusedSession(group));
}

function nextCockpitFocusedSession(group){
  if(!nextRoute || nextRoute.view !== "project" || !nextRoute.focus) return null;
  return group.sessions.find(session => sessKey(session) === nextRoute.focus) || null;
}

function nextCockpitSessionActivityDetail(session){
  const state = String(session && session.state || "").trim().toLowerCase();
  for(const candidate of [session && session.state_detail, session && session.title]){
    const detail = String(candidate || "").trim().replace(/\s+/g, " ");
    if(detail && detail.toLowerCase() !== state) return detail;
  }
  return "";
}

function nextCockpitScopeLabel(group){
  const named = group.sessions.find(session => String(session.project_name || "").trim());
  return String(named && named.project_name || group.label).split("/").filter(Boolean).pop() || "Project";
}

function nextCockpitProjectScopeKind(){
  return {kind:"project", owner:"project"};
}

function nextCockpitSessionScopeKind(session){
  const source = session && session.source_session || session || {};
  const harness = String(source.harness || "");
  const sid = String(source.sid || "");
  if(!harness || !sid) return {kind:"unknown", owner:"unknown"};
  return {kind:"session", owner:`${harness}:${sid}`,
    detail:nextHarnessLabels().get(harness) || nextCockpitHumanLabel(harness)};
}

function nextCockpitFactScope(fact){
  if(!fact || typeof fact !== "object") return {kind:"unknown", owner:"unknown"};
  const declared = String(fact.scope || "").toLowerCase();
  if(declared === "project") return nextCockpitProjectScopeKind();
  if(fact.type === "gate_decision"){
    return declared === "session" ? nextCockpitSessionScopeKind(fact.source_session) :
      nextCockpitProjectScopeKind();
  }
  const session = nextCockpitSessionScopeKind(fact.source_session);
  if(session.kind === "session") return session;
  if(["prepared_dispatch", "stage_transition"].includes(String(fact.type || ""))){
    return nextCockpitProjectScopeKind();
  }
  return {kind:"unknown", owner:"unknown"};
}

function nextCockpitFactSetScope(facts){
  const scopes = (facts || []).map(nextCockpitFactScope);
  if(!scopes.length || scopes.some(scope => scope.kind === "unknown")){
    return {kind:"unknown", owner:"unknown"};
  }
  const sessions = new Map(scopes.filter(scope => scope.kind === "session")
    .map(scope => [scope.owner, scope]));
  if(sessions.size === 1 && scopes.every(scope => scope.kind === "session")){
    return [...sessions.values()][0];
  }
  return nextCockpitProjectScopeKind();
}

function nextCockpitScopeCue(scope){
  const kind = ["project", "session"].includes(scope && scope.kind) ? scope.kind : "unknown";
  const label = kind === "project" ? "PROJECT" : kind === "session" ? "SESSION" : "SCOPE UNKNOWN";
  const marker = kind === "project" ? "square" : kind === "session" ? "round" : "unknown";
  const detail = scope && scope.detail ? `<span>${esc(scope.detail)}</span>` : "";
  return `<span class="next-scope-cue next-scope-cue--${kind}" data-scope-kind="${kind}" ` +
    `data-scope-owner="${esc(scope && scope.owner || "unknown")}">` +
    `<i class="next-scope-marker next-scope-marker--${marker}" aria-hidden="true"></i>` +
    `<strong>${label}</strong>${detail}</span>`;
}

function nextCockpitScopeLinks(group, focus, surface = "tree"){
  const selected = focus ? sessKey(focus) : "project";
  const link = (key, label, state, subtitle, scope) => {
    const route = {view:"project",project:group.label,focus:key === "project" ? null : key,
      tab:nextRoute && nextRoute.tab || "now"};
    return `<a href="${esc(nextFragmentForRoute(route))}" data-next-cockpit-scope="${esc(key)}"` +
      (selected === key ? ` aria-current="page"` : "") +
      ` data-scope-kind="${esc(scope.kind)}" data-next-focus="cockpit-scope:${surface}:${esc(key)}">` +
      nextCockpitScopeCue(Object.assign({}, scope, {detail:""})) +
      `<strong class="next-cockpit-scope-name">${esc(label)}</strong>` +
      (state ? `<span class="next-cockpit-scope-state">${esc(state)}</span>` : "") +
      (subtitle ? `<small${subtitle === "Session title not published" ? ' data-next-withheld' : ""}>` +
        `${esc(String(subtitle).replace(/\s+/g, " ").slice(0, 90))}</small>` : "") +
      `</a>`;
  };
  const rows = [...group.sessions].sort((left, right) =>
    String(left.harness || "").localeCompare(String(right.harness || "")) ||
    sessKey(left).localeCompare(sessKey(right)));
  /* Everything a reader can see about a row. Two sessions of one harness in
     one state under one title render byte-identical links: the session key is
     in the href and in a data attribute, and neither is on screen, so the
     reader picks one of two and finds out which by reading the tab it opens.
     Only the rows that collide carry the sid, because a key beside a name
     that is already unique is noise on every other board. */
  const face = session => [String(session.harness || ""), String(session.state || ""),
    String(session.title || "").trim()].join("\u0000");
  const faces = rows.map(face);
  return link("project", nextCockpitScopeLabel(group), "",
      `${rows.length} ${rows.length === 1 ? "session" : "sessions"}`,
      nextCockpitProjectScopeKind()) +
    rows.map((session, index) => {
      const harness = nextHarnessLabels().get(String(session.harness || "")) ||
        String(session.harness || "Session");
      const twin = faces.some((other, at) => at !== index && other === faces[index]);
      const title = String(session.title || "").trim() || "Session title not published";
      return link(sessKey(session), harness, String(session.state || "unknown"),
        twin ? `${title} · ${String(session.sid || "")}` : title,
        nextCockpitSessionScopeKind(session));
    }).join("");
}

function nextCockpitScopeTree(group, focus){
  return `<nav class="next-cockpit-scope-tree" aria-label="Project scope">` +
    '<span class="next-cockpit-scope-heading">SCOPE</span>' +
    nextCockpitScopeLinks(group, focus) + `</nav>`;
}

function nextCockpitScopeSwitcher(group, focus){
  const selected = focus
    ? `Viewing session · ${nextCockpitSessionScopeKind(focus).detail || "Session"} · ` +
      String(focus.state || "state unavailable")
    : `Viewing project · ${nextCockpitScopeLabel(group)}`;
  return '<details class="next-cockpit-scope-switcher"' + nextCockpitDisclosureAttr("scope") + '>' +
    `<summary><span>${esc(selected)}</span><strong>Change scope</strong></summary>` +
    `<nav class="next-cockpit-scope-options" aria-label="Change project scope">` +
    nextCockpitScopeLinks(group, focus, "switcher") + '</nav></details>';
}

function nextCockpitHumanLabel(value){
  const words = String(value || "work").replace(/[-_]+/g, " ").trim();
  return words ? words[0].toUpperCase() + words.slice(1) : "Work";
}

function nextCockpitProjectNeeds(group){
  return nextCockpitObservedProject(group)?.needs.length || 0;
}

function nextCockpitObservedProject(group){
  return nextCurrentObserved().projects.find(project => project.key === group.label);
}

function nextCockpitWorkingSessions(group){
  const keys = new Set((nextCockpitObservedProject(group)?.working || []).map(nextSessionKey));
  return group.sessions.filter(session => keys.has(nextSessionKey(session)));
}

function nextCockpitProjectStatus(group, semantic){
  const needs = nextCockpitProjectNeeds(group);
  const labels = new Map((semantic.work_items || []).map(item =>
    [String(item.work_item_id || ""), nextCockpitHumanLabel(item.label)]));
  const seen = new Set();
  const decisions = (semantic.facts || []).filter(fact =>
    fact && fact.type === "gate_decision" && fact.by === "person:captain")
    .sort((left, right) => Number(right.at || 0) - Number(left.at || 0))
    .filter(fact => {
      const key = [fact.work_item_id, fact.decision, fact.stage, fact.application_state,
        fact.target_stage].join("\n");
      if(seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  const row = fact => {
    const label = labels.get(String(fact.work_item_id || "")) || "Workflow item";
    return `<li><strong>${esc(label + " · " + projectGateApplicationResult(fact))}</strong></li>`;
  };
  const latest = decisions.slice(0, 2).map(row).join("");
  const older = decisions.slice(2);
  const history = older.length ? `<details${nextCockpitDisclosureAttr("older-status")}><summary>${older.length} older ` +
    `${older.length === 1 ? "decision" : "decisions"}</summary><ul>${older.map(row).join("")}</ul></details>` : "";
  const decisionList = latest ? `<ul>${latest}</ul>${history}` :
    '<span class="next-cockpit-status-empty">No captain decisions observed</span>';
  return '<section class="next-cockpit-project-status" aria-label="Project status">' +
    `<strong>${needs ? `Gate or ask observed · ${needs}` : "No gate or ask observed"}</strong>` +
    `<div><span>Latest decisions</span>${decisionList}</div></section>`;
}

function nextCockpitCaptainDecisionCounts(semantic){
  const counts = {pending:0, unknown:0, superseded:0, applied:0};
  for(const fact of projectDecisionFacts(semantic)){
    const state = String(fact.application_state || "unknown").toLowerCase();
    if(state === "pending" || state === "unspent") counts.pending += 1;
    else if(state === "consumed" || state === "applied") counts.applied += 1;
    else if(state === "superseded") counts.superseded += 1;
    else counts.unknown += 1;
  }
  return counts;
}

function nextCockpitRecoveryOutcome(group, observation){
  const discovery = observation && observation.workflow_discovery || {};
  const workflows = Array.isArray(discovery.workflows) ? discovery.workflows : [];
  if(discovery.state === "observed"){
    const workflow = workflows.find(row => String(row && row.goal || "").trim());
    if(workflow) return String(workflow.goal).trim();
  }
  return "Outcome not recorded";
}

function nextCockpitSourceFailures(observation){
  const failures = [];
  const sources = observation && observation.sources || {};
  for(const [name, channel] of Object.entries(sources)){
    if(!channel || !Array.isArray(channel.unavailable)) continue;
    for(const row of channel.unavailable){
      const reason = String(row && row.reason || "source unavailable").trim();
      const failure = `${nextCockpitHumanLabel(name)} · ${reason}`;
      if(reason && !failures.includes(failure)) failures.push(failure);
    }
  }
  return failures;
}

function nextCockpitAttentionCoverage(group, observation){
  const entry = nextCockpitContexts.get(nextCockpitContextKey(group, null));
  if(!observation || entry && entry.error){
    return {state:"unavailable",label:"Captain attention unavailable",
      source:entry && entry.error ? "project context request failed" : "project context pending",
      scanned:null,total:null};
  }
  const semantic = observation.semantic || {};
  const raw = semantic.projections && semantic.projections.command_attention_coverage || {};
  const state = String(raw.state || "");
  const scanned = Number(raw.scanned);
  const total = Number(raw.total);
  const omitted = Number(raw.omitted);
  if(!["complete", "incomplete"].includes(state) || !Number.isFinite(scanned) ||
    !Number.isFinite(total) || scanned < 0 || total < scanned){
    return {state:"unavailable",label:"Captain attention unavailable",
      source:"project context coverage unavailable",scanned:null,total:null};
  }
  const count = `${scanned} of ${total} active ${total === 1 ? "session" : "sessions"}`;
  if(state === "incomplete"){
    const missing = Number.isFinite(omitted) && omitted >= 0 ? omitted : total - scanned;
    return {state,label:`Coverage incomplete · ${count} · ${missing} omitted`,scanned,total,
      source:String(raw.source || "active-session attention scan")};
  }
  return {state,label:`Coverage complete · ${count}`,scanned,total,
    source:String(raw.source || "active-session attention scan")};
}

function nextCockpitRecoveryChildren(group){
  const active = nextCockpitWorkingSessions(group)
    .flatMap(session => projectDelegationLanes(session, {label:nextCockpitStableKey(group)}))
    .filter(lane => lane.active !== false)
    .map(lane => ({worker:lane.worker,lifecycle:"active",assignment:lane.assignment,
      assignmentSource:lane.source,sourceSession:lane.parentSession,workItemId:lane.workItemId}));
  const returned = group.sessions.flatMap(session =>
    (Array.isArray(session.subagent_events) ? session.subagent_events : [])
      .filter(event => event && event.kind === "subagent_complete")
      .map(event => {
        const at = Number(event.at) || 0;
        const ageSec = nextAgeSeconds(at);
        const assignment = typeof event.assignment === "string" && event.assignment.trim()
          ? event.assignment.trim() : "assignment unavailable";
        const result = [event.result, event.result_summary]
          .find(value => typeof value === "string" && value.trim())?.trim() ||
          "result unavailable";
        return {worker:String(event.name || "Child"),lifecycle:"returned",assignment,
          assignmentSource:String(event.source || "child lifecycle source unavailable"),
          result,handoffUnavailable:assignment === "assignment unavailable" &&
            result === "result unavailable",
          sourceSession:sessKey(session),at,ageSec,age:nextFormatDuration(ageSec)};
      }))
    .sort((left, right) => right.at - left.at);
  return {active,latestReturn:returned[0] || null};
}

function nextCockpitCommandAttention(group, observation){
  const attention = [];
  const add = (owner, label, source, confidence = "exact", kind = "") => attention.push({
    owner, label, kind, evidence:{source, confidence},
  });
  const semantic = observation && observation.semantic || {};
  const projected = semantic.projections && Array.isArray(semantic.projections.command_attention)
    ? semantic.projections.command_attention : [];
  for(const item of projected){
    if(!item || !["CAPTAIN", "FO"].includes(item.owner)) continue;
    const kind = String(item.kind || "");
    const question = String(item.question || "").trim();
    const blockedStep = String(item.blocked_step || "").trim();
    if(item.owner === "CAPTAIN" && !question){
      const recorded = kind.replaceAll("_", " ").trim() || "decision";
      attention.push({owner:"FO",kind:"decision_application",
        label:`apply recorded ${recorded}`,question:"",blockedStep,
        evidence:item.evidence || {}});
      continue;
    }
    const label = question || String(item.label || "resolve system follow-up");
    attention.push({owner:item.owner,label,question,kind,blockedStep,
      evidence:item.evidence || {}});
  }
  const coverage = nextCockpitAttentionCoverage(group, observation);
  if(coverage.state === "unavailable"){
    attention.push({owner:"FO",kind:"coverage_inspection",
      label:"refresh captain-attention scan",question:"",
      evidence:{source:coverage.source,confidence:"unavailable"}});
  }else if(coverage.state === "incomplete"){
    attention.push({owner:"FO",kind:"coverage_inspection",
      label:"complete captain-attention scan",question:"",
      evidence:{source:coverage.source,
        confidence:"bounded"}});
  }
  const waiting = nextCockpitObservedProject(group)?.needs || [];
  for(const session of waiting){
    if(session.askKnown){
      add("CAPTAIN", session.askText, "AskRegistry exact question", "exact", "ask");
      continue;
    }
    const name = nextHarnessLabels().get(String(session.harness || "")) ||
      nextCockpitHumanLabel(session.harness || "session");
    add("FO", `inspect ${name} input request`, "exact session needs-input state",
      "unavailable");
  }

  const discovery = observation && observation.workflow_discovery || {};
  const projectedDiscovery = projected.some(item => item && item.owner === "FO" &&
    /workflow discovery/i.test(String(item.question || item.label || "")));
  if(discovery.state === "error" && !projectedDiscovery){
    const reason = String(discovery.reason || "source error").trim();
    add("FO", "refresh workflow discovery",
      `${String(discovery.source || "project workflow discovery")} · ${reason}`);
  }else if(discovery.state === "unavailable" && !projectedDiscovery){
    const reason = String(discovery.reason || "source unavailable").trim();
    add("FO", "refresh workflow discovery",
      `${String(discovery.source || "project workflow discovery")} · ${reason}`);
  }
  const failures = nextCockpitSourceFailures(observation);
  if(failures.length){
    const observer = failures.some(reason => /observer/i.test(reason));
    add("FO", observer ? "refresh observer" : "inspect project context source",
      failures.join(" · "), "unavailable");
  }

  const trails = semantic.projections && Array.isArray(semantic.projections.trail_heads)
    ? semantic.projections.trail_heads : [];
  const unreturned = trails.filter(row => row && ["prepared", "requested"].includes(row.status));
  if(unreturned.length){
    const retried = unreturned.filter(row => Number(row.dispatch_count || 0) > 1).length;
    add("FO", `inspect assignment return · ${unreturned.length}` +
      (retried ? ` · ${retried} retried` : ""), "semantic task trail heads");
  }

  const idle = group.sessions.filter(session => session.state === "idle");
  const stale = group.sessions.filter(session => {
    const age = nextAgeSeconds(session.last_activity);
    return session.state !== "idle" && age != null && age >= NEXT_PROJECT_STALLED_SEC;
  });
  if(idle.length || stale.length){
    const parts = [];
    if(idle.length) parts.push(`inspect idle owner · ${idle.length}`);
    if(stale.length) parts.push(`refresh stale owner · ${stale.length}`);
    add("FO", parts.join(" · "), "exact session state");
  }
  const children = nextCockpitRecoveryChildren(group);
  for(const child of children.active){
    if(child.assignment !== "assignment unavailable") continue;
    add("FO", `inspect ${child.worker} assignment`, child.assignmentSource,
      "unavailable", "child_evidence_gap");
  }
  const returned = children.latestReturn;
  if(returned && (returned.assignment === "assignment unavailable" ||
      returned.result === "result unavailable")){
    if(returned.handoffUnavailable){
      add("FO", `recover ${returned.worker} handoff`, returned.assignmentSource,
        "unavailable", "child_evidence_gap");
    }else if(/source unavailable/i.test(returned.assignmentSource)){
      const gaps = [returned.assignment === "assignment unavailable" ? "assignment" : "",
        returned.result === "result unavailable" ? "result" : ""].filter(Boolean);
      add("FO", `inspect ${returned.worker} ${gaps.join("/")}`,
        returned.assignmentSource, "unavailable", "child_evidence_gap");
    }else{
      add("FO", `inspect ${returned.worker} handoff`, returned.assignmentSource,
        "unavailable", "child_evidence_gap");
    }
  }
  const rank = owner => owner === "CAPTAIN" ? 0 : 1;
  const seen = new Set();
  return attention.filter(item => {
    const key = `${item.owner}\n${item.label}`;
    if(seen.has(key)) return false;
    seen.add(key);
    return true;
  }).sort((left, right) => rank(left.owner) - rank(right.owner));
}

function nextCockpitAuthorityVerb(item){
  const kind = String(item && item.kind || "").toLowerCase();
  if(item && item.owner === "CAPTAIN"){
    if(/authori|approv/.test(kind)) return "AUTHORIZE";
    if(/cho(?:ice|ose)|select/.test(kind)) return "CHOOSE";
    if(/revis/.test(kind)) return "REVISE";
    return "ANSWER";
  }
  const label = String(item && item.label || "").toLowerCase();
  if(kind === "decision_application" || /^apply\b/.test(label)) return "APPLY";
  if(/^refresh\b/.test(label)) return "REFRESH";
  if(/^complete\b/.test(label)) return "COMPLETE";
  if(/^link\b/.test(label)) return "LINK";
  return "INSPECT";
}

function nextCockpitRecoveryAttention(group, observation, commandAttention){
  const attention = commandAttention || nextCockpitCommandAttention(group, observation);
  const coverage = nextCockpitAttentionCoverage(group, observation);
  const row = item => `<strong>${esc(nextCockpitAuthorityVerb(item) + " · " + item.label)}</strong>`;
  const evidence = item => `<small>${esc(item.owner + " · " +
    (item.kind || "attention") + " · " + item.label + " · " +
    String(item.evidence && item.evidence.source || "source unavailable") + " · " +
    String(item.evidence && item.evidence.confidence || "confidence unavailable"))}</small>`;
  const captain = attention.filter(item => item && item.owner === "CAPTAIN");
  const system = attention.filter(item => item && item.owner === "FO");
  const state = captain.length ? "captain-needed" :
    coverage.state !== "complete" || system.length ? "fo-inspecting" : "fo-continues";
  const stateLabel = state === "captain-needed" ? "CAPTAIN NEEDED" :
    state === "fo-inspecting" ? "FO INSPECTING" : "FO CONTINUES";
  const children = nextCockpitRecoveryChildren(group);
  const compactIdle = state === "fo-continues" && !children.active.length &&
    !children.latestReturn && !nextCockpitProjectNeeds(group);
  const captainTruth = captain.length || nextCockpitProjectNeeds(group) ? "" : coverage.state === "complete"
    ? "Captain not needed" : "Captain state unknown";
  const stateHeading = compactIdle ? "FO CONTINUES · Continue current assignment" : stateLabel;
  const primary = compactIdle ? "" : captain.map(row).join("") +
    (system[0] ? row(system[0]) : "") +
    (captainTruth ? `<small>${captainTruth}</small>` : "");
  const remainder = Math.max(0, system.length - 1);
  const evidenceRows = attention.map(evidence).join("") +
    (remainder ? `<small>${remainder} more FO ${remainder === 1 ? "action" : "actions"}</small>` : "") +
    `<small data-next-cockpit-attention-coverage>${esc(coverage.label + " · " + coverage.source)}</small>`;
  return `<div class="next-cockpit-authority next-cockpit-authority--${state}" ` +
    `data-next-cockpit-authority-state="${state}"><span>${stateHeading}</span>${primary}` +
    (coverage.state !== "complete" ? `<p class="next-cockpit-evidence-missing">` +
      `${esc(coverage.label + " · " + coverage.source)}</p>` : "") +
    `<details${nextCockpitDisclosureAttr("attention")}><summary>Evidence · attention sources</summary>${evidenceRows}</details></div>`;
}

function nextCockpitRecoveryDecisions(semantic){
  const counts = nextCockpitCaptainDecisionCounts(semantic);
  const total = Object.values(counts).reduce((sum, value) => sum + value, 0);
  if(!total) return "No captain decisions observed";
  const labels = {pending:"pending", unknown:"unknown", superseded:"superseded",
    applied:"consumed/applied"};
  return ["pending", "unknown", "superseded", "applied"]
    .filter(key => counts[key])
    .map(key => `${labels[key]} ${counts[key]}`)
    .join(" · ");
}

function nextCockpitRecoveryActive(group){
  const activeSessions = nextCockpitWorkingSessions(group);
  const exactAssignments = activeSessions.flatMap(session =>
    projectDelegationLanes(session, {label:nextCockpitStableKey(group)}))
    .filter(lane => lane.active !== false && lane.assignment !== "assignment unavailable" &&
      /(?:exact|structured)/i.test(String(lane.source || "")));
  if(!activeSessions.length && !exactAssignments.length){
    return "No active sessions or exact assignments observed";
  }
  return `${activeSessions.length} active ${activeSessions.length === 1 ? "session" : "sessions"}` +
    ` · ${exactAssignments.length} exact ${exactAssignments.length === 1 ? "assignment" : "assignments"}`;
}

function nextCockpitFactSessionKey(fact){
  const source = fact && fact.source_session || {};
  const harness = String(source.harness || "");
  const sid = String(source.sid || "");
  return harness && sid ? `${harness}:${sid}` : "";
}

function nextCockpitSubstantiveDirection(group, semantic){
  const active = new Set(nextCockpitWorkingSessions(group)
    .map(session => sessKey(session)));
  const known = new Set(group.sessions.map(session => sessKey(session)));
  const facts = semantic && Array.isArray(semantic.facts) ? semantic.facts : [];
  const candidates = facts.filter(fact => {
    if(!fact || fact.type !== "user_message" || fact.intent_promoted === false ||
      !fact.evidence || fact.evidence.confidence !== "exact") return false;
    const source = nextCockpitFactSessionKey(fact);
    const summary = String(fact.summary || "").trim();
    if(!source || !known.has(source) || !summary) return false;
    if(/^(?:great|thanks|thank you|ok|okay|well|got it|acknowledged)[.!\s]*$/i.test(summary)){
      return false;
    }
    if(/^https?:\/\/\S+\/?$/i.test(summary)) return false;
    if(/\b(?:playwright(?:-chrome)?|built-?in browser|browser works|sandbox access|broader sandbox)\b/i
      .test(summary)) return false;
    if(/^(?:please\s+)?(?:send|report|share|provide)\b.{0,40}\b(?:progress|status|update)\b/i
      .test(summary)) return false;
    return true;
  });
  const pool = candidates.some(fact => active.has(nextCockpitFactSessionKey(fact)))
    ? candidates.filter(fact => active.has(nextCockpitFactSessionKey(fact))) : candidates;
  return pool.sort((left, right) => Number(right.at || 0) - Number(left.at || 0))[0] || null;
}

function nextCockpitStageLinkEffect(group, commandAttention, sourceSession){
  const blocked = (commandAttention || []).find(item => item && item.owner === "FO" &&
    item.kind === "stage_link_required" && item.blockedStep && item.evidence &&
    item.evidence.confidence === "exact");
  if(blocked) return `Stage link required before ${blocked.blockedStep}`;
  const canContinue = nextCockpitWorkingSessions(group).some(session => sessKey(session) === sourceSession);
  return canContinue ? "Stage link missing · current work can continue" : "";
}

function nextCockpitRecoveryAssignment(group, semantic, observation, commandAttention){
  const current = nextCockpitCurrentTask(observation);
  if(current.known){
    const bound = (semantic && Array.isArray(semantic.facts) ? semantic.facts : [])
      .filter(fact => fact && String(fact.work_item_id || "") === current.id &&
        nextCockpitFactSessionKey(fact))
      .sort((left, right) => Number(right.at || 0) - Number(left.at || 0))[0] || null;
    return Object.assign({}, current, {provenance:"Exact workflow state",qualifier:"",
      sourceSession:nextCockpitFactSessionKey(bound),fact:null});
  }
  const fact = nextCockpitSubstantiveDirection(group, semantic);
  if(!fact) return Object.assign({}, current, {provenance:"",qualifier:"",
    sourceSession:"",fact:null});
  const summary = String(fact.summary || "").trim();
  const sourceSession = nextCockpitFactSessionKey(fact);
  return {known:true,id:"",label:summary[0].toUpperCase() + summary.slice(1),stage:"",
    provenance:"Exact operator direction",
    qualifier:nextCockpitStageLinkEffect(group, commandAttention, sourceSession),
    sourceSession,fact};
}

function nextCockpitLatestSessionResult(group, sourceSession){
  const outputs = group.sessions.filter(session => !sourceSession || sessKey(session) === sourceSession)
    .map(session => {
    const summary = typeof session.last_output === "string" ? session.last_output.trim() : "";
    const firstLine = summary.split(/\r?\n/).map(line => line.trim()).find(Boolean) || "";
    const display = firstLine.length > 180 ? firstLine.slice(0, 177).trimEnd() + "…" : firstLine;
    return {summary,display,at:Number(session.last_activity) || 0,
      source_session:{harness:String(session.harness || ""),sid:String(session.sid || "")},
      evidence:{source:"attributable session output",confidence:"uncertain"}};
  }).filter(result => result.summary && result.source_session.harness && result.source_session.sid)
    .sort((left, right) => right.at - left.at);
  return outputs[0] || null;
}

function nextCockpitRecoveryLatest(group, semantic, stale, assignment){
  const exact = type => (semantic && Array.isArray(semantic.facts) ? semantic.facts : [])
    .filter(fact => fact && fact.type === type && fact.evidence &&
      fact.evidence.confidence === "exact" && String(fact.summary || "").trim())
    .sort((left, right) => Number(right.at || 0) - Number(left.at || 0));
  const direction = assignment.fact || nextCockpitSubstantiveDirection(group, semantic);
  const semanticResult = exact("result").find(fact =>
    assignment.id && String(fact.work_item_id || "") === assignment.id ||
    assignment.sourceSession && nextCockpitFactSessionKey(fact) === assignment.sourceSession) || null;
  const sessionResult = semanticResult || !assignment.sourceSession ? null :
    nextCockpitLatestSessionResult(group, assignment.sourceSession);
  return {direction,directionInAssignment:!!assignment.fact,result:semanticResult || sessionResult,
    resultKind:semanticResult ? "semantic" : sessionResult ? "session" : "unavailable",
    stale:!!stale};
}

function nextCockpitRecoveryFactSource(fact){
  const source = fact && fact.source_session || {};
  const harness = String(source.harness || "");
  const sid = String(source.sid || "");
  return harness && sid ? `${harness}:${sid}` : "unavailable";
}

function nextCockpitRecoveryBriefing(group, focus, observation, commandAttention){
  const semantic = observation && observation.semantic || {};
  const context = nextCockpitContexts.get(nextCockpitContextKey(group, null));
  const outcome = nextCockpitReadMemo(nextCockpitMemoKey(group, focus, "outcome")) || "Not set";
  const currentFocus = nextCockpitReadMemo(nextCockpitMemoKey(group, focus, "focus")) || "Not set";
  const task = nextCockpitRecoveryAssignment(group, semantic, observation, commandAttention);
  const active = nextCockpitRecoveryActive(group);
  const latest = nextCockpitRecoveryLatest(group, semantic, context && context.error, task);
  const decisions = nextCockpitRecoveryDecisions(semantic);
  const coverage = nextCockpitAttentionCoverage(group, observation);
  const children = nextCockpitRecoveryChildren(group);
  const captain = (commandAttention || []).filter(item => item && item.owner === "CAPTAIN" &&
    !["coverage_unavailable"].includes(String(item.kind || "")) &&
    item.label !== "Captain-attention coverage incomplete");
  const activeSessions = nextCockpitWorkingSessions(group);
  const assignments = activeSessions.flatMap(session =>
    projectDelegationLanes(session, {label:nextCockpitStableKey(group)}))
    .filter(lane => lane.active !== false && lane.assignment !== "assignment unavailable" &&
      /(?:exact|structured)/i.test(String(lane.source || "")));
  const returnedAge = children.latestReturn && (children.latestReturn.age
    ? `${children.latestReturn.age} ago${children.latestReturn.ageSec >= NEXT_PROJECT_STALLED_SEC
      ? " · stale" : ""}` : "age unavailable");
  const lines = [
    "Cargento recovery briefing",
    `Project: ${nextCockpitScopeLabel(group)}`,
    `Scope: ${focus ? `Session ${sessKey(focus)}` : "Project"}`,
    ...(outcome !== "Not set" ? [`Outcome (browser-local): ${outcome}`] : []),
    ...(currentFocus !== "Not set" ? [`Focus (browser-local): ${currentFocus}`] : []),
    `Assignment: ${task.known ? [task.label, task.stage, task.provenance, task.qualifier]
      .filter(Boolean).join(" · ") : "Not observed"}`,
    `Active: ${active}`,
    `Active sessions: ${activeSessions.length ? activeSessions.map(session =>
      `${sessKey(session)} · ${session.state}`).join("; ") : "None observed"}`,
    `Active children: ${children.active.length ? children.active.map(child =>
      `${child.worker} · ${child.lifecycle} · ${child.assignment} · source session ` +
      child.sourceSession).join("; ") : "None observed"}`,
    `Latest returned child (bounded 1): ${children.latestReturn ?
      `${children.latestReturn.worker} · ${children.latestReturn.lifecycle} · ` +
      `${children.latestReturn.assignment} · ${children.latestReturn.result} · source session ` +
      `${children.latestReturn.sourceSession} · ${returnedAge}` : "None observed"}`,
    `Exact assignments: ${assignments.length ? assignments.map(lane => lane.assignment).join("; ") :
      "None observed"}`,
    ...(latest.direction ? [
      `${latest.stale ? "Actionable direction (stale cached)" : "Latest actionable direction"}: ` +
        `${latest.direction.summary} · source session ` +
        nextCockpitRecoveryFactSource(latest.direction),
    ] : []),
    ...(latest.resultKind === "semantic" ? [
      `${latest.stale ? "Exact result (stale cached)" : "Latest exact result"}: ` +
        `${latest.result.summary} · source session ${nextCockpitRecoveryFactSource(latest.result)}`,
    ] : latest.resultKind === "session" ? [
      `Latest session result: ${latest.result.summary} · source session ` +
        `${nextCockpitRecoveryFactSource(latest.result)} · uncertainty: ` +
        "session output; semantic result not captured",
    ] : []),
    `Decisions: ${decisions}`,
    `Captain attention: ${captain.length ? captain.map(item => item.label).join("; ") :
      coverage.state === "complete" ? "None observed" : coverage.label}`,
    `Attention coverage: ${coverage.label} · source ${coverage.source}`,
  ];
  return {outcome,currentFocus,task,active,children,latest,decisions,coverage,text:lines.join("\n")};
}

/* Project scope only, since DRC-4508. The `Held to` tab put two more typed
   fields on the session-scope page, and four of them across two bounds (240
   here, 500 there) and two save semantics (a numbered revision on the server,
   autosave into this browser) is a surface nobody can read the rules off. The
   memo cell keeps the scope where it has no rival; nothing is deleted, and
   whether the two should merge is a decision worth filing rather than
   guessing. */
/* DRC-4508's input surface: the two fields a person types their own intent
   into, at session scope, saved as numbered revisions on the server.

   Drafts live in a module Map rather than in the DOM, the way
   `nextCockpitMemoDrafts` does, so a redraw between keystrokes cannot lose
   what is half-typed. `next-chrome.js` puts the caret and the internal scroll
   back for any `[data-next-focus]` input, which is why every field carries
   one. See docs/design-reader-state.md. */
const nextCockpitHeldDrafts = new Map();
const nextCockpitHeldStates = new Map();
const NEXT_COCKPIT_HELD_CAP = 240;
const NEXT_COCKPIT_HELD_FIELDS = [
  ["goal", "TYPED GOAL", "goal", "goal_why", "what you are after, in one line"],
  ["output", "EXPECTED OUTPUT", "output", "output_why", "what should exist when it is done"],
];

function nextCockpitHeldKey(session, kind){
  return `held:${String(session && session.harness || "")}:` +
    `${String(session && session.sid || "")}:${kind}`;
}

function nextCockpitHeldCap(){
  const cap = nextNumber(nextData && nextData.annotate_cap);
  return cap != null && cap > 0 ? Math.round(cap) : NEXT_COCKPIT_HELD_CAP;
}

/* One field. `saved` is what the server holds, `draft` is what is in the box.
   `clear` appears only where there is text to clear and `save` only where the
   box and the store disagree, both per the design; a save control standing on
   an unchanged field invites a revision number that records nothing. */
/* Rendered either way and hidden when it does not apply, because the input
   handler above cannot redraw and has to reach an element that is already
   there. `hidden` rather than a class: it is the attribute that means this,
   and `styles.css` is where it is made to stick. */
/* The store's own character class, character for character. `records.safe_text`
   turns every run of these into ONE space before the store sees anything, so a
   pasted line break was already gone at the save while the box still showed it
   and the cue said "Saved as a new revision." under text the store never held.
   Collapsing here makes the box show what will be stored.

   Spelled with escapes rather than raw codepoints for two reasons: it is then
   byte-identical to `records._UNSAFE_CHARS.pattern`, which
   `AnnotationFieldCollapseTest` pins so the two spellings cannot drift; and a
   raw bidi control in a source file is the thing this class exists to strip. */
const NEXT_COCKPIT_HELD_UNSAFE = /[\x00-\x1f\x7f\u200b\u200e\u200f\u202a-\u202e\u2066-\u2069]+/g;

function nextCockpitHeldControl(action, label, kind, shown){
  return `<button type="button" data-next-cockpit-action="${action}" data-arg="${kind}"` +
    `${shown ? "" : " hidden"}>${label}</button>`;
}

function nextCockpitHeldToggle(field, action, shown){
  const control = field.querySelector(`[data-next-cockpit-action="${action}"]`);
  if(control) control.hidden = !shown;
}

/* What the last save attempt is still worth saying, and for how long.
   Stamped and expiring, because an unstamped cue survives every redraw and a
   navigation away and back, so "Saved as a new revision." greets a reader
   returning hours later as though they had just pressed it. The row controls
   next door already expire their confirmation for that reason.

   `persisted:false` is its own cue and not a success. The endpoint answers it
   honestly when the store could not be written, and the annotation is then
   held only in this process: the next collection reloads the store from disk
   and the words are gone. An earlier version of this code read only `ok` and
   called that a save, with a comment claiming the store said so itself. It
   does not; the only report went to a diagnostic sink no reader sees. */
const NEXT_COCKPIT_HELD_CUE_LIMIT = 16;
const NEXT_COCKPIT_HELD_CUES = {
  error: "Not saved. The server refused the write, and your words are still in the box.",
  unpersisted: "Not stored. The store could not be written, so the refresh has already " +
    "dropped these words, and they are still in the box.",
  saved: "Saved as a new revision.",
};

function nextCockpitHeldCue(key){
  const held = nextCockpitHeldStates.get(key);
  if(!held) return "";
  // The same clock and the same window the row controls use, so two cues on
  // one page do not disagree about how long a confirmation is worth.
  if(Date.now() - held.at >= NEXT_CONTROL_STATE_TTL_MS){
    nextCockpitHeldStates.delete(key);
    return "";
  }
  return NEXT_COCKPIT_HELD_CUES[held.kind] || "";
}

function nextCockpitHeldMark(key, kind){
  nextCockpitHeldStates.delete(key);
  nextCockpitHeldStates.set(key, {kind, at: Date.now()});
  while(nextCockpitHeldStates.size > NEXT_COCKPIT_HELD_CUE_LIMIT){
    nextCockpitHeldStates.delete(nextCockpitHeldStates.keys().next().value);
  }
}

function nextCockpitHeldField(session, annotation, spec, cap){
  const [kind, label, valueKey, whyKey, placeholder] = spec;
  const key = nextCockpitHeldKey(session, kind);
  const saved = String(annotation && annotation[valueKey] || "");
  const draft = nextCockpitHeldDrafts.has(key) ? nextCockpitHeldDrafts.get(key) : saved;
  const why = String(annotation && annotation[whyKey] || "");
  const cue = nextCockpitHeldCue(key);
  return `<div class="next-cockpit-held-field" data-next-cockpit-held-field="${kind}">` +
    `<span class="next-cockpit-held-label">${label}</span>` +
    '<span class="next-cockpit-held-sub">your words</span>' +
    `<textarea maxlength="${cap}" data-next-cockpit-held-kind="${kind}" ` +
    `data-next-cockpit-held-key="${esc(key)}" data-next-cockpit-held-saved="${esc(saved)}" ` +
    `data-next-focus="${esc(key)}" placeholder="${esc(placeholder)}">${esc(draft)}</textarea>` +
    `<span class="next-cockpit-held-count" data-next-cockpit-held-count="${kind}">` +
    `${draft.length}/${cap}</span>` +
    nextCockpitHeldControl("held-clear", "clear", kind, Boolean(draft)) +
    nextCockpitHeldControl("held-save", "save", kind, draft !== saved) +
    /* The absence sentence answers "why is this empty", so it goes when the
       box stops being empty. It read the SERVER value alone, which put "No
       goal typed for this session." directly under the sentence the reader
       was in the middle of typing. */
    /* Rendered and hidden rather than rendered conditionally, for the reason
       the input handler gives: a keystroke does not redraw, so a paragraph
       that only the renderer can remove stays under the sentence being
       typed. */
    (why ? `<p class="next-cockpit-held-absent" data-next-cockpit-held-absent="${kind}"` +
      `${draft ? " hidden" : ""}>${esc(why)}</p>` : "") +
    (cue ? `<small class="next-cockpit-held-cue">${esc(cue)}</small>` : "") + '</div>';
}

/* DRC-4509's work evidence: what the observed record lets a reader inspect,
   beside the words they typed. No judgement is attached and no model is
   called; the comparison is theirs.

   Each row keeps the fact's own `type` and the source that published it. The
   issue's rule is that an entry is a decision only where the source records
   one explicitly, and the cheapest way to keep that rule is never to rename a
   type on the way to the screen.

   The limit line is unconditional and it is the half a reader cannot infer.
   Demonstrated work results come from `_work_evidence`, which returns nothing
   for any harness but Pi, so on Claude and Codex the rows above are
   instructions, dispatches and gate decisions and never an inspected file,
   test or deliverable. Without the sentence an empty list reads as "no work
   was done" rather than "that path was never taken here". */
function nextCockpitWorkEvidenceLimit(harness){
  const label = nextHarnessLabels().get(harness) || nextCockpitHumanLabel(harness);
  return harness === "pi"
    ? `${label} publishes demonstrated work results, and they are read here.`
    : `${label} publishes no demonstrated work results. Cargento reads those on Pi ` +
      "alone, so nothing above is an inspected file, test or deliverable.";
}

/* The entries, once. The rows below render them and a reading cites them, so
   a citation resolves against the same list the reader is looking at rather
   than against a second collection assembled from the same facts. */
/* Where the observed record for one session comes from, and how far the page
   can be trusted to have it.

   Two contexts exist: the project one, which the server bounds to its most
   recently active sessions, and a focus-scoped one it fetches for the session
   the reader selected. The focused fetch is the one that names this session on
   purpose, so it wins where it has landed.

   The state matters as much as the entries. "No entry in the observed record
   names this session" is a claim ABOUT a record, and the block printed it
   while the fetch was still in flight, after the fetch had failed, and for a
   session the server had said in the same payload it did not scan. Three
   different facts wearing one sentence, and the least true of them read as
   the most reassuring. */
function nextCockpitWorkSource(group, session){
  const key = sessKey(session);
  const focused = nextCockpitContexts.get(nextCockpitContextKey(group, session));
  const project = nextCockpitContexts.get(nextCockpitContextKey(group, null));
  const entry = focused && focused.data ? focused : project;
  if(!entry) return {entries: [], state: "unread"};
  if(!entry.data) return {entries: entry.error ? [] : [], state: entry.error ? "error" : "unread"};
  const all = nextCockpitWorkEntries(session, entry.data.semantic);
  /* The most recent, in the order they happened. Nothing upstream caps the
     semantic facts, so a long session draws as many rows as it has entries.

     `all` is published beside the window because this bound is a readability
     bound and nothing else. It was handed to the reading as well, which made
     it a citation bound too: a departure citing a fact older than the window
     stopped resolving as the session grew, was demoted to `not verifiable`
     under rule 3, and the block then printed "the reading raised no
     departure" about one the payload still held. */
  const entries = all.slice(-NEXT_COCKPIT_WORK_ROWS);
  if(entries.length){
    return {entries, all, state: "read", shown: entries.length, total: all.length};
  }
  if(entry.error) return {entries, all, state: "error"};
  /* Whether the scan that produces these facts reached this session. The
     answer is `sources.work.omitted`, a list of the sessions
     `_analysis_context_sessions` bounded out at MAX_PROJECT_OBSERVERS, and
     naming the session is what makes the state a fact rather than an
     inference from two counts.

     It is not `command_attention_coverage`, which this block read first: that
     is a different bounded sweep, over active sessions' final output, capped
     at 64 rather than 3. A session omitted from the scan that publishes the
     facts is almost never omitted from that one, so the state this exists to
     distinguish resolved to "empty" for exactly the sessions it was written
     for. */
  const omittedRows = entry.data.sources && entry.data.sources.work &&
    entry.data.sources.work.omitted;
  const omittedHere = Array.isArray(omittedRows) && omittedRows.some(row =>
    row && sessKey(row) === key);
  if(omittedHere){
    return {entries, all, state: "partial", scanned: nextNumber(
      entry.data.sources.observer && entry.data.sources.observer.live),
      omitted: omittedRows.length};
  }
  return {entries, all, state: "empty"};
}

function nextCockpitWorkAbsence(source){
  if(source.state === "unread"){
    return "The observed record for this session has not been read yet.";
  }
  if(source.state === "error"){
    return "The observed record could not be read, so nothing here says what this session " +
      "has been doing.";
  }
  if(source.state === "partial"){
    const scanned = source.scanned == null ? "the most recently active" : `${source.scanned}`;
    return `This session was outside the observed-record scan, which covered ${scanned} ` +
      `of the sessions in this project and left ${source.omitted} out. Its record is ` +
      "unread rather than empty.";
  }
  return "No entry in the observed record names this session.";
}

function nextCockpitWorkEntries(session, semantic){
  const key = sessKey(session);
  return (semantic && Array.isArray(semantic.facts) ? semantic.facts : [])
    .filter(fact => fact && nextCockpitFactSessionKey(fact) === key)
    .sort((left, right) => Number(left.at || 0) - Number(right.at || 0))
    .map(fact => {
      const evidence = fact.evidence && typeof fact.evidence === "object" ? fact.evidence : {};
      /* `actor_claim` is the string `project_context` computes to say who
         derived a snapshot, and it was dropped here, so a model's paraphrase
         of the goal rendered in the same mono register as a line a harness
         published. Making that field honest was the first fix on this branch;
         throwing it away at the last step undid it. */
      return {
        id: String(fact.fact_id || ""),
        type: String(fact.type || ""),
        by: String(fact.by || ""),
        summary: String(fact.summary || "No summary published"),
        at: fact.at,
        actorClaim: String(fact.actor_claim || ""),
        modelDerived: String(fact.actor_claim || "").startsWith("model-derived"),
        source: [evidence.source, evidence.confidence].map(value =>
          String(value == null ? "" : value).trim()).filter(Boolean).join(" · "),
      };
    });
}

/* How many entries the block draws. Nothing upstream caps the semantic facts:
   measured on a real board, one project held 26 and one eleven-hour session
   named 7 of them, and a session ten times as long would draw ten times as
   many. This is a readability bound rather than a measurement, which is
   exactly why the count it hid is stated under the rows: a silent cap reads
   as the whole record. */
const NEXT_COCKPIT_WORK_ROWS = 20;

function nextCockpitWorkEvidence(session, source){
  const entries = source.entries;
  const rows = entries.map(entry => {
    const at = nextDurationSince(entry.at);
    /* A model's paraphrase takes the third treatment, not the mono of a
       string a source published. It is the same rule the reading block
       follows, and the reason is the same: the reader must be able to tell
       the record from an account of it. */
    const summary = entry.modelDerived
      ? `<em class="next-cockpit-work-derived">${esc(entry.summary)}</em>`
      : `<span class="next-cockpit-work-summary">${esc(entry.summary)}</span>`;
    return `<div class="next-cockpit-work-row" data-next-cockpit-work-type="${esc(entry.type)}">` +
      `<span class="next-cockpit-work-type">${esc(entry.type)}</span>${summary}` +
      `<span class="next-cockpit-work-source">${esc(entry.source || "Source not published")}` +
      /* Only where it says something the source line does not. On most fact
         types `actor_claim` IS the evidence source, and appending it printed
         "timestamped non-meta user-role record · exact · timestamped non-meta
         user-role record". Caught by walking the board, not by the suite. */
      `${entry.actorClaim && !entry.source.includes(entry.actorClaim)
        ? ` · ${esc(entry.actorClaim)}` : ""}</span>` +
      `<span class="next-cockpit-work-at">${esc(at == null ? "time not published" : `${at} ago`)}` +
      '</span></div>';
  }).join("");
  return '<section class="next-cockpit-work" data-next-cockpit-work>' +
    '<header><h2>OBSERVED RECORD</h2></header>' +
    (rows || '<p class="next-cockpit-work-absent">' +
      `${esc(nextCockpitWorkAbsence(source))}</p>`) +
    (entries.length ? `<p class="next-cockpit-work-mix">${esc(nextCockpitWorkMix(entries))}</p>`
      : "") +
    (source.shown != null && source.shown < source.total
      ? `<p class="next-cockpit-work-dropped">Showing the ${source.shown} most recent of ` +
        `${source.total} observed entries.</p>` : "") +
    '<p class="next-cockpit-work-limit">' +
    `${esc(nextCockpitWorkEvidenceLimit(String(session.harness || "")))}</p></section>`;
}

/* What the rows actually are, counted from the rows themselves.

   The block was headed WORK EVIDENCE, and on Claude and Codex every entry is
   a `user_message`: `project_context._SEMANTIC_FACT_TYPES` maps `steer` to
   that type and a session with no workflow promotes nothing else. So a reader
   comparing their words against "work evidence" was reading their own
   sentences back on both sides of the comparison. The heading now names the
   record rather than the work, and this line says what is in it. */
function nextCockpitWorkMix(entries){
  /* One pass and four exclusive buckets, so the remainder cannot be reached
     by subtracting overlapping filters.

     `observer_snapshot` is the bucket this line was missing. Its summary is
     the session's goal restated, and `_OBSERVER_ACTOR_CLAIMS` publishes three
     derivations for it: model, deterministic, and one never recorded. Only
     the first sets `modelDerived`, so the other two fell into the remainder
     and a paraphrase of the goal was counted as "observed of what it did" —
     the exact conflation the heading above was rewritten to stop.

     Directions use `nextReadingPersonAuthored` rather than a second opinion
     about who wrote a row, because rule 7 already owns that question and two
     answers to it on one page is how they drift. */
  let directions = 0;
  let derived = 0;
  let summaries = 0;
  let work = 0;
  for(const entry of entries){
    if(nextReadingPersonAuthored(entry)) directions += 1;
    else if(entry.modelDerived) derived += 1;
    else if(String(entry.type || "") === "observer_snapshot") summaries += 1;
    else work += 1;
  }
  const parts = [`${entries.length} ${entries.length === 1 ? "entry" : "entries"}`];
  if(directions) parts.push(`${directions} ${directions === 1 ? "direction" : "directions"} you gave`);
  if(derived) parts.push(`${derived} model-derived`);
  if(summaries){
    parts.push(`${summaries} derived ${summaries === 1 ? "summary" : "summaries"} of this session`);
  }
  parts.push(`${work} observed of what it did`);
  return `${parts.join(" · ")}.`;
}

function nextCockpitObserverModel(group){
  const focus = nextCockpitFocusedSession(group);
  nextCockpitLoadContext(group, focus);
  for(const scope of [focus, null]){
    const entry = nextCockpitContexts.get(nextCockpitContextKey(group, scope));
    const model = entry && entry.data && entry.data.observer_model;
    if(model) return model;
  }
  return null;
}

/* The shape contract, as a producer rather than a checklist.
   [DEC-17](docs/design-reading-a-session.md#dec-17-the-shape-contract)

   A model was permitted to read a session against the reader's typed words on
   explicit request, with nothing said about what makes the result sound
   ([DEC-15](docs/design-reading-a-session.md#dec-15-the-floor-and-the-overlay)).
   The ruling above closed that: the rubric named there gates AUTOMATIC
   evaluation only, and a reader-requested reading is held to seven rules
   instead. They remove failure classes rather than measuring a rate, which is
   why they can stand where no rate has been measured.

   They are built into `nextCockpitReadingCriterion` rather than asserted after
   it, so the three worst outputs are unrenderable rather than rare: the word
   "met", a departure citing nothing, and a deliverable claim on a harness that
   publishes no work evidence. Every demotion here lands on `not verifiable
   from available evidence`, which the ruling names as the safe direction.

   Nothing produces a reading yet. The control below is disabled until the
   abstention check has run, which is the condition on enabling rather than
   on building, and the storage that will carry one is DRC-4512's. */
const NEXT_READING_DEPARTURE = "departure";
const NEXT_READING_CONSISTENT = "consistent with the evidence read";
const NEXT_READING_UNVERIFIABLE = "not verifiable from available evidence";
// Rule 1, as data. A result reaches the page only by being one of these.
const NEXT_READING_RESULTS = [
  NEXT_READING_DEPARTURE, NEXT_READING_CONSISTENT, NEXT_READING_UNVERIFIABLE,
];
// Rule 6: two constraints, each naming itself, never blended. Keyed on
// identity so rule 7 needs no reading of the clause.
const NEXT_READING_CONSTRAINTS = [
  ["goal", "TYPED GOAL"],
  ["output", "EXPECTED OUTPUT"],
];
const NEXT_READING_ASSISTANT_ONLY =
  "Every entry cited here was written by the agent, which is not evidence " +
  "that the requested output exists.";
const NEXT_READING_UNCITED =
  "Nothing resolvable was cited, so there is no entry to read this against.";
const NEXT_READING_MALFORMED =
  "The reading did not return a usable result for this constraint.";

/* Who wrote an evidence entry. A closed set on the person side, because the
   asymmetry in rule 7 turns on it and a truthy check would count every
   unfamiliar type as a person's words. A gate decision is a person's only
   where the source records one. */
function nextReadingPersonAuthored(entry){
  const type = String(entry && entry.type || "");
  if(type === "user_message") return true;
  return type === "gate_decision" && String(entry && entry.by || "").startsWith("person:");
}

/* Rule 3: a citation resolves only when it names an entry the page holds AND
   that entry carries both a type and a source. A citation to nothing is the
   shape an invented departure takes. */
function nextReadingCitations(raw, entries){
  const byId = new Map((entries || []).map(entry => [String(entry && entry.id || ""), entry]));
  const cited = Array.isArray(raw && raw.cites) ? raw.cites : [];
  return cited.map(id => byId.get(String(id))).filter(entry =>
    entry && String(entry.type || "").trim() && String(entry.source || "").trim());
}

function nextCockpitReadingCriterion(key, label, clause, raw, entries, limit){
  const citations = nextReadingCitations(raw, entries);
  const declared = raw && typeof raw === "object" ? String(raw.result || "") : "";
  let result = NEXT_READING_RESULTS.includes(declared) ? declared : NEXT_READING_UNVERIFIABLE;
  // Rule 2, and it is the reason the default above is not `consistent`: a
  // producer that returned nothing has said nothing, and silence is not a pass.
  let why = result === declared ? "" : NEXT_READING_MALFORMED;
  if(result !== NEXT_READING_UNVERIFIABLE && !citations.length){
    // Rule 3 names the departure arm. A `consistent` resting on nothing is the
    // same failure wearing the safer-looking face, so it is demoted too.
    result = NEXT_READING_UNVERIFIABLE;
    why = NEXT_READING_UNCITED;
  }
  if(result !== NEXT_READING_UNVERIFIABLE && limit){
    /* Rule 5, and the limit reaches this row only because the caller decided
       it bears on this constraint. What `_work_evidence` would have supplied
       is deliverables, so its absence limits Expected Output and says nothing
       about Goal: a transcript is exactly the evidence a change of direction
       leaves, and it was read.

       Rule 5 names `consistent`. A departure is demoted too, which is
       stricter than the letter and is the direction the ruling calls safe: a
       departure from a requested output, claimed where the thing itself was
       never looked at, is the deliverable claim rule 7 exists to prevent. */
    result = NEXT_READING_UNVERIFIABLE;
    // Not `why = limit`: the limit has its own row below, and setting both
    // printed the identical sentence twice, the second time prefixed
    // `limit ·`.
    why = "";
  }
  const fromPerson = citations.filter(nextReadingPersonAuthored);
  if(key === "output" && result !== NEXT_READING_UNVERIFIABLE && !fromPerson.length){
    // Rule 7, the Expected Output half. Self-report is not evidence of a
    // deliverable, in either direction.
    result = NEXT_READING_UNVERIFIABLE;
    why = NEXT_READING_ASSISTANT_ONLY;
  }
  // Rule 7, the Goal half. A departure on the agent's own narration stands,
  // because a stated change of direction is what that evidence is good for,
  // and a `consistent` resting only on it says so rather than reading as
  // corroborated.
  const narration = result === NEXT_READING_CONSISTENT && !fromPerson.length
    ? "Rests on the agent's own account alone." : "";
  return {
    key, label,
    clause: clause || "the words of the revision this reading read are not retained",
    clauseKnown: Boolean(clause),
    result,
    detail: String(raw && raw.detail || ""),
    why, narration, limit: limit || "",
    // Mutually exclusive with `limit`, and never both blank: a row states its
    // evidence or states why it has none.
    evidence: limit ? [] : citations.map(entry =>
      `${entry.type} · ${entry.source}`),
  };
}

/* The reading, shaped. `raw` is whatever a producer returned; `annotation` is
   what the reader typed; `entries` are the work-evidence rows already on the
   page, so a citation resolves against the same list the reader can see. */
/* The words the reading was read against.

   The producer carries them, because only it knows what the revision it read
   actually said. The current annotation is a legitimate fallback only while
   the reading read the current revision; once a later revision exists,
   showing today's text as the clause a past reading judged is the historical
   reading claiming to describe the current request, which is precisely what
   the amber line beside it exists to deny. */
function nextCockpitReadingClause(key, row, annotation, historical){
  const carried = String(row && row.clause || "").trim();
  if(carried) return carried;
  if(historical) return "";
  return String(annotation && annotation[key] || "").trim();
}

function nextCockpitReadingShape(raw, annotation, entries, limit){
  const source = raw && typeof raw === "object" ? raw : {};
  const rows = source.criteria && typeof source.criteria === "object" ? source.criteria : {};
  const revisionRead = nextNumber(source.revision_read);
  const current = nextNumber(annotation && annotation.revision);
  const historical = revisionRead != null && current != null && revisionRead !== current;
  /* Which constraints the READING read, not which are typed now. Filtering on
     the current annotation meant a field cleared since the reading dropped
     its row and its departure with it, after which the departures block
     rendered "The reading raised no departure from the revision it read" —
     a sentence about a revision whose departure had just been deleted. */
  const criteria = NEXT_READING_CONSTRAINTS
    .filter(([key]) => rows[key] || String(annotation && annotation[key] || "").trim())
    .map(([key, label]) => nextCockpitReadingCriterion(
      key, label, nextCockpitReadingClause(key, rows[key], annotation, historical),
      rows[key], entries, key === "output" ? limit : ""));
  return {
    criteria,
    departures: criteria.filter(row => row.result === NEXT_READING_DEPARTURE),
    revisionRead,
    stamp: String(source.stamp || ""),
    cutoff: String(source.cutoff || ""),
  };
}

/* The reading block, and its three states are all first class. A model
   reading is neither a published string nor the board stating a fact, so it
   takes the third treatment: italic, secondary ink, a dotted rule, and no
   colour under any result. Accent on a reading would read as "met", which is
   a claim about the reader's intent from partial evidence.

   One stamp, in the header, rather than one per block. The design's notes ask
   for one on every block and its markup carries one; a stamp repeated beside
   each criterion says the same three facts three times and pushes the reading
   itself further down a tab that is already the last thing on the page. */
function nextCockpitReadingStates(annotation, model){
  if(!String(annotation && annotation.goal || "").trim() &&
      !String(annotation && annotation.output || "").trim()){
    return "Nothing has been typed for this session, so there is nothing to read it against.";
  }
  if(!model) return "Observer model availability has not been read, so no reading can be offered.";
  if(model.enabled !== true){
    return "Observer model is disabled for this run, so no reading can be offered. " +
      "Start with --observer-model to allow one; --no-observer-model refuses it.";
  }
  return "";
}

/* Mono is for words a person typed. When the revision a reading read is no
   longer retained, this cell holds the board saying so instead, and rendering
   that into the quotation's own register made the explanation look like the
   quotation it stands in for. The stylesheet states the rule two lines above
   the class it applies to; `clauseKnown` was computed for this and never
   read. */
function nextCockpitReadingClauseCell(row){
  return `<span class="next-cockpit-reading-clause${row.clauseKnown ? "" : "-absent"}">` +
    `${esc(row.clause)}</span>`;
}

function nextCockpitReadingCriterionRow(row){
  const tail = row.limit
    ? `<span class="next-cockpit-reading-limit">limit · ${esc(row.limit)}</span>`
    : row.evidence.map(line =>
      `<span class="next-cockpit-reading-evidence">${esc(line)}</span>`).join("");
  return '<div class="next-cockpit-reading-row">' +
    `<span class="next-cockpit-reading-name">${esc(row.label)}</span>` +
    nextCockpitReadingClauseCell(row) +
    `<em class="next-cockpit-reading-result">${esc(row.result)}</em>` +
    (row.detail ? `<em class="next-cockpit-reading-detail">${esc(row.detail)}</em>` : "") +
    (row.why ? `<span class="next-cockpit-reading-why">${esc(row.why)}</span>` : "") +
    (row.narration ? `<span class="next-cockpit-reading-why">${esc(row.narration)}</span>` : "") +
    tail + '</div>';
}

/* One sentence, two places. Note 4 of the design records that the steer box
   and this panel both say steering is manual in different words; this is the
   half that references the other rather than restating the ruling
   ([DEC-16](docs/design-reading-a-session.md#dec-16-cargento-does-not-write-into-a-session)). */
const NEXT_COCKPIT_STEER_BY_HAND = "Raised to you and nowhere else. Cargento does not write " +
  "into a session, so steering is by hand; the steer box in Console states the same rule " +
  "about notes you write there.";

function nextCockpitDepartures(shape){
  /* Rendered whether or not a reading exists. It carried the ruling's
     sentence that steering is manual and the fact that nothing was raised, and
     both were reachable only through a reading nothing produces, so journey
     step 4 had no surface at all. Saying "no reading has been made, so
     nothing has been raised" needs no model. */
  if(!shape){
    return '<section class="next-cockpit-departures"><header>' +
      '<h2>DEPARTURES RAISED TO YOU</h2></header>' +
      '<p class="next-cockpit-reading-why">No reading has been made, so nothing has been ' +
      'raised. Nothing watches for a departure on its own.</p>' +
      `<p class="next-cockpit-reading-why">${NEXT_COCKPIT_STEER_BY_HAND}</p></section>`;
  }
  const rows = shape.departures.map(row =>
    '<div class="next-cockpit-departure">' +
    `<span class="next-cockpit-reading-name">${esc(row.label)}</span>` +
    nextCockpitReadingClauseCell(row) +
    `<em class="next-cockpit-reading-detail">${esc(row.detail || row.result)}</em>` +
    row.evidence.map(line =>
      `<span class="next-cockpit-reading-evidence">${esc(line)}</span>`).join("") +
    '</div>').join("");
  /* Once, for the block. It was inside each departure row, which said one
     fact as many times as there were departures and never once when there
     were none — and a reading that raised nothing is exactly the one whose
     cutoff a reader needs, because "nothing was raised" is worth only as much
     as the evidence it was raised against. */
  const cutoff = shape.cutoff
    ? `<p class="next-cockpit-reading-why">${esc(shape.cutoff)}</p>` : "";
  return '<section class="next-cockpit-departures"><header>' +
    '<h2>DEPARTURES RAISED TO YOU</h2></header>' +
    (rows || '<p class="next-cockpit-reading-why">The reading raised no departure from the ' +
      'revision it read.</p>') + cutoff +
    `<p class="next-cockpit-reading-why">${NEXT_COCKPIT_STEER_BY_HAND}</p></section>`;
}

function nextCockpitReading(session, annotation, entries, model, observed){
  const header = '<section class="next-cockpit-reading"><header><h2>READING</h2>';
  const limit = String(session.harness || "") === "pi"
    ? "" : nextCockpitWorkEvidenceLimit(String(session.harness || ""));
  const raw = annotation && annotation.assessment;
  /* A reading already made renders whatever the model's state is now. The
     three states below are about offering a NEW one, and DEC-15b's whole
     point is that a retained reading outlives the run that produced it. */
  if(!raw){
    const reason = nextCockpitReadingStates(annotation, model);
    if(reason){
      return `${header}</header><p class="next-cockpit-reading-why">${esc(reason)}</p>` +
        '</section>' + nextCockpitDepartures(null);
    }
    /* The offer. `Ask for a reading` reads the abstention check's recorded
       result rather than a constant, which is the condition on enabling:
       the reading is built now, the control waits on a check that needs
       recorded sessions across two harnesses and a second person's
       expectations marked in advance.

       A recorded pass implies a producer, because the check cannot be run
       without one to run it on. It does not imply this button is wired to
       that producer, and an earlier version of this comment said it did.
       `ReadingControlIsWiredTest` holds the difference: a rendered action
       with no dispatch arm may not become reachable, and no arm exists for
       this one yet. */
    const passed = nextData && nextData.reading_check === "passed";
    return `${header}</header>` +
      '<p class="next-cockpit-reading-why">A reading is a model’s account of the evidence ' +
      'on this page: the observed record above and the words you typed, and nothing else. It ' +
      'does not read a diff, a file, a test or a deliverable, and it is never a verification ' +
      'that the work was done.</p>' +
      '<button type="button" data-next-cockpit-action="reading-ask" ' +
      `data-next-focus="reading:${esc(sessKey(session))}"${passed ? "" : " disabled"}>` +
      'Ask for a reading</button>' +
      (passed ? "" : '<p class="next-cockpit-reading-why">The abstention check this ruling ' +
        'requires has not been run, so a reading cannot be asked for yet. The evidence above ' +
        'stays readable without one.</p>') + '</section>' + nextCockpitDepartures(null);
  }
  const shape = nextCockpitReadingShape(raw, annotation, entries, limit);
  /* Journey step 3: a reading offered before the session ended says so. The
     end evidence is the two-axis derivation next door, so the scope sentence
     and the HOW IT LANDED cards cannot disagree about whether it ended. */
  /* On the session END, not on `endKnown`, which a turn stop sets too. The
     card next door renders "A turn stop was observed; no session end was" on
     the same evidence, so keying the qualifier on `endKnown` made the two
     halves of one tab disagree about whether the session had ended. */
  const provisional = observed && observed.landing &&
    observed.landing.endKind !== "session-end"
    ? '<p class="next-cockpit-reading-why">This covers only the work so far. ' +
      `${esc(observed.landing.endText)}, so nothing here is a reading of how it ended.</p>`
    : "";
  const current = nextNumber(annotation && annotation.revision);
  /* The one warm ink the design allows near a reading, and it is not part of
     one: which revision was read is an observation about revisions. */
  const stale = shape.revisionRead != null && current != null && shape.revisionRead !== current
    ? `<p class="next-cockpit-reading-stale">This reading read revision ${shape.revisionRead}. ` +
      `Revision ${current} is current, so it does not describe what you are asking for now.</p>`
    : "";
  return header +
    (shape.stamp ? `<span class="next-cockpit-reading-stamp">${esc(shape.stamp)}</span>` : "") +
    '</header>' + stale + provisional +
    shape.criteria.map(nextCockpitReadingCriterionRow).join("") + '</section>' +
    nextCockpitDepartures(shape);
}

/* HOW IT LANDED: the two axes `nextObservedLanding` derives, drawn where the
   reader is comparing the work to what they asked for.

   The derivation shipped with no consumer, and all three reviewing harnesses
   found the same hole: journey step 3 turns on whether Cargento has evidence
   the session ended, and a reader in this tab could not see whether it did.
   Two cards and never one verdict, because what ended and who says the work
   finished are different questions with different answers. */
function nextCockpitLanded(observed){
  if(!observed || !observed.landing){
    return '<section class="next-cockpit-landed"><header><h2>HOW IT LANDED</h2></header>' +
      '<p class="next-cockpit-reading-why">This session was not in the observed payload, ' +
      'so nothing here says how it ended.</p></section>';
  }
  const landing = observed.landing;
  const card = (title, text, known, note) =>
    '<div class="next-cockpit-landed-card">' +
    `<span class="next-cockpit-landed-label">${title}</span>` +
    `<span class="next-cockpit-landed-value${known ? "" : " next-cockpit-landed-value--absent"}">` +
    `${esc(text)}</span>` +
    (note ? `<span class="next-cockpit-landed-note">${esc(note)}</span>` : "") + '</div>';
  return '<section class="next-cockpit-landed"><header><h2>HOW IT LANDED</h2>' +
    '<span class="next-cockpit-landed-axes">two axes, read separately</span></header>' +
    '<div class="next-cockpit-landed-cards">' +
    card("END EVIDENCE", landing.endText, landing.endKnown, "") +
    card("WHO CLAIMS IT FINISHED", landing.claimText, landing.claimKnown,
      landing.independentText) +
    '</div><p class="next-cockpit-reading-why">Neither card implies the other.</p></section>';
}

/* DRC-4509's fourth criterion and DRC-4511's third: where re-entry is
   supported, expose the route and state its limits. The route was already
   reachable and the limits were not, which is the half the pull request
   conceded rather than half-built.

   A link rather than a fifth copy of the two controls. `next-session.js`
   renders both unconditionally on the session view and `nextSessionHeldLink`
   links that view to this tab; this is the return leg, and the criterion
   verifies with a navigation check, which is what a link is.

   Two limits, not one, and split by cause. A harness outside
   `NEXT_RESUME_COMMANDS` has no re-entry command and never will; one inside it
   with no usable id has none THIS RUN. `nextResumeCommand` collapses both to
   "", which is the same conflation journey-review finding C fixed on the
   observed record. The raise's limit is the standing one recorded beside
   `nextSessionRaiseControl`, said here because a single session is the whole
   subject of this tab and rendering nothing reads as "no limit" rather than as
   "not this session". */
function nextCockpitHeldReEntry(session){
  if(!session) return "";
  const harness = String(session.harness || "");
  const project = String(session.project == null ? "" : session.project);
  const raise = !nextFocusCapability()
    ? NEXT_FOCUS_OFF_LINE
    : session.focusable === true
      ? "Its terminal can be raised, and that control is offered while the session is waiting " +
        "on you. A raise switches what the terminal displays; its window may still be behind " +
        "others."
      : "No terminal was reported for this session, so it cannot be raised. That is the " +
        "ordinary answer outside tmux, for a session older than this server run, and on " +
        "Linux and Windows.";
  const label = nextHarnessLabels().get(harness) || nextCockpitHumanLabel(harness);
  const resume = !NEXT_RESUME_COMMANDS.has(harness)
    ? `${label} publishes no re-entry command, so there is none to copy.`
    : nextResumeCommand(session)
      ? "A re-entry command for it is on the session page."
      : "This session published no usable id this run, so there is no re-entry command to copy.";
  /* `data-next-focus` because keyboard focus here is a managed lane
     ([reader state](docs/design-reader-state.md#the-inventory)); an
     anchor without it loses focus on every redraw. */
  const link = project
    ? `<a href="${esc(nextFragmentForRoute({view: "session", project, harness,
        session: String(session.sid == null ? "" : session.sid)}))}" ` +
      'data-next-focus="cockpit-held-reentry">Open this session</a> to re-enter it. '
    : "";
  return `<p class="next-cockpit-held-reentry">${link}${esc(raise)} ${esc(resume)}</p>`;
}

function nextCockpitHeldTo(group, observation){
  const session = nextCockpitFocusedSession(group);
  if(!session){
    return '<section class="next-cockpit-held"><header><h2>WHAT YOU ASKED FOR</h2></header>' +
      '<p class="next-cockpit-held-absent">No session is selected, so there is nobody ' +
      'whose words these would be.</p></section>';
  }
  /* No field at all when the store is off, which is what `--no-annotations`
     promises. A box whose every save answers 503 is worse than none, and the
     reason is on screen rather than left to the reader. */
  if(!(nextData && nextData.annotate === true)){
    return '<section class="next-cockpit-held"><header><h2>WHAT YOU ASKED FOR</h2></header>' +
      '<p class="next-cockpit-held-absent">Annotations are off for this run. Start without ' +
      '--no-annotations to type a goal and an expected output here.</p></section>';
  }
  const annotation = nextCockpitAnnotation(session);
  const workSource = nextCockpitWorkSource(group, session);
  // The full set, not the displayed window: a citation resolves against what
  // the payload holds, and the window is a readability bound on the rows.
  const entries = workSource.all || workSource.entries;
  /* The design's order inside this tab: what you asked for, then the reading
     of it, then the departures it raised. Intent first, then a reading of the
     intent, so nothing above the reading is a model's words. */
  const observed = nextCockpitFocusedObserved(group, nextCockpitObservedProject(group));
  /* The design's order inside this tab: what you asked for, then the reading
     of it, then the departures it raised, then how it landed. */
  const evidence = nextCockpitWorkEvidence(session, workSource) +
    nextCockpitReading(session, annotation, entries, nextCockpitObserverModel(group), observed) +
    nextCockpitLanded(observed);
  const cap = nextCockpitHeldCap();
  const revision = nextProjectRevisionLine(annotation) || "No revision saved yet";
  const binding = annotation && annotation.binding_why && (annotation.goal || annotation.output)
    ? `<p class="next-cockpit-held-absent">${esc(annotation.binding_why)}</p>` : "";
  /* An ended session may still be annotated, and the store will keep it. What
     is unsettled is whether anything should then read it, so the line says
     that rather than disabling a control over an open question. */
  const ended = nextSessionEndedAt(session) != null
    ? '<p class="next-cockpit-held-absent">This session has ended. Annotating a finished ' +
      'session is an open proposal: your words are kept, and nothing is promised to read ' +
      'them.</p>' : "";
  /* Named, because the reader has to know whose words these are. Two sessions
     that publish one title are indistinguishable in the scope rail, and this
     block said nothing at all about which of them it was binding to. The
     harness and the session id are what the store keys on, so they are what
     is shown. */
  return '<section class="next-cockpit-held"><header><h2>WHAT YOU ASKED FOR</h2>' +
    `<span class="next-cockpit-held-bound">${esc(sessKey(session))}</span>` +
    `<span class="next-cockpit-held-revision">${esc(revision)}</span></header>` +
    '<div class="next-cockpit-held-fields">' +
    NEXT_COCKPIT_HELD_FIELDS.map(spec =>
      nextCockpitHeldField(session, annotation, spec, cap)).join("") + '</div>' +
    binding + ended + nextCockpitHeldReEntry(session) + '</section>' + evidence;
}

async function nextCockpitHeldSave(session, kind){
  const key = nextCockpitHeldKey(session, kind);
  // Only the field that changed. `null` is "leave this one alone" at the
  // endpoint, and "" is "clear it": sending both every time would let a stale
  // draft of one field overwrite a save of the other.
  const body = {harness: session.harness, sid: session.sid, goal: null, output: null};
  const sent = nextCockpitHeldDrafts.has(key) ? nextCockpitHeldDrafts.get(key) : null;
  body[kind] = sent;
  try{
    const response = await fetch("/api/annotate", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    });
    if(!response || !response.ok) throw new Error(`HTTP ${response && response.status}`);
    const saved = await response.json();
    // `ok`, which is what `/api/annotate` answers with. `persisted` beside it
    // is whether the write reached disk, and a false there is not a failed
    // save: the words are held for this run and the store says so itself.
    if(!saved || saved.ok !== true) throw new Error("save not confirmed");
    /* Only when the box still holds what was sent. A reader who kept typing
       while the request was open has a newer instruction in there, and
       dropping the draft would revert the field to the older text they just
       watched leave. */
    /* And only when the store actually took them. `annotations.annotate`
       sets `state.annotations` before it writes, so `persisted:false` leaves
       the revision in this process alone — and every collection calls
       `annotation_store.refresh`, which reloads the file and drops it. The
       next line starts one. Dropping the draft here therefore destroyed the
       only remaining copy of what someone typed, while the cue beside it
       warned the words would be gone at a refresh that had already run. */
    const persisted = saved.persisted === true;
    if(persisted && nextCockpitHeldDrafts.get(key) === sent) nextCockpitHeldDrafts.delete(key);
    nextCockpitHeldMark(key, persisted ? "saved" : "unpersisted");
    await refreshNext();
  }catch(_error){
    // The draft stays. Losing what someone typed to report a failure is the
    // one outcome worse than the failure.
    nextCockpitHeldMark(key, "error");
    renderNext({named: key});
  }
}

function nextCockpitRecoveryMemoCell(group, focus, briefing){
  if(focus) return "";
  const outcomeKey = nextCockpitMemoKey(group, focus, "outcome");
  const focusKey = nextCockpitMemoKey(group, focus, "focus");
  if(briefing.outcome === "Not set" && briefing.currentFocus === "Not set" &&
      ![outcomeKey, focusKey].includes(nextCockpitMemoEditingKey)){
    if(briefing.task.known && briefing.coverage.state === "complete") return "";
    return '<div class="next-cockpit-recovery-memos" data-next-cockpit-memo-empty>' +
      `<button type="button" data-next-cockpit-action="memo-edit" data-arg="${esc(outcomeKey)}">` +
      '+ Add human context · this browser</button></div>';
  }
  const field = (kind, label, placeholder, value) => {
    const key = nextCockpitMemoKey(group, focus, kind);
    const state = nextCockpitMemoStates.get(key);
    const editing = nextCockpitMemoEditingKey === key;
    if(editing){
      const cue = state === "error" ? "Browser storage unavailable" :
        state === "saved" ? "Saved in this browser" : "Autosaves in this browser";
      return `<label data-next-cockpit-memo-field="${kind}"><span>${label}</span>` +
        `<textarea maxlength="${NEXT_COCKPIT_MEMO_LIMIT}" data-next-cockpit-memo-input ` +
        `data-next-cockpit-memo-key="${esc(key)}" data-next-cockpit-memo-kind="${kind}" ` +
        `data-next-focus="memo:${esc(key)}" ` +
        `placeholder="${esc(placeholder)}">${esc(value === "Not set" ? "" : value)}</textarea>` +
        `<small data-next-cockpit-memo-cue="${kind}">${cue}</small>` +
        '<button type="button" data-next-cockpit-action="memo-done">Done</button></label>';
    }
    return `<div data-next-cockpit-memo-field="${kind}"><span>${label}</span>` +
      `<strong>${esc(value)}</strong><button type="button" data-next-cockpit-action="memo-edit" ` +
      `data-arg="${esc(key)}" aria-label="Edit ${label}">Edit</button></div>`;
  };
  return '<div class="next-cockpit-recovery-memos"><span>OPTIONAL HUMAN NOTE · THIS BROWSER</span>' +
    field("outcome", "OUTCOME", "What result should this scope achieve?", briefing.outcome) +
    field("focus", "FOCUS", "What are you concentrating on now?", briefing.currentFocus) + '</div>';
}

function nextCockpitRecoveryExecution(group, briefing, compactIdle = false){
  const labels = nextHarnessLabels();
  const children = [...briefing.children.active];
  if(briefing.children.latestReturn) children.push(briefing.children.latestReturn);
  if(compactIdle) return '<strong>No execution observed · Captain not needed</strong>';
  const working = new Set(nextCockpitWorkingSessions(group).map(sessKey));
  const sessions = group.sessions.filter(session => working.has(sessKey(session)) ||
    children.some(child => child.sourceSession === sessKey(session)));
  if(!sessions.length) return '<strong>No execution observed</strong>';
  const childEvidence = child =>
    (child.assignment === "assignment unavailable" || child.result === "result unavailable"
      ? `<p class="next-cockpit-evidence-missing">${esc([
        child.assignment === "assignment unavailable" ? child.assignment : "",
        child.result === "result unavailable" ? child.result : "",
      ].filter(Boolean).join(" · "))}</p>` : "") +
    `<details${nextCockpitDisclosureAttr("child:" + child.sourceSession + ":" + child.worker + ":" + child.lifecycle)}>` +
    '<summary>Evidence · child handoff</summary>' +
    `<small>${child.assignment === "assignment unavailable" ? esc(child.assignment) : nextCockpitSourceText(child.assignment)}` +
    (child.result ? " · " + (child.result === "result unavailable" ? esc(child.result) : nextCockpitSourceText(child.result)) : "") +
    " · " + (/unavailable/i.test(child.assignmentSource) ? esc("source " + child.assignmentSource) :
      nextCockpitSourceText("source " + child.assignmentSource)) + " · " +
    nextCockpitSourceText("source session " + child.sourceSession) +
    (child.lifecycle === "returned" ? " · " + nextCockpitSourceText(`event ${child.at || "unavailable"}`) +
      " · " + nextCockpitSourceText("age " + (child.age ? `${child.age} ago` : "unavailable")) : "") +
    '</small>' +
    '</details>';
  return sessions.map(session => {
    const key = sessKey(session);
    const harness = labels.get(String(session.harness || "")) || String(session.harness || "Session");
    const state = session.state === "needs_input" ? "needs input" : String(session.state || "unknown");
    const rows = children.filter(child => child.sourceSession === key).map(child => {
      const returned = child.lifecycle === "returned" && child.ageSec >= NEXT_PROJECT_STALLED_SEC
        ? ` · stale ${child.age || "age unavailable"}` : "";
      const handoff = child.lifecycle === "returned" && child.handoffUnavailable
        ? " · handoff unavailable" : "";
      return '<div class="next-cockpit-child-row">' +
        `<strong>${esc(child.worker + " · " + child.lifecycle + handoff + returned)}</strong>` +
        `${childEvidence(child)}</div>`;
    }).join("");
    return '<div class="next-cockpit-execution-root">' +
      `<strong>${esc(harness + " · " + state)}</strong>${rows}</div>`;
  }).join("");
}

function nextCockpitWaitingCommand(project){
  const session = project && project.needs[0];
  if(!session) return "";
  const route = nextFragmentForRoute({view:"session",project:project.key,
    harness:session.harness,session:session.sid});
  return '<div class="next-cockpit-waiting" data-next-cockpit-waiting>' +
    '<span>WAITING ON YOU</span>' +
    `<a href="${esc(route)}" data-next-route="${esc(route.slice(3))}">` +
    nextProjectValue(session.titleText, session.titleKnown) + '</a>' +
    nextProjectValue(session.waitedText, session.waitedKnown) +
    (session.askKnown ? `<p class="next-cockpit-source">${esc(session.askText)}</p>` : "") +
    '<div class="next-rail-wait-controls">' + nextSessionRaiseControl(session) +
    (nextSessionResumeControl(session) || nextSessionCopyControl(session)) + '</div></div>';
}

function nextCockpitRecoveryStrip(group, observation, commandAttention, project = nextCockpitObservedProject(group)){
  const focus = nextCockpitFocusedSession(group);
  const briefing = nextCockpitRecoveryBriefing(group, focus, observation, commandAttention);
  const attention = commandAttention || nextCockpitCommandAttention(group, observation);
  const captain = attention.filter(item => item && item.owner === "CAPTAIN");
  const system = attention.filter(item => item && item.owner === "FO");
  const authorityState = captain.length ? "captain-needed" :
    briefing.coverage.state !== "complete" || system.length ? "fo-inspecting" : "fo-continues";
  const compactIdle = authorityState === "fo-continues" && !briefing.children.active.length &&
    !briefing.children.latestReturn && !project?.needs.length && !nextCockpitWorkingSessions(group).length;
  const exactLabel = briefing.latest.stale ? "ACTIONABLE DIRECTION · STALE CACHED" :
    "LATEST ACTIONABLE DIRECTION";
  const directionSource = briefing.latest.direction
    ? nextCockpitRecoveryFactSource(briefing.latest.direction) : "unavailable";
  const resultSource = briefing.latest.result
    ? nextCockpitRecoveryFactSource(briefing.latest.result) : "unavailable";
  const resultLabel = briefing.latest.resultKind === "semantic"
    ? (briefing.latest.stale ? "LATEST EXACT RESULT · STALE CACHED" : "LATEST EXACT RESULT")
    : "LATEST SESSION RESULT";
  const directionEvidence = briefing.latest.direction
    ? `promoted exact direction · source session ${directionSource}` :
    "actionable direction not captured";
  const resultEvidence = briefing.latest.resultKind === "semantic"
    ? `exact semantic result · source session ${resultSource}`
    : briefing.latest.resultKind === "session"
      ? `session output; semantic result not captured · source session ${resultSource}`
      : "";
  const taskText = briefing.task.known ? [briefing.task.label, briefing.task.stage]
    .filter(Boolean).join(" · ") : "Not observed";
  const taskAttrs = (briefing.task.id ? ` data-work-item="${esc(briefing.task.id)}"` : "") +
    (briefing.task.known ? ' data-next-cockpit-task-known' : "");
  const assignmentEffect = briefing.task.known && briefing.task.qualifier
    ? `<small>${esc(briefing.task.qualifier)}</small>` : "";
  const assignmentEvidence = briefing.task.known && briefing.task.provenance
    ? `<details${nextCockpitDisclosureAttr("assignment:" + (briefing.task.id || briefing.task.sourceSession))}>` +
      '<summary>Evidence · assignment source</summary>' +
      `<small class="next-cockpit-source">${esc(briefing.task.provenance +
        (briefing.task.sourceSession ? ` · source session ${briefing.task.sourceSession}` : "") +
        (briefing.task.fact && briefing.task.fact.at ? ` · event ${briefing.task.fact.at}` : ""))}</small>` +
      '</details>' : '<small class="next-cockpit-evidence-missing">Assignment evidence not published</small>';
  const latestCells = [
    briefing.latest.directionInAssignment ? '<p>Direction shown in assignment</p>' :
    briefing.latest.direction ? `<span>${exactLabel}</span>` +
      `<strong>${esc(briefing.latest.direction.summary)}</strong>` : "",
    briefing.latest.result ? `<span>${resultLabel}</span>` +
      `<strong>${esc(briefing.latest.result.display || briefing.latest.result.summary)}</strong>` : "",
  ].filter(Boolean).join("");
  const latestEvidence = [briefing.latest.direction ? directionEvidence : "",
    briefing.latest.result ? resultEvidence : ""].filter(Boolean);
  const latestCell = latestCells ? '<div class="next-cockpit-recovery-evidence">' +
    `<span>LATEST EVIDENCE</span>${latestCells}` +
    (!briefing.latest.direction ? '<p class="next-cockpit-evidence-missing">Actionable direction not captured</p>' : "") +
    (!briefing.latest.result ? '<p class="next-cockpit-evidence-missing">Session result not captured</p>' : "") +
    `<details${nextCockpitDisclosureAttr("latest")}><summary>Evidence · direction and result sources</summary>` + latestEvidence.map(value =>
      `<small class="next-cockpit-source">${esc(value)}</small>`).join("") + '</details></div>' :
    '<div class="next-cockpit-recovery-evidence"><span>LATEST EVIDENCE</span>' +
    '<p class="next-cockpit-evidence-missing">Actionable direction not captured · ' +
    'Session result not captured</p></div>';
  return '<section class="next-cockpit-recovery" aria-label="Recovery summary">' +
    '<header><strong>PROJECT RECOVERY BRIEFING</strong></header>' +
    `<div data-next-cockpit-task${taskAttrs}><span>ASSIGNMENT</span>` +
    `<strong>${esc(taskText)}</strong>` +
    `${assignmentEffect}${assignmentEvidence}` +
    (project ? nextProjectGoal(project, nextCockpitFocusedAnnotation(group),
      nextCockpitFocusedObserved(group, project)) : "") + '</div>' +
    `<div><span>EXECUTION</span>${nextCockpitRecoveryExecution(group, briefing, compactIdle)}</div>` +
    `<div><span>COMMAND</span>` +
    nextCockpitWaitingCommand(project) +
    `${nextCockpitRecoveryAttention(group, observation, attention)}</div>` +
    latestCell +
    nextCockpitRecoveryMemoCell(group, focus, briefing) +
    '</section>';
}

function nextCockpitUtilityMenuItems(){
  if(nextRoute.view !== "project") return "";
  const group = nextProjectGroups().find(candidate => candidate.label === nextRoute.project);
  if(!group) return "";
  const focus = nextCockpitFocusedSession(group);
  const key = nextCockpitContextKey(group, focus);
  const copyState = nextCockpitBriefingCopyStates.get(key);
  const copyLabel = copyState === "copied" ? "Copied" :
    copyState === "error" ? "Copy unavailable" : "Copy briefing";
  const observation = nextCockpitProjectObservation(group);
  const attention = nextCockpitCommandAttention(group, observation);
  const briefing = nextCockpitRecoveryBriefing(group, focus, observation, attention);
  const memoEmpty = briefing.outcome === "Not set" && briefing.currentFocus === "Not set";
  const memoUtility = memoEmpty && briefing.task.known && briefing.coverage.state === "complete"
    ? `<button type="button" data-next-cockpit-action="memo-edit" ` +
      `data-arg="${esc(nextCockpitMemoKey(group, focus, "outcome"))}">Add human context</button>`
    : "";
  return `<button type="button" data-next-cockpit-action="copy-briefing">${copyLabel}</button>` +
    memoUtility;
}

function nextCockpitContextKey(group, focus){
  return `${nextCockpitStableKey(group)}\n${focus ? sessKey(focus) : ""}`;
}

function nextCockpitProjectObservation(group){
  const entry = nextCockpitContexts.get(nextCockpitContextKey(group, null));
  return entry && entry.data || null;
}

function nextCockpitCanonicalSemantic(group, semantic){
  const observation = nextCockpitProjectObservation(group);
  const projectSemantic = observation && observation.semantic || {};
  const labels = new Map((projectSemantic.work_items || []).map(item =>
    [String(item.work_item_id || ""), String(item.label || "")]));
  return Object.assign({}, semantic, {work_items:(semantic.work_items || []).map(item => {
    const label = labels.get(String(item.work_item_id || ""));
    return label ? Object.assign({}, item, {label}) : item;
  })});
}

function nextCockpitLoadContext(group, focus){
  if(!nextData) return;
  const key = nextCockpitContextKey(group, focus);
  if(nextObserverRequests.has(key)) return;
  const revision = nextFiniteNumber(nextData.generated);
  const settled = nextCockpitContexts.get(key);
  if(nextCockpitRequests.has(key) || settled && settled.revision >= revision) return;
  const request = {};
  nextCockpitRequests.set(key, request);
  const query = "/api/project-context?project=" + encodeURIComponent(nextCockpitStableKey(group)) +
    (focus ? "&session=" + encodeURIComponent(sessKey(focus)) : "");
  fetch(query).then(response => {
    if(!response.ok) throw new Error(String(response.status));
    return response.json();
  }).then(data => {
    if(nextCockpitRequests.get(key) !== request) return;
    nextCockpitRequests.delete(key);
    nextCockpitContexts.set(key, {data, revision});
    renderNext();
  }).catch(() => {
    if(nextCockpitRequests.get(key) !== request) return;
    nextCockpitRequests.delete(key);
    nextCockpitContexts.set(key, {data: settled && settled.data || null, revision, error: true});
    renderNext();
  });
}

function nextCockpitMemoFields(group, focus){
  const field = (kind, label, placeholder) => {
    const key = nextCockpitMemoKey(group, focus, kind);
    const value = nextCockpitReadMemo(key);
    const state = nextCockpitMemoStates.get(key);
    const cue = state === "error" ? "Browser storage unavailable" :
      state === "saved" ? "Saved in this browser" : "Autosaves in this browser";
    const editing = nextCockpitMemoEditingKey === key;
    if(editing){
      return `<label data-next-cockpit-memo-field="${kind}"><span>${label}</span>` +
        `<textarea maxlength="${NEXT_COCKPIT_MEMO_LIMIT}" data-next-cockpit-memo-input ` +
        `data-next-cockpit-memo-key="${esc(key)}" data-next-cockpit-memo-kind="${kind}" ` +
        `data-next-focus="memo:${esc(key)}" ` +
        `placeholder="${esc(placeholder)}">${esc(value)}</textarea>` +
        `<small data-next-cockpit-memo-cue="${kind}">${cue}</small>` +
        `<button type="button" data-next-cockpit-action="memo-done">Done</button></label>`;
    }
    return `<div data-next-cockpit-memo-field="${kind}"><span>${label}</span>` +
      `<strong>${esc(value || "Not set")}</strong>` +
      `<button type="button" data-next-cockpit-action="memo-edit" ` +
      `data-arg="${esc(key)}" aria-label="Edit ${label}">Edit</button></div>`;
  };
  const scope = focus ? nextCockpitSessionScopeKind(focus) : nextCockpitProjectScopeKind();
  return `<section class="next-cockpit-memos" data-next-cockpit-memos ` +
    `data-next-cockpit-primary data-scope-owner="${esc(scope.owner)}">` +
    '<header><strong>Outcome &amp; Focus</strong>' + nextCockpitScopeCue(scope) +
    '<span>Captain-authored · This browser only</span></header>' +
    '<div>' + field("outcome", "OUTCOME", "What result should this scope achieve?") +
    field("focus", "FOCUS", "What are you concentrating on now?") + '</div>' +
    '</section>';
}

function nextCockpitProjectScope(){
  return '<section class="next-cockpit-scope next-cockpit-scope--project">' +
    nextCockpitScopeCue(nextCockpitProjectScopeKind()) +
    '<strong>OVERVIEW</strong>' +
    '<span>Session selection filters Course, Decisions, and Console; Now remains project-wide.</span>' +
    '</section>';
}

function nextCockpitConsoleScope(focus){
  const scope = focus ? nextCockpitSessionScopeKind(focus) : nextCockpitProjectScopeKind();
  return '<header class="next-cockpit-scope next-cockpit-scope--evidence">' +
    nextCockpitScopeCue(scope) + '<strong>CONSOLE</strong></header>';
}

function nextCockpitSemantic(observation){
  return observation && observation.semantic || {facts:[],work_items:[],projections:{}};
}

function nextCockpitCurrentTask(observation){
  const semantic = nextCockpitSemantic(observation);
  const items = new Map((semantic.work_items || []).map(item =>
    [String(item.work_item_id || ""), item]));
  const heads = semantic.projections && Array.isArray(semantic.projections.trail_heads)
    ? semantic.projections.trail_heads : [];
  const head = heads.find(row => row && row.status === "current stage") || null;
  const id = String(head && head.work_item_id || "").trim();
  const item = id ? items.get(id) : null;
  const label = String(item && item.label || "").trim();
  const stage = String(head && head.stage || "").trim();
  if(!id || !label || !stage) return {known:false,id:"",label:"Not observed",stage:""};
  return {known:true,id,label:nextCockpitHumanLabel(label),stage:nextCockpitHumanLabel(stage)};
}

function nextCockpitTaskSubject(observation){
  const task = nextCockpitCurrentTask(observation);
  const scope = nextCockpitScopeCue(nextCockpitProjectScopeKind());
  if(!task.known){
    return '<section class="next-cockpit-task-subject" data-next-cockpit-task-subject ' +
      `data-next-cockpit-primary>${scope}<span>WORKFLOW TASK</span>` +
      '<h2>Not observed</h2></section>';
  }
  return '<section class="next-cockpit-task-subject" data-next-cockpit-task-subject ' +
    `data-next-cockpit-primary data-work-item="${esc(task.id)}">${scope}<span>CURRENT TASK</span>` +
    `<h2>${esc(task.label)} <small>· ${esc(task.stage)}</small></h2></section>`;
}

function nextCockpitViewingSession(focus){
  if(!focus) return "";
  const scope = nextCockpitSessionScopeKind(focus);
  const state = String(focus.state || "state unavailable").trim();
  return `<p class="next-cockpit-viewing-session" data-next-cockpit-viewing-session="${esc(sessKey(focus))}">` +
    `Viewing session · ${esc(scope.detail || "Session")} · ${esc(state)}</p>`;
}

function nextCockpitTabList(){
  const tabs = nextCockpitTabs(nextRoute && nextRoute.focus);
  const selected = tabs.includes(nextRoute && nextRoute.tab) ? nextRoute.tab : "now";
  return '<nav class="next-cockpit-tabs" role="tablist" aria-label="Project cockpit views">' +
    tabs.map(tab => {
      const label = nextCockpitHumanLabel(tab);
      const current = tab === selected;
      return `<button type="button" role="tab" data-next-cockpit-action="tab" ` +
        `data-arg="${tab}" data-next-focus="cockpit-tab:${tab}" aria-controls="next-cockpit-panel-${tab}" ` +
        `aria-selected="${current}" tabindex="${current ? 0 : -1}">${label}</button>`;
    }).join("") + '</nav>';
}

function nextCockpitLatestCompletedResult(semantic){
  const results = (semantic.facts || []).filter(fact => fact && fact.type === "result")
    .sort((left, right) => Number(right.at || 0) - Number(left.at || 0));
  for(const fact of results){
    const detail = String(fact.detail || fact.summary || "");
    const firstLine = detail.trimStart().split(/\r?\n/, 1)[0];
    if(!/^(?:fixed|completed|done)\b.*\blive\b/i.test(firstLine)) continue;
    const checkpoint = detail.match(/(?:checkpoint\s*:?\s*|\bat\s+)`?([0-9a-f]{7,40})`?/i);
    if(checkpoint) return {fact,checkpoint:checkpoint[1]};
  }
  return null;
}

function nextCockpitNowState(observation){
  const semantic = nextCockpitSemantic(observation);
  const task = nextCockpitCurrentTask(observation);
  const completed = nextCockpitLatestCompletedResult(semantic);
  const result = completed
    ? `<div>${nextCockpitScopeCue(nextCockpitFactScope(completed.fact))}` +
      `<span>COMPLETED RESULT · EXACT</span><strong>${esc(completed.checkpoint)}</strong>` +
      `<small>${esc(completed.fact.summary || "Exact returned result")}</small></div>`
    : `<div>${nextCockpitScopeCue(nextCockpitProjectScopeKind())}` +
      '<span>COMPLETED RESULT</span><strong>No completed result observed</strong></div>';
  return '<section class="next-cockpit-now-state" aria-label="Current task state">' +
    `<div>${nextCockpitScopeCue(nextCockpitProjectScopeKind())}` +
    '<span>CURRENT · EXACT WORKFLOW STATE</span>' +
    `<strong>${esc(task.known ? task.label + " · " + task.stage : task.label)}</strong></div>` +
    `<div>${nextCockpitScopeCue({kind:"unknown",owner:"unknown"})}` +
    '<span>CURRENT FOCUS · DERIVED</span><strong>Browser-local operator interpretation</strong></div>' +
    result + '</section>';
}

function nextCockpitActiveDelegation(group, observation){
  const task = nextCockpitCurrentTask(observation);
  const delegationGroup = {label:nextCockpitStableKey(group)};
  const lanes = group.sessions.flatMap(session => projectDelegationLanes(session, delegationGroup));
  const activeSessions = nextCockpitWorkingSessions(group);
  if(!lanes.length && !activeSessions.length){
    return '<section class="next-cockpit-active-delegation" data-next-cockpit-primary>' +
      nextCockpitScopeCue(nextCockpitProjectScopeKind()) +
      '<h2>Active work</h2><p>No active work</p></section>';
  }
  const assignmentRows = lanes.map(lane => {
    const session = group.sessions.find(candidate => sessKey(candidate) === lane.parentSession);
    const scope = session ? nextCockpitSessionScopeKind(session) : {kind:"unknown",owner:"unknown"};
    const workItem = lane.workItemId ? ` data-work-item="${esc(lane.workItemId)}"` : "";
    return `<li${workItem} data-parent-session="${esc(lane.parentSession || "")}">` +
      `<strong>${esc(lane.assignment)}</strong>` +
      `<small>${esc(lane.worker)} · ${esc(scope.detail || "source unavailable")} · ` +
      `${esc(lane.source)}</small></li>`;
  });
  const sessionRows = lanes.length ? [] : activeSessions.map(session => {
    const scope = nextCockpitSessionScopeKind(session);
    const detail = nextCockpitSessionActivityDetail(session);
    const secondary = [detail, scope.detail].filter(Boolean).join(" · ") || "Session";
    const binding = String(session.work_item_id || "").trim();
    const title = task.known && binding === task.id ? "Current task is active" : "Work is active";
    return `<li data-parent-session="${esc(sessKey(session))}"><strong>${title}</strong>` +
      `<small>${esc(secondary)}</small></li>`;
  });
  const rows = assignmentRows.concat(sessionRows).join("");
  return '<section class="next-cockpit-active-delegation" data-next-cockpit-active-delegation ' +
    'data-next-cockpit-primary>' +
    nextCockpitScopeCue(nextCockpitProjectScopeKind()) + '<h2>Active work</h2>' +
    `<ul>${rows}</ul></section>`;
}

function nextCockpitNeedsYou(commandAttention){
  const captain = (commandAttention || []).filter(item => item && item.owner === "CAPTAIN");
  const guard = (commandAttention || []).find(item => item &&
    item.kind === "coverage_inspection");
  if(!captain.length){
    const guardLabel = guard && guard.evidence && guard.evidence.confidence === "bounded"
      ? "Captain-attention coverage incomplete" : guard ? "Captain attention unavailable" :
        "Nothing needs you";
    return '<section class="next-cockpit-needs" data-next-cockpit-primary>' +
      nextCockpitScopeCue(nextCockpitProjectScopeKind()) +
      `<h2>Needs you</h2><p>${esc(guardLabel)}</p></section>`;
  }
  const rows = captain.map(item => `<li><strong>${esc(item.question || item.label)}</strong></li>`)
    .join("");
  return '<section class="next-cockpit-needs" data-next-cockpit-primary>' +
    nextCockpitScopeCue(nextCockpitProjectScopeKind()) +
    `<h2>Needs you</h2><ul>${rows}</ul></section>`;
}

function nextCockpitSystemDetails(commandAttention){
  const system = (commandAttention || []).filter(item => item && item.owner === "FO");
  if(!system.length) return "";
  return '<details class="next-cockpit-system-details" data-next-cockpit-system-details' +
    nextCockpitDisclosureAttr("system") + '>' +
    `<summary>System details</summary><ul>${system.map(item =>
      `<li>${esc(item.label)}</li>`).join("")}</ul></details>`;
}

function nextCockpitPlanDisclosure(context){
  const observation = nextCockpitProjectObservation(context.group);
  const discovery = observation && observation.workflow_discovery || {};
  const discovered = discovery.state === "observed" &&
    Array.isArray(discovery.workflows) && discovery.workflows.length;
  const attached = context.group.sessions.some(session => session.spacedock);
  if(!context.plans.length && !discovered && !attached) return "";
  return '<details class="next-cockpit-plan-details" data-next-cockpit-plan-details' +
    nextCockpitDisclosureAttr("plan") + '>' +
    `<summary>Show project plan</summary><div>${nextProjectPlanBlock(context)}</div></details>`;
}

function nextCockpitCompletedWork(context){
  const sessions = context.group.sessions;
  return nextProjectCompletedTasks(sessions).length || nextProjectProgress(sessions)
    ? nextProjectDone(context) : "";
}

function nextCockpitDecisionSummary(group, focus, observation){
  const entry = focus ? nextCockpitContexts.get(nextCockpitContextKey(group, focus)) : null;
  const semantic = focus ? entry && entry.data && entry.data.semantic : nextCockpitSemantic(observation);
  if(!semantic) return "";
  const canonical = nextCockpitCanonicalSemantic(group, semantic);
  const counts = nextCockpitCaptainDecisionCounts(canonical);
  const total = Object.values(counts).reduce((sum, value) => sum + value, 0);
  if(!total) return "";
  return '<p class="next-cockpit-decision-summary" data-next-cockpit-decision-summary>' +
    `Decision application · ${esc(nextCockpitRecoveryDecisions(canonical))}</p>`;
}

function nextCockpitConsoleStatus(group){
  const rows = group.sessions.map(session => `<li>${esc(sessKey(session))} · ` +
    `${esc(String(session.state || "unknown"))}</li>`).join("");
  if(!rows) return "";
  return '<details class="next-cockpit-console-status" data-next-cockpit-console-status' +
    nextCockpitDisclosureAttr("status") + '>' +
    `<summary>Raw project status</summary><ul>${rows}</ul></details>`;
}

function nextCockpitReviewFindings(detail){
  const lines = String(detail || "").split(/\r?\n/);
  let collecting = false;
  const findings = [];
  for(const raw of lines){
    const line = raw.replace(/^\s*\d+\.\s*/, "").replace(/\*\*/g, "").trim();
    if(/^review changed the course\s*:/i.test(line)){
      collecting = true;
      continue;
    }
    if(!collecting) continue;
    const bullet = line.match(/^[-*]\s+(.+)/);
    if(bullet){ findings.push(bullet[1].trim()); continue; }
    if(line) break;
  }
  return findings;
}

function nextCockpitCourseEvidence(fact, contributors, occurrence = ""){
  const evidence = fact.evidence || {};
  const source = String(evidence.source || fact.source_kind || "").trim();
  const confidence = String(evidence.confidence || "").trim();
  const identity = String(fact.fact_id || "").trim();
  const known = value => Boolean(value) && !/^(?:(?:source|confidence) )?(?:unavailable|unknown)$/i.test(value);
  const missing = [!known(source) ? "Evidence source not published" : "",
    !known(confidence) ? "Evidence confidence not published" : "",
    !identity ? "Fact identity not published" : ""].filter(Boolean);
  const absence = missing.length ? `<p class="next-cockpit-evidence-missing">` +
    `${esc(missing.join(" · "))}</p>` : "";
  if(!known(source) && !known(confidence) && !identity && !contributors.length) return absence;
  const names = contributors.length
    ? `<div><b>Contributors</b> · ${esc(contributors.join(" · "))}</div>` : "";
  return absence + '<details class="next-course-evidence"' +
    nextCockpitDisclosureAttr("course:" + occurrence + ":" + (identity || source + ":" + fact.at)) + '>' +
    '<summary>Evidence · source and confidence</summary>' +
    (known(source) ? `<div><b>Source</b> · <span class="next-cockpit-source">${esc(source)}</span></div>` : "") +
    (known(confidence) ? `<div><b>Confidence</b> · <span class="next-cockpit-source">${esc(confidence)}</span></div>` : "") +
    (identity ? `<div><b>Fact</b> · <span class="next-cockpit-source">${esc(identity)}</span></div>` : "") +
    `${names}</details>`;
}

function nextCockpitCourseRow(episode){
  const direction = episode.directionFact
    ? `<p><b>Direction</b> · ${esc(episode.directionFact.summary || "Direction unavailable")}</p>`
    : "";
  const body = episode.findings && episode.findings.length
    ? `<ul>${episode.findings.map(finding => `<li>${esc(finding)}</li>`).join("")}</ul>`
    : `<p>${esc(episode.summary)}</p>`;
  const scope = episode.scope || nextCockpitFactSetScope(episode.sourceFacts || [episode.fact]);
  return `<article class="next-course-episode" data-epistemic-kind="${esc(episode.epistemic)}" ` +
    `data-scope-kind="${esc(scope.kind)}">` +
    `<header>${nextCockpitScopeCue(scope)}<span>${esc(episode.badge)}</span></header>` +
    `<strong>${esc(episode.task + " · " + episode.label)}</strong>${direction}${body}` +
    nextCockpitCourseEvidence(episode.fact, episode.contributors || []) +
    (episode.directionFact ? nextCockpitCourseEvidence(episode.directionFact, [],
      "direction-for:" + episode.fact.fact_id) : "") +
    '</article>';
}

function nextCockpitCourseEpisodes(semantic, lanes){
  const items = new Map((semantic.work_items || []).map(item =>
    [String(item.work_item_id || ""), nextCockpitHumanLabel(item.label)]));
  const taskFor = fact => items.get(String(fact.work_item_id || "")) || "Task not observed";
  const exactlyBound = fact => items.has(String(fact && fact.work_item_id || ""));
  const facts = (semantic.facts || []).filter(Boolean);
  const factsById = new Map(facts.map(fact => [String(fact.fact_id || ""), fact]));
  const projections = semantic.projections || {};
  const intents = new Map((projections.operator_intents || []).map(intent =>
    [String(intent && intent.projection_id || ""), intent]));
  const pairedDirection = fact => {
    const episode = (projections.steering_episodes || []).find(row =>
      String(row && row.adaptation_fact || "") === String(fact.fact_id || ""));
    const intent = episode && intents.get(String(episode.intent_id || ""));
    const direction = intent && factsById.get(String(intent.derived_from || ""));
    const sameTask = String(direction && direction.work_item_id || "") &&
      String(direction && direction.work_item_id || "") === String(fact.work_item_id || "");
    const ordered = Number.isFinite(Number(direction && direction.at)) &&
      Number.isFinite(Number(fact.at)) && Number(direction.at) <= Number(fact.at);
    return direction && direction.type === "user_message" && exactlyBound(direction) &&
      sameTask && ordered ? direction : null;
  };
  const contributorNames = fact => [...new Set((lanes || []).filter(lane =>
    !fact.work_item_id || String(lane.workItemId || "") === String(fact.work_item_id))
    .map(lane => String(lane.worker || "")).filter(Boolean))];
  const episodes = [];
  const used = new Set();
  const lifecycle = new Set();
  for(const fact of facts){
    if(used.has(String(fact.fact_id || ""))) continue;
    const findings = fact.type === "result" ? nextCockpitReviewFindings(fact.detail) : [];
    const completed = fact.type === "result"
      ? nextCockpitLatestCompletedResult({facts:[fact]}) : null;
    const directionFact = pairedDirection(fact);
    const evidence = fact.evidence || {};
    const review = findings.length > 0 && Boolean(String(evidence.source || "").trim());
    const decision = fact.type === "gate_decision" && Boolean(String(fact.decision || "").trim());
    const state = fact.type === "stage_transition" && Boolean(String(fact.stage || "").trim());
    if(!exactlyBound(fact) || !review && !completed && !decision && !state) continue;
    const lifecycleKey = fact.type === "result" ? String(fact.fact_id || "") :
      `${fact.type}\n${String(fact.work_item_id || "")}\n${String(fact.stage || fact.source_kind || "")}`;
    if(lifecycle.has(lifecycleKey)) continue;
    lifecycle.add(lifecycleKey);
    const summary = String(fact.summary || fact.stage || "Work observed") +
      (completed ? ` · checkpoint ${completed.checkpoint}` : "");
    const sourceFacts = directionFact ? [directionFact, fact] : [fact];
    episodes.push({at:Number(fact.at || 0),fact,sourceFacts,task:taskFor(fact),
      label:review ? "Course change" : decision ? "Decision" : state ? "State change" : "Result",
      badge:review ? "DERIVED COURSE CHANGE" : decision ? "EXACT DECISION" :
        state ? "EXACT STATE CHANGE" : "EXACT RESULT",
      epistemic:review ? "derived-course-change" : "exact-course-change",
      summary,findings,directionFact,contributors:contributorNames(fact)});
    if(directionFact) used.add(String(directionFact.fact_id || ""));
  }
  return episodes.sort((left, right) => left.at - right.at);
}

function nextCockpitCourseDirections(semantic, episodes){
  const used = new Set(episodes.map(episode =>
    String(episode.directionFact && episode.directionFact.fact_id || "")).filter(Boolean));
  const projected = new Set((semantic.projections && semantic.projections.operator_intents || [])
    .map(intent => String(intent && intent.derived_from || "")).filter(Boolean));
  return (semantic.facts || []).filter(fact => fact && fact.type === "user_message" &&
    !used.has(String(fact.fact_id || "")) &&
    (fact.intent_promoted === true || projected.has(String(fact.fact_id || ""))))
    .sort((left, right) => Number(left.at || 0) - Number(right.at || 0));
}

function nextCockpitCourseDirectionRow(fact){
  const scope = nextCockpitFactScope(fact);
  return `<article class="next-course-direction" data-scope-kind="${esc(scope.kind)}">` +
    `<header>${nextCockpitScopeCue(scope)}<span>EXACT DIRECTION</span></header>` +
    `<p>${esc(fact.summary || "Direction unavailable")}</p>` +
    nextCockpitCourseEvidence(fact, []) + '</article>';
}

function nextCockpitCourse(group, semantic, lanes){
  const episodes = nextCockpitCourseEpisodes(semantic, lanes);
  const directions = nextCockpitCourseDirections(semantic, episodes);
  const visible = episodes.slice(-8);
  const earlier = episodes.slice(0, -8);
  const disclosure = earlier.length ? '<details class="next-course-earlier"' +
    nextCockpitDisclosureAttr("course-earlier") + '><summary>' +
    `${earlier.length} Earlier</summary>${earlier.map(nextCockpitCourseRow).join("")}</details>` : "";
  const empty = episodes.length ? "" :
    `<p class="next-cockpit-empty">${esc(projectHistoryEmptyText(semantic, "course"))}</p>`;
  const other = directions.length ? '<details class="next-course-directions"' +
    nextCockpitDisclosureAttr("course-directions") + '><summary>' +
    `Other directions (${directions.length})</summary>` +
    directions.map(nextCockpitCourseDirectionRow).join("") + '</details>' : "";
  return `<div class="next-cockpit-course" data-next-cockpit-course>${empty}${disclosure}` +
    visible.map(nextCockpitCourseRow).join("") + other + '</div>';
}

function nextCockpitTimeline(group, focus, mode = "active"){
  const key = nextCockpitContextKey(group, focus);
  const entry = nextCockpitContexts.get(key);
  const projectEntry = nextCockpitContexts.get(nextCockpitContextKey(group, null));
  nextCockpitLoadContext(group, focus);
  if(!entry || !entry.data || focus && (!projectEntry || !projectEntry.data)){
    const failed = entry && entry.error || focus && projectEntry && projectEntry.error;
    const label = failed ? "Semantic context unavailable." : "Loading semantic context…";
    return `<section class="next-cockpit-semantic" data-next-cockpit-semantic><h2>SEMANTIC TIMELINE</h2>` +
      `<p class="next-cockpit-empty">${label}</p></section>`;
  }
  projectQuerySession = focus ? sessKey(focus) : "";
  const cacheKey = projectContextKey(nextCockpitStableKey(group));
  projectContextByLabel[cacheKey] = {state:"ready", data:entry.data, generated:entry.revision};
  const delegationGroup = {label: nextCockpitStableKey(group)};
  const lanes = focus ? projectDelegationLanes(focus, delegationGroup) :
    group.sessions.flatMap(session => projectDelegationLanes(session, delegationGroup));
  const semantic = nextCockpitCanonicalSemantic(
    group,
    entry.data.semantic || {facts:[], work_items:[], projections:{}},
  );
  const timeline = projectSemanticTimeline(nextData, semantic, lanes, focus, group.sessions,
    mode === "decisions" ? {mode:"decisions",controls:false,
      eventPrefix:event => nextCockpitScopeCue(nextCockpitFactScope(event.fact))} : null)
    .replaceAll('data-calm="project-graph-mode"', 'data-next-cockpit-action="graph-mode"');
  return '<section class="next-cockpit-semantic" data-next-cockpit-semantic>' +
    `<h2>${mode === "decisions" ? "RECORDED DECISIONS" : "SEMANTIC TIMELINE"}</h2>` +
    timeline + '</section>';
}

function nextCockpitCoursePanel(group, focus){
  const key = nextCockpitContextKey(group, focus);
  const entry = nextCockpitContexts.get(key);
  const projectEntry = nextCockpitContexts.get(nextCockpitContextKey(group, null));
  nextCockpitLoadContext(group, focus);
  if(!entry || !entry.data || focus && (!projectEntry || !projectEntry.data)){
    const failed = entry && entry.error || focus && projectEntry && projectEntry.error;
    return `<p class="next-cockpit-empty">${failed ? "Course evidence unavailable." :
      "Loading course evidence…"}</p>`;
  }
  const delegationGroup = {label:nextCockpitStableKey(group)};
  const lanes = focus ? projectDelegationLanes(focus, delegationGroup) :
    group.sessions.flatMap(session => projectDelegationLanes(session, delegationGroup));
  const semantic = nextCockpitCanonicalSemantic(
    group,
    entry.data.semantic || {facts:[],work_items:[],projections:{}},
  );
  return nextCockpitCourse(group, semantic, lanes);
}

function nextCockpitTerminal(group, focus){
  if(!focus) return "";
  projectTerminalLookup(nextData, focus);
  const surface = projectTerminalSurface(focus);
  if(!surface) return "";
  return '<section class="next-cockpit-terminal" data-next-cockpit-terminal>' +
    '<h2>EXACT SESSION TERMINAL</h2>' +
    surface.replaceAll('data-calm="project-terminal-', 'data-next-cockpit-action="terminal-') +
    '</section>';
}

function nextCockpitPanel(context, focus, observation, commandAttention){
  /* The route's `focus`, not this function's resolved `focus` session. Every
     other site that needs the tab set has only the route: the keydown handler
     has no group, and `next-boot.js` runs before there is one. One source, so
     the nav, the panel and the wrap cannot answer differently. */
  const tab = nextCockpitTabs(nextRoute && nextRoute.focus).includes(nextRoute && nextRoute.tab)
    ? nextRoute.tab : "now";
  let body = "";
  if(tab === "now"){
    body = (focus ? '<p class="next-cockpit-scope-note">Now remains project-wide, ' +
      'including activity from other sessions.</p>' : "") +
      nextProjectGoingOn(context, commandAttention) + nextProjectEndings(context) +
      nextProjectPlanStatus(context) + nextCockpitPlanDisclosure(context);
  }else if(tab === "held-to"){
    body = nextCockpitHeldTo(context.group, observation);
  }else if(tab === "course"){
    body = nextProjectChanges(context.project) +
      nextCockpitCoursePanel(context.group, focus) + nextCockpitCompletedWork(context);
  }else if(tab === "decisions"){
    body = nextCockpitDecisionSummary(context.group, focus, observation) +
      nextCockpitTimeline(context.group, focus, "decisions");
  }else{
    body = nextCockpitConsoleScope(focus) + (focus
      ? nextCockpitTerminal(context.group, focus)
      : '<p class="next-cockpit-empty">Select one exact session to open its read-only console.' +
        (context.group.sessions.length === 1
          ? ` <a href="${esc(nextFragmentForRoute({view:"project",project:context.group.label,
            focus:sessKey(context.group.sessions[0]),tab:"console"}))}">Open this session’s console</a>`
          : "") + '</p>') +
      nextObserverModelControls(context.group, focus) +
      nextCockpitConsoleStatus(context.group) + nextProjectRail(context);
  }
  return `<section class="next-cockpit-panel" id="next-cockpit-panel-${tab}" role="tabpanel" ` +
    `data-next-cockpit-panel="${tab}" aria-label="${nextCockpitHumanLabel(tab)}">${body}</section>`;
}

function nextProjectCockpit(context, observation, commandAttention){
  const group = context.group;
  const focus = nextCockpitFocusedSession(group);
  projectQuerySession = focus ? sessKey(focus) : "";
  lastData = nextData;
  return nextCockpitViewingSession(focus) +
    nextCockpitRecoveryStrip(group, observation, commandAttention, context.project) +
    nextCockpitTabList() +
    nextCockpitPanel(context, focus, observation, commandAttention);
}

function nextCockpitBeforeRender(){
  const app = document.getElementById("app");
  for(const details of nextCockpitHadDisclosures && app && app.querySelectorAll ? app.querySelectorAll("[data-next-cockpit-disclosure]") : []){
    nextCockpitDisclosureStates.set(details.getAttribute("data-next-cockpit-disclosure"), details.open === true);
  }
  projectCaptureDisclosureStates();
  nextCockpitTerminalScreen = projectTerminalBeforeRender();
}

function nextCockpitAfterRender(){
  const app = document.getElementById("app");
  nextCockpitHadDisclosures = nextRoute && nextRoute.view === "project";
  for(const details of nextCockpitHadDisclosures && app && app.querySelectorAll ? app.querySelectorAll("[data-next-cockpit-disclosure]") : []){
    const key = details.getAttribute("data-next-cockpit-disclosure");
    details.open = nextCockpitDisclosureStates.get(key) === true;
    const summary = details.querySelector("summary");
    if(summary) summary.setAttribute("data-next-focus", "cockpit-disclosure:" + key);
  }
  projectTerminalAfterRender(nextCockpitTerminalScreen);
  nextCockpitTerminalScreen = null;
}

function nextCockpitActionTarget(event){
  return event.target && event.target.closest
    ? event.target.closest("[data-next-cockpit-action]") : null;
}

document.addEventListener("input", event => {
  const input = event.target && event.target.closest
    ? event.target.closest("[data-next-cockpit-memo-input]") : null;
  if(!input) return;
  const key = String(input.dataset.nextCockpitMemoKey || "");
  if(!key) return;
  const value = nextCockpitBoundMemo(input.value);
  input.value = value;
  nextCockpitMemoDrafts.set(key, value);
  try{
    localStorage.setItem(key, value);
    nextCockpitMemoStates.set(key, "saved");
  }catch(_error){
    nextCockpitMemoStates.set(key, "error");
  }
  const cue = input.parentElement && input.parentElement.querySelector
    ? input.parentElement.querySelector(`[data-next-cockpit-memo-cue="${input.dataset.nextCockpitMemoKind}"]`)
    : null;
  if(cue) cue.textContent = nextCockpitMemoStates.get(key) === "saved"
    ? "Saved in this browser" : "Browser storage unavailable";
});

/* No redraw on a keystroke, and this is measured rather than copied from the
   memo lane beside it. A first version called `renderNext` here, and every
   character typed landed at offset 0: the field is a new element after the
   replacement and the named-focus lane restores the caret a beat late, so
   " and green" arrived as "neerg dna" in front of the saved value. The three
   things an edit changes are updated in place instead, which is also why both
   controls are rendered and hidden rather than rendered conditionally. */
document.addEventListener("input", event => {
  const input = event.target && event.target.closest
    ? event.target.closest("[data-next-cockpit-held-key]") : null;
  if(!input) return;
  const key = String(input.dataset.nextCockpitHeldKey || "");
  if(!key) return;
  const value = String(input.value || "")
    .replace(NEXT_COCKPIT_HELD_UNSAFE, " ").slice(0, nextCockpitHeldCap());
  if(value !== input.value) input.value = value;
  nextCockpitHeldDrafts.set(key, value);
  nextCockpitHeldStates.delete(key);
  const field = input.closest ? input.closest("[data-next-cockpit-held-field]") : null;
  if(!field || !field.querySelector) return;
  const count = field.querySelector("[data-next-cockpit-held-count]");
  if(count) count.textContent = `${value.length}/${nextCockpitHeldCap()}`;
  nextCockpitHeldToggle(field, "held-clear", Boolean(value));
  nextCockpitHeldToggle(field, "held-save",
    value !== String(input.dataset.nextCockpitHeldSaved || ""));
  // The fourth thing an edit changes. "No goal typed for this session" is an
  // answer to "why is this empty", and it stayed under the reader's own
  // half-typed sentence until something else forced a redraw.
  const absent = field.querySelector("[data-next-cockpit-held-absent]");
  if(absent) absent.hidden = Boolean(value);
});

document.addEventListener("click", event => {
  const target = nextCockpitActionTarget(event);
  if(!target) return;
  const action = String(target.dataset.nextCockpitAction || "");
  const group = nextRoute.view === "project"
    ? nextProjectGroups().find(candidate => candidate.label === nextRoute.project) : null;
  if(action === "tab"){
    const tab = String(target.dataset.arg || "");
    if(!group || !nextCockpitTabs(nextRoute.focus).includes(tab)) return;
    event.preventDefault();
    navigateNext({view:"project",project:group.label,focus:nextRoute.focus || null,tab});
    nextRestoreFocus({named:"cockpit-tab:" + tab}, nextAttention);
    return;
  }
  if(action === "held-clear" || action === "held-save"){
    const session = group ? nextCockpitFocusedSession(group) : null;
    if(!session) return;
    event.preventDefault();
    const kind = String(target.dataset.arg || "");
    const key = nextCockpitHeldKey(session, kind);
    if(action === "held-save"){
      nextCockpitHeldSave(session, kind);
      return;
    }
    // Emptying the box is an edit, not a save. The cleared field then differs
    // from the store, so `save` appears and the person commits the clearing
    // deliberately.
    nextCockpitHeldDrafts.set(key, "");
    nextCockpitHeldStates.delete(key);
    renderNext({named: key});
    return;
  }
  if(action === "memo-edit"){
    event.preventDefault();
    nextCockpitMemoEditingKey = String(target.dataset.arg || "");
    nextCockpitMemoOriginal = nextCockpitReadMemo(nextCockpitMemoEditingKey);
    renderNext({named:"memo:" + nextCockpitMemoEditingKey});
    return;
  }
  if(action === "memo-done"){
    event.preventDefault();
    nextCockpitMemoEditingKey = null;
    renderNext();
    return;
  }
  if(action === "copy-briefing"){
    event.preventDefault();
    if(!group) return;
    const focus = nextCockpitFocusedSession(group);
    const observation = nextCockpitProjectObservation(group);
    const attention = nextCockpitCommandAttention(group, observation);
    const key = nextCockpitContextKey(group, focus);
    const clipboard = navigator && navigator.clipboard;
    if(!clipboard || typeof clipboard.writeText !== "function"){
      nextCockpitBriefingCopyStates.set(key, "error");
      renderNext();
      return;
    }
    Promise.resolve(clipboard.writeText(
      nextCockpitRecoveryBriefing(group, focus, observation, attention).text,
    )).then(() => {
      nextCockpitBriefingCopyStates.set(key, "copied");
      renderNext();
    }).catch(() => {
      nextCockpitBriefingCopyStates.set(key, "error");
      renderNext();
    });
    return;
  }
  const key = String(target.dataset.arg || projectQuerySession || "");
  if(action === "graph-mode"){
    event.preventDefault();
    if(["active", "all", "decisions"].includes(String(target.dataset.arg || ""))){
      projectGraphModeBySession.set(projectQuerySession, String(target.dataset.arg));
      renderNext();
    }
  }else if(action === "terminal-open"){
    event.preventDefault();
    projectTerminalOpenKey = key;
    projectTerminalFollowLive = true;
    projectTerminalScrollTop = 0;
    renderNext();
  }else if(action === "terminal-close"){
    event.preventDefault();
    projectTerminalOpenKey = null;
    projectTerminalDispose();
    renderNext();
  }else if(action === "terminal-jump"){
    event.preventDefault();
    projectTerminalScrollToLive();
  }
});

function nextCockpitHandleKeydown(event){
  const held = event.target && event.target.closest
    ? event.target.closest("[data-next-cockpit-held-key]") : null;
  if(event.key === "Escape" && held){
    event.preventDefault();
    const key = String(held.dataset.nextCockpitHeldKey || "");
    // Drop the draft rather than write the saved value back into it: the
    // render reads the store whenever the Map has no entry, so this is the
    // one place the two cannot disagree.
    nextCockpitHeldDrafts.delete(key);
    nextCockpitHeldStates.delete(key);
    renderNext({named: key});
    return true;
  }
  const field = event.target && event.target.closest
    ? event.target.closest("[data-next-cockpit-memo-field]") : null;
  if(event.key === "Escape" && field && nextCockpitMemoEditingKey){
    event.preventDefault();
    const key = nextCockpitMemoEditingKey;
    nextCockpitMemoDrafts.set(key, nextCockpitMemoOriginal);
    try{
      localStorage.setItem(key, nextCockpitMemoOriginal);
      nextCockpitMemoStates.set(key, "saved");
    }catch(_error){
      nextCockpitMemoStates.set(key, "error");
    }
    nextCockpitMemoEditingKey = null;
    renderNext();
    return true;
  }
  const target = nextCockpitActionTarget(event);
  if(!target || String(target.dataset.nextCockpitAction || "") !== "tab") return false;
  if(!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return false;
  const current = String(target.dataset.arg || "now");
  /* The one list, so the wrap cannot reach past what the nav drew. */
  const tabs = nextCockpitTabs(nextRoute.focus);
  const index = Math.max(0, tabs.indexOf(current));
  const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 :
    (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
  event.preventDefault();
  navigateNext({view:"project",project:nextRoute.project,focus:nextRoute.focus || null,
    tab:tabs[next]});
  nextRestoreFocus({named:"cockpit-tab:" + tabs[next]}, nextAttention);
  return true;
}
