import { compatSessKey } from '../api/identity';
import { nextNumber } from '../api/bootstrap';
import { Disclosure, disclosureKey, useFocusKey } from '../controls';
import { clock } from '../observed';
import { useDisplayed } from '../shell/context';
import { ActionButton } from './ActionButton';
import { discardStamp, revisionLine, storeUnreadable } from './annotation';
import { heldSentence } from './cues';
import {
  directionLinesQuestion,
  intentChanges,
  intentDrafted,
  intentKey,
  noDraftWhy,
} from './derive';
import { undoChanges } from './edit';
import { GoalField } from './GoalField';
import { OutcomeLines } from './OutcomeLines';
import { saveIntent } from './save';
import { INTENT_MEASURED } from './sentences';
import { usePanel } from './useIntent';

/* Under both fields, as the design's single hint line is: the hint on the left, Undo changes and Save intent
   on the right, both inert while nothing has changed. An inert save is described by whichever absence
   sentences stand, which is why those stay in the document visually hidden. */
function Footer() {
  const { ctx, input, session, payload } = usePanel();
  const key = intentKey(session);
  const changes = intentChanges(input);
  const unreadable = Boolean(storeUnreadable(payload));
  const absent = unreadable
    ? []
    : (
        [
          ['goal', 'goal_why'],
          ['lines', 'lines_why'],
        ] as const
      )
        .filter(([, why]) => input.annotation?.[why])
        .map(([kind]) => `next-cockpit-held-absent-${kind}`);
  /* Not while the save is still busy: the outcome is drawn and said together, when the button settles, and a
     redraw in between drew "Saved" beside "Saving…". */
  const saving = useDisplayed((snapshot) => snapshot.pending.includes(`${key}:save`));
  const cue = saving ? '' : heldSentence(ctx.held.kind(key), null);
  const question = directionLinesQuestion(ctx.held, session);
  /* Undo is inert while its save is in flight: reverting the box would leave the words being sent unseen. */
  return (
    <div className="next-cockpit-held-footer">
      <p className="next-cockpit-held-hint" data-next-intent-measured>
        {INTENT_MEASURED}
      </p>
      <span className="next-cockpit-held-tools">
        <ActionButton
          label="Undo changes"
          action="held-undo"
          arg="intent"
          inert={!(changes.undoable && !saving)}
          focusKey={`${key}:undo`}
          onPress={() => undoChanges(ctx, input)}
        />
        <ActionButton
          label="Save intent"
          busyLabel="Saving…"
          pendingKey={`${key}:save`}
          action="held-save"
          arg="intent"
          inert={!((changes.any || changes.adoptable) && !question)}
          describedBy={absent.join(' ')}
          focusKey={`${key}:save`}
          onPress={() => void saveIntent(ctx, session)}
        />
      </span>
      {cue ? <small className="next-cockpit-held-cue">{cue}</small> : null}
    </div>
  );
}

/* "Saved", without a check mark: a check in this panel reads as a verdict, and "Confirmed" would claim what
   nothing did, since a saved revision is the reader's own words. The store key is in its details because the
   reader may need whose words these are, and the page's title already names the session. */
function SavedStamp() {
  const { input, session, project } = usePanel();
  const annotation = input.annotation;
  const generated = nextNumber(input.payload['generated']);
  const stamp = discardStamp(annotation, generated);
  const line = stamp ? '' : revisionLine(annotation, generated);
  if (!line) return null;
  const start = nextNumber(annotation?.['window_start']);
  return (
    <Disclosure
      disclosureKey={disclosureKey({
        project,
        scope: compatSessKey(session),
        name: 'held-stamp',
      })}
      summary={`Saved${start !== null && start > 0 ? ` · reads from ${clock(start)}` : ''}`}
      className="next-cockpit-held-stamp"
    >
      <p>Adding a line keeps this window; saving new goal words opens another.</p>
      <span className="next-cockpit-held-revision">{line}</span>
      <span className="next-cockpit-define">Each save is a revision.</span>
      <span className="next-cockpit-held-bound">{compatSessKey(session)}</span>
    </Disclosure>
  );
}

export function IntentSection() {
  const { input, session, payload } = usePanel();
  const { ctx } = usePanel();
  const heading = useFocusKey<HTMLHeadingElement>(
    ctx.shell.controls.focusLane,
    `intent:${compatSessKey(session)}`,
  );
  const annotation = input.annotation;
  const generated = nextNumber(payload['generated']);
  const stamp = discardStamp(annotation, generated);
  const drafted = intentDrafted(input);
  const why = drafted ? '' : noDraftWhy(session, annotation, payload);
  const unreadable = storeUnreadable(payload);
  return (
    <section className="next-cockpit-held">
      <header>
        <h2
          id="next-session-intent-heading"
          ref={heading}
          tabIndex={-1}
          data-next-focus={`intent:${compatSessKey(session)}`}
        >
          Intent
        </h2>
      </header>
      {/* Under the heading rather than in its header, so the revision line keeps the sentence tier. */}
      <SavedStamp />
      {why ? (
        <p className="next-cockpit-held-lede" data-next-intent-no-draft>
          {why}
        </p>
      ) : null}
      {unreadable ? <p className="next-cockpit-held-absent">{unreadable}</p> : null}
      {stamp ? (
        <div className="next-cockpit-held-stamp">
          <span className="next-cockpit-held-revision">{stamp}</span>
        </div>
      ) : null}
      <div className="next-cockpit-held-fields">
        <GoalField />
        <OutcomeLines />
      </div>
      <Footer />
    </section>
  );
}
