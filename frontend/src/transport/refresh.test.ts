import { describe, expect, it, vi } from 'vitest';
import type { PayloadData } from '../api/types';
import { createRefreshController, type DataOutcome, type RefreshSink } from './refresh';
import { createRevisionMemo } from './revision';

interface Deferred<T> {
  readonly promise: Promise<T>;
  resolve(value: T): void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => (resolve = done));
  return { promise, resolve };
}

const flush = async () => {
  for (let turn = 0; turn < 8; turn += 1) await Promise.resolve();
};

const body = (generated: number): PayloadData => ({ generated, sessions: [] });
const ok = (generated: number, revision = ''): DataOutcome => ({
  kind: 'data',
  body: body(generated),
  revision,
});

function harness() {
  const fetches: { signal: AbortSignal; answer: Deferred<DataOutcome> }[] = [];
  const events: string[] = [];
  const paints: Deferred<undefined>[] = [];
  const sink: RefreshSink = {
    fetchData(signal) {
      const answer = deferred<DataOutcome>();
      fetches.push({ signal, answer });
      return answer.promise;
    },
    manualInFlight: (active) => events.push(`manual:${active}`),
    accepted: (data, revision) => events.push(`accepted:${String(data.generated)}@${revision}`),
    failed: (failure) => events.push(`failed:${failure.kind}`),
    paint(info) {
      events.push(
        `paint:${info.manual ? 'manual' : 'background'}:${info.accepted ? 'data' : 'failure'}`,
      );
      const gate = deferred<undefined>();
      paints.push(gate);
      return gate.promise;
    },
  };
  const revisions = createRevisionMemo();
  const controller = createRefreshController({ sink, revisions });
  const settleAll = async () => {
    await flush();
    for (const gate of paints) gate.resolve(undefined);
    await flush();
  };
  return { controller, fetches, events, paints, revisions, settleAll };
}

function track(promise: Promise<void>) {
  const state = { done: false };
  void promise.then(() => (state.done = true));
  return state;
}

describe('one refresh', () => {
  it('fetches once, accepts the body, advances the revision and paints', async () => {
    const h = harness();
    const done = track(h.controller.poll());
    expect(h.fetches).toHaveLength(1);
    h.fetches[0]?.answer.resolve(ok(1, '5.2'));
    await flush();
    expect(h.events).toEqual(['accepted:1@5.2', 'paint:background:data']);
    expect(h.revisions.get()).toBe('5.2');
    expect(done.done).toBe(false);
    await h.settleAll();
    expect(done.done).toBe(true);
  });

  it('separates acceptance from paint completion', async () => {
    const h = harness();
    const done = track(h.controller.refresh());
    h.fetches[0]?.answer.resolve(ok(1));
    await flush();
    expect(h.events).toContain('accepted:1@');
    expect(done.done).toBe(false);
    await h.settleAll();
    expect(done.done).toBe(true);
  });

  it('never regresses the remembered revision', async () => {
    const h = harness();
    h.revisions.advance('5.9');
    void h.controller.poll();
    h.fetches[0]?.answer.resolve(ok(1, '5.4'));
    await h.settleAll();
    expect(h.revisions.get()).toBe('5.9');
  });
});

describe('request identity and waiters', () => {
  it('drops the answer of a superseded poll and hands its waiter to the newer fetch', async () => {
    const h = harness();
    const first = track(h.controller.poll());
    const second = track(h.controller.poll());
    expect(h.fetches).toHaveLength(2);
    h.fetches[0]?.answer.resolve(ok(1));
    await h.settleAll();
    expect(h.events).toEqual([]);
    expect(first.done).toBe(false);
    h.fetches[1]?.answer.resolve(ok(2));
    await h.settleAll();
    expect(h.events).toEqual(['accepted:2@', 'paint:background:data']);
    expect(first.done).toBe(true);
    expect(second.done).toBe(true);
  });

  it('makes an awaited post-save refresh wait for a fetch that started after the call', async () => {
    const h = harness();
    void h.controller.poll();
    const saved = track(h.controller.refresh());
    expect(h.fetches).toHaveLength(2);
    h.fetches[0]?.answer.resolve(ok(1));
    await h.settleAll();
    expect(saved.done).toBe(false);
    expect(h.events).toEqual([]);
    h.fetches[1]?.answer.resolve(ok(2));
    await h.settleAll();
    expect(saved.done).toBe(true);
    expect(h.events).toEqual(['accepted:2@', 'paint:background:data']);
  });

  it('counts a failure only for the newest request', async () => {
    const h = harness();
    void h.controller.poll();
    void h.controller.poll();
    h.fetches[0]?.answer.resolve({ kind: 'failed', failure: { kind: 'network-error' } });
    await h.settleAll();
    expect(h.events).toEqual([]);
    h.fetches[1]?.answer.resolve({ kind: 'failed', failure: { kind: 'http-error', status: 503 } });
    await h.settleAll();
    expect(h.events).toEqual(['failed:http-error', 'paint:background:failure']);
  });

  it('keeps the previous board by calling failed instead of accepted', async () => {
    const h = harness();
    void h.controller.poll();
    h.fetches[0]?.answer.resolve({ kind: 'failed', failure: { kind: 'network-error' } });
    await h.settleAll();
    expect(h.events.some((event) => event.startsWith('accepted'))).toBe(false);
  });

  it('treats a body the sink cannot apply as a failed read', async () => {
    const h = harness();
    const throwing = createRefreshController({
      revisions: h.revisions,
      sink: {
        fetchData: () => Promise.resolve(ok(1)),
        manualInFlight: () => undefined,
        accepted: () => {
          throw new Error('cannot apply');
        },
        failed: (failure) => h.events.push(`failed:${failure.kind}`),
        paint: () => Promise.resolve(),
      },
    });
    await throwing.refresh();
    expect(h.events).toEqual(['failed:malformed']);
  });
});

