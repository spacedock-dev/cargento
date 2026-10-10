import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ControlsProvider, Disclosure } from '../src/controls';
import { testControls } from '../src/controls/testControls';
import { firstShapeDifference, shape } from '../src/delegation/dom.test.helper';
import { disclosureReadings, normalizeDisclosures } from './disclosures';

function fixture(open: boolean) {
  const kit = testControls();
  kit.controls.disclosures.set('first', open);
  const view = render(
    <ControlsProvider controls={kit.controls}>
      <section>
        <Disclosure disclosureKey="first" className="next-proof" summary="First summary">
          <p>
            First body <strong>with evidence</strong>
          </p>
        </Disclosure>
        <Disclosure disclosureKey="second" summary="Second summary">
          <p>Second body</p>
        </Disclosure>
      </section>
    </ControlsProvider>,
  );
  const template = document.createElement('template');
  template.innerHTML = `<section><details class="ctl-disclosure next-proof"${open ? ' open' : ''}><summary>First summary</summary><p>First body <strong>with evidence</strong></p></details><details class="ctl-disclosure"><summary>Second summary</summary><p>Second body</p></details></section>`;
  const legacy = template.content.firstElementChild as Element;
  const root = view.container.firstElementChild as Element;
  const reading = () => shape(root);
  const readings = () => disclosureReadings(normalizeDisclosures(root));
  const expected = [
    { summary: 'First summary', open, body: 'First body with evidence' },
    { summary: 'Second summary', open: false, body: 'Second body' },
  ];
  return { root, legacy: shape(legacy), reading, readings, expected };
}

describe('recorded disclosure normalization', () => {
  for (const open of [false, true]) {
    it(`keeps summary, body and ${open ? 'open' : 'closed'} state equivalent to native details`, () => {
      const made = fixture(open);
      expect(firstShapeDifference(made.legacy, made.reading())).toBeNull();
      expect(made.readings()).toEqual(made.expected);
      expect(normalizeDisclosures(made.root).textContent).toBe(
        'First summaryFirst body with evidenceSecond summarySecond body',
      );
      expect(made.root.querySelector('[data-slot="accordion"]')).not.toBeNull();
    });
  }

  const mutations: readonly [string, (root: Element) => void][] = [
    ['missing body', (root) => root.querySelector('[data-slot="accordion-content"] p')?.remove()],
    [
      'changed body',
      (root) => {
        const body = root.querySelector('p');
        if (body) body.textContent = 'Other evidence';
      },
    ],
    [
      'renamed summary',
      (root) => {
        const trigger = root.querySelector('[data-slot="accordion-trigger"]');
        if (trigger?.firstChild) trigger.firstChild.textContent = 'Other summary';
      },
    ],
    [
      'flipped open state',
      (root) => {
        const disclosure = root.querySelector('[data-slot="accordion"]');
        disclosure?.setAttribute('data-open', '');
        disclosure
          ?.querySelector('[data-slot="accordion-trigger"]')
          ?.setAttribute('aria-expanded', 'true');
      },
    ],
    ['removed disclosure', (root) => root.querySelector('[data-slot="accordion"]')?.remove()],
    [
      'reordered disclosures',
      (root) => {
        const disclosure = root.firstElementChild;
        if (disclosure) root.append(disclosure);
      },
    ],
    [
      'reordered body',
      (root) => {
        const body = root.querySelector('p');
        const evidence = body?.querySelector('strong');
        if (body && evidence) body.prepend(evidence);
      },
    ],
  ];
  for (const [name, mutate] of mutations) {
    it(`rejects a ${name}`, () => {
      const made = fixture(false);
      expect(firstShapeDifference(made.legacy, made.reading())).toBeNull();
      expect(made.readings()).toEqual(made.expected);
      mutate(made.root);
      expect(firstShapeDifference(made.legacy, made.reading())).not.toBeNull();
      expect(made.readings()).not.toEqual(made.expected);
    });
  }

  for (const selector of ['accordion-trigger', 'accordion-content']) {
    it(`rejects a missing ${selector}`, () => {
      const made = fixture(false);
      expect(firstShapeDifference(made.legacy, made.reading())).toBeNull();
      made.root.querySelector(`[data-slot="${selector}"]`)?.remove();
      expect(made.reading).toThrow('A disclosure lost or reordered its trigger or panel.');
    });
  }
});

