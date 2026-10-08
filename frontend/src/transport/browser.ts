import type { FetchLike } from '../api/client';
import { createLegacyStorage, createTabId, type BackendProvider, type LegacyStorage } from '../storage';
import { createTransportStorage, type StorageEventTarget } from './legacyStorage';
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

export type BrowserRuntime = BoardRuntime & {
  /** The document's one storage instance, shared with the UI so in-tab consent and memo fallbacks agree when browser storage is blocked. */
  readonly storage: LegacyStorage;
};

export interface BrowserRuntimeOptions {
  readonly env?: Environment;
  readonly fetch?: FetchLike;
  readonly provider?: BackendProvider;
  readonly events?: StorageEventTarget;
  readonly search?: string;
  readonly doc?: Pick<Document, 'querySelector'> | null;
}

/* Builds the runtime for this document and starts nothing: the caller decides
   when (an effect's `acquire`). The one `LegacyStorage` it creates is exposed,
   because each instance holds its own in-tab fallbacks and a second instance
   would disagree with the transport about consent when storage is blocked. The
   options exist for tests; production passes none. */
export function createBrowserRuntime(options: BrowserRuntimeOptions = {}): BrowserRuntime {
  const globals: BrowserGlobals = {
    window,
    document,
    EventSource: typeof EventSource === 'undefined' ? undefined : (EventSource as unknown as new (url: string) => EventSourceLike),
    now: () => Date.now(),
  };
  const legacy = options.provider ? createLegacyStorage(options.provider) : createLegacyStorage();
  const runtime = createBoardRuntime({
    fetch: options.fetch ?? ((url, init) => fetch(url, init)),
    storage: createTransportStorage(legacy, options.events ?? window),
    env: options.env ?? createBrowserEnvironment(globals),
    search: options.search ?? window.location.search,
    doc: options.doc === undefined ? document : options.doc,
  });
  return Object.assign(runtime, { storage: legacy });
}
