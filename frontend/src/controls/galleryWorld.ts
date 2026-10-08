/* The gallery's wiring, built the way the shell builds it: from props, with a recording clipboard so
   a browser test never touches the real one. */
import { createBrowserRuntime } from '../transport/browser';
import type { Clock } from '../transport/ports';
import { choiceOpenIn, createDisplayGate } from './displayGate';
import { createControls } from './kit';

const clock: Clock = {
  now: () => Date.now(),
  setTimeout: (callback, ms) => window.setTimeout(callback, ms),
  clearTimeout: (handle) => window.clearTimeout(handle as number),
  setInterval: (callback, ms) => window.setInterval(callback, ms),
  clearInterval: (handle) => window.clearInterval(handle as number),
};

export interface Hooks {
  announced: { key: string; text: string }[];
  copied: string[];
}

export function createWorld(hooks: Hooks) {
  const gate = createDisplayGate({
    clock,
    reducedMotion: () => window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    isChoiceOpen: () => choiceOpenIn(() => document.getElementById('gallery')),
  });
  const announce = (key: string, text: string) => {
    hooks.announced.push({ key, text });
    const region = document.getElementById('gallery-live');
    if (region) region.textContent = text;
  };
  const runtime = createBrowserRuntime({ paint: gate.paint, announce });
  gate.attach(runtime.store);
  const controls = createControls({
    clock,
    announce,
    memo: runtime.storage.memo,
    // A recording stand-in: a browser test never touches the real clipboard.
    clipboard: () => ({
      writeText: (text: string) => {
        hooks.copied.push(text);
        return Promise.resolve();
      },
    }),
    focus: (identity) => runtime.focus(identity),
    noteToggle: () => gate.noteToggle(),
  });
  return { gate, runtime, controls };
}

export type World = ReturnType<typeof createWorld>;

