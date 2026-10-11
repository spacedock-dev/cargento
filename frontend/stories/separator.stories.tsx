import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, within } from 'storybook/test';
import { Separator } from '../src/ui/separator';
const meta = { title: 'UI/Separator', component: Separator } satisfies Meta<typeof Separator>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Horizontal: Story = {
  args: {},
  play: async ({ canvasElement }) => {
    const node = within(canvasElement).getByRole('separator');
    await expect(node).toHaveAttribute('aria-orientation', 'horizontal');
    await expect(node.getBoundingClientRect().height).toBeGreaterThan(0);
  },
};
export const Vertical: Story = {
  render: () => (
    <div style={{ display: 'flex', height: 100 }}>
      <Separator orientation="vertical" />
    </div>
  ),
  play: async ({ canvasElement }) => {
    const node = within(canvasElement).getByRole('separator');
    await expect(node).toHaveAttribute('aria-orientation', 'vertical');
    await expect(node.getBoundingClientRect().height).toBe(100);
  },
};
export const Decorative: Story = {
  args: { role: 'presentation', 'aria-hidden': true },
  play: async ({ canvasElement }) => {
    await expect(within(canvasElement).queryByRole('separator')).toBeNull();
  },
};
