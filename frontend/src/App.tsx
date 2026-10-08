import { ControlsProvider } from './controls/ControlsProvider';
import { AnnouncerProvider, LiveRegions } from './shell/LiveRegions';
import { Page } from './shell/Page';
import { ShellContext, type Shell } from './shell/context';

/* The one React tree. The page and its five live regions are siblings: the regions are never inside the
   subtree a route replaces, because a node that arrives carrying its text is the one a reader's software
   skips. Nothing here fetches, polls or opens a stream by itself; the page acquires the board's runtime
   in an effect, which tolerates StrictMode's second pass. */
export function App({ shell }: { readonly shell: Shell }) {
  return (
    <ShellContext value={shell}>
      <AnnouncerProvider announcer={shell.announcer}>
        <ControlsProvider controls={shell.controls}>
          <Page />
          <LiveRegions />
        </ControlsProvider>
      </AnnouncerProvider>
    </ShellContext>
  );
}
