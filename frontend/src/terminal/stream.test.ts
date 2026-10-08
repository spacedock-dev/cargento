import { describe, expect, it } from 'vitest';
import { createFakeClock } from '../transport/testing';
import { createOutputStream, RECONNECT_MS, type StreamSocket, type StreamTerminal } from './stream';

/* A socket that records everything the client could do to it. The interface the stream is written
   against has no `send`, so a call to one would not compile; this fake also throws on one, so a cast
   that got round the type would still fail the test rather than pass it silently. */
class FakeSocket implements StreamSocket {
  onmessage: StreamSocket['onmessage'] = null;
  onclose: StreamSocket['onclose'] = null;
  closed = 0;
  sent = 0;
  close(): void {
    this.closed += 1;
  }
  send(): never {
    this.sent += 1;
    throw new Error('the terminal socket is output-only');
  }
  deliver(frame: unknown): void {
    this.onmessage?.({ data: typeof frame === 'string' ? frame : JSON.stringify(frame) });
  }
  drop(code: number): void {
    this.onclose?.({ code });
  }
}

function fakeTerminal(): StreamTerminal & {
  calls: string[];
  written: string[];
  done: (() => void)[];
} {
  const calls: string[] = [];
  const written: string[] = [];
  const done: (() => void)[] = [];
  const size = { cols: 80, rows: 24 };
  return {
    calls,
    written,
    done,
    get cols() {
      return size.cols;
    },
    get rows() {
      return size.rows;
    },
    resize(cols, rows) {
      calls.push(`resize ${String(cols)}x${String(rows)}`);
      size.cols = cols;
      size.rows = rows;
    },
    reset() {
      calls.push('reset');
    },
    write(data, finished) {
      calls.push('write');
      written.push(data);
      done.push(finished);
    },
    writeln(text) {
      calls.push(`writeln ${text}`);
    },
  };
}

function setup(
  overrides: { originHint?: string; wanted?: () => boolean; following?: () => boolean } = {},
) {
  const clock = createFakeClock();
  const sockets: FakeSocket[] = [];
  const terminal = fakeTerminal();
  const log = { scrolls: 0, sized: 0 };
  const stream = createOutputStream({
    url: 'ws://127.0.0.1:1/api/interaction/stream',
    openSocket: () => {
      const socket = new FakeSocket();
      sockets.push(socket);
      return socket;
    },
    clock,
    originHint: overrides.originHint ?? '',
    terminal,
    wanted: overrides.wanted ?? (() => true),
    following: overrides.following ?? (() => true),
    scrollToLive: () => {
      log.scrolls += 1;
    },
    sized: () => {
      log.sized += 1;
    },
  });
  return { clock, sockets, terminal, log, stream };
}

const chunk = (sequence: number, data: string, cols = 80, rows = 24) => ({
  sequence,
  data,
  cols,
  rows,
});
const streamed = (chunks: unknown[], extra: Record<string, unknown> = {}) => ({
  state: 'streamed',
  sequence: 1,
  chunks,
  origin_id_hint: 'abcd1234',
  ...extra,
});

describe('opening the socket', () => {
  it('opens one socket to the given address and not a second while it is open', () => {
    const { sockets, stream } = setup();
    stream.connect();
    stream.connect();
    expect(sockets).toHaveLength(1);
  });

  it('does not open a socket for a stream that is no longer wanted', () => {
    const { sockets, stream } = setup({ wanted: () => false });
    stream.connect();
    expect(sockets).toHaveLength(0);
  });

  it('transmits nothing, whatever arrives, however it drops and reconnects', () => {
    const { clock, sockets, stream } = setup();
    stream.connect();
    sockets[0]?.deliver(streamed([chunk(1, 'hello\r\n')]));
    sockets[0]?.deliver({ state: 'refused', reason: 'stale-registration' });
    sockets[0]?.drop(1006);
    clock.advance(RECONNECT_MS);
    sockets[1]?.deliver(streamed([chunk(1, 'again')]));
    stream.dispose();
    expect(sockets.map((socket) => socket.sent)).toEqual([0, 0]);
  });
});

