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
  if(filtered) return {kind: "assignment", text: filtered};
  const context = String(session.last_prompt || session.title || "").trim();
  return context ? {kind: "context", text: context} : null;
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

function nextProjectHasSpacedock(sessions){
  return sessions.some(session => {
    const spacedock = session && session.spacedock;
    return spacedock && typeof spacedock === "object" && !Array.isArray(spacedock);
  });
}

function nextProjectRequestLabel(ask){
  return nextAskResponsibility(nextData, ask) === "CAPTAIN" ? "Captain" : "Needs you";
}

function nextProjectCell(group){
  const workflows = nextProjectWorkflows(group.sessions);
  const instruction = nextProjectInstruction(group.sessions);
  const chips = workflows.map(workflow =>
    `<span class="next-project-workflow" title="${esc(workflow.goal)}">` +
      `${esc(workflow.workflow)}</span>`,
  ).join("");
  const last = instruction
    ? `<div class="next-project-instruction">${instruction.kind === "assignment" ?
      "Latest assignment" : "Latest session context"} · ${esc(instruction.text)}</div>`
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

function nextProjectRow(group, summary){
  const asks = nextProjectAsks(group);
  const ask = asks.length ? asks[0] : null;
  const question = String(ask && ask.question || "").trim();
  const blocked = Boolean(ask);
  const running = group.sessions.filter(session => session.state === "working" && session.active).length;
  let situation = "State unavailable in the current payload";
  if(question) situation = `Waiting for your response: ${question}`;
  else if(running) situation = `${running} ${running === 1 ? "session" : "sessions"} executing`;
  else if(group.sessions.some(session => session.state === "needs_input")){
    situation = "Input signal observed; request unavailable in the current payload";
  }else if(group.sessions.every(session => session.state === "idle")){
    situation = "No active session observed";
  }
  const response = question
    ? `<div><span>RESPONSE</span><strong>${nextProjectRequestLabel(ask)} · ${esc(question)}</strong></div>`
    : "";
  const commandClass = question
    ? "next-project-command"
    : "next-project-command next-project-command--situation-only";
  const route = nextRouteToken({view: "project", project: group.label, session: null});
  const progress = nextProjectProgress(group.sessions);
  const progressBlock = progress ? `<div class="next-project-progress">${progress}</div>` : "";
  return `<article class="next-project-row${blocked ? " next-project-row--blocked" : ""}" ` +
    `data-next-project-row data-next-project="${esc(group.label)}" data-next-route="${esc(route)}" ` +
    'role="link" tabindex="0">' +
    `<div class="next-project-project">${nextProjectCell(group)}` +
    `${nextProjectSummaryHtml(summary, group.sessions.length)}${progressBlock}</div>` +
    `<div class="${commandClass}"><div><span>SITUATION</span>` +
    `<strong>${esc(situation)}</strong></div>${response}</div></article>`;
}

function nextProjectsView(model){
  const groups = nextProjectGroups().map((group, index) => ({
    group, index, summary: nextAttentionProjectSummary(model, group.sessions),
  }));
  if(!groups.length){
    const window = model.windowHours == null ? "current payload" : `${esc(model.windowHours)}h payload`;
    return `<p class="next-projects-empty">No project display labels in this ${window}.</p>`;
  }
  groups.sort((left, right) => right.summary.exactRequests - left.summary.exactRequests ||
    right.summary.risk - left.summary.risk ||
    right.summary.close - left.summary.close ||
    right.summary.working - left.summary.working ||
    right.summary.quiet - left.summary.quiet ||
    left.index - right.index);
  return `<div class="next-projects-brief">${groups.map(item =>
    nextProjectRow(item.group, item.summary)).join("")}</div>`;
}
