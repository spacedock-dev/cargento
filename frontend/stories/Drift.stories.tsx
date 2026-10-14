import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, userEvent, waitFor, within } from 'storybook/test';
import {
  HARNESS_LIMIT,
  JOB_NOTE_SO_FAR,
  JOB_TITLE,
  LIVE_LEVEL_NAMES,
  NUDGE,
  RESULT_DEPARTS,
} from '../src/drift/sentences';
import { INTENT_EDITED } from '../src/intent/sentences';
import {
  DEPARTURE_READING,
  DriftScenario,
  failedCheck,
  fact,
  passedCheck,
  STORED_READING,
  written,
  type Scenario,
} from './drift.scenario';
import { REASON_CASES, routeFor } from './drift.reasons';

/* The Intent and drift card, held by stage, by harness and by route. Each story mounts the real page over a
   scripted backend and asserts what a reader sees: the words the card prints and the controls it draws. The
   strings come from the page's own sentence tables where they are one string, and are spelt out where the
   page composes them from a count or a number. Every story asserts a retired string ("Looks right",
   "Send to session") absent, and a result also asserts `Done` and a check mark absent, because a result is an
   account of the evidence and never that the work was done. */

const meta = {
  title: 'Drift/Stages, harness limits and no reader',
  component: DriftScenario,
} satisfies Meta<typeof DriftScenario>;
export default meta;
type Story = StoryObj<typeof meta>;

const scenario = (value: Scenario): Pick<Story, 'args'> => ({ args: { scenario: value } });

/* The control the page draws as its one primary. The count is over the whole page: the Raise control is the
   only other primary the page owns, and only for a session that is waiting on the reader. */
const primaries = (root: HTMLElement): HTMLElement[] => [
  ...root.querySelectorAll<HTMLElement>('[data-variant="primary"]'),
];
const action = (root: HTMLElement, name: string): HTMLElement | null =>
  root.querySelector<HTMLElement>(`[data-next-cockpit-action="${name}"]`);
const said = (node: Element | null): string =>
  (node?.textContent ?? '').replace(/\s+/g, ' ').trim();

async function drawn(canvasElement: HTMLElement): Promise<HTMLElement> {
  await waitFor(() => expect(canvasElement.querySelector('#next-session-drift')).not.toBeNull());
  return canvasElement.querySelector('#next-session-drift') as HTMLElement;
}

/* A result's account of the work is never "done": no word for it and no mark. */
async function neverDone(root: HTMLElement) {
  await expect(root.textContent).not.toMatch(/\bDone\b/);
  await expect(root.textContent).not.toMatch(/[✓✔]/);
}

async function neverRetired(root: HTMLElement) {
  await expect(root.textContent).not.toContain('Looks right');
  await expect(root.textContent).not.toContain('Send to session');
}

/* A failed check counts for Steer back only after a message from the person, so each story that offers it
   carries one before the check. */
const FAILED = [failedCheck('c1', 500)];
const personSaid = (harness = 'claude') =>
  fact('u1', 200, { type: 'user_message', by: 'person:me', summary: 'Ship it' }, harness);
const PROMPT = personSaid();
const WRITES = [
  written('w1', 220, 'src/queue/worker.ts'),
  written('w2', 240, 'src/queue/index.ts'),
  written('w3', 260, 'tests/test_queue.py'),
];

/* Stage 1: no saved words. The first prompt is drafted into the goal box and marked as the prompt's, nothing
   is stored, and the press that reads it adopts it, so Analyze is the one primary. Save intent is live over
   the draft and stays quiet. */
export const IdleWithADraftedGoal: Story = {
  ...scenario({ unsaved: true }),
  play: async ({ canvasElement }) => {
    const card = await drawn(canvasElement);
    const page = within(canvasElement);
    const goal = await page.findByRole('textbox', { name: 'Goal' });
    await expect(goal).toHaveValue('Ship the queue worker');
    await expect(canvasElement.querySelector('[data-next-cockpit-draft-marks]')).toHaveTextContent(
      'from your prompt',
    );
    await expect(page.getByRole('button', { name: 'Save intent' })).not.toHaveAttribute(
      'aria-disabled',
      'true',
    );
    const analyze = action(card, 'reading-ask');
    await expect(analyze).toHaveTextContent('Analyze drift');
    await expect(analyze).not.toHaveAttribute('aria-disabled');
    await expect(card.querySelector('#next-cockpit-reading-refused')).toBeNull();
    await expect(primaries(canvasElement)).toEqual([analyze]);
    await neverRetired(canvasElement);
  },
};