describe('reading frames', () => {
  it('writes each chunk in order and records the last sequence', () => {
    const { sockets, stream, terminal } = setup();
    stream.connect();
    sockets[0]?.deliver(streamed([chunk(1, 'one'), chunk(2, 'two')]));
    expect(terminal.written).toEqual(['one', 'two']);
    expect(stream.sequence()).toBe(2);
  });

  it('reads a frame with no chunk list as one chunk of its own', () => {
    const { sockets, stream, terminal } = setup();
    stream.connect();
    sockets[0]?.deliver({ state: 'streamed', sequence: 4, data: 'whole', cols: 80, rows: 24 });
    expect(terminal.written).toEqual(['whole']);
    expect(stream.sequence()).toBe(4);
  });

  it('drops a chunk it has already seen, and one that is out of order', () => {
    const { sockets, stream, terminal } = setup();
    stream.connect();
    sockets[0]?.deliver(streamed([chunk(3, 'three')]));
    sockets[0]?.deliver(streamed([chunk(2, 'older'), chunk(3, 'again'), chunk(4, 'four')]));
    expect(terminal.written).toEqual(['three', 'four']);
    expect(stream.sequence()).toBe(4);
  });

  it('refuses a chunk whose size is not a positive whole number and does not advance past it', () => {
    const { sockets, stream, terminal } = setup();
    stream.connect();
    sockets[0]?.deliver(
      streamed([chunk(1, 'a', 0, 24), chunk(2, 'b', 80, 1.5), chunk(3, 'c', 80, 24)]),
    );
    expect(terminal.written).toEqual(['c']);
    expect(stream.sequence()).toBe(3);
  });

  it('resizes only when the pane size changed, and tells the host to follow the new size', () => {
    const { log, sockets, stream, terminal } = setup();
    stream.connect();
    sockets[0]?.deliver(
      streamed([chunk(1, 'a', 80, 24), chunk(2, 'b', 100, 30), chunk(3, 'c', 100, 30)]),
    );
    expect(terminal.calls.filter((call) => call.startsWith('resize'))).toEqual(['resize 100x30']);
    expect(log.sized).toBe(1);
  });

  it('clears the screen before the first chunk of a reset frame, and only once', () => {
    const { sockets, stream, terminal } = setup();
    stream.connect();
    sockets[0]?.deliver(streamed([chunk(1, 'a'), chunk(2, 'b')], { reset: true }));
    expect(terminal.calls.filter((call) => call === 'reset')).toHaveLength(1);
    expect(terminal.calls.indexOf('reset')).toBeLessThan(terminal.calls.indexOf('write'));
  });

  it('says a refusal on the screen instead of leaving it silent', () => {
    const { sockets, stream, terminal } = setup();
    stream.connect();
    sockets[0]?.deliver({ state: 'refused', reason: 'stale-registration' });
    expect(terminal.calls).toEqual(['writeln \r\n[refused: stale-registration]']);
    expect(terminal.written).toEqual([]);
  });

  it('closes a stream whose origin hint is another registration', () => {
    const { sockets, stream, terminal } = setup({ originHint: 'abcd1234' });
    stream.connect();
    sockets[0]?.deliver(streamed([chunk(1, 'ok')], { origin_id_hint: 'abcd1234' }));
    expect(sockets[0]?.closed).toBe(0);
    sockets[0]?.deliver(streamed([chunk(2, 'foreign')], { origin_id_hint: 'ffff0000' }));
    expect(sockets[0]?.closed).toBe(1);
    expect(terminal.written).toEqual(['ok']);
  });

  it('ignores a frame that is not JSON or not an object', () => {
    const { sockets, stream, terminal } = setup();
    stream.connect();
    sockets[0]?.deliver('not json');
    sockets[0]?.deliver('7');
    sockets[0]?.deliver('null');
    expect(terminal.calls).toEqual([]);
    expect(stream.sequence()).toBe(0);
  });

  it('keeps up with output only while following', () => {
    let following = true;
    const { log, sockets, stream, terminal } = setup({ following: () => following });
    stream.connect();
    sockets[0]?.deliver(streamed([chunk(1, 'a')]));
    expect(log.scrolls).toBe(0);
    terminal.done[0]?.();
    expect(log.scrolls).toBe(1);
    following = false;
    sockets[0]?.deliver(streamed([chunk(2, 'b')]));
    terminal.done[1]?.();
    expect(log.scrolls).toBe(1);
  });

  it('scrolls on a dataless chunk while following, since there is nothing to wait for', () => {
    const { log, sockets, stream } = setup();
    stream.connect();
    sockets[0]?.deliver(streamed([chunk(1, '')]));
    expect(log.scrolls).toBe(1);
  });

  it('does not scroll for a write that finishes after the stream was disposed', () => {
    const { log, sockets, stream, terminal } = setup();
    stream.connect();
    sockets[0]?.deliver(streamed([chunk(1, 'a')]));
    stream.dispose();
    terminal.done[0]?.();
    expect(log.scrolls).toBe(0);
  });
});

