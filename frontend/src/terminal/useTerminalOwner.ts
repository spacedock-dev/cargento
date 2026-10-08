import { useShell, type Shell } from '../shell/context';
import { createTerminalOwner, type TerminalOwner } from './owner';
import type { StreamSocket } from './stream';
import { createXtermLoader, type XtermConstructor } from './xterm';

/* One owner per shell, held outside the tree. The shell is built once per document, so this is one owner
   per document: a remount, a route change and StrictMode's second render all reach the same terminal, and
   none of them can open a second socket. */
const owners = new WeakMap<Shell, TerminalOwner>();

/* A hot update re-runs the module that builds the shell, which makes a new shell and so a new owner. The
   previous one is disposed here, before the new one can open anything, for the reason `replaceRuntime`
   gives for the board's runtime: two owners would hold a socket each. */
const SLOT = Symbol.for('cargento.terminal.owner');

/* The browser's WebSocket behind the interface the stream is written against. The close handler and the
   message handler are wrapped rather than assigned straight, and there is no `send` on what it returns:
   the terminal socket is output-only (see `./stream`). */
export function browserSocket(url: string): StreamSocket {
  const socket = new WebSocket(url);
  const handle: StreamSocket = {
    onmessage: null,
    onclose: null,
    close: () => {
      socket.close();
    },
  };
  socket.onmessage = (event) => handle.onmessage?.({ data: event.data as unknown });
  socket.onclose = (event) => handle.onclose?.({ code: event.code });
  return handle;
}

export function terminalOwnerFor(shell: Shell): TerminalOwner {
  const held = owners.get(shell);
  if (held) return held;
  const owner = createTerminalOwner({
    client: shell.runtime.client,
    clock: shell.clock,
    loader: createXtermLoader({
      document,
      terminal: () => (window as unknown as { Terminal?: XtermConstructor }).Terminal,
    }),
    openSocket: browserSocket,
    streamUrl: () =>
      `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/interaction/stream`,
    document,
  });
  const slot = globalThis as unknown as Record<symbol, TerminalOwner | undefined>;
  slot[SLOT]?.dispose();
  slot[SLOT] = owner;
  owners.set(shell, owner);
  return owner;
}

/* A test seam: a component test installs an owner built over doubles (no real renderer script, no real
   socket) before it renders. Production never calls it. */
export function installTerminalOwner(shell: Shell, owner: TerminalOwner): void {
  owners.set(shell, owner);
}

export function useTerminalOwner(): TerminalOwner {
  return terminalOwnerFor(useShell());
}
