/* The filtered reading of the newest prompt, where the payload carries one.
   `instruction.text` with the "asked" label IS the newest genuine prompt: the
   injected harness shapes dropped, slash markup read back out, and the whole
   string through `safe_text`. `last_prompt` is the raw newest record on every
   harness but Codex, so on a Claude row the two are two readings of one prompt
   and this takes the filtered one. Measured over 2,931 local rows: 114 carry an
   "asked" line, 15 of those differ from `last_prompt`, and 2 have no
   `last_prompt` at all.

   Only that label. This cell renders one latest-command claim with nowhere to put
   a source qualifier, and the other two labels are exactly the readings that need one:
   "agent" is an agent quoting itself and "earlier" says this is not the newest
   thing asked. Published bare they would be the claim
   `transcripts.instruction_from` refuses to make. */
function nextProjectInstructionRecord(session){
  const instruction = session && session.instruction;
  const labelled = instruction && typeof instruction === "object" &&
    !Array.isArray(instruction) && String(instruction.label || "") === "asked";
  const filtered = labelled
    ? String(instruction.text == null ? "" : instruction.text).trim()
    : "";
  return filtered ? {kind: "assignment", text: filtered} : null;
}

function nextProjectInstructionText(session){
  const record = nextProjectInstructionRecord(session);
  return record ? record.text : "";
}

function nextProjectInstruction(sessions){
  let chosen = null;
  for(const session of sessions){
    const record = nextProjectInstructionRecord(session);
    if(!record) continue;
    const at = nextFiniteNumber(session.last_activity);
    if(!chosen || at > chosen.at) chosen = {at, ...record};
  }
  return chosen;
}

function nextProjectAsks(group){
  const keys = new Set(group.sessions.map(nextSessionKey));
  return nextPayloadAsks(nextData).filter(ask => {
    const owner = nextExactAskOwner(nextData, ask);
    return owner && keys.has(nextSessionKey(owner));
  });
}

function nextProjectWorkflows(sessions){
  const found = [];
  const seen = new Set();
  for(const session of sessions){
    const spacedock = session.spacedock;
    const workflows = spacedock && Array.isArray(spacedock.workflows)
      ? spacedock.workflows
      : [];
    for(const item of workflows){
      const workflow = String(item && item.workflow || "").trim();
      const goal = String(item && item.goal || "").trim();
      if(!workflow && !goal) continue;
      const key = `${workflow}\n${goal}`;
      if(seen.has(key)) continue;
      seen.add(key);
      found.push({workflow: workflow || goal, goal});
    }
  }
  return found;
}

function nextProjectCell(group, operationalSessions){
  const workflows = nextProjectWorkflows(operationalSessions);
  const instruction = nextProjectInstruction(operationalSessions);
  const chips = workflows.map(workflow =>
    `<span class="next-project-workflow" title="${esc(workflow.goal)}">` +
      `${esc(workflow.workflow)}</span>`,
  ).join("");
  const last = instruction
    ? `<div class="next-project-instruction">Latest assignment · ${esc(instruction.text)}</div>`
    : "";
  /* The old collision signal is live-only because it warns about concurrent
     writes. This table makes a grouping claim, so even two idle rows need the
     caveat that spark.js:222-232 deliberately withholds from them. */
  const collision = group.sessions.length >= 2
    ? `<div class="next-project-collision" title="${esc(NEXT_DUPLICATE_LABEL_LIMIT)}">` +
      `${group.sessions.length} sessions share this label</div>`
    : "";
  return `<strong class="next-project-name">${esc(group.label)}</strong>${chips}${last}${collision}`;
}

function nextProjectProgress(sessions){
  const total = sessions.reduce((sum, session) => sum + Math.max(0, nextFiniteNumber(session.total)), 0);
  if(total <= 0) return "";
  const done = sessions.reduce((sum, session) => sum + Math.max(0, nextFiniteNumber(session.done)), 0);
  return `<progress class="next-project-progress-bar" value="${esc(Math.min(done, total))}" ` +
    `max="${esc(total)}" aria-label="${esc(done)} of ${esc(total)} tasks done"></progress>` +
    `<span>${esc(done)} of ${esc(total)} done</span>`;
}

function nextProjectNow(sessions){
  if(sessions.some(session => session.state === "needs_input")){
    return '<span class="next-project-now next-project-now--blocked">● blocked</span>';
  }
  const running = sessions.filter(session => session.state === "working" && session.active).length;
  if(running){
    return `<span class="next-project-now next-project-now--running">● ${running} running</span>`;
  }
  const statesKnown = sessions.length && sessions.every(session =>
    ["needs_input", "working", "idle"].includes(session.state),
  );
  return statesKnown
    ? '<span class="next-project-now next-project-now--idle">idle</span>'
    : "";
}

