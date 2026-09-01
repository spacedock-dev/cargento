function nextSessionCollisionCounts(){
  const counts = new Map();
  for(const session of nextRows()){
    const project = String(session.project == null ? "" : session.project);
    counts.set(project, (counts.get(project) || 0) + 1);
  }
  return counts;
}

function nextSessionBlocks(){
  const rows = nextRows();
  const gates = rows.filter(session => session.state === "needs_input");
  const working = nextSessionWorkingOrder(
    rows.filter(session => session.state === "working"),
  );
  /* aggregate.py deliberately uses sid for a stable idle payload. Keep the
     server's gate order and override only the idle tail by nearest activity. */
  const generated = nextNumber(nextData && nextData.generated) || 0;
  const idle = rows.filter(session => session.state === "idle").sort((left, right) => {
    const leftAt = nextNumber(left.last_activity) || 0;
    const rightAt = nextNumber(right.last_activity) || 0;
    const byAge = (generated - leftAt) - (generated - rightAt);
    if(byAge) return byAge;
    const leftSid = String(left.sid || "");
    const rightSid = String(right.sid || "");
    return leftSid < rightSid ? -1 : (leftSid > rightSid ? 1 : 0);
  });
  const other = rows.filter(session =>
    !["needs_input", "working", "idle"].includes(String(session.state || "")));
  return {gates, working, idle, other};
}

function nextSessionCollision(session, counts){
  const project = String(session.project == null ? "" : session.project);
  const count = counts.get(project) || 0;
  if(count < 2) return "";
  return `<span class="next-operation-collision" title="${esc(NEXT_DUPLICATE_LABEL_LIMIT)}">` +
    `${count} sessions share this label</span>`;
}

function nextOperationsAsks(rows){
  if(!nextData || nextData.ask !== true) return [];
  const identities = new Set(rows.map(session => String(session && session.sid || "")));
  return nextPayloadAsks(nextData).filter(ask =>
    identities.has(String(ask && ask.session_id || "")));
}

function nextOperationsHarnesses(){
  const entries = nextData && Array.isArray(nextData.harnesses) ? nextData.harnesses : [];
  return new Map(entries.map(entry => [String(entry && entry.key || ""), entry]));
}

function nextOperationsReportsBlocks(session, harnesses){
  if(session.state === "needs_input") return true;
  const harness = harnesses.get(String(session.harness || ""));
  return Boolean(harness && harness.reports_needs_input === true);
}

function nextOperationsFleetFact(kind, label, value, note = ""){
  const detail = note ? `<small>${esc(note)}</small>` : "";
  return `<section data-next-fleet-fact="${kind}"><span>${label}</span>` +
    `<strong>${value}</strong>${detail}</section>`;
}

function nextOperationsFleet(rows, asks, harnesses){
  const working = rows.filter(session => session.state === "working").length;
  const blocks = rows.filter(session => session.state === "needs_input").length;
  const covered = rows.filter(session =>
    nextOperationsReportsBlocks(session, harnesses)).length;
  const coverage = `${covered} of ${rows.length} sessions report block state`;
  return '<section class="next-operations-fleet" aria-label="Fleet facts">' +
    nextOperationsFleetFact("observed", "OBSERVED SESSIONS", rows.length) +
    nextOperationsFleetFact("working", "WORKING", working) +
    nextOperationsFleetFact("requests", "EXACT REQUESTS", asks.length) +
    nextOperationsFleetFact("reported-blocks", "REPORTED BLOCKS", blocks, coverage) +
    "</section>";
}

function nextOperationsTask(session, status){
  const tasks = Array.isArray(session.tasks) ? session.tasks : [];
  return tasks.find(task =>
    task && task.status === status && String(task.subject || "").trim()) || null;
}

function nextOperationsFact(kind, label, value, detail = "", tone = ""){
  const suffix = tone ? ` next-operation-fact--${tone}` : "";
  const secondary = detail ? `<em>${esc(detail)}</em>` : "";
  return `<span class="next-operation-fact${suffix}" data-next-operation-fact="${kind}">` +
    `<small>${label}</small><strong>${esc(value)}</strong>${secondary}</span>`;
}

function nextOperationsWhere(session){
  const project = String(session.project == null ? "" : session.project).trim();
  return nextOperationsFact(
    "where",
    "WHERE · PROJECT LABEL",
    project || "Project label not published",
    "Exact location not published",
  );
}

