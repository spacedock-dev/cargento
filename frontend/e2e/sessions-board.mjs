/*
 * The board and the pages the Sessions browser tests drive (DRC-4824).
 *
 * `startSessionsBoard` starts the REAL backend over `frontend/test/sessions_backend.py`: the React page through
 * the development supervisor (Vite serves modules, Python serves the document and every /api route), and the
 * legacy page from the same helper, so a differential run compares the two renderers over one board. It is
 * `startBoard` of `support/browser.mjs` with the helper swapped, because that function names its helper.
 *
 * Nothing here reads a harness store, a model, a clipboard, a notification or a terminal. The page's clipboard
 * is replaced before it loads by `recordClipboard`, so a Copy press is observed and nothing is written.
 */
import { spawn } from 'node:child_process';
import { mkdir, mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import { startReactWorld } from './support/world.mjs';
import { isolatedEnvironment } from '../dev/protocol.mjs';
import { REPOSITORY, freePorts } from './support/browser.mjs';

export const SESSIONS_BACKEND = fileURLToPath(
  new URL('../test/sessions_backend.py', import.meta.url),
);

function resolvePython() {
  const name =
    process.env.CARGENTO_TEST_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
  return execFileSync(name, ['-I', '-c', 'import sys; print(sys.executable)'], {
    encoding: 'utf8',
    timeout: 5000,
  }).trim();
}

async function waitForHealth(origin, child, deadlineMs = 20000) {
  const deadline = Date.now() + deadlineMs;
  for (;;) {
    if (child.exitCode !== null)
      throw new Error('Legacy sessions backend exited: ' + (child.diagnostic || ''));
    try {
      const health = await (
        await fetch(origin + '/api/health', { signal: AbortSignal.timeout(1000) })
      ).json();
      if (health.ok === true && health.pid === child.pid) return;
      throw new Error('Port belongs to another process.');
    } catch (error) {
      if (Date.now() > deadline)
        throw new Error(
          'Legacy sessions backend never became ready: ' + (child.diagnostic || error.message),
          { cause: error },
        );
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
  }
}

/** `{ react: { origin, dev, viteOrigin }, legacy: { origin } | null, close }`. `close` stops exactly what was started here. */
export async function startSessionsBoard({ legacy = false, root = REPOSITORY } = {}) {
  const helper = join(root, 'frontend/test/sessions_backend.py');
  /* A sibling run can bind a port between the check that it is free and the bind itself, and then startup
     fails loudly rather than adopting someone else's listener. Try again on other ports, a few times. */
  const refused = [];
  let ports;
  let dev;
  for (let attempt = 0; ; attempt += 1) {
    ports = await freePorts(legacy ? 3 : 2, refused);
    try {
      dev = await startReactWorld({
        root,
        port: ports[0],
        vitePort: ports[1],
        backendHelper: helper,
      });
      break;
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
  const legacyPort = ports[2];
  const board = {
    react: { origin: dev.origin, viteOrigin: dev.viteOrigin, dev },
    legacy: null,
    close,
  };
  let child = null;
  let scratch = null;
  async function close() {
    if (child && child.exitCode === null) {
      child.kill('SIGTERM');
      await new Promise((resolve) => {
        const timer = setTimeout(() => {
          child.kill('SIGKILL');
          resolve();
        }, 3000);
        child.once('close', () => {
          clearTimeout(timer);
          resolve();
        });
      });
    }
    await dev.close();
    if (scratch) await rm(scratch, { recursive: true, force: true });
  }
  if (legacy) {
    try {
      scratch = await mkdtemp(join(tmpdir(), 'cargento-sessions-legacy-'));
      await mkdir(join(scratch, 'no-executables'));
      const args = [
        helper,
        '--frontend',
        'legacy',
        '--host',
        '127.0.0.1',
        '--port',
        String(legacyPort),
        '--no-observer-model',
        '--no-usage',
        '--no-git',
        '--no-spacedock',
        '--no-tripwires',
        '--no-reach',
        '--no-history',
      ];
      child = spawn(resolvePython(), args, {
        cwd: root,
        env: isolatedEnvironment(scratch, process.env),
        stdio: ['ignore', 'pipe', 'pipe'],
      });
      child.stderr.on('data', (chunk) => {
        child.diagnostic = ((child.diagnostic || '') + chunk).slice(-3000);
      });
      child.stdout.resume();
      const origin = `http://127.0.0.1:${legacyPort}`;
      await waitForHealth(origin, child);
      board.legacy = { origin };
    } catch (error) {
      await close();
      throw error;
    }
  }
  return board;
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
