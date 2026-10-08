import type { Clock, TimerHandle } from './ports';

/* 15 s, because the annotation store's lock wait is 10 s and one cold
   collection follows it; past that the request is aborted. The backstop
   follows 5 s later and clears the entry whatever the fetch did, so a lost
   request never leaves a spinner standing. The start sentence waits 400 ms, so
   a fast answer says nothing but its outcome. */
export const PENDING_BOUND_MS = 15_000;
export const PENDING_BACKSTOP_MS = 5_000;
export const PENDING_SAY_MS = 400;

export interface PendingToken {
  readonly busy: string;
  readonly say: string;
  readonly startedAt: number;
  readonly signal: AbortSignal;
}

interface Entry extends PendingToken {
  readonly controller: AbortController;
  readonly timers: TimerHandle[];
}

export interface PendingDeps {
  readonly clock: Clock;
  /** The set of pending keys changed without the caller ending an entry. */
  readonly onChange: () => void;
  readonly announce: (key: string, sentence: string) => void;
}

/* Held outside the rendered tree because the board redraws on every poll. The
   returned entry is the caller's token: an old handler that outlived the
   backstop ends nothing of a newer press. */
export function createPendingRegistry(deps: PendingDeps) {
  const entries = new Map<string, Entry>();
  let disposed = false;

  function clearTimers(entry: Entry): void {
    for (const timer of entry.timers) deps.clock.clearTimeout(timer);
    entry.timers.length = 0;
  }

  function end(key: string, token: PendingToken | null | undefined): boolean {
    const entry = entries.get(key);
    if (!entry || entry !== token) return false;
    clearTimers(entry);
    entries.delete(key);
    return true;
  }

  return {
    start(key: string, busy: string, say = ''): PendingToken | null {
      if (disposed || !key || entries.has(key)) return null;
      const controller = new AbortController();
      const entry: Entry = {
        busy,
        say,
        startedAt: deps.clock.now(),
        signal: controller.signal,
        controller,
        timers: [],
      };
      entries.set(key, entry);
      if (say) {
        entry.timers.push(
          deps.clock.setTimeout(() => {
            if (entries.get(key) === entry) deps.announce(key, say);
          }, PENDING_SAY_MS),
        );
      }
      entry.timers.push(deps.clock.setTimeout(() => controller.abort(), PENDING_BOUND_MS));
      entry.timers.push(
        deps.clock.setTimeout(() => {
          if (end(key, entry)) deps.onChange();
        }, PENDING_BOUND_MS + PENDING_BACKSTOP_MS),
      );
      return entry;
    },
    end,
    has: (key: string): boolean => Boolean(key) && entries.has(key),
    keys: (): readonly string[] => [...entries.keys()],
    dispose(): void {
      disposed = true;
      for (const entry of entries.values()) {
        clearTimers(entry);
        entry.controller.abort();
      }
      entries.clear();
    },
  };
}

export type PendingRegistry = ReturnType<typeof createPendingRegistry>;
