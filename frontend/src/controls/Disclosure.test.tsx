import { act, fireEvent, render } from '@testing-library/react';
import { StrictMode, useState, type ReactElement } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ControlsProvider } from './ControlsProvider';
import { Disclosure } from './Disclosure';
import { disclosureKey } from './disclosureStore';
import { createDisclosureBinding } from './useDisclosureState';
import { testControls, type TestControlsOptions } from './testControls';

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

const key = (name: string, project: string | null = 'alpha', scope: string | null = 'claude:s1') =>
  disclosureKey({ project, scope, name });

function isOpen(node: HTMLElement | null) {
  return node instanceof HTMLDetailsElement
    ? node.open
    : (node?.hasAttribute('data-open') ?? false);
}

function toggle(details: HTMLElement, open: boolean) {
  if (!(details instanceof HTMLDetailsElement)) {
    if (isOpen(details) !== open)
      fireEvent.click(details.querySelector('[data-slot=accordion-trigger]') as HTMLElement);
    return;
  }
  // jsdom queues its own `toggle` event; the component listens for exactly that one.
  act(() => {
    details.open = open;
  });
}

const flushToggle = () => act(() => new Promise<void>((resolve) => setTimeout(resolve, 0)));

describe('a disclosure keeps its open state by key, not by node', () => {
  beforeEach(() => {
    // After the click's own activation behaviour has opened the node, as a real frame is.
    vi.stubGlobal('requestAnimationFrame', (run: () => void) => setTimeout(run, 0));
    Element.prototype.scrollIntoView = vi.fn();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('follows a store write made outside React, without remounting', async () => {
    const { view, kit, rerender } = mount(
      <Disclosure disclosureKey={key('plan')} summary="Project plan">
        Body
      </Disclosure>,
    );
    const details = view
      .getByText('Project plan')
      .closest('[data-slot=accordion],details') as HTMLDetailsElement;
    act(() => kit.controls.disclosures.set(key('plan'), true));
    expect(isOpen(details)).toBe(true);
    await flushToggle();
    act(() => kit.controls.disclosures.set(key('plan'), false));
    rerender(
      <Disclosure disclosureKey={key('plan')} summary="Project plan">
        Poll
      </Disclosure>,
    );
    await flushToggle();
    expect(isOpen(details)).toBe(false);
    expect(view.getByText('Project plan').closest('[data-slot=accordion],details')).toBe(details);
  });

  it('records a summary opening before a poll and its queued toggle', async () => {
    const { view, kit, rerender } = mount(
      <Disclosure disclosureKey={key('plan')} summary="Project plan">
        Body
      </Disclosure>,
    );
    fireEvent.click(view.getByText('Project plan'));
    expect(kit.controls.disclosures.isOpen(key('plan'))).toBe(true);
    rerender(
      <Disclosure disclosureKey={key('plan')} summary="Project plan">
        Poll
      </Disclosure>,
    );
    await flushToggle();
    expect(
      isOpen(
        view
          .getByText('Project plan')
          .closest('[data-slot=accordion],details') as HTMLDetailsElement,
      ),
    ).toBe(true);
  });

  it('ignores a queued native opening superseded by newer external writes', async () => {
    const { view, kit } = mount(
      <Disclosure disclosureKey={key('plan')} summary="Project plan" variant="popover">
        Body
      </Disclosure>,
    );
    const details = view
      .getByText('Project plan')
      .closest('[data-slot=accordion],details') as HTMLDetailsElement;
    toggle(details, true);
    act(() => kit.controls.disclosures.set(key('plan'), true));
    act(() => kit.controls.disclosures.set(key('plan'), false));
    const stale = new Event('toggle');
    Object.defineProperty(stale, 'newState', { value: 'open' });
    fireEvent(details, stale);
    expect(kit.controls.disclosures.isOpen(key('plan'))).toBe(false);
    await flushToggle();
    expect(isOpen(details)).toBe(false);
  });

  it('accepts a native opening after a write that landed before the subscription', () => {
    const { controls } = testControls();
    const store = controls.disclosures;
    const binding = createDisclosureBinding(store, key('plan'));
    const details = document.createElement('details');
    const detach = binding.attach(details);
    // The parent's layout effect closes the section before the passive subscribe runs.
    store.set(key('plan'), false);
    const release = binding.subscribe(vi.fn());
    details.open = true;
    const opening = new Event('toggle');
    Object.defineProperty(opening, 'newState', { value: 'open' });
    binding.toggle(opening);
    expect(store.isOpen(key('plan'))).toBe(true);
    release();
    detach();
  });

  it('lets an external close supersede a native opening while the store is still closed', async () => {
    const { view, kit } = mount(
      <Disclosure disclosureKey={key('plan')} summary="Project plan" variant="popover">
        Body
      </Disclosure>,
    );
    const details = view
      .getByText('Project plan')
      .closest('[data-slot=accordion],details') as HTMLDetailsElement;
    toggle(details, true);
    act(() => kit.controls.disclosures.set(key('plan'), false));
    const stale = new Event('toggle');
    Object.defineProperty(stale, 'newState', { value: 'open' });
    fireEvent(details, stale);
    await flushToggle();
    expect(isOpen(details)).toBe(false);
    expect(kit.controls.disclosures.isOpen(key('plan'))).toBe(false);
  });

  it('closes a native opening on a summary press before its queued toggle', async () => {
    const { view, kit } = mount(
      <Disclosure disclosureKey={key('plan')} summary="Project plan" variant="popover">
        Body
      </Disclosure>,
    );
    const details = view
      .getByText('Project plan')
      .closest('[data-slot=accordion],details') as HTMLDetailsElement;
    toggle(details, true);
    fireEvent.click(view.getByText('Project plan'));
    await flushToggle();
    expect(isOpen(details)).toBe(false);
    expect(kit.controls.disclosures.isOpen(key('plan'))).toBe(false);
  });

  it('never echoes a toggle caused by rendering a store write', async () => {
    const { view, kit } = mount(
      <Disclosure disclosureKey={key('plan')} summary="Project plan">
        Body
      </Disclosure>,
    );
    const set = vi.spyOn(kit.controls.disclosures, 'set');
    act(() => kit.controls.disclosures.set(key('plan'), true));
    await flushToggle();
    expect(
      isOpen(
        view
          .getByText('Project plan')
          .closest('[data-slot=accordion],details') as HTMLDetailsElement,
      ),
    ).toBe(true);
    expect(set).toHaveBeenCalledTimes(1);
  });

  it('keeps the latest rapid press and lets siblings open together', async () => {
    const { view, kit } = mount(
      <>
        <Disclosure disclosureKey={key('a')} summary="A">
          A body
        </Disclosure>
        <Disclosure disclosureKey={key('b')} summary="B">
          B body
        </Disclosure>
      </>,
    );
    for (let i = 0; i < 3; i += 1) fireEvent.click(view.getByText('A'));
    fireEvent.click(view.getByText('B'));
    expect(kit.controls.disclosures.isOpen(key('a'))).toBe(true);
    expect(kit.controls.disclosures.isOpen(key('b'))).toBe(true);
    await flushToggle();
    expect(
      isOpen(view.getByText('A').closest('[data-slot=accordion],details') as HTMLDetailsElement),
    ).toBe(true);
    expect(
      isOpen(view.getByText('B').closest('[data-slot=accordion],details') as HTMLDetailsElement),
    ).toBe(true);
  });

  it('accepts a native browser opening even when a redraw precedes the queued event', async () => {
    const { view, kit, rerender } = mount(
      <Disclosure disclosureKey={key('plan')} summary="Project plan" variant="popover">
        Body
      </Disclosure>,
    );
    const details = view
      .getByText('Project plan')
      .closest('[data-slot=accordion],details') as HTMLDetailsElement;
    toggle(details, true);
    rerender(
      <Disclosure disclosureKey={key('plan')} summary="Project plan" variant="popover">
        Poll
      </Disclosure>,
    );
    await flushToggle();
    expect(isOpen(details)).toBe(true);
    expect(kit.controls.disclosures.isOpen(key('plan'))).toBe(true);
  });

  it('publishes a browser beforematch opening through the controlled store and retains it across a redraw', () => {
    const { view, kit, rerender } = mount(
      <Disclosure disclosureKey={key('find')} summary="Find">
        <p>Target</p>
      </Disclosure>,
    );
    const panel = view.getByText('Target').closest('[data-slot=accordion-content]') as HTMLElement;
    fireEvent(panel, new Event('beforematch'));
    expect(kit.controls.disclosures.isOpen(key('find'))).toBe(true);
    rerender(
      <Disclosure disclosureKey={key('find')} summary="Find">
        <p>Target</p>
      </Disclosure>,
    );
    expect(view.getByRole('button', { name: 'Find' }).getAttribute('aria-expanded')).toBe('true');
  });

  it('publishes only changed snapshots and releases subscriptions on unmount', async () => {
    const { view, kit } = mount(
      <Disclosure disclosureKey={key('plan')} summary="Project plan">
        Body
      </Disclosure>,
    );
    const store = kit.controls.disclosures;
    const snapshots: boolean[] = [];
    const release = store.subscribe(() => snapshots.push(store.isOpen(key('plan'))));
    const closed = store.read(key('plan'));
    act(() => store.set(key('plan'), false));
    expect(store.read(key('plan'))).toBe(closed);
    act(() => store.set(key('plan'), true));
    const opened = store.read(key('plan'));
    act(() => store.set(key('plan'), true));
    expect(store.read(key('plan'))).toBe(opened);
    expect(store.size()).toBe(1);
    act(() => store.set(key('plan'), false));
    expect(store.read(key('plan')).version).toBeGreaterThan(opened.version);
    expect(store.size()).toBe(0);
    expect(snapshots).toEqual([true, false]);
    release();
    view.unmount();
    store.set(key('plan'), true);
    await flushToggle();
    expect(snapshots).toEqual([true, false]);
  });

  it('draws a named controlled button and keeps closed content available to browser find', () => {
    const { view } = mount(
      <Disclosure disclosureKey={key('plan')} summary="Project plan">
        <p>Body</p>
      </Disclosure>,
    );
    const details = view
      .getByText('Project plan')
      .closest<HTMLElement>('[data-slot=accordion],details');
    expect(details).not.toBeNull();
    expect(
      view.getByText('Body').closest('[data-slot=accordion-content]')?.getAttribute('hidden'),
    ).toBe('until-found');
    expect(isOpen(details)).toBe(false);
    expect(view.getByRole('button', { name: 'Project plan' }).getAttribute('aria-expanded')).toBe(
      'false',
    );
  });

  it('comes back open in the markup after a remount, so no opening motion replays', async () => {
    const { view, rerender, kit } = mount(
      <Disclosure disclosureKey={key('plan')} summary="Project plan">
        <p>Body</p>
      </Disclosure>,
    );
    const first = view
      .getByText('Project plan')
      .closest('[data-slot=accordion],details') as HTMLDetailsElement;
    toggle(first, true);
    await flushToggle();
    expect(kit.controls.disclosures.isOpen(key('plan'))).toBe(true);

    rerender(<p>elsewhere</p>);
    expect(view.queryByText('Project plan')).toBeNull();

    const records: MutationRecord[] = [];
    const observer = new MutationObserver((batch) => records.push(...batch));
    observer.observe(document.body, { attributes: true, subtree: true, attributeFilter: ['open'] });
    rerender(
      <Disclosure disclosureKey={key('plan')} summary="Project plan">
        <p>Body</p>
      </Disclosure>,
    );
    await flushToggle();
    observer.disconnect();
    const second = view
      .getByText('Project plan')
      .closest('[data-slot=accordion],details') as HTMLDetailsElement;
    expect(second).not.toBe(first);
    expect(isOpen(second)).toBe(true);
    expect(records).toEqual([]);
  });

  it('is left alone, same node and same state, by an unrelated update', async () => {
    function Page() {
      const [tick, setTick] = useState(0);
      return (
        <div data-tick={tick}>
          <button type="button" onClick={() => setTick(tick + 1)}>
            tick
          </button>
          <Disclosure disclosureKey={key('plan')} summary="Project plan">
            <p>{`Body ${String(tick)}`}</p>
          </Disclosure>
        </div>
      );
    }
    const { view } = mount(<Page />);
    const details = view
      .getByText('Project plan')
      .closest('[data-slot=accordion],details') as HTMLDetailsElement;
    toggle(details, true);
    await flushToggle();
    const records: MutationRecord[] = [];
    const observer = new MutationObserver((batch) => records.push(...batch));
    observer.observe(details, { attributes: true });
    act(() => view.getByRole('button', { name: 'tick' }).click());
    act(() => view.getByRole('button', { name: 'tick' }).click());
    await flushToggle();
    observer.disconnect();
    expect(view.getByText('Project plan').closest('[data-slot=accordion],details')).toBe(details);
    expect(isOpen(details)).toBe(true);
    expect(records).toEqual([]);
    expect(view.getByText('Body 2')).toBeVisible();
  });

  it('keeps one disclosure per key independent of the others', async () => {
    const { view } = mount(
      <>
        <Disclosure disclosureKey={key('plan', 'alpha', 'claude:s1')} summary="Plan A1">
          <p>a1</p>
        </Disclosure>
        <Disclosure disclosureKey={key('plan', 'alpha', 'claude:s2')} summary="Plan A2">
          <p>a2</p>
        </Disclosure>
        <Disclosure disclosureKey={key('plan', 'beta', 'claude:s1')} summary="Plan B1">
          <p>b1</p>
        </Disclosure>
      </>,
    );
    toggle(
      view.getByText('Plan A1').closest('[data-slot=accordion],details') as HTMLDetailsElement,
      true,
    );
    await flushToggle();
    expect(
      isOpen(
        view.getByText('Plan A2').closest('[data-slot=accordion],details') as HTMLDetailsElement,
      ),
    ).toBe(false);
    expect(
      isOpen(
        view.getByText('Plan B1').closest('[data-slot=accordion],details') as HTMLDetailsElement,
      ),
    ).toBe(false);
  });

  it('records a reader toggle for the motion hold, and nothing else does', () => {
    const noteToggle = vi.fn();
    const { view, rerender } = mount(
      <Disclosure disclosureKey={key('plan')} summary="Project plan">
        <p>Body</p>
      </Disclosure>,
      { noteToggle },
    );
    expect(noteToggle).not.toHaveBeenCalled();
    rerender(
      <Disclosure disclosureKey={key('plan')} summary="Project plan">
        <p>Changed body</p>
      </Disclosure>,
    );
    expect(noteToggle).not.toHaveBeenCalled();
    fireEvent.click(view.getByText('Project plan'));
    expect(noteToggle).toHaveBeenCalledOnce();
  });

  it('forgets an open state when the reader closes it', async () => {
    const { view, kit } = mount(
      <Disclosure disclosureKey={key('plan')} summary="Project plan">
        <p>Body</p>
      </Disclosure>,
    );
    const details = view
      .getByText('Project plan')
      .closest('[data-slot=accordion],details') as HTMLDetailsElement;
    toggle(details, true);
    await flushToggle();
    toggle(details, false);
    await flushToggle();
    expect(kit.controls.disclosures.isOpen(key('plan'))).toBe(false);
  });
});

describe('a popover closes on Escape, outside, and focus departure, and nothing else does', () => {
  beforeEach(() => {
    // After the click's own activation behaviour has opened the node, as a real frame is.
    vi.stubGlobal('requestAnimationFrame', (run: () => void) => setTimeout(run, 0));
    Element.prototype.scrollIntoView = vi.fn();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function page() {
    return (
      <>
        <Disclosure disclosureKey={key('why')} summary="Why" variant="popover">
          <p>Because</p>
        </Disclosure>
        <Disclosure disclosureKey={key('plan')} summary="Plan">
          <p>Plan body</p>
        </Disclosure>
        <button type="button">Elsewhere</button>
      </>
    );
  }

  async function openBoth(view: ReturnType<typeof mount>['view']) {
    const why = view
      .getByText('Why')
      .closest('[data-slot=accordion],details') as HTMLDetailsElement;
    const plan = view
      .getByText('Plan')
      .closest('[data-slot=accordion],details') as HTMLDetailsElement;
    toggle(plan, true);
    toggle(why, true);
    await flushToggle();
    return { why, plan };
  }

  it('closes the popover on Escape, returns focus to its summary, and leaves the accordion open', async () => {
    const { view } = mount(page());
    const { why, plan } = await openBoth(view);
    view.getByText('Elsewhere').focus();
    const event = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true });
    act(() => {
      view.getByText('Elsewhere').dispatchEvent(event);
    });
    expect(isOpen(why)).toBe(false);
    expect(isOpen(plan)).toBe(true);
    expect(event.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(view.getByText('Why'));
  });

  it('publishes dismissal before a poll or a queued toggle can reopen the popover', async () => {
    const { view, kit, rerender } = mount(page());
    const { why } = await openBoth(view);
    fireEvent.keyDown(view.getByText('Elsewhere'), { key: 'Escape' });
    expect(kit.controls.disclosures.isOpen(key('why'))).toBe(false);
    rerender(page());
    await flushToggle();
    expect(isOpen(why)).toBe(false);
  });

  it('dismisses a native opening before its queued toggle reaches the store', async () => {
    const { view, kit, rerender } = mount(page());
    const why = view
      .getByText('Why')
      .closest('[data-slot=accordion],details') as HTMLDetailsElement;
    toggle(why, true);
    fireEvent.keyDown(view.getByText('Elsewhere'), { key: 'Escape' });
    expect(isOpen(why)).toBe(false);
    rerender(page());
    await flushToggle();
    expect(kit.controls.disclosures.isOpen(key('why'))).toBe(false);
    expect(isOpen(why)).toBe(false);
  });

  it('does not swallow Escape when no popover is open', () => {
    const { view } = mount(page());
    const event = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true });
    act(() => {
      view.getByText('Elsewhere').dispatchEvent(event);
    });
    expect(event.defaultPrevented).toBe(false);
  });

  it('closes on a click outside, but not on a click inside', async () => {
    const { view } = mount(page());
    const { why, plan } = await openBoth(view);
    fireEvent.click(view.getByText('Because'));
    expect(isOpen(why)).toBe(true);
    fireEvent.click(view.getByText('Elsewhere'));
    expect(isOpen(why)).toBe(false);
    expect(isOpen(plan)).toBe(true);
  });

  it('closes when focus moves to another control, and stays open when focus goes nowhere', async () => {
    const { view } = mount(page());
    const { why } = await openBoth(view);
    const summary = view.getByText('Why');
    summary.focus();
    fireEvent.focusOut(summary, { relatedTarget: null });
    expect(isOpen(why)).toBe(true);
    fireEvent.focusOut(summary, { relatedTarget: view.getByText('Elsewhere') });
    expect(isOpen(why)).toBe(false);
  });

  it('scrolls an opened popover into view once, on the reader press, and not on a redraw', async () => {
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    const { view, rerender } = mount(page());
    fireEvent.click(view.getByText('Why'));
    await flushToggle();
    await flushToggle();
    await flushToggle();
    expect(scroll).toHaveBeenCalledOnce();
    rerender(page());
    rerender(page());
    expect(scroll).toHaveBeenCalledOnce();
  });

  it('adds and removes its document handlers in balance, StrictMode double effects included', () => {
    const add = vi.spyOn(document, 'addEventListener');
    const remove = vi.spyOn(document, 'removeEventListener');
    const { view } = mount(page());
    view.unmount();
    for (const type of ['keydown', 'click', 'focusout']) {
      const added = add.mock.calls.filter(([name]) => name === type).length;
      const removed = remove.mock.calls.filter(([name]) => name === type).length;
      expect(added, type).toBeGreaterThan(0);
      expect(removed, type).toBe(added);
    }
    add.mockRestore();
    remove.mockRestore();
  });
});
