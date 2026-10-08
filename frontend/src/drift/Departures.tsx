import { nextNumber } from '../api/bootstrap';
import { isRecord, type Row } from '../observed';
import { DepartureEvidence } from '../sessions/DepartureParts';
import { reentryLimit, sessionDelivery } from '../sessions/detail';
import { useShell } from '../shell/context';
import { useDrift } from './context';
import { DEPARTURE_DEFINITION, STEER_BY_HAND, STEER_BY_HAND_WHY, UNVERIFIABLE } from './sentences';
import { Why } from './Why';

/* The section where a raise is reviewed, and it holds two collections rather than one. A reading the reader
   asked for raises departures inside itself; the unasked lane raises them on its own, into a durable store,
   with a different lifetime and a different citation vocabulary. Merging them into one list would make a
   citation ambiguous about which collection it belongs to, so each keeps its own labelled part, and under it
   what became of the raise and the figures. The legacy page's `nextCockpitDepartures` is the oracle. */

/* The lane's rows, counted once and used for the delivery part and the figure: the delivery part is printed
   only where one of THESE stands, because only this lane raises a notification. `departure_checked` and not
   the list's own length, because an empty list is two different facts: the lane publishes `[]` for a session
   it read and found nothing in AND for one it has never reached, and only the first is a figure. With the
   lane off the figure is the rows this section actually drew, and only where it drew some: a switch that is
   off publishes no capability key and a length read off a list the base session declares empty on every row
   would report the schema. */
function laneCount(payload: Row, session: Row): number | null {
  const laneOn = payload['unasked'] === true;
  const rows = Array.isArray(session['departures']) ? (session['departures'] as unknown[]) : null;
  if (!rows) return null;
  const counted = laneOn
    ? rows.length > 0 || session['departure_checked'] === true
    : rows.length > 0;
  return counted ? rows.length : null;
}

/* The count of departures the reading raised, from one derivation over one collection. `null` on every branch
   that renders no rows because it could not read the collection: no reading, a reading this build cannot
   parse, or a payload whose observed record has not landed, so the citations cannot resolve. Zero is a
   figure: the reading was read, and it raised nothing. */
function readingCount(
  shape: {
    readonly malformed: string;
    readonly departures: readonly unknown[];
    readonly criteria: readonly { readonly result: string }[];
  } | null,
  state: string,
): number | null {
  if (!shape || shape.malformed) return null;
  if (state !== 'read') return null;
  if (
    !shape.departures.length &&
    shape.criteria.length &&
    shape.criteria.every((row) => row.result === UNVERIFIABLE)
  ) {
    return 0;
  }
  return shape.departures.length;
}

function Line({ label, value }: { readonly label: string; readonly value: number | null }) {
  return (
    <div className="next-cockpit-count">
      <span className="next-cockpit-count-label">{label}</span>
      <span
        className="next-cockpit-count-value"
        {...(value === null ? { 'data-next-absent': '' } : {})}
      >
        {value === null ? 'not published' : String(value)}
      </span>
    </div>
  );
}

/* The figures, as labelled lines with no arithmetic between them. Attempts and hand-overs are different
   questions and a ratio answers neither. One line per collection: each figure is derived from exactly the rows
   its own part rendered. A figure the payload does not carry says so rather than rendering zero. */
function Counts({
  fromReading,
  fromLane,
}: {
  readonly fromReading: number | null;
  readonly fromLane: number | null;
}) {
  const { model } = useDrift();
  const counts = model.payload['delivery_counts'];
  const record = isRecord(counts) ? counts : null;
  const board = record ? nextNumber(record['raises']) : null;
  if (!record || (fromLane === null && !board)) return null;
  return (
    <div className="next-cockpit-departure-part">
      <span className="next-cockpit-departure-label">COUNTS</span>
      <div className="next-cockpit-departure-counts">
        <span className="next-cockpit-count-group">DEPARTURES</span>
        <Line label="From the reading you asked for" value={fromReading} />
        <Line label="From the checks run while you were away" value={fromLane} />
        <span className="next-cockpit-count-group">RAISES</span>
        <Line label="On record for this board" value={board} />
        <Line label="This board attempted" value={nextNumber(record['attempted'])} />
        <Line label="A notification service accepted" value={nextNumber(record['handed_over'])} />
      </div>
      <p className="next-cockpit-reading-why">Five figures, and no arithmetic between them.</p>
      <Why
        name="counts-why"
        summary="What a count does not say"
        body="A count identifies a session worth reading; it establishes nothing about whether the brief, the agent or Cargento’s own judgement was poor, and those three are not separable from it."
      />
    </div>
  );
}

