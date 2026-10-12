import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { openSelect } from '../../test/select';
import { userEvent } from 'storybook/test';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '../ui/select';
import { choiceOpenIn, installChoiceRelease } from './displayGate';

function Choice({ name }: { name: string }) {
  return (
    <Select defaultValue="a" items={{ a: 'Alpha', b: 'Beta' }}>
      <SelectTrigger aria-label={name}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="a">Alpha</SelectItem>
        <SelectItem value="b">Beta</SelectItem>
      </SelectContent>
    </Select>
  );
}

describe('an open Base UI choice', () => {
  it('holds only an open popup from the page, including focus in its portal, and never a merely focused trigger', async () => {
    const view = render(
      <div>
        <section data-root>
          <Choice name="Inside" />
        </section>
        <Choice name="Outside" />
      </div>,
    );
    const root = () => view.container.querySelector('[data-root]');
    const inside = screen.getByRole('combobox', { name: 'Inside' });
    const user = userEvent.setup();
    inside.focus();
    expect(choiceOpenIn(root)).toBe(false);
    await openSelect(inside);
    expect(choiceOpenIn(root)).toBe(true);
    screen.getByRole('listbox').focus();
    expect(choiceOpenIn(root)).toBe(true);
    await user.keyboard('{Escape}');
    expect(choiceOpenIn(root)).toBe(false);
    await openSelect(screen.getByRole('combobox', { name: 'Outside' }));
    expect(choiceOpenIn(root)).toBe(false);
    expect(choiceOpenIn(() => null)).toBe(false);
  });

  it('catches up once after a choice or Escape, ignores unrelated controls, and disconnects on disposal', async () => {
    render(<Choice name="Choice" />);
    const gate = { releaseChoice: vi.fn(() => true) };
    const remove = installChoiceRelease(document, gate);
    const user = userEvent.setup();
    const trigger = screen.getByRole('combobox');
    await openSelect(trigger);
    await user.click(screen.getByRole('option', { name: 'Beta' }));
    await waitFor(() => expect(gate.releaseChoice).toHaveBeenCalledTimes(1));
    await openSelect(trigger);
    await user.keyboard('{Escape}');
    await waitFor(() => expect(gate.releaseChoice).toHaveBeenCalledTimes(2));
    document.body.dispatchEvent(new Event('change', { bubbles: true }));
    trigger.focus();
    trigger.blur();
    expect(gate.releaseChoice).toHaveBeenCalledTimes(2);
    remove();
    await openSelect(trigger);
    await user.keyboard('{Escape}');
    expect(gate.releaseChoice).toHaveBeenCalledTimes(2);
  });
});
