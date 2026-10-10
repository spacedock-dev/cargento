import { Button } from '../ui/button';
import { useEffect, useSyncExternalStore } from 'react';
import { useFocusKey } from '../controls/useFocusKey';
import { useDisplayed, useShell } from '../shell/context';
import { notifyOwnerFor, startNotifications } from './registry';
import './notify.css';

const BLOCKED_TITLE =
  'Re-enable notifications for this site in your browser settings to be alerted when a session needs you.';

/* The header's notification control, and the place the tab's notification owner is started. Starting is
   all that happens on mount: the owner reads the board, and the browser's prompt opens only when the reader
   presses Enable. A granted or unsupported tab, and one whose banners the server's own lane raises, draws
   nothing, so the control never offers what the tab cannot do. */
export function NotificationControl() {
  const { runtime, controls } = useShell();
  const owner = notifyOwnerFor(runtime);
  useEffect(() => {
    startNotifications(runtime);
  }, [runtime]);
  useSyncExternalStore(owner.subscribe, owner.version);
  const data = useDisplayed((snapshot) => snapshot.data);
  /* The control is the focus lane's fallback holder for itself: once the reader answers, it goes, and
     focus returns to the current primary item rather than to the page. */
  const buttonRef = useFocusKey<HTMLButtonElement>(controls.focusLane, 'notify-enable', {
    fallback: 'primary-current',
  });
  const state = owner.control(data);
  if (state === 'blocked') {
    return (
      <span className="next-notify-note" title={BLOCKED_TITLE}>
        notifications blocked
      </span>
    );
  }
  if (state !== 'enable') return null;
  return (
    <Button
      ref={buttonRef}
      type="button"
      className="next-notify-button"
      data-next-action="enable-notifications"
      onClick={() => owner.request()}
    >
      Enable notifications
    </Button>
  );
}
