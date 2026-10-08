import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { PayloadData } from '../api/types';
import { ControlsProvider } from '../controls/ControlsProvider';
import { testControls } from '../controls/testControls';
import { createBoardStore, type BoardSnapshot } from '../store/board';
import { Notices } from './Notices';

const body = (value: unknown): PayloadData => value as PayloadData;

/* A board in the state a poll history left it: `failures` consecutive failed reads since the last accepted body. */
function board(options: { data?: unknown; failures?: number; at?: number; build?: string } = {}) {
  let clock = options.at ?? 1_000_000;
  const store = createBoardStore({ now: () => clock });
  if (options.data !== undefined) {
    const data = body(options.data);
    store.acceptData(options.build === undefined ? data : body({ ...(data as object), build: options.build }), '1.1');
  }
  for (let index = 0; index < (options.failures ?? 0); index += 1) store.recordFailure({ kind: 'network-error' });
  return { store, snapshot: (): BoardSnapshot => store.getSnapshot(), setClock: (value: number) => void (clock = value) };
}

function show(snapshot: BoardSnapshot, extra: { now?: number; retryMs?: number; onRetry?: () => void; onReload?: () => void } = {}) {
  const { controls } = testControls();
  const props = {
    snapshot,
    now: extra.now ?? 1_000_000,
    retryMs: extra.retryMs ?? 20_000,
    onRetry: extra.onRetry ?? (() => undefined),
    onReload: extra.onReload ?? (() => undefined),
    disclosureScope: { project: null, scope: null },
  };
  const utils = render(
    <ControlsProvider controls={controls}>
      <Notices {...props} />
    </ControlsProvider>,
  );
  return { ...utils, props, controls };
}

