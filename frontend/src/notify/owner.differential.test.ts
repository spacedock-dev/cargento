import { describe, expect, it } from 'vitest';
import { mulberry32, pick, type Rng } from '../observed/generate.test.helper';
import { loadLegacyNotify } from './legacy.test.helper';
import { createNotifyOwner, type NotifyHost } from './owner';

/* The notification owner is held to the legacy file that decides when a banner is raised. Both run the
   same long sequence of boards, permissions, clocks and leader states in lockstep, and after every step
   they must agree on every banner raised (title, body and tag, in order), on every lane report posted and
   on the control the header would draw. The sequences are built to meet the cases that cost most when
   wrong: a gate that arrives on the first board, a session that falls quiet twice inside the repeat
   window, a question that arrives with the session that asks it, a native lane that owns the banner, a
   permission that is revoked mid-tab, a stage condition that is repeated, and a lane report the server
   refuses. A Notification here is a scripted object: nothing creates a native notification. */

const HARNESSES = [
  { key: 'claude', label: 'Claude' },
  { key: 'codex', label: '' },
  { key: 'pi' },
] as const;
const PROJECTS = ['alpha/app', 'beta/api', 'ünï/çødé', '<b>x</b>'] as const;
const STATES = ['working', 'idle', 'needs_input', 'working', 'idle', 'bogus'] as const;

interface Step {
  readonly payload: Record<string, unknown>;
  readonly now: number;
  readonly permission: string | null;
  readonly supported: boolean;
  readonly leader: boolean;
  readonly throwing: boolean;
  readonly laneAnswer: boolean | null;
}

function buildSequence(seed: number): Step[] {
  const rnd: Rng = mulberry32(seed);
  const steps: Step[] = [];
  let now = 1_000_000;
  let permission: string | null = pick(rnd, ['default', 'granted', 'granted', 'denied']);
  let generated = 1000;
  for (let index = 0; index < 14; index += 1) {
    now += pick(rnd, [0, 1000, 100_000, 599_000, 599_999, 600_000, 601_000]);
    generated += pick(rnd, [0, 1, 20, 20]);
    if (rnd() < 0.15) permission = pick(rnd, ['default', 'granted', 'denied', null]);
    const sessions = [0, 1, 2, 3].flatMap((slot) => {
      if (rnd() < 0.2) return [];
      const state = pick(rnd, STATES);
      const harness = HARNESSES[slot % 3] as (typeof HARNESSES)[number];
      return [
        {
          harness: harness.key,
          sid: `s${String(slot)}`,
          project: pick(rnd, PROJECTS),
          state,
          state_detail: pick(rnd, ['', 'open question', 'generating', 'Ünï']),
          active: pick(rnd, [true, true, false]),
        },
      ];
    });
    const asks = [0, 1, 2].flatMap((slot) =>
      rnd() < 0.5
        ? []
        : [
            {
              id: pick(rnd, [`a${String(slot)}`, `a${String(slot)}`, '', `b${String(index)}`]),
              harness: (HARNESSES[slot % 3] as (typeof HARNESSES)[number]).key,
              project: pick(rnd, [...PROJECTS, '']),
              question: pick(rnd, ['Approve?', 'Ship it?', 'Ünï?']),
            },
          ],
    );
    const payload: Record<string, unknown> = {
      generated,
      sessions,
      harnesses: HARNESSES.map((harness) => ({ ...harness })),
      ask: pick(rnd, [true, true, false]),
      asks,
      native_notify: pick(rnd, ['', '', '', 'osascript']),
    };
    if (rnd() < 0.6) payload['browser_lane'] = pick(rnd, [true, false]);
    if (rnd() < 0.5) {
      payload['tripwires'] = {
        enabled: pick(rnd, [true, true, false]),
        rules: [0, 1].flatMap(() =>
          rnd() < 0.5
            ? []
            : [
                {
                  event_id: pick(rnd, ['stage:1', 'stage:2', 'stage:3', '']),
                  workflow: pick(rnd, ['flow', 'Ünï flow']),
                  why: 'Observed task change.',
                },
              ],
        ),
      };
    }
    steps.push({
      payload,
      now,
      permission,
      supported: rnd() > 0.05,
      leader: pick(rnd, [true, false]),
      throwing: rnd() < 0.15,
      laneAnswer: pick(rnd, [true, true, false, null]),
    });
  }
  return steps;
}

