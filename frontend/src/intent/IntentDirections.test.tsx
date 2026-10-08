import { act, fireEvent } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { openPendingDirection } from './api';
import { json } from './testing';
import {
  board,
  control,
  goalBox,
  inert,
  lineBoxes,
  mountSession,
  stored,
  text,
  type,
} from './panel.testing';

/* Later directions: what the reader said after saving their words, asked about before a reading is spent.
   Add opens one for review as a pending line, Keep settles every direction it was shown, and neither
   decides whether a direction conflicts. */

const settle = async (page: { settle: () => Promise<void> }) => {
  await page.settle();
  await page.settle();
};
const press = async (button: Element | null) => {
  await act(async () => {
    fireEvent.click(button as Element);
  });
};

const fact = (id: string, at: number, summary: string, extra: Record<string, unknown> = {}) => ({
  fact_id: id,
  type: 'user_message',
  by: 'person:me',
  summary,
  at,
  source_session: { harness: 'claude', sid: 's1' },
  ...extra,
});
const record =
  (...facts: unknown[]) =>
  () =>
    json({ semantic: { facts } });

const SAVED = { goal: 'Ship the worker', revision: 1 };
const SAVED_AT = { annotation_goal_saved_at: 500, annotation_at: 500 };
const ONE = [fact('f1', 600, 'Do it the careful way')];

describe('the question before the press', () => {
  it('asks about a later direction in the Analyze control’s place, naming the number it draws', async () => {
    const page = mountSession({
      store: SAVED,
      session: SAVED_AT,
      routes: { '/api/project-context': record(...ONE) },
    });
    await settle(page);
    expect(text('.next-cockpit-direction-said')).toBe(
      'You gave a later direction at #1: "Do it the careful way".',
    );
    expect(
      [...document.querySelectorAll('.next-cockpit-reading-ask button')].map((b) => b.textContent),
    ).toEqual(['Keep my intent', 'Add it to my intent', 'Use this as my goal']);
    expect(page.posts()).toBe(0);
  });

  it('asks nothing of a direction that was said before the words were saved, or already settled', async () => {
    const early = mountSession({
      store: SAVED,
      session: SAVED_AT,
      routes: { '/api/project-context': record(fact('f0', 400, 'Said before saving')) },
    });
    await settle(early);
    expect(document.querySelector('[data-next-cockpit-direction-question]')).toBeNull();
    early.unmount();
    const settled = mountSession({
      store: { ...SAVED, settled_through: 600 },
      session: { ...SAVED_AT, annotation_settled_at: 800, annotation_settled_revision: 1 },
      routes: { '/api/project-context': record(...ONE) },
    });
    await settle(settled);
    expect(document.querySelector('[data-next-cockpit-direction-question]')).toBeNull();
    expect(text('.next-cockpit-conflict summary')).toMatch(/^Later directions: settled /);
  });

  it('does not count a correction the reader copied from Cargento as something they said', async () => {
    const page = mountSession({
      store: SAVED,
      session: SAVED_AT,
      routes: {
        '/api/project-context': record(fact('f2', 650, 'A pasted correction', { copied: true })),
      },
    });
    await settle(page);
    expect(document.querySelector('[data-next-cockpit-direction-question]')).toBeNull();
  });

  it('names the selected direction of several and lets the reader pick another', async () => {
    const page = mountSession({
      store: SAVED,
      session: SAVED_AT,
      routes: {
        '/api/project-context': record(
          fact('f1', 600, 'First one.'),
          fact('f2', 700, 'Second one.'),
        ),
      },
    });
    await settle(page);
    expect(text('.next-cockpit-direction-said')).toBe(
      'You gave 2 later directions since saving your intent, the selected direction at #2: "Second one."',
    );
    const pick = document.querySelector('[data-next-direction-select]') as HTMLSelectElement;
    expect([...pick.options].map((o) => o.textContent)).toEqual([
      '#1 · First one.',
      '#2 · Second one.',
    ]);
    await act(async () => {
      fireEvent.change(pick, { target: { value: 'f1' } });
    });
    expect(text('.next-cockpit-direction-said')).toContain('at #1: "First one."');
    expect(page.posts()).toBe(0);
  });

  it('says the record could not be read rather than saying there was no direction', async () => {
    const page = mountSession({
      store: SAVED,
      session: SAVED_AT,
      routes: { '/api/project-context': () => json({}, 500) },
    });
    await settle(page);
    expect(text('.next-cockpit-conflict summary')).toBe(
      'Later directions: unknown (record unread)',
    );
  });
});

