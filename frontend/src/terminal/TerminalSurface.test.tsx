import { act, fireEvent, render } from '@testing-library/react';
import { StrictMode, useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { FetchLike } from '../api/client';
import { ControlsProvider } from '../controls/ControlsProvider';
import { fakeBackend } from '../../test/storage_backends';
import { ShellContext } from '../shell/context';
import { createShell } from '../shell/createShell';
import { createFakeClock, createFakeEnvironment } from '../transport/testing';
import { createTerminalOwner } from './owner';
import { FakeSocket, FakeXterm, instances } from './testing';
import { TerminalSurface } from './TerminalSurface';
import { installTerminalOwner } from './useTerminalOwner';
import type { XtermConstructor } from './xterm';

/* The surface over the real shell objects (store, runtime, controls, disclosures) and a scripted backend.
   Only the renderer script and the WebSocket are doubled, because jsdom loads neither. */

type OriginAnswer = { readonly status: number; readonly body?: Record<string, unknown> };

function world(answers: Record<string, OriginAnswer>) {
  instances.length = 0;
  const clock = createFakeClock();
  const env = createFakeEnvironment({ clock });
  const requests: { method: string; url: string }[] = [];
  const fetch: FetchLike = (url, init) => {
    requests.push({ method: init?.method ?? 'GET', url });
    const match = /^\/api\/interaction\/origin\?harness=([^&]*)&sid=([^&]*)$/.exec(url);
    if (!match) return Promise.reject(new Error('offline'));
    const answer = answers[`${decodeURIComponent(match[1] ?? '')}:${decodeURIComponent(match[2] ?? '')}`] ?? { status: 404 };
    return Promise.resolve(new Response(JSON.stringify(answer.body ?? {}), { status: answer.status }));
  };
  const shell = createShell({
    env,
    fetch,
    provider: () => fakeBackend(),
    events: { addEventListener: () => undefined, removeEventListener: () => undefined },
    search: '',
    doc: null,
    reducedMotion: () => true,
  });
  const sockets: FakeSocket[] = [];
  const loads: (() => void)[] = [];
  let shared: Promise<XtermConstructor> | null = null;
  const owner = createTerminalOwner({
    client: shell.runtime.client,
    clock: shell.clock,
    loader: {
      load: () => {
        shared ??= new Promise<XtermConstructor>((resolve) => {
          loads.push(() => resolve(FakeXterm as unknown as XtermConstructor));
        });
        return shared;
      },
    },
    openSocket: () => {
      const socket = new FakeSocket();
      sockets.push(socket);
      return socket;
    },
    streamUrl: () => 'ws://127.0.0.1:1/api/interaction/stream',
    document,
  });
  installTerminalOwner(shell, owner);
  return { shell, owner, requests, sockets, loads, clock };
}

const REGISTERED = {
  status: 200,
  body: {
    state: 'registered',
    reason: 'exact-collected-session-origin',
    origin: { session_name: 'smoke', window_index: '0', pane_index: '0' },
    origin_id_hint: 'abcd1234',
  },
};

const settle = () =>
  act(async () => {
    for (let turn = 0; turn < 12; turn += 1) await Promise.resolve();
  });

function mount(
  w: ReturnType<typeof world>,
  props: { project?: string; harness?: string; sid?: string } = {},
) {
  const project = props.project ?? 'alpha/app';
  const identity = { harness: props.harness ?? 'codex', sid: props.sid ?? 'alpha' };
  const Host = () => {
    const [shown, setShown] = useState(true);
    return (
      <>
        <button type="button" onClick={() => setShown((value) => !value)}>
          toggle view
        </button>
        {shown ? <TerminalSurface project={project} identity={identity} /> : <p>another view</p>}
      </>
    );
  };
  const tree = (
    <StrictMode>
      <ShellContext value={w.shell}>
        <ControlsProvider controls={w.shell.controls}>
          <Host />
        </ControlsProvider>
      </ShellContext>
    </StrictMode>
  );
  return render(tree);
}

beforeEach(() => {
  // After a click's own activation, as a real frame is.
  vi.stubGlobal('requestAnimationFrame', (run: () => void) => setTimeout(run, 0));
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe('what the surface says before it can offer a terminal', () => {
  it('says it is checking, as a status, until the first answer', async () => {
    const w = world({ 'codex:alpha': REGISTERED });
    const view = mount(w);
    expect(view.getByRole('status').textContent).toBe('Checking terminal registration for this exact session.');
    await settle();
    expect(view.queryByRole('status')).toBeNull();
  });

  it('asks for the exact harness and sid, by GET, and sends no POST', async () => {
    const w = world({ 'codex:alpha': REGISTERED });
    mount(w, { harness: 'codex', sid: 'colon:sid' });
    await settle();
    expect(w.requests).toEqual([{ method: 'GET', url: '/api/interaction/origin?harness=codex&sid=colon%3Asid' }]);
  });

  it('asks nothing, and says why, for a session with no exact identity', async () => {
    const w = world({ 'codex:': REGISTERED });
    const view = mount(w, { harness: 'codex', sid: '' });
    await settle();
    expect(w.requests).toEqual([]);
    expect(view.getByText('This session published no exact identity, so no terminal can be matched to it.')).toBeInTheDocument();
    expect(view.queryByRole('button', { name: 'Open terminal' })).toBeNull();
  });

  it('never lets a terminal registered for one session be opened from another that shares its sid or project', async () => {
    const w = world({ 'codex:alpha': REGISTERED, 'claude:alpha': { status: 200, body: { state: 'refused', reason: 'session-mismatch' } } });
    const view = mount(w, { harness: 'claude', sid: 'alpha' });
    await settle();
    expect(w.requests.map((request) => request.url)).toEqual(['/api/interaction/origin?harness=claude&sid=alpha']);
    expect(view.getByText('The registered terminal belongs to another session.')).toBeInTheDocument();
    expect(view.queryByRole('button', { name: 'Open terminal' })).toBeNull();
  });

  it('says the bridge is disabled when the server has none, and shows the two-step recipe behind a disclosure', async () => {
    const w = world({});
    const view = mount(w);
    await settle();
    expect(view.getByText('The terminal bridge is disabled on this server.')).toBeInTheDocument();
    expect(view.queryByRole('button', { name: 'Open terminal' })).toBeNull();
    const summary = view.getByText('How to register a terminal');
    expect(summary.tagName).toBe('SUMMARY');
    const steps = summary.closest('details')?.querySelectorAll('ol > li');
    expect(steps).toHaveLength(2);
    expect(steps?.[0]?.textContent).toContain('--interaction-origin-session harness:sid');
    expect(steps?.[0]?.textContent).toContain('--interaction-origin-registration-file PATH');
    expect(steps?.[1]?.textContent).toBe('Run the registration client inside the tmux pane for this exact session with that file.');
    expect(view.getByText('Output is read-only.')).toBeInTheDocument();
  });

  it('shows no recipe for a reason registering cannot fix', async () => {
    const w = world({ 'codex:alpha': { status: 200, body: { state: 'unknown', reason: 'origin-disconnected' } } });
    const view = mount(w);
    await settle();
    expect(view.getByText('The registered tmux pane is disconnected.')).toBeInTheDocument();
    expect(view.queryByText('How to register a terminal')).toBeNull();
  });

  it('shows a reason this page has no sentence for as the server stated it', async () => {
    const w = world({ 'codex:alpha': { status: 200, body: { state: 'refused', reason: 'brand-new-reason' } } });
    const view = mount(w);
    await settle();
    expect(view.getByText('The server refused terminal access.')).toBeInTheDocument();
    expect(view.getByText('brand-new-reason').tagName).toBe('CODE');
  });

  it('keeps the recipe open, and each project’s open state its own, across leaving and returning', async () => {
    const w = world({});
    const first = mount(w, { project: 'alpha/app' });
    await settle();
    const details = first.getByText('How to register a terminal').closest('details') as HTMLDetailsElement;
    act(() => {
      details.open = true;
    });
    await act(() => new Promise<void>((resolve) => setTimeout(resolve, 0)));
    fireEvent.click(first.getByRole('button', { name: 'toggle view' }));
    expect(first.getByText('another view')).toBeInTheDocument();
    fireEvent.click(first.getByRole('button', { name: 'toggle view' }));
    const back = first.getByText('How to register a terminal').closest('details') as HTMLDetailsElement;
    expect(back.open).toBe(true);
    first.unmount();
    // Another project's console, same session identity: its own state, closed.
    const other = mount(w, { project: 'beta/api' });
    await settle();
    expect((other.getByText('How to register a terminal').closest('details') as HTMLDetailsElement).open).toBe(false);
  });
});

describe('opening the terminal', () => {
  it('offers Open terminal for a registered session and starts nothing until it is pressed', async () => {
    const w = world({ 'codex:alpha': REGISTERED });
    const view = mount(w);
    await settle();
    expect(view.getByRole('button', { name: 'Open terminal' })).toBeInTheDocument();
    expect(w.loads).toHaveLength(0);
    expect(w.sockets).toHaveLength(0);
    expect(instances).toHaveLength(0);
  });

  it('opens one terminal and one socket under StrictMode, titled with its exact coordinates, zero included', async () => {
    const w = world({ 'codex:alpha': REGISTERED });
    const view = mount(w);
    await settle();
    fireEvent.click(view.getByRole('button', { name: 'Open terminal' }));
    await settle();
    expect(view.getByLabelText('Read-only terminal output', { selector: 'aside' })).toBeInTheDocument();
    expect(view.getByText('smoke:0.0')).toBeInTheDocument();
    expect(view.getByText('read-only')).toBeInTheDocument();
    expect(w.loads).toHaveLength(1);
    w.loads[0]?.();
    await settle();
    expect(instances).toHaveLength(1);
    expect(w.sockets).toHaveLength(1);
    expect(document.querySelector('#pc-terminal-viewport #pc-terminal-screen .xterm')).not.toBeNull();
  });

  it('says what it was not told, and never invents a coordinate', async () => {
    const w = world({
      'codex:alpha': { status: 200, body: { state: 'registered', origin: { window_index: 0 }, origin_id_hint: 'abcd1234' } },
    });
    const view = mount(w);
    await settle();
    fireEvent.click(view.getByRole('button', { name: 'Open terminal' }));
    await settle();
    expect(view.getByText('Tmux session name not published.')).toBeInTheDocument();
    expect(view.getByText('window 0').tagName).toBe('CODE');
    expect(view.getByText('Pane index not published.')).toBeInTheDocument();
  });

  it('hides Jump to live while following and shows it when the reader scrolls away, and Jump resumes', async () => {
    const w = world({ 'codex:alpha': REGISTERED });
    const view = mount(w);
    await settle();
    fireEvent.click(view.getByRole('button', { name: 'Open terminal' }));
    await settle();
    w.loads[0]?.();
    await settle();
    const viewport = document.getElementById('pc-terminal-viewport') as HTMLElement;
    const jump = view.getByText('Jump to live') as HTMLButtonElement;
    expect(jump.hidden).toBe(true);
    // jsdom lays nothing out; give the real viewport a 492 px content height in a 340 px window.
    Object.defineProperties(viewport, {
      scrollHeight: { value: 492, configurable: true },
      clientHeight: { value: 340, configurable: true },
    });
    const terminal = instances[0];
    if (terminal) terminal.buffer.active.cursorY = 23;
    act(() => {
      viewport.scrollTop = 30;
      viewport.dispatchEvent(new Event('scroll'));
    });
    expect(jump.hidden).toBe(false);
    fireEvent.click(jump);
    expect(jump.hidden).toBe(true);
  });

  it('keeps the same screen, terminal and socket when the view is left and returned to', async () => {
    const w = world({ 'codex:alpha': REGISTERED });
    const view = mount(w);
    await settle();
    fireEvent.click(view.getByRole('button', { name: 'Open terminal' }));
    await settle();
    w.loads[0]?.();
    await settle();
    const screen = document.getElementById('pc-terminal-screen');
    w.sockets[0]?.deliver({ state: 'streamed', sequence: 1, origin_id_hint: 'abcd1234', chunks: [{ sequence: 1, data: 'kept', cols: 80, rows: 24 }] });
    fireEvent.click(view.getByRole('button', { name: 'toggle view' }));
    expect(document.getElementById('pc-terminal-viewport')).toBeNull();
    expect(screen?.isConnected).toBe(false);
    expect(instances[0]?.disposed).toBe(false);
    fireEvent.click(view.getByRole('button', { name: 'toggle view' }));
    await settle();
    expect(document.getElementById('pc-terminal-screen')).toBe(screen);
    expect(instances).toHaveLength(1);
    expect(instances[0]?.written).toEqual(['kept']);
    expect(w.sockets).toHaveLength(1);
    expect(w.sockets[0]?.closed).toBe(0);
    expect(w.loads).toHaveLength(1);
  });

  it('closes the terminal and goes back to the offer on Close, closing only its own socket', async () => {
    const w = world({ 'codex:alpha': REGISTERED });
    const view = mount(w);
    await settle();
    fireEvent.click(view.getByRole('button', { name: 'Open terminal' }));
    await settle();
    w.loads[0]?.();
    await settle();
    fireEvent.click(view.getByRole('button', { name: 'Close' }));
    expect(view.getByRole('button', { name: 'Open terminal' })).toBeInTheDocument();
    expect(instances[0]?.disposed).toBe(true);
    expect(w.sockets[0]?.closed).toBe(1);
  });

  it('re-checks the registration on the next board revision without asking twice for one', async () => {
    const w = world({ 'codex:alpha': REGISTERED });
    mount(w);
    await settle();
    expect(w.requests).toHaveLength(1);
    act(() => w.shell.runtime.store.acceptData({ generated: 5 }, 'r5'));
    await settle();
    expect(w.requests).toHaveLength(2);
    act(() => w.shell.runtime.store.acceptData({ generated: 5 }, 'r5'));
    await settle();
    expect(w.requests).toHaveLength(2);
  });
});
