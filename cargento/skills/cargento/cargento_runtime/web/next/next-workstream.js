// At the measured five-second cadence, 22 sessions produce 95,040 samples in
// six hours. Keep that useful window with room for transitions while placing a
// hard ceiling on what one browser tab retains.
const NEXT_WORKSTREAM_ENTRY_CAP = 100000;
// The old and next pages share an origin. Keep next-only viewer preferences in
// their own namespace so the stable bundle cannot mistake them for its state.
const NEXT_WORKSTREAM_COLLAPSED_KEY = "cargento.next.workstream.collapsed";

let nextWorkstreamGroups = [];
let nextWorkstreamEntryCount = 0;
let nextWorkstreamPreviousSessions = new Map();
let nextWorkstreamSeenAsks = new Map();
let nextWorkstreamLastGenerated = null;
let nextWorkstreamObservedSince = null;

function nextWorkstreamStoredCollapsed(){
  try{
    return localStorage.getItem(NEXT_WORKSTREAM_COLLAPSED_KEY) === "1";
  }catch(_error){
    return false;
  }
}

let nextWorkstreamCollapsed = nextWorkstreamStoredCollapsed();

function nextWorkstreamStoreCollapsed(){
  try{
    localStorage.setItem(NEXT_WORKSTREAM_COLLAPSED_KEY, nextWorkstreamCollapsed ? "1" : "0");
  }catch(_error){
    // The in-memory toggle remains useful when private mode rejects storage.
  }
}

function nextWorkstreamSessionKey(session){
  return `${String(session && session.harness || "")}:${String(session && session.sid || "")}`;
}

function nextWorkstreamSession(session){
  return {
    finishedAt: nextNumber(session && session.finished_at),
    harness: String(session && session.harness || ""),
    project: String(session && session.project || ""),
    sid: String(session && session.sid || ""),
    state: String(session && session.state || "idle"),
  };
}

function nextWorkstreamHarnessInitialism(harness, labels){
  const fallback = String(harness || "agent");
  const label = String(labels.get(fallback) || fallback).trim();
  const initials = label.split(/\s+/).filter(Boolean).map(word => word[0]).join("");
  return String(initials || label.slice(0, 2) || "A").slice(0, 3).toUpperCase();
}

function nextWorkstreamStateLabel(state){
  if(state === "working") return "agent resumed";
  if(state === "needs_input") return "needs input";
  return "became idle";
}

function nextWorkstreamTransition(fromState, toState){
  const leftGate = fromState === "needs_input" && toState !== "needs_input";
  const promptBoundary = fromState === "idle" && toState === "working";
  const humanTurn = leftGate || promptBoundary;
  return {
    filled: toState !== "needs_input" && !humanTurn,
    humanTurn,
  };
}

function nextWorkstreamRateKnown(harness, rate, sources){
  if(rate == null) return false;
  const source = sources.get(harness);
  const fallback = rate > 0;
  if(!source) return fallback;
  if(source.error) return false;
  return typeof source.reports_rate === "boolean" ? source.reports_rate : fallback;
}

function nextWorkstreamAppendGroup(group){
  const samples = Array.isArray(group.samples) ? group.samples : [];
  const events = Array.isArray(group.events) ? group.events : [];
  const weight = samples.length + events.length;
  if(weight === 0) return;
  nextWorkstreamGroups.push({at: group.at, events, samples, weight});
  nextWorkstreamEntryCount += weight;
  while(nextWorkstreamEntryCount > NEXT_WORKSTREAM_ENTRY_CAP && nextWorkstreamGroups.length > 1){
    const removed = nextWorkstreamGroups.shift();
    nextWorkstreamEntryCount -= removed.weight;
  }
  if(nextWorkstreamEntryCount <= NEXT_WORKSTREAM_ENTRY_CAP) return;
  const retained = nextWorkstreamGroups[0];
  const flat = [...retained.samples, ...retained.events]
    .slice(nextWorkstreamEntryCount - NEXT_WORKSTREAM_ENTRY_CAP);
  retained.samples = flat.filter(entry => entry.kind === "sample");
  retained.events = flat.filter(entry => entry.kind !== "sample");
  retained.weight = flat.length;
  nextWorkstreamEntryCount = flat.length;
}

