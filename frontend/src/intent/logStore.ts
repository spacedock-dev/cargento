import type { ApiClient } from '../api/client';
import type { Row } from '../observed';
import { isRecord } from '../observed';
import type { Clock } from '../transport/ports';
import type { LogLoad } from './logModel';

/* The retained half of the Intent log has its own route because its rows outlive the live board.
   Fetching it on every redraw would put up to 256 sessions of retained prose on the refresh loop, and
   keeping its first response forever was the opposite failure: after a discard, an open tab went on
   printing the withdrawn words although the route already answered with a text-free record.

   The dashboard carries a change token for the complete annotation and departure sources, including
   sessions that have left the board, and it carries no retained prose. A changed token removes the cached
   rows at once; a visible log fetches once; a hidden one waits until it is opened. The route's own answer
   carries a token for the same inputs its rows used, which can be ahead of the dashboard snapshot, so
   tokens are compared for equality and never ordered. A request generation stops a response started
   before an invalidation from restoring old words, and changes arriving during a request coalesce until
   it settles. A failed load shows that the store could not be read, withholds the old rows, and allows
   another attempt on a later redraw after twenty seconds, never on every one
   ([Intent log freshness](docs/design-reader-state.md#intent-log-freshness)). */

/* The legacy `NEXT_FALLBACK_POLL_MS`, which doubles as the request bound and the retry interval. */
export const LOG_REQUEST_MS = 20_000;

export interface LogSnapshot {
  readonly rows: readonly Row[] | null;
  readonly state: LogLoad;
  /* Whether a request is open. A settle that changed nothing the reader sees still has to wake the view:
     an invalidation that arrived while the request was open left the log "unread", and the slot the
     request held has just been released for the load that is now due. */
  readonly loading: boolean;
}

export interface IntentLogDeps {
  readonly client: Pick<ApiClient, 'getAnnotations'>;
  readonly clock: Clock;
}

export function createIntentLog(deps: IntentLogDeps) {
  const { client, clock } = deps;
  let rows: readonly Row[] | null = null;
  let state: LogLoad = 'unread';
  let enabled = false;
  let observedRevision: string | null = null;
  let revision: string | null = null;
  let generation = 0;
  let loading = false;
  let retryAt = 0;
  let snapshot: LogSnapshot = { rows, state, loading };
  const listeners = new Set<() => void>();

  function publish(): void {
    if (snapshot.rows === rows && snapshot.state === state && snapshot.loading === loading) return;
    snapshot = { rows, state, loading };
    for (const listener of [...listeners]) listener();
  }

  function invalidate(): void {
    generation += 1;
    rows = null;
    revision = null;
    state = 'unread';
    retryAt = 0;
    publish();
  }

  return {
    subscribe(listener: () => void): () => void {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    getSnapshot: (): LogSnapshot => snapshot,

    /* Called with every accepted board. The route can have read a newer store than the dashboard
       snapshot, so when the dashboard catches up those already-current rows need no second fetch. */
    sync(data: Row | null | undefined): void {
      const next = Boolean(data && data['annotate'] === true);
      const token =
        data && next && typeof data['intent_revision'] === 'string'
          ? data['intent_revision']
          : null;
      if (next === enabled && token === observedRevision) return;
      enabled = next;
      observedRevision = token;
      if (next && token && token === revision && state === 'read') return;
      invalidate();
    },

    /** A confirmed discard invalidates the initiating tab before its dashboard refresh finishes. */
    invalidate,

    /* Fetches once when the log is unread or failed and due for a retry. Never from a timer: a failed
       load is tried again on a later redraw, so a store that cannot be read costs one request per
       twenty seconds of redraws and not one per render. */
    load(): void {
      if (!enabled || loading || clock.now() < retryAt) return;
      const started = generation;
      const controller = new AbortController();
      const timeout = clock.setTimeout(() => controller.abort(), LOG_REQUEST_MS);
      loading = true;
      state = 'loading';
      publish();
      void client.getAnnotations({ signal: controller.signal }).then((result) => {
        clock.clearTimeout(timeout);
        if (started === generation) {
          if (result.kind === 'ok' && isRecord(result.body)) {
            const body = result.body as Row;
            rows = Array.isArray(body['annotations']) ? body['annotations'].filter(isRecord) : [];
            revision = typeof body['intent_revision'] === 'string' ? body['intent_revision'] : null;
            state = 'read';
          } else {
            rows = null;
            state = 'error';
            retryAt = clock.now() + LOG_REQUEST_MS;
          }
        }
        // Invalidations coalesce while the old request settles. Its completion cannot restore words, but
        // must release the slot for the current load.
        loading = false;
        publish();
      });
    },

    isLoading: (): boolean => loading,
  };
}

export type IntentLog = ReturnType<typeof createIntentLog>;
