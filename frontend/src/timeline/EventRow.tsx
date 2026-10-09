import type { ReactNode } from 'react';
import { Disclosure } from '../controls/Disclosure';
import { formatDuration } from '../shell/format';
import { GraphRail } from './Lanes';
import { laneStyle, type Flow } from './rails';
import { ScopeCue } from './ScopeCue';
import { timelineDisclosureKey, timelineFocusKey, type RowScope } from './scope';
import {
  eventKind,
  eventSentence,
  factScope,
  gateApplicationDisposition,
  taskTitle,
  type Fact,
  type Lane,
  type TaskLane,
  type TimelineEvent,
} from './semantic';

/* One event of the semantic timeline. Ported from `projectGlobalEventRow`, `projectGlobalEventDetails`,
   `projectPublishedValue`, `projectEventTime` and `projectGraphRow` in the legacy `project.js`; the lane
   rail drawn beside the row is the project step's. */

/* A value the payload published, or the plain statement that it did not. Never a blank and never a guess. */
function Published({ value, reason }: { readonly value: unknown; readonly reason: string }) {
  return value !== null && value !== undefined && String(value).trim() !== '' ? (
    <span className="pc-source">{String(value)}</span>
  ) : (
    <span className="pc-substrate-reason">{reason}</span>
  );
}

function EventTime({ at }: { readonly at: number | null }) {
  const date = at === null ? null : new Date(at * 1000);
  if (!date || !Number.isFinite(date.getTime()))
    return <span className="pc-substrate-reason">Event time not published.</span>;
  const iso = date.toISOString();
  return <time dateTime={iso}>{iso}</time>;
}

function relationLines(event: TimelineEvent): string[] {
  const { lane } = event;
  return event.relations.map((relation) => {
    if (relation.type === 'dispatches_to')
      return `Exact dispatch · First Officer → ${taskTitle(lane.label)}`;
    if (relation.type === 'returns_to')
      return `Exact return · ${taskTitle(lane.label)} → First Officer`;
    return (relation.type || 'supported relation').replace(/_/g, ' ');
  });
}

function Details({ event, scope }: { readonly event: TimelineEvent; readonly scope: RowScope }) {
  const { fact, lane } = event;
  const bindings = lane.kind === 'task' ? lane.item.bindings : [];
  const relations = relationLines(event);
  const matching =
    event.kind === 'dispatch'
      ? lane.events.filter(
          (candidate) =>
            eventKind(candidate) === 'dispatch' &&
            candidate.summary.trim().toLowerCase() === event.meaning.trim().toLowerCase(),
        )
      : [];
  const path = fact.stage && fact.targetStage ? `${fact.stage} → ${fact.targetStage}` : fact.stage;
  const author = fact.by === 'person:captain' ? 'Captain' : fact.by;
  const disposition = gateApplicationDisposition(fact);
  return (
    <div className="pc-entry-details">
      <div>
        <b>Why included</b> · {event.rationale || 'Inclusion reason not published.'}
      </div>
      {event.kind === 'decision' ? (
        <>
          <div>
            <b>Decision author</b> ·{' '}
            <Published value={author || null} reason="Decision author not published." />
          </div>
          <div {...(path.trim() ? { className: 'pc-source' } : {})}>
            <b>Decision mechanics</b> ·{' '}
            {path.trim() ? path : <Published value={null} reason="Decision stage not published." />}
            {!fact.stage && fact.targetStage ? (
              <>
                {' '}
                Target stage: <Published value={fact.targetStage} reason="" />
              </>
            ) : null}
            {' · '}
            {fact.applicationState ? (
              disposition
            ) : (
              <span className="pc-substrate-reason">{disposition}</span>
            )}
          </div>
        </>
      ) : null}
      <div>
        <b>Source</b> ·{' '}
        <Published
          value={fact.evidenceSource ?? (fact.sourceKind || null)}
          reason="Evidence source not published."
        />{' '}
        · <Published value={fact.evidenceConfidence} reason="Evidence confidence not published." />{' '}
        · <EventTime at={fact.at} />
      </div>
      {relations.length ? (
        <div>
          <b>Relation</b> · {interleave(relations)}
        </div>
      ) : null}
      {bindings.length ? (
        <div>
          <b>Task source</b> ·{' '}
          {interleave(
            bindings.map((binding) => (
              <>
                <Published value={binding.source} reason="Task source not published." /> ·{' '}
                <Published value={binding.value} reason="Task binding not published." />
              </>
            )),
          )}
        </div>
      ) : null}
      {matching.length > 1 ? (
        <div>
          <b>Assignment records</b> · {matching.length} exact records; {matching.length - 1} older
          matching record{matching.length === 2 ? '' : 's'} folded here.
        </div>
      ) : null}
      {event.suppressed.length ? (
        <Disclosure
          disclosureKey={timelineDisclosureKey(scope, `timeline-suppressed:${event.eventId}`)}
          focusKey={timelineFocusKey(scope, `timeline-suppressed:${event.eventId}`)}
          summary={`Source-only messages · ${String(event.suppressed.length)}`}
          className="pc-entry-suppressed"
        >
          <div className="pc-entry-source-list">
            {event.suppressed.map((row: Fact, index) => (
              <div key={`${row.id}:${String(index)}`}>
                <EventTime at={row.at} /> ·{' '}
                <Published value={row.summary || row.type} reason="Source message not published." />
              </div>
            ))}
          </div>
        </Disclosure>
      ) : null}
    </div>
  );
}