function nextWorkstreamAskTime(ask, generated, floor){
  const age = nextNumber(ask && ask.age_sec);
  if(age == null || age < 0) return generated;
  const registered = generated - age;
  return registered > floor && registered <= generated ? registered : generated;
}

function nextObserveWorkstream(payload){
  const generated = nextNumber(payload && payload.generated);
  if(generated == null || (nextWorkstreamLastGenerated != null && generated <= nextWorkstreamLastGenerated)){
    return;
  }
  const sessions = payload && Array.isArray(payload.sessions) ? payload.sessions : [];
  const asks = payload && Array.isArray(payload.asks) ? payload.asks : [];
  const labels = new Map();
  const rateSources = new Map();
  for(const harness of payload && Array.isArray(payload.harnesses) ? payload.harnesses : []){
    const key = String(harness && harness.key || "");
    if(key){
      labels.set(key, String(harness.label || key));
      rateSources.set(key, harness);
    }
  }
  const current = new Map();
  const samples = [];
  for(const source of sessions){
    const session = nextWorkstreamSession(source);
    const key = nextWorkstreamSessionKey(session);
    if(!session.sid) continue;
    const rate = nextNumber(source.rate_per_min);
    current.set(key, session);
    samples.push({
      at: generated,
      harness: session.harness,
      kind: "sample",
      project: session.project,
      rate,
      rateKnown: nextWorkstreamRateKnown(session.harness, rate, rateSources),
      sid: session.sid,
      state: session.state,
    });
  }

  if(nextWorkstreamLastGenerated == null){
    nextWorkstreamObservedSince = generated;
    nextWorkstreamPreviousSessions = current;
    for(const ask of asks){
      const id = String(ask && ask.id || "");
      if(id) nextWorkstreamSeenAsks.set(id, generated);
    }
    nextWorkstreamAppendGroup({at: generated, events: [], samples});
    nextWorkstreamLastGenerated = generated;
    return;
  }

  const events = [];
  for(const [key, session] of current){
    const previous = nextWorkstreamPreviousSessions.get(key);
    if(!previous) continue;
    const right = nextWorkstreamHarnessInitialism(session.harness, labels);
    if(previous.state !== session.state){
      const transition = nextWorkstreamTransition(previous.state, session.state);
      events.push({
        at: generated,
        filled: transition.filled,
        fromState: previous.state,
        harness: session.harness,
        kind: "state",
        label: nextWorkstreamStateLabel(session.state),
        project: session.project,
        right,
        sid: session.sid,
        state: session.state,
        toState: session.state,
      });
    }
    if(
      session.finishedAt != null &&
      session.finishedAt > nextWorkstreamLastGenerated &&
      session.finishedAt <= generated &&
      (previous.finishedAt == null || session.finishedAt > previous.finishedAt)
    ){
      events.push({
        at: session.finishedAt,
        filled: true,
        harness: session.harness,
        kind: "turn",
        label: "turn stopped",
        project: session.project,
        right,
        sid: session.sid,
      });
    }
  }
  for(const ask of asks){
    const id = String(ask && ask.id || "");
    if(!id || nextWorkstreamSeenAsks.has(id)) continue;
    const at = nextWorkstreamAskTime(ask, generated, nextWorkstreamLastGenerated);
    events.push({
      at,
      filled: false,
      harness: String(ask && ask.harness || ""),
      kind: "ask",
      label: String(ask && ask.question || "agent asked for input"),
      project: String(ask && ask.project || ""),
      right: "asked you",
      sid: String(ask && ask.session_id || ""),
    });
    nextWorkstreamSeenAsks.set(id, generated);
  }
  while(nextWorkstreamSeenAsks.size > NEXT_WORKSTREAM_ENTRY_CAP){
    nextWorkstreamSeenAsks.delete(nextWorkstreamSeenAsks.keys().next().value);
  }
  events.sort((left, right) => left.at - right.at);
  nextWorkstreamAppendGroup({at: generated, events, samples});
  nextWorkstreamPreviousSessions = current;
  nextWorkstreamLastGenerated = generated;
}

