import type { ApiClient } from '../api/client';
import { compatSessKey, contextKey } from '../api/identity';
import type { SemanticFact, SessionIdentity, SessionRecord } from '../api/types';
import {
  EMPTY_RECORD,
  type BoardSnapshot,
  type BoardStore,
  type RecordEntry,
} from '../store/board';

export const RECORD_PAGE_SIZE = 50;
/* The most pages one finished press may read to find what its reading cites: 1,000 entries at fifty a page.
   Past it the reader's own Show more continues, so a reading that cites an id the record never held cannot
   walk a session's whole history. docs/design-reader-state.md#the-inventory owns this exception. */
export const RESOLVE_MAX_PAGES = 20;
/* The most pages one refresh may read to meet what the record already holds. A refresh asks for the newest page
   and follows older ones only through a burst of more than a page since the last read, so one is almost always
   one request. Past the cap the record starts again from the newest entries rather than walk a session's
   history on a poll. */
export const REFRESH_MAX_PAGES = RESOLVE_MAX_PAGES;
export interface RecordScope {
  readonly projectKey: string;
  readonly focus: SessionIdentity;
}

/* A record a refresh may merge into: one that loaded, or one that still holds entries while an older page is
   being read or has failed. Merging at the newest end is safe in all three, since it only adds entries. */
const mergeable = (record: RecordEntry | undefined): record is RecordEntry =>
  record !== undefined &&
  (record.status === 'loaded' ||
    ((record.status === 'loading' || record.status === 'error') && record.entries.length > 0));

