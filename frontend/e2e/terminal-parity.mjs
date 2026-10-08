/*
 * The exact-session terminal in a real browser, against the real backend (DRC-4824).
 *
 * The legacy page and the React page run in the same Chromium over the same synthetic board and the same
 * synthetic read-only terminal (`frontend/test/terminal_backend.py`), and a differential compares what a
 * reader can observe: the rows the renderer drew, the scroll offset and whether it follows, the Jump
 * control, and the resources each page used (sockets, requests for the vendored renderer, external
 * requests). The legacy page is the oracle: where the two disagree the React page is wrong.
 *
 * What a unit test cannot see is proved here: that nothing typed, pasted or pressed in the terminal reaches
 * the socket (counted where the browser hands a frame to the network, and by the server not revoking the
 * connection), that StrictMode opens one socket, that leaving the route and coming back finds the same
 * screen with its output and its offset, that reconnecting and closing touch only the page's own sockets,
 * and that the layout holds at 320 and 375 CSS px.
 *
 * Models, usage, focus and notifications are off; nothing here reads a harness store, a clipboard or a
 * real terminal. Run with `pnpm test:terminal:browser`; `CARGENTO_E2E_STEPS=<regex>` runs only the steps
 * whose name matches, `CARGENTO_SCREENSHOTS=1` writes captures to docs/screenshots/, and
 * `CARGENTO_MUTATION=<name>` applies one deliberate break (see MUTATIONS), which must make the run FAIL.
 */
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { chromium } from '@playwright/test';
import {
  disconnect,
  emit,
  fragmentFor,
  numbered,
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

/* One break each, applied to the scratch copy only. A missing needle fails the run loudly rather than
   silently testing nothing. */
const MUTATIONS = {
  // The socket gains a way to send, and a key press uses it: the zero-input proof must catch it.
  'transmit-input': [
    [
      'src/terminal/useTerminalOwner.ts',
      'socket.onmessage = (event)',
      "document.addEventListener('keydown', () => { if (socket.readyState === 1) socket.send('x'); });\n  socket.onmessage = (event)",
    ],
  ],
  // Every attach starts the terminal even when one is loading or running: StrictMode opens two sockets.
  'second-socket': [
    [
      'src/terminal/owner.ts',
      'if (!current || current.terminal || current.loading || current.failed || !viewport) return;',
      'if (!current || !viewport) return;',
    ],
  ],
  // Leaving the route disposes the terminal, as a component that owned it would on unmount: the retained
  // screen is lost. (Deferred a tick so StrictMode's immediate re-attach does not mask it.)
  'dispose-on-detach': [
    [
      'src/terminal/owner.ts',
      'if (current.screen.parentElement === element) current.screen.remove();',
      'if (current.screen.parentElement === element) current.screen.remove();\n        setTimeout(() => { if (viewport === null) close(); }, 0);',
    ],
  ],
  // The follow threshold moves from 2 px to 3 px.
  'threshold-3': [
    [
      'src/terminal/viewport.ts',
      'export const FOLLOW_THRESHOLD_PX = 2;',
      'export const FOLLOW_THRESHOLD_PX = 3;',
    ],
  ],
  // The renderer script is requested when the page loads, not when a reader opens a terminal.
  'eager-renderer': [
    [
      'src/terminal/TerminalSurface.tsx',
      'const owner = useTerminalOwner();',
      "const owner = useTerminalOwner();\n  useEffect(() => { void import('./xterm').then(() => undefined); const s = document.createElement('script'); s.src = '/assets/xterm.js'; document.head.append(s); }, []);",
    ],
  ],
  // The registration recipe is a bare details that a redraw snaps shut.
  'recipe-remounts': [
    [
      'src/controls/Disclosure.tsx',
      'return <DisclosureNode key={props.disclosureKey} {...props} />;',
      'return <DisclosureNode key={props.disclosureKey + String(Math.random())} {...props} />;',
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
const near = (a, b, within, message) =>
  assert.ok(Math.abs(a - b) <= within, `${message}: ${a} vs ${b}`);

/* ---- what a reader can observe, read the same way from either page ---- */
const rowsOf = (page) =>
  page.evaluate(() =>
    [...globalThis.document.querySelectorAll('#pc-terminal-screen .xterm-rows > div')].map((row) =>
      row.textContent.replace(/\u00a0/g, ' ').trimEnd(),
    ),
  );
/* `live` is where following puts the reader once the cursor is on the last row: the screen plus the host's two
   6 px insets, less the window. It is derived from the DOM so both pages are read the same way, and it is not
   `max`: the legacy page's global `textarea` rule makes xterm's invisible helper 44 px tall, which extends its
   scroll area 21 px past the screen, so its maximum is larger than its live position and the React page's is not. */
const metricsOf = (page) =>
  page.evaluate(() => {
    const { document } = globalThis;
    const viewport = document.getElementById('pc-terminal-viewport');
    const jump = document.getElementById('pc-terminal-jump');
    const screen = document.querySelector('#pc-terminal-screen .xterm-screen');
    if (!viewport) return null;
    const max = viewport.scrollHeight - viewport.clientHeight;
    const live = screen
      ? Math.min(
          max,
          Math.max(
            0,
            Math.ceil(screen.getBoundingClientRect().height + 12 - viewport.clientHeight),
          ),
        )
      : null;
    return {
      top: viewport.scrollTop,
      scrollHeight: viewport.scrollHeight,
      client: viewport.clientHeight,
      max,
      live,
      jumpHidden: jump ? jump.hidden : null,
    };
  });
const scrollTo = (page, offset) =>
  page.evaluate((top) => {
    globalThis.document.getElementById('pc-terminal-viewport').scrollTop = top;
  }, offset);
const titleOf = (page) =>
  page.evaluate(() => {
    const bar = globalThis.document.querySelector('.pc-terminal-bar');
    return bar ? bar.textContent.replace(/\s+/g, ' ').trim() : null;
  });

async function waitRows(page, text, timeout = patience(10000)) {
  try {
    await page.waitForFunction(
      (needle) =>
        [...globalThis.document.querySelectorAll('#pc-terminal-screen .xterm-rows > div')].some(
          (row) => row.textContent.includes(needle),
        ),
      text,
      { timeout },
    );
  } catch (error) {
    // A bare timeout says nothing about which page or what it drew instead.
    const rows = await rowsOf(page).catch(() => []);
    throw new Error(
      `"${text}" never appeared (${page.url().split('/')[2]}); the page drew: ${JSON.stringify(rows.filter(Boolean).slice(-6))}`,
      { cause: error },
    );
  }
}

/* A real wheel over the host's 6 px inset, after bringing the terminal into the window: over the renderer
   itself the wheel scrolls xterm's own scrollback and the container never moves, in the legacy page as in
   this one, and a terminal below the fold takes no wheel at all. */
async function wheelOverInset(side, deltaY) {
  await side.page.locator('#pc-terminal-viewport').scrollIntoViewIfNeeded();
  const box = await side.page.locator('#pc-terminal-viewport').boundingBox();
  await side.page.mouse.move(box.x + 3, box.y + box.height / 2);
  await side.page.mouse.wheel(0, deltaY);
}

/* A fixed wait only guesses how long the page needs. This reads until two consecutive readings agree, so a
   runner that delivers scroll events late is waited for instead of measured mid-flight (the threshold step read
   the legacy page 150 ms after a scroll on a hosted macOS runner and saw it still following). */
async function settled(read) {
  let last = JSON.stringify(await read());
  for (let still = 0, tries = 0; still < 2 && tries < 60; tries += 1) {
    await pause(60);
    const now = JSON.stringify(await read());
    still = now === last ? still + 1 : 0;
    last = now;
  }
  return JSON.parse(last);
}

/* The sides: one tracked page each over the same backend pair. */
const SIDES = ['legacy', 'react'];

/* A real press on Jump to live, only when it is on screen: a hidden control cannot be pressed. */
async function jumpIfShown(side) {
  const state = await metricsOf(side.page);
  if (state && state.jumpHidden === false)
    await side.page.getByRole('button', { name: 'Jump to live' }).click();
}

async function ready(side, fragment) {
  const { page } = side;
  await page.goto('about:blank');
  await page.goto(side.origin + '/' + fragment);
  if (side.name === 'legacy')
    await page.waitForFunction('typeof nextData !== "undefined" && nextData !== null');
  await page.waitForTimeout(patience(200));
}
/* A terminal the bridge has not registered is not "operational content" on the legacy Console, so it sits inside
   the closed "How this server was started" disclosure there. The React surface has no such wrapper: the
   Console that hosts it owns that disclosure. */
async function revealSetup(side) {
  if (side.name !== 'legacy') return;
  const details = side.page.locator('details[data-next-cockpit-console-setup]');
  await details.waitFor();
  if (!(await details.evaluate((node) => node.open))) await details.locator('> summary').click();
  await pause(300);
}
const openButton = (side) => side.page.getByRole('button', { name: 'Open terminal', exact: true });

const both = (fn) => Promise.all(SIDES.map((name) => fn(world[name], name)));
const pairs = async (read) => {
  const [legacy, react] = await Promise.all(SIDES.map((name) => read(world[name])));
  return { legacy, react };
};

let browser, world, started;
try {
  const w = await startWorld({ mutations: MUTATIONS });
  started = w;
  browser = await chromium.launch();
  const origins = [w.react.origin, w.react.viteOrigin, w.legacy.origin];
  world = {
    legacy: {
      name: 'legacy',
      origin: w.legacy.origin,
      control: w.legacy.control,
      ...(await openTracked(browser, origins, { viewport: { width: 1100, height: 900 } })),
    },
    react: {
      name: 'react',
      origin: w.react.origin,
      control: w.react.control,
      ...(await openTracked(browser, origins, { viewport: { width: 1100, height: 900 } })),
    },
  };
  const consoleFragment = fragmentFor('console');
  const awayFragment = '#n=sessions';

  // -----------------------------------------------------------------------------------------------
  await step(
    'a registered session offers Open terminal and starts nothing until it is pressed',
    async () => {
      await both((side) => ready(side, consoleFragment));
      await both((side) => openButton(side).waitFor());
      for (const name of SIDES) {
        const side = world[name];
        assert.equal(side.stream().length, 0, `${name}: a socket opened before the press`);
        assert.equal(
          side.requestsTo('/assets/xterm').length,
          0,
          `${name}: the renderer was requested before the press`,
        );
        assert.deepEqual(side.log.nonGet, [], `${name}: a request that was not a GET`);
      }
      const stats = await world.react.page.evaluate(() => globalThis.__harness.owner.stats());
      assert.equal(stats.terminals, 0);
      assert.equal(stats.sockets, 0);
      assert.equal(stats.openKey, null);
    },
  );

  await step(
    'pressing Open terminal opens one terminal, one socket and the two local assets, in both',
    async () => {
      await both((side) => openButton(side).click());
      await both((side) => side.page.locator('#pc-terminal-screen .xterm').waitFor());
      await both((side) => waitRows(side.page, TERMINAL.banner));
      for (const name of SIDES) {
        const side = world[name];
        assert.equal(side.stream().length, 1, `${name}: expected one terminal socket`);
        assert.equal(
          side.requestsTo('/assets/xterm.js').length,
          1,
          `${name}: renderer script requests`,
        );
        assert.equal(
          side.requestsTo('/assets/xterm.css').length,
          1,
          `${name}: renderer stylesheet requests`,
        );
        assert.deepEqual(side.log.externalRequests, [], `${name}: an external request`);
        assert.deepEqual(side.log.nonGet, [], `${name}: a request that was not a GET`);
        assert.equal(
          await side.page.locator('#pc-terminal-screen .xterm').count(),
          1,
          `${name}: renderer count`,
        );
      }
      const title = await pairs((side) => titleOf(side.page));
      assert.ok(title.legacy?.includes(TERMINAL.title), `legacy title: ${title.legacy}`);
      assert.ok(
        title.react?.includes(TERMINAL.title),
        `react title (zero coordinates kept): ${title.react}`,
      );
      assert.ok(title.react?.includes('read-only'));
      const labels = await pairs((side) =>
        side.page.evaluate(() => {
          const area = globalThis.document.querySelector(
            '#pc-terminal-screen .xterm-helper-textarea',
          );
          return area ? { readOnly: area.readOnly, label: area.getAttribute('aria-label') } : null;
        }),
      );
      assert.deepEqual(labels.react, { readOnly: true, label: 'Read-only terminal output' });
      assert.deepEqual(labels.react, labels.legacy);
      const stats = await world.react.page.evaluate(() => globalThis.__harness.owner.stats());
      assert.deepEqual(
        { terminals: stats.terminals, sockets: stats.sockets, attached: stats.attached },
        { terminals: 1, sockets: 1, attached: true },
      );
      return { sockets: 1, rendererRequests: 2, strictMode: true };
    },
  );

  await step(
    'short output stays readable: the banner row is inside the viewport, at offset zero',
    async () => {
      const seen = await pairs((side) =>
        side.page.evaluate(() => {
          const viewport = globalThis.document
            .getElementById('pc-terminal-viewport')
            .getBoundingClientRect();
          const row = [
            ...globalThis.document.querySelectorAll('#pc-terminal-screen .xterm-rows > div'),
          ].find((node) => node.textContent.includes('Synthetic read-only'));
          const box = row.getBoundingClientRect();
          return {
            visible: box.top >= viewport.top - 0.5 && box.bottom <= viewport.bottom + 0.5,
            top: globalThis.document.getElementById('pc-terminal-viewport').scrollTop,
          };
        }),
      );
      assert.equal(seen.react.visible, true, 'the banner row is outside the react viewport');
      assert.equal(seen.legacy.visible, true, 'the banner row is outside the legacy viewport');
      assert.equal(seen.react.top, seen.legacy.top);
    },
  );

  await step(
    'long output: both draw the same rows and follow it to the same live position, with Jump hidden',
    async () => {
      await both((side, name) => emit(world[name], numbered(1, 60)));
      await both((side) => waitRows(side.page, 'line 060'));
      await pause(250);
      const rows = await pairs((side) => rowsOf(side.page));
      assert.deepEqual(rows.react, rows.legacy);
      const metrics = await pairs((side) => metricsOf(side.page));
      assert.ok(
        metrics.legacy.live > 20,
        `the terminal is not taller than its window: ${JSON.stringify(metrics.legacy)}`,
      );
      near(metrics.react.live, metrics.legacy.live, 1, 'live position');
      near(metrics.react.top, metrics.react.live, 2, 'react follows to the live position');
      near(metrics.legacy.top, metrics.legacy.live, 2, 'legacy follows to the live position');
      assert.equal(metrics.react.jumpHidden, true);
      assert.equal(metrics.legacy.jumpHidden, true);
      if (shots) {
        await mkdir(SHOTS, { recursive: true });
        await world.react.page.screenshot({
          path: join(SHOTS, 'drc-4824-terminal-react-1100px.png'),
          fullPage: true,
        });
        await world.legacy.page.screenshot({
          path: join(SHOTS, 'drc-4824-terminal-legacy-1100px.png'),
          fullPage: true,
        });
      }
      return {
        live: metrics.react.live,
        maxReact: metrics.react.max,
        maxLegacy: metrics.legacy.max,
      };
    },
  );

  await step(
    'scrolling away stops following: Jump shows and new output does not move the reader',
    async () => {
      for (const name of SIDES) await wheelOverInset(world[name], -160);
      await pause(300);
      const before = await pairs((side) => metricsOf(side.page));
      assert.equal(before.legacy.jumpHidden, false, 'Jump to live did not show in legacy');
      assert.equal(before.react.jumpHidden, false, 'Jump to live did not show in react');
      assert.ok(before.react.top < before.react.live - 20);
      near(before.react.top, before.legacy.top, 1, 'scrolled offset');
      await both((side, name) => emit(world[name], numbered(61, 66)));
      await both((side) => waitRows(side.page, 'line 066'));
      await pause(250);
      const after = await pairs((side) => metricsOf(side.page));
      near(after.react.top, before.react.top, 1, 'react moved while the reader was away');
      near(after.legacy.top, before.legacy.top, 1, 'legacy moved while the reader was away');
      assert.equal(after.react.jumpHidden, false);
      assert.equal(after.legacy.jumpHidden, false);
      const rows = await pairs((side) => rowsOf(side.page));
      assert.deepEqual(rows.react, rows.legacy);
    },
  );

  await step('Jump to live resumes following, and new output is then followed again', async () => {
    await both((side) => side.page.getByRole('button', { name: 'Jump to live' }).click());
    await pause(200);
    const jumped = await pairs((side) => metricsOf(side.page));
    near(jumped.react.top, jumped.react.live, 2, 'react did not reach live');
    near(jumped.legacy.top, jumped.legacy.live, 2, 'legacy did not reach live');
    near(jumped.react.top, jumped.legacy.top, 1, 'jump offset');
    assert.equal(jumped.react.jumpHidden, true);
    assert.equal(jumped.legacy.jumpHidden, true);
    await both((side, name) => emit(world[name], numbered(67, 72)));
    await both((side) => waitRows(side.page, 'line 072'));
    await pause(250);
    const followed = await pairs((side) => metricsOf(side.page));
    near(followed.react.top, followed.react.live, 2, 'react stopped following');
    near(followed.legacy.top, followed.legacy.live, 2, 'legacy stopped following');
    near(followed.react.top, followed.legacy.top, 1, 'followed offset');
  });

  await step(
    'the follow threshold agrees with the legacy page offset by offset, and flips at 3 px from live',
    async () => {
      const flips = { legacy: [], react: [] };
      const distances = [0, 1, 2, 3, 4, 6];
      for (const distance of distances) {
        for (const name of SIDES) {
          const { live } = await metricsOf(world[name].page);
          await scrollTo(world[name].page, live);
          await scrollTo(world[name].page, live - distance);
        }
        const state = await settled(() =>
          pairs(async (side) => (({ jumpHidden }) => ({ jumpHidden }))(await metricsOf(side.page))),
        );
        flips.legacy.push(state.legacy.jumpHidden);
        flips.react.push(state.react.jumpHidden);
      }
      assert.deepEqual(
        flips.react,
        flips.legacy,
        `threshold: react ${flips.react} vs legacy ${flips.legacy}`,
      );
      assert.deepEqual(
        flips.react,
        [true, true, true, false, false, false],
        `the flip is not between 2 px and 3 px: ${flips.react}`,
      );
      return { distances, followingByDistance: flips.react };
    },
  );

  await step(
    'typing, pasting and key presses transmit no frame, and nothing revokes the socket',
    async () => {
      await both((side) => jumpIfShown(side));
      for (const name of SIDES) {
        const { page } = world[name];
        await page.locator('#pc-terminal-screen .xterm-helper-textarea').focus();
        await page.keyboard.type('echo this must never leave the browser');
        await page.keyboard.press('Enter');
        await page.keyboard.press('Control+C');
        await page.keyboard.press('ArrowUp');
        await page.keyboard.insertText('pasted text');
        await page.evaluate(() => {
          const area = globalThis.document.querySelector(
            '#pc-terminal-screen .xterm-helper-textarea',
          );
          const data = new globalThis.DataTransfer();
          data.setData('text/plain', 'pasted through an event');
          area.dispatchEvent(
            new globalThis.ClipboardEvent('paste', {
              clipboardData: data,
              bubbles: true,
              cancelable: true,
            }),
          );
        });
        await page.locator('#pc-terminal-screen').click();
        await page.keyboard.type('and clicking first');
      }
      await pause(600);
      for (const name of SIDES) {
        const [socket] = world[name].stream();
        assert.deepEqual(
          socket.sent,
          [],
          `${name}: the page sent ${socket.sent.length} frame(s) on the terminal socket`,
        );
        assert.equal(
          socket.closed,
          null,
          `${name}: the socket was closed: ${JSON.stringify(socket.closed)}`,
        );
      }
      // And it still streams afterwards: nothing the reader did ended it.
      await both((side, name) => emit(world[name], 'still streaming\r\n'));
      await both((side) => waitRows(side.page, 'still streaming'));
      return { framesSentByPage: 0 };
    },
  );

  await step(
    'leaving the route and coming back finds the same screen, output, socket and offset',
    async () => {
      // Put the reader somewhere that is not the end.
      for (const name of SIDES) await wheelOverInset(world[name], -30);
      await pause(300);
      const before = await pairs((side) => metricsOf(side.page));
      assert.equal(before.react.jumpHidden, false);
      await world.react.page.evaluate(() => {
        globalThis.__mark = globalThis.document.getElementById('pc-terminal-screen');
      });
      const requests = {
        legacy: world.legacy.requestsTo('/assets/xterm').length,
        react: world.react.requestsTo('/assets/xterm').length,
      };
      await both((side) =>
        side.page.evaluate((fragment) => {
          globalThis.location.hash = fragment;
        }, awayFragment),
      );
      await both((side) =>
        side.page.locator('#pc-terminal-viewport').waitFor({ state: 'detached' }),
      );
      await both((side, name) => emit(world[name], 'printed while away\r\n'));
      await pause(400);
      for (const name of SIDES)
        assert.equal(
          world[name].stream().filter((socket) => socket.closed === null).length,
          1,
          `${name}: the socket did not stay open while away`,
        );
      await both((side) => side.page.goBack());
      await both((side) => side.page.locator('#pc-terminal-viewport').waitFor());
      await both((side) => waitRows(side.page, 'printed while away'));
      await pause(300);
      const rows = await pairs((side) => rowsOf(side.page));
      assert.ok(
        rows.react.some((row) => row.includes('printed while away')),
        'the output printed while away is missing in react',
      );
      assert.deepEqual(
        rows.react,
        rows.legacy,
        `rows differ after coming back: react ${JSON.stringify(rows.react.filter(Boolean))} legacy ${JSON.stringify(rows.legacy.filter(Boolean))}`,
      );
      const after = await pairs((side) => metricsOf(side.page));
      near(after.react.top, before.react.top, 1, 'react did not restore the offset');
      near(after.legacy.top, before.legacy.top, 1, 'legacy did not restore the offset');
      assert.equal(after.react.jumpHidden, false);
      for (const name of SIDES) {
        assert.equal(world[name].stream().length, 1, `${name}: coming back opened another socket`);
        assert.equal(
          world[name].requestsTo('/assets/xterm').length,
          requests[name],
          `${name}: coming back asked for the renderer again`,
        );
      }
      assert.equal(
        await world.react.page.evaluate(
          () => globalThis.__mark === globalThis.document.getElementById('pc-terminal-screen'),
        ),
        true,
        'react drew a different screen element',
      );
      const stats = await world.react.page.evaluate(() => globalThis.__harness.owner.stats());
      assert.deepEqual(
        { terminals: stats.terminals, sockets: stats.sockets },
        { terminals: 1, sockets: 1 },
      );
      return { sameScreenElement: true, socketsOpened: 1 };
    },
  );

  await step(
    'an offset past the new scroll maximum is clamped to it on return, as the legacy page clamps',
    async () => {
      for (const name of SIDES) await world[name].page.setViewportSize({ width: 700, height: 900 });
      await pause(300);
      for (const name of SIDES) {
        const { live } = await metricsOf(world[name].page);
        await scrollTo(world[name].page, live - 30);
      }
      await pause(200);
      const before = await pairs((side) => metricsOf(side.page));
      assert.equal(before.react.jumpHidden, false);
      await both((side) =>
        side.page.evaluate((fragment) => {
          globalThis.location.hash = fragment;
        }, awayFragment),
      );
      await both((side) =>
        side.page.locator('#pc-terminal-viewport').waitFor({ state: 'detached' }),
      );
      // Wider again: the window is taller, so the same content has a smaller maximum.
      for (const name of SIDES)
        await world[name].page.setViewportSize({ width: 1100, height: 900 });
      await pause(200);
      await both((side) => side.page.goBack());
      await both((side) => side.page.locator('#pc-terminal-viewport').waitFor());
      await pause(300);
      const after = await pairs((side) => metricsOf(side.page));
      for (const name of SIDES) {
        assert.ok(
          after[name].max < before[name].max - 20,
          `${name}: the maximum did not shrink, so nothing was clamped`,
        );
        assert.ok(
          before[name].top > after[name].max,
          `${name}: the saved offset was not past the new maximum`,
        );
        near(after[name].top, after[name].max, 1, `${name} did not clamp to the new maximum`);
      }
      return {
        offsetBefore: before.react.top,
        maxAfter: after.react.max,
        offsetAfter: after.react.top,
      };
    },
  );

  await step(
    'a dropped stream reconnects, one socket at a time, and the old one is closed',
    async () => {
      await both((side) => jumpIfShown(side));
      await both((side, name) => disconnect(world[name]));
      await both((side) => waitRows(side.page, 'control-mode-disconnected'));
      await pause(3300);
      for (const name of SIDES) {
        const sockets = world[name].stream();
        assert.ok(
          sockets.length >= 3,
          `${name}: expected repeated reconnects, saw ${sockets.length}`,
        );
        assert.ok(
          sockets.slice(0, -1).every((socket) => socket.closed !== null),
          `${name}: a superseded socket is still open`,
        );
        assert.ok(
          sockets.filter((socket) => socket.closed === null).length <= 1,
          `${name}: more than one socket open at once`,
        );
        assert.deepEqual(
          sockets.flatMap((socket) => socket.sent),
          [],
          `${name}: a reconnect sent a frame`,
        );
      }
      for (const name of SIDES) {
        const response = await fetch(world[name].origin + '/api/interaction/reconnect', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: '{}',
        });
        assert.equal(response.status, 200);
      }
      await pause(1500);
      await both((side, name) => emit(world[name], 'after reconnect\r\n'));
      await both((side) => waitRows(side.page, 'after reconnect'));
      const rows = await pairs((side) => rowsOf(side.page));
      assert.ok(rows.react.some((row) => row.includes('after reconnect')));
      return { reconnectSockets: world.react.stream().length };
    },
  );

  await step(
    'Close lets go of exactly the page’s own socket and renderer, and nothing reconnects',
    async () => {
      await both((side) => side.page.getByRole('button', { name: 'Close' }).click());
      await both((side) => openButton(side).waitFor());
      /* The count is taken once Close has taken effect: the stream was still reconnecting when it was pressed, and
       a reconnect that landed between a count taken before the press and the press itself is not a socket opened
       after Close (a hosted runner measured exactly that: 10 against 9). */
      const before = { legacy: world.legacy.stream().length, react: world.react.stream().length };
      await pause(2600);
      for (const name of SIDES) {
        const sockets = world[name].stream();
        assert.equal(sockets.length, before[name], `${name}: a socket opened after Close`);
        assert.ok(
          sockets.every((socket) => socket.closed !== null),
          `${name}: a terminal socket is still open after Close`,
        );
        assert.equal(
          await world[name].page.locator('#pc-terminal-screen .xterm').count(),
          0,
          `${name}: the renderer is still on the page`,
        );
      }
      const stats = await world.react.page.evaluate(() => globalThis.__harness.owner.stats());
      assert.deepEqual(
        { terminals: stats.terminals, sockets: stats.sockets, openKey: stats.openKey },
        { terminals: 0, sockets: 0, openKey: null },
      );
    },
  );

  await step('opening again after Close opens one fresh terminal, not two', async () => {
    const before = { legacy: world.legacy.stream().length, react: world.react.stream().length };
    await both((side) => openButton(side).click());
    await both((side) => side.page.locator('#pc-terminal-screen .xterm').waitFor());
    await both((side) => waitRows(side.page, TERMINAL.banner));
    for (const name of SIDES) {
      assert.equal(
        world[name].stream().length,
        before[name] + 1,
        `${name}: expected exactly one new socket`,
      );
      assert.equal(
        await world[name].page.locator('#pc-terminal-screen .xterm').count(),
        1,
        `${name}: renderer count`,
      );
      assert.equal(
        world[name].requestsTo('/assets/xterm.js').length,
        1,
        `${name}: the renderer script was requested again`,
      );
    }
    await both((side) => side.page.getByRole('button', { name: 'Close' }).click());
  });

  await step(
    'refused, disabled and failed readings say what they are, with the recipe behind a disclosure that stays open',
    async () => {
      const other = `#n=project:${encodeURIComponent('beta/api')}:${encodeURIComponent('codex:beta-working')}:console`;
      await both((side) => ready(side, other));
      await both((side) => revealSetup(side));
      const sentences = await pairs(async (side) => {
        await side.page.getByText('How to register a terminal').waitFor();
        return side.page.evaluate(() => ({
          message: [
            ...globalThis.document.querySelectorAll(
              '.pc-terminal-absence .pc-substrate-empty, .next-cockpit-terminal .pc-substrate-empty',
            ),
          ]
            .map((node) => node.textContent.trim())
            .filter(Boolean),
          steps: [...globalThis.document.querySelectorAll('.pc-substrate-steps li')].map((node) =>
            node.textContent.trim(),
          ),
        }));
      });
      assert.ok(
        sentences.react.message.includes('The registered terminal belongs to another session.'),
        JSON.stringify(sentences.react),
      );
      assert.deepEqual(sentences.react.steps, sentences.legacy.steps);
      assert.equal(sentences.react.steps.length, 2);
      assert.ok(sentences.react.message.includes('Output is read-only.'));
      // Open it, then let live data arrive: it must stay open, and keep its node in the React page.
      await both((side) => side.page.getByText('How to register a terminal').click());
      await world.react.page.evaluate(() => {
        globalThis.__recipe = globalThis.document.querySelector('details:has(.pc-substrate-steps)');
      });
      await world.react.page.evaluate(() =>
        globalThis.__harness.shell.runtime.refresh({ manual: true }),
      );
      await world.legacy.page.evaluate(() => globalThis.nextRefreshPoll());
      await pause(500);
      const open = await pairs((side) =>
        side.page.evaluate(
          () => globalThis.document.querySelector('details:has(.pc-substrate-steps)')?.open ?? null,
        ),
      );
      assert.deepEqual(open, { legacy: true, react: true });
      assert.equal(
        await world.react.page.evaluate(
          () =>
            globalThis.__recipe ===
            globalThis.document.querySelector('details:has(.pc-substrate-steps)'),
        ),
        true,
        'the disclosure was rebuilt by a live update',
      );
      // Away and back: still open.
      await both((side) =>
        side.page.evaluate((fragment) => {
          globalThis.location.hash = fragment;
        }, awayFragment),
      );
      await pause(300);
      await both((side) => side.page.goBack());
      await pause(500);
      const back = await pairs((side) =>
        side.page.evaluate(
          () => globalThis.document.querySelector('details:has(.pc-substrate-steps)')?.open ?? null,
        ),
      );
      assert.deepEqual(back, { legacy: true, react: true });
    },
  );

  await step(
    'a missing bridge, a failed lookup and an incomplete origin read the same in both pages',
    async () => {
      const cases = [
        [
          '404 reads as the bridge being off',
          { status: 404, body: '' },
          'The terminal bridge is disabled on this server.',
        ],
        [
          'a server error reads as a lookup that could not be made',
          { status: 500, body: '' },
          'Terminal registration could not be checked because the local request failed.',
        ],
      ];
      const seen = {};
      for (const [name, answer, sentence] of cases) {
        await both((side) =>
          side.page.route('**/api/interaction/origin*', (route) => route.fulfill(answer)),
        );
        await both((side) => ready(side, consoleFragment));
        await both((side) => revealSetup(side));
        await both((side) => side.page.getByText(sentence).waitFor());
        seen[name] = true;
        await both((side) => side.page.unroute('**/api/interaction/origin*'));
      }
      const incomplete = {
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          state: 'registered',
          origin: { window_index: 0 },
          origin_id_hint: 'abcd1234',
        }),
      };
      await both((side) =>
        side.page.route('**/api/interaction/origin*', (route) => route.fulfill(incomplete)),
      );
      await both((side) => ready(side, consoleFragment));
      await both((side) => openButton(side).click());
      await both((side) => side.page.getByText('Pane index not published.').waitFor());
      const titles = await pairs((side) =>
        side.page.evaluate(() =>
          [...globalThis.document.querySelectorAll('.pc-terminal-identity > *')].map((node) =>
            node.textContent.trim(),
          ),
        ),
      );
      assert.deepEqual(titles.react, titles.legacy);
      assert.ok(
        titles.react.includes('window 0'),
        `a zero window index must stay readable: ${titles.react}`,
      );
      await both((side) => side.page.unroute('**/api/interaction/origin*'));
      return seen;
    },
  );

  await step(
    'the layout holds at 320 and 375 px: no horizontal page scroll, the terminal and its controls inside the window',
    async () => {
      const report = {};
      for (const width of [320, 375]) {
        for (const name of SIDES) await world[name].page.setViewportSize({ width, height: 800 });
        await both((side) => ready(side, consoleFragment));
        await both((side) => openButton(side).click());
        await both((side) => side.page.locator('#pc-terminal-screen .xterm').waitFor());
        await both((side, name) => emit(world[name], numbered(100, 130)));
        await both((side) => waitRows(side.page, 'line 130'));
        await pause(300);
        const measure = await pairs((side) =>
          side.page.evaluate(() => {
            const { document } = globalThis;
            const doc = document.documentElement;
            const bar = document.querySelector('.pc-terminal-bar');
            const viewport = document
              .getElementById('pc-terminal-viewport')
              .getBoundingClientRect();
            const buttons = [
              ...document.querySelectorAll('.pc-terminal-bar button:not([hidden])'),
            ].map((node) => {
              const box = node.getBoundingClientRect();
              return {
                label: node.textContent.trim(),
                width: Math.round(box.width),
                height: Math.round(box.height),
                right: Math.round(box.right),
              };
            });
            return {
              overflow: doc.scrollWidth - doc.clientWidth,
              barRight: bar ? Math.round(bar.getBoundingClientRect().right) : null,
              viewportRight: Math.round(viewport.right),
              viewportHeight: Math.round(viewport.height),
              client: doc.clientWidth,
              buttons,
            };
          }),
        );
        for (const name of SIDES) {
          assert.ok(
            measure[name].overflow <= 0,
            `${name}: horizontal page scroll at ${width}px: ${measure[name].overflow}`,
          );
          assert.ok(
            measure[name].viewportRight <= measure[name].client + 1,
            `${name}: the terminal overflows the window at ${width}px`,
          );
          for (const button of measure[name].buttons)
            assert.ok(
              button.right <= measure[name].client + 1,
              `${name}: "${button.label}" is outside the window at ${width}px`,
            );
        }
        const small = measure.react.buttons
          .filter((button) => button.height < 44 || button.width < 44)
          .map((button) => `${button.label} ${button.width}x${button.height}`);
        assert.deepEqual(small, [], `react terminal controls under 44 px at ${width}px`);
        report[width] = {
          overflowReact: measure.react.overflow,
          overflowLegacy: measure.legacy.overflow,
          viewportHeight: measure.react.viewportHeight,
        };
        if (shots) {
          await mkdir(SHOTS, { recursive: true });
          await world.react.page.screenshot({
            path: join(SHOTS, `drc-4824-terminal-react-${width}px.png`),
            fullPage: true,
          });
          await world.legacy.page.screenshot({
            path: join(SHOTS, `drc-4824-terminal-legacy-${width}px.png`),
            fullPage: true,
          });
        }
        await both((side) => side.page.getByRole('button', { name: 'Close' }).click());
      }
      for (const name of SIDES)
        await world[name].page.setViewportSize({ width: 1100, height: 900 });
      return report;
    },
  );

  await step(
    'a page without StrictMode opens the same one socket and the same two assets',
    async () => {
      const plain = await openTracked(browser, origins, { viewport: { width: 1100, height: 900 } });
      try {
        await plain.page.goto(world.react.origin + '/?strict=0' + consoleFragment);
        await plain.page.getByRole('button', { name: 'Open terminal', exact: true }).click();
        await plain.page.locator('#pc-terminal-screen .xterm').waitFor();
        // The pane's whole history replays to a new socket, so the banner has long scrolled off: wait for a fresh line.
        await emit(world.react, 'plain page marker\r\n');
        await waitRows(plain.page, 'plain page marker');
        assert.equal(plain.stream().length, 1);
        assert.equal(plain.requestsTo('/assets/xterm.js').length, 1);
        assert.equal(plain.requestsTo('/assets/xterm.css').length, 1);
      } finally {
        await plain.close();
      }
    },
  );

  await step('no external request, page error or console error in either page', async () => {
    for (const name of SIDES) {
      assert.deepEqual(world[name].log.externalRequests, [], `${name}: an external request`);
      assert.deepEqual(world[name].log.pageErrors, [], `${name}: a page error`);
      assert.deepEqual(
        world[name].log.consoleErrors.filter(
          (text) =>
            !/net::ERR_FAILED|Failed to load resource: the server responded with a status of (404|500)/.test(
              text,
            ),
        ),
        [],
        `${name}: a console error`,
      );
      assert.deepEqual(world[name].log.nonGet, [], `${name}: a request that was not a GET`);
    }
  });

  console.log(
    JSON.stringify(
      {
        terminalBrowser: {
          mutation: w.mutation || null,
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
    console.error(JSON.stringify({ mutation: w.mutation || null, failures }, null, 2));
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
