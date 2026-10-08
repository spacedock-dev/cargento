import { act, fireEvent } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
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

/* The goal and outcome editor, read the way a reader meets it: the words in the boxes, the sentences
   under them, and what a press sends. Every assertion quotes the rendered text, not the data behind it. */

const footerCue = () => text('.next-cockpit-held-footer .next-cockpit-held-cue');

const settle = async (page: { settle: () => Promise<void> }) => {
  await page.settle();
  await page.settle();
};

describe('a goal-less session arrives with its first prompt drafted and nothing sent', () => {
  it('shows the first prompt as an unsaved draft and sends no request on mount, under StrictMode', async () => {
    const page = mountSession();
    await settle(page);
    expect(goalBox().value).toBe('Ship the queue worker');
    expect(text('[data-next-cockpit-draft-marks]')).toBe('from your prompt');
    // The draft is adopted by Save intent, which is live over it; nothing else is.
    expect(inert(control('held-save'))).toBe(false);
    expect(inert(control('held-undo'))).toBe(true);
    expect(page.posts()).toBe(0);
    expect(page.state.requests.filter((r) => r.method !== 'GET').length).toBe(0);
  });

  it('reads nothing it was not asked to: the observed record only, and only as a passive read', async () => {
    const page = mountSession();
    await settle(page);
    const paths = new Set(page.state.requests.map((r) => `${r.method} ${r.path}`));
    expect([...paths].sort()).toEqual(['GET /api/data', 'GET /api/project-context']);
  });
});

describe('typing in the goal box', () => {
  it('counts against the server bound and takes the draft marks away on the first edit', async () => {
    const page = mountSession();
    await settle(page);
    type(goalBox(), 'Ship the queue worker, then verify');
    expect(text('[data-next-cockpit-held-count="goal"]')).toBe('34/240');
    expect(document.querySelector('[data-next-cockpit-draft-marks]')).toBeNull();
    expect(inert(control('held-undo'))).toBe(false);
    expect(page.posts()).toBe(0);
  });

  it('collapses a pasted line break to the one space the store would keep, and cuts at the bound', async () => {
    const page = mountSession();
    await settle(page);
    type(goalBox(), 'one\ntwo');
    expect(goalBox().value).toBe('one two');
    type(goalBox(), 'x'.repeat(300));
    expect(goalBox().value).toHaveLength(240);
    expect(text('[data-next-cockpit-held-count="goal"]')).toBe('240/240');
  });

  it('keeps the words, the caret and the selection across a board refresh that changes nothing they stand on', async () => {
    const page = mountSession();
    await settle(page);
    const box = goalBox();
    type(box, 'my own words');
    box.setSelectionRange(3, 6);
    await page.poll({ ...(page.state.data as object), generated: 1100 });
    expect(goalBox()).toBe(box);
    expect(box.value).toBe('my own words');
    expect([box.selectionStart, box.selectionEnd]).toEqual([3, 6]);
  });

  it('keeps an unsaved draft when the reader leaves the session and comes back', async () => {
    const page = mountSession();
    await settle(page);
    type(goalBox(), 'half a sentence');
    await page.go('#n=sessions');
    await page.go('#n=session:alpha%2Fapp:claude:s1');
    expect(goalBox().value).toBe('half a sentence');
    expect(page.posts()).toBe(0);
  });

  it('puts another tab’s save into an untouched box, and leaves a box the reader is typing in alone', async () => {
    const page = mountSession({ store: { goal: 'Saved elsewhere', revision: 1 } });
    await settle(page);
    expect(goalBox().value).toBe('Saved elsewhere');
    await page.poll({
      ...(page.state.data as object),
      sessions: [
        {
          ...(page.state.data as { sessions: object[] }).sessions[0],
          annotation_goal: 'Saved elsewhere, edited',
          annotation_revision: 2,
        },
      ],
    });
    expect(goalBox().value).toBe('Saved elsewhere, edited');
    type(goalBox(), 'typing now');
    await page.poll({
      ...(page.state.data as object),
      sessions: [
        {
          ...(page.state.data as { sessions: object[] }).sessions[0],
          annotation_goal: 'A third save',
          annotation_revision: 3,
        },
      ],
    });
    expect(goalBox().value).toBe('typing now');
  });
});

