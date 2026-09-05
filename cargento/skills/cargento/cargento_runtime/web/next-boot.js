const nextQuery = new URLSearchParams(location.search);
const NEXT_DUPLICATE_LABEL_LIMIT = "Same label is not proof of the same directory: the label is the" +
  " last two segments of each session's path, so sibling worktrees read alike.";
const NEXT_TOP_LEVEL_VIEWS = new Set(["attention", "projects", "sessions"]);

const qs = name => nextQuery.get(name);
const esc = value => String(value == null ? "" : value).replace(/[&<>"']/g,
  char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));

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
    if(project) return {view: "project", project, session: null};
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
  return {view: "sessions", project: null, session: null};
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
    return `#n=project:${encodeURIComponent(route.project)}`;
  }
  if(route && NEXT_TOP_LEVEL_VIEWS.has(route.view)) return `#n=${route.view}`;
  return "#n=sessions";
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

function nextSessionCopyControl(session){
  const sid = String(session && session.sid || "").trim();
  if(!sid) return "";
  return `<button type="button" class="next-session-copy" data-next-copy-session="${esc(sid)}" ` +
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
const NEXT_RESUME_TOKEN = /^[A-Za-z0-9_-]{1,64}$/;

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
  return `<button type="button" class="next-session-copy next-attention-resume" ` +
    `data-next-copy-command="${esc(command)}" ` +
    `aria-label="Copy re-entry command ${esc(command)}" title="${esc(command)}">` +
    '<span aria-hidden="true">COPY COMMAND</span></button>';
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