function mine() {
  const state = {
    permission: 'default' as string | null,
    supported: true,
    now: 0,
    leader: false,
    throwing: false,
    laneAnswer: true as boolean | null,
  };
  const banners: { title: string; body: string; tag: string }[] = [];
  let lanePosts = 0;
  const host: NotifyHost = {
    supported: () => state.supported,
    permission: () => (state.supported ? state.permission || 'default' : 'unsupported'),
    request: () => undefined,
    create(title, options) {
      if (state.throwing) throw new Error('permission revoked');
      banners.push({ title, body: options.body, tag: options.tag });
    },
  };
  const owner = createNotifyOwner({
    host,
    now: () => state.now,
    postLane: () => {
      lanePosts += 1;
      return state.laneAnswer === null
        ? Promise.reject(new Error('offline'))
        : Promise.resolve(state.laneAnswer);
    },
    isLeader: () => state.leader,
  });
  return { state, banners, owner, lanePosts: () => lanePosts };
}

const SEEDS = Number(process.env['NOTIFY_SEEDS'] ?? 300);

describe('the notification owner raises what the legacy module raises', () => {
  it(`agrees step by step over ${String(SEEDS)} generated sequences`, async () => {
    const failures: string[] = [];
    let raised = 0;
    let quietSuppressed = 0;
    let stage = 0;
    let lane = 0;
    for (let seed = 1; seed <= SEEDS && failures.length < 3; seed += 1) {
      const legacy = loadLegacyNotify();
      const port = mine();
      for (const [index, step] of buildSequence(seed).entries()) {
        legacy.setNow(step.now);
        legacy.setPermission(step.permission);
        legacy.setSupported(step.supported);
        legacy.setLeader(step.leader);
        legacy.setThrowing(step.throwing);
        legacy.setLaneAnswer(step.laneAnswer);
        port.state.now = step.now;
        port.state.permission = step.permission;
        port.state.supported = step.supported;
        port.state.leader = step.leader;
        port.state.throwing = step.throwing;
        port.state.laneAnswer = step.laneAnswer;
        legacy.sync(step.payload);
        port.owner.sync(step.payload);
        // The lane report resolves on promise turns, which the next step must see settled on both sides.
        await legacy.settle();
        await Promise.resolve();
        await Promise.resolve();
        await Promise.resolve();
        const label = `seed ${String(seed)} step ${String(index)}`;
        if (JSON.stringify(legacy.banners) !== JSON.stringify(port.banners)) {
          failures.push(
            `${label}: banners ${JSON.stringify(legacy.banners.slice(-2))} != ${JSON.stringify(port.banners.slice(-2))}`,
          );
          break;
        }
        if (legacy.lanePosts.length !== port.lanePosts()) {
          failures.push(
            `${label}: lane posts ${String(legacy.lanePosts.length)} != ${String(port.lanePosts())}`,
          );
          break;
        }
        const old = legacy.control(step.payload);
        const control = port.owner.control(step.payload);
        const word = old.includes('data-next-action="enable-notifications"')
          ? 'enable'
          : old.includes('notifications blocked')
            ? 'blocked'
            : null;
        if (word !== control) {
          failures.push(`${label}: control ${String(word)} != ${String(control)}`);
          break;
        }
      }
      raised += legacy.banners.length;
      stage += legacy.banners.filter(
        (banner) => banner.title === 'Workflow stage condition',
      ).length;
      quietSuppressed += legacy.banners.filter((banner) =>
        banner.title.endsWith('has gone quiet'),
      ).length;
      lane += legacy.lanePosts.length;
    }
    expect(failures).toEqual([]);
    // Agreement over silence would prove nothing: the sequences must have raised and reported.
    expect(raised).toBeGreaterThan(200);
    expect(stage).toBeGreaterThan(0);
    expect(quietSuppressed).toBeGreaterThan(0);
    expect(lane).toBeGreaterThan(0);
  }, 120_000);
});
