import { nextFiniteNumber } from '../api/bootstrap';
import type { ObservedSession } from '../observed';
import { durationSince, isRecord, sessionKey, type Row } from '../observed/values';
import { type Row as RawRow } from './raw';

/* What a project's sessions are doing, as the Projects list and the Now tab draw it: which members a row
   names, how far the tasks have got, what finished, and the subagent pills on a running card. Ported from
   `next-projects.js` and `next-activity.js`. Every count is derived from the collection its rows are drawn
   from, never authored. */

/** The member lines an Active project row renders, past which one count line names what is left. */
export const MEMBER_CAP = 5;

/* Blocked on you, then working, then any member carrying a risk, then quiet by most recent activity, then
   everything else, then ended. Blocked, working and risky members render even past the cap, because hiding
   one would bury what the row exists to show and what turned its rail colour; the rest fill up to the cap. */
export function projectMembers(
  sessions: readonly ObservedSession[],
  risky: readonly ObservedSession[] = [],
): { readonly shown: readonly ObservedSession[]; readonly hidden: number } {
  const risks = new Set(risky.map((session) => sessionKey(session as unknown as Row)));
  const rank = (session: ObservedSession): number =>
    session.isNeeds || session.askKnown
      ? 0
      : session.isWorking
        ? 1
        : risks.has(sessionKey(session as unknown as Row))
          ? 1.5
          : session.isEnded
            ? 4
            : session.isQuiet
              ? 2
              : 3;
  const ordered = sessions
    .map((session, index) => ({ session, index }))
    .sort(
      (a, b) =>
        rank(a.session) - rank(b.session) ||
        (rank(a.session) >= 2
          ? (b.session.lastActivityAt || 0) - (a.session.lastActivityAt || 0)
          : 0) ||
        a.index - b.index,
    )
    .map((row) => row.session);
  const pinned = ordered.filter((session) => rank(session) < 2);
  const rest = ordered.filter((session) => rank(session) >= 2);
  const shown = [...pinned, ...rest.slice(0, Math.max(0, MEMBER_CAP - pinned.length))];
  return { shown, hidden: ordered.length - shown.length };
}

/* The tasks done of the tasks published, across the project's raw rows. Null when none published a total:
   a progress bar with nothing to measure would read as zero done of zero, which is not a claim anyone made. */
export function projectProgress(
  sessions: readonly RawRow[],
): { readonly done: number; readonly total: number } | null {
  const total = sessions.reduce(
    (sum, session) => sum + Math.max(0, nextFiniteNumber(session['total'])),
    0,
  );
  if (total <= 0) return null;
  const done = sessions.reduce(
    (sum, session) => sum + Math.max(0, nextFiniteNumber(session['done'])),
    0,
  );
  return { done, total };
}

/** The bar's own value: done, never past the total. */
export function progressValue(progress: { readonly done: number; readonly total: number }): number {
  return Math.min(progress.done, progress.total);
}

/** The completed tasks the observed sessions published, in session then task order. No harness allowlist: the field is read as published. */
export function completedTasks(sessions: readonly { readonly tasks?: unknown }[]): RawRow[] {
  const completed: RawRow[] = [];
  for (const session of sessions) {
    const tasks: unknown[] = Array.isArray(session.tasks) ? session.tasks : [];
    for (const task of tasks) {
      if (isRecord(task) && task['status'] === 'completed') completed.push(task);
    }
  }
  return completed;
}

/** At most this many subagent pills on a running card. */
export const SUBAGENT_LIMIT = 6;

/** Only an explicit `active: false` withholds the live mark: none means the collector does not measure it. */
export function subagentIsLive(subagent: unknown): boolean {
  return !subagent || (subagent as { active?: unknown }).active !== false;
}

export interface SubagentPill {
  readonly index: number;
  readonly name: string;
  readonly elapsed: string;
  readonly live: boolean;
}

/* The crew that is moving reads first: a lead with a finished teammate and six live lenses would otherwise
   spend the six-pill budget on work that has stopped. Order within each group is the order the collector
   published, which is mtime order only for the lead's own agents. */
export function activitySubagents(
  session: Pick<ObservedSession, 'subagents'>,
  generated: number | null,
): { readonly pills: readonly SubagentPill[]; readonly remaining: number } | null {
  const subagents = Array.isArray(session.subagents) ? session.subagents : [];
  if (!subagents.length) return null;
  const ordered = [
    ...subagents.filter((subagent) => subagentIsLive(subagent)),
    ...subagents.filter((subagent) => !subagentIsLive(subagent)),
  ];
  const pills = ordered.slice(0, SUBAGENT_LIMIT).map((subagent, index) => ({
    index,
    name: String((isRecord(subagent) && subagent['name']) || 'subagent'),
    elapsed:
      durationSince(generated, isRecord(subagent) ? subagent['started_at'] : undefined) ?? '',
    live: subagentIsLive(subagent),
  }));
  return { pills, remaining: subagents.length - SUBAGENT_LIMIT };
}

/* A line that repeats the title says nothing the title did not. The one case beyond equality: line 1 clips
   at 80 characters and line 2 at 140, so one prompt reaches them as two strings and the shorter ends in an
   ellipsis. Deliberately not a plain prefix test: a short generated title that happens to open a longer,
   genuinely newer instruction is not a duplicate, and suppressing it would lose the line. */
export function instructionEchoes(instruction: string, title: string): boolean {
  const norm = (value: unknown) =>
    String(value == null ? '' : value)
      .trim()
      .toLowerCase();
  const line = norm(instruction);
  const head = norm(title);
  if (!line || !head) return false;
  if (line === head) return true;
  return head.endsWith('…') && line.startsWith(head.slice(0, -1));
}
