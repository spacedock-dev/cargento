import assert from 'node:assert/strict';
import { cp, mkdir, mkdtemp, readFile, rm, symlink, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';
import { call, startIntentBoard } from './intent-board.mjs';
import { openPage, REPOSITORY } from './support/browser.mjs';
import { forcePoll } from './support/field-worlds.mjs';
import { nativeFieldContinuity } from './support/native-field.mjs';
import { copyProofPath } from './support/proof-copy.mjs';
import { awaitRecordRead } from './support/record.mjs';

const frames = (page) =>
  page.evaluate(
    () =>
      new Promise((done) =>
        globalThis.requestAnimationFrame(() => globalThis.requestAnimationFrame(done)),
      ),
  );

const announce = (page) =>
  page.evaluate(() => {
    globalThis.__fieldPollWake = (globalThis.__fieldPollWake || 0) + 1;
    globalThis.dispatchEvent(
      new globalThis.StorageEvent('storage', {
        key: 'compass.next.revision',
        newValue: `${Date.now()}.${globalThis.__fieldPollWake}`,
      }),
    );
  });

/* Kept as the negative control: a completed response and two frames need not paint anything. */
async function oldForcePoll(page) {
  const fetched = page.waitForResponse(
    (response) => new URL(response.url()).pathname === '/api/data',
  );
  await announce(page);
  await (await fetched).finished();
  await frames(page);
}

export async function proveFieldPoll() {
  await mkdir(join(REPOSITORY, 'docs/screenshots'), { recursive: true });
  const copy = await mkdtemp(join(REPOSITORY, 'docs/screenshots/field-poll-proof-'));
  let board;
  let browser;
  let opened;
  try {
    for (const folder of ['frontend', 'compass'])
      await cp(join(REPOSITORY, folder), join(copy, folder), {
        recursive: true,
        filter: copyProofPath,
      });
    await symlink(
      join(REPOSITORY, 'node_modules'),
      join(copy, 'node_modules'),
      process.platform === 'win32' ? 'junction' : 'dir',
    );
    const target = join(copy, 'frontend/src/intent/HeldTextarea.tsx');
    const source = await readFile(target, 'utf8');
    assert.ok(
      source.includes('defaultValue={initial}'),
      'controlled-field mutation needle is missing',
    );
    await writeFile(
      target,
      source.replace(
        'defaultValue={initial}',
        '{...((globalThis as unknown as { __controlOnPoll?: boolean }).__controlOnPoll ? { value: initial, onChange: () => undefined } : { defaultValue: initial })}',
      ),
    );
    board = await startIntentBoard({ root: copy });
    browser = await chromium.launch();
    opened = await openPage(browser, [board.react.origin, board.react.viteOrigin]);
    const { page, context } = opened;
    await page.route('**/api/stream', (route) => route.abort());
    await page.goto(`${board.react.origin}/#n=session:w%2Falpha:claude:intent-4`);
    await awaitRecordRead(page);
    const body = (await call(board.react.origin, 'GET', '/api/data')).body;
    const field = page.locator('[data-next-cockpit-held-kind=goal]');
    await field.fill('Words the reader has not saved');
    await field.evaluate((node) => node.setSelectionRange(3, 7));
    const capture = () =>
      field.evaluate((node) => [node.value, node.selectionStart, node.selectionEnd]);
    const held = await capture();
    const title = () =>
      page.locator('nav[aria-label=Breadcrumb] [aria-current=page]').textContent();

    async function superseded(poll, shouldWait) {
      const initial = await title();
      const routes = [];
      let next;
      const arrived = () =>
        new Promise((done, reject) => {
          const timer = setTimeout(
            () => reject(new Error('scripted data request did not arrive')),
            15000,
          );
          next = () => {
            clearTimeout(timer);
            done();
          };
        });
      let request = arrived();
      const handler = (route) => {
        routes.push(route);
        next();
      };
      await context.route('**/api/data*', handler);
      let completed = false;
      const pending = poll(page).then(() => {
        completed = true;
      });
      pending.catch(() => undefined);
      try {
        await request;
        request = arrived();
        await announce(page);
        await routes[0].fulfill({
          json: {
            ...body,
            sessions: body.sessions.map((row) => ({ ...row, title: 'Discarded answer' })),
          },
          headers: { 'X-Compass-Revision': '1.1' },
        });
        await request;
        if (!shouldWait) await pending;
        await frames(page);
        assert.equal(await title(), initial, 'the matched response was discarded without a render');
        assert.deepEqual(
          await capture(),
          held,
          'the untouched field passes preservation vacuously',
        );
        assert.equal(completed, !shouldWait, 'forcePoll returned before a successor rendered');
        await routes[1].fulfill({
          json: {
            ...body,
            sessions: body.sessions.map((row) => ({ ...row, title: 'Rendered successor' })),
          },
          headers: { 'X-Compass-Revision': '1.2' },
        });
        await pending;
        await page.waitForFunction(() =>
          globalThis.document
            .querySelector('nav[aria-label=Breadcrumb] [aria-current=page]')
            ?.textContent.includes('Rendered successor'),
        );
      } finally {
        await context.unroute('**/api/data*', handler);
        for (const route of routes) await route.abort().catch(() => undefined);
        await pending.catch(() => undefined);
      }
    }

    await superseded(oldForcePoll, false);
    await superseded(forcePoll, true);

    const delayed = [];
    const hold = (route) => {
      delayed.push(route);
    };
    await context.route('**/api/data*', hold);
    try {
      await assert.rejects(forcePoll(page), /forcePoll: no rendered revision .* within \d+ ms/);
      assert.equal(
        await page.evaluate(() => '__fieldPollFetch' in globalThis),
        false,
        'a timed-out poll restores fetch',
      );
    } finally {
      await context.unroute('**/api/data*', hold);
      for (const route of delayed) await route.abort().catch(() => undefined);
    }

    await page.reload();
    await awaitRecordRead(page);
    await page.setViewportSize({ width: 320, height: 900 });
    await nativeFieldContinuity(opened, field, () => forcePoll(page));
    let rendered = 0;
    await assert.rejects(
      nativeFieldContinuity(opened, field, async () => {
        await page.evaluate(() => {
          globalThis.__controlOnPoll = true;
        });
        await forcePoll(page);
        rendered += 1;
      }),
      /a redraw keeps native node identity and focus|a redraw keeps caret, selection, scroll and dragged size/,
    );
    assert.ok(rendered > 0, 'the controlled-field mutation must fail after an observed render');
    assert.deepEqual(opened.log.externalRequests, []);
    assert.deepEqual(opened.log.pageErrors, []);
    return {
      oldHelper: 'vacuous pass with zero renders',
      newHelper: 'waited for the successor',
      stalledHelper: 'threw when no revision rendered',
      controlledField: 'preservation failed after a rendered revision',
    };
  } finally {
    await opened?.close();
    await browser?.close();
    await board?.close();
    await rm(copy, { recursive: true, force: true });
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  console.log(JSON.stringify(await proveFieldPoll(), null, 2));
}
