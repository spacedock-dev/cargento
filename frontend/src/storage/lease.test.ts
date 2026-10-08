import { describe, expect, it } from 'vitest';
import { blockedBackend, fakeBackend } from '../../test/storage_backends';
import {
  createLegacyStorage,
  createTabId,
  electionDecision,
  LEASE_RENEW_MS,
  LEASE_STALE_MS,
  leaseIsLive,
  parseLease,
  revisionFromStorageEvent,
  revisionNewer,
} from '.';

describe('leader lease (cargento.next.leader)', () => {
  it('keeps the released renew and stale windows', () => {
    expect(LEASE_RENEW_MS).toBe(2000);
    expect(LEASE_STALE_MS).toBe(6000);
  });

  it('writes {id, ts} as the released JSON and reads it back', () => {
    const backend = fakeBackend();
    const { lease } = createLegacyStorage(() => backend);
    expect(lease.write('abc-1', 1_700_000_000_000)).toBe(true);
    expect(backend.data.get('cargento.next.leader')).toBe('{"id":"abc-1","ts":1700000000000}');
    expect(lease.read()).toEqual({ id: 'abc-1', ts: 1_700_000_000_000 });
  });

  it('reads a missing, corrupt or falsy record as no lease', () => {
    for (const raw of [undefined, '{oops', 'null', '0', '""', 'false']) {
      const backend = fakeBackend(raw === undefined ? {} : { 'cargento.next.leader': raw });
      expect(createLegacyStorage(() => backend).lease.read()).toBeNull();
    }
  });

  it('keeps a foreign record that is not the released shape, so it still counts as foreign', () => {
    expect(parseLease('{"id":5,"ts":"x"}')).toEqual({ id: 5, ts: 'x' });
    expect(parseLease('7')).toEqual({ id: undefined, ts: undefined });
  });

  it('is live strictly inside six seconds and stale at six', () => {
    expect(leaseIsLive({ id: 'a', ts: 1000 }, 1000 + 5999)).toBe(true);
    expect(leaseIsLive({ id: 'a', ts: 1000 }, 1000 + 6000)).toBe(false);
    expect(leaseIsLive({ id: 'a', ts: '1000' }, 1000 + 100)).toBe(true);
    expect(leaseIsLive({ id: 'a', ts: undefined }, 5)).toBe(false);
    expect(leaseIsLive({ id: 'a', ts: 'NaN' }, 5)).toBe(false);
    expect(leaseIsLive(null, 5)).toBe(false);
  });

  it('yields to a live foreign owner, and to a stale one only if it was leading', () => {
    const now = 100_000;
    const live = { id: 'other', ts: now - 1000 };
    const stale = { id: 'other', ts: now - 7000 };
    expect(electionDecision({ lease: null, tabId: 'me', isLeader: false, now })).toBe('lead');
    expect(electionDecision({ lease: { id: 'me', ts: now }, tabId: 'me', isLeader: true, now })).toBe('lead');
    expect(electionDecision({ lease: live, tabId: 'me', isLeader: false, now })).toBe('yield');
    expect(electionDecision({ lease: live, tabId: 'me', isLeader: true, now })).toBe('yield');
    expect(electionDecision({ lease: stale, tabId: 'me', isLeader: false, now })).toBe('lead');
    expect(electionDecision({ lease: stale, tabId: 'me', isLeader: true, now })).toBe('yield');
  });

  it('releases by removing the key', () => {
    const backend = fakeBackend({ 'cargento.next.leader': '{"id":"a","ts":1}' });
    expect(createLegacyStorage(() => backend).lease.release()).toBe(true);
    expect(backend.data.has('cargento.next.leader')).toBe(false);
  });

  it('lets a tab lead itself when storage cannot coordinate', () => {
    const { lease } = createLegacyStorage(() => blockedBackend());
    expect(lease.read()).toBeNull();
    expect(lease.write('me', 1)).toBe(false);
    expect(lease.release()).toBe(false);
    expect(electionDecision({ lease: lease.read(), tabId: 'me', isLeader: false, now: 1 })).toBe('lead');
  });

  it('builds a tab id from base-36 randomness and the clock', () => {
    expect(createTabId(() => 0.5, 1_700_000_000_000)).toBe('i-1700000000000');
    expect(createTabId()).toMatch(/^[0-9a-z]+-\d+$/);
  });
});

describe('revision (cargento.next.revision)', () => {
  it('orders the wire revision <started>.<counter>', () => {
    expect(revisionNewer('', 'a.1')).toBe(false);
    expect(revisionNewer('a.1', null)).toBe(true);
    expect(revisionNewer('a.2', 'a.1')).toBe(true);
    expect(revisionNewer('a.1', 'a.1')).toBe(false);
    expect(revisionNewer('a.1', 'a.2')).toBe(false);
    expect(revisionNewer('a.10', 'a.9')).toBe(true);
  });

  it('treats a changed start stamp as a restart and always newer', () => {
    expect(revisionNewer('b.1', 'a.99')).toBe(true);
    expect(revisionNewer('a.1.5', 'a.1.4')).toBe(true);
    expect(revisionNewer('a.1.5', 'a.2.4')).toBe(true);
  });

  it('falls back to inequality when a counter is not finite or there is no dot', () => {
    expect(revisionNewer('a.x', 'a.1')).toBe(true);
    expect(revisionNewer('a.x', 'a.x')).toBe(false);
    expect(revisionNewer('abc', 'abd')).toBe(true);
    expect(revisionNewer('abc', 'abc')).toBe(false);
  });

  it('stores the raw revision and never wraps it', () => {
    const backend = fakeBackend();
    const { revision } = createLegacyStorage(() => backend);
    expect(revision.read()).toBeNull();
    expect(revision.write('1700.42')).toBe(true);
    expect(backend.data.get('cargento.next.revision')).toBe('1700.42');
    expect(revision.read()).toBe('1700.42');
  });

  it('is lost quietly when storage is blocked', () => {
    const { revision } = createLegacyStorage(() => blockedBackend());
    expect(revision.write('1.1')).toBe(false);
    expect(revision.read()).toBeNull();
  });

  it('extracts a revision from its storage event and ignores every other key', () => {
    expect(revisionFromStorageEvent({ key: 'cargento.next.revision', newValue: '1.2' })).toBe('1.2');
    expect(revisionFromStorageEvent({ key: 'cargento.next.revision', newValue: null })).toBe('');
    expect(revisionFromStorageEvent({ key: 'cargento.next.leader', newValue: '1.2' })).toBeNull();
    expect(revisionFromStorageEvent(null)).toBeNull();
  });
});
