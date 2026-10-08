import { describe, expect, it } from 'vitest';
import type { ApiResult, AnnotationsBody } from '../api/types';
import { createFakeClock } from '../transport/testing';
import { createIntentLog, LOG_REQUEST_MS } from './logStore';

/* The log's freshness rules (docs/design-reader-state.md, "Intent log freshness"), one at a time, over a
   client the test answers by hand. */

interface Held {
  readonly resolve: (result: ApiResult<AnnotationsBody>) => void;
  readonly signal: AbortSignal | undefined;
}

function setup() {
  const clock = createFakeClock();
  const requests: Held[] = [];
  const client = {
    getAnnotations: (options: { readonly signal?: AbortSignal }) =>
      new Promise<ApiResult<AnnotationsBody>>((resolve) => {
        requests.push({ resolve, signal: options.signal });
        options.signal?.addEventListener('abort', () => resolve({ kind: 'aborted' }));
      }),
  };
  const log = createIntentLog({ client, clock });
  const ok = (annotations: unknown[], intent_revision = 'r1'): ApiResult<AnnotationsBody> => ({
    kind: 'ok',
    status: 200,
    body: { annotations, intent_revision },
    revision: '',
  });
  const settle = async () => {
    for (let turn = 0; turn < 6; turn += 1) await Promise.resolve();
  };
  return { clock, requests, log, ok, settle };
}

const board = (token: string | undefined) => ({ annotate: true, intent_revision: token });

describe('the Intent log store', () => {
  it('fetches nothing until a view asks, and nothing at all while annotations are off', async () => {
    const { log, requests } = setup();
    log.sync({ annotate: false });
    log.load();
    log.sync(board('a'));
    expect(requests).toHaveLength(0);
    log.load();
    log.load();
    expect(requests).toHaveLength(1);
  });

  it('never reads the store while annotations are off', () => {
    const { log, requests } = setup();
    log.sync({ annotate: false, intent_revision: 'a' });
    log.load();
    expect(requests).toHaveLength(0);
    expect(log.getSnapshot().state).toBe('unread');
  });

  it('holds the rows it read, and fetches again only when the token moves', async () => {
    const { log, requests, ok, settle } = setup();
    log.sync(board('a'));
    log.load();
    requests[0]?.resolve(ok([{ harness: 'codex', sid: 's1' }], 'a'));
    await settle();
    expect(log.getSnapshot().state).toBe('read');
    expect(log.getSnapshot().rows).toHaveLength(1);
    // The same token again, and an unrelated board, reuse the rows.
    log.sync(board('a'));
    log.sync({ ...board('a'), generated: 5 });
    expect(log.getSnapshot().state).toBe('read');
    // A moved token withholds the words at once, before any replacement arrives.
    log.sync(board('b'));
    expect(log.getSnapshot().state).toBe('unread');
    expect(log.getSnapshot().rows).toBeNull();
  });

  it('keeps rows a newer route answer already read when the dashboard catches up to them', async () => {
    const { log, requests, ok, settle } = setup();
    log.sync(board('a'));
    log.load();
    requests[0]?.resolve(ok([{ sid: 'x' }], 'c'));
    await settle();
    // The dashboard was behind the route; its token now equals the rows' token, so no second fetch.
    log.sync(board('c'));
    expect(log.getSnapshot().state).toBe('read');
    expect(log.getSnapshot().rows).toHaveLength(1);
  });

  it('never lets a response started before an invalidation restore withdrawn words', async () => {
    const { log, requests, ok, settle } = setup();
    log.sync(board('a'));
    log.load();
    log.sync(board('b'));
    requests[0]?.resolve(ok([{ sid: 'withdrawn', goal: 'old words' }], 'a'));
    await settle();
    expect(log.getSnapshot().rows).toBeNull();
    expect(log.getSnapshot().state).toBe('unread');
    // The slot the old request held is released, and the view is woken so the load that is now due runs.
    expect(log.getSnapshot().loading).toBe(false);
    log.load();
    expect(requests).toHaveLength(2);
  });

  it('coalesces changes that arrive during a request into one load after it settles', async () => {
    const { log, requests, ok, settle } = setup();
    log.sync(board('a'));
    log.load();
    log.sync(board('b'));
    log.load();
    log.sync(board('c'));
    log.load();
    expect(requests).toHaveLength(1);
    requests[0]?.resolve(ok([], 'a'));
    await settle();
    log.load();
    expect(requests).toHaveLength(2);
  });

  it('states a failed read as an error, withholds the old rows and waits twenty seconds to try again', async () => {
    const { log, requests, ok, settle, clock } = setup();
    log.sync(board('a'));
    log.load();
    requests[0]?.resolve(ok([{ sid: 'kept?' }], 'a'));
    await settle();
    log.sync(board('b'));
    log.load();
    requests[1]?.resolve({ kind: 'http-error', status: 500, body: null });
    await settle();
    expect(log.getSnapshot().state).toBe('error');
    expect(log.getSnapshot().rows).toBeNull();
    log.load();
    clock.advance(LOG_REQUEST_MS - 1);
    log.load();
    expect(requests).toHaveLength(2);
    clock.advance(1);
    log.load();
    expect(requests).toHaveLength(3);
  });

  it('treats an unreadable body and a request that outlives its bound as failures, never as empty', async () => {
    const { log, requests, settle, clock } = setup();
    log.sync(board('a'));
    log.load();
    requests[0]?.resolve({ kind: 'malformed', status: 200 });
    await settle();
    expect(log.getSnapshot().state).toBe('error');
    clock.advance(LOG_REQUEST_MS);
    log.load();
    expect(requests).toHaveLength(2);
    clock.advance(LOG_REQUEST_MS);
    await settle();
    expect(requests[1]?.signal?.aborted).toBe(true);
    expect(log.getSnapshot().state).toBe('error');
    expect(log.getSnapshot().rows).toBeNull();
  });

  it('invalidates on a confirmed discard without waiting for the board', async () => {
    const { log, requests, ok, settle } = setup();
    log.sync(board('a'));
    log.load();
    requests[0]?.resolve(ok([{ sid: 'x', goal: 'words' }], 'a'));
    await settle();
    log.invalidate();
    expect(log.getSnapshot().rows).toBeNull();
    expect(log.getSnapshot().state).toBe('unread');
  });
});
