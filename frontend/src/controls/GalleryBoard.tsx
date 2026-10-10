import { Button, buttonVariants } from '../ui/button';
import { useState } from 'react';
import { memoKey } from '../storage';
import { selectSessions } from '../store/selectors';
import { useBoardRuntime } from '../transport/hooks';
import { CopyControl } from './CopyControl';
import { DraftTextarea } from './DraftField';
import { Disclosure } from './Disclosure';
import { disclosureKey } from './disclosureStore';
import type { World } from './galleryWorld';
import { HumanContextField } from './HumanContextField';
import { useControls } from './kit';
import { MoreMenu } from './MoreMenu';
import { RaiseControl } from './RaiseControl';
import { useChoiceRelease } from './useChoiceRelease';
import { useDisplayedSelector } from './useDisplayed';
import { useFocusKey } from './useFocusKey';

/* Replaced on every paint (its key is the board revision), so a browser test can watch the focus
   lane put focus back on a keyed control that a redraw swapped, with and without a scroll. */
function ParkedControl() {
  const { focusLane } = useControls();
  const ref = useFocusKey<HTMLButtonElement>(focusLane, 'parked');
  return (
    <Button variant="bare" type="button" ref={ref}>
      Parked control
    </Button>
  );
}

export function GalleryBoard({ world }: { world: World }) {
  useBoardRuntime(world.runtime);
  useChoiceRelease(world.gate);
  const sessions = useDisplayedSelector(world.gate, selectSessions);
  const displayedAccepted = useDisplayedSelector(world.gate, (snapshot) => snapshot.acceptedCount);
  const displayedGenerated = useDisplayedSelector(
    world.gate,
    (snapshot) => snapshot.data?.generated ?? 0,
  );
  const [choice, setChoice] = useState('');
  const [reservedBusy, setReservedBusy] = useState(false);
  const [draftShown, setDraftShown] = useState(true);
  // The words belong to the caller (here, this state); the field keeps only caret, scroll and size.
  const [draftText, setDraftText] = useState('');
  const [disclosuresShown, setDisclosuresShown] = useState(true);
  const first = sessions.rows[0];
  const second = sessions.rows[1];
  const project = first?.project_key ?? first?.project ?? 'alpha/app';

  return (
    <main id="gallery">
      <h1>Shared controls</h1>
      <section aria-label="Button gallery" data-button-gallery style={{ maxWidth: '100%' }}>
        <Button data-example="default">Default action</Button>
        <Button data-example="hover">Hover action</Button>
        <Button data-example="focus">Focus action</Button>
        <Button data-example="pending" aria-busy="true" aria-disabled="true" busyLabel="Saving…">
          Save intent
        </Button>
        <Button data-example="disabled" disabled>
          Unavailable action
        </Button>
        <Button data-example="long">
          Save the long intent that explains every expected outcome to the reader
        </Button>
        <Button data-example="primary" variant="primary">
          Primary action
        </Button>
        <Button data-example="quiet" variant="quiet">
          Quiet action
        </Button>
        <Button data-example="raise-primary" variant="raise-primary">
          RAISE
        </Button>
        <Button
          data-example="reserved"
          reserve="Saving the intent…"
          busyLabel="Saving…"
          {...(reservedBusy ? { 'aria-busy': true, 'aria-disabled': true } : {})}
          onClick={() => setReservedBusy(true)}
        >
          Save
        </Button>
        <a href="#gallery" data-example="link" data-slot="button-link" className={buttonVariants()}>
          Linked action
        </a>
      </section>
      <p>
        Displayed board revision{' '}
        <output data-readout="displayed-accepted">{displayedAccepted}</output>, generated{' '}
        <output data-readout="displayed-generated">{displayedGenerated}</output>
      </p>

      <section aria-label="Native select">
        <label htmlFor="stage-choice">Stage condition</label>
        <select
          id="stage-choice"
          className="ctl-select"
          value={choice}
          onChange={(event) => setChoice(event.target.value)}
        >
          <option value="">Choose a session</option>
          {sessions.rows.map((row) => (
            <option key={`${row.harness}:${row.sid}`} value={`${row.harness}:${row.sid}`}>
              {`${row.title ?? row.sid} · ${String(row.harness)} · board ${String(displayedAccepted)}`}
            </option>
          ))}
        </select>
        <output className="ctl-wrap" data-readout="choice">
          {choice}
        </output>
      </section>

      <section aria-label="Session controls">
        {first ? (
          <div>
            <CopyControl kind="id" harness={first.harness} sid={first.sid} value={first.sid} />
            <CopyControl
              kind="link"
              harness={first.harness}
              sid={first.sid}
              value={`${location.origin}/#n=session:${first.sid}`}
            />
            <CopyControl
              kind="command"
              harness={first.harness}
              sid={first.sid}
              value={`claude --resume ${first.sid}`}
            />
            <RaiseControl harness={first.harness} sid={first.sid} focusable />
          </div>
        ) : null}
        {second ? (
          <div>
            <CopyControl kind="id" harness={second.harness} sid={second.sid} value={second.sid} />
            <RaiseControl harness={second.harness} sid={second.sid} focusable />
          </div>
        ) : null}
      </section>

      <section aria-label="Disclosures">
        <Button variant="bare" type="button" onClick={() => setDisclosuresShown(!disclosuresShown)}>
          {disclosuresShown ? 'Hide disclosures' : 'Show disclosures'}
        </Button>
        {disclosuresShown ? (
          <>
            <Disclosure
              disclosureKey={disclosureKey({ project, scope: null, name: 'plan' })}
              summary="Project plan"
            >
              <p data-readout="plan-body">{`Plan as of board ${String(displayedAccepted)}`}</p>
              <Button variant="bare" type="button">
                Inside the plan
              </Button>
            </Disclosure>
            <Disclosure
              disclosureKey={disclosureKey({ project, scope: null, name: 'why' })}
              summary="Why"
              variant="popover"
            >
              <p>{`Because of board ${String(displayedAccepted)}`}</p>
            </Disclosure>
          </>
        ) : null}
      </section>

      <section aria-label="Project menu">
        <MoreMenu
          projectKey={project}
          focus={null}
          running={sessions.rows.filter((row) => row.active === true).length}
          subagents={0}
          briefingText={() => `Briefing for ${project}`}
          addHumanContext={{ memoKey: memoKey(project, null, 'outcome') }}
        />
      </section>

      <section aria-label="Human context">
        <HumanContextField
          memoKey={memoKey(project, null, 'outcome')}
          kind="outcome"
          label="OUTCOME"
          placeholder="What result should this scope achieve?"
        />
        <HumanContextField
          memoKey={memoKey(project, null, 'focus')}
          kind="focus"
          label="FOCUS"
          placeholder="What are you concentrating on now?"
        />
      </section>

      <section aria-label="Draft">
        <Button variant="bare" type="button" onClick={() => setDraftShown(!draftShown)}>
          {draftShown ? 'Hide draft' : 'Show draft'}
        </Button>
        {draftShown ? (
          <>
            <label htmlFor="gallery-draft">Draft note</label>
            <DraftTextarea
              id="gallery-draft"
              memoryKey={`gallery:draft:${project}`}
              focusKey="gallery-draft"
              className="ctl-draft"
              rows={4}
              defaultValue={draftText}
              onInput={(event) => setDraftText(event.currentTarget.value)}
            />
          </>
        ) : null}
      </section>

      <div aria-hidden="true" style={{ blockSize: 2400 }} />
      <ParkedControl key={displayedAccepted} />
    </main>
  );
}
