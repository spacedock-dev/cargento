import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import vm from 'node:vm';
import { loadLegacyViews, type LegacyViews } from '../observed/legacy.test.helper';

/* The legacy page's Attention model, its text builders and its view, run as the page runs them, for the
   differential tests. The legacy source is the oracle: the page stays the rollback while this one is
   built, so the port is held to what it computes, never to a description of it. The sessions harness
   already loads the boot, observed and session parts; this adds `next-attention.js` and the two small
   functions of `next-chrome.js` the view and the announcer read. Vitest runs from the repository root. */
const WEB = 'cargento/skills/cargento/cargento_runtime/web';

function read(file: string): string {
  return readFileSync(resolve(process.cwd(), WEB, file), 'utf8');
}

/* A function lifted out of a file that is too large to load whole, as source text, so the code that runs
   is the page's and not a copy of it. */
function lift(file: string, names: readonly string[]): string {
  const source = read(file);
  return names
    .map((name) => {
      const start = source.indexOf(`\nfunction ${name}(`);
      if (start < 0) throw new Error(`${file} declares no ${name}.`);
      const end = source.indexOf('\n}\n', start) + 3;
      return source.slice(start, end);
    })
    .join('\n');
}

export interface LegacyAttention extends LegacyViews {
  /** `nextAttentionModel(payload)`. */
  model(payload: unknown): Record<string, unknown>;
  /** `nextAttentionAnnouncement(previous, current)` over two payloads. */
  announcement(previous: unknown, current: unknown): string;
  /** `nextAttentionView(model, expanded, open)` for `payload`, as the page assembles it. */
  attentionHtml(payload: unknown, expanded?: readonly string[], open?: readonly string[]): string;
}

export function loadLegacyAttention(): LegacyAttention {
  const base = loadLegacyViews();
  const { sandbox } = base;
  vm.runInContext(read('next-attention.js'), sandbox, { filename: 'next-attention.js' });
  vm.runInContext(
    lift('next-chrome.js', ['nextDisclosureAttr', 'nextAttentionAnnouncement']),
    sandbox,
    {
      filename: 'lifted-attention.js',
    },
  );
  return {
    ...base,
    model(payload) {
      base.setData(payload);
      return base.call('nextAttentionModel', payload);
    },
    announcement(previous, current) {
      return base.call(
        'nextAttentionAnnouncement',
        base.call('nextAttentionModel', previous),
        base.call('nextAttentionModel', current),
      );
    },
    attentionHtml(payload, expanded = [], open = []) {
      base.setData(payload);
      sandbox['__expanded'] = new Set(expanded);
      sandbox['__open'] = new Set(open);
      const model = base.call('nextAttentionModel', payload);
      sandbox['__model'] = model;
      // `nextViewBody` stamps the subject key a second time for the focus capture; it is part of the markup.
      return base
        .call<string>('nextAttentionView', model, sandbox['__expanded'], sandbox['__open'])
        .replace(
          /data-next-attention-subject="([^"]*)"/g,
          'data-next-attention-subject="$1" data-next-subject-key="$1"',
        );
    },
  };
}
