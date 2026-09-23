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

function nextOperationsFleet(model){
  const keys = ["active", "working", "requests", "reported-blocks"];
  return '<section class="next-operations-fleet" aria-label="Fleet facts">' +
    model.counters.map((counter, index) => nextOperationsFleetFact(
      keys[index], esc(counter.label), esc(counter.value), counter.noteText,
    )).join("") + "</section>";
}

function nextOperationsTask(session, status){
  const tasks = Array.isArray(session.tasks) ? session.tasks : [];
  return tasks.find(task =>
    task && task.status === status && String(task.subject || "").trim()) || null;
}

function nextOperationsFact(kind, label, value, detail = "", tone = ""){
  const suffix = tone ? ` next-operation-fact--${tone}` : "";
  const secondary = detail ? `<em>${esc(detail)}</em>` : "";
  /* An `unknown` value is a stated absence, and absences wear `.next-absence`
     rather than dim body text, so "not published" never reads as a quieter
     version of a value. */
  const absence = tone === "unknown" ? ' class="next-absence"' : "";
  return `<span class="next-operation-fact${suffix}" data-next-operation-fact="${kind}">` +
    `<small>${label}</small><strong${absence}>${esc(value)}</strong>${secondary}</span>`;
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
    (!session.titleKnown && session.promptKnown ?
      `<span class="next-operation-assignment">LAST PROMPT · ${esc(session.promptText)}</span>` : "") +
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
  // Recency cannot establish current activity; an end requires its own stamp.
  const endedAt = nextSessionEndedAt(session);
  if(endedAt == null) return nextOperationsFact("now", "NOW", "Current activity not observed");
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
  const next = history ? nextOperationsFact("next", "NEXT", "No current step observed") : nextOperationsNext(session);
  const blocked = history
    ? nextOperationsFact("blocked", "BLOCKED", "Current block state not observed")
    : nextOperationsBlocked(session, asks, harnesses);
  return `<article class="next-operation-row next-operation-row--${esc(state)}${live}" ` +
    `data-next-harness="${esc(harness)}" data-next-session="${esc(sid)}" ` +
    `${historyAttr}>` +
    nextOperationsIdentity(session, labels, collisions, route, history) +
    nextOperationsWhere(session) +
    now + next + blocked + "</article>";
}

function nextOperationsColumns(history = false){
  return '<div class="next-operations-columns" aria-hidden="true">' +
    '<span>SESSION</span><span>WHERE</span><span>GOAL</span><span>NOW</span>' +
    (history ? '<span>STATE</span>' : '<span>NEXT</span><span>BLOCKED</span>') + '</div>';
}

/* `label` is a fragment naming what the group holds; `caveat` is a sentence
   qualifying it, and goes behind a disclosure so the first screen carries
   values rather than prose
   ([NUI-19](docs/design-next-ui.md#nui-19-a-caveat-has-three-tiers)). */
function nextOperationsGroup(kind, title, label, sessions, renderer, empty, caveat = null){
  const rows = sessions.map(renderer).join("");
  const body = rows || `<p class="next-sessions-empty next-absence">${esc(empty)}</p>`;
  const lead = label ? `<p>${esc(label)}</p>` : "";
  const why = caveat ? nextCockpitWhy(`sessions-${kind}-why`, caveat.summary, caveat.body) : "";
  return `<section class="next-operation-group next-operation-group--${kind}" ` +
    `data-next-operation-group="${kind}"><header><h2>${title}</h2>` +
    `${lead}${why}</header>${nextOperationsColumns(kind === "history")}` +
    `<div class="next-operation-rows">${body}</div></section>`;
}

function nextOperationsObservedFact(kind, label, text, known, note = "", tone = ""){
  return nextOperationsFact(kind, label, text, note, known ? tone : "unknown");
}

function nextOperationsObservedIdentity(session, source, labels, route, history){
  const dot = session.isLive
    ? nextStatusDot("working", "next-operation-live-glyph") : "";
  const titleClass = session.titleKnown ? "" :
    ' class="next-operation-title--unknown next-absence"';
  const collision = session.sharedLabelKnown
    ? `<span class="next-operation-collision" title="${esc(NEXT_DUPLICATE_LABEL_LIMIT)}">` +
      `${esc(session.sharedLabelText)}</span>` : "";
  return '<span class="next-operation-identity">' +
    '<small class="next-operation-local-label">SESSION</small>' +
    `<span class="next-operation-harness">${esc(labels.get(session.harness) || session.harness)}</span>` +
    `<a class="next-operation-route" href="#n=${esc(route)}" data-next-route="${esc(route)}" ` +
    `aria-label="Open session ${esc(session.titleText)}"><strong${titleClass}>${dot}${esc(session.titleText)}</strong></a>` +
    nextSessionCopyControl(session) +
    (!session.titleKnown && session.promptKnown ?
      `<span class="next-operation-assignment">LAST PROMPT · ${esc(session.promptText)}</span>` : "") +
    (history ? "" : nextOperationsAssignment(source)) + collision +
    nextSessionScanOnly(source) + nextSessionUnread(source) + "</span>";
}

