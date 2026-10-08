import { describe, expect, it } from 'vitest';
import { blockedBackend, fakeBackend, readOnlyBackend } from '../../test/storage_backends';
import {
  createLegacyStorage,
  decodeGraphModes,
  decodeUsage,
  GOAL_EDITOR_MAX_UTF16,
  goalKey,
  graphModeScope,
} from '.';

describe('graph mode family (cargento.next.graph.mode)', () => {
  it('scopes a choice by project and session joined on NUL', () => {
    expect(graphModeScope('p', 's')).toBe('p\u0000s');
    expect(graphModeScope('p', null)).toBe('p\u0000');
    expect(graphModeScope('p', undefined)).toBe('p\u0000');
  });

  it('loads only two-part keys with a valid mode, retiring the old empty-key entry', () => {
    const raw = JSON.stringify({
      '': 'all',
      'p\u0000': 'decisions',
      'p\u0000s': 'all',
      'a\u0000b\u0000c': 'all',
      'q\u0000s': 'sideways',
      'no-separator': 'all',
    });
    expect([...decodeGraphModes(raw)]).toEqual([
      ['p\u0000', 'decisions'],
      ['p\u0000s', 'all'],
    ]);
  });

  it('reads corrupt, scalar, array and missing values as no choices', () => {
    for (const raw of ['{', '5', '"x"', 'null', '[]', '["all"]', null, '']) {
      expect(decodeGraphModes(raw).size).toBe(0);
    }
  });

  it('writes the whole map as one JSON object', () => {
    const backend = fakeBackend();
    const { graphMode } = createLegacyStorage(() => backend);
    expect(graphMode.set(graphModeScope('p', 's'), 'all')).toBe(true);
    graphMode.set(graphModeScope('p', null), 'decisions');
    expect(backend.data.get('cargento.next.graph.mode')).toBe('{"p\\u0000s":"all","p\\u0000":"decisions"}');
  });

  it('refuses a mode that is not offered and writes nothing', () => {
    const backend = fakeBackend();
    const { graphMode } = createLegacyStorage(() => backend);
    expect((graphMode.set as (scope: string, mode: string) => boolean)('p\u0000', 'nope')).toBe(false);
    expect(backend.writes).toEqual([]);
  });

  it('resolves a pinned mode, then the stored one, then the default, then active', () => {
    const scope = graphModeScope('p', 's');
    const { graphMode } = createLegacyStorage(() => fakeBackend({ 'cargento.next.graph.mode': '{"p\\u0000s":"all"}' }));
    expect(graphMode.resolve({ scope, mode: 'decisions' })).toBe('decisions');
    expect(graphMode.resolve({ scope })).toBe('all');
    expect(graphMode.resolve({ scope: graphModeScope('q', 's'), defaultMode: 'decisions' })).toBe('decisions');
    expect(graphMode.resolve({ scope: graphModeScope('q', 's') })).toBe('active');
    expect(graphMode.resolve({ scope, mode: 'bogus' as 'all' })).toBe('all');
  });

  it('keeps the tab choice when storage refuses', () => {
    const { graphMode } = createLegacyStorage(() => readOnlyBackend());
    graphMode.set(graphModeScope('p', null), 'all');
    expect(graphMode.resolve({ scope: graphModeScope('p', null) })).toBe('all');
    expect(createLegacyStorage(() => blockedBackend()).graphMode.resolve({ scope: 'p\u0000' })).toBe('active');
  });
});

describe('cockpit project family (cargento.projectCockpitProject)', () => {
  it('stores the raw label and reads a missing or empty one as null', () => {
    const backend = fakeBackend();
    const { cockpitProject } = createLegacyStorage(() => backend);
    expect(cockpitProject.read()).toBeNull();
    expect(cockpitProject.write('my project')).toBe(true);
    expect(backend.data.get('cargento.projectCockpitProject')).toBe('my project');
    expect(cockpitProject.read()).toBe('my project');
    cockpitProject.write('');
    expect(backend.data.get('cargento.projectCockpitProject')).toBe('');
    expect(cockpitProject.read()).toBeNull();
  });

  it('reads null and refuses the write under blocked storage', () => {
    const { cockpitProject } = createLegacyStorage(() => blockedBackend());
    expect(cockpitProject.read()).toBeNull();
    expect(cockpitProject.write('x')).toBe(false);
  });
});