describe('stream wakes', () => {
  it('starts a fetch at once when only a poll is out, superseding it', async () => {
    const h = harness();
    void h.controller.poll();
    h.controller.wake('5.1');
    expect(h.fetches).toHaveLength(2);
    h.fetches[0]?.answer.resolve(ok(1));
    await h.settleAll();
    expect(h.events).toEqual([]);
  });

  it('queues at most one follow-up behind active work, with the newest revision', async () => {
    const h = harness();
    void h.controller.refresh();
    h.controller.wake('5.2');
    h.controller.wake('5.3');
    h.controller.wake('5.1');
    expect(h.fetches).toHaveLength(1);
    h.fetches[0]?.answer.resolve(ok(1, '5.0'));
    await h.settleAll();
    expect(h.events).toEqual([]);
    expect(h.fetches).toHaveLength(2);
    h.fetches[1]?.answer.resolve(ok(2, '5.3'));
    await h.settleAll();
    expect(h.events).toEqual(['accepted:2@5.3', 'paint:background:data']);
    expect(h.fetches).toHaveLength(2);
  });

  it('absorbs a queued wake when the answer already carries its revision', async () => {
    const h = harness();
    void h.controller.refresh();
    h.controller.wake('5.3');
    h.fetches[0]?.answer.resolve(ok(1, '5.3'));
    await h.settleAll();
    expect(h.events).toEqual(['accepted:1@5.3', 'paint:background:data']);
    expect(h.fetches).toHaveLength(1);
  });

  it('absorbs a queued wake the answer is newer than', async () => {
    const h = harness();
    void h.controller.refresh();
    h.controller.wake('5.2');
    h.fetches[0]?.answer.resolve(ok(1, '5.4'));
    await h.settleAll();
    expect(h.fetches).toHaveLength(1);
    expect(h.events[0]).toBe('accepted:1@5.4');
  });

  it('does not absorb a wake for a newer revision than the answer carries', async () => {
    const h = harness();
    void h.controller.refresh();
    h.controller.wake('5.4');
    h.fetches[0]?.answer.resolve(ok(1, '5.3'));
    await h.settleAll();
    expect(h.events).toEqual([]);
    expect(h.fetches).toHaveLength(2);
  });

  it('does not absorb a wake when the answer carries no revision', async () => {
    const h = harness();
    void h.controller.refresh();
    h.controller.wake('5.1');
    h.fetches[0]?.answer.resolve(ok(1, ''));
    await h.settleAll();
    expect(h.fetches).toHaveLength(2);
  });

  it('answers the waiters of a refresh that was queued behind', async () => {
    const h = harness();
    void h.controller.refresh();
    h.controller.wake('5.2');
    const saved = track(h.controller.refresh());
    expect(h.fetches).toHaveLength(2);
    h.fetches[0]?.answer.resolve(ok(1));
    h.fetches[1]?.answer.resolve(ok(2));
    await h.settleAll();
    expect(saved.done).toBe(true);
  });
});

describe('manual refresh', () => {
  it('raises the in-flight flag for the call and ignores a second manual press', async () => {
    const h = harness();
    const first = track(h.controller.refresh({ manual: true }));
    expect(h.controller.manualInFlight()).toBe(true);
    const second = track(h.controller.refresh({ manual: true }));
    await flush();
    expect(second.done).toBe(true);
    expect(h.fetches).toHaveLength(1);
    h.fetches[0]?.answer.resolve(ok(1));
    await h.settleAll();
    expect(first.done).toBe(true);
    expect(h.controller.manualInFlight()).toBe(false);
    expect(h.events).toEqual(['manual:true', 'accepted:1@', 'manual:false', 'paint:manual:data']);
  });
});

describe('disposal', () => {
  it('aborts the owned fetch, drops its answer and releases every waiter', async () => {
    const h = harness();
    const waiting = track(h.controller.refresh());
    h.controller.dispose();
    expect(h.fetches[0]?.signal.aborted).toBe(true);
    h.fetches[0]?.answer.resolve(ok(1, '5.1'));
    await h.settleAll();
    expect(h.events).toEqual([]);
    expect(waiting.done).toBe(true);
    expect(h.revisions.get()).toBeNull();
  });

  it('starts nothing after disposal', async () => {
    const h = harness();
    h.controller.dispose();
    const done = track(h.controller.poll());
    h.controller.wake('5.1');
    await flush();
    expect(h.fetches).toHaveLength(0);
    expect(done.done).toBe(true);
  });

  it('is idempotent', () => {
    const h = harness();
    void h.controller.poll();
    h.controller.dispose();
    expect(() => h.controller.dispose()).not.toThrow();
  });

  it('lowers the manual flag when a disposed manual refresh settles', async () => {
    const h = harness();
    void h.controller.refresh({ manual: true });
    h.controller.dispose();
    h.fetches[0]?.answer.resolve({ kind: 'aborted' });
    await flush();
    expect(h.events).toEqual(['manual:true', 'manual:false']);
  });
});

describe('uses injected sink only', () => {
  it('calls fetchData once per started run', () => {
    const fetchData = vi.fn(() => new Promise<DataOutcome>(() => undefined));
    const controller = createRefreshController({
      revisions: createRevisionMemo(),
      sink: {
        fetchData,
        manualInFlight: vi.fn(),
        accepted: vi.fn(),
        failed: vi.fn(),
        paint: () => Promise.resolve(),
      },
    });
    void controller.poll();
    void controller.refresh();
    expect(fetchData).toHaveBeenCalledTimes(2);
  });
});
