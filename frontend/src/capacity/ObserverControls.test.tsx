import { fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ProjectConsole } from '../delegation';
import { json, mountPanels, type Handler, type MountOptions } from '../steering/testing';
import { ObserverControls } from './ObserverControls';

/* The observer-model controls: what they say for a capability nothing has read, one the server switched off,
   one that is on but unanswered, one allowed and one declined; that allowing sends nothing; and that the only
   thing that starts a model request is the press of "Summarize this session", once, for the exact session on
   screen. Every request is counted at the fetch: the backend is a script, so no model is called here. */
const CONSENT = 'cargento.observer-model-consent.v1';
const DISCLOSURE = 'Send redacted transcript excerpts for a goal summary? Each prompt is capped.';
const focus = { harness: 'claude', sid: 's1' };
const board = {
  generated: 1000,
  sessions: [{ harness: 'claude', sid: 's1', project: 'alpha', state: 'working', title: 'Work' }],
};
const offer = (over: Record<string, unknown> = {}) => ({
  enabled: true,
  disclosure: DISCLOSURE,
  ...over,
});
const context =
  (model: unknown, extra: Record<string, unknown> = {}): Handler =>
  () =>
    json({ semantic: {}, observer_model: model, ...extra });
const mount = (
  model: unknown,
  options: MountOptions = {},
  props: { focus?: typeof focus | null } = {},
) => {
  const chosen = props.focus === undefined ? focus : props.focus;
  return mountPanels(
    <ProjectConsole
      project="alpha"
      projectKey="alpha"
      focus={chosen}
      observer={<ObserverControls projectKey="alpha" focus={chosen} />}
    />,
    {
      data: board,
      routes: {
        '/api/interaction/origin': () => json({ state: 'unavailable' }),
        '/api/project-context': context(model),
        ...(options.routes ?? {}),
      },
      ...(options.storage ? { storage: options.storage } : {}),
    },
  );
};
const text = (): string =>
  document.querySelector('[data-next-observer-consent]')?.textContent ??
  document.querySelector('.next-cockpit-console-setup .next-cockpit-empty')?.textContent ??
  '';
const modelRequests = (page: ReturnType<typeof mount>) =>
  page.state.requests.filter((r) => /observer_model=1/.test(r.url));
const action = (name: string) =>
  document.querySelector<HTMLButtonElement>(`[data-next-observer-action="${name}"]`);
const press = (name: string) => {
  const button = action(name);
  if (!button) throw new Error(`no ${name} button`);
  fireEvent.click(button);
};

describe('an offer nothing has read is not an offer that is off', () => {
  it('says "not read" before the read arrives, "disabled" after a server that switched it off', async () => {
    const page = mount(offer(), { routes: { '/api/project-context': () => 'hold' as never } });
    await page.settle();
    expect(document.body.textContent).toContain('Observer model availability has not been read.');
    expect(document.body.textContent).not.toContain('disabled for this run');
    await page.release(
      '/api/project-context',
      json({ semantic: {}, observer_model: { enabled: false } }),
    );
    expect(document.body.textContent).toContain('Observer model is disabled for this run.');
    expect(document.body.textContent).toContain('--no-observer-model refuses them');
    expect(document.body.textContent).not.toContain('availability has not been read');
    expect(action('allow')).toBeNull();
    expect(action('request')).toBeNull();
  });

  it('a read that published no offer at all says "not read", as the page did', async () => {
    const page = mount(null);
    await page.settle();
    expect(document.body.textContent).toContain('Observer model availability has not been read.');
    expect(modelRequests(page)).toEqual([]);
  });

  it('an enabled offer with no disclosure withholds the request and says why', async () => {
    const page = mount({ enabled: true });
    await page.settle();
    expect(document.body.textContent).toContain(
      'Observer disclosure is unavailable; model requests are withheld.',
    );
    expect(action('request')).toBeNull();
    expect(action('allow')).toBeNull();
  });

  it('asks for one exact session at project scope, and never offers a display id as one', async () => {
    const page = mount(offer(), {}, { focus: null });
    await page.settle();
    expect(document.body.textContent).toContain(
      'Select one exact session to request an optional model goal summary.',
    );
    page.unmount();
    const half = mount(offer(), {}, { focus: { harness: 'claude', sid: '' } });
    await half.settle();
    expect(action('request')).toBeNull();
    expect(modelRequests(half)).toEqual([]);
  });
});

