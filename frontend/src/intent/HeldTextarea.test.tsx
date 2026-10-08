import { act, fireEvent, render } from '@testing-library/react';
import { StrictMode, useState } from 'react';
import { describe, expect, it } from 'vitest';
import { ControlsProvider } from '../controls/ControlsProvider';
import { createControls } from '../controls/kit';
import { createFakeClock } from '../transport/testing';
import { HeldTextarea } from './HeldTextarea';

/* The native editor's contract, in isolation: the node is the reader's while they type, and is replaced only
   when the page changed the words for a reason other than typing. */

function Harness({
  initial,
  strict = false,
}: {
  readonly initial: string;
  readonly strict?: boolean;
}) {
  const [held, setHeld] = useState(initial);
  const box = (
    <>
      <HeldTextarea
        memoryKey="m"
        focusKey="f"
        text={held}
        data-testid="box"
        onEdit={(raw) => {
          const kept = raw.slice(0, 10);
          setHeld(kept);
          return kept;
        }}
      />
      <button type="button" onClick={() => setHeld('set by the page')}>
        page
      </button>
      <button type="button" onClick={() => setHeld('line one\r\nline two')}>
        crlf
      </button>
      <span data-testid="held">{held}</span>
    </>
  );
  return strict ? <StrictMode>{box}</StrictMode> : box;
}

function mount(initial: string, strict = false) {
  const controls = createControls({
    clock: createFakeClock(),
    announce: () => undefined,
    memo: {} as never,
  });
  const view = render(
    <ControlsProvider controls={controls}>
      <Harness initial={initial} strict={strict} />
    </ControlsProvider>,
  );
  const box = () => view.getByTestId('box') as HTMLTextAreaElement;
  return { ...view, box, controls };
}

describe('the held native editor', () => {
  it.each([false, true])(
    'keeps its node and caret while the reader types (StrictMode %s)',
    (strict) => {
      const page = mount('start', strict);
      const node = page.box();
      node.focus();
      node.value = 'startx';
      node.setSelectionRange(2, 4);
      fireEvent.input(node);
      node.setSelectionRange(2, 4);
      expect(page.box()).toBe(node);
      expect(page.getByTestId('held').textContent).toBe('startx');
      expect([node.selectionStart, node.selectionEnd]).toEqual([2, 4]);
    },
  );

  it('puts back what it cut or scrubbed, which is the one write to the node', () => {
    const page = mount('');
    fireEvent.input(page.box(), { target: { value: 'abcdefghijklmnop' } });
    expect(page.box().value).toBe('abcdefghij');
  });

  it('is replaced, under the same memory, when the page changes the words', async () => {
    const page = mount('start');
    const node = page.box();
    await act(async () => {
      fireEvent.click(page.getByText('page'));
    });
    expect(page.box()).not.toBe(node);
    expect(page.box().value).toBe('set by the page');
  });

  it('does not replace itself forever over words the browser normalises', async () => {
    const page = mount('start');
    await act(async () => {
      fireEvent.click(page.getByText('crlf'));
    });
    expect(page.box().value).toBe('line one\nline two');
    const settled = page.box();
    await act(async () => {
      fireEvent.click(page.getByText('crlf'));
    });
    expect(page.box()).toBe(settled);
  });

  it('puts back an earlier page-set value after typing over it, which is a new change, not a repeat', async () => {
    const page = mount('start');
    await act(async () => {
      fireEvent.click(page.getByText('page'));
    });
    fireEvent.input(page.box(), { target: { value: 'typed' } });
    const typed = page.box();
    expect(typed.value).toBe('typed');
    await act(async () => {
      fireEvent.click(page.getByText('page'));
    });
    expect(page.box().value).toBe('set by the page');
  });
});
