import { useEffect } from 'react';
import type { Row } from '../observed';
import { useShell } from '../shell/context';
import { answerNotesFor } from './heldState';

/* A note never outlives its question: what the board no longer carries is forgotten. Run by the session
   page itself on every payload, not by the block that draws the notes, because the block is not drawn once
   its question has left, and a note kept past that would greet the same id if it ever came back. */
export function usePruneAnswerNotes(payload: Row): void {
  const { runtime } = useShell();
  useEffect(() => {
    const all = Array.isArray(payload['asks']) ? (payload['asks'] as unknown[]) : [];
    answerNotesFor(runtime).prune(new Set(all.map((ask) => String((ask as Row | null)?.['id'] ?? ''))));
  }, [runtime, payload]);
}

