import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, userEvent, within } from 'storybook/test';
import { Input } from '../src/ui/input';
const meta = { title: 'UI/Input', component: Input } satisfies Meta<typeof Input>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Editable: Story = {
  args: { 'aria-label': 'Editable' },
  play: async ({ canvasElement }) => {
    const node = within(canvasElement).getByRole('textbox', { name: 'Editable' });
    await userEvent.type(node, 'Reader words');
    await expect(node).toHaveValue('Reader words');
  },
};
export const Invalid: Story = {
  args: { 'aria-invalid': true, 'aria-label': 'Invalid' },
  play: async ({ canvasElement }) => {
    const node = within(canvasElement).getByRole('textbox', { name: 'Invalid' });
    await userEvent.type(node, 'Reader words');
    await expect(node).toHaveValue('Reader words');
    await expect(node).toHaveAttribute('aria-invalid', 'true');
  },
};
export const Disabled: Story = {
  args: { disabled: true, 'aria-label': 'Disabled' },
  play: async ({ canvasElement }) => {
    const node = within(canvasElement).getByRole('textbox', { name: 'Disabled' });
    await expect(node).toBeDisabled();
  },
};