describe('a failed live refresh', () => {
  it('shows nothing before the first failure, and nothing at the first', () => {
    const healthy = board({ data: { sessions: [] } });
    expect(show(healthy.snapshot()).container.innerHTML).toBe('');
    const once = board({ data: { sessions: [] }, failures: 1 });
    expect(show(once.snapshot()).container.innerHTML).toBe('');
  });

  it('is told at the second consecutive failure, with the retry interval and the age of the data on screen', () => {
    const twice = board({ data: { sessions: [] }, failures: 2, at: 1_000_000 });
    show(twice.snapshot(), { now: 1_040_000, retryMs: 5_000 });
    const notice = screen.getByRole('status');
    expect(notice.getAttribute('data-next-state')).toBe('stalled');
    expect(within(notice).getByText('Live refresh failed twice in a row.')).toBeInTheDocument();
    expect(notice.textContent).toContain('Displayed data may be stale. Last updated 40s ago. Retrying automatically every 5s.');
    expect((within(notice).getByRole('button', { name: 'Retry now' }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('counts further failures in words, and names the interval the stream-less poll uses', () => {
    const many = board({ data: { sessions: [] }, failures: 4 });
    show(many.snapshot(), { retryMs: 20_000 });
    expect(screen.getByText('Live refresh failed 4 times in a row.')).toBeInTheDocument();
    expect(screen.getByRole('status').textContent).toContain('Retrying automatically every 20s.');
  });

  it('never rounds the interval below one second', () => {
    show(board({ data: { sessions: [] }, failures: 2 }).snapshot(), { retryMs: 100 });
    expect(screen.getByRole('status').textContent).toContain('Retrying automatically every 1s.');
  });

  it('says plainly that nothing has ever arrived, instead of dressing an absent board as stale data', () => {
    show(board({ failures: 2 }).snapshot());
    const notice = screen.getByRole('status');
    expect(notice.textContent).toContain('No data has been received in this tab.');
    expect(notice.textContent).not.toContain('Displayed data may be stale');
    expect(notice.textContent).not.toContain('Last updated');
  });

  it('is cleared by the next accepted body, which is the only success there is', () => {
    const recovering = board({ data: { sessions: [] }, failures: 3 });
    const { container, rerender, props, controls } = show(recovering.snapshot());
    expect(container.innerHTML).not.toBe('');
    recovering.store.acceptData(body({ sessions: [] }), '1.2');
    rerender(
      <ControlsProvider controls={controls}>
        <Notices {...props} snapshot={recovering.snapshot()} />
      </ControlsProvider>,
    );
    expect(container.innerHTML).toBe('');
  });

  it('offers Retry now once per press, and holds it unavailable, never disabled, while a manual refresh is out', () => {
    const onRetry = vi.fn();
    const failing = board({ data: { sessions: [] }, failures: 2 });
    const { rerender, props, controls } = show(failing.snapshot(), { onRetry });
    fireEvent.click(screen.getByRole('button', { name: 'Retry now' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
    failing.store.setManualRefreshing(true);
    rerender(
      <ControlsProvider controls={controls}>
        <Notices {...props} snapshot={failing.snapshot()} />
      </ControlsProvider>,
    );
    const button = screen.getByRole('button', { name: 'Retry now' }) as HTMLButtonElement;
    // `disabled` would drop focus from the control the reader just pressed, and the notice's removal
    // would then have no focused node to hand back; `aria-disabled` keeps it, and the press is refused here.
    expect(button.disabled).toBe(false);
    expect(button.getAttribute('aria-disabled')).toBe('true');
    fireEvent.click(button);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('does not press anything on mount', () => {
    const onRetry = vi.fn();
    show(board({ data: { sessions: [] }, failures: 2 }).snapshot(), { onRetry });
    expect(onRetry).not.toHaveBeenCalled();
  });
});

describe('a reset history', () => {
  const reset = (reason: unknown) => show(board({ data: { sessions: [], history_reset: reason } }).snapshot());

  it('tells which reset it was, so a corruption reset and a version reset do not read alike', () => {
    const unreadable = reset('unreadable');
    const first = screen.getByRole('status').textContent;
    expect(screen.getByRole('status').getAttribute('data-next-state')).toBe('history-reset');
    expect(first).toContain('The saved history was reset.');
    expect(first).toContain('The saved file could not be read.');
    expect(first).toContain('The rail and the delegation figure start from this tab.');
    unreadable.unmount();
    reset('version');
    const second = screen.getByRole('status').textContent;
    expect(second).toContain('It was written by a different version of Cargento.');
    expect(second).not.toBe(first);
  });

  it('draws nothing for an absent or unrecognised literal, which a tampered store could have written', () => {
    for (const value of [undefined, '<img src=x onerror=alert(1)>', 'toString', 3, null]) {
      const { container, unmount } = reset(value);
      expect(container.innerHTML).toBe('');
      unmount();
    }
  });
});

describe('a server restarted into a newer build', () => {
  it('asks for a reload only when the board published a build different from the first it heard', () => {
    const same = board({ data: { sessions: [] }, build: 'b1' });
    expect(show(same.snapshot()).container.innerHTML).toBe('');
  });

  it('says nothing for a board that publishes no build, which is an older one', () => {
    expect(show(board({ data: { sessions: [] } }).snapshot()).container.innerHTML).toBe('');
  });

  it('shows one reload line with a Reload button that fires only on a press, and a Why disclosure behind it', () => {
    const onReload = vi.fn();
    const changed = board({ data: { sessions: [] }, build: 'b1' });
    changed.store.acceptData(body({ sessions: [], build: 'b2' }), '1.2');
    show(changed.snapshot(), { onReload });
    const notice = screen.getByRole('status');
    expect(notice.getAttribute('data-next-state')).toBe('build-changed');
    expect(within(notice).getByText('Reload to use the new version.')).toBeInTheDocument();
    expect(within(notice).getByText('Why reload')).toBeInTheDocument();
    expect(notice.textContent).toContain('Cargento was restarted with a different version after this page loaded');
    expect(onReload).not.toHaveBeenCalled();
    fireEvent.click(within(notice).getByRole('button', { name: 'Reload' }));
    expect(onReload).toHaveBeenCalledTimes(1);
  });
});

describe('the notices stand in a fixed order and stay distinct', () => {
  it('draws the stalled notice, then the history reset, then the build notice, never merged', () => {
    const everything = board({ data: { sessions: [], history_reset: 'version' }, build: 'b1', failures: 2 });
    everything.store.acceptData(body({ sessions: [], history_reset: 'version', build: 'b2' }), '1.2');
    everything.store.recordFailure({ kind: 'network-error' });
    everything.store.recordFailure({ kind: 'network-error' });
    show(everything.snapshot());
    const states = screen.getAllByRole('status').map((node) => node.getAttribute('data-next-state'));
    expect(states).toEqual(['stalled', 'history-reset', 'build-changed']);
  });
});
