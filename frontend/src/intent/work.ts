import { nextNumber } from '../api/bootstrap';
import { compatSessKey, contextKey } from '../api/identity';
import { isRecord, type Row } from '../observed';
import type { ContextEntry } from '../store/board';
import { PROMPT_SOURCES, type PromptCandidate } from '../sessions/intent';
import type { Annotation } from './annotation';

/* The observed record one session's Intent panel reads: the facts the server's project context published
   about it, in the order they happened, and the later directions found among them. Passive source reading
   and nothing else; no model is asked anything here. The legacy page's `nextCockpitWorkSource` and the
   functions beside it are the oracle (`work.differential.test.ts`). */

export const WORK_BY_HARNESS: Readonly<Record<string, readonly string[]>> = {
  pi: ['work_result', 'result'],
  claude: ['tool_report'],
};

/* Per harness, as `reading.WORK_EVIDENCE_BY_HARNESS` says: `result` is Pi's work result and, on Codex, the
   agent's own final answer, which is self-report. */
export function workOn(harness: unknown, type: unknown): boolean {
  const types = Object.hasOwn(WORK_BY_HARNESS, String(harness || ''))
    ? WORK_BY_HARNESS[String(harness || '')]
    : undefined;
  return Array.isArray(types) && types.includes(String(type || ''));
}

export interface WorkEntry {
  readonly id: string;
  readonly type: string;
  readonly by: string;
  readonly summary: string;
  readonly at: unknown;
  readonly resultAt: unknown;
  readonly sourceSession: unknown;
  readonly workerKind: string;
  readonly actorClaim: string;
  readonly modelDerived: boolean;
  readonly subject: string;
  readonly copied: boolean;
  readonly work: boolean;
  readonly result: string;
  readonly resultSource: string;
  readonly earlierFailed: boolean;
  readonly beforeLastChange: boolean;
  readonly changedAfter: boolean;
  readonly readIncomplete: boolean;
  readonly source: string;
}

function factSessionKey(fact: Row | null | undefined): string {
  const source = isRecord(fact?.['source_session']) ? fact['source_session'] : {};
  const harness = String(source['harness'] || '');
  const sid = String(source['sid'] || '');
  return harness && sid ? `${harness}:${sid}` : '';
}

/* Fact id breaks a tie, so two checks with one call time number the same whatever order the payload sent. */
function order(left: Row, right: Row): number {
  const byTime = Number(left['at'] || 0) - Number(right['at'] || 0);
  if (byTime) return byTime;
  const a = String(left['fact_id'] || '');
  const b = String(right['fact_id'] || '');
  return a < b ? -1 : a > b ? 1 : 0;
}

export function workEntries(session: Row, semantic: unknown): WorkEntry[] {
  const key = compatSessKey(session);
  const facts = isRecord(semantic) && Array.isArray(semantic['facts']) ? semantic['facts'] : [];
  return facts
    .filter((fact): fact is Row => Boolean(fact) && factSessionKey(fact as Row) === key)
    .sort(order)
    .map((fact) => {
      const evidence = isRecord(fact['evidence']) ? fact['evidence'] : {};
      const claim = String(fact['actor_claim'] || '');
      return {
        id: String(fact['fact_id'] || ''),
        type: String(fact['type'] || ''),
        by: String(fact['by'] || ''),
        summary: String(fact['summary'] || 'No summary published'),
        at: fact['at'],
        resultAt: fact['result_at'],
        sourceSession: fact['source_session'],
        workerKind: String(fact['worker_kind'] || ''),
        /* Kept: it says who derived a snapshot, so a model's paraphrase of the goal is never drawn in the
           register of a line a harness published. */
        actorClaim: claim,
        modelDerived: claim.startsWith('model-derived'),
        subject: String(fact['subject'] || ''),
        copied: fact['copied'] === true,
        work: workOn(session['harness'], fact['type']),
        result: String(fact['result'] || ''),
        resultSource: String(fact['result_source'] || ''),
        earlierFailed: fact['earlier_failed'] === true,
        beforeLastChange: fact['before_last_change'] === true,
        changedAfter: fact['changed_after'] === true,
        readIncomplete: fact['read_incomplete'] === true,
        source: [evidence['source'], evidence['confidence']]
          .map((value) => String(value == null ? '' : value).trim())
          .filter(Boolean)
          .join(' · '),
      };
    });
}

/* How many entries the list draws. Nothing upstream caps the semantic facts, so this is a readability
   bound and not a measurement, which is why the count it hid is stated under the rows. */
export const WORK_ROWS = 20;

