/* global document, getComputedStyle, CSSStyleRule, CSSMediaRule -- used inside page.evaluate, which runs in the browser */
/*
 * The readability contract of the shipped stylesheet, asked of COMPUTED styles on the page a reader gets.
 *
 * The previous interface's tests resolved the cascade by hand over the elements its emitters rendered, and
 * that is how they saw a rule that reaches an element through ancestors a selector never names (a block's
 * `header p` taking a caveat below the floor). `frontend/src/styles/css.test.ts` reads declarations and is
 * blind to exactly that. This proof puts the same questions to the browser's own cascade, on every route and
 * tab the fixture boards populate:
 *
 *   floor       no element that owns text computes below the 13px label step;
 *   sentences   prose in the sans family computes at the 15px sentence step, bar the named exceptions;
 *   absence     a stated absence is sans, in the absence ink, and never larger than the 15px step or than
 *               the element it sits in (an absence that outranks the value it replaces reads as the fact);
 *   ink         the four ink registers are the only text colours the page spends on its label, value,
 *               absence and caption roles, and no text spends the retired third ink;
 *   controls    every control is at least at the label step, `[data-slot="button"]` is at the sentence step, and
 *               controls that touch agree on a size;
 *   variables   every `var(--x)` any rule uses resolves to a declared custom property;
 *   palette     the page is dark only: no `prefers-color-scheme` rule, and a light-scheme browser draws the
 *               same page;
 *   focus       every focusable element shows a ring of its own authoring when focused from the keyboard.
 *
 * The population is a floor, not a census: a surface no fixture board draws is not checked here, and the
 * coverage step names the surfaces this run has to have reached so an emptied render fails instead of passing.
 *
 * The page is whatever `support/world.mjs` serves: development by default, the production bundle with
 * `CARGENTO_E2E_BUNDLE=production`. Run with `pnpm test:css:browser`. `CARGENTO_MUTATION=<name>` serves a
 * scratch copy of the tree with one deliberate break (see MUTATIONS) and the run is then expected to FAIL;
 * `CSS_CONTRACT_WORLDS=sessions,intent,console` narrows the worlds (the coverage and light-scheme steps then
 * fail by design). Models, usage, notifications, the clipboard and the terminal are off or replaced, and every
 * request leaving the board's own origins is refused.
 */
