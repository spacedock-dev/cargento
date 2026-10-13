// Only the retired activity label doubled its actor. No other text or row is normalized.
export function recordedActivityActor(root: HTMLElement): void {
  for (const label of root.querySelectorAll('.next-cockpit-work-type')) {
    if (label.textContent === 'Agent said') label.textContent = 'said';
  }
}