export type WorkState = 'unread' | 'error' | 'partial' | 'empty' | 'read';

export interface WorkSource {
  readonly state: WorkState;
  readonly entries: readonly WorkEntry[];
  /** The full set, never the displayed window: a citation resolves against what the payload holds. */
  readonly all?: readonly WorkEntry[];
  readonly scan?: Row | null;
  readonly lineRequests?: Row | null;
  readonly shown?: number;
  readonly total?: number;
  readonly scanned?: number | null;
  readonly omitted?: number;
}

/* Where the observed record for one session comes from, and how far the page can be trusted to have it.

   Two contexts exist: the project one, which the server bounds to its most recently active sessions, and a
   focus-scoped one it fetches for the session the reader selected. The focused fetch names this session on
   purpose, so it wins where it has landed. The state matters as much as the entries: "No entry in the
   observed record names this session" is a claim ABOUT a record, and it was printed while the fetch was
   still in flight, after it failed, and for a session the server said it did not scan. */
export function workSource(
  contexts: ReadonlyMap<string, ContextEntry>,
  projectKey: string,
  session: Row,
): WorkSource {
  const key = compatSessKey(session);
  const focused = contexts.get(contextKey(projectKey, session as never));
  const project = contexts.get(contextKey(projectKey, null));
  const entry = focused?.data ? focused : project;
  if (!entry) return { entries: [], state: 'unread' };
  if (!entry.data) return { entries: [], state: entry.error ? 'error' : 'unread' };
  const data = entry.data as unknown as Row;
  const all = workEntries(session, data['semantic']);
  /* The window bounds the other rows only. A check or a written file is one of at most twelve, chosen
     failures first, and trimming them to the most recent would hide a listed failure. */
  const others = all.filter((row) => row.type !== 'tool_report').slice(-WORK_ROWS);
  const entries = all.filter((row) => row.type === 'tool_report' || others.includes(row));
  const otherTotal = all.filter((row) => row.type !== 'tool_report').length;
  const sources = isRecord(data['sources']) ? data['sources'] : null;
  const work = sources && isRecord(sources['work']) ? sources['work'] : null;
  const reports = work?.['tool_reports'];
  const scan =
    (Array.isArray(reports) ? reports : []).find(
      (row): row is Row => Boolean(row) && compatSessKey(row as Row) === key,
    ) ?? null;
  const requests = work?.['line_requests'];
  const requestRows = (Array.isArray(requests) ? requests : []).filter(
    (row): row is Row =>
      Boolean(row) &&
      (row as Row)['harness'] === session['harness'] &&
      (row as Row)['sid'] === session['sid'],
  );
  const lineRequests = requestRows.length === 1 ? (requestRows[0] ?? null) : null;
  if (entries.length) {
    return {
      entries,
      all,
      scan,
      lineRequests,
      state: 'read',
      shown: others.length,
      total: otherTotal,
    };
  }
  if (entry.error) return { entries, all, state: 'error' };
  /* Whether the scan that produces these facts reached this session. The answer is `sources.work.omitted`,
     a list of the sessions the analysis context bounded out, and naming the session is what makes the
     state a fact rather than an inference from two counts. It is not `command_attention_coverage`, which
     is a different bounded sweep with a different cap. */
  const omittedRows = work?.['omitted'];
  const omittedHere =
    Array.isArray(omittedRows) &&
    omittedRows.some((row) => Boolean(row) && compatSessKey(row as Row) === key);
  if (omittedHere) {
    const observer = sources && isRecord(sources['observer']) ? sources['observer'] : null;
    return {
      entries,
      all,
      scan,
      state: 'partial',
      scanned: nextNumber(observer?.['live']),
      omitted: (omittedRows as unknown[]).length,
    };
  }
  return { entries, all, scan, state: 'empty' };
}

export function workAbsence(source: Pick<WorkSource, 'state' | 'scanned' | 'omitted'>): string {
  if (source.state === 'unread')
    return 'The observed record for this session has not been read yet.';
  if (source.state === 'error') {
    return 'The observed record could not be read, so nothing here says what this session has been doing.';
  }
  if (source.state === 'partial') {
    const scanned =
      source.scanned == null ? 'the most recently active' : `${String(source.scanned)}`;
    return `This session was outside the observed-record scan, which covered ${scanned} of the sessions in this project and left ${String(source.omitted)} out. Its record is unread rather than empty.`;
  }
  return 'No entry in the observed record names this session.';
}

/* A message the server recognised as a correction the reader copied from Cargento is Cargento's words:
   not theirs here, so not a later direction and not a turn's start either. */
