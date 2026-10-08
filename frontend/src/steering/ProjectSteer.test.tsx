import { act, fireEvent, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ProjectSteer } from './ProjectSteer';
import { mountPanels } from './testing';

/* The steering bar is a note to oneself. These hold what the reader keeps: the words, the caret, the receipt,
   and that nothing is ever sent. The real browser keeps the undo history and the composition, which jsdom
   cannot, and `console-parity.mjs` proves those against Chromium. */
const box = (): HTMLInputElement =>
  document.querySelector('[data-next-draft="steer"]') as HTMLInputElement;
const type = (element: HTMLInputElement, value: string) => {
  element.focus();
  fireEvent.input(element, { target: { value } });
};

describe('the steering bar says what it is before the first keystroke', () => {
  it('names itself local and says there is no write path into a session', async () => {
    const page = mountPanels(<ProjectSteer project="alpha/app" />);
    await page.settle();
    expect(screen.getByText('STEER · LOCAL ONLY')).toBeInTheDocument();
    expect(
      screen.getByText(
        /Cargento has no write path into a session\. Anything you type here is a note to yourself/,
      ),
    ).toBeInTheDocument();
    expect(box().getAttribute('maxlength')).toBe('500');
  });
});

describe('a draft', () => {
  it('survives the bar leaving and coming back, with its caret', async () => {
    const page = mountPanels(<ProjectSteer project="alpha/app" />);
    await page.settle();
    type(box(), 'tell the queue to drain');
    box().setSelectionRange(5, 9);
    page.show(<p>elsewhere</p>);
    await page.settle();
    expect(document.querySelector('[data-next-steer]')).toBeNull();
    page.show(<ProjectSteer project="alpha/app" />);
    await page.settle();
    expect(box().value).toBe('tell the queue to drain');
    expect([box().selectionStart, box().selectionEnd]).toEqual([5, 9]);
  });

  it('is one project’s own: another project’s box is another node with its own words', async () => {
    const page = mountPanels(<ProjectSteer project="alpha/app" />);
    await page.settle();
    const alpha = box();
    type(alpha, 'alpha words');
    page.show(<ProjectSteer project="beta/api" />);
    await page.settle();
    expect(box()).not.toBe(alpha);
    expect(box().value).toBe('');
    type(box(), 'beta words');
    page.show(<ProjectSteer project="alpha/app" />);
    await page.settle();
    expect(box().value).toBe('alpha words');
    page.show(<ProjectSteer project="beta/api" />);
    await page.settle();
    expect(box().value).toBe('beta words');
  });

  it('keeps one node across a board that changes: the editor is never replaced under the reader', async () => {
    const data = { generated: 1000, sessions: [] };
    const page = mountPanels(<ProjectSteer project="alpha/app" />, { data });
    await page.settle();
    const node = box();
    type(node, 'half a sentence');
    node.setSelectionRange(3, 3);
    await page.poll({ generated: 1001, sessions: [] });
    await page.poll({ generated: 1002, sessions: [] });
    expect(box()).toBe(node);
    expect(box().value).toBe('half a sentence');
    expect(box().selectionStart).toBe(3);
  });
});

describe('sending a draft', () => {
  it('records a receipt that says it was not delivered, and empties the box AND the draft', async () => {
    const page = mountPanels(<ProjectSteer project="alpha/app" />);
    await page.settle();
    type(box(), '  take the safer route  ');
    await act(async () => {
      fireEvent.submit(box().closest('form') as HTMLFormElement);
    });
    const receipt = document.querySelector('[data-next-steer-receipt]') as HTMLElement;
    expect(within(receipt).getByText('take the safer route')).toBeInTheDocument();
    expect(receipt.textContent).toContain('Draft recorded in this tab. Not delivered.');
    expect(box().value).toBe('');
    // Gone from the draft too: the bar leaving and returning must not bring the sentence back.
    page.show(<p>elsewhere</p>);
    page.show(<ProjectSteer project="alpha/app" />);
    await page.settle();
    expect(box().value).toBe('');
    // A second send of nothing records nothing.
    await act(async () => {
      fireEvent.submit(box().closest('form') as HTMLFormElement);
    });
    expect(document.querySelectorAll('[data-next-steer-receipt]')).toHaveLength(1);
  });

  it('never sends anything: no request from a mount, a poll, a press or StrictMode', async () => {
    const page = mountPanels(<ProjectSteer project="alpha/app" />, {
      data: { generated: 1, sessions: [] },
    });
    await page.settle();
    type(box(), 'note');
    await act(async () => {
      fireEvent.submit(box().closest('form') as HTMLFormElement);
    });
    await page.poll({ generated: 2, sessions: [] });
    expect(page.allPosts()).toEqual([]);
  });

  it('keeps only the newest twenty receipts, oldest first', async () => {
    const page = mountPanels(<ProjectSteer project="alpha/app" />);
    await page.settle();
    for (let n = 1; n <= 23; n += 1) {
      type(box(), `note ${String(n)}`);
      await act(async () => {
        fireEvent.submit(box().closest('form') as HTMLFormElement);
      });
    }
    const notes = [...document.querySelectorAll('[data-next-steer-receipt] strong')].map(
      (node) => node.textContent,
    );
    expect(notes).toHaveLength(20);
    expect(notes[0]).toBe('note 4');
    expect(notes[19]).toBe('note 23');
  });
});
