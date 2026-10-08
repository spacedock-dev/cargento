import { nextNumber } from '../api/bootstrap';
import {
  conflictCandidates,
  entryNumbering,
  laterDirections,
  personAuthored,
  workAbsence,
  type WorkEntry,
  type WorkSource,
} from '../intent/work';
import type { Draft } from '../intent/derive';
import type { Annotation } from '../intent/annotation';
import {
  durationSince,
  endedAt,
  READING_TURN_STOP_HARNESSES,
  sessionStop,
  type Row,
} from '../observed';
import { harnessLabels } from '../sessions/rows';
import { readingRoute } from './route';
import { WORK_AS_REPORTED, WORK_READ_FROM } from './sentences';
import { readingAuthor, readingCopied } from './shape';

/* The session's activity, numbered. It sits right after CURRENT ACTIVITY in the activity column, under the
   column's own "Session activity" heading, and the numbers are the ones every "#<n>" on the page names: a
   reading cites an entry by this list's number, so a citation resolves against the same list the reader is
   looking at rather than against a second collection assembled from the same facts. `cited` is the set of
   fact ids the current reading's surviving departures rest on. The legacy cockpit's `nextCockpitWorkEvidence`
   is the oracle (`workList.differential.test.ts`). */

/* The agent's messages, bounded apart: half the other rows' bound, a readability choice, stated under the rows
   the same way. */
export const AGENT_ROWS = 10;
/* How many entries the block draws: a readability bound rather than a measurement, which is why the count it
   hid is stated under the rows. Nothing upstream caps the semantic facts. */
export const WORK_ROWS = 20;

/* A fact's type as a word on the activity list. Closed, and a Map so a type named like an Object property
   cannot resolve to one: a type with no word here reads "Entry" rather than its raw token. */
const ENTRY_KIND = new Map([
  ['prepared_dispatch', 'Dispatch'],
  ['work_birth', 'Task started'],
  ['work_result', 'Task result'],
  ['result', 'Result'],
  ['gate_decision', 'Gate'],
  ['decision', 'Decision'],
  ['assignment', 'Assignment'],
  ['stage_transition', 'Stage'],
  ['agent_message', 'Agent said'],
]);

/* A check's or a written path's own line under its summary: who, what, and what the tool reported. The result
   words say where the result came from, because "passed" from an error flag and "passed" from a summary line
   are different strengths of the same claim. */
const CHECK_RESULTS: Readonly<Record<string, string>> = {
  'failed flag': 'failed, as the tool reported',
  'passed flag': 'passed, as the tool reported',
  'failed summary': 'failed, per its summary line',
  'passed summary': 'passed, per its summary line',
  'failed marker': 'failed, per a failure line in its output',
};

export function toolReportLine(entry: WorkEntry): string {
  if (entry.subject !== 'check') return 'Agent · file written';
  const key = `${entry.result} ${entry.resultSource}`;
  const parts = [
    'Agent',
    'check',
    Object.hasOwn(CHECK_RESULTS, key) ? (CHECK_RESULTS[key] as string) : 'ran, result not recorded',
  ];
  if (entry.earlierFailed) parts.push('an earlier run failed');
  if (entry.beforeLastChange) parts.push('before the last change');
  return parts.join(' · ');
}

function humanLabel(value: string): string {
  const words = String(value || 'work')
    .replace(/[-_]+/g, ' ')
    .trim();
  return words ? (words[0] ?? '').toUpperCase() + words.slice(1) : 'Work';
}

/* What the whole scan found, from the counts `claude_tool_reports` publishes beside the rows. Every figure is
   the full scan, never the listed rows: a dropped entry must not turn into "no check" or into a reassurance. A
   background launch is named, because a background run records no result and a sentence that said no check
   ran would be false. */
