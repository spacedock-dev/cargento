import { describe, expect, it } from 'vitest';
import { canonical, firstDifference } from '../observed/legacy.test.helper';
import { loadLegacyApp } from '../project/legacy.test.helper';
import { genSequence } from './generate.test.helper';
import {
  createWorkstream,
  payloadEvidence,
  projectChanges,
  projectWindow,
  windowLabel,
  windowPhrase,
  type WorkstreamEvidence,
} from './model';

/* The workstream, held to the legacy `next-workstream.js` by running both over the same generated board
   sequences: the tab's buffer (groups, entries, the seed from the history store), the per-project window
   and the changes a project page lists. The legacy page is the real one, loaded whole, and each sequence
   gets a fresh copy because its buffer is module state. */

const CASES = 80;
const SEEDS = CASES;

interface Legacy {
  readonly app: ReturnType<typeof loadLegacyApp>;
}

function legacyEvidence({ app }: Legacy): unknown {
  const evidence = app.call<Record<string, unknown>>('nextWorkstreamSnapshot');
  return shape(evidence);
}

/* A Map is invisible to `canonical`, which reads own keys, so both sides turn it into sorted pairs. */
function shape(evidence: unknown): unknown {
  const value = evidence as {
    groups: unknown[];
    observedSince: unknown;
    lastGenerated: unknown;
    seeded: unknown;
    seededSince: Map<string, number>;
  };
  return {
    groups: value.groups,
    observedSince: value.observedSince,
    lastGenerated: value.lastGenerated,
    seeded: value.seeded,
    seededSince: [...value.seededSince.entries()].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)),
  };
}

function projectsOf(sequence: readonly unknown[]): string[] {
  const names = new Set<string>(['', 'alpha/app', 'beta/api', 'unseen']);
  for (const body of sequence) {
    const rows = (body as { sessions?: unknown } | null)?.sessions;
    if (Array.isArray(rows))
      for (const row of rows) {
        const project = (row as { project?: unknown } | null)?.project;
        if (typeof project === 'string') names.add(project);
      }
  }
  return [...names];
}

/* The legacy page's `nextObservedHistory(project, evidence)`, which is where the changes a project page
   lists are derived from the window. */
function legacyChanges(app: ReturnType<typeof loadLegacyApp>, project: string): unknown {
  const history = app.run<Record<string, unknown>>(
    'nextObservedHistory(__project, nextWorkstreamSnapshot())',
    { project },
  );
  return {
    changes: history['changes'],
    noteText: history['changeNoteText'],
    emptyText: history['changeEmptyText'],
  };
}

describe('the workstream buffer reads as the legacy buffer does', () => {
  it(`agrees on ${String(SEEDS)} generated board sequences, evidence and per-project changes`, () => {
    const failures: string[] = [];
    for (let seed = 1; seed <= SEEDS; seed += 1) {
      const sequence = genSequence(seed);
      const app = loadLegacyApp();
      const mine = createWorkstream();
      for (const [index, body] of sequence.entries()) {
        let legacyThrew: unknown = null;
        try {
          app.observe(body);
        } catch (error) {
          legacyThrew = error;
        }
        // The legacy page would stop drawing on one of these; a port that returned quietly is the one to doubt.
        if (legacyThrew) {
          failures.push(
            `seed ${String(seed)} step ${String(index)}: legacy threw ${String(legacyThrew)}`,
          );
          break;
        }
        mine.observe(body);
        const left = canonical(legacyEvidence({ app }));
        const right = canonical(shape(mine.snapshot()));
        const found = firstDifference(left, right);
        if (found) failures.push(`seed ${String(seed)} step ${String(index)}: ${found}`);
      }
      if (failures.length === 0) {
        for (const project of projectsOf(sequence)) {
          const evidence = mine.snapshot();
          const found = firstDifference(
            canonical(legacyChanges(app, project)),
            canonical(projectChanges(projectWindow(project, evidence))),
          );
          if (found)
            failures.push(`seed ${String(seed)} project ${JSON.stringify(project)}: ${found}`);
        }
      }
      if (failures.length >= 3) break;
    }
    expect(failures).toEqual([]);
  }, 180_000);

  it('derives the same evidence from one payload alone', () => {
    const failures: string[] = [];
    for (let seed = 1; seed <= SEEDS; seed += 1) {
      const sequence = genSequence(seed);
      const body = sequence[sequence.length - 1];
      if (typeof body !== 'object' || body === null || Array.isArray(body)) continue;
      const app = loadLegacyApp();
      const legacy = app.run<unknown>('nextWorkstreamPayloadEvidence(__payload)', {
        payload: body,
      });
      const found = firstDifference(
        canonical(shape(legacy)),
        canonical(shape(payloadEvidence(body as never))),
      );
      if (found) failures.push(`seed ${String(seed)}: ${found}`);
      if (failures.length >= 3) break;
    }
    expect(failures).toEqual([]);
  }, 180_000);

  it('reaches the cases that make agreement mean something', () => {
    const seen = { seeded: 0, state: 0, turn: 0, ask: 0, unattended: 0, empty: 0, days: 0 };
    for (let seed = 1; seed <= SEEDS; seed += 1) {
      const mine = createWorkstream();
      for (const body of genSequence(seed)) mine.observe(body);
      const evidence: WorkstreamEvidence = mine.snapshot();
      if (evidence.seeded) seen.seeded += 1;
      for (const project of ['alpha/app', 'beta/api', '']) {
        const window = projectWindow(project, evidence);
        for (const event of window.events) {
          if (event.kind === 'state') seen.state += 1;
          if (event.kind === 'turn') seen.turn += 1;
          if (event.kind === 'ask') seen.ask += 1;
          if (event.filled) seen.unattended += 1;
        }
        if (window.events.length === 0) seen.empty += 1;
        if (/last \d+d/.test(windowLabel(window))) seen.days += 1;
      }
    }
    for (const [name, count] of Object.entries(seen)) expect(count, name).toBeGreaterThan(1);
  });
});

describe('the window words', () => {
  it('names how far back the evidence reaches, in the legacy forms', () => {
    const at = (started: number | null, ended: number | null) =>
      windowLabel({ startedAt: started, endedAt: ended });
    expect(at(null, 100)).toBe('since this tab opened');
    expect(at(100, null)).toBe('since this tab opened');
    expect(at(100, 100)).toBe('since this tab opened');
    expect(at(100, 130)).toBe('last 30s');
    expect(at(100, 100.4)).toBe('last 1s');
    expect(at(0, 3600 * 3 + 20 * 60)).toBe('last 3h 20m');
    expect(at(0, 3600 * 3)).toBe('last 3h');
    expect(at(0, 86400 * 14)).toBe('last 14d');
    expect(at(0, 86400 * 2 + 3600 * 5)).toBe('last 2d 5h');
    expect(windowPhrase({ startedAt: 0, endedAt: 600 })).toBe('in the last 10m');
    expect(windowPhrase({ startedAt: null, endedAt: 600 })).toBe('since this tab opened');
  });
});
