/*
 * Shared browser harness for the React-migration browser tests (DRC-4823 onward).
 *
 * `startBoard` runs the REAL backend over the synthetic board in `fixture_backend.py`: the React
 * page through the development supervisor (Vite serves modules, Python serves the document and
 * every /api route), and optionally the legacy page from the same helper, so a differential
 * test compares the two renderers against identical data. `openPage` returns a Chromium page
 * that refuses every request leaving the board's own origins and records what the page did.
 *
 * Ports are taken from the owned range only, after a bind check. Nothing here touches a real
 * harness store, a model, a clipboard, a notification or a terminal.
 */
import { execFileSync, spawn } from 'node:child_process';
import { mkdir, mkdtemp, rm } from 'node:fs/promises';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { LEGACY_LIVE } from './golden.mjs';
import { startReactWorld } from './world.mjs';
import { isolatedEnvironment } from '../../dev/protocol.mjs';

export const REPOSITORY = fileURLToPath(new URL('../../../', import.meta.url));
export const FIXTURE_BACKEND = fileURLToPath(new URL('./fixture_backend.py', import.meta.url));

/* The ports this migration may bind. 4553, 4563 and 4567 belong to running dashboards. */
export const OWNED_PORTS = [4581, 4582, 4583, 4584, 4585, 4586, 4594, 4595, 4597, 4598, 4599];

/* The fixture board's rows, as `fixture_backend.py` publishes them. Kept here so a test names a
   session without re-reading the Python. `sharedSid` is carried by both harnesses on purpose. */
export const BOARD = {
  sharedSid: 'shared-sid',
  colonSid: 'colon:sid',
  bareProjectSid: 'bare-project-sid',
  projects: ['alpha/app', 'beta/api', ''],
  sessions: [
    { harness: 'claude', sid: 'shared-sid', project: 'alpha/app', title: 'Alpha shared claude' },
    { harness: 'codex', sid: 'shared-sid', project: 'alpha/app', title: 'Alpha shared codex' },
    { harness: 'claude', sid: 'colon:sid', project: 'beta/api', title: null },
    { harness: 'codex', sid: 'bare-project-sid', project: '', title: 'No project label' },
    { harness: 'codex', sid: 'beta-working', project: 'beta/api', title: 'Beta working' },
  ],
};

function bindable(port) {
  return new Promise((resolve) => {
    const server = createServer();
    server.once('error', () => resolve(false));
    server.listen({ port, host: '127.0.0.1' }, () => server.close(() => resolve(true)));
  });
}

/* The first `count` owned ports that bind right now, skipping `taken`. A sibling builder can win
   the race between this check and the bind; the caller's own startup then fails loudly rather
   than adopting someone else's listener, and the run is simply repeated. */
export async function freePorts(count, taken = []) {
  const found = [];
  for (const port of OWNED_PORTS) {
    if (taken.includes(port) || found.includes(port)) continue;
    if (await bindable(port)) found.push(port);
    if (found.length === count) return found;
  }
  throw new Error(`Fewer than ${count} owned ports are free (${OWNED_PORTS.join(', ')}).`);
}

function resolvePython() {
  const name =
    process.env.CARGENTO_TEST_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
  return execFileSync(name, ['-I', '-c', 'import sys; print(sys.executable)'], {
    encoding: 'utf8',
    timeout: 5000,
  }).trim();
}

async function waitForHealth(origin, child, deadlineMs = 15000) {
  const deadline = Date.now() + deadlineMs;
  for (;;) {
    if (child.exitCode !== null)
      throw new Error('Legacy fixture backend exited: ' + (child.diagnostic || ''));
    try {
      const response = await fetch(origin + '/api/health', { signal: AbortSignal.timeout(1000) });
      const health = await response.json();
      if (health.ok === true && health.pid === child.pid) return;
      throw new Error('Port belongs to another process.');
    } catch (error) {
      if (Date.now() > deadline)
        throw new Error(
          'Legacy fixture backend never became ready: ' + (child.diagnostic || error.message),
          { cause: error },
        );
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
  }
}

/**
 * Start the board. Returns `{ react, legacy, close }`: each is `{ origin }` (legacy only when
 * asked, and only while `CARGENTO_LEGACY` is `live` or `record`). `close()` stops exactly the processes started here and removes only their scratch.
 */
export async function startBoard({ legacy = false, root = REPOSITORY } = {}) {
  // In replay the legacy page is read from a recording (`support/golden.mjs`); a proof that still asks for
  // one has missed a seam, and starting a backend nobody should read would hide that.
  if (legacy && !LEGACY_LIVE)
    throw new Error(
      'startBoard({ legacy: true }) in replay mode: ask for it only when golden.live.',
    );
  const [pythonPort, vitePort, legacyPort] = await freePorts(legacy ? 3 : 2);
  // The helper that runs is the one under `root`, so a scratch copy of the tree (a mutation check, or a
  // contributor's experiment) serves its own sources and its own runtime end to end.
  const helper = join(root, 'frontend/e2e/support/fixture_backend.py');
  const dev = await startReactWorld({ root, port: pythonPort, vitePort, backendHelper: helper });
  const board = { react: { origin: dev.origin, dev }, legacy: null, close };
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
      scratch = await mkdtemp(join(tmpdir(), 'cargento-shell-legacy-'));
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
        '--no-focus',
        '--no-events',
        '--no-spacedock',
        '--no-tripwires',
        '--no-reach',
        '--no-ask',
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

/**
 * A page that may only talk to `origins` (plus data: URLs), with a log of what it did.
 * `log.externalRequests` must stay empty; `log.nonGet` lists every request that was not a GET.
 */
export async function openPage(browser, origins, { viewport, reducedMotion, locale } = {}) {
  const allowed = [].concat(origins);
  const context = await browser.newContext({ viewport, reducedMotion, locale });
  const log = { consoleErrors: [], pageErrors: [], externalRequests: [], nonGet: [], requests: [] };
  const inside = (url) =>
    url.startsWith('data:') ||
    allowed.some((origin) => url.startsWith(origin + '/') || url === origin);
  await context.route('**/*', (route) => {
    const url = route.request().url();
    if (inside(url)) return route.continue();
    log.externalRequests.push(url);
    return route.abort();
  });
  await context.routeWebSocket('**/*', (socket) => {
    const target = socket.url().replace(/^ws:/, 'http:');
    if (inside(target)) return socket.connectToServer();
    log.externalRequests.push(socket.url());
    return socket.close({ code: 1008 });
  });
  const page = await context.newPage();
  page.on('console', (message) => {
    if (message.type() === 'error') log.consoleErrors.push(message.text());
  });
  page.on('pageerror', (error) => log.pageErrors.push(error.message));
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.protocol === 'data:') return;
    log.requests.push({ method: request.method(), path: url.pathname + url.search });
    if (request.method() !== 'GET')
      log.nonGet.push({ method: request.method(), path: url.pathname });
  });
  const count = (predicate) => log.requests.filter(predicate).length;
  return {
    page,
    context,
    log,
    /** GET /api/data, GET /api/stream and every non-GET since the page was opened (or `reset()`). */
    counts: () => ({
      data: count((entry) => entry.method === 'GET' && entry.path.startsWith('/api/data')),
      stream: count((entry) => entry.path.startsWith('/api/stream')),
      nonGet: log.nonGet.length,
    }),
    reset() {
      log.requests.length = 0;
      log.nonGet.length = 0;
    },
    close: () => context.close(),
  };
}