import assert from 'node:assert/strict';
import { cp, mkdir, mkdtemp, readFile, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { chromium } from '@playwright/test';
import { call, startIntentBoard } from './intent-board.mjs';
import { awaitRecordRead } from './support/record.mjs';
import {
  ASSESSMENT,
  freshScript,
  installScript,
  POLICY,
  RECORD,
  ROUTE,
  SAVED,
  UNCONSENTED,
} from './drift-board.mjs';
import { recordClipboard, startSessionsBoard } from './sessions-board.mjs';
import { freePorts, openPage, REPOSITORY } from './support/browser.mjs';
import { startReactWorld } from './support/world.mjs';
import { measureButtonChrome, normaliseButtonKey } from './support/button-chrome.mjs';

const BUTTON_TABLE = JSON.parse(
  await readFile(new URL('./button-chrome-reference.json', import.meta.url), 'utf8'),
);
const BUTTON_REFERENCE = Object.fromEntries(
  Object.entries(BUTTON_TABLE.instances).map(([key, profile]) => [
    key,
    BUTTON_TABLE.profiles[profile],
  ]),
);

/* Every fixed wait here means "give the page time to react"; a hosted runner delivers frames later, so each is
   tripled there. */
const patience = (ms) => (process.env.CI ? ms * 3 : ms);
const E = encodeURIComponent;
const WORLDS = (process.env.CSS_CONTRACT_WORLDS || 'sessions,intent,console').split(',');
const MUTATION = process.env.CARGENTO_MUTATION || '';

const LABEL_PX = 13;
const SENTENCE_PX = 15;
const TABS = ['now', 'course', 'decisions', 'console'];

/* One deliberate break per name, in the SHIPPED sheets of a scratch copy: [file under frontend/src, the text to
   replace, what replaces it]. The run is expected to fail, and to fail on the check the name says. */
const MUTATIONS = {
  'absence-mono': [
    [
      'capacity/capacity.css',
      '.next-capacity-absent{color:var(--ink-absence);font-family:var(--sans);font-size:var(--fs-label)}',
      '.next-capacity-absent{color:var(--ink-absence);font-family:var(--mono);font-size:var(--fs-label)}',
    ],
  ],
  'absence-white': [
    [
      'capacity/capacity.css',
      '.next-capacity-absent{color:var(--ink-absence);',
      '.next-capacity-absent{color:#fff;',
    ],
  ],
  'absence-hero': [
    [
      'capacity/capacity.css',
      '.next-capacity-absent{color:var(--ink-absence);font-family:var(--sans);font-size:var(--fs-label)}',
      '.next-capacity-absent{color:var(--ink-absence);font-family:var(--sans);font-size:var(--fs-hero)}',
    ],
  ],
  'button-size-removed': [['ui/button.tsx', 'text-body', 'text-label']],
  'button-cascade-colour': [['ui/button.tsx', 'text-foreground', 'text-muted-foreground']],
  'button-memo-native': [
    ['controls/HumanContextField.tsx', 'variant="default"', 'variant="native"'],
  ],
  'button-raise-amber': [
    ['ui/button.tsx', 'data-[raise-state=throttled]:border-[var(--amber)]', ''],
  ],
  'button-retry-dashed': [
    [
      'ui/button.tsx',
      'aria-disabled:not-aria-busy:border-solid',
      'aria-disabled:not-aria-busy:border-dashed',
    ],
  ],
  'button-target-removed': [['ui/button.tsx', 'min-h-[44px] min-w-[44px]', 'min-h-0 min-w-0']],
  'button-reserve-removed': [['ui/button.tsx', 'reserve ? (', 'false ? (']],
  'button-focus-removed': [
    [
      'ui/button.tsx',
      'focus-visible:outline-2 focus-visible:outline-solid',
      'focus-visible:outline-none',
    ],
  ],
  'focus-removed': [
    [
      'sessions/sessions.css',
      '.next-operation-route:focus-visible{outline:2px solid var(--accent);outline-offset:2px}',
      '',
    ],
  ],
  'unknown-token': [
    [
      'sessions/sessions.css',
      '.next-session-fact-note{display:block;margin-top:4px;color:var(--ink-caption);',
      '.next-session-fact-note{display:block;margin-top:4px;color:var(--no-such-token);',
    ],
  ],
  'light-scheme': [
    [
      'styles/shell.css',
      '* {\n  box-sizing: border-box;\n}',
      '* {\n  box-sizing: border-box;\n}\n@media (prefers-color-scheme: light) {\n  :root {\n    --bg: #fff;\n    --ink: #111;\n  }\n}',
    ],
  ],
  'ancestor-rule': [
    [
      'steering/steering.css',
      '.next-stage-conditions { margin: 1rem 0; }',
      '.next-stage-conditions { margin: 1rem 0; }\n.next-steer>header p{font-size:var(--fs-label)}',
    ],
  ],
  'sentence-12px': [
    [
      'sessions/sessions.css',
      '.next-session-fact-note{display:block;margin-top:4px;color:var(--ink-caption);font-family:var(--sans);font-size:var(--fs-label)}',
      '.next-session-fact-note{display:block;margin-top:4px;color:var(--ink-caption);font-family:var(--sans);font-size:12px}',
    ],
  ],
};

/* The named exceptions, measured on the shipped page. Each is an exact set (see `exactly`): a new shape fails the
   run, and so does one that no longer occurs, so the change that removes the cause has to remove the entry.

   - sentencesAtLabel: captions, counts and meta lines under a heading, and the empty-state lines of the
     timeline and workstream, are deliberately one step below the 15px sentences.
   - absencesLarger: an absence that stands where a title or a figure would takes that element's size.
   - uaFocusRing: elements that draw the browser's own focus ring. It is visible on the dark page and it is the
     ring the previous page drew for them, but no rule in the sheets says so; every other focusable element has
     a ring the sheets author, so a removed `:focus-visible` rule lands the element here and fails.
   - uaLinks: links no rule colours, which draw in the browser's link colour, as the previous page's did.
   - offScale: headings with no size rule, which draw at the browser's default heading size (2em, 1.5em), off
     the five steps, as the previous page's did.
   - unresolved: custom properties a rule uses and no sheet declares, which resolve to nothing. None is held, so
     a new one fails; add the declaration rather than an entry. */
const INVENTORY = {
  sentencesAtLabel: [
    'article.next-attention-item > div.next-attention-risk-source > span.next-attention-risk-next',
    'article.next-project-detail > header.next-project-detail-header > p.next-project-detail-count',
    'article.next-project-detail > header.next-project-detail-header > span.next-project-value',
    'div > dd > span.next-session-fact-note',
    'div.next-capacity-row > div.next-capacity-ends > span.next-capacity-slack',
    'header.next-header > div.next-header-right > span.next-running.next-live',
    'header.next-session-detail-header > div.next-session-detail-bar > p.next-session-detail-meta',
    'header.next-session-drift-head > div.next-session-drift-titles > p.next-session-drift-sub',
    'main > article.next-session-detail > footer.next-session-footer',
    'main > nav.next-breadcrumb > span',
    'section.next-capacity > div.next-capacity-models > i',
    'section.next-capacity > div.next-capacity-row.next-capacity-more > i',
    'section.next-cockpit-recovery > header > small.next-cockpit-recovery-gloss',
    'section.next-cockpit-semantic > section.pc-semantic-timeline > p.pc-substrate-empty',
    'section.next-control.next-guardrails > header.next-rail-header > span.next-rail-meta',
    'section.next-project-activity > div.next-activity-cards > p.next-activity-empty',
    'section.next-project-group > header > p',
    'section.next-rail-panel > header.next-rail-header > span.next-rail-meta',
    'section.next-rail-panel > section.next-usage-consent > p',
    'section.next-usage-consent > p > strong',
    'section.next-workstream > div > p.next-workstream-empty',
  ],
  absencesLarger: [
    'header.next-session-detail-header > div.next-session-detail-title > h1.next-session-absent',
    'section.next-delegation.next-rail-panel > div.next-delegation-withheld > strong',
  ],
  uaFocusRing: [
    'div.next-cockpit-held-fields > div.next-cockpit-held-field > textarea',
    'div.next-cockpit-held-heading > label.next-intent-prompt-pick > select.next-intent-prompt-select',
    'form > label > input',
    'ol.next-cockpit-held-list > li.next-cockpit-held-line > textarea',
  ],
  uaLinks: [
    'div.next-session-detail-title > p.next-session-identity > a',
    'main > section.next-session-detail-empty > a',
    'section.next-cockpit-panel > p.next-cockpit-empty > a',
  ],
  offScale: [
    'main > section.next-intent > h1',
    'main > section.next-intent > h2',
    'section.next-cockpit-panel > section.next-stage-conditions > h2',
  ],
  unresolved: [],
};
const near = (a, b) => Math.abs(a - b) < 0.01;

const receipts = {};
const failures = [];
async function step(name, run) {
  try {
    const detail = await run();
    receipts[name] = detail === undefined ? 'ok' : detail;
  } catch (error) {
    failures.push({ name, message: String(error.stack || error.message || error).slice(0, 4000) });
    receipts[name] = 'FAILED';
  }
}

/* ---- the page-side measurements. These run IN the page, so each is self-contained. ---- */

/* Every element that owns text, with what the browser computed for it. */
const measureText = () => {
  const { document: doc } = globalThis;
  const SKIP = new Set([
    'SCRIPT',
    'STYLE',
    'NOSCRIPT',
    'TEMPLATE',
    'HEAD',
    'TITLE',
    'META',
    'LINK',
  ]);
  const ABSENCE =
    '[data-next-absent],[data-next-withheld],[class*="-absent"],[class*="--absent"],[class*="-withheld"],.next-absence-reason';
  const CONTROL = 'button,a[href],summary,select,input,textarea,[role="button"],[role="link"]';
  for (const details of doc.querySelectorAll('details:not([open])')) details.open = true;
  const label = (el) => {
    const parts = [];
    for (let node = el; node && node !== doc.body && parts.length < 4; node = node.parentElement) {
      const classes = [...node.classList]
        .filter((name) => /^(next-|ctl-|pc-)/.test(name))
        .slice(0, 2)
        .join('.');
      parts.unshift(node.localName + (classes ? `.${classes}` : ''));
    }
    return parts.join(' > ');
  };
  // What an absence's value would compute as: the same element with its `--absent` class swapped for `--known`.
  const twinOf = (el) => {
    const absent = [...el.classList].find((name) => name.endsWith('--absent'));
    if (!absent) return null;
    const known = absent.replace(/--absent$/, '--known');
    el.classList.replace(absent, known);
    const px = parseFloat(getComputedStyle(el).fontSize);
    el.classList.replace(known, absent);
    return px;
  };
  const rows = [];
  for (const el of doc.body.querySelectorAll('*')) {
    if (SKIP.has(el.tagName) || el.closest('svg')) continue;
    const control = el.matches('input,textarea,select');
    const own = [...el.childNodes]
      .filter((node) => node.nodeType === 3)
      .map((node) => node.textContent)
      .join(' ')
      .replace(/\s+/g, ' ')
      .trim();
    if (!own && !control) continue;
    if (!el.checkVisibility({ visibilityProperty: true })) continue;
    const box = el.getBoundingClientRect();
    if (box.width <= 2 || box.height <= 2) continue;
    const css = getComputedStyle(el);
    const parent = el.parentElement ? getComputedStyle(el.parentElement) : css;
    rows.push({
      at: label(el),
      text: (own || el.value || el.placeholder || '').slice(0, 60),
      words: own ? own.split(' ').length : 0,
      px: parseFloat(css.fontSize),
      parentPx: parseFloat(parent.fontSize),
      mono: /mono/i.test(css.fontFamily),
      weight: Number(css.fontWeight),
      color: css.color,
      upper: css.textTransform === 'uppercase',
      spacing: parseFloat(css.letterSpacing) || 0,
      absence:
        el.matches(ABSENCE) ||
        Boolean(el.parentElement?.matches('[data-next-absent],[data-next-withheld]')),
      control: Boolean(el.closest(CONTROL)),
      action: el.dataset.slot === 'button' && el.dataset.variant !== 'native',
      hidden: el.matches('.next-visually-hidden') || Boolean(el.closest('.next-visually-hidden')),
      twinPx: twinOf(el),
      disabled: Boolean(
        el.closest('[disabled],[aria-disabled="true"],[data-state="todo"],[aria-checked="false"]'),
      ),
      tag: el.localName,
      pseudo: false,
    });
    // Text drawn by a pseudo-element (the More menu's label is an attribute shown by `::before`).
    for (const which of ['::before', '::after']) {
      const drawn = getComputedStyle(el, which);
      const content = drawn.content;
      if (!content || content === 'none' || content === 'normal' || content === '""') continue;
      rows.push({
        at: `${label(el)} ${which}`,
        text: content.replace(/^"|"$/g, '').slice(0, 60) || content,
        words: 0,
        px: parseFloat(drawn.fontSize),
        parentPx: parseFloat(css.fontSize),
        mono: /mono/i.test(drawn.fontFamily),
        weight: Number(drawn.fontWeight),
        color: drawn.color,
        upper: drawn.textTransform === 'uppercase',
        spacing: parseFloat(drawn.letterSpacing) || 0,
        absence: false,
        control: Boolean(el.closest(CONTROL)),
        action: false,
        hidden: false,
        twinPx: null,
        disabled: false,
        tag: el.localName,
        pseudo: true,
      });
    }
  }
  const probe = doc.createElement('span');
  doc.body.append(probe);
  const register = (name) => {
    probe.style.color = `var(${name})`;
    return getComputedStyle(probe).color;
  };
  const registers = Object.fromEntries(
    [
      '--ink',
      '--ink2',
      '--ink3',
      '--ink-label',
      '--ink-value',
      '--ink-absence',
      '--ink-caption',
      '--accent',
      '--accent-dim',
      '--amber',
      '--clay',
    ].map((name) => [name, register(name)]),
  );
  probe.remove();
  // Controls that sit side by side in one parent, with the size each computes.
  const groups = [];
  for (const parent of new Set(
    [...doc.body.querySelectorAll('button')].map((b) => b.parentElement),
  )) {
    const kids = [...parent.children].filter(
      (kid) => kid.matches('button') && kid.checkVisibility({ visibilityProperty: true }),
    );
    if (kids.length < 2) continue;
    groups.push({
      at: label(parent),
      buttons: kids.map((kid) => ({
        at: label(kid),
        text: kid.textContent.replace(/\s+/g, ' ').trim().slice(0, 30),
        px: parseFloat(getComputedStyle(kid).fontSize),
      })),
    });
  }
  const buttons = [...doc.body.querySelectorAll('button,summary')]
    .filter((el) => el.checkVisibility({ visibilityProperty: true }))
    .map((el) => ({
      at: label(el),
      text: el.textContent.replace(/\s+/g, ' ').trim().slice(0, 30),
      px: parseFloat(getComputedStyle(el).fontSize),
      color: getComputedStyle(el).color,
      disabled: Boolean(el.disabled),
      action: el.dataset.slot === 'button' && !['native', 'terminal'].includes(el.dataset.variant),
    }));
  // The colour a link with no authored colour draws in, in this page's colour scheme.
  const link = doc.createElement('a');
  link.href = '#';
  doc.body.append(link);
  const linkColour = getComputedStyle(link).color;
  link.remove();
  return {
    rows,
    registers,
    groups,
    buttons,
    linkColour,
    scheme: getComputedStyle(doc.documentElement).colorScheme,
  };
};

/* The custom properties every rule uses and every rule (or inline style) declares, and the media queries that
   name a colour scheme. */
const measureSheets = () => {
  const { document: doc } = globalThis;
  const declared = new Set();
  const used = new Map();
  const schemes = [];
  const rules = [];
  const walk = (list) => {
    for (const rule of list) {
      if (rule instanceof CSSMediaRule && /prefers-color-scheme/.test(rule.conditionText))
        schemes.push(rule.conditionText);
      if (rule instanceof CSSStyleRule) {
        for (const name of rule.style) if (name.startsWith('--')) declared.add(name);
        const text = rule.cssText;
        for (const match of text.matchAll(/var\(\s*(--[\w-]+)\s*([,)])/g))
          if (match[2] === ')') used.set(match[1], rule.selectorText);
      }
      if (rule.cssRules) walk(rule.cssRules);
      rules.push(rule);
    }
  };
  for (const sheet of doc.styleSheets) {
    try {
      walk(sheet.cssRules);
    } catch {
      // A cross-origin sheet cannot be read; the page loads none, and the request log says so.
    }
  }
  for (const el of doc.querySelectorAll('[style]')) {
    for (const name of el.style) if (name.startsWith('--')) declared.add(name);
    for (const match of (el.getAttribute('style') || '').matchAll(/var\(\s*(--[\w-]+)\s*\)/g))
      used.set(match[1], 'style attribute');
  }
  return {
    declared: [...declared],
    used: [...used].map(([name, at]) => ({ name, at })),
    schemes,
    rules: rules.length,
  };
};

/* The focusable elements that draw, in document order, as the page would offer them to a keyboard. */
const FOCUSABLE =
  'a[href],button:not([disabled]),summary,input:not([type="hidden"]):not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"]),[contenteditable="true"],[role="button"],[role="link"]';

const ringOf = (el) => {
  if (!el) return null;
  const alpha = (colour) => {
    const m = /rgba?\(([^)]*)\)/.exec(colour);
    if (!m) return 1;
    const parts = m[1].split(/[ ,/]+/).filter(Boolean);
    return parts.length > 3 ? Number(parts[3]) : 1;
  };
  const outline = (css) => {
    const width = parseFloat(css.outlineWidth) || 0;
    if (css.outlineStyle === 'none' || css.outlineStyle === 'hidden' || width < 1) return null;
    if (alpha(css.outlineColor) === 0) return null;
    return `${css.outlineStyle} ${width}px ${css.outlineColor}`;
  };
  const own = getComputedStyle(el);
  return {
    focusVisible: el.matches(':focus-visible'),
    outline:
      outline(own) ||
      outline(getComputedStyle(el, '::after')) ||
      outline(getComputedStyle(el, '::before')),
    shadow: own.boxShadow !== 'none' ? own.boxShadow : null,
    label: (() => {
      const parts = [];
      for (
        let node = el;
        node && node !== document.body && parts.length < 3;
        node = node.parentElement
      ) {
        const classes = [...node.classList]
          .filter((name) => /^(next-|ctl-|pc-)/.test(name))
          .slice(0, 2)
          .join('.');
        parts.unshift(node.localName + (classes ? `.${classes}` : ''));
      }
      return parts.join(' > ');
    })(),
  };
};

