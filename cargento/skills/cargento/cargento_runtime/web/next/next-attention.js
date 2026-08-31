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

const NEXT_RISK_KIND_ORDER = new Map([
  ["attribution", 0], ["loop", 1], ["quota", 2], ["long-turn", 3], ["collision", 4],
]);

function nextAttentionRiskKind(signal){
  return NEXT_RISK_KIND_ORDER.has(signal && signal.kind) ? signal.kind : "collision";
}

function nextAttentionSubjectIdentity(subject){
  if(subject && subject.identity) return subject.identity;
  if(subject && subject.session) return subject.session;
  return subject && Array.isArray(subject.sessions) ? subject.sessions[0] || null : null;
}

function nextAttentionStableCompare(left, right, model){
  const leftSession = nextAttentionSubjectIdentity(left);
  const rightSession = nextAttentionSubjectIdentity(right);
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
  const leftSourceIndex = Number.isInteger(left.sourceIndex) ? left.sourceIndex : Number.MAX_SAFE_INTEGER;
  const rightSourceIndex = Number.isInteger(right.sourceIndex) ? right.sourceIndex : Number.MAX_SAFE_INTEGER;
  if(leftSourceIndex !== rightSourceIndex) return leftSourceIndex - rightSourceIndex;
  return compareText(left.stableId || left.key, right.stableId || right.key);
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
  if(left.section === "risk" && right.section === "risk"){
    const leftKind = nextAttentionRiskKind(left.signals[0]);
    const rightKind = nextAttentionRiskKind(right.signals[0]);
    const kindOrder = NEXT_RISK_KIND_ORDER.get(leftKind) - NEXT_RISK_KIND_ORDER.get(rightKind);
    if(kindOrder) return kindOrder;
    const leftDetail = left.signals[0].detail;
    const rightDetail = right.signals[0].detail;
    if(leftKind === "attribution" && left.sourceIndex !== right.sourceIndex){
      return left.sourceIndex - right.sourceIndex;
    }
    if(leftKind === "loop" && leftDetail.errors !== rightDetail.errors){
      return rightDetail.errors - leftDetail.errors;
    }
    if(leftKind === "quota"){
      if(leftDetail.pct !== rightDetail.pct) return rightDetail.pct - leftDetail.pct;
      const leftReset = leftDetail.resetAt;
      const rightReset = rightDetail.resetAt;
      if(leftReset != null && rightReset == null) return -1;
      if(leftReset == null && rightReset != null) return 1;
      if(leftReset != null && rightReset != null && leftReset !== rightReset){
        return leftReset - rightReset;
      }
    }
    if(leftKind === "collision" && leftDetail.memberCount !== rightDetail.memberCount){
      return rightDetail.memberCount - leftDetail.memberCount;
    }
  }
  return nextAttentionStableCompare(left, right, model);
}

function nextAttentionLoopSignal(session, sourceIndex){
  const loop = session && session.loop;
  if(!loop || typeof loop !== "object" || Array.isArray(loop) || !Number.isInteger(loop.errors) ||
    loop.errors <= 0) return null;
  const detail = {errors: loop.errors};
  const tool = typeof loop.tool === "string" ? loop.tool.trim() : "";
  if(tool) detail.tool = tool;
  return {kind: "loop", section: "risk", sourceIndex, detail};
}

function nextAttentionLongTurnSignal(session, sourceIndex){
  const turn = session && session.turn;
  if(session && session.state === "working" && turn && typeof turn === "object" &&
    !Array.isArray(turn) && turn.long === true){
    return {kind: "long-turn", section: "risk", sourceIndex, detail: {session}};
  }
  return null;
}

function nextAttentionQuotaSignal(entry, scope, row, sourceIndex){
  if(!entry || entry.state !== "ok" || !row || !Number.isInteger(row.pct) || row.pct < 70){
    return null;
  }
  const resetAt = typeof row.resetAt === "number" && Number.isFinite(row.resetAt) && row.resetAt > 0
    ? row.resetAt
    : null;
  return {kind: "quota", section: "risk", sourceIndex,
    detail: {harness: String(entry.harness || ""), scope, pct: row.pct,
      resetAt, tone: row.pct >= 90 ? "critical" : "warning"}};
}

