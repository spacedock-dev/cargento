import {
  annotationLines,
  revisionLine,
  type Annotation,
  type OutcomeLine,
} from '../intent/annotation';
import type { ObservedProject, ObservedSession } from '../observed';
import { durationSince } from '../observed/values';
import { PROMPT_SOURCES } from '../sessions/intent';

/* STATED GOAL is a list, not a field: zero to n rows, each with its own tag and its own source line. The
   reader's typed words are rows above the harness's, never merged with them, because "what I asked for"
   and "what the harness published" are different claims and one string cannot carry both. Ported from
   `nextProjectGoal` and the helpers around it. */

export interface GoalScope {
  readonly text: string;
  readonly known: boolean;
  readonly src: string;
  readonly at: number | null;
}

/* Whose derived goal this is. A focused session answers for itself; with none, the project answers for the
   group, and that goal is whichever session moved most recently. Pairing it with one session's typed words
   would put another session's directive under DERIVED FROM THE HARNESS. */
export function goalScope(project: ObservedProject, focus: ObservedSession | null): GoalScope {
  return focus
    ? {
        text: focus.ownGoalText,
        known: focus.ownGoalKnown,
        src: focus.ownGoalSrcText,
        at: focus.ownGoalAt,
      }
    : {
        text: project.goalText,
        known: project.goalKnown,
        src: project.goalSrcText,
        at: project.goalAt,
      };
}

/** "Spacedock · workflow goal · observed 4m ago": the source, with when the directive was observed. */
export function derivedSource(scope: GoalScope, generated: number | null): string {
  if (!scope.known) return '';
  const age = scope.at === null ? null : durationSince(generated, scope.at);
  return `${scope.src} · ${age === null ? 'observation time not published' : `observed ${age} ago`}`;
}

export interface GoalRow {
  readonly tag: string;
  readonly text: string;
  readonly source: string;
  readonly known: boolean;
}

export interface Goal {
  readonly scope: GoalScope;
  /** The reader's own words, then the outline lines, each with the revision they were saved at. */
  readonly typed: readonly GoalRow[];
  readonly derivedSource: string;
  /** The binding sentence: another session sharing a prefixed id would share these words. Only where there are words for it to be about. */
  readonly binding: string;
  /** A count across the project's sessions: beside one session's typed words it answers a question not asked. */
  readonly gap: string;
}

export function projectGoal(
  project: ObservedProject,
  annotation: Annotation | null,
  focus: ObservedSession | null,
  generated: number | null,
): Goal {
  const scope = goalScope(project, focus);
  const revision = revisionLine(annotation, generated);
  const typed: GoalRow[] = [];
  if (annotation?.['goal']) {
    typed.push({
      tag: PROMPT_SOURCES.includes(annotation['goal_source'] as string)
        ? 'FROM YOUR PROMPT · GOAL'
        : 'YOUR WORDS · GOAL',
      text: String(annotation['goal']),
      source: revision,
      known: true,
    });
  }
  const lines: OutcomeLine[] = annotationLines(annotation);
  for (const line of lines) {
    typed.push({
      tag: `YOUR WORDS · EXPECTED OUTCOME · LINE ${String(line.k)}`,
      text: line.text,
      source: revision,
      known: true,
    });
  }
  const why = annotation?.['binding_why'];
  return {
    scope,
    typed,
    derivedSource: derivedSource(scope, generated),
    binding: why && (annotation?.['goal'] || lines.length) ? String(why) : '',
    gap: !focus && project.goalGapKnown ? project.goalGapText : '',
  };
}