/**
 * What a reader can observe of the shell, read from the DOM and nothing else: the fragment,
 * the document title, the current primary item, the breadcrumb sentence and the history depth.
 * The same function runs against the legacy page and the React page.
 */
/* A render follows its event by a frame or more, so a read taken the instant after a click can still show the
   previous view on a slow runner. The shell counts as observed once two reads 80 ms apart agree. */
export async function observeShell(page) {
  let previous = await readShell(page);
  for (let waited = 0; waited < 4000; waited += 80) {
    await new Promise((resolve) => setTimeout(resolve, 80));
    const next = await readShell(page);
    if (JSON.stringify(next) === JSON.stringify(previous)) return next;
    previous = next;
  }
  throw Error('The shell kept changing for four seconds.');
}

function readShell(page) {
  return page.evaluate(() => {
    const { document, location, history } = globalThis;
    const text = (node) => (node ? node.textContent.replace(/\s+/g, ' ').trim() : null);
    const current = document.querySelector('nav[aria-label="Primary"] [aria-current="page"]');
    return {
      hash: location.hash,
      search: location.search,
      title: document.title,
      current: text(current),
      primary: [...document.querySelectorAll('nav[aria-label="Primary"] a')].map(text),
      breadcrumb: text(document.querySelector('nav[aria-label="Breadcrumb"]')),
      historyLength: history.length,
    };
  });
}

/** Resolves once the shell's primary navigation is on the page, for either renderer. */
export function waitForShell(page) {
  return page.locator('nav[aria-label="Primary"]').waitFor();
}

/**
 * What the focused element is called to a reader: its aria-label, else its text, else its tag. `null` when
 * nothing but the page itself holds focus, which is what a control that vanished under the reader leaves.
 */
export function focusedLabel(page) {
  return page.evaluate(() => {
    const active = globalThis.document.activeElement;
    if (
      !active ||
      active === globalThis.document.body ||
      active === globalThis.document.documentElement
    )
      return null;
    const name = active.getAttribute('aria-label') || active.textContent || active.tagName;
    return name.replace(/\s+/g, ' ').trim().slice(0, 80) || active.tagName;
  });
}

/**
 * Press Tab from the top of the page until the control called `label` holds focus; the count of presses.
 * The starting point is reset first: Chromium otherwise continues from wherever the last control was,
 * which would make the count depend on the step before. Fails with the labels it walked past.
 */
export async function tabTo(page, label, { max = 200 } = {}) {
  await page.evaluate(() => {
    const { document } = globalThis;
    document.activeElement?.blur?.();
    document.body.setAttribute('tabindex', '-1');
    document.body.focus();
    document.body.removeAttribute('tabindex');
    globalThis.scrollTo(0, 0);
  });
  const walked = [];
  for (let presses = 1; presses <= max; presses += 1) {
    await page.keyboard.press('Tab');
    const now = await focusedLabel(page);
    walked.push(now);
    if (now === label) return presses;
  }
  throw new Error(
    `Tab never reached "${label}" in ${max} presses; it walked: ${JSON.stringify(walked.slice(-12))}`,
  );
}

/* A live update through the React page's own refresh path. The harness exposes the runtime, so a refresh is the
   manual one; the shipped page exposes nothing, so another tab's announcement stands in, which is how the page is
   told in real use: a storage event on the revision key wakes it to read the board. */
let wakes = 0;
export function refreshReact(page, shipped) {
  wakes += 1;
  return shipped
    ? page.evaluate(
        (number) =>
          globalThis.dispatchEvent(
            new globalThis.StorageEvent('storage', {
              key: 'cargento.next.revision',
              newValue: `9999999999.${String(number)}`,
            }),
          ),
        wakes,
      )
    : page.evaluate(() => globalThis.__harness.shell.runtime.refresh({ manual: true }));
}