/* [DEC-22](docs/design-reading-a-session.md#dec-22-your-own-prompt-may-become-your-goal)
   admits the collector's asked Claude instruction and classified Codex
   title, never a workflow/observer paraphrase. Displaying it saves nothing. */
function nextSessionsGoal(source, route){
  if(!(nextData && nextData.annotate === true)){
    return nextOperationsFact("goal", "GOAL", "Annotations off", "", "unknown");
  }
  const typed = String(source && source.annotation_goal || "").trim();
  const asked = source && source.harness === "claude" ? nextSessionInstruction(source, "asked") : null;
  const prompt = asked ? String(asked.text || "").trim()
    : source && source.harness === "codex" && source.prompt_states_work === true
      ? String(source.title || "").trim() : "";
  const text = typed || prompt;
  const label = typed ? "GOAL · YOUR WORDS" : prompt ? "GOAL · YOUR LATEST PROMPT" : "GOAL";
  const content = typed ? `<strong>${esc(text)}</strong>`
    : `<a class="next-operation-goal-link${text ? "" : " next-absence"}" ` +
      `href="#n=${esc(route)}" data-next-route="${esc(route)}" data-next-goal-focus>` +
      `${esc(text || "Add a goal")}</a>`;
  return `<span class="next-operation-fact" data-next-operation-fact="goal">` +
    `<small>${label}</small>${content}</span>`;
}

/* A record projection, not a new reading. Neither the annotation's presence
   nor its press count establishes a departure. Legacy assessments have no
   reading epoch; their clock-only stamp cannot supply one. */
function nextSessionsDrift(source){
  if(!(nextData && nextData.annotate === true) || !source) return [];
  const rows = (Array.isArray(source.departures) ? source.departures : [])
    .filter(row => row && typeof row === "object")
    .map(row => ({at: nextNumber(row.at), revision: nextNumber(row.revision), subject: "This raise"}));
  const raw = source.annotation_assessment;
  if(raw && typeof raw === "object" && !Array.isArray(raw) &&
      Object.keys(raw).every(key => NEXT_READING_ASSESSMENT_KEYS.includes(key)) &&
      ["goal", "output"].some(key => {
        const criterion = raw.criteria && raw.criteria[key];
        return criterion && criterion.result === "departure" &&
          Array.isArray(criterion.cites) && criterion.cites.some(cite => typeof cite === "string" && cite.trim());
      })){
    rows.push({at: nextNumber(raw.read_at), revision: nextNumber(raw.revision_read), subject: "This reading"});
  }
  return rows;
}

function nextSessionsDriftMark(source){
  const records = nextSessionsDrift(source);
  if(!records.length) return "";
  const dated = records.map(row => row.at).filter(at => at != null && at > 0);
  const age = dated.length ? nextDurationSince(Math.max(...dated)) : null;
  const stale = [...new Set(records.map(row => nextRevisionSuperseded(
    row.subject, row.revision, nextNumber(source.annotation_revision))).filter(Boolean))];
  return '<span class="next-operation-drift" data-next-session-drift-mark>' +
    `<strong>Drift</strong> · ${esc(age == null ? "age unknown" : `${age} ago`)}` +
    (records.some(row => row.at == null || row.at <= 0) && dated.length
      ? '<small>Some recorded departure ages are unknown</small>' : "") +
    stale.map(line => `<small>${esc(line)}</small>`).join("") + '</span>';
}

/* Promote only this screen's rows. Changing shared isActive or model.active
   would turn a stored reading into running evidence and inflate its counter. */
function nextSessionsGroups(model, sources){
  const ordered = [...model.active, ...model.history];
  const rank = session => session.isNeeds || session.askKnown ? 0
    : nextSessionsDrift(sources.get(nextSessionKey(session))).length ? 1 : 2;
  const active = ordered.filter(session => session.isActive || rank(session) < 2);
  const activeKeys = new Set(active.map(nextSessionKey));
  active.sort((left, right) => rank(left) - rank(right));
  return {active, history: ordered.filter(session => !activeKeys.has(nextSessionKey(session)))};
}