describe('Add it to my intent', () => {
  it('reads the direction whole, opens it as one pending line that is not saved, and saves only on Save', async () => {
    const page = mountSession({
      store: SAVED,
      session: SAVED_AT,
      routes: {
        '/api/project-context': record(...ONE),
        '/api/direction': () =>
          json({ ok: true, text: 'Do it the careful way, with a flag', clipped: false }),
        '/api/annotate': () => stored(2),
      },
    });
    await settle(page);
    await press(control('direction-add'));
    await settle(page);
    expect(page.allPosts().map((p) => p.path)).toEqual(['/api/direction']);
    expect(page.allPosts()[0]?.body).toEqual({ harness: 'claude', sid: 's1', fact_id: 'f1' });
    const line = document.querySelector('[data-next-cockpit-direction-key]') as HTMLTextAreaElement;
    expect(line.value).toBe('Do it the careful way, with a flag');
    expect(text('.next-cockpit-direction-line .next-cockpit-held-source')).toBe(
      'from #1 · not saved',
    );
    expect(document.activeElement).toBe(line);
    await press(control('direction-save'));
    await settle(page);
    expect(page.allPosts()[1]?.body).toEqual({
      harness: 'claude',
      sid: 's1',
      add_direction: 'f1',
      text: 'Do it the careful way, with a flag',
      expected_revision: 1,
    });
    expect(document.querySelector('[data-next-cockpit-direction-key]')).toBeNull();
  });

  it('sends a second press to the line already pending and reads nothing again', async () => {
    const page = mountSession({
      store: SAVED,
      session: SAVED_AT,
      routes: {
        '/api/project-context': record(...ONE),
        '/api/direction': () => json({ ok: true, text: 'Original', clipped: false }),
      },
    });
    await settle(page);
    await press(control('direction-add'));
    await settle(page);
    const line = document.querySelector('[data-next-cockpit-direction-key]') as HTMLTextAreaElement;
    type(line, 'My own edit');
    (document.activeElement as HTMLElement).blur();
    await press(control('direction-add'));
    expect(page.allPosts()).toHaveLength(1);
    expect(line.value).toBe('My own edit');
    expect(document.activeElement).toBe(line);
  });

  it('holds the whole text, counts it past the bound, and refuses to save it rather than cutting it', async () => {
    const long = 'w'.repeat(300);
    const page = mountSession({
      store: SAVED,
      session: SAVED_AT,
      routes: {
        '/api/project-context': record(...ONE),
        '/api/direction': () => json({ ok: true, text: long, clipped: false }),
        '/api/annotate': () => stored(2),
      },
    });
    await settle(page);
    await press(control('direction-add'));
    await settle(page);
    const line = document.querySelector('[data-next-cockpit-direction-key]') as HTMLTextAreaElement;
    expect(line.value).toHaveLength(300);
    expect(line.hasAttribute('maxlength')).toBe(false);
    expect(text('[data-next-cockpit-direction-count]')).toBe('300/240');
    expect(text('#next-cockpit-direction-why')).toBe(
      'A line holds 240 characters. Shorten this one to add it.',
    );
    expect(inert(control('direction-save'))).toBe(true);
    await press(control('direction-save'));
    expect(page.allPosts()).toHaveLength(1);
    type(line, 'short enough');
    expect(inert(control('direction-save'))).toBe(false);
    expect(text('#next-cockpit-direction-why')).toBe('');
  });

  it('says a direction the server cannot open opens nothing, and tries again on the next press', async () => {
    let answers = 0;
    const page = mountSession({
      store: SAVED,
      session: SAVED_AT,
      routes: {
        '/api/project-context': record(...ONE),
        '/api/direction': () => {
          answers += 1;
          return answers === 1
            ? json({ ok: false, why: 'That entry is no longer in the record.' })
            : json({ ok: true, text: 'Opened now', clipped: false });
        },
      },
    });
    await settle(page);
    await press(control('direction-add'));
    await settle(page);
    expect(document.querySelector('[data-next-cockpit-direction-key]')).toBeNull();
    expect(document.body.textContent).toContain('That entry is no longer in the record.');
    await press(control('direction-add'));
    await settle(page);
    expect(
      (document.querySelector('[data-next-cockpit-direction-key]') as HTMLTextAreaElement).value,
    ).toBe('Opened now');
  });

  it('keeps the line and says so when the store refuses the save', async () => {
    const page = mountSession({
      store: SAVED,
      session: SAVED_AT,
      routes: {
        '/api/project-context': record(...ONE),
        '/api/direction': () => json({ ok: true, text: 'Keep me', clipped: false }),
        '/api/annotate': () => json({ ok: true, outcome: 'refused', persisted: false }),
      },
    });
    await settle(page);
    await press(control('direction-add'));
    await settle(page);
    await press(control('direction-save'));
    await settle(page);
    expect(
      (document.querySelector('[data-next-cockpit-direction-key]') as HTMLTextAreaElement).value,
    ).toBe('Keep me');
    expect(text('.next-cockpit-direction-line .next-cockpit-held-cue')).toBe(
      'Not saved. The server refused the write, and your words are still in the box.',
    );
  });

  it('refuses the save over an unsaved edit, beside the line, and sends nothing', async () => {
    const page = mountSession({
      store: SAVED,
      session: SAVED_AT,
      routes: {
        '/api/project-context': record(...ONE),
        '/api/direction': () => json({ ok: true, text: 'A line', clipped: false }),
      },
    });
    await settle(page);
    await press(control('direction-add'));
    await settle(page);
    type(goalBox(), 'Edited goal');
    expect(text('#next-cockpit-direction-why')).toBe(
      'Save your intent, or undo your edit, to add this direction.',
    );
    expect(inert(control('direction-save'))).toBe(true);
    await press(control('direction-save'));
    expect(page.allPosts()).toHaveLength(1);
  });

  it('names the line to replace when the list is full, counting from zero for the server', async () => {
    const page = mountSession({
      store: { ...SAVED, lines: ['1', '2', '3', '4', '5', '6'], revision: 2 },
      session: SAVED_AT,
      routes: {
        '/api/project-context': record(...ONE),
        '/api/direction': () =>
          json({ ok: true, text: 'Take the third line’s place', clipped: false }),
        '/api/annotate': () => stored(3),
      },
    });
    await settle(page);
    await press(control('direction-add'));
    await settle(page);
    expect(text('#next-cockpit-direction-why')).toBe(
      'An expected outcome holds six lines. Replace or merge a line to add another.',
    );
    expect(inert(control('direction-save'))).toBe(true);
    await press(control('direction-replace', '2'));
    expect(control('direction-replace', '2')?.getAttribute('aria-pressed')).toBe('true');
    expect(inert(control('direction-save'))).toBe(false);
    await press(control('direction-save'));
    await settle(page);
    expect(page.allPosts()[1]?.body).toMatchObject({
      add_direction: 'f1',
      replace: 2,
      expected_revision: 2,
    });
  });

  it('opens from an analysis result through the exported action, and sends one request to read it whole', async () => {
    const page = mountSession({
      store: SAVED,
      session: SAVED_AT,
      routes: {
        '/api/project-context': record(...ONE),
        '/api/direction': () => json({ ok: true, text: 'From the result card', clipped: false }),
      },
    });
    await settle(page);
    await act(async () => {
      await openPendingDirection(page.shell, { harness: 'claude', sid: 's1' }, 'f1');
    });
    await settle(page);
    expect(page.allPosts()).toHaveLength(1);
    expect(
      (document.querySelector('[data-next-cockpit-direction-key]') as HTMLTextAreaElement).value,
    ).toBe('From the result card');
    expect(text('.next-cockpit-direction-line .next-cockpit-held-source')).toBe(
      'from #1 · not saved',
    );
  });

  it('opens an empty line when there is no direction to offer', async () => {
    const page = mountSession({
      store: SAVED,
      session: SAVED_AT,
      routes: { '/api/project-context': record() },
    });
    await settle(page);
    await act(async () => {
      await openPendingDirection(page.shell, { harness: 'claude', sid: 's1' }, null);
    });
    expect(lineBoxes()).toHaveLength(2);
    expect(page.posts()).toBe(0);
  });
});

