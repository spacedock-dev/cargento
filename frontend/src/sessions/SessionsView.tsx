import { buttonVariants } from '../ui/button';
import { cn } from '../lib/utils';
import { useMemo, type MouseEvent, type ReactNode } from 'react';
import { CapacityStrip } from '../capacity';
import { Disclosure, disclosureKey, CopyControl } from '../controls';
import { gapNames, isScanOnly, type Row } from '../observed';
import { fragmentForRoute, type RouteInput } from '../router/grammar';
import { selectObserved } from '../observed/select';
import { selectHarnessSources } from '../store/selectors';
import { useDisplayed, useNavigate, useShell } from '../shell/context';
import { buildSessionsScreen, NOT_CHECKED, type SessionRow } from './rows';
import { sessionInstruction, type PromptCandidate } from './intent';
import { goalFocusFor } from './heldState';
import {
  BOARD_WHY,
  DUPLICATE_LABEL_LIMIT,
  GOAL_SOURCES_OFF,
  GOAL_SOURCES_ON,
  RECENT_WHY,
  SCAN_ONLY_LINE,
  SCAN_ONLY_NOTE,
  UNREAD_SOURCE_NOTE,
} from './notes';
import './sessions.css';

/* The Sessions screen: one row per exact session, the blocked and moving ones first, each with the goal
   it was given and whether it has drifted. A pure render of one payload: every figure comes from the
   model read from the rows being drawn, so the fleet facts, the groups and the header cannot disagree.
   Nothing here fetches, polls or acts; a row's controls act only when pressed. */

export function StatusDot({
  label,
  className,
  filled = true,
}: {
  readonly label: string;
  readonly className?: string;
  readonly filled?: boolean;
}) {
  return (
    <span
      className={className ? `next-status-dot ${className}` : 'next-status-dot'}
      aria-label={label}
    >
      {filled ? '●' : '○'}
    </span>
  );
}

/* A link to a route that keeps the released fragment as its `href` (so it opens in a new tab and copies as
   a link) and sends a plain click through the router, which stamps where a session was opened from. A
   modified click or a non-primary button is the browser's own. */
export function RouteAnchor({
  route,
  className,
  label,
  extra,
  before,
  children,
}: {
  readonly route: RouteInput;
  readonly className?: string;
  readonly label?: string;
  readonly extra?: Record<string, string>;
  readonly before?: () => void;
  readonly children: ReactNode;
}) {
  const navigate = useNavigate();
  const fragment = fragmentForRoute(route);
  const onClick = (event: MouseEvent<HTMLAnchorElement>) => {
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    )
      return;
    event.preventDefault();
    before?.();
    navigate(route);
  };
  return (
    <a
      data-slot="button-link"
      className={cn(className, buttonVariants({ variant: 'native' }))}
      href={fragment}
      data-next-route={fragment.slice(3)}
      {...(label ? { 'aria-label': label } : {})}
      {...extra}
      onClick={onClick}
    >
      {children}
    </a>
  );
}

function Fact({
  kind,
  label,
  value,
  detail = '',
  tone = '',
}: {
  readonly kind: string;
  readonly label: string;
  readonly value: string;
  readonly detail?: string;
  readonly tone?: string;
}) {
  return (
    <span
      className={tone ? `next-operation-fact next-operation-fact--${tone}` : 'next-operation-fact'}
      data-next-operation-fact={kind}
    >
      <small>{label}</small>
      <strong {...(tone === 'unknown' ? { className: 'next-absence' } : {})}>{value}</strong>
      {detail ? <em>{detail}</em> : null}
    </span>
  );
}

/* A fact is toned only while it is known: an unknown value is a stated absence and wears `.next-absence`,
   so "not published" never reads as a quieter version of a value. */
function ObservedFact({
  kind,
  label,
  text,
  known,
  note = '',
  tone = '',
}: {
  readonly kind: string;
  readonly label: string;
  readonly text: string;
  readonly known: boolean;
  readonly note?: string;
  readonly tone?: string;
}) {
  return (
    <Fact kind={kind} label={label} value={text} detail={note} tone={known ? tone : 'unknown'} />
  );
}

function assignmentOf(source: Row | undefined): string {
  const assignment = sessionInstruction(source, 'asked');
  const text = assignment ? String(assignment['text'] || '').trim() : '';
  const title = String(source?.['title'] || source?.['last_prompt'] || '').trim();
  return text && text !== title ? text : '';
}

