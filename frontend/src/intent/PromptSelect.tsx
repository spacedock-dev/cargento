import { useState } from 'react';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '../ui/select';
import { useFocusKey } from '../controls';
import { goalKey, promptMenu, promptChoices } from './derive';
import { choosePrompt } from './edit';
import { closePromptMenu, loadPromptChoices } from './prompts';
import { usePanel } from './useIntent';

/* Two different absences, said apart. A long session's focused record holds only its newest events, so
   the reader's own prompts can all lie outside it; that is a limit of what is read, not a claim that
   none were written. */
const EMPTY_NONE =
  'None of your prompts are in the recent part of this session that Cargento reads.';
const EMPTY_FAILED = 'Cargento could not read your prompts from this session.';

/* Open before the async read: a browser picker requested after that read loses the click's user
   activation. Base UI keeps the same popup while loading and across board revisions.
   docs/design-shadcn-adoption.md#form-controls-layer owns that reversal. */
export function PromptSelect() {
  const { ctx, input, session, projectKey } = usePanel();
  const menu = promptMenu(input);
  const [open, setOpen] = useState(false);
  const focusKey = `${goalKey(session)}:prompt`;
  const ref = useFocusKey<HTMLButtonElement>(ctx.shell.controls.focusLane, focusKey);
  // A last offer disappearing must state the absence in the popup the reader already opened.
  if (!menu.visible && !open) return null;
  return (
    <div className="next-intent-prompt-pick ms-auto flex min-w-0 max-w-full w-[18rem] max-[760px]:w-full">
      <Select
        value={menu.value || null}
        open={open}
        items={menu.options}
        onOpenChange={(next) => {
          setOpen(next);
          if (next) void loadPromptChoices(ctx, input, projectKey);
          else closePromptMenu(ctx, session);
        }}
        onValueChange={(value) => {
          if (!value) return;
          choosePrompt(ctx, input, value, promptChoices(ctx.held, input.contexts, session));
        }}
      >
        <SelectTrigger
          ref={ref}
          className="next-intent-prompt-select ps-[12px] font-medium"
          data-next-cockpit-prompt-select
          data-next-focus={focusKey}
          aria-label="Fill the goal from one of your prompts"
          aria-busy={menu.pending}
          title={
            menu.options.find((option) => option.value === menu.value)?.label ?? 'Use your prompt'
          }
        >
          <SelectValue placeholder="Use your prompt" />
        </SelectTrigger>
        <SelectContent>
          {menu.pending ? (
            <SelectItem value="__loading" disabled>
              Loading your prompts
            </SelectItem>
          ) : menu.options.length ? (
            menu.options.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))
          ) : (
            <SelectItem value="__empty" disabled>
              {menu.failed ? EMPTY_FAILED : EMPTY_NONE}
            </SelectItem>
          )}
        </SelectContent>
      </Select>
    </div>
  );
}
