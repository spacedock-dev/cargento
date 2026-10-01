const NEXT_COCKPIT_MEMO_PREFIX = "cargento.cockpit.memo.v2:";
const NEXT_COCKPIT_MEMO_LIMIT = 500;
const nextCockpitContexts = new Map();
const nextCockpitRequests = new Map();
const nextCockpitReadingRequests = new Map();
/* A Cancel in flight, or one that could not be confirmed, per session and for
   the one job it named, so neither outlives that job's box (DRC-4693). */
const nextCockpitReadingCancels = new Map();
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
  /* Every published field, and every one of them is published now:
     `base_session` declares all three of the reading's. The comment here
     used to say `assessment` was read but never published, which stopped
     being true when a producer landed -- and `TheAnnotationFieldListIsDerivedTest`
     now derives this list from `annotations.published` so it cannot drift
     again. This is a three-defect site, and every defect was the page
     reading a field nothing publishes. */
  const fields = ["goal", "goal_why", "lines_why",
    "line_1", "line_1_source", "line_1_source_id", "line_2", "line_2_source", "line_2_source_id",
    "line_3", "line_3_source", "line_3_source_id", "line_4", "line_4_source", "line_4_source_id",
    "line_5", "line_5_source", "line_5_source_id", "line_6", "line_6_source", "line_6_source_id",
    "revision", "revision_count", "at", "goal_source", "goal_source_at", "goal_saved_at", "window_start", "binding_why", "settled_at", "settled_through",
    "settled_revision", "assessment", "reading_count", "reading_withheld",
    "reading_withheld_at", "reading_refused", "not_accurate", "discarded_at", "discarded_why"];
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
      !fact.evidence || fact.evidence.confidence !== "exact" || nextReadingCopied(fact)) return false;
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
  ["goal", "Goal", "goal", "goal_why", "what you are after, in one line"],
];
/* The seventh line's refusal, said where the reader meets it: beside the add
   control, which stays on the page and inert at six, and in the polite region
   when it is pressed anyway
   ([NUI-18](docs/design-next-ui.md#nui-18-one-control-primitive-and-an-inert-control-stays-on-the-page)).
   The owner's ruling for a full list is to replace or merge a line, so the
   sentence names both. */
const NEXT_COCKPIT_LINES_FULL =
  "An expected outcome holds six lines. Replace or merge a line to add another.";

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
/* `focus` is the control's own key, so a redraw leaves a keyboard reader on
   it rather than on the page (DRC-4714). */
function nextCockpitHeldControl(action, label, kind, shown, inert, describedBy, focus = ""){
  const off = inert ? ' aria-disabled="true"' : " hidden";
  const why = !shown && inert && describedBy ? ` aria-describedby="${describedBy}"` : "";
  return `<button type="button"${focus ? ` data-next-focus="${esc(focus)}"` : ""} ` +
    `data-next-cockpit-action="${action}" data-arg="${kind}"` +
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
  /* The store exists and the server could not read it, so it wrote nothing:
     writing would keep only what it can read and lose every other session's
     words (`annotations.OUTCOME_UNTRUSTED`). The remedy is the file, not a
     retry, so the sentence names the file and the step, as every refusal
     names one:
     [NUI-18](docs/design-next-ui.md#nui-18-one-control-primitive-and-an-inert-control-stays-on-the-page). */
  untrusted: "Not saved. Cargento could not read cargento-annotations.json, so nothing was " +
    "saved and nothing was overwritten, and what you typed is still in the box. Move or " +
    "repair that file to save again.",
  "settle-untrusted": "Not settled. Cargento could not read cargento-annotations.json, so " +
    "nothing was saved and nothing was overwritten. Move or repair that file to settle again.",
  /* This session's own entry is one this build cannot read
     (`annotations.OUTCOME_UNREADABLE`): it is kept as it was, never saved over. */
  unreadable: "Not saved. This session's words were saved by a build of Cargento that can " +
    "read more than this one, so nothing was saved over them, and what you typed is still in " +
    "the box. Save from that build, or remove this session's entry from " +
    "cargento-annotations.json.",
};
/* The reply's `outcome` token (`annotations.OUTCOMES`) to the cue it earns. An
   unknown token, from a server newer than this page, falls back on
   `persisted`, which keeps its meaning across builds. */
const NEXT_COCKPIT_HELD_OUTCOME_CUES = {
  stored: "saved", unchanged: "unchanged", refused: "error", unwritable: "unpersisted",
  untrusted: "untrusted", unreadable: "unreadable",
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

/* The server's sentence while the annotation store cannot be read, or "".
   While it stands, no box may say nothing was typed: the words may be on disk
   in a file this build could not read (`annotations.store_notice`). */
function nextCockpitStoreUnreadable(){
  return String(nextData && nextData.annotate_unreadable || "");
}

/* The draft's marks in the goal's heading row: where the words came from,
   that an excerpt is one, and Looks right. Drawn while the box holds the
   draft; the input handler hides them on the first edit, because a keystroke
   does not redraw, and a box put back to the draft redraws them. */
function nextIntentDraftMarks(session, draft){
  const which = draft.source === "latest-prompt" ? " \u00b7 latest" : "";
  const clipped = draft.text.endsWith("\u2026") ? " Shown excerpt only." : "";
  return '<span class="next-intent-draft-marks" data-next-cockpit-draft-marks>' +
    `<span class="next-intent-draft-source">from your prompt${which}</span>` +
    (clipped ? `<span class="next-cockpit-held-cue">${clipped.trim()}</span>` : "") +
    '<button type="button" data-next-cockpit-action="draft-confirm" ' +
    `data-next-focus="${esc(nextCockpitHeldKey(session, "goal"))}:confirm" ` +
    `data-next-focus-fallback="${esc(nextCockpitHeldKey(session, "goal"))}">Looks right</button></span>`;
}

/* Where the Sessions goal link lands. Over an untouched draft it is the
   panel's heading, not the box: a focused box that holds still under the
   mouse cannot also grow to show the whole draft, and Keep adopts all of it
   (verifier V1). The heading is where the reading starts, above the draft and
   its marks. With nothing drafted the empty box is what the link offered. */
function nextCockpitIntentHeadingKey(session){
  return `intent:${sessKey(session)}`;
}

function nextCockpitGoalLanding(session){
  const annotation = nextCockpitAnnotation(session);
  const drafted = nextIntentDraft(session, annotation);
  const key = nextCockpitHeldKey(session, "goal");
  const untouched = Boolean(drafted) &&
    (!nextCockpitHeldDrafts.has(key) || nextCockpitHeldDrafts.get(key) === drafted.text);
  return untouched ? nextCockpitIntentHeadingKey(session) : key;
}

function nextCockpitHeldField(session, annotation, spec, cap){
  const [kind, label, valueKey, whyKey, placeholder] = spec;
  const key = nextCockpitHeldKey(session, kind);
  const stored = String(annotation && annotation[valueKey] || "");
  /* Over a goal-less session the box holds the drafted prompt, and the draft
     stands where the stored words would: `save` compares the box against it,
     so the untouched draft offers Looks right rather than a typed save of an
     excerpt (DRC-4682). */
  const drafted = kind === "goal" ? nextIntentDraft(session, annotation) : null;
  const saved = drafted ? drafted.text : stored;
  const draft = nextCockpitHeldDrafts.has(key) ? nextCockpitHeldDrafts.get(key) : saved;
  const untouched = Boolean(drafted) && draft === drafted.text;
  const why = nextCockpitStoreUnreadable() ? "" : String(annotation && annotation[whyKey] || "");
  const cue = nextCockpitHeldCue(key);
  return `<div class="next-cockpit-held-field" data-next-cockpit-held-field="${kind}"` +
    `${untouched ? " data-next-cockpit-drafted" : ""}>` +
    '<div class="next-cockpit-held-heading">' +
    `<span class="next-cockpit-held-label">${esc(label)}</span>` +
    (untouched ? nextIntentDraftMarks(session, drafted) : "") +
    (kind === "goal" ? nextPromptSourceLine(annotation) + nextPromptAdoptControls(session) : "") +
    /* The field's count and controls share its heading row, before the box in
       reading order as they are on screen: under the box they cost a second
       44px row in the panel's column (DRC-4680 fold). */
    `<span class="next-cockpit-held-count" data-next-cockpit-held-count="${kind}">` +
    `${draft.length}/${cap}</span>` +
    '<span class="next-cockpit-held-tools">' +
    nextCockpitHeldControl("held-clear", "clear", kind, Boolean(draft), false, "", `${key}:clear`) +
    nextCockpitHeldControl("held-save", "save", kind, draft !== saved, true,
      why ? nextCockpitHeldAbsentId(kind) : "", `${key}:save`) +
    '</span></div>' +
    `<textarea maxlength="${cap}" data-next-cockpit-held-kind="${kind}" ` +
    `data-next-cockpit-held-key="${esc(key)}" data-next-cockpit-held-saved="${esc(saved)}" ` +
    (drafted ? `data-next-cockpit-draft="${esc(drafted.text)}" ` : "") +
    `data-next-focus="${esc(key)}" placeholder="${esc(placeholder)}">${esc(draft)}</textarea>` +
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

/* The expected outcome, as a checklist of up to six lines (DRC-4685).

   One draft per session, an array held in `nextCockpitHeldDrafts` under the
   `lines` key, so adding, removing and typing survive a redraw as the goal's
   draft does; docs/design-reader-state.md holds the row. The saved list is
   what the store published. A box a reader emptied is still a box until the
   save, where the store drops it. With nothing saved and nothing drafted,
   one empty box is offered rather than none. */
function nextCockpitSavedLines(annotation){
  return nextAnnotationLines(annotation).map(line => line.text);
}

function nextCockpitLinesDraft(session, annotation){
  const key = nextCockpitHeldKey(session, "lines");
  return nextCockpitHeldDrafts.has(key) ? nextCockpitHeldDrafts.get(key).slice()
    : nextCockpitSavedLines(annotation);
}

/* Which saved line each draft line came from, by position, or null for one
   added here. Kept beside the draft so the save can say it, and the store can
   give a line its own source when two lines share text: deleting the first of
   two lends the survivor its own entry, not the deleted one's. */
const nextCockpitHeldOrigins = new Map();

function nextCockpitLinesOrigins(key, draft){
  const held = nextCockpitHeldOrigins.get(key);
  return held && held.length === draft.length ? held.slice() : draft.map((_text, index) => index);
}

function nextCockpitLinesKeep(key, draft, origins){
  nextCockpitHeldDrafts.set(key, draft);
  nextCockpitHeldOrigins.set(key, origins);
}

function nextCockpitLinesForget(key){
  nextCockpitHeldDrafts.delete(key);
  nextCockpitHeldOrigins.delete(key);
}

// What a save would send: the lines with words in them, in order.
function nextCockpitLinesToSend(draft){
  return draft.filter(text => String(text || "").trim());
}

function nextCockpitLinesChanged(draft, annotation){
  return JSON.stringify(nextCockpitLinesToSend(draft)) !==
    JSON.stringify(nextCockpitSavedLines(annotation));
}

/* Where a saved line came from, named by the entry itself (DRC-4697, owner
   2026-09-28): "added from #12" where the list numbers it, "added from your
   direction at 14:04" where it does not, from `line_N_source_id` on every
   render, as every "#<n>" here is. With no record read, or the entry gone from
   it, the kind of source alone. */
function nextCockpitLineSource(line, session, source){
  if(!line || line.source !== "entry" || !line.sourceId) return nextOutcomeLineSource(line);
  if(!source || (source.state !== "read" && source.state !== "empty")) return nextOutcomeLineSource(line);
  const n = nextCockpitEntryNumbers(session, source).get(line.sourceId);
  if(n != null) return `added from #${n}`;
  const entry = (source.all || source.entries || []).find(item => String(item.id || "") === line.sourceId);
  const at = entry ? nextNumber(entry.at) : null;
  return at != null && at > 0 ? `added from your direction at ${nextSessionClock(at)}`
    : nextOutcomeLineSource(line);
}

function nextCockpitHeldLines(session, annotation, cap, source = null){
  const key = nextCockpitHeldKey(session, "lines");
  const saved = nextAnnotationLines(annotation);
  const draft = nextCockpitLinesDraft(session, annotation);
  const boxes = draft.length ? draft : [""];
  const full = draft.length >= NEXT_OUTCOME_LINES_MAX;
  const why = nextCockpitStoreUnreadable() ? "" : String(annotation && annotation.lines_why || "");
  const cue = nextCockpitHeldCue(key);
  /* Where an open later direction already says the list is full beside its own
     save, the list's sentence is hidden rather than drawn twice (DRC-4760). Only
     then: the line checks saved lines and the list counts draft lines, and a line
     giving another reason would leave the disabled add control with none. It
     stays in the DOM for that control's `aria-describedby`. */
  const direction = nextCockpitDirectionLine(session, annotation, cap, source);
  const said = Boolean(direction) && nextCockpitDirectionSaysFull(session, annotation, cap);
  const rows = boxes.map((text, index) => {
    // The source is a fact about saved words, so it shows only while the box
    // still holds the line saved in that place. Its space is kept while it is
    // hidden, so the box does not widen under the caret (DRC-4714).
    const place = saved[index] || null;
    const line = place && place.text === text ? place : null;
    return `<li class="next-cockpit-held-line" data-next-cockpit-held-line="${index}">` +
      `<textarea rows="1" maxlength="${cap}" data-next-cockpit-held-line-index="${index}" ` +
      `data-next-cockpit-held-lines-key="${esc(key)}" ` +
      `data-next-cockpit-held-saved="${esc(place ? place.text : "")}" ` +
      `data-next-focus="${esc(`${key}:${index}`)}" ` +
      'placeholder="one thing that should exist when it is done">' +
      `${esc(text)}</textarea>` +
      `<span class="next-cockpit-held-count" data-next-cockpit-held-line-count="${index}">` +
      `${String(text).length}/${cap}</span>` +
      (place ? `<span class="next-cockpit-held-source" data-next-cockpit-held-line-source="${index}"` +
        `${line ? "" : " data-next-cockpit-held-line-source-stale"}>` +
        `${esc(nextCockpitLineSource(place, session, source))}</span>` : "") +
      `<button type="button" data-next-cockpit-action="held-line-remove" data-arg="${index}" ` +
      `data-next-focus="${esc(`${key}:remove:${index}`)}">remove</button></li>`;
  }).join("") + direction;
  const add = '<button type="button" data-next-cockpit-action="held-line-add" data-arg="lines"' +
    ` data-next-focus="${esc(`${key}:add`)}"` +
    (full ? ' aria-disabled="true" aria-describedby="next-cockpit-held-full"' : "") +
    ">add a line</button>";
  return '<div class="next-cockpit-held-field next-cockpit-held-lines" ' +
    'data-next-cockpit-held-field="lines">' +
    '<div class="next-cockpit-held-heading">' +
    '<span class="next-cockpit-held-label">Expected outcome</span>' +
    /* In the heading row, as the goal's are (DRC-4680 fold). */
    '<span class="next-cockpit-held-tools">' + add +
    nextCockpitHeldControl("held-save", "save", "lines", nextCockpitLinesChanged(draft, annotation),
      true, why ? nextCockpitHeldAbsentId("lines") : "", `${key}:save`) + '</span></div>' +
    `<ol class="next-cockpit-held-list">${rows}</ol>` +
    '<p class="next-cockpit-held-full" id="next-cockpit-held-full" data-next-cockpit-held-full' +
    `${full && !said ? "" : " hidden"}>${esc(NEXT_COCKPIT_LINES_FULL)}</p>` +
    (why ? `<p class="next-cockpit-held-absent" id="${nextCockpitHeldAbsentId("lines")}" ` +
      `data-next-cockpit-held-absent="lines"` +
      `${nextCockpitLinesToSend(draft).length ? " hidden" : ""}>${esc(why)}</p>` : "") +
    (cue ? `<small class="next-cockpit-held-cue">${esc(cue)}</small>` : "") + '</div>';
}

/* "Add it to my intent" (item 4 of
   [DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy),
   DRC-4682): a later direction's whole text, opened by `POST /api/direction`
   for the reader to review as one pending outcome line, and saved only by
   the `add_direction` arm of `/api/annotate`. Per session, beside the lines
   draft; docs/design-reader-state.md holds the row. `replace` counts from 0,
   as the server's does. */
const nextCockpitDirectionLines = new Map();
/* Never clipped on save: a line over the store's bound is refused, and the
   box holds the whole text with no `maxlength`, so nothing truncates it
   silently. */
function nextCockpitDirectionTooLong(cap){
  return `A line holds ${cap} characters. Shorten this one to add it.`;
}
const NEXT_COCKPIT_DIRECTION_CLIPPED =
  "Only the start of this direction is shown; it is longer than Cargento opens.";
const NEXT_COCKPIT_DIRECTION_UNOPENED =
  "Could not open that direction, so nothing was added. Press again to retry.";

/* Why the pending line cannot be saved as it stands, or "". An unsaved edit
   to the intent is one: the save would write the added line over words that
   are not on screen, and then drop the edit (consent F1, F2). Said here,
   beside the line the reader pressed save on, not in the Drift control. */
function nextCockpitDirectionWhy(held, annotation, cap, session = null){
  if(String(held.text || "").length > cap) return nextCockpitDirectionTooLong(cap);
  if(nextAnnotationLines(annotation).length >= NEXT_OUTCOME_LINES_MAX && held.replace == null){
    return NEXT_COCKPIT_LINES_FULL;
  }
  if(session && nextIntentUnsaved(session, annotation)) return NEXT_INTENT_EDITED_ADD;
  return "";
}

// Whether the open direction's reason is the list's own six-line sentence.
function nextCockpitDirectionSaysFull(session, annotation, cap){
  const held = nextCockpitDirectionLines.get(sessKey(session));
  return Boolean(held) && typeof held.text === "string" &&
    nextCockpitDirectionWhy(held, annotation, cap, session) === NEXT_COCKPIT_LINES_FULL;
}

function nextCockpitDirectionLine(session, annotation, cap, source = null){
  const key = sessKey(session);
  const held = nextCockpitDirectionLines.get(key);
  if(!held || typeof held.text !== "string") return "";
  /* From its fact id on every render, as every "#<n>" on the page is, and
     gone once its direction is no longer open: a number kept from the press
     can name a row the list no longer draws (layout F2, Codex 7). */
  const read = Boolean(source) && (source.state === "read" || source.state === "empty");
  /* Opened by Update intent instead, a direction an analysis's Keep already
     settled is still one to add (DRC-4697), so that line stands while its
     direction is any later direction; the question's own Add keeps the
     narrower open set. */
  const open = held.later
    ? nextCockpitLaterDirections(annotation, source.all || source.entries, session)
    : nextCockpitDirectionsOpen(session, annotation, source);
  if(read && !open.some(entry => String(entry.id || "") === held.factId)){
    nextCockpitDirectionLines.delete(key);
    return "";
  }
  const n = read ? nextCockpitEntryNumbers(session, source).get(held.factId) : held.n;
  const text = held.text;
  const why = nextCockpitDirectionWhy(held, annotation, cap, session);
  const ready = !why && Boolean(text.trim()) && !held.pending;
  const full = nextAnnotationLines(annotation).length >= NEXT_OUTCOME_LINES_MAX;
  const from = n != null ? `from #${n} \u00b7 not saved` : "from your direction \u00b7 not saved";
  const choose = full
    ? '<span class="next-cockpit-direction-replace"><span>Replace line</span>' +
      nextAnnotationLines(annotation).map((_line, index) =>
        `<button type="button" data-next-cockpit-action="direction-replace" data-arg="${index}" ` +
        `aria-pressed="${held.replace === index ? "true" : "false"}" ` +
        `aria-label="Replace line ${index + 1}" ` +
        `data-next-focus="direction-replace:${esc(key)}:${index}">${index + 1}</button>`).join("") +
      "</span>" : "";
  const cue = held.cue ? NEXT_COCKPIT_HELD_CUES[held.cue] || "" : "";
  return '<li class="next-cockpit-held-line next-cockpit-direction-line" data-next-cockpit-direction-line>' +
    `<textarea rows="1" data-next-cockpit-direction-key="${esc(key)}" ` +
    `data-next-focus="direction:${esc(key)}" aria-label="${esc(from)}">${esc(text)}</textarea>` +
    `<span class="next-cockpit-held-count" data-next-cockpit-direction-count>${text.length}/${cap}</span>` +
    `<span class="next-cockpit-held-source">${esc(from)}</span>` +
    '<span class="next-cockpit-direction-tools">' +
    '<button type="button" data-next-cockpit-action="direction-save" ' +
    `data-next-focus="direction-save:${esc(key)}"` +
    `${ready ? "" : ' aria-disabled="true"'}` +
    `${why ? ' aria-describedby="next-cockpit-direction-why"' : ""}>save</button>` +
    '<button type="button" data-next-cockpit-action="direction-cancel" ' +
    `data-next-focus="direction-cancel:${esc(key)}">remove</button></span>` + choose +
    '<p class="next-cockpit-held-full" id="next-cockpit-direction-why" data-next-cockpit-direction-why' +
    `${why ? "" : " hidden"}>${esc(why)}</p>` +
    (held.clipped ? `<p class="next-cockpit-held-full">${esc(NEXT_COCKPIT_DIRECTION_CLIPPED)}</p>` : "") +
    (cue ? `<small class="next-cockpit-held-cue">${esc(cue)}</small>` : "") + "</li>";
}

async function nextCockpitOpenDirection(session, factId, n, later = false){
  const key = sessKey(session);
  /* A second press while a line is pending goes to that line: reopening it
     would put the server's text back over the reader's edits (layout F2). */
  const open = nextCockpitDirectionLines.get(key);
  if(open && (open.opening || typeof open.text === "string")){
    if(!open.opening) renderNext({named: `direction:${key}`});
    return;
  }
  nextCockpitDirectionLines.set(key, {factId, n, later, opening: true});
  renderNext();
  let held;
  try{
    const response = await fetch("/api/direction", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({harness: session.harness, sid: session.sid, fact_id: factId})});
    const answer = response && typeof response.json === "function"
      ? await response.json().catch(() => null) : null;
    if(response && response.ok && answer && answer.ok === true && typeof answer.text === "string"){
      /* The store's own collapse, so a multi-line direction is the one line
         the store would hold. The scrub is not a summary. */
      held = {factId, n, later, text: answer.text.replace(NEXT_COCKPIT_HELD_UNSAFE, " "),
        clipped: answer.clipped === true, replace: null};
    }else if(response && response.ok && answer && answer.ok === false){
      held = {factId, n, later, error: String(answer.why || NEXT_COCKPIT_DIRECTION_UNOPENED)};
    }else{
      throw new Error("direction not opened");
    }
  }catch(_error){
    held = {factId, n, later, error: NEXT_COCKPIT_DIRECTION_UNOPENED};
  }
  nextCockpitDirectionLines.set(key, held);
  renderNext(held.error ? {} : {named: `direction:${key}`});
}

async function nextCockpitSaveDirection(session){
  const key = sessKey(session);
  const held = nextCockpitDirectionLines.get(key);
  if(!held || typeof held.text !== "string" || held.pending) return;
  const annotation = nextCockpitAnnotation(session);
  const cap = nextCockpitHeldCap();
  const why = nextCockpitDirectionWhy(held, annotation, cap, session);
  if(why || !held.text.trim()){
    if(why){
      nextCockpitAnnounceCue(`direction:${key}`, why, false);
      renderNext({named: `direction-save:${key}`});
    }
    return;
  }
  // Over a draft the one write adopts it, as the owner ruled.
  const draft = nextIntentDraft(session, annotation);
  const linesKey = nextCockpitHeldKey(session, "lines");
  held.pending = true;
  held.cue = "";
  renderNext();
  try{
    const response = await fetch("/api/annotate", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({harness: session.harness, sid: session.sid,
        add_direction: held.factId, text: held.text,
        expected_revision: nextNumber(annotation && annotation.revision) || 0,
        ...(held.replace != null ? {replace: held.replace} : {}),
        ...nextIntentAdoption(draft)})});
    if(!response || !response.ok) throw new Error(`HTTP ${response && response.status}`);
    const saved = await response.json();
    if(!saved || saved.ok !== true) throw new Error("save not confirmed");
    const outcome = String(saved.outcome || "");
    const kind = NEXT_COCKPIT_HELD_OUTCOME_CUES[outcome] ||
      (saved.persisted === true ? "saved" : "unpersisted");
    let typed = false;
    if(kind === "saved" || kind === "unchanged"){
      nextCockpitDirectionLines.delete(key);
      nextIntentForgetAdopted(session, draft);
      /* A lines draft still equal to the list this save stood on would hide
         the added line and delete it at the next line save, so it goes. One
         the reader changed while the save was open is theirs: it stays, and
         takes the stored line below (verifier V2). */
      const lines = nextCockpitHeldDrafts.get(linesKey);
      if(lines && !nextCockpitLinesChanged(lines, annotation)) nextCockpitLinesForget(linesKey);
      else if(lines && kind === "saved") typed = true;
      nextCockpitHeldMark(linesKey, kind);
    }else{
      held.cue = kind;
    }
    await refreshNext();
    /* A poll that starts while that refresh is open supersedes it, and the
       superseded one returns without publishing, so the merge read the
       pre-save row: measured live (verifier F1). Refresh again, a bounded
       number of times, until the row carries the revision the save minted. */
    const minted = nextNumber(saved.revision) || 0;
    for(let tries = 0; typed && tries < 3 && nextCockpitRowRevision(session) < minted; tries += 1){
      await refreshNext();
    }
    const typing = typed ? nextCockpitHeldDrafts.get(linesKey) : null;
    if(typing) nextCockpitLinesTakeAdded(session, linesKey, typing, held, annotation);
  }catch(_error){
    held.cue = "error";
  }finally{
    held.pending = false;
    renderNext();
  }
}

