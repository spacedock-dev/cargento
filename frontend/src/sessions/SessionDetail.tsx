import { useMemo, type ReactNode } from 'react';
import { CopyControl, Disclosure, RaiseControl, disclosureKey, resumeCommand, useFocusKey } from '../controls';
import { endedAt, type ObservedSession, type Row } from '../observed';
import { selectObserved } from '../observed/select';
import { sessionHome, type SessionRoute } from '../router/grammar';
import { sessionLink } from '../router/permalink';
import { useDisplayed, useShell } from '../shell/context';
import type { PayloadData } from '../api/types';
import { AnswerBlock } from './AnswerBlock';
import { usePruneAnswerNotes } from './usePruneAnswerNotes';
import { DelegatedWorkLine, UnaskedDepartureBody } from './DepartureParts';
import { DriftSlot } from './DriftSlot';
import { CommandReportsView, DeliveryView, DeparturesKept, FactsView, HealthView, InstructionLine, LandedView, SubagentsView, TasksView } from './DetailParts';
import {
  askingTitle,
  commandReports,
  detailState,
  reentryLimit,
  sessionAsks,
  sessionDelivery,
  sessionFacts,
  sessionFooter,
  sessionHealth,
  sessionMeta,
  sessionSubagents,
  sessionTasks,
  unaskedDepartures,
  LANE_OFF_RECORD,
  laneOffWhy,
} from './detail';
import { RouteAnchor } from './SessionsView';
import { harnessLabels } from './rows';
import { sessionInstruction } from './intent';
import './sessions.css';

/* The session page: one exact session, its state, what it is waiting on, and what it has done. Identity is
   the harness and the sid together, never the display id, and every control it carries acts only when
   pressed. The legacy `next-session.js` is the oracle for every sentence; the Intent and drift panel that
   sits beside the activity column belongs to the Intent step and is a stated slot here. */

function Controls({ session, observed, route, labels }: { readonly session: Row; readonly observed: ObservedSession; readonly route: SessionRoute; readonly labels: ReadonlyMap<string, string> }) {
  const shell = useShell();
  const rawHarness = String(session['harness'] == null ? '' : session['harness']);
  const harness = String(session['harness'] || '');
  const rawSid = String(session['sid'] || '');
  /* The copy control and the raise name the session by its trimmed id and harness, and the link and the
     command by what the row published, exactly as the legacy controls do: the cue is keyed on the pair, so
     the lane a press writes is the lane the same control reads back. */
  const trimmedSid = rawSid.trim();
  const command = resumeCommand(harness, String(session['resume_id'] || ''));
  const focusCapability = shell.controls.focus !== null;
  const raisable = session['focusable'] === true && Boolean(trimmedSid) && Boolean(rawHarness.trim()) && focusCapability;
  const limit = reentryLimit({
    label: labels.get(harness) || humanLabel(harness),
    hasCommand: Boolean(command),
    knownHarness: harness === 'claude' || harness === 'codex',
    canRaise: raisable,
    focusCapability,
  });
  const missing = [limit.resume ? 'No resume command' : '', !raisable ? (focusCapability ? 'No terminal to raise' : 'Terminal raise off') : ''].filter(Boolean);
  return (
    <>
      <div className="next-session-controls">
        {trimmedSid ? <CopyControl kind="id" harness={harness} sid={trimmedSid} value={trimmedSid} /> : null}
        {rawSid ? <CopyControl kind="link" harness={harness} sid={rawSid} value={sessionLink(window.location.href, { project: observed.project, harness, sid: rawSid })} /> : null}
        {command ? <CopyControl kind="command" harness={harness} sid={rawSid} value={command} /> : null}
        {observed.isNeeds ? <RaiseControl harness={rawHarness.trim()} sid={trimmedSid} focusable={session['focusable'] === true} primary /> : null}
      </div>
      {missing.length ? (
        <div className="next-session-reentry-none">
          <span className="next-session-reentry-clause">{missing.join(' · ')}</span>
          {/* A popover: this row is a flex row ending at the controls, and an in-flow body widened the item to its paragraphs and dragged "Why" 492px left. */}
          <Disclosure disclosureKey={disclosureKey({ project: route.project, scope: `${route.harness ?? ''}:${route.session}`, name: 'reentry-why' })} summary="Why" variant="popover">
            {limit.resume ? <ReentryLine text={limit.resume} /> : null}
            {!raisable ? <ReentryLine text={limit.raise} /> : null}
          </Disclosure>
        </div>
      ) : null}
    </>
  );
}

