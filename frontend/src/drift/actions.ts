import { nextNumber } from '../api/bootstrap';
import { compatSessKey } from '../api/identity';
import type { ReadingRequest, SessionIdentity } from '../api/types';
import { annotationOf } from '../intent/annotation';
import {
  announce,
  answered,
  identityOf,
  liveRow,
  pendingEnd,
  pendingHas,
  pendingStart,
  readInput,
  refresh,
} from '../intent/context';
import { goalKey, intentKey } from '../intent/derive';
import type { KeepAnalyzeOutcome, KeepAnalyzeRequest } from '../intent/directions';
import { intentForReading } from '../intent/api';
import { KEEP_REFUSED } from '../intent/sentences';
import { isRecord, type Row } from '../observed';
import { acknowledgeFlip } from './flip';
import { currentPayload, showJob, showReading, showRoute } from './overlay';
import {
  needsAllow,
  policyReason,
  pressRefusal,
  promptReadingRefusal,
  readingJob,
  readingRoute,
  routeRefusal,
} from './route';
import {
  CANCEL_FAILED,
  DESTINATION_CHANGED,
  PROVIDER_CHANGED,
  RESULT_MARK_UNSAVED,
} from './sentences';
import type { DriftCtx } from './state';
import { pressLine } from './route';

/* Every request the Drift section sends, each from one explicit press of one control. A mount, a second
   mount under StrictMode, a board refresh, a poll, a reconnect or a retry reaches none of them, and a lost
   answer is never retried: it does not establish that the model never ran.

   `press: true` is the shape contract's "asserted rather than assumed" made mechanical: the literal appears
   in this one place, inside a handler a click reaches, and the route refuses a body without it.
   `observer_model: 1` preserves the route's explicit-request guard; the separate allow field records a
   first-press answer, and the server checks its durable permission and budget again at the model seam. */

function pressDetails(ctx: DriftCtx, identity: SessionIdentity) {
  const session = liveRow(ctx.intent, identity);
  const input = session ? readInput(ctx.intent, identity, session) : null;
  const payload = currentPayload(ctx);
  if (!session || !input || !payload) return null;
  return { session, input: { ...input, payload }, payload };
}

