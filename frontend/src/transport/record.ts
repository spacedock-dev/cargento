import type { ApiClient } from '../api/client';
import { compatSessKey, contextKey } from '../api/identity';
import type { SessionIdentity } from '../api/types';
import { EMPTY_RECORD, type BoardSnapshot, type BoardStore } from '../store/board';

export const RECORD_PAGE_SIZE = 50;
/* The most pages one finished press may read to find what its reading cites: 1,000 entries at fifty a page.
   Past it the reader's own Show more continues, so a reading that cites an id the record never held cannot
   walk a session's whole history. docs/design-reader-state.md#the-inventory owns this exception. */
export const RESOLVE_MAX_PAGES = 20;
export interface RecordScope {
  readonly projectKey: string;
  readonly focus: SessionIdentity;
}

// docs/design-reader-state.md#the-inventory owns this short lifetime. No subscription loads pages: the
// reader's Show more does, and so does `resolve`, once, for the reading their own press just finished.
export function createRecordLoader({
  client,
  store,
}: {
  readonly client: Pick<ApiClient, 'getSessionRecord'>;
  readonly store: BoardStore;
}) {
  interface Opening {
    holders: number;
    request: AbortController | null;
    pending: Promise<void> | null;
    /* The one resolution this opening runs, with the test it stops on. A second press while it runs
       replaces the test and shares the run, so two presses never read two sets of pages. */
    resolution: { until: (snapshot: BoardSnapshot) => boolean; run: Promise<void> } | null;
  }
  const openings = new Map<string, Opening>();
  let disposed = false;

  function read(scope: RecordScope, opening: Opening): Promise<void> {
    const key = contextKey(scope.projectKey, scope.focus);
    if (disposed || openings.get(key) !== opening) return Promise.resolve();
    if (opening.pending) return opening.pending;
    const previous = store.getSnapshot().records.get(key) ?? EMPTY_RECORD;
    if (previous.reachedStart || previous.status === 'unsupported') return Promise.resolve();
    const owned = new AbortController();
    opening.request = owned;
    store.setRecord(key, { ...previous, status: 'loading', error: null });
    const current = () => !disposed && !owned.signal.aborted && openings.get(key) === opening;
    opening.pending = (async () => {
      let before = previous.next;
      for (let attempt = 0; attempt < 2; attempt += 1) {
        const result = await client.getSessionRecord({
          project: scope.projectKey,
          session: compatSessKey(scope.focus),
          limit: RECORD_PAGE_SIZE,
          ...(before ? { before } : {}),
          signal: owned.signal,
        });
        if (!current() || result.kind === 'aborted') return;
        const held = store.getSnapshot().records.get(key) ?? EMPTY_RECORD;
        if (result.kind !== 'ok') {
          store.setRecord(key, { ...held, status: 'error', error: result });
          return;
        }
        const body = result.body;
        if (
          !['ok', 'stale', 'unsupported', 'unavailable'].includes(body.state) ||
          !Array.isArray(body.entries) ||
          body.session?.harness !== scope.focus.harness ||
          body.session.sid !== scope.focus.sid
        ) {
          store.setRecord(key, {
            ...held,
            status: 'error',
            error: { kind: 'malformed', status: result.status },
          });
          return;
        }
        if (body.state === 'stale') {
          store.setRecord(key, {
            ...EMPTY_RECORD,
            status: 'stale',
            restarted: true,
            error: attempt === 1 ? { kind: 'stale' } : null,
          });
          if (attempt === 0) {
            before = null;
            continue;
          }
          return;
        }
        if (body.state === 'unsupported' || body.state === 'unavailable') {
          store.setRecord(key, {
            ...held,
            status: body.state === 'unsupported' ? 'unsupported' : 'error',
            error: body.state === 'unavailable' ? { kind: 'unavailable' } : null,
          });
          return;
        }
        const merged = new Map(held.entries.map((fact) => [fact.fact_id, fact]));
        for (const fact of body.entries) merged.set(fact.fact_id, fact);
        store.setRecord(key, {
          entries: [...merged.values()].sort(
            (a, b) => b.at - a.at || (a.fact_id < b.fact_id ? -1 : a.fact_id > b.fact_id ? 1 : 0),
          ),
          next: body.next,
          reachedStart: body.reached_start,
          bound: body.bound,
          scannedBytes: body.scanned_bytes,
          status: 'loaded',
          error: null,
          pages: held.pages + 1,
          restarted: held.restarted,
        });
        return;
      }
    })().finally(() => {
      if (opening.request === owned) {
        opening.request = null;
        opening.pending = null;
      }
    });
    return opening.pending;
  }

  /* Reads older pages until `until` holds, the record reaches its start, a page makes no progress, or the page
     cap is spent. Only this opening's own pages are read, so a reader who leaves the session ends it at the
     next page: `close` removes the opening and aborts the request in flight. */
  function resolve(
    scope: RecordScope,
    until: (snapshot: BoardSnapshot) => boolean,
    opening: Opening,
  ): Promise<void> {
    if (opening.resolution) {
      opening.resolution.until = until;
      return opening.resolution.run;
    }
    const key = contextKey(scope.projectKey, scope.focus);
    const held = { until, run: Promise.resolve() };
    held.run = (async () => {
      for (let step = 0; step < RESOLVE_MAX_PAGES; step += 1) {
        // The newest page may still be in flight; it is the first page, not one this loop asks for.
        if (opening.pending) await opening.pending;
        if (disposed || openings.get(key) !== opening) return;
        const snapshot = store.getSnapshot();
        const record = snapshot.records.get(key) ?? EMPTY_RECORD;
        if (record.status !== 'loaded' || record.reachedStart || held.until(snapshot)) return;
        await read(scope, opening);
        // A page that moved nothing (an error, a leave, a record that reset) ends the loop.
        if ((store.getSnapshot().records.get(key) ?? EMPTY_RECORD).pages === record.pages) return;
      }
    })().finally(() => {
      if (opening.resolution === held) opening.resolution = null;
    });
    opening.resolution = held;
    return held.run;
  }

  function close(key: string, opening: Opening): void {
    if (openings.get(key) !== opening) return;
    openings.delete(key);
    opening.request?.abort();
    store.dropRecord(key);
  }

  return {
    open(scope: RecordScope): () => void {
      if (disposed) return () => undefined;
      const key = contextKey(scope.projectKey, scope.focus);
      let opening = openings.get(key);
      if (!opening) {
        opening = { holders: 0, request: null, pending: null, resolution: null };
        openings.set(key, opening);
        store.setRecord(key, EMPTY_RECORD);
        void read(scope, opening);
      }
      opening.holders += 1;
      const held = opening;
      let released = false;
      return () => {
        if (released) return;
        released = true;
        held.holders -= 1;
        // StrictMode's effect replay is the same opening; a real leave closes at this microtask.
        queueMicrotask(() => {
          if (held.holders === 0) close(key, held);
        });
      };
    },
    resolve(scope: RecordScope, until: (snapshot: BoardSnapshot) => boolean): Promise<void> {
      const opening = openings.get(contextKey(scope.projectKey, scope.focus));
      return opening ? resolve(scope, until, opening) : Promise.resolve();
    },
    more(scope: RecordScope): Promise<void> {
      const opening = openings.get(contextKey(scope.projectKey, scope.focus));
      return opening ? read(scope, opening) : Promise.resolve();
    },
    dispose(): void {
      disposed = true;
      for (const [key, opening] of openings) close(key, opening);
    },
  };
}
