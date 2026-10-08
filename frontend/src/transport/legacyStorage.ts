import { revisionFromStorageEvent, type LegacyStorage } from '../storage';
import type { TransportStorage } from './ports';

export interface StorageEventTarget {
  addEventListener(type: 'storage', listener: (event: { readonly key: string | null; readonly newValue: string | null }) => void): void;
  removeEventListener(type: 'storage', listener: (event: { readonly key: string | null; readonly newValue: string | null }) => void): void;
}

/* The transport's storage port over the families `../storage` owns. Keys,
   encodings and the in-tab fallbacks stay there, so the released page reads
   whatever this writes and the reverse. */
export function createTransportStorage(
  legacy: Pick<LegacyStorage, 'lease' | 'revision' | 'usageConsent' | 'observerConsent'>,
  events: StorageEventTarget,
): TransportStorage {
  return {
    readLease: () => legacy.lease.read(),
    writeLease: (claim) => legacy.lease.write(claim.id, claim.ts),
    removeLease() {
      legacy.lease.release();
    },
    writeRevision(revision) {
      legacy.revision.write(revision);
    },
    subscribeRevision(listener) {
      const onStorage = (event: { readonly key: string | null; readonly newValue: string | null }) => {
        const revision = revisionFromStorageEvent(event);
        if (revision !== null) listener(revision);
      };
      events.addEventListener('storage', onStorage);
      return () => events.removeEventListener('storage', onStorage);
    },
    usageConsent: () => legacy.usageConsent.get(),
    setUsageConsent(answer) {
      legacy.usageConsent.set(answer);
    },
    observerConsent: () => legacy.observerConsent.get(),
    setObserverConsent(answer) {
      legacy.observerConsent.set(answer);
    },
  };
}