// The session's row as the latest refresh published it, by harness and sid.
function nextCockpitCurrentRow(session){
  return nextRows().find(row => row && row.harness === session.harness &&
    row.sid === session.sid) || session;
}

function nextCockpitRowRevision(session){
  const annotation = nextCockpitAnnotation(nextCockpitCurrentRow(session));
  return nextNumber(annotation && annotation.revision) || 0;
}

/* The stored line, and its place in the store's new list as its origin, join
   a lines draft the reader typed into while Add's save was open. The origin
   counts only once the refresh has published the revision the save minted;
   before that the line is offered as added here, and the store gives it a
   source of its own. A replace takes the place of the line it replaced where
   the draft still holds that line untouched. The stored list is read from
   the row the refresh published: the poll hands the page a new object, so
   the one this save captured never moves (verifier F1). */
function nextCockpitLinesTakeAdded(session, key, draft, held, before){
  const annotation = nextCockpitAnnotation(nextCockpitCurrentRow(session));
  const saved = nextCockpitSavedLines(annotation);
  const moved = (nextNumber(annotation && annotation.revision) || 0) >
    (nextNumber(before && before.revision) || 0);
  const index = held.replace != null ? held.replace : saved.length - 1;
  const text = moved && saved[index] != null ? saved[index] : held.text;
  const origin = moved && saved[index] != null ? index : null;
  const lines = draft.slice();
  const origins = nextCockpitLinesOrigins(key, draft);
  const replaced = held.replace != null ? nextCockpitSavedLines(before)[held.replace] : null;
  const at = replaced != null ? origins.indexOf(held.replace) : -1;
  if(at >= 0 && moved && lines[at] === replaced){
    lines[at] = text;
    origins[at] = origin;
  }else{
    lines.push(text);
    origins.push(origin);
  }
  nextCockpitLinesKeep(key, lines, origins);
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
/* Which harnesses' work is read at all, ahead of what this one's record is
   (owner, DRC-4734): once Pi's checks were read too, a line naming only this
   harness left the reader to guess whether any other was. */
const NEXT_COCKPIT_WORK_READ_FROM = "Cargento reads work results from Claude Code and Pi only.";

function nextCockpitWorkEvidenceLimit(harness){
  return `${NEXT_COCKPIT_WORK_READ_FROM} ${nextCockpitWorkEvidenceOwn(harness)}`;
}

function nextCockpitWorkEvidenceOwn(harness){
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
  /* "Cargento reads those on Pi alone" stood here, and stopped being true
     when Claude Code's checks were read too. The panel's own harness limit is
     `nextDriftLevel`'s, so this line says only what the record above is. */
  return `${label} publishes no demonstrated work results, so nothing above is an ` +
    "inspected file, test or deliverable.";
}

/* The reading's Expected Output limit, apart from the record's own line. On
   Claude Code it is lifted only where the route names where the checks go, so
   a reading can carry them after the reader allows tool output, under item 7 of
   [DEC-23](docs/design-reading-a-session.md#dec-23-a-claude-code-sessions-record-of-its-checks-may-show-the-work).
   Where it cannot name that, no check is sent and the demotion stays. */
function nextReadingOutputLimit(harness){
  if(harness === "pi") return "";
  const label = nextHarnessLabels().get(harness) || nextCockpitHumanLabel(harness);
  /* Its own sentence, not the record's: this row is in the panel and the
     record is in the activity column beside it, so the record line's "above"
     would point the wrong way here (DRC-4680 review, C-5). */
  if(harness !== "claude"){
    return `${label} publishes no demonstrated work results, so nothing in this session\u2019s ` +
      "observed record is an inspected file, test or deliverable.";
  }
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
    /* The fact id breaks a tie, so two checks with one call time (`bash -c
       "pytest && ruff"`) number the same whatever order the payload sent. */
    .sort((left, right) => (Number(left.at || 0) - Number(right.at || 0)) ||
      (String(left.fact_id || "") < String(right.fact_id || "") ? -1
        : String(left.fact_id || "") > String(right.fact_id || "") ? 1 : 0))
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
        resultAt: fact.result_at,
        actorClaim: String(fact.actor_claim || ""),
        modelDerived: String(fact.actor_claim || "").startsWith("model-derived"),
        subject: String(fact.subject || ""),
        copied: fact.copied === true,
        work: nextReadingWorkOn(session && session.harness, fact.type),
        result: String(fact.result || ""),
        resultSource: String(fact.result_source || ""),
        earlierFailed: fact.earlier_failed === true,
        beforeLastChange: fact.before_last_change === true,
        changedAfter: fact.changed_after === true,
        readIncomplete: fact.read_incomplete === true,
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

/* The observed last turn of a session waiting at its prompt, inside the
   evidence window (item 13 of
   [DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy)):
   from the reader's latest message at or before the stop, or the window start
   if later, up to the stop. Not from the window start to the save: that range
   is fixed when the words are saved, so the next turn made it name an older
   one. Null on every other session and where no message opens the turn,
   because a label nothing measured would be the board authoring a turn. */
function nextCockpitLastTurn(session, entries){
  if(!NEXT_READING_TURN_STOP_HARNESSES.includes(String(session && session.harness || ""))) return null;
  if(nextSessionEndedAt(session) != null) return null;
  const stop = nextNumber(session.finished_at);
  if(!(session.state === "idle" && stop > 0)) return null;
  const opened = nextNumber(session.annotation_window_start);
  const starts = (entries || []).filter(nextReadingPersonAuthored)
    .map(entry => nextNumber(entry.at)).filter(at => at != null && at > 0 && at <= stop);
  if(opened == null || !starts.length) return null;
  const from = Math.max(opened, ...starts);
  return from <= stop ? {from, to: stop} : null;
}

/* Where the numbers start: the evidence window of the saved words, and the
   whole record where nothing is saved or the store is off (owner, DRC-4694).
   Read from the session's own published start, the one the producer reads
   from, so the list's #1 and a reading's window are one moment. */
function nextCockpitEntryWindow(session){
  if(!(nextData && nextData.annotate === true)) return null;
  const opened = nextNumber(session && session.annotation_window_start);
  return opened != null && opened > 0 ? opened : null;
}

/* The numbers, recomputed from the fact ids on every render and never stored
   ([DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy)
   item 11). Over the full set, never the listed rows, for the reason citations
   resolve against it. An untimed entry cannot be placed in a window, so it is
   counted and not numbered. Stable only while entries arrive at the end: the
   four causes that renumber are in
   [DEC-24](docs/design-reading-a-session.md#what-the-numbering-build-decided-2026-09-25). */
function nextCockpitEntryNumbering(session, source){
  const all = (source && (source.all || source.entries)) || [];
  const opened = nextCockpitEntryWindow(session);
  const numbers = new Map();
  const earlier = [];
  const untimed = [];
  for(const entry of all){
    const at = nextNumber(entry && entry.at);
    if(at == null || at <= 0) untimed.push(entry);
    else if(opened != null && at < opened) earlier.push(entry);
    else numbers.set(entry, numbers.size + 1);
  }
  return {all, opened, numbers, earlier, untimed};
}

/* Fact id to its number, for the panel's "#<n>" (DRC-4695, DRC-4681) to read
   rather than recount. */
function nextCockpitEntryNumbers(session, source){
  const {numbers} = nextCockpitEntryNumbering(session, source);
  return new Map([...numbers].map(([entry, n]) => [String(entry.id || ""), n]));
}

function nextCockpitEntryActor(entry){
  const author = nextReadingAuthor(entry);
  /* You pasted it, and Cargento wrote it: the meta says which. */
  if(author === "person" || nextReadingCopied(entry)) return "You";
  /* Cargento's own paraphrase is never credited to the agent, which is the
     rule `nextReadingAuthor` records for a reading. */
  return author === "derived" ? "Cargento’s summary" : "Agent";
}

function nextCockpitEntryCount(n){
  return `${n} ${n === 1 ? "entry" : "entries"}`;
}

/* "A, B and C", for the bound sentence's clauses. */
function nextCockpitJoinClauses(parts){
  return parts.length < 2 ? parts.join("")
    : `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
}

/* The clause for entries that are counted and not listed, naming the ones a
   departure cites, which are listed anyway with their time and no number. */
function nextCockpitUnlistedClause(count, what, cited, timed = true){
  const are = count === 1 ? "is" : "are";
  /* An untimed entry has no time to list it with (review F2). */
  const how = timed ? `with ${cited === 1 ? "its" : "their"} time and no number` : "with no number";
  const except = !cited ? ""
    : `, except ${cited === 1 ? "the one" : `the ${cited}`} the analysis cites, listed ${how}`;
  return `${count} ${what} ${are} counted and not listed${except}.`;
}

/* The session's activity, numbered (DRC-4694). It sits right after CURRENT
   ACTIVITY in the activity column, under the column's own "Session activity"
   heading, so it has none of its own. `cited` is the set of fact ids the
   current reading's surviving departures rest on. */
function nextCockpitWorkEvidence(session, source, cited = new Set()){
  const numbering = nextCockpitEntryNumbering(session, source);
  const {all, numbers, earlier, untimed, opened} = numbering;
  const annotation = nextData && nextData.annotate === true ? nextCockpitAnnotation(session) : null;
  const later = new Set(nextCockpitLaterDirections(annotation, all, session));
  /* Every unsettled later direction is drawn at its own number, as a cited
     entry is, so the "#<n>" the question before the press names is always a
     row on screen (owner, DRC-4682). One from before the window has no number
     and is drawn with its time, as a cited earlier entry is, and is not
     counted among the earlier entries left unlisted (layout F1). A settled one
     takes the bound. */
  const open = new Set(nextCockpitConflictCandidates(annotation, all, session));
  /* The readability bound, as before: the newest non-tool rows, every listed
     check and file, and now every entry a departure cites, each at its own
     number so the gaps show. A cited entry is always drawn, so it is
     reachable without an expand control. */
  const numbered = all.filter(entry => numbers.has(entry));
  const recent = new Set(numbered.filter(entry => entry.type !== "tool_report")
    .slice(-NEXT_COCKPIT_WORK_ROWS));
  const isCited = entry => cited.has(String(entry && entry.id || ""));
  const entries = all.filter(entry => isCited(entry) || open.has(entry) ||
    (numbers.has(entry) && (entry.type === "tool_report" || recent.has(entry))));
  const lastTurn = nextCockpitLastTurn(session, all);
  const rows = entries.map(entry => {
    const at = nextDurationSince(entry.at);
    const stamp = nextNumber(entry.at);
    const n = numbers.get(entry);
    const turn = lastTurn && stamp != null && stamp >= lastTurn.from && stamp <= lastTurn.to &&
      !nextReadingPersonAuthored(entry)
      ? '<span class="next-cockpit-work-turn">from the last turn</span>' : "";
    /* A model's paraphrase takes the third treatment, not the mono of a
       string a source published. It is the same rule the reading block
       follows, and the reason is the same: the reader must be able to tell
       the record from an account of it. */
    const summary = entry.modelDerived
      ? `<em class="next-cockpit-work-derived">${esc(entry.summary)}</em>`
      : `<span class="next-cockpit-work-summary">${esc(entry.summary)}</span>`;
    /* A check's or a written file's line already reads actor · meta. Every
       other row takes the design's actor and meta: "Prompt" for your message,
       the fact's own type string otherwise, never a count nothing measured. */
    const head = entry.type === "tool_report"
      ? `<span class="next-cockpit-work-result">${esc(nextCockpitToolReportLine(entry))}</span>`
      : `<span class="next-cockpit-work-actor">${esc(nextCockpitEntryActor(entry))}</span>` +
        `<span class="next-cockpit-work-type">${esc(nextReadingCopied(entry)
          ? "Copied from Cargento" : entry.type === "user_message" ? "Prompt" : entry.type)}</span>`;
    /* Neutral tags: neither is a finding. "Cited" says a departure rests on
       the entry, and a later direction is never called drift
       ([DEC-16](docs/design-reading-a-session.md#dec-16-cargento-does-not-write-into-a-session)). */
    const flags = (later.has(entry)
      ? '<span class="next-cockpit-work-flag" data-next-entry-flag="later">' +
        "A later direction you gave</span>" : "") +
      (isCited(entry)
        ? '<span class="next-cockpit-work-flag" data-next-entry-flag="cited">Cited</span>' : "");
    return `<div class="next-cockpit-work-row" role="listitem" ` +
      `data-next-cockpit-work-type="${esc(entry.type)}"` +
      `${n == null ? "" : ` data-next-entry="${n}"`} data-next-entry-id="${esc(entry.id)}">` +
      `<span class="next-cockpit-work-n">${n == null
        ? '<span class="next-visually-hidden">not numbered</span>' : `#${n}`}</span>` +
      `<div class="next-cockpit-work-body"><div class="next-cockpit-work-head">${head}${flags}` +
      `</div>${summary}` +
      `<span class="next-cockpit-work-source">${esc(entry.source || "Source not published")}` +
      /* Only where it says something the source line does not. On most fact
         types `actor_claim` IS the evidence source, and appending it printed
         "timestamped non-meta user-role record · exact · timestamped non-meta
         user-role record". Caught by walking the board, not by the suite. */
      `${entry.actorClaim && !entry.source.includes(entry.actorClaim)
        ? ` · ${esc(entry.actorClaim)}` : ""}</span>` +
      `<span class="next-cockpit-work-at">${esc(at == null ? "time not published" : `${at} ago`)}` +
      `</span>${turn}</div></div>`;
  }).join("");
  /* Where the words' window opens, a message of the reader's should sit: the
     latest one at or before the save for typed words, the prompt itself for
     adopted ones. A window at the save time is typed words with no earlier
     message, and nothing is expected there. */
  const promptSource = annotation && ["latest-prompt", "first-prompt"].includes(annotation.goal_source);
  const saved = nextNumber(annotation && annotation.at);
  const expected = opened != null && (promptSource || (saved != null && opened < saved));
  const anchor = expected && numbers.size && !all.some(entry => nextNumber(entry.at) === opened)
    ? `<p class="next-cockpit-work-anchor">${earlier.length
      ? "No entry in the record read here sits where your intent’s window opens, so #1 is " +
        "the first entry after that point."
      : "The record read here no longer reaches back to where your intent’s window opens, " +
        "so #1 is the first entry it holds after that point."}</p>` : "";
  const unlisted = [];
  const unasked = earlier.filter(entry => !open.has(entry));
  if(unasked.length){
    unlisted.push(nextCockpitUnlistedClause(unasked.length,
      `earlier ${unasked.length === 1 ? "entry" : "entries"}, from before your intent’s ` +
      "window opened,", unasked.filter(isCited).length));
  }
  if(untimed.length){
    unlisted.push(nextCockpitUnlistedClause(untimed.length,
      `${untimed.length === 1 ? "entry" : "entries"} with no published time`,
      untimed.filter(isCited).length, false));
  }
  /* Every figure from the rows drawn and the numbers given, never authored. */
  const listed = entries.filter(entry => numbers.has(entry));
  const bound = listed.length < numbers.size
    ? `<p class="next-cockpit-work-dropped">Listing ${listed.length} of ` +
      `${nextCockpitEntryCount(numbers.size)}: ${nextCockpitJoinClauses([
        `the ${recent.size} most recent`,
        /* In the window: a check or file from before it is counted with the
           earlier entries, so "every" is true only of this set (review F3). */
        ...(listed.some(entry => entry.type === "tool_report")
          ? ["every check and file in the window"] : []),
        ...(listed.some(entry => isCited(entry) && entry.type !== "tool_report" &&
          !recent.has(entry)) ? ["every entry the analysis cites"] : []),
        ...(listed.some(entry => open.has(entry) && !isCited(entry) && !recent.has(entry))
          ? ["every later direction still to settle"] : []),
      ])}. ${numbers.size - listed.length} ${numbers.size - listed.length === 1 ? "is" : "are"} ` +
      "counted and not listed.</p>" : "";
  /* Nothing numbered while the record holds entries is a fact about the
     window, not an empty record: "No entry names this session" beside a count
     of the entries it holds was false (review F1). */
  const unnumbered = !numbers.size && (earlier.length || untimed.length)
    ? '<p class="next-cockpit-work-absent">' + (earlier.length
      ? "No entry in the record read here is from after your intent\u2019s window opened, so " +
        "none is numbered."
      : "No entry in the record read here has a published time, so none is numbered.") + "</p>"
    : "";
  return '<section class="next-cockpit-work" data-next-cockpit-work>' + anchor + unnumbered +
    (rows ? `<div class="next-cockpit-work-rows" role="list">${rows}</div>`
      : unnumbered ? ""
      : '<p class="next-cockpit-work-absent">' + `${esc(nextCockpitWorkAbsence(source))}</p>`) +
    (numbered.length ? `<p class="next-cockpit-work-mix">${esc(nextCockpitWorkMix(numbered))}</p>`
      : "") +
    unlisted.map(said => `<p class="next-cockpit-work-earlier">${esc(said)}</p>`).join("") +
    (source.scan ? `<p class="next-cockpit-work-checks">${esc(nextCockpitCheckScan(source.scan))}` +
      "</p>" : "") + bound +
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
  let copied = 0;
  let derived = 0;
  let summaries = 0;
  let work = 0;
  for(const entry of entries){
    if(nextReadingPersonAuthored(entry)) directions += 1;
    else if(nextReadingCopied(entry)) copied += 1;
    else if(entry.modelDerived) derived += 1;
    else if(String(entry.type || "") === "observer_snapshot") summaries += 1;
    else work += 1;
  }
  const parts = [`${entries.length} ${entries.length === 1 ? "entry" : "entries"}`];
  if(directions) parts.push(`${directions} ${directions === 1 ? "direction" : "directions"} you gave`);
  if(copied) parts.push(`${copied} copied from Cargento`);
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
// Rule 6: the goal and each outcome line, each naming itself, never blended.
// Keyed on identity so rule 7 needs no reading of the clause. `output` is the
// single expected output a reading stored before the checklist carries; the
// store reads it back as `line_1`, and a tab left open across the upgrade can
// still hold it.
const NEXT_READING_OUTCOME_LINE = /^line_([1-9][0-9]*)$/;

function nextReadingIsOutcomeLine(key){
  const match = NEXT_READING_OUTCOME_LINE.exec(String(key));
  return key === "output" || Boolean(match && Number(match[1]) <= NEXT_OUTCOME_LINES_MAX);
}

function nextReadingNamesConstraint(key){
  return key === "goal" || nextReadingIsOutcomeLine(key);
}

/* The constraints a reading's rows are drawn for, goal first and then each
   line in order: the constraints the READING read, from its own criteria,
   and never today's lines. A line typed after the reading was never asked,
   and drawing it made the row say the reading failed on it. The goal alone
   falls back to today's words, because every reading asks it. */
/* `current` is a reading of the words shown now: then every line typed now
   was a line it read, and one it returned no result for is drawn as missing
   rather than left out (item 14 of
   [DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy)). */
function nextReadingConstraints(rows, annotation, current = false){
  const typed = current
    ? nextAnnotationLines(annotation).map(line => `line_${line.k}`) : [];
  const keys = new Set(["goal", ...Object.keys(rows || {}).filter(nextReadingNamesConstraint),
    ...typed.filter(key => !(rows && rows.output && key === "line_1"))]);
  const order = key => key === "goal" ? 0 : key === "output" ? 1
    : Number(NEXT_READING_OUTCOME_LINE.exec(key)[1]);
  return [...keys].sort((left, right) => order(left) - order(right))
    .filter(key => (rows && rows[key]) || String(annotation && annotation[key] || "").trim())
    .map(key => [key, key === "goal" ? "TYPED GOAL" : key === "output" ? "EXPECTED OUTCOME"
      : `EXPECTED OUTCOME · LINE ${order(key)}`]);
}
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
const NEXT_READING_ASSESSMENT_KEYS = ["goal_source", "goal_source_at", "revision_read", "revision_read_at", "window_start", "read_at", "stamp", "cutoff",
  "scope", "scope_text", "ended_at_read", "evidence_through", "criteria"];
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
const NEXT_READING_SAVE_STEP = "Save a goal above to analyze drift.";
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
/* The analyzing box (DRC-4686). "Analyzing drift" rather than the design's
   "Analyzing N turns": Claude Code supplies no stable turn identity, so the
   word is not used for it (item 11 of
   [DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy)). The step names are the server's,
   one per real phase, so this page never words a phase it did not see. */
const NEXT_READING_JOB_TITLE = "Analyzing drift";
const NEXT_READING_JOB_NOTE = "You can keep working. The result will appear here.";
const NEXT_READING_BACKGROUND = "Runs in the background.";
/* A lost answer does not establish that the cancel missed, nor that it landed. */
const NEXT_READING_CANCEL_FAILED =
  "Could not confirm the cancel. The analysis may still be running; refresh to check.";
const NEXT_READING_MODEL_OFF =
  "Model calls are off for this run. Restart without --no-observer-model or its alias " +
  "--no-harness-usage to allow a reading.";
/* A build constant, not a run setting, so no flag or press on this page lifts
   it and the sentence names none: it says what it waits on. */
const NEXT_READING_UNAUTHORIZED =
  "Analyzing drift is not enabled in this build, because the abstention check that " +
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
  "Who would read this session is not published, so no analysis is offered. " +
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
/* A pass a later command may have changed files after (`changed-after-check`),
   and an expected output not put to the reading because no check had room
   (`checks-not-read`). Both known only to the producer, so read from the store. */
const NEXT_READING_CHANGED_AFTER_CHECK =
  "The check it cited passed, and a later command may have changed files, so it does not " +
  "show this.";
const NEXT_READING_CHECK_READ_INCOMPLETE =
  "The check passed, but part of the work record was not read, so it does not show this.";
const NEXT_READING_CHECKS_NOT_READ =
  "No check this session recorded had room in the reading, so your expected output was not " +
  "put to it.";
/* A line about what the agent tells the reader (`tells-the-person`), read
   from the store: the rule keys on the line's whole text, which the page does
   not re-read. */
const NEXT_READING_TELLS_THE_PERSON =
  "This line is about what the session told you, and nothing in the record can show that, " +
  "so it reads as not verifiable.";
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
  "changed-after-check": NEXT_READING_CHANGED_AFTER_CHECK,
  "check-read-incomplete": NEXT_READING_CHECK_READ_INCOMPLETE,
  "checks-not-read": NEXT_READING_CHECKS_NOT_READ,
  "tells-the-person": NEXT_READING_TELLS_THE_PERSON,
};

/* Who wrote an evidence entry. A closed set on the person side, because the
   asymmetry in rule 7 turns on it and a truthy check would count every
   unfamiliar type as a person's words. A gate decision is a person's only
   where the source records one. */
/* A message the server recognised as a correction the reader copied from
   Cargento is Cargento's words (DRC-4678, `reading.COPIED_FLAG`): not theirs
   here, so not a later direction and not a turn's start either. */
function nextReadingCopied(entry){
  return String(entry && entry.type || "") === "user_message" && entry.copied === true;
}

function nextReadingPersonAuthored(entry){
  const type = String(entry && entry.type || "");
  if(type === "user_message") return entry.copied !== true;
  return type === "gate_decision" && String(entry && entry.by || "").startsWith("person:");
}

/* Which entries demonstrate that work happened, as opposed to describing or
   requesting it. Rule 7 was keyed on WHO wrote an entry and the captain
   amended it on 2026-09-10, because as written it inverted its own reason:
   the reason is "self-report is not evidence of a deliverable", and a
   REQUEST is not evidence of one either. Keyed on authorship, citing the
   reader's own words licensed a `consistent` about her own deliverable while
   citing the actual work result demoted. */
/* Per harness, as `reading.WORK_EVIDENCE_BY_HARNESS` says and
   `ReadingVocabularyIsSpeltOnceTest` compares: `result` is Pi's work result
   and, on Codex, the agent's own final answer, which is self-report. */
const NEXT_READING_WORK_BY_HARNESS = {pi: ["work_result", "result"], claude: ["tool_report"]};

function nextReadingWorkOn(harness, type){
  const types = NEXT_READING_WORK_BY_HARNESS[String(harness || "")];
  return Array.isArray(types) && types.includes(String(type || ""));
}

function nextReadingDemonstratesWork(entry){
  return Boolean(entry && entry.work === true);
}

/* `reading.evidence_at`: a check's result time where one was recorded, and
   its call time otherwise. It decides the window only; the numbering and every
   change comparison keep the call time (owner, DRC-4702). */
function nextReadingEvidenceAt(entry){
  const resultAt = nextNumber(entry && entry.resultAt);
  return resultAt != null && resultAt > 0 ? resultAt : nextNumber(entry && entry.at);
}

/* `reading._before_window`: an entry whose evidence cannot be placed at or
   after the window's start, earlier than it or with no time once one is open.
   A reading may not cite one (owner, DRC-4715); a test holds this to the
   producer's rule. A reading with no window start refuses nothing here. */
function nextReadingBeforeWindow(entry, windowStart){
  const at = nextReadingEvidenceAt(entry) || 0;
  const start = windowStart == null ? 0 : windowStart;
  return at < start || (start > 0 && at <= 0);
}

/* `reading.check_supports`, spelt for the entries the page holds: a check, on
   any harness (a Pi validation run as well as a Claude Code tool report),
   carries a verdict only as a run whose result arrived in the window, failed
   for a departure, passed, not before the last change and with no changing
   command after it for a consistent. A written path shows a write and no
   result, so it carries neither, and a subjectless Pi result an older build
   stored carries none (`reading._subjectless_pi_check`). Two tests hold this
   to the producer's rule, one from the server's own Pi fixture (DRC-4734). */
function nextReadingCheckSupports(entry, result, windowStart){
  const report = String(entry && entry.type || "") === "tool_report";
  if(!report && entry.subject !== "check") return !nextReadingSubjectlessPiCheck(entry);
  if(entry.subject !== "check") return false;
  const at = nextReadingEvidenceAt(entry);
  if(at == null || at <= 0 || (windowStart != null && at < windowStart)) return false;
  if(result === NEXT_READING_DEPARTURE) return entry.result === "failed";
  if(result === NEXT_READING_CONSISTENT){
    return entry.result === "passed" && !entry.beforeLastChange && !entry.changedAfter &&
      !entry.readIncomplete;
  }
  return false;
}

/* `reading._PI_CHECK_SOURCE_PREFIX`, spelt a third time for the page, which
   holds the entry's source as the ledger joins it. */
const NEXT_READING_PI_CHECK_SOURCE = "Pi bash tool call";

function nextReadingSubjectlessPiCheck(entry){
  return String(entry && entry.type || "") === "result" &&
    String(entry && entry.source || "").startsWith(NEXT_READING_PI_CHECK_SOURCE);
}

/* The third author, which the page did not have. An observer snapshot is
   Cargento's own paraphrase of the session: counting it as the agent's
   account overstates it, and counting it as a person's words overstates it
   much further. Keyed on the fact type rather than on the `model-derived`
   prefix, because all three observer actor claims are the same paraphrase
   and the prefix catches only one of them. */
function nextReadingAuthor(entry){
  if(nextReadingPersonAuthored(entry)) return "person";
  if(nextReadingCopied(entry)) return "derived";
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
/* Every later direction, settled or not. The activity list flags these and
   the conflict block below narrows them to the unsettled, so the two read one
   predicate and cannot disagree about who wrote a row or when. A settled one
   stays flagged: settling records that the baseline still applies, not that
   the reader never said it (owner, DRC-4694). */
/* Where "later" starts: the server's `annotations.direction_floor`, spelt
   for the page, so the list's flag, the question and `POST /api/direction`
   agree about which entries are later. Adopted words floor at their prompt; a
   typed goal at the save of its current words (`goal_saved_at`, carried
   unchanged by a lines-only save, falling back to the revision time an older
   build published); no goal at the draft's prompt (DRC-4682). A caller with no
   session keeps the revision time, which is what the page read before. */
function nextCockpitBaselineAt(annotation, session){
  if(annotation && ["latest-prompt", "first-prompt"].includes(annotation.goal_source)){
    return nextNumber(annotation.goal_source_at);
  }
  if(String(annotation && annotation.goal || "").trim()){
    const saved = nextNumber(annotation.goal_saved_at);
    return saved != null ? saved : nextNumber(annotation.at);
  }
  if(!session) return nextNumber(annotation && annotation.at);
  const draft = nextIntentDraft(session, annotation);
  return draft ? draft.at : null;
}

function nextCockpitLaterDirections(annotation, entries, session = null){
  const typedAt = nextCockpitBaselineAt(annotation, session);
  if(typedAt == null) return [];
  return (entries || []).filter(entry => {
    const at = nextNumber(entry && entry.at);
    return at != null && at > typedAt && nextReadingPersonAuthored(entry);
  });
}

function nextCockpitConflictCandidates(annotation, entries, session = null){
  const settled = nextNumber(annotation && annotation.settled_through);
  return nextCockpitLaterDirections(annotation, entries, session).filter(entry =>
    settled == null || nextNumber(entry.at) > settled);
}

function nextCockpitReadingCriterion(key, label, clause, raw, entries, limit, unsettled,
    windowStart = null){
  /* Refused like any citation that does not resolve. The producer never
     numbers such an entry, so this holds only for a reading stored before it
     stopped (DRC-4715). */
  let citations = nextReadingCitations(raw, entries)
    .filter(entry => !nextReadingBeforeWindow(entry, windowStart));
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
    const incompletePass = result === NEXT_READING_CONSISTENT && citations.some(entry =>
      entry.readIncomplete && nextReadingCheckSupports({...entry, readIncomplete:false},
        result, windowStart));
    const supporting = citations.filter(entry => nextReadingCheckSupports(entry, result, windowStart));
    droppedCheck = supporting.length < citations.length;
    citations = supporting;
    if(!citations.length){
      result = NEXT_READING_UNVERIFIABLE;
      why = incompletePass ? NEXT_READING_CHECK_READ_INCOMPLETE
        : NEXT_READING_CHECK_DOES_NOT_SHOW_IT;
    }
  }
  const shows = citations.filter(nextReadingDemonstratesWork);
  const authors = citations.map(nextReadingAuthor);
  const derivedOnly = authors.length > 0 && authors.every(name => name === "derived");
  if(nextReadingIsOutcomeLine(key) && result !== NEXT_READING_UNVERIFIABLE && !shows.length){
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
  /* What a consistent row names as its source, by the cited entry's type
     (item 6 of
     [DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy)):
     a tool outcome (a Claude Code tool report, or any harness's check) is what
     the tool reported, never an inspection; otherwise it is what the session
     said. The number is the list's, filled in where the row is drawn. */
  const tool = result === NEXT_READING_CONSISTENT
    ? citations.find(entry => String(entry.type || "") === "tool_report" ||
      entry.subject === "check") : null;
  const said = result === NEXT_READING_CONSISTENT && !tool
    ? citations.find(entry => nextReadingAuthor(entry) === "agent") : null;
  const restsOn = tool ? "tool" : said ? "agent" : "";
  const restsOnEntry = tool || said || null;
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
    why, restsOn, restsOnEntry, limit: limitText,
    // Mutually exclusive with `limit`, and never both blank: a row states its
    // evidence or states why it has none.
    evidence: limitText ? [] : citations.map(entry =>
      `${entry.type} · ${entry.source}`),
    /* The ids behind `evidence`, after every filter above, so the activity
       list flags exactly what this row still rests on. */
    citedIds: limitText ? [] : citations.map(entry => String(entry.id || "")),
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
/* A line's row names where the line came from, but only while the reading
   read the words shown now: under a reading of an older revision today's
   source would be a claim about words it never read. */
function nextCockpitLineLabel(key, label, row, annotation, historical,
    lineSource = nextOutcomeLineSource){
  const match = NEXT_READING_OUTCOME_LINE.exec(String(key));
  if(!match || historical) return label;
  const line = nextAnnotationLines(annotation).find(item => item.k === Number(match[1]));
  const clause = String(row && row.clause || "").trim();
  if(!line || (clause && clause !== line.text)) return label;
  return `${label} · ${lineSource(line).toUpperCase()}`;
}

function nextCockpitReadingClause(key, row, annotation, historical){
  const carried = String(row && row.clause || "").trim();
  if(carried) return carried;
  if(historical) return "";
  return String(annotation && annotation[key === "output" ? "line_1" : key] || "").trim();
}

/* Built and unexercised, and the tests below are not the contract they look
   like: nothing publishes an `assessment`, so every assertion about these
   seven rules is against an injected fixture rather than a payload
   ([the shape contract](docs/design-reading-a-session.md#dec-17-the-shape-contract)).
   Whoever adds a producer adds the published field with it and re-derives
   these assertions from that field. */
/* `lineSource` names a saved line's source; the panel passes the one that
   numbers an added line by the list ("added from #12"), as the saved line
   above it reads (DRC-4697), so the result renders it anew (DRC-4695). */
function nextCockpitReadingShape(raw, annotation, entries, limit, unsettled,
    lineSource = nextOutcomeLineSource){
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
  /* Where the evidence window opened for the revision this reading read, as
     the reading carries it, so a check before the words cannot carry a
     verdict on either side. A reading stored before it carried one opened
     where the producer's `baseline_at` did, and is derived that way. */
  const windowStart = nextNumber(source.window_start) != null ? nextNumber(source.window_start)
    : nextNumber(["latest-prompt", "first-prompt"].includes(source.goal_source)
      ? source.goal_source_at : source.revision_read_at);
  const constraints = nextReadingConstraints(rows, annotation,
    revisionRead != null && current != null && !historical);
  const criteria = constraints
    .map(([key, label]) => nextCockpitReadingCriterion(
      key, key === "goal" && ["latest-prompt", "first-prompt"].includes(source.goal_source)
        ? "GOAL FROM YOUR PROMPT"
        : nextCockpitLineLabel(key, label, rows[key], annotation, historical, lineSource),
      nextCockpitReadingClause(key, rows[key], annotation, historical),
      rows[key], entries, nextReadingIsOutcomeLine(key) ? limit : "", unsettled, windowStart));
  return {
    criteria,
    departures: criteria.filter(row => row.result === NEXT_READING_DEPARTURE),
    revisionRead,
    revisionReadAt: nextNumber(source.revision_read_at),
    windowStart,
    promptSource: ["latest-prompt", "first-prompt"].includes(source.goal_source),
    /* Through the same helper the criterion row uses, and filtered the same
       way. Read raw, the disclosure said "nothing typed in that revision" for
       an empty clause while the row beside it said the words were not
       retained: `_criterion` coerces a missing clause to "", so after a store
       round trip the two are indistinguishable and only one of those sentences
       can be honest. */
    readClauses: constraints
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
  if(nextCockpitStoreUnreadable()) return nextCockpitStoreUnreadable();
  if(!String(annotation && annotation.goal || "").trim() &&
      !nextAnnotationLines(annotation).length){
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

/* Each line's words, verbatim from item 6 of
   [DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy),
   and never "Done" or a check mark. The number is the activity list's own
   (`nextCockpitEntryNumbers`), so the "#<n>" is a row on screen; an entry the
   list does not number keeps its time instead, as a saved line added from an
   unnumbered entry does. */
const NEXT_RESULT_CANT_TELL = "Can't tell";
const NEXT_RESULT_NOTHING_SHOWS = "Can't tell: nothing recorded shows this yet";

function nextCockpitResultWhere(entry, numbers){
  if(!entry) return "";
  const n = numbers.get(String(entry.id || ""));
  if(n != null) return `#${n}`;
  const at = nextNumber(entry.at);
  return at != null && at > 0 ? nextSessionClock(at) : "";
}

function nextCockpitResultStatus(row, numbers, byId){
  if(row.result === NEXT_READING_DEPARTURE){
    const where = nextCockpitResultWhere(byId.get(String((row.citedIds || [])[0] || "")), numbers);
    return where ? `Departs at ${where}` : "Departs";
  }
  if(row.result === NEXT_READING_CONSISTENT && row.restsOn){
    const where = nextCockpitResultWhere(row.restsOnEntry, numbers);
    if(where){
      return row.restsOn === "tool"
        ? `Consistent with ${where}, as the tool reported; not inspected`
        : `Consistent with what the session said at ${where}; not a check`;
    }
  }
  /* A consistent the page cannot place is no claim it can word, so it is
     said as what it is to the reader: nothing shown. */
  return row.why || row.limit ? NEXT_RESULT_CANT_TELL : NEXT_RESULT_NOTHING_SHOWS;
}

function nextCockpitResultState(row){
  return row.result === NEXT_READING_DEPARTURE ? "departs"
    : row.result === NEXT_READING_CONSISTENT && row.restsOn ? "consistent" : "cant-tell";
}

function nextCockpitReadingCriterionRow(row, numbers = null, byId = null){
  const numbered = numbers instanceof Map ? numbers : new Map();
  const entries = byId instanceof Map ? byId : new Map(
    (row.restsOnEntry ? [row.restsOnEntry] : []).map(entry => [String(entry.id || ""), entry]));
  const tail = row.limit
    ? `<span class="next-cockpit-reading-limit">limit · ${esc(row.limit)}</span>`
    : row.evidence.map(line =>
      `<span class="next-cockpit-reading-evidence">${esc(line)}</span>`).join("");
  /* The departure's own account renders once, in the headline's account
     above the rows, with its citation. */
  return `<div class="next-cockpit-reading-row" data-next-result-state="${nextCockpitResultState(row)}">` +
    `<span class="next-cockpit-reading-name">${esc(row.label)}</span>` +
    nextCockpitReadingClauseCell(row) +
    `<em class="next-cockpit-reading-result">${esc(nextCockpitResultStatus(row, numbered, entries))}</em>` +
    (row.why ? `<span class="next-cockpit-reading-why">${esc(row.why)}</span>` : "") +
    tail + '</div>';
}

/* Item 14's answer reducer, over the rows after every page rule. Any valid
   departure departs, whatever the other lines say; otherwise a failed check in
   the reading's window, where a check with no time counts as inside it, as
   `levels.analysis_level` reads it; otherwise any line without a valid
   verdict, a malformed or missing result included, cannot tell; otherwise
   nothing was found. A reading with no outcome line cannot tell either: the
   goal row alone is not an answer against what the work was for. */
function nextDriftAnswer(shape, entries){
  const departures = shape.criteria.filter(row => row.result === NEXT_READING_DEPARTURE);
  if(departures.length) return {kind: "departs", count: departures.length, departures};
  const start = shape.windowStart;
  const failed = (entries || []).filter(entry => entry && entry.subject === "check" &&
    entry.result === "failed" && (start == null || (nextReadingEvidenceAt(entry) || start) >= start));
  if(failed.length){
    const latest = failed.reduce((a, b) =>
      (nextReadingEvidenceAt(b) || 0) >= (nextReadingEvidenceAt(a) || 0) ? b : a);
    return {kind: "failed-check", failed: latest};
  }
  const verdict = row => row.result === NEXT_READING_CONSISTENT && row.restsOn;
  if(!shape.criteria.some(row => nextReadingIsOutcomeLine(row.key)) ||
      !shape.criteria.every(verdict)) return {kind: "cant-tell"};
  return {kind: "nothing-found"};
}

const NEXT_RESULT_DEPARTS = "Departs from your intent";
const NEXT_RESULT_NOTHING_FOUND =
  "Nothing found against what it read. This is not a check that the work was done.";

/* The answer, and under a departure the headline with its count and a short
   account built from each departure's detail and its citation, never a
   model's narrative (item 6). The count renders only here. */
function nextCockpitResultAnswer(answer, numbers, byId){
  const open = '<div class="next-cockpit-result-answer">';
  if(answer.kind === "departs"){
    const count = `${answer.count} departure${answer.count === 1 ? "" : "s"}`;
    const account = answer.departures.map(row => {
      const where = nextCockpitResultWhere(byId.get(String((row.citedIds || [])[0] || "")), numbers);
      const detail = String(row.detail || "").trim();
      return detail
        ? `<p class="next-cockpit-reading-detail">${esc(detail)}${where ? ` (${esc(where)})` : ""}</p>`
        : "";
    }).join("");
    return open + '<p class="next-cockpit-result-headline">' +
      `<span>${NEXT_RESULT_DEPARTS}</span>` +
      `<span class="next-cockpit-result-count">${esc(count)}</span></p>${account}</div>`;
  }
  if(answer.kind === "failed-check"){
    const where = nextCockpitResultWhere(answer.failed, numbers);
    return open + `<p class="next-cockpit-result-line">${esc(where
      ? `A check failed at ${where}.` : "A check failed.")}</p></div>`;
  }
  return open + `<p class="next-cockpit-result-line">${esc(answer.kind === "cant-tell"
    ? NEXT_RESULT_CANT_TELL : NEXT_RESULT_NOTHING_FOUND)}</p></div>`;
}

/* Where the work went: the written paths in this analysis window,
   grouped by folder without a model (item 6). A path with no folder is the
   working directory, where `claude_tool_reports` publishes it relative to.
   The twelve-entry listing cannot count its own omissions; the scan supplies
   a distinct-path count for the same cutoff, including paths it did not list.
   A saved result keeps that cutoff even when the current intent window moves. */
function nextCockpitResultWork(entries, numbers, scan, resultWindow){
  const writes = (entries || []).filter(entry => entry && entry.type === "tool_report" &&
    entry.subject === "write" && nextNumber(entry.at) > 0 &&
    (resultWindow == null || entry.at >= resultWindow));
  const counted = scan && typeof scan === "object" &&
    nextNumber(scan.window_start) === resultWindow &&
    Number.isSafeInteger(scan.window_written_paths) && scan.window_written_paths >= 0
    ? scan.window_written_paths : null;
  if(!writes.length && !counted) return "";
  const groups = new Map();
  for(const entry of writes){
    const path = String(entry.summary || "");
    const cut = path.lastIndexOf("/");
    const folder = cut > 0 ? path.slice(0, cut) : "";
    if(!groups.has(folder)) groups.set(folder, []);
    groups.get(folder).push(entry);
  }
  const ordered = [...groups].sort((a, b) => b[1].length - a[1].length ||
    (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
  const items = ordered.map(([folder, rows]) => {
    const numbered = rows.filter(entry => numbers.has(String(entry.id || "")))
      .map(entry => `#${numbers.get(String(entry.id || ""))}`);
    const unnumbered = rows.length - numbered.length;
    const references = [...numbered,
      ...(unnumbered ? [`${unnumbered} not numbered in the current view`] : [])];
    return '<li class="next-cockpit-result-folder">' +
      `<span class="next-cockpit-result-path">${esc(folder || "The working directory")}</span>` +
      `<span>${rows.length} file${rows.length === 1 ? "" : "s"}</span>` +
      `<span>${esc(references.join(", "))}</span>` +
      '</li>';
  }).join("");
  const more = counted != null && counted >= writes.length ? counted - writes.length : 0;
  const unlisted = more
    ? `<p class="next-cockpit-reading-why">${more} more written ${more === 1 ? "file is" : "files are"} ` +
      "counted and not listed.</p>" : counted == null || counted < writes.length
      ? '<p class="next-cockpit-reading-why">The total written in this window is unavailable.</p>'
      : "";
  return '<div class="next-cockpit-result-work"><h3>Where the work went</h3>' +
    `<ul>${items}</ul>${unlisted}</div>`;
}

/* The two stale states of item 6, from the revision the reading read and the
   newest entry it saw (`evidence_through`), each with Analyze again where a
   press would run. The words changing says why with the revision sentence the
   raises use; new work is any entry after the reading's newest. A reading
   stored with no such time counts from when it read instead, so an older row
   still owns up to work that landed after it. */
function nextCockpitResultStale(shape, raw, annotation, entries, again){
  const current = nextNumber(annotation && annotation.revision);
  const superseded = nextRevisionSuperseded("This reading", shape.revisionRead, current);
  const evidence = nextNumber(raw && raw.evidence_through);
  const through = evidence != null ? evidence : nextNumber(raw && raw.read_at);
  const newer = !superseded && through != null &&
    (entries || []).some(entry => (nextNumber(entry && entry.at) || 0) > through);
  if(!superseded && !newer) return "";
  const head = superseded ? "Your intent changed after this analysis." : "New work since this analysis.";
  return `<div class="next-cockpit-result-stale" data-next-result-stale="${superseded ? "intent" : "work"}">` +
    `<p class="next-cockpit-result-stale-head">${head}</p>` +
    (superseded ? `<p class="next-cockpit-reading-stale">${esc(superseded)}</p>` : "") +
    again + '</div>';
}

/* Not accurate (item 10): a token on this reading, posted with the reading's
   time so a newer one is never marked by a tab drawn before it. Pressed again
   it takes the mark back. It is never sent anywhere else and never counted. */
const NEXT_RESULT_NOT_ACCURATE = "Not accurate?";
const NEXT_RESULT_MARKED = "You marked this analysis not accurate.";
const NEXT_RESULT_MARK_UNSAVED = "Your mark was not saved. Press Not accurate? again to retry.";
/* Per session, for the life of the tab: the one press whose mark the store
   did not take, until the next press. docs/design-reader-state.md holds the row. */
const nextCockpitNotAccurateUnsaved = new Set();

function nextCockpitResultFoot(session, annotation, raw){
  const readAt = nextNumber(raw && raw.read_at);
  if(readAt == null || !(nextData && nextData.annotate === true)) return "";
  const marked = annotation && annotation.not_accurate === true;
  const key = sessKey(session);
  return '<div class="next-cockpit-result-foot">' +
    '<button type="button" class="next-cockpit-result-mark" data-next-cockpit-action="not-accurate" ' +
    `data-arg="${esc(String(readAt))}" aria-pressed="${marked ? "true" : "false"}" ` +
    `data-next-focus="not-accurate:${esc(key)}">${NEXT_RESULT_NOT_ACCURATE}</button>` +
    (marked ? `<span class="next-cockpit-result-marked">${NEXT_RESULT_MARKED}</span>` : "") +
    (nextCockpitNotAccurateUnsaved.has(key)
      ? `<p class="next-cockpit-reading-why" role="status">${NEXT_RESULT_MARK_UNSAVED}</p>` : "") +
    '</div>';
}

async function nextCockpitMarkNotAccurate(session, readAt){
  const key = sessKey(session);
  const annotation = nextCockpitAnnotation(session);
  const on = !(annotation && annotation.not_accurate === true);
  nextCockpitNotAccurateUnsaved.delete(key);
  let saved = false;
  try{
    const response = await fetch("/api/annotate", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({harness: session.harness, sid: session.sid, not_accurate: on,
        read_at: readAt})});
    const answer = response && typeof response.json === "function"
      ? await response.json().catch(() => null) : null;
    saved = Boolean(response && response.ok && answer && answer.persisted !== false &&
      ["stored", "unchanged"].includes(String(answer.outcome || "")));
  }catch(_error){
    saved = false;
  }
  if(!saved) nextCockpitNotAccurateUnsaved.add(key);
  await refreshNext();
  renderNext({named: `not-accurate:${key}`});
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
    return nothing("This reading verified none of the constraints it read, so it raised nothing and " +
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
const NEXT_READING_DISCLOSURE_ID = "next-cockpit-reading-disclosure";

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

/* The short line beside an inert Analyze drift, one per token the board can
   publish as `reading_eligibility.reason` (`reading.PRESS_WITHHELD`, walked by
   a test). Page copy keyed by the server's token; the server's own sentence
   rides beside it, verbatim, under "Why it can't read". Codex, which reads
   only while a turn runs and has no session end the board can observe, gets
   its own line for both idle tokens (owner Q8, 2026-10-01). DRC-4758 slice B. */
const NEXT_READING_PRESS_LINES = {
  "idle-unknown": "Analyze opens once this session finishes a turn.",
  "unobservable": "No events reach Cargento from this session, so it can't be analyzed.",
  "turn-stop": "Analyze opens while a turn runs or once the session ends.",
  "settling": "Ready in a few seconds.",
  "stop-settling": "Ready in a few seconds.",
  "revision-after-end": "Your intent was saved after this session ended.",
};
const NEXT_READING_PRESS_CODEX = "Codex sessions can be analyzed only while a turn is running.";

/* Whether a press could read this row now, as the board published it, or as
   this tab's last press was answered when the board has not published it (a
   payload with annotations off, or one from before the field). Absent means
   not computed, and a press is then offered and the server decides. A
   settling row whose `until` has passed is read as eligible on the next
   render or press, with no timer of its own: the next collection drops the
   token anyway. */
function nextReadingEligibility(session){
  const published = session && session.reading_eligibility;
  const answered = nextCockpitReadingRequests.get(sessKey(session));
  const held = published && typeof published === "object" ? published
    : answered && answered.eligibility || null;
  if(!held || held.ok !== false || typeof held.reason !== "string") return null;
  const until = nextNumber(held.until);
  if(until != null && Date.now() / 1000 >= until) return null;
  return held;
}

function nextReadingPressLine(session, eligibility){
  const reason = String(eligibility.reason);
  if(String(session && session.harness || "") === "codex" &&
    ["idle-unknown", "turn-stop"].includes(reason)) return NEXT_READING_PRESS_CODEX;
  return NEXT_READING_PRESS_LINES[reason] || String(eligibility.sentence || "");
}

function nextReadingPressRefusal(session){
  const eligibility = nextReadingEligibility(session);
  return eligibility ? nextReadingPressLine(session, eligibility) : "";
}

/* How long ago a stored withhold was written, for "Last analysis, 3m ago:". */
function nextReadingWithheldAge(annotation){
  const at = nextNumber(annotation && annotation.reading_withheld_at);
  if(at == null) return "";
  const age = Math.max(0, (nextData && nextData.generated || 0) - at);
  return age < 60 ? "just now" : `${fmtDur(age)} ago`;
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
  if(policy.reason === "store-unavailable") return "Reading permission or its daily budget could not be read or saved. Restore access to the Cargento store before analyzing drift.";
  if(policy.reason === "daily-cap"){
    const at = nextNumber(policy.retry_at);
    return at == null ? "The daily reading limit is reached. Wait for the next update."
      : `The daily reading limit is reached. Try again after ${new Date(at * 1000).toLocaleString()}.`;
  }
  return "";
}

/* The running analysis for a session, from the published payload alone: a
   reload, another tab and this press all read the same job. */
function nextReadingJob(session){
  const jobs = nextData && nextData.reading_jobs;
  const job = jobs && typeof jobs === "object" ? jobs[sessKey(session)] : null;
  return job && typeof job === "object" && typeof job.id === "string" ? job : null;
}

/* Each step's state comes from where the published phase sits among them. A
   finished step is a filled mark, never a check mark: a check beside a
   reading is the shape item 6 of
   [DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy)
   keeps off every result. An unknown phase
   marks every step still to come rather than guessing which one is running. */
function nextReadingJobBox(job, key){
  const steps = Array.isArray(job.steps) ? job.steps : [];
  const at = steps.findIndex(step => step && step.phase === job.phase);
  const items = steps.map((step, index) => {
    const state = at < 0 || index > at ? "todo" : index < at ? "done" : "active";
    return `<li class="next-cockpit-reading-step" data-state="${state}"` +
      `${state === "active" ? ' aria-current="step"' : ""}>` +
      '<span class="next-cockpit-reading-step-mark" aria-hidden="true"></span>' +
      `<span>${esc(String(step && step.text || ""))}</span></li>`;
  }).join("");
  /* Cancel sits in the header row beside the title, as the design draws it.
     While a cancel is finishing it keeps its label and is disabled, from the
     published `cancelling` so a reload draws the same; a request of this
     page's own still in flight disables it too. The press button's focus key
     goes to the title, not to Cancel: on Cancel, a keyboard press followed by
     a second Enter cancelled the analysis it had just started, which is a
     spent attempt (S6 review, P-1). Cancel's own key falls back to the press,
     so focus lands there again when the box goes.
     `data-next-analyzing` is the hook DRC-4680's meter dims on. */
  const held = nextCockpitReadingCancels.get(key);
  const mine = held && held.job === job.id ? held : null;
  const finishing = job.cancelling === true || Boolean(mine && mine.pending);
  /* No role: the box is inside `#app`, which every render rebuilds, so a
     status role re-announced it on each revision while the job ran
     (DRC-4736). Its start and its outcome go once each through the
     persistent region instead (`nextCockpitReadingJobCues`). */
  nextCockpitReadingJobsDrawn.add(String(job.id));
  return `<div class="next-cockpit-reading-job" data-next-analyzing="${esc(job.id)}">` +
    '<div class="next-cockpit-reading-job-head"><span class="next-cockpit-reading-job-title" ' +
    `tabindex="-1" data-next-focus="reading:${esc(key)}">${esc(NEXT_READING_JOB_TITLE)}</span>` +
    '<button type="button" class="next-action" data-next-cockpit-action="reading-cancel" ' +
    `data-next-focus="reading-cancel:${esc(key)}" data-next-focus-fallback="reading:${esc(key)}"` +
    `${finishing ? ' aria-disabled="true"' : ""}>Cancel</button></div>` +
    `<ol class="next-cockpit-reading-steps">${items}</ol>` +
    `<p class="next-cockpit-reading-job-note">${esc(NEXT_READING_JOB_NOTE)}</p>` +
    (mine && mine.failed && !finishing
      ? `<p class="next-cockpit-reading-why">${esc(NEXT_READING_CANCEL_FAILED)}</p>` : "") +
    "</div>";
}

function nextReadingJobShown(session, job){
  if(!nextData || !job || typeof job !== "object") return;
  nextData.reading_jobs = {...(nextData.reading_jobs || {}), [sessKey(session)]: job};
}

/* How an analysis ended, said once (DRC-4726). A withheld, cancelled or
   interrupted end is the server's own `reading_withheld` sentence; a stored
   reading is this one (owner, 2026-09-28). */
const NEXT_READING_FINISHED = "The analysis finished. Its reading is in the Reading section.";
/* The job ids drawn by the render in progress, cleared before each one. */
const nextCockpitReadingJobsDrawn = new Set();
/* Per session, the running job this tab has seen, whether the last render
   drew its box, and the outcome fields as they stood when it was first seen,
   so an end can tell a new reading from the one already stored. Held for the
   life of the tab and dropped when the job ends; docs/design-reader-state.md
   holds the row. */
const nextCockpitReadingJobsSeen = new Map();
let nextCockpitReadingJobsPrimed = false;

function nextCockpitReadingJobOutcome(key, seen){
  const row = (nextData && Array.isArray(nextData.sessions) ? nextData.sessions : [])
    .find(session => sessKey(session) === key);
  const annotation = row ? nextCockpitAnnotation(row) : null;
  const withheld = String(annotation && annotation.reading_withheld || "");
  if(withheld) return withheld;
  const reading = JSON.stringify(annotation && annotation.assessment || null);
  return reading !== "null" && reading !== seen.reading ? NEXT_READING_FINISHED : "";
}

/* Run after every render, once the regions are ensured, and never from the
   render itself: a region and its first message must not arrive in the same
   mutation. "Analyzing drift" is said when a job this tab had not seen is
   first drawn, and the outcome when a job whose box the last render drew
   leaves `reading_jobs`, so a redraw, a phase revision or a reload says
   nothing again. The first pass only records what is already running: a
   reload pressed nothing. */
/* A region already holding the sentence is emptied first, as
   `nextCockpitKeepUnsay` does for Keep: setting the same text again is not
   read (verifier V5). */
function nextCockpitReadingJobSay(key, sentence){
  const region = nextCockpitCueStatus(document.getElementById("app"));
  if(region && region.textContent === sentence) region.textContent = "";
  nextCockpitAnnounceCue(key, sentence, false);
}

function nextCockpitReadingJobCues(){
  if(!nextData) return;
  const jobs = nextData.reading_jobs && typeof nextData.reading_jobs === "object"
    ? nextData.reading_jobs : {};
  const primed = nextCockpitReadingJobsPrimed;
  nextCockpitReadingJobsPrimed = true;
  for(const [key, seen] of [...nextCockpitReadingJobsSeen]){
    const job = jobs[key];
    if(job && typeof job === "object" && String(job.id) === seen.id) continue;
    nextCockpitReadingJobsSeen.delete(key);
    const outcome = seen.drawn ? nextCockpitReadingJobOutcome(key, seen) : "";
    if(outcome){
      nextCockpitReadingJobSay(`job:${seen.id}`, outcome);
    }else{
      /* Ended unannounced: a virtual cursor must not still find "Analyzing
         drift" in the region, and the next start must not set that same
         text again, which is not read (a11y review F1). */
      nextCockpitAnnouncedCues.delete(`job:${seen.id}`);
      const region = nextCockpitCueStatus(document.getElementById("app"));
      if(region && region.textContent === NEXT_READING_JOB_TITLE) region.textContent = "";
    }
  }
  for(const [key, job] of Object.entries(jobs)){
    if(!job || typeof job !== "object" || typeof job.id !== "string") continue;
    const drawn = nextCockpitReadingJobsDrawn.has(job.id);
    const seen = nextCockpitReadingJobsSeen.get(key);
    if(seen){
      seen.drawn = drawn;
      continue;
    }
    const row = (Array.isArray(nextData.sessions) ? nextData.sessions : [])
      .find(session => sessKey(session) === key);
    const annotation = row ? nextCockpitAnnotation(row) : null;
    nextCockpitReadingJobsSeen.set(key, {id: job.id, drawn,
      reading: JSON.stringify(annotation && annotation.assessment || null)});
    if(primed && drawn) nextCockpitReadingJobSay(`job:${job.id}`, NEXT_READING_JOB_TITLE);
  }
}

/* Steer back (DRC-4681): the server's correction, composed from the reader's
   words, each line's state and the cited entries' times (`correction.py`),
   shown for the reader to edit and copy. Item 7 of
   [DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy):
   Copy only, and nothing goes to the session. Per session, in memory only:
   whether the box is open, the server's parts, the reader's text once edited
   or copied, the refusal and the Copy cue. docs/design-reader-state.md holds
   the rows. */
const nextCockpitCorrections = new Map();
const NEXT_COCKPIT_CORRECTION_CAP = 2000;
const NEXT_COCKPIT_STEER_HARNESSES = ["claude"];
const NEXT_COCKPIT_CORRECTION_HINT =
  "Cargento never sends this. Copy it and paste it into the session.";
const NEXT_COCKPIT_CORRECTION_NOTHING =
  "Nothing recorded now gives a correction to steer back from.";
const NEXT_COCKPIT_CORRECTION_FAILED =
  "Could not compose a correction. Press Steer back again to retry.";
const NEXT_COCKPIT_CORRECTION_OLDER =
  "This was composed from an older record. Recompose replaces your edit with a correction from " +
  "the record as it stands.";
const NEXT_COCKPIT_CORRECTION_EDIT_REFUSED =
  "This edit is unavailable here. Your text is kept.";
const NEXT_COCKPIT_CORRECTION_COMPOSITION_REFUSED =
  "This composition would exceed 2,000 characters and was not kept.";
const NEXT_COCKPIT_CORRECTION_UNDO_UNAVAILABLE =
  "The previous text was restored. Undo is unavailable for this refused edit.";
const NEXT_COCKPIT_CORRECTION_PAINT_PAUSED =
  "Updates are paused while you edit this correction. Leave the box to show new work.";

/* The failed checks after the words, by the server's rule (`_failed_checks`):
   the correction's "A check failed at" names the latest of them. */
function nextCockpitFailedChecks(session, entries){
  const opened = nextNumber(session && session.annotation_window_start) || 0;
  return entries.filter(entry => entry.type === "tool_report" && entry.subject === "check" &&
    entry.result === "failed" && nextNumber(entry.at) > 0 &&
    (nextReadingEvidenceAt(entry) || 0) > 0 && nextReadingEvidenceAt(entry) >= opened);
}

/* Whether there is anything to steer from, by the server's own rule
   (`correction.compose`) over what this page holds, or null: saved words, and
   a departure that survives in a reading of those words, a failed check after
   them, or a later direction. `departed` places the control. Claude Code only,
   as the copy route is, so a paste of it can be recognised coming back. */
function nextCockpitSteerOffer(session, annotation, source, shape){
  if(!NEXT_COCKPIT_STEER_HARNESSES.includes(String(session && session.harness || ""))) return null;
  if(!(nextData && nextData.annotate === true) || nextIntentDrafted(session, annotation)) return null;
  if(!String(annotation && annotation.goal || "").trim() &&
      !nextAnnotationLines(annotation).length) return null;
  if(!source || (source.state !== "read" && source.state !== "empty")) return null;
  const entries = source.all || source.entries || [];
  const current = Boolean(shape && !shape.malformed && shape.revisionRead != null &&
    shape.revisionRead === nextNumber(annotation && annotation.revision));
  const departed = current && shape.departures.length > 0;
  const failed = nextCockpitFailedChecks(session, entries).length > 0;
  const later = nextCockpitLaterDirections(annotation, entries, session).length > 0;
  return departed || failed || later ? {departed} : null;
}

/* The direction Update intent instead offers (owner, 2026-09-28): the later
   direction a surviving departure cites, else the latest, else none. One
   already saved as a line is never offered again: adding it twice wrote a
   typed line away for a copy of one kept (page F1). */
function nextCockpitOfferedDirection(annotation, entries, session, shape){
  const saved = new Set(nextAnnotationLines(annotation).map(line => line.sourceId).filter(Boolean));
  const later = nextCockpitLaterDirections(annotation, entries, session)
    .filter(entry => !saved.has(String(entry.id || "")));
  const ids = new Set(later.map(entry => String(entry.id || "")));
  const cited = shape ? shape.departures.flatMap(row => row.citedIds || [])
    .find(id => ids.has(String(id))) : null;
  if(cited) return String(cited);
  return later.length ? String(later[later.length - 1].id || "") : "";
}

/* The parts with "#n" filled from the list's own numbers: the first number
   drawn reads "(#n in Cargento)", the rest "(#n)", and an entry the list does
   not number keeps only its time, which the server already wrote (owner,
   2026-09-28). The server counts every placeholder at its widest, so the text
   stays within the cap. */
function nextCockpitCorrectionText(parts, numbers){
  let first = true;
  return (parts || []).map(part => {
    if(typeof part === "string") return part;
    const n = numbers.get(String(part && part.entry || ""));
    if(n == null) return "";
    const said = first ? ` (#${n} in Cargento)` : ` (#${n})`;
    first = false;
    return said;
  }).join("");
}

function nextCockpitCorrectionDraft(session, held, source){
  if(typeof held.text === "string") return held.text;
  if(held.recomposing && typeof held.recomposeText === "string") return held.recomposeText;
  const read = source && (source.state === "read" || source.state === "empty");
  return nextCockpitCorrectionText(held.parts, read ? nextCockpitEntryNumbers(session, source)
    : new Map());
}

/* Characters as the server counts them (`correction._width`, the copy route's
   cap): code points, never UTF-16 units, so a correction of astral characters
   is neither refused nor cut on one side only (injection F2). */
function nextCockpitCorrectionLength(text){
  return [...String(text || "")].length;
}

/* What composition read, as this page holds it at the press: the saved words'
   revision, how far a Keep settled, and when the stored reading was read. The
   entries the parts cite are added when the parts arrive (`cited`). A change in
   any of them means the text may claim what the panel no longer does (injection
   F1, page F3). */
function nextCockpitCorrectionStamp(annotation){
  const assessment = annotation && annotation.assessment;
  return JSON.stringify([
    nextNumber(annotation && annotation.revision),
    nextNumber(annotation && annotation.settled_through),
    assessment && typeof assessment === "object" ? nextNumber(assessment.read_at) : null,
  ]);
}

function nextCockpitCorrectionIds(source){
  const read = source && (source.state === "read" || source.state === "empty");
  return read ? new Set((source.all || source.entries || []).map(entry => String(entry.id || "")))
    : null;
}

function nextCockpitCorrectionFailedIds(session, source){
  const read = source && (source.state === "read" || source.state === "empty");
  return read ? nextCockpitFailedChecks(session, source.all || source.entries || [])
    .map(entry => String(entry.id || "")) : null;
}

/* Whether the held correction was composed from a record that no longer holds:
   a stamp that moved, a cited entry gone, or a failed check it did not see,
   which would leave "A check failed at" naming an older one (V3). An unread
   record says nothing either way, so it never marks one stale. */
function nextCockpitCorrectionStale(held, annotation, source, session){
  if(!held || !Array.isArray(held.parts)) return false;
  if(held.stale) return true;
  if(held.stamp != null && held.stamp !== nextCockpitCorrectionStamp(annotation)) return true;
  const ids = nextCockpitCorrectionIds(source);
  if(ids && Array.isArray(held.cited) && held.cited.some(id => !ids.has(id))) return true;
  const failed = session ? nextCockpitCorrectionFailedIds(session, source) : null;
  return Boolean(failed && Array.isArray(held.failed) && failed.some(id => !held.failed.includes(id)));
}

/* On every render of the slot. Unedited, a correction from a record that no
   longer holds is dropped: recomposed from the server where there is still
   something to steer from, closed where there is not. Edited, it is the
   reader's and is kept, marked as composed from an older record, with
   Recompose beside it. */
function nextCockpitCorrectionFollow(session, annotation, source, offer){
  const key = sessKey(session);
  const held = nextCockpitCorrections.get(key);
  /* Only against a record read: while it is being fetched again, whether
     there is anything to steer from is not known, and a box closed then would
     close on a gap in the page rather than a change in the record. */
  const ids = nextCockpitCorrectionIds(source);
  if(!held || held.pending || held.recomposing || !Array.isArray(held.parts) || !ids) return;
  if(!Array.isArray(held.cited)){
    held.cited = held.parts.filter(part => typeof part !== "string")
      .map(part => String(part.entry || "")).filter(id => ids.has(id));
  }
  if(!Array.isArray(held.failed)) held.failed = nextCockpitCorrectionFailedIds(session, source);
  if(!nextCockpitCorrectionStale(held, annotation, source, session)) return;
  if(held.edited){
    held.stale = true;
    return;
  }
  if(!offer || !held.open){
    nextCockpitCorrections.delete(key);
    return;
  }
  /* The old box stays drawn while the request is out, so a key typed into it
     lands in it rather than nowhere (V5). Freeze its last rendering before
     this record can renumber the old server parts (DRC-4739). */
  held.recomposeText = typeof held.shownText === "string" ? held.shownText
    : nextCockpitCorrectionDraft(session, held, source);
  held.recomposing = true;
  const stamp = nextCockpitCorrectionStamp(annotation);
  /* After this render: a render never starts a request inside itself. */
  Promise.resolve().then(() => nextCockpitComposeCorrection(session, stamp, {quiet: held}));
}

function nextCockpitSteerButton(session, primary){
  const key = sessKey(session);
  const held = nextCockpitCorrections.get(key);
  return `<button type="button" class="next-action${primary ? " next-action--primary" : ""}" ` +
    `data-next-cockpit-action="steer-back" aria-expanded="${held && held.open ? "true" : "false"}" ` +
    `data-next-focus="steer-back:${esc(key)}">Steer back</button>`;
}

/* The design's steer box with Copy-only wording: "Correction to copy" and the
   hint the issue gives in place of the Send hint. Copy's label is its cue, the
   More menu's "Copied" and "Copy unavailable" (owner, 2026-09-28). */
function nextCockpitSteerBox(session, source){
  const key = sessKey(session);
  const held = nextCockpitCorrections.get(key);
  if(!held || !held.open || held.pending) return "";
  if(held.why){
    return `<p class="next-cockpit-reading-why" role="status" data-next-steer-refused>` +
      `${esc(held.why)}</p>`;
  }
  if(!Array.isArray(held.parts)) return "";
  const label = held.cue === "copied" ? "Copied" : held.cue === "failed" ? "Copy unavailable" : "Copy";
  const draft = nextCockpitCorrectionDraft(session, held, source);
  held.shownText = draft;
  /* No `maxlength`: it counts UTF-16 units, and the cap is in characters. The
     input handler holds the cap, and the count says where it stands. */
  const older = held.stale
    ? `<p class="next-cockpit-reading-why" data-next-correction-older>${NEXT_COCKPIT_CORRECTION_OLDER}</p>` +
      '<button type="button" class="next-action" data-next-cockpit-action="correction-recompose" ' +
      `data-next-focus="correction-recompose:${esc(key)}">Recompose</button>`
    : "";
  return '<div class="next-cockpit-steer-box" data-next-steer-box>' +
    '<label class="next-cockpit-held-label" for="next-cockpit-correction">Correction to copy</label>' +
    '<textarea id="next-cockpit-correction" rows="6" ' +
    `data-next-cockpit-correction-key="${esc(key)}" data-next-focus="correction:${esc(key)}" ` +
    'aria-describedby="next-cockpit-correction-hint">' +
    `${esc(draft)}</textarea>` +
    '<div class="next-cockpit-steer-tools">' +
    '<button type="button" class="next-action" data-next-cockpit-action="correction-copy" ' +
    `data-next-copy-correction="${esc(key)}" data-next-focus="correction-copy:${esc(key)}" ` +
    `data-next-correction-cue>${label}</button>` +
    `<span class="next-cockpit-held-count" data-next-correction-count>` +
    `${nextCockpitCorrectionLength(draft)}/${NEXT_COCKPIT_CORRECTION_CAP}</span>` + older +
    `<p class="next-cockpit-reading-why" data-next-correction-edit-why${held.editWhy ? "" : " hidden"}>` +
    `${esc(held.editWhy || "")}</p>` +
    `<p class="next-cockpit-reading-why" data-next-correction-paint-why${held.paintWhy ? "" : " hidden"}>` +
    `${esc(held.paintWhy || "")}</p>` +
    `<p class="next-cockpit-reading-why" id="next-cockpit-correction-hint">` +
    `${NEXT_COCKPIT_CORRECTION_HINT}</p></div></div>`;
}

function nextCockpitCorrectionParts(parts){
  return Array.isArray(parts) && parts.every(part => typeof part === "string" ||
    (part && typeof part === "object" && typeof part.entry === "string")) ? parts : null;
}

/* The press opens the box and asks the server, naming the session and nothing
   else, so no text the page holds can reach the composition. A second press
   closes an open box; over a refusal it asks again, as the refusal says (page
   F4). A text the reader edited or copied is kept across a close. `stamp` is
   what the page held at the press (`nextCockpitCorrectionStamp`). */
function nextCockpitSteerBack(session, stamp){
  const key = sessKey(session);
  const held = nextCockpitCorrections.get(key);
  if(held && held.pending) return undefined;
  if(held && held.open && !held.why){
    held.open = false;
    renderNext({named: `steer-back:${key}`});
    return undefined;
  }
  if(held && !held.why && typeof held.text === "string" && Array.isArray(held.parts)){
    held.open = true;
    renderNext({named: `correction:${key}`});
    return undefined;
  }
  return nextCockpitComposeCorrection(session, stamp);
}

/* One request for the session's correction. `quiet` is the held entry of a
   recomposition the reader did not press for (`nextCockpitCorrectionFollow`):
   that box stays drawn until the answer, an edit made to it meanwhile keeps
   it as the reader's, the answer is drawn with the ordinary focus capture so
   a reader typing elsewhere stays there (V1), and with nothing left to steer
   from it closes rather than refusing a press nobody made. */
async function nextCockpitComposeCorrection(session, stamp, {quiet = null} = {}){
  const key = sessKey(session);
  const next = {open: true, pending: true, parts: null, text: null, edited: false, why: "",
    cue: "", stamp, cited: null, failed: null};
  if(!quiet){
    nextCockpitCorrections.set(key, next);
    renderNext();
  }
  try{
    const response = await fetch("/api/correction", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({harness: session.harness, sid: session.sid})});
    const answer = response && typeof response.json === "function"
      ? await response.json().catch(() => null) : null;
    const parts = answer && answer.ok === true ? nextCockpitCorrectionParts(answer.parts) : null;
    if(response && response.ok && parts){
      next.parts = parts;
    }else if(response && response.ok && answer && answer.ok === false){
      next.why = answer.reason === "too-long" && typeof answer.why === "string" ? answer.why
        : answer.reason === "nothing" ? NEXT_COCKPIT_CORRECTION_NOTHING : NEXT_COCKPIT_CORRECTION_FAILED;
    }else{
      throw new Error("correction not composed");
    }
  }catch(_error){
    next.why = NEXT_COCKPIT_CORRECTION_FAILED;
  }
  next.pending = false;
  if(quiet){
    /* Replaced, closed or edited while the request was out: that answer is not
       this box's, and an edit keeps the reader's text with Recompose beside it. */
    if(nextCockpitCorrections.get(key) !== quiet) return;
    quiet.recomposing = false;
    if(quiet.edited || nextCockpitCorrectionComposition &&
        nextCockpitCorrectionComposition.held === quiet) quiet.stale = true;
    else if(!quiet.open || next.why === NEXT_COCKPIT_CORRECTION_NOTHING) nextCockpitCorrections.delete(key);
    else nextCockpitCorrections.set(key, next);
    renderNext();
    return;
  }
  /* Replaced or closed while the request was out: that answer is not this box's. */
  if(nextCockpitCorrections.get(key) !== next) return;
  renderNext({named: next.why ? `steer-back:${key}` : `correction:${key}`});
}

/* Copy writes the box's exact text and only then records it, through
   DRC-4678's route, so a paste of it coming back reads as Cargento's words.
   The text is frozen at the press, so what is recorded is what was shown. */
async function nextCockpitCopyCorrection(session, target, source){
  const key = sessKey(session);
  const held = nextCockpitCorrections.get(key);
  if(!held || !Array.isArray(held.parts) || held.copying || held.pending) return;
  if(nextCockpitCorrectionComposition && nextCockpitCorrectionComposition.held === held){
    held.cue = "failed";
    nextCockpitCorrectionUpdateTools(nextCockpitCorrectionComposition.input, held);
    return;
  }
  /* Never a text composed from a record that no longer holds, unless the
     reader made it theirs: the redraw recomposes it instead. */
  if(!held.edited && nextCockpitCorrectionStale(held, nextCockpitAnnotation(session), source, session)){
    held.cue = "failed";
    renderNext({named: `correction-copy:${key}`});
    return;
  }
  const text = nextCockpitCorrectionDraft(session, held, source);
  held.text = text;
  held.copying = true;
  const copied = await nextCopyToClipboard(target, text);
  held.copying = false;
  held.cue = copied ? "copied" : "failed";
  renderNext({named: `correction-copy:${key}`});
  if(!copied) return;
  try{
    await fetch("/api/correction/copied", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({harness: session.harness, sid: session.sid, text})});
  }catch(_error){
    /* Unrecorded, a paste reads as the reader's own words: the safe side. */
  }
}

/* `steer` is Steer back's controls and box in this slot
   (`nextCockpitReadingParts` decides): under a departure, the primary with
   Update intent instead beside it, ahead of Analyze drift (`lead`); with no
   reader, the primary beside the route's reason; with a reader and no
   departure, a secondary after Analyze drift. */
function nextCockpitReadingControl(session, annotation, model, primary = true, steer = null){
  const steerButton = steer ? steer.button : "";
  const lead = Boolean(steer && steer.lead);
  const steerBox = steer ? steer.box : "";
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
  /* A press the board says cannot read is inert and not the stage's primary,
     and no Allow step is offered for it: the handler refuses on this same
     reason before it would ask (DRC-4758 slice B). */
  const pressed = nextReadingEligibility(session);
  const inert = Boolean(pressed) && reason === nextReadingPressLine(session, pressed);
  const confirming = Boolean(provider && !inert && request && request.consent &&
    nextReadingNeedsAllow(route));
  /* `authorized` is no longer a second term here: an unauthorized check is
     one of the sentences `nextCockpitReadingRefusal` returns, so `!reason`
     already carries it. */
  const enabled = !reason && !pending;
  const count = nextNumber(annotation && annotation.reading_count) || 0;
  const spent = `${count} model request${count === 1 ? "" : "s"} recorded for this session.`;
  /* The route's disclosure, naming this session's own receiver, whose
     capacity is spent and where the words go. The offer paragraph in the
     reading scopes WHAT is sent and says nothing about where it goes or who
     pays. Where it sits is the owner's ruling (DRC-4680): idle, under the
     button with the hint, as item 5 of
     [DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy)
     draws it: that press either opens the confirming step or runs under an
     Allow already given after this same disclosure; confirming, before
     "Allow and analyze", because that press is the consent. Either way the
     button is described by it, unless a refusal is what describes it. */
  const disclosure = provider && route.disclosure
    ? `<p class="next-cockpit-reading-why" id="${NEXT_READING_DISCLOSURE_ID}">` +
      `${esc(route.disclosure)}</p>` : "";
  /* Confirming, the same disclosure as the server's own parts, a short list
     in its order and unreworded, so "Allow and analyze" no longer drops below
     one long block (owner Q1, 2026-10-01). A route from before the parts
     were published shows its whole disclosure as one item. */
  const parts = provider && Array.isArray(route.disclosure_parts) && route.disclosure_parts.length
    ? route.disclosure_parts : provider && route.disclosure ? [route.disclosure] : [];
  const disclosureParts = parts.length
    ? `<ul class="next-cockpit-reading-parts" id="${NEXT_READING_DISCLOSURE_ID}">` +
      parts.map(part => `<li>${esc(String(part))}</li>`).join("") + "</ul>" : "";
  /* What an analysis will read, under the control, and only where a press
     could read it: a provider, no refusal beside it, saved words, and words
     given before any observed end, which the server withholds by the same
     time `nextCockpitConflictCandidates` floors on. */
  const given = nextNumber(annotation &&
    (["latest-prompt", "first-prompt"].includes(annotation.goal_source)
      ? annotation.goal_source_at : annotation.at));
  const endedAt = nextSessionEndedAt(session);
  const hint = provider && !reason && String(annotation && annotation.goal || "").trim() &&
    !(endedAt != null && given != null && given > endedAt) ? nextObservedReadHint(session) : "";
  const readHint = hint ? `${hint} ${NEXT_READING_BACKGROUND}` : "";
  const job = nextReadingJob(session);
  const off = nextReadingAnyConsent()
    ? '<button type="button" class="next-action" data-next-cockpit-action="reading-off" ' +
      `data-next-focus="reading-off:${esc(key)}">Turn off readings</button>` : "";
  /* Only from a published annotation: with the store off there is no count
     to read, and "0 requests" would be a default standing in for one. */
  const counted = annotation ? `<span class="next-cockpit-reading-count">${esc(spent)}</span>` : "";
  /* What the last press or withdrawal came to, announced. Every arm prints
     it: a failed "Turn off readings" that says nothing leaves the reader
     believing a permission is gone that is still on record (review C-1). */
  const answered = request && request.message && !request.refusal ? String(request.message) : "";
  const said = text => text
    ? `<p class="next-cockpit-reading-why"${request && request.announced ? "" : ' role="status"'}` +
      `${nextAbsenceAttr(NEXT_READING_REFUSAL_ABSENCE.get(text))}>${esc(text)}</p>` : "";
  /* While a job runs, the box stands where the button was, as the design
     draws it, with the disclosure and the count after it in the idle order.
     A refusal is about a new press, which is not offered, so it waits. */
  if(job){
    return nextReadingJobBox(job, key) +
      (off ? `<div class="next-cockpit-reading-ask">${off}</div>` : "") +
      disclosure + said(answered) + counted;
  }
  /* No reader on this machine: the route's reason stands where the button
     would be, and no inert button is drawn, because there is no press to
     refuse. A narrowing of
     [NUI-18](docs/design-next-ui.md#nui-18-one-control-primitive-and-an-inert-control-stays-on-the-page)
     for this one case (owner, DRC-4680); every other refusal keeps the inert
     control and its sentence. `--no-annotations` is one of those, so the
     store's state is checked first. */
  const noReader = nextData && nextData.annotate === true ? nextReadingRouteRefusal(session) : "";
  /* The reason takes the button's focus key, so a reader whose focus was on
     Analyze drift when the reader went away lands on why, not on the page. */
  if(noReader){
    return '<div class="next-cockpit-reading-ask next-cockpit-reading-ask--none">' +
      `<p class="next-cockpit-reading-why" tabindex="-1" data-next-focus="reading:${esc(key)}" ` +
      `data-next-reading-no-reader${nextAbsenceAttr(NEXT_READING_REFUSAL_ABSENCE.get(noReader))}>` +
      `${esc(noReader)}</p>` + steerButton + off + '</div>' + steerBox +
      said(answered === noReader ? "" : answered) + counted;
  }
  /* `aria-disabled` rather than `disabled`, so the control keeps its place in
     the tab order and its reason is announced. The press this lets back in is
     refused by `nextCockpitAskForReading`, on the reason computed above. */
  /* The page's one primary, unless the session is blocked on the reader: then
     the raise holds it when offered, nothing does otherwise, and this sits
     below as an ordinary control
     ([DEC-20](docs/design-reading-a-session.md#dec-20-the-first-screen-shows-goal-beside-direction-and-drift-has-one-home)).
     The four cockpit tabs have no action to mark at all (DRC-4590, DRC-4603). */
  const described = reason ? NEXT_READING_REFUSED_ID : disclosure ? NEXT_READING_DISCLOSURE_ID : "";
  const button =
    `<button type="button" class="next-action${primary && provider && !inert ? " next-action--primary" : ""}" ` +
    `data-next-cockpit-action="${confirming ? 'reading-allow' : 'reading-ask'}" ` +
    `data-next-focus="reading:${esc(sessKey(session))}"` +
    `${enabled ? "" : ' aria-disabled="true"'}` +
    `${described ? ` aria-describedby="${described}"` : ""}>` +
    `${confirming ? "Allow and analyze" : "Analyze drift"}</button>`;
  /* The announcement and the description are one node while a refusal
     stands. Printing the stored message and the reason separately rendered
     the same sentence twice, adjacent and identical, where the contract is
     that it renders exactly once. The press is still announced, because this
     node carries `role="status"` when it is the refusal. */
  const refused = reason
    ? `<p class="next-cockpit-reading-why"${request && request.refusal && !request.announced
      ? ' role="status"' : ""}` +
      ` id="${NEXT_READING_REFUSED_ID}"` +
      `${nextAbsenceAttr(NEXT_READING_REFUSAL_ABSENCE.get(reason))}>${esc(reason)}</p>` +
      (inert ? nextCockpitWhy(`reading-why:${key}`, "Why it can't read", pressed.sentence) : "")
    : "";
  /* What the last press came to when it was withheld, from the store, so a
     reload and another tab say the same. It was the READING section's, far
     below the button the reader pressed, which is where the owner's walk lost
     it. Not announced here: the job's end already said it once through the
     persistent region (`nextCockpitReadingJobCues`). Left out when the inert
     line above already carries the same sentence. */
  const stored = String(annotation && annotation.reading_withheld || "");
  const age = nextReadingWithheldAge(annotation);
  const outcome = stored && !(inert && String(pressed.sentence || "") === stored)
    ? `<p class="next-cockpit-reading-why next-cockpit-reading-outcome">` +
      `${esc(age ? `Last analysis, ${age}: ` : "Last analysis: ")}${esc(stored)}</p>` : "";
  /* Every account of a press -- why it cannot run, what the last one came to,
     what this tab's press was answered with -- sits directly under the
     button's row, before the hint and the disclosure (DRC-4758 slice B). */
  const accounts = refused + said(answered) + outcome + steerBox +
    (readHint ? `<p class="next-cockpit-reading-why">${esc(readHint)}</p>` : "");
  if(confirming){
    /* The consent step stands in the button's slot: a question naming the
       receiver, the disclosure's parts in view, then the press that is the
       consent and the way out. The heading takes the press's focus key, as
       the job box's title does, so focus lands on the question rather than
       on Allow, and a second Enter or the rest of a double-click cannot give
       consent unread. Not now falls back to that key, which Analyze drift
       carries again once the card goes. */
    const label = String(route.label || provider);
    const steers = steerButton ? `<div class="next-cockpit-reading-ask">${steerButton}</div>` : "";
    return (lead ? steers : "") +
      '<div class="next-cockpit-reading-consent" role="group" ' +
      'aria-labelledby="next-cockpit-reading-consent-title">' +
      '<h3 class="next-cockpit-reading-consent-title" id="next-cockpit-reading-consent-title" ' +
      `tabindex="-1" data-next-focus="reading:${esc(key)}">` +
      `${esc(`Send this session to ${label} for analysis?`)}</h3>` + disclosureParts +
      '<div class="next-cockpit-reading-ask">' +
      button.replace(`data-next-focus="reading:${esc(key)}"`, `data-next-focus="reading-allow:${esc(key)}"`) +
      '<button type="button" class="next-action" data-next-cockpit-action="reading-not-now" ' +
      `data-next-focus="reading-not-now:${esc(key)}" data-next-focus-fallback="reading:${esc(key)}">` +
      "Not now</button></div></div>" +
      (lead ? "" : steers) + (off ? `<div class="next-cockpit-reading-ask">${off}</div>` : "") +
      accounts + counted;
  }
  return '<div class="next-cockpit-reading-ask">' +
    (lead ? steerButton + button : button + steerButton) + off + '</div>' +
    accounts + disclosure + counted;
}

/* "Not now" on the consent step: nothing is sent, allowed or recorded, and
   the idle button comes back. The adoption the step held goes with it. */
function nextCockpitReadingNotNow(session){
  const key = sessKey(session);
  const request = nextCockpitReadingRequests.get(key);
  if(request && request.consent && !request.pending) nextCockpitReadingRequests.delete(key);
  renderNext();
}

/* No positional word. The record is in the activity column and this sentence
   in the panel beside it (DRC-4680), so "below" was true of the markup and
   false to the eye at every width wide enough for two columns. It names the
   column instead, and `HeldToPositionalSentencesTest` lost its row with the
   word rather than keeping a row that measures nothing. */
const NEXT_READING_OFFER =
  "A reading is a model\u2019s account of the evidence on this page: the observed record in " +
  "this session\u2019s activity and the goal and output you saved, and nothing else. It does not " +
  "read a diff, a file, a test or a deliverable.";

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
  /* Both times, as item 13 of
     [DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy)
     asks, where they differ: typed words read work from the reader's latest
     message before the save. Adopted words already name their prompt above. */
  const opened = !shape.promptSource && shape.windowStart != null && shape.revisionReadAt != null &&
    shape.windowStart < shape.revisionReadAt
    ? `; reads work from your message ${esc(fmtDur(Math.max(0, (nextData && nextData.generated || 0) - shape.windowStart)))} ago`
    : "";
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
    `<summary>What it read: revision ${shape.revisionRead}, ${typed}${opened}</summary>` +
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
  /* The question before the press stands in the control's place while a
     later direction is unsettled: Keep is then the stage's one primary. */
  const question = source ? nextCockpitDirectionQuestion(session, annotation, source, model, primary) : "";
  const limit = nextReadingOutputLimit(String(session.harness || ""));
  const raw = annotation && annotation.assessment;
  /* Steer back, drawn only where there is something to steer from, and never
     beside the question, which owns this slot. It takes the control's slot on
     the first screen rather than the result's rows, which run past the fold
     at six lines (measured: 2,567px at 1440x900): under a departure it is the
     one primary with Update intent instead beside it (C4), and Analyze drift
     follows as the design's "Analyze again"; with no reader it is the primary
     beside the route's reason; otherwise a secondary after Analyze drift
     (DRC-4681). Nothing is added to the result stage, which DRC-4695 fills. */
  const early = raw ? nextCockpitReadingShape(raw, annotation, entries, limit, unsettled,
    line => nextCockpitLineSource(line, session, source)) : null;
  const steerable = nextCockpitSteerOffer(session, annotation, source, early);
  nextCockpitCorrectionFollow(session, annotation, source, steerable);
  const offer = question ? null : steerable;
  const departed = Boolean(offer && offer.departed);
  const noReader = nextData && nextData.annotate === true ? nextReadingRouteRefusal(session) : "";
  const update = departed
    ? '<button type="button" class="next-action" data-next-cockpit-action="update-intent" ' +
      `data-arg="${esc(nextCockpitOfferedDirection(annotation, entries, session, early))}" ` +
      `data-next-focus="update-intent:${esc(sessKey(session))}">Update intent instead</button>`
    : "";
  const slotted = offer ? {lead: departed,
    button: nextCockpitSteerButton(session, primary && (departed || Boolean(noReader))) + update,
    box: nextCockpitSteerBox(session, source)} : null;
  const control = '<div class="next-session-drift-check">' +
    (question || nextCockpitReadingControl(session, annotation, model, primary && !departed, slotted)) +
    '</div>';
  const header = '<section class="next-cockpit-reading"><header><h2>READING</h2>';
  /* `defined` rather than sniffing the composed body: the no-reading arm
     already renders NEXT_READING_OFFER, which says what a reading is at more
     length, and a second sentence saying the same thing is a regression
     rather than a fix. Every other arm needs the short one. */
  const close = (body, shape, defined) => ({control,
    reading: `${header}</header>` +
      (defined ? "" : `<p class="next-cockpit-define">${NEXT_COCKPIT_READING_DEFINITION}</p>`) +
      `${body}</section>`,
    departures: nextCockpitDepartures(shape, source, session), cited: new Set()});
  /* A press that produced nothing is not the same as no press, and the
     reason it produced nothing is a sentence the producer chose from a
     closed set rather than one this page infers. It is said beside the
     control, as "Last analysis" (`nextCockpitReadingControl`), and this
     section no longer repeats it (DRC-4758 slice B). */
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
    return close(refused + offer, null, true);
  }
  const shape = early;
  if(shape.malformed){
    /* A refusal is a substitution and never an omission: the block still
       renders, names the field it could not read, and draws no verdict of
       any kind. */
    return close(
      `<p class="next-cockpit-reading-why">${esc(NEXT_READING_UNKNOWN_KEY)}</p>` +
      `<p class="next-cockpit-reading-why">Unrecognised: ${esc(shape.malformed)}.</p>`, shape);
  }
  /* The result (DRC-4695): why it is stale, the answer, each line, where
     the work went, and Not accurate. Numbers are the activity list's, from the
     same record the rows cite. The revision sentence is the one warm ink the
     design allows near a reading, and it is not part of one: which revision
     was read is an observation about revisions, worded as the raises below
     word it about themselves. */
  const record = source && (source.all || source.entries) ? source : {all: entries || []};
  const numbers = nextCockpitEntryNumbers(session, record);
  const held = record.all || record.entries || [];
  const byId = new Map(held.map(entry => [String(entry.id || ""), entry]));
  const routed = nextReadingRoute(session);
  /* Where a press would run: a reader, no refusal, no job, and no question
     before the press standing in the control's place, which Keep answers. */
  const again = !question && !noReader && routed && routed.provider && !nextReadingJob(session) &&
    !nextPromptReadingRefusal(session, annotation, model)
    ? '<button type="button" class="next-action" data-next-cockpit-action="reading-ask" ' +
      `data-next-focus="reading-again:${esc(sessKey(session))}">Analyze again</button>` : "";
  const stale = nextCockpitResultStale(shape, raw, annotation, held, again);
  const answer = shape.criteria.length || shape.departures.length
    ? nextCockpitResultAnswer(nextDriftAnswer(shape, held), numbers, byId) : "";
  const work = nextCockpitResultWork(held, numbers, source && source.scan, shape.windowStart);
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
      stale + answer +
      shape.criteria.map(row => nextCockpitReadingCriterionRow(row, numbers, byId)).join("") +
      work +
      (shape.promptSource ? '<p class="next-cockpit-reading-why">Baseline from your prompt.</p>' : "") +
      nextCockpitReadingBaseline(shape) + scope +
      nextCockpitResultFoot(session, annotation, raw) + '</section>',
    departures: nextCockpitDepartures(shape, source, session),
    /* What the activity list flags "Cited": the entries the surviving
       departures rest on, from this one stored reading and nothing earlier
       (item 6 of
       [DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy)).
       A consistent row's entries are listed, never flagged. */
    cited: new Set(shape.departures.flatMap(row => row.citedIds || []).filter(Boolean))};
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
    nextAnnotationLines(annotation).length;
  if(!typed) return "";
  /* The neutral states only: nothing since, a settled baseline and an unread
     record ask the reader to act on nothing
     ([DEC-20](docs/design-reading-a-session.md#dec-20-the-first-screen-shows-goal-beside-direction-and-drift-has-one-home)).
     An unsettled direction is asked about before the press instead. */
  const header = '<section class="next-cockpit-conflict"><header><h2>A LATER DIRECTION</h2></header>';
  const steer = '<p class="next-cockpit-conflict-why">Nothing here decides whether it changes ' +
    'what you are asking for. That is yours, and Cargento does not write into the session ' +
    'either way.</p></section>';
  if(source.state !== "read" && source.state !== "empty"){
    return `${header}<p class="next-cockpit-conflict-why">` +
      `${esc(nextCockpitWorkAbsence(source))} So whether you have given a later direction is ` +
      'unknown, not none.</p>' + steer;
  }
  const pending = nextCockpitConflictCandidates(annotation, source.all || source.entries, session);
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
  /* An unsettled one is asked about before the press, in the control's
     place (`nextCockpitDirectionQuestion`), which replaced this block's
     buttons (owner, DRC-4682). */
  return "";
}

