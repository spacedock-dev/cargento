const NEXT_ANSWER_FAILURE = "no confirmation came back — it may already have been answered";
const NEXT_SESSION_LONG_TURN_NOTE = "This request is running long (or estimated to). " +
  "Double-check what the agent is doing matches your expectations.";
const NEXT_SESSION_MCP_TOOL = /\bmcp__([A-Za-z0-9-]+(?:_[A-Za-z0-9-]+)*?)__([A-Za-z0-9_-]+)/g;
const NEXT_SESSION_MCP_HOST_PREFIX = /^(?:claude_ai_|claude_code_|plugin_)/;
const nextSessionAnswerNotes = new Map();

function nextSessionFind(project, harness, sid){
  const projectKey = String(project == null ? "" : project);
  const harnessKey = String(harness == null ? "" : harness);
  const sessionKey = String(sid == null ? "" : sid);
  const matches = nextRows().filter(session =>
    String(session.project == null ? "" : session.project) === projectKey &&
    String(session.sid == null ? "" : session.sid) === sessionKey &&
    (!harnessKey || String(session.harness == null ? "" : session.harness) === harnessKey)
  );
  return matches.length === 1 ? matches[0] : null;
}

function nextSessionAsks(session){
  if(!nextData || nextData.ask !== true || !Array.isArray(nextData.asks)) return [];
  const key = nextSessionKey(session);
  return nextData.asks.filter(ask => {
    const owner = nextExactAskOwner(nextData, ask);
    return owner && nextSessionKey(owner) === key;
  });
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

function nextSessionSourceOwner(session){
  const harness = String(session && session.harness || "");
  if(harness === "codex") return "Codex transcript";
  if(harness === "claude") return "Claude transcript";
  if(harness === "antigravity") return "AGY CLI log";
  const label = nextSessionRegistryLabel(session);
  return label ? `${label} session source` : "Session source";
}

function nextSessionInstruction(session, label){
  const instruction = session && session.instruction;
  if(!instruction || typeof instruction !== "object" || Array.isArray(instruction)) return null;
  if(String(instruction.label || "") !== label) return null;
  return String(instruction.text == null ? "" : instruction.text).trim() ? instruction : null;
}

function nextSessionSourceCoverage(owner, next, asks, openDisclosures){
  if(asks.length || next) return "";
  return '<details class="next-session-source-coverage"' +
    `${nextDisclosureAttr("session-source-coverage", openDisclosures)}>` +
    '<summary data-next-disclosure="session-source-coverage" ' +
    'data-next-focus="session-source-coverage">SOURCE COVERAGE</summary>' +
    `<p>${esc(owner)} did not publish a next action.</p></details>`;
}

function nextSessionCommandFact(kind, label, body){
  return `<section data-next-session-command-fact="${kind}"><h2>${label}</h2>${body}</section>`;
}

/* The agent's direction, which the drift block sets beside the reader's words
   (the drift ruling names the NOW line as the direction). It used to lead the page with
   the identity header inside it; the drift block now leads, and this card is
   its second part rather than a copy of it, so the NOW line has one renderer. */
function nextSessionCommandSurface(session, observed){
  const context = nextSessionInstruction(session, "agent") || nextSessionInstruction(session, "earlier");
  const contextLine = context ? nextInstructionLine(session, "", "next-session-command-context") : "";
  const state = observed.isNeeds ? "waiting on you" : (observed.isEnded ? "session ended" : observed.state);
  return '<div class="next-session-command-surface" aria-label="Session command surface">' +
    '<section class="next-session-current" data-next-session-command="activity">' +
    '<span class="next-session-current-label">CURRENT ACTIVITY</span>' +
    `<strong${observed.nowKnown ? "" : ' class="next-session-absent"'}>` +
    `${esc(state)} · ${esc(observed.nowText)}</strong>${contextLine}</section></div>`;
}

function nextSessionFacts(observed, asks){
  const rows = [
    ["NEXT STEP", "next", observed.nextText, observed.nextKnown],
    ["TURN", "turn", observed.turnText, observed.turnKnown],
    ["BLOCKED", "block", observed.blockText, observed.blockKnown],
    ["OUTCOME", "outcome", observed.outcomeText, observed.outcomeKnown],
    ["GIT STATE", "git", observed.gitText, observed.gitKnown],
    ["PROJECT", "project", observed.project, true],
  ];
  return '<dl class="next-session-facts">' + rows.map(([label, key, text, known]) => {
    let value = `<span${known ? "" : ' class="next-session-absent"'}>${esc(text)}</span>`;
    if(key === "next" && known && !asks.length){
      value = `<section data-next-session-command-fact="next">${value}</section>`;
    }
    const note = key === "block"
      ? `<span class="next-session-fact-note">${esc(observed.blockNote)}</span>` : "";
    return `<div data-next-session-fact="${key}"><dt>${label}</dt><dd>${value}${note}</dd></div>`;
  }).join("") + "</dl>";
}

function nextSessionTitle(session){
  return nextCurrentObserved().sessions.find(row =>
    nextSessionKey(row) === nextSessionKey(session) && row.project === String(session.project == null ? "" : session.project)).titleText;
}

function nextSessionMeta(session){
  const parts = [];
  const harness = nextSessionRegistryLabel(session);
  if(harness) parts.push(harness);
  /* An observed end supersedes the present-tense activity and duration phrases;
     an ended session must not describe itself as awaiting input (DRC-4554). */
  const ended = nextDurationSince(nextSessionEndedAt(session));
  if(ended != null){
    parts.push(`ended ${ended} ago`);
  }else{
    if(session.state_detail) parts.push(String(session.state_detail));
    if(session.state === "needs_input"){
      const blocked = nextDurationSince(session.blocked_since);
      if(blocked != null) parts.push(`blocked ${blocked}`);
      if(session.wait_unconfirmed) parts.push("unconfirmed: no positive observation in 5m");
    }else if(session.state === "working"){
      const turn = session.turn;
      const elapsed = turn && typeof turn === "object" && !Array.isArray(turn) &&
        typeof turn.elapsed_h === "string" ? turn.elapsed_h.trim() : "";
      if(elapsed) parts.push(`turn started ${elapsed} ago`);
    }else if(session.state === "idle"){
      const started = nextDurationSince(session.started_at);
      if(started != null) parts.push(`session started ${started} ago`);
    }
  }
  /* These last two are unconditional, and both for the reason the first one
     gives: every clause above is a reading, and these say what the readings
     cannot cover, so they qualify the whole line rather than any one of them.
     The row already carries both, but a reader who clicked through from a
     disclosed row must not arrive at a page that asserts the state alone. */
  if(nextSessionIsScanOnly(session)){
    parts.push("read by scanning: no turn end can be observed here");
  }
  const gaps = nextSessionGapNames(session);
  if(gaps.length) parts.push(`source not fully read: ${gaps.join(", ")}`);
  return parts.join(" · ");
}

function nextSessionAskBlock(session, asks, observed){
  if(!observed.askKnown) return "";
  const cards = asks.map(ask => {
    const id = String(ask && ask.id || "");
    const options = Array.isArray(ask && ask.options) ? ask.options : [];
    const buttons = options.map((option, index) =>
      `<button type="button" class="next-action" data-next-answer="${esc(id)}" ` +
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
      `<p class="next-session-ask-question">${esc(asks.length === 1 ? observed.askText : ask.question)}</p>` +
      choices + note + "</article>";
  }).join("");
  return '<section class="next-session-section" data-next-session-section="ask">' +
    '<div class="next-session-ask-callout">' +
    `<span>ASKED YOU · <span class="next-session-wait" data-known="${observed.waitedKnown === true}">` +
    `${esc(observed.waitedText)}</span></span>` +
    `<strong class="next-visually-hidden">AGENT IS ASKING · ${esc(nextSessionAskingTitle(session))}</strong>` +
    nextSessionCommandFact("request", nextAskResponsibility(nextData, asks[0]), "") +
    '</div>' + (asks.length ? cards : `<p class="next-session-ask-question">${esc(observed.askText)}</p>`) +
    '</section>';
}

// Keep transport-name presentation beside the session detail that uses it.
function nextSessionHumanTool(text){
  return text.replace(NEXT_SESSION_MCP_TOOL, (whole, server, tool) => {
    const service = server.replace(NEXT_SESSION_MCP_HOST_PREFIX, "").replace(/_+/g, " ").trim();
    const action = tool.replace(/_+/g, " ").trim();
    if(!action) return whole;
    return (service ? `${service} · ` : "") + action;
  });
}

function nextSessionLoopNote(loop){
  if(!loop || typeof loop !== "object" || Array.isArray(loop)) return "";
  const errors = nextNumber(loop.errors);
  if(errors == null || !Number.isInteger(errors) || errors <= 0) return "";
  const rawTool = typeof loop.tool === "string" ? loop.tool.trim() : "";
  const tool = rawTool ? ` (most recently ${nextSessionHumanTool(rawTool)})` : "";
  const failures = nextNumber(loop.failures);
  const total = failures != null && Number.isInteger(failures) && failures > errors
    ? failures
    : errors;
  const calls = total === 1 ? "tool call" : "tool calls";
  const advice = "Check the agent is working the problem rather than repeating the failure.";
  // Three readings of one turn, and each sentence says which one fired. Saying
  // "in a row" about a total would be false the moment a success split it,
  // which is the whole reason the total exists (DRC-4021).
  if(loop.barren === true){
    return `${total} ${calls} failed this turn and none succeeded${tool}. ${advice}`;
  }
  if(total > errors){
    return `${total} ${calls} failed this turn, ${errors} of them consecutive${tool}. ${advice}`;
  }
  return `${errors} ${calls} in a row came back as errors${tool}. ${advice}`;
}

function nextSessionHealth(session){
  const turn = session && session.turn;
  const long = Boolean(turn && typeof turn === "object" && !Array.isArray(turn) &&
    turn.long === true);
  const loopNote = nextSessionLoopNote(session && session.loop);
  if(!long && !loopNote) return "";
  const kind = long ? "long-turn" : "failed-tool-loop";
  const label = long ? "LONG TURN" : "FAILED TOOL LOOP";
  const why = loopNote || NEXT_SESSION_LONG_TURN_NOTE;
  return `<aside class="next-session-health" role="note" aria-label="${label}" ` +
    `data-next-session-health="${kind}"><strong>${label}</strong>` +
    '<span class="next-session-health-separator" aria-hidden="true"> — </span>' +
    `<span>${esc(why)}</span></aside>`;
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
  /* Gated on the payload, not on the harness name. It was `harness !== "claude"`
     while Claude was the only collector filling the field, and that spelling
     then hid a Codex plan the moment one arrived — a harness allowlist reports
     "no tasks" for a session that published fifteen. An empty list still renders
     nothing, which is the check that was actually wanted. */
  const tasks = Array.isArray(session.tasks) ? session.tasks : [];
  if(!tasks.length) return "";
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
  /* Every number in the heading counts DIRECT children, so the leading clause
     agrees with the row's state line above it: `working_detail` counts that
     same population and a grandchild is deliberately not in it. Counting every
     live element made one row read "running 1 subagent" beside a
     "3 RUNNING SUBAGENTS" heading; leaving the TOTAL wide while narrowing the
     running clause then made an idle teammate holding a live worker read
     "2 SUBAGENTS · NONE RUNNING" above a row a screen reader announces as
     running. A worker beneath a teammate is a third population and gets its
     own clause rather than being folded into either count. */
  const direct = subagents.filter(subagent => !(subagent && subagent.parent));
  const running = direct.filter(nextSubagentIsLive).length;
  const beneath = subagents.filter(
    subagent => subagent && subagent.parent && nextSubagentIsLive(subagent),
  ).length;
  const rows = subagents.map((subagent, index) => {
    const elapsed = nextDurationSince(subagent && subagent.started_at);
    const measured = elapsed == null
      ? ""
      : `<span class="next-session-subagent-elapsed">${elapsed}</span>`;
    const live = nextSubagentIsLive(subagent);
    /* Nested inside the name cell rather than given a grid column of its own, so
       attribution costs one CSS rule instead of a new column every breakpoint
       has to agree about. */
    const parent = subagent && subagent.parent
      ? `<span class="next-session-subagent-parent"> · ${esc(subagent.parent)}</span>`
      : "";
    return `<div class="next-session-subagent${live ? " next-live" : ""}" ` +
      `data-next-session-subagent="${index}">` +
      `${nextStatusDot(live ? "running" : "idle", "next-session-subagent-glyph", live)}` +
      '<strong class="next-session-subagent-name">' +
      `${esc(subagent && subagent.name || "subagent")}${parent}</strong>` +
      `${measured}</div>`;
  }).join("");
  /* The heading has to survive the state this feature creates: a finished board
     still inside the display window, every element inactive. Guarding the whole
     block on `running` would hide the list, which is the vanishing act
     DRC-4344 exists to stop, so the heading tells the truth instead and the
     rows stay. */
  const label = (running === 0
    ? `${direct.length} SUBAGENT${direct.length === 1 ? "" : "S"} · NONE RUNNING`
    : running === 1 ? "1 RUNNING SUBAGENT" : `${running} RUNNING SUBAGENTS`) +
    (beneath === 0
      ? ""
      : ` · ${beneath} WORKER${beneath === 1 ? "" : "S"} RUNNING BENEATH`);
  const omitted = nextNumber(session.subagentsOmitted ?? session.subagents_omitted) || 0;
  const omittedNotice = omitted > 0
    ? `<div class="next-session-subagents-omitted">+${omitted} older finished worker${omitted === 1 ? "" : "s"} omitted</div>`
    : "";
  return '<div class="next-session-current-subagents" data-next-session-subagents>' +
    `<span>${label}</span>${rows}${omittedNotice}</div>`;
}

function nextCompactTokens(value){
  if(value < 1000) return Math.round(value).toLocaleString("en-US");
  return `${Math.round(value / 100) / 10}k`;
}

function nextSessionFooter(session){
  const sessionTotal = nextNumber(session.session_output_tokens);
  const turnTotal = nextNumber(session.turn_output_tokens);
  let source = session.state === "working" ? "turn" : "session";
  let value = source === "turn" ? turnTotal : sessionTotal;
  if(value == null){
    source = source === "turn" ? "session" : "turn";
    value = source === "turn" ? turnTotal : sessionTotal;
  }
  if(value == null) return "";
  return `<footer class="next-session-footer" data-next-session-tokens="${source}">` +
    `${nextCompactTokens(value)} output tokens this ${source}</footer>`;
}

/* The rows and the absence sentence, in one wording for every surface that
   shows them (DRC-4514).

   One caller now, the drift block's departures section: the session page's
   own UNASKED CHECKS section was absorbed into it (DRC-4639), because a raise
   printed in two sections of one page reads as two raises. The section heading
   is the caller's; everything inside it is here. */
function nextUnaskedDepartureBody(session){
  const rows = Array.isArray(session && session.departures) ? session.departures : [];
  const why = String((session && session.departure_why) == null ? "" : session.departure_why);
  if(!rows.length && !why) return "";
  /* "while you were away" was a claim about the reader, and nothing here
     observes where they were. The store has no expiry either, so a row can be
     days old under a heading that implies this trip. The heading counts, and
     each row says when. */
  const heading = rows.length === 1
    ? "One departure was raised"
    : `${rows.length} departures were raised`;
  /* Read here rather than handed in by either caller. An existing test calls
     this function directly and asserts its result is a substring of both
     surfaces, so a value that arrived per-caller could differ between them --
     which is the one thing this shared body exists to prevent. */
  const current = nextNumber(session && session.annotation_revision);
  return (rows.length ? `<p class="next-session-departures-count">${esc(heading)}</p>` : "") +
    rows.map(row => nextSessionDepartureRow(row, current, nextDepartureReentry(session)))
      .join("") +
    (why ? `<p class="next-session-departures-why">${esc(why)}</p>` : "") +
    nextDeliveryAbsence(session, rows.length > 0);
}

/* The delivery figures for the lane that raises a departure, and never the
   board's.

   The flat `delivery_*` keys carry the LATEST raise of ANY lane, and four write
   the store: gate, ask, hook and departure. Beside a departure that is the
   wrong scope in both directions -- a session with no departure at all printed
   another lane's outcome under a heading about raises, and a departure that was
   handed over printed a later hook refusal's sentence. `deliveries.published`
   is called a second time narrowed to the lane, under this one key, with the
   same key names inside, so the two scopes cannot be worded differently. */
function nextDepartureDelivery(session){
  const scoped = session && session.delivery_departure;
  return scoped && typeof scoped === "object" ? scoped : null;
}

/* The sentence for a departure no raise was ever recorded against.

   Printed only beside a departure and only when the DEPARTURE LANE holds no
   raise for this session. Walked on the board: two departures rendered with the
   notifications block simply absent, so nothing on screen distinguished a raise
   that failed from a departure the reader was never alerted to. `deliveries`
   owns the sentence, for the reason it owns the other five. */
function nextDeliveryAbsence(session, hasDeparture){
  if(!hasDeparture) return "";
  const scoped = nextDepartureDelivery(session);
  if(!scoped) return "";
  const raises = Number(scoped.delivery_raises);
  if(Number.isFinite(raises) && raises > 0) return "";
  const none = String(scoped.delivery_none_why == null ? "" : scoped.delivery_none_why);
  return none ? `<p class="next-session-delivery-why">${esc(none)}</p>` : "";
}

/* Wall-clock hours and minutes, the way `nextWorkstreamClock` does it. Its own
   copy rather than a reach across parts: these files are concatenated into one
   scope in APP_PARTS order, and this one loads before the workstream. */
function nextSessionClock(stamp){
  const date = new Date(stamp * 1000);
  return `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

/* One raised departure, with the baseline it rested on.

   The revision and the cutoff are printed rather than implied. By the time this
   is read the annotation may be at a later revision and the evidence window has
   moved, so a row that does not say which words it read and where its evidence
   stopped cannot be checked by the person it was raised to. A raise whose
   revision did not survive says so rather than borrowing today's.

   And it says, in the one wording the reading block above it uses, when the
   words it read are no longer the words on record. The revision was already
   printed and the comparison was not, so a reader had the number and no second
   source to check it against -- on the session page the baseline line is the
   only mention of a revision anywhere. */
function nextSessionDepartureRow(row, current, reentry = ""){
  const text = key => String(row[key] == null ? "" : row[key]);
  const revision = Number(row.revision);
  const read = Number.isFinite(revision) && revision > 0 ? revision : null;
  const baseline = read != null
    ? `read against revision ${read}`
    : "the revision it read is not on record";
  const superseded = nextRevisionSuperseded("This raise", read, current);
  const cutoff = Number(row.cutoff);
  const window = Number.isFinite(cutoff) && cutoff > 0
    ? ` · evidence to ${nextSessionClock(cutoff)}`
    : " · the evidence window is not on record";
  const at = Number(row.at);
  const when = Number.isFinite(at) && at > 0
    ? `<span class="next-session-departure-at">${esc(nextSessionClock(at))}</span>` : "";
  /* One row treatment for both parts of the review section (DRC-4514). The
     container, the constraint name, the clause, the model's sentence and the
     evidence line all take the cockpit reading row's declarations, which is
     where the design's third treatment is written down: two departure rows side
     by side under one heading, in four different sizes, is the second treatment
     the design forbids. The name and the stamp share a head row because the
     shared container is a flex column and a float does not survive one. */
  return '<div class="next-session-departure">' +
    '<div class="next-session-departure-head">' +
    `<span class="next-session-departure-name">${esc(text("constraint"))}</span>${when}` +
    "</div>" +
    (text("clause") ? `<span class="next-session-departure-clause">${esc(text("clause"))}` +
      "</span>" : "") +
    `<p class="next-session-departure-reading">${esc(text("reading"))}</p>` +
    `<p class="next-session-departure-base">${esc(baseline + window)}` +
    (text("cutoff_text") ? ` · ${esc(text("cutoff_text"))}` : "") +
    (text("evidence") ? ` · ${esc(text("evidence"))}` : "") + "</p>" +
    /* Its own element after the base line and never a clause appended to it.
       The base line is mono in the dimmest ink, the register for a string a
       source published; this sentence is the board talking, so it is sans and
       takes the one warm ink the design allows near a reading. Both rules are
       one declaration list shared with the reading block's own stale line. */
    (superseded
      ? `<p class="next-session-departure-stale">${esc(superseded)}</p>` : "") +
    /* What later evidence showed, chosen by `departures.follow_up` from later
       checks in the same store. Unknown is the common answer and it arrives as
       a sentence naming its reason: a blank here would be read as a raise that
       came to nothing bad, which is the one thing this axis must not say. */
    (text("follow_up")
      ? `<p class="next-session-departure-next">${esc(text("follow_up"))}</p>` : "") +
    reentry + "</div>";
}

/* The way back into the session, beside a departure (DRC-4642).

   Cargento never writes into a session
   ([DEC-16](docs/design-reading-a-session.md#dec-16-cargento-does-not-write-into-a-session)),
   so acting on drift means putting the reader back in it: the command that
   harness's CLI takes to resume it, and the tmux raise where one was measured.
   Both are the header's own controls, copied rather than re-drawn, so a cue
   written by one is swept onto the other, as the gate queue's are. The raise renders here
   whatever the session's state, which is the difference from the header,
   where it is offered only while the session waits on the reader.

   Only what exists is drawn per row. What does not is said once for the whole
   section by `nextDepartureReentryLimit`, because a limit repeated under every
   departure is furniture rather than information. */
function nextDepartureReentry(session){
  const controls = nextSessionResumeControl(session) + nextSessionRaiseControl(session);
  return controls
    ? `<div class="next-departure-reentry" data-next-departure-reentry>${controls}</div>` : "";
}

/* Why a way back is missing, or what the one offered cannot do, once per
   session page even before a departure exists (DRC-4658). The positive raise
   caveat still belongs after departure rows. Two limits, split by cause: a harness outside `NEXT_RESUME_COMMANDS` has
   no re-entry command and never will, while one inside it with no usable id
   has none THIS RUN. `nextResumeCommand` collapses both to "", so the cause is
   read here rather than off its answer. The raise's limit is the standing one
   recorded beside `nextSessionRaiseControl`, said here because one session is
   the whole subject and silence would read as "no limit". */
function nextDepartureReentryLimit(session){
  const harness = String(session && session.harness || "");
  const label = nextHarnessLabels().get(harness) || nextCockpitHumanLabel(harness);
  const line = text => text
    ? `<p class="next-departure-reentry-why" data-absence="not-observed">${esc(text)}</p>` : "";
  const resume = nextResumeCommand(session) ? ""
    : !NEXT_RESUME_COMMANDS.has(harness)
      ? `${label} publishes no re-entry command, so there is none to copy.`
      : "This session published no usable id this run, so there is no re-entry command to " +
        "copy.";
  /* The raise's own limit rides with it when it is offered: it selects the
     pane and does not bring the window forward, which is the hedge the status
     line uses after a raise is sent. Returned apart from the resume limit
     because it qualifies a control the rows carry, so the caller prints it
     after them rather than above them. */
  const raise = nextSessionRaiseControl(session)
    ? "A raise switches what the terminal displays; its window may still be behind others."
    : !nextFocusCapability() ? NEXT_FOCUS_OFF_LINE
      : "No terminal was reported for this session, so it cannot be raised. That is the " +
        "ordinary answer outside tmux, for a session older than this server run, and on Linux " +
        "and Windows.";
  return {resume: line(resume), raise: line(raise)};
}

/* What became of the notifications Cargento raised about this session.

   Every sentence here is composed by `deliveries.published` on the server and
   printed verbatim. That is deliberate: the wording is the product, and three
   surfaces wording it three ways is how the least true reading becomes the most
   reassuring one. This function chooses WHETHER to print, never WHAT.

   Nothing is drawn for a session with no raise. An absence of raises is not an
   absence of evidence about a raise, and a panel saying "no record" under a
   session nobody was ever alerted about invents a question the reader did not
   have. */
function nextSessionDelivery(session){
  const body = nextDeliveryBody(session);
  if(!body) return "";
  const text = key => String(session[key] == null ? "" : session[key]);
  return '<section class="next-session-delivery" ' +
    `data-next-delivery="${esc(text("delivery_outcome"))}"` +
    `${session.delivery_mixed === true ? ' data-next-delivery-mixed="true"' : ""}>` +
    `<h2>NOTIFICATIONS</h2>${body}</section>`;
}

/* The four published sentences and the count that scopes them, in one wording
   for every surface (DRC-4514). Shared with the departure review for
   `nextUnaskedDepartureBody`'s reason: the wording is the product, and the
   least true reading is the one that gets reworded into the most reassuring. */
function nextDeliveryBody(session){
  const raises = Number(session && session.delivery_raises);
  if(!Number.isFinite(raises) || raises < 1) return "";
  const text = key => String(session[key] == null ? "" : session[key]);
  /* The sentence describes the LATEST raise and no other, so the count and the
     sentence must not be printed as one claim. "3 notifications were raised"
     above one outcome reads as three of that outcome, which is how a session
     whose first raise was refused and whose second was handed over would render
     as two hand-overs. The server says whether the set is mixed; this says
     which raise the sentence is about. */
  const count = raises === 1
    ? "One notification was raised about this session"
    : `${raises} notifications were raised about this session. The most recent:`;
  return `<p class="next-session-delivery-count">${esc(count)}</p>` +
    (text("delivery_why")
      ? `<p class="next-session-delivery-why">${esc(text("delivery_why"))}</p>` : "") +
    (session.delivery_mixed === true && text("delivery_mixed_why")
      ? `<p class="next-session-delivery-note">${esc(text("delivery_mixed_why"))}</p>` : "") +
    (text("delivery_binding_why")
      ? `<p class="next-session-delivery-note">${esc(text("delivery_binding_why"))}</p>` : "") +
    /* `browser_lane_why` and never `browser_lane`. The flag is board-wide and
       says nothing about one session; the sentence is relative to this raise,
       which is why it is published per row and the flag at the top
       ([DEC-19](docs/design-reading-a-session.md#dec-19-the-page-may-report-a-lane-never-a-delivery)). */
    (text("browser_lane_why")
      ? `<p class="next-session-delivery-lane">${esc(text("browser_lane_why"))}</p>` : "") + "";
}

function nextSessionDetailState(state){
  if(state === "needs_input") return {label: "needs input", token: "needs_input"};
  if(state === "working") return {label: "working", token: "working"};
  if(state === "idle") return {label: "idle", token: "idle"};
  return null;
}

function nextCommandReports(session = null){
  const disabled = !nextData || nextData.irreversible_enabled !== true;
  const unsupported = session && !["claude", "codex"].includes(session.harness);
  const reports = disabled || unsupported ? [] : nextObservedRecords(
    session ? session.command_reports : nextData.command_reports).slice(0, 20);
  const absent = disabled ? "Command-shape reports are disabled for this run." : unsupported ?
    "Command-shape reporting is unsupported for this harness." :
    "No matching reports received; missing hooks and unmatched commands can look the same.";
  const rows = reports.map(report => {
    const owner = !session && nextObservedRecords(nextData.sessions).find(source =>
      source.harness === report.harness && source.sid === report.sid);
    const route = owner ? nextRouteToken({view: "session", project: owner.project,
      harness: owner.harness, session: owner.sid}) : "";
    const identity = session ? "" : `${report.harness} · ${report.sid} · `;
    const text = `Command shape reported: ${report.label}`;
    return `<li class="next-attention-risk-identity"><h3>${route ? `<a href="#n=${esc(route)}" data-next-route="${esc(route)}">${esc(text)}</a>` : esc(text)}</h3>` +
      `<p class="next-attention-risk-source">${esc(identity)}${esc(report.tool_name)} · ${esc(new Date(report.timestamp * 1000).toISOString())}</p></li>`;
  }).join("");
  return '<section class="next-attention-section" data-next-command-reports>' +
    '<div class="next-attention-section-heading"><h2>Command-shape reports</h2>' +
    (reports.length ? `<p>${reports.length} report${reports.length === 1 ? "" : "s"} shown · newest first</p>` : "") +
    '</div>' + (reports.length ? `<ol>${rows}</ol>` : `<p>${esc(absent)}</p>`) +
    '<p>A shape match does not prove the action succeeded.</p>' +
    '<p>Claude Code and Codex after-tool hooks only. Reports may repeat or arrive out of order. ' +
    'This run keeps up to 1,000 reports, 20 per session, for at most 24 hours; restarting clears them.</p></section>';
}

function nextSessionView(project, harness, sid, openDisclosures = new Set()){
  const session = nextSessionFind(project, harness, sid);
  /* A pasted link lands here before the first payload does, and "not in the
     payload" would then be a claim about a payload nobody has read. */
  if(!nextData){
    return '<section class="next-session-detail-empty" data-next-session-state="unread">' +
      '<p class="next-absence">The first payload has not arrived yet.</p></section>';
  }
  if(!session){
    /* Named, because a pasted link is the usual way here and the reader needs
       to know which session the board no longer holds. The window is stated
       as a fact about the board, never as the cause: a session from another
       machine is absent for a different reason. */
    const who = [harness, sid].map(part => String(part == null ? "" : part)).filter(Boolean)
      .join(" · ");
    const hours = nextNumber(nextData.window_hours);
    const window = hours != null && hours > 0
      ? `<p>The board holds sessions observed in the last ${hours} ` +
        `${hours === 1 ? "hour" : "hours"}.</p>` : "";
    return '<section class="next-session-detail-empty" ' +
      'data-next-session-state="outside-payload">' +
      '<p class="next-absence">This session is not in the current payload.</p>' +
      (who ? `<p class="next-session-identity">${esc(who)}</p>` : "") + window +
      '<a href="#n=sessions" data-next-route="sessions">View all sessions</a></section>';
  }
  nextPruneSessionAnswerNotes();
  const observed = nextCurrentObserved().sessions.find(row =>
    nextSessionKey(row) === nextSessionKey(session) && row.project === String(session.project == null ? "" : session.project));
  const asks = nextSessionAsks(session);
  const blocked = observed.isNeeds ? " next-session-detail--blocked" : "";
  const state = nextSessionDetailState(session.state);
  const stateAttr = state ? ` data-next-session-state="${state.token}"` : "";
  /* Visible, in the words the Sessions rows use, rather than the design's
     "Running": renaming a state on one page would rename it for the product. */
  const stateLabel = state ? '<span class="next-session-state">' +
    `<span class="next-visually-hidden">State: </span>${state.label}</span>` : "";
  const meta = nextSessionMeta(session);
  const metaLine = meta ? `<p class="next-session-detail-meta">${esc(meta)}</p>` : "";
  const titleClass = observed.titleKnown ? "" : ' class="next-session-absent"';
  const rate = observed.rateKnown ? ` · ${esc(observed.rateText)}` : "";
  /* At most one primary, and none while a question is open without a raise
     ([DEC-20](docs/design-reading-a-session.md#dec-20-the-first-screen-shows-goal-beside-direction-and-drift-has-one-home)).
     No answer option is ever emphasised: a filled first option reads as advice
     to approve, so every option stays a plain control. A session waiting on
     the reader gives the primary to the raise when one is offered; without
     one nothing is primary, and "Analyze drift" renders as an ordinary
     control. */
  const waiting = observed.isNeeds || observed.askKnown;
  const raise = observed.isNeeds ? nextSessionRaiseControl(session, true) : "";
  const reentryLimit = nextDepartureReentryLimit(session);
  const missingReentry = reentryLimit.resume + (nextSessionRaiseControl(session) ? "" : reentryLimit.raise);
  const controls = nextSessionCopyControl(session) + nextSessionLinkControl(session) +
    nextSessionResumeControl(session) + raise;
  /* Two rows at most, as C1's one-row header comes out in Cargento's type:
     the state, name and id, then the measured line with the controls beside
     it. Stacked one per line it took 205px at 1440x900 and put Analyze drift
     under the fold (DRC-4680 walk). */
  const identity = '<header class="next-session-detail-header">' +
    `<div class="next-session-detail-title">${stateLabel}` +
    `<h1${titleClass}>${esc(observed.titleText)}</h1>` +
    `<p class="next-session-identity">${esc(observed.harness)} · ${esc(observed.sid)}${rate}</p>` +
    '</div><div class="next-session-detail-bar">' +
    `${metaLine}<div class="next-session-controls">${controls}</div></div></header>`;
  const assignment = nextSessionInstruction(session, "asked")
    ? nextSessionCommandFact("assignment", "ASSIGNMENT",
      nextInstructionLine(session, "", "next-session-command-context")) : "";
  const coverage = nextSessionSourceCoverage(nextSessionSourceOwner(session),
    observed.nextKnown, asks, openDisclosures);
  /* The group the session belongs to, under its own label. A session with no
     project groups under "", so once this page is routed it renders the same
     block as any other. Whether such a session can reach this page at all is
     a routing question this does not settle. */
  const label = String(session.project == null ? "" : session.project);
  const group = nextProjectGroups().find(candidate => candidate.label === label) ||
    {label, sessions: [session]};
  const drift = nextCockpitDriftBlock(group, session, !waiting);
  /* Identity, then what is waiting on the reader, both full width; then the
     Intent and drift panel and the session's activity as two columns
     (DRC-4680). The answer sits above both because it outranks the check.
     The panel comes first in the markup, so it is the first thing after the
     page's name in reading and keyboard order and leads the single column on
     a narrow screen; the stylesheet puts it on the right when both fit. The
     page scrolls as one document: the panel is not its own scroll container
     and is not sticky. */
  const activity = '<div class="next-session-activity" data-next-session-activity>' +
    '<h2 class="next-session-activity-heading">Session activity</h2>' +
    nextSessionCommandSurface(session, observed) +
    /* Worker history has no height bound: 31 old workers put the check at
       2019px on a 900px screen when they shared CURRENT ACTIVITY's card. */
    nextSessionSubagents(observed) +
    nextSessionFacts(observed, asks) +
    `<div class="next-session-evidence">${assignment}${coverage}</div>` +
    nextSessionHealth(session) + nextSessionTasks(observed) +
    nextCommandReports(session) + nextSessionDelivery(session) + missingReentry + drift.record +
    "</div>";
  return `<article class="next-session-detail${blocked}" data-next-session-detail="${esc(session.sid)}"` +
    `${stateAttr} data-tone="${esc(observed.tone)}">` + identity +
    nextSessionAskBlock(session, asks, observed) +
    `<div class="next-session-columns">${drift.panel}${activity}</div>` +
    nextSessionFooter(session) + "</article>";
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
