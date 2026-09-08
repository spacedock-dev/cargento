function nextObservedString(value){
  return typeof value === "string" ? value.trim() : "";
}

function nextObservedPair(name, value, reason){
  const text = nextObservedString(value);
  return {[`${name}Text`]: text || reason, [`${name}Known`]: Boolean(text)};
}

function nextObservedRecords(value){
  return Array.isArray(value)
    ? value.filter(row => row && typeof row === "object" && !Array.isArray(row)) : [];
}

function nextObservedCompare(left, right){
  return left < right ? -1 : (left > right ? 1 : 0);
}

function nextObservedLabel(session){
  // F1 groups the exact published label, including whitespace and the empty
  // label. nextProjectGroups uses nextRows, so calling it here would read nextData.
  return String(session.project == null ? "" : session.project);
}

function nextObservedSession(source, asks, harness, generated, shared){
  const ended = nextSessionEndedAt(source) != null;
  const working = !ended && source.state === "working";
  const needs = !ended && source.state === "needs_input";
  const question = asks.map(ask => nextObservedString(ask.question)).filter(Boolean).join("\n");
  const tasks = nextObservedRecords(source.tasks);
  const task = status => tasks.find(row => row.status === status && nextObservedString(row.subject));
  const doing = task("in_progress");
  const pending = task("pending");
  const gaps = Array.isArray(source.source_gaps) ? source.source_gaps : [];
  const reporter = harness && !harness.error && harness.reports_needs_input === true &&
    !gaps.includes("block state");
  const blocked = needs || Boolean(question);
  const blockKnown = Boolean(blocked || reporter);
  const waitAge = asks.map(ask => nextNumber(ask.age_sec)).filter(age => age != null && age >= 0);
  const stampAge = nextPayloadAgeSeconds({generated}, source.blocked_since);
  const age = waitAge.length ? Math.max(...waitAge) : (blocked ? stampAge : null);
  const rate = nextNumber(source.rate_per_min);
  const rateKnown = rate != null && rate >= 0 && Boolean(harness && !harness.error &&
    harness.reports_rate === true && !gaps.includes("token accounting"));
  const loop = source.loop;
  const errors = loop && Number.isInteger(loop.errors) && loop.errors > 0 ? loop.errors : 0;
  const failures = loop && Number.isInteger(loop.failures) && loop.failures > errors ? loop.failures : 0;
  const stuck = errors ? `${errors} tool failures in a row` +
    (failures ? ` · ${failures} failures this turn` : "") : "";
  const stopped = source.state === "idle" && nextNumber(source.finished_at) > 0;
  const outcomeKnown = ended || stopped;
  const outcomePrefix = ended ? "Session ended" : "Stop observed";
  const gitKnown = typeof source.dirty === "boolean";
  const outcome = outcomeKnown ? outcomePrefix + (source.dirty === true ? " with uncommitted work" :
    (source.dirty === false ? "; git state clean" : "; git state not measured")) : "";
  let git = "";
  if(gitKnown){
    git = source.dirty ? "Uncommitted work observed" : "Git state reported clean";
    if(source.dirty && Number.isInteger(source.changed) && source.changed >= 0){
      git = `${source.changed} changed entries`;
    }
  }
  const sharedText = shared > 1 ? `${shared} sessions share this display label; ` +
    "shared location is not established" : "";
  const turn = source.turn && typeof source.turn === "object" ? source.turn : {};
  const turnElapsed = nextObservedString(turn.elapsed_h);
  const turnEta = nextObservedString(turn.eta_h);
  const turnText = turnElapsed ? `${turnElapsed} into turn` + (turnEta ? ` · ${turnEta} estimated remaining` : "") : "";
  return {
    sid: String(source.sid == null ? "" : source.sid),
    harness: String(source.harness == null ? "" : source.harness),
    project: nextObservedLabel(source),
    ...nextObservedPair("title", source.title, "Title not published"),
    ...nextObservedPair("now", ended ? "Session reported its own end" :
      (doing ? doing.subject : source.state_detail), "Activity not published"),
    ...nextObservedPair("next", pending && pending.subject, "No pending step published"),
    ...nextObservedPair("where", "", "Exact location not published"),
    ...nextObservedPair("turn", turnText, "Harness does not report turn bounds"),
    blockText: blocked ? "Waiting on you" : (reporter ? "No reported block" :
      (gaps.includes("block state") ? "Block state could not be read" : "Harness does not report blocks")),
    blockKnown,
    blockNote: question || (needs ? nextObservedString(source.state_detail) || "Block reported" :
      (reporter ? "Reporter available" : "No block-state reading available")),
    // Stops and ends are published; readership and termination cause are not.
    // Their absence belongs in open/coverage, never in an inferred outcome.
    ...nextObservedPair("outcome", outcome, "No stop or end observed"),
    outcomeGlyph: outcomeKnown ? (source.dirty === true ? "△" : (source.dirty === false ? "✓" : "◦")) : "",
    ...nextObservedPair("git", git, "Git state was not measured"),
    ...nextObservedPair("rate", rateKnown ? `${Math.round(rate).toLocaleString("en-US")} /m` : "",
      "Token rate not reported"),
    ...nextObservedPair("ask", question, "No exact request published"),
    waitedText: age == null ? "Wait duration not published" : nextFormatDuration(age),
    waitedKnown: age != null,
    ...nextObservedPair("stuck", stuck, "No stuck signal published"),
    ...nextObservedPair("sharedLabel", sharedText, "No shared display label observed"),
    state: String(source.state == null ? "" : source.state),
    isWorking: working, isNeeds: needs, isEnded: ended,
    isQuiet: !ended && source.state === "idle",
    tone: outcomeKnown ? (gitKnown ? (source.dirty ? "bad" : "ok") : "unknown") :
      (blocked || errors || (working && turn.long === true) ? "want" :
      (blockKnown && ["working", "idle"].includes(source.state) ? "ok" : "unknown")),
    subagents: Array.isArray(source.subagents) ? source.subagents : [],
    tasks: Array.isArray(source.tasks) ? source.tasks : [],
  };
}

