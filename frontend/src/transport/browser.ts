import { createLegacyStorage, createTabId } from '../storage';
import { createTransportStorage } from './legacyStorage';
import type { Environment, EventSourceLike, TimerHandle } from './ports';
import { createBoardRuntime, type BoardRuntime } from './runtime';

/* The browser surface the environment reads, named so a test can supply it
   without a real window. */
export interface BrowserGlobals {
  readonly window: {
    addEventListener(type: string, listener: () => void): void;
    removeEventListener(type: string, listener: () => void): void;
    setTimeout(callback: () => void, ms: number): TimerHandle;
    clearTimeout(handle: TimerHandle): void;
    setInterval(callback: () => void, ms: number): TimerHandle;
    clearInterval(handle: TimerHandle): void;
  };
  readonly document: {
    addEventListener(type: string, listener: () => void): void;
    removeEventListener(type: string, listener: () => void): void;
    readonly hidden: boolean;
  };
  readonly EventSource: (new (url: string) => EventSourceLike) | undefined;
  readonly now: () => number;
}

export function createBrowserEnvironment(g: BrowserGlobals): Environment {
  const listen = (target: Pick<BrowserGlobals['window'], 'addEventListener' | 'removeEventListener'>, type: string, listener: () => void) => {
    target.addEventListener(type, listener);
    return () => target.removeEventListener(type, listener);
  };
  const Source = g.EventSource;
  return {
    tabId: createTabId(Math.random, g.now()),
    clock: {
      now: g.now,
      setTimeout: (callback, ms) => g.window.setTimeout(callback, ms),
      clearTimeout: (handle) => g.window.clearTimeout(handle),
      setInterval: (callback, ms) => g.window.setInterval(callback, ms),
      clearInterval: (handle) => g.window.clearInterval(handle),
    },
    streamSupported: Source !== undefined,
    openStream() {
      if (!Source) throw new Error('EventSource is not available');
      return new Source('/api/stream');
    },
    onPageHide: (listener) => listen(g.window, 'pagehide', listener),
    onBecameVisible: (listener) =>
      listen(g.document, 'visibilitychange', () => {
        if (!g.document.hidden) listener();
      }),
  };
}

/* Builds the runtime for this document and starts nothing: the caller decides
   when (an effect's `acquire`). */
export function createBrowserRuntime(): BoardRuntime {
  const globals: BrowserGlobals = {
    window,
    document,
    EventSource: typeof EventSource === 'undefined' ? undefined : (EventSource as unknown as new (url: string) => EventSourceLike),
    now: () => Date.now(),
  };
  return createBoardRuntime({
    fetch: (url, init) => fetch(url, init),
    storage: createTransportStorage(createLegacyStorage(), window),
    env: createBrowserEnvironment(globals),
    search: window.location.search,
    doc: document,
  });
}