function interleave(nodes: ReactNode[]): ReactNode {
  return nodes.map((node, index) => (
    // The list is positional and never reordered; a line has no identity of its own.
    <span key={index}>
      {index > 0 ? <br /> : null}
      {node}
    </span>
  ));
}

/* The first row of a task lane carries its status, its workers and how many times it was dispatched. */
function taskHead(lane: TaskLane, event: TimelineEvent, stage: string) {
  const workers = lane.contributors
    .map((row) => row.worker)
    .filter(Boolean)
    .join(' · ');
  const meta = lane.working
    ? ['Working', stage].filter(Boolean).join(' · ')
    : lane.unreturned
      ? 'Unresolved'
      : taskTitle(event.kind);
  const secondary = lane.working
    ? workers
    : lane.unreturned
      ? 'No active worker · no return observed'
      : '';
  const retries = Math.max(0, lane.dispatchCount - 1);
  const attempts =
    lane.dispatchCount === 1
      ? '1 dispatch'
      : lane.dispatchCount > 1
        ? `${String(lane.dispatchCount)} dispatches${lane.retryEvidence ? ` · ${String(retries)} ${retries === 1 ? 'retry' : 'retries'}` : ''}`
        : '';
  return { meta, secondary, attempts };
}

export interface EventRowProps {
  readonly event: TimelineEvent;
  readonly scope: RowScope;
  /** First event of its lane in the list, which is the one that names the lane. */
  readonly first: boolean;
  /** The board's `generated`, which an event's age is measured against. */
  readonly generated: number | null;
  /** The harness labels the board published, for the scope cue's detail. */
  readonly harnessLabels: ReadonlyMap<string, string>;
  /** Every lane of the registry, in order: the rail beside the row has one cell for each. */
  readonly lanes: readonly Lane[];
  /** Where each lane's line runs through this row. */
  readonly flows: ReadonlyMap<string, Flow>;
}