describe('Keep my intent', () => {
  const routes = (page: () => ReturnType<typeof mountSession>) => ({
    '/api/project-context': record(
      fact('f1', 600, 'Do it the careful way, and then verify it on a clean checkout.'),
    ),
    '/api/direction': () =>
      json({
        ok: true,
        text: 'Do it the careful way, and then verify it on a clean checkout.',
        clipped: false,
      }),
    '/api/annotate': () => {
      void page;
      return stored(1, { outcome: 'unchanged' });
    },
  });

  it('draws the whole direction first and settles nothing, then settles on the next press naming the revision it drew', async () => {
    const holder: { page?: ReturnType<typeof mountSession> } = {};
    const page = mountSession({
      store: SAVED,
      session: SAVED_AT,
      routes: {
        ...routes(() => holder.page as never),
        '/api/project-context': record(
          fact('f1', 600, 'Do it the careful way, and then verify it'),
        ),
      },
    });
    holder.page = page;
    await settle(page);
    await press(control('direction-keep'));
    await settle(page);
    // The question quoted only its first words, so the whole text is drawn and the press stops.
    expect(text('.next-cockpit-direction-whole')).toContain(
      'Do it the careful way, and then verify it on a clean checkout.',
    );
    expect(page.allPosts().map((p) => p.path)).toEqual(['/api/direction']);
    expect(text('.next-cockpit-direction-question')).toContain(
      'Nothing was settled yet. Each direction Keep settles is now shown whole. Read it, then press again.',
    );
    expect(document.activeElement).toBe(
      document.querySelector('[data-next-cockpit-direction-whole]'),
    );
    await press(control('direction-keep'));
    await settle(page);
    expect(page.allPosts().map((p) => p.path)).toEqual(['/api/direction', '/api/annotate']);
    expect(page.allPosts()[1]?.body).toEqual({
      harness: 'claude',
      sid: 's1',
      settle_through: 600,
      expected_revision: 1,
    });
    expect(text('.next-cockpit-direction-question')).toContain(
      'Kept your intent and settled the direction. No analysis was started.',
    );
  });

  it('settles a sole direction the question quoted in full in one press, after opening it', async () => {
    const page = mountSession({
      store: SAVED,
      session: SAVED_AT,
      routes: {
        '/api/project-context': record(fact('f1', 600, 'Short.')),
        '/api/direction': () => json({ ok: true, text: 'Short.', clipped: false }),
        '/api/annotate': () => stored(1, { outcome: 'unchanged' }),
      },
    });
    await settle(page);
    await press(control('direction-keep'));
    await settle(page);
    expect(page.allPosts().map((p) => p.path)).toEqual(['/api/direction', '/api/annotate']);
  });

  it('refuses over an unsaved edit with the one sentence, sending nothing', async () => {
    const page = mountSession({
      store: SAVED,
      session: SAVED_AT,
      routes: { '/api/project-context': record(...ONE) },
    });
    await settle(page);
    type(goalBox(), 'Edited goal');
    await press(control('direction-keep'));
    expect(page.posts()).toBe(0);
    expect(text('#next-cockpit-cue-status')).toBe(
      'Save your intent, or undo your edit, to analyze drift.',
    );
  });

  it('says nothing was settled when a direction cannot be opened, and a direction that arrived since is unread', async () => {
    let first = true;
    const page = mountSession({
      store: SAVED,
      session: SAVED_AT,
      routes: {
        '/api/project-context': record(...ONE),
        '/api/direction': () =>
          first
            ? json({ ok: false })
            : json({ ok: true, text: 'Do it the careful way', clipped: false }),
        '/api/annotate': () => stored(1, { outcome: 'unchanged' }),
      },
    });
    await settle(page);
    await press(control('direction-keep'));
    await settle(page);
    expect(text('.next-cockpit-direction-question')).toContain(
      'Nothing was settled and no analysis was started: Cargento could not open the whole text of every direction Keep would settle',
    );
    expect(page.allPosts().map((p) => p.path)).toEqual(['/api/direction']);
    first = false;
    await press(control('direction-keep'));
    await settle(page);
    expect(page.allPosts().map((p) => p.path)).toEqual([
      '/api/direction',
      '/api/direction',
      '/api/annotate',
    ]);
  });

  it('names the revision it drew, so words saved since are refused rather than settled over', async () => {
    const page = mountSession({
      store: SAVED,
      session: SAVED_AT,
      routes: {
        '/api/project-context': record(
          fact('f1', 600, 'A much longer direction than its quoted summary shows.'),
        ),
        '/api/direction': () =>
          json({
            ok: true,
            text: 'A much longer direction than its quoted summary shows, whole.',
            clipped: false,
          }),
        '/api/annotate': () => json({ ok: true, outcome: 'refused', persisted: false }),
      },
    });
    await settle(page);
    await press(control('direction-keep'));
    await settle(page);
    await press(control('direction-keep'));
    await settle(page);
    expect(page.allPosts()[1]?.body).toMatchObject({ expected_revision: 1, settle_through: 600 });
    expect(text('.next-cockpit-direction-question')).toContain(
      'Nothing was settled and no analysis was started: your intent changed since this page was drawn, or the store refused the mark.',
    );
    // A refused Keep draws its directions again against the revision now on screen.
    expect(document.querySelector('[data-next-cockpit-direction-whole]')).toBeNull();
    void board;
  });
});

describe('Use this as my goal', () => {
  it('fills the goal box with the direction and asks whether to keep the standing outcome lines', async () => {
    const page = mountSession({
      store: { ...SAVED, lines: ['A standing line'], revision: 2 },
      session: SAVED_AT,
      routes: {
        '/api/project-context': record(...ONE),
        '/api/direction': () =>
          json({
            ok: true,
            goal_choice: { fact_id: 'f1', text: 'Do it the careful way', at: 600, cut: false },
          }),
        '/api/annotate': () => stored(3),
      },
    });
    await settle(page);
    await press(control('direction-goal'));
    await settle(page);
    expect(goalBox().value).toBe('Do it the careful way');
    expect(page.posts()).toBe(1);
    expect(inert(control('held-save'))).toBe(true);
    expect(text('.next-cockpit-held-field[data-next-cockpit-held-field="goal"]')).toContain(
      'Keep your standing outcome lines with this goal?',
    );
    await press(control('direction-lines-clear'));
    expect(lineBoxes().map((b) => b.value)).toEqual(['']);
    expect(inert(control('held-save'))).toBe(false);
  });
});
