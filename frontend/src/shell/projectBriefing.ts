import { useCallback } from 'react';
import { BriefingUnavailable } from '../controls/briefingUnavailable';
import { useControls } from '../controls/kit';
import { briefingOf, noteKey, useProjectModel } from '../project/model';
import type { ProjectRoute } from '../router/grammar';

export interface ProjectBriefing {
  /** Read only inside the press that copies it: a briefing is never built on a render. */
  readonly briefingText: () => string;
  /** The memo key the menu's "Add human context" opens, present only while the note is empty and the briefing complete. */
  readonly addHumanContext: { readonly memoKey: string } | null;
}

/* The project briefing is built from the rows the project page draws, by the same function, so what the
   menu copies is what the strip says. It is built inside the press and never on a render, because a render
   must write nothing and send nothing. A project the board no longer holds has no briefing to copy, and the
   press says so rather than copying an empty string and calling it a briefing: the thrown BriefingUnavailable
   reaches the More menu as "Copy unavailable".

   The menu offers "Add human context" only where the strip does not already: both notes empty and the
   briefing complete (a task is known and the attention scan finished), so the same words are never said
   twice and never missing. */
export function useProjectBriefing(route: ProjectRoute): ProjectBriefing {
  const model = useProjectModel(route);
  const controls = useControls();
  const read = useCallback((key: string) => controls.memo.read(key), [controls]);
  const briefingText = useCallback(() => {
    if (!model) throw new BriefingUnavailable('The project is not in the current payload.');
    return briefingOf(model, read).text;
  }, [model, read]);
  let addHumanContext: ProjectBriefing['addHumanContext'] = null;
  if (model && !model.focus) {
    const briefing = briefingOf(model, read);
    const empty = briefing.outcome === 'Not set' && briefing.currentFocus === 'Not set';
    if (empty && briefing.task.known && briefing.coverage.state === 'complete')
      addHumanContext = { memoKey: noteKey(model, 'outcome') };
  }
  return { briefingText, addHumanContext };
}
