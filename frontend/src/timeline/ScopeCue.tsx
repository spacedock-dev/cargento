import type { Scope } from './semantic';

/* Whose words an event is: the project's, one session's, or not known. Drawn with a shape as well as a
   word, so the three read apart without colour. The detail is the harness's own label for a session. */
const LABEL = { project: 'PROJECT', session: 'SESSION', unknown: 'SCOPE UNKNOWN' } as const;
const MARKER = { project: 'square', session: 'round', unknown: 'unknown' } as const;

export function ScopeCue({
  scope,
  detail,
}: {
  readonly scope: Scope;
  readonly detail?: string | undefined;
}) {
  return (
    <span
      className={`next-scope-cue next-scope-cue--${scope.kind}`}
      data-scope-kind={scope.kind}
      data-scope-owner={scope.owner}
    >
      <i
        className={`next-scope-marker next-scope-marker--${MARKER[scope.kind]}`}
        aria-hidden="true"
      />
      <strong>{LABEL[scope.kind]}</strong>
      {detail ? <span>{detail}</span> : null}
    </span>
  );
}