/* One reading, on one press, and no retry. */
export async function askForReading(
  ctx: DriftCtx,
  identity: SessionIdentity,
  allow = false,
): Promise<void> {
  const { intent, shell } = ctx;
  const held = intent.held;
  const read = pressDetails(ctx, identity);
  if (!read) return;
  const { session, input, payload } = read;
  const key = compatSessKey(session);
  /* A press in flight, or a running job, is the answer to a second press: nothing is sent. */
  if (
    pendingHas(intent, `reading:${key}`) ||
    pendingHas(intent, `reading-allow:${key}`) ||
    held.requests.get(key)?.pending ||
    readingJob(payload, session)
  ) {
    return;
  }
  /* Keep's "Press Allow and analyze" is answered by this press, so the region stops holding it. */
  shell.announcer.forget(`keep:${key}`);
  /* This press arrives from states the browser used to swallow, and an ungated one spends the reader's own
     model capacity from a state the page calls unavailable. Answered rather than dropped, because a
     clicked control that goes silent is indistinguishable from a dead one. */
  const request = held.requests.get(key);
  const now = shell.clock.now();
  const refusal = promptReadingRefusal({
    input,
    saving: pendingHas(intent, `${intentKey(session)}:save`),
    answered: request,
    nowMs: now,
  });
  if (refusal) {
    // A press during a held close learns the board's state; the card shows it now.
    if (refusal === pressRefusal(session, request, now)) acknowledgeFlip(ctx, session, false);
    held.requests.set(key, { pending: false, message: refusal, refusal: true });
    held.notify();
    return;
  }
  /* The provider the page named, sent with the press so the server can refuse one whose receiver changed
     since. A refusal above already covers a route with no provider. */
  const route = readingRoute(payload, session);
  if (!route) return;
  const provider = String(route['provider']);
  /* The destinations the disclosure named, sent with an Allow so the server can refuse one given about an
     endpoint that has since moved: where tool output goes, and where the words go, which the Allow is
     bound to. "" is sent as itself, since an unnamed one is its own value. */
  const destination = String(route['destination'] || '');
  const wordsTo = String(route['words_destination'] || '');
  const reading = intentForReading(shell, identity);
  const chosenNow = held.chosen.get(goalKey(session)) ?? null;
  if (needsAllow(payload, route) && !allow) {
    held.requests.set(key, {
      consent: true,
      adoption: reading?.adoption ?? {},
      chosen: chosenNow,
    });
    held.notify();
    return;
  }
  /* Allow sends the prompt the card was opened over, so a record that moved underneath is refused by the
     server rather than read unseen. A choice the reader made or undid while the card was up is theirs, so it
     is what the box holds now that Allow sends. */
  const confirmation = held.requests.get(key);
  const adoption =
    allow &&
    confirmation?.consent &&
    isRecord(confirmation['adoption']) &&
    confirmation['chosen'] === chosenNow
      ? confirmation['adoption']
      : (reading?.adoption ?? {});
  /* The revision this panel drew, so a press from a page another tab has since moved on is refused before
     anything starts: the model would otherwise read words this reader never saw. */
  const expected = nextNumber(annotationOf(session)?.['revision']) || 0;
  const control = allow ? `reading-allow:${key}` : `reading:${key}`;
  const press = pendingStart(intent, control, 'Starting…', 'Starting the analysis.');
  if (!press) return;
  const note: Record<string, unknown> & { pending: boolean; message: string } = {
    pending: true,
    message: '',
    adoption,
    chosen: chosenNow,
  };
  held.requests.set(key, note);
  held.notify();
  let settled = false;
  try {
    const body: Record<string, unknown> = {
      harness: identity.harness,
      sid: identity.sid,
      provider,
      press: true,
      observer_model: 1,
      ...adoption,
      expected_revision: expected,
      ...(provider === 'claude' ? { model: String(route['model'] || '') } : {}),
      ...(allow
        ? {
            allow: true,
            words_destination: wordsTo,
            ...(destination ? { tool_output: destination } : {}),
          }
        : {}),
    };
    const reply = answered(
      await shell.runtime.client.postReading(body as unknown as ReadingRequest, press.signal),
    );
    if (reply.kind === 'lost') throw new Error('reading not confirmed');
    const answer: Row | null = reply.body as Row | null;
    const status = reply.status;
    if (isRecord(answer?.['route'])) {
      /* The server's route for this harness now. Kept before the refresh so the sentence below and the
         disclosure it points at agree at once. */
      showRoute(ctx, String(session['harness'] || ''), answer['route']);
    }
    if (status === 409 && isRecord(answer?.['job'])) {
      /* Another tab, or an earlier press, already started one: show it, then take the board's word for
         whether it is still running. */
      showJob(ctx, key, answer['job']);
      pendingEnd(intent, control, press);
      held.notify();
      await refresh(intent);
      return;
    }
    if (status === 409 && answer?.['reason'] === 'provider-changed') {
      /* Nothing was sent or saved. The next press starts again, and asks for the new receiver's own Allow if
         it has none. */
      note.message = PROVIDER_CHANGED;
      note['consent'] = false;
      await refresh(intent);
      return;
    }
    if (status === 409 && answer?.['reason'] === 'revision-changed') {
      /* Nothing was started, adopted or allowed. The owner's stale sentence, shared with Keep: the next press
         is the reader's, against the words the refresh now draws. */
      note.message = KEEP_REFUSED;
      note['consent'] = false;
      /* Said once, by the persistent region, as Keep's is and under Keep's key, which the next press
         empties: a status paragraph inside the page was re-inserted and re-read on every render. */
      note['announced'] = true;
      announce(intent, `keep:${key}`, KEEP_REFUSED);
      await refresh(intent);
      return;
    }
    if (status === 409 && answer?.['reason'] === 'destination-changed') {
      note.message = DESTINATION_CHANGED;
      note['consent'] = false;
      await refresh(intent);
      return;
    }
    if (status === 409) {
      note.message =
        'A reading is already in progress for this session. Wait for it to finish; this press did not start another.';
      return;
    }
    if (isRecord(answer?.['route']) && !answer['route']['provider']) {
      const now2 = currentPayload(ctx) ?? payload;
      note.message = routeRefusal(now2, session);
      note['refusal'] = true;
      return;
    }
    if (answer?.['reason'] === 'withheld' && typeof answer['withheld'] === 'string') {
      /* Refused before any job: nothing started and nothing was spent. Held as this press's answer until the
         board publishes the row's own eligibility, which then wins, so the inert line stands beside the
         button now rather than after the next poll. */
      const eligibility = {
        ok: false,
        reason: answer['withheld'],
        until: nextNumber(answer['until']),
        sentence: String(answer['sentence'] || ''),
      };
      note['eligibility'] = eligibility;
      note.message = pressLine(session, eligibility);
      acknowledgeFlip(ctx, session, false);
      note['refusal'] = true;
      note['consent'] = false;
      await refresh(intent);
      return;
    }
    if (answer?.['adoption_refused']) {
      note.message =
        'The prompt or saved goal changed. Review the current goal before analyzing again.';
      await refresh(intent);
      return;
    }
    if (isRecord(answer?.['reading'])) {
      showReading(ctx, answer['reading']);
      note.message = policyReason(answer['reading']);
      note['refusal'] = Boolean(note.message);
      note['consent'] = ['consent-required', 'tool-output-consent-required'].includes(
        String(answer['reading']['reason']),
      );
      return;
    }
    if (!reply.ok) throw new Error(`HTTP ${String(status)}`);
    const started = answer?.['ok'] === true && isRecord(answer['job']);
    if (!started && (answer?.['ok'] !== true || typeof answer['produced'] !== 'boolean')) {
      throw new Error('reading not confirmed');
    }
    if (allow) {
      const policy = (currentPayload(ctx) ?? payload)['reading'];
      if (isRecord(policy)) {
        const providers = isRecord(policy['providers']) ? policy['providers'] : {};
        const words = isRecord(policy['words']) ? policy['words'] : {};
        const rebind = { ...(isRecord(policy['rebind']) ? policy['rebind'] : {}) };
        delete rebind[provider];
        const output = isRecord(policy['tool_output']) ? policy['tool_output'] : {};
        const granted = Array.isArray(output[provider]) ? (output[provider] as unknown[]) : [];
        showReading(ctx, {
          ...policy,
          consent: true,
          providers: { ...providers, [provider]: true },
          words: { ...words, [provider]: true },
          rebind,
          ...(destination
            ? {
                tool_output: {
                  ...output,
                  [provider]: granted.includes(destination) ? granted : [...granted, destination],
                },
              }
            : {}),
        });
      }
    }
    if (started && answer && isRecord(answer['job'])) {
      /* Drawn now from the reply, then replaced by the board: a job can end before its own reply arrives,
         and a merged job the board has dropped would stand until the next poll and swallow every press.
         Every later phase and the result arrive with the revisions the job publishes. */
      showJob(ctx, key, answer['job']);
      // The box is the answer from here on, so the press stops being busy.
      pendingEnd(intent, control, press);
      held.notify();
      await refresh(intent);
      return;
    }
    /* Answered without a job: no annotated session by that name. */
    note.message = 'No new reading was produced.';
    await refresh(intent);
  } catch {
    /* A lost response does not establish that the model never ran. */
    note.message =
      'Could not confirm the reading. The request has not been retried. Refresh to check for a result before asking again.';
    note['consent'] = false;
  } finally {
    note.pending = false;
    pendingEnd(intent, control, press);
    held.requestFocus(`reading:${key}`);
    settled = true;
  }
  void settled;
}

