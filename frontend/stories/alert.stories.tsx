import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, within } from 'storybook/test';
import { Alert } from '../src/ui/alert';
const meta = { title: 'UI/Alert', component: Alert } satisfies Meta<typeof Alert>;
export default meta;
type Story = StoryObj<typeof meta>;
export const SessionHealth: Story = {
  args: { variant: 'session-health', children: 'Alert session-health' },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await expect(canvas.getByRole('status')).toHaveTextContent(args.children as string);
  },
};
export const ObserverStatus: Story = {
  args: { variant: 'observer-status', children: 'Alert observer-status' },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await expect(canvas.getByRole('status')).toHaveTextContent(args.children as string);
  },
};
export const AnswerFailure: Story = {
  args: { variant: 'answer-failure', children: 'Alert answer-failure' },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await expect(canvas.getByRole('status')).toHaveTextContent(args.children as string);
  },
};
export const IntentNote: Story = {
  args: { variant: 'intent-note', children: 'Alert intent-note' },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await expect(canvas.getByRole('status')).toHaveTextContent(args.children as string);
  },
};
export const ShellNotice: Story = {
  args: { variant: 'shell-notice', children: 'Alert shell-notice' },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await expect(canvas.getByRole('status')).toHaveTextContent(args.children as string);
  },
};
export const TerminalAbsence: Story = {
  args: { variant: 'terminal-absence', children: 'Alert terminal-absence' },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await expect(canvas.getByRole('status')).toHaveTextContent(args.children as string);
  },
};
export const TimelineStale: Story = {
  args: { variant: 'timeline-stale', children: 'Alert timeline-stale' },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await expect(canvas.getByRole('status')).toHaveTextContent(args.children as string);
  },
};
export const DriftNudge: Story = {
  args: { variant: 'drift-nudge', children: 'Alert drift-nudge' },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await expect(canvas.getByRole('status')).toHaveTextContent(args.children as string);
  },
};
export const Silent: Story = {
  args: { announce: false, children: 'Quiet notice' },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(canvas.queryByRole('status')).toBeNull();
    await expect(canvas.getByText('Quiet notice')).toBeVisible();
  },
};
