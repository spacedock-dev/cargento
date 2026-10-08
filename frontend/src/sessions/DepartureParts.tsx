import { CopyControl, RaiseControl, resumeCommand, useControls } from '../controls';
import { delegatedWork, type Row } from '../observed';
import { unaskedDepartures, type DepartureRow } from './detail';

/* The pieces of the session page that sit beside the Intent panel's reading and are measured evidence in
   their own right: what became of a departure raised to the reader, the way back into the session beside
   it, and what the session launched that nobody has seen finish. The Intent step composes them into its
   panel; this step draws them in the panel's slot until that panel exists, so a raise on record is never
   hidden by the panel being absent. Each takes the session row and nothing else it could get wrong. */

/* The way back into the session beside a departure. Cargento never writes into a session, so acting on
   drift means putting the reader back in it: the command that harness's CLI takes to resume it, and the raise
   where one was measured. Both are the header's own controls, so a cue written by one is swept onto the
   other. The raise draws whatever the session's state, which is the difference from the header, where it is
   offered only while the session waits on the reader. Only what exists is drawn; what does not is said once
   for the section, never repeated under every departure. */
export function DepartureReentry({ session }: { readonly session: Row }) {
  const controls = useControls();
  const harness = String(session['harness'] || '');
  const sid = String(session['sid'] || '');
  const command = resumeCommand(harness, String(session['resume_id'] || ''));
  const raisable = session['focusable'] === true && Boolean(sid.trim()) && Boolean(String(session['harness'] == null ? '' : session['harness']).trim()) && controls.focus !== null;
  if (!command && !raisable) return null;
  return (
    <div className="next-departure-reentry" data-next-departure-reentry>
      {command ? <CopyControl kind="command" harness={harness} sid={sid} value={command} /> : null}
      {raisable ? <RaiseControl harness={String(session['harness']).trim()} sid={sid.trim()} focusable /> : null}
    </div>
  );
}

function DepartureRowView({ row, session }: { readonly row: DepartureRow; readonly session: Row }) {
  return (
    <div className="next-session-departure">
      <div className="next-session-departure-head">
        <span className="next-session-departure-name">{row.constraint}</span>
        {row.at ? <span className="next-session-departure-at">{row.at}</span> : null}
      </div>
      {row.clause ? <span className="next-session-departure-clause">{row.clause}</span> : null}
      <p className="next-session-departure-reading">{row.reading}</p>
      <p className="next-session-departure-base">{row.base}</p>
      {row.stale ? <p className="next-session-departure-stale">{row.stale}</p> : null}
      {row.followUp ? <p className="next-session-departure-next">{row.followUp}</p> : null}
      <DepartureReentry session={session} />
    </div>
  );
}

/* The rows and the absence sentence, in one wording for every surface that shows them. The heading counts,
   and each row says when and against which revision: a raise that did not say which words it read and where
   its evidence stopped cannot be checked by the person it was raised to. Nothing for a session with no
   departure and no sentence about why. */
export function UnaskedDepartureBody({ session }: { readonly session: Row }) {
  const body = unaskedDepartures(session);
  if (!body) return null;
  return (
    <>
      {body.rows.length ? <p className="next-session-departures-count">{body.heading}</p> : null}
      {body.rows.map((row, index) => (
        <DepartureRowView key={index} row={row} session={session} />
      ))}
      {body.why ? <p className="next-session-departures-why">{body.why}</p> : null}
      {body.absence ? <p className="next-session-delivery-why">{body.absence}</p> : null}
    </>
  );
}

/* What the session launched. Counts concern recorded launches; unpaired and activity concern this session's
   own launches, and an unread child is never a completed job. Drawn only where a launch was recorded or its
   time was, so a session that never delegated says nothing; the check beneath it appears only when the
   silence has lasted half an hour with a launch unpaired. */
export function DelegatedWorkLine({ session, now }: { readonly session: Row; readonly now: number | null }) {
  const work = delegatedWork(session, now);
  if (!work.draw) return null;
  return (
    <>
      <p data-next-delegated-work>{work.text}</p>
      {work.risky ? <p data-next-delegated-check>Is the work this session launched still running? Show its process and latest output.</p> : null}
    </>
  );
}
