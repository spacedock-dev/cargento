/* Which later migration step brings each view, for the placeholder that stands in for it until then. The step is
   named by what it brings, never by a tracker key: this text ships in the page. */
export const OWNERS = {
  intent: { step: 'intent', what: 'the Intent log' },
  projects: { step: 'projects', what: 'projects and the project workstream' },
  project: { step: 'projects', what: 'projects and the project workstream' },
  attention: { step: 'attention', what: 'Attention' },
} as const;
