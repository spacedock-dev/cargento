import { act, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { BoardSnapshot } from '../store/board';
import { ShellContext, type Shell } from '../shell/context';
import { ActionButton } from './ActionButton';

/* The control a request in flight draws busy. The previous page's test asked for "disabled, spinner, reading
   Saving…"; `frontend/e2e/intent-parity.mjs` reaches the attribute and the layout, and a browser proof that
   only reads `aria-busy` passes with the spinner and the label gone, so each part is asked for here. */

function fakeShell() {
  let pending: readonly string[] = [];
  const listeners = new Set<() => void>();
  const snapshot = () => ({ pending }) as unknown as BoardSnapshot;
  let current = snapshot();
  const shell = {
    controls: { focusLane: null },
    display: {
      subscribe: (listener: () => void) => {
        listeners.add(listener);
        return () => listeners.delete(listener);
      },
      getSnapshot: () => current,
    },
  } as unknown as Shell;
  return {
    shell,
    setPending(next: readonly string[]) {
      pending = next;
      current = snapshot();
      act(() => {
        for (const listener of listeners) listener();
      });
    },
  };
}

function mount(props: Partial<Parameters<typeof ActionButton>[0]> = {}) {
  const world = fakeShell();
  const onPress = vi.fn();
  render(
    <ShellContext.Provider value={world.shell}>
      <ActionButton
        pendingKey="save"
        label="Save intent"
        busyLabel="Saving…"
        onPress={onPress}
        {...props}
      />
    </ShellContext.Provider>,
  );
  return { ...world, onPress, button: () => screen.getByRole('button') };
}

describe('a control whose request is in flight', () => {
  it('draws idle until its key is pending: labelled, enabled, not busy', () => {
    const { button } = mount();
    expect(button().textContent).toBe('Save intent');
    expect(button().hasAttribute('aria-busy')).toBe(false);
    expect(button().hasAttribute('aria-disabled')).toBe(false);
    expect(button().querySelector('.next-spinner')).toBeNull();
  });

  it('is inert, busy, spinning and reading its busy label', () => {
    const { button, setPending } = mount();
    setPending(['save']);
    expect(button().getAttribute('aria-disabled')).toBe('true');
    expect(button().getAttribute('aria-busy')).toBe('true');
    expect(button().hasAttribute('data-next-pending')).toBe(true);
    // `aria-disabled` and never `disabled`: the control just pressed keeps keyboard focus.
    expect((button() as HTMLButtonElement).disabled).toBe(false);
    const busy = button().querySelector('.next-action-busy');
    expect(busy).not.toBeNull();
    expect(busy?.querySelector('.next-spinner')).not.toBeNull();
    expect(busy?.querySelector('.next-spinner')?.getAttribute('aria-hidden')).toBe('true');
    expect(busy?.textContent).toBe('Saving…');
  });

  it('holds the idle label as an invisible ghost, so the control keeps its width', () => {
    const { button, setPending } = mount();
    setPending(['save']);
    const ghost = button().querySelector('.next-action-ghost');
    expect(ghost?.getAttribute('aria-hidden')).toBe('true');
    expect(ghost?.textContent).toBe('Save intent');
  });

  it('returns to its idle label and drops every busy mark when the request ends', () => {
    const { button, setPending } = mount();
    setPending(['save']);
    setPending([]);
    expect(button().textContent).toBe('Save intent');
    for (const name of ['aria-busy', 'aria-disabled', 'data-next-pending'])
      expect(button().hasAttribute(name)).toBe(false);
    expect(button().querySelector('.next-spinner')).toBeNull();
  });

  it('is busy only for its own key', () => {
    const { button, setPending } = mount();
    setPending(['discard']);
    expect(button().hasAttribute('aria-busy')).toBe(false);
    expect(button().textContent).toBe('Save intent');
  });

  it('reserves the busy label at rest when asked to, and swaps it for the spinner when busy', () => {
    const { button, setPending } = mount({ reserve: 'Saving the intent…' });
    expect(button().querySelector('.next-action-reserve .next-action-ghost')?.textContent).toBe(
      'Saving the intent…',
    );
    setPending(['save']);
    expect(button().querySelector('.next-action-reserve')).toBeNull();
    expect(button().querySelector('.next-action-busy')?.textContent).toBe('Saving…');
  });
});

describe('an inert control that is not busy', () => {
  it('says it is inert without claiming a request, and is described by the sentence saying why', () => {
    const { button } = mount({ inert: true, describedBy: 'why-inert' });
    expect(button().getAttribute('aria-disabled')).toBe('true');
    expect(button().hasAttribute('aria-busy')).toBe(false);
    expect(button().getAttribute('aria-describedby')).toBe('why-inert');
    expect(button().querySelector('.next-spinner')).toBeNull();
  });
});
