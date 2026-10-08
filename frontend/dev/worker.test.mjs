import assert from 'node:assert/strict';
import { fork } from 'node:child_process';
import { request } from 'node:http';
import { randomBytes } from 'node:crypto';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { mkdtemp, rm, mkdir, writeFile, symlink, cp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, relative } from 'node:path';

const root = fileURLToPath(new URL('../../', import.meta.url));
function exchange(port, path, headers = {}, upgrade = false) {
  return new Promise((resolve, reject) => {
    const req = request({ hostname: '127.0.0.1', port, path, headers, timeout: 3000 }, (res) => {
      let body = '';
      res.setEncoding('utf8');
      res.on('data', (chunk) => (body += chunk));
      res.on('end', () => resolve({ status: res.statusCode, body }));
    });
    req.on('upgrade', (res, socket) => {
      socket.destroy();
      resolve({ status: res.statusCode, body: '' });
    });
    req.on('error', reject);
    req.on('timeout', () => req.destroy(Error('HTTP timeout')));
    if (upgrade) req.setHeader('Connection', 'Upgrade');
    req.end();
  });
}

test('real Vite admits only owned handshake and exact Python-origin modules/HMR', {
  timeout: 20000,
}, async () => {
  const scratch = await mkdtemp(join(tmpdir(), 'cargento-vite-guard-'));
  const privateRoot = join(scratch, 'outside-source');
  const link = join(root, 'frontend/dev', `guard-link-${process.pid}`);
  await mkdir(privateRoot);
  await writeFile(join(privateRoot, 'private.js'), 'export const privateValue="synthetic secret";');
  await symlink(privateRoot, link, process.platform === 'win32' ? 'junction' : 'dir');
  const child = fork(fileURLToPath(new URL('./vite-worker.mjs', import.meta.url)), [], {
    stdio: ['ignore', 'pipe', 'pipe', 'ipc'],
  });
  let error = '';
  child.stderr.on('data', (chunk) => (error += chunk));
  const exited = new Promise((resolve) => child.once('exit', resolve));
  try {
    const ready = new Promise((resolve, reject) => {
      child.once('message', (value) =>
        value.type === 'ready' ? resolve(value) : reject(Error(JSON.stringify(value))),
      );
      child.once('exit', () => reject(Error('Worker exited: ' + error)));
    });
    child.send({
      type: 'start',
      root,
      scratch,
      port: 4590,
      pythonPort: 4591,
      nonce: '00'.repeat(32),
      viteGeneration: '22'.repeat(16),
      backendGeneration: '33'.repeat(16),
    });
    assert.equal((await ready).pid, child.pid);
    const headers = { Origin: 'http://127.0.0.1:4591' };
    assert.equal((await exchange(4590, '/src/main.tsx', headers)).status, 200);
    for (const bad of [
      {},
      { Origin: 'http://127.0.0.1:4592' },
      { ...headers, Host: 'localhost:4590' },
      { ...headers, Host: '127.0.0.2:4590' },
      { ...headers, Host: 'evil.example:4590' },
    ]) {
      assert.equal((await exchange(4590, '/src/main.tsx', bad)).status, 403);
    }
    assert.equal(
      (
        await exchange(4590, '/src/main.tsx', [
          'Host',
          '127.0.0.1:4590',
          'Host',
          'evil.example:4590',
          'Origin',
          headers.Origin,
        ])
      ).status,
      403,
    );
    assert.equal((await exchange(4590, '/', headers)).status, 403);
    assert.equal((await exchange(4590, '/index.html', headers)).status, 403);
    assert.equal((await exchange(4590, '/@fs/' + root + 'tests/README.md', headers)).status, 403);
    assert.equal(
      (await exchange(4590, `/dev/guard-link-${process.pid}/private.js`, headers)).status,
      403,
    );
    const proof = await exchange(4590, '/__cargento_dev_handshake', {
      'x-cargento-dev-challenge': '11'.repeat(32),
      'x-cargento-dev-generation': '33'.repeat(16),
    });
    assert.equal(proof.status, 200);
    assert.equal(JSON.parse(proof.body).vite_pid, child.pid);
    assert.ok(!proof.body.includes('00'.repeat(32)), 'handshake must not publish its secret');
    assert.equal(
      (
        await exchange(4590, '/__cargento_dev_handshake', {
          'x-cargento-dev-challenge': '11'.repeat(32),
          'x-cargento-dev-generation': '44'.repeat(16),
        })
      ).status,
      403,
    );
    assert.equal(
      (
        await exchange(4590, '/__cargento_dev_handshake', {
          ...headers,
          'x-cargento-dev-challenge': '11'.repeat(32),
          'x-cargento-dev-generation': '33'.repeat(16),
        })
      ).status,
      403,
    );
    const client = (await exchange(4590, '/@vite/client', headers)).body;
    const token = client.match(/const wsToken = "([^"]+)"/)[1];
    const socketHeaders = {
      ...headers,
      Upgrade: 'websocket',
      'Sec-WebSocket-Version': '13',
      'Sec-WebSocket-Key': randomBytes(16).toString('base64'),
      'Sec-WebSocket-Protocol': 'vite-hmr',
    };
    assert.equal(
      (await exchange(4590, '/__cargento_hmr?token=' + token, socketHeaders, true)).status,
      101,
    );
    for (const bad of [
      { ...socketHeaders, Origin: 'http://127.0.0.1:4592' },
      { ...socketHeaders, Origin: '' },
      { ...socketHeaders, Host: 'localhost:4590' },
      { ...socketHeaders, Origin: 'http://evil.example', 'Sec-WebSocket-Protocol': 'vite-ping' },
    ]) {
      assert.equal((await exchange(4590, '/__cargento_hmr?token=' + token, bad, true)).status, 403);
    }
    assert.notEqual(
      (await exchange(4590, '/__cargento_hmr?token=wrong', socketHeaders, true)).status,
      101,
    );
  } finally {
    if (child.connected) child.send({ type: 'stop' });
    const timer = setTimeout(() => child.kill('SIGKILL'), 4000);
    await exited;
    clearTimeout(timer);
    await rm(link, { force: true, recursive: true });
    await rm(scratch, { recursive: true, force: true });
  }
});

