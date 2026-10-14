import { Card } from '../ui/card';
import { openDirection } from '../intent/directions';
import { DirectionActionButton } from '../intent/DirectionActionButton';
import { compatSessKey } from '../api/identity';
import { useDrift } from './context';
import { WORK_AS_REPORTED } from './sentences';
import { foldRuns, workList, type CheckRunModel } from './workList';
import { ActivityHead } from './ActivityHead';
import { ActivityLegend } from './ActivityMarks';
import { CheckRun } from './CheckRun';
import { TooltipProvider } from '../ui/tooltip';
import { disclosureKey, useControls } from '../controls';
import { useControlledDisclosureState } from '../controls/useDisclosureState';
import { Why } from './Why';
import { useEffect, useLayoutEffect, useRef, type ReactNode } from 'react';
import { contextKey } from '../api/identity';
import { activityStamp, entryWindow, recordPastWindow } from '../intent/work';
import { useDisplayed, useShell } from '../shell/context';
import { ShowMore } from './ShowMore';

function HeldCheckRun({
  run,
  project,
  scope,
  children,
}: {
  readonly run: CheckRunModel;
  readonly project: string;
  readonly scope: string;
  readonly children: ReactNode;
}) {
  const controls = useControls();
  // The newest end grows during work; the oldest member keeps the reader's opening attached to this run.
  // docs/design-reader-state.md#the-inventory owns this identity and its lifetime.
  const key = disclosureKey({ project, scope, name: `check-run:${run.last.entry.id}` });
  const open = useControlledDisclosureState(controls.disclosures, key);
  return (
    <CheckRun
      run={run}
      open={open}
      onOpenChange={(value, details) => {
        if (details.reason === 'trigger-press') controls.noteToggle();
        controls.disclosures.set(key, value);
      }}
    >
      {children}
    </CheckRun>
  );
}

/* The numbered activity list, drawn under CURRENT ACTIVITY. It sits in the activity column under that
   column's own heading, so it has none of its own. The record's footer is tiered: where the harness's work
   results are read, one clause stays in view and the mix, the bounds, the scan and the full limit sit behind
   "About this record"; where none are read, the limit is the absence and stays in view. The route's
   tool-output sentence is not repeated here: "What is sent" beside the control owns it.

   Newest first: the rows are drawn from the last entry to the first, so a reader opens on what just happened.
   The numbers stay the ones the list assigns oldest-first, which every "#<n>" on the page and every citation
   names, so the column reads #32 down to #1. "Add to my intent" is always drawn: a control shown only on
   hover is one a reader does not know is there. */
