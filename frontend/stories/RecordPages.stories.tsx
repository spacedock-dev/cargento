import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, userEvent, within, waitFor } from 'storybook/test';
import { useEffect, useState } from 'react';
import { ShowMore } from '../src/drift/ShowMore';
import { EMPTY_RECORD } from '../src/store/board';
import { createShell } from '../src/shell/createShell';
import { App } from '../src/App';
import { createRouter } from '../src/router/router';
import { fakeRouterEnvironment } from '../src/router/testing';
import { createFakeClock, createFakeEnvironment } from '../src/transport/testing';
import { fakeBackend } from '../test/storage_backends';

const meta = {
  title: 'Drift/Record pages',
  component: ShowMore,
  args: { onMore: () => undefined },
} satisfies Meta<typeof ShowMore>;
export default meta;
type Story = StoryObj<typeof meta>;
const ready = { ...EMPTY_RECORD, status: 'loaded' as const, pages: 1, next: 'older' };
const pagingButton = async (element: HTMLElement) => {
  const button = within(element).getByRole('button', { name: 'Show 50 older entries' });
  await expect(button.tagName).toBe('BUTTON');
  await expect(button).toHaveTextContent('Show more');
  await expect(button.getBoundingClientRect().height).toBeGreaterThanOrEqual(44);
  await expect(button.getBoundingClientRect().width).toBeGreaterThanOrEqual(44);
};
export const Idle: Story = {
  args: { record: ready },
  play: async ({ canvasElement }) => pagingButton(canvasElement),
};
export const Loading: Story = {
  args: { record: { ...ready, status: 'loading' } },
  play: async ({ canvasElement }) => {
    const button = within(canvasElement).getByRole('button', { name: 'Reading older entries' });
    await expect(button).toHaveAttribute('aria-busy', 'true');
    await expect(button).toHaveAttribute('aria-disabled', 'true');
    await expect(button).toHaveTextContent('Reading older entries');
    await expect(button.getBoundingClientRect().height).toBeGreaterThanOrEqual(44);
  },
};
export const ReadError: Story = {
  args: { record: { ...ready, status: 'error', error: { kind: 'network-error' } } },
  play: async ({ canvasElement }) => {
    await expect(within(canvasElement).getByRole('status')).toHaveTextContent(
      'Could not read older entries',
    );
    await pagingButton(canvasElement);
  },
};
export const BoundStop: Story = {
  args: { record: { ...ready, bound: 'bytes', scannedBytes: 16777216 } },
  play: async ({ canvasElement }) => {
    await expect(
      within(canvasElement).getByText(
        'The read stopped after reading 16 MB without reaching 50 more entries; Show more continues from there.',
      ),
    ).toBeVisible();
    await pagingButton(canvasElement);
  },
};
export const ReachedStart: Story = {
  args: { record: { ...ready, reachedStart: true, next: null } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(canvas.getByText('That is the start of the record.')).toBeVisible();
    await expect(canvas.queryByRole('button')).toBeNull();
  },
};
export const Unsupported: Story = {
  args: { record: { ...EMPTY_RECORD, status: 'unsupported' } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(canvas.getByText('Older entries are not read for this harness.')).toBeVisible();
    await expect(canvas.queryByRole('button')).toBeNull();
  },
};
export const Restarted: Story = {
  args: { record: { ...ready, restarted: true } },
  play: async ({ canvasElement }) => {
    await expect(within(canvasElement).getByRole('status')).toHaveTextContent(
      'The record changed. Started again from the newest entries.',
    );
    await pagingButton(canvasElement);
  },
};
export const WindowCovered: Story = {
  args: { record: ready, pastWindow: true },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(
      canvas.getByText("Everything since your intent's window opened is listed."),
    ).toBeVisible();
    const boundary = canvas.getByText("Everything since your intent's window opened is listed.");
    await expect(boundary).toHaveAttribute('tabindex', '-1');
    boundary.focus({ preventScroll: true });
    await expect(document.activeElement).toBe(boundary);
    await expect(canvas.queryByRole('button')).toBeNull();
  },
};

