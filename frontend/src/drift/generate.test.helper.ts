import { mulberry32, pick, type Rng } from '../observed/generate.test.helper';

export { mulberry32, pick, type Rng };

/* Generated evidence entries, annotations and stored readings for the Drift step's differential tests. Every
   value comes from a small closed set that includes the awkward ones (a number where text belongs, an empty
   id, a key the build does not know), because a reading is stored data a tab may read long after it was
   written and the shape contract is about what survives that. */

const TYPES = [
  'user_message',
  'user_message',
  'agent_message',
  'agent_message',
  'tool_report',
  'tool_report',
  'tool_report',
  'result',
  'work_result',
  'gate_decision',
  'observer_snapshot',
  'decision',
];

export interface GenEntry {
  id: string;
  type: string;
  by: string;
  summary: string;
  at: unknown;
  resultAt: unknown;
  sourceSession: unknown;
  workerKind: string;
  actorClaim: string;
  modelDerived: boolean;
  subject: string;
  copied: boolean;
  work: boolean;
  result: string;
  resultSource: string;
  earlierFailed: boolean;
  beforeLastChange: boolean;
  changedAfter: boolean;
  readIncomplete: boolean;
  source: string;
}

export function genEntries(rnd: Rng, harness: string): GenEntry[] {
  const count = Math.floor(rnd() * 11);
  return Array.from({ length: count }, (_, index) => {
    const type = pick(rnd, TYPES);
    const report = type === 'tool_report';
    return {
      id: pick(rnd, [`e${String(index)}`, `e${String(index)}`, `e${String(index)}`, '']),
      type,
      by: pick(rnd, ['person:me', 'agent', '']),
      summary: pick(rnd, ['A summary', 'src/a.ts', 'pytest', '']),
      at: pick(rnd, [100 + index * 10, 100 + index * 10, 0, null, 'x', 205]),
      resultAt: pick(rnd, [undefined, undefined, 0, 300, 120 + index * 10]),
      sourceSession: { harness, sid: 's1' },
      workerKind: '',
      actorClaim: pick(rnd, ['', 'model-derived', 'deterministic']),
      modelDerived: rnd() < 0.2,
      subject: report ? pick(rnd, ['check', 'check', 'write']) : pick(rnd, ['', 'check']),
      copied: type === 'user_message' && rnd() < 0.2,
      work: report || type === 'work_result' || (type === 'result' && rnd() < 0.5),
      result: pick(rnd, ['passed', 'failed', '', 'passed']),
      resultSource: pick(rnd, ['passed flag', 'failed flag', 'passed summary', '']),
      earlierFailed: rnd() < 0.2,
      beforeLastChange: rnd() < 0.2,
      changedAfter: rnd() < 0.2,
      readIncomplete: rnd() < 0.15,
      source: pick(rnd, [
        'transcript · exact',
        'Pi bash tool call · exact',
        'a source',
        '',
        'transcript · exact',
      ]),
    };
  });
}

const RESULTS = [
  'departure',
  'consistent with the evidence read',
  'not verifiable from available evidence',
  'not shown by the record',
  'not reached at this stop',
  'met',
  '',
  null,
  7,
];
const WHYS = [
  '',
  '',
  'not-asked',
  'unreadable',
  'uncited',
  'no-work-shown',
  'verdict-stated',
  'check-does-not-show-it',
  'failed-check-unread',
  'changed-after-check',
  'tells-the-person',
  'claim-uncited',
  'claim-record-unread',
  'mystery',
];

