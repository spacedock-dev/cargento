/*
 * The board and the pages the Sessions browser tests drive (DRC-4824).
 *
 * `startSessionsBoard` starts the REAL backend over `frontend/test/sessions_backend.py`: the React page through
 * the development supervisor (Vite serves modules, Python serves the document and every /api route). It is
 * `startBoard` of `support/browser.mjs` with the helper swapped, because that function names its helper.
 *
 * Nothing here reads a harness store, a model, a clipboard, a notification or a terminal. The page's clipboard
 * is replaced before it loads by `recordClipboard`, so a Copy press is observed and nothing is written.
 */
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { startReactWorld } from './support/world.mjs';
import { REPOSITORY, freePorts } from './support/browser.mjs';

export const SESSIONS_BACKEND = fileURLToPath(
  new URL('../test/sessions_backend.py', import.meta.url),
);

/** `{ react: { origin, dev, viteOrigin }, close }`. `close` stops exactly what was started here. */
export async function startSessionsBoard({ root = REPOSITORY } = {}) {
  const helper = join(root, 'frontend/test/sessions_backend.py');
  /* A sibling run can bind a port between the check that it is free and the bind itself, and then startup
     fails loudly rather than adopting someone else's listener. Try again on other ports, a few times. */
  const refused = [];
  for (let attempt = 0; ; attempt += 1) {
    const ports = await freePorts(2, refused);
    try {
      const dev = await startReactWorld({
        root,
        port: ports[0],
        vitePort: ports[1],
        backendHelper: helper,
      });
      return {
        react: { origin: dev.origin, viteOrigin: dev.viteOrigin, dev },
        close: () => dev.close(),
      };
    } catch (error) {
      refused.push(...ports);
      if (
        attempt >= 3 ||
        !/in use|EADDRINUSE|belongs to another|backend exited|readiness/i.test(
          String(error.message),
        )
      )
        throw error;
    }
  }
}

/* A page's clipboard, replaced before any script runs: a press is recorded in `window.__copied` and nothing
   reaches the machine's clipboard. */
export function recordClipboard(context) {
  return context.addInitScript(() => {
    globalThis.__copied = [];
    Object.defineProperty(globalThis.navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: (text) => {
          globalThis.__copied.push(String(text));
          return Promise.resolve();
        },
      },
    });
  });
}

/* The page's own resource use: every EventSource opened and closed, and every interval and timeout left
   standing, counted from the page's own calls so a navigation that leaked one is visible as growth. */
export function instrumentResources(context) {
  return context.addInitScript(() => {
    const live = { sources: 0, opened: 0, closed: 0, intervals: new Set(), timeouts: new Set() };
    globalThis.__resources = live;
    const NativeSource = globalThis.EventSource;
    if (NativeSource) {
      globalThis.EventSource = class extends NativeSource {
        constructor(...args) {
          super(...args);
          live.sources += 1;
          live.opened += 1;
        }
        close() {
          if (this.readyState !== 2) {
            live.sources -= 1;
            live.closed += 1;
          }
          super.close();
        }
      };
    }
    const setI = globalThis.setInterval,
      clrI = globalThis.clearInterval,
      setT = globalThis.setTimeout,
      clrT = globalThis.clearTimeout;
    globalThis.setInterval = (...args) => {
      const id = setI(...args);
      live.intervals.add(id);
      return id;
    };
    globalThis.clearInterval = (id) => {
      live.intervals.delete(id);
      return clrI(id);
    };
    globalThis.setTimeout = (fn, ms, ...rest) => {
      const id = setT(
        (...a) => {
          live.timeouts.delete(id);
          return fn(...a);
        },
        ms,
        ...rest,
      );
      live.timeouts.add(id);
      return id;
    };
    globalThis.clearTimeout = (id) => {
      live.timeouts.delete(id);
      return clrT(id);
    };
  });
}

export const resources = (page) =>
  page.evaluate(() => {
    const r = globalThis.__resources;
    return r
      ? { sources: r.sources, opened: r.opened, closed: r.closed, intervals: r.intervals.size }
      : null;
  });
