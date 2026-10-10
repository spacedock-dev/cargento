/* global document, getComputedStyle -- used inside page.evaluate, which runs in the browser */
/*
 * The Drift section, Analyze, its result, Steer back and the departures in a real browser.
 *
 * Two kinds of proof. The DIFFERENTIAL half drives the React page over one scripted board (`drift-board.mjs`: the
 * real document and modules, the Drift fields and the routes that could reach a model replaced) and compares what a
 * reader can read, in each state a reader reaches, with what the previous interface showed there: no reading, a
 * refusal, an Allow owed, a running analysis, a cancel, a stored result, a withheld one, a reading this build cannot
 * read, a superseded one, a gap in the record, the lane off and on. The BEHAVIOUR half holds the React page to what a
 * unit test cannot see: the correction box's node, text, caret, selection, native undo and input-method composition
 * surviving the board's own revisions, a route away and back and a pointer on its way to a control; request counts
 * over a mount, a poll, a route change, a hover, a focus and a keypress; keyboard operation; the announcements
 * through the runtime's live regions; and 320/375/640(200% zoom)/1280 CSS px layouts with no horizontal page scroll.
 *
 * What the previous interface said is a RECORDING (`support/golden.mjs`, `frontend/test/golden/e2e/drift-parity.json`)
 * that cannot be remade because that interface is gone. Each state is scripted onto the React page and what it reads
 * is held to the recording. Every assertion that compared the two pages (the consent step's request count, the copies
 * and the copy requests of Steer back) is a recorded observation asserted against the React page's own.
 *
 * No model is ever called: the reading route is a double. Every request leaving the board's own origins is
 * refused. Run with `pnpm test:drift:browser`; `CARGENTO_E2E_STEPS=<regex>` runs only the steps whose name
 * matches.
 */
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';
import {
  ASSESSMENT,
  HARNESS,
  POLICY,
  RECORD,
  ROUTE,
  SAVED,
  SID,
  UNCONSENTED,
  check,
  fact,
  freshScript,
  installScript,
  postsTo,
} from './drift-board.mjs';
import { call, startIntentBoard } from './intent-board.mjs';
import { instrumentResources, recordClipboard, resources } from './sessions-board.mjs';
import { openPage } from './support/browser.mjs';
import { goldenFor, jsonSafe, normalise } from './support/golden.mjs';

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
const golden = goldenFor('drift-parity');
/* The React reading in the stable form a recorded observation has, so the two compare as plain data. */
const norm = (value) => jsonSafe(normalise(value));
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
const FRAGMENT = `#n=session:${E('w/alpha')}:${HARNESS}:${E(SID)}`;
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/* ---- what a reader can read, reduced to data. These run IN the page, so they are self-contained. ---- */
const summarizeCard = () => {
  const norm = (node) => (node ? node.textContent.replace(/\s+/g, ' ').trim() : '');
  const card = document.querySelector('.next-session-drift');
  if (!card) return { missing: true, body: norm(document.body).slice(0, 200) };
  const button = (b) => [
    norm(b),
    b.getAttribute('data-next-cockpit-action') || '',
    b.getAttribute('aria-disabled') === 'true',
    b.getAttribute('aria-pressed'),
    b.hidden,
  ];
  return {
    heading: norm(card.querySelector('h2')),
    text: norm(card),
    buttons: [...card.querySelectorAll('button')]
      .filter((b) => !b.closest('.next-cockpit-held'))
      .map(button),
    resultStates: [...card.querySelectorAll('[data-next-result-state]')].map(
      (node) => node.dataset.nextResultState,
    ),
    steps: [...card.querySelectorAll('.next-cockpit-reading-step')].map((node) => [
      node.dataset.state,
      node.getAttribute('aria-current'),
    ]),
    analyzing: [...card.querySelectorAll('[data-next-analyzing]')].map(
      (node) => node.dataset.nextAnalyzing,
    ),
    absences: [...card.querySelectorAll('[data-absence]')].map((node) => [
      node.dataset.absence,
      norm(node),
    ]),
    stale: [...card.querySelectorAll('[data-next-result-stale]')].map(
      (node) => node.dataset.nextResultStale,
    ),
    delivery: [...card.querySelectorAll('[data-next-delivery]')].map((node) => [
      node.dataset.nextDelivery,
      node.dataset.nextDeliveryMixed || '',
    ]),
    levels: [...card.querySelectorAll('.next-session-drift-seg[data-on]')].length,
    pill: norm(document.querySelector('[data-next-drift-pill]')),
    work: norm(document.querySelector('[data-next-cockpit-work]')),
    entries: [...document.querySelectorAll('[data-next-entry]')].map((node) => [
      node.dataset.nextEntry,
      node.dataset.nextEntryId,
    ]),
    meta: norm(document.querySelector('.next-session-detail-meta')),
  };
};

/* A duration, a clock time and a fact id differ between two loads a moment apart, and say the same
   thing about the reader's words either way. */
const comparable = (value) =>
  JSON.stringify(value)
    // Ids first: a hex id can hold a digit followed by d, which the age pattern below would otherwise take.
    .replace(/fact:[0-9a-f]{16}/g, '<fact>')
    // A call's moment is printed whole, with its date and seconds, and a recording must not carry the day it was made.
    .replace(/\d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC/g, '<instant>')
    // No word boundary before the digits: a list row prints "exact" and its age with nothing between.
    .replace(/(?<!\d)\d+[smhd]( \d+[smh])?(?![A-Za-z0-9])/g, '<age>')
    .replace(/(?<!\d)\d\d:\d\d(?!\d)/g, '<clock>');

async function settled(read, { deadline = patience(6000), every = 120 } = {}) {
  let previous = comparable(await read());
  const until = Date.now() + deadline;
  for (;;) {
    await sleep(every);
    const next = comparable(await read());
    if (next === previous) return JSON.parse(next);
    previous = next;
    if (Date.now() > until) throw new Error('The page kept changing: ' + next.slice(0, 300));
  }
}

const board = await startIntentBoard();
const browser = await chromium.launch();
const origins = [board.react.origin, board.react.viteOrigin];
const opened = [];

