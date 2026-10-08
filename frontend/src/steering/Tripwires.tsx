import type { FormEvent, KeyboardEvent } from 'react';
import { DraftInput } from '../controls/DraftField';
import { useShell } from '../shell/context';
import { useFocusKey } from '../controls/useFocusKey';
import { useControls } from '../controls/kit';
import { RailHeader } from './RailHeader';
import { TEXT_LIMIT, useHeldVersion, useSteeringHeld } from './held';
import './steering.css';

/* The tripwires a reader keeps for a project: browser preferences, never instructions sent to a session. The
   panel says so in its heading and again beneath the rows, because nothing on this page enforces them, and a
   control that looks like a guard and is not one is the false reassurance this board exists to avoid.

   The rules live in the guardrail store (the released `cargento.next.guardrails.` family, older string rules
   still readable); what is typed and not yet added, and whether the add box is open, live in the held state
   by the exact project label. */
export function Tripwires({ project }: { readonly project: string }) {
  const { runtime } = useShell();
  const held = useSteeringHeld();
  useHeldVersion(held);
  const rules = runtime.storage.guardrails.rules(project);
  return (
    <section
      className="next-control next-guardrails next-rail-panel"
      data-next-guardrails
      data-next-rail-panel="tripwires"
    >
      <RailHeader
        label="TRIPWIRES"
        note="local only · nothing enforces these"
        tone="amber"
        sentence
      />
      <div className="next-guardrail-rows">
        {rules.length === 0 ? (
          <p className="next-guardrail-empty">No tripwires saved in this browser.</p>
        ) : (
          rules.map((rule, index) => (
            <button
              // The rules carry no identity of their own and only ever append or drop from the front, so
              // a toggle is addressed by the position it was drawn at, as the stored list is.
              key={index}
              type="button"
              className="next-guardrail-row"
              role="switch"
              aria-checked={rule.enabled}
              data-next-guardrail-toggle={index}
              data-next-controls-project={project}
              onClick={() => {
                runtime.storage.guardrails.toggle(project, index);
                held.notify();
              }}
            >
              <span className="next-guardrail-glyph" aria-hidden="true">
                ◇
              </span>
              <span className="next-guardrail-copy">
                <strong>{rule.text}</strong>
                {rule.enabled ? null : <small>Disabled in this browser.</small>}
              </span>
            </button>
          ))
        )}
      </div>
      <AddRule project={project} />
      <p className="next-rail-reason">
        C1 would let an observer act on these. Until it ships they are a note to yourself, held in
        this browser.
      </p>
    </section>
  );
}

function AddRule({ project }: { readonly project: string }) {
  const { runtime } = useShell();
  const controls = useControls();
  const held = useSteeringHeld();
  const adding = held.adding(project);
  const addKey = `guardrail-add:${project}`;
  const addRef = useFocusKey<HTMLButtonElement>(controls.focusLane, addKey);
  const draftKey = `guardrail-draft:${project}`;

  /* Added or abandoned, the box is finished with, on BOTH branches. Without clearing it, reopening the add
     control prefills it with the rule the reader just committed, and one Enter then writes that rule a second
     time. */
  const finish = (input: HTMLInputElement | null, add: boolean) => {
    if (add && input) runtime.storage.guardrails.add(project, input.value);
    held.setAdding(project, false);
    held.clearDraft(project, 'guardrail');
    if (input) input.value = '';
    held.notify();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== 'Enter' && event.key !== 'Escape') return;
    /* The Enter that commits a composition belongs to the input method, not to the form: acting on it would
       add a rule from words the reader has not finished choosing. 229 is what browsers that report the
       key after the composition has ended send in its place. */
    if (event.nativeEvent.isComposing || event.keyCode === 229) return;
    event.preventDefault();
    event.stopPropagation();
    finish(event.currentTarget, event.key === 'Enter');
  };

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const input = event.currentTarget.elements.namedItem('guardrail');
    finish(input instanceof HTMLInputElement ? input : null, true);
  };

  if (adding) {
    return (
      <form
        className="next-guardrail-add-input"
        data-next-guardrail-form
        data-next-controls-project={project}
        onSubmit={onSubmit}
      >
        <label>
          <span className="next-visually-hidden">New local tripwire</span>
          <DraftInput
            memoryKey={draftKey}
            focusKey={draftKey}
            focusFallback={addKey}
            name="guardrail"
            maxLength={TEXT_LIMIT}
            placeholder="alert me when…"
            data-next-guardrail-input
            data-next-draft="guardrail"
            data-next-controls-project={project}
            defaultValue={held.draft(project, 'guardrail')}
            onKeyDown={onKeyDown}
            onInput={(event) => held.setDraft(project, 'guardrail', event.currentTarget.value)}
          />
        </label>
        <button type="submit" className="next-action">
          add ↵
        </button>
      </form>
    );
  }
  return (
    <button
      ref={addRef}
      type="button"
      className="next-action next-guardrail-add"
      data-next-guardrail-add
      data-next-controls-project={project}
      onClick={() => {
        held.setAdding(project, true);
        /* The control that was pressed is gone, and a reader who opened the box is about to type in it. The
           legacy page leaves focus on the document; a keyboard reader would then have to find the box. */
        queueMicrotask(() => controls.focusLane.focus(draftKey));
      }}
    >
      + set a tripwire
    </button>
  );
}