export function checkScan(scan: Row | null | undefined): string {
  if (!scan || typeof scan !== 'object') return '';
  const count = (n: number, one: string, many: string): string =>
    `${String(n)} ${n === 1 ? one : many}`;
  const runs = nextNumber(scan['check_runs']) || 0;
  const background = nextNumber(scan['background']) || 0;
  const written = nextNumber(scan['written_paths']) || 0;
  const other = nextNumber(scan['other_commands']) || 0;
  const more = nextNumber(scan['more']) || 0;
  const outside = nextNumber(scan['outside_paths']) || 0;
  if (!runs && !background && !written && !other && !outside) {
    return 'No check ran in the part of the transcript read.';
  }
  /* The latest results, always, so a failure is never left for the listed rows alone to carry; the files are a
     sentence of their own, so they never read as a latest-run result. */
  const checks = runs
    ? `${count(runs, 'check run', 'check runs')} across ${count(nextNumber(scan['distinct_checks']) || 0, 'distinct check', 'distinct checks')}; latest runs: ${String(nextNumber(scan['failed']) || 0)} failed, ${String(nextNumber(scan['not_recorded']) || 0)} with no recorded result, ${String(nextNumber(scan['passed']) || 0)} passed`
    : 'no check in the foreground';
  const files: string[] = [];
  if (written) files.push(count(written, 'file written', 'files written'));
  if (outside)
    files.push(`${count(outside, 'file', 'files')} written outside the working directory`);
  const counted: string[] = [];
  if (background) {
    counted.push(
      `${count(background, 'background launch', 'background launches')}, because a background run records no result`,
    );
  }
  if (other) counted.push(count(other, 'other shell command', 'other shell commands'));
  return (
    `From the part of the transcript read: ${checks}.` +
    (files.length ? ` ${files.join(', ').replace(/^./, (c) => c.toUpperCase())}.` : '') +
    (counted.length ? ` Counted and not listed: ${counted.join('; ')}.` : '') +
    (more ? ` Failures are listed first, and ${String(more)} more are counted and not listed.` : '')
  );
}

/* The observed last turn of a session waiting at its prompt, inside the evidence window: from the reader's
   latest message at or before the stop, or the window start if later, up to the stop. Not from the window
   start to the save: that range is fixed when the words are saved, so the next turn made it name an older one.
   Null on every other session and where no message opens the turn, because a label nothing measured would be
   the board authoring a turn. */
export function lastTurn(
  session: Row,
  entries: readonly WorkEntry[],
): { readonly from: number; readonly to: number } | null {
  if (!READING_TURN_STOP_HARNESSES.includes(String(session['harness'] || ''))) return null;
  if (endedAt(session) !== null) return null;
  const found = sessionStop(session);
  const stop = found ? found.at : null;
  if (!(session['state'] === 'idle' && stop !== null && stop > 0)) return null;
  const opened = nextNumber(session['annotation_window_start']);
  const starts = entries
    .filter(personAuthored)
    .map((entry) => nextNumber(entry.at))
    .filter((at): at is number => at !== null && at > 0 && at <= stop);
  if (opened === null || !starts.length) return null;
  const from = Math.max(opened, ...starts);
  return from <= stop ? { from, to: stop } : null;
}

export function entryActor(entry: WorkEntry): string {
  const author = readingAuthor(entry);
  /* You pasted it, and Cargento wrote it: the meta says which. */
  if (author === 'person' || readingCopied(entry)) return 'You';
  /* Cargento's own paraphrase is never credited to the agent. */
  return author === 'derived' ? 'Cargento’s summary' : 'Agent';
}

const entryCount = (n: number): string => `${String(n)} ${n === 1 ? 'entry' : 'entries'}`;

/* "A, B and C", for the bound sentence's clauses. */
function joinClauses(parts: readonly string[]): string {
  const last = parts[parts.length - 1];
  return parts.length < 2 ? parts.join('') : `${parts.slice(0, -1).join(', ')} and ${last ?? ''}`;
}

