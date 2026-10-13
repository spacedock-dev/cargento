import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, userEvent, within } from 'storybook/test';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../src/ui/tooltip';
const meta = { title: 'UI/Tooltip', component: TooltipContent } satisfies Meta<
  typeof TooltipContent
>;
export default meta;
type Story = StoryObj<typeof meta>;
export const NonFocusable: Story = {
  render: () => (
    <TooltipProvider delay={0}>
      <Tooltip>
        <TooltipTrigger render={<span />} aria-label="Full words">
          Short words
        </TooltipTrigger>
        <TooltipContent>Full words</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  ),
  play: async ({ canvasElement }) => {
    const trigger = within(canvasElement).getByLabelText('Full words');
    await expect(trigger.tabIndex).toBe(-1);
    await userEvent.hover(trigger);
    await expect(
      await within(canvasElement.ownerDocument.body).findByRole('tooltip'),
    ).toHaveTextContent('Full words');
  },
};
