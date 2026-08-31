function nextAttentionAskAge(ask){
  const age = nextNumber(ask && ask.age_sec);
  return age != null && age >= 0 ? age : null;
}

function nextAttentionAskKey(ask, sourceIndex){
  return ask && ask.id != null ? `ask:${String(ask.id)}` : `ask-index:${sourceIndex}`;
}

function nextAttentionHarnessOrder(payload){
  if(!payload || typeof payload !== "object" || Array.isArray(payload) ||
    !Array.isArray(payload.harnesses)) return [];
  const found = [];
  for(const harness of payload.harnesses){
    const key = String(harness && harness.key || "");
    if(key && !found.includes(key)) found.push(key);
  }
  return found;
}

function nextAttentionStableCompare(left, right, model){
  const leftSession = left.session || left.sessions[0] || null;
  const rightSession = right.session || right.sessions[0] || null;
  const order = new Map((model.harnessOrder || []).map((harness, index) => [harness, index]));
  const harnessIndex = session => {
    const key = String(session && session.harness || "");
    return order.has(key) ? order.get(key) : Number.MAX_SAFE_INTEGER;
  };
  const leftHarness = harnessIndex(leftSession);
  const rightHarness = harnessIndex(rightSession);
  if(leftHarness !== rightHarness) return leftHarness - rightHarness;
  const compareText = (one, two) => String(one == null ? "" : one).localeCompare(
    String(two == null ? "" : two), "en",
  );
  const project = compareText(leftSession && leftSession.project, rightSession && rightSession.project);
  if(project) return project;
  const sid = compareText(leftSession && leftSession.sid, rightSession && rightSession.sid);
  if(sid) return sid;
  if(left.sourceIndex !== right.sourceIndex) return left.sourceIndex - right.sourceIndex;
  return compareText(left.key, right.key);
}

function nextAttentionCompareSubjects(left, right, model){
  const kindOrder = {ask: 0, input: 1};
  const leftKind = kindOrder[left.primaryKind] == null ? 2 : kindOrder[left.primaryKind];
  const rightKind = kindOrder[right.primaryKind] == null ? 2 : kindOrder[right.primaryKind];
  if(leftKind !== rightKind) return leftKind - rightKind;
  if(left.primaryKind === "ask" && right.primaryKind === "ask"){
    const leftAge = Math.max(...left.asks.map(nextAttentionAskAge).filter(age => age != null), -1);
    const rightAge = Math.max(...right.asks.map(nextAttentionAskAge).filter(age => age != null), -1);
    if(leftAge !== rightAge) return rightAge - leftAge;
    if(leftAge >= 0 && left.sourceIndex !== right.sourceIndex){
      return left.sourceIndex - right.sourceIndex;
    }
  }
  if(left.primaryKind === "input" && right.primaryKind === "input"){
    const leftAge = nextPayloadAgeSeconds({generated: model.generated}, left.session && left.session.blocked_since);
    const rightAge = nextPayloadAgeSeconds({generated: model.generated}, right.session && right.session.blocked_since);
    if(leftAge != null && rightAge == null) return -1;
    if(leftAge == null && rightAge != null) return 1;
    if(leftAge != null && rightAge != null && leftAge !== rightAge) return rightAge - leftAge;
  }
  return nextAttentionStableCompare(left, right, model);
}

function nextAttentionRateCoverage(_discoveredHarnesses){
  return {reported: 0, notReported: 0, failed: 0, rows: []};
}

function nextAttentionCoverage(payload){
  return {
    gates: {discovered: 0, reporting: 0, unknown: 0, failed: 0, rows: []},
    exactRequestsReported: !!(payload && payload.ask === true),
    rates: nextAttentionRateCoverage([]),
    observedStops: 0,
    ends: "fleet coverage not reported",
  };
}

function nextAttentionProjectSummary(model, sessions){
  const memberKeys = new Set(nextPayloadSessions({sessions}).map(nextSessionKey));
  const needs = (model && Array.isArray(model.needs) ? model.needs : []).filter(subject =>
    subject.session && memberKeys.has(nextSessionKey(subject.session)));
  const rows = nextPayloadSessions({sessions});
  return {
    exactRequests: needs.reduce((total, subject) => total + subject.asks.length, 0),
    risk: 0,
    close: 0,
    working: rows.filter(session => session.state === "working").length,
    quiet: rows.filter(session => session.state === "idle").length,
  };
}

function nextAttentionSectionForKey(model, key){
  for(const section of ["needs", "risk", "close", "next"]){
    if(Array.isArray(model && model[section]) && model[section].some(subject => subject.key === key)){
      return section;
    }
  }
  return null;
}

