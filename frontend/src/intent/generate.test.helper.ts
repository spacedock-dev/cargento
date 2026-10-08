import { mulberry32, pick, type Rng } from '../observed/generate.test.helper';

/* Generated annotation rows and boards for the Intent step's differential tests. Every value is drawn
   from a small closed set that includes the awkward ones (blank, zero, a number where text belongs, the
   empty label), because the payload is untrusted and the legacy truthiness rules are part of what the
   two pages must agree on. */
export { mulberry32, pick, type Rng };

const WORDS = [
  'Ship the queue',
  'Fix the login redirect',
  '  padded words  ',
  'line one\nline two',
  'a'.repeat(260),
  'Stage the migration, then verify',
  '',
  '   ',
];

function maybe<T>(rnd: Rng, chance: number, make: () => T): T | undefined {
  return rnd() < chance ? make() : undefined;
}

export function genAnnotationFields(rnd: Rng): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  const set = (name: string, value: unknown) => {
    if (value !== undefined) out[`annotation_${name}`] = value;
  };
  set(
    'goal',
    maybe(rnd, 0.6, () => pick(rnd, [...WORDS, null, 5])),
  );
  set(
    'goal_why',
    maybe(rnd, 0.3, () => pick(rnd, ['No goal typed for this session.', '', null])),
  );
  set(
    'lines_why',
    maybe(rnd, 0.3, () => pick(rnd, ['No expected outcome typed.', '', null])),
  );
  for (let k = 1; k <= 6; k += 1) {
    set(
      `line_${String(k)}`,
      maybe(rnd, 0.35, () => pick(rnd, [...WORDS, null])),
    );
    set(
      `line_${String(k)}_source`,
      maybe(rnd, 0.25, () => pick(rnd, ['typed', 'entry', '', null])),
    );
    set(
      `line_${String(k)}_source_id`,
      maybe(rnd, 0.2, () => pick(rnd, ['f1', 'f2', '', null])),
    );
  }
  set(
    'revision',
    maybe(rnd, 0.6, () => pick(rnd, [1, 2, 5, 20, 0, null, 'x'])),
  );
  set(
    'revision_count',
    maybe(rnd, 0.6, () => pick(rnd, [1, 2, 4, 16, 0, null, 'x'])),
  );
  set(
    'at',
    maybe(rnd, 0.6, () => pick(rnd, [990, 940, 100, 0, 2000, null, 'x'])),
  );
  set(
    'goal_source',
    maybe(rnd, 0.4, () =>
      pick(rnd, ['first-prompt', 'latest-prompt', 'chosen-prompt', 'typed', '']),
    ),
  );
  set(
    'goal_source_at',
    maybe(rnd, 0.3, () => pick(rnd, [900, 0, null])),
  );
  set(
    'window_start',
    maybe(rnd, 0.3, () => pick(rnd, [800, 0, null])),
  );
  set(
    'binding_why',
    maybe(rnd, 0.2, () => pick(rnd, ['A shared prefix binds to the newest.', ''])),
  );
  set(
    'reading_count',
    maybe(rnd, 0.3, () => pick(rnd, [0, 1, 3, null])),
  );
  set(
    'reading_withheld',
    maybe(rnd, 0.15, () => pick(rnd, ['The reading was withheld.', ''])),
  );
  set(
    'assessment',
    maybe(rnd, 0.3, () =>
      pick(rnd, [{ revision_read: 1 }, { revision_read: 3 }, { revision_read: 'x' }, {}, null]),
    ),
  );
  set(
    'discarded_at',
    maybe(rnd, 0.15, () => pick(rnd, [950, 0, null, 'x'])),
  );
  set(
    'discarded_why',
    maybe(rnd, 0.15, () => pick(rnd, ['You discarded these words.', ''])),
  );
  return out;
}

