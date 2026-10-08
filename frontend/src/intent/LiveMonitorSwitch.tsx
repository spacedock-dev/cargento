import { compatSessKey } from '../api/identity';
import { useFocusKey } from '../controls';
import { useShell } from '../shell/context';
import { LIVE_HARNESSES, useLiveMonitor } from './liveMonitor';
import { LIVE_MONITOR } from './sentences';
import { usePanel } from './useIntent';

/* The switch sits beside the Drift heading, as the design places it. It decides only whether the level, its
   nudge and the header pill are drawn, never what the server or a model does, and drawing it asks for
   nothing. */
export function LiveMonitorSwitch() {
  const shell = useShell();
  const { session, payload } = usePanel();
  const key = compatSessKey(session);
  const [on, set] = useLiveMonitor(shell, {
    harness: String(session['harness'] || ''),
    sid: String(session['sid'] || ''),
    session: String(session['session'] || ''),
  });
  const ref = useFocusKey<HTMLButtonElement>(shell.controls.focusLane, `live-monitor:${key}`);
  if (!LIVE_HARNESSES.has(String(session['harness'] || '')) || payload['annotate'] !== true) {
    return null;
  }
  return (
    <div className="next-session-drift-monitor">
      <span id="next-session-drift-monitor-label">{LIVE_MONITOR}</span>
      <button
        ref={ref}
        type="button"
        className="next-session-drift-switch"
        role="switch"
        aria-checked={on}
        aria-labelledby="next-session-drift-monitor-label"
        data-next-cockpit-action="live-monitor"
        data-next-focus={`live-monitor:${key}`}
        onClick={(event) => {
          event.preventDefault();
          set(!on);
        }}
      >
        <span className="next-session-drift-track" aria-hidden="true">
          <span />
        </span>
      </button>
    </div>
  );
}
