import assert from 'node:assert/strict';
import { ASSESSMENT, fact, installScript, RECORD, SAVED, POLICY, ROUTE } from '../drift-board.mjs';
import { openPage } from './browser.mjs';

const action = (name) => `[data-next-cockpit-action="${name}"]`;
const GOAL = '[data-next-cockpit-held-kind="goal"]';
const RESULT = '[data-next-result]';
const ACTIVITY = '[data-next-session-activity]';

async function inside(page, selector, name) {
  const bounds = await page.locator(selector).evaluate((node) => {
    const box = node.getBoundingClientRect();
    return { top: box.top, bottom: box.bottom, height: innerHeight, width: innerWidth };
  });
  assert.ok(
    bounds.top >= 0 && bounds.bottom <= bounds.height,
    `${name} outside viewport ${JSON.stringify(bounds)}`,
  );
}

async function resultFirst(page) {
  const bounds = await page.evaluate(
    ({ RESULT, ACTIVITY }) => {
      const result = document.querySelector(RESULT);
      const activity = document.querySelector(ACTIVITY);
      const heading = result.querySelector(
        '.next-cockpit-result-headline,.next-cockpit-result-line',
      );
      return {
        beforeActivity: Boolean(
          result.compareDocumentPosition(activity) & Node.DOCUMENT_POSITION_FOLLOWING,
        ),
        top: result.getBoundingClientRect().top,
        answerTop: heading.getBoundingClientRect().top,
        answerBottom: heading.getBoundingClientRect().bottom,
        activityTop: activity.getBoundingClientRect().top,
        height: innerHeight,
        width: innerWidth,
      };
    },
    { RESULT, ACTIVITY },
  );
  // In one column the result comes before the activity. Beside it (wider than 1100px) it reads first in the
  // markup and sits level with the activity's top, in the right-hand column.
  assert.ok(
    bounds.beforeActivity && (bounds.width > 1100 ? true : bounds.top < bounds.activityTop),
    `result must precede Session activity ${JSON.stringify(bounds)}`,
  );
  assert.ok(
    bounds.top >= 0 && bounds.answerTop < bounds.height,
    `result area outside first view ${JSON.stringify(bounds)}`,
  );
}

async function rejectedMutation(page, name, selector, mutate, check) {
  const handle = await page.locator(selector).elementHandle();
  await handle.evaluate((node) => {
    const marker = document.createComment('first-view mutation position');
    node.before(marker);
    globalThis.__firstViewMutation = { node, marker, style: node.getAttribute('style') };
  });
  try {
    await handle.evaluate(mutate);
    await assert.rejects(check, assert.AssertionError, `${name} escaped its measurement`);
    console.log(`First-view mutation rejected: ${name}`);
  } finally {
    await page.evaluate(() => {
      const { node, marker, style } = globalThis.__firstViewMutation;
      marker.replaceWith(node);
      if (style === null) node.removeAttribute('style');
      else node.setAttribute('style', style);
      delete globalThis.__firstViewMutation;
    });
    await check();
  }
}

const belowFold = (node) => {
  node.style.marginTop = '100vh';
};

