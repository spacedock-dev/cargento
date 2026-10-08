import type { BoardSnapshot } from '../store/board';
import { attentionModel, type AttentionModel } from './model';

const byBody = new WeakMap<object, AttentionModel>();

/* The model of the accepted body, computed once per body: a subscriber that selects it gets the same
   object back until the data is replaced, which `useSyncExternalStore` needs, and a poll that changed
   nothing costs nothing. Null before the first board, so "nothing has arrived" is never read as an empty
   queue. */
export function attentionFor(body: object | null): AttentionModel | null {
  if (!body) return null;
  let cached = byBody.get(body);
  if (!cached) {
    cached = attentionModel(body);
    byBody.set(body, cached);
  }
  return cached;
}

export function selectAttention(snapshot: BoardSnapshot): AttentionModel | null {
  return attentionFor(snapshot.data);
}