describe('goal family (cargento.projectGoal.v1:)', () => {
  it('keys on the encoded label', () => {
    expect(goalKey('a b/é')).toBe('cargento.projectGoal.v1:a%20b%2F%C3%A9');
  });

  it('saves the trimmed text raw, with no storage-side length bound', () => {
    const backend = fakeBackend();
    const { goal } = createLegacyStorage(() => backend);
    expect(GOAL_EDITOR_MAX_UTF16).toBe(500);
    expect(goal.save('p', '  ship it  ')).toBe('saved');
    expect(backend.data.get(goalKey('p'))).toBe('ship it');
    const long = 'g'.repeat(900);
    goal.save('q', long);
    expect(backend.data.get(goalKey('q'))).toBe(long);
    expect(createLegacyStorage(() => backend).goal.read('q')).toHaveLength(900);
  });

  it('refuses an empty goal and writes nothing', () => {
    const backend = fakeBackend();
    expect(createLegacyStorage(() => backend).goal.save('p', '  \n ')).toBe('empty');
    expect(backend.writes).toEqual([]);
  });

  it('reads a missing goal as empty and the draft before storage', () => {
    const backend = fakeBackend({ [goalKey('p')]: 'stored' });
    const { goal } = createLegacyStorage(() => backend);
    expect(goal.read('missing')).toBe('');
    expect(goal.read('p')).toBe('stored');
    goal.setDraft('p', 'half typed');
    expect(goal.read('p')).toBe('half typed');
  });

  it('clears by removing the key and dropping the draft', () => {
    const backend = fakeBackend({ [goalKey('p')]: 'stored' });
    const { goal } = createLegacyStorage(() => backend);
    goal.setDraft('p', 'draft');
    expect(goal.clear('p')).toBe('cleared');
    expect(backend.data.has(goalKey('p'))).toBe(false);
    expect(goal.read('p')).toBe('');
  });

  it('reports blocked storage instead of pretending to have saved, and keeps the draft on a failed clear', () => {
    const { goal } = createLegacyStorage(() => readOnlyBackend({ [goalKey('p')]: 'stored' }));
    expect(goal.save('p', 'new')).toBe('unavailable');
    goal.setDraft('p', 'typed');
    expect(goal.clear('p')).toBe('unavailable');
    expect(goal.read('p')).toBe('typed');
    expect(createLegacyStorage(() => blockedBackend()).goal.read('p')).toBe('');
  });
});

describe('usage family (cargento.projectUsage.v1)', () => {
  it('floors, keeps positives only and clamps at 999999', () => {
    const raw = JSON.stringify({
      a: 5.9,
      b: '7',
      c: 0,
      d: -3,
      e: 'abc',
      f: 1e9,
      g: true,
      h: null,
      '': 4,
      i: [3],
    });
    expect(decodeUsage(raw)).toEqual({ a: 5, b: 7, f: 999999, g: 1, i: 3 });
  });

  it('loads the first two hundred entries only', () => {
    const entries = Object.fromEntries(Array.from({ length: 250 }, (_, index) => [`k${index}`, index + 1]));
    const loaded = decodeUsage(JSON.stringify(entries));
    expect(Object.keys(loaded)).toHaveLength(200);
    expect(loaded['k199']).toBe(200);
    expect(loaded['k200']).toBeUndefined();
  });

  it('counts an empty-key row against the cap before dropping it, as the legacy slice does', () => {
    const entries: Record<string, number> = { '': 1 };
    for (let index = 0; index < 200; index += 1) entries[`k${index}`] = 1;
    expect(Object.keys(decodeUsage(JSON.stringify(entries)))).toHaveLength(199);
  });

  it('reads corrupt, scalar, array and missing values as empty', () => {
    for (const raw of ['{', '5', '[1,2]', 'null', '"x"', null, '']) {
      expect(decodeUsage(raw)).toEqual({});
    }
  });

  it('increments, clamps and writes the whole object, without bounding its size', () => {
    const entries = Object.fromEntries(Array.from({ length: 200 }, (_, index) => [`k${index}`, 1]));
    const backend = fakeBackend({ 'cargento.projectUsage.v1': JSON.stringify(entries) });
    const { usage } = createLegacyStorage(() => backend);
    usage.record('fresh');
    usage.record('fresh');
    const stored = JSON.parse(backend.data.get('cargento.projectUsage.v1') ?? '{}') as Record<string, number>;
    expect(Object.keys(stored)).toHaveLength(201);
    expect(stored['fresh']).toBe(2);
    expect(usage.counts()['fresh']).toBe(2);
  });

  it('never exceeds 999999', () => {
    const backend = fakeBackend({ 'cargento.projectUsage.v1': '{"a":999999}' });
    const { usage } = createLegacyStorage(() => backend);
    expect(usage.record('a')['a']).toBe(999999);
  });

  it('keeps counting in memory when storage is blocked or full', () => {
    expect(createLegacyStorage(() => blockedBackend()).usage.record('a')).toEqual({ a: 1 });
    const { usage } = createLegacyStorage(() => readOnlyBackend());
    usage.record('a');
    expect(usage.record('a')).toEqual({ a: 2 });
  });

  it('returns snapshots the caller cannot use to mutate the store', () => {
    const { usage } = createLegacyStorage(() => fakeBackend());
    const first = usage.record('a');
    usage.record('a');
    expect(first).toEqual({ a: 1 });
  });
});
