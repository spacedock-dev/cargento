/* Test doubles for the terminal: a socket that records what a client could do to it, a renderer that
   writes into a real element, and a scroll container that clamps as a browser does. Not imported by
   production code. */
import type { StreamSocket } from './stream';
import type { XtermLike, XtermOptions } from './xterm';

export class FakeSocket implements StreamSocket {
  onmessage: StreamSocket['onmessage'] = null;
  onclose: StreamSocket['onclose'] = null;
  closed = 0;
  sent = 0;
  close(): void {
    this.closed += 1;
  }
  /* Not part of the interface the owner is written against: a call to it is the failure under test. */
  send(): never {
    this.sent += 1;
    throw new Error('the terminal socket is output-only');
  }
  deliver(frame: unknown): void {
    this.onmessage?.({ data: JSON.stringify(frame) });
  }
}

export const instances: FakeXterm[] = [];

export class FakeXterm implements XtermLike {
  cols = 80;
  rows = 24;
  element: HTMLElement | undefined;
  textarea: HTMLTextAreaElement | undefined;
  buffer = { active: { cursorY: 0 } };
  written: string[] = [];
  opened: HTMLElement | null = null;
  disposed = false;
  readonly options: XtermOptions;
  constructor(options: XtermOptions) {
    this.options = options;
    instances.push(this);
  }
  open(host: HTMLElement): void {
    this.opened = host;
    const element = document.createElement('div');
    element.className = 'xterm';
    const screen = document.createElement('div');
    screen.className = 'xterm-screen';
    screen.getBoundingClientRect = () => ({ width: 640, height: 480 }) as DOMRect;
    this.textarea = document.createElement('textarea');
    element.append(screen, this.textarea);
    this.element = element;
    host.append(element);
  }
  write(data: string, done?: () => void): void {
    this.written.push(data);
    done?.();
  }
  writeln(data: string): void {
    this.written.push(data + '\n');
  }
  resize(cols: number, rows: number): void {
    this.cols = cols;
    this.rows = rows;
  }
  reset(): void {
    this.written = [];
  }
  dispose(): void {
    this.disposed = true;
  }
}

/* A scroll container that clamps as a browser does and whose size the test sets. */
export function viewportElement(scrollHeight = 492, clientHeight = 340): HTMLDivElement {
  const element = document.createElement('div');
  let top = 0;
  const size = { scrollHeight, clientHeight };
  Object.defineProperties(element, {
    scrollHeight: { get: () => size.scrollHeight, configurable: true },
    clientHeight: { get: () => size.clientHeight, configurable: true },
    scrollTop: {
      get: () => top,
      set: (value: number) => {
        top = Math.max(0, Math.min(value, Math.max(0, size.scrollHeight - size.clientHeight)));
      },
      configurable: true,
    },
  });
  return element;
}

