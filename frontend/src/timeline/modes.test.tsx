import { act, render } from '@testing-library/react';
import { StrictMode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fakeBackend } from '../../test/storage_backends';
import { createLegacyStorage } from '../storage';
import { createTimelineModes, useTimelineModeIn, type TimelineModes } from './modes';

const KEY = 'cargento.next.graph.mode';

function modesOver(initial: Record<string, string> = {}) {
  const backend = fakeBackend(initial);
  const modes = createTimelineModes(createLegacyStorage(() => backend).graphMode);
  return { backend, modes };
}

describe('resolving the activity filter', () => {
  it('prefers a mode the caller pinned, then the reader’s stored choice, then the caller’s default, then active', () => {
    const { modes } = modesOver({ [KEY]: '{"alpha\\u0000":"all"}' });
    expect(modes.resolve({ project: 'alpha', session: null, mode: 'decisions' })).toBe('decisions');
    expect(modes.resolve({ project: 'alpha', session: null })).toBe('all');
    // The reader's own choice outranks the caller's default.
    expect(modes.resolve({ project: 'alpha', session: null, defaultMode: 'decisions' })).toBe('all');
    expect(modes.resolve({ project: 'beta', session: null, defaultMode: 'decisions' })).toBe('decisions');
    expect(modes.resolve({ project: 'beta', session: null })).toBe('active');
  });

  it('keeps a pinned mode from overwriting what the reader chose', () => {
    const { backend, modes } = modesOver();
    modes.set({ project: 'alpha', session: null }, 'all');
    expect(modes.resolve({ project: 'alpha', session: null, mode: 'decisions' })).toBe('decisions');
    expect(backend.data.get(KEY)).toBe('{"alpha\\u0000":"all"}');
    expect(modes.resolve({ project: 'alpha', session: null })).toBe('all');
  });

  it('keeps each project, and each session of a project, its own', () => {
    const { modes } = modesOver();
    modes.set({ project: 'alpha', session: null }, 'all');
    modes.set({ project: 'alpha', session: 'claude:s1' }, 'decisions');
    expect(modes.resolve({ project: 'alpha', session: null })).toBe('all');
    expect(modes.resolve({ project: 'alpha', session: 'claude:s1' })).toBe('decisions');
    expect(modes.resolve({ project: 'alpha', session: 'codex:s1' })).toBe('active');
    expect(modes.resolve({ project: 'beta', session: null })).toBe('active');
    // A project with no label is a project of its own, not every project.
    expect(modes.resolve({ project: '', session: null })).toBe('active');
  });

  it('survives a reload, as the one JSON map the legacy page reads and writes', () => {
    const first = modesOver();
    first.modes.set({ project: 'alpha/app', session: 'claude:s1' }, 'decisions');
    first.modes.set({ project: 'beta/api', session: null }, 'all');
    const written = first.backend.data.get(KEY);
    expect(written).toBe('{"alpha/app\\u0000claude:s1":"decisions","beta/api\\u0000":"all"}');
    const reloaded = modesOver({ [KEY]: written ?? '' });
    expect(reloaded.modes.resolve({ project: 'alpha/app', session: 'claude:s1' })).toBe('decisions');
    expect(reloaded.modes.resolve({ project: 'beta/api', session: null })).toBe('all');
    expect(reloaded.modes.resolve({ project: 'alpha/app', session: null })).toBe('active');
  });

  it('discards the old build’s single empty-scope key rather than reading it as a project', () => {
    const { backend, modes } = modesOver({ [KEY]: '{"":"all","alpha\\u0000":"decisions"}' });
    expect(modes.resolve({ project: '', session: null })).toBe('active');
    expect(modes.resolve({ project: 'alpha', session: null })).toBe('decisions');
    modes.set({ project: 'beta', session: null }, 'all');
    expect(backend.data.get(KEY)).toBe('{"alpha\\u0000":"decisions","beta\\u0000":"all"}');
  });

  it('refuses a mode it does not know, writes nothing and tells nobody', () => {
    const { backend, modes } = modesOver();
    const listener = vi.fn();
    modes.subscribe(listener);
    expect((modes.set as (scope: { project: string; session: null }, mode: string) => boolean)({ project: 'alpha', session: null }, 'everything')).toBe(false);
    expect(backend.writes).toEqual([]);
    expect(listener).not.toHaveBeenCalled();
  });

  it('writes nothing when it only reads', () => {
    const { backend, modes } = modesOver({ [KEY]: '{"":"all"}' });
    modes.resolve({ project: 'alpha', session: null });
    expect(backend.writes).toEqual([]);
  });

  it('holds the choice for the tab when browser storage refuses writes', () => {
    const modes = createTimelineModes(
      createLegacyStorage(() => ({
        getItem: () => null,
        setItem: () => {
          throw new DOMException('quota', 'QuotaExceededError');
        },
        removeItem: () => undefined,
      })).graphMode,
    );
    expect(modes.set({ project: 'alpha', session: null }, 'all')).toBe(true);
    expect(modes.resolve({ project: 'alpha', session: null })).toBe('all');
  });

  it('tells subscribers about a choice, once, and stops when they leave', () => {
    const { modes } = modesOver();
    const listener = vi.fn();
    const off = modes.subscribe(listener);
    modes.set({ project: 'alpha', session: null }, 'all');
    expect(listener).toHaveBeenCalledTimes(1);
    off();
    modes.set({ project: 'alpha', session: null }, 'decisions');
    expect(listener).toHaveBeenCalledTimes(1);
  });
});

describe('the hook', () => {
  function Probe({ modes, project, session, defaultMode }: { modes: TimelineModes; project: string; session: string | null; defaultMode?: 'decisions' }) {
    const [mode, setMode] = useTimelineModeIn(modes, { project, session, ...(defaultMode ? { defaultMode } : {}) });
    return (
      <div data-testid={`${project}|${session ?? ''}`}>
        <output>{mode}</output>
        <button type="button" onClick={() => setMode('all')}>
          all
        </button>
      </div>
    );
  }

  it('redraws every reader of a scope when one of them chooses, under StrictMode', () => {
    const { modes } = modesOver();
    const view = render(
      <StrictMode>
        <Probe modes={modes} project="alpha" session={null} />
        <Probe modes={modes} project="alpha" session={null} />
        <Probe modes={modes} project="beta" session={null} defaultMode="decisions" />
      </StrictMode>,
    );
    const outputs = () => [...view.container.querySelectorAll('output')].map((node) => node.textContent);
    expect(outputs()).toEqual(['active', 'active', 'decisions']);
    act(() => {
      view.container.querySelector('button')?.click();
    });
    expect(outputs()).toEqual(['all', 'all', 'decisions']);
  });

  it('comes back with the choice after the view is unmounted and mounted again', () => {
    const { modes } = modesOver();
    const first = render(<Probe modes={modes} project="alpha" session="claude:s1" />);
    act(() => {
      first.container.querySelector('button')?.click();
    });
    first.unmount();
    const second = render(<Probe modes={modes} project="alpha" session="claude:s1" />);
    expect(second.container.querySelector('output')?.textContent).toBe('all');
  });
});
