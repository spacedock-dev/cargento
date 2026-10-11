/* DEC-27 retracts the session Copy controls. Normalize only the recorded side;
   a Copy control reintroduced on the React side must still fail parity. */
export function retractSessionCopies(root: ParentNode) {
  root
    .querySelectorAll(
      '[data-copy-kind], .next-session-copy, .next-session-copy-link, .next-session-copy-command',
    )
    .forEach((node) => node.remove());
  root.querySelectorAll('.next-session-reentry-clause').forEach((node) => {
    node.textContent = (node.textContent ?? '')
      .split(' · ')
      .filter((part) => part !== 'No resume command')
      .join(' · ');
  });
  root.querySelectorAll('.next-departure-reentry-why').forEach((node) => {
    if (node.textContent?.includes('re-entry command')) node.remove();
  });
  root.querySelectorAll('.next-session-reentry-none').forEach((node) => {
    if (!node.querySelector('.next-session-reentry-clause')?.textContent?.trim()) node.remove();
  });
}