describe('reconnecting and disposing', () => {
  it('reconnects once after a drop and starts reading from the beginning', () => {
    const { clock, sockets, stream, terminal } = setup();
    stream.connect();
    sockets[0]?.deliver(streamed([chunk(5, 'x')]));
    sockets[0]?.drop(1006);
    expect(sockets).toHaveLength(1);
    clock.advance(RECONNECT_MS - 1);
    expect(sockets).toHaveLength(1);
    clock.advance(1);
    expect(sockets).toHaveLength(2);
    expect(stream.sequence()).toBe(0);
    // The server's reset frame replays from sequence 1, so a chunk numbered 1 is new again.
    sockets[1]?.deliver(streamed([chunk(1, 'y')], { reset: true }));
    expect(terminal.written).toEqual(['x', 'y']);
  });

  it('does not reconnect after the server revoked it', () => {
    const { clock, sockets, stream } = setup();
    stream.connect();
    sockets[0]?.drop(1008);
    clock.advance(RECONNECT_MS * 5);
    expect(sockets).toHaveLength(1);
    expect(clock.activeTimers()).toBe(0);
    stream.connect();
    expect(sockets).toHaveLength(2);
  });

  it('does not reconnect once the stream is no longer wanted', () => {
    let wanted = true;
    const { clock, sockets, stream } = setup({ wanted: () => wanted });
    stream.connect();
    wanted = false;
    sockets[0]?.drop(1006);
    // No timer is set for a stream nobody wants, rather than one that fires and does nothing.
    expect(clock.activeTimers()).toBe(0);
    clock.advance(RECONNECT_MS * 5);
    expect(sockets).toHaveLength(1);
    expect(clock.activeTimers()).toBe(0);
  });

  it('cancels a pending reconnect on dispose and closes only its own socket', () => {
    const { clock, sockets, stream } = setup();
    stream.connect();
    sockets[0]?.drop(1006);
    expect(clock.activeTimers()).toBe(1);
    stream.dispose();
    expect(clock.activeTimers()).toBe(0);
    clock.advance(RECONNECT_MS * 5);
    expect(sockets).toHaveLength(1);
    expect(sockets[0]?.closed).toBe(0);
  });

  it('detaches the close handler before closing, so its own close cannot reconnect it', () => {
    const { clock, sockets, stream } = setup();
    stream.connect();
    const socket = sockets[0];
    stream.dispose();
    expect(socket?.closed).toBe(1);
    expect(socket?.onclose).toBeNull();
    socket?.drop(1006);
    clock.advance(RECONNECT_MS * 5);
    expect(sockets).toHaveLength(1);
  });

  it('ignores frames from a socket that has been replaced or disposed', () => {
    const { clock, sockets, stream, terminal } = setup();
    stream.connect();
    sockets[0]?.drop(1006);
    clock.advance(RECONNECT_MS);
    sockets[0]?.deliver(streamed([chunk(1, 'stale')]));
    sockets[1]?.deliver(streamed([chunk(1, 'fresh')]));
    expect(terminal.written).toEqual(['fresh']);
    stream.dispose();
    sockets[1]?.deliver(streamed([chunk(2, 'late')]));
    expect(terminal.written).toEqual(['fresh']);
  });

  it('can be disposed twice and connected again afterwards', () => {
    const { sockets, stream } = setup();
    stream.connect();
    stream.dispose();
    stream.dispose();
    expect(sockets[0]?.closed).toBe(1);
    stream.connect();
    expect(sockets).toHaveLength(2);
  });
});
