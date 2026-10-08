import { payloadSessions } from '../api/bootstrap';
import { stableProjectKey } from '../api/identity';
import type { SessionIdentity } from '../api/types';
import type { Row } from '../observed';
import type { Shell } from '../shell/context';
import { readInput } from './context';
import { adoption, intentDraft, intentDrafted, intentUnsaved, type Draft } from './derive';
import { openDirection } from './directions';
import { addLine } from './edit';
import { forgetAdopted } from './save';
import { intentCtxFor } from './useIntent';
import { entryNumbers, workSource } from './work';

/* What the Analyze step reads from, and writes to, the Intent step. Every function takes the shell and an
   exact harness and sid, never a display id, and none of them starts a request except where its name says
   it opens something for the reader to review. */

function projectKeyOf(shell: Shell, row: Row): string {
  const data = shell.runtime.store.getSnapshot().data;
  const label = String(row['project'] == null ? '' : row['project']);
  return stableProjectKey({
    label,
    sessions: data
      ? payloadSessions(data).rows.filter((candidate) => String(candidate.project ?? '') === label)
      : [],
  });
}

/* "Update intent instead", pressed on an analysis result: the offered direction opens as the pending line
   through Add's own path, so the reader reviews and saves it as one outcome line, and the goal is never
   touched. With no direction to offer it opens an empty line instead. The press sends one request, to read
   the direction whole through `POST /api/direction`; it saves nothing, and a second press while a line is
   pending focuses that line and changes nothing.

   Resolves when the line is drawn, or when the direction could not be opened and the reason is on screen. */
export async function openPendingDirection(
  shell: Shell,
  identity: SessionIdentity,
  factId: string | null,
): Promise<void> {
  const ctx = intentCtxFor(shell);
  const input = readInput(ctx, identity);
  if (!input) return;
  if (!factId) {
    addLine(ctx, input);
    return;
  }
  const source = workSource(input.contexts, projectKeyOf(shell, input.session), input.session);
  const n = entryNumbers(input.session, source, input.payload).get(factId);
  await openDirection(ctx, input.session, factId, n ?? null, true, 'update-intent');
}

/* What a request to read the session carries when the reader has not saved the goal it would read: the
   adoption of the drafted or chosen prompt, or nothing. A reading never starts from words that are not on
   screen, so `unsaved` says the press must be refused first. */
export function intentForReading(shell: Shell, identity: SessionIdentity) {
  const ctx = intentCtxFor(shell);
  const input = readInput(ctx, identity);
  if (!input) return null;
  const draft: Draft | null = intentDraft(input);
  return {
    /** The reader has words in a box that the store does not hold. */
    unsaved: intentUnsaved(input),
    /** The goal is a prompt drafted or chosen and not yet saved. */
    drafted: intentDrafted(input),
    draft,
    /** The adoption fields a reading request names, or none. */
    adoption: adoption(draft),
    /** After a reading that adopted the draft was accepted, the held goal goes only while it still equals it. */
    forgetAdopted: () => forgetAdopted(ctx, input.session, draft),
  };
}
