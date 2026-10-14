import { Button } from '../ui/button';
import { RECORD_PAGE_SIZE } from '../transport/record';
import { EMPTY_RECORD, type RecordEntry } from '../store/board';

export function ShowMore({
  record = EMPTY_RECORD,
  pastWindow = false,
  ordinals = false,
  onMore,
}: {
  readonly record?: RecordEntry;
  readonly pastWindow?: boolean;
  /** Numbers are the session's fixed ones, so loading an older page renumbers nothing and says nothing of it. */
  readonly ordinals?: boolean;
  readonly onMore: () => void;
}) {
  const loading =
    record.status === 'loading' || (record.status === 'stale' && record.error === null);
  const stop = pastWindow
    ? "Everything since your intent's window opened is listed."
    : record.status === 'unsupported'
      ? 'Older entries are not read for this harness.'
      : record.reachedStart
        ? 'That is the start of the record.'
        : '';
  return (
    <div data-record-pages className="mt-3 text-body text-muted-foreground">
      {record.pages > 1 && !ordinals ? <p>Numbers count from the oldest entry loaded.</p> : null}
      {record.restarted ? (
        <p role="status">
          {record.status === 'stale' && record.error
            ? 'The record changed again. Show more retries from the newest entries.'
            : 'The record changed. Started again from the newest entries.'}
        </p>
      ) : null}
      {stop ? (
        <p data-record-stop tabIndex={-1}>
          {stop}
        </p>
      ) : (
        <>
          {record.status === 'error' ? <p role="status">Could not read older entries</p> : null}
          {record.bound ? (
            <p>{`The read stopped after reading ${String(Math.round((record.scannedBytes / 1048576) * 100) / 100)} MB without reaching ${String(RECORD_PAGE_SIZE)} more entries; Show more continues from there.`}</p>
          ) : null}
          <Button
            type="button"
            data-record-more
            aria-label={
              loading ? 'Reading older entries' : `Show ${String(RECORD_PAGE_SIZE)} older entries`
            }
            aria-busy={loading}
            disabled={loading}
            busyLabel="Reading older entries"
            reserve="Reading older entries"
            onClick={onMore}
          >
            Show more
          </Button>
        </>
      )}
    </div>
  );
}
