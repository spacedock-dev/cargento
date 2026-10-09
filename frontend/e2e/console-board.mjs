/*
 * The world the Console, Decisions, steering and tripwire browser tests share.
 *
 * `startConsoleWorld` runs the REAL backend over the same synthetic board (`frontend/test/console_backend.py`:
 * asks, a stored history, a quota provider, one workflow stage source and a synthetic read-only terminal) serving
 * the React development page, whose entry is swapped for `console-harness.tsx` inside a scratch copy of the tree,
 * so no tracked file changes. A test then drives the React page in one Chromium and compares what a reader can
 * observe with the previous interface's recorded readings (`support/golden.mjs`). `CARGENTO_MUTATION` names one deliberate
 * break in the scratch copy (see MUTATIONS in the calling script); the run is then expected to FAIL.
 *
 * Nothing here reads a harness store, calls a model, fetches a quota, touches the clipboard or notifications,
 * or starts a terminal: the "pane" prints only what the test appends to its control file, and the one native
 * action a session could cause (raising a terminal) is inert. Every request leaving the board's own origins is
 * refused by `openPage`.
 */
import assert from 'node:assert/strict';
import { cp, mkdtemp, readFile, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { PRODUCTION, startReactWorld } from './support/world.mjs';
import { freePorts, openPage, REPOSITORY } from './support/browser.mjs';

export { REPOSITORY, openPage };

/* What the board publishes, as `console_backend.py` writes it. */
export const BOARD = {
  project: 'alpha/app',
  other: 'beta/api',
  live: { harness: 'claude', sid: 'live-work' },
  gate: { harness: 'claude', sid: 'gate-open' },
  workflow: { harness: 'claude', sid: 'workflow-run' },
  terminal: {
    harness: 'codex',
    sid: 'disposable-tmux-origin:1',
    banner: 'Synthetic read-only terminal ready',
  },
  stage: { id: 'ab'.repeat(32), workflow: 'Ship the queue' },
};
const E = encodeURIComponent;
export const fragmentFor = (tab, focus = null, project = BOARD.project) =>
  `#n=project:${E(project)}${focus ? `:${E(`${focus.harness}:${focus.sid}`)}` : ''}${tab ? `:${tab}` : ''}`;

/* Waits until the synthetic terminal has registered, so a page opened next sees it registered. */
async function waitForRegistration(origin) {
  const deadline = Date.now() + 25000;
  const url = `${origin}/api/interaction/origin?harness=${E(BOARD.terminal.harness)}&sid=${E(BOARD.terminal.sid)}`;
  for (;;) {
    try {
      const answer = await (await fetch(url, { signal: AbortSignal.timeout(1000) })).json();
      if (answer.state === 'registered') return;
    } catch {
      /* not serving yet */
    }
    if (Date.now() > deadline)
      throw new Error('The synthetic terminal never registered at ' + origin);
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
}

export async function startConsoleWorld({
  mutations = {},
  mutation = process.env.CARGENTO_MUTATION || '',
  // false serves the shipped page (the project views the slots are wired into) instead of the harness. The production
  // run serves it by default, so every console surface is proven on the page readers get; development keeps the harness.
  harness = !PRODUCTION,
} = {}) {
  // Without a mutation the shipped page is the tracked `react.html` itself, so no scratch copy is made.
  const ownsRepository = !harness && !mutation && PRODUCTION;
  const copy = ownsRepository
    ? REPOSITORY
    : await mkdtemp(join(tmpdir(), 'cargento-console-browser-'));
  let dev = null;
  const world = { copy, mutation, close };
  async function close() {
    if (dev) await dev.close();
    if (!ownsRepository) await rm(copy, { recursive: true, force: true });
  }
  try {
    if (!ownsRepository) {
      await cp(join(REPOSITORY, 'frontend'), join(copy, 'frontend'), {
        recursive: true,
        filter: (path) =>
          !path.includes('/fixtures') &&
          !path.includes('/test-results') &&
          !path.includes('__pycache__'),
      });
      await cp(join(REPOSITORY, 'cargento'), join(copy, 'cargento'), {
        recursive: true,
        filter: (path) =>
          !path.includes('/tests/') && !path.endsWith('/tests') && !path.includes('__pycache__'),
      });
      await symlink(
        join(REPOSITORY, 'node_modules'),
        join(copy, 'node_modules'),
        process.platform === 'win32' ? 'junction' : 'dir',
      );
      if (harness)
        await writeFile(join(copy, 'frontend/src/main.tsx'), "import '../e2e/console-harness';\n");
      for (const [file, needle, replacement] of mutations[mutation] ?? []) {
        const path = join(copy, 'frontend', file);
        const text = await readFile(path, 'utf8');
        assert.ok(text.includes(needle), `mutation ${mutation}: needle not found in ${file}`);
        await writeFile(path, text.replace(needle, replacement));
      }
    }
    assert.ok(!mutation || mutations[mutation], `unknown mutation ${mutation}`);

    const helper = join(copy, 'frontend/test/console_backend.py');
    /* A sibling run can bind a port between the check that it is free and the bind itself; startup then fails
       loudly rather than adopting someone else's listener. Try again on other ports, a few times. */
    const refused = [];
    let ports;
    for (let attempt = 0; ; attempt += 1) {
      ports = await freePorts(2, refused);
      try {
        dev = await startReactWorld({
          root: copy,
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
    world.react = {
      origin: dev.origin,
      viteOrigin: dev.viteOrigin,
      control: join(dev.scratch, 'state/terminal-fixture/control.ndjson'),
    };

    await waitForRegistration(world.react.origin);
    return world;
  } catch (error) {
    await close();
    throw error;
  }
}

/* `openPage` and the frames the page sent. The sockets list holds one record per WebSocket the page opened to
   the board: the frames it sent (which must be none on the terminal stream, since the server revokes the
   connection on any), the frames it received, and who closed it with which code. */
export async function openTracked(browser, origins, options) {
  const opened = await openPage(browser, origins, options);
  const inside = (url) =>
    origins.some((origin) => url.startsWith(origin.replace(/^http:/, 'ws:') + '/'));
  const sockets = [];
  await opened.context.routeWebSocket('**/*', (ws) => {
    if (!inside(ws.url())) {
      opened.log.externalRequests.push(ws.url());
      return ws.close({ code: 1008 });
    }
    const record = {
      url: ws.url(),
      path: new URL(ws.url()).pathname,
      sent: [],
      received: 0,
      closed: null,
    };
    sockets.push(record);
    const server = ws.connectToServer();
    ws.onMessage((message) => {
      record.sent.push(typeof message === 'string' ? message : '<binary>');
      server.send(message);
    });
    server.onMessage((message) => {
      record.received += 1;
      ws.send(message);
    });
    ws.onClose((code, reason) => {
      record.closed = { by: 'page', code, reason };
      server.close({ code, reason });
    });
    server.onClose((code, reason) => {
      record.closed = { by: 'server', code, reason };
      ws.close({ code, reason });
    });
  });
  const stream = () => sockets.filter((socket) => socket.path === '/api/interaction/stream');
  const requestsTo = (prefix) =>
    opened.log.requests.filter((entry) => entry.path.startsWith(prefix));
  return { ...opened, sockets, stream, requestsTo };
}
