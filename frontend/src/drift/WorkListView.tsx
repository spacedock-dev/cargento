import { Badge } from '../ui/badge';
import { Card } from '../ui/card';
import { Button } from '../ui/button';
import { openDirection } from '../intent/directions';
import { useDrift } from './context';
import { WORK_AS_REPORTED } from './sentences';
import { workList } from './workList';
import { Why } from './Why';
import { useEffect, useRef } from 'react';

/* The numbered activity list, drawn under CURRENT ACTIVITY. It sits in the activity column under that
   column's own heading, so it has none of its own. The record's footer is tiered: where the harness's work
   results are read, one clause stays in view and the mix, the bounds, the scan and the full limit sit behind
   "About this record"; where none are read, the limit is the absence and stays in view. The route's
   tool-output sentence is not repeated here: "What is sent" beside the control owns it.

   Newest first: the rows are drawn from the last entry to the first, so a reader opens on what just happened.
   The numbers stay the ones the list assigns oldest-first, which every "#<n>" on the page and every citation
   names, so the column reads #32 down to #1. "Add to my intent" is always drawn: a control shown only on
   hover is one a reader does not know is there. */
export function WorkListView() {
  const { ctx, model, finding, jump } = useDrift();
  const panel = useRef<HTMLDivElement>(null);
  const jumped = useRef<object | null>(null);
  useEffect(() => {
    if (!finding || jumped.current === jump) return;
    jumped.current = jump;
    const target = [
      ...(panel.current?.querySelectorAll<HTMLElement>('[data-next-entry-id]') ?? []),
    ].find((node) => finding.citedIds.includes(node.dataset['nextEntryId'] ?? ''));
    if (!target) return;
    target.focus({ preventScroll: true });
    target.scrollIntoView({
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches
        ? 'instant'
        : 'smooth',
      block: 'center',
    });
  }, [finding, jump]);
  const list = workList({
    session: model.session,
    payload: model.payload,
    source: model.source,
    annotation: model.annotation,
    draft: model.draft,
    cited: model.cited,
    revealed: new Set(finding?.citedIds),
    generated: model.generated,
  });
  const about = (
    <>
      {list.mix ? <p className="next-cockpit-work-mix">{list.mix}</p> : null}
      {list.unlisted.map((said) => (
        <p key={said} className="next-cockpit-work-earlier">
          {said}
        </p>
      ))}
      {list.checks ? <p className="next-cockpit-work-checks">{list.checks}</p> : null}
      {list.bound ? <p className="next-cockpit-work-dropped">{list.bound}</p> : null}
      {list.reads ? <p className="next-cockpit-work-limit">{list.limit}</p> : null}
    </>
  );
  const hasAbout = Boolean(
    list.mix || list.unlisted.length || list.checks || list.bound || list.reads,
  );
  return (
    <Card
      ref={panel}
      variant="work-panel"
      as="section"
      className="next-cockpit-work"
      data-next-cockpit-work
    >
      {list.anchor ? <p className="next-cockpit-work-anchor">{list.anchor}</p> : null}
      {list.unnumbered ? <p className="next-cockpit-work-absent">{list.unnumbered}</p> : null}
      {list.rows.length ? (
        <div className="next-cockpit-work-rows" role="list">
          {[...list.rows].reverse().map((row) => {
            const { entry } = row;
            const type = entry.type;
            return (
              <div
                key={entry.id}
                className="next-cockpit-work-row"
                role="listitem"
                data-next-cockpit-work-type={type}
                {...(row.n === null ? {} : { 'data-next-entry': String(row.n) })}
                data-next-entry-id={entry.id}
                tabIndex={-1}
              >
                <span className="next-cockpit-work-n">
                  {row.n === null ? (
                    <span className="next-visually-hidden">not numbered</span>
                  ) : (
                    `#${String(row.n)}`
                  )}
                </span>
                <div className="next-cockpit-work-body">
                  <div className="next-cockpit-work-head">
                    {'report' in row.head ? (
                      <span className="next-cockpit-work-result">{row.head.report}</span>
                    ) : (
                      <>
                        <span className="next-cockpit-work-actor">{row.head.actor}</span>
                        <span className="next-cockpit-work-type">{row.head.type}</span>
                      </>
                    )}
                    {row.flags.includes('later') ? (
                      <Badge
                        variant="work-flag"
                        className="next-cockpit-work-flag"
                        data-next-entry-flag="later"
                      >
                        A later direction you gave
                      </Badge>
                    ) : null}
                    {row.flags.includes('cited') ? (
                      <Badge
                        variant="work-flag"
                        className="next-cockpit-work-flag"
                        data-next-entry-flag="cited"
                      >
                        Cited
                      </Badge>
                    ) : null}
                  </div>
                  {finding?.citedIds.includes(entry.id) ? (
                    <p className="next-cockpit-reading-evidence" data-next-finding-entry>
                      {`Cited for “${finding.detail || finding.clause || finding.label}” · ${row.n === null ? 'Entry not numbered in this view' : `#${String(row.n)}`}`}
                    </p>
                  ) : null}
                  {/* A model's paraphrase takes the third treatment, not the mono of a string a source
                      published: the reader must be able to tell the record from an account of it. */}
                  {entry.modelDerived ? (
                    <em className="next-cockpit-work-derived">{entry.summary}</em>
                  ) : (
                    <span className="next-cockpit-work-summary">{entry.summary}</span>
                  )}
                  <span className="next-cockpit-work-source next-visually-hidden">
                    {row.source}
                  </span>
                  <span className="next-cockpit-work-at">{row.at}</span>
                  {row.turn ? (
                    <span className="next-cockpit-work-turn">from the last turn</span>
                  ) : null}
                  {row.add ? (
                    <Button
                      className="self-start"
                      variant="bare"
                      type="button"
                      data-next-cockpit-action="direction-add"
                      data-arg={entry.id}
                      onClick={(event) => {
                        event.preventDefault();
                        if (model.identity && entry.id) {
                          void openDirection(ctx.intent, model.session, entry.id, row.n, true);
                        }
                      }}
                    >
                      Add to my intent
                    </Button>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      ) : list.unnumbered ? null : (
        <p className="next-cockpit-work-absent">{list.absent}</p>
      )}
      {list.reads ? (
        <p className="next-cockpit-work-limit next-cockpit-work-reported">{WORK_AS_REPORTED}</p>
      ) : (
        <p className="next-cockpit-work-limit">{list.limit}</p>
      )}
      {hasAbout ? (
        <Why name="work-about" summary="About this record">
          {about}
        </Why>
      ) : null}
    </Card>
  );
}
