import { contextKey } from '../api/identity';
import { isRecord, type Row } from '../observed';
import type { BoardSnapshot } from '../store/board';
import { recordPastWindow, workSource } from '../intent/work';

/* Every id a stored reading cites, whichever criterion cites it. The list the reader's own press may send the
   page to read older record pages for. */
export function citedIdsOf(assessment: Row | null | undefined): string[] {
  const criteria = isRecord(assessment?.['criteria']) ? assessment['criteria'] : {};
  const ids = new Set<string>();
  for (const row of Object.values(criteria)) {
    if (!isRecord(row) || !Array.isArray(row['cites'])) continue;
    for (const id of row['cites']) if (id !== '') ids.add(String(id));
  }
  return [...ids];
}

/* When the pages read for a finished press have done their work: every cited id is one the page holds, or
   the record holds an entry from before the intent's window opened, so nothing in the window is unlisted.
   Read from the store on each call, so a page the reader's own Show more loaded in between counts. */
export function citationsHeld(
  snapshot: BoardSnapshot,
  scope: {
    readonly projectKey: string;
    readonly session: Row;
    readonly cited: readonly string[];
    readonly opened: number | null;
  },
): boolean {
  const record = snapshot.records.get(contextKey(scope.projectKey, scope.session as never));
  if (recordPastWindow(record, scope.opened)) return true;
  const source = workSource(snapshot.contexts, scope.projectKey, scope.session, record);
  const held = new Set((source.all ?? source.entries).map((entry) => entry.id));
  return scope.cited.every((id) => held.has(id));
}
