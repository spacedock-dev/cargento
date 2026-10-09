import { legacyHarness } from '../../test/legacy_goldens';

/* What the removed page said, for the notification module, as the differential tests ask for it. The
   answers are recorded in `frontend/test/golden/vitest`; see `frontend/test/legacy_goldens.ts`. The
   recording ran against a scripted `Notification` that only noted what it was asked to raise. */

export interface RaisedBanner {
  readonly title: string;
  readonly body: string;
  readonly tag: string;
}

export interface LegacyNotify {
  readonly banners: RaisedBanner[];
  readonly lanePosts: { readonly body: string }[];
  setPermission(value: string | null): void;
  /** Whether `Notification` exists in the page at all. */
  setSupported(value: boolean): void;
  setNow(ms: number): void;
  setLeader(value: boolean): void;
  /** Makes the next constructions throw, as a revoked permission does. */
  setThrowing(value: boolean): void;
  /** What the lane report answers: true is a 2xx, false a refusal, null a network failure. */
  setLaneAnswer(value: boolean | null): void;
  sync(payload: unknown): void;
  control(payload: unknown): string;
  request(): void;
  /** Lets the promise chains the legacy report and request use run to completion. */
  settle(): Promise<void>;
}

export function loadLegacyNotify(): LegacyNotify {
  return legacyHarness('notify', {
    slots: {
      setPermission: 'permission',
      setSupported: 'supported',
      setNow: 'now',
      setLeader: 'leader',
      setThrowing: 'throwing',
      setLaneAnswer: 'laneAnswer',
    },
    observe: ['control'],
    props: ['banners', 'lanePosts'],
    async: ['settle'],
  });
}
