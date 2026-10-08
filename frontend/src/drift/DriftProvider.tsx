import './drift.css';
import { useEffect, useMemo, useState, useSyncExternalStore, type ReactNode } from 'react';
import { payloadSessions } from '../api/bootstrap';
import { compatSessKey, stableProjectKey } from '../api/identity';
import { useLiveEstimateOn } from '../intent/liveMonitor';
import { useHeldVersion } from '../intent/useIntent';
import type { Row } from '../observed';
import { useDisplayed, useShell } from '../shell/context';
import { DriftContext, type DriftValue } from './context';
import { buildModel, type DriftModel } from './model';
import { overlaid } from './overlay';
import { driftCtxFor, useDriftVersion, type DriftCtx } from './state';
import { clearFlipLines } from './flip';
import { trackJobs } from './jobs';
import { syncPaused } from './steerActions';

/* Whether the reader is in this session's correction box (untouched or edited), composing in it, or holding a
   pointer on a control they left it for: then the Drift card keeps showing the board it already drew. The
   legacy page queued the whole page's paint for an edited box. The React page keeps a persistent node, so the
   editor's caret, selection and undo survive an ordinary redraw, but a redraw that moves the box in the tree
   (a stale mark turning the layout into another) would remount it, resetting the caret of a reader who has
   only clicked into it and ending a composition. So a board that arrives while the reader is in the box
   waits, and the newest one shows when they leave
   ([the reader state row](../../../docs/design-reader-state.md)). The reader's own presses never wait. */
function engaged(ctx: DriftCtx, key: string): boolean {
  const { editor, corrections } = ctx.drift;
  if (editor.composition) return true;
  if (editor.pointer && editor.pointer.key === key) return true;
  return Boolean(corrections.get(key) && editor.focused === key);
}

export function DriftProvider({
  session,
  payload,
  project,
  children,
}: {
  readonly session: Row;
  readonly payload: Row;
  readonly project: string;
  readonly children: ReactNode;
}) {
  const shell = useShell();
  const ctx = driftCtxFor(shell);
  useHeldVersion(ctx.intent.held);
  useDriftVersion(ctx.drift);
  const overlay = useSyncExternalStore(ctx.drift.subscribe, ctx.drift.getOverlay);
  const contexts = useDisplayed((snapshot) => snapshot.contexts);
  const count = useDisplayed((snapshot) => snapshot.acceptedCount);
  const key = compatSessKey(session);
  const live = useMemo(
    () => ({
      session,
      base: payload,
      payload: overlaid(payload, overlay, count),
      contexts,
    }),
    [session, payload, count, contexts, overlay],
  );
  /* The board the card shows. While the reader is mid-edit it stays the last one drawn, and the newest shows
     when they leave: state adjusted during the render that finds the wait over, so no ref is read in one. */
  const [shown, setShown] = useState(live);
  const waiting = engaged(ctx, key);
  if (!waiting && shown !== live) setShown(live);
  const view = waiting ? shown : live;
  const projectKey = useMemo(
    () =>
      stableProjectKey({
        label: project,
        sessions: payloadSessions(view.payload as never).rows.filter(
          (row) => String(row.project ?? '') === project,
        ),
      }),
    [view.payload, project],
  );
  const liveOn = useLiveEstimateOn(session);
  const model: DriftModel = buildModel({
    liveOn,
    session: view.session,
    payload: view.payload,
    base: view.base,
    project,
    projectKey,
    contexts: view.contexts,
    held: ctx.intent.held,
  });
  const value = useMemo<DriftValue>(() => ({ ctx, model }), [ctx, model]);

  /* After the commit, never from the render: the timers the card asked for, the announcements of a running
     analysis, and the one release of a paint the reader's editing queued. */
  useEffect(() => {
    ctx.drift.applyTimers();
  });
  useEffect(
    () => {
      const drawn = new Set<string>();
      const id = model.job?.['id'];
      if (typeof id === 'string') drawn.add(id);
      trackJobs(ctx, model.payload, drawn);
    },
    // The jobs move with the board, not with every keystroke held beside it.
    [ctx, model.payload, model.job],
  );
  const editing =
    waiting && shown !== live && !ctx.drift.editor.composition && !ctx.drift.editor.pointer;
  useEffect(() => syncPaused(ctx, key, editing), [ctx, key, editing]);
  useEffect(() => ctx.drift.mount(), [ctx]);
  /* The next click inside the card takes the change line down. */
  useEffect(() => {
    const onClick = (event: Event) => {
      const target = event.target;
      if (!(target instanceof Element) || !target.closest('#next-session-drift')) return;
      clearFlipLines(ctx);
    };
    document.addEventListener('click', onClick, true);
    return () => document.removeEventListener('click', onClick, true);
  }, [ctx]);
  /* Leaving the page leaves no box drawn, so a job that ends while the reader is elsewhere is not announced
     as one they watched. */
  useEffect(
    () => () => {
      for (const seen of ctx.drift.jobsSeen.values()) seen.drawn = false;
      // A press's ask for focus belongs to the page it was made on, so one still waiting goes with the card.
      ctx.intent.held.takeFocus();
    },
    [ctx],
  );
  return <DriftContext value={value}>{children}</DriftContext>;
}