describe('Save intent', () => {
  it('sends the typed goal once, with the revision both boxes were drawn against, and says it saved', async () => {
    const page = mountSession({
      routes: {
        '/api/annotate': (request) => {
          page.state.data = await_board(request.body?.['goal'] as string);
          return stored(1);
        },
      },
    });
    function await_board(goal: string) {
      return board({}, { goal, revision: 1, goal_source: '' });
    }
    await settle(page);
    type(goalBox(), 'Land the worker behind a flag');
    await act(async () => {
      fireEvent.click(control('held-save') as Element);
    });
    await settle(page);
    const posts = page.allPosts();
    expect(posts).toHaveLength(1);
    expect(posts[0]?.path).toBe('/api/annotate');
    expect(posts[0]?.body).toEqual({
      harness: 'claude',
      sid: 's1',
      goal: 'Land the worker behind a flag',
      expected_revision: 0,
    });
    expect(footerCue()).toBe('Saved as a new revision.');
    // And once, in the polite region, after the paint that shows it.
    expect(text('#next-cockpit-cue-status')).toBe('Saved as a new revision.');
    expect(goalBox().value).toBe('Land the worker behind a flag');
    expect(inert(control('held-save'))).toBe(true);
  });

  it('sends nothing from an inert control and nothing twice', async () => {
    const page = mountSession({ store: { goal: 'Saved', revision: 1 } });
    await settle(page);
    expect(inert(control('held-save'))).toBe(true);
    await act(async () => {
      fireEvent.click(control('held-save') as Element);
    });
    expect(page.posts()).toBe(0);
    type(goalBox(), 'Edited');
    page.state.routes['/api/annotate'] = () => 'hold';
    await act(async () => {
      fireEvent.click(control('held-save') as Element);
      fireEvent.click(control('held-save') as Element);
    });
    expect(page.posts()).toBe(1);
    await page.release('/api/annotate', stored(2));
  });

  it('keeps the words and says the server refused, when the store refuses the write', async () => {
    const page = mountSession({
      store: { goal: 'Saved', revision: 1 },
      routes: { '/api/annotate': () => json({ ok: true, outcome: 'refused', persisted: false }) },
    });
    await settle(page);
    type(goalBox(), 'Edited words');
    await act(async () => {
      fireEvent.click(control('held-save') as Element);
    });
    await settle(page);
    expect(footerCue()).toBe(
      'Not saved. The server refused the write, and your words are still in the box.',
    );
    expect(goalBox().value).toBe('Edited words');
  });

  it('takes a refusal’s cue away at the next keystroke, which is a fresh attempt on different words', async () => {
    const page = mountSession({
      store: { goal: 'Saved', revision: 1 },
      routes: { '/api/annotate': () => json({ ok: true, outcome: 'refused', persisted: false }) },
    });
    await settle(page);
    type(goalBox(), 'Edited words');
    await act(async () => {
      fireEvent.click(control('held-save') as Element);
    });
    await settle(page);
    expect(footerCue()).toMatch(/^Not saved\./);
    type(goalBox(), 'Edited words again');
    expect(footerCue()).toBe('');
  });

  it('keeps the words and says it cannot tell, when no answer can be read', async () => {
    const page = mountSession({
      store: { goal: 'Saved', revision: 1 },
      routes: { '/api/annotate': () => new Response('<html>', { status: 200 }) },
    });
    await settle(page);
    type(goalBox(), 'Edited words');
    await act(async () => {
      fireEvent.click(control('held-save') as Element);
    });
    await settle(page);
    expect(footerCue()).toBe(
      'Cargento did not answer, so this page cannot tell whether your intent was saved. Your words are still in the box.',
    );
    expect(goalBox().value).toBe('Edited words');
    expect(page.posts()).toBe(1);
  });

  it('says a store that could not be written is not stored, and keeps what was typed', async () => {
    const page = mountSession({
      store: { goal: 'Saved', revision: 1 },
      routes: {
        '/api/annotate': () => json({ ok: true, outcome: 'unwritable', persisted: false }),
      },
    });
    await settle(page);
    type(goalBox(), 'Edited words');
    await act(async () => {
      fireEvent.click(control('held-save') as Element);
    });
    await settle(page);
    expect(footerCue()).toMatch(/^Not stored\./);
    expect(goalBox().value).toBe('Edited words');
  });

  it('drops the draft when the words already match the stored revision, because they are on disk', async () => {
    const page = mountSession({
      store: { goal: 'Same words', revision: 1 },
      routes: {
        '/api/annotate': () =>
          json({ ok: true, outcome: 'unchanged', persisted: true, revision: 1, saved_revision: 1 }),
      },
    });
    await settle(page);
    type(goalBox(), 'Same words ');
    type(goalBox(), 'Same words');
    // Back to the stored words is not an edit: Save is inert and nothing needs sending.
    expect(inert(control('held-save'))).toBe(true);
  });
});

describe('Undo changes', () => {
  it('puts both boxes back and sends nothing', async () => {
    const page = mountSession({
      store: { goal: 'Saved goal', lines: ['A saved line'], revision: 2 },
    });
    await settle(page);
    type(goalBox(), 'edited goal');
    type(lineBoxes()[0] as HTMLTextAreaElement, 'edited line');
    await act(async () => {
      fireEvent.click(control('held-undo') as Element);
    });
    await settle(page);
    expect(goalBox().value).toBe('Saved goal');
    expect(lineBoxes().map((box) => box.value)).toEqual(['A saved line']);
    expect(page.posts()).toBe(0);
    expect(inert(control('held-undo'))).toBe(true);
  });

  it('is Escape in the goal box, and Escape in a line puts the whole list back', async () => {
    const page = mountSession({
      store: { goal: 'Saved goal', lines: ['One', 'Two'], revision: 2 },
    });
    await settle(page);
    type(goalBox(), 'edited goal');
    fireEvent.keyDown(goalBox(), { key: 'Escape' });
    await settle(page);
    expect(goalBox().value).toBe('Saved goal');
    await act(async () => {
      fireEvent.click(control('held-line-add') as Element);
    });
    expect(lineBoxes()).toHaveLength(3);
    fireEvent.keyDown(lineBoxes()[0] as HTMLTextAreaElement, { key: 'Escape' });
    await settle(page);
    expect(lineBoxes().map((box) => box.value)).toEqual(['One', 'Two']);
  });
});
