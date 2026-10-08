import { describe, expect, it } from 'vitest';
import type { ContextEntry } from '../store/board';
import { canonical, firstDifference } from '../observed/legacy.test.helper';
import { annotationOf } from './annotation';
import { intentDraft } from '../sessions/intent';
import { genSession, mulberry32, pick, type Rng } from './generate.test.helper';
import { loadLegacyIntent } from './legacy.test.helper';
import {
  baselineAt,
  conflictCandidates,
  entryNumbers,
  laterDirections,
  personAuthored,
  workAbsence,
  workSource,
} from './work';

/* The observed record a session's panel reads, and the later directions found in it, run next to the legacy
   functions over generated contexts. A difference is a bug here. */
const legacy = loadLegacyIntent();

const WORK_ROWS_PROBE = 20;
const SEEDS = Number(process.env['INTENT_SEEDS'] ?? 300);

function genFact(
  rnd: Rng,
  index: number,
  session: Record<string, unknown>,
): Record<string, unknown> {
  const own = rnd() < 0.8;
  return {
    fact_id: pick(rnd, [`f${String(index)}`, `f${String(index)}`, '', null]),
    type: pick(rnd, [
      'user_message',
      'user_message',
      'agent_message',
      'gate_decision',
      'tool_report',
      'work_result',
      'result',
      'observer_snapshot',
    ]),
    by: pick(rnd, ['person:alice', 'agent', '', null]),
    summary: pick(rnd, ['Do the thing', '', null, 'Another direction.']),
    at: pick(rnd, [800, 900, 950, 1000, 0, null, 'x', 1010]),
    result_at: pick(rnd, [undefined, 0, 960]),
    copied: pick(rnd, [true, false, undefined]),
    source_session: own
      ? { harness: session['harness'], sid: session['sid'] }
      : pick(rnd, [{ harness: 'codex', sid: 'other' }, {}, null]),
    evidence: pick(rnd, [{ source: 'transcript', confidence: 'high' }, {}, null, undefined]),
    actor_claim: pick(rnd, ['model-derived', '', undefined]),
    worker_kind: pick(rnd, ['', 'subagent', undefined]),
    earlier_failed: pick(rnd, [true, undefined]),
    before_last_change: pick(rnd, [true, undefined]),
    changed_after: pick(rnd, [true, undefined]),
    read_incomplete: pick(rnd, [true, undefined]),
  };
}

function genEntry(rnd: Rng, session: Record<string, unknown>) {
  if (rnd() < 0.12) return null;
  const facts = Array.from({ length: Math.floor(rnd() * 40) }, (_, i) => genFact(rnd, i, session));
  const data: Record<string, unknown> = {
    ...(rnd() < 0.9 ? { semantic: { facts } } : {}),
    sources: {
      work: {
        tool_reports: pick(rnd, [
          [{ harness: session['harness'], sid: session['sid'], note: 1 }],
          [],
          'x',
        ]),
        line_requests: pick(rnd, [
          [{ harness: session['harness'], sid: session['sid'], a: 1 }],
          [
            { harness: session['harness'], sid: session['sid'], a: 1 },
            { harness: session['harness'], sid: session['sid'], a: 2 },
          ],
          [],
        ]),
        omitted: pick(rnd, [[{ harness: session['harness'], sid: session['sid'] }], [], undefined]),
      },
      observer: { live: pick(rnd, [3, undefined, 'x']) },
    },
  };
  const error = rnd() < 0.15;
  return { data: rnd() < 0.1 ? null : data, revision: 1, error: error ? true : undefined };
}

function toReact(entry: {
  data: unknown;
  revision: number;
  error?: true | undefined;
}): ContextEntry {
  return {
    data: entry.data as ContextEntry['data'],
    revision: entry.revision,
    error: entry.error ? { kind: 'network-error' } : null,
  };
}

