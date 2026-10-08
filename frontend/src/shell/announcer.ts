/* The five live regions and the sentences written into them. Held outside React on purpose: a
   region has to exist BEFORE its first message and outlive every view, because a node that arrives
   carrying its text is the one a reader's software treats as initial content and skips. The legacy
   page built them as siblings of `#app` for that reason, and the React page keeps them as siblings
   of the replaceable subtree (`LiveRegions`).

   Two kinds of write. `say` is a plain write for the three announcers whose every press is its own
   act (attention counts, copy, raise). `announce` is the guarded one for the cue families, and it
   keeps the last sentence written for each standing key, so a reader who presses save twice against
   the same failing store hears it once, and a redraw between the presses cannot replay either. A
   write assigns `textContent`, which always makes a new text node: a repeated sentence is
   therefore a mutation again, which is what lets it be spoken again after a `forget`. */

export type RegionName = 'attention' | 'copy' | 'raise' | 'cue' | 'alert';

/* The legacy ids, kept so a reader's tooling that already finds them still does. */
export const REGION_IDS: Readonly<Record<RegionName, string>> = {
  attention: 'next-attention-status',
  copy: 'next-session-copy-status',
  raise: 'next-session-raise-status',
  cue: 'next-cockpit-cue-status',
  alert: 'next-cockpit-cue-alert',
};

/* Bounded on the same count as the cockpit's held marks. Most keys are dropped with their mark,
   but a settle that lands drops its mark and then announces, so one key per settled session would
   otherwise outlive every mark. */
export const ANNOUNCEMENT_LIMIT = 16;

export interface AnnounceOptions {
  /** The alert region, for the armed discard warning alone. */
  readonly assertive?: boolean;
}

export function createAnnouncer(options: { readonly limit?: number } = {}) {
  const limit = options.limit ?? ANNOUNCEMENT_LIMIT;
  const nodes = new Map<RegionName, HTMLElement>();
  /* Insertion order is recency order (delete before set), so the first key is the one to evict. */
  const said = new Map<string, string>();
  /* Whose armed warning the alert region is holding, or nothing. The region carries that one warning,
     so it holds it only while that arm stands: measured in the accessibility tree, a completed
     discard left the alert node reading "Nothing has been deleted yet" beside a status node reading
     "Discarded ... is gone", because the render had taken the paragraph away and the region was the
     only place the sentence survived. */
  let armedKey: string | null = null;

  function retractArmed(key?: string): void {
    if (armedKey === null) return;
    if (key !== undefined && key !== armedKey) return;
    /* Emptying a region is a removal, and `aria-relevant` does not cover removals, so taking the
       warning back is silent where writing it was not. */
    const region = nodes.get('alert');
    if (region) region.textContent = '';
    armedKey = null;
  }

  return {
    /* Called with the node when a region mounts and returns the call that detaches it. A second
       attach for one region replaces the first, which is what StrictMode's mount, unmount, mount
       leaves behind. */
    attach(region: RegionName, node: HTMLElement): () => void {
      nodes.set(region, node);
      return () => {
        if (nodes.get(region) === node) nodes.delete(region);
      };
    },

    say(region: RegionName, sentence: string): void {
      if (!sentence) return;
      const node = nodes.get(region);
      if (node) node.textContent = sentence;
    },

    announce(key: string, sentence: string, announceOptions: AnnounceOptions = {}): void {
      if (!sentence || said.get(key) === sentence) return;
      const assertive = announceOptions.assertive === true;
      const node = nodes.get(assertive ? 'alert' : 'cue');
      /* Recorded after the write, not before it. A sentence marked announced against a region that
         could not be built would be suppressed for the life of the tab having reached nobody. */
      if (!node) return;
      node.textContent = sentence;
      said.delete(key);
      said.set(key, sentence);
      if (assertive) armedKey = key;
      while (said.size > limit) {
        const oldest = said.keys().next();
        if (oldest.done) break;
        said.delete(oldest.value);
      }
    },

    /* Drops the guard for a key with the mark it guarded, and takes back a warning that mark armed. A
       dropped mark pressed again is a new warning, not a repeat. */
    forget(key: string): void {
      said.delete(key);
      retractArmed(key);
    },

    retractArmed,
  };
}

export type Announcer = ReturnType<typeof createAnnouncer>;