/* The question before the press (item 4 of
   [DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy),
   DRC-4682). It replaces the "Conflict to settle" block (owner, 2026-09-27):
   one home for the answer, asked before a reading is spent rather than after
   one was demoted. It asks and never answers whether the direction conflicts
   ([DEC-16](docs/design-reading-a-session.md#dec-16-cargento-does-not-write-into-a-session)).

   The number comes from `nextCockpitEntryNumbers`, and every unsettled later
   direction is drawn at its own number, so the "#<n>" named is on screen. The
   sentence drops the number rather than naming one the list did not give. */
const NEXT_COCKPIT_KEEP_ANALYZE = "Keep my intent and analyze";
const NEXT_COCKPIT_KEEP = "Keep my intent";
const NEXT_COCKPIT_ADD_DIRECTION = "Add it to my intent";
const NEXT_COCKPIT_KEEP_NO_ANALYSIS =
  "Kept your intent and settled the direction. No analysis was started.";
/* Keep never grants consent (owner, consent F5): where none is given it only
   settles, and the Allow and analyze beside its disclosure does the sending. */
const NEXT_COCKPIT_KEEP_ALLOW =
  "Kept your intent and settled the direction. Press Allow and analyze to send it for a reading.";
const NEXT_COCKPIT_KEEP_REFUSED =
  "Nothing was settled and no analysis was started: your intent changed since this page " +
  "was drawn, or the store refused the mark. Review your intent and press again.";
