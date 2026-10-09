/* global document, getComputedStyle, MutationObserver, requestAnimationFrame -- used inside page.evaluate, which runs in the browser */
/*
 * Real-Chromium proof that the shared controls keep what a persistent React node alone cannot:
 * unsaved text, caret, undo history, IME composition, a native <select>, disclosure continuity and
 * motion, focus and scroll, across live data from the REAL backend (GET /api/data and the SSE stream).
 *
 * The dashboard is served by the real Python launcher over the shell's synthetic board with the real
 * focus capability and an inert native raise (`controls-backend.py`), and the entry is swapped to the
 * component gallery inside a scratch copy of the tree, so no tracked file changes. Nothing here reads
 * a real harness store, calls a model, touches the clipboard (the gallery records writes instead),
 * notifies, or raises a terminal. Every request leaving the board's own origins is refused.
 *
 * `CONTROLS_MUTATION` names one deliberate break in the scratch copy (see MUTATIONS); the run is then
 * expected to FAIL, which is how each behaviour is shown to be pinned rather than incidental.
 */
import assert from 'node:assert/strict';
import { cp, mkdtemp, readFile, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { chromium } from '@playwright/test';
import { startReactWorld } from './support/world.mjs';
import { freePorts, openPage, REPOSITORY } from './support/browser.mjs';

const SCREENSHOTS = join(REPOSITORY, 'docs/screenshots');
const mutation = process.env.CONTROLS_MUTATION || '';
const shots = process.env.CONTROLS_SCREENSHOTS === '1';
const MOD = process.platform === 'darwin' ? 'Meta' : 'Control';

/* One break each, applied to the scratch copy only. Each names the file, the exact text and its
   replacement; a missing needle fails the run loudly rather than silently testing nothing. */
const MUTATIONS = {
  'remount-draft': [
    [
      'src/controls/DraftField.tsx',
      'return <textarea ref={ref} {...rest} />;',
      'return <textarea ref={ref} key={String(Math.random())} {...rest} />;',
    ],
  ],
  'control-draft': [
    [
      'src/controls/DraftField.tsx',
      'return <textarea ref={ref} {...rest} />;',
      "return <textarea ref={ref} {...rest} value={String(rest.defaultValue ?? '')} onChange={() => undefined} />;",
    ],
  ],
  'no-cap': [['src/store/commit-gate.ts', 'if (count < max) {', 'if (true) {']],
  'no-select-hold': [
    ['src/controls/displayGate.ts', 'isHeld: options.isChoiceOpen,', 'isHeld: () => false,'],
  ],
  'no-motion-hold': [
    [
      'src/store/commit-gate.ts',
      'if (!options.reducedMotion()) until = options.clock.now() + MOTION_HOLD_MS;',
      'void MOTION_HOLD_MS;',
    ],
  ],
  'no-manual-bypass': [
    [
      'src/store/commit-gate.ts',
      'if (!flags.manual && options.isHeld()) {',
      'if (options.isHeld()) {',
    ],
  ],
  'remount-disclosure': [
    [
      'src/controls/Disclosure.tsx',
      'return <DisclosureNode key={props.disclosureKey} {...props} />;',
      'return <DisclosureNode key={props.disclosureKey + String(Math.random())} {...props} />;',
    ],
  ],
  'drop-disclosure-memory': [
    [
      'src/controls/Disclosure.tsx',
      'controls.disclosures.set(disclosureKey, event.currentTarget.open);',
      'void disclosureKey;',
    ],
  ],
  'scroll-offscreen-focus': [
    [
      'src/controls/focusLane.ts',
      'const preventScroll = offscreen(element);',
      'const preventScroll = false;',
    ],
  ],
  'drop-field-memory': [
    [
      'src/controls/fieldMemory.ts',
      'const state = states.get(key);\n      if (!state) return;',
      'return;',
    ],
  ],
  'drop-memo-memory': [
    ['src/storage/memo.ts', 'if (draft !== undefined) return boundMemo(draft);', ''],
  ],
  'raise-no-dedup': [
    ['src/controls/RaiseControl.tsx', 'if (controls.raiseBusy.get()) {', 'if (false as boolean) {'],
  ],
  'copy-on-mount': [
    [
      'src/controls/CopyControl.tsx',
      'const cueId = useId();',
      'const cueId = useId();\n  void controls.clipboard()?.writeText(value);',
    ],
  ],
};

const results = [];
const step = async (name, run) => {
  const started = Date.now();
  try {
    const detail = await run();
    results.push({ name, ok: true, ms: Date.now() - started, ...(detail ? { detail } : {}) });
  } catch (error) {
    results.push({
      name,
      ok: false,
      ms: Date.now() - started,
      error: error.message.split('\n')[0],
    });
    throw error;
  }
};

// Doubled on a hosted runner, which draws frames and delivers events later; only a pass gets slower, the assertions after a pause are unchanged.
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, process.env.CI ? ms * 2 : ms));