/* The clause for entries that are counted and not listed, naming the ones a departure cites, which are listed
   anyway with their time and no number. An untimed entry has no time to list it with. */
function unlistedClause(count: number, what: string, cited: number, timed = true): string {
  const are = count === 1 ? 'is' : 'are';
  const how = timed ? `with ${cited === 1 ? 'its' : 'their'} time and no number` : 'with no number';
  const except = !cited
    ? ''
    : `, except ${cited === 1 ? 'the one' : `the ${String(cited)}`} the analysis cites, listed ${how}`;
  return `${String(count)} ${what} ${are} counted and not listed${except}.`;
}

/* What the rows actually are, counted from the rows themselves. The block was headed WORK EVIDENCE, and on
   Claude and Codex every entry is a `user_message`, so a reader comparing their words against "work evidence"
   was reading their own sentences back on both sides of the comparison. The heading names the record rather
   than the work, and this line says what is in it. One pass and exclusive buckets, so the remainder cannot be
   reached by subtracting overlapping filters. */
export function workMix(entries: readonly WorkEntry[]): string {
  let directions = 0;
  let copied = 0;
  let derived = 0;
  let summaries = 0;
  let said = 0;
  let work = 0;
  for (const entry of entries) {
    if (personAuthored(entry)) directions += 1;
    else if (readingCopied(entry)) copied += 1;
    else if (entry.modelDerived) derived += 1;
    else if (String(entry.type || '') === 'observer_snapshot') summaries += 1;
    /* What the agent said is its account, not an observation of what it did. */ else if (
      String(entry.type || '') === 'agent_message'
    ) {
      said += 1;
    } else work += 1;
  }
  const parts = [`${String(entries.length)} ${entries.length === 1 ? 'entry' : 'entries'}`];
  if (directions)
    parts.push(`${String(directions)} ${directions === 1 ? 'direction' : 'directions'} you gave`);
  if (said) parts.push(`${String(said)} ${said === 1 ? 'message' : 'messages'} the agent wrote`);
  if (copied) parts.push(`${String(copied)} copied from Cargento`);
  if (derived) parts.push(`${String(derived)} model-derived`);
  if (summaries) {
    parts.push(
      `${String(summaries)} derived ${summaries === 1 ? 'summary' : 'summaries'} of this session`,
    );
  }
  parts.push(`${String(work)} observed of what it did`);
  return `${parts.join(' · ')}.`;
}

export function evidenceOwn(payload: Row, harness: string, sent = true): string {
  const label = harnessLabels(payload).get(harness) || humanLabel(harness);
  if (harness === 'pi')
    return `${label} publishes demonstrated work results, and they are read here.`;
  if (harness === 'claude') {
    /* The route's own sentence says what a reading sends of them and to whom, or that it sends none, so the
       line under the checks and the disclosure beside the button cannot word it two ways. */
    const route = sent ? readingRoute(payload, { harness }) : null;
    const output = route?.['provider'] ? String(route['tool_output'] || '') : '';
    return (
      `${label} records the checks a session ran and the files it wrote, and they are listed here. A result is what the tool reported; Cargento inspects no file, test or deliverable.` +
      (output ? ` ${output}` : '')
    );
  }
  /* "Cargento reads those on Pi alone" stood here, and stopped being true when Claude Code's checks were read
     too. The panel's own harness limit is the level's, so this line says only what the record above is. */
  return `${label} publishes no demonstrated work results, so nothing above is an inspected file, test or deliverable.`;
}

export interface WorkRow {
  readonly entry: WorkEntry;
  readonly n: number | null;
  /** A check's or a file's own line, or the actor and the type's word. */
  readonly head: { readonly report: string } | { readonly actor: string; readonly type: string };
  readonly flags: readonly ('later' | 'cited')[];
  readonly source: string;
  readonly at: string;
  readonly turn: boolean;
  readonly add: boolean;
}