function nextAttentionAttributionSignal(session, sourceIndex){
  const finishedAt = nextNumber(session && session.finished_at);
  const validFinishedAt = finishedAt != null && finishedAt > 0;
  const publishedGit = typeof (session && session.dirty) === "boolean" ||
    Number.isInteger(session && session.changed);
  const active = session && (session.state === "working" || session.active === true);
  if((publishedGit && !validFinishedAt) || (validFinishedAt && active)){
    return {kind: "attribution", section: "risk", sourceIndex, detail: {
      finishedAt: validFinishedAt ? finishedAt : null,
      dirty: typeof (session && session.dirty) === "boolean" ? session.dirty : null,
      changed: Number.isInteger(session && session.changed) ? session.changed : null,
      state: String(session && session.state || ""), active: session && session.active === true,
    }};
  }
  return null;
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
  const riskSubjects = new Map();
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

  const addSessionRisk = (session, signal, sourceIndex) => {
    if(!signal) return;
    const key = nextSessionKey(session);
    const needsSubject = subjects.get(key);
    if(needsSubject && needsSubject.section === "needs"){
      needsSubject.signals.push({...signal, section: "needs"});
      return;
    }
    let subject = riskSubjects.get(key);
    if(!subject){
      subject = {
        key, stableId: key, kind: "session", section: "risk", primaryKind: signal.kind,
        signals: [], session, sessions: [session], asks: [], sourceIndex,
      };
      riskSubjects.set(key, subject);
    }
    subject.signals.push(signal);
    subject.signals.sort((left, right) => NEXT_RISK_KIND_ORDER.get(nextAttentionRiskKind(left)) -
      NEXT_RISK_KIND_ORDER.get(nextAttentionRiskKind(right)));
    subject.primaryKind = subject.signals[0].kind;
    subject.sourceIndex = subject.signals[0].sourceIndex;
  };

  for(const [sourceIndex, session] of sessions.entries()){
    addSessionRisk(session, nextAttentionAttributionSignal(session, sourceIndex), sourceIndex);
    addSessionRisk(session, nextAttentionLoopSignal(session, sourceIndex), sourceIndex);
    addSessionRisk(session, nextAttentionLongTurnSignal(session, sourceIndex), sourceIndex);
  }

  const usage = payload && typeof payload === "object" && !Array.isArray(payload) &&
    Array.isArray(payload.usage) ? payload.usage : [];
  for(const [usageIndex, entry] of usage.entries()){
    if(!entry || typeof entry !== "object" || Array.isArray(entry)) continue;
    const harness = String(entry.harness || "");
    const addQuota = (scope, row, sourceIndex) => {
      const signal = nextAttentionQuotaSignal(entry, scope, row, sourceIndex);
      if(!signal) return;
      const key = `quota:${harness}:${scope}`;
      const subject = {
        key, stableId: scope, kind: "quota", section: "risk", primaryKind: "quota",
        signals: [signal], session: null, sessions: [], asks: [], sourceIndex,
        identity: {harness, project: scope, sid: ""},
      };
      if(signal.detail.resetAt != null) subject.checkpoint = {resetAt: signal.detail.resetAt};
      riskSubjects.set(key, subject);
    };
    for(const scope of ["fiveH", "week", "month"]){
      addQuota(scope, entry[scope], usageIndex);
    }
    const models = Array.isArray(entry.models) ? entry.models : [];
    for(const [modelIndex, row] of models.entries()){
      const label = typeof (row && row.label) === "string" ? row.label : "";
      addQuota(`model:${label}:${modelIndex}`, row, usageIndex);
    }
  }

  const labels = new Map();
  for(const [sourceIndex, session] of sessions.entries()){
    const label = typeof session.project === "string" && session.project.trim() ? session.project : "";
    if(!label) continue;
    if(!labels.has(label)) labels.set(label, []);
    labels.get(label).push({session, sourceIndex});
  }
  const harnessOrder = nextAttentionHarnessOrder(payload);
  const harnessRank = harness => {
    const index = harnessOrder.indexOf(String(harness || ""));
    return index < 0 ? Number.MAX_SAFE_INTEGER : index;
  };
  for(const [label, memberRows] of labels){
    if(memberRows.length < 2) continue;
    const members = memberRows.map(row => row.session);
    const memberKeys = members.map(nextSessionKey);
    const identity = [...members].sort((left, right) => {
      const harness = harnessRank(left.harness) - harnessRank(right.harness);
      if(harness) return harness;
      const sid = String(left.sid || "").localeCompare(String(right.sid || ""), "en");
      return sid || String(left.harness || "").localeCompare(String(right.harness || ""), "en");
    })[0];
    const key = `collision:${label}`;
    riskSubjects.set(key, {
      key, stableId: key, kind: "collision", section: "risk", primaryKind: "collision",
      signals: [{kind: "collision", section: "risk", sourceIndex: Math.min(
        ...memberRows.map(row => row.sourceIndex),
      ),
        detail: {label, memberCount: members.length}}],
      session: null, sessions: members, asks: [], memberKeys,
      sourceIndex: Math.min(...memberRows.map(row => row.sourceIndex)), identity,
    });
  }

  const needs = [...subjects.values()].sort((left, right) => nextAttentionCompareSubjects(
    left, right, {generated: nextNumber(payload && payload.generated), harnessOrder: nextAttentionHarnessOrder(payload)},
  ));
  const risk = [...riskSubjects.values()].sort((left, right) => nextAttentionCompareSubjects(
    left, right, {generated: nextNumber(payload && payload.generated), harnessOrder: nextAttentionHarnessOrder(payload)},
  ));
  const represented = new Set(needs.flatMap(subject => subject.sessions.map(nextSessionKey)));
  for(const subject of risk){
    for(const memberKey of subject.memberKeys || subject.sessions.map(nextSessionKey)) represented.add(memberKey);
  }
  const healthySessions = sessions.filter(session => !represented.has(nextSessionKey(session)));
  const moving = healthySessions.filter(session => session.state === "working").length;
  const quiet = healthySessions.filter(session => session.state === "idle").length;
  const unknown = healthySessions.length - moving - quiet;
  const model = {
    needs, risk, close: [], next: [],
    healthy: {sessions: healthySessions, moving, quiet, unknown},
    coverage: nextAttentionCoverage(payload),
    counts: {needs: needs.length, risk: risk.length, close: 0, next: 0, moving, quiet, unknown},
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
