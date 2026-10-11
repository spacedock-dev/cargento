import { act, fireEvent } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { control, goalBox, lineBoxes, mountSession, text, type } from './panel.testing';

const settle = async (page: { settle: () => Promise<void> }) => {
  await page.settle();
  await page.settle();
};

describe('the first view of a session', () => {
  it('offers one optional outcome field and reveals its tools after use', async () => {
    const page = mountSession();
    await settle(page);
    expect(lineBoxes()).toHaveLength(1);
    expect(text('.next-cockpit-held-lines label')).toBe('Expected outcome (optional)');
    expect(control('held-line-add')).toBeNull();
    expect(control('held-line-remove')).toBeNull();
    type(lineBoxes()[0] as HTMLTextAreaElement, 'A passing check');
    expect(control('held-line-add')).not.toBeNull();
    expect(control('held-line-remove')).not.toBeNull();
    expect(control('held-undo')).toBeNull();
  });

  it('keeps Save visible and puts Clear and the monitor inside session More', async () => {
    const page = mountSession();
    await settle(page);
    expect(control('held-save')).not.toBeNull();
    expect(control('held-undo')).toBeNull();
    const more = document.querySelector('[data-next-session-more]');
    expect(more).not.toBeNull();
    expect(more?.contains(control('held-clear'))).toBe(true);
    expect(more?.contains(control('live-monitor'))).toBe(true);
    expect(text('.next-session-reentry-none')).toBe('');
    type(goalBox(), 'Changed goal');
    expect(control('held-undo')).not.toBeNull();
    await act(async () => {
      fireEvent.click(control('held-undo') as Element);
    });
    expect(control('held-undo')).toBeNull();
  });

  it('warns beside the goal before typing on an ended session', async () => {
    const page = mountSession({ session: { ended_at: 999 } });
    await settle(page);
    expect(text('[data-next-cockpit-held-field="goal"]')).toContain(
      'This session has ended, so Cargento can only read the goal drafted from your prompt.',
    );
    expect(goalBox().value).toBe('Ship the queue worker');
  });

  it('keeps More open and held fields across refresh and a remount', async () => {
    const page = mountSession({ store: { goal: 'Saved', lines: ['A check'], revision: 1 } });
    await settle(page);
    const trigger = document.querySelector(
      '[data-next-session-more] [data-slot="accordion-trigger"]',
    );
    await act(async () => {
      fireEvent.click(trigger as Element);
    });
    type(goalBox(), 'Held words');
    type(lineBoxes()[0] as HTMLTextAreaElement, 'Held outcome');
    await page.poll({ ...(page.state.data as object), generated: 1100 });
    expect(trigger?.getAttribute('aria-expanded')).toBe('true');
    await page.go('#n=sessions');
    await page.go('#n=session:alpha%2Fapp:claude:s1');
    expect(
      document
        .querySelector('[data-next-session-more] [data-slot="accordion-trigger"]')
        ?.getAttribute('aria-expanded'),
    ).toBe('true');
    expect(goalBox().value).toBe('Held words');
    expect(lineBoxes()[0]?.value).toBe('Held outcome');
    expect(page.posts()).toBe(0);
  });
});