/* Keep settles every direction it was shown, and the question quotes only the
   earliest one's first sentence. So before it settles, each direction is
   opened whole through `POST /api/direction`; one whose whole text is more
   than its summary is drawn here and the press stops, and one that cannot be
   opened refuses the press (owner, DRC-4732). */
const NEXT_COCKPIT_KEEP_READ_FIRST =
  "Nothing was settled yet. Each direction Keep settles is now shown whole. Read it, then " +
  "press again.";
const NEXT_COCKPIT_KEEP_UNOPENED =
  "Nothing was settled and no analysis was started: Cargento could not open the whole text " +
  "of every direction Keep would settle, so it cannot show you what you would keep. Press " +
  "again to retry.";
/* Per session: each direction's whole text as Keep opened it, by fact id, the
   ids the question drew whole, and the revision the page drew them against.
   For the life of the tab, dropped once no direction is open or a Keep is
   refused; docs/design-reader-state.md holds the row. */
const nextCockpitDirectionWhole = new Map();

function nextCockpitCollapsedText(text){
  return String(text || "").replace(/\s+/g, " ").trim();
}

/* "read" when an earlier press drew every direction Keep would settle, "shown"
   when this press drew them, "refused" when one could not be opened. Only a
   sole direction whose whole text is the summary the question quotes settles
   in one press: of several, the question quotes the earliest alone, so the
   rest were never on screen (wire review F1). A direction opened or arriving
   after the list was drawn is unread, so the next press draws it. */
