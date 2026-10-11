import { act, fireEvent, screen } from '@testing-library/react';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import { mountDrift, ROUTE } from '../drift/testing';

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

describe('the Intent how-to', () => {
  it('keeps the popup keyed across session remounts without a first-use flag', async () => {
    const page = mountDrift();
    await page.settle();
    fireEvent.click(screen.getByRole('button', { name: 'How Intent and drift works' }));
    await page.settle();
    await act(async () => {
      page.router.navigate({ view: 'sessions' });
    });
    await page.settle();
    await act(async () => {
      page.router.navigate({
        view: 'session',
        project: 'alpha/app',
        harness: 'claude',
        session: 's1',
      });
    });
    await page.settle();
    expect(screen.getByRole('dialog', { name: 'How Intent and drift works' })).toBeTruthy();
    expect(page.posts()).toBe(0);
  });
  for (const [harness, reader, steer] of [
    ['claude', true, true],
    ['pi', true, false],
    ['cursor', false, false],
  ] as const) {
    it(`derives the limits for ${harness} from the board`, async () => {
      const page = mountDrift({
        session: { harness },
        hash: `#n=session:alpha%2Fapp:${harness}:s1`,
        payload: {
          reading_routes: {
            [harness]: reader ? ROUTE : { provider: '', note: 'No reader on this machine.' },
          },
        },
      });
      await page.settle();
      const button = screen.getByRole('button', { name: 'How Intent and drift works' });
      expect(button.closest('header')?.querySelector('h2')?.textContent).toBe('Intent');
      expect(screen.queryByRole('button', { name: 'What analysis does' })).toBeNull();
      fireEvent.click(button);
      await page.settle();
      const popup = screen.getByRole('dialog', { name: 'How Intent and drift works' });
      expect((popup.textContent ?? '').split(/\s+/).length).toBeLessThanOrEqual(150);
      expect(popup.textContent).toContain('1. Give the goal.');
      expect(popup.textContent).toContain('2. Press Analyze drift.');
      expect(popup.textContent).toContain('3. Read where the work left your goal.');
      expect(popup.textContent).toContain('Levels: Claude Code and Pi only.');
      expect(popup.textContent).toContain(
        reader ? 'Analyze: Claude Code.' : 'Analyze: No reader on this machine.',
      );
      expect(popup.textContent).toContain(
        steer ? 'Steer back: available here.' : 'Steer back: Claude Code only.',
      );
      expect(popup.textContent).toContain('Cargento never writes into sessions.');
      expect(popup.textContent).toContain('Not enough recorded yet');
      const node = popup;
      await page.poll(page.state.data);
      expect(screen.getByRole('dialog', { name: 'How Intent and drift works' })).toBe(node);
      expect(page.posts()).toBe(0);
    });
  }
});
