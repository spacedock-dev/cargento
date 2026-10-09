import { act, fireEvent } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { mountPanels, type MountOptions } from '../steering/testing';
import { CapacityStrip } from './CapacityStrip';
import { heldFor } from './held';
import { RailUsage } from './UsageConsent';

/* Usage fetching is offered with a disclosure, and what the reader answers is what the next request says.
   The request is read where it is made: every `/api/data` URL the page sent is counted, because the legacy
   page's test of this was a unit over one function and the failure that matters is a request nobody asked
   for. Nothing here reads a credential: the backend is a script that answers from a board. */
const CONSENT = 'cargento.next.usage.consent';
const board = (over: Record<string, unknown> = {}) => ({
  generated: 1000,
  usage_fetch: true,
  harnesses: [{ key: 'claude', label: 'Claude Code' }],
  usage: [
    {
      harness: 'claude',
      state: 'ok',
      asOf: 990,
      fiveH: { pct: 34, windowSec: 18000, resetAt: 1000 + 9000 },
    },
  ],
  sessions: [],
  ...over,
});
const mount = (options: MountOptions = {}, strip = true) =>
  mountPanels(strip ? <CapacityStrip /> : <RailUsage />, { data: board(), ...options });
const dataUrls = (page: ReturnType<typeof mount>): string[] =>
  page.state.requests.filter((r) => r.path === '/api/data').map((r) => r.url);
const withUsage = (page: ReturnType<typeof mount>): string[] =>
  dataUrls(page).filter((url) => /[?&]usage=/.test(url));
const press = (answer: string) => {
  const button = document.querySelector(`[data-next-usage-answer="${answer}"]`);
  if (!button) throw new Error(`no ${answer} button`);
  fireEvent.click(button);
};

describe('the quota fetch is asked for, and refused until it is answered yes', () => {
  it('offers the disclosure, names what is read and where it goes, and sends no usage parameter on mount', async () => {
    const page = mount();
    await page.settle();
    const text = document.querySelector('[data-next-usage-consent]')?.textContent ?? '';
    expect(text).toContain('Read your quota from the vendor?');
    expect(text).toContain('reading the credential that harness already stored on this machine');
    expect(text).toContain('sending it to that vendor, at most once every five minutes');
    expect(text).toContain('no session content is sent');
    expect(text).toContain('--no-usage');
    expect(dataUrls(page).length).toBeGreaterThan(0);
    expect(withUsage(page)).toEqual([]);
    expect(document.querySelector('.next-usage-switch')).toBeNull();
  });

  it('unanswered sends none through StrictMode, polls, a route change and a remount', async () => {
    const page = mount();
    await page.settle();
    await page.poll(board({ generated: 1001 }));
    await page.advance(120_000);
    await page.poll(board({ generated: 1002 }));
    page.show(<p>Elsewhere</p>);
    await page.settle();
    page.show(<CapacityStrip />);
    await page.settle();
    await page.poll(board({ generated: 1003 }));
    expect(dataUrls(page).length).toBeGreaterThan(4);
    expect(withUsage(page)).toEqual([]);
    expect(page.posts()).toBe(0);
  });

  it('declined sends none, however long it runs, and keeps the choice to change it', async () => {
    const page = mount({ storage: { [CONSENT]: 'declined' } });
    await page.settle();
    await page.poll(board({ generated: 1001 }));
    await page.advance(120_000);
    expect(withUsage(page)).toEqual([]);
    expect(document.querySelector('[data-next-usage-consent]')).toBeNull();
    expect(document.querySelector('.next-usage-switch')?.textContent).toContain(
      'Vendor quota fetch: off',
    );
    expect(document.querySelector('.next-usage-lapse')?.textContent).toBe(
      'Windows above are the last cached read and will lapse.',
    );
  });

  it('an unrecognised stored answer is unanswered, never granted', async () => {
    const page = mount({ storage: { [CONSENT]: 'yes' } });
    await page.settle();
    expect(withUsage(page)).toEqual([]);
    expect(document.querySelector('[data-next-usage-consent]')).not.toBeNull();
  });

  it('Read my quota records the answer and the next request, and only that one, carries usage=1', async () => {
    const page = mount();
    await page.settle();
    const before = dataUrls(page).length;
    press('granted');
    await page.settle();
    expect(page.backend.data.get(CONSENT)).toBe('granted');
    const after = dataUrls(page).slice(before);
    expect(after.length).toBeGreaterThanOrEqual(1);
    expect(after.every((url) => /[?&]usage=1(&|$)/.test(url))).toBe(true);
    // The disclosure is gone and the switch says it is on; one question, one answer on screen.
    expect(document.querySelector('[data-next-usage-consent]')).toBeNull();
    expect(document.querySelector('.next-usage-switch')?.textContent).toContain(
      'Vendor quota fetch: on',
    );
    expect(document.querySelector('.next-usage-lapse')).toBeNull();
    await page.poll(board({ generated: 1004 }));
    expect(dataUrls(page).at(-1)).toMatch(/usage=1/);
  });

  it('an answer given on an earlier visit rides the very first request', async () => {
    const page = mount({ storage: { [CONSENT]: 'granted' } });
    await page.settle();
    expect(dataUrls(page)[0]).toMatch(/usage=1/);
  });

  it('turning it off stops the parameter at once and says the windows will lapse', async () => {
    const page = mount({ storage: { [CONSENT]: 'granted' } });
    await page.settle();
    const before = dataUrls(page).length;
    press('declined');
    await page.settle();
    await page.poll(board({ generated: 1005 }));
    const after = dataUrls(page).slice(before);
    expect(after.length).toBeGreaterThanOrEqual(1);
    expect(after.some((url) => /usage=/.test(url))).toBe(false);
    expect(page.backend.data.get(CONSENT)).toBe('declined');
    expect(document.querySelector('.next-usage-lapse')).not.toBeNull();
  });

  it('offers nothing unless the server raised the flag with a real true', async () => {
    for (const flag of [undefined, false, 'yes', 1, null]) {
      const page = mount({ data: board({ usage_fetch: flag }) });
      await page.settle();
      expect(
        document.querySelector('[data-next-usage-consent]'),
        `flag ${String(flag)}`,
      ).toBeNull();
      expect(document.querySelector('.next-usage-switch'), `flag ${String(flag)}`).toBeNull();
      expect(withUsage(page)).toEqual([]);
      page.unmount();
    }
  });

  it('the disclosure can stand alone: with no window published it is the reason there is no row', async () => {
    const page = mount({ data: board({ usage: [] }) });
    await page.settle();
    expect(document.querySelector('[data-next-usage-consent]')).not.toBeNull();
    expect(document.querySelector('[data-next-capacity]')).toBeNull();
  });
});

