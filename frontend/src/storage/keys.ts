import { compatSessKey } from '../api/identity';

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

/**
 * Exact harness and session id. `session` is the display id some rows carry instead of a sid; it
 * only ever completes a storage key, as in the legacy page, and is never an action identity.
 */
export interface SessionIdentity {
  readonly harness: string;
  readonly sid: string;
  readonly session?: string;
}

/** One implementation of the page's `sessKey`, shared with the API layer so the two cannot diverge. */
export const sessionKey: (session: SessionIdentity) => string = compatSessKey;
