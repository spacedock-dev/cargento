import { act, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { mountSession } from './panel.testing';
import { json } from './testing';

const promptSelect = () =>
  document.querySelector('[data-next-cockpit-prompt-select]') as HTMLSelectElement;
const choices = [{ fact_id: 'p1', text: 'Fix the login redirect', at: 100, cut: false }];

async function opening() {
  const page = mountSession({
    routes: {
      '/api/project-context': (request) => (request.url.includes('prompts=1') ? 'hold' : json({})),
    },
  });
  await page.settle();
  await page.settle();
  const select = promptSelect();
  const showPicker = vi.fn();
  Object.defineProperty(select, 'showPicker', { value: showPicker });
  await act(async () => {
    fireEvent.pointerDown(select);
  });
  return { page, select, showPicker };
}

describe('a reader opening their prompts', () => {
  it('sees loading on the first press, keeps focus, and gets one picker when the choices arrive', async () => {
    const { page, select, showPicker } = await opening();
    expect(select.options[0]?.textContent).toBe('Loading your prompts');
    expect(select.getAttribute('aria-busy')).toBe('true');
    expect(document.activeElement).toBe(select);
    expect(showPicker).not.toHaveBeenCalled();
    await act(async () => {
      fireEvent.pointerDown(select);
    });
    expect(showPicker).not.toHaveBeenCalled();
    await page.release('/api/project-context', json({ prompt_choices: choices }));
    expect(promptSelect()).toBe(select);
    expect(select.options[0]?.textContent).toBe('Use your prompt');
    expect(select.getAttribute('aria-busy')).toBe('false');
    expect(select.options[1]?.textContent).toContain('Fix the login redirect');
    expect(document.activeElement).toBe(select);
    expect(showPicker).toHaveBeenCalledTimes(1);
    expect(page.state.requests.filter((request) => request.url.includes('prompts=1'))).toHaveLength(
      1,
    );
  });

  it.each([json({ prompt_choices: [] }), json({ error: 'unavailable' }, 503)])(
    'returns to the invitation without opening an empty or failed picker (%#)',
    async (response) => {
      const { page, select, showPicker } = await opening();
      expect(select.options[0]?.textContent).toBe('Loading your prompts');
      await page.release('/api/project-context', response);
      expect(select.options[0]?.textContent).toBe('Use your prompt');
      expect(select.getAttribute('aria-busy')).toBe('false');
      expect(document.activeElement).toBe(select);
      expect(showPicker).not.toHaveBeenCalled();
    },
  );

  it('does not reopen a picker the reader dismissed before the choices arrived', async () => {
    const { page, select, showPicker } = await opening();
    await act(async () => {
      fireEvent.keyDown(select, { key: 'Escape' });
    });
    await page.release('/api/project-context', json({ prompt_choices: choices }));
    expect(select.options[0]?.textContent).toBe('Use your prompt');
    expect(showPicker).not.toHaveBeenCalled();
  });
});
