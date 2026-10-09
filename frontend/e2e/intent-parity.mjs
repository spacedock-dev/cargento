/* global document, getComputedStyle, requestAnimationFrame -- used inside page.evaluate, which runs in the browser */
/*
 * The Intent log and the Intent panel in a real browser, against the real backend.
 *
 * Two kinds of proof. The DIFFERENTIAL half drives the legacy page and the React page in the same Chromium
 * over one real backend (the real annotation store behind both, one at a time, given the same sequence of
 * writes) and compares what a reader can read: the Intent log's notes, groups, rows and links, and the
 * editor's boxes, counts, marks, controls and cues, in each state a reader reaches. The BEHAVIOUR half holds
 * the React page to what a unit test cannot see: the native editor's text, caret, selection, undo history
 * and input-method composition surviving the board's own revisions (announced over the real stream), a
 * route away and back, the native select, the discard's dwell, the live monitor switch's storage key, the
 * StrictMode request and resource counts, keyboard operation, and 320/375/640(200% zoom)/1280 CSS px layouts
 * with no horizontal page scroll.
 *
 * Models, usage, notifications, the clipboard and the terminal are off or replaced. Every request leaving
 * the board's own origins is refused. Run with `pnpm test:intent:browser`; `CARGENTO_E2E_STEPS=<regex>` runs
 * only the steps whose name matches.
 */
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';
import { call, startIntentBoard } from './intent-board.mjs';
import { instrumentResources, recordClipboard, resources } from './sessions-board.mjs';
import { openPage } from './support/browser.mjs';

/* Every fixed wait here means "give the page time to react". A hosted runner has a few shared cores and
   delivers events and frames later than a desktop, so each wait is tripled there; only a pass gets slower. A
   state is read once two reads a short while apart agree (`settled`), never after a fixed delay alone. */
const patience = (ms) => (process.env.CI ? ms * 3 : ms);
const MOD = process.platform === 'darwin' ? 'Meta' : 'Control';

const checkout = fileURLToPath(new URL('../../', import.meta.url)).replace(
  /\/\.claude\/worktrees\/[^/]+\/?$/,
  '/',
);
const SHOTS = (process.env.CARGENTO_SCREENSHOTS || `${checkout}docs/screenshots`).replace(
  /\/?$/,
  '/',
);
const receipts = {};
const failures = [];
const shots = [];
const only = process.env.CARGENTO_E2E_STEPS ? new RegExp(process.env.CARGENTO_E2E_STEPS) : null;

async function step(name, run) {
  if (only && !only.test(name)) return;
  try {
    const detail = await run();
    receipts[name] = detail === undefined ? 'ok' : detail;
  } catch (error) {
    failures.push({ name, message: String(error.stack || error.message || error).slice(0, 2500) });
    receipts[name] = 'FAILED';
  }
}

const E = encodeURIComponent;
const fragmentOf = (sid, project = 'w/alpha') => `#n=session:${E(project)}:claude:${E(sid)}`;

/* ---- what a reader can read, reduced to data. These run IN the page, so they are self-contained. ---- */
const summarizeLog = () => {
  const norm = (node) => (node ? node.textContent.replace(/\s+/g, ' ').trim() : '');
  const root = document.querySelector('[data-next-view-body="intent"]');
  if (!root) return { missing: true, text: norm(document.body).slice(0, 200) };
  return [...root.children].map((child) => {
    if (child.tagName === 'H1' || child.tagName === 'H2') return ['heading', norm(child)];
    if (child.classList.contains('next-intent-row')) {
      const link = child.querySelector('a');
      return [
        'row',
        [...child.children].map((cell) => [cell.className, norm(cell)]),
        link ? link.getAttribute('href') : null,
      ];
    }
    return ['note', norm(child)];
  });
};

