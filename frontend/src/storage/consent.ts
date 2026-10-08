import type { StorageAccess } from './backend';

export type ConsentAnswer = 'granted' | 'declined';

export interface ConsentStore {
  /** `null` is unanswered, and a missing or unrecognised entry must never read as granted. */
  get(): ConsentAnswer | null;
  /** Anything but `granted` is recorded as `declined`. Returns whether storage took the write. */
  set(answer: ConsentAnswer): boolean;
}

/**
 * Storage is consulted first so an answer given in another tab wins; the memo only answers when
 * storage is unreadable or holds something unrecognised, so a refused write still lasts the tab.
 */
export function createConsentStore(access: StorageAccess, key: string): ConsentStore {
  let memo: ConsentAnswer | null = null;
  return {
    get() {
      const read = access.attempt((backend) => backend.getItem(key));
      if (read.ok && (read.value === 'granted' || read.value === 'declined')) return read.value;
      return memo;
    },
    set(answer) {
      const value: ConsentAnswer = answer === 'granted' ? 'granted' : 'declined';
      memo = value;
      return access.attempt((backend) => {
        backend.setItem(key, value);
      }).ok;
    },
  };
}