export function EventRow({
  event,
  scope,
  first,
  generated,
  harnessLabels,
  lanes,
  flows,
}: EventRowProps) {
  const { fact, lane } = event;
  const stage =
    fact.stage || (first && lane.kind === 'task' && lane.head ? lane.head.stage : '') || '';
  const sentence = eventSentence(event);
  const head = lane.kind === 'task' && first ? taskHead(lane, event, stage) : null;
  const title = lane.kind === 'fo' ? 'First Officer' : taskTitle(lane.label);
  const sourceResult =
    event.kind !== 'decision' &&
    ((fact.summary !== '' && sentence.result === fact.summary) ||
      (fact.stage !== '' && sentence.result === fact.stage));
  const hasTime = event.at !== null && Number.isFinite(event.at);
  const age =
    hasTime && generated !== null && event.at !== null ? (
      <time>{`${formatDuration(Math.max(0, generated - event.at)) ?? '0s'} ago`}</time>
    ) : (
      <span className="pc-substrate-reason pc-graph-time">
        {hasTime ? 'Observation time not published.' : 'Event time not published.'}
      </span>
    );
  const cue = factScope(fact);
  const detail =
    cue.kind === 'session' && fact.session
      ? (harnessLabels.get(fact.session.harness) ?? humanLabel(fact.session.harness))
      : undefined;
  const task = lane.kind === 'task' ? lane : null;
  const binding = task && first ? bindingOf(task, fact) : '';
  const attributes: Record<string, string> = {
    'data-event-id': event.eventId,
    'data-semantic-kind': event.kind,
    'data-inclusion-rationale': event.rationale || 'changes work understanding',
  };
  if (!task) {
    if (event.kind === 'direction') {
      attributes['data-steering-state'] =
        event.causal && event.causal !== 'none' ? 'paired' : 'unpaired';
      attributes['data-causal-edge'] = event.causal ?? 'none';
    }
  } else {
    attributes['data-assignment-lane'] = first ? 'task-head' : 'task-event';
    attributes['data-work-item'] = task.workItemId;
    attributes['data-task-current'] = task.current ? 'true' : 'false';
    if (task.contributors[0])
      attributes['data-parent-session'] = task.contributors[0].parentSession ?? '';
    if (first) attributes['data-trail-head'] = task.head?.status || 'latest';
    if (stage) attributes['data-work-stage'] = stage;
    if (binding) attributes['data-workflow-binding'] = binding;
  }
  const kindClass = event.kind === 'direction' ? 'steering' : 'event';
  return (
    <article
      className={`pc-graph-row ${kindClass}`}
      data-graph-node={kindClass}
      data-lane-key={lane.key}
      style={laneStyle(
        lanes.length,
        lanes.findIndex((candidate) => candidate.key === lane.key),
      )}
      {...(flows.size ? { 'data-lane-connect': 'next' } : {})}
      {...attributes}
    >
      {age}
      <GraphRail
        lanes={lanes}
        active={lane}
        kind={kindClass}
        tip={event.meaning}
        hasEvent={hasTime}
        flows={flows}
      />
      <div className="pc-trail-body">
        <ScopeCue scope={cue} detail={detail} />
        <Disclosure
          disclosureKey={timelineDisclosureKey(scope, `timeline-event:${event.eventId}`)}
          focusKey={timelineFocusKey(scope, `timeline-event:${event.eventId}`)}
          className="pc-timeline-event"
          summary={
            <>
              <div className="pc-trail-summary">
                <div className="pc-trail-top">
                  {first ? (
                    <strong className="pc-lane-title">{title}</strong>
                  ) : (
                    <span className="pc-event-kind">{taskTitle(event.kind)}</span>
                  )}
                  {first ? <span>{head ? head.meta : taskTitle(event.kind)}</span> : null}
                </div>
                <div
                  className="pc-trail-result"
                  data-actor={sentence.actor}
                  data-action={sentence.action}
                  data-object={sentence.object}
                  data-result={sentence.result}
                >
                  {event.kind === 'decision' ? (
                    <>
                      <strong>{taskTitle(sentence.action)}</strong> {sentence.object} ·{' '}
                      {gateApplicationDisposition(fact)}
                    </>
                  ) : (
                    <>
                      <strong>{sentence.actor}</strong> {sentence.action} {sentence.object} ·{' '}
                      {sourceResult ? (
                        <Published value={sentence.result} reason="Event summary not published." />
                      ) : (
                        sentence.result
                      )}
                    </>
                  )}
                </div>
                {head?.secondary ? <div className="pc-trail-quiet">{head.secondary}</div> : null}
                {head?.attempts ? (
                  <div className="pc-trail-quiet" data-dispatch-count={task?.dispatchCount ?? 0}>
                    {head.attempts}
                  </div>
                ) : null}
              </div>
            </>
          }
        >
          <Details event={event} scope={scope} />
        </Disclosure>
      </div>
    </article>
  );
}

function bindingOf(lane: TaskLane, fact: Fact): string {
  const bindings = lane.item.bindings.length
    ? lane.item.bindings
    : fact.workflowBinding
      ? [{ source: 'task state', value: `${fact.workflowBinding}:${fact.workflowEntity}` }]
      : [];
  if (!bindings.length) return '';
  return fact.workflowBinding || (bindings[0]?.value ?? '').split(':')[0] || '';
}

function humanLabel(value: string): string {
  const words = (value || 'work').replace(/[-_]+/g, ' ').trim();
  return words ? (words[0] ?? '').toUpperCase() + words.slice(1) : 'Work';
}