/* Focus every focusable element that draws, one at a time, and report each one's ring. `ring` and `selector` are
   spliced in as source, because this function is serialised into the page. */
const sweepFocus = (ring, selector) => {
  const found = [];
  for (const el of document.querySelectorAll(selector)) {
    if (!el.checkVisibility({ visibilityProperty: true })) continue;
    const box = el.getBoundingClientRect();
    if (box.width <= 2 || box.height <= 2) continue;
    el.focus({ preventScroll: true });
    if (document.activeElement === el) found.push(ring(el));
  }
  document.activeElement?.blur();
  return found;
};

/* ---- the worlds ---- */
async function scratchCopy() {
  const copy = await mkdtemp(join(tmpdir(), 'cargento-css-contract-'));
  for (const folder of ['frontend', 'cargento']) {
    await cp(join(REPOSITORY, folder), join(copy, folder), {
      recursive: true,
      filter: (path) =>
        !path.includes('/test-results') &&
        !path.includes('__pycache__') &&
        !path.includes('/frontend/test/golden') &&
        !path.includes('/frontend/test/fixtures'),
    });
  }
  await symlink(
    join(REPOSITORY, 'node_modules'),
    join(copy, 'node_modules'),
    process.platform === 'win32' ? 'junction' : 'dir',
  );
  for (const [file, needle, replacement] of MUTATIONS[MUTATION] ?? []) {
    const path = join(copy, 'frontend/src', file);
    const text = await readFile(path, 'utf8');
    assert.ok(text.includes(needle), `mutation ${MUTATION}: the text to break is not in ${file}`);
    await writeFile(path, text.replace(needle, replacement));
  }
  return copy;
}

