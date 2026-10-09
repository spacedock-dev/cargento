import { isRecord } from '../observed';

/* The workflow stage conditions a reader has saved, and the workflow sources they are measured against, as
   the board publishes them under `tripwires`. Read defensively because the payload is untrusted, and spelled
   as the legacy card spells them because the sentences are the contract: `stage.differential.test.tsx` holds
   the card's text to the page's own.

   A condition is a browser-and-server preference to be told once when an observed entity enters a stage. It
   is not an instruction to a session, and nothing here says it is. */
export interface StageSource {
  readonly id: string;
  readonly workflow: string;
  readonly goal: string;
  readonly stages: readonly string[];
  readonly generation: unknown;
  readonly ambiguous: unknown;
  readonly sessions: readonly {
    readonly label: string;
    readonly harness: string;
    readonly sid: string;
  }[];
  readonly entities: readonly unknown[];
  readonly partial: unknown;
}

export interface StageRule {
  readonly id: string;
  readonly workflow: string;
  readonly stage: string;
  readonly state: string;
  readonly available: unknown;
  readonly revision: string;
  readonly why: string;
  readonly deliveryWhy: string;
  readonly trip: {
    readonly beforeObservedAt: number;
    readonly observedAt: number;
    readonly sourceWrittenAt: number;
  } | null;
}

export interface StageData {
  readonly enabled: boolean;
  readonly sourceEnabled: boolean | undefined;
  readonly error: string;
  readonly sources: readonly StageSource[];
  readonly rules: readonly StageRule[];
}

const text = (value: unknown): string => (value == null ? '' : String(value));
const list = (value: unknown): unknown[] => (Array.isArray(value) ? value : []);

function sourceOf(raw: unknown): StageSource | null {
  if (!isRecord(raw)) return null;
  return {
    id: text(raw['id']),
    workflow: text(raw['workflow']),
    goal: text(raw['goal']),
    stages: list(raw['stages']).map(text),
    generation: raw['generation'],
    ambiguous: raw['ambiguous'],
    sessions: list(raw['sessions'])
      .filter(isRecord)
      .map((session) => ({
        label: text(session['label']),
        harness: text(session['harness']),
        sid: text(session['sid']),
      })),
    entities: list(raw['entities']),
    partial: raw['partial'],
  };
}

function ruleOf(raw: unknown): StageRule | null {
  if (!isRecord(raw)) return null;
  const trip = raw['trip'];
  return {
    id: text(raw['id']),
    workflow: text(raw['workflow']),
    stage: text(raw['stage']),
    state: text(raw['state']),
    available: raw['available'],
    revision: text(raw['revision']),
    why: text(raw['why']),
    deliveryWhy: text(raw['delivery_why']),
    trip: isRecord(trip)
      ? {
          beforeObservedAt: Number(trip['before_observed_at']),
          observedAt: Number(trip['observed_at']),
          sourceWrittenAt: Number(trip['source_written_at']),
        }
      : null,
  };
}

/* The board's `tripwires`, or the off state a board without one is in: no card draws at all. */
export function stageData(payload: unknown): StageData {
  const raw = isRecord(payload) ? payload['tripwires'] : undefined;
  if (!isRecord(raw))
    return { enabled: false, sourceEnabled: undefined, error: '', sources: [], rules: [] };
  return {
    enabled: Boolean(raw['enabled']),
    sourceEnabled: typeof raw['source_enabled'] === 'boolean' ? raw['source_enabled'] : undefined,
    error: text(raw['error']),
    sources: list(raw['sources'])
      .map(sourceOf)
      .filter((source): source is StageSource => source !== null),
    rules: list(raw['rules'])
      .map(ruleOf)
      .filter((rule): rule is StageRule => rule !== null),
  };
}

export interface StageCardInput {
  readonly source: StageSource | null;
  readonly rule: StageRule | null;
  /** The choice the reader has made and not saved, if any. */
  readonly draft: string | undefined;
  readonly busy: boolean;
  readonly data: StageData;
  /** The browser notification lane's permission where that lane owns delivery, else null. */
  readonly lane: string | null;
  readonly stamp: (seconds: number) => string;
}