export function WorkListView() {
  const { ctx, model, finding, jump } = useDrift();
  const { runtime } = useShell();
  const record = useDisplayed((snapshot) =>
    snapshot.records.get(contextKey(model.projectKey, model.identity)),
  );
  const harness = model.identity?.harness;
  const sid = model.identity?.sid;
  useEffect(() => {
    if (!harness || !sid) return;
    return runtime.openRecord({ projectKey: model.projectKey, focus: { harness, sid } });
  }, [runtime, model.projectKey, harness, sid]);
  /* The newest page again whenever the session's published activity changes: the opening read is a snapshot,
     and the board's context only reaches back over the newest 400 KB of the transcript, so without this an
     entry that arrives and then leaves that tail is held nowhere and drops off the list, taking every number
     above it along. docs/design-reader-state.md#the-inventory owns the lifetime. */
  const stamp = activityStamp(model.session, model.generated);
  /* The revision is called every time, and the loader reads only for a new stamp or to retry a read that went
     unanswered, so a transient failure on a session's last write is tried again on the next poll. */
  // biome-ignore lint/correctness/useExhaustiveDependencies: the revision is the retry trigger, not a value the body reads.
  useEffect(() => {
    if (!harness || !sid) return;
    void runtime.refreshRecord({ projectKey: model.projectKey, focus: { harness, sid } }, stamp);
  }, [runtime, model.projectKey, harness, sid, stamp, model.generated]);
  const panel = useRef<HTMLDivElement>(null);
  const jumped = useRef<object | null>(null);
  const pagingFocus = useRef<{ button: HTMLElement; before: ReadonlySet<string> } | null>(null);
  const opened = entryWindow(model.session, model.payload);
  const pastWindow = recordPastWindow(record, opened);
  const readMore = () => {
    if (!model.identity || pastWindow) return;
    const before = new Set(list.rows.map((row) => row.entry.id));
    const button = panel.current?.querySelector<HTMLElement>('[data-record-more]');
    if (button && document.activeElement === button) pagingFocus.current = { button, before };
    // An appended older page stays below the existing rows. Focus must never scroll that page into view.
    void runtime.readMoreRecord({ projectKey: model.projectKey, focus: model.identity });
  };
  useEffect(() => {
    if (!finding || jumped.current === jump) return;
    jumped.current = jump;
    const target = [
      ...(panel.current?.querySelectorAll<HTMLElement>('[data-next-entry-id]') ?? []),
    ].find((node) => finding.citedIds.includes(node.dataset['nextEntryId'] ?? ''));
    if (!target) return;
    target.focus({ preventScroll: true });
    target.scrollIntoView({
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches
        ? 'instant'
        : 'smooth',
      block: 'center',
    });
  }, [finding, jump]);
  const list = workList({
    session: model.session,
    payload: model.payload,
    source: model.source,
    annotation: model.annotation,
    draft: model.draft,
    cited: model.cited,
    revealed: new Set(finding?.citedIds),
    generated: model.generated,
  });
  useLayoutEffect(() => {
    const request = pagingFocus.current;
    if (
      !request ||
      record?.status === 'loading' ||
      (record?.status === 'stale' && record.error === null) ||
      !panel.current
    )
      return;
    pagingFocus.current = null;
    if (document.activeElement !== request.button && document.activeElement !== document.body)
      return;
    const retained = panel.current.querySelector<HTMLElement>('[data-record-more]');
    const firstNew = [...panel.current.querySelectorAll<HTMLElement>('[data-next-entry-id]')].find(
      (row) => !request.before.has(row.dataset['nextEntryId'] ?? ''),
    );
    const boundary = panel.current.querySelector<HTMLElement>('[data-record-stop]');
    (retained ?? firstNew ?? boundary)?.focus({ preventScroll: true });
  }, [record]);
  const hasChecks = list.rows.some((row) => 'check' in row.head && row.head.check);
  const about = (
    <>
      {hasChecks ? <ActivityLegend /> : null}
      {list.mix ? <p className="next-cockpit-work-mix">{list.mix}</p> : null}
      {list.unlisted.map((said) => (
        <p key={said} className="next-cockpit-work-earlier">
          {said}
        </p>
      ))}
      {list.checks ? <p className="next-cockpit-work-checks">{list.checks}</p> : null}
      {list.bound ? <p className="next-cockpit-work-dropped">{list.bound}</p> : null}
      {list.reads ? <p className="next-cockpit-work-limit">{list.limit}</p> : null}
    </>
  );
  const hasAbout = Boolean(
    hasChecks || list.mix || list.unlisted.length || list.checks || list.bound || list.reads,
  );
  return (
    <TooltipProvider>
      <Card
        ref={panel}
        variant="work-panel"
        as="section"
        className="next-cockpit-work"
        data-next-cockpit-work
      >
        {list.anchor ? <p className="next-cockpit-work-anchor">{list.anchor}</p> : null}
        {list.unnumbered ? <p className="next-cockpit-work-absent">{list.unnumbered}</p> : null}
        {list.rows.length ? (
          <div className="next-cockpit-work-rows" role="list">
            {foldRuns([...list.rows].reverse(), new Set(finding?.citedIds)).map((item) => {
              const renderRow = (row: (typeof list.rows)[number]) => {
                const { entry } = row;
                const type = entry.type;
                return (
                  <div
                    key={entry.id}
                    className="next-cockpit-work-row"
                    role="listitem"
                    data-next-cockpit-work-type={type}
                    {...(row.n === null ? {} : { 'data-next-entry': String(row.n) })}
                    data-next-entry-id={entry.id}
                    data-next-entry-words={
                      'report' in row.head ? row.head.report : `${row.head.actor}${row.head.type}`
                    }
                    data-next-entry-turn={row.turn ? 'true' : undefined}
                    tabIndex={-1}
                  >
                    <span className="next-cockpit-work-n">
                      {row.n === null ? (
                        <span className="next-visually-hidden">not numbered</span>
                      ) : (
                        `#${String(row.n)}`
                      )}
                    </span>
                    <div className="next-cockpit-work-body">
                      <ActivityHead row={row} />
                      {finding?.citedIds.includes(entry.id) ? (
                        <p className="next-cockpit-reading-evidence" data-next-finding-entry>
                          {`Cited for “${finding.detail || finding.clause || finding.label}” · ${row.n === null ? 'Entry not numbered in this view' : `#${String(row.n)}`}`}
                        </p>
                      ) : null}
                      {/* A model's paraphrase takes the third treatment, not the mono of a string a source
                      published: the reader must be able to tell the record from an account of it. */}
                      {entry.modelDerived ? (
                        <em className="next-cockpit-work-derived">{entry.summary}</em>
                      ) : (
                        <span className="next-cockpit-work-summary">{entry.summary}</span>
                      )}
                      <span className="next-cockpit-work-source next-visually-hidden">
                        {row.source}
                      </span>
                      {row.add ? (
                        <DirectionActionButton
                          feedbackKey={`direction-row:${compatSessKey(model.session)}:${entry.id}`}
                          focusKey={`direction-row:${compatSessKey(model.session)}:${entry.id}`}
                          pendingKey={`direction-row:${compatSessKey(model.session)}:${entry.id}`}
                          className="self-start"
                          weight="quiet"
                          label="Add to my intent"
                          busyLabel="Opening…"
                          action="direction-add"
                          arg={entry.id}
                          onPress={() => {
                            if (model.identity && entry.id) {
                              void openDirection(
                                ctx.intent,
                                model.session,
                                entry.id,
                                row.n,
                                true,
                                'direction-add',
                                `direction-row:${compatSessKey(model.session)}:${entry.id}`,
                              );
                            }
                          }}
                        />
                      ) : null}
                    </div>
                  </div>
                );
              };
              return item.kind === 'row' ? (
                renderRow(item.row)
              ) : (
                <div key={item.last.entry.id} role="listitem">
                  <HeldCheckRun run={item} project={model.project} scope={model.key}>
                    {item.rows.map(renderRow)}
                  </HeldCheckRun>
                </div>
              );
            })}
          </div>
        ) : list.unnumbered ? null : (
          <p className="next-cockpit-work-absent">{list.absent}</p>
        )}
        <ShowMore {...(record ? { record } : {})} pastWindow={pastWindow} onMore={readMore} />
        {list.reads ? (
          <p className="next-cockpit-work-limit next-cockpit-work-reported">{WORK_AS_REPORTED}</p>
        ) : (
          <p className="next-cockpit-work-limit">{list.limit}</p>
        )}
        {hasAbout ? (
          <Why name="work-about" summary="About this record">
            {about}
          </Why>
        ) : null}
      </Card>
    </TooltipProvider>
  );
}
