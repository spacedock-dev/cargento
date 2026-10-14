import { describe, expect, it } from 'vitest';
import { contextKey } from '../api/identity';
import { entryLabel, entryNumbering, labelOrder, workEntries, workSource } from './work';

/* A message is numbered by its rank in the session and a check or file by the message it follows and its place
   after that message, so a number never moves when the page holds more or fewer entries. */
const session = { harness: 'claude', sid: 's1' };
const fact = (id: string, at: number, extra: Record<string, unknown> = {}) => ({
  fact_id: id,
  type: 'user_message',
  at,
  summary: id,
  source_session: session,
  ...extra,
});
const entries = (facts: unknown[]) => workEntries(session, { facts });
const labelsOf = (facts: unknown[], payload: Record<string, unknown> = {}, ordinals = true) => {
  const all = entries(facts);
  const numbering = entryNumbering(session, { all, entries: all, ordinals }, payload);
  return [...numbering.numbers].map(([entry, label]) => [entry.id, label]);
};

describe('an entry label', () => {
  it('reads 41 for a message and 41.2 for the second check after it', () => {
    const [message, check] = entries([
      fact('m', 100, { ordinal: 41 }),
      fact('c', 101, { type: 'tool_report', ordinal: 41, ordinal_sub: 2 }),
    ]);
    expect(message && entryLabel(message)).toBe('41');
    expect(check && entryLabel(check)).toBe('41.2');
  });

  it('is absent for an entry the server published no number for', () => {
    const [entry] = entries([fact('m', 100)]);
    expect(entry && entryLabel(entry)).toBeNull();
  });

  it('reads a malformed number as none, never as a wrong one', () => {
    const [entry] = entries([fact('m', 100, { ordinal: '41', ordinal_sub: 1.5 })]);
    expect(entry?.ordinal).toBeNull();
    expect(entry?.ordinalSub).toBeNull();
  });

  it('sorts 41 before 41.1 before 41.2 before 42, and 9 before 10', () => {
    const shuffled = ['42', '41.2', '10', '41', '9', '41.1'];
    expect([...shuffled].sort(labelOrder)).toEqual(['9', '10', '41', '41.1', '41.2', '42']);
  });
});

describe('numbering a list that carries the server numbers', () => {
  const facts = [
    fact('m41', 100, { ordinal: 41 }),
    fact('c41.1', 101, { type: 'tool_report', ordinal: 41, ordinal_sub: 1 }),
    fact('c41.2', 102, { type: 'tool_report', ordinal: 41, ordinal_sub: 2 }),
    fact('m42', 103, { ordinal: 42 }),
  ];

  it('labels each entry with its own number', () => {
    expect(labelsOf(facts)).toEqual([
      ['m41', '41'],
      ['c41.1', '41.1'],
      ['c41.2', '41.2'],
      ['m42', '42'],
    ]);
  });

  it('keeps a number when the check beside it is gone from the page', () => {
    expect(labelsOf([facts[0], facts[2], facts[3]])).toEqual([
      ['m41', '41'],
      ['c41.2', '41.2'],
      ['m42', '42'],
    ]);
  });

  it('keeps a number when older entries are not loaded', () => {
    expect(labelsOf(facts.slice(2))).toEqual([
      ['c41.2', '41.2'],
      ['m42', '42'],
    ]);
  });

  it('draws an entry with no number as unnumbered, not as a wrong one', () => {
    const all = entries([...facts, fact('w', 104, { type: 'work_birth' })]);
    const numbering = entryNumbering(session, { all, entries: all, ordinals: true }, {});
    expect(numbering.unnumbered.map((entry) => entry.id)).toEqual(['w']);
    expect(numbering.numbers.size).toBe(4);
  });

  it('still sets an entry before the window aside, and an untimed one', () => {
    const all = entries([
      fact('old', 50, { ordinal: 3 }),
      fact('none', 0, { ordinal: 4 }),
      ...facts,
    ]);
    const numbering = entryNumbering(
      { ...session, annotation_window_start: 90 },
      { all, entries: all, ordinals: true },
      { annotate: true },
    );
    expect(numbering.earlier.map((entry) => entry.id)).toEqual(['old']);
    expect(numbering.untimed.map((entry) => entry.id)).toEqual(['none']);
    expect(numbering.numbers.size).toBe(4);
  });
});

describe('numbering a list without server numbers', () => {
  it('counts what the page holds from the oldest, as text', () => {
    expect(labelsOf([fact('a', 10), fact('b', 20), fact('c', 30)], {}, false)).toEqual([
      ['a', '1'],
      ['b', '2'],
      ['c', '3'],
    ]);
  });
});

describe('when the page can use the server numbers', () => {
  const contexts = (focus: unknown[] | null, project: unknown[] | null) => {
    const map = new Map();
    const put = (key: string, facts: unknown[]) =>
      map.set(key, { data: { semantic: { facts } }, revision: 1, error: null });
    if (focus) put(contextKey('/p', session), focus);
    if (project) put(contextKey('/p', null), project);
    return map;
  };
  const numbered = [fact('m', 100, { ordinal: 41 })];

  it('is true once the session own context has loaded and carries them', () => {
    expect(workSource(contexts(numbered, null), '/p', session).ordinals).toBe(true);
  });

  it('is false while only the project context has loaded, which carries none for this session', () => {
    expect(workSource(contexts(null, [fact('m', 100)]), '/p', session).ordinals).toBe(false);
  });

  it('is false when the session own context carries none, as for a harness without them', () => {
    expect(workSource(contexts([fact('m', 100)], null), '/p', session).ordinals).toBe(false);
  });

  it('keeps the context number when a record page read before the index finished carries none', () => {
    const map = new Map([
      [
        contextKey('/p', session),
        {
          data: { semantic: { facts: [fact('m', 100, { ordinal: 41 })] } },
          revision: 1,
          error: null,
        },
      ],
    ]);
    const record = { status: 'loaded', entries: [fact('m', 100)] };
    const source = workSource(map, '/p', session, record as never);
    expect(source.all?.[0]?.ordinal).toBe(41);
    expect(source.ordinals).toBe(true);
  });
});
