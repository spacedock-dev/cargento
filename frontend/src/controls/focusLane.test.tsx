import { act, render } from '@testing-library/react';
import { StrictMode, useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createFocusLane, type FocusLane } from './focusLane';
import { useFocusKey } from './useFocusKey';

function Keyed({ lane, name, fallback, hidden }: { lane: FocusLane; name: string; fallback?: string; hidden?: boolean }) {
  const ref = useFocusKey<HTMLButtonElement>(lane, name, fallback === undefined ? {} : { fallback });
  return hidden ? null : (
    <button type="button" ref={ref}>
      {name}
    </button>
  );
}

const settle = () => act(() => Promise.resolve());

function rectOf(element: Element, rect: Partial<DOMRect>) {
  vi.spyOn(element, 'getBoundingClientRect').mockReturnValue({
    top: 0,
    bottom: 10,
    left: 0,
    right: 10,
    width: 10,
    height: 10,
    x: 0,
    y: 0,
    toJSON: () => ({}),
    ...rect,
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('keyboard focus follows a key, not a node', () => {
  it('leaves focus alone while its node persists through unrelated renders', () => {
    const lane = createFocusLane();
    function Board({ tick }: { tick: number }) {
      return (
        <div data-tick={tick}>
          <Keyed lane={lane} name="alpha" />
          <Keyed lane={lane} name="beta" />
        </div>
      );
    }
    const view = render(<Board tick={0} />);
    const beta = view.getByRole('button', { name: 'beta' });
    beta.focus();
    view.rerender(<Board tick={1} />);
    view.rerender(<Board tick={2} />);
    expect(document.activeElement).toBe(beta);
    expect(view.getByRole('button', { name: 'beta' })).toBe(beta);
  });

  it('hands focus to the named fallback when the focused control goes away', async () => {
    const lane = createFocusLane();
    function Board({ running }: { running: boolean }) {
      return (
        <div>
          <Keyed lane={lane} name="analyze" />
          <Keyed lane={lane} name="cancel" fallback="analyze" hidden={!running} />
        </div>
      );
    }
    const view = render(<Board running />);
    view.getByRole('button', { name: 'cancel' }).focus();
    view.rerender(<Board running={false} />);
    await settle();
    expect(document.activeElement).toBe(view.getByRole('button', { name: 'analyze' }));
  });

  it('puts focus back on a control that re-mounts under the same key in the same commit', async () => {
    const lane = createFocusLane();
    function Board({ generation }: { generation: number }) {
      return (
        <div key={generation}>
          <Keyed lane={lane} name="row" />
        </div>
      );
    }
    const view = render(<Board generation={0} />);
    const before = view.getByRole('button', { name: 'row' });
    before.focus();
    view.rerender(<Board generation={1} />);
    await settle();
    const after = view.getByRole('button', { name: 'row' });
    expect(after).not.toBe(before);
    expect(document.activeElement).toBe(after);
  });

  it('does nothing when the removed control was not the focused one', async () => {
    const lane = createFocusLane();
    const view = render(
      <>
        <Keyed lane={lane} name="a" />
        <Keyed lane={lane} name="b" fallback="a" />
      </>,
    );
    const outside = document.createElement('input');
    document.body.append(outside);
    outside.focus();
    view.unmount();
    await settle();
    expect(document.activeElement).toBe(outside);
    outside.remove();
  });

  it('does not scroll to a fallback when the removed control was wholly offscreen', async () => {
    const lane = createFocusLane();
    function Board({ shown }: { shown: boolean }) {
      return (
        <div>
          <Keyed lane={lane} name="home" />
          <Keyed lane={lane} name="far" fallback="home" hidden={!shown} />
        </div>
      );
    }
    const view = render(<Board shown />);
    const far = view.getByRole('button', { name: 'far' });
    rectOf(far, { top: 5000, bottom: 5040 });
    far.focus();
    const home = view.getByRole('button', { name: 'home' });
    const focus = vi.spyOn(home, 'focus');
    view.rerender(<Board shown={false} />);
    await settle();
    expect(focus).toHaveBeenCalledExactlyOnceWith({ preventScroll: true });
  });

  it('scrolls normally when the removed control intersected the viewport', async () => {
    const lane = createFocusLane();
    function Board({ shown }: { shown: boolean }) {
      return (
        <div>
          <Keyed lane={lane} name="home" />
          <Keyed lane={lane} name="near" fallback="home" hidden={!shown} />
        </div>
      );
    }
    const view = render(<Board shown />);
    const near = view.getByRole('button', { name: 'near' });
    rectOf(near, { top: window.innerHeight - 5, bottom: window.innerHeight + 30 });
    near.focus();
    const focus = vi.spyOn(view.getByRole('button', { name: 'home' }), 'focus');
    view.rerender(<Board shown={false} />);
    await settle();
    expect(focus).toHaveBeenCalledExactlyOnceWith({ preventScroll: false });
  });

  it('never builds a selector from a key, so a hostile key is just a key', async () => {
    const lane = createFocusLane();
    const hostile = 'x"],[data-evil="1';
    const querySelector = vi.spyOn(document, 'querySelector');
    const querySelectorAll = vi.spyOn(document, 'querySelectorAll');
    function Board({ generation }: { generation: number }) {
      return (
        <div key={generation}>
          <Keyed lane={lane} name={hostile} />
        </div>
      );
    }
    const view = render(<Board generation={0} />);
    view.getByRole('button').focus();
    view.rerender(<Board generation={1} />);
    await settle();
    expect(document.activeElement).toBe(view.getByRole('button'));
    expect(querySelector).not.toHaveBeenCalled();
    expect(querySelectorAll).not.toHaveBeenCalled();
    expect(lane.focus(hostile)).toBe(true);
  });

  it('survives StrictMode double effects with one registration per key', async () => {
    const lane = createFocusLane();
    function Board() {
      const [on, setOn] = useState(true);
      return (
        <div>
          <button type="button" onClick={() => setOn(false)}>
            toggle
          </button>
          <Keyed lane={lane} name="a" />
          <Keyed lane={lane} name="b" fallback="a" hidden={!on} />
        </div>
      );
    }
    const view = render(
      <StrictMode>
        <Board />
      </StrictMode>,
    );
    expect(lane.size()).toBe(2);
    view.getByRole('button', { name: 'b' }).focus();
    act(() => view.getByRole('button', { name: 'toggle' }).click());
    await settle();
    expect(lane.size()).toBe(1);
    expect(document.activeElement).toBe(view.getByRole('button', { name: 'a' }));
  });
});
