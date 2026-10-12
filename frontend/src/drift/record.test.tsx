import { act, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { fact, json, mountDrift, press } from './testing';

const path = '/api/session-record';
const session = { annotation_window_start: 1, annotation_goal_saved_at: 1 };
const entries = (from: number, count: number) =>
  Array.from({ length: count }, (_, i) => fact(`p${String(from - i)}`, from - i));
const pageBody = (extra: Record<string, unknown> = {}) => ({
  session: { harness: 'claude', sid: 's1' },
  entries: entries(100, 50),
  next: 'older',
  reached_start: false,
  bound: null,
  scanned_bytes: 65536,
  kinds: ['user_message', 'agent_message'],
  state: 'ok',
  ...extra,
});
const rows = () => [...document.querySelectorAll<HTMLElement>('[data-next-entry-id]')];
const more = () => screen.getByRole('button', { name: 'Show 50 older entries' });

describe('a reader paging a session record', () => {
  it('a reader with a week-long session sees the newest fifty entries first and opens older ones one page at a time', async () => {
    const page = mountDrift({
      session,
      routes: {
        [path]: (r) =>
          json(
            pageBody(r.url.includes('before=') ? { entries: entries(50, 50), next: 'oldest' } : {}),
          ),
      },
    });
    await page.settle();
    expect(page.gets(path)).toBe(1);
    expect(rows()).toHaveLength(50);
    expect(rows()[0]?.dataset['nextEntryId']).toBe('p100');
    expect(rows().at(-1)?.dataset['nextEntryId']).toBe('p51');
    expect(screen.queryByText('Numbers count from the oldest entry loaded.')).toBeNull();
    await page.poll(page.state.data);
    await act(async () => {
      await page.shell.runtime.refresh({ manual: true });
    });
    expect(page.gets(path)).toBe(1);
    await press(more());
    expect(page.state.requests.filter((r) => r.path === path).map((r) => r.url)).toEqual([
      '/api/session-record?project=%2Frepo%2Falpha&session=claude%3As1&limit=50',
      '/api/session-record?project=%2Frepo%2Falpha&session=claude%3As1&limit=50&before=older',
    ]);
    expect(rows()).toHaveLength(100);
    expect(rows()[0]?.dataset['nextEntry']).toBe('100');
    expect(screen.getByText('Numbers count from the oldest entry loaded.')).toBeVisible();
  });

  it('a reader sees one copy of an entry shared by pages and the record wins over context', async () => {
    const page = mountDrift({
      session,
      facts: [fact('p51', 51, { summary: 'Context copy' })],
      routes: {
        [path]: (r) =>
          json(
            pageBody(
              r.url.includes('before=')
                ? {
                    entries: [fact('p51', 51), ...entries(50, 49)],
                    next: 'again',
                  }
                : {},
            ),
          ),
      },
    });
    await page.settle();
    await press(more());
    expect(rows()).toHaveLength(99);
    expect([...page.shell.runtime.store.getSnapshot().records.values()][0]?.entries).toHaveLength(
      99,
    );
    expect(rows().filter((r) => r.dataset['nextEntryId'] === 'p51')).toHaveLength(1);
    expect(document.body.textContent).not.toContain('Context copy');
  });

  it('a reader keeps the busy button and can retry a failed older read with the same cursor', async () => {
    const page = mountDrift({
      session,
      routes: { [path]: (r) => (r.url.includes('before=') ? 'hold' : json(pageBody())) },
    });
    await page.settle();
    const button = more();
    button.focus();
    await press(button);
    expect(button.getAttribute('aria-busy')).toBe('true');
    expect(button.getAttribute('aria-disabled')).toBe('true');
    expect(button.textContent).toContain('Reading older entries');
    await press(button);
    expect(page.gets(path)).toBe(2);
    await page.release(path, new Response('down', { status: 503 }));
    expect(screen.getByText('Could not read older entries')).toBeVisible();
    expect(more()).toBe(button);
    page.state.routes[path] = () => json(pageBody({ entries: entries(50, 50) }));
    await press(button);
    expect(rows()).toHaveLength(100);
    expect(document.activeElement).toBe(button);
    expect(screen.queryByText('Could not read older entries')).toBeNull();
    expect(page.state.requests.at(-1)?.url).toContain('before=older');
  });

  it('a reader can continue a byte bound with no entries instead of mistaking it for the start', async () => {
    const page = mountDrift({
      session,
      routes: {
        [path]: () => json(pageBody({ entries: [], bound: 'bytes', scanned_bytes: 16777216 })),
      },
    });
    await page.settle();
    expect(
      screen.getByText(
        'The read stopped after reading 16 MB without reaching 50 more entries; Show more continues from there.',
      ),
    ).toBeVisible();
    await press(more());
    expect(page.gets(path)).toBe(2);
  });

  it('a reader is told when the clock allowance stopped the read', async () => {
    const page = mountDrift({
      session,
      routes: { [path]: () => json(pageBody({ bound: 'time', scanned_bytes: 1048576 })) },
    });
    await page.settle();
    expect(
      screen.getByText(
        'The read stopped after reading 1 MB without reaching 50 more entries; Show more continues from there.',
      ),
    ).toBeVisible();
  });

  it('a reader reaching the start moves focus to the first new row without scrolling', async () => {
    const page = mountDrift({
      session,
      routes: {
        [path]: (r) =>
          json(
            pageBody(
              r.url.includes('before=')
                ? {
                    entries: entries(50, 50),
                    next: null,
                    reached_start: true,
                  }
                : {},
            ),
          ),
      },
    });
    await page.settle();
    const button = more();
    button.focus();
    await press(button);
    expect(screen.queryByRole('button', { name: 'Show 50 older entries' })).toBeNull();
    expect(screen.getByText('That is the start of the record.')).toBeVisible();
    expect(document.activeElement).toBe(rows().find((r) => r.dataset['nextEntryId'] === 'p50'));
  });

  it('a reader typing elsewhere while a page arrives keeps their new focus', async () => {
    const page = mountDrift({
      session,
      routes: { [path]: (r) => (r.url.includes('before=') ? 'hold' : json(pageBody())) },
    });
    await page.settle();
    more().focus();
    await press(more());
    const goal = document.querySelector<HTMLTextAreaElement>(
      'textarea[data-next-cockpit-held-kind="goal"]',
    );
    goal?.focus();
    await page.release(
      path,
      json(pageBody({ entries: entries(50, 50), next: null, reached_start: true })),
    );
    expect(document.activeElement).toBe(goal);
  });

  it('a reader whose older page has no visible new row reaches the new window-boundary sentence', async () => {
    const page = mountDrift({
      session: { ...session, annotation_window_start: 40, annotation_goal_saved_at: 40 },
      routes: {
        [path]: (r) =>
          json(pageBody(r.url.includes('before=') ? { entries: entries(30, 30) } : {})),
      },
    });
    await page.settle();
    more().focus();
    await press(more());
    expect(rows()).toHaveLength(50);
    expect(document.activeElement).toBe(
      screen.getByText("Everything since your intent's window opened is listed."),
    );
  });

  it('a reader can add an older loaded direction to their intent just like a context entry', async () => {
    const page = mountDrift({
      session,
      routes: {
        [path]: (r) =>
          json(pageBody(r.url.includes('before=') ? { entries: entries(50, 50) } : {})),
        '/api/direction': () => json({ ok: true, text: 'Older direction in full', clipped: false }),
      },
    });
    await page.settle();
    await press(more());
    await press(document.querySelector('[data-next-entry-id="p50"] button'));
    expect(document.body.textContent).toContain('Older direction in full');
    await page.poll(page.state.data);
    expect(document.body.textContent).toContain('Older direction in full');
  });

  it('a reader leaving an older direction draft keeps their words while its record page is unread on return', async () => {
    const page = mountDrift({
      session,
      routes: {
        [path]: (r) =>
          json(pageBody(r.url.includes('before=') ? { entries: entries(50, 50) } : {})),
        '/api/direction': () => json({ ok: true, text: 'Older direction in full', clipped: false }),
      },
    });
    await page.settle();
    await press(more());
    await press(document.querySelector('[data-next-entry-id="p50"] button'));
    expect(document.body.textContent).toContain('Older direction in full');
    await page.go('#n=intent');
    await page.go('#n=session:alpha%2Fapp:claude:s1');
    expect(rows()).toHaveLength(50);
    expect(document.body.textContent).toContain('Older direction in full');
  });

  it('a reader whose harness is unsupported sees its limit without a paging button', async () => {
    const page = mountDrift({
      session,
      routes: { [path]: () => json(pageBody({ state: 'unsupported', entries: [], next: null })) },
    });
    await page.settle();
    expect(screen.getByText('Older entries are not read for this harness.')).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Show 50 older entries' })).toBeNull();
  });

  it('a reader with an unavailable record sees a failure and retries the newest page', async () => {
    const page = mountDrift({
      session,
      routes: { [path]: () => json(pageBody({ state: 'unavailable', entries: [], next: null })) },
    });
    await page.settle();
    expect(screen.getByText('Could not read older entries')).toBeVisible();
    page.state.routes[path] = () => json(pageBody());
    await press(more());
    expect(page.gets(path)).toBe(2);
    expect(page.state.requests.at(-1)?.url).not.toContain('before=');
  });

  it('a reader with a stale cursor loses the old pages and sees one automatic newest-page restart', async () => {
    let newest = 0;
    const page = mountDrift({
      session,
      routes: {
        [path]: (r) => {
          if (r.url.includes('before='))
            return json(pageBody({ state: 'stale', entries: [], next: null }));
          newest += 1;
          return json(pageBody({ entries: [fact(newest === 1 ? 'old' : 'fresh', 900)] }));
        },
      },
    });
    await page.settle();
    await press(more());
    expect(page.gets(path)).toBe(3);
    expect(rows().map((r) => r.dataset['nextEntryId'])).toEqual(['fresh']);
    expect(
      screen.getByText('The record changed. Started again from the newest entries.'),
    ).toBeVisible();
    await page.poll(page.state.data);
    expect(page.gets(path)).toBe(3);
  });

  it('a reader whose record changes twice gets a stated stop rather than an automatic retry loop', async () => {
    const page = mountDrift({
      session,
      routes: { [path]: () => json(pageBody({ state: 'stale', entries: [], next: null })) },
    });
    await page.settle();
    expect(page.gets(path)).toBe(2);
    expect(
      screen.getByText('The record changed again. Show more retries from the newest entries.'),
    ).toBeVisible();
  });

  it('a reader waiting for a stale restart keeps a busy control and reaches the fresh row when that restart finishes', async () => {
    let newest = 0;
    const page = mountDrift({
      session,
      routes: {
        [path]: (r) => {
          if (r.url.includes('before='))
            return json(pageBody({ state: 'stale', entries: [], next: null }));
          newest += 1;
          return newest === 1 ? json(pageBody()) : 'hold';
        },
      },
    });
    await page.settle();
    more().focus();
    await press(more());
    expect(
      screen.getByRole('button', { name: 'Reading older entries' }).getAttribute('aria-busy'),
    ).toBe('true');
    await page.release(
      path,
      json(pageBody({ entries: [fact('fresh', 900)], next: null, reached_start: true })),
    );
    expect(document.activeElement).toBe(document.querySelector('[data-next-entry-id="fresh"]'));
    expect(page.gets(path)).toBe(3);
  });

  it('a reader already past the intent window sees all its entries and cannot request invisible older rows', async () => {
    const page = mountDrift({
      session: { ...session, annotation_window_start: 75, annotation_goal_saved_at: 75 },
      routes: { [path]: () => json(pageBody()) },
    });
    await page.settle();
    expect(rows()).toHaveLength(26);
    expect(
      screen.getByText("Everything since your intent's window opened is listed."),
    ).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Show 50 older entries' })).toBeNull();
    await page.poll(page.state.data);
    expect(page.gets(path)).toBe(1);
  });

  it('a reader keeps loaded pages through a board refresh and drops them on leaving the session page', async () => {
    const page = mountDrift({
      session,
      routes: {
        [path]: (r) =>
          json(pageBody(r.url.includes('before=') ? { entries: entries(50, 50) } : {})),
      },
    });
    await page.settle();
    await press(more());
    await page.poll(page.state.data);
    expect(rows()).toHaveLength(100);
    expect(page.gets(path)).toBe(2);
    await page.go('#n=intent');
    expect(page.shell.runtime.store.getSnapshot().records.size).toBe(0);
    await page.go('#n=session:alpha%2Fapp:claude:s1');
    expect(page.gets(path)).toBe(3);
    expect(rows()).toHaveLength(50);
  });

  it('a reader leaving during a read aborts it and a late reply cannot restore discarded pages', async () => {
    const page = mountDrift({ session, routes: { [path]: () => 'hold' } });
    await page.settle();
    await page.go('#n=intent');
    await page.release(path, json(pageBody()));
    expect(page.shell.runtime.store.getSnapshot().records.size).toBe(0);
    await page.go('#n=session:alpha%2Fapp:claude:s1');
    expect(page.gets(path)).toBe(2);
    expect(rows()).toHaveLength(0);
  });
});