describe('the answer survives what browsers do to storage', () => {
  const refuseWrites = (page: ReturnType<typeof mount>) => {
    (page.backend as { setItem: unknown }).setItem = () => {
      throw new DOMException('quota', 'QuotaExceededError');
    };
  };

  it('a profile that refuses the write keeps the answer for this tab, and the fetch follows it', async () => {
    const page = mount();
    await page.settle();
    refuseWrites(page);
    const before = dataUrls(page).length;
    press('granted');
    await page.settle();
    expect(page.backend.data.has(CONSENT)).toBe(false);
    expect(document.querySelector('[data-next-usage-consent]')).toBeNull();
    expect(document.querySelector('.next-usage-switch')?.textContent).toContain('on');
    expect(
      dataUrls(page)
        .slice(before)
        .every((url) => /usage=1/.test(url)),
    ).toBe(true);
    expect(dataUrls(page).length).toBeGreaterThan(before);
  });

  it('storage that cannot be read leaves the question unanswered, which withholds the fetch', async () => {
    const page = mount();
    (page.backend as { getItem: unknown }).getItem = () => {
      throw new DOMException('blocked', 'SecurityError');
    };
    await page.poll(board({ generated: 1001 }));
    expect(document.querySelector('[data-next-usage-consent]')).not.toBeNull();
    expect(withUsage(page)).toEqual([]);
    // The reader can still answer, and the tab remembers it.
    press('declined');
    await page.settle();
    expect(document.querySelector('.next-usage-switch')?.textContent).toContain('off');
  });

  it("another tab's answer changes this tab's switch without a press", async () => {
    const page = mount();
    await page.settle();
    expect(document.querySelector('[data-next-usage-consent]')).not.toBeNull();
    page.backend.data.set(CONSENT, 'declined');
    await act(async () => {
      window.dispatchEvent(new StorageEvent('storage', { key: CONSENT, newValue: 'declined' }));
    });
    expect(document.querySelector('[data-next-usage-consent]')).toBeNull();
    expect(document.querySelector('.next-usage-switch')?.textContent).toContain('off');
  });
});

describe('the rail asks the same question', () => {
  it('shows the disclosure, answers it and then shows the switch, with the same request behaviour', async () => {
    const page = mount({}, false);
    await page.settle();
    expect(document.querySelector('[data-next-usage-consent]')).not.toBeNull();
    expect(withUsage(page)).toEqual([]);
    press('granted');
    await page.settle();
    expect(document.querySelector('.next-usage-switch')?.textContent).toContain('on');
    expect(dataUrls(page).at(-1)).toMatch(/usage=1/);
  });

  it('keyboard focus lands on the switch when the answered disclosure leaves', async () => {
    const page = mount({}, false);
    await page.settle();
    const button = document.querySelector<HTMLElement>('[data-next-usage-answer="granted"]');
    button?.focus();
    expect(document.activeElement).toBe(button);
    press('granted');
    await page.settle();
    expect(document.activeElement).toBe(document.querySelector('.next-usage-switch button'));
  });
});

describe('what is held between draws', () => {
  it('the consent lane reads the same storage the transport reads', async () => {
    const page = mount({ storage: { [CONSENT]: 'granted' } });
    await page.settle();
    expect(heldFor(page.shell.runtime).usage.read()).toBe('granted');
  });
});
