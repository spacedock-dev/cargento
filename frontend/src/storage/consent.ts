import type { StorageAccess } from './backend';

export type ConsentAnswer = 'granted' | 'declined';

export interface ConsentStore {
  /** `null` is unanswered, and a missing or unrecognised entry must never read as granted. */
  get(): ConsentAnswer | null;
  /** Anything but `granted` is recorded as `declined`. Returns whether storage took the write. */
  set(answer: ConsentAnswer): boolean;
}

/**
 * Storage is consulted first so an answer given in another tab wins. The memo answers only when storage
 * is unreadable, or when the last write was refused so storage holds nothing to read: an answer the reader
 * removed from storage is then withdrawn rather than kept alive by a copy in memory, which would fail
 * toward consent.
 */
export function createConsentStore(access: StorageAccess, key: string): ConsentStore {
  let memo: ConsentAnswer | null = null;
  let memoStands = false;
  return {
    get() {
      const read = access.attempt((backend) => backend.getItem(key));
      if (read.ok && (read.value === 'granted' || read.value === 'declined')) {
        memoStands = false;
        return read.value;
      }
      if (read.ok && read.value === null && !memoStands) return null;
      return memo;
    },
    set(answer) {
      const value: ConsentAnswer = answer === 'granted' ? 'granted' : 'declined';
      memo = value;
      const wrote = access.attempt((backend) => {
        backend.setItem(key, value);
      }).ok;
      memoStands = !wrote;
      return wrote;
    },
  };
}