/* "Not now" on the consent step: nothing is sent, allowed or recorded, and the idle button comes back. The
   adoption the step held goes with it. */
export function readingNotNow(ctx: DriftCtx, identity: SessionIdentity): void {
  const { intent } = ctx;
  const session = liveRow(intent, identity);
  if (!session) return;
  const key = compatSessKey(session);
  const request = intent.held.requests.get(key);
  // Not while Allow is being answered: that press is already the consent.
  if (pendingHas(intent, `reading-allow:${key}`)) return;
  if (request?.consent && !request.pending) intent.held.requests.delete(key);
  intent.held.notify();
}

/* What Keep's analysis asks of Analyze: one request, sent once, with the adoption and settlement a Keep
   names, and never an Allow. `settle_through` is the newest direction the reader was shown, and the
   revision is the one the list was drawn against. */
export async function keepReading(
  ctx: DriftCtx,
  identity: SessionIdentity,
  request: KeepAnalyzeRequest,
): Promise<KeepAnalyzeOutcome> {
  const { shell, intent } = ctx;
  const read = pressDetails(ctx, identity);
  if (!read) return { kind: 'refused' };
  const { session, payload, input } = read;
  const route = readingRoute(payload, session);
  if (!route || !route['provider']) return { kind: 'refused' };
  /* The card may still draw Analyze live while the board's close is held, and then Keep carries the Analyze
     label. A press is answered by what is true now: where the board says no reading can start, Keep settles
     and reads nothing, through the same route a Keep with no reading uses, and learns the board's state as
     an Analyze press during a held close does. */
  const now = shell.clock.now();
  const note = intent.held.requests.get(compatSessKey(session));
  const refusal = promptReadingRefusal({
    input,
    saving: pendingHas(intent, `${intentKey(session)}:save`),
    answered: note,
    nowMs: now,
  });
  if (refusal || readingJob(payload, session)) {
    if (refusal && refusal === pressRefusal(session, note, now))
      acknowledgeFlip(ctx, session, false);
    const settle = answered(
      await shell.runtime.client.postAnnotate(
        {
          ...identity,
          ...request.adoption,
          settle_through: request.through,
          expected_revision: request.expected,
        },
        request.signal,
      ),
    );
    const done = settle.kind === 'answered' && settle.ok ? (settle.body as Row | null) : null;
    if (!done || done['ok'] !== true) throw new Error('not kept');
    const outcome = String(done['outcome'] || '');
    return ['stored', 'unchanged'].includes(outcome) && done['persisted'] !== false
      ? { kind: 'ended', settled: true, why: '' }
      : { kind: 'refused' };
  }
  const provider = String(route['provider']);
  const body: Record<string, unknown> = {
    harness: identity.harness,
    sid: identity.sid,
    provider,
    press: true,
    observer_model: 1,
    ...request.adoption,
    settle_through: request.through,
    expected_revision: request.expected,
    ...(provider === 'claude' ? { model: String(route['model'] || '') } : {}),
  };
  const reply = answered(
    await shell.runtime.client.postReading(body as unknown as ReadingRequest, request.signal),
  );
  if (reply.kind === 'lost' || !reply.body) throw new Error('not confirmed');
  const answer = reply.body as Row;
  if (answer['adoption_refused'] || reply.status === 422) return { kind: 'refused' };
  const key = compatSessKey(session);
  const settledOutcome = ['stored', 'unchanged'].includes(String(answer['settled'] || ''));
  if (isRecord(answer['route'])) showRoute(ctx, String(session['harness'] || ''), answer['route']);
  if (isRecord(answer['reading'])) showReading(ctx, answer['reading']);
  if (reply.ok && answer['ok'] === true && isRecord(answer['job'])) {
    showJob(ctx, key, answer['job']);
    return { kind: 'started' };
  }
  if (reply.status === 409 && isRecord(answer['job'])) showJob(ctx, key, answer['job']);
  const latest = currentPayload(ctx) ?? payload;
  const why =
    answer['reason'] === 'provider-changed'
      ? PROVIDER_CHANGED
      : answer['reason'] === 'destination-changed'
        ? DESTINATION_CHANGED
        : isRecord(answer['reading'])
          ? policyReason(answer['reading'])
          : isRecord(answer['route']) && !answer['route']['provider']
            ? routeRefusal(latest, session)
            : '';
  return { kind: 'ended', settled: settledOutcome, why };
}

