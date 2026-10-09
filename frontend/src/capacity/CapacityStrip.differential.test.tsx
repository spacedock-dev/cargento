import { describe, expect, it } from 'vitest';
import { firstShapeDifference, shape } from '../delegation/dom.test.helper';
import { mulberry32, pick } from '../observed/generate.test.helper';
import { mountPanels } from '../steering/testing';
import { CapacityStrip } from './CapacityStrip';
import { genCapacity } from './generate.test.helper';
import { heldFor } from './held';
import { loadLegacyCapacity, type LegacyConsent } from './legacy.test.helper';
import { RailUsage } from './UsageConsent';

/* The strip is held to the legacy page by what a reader can read and press. The page's own `nextCapacityView`
   runs over a generated board, in each consent state and with a selection that is published, buried below
   the initial rows or no longer published, and so does the component; both are reduced to one tree and
   compared: the disclosure, every row with its bar, pace, end and reset, the model lines, the "more windows"
   count, the prospect and the switch. The selection each leaves behind is compared too.

   One deliberate difference is normalised: the page printed "and null readings" for a recent pace measured at
   zero whose reading count was not published, which is a number replaced by an absence; the port leaves the
   clause out. */
const legacy = loadLegacyCapacity();
const SEEDS = 350;
const CONSENT = 'cargento.next.usage.consent';

const parse = (html: string): Element[] => {
  const template = document.createElement('template');
  template.innerHTML = html.replace(' and null readings', '');
  return [...template.content.children];
};

describe('the capacity strip agrees with the legacy page', () => {
  it(`over ${String(SEEDS)} generated boards in every consent state`, async () => {
    const failures: string[] = [];
    const seen = {
      drawn: 0,
      disclosure: 0,
      switchOn: 0,
      switchOff: 0,
      more: 0,
      models: 0,
      prospect: 0,
      buried: 0,
      stale: 0,
    };
    for (let seed = 1; seed <= SEEDS && failures.length < 3; seed += 1) {
      const rnd = mulberry32(seed * 31 + 7);
      const { payload, keys } = genCapacity(seed);
      const consent = pick<LegacyConsent>(rnd, [null, 'granted', 'declined']);
      const selected = pick(rnd, ['', 'ghost:week', ...keys, ...keys]);
      const html = legacy.view(payload, { consent, selected });
      const page = mountPanels(
        (shell) => {
          heldFor(shell.runtime).selection.set(selected);
          return (
            <div data-test-root="">
              <CapacityStrip />
            </div>
          );
        },
        { data: payload, strict: false, storage: consent ? { [CONSENT]: consent } : {} },
      );
      await page.settle();
      const mine = [...(page.container.querySelector('[data-test-root]')?.children ?? [])];
      const theirs = parse(html);
      const label = `seed ${String(seed)} consent ${String(consent)} selected ${JSON.stringify(selected)}`;
      if (theirs.length !== mine.length) {
        failures.push(`${label}: ${String(theirs.length)} blocks != ${String(mine.length)}`);
      } else {
        for (let index = 0; index < theirs.length; index += 1) {
          const found = firstShapeDifference(
            shape(theirs[index] as Element),
            shape(mine[index] as Element),
          );
          if (found) {
            failures.push(`${label} block ${String(index)}: ${found}`);
            break;
          }
        }
      }
      const held = heldFor(page.shell.runtime).selection.read();
      if (held !== legacy.selected()) {
        failures.push(
          `${label}: held selection ${JSON.stringify(held)} != ${JSON.stringify(legacy.selected())}`,
        );
      }
      const root = page.container;
      seen.drawn += root.querySelector('[data-next-capacity]') ? 1 : 0;
      seen.disclosure += root.querySelector('[data-next-usage-consent]') ? 1 : 0;
      seen.switchOn += root.textContent?.includes('Vendor quota fetch: on') ? 1 : 0;
      seen.switchOff += root.textContent?.includes('Vendor quota fetch: off') ? 1 : 0;
      seen.more += root.querySelector('.next-capacity-more') ? 1 : 0;
      seen.models += root.querySelector('[data-next-capacity-models]') ? 1 : 0;
      seen.prospect += root.querySelector('.next-capacity-prospect') ? 1 : 0;
      seen.stale += root.querySelector('.next-capacity-prospect small') ? 1 : 0;
      const pressed = root.querySelector('button[aria-pressed="true"]');
      const rows = [...root.querySelectorAll('[data-next-capacity-row]')];
      seen.buried +=
        pressed && rows.length === 3 && pressed.closest('[data-next-capacity-row]') === rows[2]
          ? 1
          : 0;
      page.unmount();
    }
    expect(failures).toEqual([]);
    // The comparison is not vacuous: every branch the strip words differently is reached.
    expect(seen.drawn).toBeGreaterThan(150);
    expect(seen.disclosure).toBeGreaterThan(20);
    expect(seen.switchOn).toBeGreaterThan(20);
    expect(seen.switchOff).toBeGreaterThan(10);
    expect(seen.more).toBeGreaterThan(30);
    expect(seen.models).toBeGreaterThan(20);
    expect(seen.prospect).toBeGreaterThan(100);
    expect(seen.stale).toBeGreaterThan(20);
    expect(seen.buried).toBeGreaterThan(5);
  }, 240_000);

  it('the Console rail asks and switches exactly as the page does', async () => {
    let compared = 0;
    for (let seed = 1; seed <= 120; seed += 1) {
      const { payload } = genCapacity(seed);
      for (const consent of [null, 'granted', 'declined'] as const) {
        const theirs = parse(legacy.rail(payload, consent));
        const page = mountPanels(
          <div data-test-root="">
            <RailUsage />
          </div>,
          { data: payload, strict: false, storage: consent ? { [CONSENT]: consent } : {} },
        );
        await page.settle();
        const mine = [...(page.container.querySelector('[data-test-root]')?.children ?? [])];
        expect(mine.length, `seed ${String(seed)} ${String(consent)}`).toBe(theirs.length);
        for (let index = 0; index < theirs.length; index += 1) {
          expect(
            firstShapeDifference(shape(theirs[index] as Element), shape(mine[index] as Element)),
            `seed ${String(seed)} ${String(consent)}`,
          ).toBeNull();
        }
        compared += theirs.length;
        page.unmount();
      }
    }
    expect(compared).toBeGreaterThan(100);
  }, 120_000);
});