/* What became of the raise, beside the raise. `deliveries` owns every sentence and this chooses only whether to
   print. Two gates, both measured missing: a departure from the unasked lane actually rendered above, and the
   figures taken from `delivery_departure` rather than the flat keys, which carry the latest raise of ANY
   lane. */
function Delivery({ session, standing }: { readonly session: Row; readonly standing: boolean }) {
  if (!standing) return null;
  const scoped = session['delivery_departure'];
  const delivery = isRecord(scoped) ? sessionDelivery(scoped) : null;
  if (!delivery) return null;
  return (
    <div
      className="next-cockpit-departure-part"
      data-next-delivery={delivery.outcome}
      {...(delivery.mixed ? { 'data-next-delivery-mixed': 'true' } : {})}
    >
      <span className="next-cockpit-departure-label">HOW IT WAS RAISED</span>
      <p className="next-session-delivery-count">{delivery.count}</p>
      {delivery.why ? <p className="next-session-delivery-why">{delivery.why}</p> : null}
      {delivery.mixed && delivery.mixedWhy ? (
        <p className="next-session-delivery-note">{delivery.mixedWhy}</p>
      ) : null}
      {delivery.bindingWhy ? (
        <p className="next-session-delivery-note">{delivery.bindingWhy}</p>
      ) : null}
      {delivery.laneWhy ? <p className="next-session-delivery-lane">{delivery.laneWhy}</p> : null}
    </div>
  );
}

export function DeparturesSection() {
  const { model } = useDrift();
  const shell = useShell();
  const { session, payload } = model;
  const lane = laneCount(payload, session);
  const rows = Array.isArray(session['departures'])
    ? (session['departures'] as unknown[]).length
    : 0;
  /* Drawn only where the unasked lane holds rows, collapsed under their count. The reading's own departures
     are said once, in the result that stands in the control's place, so this section does not repeat them;
     "nothing watches" and the off switch's reason go with the section, because a session with nothing raised
     has nothing for them to qualify. A raise on record is drawn whichever way the switch is set.

     One exception, and it is an absence rather than a row: with the lane on and nothing raised, the lane's own
     sentence -- not checked, checked and found nothing, or a cap spent -- stays in view, because those are
     three different facts and silence would read as the reassuring one. */
  const laneOn = payload['unasked'] === true;
  const why =
    laneOn && !rows ? String(session['departure_why'] == null ? '' : session['departure_why']) : '';
  if (!rows && !why) return null;
  const sid = String(session['sid'] || '').trim();
  const raisable =
    session['focusable'] === true &&
    Boolean(sid) &&
    Boolean(String(session['harness'] == null ? '' : session['harness']).trim()) &&
    shell.controls.focus !== null;
  const raiseLine = raisable
    ? reentryLimit({
        label: '',
        hasCommand: true,
        knownHarness: true,
        canRaise: true,
        focusCapability: true,
      }).raise
    : '';
  const summary = rows ? `Raised while you were away: ${String(rows)}` : 'About these checks';
  const evidence = (
    <DepartureEvidence
      session={session}
      laneOn={laneOn}
      offReason={payload['unasked_off_reason']}
    />
  );
  return (
    <section className="next-cockpit-departures">
      {rows ? null : evidence}
      <Why name="departures" summary={summary}>
        <p className="next-cockpit-define">{DEPARTURE_DEFINITION}</p>
        {rows ? (
          <>
            {evidence}
            {raiseLine ? (
              <p className="next-departure-reentry-why" data-absence="not-observed">
                {raiseLine}
              </p>
            ) : null}
          </>
        ) : null}
        <Delivery session={session} standing={Boolean(lane)} />
        <Counts
          fromReading={model.annotate ? readingCount(model.shape, model.source.state) : null}
          fromLane={lane}
        />
        <p className="next-cockpit-reading-why">{STEER_BY_HAND}</p>
        <Why name="steer-why" summary="Why no raise goes further" body={STEER_BY_HAND_WHY} />
      </Why>
    </section>
  );
}