/* Cancel the running analysis this box shows. The job id goes with it, so a stale tab cannot cancel a newer
   press. One request per job: a Cancel in flight, or one the server already accepted, sends nothing. A `409
   not-running` means the job ended or was never this one, and the board says what stands, with no sentence of
   this page's own. */
export async function cancelReading(ctx: DriftCtx, identity: SessionIdentity): Promise<void> {
  const { intent, shell, drift } = ctx;
  const read = pressDetails(ctx, identity);
  if (!read) return;
  const { session, payload } = read;
  const key = compatSessKey(session);
  const job = readingJob(payload, session);
  const held = drift.cancels.get(key);
  if (!job || job['cancelling'] === true || (held && held.job === job['id'] && held.pending))
    return;
  const control = `reading-cancel:${key}`;
  const press = pendingStart(intent, control, 'Cancelling…', 'Cancelling the analysis.');
  if (!press) return;
  const cancel = { job: String(job['id']), pending: true, failed: false };
  drift.cancels.set(key, cancel);
  drift.notify();
  try {
    const reply = answered(
      await shell.runtime.client.postReadingCancel(
        { ...identity, job: cancel.job, press: true, observer_model: 1 },
        press.signal,
      ),
    );
    if (reply.kind === 'lost') throw new Error('cancel not confirmed');
    const answer = reply.body as Row | null;
    if (reply.status === 409 && answer?.['reason'] === 'not-running') {
      pendingEnd(intent, control, press);
      drift.cancels.delete(key);
      await refresh(intent);
      return;
    }
    if (reply.status !== 202 || !answer || answer['cancelling'] !== true) {
      throw new Error('cancel not confirmed');
    }
    // Accepted: the published `cancelling` draws the finishing state from here.
    pendingEnd(intent, control, press);
    showJob(ctx, key, { ...job, cancelling: true });
    drift.cancels.delete(key);
    await refresh(intent);
  } catch {
    cancel.failed = true;
  } finally {
    cancel.pending = false;
    pendingEnd(intent, control, press);
    drift.notify();
    intent.held.requestFocus(control);
  }
}

