import { expect, it, vi } from 'vitest';
import { createApiClient } from '../api/client';
import { contextKey } from '../api/identity';
import { createBoardStore } from '../store/board';
import { createRecordLoader, RESOLVE_MAX_PAGES } from './record';

it('a reader leaving a session aborts its request even when the network ignores cancellation', async () => {
  let signal: AbortSignal | null | undefined;
  const client = createApiClient({
    fetch: (_url, init) => {
      signal = init?.signal;
      return new Promise<Response>(() => undefined);
    },
  });
  const store = createBoardStore({ now: () => 0 });
  const loader = createRecordLoader({ client, store });
  const scope = { projectKey: '/one', focus: { harness: 'claude', sid: 'same' } };
  const leave = loader.open(scope);
  expect(signal?.aborted).toBe(false);
  leave();
  await Promise.resolve();
  expect(signal?.aborted).toBe(true);
  expect(store.getSnapshot().records.has(contextKey(scope.projectKey, scope.focus))).toBe(false);
  loader.dispose();
});

it('a reader opening identical session ids in different projects keeps their pages apart', async () => {
  const client = createApiClient({
    fetch: (url) => {
      const query = new URLSearchParams(url.split('?')[1]);
      return Promise.resolve(
        new Response(
          JSON.stringify({
            session: { harness: 'claude', sid: 'same' },
            entries: [],
            state: 'ok',
            next: query.get('project'),
            reached_start: false,
            bound: null,
            scanned_bytes: 0,
            kinds: ['user_message', 'agent_message'],
          }),
        ),
      );
    },
  });
  const store = createBoardStore({ now: () => 0 });
  const loader = createRecordLoader({ client, store });
  const focus = { harness: 'claude', sid: 'same' };
  const first = loader.open({ projectKey: '/one', focus });
  const second = loader.open({ projectKey: '/two', focus });
  await loader.more({ projectKey: '/one', focus });
  await loader.more({ projectKey: '/two', focus });
  expect(store.getSnapshot().records.get(contextKey('/one', focus))?.next).toBe('/one');
  expect(store.getSnapshot().records.get(contextKey('/two', focus))?.next).toBe('/two');
  first();
  await Promise.resolve();
  expect(store.getSnapshot().records.size).toBe(1);
  second();
  loader.dispose();
});

/* The reader's own finished press may read older pages for what its reading cites. Each test serves a record
   of `total` pages, fifty entries apiece, newest first, and counts what the loader asks for. */
function servedRecord(options: { total: number; fail?: number }) {
  const asked: (string | null)[] = [];
  const client = createApiClient({
    fetch: (url) => {
      const before = new URLSearchParams(url.split('?')[1]).get('before');
      asked.push(before);
      const page = before ? Number(before.slice(1)) : 0;
      if (options.fail === page) return Promise.resolve(new Response('{}', { status: 500 }));
      const entries = Array.from({ length: 2 }, (_, index) => ({
        fact_id: `f${String(page)}-${String(index)}`,
        at: 1000 - page * 10 - index,
      }));
      const last = page === options.total - 1;
      return Promise.resolve(
        new Response(
          JSON.stringify({
            session: { harness: 'claude', sid: 'same' },
            entries,
            state: 'ok',
            next: last ? null : `p${String(page + 1)}`,
            reached_start: last,
            bound: null,
            scanned_bytes: 0,
            kinds: ['user_message', 'agent_message'],
          }),
        ),
      );
    },
  });
  const store = createBoardStore({ now: () => 0 });
  const loader = createRecordLoader({ client, store });
  const scope = { projectKey: '/one', focus: { harness: 'claude', sid: 'same' } };
  const record = () => store.getSnapshot().records.get(contextKey(scope.projectKey, scope.focus));
  return { asked, loader, scope, record };
}
const holds =
  (id: string) => (snapshot: ReturnType<ReturnType<typeof createBoardStore>['getSnapshot']>) =>
    [...snapshot.records.values()].some((entry) =>
      entry.entries.some((fact) => fact.fact_id === id),
    );

it('resolving reads older pages until the test holds, and not one more', async () => {
  const { asked, loader, scope, record } = servedRecord({ total: 10 });
  loader.open(scope);
  await loader.resolve(scope, holds('f3-0'));
  expect(asked).toEqual([null, 'p1', 'p2', 'p3']);
  expect(record()?.pages).toBe(4);
  loader.dispose();
});

it('resolving stops at the start of the record', async () => {
  const { asked, loader, scope, record } = servedRecord({ total: 3 });
  loader.open(scope);
  await loader.resolve(scope, () => false);
  expect(asked).toHaveLength(3);
  expect(record()?.reachedStart).toBe(true);
  loader.dispose();
});

it('resolving stops after its page cap, so a citation the record never held cannot walk the whole history', async () => {
  const { asked, loader, scope } = servedRecord({ total: 500 });
  loader.open(scope);
  await loader.resolve(scope, () => false);
  expect(asked).toHaveLength(RESOLVE_MAX_PAGES + 1);
  loader.dispose();
});