function nextOperationsNow(session){
  const inProgress = nextOperationsTask(session, "in_progress");
  const state = String(session.state || "").replace("_", " ").trim();
  const detail = inProgress
    ? String(inProgress.subject).trim()
    : String(session.state_detail || "").trim();
  return nextOperationsFact(
    "now",
    `NOW${state ? ` · ${state.toUpperCase()}` : ""}`,
    detail || "Activity not published",
  );
}

function nextOperationsNext(session){
  const pending = nextOperationsTask(session, "pending");
  return nextOperationsFact(
    "next",
    "NEXT",
    pending ? String(pending.subject).trim() : "No pending step published",
  );
}

function nextOperationsBlocked(session, asks, harnesses){
  const sid = String(session.sid || "");
  const ask = asks.find(item => String(item && item.session_id || "") === sid);
  if(session.state === "needs_input" || ask){
    const question = String(ask && ask.question || "").trim();
    const detail = question || String(session.state_detail || "").trim() || "Block reported";
    return nextOperationsFact("blocked", "BLOCKED", "Reported", detail, "blocked");
  }
  if(nextOperationsReportsBlocks(session, harnesses)){
    return nextOperationsFact(
      "blocked", "BLOCKED", "No reported block", "Reporter available", "clear",
    );
  }
  return nextOperationsFact(
    "blocked", "BLOCKED", "Unknown", "Harness does not report blocks", "unknown",
  );
}

function nextOperationsIdentity(session, labels, collisions){
  const harness = String(session.harness == null ? "" : session.harness);
  const harnessLabel = labels.get(harness) || harness || "Harness not published";
  const title = String(session.title || session.last_prompt || "").trim() || "Title not published";
  const sid = String(session.sid || "").trim() || "Identity not published";
  const live = session.active === true && session.state === "working";
  const dot = live ? nextStatusDot("working", "next-operation-live-glyph") : "";
  return '<span class="next-operation-identity">' +
    `<small>SESSION · ${esc(harnessLabel)}</small><strong>${dot}${esc(title)}</strong>` +
    `<span class="next-operation-sid">${esc(sid)}</span>` +
    nextSessionCollision(session, collisions) + "</span>";
}

function nextOperationsRow(session, labels, collisions, asks, harnesses){
  const project = String(session.project == null ? "" : session.project);
  const sid = String(session.sid || "");
  const route = nextRouteToken({view: "session", project, session: sid});
  const state = String(session.state || "unknown");
  const live = session.active === true && state === "working" ? " next-live" : "";
  return `<a class="next-operation-row next-operation-row--${esc(state)}${live}" ` +
    `href="#n=${esc(route)}" data-next-session="${esc(sid)}" data-next-route="${esc(route)}">` +
    nextOperationsIdentity(session, labels, collisions) +
    nextOperationsWhere(session) +
    nextOperationsNow(session) +
    nextOperationsNext(session) +
    nextOperationsBlocked(session, asks, harnesses) +
    "</a>";
}

function nextSessionsView(){
  const rows = nextRows();
  const asks = nextOperationsAsks(rows);
  const harnesses = nextOperationsHarnesses();
  const blocks = nextSessionBlocks();
  const labels = nextHarnessLabels();
  const collisions = nextSessionCollisionCounts();
  const ordered = [...blocks.gates, ...blocks.working, ...blocks.idle, ...blocks.other];
  const rendered = ordered.map(session =>
    nextOperationsRow(session, labels, collisions, asks, harnesses)).join("");
  let body = rendered;
  if(!body){
    const windowHours = nextNumber(nextData && nextData.window_hours);
    const window = windowHours == null ? "current payload" : `${esc(windowHours)}h payload`;
    body = `<p class="next-sessions-empty">No session rows in this ${window}.</p>`;
  }
  return '<section class="next-operations" data-next-view-body="sessions">' +
    '<header class="next-operations-header"><span>COMMAND SURFACE</span>' +
    '<h1>Session operations</h1>' +
    '<p>Every observed session. One comparable command surface.</p></header>' +
    nextOperationsFleet(rows, asks, harnesses) +
    '<div class="next-operations-columns" aria-hidden="true">' +
    '<span>SESSION</span><span>WHERE</span><span>NOW</span><span>NEXT</span>' +
    '<span>BLOCKED</span></div>' +
    `<div class="next-operation-rows">${body}</div></section>`;
}
