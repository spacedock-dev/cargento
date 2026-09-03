// At the measured five-second cadence, 22 sessions produce 95,040 samples in
// six hours. Keep that useful window with room for transitions while placing a
// hard ceiling on what one browser tab retains.
const NEXT_WORKSTREAM_ENTRY_CAP = 100000;
// Preserve the released preference key so stored browser state survives the
// promotion and cannot collide with keys from retired dashboard versions.
const NEXT_WORKSTREAM_COLLAPSED_KEY = "cargento.next.workstream.collapsed";
// What the caption says when nothing older than this tab is known. Named
// rather than written twice because both panels ask whether it still
// applies, and a seeded window that kept saying it would be the panel
// lying about where its own rows came from.
const NEXT_WORKSTREAM_TAB_WINDOW = "since this tab opened";

let nextWorkstreamGroups = [];
let nextWorkstreamEntryCount = 0;
let nextWorkstreamPreviousSessions = new Map();
let nextWorkstreamSeenAsks = new Map();
let nextWorkstreamLastGenerated = null;
let nextWorkstreamObservedSince = null;
let nextWorkstreamSeeded = false;

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

function nextWorkstreamHarnessLabel(harness, labels){
  const fallback = String(harness || "agent");
  return String(labels.get(fallback) || fallback).trim() || "Agent";
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
  // Empty advancing payloads still mark unknown time; one entry keeps them bounded.
  const weight = Math.max(1, samples.length + events.length);
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

/* The published history holds one record per observed state change, stamped
   with the session's own activity time (`history.appended`), oldest first. It is
   replayed here rather than in the panels because both of them read the same
   group list, and a store that reached only the rail would leave the delegation
   figure measuring a tab that had just opened.

   Each record's own snapshot becomes a batch: every session known at that stamp,
   in the state its latest record gave it. That is the reading the delegation
   arithmetic already makes of a live poll — an observation holds until the next
   one arrives — so a replayed window and a polled one are the same shape rather
   than two cases to keep in step.

   The sample objects are shared between batches on purpose. A session's sample
   is identical until its own next record, and a full store is ~7,800 records:
   rebuilding one object per session per record allocated millions where sharing
   allocates one per record. */
function nextWorkstreamSeed(history, labels, generated){
  const records = [];
  for(const entry of Array.isArray(history) ? history : []){
    const at = nextNumber(entry && entry.last_activity);
    const sid = String(entry && entry.sid || "");
    // A record with no ordered stamp or no session cannot be placed on a
    // timeline at all. The store is a file any local process could have
    // replaced, so this drops rather than repairs — the same posture the reader
    // takes on the way in.
    if(at == null || !sid || at > generated) continue;
    records.push({
      at,
      harness: String(entry && entry.harness || ""),
      project: String(entry && entry.project || ""),
      sid,
      state: String(entry && entry.state || "idle"),
    });
  }
  if(records.length === 0) return false;
  records.sort((left, right) => left.at - right.at);
  const held = new Map();
  for(const record of records){
    const key = nextWorkstreamSessionKey(record);
    const previous = held.get(key);
    held.set(key, {
      at: record.at,
      harness: record.harness,
      kind: "sample",
      project: record.project,
      // The store keeps no token rate, and an unknown rate is what turns the
      // delegation figure into a floor rather than a number it cannot support.
      rate: null,
      rateKnown: false,
      sid: record.sid,
      state: record.state,
    });
    const events = [];
    if(previous && previous.state !== record.state){
      const transition = nextWorkstreamTransition(previous.state, record.state);
      events.push({
        at: record.at,
        filled: transition.filled,
        fromState: previous.state,
        harness: record.harness,
        kind: "state",
        label: nextWorkstreamStateLabel(record.state),
        project: record.project,
        right: nextWorkstreamHarnessLabel(record.harness, labels),
        sid: record.sid,
        state: record.state,
        toState: record.state,
      });
    }
    // A session's first stored record establishes the state a later change is
    // measured against; it is not itself a change, and listing it would make
    // the rail's heading untrue of its own rows.
    nextWorkstreamAppendGroup({at: record.at, events, samples: [...held.values()]});
  }
  return true;
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
    nextWorkstreamSeeded = nextWorkstreamSeed(payload && payload.history, labels, generated);
    nextWorkstreamObservedSince = nextWorkstreamGroups.length > 0
      ? nextWorkstreamGroups[0].at
      : generated;
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
    const right = nextWorkstreamHarnessLabel(session.harness, labels);
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
  const batches = [];
  const samples = [];
  const events = [];
  let startedAt = null;
  for(const group of nextWorkstreamGroups){
    const groupSamples = group.samples.filter(sample => sample.project === project);
    const groupEvents = group.events.filter(event => event.project === project);
    if((groupSamples.length > 0 || groupEvents.length > 0) && startedAt == null){
      startedAt = group.at;
    }
    if(startedAt != null) batches.push({at: group.at, rows: groupSamples});
    samples.push(...groupSamples);
    events.push(...groupEvents);
  }
  return {
    batches,
    endedAt: nextWorkstreamLastGenerated,
    events,
    samples,
    seeded: nextWorkstreamSeeded,
    startedAt: startedAt == null ? nextWorkstreamObservedSince : startedAt,
  };
}

function nextWorkstreamWindowLabel(window){
  if(window.startedAt == null || window.endedAt == null || window.endedAt <= window.startedAt){
    return NEXT_WORKSTREAM_TAB_WINDOW;
  }
  const seconds = Math.floor(window.endedAt - window.startedAt);
  if(seconds < 60) return `last ${Math.max(1, seconds)}s`;
  if(seconds < 3600) return `last ${Math.floor(seconds / 60)}m`;
  if(seconds < 86400){
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return minutes === 0 ? `last ${hours}h` : `last ${hours}h ${minutes}m`;
  }
  // Days, because the store's shipped retention is fourteen of them and a
  // seeded window reported as `last 336h` is a figure nobody reads as two weeks.
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  return hours === 0 ? `last ${days}d` : `last ${days}d ${hours}h`;
}

function nextWorkstreamWindowPhrase(window){
  const label = nextWorkstreamWindowLabel(window);
  return label === NEXT_WORKSTREAM_TAB_WINDOW ? label : `in the ${label}`;
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
    `<span>${glyph} OBSERVED STATE CHANGES</span><small>${esc(detail)}</small></button></header>`;
  if(nextWorkstreamCollapsed){
    return `<section class="next-workstream"${collapsed}>${header}</section>`;
  }
  if(events.length === 0){
    return '<section class="next-workstream">' + header +
      `<p class="next-workstream-empty">No state changes observed ${esc(nextWorkstreamWindowPhrase(window))}.</p></section>`;
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
