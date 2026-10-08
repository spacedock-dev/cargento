import { useFocusKey } from '../controls';
import { useDisplayed, useShell } from '../shell/context';

/* A control whose press is a request in flight draws busy whatever its resting state says: aria-disabled
   and aria-busy with a spinner over its idle label held as an invisible ghost, so its width and its focus
   stay put, and a redraw mid-request neither hides it nor re-arms it. `aria-disabled` and never `disabled`,
   which would drop keyboard focus from the control just pressed. An inert control stays on the page and
   reachable, and refuses its own press, because an inert control that goes silent reads as a dead one. */

export interface ActionButtonProps {
  /** The runtime's pending key for this control; empty for a control that never sends a request. */
  readonly pendingKey?: string;
  readonly label: string;
  readonly busyLabel?: string;
  /** The busy label of a control far narrower than it, held at rest as a hidden ghost in the same cell. */
  readonly reserve?: string;
  readonly inert?: boolean;
  readonly hidden?: boolean;
  /** What describes the control while it is inert: the sentences saying why. Emitted only then, because
   * `aria-disabled` keeps the control in the tab order and a reader would hear "dimmed" and nothing about why. */
  readonly describedBy?: string;
  /** What always describes the control, as an armed discard's warning does. */
  readonly describes?: string;
  readonly focusKey?: string;
  readonly fallbackKey?: string;
  readonly weight?: 'primary' | 'secondary' | 'quiet' | 'none';
  readonly className?: string;
  readonly action?: string;
  readonly arg?: string;
  readonly ariaLabel?: string;
  readonly ariaPressed?: boolean;
  readonly onPress: (detail: number) => void;
}

export function ActionButton({
  pendingKey = '',
  label,
  busyLabel = '',
  reserve = '',
  inert = false,
  hidden = false,
  describedBy = '',
  describes = '',
  focusKey,
  fallbackKey,
  weight = 'secondary',
  className,
  action,
  arg,
  ariaLabel,
  ariaPressed,
  onPress,
}: ActionButtonProps) {
  const { controls } = useShell();
  const busy = useDisplayed(
    (snapshot) => Boolean(pendingKey) && snapshot.pending.includes(pendingKey),
  );
  const ref = useFocusKey<HTMLButtonElement>(
    controls.focusLane,
    focusKey ?? null,
    fallbackKey === undefined ? {} : { fallback: fallbackKey },
  );
  const classes =
    className ?? (weight === 'none' ? undefined : `next-action next-action--${weight}`);
  const idle = reserve ? (
    <span className="next-action-reserve">
      <span>{label}</span>
      <span className="next-action-ghost" aria-hidden="true">
        <span className="next-action-busy">
          <span className="next-spinner" aria-hidden="true" />
          {reserve}
        </span>
      </span>
    </span>
  ) : (
    label
  );
  return (
    <button
      ref={ref}
      type="button"
      {...(classes ? { className: classes } : {})}
      {...(focusKey ? { 'data-next-focus': focusKey } : {})}
      {...(action ? { 'data-next-cockpit-action': action } : {})}
      {...(arg !== undefined ? { 'data-arg': arg } : {})}
      {...(reserve ? { 'data-next-reserve': '' } : {})}
      {...(ariaLabel ? { 'aria-label': ariaLabel } : {})}
      {...(ariaPressed !== undefined ? { 'aria-pressed': ariaPressed } : {})}
      {...(hidden ? { hidden: true } : {})}
      {...(busy
        ? { 'aria-disabled': true, 'aria-busy': true, 'data-next-pending': '' }
        : inert
          ? { 'aria-disabled': true }
          : {})}
      {...(!busy && inert && describedBy ? { 'aria-describedby': describedBy } : {})}
      {...(describes ? { 'aria-describedby': describes } : {})}
      onClick={(event) => {
        event.preventDefault();
        onPress(event.detail);
      }}
    >
      {busy ? (
        <>
          <span className="next-action-ghost" aria-hidden="true">
            {label}
          </span>
          <span className="next-action-busy">
            <span className="next-spinner" aria-hidden="true" />
            {busyLabel}
          </span>
        </>
      ) : (
        idle
      )}
    </button>
  );
}
