import { compatSessKey } from '../api/identity';
import type { Row } from '../observed';
import { isRecord } from '../observed';
import { nextNumber } from '../api/bootstrap';
import type { Ctx } from './context';
import { promptChoices, type DraftInput } from './derive';
import type { PromptChoice } from './held';

/* The prompts "Use your prompt" offers are fetched once per opening of the menu, by the reader's own
   opening gesture, and never by a poll or a mount: a passive read of the focused record that spends
   nothing and sends no model anything. `open` records that the opening is still standing, so a list that
   arrives after the menu was dismissed does not pop it open again. */
export async function loadPromptChoices(
  ctx: Ctx,
  input: DraftInput,
  projectKey: string,
): Promise<void> {
  const key = compatSessKey(input.session);
  const known = ctx.held.prompts.get(key);
  if (known?.pending || known?.open) return;
  ctx.held.prompts.set(key, {
    pending: true,
    open: true,
    choices: promptChoices(ctx.held, input.contexts, input.session),
  });
  ctx.held.notify();
  let choices: PromptChoice[] = [];
  let failed = false;
  let bounded = false;
  try {
    const result = await ctx.shell.runtime.client.getProjectContext({
      project: projectKey,
      session: key,
      prompts: true,
    });
    const body = result.kind === 'ok' ? (result.body as unknown as Row) : null;
    const sources = isRecord(body?.['sources']) ? body['sources'] : null;
    const work = isRecord(sources?.['work']) ? sources['work'] : null;
    const unavailable = Array.isArray(work?.['unavailable']) ? work['unavailable'] : [];
    /* An empty list from a record the server could not read says nothing about the reader's prompts. */
    failed =
      body === null ||
      unavailable.some(
        (entry) =>
          isRecord(entry) &&
          entry['harness'] === input.session['harness'] &&
          entry['sid'] === input.session['sid'],
      );
    const offered = body?.['prompt_choices'];
    const scan = isRecord(body?.['prompt_scan']) ? body['prompt_scan'] : null;
    failed = failed || scan?.['state'] === 'unavailable';
    bounded = scan?.['bound'] === 'bytes' || scan?.['bound'] === 'time';
    choices = Array.isArray(offered)
      ? offered.filter(isRecord).map((choice) => ({
          factId: String(choice['fact_id'] ?? ''),
          text: String(choice['text'] ?? ''),
          at: nextNumber(choice['at']),
          cut: choice['cut'] === true,
        }))
      : [];
  } catch {
    choices = [];
    failed = true;
  }
  ctx.held.prompts.set(key, {
    pending: false,
    open: ctx.held.prompts.get(key)?.open === true,
    choices,
    failed,
    bounded,
  });
  ctx.held.notify();
}

/* The menu is dismissed: Escape, a choice, an outside press or focus leaving the popup. */
export function closePromptMenu(ctx: Ctx, row: Row): void {
  const key = compatSessKey(row);
  const known = ctx.held.prompts.get(key);
  if (known?.open) ctx.held.prompts.set(key, { ...known, open: false });
}
