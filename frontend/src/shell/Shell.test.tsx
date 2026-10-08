import { act } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { REGION_IDS } from './announcer';
import { BOARD, flush, mountShell } from './testing';

const region = (name: keyof typeof REGION_IDS) => document.getElementById(REGION_IDS[name])?.textContent;

describe('the shell wires the runtime, the announcer and the controls to one another', () => {
  it('says a slow pending control’s start sentence in the polite region, once, and again for the next press', async () => {
    const page = mountShell({ data: BOARD });
    await page.settle();
    const first = page.shell.runtime.pending.start('save:goal', 'Saving', 'Saving the goal.');
    act(() => page.clock.advance(400));
    expect(region('cue')).toBe('Saving the goal.');
    act(() => {
      page.shell.runtime.pending.end('save:goal', first);
    });
    // The guard was forgotten with the entry, so the next press's sentence is spoken, not suppressed.
    act(() => {
      const cue = document.getElementById(REGION_IDS.cue);
      if (cue) cue.textContent = '';
    });
    page.shell.runtime.pending.start('save:goal', 'Saving', 'Saving the goal.');
    act(() => page.clock.advance(400));
    expect(region('cue')).toBe('Saving the goal.');
  });

  it('says nothing for a pending control that answers inside the cue delay', async () => {
    const page = mountShell({ data: BOARD });
    await page.settle();
    const token = page.shell.runtime.pending.start('save:goal', 'Saving', 'Saving the goal.');
    act(() => page.clock.advance(399));
    page.shell.runtime.pending.end('save:goal', token);
    act(() => page.clock.advance(1000));
    expect(region('cue')).toBe('');
  });

  it('sends a copy or raise control’s sentence to its own region and anything else to the guarded cue region', async () => {
    const page = mountShell({ data: BOARD });
    await page.settle();
    act(() => {
      page.shell.controls.announce('copy:id:claude:s#1', 'Copied session ID s');
      page.shell.controls.announce('raise:claude:s#2', 'Raise requested');
      page.shell.controls.announce('briefing:p#3', 'Copied the project briefing');
    });
    expect(region('copy')).toBe('Copied session ID s');
    expect(region('raise')).toBe('Raise requested');
    expect(region('cue')).toBe('Copied the project briefing');
    expect(region('attention')).toBe('');
    expect(region('alert')).toBe('');
  });

  it('offers a terminal raise only when the served document carries the run’s capability', async () => {
    const off = mountShell({ data: BOARD });
    await off.settle();
    expect(off.shell.controls.focus).toBeNull();
    off.unmount();
    const on = mountShell({ data: BOARD, focusCapability: 'abcdef' });
    await on.settle();
    expect(on.shell.controls.focus).not.toBeNull();
    expect(on.posts()).toBe(0);
  });

  it('shows a board only through the display gate, so a paint the runtime asks for is the one the reader sees', async () => {
    const page = mountShell({ data: BOARD });
    expect(page.shell.display.getSnapshot().data).toBeNull();
    await page.settle();
    expect(page.shell.display.getSnapshot().data).not.toBeNull();
    expect(page.shell.display.getSnapshot().acceptedCount).toBe(page.shell.runtime.store.getSnapshot().acceptedCount);
  });

  it('starts exactly one runtime and releases it when the page leaves, whatever StrictMode did meanwhile', async () => {
    const page = mountShell({ data: BOARD, strict: true });
    await page.settle();
    expect(page.shell.runtime.store.subscriberCount()).toBeGreaterThan(0);
    page.unmount();
    await act(async () => {
      page.clock.advance(1);
    });
    expect(page.env.openStreams()).toBe(0);
  });
});

describe('a disclosure the reader just toggled holds a background paint for its motion', () => {
  it('keeps the shown board for the 220 ms a disclosure eases, then shows the newest one', async () => {
    const page = mountShell({ data: BOARD });
    await page.settle();
    const shown = () => page.shell.display.getSnapshot().data?.generated;
    expect(shown()).toBe(1000);
    // The shared controls tell the gate through the same call a Disclosure makes on its summary's click.
    page.shell.controls.noteToggle();
    page.backend.data = { ...BOARD, generated: 2000 };
    void page.shell.runtime.refresh();
    await act(async () => void (await flush()));
    expect(page.shell.runtime.store.getSnapshot().data?.generated).toBe(2000);
    expect(shown()).toBe(1000);
    await act(async () => {
      page.clock.advance(219);
      await flush();
    });
    expect(shown()).toBe(1000);
    await act(async () => {
      page.clock.advance(1);
      await flush();
    });
    expect(shown()).toBe(2000);
  });
});

describe('an open native list holds a poll paint, and closing it shows the board', () => {
  it('keeps the shown board while a select inside the page holds focus, then catches up on blur', async () => {
    const page = mountShell({ data: BOARD });
    await page.settle();
    const shown = () => page.shell.display.getSnapshot().data?.generated;
    const select = document.createElement('select');
    select.append(new Option('one'), new Option('two'));
    document.getElementById('app')?.append(select);
    select.focus();
    expect(document.activeElement).toBe(select);
    page.backend.data = { ...BOARD, generated: 2000 };
    await act(async () => {
      await page.shell.runtime.refresh();
    });
    expect(page.shell.runtime.store.getSnapshot().data?.generated).toBe(2000);
    expect(shown()).toBe(1000);
    await act(async () => {
      select.blur();
      await flush();
    });
    expect(shown()).toBe(2000);
    select.remove();
  });

  it('does not hold a poll for a select outside the page, which cannot be the reader’s choice', async () => {
    const page = mountShell({ data: BOARD });
    await page.settle();
    const outside = document.createElement('select');
    outside.append(new Option('one'));
    document.body.append(outside);
    outside.focus();
    page.backend.data = { ...BOARD, generated: 2000 };
    await act(async () => {
      await page.shell.runtime.refresh();
    });
    expect(page.shell.display.getSnapshot().data?.generated).toBe(2000);
    outside.remove();
  });
});
