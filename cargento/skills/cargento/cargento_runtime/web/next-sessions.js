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
  /* aggregate.py deliberately uses sid for a stable idle payload. Keep the
     server's gate order and override only the idle tail by nearest activity. */
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
  const other = rows.filter(session =>
    !["needs_input", "working", "idle"].includes(String(session.state || "")));
  return {gates, working, idle, other};
}

function nextSessionCollision(session, counts){
  const project = String(session.project == null ? "" : session.project);
  const count = counts.get(project) || 0;
  if(count < 2) return "";
  return `<span class="next-operation-collision" title="${esc(NEXT_DUPLICATE_LABEL_LIMIT)}">` +
    `${count} sessions share this label</span>`;
}

/* The readings a row's collector could not take from a store it opened, as the
   page's own sentence. `source_gaps` is an untrusted published array, so a
   non-array and a non-string member are both nothing.

   NOT a `<details>`, and that is the decision worth recording: a disclosure the
   reader has to open is one they can leave shut, and this qualifies a claim
   ("generating…", "awaiting your message") that is already on screen beside it.
   It also adds no row to docs/design-reader-state.md, because there is nothing
   for a redraw to throw away. */
function nextSessionGapNames(session){
  const gaps = session && session.source_gaps;
  if(!Array.isArray(gaps)) return [];
  return gaps
    .filter(name => typeof name === "string" && name.trim())
    .map(name => name.trim());
}

const NEXT_UNREAD_SOURCE_NOTE = "Cargento opened this session's store and could not read " +
  "every part of it. What it names is missing here rather than empty; the rest of the row " +
  "was read normally.";

function nextSessionUnread(session){
  const names = nextSessionGapNames(session);
  if(!names.length) return "";
  return `<span class="next-operation-unread" title="${esc(NEXT_UNREAD_SOURCE_NOTE)}">` +
    `Source not fully read: ${esc(names.join(", "))}</span>`;
}

/* Whether no event can ever reach this row, so an absent stop on it says
   nothing about whether the turn ended. `acquisition` is published, and
   therefore untrusted: one exact string and nothing else, because a truthy
   check would print the sentence for "event" — the value that means the
   opposite — as readily as for a hostile one.

   A published stop takes precedence, and that arm is unreachable from this
   server rather than dead code: `events.parse` refuses the six harnesses'
   envelopes outright, so the two cannot disagree on a row Cargento built. It is
   here because the sentence says a stop could not be observed, and a stamp
   beside it would make that false on the reader's screen. */
function nextSessionIsScanOnly(session){
  if(!session || session.acquisition !== "scan-only") return false;
  const finished = Number(session.finished_at);
  return !(Number.isFinite(finished) && finished > 0);
}

const NEXT_SCAN_ONLY_NOTE = "Cargento reads this session off disk and no event from its " +
  "harness can reach it, so an idle row here means nothing has changed recently rather " +
  "than that the turn ended. The rest of the row was read normally.";

/* Beside the unread-source sentence and styled with it, because both are facts
   about the row's source qualifying a reading already on screen. Not a
   `<details>` for #302's reason, recorded in docs/design-unread-sources.md.
   Unconditional on `state`: the field is a property of the harness, and the
   working arm is where the reader most needs it — that row will stop, and
   nothing will tell them it did. See docs/design-scan-only-rows.md. */
function nextSessionScanOnly(session){
  if(!nextSessionIsScanOnly(session)) return "";
  return `<span class="next-operation-scan-only" title="${esc(NEXT_SCAN_ONLY_NOTE)}">` +
    "Read by scanning: no turn end can be observed here</span>";
}

function nextOperationsAsks(rows){
  if(!nextData || nextData.ask !== true) return [];
  const identities = new Set(rows.map(nextSessionKey));
  return nextPayloadAsks(nextData).filter(ask => {
    const owner = nextExactAskOwner(nextData, ask);
    return owner && identities.has(nextSessionKey(owner));
  });
}

