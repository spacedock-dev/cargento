import { act, render } from '@testing-library/react';
import { StrictMode, useState } from 'react';
import { describe, expect, it } from 'vitest';
import { DraftInput, DraftTextarea } from './DraftField';
import { createFieldMemory, FIELD_MEMORY_LIMIT } from './fieldMemory';
import { ControlsProvider } from './ControlsProvider';
import { testControls } from './testControls';

function Host({ field, which }: { field: string; which: 'a' | 'b' | 'none' }) {
  return which === 'none' ? null : (
    <DraftTextarea
      memoryKey={`field:${field}:${which}`}
      defaultValue="one two three four five"
      aria-label="draft"
    />
  );
}

function mount(node: React.ReactElement) {
  const kit = testControls();
  const view = render(<ControlsProvider controls={kit.controls}>{node}</ControlsProvider>);
  const rerender = (next: React.ReactElement) =>
    view.rerender(<ControlsProvider controls={kit.controls}>{next}</ControlsProvider>);
  return { kit, view, rerender };
}

describe('a draft field keeps its caret, inner scroll and size by exact key', () => {
  it('puts the unfocused caret, scroll offsets and dragged size back on a remounted field', () => {
    const { view, rerender } = mount(<Host field="s1" which="a" />);
    const first = view.getByLabelText('draft') as HTMLTextAreaElement;
    first.setSelectionRange(4, 7);
    first.scrollTop = 33;
    first.scrollLeft = 5;
    first.style.height = '120px';
    first.style.width = '300px';
    rerender(<Host field="s1" which="none" />);
    expect(view.queryByLabelText('draft')).toBeNull();
    rerender(<Host field="s1" which="a" />);
    const second = view.getByLabelText('draft') as HTMLTextAreaElement;
    expect(second).not.toBe(first);
    expect([second.selectionStart, second.selectionEnd]).toEqual([4, 7]);
    expect(second.scrollTop).toBe(33);
    expect(second.scrollLeft).toBe(5);
    expect(second.style.height).toBe('120px');
    expect(second.style.width).toBe('300px');
    expect(document.activeElement).not.toBe(second);
  });

  it("never carries one key's state to another session's field", () => {
    const { view, rerender } = mount(<Host field="s1" which="a" />);
    const first = view.getByLabelText('draft') as HTMLTextAreaElement;
    first.setSelectionRange(2, 2);
    first.style.height = '99px';
    rerender(<Host field="s1" which="b" />);
    const other = view.getByLabelText('draft') as HTMLTextAreaElement;
    expect(other.style.height).toBe('');
    expect(other.selectionStart).not.toBe(2);
  });

  it('clamps a remembered caret to the text the field has now', () => {
    const kit = testControls();
    const view = render(
      <ControlsProvider controls={kit.controls}>
        <DraftTextarea memoryKey="k" defaultValue="long text here" aria-label="draft" />
      </ControlsProvider>,
    );
    (view.getByLabelText('draft') as HTMLTextAreaElement).setSelectionRange(10, 14);
    view.rerender(
      <ControlsProvider controls={kit.controls}>
        <DraftTextarea memoryKey="other" defaultValue="" aria-label="draft" />
      </ControlsProvider>,
    );
    view.rerender(
      <ControlsProvider controls={kit.controls}>
        <DraftTextarea memoryKey="k" defaultValue="short" aria-label="draft" />
      </ControlsProvider>,
    );
    const field = view.getByLabelText('draft') as HTMLTextAreaElement;
    expect([field.selectionStart, field.selectionEnd]).toEqual([5, 5]);
  });

  it('leaves a persisting field untouched through unrelated renders (same node, caret, text)', () => {
    function Page() {
      const [tick, setTick] = useState(0);
      return (
        <div data-tick={tick}>
          <button type="button" onClick={() => setTick(tick + 1)}>
            tick
          </button>
          <DraftInput memoryKey="k" defaultValue="hello world" aria-label="draft" />
        </div>
      );
    }
    const { view } = mount(<Page />);
    const input = view.getByLabelText('draft') as HTMLInputElement;
    input.focus();
    input.setSelectionRange(3, 3);
    act(() => view.getByRole('button', { name: 'tick' }).click());
    expect(view.getByLabelText('draft')).toBe(input);
    expect(document.activeElement).toBe(input);
    expect([input.selectionStart, input.selectionEnd]).toEqual([3, 3]);
  });

  it('is a no-op under StrictMode double effects', () => {
    const kit = testControls();
    const view = render(
      <StrictMode>
        <ControlsProvider controls={kit.controls}>
          <DraftTextarea memoryKey="k" defaultValue="abc def" aria-label="draft" />
        </ControlsProvider>
      </StrictMode>,
    );
    const field = view.getByLabelText('draft') as HTMLTextAreaElement;
    expect(field.value).toBe('abc def');
    expect(kit.controls.fields.size()).toBeLessThanOrEqual(1);
  });

  it('bounds what it remembers and evicts the oldest key', () => {
    const memory = createFieldMemory();
    for (let index = 0; index < FIELD_MEMORY_LIMIT + 5; index += 1) {
      const input = document.createElement('input');
      input.value = 'abcdef';
      memory.capture(`k${String(index)}`, input);
    }
    expect(memory.size()).toBe(FIELD_MEMORY_LIMIT);
    expect(memory.has('k0')).toBe(false);
    expect(memory.has(`k${String(FIELD_MEMORY_LIMIT + 4)}`)).toBe(true);
  });
});
