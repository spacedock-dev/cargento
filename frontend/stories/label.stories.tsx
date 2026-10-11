import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, userEvent, within } from 'storybook/test';
import { Label } from '../src/ui/label';
import { Input } from '../src/ui/input';
const meta = { title: 'UI/Label', component: Label } satisfies Meta<typeof Label>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Associated: Story = {
  render: () => (
    <>
      <Label htmlFor="label-input">Intent words</Label>
      <Input id="label-input" />
    </>
  ),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByText('Intent words'));
    await expect(canvas.getByRole('textbox', { name: 'Intent words' })).toHaveFocus();
  },
};
