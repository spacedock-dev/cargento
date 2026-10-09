import { humanLabel } from './group';
import type { Lane } from './lanes';
import { field, fieldText, isRecord, list, record, text, type Row } from './raw';
import { factSetScope, type Scope } from './scope';
import { readingCopied } from './recovery';

/* The Course tab: the direction changes the board observed in the session record, as episodes, each
   saying what kind of evidence it rests on. An episode is exact (a recorded decision, a stage change, a
   completed result) or derived (a review that changed the course), and never promoted past that: a review
   is not a verified success, and the badge on it says "derived". Ported from `next-cockpit.js`. */

export interface CompletedResult {
  readonly fact: Row;
  readonly checkpoint: string;
}

/* The newest result whose first line says it is fixed, completed or done, and live, with the checkpoint it
   names. Both conditions are needed: "Fixed" alone is a claim about the work, not about where it landed. */
export function latestCompletedResult(semantic: unknown): CompletedResult | null {
  const facts = list(field(semantic, 'facts'));
  const results = facts
    .filter((fact): fact is Row => isRecord(fact) && fact['type'] === 'result')
    .sort((left, right) => Number(right['at'] || 0) - Number(left['at'] || 0));
  for (const fact of results) {
    const detail = String(fact['detail'] || fact['summary'] || '');
    const firstLine = detail.trimStart().split(/\r?\n/, 1)[0] ?? '';
    if (!/^(?:fixed|completed|done)\b.*\blive\b/i.test(firstLine)) continue;
    const checkpoint = /(?:checkpoint\s*:?\s*|\bat\s+)`?([0-9a-f]{7,40})`?/i.exec(detail);
    if (checkpoint) return { fact, checkpoint: checkpoint[1] as string };
  }
  return null;
}

/** The findings a review listed under "Review changed the course:", bullet by bullet. */
export function reviewFindings(detail: unknown): string[] {
  const lines = String(detail || '').split(/\r?\n/);
  let collecting = false;
  const findings: string[] = [];
  for (const raw of lines) {
    const line = raw
      .replace(/^\s*\d+\.\s*/, '')
      .replace(/\*\*/g, '')
      .trim();
    if (/^review changed the course\s*:/i.test(line)) {
      collecting = true;
      continue;
    }
    if (!collecting) continue;
    const bullet = /^[-*]\s+(.+)/.exec(line);
    if (bullet) {
      findings.push((bullet[1] as string).trim());
      continue;
    }
    if (line) break;
  }
  return findings;
}

/** The semantic read with each work item's label taken from the project-scope read, so a focused read cannot relabel a task. */
export function canonicalSemantic(projectSemantic: Row, semantic: Row): Row {
  const labels = new Map(
    list(projectSemantic['work_items'])
      .filter(isRecord)
      .map((item) => [String(item['work_item_id'] || ''), String(item['label'] || '')] as const),
  );
  return {
    ...semantic,
    work_items: list(semantic['work_items'])
      .filter(isRecord)
      .map((item) => {
        const label = labels.get(String(item['work_item_id'] || ''));
        return label ? { ...item, label } : item;
      }),
  };
}

export interface EvidenceModel {
  /** What is missing, said before anything is claimed. */
  readonly missing: readonly string[];
  /** Null when there is nothing to disclose: no source, no confidence, no identity and no contributors. */
  readonly details: {
    readonly key: string;
    readonly source: string;
    readonly confidence: string;
    readonly identity: string;
    readonly contributors: readonly string[];
  } | null;
}

const KNOWN = /^(?:(?:source|confidence) )?(?:unavailable|unknown)$/i;

export function courseEvidence(
  fact: Row,
  contributors: readonly string[],
  occurrence = '',
): EvidenceModel {
  const evidence = field(fact, 'evidence');
  const source = String(fieldText(evidence, 'source') || fact['source_kind'] || '').trim();
  const confidence = String(fieldText(evidence, 'confidence') || '').trim();
  const identity = String(fact['fact_id'] || '').trim();
  const known = (value: string) => Boolean(value) && !KNOWN.test(value);
  const missing = [
    !known(source) ? 'Evidence source not published' : '',
    !known(confidence) ? 'Evidence confidence not published' : '',
    !identity ? 'Fact identity not published' : '',
  ].filter(Boolean);
  if (!known(source) && !known(confidence) && !identity && !contributors.length)
    return { missing, details: null };
  return {
    missing,
    details: {
      key: `course:${occurrence}:${identity || `${source}:${String(fact['at'])}`}`,
      source: known(source) ? source : '',
      confidence: known(confidence) ? confidence : '',
      identity,
      contributors,
    },
  };
}

export interface Episode {
  readonly at: number;
  readonly fact: Row;
  readonly sourceFacts: readonly Row[];
  readonly task: string;
  readonly label: string;
  readonly badge: string;
  readonly epistemic: string;
  readonly summary: string;
  readonly findings: readonly string[];
  readonly directionFact: Row | null;
  readonly contributors: readonly string[];
}