const copy = await mkdtemp(join(tmpdir(), 'cargento-controls-browser-'));
let dev, browser, shell, reduced;
try {
  await cp(join(REPOSITORY, 'frontend'), join(copy, 'frontend'), {
    recursive: true,
    filter: (path) => !path.includes('/fixtures') && !path.includes('/test-results'),
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
  await writeFile(
    join(copy, 'frontend/src/main.tsx'),
    "import { mountGallery } from './controls/gallery';\nconst root = document.getElementById('root');\nif (!root) throw new Error('missing root');\nmountGallery(root);\n",
  );
  for (const [file, needle, replacement] of MUTATIONS[mutation] ?? []) {
    const path = join(copy, 'frontend', file);
    const text = await readFile(path, 'utf8');
    assert.ok(text.includes(needle), `mutation ${mutation}: needle not found in ${file}`);
    await writeFile(path, text.replace(needle, replacement));
  }
  assert.ok(!mutation || MUTATIONS[mutation], `unknown mutation ${mutation}`);

  const [port, vitePort] = await freePorts(2);
  dev = await startReactWorld({
    root: copy,
    port,
    vitePort,
    backendHelper: join(copy, 'frontend/e2e/controls-backend.py'),
  });
  browser = await chromium.launch();
  const origins = [dev.origin, dev.viteOrigin];
  shell = await openPage(browser, origins, { viewport: { width: 1100, height: 900 } });
  const { page, log } = shell;

  const gallery = () => page.locator('#gallery');
  const readout = (name) => page.locator(`[data-readout="${name}"]`);
  const displayed = async () => Number(await readout('displayed-accepted').textContent());
  const accepted = () =>
    page.evaluate(() => globalThis.__gallery.runtime.store.getSnapshot().acceptedCount);
  const refresh = (manual = false) =>
    page.evaluate((flag) => globalThis.__gallery.runtime.refresh({ manual: flag }), manual);
  const settleRefresh = async (times, manual = false) => {
    for (let i = 0; i < times; i += 1) await refresh(manual);
  };
  /* A reload is a new document and runtime. The stream is blocked unless a scenario wants the real one,
     so arrivals are exactly the ones the test makes and its counts are exact. */
  async function load({ stream = false, strict = true } = {}) {
    await page.unroute('**/api/stream').catch(() => undefined);
    if (!stream) await page.route('**/api/stream', (route) => route.abort());
    await page.goto(`${dev.origin}/?strict=${strict ? 1 : 0}`);
    await gallery().waitFor();
    await page.waitForFunction(
      () => Number(document.querySelector('[data-readout="displayed-accepted"]')?.textContent) >= 1,
    );
    await page.evaluate(() => {
      const hooks = globalThis.__gallery;
      globalThis.__commits = 0;
      hooks.gate.subscribe(() => {
        globalThis.__commits += 1;
      });
    });
  }
  const commits = () => page.evaluate(() => globalThis.__commits);
  /* The backend only recollects when something reads it, and the stream announces the new revision to
     every connected tab. This reader stands outside the page, so a revision the page receives over its
     stream was announced by the server, not requested by the page. */
  const pump = () => {
    const timer = setInterval(() => {
      fetch(`${dev.origin}/api/data`)
        .then((response) => response.text())
        .catch(() => undefined);
    }, 3200);
    return () => clearInterval(timer);
  };
  /* `transitionrun` is not dispatched for ::details-content in Chromium 153, though the transition runs
     (measured: opacity and block-size interpolate over 200 ms with no event). So motion is read where it
     shows: a frame whose ::details-content opacity is strictly between 0 and 1 is a frame of easing. */
  const ACCORDION = 'details.ctl-disclosure:not(.ctl-disclosure--pop)';
  const startSampler = (target) =>
    target.evaluate(() => {
      globalThis.__motion = { easing: 0, frames: 0 };
      globalThis.__sampling = true;
      const tick = () => {
        if (!globalThis.__sampling) return;
        const details = document.querySelector('details.ctl-disclosure:not(.ctl-disclosure--pop)');
        if (details) {
          const opacity = Number(getComputedStyle(details, '::details-content').opacity);
          globalThis.__motion.frames += 1;
          if (opacity > 0.001 && opacity < 0.999) globalThis.__motion.easing += 1;
        }
        requestAnimationFrame(tick);
      };
      tick();
    });
  const readSampler = async (target) =>
    target.evaluate(() => {
      globalThis.__sampling = false;
      return globalThis.__motion;
    });
  /* Identity, not equality: the node itself is held on the window and compared after the updates. */
  const mark = (selector, name) =>
    page.locator(selector).evaluate((node, key) => {
      globalThis.__marks ??= {};
      globalThis.__marks[key] = node;
    }, name);
  const same = (selector, name) =>
    page.locator(selector).evaluate((node, key) => globalThis.__marks[key] === node, name);

  // ---------------------------------------------------------------------------------------------
  await step('mount and StrictMode send no request that is an action', async () => {
    await load();
    assert.deepEqual(
      log.nonGet,
      [],
      'a mount, StrictMode double effect or first paint issued a non-GET request',
    );
    assert.deepEqual(await page.evaluate(() => globalThis.__gallery.hooks.copied), []);
    assert.deepEqual(await page.evaluate(() => globalThis.__gallery.hooks.announced), []);
  });

  // ---------------------------------------------------------------------------------------------
  await step(
    'a native select keeps its node, focus and option list while the poll is deferred, and catches up once on change',
    async () => {
      await load();
      const select = page.locator('#stage-choice');
      await mark('#stage-choice', 'select');
      await select.focus();
      const optionsBefore = await select.locator('option').allTextContents();
      const shownBefore = await displayed();
      const commitsBefore = await commits();
      await settleRefresh(5);
      assert.equal(await displayed(), shownBefore, 'the board repainted under a focused select');
      assert.ok((await accepted()) >= shownBefore + 5, 'the store did not accept the polls');
      assert.deepEqual(
        await select.locator('option').allTextContents(),
        optionsBefore,
        'the option list changed under the reader',
      );
      assert.equal(await same('#stage-choice', 'select'), true);
      assert.equal(await page.evaluate(() => document.activeElement?.id), 'stage-choice');
      assert.equal(await commits(), commitsBefore, 'a deferred paint notified a subscriber');
      assert.equal(await page.evaluate(() => globalThis.__gallery.gate.deferredCount()), 5);
      // `selectOption` fires the input and change events a pick fires without the platform's popup, which
      // opens on ArrowDown on macOS and not elsewhere; the click step below drives the real popup.
      await select.selectOption({ index: 1 });
      await page.waitForFunction(
        () => document.querySelector('[data-readout="choice"]')?.textContent !== '',
      );
      const stored = await accepted();
      assert.equal(
        await displayed(),
        stored,
        'change did not catch the board up to the newest payload',
      );
      assert.equal((await commits()) - commitsBefore, 1, 'the catch-up was not exactly one commit');
      assert.equal(await same('#stage-choice', 'select'), true);
      assert.equal(await page.evaluate(() => document.activeElement?.id), 'stage-choice');
      assert.notEqual(await readout('choice').textContent(), '');
    },
  );

  await step(
    'a select blur catches up once; a manual refresh paints over an open list',
    async () => {
      await load();
      const select = page.locator('#stage-choice');
      await select.focus();
      const commitsBefore = await commits();
      await settleRefresh(3);
      assert.equal((await commits()) - commitsBefore, 0);
      await select.blur();
      await page.waitForFunction(() => globalThis.__gallery.gate.hasPending() === false);
      assert.equal((await commits()) - commitsBefore, 1);
      assert.equal(await displayed(), await accepted());
      await select.focus();
      await settleRefresh(2);
      const heldAt = await displayed();
      await refresh(true);
      assert.ok((await displayed()) > heldAt, 'a manual refresh did not paint over the open list');
      assert.equal(await page.evaluate(() => globalThis.__gallery.gate.hasPending()), false);
    },
  );

  await step(
    'at most twelve consecutive holds, then the board paints and the cap is not re-armed',
    async () => {
      await load();
      const select = page.locator('#stage-choice');
      await select.focus();
      const start = await displayed();
      await settleRefresh(12);
      assert.equal(await displayed(), start, 'a hold ended before the twelfth');
      assert.equal(await page.evaluate(() => globalThis.__gallery.gate.deferredCount()), 12);
      await refresh();
      const first = await displayed();
      assert.equal(first, await accepted(), 'the thirteenth did not paint');
      await refresh();
      assert.equal(
        await displayed(),
        await accepted(),
        'the cap was re-armed while the list stayed focused',
      );
      assert.equal(await page.evaluate(() => globalThis.__gallery.gate.deferredCount()), 12);
      await page.evaluate(() => document.activeElement?.blur());
    },
  );

  await step(
    'a real click opens the native popup and the board stays held until the pick',
    async () => {
      // Headless Chromium draws the popup outside the DOM and swallows keys sent to it, so its contents
      // cannot be read here. What is checked is the contract around it: the click focuses the select,
      // the polls are held while it is open, and the pick (`selectOption` fires the real input and change
      // events) catches the board up.
      await load();
      const select = page.locator('#stage-choice');
      const shown = await displayed();
      await select.click();
      await settleRefresh(3);
      assert.equal(await page.evaluate(() => document.activeElement?.id), 'stage-choice');
      assert.equal(await displayed(), shown, 'a poll painted while the select was open');
      await select.selectOption({ index: 2 });
      await page.waitForFunction(
        () => document.querySelector('[data-readout="choice"]')?.textContent !== '',
      );
      assert.equal(await displayed(), await accepted());
    },
  );

  // ---------------------------------------------------------------------------------------------
  await step(
    'an open disclosure keeps its node, open state and summary focus, and replays no motion, across live data',
    async () => {
      await load({ stream: true });
      const plan = page.locator(ACCORDION);
      await mark(ACCORDION, 'plan');
      await startSampler(page.locator('body'));
      await plan.locator('summary').click();
      await pause(400);
      const eased = await readSampler(page.locator('body'));
      // One intermediate frame is the proof: the 200 ms ease is sampled once per frame, and a loaded runner draws about 35 of them a second.
      assert.ok(
        eased.easing >= 1,
        `the reader's own toggle did not ease (${eased.easing} easing frames of ${eased.frames})`,
      );
      await page.evaluate(() => {
        globalThis.__openMutations = 0;
        new MutationObserver((records) => {
          globalThis.__openMutations += records.length;
        }).observe(globalThis.__marks.plan, { attributes: true, attributeFilter: ['open'] });
      });
      await plan.locator('summary').focus();
      await startSampler(page.locator('body'));
      const before = await accepted();
      await settleRefresh(4);
      await page.waitForFunction(
        (count) => globalThis.__gallery.runtime.store.getSnapshot().acceptedCount >= count + 4,
        before,
      );
      await pause(500);
      const idle = await readSampler(page.locator('body'));
      assert.equal(await same(ACCORDION, 'plan'), true, 'the node was replaced');
      assert.equal(await plan.evaluate((node) => node.open), true);
      assert.equal(await page.evaluate(() => globalThis.__openMutations), 0, 'open was rewritten');
      assert.equal(idle.easing, 0, `a redraw replayed the opening motion (${idle.easing} frames)`);
      assert.ok(idle.frames > 3, 'the frame sampler was not running');
      assert.equal(await page.evaluate(() => document.activeElement?.tagName), 'SUMMARY');
      assert.match(await readout('plan-body').textContent(), /board \d+/);
    },
  );

  await step(
    'a disclosure the reader opened comes back open, with no motion, after its view is left and re-entered',
    async () => {
      await load();
      await page.locator(ACCORDION).locator('summary').click();
      await page.locator('summary:text-is("Why")').click();
      await pause(400);
      await page.locator('button:text-is("Hide disclosures")').click();
      assert.equal(await page.locator(ACCORDION).count(), 0);
      await startSampler(page.locator('body').first());
      await page.locator('button:text-is("Show disclosures")').click();
      await pause(400);
      const motion = await readSampler(page.locator('body'));
      assert.equal(
        await page.locator(ACCORDION).evaluate((node) => node.open),
        true,
        'the open state was lost',
      );
      // The click that left the view was outside the popover, so it closed it, and the closed state is what comes back.
      assert.equal(
        await page.locator('details.ctl-disclosure--pop').evaluate((node) => node.open),
        false,
        'a popover stayed open past an outside click',
      );
      assert.equal(motion.easing, 0, 'a remounted open disclosure replayed its opening motion');
    },
  );

  await step(
    'a reader toggle holds the poll for the motion window (220 ms) and coalesces it',
    async () => {
      await load();
      const plan = page.locator('details:has(> summary:text-is("Project plan"))');
      const timing = async () =>
        page.evaluate(async () => {
          const read = () =>
            Number(document.querySelector('[data-readout="displayed-accepted"]').textContent);
          const before = read();
          const started = performance.now();
          document.querySelector('details > summary').click();
          const pending = globalThis.__gallery.runtime.refresh();
          let shown = null;
          for (;;) {
            await new Promise((resolve) => requestAnimationFrame(resolve));
            if (read() !== before) {
              shown = performance.now() - started;
              break;
            }
            if (performance.now() - started > 2000) break;
          }
          await pending;
          return shown;
        });
      const held = await timing();
      assert.ok(held !== null && held >= 180, `the poll painted ${held} ms after a toggle`);
      assert.ok(held < 3000, `the poll waited ${held} ms`);
      await plan.locator('summary').click();
      await pause(300);
      return { heldMs: Math.round(held) };
    },
  );

  // ---------------------------------------------------------------------------------------------
  await step(
    'a draft keeps text, caret, selection and native undo through live data from the real SSE stream',
    async () => {
      await load({ stream: true });
      const draft = page.locator('#gallery-draft');
      await mark('#gallery-draft', 'draft');
      await draft.click();
      await page.keyboard.type('hello brave world');
      for (let i = 0; i < 5; i += 1) await page.keyboard.press('ArrowLeft');
      // One character is one undo step whatever the engine's typing coalescing does.
      await page.keyboard.type('X');
      await page.keyboard.press('ArrowLeft');
      await page.keyboard.press('Shift+ArrowLeft');
      await page.keyboard.press('Shift+ArrowLeft');
      const caret = await draft.evaluate((node) => [
        node.selectionStart,
        node.selectionEnd,
        node.value,
      ]);
      const before = await accepted();
      const stop = pump();
      try {
        // Only the stream delivers here: no explicit refresh from the page.
        await page.waitForFunction(
          (count) => globalThis.__gallery.runtime.store.getSnapshot().acceptedCount >= count + 2,
          before,
          { timeout: 30000 },
        );
      } finally {
        stop();
      }
      assert.equal(
        log.requests.filter((entry) => entry.path.startsWith('/api/stream')).length >= 1,
        true,
        'the page never opened its stream',
      );
      assert.equal(await same('#gallery-draft', 'draft'), true, 'the draft node was replaced');
      assert.deepEqual(
        await draft.evaluate((node) => [node.selectionStart, node.selectionEnd, node.value]),
        caret,
      );
      assert.equal(await page.evaluate(() => document.activeElement?.id), 'gallery-draft');
      await page.keyboard.press(`${MOD}+z`);
      assert.equal(
        await draft.inputValue(),
        'hello brave world',
        'native undo did not survive the updates',
      );
      await page.keyboard.press(`${MOD}+Shift+z`);
      assert.equal(
        await draft.inputValue(),
        'hello brave Xworld',
        'native redo did not survive the updates',
      );
      return { viaSse: true };
    },
  );

  await step(
    'an IME composition survives live data: no compositionend, same node, text commits once',
    async () => {
      await load();
      await page.evaluate(() => {
        globalThis.__ime = [];
        const target = document.querySelector('#gallery-draft');
        for (const type of ['compositionstart', 'compositionupdate', 'compositionend'])
          target.addEventListener(type, () => globalThis.__ime.push(type));
      });
      const draft = page.locator('#gallery-draft');
      await mark('#gallery-draft', 'draft');
      await draft.click();
      await page.keyboard.type('ab ');
      const cdp = await shell.context.newCDPSession(page);
      await cdp.send('Input.imeSetComposition', {
        text: 'にほん',
        selectionStart: 3,
        selectionEnd: 3,
      });
      assert.ok(
        (await page.evaluate(() => globalThis.__ime)).includes('compositionstart'),
        'the composition never started',
      );
      await settleRefresh(3);
      await settleRefresh(1, true);
      const ime = await page.evaluate(() => globalThis.__ime);
      assert.ok(
        !ime.includes('compositionend'),
        `a redraw ended the composition: ${ime.join(',')}`,
      );
      assert.equal(await same('#gallery-draft', 'draft'), true);
      assert.equal(await draft.inputValue(), 'ab にほん');
      await cdp.send('Input.imeSetComposition', {
        text: '日本',
        selectionStart: 2,
        selectionEnd: 2,
      });
      await cdp.send('Input.insertText', { text: '日本' });
      assert.equal(await draft.inputValue(), 'ab 日本');
      assert.equal(await same('#gallery-draft', 'draft'), true);
      assert.equal(
        (await page.evaluate(() => globalThis.__ime)).filter((type) => type === 'compositionend')
          .length,
        1,
      );
      await cdp.detach();
    },
  );

  await step(
    'a draft keeps its inner scroll, dragged size and caret after focus leaves, and after a remount',
    async () => {
      await load();
      const draft = page.locator('#gallery-draft');
      await draft.click();
      await draft.evaluate((node) => {
        node.value = Array.from({ length: 40 }, (_, index) => `line ${index}`).join('\n');
        node.style.height = '120px';
        node.style.width = '260px';
        node.scrollTop = 150;
        node.dispatchEvent(new Event('input', { bubbles: true }));
        node.setSelectionRange(12, 20);
      });
      await page.locator('button:text-is("Hide draft")').click();
      await page.locator('button:text-is("Show draft")').click();
      const state = await draft.evaluate((node) => [
        node.selectionStart,
        node.selectionEnd,
        node.scrollTop,
        node.style.height,
        node.style.width,
      ]);
      assert.deepEqual(
        state,
        [12, 20, 150, '120px', '260px'],
        'a remounted draft lost its caret, scroll or size',
      );
      // Focus away, update, and the unfocused field is untouched.
      await page.locator('button:text-is("Hide draft")').focus();
      await mark('#gallery-draft', 'draft').catch(() => undefined);
      await settleRefresh(3);
      assert.deepEqual(
        await draft.evaluate((node) => [
          node.selectionStart,
          node.selectionEnd,
          node.scrollTop,
          node.style.height,
        ]),
        [12, 20, 150, '120px'],
      );
    },
  );

  // ---------------------------------------------------------------------------------------------
  await step(
    'human context saves each input, keeps text, caret and undo through updates, and the words reload from storage',
    async () => {
      await load();
      await page.getByRole('button', { name: 'Edit OUTCOME' }).click();
      const box = page.getByRole('textbox', { name: 'OUTCOME' });
      await box.waitFor();
      assert.equal(await page.evaluate(() => document.activeElement?.tagName), 'TEXTAREA');
      assert.equal(await box.getAttribute('maxlength'), '500');
      await mark('textarea[maxlength="500"]', 'memo');
      await page.keyboard.type('Ship the importer');
      await settleRefresh(3);
      assert.equal(await same('textarea[maxlength="500"]', 'memo'), true);
      assert.equal(await box.inputValue(), 'Ship the importer');
      assert.equal(await page.evaluate(() => document.activeElement?.tagName), 'TEXTAREA');
      await page.keyboard.press(`${MOD}+z`);
      assert.equal(await box.inputValue(), '', 'undo did not survive');
      await page.keyboard.press(`${MOD}+Shift+z`);
      assert.equal(await box.inputValue(), 'Ship the importer');
      assert.match(
        await page.locator('[data-memo-cue="outcome"]').textContent(),
        /Saved in this browser/,
      );
      const key = await page.evaluate(() =>
        Object.keys(localStorage).find(
          (name) =>
            name.startsWith('cargento.cockpit.memo.v2:') && name.endsWith(':project:outcome'),
        ),
      );
      assert.ok(key, 'no released-format key was written');
      assert.equal(
        await page.evaluate((name) => localStorage.getItem(name), key),
        'Ship the importer',
      );
      await page.getByRole('button', { name: 'Done' }).click();
      assert.equal(
        await page.evaluate(() => document.activeElement?.getAttribute('aria-label')),
        'Edit OUTCOME',
      );
      await page.reload();
      await gallery().waitFor();
      await page.getByText('Ship the importer').waitFor();
    },
  );

  await step(
    'Escape restores the words held when editing began, closes, and says nothing',
    async () => {
      await load();
      await page.getByRole('button', { name: 'Edit OUTCOME' }).click();
      await page.keyboard.type(' plus more');
      await page.keyboard.press('Escape');
      await page.getByText('Ship the importer', { exact: true }).waitFor();
      assert.equal(await page.locator('textarea[maxlength="500"]').count(), 0);
      assert.deepEqual(await page.evaluate(() => globalThis.__gallery.hooks.announced), []);
      assert.equal(await page.evaluate(() => globalThis.location.hash), '');
    },
  );

  await step('a failing browser store keeps the words in memory and says so', async () => {
    await page.addInitScript(() => {
      if (globalThis.location.search.includes('blocked=1'))
        Storage.prototype.setItem = () => {
          throw new DOMException('quota', 'QuotaExceededError');
        };
    });
    await page.unroute('**/api/stream').catch(() => undefined);
    await page.route('**/api/stream', (route) => route.abort());
    await page.goto(`${dev.origin}/?strict=1&blocked=1`);
    await gallery().waitFor();
    await page.getByRole('button', { name: 'Edit FOCUS' }).click();
    await page.keyboard.type('only here');
    assert.match(
      await page.locator('[data-memo-cue="focus"]').textContent(),
      /Browser storage unavailable/,
    );
    await page.getByRole('button', { name: 'Done' }).click();
    await page.getByText('only here').waitFor();
  });

  // ---------------------------------------------------------------------------------------------
  await step(
    'keyboard focus survives a swapped node, and an offscreen one does not scroll the page back',
    async () => {
      await load();
      const parked = page.locator('button:text-is("Parked control")');
      await parked.focus();
      await page.evaluate(() => globalThis.scrollTo(0, 0));
      assert.equal(await page.evaluate(() => globalThis.scrollY), 0);
      await mark('button:text-is("Parked control")', 'parked');
      await settleRefresh(3);
      assert.equal(
        await same('button:text-is("Parked control")', 'parked'),
        false,
        'the control was not actually swapped',
      );
      assert.equal(
        await page.evaluate(() => document.activeElement?.textContent),
        'Parked control',
      );
      assert.equal(
        await page.evaluate(() => globalThis.scrollY),
        0,
        'restoring focus scrolled the reader down to an offscreen control',
      );
      // A visible control keeps ordinary focus without moving the page either.
      await page.evaluate(() => globalThis.scrollTo(0, document.documentElement.scrollHeight));
      await parked.focus();
      const at = await page.evaluate(() => globalThis.scrollY);
      await settleRefresh(2);
      assert.equal(
        await page.evaluate(() => document.activeElement?.textContent),
        'Parked control',
      );
      assert.ok(Math.abs((await page.evaluate(() => globalThis.scrollY)) - at) <= 2);
    },
  );

  // ---------------------------------------------------------------------------------------------
  await step(
    'copy cues are distinct and durable, copy writes once per press, and raise is explicit and deduplicated',
    async () => {
      await load({ stream: true });
      const idButton = page.getByRole('button', { name: /^Copy session ID colon:sid$/ }).first();
      await idButton.click();
      await page.waitForFunction(() => globalThis.__gallery.hooks.copied.length === 1);
      assert.deepEqual(await page.evaluate(() => globalThis.__gallery.hooks.copied), ['colon:sid']);
      assert.equal(await idButton.getAttribute('data-copy-state'), 'copied');
      assert.equal(
        await page
          .getByRole('button', { name: 'Copy a link to this session' })
          .first()
          .getAttribute('data-copy-state'),
        null,
      );
      await settleRefresh(3);
      assert.equal(
        await idButton.getAttribute('data-copy-state'),
        'copied',
        'the cue did not survive the updates',
      );
      assert.equal(
        await page.evaluate(() => globalThis.__gallery.hooks.copied.length),
        1,
        'an update copied again',
      );
      assert.equal(await page.evaluate(() => globalThis.__gallery.hooks.announced.length), 1);

      // The real POST to the real route, answered by the inert raise. Delayed so a second press lands in flight.
      const raises = [];
      await page.route('**/api/focus', async (route) => {
        raises.push(route.request().method());
        await pause(500);
        await route.continue();
      });
      const raise = page.getByRole('button', { name: /Raise the terminal/ });
      assert.equal(
        log.nonGet.filter((entry) => entry.path === '/api/focus').length,
        0,
        'a raise was sent before any press',
      );
      await raise.nth(0).click();
      await page.waitForFunction(
        () => document.querySelectorAll('[aria-disabled="true"]').length >= 2,
      );
      assert.equal(await raise.nth(1).evaluate((node) => node.disabled), false);
      // Playwright treats aria-disabled as not actionable and would wait the press out; a reader's click does not.
      await raise.nth(1).evaluate((node) => node.click());
      await page.waitForFunction(() => !document.querySelector('.ctl-raise[aria-disabled="true"]'));
      assert.equal(raises.length, 1, 'a second press while one was in flight sent another request');
      assert.equal(await raise.nth(1).getAttribute('data-raise-state'), 'throttled');
      assert.equal(await raise.nth(0).getAttribute('data-raise-state'), 'declined');
      const said = await page.evaluate(() =>
        globalThis.__gallery.hooks.announced.map((entry) => entry.text),
      );
      assert.ok(said.includes('Raise requested') && said.includes('No terminal was raised'));
      assert.equal(
        said.filter((text) => text === 'Raise requested').length,
        1,
        'the deduplicated press announced a request it never made',
      );
      assert.ok(
        said.some((text) => text.startsWith('Raise refused: another raise was too recent')),
      );
      await page.unroute('**/api/focus');
    },
  );

  await step(
    'the More menu copies the briefing once and keeps reading Copied with no expiry',
    async () => {
      await load();
      await page.locator('summary[aria-label="More"]').click();
      await page.getByRole('button', { name: 'Copy briefing' }).click();
      await page.getByRole('button', { name: 'Copied' }).waitFor();
      assert.equal((await page.evaluate(() => globalThis.__gallery.hooks.copied)).length, 1);
      await settleRefresh(2);
      assert.equal(await page.getByRole('button', { name: 'Copied' }).count(), 1);
      await page.getByRole('button', { name: 'Add human context' }).click();
      assert.equal(await page.evaluate(() => document.activeElement?.tagName), 'TEXTAREA');
    },
  );

  // ---------------------------------------------------------------------------------------------
  const widths = [320, 375, 188, 160];
  await step(
    'no horizontal scroll and 44px targets at 320 and 375 CSS px and at 200% zoom of each',
    async () => {
      await load();
      await page.locator('summary[aria-label="More"]').click();
      await page.locator('summary:text-is("Why")').click();
      await page.locator('summary:text-is("Project plan")').click();
      await page.getByRole('button', { name: 'Edit FOCUS' }).click();
      const report = {};
      for (const width of widths) {
        await page.setViewportSize({ width, height: 700 });
        await pause(150);
        const metrics = await page.evaluate(() => ({
          scroll: document.documentElement.scrollWidth,
          client: document.documentElement.clientWidth,
          wide: [...document.querySelectorAll('#gallery *')]
            .filter(
              (node) =>
                node.getBoundingClientRect().right > document.documentElement.clientWidth + 0.5,
            )
            .slice(0, 6)
            .map(
              (node) =>
                `${node.tagName.toLowerCase()}.${String(node.className).slice(0, 30)}:${Math.round(node.getBoundingClientRect().right)}`,
            ),
          small: [
            ...document.querySelectorAll(
              '#gallery .ctl-copy, #gallery .ctl-raise, #gallery .ctl-action, #gallery summary, #gallery .ctl-menu-items button, #gallery .ctl-memo button',
            ),
          ]
            .filter((node) => {
              const rect = node.getBoundingClientRect();
              return rect.width > 0 && (rect.height < 43.5 || rect.width < 43.5);
            })
            .map((node) => node.textContent.trim().slice(0, 24)),
        }));
        report[width] = metrics.scroll - metrics.client;
        assert.ok(
          metrics.scroll <= metrics.client,
          `horizontal scroll at ${width}px: ${metrics.scroll} > ${metrics.client} (${metrics.wide.join(' | ')})`,
        );
        assert.ok(
          metrics.small.length === 0,
          `targets under 44px at ${width}px: ${metrics.small.join(' | ')}`,
        );
        if (shots && (width === 320 || width === 375))
          await page.screenshot({
            path: join(SCREENSHOTS, `drc-4823-controls-gallery-${width}px.png`),
            fullPage: true,
          });
      }
      await page.setViewportSize({ width: 1100, height: 900 });
      return report;
    },
  );

  await step('reduced motion: a reader toggle runs no transition and holds no paint', async () => {
    reduced = await openPage(browser, origins, {
      viewport: { width: 1100, height: 900 },
      reducedMotion: 'reduce',
    });
    await reduced.page.route('**/api/stream', (route) => route.abort());
    await reduced.page.goto(`${dev.origin}/?strict=1`);
    await reduced.page.locator('#gallery').waitFor();
    await reduced.page.waitForFunction(
      () => Number(document.querySelector('[data-readout="displayed-accepted"]')?.textContent) >= 1,
    );
    await startSampler(reduced.page.locator('body'));
    await reduced.page.locator('summary:text-is("Project plan")').click();
    await pause(400);
    const calm = await readSampler(reduced.page.locator('body'));
    assert.ok(calm.frames > 3, 'the frame sampler was not running');
    assert.equal(calm.easing, 0, 'the disclosure eased under reduced motion');
    const shown = await reduced.page.evaluate(async () => {
      const read = () =>
        Number(document.querySelector('[data-readout="displayed-accepted"]').textContent);
      const before = read();
      document.querySelector('details > summary').click();
      const started = performance.now();
      await globalThis.__gallery.runtime.refresh();
      return { changed: read() !== before, ms: performance.now() - started };
    });
    assert.equal(shown.changed, true, 'reduced motion held a paint');
    assert.deepEqual(reduced.log.pageErrors, []);
  });

  assert.deepEqual(log.externalRequests, [], 'a request left the board');
  assert.deepEqual(log.pageErrors, [], 'a page error was raised');
  assert.deepEqual(
    log.consoleErrors.filter((text) => !/^Failed to load resource: net::ERR_FAILED$/.test(text)),
    [],
    'a console error was logged',
  );
  if (shots) {
    await load();
    await page.screenshot({ path: join(SCREENSHOTS, 'drc-4823-controls-gallery-1100px.png') });
  }
  console.log(
    JSON.stringify(
      {
        controlsBrowser: {
          mutation: mutation || null,
          strictMode: true,
          realBackend: true,
          steps: results,
        },
      },
      null,
      2,
    ),
  );
} catch (error) {
  console.error(
    JSON.stringify(
      {
        mutation: mutation || null,
        steps: results,
        failure: error.message.split('\n').slice(0, 4).join(' | '),
      },
      null,
      2,
    ),
  );
  process.exitCode = 1;
} finally {
  if (reduced) await reduced.close().catch(() => undefined);
  if (shell) await shell.close().catch(() => undefined);
  if (browser) await browser.close();
  if (dev) await dev.close();
  await rm(copy, { recursive: true, force: true });
}