describe('the observed record and the later directions read as the legacy page reads them', () => {
  it(`agree on ${String(SEEDS)} generated contexts`, () => {
    const failures: string[] = [];
    const seen: Record<string, number> = {};
    const note = (name: string) => {
      seen[name] = (seen[name] ?? 0) + 1;
    };
    for (let seed = 1; seed <= SEEDS && failures.length < 3; seed += 1) {
      const rnd = mulberry32(seed);
      const session: Record<string, unknown> = {
        ...genSession(rnd, seed),
        project_key: pick(rnd, ['/repo/a', '']),
      };
      const group = { label: String(session['project']), sessions: [session] };
      const focused = genEntry(rnd, session);
      const project = rnd() < 0.5 ? genEntry(rnd, session) : null;
      const key = (focus: boolean) =>
        legacy.call<string>('nextCockpitContextKey', group, focus ? session : null);
      legacy.setData({ annotate: pick(rnd, [true, false]), generated: 1000 });
      legacy.run('nextCockpitContexts.clear();');
      const contexts = new Map<string, ContextEntry>();
      if (focused) {
        legacy.run('nextCockpitContexts.set(__key, __entry);', { key: key(true), entry: focused });
        contexts.set(key(true), toReact(focused as never));
      }
      if (project) {
        legacy.run('nextCockpitContexts.set(__key, __entry);', { key: key(false), entry: project });
        contexts.set(key(false), toReact(project as never));
      }
      const projectKey = legacy.call<string>('nextCockpitStableKey', group);
      const theirs = legacy.call<Record<string, unknown>>('nextCockpitWorkSource', group, session);
      const mine = workSource(contexts, projectKey, session);
      note(`state:${mine.state}`);
      if (mine.state === 'read' && (mine.total ?? 0) > WORK_ROWS_PROBE) note('windowed');
      const found = [
        firstDifference(canonical(theirs), canonical(mine)),
        firstDifference(
          canonical(legacy.call('nextCockpitWorkAbsence', theirs)),
          canonical(workAbsence(mine)),
        ),
      ].find((message) => message !== null);
      if (found) {
        failures.push(`seed ${String(seed)}: ${found}`);
        continue;
      }
      const annotationPool = [
        { goal: 'x', goal_source: 'first-prompt', goal_source_at: 900, settled_through: 950 },
        { goal: 'x', goal_saved_at: 850, at: 900, settled_through: null },
        { goal: 'x', at: 920 },
        { goal: '', at: 930 },
        { goal: '', goal_source: 'chosen-prompt', goal_source_at: 870 },
        null,
      ];
      const all = (mine as { all?: readonly unknown[] }).all ?? [];
      const annotate = legacy.run<boolean>('nextData.annotate === true');
      const own = annotationOf(session);
      const draft = intentDraft(session, { annotate, unreadable: '' }, null);
      const cases: readonly (readonly [
        Record<string, unknown> | null,
        Record<string, unknown> | null,
        unknown,
      ])[] = [
        [own, session, draft],
        [pick(rnd, annotationPool), null, null],
      ];
      for (const [annotation, forSession, drafted] of cases) {
        const later = legacy.call('nextCockpitLaterDirections', annotation, all, forSession);
        const open = legacy.call('nextCockpitConflictCandidates', annotation, all, forSession);
        const baseline = legacy.call('nextCockpitBaselineAt', annotation, forSession);
        const again = [
          firstDifference(
            canonical(later),
            canonical(laterDirections(annotation, all as never, forSession, drafted as never)),
          ),
          firstDifference(
            canonical(open),
            canonical(conflictCandidates(annotation, all as never, forSession, drafted as never)),
          ),
          firstDifference(
            canonical(baseline),
            canonical(baselineAt(annotation, forSession, drafted as never)),
          ),
        ].find((message) => message !== null);
        if (again) failures.push(`seed ${String(seed)} later: ${again}`);
        if (laterDirections(annotation, all as never, forSession, drafted as never).length)
          note('later');
        if (conflictCandidates(annotation, all as never, forSession, drafted as never).length)
          note('open');
      }
      for (const entry of all) {
        const theirsAuthor = legacy.call('nextReadingPersonAuthored', entry);
        if (personAuthored(entry as never) !== theirsAuthor)
          failures.push(`seed ${String(seed)} author of ${JSON.stringify(entry).slice(0, 60)}`);
      }
      legacy.run('nextData = {...nextData, annotate: true};');
      const numbered = legacy.call<Map<string, number>>('nextCockpitEntryNumbers', session, theirs);
      const payload = { annotate: true };
      const minePairs = [
        ...entryNumbers(
          { ...session, annotation_window_start: session['annotation_window_start'] },
          mine,
          payload,
        ),
      ];
      if (JSON.stringify([...numbered]) !== JSON.stringify(minePairs))
        failures.push(
          `seed ${String(seed)} numbers: ${JSON.stringify([...numbered]).slice(0, 80)} vs ${JSON.stringify(minePairs).slice(0, 80)}`,
        );
    }
    expect(failures).toEqual([]);
    for (const name of [
      'state:read',
      'state:empty',
      'state:partial',
      'state:error',
      'state:unread',
      'windowed',
      'later',
      'open',
    ])
      expect(seen[name], name).toBeGreaterThan(0);
  });
});
