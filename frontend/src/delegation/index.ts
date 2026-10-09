/* The Console tab and the figures its rail prints. Mount `ProjectConsole` in the project's Console tab with
   the route's project label, its stable key and the exact selected session. The observer-model controls and
   the usage consent belong to the capacity step and are passed in as `observer` and `usage`. The delegation
   figure is measured over the workstream's evidence, so `startWorkstream` must run when the shell is built. */
export { ProjectConsole, type ProjectConsoleProps } from './Console';
export { useProjectWindow } from './evidence';
export { delegationFigure, metricOf, trendOf, MAX_WINDOW_SEC, MIN_WINDOW_SEC } from './metric';
export type { DelegationFigure, Range } from './metric';
export { DelegationPanel } from './DelegationPanel';
export { WaitingPanel } from './WaitingPanel';
export { CapacityPanel } from './CapacityPanel';
export { capacityRows, SLOT_LABELS, type CapacityRailRow } from './capacityRows';
