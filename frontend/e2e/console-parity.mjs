/* global document, NodeFilter, getComputedStyle, requestAnimationFrame -- used inside page.evaluate, which runs in the browser */
/*
 * The steering bar, the tripwires, the workflow stage conditions, the Decisions tab and the Console tab in a real
 * browser.
 *
 * Two kinds of proof. The DIFFERENTIAL half drives the legacy page and the React page in the same Chromium over
 * one board (`console-board.mjs`: the real documents and modules, the real backend over a synthetic board with
 * asks, a stored history, a quota provider, one workflow stage source and a synthetic read-only terminal) and
 * compares what a reader can read in each state a reader reaches: the Console at project scope and with each of
 * three sessions selected, the Decisions tab under each filter, the Course tab's conditions in and out of scope,
 * a sent draft, an added and toggled tripwire, and a stage condition saved, rearmed and removed through the real
 * `/api/tripwire` route. The BEHAVIOUR half holds the React page to what a unit test cannot see: the steering
 * box's node, text, caret and native undo surviving the board's own revisions and a change of tab, the text and
 * caret coming back after a route away and back, the tripwire box staying open, Escape cancelling it without
 * leaving the page, a stage condition's focus and its native select across a poll, request counts over a mount,
 * a poll, a tab change and StrictMode, the retained terminal across tab switches, 320/375/640(200% zoom)/1280
 * CSS px layouts with no horizontal page scroll, and keyboard operation.
 *
 * No model is ever called and no native action is ever taken: the terminal pane prints only what this script
 * appends to its control file, and a raise is inert. Every request leaving the board's own origins is refused.
 * Run with `pnpm test:console:browser`; `CARGENTO_E2E_STEPS=<regex>` runs only the steps whose name matches, and
 * `CARGENTO_MUTATION=<name>` breaks one thing in the scratch copy (see MUTATIONS), which a run then must fail.
 */
import assert from 'node:assert/strict';
import { appendFile, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';
import { BOARD, fragmentFor, openTracked, startConsoleWorld } from './console-board.mjs';
import { refreshReact } from './support/browser.mjs';
import { PRODUCTION as SHIPPED } from './support/world.mjs';

/* Every fixed wait here means "give the page time to react". A hosted runner has a few shared cores and
   delivers events and frames later than a desktop, so each wait is tripled there; only a pass gets slower. A
   state is read once two reads a short while apart agree (`settled`), never after a fixed delay alone. */
/* What shows when the route is not a project. The harness draws its own marker; the shipped page draws the Sessions view. */
const AWAY = SHIPPED ? '[data-next-view-body="sessions"]' : '#elsewhere';
const patience = (ms) => (process.env.CI ? ms * 3 : ms);
const MOD = process.platform === 'darwin' ? 'Meta' : 'Control';
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

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
    failures.push({ name, message: String(error.stack || error.message || error).slice(0, 3000) });
    receipts[name] = 'FAILED';
  }
}

/* One deliberate break each, applied to the scratch copy only. Each names the file, the exact text and its
   replacement; a missing needle fails the run loudly rather than silently testing nothing. */
const MUTATIONS = {
  'remount-steer-box': [
    [
      'src/controls/DraftField.tsx',
      'return <input ref={ref} {...rest} />;',
      'return <input ref={ref} key={String(Math.random())} {...rest} />;',
    ],
  ],
  'drop-steer-draft': [
    [
      'src/steering/ProjectSteer.tsx',
      "held.setDraft(project, 'steer', event.currentTarget.value)",
      'void 0',
    ],
  ],
  'steer-keeps-live-node': [['src/steering/ProjectSteer.tsx', "input.value = '';", 'void 0;']],
  'escape-not-stopped': [['src/steering/Tripwires.tsx', 'event.stopPropagation();', 'void 0;']],
  'steer-box-shared-by-projects': [
    [
      'src/steering/ProjectSteer.tsx',
      'const key = `steer-draft:${project}`;',
      "const key = 'steer-draft';",
    ],
  ],
  'tripwire-draft-kept': [
    ['src/steering/Tripwires.tsx', "held.clearDraft(project, 'guardrail');", 'void 0;'],
  ],
  'adding-not-held': [['src/steering/Tripwires.tsx', 'held.setAdding(project, true);', 'void 0;']],
  'stage-focus-ignores-interaction': [
    [
      'src/steering/StageConditions.tsx',
      'request.interaction === held.stage.interaction()',
      'true',
    ],
  ],
  'stage-draft-lost': [['src/steering/held.ts', 'stageDrafts.set(id, stage);', 'void stage;']],
  'stage-posts-on-mount': [
    [
      'src/steering/StageConditions.tsx',
      'const release = held.stage.mounted();',
      "const release = held.stage.mounted();\n    void fetch('/api/tripwire', { method: 'POST', body: '{}' });",
    ],
  ],
  'terminal-outside-when-off': [
    ['src/delegation/Console.tsx', '{terminal === true ? surface : null}', '{surface}'],
  ],
  'setup-state-lost': [
    [
      'src/delegation/Console.tsx',
      "disclosureKey({ project, scope: scopeKey, name: 'console-setup' })",
      'disclosureKey({ project, scope: scopeKey, name: String(Math.random()) })',
    ],
  ],
  'delegation-zero': [
    [
      'src/delegation/metric.ts',
      "pctText: known ? `${String(pct)}%` : 'no figure yet',",
      'pctText: `${String(pct ?? 0)}%`,',
    ],
  ],
};

const world = await startConsoleWorld({ mutations: MUTATIONS });
const browser = await chromium.launch();
const origins = [world.react.origin, world.react.viteOrigin, world.legacy.origin];
const opened = [];
const E = encodeURIComponent;
const focusProbe = [];

/* ---- what a reader can read, reduced to data. These run IN the page, so they are self-contained. ---- */
const readSteer = () => {
  const norm = globalThis.__norm;
  const bar = document.querySelector('[data-next-steer]');
  if (!bar) return null;
  const input = bar.querySelector('[data-next-draft="steer"]');
  return {
    label: norm(bar.querySelector('.next-steer-label')),
    caveat: norm(bar.querySelector('.next-steer-caveat')),
    placeholder: input ? input.placeholder : null,
    maxlength: input ? input.maxLength : null,
    value: input ? input.value : null,
    submit: norm(bar.querySelector('button[type="submit"]')),
    receipts: [...bar.querySelectorAll('[data-next-steer-receipt]')].map(norm),
  };
};

