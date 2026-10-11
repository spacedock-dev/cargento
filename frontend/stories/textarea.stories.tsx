import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, userEvent, within } from 'storybook/test';
import { Textarea } from '../src/ui/textarea';
const meta = { title: 'UI/Textarea', component: Textarea } satisfies Meta<typeof Textarea>;
export default meta;
type Story = StoryObj<typeof meta>;
export const intentEditable: Story = {
  args: { appearance: 'intent', 'aria-label': 'intentEditable' },
  play: async ({ canvasElement }) => {
    const node = within(canvasElement).getByRole('textbox', { name: 'intentEditable' });
    await userEvent.type(node, 'Reader words');
    await expect(node).toHaveValue('Reader words');
  },
};
export const intentInvalid: Story = {
  args: { appearance: 'intent', 'aria-invalid': true, 'aria-label': 'intentInvalid' },
  play: async ({ canvasElement }) => {
    const node = within(canvasElement).getByRole('textbox', { name: 'intentInvalid' });
    await userEvent.type(node, 'Reader words');
    await expect(node).toHaveValue('Reader words');
    await expect(node).toHaveAttribute('aria-invalid', 'true');
  },
};
export const intentDisabled: Story = {
  args: { appearance: 'intent', disabled: true, 'aria-label': 'intentDisabled' },
  play: async ({ canvasElement }) => {
    const node = within(canvasElement).getByRole('textbox', { name: 'intentDisabled' });
    await expect(node).toBeDisabled();
  },
};
export const memoEditable: Story = {
  args: { appearance: 'memo', 'aria-label': 'memoEditable' },
  play: async ({ canvasElement }) => {
    const node = within(canvasElement).getByRole('textbox', { name: 'memoEditable' });
    await userEvent.type(node, 'Reader words');
    await expect(node).toHaveValue('Reader words');
  },
};
export const memoInvalid: Story = {
  args: { appearance: 'memo', 'aria-invalid': true, 'aria-label': 'memoInvalid' },
  play: async ({ canvasElement }) => {
    const node = within(canvasElement).getByRole('textbox', { name: 'memoInvalid' });
    await userEvent.type(node, 'Reader words');
    await expect(node).toHaveValue('Reader words');
    await expect(node).toHaveAttribute('aria-invalid', 'true');
  },
};
export const memoDisabled: Story = {
  args: { appearance: 'memo', disabled: true, 'aria-label': 'memoDisabled' },
  play: async ({ canvasElement }) => {
    const node = within(canvasElement).getByRole('textbox', { name: 'memoDisabled' });
    await expect(node).toBeDisabled();
  },
};
export const draftEditable: Story = {
  args: { appearance: 'draft', 'aria-label': 'draftEditable' },
  play: async ({ canvasElement }) => {
    const node = within(canvasElement).getByRole('textbox', { name: 'draftEditable' });
    await userEvent.type(node, 'Reader words');
    await expect(node).toHaveValue('Reader words');
  },
};
export const draftInvalid: Story = {
  args: { appearance: 'draft', 'aria-invalid': true, 'aria-label': 'draftInvalid' },
  play: async ({ canvasElement }) => {
    const node = within(canvasElement).getByRole('textbox', { name: 'draftInvalid' });
    await userEvent.type(node, 'Reader words');
    await expect(node).toHaveValue('Reader words');
    await expect(node).toHaveAttribute('aria-invalid', 'true');
  },
};
export const draftDisabled: Story = {
  args: { appearance: 'draft', disabled: true, 'aria-label': 'draftDisabled' },
  play: async ({ canvasElement }) => {
    const node = within(canvasElement).getByRole('textbox', { name: 'draftDisabled' });
    await expect(node).toBeDisabled();
  },
};
export const correctionEditable: Story = {
  args: { appearance: 'correction', 'aria-label': 'correctionEditable' },
  play: async ({ canvasElement }) => {
    const node = within(canvasElement).getByRole('textbox', { name: 'correctionEditable' });
    await userEvent.type(node, 'Reader words');
    await expect(node).toHaveValue('Reader words');
  },
};
export const correctionInvalid: Story = {
  args: { appearance: 'correction', 'aria-invalid': true, 'aria-label': 'correctionInvalid' },
  play: async ({ canvasElement }) => {
    const node = within(canvasElement).getByRole('textbox', { name: 'correctionInvalid' });
    await userEvent.type(node, 'Reader words');
    await expect(node).toHaveValue('Reader words');
    await expect(node).toHaveAttribute('aria-invalid', 'true');
  },
};
export const correctionDisabled: Story = {
  args: { appearance: 'correction', disabled: true, 'aria-label': 'correctionDisabled' },
  play: async ({ canvasElement }) => {
    const node = within(canvasElement).getByRole('textbox', { name: 'correctionDisabled' });
    await expect(node).toBeDisabled();
  },
};
