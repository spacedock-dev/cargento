/*
 * The timeline's activity filter and its disclosures in a real browser, against the real backend (DRC-4824).
 *
 * The legacy page and the React page run in one Chromium over the same synthetic board; the project
 * context answers with one fixed semantic model (`frontend/test/terminal_backend.py`), so there are events
 * to filter and fold. A differential compares what a reader can observe: the heading, which filter button
 * is pressed, the events each choice shows (id, kind and lane, in order), and the one `cargento.next.graph.mode`
 * map each page writes, byte for byte. What a unit test cannot see is proved here: the choice surviving a
 * reload, project and session scopes staying independent, an old build's empty key being discarded, an open
 * disclosure keeping its state (and in the React page its node) across live updates and leaving the route,
 * keyboard focus staying on the button that was pressed, no duplicate reads under StrictMode, and the layout
 * at 320 and 375 CSS px.
 *
 * Run with `node frontend/e2e/timeline-filter.mjs` (it is the second half of `pnpm test:terminal:browser`);
 * `CARGENTO_E2E_STEPS=<regex>`, `CARGENTO_SCREENSHOTS=1` and `CARGENTO_MUTATION=<name>` behave as in
 * `terminal-parity.mjs`.
 */
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { chromium } from '@playwright/test';
import {
  FOCUS,
  fragmentFor,
  openTracked,
  REPOSITORY,
  startWorld,
  TERMINAL,
} from './terminal-support.mjs';

/* Every fixed wait here means "give the page time to react". A hosted runner has a few shared cores and delivers
   events and frames later than a desktop, so each wait is tripled there; only a pass gets slower. */
const patience = (ms) => (process.env.CI ? ms * 3 : ms);

const SHOTS = join(REPOSITORY, 'docs/screenshots');
const shots = process.env.CARGENTO_SCREENSHOTS === '1';
const only = process.env.CARGENTO_E2E_STEPS ? new RegExp(process.env.CARGENTO_E2E_STEPS) : null;
const KEY = 'cargento.next.graph.mode';

const MUTATIONS = {
  // A choice is held for the tab and never written: a reload forgets it.
  'filter-not-stored': [
    [
      'src/timeline/modes.ts',
      'if (!store.set(graphModeScope(scope.project, scope.session), mode)) return false;',
      "if (!['active', 'all', 'decisions'].includes(mode)) return false;",
    ],
  ],
  // The filter is keyed by nothing: one project's choice is every project's.
  'filter-global': [
    [
      'src/timeline/modes.ts',
      'scope: graphModeScope(options.project, options.session),',
      "scope: graphModeScope('', null),",
    ],
    [
      'src/timeline/modes.ts',
      'store.set(graphModeScope(scope.project, scope.session), mode)',
      "store.set(graphModeScope('', null), mode)",
    ],
  ],
  // The caller's default is ignored: an untouched panel opens on Active, not Decisions.
  'default-ignored': [
    [
      'src/timeline/modes.ts',
      '...(options.defaultMode ? { defaultMode: options.defaultMode } : {}),',
      '',
    ],
  ],
  // A disclosure key without its project: two projects share one open state at project scope.
  'disclosure-key-no-project': [
    [
      'src/timeline/scope.ts',
      'return disclosureKey({ project: scope.project, scope: scope.session, name });',
      "return disclosureKey({ project: '', scope: scope.session, name });",
    ],
  ],
  // An open disclosure is rebuilt by every update, closing it.
  'disclosure-remounts': [
    [
      'src/controls/Disclosure.tsx',
      'return <DisclosureNode key={props.disclosureKey} {...props} />;',
      'return <DisclosureNode key={props.disclosureKey + String(Math.random())} {...props} />;',
    ],
  ],
  // The filter buttons are rebuilt by every update, dropping keyboard focus.
  'filter-remounts': [
    [
      'src/timeline/ActivityFilter.tsx',
      'key={choice.mode}',
      'key={choice.mode + String(Math.random())}',
    ],
  ],
  // The context is read twice for the one key: a StrictMode duplicate.
  'duplicate-reads': [
    [
      'src/timeline/Timeline.tsx',
      'runtime.loadContext({ projectKey, focus: null });',
      'runtime.loadContext({ projectKey, focus: null });\n    runtime.loadContext({ projectKey: projectKey + " ", focus: null });',
    ],
  ],
};

