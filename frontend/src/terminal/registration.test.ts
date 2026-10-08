import { describe, expect, it } from 'vitest';
import type { ApiResult, InteractionOrigin } from '../api/types';
import {
  absenceOf,
  beginLookup,
  bridgeReading,
  originTitle,
  settleLookup,
  type OriginLookup,
} from './registration';

const ok = (body: InteractionOrigin & Record<string, unknown>): ApiResult<InteractionOrigin> => ({
  kind: 'ok',
  status: 200,
  body,
  revision: '',
});

describe('classifying the registration read', () => {
  it('names a registered terminal and keeps its origin', () => {
    const settled = settleLookup(
      ok({ state: 'registered', origin: { session_name: 's', window_index: '0', pane_index: '0' }, origin_id_hint: 'abcd1234' }),
      7,
    );
    expect(settled).toMatchObject({ state: 'registered', revision: 7, loading: false });
    expect(settled && 'data' in settled && settled.data.origin_id_hint).toBe('abcd1234');
  });

  it('keeps every other answer as unavailable with the server reason', () => {
    expect(settleLookup(ok({ state: 'refused', reason: 'session-mismatch' }), 3)).toMatchObject({
      state: 'unavailable',
      data: { reason: 'session-mismatch' },
    });
    expect(settleLookup(ok({ state: 'unknown', reason: 'origin-disconnected' }), 3)).toMatchObject({
      state: 'unavailable',
      data: { reason: 'origin-disconnected' },
    });
  });

  it('reads a 404 as the bridge being off, not as a failed lookup', () => {
    expect(settleLookup({ kind: 'http-error', status: 404, body: null }, 1)).toMatchObject({
      state: 'unavailable',
      data: { reason: 'bridge-disabled' },
    });
  });

  it('reads every other failure as a lookup that could not be made', () => {
    for (const result of [
      { kind: 'http-error', status: 500, body: null },
      { kind: 'http-error', status: 403, body: null },
      { kind: 'malformed', status: 200 },
      { kind: 'network-error' },
    ] as const) {
      expect(settleLookup(result, 1)).toMatchObject({ state: 'unavailable', data: { reason: 'lookup-failed' } });
    }
  });

  it('says nothing for an aborted read, which the owner ended itself', () => {
    expect(settleLookup({ kind: 'aborted' }, 1)).toBeNull();
  });

  it('does not take a non-string reason or an unknown state as a registered terminal', () => {
    expect(settleLookup(ok({ state: 'REGISTERED' }), 1)).toMatchObject({ state: 'unavailable' });
    expect(settleLookup(ok({ reason: 5 as unknown as string }), 1)).toMatchObject({ state: 'unavailable', data: {} });
  });
});

describe('when a lookup is made', () => {
  it('starts a first lookup as loading', () => {
    expect(beginLookup(undefined, 5)).toEqual({ state: 'loading', revision: 5, loading: true });
  });

  it('does not repeat a lookup in flight or one that already covers this revision', () => {
    const settled: OriginLookup = { state: 'registered', revision: 5, loading: false, data: {} };
    expect(beginLookup(settled, 5)).toBeNull();
    expect(beginLookup(settled, 4)).toBeNull();
    expect(beginLookup({ ...settled, loading: true }, 9)).toBeNull();
    expect(beginLookup({ state: 'loading', revision: 5, loading: true }, 9)).toBeNull();
  });

  it('keeps a settled answer of either kind while the next revision is checked', () => {
    const registered: OriginLookup = { state: 'registered', revision: 5, loading: false, data: { origin_id_hint: 'x' } };
    expect(beginLookup(registered, 6)).toEqual({ ...registered, revision: 6, loading: true });
    const off: OriginLookup = { state: 'unavailable', revision: 5, loading: false, data: { reason: 'bridge-disabled' } };
    // A default bridge-off console read "not read yet" on every poll when this reset to loading.
    expect(beginLookup(off, 6)).toEqual({ ...off, revision: 6, loading: true });
  });
});

