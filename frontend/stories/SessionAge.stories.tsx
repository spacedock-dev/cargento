import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, within } from 'storybook/test';
import { SessionAge } from '../src/sessions/SessionAge';
import '../src/sessions/sessions.css';

const NOW = 1900000000;
const meta = {
  title: 'Sessions/Header age',
  component: SessionAge,
  args: { session: { started_at: NOW - 23 * 3600 }, generated: NOW },
} satisfies Meta<typeof SessionAge>;
export default meta;
type Story = StoryObj<typeof meta>;
export const PublishedStart: Story = {
  play: async ({ canvasElement }) => {
    const age = within(canvasElement).getByText('Started about 23h 0m ago');
    await expect(age).toBeVisible();
    await expect(age).toHaveAttribute(
      'title',
      `Started: ${new Date((NOW - 23 * 3600) * 1000).toLocaleString()}`,
    );
  },
};
export const FirstMessage: Story = {
  args: { session: { first_prompt_at: NOW - 7 * 86400 } },
  play: async ({ canvasElement }) => {
    const age = within(canvasElement).getByText('Started about 7d 0h ago');
    await expect(age).toBeVisible();
    await expect(age.title).toBe(
      `From the first message in the record: ${new Date((NOW - 7 * 86400) * 1000).toLocaleString()}`,
    );
  },
};
export const AbsentStart: Story = {
  args: { session: {} },
  play: async ({ canvasElement }) => {
    await expect(canvasElement.querySelector('[data-session-age]')).toBeNull();
  },
};
export const PhoneHeader: Story = {
  render: (args) => (
    <div style={{ width: 343, maxWidth: '100%' }}>
      <header className="next-session-detail-header">
        <div className="next-session-detail-title">
          <h1>Synthetic record</h1>
          <p className="next-session-identity">
            claude · 67c039ff · 411 /m · recce/cargento
            <SessionAge {...args} />
          </p>
        </div>
      </header>
    </div>
  ),
  play: async ({ canvasElement }) => {
    const line = canvasElement.querySelector('.next-session-identity') as HTMLElement;
    await expect(within(line).getByText('Started about 23h 0m ago')).toBeVisible();
    await expect(line.scrollWidth).toBeLessThanOrEqual(343);
    // Two existing metadata lines at the phone's padded width; appending age introduces no new block.
    await expect(line.getBoundingClientRect().height).toBeLessThanOrEqual(40);
    await expect(canvasElement.querySelectorAll('.next-session-identity')).toHaveLength(1);
  },
};
