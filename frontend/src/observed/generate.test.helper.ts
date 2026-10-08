/* Deterministic payloads for the differential tests: the shapes a real board publishes, and the shapes
   a hostile or older one could. Built from a seed so a failing case is reproducible by number. Every
   value is JSON-representable, because a payload arrives through `JSON.parse` and nothing else.

   The generator leans on the cases the migration brief names (duplicate project labels, the same sid
   under two harnesses, a sid with colons, a missing harness, an ended session with no end time, a
   source gap, unicode, absent fields) and on the one that costs most when wrong: a field that is
   present with the wrong type. */
export type Rng = () => number;

export function mulberry32(seed: number): Rng {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export const pick = <T>(rnd: Rng, items: readonly T[]): T => items[Math.floor(rnd() * items.length)] as T;
const chance = (rnd: Rng, p: number): boolean => rnd() < p;
const int = (rnd: Rng, low: number, high: number): number => low + Math.floor(rnd() * (high - low + 1));

const HARNESSES = ['claude', 'codex', 'cursor', 'pi', 'gemini', 'ghost', ''] as const;
const PROJECTS = ['alpha/app', 'beta/api', '', '  ', 'alpha/app ', 'ünï/çødé', 'a:b', '<b>x</b>', 'gamma'] as const;
const SIDS = ['s1', 's2', 'shared', 'colon:sid', 'a:b:c', '', 'ünï', 'x y', '0', 'long-' + 'z'.repeat(40)] as const;
const STATES = ['working', 'idle', 'needs_input', 'working', 'idle', 'bogus', '', null, 7] as const;
const TITLES = ['Fix the build', '  padded  ', '', null, 'Ünï ✓', '<script>x</script>', 'Title with "quotes" & <tags>'] as const;
const STAMPS = [0, -5, 1, 999000, 999940, 1000, 1000.5, 1200, null, 'soon', '1000'] as const;

function maybe<T>(rnd: Rng, p: number, make: () => T): T | undefined {
  return chance(rnd, p) ? make() : undefined;
}

function genTasks(rnd: Rng): unknown {
  const count = int(rnd, 0, 4);
  const tasks: unknown[] = [];
  for (let index = 0; index < count; index += 1) {
    tasks.push(
      chance(rnd, 0.1)
        ? pick(rnd, ['text', 3, null, [1]])
        : {
            id: String(index),
            subject: pick(rnd, ['Write tests', '  ', '', 'Ship it', 5, null, 'Ünï task']),
            status: pick(rnd, ['in_progress', 'pending', 'completed', 'weird', '']),
          },
    );
  }
  return chance(rnd, 0.1) ? pick(rnd, ['tasks', 4, {}]) : tasks;
}

function genSubagents(rnd: Rng): unknown {
  const count = int(rnd, 0, 3);
  const out: unknown[] = [];
  for (let index = 0; index < count; index += 1) {
    out.push(
      chance(rnd, 0.1)
        ? null
        : {
            name: pick(rnd, ['helper', '', 'Ünï', undefined]),
            active: pick(rnd, [true, false, undefined]),
            parent: pick(rnd, [undefined, 'lead', '']),
            started_at: pick(rnd, STAMPS),
          },
    );
  }
  return chance(rnd, 0.08) ? pick(rnd, ['x', 2, {}]) : out;
}

function genInstruction(rnd: Rng): unknown {
  if (chance(rnd, 0.3)) return undefined;
  if (chance(rnd, 0.1)) return pick(rnd, ['text', 4, [1]]);
  return {
    label: pick(rnd, ['asked', 'agent', 'earlier', 'other', '']),
    text: pick(rnd, ['Ship the retry queue', '  ', '', 'Ünï words', null, 12]),
    at: pick(rnd, STAMPS),
  };
}

function genSession(rnd: Rng, index: number, wellFormed = false): Record<string, unknown> {
  const row: Record<string, unknown> = {};
  const harness = pick(rnd, HARNESSES);
  if (!chance(rnd, 0.06)) row['harness'] = harness;
  /* A sid of 0 is falsy to the legacy key and a published one to the model, which the model-level
     differential carries and the view-level one cannot: the legacy view throws on it. */
  if (!chance(rnd, 0.05)) row['sid'] = chance(rnd, 0.1) ? index + (wellFormed ? 1 : 0) : pick(rnd, SIDS);
  row['session'] = 's' + String(index);
  if (!chance(rnd, 0.06)) row['project'] = pick(rnd, PROJECTS);
  const state = pick(rnd, STATES);
  if (state !== null) row['state'] = state;
  const optional: [string, unknown | undefined][] = [
    ['title', maybe(rnd, 0.85, () => pick(rnd, TITLES))],
    ['last_prompt', maybe(rnd, 0.4, () => pick(rnd, ['Last prompt', '', '  ', 'Ünï prompt', 9]))],
    ['state_detail', maybe(rnd, 0.6, () => pick(rnd, ['generating', 'awaiting your message', '', '  ', 'Ünï']))],
    ['active', maybe(rnd, 0.6, () => pick(rnd, [true, false, 'yes', 1]))],
    ['focusable', maybe(rnd, 0.3, () => pick(rnd, [true, false, 'true', null, 1]))],
    ['resume_id', maybe(rnd, 0.3, () => pick(rnd, ['abc-123', '-bad', '', null, 'x'.repeat(80), 'ok_id']))],
    ['last_activity', maybe(rnd, 0.9, () => pick(rnd, STAMPS))],
    ['started_at', maybe(rnd, 0.5, () => pick(rnd, STAMPS))],
    ['ended_at', maybe(rnd, 0.3, () => pick(rnd, STAMPS))],
    ['finished_at', maybe(rnd, 0.3, () => pick(rnd, STAMPS))],
    ['turn_end_at', maybe(rnd, 0.2, () => pick(rnd, STAMPS))],
    ['blocked_since', maybe(rnd, 0.3, () => pick(rnd, STAMPS))],
    ['wait_unconfirmed', maybe(rnd, 0.2, () => pick(rnd, [true, false, 1]))],
    ['acquisition', maybe(rnd, 0.3, () => pick(rnd, ['scan-only', 'event', 'hook', '', null, 1]))],
    ['source_gaps', maybe(rnd, 0.35, () => pick(rnd, [['block state'], ['token accounting', 'x'], [], [1, ' a ', ''], 'gap', null, ['block state', 'token accounting']]))],
    ['dirty', maybe(rnd, 0.4, () => pick(rnd, [true, false, null, 'dirty', 0]))],
    ['changed', maybe(rnd, 0.3, () => pick(rnd, [0, 1, 4, -1, 2.5, null, '3']))],
    ['rate_per_min', maybe(rnd, 0.4, () => pick(rnd, [0, 1234.5, -3, null, 'fast', 88000]))],
    ['turn', maybe(rnd, 0.4, () => pick(rnd, [{ elapsed_h: '3m', eta_h: '2m', long: false }, { elapsed_h: '1h', long: true }, {}, null, 'x', [1]]))],
    ['loop', maybe(rnd, 0.3, () => pick(rnd, [{ errors: 3, failures: 5, tool: 'mcp__claude_ai_Slack__send_message', barren: false }, { errors: 0 }, { errors: 2, failures: 2, barren: true }, { errors: 1.5 }, null, 'loop']))],
    ['tasks', maybe(rnd, 0.6, () => genTasks(rnd))],
    ['subagents', maybe(rnd, 0.5, () => genSubagents(rnd))],
    ['subagents_omitted', maybe(rnd, 0.2, () => pick(rnd, [0, 2, -1, 'x', null]))],
    ['instruction', genInstruction(rnd)],
    ['copied_prompts', maybe(rnd, 0.2, () => pick(rnd, [[{ quoted_as: ['instruction'] }], [{ quoted_as: ['first_prompt'] }], [], [null], 'x']))],
    ['spacedock', maybe(rnd, 0.25, () => pick(rnd, [{ workflows: [{ goal: 'Ship the workflow' }, { goal: '  ' }, { goal: 'Second' }] }, { workflows: 'x' }, {}, null, []]))],
    ['delegated_launches', maybe(rnd, 0.35, () => pick(rnd, [0, 1, 3, null, 'x', -1, 1.5]))],
    ['delegated_unpaired', maybe(rnd, 0.35, () => pick(rnd, [0, 1, 2, null, 'x', -1]))],
    ['delegated_latest_launch_at', maybe(rnd, 0.3, () => pick(rnd, STAMPS))],
    ['delegated_last_activity_at', maybe(rnd, 0.3, () => pick(rnd, STAMPS))],
    ['delegated_quiet_since', maybe(rnd, 0.3, () => pick(rnd, [0, 100, 990000, 998000, 999900, 5000000, null, 'x']))],
    ['delegated_visibility', maybe(rnd, 0.3, () => pick(rnd, ['complete', 'partial', 'unattributed', 'not-recorded', '', null, 'other']))],
    ['annotation_goal', maybe(rnd, 0.3, () => pick(rnd, ['Ship the queue', '  ', '', null, 5]))],
    ['annotation_goal_source', maybe(rnd, 0.2, () => pick(rnd, ['latest-prompt', 'first-prompt', 'chosen-prompt', 'typed', '']))],
    ['annotation_revision', maybe(rnd, 0.3, () => pick(rnd, [1, 2, 5, null, 'x']))],
    ['annotation_assessment', maybe(rnd, 0.25, () => pick(rnd, [null, '', { criteria: { 'a constraint': { result: 'departure', cites: ['c1'] } }, read_at: 999000, revision_read: 1 }, { criteria: { claims: { result: 'departure', cites: ['c'] } } }, { bogus: 1 }, { criteria: {} }, []]))],
    ['annotation_reading_count', maybe(rnd, 0.2, () => pick(rnd, [0, 2, 'x', null]))],
    ['departure_checked', maybe(rnd, 0.2, () => pick(rnd, [true, false, 'yes']))],
    /* A null row in `departures` throws in the legacy view, so only the model-level run carries one. */
    ['departures', maybe(rnd, 0.25, () => pick(rnd, [[{ at: 999900, revision: 2, constraint: 'c', reading: 'r', cutoff: 999800, evidence: 'e', follow_up: 'later', clause: 'the clause' }], [{ at: 0, revision: 1 }], [{ at: 999000 }, { at: 'x', revision: 5, cutoff_text: 'noted' }], [], wellFormed ? [{}] : [null, 3], 'x']))],
    ['departure_why', maybe(rnd, 0.2, () => pick(rnd, ['A cap was spent', '', null, 4]))],
    ['delivery_raises', maybe(rnd, 0.3, () => pick(rnd, [0, 1, 3, 'x', null]))],
    ['delivery_outcome', maybe(rnd, 0.3, () => pick(rnd, ['refused', 'handed-over', 'no-lane', '']))],
    ['delivery_why', maybe(rnd, 0.3, () => pick(rnd, ['It was refused', '', null]))],
    ['delivery_mixed', maybe(rnd, 0.2, () => pick(rnd, [true, false]))],
    ['delivery_mixed_why', maybe(rnd, 0.2, () => pick(rnd, ['Earlier ones differed', '']))],
    ['delivery_binding_why', maybe(rnd, 0.2, () => pick(rnd, ['Bound to a tab', '']))],
    ['browser_lane_why', maybe(rnd, 0.2, () => pick(rnd, ['Lane sentence', '']))],
    ['delivery_departure', maybe(rnd, 0.3, () => pick(rnd, [{ delivery_raises: 0, delivery_none_why: 'Nothing was raised' }, { delivery_raises: 2 }, null, 'x', {}]))],
    ['command_reports', maybe(rnd, 0.3, () => pick(rnd, [[{ label: 'rm -rf', tool_name: 'Bash', timestamp: 1700000000 }, { label: 'x', tool_name: 'Edit', timestamp: 1700000100 }], [], [{ label: 'y', tool_name: 'Bash', timestamp: wellFormed ? 1700000200 : 'x' }], 'x', null]))],
    ['first_prompt', maybe(rnd, 0.3, () => pick(rnd, ['/compact', 'Do the thing', '', null]))],
    ['first_prompt_at', maybe(rnd, 0.3, () => pick(rnd, STAMPS))],
    ['first_prompt_control', maybe(rnd, 0.2, () => pick(rnd, [true, false, 'x']))],
    ['prompt_states_work', maybe(rnd, 0.3, () => pick(rnd, [true, false]))],
    ['prompt_at', maybe(rnd, 0.3, () => pick(rnd, STAMPS))],
    ['session_output_tokens', maybe(rnd, 0.3, () => pick(rnd, [0, 999, 1000, 12345, null, 'x', -2]))],
    ['turn_output_tokens', maybe(rnd, 0.3, () => pick(rnd, [0, 500, 20500, null, 'x']))],
  ];
  for (const [key, value] of optional) if (value !== undefined) row[key] = value;
  return row;
}

function genAsks(rnd: Rng, sessions: readonly Record<string, unknown>[]): unknown[] {
  const count = int(rnd, 1, 5);
  const asks: unknown[] = [];
  for (let index = 0; index < count; index += 1) {
    const owner = sessions.length && chance(rnd, 0.8) ? (pick(rnd, sessions) as Record<string, unknown>) : null;
    asks.push(
      chance(rnd, 0.06)
        ? pick(rnd, [null, 'ask', 4])
        : {
            id: pick(rnd, ['a' + String(index), 'a' + String(index), '', 'ask:with:colons']),
            harness: owner && chance(rnd, 0.8) ? owner['harness'] : pick(rnd, HARNESSES),
            session_id: owner && chance(rnd, 0.85) ? owner['sid'] : pick(rnd, SIDS),
            project: owner ? owner['project'] : 'p',
            question: pick(rnd, ['Approve the plan?', '  ', '', null, 'Ünï question?', 'Line one\nLine two', 12]),
            options: pick(rnd, [['Yes', 'No'], [], ['Only'], undefined, 'Yes', ['A', 3, null]]),
            age_sec: pick(rnd, [0, 5, 90, 4000, -1, null, 'x']),
          },
    );
  }
  return asks;
}

function genHarnesses(rnd: Rng): unknown {
  if (chance(rnd, 0.1)) return pick(rnd, [undefined, 'x', {}, null]);
  const out: unknown[] = [];
  for (const key of HARNESSES) {
    if (chance(rnd, 0.3)) continue;
    out.push(
      chance(rnd, 0.08)
        ? null
        : {
            key,
            label: pick(rnd, [key.toUpperCase(), '', '  ', undefined, 5]),
            discovered: pick(rnd, [true, false, undefined]),
            error: chance(rnd, 0.15) ? 'could not read' : undefined,
            reports_needs_input: pick(rnd, [true, false, undefined, 'yes']),
            reports_needs_input_when: pick(rnd, [undefined, 'on prompt', '']),
            reports_rate: pick(rnd, [true, false, undefined]),
            reports_turn_bounds: pick(rnd, [true, false, undefined]),
          },
    );
  }
  return out;
}

function genUsage(rnd: Rng): unknown {
  if (chance(rnd, 0.5)) return pick(rnd, [undefined, [], 'x', null]);
  const entries: unknown[] = [];
  const count = int(rnd, 1, 2);
  for (let index = 0; index < count; index += 1) {
    const window = () =>
      maybe(rnd, 0.7, () => ({
        pct: pick(rnd, [0, 5, 40, 70, 100, 120, 5.5, 'x', null]),
        windowSec: pick(rnd, [18000, 604800, 0, null, 'x']),
        resetAt: pick(rnd, [1000 + 3000, 1000 + 40000, 900, null]),
        recent: pick(rnd, [undefined, { pctPerMin: 0.5, spanSec: 600, samples: 4 }, { pctPerMin: 0, spanSec: 600, samples: 2 }, { pctPerMin: 1, spanSec: 0, samples: 1 }, 'x']),
      }));
    entries.push(
      chance(rnd, 0.1)
        ? null
        : {
            harness: pick(rnd, ['claude', 'codex', '', undefined]),
            state: pick(rnd, ['ok', 'ok', 'ok', 'error']),
            fiveH: window(),
            week: window(),
            month: window(),
            models: pick(rnd, [undefined, [{ label: 'Opus', pct: 42 }, { label: '', pct: 1 }, { label: 'X', pct: 'x' }], 'x']),
          },
    );
  }
  return entries;
}

export interface GenOptions {
  /** Only records in `sessions`, and `sessions` always a list: the shape the legacy VIEW functions can hold without throwing. */
  readonly wellFormed?: boolean;
}

export function genPayload(seed: number, options: GenOptions = {}): Record<string, unknown> {
  const rnd = mulberry32(seed);
  const payload: Record<string, unknown> = {};
  if (!chance(rnd, 0.05)) payload['generated'] = pick(rnd, [1000, 1000, 1000, 999950, 0, null, 'x']);
  const sessionCount = chance(rnd, 0.1) ? 0 : int(rnd, 1, 9);
  const sessions: Record<string, unknown>[] = [];
  for (let index = 0; index < sessionCount; index += 1) {
    const row = genSession(rnd, index, options.wellFormed === true);
    sessions.push(row);
    // The cases the brief names, forced often enough that a seed range always meets them.
    if (chance(rnd, 0.15)) sessions.push({ ...genSession(rnd, index + 100, options.wellFormed === true), harness: pick(rnd, ['claude', 'codex']), sid: row['sid'] ?? 'dup', project: row['project'] });
    if (chance(rnd, 0.08)) sessions.push({ ...row });
  }
  const garbage = options.wellFormed !== true;
  if (!garbage || !chance(rnd, 0.04)) payload['sessions'] = garbage && chance(rnd, 0.04) ? pick(rnd, ['sessions', {}, null]) : sessions;
  if (garbage && chance(rnd, 0.1)) (payload['sessions'] as unknown[] | undefined)?.push?.(pick(rnd, [null, 'row', 7, ['x']]));
  const flags: [string, unknown][] = [
    ['ask', pick(rnd, [true, true, true, true, false, undefined, 'yes'])],
    ['annotate', pick(rnd, [true, false, undefined])],
    ['annotate_unreadable', pick(rnd, [undefined, '', 'store unreadable'])],
    ['ends_observable', pick(rnd, [true, false, undefined])],
    ['window_hours', pick(rnd, [24, 1, 0, undefined, 'x'])],
    ['harnesses', genHarnesses(rnd)],
    ['usage', genUsage(rnd)],
    ['irreversible_enabled', pick(rnd, [true, true, false, undefined])],
  ];
  for (const [key, value] of flags) if (value !== undefined) payload[key] = value;
  if (chance(rnd, 0.8)) payload['asks'] = genAsks(rnd, sessions);
  return JSON.parse(JSON.stringify(payload)) as Record<string, unknown>;
}