function nextOperationsHarnesses(){
  const entries = nextData && Array.isArray(nextData.harnesses) ? nextData.harnesses : [];
  return new Map(entries.map(entry => [String(entry && entry.key || ""), entry]));
}

function nextOperationsReportsBlocks(session, harnesses){
  if(session.state === "needs_input") return true;
  const harness = harnesses.get(String(session.harness || ""));
  return Boolean(harness && harness.reports_needs_input === true);
}

function nextOperationsAskFor(session, asks){
  const key = nextSessionKey(session);
  return asks.find(ask => {
    const owner = nextExactAskOwner(nextData, ask);
    return owner && nextSessionKey(owner) === key;
  }) || null;
}

function nextOperationsIsBlocked(session, asks){
  return session.state === "needs_input" || Boolean(nextOperationsAskFor(session, asks));
}

function nextOperationsIsActive(session, asks){
  /* An observed end retires the state word and nothing else. `state` is a
     collector inference off file recency, and `session_ended` publishes no
     state of its own — it pops the whole overlay ledger — so the capture's
     0.565–5.581s gap between the last transcript write and the end leaves
     `working` standing for the rest of `working_threshold_sec` (90s). Without
     this the row that just ended sits in the lane whose whole job is "what is
     still running", for a minute and a half after every ordinary end.
     An outstanding exact request still holds the row here: the request is a
     published fact with its own lifecycle, not a reading of this session's
     recency, and it is answered or withdrawn rather than aged out. */
  const running = nextSessionEndedAt(session) == null &&
    ["working", "needs_input"].includes(String(session.state || ""));
  return running || Boolean(nextOperationsAskFor(session, asks));
}

function nextOperationsFleetFact(kind, label, value, note = ""){
  const detail = note ? `<small>${esc(note)}</small>` : "";
  return `<section data-next-fleet-fact="${kind}"><span>${label}</span>` +
    `<strong>${value}</strong>${detail}</section>`;
}

function nextOperationsFleet(rows, asks, harnesses){
  const active = rows.filter(session => nextOperationsIsActive(session, asks)).length;
  const working = rows.filter(session => session.state === "working").length;
  const blocks = rows.filter(session => nextOperationsIsBlocked(session, asks)).length;
  const covered = rows.filter(session =>
    nextOperationsReportsBlocks(session, harnesses) || nextOperationsAskFor(session, asks)).length;
  const coverage = `${covered} of ${rows.length} sessions report block state`;
  return '<section class="next-operations-fleet" aria-label="Fleet facts">' +
    nextOperationsFleetFact("active", "ACTIVE NOW", active, `${rows.length} recently observed`) +
    nextOperationsFleetFact("working", "WORKING", working) +
    nextOperationsFleetFact("requests", "EXACT REQUESTS", asks.length) +
    nextOperationsFleetFact("reported-blocks", "REPORTED BLOCKS", blocks, coverage) +
    "</section>";
}

function nextOperationsTask(session, status){
  const tasks = Array.isArray(session.tasks) ? session.tasks : [];
  return tasks.find(task =>
    task && task.status === status && String(task.subject || "").trim()) || null;
}

function nextOperationsFact(kind, label, value, detail = "", tone = ""){
  const suffix = tone ? ` next-operation-fact--${tone}` : "";
  const secondary = detail ? `<em>${esc(detail)}</em>` : "";
  return `<span class="next-operation-fact${suffix}" data-next-operation-fact="${kind}">` +
    `<small>${label}</small><strong>${esc(value)}</strong>${secondary}</span>`;
}

function nextOperationsWhere(session){
  const project = String(session.project == null ? "" : session.project).trim();
  return nextOperationsFact(
    "where",
    "WHERE · PROJECT LABEL",
    project || "Project label not published",
    "Exact location not published",
  );
}

