/*
 * The browser world the timeline and terminal tests share (DRC-4824).
 *
 * `startWorld` runs the REAL backend over the synthetic board and the synthetic read-only terminal
 * (`frontend/test/terminal_backend.py`), serving the React development page, whose entry is swapped for
 * `terminal-harness.tsx` inside a scratch copy of the tree, so no tracked file changes. A test then drives it in
 * Chromium and compares what a reader can observe with the previous interface's recorded observations
 * (`support/golden.mjs`). `CARGENTO_MUTATION` names one deliberate break in the scratch copy (see MUTATIONS in the
 * calling script); the run is then expected to FAIL.
 *
 * `openTracked` is `openPage` plus what these tests need and `openPage` does not record: every frame the
 * PAGE sent on a WebSocket, counted where the browser hands it to the network, and each socket's close.
 *
 * Nothing here reads a harness store, calls a model, touches the clipboard or notifications, or starts a
 * terminal: the "pane" prints only what the test appends to the control file. Every request leaving the
 * board's own origins is refused.
 */
import assert from 'node:assert/strict';
import { appendFile, cp, mkdtemp, readFile, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { PRODUCTION, startReactWorld } from './support/world.mjs';
import { freePorts, openPage, REPOSITORY, refreshReact } from './support/browser.mjs';

export { REPOSITORY, openPage, refreshReact };

/* The session the synthetic terminal registers for, and its project, as `terminal_backend.py` publishes them. */
export const TERMINAL = {
  harness: 'codex',
  sid: 'disposable-tmux-origin:1',
  project: 'gamma/term',
  banner: 'Synthetic read-only terminal ready',
  title: 'installed-smoke:0.0',
};
export const FOCUS = `${TERMINAL.harness}:${TERMINAL.sid}`;
const E = encodeURIComponent;
export const fragmentFor = (tab, focus = FOCUS) =>
  `#n=project:${E(TERMINAL.project)}${focus ? `:${E(focus)}` : ''}:${tab}`;

/* Waits until the synthetic terminal has registered, so a page opened next sees it registered. */
async function waitForRegistration(origin) {
  const deadline = Date.now() + 20000;
  const url = `${origin}/api/interaction/origin?harness=${E(TERMINAL.harness)}&sid=${E(TERMINAL.sid)}`;
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

export async function startWorld({
  mutations = {},
  mutation = process.env.CARGENTO_MUTATION || '',
} = {}) {
  /* Development mounts `terminal-harness.tsx` in a scratch copy. The production run serves the page readers get and the
     proofs reach the timeline and the terminal through the project page's tabs. Without a mutation that page is the
     tracked `react.html` itself; a mutation needs a scratch copy, packaged with the same build. */
  const shipped = PRODUCTION;
  const ownsRepository = shipped && !mutation;
  const copy = ownsRepository
    ? REPOSITORY
    : await mkdtemp(join(tmpdir(), 'cargento-terminal-browser-'));
  let dev = null;
  const world = { copy, mutation, shipped, close };
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
      if (!shipped)
        await writeFile(join(copy, 'frontend/src/main.tsx'), "import '../e2e/terminal-harness';\n");
      for (const [file, needle, replacement] of mutations[mutation] ?? []) {
        const path = join(copy, 'frontend', file);
        const text = await readFile(path, 'utf8');
        assert.ok(text.includes(needle), `mutation ${mutation}: needle not found in ${file}`);
        await writeFile(path, text.replace(needle, replacement));
      }
    }
    assert.ok(!mutation || mutations[mutation], `unknown mutation ${mutation}`);

    const helper = join(copy, 'frontend/test/terminal_backend.py');
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

/* What the pane prints, and what drops its stream. One JSON line per command, as the helper reads them. */
export const emit = (side, text) => appendFile(side.control, JSON.stringify({ text }) + '\n');
export const disconnect = (side) =>
  appendFile(side.control, JSON.stringify({ disconnect: true }) + '\n');
export const numbered = (from, to) =>
  Array.from(
    { length: to - from + 1 },
    (_, index) => `line ${String(from + index).padStart(3, '0')}\r\n`,
  ).join('');

/* `openPage` and the frames the page sent. The sockets list holds one record per WebSocket the page
   opened to the board: the frames it sent (which must be none on the terminal stream, since the server
   revokes the connection on any), the frames it received, and who closed it with which code. */
export async function openTracked(browser, origins, options) {
  const opened = await openPage(browser, origins, options);
  const inside = (url) =>
    origins.some((origin) => url.startsWith(origin.replace(/^http:/, 'ws:') + '/'));
  const sockets = [];
  /* A handler registered after `openPage`'s takes precedence for WebSockets, so this one decides every
     socket and `openPage`'s never sees one. */
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