function nextObservedHistory(payload, sessions){
  const generated = nextNumber(payload.generated);
  const members = new Set(sessions.map(nextSessionKey));
  const records = nextObservedRecords(payload.history).filter(record =>
    generated != null && nextNumber(record.last_activity) != null && record.last_activity > 0 &&
    record.last_activity <= generated && members.has(nextSessionKey(record)) &&
    nextObservedLabel(record) === sessions[0].project,
  ).slice().sort((a, b) => a.last_activity - b.last_activity ||
    nextObservedCompare(nextSessionKey(a), nextSessionKey(b)));
  const last = new Map();
  records.forEach((record, index) => last.set(nextSessionKey(record), index));
  const held = new Map();
  const previous = new Map();
  const closedWorking = new Set();
  const changes = [];
  let delegated = 0;
  let total = 0;
  let observed = 0;
  let human = 0;
  const idleResumptions = new Set();
  records.forEach((record, index) => {
    const key = nextSessionKey(record);
    const before = previous.get(key);
    if(before && record.last_activity > before.last_activity && before.state === "working"){
      closedWorking.add(key);
    }
    if(before && before.state !== record.state){
      const gateExit = before.state === "needs_input" && record.state !== "needs_input";
      const resume = before.state === "idle" && record.state === "working";
      const humanTurn = gateExit || resume;
      if(humanTurn && !(resume && idleResumptions.has(key))) human += 1;
      idleResumptions.delete(key);
      if(before.state === "needs_input" && record.state === "idle") idleResumptions.add(key);
      const label = record.state === "working" ? "agent resumed" :
        (record.state === "needs_input" ? "needs input" :
          (record.state === "idle" ? "became idle" : `state changed to ${record.state}`));
      changes.push({at: record.last_activity, sid: record.sid, harness: record.harness,
        fromState: before.state, toState: record.state, label,
        filled: record.state !== "needs_input" && !humanTurn});
    }
    previous.set(key, record);
    // Last observations close spans. Holding them to generated would turn a
    // stopped server's unobserved time into delegated work.
    if(last.get(key) === index) held.delete(key);
    else held.set(key, record);
    if(index + 1 >= records.length || !held.size) return;
    const seconds = records[index + 1].last_activity - record.last_activity;
    observed += seconds;
    const states = [...held.values()].map(row => row.state);
    if(states.includes("needs_input")) total += seconds;
    else if(states.includes("working")){
      total += seconds;
      delegated += seconds;
    }
  });
  const known = observed >= 600 && total > 0;
  const missing = sessions.filter(session => !closedWorking.has(nextSessionKey(session))).length;
  const pct = known ? Math.round(100 * delegated / total) : null;
  const span = records.length > 1 ? records[records.length - 1].last_activity - records[0].last_activity : 0;
  const window = span > 0 ? `last ${nextFormatDuration(span)}` : "";
  const note = known ? (missing ? `≥ because ${missing} ${missing === 1 ? "session has" : "sessions have"} ` +
    "no closed working interval in the retained window." : "Measured over closed working and needs-input intervals.") :
    "Waiting on one complete observed working-or-gated window.";
  return {
    changes,
    changeNoteText: changes.length ? `${changes.filter(change => change.filled).length} of ` +
      `${changes.length} unattended · ${window}` : "No state changes published in retained history",
    changeNoteKnown: changes.length > 0,
    delegation: {
      pctText: known ? `${pct}%` : "no figure yet", pctKnown: known, pctFloor: known && missing > 0, pct,
      tpsText: "Retained history does not publish token rates",
      tpsKnown: false,
      humanText: records.length ? `${human} observed human turns` : "Human turns not observed",
      humanKnown: records.length > 0,
      windowText: window || "No retained observation window published",
      windowKnown: Boolean(window),
      noteText: note,
      noteKnown: known,
    },
  };
}

