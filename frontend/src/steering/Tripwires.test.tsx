import { act, fireEvent, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Tripwires } from './Tripwires';
import { mountPanels } from './testing';

/* The tripwires are browser preferences. They keep the released storage format and read the older one, the add
   box stays open for the tab, Escape cancels its draft without leaving the page, and none of it is ever sent. */
const KEY = (project: string) => `cargento.next.guardrails.${encodeURIComponent(project)}`;
const input = (): HTMLInputElement =>
  document.querySelector('[data-next-guardrail-input]') as HTMLInputElement;
const add = () => screen.getByText('+ set a tripwire');
const rows = () => [...document.querySelectorAll('[data-next-guardrail-toggle]')];
const press = async (element: Element) => {
  await act(async () => {
    fireEvent.click(element);
  });
};
const type = (element: HTMLInputElement, value: string) => {
  element.focus();
  fireEvent.input(element, { target: { value } });
};

describe('the panel says nothing enforces these', () => {
  it('names itself local and says it is a note to yourself', async () => {
    const page = mountPanels(<Tripwires project="alpha/app" />);
    await page.settle();
    expect(screen.getByText('local only · nothing enforces these')).toBeInTheDocument();
    expect(
      screen.getByText(/Until it ships they are a note to yourself, held in this browser\./),
    ).toBeInTheDocument();
    expect(screen.getByText('No tripwires saved in this browser.')).toBeInTheDocument();
  });
});

describe('the rules', () => {
  it('read what an older build stored, and write the released shape', async () => {
    const page = mountPanels(<Tripwires project="alpha/app" />, {
      storage: {
        [KEY('alpha/app')]: JSON.stringify([
          'an old string rule',
          { text: ' kept ', enabled: false },
          5,
          { text: '   ' },
        ]),
      },
    });
    await page.settle();
    expect(rows().map((row) => row.textContent)).toEqual([
      '◇an old string rule',
      '◇keptDisabled in this browser.',
    ]);
    expect(rows().map((row) => row.getAttribute('aria-checked'))).toEqual(['true', 'false']);
    await press(rows()[0] as Element);
    expect(JSON.parse(page.backend.data.get(KEY('alpha/app')) ?? '[]')).toEqual([
      { enabled: false, text: 'an old string rule' },
      { enabled: false, text: 'kept' },
    ]);
  });

  it('are one project’s own, keyed by the exact label', async () => {
    const page = mountPanels(<Tripwires project="alpha/app" />);
    await page.settle();
    await press(add());
    type(input(), 'alert me when the build breaks');
    fireEvent.keyDown(input(), { key: 'Enter' });
    expect(rows()).toHaveLength(1);
    page.show(<Tripwires project="beta/api" />);
    await page.settle();
    expect(rows()).toHaveLength(0);
    expect(page.backend.data.has(KEY('alpha/app'))).toBe(true);
    expect(page.backend.data.has(KEY('beta/api'))).toBe(false);
  });

  it('keep the newest fifty and cut each to five hundred characters', async () => {
    const page = mountPanels(<Tripwires project="p" />);
    await page.settle();
    for (let n = 1; n <= 52; n += 1) {
      await press(add());
      type(input(), n === 52 ? 'x'.repeat(600) : `rule ${String(n)}`);
      fireEvent.keyDown(input(), { key: 'Enter' });
    }
    expect(rows()).toHaveLength(50);
    expect((rows()[0] as HTMLElement).textContent).toContain('rule 3');
    expect((rows()[49] as HTMLElement).querySelector('strong')?.textContent).toHaveLength(500);
  });
});

describe('the add box', () => {
  it('stays open for the tab, with its words, when the panel leaves and returns', async () => {
    const page = mountPanels(<Tripwires project="alpha/app" />);
    await page.settle();
    await press(add());
    type(input(), 'half a rule');
    input().setSelectionRange(2, 4);
    page.show(<p>elsewhere</p>);
    page.show(<Tripwires project="alpha/app" />);
    await page.settle();
    expect(input().value).toBe('half a rule');
    expect([input().selectionStart, input().selectionEnd]).toEqual([2, 4]);
  });

  it('Escape cancels the draft and closes the box, and the page does not leave', async () => {
    const page = mountPanels(<Tripwires project="alpha/app" />);
    await page.settle();
    const before = page.history.entries();
    await press(add());
    type(input(), 'never mind');
    const event = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true });
    let reachedWindow = false;
    const watch = () => {
      reachedWindow = true;
    };
    window.addEventListener('keydown', watch);
    await act(async () => {
      input().dispatchEvent(event);
    });
    window.removeEventListener('keydown', watch);
    expect(reachedWindow).toBe(false);
    expect(event.defaultPrevented).toBe(true);
    expect(document.querySelector('[data-next-guardrail-form]')).toBeNull();
    expect(page.history.entries()).toEqual(before);
    // Reopened, it is empty: an abandoned draft is not offered back.
    await press(add());
    expect(input().value).toBe('');
    expect(rows()).toHaveLength(0);
  });

  it('Enter adds once and the committed rule is not offered back', async () => {
    const page = mountPanels(<Tripwires project="alpha/app" />);
    await page.settle();
    await press(add());
    type(input(), 'notify me of a force push');
    fireEvent.keyDown(input(), { key: 'Enter' });
    expect(rows()).toHaveLength(1);
    await press(add());
    expect(input().value).toBe('');
    fireEvent.keyDown(input(), { key: 'Enter' });
    expect(rows()).toHaveLength(1);
    expect(page.backend.writes.filter((key) => key === KEY('alpha/app'))).toHaveLength(1);
  });

  it('closes on an empty submit without adding anything', async () => {
    const page = mountPanels(<Tripwires project="alpha/app" />);
    await page.settle();
    await press(add());
    await act(async () => {
      fireEvent.submit(document.querySelector('[data-next-guardrail-form]') as HTMLFormElement);
    });
    expect(document.querySelector('[data-next-guardrail-form]')).toBeNull();
    expect(rows()).toHaveLength(0);
  });

  it('ignores an Enter that commits an input-method composition', async () => {
    const page = mountPanels(<Tripwires project="alpha/app" />);
    await page.settle();
    await press(add());
    type(input(), 'にほん');
    fireEvent.keyDown(input(), { key: 'Enter', isComposing: true });
    expect(rows()).toHaveLength(0);
    expect(document.querySelector('[data-next-guardrail-form]')).not.toBeNull();
  });
});

describe('nothing is sent', () => {
  it('no request leaves from a mount, a press, a toggle or a poll', async () => {
    const page = mountPanels(<Tripwires project="alpha/app" />, {
      data: { generated: 1, sessions: [] },
    });
    await page.settle();
    await press(add());
    type(input(), 'a rule');
    fireEvent.keyDown(input(), { key: 'Enter' });
    await press(rows()[0] as Element);
    await page.poll({ generated: 2, sessions: [] });
    expect(page.allPosts()).toEqual([]);
  });
});