async function newPage(viewport = { width: 1280, height: 900 }) {
  const o = await openPage(browser, origins, { viewport });
  await o.context.addInitScript(() => {
    globalThis.__announced = [];
  });
  await recordClipboard(o.context);
  await instrumentResources(o.context);
  o.script = freshScript();
  await installScript(o.context, o.script);
  opened.push(o);
  return o;
}

async function load(o, fragment = FRAGMENT) {
  await o.page.goto('about:blank');
  await o.page.goto(`${board.react.origin}/${fragment}`);
  await o.page.waitForFunction(
    () =>
      document.querySelector('nav[aria-label="Primary"]') &&
      !/Waiting for the first board|first payload has not arrived/.test(document.body.innerText),
  );
  await o.page.waitForSelector('.next-session-drift');
}

/* The real board's own clock, so every time in a state is relative to it. */
async function clockOf() {
  const real = await (await fetch(`${board.react.origin}/api/data`)).json();
  return real.generated;
}

async function setState(o, make) {
  const next = freshScript();
  Object.assign(next, await make(o));
  for (const key of Object.keys(o.script)) delete o.script[key];
  Object.assign(o.script, next);
}

try {
  const react = await newPage();
  const read = (o) => settled(() => o.page.evaluate(summarizeCard));

  /* ===================== DIFFERENTIAL: the card, state by state ===================== */
  async function compare(label, make, { text = true, ready = null } = {}) {
    const old = golden.observe(`card: ${label}`);
    const recordUnread = /has not been read yet|record is unread rather than empty/.test(old.work);
    const g = await clockOf();
    await setState(react, (o) => make(g, o));
    const draw = async (o) => {
      await load(o);
      // A state the page reaches after a record read, said by what it draws rather than by a delay.
      if (ready) await o.page.waitForSelector(ready, { timeout: patience(15000) });
      // Two identical unread frames can precede the context response. The golden's scan gap and
      // annotations-off states really are unread, so only the recorded read states await the record.
      if (!recordUnread)
        await o.page.waitForFunction(
          () => {
            const work = document.querySelector('[data-next-cockpit-work]');
            return (
              work?.querySelector('[data-next-entry]') ||
              work?.textContent.includes('No entry in the observed record names this session.')
            );
          },
          undefined,
          { timeout: patience(15000) },
        );
      return read(o);
    };
    const mine = norm(await draw(react));
    for (const key of Object.keys(old)) {
      if (!text && key === 'text') continue;
      if (typeof old[key] === 'string' && typeof mine[key] === 'string' && old[key] !== mine[key]) {
        let at = 0;
        while (old[key][at] === mine[key][at]) at += 1;
        assert.fail(
          `the card differs from the recorded card in ${key} (${label}) at ${at}: recorded ${JSON.stringify(old[key].slice(Math.max(0, at - 60), at + 120))} / react ${JSON.stringify(mine[key].slice(Math.max(0, at - 60), at + 120))}`,
        );
      }
      assert.deepEqual(
        mine[key],
        old[key],
        `the card differs from the recorded card in ${key} (${label})`,
      );
    }
    return old;
  }

  const claude = (g, extra = {}) => ({
    // The real board's own eligibility is cleared: the backend has no reading model, so it says Analyze is closed.
    session: {
      ...SAVED(g),
      state: 'idle',
      turn_end_at: g - 200,
      reading_eligibility: undefined,
      ...(extra.session || {}),
    },
    payload: {
      reading: POLICY,
      reading_routes: { claude: ROUTE },
      reading_check: 'accepted',
      reading_jobs: {},
      ...(extra.payload || {}),
    },
    facts: extra.facts ?? [],
    work: extra.work ?? {},
    routes: extra.routes ?? {},
    contextError: extra.contextError ?? false,
  });

  await step('no reading: Analyze is offered, with what is sent one click away', async () => {
    const state = await compare('no reading', (g) => claude(g));
    assert.ok(state.buttons.some(([label]) => label === 'Analyze drift'));
    assert.match(state.text, /What is sent/);
    return state.buttons.map(([label]) => label);
  });

  await step(
    'a refusal is said under the control that was pressed, in the recorded sentence',
    async () => {
      const state = await compare('model off', (g) =>
        claude(g, { payload: { reading: { reason: 'run-disabled', used: 0, limit: 10 } } }),
      );
      assert.match(state.text, /Model calls are off for this run/);
      assert.equal(
        state.absences.some(([kind]) => kind === 'run-config'),
        true,
      );
    },
  );

  await step(
    'an Allow is owed: Analyze offers the receiver one click away and sends nothing',
    async () => {
      const state = await compare('allow owed', (g) =>
        claude(g, { payload: { reading: UNCONSENTED } }),
      );
      assert.match(state.text, /What is sent to Claude Code/);
    },
  );

  await step('no reader on this machine: the reason stands where the button would be', async () => {
    const state = await compare('no reader', (g) =>
      claude(g, {
        payload: {
          reading_routes: { claude: { provider: '', note: 'No claude binary was found.' } },
        },
      }),
    );
    assert.match(state.text, /No claude binary was found\./);
    assert.ok(!state.buttons.some(([label]) => label === 'Analyze drift'));
  });

  const JOB = (g, extra = {}) => ({
    id: 'job-1',
    phase: 'read',
    steps: [
      { phase: 'collect', text: 'Collecting the record' },
      { phase: 'read', text: 'Reading it' },
      { phase: 'write', text: 'Writing the result' },
    ],
    ...extra,
  });

  await step(
    'a running analysis draws its steps and Cancel; a cancelling one keeps Cancel inert',
    async () => {
      const running = await compare('running', (g) =>
        claude(g, {
          session: { state: 'working' },
          payload: { reading_jobs: { [`${HARNESS}:${SID}`]: JOB(g) } },
        }),
      );
      assert.deepEqual(
        running.steps.map(([s]) => s),
        ['done', 'active', 'todo'],
      );
      assert.deepEqual(running.analyzing, ['job-1']);
      const cancelling = await compare('cancelling', (g) =>
        claude(g, {
          session: { state: 'working' },
          payload: { reading_jobs: { [`${HARNESS}:${SID}`]: JOB(g, { cancelling: true }) } },
        }),
      );
      assert.ok(cancelling.buttons.some(([label, , inert]) => label === 'Cancel' && inert));
    },
  );

  const stored = (g, extra = {}) =>
    claude(g, {
      ...extra,
      session: {
        annotation_assessment: ASSESSMENT(g),
        annotation_reading_count: 1,
        ...(extra.session || {}),
      },
      facts: extra.facts ?? RECORD(g),
    });

  await step(
    'a stored result: the answer, each line by the list’s number, where the work went',
    async () => {
      const state = await compare('stored result', (g) => stored(g));
      assert.match(state.text, /Departs from your intent1 departure/);
      // Sorted as a copy: a golden observation is the stored value itself, and sorting it would change the recording.
      assert.deepEqual([...state.resultStates].sort(), ['consistent', 'departs']);
      assert.ok(state.entries.length >= 2);
      assert.ok(state.buttons.some(([label]) => label === 'Analyze again'));
      return state.resultStates;
    },
  );

  await step('a result marked not accurate draws marked, and a withheld one says why', async () => {
    const marked = await compare('not accurate', (g) =>
      stored(g, { session: { annotation_not_accurate: true } }),
    );
    assert.match(marked.text, /You marked this analysis not accurate/);
    const withheld = await compare('withheld', (g) =>
      claude(g, {
        session: {
          annotation_reading_withheld: 'The analysis was cancelled.',
          annotation_reading_withheld_at: g - 120,
          annotation_reading_count: 1,
        },
      }),
    );
    assert.match(withheld.text, /Last analysis, .* ago: The analysis was cancelled\./);
  });

  await step(
    'a reading this build cannot read, and one it refused, say so and draw no verdict',
    async () => {
      const odd = await compare('unknown field', (g) =>
        stored(g, { session: { annotation_assessment: ASSESSMENT(g, { surprise: true }) } }),
      );
      assert.match(odd.text, /cannot read the reading it was given/);
      assert.deepEqual(odd.resultStates, []);
      const refused = await compare('refused', (g) =>
        claude(g, { session: { annotation_reading_refused: true, annotation_reading_count: 1 } }),
      );
      assert.match(refused.text, /this build could not read it/);
    },
  );

  await step(
    'a reading of earlier words says so, and offers Analyze again in the callout',
    async () => {
      const state = await compare('superseded', (g) =>
        stored(g, { session: { annotation_revision: 4, annotation_revision_count: 4 } }),
      );
      assert.deepEqual(state.stale, ['intent']);
      assert.match(state.text, /Revision 4 is current/);
      const work = await compare('new work', (g) =>
        stored(g, {
          facts: [
            ...RECORD(g),
            check('c3', g - 100, 'passed'),
            fact('m1', g - 90, { type: 'agent_message', by: 'agent' }),
          ],
        }),
      );
      assert.deepEqual(work.stale, ['work']);
    },
  );

  await step('a gap in the record is said as a gap, never as an empty record', async () => {
    /* The previous interface and this page both say the record is absent, in the words of what happened. It read
       only the focused session's context, so its failure left the record "not read yet"; this page also reads the
       project's (the Intent step does, for its later directions), so the same failure is "could not be read".
       Neither is an empty record. */
    const g0 = await clockOf();
    await setState(react, () => claude(g0, { contextError: true }));
    await load(react);
    const unreadReact = norm(await read(react));
    const unreadRecorded = golden.observe('gap: the record could not be read');
    const unread = [unreadRecorded, unreadReact];
    assert.match(unread[0].work, /has not been read yet/);
    assert.match(unread[1].work, /could not be read/);
    assert.ok(
      unread.every(
        (state) => !/No entry in the observed record names this session/.test(state.work),
      ),
    );
    const partial = await compare('outside the scan', (g) =>
      claude(g, {
        work: {
          omitted: [{ harness: HARNESS, sid: SID }],
        },
      }),
    );
    assert.match(partial.work, /outside the observed-record scan/);
  });

  await step(
    'the departures section: lane on and off, raises on record, delivery and counts',
    async () => {
      const row = (g) => ({
        constraint: 'TYPED GOAL',
        at: g - 400,
        clause: 'Ship the queue worker',
        reading: 'It stopped running the tests.',
        revision: 2,
        cutoff: g - 380,
        evidence: 'pytest failed',
      });
      const raised = await compare('raises', (g) =>
        claude(g, {
          payload: { unasked: true, delivery_counts: { raises: 3, attempted: 3, handed_over: 2 } },
          session: {
            departures: [row(g)],
            departure_checked: true,
            delivery_departure: {
              delivery_raises: 1,
              delivery_outcome: 'handed-over',
              delivery_why: 'A notification service accepted it.',
            },
          },
        }),
      );
      assert.match(raised.text, /Raised while you were away: 1/);
      assert.deepEqual(raised.delivery, [['handed-over', '']]);
      const off = await compare('lane off', (g) =>
        claude(g, {
          payload: { unasked: false, unasked_off_reason: 'run-disabled' },
          session: { departures: [row(g)] },
        }),
      );
      assert.match(off.text, /model off switch refuses unasked checks/);
      const checked = await compare('lane on, nothing raised', (g) =>
        claude(g, {
          payload: { unasked: true },
          session: { departures: [], departure_why: 'Not checked yet.' },
        }),
      );
      assert.match(checked.text, /Not checked yet\./);
    },
  );

  await step(
    'a later direction is asked about before the press, with Analyze behind Keep',
    async () => {
      const state = await compare('question', (g) =>
        claude(g, {
          facts: [fact('d1', g - 100, { summary: 'Keep the flag off by default.' })],
          session: { annotation_goal_saved_at: g - 600 },
        }),
      );
      assert.ok(state.buttons.some(([label]) => label === 'Keep my intent and analyze'));
      assert.ok(!state.buttons.some(([label]) => label === 'Analyze drift'));
      const owed = await compare('question, an Allow owed', (g) =>
        claude(g, {
          payload: { reading: UNCONSENTED },
          facts: [fact('d1', g - 100, { summary: 'Keep the flag off by default.' })],
        }),
      );
      assert.ok(owed.buttons.some(([label]) => label === 'Keep my intent'));
    },
  );

  await step(
    'with annotations off the check stays on the page, inert, with its one refusal',
    async () => {
      const state = await compare('annotations off', (g) =>
        claude(g, { payload: { annotate: false, reading_check: 'not-run' } }),
      );
      assert.match(state.text, /Annotations are off for this run/);
    },
  );

  await step(
    'pressing Analyze where an Allow is owed asks for it, naming the receiver, and sends nothing',
    async () => {
      const g = await clockOf();
      await setState(react, () => claude(g, { payload: { reading: UNCONSENTED } }));
      await load(react);
      await react.page.locator('[data-next-cockpit-action="reading-ask"]').click();
      const old = golden.observe('consent: the step');
      const mine = norm(await read(react));
      assert.deepEqual(mine, old, 'the consent step differs from the recorded step');
      assert.match(old.text, /Send this session to Claude Code for analysis\?/);
      assert.deepEqual(
        old.buttons.filter(([label]) => ['Allow and analyze', 'Not now'].includes(label)).length,
        2,
      );
      const recordedSent = golden.observe('consent: reading requests the legacy page sent');
      assert.equal(recordedSent + postsTo(react.script, '/api/reading').length, 0);
      await react.page.locator('[data-next-cockpit-action="reading-not-now"]').click();
      const after = golden.observe('consent: after Not now');
      const again = norm(await read(react));
      assert.deepEqual(again, after);
      assert.ok(after.buttons.some(([label]) => label === 'Analyze drift'));
    },
  );

  await step(
    'Steer back opens the correction with its numbers filled in, and Copy records it once',
    async () => {
      const g = await clockOf();
      const PARTS = ['Your last check failed', { entry: 'c1' }, '. Fix it, then say so.'];
      await setState(react, () =>
        stored(g, {
          routes: {
            '/api/correction': () => ({ body: { ok: true, parts: PARTS } }),
            '/api/correction/copied': () => ({ body: { ok: true } }),
          },
        }),
      );
      await load(react);
      await react.page.locator('[data-next-cockpit-action="steer-back"]').click();
      await react.page.waitForSelector('#next-cockpit-correction');
      const old = golden.observe('steer: the box');
      const mine = norm(await read(react));
      assert.deepEqual(mine, old, 'the steer box differs from the recorded box');
      const text = await react.page.locator('#next-cockpit-correction').inputValue();
      const recordedText = golden.observe('steer: the correction text');
      assert.equal(text, recordedText);
      assert.match(text, /Your last check failed \(#1 in Cargento\)\. Fix it, then say so\./);
      await react.page.locator('[data-next-cockpit-action="correction-copy"]').click();
      await sleep(patience(300));
      const copied = await react.page.evaluate(() => globalThis.__copied);
      const recordedCopied = golden.observe('steer: what the legacy page copied');
      assert.deepEqual(copied, recordedCopied);
      assert.equal(recordedCopied.length, 1);
      const recordedRequests = golden.observe('steer: copy requests the legacy page sent');
      assert.equal(recordedRequests, 1);
      assert.equal(postsTo(react.script, '/api/correction/copied').length, 1);
      assert.equal(postsTo(react.script, '/api/correction').length, 1);
    },
  );

  await step('the live estimate and the header pill read as the recording does', async () => {
    const g = await clockOf();
    const make = (g2) =>
      claude(g2, {
        session: { annotation_revision: 3 },
        work: {
          live_levels: [
            {
              harness: HARNESS,
              sid: SID,
              level: 'high',
              revision: 3,
              computed_at: g2 - 60,
              reasons: ['failed-check', 'no-passing-check'],
              cites: ['c1'],
              rose_from: 'medium',
              rose_at: 'c1',
            },
          ],
        },
        facts: RECORD(g2),
      });
    await setState(react, () => make(g));
    const arm = async (o) => {
      await o.context.addInitScript(
        ([harness, sid]) => {
          globalThis.localStorage.setItem(`cargento.next.live-estimate:${harness}:${sid}`, '1');
        },
        [HARNESS, SID],
      );
      await load(o);
      return read(o);
    };
    const mine = norm(await arm(react));
    const old = golden.observe('live estimate and pill');
    assert.deepEqual(mine, old, 'the live estimate differs from the recording');
    assert.match(old.pill, /Drift: High/);
    assert.match(old.text, /Live estimate/);
  });
  /* ===================== BEHAVIOUR: nothing starts on its own ===================== */
  /* The board's own revision, moved from outside the page: another session's words are saved, the backend's
     revision advances and the stream announces it, so what the page receives it was told, not asked for. */
  let tickNumber = 0;
  async function tick(o) {
    const before = o.counts().data;
    tickNumber += 1;
    const data = (await call(board.react.origin, 'GET', '/api/data')).body;
    const row = data.sessions.find((x) => x.sid === 'intent-3');
    await call(board.react.origin, 'POST', '/api/annotate', {
      harness: 'claude',
      sid: 'intent-3',
      goal: `tick ${tickNumber}`,
      expected_revision: row.annotation_revision || 0,
    });
    await call(board.react.origin, 'GET', '/api/data');
    const until = Date.now() + patience(15000);
    while (o.counts().data <= before && Date.now() < until) await sleep(100);
    assert.ok(o.counts().data > before, 'the page never received the new board revision');
    await sleep(patience(200));
  }
  const apply = async (o, make) => {
    const g = await clockOf();
    const next = freshScript();
    Object.assign(next, await make(g));
    // What the page has already sent is a record of the page, not of the state, so it is kept.
    next.posts = o.script.posts;
    for (const key of Object.keys(o.script)) delete o.script[key];
    Object.assign(o.script, next);
  };
  const ANNOUNCE = '#next-cockpit-cue-status';
  const said = (o) => o.page.locator(ANNOUNCE).textContent();

  await step(
    'no reading, cancel or correction request leaves the page from a mount, a poll, a route change, a hover, a focus or a keypress',
    async () => {
      await apply(react, (g) => claude(g));
      await load(react);
      await settled(() => react.page.evaluate(summarizeCard));
      react.reset();
      react.script.posts.length = 0;
      const ask = react.page.locator('[data-next-cockpit-action="reading-ask"]');
      for (let i = 0; i < 3; i += 1) await tick(react);
      await ask.hover();
      await ask.focus();
      await react.page.keyboard.press('Shift');
      await react.page.keyboard.press('a');
      await react.page.mouse.move(5, 5);
      for (let round = 0; round < 2; round += 1) {
        await react.page.evaluate(() => {
          location.hash = '#n=intent';
        });
        await react.page.waitForSelector('[data-next-view-body="intent"]');
        await react.page.evaluate((hash) => {
          location.hash = hash;
        }, FRAGMENT);
        await backOnTheSession(react);
      }
      await settled(() => react.page.evaluate(summarizeCard));
      assert.deepEqual(react.log.nonGet, []);
      assert.deepEqual(react.script.posts, []);
      const r = await resources(react.page);
      assert.ok(r.sources <= 1, `${r.sources} streams are open`);
      return { requests: react.log.requests.length };
    },
  );

  async function backOnTheSession(o) {
    await o.page
      .waitForSelector('.next-session-drift', { timeout: patience(8000) })
      .catch(async (error) => {
        const where = await o.page.evaluate(
          () => `${location.href} | ${document.body.innerText.slice(0, 300)}`,
        );
        throw new Error(`${error.message} at ${where}`);
      });
  }

  const deferred = () => {
    let release;
    const promise = new Promise((resolve) => {
      release = resolve;
    });
    return { promise, release };
  };

  await step(
    'one press sends one request, however it is pressed, and nothing retries it or restarts it under StrictMode',
    async () => {
      const gate = deferred();
      await apply(react, (g) =>
        claude(g, {
          routes: {
            '/api/reading': async () => {
              await gate.promise;
              return { body: { ok: true, job: JOB(g) } };
            },
          },
        }),
      );
      await load(react);
      await settled(() => react.page.evaluate(summarizeCard));
      react.script.posts.length = 0;
      const ask = react.page.locator('[data-next-cockpit-action="reading-ask"]');
      await ask.focus();
      await react.page.keyboard.press('Enter');
      await react.page.keyboard.press('Enter');
      await react.page.keyboard.press('Space');
      await ask.click({ force: true });
      await ask.dblclick({ force: true });
      await sleep(patience(300));
      assert.equal(
        postsTo(react.script, '/api/reading').length,
        1,
        'more than one reading request left',
      );
      const body = postsTo(react.script, '/api/reading')[0].body;
      assert.equal(body.press, true);
      assert.equal(body.observer_model, 1);
      assert.equal(body.provider, 'claude');
      assert.equal(body.expected_revision, 3);
      assert.ok(!('allow' in body), 'an Allow was sent although none was owed');
      // The button is busy, not gone, and still holds focus.
      assert.equal(await ask.getAttribute('aria-busy'), 'true');
      // A poll while it is open sends nothing more.
      await tick(react);
      await tick(react);
      assert.equal(postsTo(react.script, '/api/reading').length, 1);
      // The server answers: the board now holds the job, and the box is the answer.
      await apply(react, (g) =>
        claude(g, {
          session: { state: 'working' },
          payload: { reading_jobs: { [`${HARNESS}:${SID}`]: JOB(g) } },
          routes: react.script.routes,
        }),
      );
      gate.release();
      await tick(react);
      await react.page.waitForSelector('[data-next-analyzing="job-1"]');
      assert.equal(postsTo(react.script, '/api/reading').length, 1);
      // Said once, when the box was first drawn by a tab that watched it begin.
      assert.equal(await said(react), 'Analyzing drift');
      await tick(react);
      assert.equal(await said(react), 'Analyzing drift');
      return 'one request';
    },
  );

  await step(
    'Cancel names the job, sends one request, and the server’s cancelling flag survives a reload',
    async () => {
      const gate = deferred();
      await apply(react, (g) =>
        claude(g, {
          session: { state: 'working' },
          payload: { reading_jobs: { [`${HARNESS}:${SID}`]: JOB(g) } },
          routes: {
            '/api/reading/cancel': async () => {
              await gate.promise;
              return { status: 202, body: { ok: true, cancelling: true } };
            },
          },
        }),
      );
      await load(react);
      await react.page.waitForSelector('[data-next-analyzing]');
      react.script.posts.length = 0;
      const cancel = react.page.locator('[data-next-cockpit-action="reading-cancel"]');
      await cancel.focus();
      await react.page.keyboard.press('Enter');
      await react.page.keyboard.press('Enter');
      await cancel.click({ force: true });
      await sleep(patience(300));
      const posts = postsTo(react.script, '/api/reading/cancel');
      assert.equal(posts.length, 1);
      assert.deepEqual(posts[0].body, {
        harness: HARNESS,
        sid: SID,
        job: 'job-1',
        press: true,
        observer_model: 1,
      });
      await apply(react, (g) =>
        claude(g, {
          session: { state: 'working' },
          payload: { reading_jobs: { [`${HARNESS}:${SID}`]: JOB(g, { cancelling: true }) } },
        }),
      );
      gate.release();
      await tick(react);
      await react.page.reload();
      await react.page.waitForSelector('[data-next-analyzing]');
      assert.equal(
        await react.page
          .locator('[data-next-cockpit-action="reading-cancel"]')
          .getAttribute('aria-disabled'),
        'true',
      );
    },
  );

  await step('the end of a watched analysis is announced once, in the server’s words', async () => {
    await apply(react, (g) => claude(g, { payload: {} }));
    await load(react);
    await settled(() => react.page.evaluate(summarizeCard));
    await apply(react, (g) =>
      claude(g, {
        session: { state: 'working' },
        payload: { reading_jobs: { [`${HARNESS}:${SID}`]: JOB(g) } },
      }),
    );
    await tick(react);
    await react.page.waitForSelector('[data-next-analyzing]');
    assert.equal(await said(react), 'Analyzing drift');
    await apply(react, (g) => stored(g));
    await tick(react);
    await react.page.waitForSelector('[data-next-result]');
    assert.equal(await said(react), 'The analysis finished. Its result is in the Drift section.');
    await apply(react, (g) =>
      claude(g, {
        session: {
          annotation_reading_withheld: 'The analysis was cancelled.',
          annotation_reading_count: 1,
        },
      }),
    );
    await tick(react);
    await settled(() => react.page.evaluate(summarizeCard));
    // No job was in play, so there is nothing new to say: the last word stays the last thing said.
    assert.equal(await said(react), 'The analysis finished. Its result is in the Drift section.');
  });

  await step(
    'the consent step is the only place an Allow is sent from, and a changed destination refuses it',
    async () => {
      await apply(react, (g) =>
        claude(g, {
          payload: { reading: UNCONSENTED },
          routes: {
            '/api/reading': () => ({
              status: 409,
              body: { ok: false, reason: 'destination-changed' },
            }),
          },
        }),
      );
      await load(react);
      await settled(() => react.page.evaluate(summarizeCard));
      react.script.posts.length = 0;
      await react.page.locator('[data-next-cockpit-action="reading-ask"]').click();
      await react.page.waitForSelector('.next-cockpit-reading-consent');
      await sleep(patience(200));
      assert.equal(
        postsTo(react.script, '/api/reading').length,
        0,
        'the first press sent without an Allow',
      );
      // The heading holds focus, so a second Enter cannot give consent unread.
      assert.equal(
        await react.page.evaluate(() => document.activeElement?.id),
        'next-cockpit-reading-consent-title',
      );
      await react.page.keyboard.press('Enter');
      await sleep(patience(200));
      assert.equal(postsTo(react.script, '/api/reading').length, 0);
      await react.page.locator('[data-next-cockpit-action="reading-allow"]').click();
      await sleep(patience(400));
      const sent = postsTo(react.script, '/api/reading');
      assert.equal(sent.length, 1);
      assert.equal(sent[0].body.allow, true);
      assert.equal(sent[0].body.words_destination, 'api');
      assert.equal(sent[0].body.tool_output, 'api');
      assert.match(
        await react.page.locator('.next-session-drift').textContent(),
        /Where this session would be sent changed/,
      );
      await sleep(patience(600));
      assert.equal(postsTo(react.script, '/api/reading').length, 1, 'a refused press was retried');
    },
  );
  /* ===================== BEHAVIOUR: the correction's native editor ===================== */
  const PARTS = ['Your last check failed', { entry: 'c1' }, '. Fix it, then say so.'];
  const steerState = (g, extra = {}) =>
    stored(g, {
      ...extra,
      routes: {
        '/api/correction': () => ({ body: { ok: true, parts: PARTS } }),
        '/api/correction/copied': () => ({ body: { ok: true } }),
        ...(extra.routes || {}),
      },
    });
  const BOX = '#next-cockpit-correction';
  const mark = (o, selector, name) =>
    o.page.locator(selector).evaluate((node, key) => {
      globalThis.__marks ??= {};
      globalThis.__marks[key] = node;
    }, name);
  const same = (o, selector, name) =>
    o.page.locator(selector).evaluate((node, key) => globalThis.__marks[key] === node, name);
  const caretOf = (o) =>
    o.page.locator(BOX).evaluate((node) => ({
      value: node.value,
      start: node.selectionStart,
      end: node.selectionEnd,
      focused: document.activeElement === node,
    }));
  async function openSteer(o, extra = {}) {
    await apply(o, (g) => steerState(g, extra));
    await load(o);
    await settled(() => o.page.evaluate(summarizeCard));
    o.script.posts.length = 0;
    await o.page.locator('[data-next-cockpit-action="steer-back"]').click();
    await o.page.waitForSelector(BOX);
    await o.page.waitForFunction(
      (selector) => document.activeElement === document.querySelector(selector),
      BOX,
    );
  }

  await step(
    'the correction box keeps its node, text, caret, selection, focus and native undo through the board’s own revisions',
    async () => {
      await openSteer(react);
      await mark(react, BOX, 'box');
      await react.page.keyboard.press(`${MOD}+a`);
      await react.page.keyboard.type('hello brave world');
      for (let i = 0; i < 5; i += 1) await react.page.keyboard.press('ArrowLeft');
      await react.page.keyboard.type('X');
      await react.page.keyboard.press('ArrowLeft');
      await react.page.keyboard.press('Shift+ArrowLeft');
      await react.page.keyboard.press('Shift+ArrowLeft');
      const before = await caretOf(react);
      assert.equal(before.value, 'hello brave Xworld');
      // New work lands, and a running analysis: boards that would redraw the card under the reader.
      await apply(react, (g) =>
        steerState(g, { facts: [...RECORD(g), check('c9', g - 20, 'passed')] }),
      );
      for (let i = 0; i < 3; i += 1) await tick(react);
      assert.equal(await same(react, BOX, 'box'), true, 'the box was replaced');
      assert.deepEqual(await caretOf(react), before);
      // The board that arrived waits, and the box says so.
      assert.equal(await react.page.locator('[data-next-result-stale]').count(), 0);
      assert.match(
        await react.page.locator('[data-next-correction-paint-why]').textContent(),
        /Updates are paused while you edit this correction/,
      );
      // Native undo takes back the last edit, and only that.
      await react.page.keyboard.press(`${MOD}+z`);
      assert.equal((await caretOf(react)).value, 'hello brave world');
      await react.page.keyboard.press(`${MOD}+Shift+z`);
      assert.equal((await caretOf(react)).value, 'hello brave Xworld');
      // Leaving the box shows the newest board.
      await react.page.locator('.next-session-drift-heading').click();
      await react.page.waitForSelector('[data-next-result-stale="work"]');
      // The stale mark moves the box in the layout, which the reader has left; the words are theirs and stay.
      assert.equal(await react.page.locator('[data-next-correction-paint-why]').isHidden(), true);
      assert.equal((await caretOf(react)).value, 'hello brave Xworld');
    },
  );

  await step(
    'a focused, untouched correction box keeps its node, caret and selection when a stale mark would move it',
    async () => {
      await openSteer(react);
      await mark(react, BOX, 'box');
      await react.page.locator(BOX).evaluate((node) => {
        node.focus();
        node.setSelectionRange(2, 7);
      });
      await apply(react, (g) =>
        steerState(g, { facts: [...RECORD(g), check('c9', g - 20, 'passed')] }),
      );
      await tick(react);
      await tick(react);
      assert.equal(await same(react, BOX, 'box'), true, 'the stale mark replaced the box');
      const caret = await caretOf(react);
      assert.deepEqual([caret.start, caret.end, caret.focused], [2, 7, true]);
      assert.equal(await react.page.locator('[data-next-result-stale]').count(), 0);
      // Leaving it shows the board.
      await react.page.locator('.next-session-drift-heading').click();
      await react.page.waitForSelector('[data-next-result-stale="work"]');
    },
  );

  await step('a composition is never cut, copied or lost, and the board waits for it', async () => {
    // Composing into a box nobody has edited yet, so nothing but the composition holds the board back.
    await openSteer(react);
    await mark(react, BOX, 'box');
    const before = (await caretOf(react)).value;
    await react.page.locator(BOX).evaluate((node) => {
      globalThis.__ime = [];
      for (const name of ['compositionstart', 'compositionupdate', 'compositionend']) {
        node.addEventListener(name, () => globalThis.__ime.push(name));
      }
    });
    const cdp = await react.context.newCDPSession(react.page);
    await cdp.send('Input.imeSetComposition', {
      text: 'にほん',
      selectionStart: 3,
      selectionEnd: 3,
    });
    const composing = (await caretOf(react)).value;
    assert.ok(composing.includes('にほん'), `no provisional text in ${composing}`);
    assert.equal(composing.length, before.length + 3);
    assert.ok((await react.page.evaluate(() => globalThis.__ime)).includes('compositionstart'));
    await apply(react, (g) =>
      steerState(g, { facts: [...RECORD(g), check('c9', g - 20, 'passed')] }),
    );
    await tick(react);
    await tick(react);
    assert.equal(await same(react, BOX, 'box'), true, 'a board replaced the box mid-composition');
    assert.equal((await caretOf(react)).value, composing);
    assert.equal(await react.page.locator('[data-next-result-stale]').count(), 0);
    // A press that could copy the provisional words is refused, and nothing reaches the clipboard.
    await react.page
      .locator('[data-next-cockpit-action="correction-copy"]')
      .evaluate((b) => b.click());
    assert.equal(
      (await react.page.locator('[data-next-correction-cue]').textContent()).trim(),
      'Copy unavailable',
    );
    assert.deepEqual(await react.page.evaluate(() => globalThis.__copied), []);
    await cdp.send('Input.insertText', { text: '日本' });
    const committed = (await caretOf(react)).value;
    assert.ok(committed.includes('日本') && !committed.includes('にほん'));
    assert.ok((await react.page.evaluate(() => globalThis.__ime)).includes('compositionend'));
    // Committed, the words are the reader's and the box is edited and focused, so the board still waits.
    assert.equal(await react.page.locator('[data-next-result-stale]').count(), 0);
    await react.page.locator('.next-session-drift-heading').click();
    await react.page.waitForSelector('[data-next-result-stale="work"]');
    await react.page.locator('[data-next-cockpit-action="correction-copy"]').click();
    await sleep(patience(300));
    assert.deepEqual(await react.page.evaluate(() => globalThis.__copied), [committed]);
    assert.equal(postsTo(react.script, '/api/correction/copied').at(-1).body.text, committed);
    await cdp.detach();
  });

  await step(
    'the box survives a route away and back, and its words are what Copy sends',
    async () => {
      await openSteer(react);
      await react.page.keyboard.press(`${MOD}+a`);
      await react.page.keyboard.type('Words I wrote myself.');
      await react.page.evaluate(() => {
        location.hash = '#n=intent';
      });
      await react.page.waitForSelector('[data-next-view-body="intent"]');
      await react.page.evaluate((hash) => {
        location.hash = hash;
      }, FRAGMENT);
      await backOnTheSession(react);
      await react.page.waitForSelector(BOX);
      assert.equal((await caretOf(react)).value, 'Words I wrote myself.');
      await react.page.locator('[data-next-cockpit-action="correction-copy"]').click();
      await sleep(patience(300));
      assert.deepEqual(await react.page.evaluate(() => globalThis.__copied), [
        'Words I wrote myself.',
      ]);
      // Said until an accepted edit.
      assert.equal(
        (await react.page.locator('[data-next-correction-cue]').textContent()).trim(),
        'Copied',
      );
      await tick(react);
      assert.equal(
        (await react.page.locator('[data-next-correction-cue]').textContent()).trim(),
        'Copied',
      );
      await react.page.locator(BOX).click();
      await react.page.keyboard.type('!');
      assert.equal(
        (await react.page.locator('[data-next-correction-cue]').textContent()).trim(),
        'Copy',
      );
    },
  );

  await step(
    'a paste over the cap keeps the reader’s words and cuts what was inserted, in one undo step',
    async () => {
      await openSteer(react);
      await react.page.keyboard.press(`${MOD}+a`);
      await react.page.keyboard.type('Keep these words. ');
      const cdp = await react.context.newCDPSession(react.page);
      await cdp.send('Input.insertText', { text: 'x'.repeat(2100) });
      const after = await caretOf(react);
      assert.ok(after.value.startsWith('Keep these words. '));
      assert.equal([...after.value].length, 2000);
      assert.equal(
        (await react.page.locator('[data-next-correction-count]').textContent()).trim(),
        '2000/2000',
      );
      await react.page.keyboard.press(`${MOD}+z`);
      assert.equal((await caretOf(react)).value, 'Keep these words. ');
      await cdp.detach();
    },
  );

  await step(
    'a pointer on its way to Copy is waited through, and the click that follows is not swallowed',
    async () => {
      await openSteer(react);
      await react.page.keyboard.press(`${MOD}+a`);
      await react.page.keyboard.type('An edit that is mine.');
      const copy = react.page.locator('[data-next-cockpit-action="correction-copy"]');
      const box = await copy.boundingBox();
      await react.page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
      await react.page.mouse.down();
      // The browser blurred the box between the press and the click; a board arrives meanwhile.
      await apply(react, (g) =>
        steerState(g, { facts: [...RECORD(g), check('c9', g - 20, 'passed')] }),
      );
      await tick(react);
      await tick(react);
      assert.equal(
        await react.page.locator('[data-next-result-stale]').count(),
        0,
        'a board was drawn under the pointer',
      );
      await react.page.mouse.up();
      await sleep(patience(400));
      assert.deepEqual(await react.page.evaluate(() => globalThis.__copied), [
        'An edit that is mine.',
      ]);
      await react.page.waitForSelector('[data-next-result-stale="work"]');
    },
  );

  /* ===================== BEHAVIOUR: keyboard, layout and pictures ===================== */
  await step(
    'Analyze, the consent step and Steer back are operated from the keyboard alone',
    async () => {
      await apply(react, (g) =>
        steerState(g, {
          payload: { reading: UNCONSENTED },
          routes: { '/api/reading': () => ({ body: { ok: true, produced: false } }) },
        }),
      );
      await load(react);
      await settled(() => react.page.evaluate(summarizeCard));
      react.script.posts.length = 0;
      const reach = async (selector) => {
        for (let i = 0; i < 80; i += 1) {
          const there = await react.page.evaluate(
            (sel) => document.activeElement?.matches(sel) === true,
            selector,
          );
          if (there) return;
          await react.page.keyboard.press('Tab');
        }
        throw new Error(`Tab never reached ${selector}`);
      };
      await react.page.locator('.next-session-drift-heading').focus();
      await reach('[data-next-cockpit-action="reading-ask"]');
      await react.page.keyboard.press('Enter');
      await react.page.waitForSelector('.next-cockpit-reading-consent');
      assert.equal(postsTo(react.script, '/api/reading').length, 0);
      // The question holds focus, and Tab reaches Allow and then Not now, in that order.
      await react.page.keyboard.press('Tab');
      assert.equal(
        await react.page.evaluate(() =>
          document.activeElement?.getAttribute('data-next-cockpit-action'),
        ),
        'reading-allow',
      );
      await react.page.keyboard.press('Tab');
      assert.equal(
        await react.page.evaluate(() =>
          document.activeElement?.getAttribute('data-next-cockpit-action'),
        ),
        'reading-not-now',
      );
      await react.page.keyboard.press('Space');
      await react.page.waitForSelector('[data-next-cockpit-action="reading-ask"]');
      assert.equal(postsTo(react.script, '/api/reading').length, 0);
      // Steer back, from a stored departure, the same way.
      await apply(react, (g) => steerState(g));
      await load(react);
      await settled(() => react.page.evaluate(summarizeCard));
      await react.page.locator('.next-session-drift-heading').focus();
      await reach('[data-next-cockpit-action="steer-back"]');
      await react.page.keyboard.press('Enter');
      await react.page.waitForSelector(BOX);
      await reach(BOX);
      await react.page.keyboard.type('Typed with no pointer.');
      await react.page.keyboard.press('Tab');
      assert.equal(
        await react.page.evaluate(() =>
          document.activeElement?.getAttribute('data-next-cockpit-action'),
        ),
        'correction-copy',
      );
      await react.page.keyboard.press('Enter');
      await sleep(patience(300));
      const copied = await react.page.evaluate(() => globalThis.__copied);
      assert.equal(copied.length, 1);
      assert.ok(copied[0].startsWith('Typed with no pointer.'));
    },
  );

  await step(
    '320, 375, 640 (200% zoom) and 1280 CSS px: no horizontal scroll, in every state',
    async () => {
      const widths = {};
      for (const width of [320, 375, 640, 1280]) {
        const o = await newPage({ width, height: 900 });
        const states = [
          ['result and an open correction', (g) => steerState(g)],
          [
            'a running analysis',
            (g) =>
              claude(g, {
                session: { state: 'working' },
                payload: { reading_jobs: { [`${HARNESS}:${SID}`]: JOB(g) } },
              }),
          ],
          ['the consent step', (g) => claude(g, { payload: { reading: UNCONSENTED } })],
          [
            'a stale result and a gap',
            (g) => stored(g, { session: { annotation_revision: 4 }, contextError: true }),
          ],
        ];
        for (const [name, make] of states) {
          await apply(o, make);
          await load(o);
          await settled(() => o.page.evaluate(summarizeCard));
          if (name.startsWith('result')) {
            await o.page.locator('[data-next-cockpit-action="steer-back"]').click();
            await o.page.waitForSelector(BOX);
            await o.page
              .locator(BOX)
              .fill(`${'A long correction word '.repeat(12)}${'x'.repeat(80)}`);
          }
          if (name === 'the consent step') {
            await o.page.locator('[data-next-cockpit-action="reading-ask"]').click();
            await o.page.waitForSelector('.next-cockpit-reading-consent');
          }
          const overflow = await o.page.evaluate(() => ({
            scroll: document.documentElement.scrollWidth,
            client: document.documentElement.clientWidth,
            card: document.querySelector('.next-session-drift')?.scrollWidth ?? 0,
            cardClient: document.querySelector('.next-session-drift')?.clientWidth ?? 0,
          }));
          assert.ok(
            overflow.scroll <= overflow.client,
            `${name} scrolls sideways at ${width}px: ${JSON.stringify(overflow)}`,
          );
          assert.ok(
            overflow.card <= overflow.cardClient + 1,
            `the card overflows at ${width}px in ${name}`,
          );
          if ([375, 1280].includes(width)) {
            await mkdir(SHOTS, { recursive: true });
            const file = `${SHOTS}drift-${name.replace(/[^a-z]+/g, '-')}-${width}.png`;
            await o.page.screenshot({ path: file, fullPage: true });
            shots.push(file);
          }
        }
        widths[width] = 'ok';
        await o.close();
      }
      return widths;
    },
  );
} finally {
  for (const o of opened) await o.close().catch(() => undefined);
  await browser.close();
  await board.close();
}

try {
  golden.finish({ complete: !only && failures.length === 0 });
} catch (error) {
  failures.push({ name: 'golden', message: String(error.message) });
}

console.log(JSON.stringify({ receipts, shots }, null, 2));
if (failures.length) {
  for (const failure of failures) console.error(`FAILED: ${failure.name}\n${failure.message}\n`);
  process.exit(1);
}
