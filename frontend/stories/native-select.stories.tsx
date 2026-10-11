import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, userEvent, within } from 'storybook/test';
import { useState } from 'react';
import { NativeSelect } from '../src/ui/native-select';
const meta = { title: 'UI/NativeSelect', component: NativeSelect } satisfies Meta<
  typeof NativeSelect
>;
export default meta;
type Story = StoryObj<typeof meta>;
const appearances = ['prompt', 'stage', 'direction', 'gallery'] as const;
export const Appearances: Story = {
  render: () => (
    <>
      {appearances.map((appearance) => (
        <NativeSelect
          key={appearance}
          appearance={appearance}
          aria-label={`${appearance} choice`}
          defaultValue="long"
        >
          <option value="long">
            A long choice whose chevron must leave room for the reader's text
          </option>
          <option value="short">Short choice</option>
        </NativeSelect>
      ))}
    </>
  ),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    for (const appearance of appearances) {
      const node = canvas.getByRole('combobox', { name: `${appearance} choice` });
      await expect(node.tagName).toBe('SELECT');
      await userEvent.selectOptions(node, 'short');
      await expect(node).toHaveValue('short');
    }
  },
};
function PromptExample({ initial = 'idle' }: { initial?: 'idle' | 'loading' | 'loaded' }) {
  const [state, setState] = useState(initial);
  return (
    <>
      <NativeSelect
        appearance="prompt"
        aria-label="Use your prompt"
        aria-busy={state === 'loading'}
        disabled={state !== 'loaded'}
        defaultValue=""
        style={{ width: 240 }}
      >
        <option value="">Use your prompt</option>
        {state === 'loaded' ? <option value="intent">Ship the reader's intent</option> : null}
      </NativeSelect>
      {state === 'loading' ? <p role="status">Loading your prompts</p> : null}
      <button type="button" onClick={() => setState('loading')}>
        Load prompts
      </button>
      <button type="button" onClick={() => setState('loaded')}>
        Finish loading
      </button>
    </>
  );
}
async function promptStates({ canvasElement }: { canvasElement: HTMLElement }) {
  const canvas = within(canvasElement);
  const select = canvas.getByRole('combobox', { name: 'Use your prompt' });
  const width = select.getBoundingClientRect().width;
  await expect(select.tagName).toBe('SELECT');
  await expect(select).toBeDisabled();
  await expect(select).toHaveAttribute('aria-busy', 'false');
  await userEvent.click(canvas.getByRole('button', { name: 'Load prompts' }));
  await expect(select).toHaveAttribute('aria-busy', 'true');
  await expect(canvas.getByRole('status')).toHaveTextContent('Loading your prompts');
  await expect(select.getBoundingClientRect().width).toBe(width);
  await userEvent.click(canvas.getByRole('button', { name: 'Finish loading' }));
  await expect(select).toBeEnabled();
  await expect(select).toHaveAttribute('aria-busy', 'false');
  await expect(select.tagName).toBe('SELECT');
  await expect(select.getBoundingClientRect().width).toBe(width);
  await userEvent.selectOptions(select, 'intent');
  await expect(select).toHaveValue('intent');
}
export const PromptIdle: Story = { render: () => <PromptExample />, play: promptStates };
export const PromptLoading: Story = {
  render: () => <PromptExample initial="loading" />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(canvas.getByRole('combobox')).toHaveAttribute('aria-busy', 'true');
    await expect(canvas.getByRole('status')).toHaveTextContent('Loading your prompts');
  },
};
export const PromptLoaded: Story = {
  render: () => <PromptExample initial="loaded" />,
  play: async ({ canvasElement }) => {
    const select = within(canvasElement).getByRole('combobox');
    await expect(select.tagName).toBe('SELECT');
    await userEvent.selectOptions(select, 'intent');
    await expect(select).toHaveValue('intent');
  },
};
