import { Icon } from '../ui/icons';
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip';
import { MARK_LEGEND, type ActivityMark } from './workList';

export function ActivityMarkView({ mark }: { readonly mark: ActivityMark }) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={<span />}
        role="img"
        aria-label={mark.words}
        className="inline-flex items-center gap-1 text-muted-foreground"
        data-activity-mark={mark.icon}
      >
        <Icon name={mark.icon} />
        {mark.short || null}
      </TooltipTrigger>
      <TooltipContent>{mark.words}</TooltipContent>
    </Tooltip>
  );
}

export function ActivityMarks({ marks }: { readonly marks: readonly ActivityMark[] }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-2" data-next-entry-notes>
      {marks.map((mark) => (
        <ActivityMarkView key={mark.icon} mark={mark} />
      ))}
    </span>
  );
}

export function ActivityLegend() {
  return (
    <div data-activity-legend className="text-body text-muted-foreground">
      <p className="m-0">Marks</p>
      <ul className="my-1 pl-5">
        {MARK_LEGEND.map((mark) => (
          <li key={mark.icon}>
            <span className="inline-flex items-center gap-2">
              <Icon name={mark.icon} />
              {mark.words}
            </span>
          </li>
        ))}
      </ul>
      <p className="m-0">Failed checks are always listed and never folded.</p>
    </div>
  );
}