function nextOperationsNow(session){
  /* Reached with an end stamped only where something other than `state` kept
     the row active — an outstanding exact request — and the end still wins
     the NOW cell, for the reason `nextOperationsIsActive` gives. */
  const endedAt = nextSessionEndedAt(session);
  if(endedAt != null) return nextOperationsEndedNow(endedAt);
  const inProgress = nextOperationsTask(session, "in_progress");
  const state = String(session.state || "").replace("_", " ").trim();
  const detail = inProgress
    ? String(inProgress.subject).trim()
    : String(session.state_detail || "").trim();
  return nextOperationsFact(
    "now",
    `NOW${state ? ` · ${state.toUpperCase()}` : ""}`,
    detail || "Activity not published",
  );
}

function nextOperationsNext(session){
  const pending = nextOperationsTask(session, "pending");
  return nextOperationsFact(
    "next",
    "NEXT",
    pending ? String(pending.subject).trim() : "No pending step published",
  );
}

function nextOperationsBlocked(session, asks, harnesses){
  const ask = nextOperationsAskFor(session, asks);
  if(session.state === "needs_input" || ask){
    const question = String(ask && ask.question || "").trim();
    const detail = question || String(session.state_detail || "").trim() || "Block reported";
    const responsibility = ask ? ` · ${nextAskResponsibility(nextData, ask)}` : "";
    return nextOperationsFact(
      "blocked", `BLOCKED${responsibility}`, "Reported", detail, "blocked",
    );
  }
  if(nextOperationsReportsBlocks(session, harnesses)){
    return nextOperationsFact(
      "blocked", "BLOCKED", "No reported block", "Reporter available", "clear",
    );
  }
  return nextOperationsFact(
    "blocked", "BLOCKED", "Unknown", "Harness does not report blocks", "unknown",
  );
}

function nextOperationsAssignment(session){
  const assignment = nextSessionInstruction(session, "asked");
  const text = assignment ? String(assignment.text || "").trim() : "";
  const title = String(session.title || session.last_prompt || "").trim();
  return text && text !== title
    ? `<span class="next-operation-assignment">ASSIGNMENT · ${esc(text)}</span>`
    : "";
}

function nextOperationsIdentity(session, labels, collisions, route, history = false){
  const harness = String(session.harness == null ? "" : session.harness);
  const harnessLabel = labels.get(harness) || harness || "Harness not published";
  const title = String(session.title || session.last_prompt || "").trim() || "Title not published";
  const live = session.active === true && session.state === "working";
  const dot = live ? nextStatusDot("working", "next-operation-live-glyph") : "";
  return '<span class="next-operation-identity">' +
    `<small class="next-operation-local-label">SESSION</small>` +
    `<span class="next-operation-harness">${esc(harnessLabel)}</span>` +
    `<a class="next-operation-route" href="#n=${esc(route)}" data-next-route="${esc(route)}" ` +
    `aria-label="Open session ${esc(title)}"><strong>${dot}${esc(title)}</strong></a>` +
    nextSessionCopyControl(session) +
    (history ? "" : nextOperationsAssignment(session)) +
    nextSessionCollision(session, collisions) +
    /* In the identity cell rather than in one column's slot, and on the history
       row as well as the live one: the fact is about the whole row's source, and
       the two lanes are the row's two arms — a store that would not read renders
       here as quiet and there as working. */
    nextSessionScanOnly(session) + nextSessionUnread(session) + "</span>";
}

function nextOperationsEndedNow(endedAt){
  const since = nextDurationSince(endedAt);
  return nextOperationsFact(
    "now", "NOW · ENDED", "Session reported its own end",
    since ? `ended ${since} ago` : "",
  );
}

function nextOperationsHistoryNow(session){
  /* A history row has always shown "—", because nothing about a quiet session
     is knowable from recency alone. An observed end is the one exception, and
     it is an exception because the session reported it rather than because the
     row went quiet: a row with no stamp keeps the dash. */
  const endedAt = nextSessionEndedAt(session);
  if(endedAt == null) return nextOperationsFact("now", "NOW", "—");
  return nextOperationsEndedNow(endedAt);
}