const results = {};
const failures = [];
async function step(name, run) {
  if (only && !only.test(name)) return;
  const started = Date.now();
  try {
    const detail = await run();
    results[name] = {
      ok: true,
      ms: Date.now() - started,
      ...(detail === undefined ? {} : { detail }),
    };
  } catch (error) {
    results[name] = { ok: false, ms: Date.now() - started };
    failures.push({
      name,
      message: String(error.message || error)
        .split('\n')
        .slice(0, 6)
        .join(' | ')
        .slice(0, 1800),
    });
  }
}
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, patience(ms)));

/* ---- what a reader can observe, read the same way from either page ---- */
const rowsOf = (page) =>
  page.evaluate(() =>
    [...globalThis.document.querySelectorAll('.pc-semantic-timeline article[data-event-id]')].map(
      (row) => ({
        id: row.getAttribute('data-event-id'),
        kind: row.getAttribute('data-semantic-kind'),
        lane: row.getAttribute('data-lane-key'),
      }),
    ),
  );
const pressedOf = (page) =>
  page.evaluate(() =>
    Object.fromEntries(
      [...globalThis.document.querySelectorAll('.pc-graph-filter button')].map((button) => [
        button.textContent.trim(),
        button.getAttribute('aria-pressed') === 'true',
      ]),
    ),
  );
const headingOf = (page) =>
  page.evaluate(
    () =>
      globalThis.document.querySelector('.next-cockpit-semantic > h2')?.textContent.trim() ?? null,
  );
const storedOf = (page) => page.evaluate((key) => globalThis.localStorage.getItem(key), KEY);
const filterButton = (page, name) =>
  page.locator('.pc-graph-filter').getByRole('button', { name, exact: true });
const detailsOf = (page, id) => page.locator(`article[data-event-id="${id}"] details`).first();
const bandOf = (page) => page.locator('summary', { hasText: /^Earlier meaningful/ }).first();

const SIDES = ['legacy', 'react'];
let world, started, browser;
const both = (fn) => Promise.all(SIDES.map((name) => fn(world[name], name)));
const pairs = async (read) => {
  const [legacy, react] = await Promise.all(SIDES.map((name) => read(world[name])));
  return { legacy, react };
};
async function ready(side, fragment) {
  await side.page.goto('about:blank');
  await side.page.goto(side.origin + '/' + fragment);
  if (side.name === 'legacy')
    await side.page.waitForFunction('typeof nextData !== "undefined" && nextData !== null');
  await side.page.locator('.pc-graph-filter').waitFor();
  await side.page.waitForTimeout(patience(150));
}
/* A route change inside the document, as a reader's link or Back does it: the page keeps its memory, which is
   what a disclosure's open state is made of. `ready` is a new document and forgets it. */
async function go(side, fragment) {
  await side.page.evaluate((next) => {
    globalThis.location.hash = next;
  }, fragment);
  await side.page.locator('.pc-graph-filter').waitFor();
  await pause(500);
}
const open = (page, details) =>
  details
    .evaluate((node) => {
      node.open = true;
    })
    .then(() => pause(350))
    .then(() => page);
const isOpen = (locator) => locator.evaluate((node) => node.open);
/* A live update through each page's own refresh path. */
const refresh = (side) =>
  side.name === 'react'
    ? side.page.evaluate(() => globalThis.__harness.shell.runtime.refresh({ manual: true }))
    : side.page.evaluate(() => globalThis.nextRefreshPoll());

const SESSION = fragmentFor('decisions');
const PROJECT = fragmentFor('decisions', null);
const BETA = `#n=project:${encodeURIComponent('beta/api')}:${encodeURIComponent('codex:beta-working')}:decisions`;
const BETA_PROJECT = `#n=project:${encodeURIComponent('beta/api')}:decisions`;

