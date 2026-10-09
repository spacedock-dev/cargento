/* The project views: the Projects list and one project's page (its recovery briefing, scopes, Now, Course,
   and the tab containers the steering step fills), and the briefing the More menu copies. The shell mounts
   `ProjectsView` and `ProjectDetail`; the steering step supplies `PROJECT_SLOTS`'s pieces. */
export { ProjectsView, type ProjectsViewProps } from './ProjectsView';
export { ProjectDetail } from './ProjectDetail';
export { PROJECT_SLOTS, slotContext, type ProjectSlotContext, type ProjectSlots } from './slots';
export { Placeholder } from './SlotPlaceholders';
export { useProjectModel, projectModelFor, briefingOf, noteKey, type ProjectModel } from './model';
export { delegationLanes, type Lane } from './lanes';
export { latestCompletedResult, courseEpisodes, canonicalSemantic } from './course';
export {
  recoveryBriefing,
  commandAttention,
  attentionCoverage,
  decisionFacts,
  captainDecisionCounts,
} from './recovery';
