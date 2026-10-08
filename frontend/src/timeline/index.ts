/* The timeline and its activity filter, for the views that host them (the Decisions panel of a project).
   Mount `Timeline` with the route's project, the project's stable key and, when a session is focused, its
   exact harness and sid. It reads the project context passively and writes nothing but the reader's
   filter choice, to the one released `cargento.next.graph.mode` map. */
export { Timeline, type TimelineProps } from './Timeline';
export { ActivityFilter } from './ActivityFilter';
export { decisionFacts, readSemantic, type Delegation, type SemanticModel } from './semantic';
export { modesOver, useTimelineMode, type FilterScope } from './modes';
