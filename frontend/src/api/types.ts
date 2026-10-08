/* Types for the finite route set `http_api.py` serves. They describe what the
   client reads, not the whole payload: the parsed body is kept as the server
   sent it, so a field this file does not name is carried, never dropped.
   Optional means the server may omit the key, and `null` means it published an
   absent value. The two are not interchangeable. */

export interface SessionIdentity {
  readonly harness: string;
  readonly sid: string;
}

export interface PayloadSession {
  readonly harness: string;
  readonly sid: string;
  /** The display id, never an action identity. */
  readonly session?: string;
  readonly project?: string;
  readonly project_key?: string;
  readonly project_name?: string;
  readonly state?: string;
  readonly state_detail?: string;
  readonly active?: boolean;
  readonly focusable?: boolean;
  readonly provider?: string | null;
  readonly model?: string | null;
  readonly title?: string | null;
  readonly started_at?: number | null;
  readonly ended_at?: number | null;
  readonly finished_at?: number | null;
  readonly last_activity?: number;
  readonly source_gaps?: readonly unknown[];
  readonly annotation_revision?: number | null;
  readonly annotation_revision_count?: number;
}

export interface PayloadAsk {
  readonly id: string;
  readonly harness: string;
  readonly session_id: string;
  readonly project: string;
  readonly question: string;
  readonly options: readonly string[];
  readonly age_sec: number;
}

export interface PayloadHarness {
  readonly key: string;
  readonly label?: string;
  /** Whether the harness's store was found at all, which is not whether it holds sessions. */
  readonly discovered?: boolean;
  readonly error?: string;
  readonly reports_rate?: boolean;
  readonly reports_needs_input?: boolean;
}

export interface PayloadData {
  readonly generated?: number;
  readonly build?: string;
  readonly show_all?: boolean;
  readonly sessions?: readonly PayloadSession[];
  readonly asks?: readonly PayloadAsk[];
  readonly harnesses?: readonly PayloadHarness[];
  readonly ask?: boolean;
  readonly dismiss?: boolean;
  readonly annotate?: boolean;
  readonly usage_fetch?: boolean;
  readonly reading_jobs?: unknown;
  readonly reading_routes?: unknown;
}

export interface ObserverModelOffer {
  readonly enabled?: boolean;
  readonly disclosure?: string;
}

export interface ProjectContext {
  readonly observer_model?: ObserverModelOffer;
  readonly observers?: readonly {
    readonly harness: string;
    readonly sid: string;
    readonly goal?: string;
    readonly model?: { readonly status?: string };
  }[];
  readonly prompt_choices?: readonly {
    readonly fact_id: string;
    readonly text: string;
    readonly at?: number;
    readonly cut?: boolean;
  }[];
}

export interface AnnotationsBody {
  readonly annotations?: readonly unknown[];
  readonly intent_revision?: string;
}

export interface InteractionOrigin {
  readonly state?: 'registered' | 'unavailable' | string;
}

export type AnnotateOutcome =
  | 'stored'
  | 'unchanged'
  | 'refused'
  | 'unwritable'
  | 'untrusted'
  | 'unreadable';

export interface AnnotateReceipt {
  readonly ok?: boolean;
  readonly outcome?: AnnotateOutcome | string;
  readonly persisted?: boolean;
  readonly revision?: number;
  readonly saved_revision?: number;
  readonly revision_count?: number;
  readonly discarded?: boolean;
  readonly withdrew?: boolean;
}

export interface DirectionReceipt {
  readonly ok?: boolean;
  readonly text?: string;
  readonly clipped?: boolean;
  readonly why?: string;
}

export interface CorrectionReceipt {
  readonly ok?: boolean;
  readonly parts?: unknown;
  readonly reason?: string;
  readonly why?: string;
}

export interface ReadingReceipt {
  readonly ok?: boolean;
  readonly produced?: boolean;
  readonly reason?: string;
  readonly adoption_refused?: unknown;
  readonly job?: unknown;
}

export interface ReadingCancelReceipt {
  readonly ok?: boolean;
  readonly cancelling?: boolean;
  readonly reason?: string;
}

export interface FocusReceipt {
  readonly focused?: boolean;
}

export interface TripwireReceipt {
  readonly ok?: boolean;
  readonly error?: string;
}

export interface AnswerReceipt {
  readonly answered?: boolean;
}

export interface DismissReceipt {
  readonly ok?: boolean;
  readonly persisted?: boolean;
}

export interface NotifyReceipt {
  readonly ok?: boolean;
  readonly suppressed?: string;
}

/** A request the server received and settled is a status plus a body that may not be JSON. */
export type ApiResult<T> =
  | { readonly kind: 'ok'; readonly status: number; readonly body: T; readonly revision: string }
  | { readonly kind: 'http-error'; readonly status: number; readonly body: unknown }
  | { readonly kind: 'malformed'; readonly status: number }
  | { readonly kind: 'network-error' }
  | { readonly kind: 'aborted' };

export type ApiFailure = Exclude<ApiResult<unknown>, { kind: 'ok' }>;

export type FocusOutcome = 'sent' | 'declined' | 'throttled' | 'stale' | 'failed' | 'unavailable';

export interface ReadingRequest {
  readonly harness: string;
  readonly sid: string;
  readonly provider: string;
  readonly press: true;
  readonly observer_model: 1;
  readonly expected_revision?: number;
  readonly settle_through?: unknown;
  readonly model?: string;
  readonly [adoption: string]: unknown;
}

export interface AnnotateRequest {
  readonly harness: string;
  readonly sid: string;
  readonly expected_revision?: number;
  readonly [field: string]: unknown;
}

export interface TripwireRequest {
  readonly action: string;
  readonly id: string;
  readonly stage: string;
  readonly expected_revision: string;
}