const newestFirst = (a: SemanticFact, b: SemanticFact): number =>
  b.at - a.at || (a.fact_id < b.fact_id ? -1 : a.fact_id > b.fact_id ? 1 : 0);

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
    /* The newest-end refresh: the last activity stamp it has seen (the first one is the baseline the opening
       read already covers), the run in flight, whether another stamp arrived while it ran, and its request. */
    stamp: number | undefined;
    /* The last refresh went unanswered, so the same stamp is read again on the next call. */
    retry: boolean;
    refreshing: Promise<void> | null;
    refreshAgain: boolean;
    refreshRequest: AbortController | null;
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
          entries: [...merged.values()].sort(newestFirst),
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

  /* Reads the newest page again and merges it, so what the session wrote after the opening is held here and
     does not depend on the board's context, which only reaches back over the newest 400 KB of the transcript.
     Measured 2026-10-14 on a working session: the list rose from 66 to 74 entries as messages arrived, then
     fell back to 66 as large tool results pushed them out of that tail. All eight lost entries arrived after
     the opening, were in no loaded page and were still in the record, and every number above them shifted.

     It merges by fact id and leaves the older cursor, the page count and the paging state alone, so what the
     reader loaded stays and an entry once held is held until they leave. A burst of more than a page since the
     last read is bridged by following older pages until the newest page meets what is held; one that cannot be
     bridged in `REFRESH_MAX_PAGES` starts the record again from the newest entries and says so. A refresh that
     does not answer changes nothing, and the next call tries it again even for the same stamp, so
     a transient failure on a session's last write is not left standing. */
  async function refreshOnce(scope: RecordScope, opening: Opening): Promise<boolean> {
    const key = contextKey(scope.projectKey, scope.focus);
    const current = () => !disposed && openings.get(key) === opening;
    // The opening read, or an older page the reader asked for, settles before the newest end is read again.
    if (opening.pending) await opening.pending;
    if (!current() || !mergeable(store.getSnapshot().records.get(key))) return true;
    const owned = new AbortController();
    opening.refreshRequest = owned;
    const fresh = new Map<string, SemanticFact>();
    let last: SessionRecord | null = null;
    let met = false;
    let before: string | null = null;
    for (let page = 0; page < REFRESH_MAX_PAGES; page += 1) {
      const result = await client.getSessionRecord({
        project: scope.projectKey,
        session: compatSessKey(scope.focus),
        limit: RECORD_PAGE_SIZE,
        ...(before ? { before } : {}),
        signal: owned.signal,
      });
      if (!current() || owned.signal.aborted || result.kind === 'aborted') return true;
      // An answer that is not a page changes nothing, and the same stamp is read again next time.
      if (result.kind !== 'ok') return false;
      const body = result.body;
      if (
        body.state !== 'ok' ||
        !Array.isArray(body.entries) ||
        body.session?.harness !== scope.focus.harness ||
        body.session.sid !== scope.focus.sid
      )
        return false;
      for (const fact of body.entries) fresh.set(fact.fact_id, fact);
      last = body;
      const held = store.getSnapshot().records.get(key);
      if (!mergeable(held)) return true;
      const heldIds = new Set(held.entries.map((fact) => fact.fact_id));
      met =
        held.entries.length === 0 ||
        body.reached_start ||
        body.entries.some((fact) => heldIds.has(fact.fact_id));
      if (met || !body.next) break;
      before = body.next;
    }
    const held = store.getSnapshot().records.get(key);
    if (!current() || !mergeable(held) || !last) return true;
    if (!met) {
      // An older page in flight was asked for with a cursor that no longer joins this record.
      opening.request?.abort();
      store.setRecord(key, {
        ...EMPTY_RECORD,
        entries: [...fresh.values()].sort(newestFirst),
        next: last.next,
        reachedStart: last.reached_start,
        bound: last.bound,
        scannedBytes: last.scanned_bytes,
        status: 'loaded',
        pages: 1,
        restarted: true,
      });
      return true;
    }
    const merged = new Map(held.entries.map((fact) => [fact.fact_id, fact]));
    for (const [id, fact] of fresh) merged.set(id, fact);
    store.setRecord(key, {
      ...held,
      entries: [...merged.values()].sort(newestFirst),
      ...(held.entries.length === 0
        ? {
            next: last.next,
            reachedStart: last.reached_start,
            bound: last.bound,
            scannedBytes: last.scanned_bytes,
          }
        : {}),
    });
    return true;
  }

  function refresh(scope: RecordScope, stamp: number, opening: Opening): Promise<void> {
    const key = contextKey(scope.projectKey, scope.focus);
    if (disposed || openings.get(key) !== opening) return Promise.resolve();
    if (opening.stamp === undefined) {
      opening.stamp = stamp;
      return Promise.resolve();
    }
    if (opening.stamp === stamp && !opening.retry) return opening.refreshing ?? Promise.resolve();
    opening.stamp = stamp;
    if (opening.refreshing) {
      opening.refreshAgain = true;
      return opening.refreshing;
    }
    // The clearing is inside the run, so a call that lands as the loop ends starts a new one.
    opening.refreshing = (async () => {
      try {
        do {
          opening.refreshAgain = false;
          opening.retry = !(await refreshOnce(scope, opening));
        } while (opening.refreshAgain && !disposed && openings.get(key) === opening);
      } finally {
        opening.refreshing = null;
        opening.refreshRequest = null;
      }
    })();
    return opening.refreshing;
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
    opening.refreshRequest?.abort();
    store.dropRecord(key);
  }

  return {
    open(scope: RecordScope): () => void {
      if (disposed) return () => undefined;
      const key = contextKey(scope.projectKey, scope.focus);
      let opening = openings.get(key);
      if (!opening) {
        opening = {
          holders: 0,
          request: null,
          pending: null,
          resolution: null,
          stamp: undefined,
          retry: false,
          refreshing: null,
          refreshAgain: false,
          refreshRequest: null,
        };
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
    /* `stamp` is the session's activity as the board last published it. The first stamp after an opening is its
       baseline, a stamp already seen reads nothing, and a new one reads the newest page again. */
    refresh(scope: RecordScope, stamp: number): Promise<void> {
      const opening = openings.get(contextKey(scope.projectKey, scope.focus));
      return opening ? refresh(scope, stamp, opening) : Promise.resolve();
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
