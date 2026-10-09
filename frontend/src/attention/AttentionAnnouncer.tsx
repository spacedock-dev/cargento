import { useEffect } from 'react';
import { useAnnouncer } from '../shell/announcerContext';
import type { Announcer } from '../shell/announcer';
import { useDisplayed } from '../shell/context';
import { attentionAnnouncement, type AttentionModel } from './model';
import { selectAttention } from './select';

/* The previous model each announcer has spoken against. Held outside the component so a remount (a hot
   update, StrictMode's second effect) compares against what was last heard rather than against nothing,
   which would announce the whole board again. */
const previous = new WeakMap<Announcer, AttentionModel | null>();

/* "Attention updated: ..." in the polite status region when a queue changes length, on any page. The
   first board announces nothing: arriving is not a change. Reads the DISPLAYED model, so a poll held back
   by an open option list is announced when it is shown, not while the reader still sees the old one. */
export function AttentionAnnouncer() {
  const announcer = useAnnouncer();
  const model = useDisplayed(selectAttention);
  useEffect(() => {
    const before = previous.get(announcer) ?? null;
    previous.set(announcer, model);
    const sentence = attentionAnnouncement(before, model);
    if (sentence) announcer.say('attention', sentence);
  }, [announcer, model]);
  return null;
}
