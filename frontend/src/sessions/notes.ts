/* Sentences a row or the session page prints more than once, spelt once. Each is the legacy page's own
   wording, because the same fact worded two ways is two promises. */

export const DUPLICATE_LABEL_LIMIT =
  "Same label is not proof of the same directory: the label is the last two segments of each session's path, so sibling worktrees read alike.";

export const UNREAD_SOURCE_NOTE =
  "Cargento opened this session's store and could not read every part of it. What it names is missing here rather than empty; the rest of the row was read normally.";

export const SCAN_ONLY_NOTE =
  'Cargento reads this session off disk and no event from its harness can reach it, so an idle row here means nothing has changed recently rather than that the turn ended. The rest of the row was read normally.';

export const SCAN_ONLY_LINE = 'Read by scanning: no turn end can be observed here';

export const BOARD_WHY =
  'Blocked sessions lead, followed by recorded departures, then working sessions. The Active now figure counts active evidence only; a recorded departure adds no active session.';

export const GOAL_SOURCES_ON =
  'Your first prompt, or your latest where the first is not published, comes from Claude Code or Codex; other harnesses show only your typed words. A goal marked from your prompt was adopted by you; showing a prompt alone adopts nothing, and Drift names a recorded departure.';

export const GOAL_SOURCES_OFF =
  'Annotations are off, so goals cannot be typed and Drift marks are not shown.';

export const RECENT_WHY =
  'Recently observed is not proof the harness process is still open or closed; rows marked ENDED reported their own end.';