function genCriterion(rnd: Rng, entries: readonly GenEntry[], key = ''): unknown {
  const said = entries.find((entry) => entry.type === 'agent_message');
  if (key === 'claims' && said && rnd() < 0.6) {
    const record = entries.filter((entry) => entry.id && entry.id !== said.id);
    const pickRecord = record.length ? [pick(rnd, record).id] : [];
    return {
      result: pick(rnd, RESULTS.slice(0, 5)),
      cites: pick(rnd, [[said.id], [said.id, ...pickRecord], [said.id, ...pickRecord]]),
      detail: 'It claimed more than the record shows',
    };
  }
  const shape = rnd();
  if (shape < 0.04) return 'text';
  if (shape < 0.07) return null;
  if (shape < 0.09) return ['array'];
  const cites = Array.from({ length: Math.floor(rnd() * 4) }, () =>
    pick(rnd, [...entries.map((entry) => entry.id), 'missing', 4]),
  );
  const row: Record<string, unknown> = {
    result: pick(rnd, RESULTS),
    cites: pick(rnd, [cites, cites, cites, undefined, 'x']),
    detail: pick(rnd, ['It went elsewhere', '', undefined]),
    clause: pick(rnd, ['Ship the queue', 'A line', '', undefined]),
    why: pick(rnd, WHYS),
  };
  if (rnd() < 0.05) row['extra'] = 1;
  for (const key of Object.keys(row)) if (row[key] === undefined) delete row[key];
  return row;
}

export function genAnnotation(rnd: Rng): Record<string, unknown> {
  const out: Record<string, unknown> = {
    goal: pick(rnd, ['Ship the queue', '', '  ', 'Fix login']),
    revision: pick(rnd, [3, 3, 3, 2, null, 0]),
    revision_count: 3,
    at: pick(rnd, [150, 90, null]),
    goal_source: pick(rnd, ['', '', 'typed', 'first-prompt', 'latest-prompt', 'chosen-prompt']),
    goal_source_at: pick(rnd, [100, 0, null]),
    goal_saved_at: pick(rnd, [150, null]),
    settled_through: pick(rnd, [null, null, 160]),
  };
  for (let k = 1; k <= 6; k += 1) {
    if (rnd() < 0.35) out[`line_${String(k)}`] = pick(rnd, ['A line', 'Another line', '']);
    if (rnd() < 0.2) {
      out[`line_${String(k)}_source`] = pick(rnd, ['entry', 'typed']);
      out[`line_${String(k)}_source_id`] = pick(rnd, ['e1', 'e2', '']);
    }
  }
  return out;
}

export function genAssessment(rnd: Rng, entries: readonly GenEntry[]): Record<string, unknown> {
  const criteria: Record<string, unknown> = {};
  for (const key of ['goal', 'line_1', 'line_2', 'line_3', 'output', 'claims', 'line_9', 'bogus']) {
    if (rnd() < 0.55) criteria[key] = genCriterion(rnd, entries, key);
  }
  const assessment: Record<string, unknown> = {
    revision_read: pick(rnd, [3, 3, 3, 2, null]),
    revision_read_at: pick(rnd, [150, null]),
    window_start: pick(rnd, [100, 0, null, 140]),
    read_at: pick(rnd, [260, 400, 100, null]),
    goal_source: pick(rnd, ['typed', 'first-prompt', '']),
    goal_source_at: pick(rnd, [100, null]),
    stamp: pick(rnd, ['model · today', '']),
    cutoff: pick(rnd, ['Evidence read up to its end.', '']),
    scope: pick(rnd, ['last-turn', 'mid-flight', 'session-end', '']),
    scope_text: pick(rnd, ['Read to its last turn.', '']),
    evidence_through: pick(rnd, [250, null]),
    coverage: pick(rnd, [
      undefined,
      undefined,
      null,
      {
        tail_truncated: true,
        tail_start: 120,
        unlisted: 2,
        unread_checks: 1,
        goal_source: 'whole',
      },
      {
        tail_truncated: false,
        tail_start: null,
        unlisted: 0,
        unread_checks: 0,
        goal_source: 'typed',
      },
      { tail_truncated: 'x' },
    ]),
    criteria,
  };
  if (rnd() < 0.07) assessment['surprise'] = true;
  for (const key of Object.keys(assessment))
    if (assessment[key] === undefined) delete assessment[key];
  return assessment;
}
