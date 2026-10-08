import { act, fireEvent, render } from '@testing-library/react';
import { StrictMode, useState, type ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { blockedBackend, fakeBackend } from '../../test/storage_backends';
import { memoKey, MEMO_LIMIT } from '../storage';
import { ControlsProvider } from './ControlsProvider';
import { HumanContextField } from './HumanContextField';
import { testControls, type TestControlsOptions } from './testControls';

const KEY = memoKey('alpha/app', null, 'outcome');
const FOCUS_KEY = memoKey('alpha/app', null, 'focus');

function field(kind: 'outcome' | 'focus' = 'outcome'): ReactElement {
  return kind === 'outcome' ? (
    <HumanContextField
      memoKey={KEY}
      kind="outcome"
      label="OUTCOME"
      placeholder="What result should this scope achieve?"
    />
  ) : (
    <HumanContextField
      memoKey={FOCUS_KEY}
      kind="focus"
      label="FOCUS"
      placeholder="What are you concentrating on now?"
    />
  );
}

function mount(ui: ReactElement, options: TestControlsOptions = {}) {
  const kit = testControls(options);
  const wrap = (node: ReactElement) => (
    <StrictMode>
      <ControlsProvider controls={kit.controls}>{node}</ControlsProvider>
    </StrictMode>
  );
  const view = render(wrap(ui));
  return { kit, view, rerender: (node: ReactElement) => view.rerender(wrap(node)) };
}

function type(textarea: HTMLElement, text: string) {
  act(() => {
    (textarea as HTMLTextAreaElement).value = text;
    fireEvent.input(textarea);
  });
}

const settle = () => act(() => Promise.resolve());

function edit(view: ReturnType<typeof mount>['view'], label = 'Edit OUTCOME') {
  fireEvent.click(view.getByRole('button', { name: label }));
  return view.getByRole('textbox') as HTMLTextAreaElement;
}

describe('human context: a note kept in this browser, saved on every input', () => {
  it('reads Not set, names its Edit control, and writes nothing on mount or StrictMode double effects', () => {
    const { view, kit } = mount(field());
    expect(view.getByText('Not set')).toBeVisible();
    expect(view.getByRole('button', { name: 'Edit OUTCOME' })).toBeVisible();
    expect(kit.backend.writes).toEqual([]);
    expect(kit.announced).toEqual([]);
  });

  it('shows what storage already holds, bounded to 500 UTF-16 units', () => {
    const backend = fakeBackend({ [KEY]: 'y'.repeat(700) });
    const { view } = mount(field(), { backend });
    expect(view.getByText('y'.repeat(MEMO_LIMIT))).toBeVisible();
  });

  it('opens an editor that takes focus, carries a 500-unit limit and says it autosaves', () => {
    const { view } = mount(field());
    const textarea = edit(view);
    expect(document.activeElement).toBe(textarea);
    expect(textarea.maxLength).toBe(500);
    expect(textarea.getAttribute('placeholder')).toBe('What result should this scope achieve?');
    expect(view.getByText('Autosaves in this browser')).toBeVisible();
    expect(view.getByRole('button', { name: 'Done' })).toBeVisible();
    expect(textarea.labels?.[0]?.textContent).toContain('OUTCOME');
  });

  it('saves each input to the exact released key, memory first, and says so', () => {
    const { view, kit } = mount(field());
    const textarea = edit(view);
    type(textarea, 'Ship the importer');
    expect(kit.backend.data.get(KEY)).toBe('Ship the importer');
    expect(kit.backend.writes).toEqual([KEY]);
    expect(view.getByText('Saved in this browser')).toBeVisible();
  });

  it('cuts text past 500 units at the edit, in the box and in storage', () => {
    const { view, kit } = mount(field());
    const textarea = edit(view);
    type(textarea, 'z'.repeat(650));
    expect(textarea.value).toHaveLength(500);
    expect(kit.backend.data.get(KEY)).toHaveLength(500);
  });

  it('keeps the words in memory and says storage is unavailable when the browser refuses the write', () => {
    const { view, kit } = mount(field(), { backend: blockedBackend() });
    const textarea = edit(view);
    type(textarea, 'only in memory');
    expect(view.getByText('Browser storage unavailable')).toBeVisible();
    expect(kit.controls.memo.read(KEY)).toBe('only in memory');
    fireEvent.click(view.getByRole('button', { name: 'Done' }));
    expect(view.getByText('only in memory')).toBeVisible();
  });

  it('closes on Done keeping what was typed, and returns focus to Edit rather than the page', async () => {
    const { view } = mount(field());
    const textarea = edit(view);
    type(textarea, 'kept');
    fireEvent.click(view.getByRole('button', { name: 'Done' }));
    await settle();
    expect(view.queryByRole('textbox')).toBeNull();
    expect(view.getByText('kept')).toBeVisible();
    expect(document.activeElement).toBe(view.getByRole('button', { name: 'Edit OUTCOME' }));
  });

  it('restores the words held when editing began on Escape, in the field or on Done, without an announcement', async () => {
    const backend = fakeBackend({ [KEY]: 'original' });
    const { view, kit } = mount(field(), { backend });
    const textarea = edit(view);
    type(textarea, 'half typed');
    expect(backend.data.get(KEY)).toBe('half typed');
    const escape = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true });
    act(() => {
      textarea.dispatchEvent(escape);
    });
    await settle();
    expect(escape.defaultPrevented).toBe(true);
    expect(backend.data.get(KEY)).toBe('original');
    expect(view.queryByRole('textbox')).toBeNull();
    expect(view.getByText('original')).toBeVisible();
    expect(kit.announced).toEqual([]);

    edit(view);
    type(view.getByRole('textbox'), 'again');
    const done = view.getByRole('button', { name: 'Done' });
    const fromDone = new KeyboardEvent('keydown', {
      key: 'Escape',
      bubbles: true,
      cancelable: true,
    });
    act(() => {
      done.dispatchEvent(fromDone);
    });
    expect(backend.data.get(KEY)).toBe('original');
    expect(view.queryByRole('textbox')).toBeNull();
  });

  it("keeps Escape inside the editor from reaching the page's own Escape handler", () => {
    const { view } = mount(field());
    const textarea = edit(view);
    const seen = vi.fn();
    document.addEventListener('keydown', seen);
    act(() => {
      textarea.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }),
      );
    });
    document.removeEventListener('keydown', seen);
    expect(seen).not.toHaveBeenCalled();
  });

  it('survives unrelated updates with the same node, focus, caret and typed text', () => {
    function Page() {
      const [tick, setTick] = useState(0);
      return (
        <div data-tick={tick}>
          <button type="button" onClick={() => setTick(tick + 1)}>
            tick
          </button>
          {field()}
        </div>
      );
    }
    const { view } = mount(<Page />);
    const textarea = edit(view);
    type(textarea, 'hello brave world');
    textarea.setSelectionRange(6, 11);
    act(() => view.getByRole('button', { name: 'tick' }).click());
    act(() => view.getByRole('button', { name: 'tick' }).click());
    expect(view.getByRole('textbox')).toBe(textarea);
    expect(document.activeElement).toBe(textarea);
    expect([textarea.selectionStart, textarea.selectionEnd]).toEqual([6, 11]);
    expect(textarea.value).toBe('hello brave world');
  });

  it('remounts still editing with the typed words from memory, not the older stored ones', () => {
    const backend = fakeBackend({ [KEY]: 'stored' });
    const { view, rerender, kit } = mount(field(), { backend });
    const textarea = edit(view);
    type(textarea, 'typed since');
    rerender(<p>another view</p>);
    expect(view.queryByRole('textbox')).toBeNull();
    // A storage write that lands elsewhere cannot override what this tab typed.
    backend.data.set(KEY, 'someone else');
    rerender(field());
    expect((view.getByRole('textbox') as HTMLTextAreaElement).value).toBe('typed since');
    expect(kit.controls.memoEditing.get()?.key).toBe(KEY);
  });

  it("edits one field at a time and keeps the other's words apart", () => {
    const { view, kit } = mount(
      <>
        {field('outcome')}
        {field('focus')}
      </>,
    );
    fireEvent.click(view.getByRole('button', { name: 'Edit OUTCOME' }));
    type(view.getByRole('textbox'), 'the outcome');
    fireEvent.click(view.getByRole('button', { name: 'Edit FOCUS' }));
    expect(view.getAllByRole('textbox')).toHaveLength(1);
    type(view.getByRole('textbox'), 'the focus');
    expect(kit.backend.data.get(KEY)).toBe('the outcome');
    expect(kit.backend.data.get(FOCUS_KEY)).toBe('the focus');
  });

  it('opens from outside the field, as the More menu does, and focuses it once', () => {
    const { view, kit } = mount(field());
    act(() => kit.controls.startMemoEdit(KEY));
    expect(document.activeElement).toBe(view.getByRole('textbox'));
    expect(kit.controls.memoEditing.get()?.fresh).toBe(false);
  });
});
