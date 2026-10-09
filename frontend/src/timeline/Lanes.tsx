import { Disclosure } from '../controls/Disclosure';
import { laneStyle, type Flow } from './rails';
import { timelineDisclosureKey, timelineFocusKey, type RowScope } from './scope';
import { taskTitle, type Delegation, type Lane } from './semantic';

/* The lane furniture around the timeline's rows: the legend naming each lane, the rail beside a row with its
   mark, and the strip for workers that belong to no work item. Ported from `projectLaneLegend`,
   `projectLaneRails` and `projectUnboundContext` in the legacy `project.js`. The lanes are ALL of the
   registry's, not the ones the filter kept, so a lane's column does not move when the reader changes the
   filter. */
export function LaneLegend({ lanes }: { readonly lanes: readonly Lane[] }) {
  return (
    <div className="pc-lane-legend" style={laneStyle(lanes.length)}>
      <span />
      <span className="pc-lane-labels">
        {lanes.map((lane) => (
          <span key={lane.key} title={lane.label}>
            {lane.kind === 'fo' ? lane.label : taskTitle(lane.label)}
          </span>
        ))}
      </span>
    </div>
  );
}

/* The mark is drawn only where the row has a time, because a mark with no moment to stand for would claim
   the event happened. */
export function GraphRail({
  lanes,
  active,
  kind,
  tip,
  hasEvent,
  flows,
}: {
  readonly lanes: readonly Lane[];
  readonly active: Lane;
  readonly kind: string;
  readonly tip: string;
  readonly hasEvent: boolean;
  readonly flows: ReadonlyMap<string, Flow>;
}) {
  return (
    <span className="pc-graph-rail">
      {lanes.map((lane) => {
        const flow = flows.get(lane.key);
        return (
          <span
            key={lane.key}
            className={`pc-rail-cell${lane.key === active.key ? ' active' : ''}${flow ? ` flow-${flow}` : ''}`}
            data-rail-key={lane.key}
            {...(flow ? { 'data-flow-key': lane.key } : {})}
          >
            {hasEvent && lane.key === active.key ? (
              <span className={`pc-graph-mark ${kind}`} {...(tip ? { title: tip } : {})} />
            ) : null}
          </span>
        );
      })}
    </span>
  );
}

/* Workers the First Officer started that no work item has claimed. Said once, with each worker's assignment
   and where it came from, so a worker with no task is a stated fact and not a missing row. */
export function UnboundContext({
  contributors,
  scope,
}: {
  readonly contributors: readonly Delegation[];
  readonly scope: RowScope;
}) {
  if (!contributors.length) return null;
  const count = contributors.length;
  return (
    <div className="pc-unbound-context">
      <div className="pc-trail-top">
        <strong className="pc-lane-title">First Officer</strong>
        <span>Context</span>
      </div>
      <Disclosure
        disclosureKey={timelineDisclosureKey(scope, 'fo-contributors')}
        focusKey={timelineFocusKey(scope, 'fo-contributors')}
        className="pc-trail-history pc-fo-context"
        summary={`${String(count)} unbound contributor${count === 1 ? '' : 's'}`}
      >
        {contributors.map((row, index) => {
          const name = `fo-contributor:${row.observerSid || row.worker || String(index)}`;
          return (
            // Two workers can share a name; the position keeps their rows apart.
            <div className="pc-trail-event" key={`${name}#${String(index)}`}>
              <strong>{row.assignment}</strong>
              <span>{row.worker}</span>
              <Disclosure
                disclosureKey={timelineDisclosureKey(scope, name)}
                focusKey={timelineFocusKey(scope, name)}
                className="pc-event-evidence"
                summary="evidence"
              >
                <div>{row.source}</div>
              </Disclosure>
            </div>
          );
        })}
      </Disclosure>
    </div>
  );
}
