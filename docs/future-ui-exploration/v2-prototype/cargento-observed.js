// Observed state for the project-level board.
//
// House rule, taken from the shipped runtime: never assert what no source
// published. Every field that can be absent carries an explicit reason, and
// absence renders neutral — it is not a state that earns colour.
//
// Milestone provenance for anything shown here:
//   shipped  — P3 attention queue, P4 quota windows, E2/E3/E4 end outcomes,
//              C2 stuck signal, F1 project grouping, state-change timeline
//   open     — C4 stated goals, C6 irreversible actions, C1 tripwires,
//              F3 attention accounting, E5 unpushed, E7 hand-off

export const NOW = "2026-09-08T14:22:00Z";

const P = (o) => o;

export const PROJECTS = [
  P({
    key: "recce/cargento",
    scope: "~/src/cargento",
    label: { shared: 10, note: "10 sessions share this display label; shared location is not established" },
    goal: { text: "Now using the running Cargento (at http://localhost:4553/#n=projects), navigate the UI and capture every screen with live sessions.", src: "Claude · latest assignment", exact: true },
    goalGap: "3 of 10 sessions publish no goal. Codex and Antigravity transcripts carry no assignment field.",
    sessions: [
      { id: "43ea29fa", h: "Claude", title: "Cargento UI screenshots with running sessions",
        st: "working", now: "running mcp__claude-in-chrome__browser_batch", next: null,
        turn: { into: "4m", ends: null, endsWhy: "Claude publishes no turn estimate" },
        rate: "250 /m", block: { state: "none", note: "reporter available" }, subs: [] },
      { id: "9c1b0e77", h: "Codex", title: "Read AGENTS.md, docs/design-runtime-architecture.md, and…",
        st: "working", now: "running exec", next: null,
        turn: { into: "3m", ends: null, endsWhy: "Codex transcript did not publish a next action" },
        rate: "231 /m", block: { state: "none", note: "reporter available" }, subs: [] },
      { id: "77aa41c2", h: "Claude", title: "Reconcile promise map with the shipped skill body",
        st: "needs", now: "waiting on you", next: "apply the four-site edit", waited: "11m",
        turn: { into: "—", ends: null, endsWhy: null },
        ask: "Two sites disagree about what backs P5. Take the runtime wording or the doc wording?",
        resume: "claude --resume 77aa41c2", rate: "0 /m", block: { state: "you", note: "asked you 11m ago" }, subs: [] },
      { id: "b04e5d19", h: "Antigravity", title: null, titleWhy: "Title not published",
        st: "working", now: "generating…", next: null,
        turn: { into: "1m", ends: null, endsWhy: "Harness does not report turn bounds" },
        rate: "1,103 /m", block: { state: "unknown", note: "harness does not report blocks" }, subs: [] },
      { id: "2f7d3c04", h: "Codex", title: "Bound the git probe's concurrency",
        st: "ended", now: "ended 9m ago", outcome: "unread", outcomeNote: "finished 9m ago and was never read",
        git: { state: "unmeasured", note: "git state was not measured" }, rate: null, subs: [] },
      { id: "8e2b6a90", h: "Claude", title: "Widen source_gaps to the silent swallow sites",
        st: "ended", now: "ended 41m ago", outcome: "dirty", outcomeNote: "ended leaving 3 files uncommitted",
        git: { state: "dirty", note: "3 porcelain entries under current tracking rules" }, rate: null, subs: [] },
    ],
    delegation: { pct: 99, tps: "≥924", human: 87, window: "last 4d 21h", floor: true,
      note: "≥ because two sessions have no closed working interval in the retained window." },
    changes: [
      ["10:56", "became idle", "Claude", true],
      ["11:24", "agent resumed", "Claude", false],
      ["12:53", "became idle", "Antigravity", true],
      ["13:01", "became idle", "Codex", true],
      ["13:44", "needs input", "Claude", false],
      ["14:11", "agent resumed", "Codex", true],
    ],
    changeNote: "94 of 187 unattended · last 5d 18h",
    tripwires: [],
  }),
  P({
    key: "recce/recce-cloud-infra",
    scope: "~/src/recce-cloud-infra",
    label: { shared: 3, note: "3 sessions share this display label" },
    goal: { text: "Survey this repository's infrastructure layout. Summarize the module boundaries before changing anything.", src: "Codex · latest assignment", exact: true },
    goalGap: "2 of 3 sessions publish no goal.",
    sessions: [
      { id: "51c0d8b3", h: "Codex", title: "Survey this repository's infrastructure layout. Su…",
        st: "working", now: "running exec", next: null,
        turn: { into: "6m", ends: null, endsWhy: "Codex transcript did not publish a next action" },
        rate: "187 /m", block: { state: "none", note: "reporter available" }, subs: [] },
      { id: "a19f4e26", h: "Codex", title: "Pin the one-shot probe cadence",
        st: "ended", now: "ended 2h ago", outcome: "died", outcomeNote: "died rather than finished · SessionEnd reason: killed",
        git: { state: "clean", note: "no porcelain entries under current tracking rules" }, rate: null, subs: [] },
      { id: "c73b1a58", h: "Cursor", title: "Trace the terraform module graph",
        st: "idle", now: "idle 5d 17h", rate: null,
        block: { state: "unknown", note: "harness does not report blocks" }, subs: [] },
    ],
    delegation: { pct: null, why: "Waiting on one complete token-rate window.", window: "last 5d 17h" },
    changes: [],
    changeNote: "no state changes observed in the last 5d 17h",
    tripwires: [],
  }),
  P({
    key: "antigravity",
    scope: null, scopeWhy: "Exact location not published",
    label: { shared: 2, note: "2 sessions share this display label" },
    goal: null, goalWhy: "Antigravity publishes no assignment field.",
    goalGap: null,
    sessions: [
      { id: "d5f18c72", h: "Antigravity", title: null, titleWhy: "Title not published",
        st: "working", now: "generating…", next: null,
        turn: { into: "12m", ends: null, endsWhy: "Harness does not report turn bounds" },
        rate: "1,103 /m", block: { state: "unknown", note: "harness does not report blocks" },
        stuck: "4 tool failures in a row", subs: [] },
      { id: "e0c4a935", h: "Antigravity", title: null, titleWhy: "Title not published",
        st: "working", now: "generating…", next: null,
        turn: { into: "3m", ends: null, endsWhy: "Harness does not report turn bounds" },
        rate: "812 /m", block: { state: "unknown", note: "harness does not report blocks" }, subs: [] },
    ],
    delegation: { pct: null, why: "Waiting on one complete token-rate window.", window: "last 3m" },
    changes: [],
    changeNote: "no state changes observed in the last 3m",
    tripwires: [],
  }),
  P({
    key: "projects/pendulum-of-despair",
    scope: "~/projects/pendulum-of-despair",
    label: { shared: 1, note: null },
    goal: null, goalWhy: "Antigravity publishes no assignment field.",
    goalGap: null,
    sessions: [
      { id: "3b91d7e4", h: "Antigravity", title: null, titleWhy: "Title not published",
        st: "working", now: "generating…", next: null,
        turn: { into: "27m", ends: null, endsWhy: "Harness does not report turn bounds" },
        rate: "640 /m", block: { state: "unknown", note: "harness does not report blocks" }, subs: [] },
    ],
    delegation: { pct: null, why: "Waiting on one complete token-rate window.", window: "last 27m" },
    changes: [],
    changeNote: "no state changes observed in the last 27m",
    tripwires: [],
  }),
];

