const NEXT_ANSWER_FAILURE = "no confirmation came back — it may already have been answered";
const nextSessionAnswerNotes = new Map();

function nextSessionFind(project, sid){
  const projectKey = String(project == null ? "" : project);
  const sessionKey = String(sid == null ? "" : sid);
  return nextRows().find(session =>
    String(session.project == null ? "" : session.project) === projectKey &&
    String(session.sid == null ? "" : session.sid) === sessionKey
  ) || null;
}

function nextSessionAsks(session){
  if(!nextData || nextData.ask !== true || !Array.isArray(nextData.asks)) return [];
  const sid = String(session.sid == null ? "" : session.sid);
  return nextData.asks.filter(ask => String(ask && ask.session_id || "") === sid);
}

function nextPruneSessionAnswerNotes(){
  const asks = nextData && Array.isArray(nextData.asks) ? nextData.asks : [];
  const live = new Set(asks.map(ask => String(ask && ask.id || "")));
  for(const id of nextSessionAnswerNotes.keys()){
    if(!live.has(id)) nextSessionAnswerNotes.delete(id);
  }
}

function nextSessionRegistryLabel(session){
  return nextHarnessLabels().get(String(session.harness || "")) || "";
}

function nextSessionAskingTitle(session){
  return `${nextSessionRegistryLabel(session) || "An agent"} is asking you`;
}

function nextSessionTitle(session, asks){
  const firstAsk = asks.length ? asks[0] : null;
  return String(
    session.title || session.last_prompt || (firstAsk && firstAsk.question) ||
    session.project || session.sid || "Session"
  );
}

function nextSessionMeta(session){
  const parts = [];
  const harness = nextSessionRegistryLabel(session);
  if(harness) parts.push(harness);
  const shortSid = String(session.session || session.sid || "").slice(0, 8);
  if(shortSid) parts.push(shortSid);
  if(session.state_detail) parts.push(String(session.state_detail));
  if(session.state === "needs_input"){
    const blocked = nextMinutesSince(session.blocked_since);
    if(blocked != null) parts.push(`blocked ${blocked}m`);
  }else{
    const started = nextMinutesSince(session.started_at);
    if(started != null) parts.push(`started ${started}m ago`);
  }
  return parts.join(" · ");
}

function nextSessionAskBlock(session, asks){
  if(!asks.length) return "";
  const cards = asks.map(ask => {
    const id = String(ask && ask.id || "");
    const options = Array.isArray(ask && ask.options) ? ask.options : [];
    const buttons = options.map((option, index) =>
      `<button type="button" data-next-answer="${esc(id)}" ` +
      `data-next-answer-index="${index}">${esc(option)}</button>`
    ).join("");
    const choices = buttons
      ? `<div class="next-session-answer-options">${buttons}</div>`
      : '<p class="next-session-answer-empty">No answer options were supplied.</p>';
    const failure = nextSessionAnswerNotes.get(id);
    const note = failure
      ? `<p class="next-session-answer-failure" role="status">${esc(failure)}</p>`
      : "";
    return `<article class="next-session-ask" data-next-session-ask="${esc(id)}">` +
      `<p class="next-session-ask-question">${esc(ask && ask.question)}</p>` +
      choices + note + "</article>";
  }).join("");
  return '<section class="next-session-section" data-next-session-section="ask">' +
    '<div class="next-session-ask-callout"><span>AGENT IS ASKING</span>' +
    `<strong>${esc(nextSessionAskingTitle(session))}</strong></div>${cards}</section>`;
}

function nextSessionTaskGlyph(status){
  if(status === "completed"){
    return '<span class="next-status-dot next-session-task-glyph" aria-label="completed">✓</span>';
  }
  if(status === "in_progress"){
    return nextStatusDot("in progress", "next-session-task-glyph");
  }
  return nextStatusDot("pending", "next-session-task-glyph", false);
}