export interface StageCardModel {
  readonly id: string;
  readonly workflow: string;
  readonly scopeLine: string;
  readonly savedLine: string | null;
  readonly why: string;
  readonly coverage: string;
  readonly times: string;
  readonly delivery: string;
  readonly editor: null | {
    readonly choice: string;
    readonly options: readonly {
      readonly value: string;
      readonly label: string;
      readonly stale: boolean;
    }[];
    readonly disabled: boolean;
    readonly saveDisabled: boolean;
  };
  readonly rearmDisabled: boolean | null;
  readonly removeDisabled: boolean | null;
}

export function defaultStamp(seconds: number): string {
  return new Date(seconds * 1000).toLocaleString();
}

/* One card: a source and the rule saved against it, either of which can be absent. A rule whose source has
   gone is still drawn, suspended, so a saved condition is never silently dropped. */
export function stageCard(input: StageCardInput): StageCardModel {
  const { source, rule, busy, data, lane, stamp } = input;
  const id = (source ?? (rule as StageRule)).id;
  const draft = input.draft || rule?.stage || source?.stages[0] || '';
  const unavailable = !source || !source.generation || Boolean(source.ambiguous);
  const valid = Boolean(source?.stages.includes(draft));
  const scope = source
    ? source.sessions.map((session) => `${session.label} (${session.harness})`).join(' · ')
    : data.sourceEnabled === false
      ? 'Project reads are off (--no-spacedock)'
      : 'Source session absent';
  const trip = rule?.trip ?? null;
  return {
    id,
    workflow: (source ?? (rule as StageRule)).workflow,
    scopeLine: `${source?.goal ?? ''} · ${scope}`,
    savedLine: rule
      ? `Saved stage: ${rule.stage} · ${rule.state}${rule.available ? '' : ' · suspended'}`
      : null,
    why: source?.ambiguous
      ? 'Workflow choice is ambiguous; open one source session or give the workflows distinct names.'
      : rule?.why || 'Save a stage condition to start a fresh baseline.',
    coverage: source
      ? `${String(source.entities.length)} current entity records evaluated${
          source.partial ? ' · partial coverage; missing or capped records are unavailable' : ''
        }`
      : 'Current entity state unavailable',
    times: trip
      ? `Observed ${stamp(trip.beforeObservedAt)} → ${stamp(trip.observedAt)}; source file written ${stamp(trip.sourceWrittenAt)}.`
      : '',
    delivery: `${rule?.deliveryWhy ?? ''} ${
      trip && lane !== null ? `Browser notification lane: ${lane}. No banner is confirmed.` : ''
    }`,
    editor: source
      ? {
          choice: draft,
          options: [
            ...(!valid ? [{ value: draft, label: `${draft} (unavailable)`, stale: true }] : []),
            ...source.stages.map((stage) => ({ value: stage, label: stage, stale: false })),
          ],
          disabled: busy || unavailable,
          saveDisabled: busy || unavailable || !valid,
        }
      : null,
    rearmDisabled: rule ? busy || unavailable || !source?.stages.includes(rule.stage) : null,
    removeDisabled: rule ? busy : null,
  };
}

/* The cards a scope shows. `sessions` null is every source and every rule; otherwise the sources one of
   those exact sessions belongs to, and no orphan rule, because a rule with no source has no session to
   belong to a scope. */
export function stagePairs(
  data: StageData,
  sessions: readonly { readonly harness: string; readonly sid: string }[] | null,
): { source: StageSource | null; rule: StageRule | null }[] {
  const keys = sessions && new Set(sessions.map((session) => `${session.harness}:${session.sid}`));
  const selected = data.sources.filter(
    (source) =>
      !keys || source.sessions.some((session) => keys.has(`${session.harness}:${session.sid}`)),
  );
  const ids = new Set(selected.map((source) => source.id));
  const pairs: { source: StageSource | null; rule: StageRule | null }[] = selected.map(
    (source) => ({
      source,
      rule: data.rules.find((rule) => rule.id === source.id) ?? null,
    }),
  );
  if (!keys) {
    for (const rule of data.rules) if (!ids.has(rule.id)) pairs.push({ source: null, rule });
  }
  return pairs;
}

export function stageIntro(data: StageData): string {
  return (
    data.error ||
    (data.sourceEnabled === false
      ? 'Project reads are off (--no-spacedock); saved conditions are suspended.'
      : 'Alert once on an observed entry. First sight and gaps establish a baseline; skipped stages are not inferred.')
  );
}
