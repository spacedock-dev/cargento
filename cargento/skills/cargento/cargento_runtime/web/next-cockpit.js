const NEXT_COCKPIT_MEMO_PREFIX = "cargento.cockpit.memo.v2:";
const NEXT_COCKPIT_MEMO_LIMIT = 500;
const nextCockpitContexts = new Map();
const nextCockpitRequests = new Map();
const nextCockpitReadingRequests = new Map();
/* A Cancel in flight, or one that could not be confirmed, per session and for
   the one job it named, so neither outlives that job's box (DRC-4693). */
const nextCockpitReadingCancels = new Map();
/* Whether Analyze can be pressed, as the drawn Drift card last showed it, so a
   change no press caused is said rather than silent (owner, 2026-10-02):
   `nextReadingFlip` owns it, docs/design-reader-state.md holds the row. */
const nextReadingFlips = new Map();
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
  /* `open` is written into the markup rather than set after insertion: a
     transition runs when `open` flips on a node already in the document, so
     the old post-insert `.open = true` replayed the opening motion on every
     poll that slipped a style read in first. Drawn open, the redraw has
     nothing to animate and only the reader's own toggle moves
     ([reader state](docs/design-reader-state.md#the-inventory)). */
  return ` data-next-cockpit-disclosure="${esc(key)}"` +
    (nextCockpitDisclosureStates.get(key) === true ? " open" : "");
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
function nextCockpitWhy(control, summary, body, {pop = false} = {}){
  const text = String(body == null ? "" : body).trim();
  if(!text) return "";
  if(!summary) return `<p class="next-cockpit-reading-why">${esc(text)}</p>`;
  /* `pop` is for a summary that sits in a flex row beside other content, which
     opens as a popover so the row never moves; everything else is an
     accordion ([NUI-19](docs/design-next-ui.md#nui-19-a-caveat-has-three-tiers)). */
  const why = `<p class="next-cockpit-reading-why">${esc(text)}</p>`;
  return `<details class="next-cockpit-why${pop ? " next-disclose--pop" : ""}"` +
    `${nextCockpitDisclosureAttr(control)}><summary>${esc(summary)}</summary>` +
    (pop ? `<div class="next-disclose-body">${why}</div>` : why) + "</details>";
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
/* `weight` is the next-action primitive's modifier: every field control is a
   real button, secondary or quiet and never primary (owner Q5,
   [the editor's boxes and buttons](docs/design-reading-a-session.md#amended-2026-10-01-the-intent-editors-boxes-buttons-and-footer)). */
/* A control whose press is in flight is drawn busy whatever `shown` says, so a
   redraw mid-save neither hides it nor re-arms it (`nextPendingAttrs`). */
function nextCockpitHeldControl(action, label, kind, shown, inert, describedBy, focus = "",
    weight = "secondary"){
  const off = inert ? ' aria-disabled="true"' : " hidden";
  const why = !shown && inert && describedBy ? ` aria-describedby="${describedBy}"` : "";
  const state = nextPendingHas(focus) ? nextPendingAttrs(focus) : `${shown ? "" : off}${why}`;
  return `<button type="button" class="next-action next-action--${weight}"` +
    `${focus ? ` data-next-focus="${esc(focus)}"` : ""} ` +
    `data-next-cockpit-action="${action}" data-arg="${kind}"` +
    `${state}>${nextPendingLabel(focus, label)}</button>`;
}

function nextCockpitHeldToggle(field, action, shown, inert){
  const control = field.querySelector(`[data-next-cockpit-action="${action}"]`);
  // A keystroke never re-arms a control whose press is still being answered.
  if(!control || nextPendingHas(control.dataset && control.dataset.nextFocus)) return;
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
/* The page's own, unlike the server's discard sentences: no answer came, so
   the server has said nothing about these words (owner, 2026-10-02). */
const NEXT_COCKPIT_DISCARD_UNCONFIRMED =
  "Cargento did not answer, so this page cannot tell whether the words were discarded.";
const NEXT_COCKPIT_HELD_CUES = {
  error: "Not saved. The server refused the write, and your words are still in the box.",
  unpersisted: "Not stored. The store could not be written, so the refresh has already " +
    "dropped these words, and they are still in the box.",
  saved: "Saved as a new revision.",
  /* The request was lost, aborted at the bound, or answered with something
     unreadable: not a refusal, so never "Not saved" (owner, 2026-10-02). */
  unconfirmed: "Cargento did not answer, so this page cannot tell whether your intent was " +
    "saved. Your words are still in the box.",
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
  if(kind === "discard-unconfirmed") return NEXT_COCKPIT_DISCARD_UNCONFIRMED;
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

/* `say:false` stamps the mark without announcing it, for a press whose outcome
   is said once its refresh has drawn it (`nextCockpitHeldSay`). */
function nextCockpitHeldMark(key, kind, {say = true} = {}){
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
  if(say) nextCockpitHeldSay(key, kind);
}

function nextCockpitHeldSay(key, kind){
  if(kind !== "discard-armed") nextCockpitRetractArmed(key);
  nextCockpitAnnounceCue(key, nextCockpitHeldSentence(kind), kind === "discard-armed");
}

/* The server's sentence while the annotation store cannot be read, or "".
   While it stands, no box may say nothing was typed: the words may be on disk
   in a file this build could not read (`annotations.store_notice`). */
function nextCockpitStoreUnreadable(){
  return String(nextData && nextData.annotate_unreadable || "");
}

/* The draft's marks under the goal's box: where the words came from, and
   that an excerpt is one. Drawn while the box holds the draft; the input
   handler hides them on the first edit, because a keystroke does not redraw,
   and a box put back to the draft redraws them. Save intent is the one way
   to save the draft: the "Looks right" button that did the same thing beside
   it is gone (owner, 2026-10-02). */
/* An adopted prompt longer than the goal box (owner, 2026-10-04): the box
   keeps the excerpt, and Analyze attempts a source lookup at the press. Only
   a reading that found it may promise whole source words. Short, because it sits in the row
   under the box that holds one control's height. */
const NEXT_INTENT_EXCERPT_READ_WHOLE = "Excerpt. Analyze looks up the source when pressed.";

function nextIntentDraftMarks(session, draft){
  /* A chosen prompt is named by its own time, which is what tells it apart
     from the others the menu listed. */
  const which = draft.source === "latest-prompt" ? " \u00b7 latest"
    : draft.source === NEXT_PROMPT_CHOSEN ? ` \u00b7 ${nextSessionClock(draft.at)}` : "";
  const clipped = draft.cut === true || draft.text.endsWith("\u2026")
    ? ` ${NEXT_INTENT_EXCERPT_READ_WHOLE}` : "";
  return '<span class="next-intent-draft-marks" data-next-cockpit-draft-marks>' +
    `<span class="next-intent-draft-source">from your prompt${which}</span>` +
    (clipped ? `<span class="next-cockpit-held-cue">${clipped.trim()}</span>` : "") + '</span>';
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

/* What the goal box is compared against: the drafted prompt over a goal-less
   session, where the draft stands in the stored words' place, and the stored
   goal otherwise. `save` compares the box against it, so the untouched draft
   adopts the draft rather than typing an excerpt (DRC-4682). */
function nextCockpitGoalBaseline(session, annotation){
  const drafted = nextIntentDraft(session, annotation);
  return drafted ? drafted.text : String(annotation && annotation.goal || "");
}

function nextCockpitHeldField(session, annotation, spec, cap){
  const [kind, label, valueKey, whyKey, placeholder] = spec;
  const key = nextCockpitHeldKey(session, kind);
  const drafted = kind === "goal" ? nextIntentDraft(session, annotation) : null;
  const saved = kind === "goal" ? nextCockpitGoalBaseline(session, annotation)
    : String(annotation && annotation[valueKey] || "");
  const draft = nextCockpitHeldDrafts.has(key) ? nextCockpitHeldDrafts.get(key) : saved;
  const untouched = Boolean(drafted) && draft === drafted.text;
  const why = nextCockpitStoreUnreadable() ? "" : String(annotation && annotation[whyKey] || "");
  const cue = nextCockpitHeldCue(key);
  /* Label, box, counter, as the design draws a field; Clear sits under the
     goal box it empties, and the one save for both fields is the footer's
     (owner Q6, 2026-10-01). The heading row the counts and controls moved into
     for the DRC-4680 fold left the reader unable to tell which box a save
     belonged to. */
  return `<div class="next-cockpit-held-field" data-next-cockpit-held-field="${kind}"` +
    `${untouched ? " data-next-cockpit-drafted" : ""}>` +
    '<div class="next-cockpit-held-heading">' +
    `<span class="next-cockpit-held-label">${esc(label)}</span>` +
    (kind === "goal" ? nextIntentPromptSelect(session) : "") +
    '</div>' +
    `<textarea rows="3" maxlength="${cap}" data-next-cockpit-held-kind="${kind}" ` +
    `data-next-cockpit-held-key="${esc(key)}" data-next-cockpit-held-saved="${esc(saved)}" ` +
    (drafted ? `data-next-cockpit-draft="${esc(drafted.text)}" ` : "") +
    `data-next-focus="${esc(key)}" placeholder="${esc(placeholder)}">${esc(draft)}</textarea>` +
    '<div class="next-cockpit-held-under">' +
    `<span class="next-cockpit-held-count" data-next-cockpit-held-count="${kind}">` +
    `${draft.length}/${cap}</span>` +
    /* Where the words came from sits between the count and Clear, as an
       outcome line's source sits between its count and Remove. In the label
       row it was a line of its own: drawn between the label and the select it
       wrapped the select 48px down, and drawn under the select it moved the
       box the pick fills 25px down, and back up on the first keystroke
       (measured at 1440x900, 2026-10-02, verifier F1). */
    (untouched ? nextIntentDraftMarks(session, drafted) : "") +
    (kind === "goal" && !untouched ? nextPromptSourceLine(annotation) : "") +
    nextCockpitHeldControl("held-clear", "Clear", kind, Boolean(draft), false, "", `${key}:clear`) +
    '</div>' +
    /* The absence sentence answers "why is this empty", so it goes when the
       box stops being empty. It read the SERVER value alone, which put "No
       goal typed for this session." directly under the sentence the reader
       was in the middle of typing. */
    /* Rendered and hidden rather than rendered conditionally, for the reason
       the input handler gives: a keystroke does not redraw, so a paragraph
       that only the renderer can remove stays under the sentence being
       typed. Visually hidden even while it applies (owner Q11): the empty box
       and its placeholder are the absence a sighted reader sees, and the
       sentence stays the inert save's description. */
    (why ? `<p class="next-cockpit-held-absent next-visually-hidden" ` +
      `id="${nextCockpitHeldAbsentId(kind)}" data-next-cockpit-held-absent="${kind}"` +
      `${draft ? " hidden" : ""}>${esc(why)}</p>` : "") +
    nextDirectionLinesQuestion(session) +
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
    /* The box, then one row under it as the Goal has: the count on the left
       and Remove on the right (owner, 2026-10-02, ask 3). The source is a fact
       about saved words, so it shows only while the box still holds the line
       saved in that place, and only for a line added from an entry: "typed"
       told a reader what they already knew. Its space is kept while it is
       hidden, so Remove does not jump under the caret (DRC-4714). */
    const place = saved[index] || null;
    const line = place && place.text === text ? place : null;
    return `<li class="next-cockpit-held-line" data-next-cockpit-held-line="${index}">` +
      `<textarea rows="2" maxlength="${cap}" data-next-cockpit-held-line-index="${index}" ` +
      `data-next-cockpit-held-lines-key="${esc(key)}" ` +
      `data-next-cockpit-held-saved="${esc(place ? place.text : "")}" ` +
      `data-next-focus="${esc(`${key}:${index}`)}" ` +
      'placeholder="one thing that should exist when it is done">' +
      `${esc(text)}</textarea><div class="next-cockpit-held-under">` +
      `<span class="next-cockpit-held-count" data-next-cockpit-held-line-count="${index}">` +
      `${String(text).length}/${cap}</span>` +
      (place && place.source === "entry"
        ? `<span class="next-cockpit-held-source" data-next-cockpit-held-line-source="${index}"` +
          `${line ? "" : " data-next-cockpit-held-line-source-stale"}>` +
          `${esc(nextCockpitLineSource(place, session, source))}</span>` : "") +
      '<button type="button" class="next-action next-action--secondary next-cockpit-held-remove" ' +
      `data-next-cockpit-action="held-line-remove" data-arg="${index}" ` +
      `aria-label="Remove line ${index + 1}" ` +
      `data-next-focus="${esc(`${key}:remove:${index}`)}">Remove</button></div></li>`;
  }).join("") + direction;
  const add = '<button type="button" class="next-action next-action--secondary" ' +
    'data-next-cockpit-action="held-line-add" data-arg="lines"' +
    ` data-next-focus="${esc(`${key}:add`)}"` +
    (full ? ' aria-disabled="true" aria-describedby="next-cockpit-held-full"' : "") +
    ">+ Add a line</button>";
  /* Add follows the list it extends, and the save is the footer's, shared
     with the goal (owner Q6). */
  return '<div class="next-cockpit-held-field next-cockpit-held-lines" ' +
    'data-next-cockpit-held-field="lines">' +
    '<div class="next-cockpit-held-heading">' +
    '<span class="next-cockpit-held-label">Expected outcome</span></div>' +
    `<ol class="next-cockpit-held-list">${rows}</ol>` +
    `<div class="next-cockpit-held-under">${add}</div>` +
    '<p class="next-cockpit-held-full" id="next-cockpit-held-full" data-next-cockpit-held-full' +
    `${full && !said ? "" : " hidden"}>${esc(NEXT_COCKPIT_LINES_FULL)}</p>` +
    (why ? '<p class="next-cockpit-held-absent next-visually-hidden" ' +
      `id="${nextCockpitHeldAbsentId("lines")}" data-next-cockpit-held-absent="lines"` +
      `${nextCockpitLinesToSend(draft).length ? " hidden" : ""}>${esc(why)}</p>` : "") +
    (cue ? `<small class="next-cockpit-held-cue">${esc(cue)}</small>` : "") + '</div>';
}

/* The one save for both fields, and what it would write (owner Q6,
   2026-10-01). The goal counts as changed where its box has left the stored
   words and is not back at the draft, which Save intent adopts; the lines
   where the list to send differs from the stored list. `undoable` is wider:
   a box emptied over a draft writes nothing, and is still the reader's edit
   to put back. Keyed per session as every held mark is. */
function nextCockpitIntentKey(session){
  return nextCockpitHeldKey(session, "intent");
}

function nextCockpitIntentChanges(session, annotation){
  const goalKey = nextCockpitHeldKey(session, "goal");
  const baseline = nextCockpitGoalBaseline(session, annotation);
  const stored = String(annotation && annotation.goal || "");
  const typed = nextCockpitHeldDrafts.has(goalKey) ? nextCockpitHeldDrafts.get(goalKey) : baseline;
  const goal = typed !== baseline && typed !== stored;
  const lines = nextCockpitLinesChanged(nextCockpitLinesDraft(session, annotation), annotation);
  /* A prompt chosen from the menu is a change the box shows and the store
     does not hold, so Save intent adopts it, over saved words or an empty
     goal alike. A refusal that sends the reader to Save intent therefore
     never finds it inert (DRC-4758 fix round, INT-5). */
  const chosen = typed === baseline && nextIntentChosenOverSaved(session, annotation);
  const pending = typed === baseline && nextIntentChosenPrompts.has(goalKey) &&
    Boolean(nextPromptCandidate(session, NEXT_PROMPT_CHOSEN));
  /* An untouched draft is not an edit, so Undo has nothing to undo, but Save
     intent adopts it: the one way to save it (owner, 2026-10-02). */
  const adoptable = typed === baseline && Boolean(nextIntentDraft(session, annotation));
  return {goal, lines, typed, chosen, pending, adoptable, any: goal || lines || pending,
    undoable: typed !== baseline || lines || pending};
}

const NEXT_INTENT_MEASURED = "Drift is measured against these. Edit anything that is off.";

/* Under both fields, as the design's single hint line is: the hint on the
   left, Undo changes and Save intent on the right, both inert while nothing
   has changed
   ([NUI-18](docs/design-next-ui.md#nui-18-one-control-primitive-and-an-inert-control-stays-on-the-page)).
   An inert save is described by whichever absence sentences stand, which is
   why those stay in the DOM visually hidden (owner Q11). */
function nextCockpitIntentFooter(session, annotation){
  const key = nextCockpitIntentKey(session);
  const changes = nextCockpitIntentChanges(session, annotation);
  const absent = nextCockpitStoreUnreadable() ? [] : [["goal", "goal_why"], ["lines", "lines_why"]]
    .filter(([_kind, why]) => annotation && annotation[why])
    .map(([kind]) => nextCockpitHeldAbsentId(kind));
  /* Not while the save is still busy: the outcome is drawn and said together,
     when the button settles, and a redraw in between (a context paint) drew
     "Saved" beside "Saving…" (owner, 2026-10-02). */
  const saving = nextPendingHas(`${key}:save`);
  const cue = saving ? "" : nextCockpitHeldCue(key);
  /* Undo is inert while its save is in flight: reverting the box would leave
     the words being sent unseen (orchestrator, measured in Chrome, ui4). */
  return '<div class="next-cockpit-held-footer">' +
    `<p class="next-cockpit-held-hint" data-next-intent-measured>${NEXT_INTENT_MEASURED}</p>` +
    '<span class="next-cockpit-held-tools">' +
    nextCockpitHeldControl("held-undo", "Undo changes", "intent", changes.undoable && !saving, true,
      "", `${key}:undo`) +
    nextCockpitHeldControl("held-save", "Save intent", "intent", (changes.any || changes.adoptable) && !nextDirectionLinesQuestion(session), true,
      absent.join(" "), `${key}:save`, "secondary") +
    '</span>' +
    (cue ? `<small class="next-cockpit-held-cue">${esc(cue)}</small>` : "") + '</div>';
}

/* The footer's two controls, updated in place on a keystroke for the input
   handlers' reason: a redraw there loses the caret. */
function nextCockpitIntentFooterToggle(session){
  const app = document.getElementById("app");
  if(!session || !app || typeof app.querySelector !== "function") return;
  const footer = app.querySelector(".next-cockpit-held-footer");
  if(!footer || typeof footer.querySelector !== "function") return;
  const changes = nextCockpitIntentChanges(session, nextCockpitAnnotation(session));
  /* The save's description is the fields' absence sentences, which live in
     the fields rather than the footer, so they are found from the section. */
  const section = typeof footer.closest === "function" ? footer.closest(".next-cockpit-held") : null;
  const describes = section && typeof section.querySelectorAll === "function"
    ? [...section.querySelectorAll("[data-next-cockpit-held-absent]")].map(node => node.id)
      .filter(Boolean).join(" ") : "";
  const key = nextCockpitIntentKey(session);
  const saving = nextPendingHas(`${key}:save`);
  for(const [action, live, why, focus] of [
    ["held-save", (changes.any || changes.adoptable) && !nextDirectionLinesQuestion(session), describes, `${key}:save`],
    ["held-undo", changes.undoable && !saving, "", `${key}:undo`]]){
    const control = footer.querySelector(`[data-next-cockpit-action="${action}"]`);
    /* A keystroke during a save never re-arms Save intent: the press is still
       being answered, and a second one would race it. */
    if(!control || nextPendingHas(focus)) continue;
    if(live){
      control.removeAttribute("aria-disabled");
      control.removeAttribute("aria-describedby");
      continue;
    }
    control.setAttribute("aria-disabled", "true");
    if(why) control.setAttribute("aria-describedby", why);
  }
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
  /* `add_direction` adopts only the first or latest prompt, so over a chosen
     one the save would be refused; the reader saves the choice first. */
  const draft = session ? nextIntentDraft(session, annotation) : null;
  if(draft && draft.source === NEXT_PROMPT_CHOSEN) return NEXT_INTENT_EDITED_ADD;
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
    /* The saved lines' pattern: the box, then the count and where it came
       from on the left, and Save and Remove on the right (owner, 2026-10-02). */
    '<div class="next-cockpit-held-under">' +
    `<span class="next-cockpit-held-count" data-next-cockpit-direction-count>${text.length}/${cap}</span>` +
    `<span class="next-cockpit-held-source">${esc(from)}</span>` +
    '<span class="next-cockpit-direction-tools">' +
    '<button type="button" data-next-cockpit-action="direction-save" data-next-reserve ' +
    `data-next-focus="direction-save:${esc(key)}"` +
    `${nextPendingHas(`direction-save:${key}`) ? nextPendingAttrs(`direction-save:${key}`)
      : ready ? "" : ' aria-disabled="true"'}` +
    `${why ? ' aria-describedby="next-cockpit-direction-why"' : ""}>` +
    `${nextPendingLabel(`direction-save:${key}`, "Save", "Saving\u2026")}</button>` +
    '<button type="button" data-next-cockpit-action="direction-cancel" ' +
    `data-next-focus="direction-cancel:${esc(key)}">Remove</button></span></div>` + choose +
    '<p class="next-cockpit-held-full" id="next-cockpit-direction-why" data-next-cockpit-direction-why' +
    `${why ? "" : " hidden"}>${esc(why)}</p>` +
    '<p class="next-cockpit-held-hint">Write the rule, not the moment.</p>' +
    (why || held.clipped ? nextDirectionGoalButton(session, held.factId, "line") : "") +
    (held.clipped ? `<p class="next-cockpit-held-full">${esc(NEXT_COCKPIT_DIRECTION_CLIPPED)}</p>` : "") +
    (cue ? `<small class="next-cockpit-held-cue">${esc(cue)}</small>` : "") + "</li>";
}

async function nextCockpitOpenDirection(session, factId, n, later = false, action = "direction-add"){
  const key = sessKey(session);
  /* A second press while a line is pending goes to that line: reopening it
     would put the server's text back over the reader's edits (layout F2). */
  const open = nextCockpitDirectionLines.get(key);
  if(open && (open.opening || typeof open.text === "string")){
    if(!open.opening) renderNext({named: `direction:${key}`});
    return;
  }
  const control = `${action}:${key}`;
  const press = nextPendingStart(control, "Opening\u2026");
  if(!press) return;
  nextCockpitDirectionLines.set(key, {factId, n, later, opening: true});
  renderNext({named: control});
  let held;
  try{
    const response = await nextFetchBounded("/api/direction", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({harness: session.harness, sid: session.sid, fact_id: factId})},
      press.signal);
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
  }finally{
    nextPendingEnd(control, press);
  }
  nextCockpitDirectionLines.set(key, held);
  renderNext(held.error ? {named: control} : {named: `direction:${key}`});
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
  const control = `direction-save:${key}`;
  const press = nextPendingStart(control, "Saving\u2026", "Saving the line.");
  if(!press) return;
  held.pending = true;
  held.cue = "";
  renderNext({named: control});
  try{
    let response;
    let saved;
    try{
      response = await nextFetchBounded("/api/annotate", {method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({harness: session.harness, sid: session.sid,
          add_direction: held.factId, text: held.text,
          expected_revision: nextNumber(annotation && annotation.revision) || 0,
          ...(held.replace != null ? {replace: held.replace} : {}),
          ...nextIntentAdoption(draft)})}, press.signal);
      saved = response && response.ok ? await response.json() : null;
    }catch(_error){
      // No answer is not a refusal: the page cannot tell whether it landed.
      held.cue = "unconfirmed";
      await refreshNext();
      return;
    }
    if(!response || !response.ok) throw new Error(`HTTP ${response && response.status}`);
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
    nextPendingEnd(control, press);
    renderNext({named: control});
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

function nextCockpitWorkEvidenceOwn(harness, sent = true){
  const label = nextHarnessLabels().get(harness) || nextCockpitHumanLabel(harness);
  if(harness === "pi") return `${label} publishes demonstrated work results, and they are read here.`;
  if(harness === "claude"){
    /* The route's own sentence says what a reading sends of them and to whom,
       or that it sends none, so the line under the checks and the disclosure
       beside the button cannot word it two ways. */
    const route = sent ? nextReadingRoute({harness}) : null;
    const output = route && route.provider ? String(route.tool_output || "") : "";
    return `${label} records the checks a session ran and the files it wrote, and they are ` +
      "listed here. A result is what the tool reported; Cargento inspects no file, test or " +
      "deliverable." + (output ? ` ${output}` : "");
  }
  /* "Cargento reads those on Pi alone" stood here, and stopped being true
     when Claude Code's checks were read too. The panel's own harness limit is
     `nextDriftLevel`'s, so this line says only what the record above is. */
  return `${label} publishes no demonstrated work results, so nothing above is an ` +
    "inspected file, test or deliverable.";
}

/* The reading's Expected Output limit, apart from the record's own line. On
   Claude Code it is lifted wherever a reading can be made: the agent's own
   messages go with the words and carry a line's verdict whether or not a check
   can be sent
   ([DEC-17](docs/design-reading-a-session.md#amended-2026-10-03-owner-the-agents-own-words-are-evidence)).
   With no reading model at all, the demotion stays. */
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
  if(route && route.provider) return "";
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
/* The agent's messages, bounded apart: half the other rows' bound, a
   readability choice like that one, and stated under the rows the same way. */
const NEXT_COCKPIT_AGENT_ROWS = 10;

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
  const found = nextSessionStop(session);
  const stop = found ? found.at : null;
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

/* A fact's type as a word on the activity list. Closed, and a Map so a type
   named like an Object property cannot resolve to one: a type with no word
   here reads "Entry" rather than its raw token. */
const NEXT_COCKPIT_ENTRY_KIND = new Map([
  ["prepared_dispatch", "Dispatch"], ["work_birth", "Task started"], ["work_result", "Task result"],
  ["result", "Result"], ["gate_decision", "Gate"], ["decision", "Decision"],
  ["assignment", "Assignment"], ["stage_transition", "Stage"], ["agent_message", "Agent said"],
]);

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
  /* The agent's messages take a bound of their own beside the other rows', so
     a talkative session never pushes the reader's messages off the list. */
  const agentSaid = entry => entry.type === "agent_message";
  const recent = new Set(numbered.filter(entry => entry.type !== "tool_report" && !agentSaid(entry))
    .slice(-NEXT_COCKPIT_WORK_ROWS));
  const recentSaid = new Set(numbered.filter(agentSaid).slice(-NEXT_COCKPIT_AGENT_ROWS));
  const isCited = entry => cited.has(String(entry && entry.id || ""));
  const isRecent = entry => recent.has(entry) || recentSaid.has(entry);
  const entries = all.filter(entry => isCited(entry) || open.has(entry) ||
    (numbers.has(entry) && (entry.type === "tool_report" || isRecent(entry))));
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
       and a word for the fact's type from a closed map otherwise, never the
       raw `prepared_dispatch` a reader cannot read (NU-3, 2026-10-02), and
       never a count nothing measured. */
    const head = entry.type === "tool_report"
      ? `<span class="next-cockpit-work-result">${esc(nextCockpitToolReportLine(entry))}</span>`
      : `<span class="next-cockpit-work-actor">${esc(nextCockpitEntryActor(entry))}</span>` +
        `<span class="next-cockpit-work-type">${esc(nextReadingCopied(entry)
          ? "Copied from Cargento" : entry.type === "user_message" ? "Prompt"
          : NEXT_COCKPIT_ENTRY_KIND.get(String(entry.type || "")) || "Entry")}</span>`;
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
      /* Out of view and still read out: the same source on every row was a
         full-width caption five times over (plan slice E, the per-row source;
         DRC-4758 fix round). */
      `<span class="next-cockpit-work-source next-visually-hidden">${esc(entry.source || "Source not published")}` +
      /* Only where it says something the source line does not. On most fact
         types `actor_claim` IS the evidence source, and appending it printed
         "timestamped non-meta user-role record · exact · timestamped non-meta
         user-role record". Caught by walking the board, not by the suite. */
      `${entry.actorClaim && !entry.source.includes(entry.actorClaim)
        ? ` · ${esc(entry.actorClaim)}` : ""}</span>` +
      `<span class="next-cockpit-work-at">${esc(at == null ? "time not published" : `${at} ago`)}` +
      `</span>${turn}` +
      (later.has(entry) ? '<button type="button" data-next-cockpit-action="direction-add" ' +
        `data-arg="${esc(entry.id)}">Add to my intent</button>` : "") + '</div></div>';
  }).join("");
  /* Where the words' window opens, a message of the reader's should sit: the
     latest one at or before the save for typed words, the prompt itself for
     adopted ones. A window at the save time is typed words with no earlier
     message, and nothing is expected there. */
  const promptSource = annotation && NEXT_PROMPT_SOURCES.includes(annotation.goal_source);
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
        ...(recentSaid.size ? [`the ${recentSaid.size} most recent messages the agent wrote`] : []),
        /* In the window: a check or file from before it is counted with the
           earlier entries, so "every" is true only of this set (review F3). */
        ...(listed.some(entry => entry.type === "tool_report")
          ? ["every check and file in the window"] : []),
        ...(listed.some(entry => isCited(entry) && entry.type !== "tool_report" &&
          !isRecent(entry)) ? ["every entry the analysis cites"] : []),
        ...(listed.some(entry => open.has(entry) && !isCited(entry) && !isRecent(entry))
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
    nextCockpitWorkFooter(session, (numbered.length
      ? `<p class="next-cockpit-work-mix">${esc(nextCockpitWorkMix(numbered))}</p>` : "") +
      unlisted.map(said => `<p class="next-cockpit-work-earlier">${esc(said)}</p>`).join("") +
      (source.scan ? `<p class="next-cockpit-work-checks">${esc(nextCockpitCheckScan(source.scan))}` +
        "</p>" : "") + bound) + '</section>';
}

/* The record's footer, tiered (DRC-4758 slice E, tier 2 of
   [NUI-19](docs/design-next-ui.md#nui-19-a-caveat-has-three-tiers)). Where the
   harness's work results are read, one clause stays in view and the mix, the
   bounds, the scan and the full limit sit behind "About this record"; where
   none are read, the limit is the absence and stays in view. The route's
   tool-output sentence is not repeated here: "What is sent" beside the
   control owns it, and it said the same words twice on one page. */
const NEXT_COCKPIT_WORK_AS_REPORTED = "Results are as the tool reported; not inspected.";

function nextCockpitWorkFooter(session, about){
  const harness = String(session && session.harness || "");
  const reads = harness === "claude" || harness === "pi";
  const limit = reads
    ? `${NEXT_COCKPIT_WORK_READ_FROM} ${nextCockpitWorkEvidenceOwn(harness, false)}`
    : nextCockpitWorkEvidenceLimit(harness);
  const line = reads
    ? `<p class="next-cockpit-work-limit next-cockpit-work-reported">${esc(NEXT_COCKPIT_WORK_AS_REPORTED)}</p>`
    : `<p class="next-cockpit-work-limit">${esc(limit)}</p>`;
  const body = about + (reads ? `<p class="next-cockpit-work-limit">${esc(limit)}</p>` : "");
  return line + (body ? `<details class="next-cockpit-why next-cockpit-work-about"` +
    `${nextCockpitDisclosureAttr("work-about")}><summary>About this record</summary>` +
    `${body}</details>` : "");
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
  let said = 0;
  let work = 0;
  for(const entry of entries){
    if(nextReadingPersonAuthored(entry)) directions += 1;
    else if(nextReadingCopied(entry)) copied += 1;
    else if(entry.modelDerived) derived += 1;
    else if(String(entry.type || "") === "observer_snapshot") summaries += 1;
    /* What the agent said is its account, not an observation of what it did. */
    else if(String(entry.type || "") === "agent_message") said += 1;
    else work += 1;
  }
  const parts = [`${entries.length} ${entries.length === 1 ? "entry" : "entries"}`];
  if(directions) parts.push(`${directions} ${directions === 1 ? "direction" : "directions"} you gave`);
  if(said) parts.push(`${said} ${said === 1 ? "message" : "messages"} the agent wrote`);
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
/* `reading.RESULT_UNSUPPORTED`: the claims question's own fourth result, a
   claim of the agent's nothing in the record read shows. Never a departure
   (rule 3), and only ever on the `claims` row (owner, 2026-10-04). */
const NEXT_READING_UNSUPPORTED = "not shown by the record";
// Rule 1, as data. A result reaches the page only by being one of these.
const NEXT_READING_RESULTS = [
  NEXT_READING_DEPARTURE, NEXT_READING_CONSISTENT, NEXT_READING_UNVERIFIABLE,
  NEXT_READING_UNSUPPORTED,
];
/* `reading.CONSTRAINT_CLAIMS`: what the agent claimed about the work, asked
   beside the intent on a press that carries its messages, and drawn after it. */
const NEXT_READING_CLAIMS = "claims";
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
  return key === "goal" || key === NEXT_READING_CLAIMS || nextReadingIsOutcomeLine(key);
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
    : key === NEXT_READING_CLAIMS ? NEXT_OUTCOME_LINES_MAX + 1
    : Number(NEXT_READING_OUTCOME_LINE.exec(key)[1]);
  return [...keys].sort((left, right) => order(left) - order(right))
    .filter(key => (rows && rows[key]) || String(annotation && annotation[key] || "").trim())
    .map(key => [key, key === "goal" ? "TYPED GOAL" : key === "output" ? "EXPECTED OUTCOME"
      : key === NEXT_READING_CLAIMS ? "WHAT THE AGENT CLAIMED"
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
  "scope", "scope_text", "ended_at_read", "evidence_through", "coverage", "criteria"];
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
// While the row is running, the box says the job reads only the work so far.
const NEXT_READING_JOB_NOTE_SO_FAR = "Reads only the work so far. The result will appear here.";
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
/* Said of the words as well as tool output: an Allow is bound to both
   destinations (owner, 2026-10-02), and either moving refuses it. */
const NEXT_READING_DESTINATION_CHANGED =
  "Where this session would be sent changed since this page was drawn, so nothing was " +
  "sent; read where it goes now and press again.";
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
   not re-read. Narrowed on 2026-10-03 to a line resting on no message of the
   agent's, and worded so a row stored before that is still told the truth. */
const NEXT_READING_TELLS_THE_PERSON =
  "This line is about what the agent told you, and the analysis rested it on no message " +
  "the agent wrote, so it reads as not verifiable.";
/* An outcome line's consistent resting on no work beside a failed check the
   record holds (`failed-check-on-record`), read or not. */
const NEXT_READING_FAILED_CHECK_ON_RECORD =
  "A check this session ran failed after the words you saved, and this rests on no check " +
  "that passed, so it reads as not verifiable.";
const NEXT_READING_FAILED_CHECK_UNREAD =
  "A check that failed was not read, because the reading had no room for it, so nothing here " +
  "says the output is consistent.";
/* The claims row (owner, 2026-10-04): why a verdict on it was withdrawn for
   want of the citations it needs (`claim-uncited`), and why "not shown" was
   withdrawn where the session's checks were not all read
   (`claim-record-unread`, review, PR C). */
const NEXT_READING_CLAIM_RECORD_UNREAD =
  "Not all of this session's checks were read, so the analysis cannot say the record does " +
  "not show what the agent said.";
const NEXT_READING_CLAIM_UNCITED =
  "The analysis did not cite the agent's message and, for a contradiction or a match, the " +
  "entry it compared it with, so it reads as not verifiable.";
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
  "failed-check-on-record": NEXT_READING_FAILED_CHECK_ON_RECORD,
  "claim-uncited": NEXT_READING_CLAIM_UNCITED,
  "claim-record-unread": NEXT_READING_CLAIM_RECORD_UNREAD,
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

/* One of the agent's own messages (`reading.AGENT_MESSAGE_TYPE`): the only
   agent-authored entry, besides work, that may carry an outcome line. */
function nextReadingAgentMessage(entry){
  return String(entry && entry.type || "") === "agent_message";
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
  if(annotation && NEXT_PROMPT_SOURCES.includes(annotation.goal_source)){
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
  const claims = key === NEXT_READING_CLAIMS;
  /* `unsupported` is the claims row's alone; anywhere else it is a result
     outside the row's set, as the store would refuse it. */
  const known = claims ? NEXT_READING_RESULTS
    : NEXT_READING_RESULTS.filter(name => name !== NEXT_READING_UNSUPPORTED);
  let result = known.includes(declared) ? declared : NEXT_READING_UNVERIFIABLE;
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
  /* The claims row is independent of the intent, so an unsettled later
     direction never demotes it (review, PR C). */
  if(result !== NEXT_READING_UNVERIFIABLE && unsettled && !claims){
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
  let failedCited = false;
  if(result !== NEXT_READING_UNVERIFIABLE){
    failedCited = citations.some(entry => entry.subject === "check" &&
      nextReadingCheckSupports(entry, NEXT_READING_DEPARTURE, windowStart));
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
  /* The claims row, as `reading._claims_rule` reads it: every result names
     the agent's message making the claim; a departure or a consistent also
     the entry contradicting or showing it, and that entry not only
     Cargento's paraphrase. An `unsupported` is about absence, so the message
     is all it can cite. */
  const claimSaid = claims ? citations.filter(nextReadingAgentMessage) : [];
  const claimRecord = claims ? citations.filter(entry => !nextReadingAgentMessage(entry)) : [];
  if(claims && result !== NEXT_READING_UNVERIFIABLE){
    let token = "";
    if(!claimSaid.length) token = NEXT_READING_CLAIM_UNCITED;
    else if(result !== NEXT_READING_UNSUPPORTED && !claimRecord.length){
      token = droppedCheck ? NEXT_READING_CHECK_DOES_NOT_SHOW_IT : NEXT_READING_CLAIM_UNCITED;
    }else if(result !== NEXT_READING_UNSUPPORTED &&
        claimRecord.every(entry => nextReadingAuthor(entry) === "derived")){
      token = NEXT_READING_DERIVED_ONLY;
    }else if(result === NEXT_READING_CONSISTENT && !claimRecord.some(entry =>
        nextReadingDemonstratesWork(entry) || String(entry.type || "") === "tool_report")){
      /* `reading._claims_compared`: shown means shown by the work. */
      token = NEXT_READING_CLAIM_UNCITED;
    }else if(result === NEXT_READING_DEPARTURE && !claimRecord.some(entry =>
        entry.subject === "check" ||
        (nextNumber(entry.at) || 0) >= Math.min(...claimSaid.map(said => nextNumber(said.at) || 0)))){
      /* A contradiction at or after the claim; a check is its latest run. */
      token = NEXT_READING_CLAIM_UNCITED;
    }
    if(token){
      result = NEXT_READING_UNVERIFIABLE;
      why = token;
    }
  }
  const shows = citations.filter(nextReadingDemonstratesWork);
  const authors = citations.map(nextReadingAuthor);
  const derivedOnly = authors.length > 0 && authors.every(name => name === "derived");
  const agentSaid = citations.some(nextReadingAgentMessage);
  if(nextReadingIsOutcomeLine(key) && result !== NEXT_READING_UNVERIFIABLE && !shows.length &&
      !agentSaid){
    /* Rule 7, the Expected Output half, as amended twice. A verdict about the
       deliverable needs an entry that DEMONSTRATES work, or one of the agent's
       own messages, which are evidence of what it said (owner, 2026-10-03,
       `reading._rests_on_nothing`). Only the message type: a dispatch or a
       decision is not what it said. The reader's own request is neither. */
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
  if(result === NEXT_READING_CONSISTENT && failedCited && !shows.length){
    /* A consistent that cited a check failing in the window never stands on
       the agent's account left beside it: that is the record contradicting the
       claim (`reading._evidence_rules`). */
    result = NEXT_READING_UNVERIFIABLE;
    why = NEXT_READING_CHECK_DOES_NOT_SHOW_IT;
  }
  if(result === NEXT_READING_CONSISTENT && (nextReadingIsOutcomeLine(key) || claims) &&
      !shows.length &&
      (entries || []).some(entry => entry && entry.subject === "check" &&
        nextReadingCheckSupports(entry, NEXT_READING_DEPARTURE, windowStart))){
    /* A line's consistent resting on no work beside a failed check this page
       holds, cited or not and sent or not (`failed-check-on-record`). The
       producer said `failed-check-unread` where the prompt had no room for it,
       and the stored reason keeps that sentence. */
    result = NEXT_READING_UNVERIFIABLE;
    why = stored === "failed-check-unread" ? NEXT_READING_FAILED_CHECK_UNREAD
      : NEXT_READING_FAILED_CHECK_ON_RECORD;
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
     said, and where every agent-authored entry it rests on is one of the
     agent's messages, what the agent said (review, 2026-10-03). The number is
     the list's, filled in where the row is drawn. */
  const tool = result === NEXT_READING_CONSISTENT
    ? citations.find(entry => String(entry.type || "") === "tool_report" ||
      entry.subject === "check") : null;
  const accounts = result === NEXT_READING_CONSISTENT && !tool
    ? citations.filter(entry => nextReadingAuthor(entry) === "agent") : [];
  const said = accounts.find(nextReadingAgentMessage) || accounts[0] || null;
  const restsOn = tool ? "tool"
    : said && accounts.every(nextReadingAgentMessage) ? "message"
    : said ? "agent" : "";
  const restsOnEntry = tool || said || null;
  return {
    key, label,
    /* The claims question carries no words of the reader's, and its heading
       names it, so it has no clause to draw. */
    clause: claims ? "" : clause || NEXT_READING_CLAUSE_UNRETAINED,
    clauseKnown: !claims && Boolean(clause),
    /* The claim and what the record says of it, where the claims row stands. */
    claimEntry: claims && result !== NEXT_READING_UNVERIFIABLE ? claimSaid[0] || null : null,
    recordEntry: claims && result !== NEXT_READING_UNVERIFIABLE
      ? claimRecord.find(entry => String(entry.type || "") === "tool_report" ||
        entry.subject === "check") || claimRecord[0] || null : null,
    result,
    /* Whether the stored row itself declared a verdict, before any limit: a claims row with no
       claim is not drawn under a route limit either. */
    declared: Boolean(declared) && declared !== NEXT_READING_UNVERIFIABLE,
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
const NEXT_READING_COVERAGE_KEYS = ["tail_truncated", "tail_start", "unlisted", "unread_checks", "goal_source"];
const NEXT_READING_COVERAGE_GOALS = ["typed", "whole", "excerpt", "unroomed", "unknown"];

function nextReadingCoverage(raw){
  if(!raw || typeof raw !== "object" || Array.isArray(raw) ||
      Object.keys(raw).length !== NEXT_READING_COVERAGE_KEYS.length ||
      NEXT_READING_COVERAGE_KEYS.some(key => !Object.prototype.hasOwnProperty.call(raw,key))) return null;
  if(raw.tail_truncated !== null && typeof raw.tail_truncated !== "boolean") return null;
  if(raw.tail_start !== null && (typeof raw.tail_start !== "number" ||
      !Number.isFinite(raw.tail_start) || raw.tail_start <= 0 || raw.tail_start > 253402300799)) return null;
  if([raw.unlisted,raw.unread_checks].some(n => !Number.isSafeInteger(n) || n < 0)) return null;
  return NEXT_READING_COVERAGE_GOALS.includes(raw.goal_source) ? raw : null;
}

function nextReadingWindowPartial(shape){
  return Boolean(shape.coverage && shape.coverage.tail_truncated === true &&
    shape.coverage.tail_start != null && shape.windowStart != null &&
    shape.windowStart > 0 && shape.coverage.tail_start > shape.windowStart);
}

function nextCockpitReadingCoverage(shape){
  const measured = shape.coverage;
  const clauses = [];
  if(!measured || measured.tail_truncated == null){
    clauses.push("Coverage was not recorded for this reading.");
  }else if(nextReadingWindowPartial(shape)){
    clauses.push(`Message tail starts ${nextSessionClock(measured.tail_start)}; about ` +
      `${Math.max(1,Math.ceil((measured.tail_start-shape.windowStart)/60))} min at the start of the window were outside it. ` +
      "The check listing can include older work.");
  }else if(measured.tail_truncated && measured.tail_start == null){
    clauses.push("The message tail was truncated; its start time was not recorded.");
  }
  if(measured && measured.unlisted) clauses.push(`${measured.unlisted} ` +
    `${measured.unlisted === 1 ? "pass or write in the window was" : "passes or writes in the window were"} not listed.`);
  if(measured && measured.unread_checks) clauses.push(`${measured.unread_checks} ` +
    `${measured.unread_checks === 1 ? "check" : "checks"} had no room in the reading.`);
  if(measured && ["excerpt","unroomed"].includes(measured.goal_source)){
    clauses.push("The adopted source could not be read whole; this reading used the saved excerpt. " +
      "Put the instruction you meant in the goal box, then analyze again.");
  }else if(measured && measured.goal_source === "whole"){
    clauses.push("The adopted source was found; Analyze read up to 1,000 characters.");
  }
  return clauses.length ? `<p class="next-cockpit-reading-why" data-next-reading-coverage>${esc(clauses.join(" "))}</p>` : "";
}

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
  const coverage = nextReadingCoverage(source.coverage);
  if(source.coverage != null && !coverage) unknown.push("coverage");
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
    : nextNumber(NEXT_PROMPT_SOURCES.includes(source.goal_source)
      ? source.goal_source_at : source.revision_read_at);
  const readAt = nextNumber(source.read_at);
  if(readAt != null && readAt > 0 && unsettled){
    unsettled = nextCockpitConflictCandidates(annotation, entries).some(entry =>
      (nextNumber(entry.at) || 0) <= readAt);
  }
  const constraints = nextReadingConstraints(rows, annotation,
    revisionRead != null && current != null && !historical);
  const partial = nextReadingWindowPartial({coverage,windowStart});
  const criteria = constraints
    .map(([key, label]) => nextCockpitReadingCriterion(
      key, key === "goal" && NEXT_PROMPT_SOURCES.includes(source.goal_source)
        ? "GOAL FROM YOUR PROMPT"
        : nextCockpitLineLabel(key, label, rows[key], annotation, historical, lineSource),
      nextCockpitReadingClause(key, rows[key], annotation, historical),
      rows[key], entries,
      nextReadingIsOutcomeLine(key) || key === NEXT_READING_CLAIMS ? limit : "", unsettled,
      windowStart))
    .map(row => ({...row,coverage: partial && row.key !== NEXT_READING_CLAIMS
      ? "may be in the part not read" : ""}));
  return {
    criteria,
    /* The intent's departures: a contradicted claim is not one, so it is in no
       count, flag or answer about the intent (review, PR C). */
    departures: criteria.filter(row => row.result === NEXT_READING_DEPARTURE &&
      row.key !== NEXT_READING_CLAIMS),
    revisionRead,
    revisionReadAt: nextNumber(source.revision_read_at),
    windowStart,
    coverage,
    promptSource: NEXT_PROMPT_SOURCES.includes(source.goal_source),
    /* Through the same helper the criterion row uses, and filtered the same
       way. Read raw, the disclosure said "nothing typed in that revision" for
       an empty clause while the row beside it said the words were not
       retained: `_criterion` coerces a missing clause to "", so after a store
       round trip the two are indistinguishable and only one of those sentences
       can be honest. */
    /* The reader's words only: the claims question has none to show. */
    readClauses: constraints.filter(([key]) => key !== NEXT_READING_CLAIMS)
      .map(([key, label]) =>
        [key === "goal" && NEXT_PROMPT_SOURCES.includes(source.goal_source)
          ? "GOAL FROM YOUR PROMPT" : label, nextCockpitReadingClause(key, rows[key], annotation, historical)]),
    stamp: String(source.stamp || ""),
    cutoff: String(source.cutoff || ""),
    /* From the READING, not from the live row. A stored reading describes
       the moment it was taken: keying the scope sentence on today's
       `endKind` made a mid-flight reading start claiming to cover an ending
       it never saw the moment the session stopped. */
    scopeText: String(source.scope_text || ""),
    scope: String(source.scope || ""),
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
  if(row.key === NEXT_READING_CLAIMS) return "";
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

/* The claims row's four states (owner, 2026-10-04), each naming the agent's
   message by the list's number. "Not shown" says the record read is the
   board's recent tail, so it is about what was read, never that the thing
   did not happen. */
const NEXT_RESULT_CLAIM_TAIL = "The record read is the board's recent tail.";

function nextCockpitClaimStatus(row, numbers, short){
  const said = nextCockpitResultWhere(row.claimEntry, numbers);
  const record = nextCockpitResultWhere(row.recordEntry, numbers);
  const what = said ? `What the agent said at ${said}` : "What the agent said";
  if(row.result === NEXT_READING_DEPARTURE){
    return `${what} is contradicted${record ? ` at ${record}` : ""}`;
  }
  if(row.result === NEXT_READING_UNSUPPORTED){
    return short ? `${what} is not shown by the record`
      : `${what} is not shown by the record. ${NEXT_RESULT_CLAIM_TAIL}`;
  }
  if(row.result === NEXT_READING_CONSISTENT && record){
    const tool = row.recordEntry && (String(row.recordEntry.type || "") === "tool_report" ||
      row.recordEntry.subject === "check");
    return `${what} is shown at ${record}` +
      (tool && !short ? ", as the tool reported; not inspected" : "");
  }
  return row.why || row.limit ? NEXT_RESULT_CANT_TELL : NEXT_RESULT_NOTHING_SHOWS;
}

function nextCockpitResultStatus(row, numbers, byId, short = false){
  if(row.key === NEXT_READING_CLAIMS) return nextCockpitClaimStatus(row, numbers, short);
  if(row.result === NEXT_READING_DEPARTURE){
    const where = nextCockpitResultWhere(byId.get(String((row.citedIds || [])[0] || "")), numbers);
    return where ? `Departs at ${where}` : "Departs";
  }
  if(row.result === NEXT_READING_CONSISTENT && row.restsOn){
    const where = nextCockpitResultWhere(row.restsOnEntry, numbers);
    if(where){
      /* `short` is the checklist's line in view: the source stays named, and
         the qualifier is said in full in the line's Evidence and once in view
         for every tool result, in the activity record's footer (DRC-4758 fix
         round, the stored-reading word budget). */
      const who = row.restsOn === "message" ? "the agent" : "the session";
      if(short){
        return row.restsOn === "tool" ? `Consistent with ${where}`
          : `Consistent with what ${who} said at ${where}`;
      }
      return row.restsOn === "tool"
        ? `Consistent with ${where}, as the tool reported; not inspected`
        : `Consistent with what ${who} said at ${where}; not a check`;
    }
  }
  /* A consistent the page cannot place is no claim it can word, so it is
     said as what it is to the reader: nothing shown. */
  return row.why || row.limit ? NEXT_RESULT_CANT_TELL
    : (row.citedIds || []).length ? "Can't tell: what was read does not settle this"
    : NEXT_RESULT_NOTHING_SHOWS;
}

function nextCockpitResultState(row){
  if(row.key === NEXT_READING_CLAIMS){
    return row.result === NEXT_READING_DEPARTURE ? "departs"
      : row.result === NEXT_READING_UNSUPPORTED ? "unshown"
      : row.result === NEXT_READING_CONSISTENT && row.recordEntry ? "consistent" : "cant-tell";
  }
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
    (row.coverage ? `<span class="next-cockpit-reading-why">${esc(row.coverage)}</span>` : "") +
    (row.why ? `<span class="next-cockpit-reading-why">${esc(row.why)}</span>` : "") +
    tail + '</div>';
}

/* One line of the result's checklist, in the Drift card (DRC-4758 slice C):
   a glyph by state, the line's own words as its title, the ruled status
   beneath, and the source tag, why and limit one click away under
   "Evidence". The glyph is shape first: a cross for departs, a neutral
   filled dot for consistent (never a check, never green), a dashed circle
   for can't tell; the clay on the cross is the one colour (owner Q10,
   2026-10-01). */
function nextCockpitResultItem(row, numbers, byId, tag = "li"){
  const tail = row.limit
    ? `<span class="next-cockpit-reading-limit">limit · ${esc(row.limit)}</span>`
    : row.evidence.map(line =>
      `<span class="next-cockpit-reading-evidence">${esc(line)}</span>`).join("");
  const status = nextCockpitResultStatus(row, numbers, byId, true);
  const full = nextCockpitResultStatus(row, numbers, byId);
  const evidence = `<span class="next-cockpit-reading-name">${esc(row.label)}</span>` +
    (full === status ? "" : `<span class="next-cockpit-reading-evidence">${esc(full)}</span>`) +
    (row.why ? `<span class="next-cockpit-reading-why">${esc(row.why)}</span>` : "") + tail;
  return `<${tag} class="next-cockpit-reading-row" data-next-result-state="${nextCockpitResultState(row)}"` +
    `${tag === "li" ? "" : row.key === NEXT_READING_CLAIMS ? " data-next-result-claims"
      : " data-next-result-goal"}>` +
    '<span class="next-cockpit-result-glyph" aria-hidden="true"></span>' +
    '<span class="next-cockpit-result-body">' + nextCockpitReadingClauseCell(row) +
    `<em class="next-cockpit-reading-result">${esc(status)}</em>` +
    (row.coverage ? `<span class="next-cockpit-reading-why">${esc(row.coverage)}</span>` : "") +
    `<details class="next-cockpit-why"${nextCockpitDisclosureAttr(`result-evidence:${row.key}`)}>` +
    `<summary>Evidence</summary>${evidence}</details></span></${tag}>`;
}

/* Item 14's answer reducer, over the rows after every page rule. Any valid
   departure departs, whatever the other lines say; otherwise a failed check in
   the reading's window, where a check with no time counts as inside it, as
   `levels.analysis_level` reads it; otherwise any line without a valid
   verdict, a malformed or missing result included, cannot tell; otherwise
   nothing was found. A reading with no outcome line cannot tell either: the
   goal row alone is not an answer against what the work was for. */
/* The answer is about the intent alone. The claims row is not the intent, so
   it never counts as departing from it and never holds "Nothing found" back;
   a claim is said once, in its own row, and the level names it as a reason
   (review, PR C: a fact said once on the panel). */
/* The claims row as the result draws it: not where the agent made no claim,
   which the reading says as its own `unverifiable` with no reason ("stop
   overusing prose", owner 2026-10-02; review, PR C). */
function nextCockpitClaimsDrawn(shape){
  return shape.criteria.filter(row => row.key === NEXT_READING_CLAIMS &&
    row.result !== NEXT_READING_UNVERIFIABLE);
}

function nextDriftAnswer(shape, entries, scan = null){
  const intent = shape.criteria.filter(row => row.key !== NEXT_READING_CLAIMS);
  const departures = intent.filter(row => row.result === NEXT_READING_DEPARTURE);
  if(departures.length) return {kind: "departs", count: departures.length, departures};
  if(!intent.some(row => nextReadingIsOutcomeLine(row.key))) return {kind: "cant-tell"};
  const failed = nextFailedChecksAfterPerson(entries, scan && scan.last_user_at,
    shape.windowStart || 0);
  if(failed.length){
    const latest = failed.reduce((a, b) =>
      (nextReadingEvidenceAt(b) || 0) >= (nextReadingEvidenceAt(a) || 0) ? b : a);
    return {kind: "failed-check", failed: latest};
  }
  const verdict = row => row.result === NEXT_READING_CONSISTENT && row.restsOn;
  if(!intent.some(row => nextReadingIsOutcomeLine(row.key)) ||
      !intent.every(verdict)) return {kind: "cant-tell"};
  return {kind: "nothing-found"};
}

const NEXT_RESULT_DEPARTS = "Departs from your intent";
const NEXT_RESULT_NOTHING_FOUND =
  "Nothing found against what it read. This is not a check that the work was done.";

/* The answer, and under a departure the headline with its count and a short
   account built from each departure's detail and its citation, never a
   model's narrative (item 6). The count renders only here. */
/* `midFlight` leads the answer with "So far:", so a reading of a running
   session never looks like a reading of how it ended (owner, 2026-10-02). */
function nextCockpitResultAnswer(answer, numbers, byId, midFlight = false){
  const open = '<div class="next-cockpit-result-answer">';
  const lead = midFlight ? '<span class="next-cockpit-result-scope">So far:</span> ' : "";
  if(answer.kind === "departs"){
    const count = `${answer.count} departure${answer.count === 1 ? "" : "s"}`;
    const account = answer.departures.map(row => {
      const where = nextCockpitResultWhere(byId.get(String((row.citedIds || [])[0] || "")), numbers);
      const detail = String(row.detail || "").trim();
      return detail
        ? `<p class="next-cockpit-reading-detail">${esc(detail)}${where ? ` (${esc(where)})` : ""}</p>`
        : "";
    }).join("");
    return open + `<p class="next-cockpit-result-headline">${lead}` +
      `<span>${NEXT_RESULT_DEPARTS}</span>` +
      `<span class="next-cockpit-result-count">${esc(count)}</span></p>${account}</div>`;
  }
  if(answer.kind === "failed-check"){
    const where = nextCockpitResultWhere(answer.failed, numbers);
    return open + `<p class="next-cockpit-result-line">${lead}${esc(where
      ? `A check failed at ${where}.` : "A check failed.")}</p></div>`;
  }
  return open + `<p class="next-cockpit-result-line">${lead}${esc(answer.kind === "cant-tell"
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
  /* Behind its count, so the list's own rows are what stands in view. */
  const unlisted = more
    ? `<details class="next-cockpit-why"${nextCockpitDisclosureAttr("result-work-more")}>` +
      `<summary>${more} more</summary>` +
      `<p class="next-cockpit-reading-why">${more} more written ${more === 1 ? "file is" : "files are"} ` +
      "counted and not listed.</p></details>" : counted == null || counted < writes.length
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
  const readAt = nextNumber(raw && raw.read_at);
  const after = !superseded && readAt != null ? (entries || []).filter(nextReadingPersonAuthored)
    .find(entry => (nextNumber(entry.at) || 0) > readAt) : null;
  const head = superseded ? "Your intent changed after this analysis."
    : after ? `Read before your message at ${nextSessionClock(after.at)}. New work since this analysis.`
    : "New work since this analysis.";
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
    '<button type="button" class="next-action next-action--quiet" data-next-cockpit-action="not-accurate" ' +
    `data-arg="${esc(String(readAt))}" aria-pressed="${marked ? "true" : "false"}" ` +
    `data-next-focus="not-accurate:${esc(key)}"${nextPendingAttrs(`not-accurate:${key}`)}>` +
    `${nextPendingLabel(`not-accurate:${key}`, NEXT_RESULT_NOT_ACCURATE)}</button>` +
    (marked ? `<span class="next-cockpit-result-marked">${NEXT_RESULT_MARKED}</span>` : "") +
    (nextCockpitNotAccurateUnsaved.has(key)
      ? `<p class="next-cockpit-reading-why" role="status">${NEXT_RESULT_MARK_UNSAVED}</p>` : "") +
    '</div>';
}

async function nextCockpitMarkNotAccurate(session, readAt){
  const key = sessKey(session);
  const control = `not-accurate:${key}`;
  const press = nextPendingStart(control, "Saving\u2026");
  if(!press) return;
  renderNext({named: control});
  const annotation = nextCockpitAnnotation(session);
  const on = !(annotation && annotation.not_accurate === true);
  nextCockpitNotAccurateUnsaved.delete(key);
  let saved = false;
  try{
    const response = await nextFetchBounded("/api/annotate", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({harness: session.harness, sid: session.sid, not_accurate: on,
        read_at: readAt})}, press.signal);
    const answer = response && typeof response.json === "function"
      ? await response.json().catch(() => null) : null;
    saved = Boolean(response && response.ok && answer && answer.persisted !== false &&
      ["stored", "unchanged"].includes(String(answer.outcome || "")));
  }catch(_error){
    saved = false;
  }
  if(!saved) nextCockpitNotAccurateUnsaved.add(key);
  try{
    await refreshNext();
  }finally{
    nextPendingEnd(control, press);
    renderNext({named: control});
  }
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
  const lane = nextCockpitDepartureLaneCount(session);
  const laneRows = Array.isArray(session && session.departures) ? session.departures.length : 0;
  /* Drawn only where the unasked lane holds rows, collapsed under their count
     (owner Q9, 2026-10-01; DRC-4758 slice E). The reading's own departures are
     said once, in the result that stands in the control's slot, so this
     section no longer repeats them; "nothing watches" and the off switch's
     reason go with the section, because a session with nothing raised has
     nothing for them to qualify. A raise on record is drawn whichever way the
     switch is set (DRC-4559).

     One exception, and it is an absence rather than a row: with the lane on
     and nothing raised, the lane's own sentence -- not checked, checked and
     found nothing, or a cap spent -- stays in view, because those are three
     different facts and silence would read as the reassuring one (the first
     Measured Invariant; absences are tier 1 under
     [NUI-19](docs/design-next-ui.md#nui-19-a-caveat-has-three-tiers)). */
  const laneOn = Boolean(nextData && nextData.unasked === true);
  const why = laneOn && !laneRows
    ? String(session && session.departure_why == null ? "" : session.departure_why) : "";
  if(!laneRows && !why) return "";
  const limit = nextSessionRaiseControl(session) ? nextDepartureReentryLimit(session) : {raise:""};
  const summary = laneRows ? `Raised while you were away: ${laneRows}` : "About these checks";
  return '<section class="next-cockpit-departures">' +
    (laneRows ? "" : nextCockpitUnaskedPart(session)) +
    `<details class="next-cockpit-why"${nextCockpitDisclosureAttr("departures")}>` +
    `<summary>${esc(summary)}</summary>` +
    `<p class="next-cockpit-define">${NEXT_COCKPIT_DEPARTURE_DEFINITION}</p>` +
    (laneRows ? nextCockpitUnaskedPart(session) + limit.raise : "") +
    nextCockpitDeliveryPart(session, Boolean(lane)) +
    nextCockpitDepartureCounts(shape ? nextCockpitReadingDepartures(shape, source, session).count
      : null, lane) +
    `<p class="next-cockpit-reading-why">${NEXT_COCKPIT_STEER_BY_HAND}</p>` +
    nextCockpitWhy("steer-why", "Why no raise goes further", NEXT_COCKPIT_STEER_BY_HAND_WHY) +
    '</details></section>';
}

/* Where a raise is kept, in the tab's last slot. Separate from the section
   above so the design's order survives: it is a pointer off this tab, like HOW
   IT LANDED is a block of it, and appending it inside the departures section
   put it above HOW IT LANDED at every measured offset. */
function nextCockpitDeparturesKept(){
  /* The link in view and what it keeps one click away (DRC-4758 slice E). */
  return '<div class="next-cockpit-departures-kept"><a href="#n=intent">Intent log</a>' +
    nextCockpitWhy("kept-why", "What it keeps", "The Intent log keeps what you saved and what " +
      "was raised against it after the session leaves the board.") + '</div>';
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
/* The harnesses a press carries the agent's own messages from
   (`reading_route.AGENT_MESSAGE_HARNESSES`). Elsewhere a press sends none of
   them, so an Allow given before the disclosure named them still covers it:
   the server publishes that answer as `words` (`reading_policy.WORDS_CONTENT_VERSION`). */
const NEXT_READING_AGENT_WORDS_HARNESSES = ["claude"];

function nextReadingConsent(provider, harness = ""){
  const policy = nextData && nextData.reading;
  if(!policy || !provider) return false;
  const words = policy.words;
  const map = !NEXT_READING_AGENT_WORDS_HARNESSES.includes(String(harness || "")) &&
    words && typeof words === "object" ? words : policy.providers;
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
  return !nextReadingConsent(String(route.provider), String(route.harness || "")) ||
    Boolean(route.destination && !nextReadingToolOutputGranted(route));
}

/* The short line beside an inert Analyze drift, one per token the board can
   publish as `reading_eligibility.reason` (`reading.PRESS_WITHHELD`, walked by
   a test). Page copy keyed by the server's token; the server's own sentence
   rides beside it, verbatim, under "Why it can't read". Codex, which reads
   only while a turn runs and has no session end the board can observe, gets
   its own line for both idle tokens (owner Q8, 2026-10-01). DRC-4758 slice B.
   No line promises Analyze opens "once this session finishes a turn": the turn
   may have finished where Cargento could not see it (owner, 2026-10-02).
   `nextReadingPressLine` holds the per-harness variants. */
const NEXT_READING_PRESS_LINES = {
  "idle-unknown": "Analyze opens while this session runs.",
  "unobservable": "This harness sends no events, so Analyze opens only while it runs.",
  "turn-stop": "Analyze opens while a turn runs or once the session ends.",
  "settling": "Ready in a few seconds.",
  "stop-settling": "Ready in a few seconds.",
  "revision-after-end": "Your intent was saved after this session ended.",
};
const NEXT_READING_PRESS_CODEX = "Codex sessions can be analyzed only while a turn is running.";
/* Claude Code records a finished turn itself, so an idle row without one is a
   turn not recorded as finished, and the Why says the four reasons it may be. */
const NEXT_READING_PRESS_CLAUDE = "This session's last turn isn't recorded as finished.";
const NEXT_READING_PRESS_EVENTS = "Analyze opens while this session runs or once it ends.";

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
  const harness = String(session && session.harness || "");
  if(harness === "codex" && ["idle-unknown", "turn-stop"].includes(reason)) return NEXT_READING_PRESS_CODEX;
  if(reason === "idle-unknown" && harness === "claude") return NEXT_READING_PRESS_CLAUDE;
  if(reason === "idle-unknown" && session && session.acquisition === "event") return NEXT_READING_PRESS_EVENTS;
  return NEXT_READING_PRESS_LINES[reason] || String(eligibility.sentence || "");
}

/* No silent flips. Analyze opening at once is honest, so inert to live
   commits on the render that sees it. Closing waits until the inert state has
   held for two distinct payloads and `NEXT_READING_FLIP_HOLD_MS`, the
   activity grace, so a session pausing between turns (running, then a stop
   settling for 8 s, then its last turn) never closes the button. A candidate
   that reverts first says nothing. Only the drawn card is tracked: an entry
   not drawn on the render before is drawn fresh, saying nothing. */
const NEXT_READING_FLIP_HOLD_MS = 10_000;
const NEXT_READING_FLIP_SAY_EVERY_MS = 60_000;
const NEXT_READING_FLIP_OPEN_RUNNING = "Analyze is open again: the session is running.";
const NEXT_READING_FLIP_OPEN_LAST_TURN = "Analyze is open: the session's last turn finished.";
const NEXT_READING_FLIP_OPEN_ENDED = "Analyze is open: the session ended.";
/* "Went quiet", not "stopped": a close also follows a turn left on an open tool
   call or an interruption, which did not stop (verifier F5). */
const NEXT_READING_FLIP_CLOSED = "Analyze closed: the session went quiet.";
const NEXT_READING_FLIP_CLOSED_REVISION = "Analyze closed: your intent was saved after the session ended.";
const NEXT_READING_FLIP_CLOSED_UNANSWERED = "Analyze closed before you answered, so nothing was sent.";
let nextReadingFlipRender = 0;
/* One page-wide timer each, never one per row: the hold, a settle's `until`
   and the change line's TTL, for the one drawn card. */
const nextReadingFlipTimers = {hold: null, until: null, line: null, say: null};

function nextReadingFlipSchedule(name, at){
  const current = nextReadingFlipTimers[name];
  if(current && current.at === at) return;
  if(current) clearTimeout(current.id);
  nextReadingFlipTimers[name] = null;
  if(at == null) return;
  const delay = at - Date.now();
  // A moment this far off is a fixture or a clock skew, never a settle.
  if(!Number.isFinite(delay) || delay > 2 * NEXT_READING_FLIP_SAY_EVERY_MS) return;
  nextReadingFlipTimers[name] = {at, id: setTimeout(() => {
    nextReadingFlipTimers[name] = null;
    nextPaintAfterMotion(() => renderNext());
  }, Math.max(0, delay))};
}

// Whether a press on this session is still being answered: flips wait for it.
function nextReadingFlipFrozen(session){
  const key = sessKey(session);
  return [`reading:${key}`, `reading-allow:${key}`, `direction-keep:${key}`,
    `${nextCockpitIntentKey(session)}:save`].some(nextPendingHas);
}

function nextReadingFlipOpened(session){
  if(nextSessionEndedAt(session) != null) return NEXT_READING_FLIP_OPEN_ENDED;
  if(session.state === "idle" && nextSessionStop(session)) return NEXT_READING_FLIP_OPEN_LAST_TURN;
  return NEXT_READING_FLIP_OPEN_RUNNING;
}

function nextReadingFlipSay(session, flip, sentence){
  flip.line = sentence;
  flip.lineAt = Date.now();
  /* In view every time; to the region at most once a minute per session, so a
     session that flaps is not read out on every turn. A flip inside the minute
     is held, never dropped: the newest is said when the minute is up, so the
     region's last word is never a state that has gone (verifier F4). */
  if(flip.saidAt != null && Date.now() - flip.saidAt < NEXT_READING_FLIP_SAY_EVERY_MS){
    flip.owed = sentence;
    nextReadingFlipSchedule("say", flip.saidAt + NEXT_READING_FLIP_SAY_EVERY_MS);
    return;
  }
  nextReadingFlipAnnounce(session, flip, sentence);
}

function nextReadingFlipAnnounce(session, flip, sentence){
  const key = sessKey(session);
  flip.saidAt = Date.now();
  flip.said = sentence;
  flip.owed = "";
  nextCockpitAnnouncedCues.delete(`flip:${key}`);
  nextCockpitAnnounceCue(`flip:${key}`, sentence, false);
}

/* The held flip, once the minute is up, unless the region already said the
   state the card now shows: a flip that reverted inside the minute owes nothing. */
function nextReadingFlipOwed(session, flip){
  if(!flip.owed || flip.saidAt == null) return;
  if(Date.now() - flip.saidAt < NEXT_READING_FLIP_SAY_EVERY_MS) return;
  const owed = flip.owed;
  flip.owed = "";
  if(owed !== flip.said) nextReadingFlipAnnounce(session, flip, owed);
}

/* A press the reader made learned the state itself, so the card takes it
   without a line: the press's own answer says it. */
function nextReadingFlipAcknowledge(session, pressable){
  const flip = nextReadingFlips.get(sessKey(session));
  if(flip){
    flip.shown = pressable;
    flip.candidate = null;
    flip.owed = "";
  }
}

/* Whether the drawn card shows Analyze pressable, given whether the board says
   it is. Also says a committed change and schedules the hold's re-render. */
function nextReadingFlip(session, pressable, eligibility, quiet = false){
  const key = sessKey(session);
  let flip = nextReadingFlips.get(key);
  if(!flip || flip.drawn < nextReadingFlipRender - 1){
    flip = {shown: pressable, candidate: null, candidateSince: 0, candidateData: null,
      saidAt: flip ? flip.saidAt : null, said: flip ? flip.said : "", owed: "",
      line: "", lineAt: 0, drawn: nextReadingFlipRender};
    nextReadingFlips.delete(key);
    nextReadingFlips.set(key, flip);
    while(nextReadingFlips.size > NEXT_COCKPIT_HELD_CUE_LIMIT){
      nextReadingFlips.delete(nextReadingFlips.keys().next().value);
    }
    return flip;
  }
  flip.drawn = nextReadingFlipRender;
  nextReadingFlipOwed(session, flip);
  if(nextReadingFlipFrozen(session)) return flip;
  if(pressable === flip.shown){
    flip.candidate = null;
    nextReadingFlipSchedule("hold", null);
    return flip;
  }
  if(pressable){
    flip.shown = true;
    flip.candidate = null;
    nextReadingFlipSchedule("hold", null);
    if(!quiet) nextReadingFlipSay(session, flip, nextReadingFlipOpened(session));
    return flip;
  }
  const now = Date.now();
  if(flip.candidate !== false){
    flip.candidate = false;
    flip.candidateSince = now;
    flip.candidateData = nextData;
  }
  if(nextData === flip.candidateData || now - flip.candidateSince < NEXT_READING_FLIP_HOLD_MS){
    /* Armed only while the moment is ahead. Past it, the hold waits for the
       next payload: re-arming a past moment redrew #app back to back while
       the stream was down (verifier R1). */
    const at = flip.candidateSince + NEXT_READING_FLIP_HOLD_MS;
    nextReadingFlipSchedule("hold", at > now ? at : null);
    return flip;
  }
  flip.shown = false;
  flip.candidate = null;
  nextReadingFlipSchedule("hold", null);
  const request = nextCockpitReadingRequests.get(key);
  if(quiet) return flip;
  if(request && request.consent && !request.pending){
    /* The question was the consent, and it is gone: never raised again
       without a press (J5). */
    nextCockpitReadingRequests.delete(key);
    nextReadingFlipSay(session, flip, NEXT_READING_FLIP_CLOSED_UNANSWERED);
    return flip;
  }
  nextReadingFlipSay(session, flip, eligibility && eligibility.reason === "revision-after-end"
    ? NEXT_READING_FLIP_CLOSED_REVISION : NEXT_READING_FLIP_CLOSED);
  return flip;
}

// The change line, while it stands, with the one timer that takes it down.
function nextReadingFlipLine(session){
  const flip = nextReadingFlips.get(sessKey(session));
  if(!flip || !flip.line) return "";
  const until = flip.lineAt + NEXT_CONTROL_STATE_TTL_MS;
  if(Date.now() >= until){
    flip.line = "";
    return "";
  }
  nextReadingFlipSchedule("line", until);
  return `<p class="next-cockpit-reading-why next-cockpit-reading-change">${esc(flip.line)}</p>`;
}

// The next click inside the card takes the change line down.
document.addEventListener("click", event => {
  const target = event && event.target;
  if(!target || typeof target.closest !== "function" || !target.closest("#next-session-drift")) return;
  for(const flip of nextReadingFlips.values()) flip.line = "";
}, true);

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
function nextReadingJobBox(job, key, running = false){
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
    `${nextPendingHas(`reading-cancel:${key}`) ? nextPendingAttrs(`reading-cancel:${key}`)
      : finishing ? ' aria-disabled="true"' : ""}>` +
    `${nextPendingLabel(`reading-cancel:${key}`, "Cancel")}</button></div>` +
    `<ol class="next-cockpit-reading-steps">${items}</ol>` +
    `<p class="next-cockpit-reading-job-note">` +
    `${esc(running ? NEXT_READING_JOB_NOTE_SO_FAR : NEXT_READING_JOB_NOTE)}</p>` +
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
/* No positional word, so it is true at every width: the result stands in
   the Drift card, in the button's place (DRC-4758 slice C). */
const NEXT_READING_FINISHED = "The analysis finished. Its result is in the Drift section.";
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
/* One person-message boundary for the answer and correction, mirroring reading.py. */
function nextFailedChecksAfterPerson(entries, anchor = null, floor = 0){
  const times = (entries || []).filter(entry => entry && entry.type === "user_message")
    .map(entry => nextNumber(entry.at)).filter(at => at > 0);
  if(nextNumber(anchor) > 0) times.push(nextNumber(anchor));
  if(!times.length) return [];
  const start = Math.max(floor || 0, ...times);
  return (entries || []).filter(entry => entry && entry.type === "tool_report" &&
    entry.subject === "check" && entry.result === "failed" &&
    nextReadingEvidenceAt(entry) > start);
}

function nextCockpitSteerTrigger(offer, shape, session, entries, numbers, scan = null){
  if(!offer) return "";
  const ids = offer.departed && shape ? shape.departures.flatMap(row => row.citedIds || [])
    : offer.claimed && shape ? shape.criteria.filter(row => row.key === NEXT_READING_CLAIMS)
      .flatMap(row => row.citedIds || []) : [];
  const candidates = offer.failed && !ids.length ? nextCockpitFailedChecks(session,entries,scan)
    : (entries || []).filter(entry => ids.includes(String(entry.id || "")));
  const fact = candidates.reduce((last, entry) => !last ||
    nextReadingEvidenceAt(entry) > nextReadingEvidenceAt(last) ? entry : last, null);
  if(!fact) return "";
  const at = nextReadingEvidenceAt(fact);
  const n = numbers.get(String(fact.id || ""));
  const age = at > 0 ? `${fmtDur(Math.max(0,(nextData && nextData.generated || 0)-at))} ago` : "time not recorded";
  const trigger = offer.departed ? "Departure" : offer.claimed ? "Claim to check" : "Check failed";
  return `<p class="next-cockpit-reading-why">${esc(`${trigger}${n != null ? ` at #${n}` : ""} · ${age}`)}</p>`;
}

function nextReadingBudgetLine(){
  const policy = nextData && nextData.reading;
  if(!policy || !Number.isInteger(policy.used) || !Number.isInteger(policy.limit) ||
      policy.used < 0 || policy.limit <= 0) return "";
  return `<p class="next-cockpit-reading-budget">${Math.max(0,policy.limit-policy.used)} of ${policy.limit} left today</p>`;
}

function nextReadingArrivedLine(annotation, entries){
  const at = nextNumber(annotation && annotation.assessment && annotation.assessment.read_at);
  if(!(at > 0)) return "";
  const arrived = (entries || []).filter(entry => nextReadingEvidenceAt(entry) > at);
  const checks = arrived.filter(entry => entry.type === "tool_report" && entry.subject === "check").length;
  const writes = arrived.filter(entry => entry.type === "tool_report" && entry.subject === "write").length;
  const messages = arrived.filter(entry => ["user_message","agent_message"].includes(entry.type)).length;
  const parts = [[checks,"check"],[writes,"file write"],[messages,"message"]]
    .filter(([count]) => count > 0).map(([count,label]) => `${count} ${label}${count === 1 ? "" : "s"}`);
  return parts.length ? `<p class="next-cockpit-reading-why">${esc(parts.join(", "))} arrived since this analysis.</p>` : "";
}

function nextCockpitFailedChecks(session, entries, scan = null){
  return nextFailedChecksAfterPerson(entries, scan && scan.last_user_at,
    nextNumber(session && session.annotation_window_start) || 0);
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
  const current = Boolean(annotation && annotation.not_accurate !== true &&
    shape && !shape.malformed && shape.revisionRead != null &&
    shape.revisionRead === nextNumber(annotation && annotation.revision));
  const departed = current && shape.departures.length > 0;
  /* A claim the record contradicts or does not show is something to steer
     from too (`correction._claim_line`, owner 2026-10-04), read from the
     claims row itself: it is not a departure from the intent, so it never
     offers "Update intent instead" (review, PR C). */
  const claimed = current && shape.criteria.some(row => row.key === NEXT_READING_CLAIMS &&
    [NEXT_READING_DEPARTURE, NEXT_READING_UNSUPPORTED].includes(row.result));
  const failed = nextCockpitFailedChecks(session, entries, source.scan).length > 0;
  return departed || claimed || failed ? {departed, claimed, failed} : null;
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
  return read ? nextCockpitFailedChecks(session, source.all || source.entries || [], source.scan)
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

/* A claim alone is a question and always secondary, including without a reader.
   [DEC-17](docs/design-reading-a-session.md#dec-17-the-shape-contract)
*/
function nextCockpitSteerPrimary(offer, noReader, primary = true){
  return Boolean(primary && offer && (offer.departed || (offer.failed && noReader)));
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
  const bounded = nextBoundedSignal();
  try{
    const response = await nextFetchBounded("/api/correction", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({harness: session.harness, sid: session.sid})}, bounded.signal);
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
  }finally{
    bounded.done();
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
  const bounded = nextBoundedSignal();
  try{
    await nextFetchBounded("/api/correction/copied", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({harness: session.harness, sid: session.sid, text})}, bounded.signal);
  }catch(_error){
    /* Unrecorded, a paste reads as the reader's own words: the safe side. */
  }finally{
    bounded.done();
  }
}

/* `steer` is Steer back's controls and box in this slot
   (`nextCockpitReadingParts` decides): under a departure, the primary with
   Update intent instead beside it, ahead of Analyze drift (`lead`); with no
   reader, the primary beside the route's reason; with a reader and no
   departure, a secondary after Analyze drift. */
/* `again` draws the press at the foot of a stored result (owner Q3,
   2026-10-01): "Analyze again", with every refusal, consent step and count it
   has as "Analyze drift", and no hint line. Its caller passes `primary`
   false: it is never the stage's primary. */
/* `about` is what a reading is, drawn inside "What is sent" while no reading
   is stored: the READING section that carried it is drawn only to say a stored
   reading could not be read (DRC-4758 slice E, tier 2 of
   [NUI-19](docs/design-next-ui.md#nui-19-a-caveat-has-three-tiers)). */
/* The board's half of whether Analyze can be pressed, as the drawn card shows
   it, for the Analyze control and the direction question alike: a card that
   draws Keep and Add in Analyze's place flipped silently, with no hold and no
   Why (verifier F1). `reason` is the press's refusal with the board's ranked
   first; the answer's `reason` is what to draw. */
function nextReadingBoard(session, annotation, model, reason){
  let pressed = nextReadingEligibility(session);
  const refusedByBoard = Boolean(pressed) && reason === nextReadingPressLine(session, pressed);
  /* Only the board's eligibility flips: a refusal the reader's own edit caused
     is not one. While a close is still held, the card draws Analyze live and
     a press is answered by the handler's refusal. */
  /* A change another refusal still hides (the model switch, an unsaved edit)
     is tracked and never said: "Analyze is open" beside an inert button is
     false. */
  const hidden = Boolean(nextPromptReadingRefusal(session, annotation, model, true));
  const flip = nextReadingFlip(session, !refusedByBoard, pressed, hidden);
  if(refusedByBoard && flip.shown){
    reason = nextPromptReadingRefusal(session, annotation, model, true);
    pressed = null;
  }
  const inert = refusedByBoard && !flip.shown;
  const changed = nextReadingFlipLine(session);
  const settling = inert && ["settling", "stop-settling"].includes(String(pressed.reason || ""));
  nextReadingFlipSchedule("until", settling && nextNumber(pressed.until) != null
    ? nextNumber(pressed.until) * 1000 : null);
  return {reason, pressed, inert, changed, settling};
}

/* Why a press cannot run, under the row it refuses, with the board's Why
   beside an inert one. */
function nextReadingRefusedLine(session, reason, request, board){
  if(!reason) return "";
  return `<p class="next-cockpit-reading-why"${request && request.refusal && !request.announced
    ? ' role="status"' : ""}` +
    ` id="${NEXT_READING_REFUSED_ID}"` +
    `${nextAbsenceAttr(NEXT_READING_REFUSAL_ABSENCE.get(reason))}>` +
    /* Waiting, not busy: the record is settling and Analyze opens by itself
       at `until`, so a dot pulses rather than the press's spinner. */
    `${board.settling ? '<span class="next-wait-dot" aria-hidden="true"></span>' : ""}${esc(reason)}</p>` +
    (board.inert ? nextCockpitWhy(`reading-why:${sessKey(session)}`, "Why it can't read",
      board.pressed.sentence) : "");
}

function nextCockpitReadingControl(session, annotation, model, primary = true, steer = null,
    again = false, about = ""){
  const steerButton = steer ? steer.button : "";
  const lead = Boolean(steer && steer.lead);
  const steerBox = steer ? steer.box : "";
  let reason = nextPromptReadingRefusal(session, annotation, model);
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
  const board = nextReadingBoard(session, annotation, model, reason);
  reason = board.reason;
  const {pressed, inert, changed, settling} = board;
  /* The question stays drawn while its Allow is being answered: the card is
     the consent, and taking it away mid-press left a bare hatched button. */
  const allowKey = `reading-allow:${key}`;
  const confirming = Boolean(provider && !inert && ((request && request.consent &&
    nextReadingNeedsAllow(route)) || nextPendingHas(allowKey)));
  const busyKey = confirming ? allowKey : `reading:${key}`;
  const busy = nextPendingHas(busyKey);
  /* `authorized` is no longer a second term here: an unauthorized check is
     one of the sentences `nextCockpitReadingRefusal` returns, so `!reason`
     already carries it. */
  const enabled = !reason && !pending;
  const count = nextNumber(annotation && annotation.reading_count) || 0;
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
  /* The server's own parts, a short list in its order and unreworded: in the
     consent step, so "Allow and analyze" no longer drops below one long block
     (owner Q1, 2026-10-01), and idle in the "What is sent" popover, so the two
     cannot differ (owner, 2026-10-02). A route from before the parts were
     published shows its whole disclosure as one item. */
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
    (NEXT_PROMPT_SOURCES.includes(annotation.goal_source)
      ? annotation.goal_source_at : annotation.at));
  const endedAt = nextSessionEndedAt(session);
  const hint = provider && !reason && String(annotation && annotation.goal || "").trim() &&
    !(endedAt != null && given != null && given > endedAt) ? nextObservedReadHint(session) : "";
  const readHint = hint && !again ? `${hint} ${NEXT_READING_BACKGROUND}` : "";
  const job = nextReadingJob(session);
  const off = nextReadingAnyConsent()
    ? '<button type="button" class="next-action" data-next-cockpit-action="reading-off" ' +
      `data-next-focus="reading-off:${esc(key)}"${nextPendingAttrs(`reading-off:${key}`)}>` +
      `${nextPendingLabel(`reading-off:${key}`, "Turn off readings")}</button>` : "";
  /* Only from a published annotation: with the store off there is no count
     to read, and "0 requests" would be a default standing in for one. */
  const counted = annotation ? nextCockpitReadingCount(count) : "";
  const budget = nextReadingBudgetLine();
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
  /* The disclosure is not drawn under the box: nothing more is sent by
     this job, and the reader allowed it, or it ran under an Allow, after the
     same words (DRC-4758 slice B). */
  if(job){
    const running = nextSessionEndedAt(session) == null && session.state !== "idle";
    return nextReadingJobBox(job, key, running) +
      (off ? `<div class="next-cockpit-reading-ask">${off}</div>` : "") +
      said(answered) + counted + budget;
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
  const aboutWhy = about ? nextCockpitWhy("reading-about", "What a reading reads", about) : "";
  if(noReader){
    return '<div class="next-cockpit-reading-ask next-cockpit-reading-ask--none">' +
      `<p class="next-cockpit-reading-why" tabindex="-1" data-next-focus="reading:${esc(key)}" ` +
      `data-next-reading-no-reader${nextAbsenceAttr(NEXT_READING_REFUSAL_ABSENCE.get(noReader))}>` +
      `${esc(noReader)}</p>` + steerButton + off + '</div>' + steerBox +
      said(answered === noReader ? "" : answered) + counted + aboutWhy;
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
    `<button type="button" class="next-action${primary && provider && !inert ? " next-action--primary"
      : again && !confirming ? " next-action--secondary" : ""}" ` +
    `data-next-cockpit-action="${confirming ? 'reading-allow' : 'reading-ask'}" ` +
    `data-next-focus="reading:${esc(sessKey(session))}"` +
    `${busy ? nextPendingAttrs(busyKey) : enabled ? "" : ' aria-disabled="true"'}` +
    `${described ? ` aria-describedby="${described}"` : ""}>` +
    `${nextPendingLabel(busyKey,
      confirming ? "Allow and analyze" : again ? "Analyze again" : "Analyze drift")}</button>`;
  /* The announcement and the description are one node while a refusal
     stands. Printing the stored message and the reason separately rendered
     the same sentence twice, adjacent and identical, where the contract is
     that it renders exactly once. The press is still announced, because this
     node carries `role="status"` when it is the refusal. */
  const refused = nextReadingRefusedLine(session, reason, request, board);
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
    /* The server's line when an Allow is on record that no longer covers
       where the words go, so the step says why it is asking again (owner,
       2026-10-02). Never composed here: only the store knows it was given. */
    const policy = nextData && nextData.reading;
    const rebind = policy && policy.rebind && typeof policy.rebind === "object"
      ? String(policy.rebind[provider] || "") : "";
    return (lead ? steers : "") +
      '<div class="next-cockpit-reading-consent" role="group" ' +
      'aria-labelledby="next-cockpit-reading-consent-title">' +
      '<h3 class="next-cockpit-reading-consent-title" id="next-cockpit-reading-consent-title" ' +
      `tabindex="-1" data-next-focus="reading:${esc(key)}">` +
      `${esc(`Send this session to ${label} for analysis?`)}</h3>` +
      (rebind ? `<p class="next-cockpit-reading-why">${esc(rebind)}</p>` : "") + disclosureParts +
      '<div class="next-cockpit-reading-ask">' +
      button.replace(`data-next-focus="reading:${esc(key)}"`, `data-next-focus="reading-allow:${esc(key)}" data-next-focus-fallback="reading:${esc(key)}"`) +
      '<button type="button" class="next-action" data-next-cockpit-action="reading-not-now" ' +
      `data-next-focus="reading-not-now:${esc(key)}" data-next-focus-fallback="reading:${esc(key)}"` +
      `${busy ? ' aria-disabled="true"' : ""}>Not now</button></div></div>` +
      changed + (lead ? "" : steers) +
      (off ? `<div class="next-cockpit-reading-ask">${off}</div>` : "") +
      accounts + counted + budget + aboutWhy;
  }
  /* Idle: the button and its count, the accounts and the one hint line, then
     the provider disclosure one click away under a worded summary that names
     the receiver until it is allowed, and always on a fallback route, whose
     receiver is a second provider that an Allow given on another harness's
     session lets a press reach at once (owner Q1, 2026-10-01; item 4 of the
     ruling linked below).
     Idle sends nothing: the press that would send either opens the consent
     step above or runs under an Allow given after these same words. The button stays
     described by the paragraph, which a closed summary still lets a screen
     reader read. Turn off readings sits inside it, still on the page, as item 1 of
     [DEC-21](docs/design-reading-a-session.md#dec-21-a-reading-works-the-first-time-you-ask)
     requires. */
  /* A popover, as the header's "Why" is (owner, 2026-10-02): the body is taken
     out of flow under its summary, which sits after Analyze, so opening it
     moves nothing and covers no control above it. */
  const label = provider ? String(route.label || provider) : "";
  const sent = disclosure
    ? `<details class="next-cockpit-why next-disclose--pop next-cockpit-reading-sent"` +
      `${nextCockpitDisclosureAttr("reading-sent")}>` +
      `<summary>${esc(route.fallback === true || nextReadingNeedsAllow(route)
        ? `What is sent to ${label}` : "What is sent")}` +
      `</summary><div class="next-disclose-body">${disclosureParts}` +
      (about ? `<p class="next-cockpit-reading-why">${esc(about)}</p>` : "") +
      (off ? `<div class="next-cockpit-reading-ask">${off}</div>` : "") + "</div></details>"
    : (off ? `<div class="next-cockpit-reading-ask">${off}</div>` : "") + aboutWhy;
  /* The count under the row rather than in it, so the buttons keep one row;
     not under an inert Analyze, which no press can spend (NU-9, 2026-10-02). */
  return '<div class="next-cockpit-reading-ask">' +
    (lead ? steerButton + button : button + steerButton) + '</div>' + changed +
    (inert ? "" : counted) + accounts + sent + budget;
}

/* The attempt count beside the control, as item 1 of
   [DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy)
   keeps it, worded the same in every state: short to the eye, and the whole
   sentence to a screen reader, which the short form is hidden from. */
function nextCockpitReadingCount(count){
  const short = `${count} model request${count === 1 ? "" : "s"}`;
  return '<p class="next-cockpit-reading-count">' +
    `<span aria-hidden="true">${esc(short)}</span>` +
    `<span class="next-visually-hidden">${esc(`${short} recorded for this session.`)}</span></p>`;
}

/* "Not now" on the consent step: nothing is sent, allowed or recorded, and
   the idle button comes back. The adoption the step held goes with it. */
function nextCockpitReadingNotNow(session){
  const key = sessKey(session);
  const request = nextCockpitReadingRequests.get(key);
  // Not while Allow is being answered: that press is already the consent.
  if(nextPendingHas(`reading-allow:${key}`)) return;
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
  "read a diff, a file, a test or a deliverable, replies from git, gh or connected tools, " +
  "or what you saw on your screen.";
/* The same scope without its opening clause, where the server's list is drawn
   just above it: that list already ends on "A reading is a model's account of
   the evidence", and saying it again in the next paragraph was the repetition
   verifier ui4 V2 found in the popover. */
const NEXT_READING_SCOPE =
  "What it reads is the evidence on this page: the observed record in this session\u2019s " +
  "activity and the goal and output you saved, and nothing else. It does not read a diff, a " +
  "file, a test or a deliverable, replies from git, gh or connected tools, or your screen.";

function nextCockpitReadingBaseline(shape, extra = ""){
  /* What the reading actually read, verbatim, rather than only which revision
     it was. Naming the revision says a reading is historical; it does not let
     the reader see what it said, and a reading of revision 1 sitting beside
     today's revision 3 invites them to assume the words on screen are the ones
     it read. The text was always on the wire as each criterion's clause.

     A disclosure rather than open prose: this is reference for a reader who
     doubts the reading, not part of it, and the block is long already. */
  if(shape.revisionRead == null){
    return extra ? `<details${nextCockpitDisclosureAttr("reading-baseline")}>` +
      `<summary>What it read</summary>${extra}</details>` : "";
  }
  /* One sentence either way. With no time it read "Revision 2, when it was
     typed was not recorded." (NU-13, 2026-10-02); adopted words were saved
     rather than typed, so their missing time is the save's. */
  const typed = shape.revisionReadAt != null
    ? `, ${shape.promptSource ? "saved" : "typed"} ${esc(fmtDur(Math.max(0, (nextData && nextData.generated || 0) - shape.revisionReadAt)))} ago`
    : ` (${shape.promptSource ? "save time" : "time"} not recorded)`;
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
  /* The summary is the worded tier-2 handle; the revision it read and when
     are the first line inside it, as a short summary should be
     ([NUI-19](docs/design-next-ui.md#nui-19-a-caveat-has-three-tiers); DRC-4758
     fix round). */
  return `<details${nextCockpitDisclosureAttr("reading-baseline")}>` +
    "<summary>What it read</summary>" +
    `<p class="next-cockpit-reading-why">Revision ${shape.revisionRead}${typed}${opened}.</p>` +
    extra + rows + "</details>";
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
    ? '<button type="button" class="next-action next-action--secondary" data-next-cockpit-action="update-intent" ' +
      `data-arg="${esc(nextCockpitOfferedDirection(annotation, entries, session, early))}" ` +
      `data-next-focus="update-intent:${esc(sessKey(session))}"` +
      `${nextPendingAttrs(`update-intent:${sessKey(session)}`)}>` +
      `${nextPendingLabel(`update-intent:${sessKey(session)}`, "Update intent instead")}</button>`
    : "";
  const slotted = offer ? {lead: departed,
    button: nextCockpitSteerButton(session,
      nextCockpitSteerPrimary(offer, Boolean(noReader), primary)) + update,
    box: nextCockpitSteerTrigger(offer,early,session,source.all || source.entries || [],
      nextCockpitEntryNumbers(session,source), source.scan) + nextCockpitSteerBox(session, source)} : null;
  /* Said once. The send disclosure already ends on the server's "never a
     verification that the work was done", so the page's own wording rides
     with what a reading is only where no disclosure was published. */
  const routed = nextReadingRoute(session);
  const about = raw ? "" : routed && routed.provider && routed.disclosure
    ? NEXT_READING_SCOPE : `${NEXT_READING_OFFER} ${NEXT_READING_NOT_A_VERIFICATION}`;
  const control = '<div class="next-session-drift-check">' +
    (question || nextCockpitReadingControl(session, annotation, model, primary && !departed, slotted,
      false, about)) +
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
    /* The section is drawn only for this: what a reading is now sits inside
       "What is sent" beside the control (DRC-4758 slice E). */
    const refused = annotation && annotation.reading_refused === true
      ? '<p class="next-cockpit-reading-why">A reading is stored for this session and this ' +
        "build could not read it, so nothing from it is shown. Asking again replaces it." +
        "</p>"
      : "";
    const drawn = refused ? close(refused, null, false) : close("", null, true);
    return refused ? drawn : {...drawn, reading: ""};
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
  /* The result in the button's place (owner Q3, 2026-10-01; DRC-4758 slice
     C): under the level, the stale callout if any, the headline, the goal row,
     the checklist against the expected outcome, where the work went, then the
     one press, "Analyze again" -- inert with its reason wherever "Analyze
     drift" would be -- beside Steer back, and Not accurate. "Analyze drift" is
     not drawn. While a job runs the box takes the slot alone, as the design's
     analyzing stage does; the question before the press keeps the slot's head
     and no press is drawn under it. */
  const job = nextReadingJob(session);
  const staleState = Boolean(nextCockpitResultStale(shape, raw, annotation, held, ""));
  const answer = shape.criteria.length || shape.departures.length
    ? nextCockpitResultAnswer(nextDriftAnswer(shape, held, source && source.scan), numbers, byId,
      shape.scope === "mid-flight") : "";
  const coverageLine = nextCockpitReadingCoverage(shape);
  const work = nextCockpitResultWork(held, numbers, source && source.scan, shape.windowStart);
  /* From the reading rather than from the live row. A reading describes the
     moment it was taken, and the producer already agreed with the HOW IT
     LANDED cards next door because both derive the ending the same way and
     a test asserts the two derivations match. */
  const arrived = nextReadingArrivedLine(annotation,held);
  const scope = shape.scopeText
    ? `<p class="next-cockpit-reading-why">${esc(shape.scopeText)}</p>` : "";
  const goal = shape.criteria.filter(row => row.key === "goal");
  const lines = shape.criteria.filter(row => nextReadingIsOutcomeLine(row.key));
  /* What the agent claimed, after the intent it is independent of (owner,
     2026-10-04), under its own heading. */
  const claimed = nextCockpitClaimsDrawn(shape);
  const checklist = goal.map(row => nextCockpitResultItem(row, numbers, byId, "div")).join("") +
    (lines.length
      ? '<div class="next-cockpit-result-checklist"><h3>Against expected outcome</h3>' +
        '<ol class="next-cockpit-result-lines">' +
        lines.map(row => nextCockpitResultItem(row, numbers, byId)).join("") + "</ol></div>"
      : "") +
    (claimed.length
      ? '<div class="next-cockpit-result-claims"><h3>What the agent claimed</h3>' +
        claimed.map(row => nextCockpitResultItem(row, numbers, byId, "div")).join("") + "</div>"
      : "");
  /* What it read, one click away: the definition, the model stamp, the
     baseline's source, the cutoff and the revision it read. */
  const read = `<p class="next-cockpit-define">${NEXT_COCKPIT_READING_DEFINITION}</p>` +
    `<p class="next-cockpit-reading-why">${esc(NEXT_READING_SCOPE)}</p>` +
    (shape.stamp ? `<p class="next-cockpit-reading-stamp">${esc(shape.stamp)}</p>` : "") +
    (shape.promptSource ? '<p class="next-cockpit-reading-why">Baseline from your prompt.</p>' : "") +
    scope + arrived +
    /* The cutoff was the departures section's, which no longer repeats the
       reading (owner Q9); "raised nothing" is worth only the evidence read. */
    (shape.cutoff ? `<p class="next-cockpit-reading-why">${esc(shape.cutoff)}</p>` : "");
  /* Stale, the callout holds the one "Analyze again" and Steer back keeps
     its own row below; otherwise the press sits beside Steer back at the
     foot. Never both (owner Q3). */
  const press = question ? "" : nextCockpitReadingControl(session, annotation, model,
    false, staleState ? null : slotted, true);
  const stale = nextCockpitResultStale(shape, raw, annotation, held, staleState ? press : "");
  const steers = staleState && slotted && !question
    ? `<div class="next-cockpit-reading-ask">${slotted.button}</div>${slotted.box}` : "";
  const foot = staleState ? steers : press;
  const result = job ? control
    : '<div class="next-session-drift-check next-cockpit-result" data-next-result>' +
      question + stale + answer + coverageLine + checklist + work +
      (foot ? `<div class="next-cockpit-result-press">${foot}</div>` : "") +
      nextCockpitResultFoot(session, annotation, raw) +
      nextCockpitReadingBaseline(shape, read) + '</div>';
  return {control: result,
    reading: "",
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
    /* The claim inline and its reason one click away (DRC-4758 slice E, tier 2
       of [NUI-19](docs/design-next-ui.md#nui-19-a-caveat-has-three-tiers)). */
    '</div><p class="next-cockpit-reading-why">Neither card implies the other.</p>' +
    nextCockpitWhy("landed-why", "Why two cards",
      "Evidence of an end and a claim of completion are separate questions.") + '</section>';
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
  /* Tier 2 (DRC-4758 slice E): the summary names the state, so an unread
     record is never a silent all-clear, and the sentences and the steer
     paragraph sit behind it. */
  const block = (state, body) => '<section class="next-cockpit-conflict">' +
    `<details class="next-cockpit-why"${nextCockpitDisclosureAttr("later-direction")}>` +
    `<summary>${esc(`Later directions: ${state}`)}</summary>${body}` +
    '<p class="next-cockpit-conflict-why">Nothing here decides whether it changes ' +
    'what you are asking for. That is yours, and Cargento does not write into the session ' +
    'either way.</p></details></section>';
  if(source.state !== "read" && source.state !== "empty"){
    return block("unknown (record unread)", '<p class="next-cockpit-conflict-why">' +
      `${esc(nextCockpitWorkAbsence(source))} So whether you have given a later direction is ` +
      'unknown, not none.</p>');
  }
  const pending = nextCockpitConflictCandidates(annotation, source.all || source.entries, session);
  const settledAt = nextNumber(annotation && annotation.settled_at);
  if(!pending.length){
    if(settledAt == null){
      return block("none", '<p class="next-cockpit-conflict-why">Nothing you ' +
        'have said since you saved these words is in the observed record read for this ' +
        'session.</p>');
    }
    const age = nextDurationSince(settledAt);
    const revision = nextNumber(annotation && annotation.settled_revision);
    return block(age == null ? "settled" : `settled ${age} ago`,
      '<p class="next-cockpit-conflict-settled">You settled this' +
      `${age == null ? "" : ` ${esc(age)} ago`}` +
      `${revision == null ? "" : `, against revision ${revision}`}. A direction given after ` +
      'that will raise it again.</p>');
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
async function nextCockpitKeepReadWhole(session, pending, revision, signal = null){
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
      const response = await nextFetchBounded("/api/direction", {method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({harness: session.harness, sid: session.sid, fact_id: id})}, signal);
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
  const earliest = nextDirectionSelected(session, pending);
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
    : draft.source === "first-prompt" ? "since your first prompt"
    : draft.source === NEXT_PROMPT_CHOSEN ? "since the prompt you chose" : "since your latest prompt";
  return `You gave ${pending.length} later directions ${since}, the selected direction` +
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
  /* The board's flip is tracked here too, ranked as the Analyze control
     ranks it, so an unsaved edit hides a change rather than faking one. */
  const board = nextReadingBoard(session, annotation, model,
    nextPromptReadingRefusal(session, annotation, model));
  const reason = edited ? nextIntentEditedRefusal(session) : board.reason;
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
  const earliest = nextDirectionSelected(session, pending);
  const described = edited ? NEXT_READING_REFUSED_ID : disclosure && analyze ? NEXT_READING_DISCLOSURE_ID : "";
  /* The fallback hands focus on once the question goes with a settle: to
     Analyze or Allow and analyze, or to a started job's title, which holds
     the same key (consent F7). */
  const keeping = nextPendingHas(`direction-keep:${key}`);
  const keep = `<button type="button" class="next-action${primary ? " next-action--primary" : ""}" ` +
    'data-next-cockpit-action="direction-keep" ' +
    `data-next-focus="direction-keep:${esc(key)}" data-next-focus-fallback="reading:${esc(key)}"` +
    `${keeping ? nextPendingAttrs(`direction-keep:${key}`)
      : edited || (request && request.pending) ? ' aria-disabled="true"' : ""}` +
    `${described ? ` aria-describedby="${described}"` : ""}>` +
    `${nextPendingLabel(`direction-keep:${key}`,
      analyze ? NEXT_COCKPIT_KEEP_ANALYZE : NEXT_COCKPIT_KEEP)}</button>`;
  const add = '<button type="button" class="next-action" data-next-cockpit-action="direction-add" ' +
    `data-arg="${esc(String(earliest.id || ""))}" data-next-focus="direction-add:${esc(key)}"` +
    `${nextPendingAttrs(`direction-add:${key}`)}>` +
    `${nextPendingLabel(`direction-add:${key}`, NEXT_COCKPIT_ADD_DIRECTION)}</button>`;
  const opened = nextCockpitDirectionLines.get(key);
  const count = nextNumber(annotation && annotation.reading_count) || 0;
  const running = nextSessionEndedAt(session) == null && session.state !== "idle";
  return (job ? nextReadingJobBox(job, key, running) : "") +
    '<div class="next-cockpit-direction-question" data-next-cockpit-direction-question>' +
    nextDirectionSelect(session, pending, numbers) +
    `<p class="next-cockpit-direction-said">${esc(nextCockpitDirectionSentence(
      session, annotation, pending, numbers))}</p>` +
    nextCockpitDirectionWholeList(key, pending, numbers) +
    /* The Drift card's own Turn off readings, busy state and all (verifier F2). */
    `<div class="next-cockpit-reading-ask">${keep}${add}${nextDirectionGoalButton(session, String(earliest.id || ""))}${nextReadingAnyConsent()
      ? '<button type="button" class="next-action" data-next-cockpit-action="reading-off" ' +
        `data-next-focus="reading-off:${esc(key)}"${nextPendingAttrs(`reading-off:${key}`)}>` +
        `${nextPendingLabel(`reading-off:${key}`, "Turn off readings")}</button>` : ""}</div>` +
    board.changed +
    (analyze ? disclosure : "") +
    (opened && opened.error
      ? `<p class="next-cockpit-reading-why" role="status">${esc(opened.error)}</p>` : "") +
    (answered ? `<p class="next-cockpit-reading-why"${request && request.announced ? ""
      : ' role="status"'}>${esc(answered)}</p>` : "") +
    (annotation ? nextCockpitReadingCount(count) : "") + nextReadingBudgetLine() +
    nextReadingRefusedLine(session, reason, request,
      edited ? {settling: false, inert: false, pressed: null} : board) +
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
  const control = `direction-keep:${key}`;
  if(nextPendingHas(control) || nextCockpitReadingRequests.get(key)?.pending) return;
  const annotation = nextCockpitAnnotation(session);
  const group = nextCockpitRouteGroup();
  const pending = nextCockpitDirectionsOpen(session, annotation,
    group ? nextCockpitWorkSource(group, session) : null);
  if(!pending.length) return;
  nextCockpitKeepUnsay(key);
  if(nextIntentUnsaved(session, annotation)){
    const edited = nextIntentEditedRefusal(session);
    nextCockpitReadingRequests.set(key,
      {pending: false, message: edited, refusal: true, announced: true});
    nextCockpitAnnounceCue(`keep:${key}`, edited, false);
    renderNext();
    return;
  }
  const draft = nextIntentDraft(session, annotation);
  const reason = nextPromptReadingRefusal(session, annotation, model);
  // A press during a held close learns the board's state, as Analyze's does.
  if(reason && reason === nextReadingPressRefusal(session)) nextReadingFlipAcknowledge(session, false);
  const route = nextReadingRoute(session);
  const owed = !reason && !nextReadingJob(session) && nextReadingNeedsAllow(route);
  const analyze = !reason && !nextReadingJob(session) && !owed;
  const through = nextNumber(pending[pending.length - 1].at);
  const adoption = nextIntentAdoption(draft);
  const drawnAt = nextNumber(annotation && annotation.revision) || 0;
  const press = nextPendingStart(control, "Keeping\u2026", "Keeping your intent.");
  if(!press) return;
  const request = {pending: true, message: "", adoption, announced: true};
  nextCockpitReadingRequests.set(key, request);
  renderNext({named: control});
  try{
    const read = await nextCockpitKeepReadWhole(session, pending, drawnAt, press.signal);
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
      const response = await nextFetchBounded("/api/annotate", {method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({harness: session.harness, sid: session.sid, ...adoption,
          settle_through: through, expected_revision: expected})}, press.signal);
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
           is saved now, so that press finds nothing to adopt. */
        if(owed) request.consent = true;
      }
      await refreshNext();
      return;
    }
    const provider = String(route.provider);
    const response = await nextFetchBounded("/api/reading", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({harness: session.harness, sid: session.sid, provider,
        press: true, observer_model: 1, ...adoption, settle_through: through,
        expected_revision: expected})}, press.signal);
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
    nextPendingEnd(control, press);
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
  /* Tier 2 (DRC-4758 slice E): the offer, its why and the armed warning sit
     behind "Discard everything"; the account of a discard stays in view.
     Armed, it is drawn open and outside the restore lane, so a redraw cannot
     shut the warning that describes the armed control. */
  const opening = armed
    ? '<details class="next-cockpit-why next-cockpit-held-discard-offer" open>'
    : `<details class="next-cockpit-why next-cockpit-held-discard-offer"` +
      `${nextCockpitDisclosureAttr("held-discard")}>`;
  return '<div class="next-cockpit-held-discard">' +
    (offer ? `${opening}<summary>Discard everything</summary>` : "") +
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
        nextPendingAttrs(key) +
        (warning ? ' aria-describedby="next-cockpit-discard-armed"' : "") + ">" +
        `${nextPendingLabel(key, armed ? "Confirm discard" : "Discard everything")}</button>`
      : "") +
    (offer && warning
      ? '<p class="next-cockpit-held-absent" id="next-cockpit-discard-armed">' +
        `${esc(warning)}</p>` : "") +
    (offer ? "</details>" : "") +
    (landed ? `<small class="next-cockpit-held-cue">${esc(landed)}</small>` : "") +
    '</div>';
}

/* Under the Drift heading, verbatim from the design. It names what the
   section measures and asserts no result. */
const NEXT_DRIFT_SUBTITLE = "How far the session has moved from the goal";
/* Item 14 of
   [DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy),
   as its own sentence. */
const NEXT_DRIFT_HARNESS_LIMIT = "Cargento can't read work or the agent's replies from this harness.";

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
const NEXT_DRIFT_LIVE_HINT = "Shows a level after every turn, from checks and file paths, " +
  "with no model call. The level shows here and in the header.";
const NEXT_DRIFT_LIVE_SAVE = "Save your intent to see a live estimate.";
const NEXT_DRIFT_UNCHECKED = "Not checked yet";
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
function nextDriftSignalAnchored(row, work){
  const entries=work.all || work.entries || [];
  const times=entries.filter(entry => entry.type === "user_message")
    .map(entry => nextNumber(entry.at)).filter(at => at > 0);
  if(work.scan && nextNumber(work.scan.last_user_at) > 0) times.push(nextNumber(work.scan.last_user_at));
  if(!times.length) return false;
  const anchor=Math.max(...times);
  return entries.some(entry => (row.cites || []).includes(String(entry.id || "")) &&
    nextReadingEvidenceAt(entry) > anchor);
}

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
  const work = nextCockpitWorkSource(group, session);
  const numbers = nextCockpitEntryNumbers(session, work);
  const n = numbers.get(String(row.rose_at || ""));
  const from = NEXT_DRIFT_LEVEL_NAMES[String(row.rose_from || "")];
  return {level, label, source: at != null ? `Live estimate · ${nextSessionClock(at)}` : "Live estimate",
    rose: from && n != null && row.rose_from !== "not_enough" ? `Rose from ${from} at #${n}.` : "",
    anchored: nextDriftSignalAnchored(row,work),
    reasons: nextDriftReasons(level, row.reasons, row.cites, work.all || work.entries || [],
      numbers, new Set())};
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

/* Whether every row of the intent stands consistent on what it names. The
   intent's rows only: the claims row is not the intent, and holding it to a
   consistent made None or low unreachable (review, PR C). */
function nextDriftAnalysisShown(shape){
  const intent = shape.criteria.filter(line => line.key !== NEXT_READING_CLAIMS);
  return intent.length > 0 && intent.every(line =>
    line.result === NEXT_READING_CONSISTENT && line.restsOn) &&
    !shape.criteria.some(line => line.key === NEXT_READING_CLAIMS &&
      line.result === NEXT_READING_UNSUPPORTED);
}

function nextDriftAnalysis(group, session, annotation, shape){
  const raw = annotation && annotation.assessment;
  if(!raw || !shape || shape.malformed || annotation.not_accurate === true) return null;
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
  if(level === "none_or_low" && !nextDriftAnalysisShown(shape)) level = "not_enough";
  const clock = nextSessionClock(readAt);
  /* The time is said once, in the ruled line; the source chip names the
     source alone and the caption carries the range alone (DRC-4758 slice C). */
  const source = nextCockpitWorkSource(group, session);
  const numbers = nextCockpitEntryNumbers(session, source);
  const held = source.all || source.entries || [];
  return {level, label: NEXT_DRIFT_LEVEL_NAMES[level], source: "Analysis",
    line: `Analysis at ${clock} · intent against cited checks and messages.`, analysis: true, rose: "",
    range: nextDriftRange(held, numbers, nextNumber(raw.window_start),
      nextNumber(raw.evidence_through) ?? readAt),
    reasons: nextDriftReasons(level, row.reasons, row.cites, held, numbers,
      new Set(shape.criteria.filter(line => line.result === NEXT_READING_DEPARTURE &&
        line.key !== NEXT_READING_CLAIMS).flatMap(line => line.citedIds || []).map(String)))};
}

/* "#a to #b": the first and last entries the activity list numbers inside
   the window the reading read, "#a" alone when they are one entry, and
   nothing when the list numbers none of them: "#n", never "turn n", as item 11 of
   [DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy)
   rules. */
function nextDriftRange(entries, numbers, start, through){
  const inside = (entries || []).map(entry => {
    const at = nextNumber(entry && entry.at);
    const n = numbers.get(String(entry && entry.id || ""));
    return n != null && at != null && (start == null || at >= start) &&
      (through == null || at <= through) ? n : null;
  }).filter(n => n != null);
  if(!inside.length) return "";
  const first = Math.min(...inside), last = Math.max(...inside);
  return first === last ? `#${first}` : `#${first} to #${last}`;
}

/* Why a level is what it is, one page-owned sentence per closed token from
   `levels.REASONS` (a test walks the set, and each token has exactly one
   home). A reason the level rests on reads first under the meter; what
   holds a level back from None or low reads behind "Why not None or low".
   A later direction is said as yours and unsettled, never as drift
   ([DEC-16](docs/design-reading-a-session.md#dec-16-cargento-does-not-write-into-a-session)).
   An unknown token renders nothing: no producer text reaches the page
   through this field. */
const NEXT_DRIFT_REASON_LINES = {
  "failed-check": n => n ? `A check failed at ${n}.` : "A check failed.",
  "departure": n => n ? `The session departed from your intent at ${n}.`
    : "The session departed from your intent.",
  "pass-then-write": () => "A check passed, then files were written after it.",
  "claim-contradicted": n => n ? `The record contradicts what the agent said at ${n}.`
    : "The record contradicts what the agent said.",
  "claim-not-shown": n => n ? `The record read does not show what the agent said at ${n}.`
    : "The record read does not show what the agent said.",
  "writes-outside-folders": () => "Some files were written outside the folders your intent names.",
  "most-writes-outside-folders": () =>
    "Most files were written outside the folders your intent names.",
};
const NEXT_DRIFT_BLOCKER_LINES = {
  "no-passing-check": "No check has passed yet.",
  "check-not-recorded": "A check ran and its result was not recorded.",
  "background-run": "A check ran in the background, so its result is not known.",
  "command-after-pass": "A command that can change files ran after the last pass.",
  "pass-older-than-read": "The last pass is older than the work it would show.",
  "later-direction": "A later direction of yours is unsettled.",
  "entries-not-listed": "Some written files were counted and not listed.",
  "intent-names-no-folder": "Your intent names no folder, so where files went is not weighed.",
  "scan-incomplete": "The record was not read in full.",
  "line-not-shown-by-a-check": "A line of your intent is not shown by any check.",
  "no-outcome-line": "No expected outcome line was saved.",
  "reading-malformed": "Part of the stored analysis could not be read.",
};
const NEXT_DRIFT_REASON_SILENT = new Set(["floor-met", "no-reading", "draft-unsaved"]);

function nextDriftReasons(level, tokens, cites, entries, numbers, departing){
  const said = Array.isArray(tokens) ? tokens.map(String) : [];
  const cited = (Array.isArray(cites) ? cites : []).map(String);
  const byId = new Map((entries || []).map(entry => [String(entry && entry.id || ""), entry]));
  const number = test => {
    const id = cited.find(fid => numbers.has(fid) && test(byId.get(fid), fid));
    return id ? `#${numbers.get(id)}` : "";
  };
  const failureLine = () => {
    const fid = cited.find(id => byId.get(id) && byId.get(id).subject === "check" && byId.get(id).result === "failed");
    const fact = byId.get(fid);
    if(!fact) return "A failed check is counted but its entry is not listed.";
    const at = nextReadingEvidenceAt(fact);
    const age = at > 0 ? `${fmtDur(Math.max(0,(nextData && nextData.generated || 0)-at))} ago` : "time not recorded";
    const n = numbers.get(fid);
    return `${String(fact.title || fact.summary || "A check")} failed ${age}${n != null ? ` at #${n}` : ""}${fact.beforeLastChange ? "; files changed after it" : "; no passing re-run recorded"}.`;
  };
  const finders = {
    "failed-check": entry => entry && entry.subject === "check" && entry.result === "failed",
    "departure": (_entry, fid) => departing.has(fid),
    "claim-contradicted": entry => nextReadingAgentMessage(entry),
    "claim-not-shown": entry => nextReadingAgentMessage(entry),
  };
  if(level === "not_enough"){
    const held = said.filter(token => token !== "intent-names-no-folder").map(token => token === "failed-check" ? failureLine() : NEXT_DRIFT_BLOCKER_LINES[token] ||
      (NEXT_DRIFT_REASON_LINES[token] ? NEXT_DRIFT_REASON_LINES[token]("") : "")).filter(Boolean);
    return {first: "", blockers: [...new Set(held)]};
  }
  const token = said.find(name => NEXT_DRIFT_REASON_LINES[name]);
  const finder = token && finders[token];
  return {first: token === "failed-check" ? failureLine() : token ? NEXT_DRIFT_REASON_LINES[token](finder ? number(finder) : "") : "",
    blockers: []};
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

/* The four labels under the meter's segments, the current one marked, as
   the design draws them. Hidden from a screen reader, which has the level
   word already and would otherwise hear all four after it. */
function nextDriftScale(level){
  return '<p class="next-session-drift-scale" aria-hidden="true">' +
    NEXT_DRIFT_SCALE.map(name => `<span${name === level ? " data-current" : ""}>` +
      `${esc(NEXT_DRIFT_LEVEL_NAMES[name])}</span>`).join("") + "</p>";
}

/* A reading is stored once one was spent, including one this build refused
   to read: the validator nulls a refused assessment, so the assessment alone
   would call a checked session unchecked (DRC-4758 fix round, INT-4). */
function nextDriftReadingStored(annotation){
  return Boolean(annotation && (annotation.assessment || annotation.reading_refused === true ||
    (nextNumber(annotation.reading_count) || 0) > 0));
}

/* "Not checked yet" (owner Q2, 2026-10-01): a saved intent, no level from
   any source, and no reading stored. It names a process state, never "no
   drift", and the pill stays level-only. */
function nextDriftUnchecked(session, annotation){
  if(!(nextData && nextData.annotate === true) || !annotation || nextDriftReadingStored(annotation)) return false;
  return Boolean(String(annotation.goal || "").trim() || nextAnnotationLines(annotation).length);
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
    const measured = estimate === undefined ? nextDriftEstimate(group, session) : estimate;
    const found = analysis && analysis.level !== "not_enough" ? analysis : measured || analysis;
    const drafted = nextIntentDrafted(session, annotation);
    const live = NEXT_LIVE_HARNESSES.has(harness) && nextLiveMonitorOn(session) && !analysis;
    if(live && (drafted || found && found.save)){
      return `<p class="next-session-drift-limit" data-next-drift-save>${esc(NEXT_DRIFT_LIVE_SAVE)}</p>`;
    }
    /* The design's rows: the hint (where the switch can be turned on and no
       reading is stored), then the level block, then the control slot the
       drift block appends. */
    const hint = NEXT_LIVE_HARNESSES.has(harness) && nextData && nextData.annotate === true &&
      !live && !nextDriftReadingStored(annotation)
      ? `<p class="next-session-drift-hint">${esc(NEXT_DRIFT_LIVE_HINT)}</p>` : "";
    const running = Boolean(nextReadingJob(session));
    if(drafted || !found || !found.label){
      if(drafted || !nextDriftUnchecked(session, annotation)) return hint;
      return hint + '<div class="next-session-drift-live" data-next-drift-unchecked>' +
        '<p class="next-session-drift-live-head">' +
        `<span class="next-session-drift-level">${esc(NEXT_DRIFT_UNCHECKED)}</span></p>` +
        `<p class="next-session-drift-meter" aria-hidden="true"${running ? " data-dim" : ""}>` +
        `${nextDriftMeter("")}</p>${nextDriftScale("")}</div>`;
    }
    const high = found.level === "high" || found.level === "extreme";
    /* While an analysis runs the design keeps the title and dims the meter,
       and drops the detail line. Over an unsaved edit the nudge would point at
       a press the page refuses, so it goes; the level is over the saved words. */
    const detail = found.level && !running
      ? [found.analysis ? found.line : NEXT_DRIFT_LIVE_LINE, found.rose].filter(Boolean).join(" ")
      : "";
    const reasons = !running && found.reasons ? found.reasons : {first: "", blockers: []};
    const blockers = reasons.blockers.length
      ? `<details class="next-cockpit-why"${nextCockpitDisclosureAttr("drift-why-not-low")}>` +
        "<summary>Why not None or low</summary>" +
        reasons.blockers.map(line => `<p class="next-cockpit-reading-why">${esc(line)}</p>`).join("") +
        "</details>" : "";
    return hint + '<div class="next-session-drift-live" data-next-drift-level>' +
      '<p class="next-session-drift-live-head">' +
      `<span class="next-session-drift-level">${esc(String(found.label))}</span>` +
      (found.source ? `<span class="next-session-drift-source">${esc(found.source)}</span>` : "") +
      '</p>' +
      (found.level ? `<p class="next-session-drift-meter" aria-hidden="true"${running ? " data-dim" : ""}>` +
        `${nextDriftMeter(found.level)}</p>${nextDriftScale(found.level)}` : "") +
      (detail ? `<p class="next-session-drift-detail">${esc(detail)}</p>` : "") +
      (found.range && !running ? `<p class="next-session-drift-range">${esc(found.range)}</p>` : "") +
      (reasons.first ? `<p class="next-session-drift-reason">${esc(reasons.first)}</p>` : "") +
      blockers + '</div>' +
      /* The design's C2 callout, placed definitely: directly under the live
         level at High or Extreme, before the control it points at. */
      (high && found.anchored === true && !found.analysis && !running && !nextIntentUnsaved(session, annotation)
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
  const shown = analysis && analysis.level !== "not_enough" ? analysis : estimate || analysis;
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
  /* The discard stamp stays in view, since it is the only sentence about a
     landed deletion (DRC-4565). A saved revision is a "Saved" summary whose
     details hold the revision line, what a revision is and the store key
     (plan slice D, critic 13): the reference draws none of the three, and
     an unsaved session draws nothing here at all (DRC-4758 fix round). */
  const discardStamp = nextAnnotationDiscardStamp(annotation);
  const revisionLine = discardStamp ? "" : nextProjectRevisionLine(annotation);
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
  /* The design's own line, "Drift is measured against these...", is the
     footer's hint under both fields now (owner Q6), so it is said once
     whether or not the goal is drafted. */
  const drafted = nextIntentDrafted(session, annotation);
  /* Tier 2 under its summary (DRC-4758 slice E): it says what the press does,
     which the button and its result already show. */
  const lede = '<details class="next-cockpit-why next-session-drift-about"' +
    `${nextCockpitDisclosureAttr("held-lede")}><summary>What analysis does</summary>` +
    '<p class="next-cockpit-held-lede">Choose a goal or use your prompt, then analyze drift: ' +
    'Cargento lists where this session departed from it. It never writes into the session, ' +
    'so steering stays yours.</p></details>';
  /* In the lede's slot, so it costs the fold no row a draft would not. */
  const why = drafted ? "" : nextIntentNoDraftWhy(session, annotation);
  const noDraft = why
    ? `<p class="next-cockpit-held-lede" data-next-intent-no-draft>${esc(why)}</p>` : "";
  /* "Saved", without the design's check mark: a check in this panel reads as
     a verdict (owner, DRC-4682), and the design's "Confirmed" claimed what
     nothing did, since a saved revision is the reader's own words (owner,
     2026-10-01, critic 13). The store key is in its details because the
     reader may need whose words these are, and the page's title already
     names the session. */
  const saved = revisionLine
    ? '<details class="next-cockpit-why next-cockpit-held-stamp"' +
      `${nextCockpitDisclosureAttr("held-stamp")}><summary>Saved${nextNumber(annotation.window_start) > 0
        ? ` · reads from ${esc(nextSessionClock(annotation.window_start))}` : ""}</summary>` +
      '<p>Adding a line keeps this window; saving new goal words opens another.</p>' +
      `<span class="next-cockpit-held-revision">${esc(revisionLine)}</span>` +
      `<span class="next-cockpit-define">${NEXT_COCKPIT_REVISION_DEFINITION}</span>` +
      `<span class="next-cockpit-held-bound">${esc(sessKey(session))}</span></details>` : "";
  const intent = '<section class="next-cockpit-held">' +
    '<header><h2 id="next-session-intent-heading" tabindex="-1" ' +
    `data-next-focus="${esc(nextCockpitIntentHeadingKey(session))}">Intent</h2></header>` +
    /* Under the heading rather than in its header, so the revision line keeps
       the sentence tier (DRC-4587). */
    saved +
    (drafted ? "" : noDraft) +
    (nextCockpitStoreUnreadable()
      ? `<p class="next-cockpit-held-absent">${esc(nextCockpitStoreUnreadable())}</p>` : "") +
    (discardStamp ? '<div class="next-cockpit-held-stamp">' +
      `<span class="next-cockpit-held-revision">${esc(discardStamp)}</span></div>` : "") +
    '<div class="next-cockpit-held-fields">' +
    NEXT_COCKPIT_HELD_FIELDS.map(spec =>
      nextCockpitHeldField(session, annotation, spec, cap)).join("") +
    nextCockpitHeldLines(session, annotation, cap, workSource) + '</div>' +
    nextCockpitIntentFooter(session, annotation) +
    '</section>';
  const reading = nextCockpitReadingParts(session, annotation, entries,
    nextCockpitObserverModel(group, session), observed, unsettled, workSource, primary);
  /* Below the reading, not between the fields and the control: none of these
     is the next thing to do, and above the control they pushed it off the
     first screen. */
  const discard = nextCockpitHeldDiscardBlock(session, annotation);
  /* The ended note and the binding stay in the DOM but behind one summary: they
     were the last always-visible paragraphs at the foot of the card in the
     owner's walk (DRC-4758), and neither is the next thing to do. The discard
     account stays in view, because it says what became of the reader's words. */
  const about = ended || binding
    ? '<details class="next-cockpit-why next-session-drift-saved-about"' +
      `${nextCockpitDisclosureAttr("held-saved-about")}><summary>About these saved words` +
      `</summary>${ended}${binding}</details>` : "";
  const caveats = about || discarded || discard
    ? `<div class="next-session-drift-caveats">${about}${discarded}${discard}</div>` : "";
  /* The saved introduction took 69.75px above the fields and put Analyze at
     892.5–936.5 with three lines and High on a 1440x900 board (DRC-4748).
     Keep its words below the action; the first-prompt draft's guide stays
     with the fields the reader is being asked to choose. Under a stored
     reading it is not drawn at all: it explains a step already done (NU-10,
     2026-10-02). */
  const savedIntroduction = drafted || nextDriftReadingStored(annotation) ? "" : lede;
  const delegated = nextDelegatedWork(session);
  const delegatedLine = delegated.draw ? `<p data-next-delegated-work>${esc(delegated.text)}</p>` +
    (delegated.risky ? '<p data-next-delegated-check>Is the work this session launched still running? Show its process and latest output.</p>' : "") : "";
  const panel = open + intent + head + reading.control + savedIntroduction + delegatedLine + reading.reading +
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
  /* A press in flight, or a running job, is the answer to a second press:
     nothing is sent. */
  if(nextPendingHas(`reading:${key}`) || nextPendingHas(`reading-allow:${key}`) ||
    nextCockpitReadingRequests.get(key)?.pending || nextReadingJob(session)) return;
  /* Keep's "Press Allow and analyze" is answered by this press, so the region
     stops holding it. Emptying a region is silent. */
  nextCockpitKeepUnsay(key);
  /* This press arrives from states the browser used to swallow, and an
     ungated one spends the reader's own model capacity from a state the page
     calls unavailable. Answered rather than dropped, because a clicked control
     that goes silent is indistinguishable from a dead one. */
  const refusal = nextPromptReadingRefusal(session, nextCockpitAnnotation(session), model);
  if(refusal){
    // A press during a held close learns the board's state; the card shows it now.
    if(refusal === nextReadingPressRefusal(session)) nextReadingFlipAcknowledge(session, false);
    nextCockpitReadingRequests.set(key, {pending: false, message: refusal, refusal: true});
    renderNext();
    return;
  }
  /* The provider the page named, sent with the press so the server can
     refuse one whose receiver changed since. A refusal above already covers
     a route with no provider. */
  const route = nextReadingRoute(session);
  const provider = String(route.provider);
  /* The destinations the disclosure named, sent with an Allow so the server
     can refuse one given about an endpoint that has since moved: where tool
     output goes, and where the words go, which the Allow is bound to (owner,
     2026-10-02). "" is sent as itself, since an unnamed one is its own value. */
  const destination = String(route.destination || "");
  const wordsTo = String(route.words_destination || "");
  if(nextReadingNeedsAllow(route) && !allow){
    nextCockpitReadingRequests.set(key, {consent:true, adoption:nextImplicitAdoption(session),
      chosen:nextIntentChosenPrompts.get(nextCockpitHeldKey(session, "goal")) || null});
    renderNext();
    return;
  }
  /* Pending only until the server answers with its job, which it does before
     the model runs (DRC-4686); from then on the job is the state, published
     over the push, so it survives a reload the way this map never could. */
  /* Allow sends the prompt the card was opened over, so a record that moved
     underneath is refused by the server rather than read unseen. A choice the
     reader made or undid while the card was up is theirs, so it is what the
     box holds now that Allow sends (DRC-4758 fix round, INT-1). */
  const confirmation = nextCockpitReadingRequests.get(key);
  const chosenNow = nextIntentChosenPrompts.get(nextCockpitHeldKey(session, "goal")) || null;
  const adoption = allow && confirmation && confirmation.consent && confirmation.adoption &&
    confirmation.chosen === chosenNow ? confirmation.adoption : nextImplicitAdoption(session);
  /* The revision this panel drew, so a press from a page another tab has
     since moved on is refused before anything starts (DRC-4732): the model
     would otherwise read words this reader never saw. */
  const expected = nextNumber(nextCockpitAnnotation(session)?.revision) || 0;
  const control = allow ? `reading-allow:${key}` : `reading:${key}`;
  const press = nextPendingStart(control, "Starting\u2026", "Starting the analysis.");
  if(!press) return;
  const request = {pending: true, message: "", adoption, chosen: chosenNow};
  nextCockpitReadingRequests.set(key, request);
  renderNext({named: control});
  try{
    const response = await nextFetchBounded("/api/reading", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({harness: session.harness, sid: session.sid, provider,
        press: true, observer_model: 1, ...adoption, expected_revision: expected,
        ...(allow ? {allow:true, words_destination:wordsTo,
          ...(destination ? {tool_output:destination} : {})} : {})}),
    }, press.signal);
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
      nextPendingEnd(control, press);
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
      nextReadingFlipAcknowledge(session, false);
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
      nextData.reading.words = {...(nextData.reading.words || {}), [provider]: true};
      const rebind = {...(nextData.reading.rebind || {})};
      delete rebind[provider];
      nextData.reading.rebind = rebind;
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
      // The box is the answer from here on, so the press stops being busy.
      nextPendingEnd(control, press);
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
    request.consent = false;
  }finally{
    request.pending = false;
    nextPendingEnd(control, press);
    renderNext({named: `reading:${key}`});
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
  const control = `reading-cancel:${key}`;
  const press = nextPendingStart(control, "Cancelling\u2026", "Cancelling the analysis.");
  if(!press) return;
  const cancel = {job: job.id, pending: true, failed: false};
  nextCockpitReadingCancels.set(key, cancel);
  renderNext({named: control});
  try{
    const response = await nextFetchBounded("/api/reading/cancel", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({harness: session.harness, sid: session.sid, job: job.id,
        press: true, observer_model: 1}),
    }, press.signal);
    const answer = response && typeof response.json === "function"
      ? await response.json().catch(() => null) : null;
    if(response && response.status === 409 && answer && answer.reason === "not-running"){
      nextPendingEnd(control, press);
      nextCockpitReadingCancels.delete(key);
      await refreshNext();
      return;
    }
    if(!response || response.status !== 202 || !answer || answer.cancelling !== true){
      throw new Error("cancel not confirmed");
    }
    // Accepted: the published `cancelling` draws the finishing state from here.
    nextPendingEnd(control, press);
    nextReadingJobShown(session, {...job, cancelling: true});
    nextCockpitReadingCancels.delete(key);
    await refreshNext();
  }catch(_error){
    cancel.failed = true;
  }finally{
    cancel.pending = false;
    nextPendingEnd(control, press);
    renderNext({named: control});
  }
}

async function nextCockpitReadingOff(){
  const viewing = nextSessionFind(nextRoute.project, nextRoute.harness, nextRoute.session);
  const control = viewing ? `reading-off:${sessKey(viewing)}` : "reading-off";
  const press = nextPendingStart(control, "Turning off\u2026", "Turning off readings.");
  if(!press) return;
  renderNext({named: control});
  try{
    const response = await nextFetchBounded("/api/reading", {method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({consent:"off",press:true,observer_model:1})}, press.signal);
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
  }finally{
    nextPendingEnd(control, press);
    renderNext({named: control});
  }
}

/* The endpoint's whole-annotation arm, reached from the second press.

   Shaped on `nextCockpitIntentSave` and deliberately not sharing its cue table:
   "Saved as a new revision." over a deletion, and "...they are still in the
   box" for an act with no box, are both DRC-4543's defect re-shipped. The
   sentences come from the payload instead, so the one that claims the
   departure store no longer quotes these words is written where that store
   can be tested. */
async function nextCockpitDiscardAnnotation(session){
  const key = nextCockpitHeldKey(session, "discard");
  const press = nextPendingStart(key, "Discarding\u2026", "Discarding.");
  if(!press) return;
  renderNext({named: key});
  try{
    let response;
    let answer;
    try{
      response = await nextFetchBounded("/api/annotate", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({harness: session.harness, sid: session.sid, clear: true}),
      }, press.signal);
      answer = response && response.ok ? await response.json() : null;
    }catch(_error){
      /* No answer: disarmed, said as unknown, and never re-armed on its own,
         so a second press is the reader's after the refresh shows what
         stands. */
      nextCockpitHeldMark(key, "discard-unconfirmed");
      await refreshNext();
      return;
    }
    if(!response || !response.ok) throw new Error(`HTTP ${response && response.status}`);
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
  }finally{
    nextPendingEnd(key, press);
    renderNext({named: key});
  }
}

/* Save intent: both fields in one write (owner Q6, 2026-10-01). The typed arm
   of `/api/annotate` takes `goal` and `lines` together, an absent or null
   field being "leave this one alone", so the press sends only what changed and
   a stale draft of one field cannot overwrite a save of the other. One request
   rather than two chained ones, so there is one revision and one outcome to
   report.

   With the revision both boxes were drawn against, so a save from a tab
   another tab has moved on is refused and the typed words stay in the boxes
   (DRC-4732) rather than replacing words this reader never saw. The store
   gives each line its source; the page never sends one, only the stored
   position each posted line came from. */
async function nextCockpitIntentSave(session){
  const key = nextCockpitIntentKey(session);
  const control = `${key}:save`;
  /* The same reckoning the footer decides `shown` with, so the control and
     the gate cannot disagree. Without it an inert-but-reachable control mints
     a revision identical to the stored one. An inert press starts nothing. */
  const changes = nextCockpitIntentChanges(session, nextCockpitAnnotation(session));
  if(nextDirectionLinesQuestion(session) || (!changes.any && !changes.chosen && !changes.adoptable)) return;
  const press = nextPendingStart(control, "Saving\u2026", "Saving your intent.");
  if(!press) return;
  renderNext({named: control});
  let said = null;
  try{
    said = await nextCockpitIntentSaveWork(session, press.signal);
  }finally{
    nextPendingEnd(control, press);
    renderNext({named: control});
    /* The outcome is said once it is drawn, never before the paint that shows
       it (owner, 2026-10-02). */
    if(said) nextCockpitHeldSay(key, said);
  }
}

/* The save itself, under the press's one pending entry: a choice chains its
   adoption and then the lines, and neither takes a guard of its own. Returns
   the cue kind it stamped, for the caller to say after the paint, or null. */
async function nextCockpitIntentSaveWork(session, signal){
  const annotation = nextCockpitAnnotation(session);
  const linesKey = nextCockpitHeldKey(session, "lines");
  const key = nextCockpitIntentKey(session);
  const changes = nextCockpitIntentChanges(session, annotation);
  if(changes.chosen || changes.pending){
    /* The choice first, as its own adoption naming the saved revision, then
       the lines against the revision that adoption minted: `/api/annotate`
       takes an adoption or typed words in one request, not both. */
    const adopted = await nextAdoptPrompt(session, NEXT_PROMPT_CHOSEN, signal);
    if(adopted === true && changes.lines){
      /* The refresh after the adoption replaced the rows, so the revision it
         minted is on the fresh row, not the one this press was handed. The
         held lines are keyed by session, so the fresh row still finds them. */
      const fresh = (nextData && nextData.sessions || [])
        .find(row => sessKey(row) === sessKey(session)) || session;
      return nextCockpitIntentSaveWork(fresh, signal);
    }
    if(adopted === true) nextCockpitHeldMark(key,"saved",{say:false});
    return adopted === true ? "saved" : adopted === "unconfirmed" ? "unconfirmed" : null;
  }
  if(!changes.any){
    /* The goal back at the draft adopts it, never a typed save of an excerpt
       (DRC-4682). */
    const drafted = nextIntentDraft(session, annotation);
    if(drafted && changes.typed === drafted.text){
      const adopted = await nextAdoptPrompt(session, drafted.source, signal);
      return adopted === "unconfirmed" ? "unconfirmed" : null;
    }
    return null;
  }
  const body = {harness: session.harness, sid: session.sid};
  if(changes.goal) body.goal = changes.typed;
  else if(changes.lines) body.goal = null;
  let sentLines = null;
  if(changes.lines){
    const draft = nextCockpitLinesDraft(session, annotation);
    const from = nextCockpitLinesOrigins(linesKey, draft);
    sentLines = nextCockpitLinesToSend(draft);
    body.lines = sentLines;
    body.origins = draft.map((text, index) => [text, from[index]])
      .filter(([text]) => String(text || "").trim()).map(([_text, origin]) => origin);
  }
  body.expected_revision = nextNumber(annotation && annotation.revision) || 0;
  let response;
  let saved;
  try{
    response = await nextFetchBounded("/api/annotate", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    }, signal);
    saved = response && response.ok ? await response.json() : null;
  }catch(_error){
    /* No answer, an abort at the bound, or a reply that could not be read:
       the save may or may not have landed, so the page says it cannot tell,
       and the drafts stay. Then it looks: a refresh whose row carries a newer
       revision holding exactly what was sent was this save. */
    nextCockpitHeldMark(key, "unconfirmed", {say:false});
    await refreshNext();
    if(nextCockpitIntentLanded(session, body, sentLines)){
      nextCockpitIntentForgetSent(session, changes, body, sentLines);
      nextCockpitHeldMark(key, "saved", {say:false});
      return "saved";
    }
    return "unconfirmed";
  }
  // `ok`, which is what `/api/annotate` answers with. `persisted` beside it
  // is whether the write reached disk, and a false there is not a failed
  // save: the words are held for this run and the store says so itself.
  if(!saved || saved.ok !== true){
    // The drafts stay. Losing what someone typed to report a failure is the
    // one outcome worse than the failure.
    nextCockpitHeldMark(key, "error", {say:false});
    return "error";
  }
  /* The cue from the store's own token rather than from `persisted`, which
     is one bit for four sentences; `NEXT_COCKPIT_HELD_CUES` records what
     each bit hid. */
  const outcome = String(saved.outcome || "");
  const kind = NEXT_COCKPIT_HELD_OUTCOME_CUES[outcome] ||
    (saved.persisted === true ? "saved" : "unpersisted");
  /* A draft goes only where the words are on disk, which is a minted
     revision or a repeat of the one already there, and only while its box
     still holds what was sent. `annotations.annotate` sets
     `state.annotations` before it writes, so `persisted:false` leaves the
     revision in this process alone, and the next collection reloads the
     file and drops it: dropping the draft then destroyed the only remaining
     copy of what someone typed. A reader who kept typing while the request
     was open has a newer instruction in there, and dropping it would revert
     the box to the older text they just watched leave. */
  nextCockpitHeldMark(key, kind, {say:false});
  if(kind !== "saved" && kind !== "unchanged"){
    /* Nothing landed, so the store's answer is the whole outcome and no
       refresh has words to draw: the button settles on it at once rather
       than waiting out a refresh. */
    void refreshNext();
    return kind;
  }
  nextCockpitIntentForgetSent(session, changes, body, sentLines);
  await refreshNext();
  return kind;
}

/* The drafts a landed save carried, dropped only while each box still holds
   what was sent, so nothing typed during the request is lost. */
function nextCockpitIntentForgetSent(session, changes, body, sentLines){
  const goalKey = nextCockpitHeldKey(session, "goal");
  const linesKey = nextCockpitHeldKey(session, "lines");
  if(changes.goal && nextCockpitHeldDrafts.get(goalKey) === body.goal){
    nextCockpitHeldDrafts.delete(goalKey);
  }
  // Typed words replaced the choice in the store, so it no longer stands in the box.
  if(changes.goal) nextIntentChosenPrompts.delete(goalKey);
  const held = nextCockpitHeldDrafts.get(linesKey);
  if(sentLines && held &&
      JSON.stringify(nextCockpitLinesToSend(held)) === JSON.stringify(sentLines)){
    nextCockpitLinesForget(linesKey);
  }
}

/* Whether the refreshed row shows this save landed: a revision above the one
   it was drafted against, holding the goal and lines it sent. */
function nextCockpitIntentLanded(session, body, sentLines){
  const row = (nextData && nextData.sessions || []).find(item => sessKey(item) === sessKey(session));
  if(!row) return false;
  const annotation = nextCockpitAnnotation(row);
  if(!annotation || !((nextNumber(annotation.revision) || 0) > body.expected_revision)) return false;
  if(typeof body.goal === "string" && String(annotation.goal || "") !== body.goal) return false;
  return !sentLines ||
    JSON.stringify(nextAnnotationLines(annotation).map(line => line.text)) ===
      JSON.stringify(sentLines);
}

/* Undo changes: what Escape does in each box, for both at once. The drafts
   are dropped rather than overwritten with the saved words, because the
   render reads the store whenever the Map has no entry, so this is the one
   place the two cannot disagree. */
/* Whether the intent a box's key belongs to has a save still being answered.
   Escape in a box is the same undo, so it takes the same guard. */
function nextCockpitIntentSaving(boxKey){
  return nextPendingHas(`${String(boxKey).replace(/:[^:]*$/, ":intent")}:save`);
}

function nextCockpitIntentUndo(session){
  // Never under a save still being answered: its words stay in the box.
  if(nextPendingHas(`${nextCockpitIntentKey(session)}:save`)) return;
  nextIntentChosenPrompts.delete(nextCockpitHeldKey(session, "goal"));
  for(const kind of ["goal", "lines"]){
    const key = nextCockpitHeldKey(session, kind);
    if(kind === "lines") nextCockpitLinesForget(key);
    else nextCockpitHeldDrafts.delete(key);
    nextCockpitHeldDrop(key);
  }
  const key = nextCockpitIntentKey(session);
  nextCockpitHeldDrop(key);
  renderNext({named: `${key}:undo`});
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
    nextPaintAfterMotion(() => renderNext());
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
  nextReadingFlipRender += 1;
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
  /* The footer's save mark too: it is the cue for these words, and the next
     press is a fresh attempt on different ones, so its report is not a
     repeat to suppress. */
  const session = nextCockpitFocusedSession(nextCockpitRouteGroup());
  if(session) nextCockpitHeldDrop(nextCockpitIntentKey(session));
  const field = input.closest ? input.closest("[data-next-cockpit-held-field]") : null;
  if(!field || !field.querySelector) return;
  const count = field.querySelector("[data-next-cockpit-held-count]");
  if(count) count.textContent = `${value.length}/${nextCockpitHeldCap()}`;
  /* Once the box stops holding the pick, the list's face goes back to "Use
     your prompt" in place, with no redraw to move the caret. */
  const pick = field.querySelector("[data-next-cockpit-prompt-select]");
  const chosen = nextIntentChosenPrompts.get(key);
  if(pick && pick.value && !(chosen && value === chosen.text)) pick.value = "";
  nextCockpitHeldToggle(field, "held-clear", Boolean(value), false);
  nextCockpitIntentFooterToggle(session);
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
  nextCockpitHeldDrop(nextCockpitIntentKey(session));
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
  nextCockpitIntentFooterToggle(session);
  const absent = field.querySelector("[data-next-cockpit-held-absent]");
  if(absent) absent.hidden = nextCockpitLinesToSend(draft).length > 0;
});

function nextIntentPromptMenuOpen(event){
  const select = event.target?.closest?.("[data-next-cockpit-prompt-select]");
  if(!select) return;
  const group = nextCockpitRouteGroup();
  const session = group ? nextCockpitFocusedSession(group) : null;
  if(!session) return;
  if(event.type === "keydown" && event.key === "Escape"){
    const held = nextIntentPromptLists.get(sessKey(session));
    if(held) held.open = false;
    return;
  }
  if(event.type === "keydown" && !["ArrowDown","ArrowUp"," ","Enter"].includes(event.key)) return;
  if(typeof select.showPicker === "function"){
    event.preventDefault();
    select.focus();
    nextIntentLoadPromptChoices(session).then(() => {
      if(!select.isConnected || nextIntentPromptLists.get(sessKey(session))?.open !== true) return;
      try{ select.showPicker(); }catch(_error){ select.focus(); }
    });
  }else nextIntentLoadPromptChoices(session);
}
document.addEventListener("pointerdown", nextIntentPromptMenuOpen);
document.addEventListener("keydown", nextIntentPromptMenuOpen);
document.addEventListener("focusout", event => {
  if(!event.target?.closest?.("[data-next-cockpit-prompt-select]")) return;
  const group = nextCockpitRouteGroup();
  const session = group ? nextCockpitFocusedSession(group) : null;
  const held = session && nextIntentPromptLists.get(sessKey(session));
  if(held) held.open = false;
});

document.addEventListener("change", event => {
  const select = event.target?.closest?.("[data-next-direction-select]");
  if(!select) return;
  const group = nextCockpitRouteGroup();
  const session = group ? nextCockpitFocusedSession(group) : null;
  if(session){ nextDirectionPicks.set(sessKey(session),String(select.value)); renderNext(); }
});

/* A pick in "Use your prompt". Registered before `next-render.js`'s own
   change listener (the part order in `page.py`), so the poll that list
   deferred while it held focus is taken here and not painted after the pick
   with the focus it captured before it: one render, focus on the select, and
   the deferred announcement still said. */
document.addEventListener("change", event => {
  const select = event.target && event.target.closest
    ? event.target.closest("[data-next-cockpit-prompt-select]") : null;
  if(!select || !select.value) return;
  const group = nextCockpitRouteGroup();
  const session = group ? nextCockpitFocusedSession(group) : null;
  if(!session) return;
  const menu = nextIntentPromptLists.get(sessKey(session));
  if(menu) menu.open = false;
  const pending = nextDeferredRender;
  nextDeferredRender = null;
  nextDeferredRenderCount = 0;
  nextIntentChoosePrompt(session, String(select.value));
  if(pending) nextAnnounceAttention(pending.announcement);
});

/* Focus leaving an open popover for another control closes it, so a keyboard
   reader who Tabs on from "Why" never lands on the "Saved" summary it covers
   (verifier, 2026-10-02; WCAG 2.4.11). Focus that goes nowhere leaves it open: that is
   another window taking focus, or a redraw replacing the focused node, and a
   poll must not shut a body the reader is reading. */
document.addEventListener("focusout", event => {
  const popover = event.target && typeof event.target.closest === "function"
    ? event.target.closest("details.next-disclose--pop[open]") : null;
  const next = event.relatedTarget;
  if(!popover || !next) return;
  if(!(typeof popover.contains === "function" && popover.contains(next))) popover.open = false;
});

/* Opening a popover scrolls the page just far enough to show all of it, once:
   the "What is sent" body is 487px tall at 1440x800 and ended below the
   window. Not a scroll box inside it, whose position every poll would lose
   (docs/design-reader-state.md), and not on a redraw, which re-inserts it open
   without a press. */
document.addEventListener("click", event => {
  const summary = event.target && typeof event.target.closest === "function"
    ? event.target.closest("summary") : null;
  const popover = summary && summary.parentElement;
  if(!popover || popover.tagName !== "DETAILS" || popover.open ||
     !(popover.classList && popover.classList.contains("next-disclose--pop"))) return;
  const reduce = typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  /* Two frames, not a zero timeout: measured in Chrome 156, a scroll asked for
     before the opened body is laid out moves nothing. */
  const later = typeof requestAnimationFrame === "function"
    ? run => requestAnimationFrame(() => requestAnimationFrame(run)) : run => setTimeout(run, 0);
  later(() => {
    if(!popover.open) return;
    const body = popover.querySelector(".next-disclose-body");
    if(body && typeof body.scrollIntoView === "function"){
      body.scrollIntoView({block:"nearest", behavior: reduce ? "auto" : "smooth"});
    }
  });
});

/* A click outside an open popover closes it, as a menu does. The restore lane
   reads `.open` at the next redraw, so nothing else needs telling. */
document.addEventListener("click", event => {
  const app = document.getElementById("app");
  if(!app || typeof app.querySelectorAll !== "function") return;
  for(const popover of app.querySelectorAll("details.next-disclose--pop[open]")){
    if(!(typeof popover.contains === "function" && popover.contains(event.target))) popover.open = false;
  }
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
      if(factId) nextCockpitOpenDirection(session, factId, n == null ? null : n, true, "update-intent");
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
  if(["direction-keep", "direction-add", "direction-save", "direction-cancel",
      "direction-replace", "direction-goal", "direction-lines-keep", "direction-lines-clear"].includes(action)){
    const session = group ? nextCockpitFocusedSession(group) : null;
    if(!session) return;
    event.preventDefault();
    const key = sessKey(session);
    if(action === "direction-goal"){
      nextDirectionUseGoal(session, String(target.dataset.arg || ""));
    }else if(action === "direction-lines-keep" || action === "direction-lines-clear"){
      const chosen = nextIntentChosenPrompts.get(nextCockpitHeldKey(session,"goal"));
      if(chosen){
        chosen.linesAnswer = action === "direction-lines-clear" ? "clear" : "keep";
        if(chosen.linesAnswer === "clear") nextCockpitLinesKeep(nextCockpitHeldKey(session,"lines"),[],[]);
        renderNext();
      }
    }else if(action === "direction-keep"){
      nextCockpitKeepIntent(session, nextCockpitObserverModel(group));
    }else if(action === "direction-add"){
      const factId = String(target.dataset.arg || "");
      const n = nextCockpitEntryNumbers(session, nextCockpitWorkSource(group, session)).get(factId);
      if(factId) nextCockpitOpenDirection(session, factId, n == null ? null : n, true);
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
  if(action === "held-clear" || action === "held-save" || action === "held-undo"){
    const session = group ? nextCockpitFocusedSession(group) : null;
    if(!session) return;
    event.preventDefault();
    const kind = String(target.dataset.arg || "");
    const key = nextCockpitHeldKey(session, kind);
    // One save and one undo for both fields (owner Q6), whatever field a
    // press names.
    if(action === "held-save"){
      nextCockpitIntentSave(session);
      return;
    }
    if(action === "held-undo"){
      nextCockpitIntentUndo(session);
      return;
    }
    // Emptying the box is an edit, not a save. The cleared field then differs
    // from the store, so `save` appears and the person commits the clearing
    // deliberately.
    nextCockpitHeldDrafts.set(key, "");
    nextIntentChosenPrompts.delete(key);
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
    // Not under a save still being answered, as Undo changes is not (ui4 V1).
    if(nextCockpitIntentSaving(key)) return true;
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
    if(nextCockpitIntentSaving(key)) return true;
    // Drop the draft rather than write the saved value back into it: the
    // render reads the store whenever the Map has no entry, so this is the
    // one place the two cannot disagree. A chosen prompt goes with it.
    nextCockpitHeldDrafts.delete(key);
    nextIntentChosenPrompts.delete(key);
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

/* The closed goal-source tokens an adopted goal carries, spelt as
   `reading.PROMPT_SOURCES` spells them; a test compares the two. */
const NEXT_PROMPT_CHOSEN = "chosen-prompt";
const NEXT_PROMPT_SOURCES = ["latest-prompt", "first-prompt", NEXT_PROMPT_CHOSEN];

/* The prompts "Use your prompt" offers (owner ruling Q7, 2026-10-01): the
   server's own `prompt_choices` on this session's focused project context,
   as `annotations.prompt_choices` built them, and nothing the page derives.
   An entry without an id, a time or words is not offered, because the server
   would refuse its adoption. [] until that context has loaded. */
function nextIntentPromptChoices(session){
  if(!session) return [];
  const menu = nextIntentPromptLists.get(sessKey(session));
  if(menu && Array.isArray(menu.choices)) return menu.choices.filter(choice =>
    choice && typeof choice.factId === "string" && choice.factId && typeof choice.text === "string" &&
    choice.text.trim() && nextNumber(choice.at) > 0);
  const suffix = `\n${sessKey(session)}`;
  for(const [key, entry] of nextCockpitContexts){
    const choices = entry && entry.data && entry.data.prompt_choices;
    if(!String(key).endsWith(suffix) || !Array.isArray(choices)) continue;
    return choices.filter(choice => choice && typeof choice.fact_id === "string" &&
      choice.fact_id && typeof choice.text === "string" && choice.text.trim() &&
      (nextNumber(choice.at) || 0) > 0).map(choice => ({factId: choice.fact_id,
      text: choice.text, at: nextNumber(choice.at), cut: choice.cut === true}));
  }
  return [];
}

/* The prompt a reader chose from the menu, per session goal key, as
   {factId, text, at}: tab memory, never browser storage, and never the box's
   typed draft, so the box holds it as a pending adoption the way it holds the
   first-prompt draft (docs/design-reader-state.md). */
const nextDirectionPicks = new Map();
const nextIntentPromptLists = new Map();

function nextDirectionSelected(session, pending){
  const pick = nextDirectionPicks.get(sessKey(session));
  return pending.find(entry => entry.id === pick) || pending[pending.length - 1];
}

function nextDirectionSelect(session, pending, numbers){
  if(pending.length < 2) return "";
  const chosen = nextDirectionSelected(session, pending);
  return '<label>Direction <select data-next-direction-select ' +
    `data-next-focus="direction-pick:${esc(sessKey(session))}">` +
    pending.map(entry => `<option value="${esc(entry.id)}"${entry === chosen ? " selected" : ""}>` +
      `${esc(`${numbers.has(entry.id) ? `#${numbers.get(entry.id)}` : nextSessionClock(entry.at)} · ${entry.summary || "Your direction"}`)}</option>`).join("") +
    '</select></label>';
}

function nextDirectionGoalButton(session, factId, scope = "question"){
  if(!["claude", "codex"].includes(String(session.harness || "")) || !factId) return "";
  return '<button type="button" class="next-action" data-next-cockpit-action="direction-goal" ' +
    `data-arg="${esc(factId)}" data-next-focus="direction-goal:${esc(sessKey(session))}:${esc(scope)}:${esc(factId)}"` +
    `${nextPendingAttrs(`direction-goal:${sessKey(session)}`)}>Use this as my goal</button>`;
}

async function nextDirectionUseGoal(session, factId){
  const annotation = nextCockpitAnnotation(session);
  const revision = nextNumber(session.annotation_revision) || 0;
  if(nextIntentUnsaved(session, annotation)){
    nextCockpitAnnounceCue(nextCockpitIntentKey(session), NEXT_INTENT_EDITED, false);
    return;
  }
  const control = `direction-goal:${sessKey(session)}`;
  const press = nextPendingStart(control, "Opening…");
  if(!press) return;
  try{
    const response = await nextFetchBounded("/api/direction", {method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({harness:session.harness,sid:session.sid,fact_id:factId})}, press.signal);
    const answer = response && response.ok ? await response.json() : null;
    const current = nextData?.sessions?.find(row => sessKey(row) === sessKey(session)) || session;
    if(nextIntentUnsaved(current, nextCockpitAnnotation(current)) ||
        (nextNumber(current.annotation_revision) || 0) !== revision){
      nextCockpitAnnounceCue(nextCockpitIntentKey(session), NEXT_INTENT_EDITED, false);
      return;
    }
    const choice = answer && answer.ok === true && answer.goal_choice;
    if(!choice || choice.fact_id !== factId || typeof choice.text !== "string" ||
        !choice.text.trim() || !(nextNumber(choice.at) > 0)){
      nextCockpitDirectionLines.set(sessKey(session), {factId,error:NEXT_COCKPIT_DIRECTION_UNOPENED});
      return;
    }
    const key = nextCockpitHeldKey(session, "goal");
    nextIntentChosenPrompts.set(key, {factId, text:choice.text, at:choice.at,
      cut:choice.cut === true, direction:true, linesAnswer:nextAnnotationLines(annotation).length ? null : "keep"});
    nextCockpitHeldDrafts.delete(key);
    nextCockpitDirectionLines.delete(sessKey(session));
    nextCockpitAnnounceCue(`${key}:chosen`, NEXT_INTENT_CHOSEN_SAID, false);
  }catch(_error){
    nextCockpitDirectionLines.set(sessKey(session), {factId,error:NEXT_COCKPIT_DIRECTION_UNOPENED});
  }finally{
    nextPendingEnd(control, press);
    renderNext({named:nextCockpitHeldKey(session,"goal")});
  }
}

function nextDirectionLinesQuestion(session){
  const chosen = nextIntentChosenPrompts.get(nextCockpitHeldKey(session,"goal"));
  if(!chosen || !chosen.direction || chosen.linesAnswer != null) return "";
  return '<p>Keep your standing outcome lines with this goal?</p>' +
    '<button type="button" data-next-cockpit-action="direction-lines-keep" data-next-focus="direction-lines-keep">Keep outcome lines</button>' +
    '<button type="button" data-next-cockpit-action="direction-lines-clear" data-next-focus="direction-lines-clear">Clear outcome lines</button>';
}

async function nextIntentLoadPromptChoices(session){
  const key = sessKey(session);
  if(nextIntentPromptLists.get(key)?.pending || nextIntentPromptLists.get(key)?.open) return;
  const group = nextCockpitRouteGroup();
  if(!group) return;
  nextIntentPromptLists.set(key,{pending:true,open:true,choices:nextIntentPromptChoices(session)});
  try{
    const response = await nextFetchBounded('/api/project-context?project=' +
      encodeURIComponent(nextCockpitStableKey(group)) + '&session=' + encodeURIComponent(key) + '&prompts=1');
    const data = response && response.ok ? await response.json() : null;
    nextIntentPromptLists.set(key,{pending:false,open:nextIntentPromptLists.get(key)?.open === true,choices:Array.isArray(data?.prompt_choices) ?
      data.prompt_choices.map(choice => ({factId:choice.fact_id,text:choice.text,at:choice.at,cut:choice.cut === true})) : []});
  }catch(_error){ nextIntentPromptLists.set(key,{pending:false,open:nextIntentPromptLists.get(key)?.open === true,choices:[]}); }
  /* Replacing the select closes the browser's open native menu. Fill only
     its options; ordinary polling already waits while this select holds focus. */
  const focus = `${nextCockpitHeldKey(session,"goal")}:prompt`;
  const app = document.getElementById("app");
  const select = app.querySelectorAll && [...app.querySelectorAll("[data-next-cockpit-prompt-select]")]
    .find(element => element.dataset.nextFocus === focus);
  if(select) select.innerHTML = nextIntentPromptOptions(session);
  else renderNext({named:focus});
}

const nextIntentChosenPrompts = new Map();

function nextPromptCandidate(session, source = "latest-prompt"){
  if(!session || !["claude", "codex"].includes(session.harness)) return null;
  let text = "", at = null;
  if(source === NEXT_PROMPT_CHOSEN){
    /* Only while the server still offers the same words at the same time
       under that fact: the adoption names all three, and a changed record
       must not adopt new words under an old choice. */
    const held = nextIntentChosenPrompts.get(nextCockpitHeldKey(session, "goal"));
    const found = held && (held.direction ? held : nextIntentPromptChoices(session).find(choice =>
      choice.factId === held.factId && choice.text === held.text && choice.at === held.at));
    return found ? {text: found.text, at: found.at, source, factId: found.factId,
      cut: found.cut} : null;
  }
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
   is drafted over a store this build cannot read, where Save intent could not
   save. */
function nextIntentDraft(session, annotation){
  if(!(nextData && nextData.annotate === true) || nextCockpitStoreUnreadable()) return null;
  const goal = annotation ? annotation.goal : session && session.annotation_goal;
  /* A prompt chosen from "Use your prompt" stands in the box first, over a
     saved goal as well (owner Q7): the reader picked it, so it is the pending
     adoption every consumer of the draft reads. It goes once its words are the
     saved goal, whichever press landed them, and once the server stops
     offering it. */
  const chosenKey = nextCockpitHeldKey(session, "goal");
  if(nextIntentChosenPrompts.has(chosenKey)){
    const chosen = nextPromptCandidate(session, NEXT_PROMPT_CHOSEN);
    const held = nextIntentChosenPrompts.get(chosenKey);
    const sourceChanged = held && held.direction &&
      (annotation?.goal_source !== NEXT_PROMPT_CHOSEN || nextNumber(annotation?.goal_source_at) !== chosen?.at);
    if(chosen && (String(goal || "").trim() !== chosen.text || sourceChanged)) return chosen;
    if(chosen || nextIntentChoicesSettled(session)) nextIntentChosenPrompts.delete(chosenKey);
  }
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

/* Whether this session's focused context has loaded without error, so a
   choice it no longer offers was withdrawn rather than not yet fetched. */
function nextIntentChoicesSettled(session){
  const suffix = `\n${sessKey(session)}`;
  for(const [key, entry] of nextCockpitContexts){
    if(String(key).endsWith(suffix) && entry && entry.data && !entry.error) return true;
  }
  return false;
}

// A chosen prompt over saved words is in the box and not yet saved.
function nextIntentChosenOverSaved(session, annotation){
  const draft = nextIntentDraft(session, annotation);
  const goal = annotation ? annotation.goal : session && session.annotation_goal;
  return Boolean(draft) && draft.source === NEXT_PROMPT_CHOSEN && Boolean(String(goal || "").trim());
}

/* Whether a press would stand on words other than the ones on screen: the
   goal box differs from what it stands on (the draft, or the saved goal), or
   the outcome-lines draft differs from what the server holds. A box put back
   to those words is not an edit. Keep, Add's save and Analyze are refused
   over one, for goals saved or drafted alike (consent F1 and F2, Codex 2). */
function nextIntentUnsaved(session, annotation){
  /* `/api/reading` refuses an implicit adoption over a saved goal, so a
     prompt chosen over one waits for its save as a typed edit does. */
  if(nextIntentChosenOverSaved(session, annotation)) return true;
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
  return Boolean(nextIntentDraft(session, annotation)) &&
    !nextIntentChosenOverSaved(session, annotation);
}

/* Analyze or Keep over an unsaved edit would read words that are not on
   screen, so the press is refused (owner's words, DRC-4682 fix round). Add's
   save has its own sentence, beside its line. */
const NEXT_INTENT_EDITED =
  "Save your intent, or undo your edit, to analyze drift.";
const NEXT_INTENT_SAVING = "Saving your intent\u2026";
const NEXT_INTENT_EDITED_ADD =
  "Save your intent, or undo your edit, to add this direction.";

function nextIntentAdoption(draft){
  return draft ? {adopt:draft.source, expected_prompt:draft.text,
    expected_prompt_at:draft.at, ...(draft.factId ? {prompt_fact:draft.factId} : {})} : {};
}

function nextImplicitAdoption(session){
  return nextIntentAdoption(nextIntentDraft(session, null));
}

/* While Save intent is being answered, telling the reader to save their
   intent is false: they just did. The usual line returns with the outcome. */
function nextIntentEditedRefusal(session){
  return nextPendingHas(`${nextCockpitIntentKey(session)}:save`) ? NEXT_INTENT_SAVING
    : NEXT_INTENT_EDITED;
}

/* `heldLive` skips the board's press refusal, for a card still holding a
   close (`nextReadingFlip`); every handler reads the real one. */
function nextPromptReadingRefusal(session, annotation, model, heldLive = false){
  if(!(nextData && nextData.annotate === true)) return NEXT_READING_ANNOTATIONS_OFF;
  /* A route with no reader is a fact about this machine, and it outranks any
     step the page could name: saving a goal here would not let a check run. */
  const route = nextReadingRoute(session);
  if(route && !route.provider) return nextReadingRouteRefusal(session);
  /* So does a press the board already says it cannot serve: saving or
     choosing words would not let it read (DRC-4758 slice B). */
  const press = heldLive ? "" : nextReadingPressRefusal(session);
  if(press) return press;
  if(nextIntentUnsaved(session, annotation)) return nextIntentEditedRefusal(session);
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
  if(!annotation || !NEXT_PROMPT_SOURCES.includes(annotation.goal_source)) return "";
  const at = nextNumber(annotation.goal_source_at);
  const which = annotation.goal_source === "first-prompt" ? "first"
    : annotation.goal_source === "latest-prompt" ? "latest"
    : at != null && at > 0 ? nextSessionClock(at) : "chosen";
  const clipped = String(annotation.goal || "").endsWith("…")
    ? ` ${NEXT_INTENT_EXCERPT_READ_WHOLE}` : "";
  return `<small class="next-cockpit-held-cue">from your prompt · ${which}.${clipped}</small>`;
}

/* "Use your prompt" (owner ruling Q7, 2026-10-01): one native select in the
   goal's label row listing the server's `prompt_choices`; picking one fills
   the box as a pending adoption. A native select rather than the `<details>`
   of buttons critic 14 chose ([owner, 2026-10-02](docs/design-reading-a-session.md#amended-2026-10-02-owner-a-native-select)):
   that menu jumped from the right of the row to the left when it opened,
   while the browser's own list drops over the page and moves nothing. Its
   rationale, that a poll redraw would shut a list mid-choice, is answered by
   `next-render.js`, which defers the poll's paint while a select holds focus;
   the select keeps its place by its own focus key, and its value is derived
   from the chosen prompt on every render. The first entry is the earliest
   prompt the record holds; over a session that opened with a harness control
   that is not its first prompt, so it is named the earliest. An excerpt says
   so in the option itself (item 2 of
   [DEC-24](docs/design-reading-a-session.md#dec-24-your-intent-is-a-drafted-goal-and-a-checklist-and-a-correction-is-yours-to-copy)). */
function nextIntentPromptSelect(session){
  if(!(nextData && nextData.annotate === true) || nextCockpitStoreUnreadable()) return "";
  if(!["claude","codex"].includes(String(session && session.harness || ""))) return "";
  const choices = nextIntentPromptChoices(session);
  const candidate = nextPromptCandidate(session,"first-prompt") || nextPromptCandidate(session,"latest-prompt");
  const suffix = `\n${sessKey(session)}`;
  const listed = [...nextCockpitContexts].some(([contextKey,entry]) => String(contextKey).endsWith(suffix) &&
    (entry?.data?.semantic?.facts || []).some(fact => fact.type === "user_message" &&
      fact.source_session?.harness === session.harness && fact.source_session?.sid === session.sid));
  if(!choices.length && !(candidate && candidate.at > 0) && !listed) return "";
  const key = nextCockpitHeldKey(session, "goal");
  return '<label class="next-intent-prompt-pick">' +
    '<span class="next-visually-hidden">Fill the goal from one of your prompts</span>' +
    '<select class="next-intent-prompt-select" data-next-cockpit-prompt-select ' +
    `data-next-focus="${esc(`${key}:prompt`)}">${nextIntentPromptOptions(session)}</select></label>`;
}

function nextIntentPromptOptions(session){
  const choices = nextIntentPromptChoices(session);
  const key = nextCockpitHeldKey(session,"goal");
  /* "First" only for the row's own first prompt. The choices come from the
     focused record, which holds the newest 100 events, so in a long session
     its earliest prompt is a later message (DRC-4758 fix round, F2). */
  const firstAt = nextNumber(session && session.first_prompt_at);
  const first = !nextIntentOpenedWithControl(session) && firstAt != null &&
    choices[0] && choices[0].at === firstAt ? "First prompt" : "Earliest prompt";
  /* The face shows the pick only while the box still holds it untouched; a
     keystroke puts it back to the placeholder, so the same prompt can be
     picked again. */
  const chosen = nextIntentChosenPrompts.get(key);
  const holds = Boolean(chosen) &&
    (!nextCockpitHeldDrafts.has(key) || nextCockpitHeldDrafts.get(key) === chosen.text);
  const options = choices.map((choice, index) => {
    const name = index === 0 ? first : index === 1 ? "Latest prompt" : "Earlier prompt";
    const label = `${name} \u00b7 ${nextSessionClock(choice.at)}${choice.cut ? " \u00b7 excerpt" : ""}` +
      ` \u2014 ${nextIntentPromptClip(choice.text, 60)}`;
    const selected = holds && chosen.factId === choice.factId ? " selected" : "";
    return `<option value="${esc(choice.factId)}"${selected}>${esc(label)}</option>`;
  }).join("");
  return '<option value="">Use your prompt</option>' + options;
}

/* An option's words, cut at the last space at or before `limit` characters.
   The box receives the whole prompt; only the list's line is short. */
function nextIntentPromptClip(text, limit){
  const words = String(text || "");
  if(words.length <= limit) return words;
  const space = words.lastIndexOf(" ", limit);
  return `${(space > 0 ? words.slice(0, space) : words.slice(0, limit)).trimEnd()}\u2026`;
}

const NEXT_INTENT_CHOSEN_SAID = "Goal filled from your prompt. Not saved.";

/* Choosing fills the box and saves nothing: the choice replaces whatever the
   box held, as a pending adoption the reader then saves, edits or undoes.
   Focus stays on the select, so arrowing through it on Windows or Linux,
   where each arrow is a change, previews each prompt in the box without
   throwing the reader into the textarea. */
function nextIntentChoosePrompt(session, factId){
  const found = nextIntentPromptChoices(session).find(choice => choice.factId === factId);
  if(!found) return;
  const key = nextCockpitHeldKey(session, "goal");
  nextIntentChosenPrompts.set(key, {factId: found.factId, text: found.text, at: found.at});
  nextCockpitHeldDrafts.delete(key);
  nextCockpitHeldDrop(key);
  nextCockpitAnnounceCue(`${key}:chosen`, NEXT_INTENT_CHOSEN_SAID, false);
  renderNext({named: `${key}:prompt`});
}

const NEXT_COCKPIT_ADOPT_REFUSED = {
  untrusted: "Cargento could not read cargento-annotations.json, so your prompt was not saved as " +
    "the goal and nothing was overwritten. Move or repair that file to save again.",
  unreadable: "This session's words were saved by a build of Cargento that can read more than " +
    "this one, so your prompt was not saved as the goal. Save from that build, or remove this " +
    "session's entry from cargento-annotations.json.",
};

/* Always under Save intent's pending entry, whose `signal` bounds it: choosing
   a prompt only fills the box. True when adopted, "unconfirmed" when no
   answer could be read, false when refused. */
async function nextAdoptPrompt(session, source, signal = null){
  const candidate = nextPromptCandidate(session, source);
  if(!candidate || candidate.at == null || !(nextData && nextData.annotate === true)) return false;
  const key = nextCockpitHeldKey(session, "goal");
  let response;
  let answer;
  try{
    response = await nextFetchBounded("/api/annotate", {method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({harness:session.harness,sid:session.sid,
        ...nextIntentAdoption(candidate),
        expected_revision:nextNumber(session.annotation_revision) || 0})}, signal);
    // A refusal's body is read leniently: an answered refusal is not a lost answer.
    answer = response.ok ? await response.json()
      : await Promise.resolve().then(() => response.json()).catch(() => null);
  }catch(_error){
    /* No answer is not a changed prompt: the save's own unconfirmed sentence
       says it, beside Save intent. */
    nextCockpitHeldMark(nextCockpitIntentKey(session), "unconfirmed", {say:false});
    await refreshNext();
    return "unconfirmed";
  }
  try{
    if(response.ok && answer && ["untrusted", "unreadable"].includes(String(answer.outcome || ""))){
      /* Not a changed prompt: the store could not take the save at all, and
         saying the prompt changed would send the reader to the wrong place. */
      nextCockpitReadingRequests.set(sessKey(session), {message:
        NEXT_COCKPIT_ADOPT_REFUSED[String(answer.outcome)]});
      return false;
    }
    if(!response.ok || !answer.persisted) throw new Error("adoption not saved");
    nextCockpitHeldDrafts.delete(key);
    nextIntentChosenPrompts.delete(key);
    await refreshNext();
    return true;
  }catch(_error){
    nextCockpitReadingRequests.set(sessKey(session),{message:"The prompt or saved goal changed, or could not be saved. Review the goal before trying again."});
    return false;
  }finally{renderNext();}
}
