import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, userEvent, within, waitFor } from 'storybook/test';
import { useEffect, useState } from 'react';
import { App } from '../src/App';
import { createShell } from '../src/shell/createShell';
import { createRouter } from '../src/router/router';
import { fakeRouterEnvironment } from '../src/router/testing';
import { createFakeClock, createFakeEnvironment } from '../src/transport/testing';
import { fakeBackend } from '../test/storage_backends';

function DirectionsExample({
  reason,
  count = 2,
}: {
  readonly reason?: 'not_found' | 'out_of_reach';
  readonly count?: number;
}) {
  const [shell] = useState(() => {
    const clock = createFakeClock();
    const history = fakeRouterEnvironment('#n=session:demo:claude:s1');
    let generation = 1000;
    const facts = Array.from({ length: count }, (_, index) => index + 1).map((n) => ({
      fact_id: `f${String(n)}`,
      type: 'user_message',
      at: 600 + n * 100,
      summary: `Build synthetic outcome ${String(n)}.`,
      source_session: { harness: 'claude', sid: 's1' },
      by: 'person:reader',
    }));
    return createShell({
      env: createFakeEnvironment({ clock }),
      router: createRouter(history.env),
      provider: () => fakeBackend(),
      events: { addEventListener: () => undefined, removeEventListener: () => undefined },
      search: '',
      doc: null,
      reducedMotion: () => true,
      fetch: async (url) => {
        const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });
        if (url.startsWith('/api/data'))
          return json({
            generated: generation++,
            annotate: true,
            annotate_cap: 240,
            sessions: [
              {
                harness: 'claude',
                sid: 's1',
                project: 'demo',
                project_key: '/demo',
                title: 'Synthetic long session',
                state: 'idle',
                annotation_goal: 'Ship synthetic work',
                annotation_revision: 1,
                annotation_at: 500,
                annotation_goal_saved_at: 500,
                annotation_window_start: 500,
              },
            ],
          });
        if (url.startsWith('/api/project-context')) return json({ semantic: { facts } });
        if (url.startsWith('/api/session-record'))
          return json({ state: 'ok', entries: [], next: null, reached_start: true });
        if (url === '/api/direction')
          return json(
            reason
              ? { ok: false, reason }
              : {
                  ok: true,
                  text: 'Build synthetic outcome 2.',
                  clipped: false,
                  goal_choice: {
                    fact_id: 'f2',
                    at: 800,
                    text: 'Build synthetic outcome 2.',
                    cut: false,
                  },
                },
          );
        return json({});
      },
    });
  });
  useEffect(
    () => () => {
      shell.runtime.dispose();
      shell.display.dispose();
    },
    [shell],
  );
  return (
    <>
      <App shell={shell} />
      <button type="button" onClick={() => void shell.runtime.refresh()}>
        Simulate board poll
      </button>
    </>
  );
}

const meta = { title: 'Intent/Direction actions', component: DirectionsExample } satisfies Meta<
  typeof DirectionsExample
>;
export default meta;
type Story = StoryObj<typeof meta>;

async function failedPress(element: HTMLElement, action: string, message: string) {
  const button = element.querySelector(
    `[data-next-cockpit-action="${action}"]`,
  ) as HTMLButtonElement;
  await waitFor(() => expect(button).not.toBeNull());
  await userEvent.click(button);
  await waitFor(() =>
    expect(button.parentElement?.querySelector('[data-next-action-feedback]')).toHaveTextContent(
      message,
    ),
  );
  await expect(document.activeElement).toBe(button);
  await expect(document.querySelector('#next-cockpit-cue-status')).toHaveTextContent(message);
  await expect(document.querySelector('#next-cockpit-cue-status')).toHaveAttribute(
    'aria-live',
    'polite',
  );
  await expect(button).not.toHaveAttribute('aria-busy', 'true');
}

export const OutsideSearch: Story = {
  args: { reason: 'out_of_reach' },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByRole('button', { name: 'Keep my intent' });
    const prefix = 'That direction is beyond the part of the record Compass could search.';
    await failedPress(canvasElement, 'direction-goal', `${prefix} Your goal has not changed.`);
    await failedPress(canvasElement, 'direction-add', `${prefix} No outcome line was added.`);
    await failedPress(
      canvasElement,
      'direction-keep',
      `${prefix} Nothing was settled and no analysis was started.`,
    );
    const row = canvasElement.querySelector('[data-next-entry-id="f2"]') as HTMLElement;
    await failedPress(row, 'direction-add', `${prefix} No outcome line was added.`);
    await expect(canvas.getByRole('textbox', { name: 'Goal' })).toHaveValue('Ship synthetic work');
  },
};

export const MissingRecord: Story = {
  args: { reason: 'not_found' },
  play: async ({ canvasElement }) => {
    await within(canvasElement).findByRole('button', { name: 'Keep my intent' });
    await failedPress(
      canvasElement,
      'direction-keep',
      'That direction could not be verified as later than your intent in the current record. Nothing was settled and no analysis was started.',
    );
  },
};

export const TwentyTwoDirections: Story = {
  args: { count: 22 },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByRole('button', { name: 'Keep my intent' }));
    await waitFor(() =>
      expect(canvasElement.querySelectorAll('.next-cockpit-direction-whole-item')).toHaveLength(22),
    );
    await expect(canvasElement.querySelector('[data-next-action-feedback]')).toHaveTextContent(
      'Nothing was settled yet. Each direction Keep settles is now shown whole. Read it, then press again.',
    );
    await expect(document.activeElement).toBe(
      canvasElement.querySelector('[data-next-cockpit-direction-whole]'),
    );
    await expect(canvas.getByRole('button', { name: 'Keep my intent' })).not.toHaveAttribute(
      'aria-busy',
      'true',
    );
  },
};

export const PhoneDirectionAndPendingLine: Story = {
  parameters: { viewport: { defaultViewport: 'mobile1' } },
  globals: { viewport: { value: 'mobile1', isRotated: false } },
  play: async ({ canvasElement }) => {
    const browserPage =
      '__vitest_browser_runner__' in window ? (await import('vitest/browser')).page : null;
    const before = { width: window.innerWidth, height: window.innerHeight };
    if (browserPage) await browserPage.viewport(375, 667);
    try {
      if (browserPage) {
        await expect(window.innerWidth).toBe(375);
        await expect(window.innerHeight).toBe(667);
      }
      const canvas = within(canvasElement);
      await userEvent.click(await canvas.findByRole('button', { name: 'Add it to my intent' }));
      const line = await canvas.findByDisplayValue('Build synthetic outcome 2.');
      await expect(line.tagName).toBe('TEXTAREA');
      await expect(document.activeElement).toBe(line);
      await userEvent.clear(line);
      await userEvent.type(line, 'My reviewed synthetic outcome');
      await userEvent.click(canvas.getByRole('button', { name: 'Simulate board poll' }));
      await expect(line).toHaveValue('My reviewed synthetic outcome');
      await expect(line.getBoundingClientRect().width).toBeLessThanOrEqual(window.innerWidth);
      await expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(window.innerWidth);
      await expect(canvas.getByRole('button', { name: 'Save' })).toBeVisible();
      await expect(canvas.getByRole('button', { name: 'Remove' })).toBeVisible();
    } finally {
      if (browserPage) await browserPage.viewport(before.width, before.height);
    }
  },
};