async function startWorld(name, root) {
  const helper = {
    console: 'frontend/test/capacity_backend.py',
  }[name];
  if (name === 'sessions') {
    const board = await startSessionsBoard({ root });
    return { origin: board.react.origin, viteOrigin: board.react.viteOrigin, close: board.close };
  }
  if (name === 'intent') {
    const board = await startIntentBoard({ root });
    return { origin: board.react.origin, viteOrigin: board.react.viteOrigin, close: board.close };
  }
  const refused = [];
  for (let attempt = 0; ; attempt += 1) {
    const ports = await freePorts(2, refused);
    try {
      const dev = await startReactWorld({
        root,
        port: ports[0],
        vitePort: ports[1],
        backendHelper: join(root, helper),
      });
      return {
        origin: dev.origin,
        viteOrigin: dev.viteOrigin,
        state: join(dev.scratch, 'state'),
        close: () => dev.close(),
      };
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
}

/* ---- what is measured ---- */
const measured = {
  views: [],
  text: [],
  registers: null,
  sheets: [],
  schemes: [],
  focus: [],
  surfaces: new Set(),
  lightDiffers: [],
  lightChecked: 0,
  groups: [],
  buttons: [],
  chrome: [],
};

const SURFACES = {
  'the primary navigation': 'nav[aria-label="Primary"]',
  'the Sessions list': '.next-operations-header',
  'a session page': 'article.next-session-detail',
  'the Projects list': '.next-project-row',
  'a project page': '.next-cockpit-tabs',
  'the Attention board': '.next-attention',
  'the capacity strip': '.next-capacity-head',
  'the Intent log': '[data-next-view-body="intent"]',
  'the Drift card': '.next-session-drift',
  'a reading': '.next-cockpit-reading',
  'a stated absence':
    '[data-next-absent],[class*="-absent"],[class*="--absent"],[data-next-withheld]',
  'a disclosure': 'details',
  'a stored reading result': '.next-cockpit-result',
  'a running analysis': '.next-cockpit-reading-steps',
  'the capacity absence': '.next-capacity-absent',
  'a notice': '.next-notice,[role="alert"],[role="status"]:not(:empty)',
};

async function settle(page) {
  await page.waitForFunction(
    () =>
      document.querySelector('nav[aria-label="Primary"]') &&
      !/Waiting for the first board|first payload has not arrived/.test(document.body.innerText),
    null,
    { timeout: patience(15000) },
  );
  let previous = '';
  for (let n = 0; n < 12; n += 1) {
    const now = await page.evaluate(
      () => document.body.innerText.length + ':' + document.querySelectorAll('*').length,
    );
    if (now === previous) return;
    previous = now;
    await page.waitForTimeout(patience(100));
  }
}

async function visit(opened, origin, fragment, options = {}) {
  const { page } = opened;
  await page.goto('about:blank');
  await page.goto(`${origin}/${fragment}`);
  await settle(page);
  if (options.recordRead) await awaitRecordRead(page);
  const view = `${fragment}${options.narrow ? ' @375' : ''}`;
  const first = await measure(opened, view, options);
  // A control that changes what is drawn (a capacity window selects which one is read out) is pressed in turn,
  // so the text each choice reveals is measured too.
  if (options.press) {
    const count = await page.locator(options.press).count();
    for (let n = 0; n < count; n += 1) {
      await page.locator(options.press).nth(n).click();
      await page.waitForTimeout(patience(100));
      await measure(opened, `${view} [${options.press} #${n}]`, {});
    }
  }
  return first;
}

async function measure(opened, view, { walk = false } = {}) {
  const { page } = opened;
  measured.views.push(view);
  for (const row of await page.evaluate(`(${measureButtonChrome})(${normaliseButtonKey})`))
    measured.chrome.push({ view, ...row });
  const { rows, registers, groups, buttons, linkColour, scheme } = await page.evaluate(measureText);
  measured.registers ??= registers;
  measured.palette = registers;
  measured.linkColour = linkColour;
  for (const group of groups) measured.groups.push({ view, ...group });
  for (const button of buttons) measured.buttons.push({ view, ...button });
  measured.scheme = scheme;
  for (const row of rows) measured.text.push({ view, ...row });
  const sheets = await page.evaluate(measureSheets);
  measured.sheets.push(sheets);
  for (const [name, selector] of Object.entries(SURFACES))
    if (await page.evaluate((s) => Boolean(document.querySelector(s)), selector))
      measured.surfaces.add(name);

  // Focus: once by tabbing, as a keyboard reader meets the page, and once by selector over every
  // focusable element, so a control a tab order skips is still held to a ring.
  const stops = [];
  if (walk) {
    await page.evaluate(() => document.activeElement?.blur());
    for (let n = 0; n < 160; n += 1) {
      await page.keyboard.press('Tab');
      const stop = await page.evaluate(
        `(${ringOf})(document.activeElement === document.body ? null : document.activeElement)`,
      );
      if (!stop) break;
      stops.push({ view, how: 'tab', ...stop });
    }
  }
  const count = await page.evaluate((s) => document.querySelectorAll(s).length, FOCUSABLE);
  await page.keyboard.press('Tab');
  const bySelector = await page.evaluate(
    `(${sweepFocus})(${ringOf}, ${JSON.stringify(FOCUSABLE)})`,
  );
  for (const stop of bySelector) stops.push({ view, how: 'selector', ...stop });
  measured.focus.push(...stops);
  return { rows: rows.length, focusable: count };
}

/* The page under a light colour scheme: every element's colour and background must be what the dark run drew. */
async function lightCheck(opened, origin, fragment) {
  const { page } = opened;
  await page.goto('about:blank');
  await page.goto(`${origin}/${fragment}`);
  await settle(page);
  const paint = () =>
    page.evaluate(() => {
      const out = [];
      for (const el of document.body.querySelectorAll('*')) {
        const css = getComputedStyle(el);
        out.push(`${css.color}|${css.backgroundColor}|${css.borderTopColor}`);
      }
      const root = getComputedStyle(document.documentElement);
      return {
        count: out.length,
        paint: out.join('\n'),
        scheme: root.colorScheme,
        background: getComputedStyle(document.body).backgroundColor,
      };
    });
  const dark = await paint();
  await page.emulateMedia({ colorScheme: 'light' });
  const light = await paint();
  await page.emulateMedia({ colorScheme: 'dark' });
  measured.lightChecked += 1;
  if (dark.paint !== light.paint || dark.scheme !== light.scheme)
    measured.lightDiffers.push(`${fragment}: ${dark.background} against ${light.background}`);
}

/* A page of this world's own: the proof's pages refuse every request leaving the board. */
async function openWorldPage(browser, world, viewport) {
  const opened = await openPage(browser, [world.origin, world.viteOrigin], { viewport });
  await recordClipboard(opened.context);
  return opened;
}

const rowsOf = async (origin) => (await (await fetch(`${origin}/api/data`)).json()).sessions || [];
const sessionRoute = (row) => `#n=session:${E(row.project || '')}:${row.harness}:${E(row.sid)}`;

async function runSessions(browser, world) {
  const opened = await openWorldPage(browser, world, { width: 1280, height: 900 });
  try {
    const rows = await rowsOf(world.origin);
    const projects = [...new Set(rows.map((row) => row.project).filter(Boolean))];
    const first = rows[0];
    await visit(opened, world.origin, '#n=sessions', { walk: true });
    await visit(opened, world.origin, '#n=attention', { walk: true });
    await visit(opened, world.origin, '#n=projects', { walk: true });
    await visit(opened, world.origin, '#n=bogus');
    await lightCheck(opened, world.origin, '#n=sessions');
    await lightCheck(opened, world.origin, `#n=project:${E(projects[0])}`);
    await visit(opened, world.origin, `#n=session:${E(first.project || '')}:claude:gone`);
    for (const project of projects) {
      await visit(opened, world.origin, `#n=project:${E(project)}`, {
        walk: project === projects[0],
      });
      for (const tab of TABS.slice(1))
        await visit(opened, world.origin, `#n=project:${E(project)}:${tab}`);
    }
    for (const row of rows.slice(0, 16))
      await visit(opened, world.origin, sessionRoute(row), { walk: row === rows[0] });
  } finally {
    await opened.close();
  }
  const narrow = await openWorldPage(browser, world, { width: 375, height: 800 });
  try {
    const rows = await rowsOf(world.origin);
    await visit(narrow, world.origin, '#n=sessions', { narrow: true });
    await visit(narrow, world.origin, '#n=attention', { narrow: true });
    await visit(narrow, world.origin, '#n=projects', { narrow: true });
    await visit(narrow, world.origin, sessionRoute(rows[0]), { narrow: true });
  } finally {
    await narrow.close();
  }
}

async function runIntent(browser, world) {
  // The store is written through the page's own route, as the Intent proof sets it up.
  const data = (await call(world.origin, 'GET', '/api/data')).body;
  const write = async (sid, body) => {
    const row = data.sessions.find((s) => s.sid === sid);
    const out = await call(world.origin, 'POST', '/api/annotate', {
      harness: 'claude',
      sid,
      expected_revision: row.annotation_revision || 0,
      ...body,
    });
    assert.equal(out.body.ok, true, `the backend refused ${JSON.stringify(body)}`);
  };
  await write('intent-1', {
    goal: 'Fix the redirect for signed-in readers',
    lines: ['Readers land on the last page', 'Back still works'],
  });
  await write('intent-3', {
    adopt: 'first-prompt',
    expected_prompt: data.sessions.find((s) => s.sid === 'intent-3').first_prompt,
    expected_prompt_at: data.sessions.find((s) => s.sid === 'intent-3').first_prompt_at,
  });
  const opened = await openWorldPage(browser, world, { width: 1280, height: 900 });
  const script = freshScript();
  await installScript(opened.context, script);
  try {
    await visit(opened, world.origin, '#n=intent', { walk: true });
    const generated = (await call(world.origin, 'GET', '/api/data')).body.generated;
    const claude = (extra = {}) => ({
      session: {
        ...SAVED(generated),
        state: 'idle',
        turn_end_at: generated - 200,
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
    });
    const stored = claude({
      session: { annotation_assessment: ASSESSMENT(generated), annotation_reading_count: 1 },
      facts: RECORD(generated),
    });
    const job = {
      id: 'job-1',
      phase: 'read',
      steps: [
        { phase: 'collect', text: 'Collecting the record' },
        { phase: 'read', text: 'Reading it' },
        { phase: 'write', text: 'Writing the result' },
      ],
    };
    const states = {
      'no reading': claude(),
      'a stored reading': stored,
      'an analysis running': claude({
        session: { state: 'working' },
        payload: { reading_jobs: { 'claude:intent-2': job } },
      }),
      'an Allow owed': claude({ payload: { reading: UNCONSENTED } }),
      'a model off': claude({
        payload: { reading: { reason: 'run-disabled', used: 0, limit: 10 } },
      }),
      'a reading refused': claude({
        session: { annotation_reading_refused: true, annotation_reading_count: 1 },
      }),
    };
    let walked = false;
    for (const next of Object.values(states)) {
      for (const key of Object.keys(script)) delete script[key];
      Object.assign(script, freshScript(), next);
      await visit(opened, world.origin, `#n=session:${E('w/alpha')}:claude:intent-2`, {
        walk: !walked,
        recordRead: true,
      });
      walked = true;
    }
    for (const key of Object.keys(script)) delete script[key];
    Object.assign(script, freshScript());
    await visit(opened, world.origin, `#n=session:${E('w/alpha')}:claude:intent-1`, {
      recordRead: true,
    });
    await visit(opened, world.origin, `#n=session:${E('')}:claude:intent-3`);
  } finally {
    await opened.close();
  }
}

/* The quota provider and the observer offer are steered from one control file the backend reads on every call; a
   steer that changes the windows waits for the board's own publish interval, then reads the board once. */
async function steer(world, control) {
  await mkdir(join(world.state, 'capacity-fixture'), { recursive: true });
  await writeFile(join(world.state, 'capacity-fixture/control.json'), JSON.stringify(control));
  await new Promise((done) => setTimeout(done, 2700));
  await fetch(`${world.origin}/api/data`, { signal: AbortSignal.timeout(5000) }).then((r) =>
    r.arrayBuffer(),
  );
}

async function runConsole(browser, world) {
  const opened = await openWorldPage(browser, world, { width: 1280, height: 900 });
  const CONSOLE = `#n=project:${E('alpha/app')}:${E('claude:live-work')}:console`;
  try {
    const rows = await rowsOf(world.origin);
    const project = 'alpha/app';
    await visit(opened, world.origin, '#n=sessions', {
      walk: true,
      press: '.next-capacity-window button',
    });
    for (const tab of TABS) {
      for (const focus of [null, 'claude:live-work', 'claude:gate-open', 'claude:workflow-run']) {
        const fragment = `#n=project:${E(project)}${focus ? `:${E(focus)}` : ''}:${tab}`;
        await visit(opened, world.origin, fragment, { walk: tab === 'console' && !focus });
      }
    }
    await visit(opened, world.origin, `#n=project:${E('beta/api')}:console`);
    for (const row of rows.slice(0, 8)) await visit(opened, world.origin, sessionRoute(row));
    // The states the strip and the consent say least in: no window published, then fewer clocks.
    await steer(world, { windows: 'none', observer: 'absent' });
    await visit(opened, world.origin, '#n=sessions');
    await visit(opened, world.origin, CONSOLE);
    await steer(world, { windows: 'fewer', observer: 'no-disclosure' });
    await visit(opened, world.origin, '#n=sessions', { press: '.next-capacity-window button' });
    await visit(opened, world.origin, CONSOLE);
  } finally {
    await opened.close();
  }
}

const RUNNERS = { sessions: runSessions, intent: runIntent, console: runConsole };

/* ---- the checks ---- */
/* An element named by its last three path segments, modifier classes (`--want`, `--ok`) dropped: the shape a
   person would go and look at, and one that does not change with the board's state. */
const key = (row) =>
  row.at
    .split(' > ')
    .slice(-3)
    .join(' > ')
    .replace(/\.[\w-]*--[\w-]+/g, '');
const shape = (row) => `${key(row)} "${row.text}"`;
const keys = (rows) => new Set(rows.map(key));
const rgbOf = (colour) => colour.replace(/\s+/g, '');

/* Exceptions are named, with the reason, and held as sets: a new one fails, and so does a stale one (when the run
   reached every world), because the fix that removes the cause has to remove the excuse with it. */
const FULL = !MUTATION && WORLDS.length === 3;
function exactly(found, allowed, what) {
  const unlisted = [...found].filter((item) => !allowed.has(item)).sort();
  assert.deepEqual(unlisted, [], `${what}: these are not in the inventory of exceptions`);
  if (FULL) {
    const stale = [...allowed].filter((item) => !found.has(item)).sort();
    assert.deepEqual(stale, [], `${what}: these exceptions no longer occur, so remove them`);
  }
}

/* Prose that draws at the 13px label step although it is a sentence. Captions, counts and meta lines under a
   heading, and the empty-state lines of the timeline and workstream, are deliberately one step down; the set is
   what was measured, so a sentence rule that slips from the 15px step lands outside it. */
const SENTENCES_AT_LABEL = new Set(INVENTORY.sentencesAtLabel);

/* An absence drawn larger than the element it sits in. Both stand where a figure or a title would, so they take
   the size of the thing they replace. */
const ABSENCES_LARGER_THAN_THEIR_PARENT = new Set(INVENTORY.absencesLarger);

/* Focusable elements that draw the browser's own focus ring, not one the stylesheet authors. Visible on the
   dark page, and the same ring the previous interface drew for them; each is a place the sheet could say more. */
const UA_FOCUS_RING = new Set(INVENTORY.uaFocusRing);

/* Links that draw in the browser's link colour because no rule colours them, as the previous page's did. */
const UA_COLOURED_LINKS = new Set(INVENTORY.uaLinks);

/* Headings that draw at the browser's default heading size, off the five steps, as the previous page's did. */
const OFF_SCALE_HEADINGS = new Set(INVENTORY.offScale);

/* A real defect the guard found in the shipped sheets, pinned so the run stays green until the fix lands and
   fails the moment it does without its pin being removed. */
const UNRESOLVED_VARIABLES = new Set(INVENTORY.unresolved);

const STEPS_PX = [13, 15, 18, 24, 34];

function checks() {
  const text = measured.text.filter((row) => !row.hidden);
  const regs = measured.registers;

  step_('buttons: every real-route instance keeps its pre-adoption chrome', () => {
    const failures = new Map();
    const seen = new Set();
    for (const row of measured.chrome) {
      const expected = BUTTON_REFERENCE[row.key];
      seen.add(row.key);
      if (!expected) failures.set(row.key, { view: row.view, missing: true, actual: row.chrome });
      else {
        const changed = Object.keys(expected).filter(
          (property) => row.chrome[property] !== expected[property],
        );
        if (changed.length)
          failures.set(
            row.key,
            Object.fromEntries(
              changed.map((property) => [
                property,
                { expected: expected[property], actual: row.chrome[property] },
              ]),
            ),
          );
      }
    }
    if (failures.size)
      console.error(
        JSON.stringify({ buttonChromeDifferences: Object.fromEntries(failures) }, null, 2),
      );
    assert.equal(failures.size, 0, 'Button cascade changed; differences are printed above');
    if (FULL)
      assert.deepEqual(
        Object.keys(BUTTON_REFERENCE).filter((key) => !seen.has(key)),
        [],
        'reference Button identities were not reached',
      );
    assert.ok(measured.chrome.length >= 150, 'too few Button instances reached the chrome gate');
    return `${measured.chrome.length} instances against 30bac258`;
  });

  step_('coverage: the render reaches the surfaces this proof speaks for', () => {
    assert.ok(measured.views.length >= 40, `only ${measured.views.length} views were measured`);
    assert.ok(text.length >= 4000, `only ${text.length} text elements were measured`);
    const missing = Object.keys(SURFACES).filter((name) => !measured.surfaces.has(name));
    assert.deepEqual(missing, [], `these surfaces were never drawn: ${missing.join(', ')}`);
    assert.ok(text.filter((row) => row.absence).length >= 60, 'too few absences were drawn');
    assert.ok(text.filter((row) => row.control).length >= 400, 'too few controls were drawn');
    assert.ok(measured.buttons.length >= 150, 'too few buttons were drawn');
    const tabbed = measured.focus.filter((stop) => stop.how === 'tab');
    assert.ok(tabbed.length >= 60, `the keyboard reached only ${tabbed.length} stops`);
    assert.ok(measured.focus.length >= 400, `only ${measured.focus.length} focus stops`);
    return `${measured.views.length} views, ${text.length} text elements, ${measured.focus.length} focus stops`;
  });

  step_('floor: nothing that owns text computes below the 13px label step', () => {
    const drawn = text.filter((row) => row.px > 0);
    const below = drawn.filter((row) => row.px < LABEL_PX - 0.01);
    assert.deepEqual([...new Set(below.map((row) => `${shape(row)} ${row.px}px`))], []);
    // A 0px element hands its words to a pseudo-element; that one must be on the floor, not just present.
    for (const row of text.filter((r) => r.px === 0 && !r.pseudo)) {
      const drawnBy = text.filter(
        (other) => other.pseudo && other.view === row.view && other.at.startsWith(row.at),
      );
      assert.ok(
        drawnBy.length > 0 && drawnBy.every((other) => other.px >= LABEL_PX - 0.01),
        `${key(row)} computes 0px and nothing at the floor draws in its place`,
      );
    }
  });

  step_('scale: every size is one of the five steps', () => {
    const off = text.filter((row) => row.px > 0 && !STEPS_PX.some((step) => near(step, row.px)));
    exactly(keys(off), OFF_SCALE_HEADINGS, 'sizes off the five steps');
  });

  step_('sentences: prose in the sans family sits on the 15px step', () => {
    const prose = text.filter(
      (row) => row.words >= 4 && !row.mono && !row.upper && !row.control && !row.pseudo,
    );
    assert.ok(prose.length >= 500, `only ${prose.length} sentences were drawn`);
    const below = prose.filter((row) => row.px < SENTENCE_PX - 0.01);
    exactly(keys(below), SENTENCES_AT_LABEL, 'sentences below the 15px step');
    return `${prose.length} sentences, ${keys(below).size} shapes at the label step`;
  });

  step_(
    'absence: sans, in the absence ink, never above the 15px step or the element it sits in',
    () => {
      const absences = text.filter((row) => row.absence && !row.pseudo);
      const mono = absences.filter((row) => row.mono);
      assert.deepEqual(
        [...keys(mono)],
        [],
        'an absence in the mono family reads as a string a source published',
      );
      const ink = absences.filter((row) => rgbOf(row.color) !== rgbOf(regs['--ink-absence']));
      assert.deepEqual(
        [...new Set(ink.map((row) => `${key(row)} ${row.color}`))],
        [],
        `an absence outside the absence ink ${regs['--ink-absence']}`,
      );
      const larger = absences.filter((row) => row.px > row.parentPx + 0.01);
      exactly(keys(larger), ABSENCES_LARGER_THAN_THEIR_PARENT, 'absences larger than their parent');
      const inverted = absences.filter((row) => row.twinPx !== null && row.px > row.twinPx + 0.01);
      assert.deepEqual(
        [...new Set(inverted.map((row) => `${key(row)} ${row.px}px against ${row.twinPx}px`))],
        [],
        'an absence outranks the value it replaces',
      );
      const tall = absences.filter((row) => row.px > STEPS_PX[2] + 0.01);
      assert.deepEqual([...keys(tall)], [], 'an absence above the value step reads as a headline');
      return `${absences.length} absences, ${keys(absences).size} shapes`;
    },
  );

  step_('ink: the registers are separate from the value ink, and each role spends its own', () => {
    assert.equal(rgbOf(regs['--ink-value']), rgbOf(regs['--ink']));
    assert.equal(
      rgbOf(regs['--ink-label']),
      rgbOf(regs['--ink-absence']),
      'label and absence share the muted register',
    );
    assert.equal(rgbOf(regs['--ink-label']), rgbOf(regs['--ink-caption']));
    assert.notEqual(rgbOf(regs['--ink-label']), rgbOf(regs['--ink-value']));
    // A label: the mono, bold, tracked caption above a value. Status colours may take it; the value ink may not.
    const status = new Set(
      ['--accent', '--accent-dim', '--amber', '--clay'].map((name) =>
        rgbOf(measured.palette[name]),
      ),
    );
    const labels = text.filter(
      (row) =>
        row.mono &&
        row.weight >= 600 &&
        row.spacing > 0 &&
        row.px <= LABEL_PX + 0.01 &&
        !['strong', 'b', 'a', 'button'].includes(row.tag) &&
        !row.control,
    );
    assert.ok(labels.length >= 300, `only ${labels.length} labels were drawn`);
    const off = labels.filter(
      (row) => rgbOf(row.color) !== rgbOf(regs['--ink-label']) && !status.has(rgbOf(row.color)),
    );
    assert.deepEqual(
      [...new Set(off.map((row) => `${key(row)} ${row.color}`))],
      [],
      'labels outside the label register',
    );
    // The third ink belongs to what is inactive (a disabled control, a step not yet reached, an unchecked row).
    const third = text.filter((row) => rgbOf(row.color) === rgbOf(regs['--ink3']) && !row.disabled);
    assert.deepEqual([...keys(third)], [], 'text in the third ink that is not inactive');
    // Everything else is in the palette: the two inks, the status colours, or the browser's link colour.
    const palette = new Set([
      rgbOf(regs['--ink']),
      rgbOf(regs['--ink2']),
      rgbOf(regs['--ink3']),
      ...status,
    ]);
    const stray = text.filter((row) => !palette.has(rgbOf(row.color)));
    const links = stray.filter((row) => rgbOf(row.color) === rgbOf(measured.linkColour));
    exactly(keys(links), UA_COLOURED_LINKS, 'links in the browser link colour');
    const other = stray.filter((row) => rgbOf(row.color) !== rgbOf(measured.linkColour));
    assert.deepEqual(
      [...new Set(other.map((row) => `${key(row)} ${row.color}`))],
      [],
      'text outside the palette',
    );
    return `${labels.length} labels`;
  });

  step_(
    'controls: at the label step or above; actions on the sentence step; neighbours agree',
    () => {
      const small = measured.buttons.filter((b) => b.px > 0 && b.px < LABEL_PX - 0.01 && b.text);
      assert.deepEqual([...new Set(small.map((b) => `${key(b)} ${b.px}px`))], []);
      const actions = measured.buttons.filter((b) => b.action);
      assert.ok(actions.length >= 40, `only ${actions.length} actions were drawn`);
      const off = actions.filter((b) => !near(b.px, SENTENCE_PX));
      assert.deepEqual(
        [...new Set(off.map((b) => `${key(b)} ${b.px}px`))],
        [],
        'actions off the sentence step',
      );
      const split = measured.groups.filter(
        (group) => new Set(group.buttons.map((b) => b.px)).size > 1,
      );
      assert.deepEqual(
        [
          ...new Set(
            split.map(
              (group) =>
                `${group.at}: ${group.buttons.map((b) => `${b.text} ${b.px}px`).join(', ')}`,
            ),
          ),
        ],
        [],
        'controls that touch disagree on a size',
      );
      assert.ok(measured.groups.length >= 3, 'no controls sat side by side');
      return `${actions.length} actions, ${measured.groups.length} neighbouring groups`;
    },
  );

  step_('variables: every custom property a rule uses resolves', () => {
    const unresolved = new Set();
    for (const sheet of measured.sheets) {
      const declared = new Set(sheet.declared);
      for (const use of sheet.used) if (!declared.has(use.name)) unresolved.add(use.name);
    }
    assert.ok(
      measured.sheets.every((sheet) => sheet.rules > 500),
      'the stylesheets were not read',
    );
    exactly(unresolved, UNRESOLVED_VARIABLES, 'custom properties used and never declared');
  });

  step_('palette: dark only, and a light-scheme browser draws the same page', () => {
    const named = measured.sheets.flatMap((sheet) => sheet.schemes);
    assert.deepEqual([...new Set(named)], [], 'a rule keyed to prefers-color-scheme');
    assert.equal(measured.scheme, 'dark');
    assert.deepEqual(measured.lightDiffers, [], 'the page changed under a light colour scheme');
    assert.ok(measured.lightChecked >= 2, 'the light scheme was never tried');
  });

  step_('focus: every focusable element shows a ring when the keyboard reaches it', () => {
    const lost = measured.focus.filter((stop) => !stop.focusVisible);
    assert.deepEqual(
      [...new Set(lost.map((stop) => `${stop.label}`))],
      [],
      'a stop the keyboard could not mark focus-visible',
    );
    const bare = measured.focus.filter((stop) => !stop.outline && !stop.shadow);
    assert.deepEqual(
      [...new Set(bare.map((stop) => `${stop.view} ${stop.label}`))],
      [],
      'focusable elements with no ring',
    );
    const borrowed = measured.focus.filter(
      (stop) => !stop.shadow && /^auto /.test(stop.outline || ''),
    );
    const byLabel = new Set(borrowed.map((stop) => labelKey(stop.label)));
    exactly(byLabel, UA_FOCUS_RING, 'focusable elements on the browser ring');
    return `${measured.focus.length} stops, ${byLabel.size} shapes on the browser ring`;
  });
}

const labelKey = (label) => label.replace(/\.[\w-]*--[\w-]+/g, '');

function step_(name, run) {
  pending.push([name, run]);
}
const pending = [];

async function checkButtonGallery(browser) {
  const gallery = await scratchCopy();
  let world;
  try {
    await writeFile(
      join(gallery, 'frontend/src/main.tsx'),
      "import { mountGallery } from './controls/gallery';\nconst root = document.getElementById('root');\nif (!root) throw new Error('missing root');\nmountGallery(root);\n",
    );
    const [port, vitePort] = await freePorts(2);
    world = await startReactWorld({
      root: gallery,
      port,
      vitePort,
      backendHelper: join(gallery, 'frontend/e2e/controls-backend.py'),
    });
    const opened = await openPage(browser, [world.origin, world.viteOrigin]);
    try {
      for (const width of [1280, 320]) {
        await opened.page.setViewportSize({ width, height: 900 });
        await opened.page.goto(world.origin);
        await opened.page.locator('[data-button-gallery]').waitFor();
        await opened.page.evaluate(() => document.fonts.ready);
        const buttons = await opened.page
          .locator('[data-button-gallery] [data-example]')
          .evaluateAll((elements) =>
            elements.map((el) => {
              const box = el.getBoundingClientRect(),
                css = getComputedStyle(el);
              return {
                example: el.dataset.example,
                width: box.width,
                height: box.height,
                px: parseFloat(css.fontSize),
              };
            }),
          );
        assert.equal(buttons.length, 12);
        assert.deepEqual(
          buttons.filter((b) => b.width < 44 || b.height < 44),
          [],
          'gallery controls have 44 px targets',
        );
        assert.deepEqual(
          buttons.filter((b) => b.px !== 15),
          [],
          'gallery controls agree on the control tier',
        );
        await opened.page.keyboard.press('Tab');
        for (const example of ['focus', 'pending', 'link']) {
          const control = opened.page.locator(`[data-example="${example}"]`);
          await control.focus();
          const ring = await control.evaluate((el) => ({
            width: getComputedStyle(el).outlineWidth,
            style: getComputedStyle(el).outlineStyle,
          }));
          assert.equal(ring.width, '2px');
          assert.equal(ring.style, 'solid');
        }
        const hover = opened.page.locator('[data-example="hover"]');
        assert.equal(
          await opened.page
            .locator('[data-example="retry"]')
            .evaluate((el) => getComputedStyle(el).borderTopStyle),
          'solid',
          'a refresh retry keeps the solid waiting boundary',
        );
        await hover.hover();
        assert.equal(
          await hover.evaluate((el) => getComputedStyle(el).borderColor),
          'rgb(138, 136, 116)',
        );
        assert.equal(await opened.page.getByRole('link', { name: 'Linked action' }).count(), 1);
        const raise = opened.page.locator('[data-example="raise-primary"]');
        await raise.evaluate((el) => el.setAttribute('data-raise-state', 'declined'));
        assert.deepEqual(
          await raise.evaluate((el) => ({
            border: getComputedStyle(el).borderColor,
            ink: getComputedStyle(el).color,
          })),
          { border: 'rgb(116, 114, 95)', ink: 'rgb(205, 199, 180)' },
          'primary Raise keeps its declined cue',
        );
        for (const state of ['throttled', 'stale']) {
          await raise.evaluate((el, value) => el.setAttribute('data-raise-state', value), state);
          assert.equal(
            await raise.evaluate((el) => getComputedStyle(el).borderColor),
            'rgb(240, 185, 94)',
            `primary Raise keeps its ${state} amber cue`,
          );
        }
        const memo = opened.page.getByRole('button', {
          name: 'Edit OUTCOME',
          exact: true,
        });
        assert.equal(await memo.count(), 1, 'the gallery reaches the memo edit control');
        assert.deepEqual(
          await memo.evaluate((el) => {
            const css = getComputedStyle(el);
            return {
              ink: css.color,
              background: css.backgroundColor,
              padding: css.padding,
              font: css.fontSize,
              border: css.borderTop,
            };
          }),
          {
            ink: 'rgb(246, 243, 234)',
            background: 'rgba(0, 0, 0, 0)',
            padding: '9px 14px',
            font: '15px',
            border: '1px solid rgb(116, 114, 95)',
          },
        );
        const reserved = opened.page.locator('[data-example="reserved"]');
        const before = await reserved.boundingBox();
        await reserved.click();
        await opened.page.locator('[data-example="reserved"][aria-busy="true"]').waitFor();
        assert.deepEqual(
          await reserved.boundingBox(),
          before,
          'pending keeps an explicit reservation',
        );
        assert.equal(
          await opened.page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
          false,
        );
      }
      return '12 examples at 1280 and 320 px; targets, type, hover, focus, retry, raise state, memo chrome, reserved width and link semantics';
    } finally {
      await opened.close();
    }
  } finally {
    await world?.close();
    await rm(gallery, { recursive: true, force: true });
  }
}

/* ---- main ---- */
const browser = await chromium.launch();
let copy = null;
try {
  if (MUTATION) {
    assert.ok(MUTATIONS[MUTATION], `unknown mutation ${MUTATION}`);
    copy = await scratchCopy();
  }
  await step('gallery: shared buttons at desktop and 320 px', () => checkButtonGallery(browser));
  const root = copy || REPOSITORY;
  for (const name of WORLDS) {
    const started = Date.now();
    const world = await startWorld(name, root);
    try {
      await RUNNERS[name](browser, world);
    } finally {
      await world.close();
    }
    receipts[`world ${name}`] = `${Math.round((Date.now() - started) / 1000)}s`;
  }
} catch (error) {
  failures.push({ name: 'run', message: String(error.stack || error).slice(0, 4000) });
} finally {
  await browser.close();
  if (copy) await rm(copy, { recursive: true, force: true });
}

if (!failures.some((failure) => failure.name === 'run')) {
  checks();
  for (const [name, run] of pending) await step(name, run);
}
console.log(JSON.stringify({ css: receipts }, null, 2));
if (failures.length) {
  console.error(JSON.stringify({ failures }, null, 2));
  process.exitCode = 1;
}