export function courseEpisodes(semantic: Row, lanes: readonly Lane[]): Episode[] {
  const items = new Map(
    list(semantic['work_items'])
      .filter(isRecord)
      .map((item) => [String(item['work_item_id'] || ''), humanLabel(item['label'])] as const),
  );
  const taskFor = (fact: Row) =>
    items.get(String(fact['work_item_id'] || '')) ?? 'Task not observed';
  const exactlyBound = (fact: Row | null) => items.has(String(fact?.['work_item_id'] || ''));
  // A truthy member that is not a record reads as an empty one: every field of it is absent, as on the legacy page.
  const facts = list(semantic['facts'])
    .filter(Boolean)
    .map((fact): Row => (isRecord(fact) ? fact : {}));
  const factsById = new Map(facts.map((fact) => [String(fact['fact_id'] || ''), fact] as const));
  const projections = record(semantic['projections']);
  const intents = new Map(
    list(projections['operator_intents'])
      .filter(isRecord)
      .map((intent) => [String(intent['projection_id'] || ''), intent] as const),
  );
  const pairedDirection = (fact: Row): Row | null => {
    const episode = list(projections['steering_episodes']).find(
      (row) => String(fieldText(row, 'adaptation_fact') || '') === String(fact['fact_id'] || ''),
    );
    const intent = episode ? intents.get(String(fieldText(episode, 'intent_id') || '')) : undefined;
    const direction = intent ? factsById.get(String(intent['derived_from'] || '')) : undefined;
    const sameTask =
      Boolean(String(direction?.['work_item_id'] || '')) &&
      String(direction?.['work_item_id'] || '') === String(fact['work_item_id'] || '');
    const ordered =
      Number.isFinite(Number(direction?.['at'])) &&
      Number.isFinite(Number(fact['at'])) &&
      Number(direction?.['at']) <= Number(fact['at']);
    return direction &&
      direction['type'] === 'user_message' &&
      !readingCopied(direction) &&
      exactlyBound(direction) &&
      sameTask &&
      ordered
      ? direction
      : null;
  };
  const contributorNames = (fact: Row): string[] => [
    ...new Set(
      lanes
        .filter(
          (lane) =>
            !fact['work_item_id'] || String(lane.workItemId || '') === String(fact['work_item_id']),
        )
        .map((lane) => String(lane.worker || ''))
        .filter(Boolean),
    ),
  ];
  const episodes: Episode[] = [];
  const used = new Set<string>();
  const lifecycle = new Set<string>();
  for (const fact of facts) {
    if (used.has(String(fact['fact_id'] || ''))) continue;
    const findings = fact['type'] === 'result' ? reviewFindings(fact['detail']) : [];
    const completed = fact['type'] === 'result' ? latestCompletedResult({ facts: [fact] }) : null;
    const directionFact = pairedDirection(fact);
    const evidence = field(fact, 'evidence');
    const review =
      findings.length > 0 && Boolean(String(fieldText(evidence, 'source') || '').trim());
    const decision =
      fact['type'] === 'gate_decision' && Boolean(String(fact['decision'] || '').trim());
    const state =
      fact['type'] === 'stage_transition' && Boolean(String(fact['stage'] || '').trim());
    if (!exactlyBound(fact) || (!review && !completed && !decision && !state)) continue;
    const lifecycleKey =
      fact['type'] === 'result'
        ? String(fact['fact_id'] || '')
        : `${text(fact['type'])}\n${String(fact['work_item_id'] || '')}\n${String(fact['stage'] || fact['source_kind'] || '')}`;
    if (lifecycle.has(lifecycleKey)) continue;
    lifecycle.add(lifecycleKey);
    const summary =
      String(fact['summary'] || fact['stage'] || 'Work observed') +
      (completed ? ` · checkpoint ${completed.checkpoint}` : '');
    episodes.push({
      at: Number(fact['at'] || 0),
      fact,
      sourceFacts: directionFact ? [directionFact, fact] : [fact],
      task: taskFor(fact),
      label: review ? 'Course change' : decision ? 'Decision' : state ? 'State change' : 'Result',
      badge: review
        ? 'DERIVED COURSE CHANGE'
        : decision
          ? 'EXACT DECISION'
          : state
            ? 'EXACT STATE CHANGE'
            : 'EXACT RESULT',
      epistemic: review ? 'derived-course-change' : 'exact-course-change',
      summary,
      findings,
      directionFact,
      contributors: contributorNames(fact),
    });
    if (directionFact) used.add(String(directionFact['fact_id'] || ''));
  }
  return episodes.sort((left, right) => left.at - right.at);
}

/* Directions the reader gave that did not become part of an episode, in the order they were given. A
   direction counts if the server promoted it to an intent or an intent projection derives from it. */
export function courseDirections(semantic: Row, episodes: readonly Episode[]): Row[] {
  const used = new Set(
    episodes.map((episode) => String(episode.directionFact?.['fact_id'] || '')).filter(Boolean),
  );
  const projected = new Set(
    list(record(semantic['projections'])['operator_intents'])
      .map((intent) => String(fieldText(intent, 'derived_from') || ''))
      .filter(Boolean),
  );
  return list(semantic['facts'])
    .filter(
      (fact): fact is Row =>
        isRecord(fact) &&
        fact['type'] === 'user_message' &&
        !readingCopied(fact) &&
        !used.has(String(fact['fact_id'] || '')) &&
        (fact['intent_promoted'] === true || projected.has(String(fact['fact_id'] || ''))),
    )
    .sort((left, right) => Number(left['at'] || 0) - Number(right['at'] || 0));
}

/** How many episodes show before "N Earlier" gathers the rest. */
export const COURSE_VISIBLE = 8;

export function courseScope(episode: Episode, harnesses: ReadonlyMap<string, string>): Scope {
  return factSetScope(episode.sourceFacts.length ? episode.sourceFacts : [episode.fact], harnesses);
}