const readConsole = () => {
  const norm = globalThis.__norm;
  const panel = document.querySelector('[data-next-cockpit-panel="console"]');
  if (!panel) return null;
  const setup = panel.querySelector('details.next-cockpit-console-setup');
  const rail = panel.querySelector('aside[data-next-project-rail]');
  const terminal = panel.querySelector('[data-next-cockpit-terminal]');
  const cue = panel.querySelector('.next-cockpit-scope--evidence .next-scope-cue');
  const order = [];
  for (const child of panel.children) {
    if (child.matches('header.next-cockpit-scope')) order.push('scope');
    else if (child.matches('p.next-cockpit-empty')) order.push('prompt');
    else if (child.matches('aside[data-next-project-rail]')) order.push('rail');
    else if (child.matches('[data-next-cockpit-terminal]')) order.push('terminal');
    else if (child.matches('details.next-cockpit-console-setup')) order.push('setup');
  }
  const prompt = panel.querySelector(':scope > p.next-cockpit-empty');
  return {
    order,
    scope: norm(panel.querySelector('.next-cockpit-scope--evidence')),
    scopeKind: cue ? [cue.dataset.scopeKind, cue.dataset.scopeOwner] : null,
    prompt: norm(prompt),
    promptLink:
      prompt && prompt.querySelector('a') ? prompt.querySelector('a').getAttribute('href') : null,
    rail: rail
      ? [...rail.querySelectorAll('[data-next-rail-panel]')].map((section) => ({
          name: section.dataset.nextRailPanel,
          text: norm(section),
          rows: [
            ...section.querySelectorAll(
              '[data-next-wait-session],[data-next-rail-window],[data-next-guardrail-toggle]',
            ),
          ].map((row) => norm(row)),
          controls: [...section.querySelectorAll('button')].map((button) => [
            norm(button),
            button.getAttribute('aria-label'),
            button.getAttribute('aria-checked'),
          ]),
          bars: [...section.querySelectorAll('progress,[role="img"]')].map((bar) => [
            bar.tagName,
            bar.getAttribute('value'),
            bar.getAttribute('aria-label'),
          ]),
        }))
      : null,
    terminal: terminal
      ? { inside: Boolean(setup && setup.contains(terminal)), text: norm(terminal) }
      : null,
    setup: setup
      ? { summary: norm(setup.querySelector(':scope > summary')), open: setup.open }
      : null,
    status: [...panel.querySelectorAll('.next-cockpit-console-status li')].map(norm),
  };
};

const readDecisions = () => {
  const norm = globalThis.__norm;
  const panel = document.querySelector('[data-next-cockpit-panel="decisions"]');
  if (!panel) return null;
  const section = panel.querySelector('.next-cockpit-semantic');
  const buttons = [...panel.querySelectorAll('.pc-graph-filter button')];
  return {
    summary: norm(panel.querySelector('[data-next-cockpit-decision-summary]')),
    heading: norm(section ? section.querySelector(':scope > h2') : null),
    mode: panel.querySelector('.pc-semantic-timeline')?.getAttribute('data-graph-mode') ?? null,
    filter: buttons.map((button) => [norm(button), button.getAttribute('aria-pressed')]),
    legend: [...panel.querySelectorAll('.pc-lane-labels > span')].map((node) => [
      node.getAttribute('title'),
      norm(node),
    ]),
    rows: [...panel.querySelectorAll('article.pc-graph-row')].map((row) => ({
      id: row.getAttribute('data-event-id'),
      lane: row.getAttribute('data-lane-key'),
      kind: row.getAttribute('data-semantic-kind'),
      rail: [...row.querySelectorAll('.pc-rail-cell')].map(
        (cell) =>
          `${cell.getAttribute('data-rail-key')}|${cell.classList.contains('active') ? 'active' : ''}|${[...cell.classList].filter((name) => name.startsWith('flow-')).join(',')}|${cell.querySelector('.pc-graph-mark') ? 'mark' : ''}`,
      ),
      text: norm(row),
    })),
    empty: norm(panel.querySelector('.pc-substrate-empty')),
    unbound: norm(panel.querySelector('.pc-unbound-context')),
  };
};

const readCourse = () => {
  const norm = globalThis.__norm;
  const section = document.querySelector('.next-stage-conditions');
  if (!section) return null;
  return {
    heading: norm(section.querySelector('h2')),
    intro: norm(section.querySelector(':scope > p')),
    cards: [...section.querySelectorAll('article.next-stage-rule')].map((card) => ({
      id: card.dataset.stageRule,
      title: norm(card.querySelector('h3')),
      lines: [...card.querySelectorAll(':scope > p')].map(norm),
      options: [...card.querySelectorAll('option')].map((option) => [
        option.value,
        option.selected,
        option.disabled,
      ]),
      selectDisabled: card.querySelector('select') ? card.querySelector('select').disabled : null,
      buttons: [...card.querySelectorAll('button')].map((button) => [
        button.dataset.stageAction,
        norm(button),
        button.disabled,
      ]),
      cue: norm(card.querySelector('[role="status"]')),
    })),
    fallback: [...section.querySelectorAll(':scope > p')].map(norm).slice(1),
  };
};

/* A duration, a clock time, an age and a fact id differ between two pages loaded a moment apart, and say the
   same thing about the board either way. */
const comparable = (value) =>
  JSON.stringify(value)
    .replace(/(?<!\d)\d+[smhd]( \d+[smh])?(?![A-Za-z0-9])/g, '<age>')
    .replace(/(?<!\d)\d\d:\d\d(?!\d)/g, '<clock>')
    .replace(/\d{4}-\d\d-\d\dT[\d:.]+Z/g, '<time>')
    .replace(/fact:[0-9a-f]{16}/g, '<fact>');

async function settled(read, { deadline = patience(9000), every = 150 } = {}) {
  let previous = comparable(await read());
  const until = Date.now() + deadline;
  for (;;) {
    await sleep(every);
    const next = comparable(await read());
    if (next === previous) return JSON.parse(next);
    previous = next;
    if (Date.now() > until) throw new Error(`The page kept changing: ${next.slice(0, 300)}`);
  }
}

/* ---- pages ---- */
const originOf = (kind) => (kind === 'legacy' ? world.legacy.origin : world.react.origin);

