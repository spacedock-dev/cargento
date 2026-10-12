import type { ApiClient } from '../api/client';
import { compatSessKey, contextKey } from '../api/identity';
import type { SessionIdentity } from '../api/types';
import { EMPTY_RECORD, type BoardStore } from '../store/board';

export const RECORD_PAGE_SIZE = 50;
export interface RecordScope {
  readonly projectKey: string;
  readonly focus: SessionIdentity;
}

// docs/design-reader-state.md#the-inventory owns this short lifetime. No subscription loads pages.
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
        opening = { holders: 0, request: null, pending: null };
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
