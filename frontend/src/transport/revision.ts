import { revisionNewer } from '../storage/revision';

/* One comparator, owned with the storage that carries the key. */
export { revisionNewer };

/* The newest revision this tab has seen, in memory only. A persisted revision
   is never read back as a bootstrap, so a fresh tab always fetches once. */
export function createRevisionMemo() {
  let last: string | null = null;
  return {
    get: (): string | null => last,
    advance(revision: string | null | undefined): boolean {
      if (!revision || !revisionNewer(revision, last)) return false;
      last = revision;
      return true;
    },
  };
}

export type RevisionMemo = ReturnType<typeof createRevisionMemo>;
