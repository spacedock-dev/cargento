import { Button } from '../ui/button';
import type { KeyboardEvent, ReactNode } from 'react';
import { useFocusKey } from '../controls/useFocusKey';
import { cockpitTabs, type ProjectRoute, type ProjectTab } from '../router/grammar';
import { useNavigate, useShell } from './context';

const label = (tab: string): string => (tab ? (tab[0] ?? '').toUpperCase() + tab.slice(1) : 'Work');

function Tab({
  tab,
  selected,
  cue,
  onSelect,
  onKeyDown,
}: {
  readonly tab: ProjectTab;
  readonly selected: boolean;
  readonly cue: ReactNode;
  readonly onSelect: () => void;
  readonly onKeyDown: (event: KeyboardEvent<HTMLButtonElement>) => void;
}) {
  const { controls } = useShell();
  const ref = useFocusKey<HTMLButtonElement>(controls.focusLane, `cockpit-tab:${tab}`);
  return (
    <Button
      variant="native"
      ref={ref}
      type="button"
      role="tab"
      id={`next-cockpit-tab-${tab}`}
      data-next-cockpit-action="tab"
      data-arg={tab}
      aria-controls={`next-cockpit-panel-${tab}`}
      aria-selected={selected}
      tabIndex={selected ? 0 : -1}
      onClick={onSelect}
      onKeyDown={onKeyDown}
    >
      {label(tab)}
      {cue}
    </Button>
  );
}

/* The project's tab strip and the one panel that is current. The route holds the selected tab (Now is
   the default and is not printed), and the arrow keys wrap over the list the strip drew, because a wrap
   over a list the nav did not render would move focus to a tab that is not on the reader's screen. The
   panel's body belongs to the views that fill it. */
export function ProjectTabs({
  route,
  cue,
  children,
}: {
  readonly route: ProjectRoute;
  /** What a tab's own count says, drawn inside its button: the project views supply it, a bare strip has none. */
  readonly cue?: (tab: ProjectTab) => ReactNode;
  readonly children: (tab: ProjectTab) => ReactNode;
}) {
  const navigate = useNavigate();
  const { controls } = useShell();
  const tabs = cockpitTabs(route.focus);
  const selected = route.tab && tabs.includes(route.tab) ? route.tab : 'now';
  const open = (tab: ProjectTab) =>
    navigate({ view: 'project', project: route.project, focus: route.focus ?? null, tab });

  const onKeyDown = (current: ProjectTab) => (event: KeyboardEvent<HTMLButtonElement>) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    // Alt/Cmd+Arrow is the browser's Back and Forward and Ctrl/Cmd+Home/End its scroll: the legacy page returns before its tab handler.
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    const index = Math.max(0, tabs.indexOf(current));
    const next =
      event.key === 'Home'
        ? 0
        : event.key === 'End'
          ? tabs.length - 1
          : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
    const target = tabs[next];
    if (!target) return;
    event.preventDefault();
    open(target);
    controls.focusLane.focus(`cockpit-tab:${target}`);
  };

  return (
    <>
      <nav className="next-cockpit-tabs" role="tablist" aria-label="Project cockpit views">
        {tabs.map((tab) => (
          <Tab
            key={tab}
            tab={tab}
            selected={tab === selected}
            cue={cue ? cue(tab) : null}
            onSelect={() => open(tab)}
            onKeyDown={onKeyDown(tab)}
          />
        ))}
      </nav>
      <div
        role="tabpanel"
        id={`next-cockpit-panel-${selected}`}
        aria-labelledby={`next-cockpit-tab-${selected}`}
      >
        {children(selected)}
      </div>
    </>
  );
}
