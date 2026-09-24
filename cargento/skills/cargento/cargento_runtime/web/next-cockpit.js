const NEXT_COCKPIT_MEMO_PREFIX = "cargento.cockpit.memo.v2:";
const NEXT_COCKPIT_MEMO_LIMIT = 500;
const nextCockpitContexts = new Map();
const nextCockpitRequests = new Map();
const nextCockpitReadingRequests = new Map();
const nextCockpitMemoDrafts = new Map();
const nextCockpitMemoStates = new Map();
const nextCockpitBriefingCopyStates = new Map();
const nextCockpitDisclosureStates = new Map();
let nextCockpitHadDisclosures = false;
let nextCockpitTerminalScreen = null;
let nextCockpitMemoEditingKey = null;
let nextCockpitMemoOriginal = "";

function nextCockpitDisclosureAttr(control){
  /* The session route has no `focus`, so without its own identity every
     session of one project shared a key and opening a caveat on one opened it
     on the next. `harness:session` is `sessKey`'s shape, as the cockpit's
     focus is. */
  const focus = nextRoute && nextRoute.view === "session"
    ? `${nextRoute.harness || ""}:${nextRoute.session || ""}`
    : nextRoute && nextRoute.focus || "";
  const key = [nextRoute && nextRoute.project || "", focus, control].join("\n");
  return ` data-next-cockpit-disclosure="${esc(key)}"`;
}

/* Tier 2 of the caveat rule ([NUI-19](docs/design-next-ui.md#nui-19-a-caveat-has-three-tiers)):
   the claim stays inline where the reader meets it and the rest goes behind a
   summary naming what is inside.

   Built on `nextCockpitDisclosureAttr` rather than beside it, so the generic
   restore lane in `nextCockpitAfterRender` reopens it with no registration. A
   bare `<details>` is one line shorter and snaps shut on every redraw, and the
   board redraws on live payload, so the reader would lose the sentence
   mid-read.

   Two fallbacks, because both silently delete a caveat rather than tiering it:
   an empty body renders nothing at all instead of a summary promising text
   that is not there, and a missing summary renders the body inline instead of
   hiding it behind a control with no label. */
