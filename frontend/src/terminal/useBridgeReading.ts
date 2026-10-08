import { useSyncExternalStore } from 'react';
import { compatSessKey } from '../api/identity';
import type { SessionIdentity } from '../api/types';
import { bridgeReading } from './registration';
import { useTerminalOwner } from './useTerminalOwner';

/* What the Console's summary may say about the terminal bridge: true (on), false (off), null (not read
   yet) or "per-session" (no session is selected, so there is nothing whose bridge could be read). It reads
   the owner's lookups, so it agrees with the surface below it, and it starts no read of its own. */
export function useBridgeReading(identity: SessionIdentity | null): boolean | null | 'per-session' {
  const owner = useTerminalOwner();
  const lookup = useSyncExternalStore(owner.subscribe, () =>
    identity ? owner.getSnapshot().lookups.get(compatSessKey(identity)) : undefined,
  );
  return bridgeReading(identity !== null, lookup);
}