export function personAuthored(
  entry: Pick<WorkEntry, 'type' | 'copied' | 'by'> | null | undefined,
): boolean {
  const type = String(entry?.type || '');
  if (type === 'user_message') return entry?.copied !== true;
  return type === 'gate_decision' && String(entry?.by || '').startsWith('person:');
}

/* Where the numbers start: the evidence window of the saved words, and the whole record where nothing is
   saved or the store is off. Read from the session's own published start, the one the producer reads from,
   so the list's #1 and a reading's window are one moment. */
function entryWindow(session: Row, payload: Row): number | null {
  if (payload['annotate'] !== true) return null;
  const opened = nextNumber(session['annotation_window_start']);
  return opened !== null && opened > 0 ? opened : null;
}

export interface EntryNumbering {
  readonly all: readonly WorkEntry[];
  readonly opened: number | null;
  readonly numbers: ReadonlyMap<WorkEntry, number>;
  readonly earlier: readonly WorkEntry[];
  readonly untimed: readonly WorkEntry[];
}

/* The numbers, recomputed from the fact ids on every render and never stored. Over the full set, never the
   listed rows, for the reason citations resolve against it. An untimed entry cannot be placed in a window,
   so it is counted and not numbered. */
export function entryNumbering(
  session: Row,
  source: Pick<WorkSource, 'all' | 'entries'> | null,
  payload: Row,
): EntryNumbering {
  const all = (source && (source.all || source.entries)) || [];
  const opened = entryWindow(session, payload);
  const numbers = new Map<WorkEntry, number>();
  const earlier: WorkEntry[] = [];
  const untimed: WorkEntry[] = [];
  for (const entry of all) {
    const at = nextNumber(entry.at);
    if (at === null || at <= 0) untimed.push(entry);
    else if (opened !== null && at < opened) earlier.push(entry);
    else numbers.set(entry, numbers.size + 1);
  }
  return { all, opened, numbers, earlier, untimed };
}

/* Fact id to its number, for the panel's "#<n>" to read rather than recount. */
export function entryNumbers(
  session: Row,
  source: Pick<WorkSource, 'all' | 'entries'> | null,
  payload: Row,
): Map<string, number> {
  const { numbers } = entryNumbering(session, source, payload);
  return new Map([...numbers].map(([entry, n]) => [String(entry.id || ''), n]));
}

/* Where "later" starts: the server's `annotations.direction_floor`, spelt for the page, so the list's flag,
   the question and `POST /api/direction` agree about which entries are later. Adopted words floor at their
   prompt; a typed goal at the save of its current words (`goal_saved_at`, carried unchanged by a lines-only
   save, falling back to the revision time an older build published); no goal at the draft's prompt. A
   caller with no session keeps the revision time. */
export function baselineAt(
  annotation: Annotation | null | undefined,
  session: Row | null,
  draft: Pick<PromptCandidate, 'at'> | null,
): number | null {
  if (annotation && PROMPT_SOURCES.includes(annotation['goal_source'] as string)) {
    return nextNumber(annotation['goal_source_at']);
  }
  if (String(annotation?.['goal'] || '').trim()) {
    const saved = nextNumber(annotation?.['goal_saved_at']);
    return saved !== null ? saved : nextNumber(annotation?.['at']);
  }
  if (!session) return nextNumber(annotation?.['at']);
  return draft ? draft.at : null;
}

/* Every later direction, settled or not: a person-authored entry in the observed record whose time is
   after the revision last saved. A settled one stays flagged, because settling records that the baseline
   still applies, not that the reader never said it. NOT DETECTED: whether it conflicts. Deciding that a
   later instruction contradicts a typed goal is a reading of two prose strings, which the reader settles. */
export function laterDirections(
  annotation: Annotation | null | undefined,
  entries: readonly WorkEntry[] | null | undefined,
  session: Row | null,
  draft: Pick<PromptCandidate, 'at'> | null,
): WorkEntry[] {
  const typedAt = baselineAt(annotation, session, draft);
  if (typedAt === null) return [];
  return (entries || []).filter((entry) => {
    const at = nextNumber(entry.at);
    return at !== null && at > typedAt && personAuthored(entry);
  });
}

export function conflictCandidates(
  annotation: Annotation | null | undefined,
  entries: readonly WorkEntry[] | null | undefined,
  session: Row | null,
  draft: Pick<PromptCandidate, 'at'> | null,
): WorkEntry[] {
  const settled = nextNumber(annotation?.['settled_through']);
  return laterDirections(annotation, entries, session, draft).filter(
    (entry) => settled === null || (nextNumber(entry.at) ?? 0) > settled,
  );
}