/* The same stage once the reader edits the draft: Analyze would read words that are not saved, so it is
   refused with the step that lifts that. The refused control stays on the page in its primary weight, drawn
   hatched, so the one primary does not move while the words are saved. */
export const IdleWithAnEditedDraft: Story = {
  ...scenario({ unsaved: true }),
  play: async ({ canvasElement }) => {
    const card = await drawn(canvasElement);
    const goal = await within(canvasElement).findByRole('textbox', { name: 'Goal' });
    await userEvent.type(goal, ', then verify');
    await waitFor(() =>
      expect(card.querySelector('#next-cockpit-reading-refused')).toHaveTextContent(INTENT_EDITED),
    );
    const analyze = action(card, 'reading-ask');
    await expect(analyze).toHaveAttribute('aria-disabled', 'true');
    await expect(primaries(canvasElement)).toEqual([analyze]);
    await neverRetired(canvasElement);
  },
};

const LIVE_HIGH = {
  harness: 'claude',
  sid: 's1',
  level: 'high',
  revision: 3,
  computed_at: 990,
  reasons: ['failed-check'],
  cites: ['c1'],
  rose_at: '',
  rose_from: '',
};

/* Stage 2: the live monitor is the reader's switch, off until pressed, and its level is from checks and file
   paths with no model. */