async function newPage(kind, { viewport = { width: 1280, height: 1000 }, strict = true } = {}) {
  const o = await openTracked(browser, origins, { viewport });
  o.kind = kind;
  o.strict = strict;
  let answered = 0;
  o.page.on('response', (response) => {
    if (new URL(response.url()).pathname === '/api/data' && response.ok()) answered += 1;
  });
  o.answered = () => answered;
  await o.context.addInitScript(() => {
    /* A node's words, each element's own run apart from the next. Adjacent text nodes are one run (React draws
       `resets ` and `2d` as two where the markup has one), so a split the reader cannot see changes nothing. */
    globalThis.__norm = (node) => {
      if (!node) return '';
      const words = [];
      let last = null;
      const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
      for (let text = walker.nextNode(); text; text = walker.nextNode()) {
        const value = text.nodeValue.replace(/\s+/g, ' ');
        if (last !== null && text.previousSibling === last.node) words[words.length - 1] += value;
        else words.push(value);
        last = { node: text };
      }
      return words
        .map((word) => word.trim())
        .filter(Boolean)
        .join(' ');
    };
    globalThis.__copied = [];
    Object.defineProperty(globalThis.navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: (text) => {
          globalThis.__copied.push(String(text));
          return Promise.resolve();
        },
      },
    });
  });
  opened.push(o);
  return o;
}

async function load(o, fragment, { wait = '[data-next-cockpit-panel]', state = 'visible' } = {}) {
  await o.page.goto('about:blank');
  const suffix = o.kind === 'react' && !o.strict ? '?strict=0' : '';
  await o.page.goto(`${originOf(o.kind)}/${suffix}${fragment}`);
  if (o.kind === 'legacy') {
    await o.page.waitForFunction('typeof nextData !== "undefined" && nextData !== null');
  } else {
    await o.page.waitForFunction(
      () =>
        document.querySelector('nav[aria-label="Primary"]') &&
        !/Waiting for the first board|first payload has not arrived/.test(document.body.innerText),
    );
  }
  await o.page.waitForSelector(wait, { state, timeout: patience(20000) });
}

async function hashTo(o, fragment) {
  await o.page.evaluate((next) => {
    globalThis.location.hash = next;
  }, fragment);
}

const both = (fn) => Promise.all([legacy, react].map(fn));
let legacy;
let react;

/* Both sides read until each has settled, then the two reads are compared. */
async function same(label, read, { ready = null } = {}) {
  if (ready) await both((o) => o.page.waitForFunction(ready, null, { timeout: patience(20000) }));
  const [old, mine] = await Promise.all([
    settled(() => legacy.page.evaluate(read)),
    settled(() => react.page.evaluate(read)),
  ]);
  assert.deepEqual(mine, old, `${label}: the React page reads differently from the legacy page`);
  return mine;
}

