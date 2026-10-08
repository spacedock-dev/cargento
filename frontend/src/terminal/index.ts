/* The read-only terminal, for the views that host it (the Console of a project, and a session when it
   offers one). Mount `TerminalSurface` with the route's project and the focused session's exact harness
   and sid. It reads the registration passively and opens nothing until the reader presses Open terminal. */
export { TerminalSurface, type TerminalSurfaceProps } from './TerminalSurface';
export { type OriginLookup } from './registration';
export { terminalOwnerFor, useTerminalOwner } from './useTerminalOwner';
export { useBridgeReading } from './useBridgeReading';
export type { TerminalOwner, TerminalSnapshot } from './owner';
