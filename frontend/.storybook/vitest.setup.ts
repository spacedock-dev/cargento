import { afterEach, beforeEach, expect } from 'vitest';
import { commands } from 'vitest/browser';

declare module 'vitest/browser' {
  interface BrowserCommands {
    storyGuard(): Promise<string>;
    storyResult(): Promise<string[]>;
  }
}
beforeEach(async () => {
  const css = await commands.storyGuard();
  if (!document.getElementById('story-fonts')) {
    const style = document.createElement('style');
    style.id = 'story-fonts';
    style.textContent = css;
    document.head.append(style);
  }
});
afterEach(async () => {
  expect(
    await commands.storyResult(),
    'Every story renders offline without console or page errors',
  ).toEqual([]);
});
