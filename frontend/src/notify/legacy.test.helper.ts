import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import vm from 'node:vm';

/* The legacy page's notification module, run as the page runs it, for the differential tests. The legacy
   source is the oracle: the page stays the rollback while this one is built. Only the browser objects the
   file touches are stubbed, and the Notification API is a SCRIPTED one that records what it was asked to
   raise: nothing here can create a native notification. Vitest runs from the repository root. */
const WEB = 'cargento/skills/cargento/cargento_runtime/web';

function read(file: string): string {
  return readFileSync(resolve(process.cwd(), WEB, file), 'utf8');
}

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
  const banners: RaisedBanner[] = [];
  const lanePosts: { body: string }[] = [];
  let now = 0;
  let permission: string | null = 'default';
  let supported = true;
  let throwing = false;
  let laneAnswer: boolean | null = true;

  class FakeDate extends Date {
    static override now(): number {
      return now;
    }
  }
  function FakeNotification(this: unknown, title: string, options: { body: string; tag: string }) {
    if (throwing) throw new Error('permission revoked');
    banners.push({ title, body: options.body, tag: options.tag });
  }
  Object.defineProperty(FakeNotification, 'permission', { get: () => permission });
  (FakeNotification as unknown as Record<string, unknown>)['requestPermission'] = (
    done?: () => void,
  ) => {
    permission = 'granted';
    done?.();
    return Promise.resolve('granted');
  };

  const sandbox: Record<string, unknown> = {
    location: { href: 'http://127.0.0.1:4581/', search: '', hash: '' },
    history: { state: null, replaceState: () => undefined },
    document: {
      addEventListener: () => undefined,
      querySelector: () => null,
      getElementById: () => null,
    },
    fetch: (_url: string, init: { body: string }) => {
      lanePosts.push({ body: init.body });
      if (laneAnswer === null) return Promise.reject(new Error('offline'));
      return Promise.resolve({ ok: laneAnswer });
    },
    URLSearchParams,
    encodeURIComponent,
    decodeURIComponent,
    Date: FakeDate,
    Math,
    JSON,
    Number,
    String,
    Array,
    Object,
    Set,
    Map,
  };
  vm.createContext(sandbox);
  vm.runInContext(read('next-boot.js'), sandbox, { filename: 'next-boot.js' });
  vm.runInContext(
    'let nextData = null; let nextIsLeader = false; function renderNext(){}',
    sandbox,
  );
  vm.runInContext(read('next-notify.js'), sandbox, { filename: 'next-notify.js' });
  const defineNotification = (): void => {
    if (supported) sandbox['Notification'] = FakeNotification;
    else delete sandbox['Notification'];
  };
  defineNotification();
  const call = <T>(name: string, ...args: unknown[]): T => {
    const fn = sandbox[name];
    if (typeof fn !== 'function') throw new Error(`The legacy page has no ${name}.`);
    return (fn as (...a: unknown[]) => T)(...args);
  };
  return {
    banners,
    lanePosts,
    setPermission(value) {
      permission = value;
    },
    setSupported(value) {
      supported = value;
      defineNotification();
    },
    setNow(ms) {
      now = ms;
    },
    setLeader(value) {
      sandbox['__leader'] = value;
      vm.runInContext('nextIsLeader = __leader;', sandbox);
    },
    setThrowing(value) {
      throwing = value;
    },
    setLaneAnswer(value) {
      laneAnswer = value;
    },
    sync(payload) {
      call('nextSyncNotifications', payload);
    },
    control(payload) {
      return call<string>('nextNotifyControl', payload);
    },
    request() {
      sandbox['__data'] = {};
      vm.runInContext('nextData = __data;', sandbox);
      call('nextRequestNotifyPermission');
    },
    async settle() {
      for (let turn = 0; turn < 6; turn += 1) await Promise.resolve();
    },
  };
}
