import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { test } from 'node:test';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { readinessRequest, startDevelopment } from './supervisor.mjs';

async function withDrip(kind, duration, use) {
  const timers = new Set();
  const server = createServer((req, res) => {
    if (req.url === '/ping') {
      res.end('foreign owner remains');
      return;
    }
    const socket = res.socket;
    if (kind === 'headers') socket.write('HTTP/1.1 200 OK\r\n');
    else {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.flushHeaders();
    }
    let index = 0;
    const interval = setInterval(() => {
      if (kind === 'headers') socket.write(`X-Drip-${index++}: ok\r\n`);
      else res.write(' ');
    }, 100);
    const end = setTimeout(() => {
      clearInterval(interval);
      if (kind === 'headers') socket.end('Content-Length: 2\r\n\r\n{}');
      else res.end('{}');
    }, duration);
    timers.add(interval);
    timers.add(end);
    socket.once('close', () => {
      clearInterval(interval);
      clearTimeout(end);
    });
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  try {
    await use(origin, server.address().port);
    assert.equal(server.listening, true);
    assert.equal(await (await fetch(origin + '/ping')).text(), 'foreign owner remains');
  } finally {
    for (const timer of timers) clearTimeout(timer);
    server.closeAllConnections();
    await new Promise((resolve) => server.close(resolve));
  }
}

for (const phase of ['headers', 'body'])
  test(`absolute readiness deadline interrupts active ${phase} drip`, {
    timeout: 8000,
  }, async () => {
    await withDrip(phase, 3000, async (origin) => {
      const started = Date.now();
      await assert.rejects(
        readinessRequest(origin, '/api/health', 2048, { deadline: Date.now() + 350 }),
        /deadline/,
      );
      assert.ok(
        Date.now() - started < 2200,
        'active transport must not outlive the absolute budget with broad scheduler headroom',
      );
    });
  });

test('abort cancels an active readiness body and settles its promise', {
  timeout: 8000,
}, async () => {
  await withDrip('body', 3000, async (origin) => {
    const controller = new AbortController();
    const started = Date.now();
    const request = readinessRequest(origin, '/api/health', 2048, {
      deadline: Date.now() + 5000,
      signal: controller.signal,
    });
    const timer = setTimeout(() => controller.abort(Error('fixture interrupted')), 100);
    try {
      await assert.rejects(request, /interrupted/);
    } finally {
      clearTimeout(timer);
    }
    assert.ok(Date.now() - started < 2200, 'aborted transport must settle promptly');
  });
});

test('owned Python bind failure cancels foreign readiness drip and closes owned Vite', {
  timeout: 15000,
}, async () => {
  await withDrip('body', 8000, async (_origin, port) => {
    const started = Date.now();
    await assert.rejects(startDevelopment({ port, vitePort: 4596 }), /Python|readiness/);
    assert.ok(Date.now() - started < 6000, 'dead owned child must cancel the foreign response');
    await assert.rejects(fetch('http://127.0.0.1:4596'));
  });
});

test('interrupted startup cancels foreign HTTP while its inert owned child is still alive', {
  timeout: 15000,
}, async () => {
  const root = await mkdtemp(join(tmpdir(), 'cargento-startup-interrupt-'));
  const helper = join(root, 'owned-sleeping-process.py');
  await writeFile(helper, 'import time\ntime.sleep(60)\n');
  try {
    await withDrip('body', 8000, async (_origin, port) => {
      const controller = new AbortController();
      const started = Date.now();
      const starting = startDevelopment({
        port,
        vitePort: 4596,
        backendHelper: helper,
        signal: controller.signal,
      });
      const timer = setTimeout(() => controller.abort(), 1100);
      try {
        await assert.rejects(starting, /interrupted/);
      } finally {
        clearTimeout(timer);
      }
      assert.ok(
        Date.now() - started < 6000,
        'startup interruption must cancel owned request/children',
      );
      await assert.rejects(fetch('http://127.0.0.1:4596'));
    });
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
