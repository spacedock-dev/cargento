/* Which disclosures the reader has opened, held by key rather than by node.

   The key is the identity: project, scope (or the exact harness and session id
   on a session page) and the disclosure's own name, so two sessions of one
   project never share an open caveat and the Sessions caveats, which carry no
   project, cannot collide with a project's. A component reads this once, when
   it mounts, and writes it back from the browser's own `toggle` event, so a
   remount draws the node already open and its opening motion runs only when the
   reader flips it (docs/design-reader-state.md, "An open disclosure"). Nothing
   here is derived from a DOM attribute, which is why the legacy closed key list
   is not needed: a key only ever comes from a prop.

   Held for the life of the tab and never written to browser storage. */
export function disclosureKey(parts: {
  readonly project: string | null;
  /** The scope, or `harness:sid` on a session page. Empty where the disclosure has none. */
  readonly scope: string | null;
  readonly name: string;
}): string {
  return [parts.project ?? '', parts.scope ?? '', parts.name].join('\n');
}

export function createDisclosureStore() {
  const open = new Map<string, boolean>();
  return {
    isOpen: (key: string): boolean => open.get(key) === true,
    set(key: string, value: boolean): void {
      if (value) open.set(key, true);
      else open.delete(key);
    },
    size: (): number => open.size,
  };
}

export type DisclosureStore = ReturnType<typeof createDisclosureStore>;
