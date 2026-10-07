import assert from 'node:assert/strict';
import { mkdtemp, cp, mkdir, rm, readFile, realpath } from 'node:fs/promises';
import { spawn, execFileSync } from 'node:child_process';
import { createInterface } from 'node:readline';
import { tmpdir } from 'node:os';
import { join, relative, isAbsolute } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';

const root = fileURLToPath(new URL('../../', import.meta.url));
const pythonName = process.env.CARGENTO_TEST_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const python = execFileSync(pythonName, ['-c', 'import sys; print(sys.executable)'], { encoding: 'utf8', timeout: 5000 }).trim();
const scratch = await mkdtemp(join(tmpdir(), 'cargento-installed-browser-'));
let browser;
const receipts = [];

async function backend(plugin, mode, terminal, use) {
  const args = [join(root, 'frontend/test/installed_backend.py'), '--plugin-root', plugin, '--frontend', mode, '--port', terminal ? '4584' : '4583'];
  if (terminal) args.push('--terminal-fixture');
  if (mode === 'react') args.push('--focus-token', 'abcdef');
  const child = spawn(python, args, { cwd: scratch, stdio: ['pipe', 'pipe', 'pipe'],
    env: { ...process.env, PATH: join(scratch, 'no-executables'), HOME: scratch,
      USERPROFILE: scratch, CARGENTO_HOME: join(scratch, 'state'), PYTHONPATH: '', PYTHONNOUSERSITE: '1' } });
  let stderr = '';
  child.stderr.on('data', chunk => { stderr = (stderr + chunk).slice(-4000); });
  const exit = new Promise(resolve => child.once('exit', (code, signal) => resolve({ code, signal })));
  const lines = createInterface({ input: child.stdout });
  child.stdin.on('error', () => {});
  let failure;
  try {
    const ready = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(Error('Installed backend readiness deadline: ' + stderr)), 15000);
      const error = message => { clearTimeout(timer); reject(Error(message + ': ' + stderr)); };
      child.once('error', failure => error(failure.message));
      child.once('exit', () => error('Installed backend exited before readiness'));
      lines.once('line', line => {
        clearTimeout(timer);
        try { resolve(JSON.parse(line)); } catch { reject(Error('Installed backend returned invalid readiness')); }
      });
    });
    assert.equal(ready.ready, true);
    assert.equal(ready.frontend, mode);
    const imported = relative(await realpath(plugin), await realpath(ready.runtime));
    assert.ok(!imported.startsWith('..') && !isAbsolute(imported), 'runtime import must come from installed copy');
    await use(ready);
  } catch (error) { failure = error; } finally {
    lines.close();
    child.stdin.end();
    let timer;
    const stopped = await Promise.race([exit, new Promise(resolve => { timer = setTimeout(() => resolve(null), 5000); })]);
    clearTimeout(timer);
    if (!stopped) {
      child.kill('SIGKILL');
      failure ||= Error('Installed backend required forced cleanup: ' + stderr);
      await exit;
    }
    if (stopped && stopped.code !== 0) failure ||= Error('Installed backend exit ' + stopped.code + ': ' + stderr);
  }
  if (failure) throw failure;
}

async function contextFor(port) {
  const context = await browser.newContext();
  const external = [], errors = [], requests = [], frames = [];
  const origin = `http://127.0.0.1:${port}`;
  await context.route('**/*', route => {
    const url = route.request().url();
    if (url.startsWith(origin + '/') || url.startsWith('data:')) return route.continue();
    external.push(url);
    return route.abort();
  });
  await context.routeWebSocket('**/*', socket => {
    if (!socket.url().startsWith(`ws://127.0.0.1:${port}/`)) {
      external.push(socket.url());
      return socket.close({ code: 1008, reason: 'external connections denied' });
    }
    socket.connectToServer();
  });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => requests.push(request.url()));
  page.on('websocket', socket => socket.on('framereceived', frame => frames.push(frame.payload)));
  return { context, page, external, errors, requests, frames, origin };
}

try {
  const plugin = join(scratch, 'cargento');
  await cp(join(root, 'cargento'), plugin, { recursive: true });
  await mkdir(join(scratch, 'no-executables'));
  browser = await chromium.launch();
  await backend(plugin, 'react', false, async ready => {
    const probe = await contextFor(ready.port);
    try {
      await probe.page.goto(probe.origin + '/');
      await probe.page.getByRole('heading', { level: 1, name: 'Cargento frontend preview' }).waitFor();
      await probe.page.getByText(/session views are not available here yet/i).waitFor();
      const structure = await probe.page.evaluate(() => ({ scripts: globalThis.document.scripts.length,
        roots: globalThis.document.querySelectorAll('#root').length,
        fonts: globalThis.document.fonts.size, focus: globalThis.document.querySelectorAll('meta[name="cargento-focus"]').length }));
      assert.equal(structure.scripts, 1);
      assert.equal(structure.roots, 1);
      assert.equal(structure.fonts, 15);
      assert.equal(structure.focus, 1);
      assert.equal(await probe.page.locator('head meta[name="cargento-focus"]').getAttribute('content'), 'abcdef');
      const metadata = JSON.parse(await readFile(join(plugin, 'skills/cargento/cargento_runtime/web/react.integrity.json'), 'utf8'));
      const data = await (await probe.context.request.get(probe.origin + '/api/data')).json();
      assert.equal(data.frontend, 'react');
      assert.equal(data.build, 'react-' + metadata.document.sha256.slice(0, 16));
      assert.deepEqual(probe.external, []);
      assert.deepEqual(probe.errors, []);
      assert.ok(probe.requests.every(url => url.startsWith('data:') || new URL(url).pathname === '/'));
      receipts.push({ mode: 'react', bytes: metadata.document.bytes, fonts: structure.fonts,
        embeddedCore: true, externalRequests: 0, nodeHiddenFromPython: true });
    } finally { await probe.context.close(); }
  });
  await backend(plugin, 'legacy', true, async ready => {
    const probe = await contextFor(ready.port);
    try {
      await probe.page.goto(probe.origin + '/' + ready.terminal_fragment);
      await probe.page.getByRole('button', { name: 'Open terminal', exact: true }).click();
      await probe.page.locator('#pc-terminal-screen .xterm').waitFor();
      await probe.page.waitForFunction("typeof projectTerminalSequence !== 'undefined' && projectTerminalSequence > 0");
      const content = await probe.page.evaluate(`(() => {
        const rows=[]; for(let i=0;i<projectTerminal.buffer.active.length;i++) rows.push(projectTerminal.buffer.active.getLine(i).translateToString());
        return rows.join('\\n');
      })()`);
      assert.ok(content.includes('Installed synthetic read-only terminal'));
      assert.ok(probe.requests.some(url => new URL(url).pathname === '/assets/xterm.js'));
      assert.ok(probe.requests.some(url => new URL(url).pathname === '/assets/xterm.css'));
      assert.ok(probe.frames.length > 0);
      assert.deepEqual(probe.external, []);
      assert.deepEqual(probe.errors, []);
      receipts.push({ mode: 'legacy', terminal: ready.terminal_fixture, localVendorAssets: true,
        actualReadOnlyViewportOutput: true, externalRequests: 0, nodeHiddenFromPython: true });
    } finally { await probe.context.close(); }
  });
  console.log(JSON.stringify({ installed: receipts }, null, 2));
} finally {
  if (browser) await browser.close();
  await rm(scratch, { recursive: true, force: true });
}
