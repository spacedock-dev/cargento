/*
 * The capacity strip, the usage consent and the observer-model consent in a real browser, against the real
 * backend (DRC-4827, capacity half).
 *
 * The legacy page and the React page run in the same Chromium over the same synthetic board
 * (`frontend/test/capacity_backend.py`), and each backend counts what matters to a person who was promised a
 * disclosure: the requests that carried `usage=1` to the application and the project-context requests that
 * carried the observer-model consent. A differential then compares what a reader can observe on the two
 * pages: the strip's rows and which one is selected, the consent controls, and the requests each page made.
 * The legacy page is the oracle, and a check on it that depends on timing is recorded instead of failing the
 * run on a loaded runner; the React page is always held to every assertion.
 *
 * What a unit test cannot see is proved here: that an unanswered or declined consent sends no usage parameter
 * through a mount, StrictMode, a route change, a reload and a reconnect; that the parameter rides the very next
 * request after a real press and stops at the next one after turning it off; that the answer is per origin;
 * that the selected window survives a redraw that reorders it and a route change; that allowing the observer
 * model sends nothing and that one press of Summarize sends one request for the exact session; that nothing
 * posts, raises a terminal or notifies; and that the layout holds at 320 and 375 CSS px.
 *
 * No model is called, no credential is read and no vendor is contacted: the backend answers from fixed numbers
 * and records the request instead of acting on it. `Notification` is a script that records and shows nothing.
 * Run with `pnpm test:capacity:browser`; `CARGENTO_E2E_STEPS=<regex>` runs only the steps whose name matches,
 * `CARGENTO_SCREENSHOTS=1` writes captures to docs/screenshots/, and `CARGENTO_MUTATION=<name>` applies one
 * deliberate break (see MUTATIONS), which must make the run FAIL.
 */
import assert from 'node:assert/strict';
import { execFileSync, spawn } from 'node:child_process';
import { cp, mkdir, mkdtemp, readFile, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { chromium } from '@playwright/test';
import { isolatedEnvironment } from '../dev/protocol.mjs';
import { startDevelopment } from '../dev/supervisor.mjs';
import { freePorts, openPage, REPOSITORY } from './support/browser.mjs';

/* Every fixed wait here means "give the page time to react". A hosted runner has a few shared cores and delivers
   events later than a desktop, so each wait is tripled there; only a pass gets slower. */
const patience = (ms) => (process.env.CI ? ms * 3 : ms);
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, patience(ms)));

const SHOTS = join(REPOSITORY, 'docs/screenshots');
const shots = process.env.CARGENTO_SCREENSHOTS === '1';
const only = process.env.CARGENTO_E2E_STEPS ? new RegExp(process.env.CARGENTO_E2E_STEPS) : null;

/* One break each, applied to the scratch copy only. A missing needle fails the run loudly rather than silently
   testing nothing. */
