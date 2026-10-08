import { act, fireEvent } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { mountIntent } from './testing';
import { board, mountSession, SESSION_HASH, text } from './panel.testing';

/* The live monitor switch decides only whether the deterministic level is drawn. It is off by default,
   remembered for this exact session in this browser, and it never sends anything. */

const KEY = 'cargento.next.live-estimate:claude:s1';
const switchButton = () =>
  document.querySelector('[data-next-cockpit-action="live-monitor"]') as HTMLButtonElement;

describe('the live monitor switch', () => {
  it('is off by default, drawn beside the Drift heading, and drawing it sends nothing', async () => {
    const page = mountSession();
    await page.settle();
    expect(switchButton().getAttribute('role')).toBe('switch');
    expect(switchButton().getAttribute('aria-checked')).toBe('false');
    expect(text('#next-session-drift-monitor-label')).toBe('Live monitor');
    expect(page.posts()).toBe(0);
  });

  it('writes 1 for this exact session when turned on, removes the key when turned off, and sends nothing', async () => {
    const page = mountSession();
    await page.settle();
    const storage = page.shell.runtime.storage;
    expect(storage.liveEstimate.on({ harness: 'claude', sid: 's1' })).toBe(false);
    await act(async () => {
      fireEvent.click(switchButton());
    });
    expect(switchButton().getAttribute('aria-checked')).toBe('true');
    expect(storage.liveEstimate.on({ harness: 'claude', sid: 's1' })).toBe(true);
    expect(storage.liveEstimate.on({ harness: 'claude', sid: 'another' })).toBe(false);
    await act(async () => {
      fireEvent.click(switchButton());
    });
    expect(switchButton().getAttribute('aria-checked')).toBe('false');
    expect(page.posts()).toBe(0);
    expect(
      page.state.requests.filter(
        (r) => r.path !== '/api/data' && r.path !== '/api/project-context',
      ),
    ).toEqual([]);
    expect(KEY).toContain('claude:s1');
  });

  it('is drawn only for the harness whose estimate the server publishes, and only with annotations on', async () => {
    const codex = mountIntent({
      hash: '#n=session:alpha%2Fapp:codex:c1',
      data: board({ harness: 'codex', sid: 'c1' }),
    });
    await codex.settle();
    expect(document.querySelector('[data-next-cockpit-action="live-monitor"]')).toBeNull();
    codex.unmount();
    const off = mountIntent({ hash: SESSION_HASH, data: { ...board(), annotate: false } });
    await off.settle();
    expect(document.querySelector('[data-next-cockpit-action="live-monitor"]')).toBeNull();
  });

  it('keeps the choice for the tab where storage cannot be written', async () => {
    const page = mountSession();
    await page.settle();
    const real = page.shell.runtime.storage.liveEstimate;
    expect(real.set({ harness: 'claude', sid: 's1' }, true)).toBeTypeOf('boolean');
    expect(real.on({ harness: 'claude', sid: 's1' })).toBe(true);
  });
});
