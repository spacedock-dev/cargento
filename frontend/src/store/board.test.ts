import { describe, expect, it, vi } from 'vitest';
import type { PayloadData } from '../api/types';
import { createBoardStore } from './board';

const row = (harness: string, sid: string) => ({ harness, sid });
const data = (build: string, ...sessions: ReturnType<typeof row>[]): PayloadData => ({ generated: 10, build, sessions });

function store() {
  let now = 5_000;
  const board = createBoardStore({ now: () => now });
  return { board, tick: (ms: number) => (now += ms) };
}

describe('board store contract for useSyncExternalStore', () => {
  it('starts empty and keeps one snapshot object until something changes', () => {
    const { board } = store();
    const first = board.getSnapshot();
    expect(first.data).toBeNull();
    expect(first.failures).toBe(0);
    expect(board.getSnapshot()).toBe(first);
    board.setManualRefreshing(false);
    board.setPending([]);
    expect(board.getSnapshot()).toBe(first);
  });

  it('notifies subscribers once per change and stops after unsubscribe', () => {
    const { board } = store();
    const listener = vi.fn();
    const off = board.subscribe(listener);
    board.setManualRefreshing(true);
    board.setManualRefreshing(true);
    expect(listener).toHaveBeenCalledOnce();
    off();
    board.setManualRefreshing(false);
    expect(listener).toHaveBeenCalledOnce();
    expect(board.subscriberCount()).toBe(0);
  });

  it('never mutates a snapshot a subscriber already holds', () => {
    const { board } = store();
    const before = board.getSnapshot();
    board.acceptData(data('a', row('claude', 's')), '1.1');
    expect(before.data).toBeNull();
    expect(board.getSnapshot()).not.toBe(before);
  });
});

describe('listener isolation', () => {
  it('lets one throwing subscriber neither throw out of the store nor starve the others', () => {
    const errors: unknown[] = [];
    const board = createBoardStore({ now: () => 1, reportError: (error) => errors.push(error) });
    const late = vi.fn();
    board.subscribe(() => {
      throw new Error('subscriber bug');
    });
    board.subscribe(late);
    expect(() => board.acceptData(data('a'), '1.1')).not.toThrow();
    expect(late).toHaveBeenCalledOnce();
    expect(board.getSnapshot().data).not.toBeNull();
    expect(errors).toHaveLength(1);
    expect((errors[0] as Error).message).toBe('subscriber bug');
  });

  it('bounds how many errors it reports while still counting them, and never throws from a reporter that throws', () => {
    const errors: unknown[] = [];
    const board = createBoardStore({
      now: () => 1,
      reportError: (error) => {
        errors.push(error);
        throw new Error('reporter bug');
      },
    });
    board.subscribe(() => {
      throw new Error('subscriber bug');
    });
    for (let change = 0; change < 40; change += 1) board.setPending([String(change)]);
    expect(errors.length).toBeLessThanOrEqual(10);
    expect(errors.length).toBeGreaterThan(0);
    expect(board.listenerErrorCount()).toBe(40);
  });
});

describe('accepted data and failures', () => {
  it('accepts a body with its revision and clears the failure state', () => {
    const { board, tick } = store();
    board.recordFailure({ kind: 'network-error' });
    tick(10);
    board.acceptData(data('a', row('claude', 's')), '1.4');
    const snapshot = board.getSnapshot();
    expect(snapshot.data?.sessions).toHaveLength(1);
    expect(snapshot.revision).toBe('1.4');
    expect(snapshot.failures).toBe(0);
    expect(snapshot.lastFailure).toBeNull();
    expect(snapshot.lastSuccessAt).toBe(5_010);
    expect(snapshot.acceptedCount).toBe(1);
  });

  it('retains the last accepted data on a failed read and counts the failure', () => {
    const { board } = store();
    board.acceptData(data('a', row('claude', 's')), '1.4');
    const accepted = board.getSnapshot().data;
    board.recordFailure({ kind: 'http-error', status: 503 });
    board.recordFailure({ kind: 'http-error', status: 403 });
    const snapshot = board.getSnapshot();
    expect(snapshot.data).toBe(accepted);
    expect(snapshot.failures).toBe(2);
    expect(snapshot.lastFailure).toEqual({ kind: 'http-error', status: 403 });
    expect(snapshot.revision).toBe('1.4');
  });

  it('remembers the first non-empty build for the life of the document', () => {
    const { board } = store();
    board.acceptData({ generated: 1 }, '');
    expect(board.getSnapshot().firstBuild).toBe('');
    board.acceptData(data('a'), '');
    board.acceptData(data('b'), '');
    expect(board.getSnapshot().firstBuild).toBe('a');
  });
});

describe('context entries and observer requests', () => {
  it('replaces an entry with a fresh object and keeps the others untouched', () => {
    const { board } = store();
    board.setContext('p\n', { data: { observers: [] }, revision: 3, error: null });
    const first = board.getSnapshot().contexts.get('p\n');
    board.setContext('q\n', { data: null, revision: 3, error: null });
    expect(board.getSnapshot().contexts.get('p\n')).toBe(first);
    expect(board.getSnapshot().contexts.size).toBe(2);
  });

  it('tracks an in-flight explicit summary and its outcome per key', () => {
    const { board } = store();
    board.setObserverRequest('p\ns', true);
    expect(board.getSnapshot().observer.requests).toEqual(['p\ns']);
    board.setObserverRequest('p\ns', true);
    board.setObserverRequest('p\ns', false);
    board.setObserverState('p\ns', 'ready');
    expect(board.getSnapshot().observer.requests).toEqual([]);
    expect(board.getSnapshot().observer.states.get('p\ns')).toBe('ready');
  });

  it('holds the pending control keys as an immutable list', () => {
    const { board } = store();
    board.setPending(['a', 'b']);
    const first = board.getSnapshot();
    board.setPending(['a', 'b']);
    expect(board.getSnapshot()).toBe(first);
    board.setPending(['a']);
    expect(board.getSnapshot().pending).toEqual(['a']);
    expect(first.pending).toEqual(['a', 'b']);
  });
});
