import { useSyncExternalStore } from 'react';
import { useShell } from '../shell/context';
import { projectChanges, projectWindow, type ProjectChanges, type Workstream } from './model';
import { startWorkstream } from './store';

/* A project's changes are derived once per version of the tab's evidence and handed back as the same
   object until the evidence advances, which is what `useSyncExternalStore` needs and what keeps a render
   that changed nothing from deriving them again. */
const derived = new WeakMap<
  Workstream,
  Map<string, { readonly version: number; readonly changes: ProjectChanges }>
>();

export function changesOf(buffer: Workstream, project: string): ProjectChanges {
  let byProject = derived.get(buffer);
  if (!byProject) {
    byProject = new Map();
    derived.set(buffer, byProject);
  }
  const version = buffer.version();
  const held = byProject.get(project);
  if (held && held.version === version) return held.changes;
  const changes = projectChanges(projectWindow(project, buffer.snapshot()));
  byProject.set(project, { version, changes });
  return changes;
}

/** The changes of one project, derived from the tab's evidence. The Course tab's count rides the same figure. */
export function useProjectChanges(project: string): ProjectChanges {
  const { runtime } = useShell();
  const buffer = startWorkstream(runtime);
  return useSyncExternalStore(buffer.subscribe, () => changesOf(buffer, project));
}