function nextWorkstreamProjectWindow(project){
  const samples = [];
  const events = [];
  let startedAt = null;
  for(const group of nextWorkstreamGroups){
    const groupSamples = group.samples.filter(sample => sample.project === project);
    const groupEvents = group.events.filter(event => event.project === project);
    if((groupSamples.length > 0 || groupEvents.length > 0) && startedAt == null){
      startedAt = group.at;
    }
    samples.push(...groupSamples);
    events.push(...groupEvents);
  }
  return {
    endedAt: nextWorkstreamLastGenerated,
    events,
    samples,
    startedAt: startedAt == null ? nextWorkstreamObservedSince : startedAt,
  };
}

function nextWorkstreamWindowLabel(window){
  if(window.startedAt == null || window.endedAt == null || window.endedAt <= window.startedAt){
    return "since this tab opened";
  }
  const seconds = Math.floor(window.endedAt - window.startedAt);
  if(seconds < 60) return `last ${Math.max(1, seconds)}s`;
  if(seconds < 3600) return `last ${Math.floor(seconds / 60)}m`;
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return minutes === 0 ? `last ${hours}h` : `last ${hours}h ${minutes}m`;
}

function nextWorkstreamClock(stamp){
  const date = new Date(stamp * 1000);
  return `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

function nextProjectWorkstream(context){
  const window = nextWorkstreamProjectWindow(context.group.label);
  const events = window.events;
  const unattended = events.filter(event => event.filled).length;
  const glyph = nextWorkstreamCollapsed ? "▸" : "▾";
  const graphNote = `${unattended} of ${events.length} unattended`;
  const detail = nextWorkstreamCollapsed
    ? graphNote
    : `${graphNote} · ${nextWorkstreamWindowLabel(window)}`;
  const collapsed = nextWorkstreamCollapsed ? " data-next-workstream-collapsed" : "";
  const header = '<header class="next-workstream-header">' +
    `<button type="button" data-next-workstream-toggle aria-expanded="${!nextWorkstreamCollapsed}">` +
    `<span>${glyph} WORKSTREAM</span><small>${esc(detail)}</small></button></header>`;
  if(nextWorkstreamCollapsed){
    return `<section class="next-workstream"${collapsed}>${header}</section>`;
  }
  if(events.length === 0){
    return '<section class="next-workstream">' + header +
      '<p class="next-workstream-empty">No workstream events since this tab opened.</p></section>';
  }
  const rows = events.map(event => {
    const human = event.filled ? "" : " next-workstream-event--human";
    const right = event.kind === "ask" ? " next-workstream-right--ask" : "";
    return `<li class="next-workstream-event${human}" data-next-workstream-event="${esc(event.kind)}">` +
      `<time>${esc(nextWorkstreamClock(event.at))}</time>` +
      `<span class="next-workstream-node" aria-hidden="true">${event.filled ? "●" : "○"}</span>` +
      `<span class="next-workstream-name">${esc(event.label)}</span>` +
      '<span class="next-workstream-leader" aria-hidden="true"></span>' +
      `<span class="next-workstream-right${right}">${esc(event.right)}</span></li>`;
  }).join("");
  return `<section class="next-workstream">${header}<ol>${rows}</ol></section>`;
}

function nextWorkstreamToggleTarget(event){
  return event.target && event.target.closest
    ? event.target.closest("[data-next-workstream-toggle]")
    : null;
}

function nextWorkstreamToggle(){
  nextWorkstreamCollapsed = !nextWorkstreamCollapsed;
  nextWorkstreamStoreCollapsed();
  renderNext();
}

document.addEventListener("click", event => {
  if(!nextWorkstreamToggleTarget(event)) return;
  event.preventDefault();
  nextWorkstreamToggle();
});
