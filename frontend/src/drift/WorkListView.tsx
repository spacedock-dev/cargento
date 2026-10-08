import { openDirection } from '../intent/directions';
import { useDrift } from './context';
import { WORK_AS_REPORTED } from './sentences';
import { workList } from './workList';
import { Why } from './Why';

/* The numbered activity list, drawn under CURRENT ACTIVITY. It sits in the activity column under that
   column's own heading, so it has none of its own. The record's footer is tiered: where the harness's work
   results are read, one clause stays in view and the mix, the bounds, the scan and the full limit sit behind
   "About this record"; where none are read, the limit is the absence and stays in view. The route's
   tool-output sentence is not repeated here: "What is sent" beside the control owns it. */
export function WorkListView() {
  const { ctx, model } = useDrift();
  const list = workList({
    session: model.session,
    payload: model.payload,
    source: model.source,
    annotation: model.annotation,
    draft: model.draft,
    cited: model.cited,
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
    <section className="next-cockpit-work" data-next-cockpit-work>
      {list.anchor ? <p className="next-cockpit-work-anchor">{list.anchor}</p> : null}
      {list.unnumbered ? <p className="next-cockpit-work-absent">{list.unnumbered}</p> : null}
      {list.rows.length ? (
        <div className="next-cockpit-work-rows" role="list">
          {list.rows.map((row) => {
            const { entry } = row;
            const type = entry.type;
            return (
              <div
                key={`${entry.id}:${String(row.n)}`}
                className="next-cockpit-work-row"
                role="listitem"
                data-next-cockpit-work-type={type}
                {...(row.n === null ? {} : { 'data-next-entry': String(row.n) })}
                data-next-entry-id={entry.id}
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
                      <span className="next-cockpit-work-flag" data-next-entry-flag="later">
                        A later direction you gave
                      </span>
                    ) : null}
                    {row.flags.includes('cited') ? (
                      <span className="next-cockpit-work-flag" data-next-entry-flag="cited">
                        Cited
                      </span>
                    ) : null}
                  </div>
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
                    <button
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
                    </button>
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
    </section>
  );
}
