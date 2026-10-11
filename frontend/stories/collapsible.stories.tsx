import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, userEvent, within, waitFor } from 'storybook/test';
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from '../src/ui/collapsible';
const meta = { title: 'UI/Collapsible', component: Collapsible } satisfies Meta<typeof Collapsible>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Keyboard: Story = {
  render: () => (
    <Collapsible>
      <CollapsibleTrigger>Collapsible section</CollapsibleTrigger>
      <CollapsibleContent>Small collapsible body</CollapsibleContent>
    </Collapsible>
  ),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const trigger = canvas.getByRole('button', { name: 'Collapsible section' });
    trigger.focus();
    await userEvent.keyboard('{Enter}');
    await waitFor(() => expect(canvas.getByText('Small collapsible body')).toBeVisible());
    await expect(trigger).toHaveAttribute('aria-expanded', 'true');
    await userEvent.keyboard(' ');
    await expect(trigger).toHaveAttribute('aria-expanded', 'false');
    await expect(trigger).toHaveFocus();
  },
};
export const Disabled: Story = {
  render: () => (
    <Collapsible disabled>
      <CollapsibleTrigger>Unavailable section</CollapsibleTrigger>
      <CollapsibleContent>Body</CollapsibleContent>
    </Collapsible>
  ),
  play: async ({ canvasElement }) => {
    await expect(
      within(canvasElement).getByRole('button', { name: 'Unavailable section' }),
    ).toHaveAttribute('aria-disabled', 'true');
    const trigger = within(canvasElement).getByRole('button', { name: 'Unavailable section' });
    trigger.focus();
    await userEvent.keyboard('{Enter}');
    await expect(trigger).toHaveAttribute('aria-expanded', 'false');
  },
};
