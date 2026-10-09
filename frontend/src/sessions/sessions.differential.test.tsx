import { describe, expect, it } from 'vitest';
import { genPayload } from '../observed/generate.test.helper';
import { loadLegacyViews } from '../observed/legacy.test.helper';
import { mountShell } from '../shell/testing';

/* The Sessions screen, held to the legacy page by what a reader can read. The legacy `nextSessionsView`
   runs unchanged over a generated payload and this screen renders the same payload in the real shell;
   both are reduced to the same shape (each group, each row in order, its text, its route, its tone) and
   compared. A difference is a bug here unless it is named in DEVIATIONS with its reason.

   Two things are outside the comparison on purpose, both because a later step owns them: the capacity strip
   that follows the groups, and the note this screen adds above them when a harness's store could not be
   read (the legacy page says nothing there). */

const legacy = loadLegacyViews();

interface RowSummary {
  readonly harness: string;
  readonly sid: string;
  readonly history: boolean;
  readonly tone: string;
  readonly href: string | null;
  readonly aria: string | null;
  readonly text: string;
  readonly copyLabels: readonly (string | null)[];
}

interface Summary {
  readonly header: string;
  readonly fleet: readonly (readonly [string, string])[];
  readonly groups: readonly {
    readonly kind: string;
    readonly header: string;
    readonly empty: string | null;
    readonly rows: readonly RowSummary[];
  }[];
}

const norm = (node: Element | null): string =>
  node ? (node.textContent ?? '').replace(/\s+/g, ' ').trim() : '';

function summarize(root: ParentNode): Summary {
  return {
    header: norm(root.querySelector('.next-operations-header')),
    fleet: [...root.querySelectorAll('[data-next-fleet-fact]')].map(
      (node) => [(node as HTMLElement).dataset['nextFleetFact'] ?? '', norm(node)] as const,
    ),
    groups: [...root.querySelectorAll('[data-next-operation-group]')].map((group) => ({
      kind: (group as HTMLElement).dataset['nextOperationGroup'] ?? '',
      header: norm(group.querySelector(':scope > header')),
      empty: group.querySelector('.next-sessions-empty')
        ? norm(group.querySelector('.next-sessions-empty'))
        : null,
      rows: [...group.querySelectorAll('article.next-operation-row')].map((row) => {
        const route = row.querySelector('a.next-operation-route');
        const data = (row as HTMLElement).dataset;
        return {
          harness: data['nextHarness'] ?? '',
          sid: data['nextSession'] ?? '',
          history: data['nextOperationHistory'] === 'true',
          tone: [...row.classList].find((name) => name.startsWith('next-operation-row--')) ?? '',
          href: route?.getAttribute('href') ?? null,
          aria: route?.getAttribute('aria-label') ?? null,
          text: norm(row),
          copyLabels: [...row.querySelectorAll('button')].map((button) =>
            button.getAttribute('aria-label'),
          ),
        };
      }),
    })),
  };
}

function legacySummary(payload: unknown): Summary {
  const template = document.createElement('template');
  template.innerHTML = legacy.sessionsHtml(payload);
  return summarize(template.content);
}

async function reactSummary(payload: unknown): Promise<Summary> {
  const page = mountShell({ hash: '#n=sessions', data: payload, strict: false });
  await page.settle();
  const root = page.container.querySelector('[data-next-view-body="sessions"]');
  if (!root) throw new Error('The Sessions screen did not draw.');
  const result = summarize(root);
  page.unmount();
  return result;
}

/* Named differences, each with its reason. Empty today: every compared field agrees. */
const DEVIATIONS: readonly {
  readonly seed: number;
  readonly path: string;
  readonly reason: string;
}[] = [];

describe('the Sessions screen reads as the legacy screen does, over generated payloads', () => {
  const CASES = 60;
  const SEEDS = CASES;
  it(`agrees on ${String(SEEDS)} seeds, group by group and row by row`, async () => {
    const failures: string[] = [];
    for (let seed = 1; seed <= SEEDS; seed += 1) {
      const payload = genPayload(seed, { wellFormed: true });
      const old = legacySummary(payload);
      const mine = await reactSummary(payload);
      for (const [index, group] of old.groups.entries()) {
        const other = mine.groups[index];
        if (
          JSON.stringify(group.rows.map((row) => [row.harness, row.sid, row.history])) !==
          JSON.stringify(other?.rows.map((row) => [row.harness, row.sid, row.history]))
        ) {
          failures.push(`seed ${String(seed)} ${group.kind}: membership or order differs`);
        }
      }
      if (
        JSON.stringify(old) !== JSON.stringify(mine) &&
        !DEVIATIONS.some((d) => d.seed === seed)
      ) {
        const left = JSON.stringify(old);
        const right = JSON.stringify(mine);
        let at = 0;
        while (left[at] === right[at]) at += 1;
        failures.push(
          `seed ${String(seed)}: differs near ${JSON.stringify(left.slice(Math.max(0, at - 90), at + 160))} vs ${JSON.stringify(right.slice(Math.max(0, at - 90), at + 160))}`,
        );
      }
      if (failures.length >= 3) break;
    }
    expect(failures).toEqual([]);
  }, 120_000);

  it('reaches both groups, ended rows, held requests, drift marks and shared labels, so agreement means something', async () => {
    const seen = {
      active: 0,
      history: 0,
      ended: 0,
      asked: 0,
      drift: 0,
      shared: 0,
      goalTyped: 0,
      annotationsOff: 0,
    };
    for (let seed = 1; seed <= SEEDS; seed += 1) {
      const text = JSON.stringify(legacySummary(genPayload(seed, { wellFormed: true })));
      seen.active += (text.match(/"kind":"active"/g) ?? []).length;
      seen.history += (text.match(/"kind":"history"/g) ?? []).length;
      seen.ended += (text.match(/NOW · ENDED/g) ?? []).length;
      seen.asked += (text.match(/BLOCKED · /g) ?? []).length;
      seen.drift += (text.match(/Drift · /g) ?? []).length;
      seen.shared += (text.match(/share this display label/g) ?? []).length;
      seen.goalTyped += (text.match(/GOAL · YOUR WORDS|GOAL · FROM YOUR PROMPT/g) ?? []).length;
      seen.annotationsOff += (text.match(/Annotations off/g) ?? []).length;
    }
    for (const [name, count] of Object.entries(seen)) expect(count, name).toBeGreaterThan(5);
  });
});