function nextObservedGoal(source){
  const instruction = source.instruction;
  if(instruction && instruction.label === "asked" && nextObservedString(instruction.text)){
    return {text: instruction.text, src: `${source.harness} · latest assignment`};
  }
  const workflows = nextObservedRecords(source.spacedock && source.spacedock.workflows);
  const goals = workflows.filter(workflow => nextObservedString(workflow.goal));
  return goals.length ? {text: goals.map(workflow => workflow.goal).join("\n"), src: "Spacedock · workflow goal"} : false;
}

function nextObservedProject(key, sessions, sources, payload, risky){
  const needs = sessions.filter(session => session.isNeeds);
  const working = sessions.filter(session => session.isWorking);
  const ended = sessions.filter(session => session.isEnded);
  const quiet = sessions.filter(session => session.isQuiet);
  const counts = [`${sessions.length} ${sessions.length === 1 ? "session" : "sessions"}`];
  if(working.length) counts.push(`${working.length} working`);
  if(needs.length) counts.push(`${needs.length} waiting on you`);
  if(ended.length) counts.push(`${ended.length} ended`);
  if(quiet.length) counts.push(`${quiet.length} quiet`);
  const other = sessions.length - working.length - needs.length - ended.length - quiet.length;
  if(other) counts.push(`${other} in no counted state`);
  const goals = sources.map(source => ({source, goal: nextObservedGoal(source)})).filter(row => row.goal);
  goals.sort((a, b) => (nextNumber(b.source.last_activity) || 0) - (nextNumber(a.source.last_activity) || 0) ||
    nextObservedCompare(nextSessionKey(a.source), nextSessionKey(b.source)));
  const goal = goals.length ? goals[0].goal : false;
  return {
    key, ...nextObservedPair("scope", "", "Exact location not published"),
    countLine: counts.join(" · "),
    sharedLabelText: sessions[0].sharedLabelText, sharedLabelKnown: sessions[0].sharedLabelKnown,
    ...nextObservedPair("goal", goal && goal.text, "No assignment or workflow goal published"),
    goalSrcText: goal ? goal.src : "Goal source not published",
    goalSrcKnown: Boolean(goal),
    goalGapText: `${sessions.length - goals.length} of ${sessions.length} sessions publish no goal.`,
    goalGapKnown: true,
    sessions, needs, working, ended, risky,
    ...nextObservedHistory(payload, sessions),
    tone: needs.length || sessions.some(session => session.askKnown) ? "want" :
      (risky.some(session => session.tone === "bad") ? "bad" :
        (risky.length ? "want" : (sessions.some(session => session.tone === "ok") ? "ok" : "unknown"))),
  };
}

function nextObservedRisk(session, kind, title, text){
  return {scope: "session", kind, sid: session.sid, harness: session.harness, project: session.project,
    title, identity: `${session.project} · ${session.sid}`, src: session.harness,
    nowText: text, nowKnown: true, nextText: session.nextText, nextKnown: session.nextKnown,
    tone: session.tone};
}

