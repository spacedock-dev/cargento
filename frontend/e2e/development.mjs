import assert from 'node:assert/strict';
import { mkdtemp, cp, symlink, readFile, writeFile, mkdir, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';
import { startDevelopment } from '../dev/supervisor.mjs';

const repository = fileURLToPath(new URL('../../', import.meta.url));
const copy = await mkdtemp(join(tmpdir(), 'cargento-development-browser-'));
let dev, browser, context;
const external = [], errors = [];
const failures = [];
try {
  await cp(join(repository, 'frontend'), join(copy, 'frontend'), { recursive: true });
  await cp(join(repository, 'cargento'), join(copy, 'cargento'), { recursive: true,
    filter: path => !path.includes('/tests/') && !path.endsWith('/tests') && !path.includes('__pycache__') });
  await symlink(join(repository, 'node_modules'), join(copy, 'node_modules'), process.platform === 'win32' ? 'junction' : 'dir');
  const component = join(copy, 'frontend/src/MigrationShell.tsx');
  const original = await readFile(component, 'utf8');
  const fixture = "import { useState } from 'react';\n" + original.replace('  return (', "  const [count, setCount] = useState(0);\n  return (")
    .replace('<main>', '<main><button onClick={() => setCount(count + 1)}>Fixture count {count}</button>');
  await writeFile(component, fixture);
  dev = await startDevelopment({ root: copy, port: 4587, vitePort: 4588 });
  browser = await chromium.launch();
  context = await browser.newContext();
  await context.route('**/*', route => {
    const url = route.request().url();
    if ([dev.origin, dev.viteOrigin].some(origin => url.startsWith(origin + '/')) || url.startsWith('data:')) return route.continue();
    external.push(url); return route.abort();
  });
  await context.routeWebSocket('**/*', socket => {
    if (socket.url().startsWith(dev.viteOrigin.replace('http:', 'ws:') + '/__cargento_hmr')) socket.connectToServer();
    else { external.push(socket.url()); socket.close({ code: 1008 }); }
  });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  page.on('response', response => { if (response.status() >= 400) failures.push({ url: response.url(), status: response.status() }); });
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  await page.goto(dev.origin);
  await page.getByRole('heading', { name: 'Cargento frontend preview' }).waitFor();
  assert.equal(await page.evaluate(() => globalThis.document.fonts.size), 15);
  await page.getByRole('button', { name: 'Fixture count 0' }).click();
  await page.evaluate(() => { globalThis.__devDocumentSentinel = 'same document'; });
  await writeFile(component, fixture.replace('Cargento frontend preview', 'Hot refresh verified'));
  await page.getByRole('heading', { name: 'Hot refresh verified' }).waitFor();
  await page.getByRole('button', { name: 'Fixture count 1' }).waitFor();
  assert.equal(await page.evaluate(() => globalThis.__devDocumentSentinel), 'same document');
  const first = await page.evaluate(async () => (await fetch('/api/data')).json());
  assert.match(first.build, /^react-dev-/); assert.equal(first.frontend, 'react');
  await page.evaluate(() => {
    globalThis.__devRevisions = [];
    globalThis.__devOpenCount = 0;
    globalThis.__devStream = new globalThis.EventSource('/api/stream');
    globalThis.__devStream.addEventListener('open', () => { globalThis.__devOpenCount++; });
    globalThis.__devStream.addEventListener('revision', event => globalThis.__devRevisions.push(event.data));
  });
  await page.waitForFunction(() => globalThis.__devRevisions.length > 0);
  const before = await page.evaluate(() => globalThis.__devRevisions.at(-1));
  const sessions = join(dev.scratch, 'codex/sessions/2026/10/07');
  await mkdir(sessions, { recursive: true });
  const sid = '11111111-1111-4111-8111-111111111111';
  const records = [{ type: 'session_meta', payload: { id: sid, cwd: copy } },
    { timestamp: new Date().toISOString(), type: 'response_item', payload: { type: 'message', role: 'user',
      content: [{ type: 'input_text', text: 'Synthetic isolated developer fixture.' }] } }];
  await writeFile(join(sessions, 'rollout-fixture.jsonl'), records.map(row => JSON.stringify(row)).join('\n') + '\n');
  await page.waitForFunction(async target => {
    const data = await (await fetch('/api/data')).json();
    return data.sessions.some(row => row.sid === target);
  }, sid);
  await page.waitForFunction(previous => globalThis.__devRevisions.at(-1) !== previous, before);
  const oldGeneration = dev.ready.generation;
  const oldOpenCount = await page.evaluate(() => globalThis.__devOpenCount);
  await dev.restart();
  assert.notEqual(dev.ready.generation, oldGeneration);
  await page.waitForFunction(async oldBuild => (await (await fetch('/api/data')).json()).build !== oldBuild, first.build);
  await page.waitForFunction(previous => globalThis.__devOpenCount > previous &&
    globalThis.__devStream.readyState === globalThis.EventSource.OPEN, oldOpenCount);
  assert.equal((await context.request.get(dev.origin + '/api/data', { headers: { Origin: dev.viteOrigin } })).status(), 403);
  assert.equal((await context.request.get(dev.origin + '/@vite/client')).status(), 404);
  assert.equal((await context.request.post(dev.origin + '/api/focus', { headers: { Origin: dev.viteOrigin }, data: {} })).status(), 403);
  await page.evaluate(() => globalThis.__devStream.close());
  assert.deepEqual(external, []); assert.deepEqual(errors, []);
  await context.close(); context = null;
  await dev.close(); dev = null;

  // Separate fixture uses the real application's capability, HTTP guard and
  // lifecycle. Only its native raise callback is inert; normal pnpm dev keeps
  // focus/events disabled and has no injected focus capability.
  dev = await startDevelopment({ root: copy, port: 4587, vitePort: 4588,
    backendHelper: join(copy, 'frontend/test/dev_capability_backend.py') });
  context = await browser.newContext();
  await context.route('**/*', route => {
    const url = route.request().url();
    if ([dev.origin, dev.viteOrigin].some(origin => url.startsWith(origin + '/')) || url.startsWith('data:')) return route.continue();
    external.push(url); return route.abort();
  });
  await context.routeWebSocket('**/*', socket => {
    if (socket.url().startsWith(dev.viteOrigin.replace('http:', 'ws:') + '/__cargento_hmr')) socket.connectToServer();
    else { external.push(socket.url()); socket.close({ code: 1008 }); }
  });
  const capPage = await context.newPage();
  capPage.on('pageerror', error => errors.push(error.message));
  await capPage.goto(dev.origin);
  await capPage.getByRole('heading', { name: 'Hot refresh verified' }).waitFor();
  const token = await capPage.locator('head meta[name="cargento-focus"]').getAttribute('content');
  assert.match(token, /^[0-9a-f]{64}$/);
  const focus = async capability => capPage.evaluate(async value => {
    const response = await fetch('/api/focus', { method: 'POST', headers: {
      'Content-Type': 'application/json', ...(value ? { 'X-Cargento-Capability': value } : {}) },
    body: JSON.stringify({ harness: 'codex', sid: 'synthetic-missing-session' }) });
    return { status: response.status, body: response.status === 200 ? await response.json() : null };
  }, capability);
  assert.equal((await focus(null)).status, 403);
  assert.equal((await focus('00'.repeat(32))).status, 403);
  assert.deepEqual(await focus(token), { status: 200, body: { focused: false } });
  assert.equal((await context.request.post(dev.origin + '/api/focus', { headers: {
    Origin: dev.viteOrigin, 'X-Cargento-Capability': token }, data: { harness: 'codex', sid: 'synthetic-missing-session' } })).status(), 403);
  await dev.restart();
  await capPage.reload();
  await capPage.getByRole('heading', { name: 'Hot refresh verified' }).waitFor();
  const renewedToken = await capPage.locator('head meta[name="cargento-focus"]').getAttribute('content');
  assert.notEqual(renewedToken, token);
  assert.equal((await focus(token)).status, 403);
  assert.deepEqual(await focus(renewedToken), { status: 200, body: { focused: false } });
  assert.deepEqual(external, []); assert.deepEqual(errors, []);
  console.log(JSON.stringify({ development: { realPython: true, hotRefreshPreservedState: true, fonts: 15,
    collectorFixtureObserved: true, realSseRevision: true, backendRestart: true, sseReconnected: true,
    externalRequests: 0, modelsAndUsageDisabled: true, nativeActionsDisabled: true },
  inertCapabilityFixture: { actualInjection: true, missingAndWrongRefused: true, crossOriginRefused: true,
    renewedAfterRestart: true, staleRefused: true, authorizedResponseFocused: false, nativeRaiseInert: true } }, null, 2));
} catch (error) {
  console.error(JSON.stringify({ errors, failures, external }));
  throw error;
} finally {
  if (context) await context.close();
  if (browser) await browser.close();
  if (dev) await dev.close();
  await rm(copy, { recursive: true, force: true });
}
