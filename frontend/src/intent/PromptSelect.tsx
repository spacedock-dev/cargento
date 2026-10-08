import { useFocusKey } from '../controls';
import { goalKey, promptMenu } from './derive';
import { choosePrompt } from './edit';
import { closePromptMenu, loadPromptChoices } from './prompts';
import { usePanel } from './useIntent';
import { promptChoices } from './derive';

/* "Use your prompt": one native select in the goal's label row. Picking one fills the box as a pending
   adoption and saves nothing. A native select so the browser's own list drops over the page and moves
   nothing; a poll redraw cannot shut it mid-choice because the display gate defers a background paint while a
   select holds focus. Its options are fetched once per opening, by the reader's own opening gesture. */
export function PromptSelect() {
  const { ctx, input, session, projectKey } = usePanel();
  const menu = promptMenu(input);
  const focusKey = `${goalKey(session)}:prompt`;
  const ref = useFocusKey<HTMLSelectElement>(ctx.shell.controls.focusLane, focusKey);
  if (!menu.visible) return null;
  const open = (event: {
    readonly type: string;
    readonly key?: string;
    preventDefault(): void;
    readonly currentTarget: HTMLSelectElement;
  }) => {
    const select = event.currentTarget;
    if (event.type === 'keydown' && event.key === 'Escape') {
      closePromptMenu(ctx, session);
      return;
    }
    if (
      event.type === 'keydown' &&
      !['ArrowDown', 'ArrowUp', ' ', 'Enter'].includes(event.key ?? '')
    ) {
      return;
    }
    if (typeof select.showPicker === 'function') {
      event.preventDefault();
      select.focus();
      void loadPromptChoices(ctx, input, projectKey).then(() => {
        if (!select.isConnected || ctx.held.prompts.get(compatKey(session))?.open !== true) return;
        try {
          select.showPicker();
        } catch {
          select.focus();
        }
      });
    } else {
      void loadPromptChoices(ctx, input, projectKey);
    }
  };
  return (
    <label className="next-intent-prompt-pick">
      <span className="next-visually-hidden">Fill the goal from one of your prompts</span>
      <select
        ref={ref}
        className="next-intent-prompt-select"
        data-next-cockpit-prompt-select
        data-next-focus={focusKey}
        value={menu.value}
        onPointerDown={open}
        onKeyDown={open}
        onBlur={() => closePromptMenu(ctx, session)}
        onChange={(event) => {
          if (!event.currentTarget.value) return;
          closePromptMenu(ctx, session);
          choosePrompt(
            ctx,
            input,
            event.currentTarget.value,
            promptChoices(ctx.held, input.contexts, session),
          );
        }}
      >
        <option value="">Use your prompt</option>
        {menu.options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function compatKey(row: Record<string, unknown>): string {
  return `${String(row['harness'] || '')}:${String(row['sid'] || row['session'] || '')}`;
}