/* The departures raised to the reader and the way back beside them, drawn under the label the legacy page
   gives them until the Intent step's panel composes them itself. */
function DepartureEvidence({ session, laneOn, offReason }: { readonly session: Row; readonly laneOn: boolean; readonly offReason: unknown }) {
  const body = unaskedDepartures(session);
  if (!body) return null;
  return (
    <div className="next-cockpit-departure-part">
      <span className="next-cockpit-departure-label">FROM THE CHECKS RUN WHILE YOU WERE AWAY</span>
      {/* With the lane off the rows are still on the wire, so they are printed with the limit that qualifies them:
          without it the label alone would read as checks that ran while the reader was away. */}
      {laneOn ? null : (
        <>
          <p className="next-cockpit-reading-why" data-absence="run-config">
            {laneOffWhy(offReason)}
          </p>
          <p className="next-cockpit-reading-why" data-absence="run-config">
            {LANE_OFF_RECORD}
          </p>
        </>
      )}
      <UnaskedDepartureBody session={session} />
    </div>
  );
}

function humanLabel(value: string): string {
  const words = String(value || 'work').replace(/[-_]+/g, ' ').trim();
  return words ? (words[0] ?? '').toUpperCase() + words.slice(1) : 'Work';
}

function ReentryLine({ text }: { readonly text: string }) {
  return (
    <p className="next-departure-reentry-why" data-absence="not-observed">
      {text}
    </p>
  );
}

function CommandSurface({ session, observed, generated }: { readonly session: Row; readonly observed: ObservedSession; readonly generated: number | null }) {
  const context = sessionInstruction(session, 'agent') ?? sessionInstruction(session, 'earlier');
  const state = observed.isNeeds ? 'waiting on you' : observed.isEnded ? 'session ended' : observed.state;
  return (
    <div className="next-session-command-surface" aria-label="Session command surface">
      <section className="next-session-current" data-next-session-command="activity">
        <span className="next-session-current-label">CURRENT ACTIVITY</span>
        <strong {...(observed.nowKnown ? {} : { className: 'next-session-absent' })}>{`${state} · ${observed.nowText}`}</strong>
        {context ? <InstructionLine session={session} generated={generated} className="next-session-command-context" /> : null}
      </section>
    </div>
  );
}

function Header({ session, observed, route, labels, generated }: { readonly session: Row; readonly observed: ObservedSession; readonly route: SessionRoute; readonly labels: ReadonlyMap<string, string>; readonly generated: number | null }) {
  const shell = useShell();
  const titleRef = useFocusKey<HTMLHeadingElement>(shell.controls.focusLane, 'session-title');
  const state = detailState(session['state']);
  /* An observed end retires the state word, as it does on the Sessions rows: "working" beside "ended 1s ago"
     contradicts the line under it. A question still waiting says "needs input" whatever the collector
     inferred, because after `session_ended` pops the overlay the state is the collector's `working` or
     `idle` while the ask stays open. */
  const ended = endedAt(session) !== null && !observed.askKnown;
  const word = ended ? 'ended' : observed.askKnown ? 'needs input' : state?.label;
  const label = observed.project;
  const meta = sessionMeta(session, labels, generated, null);
  return (
    <header className="next-session-detail-header">
      <div className="next-session-detail-title">
        {state ? (
          <span className="next-session-state">
            <span className="next-visually-hidden">State: </span>
            {word}
          </span>
        ) : null}
        <h1 ref={titleRef} tabIndex={-1} {...(observed.titleKnown ? {} : { className: 'next-session-absent' })}>
          {observed.titleText}
        </h1>
        <p className="next-session-identity">
          {`${observed.harness} · ${observed.sid}`}
          {observed.rateKnown ? ` · ${observed.rateText}` : ''}
          {label && sessionHome(route) !== 'projects' ? (
            <>
              {' · '}
              <RouteAnchor route={{ view: 'project', project: label }}>{label}</RouteAnchor>
            </>
          ) : null}
        </p>
      </div>
      <div className="next-session-detail-bar">
        {meta ? <p className="next-session-detail-meta">{meta}</p> : null}
        <Controls session={session} observed={observed} route={route} labels={labels} />
      </div>
    </header>
  );
}