const summarizeEditor = () => {
  const norm = (node) => (node ? node.textContent.replace(/\s+/g, ' ').trim() : '');
  const root = document.querySelector('.next-cockpit-held');
  if (!root) return { missing: true };
  const button = (b) => [norm(b), b.getAttribute('aria-disabled') === 'true', b.hidden];
  const fields = [...root.querySelectorAll('[data-next-cockpit-held-field]')].map((field) => ({
    kind: field.dataset.nextCockpitHeldField,
    label: norm(field.querySelector('.next-cockpit-held-label')),
    boxes: [...field.querySelectorAll('textarea')].map((box) => box.value),
    counts: [
      ...field.querySelectorAll(
        '[data-next-cockpit-held-count],[data-next-cockpit-held-line-count],[data-next-cockpit-direction-count]',
      ),
    ].map(norm),
    marks: norm(field.querySelector('[data-next-cockpit-draft-marks]')),
    sources: [...field.querySelectorAll('.next-cockpit-held-source')].map((node) => [
      norm(node),
      node.hasAttribute('data-next-cockpit-held-line-source-stale'),
    ]),
    buttons: [...field.querySelectorAll('button')].map(button),
    cues: [...field.querySelectorAll('small.next-cockpit-held-cue')].map(norm),
    menu: [...field.querySelectorAll('[data-next-cockpit-prompt-select] option')].map((o) => [
      o.value,
      norm(o),
    ]),
    absent: [...field.querySelectorAll('.next-cockpit-held-absent')].map((node) => [
      norm(node),
      node.hidden,
    ]),
    full: [...field.querySelectorAll('[data-next-cockpit-held-full]')].map((n) => [
      norm(n),
      n.hidden,
    ]),
  }));
  const footer = root.querySelector('.next-cockpit-held-footer');
  const question = document.querySelector('[data-next-cockpit-direction-question]');
  return {
    heading: norm(root.querySelector('h2')),
    notes: [...root.children]
      .filter(
        (child) => !child.matches('header, .next-cockpit-held-fields, .next-cockpit-held-footer'),
      )
      .map(norm),
    fields,
    footer: footer
      ? {
          hint: norm(footer.querySelector('.next-cockpit-held-hint')),
          buttons: [...footer.querySelectorAll('button')].map(button),
          cue: norm(footer.querySelector(':scope > small')),
        }
      : null,
    caveats: norm(document.querySelector('.next-session-drift-caveats')),
    later: norm(document.querySelector('.next-cockpit-conflict')),
    monitor: document.querySelector('.next-session-drift-switch')
      ? document.querySelector('.next-session-drift-switch').getAttribute('aria-checked')
      : null,
    question: question
      ? {
          said: norm(question.querySelector('.next-cockpit-direction-said')),
          buttons: [...question.querySelectorAll('.next-cockpit-reading-ask button')]
            .map(norm)
            .filter((label) => label !== 'Turn off readings'),
        }
      : null,
  };
};

/* A duration, a clock time and a fact id (which hashes the moment a message was written) differ between two
   backends started at different moments, and say the same thing about the reader's words either way. */
const comparable = (value) =>
  JSON.stringify(value)
    .replace(/(?<!\d)\d+[smhd]( \d+[smh])?(?![A-Za-z0-9])/g, '<age>')
    // No word boundary after the minutes: the page prints "13:09Adding a line..." with the next sentence glued on.
    .replace(/(?<!\d)\d\d:\d\d(?!\d)/g, '<clock>')
    .replace(/fact:[0-9a-f]{16}/g, '<fact>');

async function settled(read, { deadline = patience(6000), every = 100 } = {}) {
  let previous = comparable(await read());
  const until = Date.now() + deadline;
  for (;;) {
    await new Promise((resolve) => setTimeout(resolve, every));
    const next = comparable(await read());
    if (next === previous) return JSON.parse(next);
    previous = next;
    if (Date.now() > until) throw new Error('The page kept changing: ' + next.slice(0, 300));
  }
}

const board = await startIntentBoard({ legacy: true });
const browser = await chromium.launch();
const origins = [board.react.origin, board.react.viteOrigin, board.legacy.origin];
const opened = [];
async function newPage(kind, viewport = { width: 1280, height: 900 }) {
  const o = await openPage(browser, origins, { viewport });
  await o.context.addInitScript(() => {
    globalThis.__announced = [];
  });
  await recordClipboard(o.context);
  await instrumentResources(o.context);
  o.kind = kind;
  opened.push(o);
  return o;
}

async function load(o, fragment) {
  const origin = o.kind === 'legacy' ? board.legacy.origin : board.react.origin;
  await o.page.goto('about:blank');
  await o.page.goto(`${origin}/${fragment}`);
  if (o.kind === 'legacy')
    await o.page.waitForFunction('typeof nextData !== "undefined" && nextData !== null');
  else
    await o.page.waitForFunction(
      () =>
        document.querySelector('nav[aria-label="Primary"]') &&
        !/Waiting for the first board|first payload has not arrived/.test(document.body.innerText),
    );
}

const origin = (kind) => (kind === 'legacy' ? board.legacy.origin : board.react.origin);
const both = (fn) => Promise.all(['legacy', 'react'].map(fn));

/* One write, made identically on both backends. A prompt adoption names its prompt as that backend published
   it, because the two started at different moments. */
async function writeBoth(sid, body) {
  const out = {};
  for (const kind of ['legacy', 'react']) {
    const data = (await call(origin(kind), 'GET', '/api/data')).body;
    const row = data.sessions.find((s) => s.sid === sid);
    const request = { harness: 'claude', sid, expected_revision: row.annotation_revision || 0 };
    if (body.adopt === 'first-prompt') {
      Object.assign(request, {
        adopt: 'first-prompt',
        expected_prompt: row.first_prompt,
        expected_prompt_at: row.first_prompt_at,
      });
    } else Object.assign(request, body);
    out[kind] = await call(origin(kind), 'POST', '/api/annotate', request);
    assert.equal(out[kind].body.ok, true, `${kind} refused ${JSON.stringify(body)}`);
  }
  return out;
}

