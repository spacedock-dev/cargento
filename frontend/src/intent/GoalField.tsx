import { nextNumber } from '../api/bootstrap';
import { clock } from '../observed';
import { PROMPT_CHOSEN, PROMPT_SOURCES } from '../sessions/intent';
import { ActionButton } from './ActionButton';
import { storeUnreadable } from './annotation';
import { heldSentence } from './cues';
import { clearGoal, escapeGoal, typeGoal } from './edit';
import { directionLinesQuestion, goalBaseline, goalKey, intentDraft, type Draft } from './derive';
import { answerLines } from './directions';
import { HeldTextarea } from './HeldTextarea';
import { PromptSelect } from './PromptSelect';
import { EXCERPT_READ_WHOLE } from './sentences';
import { usePanel } from './useIntent';

/* Where the goal came from, and that an excerpt is one. Drawn while the box holds the draft; the first edit
   takes it away, and a box put back to the draft brings it back. Save intent is the one way to save the
   draft. */
function DraftMarks({ draft }: { readonly draft: Draft }) {
  /* A chosen prompt is named by its own time, which is what tells it apart from the others the menu listed. */
  const which =
    draft.source === 'latest-prompt'
      ? ' · latest'
      : draft.source === PROMPT_CHOSEN
        ? ` · ${clock(draft.at ?? 0)}`
        : '';
  const clipped = draft.cut === true || draft.text.endsWith('…');
  return (
    <span className="next-intent-draft-marks" data-next-cockpit-draft-marks>
      <span className="next-intent-draft-source">{`from your prompt${which}`}</span>
      {clipped ? <span className="next-cockpit-held-cue">{EXCERPT_READ_WHOLE}</span> : null}
    </span>
  );
}

/* The saved goal's own source line, for a goal adopted from a prompt. */
function SourceLine() {
  const { input } = usePanel();
  const annotation = input.annotation;
  if (!annotation || !PROMPT_SOURCES.includes(annotation['goal_source'] as string)) return null;
  const at = nextNumber(annotation['goal_source_at']);
  const source = annotation['goal_source'];
  const which =
    source === 'first-prompt'
      ? 'first'
      : source === 'latest-prompt'
        ? 'latest'
        : at !== null && at > 0
          ? clock(at)
          : 'chosen';
  const clipped = String(annotation['goal'] || '').endsWith('…') ? ` ${EXCERPT_READ_WHOLE}` : '';
  return (
    <small className="next-cockpit-held-cue">{`from your prompt · ${which}.${clipped}`}</small>
  );
}

/* "Keep your standing outcome lines with this goal?": asked once when a direction became the goal, and Save
   intent waits for the answer. */
function LinesQuestion() {
  const { ctx, session } = usePanel();
  if (!directionLinesQuestion(ctx.held, session)) return null;
  return (
    <>
      <p>Keep your standing outcome lines with this goal?</p>
      <ActionButton
        weight="none"
        label="Keep outcome lines"
        action="direction-lines-keep"
        focusKey="direction-lines-keep"
        onPress={() => answerLines(ctx, session, 'keep')}
      />
      <ActionButton
        weight="none"
        label="Clear outcome lines"
        action="direction-lines-clear"
        focusKey="direction-lines-clear"
        onPress={() => answerLines(ctx, session, 'clear')}
      />
    </>
  );
}

export function GoalField() {
  const { ctx, input, session, cap } = usePanel();
  const { held } = ctx;
  const key = goalKey(session);
  const drafted = intentDraft(input);
  const saved = goalBaseline(input);
  const text = held.goals.has(key) ? (held.goals.get(key) ?? saved) : saved;
  const untouched = Boolean(drafted) && text === drafted?.text;
  const why = storeUnreadable(input.payload) ? '' : String(input.annotation?.['goal_why'] || '');
  const cue = heldSentence(held.kind(key), null);
  return (
    <div
      className="next-cockpit-held-field"
      data-next-cockpit-held-field="goal"
      {...(untouched ? { 'data-next-cockpit-drafted': '' } : {})}
    >
      <div className="next-cockpit-held-heading">
        <span className="next-cockpit-held-label">Goal</span>
        <PromptSelect />
      </div>
      <HeldTextarea
        rows={3}
        maxLength={cap}
        memoryKey={key}
        focusKey={key}
        text={text}
        placeholder="what you are after, in one line"
        data-next-cockpit-held-kind="goal"
        data-next-cockpit-held-key={key}
        data-next-focus={key}
        onEdit={(raw) => typeGoal(ctx, input, raw)}
        onKeyDown={(event) => {
          if (event.key !== 'Escape') return;
          event.preventDefault();
          event.stopPropagation();
          escapeGoal(ctx, input);
        }}
      />
      <div className="next-cockpit-held-under">
        <span className="next-cockpit-held-count" data-next-cockpit-held-count="goal">
          {`${String(text.length)}/${String(cap)}`}
        </span>
        {/* Where the words came from sits between the count and Clear, as an outcome line's source sits
            between its count and Remove. In the label row it was a line of its own, and moved the box the
            pick fills 25px down and back up on the first keystroke. */}
        {untouched && drafted ? <DraftMarks draft={drafted} /> : <SourceLine />}
        <ActionButton
          label="Clear"
          action="held-clear"
          arg="goal"
          hidden={!text}
          focusKey={`${key}:clear`}
          onPress={() => clearGoal(ctx, input)}
        />
      </div>
      {/* The absence sentence answers "why is this empty", so it goes when the box stops being empty. It
          stays in the document, visually hidden, because the inert Save intent is described by it. */}
      {why ? (
        <p
          className="next-cockpit-held-absent next-visually-hidden"
          id="next-cockpit-held-absent-goal"
          data-next-cockpit-held-absent="goal"
          hidden={Boolean(text)}
        >
          {why}
        </p>
      ) : null}
      <LinesQuestion />
      {cue ? <small className="next-cockpit-held-cue">{cue}</small> : null}
    </div>
  );
}
