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
const NEXT_STOP_KIND_ORDER = new Map([
  ["stop-dirty", 0], ["stop-unknown", 1], ["stop-clean", 2],
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
  if(left.section === "close" && right.section === "close"){
    const leftKind = NEXT_STOP_KIND_ORDER.get(left.primaryKind);
    const rightKind = NEXT_STOP_KIND_ORDER.get(right.primaryKind);
    if(leftKind !== rightKind) return leftKind - rightKind;
    const leftFinishedAt = left.signals[0].detail.finishedAt;
    const rightFinishedAt = right.signals[0].detail.finishedAt;
    if(leftFinishedAt !== rightFinishedAt) return leftFinishedAt - rightFinishedAt;
  }
  if(left.section === "next" && right.section === "next"){
    const leftStatus = left.checkpoint && left.checkpoint.status;
    const rightStatus = right.checkpoint && right.checkpoint.status;
    const leftStatusOrder = leftStatus === "in_progress" ? 0 : 1;
    const rightStatusOrder = rightStatus === "in_progress" ? 0 : 1;
    if(leftStatusOrder !== rightStatusOrder) return leftStatusOrder - rightStatusOrder;
    const leftWorking = left.session && left.session.state === "working";
    const rightWorking = right.session && right.session.state === "working";
    const leftIdle = left.session && left.session.state === "idle";
    const rightIdle = right.session && right.session.state === "idle";
    if(leftWorking && rightIdle) return -1;
    if(leftIdle && rightWorking) return 1;
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

function nextAttentionQuotaSignalCompare(left, right){
  const leftDetail = left.detail;
  const rightDetail = right.detail;
  if(leftDetail.pct !== rightDetail.pct) return rightDetail.pct - leftDetail.pct;
  const leftReset = leftDetail.resetAt;
  const rightReset = rightDetail.resetAt;
  if(leftReset != null && rightReset == null) return -1;
  if(leftReset == null && rightReset != null) return 1;
  if(leftReset != null && rightReset != null && leftReset !== rightReset){
    return leftReset - rightReset;
  }
  return left.sourceIndex - right.sourceIndex;
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

function nextAttentionStopSignal(session, sourceIndex){
  const finished = typeof session.finished_at === "number" &&
    Number.isFinite(session.finished_at) && session.finished_at > 0;
  if(!finished || session.state !== "idle") return null;
  let kind = "stop-unknown";
  if(session.dirty === true) kind = "stop-dirty";
  if(session.dirty === false) kind = "stop-clean";
  return {kind, section: "close", sourceIndex, detail: {
    finishedAt: session.finished_at,
    changedEntries: Number.isInteger(session.changed) && session.changed >= 0 ? session.changed : null,
  }};
}

function nextAttentionRateCoverage(discovered){
  const failed = discovered.filter(row => row.error != null);
  const reported = discovered.filter(row => row.error == null && row.reports_rate === true);
  const notReported = discovered.filter(row => row.error == null && row.reports_rate === false);
  return {
    reported: reported.length, notReported: notReported.length, failed: failed.length,
    rows: discovered,
  };
}

function nextAttentionCoverage(payload){
  const rows = payload && typeof payload === "object" && !Array.isArray(payload) &&
    Array.isArray(payload.harnesses) ? payload.harnesses : [];
  const discovered = rows.filter(row => row && row.discovered === true);
  const failed = discovered.filter(row => row.error != null);
  const reporting = discovered.filter(row =>
    row.error == null && row.reports_needs_input === true
  );
  const unknown = discovered.filter(row =>
    row.error == null && row.reports_needs_input !== true
  );
  return {
    gates: {
      discovered: discovered.length, reporting: reporting.length,
      unknown: unknown.length, failed: failed.length, rows: discovered,
    },
    exactRequestsReported: !!(payload && payload.ask === true),
    exactRequestCount: nextPayloadAsks(payload).length,
    rates: nextAttentionRateCoverage(discovered),
    observedStops: nextPayloadSessions(payload).filter(session =>
      typeof session.finished_at === "number" && Number.isFinite(session.finished_at) &&
        session.finished_at > 0
    ).length,
    ends: "fleet coverage not reported",
  };
}

function nextAttentionProjectSummary(model, sessions){
  const all = model.needs.concat(model.risk, model.close, model.next);
  const rows = nextPayloadSessions({sessions});
  const keys = new Set(rows.map(nextSessionKey));
  const sessionSubjects = all.filter(item =>
    item.session && keys.has(nextSessionKey(item.session)));
  const collisionSubjects = model.risk.filter(item => item.kind === "collision" &&
    item.sessions.some(session => keys.has(nextSessionKey(session))));
  return {
    exactRequests: sessionSubjects.reduce((total, item) => total + item.asks.length, 0),
    risk: sessionSubjects.filter(item => item.section === "risk").length + collisionSubjects.length,
    close: sessionSubjects.filter(item => item.section === "close").length,
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
      let subject = riskSubjects.get(key);
      if(!subject){
        subject = {
          key, stableId: scope, kind: "quota", section: "risk", primaryKind: "quota",
          signals: [], session: null, sessions: [], asks: [], sourceIndex,
          identity: {harness, project: scope, sid: ""},
        };
        riskSubjects.set(key, subject);
      }
      subject.signals.push(signal);
      subject.signals.sort(nextAttentionQuotaSignalCompare);
      subject.sourceIndex = subject.signals[0].sourceIndex;
      if(subject.signals[0].detail.resetAt != null){
        subject.checkpoint = {resetAt: subject.signals[0].detail.resetAt};
      }else{
        delete subject.checkpoint;
      }
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
    if(!labels.has(label)) labels.set(label, new Map());
    const members = labels.get(label);
    const key = nextSessionKey(session);
    if(!members.has(key)) members.set(key, {session, sourceIndex});
  }
  const harnessOrder = nextAttentionHarnessOrder(payload);
  const harnessRank = harness => {
    const index = harnessOrder.indexOf(String(harness || ""));
    return index < 0 ? Number.MAX_SAFE_INTEGER : index;
  };
  for(const [label, members] of labels){
    const memberRows = [...members.values()];
    if(memberRows.length < 2) continue;
    const memberSessions = memberRows.map(row => row.session);
    const memberKeys = memberSessions.map(nextSessionKey);
    const identity = [...memberSessions].sort((left, right) => {
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
        detail: {label, memberCount: memberSessions.length}}],
      session: null, sessions: memberSessions, asks: [], memberKeys,
      sourceIndex: Math.min(...memberRows.map(row => row.sourceIndex)), identity,
    });
  }

  const collisionByMemberKey = new Map();
  for(const subject of riskSubjects.values()){
    if(subject.kind !== "collision") continue;
    for(const memberKey of subject.memberKeys || []){
      if(!collisionByMemberKey.has(memberKey)) collisionByMemberKey.set(memberKey, subject);
    }
  }

  const riskRepresented = new Set();
  for(const subject of riskSubjects.values()){
    for(const memberKey of subject.memberKeys || subject.sessions.map(nextSessionKey)){
      riskRepresented.add(memberKey);
    }
  }
  const closeSubjects = new Map();
  const attachedStopKeys = new Set();
  for(const [sourceIndex, session] of sessions.entries()){
    const key = nextSessionKey(session);
    const signal = nextAttentionStopSignal(session, sourceIndex);
    if(!signal || attachedStopKeys.has(key)) continue;
    const winningSubject = subjects.get(key) || riskSubjects.get(key) || collisionByMemberKey.get(key);
    if(winningSubject){
      const attached = winningSubject.kind === "collision"
        ? {...signal, detail: {...signal.detail, session}}
        : signal;
      winningSubject.signals.push(attached);
      attachedStopKeys.add(key);
      continue;
    }
    if(riskRepresented.has(key) || closeSubjects.has(key)) continue;
    closeSubjects.set(key, {
      key, stableId: key, kind: "session", section: "close", primaryKind: signal.kind,
      signals: [signal], session, sessions: [session], asks: [], sourceIndex,
    });
    attachedStopKeys.add(key);
  }

  const comparatorModel = {
    generated: nextNumber(payload && payload.generated), harnessOrder: nextAttentionHarnessOrder(payload),
  };
  const needs = [...subjects.values()].sort((left, right) => nextAttentionCompareSubjects(
    left, right, comparatorModel,
  ));
  const risk = [...riskSubjects.values()].sort((left, right) => nextAttentionCompareSubjects(
    left, right, comparatorModel,
  ));
  const close = [...closeSubjects.values()].sort((left, right) => nextAttentionCompareSubjects(
    left, right, comparatorModel,
  ));
  const represented = new Set(needs.flatMap(subject => subject.sessions.map(nextSessionKey)));
  for(const subject of risk){
    for(const memberKey of subject.memberKeys || subject.sessions.map(nextSessionKey)) represented.add(memberKey);
  }
  for(const subject of close){
    for(const session of subject.sessions) represented.add(nextSessionKey(session));
  }
  const nextSubjects = new Map();
  const attachedTaskKeys = new Set();
  for(const [sourceIndex, session] of sessions.entries()){
    const key = nextSessionKey(session);
    const checkpoint = nextPublishedTask(session);
    if(!checkpoint || attachedTaskKeys.has(key)) continue;
    const winningSubject = subjects.get(key) || riskSubjects.get(key) || closeSubjects.get(key) ||
      collisionByMemberKey.get(key);
    if(winningSubject){
      winningSubject.signals.push({
        kind: "task", section: "next", detail: {task: checkpoint, session}, sourceIndex,
      });
      if(!winningSubject.checkpoint) winningSubject.checkpoint = checkpoint;
      attachedTaskKeys.add(key);
      continue;
    }
    if(represented.has(key) || nextSubjects.has(key)) continue;
    nextSubjects.set(key, {
      key, stableId: key, kind: "session", section: "next", primaryKind: "task",
      signals: [{kind: "task", section: "next", detail: {task: checkpoint, session}, sourceIndex}],
      session, sessions: [session], asks: [], sourceIndex, checkpoint,
    });
    attachedTaskKeys.add(key);
  }
  const next = [...nextSubjects.values()].sort((left, right) => nextAttentionCompareSubjects(
    left, right, comparatorModel,
  ));
  for(const subject of next){
    for(const session of subject.sessions) represented.add(nextSessionKey(session));
  }
  const healthyByKey = new Map();
  for(const session of sessions){
    const key = nextSessionKey(session);
    if(!represented.has(key) && !healthyByKey.has(key)) healthyByKey.set(key, session);
  }
  const healthySessions = [...healthyByKey.values()];
  const moving = healthySessions.filter(session => session.state === "working").length;
  const quiet = healthySessions.filter(session => session.state === "idle").length;
  const unknown = healthySessions.length - moving - quiet;
  const model = {
    needs, risk, close, next,
    healthy: {sessions: healthySessions, moving, quiet, unknown},
    coverage: nextAttentionCoverage(payload),
    counts: {needs: needs.length, risk: risk.length, close: close.length, next: next.length, moving, quiet, unknown},
    harnessOrder: nextAttentionHarnessOrder(payload),
    representedSessionKeys: [...represented],
    generated: nextNumber(payload && payload.generated),
    windowHours: nextNumber(payload && payload.window_hours),
    sessionCount: sessions.length,
  };
  return model;
}

function nextAttentionSubjectRoute(subject){
  const identity = nextAttentionSubjectIdentity(subject);
  const project = String(identity && identity.project != null ? identity.project : "");
  const harness = String(identity && identity.harness != null ? identity.harness : "");
  const sid = String(identity && identity.sid != null ? identity.sid : "");
  return project && sid
    ? nextRouteToken({view: "session", project, harness, session: sid})
    : nextRouteToken({view: "sessions"});
}

const NEXT_ATTENTION_KIND_LABELS = new Map([
  ["ask", "Question waiting"],
  ["input", "Input signal observed"],
  ["attribution", "Attribution conflict"],
  ["loop", "Repeated tool failures"],
  ["quota", "Quota pressure"],
  ["long-turn", "Long-running turn"],
  ["collision", "Identity collision"],
  ["stop-dirty", "Stop observed with uncommitted work"],
  ["stop-clean", "Stop observed; git state clean"],
  ["stop-unknown", "Stop observed; git state not measured"],
  ["task", "Published task"],
]);

function nextAttentionEsc(value){
  return esc(value).replace(/=/g, "&#61;");
}

function nextAttentionHarnessLabel(model, harness){
  const key = String(harness == null ? "" : harness);
  const rows = model && model.coverage && model.coverage.gates &&
    Array.isArray(model.coverage.gates.rows) ? model.coverage.gates.rows : [];
  const row = rows.find(item => String(item && item.key || "") === key);
  const label = String(row && row.label != null ? row.label : "").trim();
  return label || key || "Source not identified";
}

function nextAttentionAskedAssignment(session){
  const instruction = session && session.instruction;
  if(!instruction || typeof instruction !== "object" || Array.isArray(instruction) ||
    instruction.label !== "asked" || typeof instruction.text !== "string") return "";
  return instruction.text.trim();
}

function nextAttentionWorkflowGoal(session){
  const spacedock = session && session.spacedock;
  const workflows = spacedock && typeof spacedock === "object" && !Array.isArray(spacedock) &&
    Array.isArray(spacedock.workflows) ? spacedock.workflows : [];
  const goals = [];
  for(const workflow of workflows){
    const goal = workflow && typeof workflow.goal === "string" ? workflow.goal.trim() : "";
    if(goal && !goals.includes(goal)) goals.push(goal);
  }
  return goals.length === 1 ? goals[0] : "";
}

function nextAttentionSubjectIdentityText(subject, model){
  if(subject && subject.kind === "quota"){
    const identity = nextAttentionSubjectIdentity(subject);
    return `${nextAttentionHarnessLabel(model, identity && identity.harness)} · ` +
      `${String(identity && identity.project || "Quota window")}`;
  }
  if(subject && subject.kind === "collision"){
    const signal = subject.signals && subject.signals[0];
    const detail = signal && signal.detail || {};
    return `${String(detail.label || "Unlabelled display")} display label · ` +
      `${Number(detail.memberCount) || 0} exact sessions`;
  }
  const identity = nextAttentionSubjectIdentity(subject);
  if(identity){
    const project = String(identity.project == null ? "" : identity.project) || "Unlabelled display";
    const harness = nextAttentionHarnessLabel(model, identity.harness);
    const sid = String(identity.sid == null ? "" : identity.sid) || "identity not reported";
    return `${project} · ${harness} · ${sid}`;
  }
  const ask = subject && Array.isArray(subject.asks) ? subject.asks[0] : null;
  const project = String(ask && ask.project == null ? "" : ask && ask.project) ||
    "Unlabelled display";
  const harness = nextAttentionHarnessLabel(model, ask && ask.harness);
  const sid = String(ask && ask.session_id == null ? "" : ask && ask.session_id) ||
    "identity not reported";
  return `${project} · ${harness} · ${sid}`;
}

function nextAttentionOutcome(subject, model){
  const session = subject && subject.session;
  const assignment = nextAttentionAskedAssignment(session);
  if(assignment) return {label: "OUTCOME", text: assignment};
  const goal = nextAttentionWorkflowGoal(session);
  if(goal) return {label: "OUTCOME", text: goal};
  return {label: "IDENTITY", text: nextAttentionSubjectIdentityText(subject, model)};
}

function nextAttentionAttributionNow(detail){
  if(detail && detail.ask && detail.owner){
    const askProject = String(detail.ask.project == null ? "" : detail.ask.project);
    const ownerProject = String(detail.owner.project == null ? "" : detail.owner.project);
    return `Sources disagree · request display label: ${askProject} · ` +
      `session display label: ${ownerProject}`;
  }
  const readings = [];
  if(detail && detail.state) readings.push(`state: ${detail.state}`);
  if(detail && detail.active === true) readings.push("active: true");
  if(detail && detail.finishedAt != null) readings.push(`stop observed: ${detail.finishedAt}`);
  if(detail && detail.dirty != null) readings.push(`dirty: ${detail.dirty}`);
  if(detail && detail.changed != null) readings.push(`changed entries: ${detail.changed}`);
  return readings.length ? `Sources disagree · ${readings.join(" · ")}` : "Sources disagree";
}

function nextAttentionSignalNow(signal, subject){
  const detail = signal && signal.detail || {};
  if(signal.kind === "ask"){
    const ask = detail.ask;
    const question = String(ask && ask.question == null ? "" : ask && ask.question).trim();
    const options = Array.isArray(ask && ask.options) ? ask.options.length : 0;
    return {text: question, note: options ? `${options} published options` : ""};
  }
  if(signal.kind === "input"){
    const text = String(subject.session && subject.session.state_detail || "").trim();
    return {text: text || "Needs-input state reported", note: ""};
  }
  if(signal.kind === "attribution"){
    return {text: nextAttentionAttributionNow(detail), note: ""};
  }
  if(signal.kind === "loop"){
    const tool = String(detail.tool == null ? "" : detail.tool).trim();
    const text = tool
      ? `${tool} failed ${detail.errors} times`
      : `Tool failures reported ${detail.errors} times`;
    return {text, note: ""};
  }
  if(signal.kind === "quota") return {text: `${detail.pct}% reported`, note: ""};
  if(signal.kind === "long-turn"){
    const session = subject.session || detail.session || {};
    const state = String(session.state_detail || "Working").trim() || "Working";
    const elapsed = session.turn && typeof session.turn.elapsed_h === "string"
      ? session.turn.elapsed_h.trim()
      : "";
    return {text: elapsed ? `${state} · ${elapsed} elapsed` : state, note: ""};
  }
  if(signal.kind === "collision"){
    return {
      text: `${detail.memberCount} exact sessions share ${String(detail.label || "")} display label`,
      note: "Identity scope only; shared location is not established",
    };
  }
  if(signal.kind === "stop-dirty"){
    const changed = Number.isInteger(detail.changedEntries)
      ? `${detail.changedEntries} changed entries`
      : "Uncommitted work observed";
    return {text: changed, note: ""};
  }
  if(signal.kind === "stop-clean") return {text: "Git state reported clean", note: ""};
  if(signal.kind === "stop-unknown"){
    return {text: "Git state was not measured", note: ""};
  }
  if(signal.kind === "task"){
    const status = subject.checkpoint && subject.checkpoint.status;
    return {text: status === "in_progress" ? "In progress" : "Pending", note: ""};
  }
  return {text: "Source signal observed", note: ""};
}

function nextAttentionSignalAttribution(signal, model){
  const session = signal && signal.detail && signal.detail.session;
  if(!session) return "";
  return nextAttentionSubjectIdentityText({session}, model);
}

function nextAttentionSubjectNow(subject, model){
  const signals = subject && Array.isArray(subject.signals) ? subject.signals : [];
  const rows = [];
  for(const [index, signal] of signals.entries()){
    if(signal.kind === "task" && subject.primaryKind !== "task") continue;
    const row = nextAttentionSignalNow(signal, subject);
    if(!row.text) continue;
    const secondary = index > 0;
    const label = NEXT_ATTENTION_KIND_LABELS.get(signal.kind) || "Source signal observed";
    const attribution = nextAttentionSignalAttribution(signal, model);
    const prefix = [attribution, secondary ? label : ""].filter(Boolean).join(" · ");
    rows.push({...row, text: prefix ? `${prefix}: ${row.text}` : row.text});
  }
  return rows;
}

function nextAttentionCheckpointText(subject){
  const checkpoint = subject && subject.checkpoint;
  if(!checkpoint) return "";
  const task = String(checkpoint.activeForm || checkpoint.subject || "").trim();
  if(task) return task;
  if(typeof checkpoint.resetAt === "number" && Number.isFinite(checkpoint.resetAt)){
    const instant = new Date(checkpoint.resetAt * 1000);
    return Number.isNaN(instant.getTime()) ? "" : `Reset at ${instant.toISOString()}`;
  }
  return "";
}

function nextAttentionCheckpointRows(subject, model){
  const rows = [];
  const signals = subject && Array.isArray(subject.signals) ? subject.signals : [];
  for(const signal of signals){
    if(signal.kind !== "task") continue;
    const task = signal.detail && signal.detail.task;
    const text = String(task && (task.activeForm || task.subject) || "").trim();
    if(!text) continue;
    const attribution = nextAttentionSignalAttribution(signal, model);
    rows.push(attribution ? `${attribution}: ${text}` : text);
  }
  if(rows.length) return rows;
  const checkpoint = nextAttentionCheckpointText(subject);
  return checkpoint ? [checkpoint] : [];
}

function nextAttentionSubjectAge(subject, model){
  if(subject.primaryKind === "ask"){
    const ages = subject.asks.map(nextAttentionAskAge).filter(age => age != null);
    return ages.length ? Math.max(...ages) : null;
  }
  if(subject.primaryKind === "input"){
    return nextPayloadAgeSeconds({generated: model.generated}, subject.session &&
      subject.session.blocked_since);
  }
  if(subject.section === "close"){
    const signal = subject.signals && subject.signals[0];
    return nextPayloadAgeSeconds({generated: model.generated}, signal && signal.detail.finishedAt);
  }
  return null;
}

function nextAttentionSubjectSource(subject, model){
  const identity = nextAttentionSubjectIdentity(subject);
  const ask = subject && Array.isArray(subject.asks) ? subject.asks[0] : null;
  const harness = identity && identity.harness || ask && ask.harness || "";
  const parts = [];
  if(subject.responsibility) parts.push(subject.responsibility);
  parts.push(nextAttentionHarnessLabel(model, harness));
  const age = nextAttentionSubjectAge(subject, model);
  if(age != null) parts.push(nextFormatDuration(age));
  return parts.join(" · ");
}

function nextAttentionSubjectHtml(subject, model, hidden = false){
  const route = nextAttentionSubjectRoute(subject);
  const title = NEXT_ATTENTION_KIND_LABELS.get(subject.primaryKind) || "Source signal observed";
  const secondary = subject.signals.length > 1
    ? ` · ${subject.signals.length - 1} additional source signal${subject.signals.length === 2 ? "" : "s"}`
    : "";
  const outcome = nextAttentionOutcome(subject, model);
  const nowRows = nextAttentionSubjectNow(subject, model).map(row =>
    `<span class="next-attention-now-value">${nextAttentionEsc(row.text)}` +
      `${row.note ? `<small>${nextAttentionEsc(row.note)}</small>` : ""}</span>`
  ).join("");
  const checkpoints = nextAttentionCheckpointRows(subject, model);
  const checkpointRows = checkpoints.map(checkpoint =>
    `<span class="next-attention-now-value">${nextAttentionEsc(checkpoint)}</span>`
  ).join("");
  const next = checkpoints.length
    ? '<p class="next-attention-part" data-next-attention-part="next">' +
      `<span class="next-attention-label">NEXT</span><span>${checkpointRows}</span></p>`
    : "";
  return `<li${hidden ? " hidden" : ""}><article class="next-attention-item" ` +
    `data-next-attention-subject="${nextAttentionEsc(subject.key)}" ` +
    `data-next-attention-kind="${nextAttentionEsc(subject.primaryKind)}">` +
    '<h3 class="next-attention-why" data-next-attention-part="why">' +
    `<a href="#n=${esc(route)}" data-next-route="${esc(route)}">${esc(title)}${esc(secondary)}</a>` +
    "</h3>" +
    '<p class="next-attention-part" data-next-attention-part="outcome">' +
    `<span class="next-attention-label">${outcome.label}</span>` +
    `<span>${nextAttentionEsc(outcome.text)}</span></p>` +
    '<div class="next-attention-part" data-next-attention-part="now">' +
    `<span class="next-attention-label">NOW</span><span>${nowRows}</span></div>` + next +
    '<p class="next-attention-part" data-next-attention-part="source">' +
    `<span class="next-attention-label">SOURCE</span>` +
    `<span>${nextAttentionEsc(nextAttentionSubjectSource(subject, model))}</span></p></article></li>`;
}

function nextAttentionCoverageHtml(model){
  const coverage = model.coverage;
  const gates = coverage.gates;
  const failed = gates.failed ? ` · ${gates.failed} failed` : "";
  const visible = `Gates: ${gates.reporting}/${gates.discovered} reporting · ` +
    `${gates.unknown} unknown${failed} · Ends: ${coverage.ends}`;
  const rows = gates.rows.map(row => {
    const name = String(row.label == null ? "" : row.label).trim() || String(row.key || "Harness");
    const gate = row.error != null
      ? "needs-input reporting failed"
      : row.reports_needs_input === true ? "needs-input reporting" : "needs-input reporting unknown";
    const rate = row.error != null
      ? "token-rate reporting failed"
      : row.reports_rate === true
        ? "token-rate reporting"
        : row.reports_rate === false ? "token-rate not reported" : "token-rate reporting unknown";
    return `<li><strong>${nextAttentionEsc(name)}</strong> · ${gate} · ${rate}</li>`;
  }).join("");
  const exact = coverage.exactRequestsReported && coverage.exactRequestCount === 0
    ? "<p>No exact requests published.</p>"
    : "";
  const stops = coverage.observedStops > 0
    ? `<p>Stops observed on ${coverage.observedStops} ` +
      `session${coverage.observedStops === 1 ? "" : "s"}; fleet coverage not reported.</p>`
    : "";
  return '<div class="next-attention-coverage">' +
    `<p><span class="next-attention-brief-label">COVERAGE</span>${esc(visible)}</p>` +
    '<details class="next-attention-coverage-details"><summary>Coverage details</summary>' +
    `${rows ? `<ul>${rows}</ul>` : ""}${exact}${stops}` +
    '<p>Termination cause not reported.</p></details></div>';
}

const NEXT_ATTENTION_INITIAL_SECTION_SIZE = 3;

function nextAttentionSectionHtml(key, title, subjects, model, expandedSections){
  if(!subjects.length) return "";
  const expanded = !!(expandedSections && typeof expandedSections.has === "function" &&
    expandedSections.has(key));
  const remainder = Math.max(0, subjects.length - NEXT_ATTENTION_INITIAL_SECTION_SIZE);
  const listId = `next-attention-${key}-list`;
  const items = subjects.map((subject, index) => nextAttentionSubjectHtml(
    subject, model, !expanded && index >= NEXT_ATTENTION_INITIAL_SECTION_SIZE,
  )).join("");
  const disclosure = remainder
    ? '<button type="button" class="next-attention-disclosure" ' +
      `data-next-attention-toggle="${key}" aria-expanded="${expanded}" ` +
      `aria-controls="${listId}">` +
      `${expanded ? `Show fewer (hide ${remainder})` : `Show ${remainder} more`}</button>`
    : "";
  return `<section class="next-attention-section" data-next-attention-section="${key}">` +
    `<h2 tabindex="-1">${title} (${subjects.length})</h2>` +
    `<ol id="${listId}">${items}</ol>${disclosure}</section>`;
}

function nextAttentionHealthyHtml(model){
  const healthy = model.healthy;
  const count = healthy.sessions.length;
  if(!count) return "";
  const states = [];
  if(healthy.moving) states.push(`${healthy.moving} moving`);
  if(healthy.quiet) states.push(`${healthy.quiet} quiet`);
  if(healthy.unknown) states.push(`${healthy.unknown} unknown state`);
  return '<section class="next-attention-section next-attention-healthy" ' +
    'data-next-attention-section="healthy">' +
    `<h2 tabindex="-1">NO PUBLISHED EXCEPTION (${count})</h2>` +
    `<p><strong>${count} session${count === 1 ? "" : "s"} with no published exception</strong>` +
    `${states.length ? `<span>${esc(states.join(" · "))}</span>` : ""}</p>` +
    '<p>No published exception; coverage applies</p>' +
    '<a href="#n=projects" data-next-route="projects">View all projects</a></section>';
}

function nextAttentionView(model, expandedSections = new Set()){
  const counts = model.counts;
  const observed = [
    `${counts.needs} need you`, `${counts.risk} at risk`, `${counts.close} close the loop`,
    `${counts.next} coming next`, `${counts.moving} moving`, `${counts.quiet} quiet`,
  ].join(" · ");
  const empty = model.sessionCount === 0
    ? `<p class="next-attention-empty">No sessions in this ` +
      `${model.windowHours == null ? "payload" : `${esc(model.windowHours)}h payload`}</p>`
    : "";
  return '<section class="next-attention" data-next-view-body="attention"><h1 tabindex="-1">' +
    "Attention</h1><div class=\"next-attention-brief\">" +
    `<p><span class="next-attention-brief-label">OBSERVED NOW</span>${observed}</p>` +
    `${nextAttentionCoverageHtml(model)}</div>${empty}` +
    nextAttentionSectionHtml("needs", "NEEDS YOU NOW", model.needs, model, expandedSections) +
    nextAttentionSectionHtml("risk", "AT RISK", model.risk, model, expandedSections) +
    nextAttentionSectionHtml("close", "CLOSE THE LOOP", model.close, model, expandedSections) +
    nextAttentionSectionHtml("next", "COMING NEXT", model.next, model, expandedSections) +
    `${nextAttentionHealthyHtml(model)}</section>`;
}