// P4 · shipped. Each window's budget against its own clock. DEC-12 ruled out
// projecting a burn rate, so pace is reported, never extrapolated into a verdict.
export const WINDOWS = [
  { key: "codex-week", vendor: "Codex", window: "weekly · 7d 0h", used: 25, pace: "13.3×", paceHot: true,
    ends: "21:36 · in 2h 32m", resets: "6d 21h", clock: 6,
    detail: [
      ["The remaining 75% buys 7h 36m at this window's average pace, or 4h 57m at the recent pace (last 3m). Resets in 6d 21h.", true],
      ["Sessions in recce/cargento have worked 3s to 34m, median 8m, from 4 observed. 1 more session has no closed working interval in the retained window and is not in that figure.", true],
      ["Recent pace measured at zero: nothing spent across 2m and 12 readings, so nothing is projected from it.", false],
    ] },
  { key: "claude-5h", vendor: "Claude", window: "5-hour · 5h 0m", used: 8, pace: "0.2×", paceHot: false,
    ends: "Wed 11:11 · ~78% spare at reset", resets: "3h 9m", clock: 45, detail: [] },
  { key: "claude-week", vendor: "Claude", window: "weekly · 7d 0h", used: 81, pace: "1.0×", paceHot: true,
    ends: "Wed 20:58", resets: "1d 11h", clock: 80, detail: [] },
];

