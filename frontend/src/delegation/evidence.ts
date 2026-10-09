import { useSyncExternalStore } from 'react';
import { useShell } from '../shell/context';
import { projectWindow, startWorkstream, type ProjectWindow, type Workstream } from '../workstream';

/* The delegation figure is measured over the workstream's evidence: the tab's own observations and the
   history store's replay, appended to by every payload the board accepts (`startWorkstream`, which the shell
   calls when it is built, so the window reaches back to the first payload and not to the first time a
   Console opened). A window is derived once per version of that evidence and handed back as the same object
   until it advances, which is what `useSyncExternalStore` needs and what keeps the figure from being
   recomputed by a render that changed nothing. */
const windows = new WeakMap<
  Workstream,
  Map<string, { readonly version: number; readonly window: ProjectWindow }>
>();

function windowOf(memory: Workstream, project: string): ProjectWindow {
  let byProject = windows.get(memory);
  if (!byProject) {
    byProject = new Map();
    windows.set(memory, byProject);
  }
  const version = memory.version();
  const held = byProject.get(project);
  if (held && held.version === version) return held.window;
  const window = projectWindow(project, memory.snapshot());
  byProject.set(project, { version, window });
  return window;
}

/* One project's window over that evidence. The evidence is appended to as a payload is ACCEPTED, so this can
   be a step ahead of the board shown while a native list holds a poll back, as the legacy page's figure is. */
export function useProjectWindow(project: string): ProjectWindow {
  const { runtime } = useShell();
  const memory = startWorkstream(runtime);
  return useSyncExternalStore(memory.subscribe, () => windowOf(memory, project));
}
