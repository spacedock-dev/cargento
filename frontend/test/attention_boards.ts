/* Synthetic boards for the Attention step's tests: the unit tests and the browser proof build the same
   payloads, so a behaviour proven in one is the behaviour driven in the other. Every value is JSON, and
   nothing here is a real transcript, harness store, question or path. Plain TypeScript with no imports, so
   Node can strip its types when the browser script loads it.

   `attentionBoard` makes one board with every queue longer than the three rows a section shows at first:
   five sessions holding a question, a long failing turn, a stop and an end that left work behind, tasks
   coming next, two sessions that publish one label, a quiet delegated launch, and a question no session
   owns. `revision` reorders and replaces rows the way a live board does, so a test can hold a reader's
   choice across it. */

export interface BoardOptions {
  readonly generated?: number;
  /** Which exact sids hold a question. Defaults to five. */
  readonly asking?: readonly string[];
  /** Reverses every queue's source order, which is what a revision that reorders looks like. */
  readonly reversed?: boolean;
  /** Sids that have gone from the board. */
  readonly gone?: readonly string[];
  /** Sids that have just moved from working to needs_input, without a question. */
  readonly blocked?: readonly string[];
  /** The server's own native lane owns the banner. */
  readonly nativeNotify?: string;
  /** What the server says about the browser lane, or absent. */
  readonly browserLane?: boolean;
  readonly terminals?: boolean;
  /** A question whose session the board does not hold. On by default; it is a board risk of its own. */
  readonly unowned?: boolean;
  /** A command-shape report whose stamp is no date. The legacy page throws on one and draws nothing; this page prints the report without a time. */
  readonly malformedReport?: boolean;
}

const NOW = 1_000_000;

type Row = Record<string, unknown>;

export const ASKING = ['gate-1', 'gate-2', 'gate-3', 'gate-4', 'gate-5'] as const;

function sessions(options: BoardOptions): Row[] {
  const asking = options.asking ?? ASKING;
  const rows: Row[] = [];
  for (const [index, sid] of ['gate-1', 'gate-2', 'gate-3', 'gate-4', 'gate-5'].entries()) {
    rows.push({
      harness: 'claude',
      sid,
      session: sid,
      project: index % 2 ? 'beta/api' : 'alpha/app',
      title: `Gate ${String(index + 1)}`,
      state: asking.includes(sid) ? 'needs_input' : 'working',
      state_detail: asking.includes(sid) ? 'waiting on a permission prompt' : 'generating',
      active: true,
      blocked_since: NOW - 300 - index * 40,
      focusable: options.terminals === true && index < 2,
      resume_id: sid,
      last_activity: NOW,
    });
  }
  rows.push({
    harness: 'claude',
    sid: 'long-turn',
    session: 'long-turn',
    project: 'gamma',
    title: 'A long turn and a failing loop',
    state: 'working',
    active: true,
    last_activity: NOW,
    turn: { elapsed_h: '41m', long: true },
    loop: { errors: 3, failures: 5, tool: 'mcp__demo__send', barren: false },
  });
  for (const [index, dirty] of [true, false, null, true].entries()) {
    rows.push({
      harness: 'claude',
      sid: `ended-${String(index + 1)}`,
      session: `ended-${String(index + 1)}`,
      project: `done/${String(index + 1)}`,
      title: `Ended ${String(index + 1)}`,
      state: 'idle',
      ended_at: NOW - 100 * (index + 1),
      finished_at: NOW - 120 * (index + 1),
      ...(dirty === null ? {} : { dirty, changed: dirty ? index + 2 : 0 }),
      last_activity: NOW - 100 * (index + 1),
    });
  }
  for (let index = 1; index <= 4; index += 1) {
    rows.push({
      harness: 'codex',
      sid: `task-${String(index)}`,
      session: `task-${String(index)}`,
      project: `later/${String(index)}`,
      title: `Task ${String(index)}`,
      state: index % 2 ? 'working' : 'idle',
      active: index % 2 === 1,
      last_activity: NOW - index * 5,
      tasks: [
        {
          id: '1',
          subject: `Step ${String(index)}`,
          status: index === 3 ? 'in_progress' : 'pending',
        },
      ],
    });
  }
  for (const [index, harness] of ['claude', 'codex'].entries()) {
    rows.push({
      harness,
      sid: `twin-${String(index + 1)}`,
      session: `twin-${String(index + 1)}`,
      project: 'shared/label',
      title: `Twin ${String(index + 1)}`,
      state: 'idle',
      last_activity: NOW - 3000,
    });
  }
  rows.push({
    harness: 'claude',
    sid: 'delegated',
    session: 'delegated',
    project: 'delta',
    title: 'Launched work nobody saw finish',
    state: 'idle',
    last_activity: NOW - 2400,
    delegated_launches: 2,
    delegated_unpaired: 1,
    delegated_latest_launch_at: NOW - 2600,
    delegated_last_activity_at: NOW - 2500,
    delegated_quiet_since: NOW - 2400,
    delegated_visibility: 'partial',
  });
  rows.push({
    harness: 'codex',
    sid: 'healthy',
    session: 'healthy',
    project: 'quiet/one',
    title: 'Healthy and idle',
    state: 'idle',
    last_activity: NOW - 20,
  });
  for (const sid of options.blocked ?? []) {
    const row = rows.find((candidate) => candidate['sid'] === sid);
    if (row) Object.assign(row, { state: 'needs_input', state_detail: 'a prompt appeared' });
  }
  const gone = new Set(options.gone ?? []);
  const kept = rows.filter((row) => !gone.has(String(row['sid'])));
  return options.reversed ? kept.reverse() : kept;
}

