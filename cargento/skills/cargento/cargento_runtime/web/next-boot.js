const nextQuery = new URLSearchParams(location.search);
const NEXT_DUPLICATE_LABEL_LIMIT = "Same label is not proof of the same directory: the label is the" +
  " last two segments of each session's path, so sibling worktrees read alike.";
/* The load-bearing half of what a reading is not, owned here because two
   surfaces state it and a second wording would be a second promise. The
   reading block says it about the reading it is offering; the Intent log says
   it about every row it lists. */
const NEXT_READING_NOT_A_VERIFICATION =
  "A reading is never a verification that the work was done.";
const NEXT_TOP_LEVEL_VIEWS = new Set(["attention", "projects", "sessions", "intent"]);
const NEXT_PROJECT_TABS = ["now", "course", "decisions", "console"];
/* Tabs that exist only while one session is in focus. Empty at project scope
   rather than disabled there, because a tab about one session's words has
   nothing to show when no session is selected, and an always-empty tab
   teaches a reader not to click the one that will matter.

   Not gated on the annotation store being live. This list is read by
   `nextRouteFromFragment` at boot, before any payload has arrived, and a
   capability-gated list would refuse to parse a bookmarked `:held-to` link on
   first load and drop the reader on the projects index. The panel says the
   store is off; the route stays readable either way. */
const NEXT_SESSION_TABS = ["held-to"];
const NEXT_OBSERVER_CONSENT_KEY = "cargento.observer-model-consent.v1";
let nextObserverConsentMemo = null;
const nextObserverRequests = new Set();
const nextObserverRequestStates = new Map();

const qs = name => nextQuery.get(name);
const esc = value => String(value == null ? "" : value).replace(/[&<>"']/g,
  char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));

/* Which cockpit tabs exist, given the session a project view is narrowed to.
   `focus` is `nextRoute.focus`, and falsy is project scope.

   One reader in place of the thirteen sites that read the list directly, and
   it takes the scope now while both scopes still answer the same, so this
   change moves nothing a reader sees. Six of those thirteen were the keyboard
   wrap alone, which computes an index and a length against the list: a wrap
   over a list the nav did not render moves focus to a tab that is not on the
   reader's screen, and it does it silently. */
function nextCockpitTabs(focus){
  return focus ? [...NEXT_PROJECT_TABS, ...NEXT_SESSION_TABS] : NEXT_PROJECT_TABS;
}

function nextDecodeRoutePart(value){
  try{
    return decodeURIComponent(value);
  }catch(_error){
    return "";
  }
}

function nextRouteFromFragment(fragment){
  const token = String(fragment || "").startsWith("#n=")
    ? String(fragment).slice(3)
    : "";
  if(NEXT_TOP_LEVEL_VIEWS.has(token)){
    return {view: token, project: null, session: null};
  }
  const parts = token.split(":");
  if(parts.length === 2 && parts[0] === "project"){
    const project = nextDecodeRoutePart(parts[1]);
    if(project) return {view:"project",project,session:null};
  }
  if(parts.length === 3 && parts[0] === "project"){
    const project = nextDecodeRoutePart(parts[1]);
    const value = nextDecodeRoutePart(parts[2]);
    if(project && nextCockpitTabs(null).includes(value)){
      return {view:"project",project,session:null,tab:value};
    }
    if(project && value) return {view:"project",project,session:null,focus:value};
  }
  if(parts.length === 4 && parts[0] === "project"){
    const project = nextDecodeRoutePart(parts[1]);
    const focus = nextDecodeRoutePart(parts[2]);
    const tab = nextDecodeRoutePart(parts[3]);
    if(project && focus && nextCockpitTabs(focus).includes(tab)){
      return {view:"project",project,session:null,focus,tab};
    }
  }
  if(parts.length === 4 && parts[0] === "session"){
    const project = nextDecodeRoutePart(parts[1]);
    const harness = nextDecodeRoutePart(parts[2]);
    const session = nextDecodeRoutePart(parts[3]);
    if(project && harness && session) return {view: "session", project, harness, session};
  }
  if(parts.length === 3 && parts[0] === "session"){
    const project = nextDecodeRoutePart(parts[1]);
    const session = nextDecodeRoutePart(parts[2]);
    if(project && session) return {view: "session", project, session};
  }
  return {view: "projects", project: null, session: null};
}