function SessionRecordExample({ intent = false }: { readonly intent?: boolean }) {
  const [shell] = useState(() => {
    const history = fakeRouterEnvironment('#n=session:demo:claude:s1');
    const clock = createFakeClock();
    const data = {
      generated: 1900000000,
      annotate: intent,
      sessions: [
        {
          harness: 'claude',
          sid: 's1',
          project: 'demo',
          project_key: '/demo',
          title: 'Synthetic record',
          state: 'idle',
          started_at: 1900000000 - 23 * 3600,
          ...(intent
            ? {
                annotation_goal: 'Synthetic goal',
                annotation_revision: 1,
                annotation_at: 1900000000 - 200,
                annotation_goal_saved_at: 1900000000 - 200,
                annotation_window_start: 1900000000 - 200,
              }
            : {}),
        },
      ],
    };
    return createShell({
      env: createFakeEnvironment({ clock }),
      router: createRouter(history.env),
      provider: () => fakeBackend(),
      events: { addEventListener: () => undefined, removeEventListener: () => undefined },
      search: '',
      doc: null,
      reducedMotion: () => true,
      fetch: (url) => {
        const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });
        if (url.startsWith('/api/data')) return Promise.resolve(json(data));
        if (url === '/api/direction')
          return Promise.resolve(
            json({ ok: true, text: 'Synthetic older direction', clipped: false }),
          );
        if (url.startsWith('/api/session-record')) {
          const older = url.includes('before=');
          return Promise.resolve(
            json({
              state: 'ok',
              session: { harness: 'claude', sid: 's1' },
              entries: Array.from({ length: 50 }, (_, i) => ({
                fact_id: `e${String((older ? 50 : 100) - i)}`,
                at: 1900000000 - (older ? 50 : 0) - i,
                type: 'user_message',
                by: 'person:reader',
                source_session: { harness: 'claude', sid: 's1' },
                summary: `Synthetic entry ${String((older ? 50 : 100) - i)}`,
                evidence: { source: 'transcript', confidence: 'exact' },
              })),
              next: 'older',
              reached_start: false,
              bound: null,
              scanned_bytes: 65536,
              kinds: ['user_message', 'agent_message'],
            }),
          );
        }
        return Promise.resolve(json({}));
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
  return <App shell={shell} />;
}
export const ReaderAppendsOlderEntries: Story = {
  render: () => <SessionRecordExample />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const button = await canvas.findByRole('button', { name: 'Show 50 older entries' });
    await waitFor(() =>
      expect(canvasElement.querySelectorAll('[data-next-entry-id]')).toHaveLength(50),
    );
    button.focus({ preventScroll: true });
    window.scrollTo({
      top: button.getBoundingClientRect().top + window.scrollY - 200,
      behavior: 'instant',
    });
    await new Promise<void>((resolve) =>
      requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
    );
    const offset = window.scrollY;
    await userEvent.click(button);
    await waitFor(() =>
      expect(canvasElement.querySelectorAll('[data-next-entry-id]')).toHaveLength(100),
    );
    await new Promise<void>((resolve) =>
      requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
    );
    await expect(document.activeElement).toBe(button);
    await expect(window.scrollY).toBe(offset);
    await expect(canvas.getByText('Numbers count from the oldest entry loaded.')).toBeVisible();
    await expect(canvasElement.querySelector('[data-next-entry-id]')).toHaveAttribute(
      'data-next-entry',
      '100',
    );
    window.scrollTo({ top: 0, behavior: 'instant' });
  },
};

export const OlderDirectionDraftSurvivesNavigation: Story = {
  render: () => <SessionRecordExample intent />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByRole('button', { name: 'Show 50 older entries' }));
    await waitFor(() =>
      expect(canvasElement.querySelectorAll('[data-next-entry-id]')).toHaveLength(100),
    );
    const row = canvasElement.querySelector('[data-next-entry-id="e50"]') as HTMLElement;
    await userEvent.click(within(row).getByRole('button', { name: 'Add to my intent' }));
    await expect(await canvas.findByDisplayValue('Synthetic older direction')).toBeVisible();
    // Primary links belong to browser hashchange; this isolated router owns its keyboard path.
    await userEvent.click(canvas.getByRole('heading', { name: 'Session activity' }));
    await userEvent.keyboard('s');
    await userEvent.click(await canvas.findByRole('link', { name: /Synthetic record/ }));
    await waitFor(() =>
      expect(canvasElement.querySelectorAll('[data-next-entry-id]')).toHaveLength(50),
    );
    await expect(await canvas.findByDisplayValue('Synthetic older direction')).toBeVisible();
    await expect(canvasElement.querySelector('[data-next-entry-id="e50"]')).toBeNull();
  },
};