describe('what an absent terminal says', () => {
  it('says it is checking before any answer', () => {
    expect(absenceOf(undefined)).toMatchObject({ checking: true });
    expect(absenceOf({ state: 'loading', revision: 1, loading: true })).toMatchObject({ checking: true });
  });

  it('gives each known reason its sentence, and the recipe for the four that can be fixed by registering', () => {
    const cases: [string, string, boolean][] = [
      ['unregistered-origin', 'Terminal not registered for this session.', true],
      ['bridge-disabled', 'The terminal bridge is disabled on this server.', true],
      ['stale-registration', 'Terminal registration has expired.', true],
      ['origin-disconnected', 'The registered tmux pane is disconnected.', false],
      ['origin-mismatch', 'The registered tmux pane no longer matches its recorded identity.', false],
      ['session-mismatch', 'The registered terminal belongs to another session.', true],
      ['session-uncollected', 'This session is no longer in the server’s collected sessions.', false],
      ['lookup-failed', 'Terminal registration could not be checked because the local request failed.', false],
    ];
    for (const [reason, message, recipe] of cases) {
      const lookup: OriginLookup = { state: 'unavailable', revision: 1, loading: false, data: { reason } };
      expect(absenceOf(lookup), reason).toEqual({ checking: false, message, serverReason: null, recipe });
    }
  });

  it('shows an unknown reason as the server stated it, never as a guess', () => {
    const lookup: OriginLookup = { state: 'unavailable', revision: 1, loading: false, data: { reason: 'new-reason' } };
    expect(absenceOf(lookup)).toEqual({
      checking: false,
      message: 'The server refused terminal access.',
      serverReason: 'new-reason',
      recipe: false,
    });
  });

  it('says the status was not published when the answer carried no reason', () => {
    const lookup: OriginLookup = { state: 'unavailable', revision: 1, loading: false, data: {} };
    expect(absenceOf(lookup)).toEqual({
      checking: false,
      message: 'Terminal registration status was not published by the server.',
      serverReason: null,
      recipe: false,
    });
  });
});

describe('the console capability reading', () => {
  it('is per-session with no session, unread before an answer, and on or off after', () => {
    expect(bridgeReading(false, undefined)).toBe('per-session');
    expect(bridgeReading(true, undefined)).toBeNull();
    expect(bridgeReading(true, { state: 'loading', revision: 1, loading: true })).toBeNull();
    expect(bridgeReading(true, { state: 'registered', revision: 1, loading: false, data: {} })).toBe(true);
    expect(bridgeReading(true, { state: 'unavailable', revision: 1, loading: false, data: {} })).toBe(false);
  });

  it('reads a registered terminal that is being re-checked as on, not as unread', () => {
    // `loading` is a flag beside the state; reading it reported "not read yet" on every poll of a working console.
    expect(bridgeReading(true, { state: 'registered', revision: 2, loading: true, data: {} })).toBe(true);
  });
});

describe('the terminal title', () => {
  it('joins a complete origin as session:window.pane, with zero coordinates kept', () => {
    expect(originTitle({ session_name: 'work', window_index: 0, pane_index: 0 })).toEqual({
      complete: 'work:0.0',
      session: 'work',
      window: '0',
      pane: '0',
    });
    expect(originTitle({ session_name: 'work', window_index: '0', pane_index: '0' }).complete).toBe('work:0.0');
  });

  it('names each missing part rather than inventing it', () => {
    expect(originTitle({ window_index: 1 })).toEqual({
      complete: null,
      session: null,
      window: '1',
      pane: null,
    });
    expect(originTitle({ session_name: 'work', window_index: '', pane_index: 2 })).toEqual({
      complete: null,
      session: 'work',
      window: null,
      pane: '2',
    });
    expect(originTitle(undefined)).toEqual({ complete: null, session: null, window: null, pane: null });
  });
});
