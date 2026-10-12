import type { WorkSource } from '../src/intent/work';
import type { Row } from '../src/observed';
import { formatDuration } from '../src/shell/format';

// The recording keeps the full numbered source, even where its HTML capped rows. This projection
// restores only those omitted rows from that recorded source, and retires only the old cap caption.
// docs/design-frontend-migration.md#activity-list-order records the changed contract.
export function projectRecordedLoadedActivity(
  html: string,
  source: WorkSource,
  session: Row,
  payload: Row,
  cited: ReadonlySet<string>,
  baseline: number | null,
): string {
  const panel = document.createElement('div');
  panel.innerHTML = html;
  const rows = panel.querySelector('.next-cockpit-work-rows');
  if (!rows) return panel.innerHTML;
  const all = source.all ?? source.entries;
  const opened =
    payload['annotate'] === true && Number(session['annotation_window_start']) > 0
      ? Number(session['annotation_window_start'])
      : null;
  const numbered = all.filter(
    (entry) =>
      Number.isFinite(Number(entry.at)) &&
      Number(entry.at) > 0 &&
      (opened === null || Number(entry.at) >= opened),
  );
  const existing = new Map(
    [...rows.querySelectorAll<HTMLElement>('[data-next-entry-id]')].map((row) => [
      row.dataset['nextEntryId'],
      row,
    ]),
  );
  const person = (entry: (typeof all)[number]) =>
    entry.type === 'user_message'
      ? !entry.copied
      : entry.type === 'gate_decision' && entry.by.startsWith('person:');
  const starts = all
    .filter(person)
    .map((entry) => Number(entry.at))
    .filter((at) => Number.isFinite(at) && at > 0 && at <= Number(session['turn_end_at']));
  const from = starts.length
    ? Math.max(Number(session['annotation_window_start']), ...starts)
    : null;
  const kinds = new Map([
    ['prepared_dispatch', 'Dispatch'],
    ['work_birth', 'Task started'],
    ['work_result', 'Task result'],
    ['result', 'Result'],
    ['gate_decision', 'Gate'],
    ['decision', 'Decision'],
    ['assignment', 'Assignment'],
    ['stage_transition', 'Stage'],
    ['agent_message', 'said'],
  ]);
  const drawn: HTMLElement[] = [];
  for (const entry of all) {
    const held = existing.get(entry.id);
    if (held) {
      drawn.push(held);
      continue;
    }
    const index = numbered.indexOf(entry);
    if (index < 0) continue;
    // Checks never took the retired cap, so only message/workflow row words are reconstructed.
    if (entry.type === 'tool_report') throw new Error('A recorded listed check disappeared.');
    const copied = entry.type === 'user_message' && entry.copied;
    const actor =
      person(entry) || copied
        ? 'You'
        : entry.type === 'observer_snapshot'
          ? 'Compass’s summary'
          : 'Agent';
    const kind = copied
      ? 'Copied from Compass'
      : entry.type === 'user_message'
        ? 'Prompt'
        : (kinds.get(entry.type) ?? 'Entry');
    const later = person(entry) && baseline !== null && Number(entry.at) > baseline;
    const age = formatDuration(Math.max(0, Number(payload['generated']) - Number(entry.at)));
    const turn =
      session['harness'] === 'claude' &&
      session['state'] === 'idle' &&
      !session['ended_at'] &&
      from !== null &&
      Number(entry.at) >= from &&
      Number(entry.at) <= Number(session['turn_end_at']) &&
      !person(entry);
    const sourceText =
      (entry.source || 'Source not published') +
      (entry.actorClaim && !entry.source.includes(entry.actorClaim)
        ? ` · ${entry.actorClaim}`
        : '');
    const row = document.createElement('div');
    row.dataset['nextEntryId'] = entry.id;
    row.textContent = [
      `#${String(index + 1)}`,
      actor + kind,
      later ? 'A later direction you gave' : '',
      cited.has(entry.id) ? 'Cited' : '',
      entry.summary,
      sourceText,
      `${age} ago`,
      turn ? 'from the last turn' : '',
      later ? 'Add to my intent' : '',
    ].join('');
    drawn.push(row);
  }
  rows.replaceChildren(...drawn);
  panel.querySelector('.next-cockpit-work-dropped')?.remove();
  return panel.innerHTML;
}
