/* Thrown by a briefing builder that does not exist yet. The press then says so, instead of reporting a clipboard
   failure that would invite the reader to retry something that cannot work. Its own file, so the menu component
   file exports only a component. */
export class BriefingUnavailable extends Error {}
