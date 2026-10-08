import { nextNumber } from '../api/bootstrap';
import { compatSessKey } from '../api/identity';
import {
  annotationDiscarded,
  annotationLines,
  storeUnreadable,
  annotateOn,
  type Annotation,
} from '../intent/annotation';
import { editedRefusal, intentDraft, intentUnsaved, type DraftInput } from '../intent/derive';
import { isRecord, type Row } from '../observed';
import { formatDuration } from '../shell/format';
import { openedWithControl, promptCandidate } from '../sessions/intent';
import {
  ANNOTATIONS_OFF,
  MODEL_OFF,
  MODEL_UNREAD,
  NO_WORDS,
  PRESS_CLAUDE,
  PRESS_CODEX,
  PRESS_EVENTS,
  PRESS_LINES,
  ROUTE_UNREAD,
  SAVE_STEP,
  UNAUTHORIZED,
} from './sentences';

/* Who would read a session, whether they were allowed to, and what refuses a press before it is made. Every
   function reads the payload it is given and nothing else, so the refusal the control draws and the one the
   handler enforces come from one derivation: a handler with a second opinion can refuse a press the button
   offered, or take one it refused. The legacy cockpit's `nextReading*` functions are the oracle. */

/* The page's one duration spelling, with the zero a caller wants in a sentence. */
export const fmtDur = (seconds: number): string => formatDuration(seconds) ?? '0s';

export function readingRoute(payload: Row, session: Row | null | undefined): Row | null {
  const routes = payload['reading_routes'];
  const route =
    isRecord(routes) && session ? (routes as Row)[String(session['harness'] || '')] : null;
  return isRecord(route) ? route : null;
}

/* The harnesses a press carries the agent's own messages from (`reading_route.AGENT_MESSAGE_HARNESSES`).
   Elsewhere a press sends none of them, so an Allow given before the disclosure named them still covers it:
   the server publishes that answer as `words`. */
const AGENT_WORDS_HARNESSES: readonly string[] = ['claude'];

/* Permission is per receiver: a Codex answer never stands in for Claude Code's. A payload without the
   per-provider map predates the second provider, and its one answer was Codex's. */
export function readingConsent(payload: Row, provider: string, harness = ''): boolean {
  const policy = payload['reading'];
  if (!isRecord(policy) || !provider) return false;
  const words = policy['words'];
  const map =
    !AGENT_WORDS_HARNESSES.includes(String(harness || '')) && words && typeof words === 'object'
      ? words
      : policy['providers'];
  return map && typeof map === 'object'
    ? (map as Row)[provider] === true
    : provider === 'codex' && policy['consent'] === true;
}

/* Tool output is its own answer, keyed by where it goes: a words-only Allow, or one given for another
   destination, never covers it. */
export function toolOutputGranted(payload: Row, route: Row | null): boolean {
  const policy = payload['reading'];
  const map = isRecord(policy) ? policy['tool_output'] : null;
  const granted = isRecord(map) && route ? map[String(route['provider'])] : null;
  return Array.isArray(granted) && granted.includes(String(route?.['destination']));
}

export function needsAllow(payload: Row, route: Row | null): boolean {
  if (!route || !route['provider']) return false;
  return (
    !readingConsent(payload, String(route['provider']), String(route['harness'] || '')) ||
    Boolean(route['destination'] && !toolOutputGranted(payload, route))
  );
}

/* Whether a press could read this row now, as the board published it, or as this tab's last press was
   answered when the board has not published it. Absent means not computed, and a press is then offered and
   the server decides. A settling row whose `until` has passed is read as eligible on the next render or
   press, with no timer of its own: the next collection drops the token anyway. */
export function eligibility(
  session: Row,
  answered: Readonly<Record<string, unknown>> | undefined,
  nowMs: number,
): Row | null {
  const published = session['reading_eligibility'];
  const given = answered?.['eligibility'];
  const held = isRecord(published) ? published : isRecord(given) ? given : null;
  if (!held || held['ok'] !== false || typeof held['reason'] !== 'string') return null;
  const until = nextNumber(held['until']);
  if (until !== null && nowMs / 1000 >= until) return null;
  return held;
}

/* The short line beside an inert Analyze drift, one per token the board can publish as
   `reading_eligibility.reason`. Codex, which reads only while a turn runs and has no session end the board
   can observe, gets its own line for both idle tokens. No line promises Analyze opens "once this session
   finishes a turn": the turn may have finished where Cargento could not see it. */
export function pressLine(session: Row | null | undefined, held: Row): string {
  const reason = String(held['reason']);
  const harness = String(session?.['harness'] || '');
  if (harness === 'codex' && ['idle-unknown', 'turn-stop'].includes(reason)) return PRESS_CODEX;
  if (reason === 'idle-unknown' && harness === 'claude') return PRESS_CLAUDE;
  if (reason === 'idle-unknown' && session && session['acquisition'] === 'event')
    return PRESS_EVENTS;
  return Object.hasOwn(PRESS_LINES, reason)
    ? (PRESS_LINES[reason] as string)
    : String(held['sentence'] || '');
}

export function pressRefusal(
  session: Row,
  answered: Readonly<Record<string, unknown>> | undefined,
  nowMs: number,
): string {
  const held = eligibility(session, answered, nowMs);
  return held ? pressLine(session, held) : '';
}