export interface SessionDetailProps {
  readonly route: SessionRoute;
  readonly data: PayloadData;
  readonly session: Row;
}

export function SessionDetail({ route, data, session }: SessionDetailProps): ReactNode {
  const payload = data as unknown as Row;
  const model = useDisplayed(selectObserved);
  const observed = useMemo(
    () => model.sessions.find((row) => row.harness === String(session['harness'] ?? '') && row.sid === String(session['sid'] ?? '') && row.project === String(session['project'] ?? '')) ?? null,
    [model, session],
  );
  const labels = useMemo(() => harnessLabels(payload), [payload]);
  const generated = typeof payload['generated'] === 'number' && Number.isFinite(payload['generated']) ? payload['generated'] : null;
  const asks = useMemo(() => sessionAsks(payload, session), [payload, session]);
  usePruneAnswerNotes(payload);
  const scope = `${route.harness ?? ''}:${route.session}`;
  if (!observed) return null;
  const blocked = observed.isNeeds ? ' next-session-detail--blocked' : '';
  const state = detailState(session['state']);
  const facts = sessionFacts(observed, asks);
  const tasks = sessionTasks(observed.tasks);
  const subagents = sessionSubagents(observed.subagents, observed.subagentsOmitted, generated);
  const health = sessionHealth(session);
  const reports = commandReports(payload, session);
  const delivery = sessionDelivery(session);
  const footer = sessionFooter(session);
  const asked = sessionInstruction(session, 'asked');
  const factKey = (name: string) => disclosureKey({ project: route.project, scope, name });
  return (
    <article className={`next-session-detail${blocked}`} data-next-session-detail={String(session['sid'] ?? '')} {...(state ? { 'data-next-session-state': state.token } : {})} data-tone={observed.tone}>
      <Header session={session} observed={observed} route={route} labels={labels} generated={generated} />
      {observed.askKnown ? <AnswerBlock payload={payload} observed={observed} asks={asks} title={askingTitle(labels, session)} /> : null}
      <div className="next-session-columns">
        <DriftSlot harness={observed.harness} sid={observed.sid}>
          <DelegatedWorkLine session={session} now={generated} />
          <DepartureEvidence session={session} laneOn={payload['unasked'] === true} offReason={payload['unasked_off_reason']} />
        </DriftSlot>
        <div className="next-session-activity" data-next-session-activity>
          <h2 className="next-session-activity-heading">Session activity</h2>
          <CommandSurface session={session} observed={observed} generated={generated} />
          {subagents ? <SubagentsView subagents={subagents} /> : null}
          <FactsView facts={facts} disclosureKey={factKey('session-facts')} />
          <div className="next-session-evidence">
            {asked ? (
              <section data-next-session-command-fact="assignment">
                <h2>ASSIGNMENT</h2>
                <InstructionLine session={session} generated={generated} className="next-session-command-context" />
              </section>
            ) : null}
          </div>
          {health ? <HealthView health={health} /> : null}
          {tasks ? <TasksView tasks={tasks} /> : null}
          <CommandReportsView reports={reports} disclosureKey={factKey('command-reports')} />
          {delivery ? <DeliveryView delivery={delivery} /> : null}
          {/* The record under the activity column belongs to the annotation store: with it off the page this
              ports draws neither card nor pointer, and a card claiming an end the store cannot back would be new. */}
          {payload['annotate'] === true ? (
            <>
              <LandedView landing={observed.landing} disclosureKey={factKey('landed-why')} />
              <DeparturesKept disclosureKey={factKey('kept-why')} />
            </>
          ) : null}
        </div>
      </div>
      {footer ? (
        <footer className="next-session-footer" data-next-session-tokens={footer.source}>
          {footer.text}
        </footer>
      ) : null}
    </article>
  );
}