function nextSessionTasks(session){
  const tasks = Array.isArray(session.tasks) ? session.tasks : [];
  if(session.harness !== "claude" || !tasks.length) return "";
  const completed = tasks.filter(task => task && task.status === "completed").length;
  const rows = tasks.map(task => {
    const status = String(task && task.status || "pending");
    const pending = status === "pending" ? " next-session-task--pending" : "";
    return `<div class="next-session-task${pending}" ` +
      `data-next-session-task="${esc(task && task.id)}">` +
      `${nextSessionTaskGlyph(status)}` +
      `<strong class="next-session-task-subject">${esc(task && task.subject)}</strong></div>`;
  }).join("");
  return '<section class="next-session-section" data-next-session-section="tasks">' +
    `<h2>TASKS · ${completed} OF ${tasks.length} DONE</h2>${rows}</section>`;
}

function nextSessionSubagents(session){
  const subagents = Array.isArray(session.subagents) ? session.subagents : [];
  if(!subagents.length) return "";
  const rows = subagents.map((subagent, index) => {
    const elapsed = nextMinutesSince(subagent && subagent.started_at);
    const measured = elapsed == null
      ? ""
      : `<span class="next-session-subagent-elapsed">${elapsed}m</span>`;
    return `<div class="next-session-subagent next-live" data-next-session-subagent="${index}">` +
      `${nextStatusDot("running", "next-session-subagent-glyph")}` +
      `<strong class="next-session-subagent-name">${esc(subagent && subagent.name || "subagent")}</strong>` +
      `${measured}</div>`;
  }).join("");
  return '<section class="next-session-section" data-next-session-section="subagents">' +
    `<h2>SUBAGENTS</h2>${rows}</section>`;
}

function nextCompactTokens(value){
  if(value < 1000) return Math.round(value).toLocaleString("en-US");
  return `${Math.round(value / 100) / 10}k`;
}

function nextSessionFooter(session){
  const sessionTotal = nextNumber(session.session_output_tokens);
  const turnTotal = nextNumber(session.turn_output_tokens);
  const source = sessionTotal != null ? "session" : (turnTotal != null ? "turn" : "");
  const value = sessionTotal != null ? sessionTotal : turnTotal;
  if(value == null) return "";
  return `<footer class="next-session-footer" data-next-session-tokens="${source}">` +
    `${nextCompactTokens(value)} output tokens</footer>`;
}

function nextSessionView(project, sid){
  const session = nextSessionFind(project, sid);
  if(!session){
    return '<section class="next-session-detail-empty" ' +
      'data-next-session-state="outside-payload">This session is outside the current payload.</section>';
  }
  nextPruneSessionAnswerNotes();
  const asks = nextSessionAsks(session);
  const blocked = session.state === "needs_input" ? " next-session-detail--blocked" : "";
  const meta = nextSessionMeta(session);
  const metaLine = meta ? `<p class="next-session-detail-meta">${esc(meta)}</p>` : "";
  return `<article class="next-session-detail${blocked}" data-next-session-detail="${esc(session.sid)}">` +
    '<header class="next-session-detail-header"><span class="next-session-detail-label">SESSION</span>' +
    `<h1>${esc(nextSessionTitle(session, asks))}</h1>${metaLine}</header>` +
    nextSessionAskBlock(session, asks) + nextSessionTasks(session) +
    nextSessionSubagents(session) + nextSessionFooter(session) + "</article>";
}

async function nextAnswerAsk(id, index){
  try{
    const response = await fetch("/api/answer", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({id, index}),
    });
    if(!response.ok) throw new Error(`HTTP ${response.status}`);
    const answer = await response.json();
    if(answer.answered !== true) throw new Error("answer not confirmed");
    nextSessionAnswerNotes.delete(id);
    await refreshNext();
  }catch(_error){
    nextSessionAnswerNotes.set(id, NEXT_ANSWER_FAILURE);
    renderNext();
  }
}

document.addEventListener("click", event => {
  const target = event.target && event.target.closest
    ? event.target.closest("[data-next-answer]")
    : null;
  if(!target) return;
  const id = String(target.dataset.nextAnswer || "");
  const index = Number(target.dataset.nextAnswerIndex);
  if(!id || !Number.isInteger(index) || index < 0) return;
  event.preventDefault();
  void nextAnswerAsk(id, index);
});
