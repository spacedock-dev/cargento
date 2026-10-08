import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { test } from 'node:test';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { startDevelopment } from './supervisor.mjs';

test('missing Python fails before owned children start', async () => {
  await assert.rejects(startDevelopment({ python: '/missing/cargento-python', port: 4585, vitePort: 4586 }), /Python/);
});

test('missing frozen frontend dependencies gives an actionable error before any bind', async () => {
  const root = await mkdtemp(join(tmpdir(), 'cargento-missing-dependencies-'));
  try { await assert.rejects(startDevelopment({ root, port: 4585, vitePort: 4586 }), /dependencies.*pnpm install/); }
  finally { await rm(root, { recursive: true, force: true }); }
});

test('Vite port collision leaves unrelated listener alive', { timeout: 15000 }, async () => {
  const server = createServer((_, res) => res.end('foreign owner'));
  await new Promise(resolve => server.listen(4586, '127.0.0.1', resolve));
  try {
    await assert.rejects(startDevelopment({ port: 4585, vitePort: 4586 }), /already in use|EADDRINUSE/);
    assert.equal(await (await fetch('http://127.0.0.1:4586')).text(), 'foreign owner');
  } finally { await new Promise(resolve => server.close(resolve)); }
});

test('Python port collision never adopts the foreign server and closes owned Vite', { timeout: 20000 }, async () => {
  const server = createServer((_, res) => res.end('foreign Python owner'));
  await new Promise(resolve => server.listen(4585, '127.0.0.1', resolve));
  try {
    await assert.rejects(startDevelopment({ port: 4585, vitePort: 4586 }), /Python|readiness/);
    assert.equal(await (await fetch('http://127.0.0.1:4585')).text(), 'foreign Python owner');
    await assert.rejects(fetch('http://127.0.0.1:4586'));
  } finally { await new Promise(resolve => server.close(resolve)); }
});

test('real backend restarts serialize fresh identities and close only owned children', { timeout: 30000 }, async () => {
  const dev = await startDevelopment({ port: 4585, vitePort: 4586 });
  try {
    const first = dev.ready;
    const data = await (await fetch(first.origin + '/api/data')).json();
    assert.equal(data.frontend, 'react'); assert.match(data.build, /^react-dev-/);
    await Promise.all([dev.restart(), dev.restart()]);
    assert.notEqual(dev.ready.pid, first.pid);
    assert.notEqual(dev.ready.generation, first.generation);
    assert.notEqual((await (await fetch(first.origin + '/api/data')).json()).build, data.build);
  } finally { await dev.close(); }
  await assert.rejects(fetch('http://127.0.0.1:4585'));
  await assert.rejects(fetch('http://127.0.0.1:4586'));
});

test('interruption during startup and Vite child death clean both owned processes', { timeout: 20000 }, async () => {
  const abort = new AbortController();
  const starting = startDevelopment({ port: 4585, vitePort: 4586, signal: abort.signal });
  abort.abort();
  await assert.rejects(starting, /interrupted/);
  const dev = await startDevelopment({ port: 4585, vitePort: 4586 });
  dev.worker.kill('SIGTERM');
  await dev.closed;
  await assert.rejects(fetch('http://127.0.0.1:4585'));
  await assert.rejects(fetch('http://127.0.0.1:4586'));
});

test('documented contributor executable exits cleanly on stdin EOF after readiness', { timeout: 20000 }, async () => {
  const child = spawn(process.execPath, [fileURLToPath(new URL('./supervisor.mjs', import.meta.url)),
    '--port', '4585', '--vite-port', '4586'], { stdio: ['pipe', 'pipe', 'pipe'] });
  let output = '', diagnostic = '';
  child.stderr.on('data', chunk => diagnostic += chunk);
  const stopped = new Promise(resolve => child.once('close', code => resolve(code)));
  try {
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(Error('Contributor readiness timeout: ' + diagnostic)), 12000);
      child.stdout.on('data', chunk => {
        output += chunk;
        if (output.includes('Cargento development: http://127.0.0.1:4585')) { clearTimeout(timer); resolve(); }
      });
      child.once('close', () => { clearTimeout(timer); reject(Error('Contributor stopped before readiness: ' + diagnostic)); });
    });
    child.stdin.end();
    assert.equal(await stopped, 0);
    await assert.rejects(fetch('http://127.0.0.1:4585'));
    await assert.rejects(fetch('http://127.0.0.1:4586'));
  } finally {
    if (child.exitCode === null) { child.stdin.end(); child.kill('SIGTERM'); await stopped; }
  }
});
