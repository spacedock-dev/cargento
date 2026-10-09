import type { Row } from '../observed/values';
import type { ProjectModel } from './model';

/** The project-scope context data the plan and the strip read, or null before one arrived. */
export function semanticObservation(model: ProjectModel): Row | null {
  return model.env.entry?.data ?? null;
}