function popoverFixture(open: boolean) {
  const kit = testControls();
  kit.controls.disclosures.set('popover-first', open);
  const view = render(
    <ControlsProvider controls={kit.controls}>
      <div id="app">
        <section>
          <Disclosure
            disclosureKey="popover-first"
            variant="popover"
            className="next-proof"
            summary="First summary"
          >
            <p>
              First body <strong>with evidence</strong>
            </p>
          </Disclosure>
          <Disclosure disclosureKey="popover-second" variant="popover" summary="Second summary">
            <p>Second body</p>
          </Disclosure>
        </section>
      </div>
    </ControlsProvider>,
  );
  const root = view.container.querySelector('section') as Element;
  const template = document.createElement('template');
  template.innerHTML = `<section><details class="ctl-disclosure ctl-disclosure--pop next-proof"${open ? ' open' : ''}><summary>First summary</summary><p>First body <strong>with evidence</strong></p></details><details class="ctl-disclosure ctl-disclosure--pop"><summary>Second summary</summary><p>Second body</p></details></section>`;
  const legacy = template.content.firstElementChild as Element;
  return {
    root,
    app: view.container.querySelector('#app') as Element,
    legacy: shape(legacy),
    reading: () => shape(root),
    readings: () => disclosureReadings(normalizeDisclosures(root)),
    expected: [
      { summary: 'First summary', open, body: 'First body with evidence' },
      { summary: 'Second summary', open: false, body: 'Second body' },
    ],
  };
}

describe('recorded popover disclosure normalization', () => {
  for (const open of [false, true]) {
    it(`keeps portalled bodies and ${open ? 'open' : 'closed'} state equivalent to native details`, () => {
      const made = popoverFixture(open);
      expect(made.root.querySelector('[data-slot=popover-content]')).toBeNull();
      expect(made.app.querySelectorAll('[data-slot=popover-content]')).toHaveLength(2);
      expect(firstShapeDifference(made.legacy, made.reading())).toBeNull();
      expect(made.readings()).toEqual(made.expected);
      expect(disclosureReadings(normalizeDisclosures(made.app))).toEqual(made.expected);
      expect(normalizeDisclosures(made.app).textContent).toBe(
        'First summaryFirst body with evidenceSecond summarySecond body',
      );
      expect(made.root.querySelector('[data-slot=popover-trigger]')).not.toBeNull();
      expect(made.app.querySelectorAll('[data-slot=popover-content]')).toHaveLength(2);
    });
  }

  const mutations: readonly [string, (made: ReturnType<typeof popoverFixture>) => void][] = [
    [
      'changed body',
      (made) => {
        const body = made.app.querySelector('[data-slot=popover-content] p');
        if (body) body.textContent = 'Other evidence';
      },
    ],
    [
      'renamed summary',
      (made) => {
        const trigger = made.root.querySelector('[data-slot=popover-trigger]');
        if (trigger?.firstChild) trigger.firstChild.textContent = 'Other summary';
      },
    ],
    [
      'flipped open state',
      (made) => {
        const disclosure = made.root.querySelector('[data-slot=popover]');
        disclosure?.setAttribute('data-open', '');
        disclosure
          ?.querySelector('[data-slot=popover-trigger]')
          ?.setAttribute('aria-expanded', 'true');
      },
    ],
  ];
  for (const [name, mutate] of mutations) {
    it(`rejects a popover with ${name}`, () => {
      const made = popoverFixture(false);
      expect(firstShapeDifference(made.legacy, made.reading())).toBeNull();
      expect(made.readings()).toEqual(made.expected);
      mutate(made);
      expect(firstShapeDifference(made.legacy, made.reading())).not.toBeNull();
      expect(made.readings()).not.toEqual(made.expected);
    });
  }
  for (const missing of ['trigger', 'panel']) {
    it(`rejects a missing popover ${missing}`, () => {
      const made = popoverFixture(false);
      expect(made.readings()).toEqual(made.expected);
      (missing === 'trigger'
        ? made.root.querySelector('[data-slot=popover-trigger]')
        : made.app.querySelector('[data-slot=popover-content]')
      )?.remove();
      expect(made.reading).toThrow('A popover disclosure lost its trigger or labelled panel.');
    });
  }
  it('rejects ambiguously labelled popup bodies', () => {
    const made = popoverFixture(false);
    const panel = made.app.querySelector('[data-slot=popover-content]');
    if (panel) made.app.append(panel.cloneNode(true));
    expect(made.reading).toThrow('A popover disclosure lost its trigger or labelled panel.');
  });
  it('rejects inconsistent popover open state', () => {
    const made = popoverFixture(false);
    made.root.querySelector('[data-slot=popover]')?.setAttribute('data-open', '');
    expect(made.reading).toThrow('A disclosure has inconsistent open state.');
  });
});
