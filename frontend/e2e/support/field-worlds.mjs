import assert from 'node:assert/strict';
import { join } from 'node:path';
import { call, startIntentBoard } from '../intent-board.mjs';
import { freePorts, openPage } from './browser.mjs';
import { startReactWorld } from './world.mjs';
import { awaitRecordRead } from './record.mjs';
import {
  ASSESSMENT,
  SAVED,
  RECORD,
  POLICY,
  ROUTE,
  freshScript,
  installScript,
} from '../drift-board.mjs';

const patience = (ms) => (process.env.CI ? ms * 3 : ms);
let polls = 0;

export async function forcePoll(page) {
  const sequence = ++polls;
  const marker = `[poll:${sequence}]`;
  // A completed GET can be discarded, and store acceptance can precede display. Stamp after the
  // scripted backend so correction fixtures keep their overlays.
  await page.evaluate(
    ({ marker }) => {
      const original = globalThis.fetch;
      globalThis.__fieldPollFetch = original;
      globalThis.fetch = async (input, init) => {
        const response = await original(input, init);
        const url = input instanceof Request ? input.url : String(input);
        if (new URL(url, globalThis.location.href).pathname !== '/api/data' || !response.ok)
          return response;
        const body = await response.json();
        body.sessions = (body.sessions || []).map((row) => ({
          ...row,
          title: `${row.title || 'Session'} ${marker}`,
        }));
        return new Response(JSON.stringify(body), {
          status: response.status,
          statusText: response.statusText,
          headers: response.headers,
        });
      };
      globalThis.__fieldPollWake = (globalThis.__fieldPollWake || 0) + 1;
      globalThis.dispatchEvent(
        new StorageEvent('storage', {
          key: 'compass.next.revision',
          newValue: `${Date.now()}.${globalThis.__fieldPollWake}`,
        }),
      );
    },
    { marker, sequence },
  );
  try {
    await page
      .waitForFunction(
        (marker) =>
          [
            ...globalThis.document.querySelectorAll(
              '.next-cockpit-scope-title, nav[aria-label=Breadcrumb] [aria-current=page]',
            ),
          ].some((node) => node.textContent.includes(marker)),
        marker,
        { timeout: patience(6000) },
      )
      .catch((cause) => {
        throw new Error(`forcePoll: no rendered revision ${marker} within ${patience(6000)} ms`, {
          cause,
        });
      });
    await page.evaluate(
      () => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done))),
    );
  } finally {
    await page.evaluate(() => {
      globalThis.fetch = globalThis.__fieldPollFetch;
      delete globalThis.__fieldPollFetch;
    });
  }
}

/* States the route census does not reach: editable memos, an added tripwire and later directions. */
export async function visitFieldStates(browser, root, record) {
  const [port, vitePort] = await freePorts(2);
  const consoleWorld = await startReactWorld({
    root,
    port,
    vitePort,
    backendHelper: join(root, 'frontend/test/console_backend.py'),
  });
  let opened;
  try {
    opened = await openPage(browser, [consoleWorld.origin, consoleWorld.viteOrigin]);
    const page = opened.page;
    const recordField = (page, view) => record(page, view, opened.context, () => forcePoll(page));
    for (const tab of ['course', 'now', 'console']) {
      await page.goto(
        `${consoleWorld.origin}/#n=project:alpha%2Fapp${tab === 'now' ? '' : ':claude%3Alive-work'}:${tab}`,
      );
      await page.locator('nav[aria-label=Primary]').waitFor();
      if (tab === 'course') await page.locator('[data-stage-choice]').waitFor();
      if (tab === 'now') {
        await page.locator('.next-cockpit-recovery').waitFor();
        const add = page.getByRole('button', { name: /^\+ Add human context/ });
        if (await add.count()) await add.click();
        else {
          await page.locator('.ctl-menu > summary[aria-label=More]').click();
          await page.getByRole('button', { name: 'Add human context', exact: true }).click();
        }
        await page.getByRole('textbox', { name: 'OUTCOME', exact: true }).waitFor();
        await recordField(page, 'field states: memo OUTCOME');
        await page.getByRole('textbox', { name: 'OUTCOME', exact: true }).fill('Reader note');
        await page.getByRole('button', { name: 'Done', exact: true }).click();
        for (const label of ['FOCUS']) {
          const edit = page.getByRole('button', { name: `Edit ${label}`, exact: true });
          assert.equal(await edit.count(), 1);
          await edit.click();
          await page.getByRole('textbox', { name: label, exact: true }).waitFor();
          await recordField(page, `field states: memo ${label}`);
          await page.getByRole('button', { name: 'Done', exact: true }).click();
        }
      }
      if (tab === 'console') {
        await page.getByRole('button', { name: '+ set a tripwire', exact: true }).click();
        await page.locator('[data-next-guardrail-input]').waitFor();
      }
      await recordField(page, `field states: ${tab}`);
    }
  } finally {
    await opened?.close();
    await consoleWorld.close();
  }
  const board = await startIntentBoard({ root });
  try {
    const data = (await call(board.react.origin, 'GET', '/api/data')).body;
    const row = data.sessions.find((s) => s.sid === 'intent-4');
    const saved = await call(board.react.origin, 'POST', '/api/annotate', {
      harness: 'claude',
      sid: row.sid,
      adopt: 'first-prompt',
      expected_prompt: row.first_prompt,
      expected_prompt_at: row.first_prompt_at,
      expected_revision: row.annotation_revision || 0,
    });
    assert.equal(saved.body.ok, true);
    opened = await openPage(browser, [board.react.origin, board.react.viteOrigin]);
    const page = opened.page;
    const recordField = (page, view) => record(page, view, opened.context, () => forcePoll(page));
    await page.goto(`${board.react.origin}/#n=session:w%2Falpha:claude:intent-4`);
    await awaitRecordRead(page);
    await page.locator('[data-next-direction-select]').waitFor();
    await recordField(page, 'field states: direction choice');
    await page
      .locator('[data-next-cockpit-direction-question] [data-next-cockpit-action=direction-add]')
      .click();
    await page.locator('[data-next-cockpit-direction-key]').waitFor();
    await recordField(page, 'field states: direction draft');
    const generated = (await call(board.react.origin, 'GET', '/api/data')).body.generated;
    const script = {
      ...freshScript(),
      session: {
        ...SAVED(generated),
        annotation_assessment: ASSESSMENT(generated),
        annotation_reading_count: 1,
        state: 'idle',
        turn_end_at: generated - 200,
      },
      payload: {
        reading: POLICY,
        reading_routes: { claude: ROUTE },
        reading_check: 'accepted',
        reading_jobs: {},
      },
      facts: RECORD(generated),
      routes: {
        '/api/correction': () => ({
          body: { ok: true, parts: ['Your check failed ', { entry: 'c1' }, '. Fix it.'] },
        }),
      },
    };
    await installScript(opened.context, script);
    await page.goto(`${board.react.origin}/#n=session:w%2Falpha:claude:intent-2`);
    await awaitRecordRead(page);
    await page.locator('[data-next-cockpit-action=steer-back]').click();
    await page.locator('[data-next-cockpit-correction-key]').waitFor();
    await recordField(page, 'field states: correction');
  } finally {
    await opened?.close();
    await board.close();
  }
}