export interface WorkList {
  readonly anchor: string;
  readonly unnumbered: string;
  readonly rows: readonly WorkRow[];
  /** Said where no row is drawn and the record is not merely unnumbered. */
  readonly absent: string;
  readonly mix: string;
  readonly unlisted: readonly string[];
  readonly checks: string;
  readonly bound: string;
  readonly reads: boolean;
  readonly limit: string;
}

export interface WorkListInput {
  readonly session: Row;
  readonly payload: Row;
  readonly source: WorkSource;
  readonly annotation: Annotation | null;
  readonly draft: Draft | null;
  readonly cited: ReadonlySet<string>;
  readonly generated: number;
}

export function workList(input: WorkListInput): WorkList {
  const { session, payload, source, annotation, cited } = input;
  const numbering = entryNumbering(session, source, payload);
  const { all, numbers, earlier, untimed, opened } = numbering;
  const annotate = payload['annotate'] === true;
  const ann = annotate ? annotation : null;
  const later = new Set(laterDirections(ann, all, session, input.draft));
  /* Every unsettled later direction is drawn at its own number, as a cited entry is, so the "#<n>" the
     question before the press names is always a row on screen. One from before the window has no number and
     is drawn with its time, as a cited earlier entry is, and is not counted among the earlier entries left
     unlisted. A settled one takes the bound. */
  const open = new Set(conflictCandidates(ann, all, session, input.draft));
  /* The readability bound: the newest non-tool rows, every listed check and file, and every entry a departure
     cites, each at its own number so the gaps show. A cited entry is always drawn, so it is reachable without
     an expand control. */
  const numbered = all.filter((entry) => numbers.has(entry));
  /* The agent's messages take a bound of their own beside the other rows', so a talkative session never
     pushes the reader's messages off the list. */
  const agentSaid = (entry: WorkEntry): boolean => entry.type === 'agent_message';
  const recent = new Set(
    numbered.filter((entry) => entry.type !== 'tool_report' && !agentSaid(entry)).slice(-WORK_ROWS),
  );
  const recentSaid = new Set(numbered.filter(agentSaid).slice(-AGENT_ROWS));
  const isCited = (entry: WorkEntry): boolean => cited.has(String(entry?.id || ''));
  const isRecent = (entry: WorkEntry): boolean => recent.has(entry) || recentSaid.has(entry);
  const entries = all.filter(
    (entry) =>
      isCited(entry) ||
      open.has(entry) ||
      (numbers.has(entry) && (entry.type === 'tool_report' || isRecent(entry))),
  );
  const turnOf = lastTurn(session, all);
  const rows = entries.map((entry): WorkRow => {
    const stamp = nextNumber(entry.at);
    const n = numbers.get(entry);
    const copied = readingCopied(entry);
    return {
      entry,
      n: n ?? null,
      head:
        entry.type === 'tool_report'
          ? { report: toolReportLine(entry) }
          : {
              actor: entryActor(entry),
              type: copied
                ? 'Copied from Cargento'
                : entry.type === 'user_message'
                  ? 'Prompt'
                  : (ENTRY_KIND.get(String(entry.type || '')) ?? 'Entry'),
            },
      /* Neutral tags: neither is a finding. "Cited" says a departure rests on the entry, and a later
         direction is never called drift. */
      flags: [
        ...(later.has(entry) ? (['later'] as const) : []),
        ...(isCited(entry) ? (['cited'] as const) : []),
      ],
      /* Out of view and still read out: the same source on every row was a full-width caption five times
         over. Only where `actor_claim` says something the source line does not. */
      source:
        (entry.source || 'Source not published') +
        (entry.actorClaim && !entry.source.includes(entry.actorClaim)
          ? ` · ${entry.actorClaim}`
          : ''),
      at: ((): string => {
        const age = durationSince(input.generated, entry.at);
        return age === null ? 'time not published' : `${age} ago`;
      })(),
      turn: Boolean(
        turnOf &&
          stamp !== null &&
          stamp >= turnOf.from &&
          stamp <= turnOf.to &&
          !personAuthored(entry),
      ),
      add: later.has(entry),
    };
  });
  /* Where the words' window opens, a message of the reader's should sit: the latest one at or before the save
     for typed words, the prompt itself for adopted ones. A window at the save time is typed words with no
     earlier message, and nothing is expected there. */
  const promptSource = Boolean(
    annotation &&
      ['latest-prompt', 'first-prompt', 'chosen-prompt'].includes(
        String(annotation['goal_source']),
      ),
  );
  const saved = nextNumber(annotation?.['at']);
  const expected = opened !== null && (promptSource || (saved !== null && opened < saved));
  const anchor =
    ann && expected && numbers.size && !all.some((entry) => nextNumber(entry.at) === opened)
      ? earlier.length
        ? 'No entry in the record read here sits where your intent’s window opens, so #1 is the first entry after that point.'
        : 'The record read here no longer reaches back to where your intent’s window opens, so #1 is the first entry it holds after that point.'
      : '';
  const unlisted: string[] = [];
  const unasked = earlier.filter((entry) => !open.has(entry));
  if (unasked.length) {
    unlisted.push(
      unlistedClause(
        unasked.length,
        `earlier ${unasked.length === 1 ? 'entry' : 'entries'}, from before your intent’s window opened,`,
        unasked.filter(isCited).length,
      ),
    );
  }
  if (untimed.length) {
    unlisted.push(
      unlistedClause(
        untimed.length,
        `${untimed.length === 1 ? 'entry' : 'entries'} with no published time`,
        untimed.filter(isCited).length,
        false,
      ),
    );
  }
  /* Every figure from the rows drawn and the numbers given, never authored. */
  const listed = entries.filter((entry) => numbers.has(entry));
  const bound =
    listed.length < numbers.size
      ? `Listing ${String(listed.length)} of ${entryCount(numbers.size)}: ${joinClauses([
          `the ${String(recent.size)} most recent`,
          ...(recentSaid.size
            ? [`the ${String(recentSaid.size)} most recent messages the agent wrote`]
            : []),
          /* In the window: a check or file from before it is counted with the earlier entries, so "every" is
             true only of this set. */
          ...(listed.some((entry) => entry.type === 'tool_report')
            ? ['every check and file in the window']
            : []),
          ...(listed.some(
            (entry) => isCited(entry) && entry.type !== 'tool_report' && !isRecent(entry),
          )
            ? ['every entry the analysis cites']
            : []),
          ...(listed.some((entry) => open.has(entry) && !isCited(entry) && !isRecent(entry))
            ? ['every later direction still to settle']
            : []),
        ])}. ${String(numbers.size - listed.length)} ${numbers.size - listed.length === 1 ? 'is' : 'are'} counted and not listed.`
      : '';
  /* Nothing numbered while the record holds entries is a fact about the window, not an empty record: "No entry
     names this session" beside a count of the entries it holds was false. */
  const unnumbered =
    !numbers.size && (earlier.length || untimed.length)
      ? earlier.length
        ? 'No entry in the record read here is from after your intent’s window opened, so none is numbered.'
        : 'No entry in the record read here has a published time, so none is numbered.'
      : '';
  const harness = String(session['harness'] || '');
  const reads = harness === 'claude' || harness === 'pi';
  const limit = reads
    ? `${WORK_READ_FROM} ${evidenceOwn(payload, harness, false)}`
    : `${WORK_READ_FROM} ${evidenceOwn(payload, harness)}`;
  return {
    anchor,
    unnumbered,
    rows,
    absent: rows.length || unnumbered ? '' : workAbsence(source),
    mix: numbered.length ? workMix(numbered) : '',
    unlisted,
    checks: source.scan ? checkScan(source.scan) : '',
    bound,
    reads,
    limit,
  };
}

export { WORK_AS_REPORTED };
