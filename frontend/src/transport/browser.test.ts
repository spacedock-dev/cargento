import { describe, expect, it, vi } from 'vitest';
import { createBrowserEnvironment, type BrowserGlobals } from './browser';

function globals(options: { hidden?: boolean; withEventSource?: boolean } = {}) {
  const windowListeners = new Map<string, Set<() => void>>();
  const documentListeners = new Map<string, Set<() => void>>();
  const track = (map: Map<string, Set<() => void>>) => ({
    addEventListener: (type: string, listener: () => void) => void (map.get(type) ?? map.set(type, new Set()).get(type))?.add(listener),
    removeEventListener: (type: string, listener: () => void) => void map.get(type)?.delete(listener),
  });
  const opened: string[] = [];
  class FakeSource {
    readyState = 0;
    constructor(readonly url: string) {
      opened.push(url);
    }
    close() {
      this.readyState = 2;
    }
    addEventListener() {
      /* unused here */
    }
  }
  const state = { hidden: options.hidden ?? false };
  const g: BrowserGlobals = {
    window: { ...track(windowListeners), setTimeout: vi.fn(), clearTimeout: vi.fn(), setInterval: vi.fn(), clearInterval: vi.fn() },
    document: {
      ...track(documentListeners),
      get hidden() {
        return state.hidden;
      },
    },
    EventSource: options.withEventSource === false ? undefined : (FakeSource as unknown as BrowserGlobals['EventSource']),
    now: () => 4242,
  };
  const count = (map: Map<string, Set<() => void>>, type: string) => map.get(type)?.size ?? 0;
  return {
    g,
    state,
    opened,
    windowListeners,
    documentListeners,
    fire: (map: Map<string, Set<() => void>>, type: string) => {
      for (const listener of [...(map.get(type) ?? [])]) listener();
    },
    count,
  };
}

describe('browser environment', () => {
  it('names the tab with the released random-and-timestamp shape', () => {
    const env = createBrowserEnvironment(globals().g);
    expect(env.tabId).toMatch(/^[a-z0-9]+-4242$/);
  });

  it('opens the stream route and reports support from the constructor’s presence', () => {
    const supported = globals();
    const env = createBrowserEnvironment(supported.g);
    expect(env.streamSupported).toBe(true);
    env.openStream();
    expect(supported.opened).toEqual(['/api/stream']);
    expect(createBrowserEnvironment(globals({ withEventSource: false }).g).streamSupported).toBe(false);
  });

  it('adds and removes its pagehide listener', () => {
    const t = globals();
    const env = createBrowserEnvironment(t.g);
    const off = env.onPageHide(() => undefined);
    expect(t.count(t.windowListeners, 'pagehide')).toBe(1);
    off();
    expect(t.count(t.windowListeners, 'pagehide')).toBe(0);
  });

  it('reports a visibility change only when the page is visible', () => {
    const t = globals({ hidden: true });
    const env = createBrowserEnvironment(t.g);
    const seen = vi.fn();
    const off = env.onBecameVisible(seen);
    t.fire(t.documentListeners, 'visibilitychange');
    expect(seen).not.toHaveBeenCalled();
    t.state.hidden = false;
    t.fire(t.documentListeners, 'visibilitychange');
    expect(seen).toHaveBeenCalledOnce();
    off();
    expect(t.count(t.documentListeners, 'visibilitychange')).toBe(0);
  });

  it('delegates timers to the window and time to the supplied clock', () => {
    const t = globals();
    const env = createBrowserEnvironment(t.g);
    expect(env.clock.now()).toBe(4242);
    const callback = vi.fn();
    env.clock.setTimeout(callback, 5);
    env.clock.setInterval(callback, 7);
    expect(t.g.window.setTimeout).toHaveBeenCalledWith(callback, 5);
    expect(t.g.window.setInterval).toHaveBeenCalledWith(callback, 7);
  });
});