const MUTATIONS = {
  // An unanswered consent is read as a yes: the first request carries the usage parameter.
  'unanswered-is-yes': [
    [
      'src/transport/runtime.ts',
      "usage: storage.usageConsent() === 'granted',",
      "usage: storage.usageConsent() !== 'declined',",
    ],
  ],
  // The disclosure stays after the answer, claiming a decision the switch also claims.
  'disclosure-stays': [
    [
      'src/capacity/UsageConsent.tsx',
      'if (!offered || consent !== null) return null;',
      'if (!offered) return null;',
    ],
  ],
  // Allowing the observer model also asks it for a summary.
  'allow-sends': [
    [
      'src/capacity/ObserverControls.tsx',
      "if (action === 'allow') answer('granted');",
      "if (action === 'allow') {\n      answer('granted');\n      summarize();\n    }",
    ],
  ],
  // The observer model is asked for a summary as soon as the controls are drawn with consent already given.
  'observer-on-mount': [
    [
      'src/capacity/ObserverControls.tsx',
      "import { useState, type ReactNode } from 'react';",
      "import { useEffect, useState, type ReactNode } from 'react';",
    ],
    [
      'src/capacity/ObserverControls.tsx',
      'const model = selectObserverModel(entry);',
      "useEffect(() => {\n    if (identity && heldFor(runtime).observer.read() === 'granted')\n      void runtime.requestObserverSummary({ projectKey, focus: identity });\n  }, [entry]);\n  const model = selectObserverModel(entry);",
    ],
  ],
  // The selection is not kept: the first window is always the selected one.
  'selection-forgotten': [
    [
      'src/capacity/model.ts',
      'const selected = rows.find((row) => rowKey(row) === key) ?? first;',
      'const selected = first;',
    ],
  ],
  // A fallback is not held: the stored selection is never written back.
  'fallback-not-held': [
    ['src/capacity/CapacityStrip.tsx', 'if (read) lane.set(selectedKey);', 'void read;'],
  ],
  // A row with no clock is given a tick at the middle of its bar.
  'invented-tick': [
    [
      'src/capacity/CapacityStrip.tsx',
      'if (row.elapsed === null) {\n    return (',
      'if (row.elapsed === null && row.pct < 0) {\n    return (',
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

/* A check on the legacy page that depends on its timing. The legacy page is the oracle, so on a loaded runner a
   check it fails is recorded under the run's notes instead of failing it. */
const legacyNotes = [];
function legacySoft(label, check) {
  try {
    check();
  } catch (error) {
    legacyNotes.push(`${label}: ${String(error.message || error).split('\n')[0]}`);
  }
}

/* Waits for a condition read from the page or the server, and says what it was waiting for. */
async function until(read, what, timeout = patience(12000)) {
  const deadline = Date.now() + timeout;
  let last;
  for (;;) {
    try {
      last = await read();
      if (last) return last;
    } catch (error) {
      last = error.message;
    }
    if (Date.now() > deadline)
      throw new Error(
        `Never saw ${what}${last === undefined ? '' : ` (last: ${JSON.stringify(last)})`}`,
      );
    await new Promise((resolve) => setTimeout(resolve, 80));
  }
}

/* ---- the world: one backend serving each page, over a scratch copy of the tree ---- */
function resolvePython() {
  const name =
    process.env.CARGENTO_TEST_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
  return execFileSync(name, ['-I', '-c', 'import sys; print(sys.executable)'], {
    encoding: 'utf8',
    timeout: 5000,
  }).trim();
}

async function waitForHealth(origin, child) {
  const deadline = Date.now() + 25000;
  for (;;) {
    if (child.exitCode !== null)
      throw new Error('Legacy capacity backend exited: ' + (child.diagnostic || ''));
    try {
      const health = await (
        await fetch(origin + '/api/health', { signal: AbortSignal.timeout(1000) })
      ).json();
      if (health.ok === true && health.pid === child.pid) return;
      throw new Error('Port belongs to another process.');
    } catch (error) {
      if (Date.now() > deadline)
        throw new Error(
          'Legacy capacity backend never became ready: ' + (child.diagnostic || error.message),
          { cause: error },
        );
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
  }
}

async function startWorld({ mutation = process.env.CARGENTO_MUTATION || '' } = {}) {
  const copy = await mkdtemp(join(tmpdir(), 'cargento-capacity-browser-'));
  let dev = null;
  let child = null;
  let legacyScratch = null;
  const world = { copy, mutation, close };
  async function close() {
    if (child && child.exitCode === null) {
      child.kill('SIGTERM');
      await new Promise((resolve) => {
        const timer = setTimeout(() => {
          child.kill('SIGKILL');
          resolve();
        }, 3000);
        child.once('close', () => {
          clearTimeout(timer);
          resolve();
        });
      });
    }
    if (dev) await dev.close();
    if (legacyScratch) await rm(legacyScratch, { recursive: true, force: true });
    await rm(copy, { recursive: true, force: true });
  }
  try {
    await cp(join(REPOSITORY, 'frontend'), join(copy, 'frontend'), {
      recursive: true,
      filter: (path) =>
        !path.includes('/fixtures') &&
        !path.includes('/test-results') &&
        !path.includes('__pycache__'),
    });
    await cp(join(REPOSITORY, 'cargento'), join(copy, 'cargento'), {
      recursive: true,
      filter: (path) =>
        !path.includes('/tests/') && !path.endsWith('/tests') && !path.includes('__pycache__'),
    });
    await symlink(
      join(REPOSITORY, 'node_modules'),
      join(copy, 'node_modules'),
      process.platform === 'win32' ? 'junction' : 'dir',
    );
    await writeFile(join(copy, 'frontend/src/main.tsx'), "import '../e2e/capacity-harness';\n");
    assert.ok(!mutation || MUTATIONS[mutation], `unknown mutation ${mutation}`);
    for (const [file, needle, replacement] of MUTATIONS[mutation] ?? []) {
      const path = join(copy, 'frontend', file);
      const text = await readFile(path, 'utf8');
      assert.ok(text.includes(needle), `mutation ${mutation}: needle not found in ${file}`);
      await writeFile(path, text.replace(needle, replacement));
    }

    const helper = join(copy, 'frontend/test/capacity_backend.py');
    /* A sibling run can bind a port between the check that it is free and the bind itself; startup then fails
       loudly rather than adopting someone else's listener. Try again on other ports, a few times. */
    const refused = [];
    let ports;
    for (let attempt = 0; ; attempt += 1) {
      ports = await freePorts(3, refused);
      try {
        dev = await startDevelopment({
          root: copy,
          port: ports[0],
          vitePort: ports[1],
          backendHelper: helper,
        });
        break;
      } catch (error) {
        refused.push(...ports);
        if (
          attempt >= 3 ||
          !/in use|EADDRINUSE|belongs to another|backend exited|readiness/i.test(
            String(error.message),
          )
        )
          throw error;
      }
    }
    world.react = {
      name: 'react',
      origin: dev.origin,
      viteOrigin: dev.viteOrigin,
      state: join(dev.scratch, 'state'),
    };

    legacyScratch = await mkdtemp(join(tmpdir(), 'cargento-capacity-legacy-'));
    await mkdir(join(legacyScratch, 'no-executables'));
    child = spawn(
      resolvePython(),
      [
        helper,
        '--frontend',
        'legacy',
        '--host',
        '127.0.0.1',
        '--port',
        String(ports[2]),
        '--no-observer-model',
        '--no-usage',
        '--no-git',
        '--no-reach',
      ],
      {
        cwd: copy,
        env: isolatedEnvironment(legacyScratch, process.env),
        stdio: ['ignore', 'pipe', 'pipe'],
      },
    );
    child.stderr.on('data', (chunk) => {
      child.diagnostic = ((child.diagnostic || '') + chunk).slice(-3000);
    });
    child.stdout.resume();
    const legacyOrigin = `http://127.0.0.1:${ports[2]}`;
    await waitForHealth(legacyOrigin, child);
    world.legacy = { name: 'legacy', origin: legacyOrigin, state: join(legacyScratch, 'state') };
    return world;
  } catch (error) {
    await close();
    throw error;
  }
}

/* What a backend counted since it started, and the board a test asks it to publish next. */
async function eventsOf(side, kind) {
  try {
    const text = await readFile(join(side.state, 'capacity-fixture/events.ndjson'), 'utf8');
    return text
      .split('\n')
      .filter(Boolean)
      .map((line) => JSON.parse(line))
      .filter((event) => event.event === kind);
  } catch {
    return [];
  }
}
/* The board is published at most every 2.5 s and announced to a page only when it changes, so a steer that changes
   the windows waits that long and reads the board once itself: waiting for the page's own fallback poll took
   several seconds a step. A steer that changes only what the project context says is read on the next request. */
async function steer(side, control, { board = true } = {}) {
  await mkdir(join(side.state, 'capacity-fixture'), { recursive: true });
  await writeFile(join(side.state, 'capacity-fixture/control.json'), JSON.stringify(control));
  if (!board) return;
  await new Promise((resolve) => setTimeout(resolve, 2700));
  await fetch(`${side.origin}/api/data`, { signal: AbortSignal.timeout(5000) }).then((r) =>
    r.arrayBuffer(),
  );
}

/* A script in place of the browser's Notification: it records what a page asks of it and shows nothing, so the
   test can state that no surface here asked for permission or made one. */
const SCRIPTED_NOTIFICATION = `
  globalThis.__notified = [];
  globalThis.Notification = class {
    static permission = 'default';
    static requestPermission() { globalThis.__notified.push('requestPermission'); return Promise.resolve('default'); }
    constructor(title) { globalThis.__notified.push('construct:' + title); }
    close() {}
  };
`;

const E = encodeURIComponent;
const SESSIONS = '#n=sessions';
const CONSOLE = `#n=project:${E('alpha/app')}:${E('claude:live-work')}:console`;
const ELSEWHERE = '#n=projects';

async function open(browser, side, extra = []) {
  const opened = await openPage(browser, [side.origin, side.viteOrigin ?? side.origin, ...extra], {
    viewport: { width: 1100, height: 900 },
    reducedMotion: 'reduce',
  });
  await opened.context.addInitScript(SCRIPTED_NOTIFICATION);
  // `reset()` clears the shared log between steps; this one never is, so the closing checks see every request.
  const everything = [];
  opened.page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.protocol !== 'data:')
      everything.push({ method: request.method(), path: url.pathname + url.search });
  });
  return { ...opened, side, everything };
}

async function go(view, fragment) {
  const { page, side } = view;
  await page.goto('about:blank');
  await page.goto(`${side.origin}/${fragment}`);
  if (side.name === 'legacy')
    await page.waitForFunction('typeof nextData !== "undefined" && nextData !== null');
  try {
    await page.waitForSelector('nav[aria-label="Primary"]', { timeout: patience(15000) });
  } catch (error) {
    const body = await page.evaluate(() => globalThis.document.body.innerText.slice(0, 300));
    throw new Error(
      `${side.name} never drew its navigation (${page.url()}): ${body} ${JSON.stringify([...view.log.pageErrors, ...view.log.consoleErrors]).slice(0, 600)}`,
      {
        cause: error,
      },
    );
  }
}

/* The route change a link makes, which is a hash change for both pages and a real unmount for the React one. */
async function navigate(view, fragment) {
  await view.page.evaluate((hash) => {
    globalThis.location.hash = hash;
  }, fragment);
}

/* ---- what a reader can observe, read the same way from either page ---- */
const stripOf = (page) =>
  page.evaluate(() => {
    const text = (node) => (node ? node.textContent.replace(/\s+/g, ' ').trim() : null);
    const section = globalThis.document.querySelector('[data-next-capacity]');
    if (!section) return null;
    return {
      rows: [...section.querySelectorAll('[data-next-capacity-row]')].map((row) => ({
        key: row.dataset.nextCapacityRow,
        pressed: row.querySelector('button')?.getAttribute('aria-pressed') === 'true',
        text: text(row),
        tick: Boolean(row.querySelector('.next-capacity-tick')),
        noclock: Boolean(row.querySelector('.next-capacity-noclock')),
      })),
      more: text(section.querySelector('.next-capacity-more')),
      prospect: text(section.querySelector('.next-capacity-prospect')),
      models: [...section.querySelectorAll('[data-next-capacity-models]')].map(text),
    };
  });
const consentOf = (page) =>
  page.evaluate(() => {
    const text = (node) => (node ? node.textContent.replace(/\s+/g, ' ').trim() : null);
    const { document } = globalThis;
    return {
      disclosure: text(document.querySelector('[data-next-usage-consent]')),
      switch: text(document.querySelector('.next-usage-switch')),
    };
  });
const dataRequests = (view) => view.log.requests.filter((r) => r.path.startsWith('/api/data'));
const usageRequests = (view) => dataRequests(view).filter((r) => /[?&]usage=/.test(r.path));
const modelRequests = (view) =>
  view.log.requests.filter(
    (r) => r.path.startsWith('/api/project-context') && /observer_model=1/.test(r.path),
  );
const pressUsage = (view, answer) =>
  view.page.locator(`[data-next-usage-answer="${answer}"]`).first().click();
const pressedKey = async (view) => (await stripOf(view.page))?.rows.find((r) => r.pressed)?.key;
const pressWindow = (view, key) =>
  view.page.locator(`[data-next-capacity-row="${key}"] button`).first().click();
const observerText = (page) =>
  page.evaluate(() => {
    const section = globalThis.document.querySelector('[data-next-observer-consent]');
    if (section) return section.textContent.replace(/\s+/g, ' ').trim();
    const empty = [...globalThis.document.querySelectorAll('.next-cockpit-empty')]
      .map((node) => node.textContent.replace(/\s+/g, ' ').trim())
      .filter((text) => /^(Observer|Select one exact session to request)/.test(text));
    return empty.join(' | ') || null;
  });
const observerButtons = (page) =>
  page.evaluate(() =>
    [...globalThis.document.querySelectorAll('[data-next-observer-action]')].map((button) => ({
      action: button.dataset.nextObserverAction,
      label: button.textContent.trim(),
      disabled: button.disabled,
    })),
  );

let world;
let browser;
try {
  world = await startWorld();
  browser = await chromium.launch();
  const SIDES = [world.legacy, world.react];

  /* One tracked page per side for the strip and the usage consent, and one fresh profile per consent path, so
     an answer given in one step cannot stand in for the question in the next. */
  const strip = {};
  for (const side of SIDES) {
    strip[side.name] = await open(browser, side);
    await go(strip[side.name], SESSIONS);
  }
  const both = async (run) => {
    for (const side of SIDES) await run(strip[side.name], side);
  };

  await step(
    'the unanswered disclosure is drawn and no request carries a usage parameter',
    async () => {
      await both(async (view) => {
        await until(async () => (await consentOf(view.page)).disclosure, 'the disclosure');
        await until(async () => (await stripOf(view.page))?.rows.length, 'the strip');
      });
      await pause(2500);
      for (const side of SIDES) {
        const view = strip[side.name];
        assert.ok(dataRequests(view).length > 0, `${side.name}: the page read the board`);
        assert.deepEqual(
          usageRequests(view),
          [],
          `${side.name}: a usage parameter without an answer`,
        );
        assert.equal(
          (await eventsOf(side, 'usage_fetch')).length,
          0,
          `${side.name}: the server saw one`,
        );
      }
      const [legacy, react] = await Promise.all(SIDES.map((s) => consentOf(strip[s.name].page)));
      assert.equal(react.disclosure, legacy.disclosure, 'the two pages ask the same question');
      assert.match(react.disclosure, /reading the credential that harness already stored/);
      assert.equal(react.switch, null);
    },
  );

  await step('a route change, a reload and a reconnect without an answer send none', async () => {
    for (const side of SIDES) {
      const view = strip[side.name];
      await navigate(view, ELSEWHERE);
      await pause(300);
      await navigate(view, SESSIONS);
      await until(async () => (await stripOf(view.page))?.rows.length, 'the strip after a return');
      await view.page.reload();
      await until(
        async () => (await consentOf(view.page)).disclosure,
        'the disclosure after a reload',
      );
      // A reconnect: the page loses the network, then regains it, and reads the board again.
      const before = dataRequests(view).length;
      await view.context.setOffline(true);
      await pause(1200);
      await view.context.setOffline(false);
      view.page
        .evaluate(() => globalThis.dispatchEvent(new Event('online')))
        .catch(() => undefined);
      await until(
        () => dataRequests(view).length > before,
        `${side.name} reading the board again after reconnecting`,
        patience(20000),
      );
      assert.deepEqual(
        usageRequests(view),
        [],
        `${side.name}: a usage parameter without an answer`,
      );
      assert.equal((await eventsOf(side, 'usage_fetch')).length, 0);
    }
  });

  await step(
    'No thanks sends no parameter, says the windows will lapse, and is kept across a reload',
    async () => {
      for (const side of SIDES) {
        const view = strip[side.name];
        view.reset();
        await pressUsage(view, 'declined');
        await until(async () => (await consentOf(view.page)).switch, `${side.name} the switch`);
        // The answer asks for the board again, and that read says nothing about usage.
        await until(
          () => dataRequests(view).length > 0,
          `${side.name} reading the board after the answer`,
        );
        const state = await consentOf(view.page);
        assert.equal(state.disclosure, null, `${side.name}: the question is gone once answered`);
        assert.match(state.switch, /Vendor quota fetch: off/);
        assert.match(state.switch, /Windows above are the last cached read and will lapse\./);
        await pause(2000);
        assert.deepEqual(usageRequests(view), [], `${side.name}: declined sent a usage parameter`);
        await view.page.reload();
        await until(async () => (await consentOf(view.page)).switch, 'the switch after a reload');
        assert.equal((await consentOf(view.page)).disclosure, null);
        assert.deepEqual(usageRequests(view), []);
        assert.equal((await eventsOf(side, 'usage_fetch')).length, 0);
      }
    },
  );

  await step(
    'the answer is per origin: another origin in the same profile is asked again',
    async () => {
      const wide = await open(browser, world.react, [world.legacy.origin]);
      try {
        await go(wide, SESSIONS);
        await until(async () => (await consentOf(wide.page)).disclosure, 'the question');
        await pressUsage(wide, 'declined');
        await until(async () => (await consentOf(wide.page)).switch, 'the answer on this origin');
        // Same profile, different origin: nothing was answered there, so the question is asked.
        await wide.page.goto(`${world.legacy.origin}/${SESSIONS}`);
        await wide.page.waitForFunction('typeof nextData !== "undefined" && nextData !== null');
        await until(
          async () => (await consentOf(wide.page)).disclosure,
          'the question on the other origin',
        );
        assert.equal((await consentOf(wide.page)).switch, null);
      } finally {
        await wide.close();
      }
    },
  );

  await step(
    'Turn on carries usage=1 on the very next request, the server sees it, and Turn off stops it',
    async () => {
      for (const side of SIDES) {
        const view = strip[side.name];
        view.reset();
        const before = (await eventsOf(side, 'usage_fetch')).length;
        await pressUsage(view, 'granted');
        await until(
          () => usageRequests(view).length > 0,
          `${side.name} a request with the parameter`,
        );
        assert.match(usageRequests(view)[0].path, /usage=1/);
        await until(
          async () => (await eventsOf(side, 'usage_fetch')).length > before,
          `${side.name} the server counting it`,
        );
        assert.match((await consentOf(view.page)).switch, /Vendor quota fetch: on/);
        assert.doesNotMatch((await consentOf(view.page)).switch, /lapse/);
        // An answer given on an earlier visit rides the very first read of a fresh page.
        view.reset();
        await view.page.reload();
        await until(() => dataRequests(view).length > 0, `${side.name} the first read`);
        assert.match(
          dataRequests(view)[0].path,
          /usage=1/,
          `${side.name}: an answered yes rides the first read`,
        );
        // Off again: the read the press asks for carries none, and the server's count stops.
        view.reset();
        await until(async () => (await consentOf(view.page)).switch, 'the switch');
        await pressUsage(view, 'declined');
        await until(
          () => dataRequests(view).length > 0,
          `${side.name} the read after turning it off`,
        );
        assert.deepEqual(usageRequests(view), [], `${side.name}: still sending the parameter`);
        const frozen = (await eventsOf(side, 'usage_fetch')).length;
        await pause(2500);
        assert.equal(
          (await eventsOf(side, 'usage_fetch')).length,
          frozen,
          `${side.name}: still fetching`,
        );
        assert.deepEqual(usageRequests(view), [], `${side.name}: still sending the parameter`);
      }
    },
  );

  await step(
    'a fresh profile answering Read my quota is asked once, and nothing before the press',
    async () => {
      const fresh = await open(browser, world.react);
      try {
        await go(fresh, SESSIONS);
        await until(async () => (await consentOf(fresh.page)).disclosure, 'the question');
        await pause(1500);
        assert.deepEqual(usageRequests(fresh), [], 'nothing before the press');
        const seen = (await eventsOf(world.react, 'usage_fetch')).length;
        await pressUsage(fresh, 'granted');
        await until(() => usageRequests(fresh).length > 0, 'the request after the press');
        assert.match((await consentOf(fresh.page)).switch, /Vendor quota fetch: on/);
        await until(
          async () => (await eventsOf(world.react, 'usage_fetch')).length > seen,
          'the server counting the press',
        );
        // The very press moved focus to the switch, so a keyboard reader is not left on nothing.
        const focused = await fresh.page.evaluate(
          () => globalThis.document.activeElement?.closest('.next-usage-switch') !== null,
        );
        assert.ok(focused, 'focus lands on the switch');
      } finally {
        await fresh.close();
      }
    },
  );

  /* The selected window. The board is steered to publish six windows, the third of which the reader chooses; a
     later board ranks it fourth, and it must stay on screen and selected. */
  await step(
    'the selected window keeps its identity across a redraw that reorders it and a route change',
    async () => {
      for (const side of SIDES) {
        const view = strip[side.name];
        await steer(side, { windows: 'full' });
        await go(view, SESSIONS);
        const first = await until(
          async () => {
            const state = await stripOf(view.page);
            return state &&
              state.rows.length === 3 &&
              state.rows.some((r) => r.key === 'codex:fiveH')
              ? state
              : null;
          },
          `${side.name} the full board`,
          patience(15000),
        );
        assert.equal(first.rows[0].key, 'cursor:fiveH');
        assert.match(first.more, /^3 more windows/);
        assert.equal(first.rows.filter((r) => r.pressed).length, 1);
        assert.equal(
          await pressedKey(view),
          'cursor:fiveH',
          'the first window is selected until the reader chooses',
        );
        await pressWindow(view, 'codex:fiveH');
        assert.equal(await pressedKey(view), 'codex:fiveH');
        await steer(side, { windows: 'reordered' });
        const after = await until(
          async () => {
            const state = await stripOf(view.page);
            const claude = state?.rows.find((r) => r.key === 'claude:fiveH');
            return claude && /95%/.test(claude.text) ? state : null;
          },
          `${side.name} the reordered board`,
          patience(20000),
        );
        // The chosen window is now ranked below the first three, and still drawn, selected.
        assert.equal(after.rows.length, 3);
        assert.ok(
          after.rows.some((r) => r.key === 'codex:fiveH'),
          `${side.name}: the chosen window left the strip`,
        );
        assert.equal(
          await pressedKey(view),
          'codex:fiveH',
          `${side.name}: the selection moved with the rank`,
        );
        assert.match(after.prospect, /Codex · 5-hour/);
        await navigate(view, ELSEWHERE);
        await pause(300);
        await navigate(view, SESSIONS);
        await until(
          async () => (await stripOf(view.page))?.rows.length,
          'the strip after a return',
        );
        assert.equal(
          await pressedKey(view),
          'codex:fiveH',
          `${side.name}: lost across a route change`,
        );
        // A page is a tab's life: a reload starts again at the first window.
        await view.page.reload();
        await until(
          async () => (await stripOf(view.page))?.rows.length,
          'the strip after a reload',
        );
        assert.notEqual(await pressedKey(view), 'codex:fiveH');
      }
    },
  );

  await step(
    'the selection falls back only when its window is gone, holds the fallback, and clears with the last window',
    async () => {
      for (const side of SIDES) {
        const view = strip[side.name];
        await steer(side, { windows: 'full' });
        await go(view, SESSIONS);
        await until(
          async () => (await stripOf(view.page))?.rows.some((r) => r.key === 'codex:fiveH'),
          'the board',
        );
        await pressWindow(view, 'codex:fiveH');
        await steer(side, { windows: 'fewer' });
        await until(
          async () => {
            const state = await stripOf(view.page);
            return state && state.rows.every((r) => r.key.startsWith('claude:')) ? state : null;
          },
          `${side.name} the smaller board`,
          patience(20000),
        );
        const fell = await pressedKey(view);
        assert.ok(fell?.startsWith('claude:'), `${side.name}: no fallback to an existing window`);
        await steer(side, { windows: 'full' });
        await until(
          async () => (await stripOf(view.page))?.rows.some((r) => r.key === 'codex:fiveH'),
          'the board back',
        );
        assert.equal(await pressedKey(view), fell, `${side.name}: the fallback was not held`);
        await steer(side, { windows: 'none' });
        await until(
          async () => (await stripOf(view.page)) === null,
          `${side.name} no strip`,
          patience(20000),
        );
        assert.equal(await view.page.locator('[data-next-capacity]').count(), 0);
        await steer(side, { windows: 'full' });
        await until(async () => (await stripOf(view.page))?.rows.length, 'the strip returning');
        assert.equal(
          await pressedKey(view),
          'cursor:fiveH',
          `${side.name}: not cleared when none remained`,
        );
      }
    },
  );

  await step('the strip draws the same facts on both pages and invents no tick', async () => {
    const facts = (state) => ({
      keys: state.rows.map((r) => r.key),
      ticks: state.rows.map((r) => r.tick),
      noclock: state.rows.map((r) => r.noclock),
      more: state.more,
      models: state.models,
    });
    const read = (side, count) =>
      until(
        async () => {
          const state = await stripOf(strip[side.name].page);
          return state && state.rows.length === count ? state : null;
        },
        `${side.name} ${count} windows`,
        patience(20000),
      );
    for (const [windows, count] of [
      ['full', 3],
      ['fewer', 3],
    ]) {
      for (const side of SIDES) {
        await steer(side, { windows });
        await go(strip[side.name], SESSIONS);
      }
      const old = await read(world.legacy, count);
      const mine = await read(world.react, count);
      assert.deepEqual(
        facts(mine),
        facts(old),
        `${windows}: the same windows, ticks and sub-limits`,
      );
      if (windows === 'full') {
        // A spent budget says so, and the window with no clock is ranked last, behind the fold, untimed.
        assert.match(mine.rows[0].text, /already spent/);
        assert.match(mine.more, /^3 more windows, 1 of them not timed$/);
        continue;
      }
      // The window that publishes no clock draws a hatched gap and no tick: nothing is invented to fill it.
      const month = mine.rows.find((r) => r.key === 'claude:month');
      assert.ok(
        month?.noclock && !month.tick,
        'react: a window with no clock drew a bar or a tick',
      );
      assert.match(month.text, /Window length not published/);
      assert.match(month.text, /Pace not measured/);
      assert.match(month.text, /not projected/);
      await pressWindow(strip.react, 'claude:week');
      await pressWindow(strip.legacy, 'claude:week');
      const week = await stripOf(strip.react.page);
      assert.ok(week.rows.find((r) => r.key === 'claude:week')?.pressed);
      // The sub-limits hang under the weekly row only, and keep a measured zero.
      assert.deepEqual(
        week.models.map((m) => /Opus 71%.*Sonnet 0%/.test(m)),
        [true],
      );
      const theirs = await stripOf(strip.legacy.page);
      legacySoft('prospect', () => assert.equal(week.prospect, theirs.prospect));
      legacySoft('rows', () =>
        assert.deepEqual(
          week.rows.map((r) => r.text),
          theirs.rows.map((r) => r.text),
        ),
      );
      // The weekly row's recent pace is a measured zero, which is evidence and is not "not measured".
      assert.match(
        week.prospect,
        /Recent pace measured at zero: nothing spent across .+ and \d+ readings/,
      );
    }
  });

  /* The observer-model controls, in the Console tab of the exact session, with a fresh profile per path. */
  const observer = async (side, body) => {
    const view = await open(browser, side);
    try {
      await go(view, CONSOLE);
      await body(view);
      assert.deepEqual(
        view.everything.filter((r) => r.method !== 'GET'),
        [],
        `${side.name}: a request that was not a GET`,
      );
      assert.deepEqual(
        view.everything.filter((r) => r.path.startsWith('/api/focus')),
        [],
        `${side.name}: a focus request`,
      );
      assert.deepEqual(await view.page.evaluate(() => globalThis.__notified), []);
    } finally {
      await view.close();
    }
  };
  await step(
    'an offer nothing read, one that is off, and one withheld are three different sentences',
    async () => {
      for (const side of SIDES) {
        const said = {};
        for (const [mode, expected] of [
          ['absent', /Observer model availability has not been read\./],
          ['disabled', /Observer model is disabled for this run\./],
          ['no-disclosure', /Observer disclosure is unavailable; model requests are withheld\./],
        ]) {
          await steer(side, { windows: 'full', observer: mode }, { board: false });
          await observer(side, async (view) => {
            await until(
              async () => expected.test((await observerText(view.page)) ?? ''),
              `${side.name} ${mode}`,
            );
            said[mode] = await observerText(view.page);
            assert.deepEqual(
              await observerButtons(view.page),
              [],
              `${side.name} ${mode}: controls offered`,
            );
            assert.equal(modelRequests(view).length, 0);
          });
        }
        assert.equal(new Set(Object.values(said)).size, 3);
        assert.equal((await eventsOf(side, 'model_call')).length, 0);
      }
    },
  );

  await step(
    'allowing sends nothing; one press of Summarize sends one request for the exact session',
    async () => {
      for (const side of SIDES) {
        await steer(side, { windows: 'full', observer: 'enabled' }, { board: false });
        const before = (await eventsOf(side, 'model_call')).length;
        await observer(side, async (view) => {
          const first = await until(async () => {
            const buttons = await observerButtons(view.page);
            return buttons.some((b) => b.action === 'allow') ? buttons : null;
          }, `${side.name} the question`);
          assert.deepEqual(
            first.map((b) => b.label),
            ['Allow model summaries', 'No thanks'],
          );
          const asked = await observerText(view.page);
          assert.match(asked, /Quota consent does not authorize this request\./);
          assert.match(asked, /Allowing summaries does not send a request\./);
          // Mounting, StrictMode, a poll and a route change asked nothing.
          await pause(2000);
          await navigate(view, ELSEWHERE);
          await pause(300);
          await navigate(view, CONSOLE);
          await until(
            async () => (await observerButtons(view.page)).length,
            'the controls after a return',
          );
          assert.equal(modelRequests(view).length, 0, `${side.name}: a request before a press`);
          await view.page.locator('[data-next-observer-action="allow"]').click();
          const allowed = await until(async () => {
            const buttons = await observerButtons(view.page);
            return buttons.some((b) => b.action === 'request') ? buttons : null;
          }, `${side.name} the allowed state`);
          assert.deepEqual(
            allowed.map((b) => b.label),
            ['Summarize this session', 'Turn off model summaries'],
          );
          await pause(1500);
          assert.equal(modelRequests(view).length, 0, `${side.name}: allowing sent a request`);
          assert.equal(
            (await eventsOf(side, 'model_call')).length,
            before,
            `${side.name}: the server saw one`,
          );
          // Consent is kept, and a reload asks nothing either.
          await view.page.reload();
          await until(
            async () => (await observerButtons(view.page)).some((b) => b.action === 'request'),
            'the allowed state after a reload',
          );
          await pause(1500);
          assert.equal(modelRequests(view).length, 0, `${side.name}: a reload sent a request`);
          // The press: a double click is one request for exactly this session.
          await view.page.locator('[data-next-observer-action="request"]').dblclick();
          // The answer comes from the fixture's own refresh on a shared runner, so the wait is generous, and the
          // page's text is what a failure reports: "false" said nothing about what the page drew instead.
          await until(
            async () => {
              const drawn = (await observerText(view.page)) ?? '';
              if (/Observed goal: Retry the queue until it drains/.test(drawn)) return drawn;
              throw new Error(`the page drew: ${drawn.slice(0, 400)}`);
            },
            `${side.name} the goal`,
            patience(30000),
          );
          const text = await observerText(view.page);
          assert.match(text, /The refresh returned\./);
          assert.match(text, /Model status: fixture/);
          assert.equal(modelRequests(view).length, 1, `${side.name}: not one request`);
          assert.match(modelRequests(view)[0].path, /session=claude%3Alive-work/);
          const calls = (await eventsOf(side, 'model_call')).slice(before);
          assert.deepEqual(
            calls.map((c) => [c.harness, c.sid]),
            [['claude', 'live-work']],
          );
          // Turning it off offers only the way back; what the last refresh returned stays as it was said.
          await view.page.locator('[data-next-observer-action="decline"]').click();
          await until(async () => {
            const actions = (await observerButtons(view.page)).map((b) => b.action);
            return actions.length === 1 && actions[0] === 'allow';
          }, `${side.name} the way back`);
          assert.equal((await eventsOf(side, 'model_call')).length, before + 1);
        });
      }
    },
  );

  await step('quota consent does not authorize the observer model', async () => {
    for (const side of SIDES) {
      await steer(side, { windows: 'full', observer: 'enabled' }, { board: false });
      const view = await open(browser, side);
      try {
        await view.page.goto(`${side.origin}/${SESSIONS}`);
        await view.page.evaluate(() =>
          globalThis.localStorage.setItem('cargento.next.usage.consent', 'granted'),
        );
        const before = (await eventsOf(side, 'model_call')).length;
        await go(view, CONSOLE);
        await until(
          async () => (await observerButtons(view.page)).some((b) => b.action === 'allow'),
          `${side.name} the question`,
        );
        assert.deepEqual(
          (await observerButtons(view.page)).map((b) => b.action),
          ['allow', 'decline'],
        );
        await pause(1500);
        assert.equal(modelRequests(view).length, 0);
        assert.equal((await eventsOf(side, 'model_call')).length, before);
        // Declining says so in words, and offers only the way back.
        await view.page.locator('[data-next-observer-action="decline"]').click();
        await until(
          async () =>
            /Model summaries are off in this browser\./.test((await observerText(view.page)) ?? ''),
          `${side.name} the declined sentence`,
        );
        assert.deepEqual(
          (await observerButtons(view.page)).map((b) => b.action),
          ['allow'],
        );
        assert.equal(modelRequests(view).length, 0);
      } finally {
        await view.close();
      }
    }
  });

  await step('nothing posted, raised a terminal or notified on either page', async () => {
    for (const side of SIDES) {
      const view = strip[side.name];
      assert.deepEqual(
        view.everything.filter((r) => r.method !== 'GET'),
        [],
        `${side.name}: a request that was not a GET`,
      );
      assert.deepEqual(
        view.everything.filter((r) => r.path.startsWith('/api/focus')),
        [],
        `${side.name}: a focus request`,
      );
      assert.deepEqual(
        await view.page.evaluate(() => globalThis.__notified),
        [],
        `${side.name}: a notification call`,
      );
    }
  });

  await step('the layout holds at 320 and 375 px and every control is a touch target', async () => {
    const report = {};
    for (const side of SIDES) await steer(side, { windows: 'full', observer: 'enabled' });
    for (const width of [375, 320]) {
      for (const side of SIDES) {
        const view = strip[side.name];
        await view.page.setViewportSize({ width, height: 900 });
        await go(view, SESSIONS);
        await until(async () => (await stripOf(view.page))?.rows.length, 'the strip');
        const measured = await view.page.evaluate(() => {
          const { document } = globalThis;
          const root = document.scrollingElement;
          const boxes = (selector) =>
            [...document.querySelectorAll(selector)].map((node) => {
              const box = node.getBoundingClientRect();
              return { width: box.width, height: box.height, right: box.right };
            });
          return {
            overflow: root.scrollWidth - root.clientWidth,
            client: root.clientWidth,
            rows: boxes('.next-capacity-row'),
            actions: boxes('.next-usage-consent-actions button, .next-usage-switch button'),
          };
        });
        if (side.name === 'react') {
          assert.ok(
            measured.overflow <= 0,
            `react: horizontal page scroll at ${width}px: ${measured.overflow}`,
          );
          for (const row of measured.rows)
            assert.ok(
              row.right <= measured.client + 1,
              `react: a window row leaves the page at ${width}px`,
            );
          const small = measured.rows.filter((r) => r.height < 44).length;
          assert.equal(small, 0, `react: a window row under 44 px at ${width}px`);
          for (const action of measured.actions)
            assert.ok(
              action.height >= 44 && action.width >= 44,
              `react: a consent control under 44 px at ${width}px`,
            );
        } else {
          legacySoft(`overflow ${width}`, () =>
            assert.ok(measured.overflow <= 0, `legacy overflow ${measured.overflow}`),
          );
        }
        report[`${side.name}@${width}`] = { overflow: measured.overflow };
        if (shots) {
          await mkdir(SHOTS, { recursive: true });
          await view.page.screenshot({
            path: join(SHOTS, `drc-4827-capacity-${side.name}-${width}px.png`),
            fullPage: true,
          });
        }
      }
    }
    for (const side of SIDES)
      await strip[side.name].page.setViewportSize({ width: 1100, height: 900 });
    if (shots) {
      const view = strip.react;
      await go(view, SESSIONS);
      await until(async () => (await stripOf(view.page))?.rows.length, 'the strip');
      await view.page.screenshot({
        path: join(SHOTS, 'drc-4827-capacity-react-1100px.png'),
        fullPage: true,
      });
      await go(strip.legacy, SESSIONS);
      await until(async () => (await stripOf(strip.legacy.page))?.rows.length, 'the legacy strip');
      await strip.legacy.page.screenshot({
        path: join(SHOTS, 'drc-4827-capacity-legacy-1100px.png'),
        fullPage: true,
      });
      await steer(world.react, { windows: 'full', observer: 'enabled' });
      const consoleView = await open(browser, world.react);
      try {
        await go(consoleView, CONSOLE);
        await until(
          async () => (await observerButtons(consoleView.page)).length,
          'the observer controls',
        );
        await consoleView.page.screenshot({
          path: join(SHOTS, 'drc-4827-observer-react-1100px.png'),
          fullPage: true,
        });
      } finally {
        await consoleView.close();
      }
    }
    return report;
  });

  await step('no external request, page error or console error in either page', async () => {
    for (const side of SIDES) {
      const view = strip[side.name];
      assert.deepEqual(view.log.externalRequests, [], `${side.name}: an external request`);
      assert.deepEqual(view.log.pageErrors, [], `${side.name}: a page error`);
      assert.deepEqual(
        view.log.consoleErrors.filter(
          (text) =>
            !/net::ERR_FAILED|ERR_INTERNET_DISCONNECTED|Failed to load resource: the server responded with a status of (404|500)/.test(
              text,
            ),
        ),
        [],
        `${side.name}: a console error`,
      );
    }
  });

  console.log(
    JSON.stringify(
      {
        capacityBrowser: {
          mutation: world.mutation || null,
          strictMode: true,
          realBackend: true,
          failures: failures.length,
          legacyNotes,
          steps: results,
        },
      },
      null,
      2,
    ),
  );
  if (failures.length) {
    console.error(JSON.stringify({ mutation: world.mutation || null, failures }, null, 2));
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
  if (browser) await browser.close();
  if (world) await world.close();
}