function nextFragmentForRoute(route){
  if(route && route.view === "session" && route.project && route.session){
    const harness = String(route.harness || "");
    const prefix = `#n=session:${encodeURIComponent(route.project)}:`;
    return harness
      ? `${prefix}${encodeURIComponent(harness)}:${encodeURIComponent(route.session)}`
      : `${prefix}${encodeURIComponent(route.session)}`;
  }
  if(route && route.view === "project" && route.project){
    const focus = route.focus ? `:${encodeURIComponent(route.focus)}` : "";
    const tab = nextCockpitTabs(route.focus).includes(route.tab) && route.tab !== "now"
      ? `:${encodeURIComponent(route.tab)}` : "";
    return `#n=project:${encodeURIComponent(route.project)}${focus}${tab}`;
  }
  if(route && NEXT_TOP_LEVEL_VIEWS.has(route.view)) return `#n=${route.view}`;
  return "#n=projects";
}

function nextNumber(value){
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function nextFiniteNumber(value){
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

function nextPayloadSessions(payload){
  if(!payload || typeof payload !== "object" || Array.isArray(payload)) return [];
  if(!Array.isArray(payload.sessions)) return [];
  return payload.sessions.filter(session =>
    session && typeof session === "object" && !Array.isArray(session));
}

function nextPayloadAsks(payload){
  if(!payload || typeof payload !== "object" || Array.isArray(payload)) return [];
  if(!Array.isArray(payload.asks)) return [];
  return payload.asks.filter(ask => ask && typeof ask === "object" && !Array.isArray(ask));
}

/* When a session id was observed to end, or null. Null is the whole of what the
   page may say: absence covers a SIGKILL, a harness with no event adapter, a
   session that predates this server run, and --no-events, so a row without a
   stamp is NOT known to be running and must never be rendered as though it
   were. Every end-aware surface goes through here so that rule lives once. */
function nextSessionEndedAt(session){
  const at = nextNumber(session && session.ended_at);
  return at != null && at > 0 ? at : null;
}

function nextSessionKey(session){
  return `session:${JSON.stringify([String(session && session.harness || ""), String(session && session.sid || "")])}`;
}

function nextExactAskOwner(payload, ask){
  const sid = String(ask && ask.session_id || "");
  if(!sid) return null;
  const harness = String(ask && ask.harness || "");
  const matches = nextPayloadSessions(payload).filter(session =>
    String(session.sid || "") === sid &&
    (!harness || String(session.harness || "") === harness));
  return matches.length === 1 ? matches[0] : null;
}

// What a row control last said, held outside the DOM. `renderNext` replaces
// `#app` wholesale on every revision and on a bare interval — 20 s with an
// EventSource, 5 s without — so a cue written onto the element died of a clock
// rather than of anything the reader did, and asymmetrically: the live region is
// a sibling of `#app` and survived, so the screen-reader cue outlived the
// coloured one (DRC-4392). The render functions below re-emit from here.
//
// One map for all three controls, because they are one lane in every other
// respect and three maps would be three places for the same expiry rule to
// drift. The lane is part of the key: copying a session id is not proof the
// re-entry command was copied.
//
// Stamped, because never expiring is the worse lie of the two. A row would read
// SENT for the rest of the run, including after `ended_at` marks the session
// over. 30 s is longer than the 20 s idle render (next-live.js's
// NEXT_FALLBACK_POLL_MS), so the cue's life is not decided by when the next
// render happens to land, and short enough that nobody reads it as a property of
// the session.
const NEXT_CONTROL_STATE_TTL_MS = 30_000;
// Bounded like every other module-level map here. A board carries hundreds of
// rows and a tab stays open for hours, so the clock drops what is stale and the
// cap drops what is oldest rather than letting the map grow with the session.
const NEXT_CONTROL_STATE_LIMIT = 32;
const nextControlStates = new Map();

function nextControlStateKey(lane, harness, sid){
  return `${lane}\u0000${String(harness == null ? "" : harness)}` +
    `\u0000${String(sid == null ? "" : sid)}`;
}

function nextRememberControlState(key, state){
  // Deleted before set so the Map's insertion order stays recency order, which
  // is what makes the first key the right one to evict.
  nextControlStates.delete(key);
  nextControlStates.set(key, {state, at: Date.now()});
  while(nextControlStates.size > NEXT_CONTROL_STATE_LIMIT){
    nextControlStates.delete(nextControlStates.keys().next().value);
  }
}

function nextControlState(key){
  const held = nextControlStates.get(key);
  if(!held) return "";
  if(Date.now() - held.at >= NEXT_CONTROL_STATE_TTL_MS){
    nextControlStates.delete(key);
    return "";
  }
  return held.state;
}

function nextControlStateAttr(attribute, lane, harness, sid){
  const state = nextControlState(nextControlStateKey(lane, harness, sid));
  return state ? ` ${attribute}="${esc(state)}"` : "";
}

function nextSessionCopyControl(session){
  const sid = String(session && session.sid || "").trim();
  if(!sid) return "";
  // The harness rides the control because the cue is keyed on both, as every
  // other session-keyed structure here is (`nextSessionKey`): a sid is unique
  // within a harness and nowhere else.
  const harness = String(session && session.harness || "");
  return `<button type="button" class="next-session-copy" data-next-copy-session="${esc(sid)}" ` +
    `data-next-copy-harness="${esc(harness)}"` +
    `${nextControlStateAttr("data-next-copy-state", "copy", harness, sid)} ` +
    `aria-label="Copy session ID ${esc(sid)}" title="${esc(sid)}">` +
    '<span aria-hidden="true">COPY ID</span></button>';
}

// The verb each harness's own CLI takes to re-enter a session, keyed by harness.
//
// Both were read off `--help` on the installed CLI rather than off documentation:
// Claude Code 2.1.261 takes `--resume <session-id>` and Codex 0.153.4 takes
// `resume <SESSION_ID>`. A harness absent from this table gets no control at all,
// because a guessed verb costs the reader a failed command on top of the hunt it
// was meant to replace.
//
// On re-entering a session that is still live, which is the question a reader will
// ask before they trust this: neither harness lets a second process onto the same
// conversation, and both say so rather than doing it quietly. Measured, not
// inferred. Claude Code refuses — `Can't open — this session is running in another
// terminal` interactively, and in the background variant it starts a copy and
// reports `The original conversation is unchanged`. Codex refuses too, with
// `thread-store conflict: thread <id> already has an active writer`, observed by
// running two `codex exec resume` calls against one id. So there is no footgun to
// warn about, and the control carries no warning: the worst case is a refusal that
// names what to do next.
const NEXT_RESUME_COMMANDS = new Map([
  ["claude", id => `claude --resume ${id}`],
  ["codex", id => `codex resume ${id}`],
]);

// The published token is checked again here, having already been checked by the
// collector that published it. Not belt and braces for its own sake: the page
// treats the payload as untrusted the way the server treats a hook's output, and
// this is the one string on the board that becomes a shell command in someone
// else's terminal.
//
// Same grammar as the server's RESUME_TOKEN_PATTERN, first character included:
// a `-`-leading token is one word to a shell but a flag to the CLI, and both
// harnesses have a valueless flag that turns off their permission checks. Keep
// the two in step; a page-only anchor would leave every other reader of
// /api/data holding the raw value.
const NEXT_RESUME_TOKEN = /^[A-Za-z0-9_][A-Za-z0-9_-]{0,63}$/;

function nextResumeCommand(session){
  const build = NEXT_RESUME_COMMANDS.get(String(session && session.harness || ""));
  const token = String(session && session.resume_id || "");
  return build && NEXT_RESUME_TOKEN.test(token) ? build(token) : "";
}

function nextSessionResumeControl(session){
  const command = nextResumeCommand(session);
  if(!command) return "";
  // `title` carries the command as well as the clipboard does, which is the
  // fallback: a context with no `navigator.clipboard` still shows the reader what
  // to type. Same lane as the session-id control beside it, deliberately.
  const sid = String(session && session.sid || "");
  const harness = String(session && session.harness || "");
  return `<button type="button" class="next-session-copy next-attention-resume" ` +
    `data-next-copy-command="${esc(command)}" data-next-copy-session="${esc(sid)}" ` +
    `data-next-copy-harness="${esc(harness)}"` +
    `${nextControlStateAttr("data-next-copy-state", "command", harness, sid)} ` +
    `aria-label="Copy re-entry command ${esc(command)}" title="${esc(command)}">` +
    '<span aria-hidden="true">COPY COMMAND</span></button>';
}

// The capability this run minted for the focus route, injected into the served
// document at `cli.inject_focus_capability` rather than baked into an asset,
// which is what keeps this file's bytes deterministic. Read from the document
// because that is the only place it arrives: SECURITY.md keeps it out of
// `/api/data`, so a page reading it from the payload is reading something the
// server does not send. Absent means the feature is off for the run — `--no-focus`,
// or `--no-events` taking the coordinator that mints it — and an absent capability
// renders no control rather than one whose request could only be refused.
const NEXT_FOCUS_META = 'meta[name="cargento-focus"]';

// One fact about the process, stated at two scopes: the fleet coverage line on
// Attention and the per-session limit in the Held to tab. Hoisted rather than
// spelled twice, because two spellings of one fact drift.
const NEXT_FOCUS_OFF_LINE = "Terminal raise: off for this run.";

function nextFocusCapability(){
  if(typeof document === "undefined" || typeof document.querySelector !== "function") return "";
  let meta = null;
  try{
    meta = document.querySelector(NEXT_FOCUS_META);
  }catch(_error){
    return "";
  }
  const value = meta && typeof meta.getAttribute === "function"
    ? meta.getAttribute("content")
    : null;
  return typeof value === "string" ? value.trim() : "";
}

// Beside the copy control and never in place of it. The copy always works. This
// one's target is resolved at the moment of the raise and never at render, so at
// render the page cannot know whether it will work, and drawing it optimistically
// over the copy would leave a reader whose raise is declined with less than the
// affordance that always works.
//
// `focusable` is a bit and never a target, so there is nothing for a `title` to
// carry: the copy control's title holds its own payload as the no-clipboard
// fallback, and the focus contract forbids echoing a target. The accessible name
// is the `aria-label`, and it names the act rather than the terminal.
//
// A row with no reported terminal renders nothing at all. False is the majority
// answer and will stay so — a session outside tmux, one that predates this server
// run, and every Linux and Windows session, where the contract's own device
// grammar refuses `/dev/pts/N` — so the coverage line says how far the feature
// reaches once, where a per-row note would print forever and say nothing.
//
// That holds for a QUEUE of rows and is why Attention states it once. It does not
// hold where one session is the whole subject: the Held to tab is about the
// session on screen, a reader there is asking whether they can get back into that
// one, and "nothing at all" is the answer that reads as "no limit" rather than as
// "not this session". `nextCockpitHeldReEntry` states it for that scope, which is
// a second place and not a per-row note.
function nextSessionRaiseControl(session){
  if(!session || session.focusable !== true) return "";
  const sid = String(session.sid == null ? "" : session.sid).trim();
  const harness = String(session.harness == null ? "" : session.harness).trim();
  if(!sid || !harness || !nextFocusCapability()) return "";
  // Every RAISE on the page, not the one that was clicked. The refusal is the
  // daemon's — one `_focus_inflight` and one `_focus_last_at` for the whole
  // process — and the page's own gate is one module-level flag, so painting the
  // clicked row alone attributes a page-wide condition to whichever row was
  // clicked while every other RAISE is equally unavailable and says nothing
  // (DRC-4390). `aria-disabled` rather than `disabled`: the control keeps its
  // place in the tab order, and the click still reaches the handler that says why.
  const busy = nextRaiseInFlight ? ' aria-disabled="true"' : "";
  return '<button type="button" class="next-session-raise next-attention-raise" ' +
    `data-next-raise-session="${esc(sid)}" data-next-raise-harness="${esc(harness)}"` +
    `${nextControlStateAttr("data-next-raise-state", "raise", harness, sid)}${busy} ` +
    'aria-label="Raise the terminal this session is running in">' +
    '<span aria-hidden="true">RAISE</span></button>';
}

function nextAskResponsibility(payload, ask){
  const owner = nextExactAskOwner(payload, ask);
  const spacedock = owner && owner.spacedock;
  return spacedock && typeof spacedock === "object" && !Array.isArray(spacedock)
    ? "CAPTAIN"
    : "NEEDS YOU";
}

function nextPublishedTask(session){
  const tasks = session && Array.isArray(session.tasks) ? session.tasks : [];
  const valid = tasks.filter(task => task && typeof task === "object" && !Array.isArray(task));
  return valid.find(task => task.status === "in_progress") ||
    valid.find(task => task.status === "pending") || null;
}

function nextPayloadAgeSeconds(payload, stamp){
  const generated = nextNumber(payload && payload.generated);
  const at = nextNumber(stamp);
  if(generated == null || at == null || at <= 0) return null;
  return Math.max(0, generated - at);
}

function nextAgeSeconds(stamp){
  const generated = nextNumber(nextData && nextData.generated);
  const at = nextNumber(stamp);
  if(generated == null || at == null || at <= 0) return null;
  return Math.max(0, generated - at);
}

function nextFormatDuration(seconds){
  if(typeof seconds !== "number" || !Number.isFinite(seconds) || seconds < 0) return null;
  const whole = Math.floor(seconds);
  if(whole < 60) return `${whole}s`;
  if(whole < 3600) return `${Math.floor(whole / 60)}m`;
  if(whole < 86400){
    return `${Math.floor(whole / 3600)}h ${Math.floor((whole % 3600) / 60)}m`;
  }
  return `${Math.floor(whole / 86400)}d ${Math.floor((whole % 86400) / 3600)}h`;
}

function nextDurationSince(stamp){
  const age = nextAgeSeconds(stamp);
  return age == null ? null : nextFormatDuration(age);
}

// The second line beneath a session title: what the session is working on now,
// where the title above it cannot say. Never rendered without its label and the
// age of the record it came from — "agent, 4m:" is an agent quoting itself and
// "earlier, 2h:" is not the newest thing asked, and a reader who cannot see
// which has been handed a claim the runtime cannot support.
//
// Returns "" rather than a blank line when there is nothing honest to say, and
// when the line would only repeat the title: `calm.js` already renders the
// title and the prompt as separate elements and would show the same string
// twice on a session whose first prompt is still its newest.
const NEXT_INSTRUCTION_LABELS = new Map([
  ["asked", "asked"],
  ["agent", "agent"],
  ["earlier", "earlier"],
]);

function nextInstructionEchoes(text, title){
  const norm = value => String(value == null ? "" : value).trim().toLowerCase();
  const line = norm(text);
  const head = norm(title);
  if(!line || !head) return false;
  if(line === head) return true;
  // The one case beyond equality: line 1 clips at 80 characters and line 2 at
  // 140, so one prompt reaches them as two strings and the shorter ends in an
  // ellipsis. Deliberately not a plain prefix test — a short generated title
  // that happens to open a longer, genuinely newer instruction is not a
  // duplicate, and suppressing it would lose the line this whole feature adds.
  return head.endsWith("…") && line.startsWith(head.slice(0, -1));
}

function nextInstructionLine(session, title, className, tag){
  const instruction = session && session.instruction;
  if(!instruction || typeof instruction !== "object" || Array.isArray(instruction)) return "";
  const label = NEXT_INSTRUCTION_LABELS.get(String(instruction.label || ""));
  const text = String(instruction.text == null ? "" : instruction.text).trim();
  if(!label || !text || nextInstructionEchoes(text, title)) return "";
  const age = nextDurationSince(instruction.at);
  // The age sits OUTSIDE the label span. `.next-instruction-label` uppercases,
  // and the age inside it rendered "ASKED, 4M:" — a duration whose unit is a
  // capital letter reads as an initialism, and the whole prefix reads as one
  // label rather than as a label and the age of the record it came from.
  const stamp = age == null ? ":" : `, ${age}:`;
  // A `<p>` is flow content, and the GOING ON card is a `<button>`, which takes
  // phrasing content only. One renderer for the policy, two element names.
  const el = tag === "span" ? "span" : "p";
  return `<${el} class="${esc(className)}" data-next-instruction="${esc(instruction.label)}">` +
    `<span class="next-instruction-label">${esc(label)}</span>${esc(stamp)} ` +
    `<span class="next-instruction-text">${esc(text)}</span></${el}>`;
}

function nextHarnessLabels(){
  const labels = new Map();
  const harnesses = nextData && Array.isArray(nextData.harnesses) ? nextData.harnesses : [];
  for(const harness of harnesses){
    const key = String(harness && harness.key || "");
    if(key) labels.set(key, String(harness.label || key));
  }
  return labels;
}

function nextSessionWorkingOrder(rows){
  const bySid = (left, right) => {
    const leftSid = String(left.sid || "");
    const rightSid = String(right.sid || "");
    return leftSid < rightSid ? -1 : (leftSid > rightSid ? 1 : 0);
  };
  return [...rows].sort((left, right) => {
    const leftRank = left.turn && left.turn.long ? 1 : 2;
    const rightRank = right.turn && right.turn.long ? 1 : 2;
    if(leftRank !== rightRank) return leftRank - rightRank;
    return bySid(left, right);
  });
}

function nextSessionMetric(session){
  if(session.state === "needs_input"){
    const wait = nextDurationSince(session.blocked_since);
    return wait == null ? "" : `${wait} wait`;
  }
  if(session.state === "working"){
    const rate = nextNumber(session.rate_per_min);
    return rate == null ? "" : `${Math.round(rate).toLocaleString("en-US")} /m`;
  }
  const idle = nextDurationSince(session.last_activity);
  return idle == null ? "" : `${idle} idle`;
}

function nextStatusDot(label, className, filled = true){
  const suffix = className ? ` ${esc(className)}` : "";
  return `<span class="next-status-dot${suffix}" aria-label="${esc(label)}">` +
    `${filled ? "●" : "○"}</span>`;
}

/* Only `active === false` withholds the live pulse and the running count. None
   means the collector does not measure per-entry liveness, so a harness nobody
   has taught to measure it renders exactly as it did before. This also retires a
   defect DRC-4229 left standing: a registered member that has demonstrably not
   started was already published in `subagents[]` and pulsed like a running one. */
function nextSubagentIsLive(subagent){
  return !subagent || subagent.active !== false;
}

function nextProjectGroups(){
  const groups = new Map();
  for(const session of nextRows()){
    const label = String(session.project == null ? "" : session.project);
    if(!groups.has(label)) groups.set(label, []);
    groups.get(label).push(session);
  }
  return [...groups].map(([label, sessions]) => ({label, sessions}));
}

function nextWithheld(primary, secondary){
  const detail = secondary ? `<small>${esc(secondary)}</small>` : "";
  return `<span>${esc(primary)}</span>${detail}`;
}

function nextWithheldLine(primary, secondary){
  return `${esc(primary)} · ${esc(secondary)}`;
}

let nextRoute = nextRouteFromFragment(location.hash);
const nextInitialFragment = nextFragmentForRoute(nextRoute);
if(location.hash !== nextInitialFragment) location.hash = nextInitialFragment;
