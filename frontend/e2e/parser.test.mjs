import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { chromium } from '@playwright/test';
import { createDocument } from '../build/package.mjs';

test('served embedded modules preserve hostile literals without changing the HTML parse', { timeout: 20000 }, async () => {
  const values = ['</script><img id="injected">', '<!--', '<script>', '</style>', '</head>', 'Ω & < " \''];
  const javascript = `const values=${JSON.stringify(values)};
    const raw=String.raw\`</ScRiPt><!--<script>\`;
    const pattern=/<\\/script>/i;
    globalThis.parserResult={values,raw,comparison:1<2,pattern:pattern.source};
    document.getElementById('root').textContent='Parser result ready';`;
  const document = createDocument(javascript, ':root{--hostile:"</style>"}');
  const server = createServer((_request, response) => {
    response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Content-Security-Policy': "frame-ancestors 'none'" });
    response.end(document);
  });
  let browser;
  try {
    server.listen(4586, '127.0.0.1');
    await once(server, 'listening');
    browser = await chromium.launch();
    const context = await browser.newContext();
    const external = [], errors = [];
    await context.route('**/*', route => {
      const url = route.request().url();
      if (url.startsWith('http://127.0.0.1:4586/') || url.startsWith('data:')) return route.continue();
      external.push(url);
      return route.abort();
    });
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('http://127.0.0.1:4586/');
    await page.getByText('Parser result ready').waitFor();
    const actual = await page.evaluate(() => ({ ...globalThis.parserResult,
      scripts: document.scripts.length, roots: document.querySelectorAll('#root').length,
      injected: !!document.querySelector('#injected'),
      css: globalThis.getComputedStyle(document.documentElement).getPropertyValue('--hostile').trim(),
    }));
    assert.deepEqual(actual.values, values);
    assert.equal(actual.raw, '</ScRiPt><!--<script>');
    assert.equal(actual.comparison, true);
    assert.equal(actual.pattern, '<\\/script>');
    assert.equal(actual.scripts, 1);
    assert.equal(actual.roots, 1);
    assert.equal(actual.injected, false);
    assert.equal(actual.css, '"</style>"');
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
  } finally {
    if (browser) await browser.close();
    server.closeAllConnections();
    if (server.listening) await new Promise(resolve => server.close(resolve));
  }
});
