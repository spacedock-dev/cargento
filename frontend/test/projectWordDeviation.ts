import type { Row } from '../src/observed';

// Recorded summaries flatten labels and evidence into two UI regions. Mask the
// published values before changing those regions; other fields are never renamed.
export function renameProjectWords(
  text: string,
  gloss: boolean,
  evidence: unknown,
  heading: string,
): string {
  const words = new Set<string>();
  const collect = (value: unknown): void => {
    if (typeof value === 'string' && value) words.add(value.replace(/\s+/g, ' ').trim());
    else if (Array.isArray(value)) value.forEach(collect);
    else if (value && typeof value === 'object')
      Object.entries(value)
        .filter(([key]) => !['owner', 'by', 'type', 'kind', 'role', 'quoted_as'].includes(key))
        .forEach(([, item]) => collect(item));
  };
  collect(evidence);
  const held: string[] = [];
  const affected = [...words].filter((word) =>
    /PROJECT RECOVERY BRIEFING|STATED GOAL|ASSIGNMENT|EXECUTION|COMMAND|LATEST EVIDENCE|YOUR WORDS|FROM YOUR PROMPT|workflow goal|no goal\.|FO|Captain|CAPTAIN|captain|Direction shown in assignment/.test(
      word,
    ),
  );
  const escaped = affected
    .sort((a, b) => b.length - a.length)
    .map((word) => word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  if (escaped.length)
    text = text.replace(
      new RegExp(escaped.join('|'), 'g'),
      (word) => `\uE000${held.push(word) - 1}\uE001`,
    );
  text = text
    .replace('PROJECT RECOVERY BRIEFING', 'Where this project stands')
    .replaceAll(
      'STATED GOAL',
      /This session published no goal|No assignment or workflow goal published/.test(text)
        ? 'Published instruction'
        : heading,
    )
    .replace('ASSIGNMENT', 'Current task')
    .replace('EXECUTION', 'Running now')
    .replace('COMMAND', 'Needs you')
    .replace('LATEST EVIDENCE', 'Latest result')
    .replaceAll('FROM YOUR PROMPT · GOAL', 'Your saved words · from your prompt')
    .replaceAll('YOUR WORDS · GOAL', 'Your saved words')
    .replaceAll(
      'YOUR WORDS · EXPECTED OUTCOME · LINE',
      'Your saved words · expected outcome · line',
    )
    .replaceAll('workflow goal', 'workflow instruction')
    .replaceAll(
      'No assignment or workflow instruction published',
      'No task or workflow instruction published',
    )
    .replaceAll('This session published no goal', 'This session published no instruction')
    .replaceAll('no goal.', 'no instruction.')
    .replaceAll('Direction shown in assignment', 'Direction shown in the current task');
  if (!gloss)
    text = text
      .replace('FO is the first officer, the agent driving this workflow; Captain is you.', '')
      .replaceAll('CAPTAIN NEEDED', 'NEEDS YOU')
      .replaceAll('FO INSPECTING', 'CHECKING')
      .replaceAll(
        'FO CONTINUES · Continue current assignment',
        'CONTINUES · Continue the current task',
      )
      .replaceAll('FO CONTINUES', 'CONTINUES')
      .replaceAll('Captain not needed', 'You are not needed')
      .replaceAll('Captain state unknown', 'Your attention is unknown')
      .replaceAll('Captain attention unavailable', 'Attention unavailable')
      .replaceAll('captain-attention scan', 'attention scan')
      .replaceAll('CAPTAIN ·', 'YOU ·')
      .replaceAll('FO ·', 'AGENT ·')
      .replaceAll('more FO ', 'more ');
  return text.replace(/\uE000(\d+)\uE001/g, (_match, index: string) => held[Number(index)] ?? '');
}

export function projectInstructionHeading(
  board: Row,
  project: string,
  focus: Row | null = null,
): string {
  const sessions = Array.isArray(board['sessions']) ? (board['sessions'] as Row[]) : [];
  const identity = (row: Row) =>
    JSON.stringify([String(row['harness'] || ''), String(row['sid'] || '')]);
  const sources = new Map(sessions.map((row) => [identity(row), row]));
  const candidates = (
    focus ? [focus] : sessions.filter((row) => String(row['project'] || '') === project)
  ).flatMap((original) => {
    const row = sources.get(identity(original)) ?? original;
    const instruction = row['instruction'] as Row | undefined;
    const copied =
      Array.isArray(row['copied_prompts']) &&
      (row['copied_prompts'] as Row[]).some(
        (entry) =>
          entry && Array.isArray(entry['quoted_as']) && entry['quoted_as'].includes('instruction'),
      );
    if (
      instruction?.['label'] === 'asked' &&
      typeof instruction['text'] === 'string' &&
      instruction['text'].trim() &&
      !copied
    )
      return [
        {
          at:
            typeof instruction['at'] === 'number' && Number.isFinite(instruction['at'])
              ? instruction['at']
              : null,
        },
      ];
    const spacedock = row['spacedock'] as Row | undefined;
    return Array.isArray(spacedock?.['workflows']) &&
      (spacedock['workflows'] as Row[]).some(
        (workflow) => workflow && typeof workflow['goal'] === 'string' && workflow['goal'].trim(),
      )
      ? [{ at: null }]
      : [];
  });
  return candidates.length && candidates.every((candidate) => candidate.at !== null)
    ? 'Latest instruction'
    : 'Published instruction';
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

export function projectWordDeviation<T>(
  value: T,
  gloss: boolean,
  evidence: unknown = {},
  heading = 'Latest instruction',
): T {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return value;
  const summary = value as Record<string, unknown>;
  return Object.fromEntries(
    Object.entries(summary).map(([key, item]) => {
      if (key === 'strip' && typeof item === 'string')
        return [key, renameProjectWords(item, gloss, evidence, heading)];
      if (key === 'disclosures' && Array.isArray(item))
        return [
          key,
          item.map((disclosure) => ({
            ...disclosure,
            body:
              disclosure.summary === 'Evidence · attention sources'
                ? renameProjectWords(disclosure.body, gloss, evidence, heading)
                : disclosure.body,
          })),
        ];
      return [key, item];
    }),
  ) as T;
}
