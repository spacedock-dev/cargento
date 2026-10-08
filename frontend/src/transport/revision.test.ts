import { describe, expect, it } from 'vitest';
import { createRevisionMemo, revisionNewer } from './revision';

describe('revision comparator', () => {
  it('compares finite counters under one start stamp', () => {
    expect(revisionNewer('9.5', '9.4')).toBe(true);
    expect(revisionNewer('9.4', '9.4')).toBe(false);
    expect(revisionNewer('9.3', '9.4')).toBe(false);
    expect(revisionNewer('9.10', '9.9')).toBe(true);
  });

  it('treats a changed start stamp as newer even with a smaller counter', () => {
    expect(revisionNewer('10.1', '9.400')).toBe(true);
  });

  it('splits at the last dot only', () => {
    expect(revisionNewer('a.b.2', 'a.b.1')).toBe(true);
    expect(revisionNewer('a.b.1', 'a.c.1')).toBe(true);
  });

  it('falls back to inequality when a counter is not finite', () => {
    expect(revisionNewer('9.x', '9.y')).toBe(true);
    expect(revisionNewer('9.x', '9.x')).toBe(false);
    expect(revisionNewer('nodot', 'other')).toBe(true);
    expect(revisionNewer('nodot', 'nodot')).toBe(false);
  });

  it('never calls an empty revision newer and always calls any revision newer than none', () => {
    expect(revisionNewer('', '9.1')).toBe(false);
    expect(revisionNewer(null, null)).toBe(false);
    expect(revisionNewer('9.1', '')).toBe(true);
    expect(revisionNewer('9.1', null)).toBe(true);
  });

  it('keeps the newest revision in memory and reports whether it advanced', () => {
    const memo = createRevisionMemo();
    expect(memo.get()).toBeNull();
    expect(memo.advance('9.2')).toBe(true);
    expect(memo.advance('9.2')).toBe(false);
    expect(memo.advance('9.1')).toBe(false);
    expect(memo.advance('')).toBe(false);
    expect(memo.advance('9.3')).toBe(true);
    expect(memo.get()).toBe('9.3');
  });
});