function nextOperationsRow(session, labels, collisions, asks, harnesses, history = false){
  const project = String(session.project == null ? "" : session.project);
  const harness = String(session.harness || "");
  const sid = String(session.sid || "");
  const route = nextRouteToken({view: "session", project, harness, session: sid});
  const state = String(session.state || "unknown");
  const live = session.active === true && state === "working" ? " next-live" : "";
  const historyAttr = history ? ' data-next-operation-history="true"' : "";
  const now = history ? nextOperationsHistoryNow(session) : nextOperationsNow(session);
  const next = history ? nextOperationsFact("next", "NEXT", "—") : nextOperationsNext(session);
  const blocked = history
    ? nextOperationsFact("blocked", "BLOCKED", "—")
    : nextOperationsBlocked(session, asks, harnesses);
  return `<article class="next-operation-row next-operation-row--${esc(state)}${live}" ` +
    `data-next-harness="${esc(harness)}" data-next-session="${esc(sid)}" ` +
    `${historyAttr}>` +
    nextOperationsIdentity(session, labels, collisions, route, history) +
    nextOperationsWhere(session) +
    now + next + blocked + "</article>";
}

function nextOperationsColumns(){
  return '<div class="next-operations-columns" aria-hidden="true">' +
    '<span>SESSION</span><span>WHERE</span><span>NOW</span><span>NEXT</span>' +
    '<span>BLOCKED</span></div>';
}

function nextOperationsGroup(kind, title, description, sessions, renderer, empty){
  const rows = sessions.map(renderer).join("");
  const body = rows || `<p class="next-sessions-empty">${esc(empty)}</p>`;
  return `<section class="next-operation-group next-operation-group--${kind}" ` +
    `data-next-operation-group="${kind}"><header><h2>${title}</h2>` +
    `<p>${description}</p></header>${nextOperationsColumns()}` +
    `<div class="next-operation-rows">${body}</div></section>`;
}

function nextSessionsView(){
  const rows = nextRows();
  const asks = nextOperationsAsks(rows);
  const harnesses = nextOperationsHarnesses();
  const blocks = nextSessionBlocks();
  const labels = nextHarnessLabels();
  const collisions = nextSessionCollisionCounts();
  const ordered = [...blocks.gates, ...blocks.working, ...blocks.idle, ...blocks.other];
  const active = ordered.filter(session => nextOperationsIsActive(session, asks));
  const history = ordered.filter(session => !nextOperationsIsActive(session, asks));
  const renderActive = session =>
    nextOperationsRow(session, labels, collisions, asks, harnesses, false);
  const renderHistory = session =>
    nextOperationsRow(session, labels, collisions, asks, harnesses, true);
  const windowHours = nextNumber(nextData && nextData.window_hours);
  const window = windowHours == null ? "current payload" : `${windowHours}h payload`;
  return '<section class="next-operations" data-next-view-body="sessions">' +
    '<header class="next-operations-header"><span>COMMAND SURFACE</span>' +
    '<h1>Session operations</h1>' +
    '<p>Active evidence leads. Every recently observed session remains reachable.</p></header>' +
    nextOperationsFleet(rows, asks, harnesses) +
    // Directly beneath the fleet counts, because "what is my fleet doing" and
    // "how long can it keep doing it" are one look. Its own strip rather than a
    // fifth count: a projection is not a count, and the fleet grid collapses
    // two-by-two on narrow screens with exactly four cells.
    nextCapacityView(nextData) +
    nextOperationsGroup(
      "active", "Active now",
      "Working, needs-input, or exact request.",
      active, renderActive, "No exact session has active evidence right now.",
    ) + nextOperationsGroup(
      "history", "Recent history",
      "Recently observed is not proof the harness process is still open or closed; " +
        "rows marked ENDED reported their own end.",
      history, renderHistory, `No recent-history rows in this ${window}.`,
    ) + "</section>";
}