// Sub-limits inside the Claude weekly budget. They publish no clock, so they
// get a number and nothing else — no pace, no projected end.
export const SUBLIMITS = { within: "Claude · weekly", rows: [["Fable", "0%"]],
  note: "Per-model sub-limits publish no clock, so no pace and no projected end." };

// P1 · shipped. Coverage is stated per harness so a silent row is
// distinguishable from a missing one.
export const COVERAGE = {
  // Denominators are derived from the session fixture, never written by hand:
  // 12 sessions · 5 carry a subject · 7 do not. DRC-4453 was exactly this bug.
  observed: "5 of 12 sessions carry a subject: 1 waiting on you · 4 at risk · 0 to close the loop.",
  quiet: "The other 7: 6 moving · 1 quiet; of these, 1 partially read.",
  gates: "4 of 7 harnesses report needs-input · 3 unknown · ends observed on 3 sessions",
  rows: [
    ["Claude", "needs-input reporting", "token-rate reporting", 2],
    ["Codex", "needs-input reporting, where approvals are enabled", "token-rate reporting", 2],
    ["Antigravity", "needs-input reporting unknown", "token-rate reporting", 1],
    ["Pi", "needs-input reporting unknown", "token-rate reporting", 1],
    ["Copilot", "needs-input reporting", "token-rate not reported", 1],
    ["Cursor", "needs-input reporting", "token-rate not reported", 1],
    ["Droid", "needs-input reporting unknown", "token-rate not reported", 0],
  ],
  caveats: [
    "No exact requests published.",
    "A session with no observed end is not known to be running.",
    "Termination cause not reported.",
  ],
};

// Two scopes, counted separately. A session subject is one of the 5 above; a
// board subject is not a session and is not in that denominator.
export const RISKS = [
  { scope: "session", title: "Stuck signal", identity: "antigravity · d5f18c72", src: "Antigravity",
    now: "4 tool failures in a row, no state change in 12m", next: null, tone: "amber" },
  { scope: "session", title: "Ended leaving uncommitted work", identity: "recce/cargento · 8e2b6a90", src: "Claude",
    now: "3 porcelain entries under current tracking rules, 41m ago", next: null, tone: "clay" },
  { scope: "session", title: "Died rather than finished", identity: "recce/recce-cloud-infra · a19f4e26", src: "Codex",
    now: "SessionEnd reason: killed, 2h ago", next: null,
    sub: "Termination cause beyond the reason field is not reported", tone: "clay" },
  { scope: "session", title: "Finished, and nobody read it", identity: "recce/cargento · 2f7d3c04", src: "Codex",
    now: "Ended 9m ago and has not been read", next: null, tone: "amber" },
  { scope: "board", title: "Quota pressure", identity: "Claude · weekly window", src: "Claude vendor fetch",
    now: "81% reported, 1.0× the pace this window sustains", next: "Resets Wed 21:44", tone: "amber" },
  { scope: "board", title: "Identity collision", identity: "recce/cargento display label · 10 exact sessions", src: "Claude",
    now: "10 exact sessions share this display label", next: null,
    sub: "Identity scope only; shared location is not established", tone: "grey" },
];