export function attentionBoard(options: BoardOptions = {}): Row {
  const asking = options.asking ?? ASKING;
  const ownedAsks = asking
    .filter((sid) => !(options.gone ?? []).includes(sid))
    .map((sid, index) => ({
      id: `ask-${sid}`,
      harness: 'claude',
      session_id: sid,
      project: index % 2 ? 'beta/api' : 'alpha/app',
      question: `Approve step ${String(index + 1)}?`,
      options: ['Yes', 'No'],
      age_sec: 500 - index * 60,
    }));
  const asks = [
    ...ownedAsks,
    ...(options.unowned === false
      ? []
      : [
          {
            id: 'ask-nobody',
            harness: 'claude',
            session_id: 'no-such-session',
            project: 'elsewhere',
            question: 'A question no session owns?',
            options: [],
            age_sec: 30,
          },
        ]),
  ];
  const body: Row = {
    generated: options.generated ?? NOW,
    window_hours: 24,
    ask: true,
    ends_observable: true,
    harnesses: [
      {
        key: 'claude',
        label: 'Claude Code',
        discovered: true,
        reports_needs_input: true,
        reports_needs_input_when: 'on a permission prompt',
        reports_rate: true,
      },
      {
        key: 'codex',
        label: 'Codex',
        discovered: true,
        reports_needs_input: false,
        reports_rate: false,
      },
      { key: 'gemini', label: 'Gemini', discovered: true, error: 'the store is not readable' },
    ],
    sessions: sessions(options),
    asks,
    native_notify: options.nativeNotify ?? '',
    irreversible_enabled: true,
    command_reports: [
      {
        harness: 'claude',
        sid: 'long-turn',
        label: 'rm -rf <dir>',
        tool_name: 'Bash',
        timestamp: 1_700_000_000,
      },
      {
        harness: 'claude',
        sid: 'nobody',
        label: 'git push --force',
        tool_name: 'Bash',
        timestamp: options.malformedReport === true ? 'not a stamp' : 1_700_000_100,
      },
    ],
  };
  if (options.browserLane !== undefined) body['browser_lane'] = options.browserLane;
  return body;
}
