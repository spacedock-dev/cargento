import { afterEach, describe, expect, it, vi } from 'vitest';
import { choiceOpenIn, installChoiceRelease } from './displayGate';

afterEach(() => {
  document.body.replaceChildren();
});

function page() {
  const root = document.createElement('div');
  const select = document.createElement('select');
  select.append(new Option('a'), new Option('b'));
  const input = document.createElement('input');
  const outside = document.createElement('select');
  root.append(select, input);
  document.body.append(root, outside);
  return { root, select, input, outside };
}

describe('is a native option list possibly open', () => {
  it('is true only while a select inside the page root holds focus', () => {
    const { root, select, input, outside } = page();
    expect(choiceOpenIn(() => root)).toBe(false);
    select.focus();
    expect(choiceOpenIn(() => root)).toBe(true);
    input.focus();
    expect(choiceOpenIn(() => root)).toBe(false);
    outside.focus();
    expect(choiceOpenIn(() => root)).toBe(false);
    expect(choiceOpenIn(() => null)).toBe(false);
  });
});

describe('catching up when the list closes', () => {
  it('releases on a select change and on its blur, once each, and never for another control', () => {
    const { select, input } = page();
    const gate = { releaseChoice: vi.fn(() => true) };
    const remove = installChoiceRelease(document, gate);
    select.dispatchEvent(new Event('change', { bubbles: true }));
    expect(gate.releaseChoice).toHaveBeenCalledTimes(1);
    select.focus();
    select.blur();
    expect(gate.releaseChoice).toHaveBeenCalledTimes(2);
    input.dispatchEvent(new Event('change', { bubbles: true }));
    input.focus();
    input.blur();
    expect(gate.releaseChoice).toHaveBeenCalledTimes(2);
    remove();
    select.dispatchEvent(new Event('change', { bubbles: true }));
    expect(gate.releaseChoice).toHaveBeenCalledTimes(2);
  });
});
