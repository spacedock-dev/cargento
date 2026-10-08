/*
 * Exact spellings of the twelve persisted families. They stay readable by the legacy page
 * while its rollback exists, so nothing here adds a namespace, wrapper, version or expiry.
 */
export const STORAGE_KEYS = {
  memoPrefix: 'cargento.cockpit.memo.v2:',
  graphMode: 'cargento.next.graph.mode',
  guardrailPrefix: 'cargento.next.guardrails.',
  leader: 'cargento.next.leader',
  liveEstimatePrefix: 'cargento.next.live-estimate:',
  revision: 'cargento.next.revision',
  usageConsent: 'cargento.next.usage.consent',
  workstreamCollapsed: 'cargento.next.workstream.collapsed',
  observerConsent: 'cargento.observer-model-consent.v1',
  cockpitProject: 'cargento.projectCockpitProject',
  goalPrefix: 'cargento.projectGoal.v1:',
  usage: 'cargento.projectUsage.v1',
} as const;

/** Exact harness and session id; a display id never stands in for either. */
export interface SessionIdentity {
  readonly harness: string;
  readonly sid: string;
}

/** The legacy `sessKey`: split a composite only at its first colon, because a sid may contain colons. */
export function sessionKey(session: SessionIdentity): string {
  return `${String(session.harness || '')}:${String(session.sid || '')}`;
}