export const LiveMonitorAtHigh: Story = {
  ...scenario({ facts: [PROMPT, ...FAILED], work: { live_levels: [LIVE_HIGH] } }),
  play: async ({ canvasElement }) => {
    const card = await drawn(canvasElement);
    const page = within(canvasElement);
    const monitor = await page.findByRole('switch', { name: 'Live monitor' });
    await expect(monitor).toHaveAttribute('aria-checked', 'false');
    await expect(card.querySelector('[data-next-drift-level]')).toBeNull();
    await userEvent.click(monitor);
    const level = await waitFor(() => {
      const node = card.querySelector('[data-next-drift-level]');
      expect(node).not.toBeNull();
      return node as HTMLElement;
    });
    await expect(level.querySelector('.next-session-drift-level')).toHaveTextContent(
      LIVE_LEVEL_NAMES['high'] as string,
    );
    await expect(level.querySelector('.next-session-drift-source')).toHaveTextContent(
      /^Live estimate · \d\d:\d\d$/,
    );
    await expect(level).toHaveTextContent('Recorded signals');
    await expect(level).toHaveTextContent(/pytest -q failed .* ago at #\d+/);
    await expect(level).toHaveTextContent('Result time not recorded.');
    await expect(card).toHaveTextContent(NUDGE);
    await expect(action(card, 'reading-ask')).toHaveTextContent('Analyze drift');
    await expect(primaries(canvasElement)).toHaveLength(1);
    await expect(primaries(canvasElement)[0]).toBe(action(card, 'reading-ask'));
    await neverRetired(canvasElement);
  },
};

const JOB = {
  id: 'j1',
  phase: 'read',
  steps: [
    { phase: 'collect', text: 'Collecting the record' },
    { phase: 'read', text: 'Reading it' },
    { phase: 'write', text: 'Writing the result' },
  ],
};

/* Stage 3: the card says what is running and stands Cancel where Analyze was, so no new press is offered. */
export const Analyzing: Story = {
  ...scenario({
    session: { state: 'working' },
    facts: FAILED,
    payload: { reading_jobs: { 'claude:s1': JOB } },
  }),
  play: async ({ canvasElement }) => {
    const card = await drawn(canvasElement);
    const box = await waitFor(() => {
      const node = card.querySelector('[data-next-analyzing]');
      expect(node).not.toBeNull();
      return node as HTMLElement;
    });
    await expect(box.querySelector('.next-cockpit-reading-job-title')).toHaveTextContent(JOB_TITLE);
    await expect(
      [...box.querySelectorAll('.next-cockpit-reading-step')].map((step) => [
        said(step),
        step.getAttribute('data-state'),
      ]),
    ).toEqual([
      ['Collecting the record', 'done'],
      ['Reading it', 'active'],
      ['Writing the result', 'todo'],
    ]);
    await expect(box.querySelector('.next-cockpit-reading-job-note')).toHaveTextContent(
      JOB_NOTE_SO_FAR,
    );
    await expect(action(card, 'reading-cancel')).toHaveTextContent('Cancel');
    await expect(action(card, 'reading-ask')).toBeNull();
    await expect(box.textContent).not.toMatch(/[✓✔]/);
    // The running analysis is the card's state, not a press to make: nothing on the page asks for one.
    await expect(primaries(canvasElement)).toHaveLength(0);
    await neverRetired(canvasElement);
  },
};

/* Stage 4: a result under a departure leads with Steer back, the one primary, and offers the intent as the
   other way out. The model's own words about the departure are drawn, and the work is grouped by folder. */
export const ResultUnderADeparture: Story = {
  ...scenario({
    session: STORED_READING,
    facts: [...WRITES, ...FAILED, passedCheck('c2', 600)],
  }),
  play: async ({ canvasElement }) => {
    const card = await drawn(canvasElement);
    const result = await waitFor(() => {
      const node = card.querySelector('[data-next-result]');
      expect(node).not.toBeNull();
      return node as HTMLElement;
    });
    await expect(result.querySelector('.next-cockpit-result-headline')).toHaveTextContent(
      `${RESULT_DEPARTS}1 departure`,
    );
    const goal = result.querySelector('[data-next-result-goal]') as HTMLElement;
    await expect(goal).toHaveAttribute('data-next-result-state', 'departs');
    await expect(result.querySelector('.next-cockpit-result-answer')).toHaveTextContent(
      DEPARTURE_READING.criteria.goal.detail,
    );
    const line = result.querySelector('.next-cockpit-result-lines li') as HTMLElement;
    await expect(line).toHaveAttribute('data-next-result-state', 'consistent');
    await expect(line).toHaveTextContent(/Consistent with #\d+/);
    await expect(result.querySelector('.next-cockpit-result-work h3')).toHaveTextContent(
      'Where the work went',
    );
    await expect(result.querySelector('.next-cockpit-result-work')).toHaveTextContent(/src\/queue/);
    const steer = action(card, 'steer-back') as HTMLElement;
    await expect(steer).toHaveTextContent('Steer back');
    await expect(action(card, 'update-intent')).toHaveTextContent('Update intent instead');
    await expect(primaries(canvasElement)).toEqual([steer]);
    // A current result draws no second run control; Analyze returns when the reading is out of date.
    await expect(action(card, 'reading-ask')).toBeNull();
    await neverDone(result);
    await neverRetired(canvasElement);
  },
};

/* Stage 5: work that arrived after the reading says so, and the one press that reads it again stands in the
   callout, with nowhere else on the card to start another. */
export const StaleResult: Story = {
  ...scenario({
    session: STORED_READING,
    facts: [
      ...WRITES,
      ...FAILED,
      passedCheck('c2', 600),
      passedCheck('c3', 1200),
      fact('m1', 1250, { type: 'agent_message', by: 'agent' }),
    ],
  }),
  play: async ({ canvasElement }) => {
    const card = await drawn(canvasElement);
    const stale = await waitFor(() => {
      const node = card.querySelector('[data-next-result-stale="work"]');
      expect(node).not.toBeNull();
      return node as HTMLElement;
    });
    await expect(stale).toHaveTextContent('New work since this analysis.');
    const again = card.querySelectorAll('[data-next-cockpit-action="reading-ask"]');
    await expect(again).toHaveLength(1);
    await expect(again[0]).toHaveTextContent('Analyze again');
    await expect(stale.contains(again[0] as Node)).toBe(true);
    await expect(card.querySelector('[data-next-result]')).toHaveTextContent(
      '1 check, 1 message arrived since this analysis.',
    );
    // The departure still stands, so Steer back stays the one primary and Analyze again is the quiet way to
    // read the new work.
    await expect(primaries(canvasElement)).toEqual([action(card, 'steer-back')]);
    await neverDone(card);
    await neverRetired(canvasElement);
  },
};

const NO_READER = 'not-installed';

/* Stage 6: no reader on this machine. The reason stands where Analyze would be and no inert Analyze is
   drawn, because there is no press to refuse. With a failed check on the record, Steer back is the one
   primary: it is the only thing the page can still offer. */
export const NoReader: Story = {
  ...scenario({ facts: [PROMPT, ...FAILED], route: routeFor(NO_READER) }),
  play: async ({ canvasElement }) => {
    const card = await drawn(canvasElement);
    await noReaderStory(canvasElement, card, NO_READER);
  },
};

async function noReaderStory(canvasElement: HTMLElement, card: HTMLElement, reason: string) {
  const note = REASON_CASES[reason]?.note as string;
  const sentence = await waitFor(() => {
    const node = card.querySelector('[data-next-reading-no-reader]');
    expect(node).not.toBeNull();
    return node as HTMLElement;
  });
  await expect(sentence).toHaveTextContent(note);
  await expect(action(card, 'reading-ask')).toBeNull();
  await expect(card).not.toHaveTextContent('Analyze drift');
  const steer = action(card, 'steer-back') as HTMLElement;
  await expect(steer).toHaveTextContent('Steer back');
  await expect(primaries(canvasElement)).toEqual([steer]);
  await neverRetired(canvasElement);
}

/* One story per reason the producer can give a route, built by `routeStory` so the guard in
   `drift.reasons.test.ts` reads each reason off the call. A reason with no reader draws its sentence where
   Analyze would be. A reason with a reader draws Analyze, and says why this reader in "What is sent". */
function routeStory(reason: string): Story {
  const found = REASON_CASES[reason];
  if (!found) throw new Error(`no story fixture for route reason ${reason}`);
  const harness = found.harness;
  const checks = [personSaid(harness), failedCheck('c1', 500, harness)];
  return {
    ...scenario({ harness, facts: checks, route: routeFor(reason) }),
    play: async ({ canvasElement }) => {
      const card = await drawn(canvasElement);
      if (!found.provider) {
        await noReaderStory(canvasElement, card, reason);
        return;
      }
      const analyze = await waitFor(() => {
        const node = action(card, 'reading-ask');
        expect(node).not.toBeNull();
        return node as HTMLElement;
      });
      await expect(analyze).toHaveTextContent('Analyze drift');
      await expect(card.querySelector('[data-next-reading-no-reader]')).toBeNull();
      const sent = within(card).getByRole('button', {
        name: found.fallback ? `What is sent to ${found.label}` : 'What is sent',
      });
      await userEvent.click(sent);
      await waitFor(() =>
        expect(within(document.body).getByText(found.note, { exact: false })).toBeVisible(),
      );
      await expect(primaries(canvasElement)).toEqual([analyze]);
      await neverRetired(canvasElement);
    },
  };
}

export const OwnHarnessReads: Story = routeStory('own-harness');
export const HarnessWithNoProducerIsReadByCodex: Story = routeStory('no-own-producer');
export const ClaudeCodeMissingFallsBackToCodex: Story = routeStory('fallback-not-installed');
export const ClaudeCodeUnqualifiedFallsBackToCodex: Story = routeStory('fallback-not-qualified');
export const NoReaderNeitherInstalled: Story = routeStory('not-installed');
export const NoReaderClaudeMissingCodexUnqualified: Story = routeStory(
  'not-installed-other-not-qualified',
);
export const NoReaderClaudeUnqualifiedCodexMissing: Story = routeStory(
  'not-qualified-other-not-installed',
);
export const NoReaderNeitherQualified: Story = routeStory('not-qualified');

/* Harness limits. Compass reads work results from Claude Code and Pi only, the live estimate from Claude
   Code only, and corrections for Claude Code only; a card for any other harness says so and draws no level,
   because a level from work it cannot read would measure nothing. */

const ANALYSIS_HIGH = {
  harness: 'pi',
  sid: 's1',
  level: 'high',
  revision_read: 3,
  read_at: 1000,
  reasons: ['failed-check'],
  cites: ['c1'],
};

export const ClaudeCodeShowsLevelSwitchAndSteerBack: Story = {
  ...scenario({ facts: [PROMPT, ...FAILED], work: { live_levels: [LIVE_HIGH] } }),
  play: async ({ canvasElement }) => {
    const card = await drawn(canvasElement);
    const monitor = await within(canvasElement).findByRole('switch', { name: 'Live monitor' });
    await userEvent.click(monitor);
    await waitFor(() =>
      expect(card.querySelector('[data-next-drift-level]')).toHaveTextContent('High'),
    );
    await expect(card.querySelector('[data-next-drift-limit]')).toBeNull();
    await expect(card.querySelector('.next-session-drift-meter')).not.toBeNull();
    await expect(action(card, 'steer-back')).toHaveTextContent('Steer back');
    await expect(primaries(canvasElement)).toEqual([action(card, 'reading-ask')]);
    await neverRetired(canvasElement);
  },
};

/* Pi has work results and so a level, but only from an analysis: there is no live estimate to switch on, and
   no correction to steer back with. */
export const PiShowsAnalysisLevelWithNoSwitchAndNoSteerBack: Story = {
  ...scenario({
    harness: 'pi',
    session: STORED_READING,
    facts: [...WRITES, failedCheck('c1', 500, 'pi'), passedCheck('c2', 600, 'pi')],
    work: { analysis_levels: [ANALYSIS_HIGH] },
  }),
  play: async ({ canvasElement }) => {
    const card = await drawn(canvasElement);
    const level = await waitFor(() => {
      const node = card.querySelector('[data-next-drift-level]');
      expect(node).not.toBeNull();
      return node as HTMLElement;
    });
    await expect(level.querySelector('.next-session-drift-level')).toHaveTextContent('High');
    await expect(level.querySelector('.next-session-drift-source')).toHaveTextContent('Analysis');
    await expect(
      canvasElement.querySelector('[data-next-cockpit-action="live-monitor"]'),
    ).toBeNull();
    await expect(within(canvasElement).queryByRole('switch')).toBeNull();
    await expect(action(card, 'steer-back')).toBeNull();
    await expect(card.querySelector('[data-next-drift-limit]')).toBeNull();
    await expect(card).not.toHaveTextContent('Live estimate');
    // A current result draws no run control and Pi has nothing to steer with, so no control is primary.
    await expect(primaries(canvasElement)).toHaveLength(0);
    await neverRetired(canvasElement);
  },
};

/* Codex and Antigravity: the sentence in place of a level, and neither a meter nor a switch. Analyze is still
   offered, because a reading needs the saved words and the messages, not work results. */
const limited = (harness: 'codex' | 'antigravity'): Story => ({
  ...scenario({ harness, facts: [personSaid(harness), failedCheck('c1', 500, harness)] }),
  play: async ({ canvasElement }) => {
    const card = await drawn(canvasElement);
    const limit = await waitFor(() => {
      const node = card.querySelector('[data-next-drift-limit]');
      expect(node).not.toBeNull();
      return node as HTMLElement;
    });
    await expect(limit).toHaveTextContent(HARNESS_LIMIT);
    await expect(card.querySelector('[data-next-drift-level]')).toBeNull();
    await expect(card.querySelector('[data-next-drift-unchecked]')).toBeNull();
    await expect(card.querySelector('.next-session-drift-meter')).toBeNull();
    await expect(card.querySelector('.next-session-drift-scale')).toBeNull();
    await expect(within(canvasElement).queryByRole('switch')).toBeNull();
    await expect(action(card, 'steer-back')).toBeNull();
    const analyze = action(card, 'reading-ask') as HTMLElement;
    await expect(analyze).toHaveTextContent('Analyze drift');
    await expect(primaries(canvasElement)).toEqual([analyze]);
    await neverRetired(canvasElement);
  },
});

export const CodexSaysItCannotReadWork: Story = limited('codex');
export const AntigravitySaysItCannotReadWork: Story = limited('antigravity');
