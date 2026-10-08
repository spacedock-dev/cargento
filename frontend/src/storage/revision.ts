import type { StorageAccess } from './backend';
import { STORAGE_KEYS } from './keys';

/**
 * Whether wire revision `a` ("<started>.<counter>") is newer than `b`. A different start stamp is
 * a server restart and always newer, so a tab that outlived its server still follows the new one.
 */
export function revisionNewer(a: string | null | undefined, b: string | null | undefined): boolean {
  if (!a) return false;
  if (!b) return true;
  const split = (value: string): [string, number] => {
    const at = value.lastIndexOf('.');
    return at < 0 ? [value, NaN] : [value.slice(0, at), Number(value.slice(at + 1))];
  };
  const [startedA, counterA] = split(a);
  const [startedB, counterB] = split(b);
  if (startedA !== startedB) return true;
  if (!Number.isFinite(counterA) || !Number.isFinite(counterB)) return a !== b;
  return counterA > counterB;
}

/** The revision a `storage` event carries, '' when it carries none, null for any other key. */
export function revisionFromStorageEvent(
  event: { readonly key: string | null; readonly newValue: string | null } | null | undefined,
): string | null {
  if (!event || event.key !== STORAGE_KEYS.revision) return null;
  return String(event.newValue || '');
}

export interface RevisionStore {
  read(): string | null;
  write(revision: string): boolean;
}

/**
 * Only a broadcast between tabs. The legacy page never hydrates its in-memory revision from
 * this key, and a persisted revision is not a record that the data was accepted.
 */
export function createRevisionStore(access: StorageAccess): RevisionStore {
  return {
    read() {
      const read = access.attempt((backend) => backend.getItem(STORAGE_KEYS.revision));
      return read.ok ? read.value : null;
    },
    write: (revision) =>
      access.attempt((backend) => {
        backend.setItem(STORAGE_KEYS.revision, revision);
      }).ok,
  };
}
