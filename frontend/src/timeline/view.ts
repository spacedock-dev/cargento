import type { SessionIdentity } from '../api/types';
import {
  buildRegistry,
  readSemantic,
  withCanonicalLabels,
  type Delegation,
  type Registry,
  type SemanticModel,
} from './semantic';

export interface TimelineView {
  readonly model: SemanticModel;
  readonly registry: Registry;
  /** The focused session as the registry reads it, with its state. Null at project scope. */
  readonly focus: (SessionIdentity & { readonly state?: string }) | null;
}

interface RawContext {
  readonly semantic?: unknown;
}

export interface ViewInput {
  /** The focused (or project) context body, exactly as the server sent it. */
  readonly data: unknown;
  /** The project-wide context body, which is canonical for work item labels. */
  readonly projectData: unknown;
  readonly focusHarness: string | null;
  readonly focusSid: string | null;
  readonly focusState: string | null;
  readonly sessions: readonly SessionIdentity[];
  readonly delegations: readonly Delegation[] | undefined;
}

export function deriveView(input: ViewInput): TimelineView {
  const raw = (input.data ?? {}) as RawContext;
  const project = (input.projectData ?? null) as RawContext | null;
  const model = withCanonicalLabels(
    readSemantic(raw.semantic ?? {}),
    project?.semantic !== undefined ? readSemantic(project.semantic) : null,
  );
  const focus =
    input.focusHarness !== null && input.focusSid !== null
      ? {
          harness: input.focusHarness,
          sid: input.focusSid,
          ...(input.focusState ? { state: input.focusState } : {}),
        }
      : null;
  const registry = buildRegistry({
    model,
    ...(input.delegations ? { delegations: input.delegations } : {}),
    focus,
    origins: input.sessions,
    fallbackSession: focus ? `${focus.harness}:${focus.sid}` : '',
  });
  return { model, registry, focus };
}