function Identity({ row }: { readonly row: SessionRow }) {
  const { session, source, history } = row;
  const sid = session.sid.trim();
  const assignment = history ? '' : assignmentOf(source);
  const names = source ? gapNames(source) : [];
  return (
    <span className="next-operation-identity">
      <small className="next-operation-local-label">SESSION</small>
      <span className="next-operation-harness">{row.harnessLabel}</span>
      <RouteAnchor
        route={row.route}
        className="next-operation-route"
        label={`Open session ${session.titleText}`}
      >
        <strong
          {...(session.titleKnown
            ? {}
            : { className: 'next-operation-title--unknown next-absence' })}
        >
          {session.isLive ? (
            <StatusDot label="working" className="next-operation-live-glyph" />
          ) : null}
          {session.titleText}
        </strong>
      </RouteAnchor>
      {sid ? <CopyControl kind="id" harness={session.harness} sid={sid} value={sid} /> : null}
      {!session.titleKnown && session.promptKnown ? (
        <span className="next-operation-assignment">{`LAST PROMPT · ${session.promptText}`}</span>
      ) : null}
      {assignment ? (
        <span className="next-operation-assignment">{`ASSIGNMENT · ${assignment}`}</span>
      ) : null}
      {session.sharedLabelKnown ? (
        <span className="next-operation-collision" title={DUPLICATE_LABEL_LIMIT}>
          {session.sharedLabelText}
        </span>
      ) : null}
      {source && isScanOnly(source) ? (
        <span className="next-operation-scan-only" title={SCAN_ONLY_NOTE}>
          {SCAN_ONLY_LINE}
        </span>
      ) : null}
      {names.length ? (
        <span className="next-operation-unread" title={UNREAD_SOURCE_NOTE}>
          {`Source not fully read: ${names.join(', ')}`}
        </span>
      ) : null}
    </span>
  );
}

function GoalCellView({ row }: { readonly row: SessionRow }) {
  const shell = useShell();
  const { goal } = row;
  if (goal.kind === 'off')
    return <Fact kind="goal" label="GOAL" value={goal.text} tone="unknown" />;
  const onGoal = () =>
    goalFocusFor(shell.controls).request({ harness: row.session.harness, sid: row.session.sid });
  return (
    <span className="next-operation-fact" data-next-operation-fact="goal">
      <small>{goal.label}</small>
      {goal.kind === 'typed' ? (
        <strong>{goal.text}</strong>
      ) : (
        <RouteAnchor
          route={row.route}
          className={
            goal.known ? 'next-operation-goal-link' : 'next-operation-goal-link next-absence'
          }
          extra={{ 'data-next-goal-focus': '' }}
          before={onGoal}
        >
          {goal.text}
        </RouteAnchor>
      )}
    </span>
  );
}

function DriftMarkView({ row }: { readonly row: SessionRow }) {
  const mark = row.drift;
  if (!mark) return null;
  return (
    <span className="next-operation-drift" data-next-session-drift-mark>
      <strong>Drift</strong>
      {` · ${mark.age}`}
      {mark.someUnknown ? <small>Some recorded departure ages are unknown</small> : null}
      {mark.stale.map((line) => (
        <small key={line}>{line}</small>
      ))}
    </span>
  );
}

function RowView({ row }: { readonly row: SessionRow }) {
  const { session, history } = row;
  const nowKind = session.isEnded
    ? 'NOW · ENDED'
    : `NOW · ${session.state.replaceAll('_', ' ').toUpperCase()}`;
  const outcome = session.outcomeKnown ? (
    <span className={`next-operation-outcome next-operation-outcome--${session.tone}`}>
      {`${session.outcomeGlyph} ${session.outcomeText}`}
      <span
        className={
          session.gitKnown
            ? 'next-operation-outcome'
            : 'next-operation-outcome next-operation-outcome--unknown'
        }
      >
        {session.gitText}
      </span>
    </span>
  ) : null;
  const stateTag = session.isEnded ? 'ENDED' : session.isQuiet ? 'QUIET' : '';
  const tag = stateTag ? <span className="next-operation-state">{stateTag}</span> : null;
  const now = (
    <ObservedFact
      kind="now"
      label={nowKind}
      text={session.nowText}
      known={session.nowKnown}
      note={row.endedSince}
    />
  );
  return (
    <article
      className={`next-operation-row next-operation-row--${session.tone}`}
      data-next-harness={session.harness}
      data-next-session={session.sid}
      {...(history ? { 'data-next-operation-history': 'true' } : {})}
    >
      <Identity row={row} />
      <ObservedFact
        kind="where"
        label="WHERE · PROJECT LABEL"
        text={session.whereText}
        known={session.whereKnown}
        note={session.project}
      />
      <GoalCellView row={row} />
      {history ? (
        <>
          <div className="next-operation-history-now">
            {now}
            {outcome}
          </div>
          {tag}
        </>
      ) : (
        <>
          {now}
          <ObservedFact
            kind="next"
            label="NEXT"
            text={session.nextText}
            known={session.nextKnown}
          />
          <ObservedFact
            kind="blocked"
            label={`BLOCKED${row.responsibility}`}
            text={session.blockText}
            known={session.blockKnown}
            note={session.blockNote}
            tone={session.isNeeds || session.askKnown ? 'blocked' : 'clear'}
          />
          {stateTag || outcome ? (
            <div className="next-operation-end-note">
              {tag}
              {outcome}
            </div>
          ) : null}
        </>
      )}
      <DriftMarkView row={row} />
    </article>
  );
}