function nextObservedCapacity(payload){
  const windows = [];
  const sublimits = [];
  const risks = [];
  const generated = nextNumber(payload.generated);
  for(const entry of nextObservedRecords(payload.usage)){
    if(entry.state !== "ok") continue;
    const vendor = nextObservedString(entry.harness) || "Source not identified";
    for(const [slot, label] of [["fiveH", "5-hour"], ["week", "weekly"], ["month", "billing cycle"]]){
      const raw = entry[slot];
      if(!raw || !Number.isInteger(raw.pct)) continue;
      const length = nextNumber(raw.windowSec);
      const reset = nextNumber(raw.resetAt);
      const remaining = generated != null && reset != null ? reset - generated : null;
      const elapsed = length != null && length > 0 && remaining != null && remaining > 0 ?
        Math.max(0, Math.min(1, (length - remaining) / length)) : null;
      const pace = elapsed != null && elapsed > 0 ? raw.pct / (100 * elapsed) : null;
      const minutes = pace != null && pace > 0 ? Math.max(0, 100 - raw.pct) / raw.pct * elapsed * length / 60 : null;
      const tone = pace == null ? "unknown" : (pace >= 1.5 ? "bad" : (pace >= 1 ? "want" : "ok"));
      const key = `${vendor}:${slot}`;
      const recent = raw.recent && typeof raw.recent === "object" ? raw.recent : {};
      const recentRate = nextNumber(recent.pctPerMin);
      const recentSpan = nextNumber(recent.spanSec);
      const recentKnown = recentRate != null && recentRate >= 0 && recentSpan != null && recentSpan > 0 &&
        Number.isInteger(recent.samples) && recent.samples >= 2 && remaining != null && remaining > 0;
      const recentBasis = recentKnown ? `across ${nextFormatDuration(recentSpan)} and ${recent.samples} readings` : "";
      const recentText = !recentKnown ? "" : (recentRate === 0 ?
        `Measured at zero: nothing spent ${recentBasis}, so nothing is projected from it.` :
        `${recentRate} percentage points per minute ${recentBasis}; ` +
          `${nextFormatDuration(Math.max(0, 100 - raw.pct) / recentRate * 60)} of budget remaining at that pace.`);
      const window = {
        key, vendor, slot, used: raw.pct,
        ...nextObservedPair("window", label, "Window label not published"),
        ...nextObservedPair("pace", pace == null ? "" : `${pace.toFixed(1)}×`, "Window pace not reported"),
        ...nextObservedPair("ends", raw.pct >= 100 ? "Already spent" :
          (minutes == null ? "" : `In ${nextFormatDuration(minutes * 60)} at this window's average pace`),
        "Budget end not projected"),
        ...nextObservedPair("resets", remaining != null && remaining > 0 ? nextFormatDuration(remaining) : "",
          remaining != null && remaining <= 0 ? "Published reset has passed" : "Reset time not published"),
        ...nextObservedPair("clock", elapsed == null ? "" : `${Math.round(elapsed * 100)}% of window elapsed`,
          "Window clock not published"),
        ...nextObservedPair("recent", recentText, "Recent quota pace not measured for a current window"),
        ...nextObservedPair("basis", elapsed != null && elapsed < 0.1 ?
          "Less than a tenth of this window has elapsed; the projection rests on a short observation." : "",
        "No short-window qualification published"),
        tone,
      };
      windows.push(window);
      const pressure = raw.pct >= 70 || (elapsed >= 0.1 && raw.pct >= 10 &&
        minutes != null && remaining > 0 && minutes * 60 < remaining);
      if(pressure) risks.push({scope: "board", kind: "quota", title: "Quota pressure",
        identity: `${vendor} · ${label} window`, src: `${vendor} vendor quota`,
        nowText: `${raw.pct}% reported · ${window.paceText}`, nowKnown: true,
        nextText: window.resetsText, nextKnown: window.resetsKnown, tone});
    }
    for(const model of nextObservedRecords(entry.models).slice(0, 8)){
      if(!nextObservedString(model.label) || !Number.isInteger(model.pct)) continue;
      sublimits.push({within: `${vendor} · weekly`, label: model.label, used: model.pct,
        ...nextObservedPair("note", "", "Per-model sub-limits publish no clock, so no pace and no projected end.")});
    }
  }
  return {windows, sublimits, risks};
}

