/* A development-only page that mounts the timeline and the exact-session terminal over the REAL shell
   (runtime, store, router, controls, display gate), so a browser test can drive them against the real
   Python backend the way the later project and session views will host them. It is not shipped: nothing
   in the production entry imports it, and the browser tests serve it by swapping `main.tsx` inside a
   scratch copy of the tree.

   The route decides what is on the page, exactly as the project view will: a project route with a focused
   session shows that session's Decisions timeline and its terminal, a project route without one shows the
   project-scope timeline, and anything else is "elsewhere", which unmounts both. Leaving and coming back
   is therefore a real route change and a real unmount, not a toggle the test invented. */
import { StrictMode, useMemo } from 'react';
import { createRoot } from 'react-dom/client';
import { splitSessKey } from '../src/api/identity';
import { ControlsProvider } from '../src/controls/ControlsProvider';
import { ShellContext, useDisplayed, useRoute, useShell } from '../src/shell/context';
import { createShell } from '../src/shell/createShell';
import { payloadSessions } from '../src/api/bootstrap';
import { TerminalSurface, terminalOwnerFor } from '../src/terminal';
import { Timeline } from '../src/timeline';
import { useBoardRuntime } from '../src/transport/hooks';
import { replaceRuntime } from '../src/transport/runtime';
import '../src/styles/shell.css';
import '../src/styles/controls.css';
import '../src/styles/tailwind.css';

// A test entry module that mounts itself and exports nothing, so fast refresh has no component to track.
// biome-ignore lint/style/useComponentExportOnlyModules: nothing is exported, as the note above says.
function Hosted() {
  const shell = useShell();
  useBoardRuntime(shell.runtime);
  const route = useRoute();
  const data = useDisplayed((snapshot) => snapshot.data);
  const project = route.view === 'project' ? route.project : null;
  /* The timeline wants a stable list, so a poll that changes nothing about the project's sessions does not
     rebuild its model. */
  const members = useMemo(
    () =>
      payloadSessions(data)
        .rows.filter((row) => String(row.project ?? '') === project)
        .flatMap((row) => (row.harness && row.sid ? [{ harness: row.harness, sid: row.sid }] : [])),
    [data, project],
  );
  if (route.view !== 'project') {
    return (
      <p id="elsewhere" data-view={route.view}>
        Elsewhere: {route.view}
      </p>
    );
  }
  const identity = route.focus ? splitSessKey(route.focus) : null;
  return (
    <div id="hosted" data-project={route.project} data-focus={route.focus ?? ''}>
      <Timeline
        project={route.project}
        projectKey={route.project}
        focus={identity}
        sessions={members}
        defaultMode="decisions"
      />
      {identity ? (
        <TerminalSurface project={route.project} identity={identity} />
      ) : (
        <p id="no-focus">No session is focused.</p>
      )}
    </div>
  );
}

function mountHarness(root: HTMLElement): void {
  const shell = createShell();
  replaceRuntime(shell.runtime);
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