async function nextCockpitKeepReadWhole(session, pending, revision){
  const key = sessKey(session);
  const held = nextCockpitDirectionWhole.get(key) ||
    {texts: new Map(), drawn: new Set(), revision: null};
  nextCockpitDirectionWhole.set(key, held);
  let refused = false;
  for(const entry of pending){
    const id = String(entry.id || "");
    if(held.texts.has(id)) continue;
    let opened = null;
    try{
      const response = await fetch("/api/direction", {method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({harness: session.harness, sid: session.sid, fact_id: id})});
      const answer = response && typeof response.json === "function"
        ? await response.json().catch(() => null) : null;
      if(response && response.ok && answer && answer.ok === true && typeof answer.text === "string"){
        opened = {text: answer.text, clipped: answer.clipped === true};
      }
    }catch(_error){
      opened = null;
    }
    if(!opened){
      refused = true;
      break;
    }
    held.texts.set(id, opened);
  }
  if(refused) return "refused";
  const ids = pending.map(entry => String(entry.id || ""));
  if(ids.every(id => held.drawn.has(id))) return "read";
  const sole = ids.length === 1 && !held.drawn.size ? held.texts.get(ids[0]) : null;
  if(sole && !sole.clipped &&
     nextCockpitCollapsedText(sole.text) === nextCockpitCollapsedText(pending[0].summary)){
    return "read";
  }
  held.drawn = new Set(ids);
  held.revision = revision;
  return "shown";
}

function nextCockpitDirectionWholeList(key, pending, numbers){
  const held = nextCockpitDirectionWhole.get(key);
  if(!held || !held.drawn.size) return "";
  const items = pending.filter(entry => held.drawn.has(String(entry.id || ""))).map(entry => {
    const id = String(entry.id || "");
    const opened = held.texts.get(id);
    const n = numbers.get(id);
    return '<li class="next-cockpit-direction-whole-item">' +
      (n == null ? "" : `<span class="next-cockpit-source">#${n}</span>`) +
      `<span class="next-cockpit-direction-whole-text">${esc(opened.text)}</span>` +
      (opened.clipped ? `<p class="next-cockpit-held-full">${esc(NEXT_COCKPIT_DIRECTION_CLIPPED)}</p>` : "") +
      "</li>";
  }).join("");
  /* Focusable by script alone, and named for the focus restore, so it keeps
     focus across the redraws while the reader reads (a11y review F3). */
  return items ? '<ol class="next-cockpit-direction-whole" data-next-cockpit-direction-whole ' +
    `tabindex="-1" data-next-focus="direction-whole:${esc(key)}">${items}</ol>` : "";
}

const NEXT_COCKPIT_KEEP_UNCONFIRMED =
  "Could not confirm the press. Refresh to check whether your intent was kept before " +
  "pressing again.";

/* Of several, the sentence quotes the earliest, the one Add opens (owner,
   2026-09-28, verifier V4): quoting the latest named a direction Add could not
   reach until the ones before it were added or kept. */
function nextCockpitDirectionSentence(session, annotation, pending, numbers){
  const earliest = pending[0];
  const n = numbers.get(String(earliest.id || ""));
  const summary = String(earliest.summary || "").trim();
  /* No second mark after a quote that ends in its own (DRC-4736): the
     sentence's full stop is the quote's, including a mark a closing quote or
     bracket follows, as in (see tests.). */
  const said = `"${summary}"${/[.!?\u2026]["'\u201d\u2019)\]]*$/.test(summary) ? "" : "."}`;
  if(pending.length === 1){
    return n == null ? `You gave a later direction: ${said}`
      : `You gave a later direction at #${n}: ${said}`;
  }
  const draft = String(annotation && annotation.goal || "").trim() ? null
    : nextIntentDraft(session, annotation);
  const since = !draft ? "since saving your intent"
    : draft.source === "first-prompt" ? "since your first prompt" : "since your latest prompt";
  return `You gave ${pending.length} later directions ${since}, the earliest` +
    `${n == null ? "" : ` at #${n}`}: ${said}`;
}