function Group({
  kind,
  title,
  label,
  rows,
  empty,
  caveat,
}: {
  readonly kind: 'active' | 'history';
  readonly title: string;
  readonly label: string;
  readonly rows: readonly SessionRow[];
  readonly empty: string;
  readonly caveat?: { readonly summary: string; readonly body: string };
}) {
  return (
    <section
      className={`next-operation-group next-operation-group--${kind}`}
      data-next-operation-group={kind}
    >
      <header>
        <h2>{title}</h2>
        {label ? <p>{label}</p> : null}
        {caveat ? (
          <Disclosure
            disclosureKey={disclosureKey({
              project: null,
              scope: null,
              name: `sessions-${kind}-why`,
            })}
            summary={caveat.summary}
            variant="popover"
          >
            <p className="next-why-body">{caveat.body}</p>
          </Disclosure>
        ) : null}
      </header>
      <div className="next-operations-columns" aria-hidden="true">
        <span>SESSION</span>
        <span>WHERE</span>
        <span>GOAL</span>
        <span>NOW</span>
        {kind === 'history' ? (
          <span>STATE</span>
        ) : (
          <>
            <span>NEXT</span>
            <span>BLOCKED</span>
          </>
        )}
      </div>
      <div className="next-operation-rows">
        {rows.length ? (
          rows.map((row) => <RowView key={row.key} row={row} />)
        ) : (
          <p className="next-sessions-empty next-absence">{empty}</p>
        )}
      </div>
    </section>
  );
}

const FACT_KEYS = ['active', 'working', 'requests', 'reported-blocks'] as const;

/* The harnesses whose store could not be read, named, because "no sessions" under one of them would be
   a claim about a store nobody could open. */
function SourceGaps() {
  const harnesses = useDisplayed(selectHarnessSources);
  const failed = harnesses.rows.filter((row) => row.error !== null);
  if (!failed.length) return null;
  return (
    <ul className="next-sessions-sources" data-next-source-gaps>
      {failed.map((row) => (
        <li
          key={row.key}
        >{`${row.label ?? row.key}: Harness source could not be read; its sessions are missing here, not absent.`}</li>
      ))}
    </ul>
  );
}

export interface SessionsViewProps {
  /** The Intent step's prompt the reader picked and has not saved, for a session's goal cell. */
  readonly chosenFor?: (session: Row) => PromptCandidate | null;
}

export function SessionsView({ chosenFor }: SessionsViewProps = {}) {
  const data = useDisplayed((snapshot) => snapshot.data);
  const model = useDisplayed(selectObserved);
  const screen = useMemo(
    () => (data ? buildSessionsScreen(data as unknown as Row, model, chosenFor) : null),
    [data, model, chosenFor],
  );
  if (!screen) return null;
  return (
    <section className="next-operations" data-next-view-body="sessions">
      <header className="next-operations-header">
        <span>COMMAND SURFACE</span>
        <h1>Session operations</h1>
        {screen.lede ? <p>{NOT_CHECKED}</p> : null}
        <Disclosure
          disclosureKey={disclosureKey({ project: null, scope: null, name: 'sessions-board-why' })}
          summary="How rows are split"
        >
          <p className="next-why-body">{BOARD_WHY}</p>
        </Disclosure>
        <Disclosure
          disclosureKey={disclosureKey({
            project: null,
            scope: null,
            name: 'sessions-goal-source',
          })}
          summary="Goal sources"
        >
          <p className="next-why-body">
            {screen.context.annotate ? GOAL_SOURCES_ON : GOAL_SOURCES_OFF}
          </p>
        </Disclosure>
      </header>
      <SourceGaps />
      <section className="next-operations-fleet" aria-label="Fleet facts">
        {screen.counters.map((counter, index) => (
          <section key={FACT_KEYS[index]} data-next-fleet-fact={FACT_KEYS[index]}>
            <span>{counter.label}</span>
            <strong>{counter.value}</strong>
            <small>{counter.noteText}</small>
          </section>
        ))}
      </section>
      <Group
        kind="active"
        title="Active now"
        label="working, waiting on you, an exact request, or recorded drift"
        rows={screen.active}
        empty="No exact session has active evidence right now."
      />
      <Group
        kind="history"
        title="Recent history"
        label=""
        rows={screen.history}
        empty="No recent-history rows in this payload."
        caveat={{ summary: 'What recent means', body: RECENT_WHY }}
      />
      <CapacityStrip />
    </section>
  );
}