describe('allowing summaries sends nothing', () => {
  it('shows the disclosure and sends no model request through mount, polls, a remount and StrictMode', async () => {
    const page = mount(offer());
    await page.settle();
    expect(text()).toContain(DISCLOSURE);
    expect(text()).toContain('Credential redaction does not remove private prose.');
    expect(text()).toContain('Quota consent does not authorize this request.');
    expect(text()).toContain('Allowing summaries does not send a request.');
    expect(action('allow')?.textContent).toBe('Allow model summaries');
    expect(action('decline')?.textContent).toBe('No thanks');
    expect(action('request')).toBeNull();
    await page.poll({ ...board, generated: 1001 });
    await page.advance(120_000);
    page.show(<p>Elsewhere</p>);
    await page.settle();
    page.show(
      <ProjectConsole
        project="alpha"
        projectKey="alpha"
        focus={focus}
        observer={<ObserverControls projectKey="alpha" focus={focus} />}
      />,
    );
    await page.settle();
    expect(modelRequests(page)).toEqual([]);
    expect(page.posts()).toBe(0);
  });

  it('Allow records the answer and still sends nothing; Summarize then appears', async () => {
    const page = mount(offer());
    await page.settle();
    press('allow');
    await page.settle();
    expect(page.backend.data.get(CONSENT)).toBe('granted');
    expect(modelRequests(page)).toEqual([]);
    expect(action('request')?.textContent).toBe('Summarize this session');
    expect(action('decline')?.textContent).toBe('Turn off model summaries');
    expect(action('allow')).toBeNull();
    await page.poll({ ...board, generated: 1002 });
    expect(modelRequests(page)).toEqual([]);
  });

  it('declining says so and offers only Allow; quota consent authorizes nothing here', async () => {
    const page = mount(offer(), {
      storage: { [CONSENT]: 'declined', 'cargento.next.usage.consent': 'granted' },
    });
    await page.settle();
    expect(text()).toContain('Model summaries are off in this browser.');
    expect(action('request')).toBeNull();
    expect(action('allow')).not.toBeNull();
    expect(modelRequests(page)).toEqual([]);
    page.unmount();
    // Quota granted, observer unanswered: still only the question.
    const other = mount(offer(), { storage: { 'cargento.next.usage.consent': 'granted' } });
    await other.settle();
    expect(action('allow')).not.toBeNull();
    expect(action('request')).toBeNull();
    expect(modelRequests(other)).toEqual([]);
  });
});

