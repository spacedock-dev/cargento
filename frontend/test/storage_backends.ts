import type { StorageBackend } from '../src/storage';

export interface FakeBackend extends StorageBackend {
  readonly data: Map<string, string>;
  readonly writes: string[];
}

/** A Map-backed Storage that records every key written, so tests can assert on raw values. */
export function fakeBackend(initial: Record<string, string> = {}): FakeBackend {
  const data = new Map(Object.entries(initial));
  const writes: string[] = [];
  return {
    data,
    writes,
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => {
      writes.push(key);
      data.set(key, value);
    },
    removeItem: (key) => {
      writes.push(key);
      data.delete(key);
    },
  };
}

/** Storage that refuses everything, as a blocked-site-data profile or a full quota does. */
export function blockedBackend(): StorageBackend {
  const refuse = (): never => {
    throw new DOMException('blocked', 'SecurityError');
  };
  return { getItem: refuse, setItem: refuse, removeItem: refuse };
}

/** Readable storage whose writes fail, as an origin at quota does. */
export function readOnlyBackend(initial: Record<string, string> = {}): StorageBackend {
  const inner = fakeBackend(initial);
  return {
    getItem: (key) => inner.getItem(key),
    setItem: () => {
      throw new DOMException('quota', 'QuotaExceededError');
    },
    removeItem: () => {
      throw new DOMException('quota', 'QuotaExceededError');
    },
  };
}
