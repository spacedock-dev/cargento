/* A shell for the steering and Console tests: the real owners (runtime, store, router, announcer, gate,
   controls, storage) over a fake clock, an in-memory storage and a scripted backend that answers each route
   on its own terms and counts every request. The children are the components under test, mounted inside the
   same providers `App` builds, so a test drives them as the page does without the rest of the page. Not
   imported by production code. */
import { act, render } from '@testing-library/react';
import { StrictMode, type ReactNode } from 'react';
import type { FetchLike } from '../api/client';
import { fakeBackend, type FakeBackend } from '../../test/storage_backends';
import { ControlsProvider } from '../controls/ControlsProvider';
import { AnnouncerProvider, LiveRegions } from '../shell/LiveRegions';
import { createRouter } from '../router/router';
import { fakeRouterEnvironment } from '../router/testing';
import { ShellContext, useShell } from '../shell/context';
import { createShell } from '../shell/createShell';
import { flush } from '../shell/testing';
import { useBoardRuntime } from '../transport/hooks';
import { createFakeClock, createFakeEnvironment } from '../transport/testing';

export interface RecordedRequest {
  readonly method: string;
  readonly url: string;
  readonly path: string;
  readonly body: Record<string, unknown> | null;
  readonly signal?: AbortSignal;
}

export type Handler = (request: RecordedRequest) => Response | Promise<Response> | 'hold';

export const json = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status });

export interface MountOptions {
  readonly data?: unknown;
  readonly strict?: boolean;
  readonly hash?: string;
  readonly routes?: Record<string, Handler>;
  readonly storage?: Record<string, string>;
  readonly focusCapability?: string;
}

// biome-ignore lint/style/useComponentExportOnlyModules: a test double, never part of a fast-refresh tree.
function Host({ children }: { readonly children: ReactNode }) {
  useBoardRuntime(useShell().runtime);
  return <>{children}</>;
}

export function mountPanels(
  children: ReactNode | ((shell: ReturnType<typeof createShell>) => ReactNode),
  options: MountOptions = {},
) {
  const history = fakeRouterEnvironment(options.hash ?? '#n=projects');
  const router = createRouter(history.env);
  const clock = createFakeClock();
  const env = createFakeEnvironment({ clock, streamSupported: true });
  const backend: FakeBackend = fakeBackend(options.storage ?? {});
  const state = {
    data: options.data as unknown,
    revision: 1,
    requests: [] as RecordedRequest[],
    routes: { ...(options.routes ?? {}) } as Record<string, Handler>,
    held: [] as { readonly path: string; readonly release: (response: Response) => void }[],
  };
  const fetch: FetchLike = (url, init) => {
    const path = url.split('?')[0] ?? url;
    const parsed = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null;
    const request: RecordedRequest = {
      method: init?.method ?? 'GET',
      url,
      path,
      body: parsed,
      ...(init?.signal ? { signal: init.signal } : {}),
    };
    state.requests.push(request);
    const handler = state.routes[path];
    if (handler) {
      const answer = handler(request);
      if (answer === 'hold') {
        return new Promise<Response>((resolve) => {
          state.held.push({ path, release: resolve });
        });
      }
      return Promise.resolve(answer);
    }
    if (path === '/api/project-context')
      return Promise.resolve(json({ semantic: {}, observer_model: null }));
    if (path !== '/api/data') return Promise.resolve(new Response('not scripted', { status: 404 }));
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
  });
  const body = typeof children === 'function' ? children(shell) : children;
  const page = (
    <ShellContext value={shell}>
      <AnnouncerProvider announcer={shell.announcer}>
        <ControlsProvider controls={shell.controls}>
          <Host>{body}</Host>
          <LiveRegions />
        </ControlsProvider>
      </AnnouncerProvider>
    </ShellContext>
  );
  const view = render(options.strict === false ? page : <StrictMode>{page}</StrictMode>);
  const count = (method: string, prefix: string) =>
    state.requests.filter((request) => request.method === method && request.path.startsWith(prefix))
      .length;
  return {
    ...view,
    shell,
    clock,
    state,
    backend,
    history,
    gets: (prefix = '/api/data') => count('GET', prefix),
    posts: (prefix = '/api/') => count('POST', prefix),
    allPosts: () => state.requests.filter((request) => request.method === 'POST'),
    settle: () => act(async () => void (await flush())),
    /** Replaces what is mounted, as a route change would, keeping the shell. */
    show(next: ReactNode) {
      view.rerender(
        <StrictMode>
          <ShellContext value={shell}>
            <AnnouncerProvider announcer={shell.announcer}>
              <ControlsProvider controls={shell.controls}>
                <Host>{next}</Host>
                <LiveRegions />
              </ControlsProvider>
            </AnnouncerProvider>
          </ShellContext>
        </StrictMode>,
      );
    },
    /** Answers the oldest held request on `path`, as the server would. */
    async release(path: string, response: Response) {
      await act(async () => {
        const at = state.held.findIndex((entry) => entry.path === path);
        const [entry] = at >= 0 ? state.held.splice(at, 1) : [];
        entry?.release(response);
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
    async advance(ms: number) {
      await act(async () => {
        clock.advance(ms);
        await flush();
      });
    },
  };
}
