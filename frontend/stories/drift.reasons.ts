import { routeOf, type Harness } from './drift.scenario';

/* Every reason `reading_route.resolve` can give a session, with the route it publishes: the words are the
   producer's own (`reading_route._sentence`, `_clause` and `_route`), because the page prints a route's note
   as it is given. `drift.reasons.test.ts` holds this table to `reading_route.REASONS` and to the stories in
   Drift.stories.tsx, so a reason added to the producer and not here fails a test. */

const GONE = {
  claude: 'the Claude Code CLI was not found on this machine',
  codex: 'the Codex CLI was not found on this machine',
};
const UNQUALIFIED = {
  claude: 'Claude Code checks are not qualified on this build',
  codex: 'Codex checks are not qualified on this build',
};
const NONE = ', so no analysis can run for this session.';
const sentence = (text: string): string => `${text.slice(0, 1).toUpperCase()}${text.slice(1)}`;

export interface ReasonCase {
  readonly harness: Harness;
  readonly provider: string;
  readonly label: string;
  readonly note: string;
  readonly fallback: boolean;
}

export const REASON_CASES: Readonly<Record<string, ReasonCase>> = {
  'own-harness': {
    harness: 'claude',
    provider: 'claude',
    label: 'Claude Code',
    note: "This session's own harness reads it.",
    fallback: false,
  },
  'no-own-producer': {
    harness: 'pi',
    provider: 'codex',
    label: 'Codex',
    note: 'This harness has no reading producer of its own, so Codex reads this session.',
    fallback: false,
  },
  'fallback-not-installed': {
    harness: 'claude',
    provider: 'codex',
    label: 'Codex',
    note: `${sentence(GONE.claude)}, so Codex reads this session.`,
    fallback: true,
  },
  'fallback-not-qualified': {
    harness: 'claude',
    provider: 'codex',
    label: 'Codex',
    note: `${UNQUALIFIED.claude}, so Codex reads this session.`,
    fallback: true,
  },
  'not-installed': {
    harness: 'claude',
    provider: '',
    label: '',
    note: `${sentence(GONE.claude)}, and ${GONE.codex}${NONE}`,
    fallback: false,
  },
  'not-installed-other-not-qualified': {
    harness: 'claude',
    provider: '',
    label: '',
    note: `${sentence(GONE.claude)}, and ${UNQUALIFIED.codex}${NONE}`,
    fallback: false,
  },
  'not-qualified-other-not-installed': {
    harness: 'claude',
    provider: '',
    label: '',
    note: `${UNQUALIFIED.claude}, and ${GONE.codex}${NONE}`,
    fallback: false,
  },
  'not-qualified': {
    harness: 'claude',
    provider: '',
    label: '',
    note: `${UNQUALIFIED.claude}, and ${UNQUALIFIED.codex}${NONE}`,
    fallback: false,
  },
};

export function routeFor(reason: string): Record<string, unknown> {
  const found = REASON_CASES[reason];
  if (!found) throw new Error(`no story fixture for route reason ${reason}`);
  return routeOf(found.harness, { ...found, reason });
}
