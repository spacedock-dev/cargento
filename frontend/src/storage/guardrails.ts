import type { StorageAccess } from './backend';
import { STORAGE_KEYS } from './keys';

export const GUARDRAIL_LIMIT = 50;
export const GUARDRAIL_TEXT_LIMIT = 500;

export interface GuardrailRule {
  readonly enabled: boolean;
  readonly text: string;
}

export interface GuardrailChange {
  readonly rules: readonly GuardrailRule[];
  /** False only when a write was attempted and refused; a no-op change attempts none. */
  readonly persisted: boolean;
}

export function guardrailKey(project: string): string {
  return `${STORAGE_KEYS.guardrailPrefix}${encodeURIComponent(project)}`;
}

/** Earlier builds stored bare strings; those read as enabled. Only an explicit `false` disables. */
export function normalizeGuardrail(value: unknown): GuardrailRule | null {
  const source = typeof value === 'string' ? { text: value, enabled: true } : value;
  if (!source || typeof (source as { text?: unknown }).text !== 'string') return null;
  const { text: raw, enabled } = source as { text: string; enabled?: unknown };
  const text = raw.trim().slice(0, GUARDRAIL_TEXT_LIMIT);
  if (!text) return null;
  return { enabled: enabled !== false, text };
}

/** The cap applies after invalid rules are dropped, so it keeps the first fifty usable ones. */
export function decodeGuardrails(raw: string | null): GuardrailRule[] {
  try {
    const parsed: unknown = raw == null ? [] : JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    const rules: GuardrailRule[] = [];
    for (const item of parsed) {
      const rule = normalizeGuardrail(item);
      if (rule) rules.push(rule);
    }
    return rules.slice(0, GUARDRAIL_LIMIT);
  } catch {
    return [];
  }
}

export interface GuardrailStore {
  rules(project: string): readonly GuardrailRule[];
  add(project: string, text: string): GuardrailChange;
  toggle(project: string, index: number): GuardrailChange;
}

export function createGuardrailStore(access: StorageAccess): GuardrailStore {
  // Read from storage once per project, then answer from the tab so a refused write loses nothing.
  const projects = new Map<string, readonly GuardrailRule[]>();
  const current = (project: string): readonly GuardrailRule[] => {
    const known = projects.get(project);
    if (known) return known;
    const read = access.attempt((backend) => backend.getItem(guardrailKey(project)));
    const loaded = read.ok ? decodeGuardrails(read.value) : [];
    projects.set(project, loaded);
    return loaded;
  };
  const commit = (project: string, rules: readonly GuardrailRule[]): GuardrailChange => {
    projects.set(project, rules);
    const persisted = access.attempt((backend) => {
      backend.setItem(guardrailKey(project), JSON.stringify(rules));
    }).ok;
    return { rules: [...rules], persisted };
  };
  return {
    rules: (project) => [...current(project)],
    add(project, text) {
      const rule = normalizeGuardrail({ enabled: true, text });
      const rules = current(project);
      if (!rule) return { rules: [...rules], persisted: true };
      return commit(project, [...rules, rule].slice(-GUARDRAIL_LIMIT));
    },
    toggle(project, index) {
      const rules = current(project);
      const target = Number.isInteger(index) ? rules[index] : undefined;
      if (!target) return { rules: [...rules], persisted: true };
      return commit(
        project,
        rules.map((rule, at) =>
          at === index ? { enabled: !rule.enabled, text: rule.text } : rule,
        ),
      );
    },
  };
}
