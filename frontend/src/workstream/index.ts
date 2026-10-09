/* The workstream: what this tab and the history store observed about each project's sessions changing
   state, as evidence a view reads. The Course tab draws the changes; the delegation figure (the steering
   step's) measures the same evidence, so both import the window from here. */
export { ChangesPanel } from './ChangesPanel';
export { changesOf, useProjectChanges } from './changes';
export { collapseFor, useCollapsed } from './collapse';
export {
  createWorkstream,
  payloadEvidence,
  projectChanges,
  projectWindow,
  sessionKey,
  stateLabel,
  transition,
  windowLabel,
  windowPhrase,
  TAB_WINDOW,
  WORKSTREAM_ENTRY_CAP,
  type Batch,
  type Change,
  type ProjectChanges,
  type ProjectWindow,
  type Workstream,
  type WorkstreamEvent,
  type WorkstreamEvidence,
  type WorkstreamSample,
} from './model';
export { startWorkstream, useWorkstreamVersion } from './store';
