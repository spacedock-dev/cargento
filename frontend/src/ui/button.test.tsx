import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { Button, buttonVariants } from './button';

it('keeps a pending button in the tab order and blocks repeated activation', () => {
  const press = vi.fn();
  const view = render(<Button onClick={press}>Save</Button>);
  const button = screen.getByRole('button');
  fireEvent.click(button);
  view.rerender(
    <Button aria-busy aria-disabled busyLabel="Saving…" onClick={press}>
      Save
    </Button>,
  );
  button.focus();
  for (const detail of [1, 0, 0]) fireEvent.click(button, { detail });
  expect(press).toHaveBeenCalledTimes(1);
  expect(button.hasAttribute('disabled')).toBe(false);
  expect(button.getAttribute('aria-disabled')).toBe('true');
  expect(button.getAttribute('aria-busy')).toBe('true');
  expect(button.tabIndex).toBe(0);
  expect(document.activeElement).toBe(button);
});

it('keeps a styled anchor a link with its destination', () => {
  render(
    <a href="#n=sessions" className={buttonVariants()}>
      Sessions
    </a>,
  );
  expect(screen.getByRole('link', { name: 'Sessions' }).getAttribute('href')).toBe('#n=sessions');
  expect(screen.queryByRole('button')).toBeNull();
});

it('leaves shell navigation keys uncancelled while pending and refuses activation keys', () => {
  const press = vi.fn();
  render(
    <Button aria-busy aria-disabled onClick={press}>
      Save
    </Button>,
  );
  const button = screen.getByRole('button');
  button.focus();
  for (const key of ['Escape', 'a', 'p', 's', 'Tab']) {
    const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true });
    fireEvent(button, event);
    expect(event.defaultPrevented, key).toBe(false);
  }
  for (const key of ['Enter', ' ']) {
    const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true });
    fireEvent(button, event);
    expect(event.defaultPrevented, key).toBe(true);
    fireEvent.keyUp(button, { key });
  }
  fireEvent.click(button);
  expect(press).not.toHaveBeenCalled();
});

it('keeps the native role of a tab or switch', () => {
  render(
    <>
      <Button role="tab" aria-selected>
        Now
      </Button>
      <Button role="switch" aria-checked>
        Monitor
      </Button>
    </>,
  );
  expect(screen.getByRole('tab', { name: 'Now' }).getAttribute('aria-selected')).toBe('true');
  expect(screen.getByRole('switch', { name: 'Monitor' }).getAttribute('aria-checked')).toBe('true');
});