function nextProjectSummaryHtml(summary, sessionCount){
  const values = [`${sessionCount} ${sessionCount === 1 ? "session" : "sessions"}`];
  if(summary.exactRequests){
    values.push(`${summary.exactRequests} exact request${summary.exactRequests === 1 ? "" : "s"}`);
  }
  if(summary.risk) values.push(`${summary.risk} at risk`);
  if(summary.close) values.push(`${summary.close} close the loop`);
  if(summary.working) values.push(`${summary.working} working`);
  if(summary.quiet) values.push(`${summary.quiet} quiet`);
  return `<div class="next-project-summary">${values.map(value => `<span>${esc(value)}</span>`).join("")}</div>`;
}

function nextProjectSessionLine(session, asks, harnesses, labels){
  const harness = String(session.harness || "");
  const sid = String(session.sid || "");
  const harnessLabel = labels.get(harness) || harness || "Harness not published";
  const title = String(session.title || session.last_prompt || "").trim() || "Title not published";
  return '<div class="next-project-session" role="group" data-next-project-session ' +
    `data-next-harness="${esc(harness)}" data-next-session="${esc(sid)}" ` +
    `aria-label="${esc(harnessLabel)} session ${esc(title)}">` +
    '<span class="next-project-session-identity">' +
    `<small>SESSION</small><span>${esc(harnessLabel)}</span><strong>${esc(title)}</strong></span>` +
    nextOperationsNow(session) + nextOperationsNext(session) +
    nextOperationsBlocked(session, asks, harnesses) + "</div>";
}

function nextProjectSessionCommands(sessions, asks){
  const harnesses = nextOperationsHarnesses();
  const labels = nextHarnessLabels();
  return '<div class="next-project-sessions" aria-label="Active exact sessions">' +
    sessions.map(session => nextProjectSessionLine(session, asks, harnesses, labels)).join("") +
    "</div>";
}

function nextProjectRow(group, operationalSessions, summary, history = false){
  const operational = {...group, sessions: operationalSessions};
  const asks = nextProjectAsks(operational);
  const blocked = operationalSessions.some(session => nextOperationsIsBlocked(session, asks));
  const route = nextRouteToken({view: "project", project: group.label, session: null});
  const progress = nextProjectProgress(operationalSessions);
  const progressBlock = progress ? `<div class="next-project-progress">${progress}</div>` : "";
  const historyClass = history ? " next-project-row--history" : "";
  const historyAttr = history ? ' data-next-project-history="true"' : "";
  const command = history ? "" : nextProjectSessionCommands(operationalSessions, asks);
  return `<article class="next-project-row${blocked ? " next-project-row--blocked" : ""}${historyClass}" ` +
    `data-next-project-row data-next-project="${esc(group.label)}" data-next-route="${esc(route)}" ` +
    `role="link" tabindex="0"${historyAttr}>` +
    `<div class="next-project-project">${nextProjectCell(group, operationalSessions)}` +
    `${nextProjectSummaryHtml(summary, group.sessions.length)}${progressBlock}</div>` +
    `${command}</article>`;
}

function nextProjectGroup(kind, title, description, items, renderer, empty){
  const rows = items.map(renderer).join("");
  return `<section class="next-project-group next-project-group--${kind}" ` +
    `data-next-project-group="${kind}"><header><h2>${title}</h2>` +
    `<p>${description}</p></header><div class="next-projects-brief">` +
    `${rows || `<p class="next-projects-empty">${esc(empty)}</p>`}</div></section>`;
}

function nextProjectsView(model){
  const asks = nextPayloadAsks(nextData);
  const groups = nextProjectGroups().map((group, index) => {
    const activeSessions = group.sessions.filter(session =>
      nextOperationsIsActive(session, asks));
    const latest = Math.max(...group.sessions.map(session =>
      nextFiniteNumber(session.last_activity)), 0);
    return {
      group,
      index,
      activeSessions,
      latest,
      summary: nextAttentionProjectSummary(model, activeSessions),
    };
  });
  if(!groups.length){
    const window = model.windowHours == null ? "current payload" : `${esc(model.windowHours)}h payload`;
    return `<p class="next-projects-empty">No project display labels in this ${window}.</p>`;
  }
  const active = groups.filter(item => item.activeSessions.length);
  const history = groups.filter(item => !item.activeSessions.length);
  active.sort((left, right) => right.summary.exactRequests - left.summary.exactRequests ||
    right.summary.risk - left.summary.risk ||
    right.summary.close - left.summary.close ||
    right.summary.working - left.summary.working ||
    right.summary.quiet - left.summary.quiet ||
    left.index - right.index);
  history.sort((left, right) => right.latest - left.latest || left.index - right.index);
  return nextProjectGroup(
    "active", "Active projects", "Only source-backed active sessions contribute operational claims.",
    active, item => nextProjectRow(item.group, item.activeSessions, item.summary),
    "No project has active session evidence right now.",
  ) + nextProjectGroup(
    "history", "Recently observed projects",
    "Project identity and scope remain available without stale operational claims.",
    history, item => nextProjectRow(item.group, [], item.summary, true),
    "No recently observed project history in this payload.",
  );
}