// Still open on the roadmap. Named here so the board can say so rather than
// implying the capability exists.
export const OPEN = [
  ["C4", "Stated goals across sessions", "Goals shown are whatever a harness publishes. Nothing normalises them yet."],
  ["C6", "Irreversible actions", "Force pushes and destructive shapes are not reported on this board yet."],
  ["C1", "Subagent tripwires", "Tripwires are held in this browser. No observer enforces them."],
  ["F3", "Attention accounting", "Delegation share is measured per project, not yet aggregated across the week."],
  ["E5", "Ended with unpushed commits", "The board reports uncommitted work, not commits that never reached a remote."],
];

export function derive() {
  const projects = PROJECTS.map(p => {
    const sess = p.sessions.map(s => ({
      ...s,
      titleText: s.title || s.titleWhy,
      titleKnown: !!s.title,
      isWorking: s.st === "working",
      isNeeds: s.st === "needs",
      isEnded: s.st === "ended",
      isIdle: s.st === "idle",
      hasAsk: !!s.ask,
      hasRate: !!s.rate,
      hasStuck: !!s.stuck,
      nextText: s.next || "No pending step published",
      nextKnown: !!s.next,
    }));
    const needs = sess.filter(s => s.isNeeds);
    const working = sess.filter(s => s.isWorking);
    const ended = sess.filter(s => s.isEnded);
    const risky = sess.filter(s => s.hasStuck || (s.outcome && s.outcome !== "clean"));
    return {
      ...p, sess, needs, working, ended, risky,
      nNeeds: needs.length, nWorking: working.length, nEnded: ended.length,
      total: sess.length,
      active: working.length + needs.length,
      hasGoal: !!p.goal,
      hasScope: !!p.scope,
      shared: p.label.shared > 1,
      hasChanges: p.changes.length > 0,
      unattended: p.changes.filter(c => c[3]).length,
    };
  });
  // DRC-4468 · a project blocked on the reader ranks above one merely working.
  const rank = (p) => (p.nNeeds ? 0 : (p.risky.length ? 1 : (p.nWorking ? 2 : 3)));
  projects.sort((a, b) => rank(a) - rank(b));
  const activeProjects = projects.filter(p => p.active > 0);
  const restProjects = projects.filter(p => p.active === 0);
  const allSess = projects.flatMap(p => p.sess.map(s => ({
    ...s, project: p.key,
    whereText: p.hasScope ? p.scope : (p.scopeWhy || "Exact location not published"),
    whereKnown: p.hasScope,
    sharedNote: p.label.shared > 1 ? p.label.shared + " sessions share this label" : null,
  })));
  const active = allSess.filter(s => s.isWorking || s.isNeeds);
  const reportsBlock = allSess.filter(s => s.block && s.block.state !== "unknown");
  const counters = [
    ["ACTIVE NOW", active.length, allSess.length + " recently observed"],
    ["WORKING", allSess.filter(s => s.isWorking).length, active.length - allSess.filter(s => s.isWorking).length + " waiting on you"],
    ["EXACT REQUESTS", 0, "no session published an exact request"],
    ["REPORTED BLOCKS", 0, reportsBlock.length + " of " + allSess.length + " sessions report block state"],
  ];
  return {
    active, counters,
    history: allSess.filter(s => s.isEnded || s.isIdle),
    projects, activeProjects, restProjects, allSess,
    running: allSess.filter(s => s.isWorking).length,
    needsCount: allSess.filter(s => s.isNeeds).length,
    subagents: allSess.reduce((a, s) => a + s.subs.length, 0),
    windows: WINDOWS, sublimits: SUBLIMITS, coverage: COVERAGE, open: OPEN,
    risks: RISKS.filter(r => r.scope === "session").map((r, i) => ({ ...r, n: i + 1 })),
    boardRisks: RISKS.filter(r => r.scope === "board").map((r, i) => ({ ...r, n: i + 1 })),
  };
}
