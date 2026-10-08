import { createContext, useContext } from 'react';
import type { Announcer } from './announcer';

export const AnnouncerContext = createContext<Announcer | null>(null);

/* What a control uses to say something: `say` for a plain write, `announce` for a guarded cue. */
export function useAnnouncer(): Announcer {
  const announcer = useContext(AnnouncerContext);
  if (!announcer) throw new Error('useAnnouncer needs an AnnouncerProvider above it.');
  return announcer;
}