export async function proveFirstViewStates({ page, browser, board, script }) {
  // A synthetic capability draws Raise; the refusal keeps a misplaced press from reaching native focus.
  await page.addInitScript(() => {
    const observer = new MutationObserver(() => {
      if (!document.head) return;
      const meta = document.createElement('meta');
      meta.name = 'compass-focus';
      meta.content = 'first-view-proof-only';
      document.head.prepend(meta);
      observer.disconnect();
    });
    observer.observe(document, { childList: true, subtree: true });
  });
  await page.route('**/api/focus', (route) => route.fulfill({ status: 403, body: '{}' }));
  const generated = (await (await fetch(`${board.react.origin}/api/data`)).json()).generated;
  script.payload = {
    reading: POLICY,
    reading_routes: { claude: ROUTE },
    reading_check: 'accepted',
    reading_jobs: {},
  };
  const base = { ...SAVED(generated), state: 'working', reading_eligibility: undefined };
  const load = async (session, facts = []) => {
    script.session = { ...base, ...session };
    script.facts = facts;
    await page.reload();
    await page.locator(GOAL).waitFor();
    await page.evaluate(() => scrollTo(0, 0));
  };
  const viewports = [
    { width: 1280, height: 800 },
    { width: 375, height: 667 },
  ];
  for (const viewport of viewports) {
    await page.setViewportSize(viewport);
    await load(
      { annotation_assessment: ASSESSMENT(generated), annotation_reading_count: 1 },
      RECORD(generated),
    );
    await page.locator(RESULT).waitFor();
    await resultFirst(page);
    await rejectedMutation(
      page,
      'result below activity',
      RESULT,
      (node) => document.querySelector('[data-next-session-activity]').append(node),
      () => resultFirst(page),
    );
    await inside(page, action('steer-back'), 'Steer back');
    await rejectedMutation(page, 'Steer back below fold', action('steer-back'), belowFold, () =>
      inside(page, action('steer-back'), 'Steer back'),
    );
    for (const count of [1, 4]) {
      await load(
        {},
        Array.from({ length: count }, (_, index) =>
          fact(`later-${index}`, generated - 100 + index),
        ),
      );
      await page.locator(action('direction-keep')).waitFor();
      await inside(page, action('direction-keep'), `Keep with ${count} directions`);
      await rejectedMutation(
        page,
        `Keep with ${count} directions below fold`,
        action('direction-keep'),
        belowFold,
        () => inside(page, action('direction-keep'), 'Keep'),
      );
    }
    for (const title of [
      'Blocked work',
      'Blocked work waiting for your decision about the next step before it can continue',
    ]) {
      await load({ state: 'needs_input', title, focusable: true });
      await page.locator('.next-session-detail--blocked').waitFor();
      const raise = '.next-session-detail-header [data-control="raise"]';
      await inside(page, GOAL, 'blocked goal');
      await inside(page, raise, 'blocked raise');
      if (viewport.width === 375 && title !== 'Blocked work') {
        const lines = await page.locator('.next-session-detail-header h1').evaluate((node) => {
          const range = document.createRange();
          range.selectNodeContents(node);
          const bottom = node.getBoundingClientRect().bottom;
          return new Set(
            [...range.getClientRects()].filter((rect) => rect.top < bottom).map((rect) => rect.top),
          ).size;
        });
        assert.ok(lines > 1, 'the blocked header fixture must wrap');
      }
      await rejectedMutation(page, 'blocked goal below fold', GOAL, belowFold, () =>
        inside(page, GOAL, 'blocked goal'),
      );
      await rejectedMutation(page, 'blocked raise below fold', raise, belowFold, () =>
        inside(page, raise, 'blocked raise'),
      );
    }
  }
  const touch = await openPage(browser, [board.react.origin, board.react.viteOrigin], {
    viewport: { width: 375, height: 667 },
    hasTouch: true,
  });
  try {
    script.session = base;
    script.facts = [fact('touch-direction', generated - 100)];
    await installScript(touch.context, script);
    await touch.page.emulateMedia({ reducedMotion: 'reduce' });
    await touch.page.goto(page.url());
    const add = `${ACTIVITY} ${action('direction-add')}`;
    await touch.page.locator(add).waitFor();
    const media = await touch.page.evaluate(() => ({
      noHover: matchMedia('(hover: none)').matches,
      coarse: matchMedia('(pointer: coarse)').matches,
    }));
    assert.deepEqual(media, { noHover: true, coarse: true });
    const visible = async () => {
      const opacity = await touch.page
        .locator(add)
        .evaluate((node) => getComputedStyle(node).opacity);
      assert.equal(opacity, '1', 'Add to my intent must be visible without hover');
    };
    await visible();
    const classes = await touch.page.locator(add).getAttribute('class');
    try {
      await touch.page.locator(add).evaluate((node) => {
        for (const name of [...node.classList])
          if (name.includes('hover:none') || name.includes('pointer:coarse'))
            node.classList.remove(name);
      });
      await assert.rejects(
        visible,
        assert.AssertionError,
        'missing touch fallback escaped the proof',
      );
      console.log('First-view mutation rejected: missing touch fallback');
    } finally {
      await touch.page
        .locator(add)
        .evaluate((node, classes) => node.setAttribute('class', classes), classes);
    }
    await visible();
    await touch.page.locator(add).focus();
    assert.equal(
      await touch.page.locator(add).evaluate((node) => document.activeElement === node),
      true,
    );
    assert.equal(touch.log.nonGet.length, 0);
    assert.deepEqual(touch.log.externalRequests, []);
  } finally {
    await touch.close();
  }
}