// On a Windows runner os.tmpdir() is an 8.3 short path (C:\\Users\\RUNNER~1\\...). Vite refuses any file whose
// path keeps a short-name segment, so a copied tree under tmpdir must be served from its canonical spelling.
// This reproduces only on Windows (it fails there without the canonical root); on POSIX it passes either way.
test('real Vite serves a source tree whose root is spelled through the temporary directory', {
  timeout: 30000,
}, async () => {
  const copy = await mkdtemp(join(tmpdir(), 'cargento-vite-root-'));
  const child = fork(fileURLToPath(new URL('./vite-worker.mjs', import.meta.url)), [], {
    stdio: ['ignore', 'pipe', 'pipe', 'ipc'],
  });
  let error = '';
  child.stderr.on('data', (chunk) => (error += chunk));
  const exited = new Promise((resolve) => child.once('exit', resolve));
  try {
    await cp(join(root, 'frontend'), join(copy, 'frontend'), { recursive: true });
    await cp(join(root, 'cargento'), join(copy, 'cargento'), {
      recursive: true,
      filter: (path) =>
        !relative(join(root, 'cargento'), path)
          .split(/[\\/]/)
          .some((part) => part === 'tests' || part === '__pycache__'),
    });
    await symlink(
      join(root, 'node_modules'),
      join(copy, 'node_modules'),
      process.platform === 'win32' ? 'junction' : 'dir',
    );
    const ready = new Promise((resolve, reject) => {
      child.once('message', (value) =>
        value.type === 'ready' ? resolve(value) : reject(Error(JSON.stringify(value))),
      );
      child.once('exit', () => reject(Error('Worker exited: ' + error)));
    });
    child.send({
      type: 'start',
      root: copy,
      scratch: copy,
      port: 4592,
      pythonPort: 4593,
      nonce: '00'.repeat(32),
      viteGeneration: '22'.repeat(16),
      backendGeneration: '33'.repeat(16),
    });
    await ready;
    const headers = { Origin: 'http://127.0.0.1:4593' };
    const served = await exchange(4592, '/src/main.tsx', headers);
    assert.equal(served.status, 200, served.body.slice(0, 300));
    assert.equal(
      (
        await exchange(
          4592,
          '/@fs/' + join(copy, 'cargento/skills/cargento/server.py').replaceAll('\\', '/'),
          headers,
        )
      ).status,
      403,
    );
  } finally {
    if (child.connected) child.send({ type: 'stop' });
    const timer = setTimeout(() => child.kill('SIGKILL'), 4000);
    await exited;
    clearTimeout(timer);
    await rm(copy, { recursive: true, force: true });
  }
});