function nextObserved(payload){
  payload = payload && typeof payload === "object" && !Array.isArray(payload) ? payload : {};
  const sources = nextPayloadSessions(payload);
  const harnesses = nextObservedRecords(payload.harnesses);
  const byHarness = new Map(harnesses.map(row => [String(row.key || ""), row]));
  const groups = new Map();
  for(const source of sources){
    const label = nextObservedLabel(source);
    if(!groups.has(label)) groups.set(label, []);
    groups.get(label).push(source);
  }
  const asks = new Map();
  const unowned = [];
  for(const ask of payload.ask === true ? nextPayloadAsks(payload) : []){
    if(!nextObservedString(ask.question)) continue;
    const owner = nextExactAskOwner(payload, ask);
    if(!owner){ unowned.push(ask); continue; }
    const key = nextSessionKey(owner);
    if(!asks.has(key)) asks.set(key, []);
    asks.get(key).push(ask);
  }
  const sessions = sources.map(source => nextObservedSession(source, asks.get(nextSessionKey(source)) || [],
    byHarness.get(String(source.harness || "")), nextNumber(payload.generated),
    groups.get(nextObservedLabel(source)).length));
  const risks = [];
  sessions.forEach((session, index) => {
    const source = sources[index];
    const finished = nextNumber(source.finished_at) > 0;
    const attributed = !session.isEnded && ((finished && (session.isWorking || source.active === true)) ||
      (!finished && (typeof source.dirty === "boolean" || Number.isInteger(source.changed))));
    if(session.outcomeKnown && source.dirty === true){
      risks.push(nextObservedRisk(session, session.isEnded ? "end-dirty" : "stop-dirty", session.outcomeText, session.gitText));
    }
    else if(attributed) risks.push(nextObservedRisk(session, "attribution", "Conflicting completion evidence",
      "Published activity and completion or git evidence do not establish the same end"));
    else if(session.stuckKnown) risks.push(nextObservedRisk(session, "loop", "Stuck signal", session.stuckText));
    else if(session.isWorking && source.turn && source.turn.long === true){
      risks.push(nextObservedRisk(session, "long-turn", "Long working turn", session.turnText));
    }
  });
  const riskKeys = new Set(risks.map(nextSessionKey));
  const projects = [...groups].map(([key, group]) => {
    const members = sessions.filter(session => session.project === key);
    return nextObservedProject(key, members, group, payload, members.filter(session => riskKeys.has(nextSessionKey(session))));
  });
  const rank = project => project.needs.length ? 0 : (project.risky.length ? 1 : (project.working.length ? 2 : 3));
  projects.sort((a, b) => rank(a) - rank(b) || nextObservedCompare(a.key, b.key));
  const capacity = nextObservedCapacity(payload);
  const boardRisks = capacity.risks;
  for(const project of projects){
    if(!project.key.trim() || project.sessions.length < 2) continue;
    boardRisks.push({scope: "board", kind: "collision", title: "Identity collision",
      identity: `${project.key} display label`, src: "Published project labels",
      nowText: project.sharedLabelText, nowKnown: true,
      nextText: "Shared location is not established", nextKnown: false, tone: "unknown"});
  }
  for(const ask of unowned){
    boardRisks.push({scope: "board", kind: "ask", title: "Exact request without an identified session",
      identity: nextObservedString(ask.id) || "Request identity not published", src: nextObservedString(ask.harness) || "Harness not published",
      nowText: ask.question, nowKnown: true, nextText: "Exact session ownership not established", nextKnown: false, tone: "want"});
  }
  const totals = {
    sessions: sessions.length, running: sessions.filter(session => session.isWorking).length,
    needs: sessions.filter(session => session.isNeeds).length, ended: sessions.filter(session => session.isEnded).length,
    quiet: sessions.filter(session => session.isQuiet).length,
    subagents: sessions.reduce((sum, session) => sum + session.subagents.length, 0),
    reportsBlock: sessions.filter(session => session.blockKnown).length,
    exactRequests: sessions.filter(session => session.askKnown).length,
  };
  const active = sessions.filter(session => session.isWorking || session.isNeeds || session.askKnown);
  const history = sessions.filter(session => session.isEnded || session.isQuiet);
  const needs = sessions.filter(session => session.isNeeds || session.askKnown);
  const needKeys = new Set(needs.map(nextSessionKey));
  const atRisk = sessions.filter(session => riskKeys.has(nextSessionKey(session)) && !needKeys.has(nextSessionKey(session)));
  const close = sessions.filter((session, index) => !needKeys.has(nextSessionKey(session)) &&
    !riskKeys.has(nextSessionKey(session)) && (session.isEnded ||
      (session.isQuiet && nextNumber(sources[index].finished_at) > 0)));
  const subjectKeys = new Set([...needs, ...atRisk, ...close].map(nextSessionKey));
  const other = sessions.filter(session => !subjectKeys.has(nextSessionKey(session)));
  const partial = other.filter(session => {
    const source = sources[sessions.indexOf(session)];
    return Array.isArray(source.source_gaps) && source.source_gaps.length;
  }).length;
  const otherWords = [["moving", other.filter(session => session.isWorking).length],
    ["quiet", other.filter(session => session.isQuiet).length],
    ["ended", other.filter(session => session.isEnded).length]];
  const counted = otherWords.reduce((sum, word) => sum + word[1], 0);
  if(counted < other.length) otherWords.push(["in no counted state", other.length - counted]);
  const coverage = {
    observed: `${sessions.length - other.length} of ${totals.sessions} sessions carry a subject: ` +
      `${needs.length} waiting on you · ${atRisk.length} at risk · ${close.length} to close the loop.`,
    quiet: `The other ${other.length}: ${otherWords.filter(word => word[1]).map(word => `${word[1]} ${word[0]}`).join(" · ") || "none"}; ` +
      `of these, ${partial} partially read.`,
    gates: `${totals.reportsBlock} of ${totals.sessions} sessions report block state · ` +
      `${totals.sessions - totals.reportsBlock} unknown · ends observed on ${totals.ended} sessions`,
    rows: harnesses.map(row => ({key: String(row.key || ""), label: nextObservedString(row.label) || String(row.key || "Harness not published"),
      sessions: sessions.filter(session => session.harness === row.key).length,
      ...nextObservedPair("block", !row.error && row.reports_needs_input === true ?
        "needs-input reporting" + (nextObservedString(row.reports_needs_input_when) ? `, ${row.reports_needs_input_when}` : "") : "",
      row.error ? "Harness source could not be read" : "Harness does not report blocks"),
      ...nextObservedPair("rate", !row.error && row.reports_rate === true ? "token-rate reporting" : "", "Token rate not reported")})),
    caveats: ["Termination cause not reported.", ...new Set(Object.keys(sessions[0] || {}).filter(key => key.endsWith("Text") &&
      sessions.every(session => session[key.slice(0, -4) + "Known"] === false))
      .flatMap(key => sessions.map(session => session[key])))],
  };
  const counter = (label, value, noteText) => ({label, value, noteText, noteKnown: true});
  return {
    sessions, projects, activeProjects: projects.filter(project => project.needs.length || project.working.length),
    restProjects: projects.filter(project => !project.needs.length && !project.working.length),
    active, history, totals, coverage, risks, boardRisks,
    counters: [counter("ACTIVE NOW", active.length, `${totals.sessions} recently observed`),
      counter("WORKING", totals.running, `${needs.length} waiting on you`),
      counter("EXACT REQUESTS", totals.exactRequests, `${totals.exactRequests} of ${totals.sessions} sessions carry an exact request`),
      counter("REPORTED BLOCKS", totals.reportsBlock, `${totals.reportsBlock} of ${totals.sessions} sessions report block state`)],
    windows: capacity.windows, sublimits: capacity.sublimits,
    open: [
      ["C4", "Stated goals across sessions", "Goals shown are whatever a harness publishes. Nothing normalises them yet."],
      ["C6", "Irreversible actions", "Force pushes and destructive shapes are not reported on this board yet."],
      ["C1", "Subagent tripwires", "Tripwires are held in this browser. No observer enforces them."],
      ["F3", "Attention accounting", "Delegation share is measured per project, not yet aggregated across the week."],
      ["E5", "Ended with unpushed commits", "The board reports uncommitted work, not commits that never reached a remote."],
      ["E6", "Finished and never read", "Nothing on the board publishes whether you have read a finished session. " +
        "The dismissal store is server-side and does not reach the page."],
    ],
  };
}
