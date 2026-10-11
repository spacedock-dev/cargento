import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, userEvent, within, waitFor } from 'storybook/test';
import { useState } from 'react';
import { DisclosureChevron } from '../src/ui/disclosureChevron';
const meta = { title: 'UI/DisclosureChevron', component: DisclosureChevron } satisfies Meta<
  typeof DisclosureChevron
>;
export default meta;
type Story = StoryObj<typeof meta>;
function Example() {
  const [open, setOpen] = useState(false);
  return (
    <button type="button" aria-expanded={open} onClick={() => setOpen(!open)}>
      Plan
      <DisclosureChevron />
    </button>
  );
}
export const Rotation: Story = {
  render: () => <Example />,
  play: async ({ canvasElement }) => {
    const button = within(canvasElement).getByRole('button', { name: 'Plan' });
    const svg = button.querySelector('svg');
    if (!svg) throw new Error('Missing chevron');
    await expect(svg).toHaveAttribute('aria-hidden', 'true');
    const closed = getComputedStyle(svg).rotate;
    await userEvent.click(button);
    await expect(button).toHaveAttribute('aria-expanded', 'true');
    await waitFor(() => expect(getComputedStyle(svg).rotate).not.toBe(closed));
    await expect(within(canvasElement).queryByRole('img')).toBeNull();
  },
};
