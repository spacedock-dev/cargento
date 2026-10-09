/* A development-only page that mounts the steering bar, the Course tab's stage conditions, the Decisions tab
   and the Console tab over the REAL shell (runtime, store, router, controls, display gate), through the same
   slot functions the project page composes (`STEERING_SLOTS`), so a browser test can drive them against the
   real Python backend. It is not shipped: nothing in the production entry imports it, and the browser tests
   serve it by swapping `main.tsx` inside a scratch copy of the tree.

   The route decides what is on the page, exactly as the project page will: a project route draws the steering
   bar above the tab strip and the selected tab's panel, and anything else is "elsewhere", which unmounts all of
   it. Leaving and coming back is therefore a real route change and a real unmount, not a toggle the test
   invented. The Now tab is not this step's, and says so. */
import { StrictMode, useEffect } from 'react';
import { createRoot } from 'react-dom/client';
import { payloadSessions } from '../src/api/bootstrap';
import { compatSessKey, exactIdentity, stableProjectKey } from '../src/api/identity';
import { ControlsProvider } from '../src/controls/ControlsProvider';
import { installChoiceRelease } from '../src/controls/displayGate';
import { shortcutTarget } from '../src/shell/keyboard';
import { ProjectTabs } from '../src/shell/ProjectTabs';
import { ShellContext, useDisplayed, useRoute, useShell } from '../src/shell/context';
import { createShell } from '../src/shell/createShell';
import { STEERING_SLOTS } from '../src/steering';
import { terminalOwnerFor } from '../src/terminal';
import { useBoardRuntime } from '../src/transport/hooks';
import { replaceRuntime } from '../src/transport/runtime';
import { startWorkstream } from '../src/workstream';
import '../src/styles/shell.css';
import '../src/styles/controls.css';
import '../src/project/project.css';

// A test entry module that mounts itself and exports nothing, so fast refresh has no component to track.
// biome-ignore lint/style/useComponentExportOnlyModules: nothing is exported, as the note above says.
function Hosted() {
  const shell = useShell();
  useBoardRuntime(shell.runtime);
  /* What the page does for the document and nothing else: a native list closing is the reader's own moment
     for the held poll, and Escape is the page's "leave this view" unless a control took it first. */
  useEffect(() => installChoiceRelease(document, shell.display), [shell]);
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target instanceof Element ? event.target : null;
      const move = shortcutTarget(
        {
          key: event.key,
          tagName: target?.tagName ?? 'BODY',
          isContentEditable: target instanceof HTMLElement && target.isContentEditable,
          metaKey: event.metaKey,
          ctrlKey: event.ctrlKey,
          altKey: event.altKey,
          defaultPrevented: event.defaultPrevented,
        },
        shell.router.getRoute(),
      );
      if (!move) return;
      event.preventDefault();
      shell.router.navigate(move);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [shell]);
  const route = useRoute();
  const data = useDisplayed((snapshot) => snapshot.data);
  if (route.view !== 'project') {
    return (
      <p id="elsewhere" data-view={route.view}>
        Elsewhere: {route.view}
      </p>
    );
  }
  const rows = payloadSessions(data).rows.filter(
    (row) => String(row.project ?? '') === route.project,
  );
  const focusRow = route.focus ? rows.find((row) => compatSessKey(row) === route.focus) : undefined;
  const identity = focusRow ? exactIdentity(focusRow) : null;
  const context = {
    project: route.project,
    projectKey: stableProjectKey({ label: route.project, sessions: rows }),
    focus: identity ? { ...identity, state: String(focusRow?.state ?? '') } : null,
    sessions: identity
      ? [identity]
      : rows.flatMap((row) => {
          const pair = exactIdentity(row);
          return pair ? [pair] : [];
        }),
  };
  return (
    <div id="hosted" data-project={route.project} data-focus={route.focus ?? ''}>
      <h1>{route.project}</h1>
      {STEERING_SLOTS.steering?.(context)}
      <ProjectTabs route={route}>
        {(tab) => (
          <section
            className="next-cockpit-panel"
            data-next-cockpit-panel={tab}
            aria-label={tab[0]?.toUpperCase() + tab.slice(1)}
          >
            {tab === 'now' ? (
              <p id="not-this-step">The Now tab is not part of this page.</p>
            ) : tab === 'course' ? (
              STEERING_SLOTS.courseConditions?.(context)
            ) : tab === 'decisions' ? (
              STEERING_SLOTS.decisions?.(context)
            ) : (
              STEERING_SLOTS.console?.(context)
            )}
          </section>
        )}
      </ProjectTabs>
    </div>
  );
}

function mountHarness(root: HTMLElement): void {
  const shell = createShell();
  replaceRuntime(shell.runtime);
  // The delegation figure is measured over the tab's evidence, which follows every payload from the first.
  startWorkstream(shell.runtime);
  const strict = new URLSearchParams(location.search).get('strict') !== '0';
  const page = (
    <ShellContext value={shell}>
      <ControlsProvider controls={shell.controls}>
        <main id="app">
          <nav aria-label="Primary">
            <a href="#n=sessions">Sessions</a>
          </nav>
          <Hosted />
        </main>
      </ControlsProvider>
    </ShellContext>
  );
  createRoot(root).render(strict ? <StrictMode>{page}</StrictMode> : page);
  Object.assign(window, { __harness: { shell, owner: terminalOwnerFor(shell) } });
}

const root = document.getElementById('root');
if (!root) throw new Error('The harness document is missing its root.');
mountHarness(root);