/* The later directions the question asks about, or none: only over words or
   a draft, and only from a record that was read. */
function nextCockpitDirectionsOpen(session, annotation, source){
  if(!(nextData && nextData.annotate === true)) return [];
  if(!source || (source.state !== "read" && source.state !== "empty")) return [];
  return nextCockpitConflictCandidates(annotation, source.all || source.entries, session);
}

function nextCockpitDirectionQuestion(session, annotation, source, model, primary){
  const pending = nextCockpitDirectionsOpen(session, annotation, source);
  const key = sessKey(session);
  if(!pending.length){
    nextCockpitDirectionWhole.delete(key);
    return "";
  }
  const numbers = nextCockpitEntryNumbers(session, source);
  /* An unsaved edit outranks every other refusal: Keep would settle over
     words that are not on screen on any route, the no-reader one included. */
  const edited = nextIntentUnsaved(session, annotation);
  const reason = edited ? NEXT_INTENT_EDITED : nextPromptReadingRefusal(session, annotation, model);
  const job = nextReadingJob(session);
  const route = nextReadingRoute(session);
  const provider = route && route.provider ? String(route.provider) : "";
  /* Keep is never the consent, so where an Allow is still owed it promises no
     analysis and the disclosure waits for the Allow it describes. */
  const analyze = !reason && !job && !nextReadingNeedsAllow(route);
  const disclosure = provider && route.disclosure
    ? `<p class="next-cockpit-reading-why" id="${NEXT_READING_DISCLOSURE_ID}">` +
      `${esc(route.disclosure)}</p>` : "";
  const request = nextCockpitReadingRequests.get(key);
  const answered = request && request.message && !request.refusal ? String(request.message) : "";
  /* The earliest: its save settles through that direction only, so the
     question comes back for any later one (consent F3, Codex 5). */
  const earliest = pending[0];
  const described = edited ? NEXT_READING_REFUSED_ID : disclosure && analyze ? NEXT_READING_DISCLOSURE_ID : "";
  /* The fallback hands focus on once the question goes with a settle: to
     Analyze or Allow and analyze, or to a started job's title, which holds
     the same key (consent F7). */
  const keep = `<button type="button" class="next-action${primary ? " next-action--primary" : ""}" ` +
    'data-next-cockpit-action="direction-keep" ' +
    `data-next-focus="direction-keep:${esc(key)}" data-next-focus-fallback="reading:${esc(key)}"` +
    `${edited || (request && request.pending) ? ' aria-disabled="true"' : ""}` +
    `${described ? ` aria-describedby="${described}"` : ""}>` +
    `${analyze ? NEXT_COCKPIT_KEEP_ANALYZE : NEXT_COCKPIT_KEEP}</button>`;
  const add = '<button type="button" class="next-action" data-next-cockpit-action="direction-add" ' +
    `data-arg="${esc(String(earliest.id || ""))}" data-next-focus="direction-add:${esc(key)}">` +
    `${NEXT_COCKPIT_ADD_DIRECTION}</button>`;
  const opened = nextCockpitDirectionLines.get(key);
  const count = nextNumber(annotation && annotation.reading_count) || 0;
  return (job ? nextReadingJobBox(job, key) : "") +
    '<div class="next-cockpit-direction-question" data-next-cockpit-direction-question>' +
    `<p class="next-cockpit-direction-said">${esc(nextCockpitDirectionSentence(
      session, annotation, pending, numbers))}</p>` +
    nextCockpitDirectionWholeList(key, pending, numbers) +
    `<div class="next-cockpit-reading-ask">${keep}${add}${nextReadingAnyConsent()
      ? '<button type="button" class="next-action" data-next-cockpit-action="reading-off" ' +
        `data-next-focus="reading-off:${esc(key)}">Turn off readings</button>` : ""}</div>` +
    (analyze ? disclosure : "") +
    (opened && opened.error
      ? `<p class="next-cockpit-reading-why" role="status">${esc(opened.error)}</p>` : "") +
    (answered ? `<p class="next-cockpit-reading-why"${request && request.announced ? ""
      : ' role="status"'}>${esc(answered)}</p>` : "") +
    (annotation ? `<span class="next-cockpit-reading-count">${esc(
      `${count} model request${count === 1 ? "" : "s"} recorded for this session.`)}</span>` : "") +
    (reason
      ? `<p class="next-cockpit-reading-why"${request && request.refusal && !request.announced
        ? ' role="status"' : ""}` +
        ` id="${NEXT_READING_REFUSED_ID}"` +
        `${nextAbsenceAttr(NEXT_READING_REFUSAL_ABSENCE.get(reason))}>${esc(reason)}</p>` : "") +
    "</div>";
}

/* Each Keep press is a new outcome to announce, even the same sentence
   again: its guard goes, and a region still holding the last Keep sentence is
   emptied now, so the press's write is a change the reader's software reads
   rather than the same text set twice (verifier V5). */
function nextCockpitKeepUnsay(key){
  const said = nextCockpitAnnouncedCues.get(`keep:${key}`);
  nextCockpitAnnouncedCues.delete(`keep:${key}`);
  const region = said ? nextCockpitCueStatus(document.getElementById("app")) : null;
  if(region && region.textContent === said) region.textContent = "";
}

/* Keep my intent: settle every later direction the reader was shown, adopting
   the draft in the same write, and start the analysis where consent is given.
   Every Keep names the revision it was drawn against. Where the page already
   knows no analysis can start, or an Allow is still owed, it goes to
   `/api/annotate`, which settles and reads nothing: Keep never carries Allow
   (owner, consent F5). `/api/reading` refuses three of the other states
   before it would settle (the server build's note). */
async function nextCockpitKeepIntent(session, model){
  const key = sessKey(session);
  if(nextCockpitReadingRequests.get(key)?.pending) return;
  const annotation = nextCockpitAnnotation(session);
  const group = nextCockpitRouteGroup();
  const pending = nextCockpitDirectionsOpen(session, annotation,
    group ? nextCockpitWorkSource(group, session) : null);
  if(!pending.length) return;
  nextCockpitKeepUnsay(key);
  if(nextIntentUnsaved(session, annotation)){
    nextCockpitReadingRequests.set(key,
      {pending: false, message: NEXT_INTENT_EDITED, refusal: true, announced: true});
    nextCockpitAnnounceCue(`keep:${key}`, NEXT_INTENT_EDITED, false);
    renderNext();
    return;
  }
  const draft = nextIntentDraft(session, annotation);
  const reason = nextPromptReadingRefusal(session, annotation, model);
  const route = nextReadingRoute(session);
  const owed = !reason && !nextReadingJob(session) && nextReadingNeedsAllow(route);
  const analyze = !reason && !nextReadingJob(session) && !owed;
  const through = nextNumber(pending[pending.length - 1].at);
  const adoption = nextIntentAdoption(draft);
  const drawnAt = nextNumber(annotation && annotation.revision) || 0;
  const request = {pending: true, message: "", adoption, announced: true};
  nextCockpitReadingRequests.set(key, request);
  renderNext();
  try{
    const read = await nextCockpitKeepReadWhole(session, pending, drawnAt);
    if(read !== "read"){
      request.message = read === "refused" ? NEXT_COCKPIT_KEEP_UNOPENED : NEXT_COCKPIT_KEEP_READ_FIRST;
      return;
    }
    /* A press after the list was drawn names the revision it was drawn
       against, so words saved since then are refused rather than settled
       over. `pending` is every drawn direction here, so `through` is too. */
    const held = nextCockpitDirectionWhole.get(key);
    const expected = held && held.drawn.size && held.revision != null ? held.revision : drawnAt;
    if(!analyze){
      const response = await fetch("/api/annotate", {method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({harness: session.harness, sid: session.sid, ...adoption,
          settle_through: through, expected_revision: expected})});
      const answer = response && typeof response.json === "function"
        ? await response.json().catch(() => null) : null;
      if(!response || !response.ok || !answer || answer.ok !== true) throw new Error("not kept");
      const outcome = String(answer.outcome || "");
      const settled = ["stored", "unchanged"].includes(outcome) && answer.persisted !== false;
      request.message = settled ? (owed ? NEXT_COCKPIT_KEEP_ALLOW : NEXT_COCKPIT_KEEP_NO_ANALYSIS)
        : outcome === "untrusted" ? NEXT_COCKPIT_HELD_CUES["settle-untrusted"]
        : NEXT_COCKPIT_KEEP_REFUSED;
      /* A refused Keep draws its directions again against the revision now
         on screen: the one held was what the store just refused. */
      if(!settled) nextCockpitDirectionWhole.delete(key);
      if(settled){
        nextIntentForgetAdopted(session, draft);
        /* The confirming step the idle control draws: its Allow, beside the
           disclosure naming the receiver, is the press that sends. The draft
           is saved now, so that press adopts nothing. */
        if(owed){ request.consent = true; request.adoption = {}; }
      }
      await refreshNext();
      return;
    }
    const provider = String(route.provider);
    const response = await fetch("/api/reading", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({harness: session.harness, sid: session.sid, provider,
        press: true, observer_model: 1, ...adoption, settle_through: through,
        expected_revision: expected})});
    const answer = response && typeof response.json === "function"
      ? await response.json().catch(() => null) : null;
    if(!answer) throw new Error("not confirmed");
    if(answer.adoption_refused || (response && response.status === 422)){
      request.message = NEXT_COCKPIT_KEEP_REFUSED;
      nextCockpitDirectionWhole.delete(key);
      await refreshNext();
      return;
    }
    const settled = ["stored", "unchanged"].includes(String(answer.settled || ""));
    if(settled) nextIntentForgetAdopted(session, draft);
    if(answer.route && typeof answer.route === "object"){
      nextData.reading_routes = {...(nextData.reading_routes || {}),
        [String(session.harness || "")]: answer.route};
    }
    if(answer.reading) nextData.reading = answer.reading;
    if(response && response.ok && answer.ok === true && answer.job && typeof answer.job === "object"){
      nextReadingJobShown(session, answer.job);
      renderNext();
      await refreshNext();
      return;
    }
    if(response && response.status === 409 && answer.job) nextReadingJobShown(session, answer.job);
    const why = answer.reason === "provider-changed" ? NEXT_READING_PROVIDER_CHANGED
      : answer.reason === "destination-changed" ? NEXT_READING_DESTINATION_CHANGED
      : answer.reading ? nextReadingPolicyReason(answer.reading)
      : answer.route && !answer.route.provider ? nextReadingRouteRefusal(session) : "";
    request.message = settled
      ? [NEXT_COCKPIT_KEEP_NO_ANALYSIS, why].filter(Boolean).join(" ")
      : NEXT_COCKPIT_KEEP_UNCONFIRMED;
    await refreshNext();
  }catch(_error){
    request.message = NEXT_COCKPIT_KEEP_UNCONFIRMED;
  }finally{
    request.pending = false;
    /* The persistent polite region, as every settle outcome was (layout F4),
       and only there: the paragraph beside the control is drawn without a
       role, so the outcome is announced once (verifier V5). */
    if(request.message) nextCockpitAnnounceCue(`keep:${key}`, request.message, false);
    renderNext();
    if(request.message === NEXT_COCKPIT_KEEP_READ_FIRST) nextCockpitShowWhole(key);
  }
}

/* The whole text Keep asks the reader to read, brought to them: focus on the
   list, so a screen reader is where "it" is and the next Tab reaches Keep
   again, and its start scrolled into view, since a long list focused as it
   stands leaves its start above the viewport (a11y review F3, measured 760px
   above at 1440x900). */