export function genSession(rnd: Rng, index: number): Record<string, unknown> {
  return {
    harness: pick(rnd, ['claude', 'codex', 'pi']),
    sid: `s${String(index)}${pick(rnd, ['', ':x', ' y'])}`,
    project: pick(rnd, ['alpha/app', 'beta/api', '', 'gamma']),
    title: pick(rnd, ['Fix it', 'Ship the queue', null, '']),
    state: pick(rnd, ['working', 'idle', 'needs_input']),
    ...genAnnotationFields(rnd),
    ...(rnd() < 0.3
      ? {
          cached_deterministic_goal: pick(rnd, [
            { goal: 'Derived goal', observed_at: 900 },
            { goal: 'Derived goal' },
            { goal: '  ' },
            null,
          ]),
        }
      : {}),
    ...(rnd() < 0.3
      ? {
          spacedock: {
            workflows: pick(rnd, [
              [{ workflow: 'build', goal: 'Land it' }],
              [{ goal: '' }, { workflow: 'ship', goal: 'Ship' }],
              [],
              [null, 5],
            ]),
          },
        }
      : {}),
    ...(rnd() < 0.3 ? { departures: pick(rnd, [[{ a: 1 }], [{ a: 1 }, { a: 2 }], []]) } : {}),
    ...(rnd() < 0.2 ? { departure_why: pick(rnd, ['Cap spent.', '', null]) } : {}),
  };
}

/* A retained annotation row as `/api/annotations` publishes it: the typed fields without the
   `annotation_` prefix, plus the reading and raise fields the log prints. */
export function genRetained(rnd: Rng, session: Record<string, unknown> | null, index: number) {
  const row: Record<string, unknown> = {
    harness: session ? session['harness'] : pick(rnd, ['claude', 'codex']),
    sid: session ? session['sid'] : `gone${String(index)}`,
  };
  const set = (name: string, value: unknown) => {
    if (value !== undefined) row[name] = value;
  };
  const fields = genAnnotationFields(rnd);
  for (const [name, value] of Object.entries(fields)) row[name.replace(/^annotation_/, '')] = value;
  set(
    'goal',
    maybe(rnd, 0.7, () => pick(rnd, WORDS)),
  );
  set(
    'revision',
    maybe(rnd, 0.8, () => pick(rnd, [1, 2, 4, 20])),
  );
  set(
    'revision_count',
    maybe(rnd, 0.8, () => pick(rnd, [1, 2, 4, 16])),
  );
  set(
    'at',
    maybe(rnd, 0.8, () => pick(rnd, [990, 940, 700])),
  );
  set(
    'departures',
    maybe(rnd, 0.3, () => pick(rnd, [[{ a: 1 }], [{ a: 1 }, { a: 2 }], []])),
  );
  set(
    'departure_why',
    maybe(rnd, 0.3, () => pick(rnd, ['Cap spent.', '', null])),
  );
  set(
    'binding_why',
    maybe(rnd, 0.2, () => pick(rnd, ['A shared prefix binds to the newest.', ''])),
  );
  return row;
}

export interface LogCase {
  readonly payload: Record<string, unknown>;
  readonly rows: Record<string, unknown>[];
  readonly state: 'read' | 'error' | 'loading' | 'unread';
}

export function genLogCase(seed: number): LogCase {
  const rnd = mulberry32(seed);
  const sessions = Array.from({ length: 1 + Math.floor(rnd() * 5) }, (_, i) => genSession(rnd, i));
  const rows: Record<string, unknown>[] = [];
  sessions.forEach((session, index) => {
    if (rnd() < 0.55) rows.push(genRetained(rnd, session, index));
  });
  for (let i = 0; i < Math.floor(rnd() * 5); i += 1) rows.push(genRetained(rnd, null, i));
  const payload: Record<string, unknown> = {
    generated: 1000,
    sessions,
    annotate: pick(rnd, [true, true, true, false]),
    ...(rnd() < 0.5 ? { unasked: pick(rnd, [true, false]) } : {}),
    ...(rnd() < 0.2 ? { spacedock_enabled: false } : {}),
    annotate_discard: {
      record: 'The record of a discard.',
      record_standing: 'A raise still quotes it.',
    },
  };
  return {
    payload,
    rows,
    state: pick(rnd, ['read', 'read', 'read', 'error', 'loading', 'unread']),
  };
}
