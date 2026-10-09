import type { ReactNode } from 'react';

/* The heading of a rail panel: the label and a note on the same line. `sentence` sets the note in the sans
   face for a note that is a sentence, and `tone` colours a caution. Shared by the Console's panels and the
   tripwires panel that sits among them, so it lives here and not in either. */
export function RailHeader({
  label,
  note,
  tone,
  sentence = false,
}: {
  readonly label: string;
  readonly note: ReactNode;
  readonly tone?: 'amber';
  readonly sentence?: boolean;
}) {
  const classes = ['next-rail-meta'];
  if (sentence) classes.push('next-rail-meta--sentence');
  if (tone) classes.push(`next-rail-meta--${tone}`);
  return (
    <header className="next-rail-header">
      <h2>{label}</h2>
      <span className={classes.join(' ')}>{note}</span>
    </header>
  );
}
