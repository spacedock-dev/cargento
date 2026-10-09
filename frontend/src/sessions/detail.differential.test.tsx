import { describe, expect, it } from 'vitest';
import { fragmentForRoute } from '../router/grammar';
import { genPayload } from '../observed/generate.test.helper';
import { loadLegacyViews } from '../observed/legacy.test.helper';
import { mountShell } from '../shell/testing';
import { caseCount } from '../../test/legacy_goldens';

/* The session page, held to the legacy page by what a reader can read. `nextSessionView` runs unchanged
   over a generated payload for each of several sessions in it, and this page renders the same route in the
   real shell. The Intent and drift panel is outside the comparison (it is a stated slot here, and a stub
   there), and so is the activity list the panel feeds; everything else on the page is compared as
   text: the header with its state word, identity, measured line and controls, the held request with its
   answer options, the activity column, the footer, and the attributes the page carries on its root. */

const legacy = loadLegacyViews();
const norm = (node: Element | null): string =>
  node ? (node.textContent ?? '').replace(/\s+/g, ' ').trim() : '';

interface DetailSummary {
  readonly state: string | null;
  readonly attributes: Record<string, string | null>;
  readonly text: string;
  readonly answers: readonly string[];
  readonly links: readonly string[];
}

function summarize(root: ParentNode): DetailSummary {
  const article = root.querySelector('article.next-session-detail');
  if (!article)
    return {
      state:
        root.querySelector('[data-next-session-state]')?.getAttribute('data-next-session-state') ??
        null,
      attributes: {},
      text: norm(root.querySelector('.next-session-detail-empty')),
      answers: [],
      links: [],
    };
  const copy = article.cloneNode(true) as Element;
  copy.querySelector('.next-session-panel')?.remove();
  /* The numbered activity list and the header's drift pill and entry count belong to the Drift step: the legacy
     stub draws none of them, and `drift-parity.mjs` and the drift tests hold them to the real page. */
  for (const owned of copy.querySelectorAll('[data-next-cockpit-work], [data-next-drift-pill]')) {
    owned.remove();
  }
  const meta = copy.querySelector('.next-session-detail-meta');
  if (meta) {
    meta.textContent = (meta.textContent ?? '')
      .split(' · ')
      .filter((part) => !/^\d+ entr(?:y|ies)$/.test(part))
      .join(' · ');
  }
  return {
    state: null,
    attributes: {
      detail: article.getAttribute('data-next-session-detail'),
      state: article.getAttribute('data-next-session-state'),
      tone: article.getAttribute('data-tone'),
      blocked: String(article.classList.contains('next-session-detail--blocked')),
    },
    text: norm(copy),
    answers: [...article.querySelectorAll('[data-next-answer]')].map(
      (button) =>
        `${button.getAttribute('data-next-answer')}#${button.getAttribute('data-next-answer-index')}:${norm(button)}`,
    ),
    links: [...article.querySelectorAll('a')].map((anchor) => anchor.getAttribute('href') ?? ''),
  };
}

function legacySummary(
  payload: unknown,
  route: { project: string; harness?: string; session: string; from?: string },
  capability = '',
): DetailSummary {
  legacy.setFocusCapability(capability);
  const template = document.createElement('template');
  template.innerHTML = legacy.sessionHtml(payload, route);
  return summarize(template.content);
}

async function reactSummary(
  payload: unknown,
  route: { project: string; harness?: string; session: string; from?: string },
  capability = '',
): Promise<DetailSummary> {
  const fragment = fragmentForRoute({ view: 'session', ...route });
  const page = mountShell({
    hash: fragment,
    data: payload,
    strict: false,
    ...(capability ? { focusCapability: capability } : {}),
  });
  await page.settle();
  const body = page.container.querySelector('[data-next-view-body="session"]');
  const root = page.container.querySelector('main');
  const result = body
    ? summarize(body.parentElement ?? page.container)
    : summarize(root ?? page.container);
  page.unmount();
  return result;
}

function routesOf(
  payload: Record<string, unknown>,
): { project: string; harness: string; session: string }[] {
  const rows = (
    Array.isArray(payload['sessions']) ? (payload['sessions'] as Record<string, unknown>[]) : []
  ).filter(
    (row) =>
      (typeof row['sid'] === 'string' && row['sid'] !== '') || typeof row['sid'] === 'number',
  );
  return rows.slice(0, 3).map((row) => ({
    project: String(row['project'] ?? ''),
    harness: String(row['harness'] ?? ''),
    session: String(row['sid']),
  }));
}

describe('the session page reads as the legacy page does, over generated payloads', () => {
  const CASES = 40;
  const SEEDS = caseCount(CASES, 'SESSIONS_SEEDS');
  for (const capability of ['', 'run-capability']) {
    it(`agrees on every session of ${String(SEEDS)} seeds${capability ? ', with a terminal-raise capability' : ''}`, async () => {
      const failures: string[] = [];
      let compared = 0;
      for (let seed = 1; seed <= SEEDS; seed += 1) {
        const payload = genPayload(seed, { wellFormed: true });
        for (const route of routesOf(payload)) {
          const old = legacySummary(payload, route, capability);
          const mine = await reactSummary(payload, route, capability);
          compared += 1;
          if (JSON.stringify(old) !== JSON.stringify(mine)) {
            const left = JSON.stringify(old);
            const right = JSON.stringify(mine);
            let at = 0;
            while (left[at] === right[at]) at += 1;
            failures.push(
              `seed ${String(seed)} ${route.harness}/${route.session}: ${JSON.stringify(left.slice(Math.max(0, at - 100), at + 140))} vs ${JSON.stringify(right.slice(Math.max(0, at - 100), at + 140))}`,
            );
          }
          if (failures.length >= 3) break;
        }
        if (failures.length >= 3) break;
      }
      expect(compared).toBeGreaterThan(20);
      expect(failures).toEqual([]);
    }, 240_000);
  }

  it('reads a session opened from a project the same way, with the project link left to the crumb', async () => {
    const payload = genPayload(5, { wellFormed: true });
    for (const route of routesOf(payload)) {
      const withFrom = { ...route, from: 'project' };
      expect(await reactSummary(payload, withFrom)).toEqual(legacySummary(payload, withFrom));
    }
  });

  it('reaches held requests, ended sessions, tasks, workers, health notes, deliveries and reports, so agreement means something', () => {
    const seen = {
      ask: 0,
      ended: 0,
      tasks: 0,
      workers: 0,
      health: 0,
      facts: 0,
      absent: 0,
      noRaise: 0,
    };
    for (let seed = 1; seed <= Math.min(SEEDS, 30); seed += 1) {
      const payload = genPayload(seed, { wellFormed: true });
      for (const route of routesOf(payload)) {
        const old = legacySummary(payload, route);
        seen.ask += old.text.includes('ASKED YOU') ? 1 : 0;
        seen.ended += old.text.includes('ended') ? 1 : 0;
        seen.tasks += old.text.includes('TASKS ·') ? 1 : 0;
        seen.workers += /SUBAGENT|RUNNING SUBAGENT/.test(old.text) ? 1 : 0;
        seen.health += /LONG TURN|FAILED TOOL LOOP/.test(old.text) ? 1 : 0;
        seen.facts += old.text.includes('Session facts:') ? 1 : 0;
        seen.absent += old.text.includes('not in the current payload') ? 1 : 0;
        seen.noRaise += old.text.includes('Terminal raise off') ? 1 : 0;
      }
    }
    for (const [name, count] of Object.entries(seen)) expect(count, name).toBeGreaterThan(1);
  });
});
