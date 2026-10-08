/* The sentences the Intent panel prints more than once, spelt once. Each is the legacy page's own wording,
   because the same fact worded two ways is two promises, and a refusal always names the step that
   resolves it. */

/* The seventh line's refusal, said where the reader meets it: beside the add control, which stays on the
   page and inert at six, and in the polite region when it is pressed anyway. The owner's ruling for a full
   list is to replace or merge a line, so the sentence names both. */
export const LINES_FULL =
  'An expected outcome holds six lines. Replace or merge a line to add another.';

export function directionTooLong(cap: number): string {
  return `A line holds ${String(cap)} characters. Shorten this one to add it.`;
}

export const DIRECTION_CLIPPED =
  'Only the start of this direction is shown; it is longer than Cargento opens.';
export const DIRECTION_UNOPENED =
  'Could not open that direction, so nothing was added. Press again to retry.';

/* Analyze or Keep over an unsaved edit would read words that are not on screen, so the press is refused. Add's
   save has its own sentence, beside its line. */
export const INTENT_EDITED = 'Save your intent, or undo your edit, to analyze drift.';
export const INTENT_SAVING = 'Saving your intent…';
export const INTENT_EDITED_ADD = 'Save your intent, or undo your edit, to add this direction.';
export const INTENT_CHOSEN_SAID = 'Goal filled from your prompt. Not saved.';
export const INTENT_MEASURED = 'Drift is measured against these. Edit anything that is off.';
export const EXCERPT_READ_WHOLE = 'Excerpt. Analyze looks up the source when pressed.';

/* What the last save attempt is still worth saying. `persisted:false` is its own cue and not a success: the
   annotation is then held only in this process, and the next collection reloads the store from disk and
   the words are gone. One sentence per store outcome, chosen from the reply's `outcome` token and not from
   `persisted`, which is one bit for four sentences. */
export const HELD_CUES: Readonly<Record<string, string>> = {
  error: 'Not saved. The server refused the write, and your words are still in the box.',
  unpersisted:
    'Not stored. The store could not be written, so the refresh has already dropped these words, and they are still in the box.',
  saved: 'Saved as a new revision.',
  /* The request was lost, aborted at the bound, or answered with something unreadable: not a refusal, so
     never "Not saved". */
  unconfirmed:
    'Cargento did not answer, so this page cannot tell whether your intent was saved. Your words are still in the box.',
  unchanged: 'Already stored. These words match the saved revision, so no new revision was minted.',
  /* The store exists and the server could not read it, so it wrote nothing: writing would keep only what
     it can read and lose every other session's words. The remedy is the file, not a retry. */
  untrusted:
    'Not saved. Cargento could not read cargento-annotations.json, so nothing was saved and nothing was overwritten, and what you typed is still in the box. Move or repair that file to save again.',
  'settle-untrusted':
    'Not settled. Cargento could not read cargento-annotations.json, so nothing was saved and nothing was overwritten. Move or repair that file to settle again.',
  /* This session's own entry is one this build cannot read: it is kept as it was, never saved over. */
  unreadable:
    "Not saved. This session's words were saved by a build of Cargento that can read more than this one, so nothing was saved over them, and what you typed is still in the box. Save from that build, or remove this session's entry from cargento-annotations.json.",
};

/* The reply's `outcome` token to the cue it earns. An unknown token, from a server newer than this page,
   falls back on `persisted`, which keeps its meaning across builds. */
export const HELD_OUTCOME_CUES: Readonly<Record<string, string>> = {
  stored: 'saved',
  unchanged: 'unchanged',
  refused: 'error',
  unwritable: 'unpersisted',
  untrusted: 'untrusted',
  unreadable: 'unreadable',
};

/* The page's own, unlike the server's discard sentences: no answer came, so the server has said nothing
   about these words. */
export const DISCARD_UNCONFIRMED =
  'Cargento did not answer, so this page cannot tell whether the words were discarded.';

/* How long the armed discard refuses to be confirmed. Above the one second a double-click interval can be
   set to and above a key repeat delay, because both gestures deliver the second press through one listener
   and the replacement button is already under the pointer. A floor and not a disabled interval, because a
   disabled button would move focus and the arm is meant to lapse on its own. */
export const DISCARD_DWELL_MS = 1_200;

export const ADOPT_REFUSED: Readonly<Record<string, string>> = {
  untrusted:
    'Cargento could not read cargento-annotations.json, so your prompt was not saved as the goal and nothing was overwritten. Move or repair that file to save again.',
  unreadable:
    "This session's words were saved by a build of Cargento that can read more than this one, so your prompt was not saved as the goal. Save from that build, or remove this session's entry from cargento-annotations.json.",
};

export const ADOPT_CHANGED =
  'The prompt or saved goal changed, or could not be saved. Review the goal before trying again.';

export const KEEP_ANALYZE = 'Keep my intent and analyze';
export const KEEP = 'Keep my intent';
export const ADD_DIRECTION = 'Add it to my intent';
export const KEEP_NO_ANALYSIS =
  'Kept your intent and settled the direction. No analysis was started.';
/* Keep never grants consent: where none is given it only settles, and the Allow and analyze beside its
   disclosure does the sending. */
export const KEEP_ALLOW =
  'Kept your intent and settled the direction. Press Allow and analyze to send it for a reading.';
export const KEEP_REFUSED =
  'Nothing was settled and no analysis was started: your intent changed since this page was drawn, or the store refused the mark. Review your intent and press again.';
export const KEEP_READ_FIRST =
  'Nothing was settled yet. Each direction Keep settles is now shown whole. Read it, then press again.';
export const KEEP_UNOPENED =
  'Nothing was settled and no analysis was started: Cargento could not open the whole text of every direction Keep would settle, so it cannot show you what you would keep. Press again to retry.';
export const KEEP_UNCONFIRMED =
  'Could not confirm the press. Refresh to check whether your intent was kept before pressing again.';

export const DRIFT_SUBTITLE = 'How far the session has moved from the goal';
export const LIVE_MONITOR = 'Live monitor';
