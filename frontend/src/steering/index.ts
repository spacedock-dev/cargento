/* The project's steering controls and the tab that records its decisions. Mount `ProjectSteer` once in the
   project's chrome, `StageConditions` in the Course tab, and `ProjectDecisions` in the Decisions tab. The
   tripwires panel is part of the Console's rail (`../delegation`), and `Tripwires` is exported for whatever
   else wants it. Everything here is local to the browser: a draft, a tripwire and a receipt are notes the
   reader keeps, and nothing says otherwise. */
export { ProjectSteer } from './ProjectSteer';
export { Tripwires } from './Tripwires';
export { RailHeader } from './RailHeader';
export { StageConditions, type StageConditionsProps } from './StageConditions';
export { ProjectDecisions, type ProjectDecisionsProps } from './ProjectDecisions';
export { steeringHeldFor, STEER_RECORD_LIMIT, type SteeringHeld } from './held';
export { stageData, stageCard, stagePairs, type StageData } from './stage';
export { STEERING_SLOTS } from './slots';