function nextCockpitWhy(control, summary, body){
  const text = String(body == null ? "" : body).trim();
  if(!text) return "";
  if(!summary) return `<p class="next-cockpit-reading-why">${esc(text)}</p>`;
  return `<details class="next-cockpit-why"${nextCockpitDisclosureAttr(control)}>` +
    `<summary>${esc(summary)}</summary>` +
    `<p class="next-cockpit-reading-why">${esc(text)}</p></details>`;
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

/* The row's seventeen flat `annotation_*` fields as one object, or null when the
   row carries none. The payload is flat because `history.PROMPT_TEXT_ALLOWLIST`
   admits field names and a name cannot reach inside a mapping; the renderers
   want an object, so the seam is here and they are unchanged.

   Null when nothing was ever typed AND no reason was published, which is a row
   from a build older than the field set rather than an unannotated session: an
   unannotated row carries its absence sentences. */
function nextCockpitAnnotation(session){
  if(!session) return null;
  /* Seventeen published fields, and every one of them is published now:
     `base_session` declares all three of the reading's. The comment here
     used to say `assessment` was read but never published, which stopped
     being true when a producer landed -- and `TheAnnotationFieldListIsDerivedTest`
     now derives this list from `annotations.published` so it cannot drift
     again. This is a three-defect site, and every defect was the page
     reading a field nothing publishes. */
  const fields = ["goal", "goal_why", "output", "output_why", "revision",
    "revision_count", "at", "goal_source", "goal_source_at", "binding_why", "settled_at", "settled_through",
    "settled_revision", "assessment", "reading_count", "reading_withheld",
    "reading_refused", "discarded_at", "discarded_why"];
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
function nextCockpitFocusedObserved(group, project, focus = nextCockpitFocusedSession(group)){
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

/* The one session this page is about, on either route that has one. The
   session view joined the project cockpit's focus when Held to merged into it
   under the drift ruling, and every drift control resolves its session here, so the two
   routes cannot disagree about whose words a press acts on. The session arm
   applies `nextSessionFind`'s rule: harness and sid, and exactly one match. */
function nextCockpitFocusedSession(group){
  if(!nextRoute || !group) return null;
  if(nextRoute.view === "session"){
    const harness = String(nextRoute.harness || "");
    const matches = group.sessions.filter(session =>
      String(session.sid == null ? "" : session.sid) === String(nextRoute.session || "") &&
      (!harness || String(session.harness || "") === harness));
    return matches.length === 1 ? matches[0] : null;
  }
  if(nextRoute.view !== "project" || !nextRoute.focus) return null;
  return group.sessions.find(session => sessKey(session) === nextRoute.focus) || null;
}

/* The project group the current route is inside, for the project cockpit and
   for a session page alike. A session with no project label groups under "",
   which is a real group here rather than a missing one. */
function nextCockpitRouteGroup(){
  if(!nextRoute || !["project", "session"].includes(nextRoute.view)) return null;
  const label = String(nextRoute.project == null ? "" : nextRoute.project);
  return nextProjectGroups().find(candidate => candidate.label === label) || null;
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

function nextCockpitSessionIsWorking(session, group){
  if(session && session.state === "working" && nextSessionEndedAt(session) == null){
    return true;
  }
  if(group){
    const observed = nextCockpitObservedProject(group);
    if(observed && Array.isArray(observed.working)){
      const keys = new Set(observed.working.map(nextSessionKey));
      if(keys.has(nextSessionKey(session))) return true;
    }
  }
  return false;
}

function nextCockpitSessionTone(session, group){
  if(group){
    const observed = nextCockpitObservedProject(group);
    if(observed && Array.isArray(observed.sessions)){
      const found = observed.sessions.find(s => nextSessionKey(s) === nextSessionKey(session));
      if(found && found.tone) return found.tone;
    }
  }
  if(session && session.tone) return session.tone;
  if(session && session.turn && session.turn.long) return "want";
  return "ok";
}

function nextCockpitScopeSessionRank(session, group){
  if(nextCockpitSessionIsWorking(session, group)) return 0;
  if(session && session.state === "needs_input") return 1;
  if(session && session.state === "idle") return 2;
  return 3;
}

function nextCockpitScopeHarnessLabel(session){
  return nextHarnessLabels().get(String(session && session.harness || "")) ||
    String(session && session.harness || "Session");
}

/* The harness name when every row in the group carries the same one, so the
   rail says it once in its heading instead of on every card. Empty on a mixed
   group, where the name is the thing that tells two cards apart. */
function nextCockpitScopeHoistedHarness(group){
  const sessions = group && Array.isArray(group.sessions) ? group.sessions : [];
  const labels = new Set(sessions.map(nextCockpitScopeHarnessLabel));
  return sessions.length && labels.size === 1 ? [...labels][0] : "";
}

function nextCockpitScopeHeading(group){
  const hoisted = nextCockpitScopeHoistedHarness(group);
  return `<span class="next-cockpit-scope-heading">SCOPE${hoisted ? " \u00b7 " + esc(hoisted) : ""}</span>`;
}

function nextCockpitScopeLinks(group, focus, surface = "tree"){
  const selected = focus ? sessKey(focus) : "project";
  /* `value` and `meta`, not `label` and `subtitle`: the project row and the
     session rows hold their value in opposite slots -- the project's is its
     own name with the count beneath, a session's is its title with the
     harness and state beneath. Reordering the DOM for every row would put the
     project's count above its name, so each caller says which of its strings
     is the value instead.

     `value` is text and is escaped here; `meta` is HTML, because the session
     row composes a state span into it. A caller passing text escapes it. */
  const link = (key, rawValue, meta, scope, options = {}) => {
    const route = {view:"project",project:group.label,focus:key === "project" ? null : key,
      tab:nextRoute && nextRoute.tab || "now"};
    /* Whitespace normalised, because line 1 is one clipped line and a title
       carrying a newline would break both the line and the `title=` tooltip.
       Not truncated: the 90-character slice this replaces existed when the
       string wrapped to two rows with nothing clipping it, and cutting it here
       now would take the tail that `text-overflow:ellipsis` is drawing. */
    const value = String(rawValue).replace(/\s+/g, " ").trim();
    const withheld = value === "Session title not published";
    const kindMark = scope.kind === "session"
      ? '<span class="next-cockpit-scope-mark" aria-hidden="true">' +
        '<i class="next-scope-marker next-scope-marker--round"></i></span>' +
        '<span class="next-visually-hidden">SESSION</span>'
      : "";
    return `<a href="${esc(nextFragmentForRoute(route))}" data-next-cockpit-scope="${esc(key)}"` +
      (selected === key ? ` aria-current="page"` : "") +
      (options.isWorking ? ' data-next-working="true"' : "") +
      ` data-scope-kind="${esc(scope.kind)}" data-scope-owner="${esc(scope.owner || "unknown")}"` +
      ` data-next-focus="cockpit-scope:${surface}:${esc(key)}">` +
      (scope.kind === "session" ? "" :
        nextCockpitScopeCue(Object.assign({}, scope, {detail:""}))) +
      '<span class="next-cockpit-scope-line">' + kindMark +
      `<span class="next-cockpit-scope-title"${withheld ? " data-next-withheld" : ""}` +
      ` title="${esc(value)}">${esc(value)}</span></span>` +
      (meta ? `<span class="next-cockpit-scope-meta">${meta}</span>` : "") +
      `</a>`;
  };
  const rows = [...group.sessions].sort((left, right) =>
    nextCockpitScopeSessionRank(left, group) - nextCockpitScopeSessionRank(right, group) ||
    String(left.harness || "").localeCompare(String(right.harness || "")) ||
    sessKey(left).localeCompare(sessKey(right)));
  /* Everything a reader can see about a row. Two sessions of one harness in
     one state under one title render byte-identical links: the session key is
     in the href and in a data attribute, and neither is on screen, so the
     reader picks one of two and finds out which by reading the tab it opens.
     Only the rows that collide carry the sid, because a key beside a name
     that is already unique is noise on every other board.

     On the meta line rather than appended to the title: line 1 is clipped to
     one line, so a sid on the end of it is the first thing truncated -- and
     with the sid off the title the equality that stamps `data-next-withheld`
     holds again on a title-less twin, which it did not before. */
  const face = session => [String(session.harness || ""), String(session.state || ""),
    String(session.title || "").trim()].join("\u0000");
  const faces = rows.map(face);
  const hoisted = nextCockpitScopeHoistedHarness(group);
  return link("project", nextCockpitScopeLabel(group),
      esc(`${rows.length} ${rows.length === 1 ? "session" : "sessions"}`),
      nextCockpitProjectScopeKind()) +
    rows.map((session, index) => {
      const harness = nextCockpitScopeHarnessLabel(session);
      const twin = faces.some((other, at) => at !== index && other === faces[index]);
      const title = String(session.title || "").trim() || "Session title not published";
      const isWorking = nextCockpitSessionIsWorking(session, group);
      const tone = nextCockpitSessionTone(session, group);
      const state = String(session.state || "unknown");
      const liveDot = isWorking
        ? `<span class="next-project-dot next-project-tone--${esc(tone)} next-project-dot--working" role="img" aria-label="${esc(state)}"></span>`
        : "";
      const stateClass = isWorking
        ? "next-cockpit-scope-state next-cockpit-scope-state--working"
        : "next-cockpit-scope-state";
      const age = nextDurationSince(session.last_activity);
      const meta = [
        hoisted ? "" : esc(harness),
        `<span class="${stateClass}">${liveDot}${esc(state)}</span>`,
        age ? esc(age) : "",
        twin ? esc(String(session.sid || "")) : ""
      ].filter(Boolean).join(" \u00b7 ");
      return link(sessKey(session), title, meta,
        nextCockpitSessionScopeKind(session), {isWorking});
    }).join("");
}

function nextCockpitScopeTree(group, focus){
  return `<nav class="next-cockpit-scope-tree" aria-label="Project scope">` +
    nextCockpitScopeHeading(group) +
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
    nextCockpitScopeHeading(group) +
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
        "session output; semantic result not published",
    ] : []),
    `Decisions: ${decisions}`,
    `Captain attention: ${captain.length ? captain.map(item => item.label).join("; ") :
      coverage.state === "complete" ? "None observed" : coverage.label}`,
    `Attention coverage: ${coverage.label} · source ${coverage.source}`,
  ];
  return {outcome,currentFocus,task,active,children,latest,decisions,coverage,text:lines.join("\n")};
}

/* Project scope only, since DRC-4508. The drift block (once the `Held to`
   tab) puts two more typed fields on the session page, and four of them across two bounds (240
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

/* `inert` picks how a control that does not apply is drawn, and the two here
   want different answers. `save` is the field's own verb, so it stays on the
   page and reachable rather than vanishing from under a keyboard reader; it
   refuses the press silently, because the box beside it already shows that the
   draft matches what is stored. `clear` stays `hidden`, because an empty box
   has nothing to clear and no explanation to offer. */
// The field's absence sentence, which the inert `save` is described by. One id
// per field rather than one per page: both fields render at once.
function nextCockpitHeldAbsentId(kind){
  return `next-cockpit-held-absent-${kind}`;
}

/* `describedBy` is emitted only while the control is BOTH inert and has a
   sentence to point at. `aria-disabled` keeps this control in the tab order
   where `hidden` removed it from the page, so a screen-reader user now reaches
   it and would otherwise hear "save, dimmed" and nothing about why. Pointing at
   an id that is not on the page is worse than pointing at nothing, and a field
   holding saved words renders no absence sentence, so the attribute is
   conditional on the sentence rather than on the state alone. */
function nextCockpitHeldControl(action, label, kind, shown, inert, describedBy){
  const off = inert ? ' aria-disabled="true"' : " hidden";
  const why = !shown && inert && describedBy ? ` aria-describedby="${describedBy}"` : "";
  return `<button type="button" data-next-cockpit-action="${action}" data-arg="${kind}"` +
    `${shown ? "" : off}${why}>${label}</button>`;
}

function nextCockpitHeldToggle(field, action, shown, inert){
  const control = field.querySelector(`[data-next-cockpit-action="${action}"]`);
  if(!control) return;
  /* The attribute, not the property, on the inert path. This runs on a
     keystroke with no redraw, so whichever of the two the renderer chose is
     the one already in the DOM and the one that has to be cleared here. */
  if(!inert){ control.hidden = !shown; return; }
  /* The description goes with the state it explains. A keystroke makes the
     control live, and leaving the pointer behind would describe an active
     control by the sentence saying its field is empty. */
  const absent = field.querySelector("[data-next-cockpit-held-absent]");
  if(shown){
    control.removeAttribute("aria-disabled");
    control.removeAttribute("aria-describedby");
    return;
  }
  control.setAttribute("aria-disabled", "true");
  if(absent && absent.id) control.setAttribute("aria-describedby", absent.id);
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
   does not; the only report went to a diagnostic sink no reader sees.

   One sentence per store outcome, chosen from the reply's `outcome` token and
   not from `persisted`, which is one bit for four sentences (decisions.md,
   DRC-4543). Forced live on 2026-09-12: a save the store REFUSED wore the
   `unpersisted` sentence while the store's mtime did not move, so it claimed
   a write and a loss when there had been neither; and a repeat of the last
   revision wore `saved` while the reply's own `revision_count` had not moved.
   The refusal sentence already exists for the HTTP refusals and is as true of
   a store refusal. The two `settle-*` kinds ride this same lane -- one stamp,
   one TTL, one bound -- and are drawn inside the conflict block by
   `nextCockpitConflict`, worded about what has already happened, because the
   handler's own refresh has run by the time the reader can read them. */
const NEXT_COCKPIT_HELD_CUE_LIMIT = 16;
/* How long the armed discard refuses to be confirmed. Above the one second a
   macOS double-click interval can be set to and above the quarter second its
   key-repeat delay starts at, because both gestures deliver the second press
   through this one listener: the click handler is delegated on `document` and
   `renderNext` is synchronous, so the replacement button is already under the
   pointer, carrying the same action, before the second click of a double-click
   is dispatched. Measured on the shipped control: one ordinary double-click
   armed and confirmed, deleting every revision, the stored reading and the
   departure quotations with nothing read in between.

   A floor and not a disabled interval, because a disabled button would move
   focus and the arm is meant to lapse on its own. A press inside it re-arms
   rather than being dropped, so a slip cannot silently undo the deliberate
   press before it, and a held key never accumulates its way to a confirm. */
const NEXT_COCKPIT_DISCARD_DWELL_MS = 1_200;
const NEXT_COCKPIT_HELD_CUES = {
  error: "Not saved. The server refused the write, and your words are still in the box.",
  unpersisted: "Not stored. The store could not be written, so the refresh has already " +
    "dropped these words, and they are still in the box.",
  saved: "Saved as a new revision.",
  unchanged: "Already stored. These words match the saved revision, so no new revision " +
    "was minted.",
  /* "below" in both, and measured rather than reasoned: `nextCockpitConflict`
     draws this cue inside its own `<header>`, immediately after the `<h2>`,
     so the open question it refers to renders after it. Found by
     `HeldToPositionalSentencesTest`, which is the third instance of DRC-4594's
     class and the second one its by-hand sweep missed. */
  "settle-refused": "Not settled. The store refused the mark, so the question below still " +
    "stands as it did.",
  "settle-unpersisted": "Not settled. The store could not be written, so the mark has " +
    "already been dropped and the question below still stands.",
};
/* The one cue sentence this page owns rather than reads.

   A settle that LANDS prints nothing: the block re-renders its own "You
   settled this ... ago" out of the store, which the refresh on the next line
   has not read yet, so there is no published sentence to carry at the moment
   the press is made. Covering only the table above would leave the outcome a
   reader most wants confirmed as the one that says nothing at all. Worded off
   the block's own second sentence, so a reader who hears this recognises what
   they then read. */
const NEXT_COCKPIT_SETTLE_LANDED = "Settled. A direction given after this will raise it again.";
/* The reply's `outcome` token (`annotations.OUTCOMES`) to the cue it earns. An
   unknown token, from a server newer than this page, falls back on
   `persisted`, which keeps its meaning across builds. */
const NEXT_COCKPIT_HELD_OUTCOME_CUES = {
  stored: "saved", unchanged: "unchanged", refused: "error", unwritable: "unpersisted",
};

/* The stamped kind, or nothing once it has expired. Split out from the cue
   below because the discard block reads the kind rather than a sentence: its
   sentences are published (`annotate_discard`) and its armed state is a state
   and not a cue, and both ride this one lane so the block keeps two rows in
   docs/design-reader-state.md rather than four. */
function nextCockpitHeldKind(key){
  const held = nextCockpitHeldStates.get(key);
  if(!held) return "";
  // The same clock and the same window the row controls use, so two cues on
  // one page do not disagree about how long a confirmation is worth.
  if(Date.now() - held.at >= NEXT_CONTROL_STATE_TTL_MS){
    /* The repeat guard goes with the mark. A mark that has lapsed is no longer
       standing, so the next one is a new report rather than a repeat -- a
       reader who walked away, came back to a disarmed control and pressed it
       again needs the warning they were given 30 seconds ago. */
    nextCockpitHeldDrop(key);
    return "";
  }
  return held.kind;
}

function nextCockpitHeldCue(key){
  return NEXT_COCKPIT_HELD_CUES[nextCockpitHeldKind(key)] || "";
}

/* One sentence per marked kind, for the element that draws it and the region
   that carries it (DRC-4564). Two derivations of one cue is how a region comes
   to say something the block never printed, and the discard family's sentences
   are the server's rather than this page's, so the resolver is the only place
   that knows which table a kind belongs to. */
function nextCockpitHeldSentence(kind){
  if(!kind) return "";
  if(kind.startsWith("discard-")){
    const said = (nextData && nextData.annotate_discard) || {};
    return String(said[kind.slice("discard-".length)] || "");
  }
  return NEXT_COCKPIT_HELD_CUES[kind] || "";
}

/* The last sentence written to either region for each standing mark, keyed by
   that mark's own key. A reader who presses save twice against the same
   failing store gets one report of it, not two, and a redraw between the
   presses cannot replay either.

   Keyed rather than one string for the whole page, because the cue sentences
   are field-independent: "Saved as a new revision." is the same characters
   whichever box was saved, so one string suppressed the second field's write
   in the ordinary two-field workflow -- two cues on screen and a single write
   into the region. Dropped with the mark it guards rather than replaced,
   because a lapsed or dismissed arm pressed again is a new warning. */
const nextCockpitAnnouncedCues = new Map();

/* Whose armed warning the assertive region is holding, or nothing. The region
   carries that one warning, so it holds it only while that arm stands.

   Measured in the accessibility tree on a live board: after a completed
   discard the alert node still read "Nothing has been deleted yet" beside a
   status node reading "Discarded ... is gone". The render had already taken
   the paragraph away, so the region was the only place the sentence survived,
   and it was the one saying the act had not happened.

   Retracting costs nothing to say: emptying a region is a removal, and
   `aria-relevant` does not cover removals, so taking the warning back is
   silent where writing it was not. */
let nextCockpitArmedAnnouncedKey = null;

function nextCockpitRetractArmed(key){
  if(nextCockpitArmedAnnouncedKey === null) return;
  if(key != null && key !== nextCockpitArmedAnnouncedKey) return;
  const region = nextCockpitCueAlert(document.getElementById("app"));
  if(region) region.textContent = "";
  nextCockpitArmedAnnouncedKey = null;
}

/* One drop, all three lanes. Four of the six sites that drop a mark did not
   clear the guard while it was a single string, and this file, the
   reader-state inventory and the commit that introduced it all said they did;
   a helper is the shape that cannot drift apart again. The delete inside
   `nextCockpitHeldMark` is deliberately not routed through it: that one
   re-stamps a mark rather than dropping it, and clearing the guard there would
   be the repeat the guard exists to stop. */
function nextCockpitHeldDrop(key){
  nextCockpitHeldStates.delete(key);
  nextCockpitAnnouncedCues.delete(key);
  nextCockpitRetractArmed(key);
}

function nextCockpitAnnounceCue(key, sentence, assertive){
  if(!sentence || nextCockpitAnnouncedCues.get(key) === sentence) return;
  const app = document.getElementById("app");
  const region = assertive ? nextCockpitCueAlert(app) : nextCockpitCueStatus(app);
  /* Recorded after the write, not before it. A sentence marked announced
     against a region that could not be built would be suppressed for the life
     of the tab having reached nobody. */
  if(!region) return;
  region.textContent = sentence;
  nextCockpitAnnouncedCues.set(key, sentence);
  if(assertive) nextCockpitArmedAnnouncedKey = key;
  /* Bounded on the same count as the marks. Most entries are dropped with
     their mark, but the settle that lands drops its mark and then announces,
     so one key per settled session would otherwise outlive every mark. */
  while(nextCockpitAnnouncedCues.size > NEXT_COCKPIT_HELD_CUE_LIMIT){
    nextCockpitAnnouncedCues.delete(nextCockpitAnnouncedCues.keys().next().value);
  }
}

function nextCockpitHeldMark(key, kind){
  // Deleted and re-set to move the key to the end of the insertion order the
  // eviction below reads. Not a drop; see `nextCockpitHeldDrop`.
  nextCockpitHeldStates.delete(key);
  nextCockpitHeldStates.set(key, {kind, at: Date.now()});
  while(nextCockpitHeldStates.size > NEXT_COCKPIT_HELD_CUE_LIMIT){
    nextCockpitHeldDrop(nextCockpitHeldStates.keys().next().value);
  }
  /* Pushed from here rather than from the render: this is the one point all
     four cue families pass through, it runs before the render that follows,
     and it fires once per press where a render fires on every fallback poll.
     Assertive for the arm alone; see the region factories for why.

     The outcome retracts the warning before it reports: this is the site that
     replaces an arm rather than dropping one, so `nextCockpitHeldDrop` never
     runs on it, and the sentence it leaves standing says nothing has been
     deleted yet. */
  if(kind !== "discard-armed") nextCockpitRetractArmed(key);
  nextCockpitAnnounceCue(key, nextCockpitHeldSentence(kind), kind === "discard-armed");
}

function nextCockpitHeldField(session, annotation, spec, cap){
  const [kind, label, valueKey, whyKey, placeholder] = spec;
  const key = nextCockpitHeldKey(session, kind);
  const saved = String(annotation && annotation[valueKey] || "");
  const draft = nextCockpitHeldDrafts.has(key) ? nextCockpitHeldDrafts.get(key) : saved;
  const why = String(annotation && annotation[whyKey] || "");
  const cue = nextCockpitHeldCue(key);
  return `<div class="next-cockpit-held-field" data-next-cockpit-held-field="${kind}">` +
    '<div class="next-cockpit-held-heading">' +
    `<span class="next-cockpit-held-label">${kind === "goal" ? "GOAL" : label}</span>` +
    (kind === "goal" ? nextPromptSourceLine(annotation) + nextPromptAdoptControls(session) : "") +
    '</div>' +
    `<textarea maxlength="${cap}" data-next-cockpit-held-kind="${kind}" ` +
    `data-next-cockpit-held-key="${esc(key)}" data-next-cockpit-held-saved="${esc(saved)}" ` +
    `data-next-focus="${esc(key)}" placeholder="${esc(placeholder)}">${esc(draft)}</textarea>` +
    `<span class="next-cockpit-held-count" data-next-cockpit-held-count="${kind}">` +
    `${draft.length}/${cap}</span>` +
    nextCockpitHeldControl("held-clear", "clear", kind, Boolean(draft), false) +
    nextCockpitHeldControl("held-save", "save", kind, draft !== saved, true,
      why ? nextCockpitHeldAbsentId(kind) : "") +
    /* The absence sentence answers "why is this empty", so it goes when the
       box stops being empty. It read the SERVER value alone, which put "No
       goal typed for this session." directly under the sentence the reader
       was in the middle of typing. */
    /* Rendered and hidden rather than rendered conditionally, for the reason
       the input handler gives: a keystroke does not redraw, so a paragraph
       that only the renderer can remove stays under the sentence being
       typed. */
    (why ? `<p class="next-cockpit-held-absent" id="${nextCockpitHeldAbsentId(kind)}" ` +
      `data-next-cockpit-held-absent="${kind}"` +
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
   Demonstrated work results come from `_work_evidence` on Pi, and on Claude
   Code from `claude_tool_reports`: the checks a session ran and the files it
   wrote, each result as the tool reported it. On Codex the rows above are
   instructions, dispatches and gate decisions and never an inspected file,
   test or deliverable. Without the sentence an empty list reads as "no work
   was done" rather than "that path was never taken here". */
function nextCockpitWorkEvidenceLimit(harness){
  const label = nextHarnessLabels().get(harness) || nextCockpitHumanLabel(harness);
  if(harness === "pi") return `${label} publishes demonstrated work results, and they are read here.`;
  if(harness === "claude"){
    /* The route's own sentence says what a reading sends of them and to whom,
       or that it sends none, so the line under the checks and the disclosure
       beside the button cannot word it two ways. */
    const route = nextReadingRoute({harness});
    const sent = route && route.provider ? String(route.tool_output || "") : "";
    return `${label} records the checks a session ran and the files it wrote, and they are ` +
      "listed here. A result is what the tool reported; Cargento inspects no file, test or " +
      "deliverable." + (sent ? ` ${sent}` : "");
  }
  return `${label} publishes no demonstrated work results. Cargento reads those on Pi ` +
    "alone, so nothing above is an inspected file, test or deliverable.";
}

/* The reading's Expected Output limit, apart from the record's own line. On
   Claude Code it is lifted only where the route names where the checks go, so
   a reading can carry them after the reader allows tool output, under item 7 of
   [DEC-23](docs/design-reading-a-session.md#dec-23-a-claude-code-sessions-record-of-its-checks-may-show-the-work).
   Where it cannot name that, no check is sent and the demotion stays. */
function nextReadingOutputLimit(harness){
  if(harness === "pi") return "";
  if(harness !== "claude") return nextCockpitWorkEvidenceLimit(harness);
  const label = nextHarnessLabels().get(harness) || nextCockpitHumanLabel(harness);
  const route = nextReadingRoute({harness});
  if(route && route.provider && route.destination) return "";
  if(route && route.provider){
    return `${label} records the checks a session ran, but Cargento cannot name where ` +
      `${route.label} would send them, so no check is sent and a reading cannot judge an ` +
      "expected output here.";
  }
  return `${label} records the checks a session ran, but no reading can carry them here, so ` +
    "a reading cannot judge an expected output here.";
}

/* A check's or a written path's own line under its summary: who, what, and
   what the tool reported, in the design's actor · meta form. The result words
   say where the result came from, because "passed" from an error flag and
   "passed" from a summary line are different strengths of the same claim. */
const NEXT_COCKPIT_CHECK_RESULTS = {
  "failed flag": "failed, as the tool reported",
  "passed flag": "passed, as the tool reported",
  "failed summary": "failed, per its summary line",
  "passed summary": "passed, per its summary line",
  "failed marker": "failed, per a failure line in its output",
};

function nextCockpitToolReportLine(entry){
  if(entry.subject !== "check") return "Agent · file written";
  const parts = ["Agent", "check", NEXT_COCKPIT_CHECK_RESULTS[`${entry.result} ${entry.resultSource}`]
    || "ran, result not recorded"];
  if(entry.earlierFailed) parts.push("an earlier run failed");
  if(entry.beforeLastChange) parts.push("before the last change");
  return parts.join(" · ");
}

/* What the whole scan found, from the counts `claude_tool_reports` publishes
   beside the rows. Every figure here is the full scan, never the listed rows:
   a dropped entry must not turn into "no check" or into a reassurance, as
   item 4 of the same ruling requires. A background launch is named, because a background run
   records no result and a sentence that said no check ran would be false. */
function nextCockpitCheckScan(scan){
  if(!scan || typeof scan !== "object") return "";
  const count = (n, one, many) => `${n} ${n === 1 ? one : many}`;
  const runs = nextNumber(scan.check_runs) || 0;
  const background = nextNumber(scan.background) || 0;
  const written = nextNumber(scan.written_paths) || 0;
  const other = nextNumber(scan.other_commands) || 0;
  const more = nextNumber(scan.more) || 0;
  const outside = nextNumber(scan.outside_paths) || 0;
  if(!runs && !background && !written && !other && !outside){
    return "No check ran in the part of the transcript read.";
  }
  /* The latest results, always, so a failure is never left for the listed
     rows alone to carry; the files are a sentence of their own, so they never
     read as a latest-run result (review and verifier, 2026-09-24). */
  const checks = runs
    ? `${count(runs, "check run", "check runs")} across ` +
      `${count(nextNumber(scan.distinct_checks) || 0, "distinct check", "distinct checks")}; ` +
      `latest runs: ${nextNumber(scan.failed) || 0} failed, ` +
      `${nextNumber(scan.not_recorded) || 0} with no recorded result, ` +
      `${nextNumber(scan.passed) || 0} passed`
    : "no check in the foreground";
  const files = [];
  if(written) files.push(count(written, "file written", "files written"));
  if(outside){
    files.push(`${count(outside, "file", "files")} written outside the working directory`);
  }
  const counted = [];
  if(background){
    counted.push(`${count(background, "background launch", "background launches")}, ` +
      "because a background run records no result");
  }
  if(other) counted.push(count(other, "other shell command", "other shell commands"));
  return `From the part of the transcript read: ${checks}.` +
    (files.length ? ` ${files.join(", ").replace(/^./, c => c.toUpperCase())}.` : "") +
    (counted.length ? ` Counted and not listed: ${counted.join("; ")}.` : "") +
    (more ? ` Failures are listed first, and ${more} more are counted and not listed.` : "");
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
  /* The window bounds the other rows only. A check or a written file is one
     of at most twelve the reader chose failures first, and trimming them to
     the most recent would hide a listed failure (review, 2026-09-24). */
  const others = all.filter(row => row.type !== "tool_report").slice(-NEXT_COCKPIT_WORK_ROWS);
  const entries = all.filter(row => row.type === "tool_report" || others.includes(row));
  const otherTotal = all.filter(row => row.type !== "tool_report").length;
  const reports = entry.data.sources && entry.data.sources.work &&
    entry.data.sources.work.tool_reports;
  const scan = (Array.isArray(reports) ? reports : []).find(row => row && sessKey(row) === key)
    || null;
  if(entries.length){
    return {entries, all, scan, state: "read", shown: others.length, total: otherTotal};
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
    return {entries, all, scan, state: "partial", scanned: nextNumber(
      entry.data.sources.observer && entry.data.sources.observer.live),
      omitted: omittedRows.length};
  }
  return {entries, all, scan, state: "empty"};
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
        subject: String(fact.subject || ""),
        result: String(fact.result || ""),
        resultSource: String(fact.result_source || ""),
        earlierFailed: fact.earlier_failed === true,
        beforeLastChange: fact.before_last_change === true,
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
    const report = entry.type === "tool_report"
      ? `<span class="next-cockpit-work-result">${esc(nextCockpitToolReportLine(entry))}</span>`
      : "";
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
      `</span>${report}</div>`;
  }).join("");
  return '<section class="next-cockpit-work" data-next-cockpit-work>' +
    '<header><h2>OBSERVED RECORD</h2></header>' +
    (rows || '<p class="next-cockpit-work-absent">' +
      `${esc(nextCockpitWorkAbsence(source))}</p>`) +
    (entries.length ? `<p class="next-cockpit-work-mix">${esc(nextCockpitWorkMix(entries))}</p>`
      : "") +
    (source.scan ? `<p class="next-cockpit-work-checks">${esc(nextCockpitCheckScan(source.scan))}` +
      "</p>" : "") +
    (source.shown != null && source.shown < source.total
      ? `<p class="next-cockpit-work-dropped">Showing the ${source.shown} most recent of ` +
        `${source.total} ${entries.some(row => row.type === "tool_report")
          ? "other observed entries, and every listed check and file" : "observed entries"}` +
        ".</p>" : "") +
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

function nextCockpitObserverModel(group, focus = nextCockpitFocusedSession(group)){
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
/* Rule 7 stopped keying on WHO wrote an entry on 2026-09-10 and this sentence
   did not follow it. It told the reader every cited entry was written by the
   agent, directly above an evidence line naming her own message -- self
   contradicting on one row, and wrong in the direction that flatters the
   agent. */
const NEXT_READING_ASSISTANT_ONLY =
  "Nothing cited here demonstrates that the requested output exists; each entry describes " +
  "or asks for the work rather than showing it.";
const NEXT_READING_UNCITED =
  "Nothing resolvable was cited, so there is no entry to read this against.";
const NEXT_READING_BASELINE_OPEN =
  "You have given a later direction that is still unsettled, so this reads against a baseline " +
  "that may not be the one you want.";
/* The published shape, spelt once on each side. `reading.ASSESSMENT_KEYS`
   and `reading.CRITERION_KEYS` carry the same members and
   `ReadingVocabularyIsSpeltOnceTest` compares them, because the measured
   failure here is a producer and a renderer disagreeing about a key name
   and neither one noticing. */
const NEXT_READING_ASSESSMENT_KEYS = ["goal_source", "goal_source_at", "revision_read", "revision_read_at", "read_at", "stamp", "cutoff",
  "scope", "scope_text", "ended_at_read", "criteria"];
const NEXT_READING_CRITERION_KEYS = ["result", "cites", "detail", "clause", "why"];
/* Said in two places now, the criterion row and the disclosure, so it is a
   constant. It is deliberately narrower than "nothing typed": `_criterion`
   coerces a missing clause to "", so this board cannot tell an empty field
   from a producer that did not carry the words. */
const NEXT_READING_CLAUSE_UNRETAINED =
  "the words of the revision this reading read are not retained";
const NEXT_READING_UNKNOWN_KEY =
  "This board cannot read the reading it was given: it carries a field this build does not " +
  "know. Nothing from it is shown, because a reading half-read is not a reading.";
/* DRC-4593. FO and Captain are this workflow's words, not the reader's, and
   they were rendered for months with no definition anywhere on the page. The
   state names themselves stay verbatim: they are strings a source published,
   and inventing prose about what the agent is doing is a claim the board never
   observed. */
const NEXT_COCKPIT_AUTHORITY_GLOSS =
  "FO is the first officer, the agent driving this workflow; Captain is you.";

/* The one step that lifts both refusals about missing words: nothing typed,
   and what was asked discarded. Page-owned, so it is spelled once. */
const NEXT_READING_SAVE_STEP = "Save a goal above to check for drift.";
const NEXT_READING_NO_WORDS =
  "Nothing has been typed for this session, so there is nothing to read it against. " +
  NEXT_READING_SAVE_STEP;
/* One next step per refusal, as the inert-control rule asks: every other state names what would
   lift it, and this one named nothing. The model state rides on the project
   context, which `nextCockpitLoadContext` fetches again on every new payload
   revision, so the step is the page's own and asks nothing of the reader. */
const NEXT_READING_MODEL_UNREAD =
  "Reading availability has not been read, so no reading can be offered. " +
  "Cargento asks again with the next update.";
const NEXT_READING_PENDING =
  "Checking for drift. This can take up to a minute; the rest of the page stays usable.";
const NEXT_READING_MODEL_OFF =
  "Model calls are off for this run. Restart without --no-observer-model or its alias " +
  "--no-harness-usage to allow a reading.";
/* A build constant, not a run setting, so no flag or press on this page lifts
   it and the sentence names none: it says what it waits on. */
const NEXT_READING_UNAUTHORIZED =
  "Checking for drift is not enabled in this build, because the abstention check that " +
  "gates it has not been recorded. It waits on a later release; nothing on this page lifts it.";
/* `--no-annotations`: the check stays on the page, inert, and this is its one
   refusal ([NUI-18](docs/design-next-ui.md#nui-18-one-control-primitive-and-an-inert-control-stays-on-the-page)).
   It replaces the field section's own sentence rather than repeating it. */
const NEXT_READING_ANNOTATIONS_OFF =
  "Annotations are off for this run. Start without --no-annotations to type a goal and an " +
  "expected output here.";
/* Which kind of absence each refusal is, held beside the sentences rather than
   recovered from them at render. One paragraph class prints all four and a
   regex over the prose would re-derive what the producer already knows. The
   discard sentence is deliberately not in here: it comes from the server, so
   this page cannot classify it, and an unmapped sentence renders with no
   attribute rather than with a guessed one. */
/* Who reads a session is the server's route for its harness (DRC-4650). A
   payload without one names no receiver, and a press under no named receiver
   is the one this disclosure exists to prevent, so the page offers none. */
const NEXT_READING_ROUTE_UNREAD =
  "Who would read this session is not published, so no check is offered. " +
  "Cargento asks again with the next update.";
const NEXT_READING_PROVIDER_CHANGED =
  "The reader for this session changed since this page was drawn, so nothing was sent; " +
  "read who reads it now and press again.";
const NEXT_READING_DESTINATION_CHANGED =
  "Where tool output would go changed since this page was drawn, so nothing was sent; " +
  "read where it goes now and press again.";
const NEXT_READING_REFUSAL_ABSENCE = new Map([
  [NEXT_READING_ROUTE_UNREAD, "not-observed"],
  [NEXT_READING_NO_WORDS, "waiting-on-you"],
  [NEXT_READING_MODEL_UNREAD, "not-observed"],
  [NEXT_READING_MODEL_OFF, "run-config"],
  [NEXT_READING_UNAUTHORIZED, "run-config"],
  [NEXT_READING_ANNOTATIONS_OFF, "run-config"],
]);
/* Never on a paragraph that is not an absence. `.next-cockpit-reading-why`
   also carries rules, offers and results, and tagging all of its emissions
   would make the attribute a structurally-present default that measures
   nothing about the session. */
function nextAbsenceAttr(kind){
  return kind ? ` data-absence="${kind}"` : "";
}

const NEXT_READING_DERIVED_ONLY =
  "Rests only on Cargento's own summary of this session, which is not evidence about it.";
const NEXT_READING_OWN_WORDS_ONLY =
  "Rests only on what you asked for, which is the request rather than the work.";
const NEXT_READING_MALFORMED =
  "The reading did not return a usable result for this constraint.";
/* Rule 5 as the reading stored it. The limit row used to come from TODAY's
   harness alone, so a stored Expected Output row re-read after the harness
   table moved rendered as a model verdict rather than a constraint that was
   never put to the model. Phrased in the limit's own register because it
   renders in the limit's slot. */
const NEXT_READING_NOT_ASKED =
  "This constraint was not put to the reading when it was made, so no verdict on it was " +
  "asked for.";
/* Rule 4's backstop fired in the producer. The page has no word list of its
   own -- the prose it would check renders only under a departure, which the
   demotion has already taken away -- so this is the one reason it cannot
   re-derive and must take from the store. */
const NEXT_READING_VERDICT_STATED =
  "The reading's explanation stated whether the work landed, which is a verdict the evidence " +
  "read does not license, so its result was withdrawn.";
/* Item 8 of the tool report ruling, as the page re-applies it and as the
   producer stores it (`check-does-not-show-it`). */
const NEXT_READING_CHECK_DOES_NOT_SHOW_IT =
  "The check it cited does not show this: a departure needs its latest run failing, and a " +
  "consistent its latest run passing with no change after it, both after the words you saved.";
/* Only the producer knows which failed checks the prompt had no room for, so
   this one is read from the store and never re-derived. */
const NEXT_READING_FAILED_CHECK_UNREAD =
  "A check that failed was not read, because the reading had no room for it, so nothing here " +
  "says the output is consistent.";
/* Why a stored row is `not verifiable`, token to sentence. The producer owns
   the tokens (`reading.WHY_TOKENS`, compared by `ReadingVocabularyIsSpeltOnceTest`)
   and this page owns every sentence, so no producer prose reaches the page
   through the field. Consulted only where this page's own derivation left a
   `not verifiable` row without a reason: the live rules stay authoritative,
   and a stored reason never overrides a result derived from evidence the
   page holds (DRC-4544 item 3). */
const NEXT_READING_STORED_WHY = {
  "not-asked": NEXT_READING_NOT_ASKED,
  "unreadable": NEXT_READING_MALFORMED,
  "uncited": NEXT_READING_UNCITED,
  "no-work-shown": NEXT_READING_ASSISTANT_ONLY,
  "board-quoting-itself": NEXT_READING_DERIVED_ONLY,
  "uncorroborated": NEXT_READING_OWN_WORDS_ONLY,
  "verdict-stated": NEXT_READING_VERDICT_STATED,
  "check-does-not-show-it": NEXT_READING_CHECK_DOES_NOT_SHOW_IT,
  "failed-check-unread": NEXT_READING_FAILED_CHECK_UNREAD,
};

/* Who wrote an evidence entry. A closed set on the person side, because the
   asymmetry in rule 7 turns on it and a truthy check would count every
   unfamiliar type as a person's words. A gate decision is a person's only
   where the source records one. */
function nextReadingPersonAuthored(entry){
  const type = String(entry && entry.type || "");
  if(type === "user_message") return true;
  return type === "gate_decision" && String(entry && entry.by || "").startsWith("person:");
}

/* Which entries demonstrate that work happened, as opposed to describing or
   requesting it. Rule 7 was keyed on WHO wrote an entry and the captain
   amended it on 2026-09-10, because as written it inverted its own reason:
   the reason is "self-report is not evidence of a deliverable", and a
   REQUEST is not evidence of one either. Keyed on authorship, citing the
   reader's own words licensed a `consistent` about her own deliverable while
   citing the actual work result demoted. */
const NEXT_READING_WORK_TYPES = ["work_result", "result", "tool_report"];

function nextReadingDemonstratesWork(entry){
  return NEXT_READING_WORK_TYPES.indexOf(String(entry && entry.type || "")) >= 0;
}

/* `reading.check_supports`, spelt for the entries the page holds: a cited
   tool report carries a verdict only as a check run in the window, failed for
   a departure, passed and not before the last change for a consistent. A
   written path shows a write and no result, so it carries neither. */
function nextReadingCheckSupports(entry, result, windowStart){
  if(String(entry && entry.type || "") !== "tool_report") return true;
  if(entry.subject !== "check") return false;
  const at = nextNumber(entry.at);
  if(at == null || at <= 0 || (windowStart != null && at < windowStart)) return false;
  if(result === NEXT_READING_DEPARTURE) return entry.result === "failed";
  if(result === NEXT_READING_CONSISTENT) return entry.result === "passed" && !entry.beforeLastChange;
  return false;
}

/* The third author, which the page did not have. An observer snapshot is
   Cargento's own paraphrase of the session: counting it as the agent's
   account overstates it, and counting it as a person's words overstates it
   much further. Keyed on the fact type rather than on the `model-derived`
   prefix, because all three observer actor claims are the same paraphrase
   and the prefix catches only one of them. */
function nextReadingAuthor(entry){
  if(nextReadingPersonAuthored(entry)) return "person";
  return String(entry && entry.type || "") === "observer_snapshot" ? "derived" : "agent";
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

/* What a later direction is, and what it is not.

   DETECTED: that you gave one. A person-authored entry in the observed record
   whose time is after the revision you last saved, and after anything you have
   already settled. Both halves are available — `annotation_at` is an epoch and
   every fact carries its own — and `nextReadingPersonAuthored` already owns
   the authorship question, so rule 7 and this cannot disagree about who wrote
   a row.

   NOT DETECTED: whether it conflicts. Deciding that a later instruction
   contradicts your typed goal is a reading of two prose strings, which is
   exactly the model evaluation refused by
   [DEC-15](docs/design-reading-a-session.md#dec-15-the-floor-and-the-overlay)
   and permitted only behind four unmet preconditions by
   [DEC-18](docs/design-reading-a-session.md#dec-18-an-unasked-reading-is-permitted-and-gated-on-delivery-first). So the block asks
   rather than answers, and the reader settles it. A block that claimed to
   detect a semantic conflict would be the false claim this whole tab exists to
   avoid. */
function nextCockpitConflictCandidates(annotation, entries){
  const typedAt = nextNumber(annotation &&
    (["latest-prompt", "first-prompt"].includes(annotation.goal_source)
      ? annotation.goal_source_at : annotation.at));
  if(typedAt == null) return [];
  const settled = nextNumber(annotation && annotation.settled_through);
  const after = settled == null ? typedAt : Math.max(typedAt, settled);
  return (entries || []).filter(entry => {
    const at = nextNumber(entry && entry.at);
    return at != null && at > after && nextReadingPersonAuthored(entry);
  });
}

function nextCockpitReadingCriterion(key, label, clause, raw, entries, limit, unsettled,
    windowStart = null){
  let citations = nextReadingCitations(raw, entries);
  const declared = raw && typeof raw === "object" ? String(raw.result || "") : "";
  const stored = raw && typeof raw === "object" ? String(raw.why || "") : "";
  let limitText = limit || "";
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
  if(result !== NEXT_READING_UNVERIFIABLE && unsettled){
    /* DRC-4511: an unresolved baseline conflict never becomes an agent-drift
       verdict. A demotion rather than a filter over `shape.departures`, for
       the reason the shape-contract comment above gives: filtering would
       leave the word `departure` rendered in the row above it, which is the
       verdict the rule forbids, on screen.

       Keyed on the detected superset — any unsettled later direction — rather
       than on a declared conflict, because over-suppression is the safe
       direction argued for everywhere else by
       [DEC-17](docs/design-reading-a-session.md#dec-17-the-shape-contract). The cost is a suppressed
       departure on a session where the reader steered without contradicting
       themselves, and one click clears it. */
    result = NEXT_READING_UNVERIFIABLE;
    why = NEXT_READING_BASELINE_OPEN;
  }
  if(raw && typeof raw === "object" && Object.keys(raw).some(name =>
      NEXT_READING_CRITERION_KEYS.indexOf(name) < 0)){
    // The same asymmetry one level down, and the same reason.
    result = NEXT_READING_UNVERIFIABLE;
    why = NEXT_READING_MALFORMED;
  }
  if(stored && !Object.prototype.hasOwnProperty.call(NEXT_READING_STORED_WHY, stored)){
    // A reason this build does not know is the unknown-key asymmetry one
    // level further down: the store refuses it whole, so this arm only fires
    // in a tab left open across a server upgrade, and it says so rather than
    // guessing which sentence was meant.
    result = NEXT_READING_UNVERIFIABLE;
    why = NEXT_READING_MALFORMED;
  }
  let droppedCheck = false;
  if(result !== NEXT_READING_UNVERIFIABLE){
    const supporting = citations.filter(entry => nextReadingCheckSupports(entry, result, windowStart));
    droppedCheck = supporting.length < citations.length;
    citations = supporting;
    if(!citations.length){
      result = NEXT_READING_UNVERIFIABLE;
      why = NEXT_READING_CHECK_DOES_NOT_SHOW_IT;
    }
  }
  const fromPerson = citations.filter(nextReadingPersonAuthored);
  const shows = citations.filter(nextReadingDemonstratesWork);
  const authors = citations.map(nextReadingAuthor);
  const derivedOnly = authors.length > 0 && authors.every(name => name === "derived");
  if(key === "output" && result !== NEXT_READING_UNVERIFIABLE && !shows.length){
    /* Rule 7, the Expected Output half, as amended. A verdict about the
       deliverable needs an entry that DEMONSTRATES work. The agent saying it
       finished does not, and neither does the reader's own request. */
    result = NEXT_READING_UNVERIFIABLE;
    why = droppedCheck ? NEXT_READING_CHECK_DOES_NOT_SHOW_IT : NEXT_READING_ASSISTANT_ONLY;
  }
  if(result !== NEXT_READING_UNVERIFIABLE && derivedOnly){
    /* On either constraint: a verdict resting only on Cargento's own
       paraphrase is this board quoting itself. The entry stays citable --
       it is real evidence of what the session said -- it just cannot carry
       a result alone. */
    result = NEXT_READING_UNVERIFIABLE;
    why = NEXT_READING_DERIVED_ONLY;
  }
  if(result === NEXT_READING_CONSISTENT && !citations.some(entry =>
      nextReadingAuthor(entry) === "agent" || nextReadingDemonstratesWork(entry))){
    /* A `consistent` needs something that speaks to what the session DID.
       The reader restating what she wanted is the constraint, not the work,
       so agreeing with it is circular -- and it is the shape a reader is
       most likely to misread as corroboration, because the words match. A
       DEPARTURE on her own words is different and stays: a stated change of
       direction is exactly what that evidence is good for. */
    result = NEXT_READING_UNVERIFIABLE;
    why = droppedCheck ? NEXT_READING_CHECK_DOES_NOT_SHOW_IT : NEXT_READING_OWN_WORDS_ONLY;
  }
  if(result === NEXT_READING_UNVERIFIABLE && !why && !limitText &&
      Object.prototype.hasOwnProperty.call(NEXT_READING_STORED_WHY, stored)){
    /* Only the gap the page's own derivation leaves: a row the producer
       already marked `not verifiable`, with no live rule and no live limit
       explaining why. Rule 5's token draws the limit row, in the limit's
       slot, because a constraint never asked has no evidence line to show;
       every other token is a reason under the result. Today's limit wins
       where both exist, above, because it describes the harness the reader
       is looking at now. */
    if(stored === "not-asked") limitText = NEXT_READING_STORED_WHY[stored];
    else why = NEXT_READING_STORED_WHY[stored];
  }
  // Rule 7, the Goal half. A departure on the agent's own narration stands,
  // because a stated change of direction is what that evidence is good for,
  // and a `consistent` resting only on it says so rather than reading as
  // corroborated.
  /* Three sentences, because one covered two cases and was FALSE for the
     second in the flattering direction: an observer snapshot is Cargento's
     own derived summary, not the agent's account, and calling it the latter
     credits the session with having said something it did not. */
  /* The label item 6 of
     [DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy)
     gives a consistent resting on a check: what the tool reported, never an
     inspection. Named by the check's own command, because the activity list
     does not number its entries yet (its item 11). */
  const reported = result === NEXT_READING_CONSISTENT
    ? citations.find(entry => String(entry.type || "") === "tool_report") : null;
  const restsOn = result !== NEXT_READING_CONSISTENT || fromPerson.length ? ""
    : (authors.indexOf("derived") >= 0
      ? "Rests on the agent's own account and Cargento's derived summary of it, and on " +
        "nothing a person wrote."
      : "Rests on the agent's own account alone.");
  const narration = reported
    ? `Consistent with the check "${String(reported.summary || "")}", as the tool reported; ` +
      "not inspected."
    : restsOn;
  return {
    key, label,
    clause: clause || NEXT_READING_CLAUSE_UNRETAINED,
    clauseKnown: Boolean(clause),
    result,
    /* Only under a departure that survived every rule above. It was set
       unconditionally and rendered whenever truthy, so a declared departure
       that rule 3, 5, 7 or the baseline rule demoted still printed its
       departure prose underneath the demoted result -- the reader saw the
       finding and the refusal of it at once. */
    detail: result === NEXT_READING_DEPARTURE ? String(raw && raw.detail || "") : "",
    why, narration, limit: limitText,
    // Mutually exclusive with `limit`, and never both blank: a row states its
    // evidence or states why it has none.
    evidence: limitText ? [] : citations.map(entry =>
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

/* Built and unexercised, and the tests below are not the contract they look
   like: nothing publishes an `assessment`, so every assertion about these
   seven rules is against an injected fixture rather than a payload
   ([the shape contract](docs/design-reading-a-session.md#dec-17-the-shape-contract)).
   Whoever adds a producer adds the published field with it and re-derives
   these assertions from that field. */
function nextCockpitReadingShape(raw, annotation, entries, limit, unsettled){
  const source = raw && typeof raw === "object" ? raw : {};
  /* Unknown keys are fatal; MISSING keys are not. That asymmetry is the
     whole point. A producer that omits a field renders a reading with less
     in it, which is legible. A producer that emits a field this build does
     not know has diverged from the shape, and the measured way that fails is
     silent and confident: `revisionRead` for `revision_read` yields no stale
     warning plus every criterion captioned with today's typed words under a
     reading of an older revision. A named refusal is worse to look at and
     better to have. */
  const unknown = Object.keys(source).filter(name =>
    NEXT_READING_ASSESSMENT_KEYS.indexOf(name) < 0);
  if(unknown.length){
    return {criteria: [], departures: [], malformed: unknown.slice(0, 4).join(", "),
      revisionRead: null, revisionReadAt: null, stamp: "", cutoff: "", scopeText: ""};
  }
  const rows = source.criteria && typeof source.criteria === "object" ? source.criteria : {};
  const revisionRead = nextNumber(source.revision_read);
  const current = nextNumber(annotation && annotation.revision);
  const historical = revisionRead != null && current != null && revisionRead !== current;
  /* Which constraints the READING read, not which are typed now. Filtering on
     the current annotation meant a field cleared since the reading dropped
     its row and its departure with it, after which the departures block
     rendered "The reading raised no departure from the revision it read" —
     a sentence about a revision whose departure had just been deleted. */
  /* Where the evidence window opened for the revision this reading read,
     the producer's `baseline_at`, so a check before the words cannot carry a
     verdict on either side. */
  const windowStart = nextNumber(["latest-prompt", "first-prompt"].includes(source.goal_source)
    ? source.goal_source_at : source.revision_read_at);
  const criteria = NEXT_READING_CONSTRAINTS
    .filter(([key]) => rows[key] || String(annotation && annotation[key] || "").trim())
    .map(([key, label]) => nextCockpitReadingCriterion(
      key, key === "goal" && ["latest-prompt", "first-prompt"].includes(source.goal_source)
        ? "GOAL FROM YOUR PROMPT" : label, nextCockpitReadingClause(key, rows[key], annotation, historical),
      rows[key], entries, key === "output" ? limit : "", unsettled, windowStart));
  return {
    criteria,
    departures: criteria.filter(row => row.result === NEXT_READING_DEPARTURE),
    revisionRead,
    revisionReadAt: nextNumber(source.revision_read_at),
    promptSource: ["latest-prompt", "first-prompt"].includes(source.goal_source),
    /* Through the same helper the criterion row uses, and filtered the same
       way. Read raw, the disclosure said "nothing typed in that revision" for
       an empty clause while the row beside it said the words were not
       retained: `_criterion` coerces a missing clause to "", so after a store
       round trip the two are indistinguishable and only one of those sentences
       can be honest. */
    readClauses: NEXT_READING_CONSTRAINTS
      .filter(([key]) => rows[key] || String(annotation && annotation[key] || "").trim())
      .map(([key, label]) =>
        [key === "goal" && ["latest-prompt", "first-prompt"].includes(source.goal_source)
          ? "GOAL FROM YOUR PROMPT" : label, nextCockpitReadingClause(key, rows[key], annotation, historical)]),
    stamp: String(source.stamp || ""),
    cutoff: String(source.cutoff || ""),
    /* From the READING, not from the live row. A stored reading describes
       the moment it was taken: keying the scope sentence on today's
       `endKind` made a mid-flight reading start claiming to cover an ending
       it never saw the moment the session stopped. */
    scopeText: String(source.scope_text || ""),
    malformed: "",
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
  /* Before the nothing-typed arm, because a discard record satisfies that one
     too and the wider answer is the less true of the two (DRC-4565). The
     sentence is the server's -- `annotations.DISCARD_SENTENCES.unreadable` is
     the same string `/api/reading` refuses with -- so the block and the route
     behind its button cannot word one state two ways. */
  if(nextAnnotationDiscarded(annotation)){
    /* The server's sentence says why and names no step, so the page adds the
       one that lifts it, as every other refusal here names one
       ([NUI-18](docs/design-next-ui.md#nui-18-one-control-primitive-and-an-inert-control-stays-on-the-page)). */
    const said = (nextData && nextData.annotate_discard) || {};
    const why = String(said.unreadable || "").trim();
    return why ? `${why} ${NEXT_READING_SAVE_STEP}` : NEXT_READING_SAVE_STEP;
  }
  if(!String(annotation && annotation.goal || "").trim() &&
      !String(annotation && annotation.output || "").trim()){
    /* Both sentences are this page's. The route refuses the same state in its
       own words -- `reading.REFUSALS` says "Nothing is typed against this
       session" where this says "has been typed for" -- so unlike the discard
       arm above, which carries the server's string, these two are not the same
       characters and this comment does not claim they are. The second sentence
       exists because the control now renders beside the reason, so a reader
       who is being refused can see the one step that would permit it. */
    return NEXT_READING_NO_WORDS;
  }
  return nextReadingPolicyReason(nextData && nextData.reading);
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
const NEXT_COCKPIT_STEER_BY_HAND = "Raised to you and nowhere else.";
const NEXT_COCKPIT_STEER_BY_HAND_WHY = "Cargento does not write into a session, so steering " +
  "is by hand; the steer box in Console states the same rule about notes you write there.";

/* The section where a raise is reviewed, and it holds two collections rather
   than one (DRC-4514).

   A reading the reader asked for raises departures inside itself; the unasked
   lane raises them on its own, into a durable store, with a different lifetime
   and a different citation vocabulary. Merging them into one list would make a
   citation ambiguous about which collection it belongs to, so each keeps its
   own labelled part. Under it sits what became of the raise and the two counts,
   because a raise and its outcome were two blocks with two counts and nothing
   tying a row to a result.

   The order is the design's, and it is load bearing: what was raised, then how
   it was raised, then the figures, then the ruling. Where it is kept is the
   tab's LAST slot and not this section's -- the design's order ends "the
   departures it raised, then how it landed, then where it is kept", and reading
   those three as five slots inside one section put the Intent-log pointer
   before HOW IT LANDED. `nextCockpitDriftBlock` appends it. */
// Defined where the noun is first used rather than in a glossary nobody
// opens. One sentence each, and each rendered exactly once per panel.
const NEXT_COCKPIT_DEPARTURE_DEFINITION =
  "A departure is a place the record does not match the words you chose.";
const NEXT_COCKPIT_REVISION_DEFINITION = "Each save is a revision.";
const NEXT_COCKPIT_READING_DEFINITION =
  "A reading is one model pass over the record, made only when you press for it.";

/* The lane's rows, counted once and used three times: the delivery part is
   printed only where one of THESE stands, because only this lane raises a
   notification; the figure below must count the rows this section actually
   rendered; and the tab strip's cue must agree with both.

   `departure_checked` and not the list's own length, because an empty list
   is two different facts. The lane publishes `[]` for a session it read and
   found nothing in AND for one it has never reached, and only the first is a
   figure: walked with the switch on and this session unread, "Departures the
   checks run while you were away raised 0" printed four lines under
   "Cargento has not checked this session against what you asked for". The
   switch test in `nextCockpitUnaskedPart` is the same rule one layer out.

   With the lane off the figure is the rows this section actually drew, and
   only where it drew some: `departure_checked` is not consulted there,
   because a switch that is off publishes no capability key and a length read
   off a list `base_session` declares empty on every row would report the
   schema (DRC-4559, the first Measured Invariant). */
function nextCockpitDepartureLaneCount(session){
  const laneOn = Boolean(nextData && nextData.unasked === true);
  const laneRows = Array.isArray(session && session.departures) ? session.departures : null;
  if(!laneRows) return null;
  const counted = laneOn
    ? (laneRows.length > 0 || session.departure_checked === true)
    : laneRows.length > 0;
  return counted ? laneRows.length : null;
}

function nextCockpitDepartures(shape, source, session){
  const reading = nextCockpitReadingDepartures(shape, source, session);
  const lane = nextCockpitDepartureLaneCount(session);
  const laneRows = Array.isArray(session && session.departures) ? session.departures.length : 0;
  /* Once for the section, and only where a departure is drawn: a missing way
     back is worth saying beside the thing it would act on (DRC-4642). */
  /* Drawn only with the unasked lane on or a departure on record. A panel on
     every session of a board whose switch is off, saying nothing was raised by
     a check nobody turned on, is noise (DRC-4543); a raise on record is not,
     whichever way the switch is set (DRC-4559). A reading the reader asked for
     keeps it too, even one that raised nothing: its cutoff is printed here and
     nowhere else, and "raised nothing" is only worth the evidence it read. */
  const onRecord = (reading.count || 0) + laneRows > 0;
  if(!onRecord && !shape && !(nextData && nextData.unasked === true)) return "";
  const limit = nextSessionRaiseControl(session) ? nextDepartureReentryLimit(session) : {raise:""};
  return '<section class="next-cockpit-departures"><header>' +
    '<h2>DEPARTURES RAISED TO YOU</h2>' +
    `<p class="next-cockpit-define">${NEXT_COCKPIT_DEPARTURE_DEFINITION}</p></header>` +
    reading.html +
    nextCockpitUnaskedPart(session) + limit.raise +
    nextCockpitDeliveryPart(session, Boolean(lane)) +
    nextCockpitDepartureCounts(reading.count, lane) +
    `<p class="next-cockpit-reading-why">${NEXT_COCKPIT_STEER_BY_HAND}</p>` +
    nextCockpitWhy("steer-why", "Why no raise goes further", NEXT_COCKPIT_STEER_BY_HAND_WHY) +
    '</section>';
}

/* Where a raise is kept, in the tab's last slot. Separate from the section
   above so the design's order survives: it is a pointer off this tab, like HOW
   IT LANDED is a block of it, and appending it inside the departures section
   put it above HOW IT LANDED at every measured offset. */
function nextCockpitDeparturesKept(){
  return '<p class="next-cockpit-departures-kept"><a href="#n=intent">The Intent log</a> keeps ' +
    'what you saved and what was raised against it after the session leaves the board.</p>';
}

/* What the unasked lane raised, in the section named for it.

   These are the departures actually raised TO the reader, and until now they
   rendered on the session page and nowhere here, so the section titled
   DEPARTURES RAISED TO YOU was the one place they did not appear. The body is
   `next-session.js`'s, verbatim, rather than a second rendering of the same
   fields.

   The claim that nothing watches is conditional on the switch, which it was
   not: with `--unasked-readings` on and two raises standing, this section said
   nothing watches for a departure while the session page listed both. */
function nextCockpitUnaskedPart(session){
  const label = '<span class="next-cockpit-departure-label">' +
    'FROM THE CHECKS RUN WHILE YOU WERE AWAY</span>';
  if(!(nextData && nextData.unasked === true)){
    /* Two sentences and two subjects. The first is about the present and is
       true either way; the second is about the record, and it is printed with
       the rows it is about because the store is read with the lane off and
       every standing raise was already on the wire (DRC-4559). Separate
       paragraphs, so neither can be read as qualifying the other. */
    const rows = Array.isArray(session && session.departures) ? session.departures : [];
    const standing = rows.length ? nextUnaskedDepartureBody(session) : "";
    const why = nextData && nextData.unasked_off_reason === "run-disabled"
      ? "The model off switch refuses unasked checks. Restart with --unasked-readings and without either --no-harness-usage or --no-observer-model to enable them."
      : "Nothing watches for a departure on its own. Start with --unasked-readings to have Cargento check a session against what you asked for while you are away.";
    return '<div class="next-cockpit-departure-part">' + label +
      `<p class="next-cockpit-reading-why" data-absence="run-config">${esc(why)}</p>` +
      (standing
        ? '<p class="next-cockpit-reading-why" data-absence="run-config">' +
          `${esc(NEXT_UNASKED_LANE_OFF_RECORD)}</p>` +
          standing
        : "") + '</div>';
  }
  const body = nextUnaskedDepartureBody(session);
  return body ? '<div class="next-cockpit-departure-part">' + label + body + '</div>' : "";
}

/* What became of the raise, beside the raise. `deliveries` owns every sentence
   and this chooses only whether to print, which is `nextSessionDelivery`'s rule
   and the reason the body is shared with it.

   Two gates, and both were measured missing. `standing` is a departure from the
   unasked lane actually rendered above: without it a default board with no
   departure at all printed "One notification was raised about this session"
   under HOW IT WAS RAISED, four lines below a heading saying nothing watches
   for a departure -- a delivery sentence for a raise that does not exist. And
   the figures come from `delivery_departure` rather than the flat keys, because
   those carry the latest raise of ANY lane: a departure handed over at 10:00
   and an unrelated hook refusal at 11:00 printed the refusal's sentence, in
   amber, beside the raise that got out. `delivery_mixed_why` cannot rescue
   either case -- it says earlier raises ended differently, never that some were
   not about a departure.

   The absence case is not here: it belongs beside a DEPARTURE and rides inside
   `nextUnaskedDepartureBody`, so a session nobody was ever raised about still
   draws nothing at all. */
function nextCockpitDeliveryPart(session, standing){
  if(!standing) return "";
  const scoped = nextDepartureDelivery(session);
  const body = scoped ? nextDeliveryBody(scoped) : "";
  if(!body) return "";
  const outcome = String(scoped.delivery_outcome || "");
  return '<div class="next-cockpit-departure-part" ' +
    `data-next-delivery="${esc(outcome)}"` +
    `${scoped.delivery_mixed === true ? ' data-next-delivery-mixed="true"' : ""}>` +
    '<span class="next-cockpit-departure-label">HOW IT WAS RAISED</span>' + body + '</div>';
}

/* The figures, as labelled lines with no arithmetic between them.

   Attempts and hand-overs are different questions and a ratio answers neither;
   neither is a compliance figure, and nothing here interprets one. Both
   departure figures come from the published lists, which FILTER: the store
   keeps a row for every check, so counting rows would tell a reader that
   fourteen quiet checks were fourteen departures.

   ONE LINE PER COLLECTION, and that is the shared contract's second rule rather
   than a layout choice. This section renders two collections under one heading
   and the figure counted one of them: one departure in each rendered two rows
   above "Departures raised about this session 1", and a reading departure with
   no unasked row rendered a visible row above a 0. Each figure is derived from
   exactly the rows its own part rendered, in the one pass that renders them.

   A figure the payload does not carry says so rather than rendering zero, which
   is the shared contract's first rule -- and the per-session departure line was
   the one exemption from it. On a default board `session.departures` is `[]`
   whether or not the lane ran, so the ternary that read it always produced a
   number: the board printed "Departures raised about this session 0" directly
   under "Nothing watches for a departure on its own". `null` from either
   collection is an unmeasured figure and prints its absence. */
function nextCockpitDepartureCounts(fromReading, fromLane){
  const counts = (nextData && nextData.delivery_counts) || null;
  const board = counts ? nextNumber(counts.raises) : null;
  if(!counts || (fromLane == null && !board)) return "";
  const line = (label, value) =>
    '<div class="next-cockpit-count">' +
    `<span class="next-cockpit-count-label">${esc(label)}</span>` +
    `<span class="next-cockpit-count-value"${value == null ? " data-next-absent" : ""}>` +
    `${esc(value == null ? "not published" : String(value))}</span></div>`;
  /* The quantity noun moves from every label to the group heading above it.
     Five labels each opening with the word the group already supplies is five
     readings of the same word, and the rows are what the reader is scanning.
     The `line()` value arguments are untouched: only the label text moves, so
     the null-to-"not published" branch and the positional value reads that
     assert it are unaffected. */
  const group = (text) => `<span class="next-cockpit-count-group">${esc(text)}</span>`;
  return '<div class="next-cockpit-departure-part">' +
    '<span class="next-cockpit-departure-label">COUNTS</span>' +
    '<div class="next-cockpit-departure-counts">' +
    group("DEPARTURES") +
    line("From the reading you asked for", fromReading) +
    line("From the checks run while you were away", fromLane) +
    group("RAISES") +
    line("On record for this board", board) +
    line("This board attempted", nextNumber(counts.attempted)) +
    line("A notification service accepted", nextNumber(counts.handed_over)) +
    '</div><p class="next-cockpit-reading-why">Five figures, and no arithmetic between ' +
    'them.</p>' +
    nextCockpitWhy("counts-why", "What a count does not say",
      "A count identifies a session worth reading; it establishes nothing about whether " +
      "the brief, the agent or Cargento\u2019s own judgement was poor, and those three are " +
      "not separable from it.") +
    '</div>';
}

/* Returns the part AND the figure for it, in one derivation over one
   collection. Two passes is how the count came to be scoped to a different set
   of rows than the ones drawn (the shared contract's second rule, and the
   DRC-4453 defect class): a caller cannot ask this for a number without the
   markup that number describes. `count` is null on every branch that renders no
   rows because it could not read the collection -- no reading, a reading this
   build cannot parse, or a payload whose observed record has not landed, so the
   citations cannot resolve. */
function nextCockpitReadingDepartures(shape, source, session = null){
  const part = (body) =>
    '<div class="next-cockpit-departure-part">' +
    '<span class="next-cockpit-departure-label">FROM THE READING YOU ASKED FOR</span>' +
    body + '</div>';
  /* Rendered whether or not a reading exists. It carried the ruling's
     sentence that steering is manual and the fact that nothing was raised, and
     both were reachable only through a reading nothing produces, so journey
     step 4 had no surface at all. Saying "no reading has been made, so
     nothing has been raised" needs no model.

     Scoped to a reading the reader ASKED for, because the part below now
     carries the ones nobody asked for and the unqualified sentence was false
     beside them. */
  if(!shape){
    return {count: null,
      html: part('<p class="next-cockpit-reading-why" data-absence="not-observed">No reading ' +
        'has been made at your request, so nothing has been raised from one.</p>')};
  }
  /* An empty departures list had five causes and one sentence, and the
     sentence was the most reassuring of them. `departures` is
     `criteria.filter(result === departure)`, so it is empty when every
     criterion was demoted, and empty again when this page could not resolve
     a single citation because its own evidence fetch has not landed -- on
     that redraw a stored reading holding two real departures rendered as
     "raised no departure", with its own cutoff line underneath vouching for
     how many entries it had read.

     The tree has been bitten by this class once already: the 20-row display
     window did exactly this until the caller was changed to pass `all`. This
     is the residual, and a producer is what finally makes the sentence
     reachable in earnest. */
  /* The kind is a parameter and not a constant on the helper: two of its three
     callers state that nothing was observed, and the third states that a
     reading WAS read and raised nothing. Stamping all three alike would put an
     absence cue on a result. */
  const nothing = (text, count, absence = "") =>
    ({count, html: part(`<p class="next-cockpit-reading-why"${nextAbsenceAttr(absence)}>` +
      `${esc(text)}</p>`)});
  if(shape.malformed){
    return nothing("A reading was made and this board could not read it, so nothing here is " +
      "raised from it.", null, "not-observed");
  }
  if(source && String(source.state || "") !== "read"){
    return nothing("The observed record is not on this page right now, so the entries this " +
      "reading cited cannot be resolved and nothing can be raised from it.", null,
      "not-observed");
  }
  if(!shape.departures.length && shape.criteria.length &&
      shape.criteria.every(row => row.result === NEXT_READING_UNVERIFIABLE)){
    /* Zero and not unmeasured: the reading was read, and it raised nothing.
       The sentence beside the figure is what says the nothing is worth
       nothing. */
    return nothing("This reading verified neither constraint, so it raised nothing and " +
      "confirmed nothing.", 0);
  }
  const rows = shape.departures.map(row =>
    '<div class="next-cockpit-departure">' +
    `<span class="next-cockpit-reading-name">${esc(row.label)}</span>` +
    nextCockpitReadingClauseCell(row) +
    `<em class="next-cockpit-reading-detail">${esc(row.detail || row.result)}</em>` +
    row.evidence.map(line =>
      `<span class="next-cockpit-reading-evidence">${esc(line)}</span>`).join("") +
    (session ? nextDepartureReentry(session) : "") + '</div>').join("");
  /* Once, for the block. It was inside each departure row, which said one
     fact as many times as there were departures and never once when there
     were none — and a reading that raised nothing is exactly the one whose
     cutoff a reader needs, because "nothing was raised" is worth only as much
     as the evidence it was raised against. */
  const cutoff = shape.cutoff
    ? `<p class="next-cockpit-reading-why">${esc(shape.cutoff)}</p>` : "";
  return {
    count: shape.departures.length,
    html: part((rows || '<p class="next-cockpit-reading-why">The reading raised no departure ' +
      'from the revision it read.</p>') + cutoff),
  };
}

/* The offer, and the count beside it.

   Hoisted out of the no-reading branch, where it lived. That put the button
   and the paragraph explaining it inside `if(!raw)`, so the moment ANY
   reading was stored both vanished -- and the shape contract requires the
   press count to render beside the control, which could then only ever have
   shown zero. A reader looking at the amber "revision 3 is current" line had
   no way to ask for a current one. */
/* One reason, read by the control that renders it and by the handler that
   refuses the press: a handler with a second opinion can refuse a press the
   button offered, or take one it refused
   ([NUI-18](docs/design-next-ui.md#nui-18-one-control-primitive-and-an-inert-control-stays-on-the-page)). */
function nextCockpitReadingRefusal(annotation, model){
  /* First, because with the store off there are no words to read and the
     route answers 503 whatever else is true. */
  if(!(nextData && nextData.annotate === true)) return NEXT_READING_ANNOTATIONS_OFF;
  const authorized = nextData && ["passed", "accepted"].includes(nextData.reading_check);
  /* A stored reading outlives the model option. Only the new request is
     gated here; retaining the old account never establishes availability. */
  return nextCockpitReadingStates(annotation, model) || (authorized ? "" :
    NEXT_READING_UNAUTHORIZED);
}

// One block renders per page -- the focused session's -- so the paragraph the
// button points at can carry a constant id, as the discard control's warning
// already does two hundred lines below.
const NEXT_READING_REFUSED_ID = "next-cockpit-reading-refused";

function nextReadingRoute(session){
  const routes = nextData && nextData.reading_routes;
  const route = routes && session ? routes[String(session.harness || "")] : null;
  return route && typeof route === "object" ? route : null;
}

/* Permission is per receiver: a Codex answer never stands in for Claude
   Code's. A payload without the per-provider map predates the second
   provider, and its one answer was Codex's. */
function nextReadingConsent(provider){
  const policy = nextData && nextData.reading;
  if(!policy || !provider) return false;
  const map = policy.providers;
  return map && typeof map === "object"
    ? map[provider] === true : provider === "codex" && policy.consent === true;
}

/* Tool output is its own answer, keyed by where it goes: a words-only Allow,
   or one given for another destination, never covers it (item 7 of the tool
   report ruling). */
function nextReadingToolOutputGranted(route){
  const policy = nextData && nextData.reading;
  const map = policy && policy.tool_output;
  const granted = map && typeof map === "object" && route ? map[String(route.provider)] : null;
  return Array.isArray(granted) && granted.includes(String(route.destination));
}

function nextReadingNeedsAllow(route){
  if(!route || !route.provider) return false;
  return !nextReadingConsent(String(route.provider)) ||
    Boolean(route.destination && !nextReadingToolOutputGranted(route));
}

function nextReadingAnyConsent(){
  const policy = nextData && nextData.reading;
  const map = policy && policy.providers;
  return map && typeof map === "object"
    ? Object.values(map).some(value => value === true) : Boolean(policy && policy.consent);
}

function nextReadingRouteRefusal(session){
  const route = nextReadingRoute(session);
  if(!route) return NEXT_READING_ROUTE_UNREAD;
  return route.provider ? "" : String(route.note || NEXT_READING_ROUTE_UNREAD);
}

function nextReadingPolicyReason(policy){
  if(!policy) return NEXT_READING_MODEL_UNREAD;
  if(policy.reason === "run-disabled") return NEXT_READING_MODEL_OFF;
  if(policy.reason === "store-unavailable") return "Reading permission or its daily budget could not be read or saved. Restore access to the Cargento store before checking.";
  if(policy.reason === "daily-cap"){
    const at = nextNumber(policy.retry_at);
    return at == null ? "The daily reading limit is reached. Wait for the next update."
      : `The daily reading limit is reached. Try again after ${new Date(at * 1000).toLocaleString()}.`;
  }
  return "";
}

function nextCockpitReadingControl(session, annotation, model, primary = true){
  const reason = nextPromptReadingRefusal(session, annotation, model);
  const key = sessKey(session);
  let request = nextCockpitReadingRequests.get(key);
  /* A refusal is a state, not an event, and it stops being true the moment the
     reader does what it asks. Dropped as soon as that state has gone: one that
     nothing clears leaves "Nothing has been typed for this session" standing
     under a button that is no longer refused, which is the board asserting an
     absence after it stopped being true. A response is an event and is kept --
     "Reading received." describes a press that happened, not a state. */
  if(request && request.refusal && request.message !== reason){
    nextCockpitReadingRequests.delete(key);
    request = undefined;
  }
  const pending = request && request.pending;
  const route = nextReadingRoute(session);
  const provider = route && route.provider ? String(route.provider) : "";
  const confirming = Boolean(provider && request && request.consent && nextReadingNeedsAllow(route));
  /* `authorized` is no longer a second term here: an unauthorized check is
     one of the sentences `nextCockpitReadingRefusal` returns, so `!reason`
     already carries it. */
  const enabled = !reason && !pending;
  const count = nextNumber(annotation && annotation.reading_count) || 0;
  const spent = `${count} model request${count === 1 ? "" : "s"} recorded for this session.`;
  /* Before the button, not after the press: the route's disclosure, naming
     this session's own receiver, whose capacity is spent and where the words
     go. The offer paragraph in the reading scopes WHAT is sent and says
     nothing about where it goes or who pays. With no provider there is no
     disclosure and no offer: the route's sentence says why, as the refusal
     below. */
  const disclosure = provider && route.disclosure
    ? `<p class="next-cockpit-reading-why">${esc(route.disclosure)}</p>` : "";
  /* `aria-disabled` rather than `disabled`, so the control keeps its place in
     the tab order and its reason is announced. The press this lets back in is
     refused by `nextCockpitAskForReading`, on the reason computed above. */
  /* The page's one primary, unless the session is blocked on the reader: then
     the raise holds it when offered, nothing does otherwise, and this sits
     below as an ordinary control
     ([DEC-20](docs/design-reading-a-session.md#dec-20-the-first-screen-shows-goal-beside-direction-and-drift-has-one-home)).
     The four cockpit tabs have no action to mark at all (DRC-4590, DRC-4603). */
  /* The disclosure and the button share a row, the disclosure still first in
     reading order: stacked, the disclosure's five sentences pushed the button
     under a 900px first screen, measured on a live board at 1440 wide. */
  return '<div class="next-cockpit-reading-ask">' + disclosure +
    `<button type="button" class="next-action${primary && provider ? " next-action--primary" : ""}" ` +
    `data-next-cockpit-action="${confirming ? 'reading-allow' : 'reading-ask'}" ` +
    `data-next-focus="reading:${esc(sessKey(session))}"` +
    `${enabled ? "" : ' aria-disabled="true"'}` +
    `${reason ? ` aria-describedby="${NEXT_READING_REFUSED_ID}"` : ""}>` +
    `${pending ? "Checking for drift…" : confirming ? "Allow and check" : "Check for drift"}</button>` +
    (nextReadingAnyConsent()
      ? '<button type="button" class="next-action" data-next-cockpit-action="reading-off">Turn off readings</button>' : "") +
    '</div>' +
    (request && request.message && !request.refusal
      ? '<p class="next-cockpit-reading-why" role="status"' +
        `${nextAbsenceAttr(NEXT_READING_REFUSAL_ABSENCE.get(request.message))}>` +
        `${esc(request.message)}</p>` : "") +
    /* Only from a published annotation: with the store off there is no count
       to read, and "0 requests" would be a default standing in for one. */
    (annotation ? `<span class="next-cockpit-reading-count">${esc(spent)}</span>` : "") +
    /* The announcement and the description are one node while a refusal
       stands. Printing the stored message and the reason separately rendered
       the same sentence twice, adjacent and identical, where the contract is
       that it renders exactly once. The press is still announced, because this
       node carries `role="status"` when it is the refusal. */
    (reason
      ? `<p class="next-cockpit-reading-why"${request && request.refusal ? ' role="status"' : ""}` +
        ` id="${NEXT_READING_REFUSED_ID}"` +
        `${nextAbsenceAttr(NEXT_READING_REFUSAL_ABSENCE.get(reason))}>${esc(reason)}</p>`
      : "");
}

/* "below", and the word is kept rather than dropped. DRC-4594 moved OBSERVED
   RECORD to the end of this tab and left both of these sentences claiming the
   side they used to have; the tempting repair is to delete the positional word
   from each, after which the sweep that found them returns nothing and passes
   forever. `HeldToPositionalSentencesTest` reads the direction each one states
   and compares rendered indices, so a true word is what keeps it measuring. */
const NEXT_READING_OFFER =
  "A reading is a model\u2019s account of the evidence on this page: the observed record below " +
  "and the goal and output you saved, and nothing else. It does not read a diff, a file, a test or a " +
  "deliverable.";

function nextCockpitReadingBaseline(shape){
  /* What the reading actually read, verbatim, rather than only which revision
     it was. Naming the revision says a reading is historical; it does not let
     the reader see what it said, and a reading of revision 1 sitting beside
     today's revision 3 invites them to assume the words on screen are the ones
     it read. The text was always on the wire as each criterion's clause.

     A disclosure rather than open prose: this is reference for a reader who
     doubts the reading, not part of it, and the block is long already. */
  if(shape.revisionRead == null) return "";
  const typed = shape.revisionReadAt != null
    ? `${shape.promptSource ? "saved" : "typed"} ${esc(fmtDur(Math.max(0, (nextData && nextData.generated || 0) - shape.revisionReadAt)))} ago`
    : (shape.promptSource ? "when it was saved was not recorded" : "when it was typed was not recorded");
  const rows = (shape.readClauses || []).map(([label, clause]) => {
    /* One wording with the criterion row, from one place. This board cannot
       tell "the reader typed nothing" from "the producer did not carry the
       words", so it says the narrower thing that is true of both. */
    const body = clause
      ? `<span class="next-cockpit-reading-clause">${esc(clause)}</span>`
      : '<span class="next-cockpit-reading-clause-absent">' +
        NEXT_READING_CLAUSE_UNRETAINED + "</span>";
    return `<div class="next-cockpit-reading-criterion-clause">` +
      `<span class="next-cockpit-source">${esc(label)}</span>${body}</div>`;
  }).join("");
  return `<details${nextCockpitDisclosureAttr("reading-baseline")}>` +
    `<summary>What it read: revision ${shape.revisionRead}, ${typed}</summary>` +
    rows + "</details>";
}

/* The three parts in the page's order, joined. The drift block places them
   apart, with the conflict and the caveats between the reading and the
   departures; this joined form is for a caller that wants one block. */
function nextCockpitReading(session, annotation, entries, model, observed, unsettled, source,
    primary = true){
  const parts = nextCockpitReadingParts(session, annotation, entries, model, observed, unsettled,
    source, primary);
  return parts.control + parts.reading + parts.departures;
}

/* The control is its own part so it can sit on the first screen, directly
   under the direction, with the reading and its caveats below it (DRC-4639).
   Every arm returns the same control; only the reading varies. */
function nextCockpitReadingParts(session, annotation, entries, model, observed, unsettled, source,
    primary = true){
  const control = '<div class="next-session-drift-check">' +
    nextCockpitReadingControl(session, annotation, model, primary) + '</div>';
  const header = '<section class="next-cockpit-reading"><header><h2>READING</h2>';
  const limit = nextReadingOutputLimit(String(session.harness || ""));
  const raw = annotation && annotation.assessment;
  const withheld = String(annotation && annotation.reading_withheld || "");
  /* `defined` rather than sniffing the composed body: the no-reading arm
     already renders NEXT_READING_OFFER, which says what a reading is at more
     length, and a second sentence saying the same thing is a regression
     rather than a fix. Every other arm needs the short one. */
  const close = (body, shape, defined) => ({control,
    reading: `${header}</header>` +
      (defined ? "" : `<p class="next-cockpit-define">${NEXT_COCKPIT_READING_DEFINITION}</p>`) +
      `${body}</section>`,
    departures: nextCockpitDepartures(shape, source, session)});
  /* A press that produced nothing is not the same as no press, and the
     reason it produced nothing is a sentence the producer chose from a
     closed set rather than one this page infers. */
  const why = withheld ? `<p class="next-cockpit-reading-why">${esc(withheld)}</p>` : "";
  /* A reading already made renders whatever the model's state is now. The
     states below are about offering a NEW one, and a retained reading
     outliving the run that produced it is the whole point of storing it.
     The CONTROL hoists out of this branch; this check does not, and
     conflating the two made a stored reading disappear the moment the
     observer model was switched off. */
  if(!raw){
    /* No early return on a reason: the control renders in all four of them and
       prints the reason after the button, so the sentence moves rather than
       going. This supersedes the withheld-offer ruling
       ([NUI-18](docs/design-next-ui.md#nui-18-one-control-primitive-and-an-inert-control-stays-on-the-page)). */
    /* A reading the store refused on read-back is not a session nobody
       pressed on. `readings` survives a refusal, so without this the block
       said "N readings asked for" above "No reading has been made" and left
       the difference unaccounted for. The JS refusal below cannot reach this:
       the validator nulls the assessment before the page ever sees it, so
       that arm only fires in a tab left open across a server upgrade. */
    const refused = annotation && annotation.reading_refused === true
      ? '<p class="next-cockpit-reading-why">A reading is stored for this session and this ' +
        "build could not read it, so nothing from it is shown. Asking again replaces it." +
        "</p>"
      : "";
    /* Said once. The send disclosure beside the control already ends on the
       server's "never a verification that the work was done", so the page's
       own wording rides here only where no disclosure was published. */
    const routed = nextReadingRoute(session);
    const verification = routed && routed.provider && routed.disclosure
      ? "" : ` ${NEXT_READING_NOT_A_VERIFICATION}`;
    const offer = `<p class="next-cockpit-reading-why">${NEXT_READING_OFFER}${verification}</p>`;
    return close(refused + offer + why, null, true);
  }
  const shape = nextCockpitReadingShape(raw, annotation, entries, limit, unsettled);
  if(shape.malformed){
    /* A refusal is a substitution and never an omission: the block still
       renders, names the field it could not read, and draws no verdict of
       any kind. */
    return close(
      `<p class="next-cockpit-reading-why">${esc(NEXT_READING_UNKNOWN_KEY)}</p>` +
      `<p class="next-cockpit-reading-why">Unrecognised: ${esc(shape.malformed)}.</p>`, shape);
  }
  const current = nextNumber(annotation && annotation.revision);
  /* The one warm ink the design allows near a reading, and it is not part of
     one: which revision was read is an observation about revisions. The
     characters are `nextRevisionSuperseded`'s, because the raises below this
     block say the same thing about themselves. */
  const superseded = nextRevisionSuperseded("This reading", shape.revisionRead, current);
  const stale = superseded
    ? `<p class="next-cockpit-reading-stale">${esc(superseded)}</p>`
    : "";
  /* From the reading rather than from the live row. A reading describes the
     moment it was taken, and the producer already agreed with the HOW IT
     LANDED cards next door because both derive the ending the same way and
     a test asserts the two derivations match. */
  const scope = shape.scopeText
    ? `<p class="next-cockpit-reading-why">${esc(shape.scopeText)}</p>` : "";
  return {control,
    reading: header +
      (shape.stamp ? `<span class="next-cockpit-reading-stamp">${esc(shape.stamp)}</span>` : "") +
      '</header>' + `<p class="next-cockpit-define">${NEXT_COCKPIT_READING_DEFINITION}</p>` +
      stale + (shape.promptSource ? '<p class="next-cockpit-reading-why">Baseline from your prompt.</p>' : "") + nextCockpitReadingBaseline(shape) + scope + why +
      shape.criteria.map(nextCockpitReadingCriterionRow).join("") + '</section>',
    departures: nextCockpitDepartures(shape, source, session)};
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
      '<p class="next-cockpit-reading-why" data-absence="not-observed">This session was not ' +
      'in the observed payload, so nothing here says how it ended.</p></section>';
  }
  const landing = observed.landing;
  const card = (title, text, known, note) =>
    '<div class="next-cockpit-landed-card">' +
    `<span class="next-cockpit-landed-label">${title}</span>` +
    `<span class="next-cockpit-landed-value${known ? "" : " next-cockpit-landed-value--absent"}">` +
    `${esc(text)}</span>` +
    (note ? `<span class="next-cockpit-landed-note">${esc(note)}</span>` : "") + '</div>';
  return '<section class="next-cockpit-landed"><header><h2>HOW IT LANDED</h2></header>' +
    '<div class="next-cockpit-landed-cards">' +
    card("END EVIDENCE", landing.endText, landing.endKnown, "") +
    card("WHO CLAIMS IT FINISHED", landing.claimText, landing.claimKnown,
      landing.independentText) +
    '</div><p class="next-cockpit-reading-why">Neither card implies the other. Evidence of ' +
    'an end and a claim of completion are separate questions.</p></section>';
}

/* The block, gated on the annotation alone rather than on a reading existing,
   so a later direction that raises no departure falls out of the layout rather
   than needing a rule. It sits directly under the reading it constrains, below
   the one control, so the control stays on the first screen (DRC-4639).

   The window is the record's own. A direction older than the tail
   `io.read_tail` keeps is not in `entries` and cannot be counted here, so the
   block says what it read rather than implying it read everything: on a long
   session the suppression can release because the evidence aged out, and that
   is a limit to state rather than a bug to hide.

   Three states, and the unread one is not silence. `nextCockpitWorkAbsence`
   owns that wording so the two blocks cannot word it differently. */
function nextCockpitConflict(session, annotation, source){
  const typed = String(annotation && annotation.goal || "").trim() ||
    String(annotation && annotation.output || "").trim();
  if(!typed) return "";
  /* What the last settle press is still worth saying. Its own class rather
     than the held fields' cue class, so the tests that read the first held
     cue on the page never read this one instead. */
  const cue = nextCockpitHeldCue(nextCockpitHeldKey(session, "settle"));
  /* "Conflict to settle" only where there is one: an unsettled later
     direction is what the drift ruling names by that label. Nothing since, a
     settled baseline and an unread record have nothing to settle, and calling
     them a conflict asks the reader to act on nothing
     ([DEC-20](docs/design-reading-a-session.md#dec-20-the-first-screen-shows-goal-beside-direction-and-drift-has-one-home)). */
  const headed = title => '<section class="next-cockpit-conflict"><header>' +
    `<h2>${title}</h2></header>` +
    (cue ? `<small class="next-cockpit-conflict-cue">${esc(cue)}</small>` : "");
  const header = headed("A LATER DIRECTION");
  const steer = '<p class="next-cockpit-conflict-why">Nothing here decides whether it changes ' +
    'what you are asking for. That is yours, and Cargento does not write into the session ' +
    'either way.</p></section>';
  if(source.state !== "read" && source.state !== "empty"){
    return `${header}<p class="next-cockpit-conflict-why">` +
      `${esc(nextCockpitWorkAbsence(source))} So whether you have given a later direction is ` +
      'unknown, not none.</p>' + steer;
  }
  const pending = nextCockpitConflictCandidates(annotation, source.all || source.entries);
  const settledAt = nextNumber(annotation && annotation.settled_at);
  if(!pending.length){
    if(settledAt == null){
      return `${header}<p class="next-cockpit-conflict-why">Nothing you have said since you ` +
        'saved these words is in the observed record read for this session.</p>' + steer;
    }
    const age = nextDurationSince(settledAt);
    const revision = nextNumber(annotation && annotation.settled_revision);
    return `${header}<p class="next-cockpit-conflict-settled">You settled this` +
      `${age == null ? "" : ` ${esc(age)} ago`}` +
      `${revision == null ? "" : `, against revision ${revision}`}. A direction given after ` +
      'that will raise it again.</p>' + steer;
  }
  const rows = pending.slice(-NEXT_COCKPIT_WORK_ROWS).map(entry => {
    const age = nextDurationSince(entry.at);
    return '<div class="next-cockpit-conflict-row">' +
      `<span class="next-cockpit-conflict-text">${esc(entry.summary)}</span>` +
      `<span class="next-cockpit-conflict-at">${esc(age == null ? "time not published" :
        `${age} ago`)}</span></div>`;
  }).join("");
  const count = pending.length;
  return `${headed("CONFLICT TO SETTLE")}<p class="next-cockpit-conflict-open">${count} ` +
    `${count === 1 ? "direction" : "directions"} you gave after you saved the words above, ` +
    'in the part of the record read here.</p>' + rows +
    '<div class="next-cockpit-conflict-choices">' +
    '<button type="button" class="next-action" data-next-cockpit-action="conflict-settle" ' +
    `data-arg="${esc(String(pending[pending.length - 1].at || 0))}" ` +
    `data-next-focus="conflict-settle:${esc(sessKey(session))}">The baseline still applies` +
    '</button>' +
    '<button type="button" class="next-action" data-next-cockpit-action="conflict-retype" ' +
    `data-next-focus="conflict-retype:${esc(sessKey(session))}">Retype the baseline</button>` +
    '</div>' +
    /* Said plainly because the store mints no revision for unchanged text, so
       a reader who re-reads their goal, decides it still stands and saves it
       again would find the block unmoved and no way out of it. The other
       button is that way out. */
    '<p class="next-cockpit-conflict-why">Retyping clears this only if the words change. If ' +
    'they still stand, say so with the other choice.</p>' + steer;
}

/* The act the endpoint has always had and no control reached (DRC-4561).

   Section scope, not field scope: `annotations.clear` drops the whole entry,
   so a control inside the three-column field grid would offer an act it cannot
   perform. Labelled `discard everything` and never `clear` -- the shorter word
   is already printed on the button beside each box for a weaker act on a
   different store, and two buttons in one block carrying one word is the
   defect rather than the fix. SECURITY.md says the same thing in the same
   words.

   Every sentence here is the server's. The success one claims the departure
   store no longer quotes these words, and the page never reads that store, so
   it must not compose the claim.

   Armed by the first press and performed by the second, through the cue lane
   and its 30 second TTL rather than a dialog: the bundle has no dialog
   anywhere, the same block already ships a deliberate two-step for the weaker
   act, and an arm that lapses on its own leaves a reader who walked away with
   a disarmed control. */
function nextCockpitHeldDiscardBlock(session, annotation){
  const said = (nextData && nextData.annotate_discard) || {};
  const key = nextCockpitHeldKey(session, "discard");
  const kind = nextCockpitHeldKind(key);
  const armed = kind === "discard-armed";
  const landed = kind && !armed ? nextCockpitHeldSentence(kind) : "";
  const warning = armed ? nextCockpitHeldSentence("discard-armed") : "";
  /* `revision_count` is `len(entry["revisions"])` for a real entry and 0 for
     none, so the OFFER is a measured value and not a structurally-present
     default: it never offers to discard nothing.

     The account of a discard that already happened is not gated on it, and
     that is the whole of this branch. A landed discard deletes the entry, the
     next payload publishes 0, and the gate would close over the one sentence
     saying what became of the words -- measured: every discard succeeded
     silently, and only the two failures, which leave the revisions in place,
     ever printed theirs. */
  const offer = nextNumber(annotation && annotation.revision_count) > 0;
  if(!offer && !landed) return "";
  const why = String(said.why || "");
  return '<div class="next-cockpit-held-discard">' +
    (offer && why ? `<p class="next-cockpit-held-absent">${esc(why)}</p>` : "") +
    /* The warning is the control's description rather than the sibling after
       it (DRC-4564). Measured in the accessibility tree: a reader who tabs to
       the armed control was told exactly "confirm discard, button", with the
       four effects of the second press sitting in a node they had to go
       looking for. No live region reaches that state, because nothing mutates
       when you tab. */
    (offer
      ? '<button type="button" class="next-action" ' +
        'data-next-cockpit-action="held-discard" ' +
        `data-next-cockpit-discard-key="${esc(key)}" data-next-focus="${esc(key)}"` +
        (warning ? ' aria-describedby="next-cockpit-discard-armed"' : "") + ">" +
        `${armed ? "confirm discard" : "discard everything"}</button>`
      : "") +
    (offer && warning
      ? '<p class="next-cockpit-held-absent" id="next-cockpit-discard-armed">' +
        `${esc(warning)}</p>` : "") +
    (landed ? `<small class="next-cockpit-held-cue">${esc(landed)}</small>` : "") +
    '</div>';
}

/* The session page's DRIFT block, and the sections that follow it lower down
   (DRC-4639). Held to merged into the session view, so what was the tab's body
   is now two returns: `drift` renders first after the page's identity, and
   `record` renders after the session's own facts
   ([DEC-20](docs/design-reading-a-session.md#dec-20-the-first-screen-shows-goal-beside-direction-and-drift-has-one-home)).

   The order inside the block is load bearing: what you asked for, then the
   agent's direction beside it, then the one control, so it is on the first
   screen; then the reading, then any later direction of yours and the caveats,
   then every departure on record. Your words come first, so
   nothing above the reading is a model's.

   `direction` is the caller's CURRENT ACTIVITY card, handed in rather than
   rebuilt, so the NOW line has one renderer. `primary` is false while the
   session waits on the reader, whose question the check never outranks. The word drift names the block and the control and nothing else: no
   sentence here may say a session has none. */
function nextCockpitDriftBlock(group, session, direction, primary){
  const head = '<section class="next-session-drift" data-next-session-drift ' +
    'aria-labelledby="next-session-drift-heading">' +
    '<h2 id="next-session-drift-heading" class="next-session-drift-heading">DRIFT</h2>';
  /* No field at all when the store is off, which is what `--no-annotations`
     promises. A box whose every save answers 503 is worse than none, and the
     reason is on screen rather than left to the reader. The direction and any
     standing raise still render: the departure store is read whichever way. */
  if(!(nextData && nextData.annotate === true)){
    /* The check stays, inert, and its refusal is the one place the store's
       state is said: no field section above it repeating the sentence. */
    const source = nextCockpitWorkSource(group, session);
    const check = '<div class="next-session-drift-check">' +
      nextCockpitReadingControl(session, null, null, primary) + '</div>';
    return {drift: head + direction + check + nextCockpitDepartures(null, source, session) +
      '</section>', record: ""};
  }
  const annotation = nextCockpitAnnotation(session);
  const workSource = nextCockpitWorkSource(group, session);
  // The full set, not the displayed window: a citation resolves against what
  // the payload holds, and the window is a readability bound on the rows.
  const entries = workSource.all || workSource.entries;
  const observed = nextCockpitFocusedObserved(group, nextCockpitObservedProject(group), session);
  /* The same open set gates the conflict block and the reading's demotion, so
     those two cannot disagree about whether a baseline is settled. */
  const unsettled = Boolean(
    nextCockpitConflictCandidates(annotation, workSource.all || entries).length);
  const cap = nextCockpitHeldCap();
  /* The header line, and the discard stamp takes its slot rather than sitting
     under it (DRC-4565). Both answer "what state are these two boxes in", and
     "No revision saved yet" is the answer for a session nobody typed against
     -- printing it above a record of a deletion is the false sentence this
     issue removes. */
  const revision = nextAnnotationDiscardStamp(annotation) ||
    nextProjectRevisionLine(annotation) || "No revision saved yet";
  /* What became of the words, in the board's own voice, and the second
     sentence only where a raise still quotes them. Not gated on the offer to
     discard: `revision_count` is 0 once a discard lands, and gating the
     account on the control is how the only sentence about a landed discard
     came to render for the two FAILURE cases alone. */
  const discarded = nextAnnotationDiscardAccount(annotation, session.departures)
    .map(said => `<p class="next-cockpit-held-absent">${esc(said)}</p>`).join("");
  const binding = annotation && annotation.binding_why && (annotation.goal || annotation.output)
    ? `<p class="next-cockpit-held-absent">${esc(annotation.binding_why)}</p>` : "";
  /* An ended session may still be annotated, and the store will keep it. What
     is unsettled is whether anything should then read it, so the line says
     that rather than disabling a control over an open question. A caveat, so
     it renders with the caveats below the reading (DRC-4669): between the
     fields and the control it pushed Check for drift under a 1440x900 fold
     on every ended session. */
  const ended = nextSessionEndedAt(session) != null
    ? '<p class="next-cockpit-held-absent">This session has ended. Anything you save ' +
      'against it is kept, and nothing is promised to read it.</p>' : "";
  /* What typing buys, before anything that qualifies it, worded to the default
     board: the unasked lane is off unless the reader started with
     `--unasked-readings`, so a check happens because the reader pressed. */
  const lede = '<p class="next-cockpit-held-lede">Choose a goal or use your prompt, then check for ' +
    'drift: Cargento lists where this session departed from it. It never writes into the ' +
    'session, so steering stays yours.</p>';
  /* Named, because the reader has to know whose words these are: the harness
     and the session id are what the store keys on. */
  const asked = '<section class="next-cockpit-held"><header><h2>WHAT YOU ASKED FOR</h2>' +
    `<span class="next-cockpit-held-bound">${esc(sessKey(session))}</span></header>` +
    lede +
    `<span class="next-cockpit-held-revision">${esc(revision)}</span>` +
    `<span class="next-cockpit-define">${NEXT_COCKPIT_REVISION_DEFINITION}</span>` +
    '<div class="next-cockpit-held-fields">' +
    NEXT_COCKPIT_HELD_FIELDS.map(spec =>
      nextCockpitHeldField(session, annotation, spec, cap)).join("") + '</div>' +
    '</section>';
  const reading = nextCockpitReadingParts(session, annotation, entries,
    nextCockpitObserverModel(group, session), observed, unsettled, workSource, primary);
  /* Below the reading, not between the fields and the control: none of these
     is the next thing to do, and above the control they pushed it off the
     first screen. */
  const discard = nextCockpitHeldDiscardBlock(session, annotation);
  const caveats = ended || discarded || binding || discard
    ? `<div class="next-session-drift-caveats">${ended}${discarded}${binding}${discard}</div>` : "";
  const drift = head + asked + direction + reading.control + reading.reading +
    nextCockpitConflict(session, annotation, workSource) + caveats + reading.departures +
    '</section>';
  /* Below the session's facts: how it landed, the observed record the reading
     cites, and where a raise is kept. The reading's offer says the record is
     "below", and it is. */
  const record = nextCockpitLanded(observed) +
    nextCockpitWorkEvidence(session, workSource) +
    nextCockpitDeparturesKept();
  return {drift, record};
}

/* The reader's answer, posted to the same route their words go to. `through`
   is the newest direction they were shown, not `Date.now()`: the mark has to
   be the moment they actually looked at, and the store clamps it to now so a
   forged value cannot disable the block forever. */
/* One reading, on one press, and no retry.

   `press: true` is the shape contract's "asserted rather than assumed" made
   mechanical: the literal appears in this one place, inside a click handler,
   and the route refuses a body without it. Nothing on render, poll,
   reconnect, resume, focus change or revision save carries it.

   `observer_model: 1` preserves the route's explicit-request guard. The
   separate allow field records a first-press answer; the server checks its
   durable permission and budget again at the model seam. */
async function nextCockpitAskForReading(session, model, allow = false){
  const key = sessKey(session);
  if(nextCockpitReadingRequests.get(key)?.pending) return;
  /* This press arrives from states the browser used to swallow, and an
     ungated one spends the reader's own model capacity from a state the page
     calls unavailable. Answered rather than dropped, because a clicked control
     that goes silent is indistinguishable from a dead one. */
  const refusal = nextPromptReadingRefusal(session, nextCockpitAnnotation(session), model);
  if(refusal){
    nextCockpitReadingRequests.set(key, {pending: false, message: refusal, refusal: true});
    renderNext();
    return;
  }
  /* The provider the page named, sent with the press so the server can
     refuse one whose receiver changed since. A refusal above already covers
     a route with no provider. */
  const route = nextReadingRoute(session);
  const provider = String(route.provider);
  /* The destination the disclosure named, sent with an Allow so the server
     can refuse one given about an endpoint that has since moved. */
  const destination = String(route.destination || "");
  if(nextReadingNeedsAllow(route) && !allow){
    nextCockpitReadingRequests.set(key, {consent:true, adoption:nextImplicitAdoption(session)});
    renderNext();
    return;
  }
  /* Session-scoped state survives polling and navigation while the model
     runs. Another press must not spend capacity on a duplicate request. */
  /* The bound is `observer.OBSERVER_MODEL_TIMEOUT_SEC`, sixty seconds, and the
     sentence says so because a press that goes quiet for a minute otherwise
     reads as a dead control. Nothing on the page waits on it. */
  const confirmation = nextCockpitReadingRequests.get(key);
  const adoption = allow && confirmation && confirmation.consent
    ? confirmation.adoption : nextImplicitAdoption(session);
  const request = {pending: true, message: NEXT_READING_PENDING, adoption};
  nextCockpitReadingRequests.set(key, request);
  renderNext();
  try{
    const response = await fetch("/api/reading", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({harness: session.harness, sid: session.sid, provider,
        press: true, observer_model: 1, ...adoption,
        ...(allow ? {allow:true, ...(destination ? {tool_output:destination} : {})} : {})}),
    });
    const answer = response && typeof response.json === "function"
      ? await response.json().catch(() => null) : null;
    if(answer && answer.route && typeof answer.route === "object"){
      /* The server's route for this harness now. Kept before the refresh so
         the sentence below and the disclosure it points at agree at once. */
      nextData.reading_routes = {...(nextData.reading_routes || {}),
        [String(session.harness || "")]: answer.route};
    }
    if(response && response.status === 409 && answer && answer.reason === "provider-changed"){
      /* Nothing was sent or saved. The next press starts again, and asks for
         the new receiver's own Allow if it has none. */
      request.message = NEXT_READING_PROVIDER_CHANGED;
      request.consent = false;
      await refreshNext();
      return;
    }
    if(response && response.status === 409 && answer && answer.reason === "destination-changed"){
      request.message = NEXT_READING_DESTINATION_CHANGED;
      request.consent = false;
      await refreshNext();
      return;
    }
    if(response && response.status === 409){
      request.message = "A reading is already in progress for this session. " +
        "Wait for it to finish; this press did not start another.";
      return;
    }
    if(answer && answer.route && !answer.route.provider){
      request.message = nextReadingRouteRefusal(session);
      request.refusal = true;
      return;
    }
    if(answer && answer.adoption_refused){
      request.message = "The prompt or saved goal changed. Review the current goal before checking again.";
      await refreshNext();
      return;
    }
    if(answer && answer.reading){
      nextData.reading = answer.reading;
      request.message = nextReadingPolicyReason(answer.reading);
      request.refusal = Boolean(request.message);
      request.consent = ["consent-required", "tool-output-consent-required"]
        .includes(answer.reading.reason);
      return;
    }
    if(!response || !response.ok) throw new Error(`HTTP ${response && response.status}`);
    if(!answer || answer.ok !== true || typeof answer.produced !== "boolean"){
      throw new Error("reading not confirmed");
    }
    if(allow && nextData.reading){
      nextData.reading.consent = true;
      nextData.reading.providers = {...(nextData.reading.providers || {}), [provider]: true};
      if(destination){
        const granted = (nextData.reading.tool_output || {})[provider] || [];
        nextData.reading.tool_output = {...(nextData.reading.tool_output || {}),
          [provider]: granted.includes(destination) ? granted : [...granted, destination]};
      }
    }
    request.message = answer.produced ? "Reading received." : "No new reading was produced.";
    await refreshNext();
  }catch(_error){
    /* A lost response does not establish that the model never ran. */
    request.message = "Could not confirm the reading. The request has not been retried. " +
      "Refresh to check for a result before asking again.";
  }finally{
    request.pending = false;
    renderNext();
  }
}

async function nextCockpitReadingOff(){
  try{
    const response = await fetch("/api/reading", {method:"POST", headers:{"Content-Type":"application/json"},
      body:JSON.stringify({consent:"off",press:true,observer_model:1})});
    const answer = await response.json();
    if(!response.ok || !answer || answer.ok !== true || !answer.reading) throw new Error("permission not saved");
    nextData.reading = answer.reading;
    for(const [key, request] of nextCockpitReadingRequests){
      if(!request.pending) nextCockpitReadingRequests.delete(key);
    }
    await refreshNext();
  }catch(_error){
    const session = nextSessionFind(nextRoute.project,nextRoute.harness,nextRoute.session);
    if(session) nextCockpitReadingRequests.set(sessKey(session), {message:"Could not confirm readings are off. Try turning them off again."});
  }finally{ renderNext(); }
}

async function nextCockpitConflictSettle(session, through){
  try{
    const response = await fetch("/api/annotate", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({harness: session.harness, sid: session.sid,
        settle_through: through}),
    });
    if(!response || !response.ok) throw new Error(`HTTP ${response && response.status}`);
    const saved = await response.json();
    if(!saved || saved.ok !== true) throw new Error("settle not confirmed");
    /* `persisted` was ignored here, so a settle whose write did not land
       reopened the block looking exactly as it had before the press: the
       store sets the mark in this process before it writes, and the refresh
       on the next line reloads the file and drops it. The cue rides the held
       fields' lane and is drawn inside the block by `nextCockpitConflict`
       (decisions.md, DRC-4543). Nothing is marked for a settle that landed:
       the block's own settled sentence, read from the store on the next
       payload, is that report. */
    const settleKey = nextCockpitHeldKey(session, "settle");
    if(saved.persisted !== true){
      nextCockpitHeldMark(settleKey,
        String(saved.outcome || "") === "refused" ? "settle-refused" : "settle-unpersisted");
    }else{
      /* Cleared rather than left alone. A press that failed and a press that
         landed share one lane and one key, so a failure cue outlived its
         failure for the lane's whole TTL and was drawn directly above the
         block's own "You settled this ... ago": the block then said both
         that the mark had been dropped and that it was held. Reaching it
         needs a store unwritable and then writable inside that TTL, which
         is exactly the retry a reader makes after the first cue tells them
         to. */
      nextCockpitHeldDrop(settleKey);
      /* The one push outside `nextCockpitHeldMark`, because this outcome is
         the one that deliberately marks nothing. Under the settle key all the
         same, so the failure cue this replaces cannot suppress it. */
      nextCockpitAnnounceCue(settleKey, NEXT_COCKPIT_SETTLE_LANDED, false);
    }
    await refreshNext();
  }catch(_error){
    // The block stays open, which is the safe direction: a settlement that did
    // not land must not read as one that did.
    renderNext();
  }
}

/* The endpoint's whole-annotation arm, reached from the second press.

   Shaped on `nextCockpitHeldSave` and deliberately not sharing its cue table:
   "Saved as a new revision." over a deletion, and "...they are still in the
   box" for an act with no box, are both DRC-4543's defect re-shipped. The
   sentences come from the payload instead, so the one that claims the
   departure store no longer quotes these words is written where that store
   can be tested. */
async function nextCockpitDiscardAnnotation(session){
  const key = nextCockpitHeldKey(session, "discard");
  try{
    const response = await fetch("/api/annotate", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({harness: session.harness, sid: session.sid, clear: true}),
    });
    if(!response || !response.ok) throw new Error(`HTTP ${response && response.status}`);
    const answer = await response.json();
    if(!answer || answer.ok !== true) throw new Error("discard not confirmed");
    const outcome = String(answer.outcome || "");
    /* The store's own token, with `persisted` as the fallback an older or
       newer server leaves: one bit cannot carry three sentences, which is
       what `NEXT_COCKPIT_HELD_CUES` records about the save path. */
    const answered = ["stored", "refused", "unwritable"].includes(outcome)
      ? `discard-${outcome}`
      : (answer.persisted === true ? "discard-stored" : "discard-unwritable");
    /* A discard is one act over two stores and the second half fails on its
       own. `withdrew` is the departure store's answer, so the categorical
       sentence is not printed over rows this page is about to redraw with the
       discarded words still in them. `=== false` and not falsiness: a server
       that predates the field omits it, and an absent answer must leave the
       sentence it had. */
    const kind = answered === "discard-stored" && answer.withdrew === false
      ? "discard-unwithdrawn" : answered;
    if(kind === "discard-stored" || kind === "discard-unwithdrawn"){
      // The independent log may already hold these words, even if the next
      // dashboard fetch fails. Other tabs learn through its source revision.
      nextIntentInvalidate();
      /* The drafts go with the annotation. They are an independent lane, so a
         half-typed box would otherwise sit over an empty store and the next
         save would mint revision 1 of what the reader just discarded. */
      for(const spec of NEXT_COCKPIT_HELD_FIELDS){
        nextCockpitHeldDrafts.delete(nextCockpitHeldKey(session, spec[0]));
      }
    }
    nextCockpitHeldMark(key, kind);
    renderNext();
    await refreshNext();
  }catch(_error){
    // Nothing was deleted that this page can see, which is what the refusal
    // sentence says. No retry: a second press is the reader's to make.
    nextCockpitHeldMark(key, "discard-refused");
    renderNext({named: key});
  }
}

async function nextCockpitHeldSave(session, kind){
  const key = nextCockpitHeldKey(session, kind);
  /* The same expression `nextCockpitHeldField` decides `shown` with, so the
     control and the gate cannot disagree. Without it an inert-but-reachable
     control mints a revision identical to the stored one. */
  const annotation = nextCockpitAnnotation(session);
  const stored = String(annotation && annotation[kind] || "");
  const typed = nextCockpitHeldDrafts.has(key) ? nextCockpitHeldDrafts.get(key) : stored;
  if(typed === stored) return;
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
    /* And the cue from the store's own token rather than from `persisted`,
       which is one bit for four sentences; `NEXT_COCKPIT_HELD_CUES` records
       what each bit hid. The draft goes only where the words are on disk,
       which is a minted revision or a repeat of the one already there. */
    const outcome = String(saved.outcome || "");
    const kind = NEXT_COCKPIT_HELD_OUTCOME_CUES[outcome] ||
      (saved.persisted === true ? "saved" : "unpersisted");
    const onDisk = kind === "saved" || kind === "unchanged";
    if(onDisk && nextCockpitHeldDrafts.get(key) === sent) nextCockpitHeldDrafts.delete(key);
    nextCockpitHeldMark(key, kind);
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
    "actionable direction not observed";
  const resultEvidence = briefing.latest.resultKind === "semantic"
    ? `exact semantic result · source session ${resultSource}`
    : briefing.latest.resultKind === "session"
      ? `session output; semantic result not published · source session ${resultSource}`
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
      '</details>' : briefing.task.known
        ? '<small class="next-cockpit-evidence-missing">Assignment evidence not published</small>'
        : "";
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
    (!briefing.latest.direction ? '<p class="next-cockpit-evidence-missing">Actionable direction not observed</p>' : "") +
    (!briefing.latest.result ? '<p class="next-cockpit-evidence-missing">Session result not observed</p>' : "") +
    `<details${nextCockpitDisclosureAttr("latest")}><summary>Evidence · direction and result sources</summary>` + latestEvidence.map(value =>
      `<small class="next-cockpit-source">${esc(value)}</small>`).join("") + '</details></div>' :
    '<div class="next-cockpit-recovery-evidence"><span>LATEST EVIDENCE</span>' +
    '<p class="next-cockpit-evidence-missing">Actionable direction not observed · ' +
    'Session result not observed</p></div>';
  return '<section class="next-cockpit-recovery" aria-label="Recovery summary">' +
    '<header><strong>PROJECT RECOVERY BRIEFING</strong>' +
    `<small class="next-cockpit-recovery-gloss">${NEXT_COCKPIT_AUTHORITY_GLOSS}</small>` +
    '</header>' +
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

/* The state of one `nextCockpitContexts` entry, and then of the pair a read
   needs. Classified once, for the panel that renders a context and the cue
   that labels its tab.

   FIVE states, not two, because the map has five reachable shapes and the two
   obvious ones hide the interesting one. Three writers store into it --
   `nextCockpitLoadContext`'s `.then` and `.catch` above, and
   `next-render.js:81` -- and only the `.catch` writes `error`. That `.catch`
   MERGES rather than replaces: `data: settled && settled.data || null` carries
   the PREVIOUS data into the new object, so a failed poll over an already
   loaded context leaves `{data:<stale>, error:true}`, which a reader keying
   off `.data` alone cannot tell from a clean resolve.

   Every write is `.set(key, {...})` with a fresh object literal, so no reader
   ever sees a half-written entry. That is worth stating because it is the
   invariant a future writer breaks -- it holds by construction today rather
   than by any rule, and a single `entry.data = ...` would end it.

   The negative `error` field is read rather than a positive one added. A
   positive field would have to be written by all three writers, and the third
   living in another file is exactly how the field sets came apart here. */
function nextCockpitEntryState(entry){
  if(!entry) return "absent";
  if(entry.data) return entry.error === true ? "stale" : "ready";
  return entry.error === true ? "unavailable" : "pending";
}

/* A focused read needs its own entry AND the project's, which is the pair the
   panel has always required and the cue did not. Worst state wins, in the
   order the panel already resolved them: a finished failure outranks a read
   still in flight, which outranks data carried across a failure.

   `stale` renders exactly as `ready` does at both call sites. That is a
   ruling, not an oversight: keeping the last known rows is defensible, and
   saying so on screen would be new copy nobody has specified (DRC-4613). What
   this separation buys today is that neither surface can call a finished read
   "not loaded yet", and that the two cannot disagree, because there is one
   answer and both ask for it. */
const NEXT_COCKPIT_READ_RANK = ["unavailable", "absent", "pending", "stale", "ready"];

function nextCockpitContextRead(group, focus){
  const entry = nextCockpitContexts.get(nextCockpitContextKey(group, focus));
  const projectEntry = focus
    ? nextCockpitContexts.get(nextCockpitContextKey(group, null)) : entry;
  const states = [nextCockpitEntryState(entry)];
  if(focus) states.push(nextCockpitEntryState(projectEntry));
  const state = NEXT_COCKPIT_READ_RANK.find(candidate => states.includes(candidate));
  return {state, entry, projectEntry, shows: state === "ready" || state === "stale"};
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

/* One sentence per tab, naming the tab's own word and what its panel holds.
   Two of the four open onto a heading that does not repeat the label -- Now
   onto GOING ON, Course onto OBSERVED STATE CHANGES -- and renaming either end
   would move a string two other views share. */
const NEXT_COCKPIT_TAB_LEDES = new Map([
  ["now", "Now: what is running in this project this minute, and how sessions here have ended."],
  ["course", "Course: direction changes Cargento observed in the session record."],
  ["decisions", "Decisions: rulings found in the record, and what each one has been spent on."],
  ["console", "Console: the read-only terminal of one selected session, and the controls for it."],
]);

// Singular and plural for the cue's gloss, per tab that carries one.
const NEXT_COCKPIT_TAB_NOUNS = new Map([
  ["course", ["observed state change", "observed state changes"]],
  ["decisions", ["decision", "decisions"]],
]);

function nextCockpitTabLede(tab, focus){
  const text = NEXT_COCKPIT_TAB_LEDES.get(tab);
  if(!text) return "";
  /* Now is the one tab whose scope does not narrow with the selection, so a
     reader who has just picked a session is the only one who needs telling.
     The sentence used to be its own <p class="next-cockpit-scope-note">, which
     no rule in styles.css ever matched: it rendered in the browser default
     face and size directly under this typeset line, reading as a fault rather
     than as something somebody wrote. Folded in here rather than given a rule
     of its own, because it is the same claim this lede already makes, narrowed
     to the focused case. */
  const scope = tab === "now" && focus
    ? " It stays project-wide, including activity from other sessions."
    : "";
  return `<p class="next-cockpit-lede">${esc(text + scope)}</p>`;
}

function nextCockpitTabCueCount(length){
  return length > 0 ? {state:"count", value:length} : {state:"zero", value:0};
}

/* What the tab's own panel would count, in the five states the board can
   honestly be in about it: a figure, a collection read and found empty, a
   collection nothing has published, one whose context has not arrived, and one
   whose context was read and did not come back. `null` means this tab renders
   no countable collection at all, which is not an absence to assert -- Now
   draws three fixed cells and Console is a terminal.

   Every read is guarded on the collection being an array before `.length` is
   taken. A length read off a list that is declared on every row whether or not
   anything ran reports the schema rather than the session, which is the defect
   DRC-4559 shipped and AGENTS.md's first Measured Invariant records. That is
   also why the semantic collection is reached through the context entry rather
   than through `nextCockpitSemantic`, whose `{facts:[]}` default would turn
   "no context at all" into a confident zero. */
/* DRC-4613, the captain's 2026-09-21 ruling: a read that has since failed to
   refresh keeps its rows, and the board must say so. Until this, `stale`
   rendered exactly as `ready` at both call sites, so a reader could not tell a
   current read from the last one that worked -- the board implying currency it
   does not have, which is the same shape as an absence rendering as a value.

   The staleness rides ON the cue rather than replacing it. The count is still
   the real count; what is in doubt is its age, so the figure stays and the age
   is what the cue adds. */
function nextCockpitTabCue(tab, context, focus){
  const cue = nextCockpitTabCueBase(tab, context, focus);
  if(!cue || !context || !context.group) return cue;
  const read = nextCockpitContextRead(context.group, focus);
  if(read.state !== "stale") return cue;
  return Object.assign({}, cue, {
    stale: true, lastRead: read.entry && read.entry.revision
  });
}

function nextCockpitTabCueBase(tab, context, focus){
  const group = context && context.group;
  if(tab === "course"){
    const changes = context && context.project && context.project.changes;
    return Array.isArray(changes) ? nextCockpitTabCueCount(changes.length) : {state:"unobserved"};
  }
  if(tab === "decisions"){
    /* The state from `nextCockpitContextRead`, so the cue cannot describe the
       read differently from the panel it labels -- including the failed case,
       which this cue used to report as `pending`.

       The facts come from that same read at BOTH scopes, rather than from the
       `observation` argument at project scope. The two were the same object --
       `nextCockpitProjectObservation` returns
       `nextCockpitContexts.get(key(group, null))`, measured `===` -- so this
       changes no board. What it removes is the SECOND read, which is the shape
       that let the state and the facts drift apart here in the first place.

       Neither `pending` nor `unavailable` is `unobserved`. A collection nobody
       has finished reading is not a collection nothing published, and calling
       it that reports the schema rather than the session, which is AGENTS.md's
       first Measured Invariant. */
    if(!group) return {state:"pending"};
    const read = nextCockpitContextRead(group, focus);
    // `absent` and `pending` are both "nobody has finished reading this"; the
    // cue has one mark for that. `unavailable` is its own, because a finished
    // failure is not a read still coming.
    if(!read.shows) return {state: read.state === "unavailable" ? "unavailable" : "pending"};
    const semantic = read.entry.data.semantic;
    if(!semantic || !Array.isArray(semantic.facts)) return {state:"unobserved"};
    return nextCockpitTabCueCount(projectDecisionFacts(
      group ? nextCockpitCanonicalSemantic(group, semantic) : semantic).length);
  }
  return null;
}

function nextCockpitTabCueHtml(tab, cue){
  if(!cue) return "";
  const nouns = NEXT_COCKPIT_TAB_NOUNS.get(tab) || ["item", "items"];
  /* Four states, and the em dash is this sheet's existing mark for a slot with
     no figure in it -- `[data-next-absent]::before` puts the same character in
     front of one. A read that finished and failed is not one still running and
     not a collection nothing published, so it says so rather than borrowing
     either mark.

     Every state names its own variant. A state that fell through to "" would
     inherit `.next-cockpit-tab-cue`'s `--ink2`, which is the ink a real figure
     gets: an absence rendering as loudly as the fact it replaces is the
     inversion this milestone exists to remove. */
  const mark = cue.state === "pending" ? "\u2026" :
    cue.state === "unobserved" ? "\u00b7" :
    cue.state === "unavailable" ? "\u2014" : String(cue.value);
  const gloss = cue.state === "count"
    ? `${cue.value} ${cue.value === 1 ? nouns[0] : nouns[1]}`
    : cue.state === "zero" ? `No ${nouns[1]} observed`
    : cue.state === "pending" ? `${nouns[1]} not loaded yet`
    : cue.state === "unavailable" ? `${nouns[1]} could not be read`
    : `${nouns[1]} not published`;
  const variant = cue.state === "pending" ? " next-cockpit-tab-cue--pending" :
    cue.state === "unobserved" ? " next-cockpit-tab-cue--unobserved" :
    cue.state === "unavailable" ? " next-cockpit-tab-cue--unavailable" : "";
  /* The two channels must agree. A visible suffix with no change to the gloss
     would tell a sighted reader the rows are stale and a screen-reader user
     they are current, which is the disagreement this repository has shipped
     before. Both carry it or neither does. */
  const clock = cue.stale && cue.lastRead ? nextSessionClock(cue.lastRead) : "";
  const staleMark = cue.stale
    ? '<span class="next-cockpit-tab-cue-stale" aria-hidden="true">stale</span>' : "";
  const staleGloss = cue.stale
    ? (clock ? `, last read ${clock}, refresh has failed since`
             : ", refresh has failed since the last successful read") : "";
  /* No `--stale` variant on the wrapper: the count is still the real count, so
     its ink does not change, and a variant class with no rule is what
     `EveryTabCueVariantIsColouredByItsOwnRuleTest` exists to reject. The
     staleness is its own span, which has its own rule. */
  return `<span class="next-cockpit-tab-cue${variant}" ` +
    `data-next-cockpit-tab-cue="${cue.state}"${cue.stale ? ' data-next-cockpit-tab-stale' : ""}>` +
    `<span aria-hidden="true">${esc(mark)}</span>${staleMark}` +
    `<span class="next-visually-hidden">${esc(gloss + staleGloss)}</span></span>`;
}

function nextCockpitTabList(context, focus){
  /* The route's `focus`, not the `focus` argument. The argument carries the
     session the cue needs; the tab SET stays on the route, because
     `nextCockpitPanel` reads the route too and a stale route would otherwise
     let the nav and the panel name different tabs. */
  const tabs = nextCockpitTabs(nextRoute && nextRoute.focus);
  const selected = tabs.includes(nextRoute && nextRoute.tab) ? nextRoute.tab : "now";
  return '<nav class="next-cockpit-tabs" role="tablist" aria-label="Project cockpit views">' +
    tabs.map(tab => {
      const label = nextCockpitHumanLabel(tab);
      const current = tab === selected;
      const cue = nextCockpitTabCueHtml(tab, nextCockpitTabCue(tab, context, focus));
      return `<button type="button" role="tab" data-next-cockpit-action="tab" ` +
        `data-arg="${tab}" data-next-focus="cockpit-tab:${tab}" aria-controls="next-cockpit-panel-${tab}" ` +
        `aria-selected="${current}" tabindex="${current ? 0 : -1}">${label}${cue}</button>`;
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

function nextCockpitTimeline(group, focus){
  const key = nextCockpitContextKey(group, focus);
  nextCockpitLoadContext(group, focus);
  const read = nextCockpitContextRead(group, focus);
  const entry = read.entry;
  if(!read.shows){
    const label = read.state === "unavailable"
      ? "Semantic context unavailable." : "Loading semantic context…";
    return `<section class="next-cockpit-semantic" data-next-cockpit-semantic><h2>SEMANTIC TIMELINE</h2>` +
      `<p class="next-cockpit-empty">${label}</p></section>`;
  }
  /* DRC-4613: the panel half of the staleness disclosure. The cue says it from
     the tab strip, which is where a reader who has not opened the panel meets
     it; this says it where the rows are, with the time they are from. Both are
     driven by the same `read.state`, so the two surfaces cannot describe the
     read differently -- the cue/panel disagreement this milestone has shipped
     before.

     It sits after the `!read.shows` return on purpose: a read with nothing to
     show already says so, and saying "these are the rows from that read" over
     no rows would be the louder wrong answer. */
  const staleNotice = read.state === "stale"
    ? '<p class="next-cockpit-stale-read" data-next-cockpit-stale-read>' +
      (entry && entry.revision
        ? `Last read ${esc(nextSessionClock(entry.revision))}. Refresh has failed since; ` +
          "these are the rows from that read."
        : "Refresh has failed since the last successful read; these are the rows from it.")
      + "</p>"
    : "";
  projectQuerySession = focus ? sessKey(focus) : "";
  const cacheKey = projectContextKey(nextCockpitStableKey(group));
  /* The four writers in `project.js` all carry `dashboard_revision`, and both
     readers key off what this one used to omit: `projectLoadContext` guards on
     `(old.dashboard_revision || old.generated)` and `projectRefreshControl` on
     `state === "loading"`. Writing `{state,data,generated}` here dropped the
     revision the loader compares against AND moved an in-flight slot out of
     `loading`, which re-enabled a refresh control that had not finished.
     So this seeds the bridge without disturbing a fetch that owns the slot.
     DRC-4612. */
  const heldContext = projectContextByLabel[cacheKey];
  if(!heldContext || heldContext.state !== "loading"){
    projectContextByLabel[cacheKey] = {
      state: "ready", data: entry.data, generated: entry.revision,
      dashboard_revision: entry.revision
    };
  }
  const delegationGroup = {label: nextCockpitStableKey(group)};
  const lanes = focus ? projectDelegationLanes(focus, delegationGroup) :
    group.sessions.flatMap(session => projectDelegationLanes(session, delegationGroup));
  const semantic = nextCockpitCanonicalSemantic(
    group,
    entry.data.semantic || {facts:[], work_items:[], projections:{}},
  );
  /* `defaultMode` rather than `mode`: a pinned mode also swaps the event
     source, so pinning it here was what took the renderer's other two modes
     off the board. An untouched Decisions tab still resolves to decisions;
     a reader who presses a button gets the other two.

     `eventPrefix` is kept in all three, because it draws its per-event scope
     cue from `event.fact`, which `projectGlobalEvents` sets on every event it
     builds. Dropping it on a mode change would lose which session an event
     came from exactly where the list gets longer. */
  const options = {defaultMode:"decisions",
    eventPrefix:event => nextCockpitScopeCue(nextCockpitFactScope(event.fact))};
  const timeline = projectSemanticTimeline(nextData, semantic, lanes, focus, group.sessions,
    options)
    .replaceAll('data-calm="project-graph-mode"', 'data-next-cockpit-action="graph-mode"');
  /* Resolved by the renderer's own function rather than from the argument, so
     the heading cannot say RECORDED DECISIONS over an all-events list. */
  const mode = projectResolveGraphMode(options);
  return '<section class="next-cockpit-semantic" data-next-cockpit-semantic>' + staleNotice +
    `<h2>${mode === "decisions" ? "RECORDED DECISIONS" : "SEMANTIC TIMELINE"}</h2>` +
    timeline + '</section>';
}

function nextCockpitCoursePanel(group, focus){
  const conditions = nextStageConditions(focus ? [focus] : group.sessions);
  const key = nextCockpitContextKey(group, focus);
  const entry = nextCockpitContexts.get(key);
  const projectEntry = nextCockpitContexts.get(nextCockpitContextKey(group, null));
  nextCockpitLoadContext(group, focus);
  if(!entry || !entry.data || focus && (!projectEntry || !projectEntry.data)){
    const failed = entry && entry.error || focus && projectEntry && projectEntry.error;
    return conditions + `<p class="next-cockpit-empty">${failed ? "Course evidence unavailable." :
      "Loading course evidence…"}</p>`;
  }
  const delegationGroup = {label:nextCockpitStableKey(group)};
  const lanes = focus ? projectDelegationLanes(focus, delegationGroup) :
    group.sessions.flatMap(session => projectDelegationLanes(session, delegationGroup));
  const semantic = nextCockpitCanonicalSemantic(
    group,
    entry.data.semantic || {facts:[],work_items:[],projections:{}},
  );
  return conditions + nextCockpitCourse(group, semantic, lanes);
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

/* Read from the sources the two sections read, rather than from
   whether their HTML came back non-empty. A body-derived summary reports an
   enabled bridge as off, because nextCockpitTerminal returns "" with no focus
   or no registered surface and nextCockpitConsoleStatus returns "" with no
   sessions -- a structurally-present default standing in for a measurement,
   which is the shape AGENTS.md "Measured Invariants" names. */
/* Three states and not two, which is the same invariant one layer in. The
   first render of this tab has neither answer: the focused context entry
   carrying `observer_model` is still in flight and the terminal lookup has not
   returned. Collapsing that into `false` told a reader whose server was started
   with BOTH capabilities on "terminal bridge off, observer model off", and the
   sentence corrected itself a tick later. Measured on a fixture serving an
   enabled model and a registered terminal: unread read {terminal:false,
   observer:false} where settled read {terminal:true, observer:true}, and the
   terminal section rendered inside the setup disclosure on that render.

   Moving the lookup earlier does not remove the third state and cannot: the
   lookup is a fetch, so the render that starts it still has no answer. What the
   caller's reorder buys is that placement and summary read the same tick's map
   rather than the previous render's.

   A FOURTH value with no session selected, rather than `null`. The bridge is a
   per-session registration, so with nothing focused there is no session whose
   bridge could be reported either way -- but `null` reads as "not read yet",
   and at project scope no lookup is ever attempted, so nothing is pending and
   nothing can resolve. That is a pending state that never ends, which is the
   same defect class as the "off" it replaced, one step over. `"per-session"`
   says what is actually true, and the prompt directly above it already tells
   the reader to select a session.

   Read from `state` and NOT from the `loading` flag beside it, which is a
   distinction the first draft of this function got wrong and a poll would have
   exposed within seconds. `projectTerminalLookup` marks a REGISTERED terminal
   `{state:"registered", loading:true}` while it refreshes, and it refreshes
   whenever the payload's revision advances -- so a flag-based read reported
   `null` on every poll of a working console. Measured: settled
   `{terminal:true}`, then `{terminal:null}` one revision later, with the
   summary flipping to "terminal bridge not read yet" and the live terminal
   moving INTO the setup disclosure. `state` is the tri-state on its own:
   `loading` only before any answer, then `registered` or `unavailable`. */
function nextCockpitConsoleCapabilities(group, focus){
  const terminal = focus ? projectTerminalBySession[sessKey(focus)] : null;
  const entry = nextCockpitContexts.get(nextCockpitContextKey(group, focus));
  // `undefined` distinguishes an entry that has not arrived from one that
  // arrived publishing no observer model; `null` from the latter is a read.
  const model = entry && entry.data ? entry.data.observer_model || null : undefined;
  return {
    terminal: !focus ? "per-session"
      : (!terminal || terminal.state === "loading" ? null
        : terminal.state === "registered"),
    observer: model === undefined ? null : Boolean(model && model.enabled === true),
  };
}

function nextCockpitConsoleSetup(capabilities, body){
  // One word per state, and four of them. "off" for a capability nothing has
  // read yet is the confident wrong answer this board is built against; "not
  // read yet" for one that nothing will ever read is the same error inverted.
  const said = value => value === true ? "on"
    : (value === false ? "off"
      : (value === "per-session" ? "per-session" : "not read yet"));
  const summary = "How this server was started \u2014 terminal bridge " +
    said(capabilities.terminal) + ", observer model " + said(capabilities.observer);
  return '<details class="next-cockpit-console-setup" data-next-cockpit-console-setup' +
    nextCockpitDisclosureAttr("console-setup") + '>' +
    `<summary>${esc(summary)}</summary>${body}</details>`;
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
    body = nextProjectGoingOn(context, commandAttention) + nextProjectEndings(context) +
      nextProjectPlanStatus(context) + nextCockpitPlanDisclosure(context);
  }else if(tab === "course"){
    body = nextProjectChanges(context.project) +
      nextCockpitCoursePanel(context.group, focus) + nextCockpitCompletedWork(context);
  }else if(tab === "decisions"){
    body = nextCockpitDecisionSummary(context.group, focus, observation) +
      nextCockpitTimeline(context.group, focus);
  }else{
    /* Operations first. The reader came here to act, and the two setup
       sections describe capabilities a default run has switched off: 309px of
       968px, measured, that never change while you work. An enabled capability
       is operational content, so it leaves the disclosure -- but it is emitted
       AFTER the rail rather than before it, because the rail is what the panel
       is now ordered around and a live terminal ahead of it would put the
       operations back below a screenful. */
    /* The terminal before the capabilities, because `nextCockpitTerminal` is
       what performs the lookup the capabilities then read. Reversed, the
       placement decision read the map the next line fills. */
    const terminal = focus ? nextCockpitTerminal(context.group, focus) : "";
    const capabilities = nextCockpitConsoleCapabilities(context.group, focus);
    const prompt = focus ? ""
      : '<p class="next-cockpit-empty">Select one exact session to open its read-only console.' +
        (context.group.sessions.length === 1
          ? ` <a href="${esc(nextFragmentForRoute({view:"project",project:context.group.label,
            focus:sessKey(context.group.sessions[0]),tab:"console"}))}">Open this session’s console</a>`
          : "") + '</p>';
    const observer = nextObserverModelControls(context.group, focus);
    /* `=== true` at every gate: an unread capability is not an enabled one,
       and it offers nothing to operate on this render, so it keeps the
       disclosure's placement until it resolves. Only the summary distinguishes
       the two, because only the summary makes a claim about it. */
    body = nextCockpitConsoleScope(focus) + prompt + nextProjectRail(context) +
      (capabilities.terminal === true ? terminal : "") +
      (capabilities.observer === true ? observer : "") +
      nextCockpitConsoleSetup(capabilities,
        (capabilities.terminal === true ? "" : terminal) +
        (capabilities.observer === true ? "" : observer) +
        nextCockpitConsoleStatus(context.group));
  }
  return `<section class="next-cockpit-panel" id="next-cockpit-panel-${tab}" role="tabpanel" ` +
    `data-next-cockpit-panel="${tab}" aria-label="${nextCockpitHumanLabel(tab)}">` +
    nextCockpitTabLede(tab, focus) + `${body}</section>`;
}

function nextProjectCockpit(context, observation, commandAttention){
  const group = context.group;
  const focus = nextCockpitFocusedSession(group);
  projectQuerySession = focus ? sessKey(focus) : "";
  lastData = nextData;
  /* The one place on this page a person can write anything. It used to be the
     last child of TRIPWIRES, a section captioned "local only \u00b7 nothing
     enforces these", 86% of the way down the Console panel and on no other tab.
     The draft is project-scoped, so the project chrome is where it belongs.
     Reused rather than retyped: the renderer carries data-next-steer-form,
     data-next-draft, data-next-controls-project, data-next-focus and the
     500-character cap, and a second copy of the markup loses them silently. */
  const projectKey = context.project && context.project.key || group.label;
  return nextCockpitViewingSession(focus) +
    nextCockpitRecoveryStrip(group, observation, commandAttention, context.project) +
    nextProjectSteer(projectKey, nextControlsProjectState(projectKey), "next-steer--bar") +
    nextCockpitTabList(context, focus) +
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
  /* Sessions joins the two cockpit views because its tier-2 caveats are built
     on `nextCockpitWhy`; their keys carry no project, so they cannot collide
     with a project's. */
  nextCockpitHadDisclosures = Boolean(nextRoute &&
    ["project", "session", "sessions"].includes(nextRoute.view));
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
  nextCockpitHeldDrop(key);
  const field = input.closest ? input.closest("[data-next-cockpit-held-field]") : null;
  if(!field || !field.querySelector) return;
  const count = field.querySelector("[data-next-cockpit-held-count]");
  if(count) count.textContent = `${value.length}/${nextCockpitHeldCap()}`;
  nextCockpitHeldToggle(field, "held-clear", Boolean(value), false);
  nextCockpitHeldToggle(field, "held-save",
    value !== String(input.dataset.nextCockpitHeldSaved || ""), true);
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
  const group = nextCockpitRouteGroup();
  if(action === "tab"){
    const tab = String(target.dataset.arg || "");
    if(!group || nextRoute.view !== "project" || !nextCockpitTabs(nextRoute.focus).includes(tab)) return;
    event.preventDefault();
    navigateNext({view:"project",project:group.label,focus:nextRoute.focus || null,tab});
    nextRestoreFocus({named:"cockpit-tab:" + tab}, nextAttention);
    return;
  }
  if(action === "prompt-adopt"){
    event.preventDefault();
    const session = group ? nextCockpitFocusedSession(group) : null;
    if(session) nextAdoptPrompt(session, target.dataset.arg);
    return;
  }
  if(action === "reading-off"){
    event.preventDefault();
    nextCockpitReadingOff();
    return;
  }
  if(action === "reading-ask" || action === "reading-allow"){
    const session = group ? nextCockpitFocusedSession(group) : null;
    if(!session) return;
    event.preventDefault();
    nextCockpitAskForReading(session, nextCockpitObserverModel(group), action === "reading-allow");
    return;
  }
  if(action === "conflict-settle" || action === "conflict-retype"){
    const session = group ? nextCockpitFocusedSession(group) : null;
    if(!session) return;
    event.preventDefault();
    if(action === "conflict-retype"){
      /* No write. Cargento cannot author the reader's words, and prefilling
         the field from a fact summary would put a harness-published string in
         the TYPED GOAL box. Moving the caret there is the whole of it. */
      nextRestoreFocus({named: nextCockpitHeldKey(session, "goal")}, nextAttention);
      return;
    }
    nextCockpitConflictSettle(session, Number(target.dataset.arg || 0));
    return;
  }
  if(action === "held-discard"){
    const session = group ? nextCockpitFocusedSession(group) : null;
    if(!session) return;
    event.preventDefault();
    const key = nextCockpitHeldKey(session, "discard");
    // Read before the kind, which drops the state on expiry.
    const held = nextCockpitHeldStates.get(key);
    const armedAt = held && held.kind === "discard-armed" ? held.at : 0;
    const slip = Number(event.detail) > 1
      || Date.now() - armedAt < NEXT_COCKPIT_DISCARD_DWELL_MS;
    if(nextCockpitHeldKind(key) !== "discard-armed" || slip){
      /* Arm, or re-arm. Nothing is posted until the reader has read what the
         second press will do and pressed again -- and a press too soon after
         the arm to have read it is the double-click that used to confirm in
         one gesture, so it buys another dwell rather than the write. */
      nextCockpitHeldMark(key, "discard-armed");
      renderNext({named: key});
      return;
    }
    nextCockpitDiscardAnnotation(session);
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
    nextCockpitHeldDrop(key);
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
    if(projectSetGraphMode(String(target.dataset.arg || ""))) renderNext();
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
  /* Escape on the ARMED discard control, and only then. `next-chrome.js`
     excuses input, select and textarea from its own Escape handler and a
     button falls through it, so Escape here navigated the reader out of the
     cockpit with the arm still stamped in a Map that outlives the navigation:
     they came back to a control one press from destroying an annotation.
     Unarmed, Escape keeps meaning "leave this view". */
  const discard = event.target && event.target.closest
    ? event.target.closest("[data-next-cockpit-discard-key]") : null;
  if(event.key === "Escape" && discard){
    const key = String(discard.dataset.nextCockpitDiscardKey || "");
    if(nextCockpitHeldKind(key) === "discard-armed"){
      event.preventDefault();
      // Dropped deliberately, so the next arm is not a repeat of this one.
      nextCockpitHeldDrop(key);
      renderNext({named: key});
      return true;
    }
  }
  const held = event.target && event.target.closest
    ? event.target.closest("[data-next-cockpit-held-key]") : null;
  if(event.key === "Escape" && held){
    event.preventDefault();
    const key = String(held.dataset.nextCockpitHeldKey || "");
    // Drop the draft rather than write the saved value back into it: the
    // render reads the store whenever the Map has no entry, so this is the
    // one place the two cannot disagree.
    nextCockpitHeldDrafts.delete(key);
    nextCockpitHeldDrop(key);
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


function nextPromptCandidate(session, source = "latest-prompt"){
  if(!session || !["claude", "codex"].includes(session.harness)) return null;
  let text = "", at = null;
  if(source === "first-prompt"){
    text = String(session.first_prompt || ""); at = nextNumber(session.first_prompt_at);
  }else if(source === "latest-prompt" && session.harness === "claude"){
    const asked = nextSessionInstruction(session, "asked");
    if(asked){ text = String(asked.text || ""); at = nextNumber(asked.at); }
  }else if(source === "latest-prompt" && session.prompt_states_work === true){
    text = String(session.title || ""); at = nextNumber(session.prompt_at);
  }
  return text ? {text, at: at != null && at > 0 ? at : null, source} : null;
}

function nextImplicitAdoption(session){
  if(String(session && session.annotation_goal || "").trim()) return {};
  const candidate = nextPromptCandidate(session);
  return candidate && candidate.at != null ? {adopt:candidate.source,
    expected_prompt:candidate.text, expected_prompt_at:candidate.at} : {};
}

function nextPromptReadingRefusal(session, annotation, model){
  if(!(nextData && nextData.annotate === true)) return NEXT_READING_ANNOTATIONS_OFF;
  /* A route with no reader is a fact about this machine, and it outranks any
     step the page could name: saving a goal here would not let a check run. */
  const route = nextReadingRoute(session);
  if(route && !route.provider) return nextReadingRouteRefusal(session);
  if(!String(annotation && annotation.goal || "").trim()){
    const candidate = nextPromptCandidate(session);
    if(candidate && candidate.at == null){
      return "The prompt time was not published, so it cannot be adopted. Type a goal to check for drift.";
    }
    if(candidate){ annotation = {...annotation,goal:candidate.text,discarded_at:null,discarded_why:""}; }
  }
  return nextCockpitReadingRefusal(annotation, model) || nextReadingRouteRefusal(session);
}

function nextPromptSourceLine(annotation){
  if(!annotation || !["latest-prompt", "first-prompt"].includes(annotation.goal_source)) return "";
  const which = annotation.goal_source === "first-prompt" ? "first" : "latest";
  const clipped = String(annotation.goal || "").endsWith("…") ? " Shown excerpt only." : "";
  return `<small class="next-cockpit-held-cue">from your prompt · ${which}.${clipped}</small>`;
}

function nextPromptAdoptControls(session){
  if(!(nextData && nextData.annotate === true)) return "";
  const choices = ["latest-prompt", "first-prompt"].map(source => {
    const candidate = nextPromptCandidate(session, source);
    if(!candidate) return "";
    if(candidate.at == null) return '<small class="next-cockpit-held-cue">Prompt time unavailable; type a goal instead.</small>';
    const which = source === "first-prompt" ? "first" : "latest";
    const clipped = candidate.text.endsWith("…") ? " Shown excerpt only." : "";
    return `<details class="next-cockpit-held-adopt"${nextCockpitDisclosureAttr("adopt:" + source)}><summary>Your ${which} prompt</summary>` +
      `<p>${esc(candidate.text)}${clipped}</p>` +
      `<button type="button" data-next-cockpit-action="prompt-adopt" data-arg="${source}">Use ${which} prompt without checking</button></details>`;
  }).join("");
  return choices ? `<details class="next-cockpit-prompt-choices"${nextCockpitDisclosureAttr("adopt:choices")}><summary>Use a prompt</summary>` +
    choices + '</details>' : "";
}

async function nextAdoptPrompt(session, source){
  const candidate = nextPromptCandidate(session, source);
  if(!candidate || candidate.at == null || !(nextData && nextData.annotate === true)) return;
  const key = nextCockpitHeldKey(session, "goal");
  try{
    const response = await fetch("/api/annotate", {method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({harness:session.harness,sid:session.sid,adopt:source,
        expected_prompt:candidate.text,expected_prompt_at:candidate.at,
        expected_revision:nextNumber(session.annotation_revision) || 0})});
    const answer = await response.json();
    if(!response.ok || !answer.persisted) throw new Error("adoption not saved");
    nextCockpitHeldDrafts.delete(key);
    await refreshNext();
  }catch(_error){
    nextCockpitReadingRequests.set(sessKey(session),{message:"The prompt or saved goal changed, or could not be saved. Review the goal before trying again."});
  }finally{renderNext();}
}