function nextCockpitShowWhole(key){
  const app = document.getElementById("app");
  if(!app || typeof app.querySelectorAll !== "function") return;
  const named = `direction-whole:${key}`;
  const list = [...app.querySelectorAll("[data-next-focus]")]
    .find(target => String(target.dataset && target.dataset.nextFocus || "") === named);
  if(!list || typeof list.focus !== "function") return;
  list.focus({preventScroll: true});
  if(typeof list.scrollIntoView === "function") list.scrollIntoView({block: "start"});
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

/* Under the Drift heading, verbatim from the design. It names what the
   section measures and asserts no result. */
const NEXT_DRIFT_SUBTITLE = "How far the session has moved from the goal";
/* Item 14 of
   [DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy),
   as its own sentence. */
const NEXT_DRIFT_HARNESS_LIMIT = "Cargento can't read work from this harness.";

/* The slot the level and meter take once a level is published: the live
   estimate (DRC-4696) now, the analysis level (DRC-4695) later. Elsewhere the
   harness limit stands in it and replaces only the level: Analyze drift stays
   wherever the route names a reader (owner, DRC-4680). Never on Pi, whose work
   results are read, so the sentence would be false there. */

/* The live monitor switch (DRC-4696): off by default, and remembered per
   session in this browser only (item 4 of
   [DEC-26](docs/design-reading-a-session.md#dec-26-four-drift-levels-and-a-live-estimate-after-every-turn)).
   Nothing about it is ever sent: the server publishes the focused session's
   estimate whichever way it is set, and this decides only whether it is drawn.
   The in-memory map answers when storage throws, so the switch still works
   for the tab. */
const NEXT_LIVE_ESTIMATE_KEY = "cargento.next.live-estimate:";
const nextLiveMonitorMemory = new Map();
const NEXT_LIVE_HARNESSES = new Set(["claude"]);

function nextLiveMonitorOn(session){
  const key = NEXT_LIVE_ESTIMATE_KEY + sessKey(session);
  if(nextLiveMonitorMemory.has(key)) return nextLiveMonitorMemory.get(key);
  try{ return localStorage.getItem(key) === "1"; }catch(_error){ return false; }
}

function nextLiveMonitorSet(session, on){
  const key = NEXT_LIVE_ESTIMATE_KEY + sessKey(session);
  nextLiveMonitorMemory.set(key, on);
  try{
    if(on) localStorage.setItem(key, "1");
    else localStorage.removeItem(key);
  }catch(_error){ /* kept for the tab */ }
}

/* The design's copy, as ruled: the level names
   [DEC-26](docs/design-reading-a-session.md#dec-26-four-drift-levels-and-a-live-estimate-after-every-turn)
   fixes, "Not enough recorded yet" in place of a level, and the live
   estimate's own source line (item 1: it reads checks and file paths, not
   what the intent says). */
const NEXT_DRIFT_LEVEL_NAMES = {none_or_low:"None or low", medium:"Medium", high:"High",
  extreme:"Extreme", not_enough:"Not enough recorded yet"};
const NEXT_DRIFT_SCALE = ["none_or_low", "medium", "high", "extreme"];
const NEXT_DRIFT_LIVE_LINE = "Reads checks and file paths, not what your intent says.";
const NEXT_DRIFT_LIVE_HINT = "Turn on for a quick, low-cost drift check after every turn. " +
  "The level shows here and in the header.";
const NEXT_DRIFT_LIVE_SAVE = "Save your intent to see a live estimate.";
const NEXT_DRIFT_NUDGE =
  "This is a quick estimate. Analyze to see what drifted and how to steer back.";

/* The focused context's live row for this session, only while it read the
   words saved now: a level measured against an earlier revision is about
   words the panel no longer shows. */
function nextDriftLiveRow(group, session){
  const entry = group ? nextCockpitContexts.get(nextCockpitContextKey(group, session)) : null;
  const work = entry && entry.data && entry.data.sources && entry.data.sources.work;
  const rows = work && Array.isArray(work.live_levels) ? work.live_levels : [];
  return rows.find(row => row && sessKey(row) === sessKey(session)) || null;
}

/* The level to draw, or null. The seam the draft guard in `nextDriftLevel`
   consults, so a test can prove that guard can fail; the analysis level
   (DRC-4695) joins it. "Rose from <level> at #<n>" is the server's replay with
   the number filled from this page's own list, and withheld where the list
   does not number that entry (item 6: recomputed, never stored). */
function nextDriftEstimate(group, session){
  if(!NEXT_LIVE_HARNESSES.has(String(session && session.harness || "")) ||
      !nextLiveMonitorOn(session)) return null;
  const row = nextDriftLiveRow(group, session);
  if(!row) return null;
  const level = String(row.level || "");
  if(level === "no_live_level") return {save: true};
  const label = NEXT_DRIFT_LEVEL_NAMES[level];
  const annotation = nextCockpitAnnotation(session);
  if(!label || nextNumber(row.revision) !== (nextNumber(annotation && annotation.revision) || 0)){
    return null;
  }
  const at = nextNumber(row.computed_at);
  const numbers = nextCockpitEntryNumbers(session, nextCockpitWorkSource(group, session));
  const n = numbers.get(String(row.rose_at || ""));
  const from = NEXT_DRIFT_LEVEL_NAMES[String(row.rose_from || "")];
  return {level, label, source: at != null ? `Live estimate · ${nextSessionClock(at)}` : "Live estimate",
    rose: from && n != null && row.rose_from !== "not_enough" ? `Rose from ${from} at #${n}.` : ""};
}

/* The analysis-derived level (DRC-4695): the server's `levels.analysis_level`
   over the stored reading and the record as it is now, recomputed on every
   fetch and never stored. Drawn only for the reading the panel shows, only
   while that reading read the saved revision, and with its own source line (items 1, 2 and 6 of
   [DEC-26](docs/design-reading-a-session.md#dec-26-four-drift-levels-and-a-live-estimate-after-every-turn)).
   The page holds "None or low" to its own rows as well: a level of None or
   low beside a line the panel cannot show as consistent would reassure past
   what the rows say, so it reads "Not enough recorded yet" instead. */
function nextDriftAnalysisRow(group, session){
  const entry = group ? nextCockpitContexts.get(nextCockpitContextKey(group, session)) : null;
  const work = entry && entry.data && entry.data.sources && entry.data.sources.work;
  const rows = work && Array.isArray(work.analysis_levels) ? work.analysis_levels : [];
  return rows.find(row => row && sessKey(row) === sessKey(session)) || null;
}

function nextDriftAnalysis(group, session, annotation, shape){
  const raw = annotation && annotation.assessment;
  if(!raw || !shape || shape.malformed) return null;
  const readAt = nextNumber(raw.read_at);
  const row = nextDriftAnalysisRow(group, session);
  if(readAt == null || !row || nextNumber(row.read_at) !== readAt ||
      nextNumber(row.revision_read) !== nextNumber(raw.revision_read)) return null;
  // A level for words the reader has replaced yields to the live estimate, as
  // the live one does for a revision the panel does not show
  // ([What the live estimate build decided](docs/design-reading-a-session.md#what-the-live-estimate-build-decided-2026-09-28)).
  const current = nextNumber(annotation && annotation.revision);
  if(current != null && nextNumber(raw.revision_read) !== current) return null;
  let level = String(row.level || "");
  if(!NEXT_DRIFT_LEVEL_NAMES[level]) return null;
  const shown = shape.criteria.length > 0 && shape.criteria.every(line =>
    line.result === NEXT_READING_CONSISTENT && line.restsOn);
  if(level === "none_or_low" && !shown) level = "not_enough";
  const clock = nextSessionClock(readAt);
  return {level, label: NEXT_DRIFT_LEVEL_NAMES[level], source: `Analysis · ${clock}`,
    line: `From the analysis at ${clock}: each line of your intent against the checks and ` +
      "messages it cited.", analysis: true, rose: ""};
}

/* The switch sits beside the Drift heading, as the design places it. */
function nextDriftMonitorSwitch(session){
  if(!NEXT_LIVE_HARNESSES.has(String(session && session.harness || "")) ||
      !(nextData && nextData.annotate === true)) return "";
  const on = nextLiveMonitorOn(session);
  return '<div class="next-session-drift-monitor">' +
    '<span id="next-session-drift-monitor-label">Live monitor</span>' +
    '<button type="button" class="next-session-drift-switch" role="switch" ' +
    `aria-checked="${on ? "true" : "false"}" aria-labelledby="next-session-drift-monitor-label" ` +
    'data-next-cockpit-action="live-monitor" ' +
    `data-next-focus="live-monitor:${esc(sessKey(session))}">` +
    '<span class="next-session-drift-track" aria-hidden="true"><span></span></span>' +
    '</button></div>';
}

function nextDriftMeter(level){
  const on = NEXT_DRIFT_SCALE.indexOf(level);
  return NEXT_DRIFT_SCALE.map((name, i) =>
    `<span class="next-session-drift-seg" data-level="${esc(level)}"` +
    `${on >= 0 && i <= on ? " data-on" : ""}></span>`).join("");
}

/* The header pill: a level on the scale only, never "Not enough recorded
   yet", and never on a Sessions row (item 3). Not a link: the page routes on
   its fragment, and the Drift section leads the column at narrow widths. */
function nextDriftPill(estimate){
  if(!estimate || !NEXT_DRIFT_SCALE.includes(estimate.level)) return "";
  return '<span class="next-session-drift-pill" data-next-drift-pill>' +
    `<span class="next-session-drift-pill-meter" aria-hidden="true">${nextDriftMeter(estimate.level)}` +
    `</span><span>Drift: <strong>${esc(estimate.label)}</strong></span></span>`;
}

/* The level, its source and time, the meter, the source line and where it
   rose, then the nudge at High. No live region: the nudge is drawn, never
   announced, because the live estimate raises nothing (item 5). */
function nextDriftLevel(session, annotation = null, group = null, estimate = undefined,
    analysis = null){
  const harness = String(session && session.harness || "");
  if(harness === "claude" || harness === "pi"){
    /* No level over an unsaved draft (item 2 of
       [DEC-26](docs/design-reading-a-session.md#dec-26-four-drift-levels-and-a-live-estimate-after-every-turn)):
       an estimate of drift from words the reader has not yet chosen measures
       nothing of theirs. A result's own level is drawn over the live
       estimate, as the design's result stage draws it. */
    const found = analysis || (estimate === undefined ? nextDriftEstimate(group, session) : estimate);
    const drafted = nextIntentDrafted(session, annotation);
    const live = NEXT_LIVE_HARNESSES.has(harness) && nextLiveMonitorOn(session) && !analysis;
    if(live && (drafted || found && found.save)){
      return `<p class="next-session-drift-limit" data-next-drift-save>${esc(NEXT_DRIFT_LIVE_SAVE)}</p>`;
    }
    if(drafted || !found || !found.label){
      return NEXT_LIVE_HARNESSES.has(harness) && nextData && nextData.annotate === true && !live
        ? `<p class="next-session-drift-hint">${esc(NEXT_DRIFT_LIVE_HINT)}</p>` : "";
    }
    const high = found.level === "high" || found.level === "extreme";
    /* While an analysis runs the design keeps the title and dims the meter,
       and drops the detail line. Over an unsaved edit the nudge would point at
       a press the page refuses, so it goes; the level is over the saved words. */
    const running = Boolean(nextReadingJob(session));
    const detail = found.level && !running
      ? [found.analysis ? found.line : NEXT_DRIFT_LIVE_LINE, found.rose].filter(Boolean).join(" ")
      : "";
    return '<div class="next-session-drift-live" data-next-drift-level>' +
      '<p class="next-session-drift-live-head">' +
      `<span class="next-session-drift-level">${esc(String(found.label))}</span>` +
      (found.source ? `<span class="next-session-drift-source">${esc(found.source)}</span>` : "") +
      '</p>' +
      (found.level ? `<p class="next-session-drift-meter" aria-hidden="true"${running ? " data-dim" : ""}>` +
        `${nextDriftMeter(found.level)}</p>` : "") +
      (detail ? `<p class="next-session-drift-detail">${esc(detail)}</p>` : "") +
      '</div>' +
      (high && !found.analysis && !running && !nextIntentUnsaved(session, annotation)
        ? `<p class="next-session-drift-nudge">${esc(NEXT_DRIFT_NUDGE)}</p>` : "");
  }
  return `<p class="next-session-drift-limit" data-next-drift-limit>${esc(NEXT_DRIFT_HARNESS_LIMIT)}</p>`;
}

/* The session page's Intent and drift panel, and the activity column's
   sections that belong to it (DRC-4680). Three returns: `panel` is the aside,
   `record` renders in the activity column after the session's own facts
   ([DEC-20](docs/design-reading-a-session.md#dec-20-the-first-screen-shows-goal-beside-direction-and-drift-has-one-home),
   [DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy)
   item 1).

   The order inside the panel is load bearing: the Intent section, the
   reader's own words; then the Drift section with the one control, so it is
   on the first screen; then the reading, then any later direction of yours
   and the caveats, then every departure on record. Your words come first, so
   nothing above the reading is a model's. CURRENT ACTIVITY is no longer in
   here: it leads the activity column, beside the panel rather than inside it.

   `primary` is false while the session waits on the reader, whose question the
   check never outranks. The word drift names the section and the control and
   nothing else: no sentence here may say a session has none. */
function nextCockpitDriftBlock(group, session, primary){
  const annotated = nextData && nextData.annotate === true ? nextCockpitAnnotation(session) : null;
  const estimate = nextDriftEstimate(group, session);
  let analysis = null;
  if(annotated && annotated.assessment){
    const known = nextCockpitWorkSource(group, session);
    const held = known.all || known.entries;
    analysis = nextDriftAnalysis(group, session, annotated, nextCockpitReadingShape(
      annotated.assessment, annotated, held, nextReadingOutputLimit(String(session.harness || "")),
      Boolean(nextCockpitConflictCandidates(annotated, held, session).length)));
  }
  /* The analysis level is unaffected by the switch (item 4), so its pill
     shows whichever way the switch is set. */
  const shown = analysis || estimate;
  const pill = shown && !nextIntentDrafted(session, annotated) ? nextDriftPill(shown) : "";
  /* `data-next-session-drift` marks the whole panel, which is where the
     drift block's contents now live. */
  const open = '<aside class="next-session-panel" data-next-session-drift aria-label="Intent and drift">';
  const head = '<section class="next-session-drift" id="next-session-drift" ' +
    'aria-labelledby="next-session-drift-heading">' +
    '<header class="next-session-drift-head"><div class="next-session-drift-titles">' +
    '<h2 id="next-session-drift-heading" class="next-session-drift-heading">Drift</h2>' +
    `<p class="next-session-drift-sub">${esc(NEXT_DRIFT_SUBTITLE)}</p></div>` +
    `${nextDriftMonitorSwitch(session)}</header>` +
    nextDriftLevel(session, annotated, group, estimate, analysis);
  /* No field at all when the store is off, which is what `--no-annotations`
     promises. A box whose every save answers 503 is worse than none, and the
     reason is on screen rather than left to the reader. Any standing raise
     still renders: the departure store is read whichever way. */
  if(!(nextData && nextData.annotate === true)){
    /* The check stays, inert, and its refusal is the one place the store's
       state is said: no Intent section above it repeating the sentence. */
    const source = nextCockpitWorkSource(group, session);
    const check = '<div class="next-session-drift-check">' +
      nextCockpitReadingControl(session, null, null, primary) + '</div>';
    return {panel: open + head + check + nextCockpitDepartures(null, source, session) +
      '</section></aside>', list: nextCockpitWorkEvidence(session, source), record: "",
      count: nextCockpitEntryTotal(session, source), pill: ""};
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
    nextCockpitConflictCandidates(annotation, workSource.all || entries, session).length);
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
  const binding = annotation && annotation.binding_why &&
    (annotation.goal || nextAnnotationLines(annotation).length)
    ? `<p class="next-cockpit-held-absent">${esc(annotation.binding_why)}</p>` : "";
  /* An ended session may still be annotated, and the store will keep it. What
     is unsettled is whether anything should then read it, so the line says
     that rather than disabling a control over an open question. A caveat, so
     it renders with the caveats below the reading (DRC-4669): between the
     fields and the control it pushed the control under a 1440x900 fold on
     every ended session. */
  const ended = nextSessionEndedAt(session) != null
    ? '<p class="next-cockpit-held-absent">This session has ended. Anything you save ' +
      'against it is kept, and nothing is promised to read it.</p>' : "";
  /* What typing buys, before anything that qualifies it, worded to the default
     board: the unasked lane is off unless the reader started with
     `--unasked-readings`, so a check happens because the reader pressed. */
  /* Over a draft the design's own line takes the lede's place rather than
     adding a row: the fold had 7px to spare (DRC-4682). */
  const drafted = nextIntentDrafted(session, annotation);
  const lede = drafted
    ? '<p class="next-cockpit-held-lede" data-next-intent-measured>Drift is measured against ' +
      'these. Edit anything that is off.</p>'
    : '<p class="next-cockpit-held-lede">Choose a goal or use your prompt, then analyze ' +
      'drift: Cargento lists where this session departed from it. It never writes into the ' +
      'session, so steering stays yours.</p>';
  /* In the lede's slot, so it costs the fold no row a draft would not. */
  const why = drafted ? "" : nextIntentNoDraftWhy(session, annotation);
  const noDraft = why
    ? `<p class="next-cockpit-held-lede" data-next-intent-no-draft>${esc(why)}</p>` : "";
  /* The design's word once words are saved, without its check mark: a check
     in this panel reads as a verdict (owner, DRC-4682). */
  const confirmed = String(annotation && annotation.goal || "").trim()
    ? '<span class="next-cockpit-held-confirmed">Confirmed</span>' : "";
  /* Named, because the reader has to know whose words these are: the harness
     and the session id are what the store keys on. */
  const intent = '<section class="next-cockpit-held">' +
    '<header><h2 id="next-session-intent-heading" tabindex="-1" ' +
    `data-next-focus="${esc(nextCockpitIntentHeadingKey(session))}">Intent</h2>` + confirmed +
    `<span class="next-cockpit-held-bound">${esc(sessKey(session))}</span></header>` +
    (drafted ? lede : noDraft) +
    (nextCockpitStoreUnreadable()
      ? `<p class="next-cockpit-held-absent">${esc(nextCockpitStoreUnreadable())}</p>` : "") +
    /* One line, the stamp and what it means, rather than two (DRC-4680 fold). */
    '<div class="next-cockpit-held-stamp">' +
    `<span class="next-cockpit-held-revision">${esc(revision)}</span>` +
    `<span class="next-cockpit-define">${NEXT_COCKPIT_REVISION_DEFINITION}</span></div>` +
    '<div class="next-cockpit-held-fields">' +
    NEXT_COCKPIT_HELD_FIELDS.map(spec =>
      nextCockpitHeldField(session, annotation, spec, cap)).join("") +
    nextCockpitHeldLines(session, annotation, cap, workSource) + '</div>' +
    '</section>';
  const reading = nextCockpitReadingParts(session, annotation, entries,
    nextCockpitObserverModel(group, session), observed, unsettled, workSource, primary);
  /* Below the reading, not between the fields and the control: none of these
     is the next thing to do, and above the control they pushed it off the
     first screen. */
  const discard = nextCockpitHeldDiscardBlock(session, annotation);
  const caveats = ended || discarded || binding || discard
    ? `<div class="next-session-drift-caveats">${ended}${discarded}${binding}${discard}</div>` : "";
  /* The saved introduction took 69.75px above the fields and put Analyze at
     892.5–936.5 with three lines and High on a 1440x900 board (DRC-4748).
     Keep its words below the action; the first-prompt draft's guide stays
     with the fields the reader is being asked to choose. */
  const savedIntroduction = drafted ? "" : lede;
  const panel = open + intent + head + reading.control + savedIntroduction + reading.reading +
    nextCockpitConflict(session, annotation, workSource) + caveats + reading.departures +
    '</section></aside>';
  /* In the activity column: the numbered list the reading cites right after
     CURRENT ACTIVITY, and how it landed and where a raise is kept after the
     session's facts. */
  const list = nextCockpitWorkEvidence(session, workSource, reading.cited);
  const record = nextCockpitLanded(observed) + nextCockpitDeparturesKept();
  return {panel, list, record, count: nextCockpitEntryTotal(session, workSource), pill};
}

/* The header's "N entries": the numbers given, and nothing where the record
   was not read, because a 0 there would be a default rather than a count. */
function nextCockpitEntryTotal(session, source){
  if(source.state !== "read" && source.state !== "empty") return null;
  return nextCockpitEntryNumbering(session, source).numbers.size;
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
  /* A running job is the answer to a second press: nothing is sent. */
  if(nextCockpitReadingRequests.get(key)?.pending || nextReadingJob(session)) return;
  /* Keep's "Press Allow and analyze" is answered by this press, so the region
     stops holding it. Emptying a region is silent. */
  nextCockpitKeepUnsay(key);
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
  /* Pending only until the server answers with its job, which it does before
     the model runs (DRC-4686); from then on the job is the state, published
     over the push, so it survives a reload the way this map never could. */
  const confirmation = nextCockpitReadingRequests.get(key);
  const adoption = allow && confirmation && confirmation.consent
    ? confirmation.adoption : nextImplicitAdoption(session);
  /* The revision this panel drew, so a press from a page another tab has
     since moved on is refused before anything starts (DRC-4732): the model
     would otherwise read words this reader never saw. */
  const expected = nextNumber(nextCockpitAnnotation(session)?.revision) || 0;
  const request = {pending: true, message: "", adoption};
  nextCockpitReadingRequests.set(key, request);
  renderNext();
  try{
    const response = await fetch("/api/reading", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({harness: session.harness, sid: session.sid, provider,
        press: true, observer_model: 1, ...adoption, expected_revision: expected,
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
    if(response && response.status === 409 && answer && answer.job){
      /* Another tab, or an earlier press, already started one: show it, then
         take the board's word for whether it is still running. */
      nextReadingJobShown(session, answer.job);
      renderNext();
      await refreshNext();
      return;
    }
    if(response && response.status === 409 && answer && answer.reason === "provider-changed"){
      /* Nothing was sent or saved. The next press starts again, and asks for
         the new receiver's own Allow if it has none. */
      request.message = NEXT_READING_PROVIDER_CHANGED;
      request.consent = false;
      await refreshNext();
      return;
    }
    if(response && response.status === 409 && answer && answer.reason === "revision-changed"){
      /* Nothing was started, adopted or allowed. The owner's stale sentence,
         shared with Keep: the next press is the reader's, against the words
         the refresh now draws. */
      request.message = NEXT_COCKPIT_KEEP_REFUSED;
      request.consent = false;
      /* Said once, by the persistent region, as Keep's is and under Keep's
         key, which the next press empties: a status paragraph inside `#app`
         was re-inserted and re-read on every render (a11y review F2). */
      request.announced = true;
      nextCockpitAnnounceCue(`keep:${key}`, NEXT_COCKPIT_KEEP_REFUSED, false);
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
    if(answer && answer.reason === "withheld" && typeof answer.withheld === "string"){
      /* Refused before any job (DRC-4758 slice A2): nothing started and
         nothing was spent. Held as this press's answer until the board
         publishes the row's own eligibility, which then wins, so the inert
         line stands beside the button now rather than after the next poll. */
      request.eligibility = {ok:false, reason:answer.withheld, until:nextNumber(answer.until),
        sentence:String(answer.sentence || "")};
      request.message = nextReadingPressLine(session, request.eligibility);
      request.refusal = true;
      request.consent = false;
      await refreshNext();
      return;
    }
    if(answer && answer.adoption_refused){
      request.message = "The prompt or saved goal changed. Review the current goal before analyzing again.";
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
    const started = Boolean(answer && answer.ok === true && answer.job &&
      typeof answer.job === "object");
    if(!started && (!answer || answer.ok !== true || typeof answer.produced !== "boolean")){
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
    if(started){
      /* Drawn now from the reply, then replaced by the board: a job can end
         before its own reply arrives, and a merged job the board has dropped
         would stand until the next poll and swallow every press. Every later
         phase and the result arrive with the revisions the job publishes. */
      nextReadingJobShown(session, answer.job);
      renderNext();
      await refreshNext();
      return;
    }
    /* Answered without a job: no annotated session by that name. */
    request.message = "No new reading was produced.";
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

/* Cancel the running analysis this box shows (DRC-4693). The job id goes with
   it, so a stale tab cannot cancel a newer press. One request per job: a
   Cancel in flight, or one the server already accepted, sends nothing. A
   `409 not-running` means the job ended or was never this one, and the board
   says what stands, with no sentence of this page's own. */
async function nextCockpitCancelReading(session){
  const key = sessKey(session);
  const job = nextReadingJob(session);
  const held = nextCockpitReadingCancels.get(key);
  if(!job || job.cancelling === true || (held && held.job === job.id && held.pending)) return;
  const cancel = {job: job.id, pending: true, failed: false};
  nextCockpitReadingCancels.set(key, cancel);
  renderNext();
  try{
    const response = await fetch("/api/reading/cancel", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({harness: session.harness, sid: session.sid, job: job.id,
        press: true, observer_model: 1}),
    });
    const answer = response && typeof response.json === "function"
      ? await response.json().catch(() => null) : null;
    if(response && response.status === 409 && answer && answer.reason === "not-running"){
      nextCockpitReadingCancels.delete(key);
      await refreshNext();
      return;
    }
    if(!response || response.status !== 202 || !answer || answer.cancelling !== true){
      throw new Error("cancel not confirmed");
    }
    nextReadingJobShown(session, {...job, cancelling: true});
    nextCockpitReadingCancels.delete(key);
    await refreshNext();
  }catch(_error){
    cancel.failed = true;
  }finally{
    cancel.pending = false;
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
    const answered = outcome === "unreadable" ? "discard-held"
      : ["stored", "refused", "unwritable", "untrusted"].includes(outcome)
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
      for(const kind of [...NEXT_COCKPIT_HELD_FIELDS.map(spec => spec[0]), "lines"]){
        nextCockpitHeldDrafts.delete(nextCockpitHeldKey(session, kind));
      }
      nextCockpitHeldOrigins.delete(nextCockpitHeldKey(session, "lines"));
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

/* The whole list in one save, with the revision it was drafted against, so a
   second tab's older list is refused rather than written over this one's. The
   store gives each line its source; the page never sends one. */
async function nextCockpitLinesSave(session){
  const key = nextCockpitHeldKey(session, "lines");
  const annotation = nextCockpitAnnotation(session);
  const draft = nextCockpitLinesDraft(session, annotation);
  if(!nextCockpitLinesChanged(draft, annotation)) return;
  const sent = nextCockpitLinesToSend(draft);
  const from = nextCockpitLinesOrigins(key, draft);
  const origins = draft.map((text, index) => [text, from[index]])
    .filter(([text]) => String(text || "").trim()).map(([_text, origin]) => origin);
  try{
    const response = await fetch("/api/annotate", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({harness: session.harness, sid: session.sid, goal: null, lines: sent,
        origins, expected_revision: nextNumber(annotation && annotation.revision) || 0}),
    });
    if(!response || !response.ok) throw new Error(`HTTP ${response && response.status}`);
    const saved = await response.json();
    if(!saved || saved.ok !== true) throw new Error("save not confirmed");
    const outcome = String(saved.outcome || "");
    const kind = NEXT_COCKPIT_HELD_OUTCOME_CUES[outcome] ||
      (saved.persisted === true ? "saved" : "unpersisted");
    // The draft goes only where the words are on disk and still match what
    // was sent, for `nextCockpitHeldSave`'s reasons.
    const held = nextCockpitHeldDrafts.get(key);
    if((kind === "saved" || kind === "unchanged") && held &&
        JSON.stringify(nextCockpitLinesToSend(held)) === JSON.stringify(sent)){
      nextCockpitLinesForget(key);
    }
    nextCockpitHeldMark(key, kind);
    await refreshNext();
  }catch(_error){
    nextCockpitHeldMark(key, "error");
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
  /* The box back at the draft is Looks right, never a typed save of an
     excerpt (DRC-4682). */
  const drafted = kind === "goal" ? nextIntentDraft(session, annotation) : null;
  if(drafted && typed === drafted.text){
    nextAdoptPrompt(session, drafted.source);
    return;
  }
  if(typed === stored) return;
  // Only the field that changed. An absent field is "leave this one alone" at
  // the endpoint, and "" is "clear it": sending both every time would let a
  // stale draft of one overwrite a save of the other. The outcome lines save
  // through `nextCockpitLinesSave`.
  const sent = nextCockpitHeldDrafts.has(key) ? nextCockpitHeldDrafts.get(key) : null;
  /* With the revision this box was drawn against, as the lines save sends
     one, so a save from a tab another tab has moved on is refused and the
     typed words stay in the box (DRC-4732) rather than replacing words this
     reader never saw. */
  const body = {harness: session.harness, sid: session.sid, [kind]: sent,
    expected_revision: nextNumber(annotation && annotation.revision) || 0};
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
    return direction && direction.type === "user_message" && !nextReadingCopied(direction) &&
      exactlyBound(direction) && sameTask && ordered ? direction : null;
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
    !nextReadingCopied(fact) && !used.has(String(fact.fact_id || "")) &&
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

function nextCockpitBeforeRender(focus){
  nextCockpitReadingJobsDrawn.clear();
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

/* A new empty outcome line, focused, or the six-line refusal said in place. */
function nextCockpitLinesAdd(session){
  const key = nextCockpitHeldKey(session, "lines");
  const draft = nextCockpitLinesDraft(session, nextCockpitAnnotation(session));
  const origins = nextCockpitLinesOrigins(key, draft);
  if(draft.length >= NEXT_OUTCOME_LINES_MAX){
    // Refused in place: nothing is added, and the sentence beside the
    // control is said aloud, because an inert control that goes silent
    // reads as a dead one.
    nextCockpitAnnounceCue(key, NEXT_COCKPIT_LINES_FULL, false);
    return;
  }
  // An empty list is drawn as one empty box, so adding to it adds the second.
  if(!draft.length){ draft.push(""); origins.push(null); }
  draft.push("");
  origins.push(null);
  nextCockpitLinesKeep(key, draft, origins);
  nextCockpitHeldDrop(key);
  renderNext({named: `${key}:${Math.max(0, draft.length - 1)}`});
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

/* The run of code points an edit inserted into `before` to give `typed`: the
   common head and tail, with the caret, where the field has one, deciding
   which of two equal runs moved. */
function nextCockpitCorrectionEdit(before, typed, caret){
  const was = [...before];
  const now = [...typed];
  let tail = 0;
  if(typeof caret === "number" && caret >= 0 && caret <= typed.length){
    const after = [...typed.slice(caret)];
    if(after.length <= was.length && before.endsWith(after.join(""))) tail = after.length;
  }
  let head = 0;
  const most = Math.min(was.length, now.length) - tail;
  while(head < most && was[head] === now[head]) head += 1;
  if(!(typeof caret === "number")){
    while(tail < Math.min(was.length, now.length) - head &&
      was[was.length - 1 - tail] === now[now.length - 1 - tail]) tail += 1;
  }
  return {head: now.slice(0, head).join(""), run: now.slice(head, now.length - tail),
    tail: now.slice(now.length - tail).join("")};
}

/* The leading whole characters of `run` that fit in `room` code points: by
   grapheme where the platform segments text, and otherwise never ending on a
   base whose combining mark or joined character is left behind. */
function nextCockpitCorrectionWhole(run, room){
  if(room <= 0) return "";
  const text = run.join("");
  if(typeof Intl === "object" && typeof Intl.Segmenter === "function"){
    let kept = "";
    let count = 0;
    for(const {segment} of new Intl.Segmenter(undefined, {granularity: "grapheme"}).segment(text)){
      const width = [...segment].length;
      if(count + width > room) break;
      kept += segment;
      count += width;
    }
    return kept;
  }
  let cut = Math.min(room, run.length);
  const joined = /^[\p{M}\u200d\ufe0e\ufe0f]$/u;
  while(cut > 0 && cut < run.length && (joined.test(run[cut]) || run[cut - 1] === "\u200d")) cut -= 1;
  return run.slice(0, cut).join("");
}

/* An edit past the cap keeps the reader's existing text and cuts the inserted
   run (V2), or null when the edit fits. A first version kept the first 2,000
   code points of the whole value, so a paste in the middle cut the text's end
   and left a bare "e" where "é" had been split. */
function nextCockpitCorrectionFit(before, typed, caret){
  if(nextCockpitCorrectionLength(typed) <= NEXT_COCKPIT_CORRECTION_CAP) return null;
  const edit = nextCockpitCorrectionEdit(before, typed, caret);
  const kept = nextCockpitCorrectionLength(edit.head) + nextCockpitCorrectionLength(edit.tail);
  const run = nextCockpitCorrectionWhole(edit.run, NEXT_COCKPIT_CORRECTION_CAP - kept);
  return {value: edit.head + run + edit.tail, caret: edit.head.length + run.length};
}

let nextCockpitCorrectionComposition = null;
let nextCockpitCorrectionPendingRender = null;
let nextCockpitCorrectionPointer = null;

function nextCockpitCorrectionInput(event){
  return event.target && event.target.closest
    ? event.target.closest("[data-next-cockpit-correction-key]") : null;
}

function nextCockpitCorrectionUpdateTools(input, held){
  const box = input.closest ? input.closest("[data-next-steer-box]") : null;
  if(!box || !box.querySelector) return;
  const count = box.querySelector("[data-next-correction-count]");
  if(count) count.textContent = `${nextCockpitCorrectionLength(input.value)}/${NEXT_COCKPIT_CORRECTION_CAP}`;
  const cue = box.querySelector("[data-next-correction-cue]");
  if(cue) cue.textContent = held.cue === "copied" ? "Copied"
    : held.cue === "failed" ? "Copy unavailable" : "Copy";
  const why = box.querySelector("[data-next-correction-edit-why]");
  if(why){ why.textContent = held.editWhy || ""; why.hidden = !held.editWhy; }
  const paint = box.querySelector("[data-next-correction-paint-why]");
  if(paint){ paint.textContent = held.paintWhy || ""; paint.hidden = !held.paintWhy; }
}

function nextCockpitCorrectionEditRefused(input, held, why){
  held.editWhy = why;
  nextCockpitCorrectionUpdateTools(input, held);
  const key = `correction-edit:${String(input.dataset.nextCockpitCorrectionKey || "")}`;
  nextCockpitAnnouncedCues.delete(key);
  nextCockpitAnnounceCue(key, why, false);
}

function nextCockpitCorrectionNative(input, command, text){
  if(document.activeElement !== input || typeof document.execCommand !== "function") return false;
  try{ return document.execCommand(command, false, text); }
  catch(_error){ return false; }
}

function nextCockpitCorrectionRestore(input, before, start, end){
  const held = nextCockpitCorrections.get(String(input.dataset.nextCockpitCorrectionKey || ""));
  let undone = false;
  /* Native undo may synchronously publish input. A mismatched undo must
     never replace the held draft with the text being refused. */
  if(held) held.restoring = true;
  try{ undone = nextCockpitCorrectionNative(input, "undo") && input.value === before; }
  finally{ if(held) held.restoring = false; }
  /* A browser without native undo still keeps every pre-composition word.
     Assignment loses its undo history, so that fallback says so. */
  if(!undone) input.value = before;
  if(typeof input.setSelectionRange === "function" && typeof start === "number"){
    input.setSelectionRange(start, typeof end === "number" ? end : start);
  }
  return undone;
}

/* Intercept before the browser inserts an over-cap run. The native edit
   command keeps that insertion in its undo transaction; assigning .value
   after input erased the preceding edit as well (DRC-4739, Chrome measured).
   Paste needs its own event: textarea beforeinput may carry no paste data. */
function nextCockpitCorrectionInsert(event, text){
  const input = nextCockpitCorrectionInput(event);
  if(!input || event.isComposing || nextCockpitCorrectionComposition) return;
  const held = nextCockpitCorrections.get(String(input.dataset.nextCockpitCorrectionKey || ""));
  if(!held || event.cancelable === false) return;
  const before = String(input.value || "");
  const start = typeof input.selectionStart === "number" ? input.selectionStart : before.length;
  const end = typeof input.selectionEnd === "number" ? input.selectionEnd : start;
  const typed = before.slice(0, start) + text + before.slice(end);
  const fitted = nextCockpitCorrectionFit(before, typed, start + text.length);
  if(!fitted) return;
  event.preventDefault();
  if(fitted.value === before) return;
  const tail = before.slice(end);
  const inserted = fitted.value.slice(start, fitted.value.length - tail.length);
  let accepted = false;
  held.restoring = true;
  try{ accepted = nextCockpitCorrectionNative(input, "insertText", inserted); }
  finally{ held.restoring = false; }
  if(accepted && input.value === fitted.value){
    held.text = fitted.value;
    held.edited = true;
    held.cue = "";
    held.editWhy = "";
    nextCockpitCorrectionUpdateTools(input, held);
    return;
  }
  const undone = input.value === before || nextCockpitCorrectionRestore(input, before, start, end);
  nextCockpitCorrectionEditRefused(input, held, NEXT_COCKPIT_CORRECTION_EDIT_REFUSED +
    (undone ? "" : ` ${NEXT_COCKPIT_CORRECTION_UNDO_UNAVAILABLE}`));
}

document.addEventListener("paste", event => {
  if(!nextCockpitCorrectionInput(event) || !event.clipboardData) return;
  nextCockpitCorrectionInsert(event, event.clipboardData.getData("text/plain"));
});

document.addEventListener("beforeinput", event => {
  const input = nextCockpitCorrectionInput(event);
  if(!input || event.isComposing || nextCockpitCorrectionComposition) return;
  const kind = String(event.inputType || "");
  if(kind === "insertFromPaste" || !kind.startsWith("insert")) return;
  if(kind === "insertLineBreak" || kind === "insertParagraph"){
    nextCockpitCorrectionInsert(event, "\n");
    return;
  }
  const text = typeof event.data === "string" ? event.data : event.dataTransfer
    && typeof event.dataTransfer.getData === "function" ? event.dataTransfer.getData("text/plain") : null;
  if(text !== null){ nextCockpitCorrectionInsert(event, text); return; }
  const held = nextCockpitCorrections.get(String(input.dataset.nextCockpitCorrectionKey || ""));
  if(held && event.cancelable !== false){
    event.preventDefault();
    nextCockpitCorrectionEditRefused(input, held, NEXT_COCKPIT_CORRECTION_EDIT_REFUSED);
  }
});

/* Even an atomic connected move cleared Chrome's native undo. Payloads can
   still arrive, but their paint waits until the reader leaves this editor. */
function nextCockpitCorrectionPausePaint(input, held, focus){
  nextCockpitCorrectionPendingRender = {focus};
  held.paintWhy = NEXT_COCKPIT_CORRECTION_PAINT_PAUSED;
  nextCockpitCorrectionUpdateTools(input, held);
}

function nextCockpitCorrectionDefersRender(focus){
  if(nextCockpitCorrectionComposition){
    nextCockpitCorrectionPendingRender = {focus};
    return true;
  }
  if(nextCockpitCorrectionPointer){
    if(nextRoute.view === "session" &&
        nextCockpitCorrectionPointer.key === `${nextRoute.harness}:${nextRoute.session}`){
      nextCockpitCorrectionPendingRender = {focus};
      return true;
    }
    nextCockpitCorrectionPointer = null;
  }
  const input = nextCockpitCorrectionInput({target: document.activeElement});
  const key = input && String(input.dataset.nextCockpitCorrectionKey || "");
  const held = key && nextCockpitCorrections.get(key);
  if(!held || !held.edited || nextRoute.view !== "session" ||
      key !== `${nextRoute.harness}:${nextRoute.session}`) return false;
  nextCockpitCorrectionPausePaint(input, held, focus);
  return true;
}

function nextCockpitCorrectionResumePaint(){
  Promise.resolve().then(() => {
    if(nextCockpitCorrectionPointer) return;
    const pending = nextCockpitCorrectionPendingRender;
    nextCockpitCorrectionPendingRender = null;
    if(pending) renderNext();
  });
}

/* Blur runs between pointer down and click. Replacing the pressed control
   there swallowed Chrome's first Copy. Wait for dispatch, not a timer: a
   reader may hold the pointer down longer than any guessed delay. */
document.addEventListener("pointerdown", event => {
  if(event.button !== 0 || event.isPrimary === false || nextCockpitCorrectionInput(event)) return;
  const input = nextCockpitCorrectionInput({target: document.activeElement});
  const key = input && String(input.dataset.nextCockpitCorrectionKey || "");
  const held = key && nextCockpitCorrections.get(key);
  if(!held || !held.edited) return;
  const target = event.target && event.target.closest
    ? event.target.closest("button,a,summary,[role=button]") || event.target : event.target;
  nextCockpitCorrectionPointer = {id: event.pointerId, target, key};
}, true);

function nextCockpitCorrectionPointerDone(){
  nextCockpitCorrectionPointer = null;
  nextCockpitCorrectionResumePaint();
}

document.addEventListener("click", () => {
  if(!nextCockpitCorrectionPointer) return;
  /* Listener microtask checkpoints may precede the bubble action handler. */
  setTimeout(nextCockpitCorrectionPointerDone, 0);
}, true);

document.addEventListener("pointerup", event => {
  const pointer = nextCockpitCorrectionPointer;
  if(!pointer || event.pointerId !== pointer.id) return;
  if(pointer.target === event.target || pointer.target && pointer.target.contains &&
      pointer.target.contains(event.target)) return;
  nextCockpitCorrectionPointerDone();
}, true);

document.addEventListener("pointercancel", event => {
  if(nextCockpitCorrectionPointer && event.pointerId === nextCockpitCorrectionPointer.id){
    nextCockpitCorrectionPointerDone();
  }
}, true);
window.addEventListener("blur", nextCockpitCorrectionPointerDone);
document.addEventListener("keydown", event => {
  if(event.key === "Tab" && nextCockpitCorrectionPointer) nextCockpitCorrectionPointerDone();
}, true);

document.addEventListener("blur", event => {
  const input = nextCockpitCorrectionInput(event);
  if(!input) return;
  const held = nextCockpitCorrections.get(String(input.dataset.nextCockpitCorrectionKey || ""));
  if(held) held.paintWhy = "";
  nextCockpitCorrectionResumePaint();
}, true);

document.addEventListener("compositionstart", event => {
  const input = nextCockpitCorrectionInput(event);
  if(!input) return;
  const key = String(input.dataset.nextCockpitCorrectionKey || "");
  const held = nextCockpitCorrections.get(key);
  if(!held) return;
  nextCockpitCorrectionComposition = {input, held, before: String(input.value || ""),
    edited: held.edited, start: input.selectionStart, end: input.selectionEnd};
});

document.addEventListener("compositionend", event => {
  const composition = nextCockpitCorrectionComposition;
  if(!composition || event.target !== composition.input) return;
  nextCockpitCorrectionComposition = null;
  const {input, held, before, start, end} = composition;
  if(nextCockpitCorrectionLength(input.value) > NEXT_COCKPIT_CORRECTION_CAP){
    const undone = nextCockpitCorrectionRestore(input, before, start, end);
    held.text = before;
    held.edited = composition.edited;
    held.compositionRefused = before;
    nextCockpitCorrectionEditRefused(input, held, NEXT_COCKPIT_CORRECTION_COMPOSITION_REFUSED +
      (undone ? "" : ` ${NEXT_COCKPIT_CORRECTION_UNDO_UNAVAILABLE}`));
  }else if(input.value !== before){
    held.text = input.value;
    held.edited = true;
    held.cue = "";
    held.editWhy = "";
    nextCockpitCorrectionUpdateTools(input, held);
  }
  /* Browsers may publish the final input after compositionend. Let that
     update the held draft before drawing a payload received during the edit. */
  nextCockpitCorrectionResumePaint();
});

/* The correction box, edited in place with no redraw, for the held fields'
   measured reason below. Capped at the copy route's 2,000 characters, counted
   as the server counts them, cut from what the edit inserted and never from
   the text already there;
   an edit makes the text the reader's own and clears the Copy cue, which
   described the text before it. */
document.addEventListener("input", event => {
  const input = nextCockpitCorrectionInput(event);
  if(!input) return;
  if(event.isComposing || nextCockpitCorrectionComposition &&
      nextCockpitCorrectionComposition.input === input) return;
  const held = nextCockpitCorrections.get(String(input.dataset.nextCockpitCorrectionKey || ""));
  if(!held || held.restoring) return;
  const typed = String(input.value || "");
  if(held.compositionRefused === typed) return;
  delete held.compositionRefused;
  const before = typeof held.text === "string" ? held.text : String(input.defaultValue || "");
  if(nextCockpitCorrectionLength(typed) > NEXT_COCKPIT_CORRECTION_CAP){
    const undone = nextCockpitCorrectionRestore(input, before, before.length, before.length);
    nextCockpitCorrectionEditRefused(input, held, NEXT_COCKPIT_CORRECTION_EDIT_REFUSED +
      (undone ? "" : ` ${NEXT_COCKPIT_CORRECTION_UNDO_UNAVAILABLE}`));
    return;
  }
  held.text = typed;
  held.edited = true;
  held.cue = "";
  held.editWhy = "";
  nextCockpitCorrectionUpdateTools(input, held);
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
  /* The draft's marks describe the draft, so they go with the first edit
     and come back if the box is put back to it. */
  if(input.dataset.nextCockpitDraft != null){
    const untouched = value === String(input.dataset.nextCockpitDraft);
    const marks = field.querySelector("[data-next-cockpit-draft-marks]");
    if(marks) marks.hidden = !untouched;
    if(untouched) field.setAttribute("data-next-cockpit-drafted", "");
    else field.removeAttribute("data-next-cockpit-drafted");
  }
});

/* The pending direction's box, updated in place for the goal field's reason.
   No slice: the whole text stays, and a line over the bound is refused at the
   save rather than cut here. */
document.addEventListener("input", event => {
  const input = event.target && event.target.closest
    ? event.target.closest("[data-next-cockpit-direction-key]") : null;
  if(!input) return;
  const key = String(input.dataset.nextCockpitDirectionKey || "");
  const held = nextCockpitDirectionLines.get(key);
  if(!held || typeof held.text !== "string") return;
  const value = String(input.value || "").replace(NEXT_COCKPIT_HELD_UNSAFE, " ");
  if(value !== input.value) input.value = value;
  held.text = value;
  held.cue = "";
  const line = input.closest("[data-next-cockpit-direction-line]");
  if(!line || !line.querySelector) return;
  const session = nextCockpitFocusedSession(nextCockpitRouteGroup());
  const cap = nextCockpitHeldCap();
  const why = nextCockpitDirectionWhy(held, session ? nextCockpitAnnotation(session) : null, cap,
    session);
  const count = line.querySelector("[data-next-cockpit-direction-count]");
  if(count) count.textContent = `${value.length}/${cap}`;
  const said = line.querySelector("[data-next-cockpit-direction-why]");
  if(said){ said.textContent = why; said.hidden = !why; }
  /* The list's copy follows, so one of the two says full while the list is
     (DRC-4760): typing past the bound swaps the line's reason in place. */
  const field = typeof line.closest === "function" ? line.closest("[data-next-cockpit-held-field]") : null;
  const listSays = field && field.querySelector ? field.querySelector("[data-next-cockpit-held-full]") : null;
  if(listSays && session){
    const annotation = nextCockpitAnnotation(session);
    const full = nextCockpitLinesDraft(session, annotation).length >= NEXT_OUTCOME_LINES_MAX;
    listSays.hidden = !full || why === NEXT_COCKPIT_LINES_FULL;
  }
  const save = line.querySelector('[data-next-cockpit-action="direction-save"]');
  if(save){
    if(!why && value.trim()) save.removeAttribute("aria-disabled");
    else save.setAttribute("aria-disabled", "true");
    if(why) save.setAttribute("aria-describedby", "next-cockpit-direction-why");
    else save.removeAttribute("aria-describedby");
  }
});

/* A line box, updated in place for the goal field's reason: a keystroke that
   redraws loses the caret. The store's own scrub is mirrored, so a pasted line
   break is the one space the store will keep. */
document.addEventListener("input", event => {
  const input = event.target && event.target.closest
    ? event.target.closest("[data-next-cockpit-held-lines-key]") : null;
  if(!input) return;
  const key = String(input.dataset.nextCockpitHeldLinesKey || "");
  const index = Number(input.dataset.nextCockpitHeldLineIndex);
  const session = nextCockpitFocusedSession(nextCockpitRouteGroup());
  if(!key || !Number.isInteger(index) || !session) return;
  const value = String(input.value || "")
    .replace(NEXT_COCKPIT_HELD_UNSAFE, " ").slice(0, nextCockpitHeldCap());
  if(value !== input.value) input.value = value;
  const annotation = nextCockpitAnnotation(session);
  const draft = nextCockpitLinesDraft(session, annotation);
  const origins = nextCockpitLinesOrigins(key, draft);
  while(draft.length <= index){ draft.push(""); origins.push(null); }
  draft[index] = value;
  nextCockpitLinesKeep(key, draft, origins);
  nextCockpitHeldDrop(key);
  const field = input.closest("[data-next-cockpit-held-field]");
  if(!field || !field.querySelector) return;
  const count = field.querySelector(`[data-next-cockpit-held-line-count="${index}"]`);
  if(count) count.textContent = `${value.length}/${nextCockpitHeldCap()}`;
  const source = field.querySelector(`[data-next-cockpit-held-line-source="${index}"]`);
  /* Hidden and still taking its space, so the row holds still (DRC-4714). */
  if(source){
    if(value === String(input.dataset.nextCockpitHeldSaved || "")){
      source.removeAttribute("data-next-cockpit-held-line-source-stale");
    }else{
      source.setAttribute("data-next-cockpit-held-line-source-stale", "");
    }
  }
  nextCockpitHeldToggle(field, "held-save", nextCockpitLinesChanged(draft, annotation), true);
  const absent = field.querySelector("[data-next-cockpit-held-absent]");
  if(absent) absent.hidden = nextCockpitLinesToSend(draft).length > 0;
});

document.addEventListener("click", event => {
  const target = nextCockpitActionTarget(event);
  if(!target) return;
  const action = String(target.dataset.nextCockpitAction || "");
  const group = nextCockpitRouteGroup();
  if(action === "live-monitor"){
    const session = group ? nextCockpitFocusedSession(group) : null;
    if(!session) return;
    event.preventDefault();
    nextLiveMonitorSet(session, !nextLiveMonitorOn(session));
    renderNext();
    return;
  }
  if(action === "held-line-add" || action === "held-line-remove"){
    const session = group ? nextCockpitFocusedSession(group) : null;
    if(!session) return;
    event.preventDefault();
    if(action === "held-line-add"){
      nextCockpitLinesAdd(session);
      return;
    }
    const key = nextCockpitHeldKey(session, "lines");
    const draft = nextCockpitLinesDraft(session, nextCockpitAnnotation(session));
    const origins = nextCockpitLinesOrigins(key, draft);
    draft.splice(Number(target.dataset.arg), 1);
    origins.splice(Number(target.dataset.arg), 1);
    nextCockpitLinesKeep(key, draft, origins);
    nextCockpitHeldDrop(key);
    renderNext({named: `${key}:${Math.max(0, draft.length - 1)}`});
    return;
  }
  if(["steer-back", "correction-copy", "correction-recompose", "update-intent"].includes(action)){
    const session = group ? nextCockpitFocusedSession(group) : null;
    if(!session) return;
    event.preventDefault();
    if(action === "steer-back"){
      nextCockpitSteerBack(session, nextCockpitCorrectionStamp(nextCockpitAnnotation(session)));
    }else if(action === "correction-recompose"){
      /* The reader asked for the record as it stands, over their edit. */
      nextCockpitComposeCorrection(session, nextCockpitCorrectionStamp(nextCockpitAnnotation(session)));
    }else if(action === "correction-copy"){
      nextCockpitCopyCorrection(session, target, nextCockpitWorkSource(group, session));
    }else if(action === "update-intent"){
      /* Update intent instead: the offered direction opens as the pending line
         through Add's own path, or, with none, an empty line (owner,
         2026-09-28). The goal is never touched. */
      const factId = String(target.dataset.arg || "");
      const n = nextCockpitEntryNumbers(session, nextCockpitWorkSource(group, session)).get(factId);
      if(factId) nextCockpitOpenDirection(session, factId, n == null ? null : n, true);
      else nextCockpitLinesAdd(session);
    }
    return;
  }
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
  if(action === "reading-not-now"){
    const session = group ? nextCockpitFocusedSession(group) : null;
    if(!session) return;
    event.preventDefault();
    nextCockpitReadingNotNow(session);
    return;
  }
  if(action === "reading-cancel"){
    const session = group ? nextCockpitFocusedSession(group) : null;
    if(!session) return;
    event.preventDefault();
    nextCockpitCancelReading(session);
    return;
  }
  if(action === "not-accurate"){
    const session = group ? nextCockpitFocusedSession(group) : null;
    const readAt = Number(target.dataset.arg);
    if(!session || !String(target.dataset.arg || "").trim() || !Number.isFinite(readAt)) return;
    event.preventDefault();
    nextCockpitMarkNotAccurate(session, readAt);
    return;
  }
  if(action === "reading-ask" || action === "reading-allow"){
    const session = group ? nextCockpitFocusedSession(group) : null;
    if(!session) return;
    event.preventDefault();
    nextCockpitAskForReading(session, nextCockpitObserverModel(group), action === "reading-allow");
    return;
  }
  if(["draft-confirm", "direction-keep", "direction-add", "direction-save", "direction-cancel",
      "direction-replace"].includes(action)){
    const session = group ? nextCockpitFocusedSession(group) : null;
    if(!session) return;
    event.preventDefault();
    const key = sessKey(session);
    if(action === "draft-confirm"){
      const draft = nextIntentDraft(session, nextCockpitAnnotation(session));
      if(draft) nextAdoptPrompt(session, draft.source);
    }else if(action === "direction-keep"){
      nextCockpitKeepIntent(session, nextCockpitObserverModel(group));
    }else if(action === "direction-add"){
      const factId = String(target.dataset.arg || "");
      const n = nextCockpitEntryNumbers(session, nextCockpitWorkSource(group, session)).get(factId);
      if(factId) nextCockpitOpenDirection(session, factId, n == null ? null : n);
    }else if(action === "direction-save"){
      nextCockpitSaveDirection(session);
    }else if(action === "direction-cancel"){
      nextCockpitDirectionLines.delete(key);
      renderNext({named: `direction-add:${key}`});
    }else if(action === "direction-replace"){
      const held = nextCockpitDirectionLines.get(key);
      const index = Number(target.dataset.arg);
      if(held && Number.isInteger(index) && index >= 0 && index < NEXT_OUTCOME_LINES_MAX){
        held.replace = held.replace === index ? null : index;
        renderNext({named: `direction-replace:${key}:${index}`});
      }
    }
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
    if(action === "held-save" && kind === "lines"){
      nextCockpitLinesSave(session);
      return;
    }
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
  const lines = event.target && event.target.closest
    ? event.target.closest("[data-next-cockpit-held-lines-key]") : null;
  if(event.key === "Escape" && lines){
    // The whole list goes back to what is saved, added and removed lines
    // included: the draft is one array, and dropping it is the one place the
    // render and the store cannot disagree.
    event.preventDefault();
    const key = String(lines.dataset.nextCockpitHeldLinesKey || "");
    nextCockpitLinesForget(key);
    nextCockpitHeldDrop(key);
    renderNext({named: `${key}:0`});
    return true;
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


/* The server's verdict, never re-derived here: `transcripts.first_prompt`
   asks the one control rule the goal slot and the instruction line share. */
function nextIntentOpenedWithControl(session){
  return Boolean(session && ["claude", "codex"].includes(session.harness) &&
    session.first_prompt_control === true);
}

/* Why the goal box arrives empty over such a session, or "" where it does
   not: the command's name alone, since its arguments are not the reader's
   goal either (DRC-4766). */
function nextIntentNoDraftWhy(session, annotation){
  if(!(nextData && nextData.annotate === true) || nextCockpitStoreUnreadable()) return "";
  const goal = annotation ? annotation.goal : session && session.annotation_goal;
  if(String(goal || "").trim() || !nextIntentOpenedWithControl(session)) return "";
  const command = String(session.first_prompt || "").trim().split(/\s+/)[0];
  return command ? `This session opened with ${command}, so there is no first prompt to ` +
    "draft a goal from." : "";
}

function nextPromptCandidate(session, source = "latest-prompt"){
  if(!session || !["claude", "codex"].includes(session.harness)) return null;
  let text = "", at = null;
  if(source === "first-prompt"){
    /* A correction the reader copied from Cargento is never their goal, as
       `annotations.prompt_candidate` refuses it (DRC-4678); the latest-prompt
       arm refuses it through `nextSessionInstruction`. */
    if(nextPromptCopied(session, "first_prompt")) return null;
    text = String(session.first_prompt || ""); at = nextNumber(session.first_prompt_at);
  }else if(source === "latest-prompt" && session.harness === "claude"){
    const asked = nextSessionInstruction(session, "asked");
    if(asked){ text = String(asked.text || ""); at = nextNumber(asked.at); }
  }else if(source === "latest-prompt" && session.prompt_states_work === true){
    text = String(session.title || ""); at = nextNumber(session.prompt_at);
  }
  return text ? {text, at: at != null && at > 0 ? at : null, source} : null;
}

/* The goal a goal-less session arrives with (item 2 of
   [DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy),
   DRC-4682): the first prompt as Cargento publishes it, or the latest where no
   first prompt with a time is published, and null where neither can be
   adopted. Derived from the payload on every render and never written, so it
   holds no reader state; the box's own edits ride the held draft Map. Nothing
   is drafted over a store this build cannot read, where Looks right could not
   save. */
function nextIntentDraft(session, annotation){
  if(!(nextData && nextData.annotate === true) || nextCockpitStoreUnreadable()) return null;
  const goal = annotation ? annotation.goal : session && session.annotation_goal;
  if(String(goal || "").trim()) return null;
  /* A session that opened with a harness control has no first prompt to
     draft, and the latest is a later record, which the first-prompt read
     never drafts from (DRC-4766, SECURITY.md). */
  if(nextIntentOpenedWithControl(session)) return null;
  for(const source of ["first-prompt", "latest-prompt"]){
    const candidate = nextPromptCandidate(session, source);
    if(candidate && candidate.at != null) return candidate;
  }
  return null;
}

/* Whether a press would stand on words other than the ones on screen: the
   goal box differs from what it stands on (the draft, or the saved goal), or
   the outcome-lines draft differs from what the server holds. A box put back
   to those words is not an edit. Keep, Add's save and Analyze are refused
   over one, for goals saved or drafted alike (consent F1 and F2, Codex 2). */
function nextIntentUnsaved(session, annotation){
  const goalKey = nextCockpitHeldKey(session, "goal");
  if(nextCockpitHeldDrafts.has(goalKey)){
    const draft = nextIntentDraft(session, annotation);
    const stands = draft ? draft.text
      : String(annotation ? annotation.goal || "" : session && session.annotation_goal || "");
    if(nextCockpitHeldDrafts.get(goalKey) !== stands) return true;
  }
  const linesKey = nextCockpitHeldKey(session, "lines");
  return nextCockpitHeldDrafts.has(linesKey) &&
    nextCockpitLinesChanged(nextCockpitHeldDrafts.get(linesKey), annotation);
}

/* After a press that adopted the draft, the held goal goes only while it still
   equals that draft, so nothing typed while the request was open is dropped. */
function nextIntentForgetAdopted(session, draft){
  const key = nextCockpitHeldKey(session, "goal");
  if(draft && nextCockpitHeldDrafts.get(key) === draft.text) nextCockpitHeldDrafts.delete(key);
}

/* The one predicate the level (DRC-4695) and the live estimate and its pill
   (DRC-4696) consult: over an unsaved draft neither is drawn (item 2 of
   [DEC-26](docs/design-reading-a-session.md#dec-26-four-drift-levels-and-a-live-estimate-after-every-turn)). */
function nextIntentDrafted(session, annotation){
  return Boolean(nextIntentDraft(session, annotation));
}

/* Analyze or Keep over an unsaved edit would read words that are not on
   screen, so the press is refused (owner's words, DRC-4682 fix round). Add's
   save has its own sentence, beside its line. */
const NEXT_INTENT_EDITED =
  "Save your intent, or undo your edit, to analyze drift.";
const NEXT_INTENT_EDITED_ADD =
  "Save your intent, or undo your edit, to add this direction.";

function nextIntentAdoption(draft){
  return draft ? {adopt:draft.source, expected_prompt:draft.text,
    expected_prompt_at:draft.at} : {};
}

function nextImplicitAdoption(session){
  return nextIntentAdoption(nextIntentDraft(session, null));
}

function nextPromptReadingRefusal(session, annotation, model){
  if(!(nextData && nextData.annotate === true)) return NEXT_READING_ANNOTATIONS_OFF;
  /* A route with no reader is a fact about this machine, and it outranks any
     step the page could name: saving a goal here would not let a check run. */
  const route = nextReadingRoute(session);
  if(route && !route.provider) return nextReadingRouteRefusal(session);
  /* So does a press the board already says it cannot serve: saving or
     choosing words would not let it read (DRC-4758 slice B). */
  const press = nextReadingPressRefusal(session);
  if(press) return press;
  if(nextIntentUnsaved(session, annotation)) return NEXT_INTENT_EDITED;
  if(!String(annotation && annotation.goal || "").trim()){
    const draft = nextIntentDraft(session, annotation);
    /* Over a control-first session the latest prompt is no goal either, so
       the press falls to the refusal for nothing typed (DRC-4766). */
    const candidate = draft ||
      (nextIntentOpenedWithControl(session) ? null : nextPromptCandidate(session));
    if(candidate && candidate.at == null){
      return "The prompt time was not published, so it cannot be adopted. Type a goal to analyze drift.";
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
  /* The latest alone: the first prompt is the draft now, and Looks right is
     its adoption, so a second "Use first prompt" would say it twice. */
  const choices = ["latest-prompt"].map(source => {
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

const NEXT_COCKPIT_ADOPT_REFUSED = {
  untrusted: "Cargento could not read cargento-annotations.json, so your prompt was not saved as " +
    "the goal and nothing was overwritten. Move or repair that file to save again.",
  unreadable: "This session's words were saved by a build of Cargento that can read more than " +
    "this one, so your prompt was not saved as the goal. Save from that build, or remove this " +
    "session's entry from cargento-annotations.json.",
};

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
    if(response.ok && answer && ["untrusted", "unreadable"].includes(String(answer.outcome || ""))){
      /* Not a changed prompt: the store could not take the save at all, and
         saying the prompt changed would send the reader to the wrong place. */
      nextCockpitReadingRequests.set(sessKey(session), {message:
        NEXT_COCKPIT_ADOPT_REFUSED[String(answer.outcome)]});
      return;
    }
    if(!response.ok || !answer.persisted) throw new Error("adoption not saved");
    nextCockpitHeldDrafts.delete(key);
    await refreshNext();
  }catch(_error){
    nextCockpitReadingRequests.set(sessKey(session),{message:"The prompt or saved goal changed, or could not be saved. Review the goal before trying again."});
  }finally{renderNext();}
}
