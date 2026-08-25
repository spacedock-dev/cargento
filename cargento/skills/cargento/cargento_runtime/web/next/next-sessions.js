const NEXT_SESSION_FINISHED_UNREAD_SEC = 1200;
const NEXT_SESSION_DUPLICATE_LABEL_LIMIT =
  "Same label is not proof of the same directory: the label is the" +
  " last two segments of each session's path, so sibling worktrees read alike.";

function nextSessionNumber(value){
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function nextSessionHarnessLabels(){
  const labels = new Map();
  const harnesses = nextData && Array.isArray(nextData.harnesses) ? nextData.harnesses : [];
  for(const harness of harnesses){
    const key = String(harness && harness.key || "");
    if(key) labels.set(key, String(harness.label || key));
  }
  return labels;
}

function nextSessionCollisionCounts(){
  const counts = new Map();
  for(const session of nextRows()){
    const project = String(session.project == null ? "" : session.project);
    counts.set(project, (counts.get(project) || 0) + 1);
  }
  return counts;
}

function nextSessionWorkingOrder(rows){
  const bySid = (left, right) => {
    const leftSid = String(left.sid || "");
    const rightSid = String(right.sid || "");
    return leftSid < rightSid ? -1 : (leftSid > rightSid ? 1 : 0);
  };
  return [...rows].sort((left, right) => {
    const leftRank = left.turn && left.turn.long ? 1 : 2;
    const rightRank = right.turn && right.turn.long ? 1 : 2;
    if(leftRank !== rightRank) return leftRank - rightRank;
    return bySid(left, right);
  });
}

function nextSessionBlocks(){
  const rows = nextRows();
  const gates = rows.filter(session => session.state === "needs_input");
  const working = nextSessionWorkingOrder(
    rows.filter(session => session.state === "working"),
  );
  /* aggregate.py:31-32 deliberately uses sid for a stable idle payload. The
     mock asks for nearest-idle first, so only this tail overrides that order;
     the gate queue stays byte-for-byte in the server's priority order. */
  const generated = nextSessionNumber(nextData && nextData.generated) || 0;
  const idle = rows.filter(session => session.state === "idle").sort((left, right) => {
    const leftAt = nextSessionNumber(left.last_activity) || 0;
    const rightAt = nextSessionNumber(right.last_activity) || 0;
    const byAge = (generated - leftAt) - (generated - rightAt);
    if(byAge) return byAge;
    const leftSid = String(left.sid || "");
    const rightSid = String(right.sid || "");
    return leftSid < rightSid ? -1 : (leftSid > rightSid ? 1 : 0);
  });
  return {gates, working, idle};
}

function nextSessionMinutesSince(stamp){
  const generated = nextSessionNumber(nextData && nextData.generated);
  const at = nextSessionNumber(stamp);
  if(generated == null || at == null || at <= 0) return null;
  return Math.floor(Math.max(0, generated - at) / 60);
}

function nextSessionMetric(session){
  if(session.state === "needs_input"){
    const wait = nextSessionMinutesSince(session.blocked_since);
    return wait == null ? "" : `${wait}m wait`;
  }
  if(session.state === "working"){
    const rate = nextSessionNumber(session.rate_per_min);
    return rate == null ? "" : `${Math.round(rate).toLocaleString()} /m`;
  }
  const idle = nextSessionMinutesSince(session.last_activity);
  return idle == null ? "" : `${idle}m idle`;
}

function nextSessionActivity(session){
  if(session.state === "idle"){
    const generated = nextSessionNumber(nextData && nextData.generated);
    const finished = nextSessionNumber(session.finished_at);
    if(generated != null && finished != null && finished > 0 &&
       Math.max(0, generated - finished) >= NEXT_SESSION_FINISHED_UNREAD_SEC){
      return '<span class="next-session-done">done</span>';
    }
  }
  return esc(session.state_detail || "");
}

function nextSessionCollision(session, counts){
  const project = String(session.project == null ? "" : session.project);
  const count = counts.get(project) || 0;
  if(count < 2) return "";
  return `<span class="next-session-collision" title="${esc(NEXT_SESSION_DUPLICATE_LABEL_LIMIT)}">` +
    `${count} sessions share this label</span>`;
}

function nextSessionRow(session, labels, collisions){
  const project = String(session.project == null ? "" : session.project);
  const harness = String(session.harness == null ? "" : session.harness);
  const harnessLabel = labels.get(harness) || harness;
  const title = String(session.title || session.last_prompt || "");
  const route = nextRouteToken({view: "project", project, session: null});
  const stateClass = session.state === "needs_input"
    ? " next-session-row--blocked"
    : (session.state === "working" ? " next-session-row--working" : "");
  return `<tr class="next-session-row${stateClass}" data-next-session="${esc(session.sid)}" ` +
    `data-next-route="${esc(route)}"><td class="next-session-identity">` +
    `<strong>${esc(title)}</strong><span>${esc(project)} · ${esc(harnessLabel)}</span>` +
    `${nextSessionCollision(session, collisions)}</td>` +
    `<td class="next-session-activity">${nextSessionActivity(session)}</td>` +
    `<td class="next-session-metric">${esc(nextSessionMetric(session))}</td></tr>`;
}

function nextSessionBlock(state, label, rows, labels, collisions){
  const body = rows.map(session => nextSessionRow(session, labels, collisions)).join("");
  return `<tbody data-next-session-block="${state}">` +
    `<tr class="next-session-group"><th colspan="3" scope="rowgroup">${label}</th></tr>` +
    `${body}</tbody>`;
}

function nextSessionsView(){
  const blocks = nextSessionBlocks();
  const labels = nextSessionHarnessLabels();
  const collisions = nextSessionCollisionCounts();
  return '<div class="next-sessions-table-wrap"><table class="next-sessions-table">' +
    '<thead><tr><th scope="col">SESSION</th><th scope="col">ACTIVITY</th>' +
    '<th scope="col">RATE</th></tr></thead>' +
    nextSessionBlock("needs_input", "needs you", blocks.gates, labels, collisions) +
    nextSessionBlock("working", "working", blocks.working, labels, collisions) +
    nextSessionBlock("idle", "idle", blocks.idle, labels, collisions) +
    "</table></div>";
}
