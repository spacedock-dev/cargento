const NEXT_SESSION_FINISHED_UNREAD_SEC = 1200;

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
  /* aggregate.py:31-32 deliberately uses sid for a stable idle payload. The
     mock asks for nearest-idle first, so only this tail overrides that order;
     the gate queue stays byte-for-byte in the server's priority order. */
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
  return {gates, working, idle};
}

function nextSessionActivity(session){
  if(session.state === "idle"){
    const generated = nextNumber(nextData && nextData.generated);
    const finished = nextNumber(session.finished_at);
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
  return `<span class="next-session-collision" title="${esc(NEXT_DUPLICATE_LABEL_LIMIT)}">` +
    `${count} sessions share this label</span>`;
}

function nextSessionRow(session, labels, collisions){
  const project = String(session.project == null ? "" : session.project);
  const harness = String(session.harness == null ? "" : session.harness);
  const harnessLabel = labels.get(harness) || harness;
  const title = String(session.title || session.last_prompt || "");
  const route = nextRouteToken({view: "session", project, session: String(session.sid || "")});
  const stateClass = session.state === "needs_input"
    ? " next-session-row--blocked"
    : (session.state === "working" ? " next-session-row--working" : "");
  const live = session.active === true && session.state === "working";
  const liveClass = live ? " next-live" : "";
  const liveDot = live ? nextStatusDot("working", "next-session-live-glyph") : "";
  const instruction = nextInstructionLine(session, title, "next-session-row-instruction");
  /* Line 1 takes a label only where line 2 is there to be told apart from it.
     A labelled "asked, 4m:" under a bare string reads as a caption for the row
     rather than for the line beneath it, which is the ambiguity the labels
     exist to remove; a lone "title:" on every row of a table whose column is
     already headed SESSION is noise for nothing.

     AND line 1 has to actually be the title. `title` above falls back through
     `last_prompt` to the empty string, so gating on line 2 alone let the label
     caption an unfiltered prompt, or caption nothing and leave a dangling
     "title: ". Both are unreached today — over 3,774 Claude transcripts and 459
     Codex rollouts, every one that publishes an instruction also publishes a
     title — but that containment is a property of the corpus rather than of the
     code: `session_title` falls back to the FIRST prompt and breaks whatever it
     returns, while the instruction walks backward, so an opening prompt that
     strips to empty above a genuine later one produces the state. The
     conjunction makes it unrepresentable instead of unlikely. */
  const titleLabel = instruction && session.title
    ? '<span class="next-instruction-label">title</span>: '
    : "";
  return `<tr class="next-session-row${stateClass}${liveClass}" data-next-session="${esc(session.sid)}" ` +
    `data-next-route="${esc(route)}"><td class="next-session-identity">` +
    `<strong>${liveDot}${titleLabel}${esc(title)}</strong>${instruction}` +
    `<span>${esc(project)} · ${esc(harnessLabel)}</span>` +
    `${nextSessionCollision(session, collisions)}</td>` +
    `<td class="next-session-activity">${nextSessionActivity(session)}</td>` +
    `<td class="next-session-metric">${esc(nextSessionMetric(session))}</td></tr>`;
}

function nextSessionsView(){
  const blocks = nextSessionBlocks();
  const labels = nextHarnessLabels();
  const collisions = nextSessionCollisionCounts();
  const rows = [...blocks.gates, ...blocks.working, ...blocks.idle]
    .map(session => nextSessionRow(session, labels, collisions)).join("");
  return '<div class="next-sessions-table-wrap"><table class="next-sessions-table">' +
    '<thead><tr><th scope="col">SESSION</th><th scope="col">ACTIVITY</th>' +
    `<th scope="col">METRIC</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}
