import { payloadSessions } from '../api/bootstrap';
import { exactIdentity } from '../api/identity';
import type { ApiResult, SessionIdentity } from '../api/types';
import { isRecord, type Row } from '../observed';
import type { Shell } from '../shell/context';
import type { PendingToken } from '../transport/pending';
import { annotationOf } from './annotation';
import type { DraftInput } from './derive';
import type { Held } from './held';

/* What every Intent action reads and writes: the shell's owners and the reader's held state, and nothing
   else. An action is one explicit press of one control. Nothing here is started by a mount, a second
   mount under StrictMode, a poll, a reconnect or a retry. */
export interface Ctx {
  readonly shell: Shell;
  readonly held: Held;
}

/* The row the last accepted board published for this exact session, or null. The accepted board and not
   the one a held paint is showing: a press acts on the newest words, and refuses over a reader's edit
   whichever board they are looking at. */
export function liveRow(ctx: Ctx, identity: SessionIdentity): Row | null {
  const data = ctx.shell.runtime.store.getSnapshot().data;
  if (!data) return null;
  const found = payloadSessions(data).rows.find(
    (row) => row.harness === identity.harness && row.sid === identity.sid,
  );
  return (found as unknown as Row | undefined) ?? null;
}

export function readInput(
  ctx: Ctx,
  identity: SessionIdentity,
  row?: Row | null,
): DraftInput | null {
  const snapshot = ctx.shell.runtime.store.getSnapshot();
  const session = row ?? liveRow(ctx, identity);
  if (!session || !snapshot.data) return null;
  return {
    held: ctx.held,
    contexts: snapshot.contexts,
    payload: snapshot.data as unknown as Row,
    session,
    annotation: annotationOf(session),
  };
}

/* The exact pair a request names, never a display id: a row that carries only a display id has no action
   to send. */
export function identityOf(session: Row): SessionIdentity | null {
  return exactIdentity(session);
}

export function pendingStart(ctx: Ctx, key: string, busy: string, say = ''): PendingToken | null {
  return ctx.shell.runtime.pending.start(key, busy, say);
}

export function pendingEnd(ctx: Ctx, key: string, token: PendingToken | null): void {
  ctx.shell.runtime.pending.end(key, token);
}

export function pendingHas(ctx: Ctx, key: string): boolean {
  return ctx.shell.runtime.pending.has(key);
}

export async function refresh(ctx: Ctx): Promise<void> {
  await ctx.shell.runtime.refresh();
}

/* A request's answer as the legacy handlers saw it. An answered refusal (an HTTP status) is not a lost
   answer, and a body that could not be read is lost: the page cannot tell whether the write landed, so it
   says so and keeps the words. A bare `ok` is the transport's, so a caller still reads the body's own. */
export type Answer<T> =
  | {
      readonly kind: 'answered';
      readonly ok: boolean;
      readonly status: number;
      readonly body: T | null;
    }
  | { readonly kind: 'lost' };

export function answered<T>(result: ApiResult<T>): Answer<T> {
  switch (result.kind) {
    case 'ok':
      return { kind: 'answered', ok: true, status: result.status, body: result.body };
    case 'http-error':
      return {
        kind: 'answered',
        ok: false,
        status: result.status,
        body: isRecord(result.body) ? (result.body as T) : null,
      };
    default:
      return { kind: 'lost' };
  }
}

export const announce = (ctx: Ctx, key: string, sentence: string): void =>
  ctx.shell.announcer.announce(key, sentence);
