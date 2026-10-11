// Only reference identities move. Current DOM keys and computed chrome remain unaltered.
export function firstViewChromeKey(key) {
  if (key.includes('data-next-cockpit-action=held-undo aria-disabled=true')) return null;
  if (
    key.includes('next-session-detail--blocked') &&
    /data-next-cockpit-action=held-line-(add|remove)/.test(key)
  )
    return null;
  if (!key.includes('next-session-panel >')) return key;
  if (/data-next-cockpit-action=(held-clear|reading-off)/.test(key))
    return key.replace(/next-session-panel > .*?(?= \|)/, 'next-session-panel > ctl-disclosure');
  return key
    .replace(
      'next-session-panel > next-session-drift > next-session-drift-head > next-session-drift-monitor',
      'next-session-panel > ctl-disclosure > next-session-drift-monitor',
    )
    .replace(
      'next-session-panel > next-cockpit-held > ctl-disclosure.next-cockpit-held-stamp',
      'next-session-panel > ctl-disclosure > ctl-disclosure.next-cockpit-held-stamp',
    )
    .replace(
      'next-session-panel > next-session-drift > next-session-drift-caveats',
      'next-session-panel > ctl-disclosure > next-session-drift-caveats',
    )
    .replace(
      'next-session-panel > next-session-drift > next-cockpit-conflict',
      'next-session-panel > ctl-disclosure > next-cockpit-conflict',
    );
}

export function firstViewChromeReferences(entries) {
  return Object.fromEntries(
    entries.flatMap(([key, value]) => {
      const moved = firstViewChromeKey(key);
      return moved === null ? [] : [[moved, value]];
    }),
  );
}

export function firstViewDisclosureSizes(entries) {
  return Object.fromEntries(
    entries.flatMap(([key, sizes]) => {
      // This recorded ask remains blocked on the reader even though its collector state is working.
      if (
        key.includes('next-session-detail > next-session-detail-header') &&
        key.includes('next-session-reentry-none') &&
        !key.includes('#n=session:delta:claude:spacedock-asked')
      )
        return [];
      const moved = firstViewChromeKey(key);
      return moved === null ? [] : [[moved, moved === key ? sizes : [...sizes, null]]];
    }),
  );
}

export function isSessionMore(key) {
  return /^next-session-detail(?:\.next-session-detail--blocked)? > next-session-columns > next-session-panel > ctl-disclosure \| {2}\| More \| {2}\| disabled=false hidden=false$/.test(
    key,
  );
}

// New summary: the existing tier-2 recipe, with the natural width of "More" plus its chevron.
export const SESSION_MORE_SIZE = [{ fillsRow: false, width: 49.266 }];