try {
  started = await startWorld({ mutations: MUTATIONS });
  browser = await chromium.launch();
  const origins = [started.react.origin, started.react.viteOrigin, started.legacy.origin];
  const viewport = { width: 1100, height: 1000 };
  world = {
    legacy: {
      name: 'legacy',
      origin: started.legacy.origin,
      ...(await openTracked(browser, origins, { viewport })),
    },
    react: {
      name: 'react',
      origin: started.react.origin,
      ...(await openTracked(browser, origins, { viewport })),
    },
  };

  await step(
    'an untouched filter opens on Decisions in both, showing the same events',
    async () => {
      await both((side) => ready(side, SESSION));
      const heading = await pairs((side) => headingOf(side.page));
      assert.equal(heading.react, 'RECORDED DECISIONS');
      assert.equal(heading.legacy, 'RECORDED DECISIONS');
      const pressed = await pairs((side) => pressedOf(side.page));
      assert.deepEqual(pressed.react, { Active: false, 'All events': false, Decisions: true });
      assert.deepEqual(pressed.react, pressed.legacy);
      const rows = await pairs((side) => rowsOf(side.page));
      assert.deepEqual(
        rows.react.map((row) => row.id),
        ['gate-a'],
      );
      assert.deepEqual(rows.react, rows.legacy);
      assert.equal(
        await world.react.page.getByRole('group', { name: 'Work activity filter' }).count(),
        1,
      );
    },
  );

  const seen = {};
  await step(
    'each choice shows the events the legacy page shows, and the heading follows',
    async () => {
      for (const [label, expectedHeading] of [
        ['All events', 'SEMANTIC TIMELINE'],
        ['Active', 'SEMANTIC TIMELINE'],
        ['Decisions', 'RECORDED DECISIONS'],
      ]) {
        await both((side) => filterButton(side.page, label).click());
        await pause(200);
        const rows = await pairs((side) => rowsOf(side.page));
        assert.deepEqual(rows.react, rows.legacy, `${label}: the events differ`);
        assert.equal((await pairs((side) => headingOf(side.page))).react, expectedHeading);
        const pressed = await pairs((side) => pressedOf(side.page));
        assert.equal(pressed.react[label], true);
        assert.deepEqual(pressed.react, pressed.legacy);
        seen[label] = rows.react.length;
      }
      assert.ok(
        seen['All events'] > seen.Decisions,
        `All events shows no more than Decisions: ${JSON.stringify(seen)}`,
      );
      assert.ok(seen['All events'] >= seen.Active);
      return seen;
    },
  );

  await step(
    'the choice is written as the one released map, byte for byte, and only that key',
    async () => {
      await both((side) => filterButton(side.page, 'All events').click());
      await pause(150);
      const stored = await pairs((side) => storedOf(side.page));
      assert.equal(stored.react, stored.legacy);
      assert.equal(stored.react, JSON.stringify({ [`${TERMINAL.project}\u0000${FOCUS}`]: 'all' }));
      const keys = await pairs((side) =>
        side.page.evaluate(() => Object.keys(globalThis.localStorage).sort()),
      );
      assert.deepEqual(
        keys.react.filter((key) => key.includes('graph')),
        [KEY],
      );
    },
  );

  await step('a reload restores the choice, with the same events', async () => {
    await both((side) => side.page.reload());
    await both((side) => side.page.locator('.pc-graph-filter').waitFor());
    await pause(300);
    const pressed = await pairs((side) => pressedOf(side.page));
    assert.equal(pressed.react['All events'], true);
    assert.deepEqual(pressed.react, pressed.legacy);
    const rows = await pairs((side) => rowsOf(side.page));
    assert.deepEqual(rows.react, rows.legacy);
    assert.ok(rows.react.length > 1);
  });

  await step(
    'a sibling project, and the same project with no session, keep their own choice',
    async () => {
      await both((side) => ready(side, BETA));
      let pressed = await pairs((side) => pressedOf(side.page));
      assert.equal(
        pressed.react.Decisions,
        true,
        'the sibling project inherited another project’s choice',
      );
      assert.deepEqual(pressed.react, pressed.legacy);
      await both((side) => filterButton(side.page, 'Active').click());
      await both((side) => ready(side, PROJECT));
      pressed = await pairs((side) => pressedOf(side.page));
      assert.equal(pressed.react.Decisions, true, 'project scope inherited the session’s choice');
      assert.deepEqual(pressed.react, pressed.legacy);
      await both((side) => filterButton(side.page, 'All events').click());
      await both((side) => ready(side, SESSION));
      pressed = await pairs((side) => pressedOf(side.page));
      assert.equal(pressed.react['All events'], true);
      await both((side) => ready(side, BETA));
      pressed = await pairs((side) => pressedOf(side.page));
      assert.equal(pressed.react.Active, true);
      assert.deepEqual(pressed.react, pressed.legacy);
      const stored = await pairs((side) => storedOf(side.page));
      assert.equal(stored.react, stored.legacy);
      assert.deepEqual(
        Object.keys(JSON.parse(stored.react)).sort(),
        [
          `${TERMINAL.project}\u0000`,
          `${TERMINAL.project}\u0000${FOCUS}`,
          'beta/api\u0000codex:beta-working',
        ].sort(),
      );
    },
  );

  await step(
    'an old build’s single empty key is discarded rather than read as a project',
    async () => {
      const fresh = {};
      for (const name of SIDES) {
        fresh[name] = await openTracked(
          browser,
          [started.react.origin, started.react.viteOrigin, started.legacy.origin],
          { viewport },
        );
        await fresh[name].context.addInitScript((key) => {
          if (!globalThis.localStorage.getItem(key))
            globalThis.localStorage.setItem(key, '{"":"all"}');
        }, KEY);
      }
      try {
        for (const name of SIDES) {
          const side = { name, origin: world[name].origin, page: fresh[name].page };
          await ready(side, SESSION);
          assert.equal(
            (await pressedOf(side.page)).Decisions,
            true,
            `${name}: the empty key was read as a choice`,
          );
          await filterButton(side.page, 'Active').click();
          await pause(150);
        }
        const stored = await Promise.all(SIDES.map((name) => storedOf(fresh[name].page)));
        assert.equal(stored[0], stored[1]);
        assert.deepEqual(Object.keys(JSON.parse(stored[1])), [`${TERMINAL.project}\u0000${FOCUS}`]);
      } finally {
        await Promise.all(SIDES.map((name) => fresh[name].close()));
      }
    },
  );

  await step(
    'an opened event and the folded band keep their state across live updates, and in React keep their node',
    async () => {
      await both((side) => ready(side, SESSION));
      await both((side) => filterButton(side.page, 'All events').click());
      await pause(200);
      const rows = await pairs((side) => rowsOf(side.page));
      assert.deepEqual(rows.react, rows.legacy);
      await both((side) => open(side.page, detailsOf(side.page, 'dir-0')));
      await both(async (side) => {
        await bandOf(side.page).click();
        await pause(350);
      });
      const band = await pairs((side) =>
        bandOf(side.page).evaluate((node) => node.parentElement.open),
      );
      assert.deepEqual(band, { legacy: true, react: true });
      await world.react.page.evaluate(() => {
        globalThis.__marks = {
          event: globalThis.document.querySelector('article[data-event-id="dir-0"] details'),
          filter: globalThis.document.querySelector('.pc-graph-filter button'),
        };
      });
      await both((side) => refresh(side));
      await pause(300);
      await both((side) => refresh(side));
      await pause(500);
      const state = await pairs(async (side) => ({
        event: await isOpen(detailsOf(side.page, 'dir-0')),
        band: await bandOf(side.page).evaluate((node) => node.parentElement.open),
      }));
      assert.deepEqual(state.react, { event: true, band: true });
      assert.deepEqual(state.react, state.legacy);
      assert.equal(
        await world.react.page.evaluate(
          () =>
            globalThis.__marks.event ===
            globalThis.document.querySelector('article[data-event-id="dir-0"] details'),
        ),
        true,
        'the opened event was rebuilt by a live update',
      );
      assert.equal(
        await world.react.page.evaluate(
          () =>
            globalThis.__marks.filter ===
            globalThis.document.querySelector('.pc-graph-filter button'),
        ),
        true,
        'the filter was rebuilt by a live update',
      );
    },
  );

  await step(
    'keyboard focus stays on the button that was pressed across a live update (the legacy page drops it)',
    async () => {
      for (const name of SIDES) {
        const button = filterButton(world[name].page, 'All events');
        await button.focus();
        await world[name].page.keyboard.press('Enter');
      }
      await both((side) => refresh(side));
      await pause(500);
      const focus = await pairs((side) =>
        side.page.evaluate(() => {
          const active = globalThis.document.activeElement;
          return active && active !== globalThis.document.body
            ? active.textContent.trim().slice(0, 40)
            : null;
        }),
      );
      assert.equal(
        focus.react,
        'All events',
        'the filter button lost keyboard focus in the react page',
      );
      // Pressing a filter in the legacy page redraws the whole view, and nothing puts focus back.
      return { legacyFocusAfter: focus.legacy };
    },
  );

  await step(
    'leaving the route and coming back keeps the filter and every opened disclosure',
    async () => {
      await both((side) =>
        side.page.evaluate(() => {
          globalThis.location.hash = '#n=sessions';
        }),
      );
      await both((side) => side.page.locator('.pc-graph-filter').waitFor({ state: 'detached' }));
      await both((side) => side.page.goBack());
      await both((side) => side.page.locator('.pc-graph-filter').waitFor());
      await pause(500);
      const pressed = await pairs((side) => pressedOf(side.page));
      assert.equal(pressed.react['All events'], true);
      assert.deepEqual(pressed.react, pressed.legacy);
      const state = await pairs(async (side) => ({
        event: await isOpen(detailsOf(side.page, 'dir-0')),
        band: await bandOf(side.page).evaluate((node) => node.parentElement.open),
      }));
      assert.deepEqual(state.react, { event: true, band: true });
      assert.deepEqual(state.react, state.legacy);
    },
  );

  await step(
    'project scope and a focused session keep their own open events, and so do two projects',
    async () => {
      // Project scope, no session focused: its own filter choice and its own disclosures, closed to begin with.
      await both((side) => go(side, PROJECT));
      await both((side) => filterButton(side.page, 'All events').click());
      await pause(300);
      assert.deepEqual(
        await pairs((side) => isOpen(detailsOf(side.page, 'task-a'))),
        { legacy: false, react: false },
        'project scope began open',
      );
      await both((side) => open(side.page, detailsOf(side.page, 'task-a')));
      assert.deepEqual(
        await pairs((side) => isOpen(detailsOf(side.page, 'task-a'))),
        { legacy: true, react: true },
        'the opened event did not open',
      );
      // The same project, a focused session: the project's open event did not follow.
      await both((side) => go(side, SESSION));
      await both((side) => filterButton(side.page, 'All events').click());
      await pause(300);
      assert.deepEqual(
        await pairs((side) => isOpen(detailsOf(side.page, 'task-a'))),
        { legacy: false, react: false },
        'the session inherited the project’s open event',
      );
      // And back at project scope it is still open, as it was left.
      await both((side) => go(side, PROJECT));
      assert.deepEqual(
        await pairs((side) => isOpen(detailsOf(side.page, 'task-a'))),
        { legacy: true, react: true },
        'project scope forgot its open event',
      );
      // Another project at project scope: its own, closed.
      await both((side) => go(side, BETA_PROJECT));
      await both((side) => filterButton(side.page, 'All events').click());
      await pause(300);
      assert.deepEqual(
        await pairs((side) => isOpen(detailsOf(side.page, 'task-a'))),
        { legacy: false, react: false },
        'another project inherited the open event',
      );
    },
  );

  await step(
    'StrictMode reads the context once per key, as a page without it does, and sends no POST',
    async () => {
      const reads = (side) => side.requestsTo('/api/project-context').map((entry) => entry.path);
      const count = async (url) => {
        const probe = await openTracked(
          browser,
          [started.react.origin, started.react.viteOrigin, started.legacy.origin],
          { viewport },
        );
        try {
          await probe.page.goto(url);
          await probe.page.locator('.pc-graph-filter').waitFor();
          await pause(800);
          return { reads: reads(probe), posts: probe.log.nonGet.length };
        } finally {
          await probe.close();
        }
      };
      const strict = await count(world.react.origin + '/' + SESSION);
      const plain = await count(world.react.origin + '/?strict=0' + SESSION);
      // Two independent loads cannot be compared by exact count: the board's revision is wall-clock, so a tick inside the
      // wait adds one more read of every key in either page. What must hold is that both pages read the same keys, that
      // none is read more than a first read plus a tick plus one retry (a second start of the whole tree would put every
      // key at four on a tick), and that nothing is posted. The runtime's own unit tests pin the exact count.
      const distinct = (list) => [...new Set(list)].sort();
      assert.deepEqual(
        distinct(strict.reads),
        distinct(plain.reads),
        `the pages read different keys: ${strict.reads} vs ${plain.reads}`,
      );
      for (const url of distinct(strict.reads)) {
        const times = strict.reads.filter((read) => read === url).length;
        assert.ok(
          times >= 1 && times <= 3,
          `StrictMode read ${url} ${times} times (${strict.reads})`,
        );
      }
      assert.equal(strict.posts, 0);
      return { reads: strict.reads.length, keys: distinct(strict.reads).length };
    },
  );

  await step(
    'the layout holds at 320 and 375 px: no horizontal page scroll, controls inside the window and large enough',
    async () => {
      const report = {};
      for (const width of [320, 375]) {
        for (const name of SIDES) await world[name].page.setViewportSize({ width, height: 900 });
        await both((side) => ready(side, SESSION));
        await both((side) => filterButton(side.page, 'All events').click());
        await pause(300);
        await both((side) => open(side.page, detailsOf(side.page, 'dir-0')));
        await both(async (side) => {
          await bandOf(side.page).click();
          await pause(300);
        });
        const measure = await pairs((side) =>
          side.page.evaluate(() => {
            const { document } = globalThis;
            const doc = document.documentElement;
            const wide = [...document.querySelectorAll('.pc-semantic-timeline *')]
              .filter((node) => node.getBoundingClientRect().right > doc.clientWidth + 0.5)
              .slice(0, 5)
              .map(
                (node) => `${node.tagName.toLowerCase()}.${String(node.className).slice(0, 24)}`,
              );
            const targets = [
              ...document.querySelectorAll(
                '.pc-graph-filter button, .pc-semantic-timeline summary',
              ),
            ].map((node) => {
              const box = node.getBoundingClientRect();
              return {
                label: node.textContent.trim().slice(0, 24),
                width: Math.round(box.width),
                height: Math.round(box.height),
              };
            });
            return { overflow: doc.scrollWidth - doc.clientWidth, wide, targets };
          }),
        );
        for (const name of SIDES)
          assert.ok(
            measure[name].overflow <= 0,
            `${name}: horizontal page scroll at ${width}px (${measure[name].wide.join(' | ')})`,
          );
        const small = measure.react.targets
          .filter((target) => target.height < 44 || target.width < 44)
          .map((target) => `${target.label} ${target.width}x${target.height}`);
        assert.deepEqual(small, [], `react timeline controls under 44 px at ${width}px`);
        report[width] = {
          overflowReact: measure.react.overflow,
          overflowLegacy: measure.legacy.overflow,
        };
        if (shots) {
          await mkdir(SHOTS, { recursive: true });
          await world.react.page.screenshot({
            path: join(SHOTS, `drc-4824-timeline-react-${width}px.png`),
            fullPage: true,
          });
          await world.legacy.page.screenshot({
            path: join(SHOTS, `drc-4824-timeline-legacy-${width}px.png`),
            fullPage: true,
          });
        }
      }
      for (const name of SIDES) await world[name].page.setViewportSize(viewport);
      if (shots) {
        await both((side) => ready(side, SESSION));
        await world.react.page.screenshot({
          path: join(SHOTS, 'drc-4824-timeline-react-1100px.png'),
          fullPage: true,
        });
        await world.legacy.page.screenshot({
          path: join(SHOTS, 'drc-4824-timeline-legacy-1100px.png'),
          fullPage: true,
        });
      }
      return report;
    },
  );

  await step(
    'no external request, page error or console error, and no POST, in either page',
    async () => {
      for (const name of SIDES) {
        assert.deepEqual(world[name].log.externalRequests, [], `${name}: an external request`);
        assert.deepEqual(world[name].log.pageErrors, [], `${name}: a page error`);
        assert.deepEqual(
          world[name].log.consoleErrors.filter((text) => !/net::ERR_FAILED/.test(text)),
          [],
          `${name}: a console error`,
        );
        assert.deepEqual(world[name].log.nonGet, [], `${name}: a request that was not a GET`);
      }
    },
  );

  console.log(
    JSON.stringify(
      {
        timelineBrowser: {
          mutation: started.mutation || null,
          strictMode: true,
          realBackend: true,
          failures: failures.length,
          steps: results,
        },
      },
      null,
      2,
    ),
  );
  if (failures.length) {
    console.error(JSON.stringify({ mutation: started.mutation || null, failures }, null, 2));
    process.exitCode = 1;
  }
} catch (error) {
  console.error(
    JSON.stringify(
      {
        steps: results,
        failures,
        fatal: String(error.message || error)
          .split('\n')
          .slice(0, 6)
          .join(' | '),
      },
      null,
      2,
    ),
  );
  process.exitCode = 1;
} finally {
  for (const name of SIDES) await world?.[name]?.close?.().catch(() => undefined);
  if (browser) await browser.close();
  if (started) await started.close();
}
