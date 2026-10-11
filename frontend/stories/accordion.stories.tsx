import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, userEvent, within, waitFor } from 'storybook/test';
import { Accordion, AccordionItem, AccordionTrigger, AccordionContent } from '../src/ui/accordion';
const meta = { title: 'UI/Accordion', component: Accordion } satisfies Meta<typeof Accordion>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Keyboard: Story = {
  render: () => (
    <Accordion multiple>
      <AccordionItem value="plan">
        <AccordionTrigger>Project plan</AccordionTrigger>
        <AccordionContent>
          <p>Plan body</p>
        </AccordionContent>
      </AccordionItem>
      <AccordionItem value="disabled" disabled>
        <AccordionTrigger>Unavailable section</AccordionTrigger>
        <AccordionContent>Unavailable body</AccordionContent>
      </AccordionItem>
    </Accordion>
  ),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const trigger = canvas.getByRole('button', { name: 'Project plan' });
    await expect(trigger).toHaveAttribute('aria-expanded', 'false');
    trigger.focus();
    await userEvent.keyboard('{Enter}');
    await expect(trigger).toHaveAttribute('aria-expanded', 'true');
    await waitFor(() => expect(canvas.getByText('Plan body')).toBeVisible());
    await userEvent.keyboard(' ');
    await expect(trigger).toHaveAttribute('aria-expanded', 'false');
    await expect(trigger).toHaveFocus();
    await expect(canvas.getByRole('button', { name: 'Unavailable section' })).toHaveAttribute(
      'aria-disabled',
      'true',
    );
    const unavailable = canvas.getByRole('button', { name: 'Unavailable section' });
    unavailable.focus();
    await userEvent.keyboard('{Enter}');
    await expect(unavailable).toHaveAttribute('aria-expanded', 'false');
  },
};