/* ================================================================================================ */
try {
  legacy = await newPage('legacy');
  react = await newPage('react');

  /* =============================== DIFFERENTIAL =============================== */
  await step(
    'the steering bar says what it is before the first keystroke, in both pages',
    async () => {
      await both((o) => load(o, fragmentFor('console')));
      const bar = await same('the steering bar', readSteer);
      assert.match(bar.caveat, /no write path into a session/);
      assert.equal(bar.maxlength, 500);
      return { label: bar.label };
    },
  );

  await step(
    'Console at project scope: the scope, the prompt, the rail, the setup line and the raw status',
    async () => {
      await both((o) => load(o, fragmentFor('console')));
      const read = await same('the Console', readConsole, {
        ready: () => document.querySelector('[data-next-rail-panel="delegation"]'),
      });
      assert.deepEqual(read.order, ['scope', 'prompt', 'rail', 'setup']);
      assert.deepEqual(
        read.rail.map((panel) => panel.name),
        ['delegation', 'waiting', 'capacity', 'tripwires'],
      );
      assert.match(read.setup.summary, /terminal bridge per-session, observer model off/);
      assert.equal(read.setup.open, false);
      assert.match(read.rail[0].text, /95%/);
      assert.match(read.rail[1].text, /Approve the retry plan\?/);
      return { delegation: read.rail[0].text.slice(0, 60) };
    },
  );

  await step(
    'Console with the terminal session selected: the terminal is operational, outside the setup',
    async () => {
      await both((o) => load(o, fragmentFor('console', BOARD.terminal)));
      const read = await same('the Console on the terminal session', readConsole, {
        ready: () => document.querySelector('[data-next-cockpit-terminal]'),
      });
      assert.deepEqual(read.order, ['scope', 'rail', 'terminal', 'setup']);
      assert.equal(read.terminal.inside, false);
      assert.match(read.setup.summary, /terminal bridge on, observer model off/);
      assert.deepEqual(read.scopeKind, [
        'session',
        `${BOARD.terminal.harness}:${BOARD.terminal.sid}`,
      ]);
    },
  );

  await step(
    'Console with a session that has no terminal: the terminal stays behind the closed setup',
    async () => {
      await both((o) => load(o, fragmentFor('console', BOARD.live)));
      const read = await same('the Console on a session with no terminal', readConsole, {
        ready: () => document.querySelector('details.next-cockpit-console-setup'),
      });
      assert.equal(read.terminal.inside, true);
      assert.match(read.setup.summary, /terminal bridge off/);
      assert.equal(read.setup.open, false);
    },
  );

  await step(
    'Console of a project with no working time: the figure is withheld, never zero',
    async () => {
      await both((o) => load(o, fragmentFor('console', null, BOARD.other)));
      const read = await same('the Console of beta/api', readConsole, {
        ready: () => document.querySelector('[data-next-rail-panel="delegation"]'),
      });
      assert.match(read.rail[0].text, /no figure yet/);
      assert.doesNotMatch(read.rail[0].text, /\b0%/);
      assert.match(read.rail[1].text, /Nothing in this project has asked for you\./);
    },
  );

  await step(
    'Decisions at project scope: the summary, the legend, each row’s rail and the unbound workers, under each filter',
    async () => {
      await both((o) => load(o, fragmentFor('decisions'), { wait: '.pc-semantic-timeline' }));
      const first = await same('Decisions', readDecisions);
      assert.match(first.summary, /Decision application/);
      assert.equal(first.mode, 'decisions');
      assert.ok(first.legend.length >= 2, 'the lane legend was not drawn');
      assert.ok(first.rows.every((row) => row.rail.length === first.legend.length));
      for (const name of ['All events', 'Active', 'Decisions']) {
        await both((o) => o.page.getByRole('button', { name, exact: true }).click());
        const next = await same(`Decisions under ${name}`, readDecisions);
        assert.equal(next.filter.find(([text]) => text === name)[1], 'true');
      }
      return { rows: first.rows.length, lanes: first.legend.length };
    },
  );

  await step('Decisions with a session selected reads that session’s context', async () => {
    await both((o) =>
      load(o, fragmentFor('decisions', BOARD.terminal), { wait: '.pc-semantic-timeline' }),
    );
    const read = await same('Decisions on the terminal session', readDecisions);
    assert.ok(read.rows.length > 0);
  });

  await step(
    'Course: the stage condition narrows with the selected session, in both pages',
    async () => {
      await both((o) => load(o, fragmentFor('course'), { wait: '.next-stage-conditions' }));
      const project = await same('Course at project scope', readCourse);
      assert.equal(project.cards.length, 1);
      await both((o) =>
        load(o, fragmentFor('course', BOARD.live), { wait: '.next-stage-conditions' }),
      );
      const inScope = await same('Course on a session of the workflow', readCourse);
      assert.equal(inScope.cards.length, 1);
      await both((o) =>
        load(o, fragmentFor('course', BOARD.gate), { wait: '.next-stage-conditions' }),
      );
      const outside = await same('Course on a session outside the workflow', readCourse);
      assert.equal(outside.cards.length, 0);
      assert.match(outside.fallback.join(' '), /Workflow stage source unavailable/);
    },
  );

  await step(
    'sending a steer draft records a receipt that says it was not delivered, in both pages',
    async () => {
      await both((o) => load(o, fragmentFor('console')));
      await both((o) =>
        o.page.locator('[data-next-draft="steer"]').fill('  take the safer route  '),
      );
      await both((o) => o.page.locator('[data-next-draft="steer"]').press('Enter'));
      const bar = await same('the bar after a send', readSteer);
      assert.equal(bar.value, '');
      assert.equal(bar.receipts.length, 1);
      assert.match(bar.receipts[0], /take the safer route.*Not delivered/);
    },
  );

  await step('a tripwire is added, toggled and persisted the same way in both pages', async () => {
    await both((o) => load(o, fragmentFor('console')));
    const focusOf = (o) =>
      o.page.evaluate(() => {
        const node = document.activeElement;
        return node
          ? `${node.tagName.toLowerCase()}:${(node.getAttribute('name') || node.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 40)}`
          : null;
      });
    await both((o) => o.page.getByRole('button', { name: '+ set a tripwire' }).click());
    const opened = await both(focusOf);
    await both((o) =>
      o.page.locator('[data-next-guardrail-input]').fill('alert me when the build breaks'),
    );
    await both((o) => o.page.locator('[data-next-guardrail-input]').press('Enter'));
    await sleep(patience(300));
    focusProbe.push({ opened, added: await both(focusOf) });
    await both((o) => o.page.getByRole('switch').first().click());
    const read = await same('the tripwires panel', readConsole);
    const panel = read.rail.find((section) => section.name === 'tripwires');
    assert.match(panel.text, /alert me when the build breaks/);
    assert.match(panel.text, /Disabled in this browser\./);
    const stored = await both((o) =>
      o.page.evaluate(() => {
        const key = `cargento.next.guardrails.${encodeURIComponent('alpha/app')}`;
        return globalThis.localStorage.getItem(key);
      }),
    );
    assert.equal(stored[0], stored[1], 'the two pages wrote different bytes');
    assert.deepEqual(JSON.parse(stored[1]), [
      { enabled: false, text: 'alert me when the build breaks' },
    ]);
  });

  await step(
    'Save, Rearm and Remove through the real route say the same things in both pages',
    async () => {
      await both((o) =>
        load(o, fragmentFor('course', BOARD.live), { wait: '.next-stage-conditions' }),
      );
      const act = async (action, expected) => {
        await both((o) => o.page.locator(`[data-stage-action="${action}"]`).click());
        await both((o) =>
          o.page.waitForFunction(
            (text) =>
              document.querySelector('.next-stage-conditions [role="status"]')?.textContent ===
              text,
            expected,
            { timeout: patience(15000) },
          ),
        );
        return same(`Course after ${action}`, readCourse);
      };
      await both((o) => o.page.locator('[data-stage-choice]').selectOption('review'));
      const saved = await act('save', 'Saved.');
      assert.match(saved.cards[0].lines.join(' '), /Saved stage: review/);
      const rearmed = await act('rearm', 'Rearmed; baseline reset.');
      assert.equal(rearmed.cards[0].cue, 'Rearmed; baseline reset.');
      const removed = await act('remove', 'Removed.');
      assert.equal(
        removed.cards[0].buttons.length,
        1,
        'Rearm and Remove should be gone with the rule',
      );
    },
  );

  /* =============================== BEHAVIOUR (React) =============================== */
  const mark = (selector, name) =>
    react.page.evaluate(
      ([sel, key]) => {
        globalThis[`__mark_${key}`] = document.querySelector(sel);
      },
      [selector, name],
    );
  const sameNode = (selector, name) =>
    react.page.evaluate(
      ([sel, key]) => globalThis[`__mark_${key}`] === document.querySelector(sel),
      [selector, name],
    );
  /* How many boards the page has taken in. The harness exposes its store; the shipped page exposes nothing, so the
     boards it was answered (`/api/data` responses that arrived) stand in. They are at least the boards it accepted. */
  const generatedOf = () =>
    SHIPPED
      ? react.answered()
      : react.page.evaluate(
          () => globalThis.__harness.shell.runtime.store.getSnapshot().acceptedCount,
        );
  const waitRevisions = async (count) => {
    const start = await generatedOf();
    const deadline = Date.now() + patience(40000);
    while ((await generatedOf()) < start + count) {
      if (Date.now() > deadline) throw new Error(`fewer than ${count} boards arrived`);
      await sleep(100);
    }
  };
  const refreshNow = () => refreshReact(react.page, SHIPPED);

  await step(
    'the steering box keeps its node, text, caret and native undo through revisions and a change of tab',
    async () => {
      await load(react, fragmentFor('console'));
      const box = react.page.locator('[data-next-draft="steer"]');
      await mark('[data-next-draft="steer"]', 'steer');
      await box.click();
      await react.page.keyboard.type('hello brave world');
      for (let i = 0; i < 5; i += 1) await react.page.keyboard.press('ArrowLeft');
      // One character is one undo step whatever the engine's typing coalescing does.
      await react.page.keyboard.type('X');
      await react.page.keyboard.press('ArrowLeft');
      await react.page.keyboard.press('Shift+ArrowLeft');
      await react.page.keyboard.press('Shift+ArrowLeft');
      const caret = await box.evaluate((node) => [
        node.selectionStart,
        node.selectionEnd,
        node.value,
      ]);
      await refreshNow();
      await waitRevisions(2);
      assert.equal(
        await sameNode('[data-next-draft="steer"]', 'steer'),
        true,
        'the box was replaced by a revision',
      );
      assert.deepEqual(
        await box.evaluate((node) => [node.selectionStart, node.selectionEnd, node.value]),
        caret,
      );
      assert.equal(
        await react.page.evaluate(() => document.activeElement?.getAttribute('data-next-draft')),
        'steer',
      );
      // A tab change unmounts the panel and nothing else: the bar is the project's, and the node stays.
      await react.page.keyboard.press('Tab');
      await react.page.getByRole('tab', { name: 'Decisions' }).click();
      await react.page.getByRole('tab', { name: 'Console' }).click();
      assert.equal(
        await sameNode('[data-next-draft="steer"]', 'steer'),
        true,
        'a change of tab replaced the box',
      );
      await box.focus();
      await react.page.keyboard.press(`${MOD}+z`);
      assert.equal(
        await box.inputValue(),
        'hello brave world',
        'native undo did not survive the revisions and the tab change',
      );
      return { undo: true };
    },
  );

  await step(
    'the steering box comes back with its text and caret after a route away and back',
    async () => {
      await load(react, fragmentFor('console'));
      const box = react.page.locator('[data-next-draft="steer"]');
      await box.click();
      await react.page.keyboard.type('draft for later');
      await react.page.keyboard.press('Home');
      for (let i = 0; i < 6; i += 1) await react.page.keyboard.press('ArrowRight');
      await react.page.keyboard.press('Shift+ArrowRight');
      await react.page.keyboard.press('Shift+ArrowRight');
      const before = await box.evaluate((node) => [
        node.selectionStart,
        node.selectionEnd,
        node.value,
      ]);
      await hashTo(react, '#n=sessions');
      await react.page.locator(AWAY).waitFor();
      await refreshNow();
      await hashTo(react, fragmentFor('console'));
      await react.page.locator('[data-next-draft="steer"]').waitFor();
      assert.deepEqual(
        await react.page
          .locator('[data-next-draft="steer"]')
          .evaluate((node) => [node.selectionStart, node.selectionEnd, node.value]),
        before,
      );
      await react.page.locator('[data-next-draft="steer"]').fill('');
      return { caret: before.slice(0, 2) };
    },
  );

  await step(
    'a draft is one project’s own: another project’s bar is another box with its own words',
    async () => {
      await load(react, fragmentFor('console'));
      const box = react.page.locator('[data-next-draft="steer"]');
      await box.click();
      await react.page.keyboard.type('alpha words');
      await mark('[data-next-draft="steer"]', 'alpha');
      await hashTo(react, fragmentFor('console', null, BOARD.other));
      await react.page.waitForFunction(
        ([project, shipped]) =>
          shipped
            ? (document.querySelector('nav[aria-label="Breadcrumb"]')?.textContent ?? '').includes(
                project,
              )
            : document.querySelector('#hosted')?.getAttribute('data-project') === project,
        [BOARD.other, SHIPPED],
      );
      const other = react.page.locator('[data-next-draft="steer"]');
      assert.equal(
        await other.inputValue(),
        '',
        'the other project’s box was given the first one’s words',
      );
      assert.equal(
        await sameNode('[data-next-draft="steer"]', 'alpha'),
        false,
        'the box node was reused for another project',
      );
      await other.click();
      await react.page.keyboard.type('beta words');
      await hashTo(react, fragmentFor('console'));
      await react.page.waitForFunction(
        ([project, shipped]) =>
          shipped
            ? (document.querySelector('nav[aria-label="Breadcrumb"]')?.textContent ?? '').includes(
                project,
              )
            : document.querySelector('#hosted')?.getAttribute('data-project') === project,
        [BOARD.project, SHIPPED],
      );
      assert.equal(
        await react.page.locator('[data-next-draft="steer"]').inputValue(),
        'alpha words',
      );
      await hashTo(react, fragmentFor('console', null, BOARD.other));
      await react.page.waitForFunction(
        ([project, shipped]) =>
          shipped
            ? (document.querySelector('nav[aria-label="Breadcrumb"]')?.textContent ?? '').includes(
                project,
              )
            : document.querySelector('#hosted')?.getAttribute('data-project') === project,
        [BOARD.other, SHIPPED],
      );
      assert.equal(
        await react.page.locator('[data-next-draft="steer"]').inputValue(),
        'beta words',
      );
      await react.page.locator('[data-next-draft="steer"]').fill('');
      await hashTo(react, fragmentFor('console'));
      await react.page.locator('[data-next-draft="steer"]').fill('');
    },
  );

  await step(
    'the tripwire box stays open for the tab with its words, and Escape cancels it without leaving the page',
    async () => {
      await load(react, fragmentFor('console'));
      await react.page.getByRole('button', { name: '+ set a tripwire' }).click();
      const input = react.page.locator('[data-next-guardrail-input]');
      await input.click();
      await react.page.keyboard.type('half a rule');
      await react.page.keyboard.press('ArrowLeft');
      await react.page.keyboard.press('ArrowLeft');
      const caret = await input.evaluate((node) => [node.selectionStart, node.value]);
      await react.page.getByRole('tab', { name: 'Decisions' }).click();
      await react.page.getByRole('tab', { name: 'Console' }).click();
      assert.deepEqual(await input.evaluate((node) => [node.selectionStart, node.value]), caret);
      await hashTo(react, '#n=sessions');
      await react.page.locator(AWAY).waitFor();
      await hashTo(react, fragmentFor('console'));
      await input.waitFor();
      assert.deepEqual(await input.evaluate((node) => [node.selectionStart, node.value]), caret);
      const route = await react.page.evaluate(() => globalThis.location.hash);
      await input.focus();
      await react.page.keyboard.press('Escape');
      assert.equal(
        await react.page.evaluate(() => globalThis.location.hash),
        route,
        'Escape left the page',
      );
      assert.equal(await react.page.locator('[data-next-guardrail-form]').count(), 0);
      await react.page.getByRole('button', { name: '+ set a tripwire' }).click();
      assert.equal(await input.inputValue(), '', 'the cancelled draft was offered back');
      await react.page.keyboard.press('Escape');
      return { stayed: route };
    },
  );

  await step(
    'tripwires written by an older build are read, and stay a note to oneself that nothing sends',
    async () => {
      const key = `cargento.next.guardrails.${E(BOARD.project)}`;
      await react.page.evaluate(
        ([k]) =>
          globalThis.localStorage.setItem(
            k,
            JSON.stringify(['an old string rule', { text: 'newer rule', enabled: false }]),
          ),
        [key],
      );
      await load(react, fragmentFor('console'));
      const sent = react.log.nonGet.length;
      const rows = await react.page.locator('[data-next-guardrail-toggle]').allTextContents();
      assert.deepEqual(
        rows.map((row) => row.replace(/\s+/g, ' ').trim()),
        ['◇an old string rule', '◇newer ruleDisabled in this browser.'],
      );
      await react.page.getByRole('switch').first().click();
      assert.equal(
        react.log.nonGet.length,
        sent,
        `a tripwire press sent a request: ${JSON.stringify(react.log.nonGet.slice(sent))}`,
      );
      await react.page.evaluate(([k]) => globalThis.localStorage.removeItem(k), [key]);
    },
  );

  await step(
    'no request but the board and its passive reads from a mount, a poll, a tab change or StrictMode',
    async () => {
      for (const strict of [true, false]) {
        const page = await newPage('react', { strict });
        await load(page, fragmentFor('console', BOARD.terminal));
        await page.page.waitForSelector('[data-next-cockpit-terminal]');
        for (const tab of ['Decisions', 'Course', 'Console', 'Decisions', 'Console']) {
          await page.page.getByRole('tab', { name: tab }).click();
          await sleep(patience(150));
        }
        await refreshReact(page.page, SHIPPED);
        await sleep(patience(400));
        assert.deepEqual(
          page.log.nonGet,
          [],
          `strict=${strict}: a request that was not a read: ${JSON.stringify(page.log.nonGet)}`,
        );
        // Anything under /api/ is one of the board's own reads; every other path is the page's own assets.
        const apis = new Set(
          page.log.requests
            .map((entry) => entry.path.split('?')[0])
            .filter((path) => path.startsWith('/api/')),
        );
        for (const path of apis) {
          assert.ok(
            [
              '/api/data',
              '/api/project-context',
              '/api/interaction/origin',
              '/api/stream',
            ].includes(path),
            `strict=${strict}: unexpected request ${path}`,
          );
        }
        assert.equal(page.requestsTo('/api/focus').length, 0);
        assert.equal(page.requestsTo('/api/reading').length, 0);
        assert.ok(!page.log.requests.some((entry) => entry.path.includes('observer_model=1')));
        assert.equal(
          page.stream().length,
          0,
          `strict=${strict}: the terminal opened a stream without a press`,
        );
        assert.deepEqual(page.log.consoleErrors, []);
        assert.deepEqual(page.log.pageErrors, []);
        await page.context.close();
      }
    },
  );

  await step(
    'a stage condition: one request per press, its choice and cue kept, and the native select stays',
    async () => {
      await load(react, fragmentFor('course', BOARD.live), { wait: '.next-stage-conditions' });
      const select = react.page.locator('[data-stage-choice]');
      await mark('[data-stage-choice]', 'choice');
      await select.selectOption('review');
      // A poll lands while the reader has the select: the node, its value and its focus stay.
      await select.focus();
      await refreshNow();
      await waitRevisions(1);
      assert.equal(
        await sameNode('[data-stage-choice]', 'choice'),
        true,
        'the select was replaced by a revision',
      );
      assert.equal(await select.inputValue(), 'review');
      await react.page.getByRole('tab', { name: 'Decisions' }).click();
      await react.page.getByRole('tab', { name: 'Course' }).click();
      assert.equal(
        await react.page.locator('[data-stage-choice]').inputValue(),
        'review',
        'the choice was lost with the tab',
      );
      const sent = react.log.nonGet.length;
      await react.page.locator('[data-stage-action="save"]').focus();
      await react.page.keyboard.press('Enter');
      await react.page.waitForFunction(
        () =>
          document.querySelector('.next-stage-conditions [role="status"]')?.textContent ===
          'Saved.',
        null,
        {
          timeout: patience(15000),
        },
      );
      assert.equal(
        react.log.nonGet.slice(sent).filter((entry) => entry.path === '/api/tripwire').length,
        1,
        'a press sent more than one request',
      );
      // Focus comes back to the control that was pressed once the card is drawn enabled again, and only then.
      await react.page.waitForFunction(
        () => document.activeElement?.getAttribute('data-stage-action') === 'save',
        null,
        {
          timeout: patience(8000),
        },
      );
      return { posts: 1 };
    },
  );

  await step(
    'a reader who moves on during a save is not pulled back to it, and one who stays is',
    async () => {
      const side = await newPage('react');
      await side.page.route('**/api/tripwire', async (route) => {
        await sleep(patience(900));
        await route.continue();
      });
      await load(side, fragmentFor('course', BOARD.live), { wait: '.next-stage-conditions' });
      const cueIs = (text) =>
        side.page.waitForFunction(
          (expected) =>
            document.querySelector('.next-stage-conditions [role="status"]')?.textContent ===
            expected,
          text,
          { timeout: patience(15000) },
        );
      // Staying: the keyboard press that started the save, and nothing since.
      await side.page.locator('[data-stage-action="save"]').focus();
      await side.page.keyboard.press('Enter');
      await cueIs('Saved.');
      await side.page.waitForFunction(
        () => document.activeElement?.getAttribute('data-stage-action') === 'save',
        null,
        { timeout: patience(8000) },
      );
      // Moving on: a press on the page while the request is out.
      await side.page.locator('[data-stage-action="rearm"]').focus();
      await side.page.keyboard.press('Enter');
      await side.page.mouse.click(2, 2);
      await cueIs('Rearmed; baseline reset.');
      await sleep(patience(400));
      const where = await side.page.evaluate(() => document.activeElement?.tagName.toLowerCase());
      assert.equal(where, 'body', 'the page took focus back after the reader moved on');
      await side.context.close();
    },
  );

  await step('a refusal is said where the reader reads it, and nothing is retried', async () => {
    // A second page changes the rule underneath the first, so the first's revision is stale.
    const other = await newPage('react');
    await load(other, fragmentFor('course', BOARD.live), { wait: '.next-stage-conditions' });
    await load(react, fragmentFor('course', BOARD.live), { wait: '.next-stage-conditions' });
    await other.page.locator('[data-stage-choice]').selectOption('done');
    await other.page.locator('[data-stage-action="save"]').click();
    await other.page.waitForFunction(
      () =>
        document.querySelector('.next-stage-conditions [role="status"]')?.textContent === 'Saved.',
    );
    await other.context.close();
    const sent = react.log.nonGet.length;
    // The first page still shows the revision it drew; pressing Rearm names that one.
    await react.page.locator('[data-stage-action="rearm"]').click();
    await react.page.waitForFunction(
      () => {
        const text =
          document.querySelector('.next-stage-conditions [role="status"]')?.textContent ?? '';
        return text !== '' && text !== 'Saving…';
      },
      null,
      { timeout: patience(15000) },
    );
    const cue = await react.page.locator('.next-stage-conditions [role="status"]').textContent();
    assert.ok(cue.length > 0);
    await sleep(patience(300));
    assert.equal(
      react.log.nonGet.slice(sent).filter((entry) => entry.path === '/api/tripwire').length,
      1,
      'the refused press was retried',
    );
    return { cue };
  });

  await step(
    'the Console’s setup disclosure stays as the reader left it, per session, across polls and tabs',
    async () => {
      await load(react, fragmentFor('console', BOARD.live));
      const setup = react.page.locator('details.next-cockpit-console-setup');
      await setup.waitFor();
      await setup.locator('> summary').click();
      assert.equal(await setup.evaluate((node) => node.open), true);
      await refreshNow();
      await waitRevisions(1);
      assert.equal(await setup.evaluate((node) => node.open), true, 'a poll shut the setup');
      await react.page.getByRole('tab', { name: 'Decisions' }).click();
      await react.page.getByRole('tab', { name: 'Console' }).click();
      assert.equal(
        await react.page
          .locator('details.next-cockpit-console-setup')
          .evaluate((node) => node.open),
        true,
        'a tab change shut the setup',
      );
      await hashTo(react, fragmentFor('console', BOARD.gate));
      await react.page.locator('details.next-cockpit-console-setup').waitFor();
      assert.equal(
        await react.page
          .locator('details.next-cockpit-console-setup')
          .evaluate((node) => node.open),
        false,
        'another session shares the first’s disclosure',
      );
      await hashTo(react, fragmentFor('console', BOARD.live));
      await react.page.locator('details.next-cockpit-console-setup').waitFor();
      assert.equal(
        await react.page
          .locator('details.next-cockpit-console-setup')
          .evaluate((node) => node.open),
        true,
      );
    },
  );

  await step(
    'the retained terminal keeps one screen and one socket across tab switches, with no frame sent',
    async () => {
      const side = await newPage('react');
      await load(side, fragmentFor('console', BOARD.terminal));
      await side.page.getByRole('button', { name: 'Open terminal', exact: true }).click();
      await side.page.waitForSelector('#pc-terminal-screen .xterm, #pc-terminal-viewport .xterm', {
        timeout: patience(20000),
      });
      await side.page.evaluate(() => {
        globalThis.__screen = document.getElementById('pc-terminal-screen');
      });
      await appendFile(
        world.react.control,
        `${JSON.stringify({ text: 'printed before leaving\r\n' })}\n`,
      );
      await side.page.waitForFunction(
        () => document.body.innerText.includes('printed before leaving'),
        null,
        { timeout: patience(15000) },
      );
      for (const tab of ['Decisions', 'Course', 'Console']) {
        await side.page.getByRole('tab', { name: tab }).click();
        await sleep(patience(200));
      }
      await appendFile(
        world.react.control,
        `${JSON.stringify({ text: 'printed while away\r\n' })}\n`,
      );
      /* A terminal the page has scrolled out of view draws nothing: xterm pauses its renderer while it is off screen
         and repaints when it returns, which is its design and not a lost frame. The shipped page is taller than the
         harness, so coming back from another tab can leave the terminal below the fold; the reader scrolls to it. */
      await side.page.locator('#pc-terminal-viewport').scrollIntoViewIfNeeded();
      await side.page.waitForFunction(
        () => document.body.innerText.includes('printed while away'),
        null,
        { timeout: patience(15000) },
      );
      assert.equal(
        await side.page.evaluate(
          () => globalThis.__screen === document.getElementById('pc-terminal-screen'),
        ),
        true,
        'the console drew a different screen after a change of tab',
      );
      assert.equal(side.stream().length, 1, 'a change of tab opened another socket');
      assert.deepEqual(side.stream()[0].sent, [], 'the page sent a frame on the read-only stream');
      await side.context.close();
    },
  );

  await step(
    'the waiting session’s controls name the exact session, and a copy sends no request',
    async () => {
      const side = await newPage('react');
      await load(side, fragmentFor('console'));
      const card = side.page.locator('[data-next-wait-session="gate-open"]');
      await card.waitFor();
      side.log.requests.length = 0;
      await card.getByRole('button', { name: /Copy re-entry command/ }).click();
      assert.deepEqual(await side.page.evaluate(() => globalThis.__copied), [
        'claude --resume gate-open',
      ]);
      const href = await card.locator('a').getAttribute('href');
      assert.equal(href, `#n=session:${E(BOARD.project)}:claude:gate-open`);
      assert.deepEqual(side.log.nonGet, []);
      await side.context.close();
    },
  );

  const NARROW = [
    ['320', { width: 320, height: 800 }],
    ['375', { width: 375, height: 800 }],
    ['640 (200% zoom of 1280)', { width: 640, height: 800 }],
    ['1280', { width: 1280, height: 900 }],
  ];
  for (const [label, viewport] of NARROW) {
    await step(
      `at ${label} px the Console and Decisions tabs draw with no horizontal page scroll`,
      async () => {
        const side = await newPage('react', { viewport });
        for (const [tab, focus] of [
          ['console', BOARD.terminal],
          ['console', null],
          ['decisions', null],
          ['course', BOARD.live],
          ['console', BOARD.live],
        ]) {
          await load(side, fragmentFor(tab, focus));
          await settled(() =>
            side.page.evaluate(
              () => document.querySelector('[data-next-cockpit-panel]')?.textContent.length ?? 0,
            ),
          );
          // The window's own size, then the reader's text at twice the size: a rail that fits at one and
          // not the other is the defect this step exists to catch, and the widest element is named.
          for (const scale of ['100%', '200%']) {
            await side.page.evaluate((fontSize) => {
              document.documentElement.style.fontSize = fontSize;
            }, scale);
            const wide = await side.page.evaluate(() => {
              const root = document.documentElement;
              const past = [...document.querySelectorAll('body *')]
                .filter((node) => node.getBoundingClientRect().right > root.clientWidth + 0.5)
                .slice(0, 3)
                .map(
                  (node) => `${node.tagName.toLowerCase()}.${String(node.className).slice(0, 40)}`,
                );
              return { scroll: root.scrollWidth, client: root.clientWidth, past };
            });
            assert.ok(
              wide.scroll <= wide.client,
              `${tab}${focus ? ' (session)' : ''} at ${label}, text ${scale}: page scrolls horizontally (${wide.scroll} > ${wide.client}) at ${wide.past.join(', ')}`,
            );
          }
          await side.page.evaluate(() => {
            document.documentElement.style.fontSize = '';
          });
        }
        await load(side, fragmentFor('console', BOARD.terminal));
        await settled(() =>
          side.page.evaluate(
            () =>
              document.querySelector('[data-next-rail-panel="tripwires"]')?.textContent.length ?? 0,
          ),
        );
        await mkdir(SHOTS, { recursive: true });
        const file = `${SHOTS}console-react-${label.split(' ')[0]}px.png`;
        await side.page.screenshot({ path: file, fullPage: true });
        shots.push(file);
        for (const [name, tab, focus, ready] of [
          ['decisions', 'decisions', null, '.pc-lane-legend'],
          ['course', 'course', BOARD.live, '.next-stage-rule'],
        ]) {
          await load(side, fragmentFor(tab, focus), { wait: ready, state: 'attached' });
          await settled(() =>
            side.page.evaluate(
              () => document.querySelector('[data-next-cockpit-panel]')?.textContent.length ?? 0,
            ),
          );
          const shot = `${SHOTS}console-react-${name}-${label.split(' ')[0]}px.png`;
          await side.page.screenshot({ path: shot, fullPage: true });
          shots.push(shot);
        }
        await side.context.close();
      },
    );
  }

  await step(
    'typography and geometry match the legacy page on the shipped project page, at 375 and 1280',
    async () => {
      // The harness has no page chrome around its panels, so the boxes are compared in the shipped page.
      const real = await startConsoleWorld({ harness: false });
      try {
        const realOrigins = [real.react.origin, real.react.viteOrigin, real.legacy.origin];
        const SEL = {
          caveat: '.next-steer-caveat',
          label: '.next-steer-label',
          input: '.next-steer input',
          meta: '.next-rail-meta--amber',
          add: '.next-guardrail-add',
          summary: '.next-cockpit-decision-summary',
          event: '.pc-timeline-event',
          eventSummary: '.pc-timeline-event > summary',
          trailSummary: '.pc-trail-summary',
          top: '.pc-trail-top',
          topMeta: '.pc-trail-top > span',
          result: '.pc-trail-result',
          row: '.pc-graph-row',
        };
        const PROPS = [
          'letterSpacing',
          'fontSize',
          'fontWeight',
          'lineHeight',
          'color',
          'textAlign',
        ];
        const read = ({ sel, props }) => {
          const out = {};
          for (const [name, selector] of Object.entries(sel)) {
            const node = document.querySelector(selector);
            if (!node) continue;
            const style = getComputedStyle(node);
            const box = node.getBoundingClientRect();
            const parent = node.parentElement.getBoundingClientRect();
            out[name] = {
              ...Object.fromEntries(props.map((prop) => [prop, style[prop]])),
              width: box.width,
              height: box.height,
              // Where it sits inside what holds it, so the page chrome around both does not matter.
              rightGap: Math.round(parent.right - box.right),
            };
          }
          return out;
        };
        const cases = [];
        for (const width of [1280, 375]) {
          for (const [tab, ready] of [
            ['console', '[data-next-rail-panel=tripwires]'],
            ['decisions', '.pc-graph-row'],
          ]) {
            const pair = {};
            for (const kind of ['legacy', 'react']) {
              const o = await openTracked(browser, realOrigins, {
                viewport: { width, height: 900 },
              });
              await o.page.goto(
                `${kind === 'legacy' ? real.legacy.origin : real.react.origin}/${fragmentFor(tab)}`,
              );
              await o.page.waitForSelector(ready, { timeout: patience(30000) });
              pair[kind] = await settled(() => o.page.evaluate(read, { sel: SEL, props: PROPS }));
              await o.context.close();
            }
            const diffs = [];
            for (const name of Object.keys(pair.legacy)) {
              for (const [prop, was] of Object.entries(pair.legacy[name])) {
                const now = pair.react[name]?.[prop];
                const number = typeof was === 'number';
                // A width can differ by the shared chevron's own column and a wrap by a pixel; a typeface,
                // a spacing, a height or a side the text sits against cannot.
                const slack = prop === 'width' ? 16 : 1.5;
                if (number ? Math.abs(was - now) > slack : was !== now)
                  diffs.push(`${name}.${prop}: legacy ${was}, react ${now}`);
              }
            }
            cases.push({ width, tab, diffs });
          }
        }
        const bad = cases.filter((entry) => entry.diffs.length);
        assert.deepEqual(
          bad,
          [],
          `typography or geometry drifted from the legacy page: ${JSON.stringify(bad).slice(0, 1500)}`,
        );
        return { compared: cases.length };
      } finally {
        await real.close();
      }
    },
  );

  await step('the Console can be operated from the keyboard alone', async () => {
    const side = await newPage('react');
    await load(side, fragmentFor('console', BOARD.terminal));
    await side.page.waitForSelector('[data-next-cockpit-terminal]');
    // The tab strip's arrow keys move between tabs and keep focus on the new one.
    await side.page.getByRole('tab', { name: 'Console' }).focus();
    await side.page.keyboard.press('ArrowLeft');
    assert.equal(
      await side.page.evaluate(() => document.activeElement?.getAttribute('data-arg')),
      'decisions',
    );
    await side.page.keyboard.press('ArrowRight');
    await side.page.waitForSelector('[data-next-cockpit-panel="console"]');
    // Every control in the rail and the terminal section is reachable by Tab, in document order.
    const reached = [];
    await side.page.locator('[data-next-rail-panel="tripwires"] button').first().focus();
    for (let i = 0; i < 4; i += 1) {
      reached.push(
        await side.page.evaluate(() =>
          document.activeElement?.textContent?.replace(/\s+/g, ' ').trim(),
        ),
      );
      await side.page.keyboard.press('Tab');
    }
    assert.ok(
      reached.some((text) => /set a tripwire/.test(text ?? '')),
      `the add control is not in the tab order: ${JSON.stringify(reached)}`,
    );
    // The add control opens its box on Enter, the box takes a rule on Enter and gives focus back.
    await side.page.getByRole('button', { name: '+ set a tripwire' }).focus();
    await side.page.keyboard.press('Enter');
    await side.page.locator('[data-next-guardrail-input]').waitFor();
    // The box takes focus as it opens, so a keyboard reader can type at once.
    await side.page.waitForFunction(
      () => document.activeElement?.hasAttribute('data-next-guardrail-input'),
      null,
      { timeout: patience(5000) },
    );
    await side.page.keyboard.type('keyboard rule');
    await side.page.keyboard.press('Enter');
    await side.page.waitForFunction(
      () => document.activeElement?.textContent?.includes('set a tripwire'),
      null,
      { timeout: patience(5000) },
    );
    assert.equal(await side.page.locator('[data-next-guardrail-toggle]').count(), 1);
    await side.page.evaluate(() => globalThis.localStorage.clear());
    await side.context.close();
  });
} finally {
  await Promise.all(opened.map((o) => o.context.close().catch(() => undefined)));
  await browser.close();
  await world.close();
}

console.log(JSON.stringify({ receipts, shots, focusProbe }, null, 2));
if (failures.length) {
  for (const failure of failures) console.error(`\nFAILED: ${failure.name}\n${failure.message}`);
  process.exit(1);
}