function nextOperationsObservedRow(session, source, labels, asks, history){
  const route = nextRouteToken({view: "session", project: session.project,
    harness: session.harness, session: session.sid});
  const identity = nextOperationsObservedIdentity(session, source, labels, route, history);
  const goal = nextSessionsGoal(source, route);
  const where = nextOperationsObservedFact("where", "WHERE · PROJECT LABEL", session.whereText,
    session.whereKnown, session.project);
  const since = session.isEnded ? nextDurationSince(nextSessionEndedAt(source)) : "";
  const now = nextOperationsObservedFact("now",
    session.isEnded ? "NOW · ENDED" : `NOW · ${session.state.replaceAll("_", " ").toUpperCase()}`,
    session.nowText, session.nowKnown, since ? `ended ${since} ago` : "");
  const outcome = session.outcomeKnown
    ? `<span class="next-operation-outcome next-operation-outcome--${esc(session.tone)}">` +
      `${esc(session.outcomeGlyph)} ${esc(session.outcomeText)}` +
      `<span class="next-operation-outcome${session.gitKnown ? "" : " next-operation-outcome--unknown"}">` +
      `${esc(session.gitText)}</span></span>` : "";
  const stateTag = session.isEnded ? "ENDED" : (session.isQuiet ? "QUIET" : "");
  const tag = stateTag ? `<span class="next-operation-state">${stateTag}</span>` : "";
  let facts;
  if(history){
    facts = `<div class="next-operation-history-now">${now}${outcome}</div>` + tag;
  }else{
    const ask = nextOperationsAskFor(source, asks);
    const responsibility = ask ? ` · ${nextAskResponsibility(nextData, ask)}` : "";
    facts = now +
      nextOperationsObservedFact("next", "NEXT", session.nextText, session.nextKnown) +
      nextOperationsObservedFact("blocked", `BLOCKED${responsibility}`,
        session.blockText, session.blockKnown, session.blockNote,
        session.isNeeds || session.askKnown ? "blocked" : "clear") +
      (stateTag || outcome ? `<div class="next-operation-end-note">${tag}${outcome}</div>` : "");
  }
  return `<article class="next-operation-row next-operation-row--${esc(session.tone)}" ` +
    `data-next-harness="${esc(session.harness)}" data-next-session="${esc(session.sid)}"` +
    (history ? ' data-next-operation-history="true"' : "") + ">" +
    identity + where + goal + facts + nextSessionsDriftMark(source) + "</article>";
}

/* Whether any session in the payload carries a check: a stored reading, a
   reading counted against its words, an unasked check, or a departure on record.
   Read off the rows rather than off a flag, and only while the annotation store is on,
   because with it off a stored reading is not published and "none" would be
   a claim about something the page cannot see. Returns null for that case. */
function nextSessionsAnyChecked(rows){
  if(!(nextData && nextData.annotate === true)) return null;
  return rows.some(session => {
    if(session.departure_checked === true) return true;
    const assessment = session.annotation_assessment;
    if(assessment !== undefined && assessment !== null && assessment !== "") return true;
    if((nextNumber(session.annotation_reading_count) || 0) > 0) return true;
    return Array.isArray(session.departures) && session.departures.length > 0;
  });
}

/* The first screen's one sentence of prose
   ([DEC-20](docs/design-reading-a-session.md#dec-20-the-first-screen-shows-goal-beside-direction-and-drift-has-one-home)):
   the "not checked" line its table allows on a default run, and nothing once
   a check exists or when checks cannot be seen. It carries no count, because
   a drift total on any screen is the aggregation that ruling refuses. */
const NEXT_SESSIONS_NOT_CHECKED = "No session has been checked for drift yet; open one to check it.";

function nextSessionsView(){
  const model = nextCurrentObserved();
  const sources = new Map(nextRows().map(session => [nextSessionKey(session), session]));
  const asks = nextOperationsAsks(nextRows());
  const groups = nextSessionsGroups(model, sources);
  const labels = nextHarnessLabels();
  const renderRow = (session, history) => nextOperationsObservedRow(
    session, sources.get(nextSessionKey(session)), labels, asks, history,
  );
  const lede = nextSessionsAnyChecked(nextRows()) === false
    ? `<p>${esc(NEXT_SESSIONS_NOT_CHECKED)}</p>` : "";
  /* The fleet facts are the first thing read: four values that answer whether
     anything needs the reader before any sentence does. Active now follows,
     gate-first by `nextObservedLaneOrder`. The capacity strip, whose consent
     and budget sentences answer a different question, sits after both groups
     so the first screen carries values rather than prose. */
  return '<section class="next-operations" data-next-view-body="sessions">' +
    '<header class="next-operations-header"><span>COMMAND SURFACE</span>' +
    '<h1>Session operations</h1>' + lede +
    nextCockpitWhy("sessions-board-why", "How rows are split",
      "Blocked sessions lead, followed by recorded departures, then working sessions. " +
      "The Active now figure counts active evidence only; a recorded departure adds no active session.") +
    nextCockpitWhy("sessions-goal-source", "Goal sources",
      nextData && nextData.annotate === true
        ? "Your latest prompt comes from Claude Code or Codex; other harnesses show only your typed words. " +
          "Showing a prompt does not adopt it as a goal; a Drift mark names a departure on record, not a new check."
        : "Annotations are off, so goals cannot be typed and Drift marks are not shown.") +
    '</header>' +
    nextOperationsFleet(model) +
    nextOperationsGroup(
      "active", "Active now", "working, waiting on you, an exact request, or recorded drift",
      groups.active, session => renderRow(session, false), "No exact session has active evidence right now.",
    ) + nextOperationsGroup(
      "history", "Recent history", "",
      groups.history, session => renderRow(session, true), "No recent-history rows in this payload.",
      {summary: "What recent means",
        body: "Recently observed is not proof the harness process is still open or closed; " +
          "rows marked ENDED reported their own end."},
    ) + nextCapacityView(nextData) + "</section>";
}
