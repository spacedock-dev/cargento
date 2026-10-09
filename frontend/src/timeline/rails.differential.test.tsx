import { describe, expect, it } from 'vitest';
import { json, mountPanels } from '../steering/testing';
import { genCase } from './generate.test.helper';
import { loadLegacyTimeline } from './legacy.test.helper';
import { eventFlows } from './rails';
import { Timeline } from './Timeline';
import type { Delegation, GraphMode } from './semantic';

/* The lanes around the timeline's rows are held to the legacy page by what a reader can read: the legend that
   names each lane, the rail beside every row (which lane it is on, the mark, where each lane's line runs) and
   the strip for workers no work item claimed. The page's own `projectSemanticTimeline` runs over a generated
   semantic payload and so does the component; both are reduced to the same data and compared in every mode,
   for a focused and an unfocused timeline. A failure names the seed. */
const legacy = loadLegacyTimeline();
const MODES: readonly GraphMode[] = ['active', 'all', 'decisions'];
const CASES = 80;
const SEEDS = CASES;

const norm = (node: Element | null): string =>
  (node?.textContent ?? '').replace(/\s+/g, ' ').trim();

function summarize(root: ParentNode) {
  return {
    legend: [...root.querySelectorAll('.pc-lane-labels > span')].map((node) => [
      node.getAttribute('title'),
      norm(node),
    ]),
    legendCount:
      root
        .querySelector('.pc-lane-legend')
        ?.getAttribute('style')
        ?.match(/--lane-count:\s*(\d+)/)?.[1] ?? null,
    rows: [...root.querySelectorAll('article.pc-graph-row')].map((row) => ({
      id: row.getAttribute('data-event-id'),
      lane: row.getAttribute('data-lane-key'),
      connect: row.getAttribute('data-lane-connect'),
      style: (row.getAttribute('style') ?? '').replace(/\s+/g, '').replace(/;$/, ''),
      rail: [...row.querySelectorAll('.pc-rail-cell')].map((cell) => ({
        key: cell.getAttribute('data-rail-key'),
        active: cell.classList.contains('active'),
        flow: [...cell.classList].filter((name) => name.startsWith('flow-')),
        flowKey: cell.getAttribute('data-flow-key'),
        mark: [...cell.querySelectorAll('.pc-graph-mark')].map((mark) => [
          [...mark.classList].sort().join(' '),
          mark.getAttribute('title'),
        ]),
      })),
    })),
    unbound: [...root.querySelectorAll('.pc-unbound-context')].map((node) => ({
      head: norm(node.querySelector(':scope > .pc-trail-top')),
      summary: norm(node.querySelector(':scope > details > summary')),
      items: [...node.querySelectorAll('.pc-trail-event')].map((item) => [
        norm(item.querySelector(':scope > strong')),
        norm(item.querySelector(':scope > span')),
        norm(item.querySelector('.pc-event-evidence > div')),
      ]),
    })),
  };
}

describe('the lanes agree with the legacy page', () => {
  it(`over ${String(SEEDS)} generated payloads in every mode`, async () => {
    const failures: string[] = [];
    const seen = { rows: 0, flowed: 0, marks: 0, unbound: 0, legends: 0 };
    for (let seed = 1; seed <= SEEDS && failures.length < 3; seed += 1) {
      const generated = genCase(seed);
      const mode = MODES[seed % 3] as GraphMode;
      const origins = generated.origins ?? [];
      legacy.setScope(
        'alpha',
        generated.focus ? `${generated.focus.harness}:${generated.focus.sid}` : null,
      );
      const template = document.createElement('template');
      template.innerHTML = legacy.timeline(
        { generated: 1000 },
        generated.semantic,
        generated.delegations,
        generated.focus,
        origins,
        { mode, controls: false },
      );
      const page = mountPanels(
        <Timeline
          project="alpha"
          projectKey="alpha"
          focus={generated.focus}
          sessions={origins}
          delegations={generated.delegations as unknown as Delegation[]}
          defaultMode={mode}
        />,
        {
          data: { generated: 1000, sessions: [] },
          strict: false,
          routes: { '/api/project-context': () => json({ semantic: generated.semantic }) },
        },
      );
      await page.settle();
      const theirs = summarize(template.content);
      const mine = summarize(page.container);
      if (JSON.stringify(theirs) !== JSON.stringify(mine)) {
        const key = (Object.keys(theirs) as (keyof typeof theirs)[]).find(
          (name) => JSON.stringify(theirs[name]) !== JSON.stringify(mine[name]),
        ) as keyof typeof theirs;
        failures.push(
          `seed ${String(seed)} ${mode} ${key}\\n legacy ${JSON.stringify(theirs[key]).slice(0, 700)}\\n port   ${JSON.stringify(mine[key]).slice(0, 700)}`,
        );
      }
      seen.rows += mine.rows.length;
      seen.flowed += mine.rows.filter((row) => row.connect).length;
      seen.marks += mine.rows.filter((row) => row.rail.some((cell) => cell.mark.length)).length;
      seen.unbound += mine.unbound.length;
      seen.legends += mine.legend.length ? 1 : 0;
      page.unmount();
    }
    expect(failures).toEqual([]);
    expect(seen.rows).toBeGreaterThan(100);
    expect(seen.flowed).toBeGreaterThan(25);
    expect(seen.marks).toBeGreaterThan(80);
    expect(seen.unbound).toBeGreaterThan(5);
    expect(seen.legends).toBeGreaterThan(40);
  }, 240_000);
});

describe('a lane’s line', () => {
  it('runs from its first row to its next, through the rows between, and joins runs end to end', () => {
    const lane = (key: string) => ({ lane: { key } });
    const flows = eventFlows([lane('a'), lane('b'), lane('a'), lane('a'), lane('b')]);
    expect(flows.map((row) => [...row])).toEqual([
      [['a', 'out']],
      [
        ['a', 'through'],
        ['b', 'out'],
      ],
      [
        ['a', 'through'],
        ['b', 'through'],
      ],
      [
        ['a', 'in'],
        ['b', 'through'],
      ],
      [['b', 'in']],
    ]);
  });

  it('draws no line for a lane with one row', () => {
    expect(eventFlows([{ lane: { key: 'a' } }]).map((row) => [...row])).toEqual([[]]);
  });
});