/* How long ago a stored withhold was written, for "Last analysis, 3m ago:". */
export function withheldAge(annotation: Annotation | null | undefined, generated: number): string {
  const at = nextNumber(annotation?.['reading_withheld_at']);
  if (at === null) return '';
  const age = Math.max(0, generated - at);
  return age < 60 ? 'just now' : `${fmtDur(age)} ago`;
}

export function anyConsent(payload: Row): boolean {
  const policy = payload['reading'];
  const map = isRecord(policy) ? policy['providers'] : null;
  return map && typeof map === 'object'
    ? Object.values(map).some((value) => value === true)
    : Boolean(isRecord(policy) && policy['consent']);
}

export function routeRefusal(payload: Row, session: Row): string {
  const route = readingRoute(payload, session);
  if (!route) return ROUTE_UNREAD;
  return route['provider'] ? '' : String(route['note'] || ROUTE_UNREAD);
}

export function policyReason(policy: unknown): string {
  if (!isRecord(policy)) return MODEL_UNREAD;
  if (policy['reason'] === 'run-disabled') return MODEL_OFF;
  if (policy['reason'] === 'store-unavailable') {
    return 'Reading permission or its daily budget could not be read or saved. Restore access to the Cargento store before analyzing drift.';
  }
  if (policy['reason'] === 'daily-cap') {
    const at = nextNumber(policy['retry_at']);
    return at === null
      ? 'The daily reading limit is reached. Wait for the next update.'
      : `The daily reading limit is reached. Try again after ${new Date(at * 1000).toLocaleString()}.`;
  }
  return '';
}

/* The running analysis for a session, from the published payload alone: a reload, another tab and this
   press all read the same job. */
export function readingJob(payload: Row, session: Row): Row | null {
  const jobs = payload['reading_jobs'];
  const job = isRecord(jobs) ? jobs[compatSessKey(session)] : null;
  return isRecord(job) && typeof job['id'] === 'string' ? job : null;
}

export function budgetLine(payload: Row): string {
  const policy = payload['reading'];
  if (!isRecord(policy)) return '';
  const { used, limit } = policy;
  if (
    !Number.isInteger(used) ||
    !Number.isInteger(limit) ||
    (used as number) < 0 ||
    (limit as number) <= 0
  ) {
    return '';
  }
  return `${String(Math.max(0, (limit as number) - (used as number)))} of ${String(limit)} left today`;
}

/* A discard record satisfies the nothing-typed arm too, and the wider answer is the less true of the two, so
   it is checked first. The sentence is the server's, so the block and the route behind its button cannot
   word one state two ways; the page adds the one step that lifts it. */
export function readingStates(payload: Row, annotation: Annotation | null | undefined): string {
  if (annotationDiscarded(annotation)) {
    const said = isRecord(payload['annotate_discard']) ? payload['annotate_discard'] : {};
    const why = String(said['unreadable'] || '').trim();
    return why ? `${why} ${SAVE_STEP}` : SAVE_STEP;
  }
  const unreadable = storeUnreadable(payload);
  if (unreadable) return unreadable;
  if (!String(annotation?.['goal'] || '').trim() && !annotationLines(annotation).length) {
    return NO_WORDS;
  }
  return policyReason(payload['reading']);
}

/* First, because with the store off there are no words to read and the route answers 503 whatever else is
   true. A stored reading outlives the model option: only the new request is gated here. */
export function readingRefusal(payload: Row, annotation: Annotation | null | undefined): string {
  if (!annotateOn(payload)) return ANNOTATIONS_OFF;
  const check = payload['reading_check'];
  const authorized = check === 'passed' || check === 'accepted';
  return readingStates(payload, annotation) || (authorized ? '' : UNAUTHORIZED);
}

export interface PromptRefusalInput {
  readonly input: DraftInput;
  /** Save intent is being answered, so telling the reader to save is false. */
  readonly saving: boolean;
  readonly answered: Readonly<Record<string, unknown>> | undefined;
  readonly nowMs: number;
}

/* The one reason an Analyze press cannot run, in rank order: annotations off, a route with no reader, a
   board that already says it cannot serve the press, an unsaved edit, then the words and the policy.
   `heldLive` skips the board's press refusal, for a card still holding a close. */
export function promptReadingRefusal(
  { input, saving, answered, nowMs }: PromptRefusalInput,
  heldLive = false,
): string {
  const { payload, session } = input;
  if (!annotateOn(payload)) return ANNOTATIONS_OFF;
  /* A route with no reader is a fact about this machine, and it outranks any step the page could name:
     saving a goal here would not let a check run. */
  const route = readingRoute(payload, session);
  if (route && !route['provider']) return routeRefusal(payload, session);
  /* So does a press the board already says it cannot serve: saving or choosing words would not let it
     read. */
  const press = heldLive ? '' : pressRefusal(session, answered, nowMs);
  if (press) return press;
  if (intentUnsaved(input)) return editedRefusal(saving);
  let annotation = input.annotation;
  if (!String(annotation?.['goal'] || '').trim()) {
    const draft = intentDraft(input);
    /* Over a control-first session the latest prompt is no goal either, so the press falls to the refusal
       for nothing typed. */
    const candidate =
      draft ?? (openedWithControl(session) ? null : promptCandidate(session, 'latest-prompt'));
    if (candidate && candidate.at === null) {
      return 'The prompt time was not published, so it cannot be adopted. Type a goal to analyze drift.';
    }
    if (candidate) {
      annotation = { ...annotation, goal: candidate.text, discarded_at: null, discarded_why: '' };
    }
  }
  return readingRefusal(payload, annotation) || routeRefusal(payload, session);
}
