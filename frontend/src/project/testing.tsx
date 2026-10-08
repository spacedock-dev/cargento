/* A shell for the project views' tests: the real owners over a fake clock and a scripted backend that
   answers the board and each project-context read on its own terms, so a test can hold a read open, fail
   it, or change what the next board says. Not imported by production code. */
import { act, render } from '@testing-library/react';
import { StrictMode } from 'react';
import type { FetchLike } from '../api/client';
import { fakeBackend, type FakeBackend } from '../../test/storage_backends';
import { createRouter } from '../router/router';
import { fakeRouterEnvironment } from '../router/testing';
import { App } from '../App';
import { createShell } from '../shell/createShell';
import { flush } from '../shell/testing';
import { createFakeClock, createFakeEnvironment } from '../transport/testing';

export interface ProjectShellOptions {
  readonly hash?: string;
  readonly data?: unknown;
  /** The answer to a project-context read, by `project\nsession`; a missing key is a read that fails. */
  readonly contexts?: Readonly<Record<string, unknown>>;
  readonly strict?: boolean;
  readonly storage?: Readonly<Record<string, string>>;
  readonly storageBackend?: FakeBackend;
  readonly focusCapability?: string;
}

export interface Request {
  readonly method: string;
  readonly url: string;
  readonly body: unknown;
}

export function mountProject(options: ProjectShellOptions = {}) {
  const history = fakeRouterEnvironment(options.hash ?? '#n=projects');
  const router = createRouter(history.env);
  const clock = createFakeClock();
  const env = createFakeEnvironment({ clock, streamSupported: true });
  const backend = options.storageBackend ?? fakeBackend(options.storage ?? {});
  const state = {
    data: options.data as unknown,
    revision: 1,
    contexts: { ...(options.contexts ?? {}) } as Record<string, unknown>,
    requests: [] as Request[],
    /** Context keys whose read waits for `releaseContext`. */
    held: new Set<string>(),
    release: new Map<string, () => void>(),
  };
  const fetch: FetchLike = (url, init) => {
    const body = init?.body ? (JSON.parse(String(init.body)) as unknown) : null;
    state.requests.push({ method: init?.method ?? 'GET', url, body });
    if (url.startsWith('/api/project-context')) {
      const query = new URLSearchParams(url.slice(url.indexOf('?') + 1));
      const key = `${query.get('project') ?? ''}\n${query.get('session') ?? ''}`;
      const answer = () => {
        const reply = state.contexts[key];
        if (reply === undefined) return Promise.reject(new Error('offline'));
        return Promise.resolve(new Response(JSON.stringify(reply), { status: 200 }));
      };
      if (state.held.has(key)) {
        return new Promise<Response>((resolve, reject) => {
          state.release.set(key, () => {
            answer().then(resolve, reject);
          });
        });
      }
      return answer();
    }
    if (state.data === undefined || state.data === null)
      return Promise.reject(new Error('offline'));
    state.revision += 1;
    return Promise.resolve(
      new Response(JSON.stringify(state.data), {
        status: 200,
        headers: { 'X-Cargento-Revision': `7.${String(state.revision)}` },
      }),
    );
  };
  const written: string[] = [];
  const shell = createShell({
    env,
    router,
    fetch,
    provider: () => backend,
    events: { addEventListener: () => undefined, removeEventListener: () => undefined },
    search: '',
    doc: options.focusCapability
      ? {
          querySelector: () =>
            ({ getAttribute: () => options.focusCapability ?? null }) as unknown as Element,
        }
      : null,
    host: { reload: () => undefined, streamSupported: true },
    reducedMotion: () => false,
    clipboard: () => ({
      writeText: (text: string) => {
        written.push(text);
        return Promise.resolve();
      },
    }),
  });
  const tree =
    options.strict === false ? (
      <App shell={shell} />
    ) : (
      <StrictMode>
        <App shell={shell} />
      </StrictMode>
    );
  const view = render(tree);
  return {
    ...view,
    shell,
    router,
    clock,
    state,
    backend,
    written,
    history,
    contextReads: () =>
      state.requests.filter((request) => request.url.startsWith('/api/project-context')),
    posts: () => state.requests.filter((request) => request.method !== 'GET'),
    settle: () => act(async () => void (await flush())),
    /** Lets a held context read answer, as a slow one would. */
    async releaseContext(key: string) {
      await act(async () => {
        state.held.delete(key);
        state.release.get(key)?.();
        state.release.delete(key);
        await flush();
      });
    },
    /** The next board, as a poll would bring it. */
    async poll(next: unknown) {
      state.data = next;
      await act(async () => {
        const read = shell.runtime.refresh();
        await flush();
        clock.advance(500);
        await read;
        await flush();
      });
    },
  };
}
