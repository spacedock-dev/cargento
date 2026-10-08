import type { StorageAccess } from './backend';
import { STORAGE_KEYS, sessionKey, type SessionIdentity } from './keys';

/** UTF-16 code units, as `String.prototype.slice` and `maxlength` count them, not code points or bytes. */
export const MEMO_LIMIT = 500;

export type MemoKind = 'outcome' | 'focus';
export type MemoState = 'saved' | 'error';

/** `projectKey` is the unique repository key when the group has one, otherwise the label. */
export function memoKey(projectKey: string, focus: SessionIdentity | null, kind: MemoKind): string {
  const scope = focus ? sessionKey(focus) : 'project';
  return `${STORAGE_KEYS.memoPrefix}${encodeURIComponent(projectKey)}:${encodeURIComponent(scope)}:${kind}`;
}

/** The cut may land inside a surrogate pair; the legacy page keeps that lone half, so this does too. */
export function boundMemo(value: unknown): string {
  return typeof value === 'string' ? value.slice(0, MEMO_LIMIT) : '';
}

export interface MemoStore {
  read(key: string): string;
  write(key: string, value: string): MemoState;
  state(key: string): MemoState | undefined;
}

export function createMemoStore(access: StorageAccess): MemoStore {
  const drafts = new Map<string, string>();
  const states = new Map<string, MemoState>();
  return {
    read(key) {
      const draft = drafts.get(key);
      if (draft !== undefined) return boundMemo(draft);
      const read = access.attempt((backend) => backend.getItem(key));
      if (!read.ok) {
        states.set(key, 'error');
        return '';
      }
      return boundMemo(read.value);
    },
    write(key, value) {
      const bounded = boundMemo(value);
      drafts.set(key, bounded);
      const state: MemoState = access.attempt((backend) => backend.setItem(key, bounded)).ok ? 'saved' : 'error';
      states.set(key, state);
      return state;
    },
    state: (key) => states.get(key),
  };
}
