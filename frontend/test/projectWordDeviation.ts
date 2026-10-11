import type { Row } from '../src/observed';

// Only the recorded side changes: new words and the conditional gloss remain asserted on React.
export function renameProjectWords(text: string): string {
  return text
    .replaceAll('PROJECT RECOVERY BRIEFING', 'Where this project stands')
    .replaceAll('STATED GOAL', 'Latest instruction')
    .replaceAll('ASSIGNMENT', 'Current task')
    .replaceAll('EXECUTION', 'Running now')
    .replaceAll('COMMAND', 'Needs you')
    .replaceAll('LATEST EVIDENCE', 'Latest result')
    .replaceAll('FROM YOUR PROMPT · GOAL', 'FROM YOUR PROMPT')
    .replaceAll('YOUR WORDS · GOAL', 'YOUR WORDS')
    .replaceAll('workflow goal', 'workflow instruction')
    .replaceAll(
      'No assignment or workflow instruction published',
      'No task or workflow instruction published',
    )
    .replaceAll('This session published no goal', 'This session published no instruction')
    .replaceAll('no goal.', 'no instruction.');
}

export function projectGlossEnabled(board: Row, project: string): boolean {
  const tripwires = board['tripwires'] as Row | undefined;
  const sessions = Array.isArray(board['sessions']) ? (board['sessions'] as Row[]) : [];
  const identity = (row: Row) =>
    JSON.stringify([String(row['harness'] || ''), String(row['sid'] || '')]);
  // Malformed boards repeat identities; the project's source join takes the last row for each pair.
  const sources = new Map(sessions.map((session) => [identity(session), session]));
  return (
    Boolean(tripwires?.['enabled']) ||
    sessions
      .filter((session) => String(session['project'] || '') === project)
      .some((session) => {
        const workflow = sources.get(identity(session))?.['spacedock'] as Row | undefined;
        return workflow?.['role'] === 'first-officer';
      })
  );
}

export function projectWordDeviation<T>(value: T, gloss: boolean): T {
  if (typeof value === 'string') {
    const text = renameProjectWords(value);
    return (
      gloss
        ? text
        : text.replace(
            'FO is the first officer, the agent driving this workflow; Captain is you.',
            '',
          )
    ) as T;
  }
  if (Array.isArray(value)) return value.map((item) => projectWordDeviation(item, gloss)) as T;
  if (value && typeof value === 'object')
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, projectWordDeviation(item, gloss)]),
    ) as T;
  return value;
}