function nextAttentionModel(payload){
  const sessions = nextPayloadSessions(payload);
  const asks = nextPayloadAsks(payload);
  const subjects = new Map();
  const matchedAskOwners = new Set();

  for(const [sourceIndex, ask] of asks.entries()){
    const question = String(ask.question == null ? "" : ask.question).trim();
    if(!question) continue;
    const owner = nextExactAskOwner(payload, ask);
    if(!owner){
      const subject = {
        key: nextAttentionAskKey(ask, sourceIndex), kind: "ask", section: "needs", primaryKind: "ask",
        signals: [{kind: "ask", section: "needs", detail: {ask}, sourceIndex}], session: null,
        sessions: [], asks: [ask], sourceIndex, responsibility: "NEEDS YOU",
      };
      subjects.set(subject.key, subject);
      continue;
    }
    const key = nextSessionKey(owner);
    let subject = subjects.get(key);
    if(!subject){
      subject = {
        key, kind: "session", section: "needs", primaryKind: "ask", signals: [], session: owner,
        sessions: [owner], asks: [], sourceIndex, responsibility: nextAskResponsibility(payload, ask),
      };
      const checkpoint = nextPublishedTask(owner);
      if(checkpoint) subject.checkpoint = checkpoint;
      subjects.set(key, subject);
    }
    subject.asks.push(ask);
    subject.signals.push({kind: "ask", section: "needs", detail: {ask}, sourceIndex});
    const askProject = String(ask.project == null ? "" : ask.project).trim();
    if(askProject && askProject !== String(owner.project == null ? "" : owner.project)){
      subject.signals.push({
        kind: "attribution", section: "needs", detail: {ask, owner}, sourceIndex,
      });
    }
    matchedAskOwners.add(key);
  }

  for(const [sourceIndex, session] of sessions.entries()){
    const key = nextSessionKey(session);
    if(session.state !== "needs_input" || matchedAskOwners.has(key)) continue;
    const subject = {
      key, kind: "session", section: "needs", primaryKind: "input",
      signals: [{kind: "input", section: "needs", detail: {session}, sourceIndex}], session,
      sessions: [session], asks: [], sourceIndex,
    };
    const checkpoint = nextPublishedTask(session);
    if(checkpoint) subject.checkpoint = checkpoint;
    subjects.set(key, subject);
  }

  const needs = [...subjects.values()].sort((left, right) => nextAttentionCompareSubjects(
    left, right, {generated: nextNumber(payload && payload.generated), harnessOrder: nextAttentionHarnessOrder(payload)},
  ));
  const represented = new Set(needs.flatMap(subject => subject.sessions.map(nextSessionKey)));
  const healthySessions = sessions.filter(session => !represented.has(nextSessionKey(session)));
  const moving = healthySessions.filter(session => session.state === "working").length;
  const quiet = healthySessions.filter(session => session.state === "idle").length;
  const unknown = healthySessions.length - moving - quiet;
  const model = {
    needs, risk: [], close: [], next: [],
    healthy: {sessions: healthySessions, moving, quiet, unknown},
    coverage: nextAttentionCoverage(payload),
    counts: {needs: needs.length, risk: 0, close: 0, next: 0, moving, quiet, unknown},
    harnessOrder: nextAttentionHarnessOrder(payload),
    representedSessionKeys: [...represented],
    generated: nextNumber(payload && payload.generated),
    windowHours: nextNumber(payload && payload.window_hours),
  };
  return model;
}

function nextAttentionSubjectRoute(subject){
  if(!subject || !subject.session) return "";
  const project = String(subject.session.project == null ? "" : subject.session.project);
  const sid = String(subject.session.sid == null ? "" : subject.session.sid);
  return project && sid ? nextRouteToken({view: "session", project, session: sid}) : "";
}

function nextAttentionSubjectHtml(subject, model){
  const route = nextAttentionSubjectRoute(subject);
  const title = subject.primaryKind === "ask" ? "Question waiting" : "Input signal observed";
  const heading = route
    ? `<a href="#n=${esc(route)}" data-next-route="${esc(route)}">${esc(title)}</a>`
    : esc(title);
  const questions = subject.asks.map(ask => {
    const question = esc(String(ask.question || "").trim());
    return `<p>${subject.responsibility ? `${esc(subject.responsibility)} — ` : ""}${question}</p>`;
  }).join("");
  const blockedAge = subject.primaryKind === "input" && subject.session
    ? nextPayloadAgeSeconds({generated: model.generated}, subject.session.blocked_since)
    : null;
  const detailText = subject.primaryKind === "input" && subject.session && subject.session.state_detail
    ? esc(subject.session.state_detail)
    : "";
  const detail = detailText || blockedAge != null
    ? `<p>${detailText}${detailText && blockedAge != null ? " · " : ""}` +
      `${blockedAge != null ? esc(nextFormatDuration(blockedAge)) : ""}</p>`
    : "";
  const checkpoint = subject.checkpoint && (subject.checkpoint.activeForm || subject.checkpoint.subject);
  const next = checkpoint ? `<p><span>NEXT</span> ${esc(checkpoint)}</p>` : "";
  const attribution = subject.signals.some(signal => signal.kind === "attribution")
    ? "<p>Sources disagree</p>"
    : "";
  return `<li><article data-next-attention-subject="${esc(subject.key)}"><h3>${heading}</h3>` +
    `${questions}${detail}${attribution}${next}</article></li>`;
}

function nextAttentionView(model){
  const needs = model && Array.isArray(model.needs) ? model.needs : [];
  const section = needs.length
    ? `<section data-next-attention-section="needs"><h2>NEEDS YOU NOW (${needs.length})</h2>` +
      `<ol>${needs.map(subject => nextAttentionSubjectHtml(subject, model)).join("")}</ol></section>`
    : "";
  return `<section class="next-attention" data-next-view-body="attention"><h1>Attention</h1>${section}</section>`;
}
