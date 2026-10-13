import { expect, it } from 'vitest';
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
