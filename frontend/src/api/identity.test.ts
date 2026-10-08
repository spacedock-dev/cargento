import { describe, expect, it } from 'vitest';
import {
  compatSessKey,
  contextKey,
  exactIdentity,
  splitSessKey,
  stableProjectKey,
} from './identity';

describe('session identity', () => {
  it('keys a session by the exact harness and sid pair', () => {
    expect(compatSessKey({ harness: 'claude', sid: 'abc-123' })).toBe('claude:abc-123');
    expect(compatSessKey({ harness: 'codex', sid: 'abc-123' })).not.toBe(
      compatSessKey({ harness: 'claude', sid: 'abc-123' }),
    );
  });

  it('falls back to the display id only inside the compatibility key, never for an action identity', () => {
    const row = { harness: 'claude', session: 'abc12345' };
    expect(compatSessKey(row)).toBe('claude:abc12345');
    expect(exactIdentity(row)).toBeNull();
  });

  it('refuses a missing, blank or non-string half of the pair', () => {
    expect(exactIdentity({ harness: 'claude', sid: 'x' })).toEqual({ harness: 'claude', sid: 'x' });
    expect(exactIdentity({ harness: '', sid: 'x' })).toBeNull();
    expect(exactIdentity({ harness: 'claude', sid: '  ' })).toBeNull();
    expect(exactIdentity({ harness: 7, sid: 'x' })).toBeNull();
    expect(exactIdentity(null)).toBeNull();
  });

  it('splits a composite key at the first colon only, because a sid may hold colons', () => {
    expect(splitSessKey('claude:a:b:c')).toEqual({ harness: 'claude', sid: 'a:b:c' });
    expect(splitSessKey('nocolon')).toBeNull();
    expect(splitSessKey(':sid')).toBeNull();
    expect(splitSessKey('harness:')).toBeNull();
  });

  it('uses the shared project key when all rows agree and the label otherwise', () => {
    const rows = (...keys: string[]) => keys.map((project_key) => ({ project_key }));
    expect(stableProjectKey({ label: 'app', sessions: rows('/repo/a', '/repo/a') })).toBe(
      '/repo/a',
    );
    expect(stableProjectKey({ label: 'app', sessions: rows('/repo/a', '/repo/b') })).toBe('app');
    expect(stableProjectKey({ label: 'app', sessions: rows('', '') })).toBe('app');
  });

  it('keeps project and session scope apart in a context key', () => {
    const focus = { harness: 'claude', sid: 's1' };
    expect(contextKey('/repo/a', null)).toBe('/repo/a\n');
    expect(contextKey('/repo/a', focus)).toBe('/repo/a\nclaude:s1');
    expect(contextKey('/repo/b', focus)).not.toBe(contextKey('/repo/a', focus));
  });
});
