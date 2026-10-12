import { Badge } from '../ui/badge';
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip';
import { ActivityMarks } from './ActivityMarks';
import { LAST_TURN_MARK, type WorkRow } from './workList';

export function ActivityHead({ row }: { readonly row: WorkRow }) {
  return (
    <div className="next-cockpit-work-head">
      <span className="next-cockpit-work-actor">{row.head.actor}</span>
      <span className="next-cockpit-work-type">{row.head.type}</span>
      <span
        className="ml-auto flex min-w-0 flex-wrap items-center justify-end gap-x-2 gap-y-1 text-label [font-family:var(--mono)]"
        data-activity-head-right
      >
        {'check' in row.head && row.head.check ? (
          <ActivityMarks marks={row.head.check.marks} />
        ) : null}
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
        {row.turn ? (
          <Tooltip>
            <TooltipTrigger
              render={<span />}
              role="img"
              aria-label={LAST_TURN_MARK.words}
              className="next-cockpit-work-turn text-muted-foreground tracking-[.07em]"
            >
              {LAST_TURN_MARK.short}
            </TooltipTrigger>
            <TooltipContent>{LAST_TURN_MARK.words}</TooltipContent>
          </Tooltip>
        ) : null}
        <span className="next-cockpit-work-at">{row.at}</span>
      </span>
    </div>
  );
}