it('resolving ends on a page that fails, and leaves the record for the reader to continue', async () => {
  const { asked, loader, scope, record } = servedRecord({ total: 10, fail: 2 });
  loader.open(scope);
  await loader.resolve(scope, () => false);
  expect(asked).toEqual([null, 'p1', 'p2']);
  expect(record()?.status).toBe('error');
  loader.dispose();
});

it('resolving ends when the reader leaves the session', async () => {
  const { asked, loader, scope, record } = servedRecord({ total: 10 });
  const leave = loader.open(scope);
  const run = loader.resolve(scope, () => false);
  leave();
  await run;
  expect(asked.length).toBeLessThan(3);
  expect(record()).toBeUndefined();
  loader.dispose();
});

it('resolving with no opening reads nothing, and a second press shares the run and replaces its test', async () => {
  const idle = servedRecord({ total: 10 });
  await idle.loader.resolve(idle.scope, () => false);
  expect(idle.asked).toEqual([]);
  idle.loader.dispose();
  const { asked, loader, scope } = servedRecord({ total: 10 });
  loader.open(scope);
  const first = loader.resolve(scope, () => false);
  const second = loader.resolve(scope, holds('f2-0'));
  expect(second).toBe(first);
  await first;
  expect(asked).toEqual([null, 'p1', 'p2']);
  loader.dispose();
});

/* A record that grows while the page is open. Entries are kept oldest first and a page is cut from the newest
   end. A cursor names how many entries lie before its page, so an append never moves an older page, which is
   the server's own rule for its byte cursors. */
function liveRecord(initial: number, pageSize = 2) {
  const entries: { fact_id: string; at: number }[] = [];
  const grow = (count: number) => {
    for (let i = 0; i < count; i += 1)
      entries.push({ fact_id: `m${String(entries.length)}`, at: 1000 + entries.length });
  };
  grow(initial);
  const asked: (string | null)[] = [];
  const state = {
    fail: false,
    hold: null as null | (() => void),
    onAsk: null as null | ((count: number) => void),
    holdOlder: null as null | string,
    releaseOlder: null as null | (() => void),
  };
  const client = createApiClient({
    fetch: (url) => {
      const before = new URLSearchParams(url.split('?')[1]).get('before');
      asked.push(before);
      state.onAsk?.(asked.length);
      if (state.fail) return Promise.resolve(new Response('{}', { status: 500 }));
      const end = before === null ? entries.length : Number(before);
      const start = Math.max(0, end - pageSize);
      const body = new Response(
        JSON.stringify({
          session: { harness: 'claude', sid: 'same' },
          entries: entries.slice(start, end).reverse(),
          state: 'ok',
          next: start === 0 ? null : String(start),
          reached_start: start === 0,
          bound: null,
          scanned_bytes: 0,
          kinds: ['user_message', 'agent_message'],
        }),
      );
      if (state.holdOlder !== null && before === state.holdOlder)
        return new Promise<Response>((resolve) => {
          state.releaseOlder = () => resolve(body);
        });
      if (!state.hold) return Promise.resolve(body);
      return new Promise<Response>((resolve) => {
        state.hold = () => resolve(body);
      });
    },
  });
  const store = createBoardStore({ now: () => 0 });
  const loader = createRecordLoader({ client, store });
  const scope = { projectKey: '/one', focus: { harness: 'claude', sid: 'same' } };
  const record = () => store.getSnapshot().records.get(contextKey(scope.projectKey, scope.focus));
  const ids = () => record()?.entries.map((fact) => fact.fact_id);
  const opened = async () => {
    const leave = loader.open(scope);
    await vi.waitFor(() => expect(record()?.status).toBe('loaded'));
    return leave;
  };
  return { asked, grow, loader, scope, record, ids, opened, state, store };
}

it('a refresh adds what arrived after the opening and leaves the older cursor where it was', async () => {
  const { asked, grow, loader, scope, record, ids, opened } = liveRecord(6);
  await opened();
  expect(ids()).toEqual(['m5', 'm4']);
  const cursor = record()?.next;
  await loader.refresh(scope, 1);
  expect(asked).toEqual([null]);
  grow(1);
  await loader.refresh(scope, 2);
  expect(ids()).toEqual(['m6', 'm5', 'm4']);
  expect(record()?.next).toBe(cursor);
  expect(record()?.pages).toBe(1);
  expect(record()?.status).toBe('loaded');
  loader.dispose();
});

it('a refresh keeps the older pages the reader loaded, and reads nothing for a stamp it has seen', async () => {
  const { asked, grow, loader, scope, record, ids, opened } = liveRecord(6);
  await opened();
  await loader.refresh(scope, 1);
  await loader.more(scope);
  expect(ids()).toEqual(['m5', 'm4', 'm3', 'm2']);
  grow(1);
  await loader.refresh(scope, 2);
  await loader.refresh(scope, 2);
  expect(ids()).toEqual(['m6', 'm5', 'm4', 'm3', 'm2']);
  expect(asked).toEqual([null, '4', null]);
  expect(record()?.pages).toBe(2);
  loader.dispose();
});

