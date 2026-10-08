import { describe, expect, it } from 'vitest';
import type { PayloadData } from '../api/types';
import { createBoardStore } from './board';
import {
  selectAsks,
  selectBuildState,
  selectContextRead,
  selectContextState,
  selectDataStatus,
  selectHarnessSources,
  selectObserverRequest,
  selectSession,
  selectSessions,
} from './selectors';

function board() {
  return createBoardStore({ now: () => 1 });
}

describe('data status keeps unread, failed and empty distinct', () => {
  it('walks unread -> ready -> stale and unavailable', () => {
    const empty = board();
    expect(selectDataStatus(empty.getSnapshot())).toBe('unread');
    empty.recordFailure({ kind: 'network-error' });
    expect(selectDataStatus(empty.getSnapshot())).toBe('unavailable');

    const loaded = board();
    loaded.acceptData({ generated: 1, sessions: [] }, '1.1');
    expect(selectDataStatus(loaded.getSnapshot())).toBe('ready');
    loaded.recordFailure({ kind: 'http-error', status: 503 });
    expect(selectDataStatus(loaded.getSnapshot())).toBe('stale');
    loaded.acceptData({ generated: 2, sessions: [] }, '1.2');
    expect(selectDataStatus(loaded.getSnapshot())).toBe('ready');
  });
});

describe('sessions and asks', () => {
  it('distinguishes a missing sessions field from an empty one and drops non-object rows', () => {
    const missing = board();
    missing.acceptData({ generated: 1 }, '');
    expect(selectSessions(missing.getSnapshot())).toEqual({ present: false, rows: [] });
    const empty = board();
    empty.acceptData({ generated: 1, sessions: [] }, '');
    expect(selectSessions(empty.getSnapshot())).toEqual({ present: true, rows: [] });
    const dirty = board();
    dirty.acceptData(
      { sessions: [{ harness: 'claude', sid: 'a' }, null, 3] } as unknown as PayloadData,
      '',
    );
    expect(selectSessions(dirty.getSnapshot()).rows).toHaveLength(1);
    expect(selectSessions(board().getSnapshot())).toEqual({ present: false, rows: [] });
  });

  it('returns the same collection object while the accepted data is unchanged', () => {
    const b = board();
    b.acceptData(
      { sessions: [{ harness: 'claude', sid: 'a' }], asks: [] } as unknown as PayloadData,
      '',
    );
    const first = selectSessions(b.getSnapshot());
    b.setManualRefreshing(true);
    expect(selectSessions(b.getSnapshot())).toBe(first);
    expect(selectAsks(b.getSnapshot())).toBe(selectAsks(b.getSnapshot()));
    b.acceptData({ sessions: [{ harness: 'claude', sid: 'a' }] } as unknown as PayloadData, '');
    expect(selectSessions(b.getSnapshot())).not.toBe(first);
  });

  it('finds a session by the exact harness and sid pair, never by display id or sid alone', () => {
    const b = board();
    b.acceptData(
      {
        sessions: [
          { harness: 'claude', sid: 'same', session: 'same' },
          { harness: 'codex', sid: 'same', session: 'same' },
        ],
      } as unknown as PayloadData,
      '',
    );
    const snapshot = b.getSnapshot();
    expect(selectSession(snapshot, { harness: 'codex', sid: 'same' })?.harness).toBe('codex');
    expect(selectSession(snapshot, { harness: 'claude', sid: 'same' })?.harness).toBe('claude');
    expect(selectSession(snapshot, { harness: 'gemini', sid: 'same' })).toBeNull();
    expect(selectSession(snapshot, { harness: 'claude', sid: 'sam' })).toBeNull();
  });
});

describe('harness source availability stays distinct from empty data', () => {
  it('keeps discovered, undiscovered, errored and unstated apart', () => {
    const b = board();
    b.acceptData(
      {
        generated: 1,
        sessions: [],
        harnesses: [
          { key: 'claude', discovered: true },
          { key: 'codex', discovered: false },
          { key: 'pi', discovered: true, error: 'OSError: denied' },
          { key: 'agy' },
        ],
      },
      '',
    );
    expect(selectHarnessSources(b.getSnapshot())).toEqual({
      present: true,
      rows: [
        { key: 'claude', label: null, discovered: true, error: null },
        { key: 'codex', label: null, discovered: false, error: null },
        { key: 'pi', label: null, discovered: true, error: 'OSError: denied' },
        { key: 'agy', label: null, discovered: null, error: null },
      ],
    });
    expect(selectHarnessSources(board().getSnapshot()).present).toBe(false);
  });
});

describe('build state', () => {
  it('reports reload-required only when a later non-empty build differs', () => {
    const b = board();
    expect(selectBuildState(b.getSnapshot())).toBe('unknown');
    b.acceptData({ build: 'a' }, '');
    expect(selectBuildState(b.getSnapshot())).toBe('same');
    b.acceptData({}, '');
    expect(selectBuildState(b.getSnapshot())).toBe('unknown');
    b.acceptData({ build: 'b' }, '');
    expect(selectBuildState(b.getSnapshot())).toBe('reload-required');
  });
});

describe('the five context states', () => {
  const entry = (data: object | null, error: boolean) => ({
    data,
    revision: 1,
    error: error ? ({ kind: 'network-error' } as const) : null,
  });

  it('classifies absent, pending, ready, stale and unavailable', () => {
    const b = board();
    b.setContext('ready', entry({}, false));
    b.setContext('stale', entry({}, true));
    b.setContext('unavailable', entry(null, true));
    b.setContext('pending', entry(null, false));
    const snapshot = b.getSnapshot();
    expect(
      ['missing', 'pending', 'ready', 'stale', 'unavailable'].map((key) =>
        selectContextState(snapshot, key),
      ),
    ).toEqual(['absent', 'pending', 'ready', 'stale', 'unavailable']);
  });

  it('ranks the worst state of the focused and project entries and says whether rows show', () => {
    const b = board();
    b.setContext('p\n', entry({}, false));
    b.setContext('p\nclaude:s', entry({}, true));
    expect(selectContextRead(b.getSnapshot(), 'p', { harness: 'claude', sid: 's' })).toMatchObject({
      state: 'stale',
      shows: true,
    });
    expect(
      selectContextRead(b.getSnapshot(), 'p', { harness: 'claude', sid: 'other' }),
    ).toMatchObject({ state: 'absent', shows: false });
    b.setContext('p\ncodex:t', entry(null, true));
    expect(selectContextRead(b.getSnapshot(), 'p', { harness: 'codex', sid: 't' })).toMatchObject({
      state: 'unavailable',
      shows: false,
    });
    expect(selectContextRead(b.getSnapshot(), 'p', null)).toMatchObject({
      state: 'ready',
      shows: true,
    });
  });

  it('keeps one project’s scope from bleeding into another’s', () => {
    const b = board();
    b.setContext('p\ns', entry({}, false));
    expect(selectContextState(b.getSnapshot(), 'q\ns')).toBe('absent');
  });
});

describe('observer request selector', () => {
  it('reports pending and the last outcome per key', () => {
    const b = board();
    expect(selectObserverRequest(b.getSnapshot(), 'k')).toEqual({ pending: false, state: null });
    b.setObserverRequest('k', true);
    b.setObserverState('k', 'error');
    expect(selectObserverRequest(b.getSnapshot(), 'k')).toEqual({ pending: true, state: 'error' });
  });
});