/* "Turn off readings": withdraws every provider's permission. The one request in this section that names no
   session, so the control is keyed on the session the reader is looking at. */
export async function readingOff(ctx: DriftCtx, identity: SessionIdentity | null): Promise<void> {
  const { intent, shell } = ctx;
  const key = identity ? compatSessKey(identity) : '';
  const control = key ? `reading-off:${key}` : 'reading-off';
  const press = pendingStart(intent, control, 'Turning off…', 'Turning off readings.');
  if (!press) return;
  intent.held.notify();
  try {
    const reply = answered(
      await shell.runtime.client.postReading(
        { consent: 'off', press: true, observer_model: 1 } as unknown as ReadingRequest,
        press.signal,
      ),
    );
    const answer = reply.kind === 'answered' && reply.ok ? (reply.body as Row | null) : null;
    if (!answer || answer['ok'] !== true || !isRecord(answer['reading'])) {
      throw new Error('permission not saved');
    }
    showReading(ctx, answer['reading']);
    for (const [name, note] of [...intent.held.requests]) {
      if (!note.pending) intent.held.requests.delete(name);
    }
    await refresh(intent);
  } catch {
    if (key) {
      intent.held.requests.set(key, {
        message: 'Could not confirm readings are off. Try turning them off again.',
      });
    }
  } finally {
    pendingEnd(intent, control, press);
    intent.held.requestFocus(control);
  }
}

/* The reader's answer, posted to the same route their words go to, with the reading's time so a newer one is
   never marked by a tab drawn before it. Pressed again it takes the mark back. It is never sent anywhere
   else and never counted. The mark and its pressed state derive from the payload, never from this press: a
   store that did not take it draws unmarked and says so. */
export async function markNotAccurate(
  ctx: DriftCtx,
  identity: SessionIdentity,
  readAt: number,
): Promise<void> {
  const { intent, shell, drift } = ctx;
  const session = liveRow(intent, identity);
  if (!session) return;
  const key = compatSessKey(session);
  const control = `not-accurate:${key}`;
  const press = pendingStart(intent, control, 'Saving…');
  if (!press) return;
  intent.held.notify();
  const annotation = annotationOf(session);
  const on = !(annotation?.['not_accurate'] === true);
  drift.notAccurate.delete(key);
  let saved = false;
  try {
    const reply = answered(
      await shell.runtime.client.postAnnotate(
        { ...identity, not_accurate: on, read_at: readAt },
        press.signal,
      ),
    );
    const body = reply.kind === 'answered' && reply.ok ? (reply.body as Row | null) : null;
    saved = Boolean(
      body &&
        body['persisted'] !== false &&
        ['stored', 'unchanged'].includes(String(body['outcome'] || '')),
    );
  } catch {
    saved = false;
  }
  if (!saved) drift.notAccurate.add(key);
  try {
    await refresh(intent);
  } finally {
    pendingEnd(intent, control, press);
    drift.notify();
    intent.held.requestFocus(control);
  }
}

export { CANCEL_FAILED, RESULT_MARK_UNSAVED, identityOf };
