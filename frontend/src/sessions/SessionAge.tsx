import { nextNumber } from '../api/bootstrap';
import { durationSince, type Row } from '../observed';

export function SessionAge({
  session,
  generated,
}: {
  readonly session: Row;
  readonly generated: number | null;
}) {
  const started = nextNumber(session['started_at']);
  const first = nextNumber(session['first_prompt_at']);
  const at = started !== null && started > 0 ? started : first;
  const duration = durationSince(generated, at);
  if (duration === null || at === null) return null;
  const title = `${started !== null && started > 0 ? 'Started' : 'From the first message in the record'}: ${new Date(at * 1000).toLocaleString()}`;
  return (
    <>
      {' '}
      · <span data-session-age title={title}>{`Started about ${duration} ago`}</span>
    </>
  );
}
