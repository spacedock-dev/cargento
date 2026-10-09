/*
 * The board and the pages the Intent browser tests drive.
 *
 * `startIntentBoard` starts the REAL backend over `frontend/test/intent_backend.py`: the React page through
 * the development supervisor (Vite serves modules, Python serves the document and every /api route), and the
 * legacy page from the same helper, so a differential run compares the two renderers over one backend. It is
 * `startSessionsBoard` with the helper swapped, because that function names its helper.
 *
 * Nothing here reads a harness store, a model, a clipboard, a notification or a terminal. The transcripts the
 * helper writes live in the scratch tree the launcher points every harness at.
 */
import { execFileSync, spawn } from 'node:child_process';
import { mkdir, mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { isolatedEnvironment } from '../dev/protocol.mjs';
import { startReactWorld } from './support/world.mjs';
import { REPOSITORY, freePorts } from './support/browser.mjs';

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
      throw new Error('Legacy intent backend exited: ' + (child.diagnostic || ''));
    try {
      const health = await (
        await fetch(origin + '/api/health', { signal: AbortSignal.timeout(1000) })
      ).json();
      if (health.ok === true && health.pid === child.pid) return;
      throw new Error('Port belongs to another process.');
    } catch (error) {
      if (Date.now() > deadline)
        throw new Error(
          'Legacy intent backend never became ready: ' + (child.diagnostic || error.message),
          { cause: error },
        );
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
  }
}

/** `{ react: { origin, dev }, legacy: { origin } | null, close }`. `close` stops exactly what was started here. */
export async function startIntentBoard({ legacy = false, root = REPOSITORY } = {}) {
  const helper = join(root, 'frontend/test/intent_backend.py');
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
      scratch = await mkdtemp(join(tmpdir(), 'cargento-intent-legacy-'));
      await mkdir(join(scratch, 'no-executables'));
      const args = [
        helper,
        '--frontend',
        'legacy',
        '--host',
        '127.0.0.1',
        '--port',
        String(ports[2]),
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
      const origin = `http://127.0.0.1:${ports[2]}`;
      await waitForHealth(origin, child);
      board.legacy = { origin };
    } catch (error) {
      await close();
      throw error;
    }
  }
  return board;
}

/* A request the page itself would make, made from outside it, so a test can set the store up (or move the
   board's revision) identically on both backends without driving a page. */
export async function call(origin, method, path, body) {
  const response = await fetch(origin + path, {
    method,
    ...(body
      ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
      : {}),
    signal: AbortSignal.timeout(15000),
  });
  const text = await response.text();
  try {
    return { status: response.status, body: JSON.parse(text) };
  } catch {
    return { status: response.status, body: text };
  }
}
