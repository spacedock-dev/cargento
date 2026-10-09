import { afterEach, describe, expect, it, vi } from 'vitest';
import { genTripwires } from './generate.test.helper';
import { steeringHeldFor } from './held';
import { loadLegacySteering } from './legacy.test.helper';
import { StageConditions } from './StageConditions';
import { mountPanels } from './testing';

/* The stage-condition cards are held to the legacy page by what a reader can read. The page's own
   `nextStageConditions` runs over a generated `tripwires` section and so does the component; both are reduced
   to the same sequence (each heading, sentence, option, and button with its state) and compared. A
   difference is a bug here unless it is named in the DEVIATIONS the step records. */
const legacy = loadLegacySteering();
const CASES = 80;
const SEEDS = CASES;

const norm = (text: string | null): string => (text ?? '').replace(/\s+/g, ' ').trim();

function summarize(root: ParentNode) {
  const section = root.querySelector('.next-stage-conditions');
  if (!section) return null;
  return [...section.querySelectorAll('h2,h3,p,option,select,button,article')].map((node) => {
    const element = node as HTMLElement;
    const tag = element.tagName.toLowerCase();
    if (tag === 'option') {
      const option = element as HTMLOptionElement;
      return {
        tag,
        value: option.value,
        text: norm(option.textContent),
        selected: option.selected,
        disabled: option.disabled,
      };
    }
    if (tag === 'select') {
      return {
        tag,
        id: element.dataset['stageChoice'],
        disabled: (element as HTMLSelectElement).disabled,
      };
    }
    if (tag === 'button') {
      return {
        tag,
        id: element.dataset['stageId'],
        action: element.dataset['stageAction'],
        text: norm(element.textContent),
        disabled: (element as HTMLButtonElement).disabled,
      };
    }
    if (tag === 'article') return { tag, rule: element.dataset['stageRule'] };
    return { tag, role: element.getAttribute('role'), text: norm(element.textContent) };
  });
}

afterEach(() => vi.unstubAllGlobals());

describe('the stage-condition cards agree with the legacy page', () => {
  it(`over ${String(SEEDS)} generated boards`, async () => {
    const failures: string[] = [];
    let cards = 0;
    let withTrip = 0;
    let lanes = 0;
    for (let seed = 1; seed <= SEEDS && failures.length < 3; seed += 1) {
      const generated = genTripwires(seed);
      const html = (() => {
        legacy.reset();
        legacy.setData(generated.payload);
        legacy.setNotification(generated.notification);
        for (const [id, stage] of generated.drafts) legacy.setStageDraft(id, stage);
        const template = document.createElement('template');
        template.innerHTML = legacy.stageHtml(generated.scope);
        return template.content;
      })();
      if (generated.notification === null) vi.unstubAllGlobals();
      else vi.stubGlobal('Notification', { permission: generated.notification });
      const page = mountPanels(
        (shell) => {
          for (const [id, stage] of generated.drafts)
            steeringHeldFor(shell).stage.setDraft(id, stage);
          return <StageConditions sessions={generated.scope} />;
        },
        { data: generated.payload, strict: false },
      );
      await page.settle();
      const theirs = summarize(html);
      const mine = summarize(page.container);
      if (JSON.stringify(theirs) !== JSON.stringify(mine)) {
        const at = (theirs ?? []).findIndex(
          (row, index) => JSON.stringify(row) !== JSON.stringify((mine ?? [])[index]),
        );
        failures.push(
          `seed ${String(seed)} row ${String(at)}\n legacy ${JSON.stringify((theirs ?? [])[at])}\n port   ${JSON.stringify((mine ?? [])[at])}`,
        );
      }
      cards += mine?.filter((row) => row.tag === 'article').length ?? 0;
      withTrip += (mine ?? []).filter(
        (row) => 'text' in row && String(row.text).startsWith('Observed '),
      ).length;
      lanes += (mine ?? []).filter(
        (row) => 'text' in row && String(row.text).includes('Browser notification lane'),
      ).length;
      page.unmount();
      legacy.setNotification(null);
    }
    expect(failures).toEqual([]);
    // The comparison is not vacuous: cards were drawn, some tripped, some with a browser lane.
    expect(cards).toBeGreaterThan(40);
    expect(withTrip).toBeGreaterThan(8);
    expect(lanes).toBeGreaterThan(2);
  }, 120_000);
});