describe('the one press that starts a model request', () => {
  const allowed = { [CONSENT]: 'granted' };

  it('sends exactly one request for the exact session, shows it in progress, and cannot be doubled', async () => {
    const page = mount(offer(), {
      storage: allowed,
      routes: {
        '/api/project-context': (request) =>
          /observer_model=1/.test(request.url)
            ? 'hold'
            : json({ semantic: {}, observer_model: offer() }),
      },
    });
    await page.settle();
    expect(modelRequests(page)).toEqual([]);
    press('request');
    await page.settle();
    expect(modelRequests(page)).toHaveLength(1);
    const sent = modelRequests(page)[0]?.url ?? '';
    expect(sent).toContain('project=alpha');
    expect(sent).toContain('session=claude%3As1');
    expect(sent).toContain('refresh=1');
    expect(action('request')?.textContent).toBe('Request in progress');
    expect(action('request')?.disabled).toBe(true);
    expect(text()).toContain('The requested model summary is in progress.');
    fireEvent.click(action('request') as HTMLElement);
    expect(modelRequests(page)).toHaveLength(1);
    await page.release(
      '/api/project-context',
      json({
        semantic: {},
        observer_model: offer(),
        observers: [
          { harness: 'claude', sid: 's1', goal: 'Ship the retry queue', model: { status: 'ok' } },
          { harness: 'codex', sid: 's1', goal: 'The other harness' },
        ],
      }),
    );
    expect(text()).toContain('The refresh returned. Model failures fall back to local analysis.');
    expect(text()).toContain('Observed goal: Ship the retry queue');
    expect(text()).toContain('Model status: ok');
    expect(text()).not.toContain('The other harness');
    expect(action('request')?.disabled).toBe(false);
  });

  it('a failed request keeps local analysis and says so', async () => {
    const page = mount(offer(), {
      storage: allowed,
      routes: {
        '/api/project-context': (request) =>
          /observer_model=1/.test(request.url)
            ? new Response('no', { status: 500 })
            : json({ semantic: {}, observer_model: offer() }),
      },
    });
    await page.settle();
    press('request');
    await page.settle();
    expect(text()).toContain('The summary request failed. Local analysis remains available.');
    expect(modelRequests(page)).toHaveLength(1);
  });

  it('says when a refresh returned with no goal, and when the model status was not published', async () => {
    const page = mount(offer(), {
      storage: allowed,
      routes: {
        '/api/project-context': (request) =>
          /observer_model=1/.test(request.url)
            ? json({
                semantic: {},
                observer_model: offer(),
                observers: [{ harness: 'claude', sid: 's1', goal: '  ' }],
              })
            : json({ semantic: {}, observer_model: offer() }),
      },
    });
    await page.settle();
    press('request');
    await page.settle();
    expect(text()).toContain('No goal summary was published by this refresh.');
  });

  it('refuses, and says so, when the consent was withdrawn since the page was drawn', async () => {
    const page = mount(offer(), { storage: allowed });
    await page.settle();
    // Another tab turned it off: storage changed, this tab has not redrawn yet.
    page.backend.data.set(CONSENT, 'declined');
    press('request');
    await page.settle();
    expect(modelRequests(page)).toEqual([]);
    expect(document.querySelector('[data-next-observer-refused]')?.textContent).toContain(
      'turned off in another tab',
    );
  });

  it('refuses, and says so, when the offer the board holds is not the one on screen', async () => {
    const page = mount(offer(), { storage: allowed });
    await page.settle();
    const drawn = action('request') as HTMLElement;
    const store = page.shell.runtime.store;
    const key = 'alpha\nclaude:s1';
    const entry = store.getSnapshot().contexts.get(key);
    expect(entry).toBeDefined();
    // The board accepts a different disclosure; the reader's hand is still on the old button. A native click
    // runs the handler this render attached, before React commits the new offer.
    const spy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    store.setContext(key, {
      ...(entry as NonNullable<typeof entry>),
      data: {
        ...(entry?.data ?? {}),
        observer_model: offer({ disclosure: 'Send everything to another service?' }),
      },
    });
    drawn.click();
    spy.mockRestore();
    await page.settle();
    expect(modelRequests(page)).toEqual([]);
    expect(document.querySelector('[data-next-observer-refused]')?.textContent).toContain(
      'offer changed since this page was drawn',
    );
  });

  it('a reader who leaves while it runs finds the result, and no second request, on return', async () => {
    const hold = (request: { url: string }) =>
      /observer_model=1/.test(request.url)
        ? 'hold'
        : json({ semantic: {}, observer_model: offer() });
    const page = mount(offer(), {
      storage: allowed,
      routes: { '/api/project-context': hold as Handler },
    });
    await page.settle();
    press('request');
    await page.settle();
    page.show(<p>Elsewhere</p>);
    await page.settle();
    await page.release(
      '/api/project-context',
      json({
        semantic: {},
        observer_model: offer(),
        observers: [{ harness: 'claude', sid: 's1', goal: 'Kept goal', model: { status: 'ok' } }],
      }),
    );
    page.show(
      <ProjectConsole
        project="alpha"
        projectKey="alpha"
        focus={focus}
        observer={<ObserverControls projectKey="alpha" focus={focus} />}
      />,
    );
    await page.settle();
    expect(modelRequests(page)).toHaveLength(1);
    expect(text()).toContain('Observed goal: Kept goal');
    expect(page.shell.runtime.store.getSnapshot().observer.requests).toEqual([]);
  });
});