it('a refresh reads back through a burst until it meets what the record already holds', async () => {
  const { asked, grow, loader, scope, ids, opened } = liveRecord(6);
  await opened();
  await loader.refresh(scope, 1);
  grow(5);
  await loader.refresh(scope, 2);
  expect(ids()).toEqual(['m10', 'm9', 'm8', 'm7', 'm6', 'm5', 'm4']);
  expect(asked).toEqual([null, null, '9', '7']);
  loader.dispose();
});

it('a refresh that cannot meet what the record holds starts again from the newest entries and says so', async () => {
  const { grow, loader, scope, record, ids, opened } = liveRecord(4);
  await opened();
  await loader.refresh(scope, 1);
  grow(100);
  await loader.refresh(scope, 2);
  expect(ids()).toHaveLength(RESOLVE_MAX_PAGES * 2);
  expect(ids()?.[0]).toBe('m103');
  expect(record()?.restarted).toBe(true);
  expect(record()?.reachedStart).toBe(false);
  expect(record()?.pages).toBe(1);
  loader.dispose();
});

it('a refresh that fails changes nothing, and the next stamp tries again', async () => {
  const { grow, loader, scope, record, ids, opened, state } = liveRecord(6);
  await opened();
  await loader.refresh(scope, 1);
  grow(1);
  state.fail = true;
  await loader.refresh(scope, 2);
  expect(ids()).toEqual(['m5', 'm4']);
  expect(record()?.status).toBe('loaded');
  expect(record()?.error).toBeNull();
  state.fail = false;
  await loader.refresh(scope, 3);
  expect(ids()).toEqual(['m6', 'm5', 'm4']);
  loader.dispose();
});

it('a refresh asked while the opening page is loading waits for it, then reads the newest page once', async () => {
  const { asked, grow, loader, scope, ids } = liveRecord(6);
  const leave = loader.open(scope);
  await loader.refresh(scope, 1);
  grow(1);
  await loader.refresh(scope, 2);
  expect(asked).toEqual([null, null]);
  expect(ids()).toEqual(['m6', 'm5', 'm4']);
  leave();
  loader.dispose();
});

it('a reader leaving the session aborts a refresh in flight and no record is written back', async () => {
  const { asked, grow, loader, scope, store, opened, state } = liveRecord(6);
  const leave = await opened();
  await loader.refresh(scope, 1);
  grow(1);
  state.hold = () => undefined;
  const refreshing = loader.refresh(scope, 2);
  await vi.waitFor(() => expect(asked).toHaveLength(2));
  leave();
  await Promise.resolve();
  state.hold?.();
  await refreshing;
  expect(store.getSnapshot().records.size).toBe(0);
  loader.dispose();
});

it('refreshes asked while one is running share one more read', async () => {
  const { asked, grow, loader, scope, ids, opened, state } = liveRecord(6);
  await opened();
  await loader.refresh(scope, 1);
  grow(1);
  state.hold = () => undefined;
  const first = loader.refresh(scope, 2);
  await vi.waitFor(() => expect(asked).toHaveLength(2));
  const release = state.hold;
  state.hold = null;
  grow(1);
  const second = loader.refresh(scope, 3);
  const third = loader.refresh(scope, 4);
  release?.();
  await Promise.all([first, second, third]);
  expect(asked).toEqual([null, null, null]);
  expect(ids()).toEqual(['m7', 'm6', 'm5', 'm4']);
  loader.dispose();
});

it('an entry the record held once is held until the reader leaves, however the record grows', async () => {
  const { grow, loader, scope, ids, opened } = liveRecord(6);
  await opened();
  await loader.refresh(scope, 1);
  const seen = new Set(ids());
  for (let stamp = 2; stamp < 12; stamp += 1) {
    grow(stamp % 3);
    await loader.refresh(scope, stamp);
    for (const id of seen) expect(ids()).toContain(id);
    for (const id of ids() ?? []) seen.add(id);
  }
  loader.dispose();
});

it('a refresh still merges after an older page failed, and leaves the failure for the reader to retry', async () => {
  const { grow, loader, scope, record, ids, opened, state } = liveRecord(6);
  await opened();
  await loader.refresh(scope, 1);
  state.fail = true;
  await loader.more(scope);
  expect(record()?.status).toBe('error');
  state.fail = false;
  grow(1);
  await loader.refresh(scope, 2);
  expect(ids()).toEqual(['m6', 'm5', 'm4']);
  expect(record()?.status).toBe('error');
  expect(record()?.next).toBe('4');
  loader.dispose();
});

it('starting again from the newest entries abandons an older page asked for with the old cursor', async () => {
  const { grow, loader, scope, record, ids, opened, state } = liveRecord(4);
  await opened();
  await loader.refresh(scope, 1);
  grow(100);
  let older: Promise<void> | undefined;
  // The reader presses Show more while the refresh is still walking back through the burst.
  state.holdOlder = '2';
  state.onAsk = (count) => {
    if (count === 3) older = loader.more(scope);
  };
  await loader.refresh(scope, 2);
  state.releaseOlder?.();
  await older;
  expect(record()?.restarted).toBe(true);
  expect(ids()).toHaveLength(RESOLVE_MAX_PAGES * 2);
  expect(ids()).not.toContain('m1');
  loader.dispose();
});