try {
  const legacy = await newPage('legacy');
  const react = await newPage('react');

  /* ===================== DIFFERENTIAL: the Intent log ===================== */
  async function compareLog(label) {
    await both((kind) => load(kind === 'legacy' ? legacy : react, '#n=intent'));
    const read = (o) => settled(() => o.page.evaluate(summarizeLog));
    const [old, mine] = await Promise.all([read(legacy), read(react)]);
    assert.deepEqual(mine, old, `the Intent log differs from the legacy log (${label})`);
    return old;
  }

  await step('the Intent log reads as the legacy log does, empty', async () => {
    const log = await compareLog('empty');
    assert.ok(JSON.stringify(log).includes('No goal or expected outcome has been saved yet.'));
    return `${log.length} blocks`;
  });

  await step(
    'the Intent log reads as the legacy log does over saved words, a prompt adoption and a discard',
    async () => {
      await writeBoth('intent-1', {
        goal: 'Fix the redirect for signed-in readers',
        lines: ['Readers land on the last page', 'Back still works'],
      });
      await writeBoth('intent-3', { adopt: 'first-prompt' });
      const saved = await compareLog('saved');
      const text = JSON.stringify(saved);
      assert.ok(text.includes('Typed goal: Fix the redirect for signed-in readers'));
      assert.ok(text.includes('Goal from your prompt: Tidy the unlabelled project.'));
      await writeBoth('intent-3', { clear: true });
      const discarded = await compareLog('discarded');
      assert.ok(JSON.stringify(discarded).includes('Your words'));
      return { rows: discarded.filter((block) => block[0] === 'row').length };
    },
  );

  /* ===================== DIFFERENTIAL: the editor ===================== */
  async function compareEditor(label, sid = 'intent-1', prepare = async () => undefined) {
    await both((kind) => load(kind === 'legacy' ? legacy : react, fragmentOf(sid)));
    await prepare();
    const read = (o) => settled(() => o.page.evaluate(summarizeEditor));
    const [old, mine] = await Promise.all([read(legacy), read(react)]);
    assert.deepEqual(mine, old, `the editor differs from the legacy editor (${label})`);
    return old;
  }

  await step(
    'the editor reads as the legacy editor does over a saved goal and its lines',
    async () => {
      const state = await compareEditor('saved');
      assert.deepEqual(state.fields[1].boxes, [
        'Readers land on the last page',
        'Back still works',
      ]);
      assert.equal(state.fields[0].boxes[0], 'Fix the redirect for signed-in readers');
      assert.ok(
        state.footer.buttons.every(([, inert]) => inert),
        'Save and Undo are live over saved words',
      );
    },
  );

  await step(
    'the editor reads as the legacy editor does over a drafted first prompt, a typed edit and an added line',
    async () => {
      const drafted = await compareEditor('drafted', 'intent-2');
      assert.equal(drafted.fields[0].boxes[0], 'Ship the queue worker behind a flag.');
      assert.match(drafted.fields[0].marks, /from your prompt/);
      const typed = await compareEditor('typed', 'intent-2', async () => {
        for (const o of [legacy, react]) {
          const box = o.page.locator('textarea[data-next-cockpit-held-kind="goal"]');
          await box.click();
          await o.page.keyboard.press(`${MOD}+a`);
          await o.page.keyboard.type('Ship the worker, then verify');
          await o.page.locator('[data-next-cockpit-action="held-line-add"]').click();
          await o.page.keyboard.type('The queue drains');
        }
      });
      assert.equal(typed.fields[0].marks, '');
      assert.equal(typed.fields[0].boxes[0], 'Ship the worker, then verify');
      assert.equal(typed.fields[1].boxes.at(-1), 'The queue drains');
      return typed.footer.buttons;
    },
  );

  await step(
    'the editor reads as the legacy editor does over a chosen prompt, later directions, a pending line and an armed discard',
    async () => {
      const options = {};
      await both(async (kind) => {
        const o = kind === 'legacy' ? legacy : react;
        await load(o, fragmentOf('intent-4'));
      });
      // A chosen prompt, picked through the native list.
      for (const o of [legacy, react]) {
        const select = o.page.locator('[data-next-cockpit-prompt-select]');
        await select.click();
        await o.page.waitForFunction(
          () => document.querySelectorAll('[data-next-cockpit-prompt-select] option').length > 1,
        );
        await select.selectOption({ index: 1 });
      }
      const read = (o) => settled(() => o.page.evaluate(summarizeEditor));
      let [old, mine] = await Promise.all([read(legacy), read(react)]);
      assert.deepEqual(mine, old, 'the editor differs from the legacy editor over a chosen prompt');
      assert.match(old.fields[0].boxes[0], /Rename the worker/);
      options.chosen = old.fields[0].menu.length;
      // Save it (one adoption on each backend), which is what makes later directions the page can ask about.
      for (const o of [legacy, react]) {
        await o.page.locator('[data-next-cockpit-action="held-save"]').click();
        await o.page.waitForFunction(
          () => document.querySelector('.next-cockpit-held-footer small')?.textContent,
        );
      }
      await new Promise((resolve) => setTimeout(resolve, patience(1800)));
      await both((kind) => load(kind === 'legacy' ? legacy : react, fragmentOf('intent-4')));
      [old, mine] = await Promise.all([read(legacy), read(react)]);
      assert.deepEqual(
        mine,
        old,
        'the editor differs from the legacy editor over later directions',
      );
      assert.ok(old.question, 'no later direction was asked about');
      options.question = old.question.buttons;
      // Add opens the selected direction as a pending line.
      for (const o of [legacy, react]) {
        await o.page
          .locator(
            '[data-next-cockpit-direction-question] [data-next-cockpit-action="direction-add"]',
          )
          .click();
        await o.page.waitForSelector('[data-next-cockpit-direction-key]');
      }
      [old, mine] = await Promise.all([read(legacy), read(react)]);
      assert.deepEqual(mine, old, 'the editor differs from the legacy editor over a pending line');
      // An armed discard.
      for (const o of [legacy, react]) {
        await o.page.locator('.next-cockpit-held-discard-offer summary').click();
        await o.page.locator('[data-next-cockpit-action="held-discard"]').click();
      }
      [old, mine] = await Promise.all([read(legacy), read(react)]);
      assert.deepEqual(
        mine,
        old,
        'the editor differs from the legacy editor over an armed discard',
      );
      assert.match(old.caveats, /Confirm discard/);
      return options;
    },
  );

  /* ===================== BEHAVIOUR: the native editor ===================== */
  /* The board's own revision, moved from outside the page: another session's words are saved, the backend's
     revision advances and the stream announces it, so what the page receives it was told, not asked for. */
  let tickNumber = 0;
  async function tick(o) {
    const before = o.counts().data;
    tickNumber += 1;
    const data = (await call(board.react.origin, 'GET', '/api/data')).body;
    const row = data.sessions.find((s) => s.sid === 'intent-3');
    await call(board.react.origin, 'POST', '/api/annotate', {
      harness: 'claude',
      sid: 'intent-3',
      goal: `tick ${tickNumber}`,
      expected_revision: row.annotation_revision || 0,
    });
    // Stand outside the page: the backend only recollects when something reads it.
    await call(board.react.origin, 'GET', '/api/data');
    // A beat for the announcement to travel. This was a `waitForFunction(() => true)` that waits for a frame,
    // which a page in the background does not draw within 100 ms on a loaded machine.
    await new Promise((resolve) => setTimeout(resolve, patience(100)));
    const until = Date.now() + patience(15000);
    while (o.counts().data <= before && Date.now() < until)
      await new Promise((r) => setTimeout(r, 100));
    assert.ok(o.counts().data > before, 'the page never received the new board revision');
  }
  const mark = (o, selector, name) =>
    o.page.locator(selector).evaluate((node, key) => {
      globalThis.__marks ??= {};
      globalThis.__marks[key] = node;
    }, name);
  const same = (o, selector, name) =>
    o.page.locator(selector).evaluate((node, key) => globalThis.__marks[key] === node, name);
  const GOAL = 'textarea[data-next-cockpit-held-kind="goal"]';

  await step(
    'the goal box keeps its node, text, caret, selection, focus and native undo through the board’s own revisions',
    async () => {
      await load(react, fragmentOf('intent-2'));
      await settled(() => react.page.evaluate(summarizeEditor));
      react.reset();
      const box = react.page.locator(GOAL);
      await mark(react, GOAL, 'goal');
      await box.click();
      await react.page.keyboard.press(`${MOD}+a`);
      await react.page.keyboard.type('hello brave world');
      for (let i = 0; i < 5; i += 1) await react.page.keyboard.press('ArrowLeft');
      await react.page.keyboard.type('X');
      await react.page.keyboard.press('ArrowLeft');
      await react.page.keyboard.press('Shift+ArrowLeft');
      await react.page.keyboard.press('Shift+ArrowLeft');
      const caret = await box.evaluate((node) => [
        node.selectionStart,
        node.selectionEnd,
        node.value,
      ]);
      for (let i = 0; i < 2; i += 1) await tick(react);
      assert.equal(
        await same(react, GOAL, 'goal'),
        true,
        'the goal box was replaced by a board revision',
      );
      assert.deepEqual(
        await box.evaluate((node) => [node.selectionStart, node.selectionEnd, node.value]),
        caret,
      );
      assert.equal(
        await react.page.evaluate(() => document.activeElement?.dataset.nextCockpitHeldKind),
        'goal',
      );
      await react.page.keyboard.press(`${MOD}+z`);
      assert.equal(
        await box.inputValue(),
        'hello brave world',
        'native undo did not survive the revisions',
      );
      await react.page.keyboard.press(`${MOD}+Shift+z`);
      assert.equal(
        await box.inputValue(),
        'hello brave Xworld',
        'native redo did not survive the revisions',
      );
      // The words reached the page's held state, which is what Save intent would send.
      assert.match(
        await react.page.locator('[data-next-cockpit-held-count="goal"]').innerText(),
        /^18\/240$/,
      );
      assert.deepEqual(react.log.nonGet, [], 'typing and revisions sent a write');
    },
  );

  await step(
    'an outcome line keeps its node, text, caret and undo through revisions too',
    async () => {
      await load(react, fragmentOf('intent-2'));
      await settled(() => react.page.evaluate(summarizeEditor));
      await react.page.locator('[data-next-cockpit-action="held-line-add"]').click();
      const line = react.page.locator('textarea[data-next-cockpit-held-line-index="1"]');
      await mark(react, 'textarea[data-next-cockpit-held-line-index="1"]', 'line');
      await react.page.keyboard.type('one two three');
      await react.page.keyboard.press('ArrowLeft');
      await react.page.keyboard.press('ArrowLeft');
      await tick(react);
      assert.equal(
        await same(react, 'textarea[data-next-cockpit-held-line-index="1"]', 'line'),
        true,
      );
      assert.deepEqual(await line.evaluate((n) => [n.selectionStart, n.value]), [
        11,
        'one two three',
      ]);
      // The browser's own history is the proof: it can only undo what the node it belongs to typed.
      await react.page.keyboard.press(`${MOD}+z`);
      assert.notEqual(
        await line.inputValue(),
        'one two three',
        'native undo did not survive the revision',
      );
    },
  );

  await step(
    'an IME composition in the goal box survives the board’s revisions: no compositionend, same node, commits once',
    async () => {
      await load(react, fragmentOf('intent-2'));
      await settled(() => react.page.evaluate(summarizeEditor));
      await react.page.evaluate(() => {
        globalThis.__ime = [];
        const target = document.querySelector('textarea[data-next-cockpit-held-kind="goal"]');
        for (const type of ['compositionstart', 'compositionupdate', 'compositionend'])
          target.addEventListener(type, () => globalThis.__ime.push(type));
      });
      const box = react.page.locator(GOAL);
      await mark(react, GOAL, 'goal');
      await box.click();
      await react.page.keyboard.press(`${MOD}+a`);
      await react.page.keyboard.type('ab ');
      const cdp = await react.context.newCDPSession(react.page);
      await cdp.send('Input.imeSetComposition', {
        text: 'にほん',
        selectionStart: 3,
        selectionEnd: 3,
      });
      assert.ok((await react.page.evaluate(() => globalThis.__ime)).includes('compositionstart'));
      await tick(react);
      await tick(react);
      const ime = await react.page.evaluate(() => globalThis.__ime);
      assert.ok(
        !ime.includes('compositionend'),
        `a revision ended the composition: ${ime.join(',')}`,
      );
      assert.equal(await same(react, GOAL, 'goal'), true);
      assert.equal(await box.inputValue(), 'ab にほん');
      await cdp.send('Input.imeSetComposition', {
        text: '日本',
        selectionStart: 2,
        selectionEnd: 2,
      });
      await cdp.send('Input.insertText', { text: '日本' });
      assert.equal(await box.inputValue(), 'ab 日本');
      assert.equal(await same(react, GOAL, 'goal'), true);
      assert.equal(
        (await react.page.evaluate(() => globalThis.__ime)).filter((t) => t === 'compositionend')
          .length,
        1,
      );
      // The held draft is the committed words, never the provisional ones.
      assert.equal(
        await react.page.locator('[data-next-cockpit-held-count="goal"]').innerText(),
        '5/240',
      );
      await cdp.detach();
    },
  );

  await step(
    'a draft survives leaving the session and coming back, with no write and no second read of the log',
    async () => {
      await load(react, fragmentOf('intent-2'));
      await settled(() => react.page.evaluate(summarizeEditor));
      await react.page.locator(GOAL).click();
      await react.page.keyboard.press(`${MOD}+a`);
      await react.page.keyboard.type('half a sentence');
      react.reset();
      await react.page.locator('nav[aria-label="Primary"] a', { hasText: 'Sessions' }).click();
      await react.page.waitForSelector('[data-next-view-body="sessions"]');
      await react.page.locator('nav[aria-label="Primary"] a', { hasText: 'Intent log' }).click();
      await react.page.waitForSelector('[data-next-view-body="intent"]');
      await react.page.goBack();
      await react.page.goBack();
      await react.page.waitForSelector(GOAL);
      assert.equal(await react.page.locator(GOAL).inputValue(), 'half a sentence');
      assert.deepEqual(react.log.nonGet, []);
      return {
        reads: react.log.requests.filter((r) => r.path.startsWith('/api/annotations')).length,
      };
    },
  );

  /* ===================== BEHAVIOUR: requests and resources ===================== */
  await step(
    'mount, StrictMode, revisions and repeated navigation send no write and do not grow the page’s resources',
    async () => {
      await load(react, fragmentOf('intent-2'));
      await settled(() => react.page.evaluate(summarizeEditor));
      await react.page.waitForFunction(() => globalThis.__resources?.sources >= 1);
      react.reset();
      const start = await resources(react.page);
      for (let i = 0; i < 4; i += 1) {
        await react.page.locator('nav[aria-label="Primary"] a', { hasText: 'Intent log' }).click();
        await react.page.waitForSelector('[data-next-view-body="intent"]');
        await react.page.locator('nav[aria-label="Primary"] a', { hasText: 'Sessions' }).click();
        await react.page.waitForSelector('[data-next-view-body="sessions"]');
        await react.page.evaluate((hash) => {
          globalThis.location.hash = hash;
        }, fragmentOf('intent-2'));
        await react.page.waitForSelector(GOAL);
      }
      await tick(react);
      const end = await resources(react.page);
      assert.deepEqual(react.log.nonGet, [], 'a mount, navigation or revision sent a write');
      assert.equal(end.sources, start.sources, 'event streams grew with navigation');
      assert.ok(end.intervals <= start.intervals + 0, 'intervals grew with navigation');
      const clip = await react.page.evaluate(() => globalThis.__copied);
      assert.deepEqual(clip, [], 'a clipboard write started on its own');
      return { start, end };
    },
  );

  /* ===================== BEHAVIOUR: the prompt menu, adoption, directions, discard ===================== */
  await step(
    'the native select reads the prompts once per opening, fills the box, and Save adopts it naming the fact',
    async () => {
      await load(react, fragmentOf('intent-2'));
      await settled(() => react.page.evaluate(summarizeEditor));
      react.reset();
      const select = react.page.locator('[data-next-cockpit-prompt-select]');
      await select.click();
      await react.page.waitForFunction(
        () => document.querySelectorAll('[data-next-cockpit-prompt-select] option').length > 1,
      );
      const prompts = react.log.requests.filter((r) => r.path.includes('prompts=1'));
      assert.equal(prompts.length, 1, 'the menu read the prompts more than once for one opening');
      const options = await select.locator('option').allTextContents();
      assert.match(
        options[1],
        /^First prompt · \d\d:\d\d — Ship the queue worker behind a flag\.$/,
      );
      await select.selectOption({ index: 1 });
      assert.equal(
        await react.page.locator(GOAL).inputValue(),
        'Ship the queue worker behind a flag.',
      );
      assert.equal(
        await react.page.locator('#next-cockpit-cue-status').innerText(),
        'Goal filled from your prompt. Not saved.',
      );
      assert.deepEqual(react.log.nonGet, [], 'choosing a prompt wrote');
      await react.page.locator('[data-next-cockpit-action="held-save"]').click();
      await react.page.waitForFunction(
        () =>
          document.querySelector('.next-cockpit-held-footer small')?.textContent ===
          'Saved as a new revision.',
      );
      assert.equal(react.log.nonGet.length, 1);
      const stored = (await call(board.react.origin, 'GET', '/api/data')).body.sessions.find(
        (s) => s.sid === 'intent-2',
      );
      assert.equal(stored.annotation_goal, 'Ship the queue worker behind a flag.');
      assert.equal(stored.annotation_goal_source, 'chosen-prompt');
    },
  );

  await step(
    'later directions: asked about before a reading, read whole before Keep settles, added only on Save',
    async () => {
      // The goal for intent-2 was saved above, which is what made the backend say two things more.
      await load(react, fragmentOf('intent-2'));
      await tick(react);
      await react.page.waitForSelector('[data-next-cockpit-direction-question]', {
        timeout: patience(15000),
      });
      const said = await react.page.locator('.next-cockpit-direction-said').innerText();
      const number =
        /^You gave 2 later directions since saving your intent, the selected direction at #(\d+): /.exec(
          said,
        )?.[1];
      assert.ok(number, `the question named no drawn number: ${said}`);
      react.reset();
      await react.page.locator('[data-next-cockpit-action="direction-keep"]').click();
      await react.page.waitForSelector('[data-next-cockpit-direction-whole]');
      assert.equal(
        await react.page.evaluate(() =>
          document.activeElement?.hasAttribute('data-next-cockpit-direction-whole'),
        ),
        true,
        'focus did not move to the whole text',
      );
      assert.deepEqual(
        react.log.nonGet.map((r) => r.path),
        ['/api/direction', '/api/direction'],
        'the first Keep settled something or sent more than the reads',
      );
      // The question's own Add: the numbered activity list draws one beside every later direction too.
      await react.page
        .locator(
          '[data-next-cockpit-direction-question] [data-next-cockpit-action="direction-add"]',
        )
        .click();
      await react.page.waitForSelector('[data-next-cockpit-direction-key]');
      assert.equal(
        await react.page
          .locator('.next-cockpit-direction-line .next-cockpit-held-source')
          .innerText(),
        `from #${number} · not saved`,
      );
      react.reset();
      await react.page.locator('[data-next-cockpit-action="direction-save"]').click();
      await react.page.waitForSelector('[data-next-cockpit-direction-key]', { state: 'detached' });
      assert.equal(react.log.nonGet.length, 1);
      const row = (await call(board.react.origin, 'GET', '/api/data')).body.sessions.find(
        (s) => s.sid === 'intent-2',
      );
      assert.match(String(row.annotation_line_1), /rollback steps/);
    },
  );

  await step(
    'Discard everything arms on the first press and is not confirmed by a double-click or a slip, then performs once',
    async () => {
      await load(react, fragmentOf('intent-1'));
      await settled(() => react.page.evaluate(summarizeEditor));
      const discard = react.page.locator('[data-next-cockpit-action="held-discard"]');
      react.reset();
      // Behind its own summary, as a reader finds it.
      await react.page.locator('.next-cockpit-held-discard-offer summary').click();
      await discard.click();
      assert.equal(await discard.innerText(), 'Confirm discard');
      assert.match(await react.page.locator('#next-cockpit-cue-alert').innerText(), /^.+$/);
      await discard.click();
      await discard.dblclick();
      assert.deepEqual(
        react.log.nonGet,
        [],
        'a slip inside the dwell was taken for a confirmation',
      );
      await react.page.waitForTimeout(patience(1500));
      await discard.click();
      await react.page.waitForFunction(
        () => document.querySelector('.next-cockpit-held-discard small')?.textContent,
      );
      assert.equal(react.log.nonGet.length, 1);
      assert.equal(react.log.nonGet[0].path, '/api/annotate');
      await react.page.locator('nav[aria-label="Primary"] a', { hasText: 'Intent log' }).click();
      const log = await settled(() => react.page.evaluate(summarizeLog));
      assert.ok(JSON.stringify(log).includes('Your words'), 'the log kept withdrawn words');
      assert.ok(!JSON.stringify(log).includes('Fix the redirect for signed-in readers'));
    },
  );

  await step('Escape on the armed control disarms it without leaving the page', async () => {
    await load(react, fragmentOf('intent-2'));
    await settled(() => react.page.evaluate(summarizeEditor));
    const discard = react.page.locator('[data-next-cockpit-action="held-discard"]');
    await react.page.locator('.next-cockpit-held-discard-offer summary').click();
    await discard.click();
    await react.page.keyboard.press('Escape');
    assert.equal(await discard.innerText(), 'Discard everything');
    assert.match(await react.page.evaluate(() => globalThis.location.hash), /^#n=session:/);
  });

  await step(
    'leaving the page while a save is open neither repeats nor drops it: one write, answered once, words kept',
    async () => {
      await load(react, fragmentOf('intent-3', 'w/unlabelled'));
      await settled(() => react.page.evaluate(summarizeEditor));
      // The write is held on its way to the backend, so the route change happens while it is open.
      await react.page.route('**/api/annotate', async (route) => {
        await new Promise((resolve) => setTimeout(resolve, patience(1500)));
        await route.continue();
      });
      react.reset();
      await react.page.locator(GOAL).click();
      await react.page.keyboard.press(`${MOD}+a`);
      await react.page.keyboard.type('saved while leaving');
      await react.page.locator('[data-next-cockpit-action="held-save"]').click();
      await react.page.locator('nav[aria-label="Primary"] a', { hasText: 'Sessions' }).click();
      await react.page.waitForSelector('[data-next-view-body="sessions"]');
      await react.page.waitForTimeout(patience(2500));
      await react.page.unroute('**/api/annotate');
      assert.equal(react.log.nonGet.length, 1, 'leaving the page repeated or dropped the write');
      await react.page.goBack();
      await react.page.waitForSelector(GOAL);
      await react.page.waitForFunction(
        () =>
          document.querySelector('textarea[data-next-cockpit-held-kind="goal"]')?.value ===
          'saved while leaving',
      );
      const stored = (await call(board.react.origin, 'GET', '/api/data')).body.sessions.find(
        (s) => s.sid === 'intent-3',
      );
      assert.equal(stored.annotation_goal, 'saved while leaving');
      assert.equal(react.log.nonGet.length, 1);
      assert.equal(
        await react.page
          .locator('[data-next-cockpit-action="held-save"]')
          .getAttribute('aria-busy'),
        null,
      );
    },
  );

  /* ===================== BEHAVIOUR: the live monitor switch ===================== */
  await step(
    'the live monitor switch writes 1 for this exact session, removes the key when off, and sends nothing',
    async () => {
      await load(react, fragmentOf('intent-2'));
      await settled(() => react.page.evaluate(summarizeEditor));
      const key = 'cargento.next.live-estimate:claude:intent-2';
      const sw = react.page.locator('.next-session-drift-switch');
      react.reset();
      assert.equal(await sw.getAttribute('aria-checked'), 'false');
      await sw.click();
      assert.equal(await sw.getAttribute('aria-checked'), 'true');
      assert.equal(await react.page.evaluate((k) => globalThis.localStorage.getItem(k), key), '1');
      await react.page.reload();
      await react.page.waitForSelector('.next-session-drift-switch');
      assert.equal(
        await react.page.locator('.next-session-drift-switch').getAttribute('aria-checked'),
        'true',
      );
      assert.equal(
        await react.page.evaluate(() =>
          globalThis.localStorage.getItem('cargento.next.live-estimate:claude:intent-1'),
        ),
        null,
      );
      await react.page.locator('.next-session-drift-switch').click();
      assert.equal(await react.page.evaluate((k) => globalThis.localStorage.getItem(k), key), null);
      assert.deepEqual(react.log.nonGet, []);
    },
  );

  /* ===================== BEHAVIOUR: keyboard ===================== */
  await step(
    'the editor is operable from the keyboard: Tab order, Enter on Save, Escape in the box',
    async () => {
      await load(react, fragmentOf('intent-1'));
      await settled(() => react.page.evaluate(summarizeEditor));
      await react.page.locator(GOAL).focus();
      await react.page.keyboard.press(`${MOD}+a`);
      await react.page.keyboard.type('Typed with the keyboard');
      const order = [];
      for (let i = 0; i < 14; i += 1) {
        await react.page.keyboard.press('Tab');
        order.push(
          await react.page.evaluate(
            () =>
              document.activeElement?.dataset.nextCockpitAction ||
              document.activeElement?.dataset.nextCockpitHeldLineIndex ||
              document.activeElement?.tagName,
          ),
        );
      }
      assert.ok(order.includes('held-save'), `Save is not reachable by Tab: ${order.join(',')}`);
      await react.page.locator(GOAL).focus();
      await react.page.keyboard.press('Escape');
      assert.notEqual(await react.page.locator(GOAL).inputValue(), 'Typed with the keyboard');
      await react.page.keyboard.type(' again');
      react.reset();
      await react.page.locator('[data-next-cockpit-action="held-save"]').focus();
      await react.page.keyboard.press('Enter');
      await react.page.waitForFunction(
        () => document.querySelector('.next-cockpit-held-footer small')?.textContent,
      );
      assert.equal(react.log.nonGet.length, 1);
      return order;
    },
  );

  /* ===================== BEHAVIOUR: layout ===================== */
  const SHAPES = [
    { width: 320, height: 800, name: '320' },
    { width: 375, height: 800, name: '375' },
    { width: 640, height: 800, name: '640', zoom: true },
    { width: 1280, height: 900, name: '1280' },
  ];
  const overflow = (page) =>
    page.evaluate(() => ({
      scroll: document.documentElement.scrollWidth,
      client: document.documentElement.clientWidth,
      wide: [...document.querySelectorAll('main *')]
        .filter(
          (node) =>
            node.getBoundingClientRect().right > document.documentElement.clientWidth + 1 &&
            getComputedStyle(node).position !== 'absolute',
        )
        .slice(0, 4)
        .map((node) => `${node.tagName}.${node.className}`),
    }));

  await step(
    'layout: the log and the panel wrap at 320, 375, 200% zoom and 1280 with no horizontal page scroll',
    async () => {
      await mkdir(SHOTS, { recursive: true });
      const report = {};
      const wide = [];
      for (const shape of SHAPES) {
        const pair = {};
        for (const kind of ['legacy', 'react'])
          pair[kind] = await newPage(kind, { width: shape.width, height: shape.height });
        try {
          for (const [label, fragment] of [
            ['log', '#n=intent'],
            ['drafted', fragmentOf('intent-2')],
            ['saved', fragmentOf('intent-1')],
          ]) {
            for (const kind of ['legacy', 'react']) {
              const o = pair[kind];
              await load(o, fragment);
              await settled(() => o.page.evaluate(() => document.body.innerText.length));
              if (shape.zoom)
                await o.page.evaluate(() => {
                  document.documentElement.style.zoom = '2';
                });
              const measured = await overflow(o.page);
              report[`${shape.name} ${label} ${kind}`] = measured;
              if (kind === 'react' && measured.scroll > measured.client)
                wide.push(`${shape.name} ${label}: ${JSON.stringify(measured)}`);
              if (shape.name === '375' || shape.name === '1280') {
                const name = `intent-${label}-${kind}-${shape.name}.png`;
                await o.page.screenshot({ path: SHOTS + name, fullPage: true });
                shots.push(name);
              }
            }
          }
        } finally {
          for (const kind of ['legacy', 'react']) await pair[kind].close();
        }
      }
      assert.deepEqual(wide, [], 'horizontal page overflow on the React page: ' + wide.join(' | '));
      return report;
    },
  );
} finally {
  for (const o of opened) await o.close().catch(() => undefined);
  await browser.close().catch(() => undefined);
  await board.close();
}

console.log(JSON.stringify({ receipts, screenshots: shots }, null, 2));
if (failures.length) {
  for (const failure of failures) console.error(`\nFAILED: ${failure.name}\n${failure.message}`);
  process.exit(1);
}
