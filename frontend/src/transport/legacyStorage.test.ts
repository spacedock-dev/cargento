import { describe, expect, it, vi } from 'vitest';
import { blockedBackend, fakeBackend } from '../../test/storage_backends';
import { STORAGE_KEYS, createLegacyStorage } from '../storage';
import { createTransportStorage, type StorageEventTarget } from './legacyStorage';

function target() {
  const listeners = new Set<(event: { key: string | null; newValue: string | null }) => void>();
  const events: StorageEventTarget = {
    addEventListener: (_type, listener) => void listeners.add(listener),
    removeEventListener: (_type, listener) => void listeners.delete(listener),
  };
  return {
    events,
    listeners,
    fire: (key: string | null, newValue: string | null) => {
      for (const listener of [...listeners]) listener({ key, newValue });
    },
  };
}

function adapter(backend = fakeBackend()) {
  const events = target();
  const storage = createTransportStorage(createLegacyStorage(() => backend), events.events);
  return { backend, storage, events };
}

describe('lease over the legacy keys', () => {
  it('writes the released JSON shape under the released key', () => {
    const { backend, storage } = adapter();
    expect(storage.writeLease({ id: 'tab-1', ts: 1234 })).toBe(true);
    expect(backend.data.get(STORAGE_KEYS.leader)).toBe('{"id":"tab-1","ts":1234}');
  });

  it('reads a lease the legacy page wrote and releases only the lease key', () => {
    const { backend, storage } = adapter(fakeBackend({ [STORAGE_KEYS.leader]: '{"id":"old-page","ts":99}', other: 'kept' }));
    expect(storage.readLease()).toEqual({ id: 'old-page', ts: 99 });
    storage.removeLease();
    expect(backend.data.has(STORAGE_KEYS.leader)).toBe(false);
    expect(backend.data.get('other')).toBe('kept');
  });

  it('reads nothing and refuses writes when storage is blocked, so each tab leads itself', () => {
    const { storage } = adapter(blockedBackend() as ReturnType<typeof fakeBackend>);
    expect(storage.readLease()).toBeNull();
    expect(storage.writeLease({ id: 'a', ts: 1 })).toBe(false);
    expect(() => storage.removeLease()).not.toThrow();
    expect(() => storage.writeRevision('1.1')).not.toThrow();
  });
});

describe('revision broadcast', () => {
  it('writes the raw revision string', () => {
    const { backend, storage } = adapter();
    storage.writeRevision('9.4');
    expect(backend.data.get(STORAGE_KEYS.revision)).toBe('9.4');
  });

  it('hands another tab’s revision to the subscriber and ignores every other key', () => {
    const { storage, events } = adapter();
    const seen = vi.fn();
    storage.subscribeRevision(seen);
    events.fire(STORAGE_KEYS.leader, 'x');
    events.fire(null, null);
    events.fire(STORAGE_KEYS.revision, '9.5');
    events.fire(STORAGE_KEYS.revision, null);
    expect(seen.mock.calls).toEqual([['9.5'], ['']]);
  });

  it('removes its listener when unsubscribed', () => {
    const { storage, events } = adapter();
    const off = storage.subscribeRevision(() => undefined);
    expect(events.listeners.size).toBe(1);
    off();
    expect(events.listeners.size).toBe(0);
  });
});

describe('consent over the legacy keys', () => {
  it('reads valid storage first, so another tab’s answer wins, and falls back to the tab’s own', () => {
    const { backend, storage } = adapter(fakeBackend({ [STORAGE_KEYS.usageConsent]: 'granted' }));
    expect(storage.usageConsent()).toBe('granted');
    storage.setObserverConsent('granted');
    expect(backend.data.get(STORAGE_KEYS.observerConsent)).toBe('granted');
    backend.data.set(STORAGE_KEYS.observerConsent, 'declined');
    expect(storage.observerConsent()).toBe('declined');
  });

  it('keeps unanswered unanswered, and the tab’s answer when storage refuses', () => {
    const fresh = adapter();
    expect(fresh.storage.usageConsent()).toBeNull();
    expect(fresh.storage.observerConsent()).toBeNull();
    const blocked = adapter(blockedBackend() as ReturnType<typeof fakeBackend>);
    blocked.storage.setUsageConsent('granted');
    expect(blocked.storage.usageConsent()).toBe('granted');
    expect(blocked.storage.observerConsent()).toBeNull();
  });

  it('does not confuse the two consent keys', () => {
    const { backend, storage } = adapter();
    storage.setUsageConsent('granted');
    expect(backend.data.get(STORAGE_KEYS.usageConsent)).toBe('granted');
    expect(storage.observerConsent()).toBeNull();
  });
});
