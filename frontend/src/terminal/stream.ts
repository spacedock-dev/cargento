import type { Clock, TimerHandle } from '../transport/ports';

/* The output-only terminal socket, ported from `projectTerminalConnect` in the legacy `project.js`.

   The server answers any client frame on this socket by revoking the connection (close code 1008,
   "read-only-capability"), and the legacy page never sends one. `StreamSocket` therefore has no `send`:
   nothing typed, pasted or clicked in the terminal can be transmitted because the type this file is
   written against cannot express it, and `terminal-parity.mjs` counts the frames a real browser sent. */

export const RECONNECT_MS = 1000;

/** The close code the server uses to say it will not stream to this client; reconnecting would repeat it. */
const REVOKED = 1008;

export interface StreamSocket {
  onmessage: ((event: { readonly data: unknown }) => void) | null;
  onclose: ((event: { readonly code: number }) => void) | null;
  close(): void;
}

export interface StreamTerminal {
  readonly cols: number;
  readonly rows: number;
  resize(cols: number, rows: number): void;
  reset(): void;
  write(data: string, done: () => void): void;
  writeln(text: string): void;
}

export interface OutputStreamDeps {
  readonly url: string;
  readonly openSocket: (url: string) => StreamSocket;
  readonly clock: Clock;
  /** The registration the lookup named; a frame from another one closes the socket. */
  readonly originHint: string;
  readonly terminal: StreamTerminal;
  /** Whether this terminal is still the one the reader has open. Asked before a connect and a reconnect. */
  readonly wanted: () => boolean;
  readonly following: () => boolean;
  readonly scrollToLive: () => void;
  /** The pane was resized, so the host element should be sized to the new screen. */
  readonly sized: () => void;
}

interface Chunk {
  readonly sequence?: unknown;
  readonly cols?: unknown;
  readonly rows?: unknown;
  readonly data?: unknown;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function parse(data: unknown): Record<string, unknown> | null {
  if (typeof data !== 'string') return null;
  try {
    const frame: unknown = JSON.parse(data);
    return isRecord(frame) ? frame : null;
  } catch {
    // The legacy handler threw on a frame that was not JSON; a stream that stops on one is worse.
    return null;
  }
}

export function createOutputStream(deps: OutputStreamDeps) {
  const { terminal } = deps;
  let socket: StreamSocket | null = null;
  let reconnect: TimerHandle | null = null;
  let sequence = 0;

  function onFrame(current: StreamSocket, frame: Record<string, unknown>): void {
    if (frame.state !== 'streamed') {
      terminal.writeln(`\r\n[${String(frame.state)}: ${String(frame.reason)}]`);
      return;
    }
    if (deps.originHint && frame.origin_id_hint !== deps.originHint) {
      current.close();
      return;
    }
    const listed =
      Array.isArray(frame.chunks) && frame.chunks.length > 0
        ? (frame.chunks as Chunk[])
        : [frame as Chunk];
    let resetPending = Boolean(frame.reset);
    for (const chunk of listed) {
      const next = Number(chunk.sequence);
      if (!Number.isInteger(next) || next <= sequence) continue;
      const cols = Number(chunk.cols);
      const rows = Number(chunk.rows);
      if (!Number.isInteger(cols) || cols < 1 || !Number.isInteger(rows) || rows < 1) continue;
      if (terminal.cols !== cols || terminal.rows !== rows) {
        terminal.resize(cols, rows);
        deps.sized();
      }
      if (resetPending) {
        terminal.reset();
        resetPending = false;
      }
      if (typeof chunk.data === 'string' && chunk.data) {
        terminal.write(chunk.data, () => {
          if (socket === current && deps.following()) deps.scrollToLive();
        });
      } else if (deps.following()) {
        deps.scrollToLive();
      }
      sequence = next;
    }
  }

  function connect(): void {
    if (socket || !deps.wanted()) return;
    const opened = deps.openSocket(deps.url);
    socket = opened;
    sequence = 0;
    opened.onmessage = (event) => {
      if (socket !== opened) return;
      const frame = parse(event.data);
      if (frame) onFrame(opened, frame);
    };
    opened.onclose = (event) => {
      if (socket !== opened) return;
      socket = null;
      if (event.code === REVOKED || !deps.wanted()) return;
      reconnect = deps.clock.setTimeout(() => {
        reconnect = null;
        connect();
      }, RECONNECT_MS);
    };
  }

  function dispose(): void {
    if (reconnect !== null) {
      deps.clock.clearTimeout(reconnect);
      reconnect = null;
    }
    const closing = socket;
    socket = null;
    if (closing) {
      // The handler first: closing is this stream's own act and must not read as a drop to reconnect from.
      closing.onclose = null;
      closing.close();
    }
    sequence = 0;
  }

  return {
    connect,
    dispose,
    sequence: (): number => sequence,
    connected: (): boolean => socket !== null,
  };
}

export type OutputStream = ReturnType<typeof createOutputStream>;
