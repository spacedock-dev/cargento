import { compatSessKey } from '../api/identity';
import { annotationOf } from '../intent/annotation';
import { announce } from '../intent/context';
import { isRecord, type Row } from '../observed';
import { REGION_IDS } from '../shell/announcer';
import { JOB_TITLE, READING_FINISHED } from './sentences';
import type { DriftCtx } from './state';

/* How an analysis ended, said once. A withheld, cancelled or interrupted end is the server's own
   `reading_withheld` sentence; a stored reading is this one. No positional word, so it is true at every
   width: the result stands in the Drift card, in the button's place. */
function outcome(payload: Row, key: string, readingAtSeen: string): string {
  const sessions = Array.isArray(payload['sessions']) ? (payload['sessions'] as Row[]) : [];
  const row = sessions.find((session) => compatSessKey(session) === key);
  const annotation = row ? annotationOf(row) : null;
  const withheld = String(annotation?.['reading_withheld'] || '');
  if (withheld) return withheld;
  const reading = JSON.stringify(annotation?.['assessment'] || null);
  return reading !== 'null' && reading !== readingAtSeen ? READING_FINISHED : '';
}

function readingOf(payload: Row, key: string): string {
  const sessions = Array.isArray(payload['sessions']) ? (payload['sessions'] as Row[]) : [];
  const row = sessions.find((session) => compatSessKey(session) === key);
  const annotation = row ? annotationOf(row) : null;
  return JSON.stringify(annotation?.['assessment'] || null);
}

/* "Analyzing drift" is said when a job this tab had not seen is first drawn, and the outcome when a job whose
   box was drawn leaves `reading_jobs`, so a redraw, a phase revision or a reload says nothing again. The
   first pass only records what is already running: a reload pressed nothing. Run after the card commits, and
   never from a render: a region and its first message must not arrive in the same mutation.

   `drawn` is the ids of the boxes the committed card drew. A job first seen undrawn never announces its
   start, even if its box is drawn later: the reader did not watch it begin. */
export function trackJobs(ctx: DriftCtx, payload: Row, drawn: ReadonlySet<string>): void {
  const { drift } = ctx;
  const rawJobs = payload['reading_jobs'];
  const jobs: Record<string, unknown> = isRecord(rawJobs) ? rawJobs : {};
  const primed = drift.isPrimed();
  drift.prime();
  /* Emptying a region is silent, so a stale "Analyzing drift" is taken back without a second announcement. */
  const clearTitle = () => {
    const region = typeof document === 'undefined' ? null : document.getElementById(REGION_IDS.cue);
    if (region && region.textContent === JOB_TITLE) region.textContent = '';
  };
  const say = (key: string, sentence: string) => {
    /* A region already holding the sentence is a write the reader's software does not read again, so the
       guard goes first: the same sentence for a new job is a new event. */
    ctx.shell.announcer.forget(key);
    announce(ctx.intent, key, sentence);
  };
  for (const [key, seen] of [...drift.jobsSeen]) {
    const job = jobs[key];
    if (isRecord(job) && String(job['id']) === seen.id) continue;
    drift.jobsSeen.delete(key);
    const said = seen.drawn ? outcome(payload, key, seen.reading) : '';
    if (said) {
      say(`job:${seen.id}`, said);
    } else {
      /* Ended unannounced: a virtual cursor must not still find "Analyzing drift" in the region, and the
         next start must not set that same text again, which is not read. */
      ctx.shell.announcer.forget(`job:${seen.id}`);
      clearTitle();
    }
  }
  for (const [key, job] of Object.entries(jobs)) {
    if (!isRecord(job) || typeof job['id'] !== 'string') continue;
    const seen = drift.jobsSeen.get(key);
    const isDrawn = drawn.has(job['id']);
    if (seen) {
      seen.drawn = isDrawn;
      continue;
    }
    drift.jobsSeen.set(key, { id: job['id'], drawn: isDrawn, reading: readingOf(payload, key) });
    if (primed && isDrawn) say(`job:${job['id']}`, JOB_TITLE);
  }
}
