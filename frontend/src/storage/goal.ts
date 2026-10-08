import type { StorageAccess } from './backend';
import { STORAGE_KEYS } from './keys';

/** The editor's `maxlength`, in UTF-16 units. Storage itself bounds nothing, on read or write. */
export const GOAL_EDITOR_MAX_UTF16 = 500;

export function goalKey(label: string): string {
  return `${STORAGE_KEYS.goalPrefix}${encodeURIComponent(label)}`;
}

export type GoalSave = 'saved' | 'empty' | 'unavailable';
export type GoalClear = 'cleared' | 'unavailable';

export interface GoalStore {
  read(label: string): string;
  /** The reader's unsaved text, kept in memory only; it wins over storage until saved or cleared. */
  setDraft(label: string, value: string): void;
  save(label: string, value: string): GoalSave;
  clear(label: string): GoalClear;
}

export function createGoalStore(access: StorageAccess): GoalStore {
  const drafts = new Map<string, string>();
  return {
    read(label) {
      const draft = drafts.get(label);
      if (draft !== undefined) return draft;
      const read = access.attempt((backend) => backend.getItem(goalKey(label)));
      return read.ok ? read.value || '' : '';
    },
    setDraft(label, value) {
      drafts.set(label, String(value));
    },
    save(label, value) {
      const text = String(value).trim();
      if (!text) return 'empty';
      if (!access.attempt((backend) => backend.setItem(goalKey(label), text)).ok) return 'unavailable';
      drafts.set(label, text);
      return 'saved';
    },
    clear(label) {
      // The draft goes only after the key does, so a refused removal leaves the reader's text.
      if (!access.attempt((backend) => backend.removeItem(goalKey(label))).ok) return 'unavailable';
      drafts.delete(label);
      return 'cleared';
    },
  };
}
