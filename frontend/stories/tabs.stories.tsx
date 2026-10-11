import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, userEvent, within } from 'storybook/test';
import { Tabs, TabsList, TabsTrigger } from '../src/ui/tabs';
const meta = { title: 'UI/Tabs', component: Tabs } satisfies Meta<typeof Tabs>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Keyboard: Story = {
  render: () => (
    <Tabs defaultValue="intent">
      <TabsList aria-label="Session views">
        <TabsTrigger value="intent">Intent</TabsTrigger>
        <TabsTrigger value="work">Work</TabsTrigger>
        <TabsTrigger value="unavailable" disabled>
          Unavailable
        </TabsTrigger>
      </TabsList>
    </Tabs>
  ),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const intent = canvas.getByRole('tab', { name: 'Intent' });
    const work = canvas.getByRole('tab', { name: 'Work' });
    await expect(intent).toHaveAttribute('aria-selected', 'true');
    intent.focus();
    await userEvent.keyboard('{ArrowRight}');
    await expect(work).toHaveFocus();
    await userEvent.keyboard('{Enter}');
    await expect(work).toHaveAttribute('aria-selected', 'true');
    await userEvent.keyboard('{ArrowLeft}{Enter}');
    await expect(intent).toHaveAttribute('aria-selected', 'true');
    await expect(canvas.getByRole('tab', { name: 'Unavailable' })).toHaveAttribute(
      'aria-disabled',
      'true',
    );
    const unavailable = canvas.getByRole('tab', { name: 'Unavailable' });
    unavailable.focus();
    await userEvent.keyboard('{Enter}');
    await expect(unavailable).toHaveAttribute('aria-selected', 'false');
  },
};
